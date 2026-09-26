import socket
import logging
import errno
from threading import Thread
from select import select
from enum import Enum

from prodj.core.clientlist import ClientList
from prodj.core.vcdj import Vcdj
from prodj.data.dataprovider import DataProvider
from prodj.network.nfsclient import NfsClient
from prodj.network.ip import guess_own_iface
from prodj.network import packets
from prodj.network import packets_dump

class OwnIpStatus(Enum):
  notNeeded = 1,
  waiting = 2,
  acquired = 3

class PortInUseError(Exception):
  def __init__(self, port):
    self.port = port
    super().__init__("Port {} is currently being used. Exiting".format(port))

class ProDj(Thread):
  def __init__(self):
    super().__init__()
    self.cl = ClientList(self)
    self.data = DataProvider(self)
    self.vcdj = Vcdj(self)
    self.nfs = NfsClient(self)
    self.keepalive_ip = "0.0.0.0"
    self.keepalive_port = 50000
    self.beat_ip = "0.0.0.0"
    self.beat_port = 50001
    self.status_ip = "0.0.0.0"
    self.status_port = 50002
    self.need_own_ip = OwnIpStatus.notNeeded
    self.own_ip = None
    self.vcdj_player_number_auto = True

  def start(self):
    sockets = []
    try:
      for name, ip, port in (
          ("keepalive", self.keepalive_ip, self.keepalive_port),
          ("beat", self.beat_ip, self.beat_port),
          ("status", self.status_ip, self.status_port)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sockets.append(sock)
        try:
          if name != "status":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
          sock.bind((ip, port))
        except OSError as e:
          if e.errno in (errno.EADDRINUSE, 10048) or getattr(e, "winerror", None) == 10048:
            raise PortInUseError(port) from e
          raise
        setattr(self, name + "_sock", sock)
        logging.info("Listening on %s:%d for %s packets", ip, port, name)
    except (OSError, PortInUseError):
      for sock in sockets:
        sock.close()
      self.data.stop()
      raise
    self.socks = [self.keepalive_sock, self.beat_sock, self.status_sock]
    self.keep_running = True
    self.data.start()
    self.nfs.start()
    super().start()

  def stop(self):
    self.keep_running = False
    self.nfs.stop()
    self.data.stop()
    self.vcdj_disable()
    self.join()
    self.keepalive_sock.close()
    self.beat_sock.close()
    self.status_sock.close()

  def get_used_player_numbers(self):
    return set(c.player_number for c in self.cl.clients)

  def vcdj_next_available_player_number(self, preferred=5, reserved=None):
    if reserved is None:
      reserved = set()
    used = self.get_used_player_numbers() | set(reserved)
    player_number = preferred
    while player_number in used:
      player_number += 1
    return player_number

  def vcdj_set_player_number(self, vcdj_player_number=5, auto=False):
    logging.info("Player number set to {}".format(vcdj_player_number))
    self.vcdj.player_number = vcdj_player_number
    self.vcdj_player_number_auto = auto
    #self.data.dbc.own_player_number = vcdj_player_number

  def vcdj_auto_set_player_number(self, preferred=5, reserved=None):
    player_number = self.vcdj_next_available_player_number(preferred, reserved)
    self.vcdj_set_player_number(player_number, auto=True)

  def vcdj_enable(self, preferred_player_number=None):
    if preferred_player_number is not None:
      self.vcdj_auto_set_player_number(preferred_player_number)
    self.vcdj_set_iface()
    self.vcdj.start()

  def vcdj_disable(self):
    self.vcdj.stop()
    self.vcdj.join()

  def vcdj_set_iface(self):
    if self.own_ip is not None:
      self.vcdj.set_interface_data(*self.own_ip[1:4])

  def run(self):
    logging.debug("starting main loop")
    while self.keep_running:
      rdy = select(self.socks,[],[],1)[0]
      for sock in rdy:
        if sock == self.keepalive_sock:
          data, addr = self.keepalive_sock.recvfrom(128)
          self.handle_keepalive_packet(data, addr)
        elif sock == self.beat_sock:
          data, addr = self.beat_sock.recvfrom(128)
          self.handle_beat_packet(data, addr)
        elif sock == self.status_sock:
          data, addr = self.status_sock.recvfrom(1158) # max size of status packet (CDJ-3000), can also be smaller
          self.handle_status_packet(data, addr)
      self.cl.gc()
    logging.debug("main loop finished")

  def handle_keepalive_packet(self, data, addr):
    #logging.debug("Broadcast keepalive packet from {}".format(addr))
    try:
      packet = packets.KeepAlivePacket.parse(data)
    except Exception as e:
      logging.warning("Failed to parse keepalive packet from {}, {} bytes: {}".format(addr, len(data), e))
      packets_dump.dump_packet_raw(data)
      return
    if self.is_own_vcdj_keepalive(packet):
      return
    if self.vcdj_conflicts_with_keepalive(packet):
      old_player_number = self.vcdj.player_number
      self.vcdj_auto_set_player_number(5, reserved={packet.content.player_number})
      logging.warning(
        "VCDJ player number %d is already used by %s (%s), falling back to %d",
        old_player_number,
        packet.content.ip_addr,
        packet.model,
        self.vcdj.player_number)
    # both packet types give us enough information to store the client
    if packet["type"] in ["type_ip", "type_status", "type_change"]:
      self.cl.eatKeepalive(packet)
    if self.own_ip is None and len(self.cl.getClientIps()) > 0:
      self.own_ip = guess_own_iface(self.cl.getClientIps())
      if self.own_ip is not None:
        logging.info("Guessed own interface {} ip {} mask {} mac {}".format(*self.own_ip))
        self.vcdj_set_iface()
    packets_dump.dump_keepalive_packet(packet)

  def is_own_vcdj_keepalive(self, packet):
    if packet["type"] not in ["type_ip", "type_status"]:
      return False
    if self.vcdj.ip_addr == "" or self.vcdj.mac_addr == "":
      return False
    return (
      packet.content.ip_addr == self.vcdj.ip_addr and
      packet.content.mac_addr == self.vcdj.mac_addr and
      packet.content.player_number == self.vcdj.player_number
    )

  def vcdj_conflicts_with_keepalive(self, packet):
    if not self.vcdj_player_number_auto:
      return False
    if packet["type"] not in ["type_ip", "type_status"]:
      return False
    if packet.content.player_number != self.vcdj.player_number:
      return False
    return not self.is_own_vcdj_keepalive(packet)

  def handle_beat_packet(self, data, addr):
    #logging.debug("Broadcast beat packet from {}".format(addr))
    try:
      packet = packets.BeatPacket.parse(data)
    except Exception as e:
      logging.warning("Failed to parse beat packet from {}, {} bytes: {}".format(addr, len(data), e))
      packets_dump.dump_packet_raw(data)
      return
    if packet["type"] in ["type_beat", "type_absolute_position", "type_mixer"]:
      self.cl.eatBeat(packet)
    packets_dump.dump_beat_packet(packet)

  def handle_status_packet(self, data, addr):
    #logging.debug("Broadcast status packet from {}".format(addr))
    try:
      packet = packets.StatusPacket.parse(data)
    except Exception as e:
      logging.warning("Failed to parse status packet from {}, {} bytes: {}".format(addr, len(data), e))
      packets_dump.dump_packet_raw(data)
      return
    self.cl.eatStatus(packet)
    packets_dump.dump_status_packet(packet)

  # called whenever a keepalive packet is received
  # arguments of cb: this clientlist object, player number of changed client
  def set_client_keepalive_callback(self, cb=None):
    self.cl.client_keepalive_callback = cb

  # called whenever a status update of a known client is received
  # arguments of cb: this clientlist object, player number of changed client
  def set_client_change_callback(self, cb=None):
    self.cl.client_change_callback = cb

  # called when a player media changes
  # arguments of cb: this clientlist object, player_number, changed slot
  def set_media_change_callback(self, cb=None):
    self.cl.media_change_callback = cb
