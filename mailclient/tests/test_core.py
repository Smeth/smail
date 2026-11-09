import ssl
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mailclient.core.accounts import Account, Server
from mailclient.core.parser import metadata, decode_header_value, decode_folder
from mailclient.core.tls_policy import TLSPolicy, CertificateAlert, require_starttls
from mailclient.storage.database import Database

@pytest.fixture
def database(tmp_path):
    return Database(tmp_path / 'settings.db')

def test_storage_roundtrip_and_no_secret(database):
    account = Account('Travail', 'test@example.com', Server('localhost', 993), Server('localhost', 465))
    database.save(account)
    assert database.accounts() == [account]
    assert 'password' not in account.to_dict()
    database.trust(account.id, 'imap:localhost', 'abc')
    assert database.pin(account.id, 'imap:localhost') == 'abc'
    assert database.pin('other', 'imap:localhost') is None
    database.trust(account.id, 'imap:localhost', 'changed')
    assert database.pin(account.id, 'imap:localhost') == 'changed'

@pytest.mark.parametrize('host,port,mode', [('bad\r\nhost', 993, 'SSL/TLS'), ('host', 0, 'SSL/TLS'), ('host', 993, 'other')])
def test_server_validation(host, port, mode):
    with pytest.raises(ValueError):
        Server(host, port, mode).validate()

@pytest.mark.parametrize('encoded,expected', [
    ('=?utf-8?b?Q2Fmw6k=?=', 'Café'), ('=?iso-8859-1?q?caf=E9?=', 'café'),
    ('Simple', 'Simple'), ('=?unknown?q?test?=', 'test')])
def test_headers(encoded, expected):
    assert decode_header_value(encoded) == expected

def test_mime_metadata():
    raw = b'From: =?utf-8?q?Andr=C3=A9?= <a@example.com>\r\nSubject: =?iso-8859-1?q?R=E9union?=\r\nMIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=x\r\n\r\n--x\r\nContent-Type: text/plain\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\nBonjour=20!\r\n--x\r\nContent-Disposition: attachment; filename="a.pdf"\r\nContent-Transfer-Encoding: base64\r\n\r\nYQ==\r\n--x--\r\n'
    row = metadata(raw)
    assert row['subject'] == 'Réunion'
    assert 'André' in row['sender']
    assert row['attachment']

def test_folder_encoding():
    assert decode_folder('&AMk-l&AOk-ments envoy&AOk-s') == 'Éléments envoyés'
    assert decode_folder('A &- B') == 'A & B'

@pytest.fixture
def cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1)).sign(key, hashes.SHA256())
            .public_bytes(serialization.Encoding.DER))

class FakeSocket:
    def __init__(self, context, der):
        self.context, self.der, self.closed = context, der, False
    def getpeercert(self, binary_form=False):
        assert binary_form
        return self.der
    def close(self):
        self.closed = True

def test_invalid_cert_requires_approval_and_persists_exact_pin(database, cert):
    policy = TLSPolicy(database)
    sockets = []
    def factory(context):
        if context.verify_mode == ssl.CERT_REQUIRED:
            error = ssl.SSLCertVerificationError()
            error.verify_message = 'self signed certificate'
            raise error
        sock = FakeSocket(context, cert)
        sockets.append(sock)
        return SimpleNamespace(sock=sock)
    with pytest.raises(CertificateAlert) as captured:
        policy.connect('a', 'imap:host', factory)
    alert = captured.value
    assert sockets[-1].closed
    assert alert.issuer == 'CN=localhost'
    assert len(alert.fingerprint) == 64
    policy.approve(alert, True)
    assert not TLSPolicy(database).connect('a', 'imap:host', factory).sock.closed
    with pytest.raises(CertificateAlert):
        policy.connect('other-account', 'imap:host', factory)

def test_changed_pin_prompts_even_for_valid_certificate(database, cert):
    database.trust('a', 'endpoint', 'old')
    policy = TLSPolicy(database)
    factory = lambda context: SimpleNamespace(sock=FakeSocket(context, cert))
    with pytest.raises(CertificateAlert) as captured:
        policy.connect('a', 'endpoint', factory)
    policy.approve(captured.value, False)
    assert policy.connect('a', 'endpoint', factory)
    assert database.pin('a', 'endpoint') == 'old'
    with pytest.raises(CertificateAlert):
        TLSPolicy(database).connect('a', 'endpoint', factory)

def test_valid_certificate_uses_system_verification(database, cert):
    def factory(context):
        assert context.check_hostname
        assert context.verify_mode == ssl.CERT_REQUIRED
        return SimpleNamespace(sock=FakeSocket(context, cert))
    assert TLSPolicy(database).connect('a', 'endpoint', factory)

def test_starttls_never_falls_back():
    with pytest.raises(RuntimeError, match='aucun repli'):
        require_starttls(False)
    require_starttls(True)
