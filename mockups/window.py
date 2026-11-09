"""Trois compositions du même prototype. Toutes les actions restent en mémoire."""
import html
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QKeySequence, QShortcut, QAction
from PySide6.QtWidgets import (QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QComboBox, QLineEdit, QListWidget, QListWidgetItem, QSplitter, QStackedWidget,
    QMenu, QButtonGroup, QScrollArea)
from .data import ACCOUNTS, FOLDERS, messages
from .theme import VARIANTS, ACCENTS
from .icons import icon
from .components import (label, Button, Card, Banner, IconLabel, MailDelegate,
                         LocalTextBrowser, Skeleton, Moodboard, separator, fade, later)
from .dialogs import (ComposeDialog, AccountDialog, CertificateDialog, SettingsDialog,
                      CommandPalette, AttachmentDialog)

SCENES = [
    ('principale','01 · Fenêtre principale'), ('unifiee','02 · Réception unifiée'),
    ('redaction','03 · Rédaction'), ('ajout_compte','04 · Ajouter un compte'),
    ('compte_non_chiffre','05 · Compte sans chiffrement'), ('certificat','06 · Certificat invalide'),
    ('parametres_apparence','07 · Apparence'), ('parametres_comptes','08 · Comptes'),
    ('parametres_securite','09 · Sécurité'), ('parametres_raccourcis','10 · Raccourcis'),
    ('recherche','11 · Recherche et filtres'), ('vide','12 · Boîte vide'),
    ('sans_connexion','13 · Aucune connexion'), ('chargement','14 · Chargement'),
    ('palette','15 · Palette de commandes'), ('images_bloquees','16 · Images bloquées'),
    ('html','17 · Message HTML'), ('piece_suspecte','18 · Pièce jointe suspecte'),
    ('alerte_piece_jointe','19 · Alerte pièce jointe')]

def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())

