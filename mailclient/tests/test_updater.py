"""Mises à jour automatiques : manifeste signé, téléchargement vérifié, installation à la fermeture."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import hashlib
import io
import json
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from mailclient.core import updater
from mailclient.core.updater import Update, UpdateError

KEY = Ed25519PrivateKey.generate()
PUBLIC = KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
INSTALLER = b'MZ' + b'smail' * 1000
NAME = 'Smail-1.2.0-installation.exe'
BASE = 'https://github.com/Smeth/smail/releases/download/v1.2.0/'


def manifest(**changes):
    data = dict(version='1.2.0', file=NAME, sha256=hashlib.sha256(INSTALLER).hexdigest(), size=len(INSTALLER))
    data.update(changes)
    return json.dumps(data).encode()


class Response(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url

    def __exit__(self, *args):
        return False


def server(files, redirect=None):
    """Serveur simulé : {url: octets} ; redirect change l’URL finale (comme les fichiers de GitHub)."""
    requested = []
    def opener(request, timeout):
        url = request.full_url
        requested.append(url)
        assert request.get_header('User-agent') == 'Smail-Updater'
        return Response(files[url], redirect or url)
    opener.requested = requested
    return opener


def release(tag='v1.2.0', signed=True, data=None, signature=None, **extra):
    content = data or manifest()
    assets = [dict(name=NAME, browser_download_url=BASE + NAME)]
    if signed:
        assets += [dict(name='smail-update.json', browser_download_url=BASE + 'smail-update.json'),
                   dict(name='smail-update.json.sig', browser_download_url=BASE + 'smail-update.json.sig')]
    files = {updater.LATEST: json.dumps(dict(tag_name=tag, body='Nouveautés', assets=assets, **extra)).encode(),
             BASE + 'smail-update.json': content, BASE + 'smail-update.json.sig': signature or KEY.sign(content),
             BASE + NAME: INSTALLER}
    return files


def test_versions():
    assert updater.newer('v1.10.0', '1.9.3') and not updater.newer('1.0.0', '1.0.0') and not updater.newer('0.9.9', '1.0.0')
    for bad in ('', '1.0', '1.0.0-beta', 'v', '1.0.0.0'):
        with pytest.raises(UpdateError):
            updater.parse_version(bad)


def test_signed_release_is_accepted():
    update = updater.check('1.1.0', server(release()), PUBLIC)
    assert update == Update('1.2.0', BASE + NAME, NAME, hashlib.sha256(INSTALLER).hexdigest(), len(INSTALLER), 'Nouveautés')


def test_nothing_to_do_when_up_to_date_draft_or_prerelease():
    assert updater.check('1.2.0', server(release()), PUBLIC) is None
    assert updater.check('1.3.0', server(release()), PUBLIC) is None
    assert updater.check('1.1.0', server(release(prerelease=True)), PUBLIC) is None
    assert updater.check('1.1.0', server(release(draft=True)), PUBLIC) is None


@pytest.mark.parametrize('files, message', [
    (release(signed=False), 'pas signée'),
    (release(signature=b'x' * 64), 'Signature'),
    (release(signature=Ed25519PrivateKey.generate().sign(manifest())), 'Signature'),  # Autre clé.
    (release(data=manifest(version='1.3.0')), 'ne correspond pas'),
    (release(data=manifest(file='autre.exe')), 'Nom de fichier'),
    (release(data=manifest(sha256='0' * 10)), 'Empreinte'),
], ids=['non-signee', 'signature-fausse', 'autre-cle', 'version', 'fichier', 'empreinte'])
def test_unsigned_or_tampered_release_is_refused(files, message):
    with pytest.raises(UpdateError, match=message):
        updater.check('1.1.0', server(files), PUBLIC)


def test_unexpected_hosts_are_refused():
    files = release()
    with pytest.raises(UpdateError, match='inattendue'):
        updater.check('1.1.0', server(files, redirect='https://exemple.com/piege'), PUBLIC)
    with pytest.raises(UpdateError):
        updater.checked_url('http://github.com/Smeth/smail')


def test_download_verifies_size_and_digest(tmp_path):
    update = updater.check('1.1.0', server(release()), PUBLIC)
    opener = server(release(), redirect='https://objects.githubusercontent.com/fichier')
    path = updater.download(update, tmp_path, opener)
    assert path.read_bytes() == INSTALLER and path.name == NAME
    assert updater.download(update, tmp_path, opener) == path and len(opener.requested) == 1  # Déjà vérifié : réutilisé.
    path.unlink()
    altered = dict(release(), **{BASE + NAME: INSTALLER[:-1] + b'!'})
    with pytest.raises(UpdateError, match='altéré'):
        updater.download(update, tmp_path, server(altered))
    bigger = dict(release(), **{BASE + NAME: INSTALLER + b'!'})
    with pytest.raises(UpdateError, match='plus gros'):
        updater.download(update, tmp_path, server(bigger))
    assert not list(tmp_path.iterdir())  # Aucun fichier partiel ou refusé ne reste.


def test_old_downloads_are_removed(tmp_path):
    (tmp_path / 'Smail-1.1.5-installation.exe').write_bytes(b'ancien')
    update = updater.check('1.1.0', server(release()), PUBLIC)
    updater.download(update, tmp_path, server(release()))
    assert [p.name for p in tmp_path.iterdir()] == [NAME]


def test_install_runs_installer_silently(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(updater.subprocess, 'Popen', lambda arguments, **kwargs: calls.append(arguments))
    updater.install(tmp_path / NAME, relaunch=True)
    assert calls[0][1:] == ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCANCEL', '/CLOSEAPPLICATIONS', '/RELAUNCH=1']


def test_only_installed_copies_update_themselves(monkeypatch, tmp_path):
    assert not updater.installed_copy()  # Depuis les sources.
    monkeypatch.setattr(updater.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(updater.sys, 'executable', str(tmp_path / 'Smail.exe'))
    assert not updater.installed_copy()  # Dossier copié, sans désinstalleur.
    (tmp_path / 'unins000.exe').write_bytes(b'')
    assert updater.installed_copy()


def test_embedded_public_key_is_valid():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    Ed25519PublicKey.from_public_bytes(updater.PUBLIC_KEY)


def test_manager_downloads_installs_on_exit_and_forgets_after_update(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import process_until
    from PySide6.QtWidgets import QWidget, QStatusBar
    from mailclient.core.sync import Runner
    from mailclient.storage.database import Database
    from mailclient.ui.updates import UpdateManager

    class Window(QWidget):
        quitting, tray = False, None
        def __init__(self):
            super().__init__()
            self.bar, self.banners, self.quits = QStatusBar(), [], 0
        def statusBar(self):
            return self.bar
        def show_update_banner(self, title, description, action, callback):
            self.banners.append((title, action, callback))
        def request_quit(self):
            self.quits += 1

    real_check, real_download = updater.check, updater.download
    monkeypatch.setattr(updater, 'check', lambda current: real_check(current, server(release()), PUBLIC))
    monkeypatch.setattr(updater, 'download', lambda update, directory, cancelled: real_download(update, directory, server(release())))
    monkeypatch.setattr(updater, 'installed_copy', lambda: True)
    installs = []
    monkeypatch.setattr(updater, 'install', lambda path, relaunch: installs.append((path.name, relaunch)))
    db = Database(tmp_path / 'settings.db')
    window = Window()
    manager = UpdateManager(window, db, Runner(window, None), tmp_path, current='1.1.0')
    manager.check(manual=True)
    assert process_until(lambda: window.banners)
    title, action, callback = window.banners[-1]
    assert title == 'Smail 1.2.0 est prêt' and action == 'Redémarrer maintenant'
    assert (tmp_path / 'updates' / NAME).read_bytes() == INSTALLER
    callback()  # « Redémarrer maintenant » : fermeture demandée, relance après installation.
    assert window.quits == 1 and manager.relaunch
    assert manager.install_on_exit() and installs == [(NAME, True)]
    assert db.setting('update_pending')['attempts'] == 1
    # Fichier modifié entre la vérification et la fermeture : rien n’est lancé.
    (tmp_path / 'updates' / NAME).write_bytes(b'modifie')
    assert not manager.install_on_exit() and len(installs) == 1
    # Au redémarrage dans la nouvelle version, l’état est effacé.
    UpdateManager(window, db, Runner(window, None), tmp_path, current='1.2.0')
    assert db.setting('update_pending') is None
    # Après deux échecs d’installation, plus de tentative silencieuse.
    db.set_setting('update_pending', dict(version='1.2.0', file=NAME, sha256='x', attempts=2))
    manager = UpdateManager(window, db, Runner(window, None), tmp_path, current='1.1.0')
    manager.check()
    assert process_until(lambda: len(window.banners) == 2)
    assert 'n’a pas pu' in window.banners[-1][0] and manager.ready is None


def test_up_to_date_and_unreachable(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import process_until
    from PySide6.QtWidgets import QWidget, QStatusBar
    from mailclient.core.sync import Runner
    from mailclient.storage.database import Database
    from mailclient.ui.updates import UpdateManager

    class Window(QWidget):
        quitting, tray = False, None
        def __init__(self):
            super().__init__()
            self.bar = QStatusBar()
        def statusBar(self):
            return self.bar
    window = Window()
    manager = UpdateManager(window, Database(tmp_path / 'settings.db'), Runner(window, None), tmp_path, current='1.2.0')
    monkeypatch.setattr(updater, 'check', lambda current: None)
    manager.check(manual=True)
    assert process_until(lambda: not manager.checking)
    assert window.bar.currentMessage() == 'Smail 1.2.0 est à jour.'
    def offline(current):
        raise OSError('réseau indisponible')
    monkeypatch.setattr(updater, 'check', offline)
    manager.check()  # Vérification automatique : silencieuse.
    assert process_until(lambda: not manager.checking)
    assert window.bar.currentMessage() == 'Smail 1.2.0 est à jour.'
