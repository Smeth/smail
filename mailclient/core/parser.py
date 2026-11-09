"""Décodage des métadonnées MIME et noms de dossiers IMAP."""
import base64
import re
from email import policy
from email.parser import BytesParser
from email.header import decode_header
from dataclasses import dataclass, field
from pathlib import PureWindowsPath
import unicodedata

@dataclass
class Attachment:
    name: str
    content_type: str
    data: bytes
    cid: str = ''

@dataclass
class Mail:
    sender: str
    recipients: str
    subject: str
    date: str
    text: str = ''
    html: str = ''
    attachments: list[Attachment] = field(default_factory=list)
    cc: str = ''
    reply_to: str = ''
    message_id: str = ''
    references: str = ''

def safe_filename(name: str) -> str:
    """Neutralise chemins, caractères Windows interdits et noms réservés."""
    name = PureWindowsPath(name).name
    name = ''.join('_' if c in '<>:"/\\|?*' or unicodedata.category(c).startswith('C') else c for c in name)
    name = name.strip(' .')[:180].rstrip(' .') or 'piece-jointe'
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        name = '_' + name
    return name

def decode_body(part) -> str:
    data = part.get_payload(decode=True) or b''
    try:
        return data.decode(part.get_content_charset() or 'utf-8', errors='replace')
    except LookupError:
        return data.decode('utf-8', errors='replace')

def parse_message(raw: bytes) -> Mail:
    """Décode MIME, sans confondre un texte joint avec le corps du message."""
    message = BytesParser(policy=policy.default).parsebytes(raw)
    result = Mail(str(message.get('From', '')), str(message.get('To', '')),
                  str(message.get('Subject', '(Sans objet)')), str(message.get('Date', '')))
    plain, html = [], []
    def visit(part):
        filename = part.get_filename()
        cid = str(part.get('Content-ID', '')).strip('<> \t\r\n')
        if filename or part.get_content_disposition() == 'attachment' or (cid and not part.is_multipart() and part.get_content_maintype() != 'text'):
            if part.get_content_type() == 'message/rfc822':
                payload = part.get_payload()
                data = b'\r\n'.join(p.as_bytes(policy=policy.SMTP) for p in payload) if isinstance(payload, list) else b''
            else:
                data = part.get_payload(decode=True) or b''
            result.attachments.append(Attachment(safe_filename(filename or ('message.eml' if part.get_content_type() == 'message/rfc822' else f'piece-jointe-{len(result.attachments)+1}')),
                                                 part.get_content_type(), data, cid))
        elif part.is_multipart():
            for child in part.iter_parts():
                visit(child)
        elif part.get_content_type() == 'text/plain':
            plain.append(decode_body(part))
        elif part.get_content_type() == 'text/html':
            html.append(decode_body(part))
        else:
            result.attachments.append(Attachment(f'piece-jointe-{len(result.attachments)+1}', part.get_content_type(), part.get_payload(decode=True) or b''))
    visit(message)
    result.text, result.html = '\n\n'.join(plain), '\n'.join(html)
    result.cc = str(message.get('Cc', ''))
    result.reply_to = str(message.get('Reply-To', ''))
    result.message_id = str(message.get('Message-ID', ''))
    result.references = str(message.get('References', ''))
    return result

def decode_header_value(value: str) -> str:
    result = []
    for part, encoding in decode_header(value):
        if isinstance(part, bytes):
            try:
                part = part.decode(encoding or 'ascii', errors='replace')
            except LookupError:
                part = part.decode('utf-8', errors='replace')
        result.append(part)
    return ''.join(result)

def decode_folder(value: str) -> str:
    def replace(match):
        token = match.group(1)
        if not token:
            return '&'
        try:
            return base64.b64decode(token.replace(',', '/') + '=' * (-len(token) % 4)).decode('utf-16-be')
        except (ValueError, UnicodeError):
            return match.group(0)
    return re.sub(r'&([^-]*)-', replace, value)

def metadata(raw: bytes) -> dict:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    return {'sender': str(message.get('From', '')), 'subject': str(message.get('Subject', '(Sans objet)')),
            'date': str(message.get('Date', '')),
            'attachment': any(p.get_content_disposition() == 'attachment' or p.get_filename() for p in message.walk())}
