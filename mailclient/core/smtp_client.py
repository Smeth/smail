"""SMTP chiffré, en-têtes validés et Cci uniquement dans l’enveloppe."""
import smtplib
import mimetypes
import re
from email.message import EmailMessage
from email.utils import getaddresses, formataddr, formatdate, make_msgid
from email import policy
from mailclient.core.tls_policy import require_starttls
from mailclient.core.oauth import xoauth2

def addresses(value: str) -> list[tuple[str, str]]:
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Les en-têtes ne doivent pas contenir de caractères de contrôle.')
    value = value.strip().rstrip(',;').strip()  # Virgule finale laissée par l’autocomplétion.
    if not value:
        return []
    result = getaddresses([value])
    if not result or any(not address.isascii() or len(address) > 254 or not re.fullmatch(r'[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+', address) for _, address in result):
        raise ValueError('Adresse destinataire invalide. Séparez les adresses par des virgules.')
    return result

def build_message(account, to: str, cc: str, bcc: str, subject: str, body: str, attachments=(), reply_id='', references='', allow_empty=False, html=''):
    """html : document complet produit par l’éditeur ; envoyé en multipart/alternative avec le texte brut."""
    account.validate()
    for value in (subject, reply_id, references):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Caractère de contrôle interdit dans un en-tête.')
    groups = [addresses(value) for value in (to, cc, bcc)]
    recipients = list({address.casefold(): address for group in groups for _, address in group}.values())
    if not recipients and not allow_empty:
        raise ValueError('Ajoutez au moins un destinataire.')
    message = EmailMessage(policy=policy.SMTP)
    message['From'] = formataddr((account.name, account.email))
    for header, group in zip(('To', 'Cc'), groups):
        if group:
            message[header] = ', '.join(formataddr(pair) for pair in group)
    message['Subject'] = subject
    message['Date'] = formatdate(localtime=True)
    message['Message-ID'] = make_msgid(domain=account.email.split('@')[-1])
    if reply_id:
        message['In-Reply-To'] = reply_id
    if references:
        message['References'] = references
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype='html')
    for attachment in attachments:
        content_type = mimetypes.guess_type(attachment.name)[0] or 'application/octet-stream'
        major, minor = content_type.split('/', 1)
        message.add_attachment(attachment.data, maintype=major, subtype=minor, filename=attachment.name)
    return message, recipients

def open_connection(account, password, tls):
    server = account.smtp
    def factory(context):
        if server.mode == 'SSL/TLS':
            return smtplib.SMTP_SSL(server.host, server.port, timeout=20, context=context)
        client = smtplib.SMTP(server.host, server.port, timeout=20)
        try:
            client.ehlo()
            require_starttls(client.has_extn('starttls'))
            client.starttls(context=context)
            client.ehlo()
            return client
        except BaseException:
            client.close()
            raise
    client = smtplib.SMTP(server.host, server.port, timeout=20) if server.mode == 'Aucun' else tls.connect(account.id, f'smtp:{server.host}:{server.port}:{server.mode}', factory)
    try:
        client.ehlo()
        if account.auth_method == 'password':
            client.login(account.email, password)
        else:
            payload = xoauth2(account.email, password).decode('utf-8')
            client.auth('XOAUTH2', lambda challenge=None: payload if challenge is None else '', initial_response_ok=True)
        return client
    except BaseException:
        client.close()
        raise

def test_connection(account, password, tls):
    open_connection(account, password, tls).close()

def send_message(account, password, tls, message, recipients):
    """Aucun nouvel essai automatique après DATA : risque de double envoi."""
    client = open_connection(account, password, tls)
    try:
        return client.send_message(message, from_addr=account.email, to_addrs=recipients)
    finally:
        client.close()
