"""Visionneuse isolée ; aucun lien ni téléchargement WebEngine autorisé."""
from pathlib import Path
from html.parser import HTMLParser
from email.utils import parseaddr, parsedate_to_datetime
from PySide6.QtCore import Qt, QUrl, QSaveFile, QIODevice, QBuffer, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QPlainTextEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QScrollArea, QSizePolicy, QMenu)
from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
                                    QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo,
                                    QWebEngineUrlScheme, QWebEngineUrlSchemeHandler, QWebEngineUrlRequestJob)
from PySide6.QtWebEngineWidgets import QWebEngineView
from mailclient.core.parser import Mail
from mailclient.core.html_security import safe_document, dangerous_filename
from mailclient.core.unsubscribe import options as unsubscribe_options
from mailclient.ui.components import label, Button, Banner, Card, IconLabel
from mailclient.ui.dialog_shell import appearance
from mailclient.ui.attachment_widgets import AttachmentGrid, thumbnail
from mailclient.core.sync import Runner
from mailclient.ui.icons import icon
from PySide6.QtGui import QIcon, QPixmap
from shiboken6 import isValid


class RemoteImages(HTMLParser):
    """Détecte uniquement les images autorisables dans le HTML déjà assaini."""
    def __init__(self, document):
        super().__init__()
        self.found = False
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            source = dict(attrs).get('src','').lower()
            self.found |= source.startswith(('https://','http://'))

SCHEME = QWebEngineUrlScheme(b'smail')
SCHEME.setSyntax(QWebEngineUrlScheme.Syntax.Host)
SCHEME.setFlags(QWebEngineUrlScheme.LocalScheme)
QWebEngineUrlScheme.registerScheme(SCHEME)

class DocumentHandler(QWebEngineUrlSchemeHandler):
    """Document servi uniquement en mémoire, sans limite d’URL data de 2 Mio."""
    def __init__(self, parent):
        super().__init__(parent)
        self.content = b''
        self.buffers = {}

    def requestStarted(self, job):
        if job.requestUrl().host() != 'message' or job.requestUrl().path() != '/current':
            job.fail(QWebEngineUrlRequestJob.UrlNotFound)
            return
        buffer = QBuffer(job)
        buffer.setData(self.content)
        buffer.open(QIODevice.ReadOnly)
        self.buffers[id(job)] = buffer
        job.destroyed.connect(lambda obj=None, key=id(job): self.buffers.pop(key, None))
        job.reply(b'text/html', buffer)

class ImageInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.remote = False

    def interceptRequest(self, info):
        scheme = info.requestUrl().scheme().lower()
        kind = info.resourceType()
        allowed = scheme in {'data', 'about'}
        if scheme == 'smail':
            allowed = kind == QWebEngineUrlRequestInfo.ResourceTypeMainFrame
        if scheme in {'https', 'http'}:
            allowed = self.remote and kind == QWebEngineUrlRequestInfo.ResourceTypeImage
        info.block(not allowed)
        if allowed and scheme in {'http', 'https'}:
            info.setHttpHeader(b'Referer', b'')

class MailPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return is_main_frame and url.scheme() in {'data', 'about', 'smail'}

def print_document(mail):
    """Document imprimable : en-tête du message puis corps nettoyé (aucune image distante)."""
    import html as html_module
    from PySide6.QtGui import QTextDocument
    safe = safe_document(mail, remote_images=False, dark=False)
    body = safe.split('<body>', 1)[-1].rsplit('</body>', 1)[0]
    rows = [('De', mail.sender), ('À', mail.recipients), ('Cc', mail.cc), ('Date', mail.date)]
    header = ''.join(f'<tr><td style="color:#56657a;padding-right:12px">{name}</td><td>{html_module.escape(value)}</td></tr>'
                     for name, value in rows if value)
    document = QTextDocument()
    document.setDefaultStyleSheet('body{font-family:"Segoe UI",Arial,sans-serif;font-size:11pt}')
    document.setHtml(f'<h2>{html_module.escape(mail.subject or "(Sans objet)")}</h2><table>{header}</table><hr>{body}'
                     + (f'<p style="color:#56657a">Pièces jointes : {html_module.escape(", ".join(a.name for a in mail.attachments))}</p>'
                        if mail.attachments else ''))
    return document

