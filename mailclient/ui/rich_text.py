"""Rédaction en texte enrichi : éditeur, barre de mise en forme et conversion vers un HTML d’e-mail minimal.

Le HTML envoyé n’est jamais celui de Qt (toHtml), verbeux et chargé de styles : il est reconstruit
à partir du document, avec un ensemble fermé de balises (div, br, b, i, u, a, ul, ol, li, h1-h3).
Chaque texte est échappé et seuls les liens http, https et mailto sont conservés.
"""
from mailclient.i18n import tr, N_
import html
import re
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import (QFont, QKeySequence, QPalette, QShortcut, QTextCharFormat, QTextCursor, QTextDocument,
                           QTextListFormat)
from PySide6.QtWidgets import QApplication, QHBoxLayout, QInputDialog, QMessageBox, QTextEdit, QWidget
from mailclient.ui.components import Button

SAFE_LINK = re.compile(r'^(?:https?://[^\s<>"]+|mailto:[^\s<>"]+)$', re.IGNORECASE)
ORDERED = {QTextListFormat.Style.ListDecimal, QTextListFormat.Style.ListLowerAlpha, QTextListFormat.Style.ListUpperAlpha,
           QTextListFormat.Style.ListLowerRoman, QTextListFormat.Style.ListUpperRoman}
from mailclient.core.quote import EMAIL_BODY  # noqa: E402  (même enveloppe pour la réponse et la citation)


def _inline(block):
    """(HTML, texte) d’un paragraphe ; retours à la ligne (Maj+Entrée) conservés, objets (images) ignorés."""
    parts_html, parts_text = [], []
    it = block.begin()
    while not it.atEnd():
        fragment = it.fragment()
        it += 1
        if not fragment.isValid():
            continue
        raw = fragment.text().replace('￼', '')
        if not raw:
            continue
        fmt = fragment.charFormat()
        piece = html.escape(raw, quote=False).replace(' ', '<br>')
        text = raw.replace(' ', '\n')
        href = fmt.anchorHref().strip() if fmt.isAnchor() else ''
        if fmt.fontUnderline() and not href:
            piece = f'<u>{piece}</u>'
        if fmt.fontItalic():
            piece = f'<i>{piece}</i>'
        if fmt.fontWeight() >= QFont.Weight.DemiBold.value:
            piece = f'<b>{piece}</b>'
        if href and SAFE_LINK.match(href):
            piece = f'<a href="{html.escape(href, quote=True)}">{piece}</a>'
            if raw.strip() != href and raw.strip() != href.removeprefix('mailto:'):
                text = f'{raw} ({href.removeprefix("mailto:")})'
        parts_html.append(piece)
        parts_text.append(text)
    return ''.join(parts_html), ''.join(parts_text)


def render(document: QTextDocument) -> tuple[str, str]:
    """(fragment HTML d’e-mail, texte brut équivalent) d’un document Qt."""
    out_html, out_text = [], []
    current = None  # (index de liste, balise)
    block = document.begin()
    while block.isValid():
        text_list = block.textList()
        key = (text_list.objectIndex(), 'ol' if text_list.format().style() in ORDERED else 'ul') if text_list else None
        if current and key != current:
            out_html.append(f'</{current[1]}>')
            current = None
        if key and not current:
            out_html.append(f'<{key[1]} style="margin: 4px 0 4px 22px; padding: 0;">')
            current = key
        inline_html, inline_text = _inline(block)
        level = block.blockFormat().headingLevel()
        if key:
            out_html.append(f'<li>{inline_html or "<br>"}</li>')
            marker = f'{text_list.itemNumber(block) + 1}. ' if key[1] == 'ol' else '• '
            out_text.append(marker + inline_text)
        elif 1 <= level <= 3:
            out_html.append(f'<h{level}>{inline_html}</h{level}>')
            out_text.append(inline_text)
        else:
            out_html.append(f'<div>{inline_html or "<br>"}</div>')
            out_text.append(inline_text)
        block = block.next()
    if current:
        out_html.append(f'</{current[1]}>')
    return ''.join(out_html), '\n'.join(out_text)


def has_formatting(document: QTextDocument) -> bool:
    """Vrai si le document contient du gras, de l’italique, du souligné, un lien, une liste ou un titre."""
    block = document.begin()
    while block.isValid():
        if block.textList() or block.blockFormat().headingLevel():
            return True
        it = block.begin()
        while not it.atEnd():
            fmt = it.fragment().charFormat()
            it += 1
            if fmt.fontWeight() >= QFont.Weight.DemiBold.value or fmt.fontItalic() or fmt.fontUnderline() or fmt.isAnchor():
                return True
        block = block.next()
    return False


