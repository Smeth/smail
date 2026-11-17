"""Coordination du cache, de l’authentification et des opérations réseau."""
import base64
import threading
from datetime import timezone
from email.utils import parsedate_to_datetime
from mailclient.core.imap_client import IMAPClient, ConnectionPool
from mailclient.core.oauth import OAuth
from mailclient.core.parser import parse_message
from mailclient.core.tls_policy import CertificateAlert

def cache_key(*values) -> str:
    import json
    return json.dumps(values, ensure_ascii=False)

class MailService:
    def __init__(self, database, vault, tls):
        self.db, self.vault, self.tls = database, vault, tls
        self.oauth = OAuth(vault)
        self.pool = ConnectionPool()

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
                if not query:
                    old = self.state(account, folder) or {}
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
    def _known_rows(state):
        rows = {row['uid']: row for page in state.get('pages', {}).values() for row in page}
        return sorted(rows.values(), key=lambda row: int(row['uid']), reverse=True)

    def _search(self, rows, query):
        result = []
        query = query.casefold()
        for row in rows:
            content = row.get('sender', '') + ' ' + row.get('subject', '')
            payload = self.db.cache_get('body', self.body_key(row))
            if payload:
                mail = parse_message(base64.b64decode(payload))
                content += ' ' + mail.text + ' ' + mail.html
            if query in content.casefold():
                result.append(row)
        return result

    @staticmethod
    def body_key(row):
        return cache_key(row['account'], row['folder'], row.get('uidvalidity', ''), row['uid'])

    def message(self, account, row, cache_only=False):
        cached = self.db.cache_get('body', self.body_key(row))
        if cached:
            return parse_message(base64.b64decode(cached))
        if cache_only:
            raise RuntimeError('Ce message n’a pas encore été téléchargé. Reconnectez-vous pour le lire.')
        client = self.client(account)
        # message_raw évite une sérialisation susceptible d’altérer le MIME original.
        raw = client.message_raw(row['folder'], row['uid'])
        if row.get('uidvalidity') and client.uidvalidity != row['uidvalidity']:
            raise RuntimeError('Le dossier a changé sur le serveur. Actualisez avant de lire ce message.')
        self.db.cache_put('body', self.body_key(row), base64.b64encode(raw).decode('ascii'), account.id)
        return parse_message(raw)

    def action(self, account, rows, action, target=''):
        """Applique l’action à un message ou à une liste de messages de ce compte.

        Les messages sont regroupés par dossier et UIDVALIDITY : une commande IMAP par groupe."""
        rows = [rows] if isinstance(rows, dict) else list(rows)
        server = f'{account.imap.host}:{account.imap.port}:{account.imap.mode}'
        if not rows:
            return
        if any(row.get('server') != server for row in rows):
            raise RuntimeError('La configuration du serveur a changé. Actualisez avant de modifier ce message.')
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
        for key in (account.id, account.id + ':oauth', account.id + ':oauth-client-secret'):
            try:
                self.vault.delete(key)
            except Exception:
                failures += 1
        if failures:
            raise RuntimeError('Compte supprimé, mais certains secrets n’ont pas pu être retirés du Gestionnaire d’identifiants Windows (service SmailDesktop).')

    def sync_account(self, account, cancelled, limit=100):
        folders = self.client(account).folders()
        self.db.cache_put('folders', account.id, folders, account.id)
        new_count = 0
        for folder, _ in folders:
            if cancelled.is_set() or account.id in self.db.deleted_accounts:
                break
            def known(uid, validity):
                payload = self.db.cache_get('body', self.body_key(dict(account=account.id, folder=folder, uidvalidity=validity, uid=uid)))
                return base64.b64decode(payload) if payload else None
            rows, total, bodies, validity = self.client(account).snapshot(folder, limit, cancelled, known)
            if cancelled.is_set():
                break
            rows = self._enrich(rows, account, folder)
            previous = self.state(account, folder) or {}
            retained = {self.body_key(row) for row in rows}
            for old_row in self._known_rows(previous):
                if self.body_key(old_row) not in retained:
                    self.db.cache_delete('body', self.body_key(old_row))
            pages = {str(i//50): rows[i:i+50] for i in range(0, len(rows), 50)}
            if not pages:
                pages = {'0': []}
            state = dict(account=account.id, folder=folder, pages=pages, total=total, uidvalidity=validity)
            for row in rows:
                self.db.cache_put('body', self.body_key(row), base64.b64encode(bodies[row['uid']]).decode('ascii'), account.id)
            self.db.cache_put('mailbox', cache_key(account.id, folder), state)
            if folder.upper() == 'INBOX':
                old = self.db.cache_get('notified', account.id)
                highest = max((int(row['uid']) for row in rows), default=0)
                if old and old['validity'] == validity:
                    new_count = sum(int(row['uid']) > old['uid'] for row in rows)
                self.db.cache_put('notified', account.id, dict(validity=validity, uid=highest), account.id)
        return new_count
