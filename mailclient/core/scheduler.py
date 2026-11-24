"""Envoi (immédiat ou programmé) et report de messages, traités par Smail tant qu’il est ouvert.

Principe constant : un envoi SMTP n’est jamais relancé automatiquement. Un envoi programmé passe à
l’état « sending » avant la connexion SMTP ; s’il est retrouvé dans cet état au démarrage (coupure,
arrêt brutal), il devient « uncertain » et attend une décision de l’utilisateur.
"""
import base64
import logging
from datetime import datetime, timezone
from uuid import uuid4
from mailclient.core.parser import Attachment
from mailclient.core.smtp_client import addresses, build_message, send_message

SNOOZE_NAMES = ('Reportés', 'Snoozed')
log = logging.getLogger('smail')


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec='seconds')


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def gmail(account) -> bool:
    return account.auth_method == 'google' or account.smtp.host.lower() == 'smtp.gmail.com'


def encode_files(files) -> list:
    return [dict(name=item.name, type=item.content_type, data=base64.b64encode(item.data).decode('ascii')) for item in files]


def decode_files(items) -> list:
    return [Attachment(item['name'], item['type'], base64.b64decode(item['data'])) for item in items or []]


def send_and_record(service, account, state, files):
    """Envoi SMTP puis copie locale et carnet d’adresses ; renvoie (brut, refusés, id de copie locale)."""
    message, recipients = build_message(account, state['to'], state['cc'], state['bcc'], state['subject'], state['body'], files,
                                        state.get('reply_id', ''), state.get('references', ''), html=state.get('mail_html', ''),
                                        calendar=state.get('calendar', ''))
    refused = send_message(account, service.oauth.credential(account, 'smtp'), service.tls, message, recipients)
    raw = message.as_bytes()
    local_id = str(uuid4())
    try:
        service.db.cache_put('sent-copy', local_id, dict(id=local_id, account=account.id, raw=base64.b64encode(raw).decode('ascii'), server_saved=False))
    except Exception:
        local_id = None  # L’envoi a réussi : jamais de renvoi pour une erreur de cache.
    try:
        rejected = {value.casefold() for value in refused}
        accepted = [pair for field in ('to', 'cc', 'bcc') for pair in addresses(state[field]) if pair[1].casefold() not in rejected]
        service.remember_contacts(account, accepted, sent=True)
    except Exception:
        pass
    return raw, list(refused), local_id


def copy_to_sent(service, account, raw, local_id=None) -> str:
    """Copie dans le dossier Envoyés du serveur (Gmail la fait lui-même). Renvoie le dossier utilisé."""
    if gmail(account):
        return 'gmail'
    folders, _ = service.folders(account)
    folder = next((name for name, label in folders if any(word in (name + ' ' + label).casefold() for word in ('envoyés', 'sent'))), None)
    if not folder:
        raise RuntimeError('Dossier Envoyés introuvable. La copie locale est conservée.')
    service.client(account).append(folder, raw, False)
    if local_id:
        copy = service.db.cache_get('sent-copy', local_id)
        if copy:
            copy['server_saved'] = True
            service.db.cache_put('sent-copy', local_id, copy)
    return folder


# Boîte d’envoi locale ------------------------------------------------------------------------

def schedule(db, account, state, files, when: datetime, item_id=None) -> dict:
    if when <= now_utc():
        raise ValueError('Choisissez une date et une heure à venir.')
    item = dict(id=item_id or str(uuid4()), account=account.id, state=dict(state), files=encode_files(files),
                send_at=iso(when), status='scheduled', error='')
    db.cache_put('outbox', item['id'], item, account.id)
    return item


def outbox(db) -> list:
    return sorted(db.cache_list('outbox'), key=lambda item: item['send_at'])


def cancel(db, item_id) -> dict | None:
    """Retire un envoi programmé ; renvoie son contenu (pour le rouvrir comme brouillon)."""
    item = db.cache_get('outbox', item_id)
    if item:
        db.cache_delete('outbox', item_id)
    return item


def recover(db) -> int:
    """Au démarrage : un envoi interrompu en cours n’est jamais relancé, il devient « incertain »."""
    count = 0
    for item in db.cache_list('outbox'):
        if item.get('status') == 'sending':
            item.update(status='uncertain', error='Smail a été fermé pendant l’envoi. Vérifiez vos Envoyés avant toute nouvelle tentative.')
            db.cache_put('outbox', item['id'], item, item['account'])
            count += 1
    return count