def email_html(fragment: str) -> str:
    return EMAIL_BODY.format(fragment)


def clean_qt_html(source: str) -> str:
    """Réduit un HTML collé (page web, traitement de texte) au sous-ensemble d’e-mail de Smail."""
    document = QTextDocument()
    document.setHtml(source)
    return render(document)[0]


class RichTextEdit(QTextEdit):
    """Éditeur enrichi ; fichiers et images collés ou déposés deviennent des pièces jointes si autorisé."""
    pathsAdded = Signal(list)
    imageAdded = Signal(object)

    def __init__(self, attachments=True, parent=None):
        super().__init__(parent)
        self.attachments_allowed = attachments
        self.setAcceptRichText(True)
        self.document().setDocumentMargin(6)
        self.apply_link_color()

    def contextMenuEvent(self, event):
        """Clic droit : suggestions du correcteur d’orthographe en tête du menu habituel, s’il est activé."""
        if getattr(self, 'speller', None) is not None:
            from mailclient.ui.spelling import context_menu
            context_menu(self, event)
        else:
            super().contextMenuEvent(event)

    def apply_link_color(self):
        """Liens dans la couleur d’accent du thème (la palette Qt par défaut est peu lisible sur nos fonds)."""
        palette = QApplication.palette()
        palette.setColor(QPalette.Link, palette.color(QPalette.Highlight))
        self.setPalette(palette)

    def setHtml(self, text):
        super().setHtml(text)
        self.normalize_links()

    def insert_html(self, cursor, text):
        cursor.insertHtml(text)
        self.normalize_links()

    def normalize_links(self):
        """Liens dans la couleur d’accent du thème : Qt fige à l’import une couleur peu lisible.
        Affichage seulement : le HTML envoyé est reconstruit sans couleur."""
        accent = self.palette().color(QPalette.Highlight)
        ranges, block = [], self.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                it += 1
                if fragment.isValid() and fragment.charFormat().isAnchor() and fragment.charFormat().foreground().color() != accent:
                    ranges.append((fragment.position(), fragment.length(), fragment.charFormat()))
            block = block.next()
        for position, length, fmt in ranges:
            cursor = QTextCursor(self.document())
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.KeepAnchor)
            fmt.setForeground(accent)
            cursor.setCharFormat(fmt)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ApplicationPaletteChange:
            self.apply_link_color()
            self.normalize_links()

    def canInsertFromMimeData(self, source):
        from mailclient.ui.attachment_widgets import local_paths
        if local_paths(source) or source.hasImage():
            return self.attachments_allowed  # Signature : ni fichier, ni chemin collé comme texte.
        return source.hasText() or source.hasHtml()

    def insertFromMimeData(self, source):
        from mailclient.ui.attachment_widgets import local_paths, clipboard_image
        if not self.attachments_allowed and (local_paths(source) or source.hasImage()):
            return
        if self.attachments_allowed:
            paths = local_paths(source)
            if paths:
                self.pathsAdded.emit(paths)
                return
            if source.hasImage():
                image = clipboard_image(source)
                if not image.isNull():
                    self.imageAdded.emit(image)
                return
        if source.hasHtml():
            # Mise en forme utile conservée ; styles, images distantes et scripts du contenu collé écartés.
            self.insert_html(self.textCursor(), clean_qt_html(source.html()))
        elif source.hasText():
            self.textCursor().insertText(source.text())

    def mail_parts(self) -> tuple[str, str]:
        """(HTML d’e-mail complet ou vide si aucune mise en forme, texte brut)."""
        fragment, text = render(self.document())
        return (email_html(fragment) if has_formatting(self.document()) else ''), text


