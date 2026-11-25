"""Préférences, une page par thème : Général, Comptes, Apparence, Réception, Rédaction, Sécurité, Règles, Raccourcis."""
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QComboBox, QCheckBox, QDialogButtonBox, QListWidget, QStackedWidget, QColorDialog, QMessageBox)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from mailclient.ui.dialog_shell import dialog_layout
from mailclient.ui.components import label, Button, Card, Banner
from mailclient.ui.presentation import install_theme
from mailclient.ui.theme import VARIANTS, ACCENTS

class SettingsDialog(QDialog):
    PAGES = ('Général', 'Comptes', 'Apparence', 'Réception', 'Rédaction', 'Sécurité', 'Règles et indésirables', 'Raccourcis')

    def __init__(self, database, parent=None, page='Général'):
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
        self.nav.setFixedWidth(190)
        self.nav.setAccessibleName('Catégories des paramètres')
        self.nav.addItems(list(self.PAGES))
        self.pages = QStackedWidget()
        from mailclient.ui.rules_dialog import FiltersPage
        owner = self.parent()
        self.filters_page = FiltersPage(database, database.accounts(), getattr(owner,'apply_filters_now',None))
        for widget in (self.general_page(), self.accounts_page(), self.appearance_page(), self.reception_page(),
                       self.writing_page(), self.security_page(), self.filters_page, self.shortcuts_page()):
            self.pages.addWidget(widget)
        row.addWidget(self.nav)
        row.addWidget(self.pages,1)
        layout.addLayout(row)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(self.PAGES.index(page) if page in self.PAGES else 0)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Enregistrer')
        buttons.button(QDialogButtonBox.Save).setObjectName('Primary')
        buttons.button(QDialogButtonBox.Cancel).setText('Annuler')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    @staticmethod
    def page(title, subtitle=''):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label(title,'Title',True))
        if subtitle:
            box.addWidget(label(subtitle,'Subtitle',True))
        return widget, box

    def general_page(self):
        widget, box = self.page('Général', 'Comportement de Smail sur ce PC.')
        self.notifications = QCheckBox('Notifications de nouveaux messages')
        self.notifications.setChecked(self.database.setting('notifications',True))
        self.tray = QCheckBox('Réduire dans la zone de notification à la fermeture (Smail continue de recevoir vos messages)')
        self.tray.setChecked(self.database.setting('close_to_tray',True))
        for control in (self.notifications, self.tray):
            box.addWidget(control)
        from mailclient.core import autostart
        from mailclient.core.updater import packaged as store_copy
        self.autostart = QCheckBox('Lancer Smail à l’ouverture de session Windows (réduit dans la zone de notification)')
        self.autostart.setEnabled(autostart.supported())
        try:
            self.autostart.setChecked(autostart.supported() and autostart.enabled())
        except OSError:
            self.autostart.setEnabled(False)
        box.addWidget(self.autostart)
        if store_copy():
            startup = Button('Gérer le démarrage dans les paramètres de Windows…',self.appearance_theme,'settings-2','Secondary')
            startup.clicked.connect(lambda: __import__('PySide6.QtGui', fromlist=['QDesktopServices']).QDesktopServices.openUrl(
                __import__('PySide6.QtCore', fromlist=['QUrl']).QUrl('ms-settings:startupapps')))
            box.addWidget(startup, 0, Qt.AlignLeft)
        elif not autostart.supported():
            box.addWidget(label('Lancement au démarrage : disponible pour Smail installé.','Small',True))
        # Liens « mailto: » : Windows exige que l’utilisateur choisisse lui-même l’application par défaut.
        from mailclient.core.updater import installed_copy, packaged
        self.default_app = Button('Définir Smail comme messagerie par défaut…',self.appearance_theme,'mail','Secondary',
                                  'Ouvre les paramètres de Windows : choisissez Smail pour « MAILTO ».')
        self.default_app.clicked.connect(self.open_default_apps)
        self.default_app.setEnabled(installed_copy() or packaged())
        box.addWidget(self.default_app, 0, Qt.AlignLeft)
        box.addWidget(label('Un clic sur une adresse e-mail dans le navigateur ouvrira alors un nouveau message dans Smail.'
                            if self.default_app.isEnabled() else
                            'Disponible pour Smail installé (installateur ou Microsoft Store).','Small',True))
        from mailclient import __version__
        from mailclient.core.updater import packaged
        from mailclient.ui.updates import MODE_LABELS, update_mode
        self.update_mode = QComboBox()
        for key, text in MODE_LABELS.items():
            self.update_mode.addItem(text, key)
        self.update_mode.setCurrentIndex(self.update_mode.findData(update_mode(self.database)))
        self.update_mode.setToolTip('Vérifiées toutes les 6 heures sur GitHub ; une mise à jour n’est installée que si sa '
                                    'signature est valide.')
        form = QFormLayout()
        form.addRow(f'Mises à jour (version actuelle : {__version__})', self.update_mode)
        box.addLayout(form)
        if packaged():
            self.update_mode.setEnabled(False)
            box.addWidget(label('Cette copie vient du Microsoft Store : ses mises à jour sont installées par le Store.','Small',True))
        box.addStretch()
        return widget

    @staticmethod
    def open_default_apps():
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        # Page « Applications par défaut › Smail » (Windows 11) ; Windows 10 ouvre la page générale.
        QDesktopServices.openUrl(QUrl('ms-settings:defaultapps?registeredAppUser=Smail'))

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

    def reception_page(self):
        widget, box = self.page('Réception', 'Arrivée des messages et copie disponible hors ligne.')
        self.conversations = QCheckBox('Regrouper les messages par conversation')
        self.conversations.setChecked(bool(self.database.setting('conversation_view', True)))
        self.idle = QCheckBox('Réception instantanée (IMAP IDLE) quand le serveur la propose')
        self.idle.setChecked(self.database.setting('idle',True))
        self.mark_read = QCheckBox('Marquer comme lu à l’ouverture (dans Smail et sur le serveur)')
        self.mark_read.setChecked(bool(self.database.setting('mark_read_on_open', True)))
        box.addWidget(self.conversations)
        box.addWidget(self.mark_read)
        box.addWidget(self.idle)
        self.minutes = QSpinBox()
        self.minutes.setRange(1,120)
        self.minutes.setSuffix(' min')
        self.minutes.setValue(self.database.setting('sync_minutes',5))
        self.limit = QSpinBox()
        self.limit.setRange(50,5000)
        self.limit.setSingleStep(50)
        self.limit.setValue(self.database.setting('cache_limit',100))
        form = QFormLayout()
        form.addRow('Synchroniser toutes les',self.minutes)
        form.addRow('Messages disponibles hors ligne, par dossier',self.limit)
        box.addLayout(form)
        box.addStretch()
        return widget

    def writing_page(self):
        widget, box = self.page('Rédaction', 'Envoi des messages.')
        self.undo_send = QSpinBox()
        self.undo_send.setRange(0,30)
        self.undo_send.setSuffix(' s')
        self.undo_send.setSpecialValueText('Désactivé')
        self.undo_send.setValue(self.database.setting('undo_send_seconds',10))
        self.undo_send.setToolTip('Délai pendant lequel « Annuler l’envoi » reste possible après avoir cliqué sur Envoyer.')
        form = QFormLayout()
        form.addRow('Délai d’annulation d’envoi',self.undo_send)
        box.addLayout(form)
        box.addWidget(label('La signature se règle pour chaque compte : page Comptes › Paramètres.','Small',True))
        box.addStretch()
        return widget

    def accounts_page(self):
        widget, box = self.page('Vos comptes', 'Les comptes configurés sur ce PC : paramètres, signature, suppression.')
        add = Button('Ajouter un compte',self.appearance_theme,'plus','Secondary')
        add.setEnabled(self.parent() is not None and hasattr(self.parent(),'secrets'))
        add.clicked.connect(self.add_account)
        box.addWidget(add, 0, Qt.AlignLeft)
        self.accounts_list = QVBoxLayout()
        box.addLayout(self.accounts_list)
        box.addStretch()
        self.refresh_accounts()
        return widget

    def refresh_accounts(self):
        while self.accounts_list.count():
            item = self.accounts_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        accounts = self.database.accounts()
        methods = {'password': 'Mot de passe', 'google': 'Connexion Google', 'microsoft': 'Connexion Microsoft'}
        for account in accounts:
            card = Card('Attachment',12)
            row = QHBoxLayout()
            text = QVBoxLayout()
            text.addWidget(label(account.name or account.email,'Bold'))
            text.addWidget(label(f'{account.email} · {methods.get(account.auth_method, account.auth_method)}','Subtitle'))
            text.addWidget(label(f'Réception {account.imap.host}:{account.imap.port} · Envoi {account.smtp.host}:{account.smtp.port}','Small'))
            row.addLayout(text,1)
            edit = Button('Paramètres',self.appearance_theme,'settings-2','Secondary','Paramètres, mot de passe et signature du compte '+account.name)
            edit.setEnabled(self.parent() is not None and hasattr(self.parent(),'secrets'))
            edit.clicked.connect(lambda checked=False,a=account:self.edit_account(a))
            row.addWidget(edit)
            remove = Button('Supprimer',self.appearance_theme,'trash-2','QuietDanger','Supprimer le compte '+account.name+' de ce PC')
            remove.setAccessibleName('Supprimer le compte '+account.name)
            remove.setEnabled(edit.isEnabled())
            remove.clicked.connect(lambda checked=False,a=account,c=card:self.delete_account(a,c))
            row.addWidget(remove)
            card.box.addLayout(row)
            secure = account.imap.mode != 'Aucun' and account.smtp.mode != 'Aucun'
            card.box.addWidget(Banner('Connexion chiffrée' if secure else 'Attention · connexion en clair',
                f'IMAP : {account.imap.mode} · SMTP : {account.smtp.mode}',self.appearance_theme,
                'Info' if secure else 'Warning','lock-keyhole' if secure else 'lock-keyhole-open'))
            self.accounts_list.addWidget(card)
        if not accounts:
            self.accounts_list.addWidget(label('Aucun compte configuré : cliquez sur « Ajouter un compte ».','Subtitle',True))

    def add_account(self):
        owner = self.parent()
        if owner is not None and hasattr(owner, 'add_account'):
            owner.add_account()
            self.refresh_accounts()

    def edit_account(self, account):
        from mailclient.ui.account_dialog import AccountDialog
        owner = self.parent()
        if owner and AccountDialog(self.database,owner.secrets,owner.runner.tls,self,account=account).exec():
            owner.reload_accounts()
            owner.restart_idle()
            self.refresh_accounts()

    def delete_account(self, account, card):
        owner = self.parent()
        if owner and owner.delete_account(account):
            card.hide()
            QTimer.singleShot(0, self.refresh_accounts)

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
        widget, box = self.page('Sécurité et confidentialité')
        box.addWidget(Banner('Certificats vérifiés · images bloquées par défaut',
            'Toute exception de certificat et tout affichage d’images distantes demandent une décision explicite.',self.appearance_theme))
        self.encrypt = QCheckBox('Chiffrer les messages, pièces jointes et brouillons enregistrés sur ce PC')
        self.encrypt.setChecked(self.database.setting('cache_encrypted',False))
        box.addWidget(self.encrypt)
        box.addWidget(label('Le chiffrement protège la copie locale de vos mails avec une clé du coffre Windows. Les paramètres '
                            'des comptes restent lisibles. Sans cette option, la copie locale est en clair sur ce PC.','Small',True))
        box.addWidget(self.certificates_box())
        box.addStretch()
        return widget

    def shortcuts_page(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label('Vos mains restent au clavier','Title',True))
        for title,key in [('Nouveau message','Ctrl + N'),('Rechercher','Ctrl + F'),('Palette de commandes','Ctrl + K'),
                          ('Répondre','Ctrl + R'),('Répondre à tous','Ctrl + Maj + R'),('Transférer','Ctrl + L'),
                          ('Marquer comme lu / non lu','Ctrl + U'),('Suivre / ne plus suivre','Ctrl + Maj + G'),
                          ('Déplacer vers un dossier','Ctrl + Maj + V'),('Supprimer (liste des messages)','Suppr'),
                          ('Tout marquer comme lu (dossier)','Ctrl + Maj + U'),('Signaler comme spam','Ctrl + Maj + J'),
                          ('Message suivant / précédent (liste des messages)','J / K'),('Archiver / suivre (liste des messages)','E / S'),
                          ('Message suivant / précédent de la conversation','Alt + Bas / Haut'),('Regrouper par conversation','Ctrl + Maj + T'),
                          ('Actualiser','F5'),('Passer au thème clair / sombre','Ctrl + Maj + L'),('Changer la densité','Ctrl + Maj + D'),
                          ('Mise en forme : gras, italique, souligné','Ctrl + B, I, U'),('Insérer un lien (rédaction)','Ctrl + Maj + K'),('Envoyer (rédaction)','Ctrl + Entrée')]:
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
