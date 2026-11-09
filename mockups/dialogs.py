"""Écrans secondaires : interactions locales et démonstrations sans effets réels."""
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QKeySequence, QShortcut, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QWidget, QLineEdit, QPlainTextEdit, QComboBox, QCheckBox, QGroupBox, QSpinBox,
    QListWidget, QListWidgetItem, QStackedWidget, QColorDialog, QScrollArea, QMenu)
from .components import label, Button, Card, Banner, separator, IconLabel, later
from .data import ACCOUNTS
from .theme import VARIANTS, ACCENTS

class Dialog(QDialog):
    def __init__(self, theme, title, subtitle, parent=None, size=(800,700)):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle(title + ' · Maquette Smail')
        self.resize(*size)
        self.setMinimumSize(min(size[0],660), min(size[1],480))
        self.outer = QVBoxLayout(self)
        margin = {1:20, 2:28, 3:18}[theme.variant]
        self.outer.setContentsMargins(margin,margin,margin,margin)
        self.eyebrow = label('', 'Eyebrow')
        self.outer.addWidget(self.eyebrow)
        self.outer.addWidget(label(title, 'DialogTitle'))
        self.outer.addWidget(label(subtitle, 'Subtitle', True))
        self.content = Card(margin=20 if theme.variant != 2 else 28)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.content)
        self.outer.addWidget(scroll, 1)
        self.theme.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.eyebrow.setText(f'MAQUETTE  /  0{self.theme.variant} · {VARIANTS[self.theme.variant][0].upper()}')

    def footer(self, primary='Enregistrer', callback=None, cancel='Annuler'):
        row = QHBoxLayout()
        row.addWidget(label('Données fictives · aucune opération réelle', 'Small'))
        row.addStretch()
        back = Button(cancel, self.theme, role='Secondary')
        self.cancel_button = back
        back.clicked.connect(self.reject)
        back.setDefault(True)
        row.addWidget(back)
        self.primary = Button(primary, self.theme, role='Primary')
        self.primary.setAutoDefault(False)
        self.primary.clicked.connect(callback or self.accept)
        row.addWidget(self.primary)
        self.outer.addLayout(row)
        return self.primary

