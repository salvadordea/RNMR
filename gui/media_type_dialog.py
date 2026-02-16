"""Dialog for choosing media type before TMDB search."""
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)

from .theme import COLORS


# Return codes
SKIP = 0
SERIES = 1
MOVIE = 2
SKIP_ALL = 3


class MediaTypeDialog(QDialog):
    """Prompt the user to confirm or override the auto-detected media type.

    Shown once per title group when ``always_ask_media_type`` is enabled.
    """

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Select Media Type")
        self.setMinimumWidth(460)
        self.setModal(True)

        self._setup_ui(info)

    def _setup_ui(self, info: dict):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header
        header = QLabel("What type of media is this?")
        header.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 12pt; font-weight: bold;"
        )
        layout.addWidget(header)

        # Details
        parsed_title = info.get("parsed_title", "Unknown")
        media_type = info.get("media_type", "series")
        file_count = info.get("file_count", 1)

        filename = info.get("filepath", "")
        if filename:
            filename = Path(filename).name

        details = f"<b>Parsed title:</b> {parsed_title}"
        details += (
            f"<br><b>Auto-detected type:</b> "
            f"{'TV Series' if media_type == 'series' else 'Movie'}"
        )
        details += f"<br><b>Example file:</b> {filename}"

        info_label = QLabel(details)
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: {COLORS['text']};")
        layout.addWidget(info_label)

        # Batch note
        if file_count > 1:
            note = QLabel(
                f"<i>Your selection will apply to all {file_count} files "
                f"with this title.</i>"
            )
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {COLORS['text_muted']};")
            layout.addWidget(note)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        series_btn = QPushButton("TV Series")
        series_btn.setObjectName("primaryButton")
        series_btn.clicked.connect(lambda: self.done(SERIES))

        movie_btn = QPushButton("Movie")
        movie_btn.clicked.connect(lambda: self.done(MOVIE))

        skip_btn = QPushButton("Skip")
        skip_btn.setToolTip("Skip this batch")
        skip_btn.clicked.connect(lambda: self.done(SKIP))

        skip_all_btn = QPushButton("Skip All")
        skip_all_btn.setToolTip(
            "Skip this batch and all future unresolved batches in this scan"
        )
        skip_all_btn.clicked.connect(lambda: self.done(SKIP_ALL))

        btn_layout.addWidget(series_btn)
        btn_layout.addWidget(movie_btn)
        btn_layout.addWidget(skip_btn)
        btn_layout.addWidget(skip_all_btn)

        layout.addLayout(btn_layout)
