"""Dialog for selecting a TMDB match with interactive search."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QWidget, QFrame, QSizePolicy, QLineEdit, QComboBox,
)
from PySide6.QtCore import Qt, QSize, QThread, Signal, Slot
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from .theme import COLORS


# Dialog result codes
CONFIRM = QDialog.Accepted
SKIP = 100
SKIP_ALL = 101

POSTER_HEIGHT = 80
POSTER_WIDTH = 54  # roughly 2:3 aspect ratio


class _SearchWorker(QThread):
    """Background thread for TMDB search queries."""

    finished = Signal(list, bool)  # (results, is_movie)
    error = Signal(str)

    def __init__(self, api_key: str, query: str, is_movie: bool, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._query = query
        self._is_movie = is_movie

    def run(self):
        import requests
        try:
            endpoint = "/search/movie" if self._is_movie else "/search/tv"
            url = f"https://api.themoviedb.org/3{endpoint}"
            resp = requests.get(
                url,
                params={"api_key": self._api_key, "query": self._query},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])[:5]
                self.finished.emit(results, self._is_movie)
            else:
                self.error.emit(f"TMDB returned HTTP {resp.status_code}")
        except Exception as e:
            self.error.emit(str(e))


class _ResultCard(QFrame):
    """Clickable card representing one TMDB search result."""

    _NORMAL_STYLE = (
        f"background-color: {COLORS['panel']};"
        f"border: 2px solid {COLORS['border']};"
        "border-radius: 8px;"
        "padding: 8px;"
    )
    _SELECTED_STYLE = (
        f"background-color: {COLORS['panel_light']};"
        f"border: 2px solid {COLORS['accent']};"
        "border-radius: 8px;"
        "padding: 8px;"
    )

    def __init__(self, result: dict, is_movie: bool, parent=None):
        super().__init__(parent)
        self.result = result
        self._is_movie = is_movie
        self._selected = False

        self.setStyleSheet(self._NORMAL_STYLE)
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)

        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(12)

        # Poster placeholder
        self.poster_label = QLabel()
        self.poster_label.setFixedSize(POSTER_WIDTH, POSTER_HEIGHT)
        self.poster_label.setAlignment(Qt.AlignCenter)
        self.poster_label.setStyleSheet(
            f"background-color: {COLORS['border']};"
            "border-radius: 4px;"
            f"color: {COLORS['text_muted']};"
            "font-size: 9pt;"
        )
        self.poster_label.setText("Film")
        layout.addWidget(self.poster_label)

        # Text info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        title_field = "title" if self._is_movie else "name"
        date_field = "release_date" if self._is_movie else "first_air_date"

        title_text = self.result.get(title_field, "Unknown")
        date_text = self.result.get(date_field, "")
        year_text = date_text[:4] if date_text and len(date_text) >= 4 else ""
        tmdb_id = self.result.get("id", "")

        title_label = QLabel(f"<b>{title_text}</b>")
        title_label.setWordWrap(True)
        title_label.setStyleSheet(f"color: {COLORS['text']}; border: none;")
        info_layout.addWidget(title_label)

        meta_parts = []
        if year_text:
            meta_parts.append(year_text)
        meta_parts.append(f"ID: {tmdb_id}")

        # Show original title if different
        orig_field = "original_title" if self._is_movie else "original_name"
        orig_title = self.result.get(orig_field, "")
        if orig_title and orig_title != title_text:
            meta_parts.append(f'"{orig_title}"')

        meta_label = QLabel(" | ".join(meta_parts))
        meta_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 9pt; border: none;"
        )
        info_layout.addWidget(meta_label)

        # Overview snippet
        overview = self.result.get("overview", "")
        if overview:
            snippet = overview[:120] + ("..." if len(overview) > 120 else "")
            overview_label = QLabel(snippet)
            overview_label.setWordWrap(True)
            overview_label.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 8pt; border: none;"
            )
            info_layout.addWidget(overview_label)

        info_layout.addStretch()
        layout.addLayout(info_layout, stretch=1)

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool):
        self._selected = value
        self.setStyleSheet(
            self._SELECTED_STYLE if value else self._NORMAL_STYLE
        )

    def set_poster(self, pixmap: QPixmap):
        scaled = pixmap.scaled(
            QSize(POSTER_WIDTH, POSTER_HEIGHT),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.poster_label.setPixmap(scaled)

    def mousePressEvent(self, event):
        # Bubble up -- the dialog handles selection logic
        super().mousePressEvent(event)
        self.parent_dialog().select_card(self)

    def parent_dialog(self) -> "TMDBSelectDialog":
        widget = self.parent()
        while widget is not None:
            if isinstance(widget, TMDBSelectDialog):
                return widget
            widget = widget.parent()
        raise RuntimeError("Card is not inside a TMDBSelectDialog")


class TMDBSelectDialog(QDialog):
    """Display TMDB results as selectable cards with interactive search.

    Return values:
      - ``Accepted`` (Confirm): user picked a result.
      - ``SKIP``: skip this batch.
      - ``SKIP_ALL``: skip this and all remaining batches.

    Use ``get_result()`` after ``Accepted`` to retrieve the selection.
    """

    def __init__(
        self,
        results: list[dict],
        parsed_title: str,
        media_type: str,
        file_count: int = 1,
        api_key: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Select TMDB Match")
        self.setMinimumWidth(540)
        self.setMinimumHeight(420)
        self.setModal(True)

        self._results = results
        self._parsed_title = parsed_title
        self._media_type = media_type
        self._file_count = file_count
        self._is_movie = media_type == "movie"
        self._api_key = api_key
        self._cards: list[_ResultCard] = []
        self._selected_card: _ResultCard | None = None
        self._search_worker: _SearchWorker | None = None

        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_poster_loaded)
        self._pending_posters: dict[str, _ResultCard] = {}

        self._setup_ui()
        self._populate_results(results, self._is_movie)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        muted = COLORS["text_muted"]
        header = QLabel(
            f"<b>Select TMDB Match</b> "
            f"<span style='color:{muted};'>"
            f"for \"{self._parsed_title}\"</span>"
        )
        header.setWordWrap(True)
        header.setStyleSheet("font-size: 11pt;")
        layout.addWidget(header)

        if self._file_count > 1:
            note = QLabel(
                f"<i>Your selection will apply to all {self._file_count} "
                f"files with this title.</i>"
            )
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {COLORS['text_muted']};")
            layout.addWidget(note)

        # Search controls
        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search TMDB...")
        self._search_input.setText(self._parsed_title)
        self._search_input.setMinimumHeight(32)
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input, stretch=1)

        self._type_combo = QComboBox()
        self._type_combo.addItem("TV Series", "series")
        self._type_combo.addItem("Movie", "movie")
        self._type_combo.setCurrentIndex(0 if not self._is_movie else 1)
        self._type_combo.setMinimumHeight(32)
        self._type_combo.setMinimumWidth(100)
        search_layout.addWidget(self._type_combo)

        self._search_btn = QPushButton("Search")
        self._search_btn.setObjectName("primaryButton")
        self._search_btn.setMinimumHeight(32)
        self._search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(self._search_btn)

        layout.addLayout(search_layout)

        # Loading indicator
        self._loading_label = QLabel("Searching...")
        self._loading_label.setAlignment(Qt.AlignCenter)
        self._loading_label.setStyleSheet(
            f"color: {COLORS['accent']}; font-style: italic; padding: 4px;"
        )
        self._loading_label.setVisible(False)
        layout.addWidget(self._loading_label)

        # Scrollable card area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { border: none; }")

        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setSpacing(8)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.addStretch()

        self._scroll.setWidget(self._card_container)
        layout.addWidget(self._scroll, stretch=1)

        # No results message (hidden by default)
        self._no_results_label = QLabel("No matches found.")
        self._no_results_label.setAlignment(Qt.AlignCenter)
        self._no_results_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11pt; padding: 20px;"
        )
        self._no_results_label.setVisible(False)
        layout.addWidget(self._no_results_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._confirm_btn = QPushButton("Confirm Selection")
        self._confirm_btn.setObjectName("primaryButton")
        self._confirm_btn.clicked.connect(self.accept)

        skip_btn = QPushButton("Skip")
        skip_btn.setToolTip("Skip this batch")
        skip_btn.clicked.connect(lambda: self.done(SKIP))

        skip_all_btn = QPushButton("Skip All")
        skip_all_btn.setToolTip(
            "Skip this batch and all remaining unresolved batches"
        )
        skip_all_btn.clicked.connect(lambda: self.done(SKIP_ALL))

        btn_layout.addStretch()
        btn_layout.addWidget(self._confirm_btn)
        btn_layout.addWidget(skip_btn)
        btn_layout.addWidget(skip_all_btn)

        layout.addLayout(btn_layout)

    # -- Result population -----------------------------------------------

    def _populate_results(self, results: list[dict], is_movie: bool):
        """Replace current cards with new results."""
        # Clear existing cards
        self._selected_card = None
        self._pending_posters.clear()
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        # Remove the trailing stretch
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            # Stretch items have no widget
            if item.widget():
                item.widget().setParent(None)

        if not results:
            self._no_results_label.setVisible(True)
            self._scroll.setVisible(False)
            self._confirm_btn.setEnabled(False)
            self._card_layout.addStretch()
            return

        self._no_results_label.setVisible(False)
        self._scroll.setVisible(True)
        self._confirm_btn.setEnabled(True)

        for result in results:
            card = _ResultCard(result, is_movie, parent=self._card_container)
            self._cards.append(card)
            self._card_layout.addWidget(card)

        self._card_layout.addStretch()

        # Load posters
        self._load_posters()

        # Auto-select first card
        if self._cards:
            self.select_card(self._cards[0])

    # -- Search -----------------------------------------------------------

    def _on_search(self):
        query = self._search_input.text().strip()
        if not query:
            return
        if not self._api_key:
            return

        # Prevent overlapping searches
        if self._search_worker is not None and self._search_worker.isRunning():
            return

        is_movie = self._type_combo.currentData() == "movie"

        self._search_btn.setEnabled(False)
        self._loading_label.setVisible(True)

        self._search_worker = _SearchWorker(
            self._api_key, query, is_movie, parent=self,
        )
        self._search_worker.finished.connect(self._on_search_finished)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.start()

    @Slot(list, bool)
    def _on_search_finished(self, results: list, is_movie: bool):
        self._search_btn.setEnabled(True)
        self._loading_label.setVisible(False)
        self._is_movie = is_movie
        self._populate_results(results, is_movie)

    @Slot(str)
    def _on_search_error(self, message: str):
        self._search_btn.setEnabled(True)
        self._loading_label.setVisible(False)
        self._loading_label.setText(f"Search failed: {message}")
        self._loading_label.setStyleSheet(
            f"color: {COLORS['error']}; font-style: italic; padding: 4px;"
        )
        self._loading_label.setVisible(True)

    # -- Card selection ---------------------------------------------------

    def select_card(self, card: _ResultCard):
        if self._selected_card is not None:
            self._selected_card.selected = False
        card.selected = True
        self._selected_card = card

    def get_result(self) -> tuple[int | None, str | None, str | None]:
        """Return ``(tmdb_id, media_type, title)`` of the selected card.

        Returns ``(None, None, None)`` when no card is selected.
        """
        if self._selected_card is None:
            return None, None, None
        r = self._selected_card.result
        title_field = "title" if self._is_movie else "name"
        return (
            r.get("id"),
            "movie" if self._is_movie else "series",
            r.get(title_field, ""),
        )

    # -- Poster loading ---------------------------------------------------

    def _load_posters(self):
        for card in self._cards:
            poster_path = card.result.get("poster_path")
            if not poster_path:
                continue
            url = f"https://image.tmdb.org/t/p/w200{poster_path}"
            self._pending_posters[url] = card
            request = QNetworkRequest(url)
            self._nam.get(request)

    def _on_poster_loaded(self, reply: QNetworkReply):
        url = reply.url().toString()
        card = self._pending_posters.pop(url, None)
        if card is None or reply.error() != QNetworkReply.NoError:
            reply.deleteLater()
            return

        data = reply.readAll().data()
        image = QImage()
        if image.loadFromData(data):
            card.set_poster(QPixmap.fromImage(image))
        reply.deleteLater()
