"""TMDB manual search dialog."""
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QObject

sys.path.insert(0, str(Path(__file__).parent.parent))

from renamer.tmdb import TMDBClient, TMDBError
from .theme import COLORS


class SearchWorker(QObject):
    """Runs TMDB search in a background thread."""

    results_ready = Signal(list)
    error = Signal(str)

    def __init__(self, query: str, media_type: str, api_key: str | None = None):
        super().__init__()
        self.query = query
        self.media_type = media_type
        self._api_key = api_key

    def run(self):
        try:
            client = TMDBClient(api_key=self._api_key, verbose=False)
            if self.media_type == "series":
                data = client._request("/search/tv", {"query": self.query})
            else:
                data = client._request("/search/movie", {"query": self.query})

            if data and data.get("results"):
                self.results_ready.emit(data["results"])
            else:
                self.results_ready.emit([])
        except TMDBError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(str(e))


class TMDBSearchDialog(QDialog):
    """Dialog for manually searching TMDB.

    Returns the identity of a series or movie (TMDB ID + type + title).
    Season/episode handling is left to the caller -- each file already
    carries its own parsed season and episode numbers.
    """

    def __init__(
        self,
        parsed_title: str = "",
        media_type: str = "series",
        api_key: str | None = None,
        parent=None,
    ):
        super().__init__(parent)

        self.setWindowTitle("Search TMDB")
        self.setMinimumSize(650, 450)
        self.setModal(True)

        self._result_id: int | None = None
        self._result_type: str | None = None
        self._result_title: str | None = None
        self._search_thread: QThread | None = None
        self._raw_results: list[dict] = []
        self._api_key = api_key

        self._setup_ui(parsed_title, media_type)

    def _setup_ui(self, parsed_title: str, media_type: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Search controls
        search_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search title...")
        self.search_input.setText(parsed_title)
        self.search_input.returnPressed.connect(self._do_search)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["TV Series", "Movie"])
        if media_type == "movie":
            self.type_combo.setCurrentIndex(1)

        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("primaryButton")
        self.search_btn.clicked.connect(self._do_search)

        search_layout.addWidget(self.search_input, stretch=1)
        search_layout.addWidget(self.type_combo)
        search_layout.addWidget(self.search_btn)

        layout.addLayout(search_layout)

        # Status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        layout.addWidget(self.status_label)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Title", "Original Title", "Year", "TMDB ID"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 90)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(self._on_double_click)

        layout.addWidget(self.table, stretch=1)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        self.select_btn = QPushButton("Select")
        self.select_btn.setObjectName("primaryButton")
        self.select_btn.setEnabled(False)
        self.select_btn.clicked.connect(self._on_select)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.select_btn)

        layout.addLayout(btn_layout)

    def _do_search(self):
        query = self.search_input.text().strip()
        if not query:
            return

        self._cleanup_thread()

        media_type = "series" if self.type_combo.currentIndex() == 0 else "movie"

        self.search_btn.setEnabled(False)
        self.status_label.setText("Searching...")
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        self.table.setRowCount(0)
        self._raw_results = []
        self.select_btn.setEnabled(False)

        self._search_worker = SearchWorker(query, media_type, self._api_key)
        self._search_thread = QThread()
        self._search_worker.moveToThread(self._search_thread)

        self._search_thread.started.connect(self._search_worker.run)
        self._search_worker.results_ready.connect(self._on_results)
        self._search_worker.error.connect(self._on_error)

        self._search_thread.start()

    def _on_results(self, results: list):
        self.search_btn.setEnabled(True)
        self._raw_results = results
        is_movie = self.type_combo.currentIndex() == 1

        if not results:
            self.status_label.setText("No results found.")
            self.status_label.setStyleSheet(f"color: {COLORS['warning']};")
            return

        self.status_label.setText(f"Found {len(results)} result(s)")
        self.status_label.setStyleSheet(f"color: {COLORS['success']};")

        self.table.setRowCount(len(results))
        for i, r in enumerate(results):
            if is_movie:
                title = r.get("title", "")
                orig = r.get("original_title", "")
                date = r.get("release_date", "")
            else:
                title = r.get("name", "")
                orig = r.get("original_name", "")
                date = r.get("first_air_date", "")

            year = date[:4] if date and len(date) >= 4 else ""

            self.table.setItem(i, 0, QTableWidgetItem(title))
            self.table.setItem(i, 1, QTableWidgetItem(orig))
            self.table.setItem(i, 2, QTableWidgetItem(year))
            self.table.setItem(i, 3, QTableWidgetItem(str(r.get("id", ""))))

        self._cleanup_thread()

    def _on_error(self, error_msg: str):
        self.search_btn.setEnabled(True)
        self.status_label.setText(f"Error: {error_msg}")
        self.status_label.setStyleSheet(f"color: {COLORS['error']};")
        self._cleanup_thread()

    def _on_selection_changed(self):
        self.select_btn.setEnabled(bool(self.table.selectedItems()))

    def _on_double_click(self, index):
        self._on_select()

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        row = rows[0].row()
        if row >= len(self._raw_results):
            return

        result = self._raw_results[row]
        is_movie = self.type_combo.currentIndex() == 1
        tmdb_id = result.get("id")
        media_type = "movie" if is_movie else "series"

        if is_movie:
            title = result.get("original_title") or result.get("title", "")
        else:
            title = result.get("original_name") or result.get("name", "")

        self._result_id = tmdb_id
        self._result_type = media_type
        self._result_title = title
        self.accept()

    def get_result(self) -> tuple[int | None, str | None, str | None]:
        """Get the selected result: (tmdb_id, media_type, title)."""
        return self._result_id, self._result_type, self._result_title

    def _cleanup_thread(self):
        if self._search_thread is not None:
            self._search_thread.quit()
            self._search_thread.wait()
            self._search_thread = None

    def closeEvent(self, event):
        self._cleanup_thread()
        super().closeEvent(event)
