"""Désabonnement des listes de diffusion (RFC 2369 et RFC 8058).

Ordre de préférence : désabonnement en un clic (requête POST HTTPS, sans navigateur), puis e-mail
de désabonnement (mailto:), puis page web ouverte dans le navigateur. Rien n’est fait sans confirmation.
"""
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from dataclasses import dataclass

ONE_CLICK_BODY = b'List-Unsubscribe=One-Click'


@dataclass
class Options:
    one_click: str = ''   # URL HTTPS acceptant le POST RFC 8058.
    mailto: tuple = ()    # (adresse, objet, corps)
    web: str = ''         # Page à ouvrir dans le navigateur.

    def __bool__(self):
        return bool(self.one_click or self.mailto or self.web)

    @property
    def host(self) -> str:
        url = self.one_click or self.web
        if url:
            return urllib.parse.urlsplit(url).hostname or ''
        return self.mailto[0].split('@')[-1] if self.mailto else ''


def options(list_unsubscribe: str, list_unsubscribe_post: str = '') -> Options:
    result = Options()
    one_click = ONE_CLICK_BODY.decode().casefold() in (list_unsubscribe_post or '').replace(' ', '').casefold()
    for value in re.findall(r'<([^<>\s]{1,1500})>', list_unsubscribe or ''):
        lowered = value.casefold()
        if lowered.startswith('https://'):
            if one_click and not result.one_click:
                result.one_click = value
            elif not result.web:
                result.web = value
        elif lowered.startswith('http://') and not result.web:
            result.web = value
        elif lowered.startswith('mailto:') and not result.mailto:
            parsed = urllib.parse.urlsplit(value)
            query = urllib.parse.parse_qs(parsed.query)
            address = urllib.parse.unquote(parsed.path)
            if re.fullmatch(r'[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+', address) and address.isascii():
                subject = query.get('subject', ['unsubscribe'])[0][:200]
                body = query.get('body', [''])[0][:2000]
                result.mailto = (address, re.sub(r'[\r\n\x00-\x1f]', ' ', subject) or 'unsubscribe', body)
    return result


def public_host(host: str) -> bool:
    """Refuse les adresses locales ou privées : un message ne doit pas faire viser le réseau de l’utilisateur."""
    if not host or host.casefold() in {'localhost', 'localhost.localdomain'}:
        return False
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)}
    except OSError:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address.split('%')[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Une redirection pourrait viser une autre machine : on s’arrête à la réponse.


def one_click(url: str, timeout: int = 15) -> int:
    """POST RFC 8058, sans cookie ni redirection ; renvoie le code HTTP."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not public_host(parsed.hostname or ''):
        raise RuntimeError('Adresse de désabonnement refusée (HTTPS public requis).')
    request = urllib.request.Request(url, data=ONE_CLICK_BODY, method='POST',
                                     headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'Smail'})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as reply:
            status = reply.status
    except urllib.error.HTTPError as error:
        status = error.code
    if not 200 <= status < 400:
        raise RuntimeError(f'Le serveur de la liste a refusé la demande (HTTP {status}).')
    return status