class ComposeDialog(Dialog):
    def __init__(self, theme, parent=None, reply=False):
        title = 'Transférer le message' if reply == 'forward' else 'Répondre à tous' if reply == 'all' else 'Répondre à Élodie' if reply else 'Nouveau message'
        super().__init__(theme, title,
                         'Une rédaction claire, de l’expéditeur à la signature.', parent, (900,800))
        box = self.content.box
        form = QFormLayout()
        form.setSpacing(10)
        self.account = QComboBox()
        self.account.addItems([f'{a.name} · {a.address}' for a in ACCOUNTS])
        form.addRow('&De', self.account)
        self.to = QLineEdit('elodie.bernard@atelier-nord.example')
        if reply == 'forward':
            self.to.clear()
        form.addRow('&À', self.to)
        toggles = QHBoxLayout()
        self.cc_toggle = Button('Cc', theme)
        self.bcc_toggle = Button('Cci', theme)
        toggles.addWidget(self.cc_toggle)
        toggles.addWidget(self.bcc_toggle)
        toggles.addStretch()
        form.addRow('', toggles)
        self.cc = QLineEdit('thomas.leroy@atelier.example')
        self.bcc = QLineEdit()
        self.bcc.setPlaceholderText('Destinataires masqués')
        form.addRow('&Cc', self.cc)
        form.addRow('Cc&i', self.bcc)
        self.cc_toggle.clicked.connect(lambda: self.cc.setVisible(not self.cc.isVisible()))
        self.bcc_toggle.clicked.connect(lambda: self.bcc.setVisible(not self.bcc.isVisible()))
        self.subject = QLineEdit('Re: Planche d’inspiration — la nouvelle collection')
        if reply == 'forward':
            self.subject.setText('Tr: Planche d’inspiration — la nouvelle collection')
        form.addRow('&Objet', self.subject)
        box.addLayout(form)
        box.addWidget(separator())
        self.body = QPlainTextEdit('Bonjour Élodie,\n\nMerci pour ces premières pistes, elles correspondent très bien à l’esprit du projet.\n\nJeudi à 14 h me convient. Je vous joins le brief mis à jour pour préparer notre échange.\n\nÀ jeudi,\nCamille')
        self.body.setTabChangesFocus(True)
        self.body.setAccessibleName('Corps du message')
        box.addWidget(self.body, 1)
        self.signature = label('Camille Martin\nDesign & projets · Atelier\ncamille@atelier.example', 'Subtitle', True)
        box.addWidget(self.signature)
        self.account.currentIndexChanged.connect(self.change_signature)
        self.attachments = QHBoxLayout()
        self.attachment = Button('Brief-collection.pdf  ·  1,8 Mo', theme, 'file-text', 'Secondary')
        self.attachment.clicked.connect(lambda: self.status.setText('Pièce jointe fictive sélectionnée.'))
        self.attachments.addWidget(self.attachment)
        attach = Button('Joindre', theme, 'paperclip')
        attach.clicked.connect(self.add_attachment)
        self.attachments.addWidget(attach)
        extra = Button('',theme,'ellipsis',tooltip='Options du brouillon et des pièces jointes')
        extra.clicked.connect(self.more)
        self.attachments.addWidget(extra)
        self.attachments.addStretch()
        box.addLayout(self.attachments)
        self.status = label('Brouillon de démonstration · modifications conservées en mémoire', 'Small')
        box.addWidget(self.status)
        self.body.textChanged.connect(lambda: self.status.setText('Brouillon mis à jour en mémoire · aucune sauvegarde sur disque'))
        self.footer('Envoyer  ·  Ctrl+Entrée', self.send)
        QShortcut(QKeySequence('Ctrl+Return'), self, activated=self.send)

    def more(self):
        menu = QMenu(self)
        for title,text in [('Copier aux brouillons du serveur','Copie du brouillon simulée ; aucun serveur contacté.'),
                           ('Supprimer le brouillon','Suppression simulée de ce brouillon fictif.'),
                           ('Simuler un envoi partiel','Envoi partiel simulé : les destinataires refusés restent dans le brouillon.')]:
            menu.addAction(title,lambda value=text:self.status.setText(value))
        menu.addAction('Retirer la pièce jointe',lambda:self.attachment.hide())
        menu.exec(self.mapToGlobal(self.rect().center()))

    def change_signature(self, index):
        account = ACCOUNTS[index]
        self.signature.setText(f'Camille Martin\n{account.name}\n{account.address}')

    def add_attachment(self):
        self.attachments.insertWidget(1, Button('Notes-reunion.txt  ·  4 Ko', self.theme, 'file-text', 'Secondary'))
        self.status.setText('Une pièce jointe fictive a été ajoutée. Aucun fichier local n’a été lu.')

    def send(self):
        if not self.to.text().strip():
            self.status.setText('Ajoutez un destinataire pour poursuivre la simulation.')
            self.to.setFocus()
            return
        self.primary.setText('Envoi simulé…')
        self.primary.setEnabled(False)
        def finish():
            self.primary.setText('Envoyer à nouveau (simulation)')
            self.primary.setEnabled(True)
            self.status.setText('Simulation terminée : aucun message n’a été envoyé.')
        later(self,650,finish)

