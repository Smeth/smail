"""Sessions IMAP dédiées : lecture, actions UID et surveillance IDLE."""
import base64
import hashlib
import imaplib
import re
import select
import threading
import time
from contextlib import contextmanager
from mailclient.core.parser import metadata, decode_folder, parse_message, Mail
from mailclient.core.tls_policy import require_starttls
from mailclient.core.oauth import xoauth2

UID_SET = re.compile(r'[1-9][0-9]*(?:,[1-9][0-9]*)*')

def quote_folder(folder: str) -> str:
    if any(c in folder for c in '\r\n\x00'):
        raise ValueError('Nom de dossier invalide.')
    return '"' + folder.replace('\\', '\\\\').replace('"', '\\"') + '"'

def encode_folder(value: str) -> str:
    """UTF-7 modifié de la RFC 3501, inverse de decode_folder."""
    result, pending = [], ''
    def flush():
        if pending:
            data = base64.b64encode(pending.encode('utf-16-be')).decode('ascii').rstrip('=').replace('/', ',')
            result.append('&' + data + '-')
    for char in value:
        if 0x20 <= ord(char) <= 0x7e:
            flush()
            pending = ''
            result.append('&-' if char == '&' else char)
        else:
            pending += char
    flush()
    return ''.join(result)

def valid_folder_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 200 or any(ord(c) < 32 or c in '*%' for c in name):
        raise ValueError('Nom de dossier invalide : évitez les caractères * et %.')
    return name

# Dossiers usuels sans attribut SPECIAL-USE (Courier, cPanel, anciens Dovecot) : libellé français.
COMMON_LABELS = {'sent': 'Envoyés', 'sent items': 'Envoyés', 'sent messages': 'Envoyés', 'drafts': 'Brouillons',
                 'trash': 'Corbeille', 'deleted items': 'Corbeille', 'deleted messages': 'Corbeille',
                 'junk': 'Spam', 'spam': 'Spam', 'junk e-mail': 'Spam', 'archive': 'Archives', 'archives': 'Archives'}
QUOTED = rb'"((?:[^"\\]|\\.)*)"'

def unquote(value: bytes) -> str:
    return re.sub(r'\\(.)', r'\1', value.decode('ascii', 'replace'))

def personal_namespace(client):
    """(préfixe, séparateur) de l’espace personnel (RFC 2342), ex. ('INBOX.', '.') ; ('', None) si inconnu."""
    if b'NAMESPACE' not in getattr(client, 'capabilities', ()):
        return '', None
    try:
        status, data = client.namespace()
    except (imaplib.IMAP4.error, AttributeError):
        return '', None
    line = data[0] if status == 'OK' and data and isinstance(data[0], bytes) else b''
    match = re.match(rb'\(\(' + QUOTED + rb' (?:' + QUOTED + rb'|NIL)', line)
    if not match:
        return '', None
    return unquote(match[1]), unquote(match[2]) if match[2] is not None else None

def folder_prefix(names, delimiter, namespace=''):
    """Préfixe commun imposé par le serveur (« INBOX. ») : annoncé par NAMESPACE ou déduit de la liste."""
    if namespace:
        return namespace
    if not delimiter:
        return ''
    prefix = 'INBOX' + delimiter
    others = [name for name in names if name.upper() != 'INBOX']
    return prefix if others and all(name.upper().startswith(prefix.upper()) for name in others) else ''

def folder_label(name, delimiter, prefix='', translate=True):
    """Libellé lisible : préfixe serveur retiré, hiérarchie en « Parent › Enfant », noms usuels traduits."""
    if prefix and name.upper().startswith(prefix.upper()) and len(name) > len(prefix):
        name = name[len(prefix):]
    parts = [decode_folder(part) for part in (name.split(delimiter) if delimiter else [name]) if part]
    if len(parts) == 1 and translate:
        return COMMON_LABELS.get(parts[0].casefold(), parts[0])
    return ' › '.join(parts) or decode_folder(name)

FETCH_START = re.compile(rb'\d+ \(')

