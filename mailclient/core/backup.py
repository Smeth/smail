"""Sauvegarde et restauration de ce qui n’existe que sur ce PC.

Les messages restent sur le serveur de messagerie (IMAP) : ils réapparaissent d’eux-mêmes sur un nouveau PC. La
sauvegarde contient tout le reste : comptes (sans mot de passe), préférences, signatures, règles et listes
d’expéditeurs, contacts, brouillons et copies envoyées gardés sur ce PC, envois programmés, messages reportés et
exceptions de certificat.

Fichier « .smailbackup » : « SMAILBK1 », sel, puis les données compressées et chiffrées (Fernet : AES-128-CBC et
HMAC-SHA256) avec une clé dérivée du mot de passe par scrypt. Sans le mot de passe, le fichier est illisible ; un
fichier modifié est refusé. Les mots de passe des comptes et les jetons OAuth n’y figurent jamais : ils restent dans
le Gestionnaire d’identifiants de Windows et sont redemandés après une restauration.
"""
import base64
import json
import os
import zlib
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from mailclient.core.accounts import Account
from mailclient.i18n import tr

MAGIC = b'SMAILBK1'
FORMAT = 1
SUFFIX = '.smailbackup'
MIN_PASSWORD = 8
# Données propres à ce PC (le cache des messages, retéléchargeable, n’est pas sauvegardé).
KINDS = ('draft', 'sent-copy', 'outbox', 'filters', 'signature', 'contacts', 'snooze')
# Réglages liés à cette installation : jamais copiés d’un PC à l’autre.
LOCAL_SETTINGS = {'cache_encrypted', 'update_pending', 'last_backup', 'backup_reminded'}


class BackupError(Exception):
    pass


def _key(password: str, salt: bytes) -> bytes:
    raw = Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(password.encode('utf-8'))
    return base64.urlsafe_b64encode(raw)


def export(db, password: str) -> bytes:
    """Contenu chiffré d’un fichier de sauvegarde."""
    from mailclient import __version__
    if len(password or '') < MIN_PASSWORD:
        raise BackupError(tr('Choisissez un mot de passe d’au moins {count} caractères.').format(count=MIN_PASSWORD))
    accounts = []
    for account in db.accounts():
        config = account.to_dict()
        accounts.append(config)
    payload = dict(format=FORMAT, version=__version__, created=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                   accounts=accounts,
                   settings={key: value for key, value in db.settings_items().items() if key not in LOCAL_SETTINGS},
                   pins=[list(pin) for pin in db.pins()],
                   cache=[dict(kind=kind, key=key, account=account, value=value)
                          for kind, key, account, value in db.cache_rows(KINDS)])
    data = zlib.compress(json.dumps(payload, ensure_ascii=False).encode('utf-8'), 9)
    salt = os.urandom(16)
    return MAGIC + salt + Fernet(_key(password, salt)).encrypt(data)


def read(data: bytes, password: str) -> dict:
    """Contenu d’une sauvegarde ; BackupError si le fichier n’en est pas une, est abîmé ou si le mot de passe est faux."""
    if not data.startswith(MAGIC) or len(data) < len(MAGIC) + 17:
        raise BackupError(tr('Ce fichier n’est pas une sauvegarde de Smail.'))
    salt, token = data[len(MAGIC):len(MAGIC) + 16], data[len(MAGIC) + 16:]
    try:
        payload = json.loads(zlib.decompress(Fernet(_key(password or '', salt)).decrypt(token)).decode('utf-8'))
    except InvalidToken:
        raise BackupError(tr('Mot de passe incorrect, ou fichier de sauvegarde modifié.')) from None
    except (zlib.error, ValueError, UnicodeDecodeError):
        raise BackupError(tr('Sauvegarde illisible.')) from None
    if not isinstance(payload, dict) or payload.get('format') != FORMAT:
        raise BackupError(tr('Cette sauvegarde vient d’une version plus récente de Smail : mettez Smail à jour.'))
    return payload


def summary(payload: dict) -> dict:
    """Ce que contient une sauvegarde, pour la confirmation avant restauration."""
    counts = {}
    for entry in payload.get('cache', []):
        counts[entry.get('kind')] = counts.get(entry.get('kind'), 0) + 1
    return dict(created=payload.get('created', ''), version=payload.get('version', ''),
                accounts=[f"{item.get('name') or ''} <{item.get('email', '')}>".strip() for item in payload.get('accounts', [])],
                drafts=counts.get('draft', 0), sent=counts.get('sent-copy', 0), outbox=counts.get('outbox', 0))


def restore(db, payload: dict) -> list[Account]:
    """Ajoute les comptes de la sauvegarde (ceux déjà présents sont mis à jour) et reprend leurs données locales.
    Renvoie les comptes restaurés : leur mot de passe ou leur connexion OAuth reste à saisir sur ce PC."""
    accounts = []
    for config in payload.get('accounts', []):
        try:
            account = Account.from_dict(config)
            db.save(account)
        except (TypeError, ValueError, KeyError):
            continue  # Compte invalide : ignoré, les autres sont restaurés.
        accounts.append(account)
    known = {account.id for account in db.accounts()}
    for key, value in (payload.get('settings') or {}).items():
        if isinstance(key, str) and key not in LOCAL_SETTINGS:
            db.set_setting(key, value)
    for pin in payload.get('pins', []):
        if isinstance(pin, list) and len(pin) == 3 and pin[0] in known:
            db.trust(*pin)
    for entry in payload.get('cache', []):
        if entry.get('kind') in KINDS and isinstance(entry.get('key'), str) and len(entry['key']) == 64:
            account = entry.get('account')
            db.cache_put_hashed(entry['kind'], entry['key'], entry.get('value'), account if account in known else None)
    db.set_setting('last_backup', datetime.now(timezone.utc).isoformat(timespec='seconds'))
    return accounts


def reminder_due(db, days: int = 30) -> bool:
    """Rappel mensuel : des comptes existent et aucune sauvegarde (ni rappel) depuis `days` jours."""
    if not db.setting('backup_reminder', True) or not db.accounts():
        return False
    now = datetime.now(timezone.utc)
    for key in ('last_backup', 'backup_reminded'):
        value = db.setting(key)
        try:
            if value and (now - datetime.fromisoformat(value)).days < days:
                return False
        except (TypeError, ValueError):
            pass
    return True
