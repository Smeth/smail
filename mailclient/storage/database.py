"""Configuration et empreintes publiques uniquement ; aucun mot de passe."""
from mailclient.i18n import tr
import json
import sqlite3
import hashlib
import threading
from cryptography.fernet import Fernet
from mailclient.core.accounts import Account, LOGIN_FIELDS

SCHEMA_VERSION = 2

class Database:
    def __init__(self, path, secrets=None):
        self.path = str(path)
        self.secrets = secrets
        self.lock = threading.RLock()
        self._key = None
        self._encrypted = None
        # Comptes supprimés pendant cette session : aucune tâche en vol ne doit recréer leur cache.
        self.deleted_accounts: set[str] = set()
        with self.lock:
            self._migrate()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.execute('PRAGMA secure_delete=ON')
        return db

    def _migrate(self) -> None:
        """Migrations numérotées via PRAGMA user_version ; chaque étape est transactionnelle."""
        db = self.connect()
        try:
            db.executescript('CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, config TEXT NOT NULL); CREATE TABLE IF NOT EXISTS pins (account TEXT, endpoint TEXT, fingerprint TEXT, PRIMARY KEY(account,endpoint));'
                             'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS cache (kind TEXT, key TEXT, data BLOB NOT NULL, PRIMARY KEY(kind,key));')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(tr('Cette base a été créée par une version plus récente de Smail.'))
            # Le rattachement des entrées de cache à leur compte vit dans une table séparée : la table cache
            # garde ses trois colonnes et Smail 1.0.0 reste capable d’écrire dans une base migrée.
            if version < 2:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS cache_owner (kind TEXT, key TEXT, account TEXT NOT NULL, PRIMARY KEY(kind,key))')
                    db.execute('CREATE INDEX IF NOT EXISTS cache_owner_account ON cache_owner(account)')
                    # Préversion : colonne account ajoutée à cache ; on la déplace dans cache_owner.
                    if 'account' in {row[1] for row in db.execute('PRAGMA table_info(cache)')}:
                        db.execute('INSERT OR REPLACE INTO cache_owner SELECT kind,key,account FROM cache WHERE account IS NOT NULL')
                        db.execute('DROP INDEX IF EXISTS cache_account')
                        db.execute('ALTER TABLE cache DROP COLUMN account')
                    db.execute('PRAGMA user_version = 2')
            with db:
                self._claim_orphans(db)
        finally:
            db.close()

    def _claim_orphans(self, db) -> None:
        """Rattache à leur compte les entrées sans propriétaire (cache antérieur ou écrit par Smail 1.0.0)."""
        orphans = 'NOT EXISTS (SELECT 1 FROM cache_owner o WHERE o.kind=c.kind AND o.key=c.key)'
        if not db.execute(f'SELECT 1 FROM cache c WHERE {orphans} LIMIT 1').fetchone():
            return
        def claim(kind, key, account_id):
            db.execute('INSERT OR IGNORE INTO cache_owner VALUES (?,?,?)', (kind, key, account_id))
        for (account_id,) in list(db.execute('SELECT id FROM accounts')):
            hashed = self._cache_key(account_id)
            for kind in ('folders', 'notified'):
                if db.execute('SELECT 1 FROM cache WHERE kind=? AND key=?', (kind, hashed)).fetchone():
                    claim(kind, hashed, account_id)
        rows = list(db.execute(f"SELECT kind,key,data FROM cache c WHERE kind IN ('mailbox','draft','sent-copy') AND {orphans}"))
        rows += list(db.execute("SELECT c.kind,c.key,c.data FROM cache c JOIN cache_owner o ON o.kind=c.kind AND o.key=c.key WHERE c.kind='mailbox'"))
        for kind, key, data in rows:
            try:
                value = self._decode(bytes(data))
            except Exception:
                continue  # Clé de chiffrement indisponible : l’entrée reste orpheline mais lisible plus tard.
            account_id = value.get('account') if isinstance(value, dict) else None
            if not account_id:
                continue
            claim(kind, key, account_id)
            if kind == 'mailbox':
                for page in value.get('pages', {}).values():
                    for row in page:
                        body = json.dumps([account_id, row.get('folder', value.get('folder')), row.get('uidvalidity', ''), row.get('uid')], ensure_ascii=False)
                        hashed = self._cache_key(body)
                        if db.execute("SELECT 1 FROM cache WHERE kind='body' AND key=?", (hashed,)).fetchone():
                            claim('body', hashed, account_id)

    def setting(self, key: str, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value) -> None:
        with self.lock, self.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))

    def _fernet(self):
        if self.secrets is None:
            raise RuntimeError(tr('Le coffre Windows est nécessaire pour chiffrer le cache.'))
        if self._key is None:
            try:
                self._key = self.secrets.get('cache-encryption-key')
            except RuntimeError:
                # Ne jamais remplacer une clé perdue d’un cache déjà chiffré.
                if self.setting('cache_encrypted', False):
                    raise RuntimeError(tr('Clé de chiffrement absente. Restaurez le coffre Windows avant de lire le cache.'))
                self._key = Fernet.generate_key().decode('ascii')
                self.secrets.set('cache-encryption-key', self._key)
        return Fernet(self._key.encode('ascii'))

    def _decode(self, payload: bytes):
        if payload[:1] == b'E':
            payload = self._fernet().decrypt(payload[1:])
        else:
            payload = payload[1:]
        return json.loads(payload.decode('utf-8'))

    @staticmethod
    def _cache_key(key: str) -> str:
        return hashlib.sha256(key.encode('utf-8')).hexdigest()

    def _cache_encrypted(self) -> bool:
        if self._encrypted is None:
            self._encrypted = bool(self.setting('cache_encrypted', False))
        return self._encrypted

    def cache_put(self, kind: str, key: str, value, account: str | None = None) -> None:
        """account rattache l’entrée à un compte pour permettre sa purge ; déduit du champ account si absent."""
        if account is None and isinstance(value, dict):
            account = value.get('account')
        with self.lock:
            if account in self.deleted_accounts:
                return
            payload = json.dumps(value, ensure_ascii=False).encode('utf-8')
            payload = b'E' + self._fernet().encrypt(payload) if self._cache_encrypted() else b'P' + payload
            hashed = self._cache_key(key)
            with self.connect() as db:
                db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)', (kind, hashed, payload))
                if account:
                    db.execute('INSERT OR REPLACE INTO cache_owner VALUES (?,?,?)', (kind, hashed, account))

    def cache_get(self, kind: str, key: str, default=None):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT data FROM cache WHERE kind=? AND key=?', (kind, self._cache_key(key))).fetchone()
            return self._decode(bytes(row[0])) if row else default

    def cache_list(self, kind: str):
        with self.lock, self.connect() as db:
            return [self._decode(bytes(row[0])) for row in db.execute('SELECT data FROM cache WHERE kind=?', (kind,))]

    def cache_delete(self, kind: str, key: str) -> None:
        with self.lock, self.connect() as db:
            db.execute('DELETE FROM cache WHERE kind=? AND key=?', (kind, self._cache_key(key)))
            db.execute('DELETE FROM cache_owner WHERE kind=? AND key=?', (kind, self._cache_key(key)))
            if kind == 'body' and self._index_exists(db):
                db.execute('DELETE FROM search_index WHERE key=?', (self._cache_key(key),))

    # Index plein texte des messages en cache. Il contient le texte en clair : il n’existe que si le
    # chiffrement du cache est désactivé (le cache est alors lui-même en clair) et disparaît à son activation.
    @staticmethod
    def _index_exists(db) -> bool:
        return db.execute("SELECT 1 FROM sqlite_master WHERE name='search_index'").fetchone() is not None

    def index_enabled(self) -> bool:
        if self._cache_encrypted():
            return False
        with self.lock, self.connect() as db:
            if self._index_exists(db):
                return True
            try:
                db.execute("CREATE VIRTUAL TABLE search_index USING fts5(key UNINDEXED, account UNINDEXED, content, tokenize='trigram')")
                return True
            except sqlite3.OperationalError:
                return False  # SQLite sans FTS5 ou sans trigram : la recherche reste un balayage.

    def index_put(self, key: str, account: str, content: str) -> None:
        with self.lock:
            if account in self.deleted_accounts or not self.index_enabled():
                return
            hashed = self._cache_key(key)
            with self.connect() as db:
                db.execute('DELETE FROM search_index WHERE key=?', (hashed,))
                db.execute('INSERT INTO search_index (key, account, content) VALUES (?,?,?)', (hashed, account, content))

    def index_keys(self) -> set[str]:
        """Clés hachées déjà indexées."""
        with self.lock, self.connect() as db:
            return {row[0] for row in db.execute('SELECT key FROM search_index')} if self._index_exists(db) else set()

    def index_search(self, query: str) -> set[str]:
        """Clés hachées des contenus contenant la sous-chaîne (3 caractères au moins, casse ignorée)."""
        with self.lock, self.connect() as db:
            if not self._index_exists(db):
                return set()
            phrase = '"' + query.replace('"', '""') + '"'
            return {row[0] for row in db.execute('SELECT key FROM search_index WHERE search_index MATCH ?', (phrase,))}

    @staticmethod
    def hashed_key(key: str) -> str:
        return Database._cache_key(key)

    def encrypt_cache(self, enabled: bool) -> None:
        """Migration transactionnelle des contenus ; purge des anciennes pages SQLite."""
        with self.lock:
            cipher = self._fernet() if enabled else None
            with self.connect() as db:
                rows = list(db.execute('SELECT kind,key,data FROM cache'))
                for kind, key, data in rows:
                    raw = json.dumps(self._decode(bytes(data)), ensure_ascii=False).encode('utf-8')
                    payload = b'E' + cipher.encrypt(raw) if enabled else b'P' + raw
                    db.execute('UPDATE cache SET data=? WHERE kind=? AND key=?', (payload, kind, key))
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('cache_encrypted', json.dumps(enabled)))
                if enabled:
                    db.execute('DROP TABLE IF EXISTS search_index')  # Le texte en clair ne survit pas au chiffrement.
            self._encrypted = enabled
            self.vacuum()

    def vacuum(self) -> None:
        with self.lock:
            db = self.connect()
            try:
                db.execute('VACUUM')
            finally:
                db.close()

    def accounts(self) -> list[Account]:
        with self.connect() as db:
            rows = list(db.execute('SELECT config FROM accounts ORDER BY rowid'))
        result = []
        for (config,) in rows:
            data = json.loads(config)
            data.update(self.setting(f'logins:{data["id"]}', {}) or {})
            result.append(Account.from_dict(data))
        return result

    def save(self, account: Account) -> None:
        """Configuration publique du compte ; les identifiants de connexion à part, dans les réglages,
        pour que la configuration reste lisible par Smail 1.0.0 (qui refuse les champs inconnus)."""
        account.validate()
        config = account.to_dict()
        logins = {name: config.pop(name) for name in LOGIN_FIELDS if name in config}
        with self.lock, self.connect() as db:
            db.execute('INSERT OR REPLACE INTO accounts VALUES (?,?)', (account.id, json.dumps(config)))
            if any(logins.values()):
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (f'logins:{account.id}', json.dumps(logins)))
            else:
                db.execute('DELETE FROM settings WHERE key=?', (f'logins:{account.id}',))

    def pin(self, account: str, endpoint: str) -> str | None:
        with self.connect() as db:
            row = db.execute('SELECT fingerprint FROM pins WHERE account=? AND endpoint=?', (account, endpoint)).fetchone()
            return row[0] if row else None

    def trust(self, account: str, endpoint: str, fingerprint: str) -> None:
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO pins VALUES (?,?,?)', (account, endpoint, fingerprint))

    def pins(self) -> list[tuple[str, str, str]]:
        """Exceptions de certificat permanentes : (compte, point d’accès, empreinte)."""
        with self.connect() as db:
            return list(db.execute('SELECT account,endpoint,fingerprint FROM pins ORDER BY account,endpoint'))

    def untrust(self, account: str, endpoint: str) -> None:
        with self.lock, self.connect() as db:
            db.execute('DELETE FROM pins WHERE account=? AND endpoint=?', (account, endpoint))

    def delete_account(self, account_id: str) -> None:
        """Retire la configuration, les exceptions de certificat et tout le cache du compte, en une transaction."""
        with self.lock:
            self.deleted_accounts.add(account_id)
            with self.connect() as db:
                self._claim_orphans(db)  # Entrées écrites entre-temps par une ancienne version.
                db.execute('DELETE FROM accounts WHERE id=?', (account_id,))
                db.execute('DELETE FROM pins WHERE account=?', (account_id,))
                db.execute('DELETE FROM settings WHERE key=?', (f'logins:{account_id}',))
                db.execute('DELETE FROM cache WHERE EXISTS (SELECT 1 FROM cache_owner o WHERE o.kind=cache.kind AND o.key=cache.key AND o.account=?)', (account_id,))
                db.execute('DELETE FROM cache_owner WHERE account=?', (account_id,))
                if self._index_exists(db):
                    db.execute('DELETE FROM search_index WHERE account=?', (account_id,))
            self.vacuum()  # secure_delete efface les pages ; VACUUM réduit aussi le fichier.
