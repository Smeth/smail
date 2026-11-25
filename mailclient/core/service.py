"""Coordination du cache, de l’authentification et des opérations réseau."""
from mailclient.i18n import tr
import base64
import html
import re
import threading
from datetime import timezone
from email.utils import getaddresses, parsedate_to_datetime
from mailclient.core.imap_client import IMAPClient, ConnectionPool
from mailclient.core.oauth import OAuth
from mailclient.core.parser import parse_message, snippet
from mailclient.core.tls_policy import CertificateAlert
from mailclient.core.threads import chronological, row_ids, thread_ids, timestamp
from mailclient.core.search_query import parse as parse_query, matches as query_matches
from mailclient.core import filters
import logging

def cache_key(*values) -> str:
    import json
    return json.dumps(values, ensure_ascii=False)

def save_signature(database, account_id, qt_html=''):
    """Signature mise en forme du compte ; vide : signature texte seule (configuration du compte)."""
    if qt_html:
        database.cache_put('signature', account_id, dict(account=account_id, qt_html=qt_html), account_id)
    else:
        database.cache_delete('signature', account_id)

class MailService:
    def __init__(self, database, vault, tls):
        self.db, self.vault, self.tls = database, vault, tls
        self.oauth = OAuth(vault)
        self.pool = ConnectionPool()
        self.contacts_lock = threading.Lock()
        self.last_filtered = 0

    def client(self, account):
        return IMAPClient(account, self.oauth.credential(account), self.tls, self.pool)

    def folders(self, account, cache_only=False):
        key = account.id
        if not cache_only:
            try:
                folders = self.client(account).folders()
                self.db.cache_put('folders', key, folders, account.id)
                return folders, False
            except CertificateAlert:
                raise
            except Exception:
                cached = self.db.cache_get('folders', key)
                if cached is None:
                    raise
                return cached, True
        return self.db.cache_get('folders', key, []), True

    def _enrich(self, rows, account, folder):
        server = f'{account.imap.host}:{account.imap.port}:{account.imap.mode}'
        return [dict(row, account=account.id, folder=folder, server=server) for row in rows]

    def state(self, account, folder):
        return self.db.cache_get('mailbox', cache_key(account.id, folder))

    def messages(self, account, folder, page=0, query='', cache_only=False):
        key = cache_key(account.id, folder)
        if not cache_only:
            try:
                client = self.client(account)
                rows, total = client.messages(folder, page, query)
                rows = self._enrich(rows, account, folder)
                old = self.state(account, folder) or {}
                self._carry_previews(rows, old)
                if not query:
                    pages = old.get('pages', {}) if old.get('uidvalidity') == client.uidvalidity else {}
                    pages[str(page)] = rows
                    state = dict(account=account.id, folder=folder, pages=pages, total=total, uidvalidity=client.uidvalidity)
                    self.db.cache_put('mailbox', key, state)
                return dict(rows=rows, total=total, offline=False)
            except CertificateAlert:
                raise
            except Exception:
                if self.state(account, folder) is None:
                    raise
        state = self.state(account, folder) or {}
        if query:
            rows = self._search(self._known_rows(state), query)
            return dict(rows=rows[page*50:(page+1)*50], total=len(rows), offline=True)
        return dict(rows=state.get('pages', {}).get(str(page), []), total=state.get('total', 0), offline=True)

    @staticmethod
    def _carry_previews(rows, state):
        """Reprend les aperçus déjà calculés (même UIDVALIDITY et UID) : la liste en ligne n’a que les en-têtes."""
        known = {(row.get('uidvalidity'), row['uid']): row['preview'] for page in (state or {}).get('pages', {}).values()
                 for row in page if row.get('preview') is not None}
        for row in rows:
            if row.get('preview') is None and (row.get('uidvalidity'), row['uid']) in known:
                row['preview'] = known[row.get('uidvalidity'), row['uid']]

    def _remember_preview(self, account, row, preview):
        state = self.state(account, row['folder'])
        if not state:
            return
        changed = False
        for page in state.get('pages', {}).values():
            for item in page:
                if item['uid'] == row['uid'] and item.get('uidvalidity') == row.get('uidvalidity') and item.get('preview') is None:
                    item['preview'] = preview
                    changed = True
        if changed:
            self.db.cache_put('mailbox', cache_key(account.id, row['folder']), state)

    @staticmethod
    def _known_rows(state):
        rows = {row['uid']: row for page in state.get('pages', {}).values() for row in page}
        return sorted(rows.values(), key=lambda row: int(row['uid']), reverse=True)

    # Règles, expéditeurs bloqués et spam : appliqués côté client aux nouveaux messages de la réception.
    def apply_filters(self, account, folders, rows, validity, backlog=False):
        """Applique les filtres aux messages de la réception arrivés depuis le dernier passage.

        Au premier passage (ou après recréation du dossier), seul le repère est posé : les messages déjà
        présents ne sont jamais déplacés à l’insu de l’utilisateur. backlog=True traite toutes les lignes
        fournies (« Appliquer maintenant »). Renvoie les lignes restant dans la réception."""
        data = filters.load(self.db)
        mark = self.db.cache_get('filtered', account.id)
        highest = max((int(row['uid']) for row in rows), default=0)
        if not backlog and (not mark or mark.get('validity') != validity):
            self.db.cache_put('filtered', account.id, dict(validity=validity, uid=highest), account.id)
            return rows
        threshold = 0 if backlog else mark['uid']
        plan = {}
        for row in rows:
            if int(row['uid']) <= threshold:
                continue
            decision = filters.decide(row, data, account.id)
            if decision:
                action, target, _ = decision
                plan.setdefault((action, target), []).append(row)
        removed, client = set(), None
        for (action, target), group in plan.items():
            if action in {'junk', 'trash'}:
                target = filters.special_folder(folders, filters.JUNK_WORDS if action == 'junk' else filters.TRASH_WORDS, 'INBOX')
            elif action == 'move' and target not in {name for name, _ in folders}:
                target = None
            if action in {'junk', 'trash', 'move'} and not target:
                logging.getLogger('smail').warning('Filtre ignoré : dossier de destination introuvable (%s)', action)
                continue
            step = {'read': 'read', 'star': 'star'}.get(action, 'move')
            try:
                client = client or self.client(account)
                client.action(tr('INBOX'), ','.join(row['uid'] for row in group), validity, step, target or '')
            except CertificateAlert:
                raise
            except Exception as error:
                logging.getLogger('smail').warning('Filtre non appliqué (%s)', type(error).__name__)
                continue
            for row in group:
                if step == 'move':
                    removed.add(row['uid'])
                    self.db.cache_delete('body', self.body_key(row))
                elif step == 'read':
                    row['unread'] = False
                else:
                    row['starred'] = True
        if not backlog or highest > (mark or {}).get('uid', 0):
            self.db.cache_put('filtered', account.id, dict(validity=validity, uid=max(highest, (mark or {}).get('uid', 0))), account.id)
        self.last_filtered = sum(len(group) for group in plan.values())
        return [row for row in rows if row['uid'] not in removed]

    def apply_filters_now(self, account):
        """« Appliquer maintenant » : filtres appliqués à toute la réception synchronisée."""
        folders = self.client(account).folders()
        inbox = next((name for name, _ in folders if name.upper() == 'INBOX'), 'INBOX')
        state = self.state(account, inbox) or {}
        rows = self._known_rows(state)
        if not rows:
            return 0
        kept = self.apply_filters(account, folders, rows, state.get('uidvalidity', ''), backlog=True)
        moved = {row['uid'] for row in rows} - {row['uid'] for row in kept}
        for page, items in state.get('pages', {}).items():
            state['pages'][page] = [item for item in items if item['uid'] not in moved]
        state['total'] = max(0, state.get('total', 0) - len(moved))
        state.pop('status', None)  # Prochaine synchronisation complète de la réception.
        self.db.cache_put('mailbox', cache_key(account.id, inbox), state)
        return self.last_filtered

    def junk(self, account, rows, folders, block=False, trust=False):
        """Signaler comme spam (option : bloquer les expéditeurs) ou « Ce n’est pas un spam » (trust)."""
        data = filters.load(self.db)
        senders = {filters.normalize_sender(addr) for row in rows for _, addr in getaddresses([row.get('sender', '')]) if addr}
        if block:
            data['blocked'] = sorted(set(data['blocked']) | senders)
            data['safe'] = [entry for entry in data['safe'] if entry not in senders]
        if trust:
            data['safe'] = sorted(set(data['safe']) | senders)
            data['blocked'] = [entry for entry in data['blocked'] if entry not in senders]
        filters.save(self.db, data)
        source = rows[0]['folder'] if rows else ''
        if trust:
            target = next((name for name, _ in folders if name.upper() == 'INBOX'), 'INBOX')
        else:
            target = filters.special_folder(folders, filters.JUNK_WORDS, source)
            if not target:
                raise RuntimeError(tr('Dossier des indésirables introuvable sur le serveur. Créez-le (Dossier › Nouveau dossier) puis actualisez.'))
        if rows and source != target:
            self.action(account, rows, 'move', target)
        return target

    # Signature mise en forme : entrée de cache du compte (chiffrée avec le cache, purgée avec le compte).
    # La configuration du compte garde la version texte, lisible par Smail 1.0.0.
    def signature(self, account):
        value = self.db.cache_get('signature', account.id) if account else None
        return value if value and value.get('qt_html') else None

    def set_signature(self, account, qt_html=''):
        save_signature(self.db, account.id, qt_html)

    # Carnet d’adresses : une entrée de cache par compte (chiffrée avec le cache, purgée avec le compte).
    def remember_contacts(self, account, pairs, sent=False):
        """pairs : [(nom, adresse)]. Un envoi incrémente le compteur ; un expéditeur vu est seulement ajouté."""
        own = account.email.casefold()
        with self.contacts_lock:
            book = self.db.cache_get('contacts', account.id) or dict(account=account.id, entries={})
            entries, changed = book['entries'], False
            for name, address in pairs:
                address = address.strip()
                key = address.casefold()
                if not address or '@' not in address or key == own or len(address) > 254 or any(ord(c) < 32 for c in name + address):
                    continue
                if key not in entries:
                    entries[key] = dict(name='', address=address, sent=0)
                    changed = True
                entry, name = entries[key], name.strip()[:200]
                if name and entry['name'] != name and (not entry['name'] or sent):
                    entry['name'] = name  # Le nom choisi à l’envoi l’emporte sur celui d’un expéditeur.
                    changed = True
                if sent:
                    entry['sent'] += 1
                    changed = True
            if changed:
                self.db.cache_put('contacts', account.id, book, account.id)

    def contacts(self, accounts) -> list[str]:
        """Adresses connues, au format « Nom <adresse> », les plus utilisées d’abord."""
        merged = {}
        for account in accounts:
            for key, entry in ((self.db.cache_get('contacts', account.id) or {}).get('entries') or {}).items():
                current = merged.get(key)
                if current is None or entry['sent'] > current['sent']:
                    merged[key] = dict(entry, sent=entry['sent'] + (current or {}).get('sent', 0))
        def display(entry):
            name = entry['name']
            if not name:
                return entry['address']
            if any(c in name for c in ',;"<>@()[]:'):
                name = '"' + name.replace('"', '').replace('\\', '') + '"'
            return f'{name} <{entry["address"]}>'
        ordered = sorted(merged.values(), key=lambda e: (-e['sent'], (e['name'] or e['address']).casefold()))
        return [display(entry) for entry in ordered]

    def conversation(self, account, rows):
        """Messages d’une conversation, complétés par ceux des autres dossiers en cache (vos réponses dans
        Envoyés notamment), sans doublon, du plus ancien au plus récent."""
        ids = thread_ids(rows)
        own_ids = {row_ids(row)[0] for row in rows if row_ids(row)[0]}
        result, seen = [], set()
        def add(row):
            own = row_ids(row)[0]
            key = own or (row.get('folder'), row.get('uid'))
            if key not in seen:
                seen.add(key)
                result.append(row)
        for row in rows:
            add(row)
        if ids:
            for folder, _ in self.db.cache_get('folders', account.id, []) or []:
                for row in self._known_rows(self.state(account, folder) or {}):
                    own, references = row_ids(row)
                    if (own and own in ids) or own_ids.intersection(references):
                        add(row)
        return chronological(result)

    @staticmethod
    def searchable_text(row, mail) -> str:
        text = mail.text + ' ' + html.unescape(re.sub(r'<[^>]*>', ' ', mail.html))
        return ' '.join([row.get('sender', ''), row.get('subject', ''), text])

    def index_body(self, row, raw: bytes, mail=None) -> None:
        """Indexe un contenu nouvellement mis en cache (sans effet si le cache est chiffré)."""
        try:
            self.db.index_put(self.body_key(row), row['account'], self.searchable_text(row, mail or parse_message(raw)))
        except Exception:
            pass  # L’index est une accélération : la recherche retombe sur le balayage du cache.

    def _search(self, rows, text):
        """Recherche avancée hors ligne (mêmes opérateurs qu’en ligne) sur les lignes en cache.

        Mots du message : index FTS5 pour ceux de trois caractères ou plus, sinon décodage du contenu
        en cache (qui complète l’index au passage). Sans contenu en cache, seuls les en-têtes comptent."""
        query = parse_query(text)
        indexed = self.db.index_enabled() and bool(query.words)
        indexable = indexed and all(len(word) >= 3 for word in query.words)
        known = self.db.index_keys() if indexed else set()
        hits = {word: self.db.index_search(word) for word in query.words} if indexable else {}
        def content(row):
            hashed = self.db.hashed_key(self.body_key(row))
            if indexable and hashed in known:
                # Contenu reconstitué à partir de l’index : seuls les mots présents y figurent.
                return ' '.join(word for word in query.words if hashed in hits[word])
            payload = self.db.cache_get('body', self.body_key(row))
            if not payload:
                return None
            full = self.searchable_text(row, parse_message(base64.b64decode(payload)))
            if indexed and hashed not in known:
                self.db.index_put(self.body_key(row), row['account'], full)  # Index complété au fil des recherches.
            return full
        return [row for row in rows if query_matches(query, row, lambda row=row: content(row))]

    def search_all(self, account, text, cache_only=False, limit=100):
        """Recherche dans tous les dossiers du compte : les plus récents d’abord, au plus « limit » résultats."""
        folders = self.db.cache_get('folders', account.id, []) or []
        rows, total, offline = [], 0, cache_only
        if not cache_only:
            try:
                client = self.client(account)
                folders = client.folders()
                for folder, _ in folders:
                    found, count = client.messages(folder, 0, text)
                    found = self._enrich(found, account, folder)
                    self._carry_previews(found, self.state(account, folder))
                    rows += found
                    total += count
            except CertificateAlert:
                raise
            except Exception:
                rows, total, offline = [], 0, True  # Serveur indisponible : recherche dans le cache.
        if offline:
            for folder, _ in folders:
                found = self._search(self._known_rows(self.state(account, folder) or {}), text)
                rows += found
                total += len(found)
        rows.sort(key=lambda row: timestamp(row), reverse=True)
        return dict(rows=rows[:limit], total=min(total, limit), offline=offline, truncated=total > limit)

    @staticmethod
    def body_key(row):
        return cache_key(row['account'], row['folder'], row.get('uidvalidity', ''), row['uid'])

    def message(self, account, row, cache_only=False):
        cached = self.db.cache_get('body', self.body_key(row))
        if cached:
            return parse_message(base64.b64decode(cached))
        if cache_only:
            raise RuntimeError(tr('Ce message n’a pas encore été téléchargé. Reconnectez-vous pour le lire.'))
        client = self.client(account)
        # message_raw évite une sérialisation susceptible d’altérer le MIME original.
        raw = client.message_raw(row['folder'], row['uid'])
        if row.get('uidvalidity') and client.uidvalidity != row['uidvalidity']:
            raise RuntimeError(tr('Le dossier a changé sur le serveur. Actualisez avant de lire ce message.'))
        self.db.cache_put('body', self.body_key(row), base64.b64encode(raw).decode('ascii'), account.id)
        mail = parse_message(raw)
        self.index_body(dict(row, account=account.id), raw, mail)
        self._remember_preview(account, row, snippet(mail))
        return mail

    def action(self, account, rows, action, target=''):
        """Applique l’action à un message ou à une liste de messages de ce compte.

        Les messages sont regroupés par dossier et UIDVALIDITY : une commande IMAP par groupe."""
        rows = [rows] if isinstance(rows, dict) else list(rows)
        server = f'{account.imap.host}:{account.imap.port}:{account.imap.mode}'
        if not rows:
            return
        if any(row.get('server') != server for row in rows):
            raise RuntimeError(tr('La configuration du serveur a changé. Actualisez avant de modifier ce message.'))
        groups = {}
        for row in rows:
            groups.setdefault((row['folder'], row.get('uidvalidity', '')), []).append(row)
        for (folder, validity), group in groups.items():
            uids = [row['uid'] for row in group]
            self.client(account).action(folder, ','.join(uids), validity, action, target)
            self._apply_cached(account, folder, set(uids), action)
            if action in {'move', 'delete'}:
                for row in group:
                    self.db.cache_delete('body', self.body_key(row))

    def unread(self, account) -> dict:
        """Non-lus par dossier, relevés à la dernière synchronisation."""
        return self.db.cache_get('unread', account.id) or {}

    def restore(self, account, rows, moved_to) -> int:
        """Annule un déplacement : remet ces messages de `moved_to` dans leur dossier d’origine.

        Un message déplacé reçoit un nouvel UID dans sa destination : il y est retrouvé par son Message-ID.
        Renvoie le nombre de messages remis (ceux sans Message-ID ne peuvent pas l’être)."""
        rows = [rows] if isinstance(rows, dict) else list(rows)
        client = self.client(account)
        by_source = {}
        for row in rows:
            if not row.get('message_id'):
                continue
            uids, validity = client.find_by_message_id(moved_to, row['message_id'])
            if uids:
                by_source.setdefault(row['folder'], ([], validity))[0].append(uids)
        restored = 0
        for source, (found, validity) in by_source.items():
            client.action(moved_to, ','.join(found), validity, 'move', source)
            restored += len(found)
        state = self.state(account, moved_to)
        if state and restored:
            self.db.cache_delete('mailbox', cache_key(account.id, moved_to))  # Liste à relire au prochain affichage.
        return restored

    def _apply_cached(self, account, folder, uids, action):
        state = self.state(account, folder)
        if not state:
            return
        for page, rows in state['pages'].items():
            if action in {'move', 'delete'}:
                state['pages'][page] = [item for item in rows if item['uid'] not in uids]
                continue
            for item in rows:
                if uids is None or item['uid'] in uids:
                    if action in {'read', 'unread'}:
                        item['unread'] = action == 'unread'
                    elif action in {'answered', 'forwarded'}:
                        item[action] = True
                    else:
                        item['starred'] = action == 'star'
        if action in {'move', 'delete'}:
            state['total'] = max(0, state.get('total', 0) - len(uids))
        self.db.cache_put('mailbox', cache_key(account.id, folder), state)

    def mark_all_read(self, account, folder):
        count = self.client(account).mark_all_read(folder)
        self._apply_cached(account, folder, None, 'read')
        return count

    def empty_folder(self, account, folder):
        count = self.client(account).empty_folder(folder)
        state = self.state(account, folder) or {}
        for row in self._known_rows(state):
            self.db.cache_delete('body', self.body_key(row))
        if state:
            state.update(pages={'0': []}, total=0)
            self.db.cache_put('mailbox', cache_key(account.id, folder), state)
        return count

    def manage_folder(self, account, operation, name, new_name=''):
        """Crée, renomme ou supprime un dossier puis recharge la liste du serveur."""
        self.client(account).manage_folder(operation, name, new_name)
        if operation in {'rename', 'delete'}:
            state = self.state(account, name) or {}
            for row in self._known_rows(state):
                self.db.cache_delete('body', self.body_key(row))
            self.db.cache_delete('mailbox', cache_key(account.id, name))
        return self.folders(account)[0]

    def unified(self, accounts, page=0, query=''):
        rows = []
        for account in accounts:
            folders = self.db.cache_get('folders', account.id, [])
            inbox = next((name for name, _ in folders if name.upper() == 'INBOX'), 'INBOX')
            rows.extend(self._known_rows(self.state(account, inbox) or {}))
        if query:
            rows = self._search(rows, query)
        def date(row):
            try:
                value = parsedate_to_datetime(row['date'])
                return value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp()
            except (ValueError, TypeError, OverflowError):
                return 0
        rows.sort(key=date, reverse=True)
        return dict(rows=rows[page*50:(page+1)*50], total=len(rows), offline=True)

    def delete_account(self, account):
        """Suppression complète : configuration, cache, certificats approuvés et secrets du coffre Windows."""
        self.db.delete_account(account.id)
        self.pool.clear(account.id)
        self.tls.forget(account.id)
        failures = 0
        for key in (account.id, account.id + ':smtp', account.id + ':oauth', account.id + ':oauth-client-secret'):
            try:
                self.vault.delete(key)
            except Exception:
                failures += 1
        if failures:
            raise RuntimeError(tr('Compte supprimé, mais certains secrets n’ont pas pu être retirés du Gestionnaire d’identifiants Windows (service SmailDesktop).'))

    def sync_account(self, account, cancelled, limit=100):
        folders = self.client(account).folders()
        self.db.cache_put('folders', account.id, folders, account.id)
        try:
            statuses = self.client(account).folder_status([name for name, _ in folders])
        except CertificateAlert:
            raise
        except Exception:
            statuses = {}  # Synchronisation complète de chaque dossier.
        if statuses:
            self.db.cache_put('unread', account.id, {folder: status.get('UNSEEN', 0) for folder, status in statuses.items()}, account.id)
        new_count = 0
        senders = []
        for folder, label in folders:
            if cancelled.is_set() or account.id in self.db.deleted_accounts:
                break
            previous = self.state(account, folder) or {}
            status = statuses.get(folder)
            # Dossier inchangé depuis la dernière synchronisation complète : aucun SELECT ni FETCH.
            # « threaded » : capture faite avec les identifiants de conversation (cache antérieur recapturé une fois).
            if (status and 'HIGHESTMODSEQ' in status and previous.get('status') == status and previous.get('limit') == limit
                    and previous.get('threaded')):
                continue
            reused = set()
            def known(uid, validity):
                payload = self.db.cache_get('body', self.body_key(dict(account=account.id, folder=folder, uidvalidity=validity, uid=uid)))
                if payload:
                    reused.add(uid)
                return base64.b64decode(payload) if payload else None
            rows, total, bodies, validity = self.client(account).snapshot(folder, limit, cancelled, known)
            if cancelled.is_set():
                break
            rows = self._enrich(rows, account, folder)
            if folder.upper() == 'INBOX':
                rows = self.apply_filters(account, folders, rows, validity)
            self._carry_previews(rows, previous)
            parsed = {}
            for row in rows:
                if row.get('preview') is None:
                    parsed[row['uid']] = parse_message(bodies[row['uid']])
                    row['preview'] = snippet(parsed[row['uid']])
            if not any(word in (folder + ' ' + label).casefold() for word in ('spam', 'junk', 'indésirable')):
                senders.extend(row.get('sender', '') for row in rows)
            retained = {self.body_key(row) for row in rows}
            for old_row in self._known_rows(previous):
                if self.body_key(old_row) not in retained:
                    self.db.cache_delete('body', self.body_key(old_row))
            pages = {str(i//50): rows[i:i+50] for i in range(0, len(rows), 50)}
            if not pages:
                pages = {'0': []}
            # STATUS a été lu avant la capture : une modification pendant la capture sera revue au cycle suivant.
            state = dict(account=account.id, folder=folder, pages=pages, total=total, uidvalidity=validity,
                         status=status if status and status.get('UIDVALIDITY') == int(validity or 0) else None, limit=limit, threaded=True)
            for row in rows:
                if row['uid'] not in reused:  # Les contenus déjà en cache ne sont pas réécrits.
                    self.db.cache_put('body', self.body_key(row), base64.b64encode(bodies[row['uid']]).decode('ascii'), account.id)
                    self.index_body(row, bodies[row['uid']], parsed.get(row['uid']))
            self.db.cache_put('mailbox', cache_key(account.id, folder), state)
            if folder.upper() == 'INBOX':
                old = self.db.cache_get('notified', account.id)
                highest = max((int(row['uid']) for row in rows), default=0)
                if old and old['validity'] == validity:
                    new_count = sum(int(row['uid']) > old['uid'] for row in rows)
                self.db.cache_put('notified', account.id, dict(validity=validity, uid=highest), account.id)
        if senders and account.id not in self.db.deleted_accounts:
            self.remember_contacts(account, getaddresses(senders))
        return new_count
