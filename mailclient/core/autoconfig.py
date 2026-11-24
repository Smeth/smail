"""Détection automatique des réglages IMAP/SMTP à partir de l’adresse e-mail.

Sources, dans l’ordre (la première qui répond l’emporte) :
1. fournisseurs connus, sans réseau ;
2. fichier de réglages publié par le domaine en HTTPS (format « autoconfig » de Thunderbird, que cPanel publie) ;
3. base publique de Thunderbird (ISPDB), en HTTPS ;
4. fichier du domaine en HTTP, accepté seulement si les serveurs annoncés sont dans le domaine de l’adresse :
   en HTTP, un tiers sur le réseau pourrait sinon désigner son propre serveur et recevoir le mot de passe ;
5. noms habituels (mail., imap., smtp.) dont le port chiffré répond.

Seul le nom de domaine est transmis, jamais l’adresse complète. Les connexions sans chiffrement ne sont jamais proposées.
La vérification TLS des serveurs reste faite à la connexion, comme pour une saisie manuelle."""
import re
import socket
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from mailclient.core.accounts import Server

ISPDB = 'https://autoconfig.thunderbird.net/v1.1/{domain}'
TIMEOUT = 6
MAX_SIZE = 64 * 1024
HOSTNAME = re.compile(r'[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+')
SOCKETS = {'SSL': 'SSL/TLS', 'STARTTLS': 'STARTTLS'}  # « plain » : jamais proposé.
KNOWN = {
    'gmail.com': ('imap.gmail.com', 'smtp.gmail.com'), 'googlemail.com': ('imap.gmail.com', 'smtp.gmail.com'),
    'outlook.com': ('outlook.office365.com', 'smtp.office365.com'), 'outlook.fr': ('outlook.office365.com', 'smtp.office365.com'),
    'hotmail.com': ('outlook.office365.com', 'smtp.office365.com'), 'hotmail.fr': ('outlook.office365.com', 'smtp.office365.com'),
    'live.com': ('outlook.office365.com', 'smtp.office365.com'), 'live.fr': ('outlook.office365.com', 'smtp.office365.com'),
    'msn.com': ('outlook.office365.com', 'smtp.office365.com'),
    'yahoo.com': ('imap.mail.yahoo.com', 'smtp.mail.yahoo.com'), 'yahoo.fr': ('imap.mail.yahoo.com', 'smtp.mail.yahoo.com'),
    'icloud.com': ('imap.mail.me.com', 'smtp.mail.me.com'), 'me.com': ('imap.mail.me.com', 'smtp.mail.me.com'),
}
# Ports d’envoi en STARTTLS pour ces fournisseurs ; 465 (SSL/TLS) sinon.
STARTTLS_SMTP = {'smtp.office365.com', 'smtp.mail.me.com', 'smtp.gmail.com'}


@dataclass
class Detected:
    imap: Server
    smtp: Server
    source: str              # Texte affiché : « fournisseur connu », « votre hébergeur »…
    imap_login: str = ''     # Vide : l’adresse e-mail sert d’identifiant.
    smtp_login: str = ''


def domain_of(address: str) -> str:
    domain = address.strip().lower().rpartition('@')[2]
    return domain if HOSTNAME.fullmatch(domain or '') else ''


def known(address: str) -> Detected | None:
    hosts = KNOWN.get(domain_of(address))
    if not hosts:
        return None
    smtp = Server(hosts[1], 587, 'STARTTLS') if hosts[1] in STARTTLS_SMTP else Server(hosts[1], 465, 'SSL/TLS')
    return Detected(Server(hosts[0], 993, 'SSL/TLS'), smtp, 'fournisseur connu')


def fetch(url: str, opener=None) -> bytes | None:
    request = urllib.request.Request(url, headers={'User-Agent': 'Smail', 'Accept': 'application/xml, text/xml'})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=TIMEOUT) as response:
            data = response.read(MAX_SIZE + 1)
    except (OSError, ValueError):
        return None
    return data if len(data) <= MAX_SIZE else None


def login_for(template: str, address: str) -> str | None:
    """Identifiant annoncé : '' pour l’adresse complète, la partie locale, ou None si non pris en charge."""
    template = (template or '%EMAILADDRESS%').strip()
    if template == '%EMAILADDRESS%':
        return ''
    if template == '%EMAILLOCALPART%':
        return address.strip().partition('@')[0]
    return None


def best(servers, kind: str, address: str):
    """Premier serveur chiffré du type voulu (SSL/TLS préféré à STARTTLS)."""
    candidates = []
    for server in servers:
        if server.get('type') != kind:
            continue
        host = (server.findtext('hostname') or '').strip().lower()
        mode = SOCKETS.get((server.findtext('socketType') or '').strip().upper())
        login = login_for(server.findtext('username'), address)
        try:
            port = int(server.findtext('port') or 0)
        except ValueError:
            continue
        if mode and login is not None and HOSTNAME.fullmatch(host) and 0 < port < 65536:
            candidates.append((mode != 'SSL/TLS', Server(host, port, mode), login))
    return min(candidates, key=lambda item: item[0])[1:] if candidates else None


def parse(data: bytes, address: str, source: str) -> Detected | None:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    provider = root.find('emailProvider')
    if provider is None:
        return None
    imap = best(provider.findall('incomingServer'), 'imap', address)
    smtp = best(provider.findall('outgoingServer'), 'smtp', address)
    if not imap or not smtp:
        return None
    return Detected(imap[0], smtp[0], source, imap[1], smtp[1])


def in_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith('.' + domain)


def guess(domain: str, connect=socket.create_connection) -> Detected | None:
    """Noms habituels : un serveur dont le port chiffré accepte la connexion."""
    def open_port(host, port):
        try:
            connect((host, port), timeout=4).close()
            return True
        except OSError:
            return False
    imap = next((Server(host, 993, 'SSL/TLS') for host in (f'mail.{domain}', f'imap.{domain}') if open_port(host, 993)), None)
    if imap is None:
        return None
    for host in dict.fromkeys((imap.host, f'smtp.{domain}')):
        for port, mode in ((465, 'SSL/TLS'), (587, 'STARTTLS')):
            if open_port(host, port):
                return Detected(imap, Server(host, port, mode), 'noms de serveurs habituels (à vérifier)')
    return None


def detect(address: str, opener=None, connect=socket.create_connection) -> Detected | None:
    """Réglages trouvés pour cette adresse, ou None (saisie manuelle). Bloquant : à appeler hors de l’interface."""
    domain = domain_of(address)
    if not domain:
        return None
    found = known(address)
    if found:
        return found
    for url, source in ((f'https://autoconfig.{domain}/mail/config-v1.1.xml', 'votre hébergeur'),
                        (f'https://{domain}/.well-known/autoconfig/mail/config-v1.1.xml', 'votre hébergeur'),
                        (ISPDB.format(domain=domain), 'base publique de Thunderbird')):
        data = fetch(url, opener)
        found = parse(data, address, source) if data else None
        if found:
            return found
    data = fetch(f'http://autoconfig.{domain}/mail/config-v1.1.xml', opener)
    found = parse(data, address, 'votre hébergeur') if data else None
    if found and in_domain(found.imap.host, domain) and in_domain(found.smtp.host, domain):
        return found
    return guess(domain, connect)
