"""Lot « cohérence » et fonctions : mailto, instance unique, original, pièces jointes, orthographe, brouillons."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import base64
import pytest
from mailclient.core.mailto import parse as parse_mailto
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database
from mailclient.tests.test_scheduler import ME

RAW = (b'Return-Path: <test@livrango.com>\r\n'
       b'Authentication-Results: mx.google.com;\r\n'
       b'       dkim=pass header.i=@livrango.com;\r\n'
       b'       spf=softfail (google.com: domain of transitioning test@livrango.com does not designate 2a00::1)\r\n'
       b'       smtp.mailfrom=test@livrango.com;\r\n'
       b'       dmarc=pass (p=NONE) header.from=livrango.com\r\n'
       b'From: Livrango <test@livrango.com>\r\nSubject: Essai\r\nMessage-ID: <1@livrango.com>\r\n\r\nCorps du message\r\n')


def test_mailto_links():
    fields = parse_mailto('mailto:marie@x.fr,paul@y.fr?cc=chef@z.fr&subject=R%C3%A9union&body=Bonjour%0D%0A%C3%A0%20lundi')
    assert fields == dict(to='marie@x.fr, paul@y.fr', cc='chef@z.fr', bcc='', subject='Réunion', body='Bonjour\nà lundi')
    assert parse_mailto('MAILTO:?to=a@b.fr&to=c@d.fr')['to'] == 'a@b.fr, c@d.fr'
    assert '\r' not in parse_mailto('mailto:a@b.fr?subject=x%0D%0ABcc:%20pirate@z.fr')['subject']  # Pas d’en-tête injecté.
    assert len(parse_mailto('mailto:a@b.fr?body=' + 'x' * 50000)['body']) == 20000
    with pytest.raises(ValueError):
        parse_mailto('https://exemple.fr')


OPEN_COPY = r"""
import json, subprocess, sys, time
from PySide6.QtCore import QCoreApplication
app = QCoreApplication([])
from mailclient.ui.single_instance import SingleInstance
key, root = sys.argv[1], sys.argv[2]
first = SingleInstance(key)
nobody = first.forward({'show': True})  # Personne n’écoute encore.
assert first.listen()
received = []
first.received.connect(received.append)
# Second lancement : un autre programme, comme un clic sur un lien mailto: pendant que Smail est ouvert.
script = ('import sys; from PySide6.QtCore import QCoreApplication; app = QCoreApplication([]); '
          'from mailclient.ui.single_instance import SingleInstance; '
          'sys.exit(0 if SingleInstance(sys.argv[1]).forward({"mailto": "mailto:a@b.fr"}) else 1)')
