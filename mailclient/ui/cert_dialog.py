"""Présentation d'une décision TLS ; le contrôle reste dans tls_policy.py."""
from mailclient.i18n import tr
from PySide6.QtWidgets import QDialog, QCheckBox, QDialogButtonBox, QFormLayout
from PySide6.QtCore import Qt
from mailclient.ui.dialog_shell import dialog_layout
from mailclient.ui.components import Banner, label

class CertificateDialog(QDialog):
    def __init__(self, alert, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Alerte de sécurité — certificat'))
        theme, outer, layout = dialog_layout(self,tr('Vérifier le certificat'),tr('La connexion ne peut pas être considérée comme sûre.'),(800,680))
        layout.addWidget(Banner(tr('L’identité du serveur ne peut pas être confirmée'),
                               tr('Continuer peut exposer vos identifiants à un tiers.'),theme,'Danger','shield-alert'))
        details = QFormLayout()
        details.setSpacing(12)
        for title,value in [(tr('Serveur'),alert.endpoint),(tr('Émetteur'),alert.issuer),(tr('Validité'),alert.validity),(tr('Raison'),alert.reason)]:
            text = label(str(value),wrap=True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            details.addRow(label(title,'Subtitle'),text)
        layout.addLayout(details)
        layout.addWidget(label(tr('EMPREINTE SHA-256'),'Eyebrow'))
        fingerprint = label('\n'.join(alert.fingerprint[i:i+32] for i in range(0,len(alert.fingerprint),32)),'Small',True)
        fingerprint.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        layout.addWidget(fingerprint)
        self.remember = QCheckBox(tr('Toujours faire confiance à ce certificat pour ce compte'))
        layout.addWidget(self.remember)
        layout.addWidget(label(tr('Une empreinte différente déclenchera une nouvelle alerte.'),'Small',True))
        layout.addStretch()
        buttons = QDialogButtonBox()
        cancel = buttons.addButton(tr('Annuler'),QDialogButtonBox.RejectRole)
        cancel.setObjectName('Primary')
        proceed = buttons.addButton(tr('Continuer quand même'),QDialogButtonBox.AcceptRole)
        proceed.setObjectName('QuietDanger')
        cancel.setDefault(True)
        proceed.setAutoDefault(False)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)
