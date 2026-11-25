"""Réponse et transfert d’un message mis en forme : l’original est cité avec sa mise en forme (nettoyée).

Le texte de l’utilisateur vient de l’éditeur ; le message d’origine n’y est pas recopié (le HTML reconstruit par
l’éditeur perdrait tableaux et mise en page). Il est joint à l’envoi, sous la réponse, dans un bloc de citation :
HTML sur liste blanche, aucune image distante, liens http(s) et mailto seulement. La version texte reste citée
avec « > », comme toujours.
"""
import base64
import html
import re

import bleach

from mailclient.core.html_security import TAGS
from mailclient.i18n import tr

EMAIL_BODY = ('<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
              '<body style="font-family: \'Segoe UI\', Arial, sans-serif; font-size: 14px; line-height: 1.45;">{}</body></html>')
QUOTE_STYLE = 'margin: 0 0 0 0.8ex; border-left: 2px solid #c4ccd8; padding-left: 1ex; color: #374151;'
IMAGES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}


def quote_fragment(mail) -> str:
    """Corps HTML du message d’origine, nettoyé : images intégrées (cid:) conservées, images distantes retirées."""
    safe = bleach.clean(mail.html or '', tags=TAGS,
                        attributes={'img': ['src', 'alt', 'width', 'height'], 'td': ['colspan', 'rowspan'],
                                    'table': ['border', 'cellpadding', 'cellspacing'],
                                    'th': ['colspan', 'rowspan'], 'a': ['href', 'title']},
                        protocols={'http', 'https', 'mailto', 'cid'}, strip=True, strip_comments=True)
    embedded = {a.cid: a for a in mail.attachments if a.cid and a.content_type in IMAGES}

    def image(match):
        url = html.unescape(match[1])
        if url.startswith('cid:') and url[4:] in embedded:
            attachment = embedded[url[4:]]
            return 'src="data:' + attachment.content_type + ';base64,' + base64.b64encode(attachment.data).decode('ascii') + '"'
        return ''  # Jamais d’image distante : elle préviendrait l’expéditeur d’origine, voire chaque destinataire.
    safe = re.sub(r'\bsrc="([^"]*)"', image, safe)
    safe = re.sub(r'<img\b(?![^>]*\bsrc="data:)[^>]*>', '', safe)  # Image sans source intégrée : retirée.
    return re.sub(r'\bhref="(?!https?:|mailto:)[^"]*"', '', safe, flags=re.I)


def reply_quote(mail, mode: str, plain: str) -> tuple[str, str]:
    """(HTML, texte) de la citation : « Le …, … a écrit : » puis l’original, ou l’en-tête d’un message transféré."""
    if mode == 'forward':
        lines = [tr('---------- Message transféré ----------'), tr('De : {value}').format(value=mail.sender),
                 tr('Date : {value}').format(value=mail.date), tr('Objet : {value}').format(value=mail.subject),
                 tr('À : {value}').format(value=mail.recipients)]
        if mail.cc:
            lines.append(tr('Cc : {value}').format(value=mail.cc))
        header_html = '<br>'.join(html.escape(line) for line in lines)
        return (f'<div>{header_html}</div><br><div>{quote_fragment(mail)}</div>',
                '\n'.join(lines) + '\n\n' + plain)
    attribution = tr('Le {date}, {sender} a écrit :').format(date=mail.date, sender=mail.sender)
    quoted = '\n'.join('> ' + line for line in plain.splitlines())
    return (f'<div>{html.escape(attribution)}</div><blockquote style="{QUOTE_STYLE}">{quote_fragment(mail)}</blockquote>',
            attribution + '\n' + quoted)


def merged(state: dict) -> tuple[str, str]:
    """(texte, HTML) à envoyer : la réponse de l’éditeur, puis la citation mise en forme si elle est incluse."""
    body, document = state.get('body', ''), state.get('mail_html', '')
    if not state.get('quote_html') or not state.get('quote_included', True):
        return body, document
    fragment = state.get('mail_fragment') or ''.join(f'<div>{html.escape(line) or "<br>"}</div>' for line in body.split('\n'))
    return (body.rstrip('\n') + '\n\n' + state.get('quote_text', ''),
            EMAIL_BODY.format(fragment + '<br>' + state['quote_html']))