def fetch_items(parts) -> dict:
    """Regroupe une réponse FETCH multi-messages d’imaplib : {uid: (attributs, littéral ou None)}.

    imaplib renvoie un tuple (préfixe, littéral) par message, suivi d’octets contenant la fin des
    attributs (FLAGS peut être placé après le littéral). Les réponses sans UID (notifications
    non sollicitées) sont ignorées."""
    entries = []
    for part in parts or []:
        if isinstance(part, tuple) and len(part) == 2:
            entries.append([part[0], part[1]])
        elif isinstance(part, bytes):
            if FETCH_START.match(part) or not entries:
                entries.append([part, None])
            else:
                entries[-1][0] += part
    result = {}
    for attributes, literal in entries:
        match = re.search(rb'UID (\d+)', attributes)
        if match:
            result[match[1].decode()] = (attributes, literal)
    return result

class ConnectionPool:
    """Sessions IMAP authentifiées réutilisables, vérifiées par NOOP et fermées après inactivité."""
    def __init__(self, ttl=240, per_key=2):
        self.ttl, self.per_key = ttl, per_key
        self.lock = threading.Lock()
        self.idle: dict[tuple, list] = {}

    def acquire(self, key):
        while True:
            with self.lock:
                stack = self.idle.get(key) or []
                if not stack:
                    return None
                client, last = stack.pop()
            if time.monotonic() - last > self.ttl:
                self._close(client)
                continue
            try:
                if client.noop()[0] == 'OK':
                    return client
            except Exception:
                pass
            self._close(client)

    def release(self, key, client):
        with self.lock:
            stack = self.idle.setdefault(key, [])
            if len(stack) < self.per_key:
                stack.append((client, time.monotonic()))
                return
        self._close(client)

    def clear(self, account_id=None):
        with self.lock:
            keys = [key for key in self.idle if account_id is None or key[0] == account_id]
            clients = [client for key in keys for client, _ in self.idle.pop(key)]
        for client in clients:
            self._close(client)

    @staticmethod
    def _close(client):
        try:
            client.shutdown()
        except Exception:
            pass

