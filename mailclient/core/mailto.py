"""Liens « mailto: » (RFC 6068) : ouverture d’un nouveau message prérempli, jamais d’envoi automatique."""
from urllib.parse import parse_qsl, unquote, urlsplit

FIELDS = ('to', 'cc', 'bcc', 'subject', 'body')
LIMITS = {'to': 2000, 'cc': 2000, 'bcc': 2000, 'subject': 500, 'body': 20000}


def is_mailto(value: str) -> bool:
    return isinstance(value, str) and value[:7].lower() == 'mailto:'


def parse(url: str) -> dict:
    """Champs d’un nouveau message ; adresses séparées par des virgules, textes décodés, longueurs bornées."""
    if not is_mailto(url):
        raise ValueError('Lien mailto invalide.')
    parts = urlsplit(url.strip())
    fields = {name: '' for name in FIELDS}
    recipients = [unquote(address).strip() for address in parts.path.split(',') if address.strip()]
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        key = key.lower()
        if key in ('to', 'cc', 'bcc'):
            values = [address.strip() for address in value.split(',') if address.strip()]
            if key == 'to':
                recipients += values
            else:
                fields[key] = ', '.join(filter(None, [fields[key]] + values))
        elif key in ('subject', 'body') and not fields[key]:
            fields[key] = value.replace('\r\n', '\n')
    fields['to'] = ', '.join(dict.fromkeys(recipients))
    for name, limit in LIMITS.items():
        fields[name] = ''.join(ch for ch in fields[name] if ch == '\n' or ch >= ' ')[:limit]
    return fields