second = subprocess.Popen([sys.executable, '-c', script, key], cwd=root)
deadline = time.monotonic() + 20
while not (received and second.poll() is not None) and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.01)
first.close()
app.processEvents()
print(json.dumps(dict(nobody=nobody, received=received, returncode=second.returncode)))
"""


def test_second_launch_is_forwarded_to_the_open_copy(tmp_path):
    """Copie ouverte et second lancement dans des processus séparés : le canal local de Qt (QLocalServer)
    ne vit jamais dans le processus des tests (sa fermeture y provoquait un plantage 0xc0000374 en CI)."""
    import json
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-c', OPEN_COPY, str(tmp_path), str(root)], cwd=root, capture_output=True,
                            text=True, timeout=60, env=dict(os.environ, PYTHONPATH=str(root)))
    assert result.returncode == 0, result.stderr[-2000:]
    shown = json.loads(result.stdout.strip().splitlines()[-1])
    assert shown == dict(nobody=False, received=[{'mailto': 'mailto:a@b.fr'}], returncode=0)


@pytest.fixture
def window(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    win = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    win.accounts = db.accounts()
    yield win
    for composer in list(win.composers):
        composer.saved_revision = composer.revision
        composer.close()
    win.reader.shutdown()
    win.close()
    from shiboken6 import delete
    delete(win)


def test_mailto_opens_a_prefilled_message(window):
    window.external_request({'mailto': 'mailto:marie@x.fr?subject=Bonjour'})
    composer = next(iter(window.composers))
    assert composer.to.text() == 'marie@x.fr' and composer.subject.text() == 'Bonjour' and composer.isVisible()
    window.open_mailto('mailto:%%%?subject')  # Lien abîmé : message d’erreur, rien ne plante.


def test_original_shows_authentication_verdicts(window, monkeypatch):
    from mailclient.ui.original_dialog import OriginalDialog, authentication, headers_of, summary
    assert authentication(RAW) == {'dkim': 'pass', 'spf': 'softfail', 'dmarc': 'pass'}
    assert summary(RAW) == 'SPF : échec partiel · DKIM : réussi · DMARC : réussi'
    assert headers_of(RAW).endswith('Message-ID: <1@livrango.com>') and 'Corps' not in headers_of(RAW)
    row = dict(account=ME.id, folder='INBOX', uid='5', uidvalidity='7', subject='Essai')
    window.database.cache_put('body', window.service.body_key(row), base64.b64encode(RAW).decode(), ME.id)
    monkeypatch.setattr(window, 'selected_row', lambda: row)
    shown = []
    monkeypatch.setattr(OriginalDialog, 'exec', lambda self: (shown.append(self.verdict.text()), self.deleteLater()))
    window.show_original()
    assert shown == ['SPF : échec partiel · DKIM : réussi · DMARC : réussi']


def test_save_all_attachments(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from PySide6.QtWidgets import QMessageBox
    from mailclient.core.parser import Attachment, Mail
    from mailclient.ui.mail_view import MailView
    view = MailView()
    try:
        (tmp_path / 'rapport.pdf').write_bytes(b'ancien')
        mail = Mail('a@b.fr', 'moi', 'Pièces', '', text='x')
        mail.attachments = [Attachment('rapport.pdf', 'application/pdf', b'PDF'), Attachment('photo.jpg', 'image/jpeg', b'JPG'),
                            Attachment('outil.exe', 'application/octet-stream', b'MZ')]
        view.mail = mail
        monkeypatch.setattr(QMessageBox, 'warning', lambda *args: QMessageBox.No)  # Pas les fichiers dangereux.
        monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
        assert view.save_all_attachments(str(tmp_path)) == 2
        assert (tmp_path / 'rapport.pdf').read_bytes() == b'ancien'  # Jamais écrasé.
        assert (tmp_path / 'rapport (2).pdf').read_bytes() == b'PDF' and (tmp_path / 'photo.jpg').exists()
        assert not (tmp_path / 'outil.exe').exists()
        assert view.attachments.removable is False  # Pas de × sur les pièces jointes reçues.
    finally:
        view.shutdown()
        from shiboken6 import delete
        delete(view)


def test_spelling(tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu
    from mailclient.ui.rich_text import RichTextEdit
    from mailclient.ui.spelling import Speller, add_suggestions, install
    db = Database(tmp_path / 'settings.db')
    speller = Speller(db)
    assert speller.available
    text = 'Merci pour votre messsage. Aujourd’hui, l’entretien est peut-être demain. Écrivez à kana@x.fr ou https://x.fr/abcxyz. Livrango.'
    assert [text[a:a+n] for a, n in speller.errors(text)] == ['messsage']
    assert speller.suggestions('messsage')[0] == 'message'
    speller.add('messsage')
    assert not list(speller.errors(text)) and db.setting('spelling_words') == ['messsage']
    editor = RichTextEdit()
    install(editor, Database(tmp_path / 'autre.db'))
    editor.setPlainText('Une erreurr ici')
    editor.resize(400, 200)
    editor.show()
    menu = QMenu()
    position = editor.cursorRect(editor.textCursor()).center()
    cursor = editor.textCursor()
    cursor.setPosition(6)
    editor.setTextCursor(cursor)
    position = editor.cursorRect(cursor).center()
    add_suggestions(editor, editor.speller, menu, QPoint(position))
    texts = [action.text() for action in menu.actions()]
    assert 'erreur' in texts and 'Ajouter « erreurr » au dictionnaire' in texts
    next(action for action in menu.actions() if action.text() == 'erreur').trigger()
    assert editor.toPlainText() == 'Une erreur ici'
    from shiboken6 import delete
    editor.spell_highlighter.setDocument(None)  # Le surligneur se détache avant la destruction du document.
    delete(menu)
    delete(editor)


def test_local_drafts_shown_in_drafts_folder_and_refresh_does_both(window, monkeypatch):
    window.folder_data = [('INBOX', 'Boîte de réception'), ('Drafts', 'Brouillons')]
    window.folders.addItems(['Boîte de réception', 'Brouillons'])
    monkeypatch.setattr(window, 'account', lambda: ME)
    window.database.cache_put('draft', 'b1', dict(id='b1', account=ME.id, subject='Brouillon'), ME.id)
    window.folders.blockSignals(True)
    window.folders.setCurrentRow(1)
    window.folders.blockSignals(False)
    window.update_local_drafts()
    assert not window.local_drafts_button.isHidden()
    assert window.local_drafts_button.text() == '1 brouillon enregistré sur ce PC — ouvrir'
    window.folders.blockSignals(True)
    window.folders.setCurrentRow(0)
    window.folders.blockSignals(False)
    window.update_local_drafts()
    assert window.local_drafts_button.isHidden()
    calls = []
    monkeypatch.setattr(window, 'load_folders', lambda *a: calls.append('dossiers'))
    monkeypatch.setattr(window, 'sync_now', lambda *a: calls.append('synchronisation'))
    window.refresh_all()
    assert calls == ['dossiers', 'synchronisation']