class MockupWindow(QMainWindow):
    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.mails = messages()
        self.account_index = 0
        self.folder = 'Réception'
        self.state = 'normal'
        self.filter = 'Tous'
        self.date_filter = 'Toutes les dates'
        self.current_mail = None
        self.dialogs = []
        self.last_dialog = None
        self.setWindowTitle('Smail · Laboratoire d’interface · Données fictives')
        self.resize(1440,940)
        self.setMinimumSize(1160,780)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        self.studio = QFrame()
        self.studio.setObjectName('StudioBar')
        studio = QHBoxLayout(self.studio)
        studio.setContentsMargins(20,9,20,9)
        studio.addWidget(label('Smail', 'Brand'))
        studio.addWidget(label('MAQUETTES · HORS RÉSEAU','Badge'))
        studio.addStretch()
        self.variant_combo = QComboBox()
        self.variant_combo.setAccessibleName('Variante de design')
        for key,(name,_) in VARIANTS.items():
            self.variant_combo.addItem(f'0{key} · {name}',key)
        self.variant_combo.setMinimumWidth(230)
        self.variant_combo.setCurrentIndex(theme.variant-1)
        self.variant_combo.currentIndexChanged.connect(lambda index: self.theme.update(variant=index+1))
        self.theme_button = Button('Sombre',theme,'moon',tooltip='Basculer clair / sombre · Ctrl+Maj+L')
        self.theme_button.clicked.connect(self.toggle_theme)
        self.density_combo = QComboBox()
        self.density_combo.setAccessibleName('Densité d’affichage')
        self.density_combo.addItems(['Compacte','Normale','Aérée'])
        self.density_combo.setCurrentText(theme.density)
        self.density_combo.currentTextChanged.connect(lambda value: self.theme.update(density=value))
        self.accent_combo = QComboBox()
        self.accent_combo.setAccessibleName('Couleur d’accent')
        self.accent_combo.addItems(list(ACCENTS))
        self.accent_combo.currentTextChanged.connect(lambda value: self.theme.update(accent_name=value,custom_accent=None))
        self.scene_combo = QComboBox()
        self.scene_combo.setAccessibleName('Galerie des écrans à comparer')
        self.scene_combo.addItem('Parcourir les écrans…',None)
        for key,title in SCENES:
            self.scene_combo.addItem(title,key)
        self.scene_combo.setMinimumWidth(205)
        self.scene_combo.activated.connect(lambda index: self.show_scene(self.scene_combo.itemData(index)) if index else None)
        for widget in (self.variant_combo,self.theme_button,self.density_combo,self.accent_combo,self.scene_combo):
            studio.addWidget(widget)
        layout.addWidget(self.studio)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16,14,16,12)
        body_layout.setSpacing(12)
        self.header = Card('Header',16)
        self.header.box.setSpacing(5)
        heading_row = QHBoxLayout()
        titles = QVBoxLayout()
        self.eyebrow = label('', 'Eyebrow')
        self.title = label('Réception','Title')
        self.subtitle = label('','Subtitle')
        titles.addWidget(self.eyebrow)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        heading_row.addLayout(titles,1)
        self.search = QLineEdit()
        self.search.setObjectName('Search')
        self.search.setAccessibleName('Rechercher dans les messages fictifs')
        self.search.setPlaceholderText('Rechercher un message…  Ctrl+F')
        self.search.setMinimumWidth(340)
        self.search.textChanged.connect(self.search_changed)
        self.search.returnPressed.connect(lambda: self.set_state('normal'))
        heading_row.addWidget(self.search)
        self.command_button = Button('Ctrl+K',theme,'command', 'Secondary', 'Ouvrir la palette de commandes · Ctrl+K')
        self.command_button.clicked.connect(self.open_palette)
        heading_row.addWidget(self.command_button)
        self.sync_button = Button('',theme,'refresh-cw',tooltip='Synchroniser · F5 · simulation')
        self.sync_button.clicked.connect(self.simulate_sync)
        heading_row.addWidget(self.sync_button)
        self.settings_button = Button('',theme,'settings-2',tooltip='Ouvrir les paramètres')
        self.settings_button.clicked.connect(lambda: self.open_settings())
        heading_row.addWidget(self.settings_button)
        self.header.box.addLayout(heading_row)
        body_layout.addWidget(self.header)
        self.offline_banner = Banner('Vous êtes hors connexion', 'Aucun réseau n’est utilisé par cette maquette. Les messages fictifs restent consultables.',theme,'Warning','wifi-off','Réessayer')
        self.offline_banner.action.clicked.connect(self.simulate_sync)
        self.offline_banner.hide()
        body_layout.addWidget(self.offline_banner)
        self.splitter = QSplitter()
        self.splitter.setChildrenCollapsible(False)
        self.sidebar = QFrame()
        self.sidebar.setObjectName('Sidebar')
        self.sidebar.setMinimumWidth(200)
        self.sidebar.setMaximumWidth(290)
        sidebar_outer = QVBoxLayout(self.sidebar)
        sidebar_outer.setContentsMargins(0,0,0,0)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_content = QWidget()
        sidebar_scroll.setWidget(sidebar_content)
        sidebar_outer.addWidget(sidebar_scroll)
        self.sidebar_layout = QVBoxLayout(sidebar_content)
        self.sidebar_layout.setContentsMargins(14,18,14,14)
        self.sidebar_layout.setSpacing(8)
        self.splitter.addWidget(self.sidebar)
        self.list_panel = QFrame()
        self.list_panel.setObjectName('ListPanel')
        self.list_panel.setMinimumWidth(330)
        list_layout = QVBoxLayout(self.list_panel)
        list_layout.setContentsMargins(8,12,8,8)
        list_layout.setSpacing(4)
        self.list_title = label('Aujourd’hui', 'Bold')
        list_header = QHBoxLayout()
        list_header.setContentsMargins(12,0,8,4)
        list_header.addWidget(self.list_title,1)
        self.count_label = label('','Small')
        list_header.addWidget(self.count_label)
        list_layout.addLayout(list_header)
        self.filters_widget = QWidget()
        filters = QHBoxLayout(self.filters_widget)
        filters.setContentsMargins(4,4,4,8)
        filters.setSpacing(3)
        self.filter_buttons = []
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        for value in ('Tous','Non lus','Pièces jointes'):
            button = Button(value,theme,role='Nav')
            button.setCheckable(True)
            button.setChecked(value == 'Tous')
            button.clicked.connect(lambda checked=False,v=value: self.set_filter(v))
            self.filter_group.addButton(button)
            self.filter_buttons.append(button)
            filters.addWidget(button)
        list_layout.addWidget(self.filters_widget)
        self.search_filters = QWidget()
        search_filters = QHBoxLayout(self.search_filters)
        search_filters.setContentsMargins(7,2,7,7)
        self.account_filter = QComboBox()
        self.account_filter.setAccessibleName('Filtrer les résultats par compte')
        self.account_filter.addItems(['Tous les comptes']+[a.name for a in ACCOUNTS])
        self.account_filter.currentIndexChanged.connect(lambda index: self.populate())
        self.date_combo = QComboBox()
        self.date_combo.setAccessibleName('Filtrer les résultats par date')
        self.date_combo.addItems(['Toutes les dates','Aujourd’hui','Cette semaine'])
        self.date_combo.currentTextChanged.connect(lambda value: self.populate())
        search_filters.addWidget(self.account_filter,1)
        search_filters.addWidget(self.date_combo,1)
        list_layout.addWidget(self.search_filters)
        self.search_filters.hide()
        self.list_stack = QStackedWidget()
        self.mail_list = QListWidget()
        self.mail_list.setAccessibleName('Liste des messages : flèches pour parcourir, Entrée pour lire')
        self.mail_list.setMouseTracking(True)
        self.mail_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.delegate = MailDelegate(theme,self.mail_list)
        self.mail_list.setItemDelegate(self.delegate)
        self.mail_list.currentItemChanged.connect(self.selected)
        self.mail_list.itemActivated.connect(lambda item: self.browser.setFocus())
        self.list_stack.addWidget(self.mail_list)
        self.skeleton = Skeleton(theme)
        self.list_stack.addWidget(self.skeleton)
        self.empty_list = self.empty_view('inbox','Aucun message','Votre boîte a pris un peu d’avance sur vous.')
        self.list_stack.addWidget(self.empty_list)
        list_layout.addWidget(self.list_stack,1)
        pagination = QHBoxLayout()
        prev = Button('',theme,'chevron-left',tooltip='Page précédente')
        nxt = Button('',theme,'chevron-right',tooltip='Page suivante')
        prev.setEnabled(False)
        nxt.setEnabled(False)
        pagination.addWidget(label('50 messages par page','Small'),1)
        pagination.addWidget(prev)
        pagination.addWidget(nxt)
        list_layout.addLayout(pagination)
        self.splitter.addWidget(self.list_panel)
        self.reader_frame = QFrame()
        self.reader_frame.setObjectName('ReaderFrame')
        self.reader_frame.setMinimumWidth(450)
        self.reader_outer = QVBoxLayout(self.reader_frame)
        self.reader_outer.setContentsMargins(0,0,0,0)
        self.reader_stack = QStackedWidget()
        self.reader = QWidget()
        self.reader.setObjectName('Reader')
        self.reader_layout = QVBoxLayout(self.reader)
        self.reader_layout.setContentsMargins(24,16,24,18)
        self.reader_layout.setSpacing(12)
        self.build_reader()
        self.reader_stack.addWidget(self.reader)
        self.reader_placeholder = self.empty_view('mail','Chaque message a sa place','Sélectionnez un message pour le lire, ou rédigez-en un nouveau.')
        self.reader_stack.addWidget(self.reader_placeholder)
        loading = Card(margin=28)
        loading.box.addWidget(label('Le fil se prépare…','MessageTitle'))
        loading.box.addWidget(label('Chargement simulé · aucune connexion au serveur','Subtitle'))
        loading.box.addWidget(Skeleton(theme),1)
        self.reader_stack.addWidget(loading)
        disconnected = Card(margin=28)
        disconnected.box.addStretch()
        disconnected.box.addWidget(IconLabel('wifi-off',theme,'muted',42),0,Qt.AlignHCenter)
        disconnected.box.addWidget(label('Le réseau peut attendre.','MessageTitle',True))
        disconnected.box.addWidget(label('Aucune connexion disponible. Vos messages déjà synchronisés restent à portée de main.','Subtitle',True))
        cached = Button('Consulter le cache fictif',theme,'archive','Secondary')
        cached.clicked.connect(lambda:self.set_state('cached_offline'))
        disconnected.box.addWidget(cached)
        disconnected.box.addStretch()
        self.reader_stack.addWidget(disconnected)
        self.reader_outer.addWidget(self.reader_stack)
        self.splitter.addWidget(self.reader_frame)
        body_layout.addWidget(self.splitter,1)
        self.footer = QHBoxLayout()
        self.connection = label('Connexion chiffrée · SSL/TLS','Small')
        self.toast_label = label('Données fictives · toutes les actions sont simulées','Small')
        self.footer.addWidget(self.connection)
        self.footer.addStretch()
        self.footer.addWidget(self.toast_label)
        body_layout.addLayout(self.footer)
        layout.addWidget(body,1)
        self.setCentralWidget(root)
        self.setup_shortcuts()
        self.theme.changed.connect(self.appearance_changed)
        self.appearance_changed()

    def empty_view(self, name, title, description):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.setContentsMargins(24,24,24,24)
        box.addStretch()
        symbol = IconLabel(name,self.theme,'muted',42)
        box.addWidget(symbol,0,Qt.AlignHCenter)
        heading = label(title,'MessageTitle',True)
        heading.setAlignment(Qt.AlignCenter)
        box.addWidget(heading)
        description = label(description,'Subtitle',True)
        description.setAlignment(Qt.AlignCenter)
        box.addWidget(description)
        widget.heading, widget.description = heading, description
        button = Button('Revenir à la réception',self.theme,'inbox','Secondary')
        button.clicked.connect(lambda: self.show_scene('principale'))
        box.addWidget(button,0,Qt.AlignHCenter)
        box.addStretch()
        return widget

    def build_reader(self):
        tools = QHBoxLayout()
        self.reader_layout.addLayout(tools)
        for name,tip,callback in [('archive','Archiver le message · E',lambda:self.message_action('archive')),
                                  ('trash-2','Déplacer vers la corbeille · Suppr',lambda:self.message_action('trash')),
                                  ('folder','Déplacer vers un dossier',self.move_menu),
                                  ('star','Ajouter ou retirer des favoris · S',lambda:self.message_action('star'))]:
            button = Button('',self.theme,name,tooltip=tip)
            button.clicked.connect(callback)
            tools.addWidget(button)
        tools.addStretch()
        self.mode_button = Button('Texte brut',self.theme,tooltip='Basculer entre texte brut et HTML de démonstration')
        self.mode_button.clicked.connect(self.toggle_body)
        tools.addWidget(self.mode_button)
        more = Button('',self.theme,'ellipsis',tooltip='Autres actions sur le message')
        more.clicked.connect(self.more_menu)
        tools.addWidget(more)
        self.reader_layout.addWidget(separator())
        self.message_subject = label('', 'MessageTitle',True)
        self.reader_layout.addWidget(self.message_subject)
        sender = QHBoxLayout()
        self.avatar = label('EB','Avatar')
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setFixedSize(38,38)
        sender.addWidget(self.avatar)
        person = QVBoxLayout()
        person.setSpacing(3)
        self.sender_name = label('', 'Bold')
        self.sender_address = label('', 'Small')
        person.addWidget(self.sender_name)
        person.addWidget(self.sender_address)
        sender.addLayout(person,1)
        self.message_date = label('', 'Small')
        sender.addWidget(self.message_date)
        self.reader_layout.addLayout(sender)
        self.recipient = label('','Small',True)
        self.reader_layout.addWidget(self.recipient)
        self.remote_banner = Banner('Images distantes bloquées', 'Votre lecture reste privée tant que vous ne les affichez pas.',self.theme,'Info','image-off','Afficher')
        self.remote_banner.action.clicked.connect(self.reveal_images)
        self.reader_layout.addWidget(self.remote_banner)
        self.moodboard = Moodboard(self.theme)
        self.reader_layout.addWidget(self.moodboard)
        self.moodboard.hide()
        self.danger_banner = Banner('Pièce jointe potentiellement dangereuse', 'L’extension .exe peut exécuter du code. Le fichier ne sera pas ouvert.',self.theme,'Danger','shield-alert')
        self.reader_layout.addWidget(self.danger_banner)
        self.browser = LocalTextBrowser()
        self.reader_layout.addWidget(self.browser,1)
        self.attachment_title = label('PIÈCES JOINTES','Eyebrow')
        self.reader_layout.addWidget(self.attachment_title)
        self.attachment_box = QVBoxLayout()
        self.attachment_box.setSpacing(6)
        self.reader_layout.addLayout(self.attachment_box)
        response = QHBoxLayout()
        self.reply_button = Button('Répondre',self.theme,'reply','Secondary')
        self.reply_button.clicked.connect(lambda:self.open_compose(True))
        reply_all = Button('À tous',self.theme,'reply-all',tooltip='Répondre à tous · Ctrl+Maj+R')
        reply_all.clicked.connect(lambda:self.open_compose('all'))
        forward = Button('Transférer',self.theme,'forward')
        forward.clicked.connect(lambda:self.open_compose('forward'))
        response.addWidget(self.reply_button)
        response.addWidget(reply_all)
        response.addWidget(forward)
        response.addStretch()
        self.reader_layout.addLayout(response)

    def build_sidebar(self):
        clear_layout(self.sidebar_layout)
        compose = Button('Nouveau message',self.theme,'plus','Primary')
        compose.clicked.connect(lambda:self.open_compose())
        self.sidebar_layout.addWidget(compose)
        self.sidebar_layout.addSpacing(10 if self.theme.variant != 2 else 20)
        self.sidebar_layout.addWidget(label('VOS ESPACES' if self.theme.variant != 3 else 'ESPACE ACTIF','Eyebrow'))
        if self.theme.variant == 1:
            combo = QComboBox()
            combo.setAccessibleName('Compte actif')
            combo.addItems(['Toutes les réceptions']+[a.name for a in ACCOUNTS])
            for i,account in enumerate(ACCOUNTS,1):
                combo.setItemIcon(i,icon('lock-keyhole' if account.secure else 'lock-keyhole-open',self.theme.colors['muted' if account.secure else 'warning']))
            combo.setCurrentIndex(0 if self.account_index is None else self.account_index+1)
            combo.currentIndexChanged.connect(lambda index:self.select_account(None if index == 0 else index-1))
            self.sidebar_layout.addWidget(combo)
        elif self.theme.variant == 2:
            for index,account in enumerate(ACCOUNTS):
                button = Button(f'{account.name}\n{account.address}',self.theme,'lock-keyhole' if account.secure else 'lock-keyhole-open','Nav')
                button.setCheckable(True)
                button.setChecked(index == self.account_index)
                button.clicked.connect(lambda checked=False,i=index:self.select_account(i))
                self.sidebar_layout.addWidget(button)
        else:
            accounts = QHBoxLayout()
            for index,account in enumerate(ACCOUNTS):
                button = Button(account.initials,self.theme,icon_name='shield-alert' if not account.secure else None,role='Nav',tooltip=account.name+' · '+account.address+(' · Sans chiffrement' if not account.secure else ''))
                button.setCheckable(True)
                button.setChecked(index == self.account_index)
                button.clicked.connect(lambda checked=False,i=index:self.select_account(i))
                accounts.addWidget(button)
            self.sidebar_layout.addLayout(accounts)
        unified = Button('Réception unifiée',self.theme,'inbox','Nav')
        unified.setCheckable(True)
        unified.setChecked(self.account_index is None)
        unified.clicked.connect(lambda:self.select_account(None))
        self.sidebar_layout.addWidget(unified)
        self.sidebar_layout.addSpacing(8)
        self.sidebar_layout.addWidget(label('DOSSIERS','Eyebrow'))
        for name,title in FOLDERS:
            count = sum((self.account_index is None or mail.account == self.account_index) and (mail.starred if title == 'Favoris' else mail.folder == title) for mail in self.mails)
            button = Button(f'{title}   {count if count else ""}',self.theme,name,'Nav')
            button.setCheckable(True)
            button.setChecked(self.folder == title)
            button.clicked.connect(lambda checked=False,f=title:self.select_folder(f))
            self.sidebar_layout.addWidget(button)
        self.sidebar_layout.addStretch()
        if self.theme.variant == 3:
            self.sidebar_layout.addWidget(label('J / K   parcourir\nE   archiver     S   étoiler','Small',True))
            self.sidebar_layout.addSpacing(10)
        account = ACCOUNTS[self.account_index] if self.account_index is not None else None
        if account and not account.secure:
            self.sidebar_layout.addWidget(Banner('Connexion en clair','Vérifiez les paramètres de ce compte.',self.theme,'Warning','lock-keyhole-open'))
        elif self.account_index is None:
            self.sidebar_layout.addWidget(label('2 comptes chiffrés\n1 compte à vérifier : Association','Small',True))
        else:
            secure = QHBoxLayout()
            secure.addWidget(IconLabel('lock-keyhole',self.theme))
            secure.addWidget(label('SSL/TLS · compte protégé','Small'))
            self.sidebar_layout.addLayout(secure)
        add = Button('Ajouter un compte',self.theme,'plus')
        add.clicked.connect(lambda:self.open_account())
        self.sidebar_layout.addWidget(add)
        self.sidebar_layout.addWidget(label('30 messages fictifs · 3 comptes','Small'))

    def appearance_changed(self):
        for combo,value in [(self.variant_combo,self.theme.variant-1),(self.density_combo,self.density_combo.findText(self.theme.density)),(self.accent_combo,self.accent_combo.findText(self.theme.accent_name))]:
            combo.blockSignals(True)
            combo.setCurrentIndex(value)
            combo.blockSignals(False)
        self.theme_button.setText('Clair' if self.theme.dark else 'Sombre')
        self.theme_button.icon_name = 'sun' if self.theme.dark else 'moon'
        self.theme_button.refresh()
        name,description = VARIANTS[self.theme.variant]
        self.eyebrow.setText(f'0{self.theme.variant} / {name.upper()}  ·  LUNDI 9 NOVEMBRE 2026')
        self.command_button.setText('Commandes  Ctrl+K' if self.theme.variant == 3 else 'Ctrl+K')
        self.search.setPlaceholderText('Trouver un message ou ouvrir Ctrl+K' if self.theme.variant == 3 else 'Rechercher un message…  Ctrl+F')
        margins = {1:22,2:34,3:26}[self.theme.variant]
        self.reader_layout.setContentsMargins(margins,16,margins,18)
        padding = {1:16,2:20,3:12}[self.theme.variant]
        self.header.box.setContentsMargins(16,padding,16,padding)
        self.build_sidebar()
        sizes = {1:[230,425,735],2:[270,420,700],3:[210,475,705]}[self.theme.variant]
        self.splitter.setSizes(sizes)
        self.populate()
        self.mail_list.doItemsLayout()
        self.mail_list.viewport().update()
        for shortcut in self.quick_shortcuts:
            shortcut.setEnabled(self.theme.variant == 3)

    def select_account(self, index):
        self.account_index = index
        self.folder = 'Réception'
        self.state = 'normal'
        self.search.clear()
        self.build_sidebar()
        self.populate()

    def select_folder(self, folder):
        self.folder = folder
        self.state = 'normal'
        self.search.clear()
        self.build_sidebar()
        self.populate()

    def set_filter(self, value):
        self.filter = value
        for button in self.filter_buttons:
            button.setChecked(button.text() == value)
        self.populate()

    def search_changed(self, text):
        self.state = 'normal'
        self.search_filters.setVisible(bool(text.strip()))
        self.populate()

    def populate(self, selected_id=None):
        if selected_id is None and self.current_mail:
            selected_id = self.current_mail.id
        self.mail_list.blockSignals(True)
        self.mail_list.clear()
        query = self.search.text().strip().casefold()
        rows = [mail for mail in self.mails if (self.account_index is None or mail.account == self.account_index)
                and (mail.starred if self.folder == 'Favoris' else mail.folder == self.folder)]
        if query:
            rows = [mail for mail in rows if query in (mail.sender+' '+mail.subject+' '+mail.preview+' '+mail.body).casefold()]
            if self.account_filter.currentIndex():
                rows = [mail for mail in rows if mail.account == self.account_filter.currentIndex()-1]
            if self.date_combo.currentIndex() == 1:
                rows = [mail for mail in rows if ':' in mail.time]
            elif self.date_combo.currentIndex() == 2:
                rows = [mail for mail in rows if mail.id < 24]
        if self.filter == 'Non lus':
            rows = [mail for mail in rows if mail.unread]
        elif self.filter == 'Pièces jointes':
            rows = [mail for mail in rows if mail.attachments]
        for mail in rows:
            item = QListWidgetItem(f'{mail.sender} · {mail.subject} · {mail.preview} · {mail.time}')
            item.setData(Qt.UserRole,mail)
            item.setToolTip(f'{mail.sender}\n{mail.subject}\n{ACCOUNTS[mail.account].name} · {mail.time}\n'+('Non lu' if mail.unread else 'Lu'))
            self.mail_list.addItem(item)
        self.mail_list.blockSignals(False)
        unread = sum(mail.unread for mail in rows)
        self.title.setText('Recherche' if query else 'Réception unifiée' if self.account_index is None and self.folder == 'Réception' else self.folder)
        self.subtitle.setText(f'« {self.search.text()} » · {len(rows)} résultat(s)' if query else f'{"Tous vos comptes" if self.account_index is None else ACCOUNTS[self.account_index].name}  ·  {len(rows)} messages  ·  {unread} non lus')
        self.count_label.setText(f'{len(rows)} messages')
        self.list_title.setText('Résultats' if query else 'Les plus récents')
        self.connection.setText('Mode hors connexion · cache de démonstration' if self.state in ('offline','cached_offline') else
                                '3 comptes · 1 connexion en clair à vérifier' if self.account_index is None else
                                'SSL/TLS · certificat vérifié' if ACCOUNTS[self.account_index].secure else 'Attention · connexion non chiffrée')
        self.offline_banner.setVisible(self.state in ('offline','cached_offline'))
        if self.state == 'loading':
            self.list_stack.setCurrentIndex(1)
            self.reader_stack.setCurrentIndex(2)
            self.current_mail = None
            return
        if self.state in ('empty','offline') or not rows:
            self.list_stack.setCurrentIndex(2)
            self.reader_stack.setCurrentIndex(3 if self.state == 'offline' else 1)
            self.empty_list.heading.setText('Aucune connexion' if self.state == 'offline' else 'Aucun résultat' if query else 'Aucun message')
            self.empty_list.description.setText('Le cache reste accessible.' if self.state == 'offline' else 'Essayez un autre terme ou retirez un filtre.' if query else 'Un peu de calme dans votre journée.')
            self.current_mail = None
            if self.state == 'empty':
                self.title.setText('Corbeille')
                self.subtitle.setText('Aucun message · votre espace est à jour')
            return
        self.list_stack.setCurrentIndex(0)
        index = next((i for i,mail in enumerate(rows) if mail.id == selected_id),0)
        self.mail_list.setCurrentRow(index)
        self.show_mail(rows[index], animate=False)

    def selected(self, current, previous):
        if current:
            self.show_mail(current.data(Qt.UserRole))

    def show_mail(self, mail, animate=True):
        self.current_mail = mail
        self.reader_stack.setCurrentIndex(0)
        self.message_subject.setText(mail.subject)
        self.sender_name.setText(mail.sender)
        self.sender_address.setText(mail.address)
        self.avatar.setText(''.join(word[0] for word in mail.sender.split()[:2]))
        self.message_date.setText(mail.time)
        account = ACCOUNTS[mail.account]
        self.recipient.setText(f'À moi · {account.address}   /   '+('Connexion chiffrée' if account.secure else 'Attention : compte non chiffré'))
        self.remote_banner.setVisible(mail.remote_images)
        self.remote_banner.action.setText('Afficher')
        self.remote_banner.action.setEnabled(True)
        self.moodboard.hide()
        self.danger_banner.setVisible(any(a.suspect for a in mail.attachments))
        self.mode_button.setText('Texte brut' if mail.html else 'HTML sécurisé')
        self.set_body(mail, mail.html)
        clear_layout(self.attachment_box)
        self.attachment_title.setVisible(bool(mail.attachments))
        for attachment in mail.attachments:
            card = Card('Attachment',7)
            row = QHBoxLayout()
            row.addWidget(IconLabel('shield-alert' if attachment.suspect else 'file-text',self.theme,'danger' if attachment.suspect else 'muted'))
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(label(attachment.name,'Bold'))
            text.addWidget(label(attachment.size+(' · Exécutable Windows' if attachment.suspect else ' · Pièce jointe'),'Small'))
            row.addLayout(text,1)
            save = Button('',self.theme,'download',tooltip='Enregistrer '+attachment.name+' (simulation)')
            save.clicked.connect(lambda checked=False,a=attachment:self.save_attachment(a))
            row.addWidget(save)
            card.box.addLayout(row)
            self.attachment_box.addWidget(card)
        if animate:
            fade(self.browser,self.theme)

    def set_body(self, mail, rich):
        colors = self.theme.colors
        style = f'body{{color:{colors["text"]};font-family:Segoe UI;font-size:14px;line-height:1.6}} p{{margin-bottom:17px}} h2{{font-size:24px;font-weight:600}} a{{color:{colors["accent"]}}}'
        if rich and mail.html:
            content = f'<p style="color:{colors["muted"]};font-size:11px">MAISON NACRE / LE CARNET DE NOVEMBRE</p><h2>Un atelier plus doux,<br>des idées qui durent.</h2><p>Bonjour Camille,</p><p>Ce mois-ci, nous vous proposons trois pistes pour réinventer votre espace de travail : moins d’objets, de belles matières et davantage de lumière.</p><table cellpadding="14" width="100%" bgcolor="{colors["soft"]}"><tr><td><b>01 / Le choix des matières</b><br>Du bois clair et des textiles naturels.</td></tr><tr><td><b>02 / Une lumière juste</b><br>Des zones calmes pour mieux se concentrer.</td></tr></table><p>À très bientôt,<br>L’équipe Maison Nacre</p><p style="color:{colors["muted"]};font-size:11px">Message HTML fictif · aucun lien ni contenu externe actif.</p>'
        else:
            content = ''.join('<p>'+html.escape(paragraph).replace('\n','<br>')+'</p>' for paragraph in mail.body.split('\n\n'))
        self.browser.setHtml(f'<html><head><style>{style}</style></head><body>{content}</body></html>')

    def toggle_body(self):
        if self.current_mail:
            rich = self.mode_button.text() == 'HTML sécurisé'
            self.mode_button.setText('Texte brut' if rich else 'HTML sécurisé')
            self.set_body(self.current_mail,rich)
            self.toast('Affichage de démonstration changé. Aucun contenu extérieur chargé.')

    def reveal_images(self):
        self.moodboard.show()
        self.remote_banner.action.setText('Aperçu local affiché')
        self.remote_banner.action.setEnabled(False)
        self.toast('Les images sont remplacées par une illustration locale. Toujours aucun accès réseau.')

    def save_attachment(self, attachment):
        if attachment.suspect:
            self.open_dialog(AttachmentDialog(self.theme,self))
        else:
            self.toast(f'Enregistrement simulé : {attachment.name}. Aucun fichier créé.')

    def more_menu(self):
        menu = QMenu(self)
        for title,callback in [('Marquer lu / non lu',lambda:self.message_action('read')),
                               ('Répondre à tous',lambda:self.open_compose('all')), ('Transférer',lambda:self.open_compose('forward')),
                               ('Exporter en .eml',lambda:self.toast('Export .eml simulé · aucun fichier créé.'))]:
            menu.addAction(title,callback)
        menu.exec(self.reader.mapToGlobal(self.reader.rect().topRight()))

    def move_menu(self):
        menu = QMenu(self)
        for _,folder in FOLDERS:
            if folder != 'Favoris':
                menu.addAction(folder,lambda f=folder:self.move_to(f))
        menu.exec(self.reader.mapToGlobal(self.reader.rect().topLeft()))

    def move_to(self, folder):
        if self.current_mail:
            self.current_mail.folder = folder
            self.toast('Déplacement simulé vers '+folder)
            self.build_sidebar()
            self.populate()

    def message_action(self, action):
        if not self.current_mail:
            return
        if action in ('archive','trash'):
            self.move_to('Archives' if action == 'archive' else 'Corbeille')
            return
        if action == 'star':
            self.current_mail.starred = not self.current_mail.starred
        elif action == 'read':
            self.current_mail.unread = not self.current_mail.unread
        self.toast('État du message modifié uniquement dans les données fictives.')
        self.build_sidebar()
        self.populate()

    def set_state(self, value):
        self.state = value
        self.populate()

    def simulate_sync(self):
        self.set_state('loading')
        later(self,800,lambda:(self.set_state('normal'),self.toast('Synchronisation simulée terminée. Aucun serveur contacté.')))

    def toast(self, text):
        self.toast_label.setText(text)

    def toggle_theme(self):
        self.theme.update(dark=not self.theme.dark)

    def cycle_density(self):
        values = ['Compacte','Normale','Aérée']
        self.theme.update(density=values[(values.index(self.theme.density)+1)%3])

    def setup_shortcuts(self):
        self.shortcuts = []
        self.quick_shortcuts = []
        actions = [('Ctrl+K',self.open_palette),('Ctrl+N',self.open_compose),('Ctrl+F',self.search.setFocus),
                   ('Ctrl+R',lambda:self.open_compose(True)),('Ctrl+Shift+R',lambda:self.open_compose('all')),
                   ('Ctrl+L',lambda:self.open_compose('forward')),('Ctrl+Shift+L',self.toggle_theme),
                   ('Ctrl+Shift+D',self.cycle_density),('F5',self.simulate_sync)]
        for key,callback in actions:
            shortcut = QShortcut(QKeySequence(key),self,activated=callback)
            self.shortcuts.append(shortcut)
        for variant in (1,2,3):
            self.shortcuts.append(QShortcut(QKeySequence(f'Alt+{variant}'),self,activated=lambda v=variant:self.theme.update(variant=v)))
        for key,callback in [('J',lambda:self.move_selection(1)),('K',lambda:self.move_selection(-1)),
                             ('E',lambda:self.message_action('archive')),('S',lambda:self.message_action('star'))]:
            shortcut = QShortcut(QKeySequence(key),self.mail_list)
            shortcut.setContext(Qt.WidgetShortcut)
            shortcut.activated.connect(lambda cb=callback: cb() if self.theme.variant == 3 else None)
            self.shortcuts.append(shortcut)
            self.quick_shortcuts.append(shortcut)
        delete = QShortcut(QKeySequence('Delete'),self.mail_list)
        delete.setContext(Qt.WidgetShortcut)
        delete.activated.connect(lambda:self.message_action('trash'))
        self.shortcuts.append(delete)

    def move_selection(self, delta):
        self.mail_list.setCurrentRow(max(0,min(self.mail_list.count()-1,self.mail_list.currentRow()+delta)))

    def open_dialog(self, dialog):
        self.last_dialog = dialog
        self.dialogs.append(dialog)
        dialog.open()
        return dialog

    def open_compose(self, reply=False):
        if reply and self.current_mail is None:
            self.toast('Sélectionnez un message fictif avant de répondre ou de transférer.')
            return None
        return self.open_dialog(ComposeDialog(self.theme,self,reply))

    def open_account(self, insecure=False):
        return self.open_dialog(AccountDialog(self.theme,self,insecure))

    def open_settings(self, page=0):
        return self.open_dialog(SettingsDialog(self.theme,self,page))

    def commands(self):
        return [('Nouveau message','Ctrl+N',self.open_compose),('Rechercher un message','Ctrl+F',self.search.setFocus),
                ('Répondre au message','Ctrl+R',lambda:self.open_compose(True)),('Archiver le message','E',lambda:self.message_action('archive')),
                ('Marquer lu / non lu','',lambda:self.message_action('read')),('Ajouter aux favoris','S',lambda:self.message_action('star')),
                ('Ouvrir la réception unifiée','',lambda:self.show_scene('unifiee')),('Paramètres : apparence','',self.open_settings),
                ('Ajouter un compte','',self.open_account),('Changer le thème','Ctrl+Maj+L',self.toggle_theme),
                ('Changer la densité','Ctrl+Maj+D',self.cycle_density),('Voir l’état hors connexion','',lambda:self.show_scene('sans_connexion')),
                ('Brouillons locaux','',lambda:self.select_folder('Brouillons')),('Envoyés locaux','',lambda:self.select_folder('Envoyés')),
                ('Exporter le message en .eml','',lambda:self.toast('Export simulé, aucun fichier créé.'))]

    def open_palette(self):
        return self.open_dialog(CommandPalette(self.theme,self.commands(),self))

    def show_scene(self, scene):
        self.state = 'normal'
        self.filter = 'Tous'
        self.account_index = None if scene in ('unifiee','recherche') else 0
        self.folder = 'Réception'
        self.search.blockSignals(True)
        self.search.setText('devis' if scene == 'recherche' else '')
        self.search.blockSignals(False)
        self.search_filters.setVisible(scene == 'recherche')
        self.account_filter.setCurrentIndex(0)
        self.date_combo.setCurrentIndex(0)
        for button in self.filter_buttons:
            button.setChecked(button.text() == 'Tous')
        if scene == 'vide':
            self.state = 'empty'
            self.folder = 'Corbeille'
        elif scene == 'sans_connexion':
            self.state = 'offline'
        elif scene == 'chargement':
            self.state = 'loading'
        self.build_sidebar()
        self.populate(selected_id={'html':1,'piece_suspecte':2,'recherche':3}.get(scene,0))
        if scene == 'redaction':
            return self.open_compose()
        if scene in ('ajout_compte','compte_non_chiffre'):
            return self.open_account(scene == 'compte_non_chiffre')
        if scene == 'certificat':
            return self.open_dialog(CertificateDialog(self.theme,self))
        if scene == 'alerte_piece_jointe':
            return self.open_dialog(AttachmentDialog(self.theme,self))
        if scene.startswith('parametres_'):
            page = ['apparence','comptes','securite','raccourcis'].index(scene.removeprefix('parametres_'))
            return self.open_settings(page)
        if scene == 'palette':
            return self.open_palette()
        return self

    def closeEvent(self,event):
        for dialog in self.dialogs:
            dialog.close()
        event.accept()
