"""Préférences, une page par thème : Général, Comptes, Apparence, Réception, Rédaction, Sécurité, Règles, Raccourcis."""
from mailclient.i18n import tr, N_
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QComboBox, QCheckBox, QDialogButtonBox, QListWidget, QStackedWidget, QColorDialog, QMessageBox)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from mailclient.ui.dialog_shell import dialog_layout
from mailclient.ui.components import label, Button, Card, Banner
from mailclient.ui.presentation import install_theme
from mailclient.ui.theme import VARIANTS, ACCENTS

class SettingsDialog(QDialog):
    PAGES = (N_('Général'), N_('Comptes'), N_('Apparence'), N_('Réception'), N_('Rédaction'), N_('Sécurité'),
             N_('Règles et indésirables'), N_('Raccourcis'))  # Identifiants des pages ; affichés traduits.

    def __init__(self, database, parent=None, page='Général'):
        super().__init__(parent)
        self.database = database
        self.appearance_theme = install_theme(database)
        self.previous = {name:getattr(self.appearance_theme,name) for name in
                         ('variant','dark','density','accent_name','custom_accent','reduced_motion')}
        self.setWindowTitle(tr('Préférences de Smail'))
        theme, outer, layout = dialog_layout(self,tr('Paramètres'),tr('Une apparence à votre mesure. Des choix de sécurité explicites.'),(1000,800))
        row = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setObjectName('SettingsNav')
        self.nav.setFixedWidth(190)
        self.nav.setAccessibleName(tr('Catégories des paramètres'))
        self.nav.addItems([tr(page) for page in self.PAGES])  # Pages identifiées en français.
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
        buttons.button(QDialogButtonBox.Save).setText(tr('Enregistrer'))
        buttons.button(QDialogButtonBox.Save).setObjectName('Primary')
        buttons.button(QDialogButtonBox.Cancel).setText(tr('Annuler'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    @staticmethod
    def page(title, subtitle=''):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label(tr(title),'Title',True))
        if subtitle:
            box.addWidget(label(tr(subtitle),'Subtitle',True))
        return widget, box

    def general_page(self):
        widget, box = self.page('Général', 'Comportement de Smail sur ce PC.')
        from mailclient.i18n import LANGUAGES
        language = QHBoxLayout()
        language.addWidget(label(tr('Langue de l’interface')))
        self.language = QComboBox()
        for key, text in LANGUAGES.items():  # « Français » et « English » restent dans leur propre langue.
            self.language.addItem(tr(text), key)
        self.language.setCurrentIndex(max(0, self.language.findData(self.database.setting('language', 'auto'))))
        self.language.setToolTip(tr('Appliquée au prochain démarrage de Smail.'))
        language.addWidget(self.language)
        language.addStretch()
        box.addLayout(language)
        self.notifications = QCheckBox(tr('Notifications de nouveaux messages'))
        self.notifications.setChecked(self.database.setting('notifications',True))
        self.tray = QCheckBox(tr('Réduire dans la zone de notification à la fermeture (Smail continue de recevoir vos messages)'))
        self.tray.setChecked(self.database.setting('close_to_tray',True))
        for control in (self.notifications, self.tray):
            box.addWidget(control)
        from mailclient.core import autostart
        from mailclient.core.updater import packaged as store_copy
        self.autostart = QCheckBox(tr('Lancer Smail à l’ouverture de session Windows (réduit dans la zone de notification)'))
        self.autostart.setEnabled(autostart.supported())
        try:
            self.autostart.setChecked(autostart.supported() and autostart.enabled())
        except OSError:
            self.autostart.setEnabled(False)
        box.addWidget(self.autostart)
        if store_copy():
            startup = Button(tr('Gérer le démarrage dans les paramètres de Windows…'),self.appearance_theme,'settings-2','Secondary')
            startup.clicked.connect(lambda: __import__('PySide6.QtGui', fromlist=['QDesktopServices']).QDesktopServices.openUrl(
                __import__('PySide6.QtCore', fromlist=['QUrl']).QUrl('ms-settings:startupapps')))
            box.addWidget(startup, 0, Qt.AlignLeft)
        elif not autostart.supported():
            box.addWidget(label(tr('Lancement au démarrage : disponible pour Smail installé.'),'Small',True))
        # Liens « mailto: » : Windows exige que l’utilisateur choisisse lui-même l’application par défaut.
        from mailclient.core.updater import installed_copy, packaged
        self.default_app = Button(tr('Définir Smail comme messagerie par défaut…'),self.appearance_theme,'mail','Secondary',
                                  tr('Ouvre les paramètres de Windows : choisissez Smail pour « MAILTO ».'))
        self.default_app.clicked.connect(self.open_default_apps)
        self.default_app.setEnabled(installed_copy() or packaged())
        box.addWidget(self.default_app, 0, Qt.AlignLeft)
        box.addWidget(label(tr('Un clic sur une adresse e-mail dans le navigateur ouvrira alors un nouveau message dans Smail.')
                            if self.default_app.isEnabled() else
                            tr('Disponible pour Smail installé (installateur ou Microsoft Store).'),'Small',True))
        from mailclient import __version__
        from mailclient.core.updater import packaged
        from mailclient.ui.updates import MODE_LABELS, update_mode
        self.update_mode = QComboBox()
        for key, text in MODE_LABELS.items():
            self.update_mode.addItem(text, key)
        self.update_mode.setCurrentIndex(self.update_mode.findData(update_mode(self.database)))
        self.update_mode.setToolTip(tr('Vérifiées toutes les 6 heures sur GitHub ; une mise à jour n’est installée que si sa '
                                    'signature est valide.'))
        form = QFormLayout()
        form.addRow(tr('Mises à jour (version actuelle : {version})').format(version=__version__), self.update_mode)
        box.addLayout(form)
        if packaged():
            self.update_mode.setEnabled(False)
            box.addWidget(label(tr('Cette copie vient du Microsoft Store : ses mises à jour sont installées par le Store.'),'Small',True))
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
        box.addWidget(label(tr('L’espace qui vous ressemble'),'Title',True))
        box.addWidget(label(tr('Les changements d’apparence sont visibles immédiatement. Annuler rétablit votre choix précédent.'),'Subtitle',True))
        self.style_cards = []
        self.style_combo = QComboBox()
        for number,(name,description) in VARIANTS.items():
            self.style_combo.addItem(tr(name),number)
            button = Button(f'0{number}   {tr(name)}\n       {tr(description)}',self.appearance_theme,'layout-panel-left','Nav')
            button.setCheckable(True)
            button.setChecked(number == self.appearance_theme.variant)
            button.clicked.connect(lambda checked=False,index=number-1:self.style_combo.setCurrentIndex(index))
            self.style_cards.append(button)
            box.addWidget(button)
        self.style_combo.setCurrentIndex(self.appearance_theme.variant-1)
        self.theme = QComboBox()
        self.theme.addItems([tr('Clair'),tr('Sombre')])
        self.theme.setCurrentIndex(int(self.appearance_theme.dark))
        self.density = QComboBox()
        for density in ('Compacte','Normale','Aérée'):  # Valeur enregistrée en français, libellé traduit.
            self.density.addItem(tr(density), density)
        self.density.setCurrentIndex(max(0, self.density.findData(self.appearance_theme.density)))
        self.accent = QComboBox()
        for accent in ACCENTS:  # Nom enregistré en français, libellé traduit.
            self.accent.addItem(tr(accent), accent)
        self.accent.setCurrentIndex(max(0, self.accent.findData(self.appearance_theme.accent_name)))
        self.custom_accent = self.appearance_theme.custom_accent
        self.motion = QCheckBox(tr('Réduire les animations'))
        self.motion.setChecked(self.appearance_theme.reduced_motion)
        form = QFormLayout()
        form.addRow(tr('Style'),self.style_combo)
        form.addRow(tr('Thème'),self.theme)
        form.addRow(tr('Densité'),self.density)
        form.addRow(tr('Couleur d’accent'),self.accent)
        custom = Button(tr('Choisir une autre couleur…'),self.appearance_theme,'palette','Secondary')
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
            density=self.density.currentData(),accent_name=self.accent.currentData(),
            custom_accent=self.custom_accent,reduced_motion=self.motion.isChecked())

    def preset_accent(self, *_):
        self.custom_accent = None
        self.preview()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.appearance_theme.colors['accent']),self,tr('Couleur d’accent'))
        if color.isValid():
            self.custom_accent = color.name()
            self.preview()

    def reception_page(self):
        widget, box = self.page('Réception', 'Arrivée des messages et copie disponible hors ligne.')
        self.conversations = QCheckBox(tr('Regrouper les messages par conversation'))
        self.conversations.setChecked(bool(self.database.setting('conversation_view', True)))
        self.idle = QCheckBox(tr('Réception instantanée (IMAP IDLE) quand le serveur la propose'))
        self.idle.setChecked(self.database.setting('idle',True))
        self.mark_read = QCheckBox(tr('Marquer comme lu à l’ouverture (dans Smail et sur le serveur)'))
        self.mark_read.setChecked(bool(self.database.setting('mark_read_on_open', True)))
        box.addWidget(self.conversations)
        box.addWidget(self.mark_read)
        box.addWidget(self.idle)
        self.minutes = QSpinBox()
        self.minutes.setRange(1,120)
        self.minutes.setSuffix(tr(' min'))
        self.minutes.setValue(self.database.setting('sync_minutes',5))
        self.limit = QSpinBox()
        self.limit.setRange(50,5000)
        self.limit.setSingleStep(50)
        self.limit.setValue(self.database.setting('cache_limit',100))
        form = QFormLayout()
        form.addRow(tr('Synchroniser toutes les'),self.minutes)
        form.addRow(tr('Messages disponibles hors ligne, par dossier'),self.limit)
        box.addLayout(form)
        box.addStretch()
        return widget

    def writing_page(self):
        widget, box = self.page('Rédaction', 'Envoi des messages.')
        self.undo_send = QSpinBox()
        self.undo_send.setRange(0,30)
        self.undo_send.setSuffix(tr(' s'))
        self.undo_send.setSpecialValueText(tr('Désactivé'))
        self.undo_send.setValue(self.database.setting('undo_send_seconds',10))
        self.undo_send.setToolTip(tr('Délai pendant lequel « Annuler l’envoi » reste possible après avoir cliqué sur Envoyer.'))
        form = QFormLayout()
        form.addRow(tr('Délai d’annulation d’envoi'),self.undo_send)
        box.addLayout(form)
        box.addWidget(label(tr('La signature se règle pour chaque compte : page Comptes › Paramètres.'),'Small',True))
        box.addStretch()
        return widget

    def accounts_page(self):
        widget, box = self.page('Vos comptes', 'Les comptes configurés sur ce PC : paramètres, signature, suppression.')
        add = Button(tr('Ajouter un compte'),self.appearance_theme,'plus','Secondary')
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
        methods = {'password': tr('Mot de passe'), 'google': tr('Connexion Google'), 'microsoft': tr('Connexion Microsoft')}
        for account in accounts:
            card = Card('Attachment',12)
            row = QHBoxLayout()
            text = QVBoxLayout()
            text.addWidget(label(account.name or account.email,'Bold'))
            text.addWidget(label(f'{account.email} · {methods.get(account.auth_method, account.auth_method)}','Subtitle'))
            text.addWidget(label(tr('Réception {host}:{port} · Envoi {host2}:{port2}').format(host=account.imap.host, port=account.imap.port, host2=account.smtp.host, port2=account.smtp.port),'Small'))
            row.addLayout(text,1)
            edit = Button(tr('Paramètres'),self.appearance_theme,'settings-2','Secondary',tr('Paramètres, mot de passe et signature du compte ')+account.name)
            edit.setEnabled(self.parent() is not None and hasattr(self.parent(),'secrets'))
            edit.clicked.connect(lambda checked=False,a=account:self.edit_account(a))
            row.addWidget(edit)
            remove = Button(tr('Supprimer'),self.appearance_theme,'trash-2','QuietDanger',tr('Supprimer le compte ')+account.name+tr(' de ce PC'))
            remove.setAccessibleName(tr('Supprimer le compte ')+account.name)
            remove.setEnabled(edit.isEnabled())
            remove.clicked.connect(lambda checked=False,a=account,c=card:self.delete_account(a,c))
            row.addWidget(remove)
            card.box.addLayout(row)
            secure = account.imap.mode != 'Aucun' and account.smtp.mode != 'Aucun'
            card.box.addWidget(Banner(tr('Connexion chiffrée') if secure else tr('Attention · connexion en clair'),
                tr('IMAP : {mode} · SMTP : {mode2}').format(mode=account.imap.mode, mode2=account.smtp.mode),self.appearance_theme,
                'Info' if secure else 'Warning','lock-keyhole' if secure else 'lock-keyhole-open'))
            self.accounts_list.addWidget(card)
        if not accounts:
            self.accounts_list.addWidget(label(tr('Aucun compte configuré : cliquez sur « Ajouter un compte ».'),'Subtitle',True))

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
        box.addWidget(label(tr('Certificats approuvés'),'Bold'))
        names = {account.id:account.name for account in self.database.accounts()}
        pins = self.database.pins()
        if not pins:
            box.addWidget(label(tr('Aucune exception de certificat permanente.'),'Subtitle',True))
        for account_id,endpoint,fingerprint in pins:
            card = Card('Attachment',10)
            row = QHBoxLayout()
            text = QVBoxLayout()
            protocol,_,server = endpoint.partition(':')
            text.addWidget(label(f'{names.get(account_id,tr("Compte supprimé"))} · {protocol.upper()} {server}','Bold'))
            fingerprint_label = label(tr('SHA-256 ')+':'.join(fingerprint[i:i+2] for i in range(0,len(fingerprint),2)).upper(),'Small',True)
            fingerprint_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text.addWidget(fingerprint_label)
            row.addLayout(text,1)
            remove = Button(tr('Retirer'),self.appearance_theme,'trash-2','QuietDanger',tr('Ne plus faire confiance à ce certificat'))
            remove.clicked.connect(lambda checked=False,a=account_id,e=endpoint,c=card:self.remove_pin(a,e,c))
            row.addWidget(remove)
            card.box.addLayout(row)
            box.addWidget(card)
        return container

    def remove_pin(self, account_id, endpoint, card):
        if QMessageBox.question(self,tr('Retirer le certificat'),tr('Ne plus faire confiance à ce certificat ? Une alerte réapparaîtra à la prochaine connexion à ce serveur.'),
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
        box.addWidget(Banner(tr('Certificats vérifiés · images bloquées par défaut'),
            tr('Toute exception de certificat et tout affichage d’images distantes demandent une décision explicite.'),self.appearance_theme))
        self.encrypt = QCheckBox(tr('Chiffrer les messages, pièces jointes et brouillons enregistrés sur ce PC'))
        self.encrypt.setChecked(self.database.setting('cache_encrypted',False))
        box.addWidget(self.encrypt)
        box.addWidget(label(tr('Le chiffrement protège la copie locale de vos mails avec une clé du coffre Windows. Les paramètres '
                            'des comptes restent lisibles. Sans cette option, la copie locale est en clair sur ce PC.'),'Small',True))
        box.addWidget(self.certificates_box())
        box.addStretch()
        return widget

    def shortcuts_page(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label(tr('Vos mains restent au clavier'),'Title',True))
        for title,key in [(N_('Nouveau message'),N_('Ctrl + N')),(N_('Rechercher'),N_('Ctrl + F')),(N_('Palette de commandes'),N_('Ctrl + K')),
                          (N_('Répondre'),N_('Ctrl + R')),(N_('Répondre à tous'),N_('Ctrl + Maj + R')),(N_('Transférer'),N_('Ctrl + L')),
                          (N_('Marquer comme lu / non lu'),N_('Ctrl + U')),(N_('Suivre / ne plus suivre'),N_('Ctrl + Maj + G')),
                          (N_('Déplacer vers un dossier'),N_('Ctrl + Maj + V')),(N_('Supprimer (liste des messages)'),N_('Suppr')),
                          (N_('Tout marquer comme lu (dossier)'),N_('Ctrl + Maj + U')),(N_('Signaler comme spam'),N_('Ctrl + Maj + J')),
                          (N_('Message suivant / précédent (liste des messages)'),N_('J / K')),(N_('Archiver / suivre (liste des messages)'),N_('E / S')),
                          (N_('Message suivant / précédent de la conversation'),N_('Alt + Bas / Haut')),(N_('Regrouper par conversation'),N_('Ctrl + Maj + T')),
                          (N_('Actualiser'),N_('F5')),(N_('Passer au thème clair / sombre'),N_('Ctrl + Maj + L')),(N_('Changer la densité'),N_('Ctrl + Maj + D')),
                          (N_('Mise en forme : gras, italique, souligné'),N_('Ctrl + B, I, U')),(N_('Insérer un lien (rédaction)'),N_('Ctrl + Maj + K')),(N_('Envoyer (rédaction)'),N_('Ctrl + Entrée'))]:
            row = QHBoxLayout()
            row.addWidget(label(tr(title)))
            row.addStretch()
            row.addWidget(label(tr(key),'Key'))
            box.addLayout(row)
        box.addStretch()
        return widget

    def reject(self):
        self.appearance_theme.update(**self.previous)
        super().reject()
