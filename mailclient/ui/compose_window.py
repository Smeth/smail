"""Rédaction, réponses et brouillons locaux sauvegardés en arrière-plan."""
from mailclient.i18n import tr, N_
import base64
import re
from uuid import uuid4
from email.utils import getaddresses
import bleach
from PySide6.QtCore import QTimer, Qt, QSize
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QListWidgetItem, QFileDialog, QLabel, QMessageBox, QWidget, QMenu, QSizePolicy)
from mailclient.core.parser import Attachment
from mailclient.core.smtp_client import build_message, send_message, addresses, display_address
from mailclient.core.sync import Runner
from mailclient.ui.dialog_shell import appearance
from mailclient.ui.components import Button, Card, label
from PySide6.QtGui import QShortcut, QKeySequence, QIcon, QPixmap
from mailclient.ui.icons import icon
from mailclient.ui.attachment_widgets import (AttachmentGrid, ComposeEditor, IMAGE_FILTER,
    read_attachments, thumbnail, clipboard_attachment, local_paths, clipboard_image, CHIP)
from mailclient.core.html_security import dangerous_filename
from mailclient.ui.address_completer import AddressCompleter
from mailclient.ui.rich_text import FormatBar
from PySide6.QtGui import QTextCharFormat
from shiboken6 import isValid

SIZE_WARNING = 25_000_000  # Limite courante des messageries (Gmail, Outlook), encodage compris.

def forwarded(mail, text):
    """Message transféré recopié tel quel (sans « > ») sous un en-tête, comme Outlook et Gmail."""
    lines = [tr('---------- Message transféré ----------'), tr('De : {value}').format(value=mail.sender),
             tr('Date : {value}').format(value=mail.date), tr('Objet : {value}').format(value=mail.subject),
             tr('À : {value}').format(value=mail.recipients)]
    if mail.cc:
        lines.append(tr('Cc : {value}').format(value=mail.cc))
    return '\n'.join(lines) + '\n\n' + text


def reply_fields(mail, account, mode):
    text = mail.text or bleach.clean(mail.html, tags=set(), strip=True)
    quoted = '\n'.join('> ' + line for line in text.splitlines())
    prefix = 'Tr: ' if mode == 'forward' else 'Re: '
    subject = mail.subject if mail.subject.lower().startswith(prefix.lower()) else prefix + mail.subject
    to, cc = '', ''
    if mode != 'forward':
        pairs = getaddresses([mail.reply_to or mail.sender])
        to = ', '.join(display_address(pair) for pair in pairs if pair[1].casefold() != account.email.casefold())
        if not to:
            to = mail.reply_to or mail.sender
        if mode == 'reply_all':
            seen = {account.email.casefold(), *(address.casefold() for _, address in getaddresses([to]))}
            extra = []
            for pair in getaddresses([mail.recipients, mail.cc]):
                if pair[1] and pair[1].casefold() not in seen:
                    seen.add(pair[1].casefold())
                    extra.append(display_address(pair))
            cc = ', '.join(extra)
    ids = re.findall(r'<[^<>\s]+>', mail.message_id)
    refs = re.findall(r'<[^<>\s]+>', mail.references)
    return dict(to=to, cc=cc, bcc='', subject=subject,
                body=f'\n\n{account.signature}\n\n' + (forwarded(mail, text) if mode == 'forward' else
                     tr('Le {date}, {sender} a écrit :').format(date=mail.date, sender=mail.sender) + f'\n{quoted}'),
                reply_id=ids[0] if ids and mode != 'forward' else '',
                references=' '.join((refs + ids)[-20:]) if mode != 'forward' else '',
                attachments=mail.attachments if mode == 'forward' else [])

