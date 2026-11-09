"""Sessions IMAP dédiées : lecture, actions UID et surveillance IDLE."""
import imaplib
import re
import select
import time
from mailclient.core.parser import metadata, decode_folder, parse_message, Mail
from mailclient.core.tls_policy import require_starttls
from mailclient.core.oauth import xoauth2

def quote_folder(folder: str) -> str:
    if any(c in folder for c in '\r\n\x00'):
        raise ValueError('Nom de dossier invalide.')
    return '"' + folder.replace('\\', '\\\\').replace('"', '\\"') + '"'

class IMAPClient:
    def select(self, client, folder, readonly=True, expected=None):
        status, counts = client.select(quote_folder(folder), readonly=readonly)
        if status != 'OK':
            raise RuntimeError('Impossible d’ouvrir ce dossier.')
        self.exists = int(counts[0]) if isinstance(counts, list) and counts and isinstance(counts[0], bytes) and counts[0].isdigit() else 0
        response = client.response('UIDVALIDITY')
        values = response[1] if isinstance(response, tuple) else None
        self.uidvalidity = values[0].decode('ascii') if isinstance(values, list) and values and isinstance(values[0], bytes) else ''
        if expected and self.uidvalidity != expected:
            raise RuntimeError('Le dossier a été recréé sur le serveur. Actualisez avant de modifier les messages.')

    def message(self, folder: str, uid: str) -> Mail:
        """Télécharge le MIME sans positionner le drapeau IMAP Seen."""
        return parse_message(self.message_raw(folder, uid))

    def message_raw(self, folder: str, uid: str) -> bytes:
        if not re.fullmatch(r'[1-9][0-9]*', uid):
            raise ValueError('Identifiant de message invalide.')
        with self.open() as client:
            self.select(client, folder)
            status, parts = client.uid('fetch', uid, '(BODY.PEEK[])')
            if status != 'OK':
                raise RuntimeError('Impossible de charger le message.')
            for part in parts:
                if isinstance(part, tuple) and isinstance(part[1], bytes):
                    return part[1]
            raise RuntimeError('Ce message n’est plus disponible sur le serveur.')

    def __init__(self, account, password, tls):
        self.account, self.password, self.tls = account, password, tls

    def open(self):
        server = self.account.imap
        def factory(context):
            if server.mode == 'SSL/TLS':
                return imaplib.IMAP4_SSL(server.host, server.port, ssl_context=context, timeout=20)
            client = imaplib.IMAP4(server.host, server.port, timeout=20)
            try:
                require_starttls(b'STARTTLS' in client.capabilities)
                client.starttls(ssl_context=context)
                return client
            except BaseException:
                client.shutdown()
                raise
        if server.mode == 'Aucun':
            client = imaplib.IMAP4(server.host, server.port, timeout=20)
        else:
            client = self.tls.connect(self.account.id, f'imap:{server.host}:{server.port}:{server.mode}', factory)
        try:
            if self.account.auth_method == 'password':
                client.login(self.account.email, self.password)
            else:
                client.authenticate('XOAUTH2', lambda challenge: xoauth2(self.account.email, self.password) if not challenge else b'')
            status, capabilities = client.capability()
            if status == 'OK' and capabilities and isinstance(capabilities[0], bytes):
                client.capabilities = tuple(capabilities[0].upper().split())
            return client
        except BaseException:
            client.shutdown()
            raise

    def folders(self):
        with self.open() as client:
            status, data = client.list()
            if status != 'OK':
                raise RuntimeError('Impossible de lister les dossiers.')
            folders = []
            for line in data:
                if not isinstance(line, bytes):
                    continue
                match = re.match(rb'\((.*?)\) (?:"(?:[^"\\]|\\.)*"|NIL) (.*)', line)
                if not match or b'\\noselect' in match[1].lower():
                    continue
                name = match[2].decode('ascii', 'replace')
                if name.startswith('"') and name.endswith('"'):
                    name = re.sub(r'\\(.)', r'\1', name[1:-1])
                labels = {b'\\Sent': 'Envoyés', b'\\Drafts': 'Brouillons', b'\\Trash': 'Corbeille', b'\\Junk': 'Spam'}
                label = 'Boîte de réception' if name.upper() == 'INBOX' else next((v for k,v in labels.items() if k.lower() in match[1].lower()), decode_folder(name))
                folders.append((name, label))
            return folders

    def messages(self, folder: str, page: int, query: str = ''):
        with self.open() as client:
            self.select(client, folder)
            if query:
                client.literal = query.encode('utf-8')
                status, data = client.uid('search', 'CHARSET', 'UTF-8', 'TEXT')
            else:
                status, data = client.uid('search', None, 'UNDELETED')
            if status != 'OK':
                raise RuntimeError('Impossible de rechercher les messages.')
            ids = list(reversed(data[0].split()))
            rows = []
            for uid in ids[page * 50:(page + 1) * 50]:
                status, parts = client.uid('fetch', uid, '(FLAGS BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE CONTENT-TYPE CONTENT-DISPOSITION)])')
                if status != 'OK':
                    continue
                for part in parts:
                    if isinstance(part, tuple):
                        row = metadata(part[1])
                        row.update(uid=uid.decode(), uidvalidity=self.uidvalidity, starred=b'\\Flagged' in part[0], unread=b'\\Seen' not in part[0], attachment=row['attachment'] or bool(re.search(rb'"(?:ATTACHMENT|FILENAME|NAME)"', part[0], re.I)))
                        rows.append(row)
                        break
            return rows, len(ids)

    def action(self, folder: str, uid: str, expected: str, action: str, target=''):
        if not re.fullmatch(r'[1-9][0-9]*', uid) or not expected:
            raise ValueError('Actualisez le dossier avant de modifier ce message.')
        with self.open() as client:
            self.select(client, folder, False, expected)
            if action in {'read', 'unread', 'star', 'unstar'}:
                flag = '\\Seen' if action in {'read', 'unread'} else '\\Flagged'
                operation = '+FLAGS.SILENT' if action in {'read', 'star'} else '-FLAGS.SILENT'
                status, _ = client.uid('store', uid, operation, f'({flag})')
            elif action == 'move':
                if not target or target == folder:
                    raise ValueError('Choisissez un autre dossier de destination.')
                if b'MOVE' in client.capabilities:
                    status, _ = client.uid('MOVE', uid, quote_folder(target))
                else:
                    status, _ = client.uid('COPY', uid, quote_folder(target))
                    if status != 'OK':
                        raise RuntimeError('Copie refusée : le message source est conservé.')
                    status, _ = client.uid('STORE', uid, '+FLAGS.SILENT', '(\\Deleted)')
                    if status != 'OK':
                        raise RuntimeError('La copie a réussi, mais la suppression de la source a échoué. Actualisez les deux dossiers.')
                    if b'UIDPLUS' in client.capabilities:
                        status, _ = client.uid('EXPUNGE', uid)
            else:
                raise ValueError('Action inconnue.')
            if status != 'OK':
                raise RuntimeError('Le serveur a refusé cette action. Actualisez le dossier avant de réessayer.')

    def append(self, folder: str, raw: bytes, draft=False):
        with self.open() as client:
            status, _ = client.append(quote_folder(folder), '(\\Draft)' if draft else '(\\Seen)', None, raw)
            if status != 'OK':
                raise RuntimeError('Le serveur a refusé l’enregistrement de la copie.')

    def snapshot(self, folder: str, limit: int, cancelled, known=None):
        """Capture du dossier et téléchargement borné des derniers messages."""
        with self.open() as client:
            self.select(client, folder)
            status, data = client.uid('search', None, 'UNDELETED')
            if status != 'OK':
                raise RuntimeError('Synchronisation du dossier refusée.')
            ids = list(reversed(data[0].split()))
            rows, bodies = [], {}
            for uid in ids[:limit]:
                if cancelled.is_set():
                    break
                cached = known(uid.decode(), self.uidvalidity) if known else None
                status, parts = client.uid('fetch', uid, '(UID FLAGS)' if cached else '(UID FLAGS BODY.PEEK[])')
                if status != 'OK':
                    continue
                if cached:
                    flags = b' '.join(part for part in parts if isinstance(part, bytes))
                    row = metadata(cached)
                    row.update(uid=uid.decode(), uidvalidity=self.uidvalidity, unread=b'\\Seen' not in flags, starred=b'\\Flagged' in flags)
                    rows.append(row)
                    bodies[uid.decode()] = cached
                    continue
                for part in parts:
                    if isinstance(part, tuple) and isinstance(part[1], bytes):
                        row = metadata(part[1])
                        row.update(uid=uid.decode(), uidvalidity=self.uidvalidity, unread=b'\\Seen' not in part[0], starred=b'\\Flagged' in part[0])
                        rows.append(row)
                        bodies[uid.decode()] = part[1]
                        break
            return rows, len(ids), bodies, self.uidvalidity

    def idle_wait(self, cancelled, seconds=25):
        """IDLE RFC 2177 compatible Python 3.11+, session dédiée."""
        with self.open() as client:
            if b'IDLE' not in client.capabilities:
                return False, False
            self.select(client, 'INBOX')
            # Éviter qu’un read-ahead de makefile masque une réponse à select().
            old_file = client.file
            client.file = client.sock.makefile('rb', buffering=0)
            old_file.close()
            tag = b'SMAILIDLE'
            client.send(tag + b' IDLE\r\n')
            client.sock.settimeout(5)
            while True:
                line = client.readline()
                if line.startswith(b'+'):
                    break
                if line.startswith(tag) or not line or line.startswith(b'* BYE'):
                    raise RuntimeError('Le serveur a refusé IMAP IDLE.')
            deadline, changed = time.monotonic() + seconds, False
            try:
                while time.monotonic() < deadline and not cancelled.is_set():
                    pending = getattr(client.sock, 'pending', lambda: 0)()
                    if pending or select.select([client.sock], [], [], 0.5)[0]:
                        line = client.readline()
                        if not line or line.startswith(b'* BYE'):
                            raise ConnectionError('Connexion IDLE interrompue.')
                        event = re.match(rb'\* (\d+) (EXISTS|EXPUNGE|FETCH)', line)
                        if event and (event[2] != b'EXISTS' or int(event[1]) != self.exists):
                            changed = True
                            break
            finally:
                client.send(b'DONE\r\n')
                while True:
                    line = client.readline()
                    if line.startswith(tag):
                        if b' OK' not in line.upper():
                            raise RuntimeError('Le serveur a interrompu IMAP IDLE.')
                        break
                    if not line:
                        raise ConnectionError('Connexion IDLE interrompue.')
            return True, changed
