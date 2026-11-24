"""Composants visuels réutilisables, découplés de tout service métier."""
from PySide6.QtCore import Qt, QSize, QRectF, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPainter, QFont, QPen, QFontMetrics
from PySide6.QtWidgets import (QLabel, QPushButton, QFrame, QHBoxLayout, QVBoxLayout,
    QWidget, QStyledItemDelegate, QGraphicsOpacityEffect, QTextBrowser)
from .icons import icon

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
        self.setAccessibleName('Corps du message')

    def loadResource(self, resource_type, name):
        return None

class MailDelegate(QStyledItemDelegate):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme

    def sizeHint(self, option, index):
        return QSize(300, self.theme.row_height)

    def paint(self, painter, option, index):
        from PySide6.QtWidgets import QStyle
        mail = index.data(Qt.UserRole)
        if mail is None:
            return
        t = self.theme.colors
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(5,2,-5,-2)
        selected = bool(option.state & QStyle.State_Selected)
        if selected or option.state & QStyle.State_MouseOver:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t['soft'] if selected else t['panel']))
            painter.drawRoundedRect(QRectF(rect), 7,7)
        if selected:
            painter.setPen(QPen(QColor(t['accent']), 2))
            painter.drawLine(rect.left()+1, rect.top()+10, rect.left()+1, rect.bottom()-10)
        left = rect.left()+16
        top = rect.top()+8
        if self.theme.variant == 2:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t['panel'] if not selected else t['surface']))
            painter.drawEllipse(QRectF(left, top+4, 34,34))
            painter.setPen(QColor(t['muted']))
            painter.setFont(QFont('Segoe UI', 9, QFont.DemiBold))
            initials = ''.join(word[0] for word in mail.sender.split()[:2])
            painter.drawText(QRectF(left,top+4,34,34), Qt.AlignCenter, initials)
            left += 45
        width = rect.right()-left-16
        painter.setFont(QFont('Segoe UI', 10, QFont.DemiBold))
        painter.setPen(QColor(t['text']))
        count = getattr(mail, 'count', 1)
        badge = 0
        if count > 1:
            badge_font = QFont('Segoe UI', 8, QFont.DemiBold)
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
            painter.setFont(QFont('Segoe UI', 10, QFont.DemiBold))
        painter.setFont(QFont('Segoe UI', 8))
        painter.setPen(QColor(t['accent'] if mail.unread else t['muted']))
        painter.drawText(QRectF(rect.right()-71,top,57,20), Qt.AlignRight|Qt.AlignVCenter, mail.time)
        painter.setFont(QFont('Segoe UI', 9, QFont.DemiBold if mail.unread else QFont.Normal))
        painter.setPen(QColor(t['text']))
        subject = painter.fontMetrics().elidedText(mail.subject, Qt.ElideRight, max(40,width-19))
        painter.drawText(QRectF(left,top+22,width-15,19), Qt.AlignLeft|Qt.AlignVCenter, subject)
        if rect.height() >= 61:
            painter.setFont(QFont('Segoe UI', 9))
            painter.setPen(QColor(t['muted']))
            preview = painter.fontMetrics().elidedText(mail.preview, Qt.ElideRight, max(40,width-56))
            painter.drawText(QRectF(left,top+43,width-52,18), Qt.AlignLeft|Qt.AlignVCenter, preview)
        if self.theme.variant == 2 and rect.height() >= 89:
            painter.setFont(QFont('Segoe UI', 8))
            painter.drawText(QRectF(left,top+66,width-30,17), Qt.AlignLeft|Qt.AlignVCenter, mail.account_name)
        if mail.unread:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t['accent']))
            painter.drawEllipse(QRectF(rect.left()+6, top+8, 5,5))
        marker_y = rect.bottom()-22
        if mail.attachments:
            icon('paperclip', t['muted'], 14).paint(painter, rect.right()-23, marker_y,14,14)
        if mail.starred:
            icon('star', t['accent'], 14).paint(painter, rect.right()-43, marker_y,14,14)
        painter.restore()

class Skeleton(QWidget):
    """Squelette peint localement, animé à 180 ms sauf en capture/réduction."""
    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.setAccessibleName('Chargement des messages')
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
