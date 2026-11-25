"""Une seule copie de Smail par dossier de données : un second lancement (lien mailto:, raccourci) est transmis à
la copie déjà ouverte au lieu d’ouvrir les mêmes données deux fois.

Canal local de Windows (QLocalServer), propre à l’utilisateur ; seuls de petits messages JSON y transitent."""
import hashlib
import json
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

MAX_MESSAGE = 64 * 1024


def instance_secret(directory: str) -> str:
    """Secret aléatoire propre à ce dossier de données, créé au premier lancement."""
    import secrets
    from pathlib import Path
    path = Path(directory) / 'instance.id'
    try:
        value = path.read_text(encoding='ascii').strip()
        if len(value) == 32:
            return value
    except (OSError, UnicodeDecodeError):
        pass
    value = secrets.token_hex(16)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='ascii')
    except OSError:
        return ''  # Dossier en lecture seule : nom fondé sur le seul chemin, comme avant.
    return value


class SingleInstance(QObject):
    received = Signal(dict)

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        # Nom imprévisible pour les autres comptes Windows : il dépend d’un secret rangé dans le dossier de données
        # (privé à l’utilisateur). Sinon, sur un PC partagé, un autre compte pourrait occuper ce canal le premier
        # et empêcher Smail de démarrer.
        self.name = 'SmailDesktop-' + hashlib.sha256((key + '|' + instance_secret(key)).encode('utf-8')).hexdigest()[:20]
        self.server = None
        self.buffers = {}  # Connexion -> octets reçus (une demande arrive parfois en plusieurs morceaux).

    def forward(self, payload: dict) -> bool:
        """Vrai si une copie de Smail tourne déjà et a reçu la demande."""
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(700):
            return False
        socket.write(json.dumps(payload).encode('utf-8'))
        socket.flush()
        # flush() envoie souvent tout d’un coup sous Windows : il ne reste alors rien à attendre, et
        # waitForBytesWritten() répondrait « échec » alors que la demande est partie.
        delivered = socket.bytesToWrite() == 0 or socket.waitForBytesWritten(2000)
        socket.disconnectFromServer()
        return delivered

    def listen(self) -> bool:
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        if not self.server.listen(self.name):
            QLocalServer.removeServer(self.name)  # Canal laissé par une copie arrêtée brutalement.
            if not self.server.listen(self.name):
                return False
        self.server.newConnection.connect(self.accept)
        return True

    def accept(self):
        while self.server is not None and self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.buffers[socket] = b''
            socket.readyRead.connect(self.read)
            socket.disconnected.connect(self.finish)

    def read(self):
        socket = self.sender()
        if socket in self.buffers:
            self.buffers[socket] = (self.buffers[socket] + bytes(socket.readAll()))[:MAX_MESSAGE]

    def finish(self):
        """Demande complète à la déconnexion de l’autre lancement : décodée puis transmise."""
        socket = self.sender()
        data = self.buffers.pop(socket, b'') + bytes(socket.readAll())
        socket.deleteLater()
        try:
            payload = json.loads(data[:MAX_MESSAGE].decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return
        if isinstance(payload, dict):
            self.received.emit(payload)

    def close(self):
        if self.server is not None:
            self.server.close()
            self.server.deleteLater()
            self.server = None
        self.buffers.clear()
