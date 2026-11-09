"""Le contenu du mail reste lisible, les images intégrées ne sont pas bloquées."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from mailclient.tests.test_ui import APP, process_until
from mailclient.core.parser import Mail, Attachment
from mailclient.ui.attachment_widgets import clipboard_attachment
from mailclient.ui.mail_view import MailView


@pytest.mark.parametrize('variant',[1,2,3])
@pytest.mark.parametrize('dark',[False,True])
def test_reader_keeps_body_visible_and_selects_download(variant,dark):
    reader = MailView()
    reader.theme.update(variant=variant,dark=dark,density='Normale')
    reader.set_dark(dark)
    reader.resize(850,520)
    reader.show()
    reader.display(Mail('Expéditeur <a@example.com>','b@example.com','Sujet du message','date',
                        html='<p>Bonjour, voici le document.</p>',
                        attachments=[Attachment('document.txt','text/plain',b'contenu')]))
    APP.processEvents()
    assert reader.tabs.height() >= reader.height()/2
    assert reader.height() <= 540
    assert reader.metadata.height() <= 190
    assert reader.attachments.currentRow() == 0 and reader.save_button.isEnabled()
    assert reader.save_button.width() < reader.width()/2
    assert not reader.remote_banner.isVisible()
    assert not reader.attachments.isVisible()
    assert reader.sender_name.text() == 'Expéditeur'
    assert reader.sender_address.text() == 'a@example.com'
    assert not reader.tabs.tabBar().isVisible()
    reader.details_action.setChecked(True)
    assert reader.headers.isVisible()
    reader.details_action.setChecked(False)
    reader.plain_action.setChecked(True)
    assert reader.tabs.currentWidget() is reader.text
    reader.plain_action.setChecked(False)
    assert reader.tabs.currentWidget() is reader.web
    reader.attachment_title.click()
    APP.processEvents()
    assert reader.attachments.isVisible()
    reader.attachment_title.click()
    APP.processEvents()
    assert not reader.attachments.isVisible()
    assert reader.tabs.height() >= 180
    assert process_until(lambda: not reader.preview_runner.tasks)
    reader.close()


def test_embedded_image_is_rendered_without_remote_permission():
    image = QImage(64,32,QImage.Format_RGB32)
    image.fill(Qt.blue)
    attachment = clipboard_attachment(image,'image.png')
    attachment.cid = 'photo-interne'
    reader = MailView()
    reader.resize(850,600)
    reader.show()
    reader.display(Mail('a','b','Image intégrée','date',html='<p>Photo</p><img src="cid:photo-interne">',attachments=[attachment]))
    assert not reader.remote_banner.isVisible()
    assert not reader.interceptor.remote
    assert process_until(lambda: reader.attachments.item(0).data(Qt.UserRole))
    results = []
    def rendered():
        # Sonde dans le monde isolé de l'application, sans autoriser les scripts du mail.
        reader.web.page().runJavaScript('document.images.length && document.images[0].naturalWidth',1,results.append)
        return 64 in results
    assert process_until(rendered)
    reader.close()


def test_remote_banner_only_for_external_images_and_resets():
    reader = MailView()
    reader.show()
    reader.display(Mail('a','b','Sans image','date',html='<p>Texte HTML</p>'))
    assert not reader.remote_banner.isVisible()
    reader.display(Mail('a','b','Image distante','date',html='<img src="https://example.invalid/photo.png">'))
    assert reader.remote_banner.isVisible() and reader.images.isEnabled()
    reader.display(Mail('a','b','Message suivant','date',html='<p>Autre message</p>'))
    assert not reader.remote_banner.isVisible() and not reader.interceptor.remote
    reader.close()
