import unittest
from unittest.mock import Mock, patch
import socket

from prodj.network.nfsdownload import NfsDownload
from prodj.network.nfsclient import NfsClient
from prodj.network.packets_nfs import RpcMsg

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
