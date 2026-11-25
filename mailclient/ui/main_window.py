"""Client multi-comptes : navigation, actions, cache et synchronisation Qt."""
from mailclient.i18n import tr, N_
from mailclient.ui.components import safe_rich
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QComboBox, QListWidget, QTableWidget, QTableWidgetItem, QSplitter, QHeaderView, QLabel,
    QLineEdit, QCheckBox, QToolBar, QInputDialog, QMessageBox, QSystemTrayIcon, QMenu,
    QStyle, QApplication, QFileDialog, QFrame, QScrollArea, QStackedWidget, QListWidgetItem, QButtonGroup,
    QAbstractItemView)
from PySide6.QtCore import Qt, QTimer, QSaveFile, QIODevice, QEvent, QItemSelectionModel
from PySide6.QtGui import QFont, QAction, QActionGroup, QShortcut, QKeySequence
from mailclient.ui.account_dialog import AccountDialog
from mailclient.ui.settings_dialog import SettingsDialog
from mailclient.ui.compose_window import ComposeWindow, reply_fields
from mailclient.ui.mail_view import MailView
from mailclient.core.sync import Runner, SyncThread, IdleThread, friendly_error
from mailclient.core.service import MailService
from mailclient.core.tls_policy import CertificateAlert
from mailclient.ui.presentation import install_theme
from mailclient.ui.components import Button, Card, label, MailDelegate, Skeleton, Banner, IconLabel, fade
from mailclient.ui.icons import icon
from mailclient.ui.theme import VARIANTS, ACCENTS
from mailclient.ui.view_models import MessageRow, MessageList, DRAG_MIME, date_group, count
count_words = count  # Nom sans ambiguïté là où « count » est une variable locale.
PRIVACY_URL = 'https://github.com/Smeth/smail/blob/main/PRIVACY.md'
SUPPORT_URL = 'https://github.com/Smeth/smail/issues'
from mailclient.core.threads import timestamp

from mailclient.ui.components import GROUP_ROLE, COLLAPSED_ROLE, GROUP_COUNT_ROLE, FILTERED_ROLE, ALWAYS_OPEN  # noqa: E402

