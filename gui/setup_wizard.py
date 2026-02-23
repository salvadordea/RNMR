"""First-run setup wizard for TMDB API key configuration."""
import requests

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QStackedWidget, QWidget,
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices

from .theme import COLORS
from .i18n import t

TMDB_API_URL = "https://www.themoviedb.org/settings/api"
TMDB_CONFIG_ENDPOINT = "https://api.themoviedb.org/3/configuration"


def validate_api_key(api_key: str) -> tuple[bool, str]:
    """Test an API key against the TMDB /configuration endpoint.

    Returns (success, message).
    """
    if not api_key or not api_key.strip():
        return False, "API key cannot be empty."
    try:
        resp = requests.get(
            TMDB_CONFIG_ENDPOINT,
            params={"api_key": api_key.strip()},
            timeout=10,
        )
        if resp.status_code == 200:
            return True, "API key is valid."
        if resp.status_code == 401:
            return False, "Invalid API key (401 Unauthorized)."
        return False, f"Unexpected response: HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return False, "Connection timed out. Check your internet connection."
    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {e}"


class SetupWizard(QDialog):
    """Three-step first-run wizard for TMDB API key setup.

    Steps:
      1. Explanation -- why a key is needed, link to get one.
      2. Input + validation -- paste key, validate against TMDB.
      3. Confirmation -- success message, continue button.

    The validated key is available via ``get_api_key()`` after
    the dialog is accepted.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(t("RNMR Setup"))
        self.setMinimumWidth(520)
        self.setMinimumHeight(340)
        self.setModal(True)

        self._api_key: str = ""

        self._setup_ui()

    def get_api_key(self) -> str:
        return self._api_key

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._create_step1())
        self._stack.addWidget(self._create_step2())
        self._stack.addWidget(self._create_step3())
        layout.addWidget(self._stack)

    # -- Step 1: Explanation ---------------------------------------

    def _create_step1(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        title = QLabel(t("TMDB API Key Required"))
        title.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 14pt; font-weight: bold;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        explanation = QLabel(
            "RNMR uses <b>The Movie Database (TMDB)</b> to identify and "
            "rename your media files.\n\n"
            "To use this feature you need a free TMDB API key.\n"
            "Creating an account and generating a key takes about a minute."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 10pt; line-height: 1.5;"
        )
        explanation.setAlignment(Qt.AlignCenter)
        layout.addWidget(explanation)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        get_key_btn = QPushButton(t("Get API Key"))
        get_key_btn.setObjectName("primaryButton")
        get_key_btn.setToolTip("Opens themoviedb.org in your browser")
        get_key_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(TMDB_API_URL))
        )
        btn_layout.addWidget(get_key_btn)

        have_key_btn = QPushButton(t("I Already Have One"))
        have_key_btn.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        btn_layout.addWidget(have_key_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return page

    # -- Step 2: Input + Validation --------------------------------

    def _create_step2(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        title = QLabel(t("Enter Your API Key"))
        title.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 14pt; font-weight: bold;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        hint = QLabel(
            "Paste your TMDB API key (v3 auth) below.\n"
            "It will be validated before saving."
        )
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {COLORS['text_muted']};")
        layout.addWidget(hint)

        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText(t("Paste your TMDB API key here..."))
        self._key_edit.setMinimumHeight(36)
        layout.addWidget(self._key_edit)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        back_btn = QPushButton(t("Back"))
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        btn_layout.addWidget(back_btn)

        btn_layout.addStretch()

        self._validate_btn = QPushButton(t("Validate && Save"))
        self._validate_btn.setObjectName("primaryButton")
        self._validate_btn.clicked.connect(self._on_validate)
        btn_layout.addWidget(self._validate_btn)

        layout.addLayout(btn_layout)

        return page

    # -- Step 3: Confirmation --------------------------------------

    def _create_step3(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        title = QLabel(t("Setup Complete"))
        title.setStyleSheet(
            f"color: {COLORS['success']}; font-size: 14pt; font-weight: bold;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        msg = QLabel("API key validated successfully.\nYou're ready to start.")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet(f"color: {COLORS['text']}; font-size: 11pt;")
        layout.addWidget(msg)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        continue_btn = QPushButton(t("Continue"))
        continue_btn.setObjectName("primaryButton")
        continue_btn.clicked.connect(self.accept)
        btn_layout.addWidget(continue_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return page

    # ------------------------------------------------------------------
    # Validation logic
    # ------------------------------------------------------------------

    def _on_validate(self):
        key = self._key_edit.text().strip()
        if not key:
            self._status_label.setText(t("Please enter an API key."))
            self._status_label.setStyleSheet(
                f"color: {COLORS['warning']}; font-weight: bold;"
            )
            return

        self._validate_btn.setEnabled(False)
        self._validate_btn.setText(t("Validating..."))
        self._status_label.setText("")

        # Force UI repaint before blocking network call
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        ok, msg = validate_api_key(key)

        self._validate_btn.setEnabled(True)
        self._validate_btn.setText(t("Validate && Save"))

        if ok:
            self._api_key = key
            self._stack.setCurrentIndex(2)
        else:
            self._status_label.setText(msg)
            self._status_label.setStyleSheet(
                f"color: {COLORS['error']}; font-weight: bold;"
            )
