"""SMTP chiffré, en-têtes validés et Cci uniquement dans l’enveloppe."""
from mailclient.i18n import tr
import smtplib
import mimetypes
import re
from email.message import EmailMessage
from email.utils import getaddresses, formataddr, formatdate, make_msgid
from email import policy
from mailclient.core.tls_policy import require_starttls
from mailclient.core.oauth import xoauth2

def display_address(pair) -> str:
    """Adresse lisible pour un champ À/Cc : contrairement à formataddr, le nom n’est jamais encodé
    (« Léa <lea@x.fr> », pas « =?utf-8?q?L=C3=A9a?= »). L’encodage RFC 2047 a lieu à l’envoi."""
    name, address = ' '.join(pair[0].split()), pair[1]
    if not name:
        return address
    if any(c in name for c in ',;"<>@()[]:\\'):
        name = '"' + name.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return f'{name} <{address}>'

def addresses(value: str) -> list[tuple[str, str]]:
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(tr('Les en-têtes ne doivent pas contenir de caractères de contrôle.'))
    value = value.strip().rstrip(',;').strip()  # Virgule finale laissée par l’autocomplétion.
    if not value:
        return []
    result = getaddresses([value])
    if not result or any(not address.isascii() or len(address) > 254 or not re.fullmatch(r'[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+', address) for _, address in result):
        raise ValueError(tr('Adresse destinataire invalide. Séparez les adresses par des virgules.'))
    return result

def build_message(account, to: str, cc: str, bcc: str, subject: str, body: str, attachments=(), reply_id='', references='', allow_empty=False, html='', calendar=''):
    """html : document complet produit par l’éditeur ; envoyé en multipart/alternative avec le texte brut."""
    account.validate()
    for value in (subject, reply_id, references):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError(tr('Caractère de contrôle interdit dans un en-tête.'))
    groups = [addresses(value) for value in (to, cc, bcc)]
    recipients = list({address.casefold(): address for group in groups for _, address in group}.values())
    if not recipients and not allow_empty:
        raise ValueError(tr('Ajoutez au moins un destinataire.'))
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
    if calendar:
        # Réponse d’invitation (iTIP) : alternative text/calendar; method=REPLY, lue par les agendas.
        message.add_alternative(calendar, subtype='calendar', params={'method': 'REPLY'})
    for attachment in attachments:
        content_type = mimetypes.guess_type(attachment.name)[0] or 'application/octet-stream'
        if content_type == 'message/rfc822':
            # Message transféré en pièce jointe : partie message/rfc822 (jamais en base64, interdit par la RFC 2046).
            from email import message_from_bytes, policy as email_policy
            try:
                message.add_attachment(message_from_bytes(attachment.data, policy=email_policy.default), filename=attachment.name)
                continue
            except Exception:
                content_type = 'application/octet-stream'  # Message illisible : joint comme simple fichier.
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
            client.login(account.smtp_user, password)
        else:
            payload = xoauth2(account.email, password).decode('utf-8')
            client.auth('XOAUTH2', lambda challenge=None: payload if challenge is None else '', initial_response_ok=True)
        return client
    except BaseException:
        client.close()
        raise

def test_connection(account, password, tls):
    open_connection(account, password, tls).close()

# Après la fin du message (DATA), le serveur analyse souvent le contenu (antivirus, antispam) avant de
# répondre : la RFC 5321 (4.5.3.2) recommande d’attendre jusqu’à 10 minutes. 20 s suffisent pour se
# connecter, pas pour cette réponse avec plusieurs pièces jointes.
SEND_TIMEOUT = 300


class DeliveryUncertain(RuntimeError):
    """Connexion perdue pendant l’envoi : le serveur a pu accepter le message sans pouvoir le confirmer."""


UPLOAD_CHUNK = 64 * 1024


def report_upload(client, progress):
    """Envoie le contenu du message (DATA) par blocs et signale l’avancement.

    smtplib transmet tout le message en un seul appel à send(), terminé par CRLF.CRLF : seul cet appel
    est découpé ; les commandes (MAIL, RCPT, DATA) passent telles quelles."""
    original = client.send
    def send(data):
        if not (isinstance(data, bytes) and data.endswith(b'\r\n.\r\n')) or client.sock is None:
            return original(data)
        total = len(data)
        try:
            for start in range(0, total, UPLOAD_CHUNK):
                client.sock.sendall(data[start:start + UPLOAD_CHUNK])
                progress('upload', min(start + UPLOAD_CHUNK, total), total)
        except OSError:
            client.close()
            raise smtplib.SMTPServerDisconnected('Server not connected')
        progress('verify', total, total)  # Reste la réponse du serveur, souvent après son analyse antivirus.
    client.send = send


def send_message(account, password, tls, message, recipients, progress=None):
    """Aucun nouvel essai automatique après DATA : risque de double envoi.

    progress(étape, fait, total) : 'connect', 'upload' (octets), 'verify' (attente de la réponse du serveur)."""
    if progress:
        progress('connect', 0, 0)
    client = open_connection(account, password, tls)
    try:
        if client.sock is not None:
            client.sock.settimeout(SEND_TIMEOUT)
        if progress:
            report_upload(client, progress)
        return client.send_message(message, from_addr=account.email, to_addrs=recipients)
    except (smtplib.SMTPServerDisconnected, TimeoutError, ConnectionError) as error:
        raise DeliveryUncertain(
            tr('Le serveur d’envoi n’a pas confirmé la réception du message (connexion coupée ou réponse trop lente). '
            'Il a peut-être été envoyé : vérifiez auprès du destinataire ou dans les Envoyés avant de réessayer.')) from error
    finally:
        client.close()
