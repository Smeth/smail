"""Configuration publique des comptes, sans secret."""
from dataclasses import dataclass, field, asdict
from uuid import uuid4
import re

MODES = ('SSL/TLS', 'STARTTLS', 'Aucun')
PORTS = {'imap': (993, 143, 143), 'smtp': (465, 587, 25)}
PRESETS = {
    'gmail.com': ('imap.gmail.com', 'smtp.gmail.com'),
    'outlook.com': ('outlook.office365.com', 'smtp.office365.com'),
    'hotmail.com': ('outlook.office365.com', 'smtp.office365.com'),
    'yahoo.com': ('imap.mail.yahoo.com', 'smtp.mail.yahoo.com'),
    'yahoo.fr': ('imap.mail.yahoo.com', 'smtp.mail.yahoo.com'),
}

@dataclass
class Server:
    host: str
    port: int
    mode: str = 'SSL/TLS'

    def validate(self) -> None:
        if not re.fullmatch(r'[A-Za-z0-9._:-]+', self.host) or not 1 <= self.port <= 65535 or self.mode not in MODES:
            raise ValueError('Serveur, port ou type de connexion invalide.')

@dataclass
class Account:
    name: str
    email: str
    imap: Server
    smtp: Server
    id: str = field(default_factory=lambda: str(uuid4()))
    auth_method: str = 'password'
    oauth_client_id: str = ''
    signature: str = ''
    oauth_tenant: str = 'common'

    def validate(self) -> None:
        if not self.name.strip() or len(self.name) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in self.name + self.email):
            raise ValueError('Nom ou adresse invalide.')
        if not self.email.isascii() or len(self.email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', self.email):
            raise ValueError('Adresse e-mail invalide.')
        self.imap.validate()
        self.smtp.validate()
        if self.auth_method not in {'password', 'google', 'microsoft'}:
            raise ValueError('Méthode d’authentification inconnue.')
        if self.auth_method != 'password':
            if not self.oauth_client_id.strip() or any(c in self.oauth_client_id for c in '\r\n\x00'):
                raise ValueError('Un identifiant client OAuth2 est requis.')
            if self.imap.mode == 'Aucun' or self.smtp.mode == 'Aucun':
                raise ValueError('OAuth2 exige une connexion chiffrée sur les deux serveurs.')
            if not re.fullmatch(r'[A-Za-z0-9.-]{1,200}', self.oauth_tenant):
                raise ValueError('Tenant Microsoft invalide.')

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Account':
        return cls(**{**data, 'imap': Server(**data['imap']), 'smtp': Server(**data['smtp'])})
