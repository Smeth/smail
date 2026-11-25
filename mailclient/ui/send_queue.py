"""Envoi en arrière-plan : la rédaction se ferme aussitôt, la progression s’affiche en bas de la fenêtre principale.

Chaque message passe par la boîte d’envoi locale (scheduler) : délai d’annulation, puis envoi un par un.
Les règles de sûreté restent celles de la boîte d’envoi : état « sending » enregistré avant SMTP, jamais de
renvoi automatique, échec et envoi incertain conservés dans Fichier › Boîte d’envoi."""
from mailclient.i18n import tr
import logging
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QSystemTrayIcon, QWidget
from mailclient.core import scheduler
from mailclient.ui.components import Button, safe_rich

log = logging.getLogger('smail')


def megabytes(size):
    return f'{size / 1_000_000:.1f}'.replace('.', ',')


class Signals(QObject):
    progress = Signal(str, object, object)
    done = Signal(object)
    error = Signal(str)


class SendTask(QRunnable):
    def __init__(self, service, account, item):
        super().__init__()
        self.service, self.account, self.item = service, account, item
        self.signals = Signals()

    def run(self):
        try:
            event = scheduler.deliver_item(self.service, self.account, self.item,
                                           lambda stage, done, total: self.signals.progress.emit(stage, done, total))
        except Exception as error:  # Erreur hors SMTP (cache…) : l’état « sending » reste, rendu « incertain » au démarrage.
            log.warning('Envoi en arrière-plan interrompu (%s)', type(error).__name__)
            self.signals.error.emit(type(error).__name__)
        else:
            self.signals.done.emit(event)


