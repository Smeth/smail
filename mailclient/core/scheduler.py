"""Envoi (immédiat ou programmé) et report de messages, traités par Smail tant qu’il est ouvert.

Principe constant : un envoi SMTP n’est jamais relancé automatiquement. Un envoi programmé passe à
l’état « sending » avant la connexion SMTP ; s’il est retrouvé dans cet état au démarrage (coupure,
arrêt brutal), il devient « uncertain » et attend une décision de l’utilisateur.
"""
from mailclient.i18n import tr
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


def send_and_record(service, account, state, files, progress=None):
    """Envoi SMTP puis copie locale et carnet d’adresses ; renvoie (brut, refusés, id de copie locale)."""
    from mailclient.core.quote import merged
    body, document = merged(state)  # Réponse puis citation mise en forme de l’original, s’il y en a une.
    message, recipients = build_message(account, state['to'], state['cc'], state['bcc'], state['subject'], body, files,
                                        state.get('reply_id', ''), state.get('references', ''), html=document,
                                        calendar=state.get('calendar', ''))
    extra = dict(progress=progress) if progress else {}
    refused = send_message(account, service.oauth.credential(account, 'smtp'), service.tls, message, recipients, **extra)
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
        raise RuntimeError(tr('Dossier Envoyés introuvable. La copie locale est conservée.'))
    service.client(account).append(folder, raw, False)
    if local_id:
        copy = service.db.cache_get('sent-copy', local_id)
        if copy:
            copy['server_saved'] = True
            service.db.cache_put('sent-copy', local_id, copy)
    return folder


COPY_ATTEMPTS = 3


def retry_sent_copies(service, accounts) -> int:
    """Copies dans Envoyés restées en échec (connexion coupée…) : nouvel essai, au plus COPY_ATTEMPTS fois.

    Le serveur a pu enregistrer la copie sans pouvoir le confirmer : on cherche d’abord le Message-ID dans
    Envoyés pour ne jamais créer de doublon. Renvoie le nombre de copies désormais enregistrées."""
    from email import message_from_bytes
    by_id = {account.id: account for account in accounts}
    saved = 0
    for copy in service.db.cache_list('sent-copy'):
        account = by_id.get(copy.get('account'))
        if copy.get('server_saved') or account is None or copy.get('attempts', 0) >= COPY_ATTEMPTS:
            continue
        try:
            if gmail(account):
                folder = None
            else:
                raw = base64.b64decode(copy['raw'])
                folders, _ = service.folders(account)
                folder = next((name for name, label in folders if any(word in (name + ' ' + label).casefold() for word in ('envoyés', 'sent'))), None)
                if not folder:
                    raise RuntimeError(tr('Dossier Envoyés introuvable.'))
                message_id = (message_from_bytes(raw[:65536]).get('Message-ID') or '').strip()
                found = service.client(account).find_by_message_id(folder, message_id)[0] if message_id else ''
                if not found:
                    service.client(account).append(folder, raw, False)
            copy['server_saved'] = True
            saved += 1
        except Exception as error:
            copy['attempts'] = copy.get('attempts', 0) + 1
            log.warning('Nouvel essai de copie dans Envoyés impossible (%s)', type(error).__name__)
        service.db.cache_put('sent-copy', copy['id'], copy)
    return saved


# Boîte d’envoi locale ------------------------------------------------------------------------

def schedule(db, account, state, files, when: datetime, item_id=None) -> dict:
    if when <= now_utc():
        raise ValueError(tr('Choisissez une date et une heure à venir.'))
    item = dict(id=item_id or str(uuid4()), account=account.id, state=dict(state), files=encode_files(files),
                send_at=iso(when), status='scheduled', error='')
    db.cache_put('outbox', item['id'], item, account.id)
    return item


def enqueue(db, account, state, files, delay=0, item_id=None) -> dict:
    """Envoi immédiat en arrière-plan : il part dans `delay` secondes (délai d’annulation), par la boîte d’envoi."""
    from datetime import timedelta
    item = dict(id=item_id or str(uuid4()), account=account.id, state=dict(state), files=encode_files(files),
                send_at=iso(now_utc() + timedelta(seconds=max(0, delay))), status='scheduled', error='', immediate=True)
    db.cache_put('outbox', item['id'], item, account.id)
    return item


def due(db, moment=None) -> list:
    """Envois arrivés à échéance, du plus ancien au plus récent."""
    moment = moment or now_utc()
    return [item for item in outbox(db) if item.get('status') == 'scheduled' and parse(item['send_at']) <= moment]


