"""Préférences réelles dans les catégories de la maquette validée."""
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QComboBox, QCheckBox, QDialogButtonBox, QListWidget, QStackedWidget, QColorDialog, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from mailclient.ui.dialog_shell import dialog_layout
from mailclient.ui.components import label, Button, Card, Banner
from mailclient.ui.presentation import install_theme
from mailclient.ui.theme import VARIANTS, ACCENTS

class SettingsDialog(QDialog):
    def __init__(self, database, parent=None):
        super().__init__(parent)
        self.database = database
        self.appearance_theme = install_theme(database)
        self.previous = {name:getattr(self.appearance_theme,name) for name in
                         ('variant','dark','density','accent_name','custom_accent','reduced_motion')}
        self.setWindowTitle('Préférences de Smail')
        theme, outer, layout = dialog_layout(self,'Paramètres','Une apparence à votre mesure. Des choix de sécurité explicites.',(1000,800))
        row = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setObjectName('SettingsNav')
        self.nav.setFixedWidth(175)
        self.nav.setAccessibleName('Catégories des paramètres')
        self.nav.addItems(['Apparence','Comptes','Sécurité','Raccourcis'])
        self.pages = QStackedWidget()
        for page in (self.appearance_page(),self.accounts_page(),self.security_page(),self.shortcuts_page()):
            self.pages.addWidget(page)
        row.addWidget(self.nav)
        row.addWidget(self.pages,1)
        layout.addLayout(row)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Enregistrer')
        buttons.button(QDialogButtonBox.Save).setObjectName('Primary')
        buttons.button(QDialogButtonBox.Cancel).setText('Annuler')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def appearance_page(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label('L’espace qui vous ressemble','Title',True))
        box.addWidget(label('Les changements d’apparence sont visibles immédiatement. Annuler rétablit votre choix précédent.','Subtitle',True))
        self.style_cards = []
        self.style_combo = QComboBox()
        for number,(name,description) in VARIANTS.items():
            self.style_combo.addItem(name,number)
            button = Button(f'0{number}   {name}\n       {description}',self.appearance_theme,'layout-panel-left','Nav')
            button.setCheckable(True)
            button.setChecked(number == self.appearance_theme.variant)
            button.clicked.connect(lambda checked=False,index=number-1:self.style_combo.setCurrentIndex(index))
            self.style_cards.append(button)
            box.addWidget(button)
        self.style_combo.setCurrentIndex(self.appearance_theme.variant-1)
        self.theme = QComboBox()
        self.theme.addItems(['Clair','Sombre'])
        self.theme.setCurrentIndex(int(self.appearance_theme.dark))
        self.density = QComboBox()
        self.density.addItems(['Compacte','Normale','Aérée'])
        self.density.setCurrentText(self.appearance_theme.density)
        self.accent = QComboBox()
        self.accent.addItems(list(ACCENTS))
        self.accent.setCurrentText(self.appearance_theme.accent_name)
        self.custom_accent = self.appearance_theme.custom_accent
        self.motion = QCheckBox('Réduire les animations')
        self.motion.setChecked(self.appearance_theme.reduced_motion)
        form = QFormLayout()
        form.addRow('Style',self.style_combo)
        form.addRow('Thème',self.theme)
        form.addRow('Densité',self.density)
        form.addRow('Couleur d’accent',self.accent)
        custom = Button('Choisir une autre couleur…',self.appearance_theme,'palette','Secondary')
        custom.clicked.connect(self.choose_color)
        form.addRow('',custom)
        box.addLayout(form)
        box.addWidget(self.motion)
        box.addStretch()
        for combo in (self.style_combo,self.theme,self.density):
            combo.currentIndexChanged.connect(self.preview)
        self.accent.currentIndexChanged.connect(self.preset_accent)
        self.motion.toggled.connect(self.preview)
        return widget

    def preview(self, *_):
        variant = self.style_combo.currentData()
        for index,button in enumerate(self.style_cards,1):
            button.setChecked(index == variant)
        self.appearance_theme.update(variant=variant,dark=bool(self.theme.currentIndex()),
            density=self.density.currentText(),accent_name=self.accent.currentText(),
            custom_accent=self.custom_accent,reduced_motion=self.motion.isChecked())

    def preset_accent(self, *_):
        self.custom_accent = None
        self.preview()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.appearance_theme.colors['accent']),self,'Couleur d’accent')
        if color.isValid():
            self.custom_accent = color.name()
            self.preview()

    def accounts_page(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label('Vos comptes','Title'))
        for account in self.database.accounts():
            card = Card('Attachment',12)
            row = QHBoxLayout()
            text = QVBoxLayout()
            text.addWidget(label(account.name,'Bold'))
            text.addWidget(label(account.email,'Subtitle'))
            row.addLayout(text,1)
            edit = Button('',self.appearance_theme,'settings-2',tooltip='Paramètres et signature du compte '+account.name)
            edit.setEnabled(self.parent() is not None and hasattr(self.parent(),'secrets'))
            edit.clicked.connect(lambda checked=False,a=account:self.edit_account(a))
            row.addWidget(edit)
            remove = Button('',self.appearance_theme,'trash-2','QuietDanger','Supprimer le compte '+account.name+' de ce PC')
            remove.setAccessibleName('Supprimer le compte '+account.name)
            remove.setEnabled(edit.isEnabled())
            remove.clicked.connect(lambda checked=False,a=account,c=card:self.delete_account(a,c))
            row.addWidget(remove)
            card.box.addLayout(row)
            secure = account.imap.mode != 'Aucun' and account.smtp.mode != 'Aucun'
            card.box.addWidget(Banner('Connexion chiffrée' if secure else 'Attention · connexion en clair',
                f'IMAP : {account.imap.mode} · SMTP : {account.smtp.mode}',self.appearance_theme,
                'Info' if secure else 'Warning','lock-keyhole' if secure else 'lock-keyhole-open'))
            box.addWidget(card)
        if not self.database.accounts():
            box.addWidget(label('Aucun compte configuré. Utilisez Ajouter un compte dans la fenêtre principale.','Subtitle',True))
        box.addStretch()
        return widget

    def edit_account(self, account):
        from mailclient.ui.account_dialog import AccountDialog
        owner = self.parent()
        if owner and AccountDialog(self.database,owner.secrets,owner.runner.tls,self,account=account).exec():
            owner.reload_accounts()
            owner.restart_idle()

    def delete_account(self, account, card):
        owner = self.parent()
        if owner and owner.delete_account(account):
            card.hide()

    def certificates_box(self):
        """Exceptions de certificat permanentes, retirables une à une."""
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(0,0,0,0)
        box.addWidget(label('Certificats approuvés','Bold'))
        names = {account.id:account.name for account in self.database.accounts()}
        pins = self.database.pins()
        if not pins:
            box.addWidget(label('Aucune exception de certificat permanente.','Subtitle',True))
        for account_id,endpoint,fingerprint in pins:
            card = Card('Attachment',10)
            row = QHBoxLayout()
            text = QVBoxLayout()
            protocol,_,server = endpoint.partition(':')
            text.addWidget(label(f'{names.get(account_id,"Compte supprimé")} · {protocol.upper()} {server}','Bold'))
            fingerprint_label = label('SHA-256 '+':'.join(fingerprint[i:i+2] for i in range(0,len(fingerprint),2)).upper(),'Small',True)
            fingerprint_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text.addWidget(fingerprint_label)
            row.addLayout(text,1)
            remove = Button('Retirer',self.appearance_theme,'trash-2','QuietDanger','Ne plus faire confiance à ce certificat')
            remove.clicked.connect(lambda checked=False,a=account_id,e=endpoint,c=card:self.remove_pin(a,e,c))
            row.addWidget(remove)
            card.box.addLayout(row)
            box.addWidget(card)
        return container

    def remove_pin(self, account_id, endpoint, card):
        if QMessageBox.question(self,'Retirer le certificat','Ne plus faire confiance à ce certificat ? Une alerte réapparaîtra à la prochaine connexion à ce serveur.',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        owner = self.parent()
        tls = getattr(getattr(owner,'runner',None),'tls',None)
        if tls is not None:
            tls.forget(account_id,endpoint)
        else:
            self.database.untrust(account_id,endpoint)
        card.hide()

    def security_page(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label('La sécurité reste visible','Title',True))
        box.addWidget(Banner('Certificats vérifiés · images bloquées par défaut',
            'Toute exception de certificat et tout affichage d’images distantes demandent une décision explicite.',self.appearance_theme))
        self.encrypt = QCheckBox('Chiffrer les messages, pièces jointes et brouillons du cache')
        self.encrypt.setChecked(self.database.setting('cache_encrypted',False))
        self.idle = QCheckBox('Utiliser IMAP IDLE si disponible')
        self.idle.setChecked(self.database.setting('idle',True))
        self.notifications = QCheckBox('Notifications de nouveaux messages')
        self.notifications.setChecked(self.database.setting('notifications',True))
        self.tray = QCheckBox('Réduire dans la zone de notification à la fermeture')
        self.tray.setChecked(self.database.setting('close_to_tray',True))
        for control in (self.encrypt,self.idle,self.notifications,self.tray):
            box.addWidget(control)
        self.minutes = QSpinBox()
        self.minutes.setRange(1,120)
        self.minutes.setValue(self.database.setting('sync_minutes',5))
        self.limit = QSpinBox()
        self.limit.setRange(50,5000)
        self.limit.setSingleStep(50)
        self.limit.setValue(self.database.setting('cache_limit',100))
        form = QFormLayout()
        form.addRow('Synchroniser toutes les (minutes)',self.minutes)
        form.addRow('Messages hors ligne par dossier',self.limit)
        box.addLayout(form)
        box.addWidget(self.certificates_box())
        box.addWidget(label('Le chiffrement protège les contenus du cache avec une clé du coffre Windows. Les paramètres de comptes et le schéma SQLite restent lisibles. Sans cette option, le cache contient vos mails en clair sur ce PC.','Small',True))
        box.addStretch()
        return widget

    def shortcuts_page(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label('Vos mains restent au clavier','Title',True))
        for title,key in [('Palette de commandes','Ctrl + K'),('Rédiger','Ctrl + N'),('Rechercher','Ctrl + F'),
                          ('Répondre','Ctrl + R'),('Répondre à tous','Ctrl + Maj + R'),('Transférer','Ctrl + L'),
                          ('Synchroniser','F5'),('Changer de thème','Ctrl + Maj + L'),('Changer la densité','Ctrl + Maj + D'),
                          ('Message suivant / précédent (style 3)','J / K'),('Archiver / étoiler (style 3)','E / S'),
                          ('Corbeille (focus dans la liste)','Suppr'),('Regrouper par conversation','Ctrl + Maj + T'),('Message suivant / précédent de la conversation','Alt + Bas / Haut'),('Envoyer en rédaction','Ctrl + Entrée')]:
            row = QHBoxLayout()
            row.addWidget(label(title))
            row.addStretch()
            row.addWidget(label(key,'Key'))
            box.addLayout(row)
        box.addStretch()
        return widget

    def reject(self):
        self.appearance_theme.update(**self.previous)
        super().reject()
