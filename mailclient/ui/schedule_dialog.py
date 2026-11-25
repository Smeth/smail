"""Choix d’une date : envoi programmé ou report d’un message."""
from mailclient.i18n import tr, N_
from datetime import datetime, timedelta
from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import QDateTimeEdit, QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout
from mailclient.ui.components import label

DAYS = (N_('lundi'), N_('mardi'), N_('mercredi'), N_('jeudi'), N_('vendredi'), N_('samedi'), N_('dimanche'))


def at(day: datetime, hour: int) -> datetime:
    return day.replace(hour=hour, minute=0, second=0, microsecond=0)


def presets(kind: str, now: datetime | None = None) -> list[tuple[str, datetime]]:
    """Choix rapides, en heure locale ; seuls les moments à venir sont proposés."""
    now = (now or datetime.now().astimezone()).replace(second=0, microsecond=0)
    tomorrow = at(now + timedelta(days=1), 8)
    monday = at(now + timedelta(days=(7 - now.weekday()) or 7), 8)
    if kind == 'send':
        choices = [(N_('Dans 1 heure'), now + timedelta(hours=1)), (N_('Demain à 8 h'), tomorrow), (N_('Lundi à 8 h'), monday)]
    else:
        evening = at(now, 18)
        saturday = at(now + timedelta(days=(5 - now.weekday()) % 7 or 7), 9)
        choices = [(N_('Dans 3 heures'), now + timedelta(hours=3)), (N_('Ce soir à 18 h'), evening), (N_('Demain à 8 h'), tomorrow),
                   (N_('Samedi à 9 h'), saturday), (N_('Lundi prochain à 8 h'), monday)]
    seen, result = set(), []
    for text, moment in choices:
        if moment > now + timedelta(minutes=30) and moment not in seen:
            seen.add(moment)
            result.append((f'{tr(text)}  ·  {tr(DAYS[moment.weekday()])} ' + moment.strftime(tr('%d/%m à %H:%M')), moment))
    return result


class ScheduleDialog(QDialog):
    def __init__(self, title, intro, kind, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.moment = None
        layout = QVBoxLayout(self)
        layout.addWidget(label(intro, 'Subtitle', True))
        for text, moment in presets(kind):
            button = QPushButton(text)
            button.setObjectName('Secondary')
            button.clicked.connect(lambda checked=False, m=moment: self.choose(m))
            layout.addWidget(button)
        layout.addWidget(label(tr('Autre date'), 'Bold'))
        self.custom = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.custom.setCalendarPopup(True)
        self.custom.setDisplayFormat('dddd dd/MM/yyyy HH:mm')
        self.custom.setMinimumDateTime(QDateTime.currentDateTime().addSecs(60))
        layout.addWidget(self.custom)
        self.error = QLabel()
        self.error.setObjectName('Small')
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr('Valider cette date'))
        buttons.button(QDialogButtonBox.Cancel).setText(tr('Annuler'))
        buttons.accepted.connect(lambda: self.choose(self.custom.dateTime().toPython().astimezone()))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose(self, moment: datetime):
        if moment <= datetime.now().astimezone():
            self.error.setText(tr('Choisissez une date et une heure à venir.'))
            return
        self.moment = moment
        self.accept()