def process_outbox(service, accounts, moment=None) -> list:
    """Envoie les messages programmés arrivés à échéance ; renvoie [(événement, sujet, détail)]."""
    moment = moment or now_utc()
    by_id = {account.id: account for account in accounts}
    events = []
    for item in outbox(service.db):
        if item.get('status') != 'scheduled' or parse(item['send_at']) > moment:
            continue
        account = by_id.get(item['account'])
        subject = item['state'].get('subject') or '(Sans objet)'
        if account is None:
            continue
        item['status'] = 'sending'
        service.db.cache_put('outbox', item['id'], item, account.id)  # Avant SMTP : aucun double envoi possible.
        try:
            raw, refused, local_id = send_and_record(service, account, item['state'], decode_files(item['files']))
        except Exception as error:
            from mailclient.core.sync import friendly_error
            item.update(status='failed', error=friendly_error(error) + ' Aucun renvoi automatique : vérifiez vos Envoyés.')
            service.db.cache_put('outbox', item['id'], item, account.id)
            events.append(('failed', subject, item['error']))
            continue
        if refused:
            item.update(status='partial', error='Destinataires refusés : ' + ', '.join(refused) + '. Les autres ont reçu le message.')
            service.db.cache_put('outbox', item['id'], item, account.id)
            events.append(('partial', subject, item['error']))
        else:
            service.db.cache_delete('outbox', item['id'])
            events.append(('sent', subject, ''))
        try:
            copy_to_sent(service, account, raw, local_id)
        except Exception as error:
            log.warning('Copie Envoyés d’un envoi programmé non effectuée (%s)', type(error).__name__)
    return events


# Report (snooze) -----------------------------------------------------------------------------

def snooze_folder(service, account) -> str:
    folders, _ = service.folders(account)
    def find(items):
        # Libellé décodé ; « INBOX.Reportés » sur les serveurs qui imposent ce préfixe.
        return next((name for name, label in items if any(label == n or label.endswith(('.' + n, '/' + n)) for n in SNOOZE_NAMES)), None)
    found = find(folders)
    if found:
        return found
    found = find(service.manage_folder(account, 'create', SNOOZE_NAMES[0]))
    if not found:
        raise RuntimeError('Dossier « Reportés » introuvable après sa création. Actualisez les dossiers puis réessayez.')
    return found


def snooze(service, account, rows, until: datetime) -> str:
    """Déplace les messages vers « Reportés » et mémorise leur retour (retrouvés par Message-ID)."""
    if until <= now_utc():
        raise ValueError('Choisissez une date et une heure à venir.')
    if any(not row.get('message_id') for row in rows):
        raise RuntimeError('Ce message n’a pas d’identifiant Message-ID : il ne peut pas être reporté. Actualisez le dossier puis réessayez.')
    folder = snooze_folder(service, account)
    sources = [row for row in rows if row['folder'] != folder]
    if sources:
        service.action(account, sources, 'move', folder)
    for row in rows:
        record = dict(id=str(uuid4()), account=account.id, message_id=row['message_id'], folder=folder,
                      back_to=row['folder'] if row['folder'] != folder else 'INBOX', until=iso(until), subject=row.get('subject', ''))
        service.db.cache_put('snooze', record['id'], record, account.id)
    return folder


def process_snoozes(service, accounts, moment=None) -> list:
    """Ramène les messages reportés arrivés à échéance, non lus, dans leur dossier d’origine."""
    moment = moment or now_utc()
    by_id = {account.id: account for account in accounts}
    events = []
    for record in service.db.cache_list('snooze'):
        account = by_id.get(record['account'])
        if account is None or parse(record['until']) > moment:
            continue
        try:
            client = service.client(account)
            uids, validity = client.find_by_message_id(record['folder'], record['message_id'])
            if uids:
                client.action(record['folder'], uids, validity, 'unread')
                client.action(record['folder'], uids, validity, 'move', record['back_to'])
                events.append(('returned', record.get('subject') or '(Sans objet)', record['back_to']))
        except Exception as error:
            log.warning('Retour de message reporté différé (%s)', type(error).__name__)
            continue  # Nouvel essai au prochain passage : un déplacement IMAP peut être retenté sans risque.
        service.db.cache_delete('snooze', record['id'])  # Introuvable : déplacé ou supprimé entre-temps.
    return events
