"""TLS strict, STARTTLS sans repli et exceptions liées au certificat exact.

La sonde et la vérification d'empreinte précèdent toujours l'authentification.
Une exception temporaire ne dure que pendant la session de l'application.
"""
from mailclient.i18n import tr
import hashlib
import ssl
import threading
from dataclasses import dataclass
from cryptography import x509

@dataclass
class CertificateAlert(Exception):
    account: str
    endpoint: str
    fingerprint: str
    issuer: str
    validity: str
    reason: str

class TLSPolicy:
    def __init__(self, database):
        self.database = database
        self.session: dict[tuple[str, str], str] = {}
        self.lock = threading.Lock()

    def approve(self, alert: CertificateAlert, permanent: bool) -> None:
        with self.lock:
            self.session[alert.account, alert.endpoint] = alert.fingerprint
            if permanent:
                self.database.trust(alert.account, alert.endpoint, alert.fingerprint)

    def forget(self, account: str, endpoint: str | None = None) -> None:
        """Retire les exceptions de session (et permanentes) d’un compte ou d’un seul point d’accès."""
        with self.lock:
            for key in [key for key in self.session if key[0] == account and endpoint in (None, key[1])]:
                del self.session[key]
        if endpoint is not None:
            self.database.untrust(account, endpoint)

    def connect(self, account: str, endpoint: str, factory):
        """factory(context) établit TLS sans transmettre d'identifiants."""
        context = ssl.create_default_context()
        try:
            connection = factory(context)
            reason = tr('Le certificat a changé depuis votre décision de confiance.')
        except ssl.SSLCertVerificationError as error:
            reason = tr('Échec de vérification : {message}').format(message=error.verify_message)
            connection = factory(ssl._create_unverified_context())
        try:
            der = connection.sock.getpeercert(binary_form=True)
            fingerprint = hashlib.sha256(der).hexdigest()
            with self.lock:
                trusted = self.session.get((account, endpoint)) or self.database.pin(account, endpoint)
            valid = connection.sock.context.verify_mode == ssl.CERT_REQUIRED
            if (trusted and trusted != fingerprint) or (not valid and trusted != fingerprint):
                cert = x509.load_der_x509_certificate(der)
                raise CertificateAlert(account, endpoint, fingerprint, cert.issuer.rfc4514_string(),
                                       f'{cert.not_valid_before_utc.isoformat()} → {cert.not_valid_after_utc.isoformat()}', reason)
            return connection
        except BaseException:
            connection.sock.close()
            raise

def require_starttls(available: bool) -> None:
    if not available:
        raise RuntimeError(tr('Le serveur ne propose pas STARTTLS. Connexion annulée ; aucun repli en clair.'))