class MailView(QWidget):
    replyRequested = Signal()
    replyAllRequested = Signal()
    forwardRequested = Signal()
    archiveRequested = Signal()
    deleteRequested = Signal()
    starRequested = Signal()
    readRequested = Signal()
    threadMessageRequested = Signal(int)
    unsubscribeRequested = Signal()
    inviteAnswered = Signal(str)
    inviteImportRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mail: Mail | None = None
        self.disposed = False
        self.dark = False
        self.theme = appearance()
        self.preview_runner = Runner(self,None)
        self.preview_revision = 0
        self.setObjectName('ReaderWorkspace')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(10)
        self.action_buttons = []
        self.more_menu = QMenu(self)
        for name,title,signal in [('archive','Archiver',self.archiveRequested),('trash-2','Supprimer',self.deleteRequested),
                                  ('star','Suivre / ne plus suivre',self.starRequested),('mail','Marquer comme lu / non lu',self.readRequested)]:
            button = Button('',self.theme,name,tooltip=title,parent=self)
            button.hide()
            button.clicked.connect(lambda checked=False,s=signal:s.emit())
            self.action_buttons.append(button)
            action = self.more_menu.addAction(title,button.click)
            action.setIcon(icon(name,self.theme.colors['text']))
        self.more_menu.aboutToShow.connect(self.update_more_menu)
        self.subject_card = Card('ReaderSubject',12)
        layout.addWidget(self.subject_card)
        self.metadata = QScrollArea()
        self.metadata.setWidgetResizable(True)
        self.metadata.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.metadata.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        self.metadata.setMinimumHeight(0)
        self.metadata.setMaximumHeight(80)
        self.subject = label('','ReaderSubjectText',True)
        self.subject.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.subject.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        self.metadata.setWidget(self.subject)
        self.subject_card.box.addWidget(self.metadata)
        # Lecture empilée : messages antérieurs repliés au-dessus du message ouvert, suivants en dessous.
        self.thread_current = -1
        self.thread_card = Card('ReaderThread',8)
        self.thread_title = label('','Eyebrow')
        self.thread_card.box.addWidget(self.thread_title)
        self.thread_list = self.thread_list_widget('Messages précédents de la conversation, Entrée pour lire', 0)
        self.thread_card.box.addWidget(self.thread_list)
        self.thread_card.hide()
        layout.addWidget(self.thread_card)
        self.thread_after_card = Card('ReaderThread',8)
        self.thread_after = self.thread_list_widget('Messages suivants de la conversation, Entrée pour lire', 1)
        self.thread_after_card.box.addWidget(self.thread_after)
        self.thread_after_card.hide()
        self.message_card = Card('ReaderMessage',16)
        self.message_card.box.setSpacing(8)
        layout.addWidget(self.message_card,1)
        layout.addWidget(self.thread_after_card)
        message_layout = self.message_card.box
        sender_row = QHBoxLayout()
        sender_row.setSpacing(10)
        self.avatar = label('','ReaderAvatar')
        self.avatar.setFixedSize(42,42)
        self.avatar.setAlignment(Qt.AlignCenter)
        sender_row.addWidget(self.avatar,0,Qt.AlignTop)
        sender_info = QVBoxLayout()
        sender_info.setSpacing(3)
        self.sender_name = label('','ReaderSender')
        self.sender_name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.sender_name.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        self.sender_address = label('','Small')
        self.sender_address.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        self.recipient_summary = label('','Small')
        self.recipient_summary.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        sender_info.addWidget(self.sender_name)
        sender_info.addWidget(self.sender_address)
        sender_info.addWidget(self.recipient_summary)
        sender_row.addLayout(sender_info,1)
        header_actions = QVBoxLayout()
        header_actions.setSpacing(2)
        response = QHBoxLayout()
        response.setSpacing(2)
        for title,name,signal in [('Répondre','reply',self.replyRequested),('Répondre à tous','reply-all',self.replyAllRequested),('Transférer','forward',self.forwardRequested)]:
            button = Button('',self.theme,name,tooltip=title)
            button.setFixedSize(32,32)
            button.setMinimumHeight(32)
            button.clicked.connect(lambda checked=False,s=signal:s.emit())
            self.action_buttons.append(button)
            response.addWidget(button)
        self.more_button = Button('…',self.theme,tooltip='Autres actions et mode de lecture')
        self.more_button.setObjectName('ReaderMore')
        self.more_button.setFixedSize(36,32)
        self.more_button.setMinimumHeight(32)
        self.more_button.setMenu(self.more_menu)
        response.addWidget(self.more_button)
        header_actions.addLayout(response)
        self.date_label = label('','Small')
        self.date_label.setAlignment(Qt.AlignRight)
        header_actions.addWidget(self.date_label)
        sender_row.addLayout(header_actions)
        message_layout.addLayout(sender_row)
        self.headers = QLabel()
        self.headers.setObjectName('Small')
        self.headers.setTextFormat(Qt.PlainText)
        self.headers.setWordWrap(True)
        self.headers.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.headers.setMaximumHeight(80)
        message_layout.addWidget(self.headers)
        self.more_menu.addSeparator()
        self.details_action = self.more_menu.addAction('Afficher les détails du message')
        self.details_action.setCheckable(True)
        self.details_action.toggled.connect(self.headers.setVisible)
        self.remote_banner = Banner('Images distantes bloquées','Les images peuvent signaler votre lecture à l’expéditeur.',self.theme,'Info','image-off','Afficher les images')
        self.images = self.remote_banner.action
        self.images.setToolTip('Les images distantes peuvent signaler votre lecture à l’expéditeur.')
        self.images.clicked.connect(self.show_images)
        message_layout.addWidget(self.remote_banner)
        self.danger_banner = Banner('Pièce jointe potentiellement dangereuse','Ce fichier peut exécuter du code. Il ne sera jamais ouvert automatiquement.',self.theme,'Danger','shield-alert')
        message_layout.addWidget(self.danger_banner)
        self.unsubscribe_banner = Banner('Liste de diffusion','Vous pouvez vous désabonner sans ouvrir de lien dans le message.',
                                         self.theme,'Info','mail-minus','Se désabonner')
        self.unsubscribe_banner.action.clicked.connect(self.unsubscribeRequested.emit)
        message_layout.addWidget(self.unsubscribe_banner)
        # Invitation de calendrier : résumé et réponse à l’organisateur.
        self.invite = None
        self.invite_card = Card('Info',12)
        invite_row = QHBoxLayout()
        invite_row.addWidget(IconLabel('clock',self.theme,'accent'),0,Qt.AlignTop)
        invite_text = QVBoxLayout()
        self.invite_title = label('','Bold',True)
        self.invite_details = label('','Small',True)
        invite_text.addWidget(self.invite_title)
        invite_text.addWidget(self.invite_details)
        invite_row.addLayout(invite_text,1)
        self.invite_card.box.addLayout(invite_row)
        invite_buttons = QHBoxLayout()
        self.invite_buttons = {}
        for partstat,text,role in (('ACCEPTED','Accepter','Primary'),('TENTATIVE','Provisoire','Secondary'),('DECLINED','Refuser','Secondary')):
            button = Button(text,self.theme,role=role,tooltip='Envoie votre réponse à l’organisateur')
            button.clicked.connect(lambda checked=False,value=partstat:self.inviteAnswered.emit(value))
            invite_buttons.addWidget(button)
            self.invite_buttons[partstat] = button
        self.invite_import = Button('Ajouter au calendrier',self.theme,'download','Secondary',
                                    'Ouvre l’invitation dans l’application de calendrier de Windows')
        self.invite_import.clicked.connect(self.inviteImportRequested.emit)
        invite_buttons.addStretch()
        invite_buttons.addWidget(self.invite_import)
        self.invite_card.box.addLayout(invite_buttons)
        message_layout.addWidget(self.invite_card)
        self.empty_message = label('Sélectionnez un message pour le lire.','Subtitle',True)
        self.empty_message.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_message,1)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setMinimumHeight(180)
        self.tabs.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setTabChangesFocus(True)
        self.web = QWebEngineView()
        self.web.setContextMenuPolicy(Qt.NoContextMenu)
        self.profile = QWebEngineProfile(self.web)  # Sans nom : profil privé en mémoire.
        self.profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        self.profile.downloadRequested.connect(lambda download: download.cancel())
        self.interceptor = ImageInterceptor(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.document = DocumentHandler(self.profile)
        self.profile.installUrlSchemeHandler(b'smail', self.document)
        self.generation = 0
        self.web.setPage(MailPage(self.profile, self.web))
        settings = self.web.settings()
        for option in (QWebEngineSettings.JavascriptEnabled, QWebEngineSettings.JavascriptCanOpenWindows,
                       QWebEngineSettings.LocalContentCanAccessFileUrls, QWebEngineSettings.LocalContentCanAccessRemoteUrls,
                       QWebEngineSettings.PluginsEnabled, QWebEngineSettings.PdfViewerEnabled,
                       QWebEngineSettings.HyperlinkAuditingEnabled, QWebEngineSettings.DnsPrefetchEnabled):
            settings.setAttribute(option, False)
        self.tabs.addTab(self.web, 'HTML sécurisé')
        self.tabs.addTab(self.text, 'Texte brut')
        self.print_action = self.more_menu.addAction('Imprimer…', self.print_message)
        self.plain_action = self.more_menu.addAction('Lire en texte brut')
        self.plain_action.setCheckable(True)
        self.plain_action.toggled.connect(lambda checked:self.tabs.setCurrentIndex(1 if checked else 0))
        self.tabs.currentChanged.connect(lambda index:self.plain_action.setChecked(index == 1))
        self.attachment_section = QWidget()
        attachment_layout = QVBoxLayout(self.attachment_section)
        attachment_layout.setContentsMargins(0,0,0,0)
        attachment_layout.setSpacing(2)
        attachment_header = QHBoxLayout()
        self.attachment_title = Button('Pièces jointes',self.theme,'paperclip',tooltip='Afficher ou masquer les pièces jointes')
        self.attachment_title.setCheckable(True)
        self.attachment_title.setChecked(False)
        attachment_header.addWidget(self.attachment_title)
        attachment_header.addStretch()
        self.save_button = Button('Enregistrer…',self.theme,'download','Secondary',tooltip='Enregistrer la pièce jointe sélectionnée')
        self.save_button.clicked.connect(self.save_attachment)
        self.preview_button = Button('Aperçu',self.theme,'file-text','Secondary',tooltip='Aperçu de la pièce jointe sélectionnée (double-clic)')
        self.preview_button.clicked.connect(self.preview_attachment)
        self.save_all_button = Button('Tout enregistrer…',self.theme,'download','Secondary',
                                      tooltip='Enregistrer toutes les pièces jointes dans un dossier')
        self.save_all_button.clicked.connect(self.save_all_attachments)
        attachment_header.addWidget(self.preview_button)
        attachment_header.addWidget(self.save_button)
        attachment_header.addWidget(self.save_all_button)
        attachment_layout.addLayout(attachment_header)
        self.attachments = AttachmentGrid(removable=False)
        self.attachments.setAcceptDrops(False)
        self.attachments.viewport().setAcceptDrops(False)
        self.attachment_title.toggled.connect(self.attachments.setVisible)
        self.attachments.currentRowChanged.connect(lambda row: self.save_button.setEnabled(row >= 0))
        self.attachments.currentRowChanged.connect(self.update_preview_button)
        self.attachments.itemDoubleClicked.connect(lambda item: self.preview_attachment())
        attachment_layout.addWidget(self.attachments)
        message_layout.addWidget(self.attachment_section)
        message_layout.addWidget(self.tabs,1)
        self.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_subject()

    def fit_subject(self):
        # Un sujet court ne réserve qu'une ligne ; les sujets longs restent défilables.
        height = self.subject.heightForWidth(max(100,self.width()-28))
        self.metadata.setFixedHeight(max(28,min(80,height)))

    def update_more_menu(self):
        for action,button in zip(self.more_menu.actions()[:4],self.action_buttons[:4]):
            action.setEnabled(button.isEnabled())
            action.setIcon(button.icon())

    def set_actions_enabled(self, enabled):
        for button in self.action_buttons:
            button.setEnabled(enabled)

    def shutdown(self):
        """Détruit la page avant son profil, comme requis par WebEngine."""
        if self.disposed:
            return
        self.disposed = True
        from shiboken6 import delete
        self.web.stop()
        delete(self.web.page())
        delete(self.profile)

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def thread_list_widget(self, name, side):
        widget = QListWidget()
        widget.setObjectName('ThreadList')
        widget.setAccessibleName(name)
        widget.setWordWrap(False)
        widget.setTextElideMode(Qt.ElideRight)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        def emit(item, side=side, widget=widget):
            offset = 0 if side == 0 else self.thread_current + 1
            self.threadMessageRequested.emit(offset + widget.row(item))
        widget.itemActivated.connect(emit)
        widget.itemClicked.connect(emit)
        return widget

    @staticmethod
    def fill_thread_list(widget, entries, above=False):
        widget.clear()
        for title,extract,unread,tooltip in entries:
            item = QListWidgetItem(('● ' if unread else '') + title + ('\n' + extract if extract else ''))
            item.setToolTip(tooltip)
            font = item.font()
            font.setBold(unread)
            item.setFont(font)
            widget.addItem(item)
        rows = min(len(entries), 4)  # Au-delà, la liste défile : le message ouvert garde la place.
        widget.setFixedHeight(sum(widget.sizeHintForRow(i) for i in range(rows)) + 8 if entries else 0)
        widget.setVisible(bool(entries))
        if entries:  # Au-dessus, le message juste avant celui ouvert reste visible.
            widget.scrollToBottom() if above else widget.scrollToTop()

    def set_thread(self, entries, current=-1, elsewhere=0):
        """entries : [(qui · quand, extrait, non lu, info-bulle)] du plus ancien au plus récent ; current : message ouvert.
        Moins de deux messages : lecture simple, sans bandeau."""
        visible = len(entries) > 1 and 0 <= current < len(entries)
        self.thread_current = current if visible else -1
        self.fill_thread_list(self.thread_list, entries[:current] if visible else [], above=True)
        self.fill_thread_list(self.thread_after, entries[current+1:] if visible else [])
        self.thread_title.setText(f'CONVERSATION · {len(entries)} MESSAGES · MESSAGE {current+1} SUR {len(entries)}'
                                  + (f' · DONT {elsewhere} DANS D’AUTRES DOSSIERS' if elsewhere else ''))
        self.thread_card.setVisible(visible)
        self.thread_after_card.setVisible(visible and current < len(entries) - 1)

    def clear(self, message='Sélectionnez un message pour le lire.', keep_thread=False):
        if not keep_thread:
            self.set_thread([])
        self.mail = None
        self.preview_revision += 1
        self.interceptor.remote = False
        self.web.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
        self.web.stop()
        self.web.setHtml('')
        self.document.content = b''
        self.headers.clear()
        self.headers.hide()
        self.subject_card.hide()
        self.message_card.hide()
        self.details_action.setChecked(False)
        self.metadata.hide()
        self.subject.clear()
        self.subject.hide()
        self.empty_message.setText(message)
        self.empty_message.show()
        self.tabs.hide()
        self.remote_banner.hide()
        self.danger_banner.hide()
        self.unsubscribe_banner.hide()
        self.invite = None
        self.invite_card.hide()
        self.attachment_title.hide()
        self.attachment_section.hide()
        self.attachments.hide()
        self.save_button.hide()
        self.save_all_button.hide()
        self.preview_button.hide()
        self.text.clear()
        self.attachments.clear()
        self.images.setEnabled(False)
        self.images.setText('Afficher les images')
        self.save_button.setEnabled(False)

    def display(self, mail: Mail, keep_thread=False):
        self.clear(keep_thread=keep_thread)
        self.mail = mail
        self.subject_card.show()
        self.message_card.show()
        self.metadata.show()
        self.subject.show()
        self.subject.setText(mail.subject or '(Sans objet)')
        self.subject.setToolTip(mail.subject)
        self.fit_subject()
        name,address = parseaddr(mail.sender)
        self.sender_name.setText(name or address or mail.sender)
        self.sender_name.setToolTip(mail.sender)
        self.sender_address.setText(address if name else '')
        self.sender_address.setToolTip(address)
        self.sender_address.setVisible(bool(name and address))
        self.avatar.setText(''.join(word[0] for word in (name or address or '?').split()[:2]).upper())
        self.recipient_summary.setText('À : '+mail.recipients)
        self.recipient_summary.setToolTip('À : '+mail.recipients+('\nCc : '+mail.cc if mail.cc else ''))
        try:
            date = parsedate_to_datetime(mail.date).astimezone().strftime('%d/%m/%Y %H:%M')
        except (TypeError,ValueError,OverflowError):
            date = mail.date
        self.date_label.setText(date)
        self.date_label.setToolTip(mail.date)
        self.empty_message.hide()
        self.tabs.show()
        self.has_remote_images = RemoteImages(safe_document(mail,True,self.dark)).found if mail.html else False
        self.remote_banner.setVisible(self.has_remote_images)
        self.danger_banner.setVisible(any(dangerous_filename(a.name) for a in mail.attachments))
        self.unsubscribe_banner.setVisible(bool(unsubscribe_options(mail.list_unsubscribe, mail.list_unsubscribe_post)))
        self.show_invite(mail)
        self.attachment_title.setVisible(bool(mail.attachments))
        self.attachments.hide()
        self.save_button.setVisible(bool(mail.attachments))
        self.save_all_button.setVisible(len(mail.attachments) > 1)
        self.preview_button.setVisible(bool(mail.attachments))
        self.update_preview_button(self.attachments.currentRow())
        self.attachment_section.setVisible(bool(mail.attachments))
        self.attachment_title.setText(f'Pièces jointes · {len(mail.attachments)}')
        self.attachment_title.setChecked(False)
        cc = f'\nCc : {mail.cc}' if mail.cc else ''
        self.headers.setText(f'De : {mail.sender}\nÀ : {mail.recipients}{cc}\nDate : {mail.date}')
        self.text.setPlainText(mail.text or 'Ce message ne contient pas de version texte brut. Consultez l’onglet HTML sécurisé.')
        self.tabs.setCurrentIndex(0 if mail.html else 1)
        self.images.setEnabled(self.has_remote_images)
        self.render_html()
        for attachment in mail.attachments:
            size = f'{len(attachment.data)/1048576:.1f} Mo' if len(attachment.data)>=1048576 else f'{len(attachment.data)/1024:.1f} Ko'
            item = QListWidgetItem(f'{attachment.name}\n{size.replace(".",",")}')
            item.setToolTip(attachment.name)
            item.setIcon(icon('shield-alert' if dangerous_filename(attachment.name) else 'file-text',self.theme.colors['muted'],48))
            self.attachments.addItem(item)
        if mail.attachments:
            self.attachments.setCurrentRow(0)
            revision = self.preview_revision
            def done(previews):
                if not isValid(self) or self.disposed or revision != self.preview_revision:
                    return
                for index,image,description in previews:
                    item = self.attachments.item(index)
                    if not image.isNull():
                        item.setIcon(QIcon(QPixmap.fromImage(image)))
                        item.setData(Qt.UserRole,True)
                    if description:
                        item.setToolTip(item.toolTip()+'\n'+description)
            self.preview_runner.run(lambda:[(i,*thumbnail(a)) for i,a in enumerate(mail.attachments)],done,lambda error:None)

    def show_images(self):
        if self.mail is None:
            return
        self.interceptor.remote = True
        self.web.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.render_html(True)
        self.remote_banner.hide()
        self.images.setEnabled(False)

    def render_html(self, remote=False):
        document = safe_document(self.mail, remote, self.dark)
        # Habillage du document assaini : aucune règle provenant du mail n'est ajoutée.
        colors = self.theme.colors
        reading_style = ('<style>html{background:'+colors['surface']+'}body{box-sizing:border-box;'
            'font-family:"Segoe UI",sans-serif;font-size:15px;line-height:1.6;max-width:920px;'
            'margin:0 auto;padding:20px 24px;color:'+colors['text']+';background:'+colors['surface']+'}'
            'p{margin:0 0 16px}h1,h2,h3{line-height:1.3}td,th{padding:6px 10px;text-align:left}'
            '@media(max-width:540px){body{padding:14px 8px}}</style>')
        document = document.replace('</head>',reading_style+'</head>')
        self.document.content = document.encode('utf-8')
        self.generation += 1
        self.web.load(QUrl(f'smail://message/current?v={self.generation}'))

    def set_dark(self, dark):
        self.dark = dark
        if self.disposed:
            return
        self.layout().setContentsMargins(0,0,0,0)
        if self.mail is not None:
            self.render_html(self.interceptor.remote)

    def show_invite(self, mail):
        from mailclient.core import invite as invites
        self.invite, self.invite_attachment = invites.find(mail)
        if self.invite is None:
            self.invite_card.hide()
            return
        invite = self.invite
        title = invite.summary or 'Invitation'
        self.invite_title.setText(('Événement annulé : ' if invite.cancelled else 'Invitation : ') + title)
        details = [invites.when(invite)]
        if invite.location:
            details.append('Lieu : ' + invite.location)
        if invite.organizer:
            details.append('Organisateur : ' + (f'{invite.organizer_name} <{invite.organizer}>' if invite.organizer_name else invite.organizer))
        self.invite_details.setText('\n'.join(details))
        for button in self.invite_buttons.values():
            button.setVisible(invite.answerable)
            button.setEnabled(True)
        self.invite_card.show()

    def invite_answered(self, label_text):
        """Après l’envoi : la réponse donnée remplace les boutons."""
        for button in self.invite_buttons.values():
            button.hide()
        self.invite_details.setText(self.invite_details.text() + f'\nVotre réponse « {label_text} » a été envoyée.')

    def update_preview_button(self, row):
        from mailclient.ui.attachment_preview import preview_kind
        attachments = self.mail.attachments if self.mail else []
        possible = 0 <= row < len(attachments) and preview_kind(attachments[row]) is not None
        self.preview_button.setEnabled(possible)
        self.preview_button.setToolTip('Aperçu de la pièce jointe sélectionnée (double-clic)' if possible or row < 0 else
                                       'Aperçu indisponible pour ce type de fichier : utilisez « Enregistrer… ».')

    def preview_attachment(self):
        from mailclient.ui.attachment_preview import AttachmentPreview, preview_kind
        row = self.attachments.currentRow()
        if self.mail is None or not 0 <= row < len(self.mail.attachments):
            return
        attachment = self.mail.attachments[row]
        if preview_kind(attachment) is None:
            return
        self.preview_dialog = AttachmentPreview(attachment, self.save_attachment, self)
        self.preview_dialog.open()

    def print_message(self):
        if self.mail is None:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter(QPrinter.HighResolution)
        printer.setDocName(self.mail.subject or 'Message')
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle('Imprimer le message')
        if dialog.exec():
            print_document(self.mail).print_(printer)

    def save_all_attachments(self, folder=None):
        """Toutes les pièces jointes dans un dossier : noms assainis, rien d’écrasé, fichiers dangereux sur accord."""
        from mailclient.core.parser import safe_filename
        if self.mail is None or not self.mail.attachments:
            return
        folder = folder or QFileDialog.getExistingDirectory(self, 'Enregistrer toutes les pièces jointes dans…')
        if not folder:
            return
        attachments = list(self.mail.attachments)
        risky = [a.name for a in attachments if dangerous_filename(a.name)]
        if risky and QMessageBox.warning(
                self, 'Fichiers potentiellement dangereux',
                'Ces fichiers peuvent exécuter du code : ' + ', '.join(risky) + '.\n\nLes enregistrer aussi ? '
                '(Ils ne seront pas ouverts par Smail.) « Non » enregistre seulement les autres.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            attachments = [a for a in attachments if not dangerous_filename(a.name)]
        saved, failed = 0, []
        for attachment in attachments:
            name = safe_filename(attachment.name) or 'piece-jointe'
            target, number = Path(folder) / name, 2
            while target.exists():  # Jamais d’écrasement : « rapport (2).pdf ».
                target = Path(folder) / f'{Path(name).stem} ({number}){Path(name).suffix}'
                number += 1
            destination = QSaveFile(str(target))
            if destination.open(QIODevice.WriteOnly) and destination.write(attachment.data) == len(attachment.data) \
                    and destination.commit():
                saved += 1
            else:
                destination.cancelWriting()
                failed.append(attachment.name)
        message = f'{saved} pièce{"s" if saved > 1 else ""} jointe{"s" if saved > 1 else ""} enregistrée{"s" if saved > 1 else ""} dans {folder}.'
        if failed:
            message += '\n\nÉchec pour : ' + ', '.join(failed)
        QMessageBox.information(self, 'Pièces jointes', message)
        return saved

    def save_attachment(self):
        row = self.attachments.currentRow()
        if self.mail is None or row < 0:
            return
        attachment = self.mail.attachments[row]
        path, _ = QFileDialog.getSaveFileName(self, 'Enregistrer une pièce jointe', attachment.name)
        if not path:
            return
        if dangerous_filename(attachment.name) or dangerous_filename(Path(path).name):
            result = QMessageBox.warning(self, 'Fichier potentiellement dangereux',
                'Ce fichier peut exécuter du code. Enregistrez-le uniquement si vous faites confiance à son origine. Il ne sera pas ouvert par Smail.',
                QMessageBox.Save | QMessageBox.Cancel, QMessageBox.Cancel)
            if result != QMessageBox.Save:
                return
        destination = QSaveFile(path)
        if not destination.open(QIODevice.WriteOnly):
            QMessageBox.critical(self, 'Enregistrement impossible', 'Impossible d’écrire à cet emplacement.')
            return
        if destination.write(attachment.data) != len(attachment.data) or not destination.commit():
            destination.cancelWriting()
            QMessageBox.critical(self, 'Enregistrement impossible', 'Le fichier n’a pas pu être enregistré intégralement.')
