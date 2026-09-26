import logging
from PyQt5.QtWidgets import QComboBox, QHeaderView, QLabel, QPushButton, QSizePolicy, QTableView, QTextEdit, QHBoxLayout, QVBoxLayout, QWidget
from PyQt5.QtGui import QPalette, QStandardItem, QStandardItemModel, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from .resources import resource_path


class AboutDialog(QDialog):
  def __init__(self, parent=None):
    super().__init__(parent)
    self.setWindowTitle("About")
    self.setFixedSize(450, 420)

    title = QLabel("DeckClock", self)
    title.setStyleSheet("QLabel { color: white; font: bold 18pt; }")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)

    logo = QLabel(self)
    logo_pixmap = QPixmap(str(resource_path("logo_white.png")))
    if not logo_pixmap.isNull():
      logo.setPixmap(logo_pixmap.scaledToHeight(108, Qt.SmoothTransformation))
    logo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    logo.setAlignment(Qt.AlignCenter)

    body = QLabel(self)
    body.setOpenExternalLinks(True)
    body.setTextFormat(Qt.RichText)
    body.setWordWrap(True)
    body.setStyleSheet("QLabel { color: white; }")
    body.setText("""
      <p>
        Built to monitor and to generate timecode from Pioneer ProDJ Link transport data.
      </p>
      <p>
        Based largely on the work of the
        <a href="https://github.com/flesniak/python-prodj-link" style="color: #00A0FF;text-decoration : none">python-prodj-link</a>
        project.
      </p>
      <p>
        This software includes components licensed under the Apache License,
        Version 2.0.
      </p>
        <p>
                 ShowEngineering, its logo and other branding &copy; 2026 ShowEngineering, all rights reserved.
        </p>
      <p>
        Pioneer, CDJ, XDJ, DJM, rekordbox and related names are trademarks of
        their respective owners. This project is not affiliated with or endorsed
        by AlphaTheta/Pioneer DJ.
      </p>
    """)

    close_button = QPushButton("Close", self)
    close_button.setStyleSheet("QPushButton {color : white; background-color : black; border: 2px solid #e7e7e7; border-radius: 2px; font-size: 16px; padding-top : 8px; padding-bottom: 8px;}")
    close_button.clicked.connect(self.accept)

    layout = QVBoxLayout(self)
    layout.addWidget(title)
    layout.addWidget(logo)
    layout.addWidget(body)
    layout.addWidget(close_button)



