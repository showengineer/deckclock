import errno
import unittest
from unittest.mock import Mock, patch

from prodj.core.prodj import PortInUseError, ProDj


class StartupPortTestCase(unittest.TestCase):
  def test_busy_port_closes_sockets_and_stops_data(self):
    for busy_port in (50000, 50001, 50002):
      with self.subTest(port=busy_port):
        prodj = ProDj.__new__(ProDj)
        prodj.keepalive_ip = prodj.beat_ip = prodj.status_ip = "0.0.0.0"
        prodj.keepalive_port = 50000
        prodj.beat_port = 50001
        prodj.status_port = 50002
        prodj.data = Mock()
        prodj.nfs = Mock()
        sockets = [Mock() for _ in range(busy_port - 50000 + 1)]
        sockets[-1].bind.side_effect = OSError(errno.EADDRINUSE, "Address already in use")

        with patch("prodj.core.prodj.socket.socket", side_effect=sockets):
          with self.assertRaises(PortInUseError) as error:
            prodj.start()

        self.assertEqual(str(error.exception), "Port {} is currently being used. Exiting".format(busy_port))
        prodj.data.stop.assert_called_once_with()
        prodj.nfs.start.assert_not_called()
        for sock in sockets:
          sock.close.assert_called_once_with()
