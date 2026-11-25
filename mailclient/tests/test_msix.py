"""Paquet Microsoft Store (MSIX) : manifeste, logos et comportement de la version Store."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import sys
import xml.dom.minidom
from pathlib import Path
from mailclient.core import updater

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import build_msix  # noqa: E402


def test_manifest_is_valid_xml_with_store_version_and_escaped_identity():
    identity = dict(name='Editeur.Smail', publisher='CN=ABCD-1234', publisher_display_name='Léa & Co', display_name='Smail')
    document = xml.dom.minidom.parseString(build_msix.manifest(identity, '1.2.3').encode('utf-8'))
    node = document.getElementsByTagName('Identity')[0]
    assert (node.getAttribute('Name'), node.getAttribute('Publisher'), node.getAttribute('Version')) == \
        ('Editeur.Smail', 'CN=ABCD-1234', '1.2.3.0')  # Quatre nombres, le dernier à 0 (exigence du Store).
    assert document.getElementsByTagName('PublisherDisplayName')[0].firstChild.data == 'Léa & Co'
    application = document.getElementsByTagName('Application')[0]
    assert application.getAttribute('Executable') == 'Smail.exe'
    assert application.getAttribute('EntryPoint') == 'Windows.FullTrustApplication'
    capabilities = {node.getAttribute('Name') for node in document.getElementsByTagName('rescap:Capability')}
    assert capabilities == {'runFullTrust'}
    for logo in ('Square150x150Logo', 'Square44x44Logo'):
        assert application.getElementsByTagName('uap:VisualElements')[0].getAttribute(logo) == f'Assets\\{logo}.png'


def test_identity_file_and_version():
    identity = json.loads((ROOT / 'packaging' / 'msix' / 'identity.json').read_text(encoding='utf-8'))
    assert {'name', 'publisher', 'publisher_display_name', 'display_name'} <= set(identity)
    assert identity['publisher'].startswith('CN=')
    from mailclient import __version__
    assert build_msix.version() == __version__


def test_logos_have_the_sizes_the_manifest_expects(tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from PySide6.QtGui import QImage
    build_msix.logos(tmp_path)
    for name, size in build_msix.LOGOS.items():
        image = QImage(str(tmp_path / name))
        assert (image.width(), image.height()) == size and image.hasAlphaChannel()


def test_store_copy_leaves_updates_to_the_store(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from PySide6.QtWidgets import QWidget
    from mailclient.core.sync import Runner
    from mailclient.storage.database import Database
    from mailclient.ui.updates import UpdateManager
    assert updater.packaged() is False  # Lancé depuis les sources.
    monkeypatch.setattr(updater, 'packaged', lambda: True)
    monkeypatch.setattr(updater.sys, 'frozen', True, raising=False)
    assert not updater.installed_copy()  # Jamais d’installateur lancé par-dessus le Store.
    window = QWidget()
    window.quitting = False
    manager = UpdateManager(window, Database(tmp_path / 'settings.db'), Runner(window, None), tmp_path, current='1.1.1')
    informed = []
    manager.inform = lambda title, text: informed.append(text)
    monkeypatch.setattr(updater, 'check', lambda current: (_ for _ in ()).throw(AssertionError('aucune requête GitHub')))
    assert not manager.enabled()
    manager.check(manual=True)
    assert not manager.checking and 'Microsoft Store' in informed[0]


def test_startup_task_launches_smail_minimized():
    """Ouverture de session (version Store) : entrée dédiée, invisible, qui passe --minimized à Smail."""
    identity = dict(name='Editeur.Smail', publisher='CN=ABCD-1234', publisher_display_name='Smeth', display_name='Smail')
    document = xml.dom.minidom.parseString(build_msix.manifest(identity, '1.2.3').encode('utf-8'))
    startup = next(app for app in document.getElementsByTagName('Application') if app.getAttribute('Id') == 'SmailStartup')
    assert startup.getAttribute('uap10:Parameters') == '--minimized'
    assert startup.getElementsByTagName('uap:VisualElements')[0].getAttribute('AppListEntry') == 'none'
    assert startup.getElementsByTagName('desktop:StartupTask')[0].getAttribute('Enabled') == 'false'
    main = next(app for app in document.getElementsByTagName('Application') if app.getAttribute('Id') == 'Smail')
    assert not main.getElementsByTagName('desktop:StartupTask') and main.getElementsByTagName('uap:Protocol')