class AccountDialog(Dialog):
    def __init__(self, theme, parent=None, insecure=False):
        super().__init__(theme, 'Ajouter un compte', 'Vos accès et la sécurité de chaque serveur, au même endroit.', parent, (940,810))
        box = self.content.box
        details = QGridLayout()
        self.name, self.address = QLineEdit('Association'), QLineEdit('contact@association.example')
        self.password = QLineEdit('exemple-fictif')
        self.password.setEchoMode(QLineEdit.Password)
        self.auth = QComboBox()
        self.auth.addItems(['Mot de passe d’application', 'OAuth2 Google', 'OAuth2 Microsoft'])
        for i,(title,widget) in enumerate([('Nom du compte',self.name),('Adresse e-mail',self.address),('Authentification',self.auth),('Mot de passe',self.password)]):
            details.addWidget(label(title, 'Subtitle'), (i//2)*2,i%2)
            details.addWidget(widget, (i//2)*2+1,i%2)
            widget.setAccessibleName(title)
        box.addLayout(details)
        self.oauth = Card('Attachment',12)
        self.oauth.box.addWidget(label('Configuration OAuth2', 'Bold'))
        oauth_form = QFormLayout()
        self.client = QLineEdit()
        self.client.setPlaceholderText('Identifiant de votre application')
        oauth_form.addRow('Identifiant client', self.client)
        tenant = QLineEdit('common')
        oauth_form.addRow('Tenant Microsoft', tenant)
        self.oauth.box.addLayout(oauth_form)
        authorize = Button('Connecter dans le navigateur (simulation)', theme, 'arrow-up-right', 'Secondary')
        authorize.clicked.connect(lambda: self.status.setText('Autorisation OAuth2 simulée. Aucun navigateur ni réseau utilisé.'))
        self.oauth.box.addWidget(authorize)
        self.oauth.hide()
        box.addWidget(self.oauth)
        self.auth.currentIndexChanged.connect(self.auth_changed)
        servers = QHBoxLayout()
        self.servers = {}
        for protocol, port in [('IMAP',993), ('SMTP',465)]:
            group = QGroupBox('Réception · IMAP' if protocol == 'IMAP' else 'Envoi · SMTP')
            form = QFormLayout(group)
            host = QLineEdit(('imap' if protocol == 'IMAP' else 'smtp') + '.association.example')
            connection = QComboBox()
            connection.addItems(['SSL/TLS', 'STARTTLS', 'Aucun'])
            number = QSpinBox()
            number.setRange(1,65535)
            number.setValue(port)
            form.addRow('&Serveur', host)
            form.addRow('&Chiffrement', connection)
            form.addRow('&Port', number)
            self.servers[protocol] = (host,connection,number)
            connection.currentIndexChanged.connect(lambda value,p=protocol: self.mode_changed(p,value))
            servers.addWidget(group)
        box.addLayout(servers)
        self.secure = Banner('Connexion chiffrée', 'La vérification du certificat reste activée par défaut.', theme)
        self.warning = Banner('Connexion non chiffrée', 'Votre mot de passe et vos mails circuleront en clair et pourront être lus par des tiers. Non recommandé.', theme, 'Danger', 'lock-keyhole-open')
        self.confirm = QCheckBox('Je comprends le risque et confirme ce choix pour ce compte.')
        self.confirm.toggled.connect(self.validate)
        box.addWidget(self.secure)
        box.addWidget(self.warning)
        box.addWidget(self.confirm)
        self.warning.hide()
        self.confirm.hide()
        testrow = QHBoxLayout()
        self.test_button = Button('Tester la connexion', theme, 'refresh-cw', 'Secondary')
        self.test_button.clicked.connect(self.test)
        testrow.addWidget(self.test_button)
        self.status = label('Aucun test réel : maquette sans réseau.', 'Small', True)
        testrow.addWidget(self.status,1)
        box.addLayout(testrow)
        advanced_button = Button('Signature et options avancées',theme,'chevron-down','Secondary')
        box.addWidget(advanced_button)
        self.advanced = Card('Attachment',12)
        self.advanced.box.addWidget(label('Signature du compte','Bold'))
        signature = QPlainTextEdit('Camille Martin\nAssociation du quartier')
        signature.setTabChangesFocus(True)
        signature.setMaximumHeight(65)
        signature.setAccessibleName('Signature personnalisée du compte')
        self.advanced.box.addWidget(signature)
        secret = QLineEdit()
        secret.setEchoMode(QLineEdit.Password)
        secret.setPlaceholderText('Secret client Google (si requis)')
        secret.setAccessibleName('Secret client Google fictif')
        self.advanced.box.addWidget(secret)
        self.advanced.hide()
        box.addWidget(self.advanced)
        advanced_button.clicked.connect(lambda:self.advanced.setVisible(not self.advanced.isVisible()))
        box.addStretch()
        self.footer('Ajouter le compte', self.save)
        if insecure:
            self.servers['IMAP'][1].setCurrentIndex(2)
            self.servers['SMTP'][1].setCurrentIndex(2)

    def auth_changed(self, index):
        self.oauth.setVisible(index != 0)
        self.password.setEnabled(index == 0)
        self.validate()

    def mode_changed(self, protocol, mode):
        self.servers[protocol][2].setValue({'IMAP':[993,143,143], 'SMTP':[465,587,25]}[protocol][mode])
        insecure = any(fields[1].currentIndex() == 2 for fields in self.servers.values())
        self.warning.setVisible(insecure)
        self.confirm.setVisible(insecure)
        self.secure.setVisible(not insecure)
        self.confirm.setChecked(False)
        self.validate()

    def validate(self):
        insecure = any(fields[1].currentIndex() == 2 for fields in self.servers.values())
        valid = not insecure or self.confirm.isChecked()
        if self.auth.currentIndex() != 0 and insecure:
            valid = False
            self.status.setText('OAuth2 exige une connexion chiffrée pour les deux serveurs.')
        if hasattr(self,'primary'):
            self.primary.setEnabled(valid)
        self.test_button.setEnabled(valid)

    def test(self):
        self.status.setText('Vérification simulée en cours…')
        later(self,650,lambda: self.status.setText('Test simulé réussi · aucune connexion effectuée.'))

    def save(self):
        self.status.setText('Compte fictif ajouté à la démonstration. Rien n’a été enregistré.')
        self.primary.setText('Ajout simulé')

class CertificateDialog(Dialog):
    def __init__(self, theme, parent=None):
        super().__init__(theme, 'Vérifier le certificat', 'La connexion a été interrompue avant l’envoi de vos identifiants.', parent, (770,660))
        self.content.box.addWidget(Banner('L’identité du serveur ne peut pas être confirmée', 'Le certificat présenté a expiré. Si vous ne connaissez pas ce serveur, annulez la connexion.', theme, 'Danger', 'shield-alert'))
        form = QFormLayout()
        form.setSpacing(12)
        for title,value in [('Compte','Association · contact@association.example'), ('Serveur','imap.association.example : 993'),
                            ('Émetteur','Autorité interne · Association'), ('Validité','3 novembre 2025 → 3 novembre 2026'),
                            ('Motif','Certificat expiré depuis le 3 novembre 2026')]:
            form.addRow(label(title,'Subtitle'),label(value,wrap=True))
        self.content.box.addLayout(form)
        self.content.box.addWidget(label('EMPREINTE SHA-256', 'Eyebrow'))
        fingerprint = label('A8:4D:2F:60:17:AC:93:5B:81:CE:09:43:EB:72:14:BF\n4C:3E:91:7A:02:DD:8F:63:6E:30:15:C7:9A:EF:44:10', 'Small', True)
        fingerprint.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.TextSelectableByKeyboard)
        self.content.box.addWidget(fingerprint)
        self.remember = QCheckBox('Toujours faire confiance à ce certificat pour ce compte')
        self.content.box.addWidget(self.remember)
        self.content.box.addWidget(label('Une empreinte différente déclenchera une nouvelle alerte. Décision simulée uniquement.', 'Small', True))
        self.content.box.addStretch()
        self.footer('Continuer quand même', self.continue_demo)
        self.cancel_button.setObjectName('Primary')
        self.cancel_button.role = 'Primary'
        self.primary.setObjectName('QuietDanger')
        self.primary.role = 'QuietDanger'

    def continue_demo(self):
        self.primary.setText('Décision simulée')
        self.primary.setEnabled(False)

class AttachmentDialog(Dialog):
    def __init__(self, theme, parent=None):
        super().__init__(theme, 'Pièce jointe à risque', 'Prenez un instant pour vérifier l’expéditeur et le type de fichier.', parent, (720,530))
        self.content.box.addWidget(Banner('Ce fichier peut exécuter du code', 'Son nom masque une extension exécutable. Il ne s’agit pas d’un document PDF.', theme, 'Danger', 'shield-alert'))
        self.content.box.addWidget(label('Facture_novembre.pdf.exe', 'MessageTitle', True))
        self.content.box.addWidget(label('Application Windows · 186 Ko\nExpéditeur : Service facturation', 'Subtitle', True))
        self.content.box.addWidget(label('Aucune pièce jointe n’est ouverte automatiquement. Ici, le bouton ne crée aucun fichier.', 'Small', True))
        self.content.box.addStretch()
        self.footer('Enregistrer (simulation)', lambda: self.primary.setText('Aucun fichier créé'))
        self.cancel_button.setObjectName('Primary')
        self.cancel_button.role = 'Primary'
        self.primary.setObjectName('Secondary')
        self.primary.role = 'Secondary'

class SettingsDialog(Dialog):
    def __init__(self, theme, parent=None, page=0):
        super().__init__(theme, 'Paramètres', 'Une apparence à votre mesure. Des choix de sécurité toujours explicites.', parent, (1000,760))
        box = self.content.box
        split = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setObjectName('SettingsNav')
        self.nav.setAccessibleName('Catégories des paramètres')
        self.nav.setFixedWidth(180)
        self.nav.addItems(['Apparence', 'Comptes', 'Sécurité', 'Raccourcis'])
        split.addWidget(self.nav)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.appearance())
        self.pages.addWidget(self.accounts())
        self.pages.addWidget(self.security())
        self.pages.addWidget(self.shortcuts())
        split.addWidget(self.pages,1)
        box.addLayout(split)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(page)
        self.footer('Terminé', self.accept, 'Fermer')

    def appearance(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label('L’espace qui vous ressemble', 'Title', True))
        box.addWidget(label('Les changements s’appliquent immédiatement à toutes les maquettes.', 'Subtitle', True))
        for variant,(name,description) in VARIANTS.items():
            button = Button(f'0{variant}   {name}\n       {description}', self.theme, 'layout-panel-left', 'Secondary')
            button.clicked.connect(lambda checked=False,v=variant: self.theme.update(variant=v))
            box.addWidget(button)
        form = QFormLayout()
        theme = QComboBox()
        theme.addItems(['Clair','Sombre'])
        theme.setCurrentIndex(int(self.theme.dark))
        theme.currentIndexChanged.connect(lambda value: self.theme.update(dark=bool(value)))
        form.addRow('Thème',theme)
        density = QComboBox()
        density.addItems(['Compacte','Normale','Aérée'])
        density.setCurrentText(self.theme.density)
        density.currentTextChanged.connect(lambda value: self.theme.update(density=value))
        form.addRow('Densité',density)
        accent = QComboBox()
        accent.addItems(list(ACCENTS))
        accent.setCurrentText(self.theme.accent_name)
        accent.currentTextChanged.connect(lambda value: self.theme.update(accent_name=value,custom_accent=None))
        form.addRow('Couleur d’accent',accent)
        custom = Button('Choisir une autre couleur…',self.theme,'palette','Secondary')
        custom.clicked.connect(self.custom_color)
        form.addRow('',custom)
        box.addLayout(form)
        motion = QCheckBox('Réduire les animations')
        motion.setChecked(self.theme.reduced_motion)
        motion.toggled.connect(lambda value: self.theme.update(reduced_motion=value))
        box.addWidget(motion)
        box.addWidget(label('Les couleurs trop claires ou trop foncées sont ajustées pour préserver le contraste.', 'Small', True))
        box.addStretch()
        return widget

    def custom_color(self):
        color = QColorDialog.getColor(QColor(self.theme.colors['accent']), self, 'Couleur d’accent')
        if color.isValid():
            self.theme.update(custom_accent=color.name())

    def accounts(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label('Trois comptes, une seule vue', 'Title', True))
        for account in ACCOUNTS:
            card = Card('Attachment',12)
            header = QHBoxLayout()
            identity = QVBoxLayout()
            identity.setSpacing(3)
            identity.addWidget(label(account.name,'Bold'))
            identity.addWidget(label(account.address,'Subtitle'))
            header.addLayout(identity,1)
            edit = Button('',self.theme,'settings-2',tooltip='Paramètres et signature du compte '+account.name)
            edit.clicked.connect(lambda checked=False,a=account:self.edit_account(a))
            header.addWidget(edit)
            card.box.addLayout(header)
            card.box.addWidget(Banner('SSL/TLS · certificat vérifié' if account.secure else 'Attention · connexion en clair',
                                      '',self.theme,
                                      'Info' if account.secure else 'Warning','lock-keyhole' if account.secure else 'lock-keyhole-open'))
            box.addWidget(card)
        add = Button('Ajouter un compte',self.theme,'plus','Secondary')
        add.clicked.connect(lambda: self.open_child(AccountDialog(self.theme,self)))
        box.addWidget(add)
        box.addStretch()
        return widget

    def edit_account(self, account):
        dialog = AccountDialog(self.theme,self,not account.secure)
        dialog.name.setText(account.name)
        dialog.address.setText(account.address)
        self.open_child(dialog)

    def security(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label('La sécurité reste visible', 'Title', True))
        box.addWidget(Banner('Contenus protégés, choix explicites', 'Cette maquette illustre les réglages existants, sans lire ni modifier leur valeur réelle.', self.theme))
        for text, checked in [('Vérifier les certificats des serveurs',True), ('Bloquer les images distantes par défaut',True),
                              ('Chiffrer les contenus du cache local',True), ('Afficher les notifications de nouveaux mails',True),
                              ('Utiliser IMAP IDLE si disponible',True), ('Réduire dans la zone de notification à la fermeture',True)]:
            check = QCheckBox(text)
            check.setChecked(checked)
            box.addWidget(check)
        form = QFormLayout()
        minutes = QSpinBox()
        minutes.setRange(1,120)
        minutes.setValue(5)
        limit = QSpinBox()
        limit.setRange(50,5000)
        limit.setValue(100)
        form.addRow('Synchroniser toutes les (min)',minutes)
        form.addRow('Messages hors ligne par dossier',limit)
        box.addLayout(form)
        box.addWidget(label('Les paramètres publics du compte et le schéma SQLite restent lisibles. Les fichiers exportés ne sont pas chiffrés par le cache.', 'Small', True))
        demo = Button('Voir une alerte de certificat',self.theme,'shield-alert','Secondary')
        demo.clicked.connect(lambda: self.open_child(CertificateDialog(self.theme,self)))
        box.addWidget(demo)
        box.addStretch()
        return widget

    def shortcuts(self):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.addWidget(label('Vos mains restent au clavier', 'Title', True))
        for title,key in [('Palette de commandes','Ctrl + K'),('Nouveau message','Ctrl + N'),('Rechercher','Ctrl + F'),
                          ('Répondre','Ctrl + R'),('Répondre à tous','Ctrl + Maj + R'),('Transférer','Ctrl + L'),
                          ('Synchroniser (simulation)','F5'),('Changer le thème','Ctrl + Maj + L'),
                          ('Changer la densité','Ctrl + Maj + D'),('Variante suivante','Alt + 1 / 2 / 3'),
                          ('Message suivant / précédent (V3)','J / K'),('Archiver / étoiler (V3)','E / S'),
                          ('Fermer un dialogue','Échap')]:
            row = QHBoxLayout()
            row.addWidget(label(title))
            row.addStretch()
            row.addWidget(label(key,'Key'))
            box.addLayout(row)
        box.addStretch()
        return widget

    def open_child(self, dialog):
        self.child = dialog
        dialog.open()

class CommandPalette(Dialog):
    def __init__(self, theme, commands, parent=None):
        super().__init__(theme, 'Que souhaitez-vous faire ?', 'Tapez une action, puis Entrée. Les flèches parcourent les résultats.', parent, (760,610))
        self.commands = commands
        self.search = QLineEdit()
        self.search.setObjectName('CommandInput')
        self.search.setPlaceholderText('Rechercher une commande…')
        self.search.setAccessibleName('Rechercher une commande')
        self.content.box.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName('Commands')
        self.list.setAccessibleName('Commandes disponibles')
        self.content.box.addWidget(self.list,1)
        self.content.box.addWidget(label('↑ ↓  choisir       Entrée  exécuter       Échap  fermer', 'Small'))
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.execute)
        self.list.itemActivated.connect(lambda item: self.execute())
        self.search.installEventFilter(self)
        self.filter('')
        later(self,0,self.search.setFocus)

    def filter(self, text):
        self.list.clear()
        for name,shortcut,callback in self.commands:
            if text.casefold() in name.casefold():
                item = QListWidgetItem(f'{name}    {shortcut}')
                item.setData(Qt.UserRole,callback)
                self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def execute(self):
        item = self.list.currentItem()
        if item:
            callback = item.data(Qt.UserRole)
            self.accept()
            callback()

    def eventFilter(self, obj, event):
        if obj == self.search and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Up,Qt.Key_Down):
            delta = 1 if event.key() == Qt.Key_Down else -1
            self.list.setCurrentRow(max(0,min(self.list.count()-1,self.list.currentRow()+delta)))
            return True
        return super().eventFilter(obj,event)
