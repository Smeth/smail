"""Composants visuels réutilisables, découplés de tout service métier."""
from mailclient.i18n import tr
import re
from PySide6.QtCore import Qt, QSize, QRectF, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPainter, QFont, QPen, QFontMetrics
from PySide6.QtWidgets import (QLabel, QPushButton, QFrame, QHBoxLayout, QVBoxLayout,
    QWidget, QStyledItemDelegate, QGraphicsOpacityEffect, QTextBrowser)
from .icons import icon


def ui_font(size, weight=QFont.Normal) -> QFont:
    """Police d’interface peinte à la main (la liste est ensuite agrandie d’un bloc selon la taille du texte de Windows)."""
    font = QFont('Segoe UI')
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


def safe_rich(text) -> str:
    """Texte non fiable (expéditeur, objet, nom de fichier ou de dossier, adresse…) pour une infobulle ou une boîte de
    message, affiché tel quel. Qt y interprète sinon le HTML : un expéditeur « <img src='file://serveur/x'> » ferait
    charger une image sur un partage réseau au simple survol (fuite de l’empreinte NTLM de la session Windows)."""
    import html
    return '<qt>' + html.escape(str(text or '')).replace('\n', '<br>') + '</qt>'


# Couleurs des initiales : assez soutenues pour un texte blanc lisible, sur thème clair comme sombre.
AVATAR_COLORS = ('#D93F45', '#D0612A', '#A97700', '#3E8E4F', '#0F8C80', '#1F7FD6', '#4458C7', '#7E4CB8', '#C43A8B', '#6F6152')


def avatar(sender: str) -> tuple:
    """(initiales, couleur) d’un expéditeur « Nom <adresse> » : couleur stable, tirée de l’adresse.

    Aucune photo n’est cherchée en ligne (Gravatar, logos…) : cela révélerait à un tiers qui vous écrit."""
    import hashlib
    from email.utils import parseaddr
    name, address = parseaddr(sender or '')
    if '@' in name:
        name = ''  # « Nom » qui est en fait une adresse : initiales tirées de l’adresse.
    words = [word for word in re.split(r'[\s,.\-_]+', name.strip(' "\'')) if word and word[0].isalnum()]
    if not words:
        words = [part for part in re.split(r'[._\-]+', address.split('@')[0]) if part] or ['?']
    letters = (words[0][0] + (words[1][0] if len(words) > 1 else (words[0][1] if len(words[0]) > 1 else ''))).upper()
    key = (address or name or '?').casefold().encode('utf-8')
    return letters, AVATAR_COLORS[int(hashlib.sha1(key).hexdigest(), 16) % len(AVATAR_COLORS)]


def label(text='', role='', wrap=False):
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(wrap)
    return widget

class Button(QPushButton):
    def __init__(self, text, theme, icon_name=None, role='', tooltip=None, parent=None):
        super().__init__(text, parent)
        self.theme, self.icon_name, self.role = theme, icon_name, role
        self.setObjectName(role)
        self.setCursor(Qt.PointingHandCursor)
        # Focus au clavier (Tab) seulement : un clic ne laisse pas de cadre de focus sur le bouton
        # (le cadre restait affiché au retour d’une boîte de dialogue) et ne retire pas le focus à la liste.
        self.setFocusPolicy(Qt.TabFocus)
        self.setAccessibleName(tooltip or text)
        self.setToolTip(tooltip or text)
        self.setIconSize(QSize(18,18))
        self.setMinimumHeight(54 if '\n' in text else 40 if role == 'Primary' else 36)
        self.theme.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        if self.icon_name:
            color = self.theme.colors['on_accent' if self.role == 'Primary' else 'text']
            self.setIcon(icon(self.icon_name, color))

class IconLabel(QLabel):
    def __init__(self, name, theme, semantic='muted', size=20):
        super().__init__()
        self.name, self.theme, self.semantic, self.size = name, theme, semantic, size
        self.setFixedSize(size+2, size+2)
        self.theme.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.setPixmap(icon(self.name, self.theme.colors[self.semantic], self.size).pixmap(self.size,self.size))

class Card(QFrame):
    def __init__(self, role='Surface', margin=16):
        super().__init__()
        self.setObjectName(role)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(margin,margin,margin,margin)
        self.box.setSpacing(12)

class Banner(QFrame):
    def __init__(self, title, description, theme, kind='Info', icon_name='shield-check', action=None):
        super().__init__()
        self.setObjectName(kind)
        row = QHBoxLayout(self)
        row.setContentsMargins(13,11,13,11)
        row.addWidget(IconLabel(icon_name, theme, 'warning' if kind == 'Warning' else 'danger' if kind == 'Danger' else 'accent'))
        text = QVBoxLayout()
        text.setSpacing(3)
        text.addWidget(label(title, 'Bold', True))
        if description:
            text.addWidget(label(description, 'Small', True))
        row.addLayout(text, 1)
        self.action = None
        if action:
            self.action = Button(action, theme, role='Secondary')
            row.addWidget(self.action)

