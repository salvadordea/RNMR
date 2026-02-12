"""Dialog shown when TMDB auto-detection fails for a title group."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)
from PySide6.QtCore import Qt

from .theme import COLORS


# Return codes
SKIP = 0
SEARCH_MANUALLY = 1
ENTER_ID = 2
SKIP_ALL = 3


class FailedLookupDialog(QDialog):
    """Decision dialog when TMDB lookup returns no results for a title group.

    Shown once per title group, not per file.  The user's choice applies
    to every file that shares the same parsed title.
    """

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)

        self.setWindowTitle("TMDB Lookup Failed")
        self.setMinimumWidth(480)
        self.setModal(True)

        self._setup_ui(info)

    def _setup_ui(self, info: dict):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header
        header = QLabel("TMDB lookup returned no results")
        header.setStyleSheet(
            f"color: {COLORS['warning']}; font-size: 12pt; font-weight: bold;"
        )
        layout.addWidget(header)

        # File info
        filename = info.get("filepath", "")
        if filename:
            from pathlib import Path
            filename = Path(filename).name
        parsed_title = info.get("parsed_title", "Unknown")
        media_type = info.get("media_type", "series")
        seasons = info.get("seasons", [])
        year = info.get("year")
        file_count = info.get("file_count", 1)

        details = f"<b>Parsed title:</b> {parsed_title}"
        details += f"<br><b>Detected type:</b> {'TV Series' if media_type == 'series' else 'Movie'}"
        if seasons:
            season_str = ", ".join(str(s) for s in seasons)
            details += f"<br><b>Seasons detected:</b> {season_str}"
        if year:
            details += f"<br><b>Year:</b> {year}"
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

        search_btn = QPushButton("Search Manually")
        search_btn.setObjectName("primaryButton")
        search_btn.clicked.connect(lambda: self.done(SEARCH_MANUALLY))

        enter_id_btn = QPushButton("Enter TMDB ID")
        enter_id_btn.clicked.connect(lambda: self.done(ENTER_ID))

        skip_btn = QPushButton("Skip")
        skip_btn.setToolTip("Skip this batch")
        skip_btn.clicked.connect(lambda: self.done(SKIP))

        skip_all_btn = QPushButton("Skip All")
        skip_all_btn.setToolTip(
            "Skip this batch and all future unresolved batches in this scan"
        )
        skip_all_btn.clicked.connect(lambda: self.done(SKIP_ALL))

        btn_layout.addWidget(search_btn)
        btn_layout.addWidget(enter_id_btn)
        btn_layout.addWidget(skip_btn)
        btn_layout.addWidget(skip_all_btn)

        layout.addLayout(btn_layout)