class SendQueue(QObject):
    def __init__(self, window, service, database):
        super().__init__(window)
        self.window, self.service, self.database = window, service, database
        self.task = None          # (identifiant, sujet) du message en cours d’envoi.
        self.stage = None         # Dernière étape signalée par la tâche.
        self.alert = None         # (texte, infobulle) d’un échec, affiché jusqu’à « Voir » ou ×.
        self.widget = QWidget()
        self.widget.setAccessibleName(tr('Envoi en cours'))
        row = QHBoxLayout(self.widget)
        row.setContentsMargins(0, 0, 0, 0)
        self.text = QLabel()
        self.bar = QProgressBar()
        self.bar.setFixedWidth(150)
        self.bar.setTextVisible(False)
        self.bar.setMaximumHeight(8)
        self.cancel_button = Button(tr('Annuler'), window.appearance, 'x', 'Secondary', tr('Annuler l’envoi et rouvrir le message'))
        self.show_button = Button(tr('Voir'), window.appearance, 'clock', 'Secondary', tr('Ouvrir Fichier › Boîte d’envoi'))
        self.dismiss_button = Button('', window.appearance, 'x', 'Secondary', tr('Masquer'))
        for button in (self.cancel_button, self.show_button, self.dismiss_button):
            button.setMinimumHeight(26)
        self.cancel_button.clicked.connect(self.cancel)
        self.show_button.clicked.connect(self.show_outbox)
        self.dismiss_button.clicked.connect(self.dismiss)
        for widget in (self.text, self.bar, self.cancel_button, self.show_button, self.dismiss_button):
            row.addWidget(widget)
        window.statusBar().addPermanentWidget(self.widget)
        self.widget.hide()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)

    # File d’attente ---------------------------------------------------------------------------

    def enqueue(self, account, state, files, delay, item_id):
        scheduler.enqueue(self.database, account, state, files, delay, item_id)
        self.alert = None
        self.tick()

    def waiting(self):
        """Envois immédiats encore dans leur délai d’annulation (ou en attente de connexion)."""
        return [item for item in scheduler.outbox(self.database) if item.get('immediate') and item.get('status') == 'scheduled'
                and (self.task is None or item['id'] != self.task[0])]

    def busy(self):
        return self.task is not None

    def tick(self):
        self.kick()
        self.render()
        active = self.task is not None or bool(self.waiting())
        if active and not self.timer.isActive():
            self.timer.start()
        elif not active:
            self.timer.stop()

    def kick(self):
        if self.task is not None or self.window.offline.isChecked():
            return
        accounts = {account.id: account for account in self.window.accounts}
        item = next((item for item in scheduler.due(self.database) if item['account'] in accounts), None)
        if item is None:
            return
        subject = item['state'].get('subject') or tr('(Sans objet)')
        self.task, self.stage = (item['id'], subject), ('connect', 0, 0)
        self.origin = item['state'].get('origin')
        task = SendTask(self.service, accounts[item['account']], item)
        task.signals.progress.connect(self.progress)
        task.signals.done.connect(self.finished)
        task.signals.error.connect(self.crashed)
        self.current_task = task  # Garde les signaux en vie jusqu’à la fin.
        QThreadPool.globalInstance().start(task)

    def flush_for_quit(self):
        """Fermeture de Smail : les messages en délai d’annulation partent maintenant. Vrai s’il faut attendre."""
        if not self.window.offline.isChecked():
            for item in self.waiting():
                scheduler.send_now(self.database, item['id'])
            self.kick()
        return self.task is not None

    # Avancement -------------------------------------------------------------------------------

    def progress(self, stage, done, total):
        self.stage = (stage, done, total)
        self.render()

    def finished(self, event):
        kind, subject, detail = event
        self.task = self.stage = None
        if kind in ('sent', 'partial'):
            self.window.mark_origin_locally(getattr(self, 'origin', None))
        if kind == 'sent':
            self.window.notify(tr('Message « {subject} » envoyé.').format(subject=subject) + (f' {detail}' if detail else ''))
            if not self.window.isActiveWindow():
                self.notify(tr('Message « {subject} » envoyé.').format(subject=subject))
        else:
            texts = {'failed': tr('Échec de l’envoi'), 'uncertain': tr('Envoi incertain'), 'partial': tr('Envoi partiel')}
            self.alert = (tr('{what} de « {subject} »').format(what=texts.get(kind, tr('Envoi')), subject=subject), detail)
            self.window.notify(tr('{valeur} de « {subject} ». {detail}').format(valeur=texts.get(kind, tr("Envoi")), subject=subject, detail=detail), tr('Voir'), self.show_outbox, 'error')
            self.notify(tr('{valeur} de « {subject} » : voir Fichier › Boîte d’envoi.').format(valeur=texts.get(kind, tr("Envoi")), subject=subject))
        self.tick()

    def crashed(self, _):
        subject = self.task[1] if self.task else ''
        self.task = self.stage = None
        self.alert = (tr('Envoi de « {subject} » interrompu').format(subject=subject), tr('Vérifiez vos Envoyés avant toute nouvelle tentative.'))
        self.tick()

    def notify(self, text):
        if self.window.tray and self.database.setting('notifications', True):
            self.window.tray.showMessage(tr('Smail'), text[:240], QSystemTrayIcon.Information, 6000)

    def render(self):
        waiting = self.waiting()
        cancel = show = dismiss = False
        if self.task is not None:
            stage, done, total = self.stage or ('connect', 0, 0)
            subject = self.task[1]
            if stage == 'upload' and total:
                text = tr('Envoi de « {subject} » — {valeur} / {valeur2} Mo').format(subject=subject, valeur=megabytes(done), valeur2=megabytes(total))
                self.bar.setRange(0, 1000)
                self.bar.setValue(int(done * 1000 / total))
            else:
                steps = {'connect': tr('connexion au serveur…'), 'verify': tr('vérification par le serveur…'),
                         'copy': tr('copie dans Envoyés…')}
                text = tr('Envoi de « {subject} » — {valeur}').format(subject=subject, valeur=steps.get(stage, "…"))
                self.bar.setRange(0, 0)  # Animation d’attente : la durée dépend du serveur.
            if waiting:
                text += tr(' (+{count} en attente)').format(count=len(waiting))
            self.text.setToolTip(tr('Le message part en arrière-plan ; vous pouvez continuer à travailler.'))
        elif self.alert:
            text = self.alert[0]
            self.text.setToolTip(safe_rich(self.alert[1]))  # Message d’erreur du serveur.
            show = dismiss = True
        elif waiting:
            item = waiting[0]
            subject = item['state'].get('subject') or '(Sans objet)'
            left = (scheduler.parse(item['send_at']) - scheduler.now_utc()).total_seconds()
            if self.window.offline.isChecked():
                text = tr('« {subject} » partira à la reconnexion').format(subject=subject)
            elif left > 0:
                text = tr('Envoi de « {subject} » dans {valeur} s').format(subject=subject, valeur=int(left) + 1)
            else:
                text = tr('Envoi de « {subject} »…').format(subject=subject)
            self.text.setToolTip(tr('« Annuler » rouvre le message en brouillon.'))
            cancel = True
        else:
            self.widget.hide()
            return
        self.text.setText(text)
        self.bar.setVisible(self.task is not None)
        self.cancel_button.setVisible(cancel)
        self.show_button.setVisible(show)
        self.dismiss_button.setVisible(dismiss)
        self.widget.show()

    # Actions ----------------------------------------------------------------------------------

    def cancel(self):
        waiting = self.waiting()
        if not waiting:
            return
        item = scheduler.cancel(self.database, waiting[0]['id'])
        if item:
            draft = dict(item['state'], id=item['id'], account=item['account'], attachments=item['files'])
            self.database.cache_put('draft', item['id'], draft, item['account'])
            self.window.reopen_draft(draft)
            self.window.notify(tr('Envoi annulé : le message est rouvert en brouillon.'))
        self.tick()

    def show_outbox(self):
        self.alert = None
        self.render()
        self.window.open_outbox()

    def dismiss(self):
        self.alert = None
        self.render()
