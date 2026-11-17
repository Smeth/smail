"""Client multi-comptes : navigation, actions, cache et synchronisation Qt."""
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QComboBox, QListWidget, QTableWidget, QTableWidgetItem, QSplitter, QHeaderView, QLabel,
    QLineEdit, QCheckBox, QToolBar, QInputDialog, QMessageBox, QSystemTrayIcon, QMenu,
    QStyle, QApplication, QFileDialog, QFrame, QScrollArea, QStackedWidget, QListWidgetItem, QButtonGroup,
    QAbstractItemView)
from PySide6.QtCore import Qt, QTimer, QSaveFile, QIODevice
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
from mailclient.ui.view_models import MessageRow, MessageList

class MainWindow(QMainWindow):
    def __init__(self, database, secrets, tls, auto_load=True):
        super().__init__()
        self.database, self.secrets = database, secrets
        self.service = MailService(database, secrets, tls)
        self.runner = Runner(self, tls)
        self.accounts, self.rows, self.folder_data = [], [], []
        self.page = self.total = 0
        self.busy = self.quitting = self.sync_requested = False
        self.sync_thread = None
        self.idle_threads = []
        self.composers = set()
        self.local_copy = None
        self.auto_load = auto_load
        self.thread_rows, self.thread_account, self.thread_index = [], None, -1
        self.setWindowTitle('Smail — Client mail')
        self.resize(1440, 900)
        self.setMinimumSize(1080,720)
        self.appearance = install_theme(database)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16,14,16,12)
        layout.setSpacing(12)
        self.style_box = QComboBox()
        self.style_box.setAccessibleName('Style de l’interface')
        for number,(name,_) in VARIANTS.items():
            self.style_box.addItem(f'{number} · {name}',number)
        self.style_box.setCurrentIndex(self.appearance.variant-1)
        self.style_box.currentIndexChanged.connect(self.change_style)
        self.theme_button = Button('Clair / sombre',self.appearance,'moon')
        self.theme_button.clicked.connect(self.toggle_theme)
        self.density_box = QComboBox()
        self.density_box.addItems(['Compacte','Normale','Aérée'])
        self.density_box.setAccessibleName('Densité d’affichage')
        self.density_box.setCurrentText(self.appearance.density)
        self.density_box.currentTextChanged.connect(self.change_density)
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
        self.account_box.setAccessibleName('Compte actif')
        self.add = Button('Ajouter un compte',self.appearance,'plus')
        self.refresh = Button('Actualiser',self.appearance,'refresh-cw')
        self.search = QLineEdit()
        self.search.setObjectName('Search')
        self.search.setPlaceholderText('Rechercher dans le dossier : expéditeur, objet, contenu — Entrée')
        self.search.setAccessibleName('Rechercher dans le dossier, Entrée pour lancer')
        self.heading = label('Réception','Title')
        toolbar.addWidget(self.heading)
        toolbar.addWidget(self.search,1)
        self.command_button = Button('Ctrl+K',self.appearance,'command',tooltip='Palette de commandes · Ctrl+K')
        self.command_button.clicked.connect(self.open_palette)
        toolbar.addWidget(self.command_button)
        toolbar.addWidget(self.refresh)
        self.settings_button = Button('',self.appearance,'settings-2',tooltip='Paramètres')
        self.settings_button.clicked.connect(self.preferences)
        toolbar.addWidget(self.settings_button)
        self.offline = QCheckBox('Hors ligne')
        toolbar.addWidget(self.offline)
        header.box.addLayout(toolbar)
        layout.addWidget(header)
        self.security, self.cache_status = QLabel(), QLabel()
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
        layout.addWidget(self.cache_status)
        split = self.splitter = QSplitter()
        split.setChildrenCollapsible(False)
        self.sidebar = Card('Sidebar',14)
        self.sidebar.setMinimumWidth(190)
        self.sidebar.setMaximumWidth(285)
        self.compose_button = Button('Nouveau message',self.appearance,'plus','Primary')
        self.compose_button.clicked.connect(lambda:self.compose())
        self.sidebar.box.addWidget(self.compose_button)
        self.sidebar.box.addWidget(label('VOS ESPACES','Eyebrow'))
        self.sidebar.box.addWidget(self.account_box)
        self.account_cards = QWidget()
        self.account_cards_box = QVBoxLayout(self.account_cards)
        self.account_cards_box.setContentsMargins(0,0,0,0)
        self.account_chips = QWidget()
        self.account_chips_box = QHBoxLayout(self.account_chips)
        self.account_chips_box.setContentsMargins(0,0,0,0)
        self.sidebar.box.addWidget(self.account_cards)
        self.sidebar.box.addWidget(self.account_chips)
        self.unified_button = Button('Réception unifiée',self.appearance,'inbox','Nav')
        self.unified_button.setCheckable(True)
        self.unified_button.clicked.connect(self.show_unified)
        self.sidebar.box.addWidget(self.unified_button)
        self.sidebar.box.addWidget(label('DOSSIERS','Eyebrow'))
        self.folders = QListWidget()
        self.folders.setObjectName('SettingsNav')
        self.folders.setAccessibleName('Dossiers du compte')
        self.sidebar.box.addWidget(self.folders,1)
        self.shortcut_hint = label('J / K  parcourir\nE  archiver   S  étoiler','Small')
        self.sidebar.box.addWidget(self.shortcut_hint)
        self.sidebar.box.addWidget(self.add)
        self.list_panel = Card('ListPanel',8)
        self.list_panel.setMinimumWidth(290)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.page_filter = 'Tous'
        filter_row = QHBoxLayout()
        for title in ('Tous','Non lus','Pièces jointes'):
            button = Button(title,self.appearance,role='Nav')
            button.setCheckable(True)
            button.setChecked(title == 'Tous')
            button.clicked.connect(lambda checked=False,value=title:self.filter_page(value))
            self.filter_group.addButton(button)
            filter_row.addWidget(button)
        self.list_panel.box.addLayout(filter_row)
        self.search_filters = QWidget()
        search_filters = QHBoxLayout(self.search_filters)
        search_filters.setContentsMargins(0,0,0,0)
        self.result_account = QComboBox()
        self.result_account.addItem('Tous les comptes',None)
        self.result_account.setAccessibleName('Filtrer la page par compte')
        self.result_date = QComboBox()
        self.result_date.addItems(['Toutes les dates','Aujourd’hui','7 derniers jours'])
        self.result_date.setAccessibleName('Filtrer la page par date')
        for widget in (self.result_account,self.result_date):
            widget.setToolTip('Filtre limité aux messages chargés de la page courante.')
            widget.currentIndexChanged.connect(lambda index:self.filter_page(self.page_filter))
            search_filters.addWidget(widget,1)
        self.list_panel.box.addWidget(self.search_filters)
        self.search_filters.hide()
        self.search.textChanged.connect(lambda text:self.search_filters.setVisible(bool(text.strip())))
        self.table = MessageList()
        self.table.setAccessibleName('Messages, flèches pour parcourir, Entrée pour lire')
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setMouseTracking(True)
        self.table.setItemDelegate(MailDelegate(self.appearance,self.table))
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.table)
        self.list_stack.addWidget(Skeleton(self.appearance))
        empty = Card(margin=18)
        empty.box.addStretch()
        self.empty_title = label('Aucun message','MessageTitle',True)
        self.empty_description = label('Choisissez un dossier ou ajoutez un compte.','Subtitle',True)
        empty.box.addWidget(self.empty_title)
        empty.box.addWidget(self.empty_description)
        empty.box.addStretch()
        self.list_stack.addWidget(empty)
        self.list_panel.box.addWidget(self.list_stack,1)
        self.reader = MailView()
        for widget in (self.sidebar, self.list_panel, self.reader):
            split.addWidget(widget)
        split.setSizes([230,430,740])
        layout.addWidget(split, 1)
        pagination = QHBoxLayout()
        self.previous = Button('Précédents',self.appearance,'chevron-left')
        self.next = Button('Suivants',self.appearance,'chevron-right')
        self.page_label = QLabel('Aucun message')
        pagination.addWidget(self.previous)
        pagination.addWidget(self.page_label, 1)
        pagination.addWidget(self.next)
        layout.addLayout(pagination)
        self.setCentralWidget(root)
        self.menuBar().setNativeMenuBar(False)
        file_menu = self.menuBar().addMenu('Fichier')
        actions = self.menuBar().addMenu('Message')
        view_menu = self.menuBar().addMenu('Affichage')
        accounts_menu = self.menuBar().addMenu('Comptes')
        tools_menu = self.menuBar().addMenu('Outils')
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
                else:
                    item.setShortcut(shortcut)
            (menu or actions).addAction(item)
            if icon_name:
                self.menu_icons.append((item,icon_name))
            self.command_actions.append(item)
            if needs_message:
                self.message_actions.append(item)
            return item
        action('Rédiger', self.compose, 'Ctrl+N', menu=file_menu, icon_name='plus')
        file_menu.addSeparator()
        # Répondre et transférer exigent un seul message ; les autres actions acceptent une sélection multiple.
        self.single_actions = [
            action('Répondre', lambda: self.compose('reply'), 'Ctrl+R', True, icon_name='reply'),
            action('Répondre à tous', lambda: self.compose('reply_all'), 'Ctrl+Shift+R', True, icon_name='reply-all'),
            action('Transférer', lambda: self.compose('forward'), 'Ctrl+L', True, icon_name='forward')]
        actions.addSeparator()
        action('Lu / non lu', self.toggle_read, needs_message=True, icon_name='mail')
        action('Étoiler', self.toggle_star, needs_message=True, icon_name='star')
        actions.addSeparator()
        action('Déplacer', lambda: self.move('move'), needs_message=True, icon_name='folder')
        action('Archiver', lambda: self.move('archive'), needs_message=True, icon_name='archive')
        action('Supprimer', lambda: self.move('trash'), 'Delete', True, icon_name='trash-2')
        actions.addSeparator()
        self.mark_all_action = action('Tout marquer comme lu', self.mark_all_read, 'Ctrl+Shift+U', icon_name='check')
        folder_menu = accounts_menu.addMenu('Dossier')
        self.folder_actions = {
            'create': action('Nouveau dossier…', lambda: self.manage_folder('create'), menu=folder_menu, icon_name='folder'),
            'rename': action('Renommer le dossier…', lambda: self.manage_folder('rename'), menu=folder_menu, icon_name='file-pen-line'),
            'delete': action('Supprimer le dossier…', lambda: self.manage_folder('delete'), menu=folder_menu, icon_name='trash-2'),
            'empty': action('Vider le dossier…', self.empty_folder, menu=folder_menu, icon_name='trash-2')}
        action('Brouillons locaux', self.open_draft, menu=file_menu, icon_name='file-pen-line')
        action('Envoyés locaux', self.open_sent_copy, menu=file_menu, icon_name='send')
        action('Exporter .eml', self.export_sent_copy, menu=file_menu, icon_name='download')
        file_menu.addSeparator()
        action('Quitter', self.request_quit, 'Ctrl+Q', menu=file_menu)
        action('Ajouter un compte', self.add_account, menu=accounts_menu, icon_name='plus')
        action('Compte', self.edit_account, menu=accounts_menu, icon_name='settings-2')
        self.delete_account_action = action('Supprimer le compte…', self.delete_account, menu=accounts_menu, icon_name='trash-2')
        self.offline_action = action('Hors ligne',self.offline.click,menu=accounts_menu)
        self.offline_action.setCheckable(True)
        self.offline.toggled.connect(self.offline_action.setChecked)
        action('Synchroniser', self.sync_now, 'F5', menu=tools_menu, icon_name='refresh-cw')
        tools_menu.addSeparator()
        action('Préférences', self.preferences, 'Ctrl+,', menu=tools_menu, icon_name='settings-2')
        action('Rechercher', self.search.setFocus, 'Ctrl+F', menu=view_menu, icon_name='search')
        action('Palette de commandes', self.open_palette, 'Ctrl+K', menu=view_menu, icon_name='command')
        view_menu.addSeparator()
        self.conversation_action = QAction('Regrouper par conversation', self)
        self.conversation_action.setCheckable(True)
        self.conversation_action.setChecked(self.conversations_enabled())
        self.conversation_action.setShortcut('Ctrl+Shift+T')
        self.conversation_action.toggled.connect(self.toggle_conversations)
        view_menu.addAction(self.conversation_action)
        self.command_actions.append(self.conversation_action)
        self.dark_action = action('Thème sombre', self.toggle_theme, 'Ctrl+Shift+L', menu=view_menu, icon_name='moon')
        self.dark_action.setCheckable(True)
        self.style_actions = {}
        style_menu = view_menu.addMenu('Style de l’interface')
        style_group = QActionGroup(self)
        style_group.setExclusive(True)
        for number,(name,_) in VARIANTS.items():
            item = action(name,lambda value=number:self.style_box.setCurrentIndex(value-1),menu=style_menu)
            item.setCheckable(True)
            style_group.addAction(item)
            self.style_actions[number] = item
        self.density_actions = {}
        density_menu = view_menu.addMenu('Densité')
        density_group = QActionGroup(self)
        density_group.setExclusive(True)
        for name in ('Compacte','Normale','Aérée'):
            item = action(name,lambda value=name:self.density_box.setCurrentText(value),menu=density_menu)
            item.setCheckable(True)
            density_group.addAction(item)
            self.density_actions[name] = item
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_message_menu)
        self.folders.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folders.customContextMenuRequested.connect(self.show_folder_menu)
        self.add.clicked.connect(self.add_account)
        self.refresh.clicked.connect(self.load_folders)
        self.account_box.currentIndexChanged.connect(self.load_folders)
        self.folders.currentRowChanged.connect(self.folder_changed)
        self.previous.clicked.connect(lambda: self.change_page(-1))
        self.next.clicked.connect(lambda: self.change_page(1))
        self.search.returnPressed.connect(self.new_search)
        self.offline.toggled.connect(self.offline_changed)
        self.table.itemSelectionChanged.connect(self.read_selected)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.table.itemActivated.connect(lambda item:self.reader.tabs.setFocus())
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
        self.reader.starRequested.connect(lambda:self.trigger_command('Étoiler'))
        self.reader.readRequested.connect(lambda:self.trigger_command('Lu / non lu'))
        self.reader.threadMessageRequested.connect(self.open_thread_message)
        # Parcours de la conversation au clavier, sans quitter la liste.
        QShortcut(QKeySequence('Alt+Down'),self,activated=lambda:self.step_thread(1))
        QShortcut(QKeySequence('Alt+Up'),self,activated=lambda:self.step_thread(-1))
        self.appearance.changed.connect(self.refresh_appearance)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync_now)
        self.idle_debounce = QTimer(self)
        self.idle_debounce.setSingleShot(True)
        self.idle_debounce.setInterval(2000)
        self.idle_debounce.timeout.connect(self.sync_now)
        self.tray = None
        if auto_load and QApplication.platformName() != 'offscreen' and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QApplication.windowIcon() if not QApplication.windowIcon().isNull() else self.style().standardIcon(QStyle.SP_MessageBoxInformation), self)
            self.tray.setToolTip('Smail')
            menu = QMenu(self)
            menu.addAction('Ouvrir Smail', self.show_normal)
            menu.addAction('Synchroniser', self.sync_now)
            menu.addAction('Quitter', self.request_quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.show_normal() if reason == QSystemTrayIcon.DoubleClick else None)
            self.tray.show()
            QApplication.instance().setQuitOnLastWindowClosed(False)
        self.apply_theme()
        if auto_load:
            self.reload_accounts()
            self.start_background()
            QTimer.singleShot(1500, self.sync_now)
        else:
            self.set_busy(False)

    def show_normal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_message_menu(self, position):
        item = self.table.itemAt(position)
        if item is None or self.busy:
            return
        if not item.isSelected():
            self.table.setCurrentItem(item)
        self.update_actions()
        menu = QMenu(self.table)
        for index,action in enumerate(self.message_actions):
            if index in (3,5):
                menu.addSeparator()
            menu.addAction(action)
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
                     'junk': ('spam', 'junk', 'indésirable')}

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
            self.statusBar().showMessage(message(result) if callable(message) else message)
            self.load_folders() if reload_folders else self.load_messages()
        self.runner.run(operation, done, self.failure)

    def mark_all_read(self):
        if self.busy:
            return
        if self.offline.isChecked():
            self.statusBar().showMessage('Reconnectez-vous pour modifier les messages du serveur.')
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
        self.run_and_reload(operation, lambda count: f'{count} message(s) marqué(s) comme lu(s).')

    def empty_folder(self):
        current = self.current_folder()
        if self.busy or not current:
            return
        name, label = current
        if not (self.is_special(name,label,'trash') or self.is_special(name,label,'junk')):
            self.statusBar().showMessage('Seuls la corbeille et le dossier spam peuvent être vidés.')
            return
        if self.offline.isChecked():
            self.statusBar().showMessage('Reconnectez-vous pour vider ce dossier.')
            return
        if QMessageBox.warning(self, 'Vider le dossier', f'Supprimer définitivement tous les messages de « {label} » ?\n\nCette action est irréversible.',
                               QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        account = self.account()
        self.run_and_reload(lambda: self.service.empty_folder(account, name), lambda count: f'{count} message(s) supprimé(s) définitivement.')

    def manage_folder(self, operation):
        account = self.account()
        if self.busy or account is None:
            self.statusBar().showMessage('Choisissez d’abord un compte (pas la réception unifiée).')
            return
        if self.offline.isChecked():
            self.statusBar().showMessage('Reconnectez-vous pour gérer les dossiers.')
            return
        current = self.current_folder()
        if operation == 'create':
            name, ok = QInputDialog.getText(self, 'Nouveau dossier', 'Nom du dossier (utilisez le séparateur du serveur, souvent / ou ., pour un sous-dossier)')
            if not ok or not name.strip():
                return
            self.run_and_reload(lambda: self.service.manage_folder(account, 'create', name), f'Dossier « {name.strip()} » créé.', True)
            return
        if not current:
            return
        name, label = current
        if name.upper() == 'INBOX' or label in self.PROTECTED:
            self.statusBar().showMessage('Les dossiers système (réception, envoyés, brouillons, corbeille, spam) ne peuvent pas être modifiés.')
            return
        if operation == 'rename':
            from mailclient.core.parser import decode_folder
            new_name, ok = QInputDialog.getText(self, 'Renommer le dossier', 'Nouveau nom', text=decode_folder(name))
            if not ok or not new_name.strip() or new_name.strip() == decode_folder(name):
                return
            self.run_and_reload(lambda: self.service.manage_folder(account, 'rename', name, new_name), 'Dossier renommé.', True)
        elif operation == 'delete':
            if QMessageBox.warning(self, 'Supprimer le dossier', f'Supprimer le dossier « {label} » et tous les messages qu’il contient sur le serveur ?\n\nCette action est irréversible.',
                                   QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
                return
            self.run_and_reload(lambda: self.service.manage_folder(account, 'delete', name), f'Dossier « {label} » supprimé.', True)

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
            self.account_box.addItem('Tous les comptes — Réception unifiée', 'unified')
        for account in self.accounts:
            secure = account.imap.mode != 'Aucun' and account.smtp.mode != 'Aucun'
            self.account_box.addItem(icon('lock-keyhole' if secure else 'lock-keyhole-open',self.appearance.colors['muted' if secure else 'warning']),
                                     f'{account.name} — {account.email}',account.id)
        index = self.account_box.findData(previous)
        self.account_box.setCurrentIndex(index if index >= 0 else 1 if self.accounts else -1)
        self.account_box.blockSignals(False)
        self.result_account.blockSignals(True)
        self.result_account.clear()
        self.result_account.addItem('Tous les comptes',None)
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
        account = self.choose_account('Compte')
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
        name, ok = QInputDialog.getItem(self, title, 'Choisissez le compte', names, 0, False)
        return self.accounts[names.index(name)] if ok else None

    def delete_account(self, account=None):
        if self.busy or not self.accounts:
            return False
        account = account or self.choose_account('Supprimer le compte')
        if account is None:
            return False
        if any(window.isVisible() for window in self.composers):
            QMessageBox.information(self, 'Supprimer le compte', 'Fermez d’abord les fenêtres de rédaction ouvertes.')
            return False
        text = (f'Supprimer le compte « {account.name} » ({account.email}) de Smail ?\n\n'
                'Vos messages restent sur le serveur. Seront effacés de ce PC : les paramètres du compte, le cache hors ligne, '
                'les brouillons locaux, les copies locales des messages envoyés, les certificats approuvés et les mots de passe '
                'ou jetons OAuth2 du Gestionnaire d’identifiants Windows.\n\nCette action est irréversible.')
        box = QMessageBox(QMessageBox.Warning, 'Supprimer le compte', text, QMessageBox.Yes | QMessageBox.Cancel, self)
        box.button(QMessageBox.Yes).setText('Supprimer le compte')
        box.button(QMessageBox.Cancel).setText('Annuler')
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
                        lambda _: finish(f'Compte « {account.name} » supprimé de ce PC.'), finish)
        return True

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.account_box, self.add, self.refresh, self.folders, self.table, self.search, self.offline):
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
        self.previous.setEnabled(not busy and self.page > 0)
        self.next.setEnabled(not busy and (self.page+1)*50 < self.total)
        self.update_actions()

    def update_actions(self):
        self.offline_action.setEnabled(self.offline.isEnabled())
        self.delete_account_action.setEnabled(not self.busy and bool(self.accounts))
        selected, single = bool(self.selected_rows()), self.selected_row() is not None
        for action in self.message_actions:
            action.setEnabled(not self.busy and (single if action in self.single_actions else selected))
        self.reader.set_actions_enabled(not self.busy and single)
        online = not self.busy and not self.offline.isChecked()
        current = self.current_folder()
        self.mark_all_action.setEnabled(online and bool(self.accounts) and (current is not None or self.account() is None))
        self.folder_actions['create'].setEnabled(online and self.account() is not None)
        editable = current is not None and current[0].upper() != 'INBOX' and current[1] not in self.PROTECTED
        self.folder_actions['rename'].setEnabled(online and editable)
        self.folder_actions['delete'].setEnabled(online and editable)
        self.folder_actions['empty'].setEnabled(online and current is not None and
                                                (self.is_special(*current,'trash') or self.is_special(*current,'junk')))

    def failure(self, message):
        self.set_busy(False)
        self.statusBar().showMessage(message)
        if not self.rows:
            self.empty_title.setText('Connexion ou opération indisponible')
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
        self.search.clear()
        account = self.account()
        self.heading.setText(account.name if account else 'Réception unifiée' if self.accounts else 'Bienvenue')
        warning = account and (account.imap.mode == 'Aucun' or account.smtp.mode == 'Aucun')
        unsafe = [a.name for a in self.accounts if a.imap.mode == 'Aucun' or a.smtp.mode == 'Aucun']
        text = 'Connexion en clair : votre mot de passe et vos mails peuvent être lus par des tiers.' if warning else \
               'Compte(s) non chiffré(s) à vérifier : '+', '.join(unsafe) if account is None and unsafe else ''
        self.security.setText(text)
        self.security_frame.setVisible(bool(text))
        if not self.accounts:
            self.set_busy(False)
            self.statusBar().showMessage('Ajoutez un compte pour commencer.')
            return
        if account is None:
            self.folder_data = [('INBOX', 'Réception unifiée')]
            self.folders.addItem('Réception unifiée')
            self.folders.setCurrentRow(0)
            return
        self.set_busy(True)
        def done(result):
            folders, offline = result
            self.folder_data = folders
            self.folders.blockSignals(True)
            self.folders.addItems([label for _, label in folders])
            self.folders.blockSignals(False)
            self.set_busy(False)
            self.cache_status.setText('Dossiers du cache hors ligne' if offline else 'Connecté au serveur')
            if folders:
                index = next((i for i,(name,_) in enumerate(folders) if name.upper() == 'INBOX'), 0)
                self.folders.setCurrentRow(index)
            else:
                self.empty_title.setText('Aucun dossier disponible')
                self.empty_description.setText('Reconnectez-vous puis actualisez pour charger les dossiers.' if offline else 'Le serveur ne propose aucun dossier sélectionnable.')
        offline = self.offline.isChecked()
        self.runner.run(lambda: self.service.folders(account, offline), done, self.failure)

    def folder_changed(self, index):
        if index >= 0 and not self.busy:
            if index < len(self.folder_data):
                self.heading.setText(self.folder_data[index][1])
            self.page = 0
            self.load_messages()

    def new_search(self):
        self.page = 0
        self.load_messages()

    def change_page(self, offset):
        self.page = max(0, self.page + offset)
        self.load_messages()

    def load_messages(self, cache_only=False):
        index = self.folders.currentRow()
        if self.busy or self.quitting or index < 0:
            return
        self.reader.clear()
        self.local_copy = None
        self.rows = []
        self.table.setRowCount(0)
        account, query, page = self.account(), self.search.text().strip(), self.page
        self.set_busy(True)
        def done(result):
            self.rows, self.total = result['rows'], result['total']
            self.render_rows()
            conversations = self.table.count()
            grouped = f' · {conversations} conversation(s) sur cette page' if conversations != len(self.rows) else ''
            self.page_label.setText(f'Page {page+1} — {self.total} message(s), 50 par page{grouped}')
            self.cache_status.setText('Cache local — recherche limitée aux messages synchronisés' if result['offline'] else 'Serveur — recherche dans tout le dossier')
            if not self.rows and result['offline'] and self.total:
                self.cache_status.setText('Cette page n’est pas encore en cache. Reconnectez-vous ou augmentez la limite dans Préférences.')
            self.set_busy(False)
            self.filter_page(self.page_filter)
            self.empty_title.setText('Aucun résultat' if query else 'Aucun message')
            self.empty_description.setText('Essayez un autre terme ou retirez un filtre.' if query else 'Ce dossier ne contient aucun message disponible.')
            if not self.rows and result['offline'] and self.total:
                self.empty_title.setText('Page non téléchargée')
                self.empty_description.setText(self.cache_status.text())
        offline = self.offline.isChecked() or cache_only
        folder = self.folder_data[index][0]
        if account:
            operation = lambda: self.service.messages(account, folder, page, query, offline)
        else:
            accounts = list(self.accounts)
            operation = lambda: self.service.unified(accounts, page, query)
        self.runner.run(operation, done, self.failure)

    def conversations_enabled(self):
        return bool(self.database.setting('conversation_view', True))

    def toggle_conversations(self, checked):
        self.database.set_setting('conversation_view', bool(checked))
        if not self.busy:
            self.reader.clear()
            self.render_rows()
            self.filter_page(self.page_filter)

    def render_rows(self):
        """Une ligne par conversation (ou par message si le regroupement est désactivé)."""
        from mailclient.core.threads import group_threads
        self.table.blockSignals(True)
        self.table.clear()
        groups = group_threads(self.rows) if self.conversations_enabled() else [[row] for row in self.rows]
        for group in groups:
            row = group[0]
            row_account = self.row_account(row)
            view = MessageRow.from_thread(group,row_account)
            item = QListWidgetItem(f'{view.sender} · {view.subject} · {view.preview} · {view.time}'
                                   + (f' · {view.count} messages' if view.count > 1 else ''))
            item.setData(Qt.UserRole,view)
            item.setToolTip(f'{row["sender"]}\n{view.subject}\n{view.account_name}\n{row["date"]}'
                            + (f'\nConversation de {view.count} messages dans cette page' if view.count > 1 else ''))
            self.table.addItem(item)
        self.table.blockSignals(False)

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
        return (f'{who} · {View.from_row(row).time}{where}', bool(row.get('unread')), f'{row.get("sender","")}\n{row.get("subject","")}\n{row.get("date","")}')

    def thread_elsewhere(self):
        listed = {(row.get('account'), row.get('folder'), row.get('uid')) for row in self.rows}
        return sum((row.get('account'), row.get('folder'), row.get('uid')) not in listed for row in self.thread_rows)

    def step_thread(self, delta):
        if self.reader.thread_card.isVisible():
            self.open_thread_message(self.thread_index + delta)

    def open_thread_message(self, index):
        """Clic dans le bandeau de conversation : affiche ce message sans quitter la conversation."""
        if self.busy or not 0 <= index < len(self.thread_rows):
            return
        row, account = self.thread_rows[index], self.thread_account
        self.reader.clear('Chargement du message…', keep_thread=True)
        self.set_busy(True)
        offline = self.offline.isChecked()
        def done(mail):
            self.thread_index = index
            self.reader.display(mail, keep_thread=True)
            self.reader.set_thread([self.thread_entry(r, account) for r in self.thread_rows], index, self.thread_elsewhere())
            self.set_busy(False)
        def failed(message):
            self.reader.clear(message, keep_thread=True)
            self.failure(message)
        self.runner.run(lambda: self.service.message(account, row, offline), done, failed)

    def read_selected(self):
        view = self.selected_view()
        row = view.raw if view else None
        if self.busy:
            return
        if not row:
            count = len(self.selected_rows())
            if count > 1:
                self.reader.clear(f'{count} messages sélectionnés')
            return
        account = self.row_account(row)
        self.reader.clear('Chargement du message…')
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
            self.reader.display(mail, keep_thread=True)
            self.reader.set_thread([self.thread_entry(r, account) for r in messages] if len(messages) > 1 else [], index, self.thread_elsewhere())
            current = self.table.currentItem()
            if current and current.data(Qt.UserRole).raw is row and messages[index] is row and mail.text:
                from dataclasses import replace
                view = current.data(Qt.UserRole)
                view = replace(view,preview=' '.join(mail.text.split())[:180])
                current.setData(Qt.UserRole,view)
                current.setText(f'{view.sender} · {view.subject} · {view.preview} · {view.time}')
            self.set_busy(False)
            fade(self.reader.headers,self.appearance)
            self.statusBar().showMessage('Message chargé ; images distantes bloquées par défaut.')
        def failed(message):
            self.reader.clear(message)
            self.failure(message)
        self.runner.run(operation, done, failed)

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
            self.statusBar().showMessage('Reconnectez-vous pour modifier les messages du serveur.')
            return
        if any(account is None for account,*_ in plan):
            self.statusBar().showMessage('Le compte de ce message n’existe plus. Actualisez.')
            return
        self.set_busy(True)
        def operation():
            for account, group, step, destination in plan:
                self.service.action(account, group, step, destination)
        def done(_):
            self.set_busy(False)
            self.load_messages()
        def failed(message):
            self.failure(message + ' Actualisez les dossiers source et destination avant de réessayer : l’action peut avoir été acceptée avant une coupure.')
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
            self.statusBar().showMessage('Pour déplacer, sélectionnez des messages d’un seul compte.')
            return
        plan = []
        for group in groups.values():
            account = self.row_account(group[0])
            if account is None:
                self.statusBar().showMessage('Le compte de ce message n’existe plus. Actualisez.')
                return
            folders = self.database.cache_get('folders', account.id, [])
            source = group[0]['folder']
            source_label = next((label for name,label in folders if name == source), source)
            if kind in self.SPECIAL_WORDS and self.is_special(source, source_label, kind):
                if kind != 'trash':
                    self.statusBar().showMessage('Ce message est déjà dans le dossier de destination.')
                    return
                plan.append((account, group, 'delete', ''))  # Depuis la corbeille : suppression définitive.
                continue
            target = self.special_folder(folders, kind, exclude=source) if kind in self.SPECIAL_WORDS else None
            if target is None:
                choices = [(name, label) for name,label in folders if name != source]
                if not choices:
                    self.statusBar().showMessage('Aucun autre dossier disponible. Créez un dossier (Comptes › Dossier) puis réessayez.')
                    return
                labels = [label + ' — ' + name for name,label in choices]
                choice, ok = QInputDialog.getItem(self, 'Destination', f'Choisissez le dossier de destination ({account.name})', labels, 0, False)
                if not ok:
                    return
                target = choices[labels.index(choice)][0]
            plan.append((account, group, 'move', target))
        count = len(rows)
        subject = 'ce message' if count == 1 else f'ces {count} messages'
        if any(step == 'delete' for _,_,step,_ in plan):
            if QMessageBox.warning(self, 'Supprimer définitivement', f'Supprimer définitivement {subject} de la corbeille ?\n\nCette action est irréversible.',
                                   QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
                return
        elif kind == 'trash' and QMessageBox.question(self, 'Déplacer dans la corbeille', f'Déplacer {subject} dans la corbeille ?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.mutate(None, plan=plan)

    def compose(self, mode=None):
        if not self.accounts:
            self.statusBar().showMessage('Ajoutez un compte avant de rédiger.')
            return
        row = self.selected_row()
        account = self.row_account(row) if row else self.account() or self.accounts[0]
        fields = None
        if mode:
            if not self.reader.mail or not row:
                self.statusBar().showMessage('Sélectionnez et chargez d’abord le message.')
                return
            fields = reply_fields(self.reader.mail, account, mode)
        window = ComposeWindow(self.service, self.accounts, account, fields, parent=self, offline=self.offline.isChecked)
        self.composers.add(window)
        window.show()

    def open_draft(self):
        if not self.accounts or self.busy:
            return
        self.set_busy(True)
        def done(drafts):
            self.set_busy(False)
            if not drafts:
                self.statusBar().showMessage('Aucun brouillon local.')
                return
            labels = [f'{draft.get("subject") or "(Sans objet)"} — {draft.get("to", "")} [{i+1}]' for i,draft in enumerate(drafts)]
            label, ok = QInputDialog.getItem(self, 'Brouillons locaux', 'Ouvrir un brouillon', labels, 0, False)
            if not ok:
                return
            draft = drafts[labels.index(label)]
            if not any(a.id == draft['account'] for a in self.accounts):
                self.statusBar().showMessage('Le compte de ce brouillon n’existe plus.')
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
                self.statusBar().showMessage('Aucun message envoyé localement depuis cette installation.')
                return
            labels = [f'{mail.subject} — {mail.date} [{i+1}]' for i,(_,mail) in enumerate(copies)]
            label, ok = QInputDialog.getItem(self, 'Envoyés locaux', 'Lire une copie déjà envoyée', labels, 0, False)
            if not ok:
                return
            self.local_copy, mail = copies[labels.index(label)]
            self.rows = []
            self.table.setRowCount(0)
            self.reader.display(mail)
            self.update_actions()
            self.cache_status.setText('Copie locale d’un message déjà envoyé — utilisez Exporter .eml pour la sauvegarder.')
        self.runner.run(operation, done, self.failure)

    def export_sent_copy(self):
        if self.busy or not self.local_copy:
            self.statusBar().showMessage('Ouvrez d’abord une copie dans Envoyés locaux.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Exporter le message déjà envoyé', 'message.eml', 'Message e-mail (*.eml)')
        if not path:
            return
        import base64
        raw = self.local_copy['raw']
        self.set_busy(True)
        def operation():
            data = base64.b64decode(raw)
            output = QSaveFile(path)
            if not output.open(QIODevice.WriteOnly) or output.write(data) != len(data) or not output.commit():
                raise RuntimeError('Impossible d’exporter ce message à cet emplacement.')
        def done(_):
            self.set_busy(False)
            self.statusBar().showMessage('Copie .eml exportée.')
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
            self.tray.showMessage('Smail', f'{count} nouveau(x) message(s)', QSystemTrayIcon.Information, 6000)
        self.statusBar().showMessage('Synchronisation terminée. Les derniers messages sont disponibles hors ligne.')
        if self.account() is None and not self.busy:
            self.load_messages(cache_only=True)

    def background_error(self, error):
        if isinstance(error, CertificateAlert):
            message = 'Certificat à vérifier : utilisez Actualiser sur ce compte pour examiner l’alerte. Synchronisation suspendue pour ce compte.'
        else:
            message = 'Synchronisation : ' + friendly_error(error)
        self.statusBar().showMessage(message)

    def start_background(self):
        if self.auto_load and not self.offline.isChecked():
            self.timer.start(self.database.setting('sync_minutes', 5) * 60_000)
            self.restart_idle()

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
            for thread in self.idle_threads:
                thread.stop()
            if self.sync_thread:
                self.sync_thread.stop()
        else:
            self.start_background()
            self.sync_now()
        self.load_folders()

    def preferences(self):
        if self.busy:
            return
        dialog = SettingsDialog(self.database, self)
        if not dialog.exec():
            return
        values = dict(sync_minutes=dialog.minutes.value(), cache_limit=dialog.limit.value(), theme=dialog.theme.currentIndex(),
                      idle=dialog.idle.isChecked(), notifications=dialog.notifications.isChecked(), close_to_tray=dialog.tray.isChecked(),
                      ui_style=dialog.style_combo.currentData(),ui_density=dialog.density.currentText(),
                      ui_accent=dialog.accent.currentText(),ui_custom_accent=dialog.custom_accent,
                      ui_reduced_motion=dialog.motion.isChecked())
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
            self.statusBar().showMessage('Préférences enregistrées.')
        self.runner.run(operation, done, self.failure)

    def apply_theme(self):
        self.appearance = install_theme(self.database)
        self.reader.set_dark(self.appearance.dark)

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
        self.density_box.setCurrentText(self.appearance.density)
        self.density_box.blockSignals(False)
        self.dark_action.setChecked(self.appearance.dark)
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
        for shortcut in self.quick_keys:
            shortcut.setEnabled(self.appearance.variant == 3)
        self.splitter.setSizes({1:[230,430,740],2:[270,420,710],3:[210,475,715]}[self.appearance.variant])
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
            visible += not hidden
        current = self.table.currentItem()
        if current and current.isHidden():
            self.table.setCurrentRow(-1)
            self.reader.clear()
        if not self.busy:
            self.list_stack.setCurrentIndex(0 if visible else 2)
        if value != 'Tous':
            self.statusBar().showMessage(f'{visible} message(s) visible(s) — filtre limité à la page courante.')
        self.update_actions()

    def trigger_command(self, title):
        action = next((a for a in self.command_actions if a.text() == title),None)
        if action and action.isEnabled():
            action.trigger()

    def open_palette(self):
        from mailclient.ui.command_palette import CommandPalette
        commands = [(action.text(),action.shortcut().toString(),lambda a=action:a.trigger() if a.isEnabled() else None)
                    for action in self.command_actions if action.isEnabled()]
        self.palette_dialog = CommandPalette(self.appearance,commands,self)
        self.palette_dialog.open()

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
        self.idle_debounce.stop()
        for thread in self.idle_threads:
            thread.stop()
        if self.sync_thread:
            self.sync_thread.stop()
        for window in self.composers:
            if window.isVisible():
                window.close()
        pending = self.busy or self.runner.tasks or any(thread.isRunning() for thread in self.idle_threads) or (self.sync_thread and self.sync_thread.isRunning()) or any(window.isVisible() for window in self.composers)
        if pending:
            self.statusBar().showMessage('Fermeture : attente des connexions et de l’enregistrement des brouillons…')
            QTimer.singleShot(250, self.close)
            event.ignore()
            return
        self.service.pool.clear()
        if self.tray:
            self.tray.hide()
        self.reader.shutdown()
        event.accept()
        if self.tray:
            QTimer.singleShot(0, QApplication.instance().quit)
