#!/usr/bin/env python3

import logging
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QPalette
from PyQt5.QtCore import Qt, QTimer
import signal
import argparse

from prodj.core.prodj import ProDj, PortInUseError
from prodj.gui.gui import Gui
from prodj.gui.gui_settings import LtcSettings
from prodj.audio.output import OutputConfig, format_output_devices, import_sounddevice
from prodj.timecode.ltc_service import LTCService

def arg_size(value):
  number = int(value)
  if number < 1000 or number > 60000:
    raise argparse.ArgumentTypeError("%s is not between 1000 and 60000".format(value))
  return number

def arg_layout(value):
  if value not in ["xy", "yx", "xx", "yy", "row", "column"]:
    raise argparse.ArgumentTypeError("%s is not a value from the list xy, yx, xx, yy, row or column".format(value))
  return value

def arg_player_slots(value):
  number = int(value)
  if number not in [4, 6]:
    raise argparse.ArgumentTypeError("%s is not 4 or 6".format(value))
  return number

parser = argparse.ArgumentParser(description='DeckClock')
provider_group = parser.add_mutually_exclusive_group()
provider_group.add_argument('--disable-pdb', dest='enable_pdb', action='store_false', help='Disable PDB provider')
provider_group.add_argument('--disable-dbc', dest='enable_dbc', action='store_false', help='Disable DBClient provider')
parser.add_argument('--color-preview', action='store_true', help='Show NXS2 colored preview waveforms')
parser.add_argument('--color-waveform', action='store_true', help='Show NXS2 colored big waveforms')
parser.add_argument('-c', '--color', action='store_true', help='Shortcut for --color-preview and --color-waveform', default=True)
parser.add_argument('-q', '--quiet', action='store_const', dest='loglevel', const=logging.WARNING, help='Only display warning messages', default=logging.INFO)
parser.add_argument('-d', '--debug', action='store_const', dest='loglevel', const=logging.DEBUG, help='Display verbose debugging information')
parser.add_argument('--dump-packets', action='store_const', dest='loglevel', const=0, help='Dump packet fields for debugging', default=logging.INFO)
parser.add_argument('--chunk-size', dest='chunk_size', help='Chunk size of NFS downloads (high values may be faster but fail on some networks)', type=arg_size, default=None)
parser.add_argument('-f', '--fullscreen', action='store_true', help='Start with fullscreen window')
parser.add_argument('-l', '--layout', dest='layout', help='Display layout, values are xy (default), yx, xx, yy, row or column', type=arg_layout, default="xy")
parser.add_argument('--player-slots', type=arg_player_slots, default=4, help='Show a fixed number of player sections, either 4 or 6')
parser.add_argument('--vcdj-player', type=int, default=None, help='Virtual CDJ player number, defaults to the first free number after player-slots')
parser.add_argument('--list-audio-devices', action='store_true', help='List audio output devices and exit')
parser.add_argument('--ltc-player', type=int, default=None, help='Generate LTC from this player number')
parser.add_argument('--ltc-device', type=int, default=None, help='Audio output device index for LTC')
parser.add_argument('--ltc-channel', type=int, default=0, help='Zero-based output channel for LTC')
parser.add_argument('--ltc-fps', type=float, default=25, help='LTC frame rate')
parser.add_argument('--ltc-sample-rate', type=int, default=48000, help='LTC audio sample rate')
parser.add_argument('--ltc-blocksize', type=int, default=512, help='LTC audio callback block size')
parser.add_argument('--ltc-volume', type=float, default=0.8, help='LTC output volume')
parser.add_argument('--ltc-compensation-ms', type=float, default=0, help='Generate LTC this many milliseconds ahead to compensate fixed output latency')
parser.add_argument('--ltc-buffer-ms', type=float, default=None, help='Override target producer buffer for LTC audio in milliseconds')

args = parser.parse_args()

logging.basicConfig(level=args.loglevel, format='%(levelname)-7s %(module)s: %(message)s')

if args.list_audio_devices:
  print(format_output_devices())
  raise SystemExit(0)

prodj = ProDj()
prodj.data.pdb_enabled = args.enable_pdb
prodj.data.dbc_enabled = args.enable_dbc
if args.chunk_size is not None:
  prodj.nfs.setDownloadChunkSize(args.chunk_size)
app = QApplication([])
gui = Gui(
  prodj,
  show_color_waveform=args.color_waveform or args.color,
  show_color_preview=args.color_preview or args.color,
  arg_layout=args.layout,
  player_slots=args.player_slots,
)
initial_ltc_settings = LtcSettings(
  device=args.ltc_device,
  output_channel=args.ltc_channel,
  fps=args.ltc_fps,
  sample_rate=args.ltc_sample_rate,
  blocksize=args.ltc_blocksize,
  volume=args.ltc_volume,
  compensation_ms=args.ltc_compensation_ms,
  buffer_ms=args.ltc_buffer_ms,
)
gui.setLtcSettings(initial_ltc_settings)
gui.setLtcAvailable(True)
if args.fullscreen:
  gui.setWindowState(Qt.WindowFullScreen | Qt.WindowMaximized | Qt.WindowActive)

pal = app.palette()
pal.setColor(QPalette.Window, Qt.black)
pal.setColor(QPalette.Base, Qt.black)
pal.setColor(QPalette.Button, Qt.black)
pal.setColor(QPalette.WindowText, Qt.white)
pal.setColor(QPalette.Text, Qt.white)
pal.setColor(QPalette.ButtonText, Qt.white)
pal.setColor(QPalette.Disabled, QPalette.ButtonText, Qt.gray)
app.setPalette(pal)

