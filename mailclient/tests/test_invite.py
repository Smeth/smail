"""Invitations de calendrier : lecture (Outlook, Google, journée entière, annulation) et réponse iTIP."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
from datetime import date, datetime, timezone
from email import message_from_bytes, policy
import pytest
from mailclient.core import invite as invites
from mailclient.core.accounts import Account, Server
from mailclient.core.parser import Attachment, Mail, parse_message
from mailclient.core.smtp_client import build_message

ME = Account('Claire Martin', 'claire@exemple.fr', Server('imap.exemple.fr', 993), Server('smtp.exemple.fr', 465))

OUTLOOK = ('BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\nPRODID:Microsoft Exchange Server 2010\r\nVERSION:2.0\r\n'
           'BEGIN:VTIMEZONE\r\nTZID:Romance Standard Time\r\nEND:VTIMEZONE\r\n'
           'BEGIN:VEVENT\r\nORGANIZER;CN=Sophie Laurent:mailto:sophie@exemple.fr\r\n'
           'ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;CN=Claire Martin:mailto:claire@exemple.fr\r\n'
           'DESCRIPTION;LANGUAGE=fr-FR:Ordre du jour :\\n- planning\\, budget\r\n'
           'UID:040000008200E00074C5B7101A82E00800000000\r\n SUFFIXE-REPLIE\r\n'
           'SUMMARY;LANGUAGE=fr-FR:Revue du lancement\r\nDTSTART;TZID=Romance Standard Time:20261201T100000\r\n'
           'DTEND;TZID=Romance Standard Time:20261201T113000\r\nLOCATION;LANGUAGE=fr-FR:Salle Lumière\\, 2e étage\r\n'
           'SEQUENCE:2\r\nBEGIN:VALARM\r\nTRIGGER:-PT15M\r\nACTION:DISPLAY\r\nDESCRIPTION:Rappel\r\nEND:VALARM\r\n'
           'END:VEVENT\r\nEND:VCALENDAR\r\n').encode('utf-8')

GOOGLE = (b'BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\nBEGIN:VEVENT\r\nDTSTART:20261202T080000Z\r\nDTEND:20261202T090000Z\r\n'
          b'ORGANIZER:mailto:org@gmail.com\r\nUID:abc123@google.com\r\nSUMMARY:Point hebdo\r\n'
          b'ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:claire@exemple.fr\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')


def test_outlook_invitation_with_windows_timezone():
    invite = invites.parse(OUTLOOK)
    assert invite.method == 'REQUEST' and invite.answerable and not invite.cancelled
    assert invite.uid == '040000008200E00074C5B7101A82E00800000000SUFFIXE-REPLIE'  # Ligne repliée réunie.
    assert invite.summary == 'Revue du lancement' and invite.location == 'Salle Lumière, 2e étage'
    assert invite.description == 'Ordre du jour :\n- planning, budget' and invite.sequence == '2'
    assert invite.organizer == 'sophie@exemple.fr' and invite.organizer_name == 'Sophie Laurent'
    assert invite.attendees == [('claire@exemple.fr', 'Claire Martin', 'NEEDS-ACTION')]
    assert invite.start.astimezone(timezone.utc) == datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)  # Paris, hiver.
    assert '01/12/2026' in invites.when(invite) and invites.when(invite).count(':') == 2


def test_google_utc_all_day_cancel_and_unknown_zone():
    google = invites.parse(GOOGLE)
    assert google.start == datetime(2026, 12, 2, 8, 0, tzinfo=timezone.utc) and google.organizer == 'org@gmail.com'
    all_day = invites.parse(b'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:j\r\nSUMMARY:Salon\r\nDTSTART;VALUE=DATE:20261205\r\nEND:VEVENT\r\nEND:VCALENDAR')
    assert all_day.start == date(2026, 12, 5) and 'journée entière' in invites.when(all_day)
    assert not all_day.answerable  # Pas de METHOD:REQUEST ni d’organisateur.
    cancel = invites.parse(GOOGLE.replace(b'METHOD:REQUEST', b'METHOD:CANCEL'))
    assert cancel.cancelled and not cancel.answerable
    odd = invites.parse(b'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nDTSTART;TZID=Zone Inconnue:20261201T100000\r\nEND:VEVENT\r\nEND:VCALENDAR')
    assert odd.start is None and invites.when(odd) == '01/12/2026 10:00 (fuseau « Zone Inconnue »)'


@pytest.mark.parametrize('data', [b'', b'pas un calendrier', b'BEGIN:VCALENDAR\r\nEND:VCALENDAR', b'BEGIN:VCALENDAR\n' + b'X' * 400_000],
                         ids=['vide', 'texte', 'calendrier-vide', 'trop-grand'])
def test_malformed_calendars_are_ignored(data):
    assert invites.parse(data) is None


def test_find_in_message_parts():
    raw = (b'From: sophie@exemple.fr\r\nSubject: Invitation\r\nMIME-Version: 1.0\r\nContent-Type: multipart/alternative; boundary=b\r\n\r\n'
           b'--b\r\nContent-Type: text/plain\r\n\r\nInvitation\r\n--b\r\nContent-Type: text/calendar; method=REQUEST; charset=utf-8\r\n\r\n'
           + GOOGLE + b'\r\n--b--\r\n')
    invite, attachment = invites.find(parse_message(raw))
    assert invite.summary == 'Point hebdo' and attachment.content_type == 'text/calendar'
    assert invites.find(Mail('a', 'b', 's', 'd', text='rien'))[0] is None


def test_reply_is_valid_itip_for_this_account():
    invite = invites.parse(OUTLOOK)
    text = invites.reply(invite, ME, 'ACCEPTED')
    lines = text.split('\r\n')
    assert 'METHOD:REPLY' in lines and 'SEQUENCE:2' in lines
    assert all(len(line.encode('utf-8')) <= 75 for line in lines)
    unfolded = invites.unfold(text)
    assert 'UID:040000008200E00074C5B7101A82E00800000000SUFFIXE-REPLIE' in unfolded
    assert any(line.startswith('ATTENDEE;PARTSTAT=ACCEPTED;CN="Claire Martin":mailto:claire@exemple.fr') for line in unfolded)
    assert 'DTSTART;TZID=Romance Standard Time:20261201T100000' in unfolded
    assert 'ORGANIZER;CN=Sophie Laurent:mailto:sophie@exemple.fr' in unfolded
    assert 'SUMMARY:Accepté : Revue du lancement' in unfolded
    with pytest.raises(ValueError):
        invites.reply(invite, ME, 'MAYBE')
    with pytest.raises(ValueError):
        invites.reply(invites.parse(GOOGLE.replace(b'METHOD:REQUEST', b'METHOD:CANCEL')), ME, 'ACCEPTED')


def test_reply_never_carries_injected_lines():
    evil = OUTLOOK.replace(b'SUMMARY;LANGUAGE=fr-FR:Revue du lancement', b'SUMMARY:Revue\\nMETHOD:CANCEL')
    text = invites.reply(invites.parse(evil), ME, 'DECLINED')
    assert [line for line in invites.unfold(text) if line.startswith('METHOD')] == ['METHOD:REPLY']


def test_response_message_mime():
    state = invites.response_state(invites.parse(OUTLOOK), ME, 'TENTATIVE')
    assert state['to'] == 'sophie@exemple.fr' and state['subject'] == 'Provisoire : Revue du lancement'
    message, recipients = build_message(ME, state['to'], '', '', state['subject'], state['body'], calendar=state['calendar'])
    parsed = message_from_bytes(message.as_bytes(), policy=policy.default)
    parts = {part.get_content_type(): part for part in parsed.iter_parts()}
    assert parsed.get_content_type() == 'multipart/alternative' and recipients == ['sophie@exemple.fr']
    assert parts['text/calendar'].get_param('method') == 'REPLY'
    assert 'PARTSTAT=TENTATIVE' in parts['text/calendar'].get_content()


def test_reader_card_and_main_window_reply(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from mailclient.tests.test_ui import process_until
    from mailclient.core import scheduler
    from mailclient.core.service import MailService
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    db.set_setting('conversation_view', False)
    raw = (b'From: Sophie <sophie@exemple.fr>\r\nSubject: Invitation\r\nMIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=b\r\n\r\n'
           b'--b\r\nContent-Type: text/plain\r\n\r\nVenez\r\n--b\r\nContent-Type: text/calendar; method=REQUEST\r\n'
           b'Content-Disposition: attachment; filename=invite.ics\r\n\r\n' + OUTLOOK + b'\r\n--b--\r\n')
    class Client:
        uidvalidity = '7'
        def folders(self):
            return [('INBOX', 'Boîte de réception'), ('Sent', 'Envoyés')]
        def messages(self, folder, page, query=''):
            return [dict(uid='3', uidvalidity='7', sender='Sophie <sophie@exemple.fr>', subject='Invitation', date='',
                         unread=True, starred=False, attachment=True)], 1
        def message_raw(self, folder, uid):
            return raw
        def append(self, folder, data, draft=False):
            appended.append(folder)
    sent, appended, opened = [], [], []
    monkeypatch.setattr(MailService, 'client', lambda *args: Client())
    monkeypatch.setattr(scheduler, 'send_message', lambda account, password, tls, message, recipients: sent.append(message) or {})
    window = MainWindow(db, type('V', (), {'get': lambda s, k: 'x', 'set': lambda *a: None})(), TLSPolicy(db), auto_load=False)
    window.reload_accounts()
    window.select_account(ME.id)
    assert process_until(lambda: not window.busy and window.table.count() == 1)
    window.table.setCurrentRow(0)
    assert process_until(lambda: not window.busy and window.reader.mail is not None)
    reader = window.reader
    assert reader.invite_card.isVisibleTo(reader) and reader.invite_title.text() == 'Invitation : Revue du lancement'
    assert 'Salle Lumière' in reader.invite_details.text() and reader.invite_buttons['ACCEPTED'].isVisibleTo(reader)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    reader.invite_buttons['ACCEPTED'].click()
    assert process_until(lambda: not window.busy and sent)
    assert sent[0]['To'] == 'sophie@exemple.fr' and 'Accepté' in sent[0]['Subject']
    assert appended == ['Sent'] and 'a été envoyée' in reader.invite_details.text()
    assert not reader.invite_buttons['ACCEPTED'].isVisibleTo(reader)
    from PySide6.QtGui import QDesktopServices
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toLocalFile()) or True)
    window.import_invite()
    assert opened and opened[0].endswith('.ics') and open(opened[0], 'rb').read() == OUTLOOK
    os.remove(opened[0])
    reader.shutdown()
    window.close()
    from shiboken6 import delete
    delete(window)
