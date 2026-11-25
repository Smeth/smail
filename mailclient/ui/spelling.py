"""Correcteur d’orthographe de la rédaction : fautes soulignées en rouge, suggestions au clic droit.

Dictionnaire français de pyspellchecker (local, aucune connexion). Ne sont jamais signalés : les mots avec
majuscule (noms propres, sigles), les mots de moins de trois lettres, les adresses e-mail et les liens, les mots
ajoutés au dictionnaire personnel (Préférences enregistrées dans la base locale)."""
import re

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor

LETTERS = 'A-Za-zÀ-ÖØ-öø-ÿŒœÆæ'
WORD = re.compile(rf"[{LETTERS}]+(?:['’][{LETTERS}]+)*(?:-[{LETTERS}]+)*")
SKIP = re.compile(r'\S+@\S+|(?:https?://|www\.)\S+')            # Adresses et liens : jamais vérifiés.
ELISIONS = {'l', 'd', 'j', 'm', 't', 's', 'n', 'c', 'qu', 'jusqu', 'lorsqu', 'puisqu', 'quoiqu'}
SETTING = 'spelling_words'


class Speller:
    def __init__(self, database=None, language='fr'):
        self.database = database
        self.checker = None
        self.cache = {}
        try:
            from spellchecker import SpellChecker
            self.checker = SpellChecker(language=language)
        except Exception:  # Bibliothèque absente : la rédaction fonctionne sans correcteur.
            self.checker = None
        self.personal = set(database.setting(SETTING, []) or []) if database is not None else set()

    @property
    def available(self):
        return self.checker is not None

    def known_word(self, word: str) -> bool:
        lower = word.casefold().replace('’', "'")
        if lower in self.personal or lower in self.checker:
            return True
        if "'" in lower:  # « l’entreprise », « aujourd’hui », « qu’il » : élision puis mot connu.
            prefix, _, rest = lower.partition("'")
            if prefix in ELISIONS and (rest in self.checker or rest in self.personal):
                return True
        if '-' in lower:  # « peut-être », « rendez-vous » : chaque partie connue.
            return all(part in self.checker or part in self.personal for part in lower.split('-') if part)
        return False

    def correct(self, word: str) -> bool:
        if not self.available or len(word) < 3 or word[0].isupper() or word.isupper():
            return True
        if word not in self.cache:
            self.cache[word] = self.known_word(word)
        return self.cache[word]

    def errors(self, text: str):
        """(début, longueur) des mots inconnus dans le texte."""
        skipped = [match.span() for match in SKIP.finditer(text)]
        for match in WORD.finditer(text):
            if any(start <= match.start() < end for start, end in skipped):
                continue
            if not self.correct(match.group()):
                yield match.start(), len(match.group())

    def suggestions(self, word: str, limit=6) -> list:
        if not self.available:
            return []
        lower = word.casefold().replace('’', "'")
        candidates = self.checker.candidates(lower) or set()
        best = self.checker.correction(lower)
        ordered = ([best] if best in candidates else []) + sorted(candidates - {best}, key=lambda w: -self.checker.word_frequency[w])
        return [w for w in ordered if w != lower][:limit]

    def add(self, word: str):
        self.personal.add(word.casefold().replace('’', "'"))
        self.cache.clear()
        if self.database is not None:
            self.database.set_setting(SETTING, sorted(self.personal))


class SpellHighlighter(QSyntaxHighlighter):
    def __init__(self, document, speller: Speller):
        super().__init__(document)
        self.speller = speller
        self.format = QTextCharFormat()
        self.format.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
        self.format.setUnderlineColor(QColor('#E5484D'))

    def highlightBlock(self, text):
        # Format ajouté par-dessus la mise en forme du texte (gras, liens…) : seul le soulignement change.
        for start, length in self.speller.errors(text):
            self.setFormat(start, length, self.format)


def word_at(editor, position):
    """(curseur sélectionnant le mot, mot) sous la position du clic droit, ou (None, '')."""
    cursor = editor.cursorForPosition(position)
    block = cursor.block().text()
    column = cursor.positionInBlock()
    for match in WORD.finditer(block):
        if match.start() <= column <= match.end():
            selection = QTextCursor(cursor.block())
            selection.setPosition(cursor.block().position() + match.start())
            selection.setPosition(cursor.block().position() + match.end(), QTextCursor.KeepAnchor)
            return selection, match.group()
    return None, ''


def add_suggestions(editor, speller: Speller, menu, position):
    """En tête du menu contextuel : suggestions, « Ajouter au dictionnaire »."""
    if not speller.available:
        return
    selection, word = word_at(editor, position)
    if not word or speller.correct(word):
        return
    first = menu.actions()[0] if menu.actions() else None
    suggestions = speller.suggestions(word)
    for suggestion in suggestions:
        action = menu.addAction(suggestion)
        action.triggered.connect(lambda checked=False, s=suggestion, c=selection: c.insertText(s))
        menu.insertAction(first, action)
    if not suggestions:
        empty = menu.addAction('Aucune suggestion')
        empty.setEnabled(False)
        menu.insertAction(first, empty)
    add = menu.addAction(f'Ajouter « {word} » au dictionnaire')
    add.triggered.connect(lambda: (speller.add(word), editor.spell_highlighter.rehighlight()))
    menu.insertAction(first, add)
    menu.insertSeparator(first)


def install(editor, database=None):
    """Active le correcteur sur un éditeur de texte (QTextEdit) ; sans effet si la bibliothèque manque."""
    speller = Speller(database)
    editor.speller = speller
    editor.spell_highlighter = SpellHighlighter(editor.document(), speller) if speller.available else None
    return speller


def context_menu(editor, event):
    menu = editor.createStandardContextMenu(event.pos())
    speller = getattr(editor, 'speller', None)
    if speller is not None:
        add_suggestions(editor, speller, menu, event.pos())
    menu.exec(event.globalPos())
    menu.deleteLater()



