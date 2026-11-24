"""Ajout de compte et test asynchrone des deux serveurs."""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
                               QSpinBox, QLabel, QCheckBox, QPushButton, QDialogButtonBox, QGroupBox, QPlainTextEdit, QScrollArea, QWidget)
from PySide6.QtCore import Qt
from mailclient.ui.rich_text import RichTextEdit, FormatBar
from mailclient.core.service import save_signature
from mailclient.core.accounts import Account, Server, MODES, PORTS, PRESETS
from mailclient.core.imap_client import IMAPClient
from mailclient.core.smtp_client import test_connection
from mailclient.core.sync import Runner
from mailclient.core.oauth import OAuth
import threading
from mailclient.ui.dialog_shell import dialog_layout
from mailclient.ui.components import Card, label, Button
from PySide6.QtWidgets import QHBoxLayout

WARNING = 'Votre mot de passe et vos mails circuleront en clair et pourront être lus par des tiers. Non recommandé.'

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
        self.setWindowTitle('Ajouter un compte')
        self.appearance, outer, layout = dialog_layout(self,'Paramètres du compte' if account else 'Ajouter un compte','Vos accès et la sécurité de chaque serveur.',(960,800))
        form = QFormLayout()
        form.setSpacing(10)
        self.name, self.address, self.password = QLineEdit(), QLineEdit(), QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        form.addRow('Nom du compte', self.name)
        form.addRow('Adresse e-mail / identifiant', self.address)
        form.addRow('Mot de passe d’application', self.password)
        self.auth = QComboBox()
        self.auth.addItems(['Mot de passe', 'OAuth2 Google', 'OAuth2 Microsoft'])
        self.client_id = QLineEdit()
        self.client_secret = QLineEdit()
        self.client_secret.setEchoMode(QLineEdit.Password)
        self.tenant = QLineEdit('common')
        self.authorize_button = Button('Connecter avec OAuth2 dans le navigateur',self.appearance,'arrow-up-right','Secondary')
        self.authorize_button.clicked.connect(self.authorize)
        form.addRow('Authentification', self.auth)
        layout.addLayout(form)
        self.oauth_group = QGroupBox('Autorisation OAuth2')
        oauth_form = QFormLayout(self.oauth_group)
        oauth_form.addRow('Identifiant client OAuth2',self.client_id)
        oauth_form.addRow('Secret client Google (si requis)',self.client_secret)
        oauth_form.addRow('Tenant Microsoft',self.tenant)
        oauth_form.addRow(self.authorize_button)
        layout.addWidget(self.oauth_group)
        self.servers = {}
        self.logins = {}
        servers_row = QHBoxLayout()
        layout.addLayout(servers_row)
        for protocol in ('imap', 'smtp'):
            group = QGroupBox(protocol.upper())
            fields = QFormLayout(group)
            host = QLineEdit()
            host.setAccessibleName('Serveur '+protocol.upper())
            mode = QComboBox()
            mode.setAccessibleName('Chiffrement '+protocol.upper())
            mode.addItems(MODES)
            port = QSpinBox()
            port.setAccessibleName('Port '+protocol.upper())
            port.setRange(1, 65535)
            port.setValue(PORTS[protocol][0])
            fields.addRow('Serveur', host)
            fields.addRow('Type de connexion chiffrée', mode)
            fields.addRow('Port', port)
            login = QLineEdit()
            login.setPlaceholderText('Vide : l’adresse e-mail')
            login.setAccessibleName('Identifiant de connexion '+protocol.upper())
            login.setToolTip('À renseigner seulement si votre hébergeur fournit un identifiant différent de l’adresse e-mail.')
            fields.addRow('Identifiant', login)
            self.logins[protocol] = login
            if protocol == 'smtp':
                self.same_smtp_password = QCheckBox('Mot de passe SMTP identique à celui du compte')
                self.same_smtp_password.setChecked(True)
                self.smtp_password = QLineEdit()
                self.smtp_password.setEchoMode(QLineEdit.Password)
                self.smtp_password.setAccessibleName('Mot de passe SMTP')
                self.smtp_password.setPlaceholderText('Mot de passe du serveur d’envoi')
                self.smtp_password.setEnabled(False)
                self.same_smtp_password.toggled.connect(lambda same: self.smtp_password.setEnabled(not same and self.auth.currentIndex() == 0))
                fields.addRow('', self.same_smtp_password)
                fields.addRow('Mot de passe SMTP', self.smtp_password)
            self.servers[protocol] = (host, mode, port)
            mode.currentIndexChanged.connect(lambda index, p=protocol: self.mode_changed(p, index))
            servers_row.addWidget(group)
        self.warning = QLabel(WARNING)
        self.warning.setWordWrap(True)
        self.warning.setTextFormat(Qt.PlainText)
        self.warning_frame = Card('Danger',12)
        self.warning_frame.box.addWidget(self.warning)
        self.confirm = QCheckBox('Je comprends et j’accepte le risque de connexion en clair.')
        layout.addWidget(self.warning_frame)
        layout.addWidget(self.confirm)
        self.warning.hide()
        self.warning_frame.hide()
        self.confirm.hide()
        self.signature = RichTextEdit(attachments=False)
        self.signature.setTabChangesFocus(True)
        self.signature.setMinimumHeight(90)
        self.signature.setMaximumHeight(140)
        self.signature.setPlaceholderText('Signature ajoutée aux nouveaux messages et réponses (gras, liens, listes…)')
        self.signature.setAccessibleName('Signature du compte')
        layout.addWidget(label('Signature du compte','Bold'))
        self.signature_bar = FormatBar(self.signature, self.appearance)
        layout.addWidget(self.signature_bar)
        layout.addWidget(self.signature)
        self.status = QLabel('OAuth2 : renseignez votre identifiant d’application Google/Microsoft, puis connectez-vous dans le navigateur.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.test = Button('Tester la connexion IMAP et SMTP',self.appearance,'refresh-cw','Secondary')
        self.test.clicked.connect(self.test_servers)
        layout.addWidget(self.test)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.Save)
        self.save_button.setText('Enregistrer')
        self.save_button.setObjectName('Primary')
        buttons.button(QDialogButtonBox.Cancel).setText('Annuler')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.address.editingFinished.connect(self.preset)
        if account:
            self.setWindowTitle('Paramètres du compte')
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
                self.smtp_password.setPlaceholderText('Enregistré — saisir pour le remplacer')
            except Exception:
                pass
        self.auth.currentIndexChanged.connect(self.auth_changed)
        self.auth_changed()

    def auth_changed(self, *_):
        oauth = self.auth.currentIndex() != 0
        self.oauth_group.setVisible(oauth)
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
        insecure = any(fields[1].currentText() == 'Aucun' for fields in self.servers.values())
        self.warning.setVisible(insecure)
        self.warning_frame.setVisible(insecure)
        self.confirm.setVisible(insecure)
        self.confirm.setChecked(False)

    def preset(self):
        domain = self.address.text().strip().lower().split('@')[-1]
        if domain in PRESETS:
            for protocol, host in zip(('imap', 'smtp'), PRESETS[domain]):
                fields = self.servers[protocol]
                if not fields[0].text():
                    fields[0].setText(host)
                    fields[1].setCurrentIndex(1 if protocol == 'smtp' else 0)

    def values(self):
        servers = {p: Server(h.text().strip(), port.value(), m.currentText()) for p, (h,m,port) in self.servers.items()}
        account = Account(self.name.text().strip(), self.address.text().strip(), **servers)
        account.auth_method = ['password', 'google', 'microsoft'][self.auth.currentIndex()]
        account.oauth_client_id = self.client_id.text().strip()
        account.signature = self.signature.mail_parts()[1]  # Version texte : clients sans HTML et Smail 1.0.0.
        account.oauth_tenant = self.tenant.text().strip() or 'common'
        if account.auth_method == 'password':
            account.imap_login = self.logins['imap'].text().strip()
            account.smtp_login = self.logins['smtp'].text().strip()
            if '\x00' in self.smtp_password.text():
                raise ValueError('Saisissez un mot de passe SMTP valide.')
        if self.account_id:
            account.id = self.account_id
        else:
            self.account_id = account.id
        account.validate()
        if account.auth_method == 'password' and ((not self.password.text() and (not self.original or self.original.auth_method != 'password')) or '\x00' in self.password.text()):
            raise ValueError('Saisissez un mot de passe valide.')
        if any(s.mode == 'Aucun' for s in servers.values()) and not self.confirm.isChecked():
            raise ValueError('Vous devez confirmer explicitement le risque de connexion en clair.')
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

    def authorize(self):
        try:
            account, _ = self.values()
            if self.client_secret.text():
                self.secrets.set(account.id + ':oauth-client-secret', self.client_secret.text())
        except Exception:
            self.status.setText('Vérifiez les paramètres du compte, l’identifiant client et le coffre Windows.')
            return
        self.oauth_cancelled.clear()
        self.set_busy(True)
        self.status.setText('Autorisez l’accès dans votre navigateur. Délai maximal : 3 minutes. Annuler permet d’interrompre.')
        self.runner.run(lambda: self.oauth.authorize(account, self.oauth_cancelled),
                        lambda _: self.finished_test('Autorisation OAuth2 enregistrée dans le coffre Windows.'), self.finished_test)

    def test_servers(self):
        try:
            account, password = self.values()
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.set_busy(True)
        self.status.setText('Test des deux serveurs en cours…')
        smtp_password = self.smtp_password.text() if not self.same_smtp_password.isChecked() else ''
        def operation():
            credential = password if account.auth_method == 'password' and password else self.oauth.credential(account)
            client = IMAPClient(account, credential, self.runner.tls).open()
            client.logout()
            smtp_credential = smtp_password or (credential if account.auth_method != 'password' or password or self.same_smtp_password.isChecked()
                                                else self.oauth.credential(account, 'smtp'))
            test_connection(account, smtp_credential, self.runner.tls)
        self.runner.run(operation, lambda _: self.finished_test('Connexions IMAP et SMTP réussies.'), self.finished_test)

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
                    raise RuntimeError('Autorisation OAuth2 nécessaire.')
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
            self.status.setText('Enregistrement impossible. Vérifiez les champs, la confirmation de connexion en clair et la disponibilité du Gestionnaire d’identifiants Windows.')
            return
        self.password.clear()
        self.accept()

    def reject(self):
        if self.busy:
            self.oauth_cancelled.set()
        if not self.busy:
            self.password.clear()
            super().reject()