def separator():
    line = QFrame()
    line.setObjectName('Separator')
    return line

def later(owner, milliseconds, callback):
    """Timer possédé par le widget : aucun rappel après sa destruction."""
    timer = QTimer(owner)
    timer.setSingleShot(True)
    timer.timeout.connect(callback)
    timer.timeout.connect(timer.deleteLater)
    timer.start(milliseconds)
    return timer

def fade(widget, theme):
    if theme.reduced_motion or theme.capture_mode:
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b'opacity', widget)
    animation.setDuration(170)
    animation.setStartValue(.48)
    animation.setEndValue(1.)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._fade = animation
    animation.start()

class LocalTextBrowser(QTextBrowser):
    """Même les ressources externes ne peuvent pas être chargées par le lecteur."""
    def __init__(self):
        super().__init__()
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setAccessibleName(tr('Corps du message'))

    def loadResource(self, resource_type, name):
        return None

HEADER_ROLE = Qt.UserRole + 2   # Titre de groupe de dates (« Aujourd’hui »…) dessiné au-dessus de la ligne.
GROUP_ROLE = Qt.UserRole + 3    # Groupe de dates de la ligne (« Hier »…).
COLLAPSED_ROLE = Qt.UserRole + 4  # Première ligne d’un groupe replié : seul le titre est dessiné.
GROUP_COUNT_ROLE = Qt.UserRole + 5  # Nombre de lignes du groupe (affiché quand il est replié).
FILTERED_ROLE = Qt.UserRole + 6  # Ligne masquée par le filtre (Non lus, pièces jointes…), indépendamment du repli.
ALWAYS_OPEN = 'Aujourd’hui'  # Clé interne (date_group) ; affichée traduite.
HEADER_HEIGHT = 28
# Actions au survol : (nom, icône, infobulle) ; l’icône de lecture dépend de l’état du message.
ROW_ACTIONS = (('archive', 'archive', 'Archiver'), ('trash', 'trash-2', 'Supprimer'), ('read', None, None))


