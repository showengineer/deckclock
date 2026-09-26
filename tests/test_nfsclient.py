import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import socket

from construct import Int32ub, PascalString

from prodj.network.nfsdownload import NfsDownload
from prodj.network.nfsclient import NfsClient
from prodj.network.packets_nfs import RpcMsg, getNfsResStruct

class MockSock(Mock):
    def __init__(self, inet, type):
        assert inet == socket.AF_INET
        assert type == socket.SOCK_DGRAM
        self.sent = list()

    def sendto(self, data, host):
        msg = RpcMsg.parse(data)
        self.sent += msg
        print(msg)

class DbclientTestCase(unittest.TestCase):
    def setUp(self):
        self.nc = NfsClient(None) # prodj object only required for enqueue_download_from_mount_info
        # TODO: use unittest.mock for replacing socket module
        # self.sock = MockSock
        # NfsClient.socket.socket = self.sock

        # assert self.sock.binto.called

    @patch('socket.socket', new=MockSock)
    @patch('prodj.network.nfsclient.select')
    def test_buffer_download(self, select):
        self.nc.enqueue_buffer_download("1.1.1.1", "usb", "/folder/file")

    def test_out_of_order_blocks_do_not_crash_debug_logging(self):
        download = NfsDownload(None, ("1.1.1.1", 2049), b"", "/folder/file")
        download.size = 4
        download.blocks = {2: b"cd"}

        download.writeBlocks()

        self.assertEqual(download.write_offset, 0)
        self.assertEqual(download.blocks, {2: b"cd"})

    def test_download_filename_is_sanitized(self):
        self.assertEqual(
            self.nc.get_download_filename('/Music/odd:track*name?.mp3'),
            'odd_track_name_.mp3')

    def test_empty_download_filename_is_rejected(self):
        self.assertEqual(self.nc.get_download_filename('', 'player-2-track-2130'), 'player-2-track-2130')
        self.assertEqual(self.nc.get_download_filename('/', 'player-2-track-2130'), 'player-2-track-2130')


class NfsDownloadStartTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_missing_source_does_not_open_destination(self):
        nfsclient = Mock()
        nfsclient.NfsLookupPath.side_effect = RuntimeError("NFS call failed: err_noent")
        download = NfsDownload(nfsclient, ("169.254.1.1", 2049), b"", "/missing/export.pdb")
        download.setFilename = Mock()

        with self.assertRaisesRegex(RuntimeError, "err_noent"):
            await download.start("databases/player-3-usb.pdb")
        download.setFilename.assert_not_called()

    async def test_control_character_filename_uses_unique_directory_entry(self):
        client = NfsClient(None)
        self.addCleanup(client.loop.close)
        requested = "TiK ToK (Explicit Version) (Audio) \x14\u2020Kesha.mp3"
        actual = "TiK ToK (Explicit Version) (Audio) Kesha.mp3"
        client.NfsLookup = AsyncMock(side_effect=[RuntimeError("NFS call failed: err_noent"), {"fhandle": b"ok"}])
        client.NfsReadDir = AsyncMock(return_value=[actual])

        result = await client.NfsLookupWithFilenameFallback(("169.254.1.1", 2049), requested, b"dir")

        self.assertEqual(result["fhandle"], b"ok")
        self.assertEqual(client.NfsLookup.call_args_list[1].args[1], actual)

    async def test_ambiguous_directory_entries_do_not_select_a_file(self):
        client = NfsClient(None)
        self.addCleanup(client.loop.close)
        requested = "TiK ToK (Explicit Version) (Audio) \x14\u2020Kesha.mp3"
        client.NfsLookup = AsyncMock(side_effect=RuntimeError("NFS call failed: err_noent"))
        client.NfsReadDir = AsyncMock(return_value=[
            "TiK ToK (Explicit Version) (Audio) Kesha.mp3",
            "TiK ToK (Explicit Version) (Audio) Live.mp3"])

        with self.assertRaisesRegex(RuntimeError, "err_noent"):
            await client.NfsLookupWithFilenameFallback(("169.254.1.1", 2049), requested, b"dir")

        client.NfsLookup.assert_awaited_once()

    def test_readdir_response_decodes_padded_utf16_filename(self):
        name = "Kesha.mp3"
        encoded_name = PascalString(Int32ub, encoding="utf-16-le").build(name)
        padding = b"\x00" * (-len(encoded_name) % 4)
        response = (Int32ub.build(0) + Int32ub.build(1) + Int32ub.build(42)
                    + encoded_name + padding + b"next" + Int32ub.build(0) + Int32ub.build(1))

        parsed = getNfsResStruct("readdir").parse(response)

        self.assertEqual(parsed.content.entries[0].name, name)
        self.assertEqual(parsed.content.entries[0].cookie, b"next")
        self.assertEqual(parsed.content.eof, 1)

    async def test_readdir_follows_cookies_until_end(self):
        client = NfsClient(None)
        self.addCleanup(client.loop.close)
        first = SimpleNamespace(entries=[
            SimpleNamespace(present=1, name="first.mp3", cookie=b"next"),
            SimpleNamespace(present=0)], eof=0)
        second = SimpleNamespace(entries=[
            SimpleNamespace(present=1, name="second.mp3", cookie=b"last"),
            SimpleNamespace(present=0)], eof=1)
        client.NfsCall = AsyncMock(side_effect=[first, second])

        names = await client.NfsReadDir(("169.254.1.1", 2049), b"dir")

        self.assertEqual(names, ["first.mp3", "second.mp3"])
        self.assertEqual(client.NfsCall.call_args_list[1].args[2]["cookie"], b"next")
