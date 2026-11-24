"""Invitations de calendrier (iCalendar RFC 5545, iTIP RFC 5546) : lecture et réponse.

Smail ne gère pas d’agenda : il lit l’invitation reçue et renvoie à l’organisateur une réponse
standard (METHOD:REPLY) que comprennent Outlook, Google Agenda, Thunderbird ou Apple Calendrier.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from email.utils import parseaddr
from uuid import uuid4

LIMIT = 300_000  # Au-delà, ce n’est pas une invitation ordinaire.
PARTSTAT = {'ACCEPTED': 'Accepté', 'TENTATIVE': 'Provisoire', 'DECLINED': 'Refusé'}
# Noms de fuseaux Windows (Outlook) les plus courants → IANA.
WINDOWS_ZONES = {
    'Romance Standard Time': 'Europe/Paris', 'W. Europe Standard Time': 'Europe/Berlin',
    'Central Europe Standard Time': 'Europe/Budapest', 'Central European Standard Time': 'Europe/Warsaw',
    'GMT Standard Time': 'Europe/London', 'Greenwich Standard Time': 'Atlantic/Reykjavik', 'UTC': 'UTC',
    'E. Europe Standard Time': 'Europe/Chisinau', 'FLE Standard Time': 'Europe/Kiev', 'GTB Standard Time': 'Europe/Bucharest',
    'Morocco Standard Time': 'Africa/Casablanca', 'W. Central Africa Standard Time': 'Africa/Lagos',
    'South Africa Standard Time': 'Africa/Johannesburg', 'Egypt Standard Time': 'Africa/Cairo',
    'Eastern Standard Time': 'America/New_York', 'Central Standard Time': 'America/Chicago',
    'Mountain Standard Time': 'America/Denver', 'Pacific Standard Time': 'America/Los_Angeles',
    'Canada Central Standard Time': 'America/Regina', 'Atlantic Standard Time': 'America/Halifax',
    'Tokyo Standard Time': 'Asia/Tokyo', 'China Standard Time': 'Asia/Shanghai', 'India Standard Time': 'Asia/Kolkata',
    'Arabian Standard Time': 'Asia/Dubai', 'AUS Eastern Standard Time': 'Australia/Sydney',
}


@dataclass
class Invite:
    method: str = ''
    uid: str = ''
    summary: str = ''
    location: str = ''
    description: str = ''
    sequence: str = '0'
    start: object = None      # datetime (avec fuseau), date (journée entière) ou None
    end: object = None
    start_label: str = ''     # Texte affiché quand le fuseau est inconnu.
    organizer: str = ''       # Adresse e-mail
    organizer_name: str = ''
    attendees: list = field(default_factory=list)  # [(adresse, nom, partstat)]
    raw_props: dict = field(default_factory=dict)  # Lignes d’origine renvoyées dans la réponse.

    @property
    def cancelled(self) -> bool:
        return self.method == 'CANCEL'

    @property
    def answerable(self) -> bool:
        return self.method == 'REQUEST' and bool(self.uid) and bool(self.organizer)


def unfold(text: str) -> list[str]:
    return re.sub(r'\r?\n[ \t]', '', text).replace('\r\n', '\n').split('\n')


def split_line(line: str):
    """« NOM;PARAM=x;PARAM2="y":valeur » → (NOM, {PARAM: x}, valeur)."""
    match = re.match(r'^([A-Za-z0-9-]+)((?:;[^:;]+=(?:"[^"]*"|[^:;]*))*):(.*)$', line)
    if not match:
        return None
    params = {key.upper(): value.strip('"') for key, value in re.findall(r';([^=;:]+)=("[^"]*"|[^;:]*)', match[2])}
    return match[1].upper(), params, match[3]


def unescape(value: str) -> str:
    return value.replace('\\n', '\n').replace('\\N', '\n').replace('\\,', ',').replace('\\;', ';').replace('\\\\', '\\')


def zone(name: str):
    from zoneinfo import ZoneInfo
    for candidate in (name, WINDOWS_ZONES.get(name, '')):
        if candidate:
            try:
                return ZoneInfo(candidate)
            except Exception:
                continue
    return None


def parse_time(value: str, params: dict):
    """(moment, libellé de repli) ; journée entière → date."""
    value = value.strip()
    try:
        if params.get('VALUE') == 'DATE' or re.fullmatch(r'\d{8}', value):
            return datetime.strptime(value[:8], '%Y%m%d').date(), ''
        moment = datetime.strptime(value.rstrip('Z'), '%Y%m%dT%H%M%S')
    except ValueError:
        return None, value
    if value.endswith('Z'):
        return moment.replace(tzinfo=timezone.utc), ''
    tzid = params.get('TZID', '')
    tz = zone(tzid) if tzid else None
    if tz is not None:
        return moment.replace(tzinfo=tz), ''
    if tzid:
        return None, f'{moment:%d/%m/%Y %H:%M} (fuseau « {tzid} »)'
    return moment.astimezone(), ''  # Heure flottante : heure locale.


def parse(data: bytes) -> Invite | None:
    if not data or len(data) > LIMIT:
        return None
    text = data.decode('utf-8', errors='replace')
    if 'BEGIN:VCALENDAR' not in text.upper():
        return None
    invite, in_event, depth = Invite(), False, 0
    for line in unfold(text):
        parsed = split_line(line.strip('\r'))
        if not parsed:
            continue
        name, params, value = parsed
        if name == 'METHOD' and not in_event:
            invite.method = value.strip().upper()
        elif name == 'BEGIN':
            if value.upper() == 'VEVENT' and not invite.uid:
                in_event, depth = True, 0
            elif in_event:
                depth += 1  # VALARM imbriqué : ignoré.
        elif name == 'END':
            if in_event and depth:
                depth -= 1
            elif in_event and value.upper() == 'VEVENT':
                break  # Seul le premier événement est lu.
        elif in_event and not depth:
            if name in {'UID', 'DTSTART', 'DTEND', 'ORGANIZER', 'SEQUENCE', 'RECURRENCE-ID'}:
                invite.raw_props[name] = line.strip('\r')
            if name == 'UID':
                invite.uid = value.strip()
            elif name == 'SUMMARY':
                invite.summary = unescape(value)[:300]
            elif name == 'LOCATION':
                invite.location = unescape(value)[:300]
            elif name == 'DESCRIPTION':
                invite.description = unescape(value)[:2000]
            elif name == 'SEQUENCE' and value.strip().isdigit():
                invite.sequence = value.strip()
            elif name == 'DTSTART':
                invite.start, invite.start_label = parse_time(value, params)
            elif name == 'DTEND':
                invite.end, _ = parse_time(value, params)
            elif name == 'ORGANIZER':
                invite.organizer = mailto(value)
                invite.organizer_name = params.get('CN', '')[:200]
            elif name == 'ATTENDEE':
                address = mailto(value)
                if address:
                    invite.attendees.append((address, params.get('CN', '')[:200], params.get('PARTSTAT', 'NEEDS-ACTION').upper()))
    return invite if invite.uid or invite.summary else None


def mailto(value: str) -> str:
    address = re.sub(r'(?i)^mailto:', '', value.strip())
    address = parseaddr(address)[1]
    return address if re.fullmatch(r'[^\s@<>,;"]+@[^\s@<>,;"]+\.[^\s@<>,;"]+', address) and address.isascii() else ''


def find(mail) -> tuple[Invite | None, object]:
    """Première invitation lisible du message, et la pièce jointe d’où elle vient."""
    for attachment in mail.attachments:
        if attachment.content_type.lower() == 'text/calendar' or attachment.name.lower().endswith('.ics'):
            invite = parse(attachment.data)
            if invite:
                return invite, attachment
    return None, None


def when(invite: Invite) -> str:
    """Date lisible, en heure locale."""
    days = ('lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.', 'dim.')
    start, end = invite.start, invite.end
    if start is None:
        return invite.start_label or 'date non précisée'
    if isinstance(start, date) and not isinstance(start, datetime):
        return f'{days[start.weekday()]} {start:%d/%m/%Y}, journée entière'
    start = start.astimezone()
    text = f'{days[start.weekday()]} {start:%d/%m/%Y} à {start:%H:%M}'
    if isinstance(end, datetime):
        end = end.astimezone()
        text += f' – {end:%H:%M}' if end.date() == start.date() else f' – {days[end.weekday()]} {end:%d/%m %H:%M}'
    return text


def escape(value: str) -> str:
    value = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', value)
    return value.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def fold(line: str) -> str:
    """Lignes de 75 octets au plus (RFC 5545), sans couper un caractère multi-octet."""
    out, current = [], ''
    for char in line:
        if len((current + char).encode('utf-8')) > (75 if not out else 74):
            out.append(current)
            current = ''
        current += char
    out.append(current)
    return '\r\n '.join(out)


def reply(invite: Invite, account, partstat: str) -> str:
    """Réponse iTIP METHOD:REPLY pour ce compte."""
    if partstat not in PARTSTAT or not invite.answerable:
        raise ValueError('Cette invitation ne peut pas recevoir de réponse.')
    me = next((entry for entry in invite.attendees if entry[0].casefold() == account.email.casefold()), None)
    name = (me[1] if me and me[1] else account.name) or account.email
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'PRODID:-//Smail//Invitations//FR', 'VERSION:2.0', 'METHOD:REPLY', 'BEGIN:VEVENT']
    for key in ('UID', 'RECURRENCE-ID', 'SEQUENCE', 'DTSTART', 'DTEND', 'ORGANIZER'):
        if key in invite.raw_props:
            lines.append(re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', invite.raw_props[key]))
    lines += [f'DTSTAMP:{stamp}',
              f'ATTENDEE;PARTSTAT={partstat};CN="{name.replace(chr(34), "")}":mailto:{account.email}',
              f'SUMMARY:{escape(PARTSTAT[partstat] + " : " + (invite.summary or "invitation"))}',
              'END:VEVENT', 'END:VCALENDAR']
    return '\r\n'.join(fold(line) for line in lines) + '\r\n'


def response_state(invite: Invite, account, partstat: str) -> dict:
    """Message de réponse, au format des états d’envoi de Smail (scheduler.send_and_record)."""
    label = PARTSTAT[partstat]
    subject = f'{label} : {invite.summary or "invitation"}'
    body = f'{account.name or account.email} a répondu « {label} » à l’invitation « {invite.summary or "sans titre"} » ({when(invite)}).'
    return dict(to=invite.organizer, cc='', bcc='', subject=subject.replace('\n', ' ')[:250], body=body, mail_html='',
                reply_id='', references='', calendar=reply(invite, account, partstat), id=str(uuid4()))
