"""Support RNMR dialog with crypto address and copy button."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication,
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices

from .theme import COLORS
from .i18n import t

BMAC_URL = "https://buymeacoffee.com/rnmr"

USDT_ADDRESS = "TKy1aQvUbmFqVnvAgiVSE9X1g3QYogWkH9"


class SupportDialog(QDialog):
    """Small modal showing crypto donation address with copy button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Support RNMR"))
        self.setMinimumWidth(420)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Title
        title = QLabel(t("Support RNMR"))
        title.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 14pt; font-weight: bold;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "If you find RNMR useful and would like to support its development:"
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10pt;")
        layout.addWidget(desc)

        # Buy Me a Coffee section
        bmac_label = QLabel(t("BUY ME A COFFEE"))
        bmac_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 9pt;"
            "font-weight: bold; letter-spacing: 1px;"
        )
        layout.addWidget(bmac_label)

        bmac_btn = QPushButton("buymeacoffee.com/rnmr")
        bmac_btn.setStyleSheet(
            "background-color: #FFDD00; color: #000; font-weight: 600;"
            "border: none; border-radius: 6px; padding: 10px 16px;"
            "font-size: 10pt;"
        )
        bmac_btn.setCursor(Qt.PointingHandCursor)
        bmac_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(BMAC_URL))
        )
        layout.addWidget(bmac_btn)

        layout.addSpacing(8)

        # Crypto section
        network_label = QLabel(t("USDT (TRC20 Network)"))
        network_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 9pt;"
            "font-weight: bold; text-transform: uppercase; letter-spacing: 1px;"
        )
        layout.addWidget(network_label)

        # Address row
        addr_layout = QHBoxLayout()
        addr_layout.setSpacing(8)

        addr_label = QLabel(USDT_ADDRESS)
        addr_label.setStyleSheet(
            f"background-color: {COLORS['panel']};"
            f"border: 1px solid {COLORS['border']};"
            "border-radius: 6px;"
            "padding: 8px 10px;"
            f"color: {COLORS['text']};"
            "font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;"
            "font-size: 9pt;"
        )
        addr_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        addr_layout.addWidget(addr_label, stretch=1)

        self._copy_btn = QPushButton(t("Copy"))
        self._copy_btn.setObjectName("primaryButton")
        self._copy_btn.setFixedWidth(70)
        self._copy_btn.clicked.connect(self._copy_address)
        addr_layout.addWidget(self._copy_btn)

        layout.addLayout(addr_layout)

        # Notice
        notice = QLabel(
            "Please make sure to use the TRC20 network when sending USDT.\n"
            "Crypto transactions are non-refundable."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 8pt;"
        )
        layout.addWidget(notice)

        layout.addStretch()

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton(t("Close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _copy_address(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(USDT_ADDRESS)
        self._copy_btn.setText(t("Copied"))
        self._copy_btn.setStyleSheet(
            f"background-color: {COLORS['success']};"
            f"border-color: {COLORS['success']};"
            "color: white; border-radius: 6px; padding: 8px 16px; font-weight: 500;"
        )
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self._reset_copy_btn)

    def _reset_copy_btn(self):
        self._copy_btn.setText(t("Copy"))
        self._copy_btn.setStyleSheet("")
        self._copy_btn.setObjectName("primaryButton")
        self._copy_btn.style().unpolish(self._copy_btn)
        self._copy_btn.style().polish(self._copy_btn)