class MailDelegate(QStyledItemDelegate):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.on_action = None  # Rappel (index, nom de l’action) pour les boutons affichés au survol.
        self.check_all = False  # Plusieurs messages cochés : chaque ligne montre sa case à cocher.

    def sizeHint(self, option, index):
        if index.data(COLLAPSED_ROLE):
            return QSize(300, HEADER_HEIGHT + 4)
        return QSize(300, round((self.theme.row_height + (HEADER_HEIGHT if index.data(HEADER_ROLE) else 0)) * self.zoom()))

    def zoom(self) -> float:
        """Taille du texte de Windows (accessibilité) : la ligne entière est agrandie, texte et zones de clic."""
        return getattr(self.theme, 'text_scale', 1.0)

    def virtual(self, option, position=None):
        """(option à l’échelle 1, position ramenée à cette échelle) : le dessin et les clics partagent la même géométrie."""
        from PySide6.QtCore import QPointF, QRect
        from PySide6.QtWidgets import QStyleOptionViewItem
        zoom = self.zoom()
        if abs(zoom - 1) < .01:
            return option, position
        scaled = QStyleOptionViewItem(option)
        top_left = option.rect.topLeft()
        scaled.rect = QRect(top_left.x(), top_left.y(), round(option.rect.width() / zoom), round(option.rect.height() / zoom))
        if position is not None:
            position = QPointF(top_left.x() + (position.x() - top_left.x()) / zoom,
                               top_left.y() + (position.y() - top_left.y()) / zoom)
        return scaled, position

    @staticmethod
    def message_rect(option, index):
        top = HEADER_HEIGHT if index.data(HEADER_ROLE) else 0
        return option.rect.adjusted(5, 2 + top, -5, -2)

    @staticmethod
    def check_rect(rect):
        """Zone des initiales, qui devient une case à cocher au survol ou en sélection multiple."""
        size = 34 if rect.height() >= 60 else 28
        return QRectF(rect.left() + 16, rect.top() + 12, size, size)

    @staticmethod
    def action_rects(rect):
        """Zones des boutons d’action, alignées à droite sur la ligne de l’expéditeur."""
        size, gap = 24, 4
        right, top = rect.right() - 10, rect.top() + 6
        return [(name, QRectF(right - (len(ROW_ACTIONS) - i) * (size + gap) + gap, top, size, size))
                for i, (name, *_rest) in enumerate(ROW_ACTIONS)]

    def editorEvent(self, event, model, option, index):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.MouseButtonRelease and self.on_action and index.data(Qt.UserRole) is not None:
            local, position = self.virtual(option, event.position())
            for name, area in self.action_rects(self.message_rect(local, index)):
                if area.contains(position):
                    self.on_action(index, name)
                    return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index):
        mail = index.data(Qt.UserRole)
        if mail is not None and self.on_action:
            from PySide6.QtWidgets import QToolTip
            texts = {'archive': tr('Archiver'), 'trash': tr('Supprimer'),
                     'read': tr('Marquer comme lu') if mail.unread else tr('Marquer comme non lu')}
            local, position = self.virtual(option, event.position() if hasattr(event, "position") else event.pos())
            for name, area in self.action_rects(self.message_rect(local, index)):
                if area.contains(position):
                    QToolTip.showText(event.globalPos(), texts[name], view)
                    return True
        return super().helpEvent(event, view, option, index)

    def paint(self, painter, option, index):
        from PySide6.QtWidgets import QStyle
        mail = index.data(Qt.UserRole)
        if mail is None:
            return
        t = self.theme.colors
        painter.save()
        zoom = self.zoom()
        if abs(zoom - 1) >= .01:  # Taille du texte de Windows : la ligne est dessinée à l’échelle 1 puis agrandie.
            origin = option.rect.topLeft()
            painter.translate(origin)
            painter.scale(zoom, zoom)
            painter.translate(-origin)
            option, _ = self.virtual(option)
        painter.setRenderHint(QPainter.Antialiasing)
        header = index.data(HEADER_ROLE)
        if header:
            collapsed = bool(index.data(COLLAPSED_ROLE))
            if header != ALWAYS_OPEN:  # Flèche : clic sur le titre pour replier ou déplier le groupe.
                icon('chevron-right' if collapsed else 'chevron-down', t['muted'], 14).paint(
                    painter, option.rect.left()+8, option.rect.top()+HEADER_HEIGHT-18, 14, 14)
            painter.setFont(ui_font(8, QFont.Bold))
            painter.setPen(QColor(t['muted']))
            from mailclient.i18n import display_group
            text = display_group(header).upper() + (f'  ({index.data(GROUP_COUNT_ROLE)})' if collapsed else '')
            painter.drawText(QRectF(option.rect.left()+26, option.rect.top()+6, option.rect.width()-42, HEADER_HEIGHT-8),
                             Qt.AlignLeft|Qt.AlignBottom, text)
            if collapsed:
                painter.restore()
                return
        rect = self.message_rect(option, index)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver) and self.on_action is not None
        if selected or option.state & QStyle.State_MouseOver:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t['soft'] if selected else t['panel']))
            painter.drawRoundedRect(QRectF(rect), 7,7)
        if selected:
            painter.setPen(QPen(QColor(t['accent']), 2))
            painter.drawLine(rect.left()+1, rect.top()+10, rect.left()+1, rect.bottom()-10)
        left = rect.left()+16
        top = rect.top()+8
        # Initiales colorées de l’expéditeur (le plus récent d’une conversation), dans tous les styles.
        initials, color = avatar(mail.raw.get('sender', '') if isinstance(getattr(mail, 'raw', None), dict) else mail.sender)
        circle = self.check_rect(rect)
        size = int(circle.width())
        if self.check_all or option.state & QStyle.State_MouseOver:
            # Case à cocher (comme Outlook) : un clic coche ou décoche ce message sans toucher aux autres.
            box = QRectF(circle.center().x() - 10, circle.center().y() - 10, 20, 20)
            painter.setPen(QPen(QColor(t['accent'] if selected else t['muted']), 1.5))
            painter.setBrush(QColor(t['accent'] if selected else t['surface']))
            painter.drawRoundedRect(box, 5, 5)
            if selected:
                icon('check', t['on_accent'], 16).paint(painter, int(box.left() + 2), int(box.top() + 2), 16, 16)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            painter.drawEllipse(circle)
            painter.setPen(QColor('#FFFFFF'))
            painter.setFont(ui_font(9 if size >= 34 else 8, QFont.DemiBold))
            painter.drawText(circle, Qt.AlignCenter, initials)
        left += size + 11
        width = rect.right()-left-16
        # Non lu : expéditeur en gras ; lu : expéditeur normal et estompé. La différence se voit d’un coup d’œil.
        sender_font = ui_font(10, QFont.Bold if mail.unread else QFont.Normal)
        painter.setFont(sender_font)
        painter.setPen(QColor(t['text'] if mail.unread or selected else t['muted']))
        count = getattr(mail, 'count', 1)
        badge = 0
        if count > 1:
            badge_font = ui_font(8, QFont.DemiBold)
            badge = QFontMetrics(badge_font).horizontalAdvance(str(count)) + 12
        sender = painter.fontMetrics().elidedText(mail.sender, Qt.ElideRight, max(40,width-76-badge))
        painter.drawText(QRectF(left,top,width-70,20), Qt.AlignLeft|Qt.AlignVCenter, sender)
        if badge:
            # Nombre de messages de la conversation, juste après les expéditeurs.
            x = left + painter.fontMetrics().horizontalAdvance(sender) + 6
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t['soft'] if not selected else t['surface']))
            painter.drawRoundedRect(QRectF(x, top+3, badge, 15), 7.5, 7.5)
            painter.setFont(badge_font)
            painter.setPen(QColor(t['accent'] if mail.unread else t['muted']))
            painter.drawText(QRectF(x, top+3, badge, 15), Qt.AlignCenter, str(count))
            painter.setFont(sender_font)
        if hovered:
            # Au survol, l’heure laisse la place aux actions rapides.
            for name, area in self.action_rects(rect):
                icon_name = {'archive': 'archive', 'trash': 'trash-2'}.get(name) or ('mail-minus' if mail.unread else 'mail')
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(t['surface']))
                painter.drawRoundedRect(area, 6, 6)
                icon(icon_name, t['text'], 16).paint(painter, int(area.left()+4), int(area.top()+4), 16, 16)
        else:
            painter.setFont(ui_font(8))
            painter.setPen(QColor(t['accent'] if mail.unread else t['muted']))
            painter.drawText(QRectF(rect.right()-71,top,57,20), Qt.AlignRight|Qt.AlignVCenter, mail.time)
        painter.setFont(ui_font(9, QFont.DemiBold if mail.unread else QFont.Normal))
        painter.setPen(QColor(t['text'] if mail.unread or selected else t['muted']))
        subject = painter.fontMetrics().elidedText(mail.subject, Qt.ElideRight, max(40,width-19))
        painter.drawText(QRectF(left,top+22,width-15,19), Qt.AlignLeft|Qt.AlignVCenter, subject)
        if rect.height() >= 61:
            painter.setFont(ui_font(9))
            painter.setPen(QColor(t['muted']))
            preview = painter.fontMetrics().elidedText(mail.preview, Qt.ElideRight, max(40,width-56))
            painter.drawText(QRectF(left,top+43,width-52,18), Qt.AlignLeft|Qt.AlignVCenter, preview)
        if self.theme.variant == 2 and rect.height() >= 89:
            painter.setFont(ui_font(8))
            painter.drawText(QRectF(left,top+66,width-30,17), Qt.AlignLeft|Qt.AlignVCenter, mail.account_name)
        if mail.unread:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t['accent']))
            painter.drawEllipse(QRectF(rect.left()+5, top+6, 8, 8))  # Point « non lu » bien visible.
        marker_y = rect.bottom()-22
        if mail.attachments:
            icon('paperclip', t['muted'], 14).paint(painter, rect.right()-23, marker_y,14,14)
        if mail.starred:
            icon('star', t['accent'], 14).paint(painter, rect.right()-43, marker_y,14,14)
        rows = getattr(mail, 'rows', ())
        # Flèche « répondu » (ou « transféré ») : on voit d’un coup d’œil les messages déjà traités.
        done = 'reply' if any(row.get('answered') for row in rows) else 'forward' if any(row.get('forwarded') for row in rows) else None
        if done:
            icon(done, t['muted'], 14).paint(painter, rect.right()-63, marker_y, 14, 14)
        painter.restore()

