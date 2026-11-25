"""« Afficher l’original » : en-têtes complets du message et verdict d’authentification (SPF, DKIM, DMARC).

Utile pour comprendre pourquoi un message est arrivé dans le spam, ou vérifier un expéditeur suspect.
Le texte est affiché tel quel, en lecture seule : rien n’est interprété ni chargé."""
from mailclient.i18n import tr
import re
from email import message_from_bytes, policy
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout
from mailclient.ui.components import label

VERDICTS = {'pass': tr('réussi'), 'fail': tr('échec'), 'softfail': tr('échec partiel'), 'neutral': tr('neutre'), 'none': tr('absent'),
            'temperror': tr('erreur temporaire'), 'permerror': tr('erreur de configuration'), 'policy': tr('politique'), 'bestguesspass': tr('probable')}


def headers_of(raw: bytes) -> str:
    """Partie en-têtes du message brut (jusqu’à la première ligne vide)."""
    head = re.split(rb'\r?\n\r?\n', raw, maxsplit=1)[0]
    return head.decode('utf-8', 'replace').replace('\r\n', '\n')


def authentication(raw: bytes) -> dict:
    """Verdicts SPF, DKIM et DMARC du serveur destinataire le plus proche (premier Authentication-Results)."""
    message = message_from_bytes(raw[:200_000], policy=policy.compat32)
    results = message.get_all('Authentication-Results') or []
    found = {}
    for header in results:
        text = re.sub(r'\s+', ' ', str(header))
        for method in ('spf', 'dkim', 'dmarc'):
            if method not in found:
                match = re.search(rf'\b{method}=([a-z]+)', text, re.I)
                if match:
                    found[method] = match[1].lower()
    return found


def summary(raw: bytes) -> str:
    verdicts = authentication(raw)
    if not verdicts:
        return tr('Aucun résultat d’authentification dans ce message (fréquent pour les messages envoyés ou internes).')
    return ' · '.join(f'{method.upper()} : {VERDICTS.get(value, value)}' for method, value in
                      ((m, verdicts[m]) for m in ('spf', 'dkim', 'dmarc') if m in verdicts))


class OriginalDialog(QDialog):
    def __init__(self, raw: bytes, subject='', parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Original — ') + (subject or 'message'))
        self.resize(820, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(label(tr('Authentification de l’expéditeur'), 'Bold'))
        self.verdict = label(summary(raw), 'Subtitle', True)
        layout.addWidget(self.verdict)
        layout.addWidget(label(tr('SPF et DKIM prouvent que le message vient bien du domaine de l’expéditeur ; DMARC dit quoi '
                               'faire en cas d’échec. Un échec explique souvent un classement en spam.'), 'Small', True))
        self.text = QPlainTextEdit(headers_of(raw))
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text.setFont(QFont('Consolas', 9))
        self.text.setAccessibleName(tr('En-têtes complets du message'))
        layout.addWidget(self.text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy = buttons.addButton(tr('Copier les en-têtes'), QDialogButtonBox.ActionRole)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.text.toPlainText()))
        buttons.button(QDialogButtonBox.Close).setText(tr('Fermer'))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