class MainWindow(QMainWindow):
    def __init__(self, database, secrets, tls, auto_load=True):
        super().__init__()
        self.database, self.secrets = database, secrets
        self.service = MailService(database, secrets, tls)
        self.runner = Runner(self, tls)
        self.accounts, self.rows, self.folder_data = [], [], []
        self.page = self.total = 0
        # Chargement au défilement : self.page = dernière page de 50 chargée dans la liste.
        self.list_generation = self.auto_loads = 0
        self.loading_more = self.list_exhausted = self.list_all_folders = self.rendering = False
        self.busy = self.quitting = self.sync_requested = False
        self.sync_thread = None
        self.idle_threads = []
        self.composers = set()
        self.local_copy = None
        self.auto_load = auto_load
        self.thread_rows, self.thread_account, self.thread_index = [], None, -1
        self.message_windows, self.pending_window = set(), False
        self.setWindowTitle(tr('Smail — Client mail'))
        self.resize(1440, 900)
        self.setMinimumSize(1080,720)
        self.appearance = install_theme(database)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16,14,16,12)
        layout.setSpacing(12)
        self.style_box = QComboBox()
        self.style_box.setAccessibleName(tr('Style de l’interface'))
        for number,(name,_) in VARIANTS.items():
            self.style_box.addItem(f'{number} · {tr(name)}',number)
        self.style_box.setCurrentIndex(self.appearance.variant-1)
        self.style_box.currentIndexChanged.connect(self.change_style)
        self.theme_button = Button(tr('Clair / sombre'),self.appearance,'moon')
        self.theme_button.clicked.connect(self.toggle_theme)
        self.density_box = QComboBox()
        for density in ('Compacte','Normale','Aérée'):  # Valeur enregistrée en français, libellé traduit.
            self.density_box.addItem(tr(density), density)
        self.density_box.setAccessibleName(tr('Densité d’affichage'))
        self.density_box.setCurrentIndex(max(0, self.density_box.findData(self.appearance.density)))
        self.density_box.currentIndexChanged.connect(lambda index: self.change_density(self.density_box.itemData(index)))
        # Les menus Affichage et les raccourcis pilotent ces contrôles partagés.
        # Leur conteneur hors mise en page ne réserve aucune hauteur à l'écran.
        self.appearance_controls = QWidget(self)
        appearance_row = QHBoxLayout(self.appearance_controls)
        for widget in (self.style_box,self.theme_button,self.density_box):
            appearance_row.addWidget(widget)
        self.appearance_controls.hide()
        header = Card('Header',16)
        toolbar = QHBoxLayout()
        self.account_box = QComboBox()
        self.account_box.setMinimumWidth(170)
        self.account_box.setAccessibleName(tr('Compte actif'))
        self.add = Button(tr('Ajouter un compte'),self.appearance,'plus')
        self.refresh = Button(tr('Actualiser'),self.appearance,'refresh-cw')
        self.search = QLineEdit()
        self.search.setObjectName('Search')
        self.search.setPlaceholderText(tr('Rechercher'))
        from mailclient.core.search_query import HELP as SEARCH_HELP
        self.search.setToolTip(tr(SEARCH_HELP))
        self.search.setAccessibleName(tr('Rechercher dans le dossier, Entrée pour lancer'))
        self.heading = label(tr('Réception'),'Title')
        toolbar.addWidget(self.heading)
        toolbar.addWidget(self.search,1)
        # Filtres : un formulaire écrit les opérateurs (de:, objet:, a:pj…) à la place de l’utilisateur.
        self.filters_button = Button(tr('Filtres'),self.appearance,'filter',tooltip=tr('Filtres de recherche : expéditeur, objet, pièce jointe, dates…'))
        self.filters_button.clicked.connect(self.open_search_filters)
        toolbar.addWidget(self.filters_button)
        self.command_button = Button('',self.appearance,'command',tooltip=tr('Commandes (Ctrl+K)'))
        self.command_button.clicked.connect(self.open_palette)
        self.command_button.hide()  # Palette toujours accessible : Ctrl+K ou menu Affichage.
        toolbar.addWidget(self.refresh)
        self.settings_button = Button('',self.appearance,'settings-2',tooltip=tr('Paramètres'))
        self.settings_button.clicked.connect(lambda: self.preferences())
        toolbar.addWidget(self.settings_button)
        self.theme_button = Button('',self.appearance,'moon',tooltip=tr('Passer au thème sombre (Ctrl+Maj+L)'))
        self.theme_button.clicked.connect(lambda: self.toggle_theme())
        toolbar.addWidget(self.theme_button)
        self.offline = QCheckBox(tr('Hors ligne'))
        self.offline.setFocusPolicy(Qt.TabFocus)
        self.offline.setToolTip(tr('Travailler sur le cache local, sans aucune connexion au serveur'))
        self.offline.hide()  # Réglage rare : menu Outils › Travailler hors ligne ; l’état reste affiché par l’indicateur.
        self.connection = label('', 'Small')
        self.connection.setAccessibleName(tr('État de la connexion'))
        self.last_sync = None
        toolbar.addWidget(self.connection)
        header.box.addLayout(toolbar)
        layout.addWidget(header)
        self.security, self.cache_status = QLabel(), QLabel()
        self.cache_status.hide()  # Affichée seulement quand elle a quelque chose à dire.
        self.security.setWordWrap(True)
        self.security.setObjectName('SecurityStatus')
        self.cache_status.setObjectName('Small')
        self.security.setTextFormat(Qt.PlainText)
        self.security_frame = Card('Warning',10)
        security_row = QHBoxLayout()
        security_row.addWidget(IconLabel('lock-keyhole-open',self.appearance,'warning'))
        security_row.addWidget(self.security,1)
        self.security_frame.box.addLayout(security_row)
        self.security_frame.hide()
        layout.addWidget(self.security_frame)
        self.update_slot = QVBoxLayout()  # Bandeau « mise à jour prête », ajouté à la demande.
        self.update_slot.setContentsMargins(0,0,0,0)
        self.update_banner = None
        layout.addLayout(self.update_slot)
        layout.addWidget(self.cache_status)
        split = self.splitter = QSplitter()
        split.setChildrenCollapsible(False)
        self.sidebar = Card('Sidebar',14)
        zoom = getattr(self.appearance, 'text_scale', 1.0)  # Taille du texte de Windows : colonnes élargies d’autant.
        self.sidebar.setMinimumWidth(round(190 * zoom))
        self.sidebar.setMaximumWidth(round(285 * zoom))
        self.compose_button = Button(tr('Nouveau message'),self.appearance,'plus','Primary')
        self.compose_button.clicked.connect(lambda:self.compose())
        self.sidebar.box.addWidget(self.compose_button)
        self.sidebar.box.addWidget(label(tr('COMPTE'),'Eyebrow'))
        self.sidebar.box.addWidget(self.account_box)
        self.account_cards = QWidget()
        self.account_cards_box = QVBoxLayout(self.account_cards)
        self.account_cards_box.setContentsMargins(0,0,0,0)
        self.account_chips = QWidget()
        self.account_chips_box = QHBoxLayout(self.account_chips)
        self.account_chips_box.setContentsMargins(0,0,0,0)
        self.sidebar.box.addWidget(self.account_cards)
        self.sidebar.box.addWidget(self.account_chips)
        self.unified_button = Button(tr('Réception unifiée'),self.appearance,'inbox','Nav')
        self.unified_button.setCheckable(True)
        self.unified_button.clicked.connect(self.show_unified)
        self.sidebar.box.addWidget(self.unified_button)
        self.sidebar.box.addWidget(label(tr('DOSSIERS'),'Eyebrow'))
        self.folders = QListWidget()
        self.folders.setObjectName('SettingsNav')
        from mailclient.ui.folder_list import FolderDelegate
        self.folder_delegate = FolderDelegate(self.appearance, self.folders)
        self.folders.setItemDelegate(self.folder_delegate)
        self.folders.setAccessibleName(tr('Dossiers du compte'))
        self.sidebar.box.addWidget(self.folders,1)
        self.shortcut_hint = label(tr('J / K  parcourir\nE  archiver   S  suivre'),'Small')
        self.sidebar.box.addWidget(self.shortcut_hint)
        self.sidebar.box.addWidget(self.add)
        self.list_panel = Card('ListPanel',8)
        self.list_panel.setMinimumWidth(round(290 * getattr(self.appearance, 'text_scale', 1.0)))
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.page_filter = 'Tous'
        filter_row = QHBoxLayout()
        self.filter_buttons = {}
        for title in (N_('Tous'),N_('Non lus'),N_('Pièces jointes')):
            button = Button(tr(title),self.appearance,role='Nav')  # Valeur du filtre : title (français).
            button.setCheckable(True)
            button.setChecked(title == 'Tous')
            button.clicked.connect(lambda checked=False,value=title:self.user_filter(value))
            self.filter_group.addButton(button)
            filter_row.addWidget(button)
            self.filter_buttons[title] = button
        self.filter_bar = QWidget()
        filter_row.setContentsMargins(0,0,0,0)
        self.filter_bar.setLayout(filter_row)
        self.list_panel.box.addWidget(self.filter_bar)
        # Sélection multiple : nombre de messages cochés et actions groupées (remplace les filtres).
        self.selection_bar = QWidget()
        selection_row = QHBoxLayout(self.selection_bar)
        selection_row.setContentsMargins(0,0,0,0)
        selection_row.setSpacing(2)
        self.selection_count = label('', 'Bold')
        selection_row.addWidget(self.selection_count)
        selection_row.addStretch()
        self.selection_buttons = []
        for icon_name, text, slot in (('check', N_('Tout sélectionner'), self.select_all_messages),
                                      ('mail', N_('Marquer comme lu / non lu'), self.toggle_read),
                                      ('archive', N_('Archiver'), lambda: self.move('archive')),
                                      ('folder', N_('Déplacer…'), lambda: self.move('move')),
                                      ('trash-2', N_('Supprimer'), lambda: self.move('trash')),
                                      ('x', N_('Annuler la sélection'), self.clear_selection)):
            button = Button('', self.appearance, icon_name, tooltip=tr(text))
            button.setFixedSize(32, 32)
            button.clicked.connect(lambda checked=False, s=slot: s())
            selection_row.addWidget(button)
            self.selection_buttons.append(button)
        self.selection_bar.hide()
        self.list_panel.box.addWidget(self.selection_bar)
        self.search_filters = QWidget()
        search_filters = QHBoxLayout(self.search_filters)
        search_filters.setContentsMargins(0,0,0,0)
        self.result_scope = QComboBox()
        self.result_scope.addItems([tr('Ce dossier'),tr('Tous les dossiers')])
        self.result_scope.setAccessibleName(tr('Portée de la recherche'))
        self.result_scope.setToolTip(tr('« Tous les dossiers » : les 100 résultats les plus récents du compte.'))
        self.result_scope.currentIndexChanged.connect(lambda index:self.new_search() if self.search.text().strip() else None)
        search_filters.addWidget(self.result_scope,1)
        self.result_account = QComboBox()
        self.result_account.addItem(tr('Tous les comptes'),None)
        self.result_account.setAccessibleName(tr('Filtrer la page par compte'))
        self.result_date = QComboBox()
        self.result_date.addItems([tr('Toutes les dates'),tr('Aujourd’hui'),tr('7 derniers jours')])
        self.result_date.setAccessibleName(tr('Filtrer la page par date'))
        for widget in (self.result_account,self.result_date):
            widget.setToolTip(tr('Filtre limité aux messages déjà chargés dans la liste.'))
            widget.currentIndexChanged.connect(lambda index:self.user_filter(self.page_filter))
            search_filters.addWidget(widget,1)
        self.list_panel.box.addWidget(self.search_filters)
        # Dossier Brouillons : les brouillons enregistrés sur ce PC (pas encore sur le serveur) y sont signalés.
        self.local_drafts_button = Button('',self.appearance,'file-pen-line','Secondary',tr('Brouillons enregistrés sur ce PC'))
        self.local_drafts_button.clicked.connect(self.open_draft)
        self.local_drafts_button.hide()
        self.list_panel.box.addWidget(self.local_drafts_button)
        self.search_filters.hide()
        self.search.textChanged.connect(lambda text:self.search_filters.setVisible(bool(text.strip())))
        self.table = MessageList()
        self.table.setAccessibleName(tr('Messages, flèches pour parcourir, Entrée pour lire'))
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setMouseTracking(True)
        self.table.setItemDelegate(MailDelegate(self.appearance,self.table))
        self.table.itemDelegate().on_action = self.row_action  # Archiver / supprimer / lu au survol d’une ligne.
        self.table.header_clicked = self.toggle_group  # Titres de groupes de dates repliables.
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.table)
        self.list_stack.addWidget(Skeleton(self.appearance))
        empty = Card(margin=18)
        empty.box.addStretch()
        self.empty_title = label(tr('Aucun message'),'MessageTitle',True)
        self.empty_description = label(tr('Choisissez un dossier ou ajoutez un compte.'),'Subtitle',True)
        empty.box.addWidget(self.empty_title)
        empty.box.addWidget(self.empty_description)
        empty.box.addStretch()
        self.list_stack.addWidget(empty)
        self.list_panel.box.addWidget(self.list_stack,1)
        # Pas de pagination : les messages plus anciens se chargent en arrivant en bas de la liste.
        self.page_label = label(tr('Aucun message'),'Subtitle')
        self.page_label.setAccessibleName(tr('État de la liste des messages'))
        self.list_panel.box.addWidget(self.page_label)
        self.reader = MailView()
        for widget in (self.sidebar, self.list_panel, self.reader):
            split.addWidget(widget)
        split.setSizes([230,430,740])
        layout.addWidget(split, 1)
        self.setCentralWidget(root)
        from mailclient.ui.toast import Toast
        self.toast = Toast(root, lambda: self.appearance.colors)
        self.menuBar().setNativeMenuBar(False)
        file_menu = self.menuBar().addMenu(tr('Fichier'))
        actions = self.message_menu = self.menuBar().addMenu(tr('Message'))
        folder_menu = self.menuBar().addMenu(tr('Dossier'))
        view_menu = self.menuBar().addMenu(tr('Affichage'))
        accounts_menu = self.menuBar().addMenu(tr('Comptes'))
        tools_menu = self.menuBar().addMenu(tr('Outils'))
        help_menu = self.menuBar().addMenu(tr('Aide'))
        self.message_actions = []
        self.command_actions = []
        self.menu_icons = []
        def action(label, slot, shortcut=None, needs_message=False, menu=None, icon_name=None):
            item = QAction(label, self)
            item.triggered.connect(lambda checked=False: slot())
            if shortcut:
                if shortcut == 'Delete':
                    key = QShortcut(QKeySequence(shortcut),self.table)
                    key.setContext(Qt.WidgetShortcut)
                    key.activated.connect(lambda:item.trigger() if item.isEnabled() else None)
                    item.setShortcut(QKeySequence(shortcut))  # Affiché dans le menu ; actif depuis la liste.
                    item.setShortcutContext(Qt.WidgetShortcut)
                else:
                    item.setShortcut(shortcut)
            (menu or actions).addAction(item)
            if icon_name:
                self.menu_icons.append((item,icon_name))
            self.command_actions.append(item)
            if needs_message:
                self.message_actions.append(item)
            return item
        # Fichier : créer, retrouver ce qui est enregistré sur ce PC, quitter.
        action(tr('Nouveau message'), self.compose, 'Ctrl+N', menu=file_menu, icon_name='plus')
        file_menu.addSeparator()
        action(tr('Brouillons enregistrés sur ce PC…'), self.open_draft, menu=file_menu, icon_name='file-pen-line')
        action(tr('Copies envoyées sur ce PC…'), self.open_sent_copy, menu=file_menu, icon_name='send')
        action(tr('Enregistrer le message (.eml)…'), self.export_sent_copy, menu=file_menu, icon_name='download')
        action(tr('Boîte d’envoi…'), self.open_outbox, menu=file_menu, icon_name='clock')
        file_menu.addSeparator()
        action(tr('Sauvegarder les comptes et réglages…'), self.backup_data, menu=file_menu, icon_name='download')
        action(tr('Restaurer une sauvegarde…'), self.restore_data, menu=file_menu, icon_name='refresh-cw')
        file_menu.addSeparator()
        action(tr('Quitter'), self.request_quit, 'Ctrl+Q', menu=file_menu)
        # Message : répondre, état, rangement, indésirables. Le menu clic droit reprend exactement ce menu.
        # Répondre, transférer et l’original exigent un seul message ; les autres actions acceptent une sélection.
        self.single_actions = [
            action(tr('Répondre'), lambda: self.compose('reply'), 'Ctrl+R', True, icon_name='reply'),
            action(tr('Répondre à tous'), lambda: self.compose('reply_all'), 'Ctrl+Shift+R', True, icon_name='reply-all'),
            action(tr('Transférer'), lambda: self.compose('forward'), 'Ctrl+L', True, icon_name='forward'),
            action(tr('Transférer en pièce jointe'), lambda: self.compose('forward_attachment'), needs_message=True, icon_name='paperclip'),
            action(tr('Ouvrir dans une fenêtre'), self.open_in_window, 'Ctrl+O', True, icon_name='layout-panel-left'),
            action(tr('Imprimer…'), self.reader.print_message, 'Ctrl+P', True, icon_name='file-text')]
        self.edit_draft_action = action(tr('Modifier le brouillon'), self.edit_server_draft, needs_message=True, icon_name='file-pen-line')
        self.single_actions.append(self.edit_draft_action)
        actions.addSeparator()
        action(tr('Tout sélectionner'), self.select_all_messages, menu=actions, icon_name='check')
        action(tr('Marquer comme lu / non lu'), self.toggle_read, 'Ctrl+U', True, icon_name='mail')
        action(tr('Suivre / ne plus suivre'), self.toggle_star, 'Ctrl+Shift+G', True, icon_name='star')
        actions.addSeparator()
        action(tr('Déplacer…'), lambda: self.move('move'), 'Ctrl+Shift+V', True, icon_name='folder')
        action(tr('Archiver'), lambda: self.move('archive'), needs_message=True, icon_name='archive')
        action(tr('Reporter…'), self.snooze, 'Ctrl+Shift+Z', True, icon_name='alarm-clock')
        action(tr('Supprimer'), lambda: self.move('trash'), 'Delete', True, icon_name='trash-2')
        actions.addSeparator()
        junk_menu = actions.addMenu(tr('Courrier indésirable'))
        action(tr('Signaler comme spam'), lambda: self.report_junk(), 'Ctrl+Shift+J', True, menu=junk_menu, icon_name='shield-alert')
        action(tr('Bloquer l’expéditeur'), lambda: self.report_junk(block=True), needs_message=True, menu=junk_menu, icon_name='ban')
        self.not_junk_action = action(tr('Ce n’est pas un spam'), lambda: self.report_junk(trust=True), needs_message=True, menu=junk_menu, icon_name='shield-check')
        action(tr('Créer une règle à partir du message…'), self.create_rule_from_message, needs_message=True, icon_name='filter')
        self.single_actions.append(action(tr('Afficher l’original (en-têtes)…'), self.show_original, needs_message=True, icon_name='file-text'))
        # Dossier : tout ce qui concerne le dossier affiché.
        self.folder_actions = {
            'create': action(tr('Nouveau dossier…'), lambda: self.manage_folder('create'), menu=folder_menu, icon_name='folder'),
            'rename': action(tr('Renommer le dossier…'), lambda: self.manage_folder('rename'), menu=folder_menu, icon_name='file-pen-line'),
            'delete': action(tr('Supprimer le dossier…'), lambda: self.manage_folder('delete'), menu=folder_menu, icon_name='trash-2'),
            'empty': action(tr('Vider le dossier…'), self.empty_folder, menu=folder_menu, icon_name='trash-2')}
        folder_menu.addSeparator()
        self.mark_all_action = action(tr('Tout marquer comme lu'), self.mark_all_read, 'Ctrl+Shift+U', menu=folder_menu, icon_name='check')
        # Comptes : ajouter, et une seule page pour les paramètres et la suppression.
        action(tr('Ajouter un compte…'), self.add_account, menu=accounts_menu, icon_name='plus')
        action(tr('Gérer les comptes…'), lambda: self.preferences('Comptes'), menu=accounts_menu, icon_name='settings-2')
        # Outils : actualiser, mode hors ligne, réglages.
        action(tr('Actualiser'), self.refresh_all, 'F5', menu=tools_menu, icon_name='refresh-cw')
        self.offline_action = action(tr('Travailler hors ligne'), self.offline.click, menu=tools_menu)
        self.offline_action.setCheckable(True)
        self.offline.toggled.connect(self.offline_action.setChecked)
        tools_menu.addSeparator()
        action(tr('Préférences…'), self.preferences, 'Ctrl+,', menu=tools_menu, icon_name='settings-2')
        action(tr('Rechercher des mises à jour…'), lambda: self.updates.check(manual=True), menu=tools_menu, icon_name='download')
        action(tr('Raccourcis clavier'), lambda: self.preferences('Raccourcis'), menu=help_menu, icon_name='command')
        action(tr('Politique de confidentialité'), lambda: self.open_link(PRIVACY_URL), menu=help_menu, icon_name='shield-check')
        action(tr('Signaler un problème ou poser une question'), lambda: self.open_link(SUPPORT_URL), menu=help_menu, icon_name='arrow-up-right')
        help_menu.addSeparator()
        action(tr('À propos de Smail'), self.about, menu=help_menu, icon_name='circle-help')
        action(tr('Rechercher'), self.search.setFocus, 'Ctrl+F', menu=view_menu, icon_name='search')
        action(tr('Palette de commandes'), self.open_palette, 'Ctrl+K', menu=view_menu, icon_name='command')
        view_menu.addSeparator()
        self.conversation_action = QAction(tr('Regrouper par conversation'), self)
        self.conversation_action.setCheckable(True)
        self.conversation_action.setChecked(self.conversations_enabled())
        self.conversation_action.setShortcut('Ctrl+Shift+T')
        self.conversation_action.toggled.connect(self.toggle_conversations)
        view_menu.addAction(self.conversation_action)
        self.command_actions.append(self.conversation_action)
        self.dark_action = action(tr('Passer au thème sombre'), self.toggle_theme, 'Ctrl+Shift+L', menu=view_menu, icon_name='moon')
        self.style_actions = {}
        style_menu = view_menu.addMenu(tr('Style de l’interface'))
        style_group = QActionGroup(self)
        style_group.setExclusive(True)
        for number,(name,_) in VARIANTS.items():
            item = action(tr(name),lambda value=number:self.style_box.setCurrentIndex(value-1),menu=style_menu)
            item.setCheckable(True)
            style_group.addAction(item)
            self.style_actions[number] = item
        self.density_actions = {}
        density_menu = view_menu.addMenu(tr('Densité'))
        density_group = QActionGroup(self)
        density_group.setExclusive(True)
        for name in ('Compacte','Normale','Aérée'):
            item = action(tr(name),lambda value=name:self.density_box.setCurrentIndex(self.density_box.findData(value)),menu=density_menu)
            item.setCheckable(True)
            density_group.addAction(item)
            self.density_actions[name] = item
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_message_menu)
        self.folders.setContextMenuPolicy(Qt.CustomContextMenu)
        # Les messages glissés depuis la liste se déposent sur un dossier.
        self.folders.viewport().setAcceptDrops(True)
        self.folders.viewport().installEventFilter(self)
        self.folders.customContextMenuRequested.connect(self.show_folder_menu)
        self.add.clicked.connect(self.add_account)
        self.refresh.clicked.connect(self.refresh_all)
        self.account_box.currentIndexChanged.connect(self.load_folders)
        self.folders.currentRowChanged.connect(self.folder_changed)
        self.table.verticalScrollBar().valueChanged.connect(lambda value: self.maybe_load_more())
        self.table.verticalScrollBar().rangeChanged.connect(lambda low, high: self.maybe_load_more(auto=True))
        self.search.returnPressed.connect(self.new_search)
        self.offline.toggled.connect(self.offline_changed)
        self.table.itemSelectionChanged.connect(self.read_selected)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.table.itemSelectionChanged.connect(self.update_selection_bar)
        self.table.itemActivated.connect(lambda item:self.reader.tabs.setFocus())
        self.table.itemDoubleClicked.connect(lambda item:self.open_in_window())
        QShortcut(QKeySequence('Ctrl+Shift+D'),self,activated=lambda:self.density_box.setCurrentIndex((self.density_box.currentIndex()+1)%3))
        self.quick_keys = []
        for key,callback in [('J',lambda:self.move_selection(1)),('K',lambda:self.move_selection(-1)),
                             ('E',lambda:self.move('archive')),('S',self.toggle_star)]:
            shortcut = QShortcut(QKeySequence(key),self.table)
            shortcut.setContext(Qt.WidgetShortcut)
            shortcut.activated.connect(callback)
            self.quick_keys.append(shortcut)
        self.reader.replyRequested.connect(lambda:self.trigger_command('Répondre'))
        self.reader.replyAllRequested.connect(lambda:self.trigger_command('Répondre à tous'))
        self.reader.forwardRequested.connect(lambda:self.trigger_command('Transférer'))
        self.reader.archiveRequested.connect(lambda:self.trigger_command('Archiver'))
        self.reader.deleteRequested.connect(lambda:self.trigger_command('Supprimer'))
        self.reader.starRequested.connect(lambda:self.trigger_command('Suivre / ne plus suivre'))
        self.reader.readRequested.connect(lambda:self.trigger_command('Marquer comme lu / non lu'))
        self.reader.threadMessageRequested.connect(self.open_thread_message)
        self.reader.unsubscribeRequested.connect(self.unsubscribe)
        self.reader.inviteAnswered.connect(self.answer_invite)
        self.reader.inviteImportRequested.connect(self.import_invite)
        # Parcours de la conversation au clavier, sans quitter la liste.
        QShortcut(QKeySequence('Alt+Down'),self,activated=lambda:self.step_thread(1))
        QShortcut(QKeySequence('Alt+Up'),self,activated=lambda:self.step_thread(-1))
        self.appearance.changed.connect(self.refresh_appearance)
        self.refresh_appearance()  # Libellé « Passer au thème clair / sombre » juste dès l’ouverture.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync_now)
        # Échéances locales : envois programmés et retours de messages reportés (Smail ouvert).
        self.due_timer = QTimer(self)
        self.due_timer.setInterval(30_000)
        self.due_timer.timeout.connect(self.process_due)
        self.due_running = False
        self.idle_debounce = QTimer(self)
        self.idle_debounce.setSingleShot(True)
        self.idle_debounce.setInterval(2000)
        self.idle_debounce.timeout.connect(self.sync_now)
        self.tray = None
        if auto_load and QApplication.platformName() != 'offscreen' and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QApplication.windowIcon() if not QApplication.windowIcon().isNull() else self.style().standardIcon(QStyle.SP_MessageBoxInformation), self)
            self.tray.setToolTip(tr('Smail'))
            menu = QMenu(self)
            menu.addAction(tr('Ouvrir Smail'), self.show_normal)
            menu.addAction(tr('Actualiser'), self.refresh_all)
            menu.addAction(tr('Quitter'), self.request_quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.show_normal() if reason == QSystemTrayIcon.DoubleClick else None)
            self.tray.show()
            QApplication.instance().setQuitOnLastWindowClosed(False)
        self.apply_theme()
        from pathlib import Path
        from mailclient.ui.updates import UpdateManager
        self.updates = UpdateManager(self, database, self.runner, Path(database.path).parent)
        self.update_connection()
        from mailclient.ui.send_queue import SendQueue
        self.send_queue = SendQueue(self, self.service, database)
        if auto_load:
            self.updates.start()
            from mailclient.core import scheduler
            uncertain = scheduler.recover(database)
            self.reload_accounts()
            self.start_background()
            if uncertain:
                self.statusBar().showMessage(tr('{uncertain} envoi(s) programmé(s) interrompu(s) : voir Fichier › Boîte d’envoi.').format(uncertain=uncertain))
            QTimer.singleShot(1500, self.sync_now)
            QTimer.singleShot(45_000, self, self.remind_backup)  # Rappel mensuel, une fois la synchronisation lancée.
            if not self.accounts:  # Premier lancement : l’assistant d’ajout de compte s’ouvre de lui-même.
                QTimer.singleShot(600, self, self.add_account)
        else:
            self.set_busy(False)

    def show_normal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def external_request(self, payload):
        """Demande d’un second lancement de Smail (raccourci, lien mailto:) : Smail revient au premier plan."""
        self.show_normal()
        if isinstance(payload.get('mailto'), str):
            self.open_mailto(payload['mailto'])

    def open_mailto(self, url):
        """Lien mailto: (navigateur, document) : nouveau message prérempli, jamais envoyé sans vous."""
        from mailclient.core.mailto import parse
        try:
            fields = parse(url)
        except ValueError:
            self.notify(tr('Lien de messagerie invalide.'), kind='error')
            return
        if not self.accounts:
            self.notify(tr('Ajoutez d’abord un compte pour écrire ce message.'), kind='error')
            return
        account = self.account() or self.accounts[0]
        window = ComposeWindow(self.service, self.accounts, account, fields, parent=self, offline=self.offline.isChecked)
        self.composers.add(window)
        window.show()
        window.raise_()

    def show_message_menu(self, position):
        item = self.table.itemAt(position)
        if item is None or self.busy:
            return
        if not item.isSelected():
            self.table.setCurrentItem(item)
        self.update_actions()
        menu = QMenu(self.table)
        menu.addActions(self.message_menu.actions())  # Même contenu et mêmes groupes que le menu Message.
        menu.exec(self.table.viewport().mapToGlobal(position))
        menu.deleteLater()

    def show_folder_menu(self, position):
        if self.busy:
            return
        item = self.folders.itemAt(position)
        if item is not None and item is not self.folders.currentItem():
            self.folders.setCurrentItem(item)
        self.update_actions()
        menu = QMenu(self.folders)
        menu.addAction(self.mark_all_action)
        menu.addSeparator()
        for action in self.folder_actions.values():
            menu.addAction(action)
        menu.exec(self.folders.viewport().mapToGlobal(position))
        menu.deleteLater()

    PROTECTED = ('Boîte de réception','Envoyés','Brouillons','Corbeille','Spam')
    SPECIAL_WORDS = {'trash': ('corbeille', 'trash', 'deleted'), 'archive': ('archive', 'all mail', 'tous les messages'),
                     'junk': ('spam', 'junk', 'indésirable'), 'drafts': ('brouillon', 'draft')}

    def current_folder(self):
        """(nom IMAP, libellé) du dossier courant d’un compte ; None en réception unifiée."""
        index = self.folders.currentRow()
        if self.account() is None or not 0 <= index < len(self.folder_data):
            return None
        return self.folder_data[index]

    def is_special(self, name, label, kind):
        return any(word in (name+' '+label).casefold() for word in self.SPECIAL_WORDS[kind])

    def special_folder(self, folders, kind, exclude=''):
        return next((name for name,label in folders if name != exclude and self.is_special(name,label,kind)), None)

    def run_and_reload(self, operation, message, reload_folders=False):
        self.set_busy(True)
        def done(result):
            self.set_busy(False)
            self.notify(message(result) if callable(message) else message)
            self.load_folders() if reload_folders else self.load_messages()
        self.runner.run(operation, done, self.failure)

    def report_junk(self, block=False, trust=False):
        """Signaler comme spam, bloquer l’expéditeur, ou « Ce n’est pas un spam » (retour en réception, expéditeur approuvé)."""
        rows = self.selected_rows()
        if self.busy or not rows:
            return
        if self.offline.isChecked():
            self.statusBar().showMessage(tr('Reconnectez-vous pour déplacer ces messages.'))
            return
        from email.utils import getaddresses
        senders = sorted({address for row in rows for _, address in getaddresses([row.get('sender', '')]) if address})
        if block and QMessageBox.question(
                self, tr('Bloquer l’expéditeur'), safe_rich(tr('Bloquer ') + ', '.join(senders[:5]) + ('…' if len(senders) > 5 else '') +
                tr(' ?\n\nLes messages sélectionnés et les prochains de ces expéditeurs iront dans les indésirables.'
                ' La liste se gère dans Préférences › Règles et indésirables.')),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        groups = {}
        for row in rows:
            groups.setdefault(row['account'], []).append(row)
        plan = [(self.row_account(group[0]), group) for group in groups.values()]
        if any(account is None for account, _ in plan):
            self.statusBar().showMessage(tr('Le compte de ce message n’existe plus. Actualisez.'))
            return
        def operation():
            for account, group in plan:
                folders = self.database.cache_get('folders', account.id, []) or self.service.folders(account)[0]
                self.service.junk(account, group, folders, block=block, trust=trust)
        message = (tr('Expéditeur approuvé, message remis dans la réception.') if trust else
                   tr('Expéditeur bloqué, messages déplacés vers les indésirables.') if block else
                   tr('Message déplacé vers les indésirables.') if len(rows) == 1 else
                   tr('{count} messages déplacés vers les indésirables.').format(count=len(rows)))
        self.run_and_reload(operation, message)

    def create_rule_from_message(self):
        rows = self.selected_rows()
        if self.busy or not rows:
            return
        from email.utils import parseaddr
        from mailclient.core import filters
        from mailclient.ui.rules_dialog import RuleDialog
        row = rows[0]
        address = parseaddr(row.get('sender', ''))[1]
        dialog = RuleDialog(self.database, self.accounts, dict(account=row['account'], field='from', op='contains', value=address), self)
        if not dialog.exec():
            return
        data = filters.load(self.database)
        data['rules'].append(dialog.rule)
        filters.save(self.database, data)
        if QMessageBox.question(self, tr('Règle enregistrée'), tr('Règle enregistrée. L’appliquer aussi aux messages déjà présents dans la réception ?'),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.apply_filters_now()
        else:
            self.statusBar().showMessage(tr('Règle enregistrée : elle s’appliquera aux nouveaux messages.'))

    def apply_filters_now(self):
        if self.busy or not self.accounts:
            return
        if self.offline.isChecked():
            self.statusBar().showMessage(tr('Reconnectez-vous pour appliquer les règles.'))
            return
        accounts = list(self.accounts)
        self.run_and_reload(lambda: sum(self.service.apply_filters_now(account) for account in accounts),
                            lambda n: tr('Règles appliquées : {valeur}.').format(valeur=count(n, "message traité", "messages traités")))

    def answer_invite(self, partstat):
        """Réponse à une invitation : e-mail iTIP (METHOD:REPLY) à l’organisateur, après confirmation."""
        from mailclient.core import invite as invites, scheduler
        invite, account = self.reader.invite, self.displayed_account()
        if self.busy or invite is None or account is None or not invite.answerable:
            return
        if self.offline.isChecked():
            self.statusBar().showMessage(tr('Reconnectez-vous pour répondre à cette invitation.'))
            return
        label_text = invites.PARTSTAT[partstat]
        if QMessageBox.question(self, tr('Répondre à l’invitation'),
                                tr('Envoyer la réponse « {label_text} » à {organizer} depuis {email} ?').format(label_text=label_text, organizer=invite.organizer, email=account.email),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        state = invites.response_state(invite, account, partstat)
        def operation():
            raw, refused, local_id = scheduler.send_and_record(self.service, account, state, [])
            if refused:
                raise RuntimeError(tr('L’organisateur a été refusé par le serveur d’envoi.'))
            try:
                scheduler.copy_to_sent(self.service, account, raw, local_id)
            except Exception:
                pass  # Réponse envoyée : la copie dans Envoyés est accessoire.
        def done(_):
            self.set_busy(False)
            self.reader.invite_answered(label_text)
            self.statusBar().showMessage(tr('Réponse « {label_text} » envoyée à {organizer}.').format(label_text=label_text, organizer=invite.organizer))
        self.set_busy(True)
        self.runner.run(operation, done, self.failure)

    def import_invite(self):
        """Ouvre l’invitation dans l’application de calendrier associée aux fichiers .ics."""
        attachment = getattr(self.reader, 'invite_attachment', None)
        if attachment is None:
            return
        import tempfile
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        handle = tempfile.NamedTemporaryFile('wb', suffix='.ics', prefix='invitation-', delete=False)
        with handle:
            handle.write(attachment.data)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(handle.name)):
            self.statusBar().showMessage(tr('Aucune application de calendrier n’est associée aux fichiers .ics sur ce PC.'))

    def unsubscribe(self):
        """Désabonnement d’une liste : un clic (RFC 8058), sinon e-mail, sinon page web — toujours après confirmation."""
        from mailclient.core import unsubscribe
        mail = self.reader.mail
        row = self.thread_rows[self.thread_index] if 0 <= self.thread_index < len(self.thread_rows) else self.selected_row()
        account = self.thread_account if self.thread_rows else (self.row_account(row) if row else None)
        if self.busy or mail is None or account is None:
            return
        options = unsubscribe.options(mail.list_unsubscribe, mail.list_unsubscribe_post)
        if not options:
            return
        if options.one_click:
            how = tr('Smail enverra une demande de désabonnement automatique à {host}, sans ouvrir de navigateur.').format(host=options.host)
        elif options.mailto:
            how = tr('Smail enverra depuis {email} un e-mail de désabonnement à {valeur}.').format(email=account.email, valeur=options.mailto[0])
        else:
            how = tr('La page de désabonnement de {host} s’ouvrira dans votre navigateur.').format(host=options.host)
        if QMessageBox.question(self, tr('Se désabonner'), safe_rich(tr('{how}\n\nContinuer ?').format(how=how)), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if not options.one_click and not options.mailto:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(options.web))
            return
        if self.offline.isChecked():
            self.statusBar().showMessage(tr('Reconnectez-vous pour vous désabonner.'))
            return
        def operation():
            if options.one_click:
                unsubscribe.one_click(options.one_click)
                return
            from mailclient.core.smtp_client import build_message, send_message
            address, subject, body = options.mailto
            message, recipients = build_message(account, address, '', '', subject, body or 'unsubscribe')
            send_message(account, self.service.oauth.credential(account, 'smtp'), self.service.tls, message, recipients)
        def done(_):
            self.set_busy(False)
            self.reader.unsubscribe_banner.hide()
            self.statusBar().showMessage(tr('Demande de désabonnement envoyée ({host}). Certaines listes mettent quelques jours à l’appliquer.').format(host=options.host))
        self.set_busy(True)
        self.runner.run(operation, done, self.failure)

    def mark_all_read(self):
        if self.busy:
            return
        if self.offline.isChecked():
            self.statusBar().showMessage(tr('Reconnectez-vous pour modifier les messages du serveur.'))
            return
        current = self.current_folder()
        if current:
            targets = [(self.account(), current[0])]
        elif self.account() is None and self.accounts:
            targets = []
            for account in self.accounts:
                folders = self.database.cache_get('folders', account.id, [])
                targets.append((account, next((name for name,_ in folders if name.upper() == 'INBOX'), 'INBOX')))
        else:
            return
        def operation():
            return sum(self.service.mark_all_read(account, folder) for account,folder in targets)
        self.run_and_reload(operation, lambda n: tr('{valeur} comme lu{valeur2}.').format(valeur=count(n, "message marqué", "messages marqués"), valeur2="s" if n > 1 else ""))

    def empty_folder(self):
        current = self.current_folder()
        if self.busy or not current:
            return
        name, label = current
        if not (self.is_special(name,label,'trash') or self.is_special(name,label,'junk')):
            self.statusBar().showMessage(tr('Seuls la corbeille et le dossier spam peuvent être vidés.'))
            return
        if self.offline.isChecked():
            self.statusBar().showMessage(tr('Reconnectez-vous pour vider ce dossier.'))
            return
        if QMessageBox.warning(self, tr('Vider le dossier'), safe_rich(tr('Supprimer définitivement tous les messages de « {label} » ?\n\nCette action est irréversible.').format(label=label)),
                               QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        account = self.account()
        self.run_and_reload(lambda: self.service.empty_folder(account, name), lambda n: tr('{valeur} définitivement.').format(valeur=count(n, "message supprimé", "messages supprimés")))

    def manage_folder(self, operation):
        account = self.account()
        if self.busy or account is None:
            self.statusBar().showMessage(tr('Choisissez d’abord un compte (pas la réception unifiée).'))
            return
        if self.offline.isChecked():
            self.statusBar().showMessage(tr('Reconnectez-vous pour gérer les dossiers.'))
            return
        current = self.current_folder()
        if operation == 'create':
            name, ok = QInputDialog.getText(self, tr('Nouveau dossier'), tr('Nom du dossier'))
            if not ok or not name.strip():
                return
            self.run_and_reload(lambda: self.service.manage_folder(account, 'create', name), tr('Dossier « {valeur} » créé.').format(valeur=name.strip()), True)
            return
        if not current:
            return
        name, label = current
        if name.upper() == 'INBOX' or label in self.PROTECTED:
            self.statusBar().showMessage(tr('Les dossiers système (réception, envoyés, brouillons, corbeille, spam) ne peuvent pas être modifiés.'))
            return
        if operation == 'rename':
            # Le dossier garde son emplacement : seul son propre nom change (« Parent › Enfant » -> Enfant).
            leaf = label.split(' › ')[-1]
            new_name, ok = QInputDialog.getText(self, tr('Renommer le dossier'), tr('Nouveau nom'), text=leaf)
            if not ok or not new_name.strip() or new_name.strip() == leaf:
                return
            self.run_and_reload(lambda: self.service.manage_folder(account, 'rename', name, new_name), tr('Dossier renommé.'), True)
        elif operation == 'delete':
            if QMessageBox.warning(self, tr('Supprimer le dossier'), safe_rich(tr('Supprimer le dossier « {label} » et tous les messages qu’il contient sur le serveur ?\n\nCette action est irréversible.').format(label=label)),
                                   QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
                return
            self.run_and_reload(lambda: self.service.manage_folder(account, 'delete', name), tr('Dossier « {label} » supprimé.').format(label=label), True)

    def account(self):
        value = self.account_box.currentData()
        return next((account for account in self.accounts if account.id == value), None)

    def selected_rows(self):
        """Messages sélectionnés ; une conversation compte pour tous ses messages de la liste."""
        items = sorted((item for item in self.table.selectedItems() if not item.isHidden()), key=self.table.row)
        return [row for item in items if isinstance(item.data(Qt.UserRole), MessageRow) for row in item.data(Qt.UserRole).rows]

    def selected_row(self):
        """Le message lu : seulement quand un seul message est sélectionné."""
        item = self.table.currentItem()
        if len(self.table.selectedItems()) > 1:
            return None
        value = item.data(Qt.UserRole) if item and item.isSelected() and not item.isHidden() else None
        return value.raw if isinstance(value, MessageRow) else None

    def row_account(self, row):
        return next((account for account in self.accounts if account.id == row['account']), None)

    def reload_accounts(self):
        previous = self.account_box.currentData()
        self.accounts = self.database.accounts()
        self.account_box.blockSignals(True)
        self.account_box.clear()
        if self.accounts:
            self.account_box.addItem(tr('Tous les comptes'), tr('unified'))
            self.account_box.setItemData(0, tr('Réception unifiée de tous les comptes'), Qt.ToolTipRole)
        for account in self.accounts:
            secure = account.imap.mode != 'Aucun' and account.smtp.mode != 'Aucun'
            self.account_box.addItem(icon('lock-keyhole' if secure else 'lock-keyhole-open',self.appearance.colors['muted' if secure else 'warning']),
                                     account.name or account.email,account.id)
            self.account_box.setItemData(self.account_box.count()-1, safe_rich(account.email), Qt.ToolTipRole)
        index = self.account_box.findData(previous)
        self.account_box.setCurrentIndex(index if index >= 0 else 1 if self.accounts else -1)
        self.account_box.blockSignals(False)
        self.result_account.blockSignals(True)
        self.result_account.clear()
        self.result_account.addItem(tr('Tous les comptes'),None)
        for account in self.accounts:
            self.result_account.addItem(account.name,account.id)
        self.result_account.blockSignals(False)
        self.refresh_account_controls()
        self.load_folders()

    def add_account(self):
        if self.busy:
            return
        if AccountDialog(self.database, self.secrets, self.runner.tls, self).exec():
            self.reload_accounts()
            self.restart_idle()
            self.sync_now()

    def edit_account(self):
        if self.busy or not self.accounts:
            return
        account = self.choose_account(tr('Compte'))
        if account is None:
            return
        if AccountDialog(self.database, self.secrets, self.runner.tls, self, account=account).exec():
            self.reload_accounts()
            self.restart_idle()

    def choose_account(self, title):
        account = self.account()
        if account is not None:
            return account
        names = [f'{a.name} — {a.email}' for a in self.accounts]
        name, ok = QInputDialog.getItem(self, title, tr('Choisissez le compte'), names, 0, False)
        return self.accounts[names.index(name)] if ok else None

    def delete_account(self, account=None):
        if self.busy or not self.accounts:
            return False
        account = account or self.choose_account(tr('Supprimer le compte'))
        if account is None:
            return False
        if any(window.isVisible() for window in self.composers):
            QMessageBox.information(self, tr('Supprimer le compte'), tr('Fermez d’abord les fenêtres de rédaction ouvertes.'))
            return False
        text = (tr('Supprimer le compte « {name} » ({email}) de Smail ?\n\nVos messages restent sur le serveur. Seront effacés de ce PC : les paramètres du compte, le cache hors ligne, les brouillons locaux, les copies locales des messages envoyés, les certificats approuvés et les mots de passe ou jetons OAuth2 du Gestionnaire d’identifiants Windows.\n\nCette action est irréversible.').format(name=account.name, email=account.email))
        box = QMessageBox(QMessageBox.Warning, tr('Supprimer le compte'), text, QMessageBox.Yes | QMessageBox.Cancel, self)
        box.button(QMessageBox.Yes).setText(tr('Supprimer le compte'))
        box.button(QMessageBox.Cancel).setText(tr('Annuler'))
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Yes:
            return False
        for thread in self.idle_threads:
            if thread.account.id == account.id:
                thread.stop()
        self.set_busy(True)
        def finish(message):
            self.set_busy(False)
            self.reload_accounts()
            self.restart_idle()
            self.statusBar().showMessage(message)
        self.runner.run(lambda: self.service.delete_account(account),
                        lambda _: finish(tr('Compte « {name} » supprimé de ce PC.').format(name=account.name)), finish)
        return True

    def set_busy(self, busy):
        self.busy = busy
        focused = QApplication.focusWidget()
        if busy and focused in (self.search, self.table, self.folders):
            self.focus_before = focused  # Le champ désactivé perd le focus : il le retrouvera ensuite.
        for widget in (self.account_box, self.add, self.refresh, self.folders, self.table, self.search, self.offline, self.filters_button):
            widget.setEnabled(not busy)
        for widget in (self.account_cards,self.account_chips,self.unified_button):
            widget.setEnabled(not busy)
        self.search_filters.setEnabled(not busy)
        for button in self.filter_group.buttons():
            button.setEnabled(not busy)
        if busy and not self.rows and self.accounts:
            self.list_stack.setCurrentIndex(1)
        elif not busy:
            self.list_stack.setCurrentIndex(0 if self.table.count() else 2)
            # Pendant le chargement, Qt a donné le focus au bouton suivant de l’en-tête (cadre bleu sans raison) :
            # il revient au champ qui l’avait, ou à la liste des messages.
            focused = QApplication.focusWidget()
            if isinstance(focused, Button) and focused.window() is self:
                target = getattr(self, 'focus_before', None) or self.table
                (target if target.isEnabled() else self.table).setFocus(Qt.OtherFocusReason)
        self.update_actions()

    def update_selection_bar(self):
        """Plusieurs messages cochés : cases visibles sur chaque ligne et barre d’actions groupées."""
        count = len(self.selected_rows())
        several = count > 1
        self.table.itemDelegate().check_all = several
        self.selection_count.setText(tr('{count} sélectionnés').format(count=count) if several else '')
        self.selection_bar.setVisible(several)
        self.filter_bar.setVisible(not several)
        for button in self.selection_buttons[1:-1]:
            button.setEnabled(several and not self.busy)
        self.table.viewport().update()

    def select_all_messages(self):
        """Coche tous les messages affichés (pas ceux des groupes repliés ni ceux masqués par un filtre)."""
        from PySide6.QtCore import QItemSelection
        selection = QItemSelection()
        for row in range(self.table.count()):
            item = self.table.item(row)
            if not item.isHidden() and not item.data(COLLAPSED_ROLE) and item.data(Qt.UserRole) is not None:
                index = self.table.indexFromItem(item)
                selection.select(index, index)
        self.table.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
        self.table.setFocus()

    def clear_selection(self):
        current = self.table.currentItem()
        self.table.clearSelection()
        if current is not None and not current.isHidden():
            current.setSelected(True)  # Retour au message courant seul.

    def update_actions(self):
        self.offline_action.setEnabled(self.offline.isEnabled())
        selected, single = bool(self.selected_rows()), self.selected_row() is not None
        for action in self.message_actions:
            action.setEnabled(not self.busy and (single if action in self.single_actions else selected))
        self.reader.set_actions_enabled(not self.busy and single)
        online = not self.busy and not self.offline.isChecked()
        current = self.current_folder()
        self.mark_all_action.setEnabled(online and bool(self.accounts) and (current is not None or self.account() is None))
        # « Ce n’est pas un spam » n’a de sens que dans le dossier des indésirables.
        self.not_junk_action.setEnabled(self.not_junk_action.isEnabled() and current is not None and self.is_special(*current, 'junk'))
        self.edit_draft_action.setEnabled(self.edit_draft_action.isEnabled() and self.in_drafts())
        self.folder_actions['create'].setEnabled(online and self.account() is not None)
        editable = current is not None and current[0].upper() != 'INBOX' and current[1] not in self.PROTECTED
        self.folder_actions['rename'].setEnabled(online and editable)
        self.folder_actions['delete'].setEnabled(online and editable)
        self.folder_actions['empty'].setEnabled(online and current is not None and
                                                (self.is_special(*current,'trash') or self.is_special(*current,'junk')))

    def open_search_filters(self):
        from mailclient.ui.search_dialog import SearchDialog
        dialog = SearchDialog(self.search.text(), self)
        if dialog.exec():
            self.search.setText(dialog.query())
            self.new_search()

    def show_original(self):
        """Message › Afficher l’original : en-têtes et verdict SPF / DKIM / DMARC (copie locale du message lu)."""
        import base64
        row = self.selected_row()
        if row is None:
            return
        payload = self.database.cache_get('body', self.service.body_key(row))
        if not payload:
            self.notify(tr('Ouvrez d’abord le message (il n’est pas encore téléchargé).'), kind='error')
            return
        from mailclient.ui.original_dialog import OriginalDialog
        OriginalDialog(base64.b64decode(payload), row.get('subject', ''), self).exec()

    def refresh_all(self):
        """« Actualiser » (bouton et F5) : dossiers et liste rechargés, puis synchronisation hors ligne."""
        self.load_folders()
        self.sync_now()

    def set_cache_status(self, text):
        """Ligne d’information sous l’en-tête : masquée quand elle est vide (sinon un grand espace vide)."""
        self.cache_status.setText(text)
        self.cache_status.setVisible(bool(text))

    def update_connection(self):
        """Indicateur discret de l’en-tête : en ligne (dernière synchronisation) ou hors ligne."""
        if self.offline.isChecked():
            self.connection.setText(tr('○ Hors ligne · cache local'))
            self.connection.setToolTip(tr('Aucune connexion aux serveurs. Pour vous reconnecter : Outils › Travailler hors ligne.'))
        else:
            when = tr(' · synchronisé à {last_sync:%H:%M}').format(last_sync=self.last_sync) if self.last_sync else ''
            self.connection.setText(tr('● En ligne') + when)
            self.connection.setToolTip(tr('Smail se connecte à vos serveurs. Pour travailler sans connexion : Outils › Travailler hors ligne.'))

    def notify(self, text, action=None, callback=None, kind='info'):
        """Message important : notification flottante (avec action éventuelle). La barre d’état n’en garde pas de
        doublon ; elle sert aux informations d’état (synchronisation, filtres)."""
        self.statusBar().clearMessage()
        self.toast.show_message(text, action, callback, kind)

    def failure(self, message):
        self.pending_window = False
        self.set_busy(False)
        self.notify(message, kind='error')
        if not self.rows:
            self.empty_title.setText(tr('Connexion ou opération indisponible'))
            self.empty_description.setText(message)

    def load_folders(self, *_):
        if self.busy or self.quitting:
            return
        self.update_account_selection()
        self.reader.clear()
        self.local_copy = None
        self.rows = []
        self.folders.blockSignals(True)
        self.folders.clear()
        self.folders.blockSignals(False)
        self.table.setRowCount(0)
        self.page = self.total = 0
        self.list_generation += 1
        self.loading_more = False
        self.search.clear()
        account = self.account()
        self.heading.setText(account.name if account else tr('Réception unifiée') if self.accounts else tr('Bienvenue'))
        warning = account and (account.imap.mode == 'Aucun' or account.smtp.mode == 'Aucun')
        unsafe = [a.name for a in self.accounts if a.imap.mode == 'Aucun' or a.smtp.mode == 'Aucun']
        text = tr('Connexion en clair : votre mot de passe et vos mails peuvent être lus par des tiers.') if warning else \
               tr('Compte(s) non chiffré(s) à vérifier : ')+', '.join(unsafe) if account is None and unsafe else ''
        self.security.setText(text)
        self.security_frame.setVisible(bool(text))
        if not self.accounts:
            self.set_busy(False)
            self.statusBar().showMessage(tr('Ajoutez un compte pour commencer.'))
            return
        if account is None:
            self.folder_data = [('INBOX', 'Réception unifiée')]
            self.fill_folders(self.folder_data)
            self.folders.setCurrentRow(0)
            return
        self.set_busy(True)
        def done(result):
            folders, offline = result
            from mailclient.ui.folder_list import ordered
            self.folder_data = folders = ordered(folders)
            self.folders.blockSignals(True)
            self.fill_folders(folders)
            self.folders.blockSignals(False)
            self.set_busy(False)
            self.set_cache_status(tr('Dossiers enregistrés sur ce PC (hors ligne)') if offline else '')
            if folders:
                index = next((i for i,(name,_) in enumerate(folders) if name.upper() == 'INBOX'), 0)
                self.folders.setCurrentRow(index)
            else:
                self.empty_title.setText(tr('Aucun dossier disponible'))
                self.empty_description.setText(tr('Reconnectez-vous puis actualisez pour charger les dossiers.') if offline else tr('Le serveur ne propose aucun dossier sélectionnable.'))
        offline = self.offline.isChecked()
        self.runner.run(lambda: self.service.folders(account, offline), done, self.failure)

    def fill_folders(self, folders):
        """Un élément par dossier : icône du dossier spécial et nombre de non-lus (dernière synchronisation)."""
        from mailclient.ui.folder_list import kind
        for name, label in folders:
            item = QListWidgetItem(icon(kind(name, label)[1], self.appearance.colors['muted']), tr(label))
            item.setToolTip(safe_rich(tr(label) if label == name else f'{tr(label)} ({name})'))  # Nom fourni par le serveur.
            self.folders.addItem(item)
        self.update_folder_counts()

    def update_folder_counts(self):
        from mailclient.ui.folder_list import COUNT_ROLE
        account = self.account()
        if account is None:  # Réception unifiée : non-lus des réceptions de tous les comptes.
            counts = {'INBOX': sum(next((n for f, n in self.service.unread(a).items() if f.upper() == 'INBOX'), 0)
                                   for a in self.accounts)}
        else:
            counts = self.service.unread(account)
        for index, (name, label) in enumerate(self.folder_data[:self.folders.count()]):
            count = counts.get(name, 0)
            item = self.folders.item(index)
            item.setData(COUNT_ROLE, count)
            item.setData(Qt.AccessibleTextRole, f'{tr(label)}, {count_words(count, "non lu", "non lus")}' if count else tr(label))

    def folder_changed(self, index):
        if index >= 0 and not self.busy:
            if index < len(self.folder_data):
                self.heading.setText(tr(self.folder_data[index][1]))
            self.reset_filter()
            self.page = 0
            self.load_messages()

    def reset_filter(self):
        """Nouveau dossier : retour à « Tous » (un filtre conservé faisait croire à un dossier vide).
        « Non lus » est masqué dans Envoyés et Brouillons, où tous les messages sont les vôtres, donc lus."""
        from mailclient.ui.folder_list import kind
        current = self.current_folder()
        own = current is not None and kind(*current)[1] in ('send', 'file-pen-line')
        self.filter_buttons['Non lus'].setVisible(not own)
        self.page_filter = 'Tous'
        self.filter_buttons['Tous'].setChecked(True)
        self.update_local_drafts()

    def update_local_drafts(self):
        """Bouton « N brouillons enregistrés sur ce PC » affiché dans le dossier Brouillons."""
        from mailclient.ui.folder_list import kind
        current = self.current_folder()
        drafts = 0
        if current is not None and kind(*current)[1] == 'file-pen-line':
            account = self.account()
            drafts = sum(1 for draft in self.database.cache_list('draft') if draft.get('account') == account.id)
        self.local_drafts_button.setText(tr('{valeur} sur ce PC — ouvrir').format(valeur=count(drafts, "brouillon enregistré", "brouillons enregistrés")))
        self.local_drafts_button.setVisible(bool(drafts))

    def new_search(self):
        self.page = 0
        self.load_messages()

    @staticmethod
    def row_key(row):
        return row.get('account'), row.get('folder'), row.get('uid')

    def page_fetcher(self, cache_only=False):
        """Fonction (page -> résultat) pour le dossier et la recherche affichés ; None pour « tous les dossiers »."""
        index = self.folders.currentRow()
        account, query = self.account(), self.search.text().strip()
        if bool(query) and account is not None and self.result_scope.currentIndex() == 1:
            return None
        offline = self.offline.isChecked() or cache_only
        if account:
            folder = self.folder_data[index][0]
            return lambda page: self.service.messages(account, folder, page, query, offline)
        accounts = list(self.accounts)
        return lambda page: self.service.unified(accounts, page, query)

    def merge_rows(self, rows, more):
        """Ajoute les messages d’une page suivante, sans doublon si la boîte a bougé entre deux pages."""
        known = {self.row_key(row) for row in rows}
        added = [row for row in more if self.row_key(row) not in known]
        rows.extend(added)
        return added

    def update_list_status(self):
        if self.list_all_folders:
            return
        loaded, conversations = len(self.rows), self.table.count()
        grouped = f' · {count(conversations, "conversation")}' if conversations != loaded else ''
        if self.loading_more:
            text = tr('Chargement des messages plus anciens…')
        elif not self.total:
            text = tr('Aucun message')
        elif loaded < self.total and not self.list_exhausted:
            text = tr('{loaded} sur {valeur} — faites défiler pour la suite{grouped}').format(loaded=loaded, valeur=count(self.total, "message"), grouped=grouped)
        elif loaded < self.total:
            text = tr('{loaded} sur {valeur} — la suite n’est pas en cache{grouped}').format(loaded=loaded, valeur=count(self.total, "message"), grouped=grouped)
        else:
            text = f'{count(self.total, "message")}{grouped}'
        self.page_label.setText(text)

    def can_load_more(self):
        return (not self.list_all_folders and not self.list_exhausted and len(self.rows) < self.total
                and self.folders.currentRow() >= 0)

    def maybe_load_more(self, auto=False):
        """Bas de liste atteint (ou liste trop courte pour défiler) : charge les 50 messages suivants."""
        if self.busy or self.loading_more or self.rendering or self.quitting or not self.can_load_more():
            return
        bar = self.table.verticalScrollBar()
        short = bar.maximum() == 0 or self.list_stack.currentIndex() != 0  # Rien à faire défiler (ou filtre vide).
        if not short and bar.maximum() - bar.value() > max(bar.pageStep() // 3, 40):
            return
        if not auto and not short:
            self.auto_loads = 0  # Vrai défilement jusqu’en bas : l’utilisateur demande la suite.
        else:
            # Liste trop courte (filtre « Non lus »…) : quelques pages au plus sans geste de l’utilisateur.
            if self.auto_loads >= 4:
                return
            self.auto_loads += 1
        self.load_more()

    def load_more(self):
        fetch = self.page_fetcher()
        if fetch is None:
            return
        page, generation = self.page + 1, self.list_generation
        self.loading_more = True
        self.update_list_status()
        def done(result):
            if generation != self.list_generation:
                return  # Dossier ou recherche changé entre-temps.
            self.loading_more = False
            self.total = result['total']
            added = self.merge_rows(self.rows, result['rows'])
            if result['rows']:
                self.page = page
            if not added:
                self.list_exhausted = True
            else:
                self.render_rows(keep_view=True)
                self.filter_page(self.page_filter)
            self.update_list_status()
            QTimer.singleShot(0, self, lambda: self.maybe_load_more(auto=True))
        def failed(message):
            if generation != self.list_generation:
                return
            self.loading_more = False
            self.update_list_status()
            self.statusBar().showMessage(tr('Messages plus anciens indisponibles : ') + message)
        self.runner.run(lambda: fetch(page), done, failed)

    def load_messages(self, cache_only=False):
        """Recharge la liste ; après une action, garde la profondeur déjà chargée (self.page)."""
        index = self.folders.currentRow()
        if self.busy or self.quitting or index < 0:
            return
        scroll = self.table.verticalScrollBar().value() if self.page else 0
        self.list_generation += 1
        self.loading_more = self.list_exhausted = False
        self.auto_loads = 0
        self.reader.clear()
        self.local_copy = None
        self.rows = []
        self.table.setRowCount(0)
        account, query, depth = self.account(), self.search.text().strip(), self.page
        fetch = self.page_fetcher(cache_only)
        all_folders = fetch is None
        self.list_all_folders = all_folders
        self.set_busy(True)
        def done(result):
            self.rows, self.total = result['rows'], result['total']
            self.page = result.get('page', 0)
            self.render_rows()
            if all_folders:
                labels = dict(self.database.cache_get('folders', account.id, []) or [])
                for row in self.rows:  # Dossier d’origine visible dans la liste.
                    row['preview'] = f'[{labels.get(row["folder"], row["folder"])}] ' + (row.get('preview') or '')
                self.render_rows()
                self.page_label.setText(tr('{valeur} dans tous les dossiers').format(valeur=count(len(self.rows), "résultat")) +
                                        (tr(' — les 100 plus récents') if result.get('truncated') else ''))
            # Ligne d’information affichée seulement quand elle apprend quelque chose : recherche ou copie locale.
            if query:
                self.set_cache_status(tr('Recherche dans les messages déjà téléchargés (hors ligne)') if result['offline'] else
                                          tr('Recherche dans tous les dossiers du compte') if all_folders else tr('Recherche dans tout le dossier'))
            else:
                self.set_cache_status(tr('Messages enregistrés sur ce PC (hors ligne)') if result['offline'] else '')
            if not self.rows and result['offline'] and self.total:
                self.set_cache_status(tr('Cette page n’est pas encore en cache. Reconnectez-vous ou augmentez la limite dans Préférences.'))
            self.list_exhausted = not self.rows
            self.set_busy(False)
            self.filter_page(self.page_filter)
            self.update_list_status()
            if scroll:
                self.table.verticalScrollBar().setValue(scroll)
            self.empty_title.setText(tr('Aucun résultat') if query else tr('Aucun message'))
            self.empty_description.setText(tr('Essayez un autre terme ou retirez un filtre.') if query else tr('Ce dossier ne contient aucun message disponible.'))
            if not self.rows and result['offline'] and self.total:
                self.empty_title.setText(tr('Page non téléchargée'))
                self.empty_description.setText(self.cache_status.text())
            QTimer.singleShot(0, self, lambda: self.maybe_load_more(auto=True))
        if all_folders:
            offline = self.offline.isChecked() or cache_only
            operation = lambda: self.service.search_all(account, query, offline)
        else:
            def operation():
                # Rechargement après une action : mêmes pages qu’avant, pour ne pas perdre sa place.
                result = fetch(0)
                rows, loaded = list(result['rows']), 0
                for page in range(1, depth + 1):
                    if len(rows) >= result['total']:
                        break
                    more = fetch(page)
                    if not more['rows']:
                        break
                    self.merge_rows(rows, more['rows'])
                    loaded = page
                return dict(result, rows=rows, page=loaded)
        self.runner.run(operation, done, self.failure)

    def conversations_enabled(self):
        return bool(self.database.setting('conversation_view', True))

    def toggle_conversations(self, checked):
        self.database.set_setting('conversation_view', bool(checked))
        if not self.busy:
            self.reader.clear()
            self.render_rows()
            self.filter_page(self.page_filter)

    def render_rows(self, keep_view=False):
        """Une ligne par conversation (ou par message si le regroupement est désactivé).

        keep_view : messages ajoutés au défilement, la sélection, le message lu et la position sont conservés."""
        from mailclient.core.threads import group_threads
        selected = {self.row_key(row) for row in self.selected_rows()} if keep_view else set()
        current = self.table.currentItem() if keep_view else None
        current_view = current.data(Qt.UserRole) if current else None
        current_keys = {self.row_key(row) for row in current_view.rows} if isinstance(current_view, MessageRow) else set()
        scroll = self.table.verticalScrollBar().value()
        self.rendering = True  # La liste vidée puis remplie ne doit pas déclencher de chargement.
        self.table.blockSignals(True)
        try:
            self.table.clear()
            self.populate_rows(group_threads(self.rows) if self.conversations_enabled() else [[row] for row in self.rows])
            self.refresh_headers()
            if keep_view:
                for index in range(self.table.count()):
                    item = self.table.item(index)
                    keys = {self.row_key(row) for row in item.data(Qt.UserRole).rows}
                    if keys & current_keys:
                        self.table.setCurrentItem(item, QItemSelectionModel.NoUpdate)
                    if keys & selected:
                        item.setSelected(True)
                self.table.doItemsLayout()  # Plage de défilement à jour avant de restaurer la position.
                self.table.verticalScrollBar().setValue(scroll)
        finally:
            self.table.blockSignals(False)
            self.rendering = False

    def populate_rows(self, groups):
        """Remplit la liste ; les signaux de self.table sont déjà bloqués par l’appelant."""
        for group in groups:
            row = group[0]
            row_account = self.row_account(row)
            view = MessageRow.from_thread(group,row_account)
            item = QListWidgetItem(f'{view.sender} · {view.subject} · {view.preview} · {view.time}'
                                   + (f' · {view.count} messages' if view.count > 1 else ''))
            item.setData(Qt.UserRole,view)
            item.setData(GROUP_ROLE, date_group(max(timestamp(message) for message in group)))
            item.setToolTip(safe_rich(f'{row["sender"]}\n{view.subject}\n{view.account_name}\n{row["date"]}'
                            + (tr('\nConversation de {count} messages chargés').format(count=view.count) if view.count > 1 else '')))
            self.table.addItem(item)

    def refresh_headers(self):
        """Titre de date au-dessus du premier message visible de chaque groupe (filtres compris) ; un groupe
        replié n’affiche que son titre et son nombre de messages."""
        from mailclient.ui.components import HEADER_ROLE
        collapsed = set(self.database.setting('collapsed_groups', []) or []) - {ALWAYS_OPEN}
        items = [self.table.item(index) for index in range(self.table.count())]
        visible = [item for item in items if not item.data(FILTERED_ROLE)]
        counts = {}
        for item in visible:
            counts[item.data(GROUP_ROLE)] = counts.get(item.data(GROUP_ROLE), 0) + 1
        previous = None
        for item in items:
            if item.data(FILTERED_ROLE):
                item.setHidden(True)
                continue
            group = item.data(GROUP_ROLE)
            first = group != previous
            folded = group in collapsed
            item.setHidden(folded and not first)
            for role, value in ((HEADER_ROLE, group if first else None), (COLLAPSED_ROLE, folded and first),
                                (GROUP_COUNT_ROLE, counts.get(group, 0) if first else None)):
                if item.data(role) != value:
                    item.setData(role, value)
            previous = group
        self.table.doItemsLayout()

    def toggle_group(self, group):
        """Clic sur le titre d’un groupe de dates : repli ou dépli, mémorisé pour les prochaines fois."""
        if not group or group == ALWAYS_OPEN:
            return
        collapsed = set(self.database.setting('collapsed_groups', []) or [])
        collapsed ^= {group}
        self.database.set_setting('collapsed_groups', sorted(collapsed))
        self.refresh_headers()

    def row_action(self, index, name):
        """Bouton d’une ligne au survol : l’action porte sur cette ligne (conversation entière)."""
        item = self.table.item(index.row())
        if item is None or self.busy:
            return
        if not item.isSelected() or len(self.table.selectedItems()) > 1:
            self.table.setCurrentItem(item)  # Sélectionne seulement cette ligne.
        if name == 'read':
            self.toggle_read()
        else:
            self.move(name)

    def selected_view(self):
        item = self.table.currentItem()
        if len(self.table.selectedItems()) > 1 or not item or not item.isSelected() or item.isHidden():
            return None
        value = item.data(Qt.UserRole)
        return value if isinstance(value, MessageRow) else None

    def thread_entry(self, row, account):
        from email.utils import parseaddr
        from mailclient.ui.view_models import MessageRow as View
        name, address = parseaddr(row.get('sender', ''))
        who = 'Moi' if account and address.casefold() == account.email.casefold() else (name or address or '?')
        folders = dict(self.database.cache_get('folders', account.id, []) or []) if account else {}
        current = self.current_folder()
        where = '' if current and row.get('folder') == current[0] else f' · {folders.get(row.get("folder"), row.get("folder", ""))}'
        extract = row.get('preview') or (tr('Contenu pas encore téléchargé') if row.get('preview') is None else '')
        return (f'{who} · {View.from_row(row).time}{where}', extract, bool(row.get('unread')),
                f'{row.get("sender","")}\n{row.get("subject","")}\n{row.get("date","")}')

    @staticmethod
    def remember_extract(row, mail):
        """Un message ouvert fournit l’extrait affiché quand il est replié dans la conversation."""
        if row.get('preview') is None:
            from mailclient.core.parser import snippet
            row['preview'] = snippet(mail)

    def thread_elsewhere(self):
        listed = {(row.get('account'), row.get('folder'), row.get('uid')) for row in self.rows}
        return sum((row.get('account'), row.get('folder'), row.get('uid')) not in listed for row in self.thread_rows)

    def step_thread(self, delta):
        if self.reader.thread_current >= 0:  # Une conversation de plusieurs messages est ouverte.
            self.open_thread_message(self.thread_index + delta)

    def open_thread_message(self, index):
        """Clic dans le bandeau de conversation : affiche ce message sans quitter la conversation."""
        if self.busy or not 0 <= index < len(self.thread_rows):
            return
        row, account = self.thread_rows[index], self.thread_account
        self.reader.clear(tr('Chargement du message…'), keep_thread=True)
        self.set_busy(True)
        offline = self.offline.isChecked()
        def done(mail):
            self.thread_index = index
            self.remember_extract(row, mail)
            self.reader.display(mail, keep_thread=True)
            self.reader.set_thread([self.thread_entry(r, account) for r in self.thread_rows], index, self.thread_elsewhere())
            self.set_busy(False)
            self.mark_opened(account, row)
            if self.pending_window:
                QTimer.singleShot(0, self.open_in_window)
        def failed(message):
            self.reader.clear(message, keep_thread=True)
            self.failure(message)
        self.runner.run(lambda: self.service.message(account, row, offline), done, failed)

    def read_selected(self):
        if self.table.selectedItems():
            self.local_copy = None  # Un message de la liste remplace la copie locale ouverte.
        current = self.table.currentItem()
        if current is not None and current.data(COLLAPSED_ROLE) and len(self.table.selectedItems()) <= 1:
            group = current.data(GROUP_ROLE)  # Lu maintenant : la ligne peut disparaître avant le déclenchement.
            QTimer.singleShot(0, self, lambda: self.toggle_group(group))  # Annulé si la fenêtre est détruite.
            return
        view = self.selected_view()
        row = view.raw if view else None
        if self.busy:
            return
        if not row:
            count = len(self.selected_rows())
            if count > 1:
                self.reader.clear(tr('{count} messages sélectionnés').format(count=count))
            return
        account = self.row_account(row)
        self.reader.clear(tr('Chargement du message…'))
        self.set_busy(True)
        offline = self.offline.isChecked()
        grouped = self.conversations_enabled()
        def operation():
            if not grouped:
                return self.service.message(account, row, offline), [row], 0
            # Conversation complète (réponses retrouvées dans les autres dossiers en cache) ;
            # ouverture sur le premier message non lu, sinon sur le plus récent.
            messages = self.service.conversation(account, list(view.rows))
            index = next((i for i, item in enumerate(messages) if item.get('unread')), len(messages) - 1)
            return self.service.message(account, messages[index], offline), messages, index
        def done(result):
            mail, messages, index = result
            self.thread_rows, self.thread_account, self.thread_index = messages, account, index
            self.remember_extract(messages[index], mail)
            self.reader.display(mail, keep_thread=True)
            self.reader.set_thread([self.thread_entry(r, account) for r in messages] if len(messages) > 1 else [], index, self.thread_elsewhere())
            self.mark_opened(account, messages[index])
            current = self.table.currentItem()
            if current and current.data(Qt.UserRole).raw is row and messages[index] is row and mail.text:
                from dataclasses import replace
                view = current.data(Qt.UserRole)
                view = replace(view,preview=' '.join(mail.text.split())[:180])
                current.setData(Qt.UserRole,view)
                current.setText(f'{view.sender} · {view.subject} · {view.preview} · {view.time}')
            self.set_busy(False)
            fade(self.reader.headers,self.appearance)
            if self.pending_window:
                QTimer.singleShot(0, self.open_in_window)  # Double-clic pendant le chargement.
            self.statusBar().showMessage(tr('Message chargé ; images distantes bloquées par défaut.'))
        def failed(message):
            self.reader.clear(message)
            self.failure(message)
        self.runner.run(operation, done, failed)

    def mark_opened(self, account, row):
        """Message ouvert : marqué comme lu dans Smail tout de suite, puis sur le serveur en arrière-plan.

        Le téléchargement utilise BODY.PEEK (sans effet sur le serveur) : sans ce marquage, un message lu restait
        « non lu » dans Smail, le webmail et le téléphone. Hors ligne ou réglage désactivé : rien ne change."""
        if account is None or not row.get('unread') or self.offline.isChecked() \
                or not self.database.setting('mark_read_on_open', True):
            return
        key = self.row_key(row)
        targets = [item for item in self.rows if self.row_key(item) == key] + [row]
        for item in targets:
            item['unread'] = False
        self.refresh_row_views(key)
        self.adjust_unread(account, row.get('folder'), -1)
        def failed(message):
            for item in targets:
                item['unread'] = True  # Le serveur n’a pas accepté : l’état réel est rétabli.
            self.refresh_row_views(key)
            self.adjust_unread(account, row.get('folder'), +1)
            self.notify(tr('Le message n’a pas pu être marqué comme lu sur le serveur : ') + message, kind='error')
        self.runner.run(lambda: self.service.action(account, [dict(row)], 'read'), lambda _: None, failed)

    def refresh_row_views(self, key):
        """Ligne de la liste recalculée (gras, point, filtre « Non lus ») après un changement d’état local."""
        from mailclient.ui.view_models import MessageRow as View
        for index in range(self.table.count()):
            item = self.table.item(index)
            view = item.data(Qt.UserRole)
            if isinstance(view, View) and any(self.row_key(r) == key for r in view.rows):
                rows = [next((r for r in self.rows if self.row_key(r) == self.row_key(old)), old) for old in view.rows]
                item.setData(Qt.UserRole, View.from_thread(rows, self.row_account(rows[0])))
        self.table.viewport().update()

    def adjust_unread(self, account, folder, delta):
        """Nombre de non-lus du dossier ajusté sans attendre la prochaine synchronisation."""
        counts = dict(self.service.unread(account))
        if folder in counts:
            counts[folder] = max(0, counts[folder] + delta)
            self.database.cache_put('unread', account.id, counts, account.id)
            self.update_folder_counts()

    def mutate(self, action, target='', rows=None, plan=None):
        """plan : [(compte, messages, action, cible)] ; par défaut la sélection courante et une seule action."""
        if plan is None:
            rows = rows if rows is not None else self.selected_rows()
            groups = {}
            for row in rows:
                groups.setdefault(row['account'], []).append(row)
            plan = [(self.row_account(group[0]), group, action, target) for group in groups.values()]
        if self.busy or not plan:
            return
        if self.offline.isChecked():
            self.statusBar().showMessage(tr('Reconnectez-vous pour modifier les messages du serveur.'))
            return
        if any(account is None for account,*_ in plan):
            self.statusBar().showMessage(tr('Le compte de ce message n’existe plus. Actualisez.'))
            return
        if all(step in ('read', 'unread', 'star', 'unstar') for _, _, step, _ in plan):
            self.change_state(plan)
            return
        self.set_busy(True)
        def operation():
            for account, group, step, destination in plan:
                self.service.action(account, group, step, destination)
        def done(_):
            self.set_busy(False)
            self.load_messages()
            moves = [(account, group, destination) for account, group, step, destination in plan if step == 'move']
            if moves:
                count = sum(len(group) for _, group, _ in moves)
                label = self.folder_label(moves[0][0], moves[0][2])
                where = tr('dans « {label} »').format(label=label) if len({destination for *_, destination in moves}) == 1 else tr('dans leurs dossiers')
                self.notify(tr('{count} message{valeur} déplacé{valeur} {where}.').format(count=count, valeur="s" if count > 1 else "", where=where),
                            tr('Annuler'), lambda: self.undo_move(moves))
            elif any(step == 'delete' for _, _, step, _ in plan):
                count = sum(len(group) for _, group, _, _ in plan)
                self.notify(tr('{count} message{valeur} supprimé{valeur} définitivement.').format(count=count, valeur="s" if count > 1 else ""))
        def failed(message):
            self.failure(message + tr(' Actualisez les dossiers source et destination avant de réessayer : l’action peut avoir été acceptée avant une coupure.'))
        self.runner.run(operation, done, failed)

    def mark_origin_locally(self, origin):
        """Après l’envoi d’une réponse ou d’un transfert : flèche affichée tout de suite sur le message d’origine."""
        if not origin or origin.get('flag') not in ('answered', 'forwarded'):
            return
        key = (origin.get('account'), origin.get('folder'), origin.get('uidvalidity', ''), origin.get('uid'))
        found = [row for row in self.rows if self.row_key(row) == key]
        for row in found:
            row[origin['flag']] = True
        if found:
            self.refresh_row_views(key)

    def change_state(self, plan):
        """Lu / non lu, suivi : appliqué tout de suite dans la liste, puis sur le serveur en arrière-plan.

        Sans rechargement : la sélection, le message lu et la position restent en place (un rechargement vidait
        la sélection et le volet de lecture). Si le serveur refuse, l’état d’origine est rétabli."""
        changed = []  # (ligne, champ, ancienne valeur, compte)
        for account, group, step, _ in plan:
            field, value = ('unread', step == 'unread') if step in ('read', 'unread') else ('starred', step == 'star')
            keys = {self.row_key(row) for row in group}
            for row in [item for item in self.rows if self.row_key(item) in keys] + list(group):
                if bool(row.get(field)) != value:
                    changed.append((row, field, row.get(field), account))
                    row[field] = value
        def refresh(restoring):
            counted = set()
            for row, field, old, account in changed:
                key = self.row_key(row)
                if field == 'unread' and key not in counted:  # Une fois par message, même présent deux fois.
                    counted.add(key)
                    self.adjust_unread(account, row.get('folder'), (-1 if old else 1) * (-1 if restoring else 1))
                self.refresh_row_views(key)
            self.update_actions()
        refresh(False)
        def operation():
            for account, group, step, destination in plan:
                self.service.action(account, group, step, destination)
        def failed(message):
            for row, field, old, _ in changed:
                row[field] = old
            refresh(True)
            self.failure(message)
        self.runner.run(operation, lambda _: None, failed)

    def folder_label(self, account, name):
        return tr(dict(self.database.cache_get('folders', account.id, []) or []).get(name, name))

    def undo_move(self, moves):
        """« Annuler » d’un déplacement : les messages reviennent dans leur dossier d’origine."""
        if self.busy:
            QTimer.singleShot(300, self, lambda: self.undo_move(moves))
            return
        if self.offline.isChecked():
            self.notify(tr('Reconnectez-vous pour annuler le déplacement.'), kind='error')
            return
        expected = sum(len(group) for _, group, _ in moves)
        self.set_busy(True)
        def operation():
            return sum(self.service.restore(account, group, destination) for account, group, destination in moves)
        def done(restored):
            self.set_busy(False)
            self.load_messages()
            if restored == expected:
                self.notify(tr('Déplacement annulé : messages remis à leur place.'))
            else:
                self.notify(tr('Déplacement annulé pour {restored} message{valeur} sur {expected} ; les autres sont restés dans le dossier de destination.').format(restored=restored, valeur="s" if restored > 1 else "", expected=expected), kind='error')
        def failed(message):
            self.failure(tr('Annulation impossible : ') + message)
        self.runner.run(operation, done, failed)

    def toggle_read(self):
        rows = self.selected_rows()
        if rows:
            self.mutate('read' if any(row['unread'] for row in rows) else 'unread', rows=rows)

    def toggle_star(self):
        rows = self.selected_rows()
        if rows:
            self.mutate('star' if not all(row.get('starred') for row in rows) else 'unstar', rows=rows)

    def move(self, kind):
        rows = self.selected_rows()
        if not rows or self.busy:
            return
        groups = {}
        for row in rows:
            groups.setdefault(row['account'], []).append(row)
        if kind == 'move' and len(groups) > 1:
            self.statusBar().showMessage(tr('Pour déplacer, sélectionnez des messages d’un seul compte.'))
            return
        plan = []
        for group in groups.values():
            account = self.row_account(group[0])
            if account is None:
                self.statusBar().showMessage(tr('Le compte de ce message n’existe plus. Actualisez.'))
                return
            folders = self.database.cache_get('folders', account.id, [])
            source = group[0]['folder']
            source_label = next((label for name,label in folders if name == source), source)
            if kind in self.SPECIAL_WORDS and self.is_special(source, source_label, kind):
                if kind != 'trash':
                    self.statusBar().showMessage(tr('Ce message est déjà dans le dossier de destination.'))
                    return
                plan.append((account, group, 'delete', ''))  # Depuis la corbeille : suppression définitive.
                continue
            target = self.special_folder(folders, kind, exclude=source) if kind in self.SPECIAL_WORDS else None
            if target is None:
                choices = [(name, label) for name,label in folders if name != source]
                if not choices:
                    self.statusBar().showMessage(tr('Aucun autre dossier disponible. Créez un dossier (Dossier › Nouveau dossier) puis réessayez.'))
                    return
                labels = [tr(label) if tr(label) == name else f'{tr(label)} — {name}' for name,label in choices]
                choice, ok = QInputDialog.getItem(self, tr('Destination'), tr('Choisissez le dossier de destination ({name})').format(name=account.name), labels, 0, False)
                if not ok:
                    return
                target = choices[labels.index(choice)][0]
            plan.append((account, group, 'move', target))
        count = len(rows)
        subject = tr('ce message') if count == 1 else tr('ces {count} messages').format(count=count)
        if any(step == 'delete' for _,_,step,_ in plan):
            if QMessageBox.warning(self, tr('Supprimer définitivement'), tr('Supprimer définitivement {subject} de la corbeille ?\n\nCette action est irréversible.').format(subject=subject),
                                   QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
                return
        self.mutate(None, plan=plan)

    def eventFilter(self, watched, event):
        if watched is self.folders.viewport() and event.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            target = self.drop_target(event)
            if target is None:
                event.ignore()
                return True
            event.acceptProposedAction()
            if event.type() == QEvent.Drop:
                import json
                self.drop_messages(json.loads(bytes(event.mimeData().data(DRAG_MIME)).decode('utf-8')), target)
            return True
        return super().eventFilter(watched, event)

    def drop_target(self, event):
        """Dossier sous le pointeur, s’il peut recevoir les messages glissés."""
        if self.busy or self.offline.isChecked() or self.account() is None or not event.mimeData().hasFormat(DRAG_MIME):
            return None
        item = self.folders.itemAt(event.position().toPoint())
        index = self.folders.row(item) if item else -1
        current = self.current_folder()
        if not 0 <= index < len(self.folder_data) or (current and self.folder_data[index][0] == current[0]):
            return None
        return self.folder_data[index][0]

    def drop_messages(self, keys, target):
        wanted = {tuple(key) for key in keys}
        rows = [row for row in self.rows if (row.get('account'), row.get('folder'), row.get('uidvalidity', ''), row.get('uid')) in wanted]
        account = self.account()
        if not rows or account is None:
            return
        label = next((label for name, label in self.folder_data if name == target), target)
        self.mutate(None, plan=[(account, rows, 'move', target)])
        self.statusBar().showMessage(tr('{valeur} vers « {label} ».').format(valeur=count(len(rows), "message déplacé", "messages déplacés"), label=label))

    def displayed_account(self):
        if self.thread_rows and self.thread_account:
            return self.thread_account
        row = self.selected_row()
        return self.row_account(row) if row else None

    def in_drafts(self):
        current = self.current_folder()
        return current is not None and self.is_special(*current, 'drafts')

    def edit_server_draft(self):
        """Brouillon du serveur (webmail, téléphone…) repris dans la rédaction ; à l’envoi, il quitte les Brouillons."""
        row = self.selected_row()
        mail = self.reader.mail
        if row is None or mail is None or not self.in_drafts():
            self.statusBar().showMessage(tr('Sélectionnez et chargez d’abord le brouillon.'))
            return
        from mailclient.core.quote import quote_fragment
        from mailclient.ui.rich_text import clean_qt_html
        account = self.row_account(row)
        fields = dict(to=mail.recipients, cc=mail.cc, bcc='', subject=mail.subject, body=mail.text or '',
                      qt_html=clean_qt_html(quote_fragment(mail)) if (mail.html or '').strip() else '',
                      attachments=[attachment for attachment in mail.attachments if not attachment.cid],
                      server_draft={key: row.get(key) for key in ('account', 'folder', 'uid', 'uidvalidity', 'server')})
        window = ComposeWindow(self.service, self.accounts, account, fields, parent=self, offline=self.offline.isChecked)
        self.composers.add(window)
        window.show()

    def open_in_window(self):
        """Message affiché dans sa propre fenêtre ; pendant un chargement, ouverture dès la fin."""
        if self.in_drafts() and not self.busy and self.reader.mail is not None:
            return self.edit_server_draft()  # Dans les Brouillons, ouvrir un message = le reprendre.
        if self.busy:
            self.pending_window = True
            return
        self.pending_window = False
        account = self.displayed_account()
        if self.reader.mail is None or account is None:
            return
        from mailclient.ui.message_window import MessageWindow
        window = MessageWindow(self.reader.mail, account, self.appearance.dark)
        window.composeRequested.connect(self.compose_from)
        window.closed.connect(self.message_windows.discard)
        self.message_windows.add(window)
        window.show()

    def compose_from(self, mail, account, mode):
        if account is None or not any(a.id == account.id for a in self.accounts):
            self.statusBar().showMessage(tr('Le compte de ce message n’existe plus.'))
            return
        window = ComposeWindow(self.service, self.accounts, account, reply_fields(mail, account, mode), parent=self, offline=self.offline.isChecked)
        self.composers.add(window)
        window.show()

    def compose(self, mode=None):
        if not self.accounts:
            self.statusBar().showMessage(tr('Ajoutez un compte avant de rédiger.'))
            return
        row = self.selected_row()
        account = self.row_account(row) if row else self.account() or self.accounts[0]
        fields = None
        if mode:
            if not self.reader.mail or not row:
                self.statusBar().showMessage(tr('Sélectionnez et chargez d’abord le message.'))
                return
            if mode == 'forward_attachment':
                fields = self.forward_as_attachment(row, account)
                if fields is None:
                    return
            else:
                fields = reply_fields(self.reader.mail, account, mode)
            fields['origin'] = dict({key: row.get(key) for key in ('account', 'folder', 'uid', 'uidvalidity', 'server')},
                                    flag='forwarded' if mode in ('forward', 'forward_attachment') else 'answered')
        window = ComposeWindow(self.service, self.accounts, account, fields, parent=self, offline=self.offline.isChecked)
        self.composers.add(window)
        window.show()

    def forward_as_attachment(self, row, account):
        """Champs d’un transfert dont le message d’origine est joint intact (.eml), en-têtes et pièces jointes compris."""
        import base64
        from mailclient.core.parser import Attachment, safe_filename
        payload = self.database.cache_get('body', self.service.body_key(row))
        if not payload:
            self.notify(tr('Ouvrez d’abord le message (il n’est pas encore téléchargé).'), kind='error')
            return None
        mail = self.reader.mail
        fields = reply_fields(mail, account, 'forward')
        name = (safe_filename(mail.subject)[:80] or 'message') + '.eml'
        fields.update(body=f'\n\n{account.signature}' if account.signature else '',
                      attachments=[Attachment(name, 'message/rfc822', base64.b64decode(payload))])
        return fields

    # Sauvegarde et restauration ------------------------------------------------------------------------------------

    def ask_password(self, title, text):
        from PySide6.QtWidgets import QLineEdit
        value, ok = QInputDialog.getText(self, title, text, QLineEdit.Password)
        return value if ok else None

    def backup_data(self):
        """Fichier .smailbackup chiffré : comptes (sans mot de passe), réglages et données gardées sur ce PC."""
        from datetime import date
        from mailclient.core import backup
        if self.busy:
            return
        password = self.ask_password(tr('Sauvegarder'), tr('Mot de passe de la sauvegarde (au moins {count} caractères).\n'
                                                          'Il sera demandé pour la restaurer ; il ne peut pas être retrouvé.').format(count=backup.MIN_PASSWORD))
        if password is None:
            return
        if len(password) < backup.MIN_PASSWORD:
            self.notify(tr('Choisissez un mot de passe d’au moins {count} caractères.').format(count=backup.MIN_PASSWORD), kind='error')
            return
        if self.ask_password(tr('Sauvegarder'), tr('Saisissez de nouveau le mot de passe.')) != password:
            self.notify(tr('Les deux mots de passe sont différents. Aucune sauvegarde n’a été créée.'), kind='error')
            return
        name = tr('Smail-sauvegarde') + f'-{date.today().isoformat()}{backup.SUFFIX}'
        path, _ = QFileDialog.getSaveFileName(self, tr('Sauvegarder les comptes et réglages'), name,
                                              tr('Sauvegarde Smail (*.smailbackup)'))
        if not path:
            return
        if not path.lower().endswith(backup.SUFFIX):
            path += backup.SUFFIX
        self.set_busy(True)
        def operation():
            data = backup.export(self.database, password)
            output = QSaveFile(path)
            if not output.open(QIODevice.WriteOnly) or output.write(data) != len(data) or not output.commit():
                raise RuntimeError(tr('Impossible d’écrire la sauvegarde à cet emplacement.'))
        def done(_):
            from datetime import datetime, timezone
            self.set_busy(False)
            self.database.set_setting('last_backup', datetime.now(timezone.utc).isoformat(timespec='seconds'))
            self.notify(tr('Sauvegarde enregistrée. Gardez-la hors de ce PC (clé USB, OneDrive…) avec son mot de passe.'))
        self.runner.run(operation, done, self.failure)

    def restore_data(self):
        """Reprend une sauvegarde : comptes, réglages, règles, signatures, brouillons… (mots de passe à ressaisir)."""
        from mailclient.core import backup
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('Restaurer une sauvegarde'), '', tr('Sauvegarde Smail (*.smailbackup)'))
        if not path:
            return
        password = self.ask_password(tr('Restaurer une sauvegarde'), tr('Mot de passe de la sauvegarde :'))
        if password is None:
            return
        self.set_busy(True)
        def operation():
            from pathlib import Path
            data = Path(path).read_bytes()
            if len(data) > 512 * 1024 * 1024:
                raise RuntimeError(tr('Fichier trop volumineux pour une sauvegarde de Smail.'))
            try:
                return backup.read(data, password)
            except backup.BackupError as error:
                raise RuntimeError(str(error)) from None
        def loaded(payload):
            self.set_busy(False)
            info = backup.summary(payload)
            text = tr('Sauvegarde du {created} (Smail {version}).\n\nComptes : {accounts}\nBrouillons : {drafts} · copies envoyées : {sent} · '
                      'envois programmés : {outbox}\n\nLes comptes de la sauvegarde seront ajoutés (ou mis à jour) et vos préférences '
                      'remplacées. Les mots de passe ne sont pas sauvegardés : vous les saisirez ensuite.\n\nRestaurer ?').format(
                created=info['created'][:16].replace('T', ' '), version=info['version'],
                accounts=', '.join(info['accounts']) or tr('aucun'), drafts=info['drafts'], sent=info['sent'], outbox=info['outbox'])
            if QMessageBox.question(self, tr('Restaurer une sauvegarde'), safe_rich(text), QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) != QMessageBox.Yes:
                return
            self.set_busy(True)
            self.runner.run(lambda: backup.restore(self.database, payload), restored, self.failure)
        def restored(accounts):
            self.set_busy(False)
            self.apply_theme()
            self.reload_accounts()
            missing = []
            for account in accounts:
                try:
                    present = account.auth_method != 'password' or bool(self.secrets and self.secrets.get(account.id))
                except Exception:
                    present = False
                if not present:
                    missing.append(account)
            if missing:
                QMessageBox.information(self, tr('Sauvegarde restaurée'), safe_rich(tr(
                    'Comptes restaurés. Pour des raisons de sécurité, les mots de passe ne font pas partie de la sauvegarde.\n\n'
                    'Saisissez le mot de passe de chaque compte (Préférences › Comptes › Modifier) : {accounts}').format(
                    accounts=', '.join(account.email for account in missing))))
                self.preferences('Comptes')
            else:
                self.notify(tr('Sauvegarde restaurée.'))
        self.runner.run(operation, loaded, self.failure)

    def remind_backup(self):
        from datetime import datetime, timezone
        from mailclient.core import backup
        if self.quitting or not backup.reminder_due(self.database):
            return
        self.database.set_setting('backup_reminded', datetime.now(timezone.utc).isoformat(timespec='seconds'))
        self.notify(tr('Pensez à sauvegarder vos comptes et réglages (une fois par mois suffit).'), tr('Sauvegarder'), self.backup_data)

    def open_draft(self):
        if not self.accounts or self.busy:
            return
        self.set_busy(True)
        def done(drafts):
            self.set_busy(False)
            if not drafts:
                self.statusBar().showMessage(tr('Aucun brouillon local.'))
                return
            labels = [f'{draft.get("subject") or tr("(Sans objet)")} — {draft.get("to", "")} [{i+1}]' for i,draft in enumerate(drafts)]
            label, ok = QInputDialog.getItem(self, tr('Brouillons locaux'), tr('Ouvrir un brouillon'), labels, 0, False)
            if not ok:
                return
            draft = drafts[labels.index(label)]
            if not any(a.id == draft['account'] for a in self.accounts):
                self.statusBar().showMessage(tr('Le compte de ce brouillon n’existe plus.'))
                return
            existing = next((window for window in self.composers if window.id == draft['id'] and window.isVisible()), None)
            if existing:
                existing.raise_()
                return
            window = ComposeWindow(self.service, self.accounts, draft=draft, parent=self, offline=self.offline.isChecked)
            self.composers.add(window)
            window.show()
        self.runner.run(lambda: self.database.cache_list('draft'), done, self.failure)

    def open_sent_copy(self):
        if self.busy:
            return
        import base64
        from mailclient.core.parser import parse_message
        self.set_busy(True)
        def operation():
            copies = self.database.cache_list('sent-copy')
            return [(item, parse_message(base64.b64decode(item['raw']))) for item in copies]
        def done(copies):
            self.set_busy(False)
            if not copies:
                self.statusBar().showMessage(tr('Aucun message envoyé localement depuis cette installation.'))
                return
            labels = [f'{mail.subject} — {mail.date} [{i+1}]' for i,(_,mail) in enumerate(copies)]
            label, ok = QInputDialog.getItem(self, tr('Envoyés locaux'), tr('Lire une copie déjà envoyée'), labels, 0, False)
            if not ok:
                return
            local_copy, mail = copies[labels.index(label)]
            self.table.clearSelection()  # La liste du dossier reste affichée ; un clic sur un message y revient.
            self.local_copy = local_copy
            self.reader.display(mail)
            self.update_actions()
            self.statusBar().showMessage(tr('Copie locale d’un message déjà envoyé — Fichier › Enregistrer le message (.eml) pour la sauvegarder.'))
        self.runner.run(operation, done, self.failure)

    def export_sent_copy(self):
        """Enregistre le message lu (ou la copie envoyée locale ouverte) en .eml, lisible par toute messagerie."""
        import base64
        from mailclient.core.parser import safe_filename
        row = self.selected_row()
        raw = self.local_copy['raw'] if self.local_copy else (
            self.database.cache_get('body', self.service.body_key(row)) if row is not None else None)
        if self.busy or not raw:
            self.statusBar().showMessage(tr('Ouvrez d’abord le message à enregistrer.'))
            return
        subject = (self.reader.mail.subject if self.reader.mail else '') or 'message'
        name = (safe_filename(subject)[:80] or 'message') + '.eml'
        path, _ = QFileDialog.getSaveFileName(self, tr('Enregistrer le message (.eml)'), name, tr('Message e-mail (*.eml)'))
        if not path:
            return
        self.set_busy(True)
        def operation():
            data = base64.b64decode(raw)
            output = QSaveFile(path)
            if not output.open(QIODevice.WriteOnly) or output.write(data) != len(data) or not output.commit():
                raise RuntimeError(tr('Impossible d’exporter ce message à cet emplacement.'))
        def done(_):
            self.set_busy(False)
            self.statusBar().showMessage(tr('Message enregistré.'))
        self.runner.run(operation, done, self.failure)

    def sync_now(self):
        if self.quitting or self.offline.isChecked() or not self.accounts:
            return
        if self.sync_thread and self.sync_thread.isRunning():
            self.sync_requested = True
            return
        self.sync_requested = False
        thread = SyncThread(self.service, self.accounts, self.database.setting('cache_limit', 100), self)
        self.sync_thread = thread
        thread.updated.connect(self.synced)
        thread.problem.connect(self.background_error)
        def finished():
            if self.sync_requested and not self.quitting:
                QTimer.singleShot(1000, self.sync_now)
        thread.finished.connect(finished)
        thread.start()

    def synced(self, account_id, count):
        if self.quitting:
            return
        if count and self.tray and self.database.setting('notifications', True):
            self.tray.showMessage(tr('Smail'), tr('Nouveau message') if count == 1 else tr('{count} nouveaux messages').format(count=count), QSystemTrayIcon.Information, 6000)
        self.statusBar().showMessage(tr('Synchronisation terminée. Les derniers messages sont disponibles hors ligne.'))
        from datetime import datetime
        self.last_sync = datetime.now()
        self.update_connection()
        self.update_folder_counts()
        if self.account() is None and not self.busy:
            self.load_messages(cache_only=True)

    def background_error(self, error):
        if isinstance(error, CertificateAlert):
            message = tr('Certificat à vérifier : utilisez Actualiser sur ce compte pour examiner l’alerte. Synchronisation suspendue pour ce compte.')
        else:
            message = tr('Synchronisation : ') + friendly_error(error)
        self.statusBar().showMessage(message)

    def process_due(self):
        if self.quitting or self.due_running or self.offline.isChecked() or not self.accounts:
            return
        from mailclient.core import scheduler
        self.due_running = True
        accounts = list(self.accounts)
        self.send_queue.tick()  # Envois programmés arrivés à échéance : même file, avec progression.
        retry_copies = not self.send_queue.busy()
        def operation():
            events = scheduler.process_snoozes(self.service, accounts)
            copied = scheduler.retry_sent_copies(self.service, accounts) if retry_copies else 0
            return events + ([('copied', count(copied, 'message envoyé', 'messages envoyés'), '')] if copied else [])
        def done(events):
            self.due_running = False
            if not events:
                return
            texts = {'returned': tr('Message reporté de retour'), 'copied': tr('Copie enregistrée dans Envoyés')}
            summary = ' · '.join(f'{texts[kind]} : {subject}' for kind, subject, _ in events)
            self.statusBar().showMessage(summary)
            if self.tray and self.database.setting('notifications', True):
                self.tray.showMessage(tr('Smail'), summary[:240], QSystemTrayIcon.Information, 6000)
            if any(kind == 'returned' for kind, _, _ in events) and not self.busy:
                self.load_messages()
        def failed(message):
            self.due_running = False
            self.statusBar().showMessage(tr('Échéances : ') + message)
        self.runner.run(operation, done, failed)

    def snooze(self):
        rows = self.selected_rows()
        if self.busy or not rows:
            return
        if self.offline.isChecked():
            self.statusBar().showMessage(tr('Reconnectez-vous pour reporter ce message.'))
            return
        if len({row['account'] for row in rows}) > 1:
            self.statusBar().showMessage(tr('Reportez les messages d’un seul compte à la fois.'))
            return
        from mailclient.ui.schedule_dialog import ScheduleDialog
        from mailclient.core import scheduler
        dialog = ScheduleDialog(tr('Reporter'), tr('Le message quitte la réception et y revient, non lu, à l’heure choisie '
                                '(dossier « Reportés » sur le serveur ; Smail doit être ouvert à ce moment-là).'), 'snooze', self)
        if not dialog.exec():
            return
        account, until = self.row_account(rows[0]), dialog.moment
        self.run_and_reload(lambda: scheduler.snooze(self.service, account, rows, until),
                            tr('Reporté jusqu’au {until:%d/%m à %H:%M}.').format(until=until))

    def open_outbox(self):
        from mailclient.ui.outbox_dialog import OutboxDialog
        dialog = OutboxDialog(self.database, self.accounts, self)
        dialog.exec()
        if dialog.reopen:
            self.reopen_draft(dialog.reopen)

    def reopen_draft(self, draft):
        window = ComposeWindow(self.service, self.accounts, draft=draft, parent=self, offline=self.offline.isChecked)
        self.composers.add(window)
        window.show()

    def start_background(self):
        if self.auto_load and not self.offline.isChecked():
            self.timer.start(self.database.setting('sync_minutes', 5) * 60_000)
            self.restart_idle()
            self.due_timer.start()
            QTimer.singleShot(3000, self.process_due)  # Échéances passées pendant la fermeture de Smail.

    def restart_idle(self):
        for thread in self.idle_threads:
            thread.stop()
        self.idle_threads = [thread for thread in self.idle_threads if thread.isRunning()]
        if not self.auto_load or self.quitting or self.offline.isChecked() or not self.database.setting('idle', True):
            return
        for account in self.accounts:
            thread = IdleThread(self.service, account, self)
            thread.changed.connect(self.idle_debounce.start)
            thread.problem.connect(self.background_error)
            self.idle_threads.append(thread)
            thread.start()

    def offline_changed(self, checked):
        if checked:
            self.timer.stop()
            self.due_timer.stop()
            for thread in self.idle_threads:
                thread.stop()
            if self.sync_thread:
                self.sync_thread.stop()
        else:
            self.start_background()
            self.sync_now()
        self.send_queue.tick()  # Hors ligne : les envois attendent ; reconnexion : ils partent.
        self.update_connection()
        self.load_folders()

    def preferences(self, page='Général'):
        if self.busy:
            return
        dialog = SettingsDialog(self.database, self, page)
        if not dialog.exec():
            return
        if dialog.autostart.isEnabled():
            from mailclient.core import autostart
            try:
                if dialog.autostart.isChecked() != autostart.enabled():
                    autostart.set_enabled(dialog.autostart.isChecked())
            except OSError:
                self.notify(tr('Le lancement au démarrage n’a pas pu être modifié.'), kind='error')
        if dialog.conversations.isChecked() != self.conversations_enabled():
            self.conversation_action.setChecked(dialog.conversations.isChecked())  # Enregistre et réaffiche la liste.
        values = dict(sync_minutes=dialog.minutes.value(), cache_limit=dialog.limit.value(), theme=dialog.theme.currentIndex(),
                      idle=dialog.idle.isChecked(), notifications=dialog.notifications.isChecked(), close_to_tray=dialog.tray.isChecked(),
                      ui_style=dialog.style_combo.currentData(),ui_density=dialog.density.currentData(),
                      ui_accent=dialog.accent.currentData(),ui_custom_accent=dialog.custom_accent,
                      ui_reduced_motion=dialog.motion.isChecked(),undo_send_seconds=dialog.undo_send.value(),
                      update_mode=dialog.update_mode.currentData(), auto_update=dialog.update_mode.currentData() != 'off',
                      mark_read_on_open=dialog.mark_read.isChecked(), language=dialog.language.currentData(),
                      backup_reminder=dialog.backup_reminder.isChecked())
        if values['language'] != self.database.setting('language', 'auto'):
            self.notify(tr('La nouvelle langue sera appliquée au prochain démarrage de Smail.'))
        encrypt = dialog.encrypt.isChecked()
        self.set_busy(True)
        def operation():
            if encrypt != self.database.setting('cache_encrypted', False):
                self.database.encrypt_cache(encrypt)
            for key,value in values.items():
                self.database.set_setting(key, value)
        def done(_):
            self.set_busy(False)
            self.apply_theme()
            self.start_background()
            if self.auto_load:
                self.updates.settings_changed()
            self.statusBar().showMessage(tr('Préférences enregistrées.'))
        self.runner.run(operation, done, self.failure)

    def apply_theme(self):
        self.appearance = install_theme(self.database)
        self.reader.set_dark(self.appearance.dark)
        self.folder_delegate.theme = self.appearance
        self.folders.viewport().update()

    def change_style(self, index):
        self.database.set_setting('ui_style',index+1)
        self.appearance.update(variant=index+1)

    def change_density(self, value):
        self.database.set_setting('ui_density',value)
        self.appearance.update(density=value)

    def toggle_theme(self):
        dark = not self.appearance.dark
        self.database.set_setting('theme',int(dark))
        self.appearance.update(dark=dark)

    def refresh_appearance(self):
        if self.reader.disposed:
            return
        self.style_box.blockSignals(True)
        self.style_box.setCurrentIndex(self.appearance.variant-1)
        self.style_box.blockSignals(False)
        self.density_box.blockSignals(True)
        self.density_box.setCurrentIndex(max(0, self.density_box.findData(self.appearance.density)))
        self.density_box.blockSignals(False)
        # Libellé et icône indiquent l’action (vers l’autre thème), pas l’état actuel.
        target, icon_name = (tr(N_('clair')), 'sun') if self.appearance.dark else (tr(N_('sombre')), 'moon')
        self.dark_action.setText(tr('Passer au thème {target}').format(target=target))
        self.dark_action.setIcon(icon(icon_name, self.appearance.colors['text']))
        self.theme_button.setIcon(icon(icon_name, self.appearance.colors['text']))
        self.theme_button.setToolTip(tr('Passer au thème {target} (Ctrl+Maj+L)').format(target=target))
        self.theme_button.setAccessibleName(tr('Passer au thème {target}').format(target=target))
        for number,action in self.style_actions.items():
            action.setChecked(number == self.appearance.variant)
        for name,action in self.density_actions.items():
            action.setChecked(name == self.appearance.density)
        for action,name in self.menu_icons:
            action.setIcon(icon(name,self.appearance.colors['text']))
        self.account_box.setVisible(self.appearance.variant == 1)
        self.account_cards.setVisible(self.appearance.variant == 2)
        self.account_chips.setVisible(self.appearance.variant == 3)
        self.shortcut_hint.setVisible(self.appearance.variant == 3)
        zoom = getattr(self.appearance, 'text_scale', 1.0)
        sizes = {1:[230,430,740],2:[270,420,710],3:[210,475,715]}[self.appearance.variant]
        self.splitter.setSizes([round(sizes[0] * zoom), round(sizes[1] * zoom), sizes[2]])
        self.reader.set_dark(self.appearance.dark)
        self.table.doItemsLayout()
        self.table.viewport().update()
        self.theme_button.icon_name = 'sun' if self.appearance.dark else 'moon'
        self.theme_button.refresh()
        for index in range(self.account_box.count()):
            account = next((a for a in self.accounts if a.id == self.account_box.itemData(index)),None)
            if account:
                secure = account.imap.mode != 'Aucun' and account.smtp.mode != 'Aucun'
                self.account_box.setItemIcon(index,icon('lock-keyhole' if secure else 'lock-keyhole-open',self.appearance.colors['muted' if secure else 'warning']))
        self.update_account_selection()

    def update_account_selection(self):
        self.unified_button.setChecked(self.account_box.currentData() == 'unified')
        for box in (self.account_cards_box,self.account_chips_box):
            for index in range(box.count()):
                button = box.itemAt(index).widget()
                if button:
                    button.setChecked(getattr(button,'account_key',None) == self.account_box.currentData())

    def refresh_account_controls(self):
        for box in (self.account_cards_box,self.account_chips_box):
            while box.count():
                child = box.takeAt(0).widget()
                if child:
                    child.hide()
                    child.deleteLater()
        for account in self.accounts:
            secure = account.imap.mode != 'Aucun' and account.smtp.mode != 'Aucun'
            for box,compact in ((self.account_cards_box,False),(self.account_chips_box,True)):
                text = ''.join(word[0] for word in account.name.split()[:2]).upper() if compact else f'{account.name}\n{account.email}'
                button = Button(text,self.appearance,'lock-keyhole' if secure else 'lock-keyhole-open','Nav',account.name+' · '+account.email)
                button.setCheckable(True)
                button.setChecked(self.account_box.currentData() == account.id)
                button.account_key = account.id
                button.clicked.connect(lambda checked=False,key=account.id:self.select_account(key))
                box.addWidget(button)

    def select_account(self, key):
        if not self.busy:
            self.account_box.setCurrentIndex(self.account_box.findData(key))

    def show_unified(self):
        self.select_account('unified')

    def move_selection(self, delta):
        row = self.table.currentRow()+delta
        while 0 <= row < self.table.count() and self.table.item(row).isHidden():
            row += delta
        if 0 <= row < self.table.count():
            self.table.setCurrentRow(row)

    def user_filter(self, value):
        """Filtre choisi par l’utilisateur : la liste filtrée se complète si elle est trop courte."""
        self.auto_loads = 0  # Avant le filtrage : masquer des lignes peut déjà déclencher un chargement.
        self.filter_page(value)
        QTimer.singleShot(0, self, lambda: self.maybe_load_more(auto=True))

    def filter_page(self, value):
        self.page_filter = value
        visible = 0
        for index in range(self.table.count()):
            item = self.table.item(index)
            view = item.data(Qt.UserRole)
            hidden = (value == 'Non lus' and not view.unread) or (value == 'Pièces jointes' and not view.attachments)
            if self.search.text().strip():
                account_key = self.result_account.currentData()
                hidden = hidden or (account_key is not None and view.raw.get('account') != account_key)
                if self.result_date.currentIndex():
                    from email.utils import parsedate_to_datetime
                    from datetime import datetime
                    try:
                        date = parsedate_to_datetime(view.raw.get('date','')).astimezone().date()
                        age = (datetime.now().astimezone().date()-date).days
                        hidden = hidden or not (age == 0 if self.result_date.currentIndex() == 1 else 0 <= age < 7)
                    except (ValueError,TypeError,OverflowError):
                        hidden = True
            item.setHidden(hidden)
            item.setData(FILTERED_ROLE, hidden)
            visible += not hidden
        current = self.table.currentItem()
        if current and current.isHidden():
            self.table.setCurrentRow(-1)
            self.reader.clear()
        if not self.busy:
            self.list_stack.setCurrentIndex(0 if visible else 2)
        if value != 'Tous':
            self.statusBar().showMessage(tr('{valeur} — filtre limité aux messages chargés.').format(valeur=count(visible, "message visible", "messages visibles")))
        self.refresh_headers()
        self.update_actions()

    def trigger_command(self, title):
        action = next((a for a in self.command_actions if a.text() in (title, tr(title))),None)
        if action and action.isEnabled():
            action.trigger()

    def open_palette(self):
        from mailclient.ui.command_palette import CommandPalette
        commands = [(action.text(),action.shortcut().toString(),lambda a=action:a.trigger() if a.isEnabled() else None)
                    for action in self.command_actions if action.isEnabled()]
        self.palette_dialog = CommandPalette(self.appearance,commands,self)
        self.palette_dialog.open()

    def about_text(self):
        from pathlib import Path
        from mailclient import __version__
        from mailclient.core import updater
        if updater.packaged():
            mode = tr('Microsoft Store — mises à jour installées par le Store')
        elif updater.installed_copy():
            from mailclient.ui.updates import update_mode
            mode = tr('installé — mises à jour : ') + {'ask': tr('proposées, installées après votre accord'), 'auto': tr('automatiques'),
                                                     'off': tr('désactivées')}[update_mode(self.database)]
        else:
            mode = tr('lancé depuis les sources ou un dossier copié — pas de mise à jour automatique')
        return (tr('Smail {version}\n\nClient mail de bureau Windows (IMAP/SMTP).\n\nCette copie : {mode}.\nDonnées locales : {parent}\n\nConfidentialité : {privacy}\nAssistance : {support}\n\nLicence MIT — https://github.com/{REPOSITORY}').format(version=__version__, mode=mode, parent=Path(self.database.path).parent, privacy=PRIVACY_URL, support=SUPPORT_URL, REPOSITORY=updater.REPOSITORY))

    def open_link(self, url):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(url))

    def about(self):
        QMessageBox.about(self, tr('À propos de Smail'), self.about_text())

    def show_update_banner(self, title, description, action_text, callback):
        if self.update_banner is not None:
            self.update_banner.deleteLater()
        self.update_banner = Banner(title, description, self.appearance, icon_name='download', action=action_text)
        if self.update_banner.action is not None and callback:
            self.update_banner.action.clicked.connect(callback)
        self.update_slot.addWidget(self.update_banner)

    def request_quit(self):
        self.quitting = True
        self.close()

    def closeEvent(self, event):
        if not self.quitting and self.tray and self.database.setting('close_to_tray', True):
            self.hide()
            event.ignore()
            return
        self.quitting = True
        self.timer.stop()
        self.due_timer.stop()
        self.idle_debounce.stop()
        for thread in self.idle_threads:
            thread.stop()
        if self.sync_thread:
            self.sync_thread.stop()
        for window in self.composers:
            if window.isVisible():
                window.close()
        for window in list(self.message_windows):
            window.close()
        sending = self.send_queue.flush_for_quit()
        pending = sending or self.busy or self.runner.tasks or any(thread.isRunning() for thread in self.idle_threads) or (self.sync_thread and self.sync_thread.isRunning()) or any(window.isVisible() for window in self.composers)
        if pending:
            self.statusBar().showMessage(tr('Fermeture : envoi du message en cours…') if sending else
                                         tr('Fermeture : attente des connexions et de l’enregistrement des brouillons…'))
            QTimer.singleShot(250, self.close)
            event.ignore()
            return
        self.service.pool.clear()
        if self.tray:
            self.tray.hide()
        self.reader.shutdown()
        event.accept()
        self.updates.install_on_exit()  # Mise à jour téléchargée et vérifiée : installée maintenant, en silence.
        if self.tray:
            QTimer.singleShot(0, QApplication.instance().quit)
