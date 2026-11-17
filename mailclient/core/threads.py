"""Regroupement des messages en conversations (inspiré de l’algorithme de J. Zawinski, simplifié).

Les messages sont reliés par Message-ID, In-Reply-To et References ; deux comptes ne sont jamais
mélangés. Un repli sur le sujet ne concerne que les réponses (« Re: », « Tr: »…) dépourvues de
références, comme en produisent certains clients mobiles ou webmails.
"""
import re
from email.utils import parsedate_to_datetime

REPLY_PREFIX = re.compile(r'^\s*(?:(?:re|tr|fw|fwd|aw|sv|rv|wg|réf|ref)\s*(?:\[\d+\])?\s*:\s*)+', re.IGNORECASE)
MIN_SUBJECT = 5  # Un sujet trop court (« Re: ok ») ne suffit pas à rapprocher deux messages.


def normalize_subject(subject: str) -> str:
    return ' '.join(REPLY_PREFIX.sub('', subject or '').split()).casefold()


def is_reply_subject(subject: str) -> bool:
    return bool(REPLY_PREFIX.match(subject or ''))


def row_ids(row) -> tuple[str, list[str]]:
    """(Message-ID, identifiants référencés) d’une ligne de liste."""
    references = (row.get('references') or '').split() + (row.get('in_reply_to') or '').split()
    return (row.get('message_id') or ''), references


def group_threads(rows: list[dict]) -> list[list[dict]]:
    """Conversations dans l’ordre de la liste : chacune est placée au rang de son message le mieux classé
    (le plus récent pour une liste triée du plus récent au plus ancien) et garde cet ordre en interne."""
    parent: dict = {}

    def find(node):
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:
            parent[node], node = root, parent[node]
        return root

    def union(a, b):
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb, key=str)] = min(ra, rb, key=str)

    by_subject: dict = {}
    for index, row in enumerate(rows):
        node = ('row', index)
        parent.setdefault(node, node)
        account = row.get('account', '')
        own, references = row_ids(row)
        for value in ([own] if own else []) + references:
            union(node, ('id', account, value))
        subject = normalize_subject(row.get('subject', ''))
        if len(subject) >= MIN_SUBJECT:
            by_subject.setdefault((account, subject), []).append(index)
    for index, row in enumerate(rows):
        own, references = row_ids(row)
        if references or not is_reply_subject(row.get('subject', '')):
            continue
        key = (row.get('account', ''), normalize_subject(row.get('subject', '')))
        other = next((candidate for candidate in by_subject.get(key, []) if candidate != index), None)
        if other is not None:
            union(('row', index), ('row', other))
    groups: dict = {}
    for index in range(len(rows)):
        groups.setdefault(find(('row', index)), []).append(index)
    ordered = sorted(groups.values(), key=lambda members: members[0])
    return [[rows[index] for index in members] for members in ordered]


def timestamp(row) -> float:
    try:
        return parsedate_to_datetime(row.get('date', '')).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def chronological(rows: list[dict]) -> list[dict]:
    """Messages d’une conversation du plus ancien au plus récent ; dates illisibles conservées en tête."""
    return sorted(rows, key=lambda row: (timestamp(row), int(row['uid']) if str(row.get('uid', '')).isdigit() else 0))


def thread_ids(rows: list[dict]) -> set[str]:
    ids = set()
    for row in rows:
        own, references = row_ids(row)
        ids.update(([own] if own else []) + references)
    return ids
