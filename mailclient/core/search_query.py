"""Recherche avancée : syntaxe à opérateurs, traduction IMAP SEARCH et filtrage du cache.

Exemples : de:lea objet:"compte rendu" a:pj est:nonlu après:2026-11-01 budget
Opérateurs (français ou anglais) : de:/from:, à:/to:, objet:/subject:, a:pj/has:attachment,
est:nonlu|lu|étoilé / is:unread|read|starred, après:/after:, avant:/before: (AAAA-MM-JJ ou JJ/MM/AAAA).
Un mot sans opérateur, ou une « expression entre guillemets », est cherché dans tout le message.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import parsedate_to_datetime

MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
FIELD_ALIASES = {'de': 'sender', 'from': 'sender', 'à': 'to', 'a': 'to', 'to': 'to', 'pour': 'to',
                 'objet': 'subject', 'subject': 'subject', 'sujet': 'subject'}
HELP = ('Opérateurs : de:nom · à:nom · objet:mot · a:pj · est:nonlu / est:suivi · après:2026-11-01 · avant:01/12/2026 · '
        '"expression exacte"')


@dataclass
class Query:
    words: list = field(default_factory=list)      # Recherchés dans tout le message.
    sender: list = field(default_factory=list)
    to: list = field(default_factory=list)
    subject: list = field(default_factory=list)
    unread: bool | None = None
    starred: bool | None = None
    attachment: bool | None = None
    since: date | None = None                      # Inclus.
    before: date | None = None                     # Exclu (sémantique IMAP BEFORE).

    @property
    def empty(self) -> bool:
        return not (self.words or self.sender or self.to or self.subject) and self.unread is None and \
            self.starred is None and self.attachment is None and self.since is None and self.before is None

    @property
    def text_terms(self) -> list:
        return self.words + self.sender + self.to + self.subject


def parse_date(value: str) -> date | None:
    for pattern in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y'):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def tokens(text: str):
    """(opérateur ou None, valeur) ; les guillemets regroupent une expression, y compris après un opérateur."""
    for match in re.finditer(r'(?:([^\s:"]+):)?(?:"([^"]*)"|(\S+))', text):
        operator, quoted, plain = match[1], match[2], match[3]
        value = quoted if quoted is not None else plain
        if value:
            yield (operator.casefold() if operator else None), value


def parse(text: str) -> Query:
    query = Query()
    for operator, value in tokens((text or '').strip()):
        lowered = value.casefold()
        if operator in {'a', 'has', 'avec'} and lowered in {'pj', 'piècejointe', 'pièce-jointe', 'attachment'}:
            query.attachment = True  # Avant les champs : « a: » sert aussi de « à: » sans accent.
        elif operator in FIELD_ALIASES:
            getattr(query, FIELD_ALIASES[operator]).append(value)
        elif operator in {'est', 'is'} and lowered in {'nonlu', 'non-lu', 'unread'}:
            query.unread = True
        elif operator in {'est', 'is'} and lowered in {'lu', 'read'}:
            query.unread = False
        elif operator in {'est', 'is'} and lowered in {'étoilé', 'etoile', 'étoile', 'starred', 'suivi'}:
            query.starred = True
        elif operator in {'après', 'apres', 'after', 'depuis', 'since'} and parse_date(value):
            query.since = parse_date(value)
        elif operator in {'avant', 'before'} and parse_date(value):
            query.before = parse_date(value)
        else:
            query.words.append(f'{operator}:{value}' if operator else value)
    return query


def imap_date(day: date) -> str:
    return f'{day.day:02d}-{MONTHS[day.month - 1]}-{day.year}'


def quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def imap_commands(query: Query) -> list[tuple[list, bytes | None]]:
    """Commandes UID SEARCH à croiser : (arguments, littéral UTF-8 ou None).

    imaplib n’envoie qu’un littéral par commande : chaque texte non ASCII a sa propre recherche.
    Les textes ASCII et les critères simples sont regroupés dans une première commande."""
    base = ['UNDELETED']
    if query.unread is True:
        base.append('UNSEEN')
    elif query.unread is False:
        base.append('SEEN')
    if query.starred:
        base.append('FLAGGED')
    if query.since:
        base += ['SINCE', imap_date(query.since)]
    if query.before:
        base += ['BEFORE', imap_date(query.before)]
    commands, extra = [], []
    for key, values in (('TEXT', query.words), ('FROM', query.sender), ('TO', query.to), ('SUBJECT', query.subject)):
        for value in values:
            if value.isascii() and not any(c in value for c in '\r\n\x00'):
                base += [key, quote(value)]
            else:
                extra.append(([key], value.replace('\r', ' ').replace('\n', ' ').encode('utf-8')))
    commands.append((base, None))
    commands.extend(extra)
    return commands


def row_date(row) -> date | None:
    try:
        return parsedate_to_datetime(row.get('date', '')).astimezone().date()
    except (TypeError, ValueError, OverflowError):
        return None


def matches(query: Query, row: dict, content=None) -> bool:
    """Filtre hors ligne ; content() renvoie le texte complet du message (ou None s’il n’est pas en cache)."""
    def contains(value, haystack):
        return value.casefold() in (haystack or '').casefold()
    if query.unread is not None and bool(row.get('unread')) != query.unread:
        return False
    if query.starred and not row.get('starred'):
        return False
    if query.attachment and not row.get('attachment'):
        return False
    day = row_date(row)
    if (query.since or query.before) and day is None:
        return False
    if query.since and day < query.since:
        return False
    if query.before and day >= query.before:
        return False
    if not all(contains(value, row.get('sender', '')) for value in query.sender):
        return False
    if not all(contains(value, row.get('recipients', '')) for value in query.to):
        return False
    if not all(contains(value, row.get('subject', '')) for value in query.subject):
        return False
    if query.words:
        header = ' '.join((row.get('sender', ''), row.get('recipients', ''), row.get('subject', '')))
        missing = [word for word in query.words if not contains(word, header)]
        if missing:
            text = content() if content else None
            if text is None or not all(contains(word, text) for word in missing):
                return False
    return True
