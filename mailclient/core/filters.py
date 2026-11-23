"""Règles de tri, expéditeurs bloqués ou approuvés et détection du spam signalé par le serveur.

Module sans Qt ni réseau : il décide, le service applique. Les réglages sont conservés dans le cache
(chiffré avec lui), car les listes d’expéditeurs sont des données personnelles.
"""
import re
from email.utils import getaddresses, parseaddr
from uuid import uuid4

FIELDS = {'from': 'De', 'to': 'À ou Cc', 'subject': 'Objet', 'any': 'De, À, Cc ou objet'}
OPERATORS = {'contains': 'contient', 'is': 'est exactement', 'ends': 'se termine par'}
ACTIONS = {'move': 'Déplacer vers', 'read': 'Marquer comme lu', 'star': 'Étoiler', 'trash': 'Mettre à la corbeille',
           'junk': 'Déplacer vers les indésirables'}
JUNK_WORDS = ('spam', 'junk', 'indésirable', 'courrier indésirable', 'bulk')
TRASH_WORDS = ('corbeille', 'trash', 'deleted', 'éléments supprimés')
DEFAULTS = dict(rules=[], blocked=[], safe=[], spam_headers=True)


def load(db) -> dict:
    data = db.cache_get('filters', 'global') or {}
    return {**DEFAULTS, **{key: value for key, value in data.items() if key in DEFAULTS}}


def save(db, data: dict) -> None:
    db.cache_put('filters', 'global', {key: data.get(key, DEFAULTS[key]) for key in DEFAULTS})


def new_rule(**values) -> dict:
    rule = dict(id=uuid4().hex, name='', enabled=True, account='', field='from', op='contains', value='', action='move', target='')
    rule.update(values)
    return validate_rule(rule)


def validate_rule(rule: dict) -> dict:
    if rule['field'] not in FIELDS or rule['op'] not in OPERATORS or rule['action'] not in ACTIONS:
        raise ValueError('Règle incomplète.')
    rule['value'] = rule['value'].strip()
    if not rule['value'] or len(rule['value']) > 300 or any(ord(c) < 32 for c in rule['value']):
        raise ValueError('Saisissez le texte à rechercher (300 caractères au plus).')
    if rule['action'] == 'move' and not rule.get('target'):
        raise ValueError('Choisissez le dossier de destination.')
    rule['name'] = (rule.get('name') or '').strip()[:120] or describe(rule)
    return rule


def describe(rule: dict) -> str:
    action = ACTIONS[rule['action']].lower() + (f' « {rule["target"]} »' if rule['action'] == 'move' else '')
    return f'Si {FIELDS[rule["field"]]} {OPERATORS[rule["op"]]} « {rule["value"]} » : {action}'


def normalize_sender(value: str) -> str:
    """Adresse complète, ou domaine écrit « @exemple.fr » / « exemple.fr »."""
    value = parseaddr(value)[1] or value
    value = value.strip().casefold()
    if not value or len(value) > 254 or any(c in value for c in ' <>,;"\'') or any(ord(c) < 33 for c in value):
        raise ValueError('Adresse ou domaine invalide.')
    if '@' not in value:
        value = '@' + value
    if not re.fullmatch(r'[^@\s]*@[^@\s]+\.[^@\s]+', value):
        raise ValueError('Adresse ou domaine invalide.')
    return value


def sender_in(address: str, entries) -> bool:
    address = address.casefold()
    return any(address == entry or (entry.startswith('@') and address.endswith(entry)) for entry in entries)


def server_flagged_spam(row: dict) -> bool:
    return bool(row.get('spam'))


def _matches(rule: dict, row: dict) -> bool:
    value = rule['value'].casefold()
    sender = row.get('sender', '')
    recipients = row.get('recipients', '')
    if rule['field'] == 'from':
        haystacks = [sender] + [address for _, address in getaddresses([sender])]
    elif rule['field'] == 'to':
        haystacks = [recipients] + [address for _, address in getaddresses([recipients])]
    elif rule['field'] == 'subject':
        haystacks = [row.get('subject', '')]
    else:
        haystacks = [sender, recipients, row.get('subject', '')]
    haystacks = [item.casefold() for item in haystacks if item]
    if rule['op'] == 'contains':
        return any(value in item for item in haystacks)
    if rule['op'] == 'is':
        return any(value == item.strip() for item in haystacks)
    return any(item.strip().endswith(value) for item in haystacks)


def decide(row: dict, data: dict, account_id: str):
    """Action pour un message de la réception : (action, cible, motif) ou None."""
    address = parseaddr(row.get('sender', ''))[1]
    trusted = bool(address) and sender_in(address, data.get('safe', []))
    if not trusted:
        if address and sender_in(address, data.get('blocked', [])):
            return 'junk', '', 'expéditeur bloqué'
        if data.get('spam_headers', True) and server_flagged_spam(row):
            return 'junk', '', 'signalé comme spam par le serveur'
    for rule in data.get('rules', []):
        if rule.get('enabled', True) and rule.get('account') in ('', account_id) and _matches(rule, row):
            return rule['action'], rule.get('target', ''), f'règle « {rule["name"]} »'
    return None


def special_folder(folders, words, exclude='') -> str | None:
    """Dossier spécial (indésirables, corbeille) d’après son libellé ou son nom."""
    return next((name for name, label in folders if name != exclude and any(word in (name + ' ' + label).casefold() for word in words)), None)