class ComposeWindow(QDialog):
    def __init__(self, service, accounts, selected=None, fields=None, draft=None, parent=None, offline=None):
        super().__init__(parent)
        self.service, self.accounts = service, list(accounts)
        self.offline = offline or (lambda: False)
        self.last_copy_id = None
        self.runner = Runner(self, service.tls)
        self.id = draft['id'] if draft else str(uuid4())
        self.busy = self.saving = self.close_when_saved = False
        self.countdown = None
        self.delivered = False
        self.revision, self.saved_revision = 1, 0
        self.files = []
        self._adding_files = False
        self._preview_generation = 0
        self._preview_cache = {}
        self.reply_id = self.references = ''
        self.setWindowTitle(tr('Rédiger un message'))
        self.appearance = appearance()
        self.setMinimumSize(580, 500)
        available = self.screen().availableGeometry()
        self.resize(min(760, available.width()-48), min(680, available.height()-64))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16,16,16,12)
        outer.setSpacing(10)
        outer.addWidget(label(tr('Nouveau message'), 'MessageTitle'))
        content = Card('ComposeCard', 14)
        layout = content.box
        layout.setSpacing(8)
        outer.addWidget(content, 1)
        form = self.form = QFormLayout()
        form.setVerticalSpacing(6)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.account_box = QComboBox()
        for account in accounts:
            self.account_box.addItem(account.email if account.name == account.email else f'{account.name} — {account.email}', account.id)
        wanted = draft.get('account') if draft else selected.id if selected else None
        if wanted:
            self.account_box.setCurrentIndex(max(0, self.account_box.findData(wanted)))
        form.addRow(tr('De'), self.account_box)
        self.to, self.cc, self.bcc, self.subject = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        try:
            contacts = service.contacts(self.accounts) if hasattr(service, 'contacts') else []
        except Exception:
            contacts = []  # Carnet illisible (clé du coffre absente…) : la saisie reste libre.
        for field in (self.to, self.cc, self.bcc):
            field.setCompleter(AddressCompleter(contacts, field))
        recipient = QHBoxLayout()
        recipient.setContentsMargins(0,0,0,0)
        recipient.addWidget(self.to,1)
        self.recipient_toggles = []
        for title,field in [(N_('Cc'),self.cc),(N_('Cci'),self.bcc)]:
            title = tr(title)
            toggle = Button(title,self.appearance)
            toggle.setCheckable(True)
            toggle.setToolTip(tr('Afficher ou masquer {title}').format(title=title))
            toggle.toggled.connect(lambda checked,widget=field:form.setRowVisible(widget,checked))
            recipient.addWidget(toggle)
            self.recipient_toggles.append(toggle)
        form.addRow(tr('À'), recipient)
        for title, widget in [(N_('Cc'),self.cc),(N_('Cci'),self.bcc),(N_('Objet'),self.subject)]:
            form.addRow(tr(title),widget)
        form.setRowVisible(self.cc,False)
        form.setRowVisible(self.bcc,False)
        layout.addLayout(form)
        self.body = ComposeEditor()
        self.body.setObjectName('ComposeBody')
        self.body.setMinimumHeight(100)
        self.body.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.body.setPlaceholderText(tr('Écrivez votre message…'))
        from mailclient.ui.spelling import install as install_spelling
        install_spelling(self.body, getattr(service, 'db', None))  # Fautes soulignées, suggestions au clic droit.
        self.body.setAccessibleName(tr('Corps du message'))
        self.body.setTabChangesFocus(True)
        self.format_bar = FormatBar(self.body, self.appearance)
        layout.addWidget(self.format_bar)
        layout.addWidget(self.body, 1)
        self.attachment_panel = QWidget()
        attachment_layout = QVBoxLayout(self.attachment_panel)
        attachment_layout.setContentsMargins(0,0,0,0)
        attachment_layout.setSpacing(2)
        attachment_header = QHBoxLayout()
        self.attachment_label = label(tr('Pièces jointes'),'Small')
        attachment_header.addWidget(self.attachment_label)
        attachment_header.addStretch()
        # Chaque étiquette a son propre × : ce bouton global ne sert plus qu’au clavier et reste masqué.
        self.remove_file = Button('',self.appearance,'x',tooltip=tr('Retirer la pièce jointe sélectionnée'))
        self.remove_file.setFixedSize(30,30)
        self.remove_file.hide()
        attachment_layout.addLayout(attachment_header)
        self.attachments = AttachmentGrid()
        attachment_layout.addWidget(self.attachments)
        layout.addWidget(self.attachment_panel)
        self.attachment_hint = label(tr('Glissez des fichiers ici ou collez une image dans le message.'),'Small',True)
        layout.addWidget(self.attachment_hint)
        buttons = QHBoxLayout()
        self.add_file = Button(tr('Joindre'),self.appearance,'paperclip','Secondary',tr('Joindre des fichiers (ou glissez-les dans la fenêtre)'))
        self.add_image = Button(tr('Image'),self.appearance,'plus','Secondary',tr('Joindre des images (ou collez-les dans le message)'))
        self.send_button = Button(tr('Envoyer'),self.appearance,'send','Primary')
        self.server_button = Button(tr('Copier aux brouillons du serveur'),self.appearance,'file-pen-line','Secondary')
        self.discard_button = Button(tr('Supprimer le brouillon'),self.appearance,'trash-2','QuietDanger')
        # Les actions secondaires restent disponibles dans un menu compact.
        self.server_button.setParent(self)
        self.discard_button.setParent(self)
        self.server_button.hide()
        self.discard_button.hide()
        self.draft_menu = QMenu(self)
        self.server_action = self.draft_menu.addAction(tr('Enregistrer aussi dans les Brouillons du serveur'),self.server_button.click)
        self.draft_menu.addSeparator()
        self.discard_action = self.draft_menu.addAction(tr('Supprimer ce brouillon'),self.discard_button.click)
        # Le brouillon est enregistré sur ce PC automatiquement ; ce menu propose le reste.
        self.more_button = Button(tr('Enregistrer'),self.appearance,'file-pen-line',
                                  tooltip=tr('Le brouillon est enregistré automatiquement sur ce PC. Menu : copie sur le serveur, suppression.'))
        self.more_button.setMenu(self.draft_menu)
        self.draft_menu.aboutToShow.connect(self.update_draft_menu)
        for button in (self.add_file,self.add_image,self.more_button):
            buttons.addWidget(button)
        buttons.addStretch()
        self.later_button = Button('',self.appearance,'clock','Secondary',tr('Envoyer plus tard…'))
        self.later_button.setAccessibleName(tr('Envoyer plus tard'))
        self.later_button.clicked.connect(self.send_later)
        buttons.addWidget(self.later_button)
        buttons.addWidget(self.send_button)
        outer.addLayout(buttons)
        self.discard_button.clicked.connect(self.discard)
        self.status = QLabel(tr('Brouillon local enregistré automatiquement après modification.'))
        self.status.setObjectName('Small')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        outer.addWidget(self.status)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(1500)
        self.debounce.timeout.connect(self.save_draft)
        self.periodic = QTimer(self)
        self.periodic.setInterval(20_000)
        self.periodic.timeout.connect(self.save_draft)
        self.periodic.start()
        self.countdown = None
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self.tick_countdown)
        values = draft or fields or dict(body='\n\n' + (self.current_account().signature if self.accounts else ''))
        for key, widget in [('to', self.to), ('cc', self.cc), ('bcc', self.bcc), ('subject', self.subject)]:
            widget.setText(values.get(key, ''))
        for toggle,field in zip(self.recipient_toggles,(self.cc,self.bcc)):
            toggle.setChecked(bool(field.text()))
        self.fill_body(values, restoring=bool(draft))
        self.reply_id, self.references = values.get('reply_id', ''), values.get('references', '')
        if draft:
            self.files = [Attachment(item['name'], item['type'], base64.b64decode(item['data'])) for item in values.get('attachments', [])]
        else:
            self.files = list(values.get('attachments', []))
        self.show_files()
        for widget in (self.to, self.cc, self.bcc, self.subject):
            widget.textChanged.connect(self.changed)
        self.body.textChanged.connect(self.changed)
        self.account_box.currentIndexChanged.connect(self.account_changed)
        self.add_file.clicked.connect(self.choose_files)
        self.add_image.clicked.connect(lambda:self.choose_files(images_only=True))
        self.attachments.pathsAdded.connect(self.add_paths)
        self.body.pathsAdded.connect(self.add_paths)
        self.attachments.imageAdded.connect(self.add_clipboard_image)
        self.body.imageAdded.connect(self.add_clipboard_image)
        self.remove_file.clicked.connect(self.remove_attachment)
        self.attachments.removeRequested.connect(self.remove_at)
        self.subject.textChanged.connect(self.update_title)
        self.update_title()
        self.send_button.clicked.connect(self.send)
        self.server_button.clicked.connect(self.save_server_draft)
        QShortcut(QKeySequence('Ctrl+Return'),self,activated=lambda:None if self.countdown else self.send())
        self.debounce.start()
        self.setAcceptDrops(True)
        self.to.setFocus()

    def fill_body(self, values, restoring):
        """Brouillon : restitué avec sa mise en forme. Nouveau message ou réponse : signature du compte,
        mise en forme si elle a été définie ainsi, insérée à sa place habituelle (avant la citation)."""
        if restoring and values.get('qt_html'):
            self.body.setHtml(values['qt_html'])
            return
        body = values.get('body', '')
        account = self.current_account() if self.accounts else None
        stored = self.service.signature(account) if account and hasattr(self.service, 'signature') else None
        prefix = f'\n\n{account.signature}' if account else ''
        if restoring or not stored or not account.signature or not body.startswith(prefix):
            self.body.setPlainText(body)
            return
        self.body.clear()
        cursor = self.body.textCursor()
        cursor.insertText('\n\n')
        self.body.insert_html(cursor, stored['qt_html'])
        rest = body[len(prefix):]  # Citation d’une réponse, avec ses propres sauts de ligne.
        if rest:
            cursor.insertText(rest, QTextCharFormat())
        cursor.setPosition(0)
        self.body.setTextCursor(cursor)

    def update_draft_menu(self):
        self.server_action.setEnabled(self.server_button.isEnabled())
        self.discard_action.setEnabled(self.discard_button.isEnabled())

    def current_account(self):
        return self.accounts[self.account_box.currentIndex()]

    def account_changed(self):
        self.status.setText(tr('Compte expéditeur changé. Vérifiez la signature avant l’envoi.'))
        self.changed()

    def changed(self, *_):
        self.revision += 1
        self.debounce.start()

    def state(self):
        # Conversion dans le fil graphique : le document Qt ne doit pas être lu depuis une tâche réseau.
        mail_html, text = self.body.mail_parts()
        return dict(id=self.id, account=self.current_account().id, to=self.to.text(), cc=self.cc.text(),
                    bcc=self.bcc.text(), subject=self.subject.text(), body=text, mail_html=mail_html,
                    qt_html=self.body.toHtml() if mail_html else '',
                    reply_id=self.reply_id, references=self.references)

    def set_busy(self, busy):
        busy = busy or self._adding_files
        self.busy = busy
        for widget in (self.account_box, self.to, self.cc, self.bcc, self.subject, self.body, self.add_file, self.add_image, self.remove_file, self.attachments,*self.recipient_toggles):
            widget.setEnabled(not busy and not self.delivered)
        self.remove_file.setEnabled(not busy and not self.delivered and bool(self.files))
        self.send_button.setEnabled(bool(self.countdown) or (not busy and not self.saving and not self.delivered))
        self.later_button.setEnabled(not busy and not self.saving and not self.delivered)
        self.format_bar.setEnabled(not busy and not self.delivered)
        self.server_button.setEnabled(not busy and not self.saving and not self.delivered)
        self.discard_button.setEnabled(not busy and not self.saving and not self.delivered)
        self.update_draft_menu()

    def save_draft(self):
        if self.saving or self.busy or self.delivered or self.saved_revision == self.revision:
            return
        state, files, revision = self.state(), list(self.files), self.revision
        self.saving = True
        self.set_busy(self.busy)
        def operation():
            state['attachments'] = [dict(name=a.name, type=a.content_type, data=base64.b64encode(a.data).decode('ascii')) for a in files]
            self.service.db.cache_put('draft', self.id, state)
        def done(_):
            self.saving = False
            self.saved_revision = revision
            self.set_busy(False)
            self.status.setText(tr('Brouillon enregistré sur ce PC.'))
            if self.revision != revision:
                self.debounce.start()
            elif self.close_when_saved:
                self.close()
        def failed(message):
            self.saving = False
            self.close_when_saved = False
            self.set_busy(False)
            self.status.setText(tr('Brouillon non enregistré : ') + message)
        self.runner.run(operation, done, failed)

    @staticmethod
    def size_text(size):
        text = tr('{valeur:.1f} Mo').format(valeur=size/1_000_000) if size >= 1_000_000 else tr('{valeur} Ko').format(valeur=max(1, round(size/1000)))
        return text.replace('.', ',')

    def update_title(self, *_):
        """Titre de la fenêtre : l’objet du message, pour distinguer plusieurs rédactions ouvertes."""
        self.setWindowTitle((self.subject.text().strip() or tr('Nouveau message')) + tr(' — Smail'))

    def update_attachment_total(self):
        """« Pièces jointes · 4 · 7,4 Mo », en orange quand le message dépassera 25 Mo une fois encodé."""
        total = sum(len(attachment.data) for attachment in self.files)
        encoded = total * 4 // 3  # Les pièces jointes grossissent d’environ un tiers à l’envoi.
        text = tr('Pièces jointes · {valeur} · {valeur2}').format(valeur=len(self.files), valeur2=self.size_text(total))
        if encoded > SIZE_WARNING:
            text += tr(' — environ {size} à l’envoi : risque de refus chez le destinataire').format(size=self.size_text(encoded))
        self.attachment_label.setText(text)
        self.attachment_label.setStyleSheet(f'color: {self.appearance.colors["warning"]};' if encoded > SIZE_WARNING else '')

    def remove_at(self, row):
        if 0 <= row < len(self.files) and not self.busy and not self.delivered:
            self.files.pop(row)
            self.show_files()
            self.changed()

    def show_files(self):
        selected = self.attachments.currentRow()
        self._preview_generation += 1
        generation = self._preview_generation
        self.attachments.clear()
        self.attachment_panel.setVisible(bool(self.files))
        self.attachment_hint.setVisible(not self.files)
        self.update_attachment_total()
        pending = []
        keep = {id(attachment) for attachment in self.files}
        self._preview_cache = {key:value for key,value in self._preview_cache.items() if key in keep}
        for index,attachment in enumerate(self.files):
            size = f'{len(attachment.data)/1048576:.1f} Mo' if len(attachment.data) >= 1048576 else f'{len(attachment.data)/1024:.1f} Ko'
            item = QListWidgetItem(f'{attachment.name}\n{size.replace(".",",")}')
            item.setSizeHint(CHIP)
            item.setToolTip(tr('{name}\n{valeur:,} octets').format(name=attachment.name, valeur=len(attachment.data)))
            item.setIcon(icon('shield-alert' if dangerous_filename(attachment.name) else 'file-text',self.appearance.colors['muted'],48))
            item.setData(Qt.UserRole,False)
            self.attachments.addItem(item)
            cached = self._preview_cache.get(id(attachment))
            if cached is not None:
                self.set_thumbnail(item,*cached)
            else:
                pending.append((index,attachment))
        if self.files:
            self.attachments.setCurrentRow(max(0,min(selected,len(self.files)-1)))
            self.attachments.fit()
        if hasattr(self,'remove_file'):
            self.remove_file.setEnabled(bool(self.files) and not self.busy and not self.delivered)
        if not pending:
            return
        def operation():
            return [(index,id(attachment),*thumbnail(attachment)) for index,attachment in pending]
        def done(previews):
            if not isValid(self) or generation != self._preview_generation:
                return
            for index,key,image,description in previews:
                self._preview_cache[key] = (image,description)
                item = self.attachments.item(index)
                if item:
                    self.set_thumbnail(item,image,description)
        self.runner.run(operation,done,lambda message:None)

    def set_thumbnail(self, item, image, description):
        if not image.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(image)))
            item.setData(Qt.UserRole,True)
        if description:
            item.setToolTip(item.toolTip()+'\n'+description)

    def choose_files(self, checked=False, images_only=False):
        if self.busy or self.delivered:
            return
        paths, _ = QFileDialog.getOpenFileNames(self,tr('Ajouter des images') if images_only else tr('Joindre des fichiers'),'',
            tr(IMAGE_FILTER) if images_only else tr('Tous les fichiers (*);;Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tif *.tiff *.ico *.avif)'))
        self.add_paths(paths)

    def add_paths(self, paths):
        if not paths or self.busy or self.delivered:
            return
        self._adding_files = True
        self.set_busy(True)
        self.status.setText(tr('Ajout des fichiers en cours…'))
        def done(result):
            files, errors = result
            self.files.extend(files)
            self._adding_files = False
            self.show_files()
            self.set_busy(False)
            if files:
                self.changed()
            self.status.setText(tr('{valeur} fichier(s) ajouté(s).').format(valeur=len(files))+(tr(' Impossible de lire : ')+', '.join(errors) if errors else tr(' Les images apparaissent en miniature.')))
        def failed(message):
            self._adding_files = False
            self.failure(message)
        self.runner.run(lambda:read_attachments(list(paths)),done,failed)

    def add_clipboard_image(self, image):
        if image.isNull() or self.busy or self.delivered:
            return
        names = {attachment.name for attachment in self.files}
        number = 1
        while f'image-collee-{number}.png' in names:
            number += 1
        name = f'image-collee-{number}.png'
        self._adding_files = True
        self.set_busy(True)
        def done(attachment):
            self.files.append(attachment)
            self._adding_files = False
            self.show_files()
            self.set_busy(False)
            self.changed()
            self.status.setText(tr('Image collée et ajoutée en pièce jointe.'))
        def failed(message):
            self._adding_files = False
            self.failure(message)
        self.runner.run(lambda:clipboard_attachment(image,name),done,failed)

    def dragEnterEvent(self, event):
        if not self.busy and not self.delivered and (local_paths(event.mimeData()) or event.mimeData().hasImage()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.busy or self.delivered:
            event.ignore()
            return
        paths = local_paths(event.mimeData())
        if paths:
            self.add_paths(paths)
        else:
            image = clipboard_image(event.mimeData())
            if image.isNull():
                event.ignore()
                return
            self.add_clipboard_image(image)
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def remove_attachment(self):
        row = self.attachments.currentRow()
        if row >= 0:
            self.files.pop(row)
            self.show_files()
            self.changed()

    def message(self, state, files, allow_empty=False):
        account = next(a for a in self.accounts if a.id == state['account'])
        return build_message(account, state['to'], state['cc'], state['bcc'], state['subject'],
                             state['body'], files, state['reply_id'], state['references'], allow_empty,
                             html=state.get('mail_html', ''))

    def failure(self, message):
        self.set_busy(False)
        self.status.setText(message)

    def send(self):
        if self.countdown:
            self.cancel_countdown()  # Pendant le délai, le bouton Envoyer devient « Annuler l’envoi ».
            return
        if self.busy or self.saving or self.delivered:
            return
        if self.offline():
            self.status.setText(tr('Mode hors ligne : reconnectez Smail avant d’envoyer. Le brouillon reste enregistré sur ce PC.'))
            return
        if not self.subject.text().strip() and QMessageBox.question(self, tr('Objet vide'), tr('Envoyer ce message sans objet ?'), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        state, files, account = self.state(), list(self.files), self.current_account()
        try:
            message, _ = self.message(state, files)  # Adresses et en-têtes vérifiés avant tout délai d’annulation.
        except ValueError as error:
            self.status.setText(str(error))
            return
        size = len(message.as_bytes())
        if size > SIZE_WARNING and QMessageBox.warning(
                self, tr('Message volumineux'),
                f'Ce message fait {size / 1_000_000:.1f} Mo une fois encodé'.replace('.', ',') + tr(' (les pièces jointes grossissent d’environ un tiers).\n\n'
                'Beaucoup de messageries (Outlook, Microsoft 365, messageries d’entreprise) refusent les messages de plus de '
                '20 à 35 Mo ; Gmail accepte jusqu’à 50 Mo. Selon le destinataire, il risque de ne jamais arriver, et le refus '
                'n’apparaît que plus tard, par un message d’erreur dans votre boîte de réception.\n\n'
                'Conseil : retirez des pièces jointes ou partagez-les par un lien (OneDrive, Google Drive…).\n\n'
                'Envoyer quand même ?'), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        delay = int(self.service.db.setting('undo_send_seconds', 10) or 0) if hasattr(self.service, 'db') else 0
        queue = getattr(self.parent(), 'send_queue', None)
        if queue is not None:
            self.hand_over(queue, state, files, account, delay)
        elif delay > 0:
            self.start_countdown(state, files, account, delay)
        else:
            self.deliver(state, files, account)

    def hand_over(self, queue, state, files, account, delay):
        """Envoi en arrière-plan : le message rejoint la boîte d’envoi et la fenêtre se ferme aussitôt.

        Le délai d’annulation et la progression s’affichent en bas de la fenêtre principale ;
        « Annuler » y rouvre le message en brouillon."""
        try:
            queue.enqueue(account, state, files, delay, self.id)
        except (ValueError, RuntimeError) as error:
            self.status.setText(str(error))
            return
        try:
            self.service.db.cache_delete('draft', self.id)  # Le message vit désormais dans la boîte d’envoi.
        except Exception:
            pass
        self.delivered = True
        self.saved_revision = self.revision
        self.debounce.stop()
        self.periodic.stop()
        self.close()

    # Annulation d’envoi : le message part à la fin du délai, ou tout de suite si la fenêtre est fermée.
    def start_countdown(self, state, files, account, delay):
        self.debounce.stop()
        self.countdown = dict(state=state, files=files, account=account, left=delay)
        self.set_busy(True)
        self.countdown_timer.start()
        self.show_countdown()

    def show_countdown(self):
        left = self.countdown['left']
        self.send_button.setText(tr('Annuler l’envoi ({left} s)').format(left=left))
        self.status.setText(tr('Envoi dans {left} s. Cliquez sur « Annuler l’envoi » pour reprendre le message ; fermer la fenêtre l’envoie tout de suite.').format(left=left))

    def tick_countdown(self):
        if not self.countdown:
            return
        self.countdown['left'] -= 1
        if self.countdown['left'] > 0:
            self.show_countdown()
            return
        self.flush_countdown()

    def flush_countdown(self):
        pending, self.countdown = self.countdown, None
        self.countdown_timer.stop()
        self.send_button.setText(tr('Envoyer'))
        self.deliver(pending['state'], pending['files'], pending['account'])

    def cancel_countdown(self):
        self.countdown_timer.stop()
        self.countdown = None
        self.send_button.setText(tr('Envoyer'))
        self.set_busy(False)
        self.status.setText(tr('Envoi annulé. Le message reste modifiable et son brouillon est conservé.'))
        self.changed()

    def send_later(self):
        if self.busy or self.saving or self.delivered or self.countdown:
            return
        from mailclient.ui.schedule_dialog import ScheduleDialog
        from mailclient.core import scheduler
        state, files, account = self.state(), list(self.files), self.current_account()
        try:
            self.message(state, files)
        except ValueError as error:
            self.status.setText(str(error))
            return
        dialog = ScheduleDialog(tr('Envoyer plus tard'), tr('Smail enverra ce message à l’heure choisie, s’il est ouvert à ce moment-là '
                                '(sinon au prochain démarrage).'), 'send', self)
        if not dialog.exec():
            return
        try:
            scheduler.schedule(self.service.db, account, state, files, dialog.moment, self.id)
            self.service.db.cache_delete('draft', self.id)
        except (ValueError, RuntimeError) as error:
            self.status.setText(str(error))
            return
        self.delivered = True
        self.saved_revision = self.revision
        self.debounce.stop()
        self.periodic.stop()
        owner = self.parent()
        if owner is not None and hasattr(owner, 'statusBar'):
            owner.statusBar().showMessage(tr('Envoi programmé le {moment:%d/%m à %H:%M} (Fichier › Envois programmés).').format(moment=dialog.moment))
        self.close()

    def deliver(self, state, files, account):
        from mailclient.core.scheduler import send_and_record
        self.set_busy(True)
        self.debounce.stop()
        self.status.setText(tr('Envoi en cours… Ne fermez pas cette fenêtre.'))
        def operation():
            return send_and_record(self.service, account, state, files)
        def done(result):
            raw, refused, self.last_copy_id = result
            self.set_busy(False)
            if refused:
                rejected = {value.casefold() for value in refused}
                for widget in (self.to, self.cc, self.bcc):
                    widget.setText(', '.join(display_address(pair) for pair in addresses(widget.text()) if pair[1].casefold() in rejected))
                self.changed()
                self.status.setText(tr('Envoi partiel : seuls les destinataires refusés restent dans ce brouillon. Les autres ont reçu le message.'))
            else:
                self.delivered = True
                try:
                    self.service.db.cache_delete('draft', self.id)
                except Exception:
                    self.status.setText(tr('Message envoyé, mais le brouillon local n’a pas pu être supprimé. Ne le renvoyez pas.'))
                self.saved_revision = self.revision
                self.debounce.stop()
                self.periodic.stop()
                self.status.setText(tr('Message accepté par le serveur SMTP. Enregistrement de la copie dans Envoyés…'))
                self.set_busy(False)
            self.copy_to_server(raw, draft=False, close_after=not refused)
        def failed(message):
            uncertain = message.startswith(tr('Le serveur d’envoi n’a pas confirmé'))  # Même début en anglais (test).
            self.failure(message if uncertain else message + tr(' Si la connexion a été coupée pendant l’envoi, vérifiez la réception avant de réessayer : aucun renvoi automatique n’a été effectué.'))
            self.save_draft()
        self.runner.run(operation, done, failed)

    def save_server_draft(self):
        if self.busy or self.saving:
            return
        if self.offline():
            self.status.setText(tr('Mode hors ligne : la copie locale est conservée ; reconnectez-vous pour la copier sur le serveur.'))
            return
        state, files = self.state(), list(self.files)
        self.set_busy(True)
        self.runner.run(lambda: self.message(state, files, True)[0].as_bytes(),
                        lambda raw: self.copy_to_server(raw, draft=True), self.failure)

    def copy_to_server(self, raw, draft, close_after=False):
        account = self.current_account()
        if not draft and (account.auth_method == 'google' or account.smtp.host.lower() == 'smtp.gmail.com'):
            self.status.setText(tr('Message envoyé. Gmail conserve automatiquement sa copie dans Envoyés.'))
            if close_after:
                self.close()
            else:
                self.save_draft()
            return
        self.set_busy(True)
        offline = self.offline()
        def operation():
            if offline:
                raise RuntimeError(tr('Smail est passé hors ligne. La copie serveur n’a pas été effectuée.'))
            folders, _ = self.service.folders(account)
            words = ('brouillons', 'draft') if draft else ('envoyés', 'sent')
            folder = next((name for name, label in folders if any(word in (name + ' ' + label).casefold() for word in words)), None)
            if not folder:
                raise RuntimeError(tr('Dossier Brouillons/Envoyés introuvable. La copie locale est conservée.'))
            self.service.client(account).append(folder, raw, draft)
            if not draft and self.last_copy_id:
                copy = self.service.db.cache_get('sent-copy', self.last_copy_id)
                if copy:
                    copy['server_saved'] = True
                    self.service.db.cache_put('sent-copy', self.last_copy_id, copy)
        def done(_):
            self.set_busy(False)
            self.status.setText(tr('Copie enregistrée sur le serveur.') if draft else tr('Message envoyé et copie enregistrée.'))
            if close_after:
                self.close()
            elif self.saved_revision != self.revision:
                self.save_draft()
        def failed(message):
            self.set_busy(False)
            # Conserver une copie exportable sans jamais représenter un message déjà envoyé comme un brouillon à renvoyer.
            saved = tr(' Copie disponible dans Envoyés locaux.') if self.last_copy_id else tr(' La copie locale n’a pas pu être enregistrée.')
            self.status.setText((tr('Message déjà envoyé. ') if not draft else '') + message + (saved + tr(' Ne renvoyez pas le message.') if not draft else ''))
        self.runner.run(operation, done, failed)

    def discard(self):
        if self.busy or self.saving or self.delivered:
            return
        if QMessageBox.question(self, tr('Supprimer le brouillon'), tr('Supprimer définitivement ce brouillon local ?'), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.set_busy(True)
        def done(_):
            self.set_busy(False)
            self.saved_revision = self.revision
            self.close()
        self.runner.run(lambda: self.service.db.cache_delete('draft', self.id), done, self.failure)

    def reject(self):
        self.close()  # Échap suit aussi le chemin de sauvegarde asynchrone.

    def closeEvent(self, event):
        if self.countdown:
            self.flush_countdown()  # Fermer pendant le délai : envoi immédiat, puis fermeture.
            event.ignore()
        elif self.busy:
            self.status.setText(tr('Attendez la fin de l’opération avant de fermer.'))
            event.ignore()
        elif self.saving:
            self.close_when_saved = True
            event.ignore()
        elif self.saved_revision != self.revision:
            self.close_when_saved = True
            self.save_draft()
            event.ignore()
        else:
            self.debounce.stop()
            self.periodic.stop()
            event.accept()
