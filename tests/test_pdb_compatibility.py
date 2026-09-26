import struct
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from prodj.data.dbclient import DBClient
from prodj.data.exceptions import FatalQueryError, TemporaryQueryError
from prodj.data.pdbprovider import PDBProvider
from prodj.pdblib.album import Album
from prodj.pdblib.piostring import PioString


class PDBCompatibilityTestCase(unittest.TestCase):
  def test_utf16_name_ending_with_surrogate_pair(self):
    name = "eat, sleep, slay, \U00010503"
    encoded = name.encode("utf-16-be") + b"\x00\x00"
    entry = b"\x90" + struct.pack("<H", len(encoded)) + encoded

    self.assertEqual(PioString.parse(entry), name)

  def test_utf16_name_does_not_read_next_string(self):
    name = "Kesha.mp3"
    encoded = name.encode("utf-16-be")
    entry = b"\x90" + struct.pack("<H", len(encoded) + 4) + encoded + b"\x90"

    self.assertEqual(PioString.parse(entry), name)

  def test_long_album_name_offset(self):
    name = b"A" * 140
    entry = (struct.pack("<HHIII", 0x84, 0, 0, 7, 42)
             + b"\x00" * 4 + struct.pack("<HH", 3, 24)
             + b"\x40" + struct.pack("<H", len(name) + 4) + b"\x00" + name)

    album = Album.parse(entry)

    self.assertEqual(album.id, 42)
    self.assertEqual(album.name, name.decode("ascii"))

  @patch("prodj.data.pdbprovider.DataStore", dict)
  def test_missing_default_pdb_tries_hidden_path(self):
    prodj = Mock()
    prodj.cl.getClient.return_value = SimpleNamespace(ip_addr="169.254.1.1")
    prodj.nfs.enqueue_download.side_effect = [RuntimeError("NFS call failed: err_noent"), None]
    provider = PDBProvider(prodj)
    provider.delete_pdb = Mock()

    provider.download_pdb(3, "usb")

    self.assertEqual(prodj.nfs.enqueue_download.call_args_list[0].args[2], "/PIONEER/rekordbox/export.pdb")
    self.assertEqual(prodj.nfs.enqueue_download.call_args_list[1].args[2], "/.PIONEER/rekordbox/export.pdb")

  @patch("prodj.data.pdbprovider.DataStore", dict)
  def test_failed_fallback_does_not_mask_download_error(self):
    prodj = Mock()
    prodj.cl.getClient.return_value = SimpleNamespace(ip_addr="169.254.1.1")
    prodj.nfs.enqueue_download.side_effect = [
      RuntimeError("NFS call failed: err_noent"),
      FileExistsError("file already exists")]
    provider = PDBProvider(prodj)
    provider.delete_pdb = Mock()

    with self.assertRaisesRegex(FatalQueryError, "file already exists"):
      provider.get_db(3, "usb")

    self.assertIn((3, "usb"), provider.dbs)

  def test_empty_mount_info_is_retryable(self):
    client = DBClient(Mock())
    client.ensure_request_possible = Mock()
    client.query_list = Mock(return_value={"mount_path": "", "track_id": 0})

    with self.assertRaises(TemporaryQueryError):
      client.handle_request("mount_info", (2, "usb", 2097))

  def test_mount_info_query_uses_track_id_without_sort_argument(self):
    client = DBClient(Mock())
    client.getSocket = Mock()
    client.getTransactionId = Mock(return_value=1)
    client.socksnd = Mock()
    client.receive_dbmessage = Mock(return_value={
      "type": "success", "args": [{"value": 0}, {"value": 0}]})

    with patch("prodj.data.dbclient.packets.DBMessage.build", return_value=b"query") as build:
      client.query_list(3, "usb", None, [5378], "mount_info_request")

    query = build.call_args.args[0]
    self.assertEqual(len(query["args"]), 2)
    self.assertEqual(query["args"][1]["value"], 5378)