signal.signal(signal.SIGINT, lambda s,f: app.quit())

prodj.set_client_keepalive_callback(gui.keepalive_callback)
prodj.set_client_change_callback(gui.client_change_callback)
prodj.set_media_change_callback(gui.media_callback)
try:
  prodj.start()
except PortInUseError as e:
  logging.error("%s", e)
  QMessageBox.critical(None, "DeckClock", str(e))
  raise SystemExit(1)
if args.vcdj_player is not None:
  prodj.vcdj_set_player_number(args.vcdj_player)
  prodj.vcdj_enable()
else:
  prodj.vcdj_enable(args.player_slots + 1)

ltc_state = {
  "service": None,
  "settings": initial_ltc_settings,
  "player_number": args.ltc_player,
}

def get_ltc_device_info(settings):
  sd = import_sounddevice()
  device_info = sd.query_devices(settings.device, "output")
  hostapi_info = sd.query_hostapis(device_info["hostapi"])
  return device_info, hostapi_info

def ltc_hostapi_label(hostapi_name):
  lower_name = hostapi_name.lower()
  if "asio" in lower_name:
    return "ASIO"
  if "directsound" in lower_name:
    return "DirectSound"
  if "wasapi" in lower_name or "wdm" in lower_name:
    return "WDM"
  return hostapi_name

def create_ltc_service(settings):
  device_info, _ = get_ltc_device_info(settings)
  sample_rate = settings.sample_rate
  if settings.sample_rate is None:
    sample_rate = int(device_info["default_samplerate"])

  ltc_config = OutputConfig(
    device=settings.device,
    sample_rate=sample_rate,
    channels=settings.output_channel + 1,
    blocksize=settings.blocksize,
  )
  return LTCService(
    prodj,
    ltc_state["player_number"],
    output_config=ltc_config,
    output_channel=settings.output_channel,
    fps=settings.fps,
    volume=settings.volume,
    latency_compensation_ms=settings.compensation_ms,
    target_buffer_ms=settings.buffer_ms,
  )

def set_ltc_footer_status(service):
  device_info, hostapi_info = get_ltc_device_info(service.output_config)
  text = "{} device {} opened at {:g} kHz".format(
    ltc_hostapi_label(hostapi_info["name"]),
    device_info["name"],
    service.output_config.sample_rate / 1000,
  )
  output_latency_ms = service.output_latency_ms()
  if output_latency_ms is not None:
    text += " / output latency {:.1f} ms".format(output_latency_ms)
  gui.setFooterText(text)

def refresh_ltc_footer_status():
  service = ltc_state["service"]
  if service is not None and service.running:
    set_ltc_footer_status(service)

def apply_ltc_settings(settings):
  was_enabled = gui.isLtcEnabled()
  if ltc_state["service"] is not None:
    ltc_state["service"].stop()
  ltc_state["settings"] = settings
  try:
    ltc_state["service"] = create_ltc_service(settings)
  except Exception as e:
    logging.exception("Failed to configure LTC output: %s", e)
    ltc_state["service"] = None
    gui.setLtcAvailable(False)
    gui.setLtcEnabled(False)
    return
  gui.setLtcAvailable(True)
  if was_enabled:
    start_ltc_service()

def start_ltc_service():
  if ltc_state["service"] is None:
    return
  try:
    ltc_state["service"].start()
    set_ltc_footer_status(ltc_state["service"])
  except Exception as e:
    logging.exception("Failed to start LTC output: %s", e)
    gui.setLtcEnabled(False)

def assign_ltc_player(player_number):
  was_enabled = gui.isLtcEnabled()
  if ltc_state["service"] is not None:
    ltc_state["service"].stop()
  if player_number <= 0:
    ltc_state["player_number"] = None
    ltc_state["service"] = create_ltc_service(ltc_state["settings"])
    gui.setLtcAssignedPlayer(None)
    if was_enabled:
      start_ltc_service()
    return
  ltc_state["player_number"] = player_number
  gui.setLtcAssignedPlayer(player_number)
  ltc_state["service"] = create_ltc_service(ltc_state["settings"])
  gui.setLtcAvailable(True)
  if was_enabled:
    start_ltc_service()

def set_ltc_enabled(enabled):
  if ltc_state["service"] is None:
    apply_ltc_settings(ltc_state["settings"])
  if ltc_state["service"] is None:
    return
  if enabled:
    start_ltc_service()
  else:
    ltc_state["service"].stop()
    gui.setFooterText("No audio devices opened")

gui.ltc_settings_signal.connect(apply_ltc_settings)
gui.ltc_enabled_signal.connect(set_ltc_enabled)
gui.ltc_assign_signal.connect(assign_ltc_player)

ltc_status_timer = QTimer()
ltc_status_timer.timeout.connect(refresh_ltc_footer_status)
ltc_status_timer.start(1000)

if args.ltc_player is not None:
  gui.setLtcAssignedPlayer(args.ltc_player)
  apply_ltc_settings(initial_ltc_settings)
  if ltc_state["service"] is not None:
    gui.setLtcEnabled(True)
    start_ltc_service()

app.exec()
logging.info("Shutting down...")
if ltc_state["service"] is not None:
  ltc_state["service"].stop()
prodj.stop()
