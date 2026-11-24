"""Détection automatique des réglages de messagerie et fenêtre d’ajout de compte."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import io
import pytest
from mailclient.core import autoconfig
from mailclient.core.accounts import Server

CPANEL = b'''<clientConfig version="1.1"><emailProvider id="exemple.fr">
  <incomingServer type="pop3"><hostname>mail.exemple.fr</hostname><port>995</port><socketType>SSL</socketType>
    <username>%EMAILADDRESS%</username></incomingServer>
  <incomingServer type="imap"><hostname>mail.exemple.fr</hostname><port>143</port><socketType>STARTTLS</socketType>
    <username>%EMAILADDRESS%</username></incomingServer>
  <incomingServer type="imap"><hostname>Mail.Exemple.fr</hostname><port>993</port><socketType>SSL</socketType>
    <username>%EMAILADDRESS%</username></incomingServer>
  <outgoingServer type="smtp"><hostname>mail.exemple.fr</hostname><port>25</port><socketType>plain</socketType>
    <username>%EMAILADDRESS%</username></outgoingServer>
  <outgoingServer type="smtp"><hostname>mail.exemple.fr</hostname><port>465</port><socketType>SSL</socketType>
    <username>%EMAILLOCALPART%</username></outgoingServer>
</emailProvider></clientConfig>'''


class Response(io.BytesIO):
    def __exit__(self, *args):
        return False


def web(pages):
    """Réseau simulé : {url: contenu} ; toute autre adresse échoue comme un domaine sans réglages."""
    asked = []
    def opener(request, timeout):
        asked.append(request.full_url)
        assert '@' not in request.full_url  # Seul le domaine est transmis.
        if request.full_url not in pages:
            raise OSError('introuvable')
        return Response(pages[request.full_url])
    opener.asked = asked
    return opener


def no_network(address, timeout):
    raise OSError('aucun serveur')


def test_known_providers_need_no_network():
    found = autoconfig.detect('Marie@GMAIL.com', opener=web({}), connect=no_network)
    assert (found.imap, found.smtp) == (Server('imap.gmail.com', 993, 'SSL/TLS'), Server('smtp.gmail.com', 587, 'STARTTLS'))
    assert autoconfig.known('a@yahoo.fr').smtp == Server('smtp.mail.yahoo.com', 465, 'SSL/TLS')


def test_provider_file_prefers_ssl_and_skips_plaintext():
    found = autoconfig.parse(CPANEL, 'jean@exemple.fr', 'votre hébergeur')
    assert found.imap == Server('mail.exemple.fr', 993, 'SSL/TLS') and found.imap_login == ''
    assert found.smtp == Server('mail.exemple.fr', 465, 'SSL/TLS') and found.smtp_login == 'jean'  # %EMAILLOCALPART%.


def test_https_sources_in_order_and_isp_database():
    opener = web({autoconfig.ISPDB.format(domain='exemple.fr'): CPANEL})
    found = autoconfig.detect('jean@exemple.fr', opener=opener, connect=no_network)
    assert found.source == 'base publique de Thunderbird'
    assert opener.asked[:3] == ['https://autoconfig.exemple.fr/mail/config-v1.1.xml',
                                'https://exemple.fr/.well-known/autoconfig/mail/config-v1.1.xml',
                                'https://autoconfig.thunderbird.net/v1.1/exemple.fr']


def test_http_file_only_trusted_for_servers_of_the_same_domain():
    honest = web({'http://autoconfig.exemple.fr/mail/config-v1.1.xml': CPANEL})
    assert autoconfig.detect('jean@exemple.fr', opener=honest, connect=no_network).imap.host == 'mail.exemple.fr'
    trap = web({'http://autoconfig.exemple.fr/mail/config-v1.1.xml': CPANEL.replace(b'mail.exemple.fr', b'mail.pirate.net')})
    assert autoconfig.detect('jean@exemple.fr', opener=trap, connect=no_network) is None


def test_usual_names_as_last_resort():
    opened = []
    class Socket:
        def close(self):
            pass
    def connect(address, timeout):
        opened.append(address)
        if address in {('imap.exemple.fr', 993), ('smtp.exemple.fr', 587)}:
            return Socket()
        raise OSError('fermé')
    found = autoconfig.detect('jean@exemple.fr', opener=web({}), connect=connect)
    assert (found.imap, found.smtp) == (Server('imap.exemple.fr', 993, 'SSL/TLS'), Server('smtp.exemple.fr', 587, 'STARTTLS'))
    assert 'à vérifier' in found.source


@pytest.mark.parametrize('data', [b'pas du xml', b'<clientConfig/>', CPANEL.replace(b'<port>993</port>', b'<port>x</port>')
                                  .replace(b'STARTTLS', b'plain')])
def test_broken_or_unsafe_files_are_ignored(data):
    assert autoconfig.parse(data, 'jean@exemple.fr', 'x') is None


def test_invalid_addresses():
    assert autoconfig.domain_of('pas-une-adresse') == '' and autoconfig.detect('a@b') is None


def test_dialog_fills_servers_from_detection(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP, FakeSecrets, process_until  # noqa: F401
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.ui.account_dialog import AccountDialog
    found = autoconfig.parse(CPANEL, 'jean@exemple.fr', 'votre hébergeur')
    monkeypatch.setattr(autoconfig, 'detect', lambda address: found)
    db = Database(tmp_path / 'settings.db')
    dialog = AccountDialog(db, FakeSecrets(), TLSPolicy(db))
    assert dialog.server_panel.isHidden()  # Nouveau compte : serveurs repliés.
    dialog.address.setText('jean@exemple.fr')
    dialog.detect()
    assert process_until(lambda: dialog.servers['imap'][0].text() == 'mail.exemple.fr')
    assert dialog.servers['imap'][2].value() == 993 and dialog.servers['smtp'][2].value() == 465
    assert dialog.logins['smtp'].text() == 'jean' and dialog.detect_status.text().startswith('Réglages trouvés (votre hébergeur)')
    # Saisie manuelle : plus jamais écrasée.
    dialog.servers['imap'][0].setText('imap.autre.fr')
    dialog.servers_edited()
    dialog.detect()
    assert dialog.servers['imap'][0].text() == 'imap.autre.fr'
    # Rien trouvé : les champs s’ouvrent pour une saisie manuelle.
    monkeypatch.setattr(autoconfig, 'detect', lambda address: None)
    other = AccountDialog(db, FakeSecrets(), TLSPolicy(db))
    other.address.setText('x@inconnu.fr')
    other.detect()
    assert process_until(lambda: not other.server_panel.isHidden())
    assert 'introuvables' in other.detect_status.text()