def send_now(db, item_id) -> None:
    """Avance l’échéance (fermeture de Smail pendant le délai d’annulation : le message part avant)."""
    item = db.cache_get('outbox', item_id)
    if item and item.get('status') == 'scheduled':
        item['send_at'] = iso(now_utc())
        db.cache_put('outbox', item['id'], item, item['account'])


def deliver_item(service, account, item, progress=None) -> tuple:
    """Envoie un message de la boîte d’envoi ; renvoie (événement, sujet, détail).

    L’état « sending » est enregistré avant SMTP : un arrêt brutal le rend « incertain », jamais renvoyé."""
    subject = item['state'].get('subject') or tr('(Sans objet)')
    item['status'] = 'sending'
    service.db.cache_put('outbox', item['id'], item, account.id)
    try:
        raw, refused, local_id = send_and_record(service, account, item['state'], decode_files(item['files']), progress)
    except Exception as error:
        from mailclient.core.sync import friendly_error
        from mailclient.core.smtp_client import DeliveryUncertain
        uncertain = isinstance(error, DeliveryUncertain)
        item.update(status='uncertain' if uncertain else 'failed',
                    error=friendly_error(error) + ('' if uncertain else ' ' + tr('Aucun renvoi automatique : vérifiez vos Envoyés.')))
        service.db.cache_put('outbox', item['id'], item, account.id)
        return ('uncertain' if uncertain else 'failed'), subject, item['error']
    if refused:
        item.update(status='partial', error=tr('Destinataires refusés : {addresses}. Les autres ont reçu le message.').format(addresses=', '.join(refused)))
        service.db.cache_put('outbox', item['id'], item, account.id)
        event = ('partial', subject, item['error'])
    else:
        service.db.cache_delete('outbox', item['id'])
        event = ('sent', subject, '')
    mark_origin(service, item['state'].get('origin'))
    remove_server_draft(service, item['state'].get('server_draft'))
    if progress:
        progress('copy', 0, 0)
    try:
        copy_to_sent(service, account, raw, local_id)
    except Exception as error:
        log.warning('Copie Envoyés d’un envoi non effectuée (%s)', type(error).__name__)
        if event[0] == 'sent':
            event = ('sent', subject, tr('Copie dans Envoyés non effectuée ; une copie locale est conservée.'))
    return event


def mark_origin(service, origin) -> None:
    """Message d’origine d’une réponse ou d’un transfert marqué « répondu » / « transféré » sur le serveur.
    Au mieux : un refus (serveur sans mots-clés, message déplacé entre-temps) n’affecte jamais l’envoi."""
    if not origin or origin.get('flag') not in ('answered', 'forwarded'):
        return
    account = next((a for a in service.db.accounts() if a.id == origin.get('account')), None)
    if account is None:
        return
    try:
        service.action(account, [dict(origin)], origin['flag'])
    except Exception as error:
        log.info('Drapeau « %s » non posé (%s)', origin['flag'], type(error).__name__)


def remove_server_draft(service, draft) -> bool:
    """Brouillon du serveur envoyé ou remplacé : retiré du dossier Brouillons (au mieux, jamais bloquant)."""
    if not draft or not draft.get('uid') or not draft.get('uidvalidity'):
        return False
    account = next((a for a in service.db.accounts() if a.id == draft.get('account')), None)
    if account is None:
        return False
    try:
        service.action(account, [dict(draft)], 'delete')
        return True
    except Exception as error:
        log.info('Ancien brouillon du serveur non retiré (%s)', type(error).__name__)
        return False


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
            item.update(status='uncertain', error=tr('Smail a été fermé pendant l’envoi. Vérifiez vos Envoyés avant toute nouvelle tentative.'))
            db.cache_put('outbox', item['id'], item, item['account'])
            count += 1
    return count


def process_outbox(service, accounts, moment=None) -> list:
    """Envoie les messages programmés arrivés à échéance ; renvoie [(événement, sujet, détail)]."""
    moment = moment or now_utc()
    by_id = {account.id: account for account in accounts}
    events = []
    for item in due(service.db, moment):
        account = by_id.get(item['account'])
        if account is not None:
            events.append(deliver_item(service, account, item))
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
        raise RuntimeError(tr('Dossier « Reportés » introuvable après sa création. Actualisez les dossiers puis réessayez.'))
    return found


def snooze(service, account, rows, until: datetime) -> str:
    """Déplace les messages vers « Reportés » et mémorise leur retour (retrouvés par Message-ID)."""
    if until <= now_utc():
        raise ValueError(tr('Choisissez une date et une heure à venir.'))
    if any(not row.get('message_id') for row in rows):
        raise RuntimeError(tr('Ce message n’a pas d’identifiant Message-ID : il ne peut pas être reporté. Actualisez le dossier puis réessayez.'))
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
