"""Dialog for setting TMDB ID manually."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLineEdit, QLabel, QComboBox,
    QGroupBox, QMessageBox
)
from PySide6.QtCore import Qt

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from renamer.id_mapping import parse_tmdb_url, IDMapping
from renamer.tmdb import TMDBClient, TMDBError
from .theme import COLORS


class SetIDDialog(QDialog):
    """Dialog for manually setting TMDB ID."""

    def __init__(self, filename: str, current_type: str = "series", parent=None):
        super().__init__(parent)

        self.filename = filename
        self.result_id: int | None = None
        self.result_type: str | None = None
        self.result_title: str | None = None

        self.setWindowTitle("Set TMDB ID")
        self.setMinimumWidth(450)

        self._setup_ui(current_type)

    def _setup_ui(self, current_type: str):
        """Setup dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # File info
        info_label = QLabel(f"<b>File:</b> {self.filename}")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Input group
        input_group = QGroupBox("TMDB Identifier")
        input_layout = QFormLayout(input_group)

        # ID input
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("Enter TMDB ID, URL, or tv:12345 / movie:12345")
        self.id_input.textChanged.connect(self._on_input_changed)
        input_layout.addRow("ID / URL:", self.id_input)

        # Media type
        self.type_combo = QComboBox()
        self.type_combo.addItems(["TV Series", "Movie"])
        if current_type == "movie":
            self.type_combo.setCurrentIndex(1)
        input_layout.addRow("Type:", self.type_combo)

        layout.addWidget(input_group)

        # Help text
        help_label = QLabel(
            "<b>Accepted formats:</b><br>"
            "- TMDB ID: <code>12345</code><br>"
            "- With type: <code>tv:12345</code> or <code>movie:12345</code><br>"
            "- TMDB URL: <code>https://themoviedb.org/tv/12345</code>"
        )
        help_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # Lookup result
        self.result_group = QGroupBox("Lookup Result")
        result_layout = QVBoxLayout(self.result_group)

        self.result_label = QLabel("Enter an ID to verify...")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)

        self.lookup_btn = QPushButton("Verify ID")
        self.lookup_btn.clicked.connect(self._lookup_id)
        result_layout.addWidget(self.lookup_btn)

        layout.addWidget(self.result_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setEnabled(False)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

    def _on_input_changed(self, text: str):
        """Handle input text change."""
        # Try to parse and auto-detect type
        tmdb_id, media_type = parse_tmdb_url(text)

        if media_type:
            self.type_combo.setCurrentIndex(0 if media_type == "series" else 1)

        # Reset verification
        self.result_label.setText("Enter an ID to verify...")
        self.result_label.setStyleSheet("")
        self.save_btn.setEnabled(False)
        self.result_id = None
        self.result_type = None
        self.result_title = None

    def _lookup_id(self):
        """Lookup the ID on TMDB."""
        text = self.id_input.text().strip()
        if not text:
            return

        tmdb_id, media_type = parse_tmdb_url(text)

        if tmdb_id is None:
            self.result_label.setText("Invalid ID format")
            self.result_label.setStyleSheet(f"color: {COLORS['error']};")
            return

        # Use combo box type if not detected from input
        if media_type is None:
            media_type = "series" if self.type_combo.currentIndex() == 0 else "movie"

        self.result_label.setText("Looking up...")

        try:
            client = TMDBClient(verbose=False)

            if media_type == "series":
                # Direct lookup by ID
                data = client._request(f"/tv/{tmdb_id}")
                if data:
                    name = data.get("original_name") or data.get("name", "Unknown")
                    year = ""
                    if data.get("first_air_date"):
                        year = f" ({data['first_air_date'][:4]})"

                    self.result_label.setText(
                        f"<b>Found:</b> {name}{year}<br>"
                        f"<span style='color: {COLORS['text_muted']};'>ID: {tmdb_id} (TV Series)</span>"
                    )
                    self.result_label.setStyleSheet(f"color: {COLORS['success']};")
                    self.result_id = tmdb_id
                    self.result_type = "series"
                    self.result_title = name
                    self.save_btn.setEnabled(True)
                else:
                    self.result_label.setText(f"TV Series with ID {tmdb_id} not found")
                    self.result_label.setStyleSheet(f"color: {COLORS['error']};")
            else:
                data = client._request(f"/movie/{tmdb_id}")
                if data:
                    name = data.get("original_title") or data.get("title", "Unknown")
                    year = ""
                    if data.get("release_date"):
                        year = f" ({data['release_date'][:4]})"

                    self.result_label.setText(
                        f"<b>Found:</b> {name}{year}<br>"
                        f"<span style='color: {COLORS['text_muted']};'>ID: {tmdb_id} (Movie)</span>"
                    )
                    self.result_label.setStyleSheet(f"color: {COLORS['success']};")
                    self.result_id = tmdb_id
                    self.result_type = "movie"
                    self.result_title = name
                    self.save_btn.setEnabled(True)
                else:
                    self.result_label.setText(f"Movie with ID {tmdb_id} not found")
                    self.result_label.setStyleSheet(f"color: {COLORS['error']};")

        except TMDBError as e:
            self.result_label.setText(f"TMDB Error: {e}")
            self.result_label.setStyleSheet(f"color: {COLORS['error']};")
        except Exception as e:
            self.result_label.setText(f"Error: {e}")
            self.result_label.setStyleSheet(f"color: {COLORS['error']};")

    def _save(self):
        """Save the mapping and close."""
        if self.result_id and self.result_type:
            self.accept()

    def get_result(self) -> tuple[int | None, str | None, str | None]:
        """Get the result after dialog closes."""
        return self.result_id, self.result_type, self.result_title
