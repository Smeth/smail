"""Configuration et empreintes publiques uniquement ; aucun mot de passe."""
import json
import sqlite3
import hashlib
import threading
from cryptography.fernet import Fernet
from mailclient.core.accounts import Account

class Database:
    def __init__(self, path, secrets=None):
        self.path = str(path)
        self.secrets = secrets
        self.lock = threading.RLock()
        self._key = None
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, config TEXT NOT NULL); CREATE TABLE IF NOT EXISTS pins (account TEXT, endpoint TEXT, fingerprint TEXT, PRIMARY KEY(account,endpoint));')
            db.executescript('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS cache (kind TEXT, key TEXT, data BLOB NOT NULL, PRIMARY KEY(kind,key));')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.execute('PRAGMA secure_delete=ON')
        return db

    def setting(self, key: str, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value) -> None:
        with self.lock, self.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))

    def _fernet(self):
        if self.secrets is None:
            raise RuntimeError('Le coffre Windows est nécessaire pour chiffrer le cache.')
        if self._key is None:
            try:
                self._key = self.secrets.get('cache-encryption-key')
            except RuntimeError:
                # Ne jamais remplacer une clé perdue d’un cache déjà chiffré.
                if self.setting('cache_encrypted', False):
                    raise RuntimeError('Clé de chiffrement absente. Restaurez le coffre Windows avant de lire le cache.')
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

    def cache_put(self, kind: str, key: str, value) -> None:
        with self.lock:
            payload = json.dumps(value, ensure_ascii=False).encode('utf-8')
            encrypted = self.setting('cache_encrypted', False)
            payload = b'E' + self._fernet().encrypt(payload) if encrypted else b'P' + payload
            with self.connect() as db:
                db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)', (kind, self._cache_key(key), payload))

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
            with self.connect() as db:
                db.execute('VACUUM')

    def accounts(self) -> list[Account]:
        with self.connect() as db:
            return [Account.from_dict(json.loads(row[0])) for row in db.execute('SELECT config FROM accounts ORDER BY rowid')]

    def save(self, account: Account) -> None:
        account.validate()
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO accounts VALUES (?,?)', (account.id, json.dumps(account.to_dict())))

    def pin(self, account: str, endpoint: str) -> str | None:
        with self.connect() as db:
            row = db.execute('SELECT fingerprint FROM pins WHERE account=? AND endpoint=?', (account, endpoint)).fetchone()
            return row[0] if row else None

    def trust(self, account: str, endpoint: str, fingerprint: str) -> None:
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO pins VALUES (?,?,?)', (account, endpoint, fingerprint))