def uid_set(uids) -> str:
    value = ','.join(str(uid) for uid in ([uids] if isinstance(uids, str) else uids))
    if not UID_SET.fullmatch(value):
        raise ValueError('Actualisez le dossier avant de modifier ce message.')
    return value

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
        with self.session() as client:
            self.select(client, folder)
            status, parts = client.uid('fetch', uid, '(BODY.PEEK[])')
            if status != 'OK':
                raise RuntimeError('Impossible de charger le message.')
            for part in parts:
                if isinstance(part, tuple) and isinstance(part[1], bytes):
                    return part[1]
            raise RuntimeError('Ce message n’est plus disponible sur le serveur.')

    def __init__(self, account, password, tls, pool=None):
        self.account, self.password, self.tls, self.pool = account, password, tls, pool

    def _pool_key(self):
        # La configuration et l’empreinte du secret : un changement de paramètres n’emprunte jamais une ancienne session.
        server = self.account.imap
        secret = hashlib.sha256((self.password or '').encode('utf-8')).hexdigest()
        return (self.account.id, server.host, server.port, server.mode, self.account.email, self.account.imap_user, self.account.auth_method, secret)

    @contextmanager
    def session(self):
        """Session authentifiée : empruntée à la réserve si possible, rendue après succès, fermée après erreur."""
        if self.pool is None:
            with self.open() as client:
                yield client
            return
        key = self._pool_key()
        client = self.pool.acquire(key) or self.open()
        try:
            yield client
        except BaseException:
            ConnectionPool._close(client)
            raise
        self.pool.release(key, client)

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
                client.login(self.account.imap_user, self.password)
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
        with self.session() as client:
            status, data = client.list()
            if status != 'OK':
                raise RuntimeError('Impossible de lister les dossiers.')
            entries, delimiter = [], None
            for line in data:
                if not isinstance(line, bytes):
                    continue
                match = re.match(rb'\((.*?)\) (?:' + QUOTED + rb'|NIL) (.*)', line)
                if not match or b'\\noselect' in match[1].lower():
                    continue
                name = match[3].decode('ascii', 'replace')
                if name.startswith('"') and name.endswith('"'):
                    name = re.sub(r'\\(.)', r'\1', name[1:-1])
                if match[2] is not None:
                    delimiter = delimiter or unquote(match[2])
                entries.append((name, match[1].lower()))
            namespace, separator = personal_namespace(client)
            delimiter = delimiter or separator
            prefix = folder_prefix([name for name, _ in entries], delimiter, namespace)
            labels = {b'\\sent': 'Envoyés', b'\\drafts': 'Brouillons', b'\\trash': 'Corbeille', b'\\junk': 'Spam', b'\\archive': 'Archives'}
            folders, special = [], set()
            for name, flags in entries:
                label = 'Boîte de réception' if name.upper() == 'INBOX' else \
                        next((v for k, v in labels.items() if k in flags), None)
                special.add(name) if label else None
                folders.append((name, label or folder_label(name, delimiter, prefix)))
            # Deux dossiers traduits pareil (« Junk » et « spam » -> « Spam ») : leurs vrais noms restent
            # affichés, sauf pour celui que le serveur désigne lui-même (SPECIAL-USE).
            counts = {}
            for _, label in folders:
                counts[label] = counts.get(label, 0) + 1
            return [(name, folder_label(name, delimiter, prefix, translate=False)
                     if counts[label] > 1 and name not in special and name.upper() != 'INBOX' else label)
                    for name, label in folders]

    def hierarchy(self, client):
        """(préfixe imposé, séparateur) pour créer et renommer les dossiers au bon endroit."""
        namespace, delimiter = personal_namespace(client)
        names = []
        try:
            status, data = client.list()
        except (imaplib.IMAP4.error, AttributeError):
            status, data = 'NO', []
        for line in (data or []) if status == 'OK' else []:
            match = re.match(rb'\((.*?)\) (?:' + QUOTED + rb'|NIL) (.*)', line) if isinstance(line, bytes) else None
            if match:
                if match[2] is not None and not delimiter:
                    delimiter = unquote(match[2])
                name = match[3].decode('ascii', 'replace')
                names.append(re.sub(r'\\(.)', r'\1', name[1:-1]) if name.startswith('"') and name.endswith('"') else name)
        return folder_prefix(names, delimiter, namespace), delimiter

    def folder_status(self, folders) -> dict:
        """STATUS de chaque dossier : {dossier: {MESSAGES, UIDNEXT, UIDVALIDITY[, HIGHESTMODSEQ]}}.

        Session neuve, jamais sélectionnée : la RFC 3501 déconseille STATUS sur le dossier sélectionné.
        HIGHESTMODSEQ (CONDSTORE, RFC 7162) change à chaque modification de drapeau : sans lui, un dossier
        ne peut pas être déclaré inchangé."""
        result = {}
        with self.open() as client:
            condstore = b'CONDSTORE' in client.capabilities
            items = '(MESSAGES UIDNEXT UIDVALIDITY HIGHESTMODSEQ)' if condstore else '(MESSAGES UIDNEXT UIDVALIDITY)'
            for folder in folders:
                try:
                    status, data = client.status(quote_folder(folder), items)
                except imaplib.IMAP4.error:
                    continue
                if status != 'OK' or not data or not isinstance(data[-1], bytes):
                    continue
                values = {key.decode(): int(value) for key, value in re.findall(rb'(MESSAGES|UIDNEXT|UIDVALIDITY|HIGHESTMODSEQ) (\d+)', data[-1])}
                if {'MESSAGES', 'UIDNEXT', 'UIDVALIDITY'} <= set(values):
                    result[folder] = values
        return result

    def search_uids(self, client, query: str = '') -> list[str]:
        """UID du dossier sélectionné correspondant à la recherche avancée, du plus récent au plus ancien.

        Une commande SEARCH par texte non ASCII (un seul littéral par commande dans imaplib), résultats
        croisés ; « a:pj » est vérifié sur BODYSTRUCTURE, que SEARCH ne sait pas interroger."""
        from mailclient.core.search_query import imap_commands, parse
        parsed = parse(query)
        found = None
        for args, literal in imap_commands(parsed):
            if literal is not None:
                client.literal = literal
                status, data = client.uid('search', 'CHARSET', 'UTF-8', *args)
            else:
                status, data = client.uid('search', None, *args)
            if status != 'OK':
                raise RuntimeError('Le serveur a refusé cette recherche.')
            uids = set(data[0].split()) if data and data[0] else set()
            found = uids if found is None else found & uids
            if not found:
                return []
        ordered = sorted(found, key=int, reverse=True)
        if parsed.attachment:
            kept = []
            for start in range(0, min(len(ordered), 5000), 500):  # Au plus 5 000 messages examinés.
                chunk = ordered[start:start + 500]
                status, parts = client.uid('fetch', b','.join(chunk).decode(), '(UID BODYSTRUCTURE)')
                if status != 'OK':
                    raise RuntimeError('Le serveur a refusé cette recherche.')
                items = fetch_items(parts)
                kept += [uid for uid in chunk if uid.decode() in items and
                         re.search(rb'"(?:ATTACHMENT|FILENAME|NAME)"', items[uid.decode()][0], re.I)]
            ordered = kept
        return [uid.decode() for uid in ordered]

    def messages(self, folder: str, page: int, query: str = ''):
        with self.session() as client:
            self.select(client, folder)
            ids = [uid.encode() for uid in self.search_uids(client, query)]
            wanted = [uid.decode() for uid in ids[page * 50:(page + 1) * 50]]
            if not wanted:
                return [], len(ids)
            # Une seule commande FETCH pour toute la page.
            status, parts = client.uid('fetch', ','.join(wanted), '(UID FLAGS BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE CONTENT-TYPE CONTENT-DISPOSITION MESSAGE-ID IN-REPLY-TO REFERENCES)])')
            if status != 'OK':
                raise RuntimeError('Impossible de charger la liste des messages.')
            items = fetch_items(parts)
            rows = []
            for uid in wanted:
                if uid not in items or items[uid][1] is None:
                    continue  # Message supprimé entre SEARCH et FETCH.
                attributes, header = items[uid]
                row = metadata(header)
                row.update(uid=uid, uidvalidity=self.uidvalidity, starred=b'\\Flagged' in attributes, unread=b'\\Seen' not in attributes,
                           attachment=row['attachment'] or bool(re.search(rb'"(?:ATTACHMENT|FILENAME|NAME)"', attributes, re.I)))
                rows.append(row)
            return rows, len(ids)

    def action(self, folder: str, uid, expected: str, action: str, target=''):
        """uid accepte un UID ou une liste d’UID du même dossier : une seule commande IMAP."""
        uid = uid_set(uid)
        if not expected:
            raise ValueError('Actualisez le dossier avant de modifier ce message.')
        with self.session() as client:
            self.select(client, folder, False, expected)
            if action == 'delete':
                status, _ = client.uid('STORE', uid, '+FLAGS.SILENT', '(\\Deleted)')
                if status == 'OK':
                    status = self._expunge(client, uid)
            elif action in {'read', 'unread', 'star', 'unstar'}:
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

    @staticmethod
    def _expunge(client, uid, allow_global=False):
        """Purge ciblée avec UIDPLUS. Sans UIDPLUS, EXPUNGE global seulement quand tout le dossier est vidé ;
        sinon le message reste marqué Deleted (masqué) jusqu’à la purge du serveur."""
        if b'UIDPLUS' in client.capabilities:
            return client.uid('EXPUNGE', uid)[0]
        return client.expunge()[0] if allow_global else 'OK'

    def mark_all_read(self, folder: str):
        with self.session() as client:
            self.select(client, folder, False)
            status, data = client.uid('search', None, 'UNSEEN')
            if status != 'OK':
                raise RuntimeError('Impossible de rechercher les messages non lus.')
            uids = data[0].split() if data and data[0] else []
            for start in range(0, len(uids), 500):
                status, _ = client.uid('STORE', b','.join(uids[start:start+500]).decode('ascii'), '+FLAGS.SILENT', '(\\Seen)')
                if status != 'OK':
                    raise RuntimeError('Le serveur a refusé de marquer les messages comme lus.')
            return len(uids)

    def empty_folder(self, folder: str):
        """Suppression définitive de tous les messages du dossier (corbeille, spam)."""
        with self.session() as client:
            self.select(client, folder, False)
            status, data = client.uid('search', None, 'ALL')
            if status != 'OK':
                raise RuntimeError('Impossible de lister les messages du dossier.')
            uids = data[0].split() if data and data[0] else []
            for start in range(0, len(uids), 500):
                chunk = b','.join(uids[start:start+500]).decode('ascii')
                status, _ = client.uid('STORE', chunk, '+FLAGS.SILENT', '(\\Deleted)')
                if status != 'OK' or self._expunge(client, chunk, allow_global=True) != 'OK':
                    raise RuntimeError('Le serveur a refusé la suppression définitive. Actualisez le dossier.')
            return len(uids)

    def manage_folder(self, operation: str, name: str, new_name: str = ''):
        """create / rename / delete ; les noms affichés sont encodés en UTF-7 modifié.

        Sur un serveur qui impose un préfixe (« INBOX. »), un nouveau dossier est créé sous ce préfixe ;
        un dossier renommé garde son parent (new_name est le nouveau nom, pas un chemin complet)."""
        with self.session() as client:
            if operation in {'create', 'rename'}:
                prefix, delimiter = self.hierarchy(client)
            if operation == 'create':
                target = encode_folder(valid_folder_name(name))
                if prefix and not target.upper().startswith(prefix.upper()):
                    target = prefix + target
                status, _ = client.create(quote_folder(target))
            elif operation == 'rename':
                parent = name[:name.rfind(delimiter) + len(delimiter)] if delimiter and delimiter in name else prefix
                status, _ = client.rename(quote_folder(name), quote_folder(parent + encode_folder(valid_folder_name(new_name))))
            elif operation == 'delete':
                status, _ = client.delete(quote_folder(name))
            else:
                raise ValueError('Opération de dossier inconnue.')
            if status != 'OK':
                raise RuntimeError('Le serveur a refusé cette opération sur le dossier (nom déjà utilisé ou dossier protégé ?).')

    def find_by_message_id(self, folder: str, message_id: str):
        """UID des messages portant ce Message-ID dans le dossier, et UIDVALIDITY ; un UID change à chaque déplacement."""
        if not re.fullmatch(r'<[^<>\s"\\]{1,250}>', message_id):
            raise ValueError('Identifiant de message invalide.')
        with self.session() as client:
            self.select(client, folder)
            status, data = client.uid('search', None, 'HEADER', 'Message-ID', f'"{message_id}"')
            if status != 'OK':
                raise RuntimeError('Recherche du message refusée par le serveur.')
            return ','.join(uid.decode() for uid in (data[0].split() if data and data[0] else [])), self.uidvalidity

    APPEND_TIMEOUT = 300

    def append(self, folder: str, raw: bytes, draft=False):
        """Copie d’un message (Envoyés, Brouillons). Depuis Python 3.5, le délai d’un socket borne l’envoi COMPLET
        d’un bloc : 20 s ne suffisent pas pour téléverser un message de plusieurs Mo ; le délai est donc allongé
        le temps de la copie."""
        with self.session() as client:
            sock = getattr(client, 'sock', None)
            previous = sock.gettimeout() if sock is not None else None
            if sock is not None:
                sock.settimeout(self.APPEND_TIMEOUT)
            try:
                status, _ = client.append(quote_folder(folder), '(\\Draft)' if draft else '(\\Seen)', None, raw)
            finally:
                if sock is not None:
                    try:
                        sock.settimeout(previous)
                    except OSError:
                        pass  # Session coupée : elle sera fermée et non réutilisée.
            if status != 'OK':
                raise RuntimeError('Le serveur a refusé l’enregistrement de la copie.')

    def snapshot(self, folder: str, limit: int, cancelled, known=None):
        """Capture du dossier et téléchargement borné des derniers messages."""
        with self.session() as client:
            self.select(client, folder)
            status, data = client.uid('search', None, 'UNDELETED')
            if status != 'OK':
                raise RuntimeError('Synchronisation du dossier refusée.')
            ids = [uid.decode() for uid in reversed(data[0].split())]
            wanted = ids[:limit]
            cached = {uid: known(uid, self.uidvalidity) for uid in wanted} if known else {}
            cached = {uid: raw for uid, raw in cached.items() if raw}
            missing = [uid for uid in wanted if uid not in cached]
            fetched = {}
            # Drapeaux des messages déjà en cache : lots de 500 ; contenus complets : lots de 25 (mémoire bornée, annulation rapide).
            for size, uids, items in ((500, list(cached), '(UID FLAGS)'), (25, missing, '(UID FLAGS BODY.PEEK[])')):
                for start in range(0, len(uids), size):
                    if cancelled.is_set():
                        break
                    status, parts = client.uid('fetch', ','.join(uids[start:start+size]), items)
                    if status == 'OK':
                        fetched.update(fetch_items(parts))
            rows, bodies = [], {}
            for uid in wanted:
                if uid not in fetched:
                    continue
                attributes, literal = fetched[uid]
                raw = cached.get(uid) or literal
                if not isinstance(raw, bytes):
                    continue
                row = metadata(raw)
                row.update(uid=uid, uidvalidity=self.uidvalidity, unread=b'\\Seen' not in attributes, starred=b'\\Flagged' in attributes)
                rows.append(row)
                bodies[uid] = raw
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
