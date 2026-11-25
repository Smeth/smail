"""Ajout de compte et test asynchrone des deux serveurs."""
from mailclient.i18n import tr, N_
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
                               QSpinBox, QLabel, QCheckBox, QPushButton, QDialogButtonBox, QGroupBox, QPlainTextEdit, QScrollArea, QWidget)
from PySide6.QtCore import Qt
from mailclient.ui.rich_text import RichTextEdit, FormatBar
from mailclient.core.service import save_signature
from mailclient.core.accounts import Account, Server, MODES, PORTS
from mailclient.core.imap_client import IMAPClient
from mailclient.core.smtp_client import test_connection
from mailclient.core.sync import Runner
from mailclient.core.oauth import OAuth
import threading
from mailclient.ui.dialog_shell import dialog_layout
from mailclient.ui.components import Card, label, Button
from PySide6.QtWidgets import QHBoxLayout

WARNING = N_('Votre mot de passe et vos mails circuleront en clair et pourront être lus par des tiers. Non recommandé.')

class AccountDialog(QDialog):
    def __init__(self, database, secrets, tls, parent=None, account=None):
        super().__init__(parent)
        self.database, self.secrets = database, secrets
        self.runner = Runner(self, tls)
        self.original = account
        self.account_id = account.id if account else None
        self.oauth = OAuth(secrets)
        self.oauth_cancelled = threading.Event()
        self.busy = False
        self.setWindowTitle(tr('Ajouter un compte'))
        self.appearance, outer, layout = dialog_layout(self,tr('Paramètres du compte') if account else tr('Ajouter un compte'),tr('Vos accès et la sécurité de chaque serveur.'),(760,640))
        form = QFormLayout()
        form.setSpacing(10)
        self.name, self.address, self.password = QLineEdit(), QLineEdit(), QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.name.setPlaceholderText(tr('ex. Marie Dupont ou Livrango'))
        self.name.setToolTip(tr('Nom affiché à vos destinataires à côté de votre adresse, et dans Smail pour ce compte.'))
        self.address.setPlaceholderText(tr('vous@exemple.fr'))
        self.password.setToolTip(tr('Gmail, Yahoo et iCloud exigent un « mot de passe d’application » créé dans les réglages '
                                 'de sécurité du compte, ou la connexion OAuth2.'))
        form.addRow(tr('Votre nom (vu par vos destinataires)'), self.name)
        form.addRow(tr('Adresse e-mail'), self.address)
        form.addRow(tr('Mot de passe'), self.password)
        self.detect_status = label('', 'Small', True)
        form.addRow('', self.detect_status)
        self.auth = QComboBox()
        self.auth.addItems([tr('Mot de passe'), tr('OAuth2 Google'), tr('OAuth2 Microsoft')])
        self.client_id = QLineEdit()
        self.client_secret = QLineEdit()
        self.client_secret.setEchoMode(QLineEdit.Password)
        self.tenant = QLineEdit('common')
        self.authorize_button = Button(tr('Connecter avec OAuth2 dans le navigateur'),self.appearance,'arrow-up-right','Secondary')
        self.authorize_button.clicked.connect(self.authorize)
        form.addRow(tr('Authentification'), self.auth)
        layout.addLayout(form)
        # Connexion en un clic avec l’application Smail : aucun identifiant technique à saisir.
        from mailclient.core import oauth_apps
        self.quick = QWidget()
        quick_row = QHBoxLayout(self.quick)
        quick_row.setContentsMargins(0, 0, 0, 0)
        quick_row.addWidget(label(tr('Compte Gmail, Outlook ou Microsoft 365 ?'), 'Bold'))
        self.quick_buttons = {}
        for provider, text in (('google', N_('Se connecter avec Google')), ('microsoft', N_('Se connecter avec Microsoft'))):
            button = Button(tr(text), self.appearance, 'arrow-up-right', 'Secondary',
                            tr('Ouvre la page de connexion dans votre navigateur ; Smail ne voit jamais votre mot de passe.'))
            button.clicked.connect(lambda checked=False, p=provider: self.one_click(p))
            button.setVisible(oauth_apps.available(provider))
            quick_row.addWidget(button)
            self.quick_buttons[provider] = button
        quick_row.addStretch()
        self.quick.setVisible(any(oauth_apps.available(p) for p in ('google', 'microsoft')))
        layout.addWidget(self.quick)
        self.own_app = QCheckBox(tr('Utiliser ma propre application OAuth2 (avancé)'))
        self.own_app.toggled.connect(self.auth_changed)
        layout.addWidget(self.own_app)
        self.oauth_group = QGroupBox(tr('Autorisation OAuth2'))
        oauth_form = QFormLayout(self.oauth_group)
        oauth_form.addRow(tr('Identifiant client OAuth2'),self.client_id)
        oauth_form.addRow(tr('Secret client Google (si requis)'),self.client_secret)
        oauth_form.addRow(tr('Tenant Microsoft'),self.tenant)
        oauth_form.addRow(self.authorize_button)
        layout.addWidget(self.oauth_group)
        self.servers = {}
        self.logins = {}
        # Réglages des serveurs : remplis par la détection, repliés tant qu’ils ne demandent rien.
        self.server_toggle = Button(tr('Réglages des serveurs'), self.appearance, 'settings-2', 'Secondary',
                                    tr('Afficher ou masquer les serveurs IMAP et SMTP'))
        self.server_toggle.clicked.connect(lambda: self.show_servers(not self.server_panel.isVisible()))
        layout.addWidget(self.server_toggle, 0, Qt.AlignLeft)
        self.server_panel = QWidget()
        servers_row = QHBoxLayout(self.server_panel)
        servers_row.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.server_panel)
        self.manual_servers = False
        self.detection = 0
        for protocol in ('imap', 'smtp'):
            group = QGroupBox(protocol.upper())
            fields = QFormLayout(group)
            host = QLineEdit()
            host.setAccessibleName(tr('Serveur ')+protocol.upper())
            host.textEdited.connect(self.servers_edited)
            mode = QComboBox()
            mode.setAccessibleName(tr('Chiffrement ')+protocol.upper())
            for value in MODES:  # « Aucun » affiché traduit, enregistré tel quel.
                mode.addItem(tr(value), value)
            port = QSpinBox()
            port.setAccessibleName(tr('Port ')+protocol.upper())
            port.setRange(1, 65535)
            port.setValue(PORTS[protocol][0])
            fields.addRow(tr('Serveur'), host)
            fields.addRow(tr('Type de connexion chiffrée'), mode)
            fields.addRow(tr('Port'), port)
            login = QLineEdit()
            login.setPlaceholderText(tr('Vide : l’adresse e-mail'))
            login.setAccessibleName(tr('Identifiant de connexion ')+protocol.upper())
            login.setToolTip(tr('À renseigner seulement si votre hébergeur fournit un identifiant différent de l’adresse e-mail.'))
            fields.addRow(tr('Identifiant'), login)
            self.logins[protocol] = login
            if protocol == 'smtp':
                self.same_smtp_password = QCheckBox(tr('Mot de passe SMTP identique à celui du compte'))
                self.same_smtp_password.setChecked(True)
                self.smtp_password = QLineEdit()
                self.smtp_password.setEchoMode(QLineEdit.Password)
                self.smtp_password.setAccessibleName(tr('Mot de passe SMTP'))
                self.smtp_password.setPlaceholderText(tr('Mot de passe du serveur d’envoi'))
                self.smtp_password.setEnabled(False)
                self.same_smtp_password.toggled.connect(lambda same: self.smtp_password.setEnabled(not same and self.auth.currentIndex() == 0))
                fields.addRow('', self.same_smtp_password)
                fields.addRow(tr('Mot de passe SMTP'), self.smtp_password)
            self.servers[protocol] = (host, mode, port)
            mode.currentIndexChanged.connect(lambda index, p=protocol: self.mode_changed(p, index))
            servers_row.addWidget(group)
        self.warning = QLabel(tr(WARNING))
        self.warning.setWordWrap(True)
        self.warning.setTextFormat(Qt.PlainText)
        self.warning_frame = Card('Danger',12)
        self.warning_frame.box.addWidget(self.warning)
        self.confirm = QCheckBox(tr('Je comprends et j’accepte le risque de connexion en clair.'))
        layout.addWidget(self.warning_frame)
        layout.addWidget(self.confirm)
        self.warning.hide()
        self.warning_frame.hide()
        self.confirm.hide()
        self.signature = RichTextEdit(attachments=False)
        self.signature.setTabChangesFocus(True)
        self.signature.setMinimumHeight(90)
        self.signature.setMaximumHeight(140)
        self.signature.setPlaceholderText(tr('Signature ajoutée aux nouveaux messages et réponses (gras, liens, listes…)'))
        self.signature.setAccessibleName(tr('Signature du compte'))
        layout.addWidget(label(tr('Signature du compte'),'Bold'))
        self.signature_bar = FormatBar(self.signature, self.appearance)
        layout.addWidget(self.signature_bar)
        layout.addWidget(self.signature)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.test = Button(tr('Tester la connexion IMAP et SMTP'),self.appearance,'refresh-cw','Secondary')
        self.test.clicked.connect(self.test_servers)
        layout.addWidget(self.test)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.Save)
        self.save_button.setText(tr('Enregistrer'))
        self.save_button.setObjectName('Primary')
        buttons.button(QDialogButtonBox.Cancel).setText(tr('Annuler'))
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.address.editingFinished.connect(self.detect)
        if account:
            self.setWindowTitle(tr('Paramètres du compte'))
            self.name.setText(account.name)
            self.address.setText(account.email)
            self.client_id.setText(account.oauth_client_id)
            self.tenant.setText(account.oauth_tenant)
            self.auth.setCurrentIndex(['password', 'google', 'microsoft'].index(account.auth_method))
            stored = database.cache_get('signature', account.id)
            if stored and stored.get('qt_html'):
                self.signature.setHtml(stored['qt_html'])
            else:
                self.signature.setPlainText(account.signature)
            for protocol in ('imap', 'smtp'):
                config = getattr(account, protocol)
                host, mode, port = self.servers[protocol]
                host.setText(config.host)
                mode.setCurrentIndex(MODES.index(config.mode))
                port.setValue(config.port)
                self.logins[protocol].setText(getattr(account, protocol + '_login'))
            try:
                secrets.get(account.id + ':smtp')
                self.same_smtp_password.setChecked(False)  # Un mot de passe SMTP distinct est enregistré.
                self.smtp_password.setPlaceholderText(tr('Enregistré — saisir pour le remplacer'))
            except Exception:
                pass
        self.auth.currentIndexChanged.connect(self.auth_changed)
        self.auth_changed()
        self.show_servers(account is not None)  # Nouveau compte : la détection les remplit d’abord.

    def uses_smail_app(self):
        """Vrai si le compte utilise l’application OAuth2 de Smail (champs techniques inutiles)."""
        from mailclient.core import oauth_apps
        provider = {1: 'google', 2: 'microsoft'}.get(self.auth.currentIndex())
        return bool(provider) and oauth_apps.available(provider) and \
            self.client_id.text().strip() in ('', oauth_apps.client_id(provider))

    def auth_changed(self, *_):
        oauth = self.auth.currentIndex() != 0
        from mailclient.core import oauth_apps
        provider = {1: 'google', 2: 'microsoft'}.get(self.auth.currentIndex())
        smail_ids = {'', oauth_apps.client_id('google'), oauth_apps.client_id('microsoft')}
        if provider and not self.own_app.isChecked() and oauth_apps.available(provider) and self.client_id.text().strip() in smail_ids:
            self.client_id.setText(oauth_apps.client_id(provider))  # Application de Smail du bon fournisseur.
        # Identifiants techniques montrés seulement pour sa propre application (ou sans application Smail).
        self.oauth_group.setVisible(oauth and (self.own_app.isChecked() or not self.uses_smail_app()))
        self.own_app.setVisible(oauth and self.quick.isVisible())
        self.password.setEnabled(not oauth and not self.busy)
        self.client_id.setEnabled(oauth and not self.busy)
        self.client_secret.setEnabled(self.auth.currentIndex() == 1 and not self.busy)
        self.tenant.setEnabled(self.auth.currentIndex() == 2 and not self.busy)
        self.authorize_button.setEnabled(oauth and not self.busy)
        for field in (*self.logins.values(), self.same_smtp_password):
            field.setEnabled(not oauth and not self.busy)  # OAuth2 : l’identité est l’adresse e-mail.
        self.smtp_password.setEnabled(not oauth and not self.busy and not self.same_smtp_password.isChecked())

    def mode_changed(self, protocol, index):
        self.servers[protocol][2].setValue(PORTS[protocol][index])
        insecure = any(fields[1].currentData() == 'Aucun' for fields in self.servers.values())
        self.warning.setVisible(insecure)
        self.warning_frame.setVisible(insecure)
        self.confirm.setVisible(insecure)
        self.confirm.setChecked(False)

    def show_servers(self, visible):
        self.server_panel.setVisible(visible)
        self.server_toggle.setText(tr('Masquer les réglages des serveurs') if visible else tr('Réglages des serveurs'))

    def servers_edited(self, *_):
        self.manual_servers = True  # Saisie manuelle : la détection ne l’écrase plus.

    def apply_detected(self, found):
        for protocol in ('imap', 'smtp'):
            server = getattr(found, protocol)
            host, mode, port = self.servers[protocol]
            host.setText(server.host)
            mode.setCurrentIndex(MODES.index(server.mode))  # Remet le port par défaut du mode…
            port.setValue(server.port)                     # … puis le port annoncé.
            self.logins[protocol].setText(getattr(found, protocol + '_login'))
        self.detect_status.setText(tr('Réglages trouvés ({source}) : réception {host}:{port}, envoi {host2}:{port2}. Utilisez « Tester la connexion » pour vérifier.').format(source=found.source, host=found.imap.host, port=found.imap.port, host2=found.smtp.host, port2=found.smtp.port))
        from mailclient.core import oauth_apps
        provider = oauth_apps.provider_for(found.imap.host)
        if provider and oauth_apps.available(provider) and self.auth.currentIndex() == 0:
            name = 'Google' if provider == 'google' else 'Microsoft'
            self.detect_status.setText(tr('Compte {name} : le plus simple est « Se connecter avec {name} », sans mot de passe à saisir dans Smail.').format(name=name))

    def preset(self):
        """Fournisseurs connus : réglages immédiats, sans réseau."""
        from mailclient.core import autoconfig
        found = autoconfig.known(self.address.text())
        if found and not self.manual_servers:
            self.apply_detected(found)
        return found

    def detect(self):
        """Détection des serveurs à partir de l’adresse (nouveau compte, serveurs non saisis à la main)."""
        from mailclient.core import autoconfig
        address = self.address.text().strip()
        if self.original is not None or self.manual_servers or self.busy or not autoconfig.domain_of(address):
            return
        if self.preset():
            return
        self.detection += 1
        ticket = self.detection
        self.detect_status.setText(tr('Recherche des réglages de votre messagerie…'))
        def done(found):
            if ticket != self.detection or self.manual_servers or self.address.text().strip() != address:
                return  # Adresse modifiée ou saisie manuelle entre-temps.
            if found:
                self.apply_detected(found)
                if 'habituels' in found.source:
                    self.show_servers(True)
            else:
                self.detect_status.setText(tr('Réglages introuvables automatiquement : renseignez les serveurs fournis par votre '
                                           'hébergeur ci-dessous.'))
                self.show_servers(True)
        def failed(message):
            if ticket == self.detection:
                done(None)
        self.runner.run(lambda: autoconfig.detect(address), done, failed)

    def values(self):
        servers = {p: Server(h.text().strip(), port.value(), m.currentData()) for p, (h,m,port) in self.servers.items()}
        account = Account(self.name.text().strip(), self.address.text().strip(), **servers)
        account.auth_method = ['password', 'google', 'microsoft'][self.auth.currentIndex()]
        account.oauth_client_id = self.client_id.text().strip()
        account.signature = self.signature.mail_parts()[1]  # Version texte : clients sans HTML et Smail 1.0.0.
        account.oauth_tenant = self.tenant.text().strip() or 'common'
        if account.auth_method == 'password':
            account.imap_login = self.logins['imap'].text().strip()
            account.smtp_login = self.logins['smtp'].text().strip()
            if '\x00' in self.smtp_password.text():
                raise ValueError(tr('Saisissez un mot de passe SMTP valide.'))
        if self.account_id:
            account.id = self.account_id
        else:
            self.account_id = account.id
        account.validate()
        if account.auth_method == 'password' and ((not self.password.text() and (not self.original or self.original.auth_method != 'password')) or '\x00' in self.password.text()):
            raise ValueError(tr('Saisissez un mot de passe valide.'))
        if any(s.mode == 'Aucun' for s in servers.values()) and not self.confirm.isChecked():
            raise ValueError(tr('Vous devez confirmer explicitement le risque de connexion en clair.'))
        return account, self.password.text()

    def set_busy(self, busy):
        self.busy = busy
        self.test.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        for field in (self.name, self.address, self.password, self.confirm, self.auth, self.client_id, self.client_secret, self.signature, self.tenant):
            field.setEnabled(not busy)
        for fields in self.servers.values():
            for field in fields:
                field.setEnabled(not busy)
        self.auth_changed()

    def one_click(self, provider):
        """« Se connecter avec Google / Microsoft » : application Smail, serveurs du fournisseur, navigateur."""
        from mailclient.core import autoconfig, oauth_apps
        address = self.address.text().strip()
        if not autoconfig.domain_of(address):
            self.status.setText(tr('Saisissez d’abord votre adresse e-mail (et votre nom), puis cliquez de nouveau.'))
            self.address.setFocus()
            return
        self.own_app.setChecked(False)
        self.client_secret.clear()
        self.tenant.setText(tr('common'))
        self.client_id.setText(oauth_apps.client_id(provider))
        self.auth.setCurrentIndex(1 if provider == 'google' else 2)
        if oauth_apps.provider_for(self.servers['imap'][0].text()) != provider:
            # Domaine personnel (Workspace, Microsoft 365) ou serveurs vides : serveurs du fournisseur.
            self.apply_detected(autoconfig.known('x@gmail.com' if provider == 'google' else 'x@outlook.com'))
        self.authorize()

    def authorize(self):
        try:
            account, _ = self.values()
            if self.client_secret.text():
                self.secrets.set(account.id + ':oauth-client-secret', self.client_secret.text())
        except ValueError as error:
            self.status.setText(str(error))
            return
        except Exception:
            self.status.setText(tr('Vérifiez les paramètres du compte, l’identifiant client et le coffre Windows.'))
            return
        self.oauth_cancelled.clear()
        self.set_busy(True)
        self.status.setText(tr('Connectez-vous et autorisez Smail dans votre navigateur (3 minutes au plus). Annuler permet d’interrompre.'))
        self.runner.run(lambda: self.oauth.authorize(account, self.oauth_cancelled),
                        lambda _: self.finished_test(tr('Connexion autorisée. Cliquez sur « Enregistrer » pour terminer.')), self.finished_test)

    def test_servers(self):
        try:
            account, password = self.values()
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.set_busy(True)
        self.status.setText(tr('Test des deux serveurs en cours…'))
        smtp_password = self.smtp_password.text() if not self.same_smtp_password.isChecked() else ''
        def operation():
            credential = password if account.auth_method == 'password' and password else self.oauth.credential(account)
            client = IMAPClient(account, credential, self.runner.tls).open()
            client.logout()
            smtp_credential = smtp_password or (credential if account.auth_method != 'password' or password or self.same_smtp_password.isChecked()
                                                else self.oauth.credential(account, 'smtp'))
            test_connection(account, smtp_credential, self.runner.tls)
        self.runner.run(operation, lambda _: self.finished_test(tr('Connexions IMAP et SMTP réussies.')), self.finished_test)

    def finished_test(self, message):
        self.set_busy(False)
        self.status.setText(message)

    def save(self):
        try:
            account, password = self.values()
        except ValueError as error:
            self.status.setText(str(error))
            return
        try:
            if account.auth_method == 'password' and password:
                self.secrets.set(account.id, password)
            elif account.auth_method != 'password':
                if not self.oauth.is_authorized(account):
                    raise RuntimeError(tr('Autorisation OAuth2 nécessaire.'))
            if account.auth_method == 'password':
                if self.same_smtp_password.isChecked():
                    if hasattr(self.secrets, 'delete'):
                        self.secrets.delete(account.id + ':smtp')
                elif self.smtp_password.text():
                    self.secrets.set(account.id + ':smtp', self.smtp_password.text())
            self.database.save(account)
            formatted = bool(self.signature.mail_parts()[0])
            save_signature(self.database, account.id, self.signature.toHtml() if formatted else '')
        except Exception:
            self.status.setText(tr('Enregistrement impossible. Vérifiez les champs, la confirmation de connexion en clair et la disponibilité du Gestionnaire d’identifiants Windows.'))
            return
        self.password.clear()
        self.accept()

    def reject(self):
        if self.busy:
            self.oauth_cancelled.set()
        if not self.busy:
            self.password.clear()
            super().reject()