class FormatBar(QWidget):
    """Gras, italique, souligné, listes, lien et effacement de la mise en forme pour un RichTextEdit."""
    def __init__(self, editor: RichTextEdit, theme, parent=None):
        super().__init__(parent)
        self.editor = editor
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self.buttons = {}
        for key, icon_name, tooltip, shortcut in [
                ('bold', 'bold', N_('Gras'), 'Ctrl+B'), ('italic', 'italic', N_('Italique'), 'Ctrl+I'),
                ('underline', 'underline', N_('Souligné'), 'Ctrl+U'), ('bullets', 'list', N_('Liste à puces'), 'Ctrl+Shift+8'),
                ('numbers', 'list-ordered', N_('Liste numérotée'), 'Ctrl+Shift+7'), ('link', 'link', N_('Insérer un lien'), 'Ctrl+Shift+K'),
                ('clear', 'remove-formatting', N_('Effacer la mise en forme'), 'Ctrl+Space')]:
            button = Button('', theme, icon_name, tooltip=f'{tr(tooltip)} ({QKeySequence(shortcut).toString(QKeySequence.NativeText)})')
            button.setAccessibleName(tr(tooltip))
            button.setFixedSize(30, 30)
            button.setMinimumHeight(30)
            button.setFocusPolicy(Qt.NoFocus)  # Le curseur reste dans le texte.
            button.setCheckable(key in {'bold', 'italic', 'underline', 'bullets', 'numbers'})
            button.clicked.connect(lambda checked=False, k=key: self.apply(k))
            key_shortcut = QShortcut(QKeySequence(shortcut), editor)
            key_shortcut.setContext(Qt.WidgetShortcut)
            key_shortcut.activated.connect(lambda k=key: self.apply(k))
            row.addWidget(button)
            self.buttons[key] = button
        row.addStretch()
        editor.cursorPositionChanged.connect(self.refresh)
        editor.currentCharFormatChanged.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        fmt = self.editor.currentCharFormat()
        text_list = self.editor.textCursor().currentList()
        states = dict(bold=fmt.fontWeight() >= QFont.Weight.DemiBold.value, italic=fmt.fontItalic(),
                      underline=fmt.fontUnderline() and not fmt.isAnchor(),
                      bullets=bool(text_list) and text_list.format().style() not in ORDERED,
                      numbers=bool(text_list) and text_list.format().style() in ORDERED)
        for key, value in states.items():
            self.buttons[key].blockSignals(True)
            self.buttons[key].setChecked(value)
            self.buttons[key].blockSignals(False)

    def apply(self, key):
        editor, cursor = self.editor, self.editor.textCursor()
        if key in {'bold', 'italic', 'underline'}:
            current = editor.currentCharFormat()
            fmt = QTextCharFormat()
            if key == 'bold':
                fmt.setFontWeight(QFont.Weight.Normal if current.fontWeight() >= QFont.Weight.DemiBold.value else QFont.Weight.Bold)
            elif key == 'italic':
                fmt.setFontItalic(not current.fontItalic())
            else:
                fmt.setFontUnderline(not current.fontUnderline())
            self.merge(cursor, fmt)
        elif key in {'bullets', 'numbers'}:
            style = QTextListFormat.Style.ListDisc if key == 'bullets' else QTextListFormat.Style.ListDecimal
            text_list = cursor.currentList()
            if text_list and (text_list.format().style() in ORDERED) == (key == 'numbers'):
                block_format = cursor.blockFormat()
                for index in reversed(range(text_list.count())):
                    item = text_list.item(index)
                    if item.position() <= cursor.selectionEnd() and item.position() + item.length() > cursor.selectionStart():
                        text_list.remove(item)
                block_format.setIndent(0)
                cursor.setBlockFormat(block_format)
            else:
                cursor.createList(style)
        elif key == 'link':
            self.insert_link(cursor)
        elif key == 'clear':
            if not cursor.hasSelection():
                cursor.select(QTextCursor.BlockUnderCursor)
            cursor.setCharFormat(QTextCharFormat())
            editor.setCurrentCharFormat(QTextCharFormat())
        editor.setFocus()
        self.refresh()

    def merge(self, cursor, fmt):
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.editor.mergeCurrentCharFormat(fmt)

    def insert_link(self, cursor):
        current = cursor.charFormat().anchorHref() if cursor.charFormat().isAnchor() else 'https://'
        url, ok = QInputDialog.getText(self, tr('Insérer un lien'), tr('Adresse (https://…, ou une adresse e-mail)'), text=current)
        url = url.strip()
        if not ok or not url or url == 'https://':
            return
        if '@' in url and '://' not in url and not url.lower().startswith('mailto:'):
            url = 'mailto:' + url
        if not SAFE_LINK.match(url):
            QMessageBox.warning(self, tr('Lien refusé'), tr('Seuls les liens https://, http:// et mailto: sont acceptés.'))
            return
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setFontUnderline(True)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            cursor.insertText(url.removeprefix('mailto:'), fmt)
            cursor.insertText(' ', QTextCharFormat())
        self.editor.normalize_links()
