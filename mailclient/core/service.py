"""Coordination du cache, de l’authentification et des opérations réseau."""
import base64
import threading
from datetime import timezone
from email.utils import parsedate_to_datetime
from mailclient.core.imap_client import IMAPClient
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

    def client(self, account):
        return IMAPClient(account, self.oauth.credential(account), self.tls)

    def folders(self, account, cache_only=False):
        key = account.id
        if not cache_only:
            try:
                folders = self.client(account).folders()
                self.db.cache_put('folders', key, folders)
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
        self.db.cache_put('body', self.body_key(row), base64.b64encode(raw).decode('ascii'))
        return parse_message(raw)

    def action(self, account, row, action, target=''):
        if row.get('server') != f'{account.imap.host}:{account.imap.port}:{account.imap.mode}':
            raise RuntimeError('La configuration du serveur a changé. Actualisez avant de modifier ce message.')
        self.client(account).action(row['folder'], row['uid'], row.get('uidvalidity', ''), action, target)
        state = self.state(account, row['folder'])
        if state:
            for page, rows in state['pages'].items():
                if action == 'move':
                    state['pages'][page] = [item for item in rows if item['uid'] != row['uid']]
                else:
                    for item in rows:
                        if item['uid'] == row['uid']:
                            if action in {'read', 'unread'}:
                                item['unread'] = action == 'unread'
                            else:
                                item['starred'] = action == 'star'
            self.db.cache_put('mailbox', cache_key(account.id, row['folder']), state)
        if action == 'move':
            self.db.cache_delete('body', self.body_key(row))

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

    def sync_account(self, account, cancelled, limit=100):
        folders = self.client(account).folders()
        self.db.cache_put('folders', account.id, folders)
        new_count = 0
        for folder, _ in folders:
            if cancelled.is_set():
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
                self.db.cache_put('body', self.body_key(row), base64.b64encode(bodies[row['uid']]).decode('ascii'))
            self.db.cache_put('mailbox', cache_key(account.id, folder), state)
            if folder.upper() == 'INBOX':
                old = self.db.cache_get('notified', account.id)
                highest = max((int(row['uid']) for row in rows), default=0)
                if old and old['validity'] == validity:
                    new_count = sum(int(row['uid']) > old['uid'] for row in rows)
                self.db.cache_put('notified', account.id, dict(validity=validity, uid=highest))
        return new_count