class Skeleton(QWidget):
    """Squelette peint localement, animé à 180 ms sauf en capture/réduction."""
    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.setAccessibleName(tr('Chargement des messages'))
        self.theme.changed.connect(self.update)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.theme.colors['skeleton']))
        for i in range(7):
            y = 18+i*82
            painter.drawRoundedRect(QRectF(18,y,140,10),5,5)
            painter.drawRoundedRect(QRectF(18,y+23,max(70,self.width()-75),12),5,5)
            painter.drawRoundedRect(QRectF(18,y+47,max(60,self.width()-115),8),4,4)

class Moodboard(QWidget):
    """Image de substitution dessinée ici, jamais récupérée à distance."""
    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.setMinimumHeight(150)
        self.setMaximumHeight(170)
        self.theme.changed.connect(self.update)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        colors = [self.theme.colors['soft'], self.theme.colors['panel'], self.theme.colors['hover']]
        width = (self.width()-24)/3
        for i,color in enumerate(colors):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            x = i*(width+12)
            painter.drawRoundedRect(QRectF(x,0,width,self.height()),10,10)
            painter.setPen(QPen(QColor(self.theme.colors['muted']),1))
            for j in range(5):
                painter.drawArc(QRectF(x+15+j*9,20+j*7,width-30,100),20*16,180*16)
