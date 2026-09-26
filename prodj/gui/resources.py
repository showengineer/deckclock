import sys
from pathlib import Path


def resource_path(name):
  if hasattr(sys, "_MEIPASS"):
    return Path(sys._MEIPASS) / name
  return Path(__file__).resolve().parents[2] / name
