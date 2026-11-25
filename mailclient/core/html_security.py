"""HTML sur liste blanche ; aucune feuille de style provenant d'un mail."""
import base64
import html
import re
import bleach
from mailclient.core.parser import Mail

TAGS = {'p', 'br', 'div', 'span', 'b', 'strong', 'i', 'em', 'u', 's', 'blockquote',
        'pre', 'code', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'td', 'th',
        'h1', 'h2', 'h3', 'h4', 'hr', 'a', 'img'}
EXECUTABLE_SUFFIXES = {'.exe', '.com', '.bat', '.cmd', '.js', '.jse', '.vbs', '.vbe',
                       '.scr', '.msi', '.msp', '.ps1', '.psm1', '.hta', '.lnk',
                       '.url', '.reg', '.pif', '.cpl', '.jar', '.wsf', '.wsh', '.svg',
                       '.py', '.pyw', '.docm', '.xlsm', '.pptm',
                       # Macros des anciens formats Office, compléments et modèles.
                       '.doc', '.dot', '.dotm', '.xls', '.xlt', '.xltm', '.xlam', '.xla', '.xll', '.ppt', '.pot', '.potm',
                       '.ppam', '.ppsm', '.sldm', '.one', '.onepkg',
                       # Images disque (contournent la marque Internet), installeurs et raccourcis Windows.
                       '.iso', '.img', '.vhd', '.vhdx', '.msix', '.msixbundle', '.appx', '.appxbundle', '.appinstaller',
                       '.application', '.appref-ms', '.gadget', '.msc', '.chm', '.hlp', '.inf', '.scf', '.sct', '.wsc',
                       '.settingcontent-ms', '.search-ms', '.searchconnector-ms', '.library-ms', '.website', '.diagcab',
                       '.cab', '.dll', '.ocx', '.sys', '.drv', '.cpl', '.ws', '.mde', '.mda', '.accde', '.ade', '.adp',
                       '.vb', '.vbscript', '.psd1', '.ps1xml', '.psc1', '.mst', '.msh', '.msh1', '.msh2', '.mshxml',
                       '.xbap', '.xnk', '.mcf', '.mam', '.maq', '.mar', '.mat', '.jnlp', '.hpj', '.shs', '.ins', '.isp'}


def mark_from_internet(path) -> None:
    """Marque Internet de Windows (Mark-of-the-Web) sur une pièce jointe enregistrée, comme Outlook et les
    navigateurs : Office l’ouvre en mode protégé et bloque ses macros, SmartScreen vérifie les programmes."""
    import os
    if os.name != 'nt':
        return
    try:
        with open(f'{path}:Zone.Identifier', 'w', encoding='ascii') as stream:
            stream.write('[ZoneTransfer]\r\nZoneId=3\r\n')
    except OSError:
        pass  # Disque sans flux NTFS (clé USB en FAT32…) : rien de plus à faire.

def dangerous_filename(name: str) -> bool:
    return any(name.lower().rstrip(' .').endswith(suffix) for suffix in EXECUTABLE_SUFFIXES)

def safe_document(mail: Mail, remote_images: bool = False, dark: bool = False) -> str:
    source = mail.html or '<pre>' + html.escape(mail.text) + '</pre>'
    safe = bleach.clean(source, tags=TAGS,
                        attributes={'img': ['src', 'alt', 'width', 'height'], 'td': ['colspan', 'rowspan'],
                                    'th': ['colspan', 'rowspan'], 'a': ['title']},
                        protocols={'http', 'https', 'cid'}, strip=True, strip_comments=True)
    embedded = {a.cid: a for a in mail.attachments if a.cid and a.content_type in {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}}
    def image(match):
        url = html.unescape(match[1])
        if url.startswith('cid:') and url[4:] in embedded:
            attachment = embedded[url[4:]]
            return 'src="data:' + attachment.content_type + ';base64,' + base64.b64encode(attachment.data).decode('ascii') + '"'
        if remote_images and re.match(r'^https?://', url, re.I):
            return 'src="' + html.escape(url, quote=True) + '"'
        return ''
    safe = re.sub(r'\bsrc="([^"]*)"', image, safe)
    images = 'data: https: http:' if remote_images else 'data:'
    csp = f"default-src 'none'; img-src {images}; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    foreground, background = ('#eeeeee', '#191b1f') if dark else ('#202124', 'white')
    return ('<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'
            + html.escape(csp, quote=True) + '"><style>body{font:15px sans-serif;overflow-wrap:anywhere;padding:12px;color:#202124;background:white}'
            f'body{{color:{foreground};background:{background}}}'
            'img{max-width:100%;height:auto}pre{white-space:pre-wrap}table{max-width:100%}blockquote{border-left:3px solid #ccc;padding-left:12px}</style></head><body>'
            + safe + '</body></html>')
