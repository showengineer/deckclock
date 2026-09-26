import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from prodj.gui.gui_browser import Browser


class BrowserSearchTestCase(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.app = QApplication.instance() or QApplication([])

  def test_filter_and_select_track_from_proxy(self):
    prodj = Mock()
    prodj.cl.getClient.return_value = SimpleNamespace(
      usb_state="loaded", sd_state="unloaded", usb_info={})
    browser = Browser(prodj, 1)
    self.addCleanup(browser.close)
    browser.renderList("title", 1, "usb", [
      {"title": "First song", "artist": "Alice", "track_id": 10},
      {"title": "Another song", "artist": "Bob", "track_id": 20}])

    browser.search_edit.setText("BOB")

    self.assertEqual(browser.search_model.rowCount(), 1)
    browser.tableItemClicked(browser.search_model.index(0, 0))
    self.assertEqual(browser.track_id, 20)
    self.assertTrue(browser.download_button.isEnabled())
    prodj.data.get_metadata.assert_called_with(1, "usb", 20, browser.storeRequest)

    browser.search_edit.clear()
    self.assertEqual(browser.search_model.rowCount(), 2)
    self.assertIsNone(browser.track_id)
    self.assertFalse(browser.download_button.isEnabled())
