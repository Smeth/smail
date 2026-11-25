"""En-tête simplifié : filtres de recherche et indicateur de connexion."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from datetime import date, datetime
from mailclient.core.search_query import parse
from mailclient.ui.search_dialog import build_query


def test_filters_write_operators_the_parser_understands():
    text = build_query('budget 2026', sender='Marie Dupont', subject='devis', attachment=True, unread=True,
                       since=date(2026, 11, 1), before=date(2026, 12, 1))
    assert text == 'budget 2026 de:"Marie Dupont" objet:devis a:pj est:nonlu après:2026-11-01 avant:2026-12-01'
    query = parse(text)
    assert query.sender == ['Marie Dupont'] and query.subject == ['devis'] and query.words == ['budget', '2026']
    assert query.attachment and query.unread and query.since == date(2026, 11, 1) and query.before == date(2026, 12, 1)
    assert build_query() == ''


def test_dialog_round_trip_and_clear():
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.ui.search_dialog import SearchDialog
    dialog = SearchDialog('de:léa objet:"point projet" a:pj est:étoilé après:2026-11-01')
    assert dialog.sender.text() == 'léa' and dialog.subject.text() == 'point projet'
    assert dialog.attachment.isChecked() and dialog.starred.isChecked() and dialog.since_on.isChecked()
    assert dialog.query() == 'de:léa objet:"point projet" a:pj est:étoilé après:2026-11-01'
    dialog.clear()
    assert dialog.query() == ''
    for text in ('', 'budget', 'est:nonlu', 'de:léa'):  # Recherche vide ou sans « a:pj » : plantait en 1.2.0.
        assert SearchDialog(text).query() == text


def test_connection_indicator(tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    try:
        assert window.connection.text() == '● En ligne' and window.offline.isHidden()
        assert window.command_button.text() == '' and window.command_button.toolTip() == 'Commandes (Ctrl+K)'
        window.last_sync = datetime(2026, 11, 24, 21, 45)
        window.update_connection()
        assert window.connection.text() == '● En ligne · synchronisé à 21:45'
        window.offline_action.trigger()  # Comptes › Hors ligne.
        assert window.offline.isChecked() and window.connection.text() == '○ Hors ligne · cache local'
    finally:
        window.reader.shutdown()
        window.close()
        from shiboken6 import delete
        delete(window)
