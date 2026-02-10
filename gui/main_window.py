"""Main window for RNMR GUI."""
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QTextEdit, QLabel, QFileDialog,
    QGroupBox, QMessageBox, QDialog, QFormLayout, QToolButton,
    QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QIcon, QColor

from .theme import COLORS
from .worker import ScanWorker, RenameWorker, RenameItem


class MetadataDialog(QDialog):
    """Dialog to show file metadata details."""

    def __init__(self, item: RenameItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle("File Details")
        self.setMinimumWidth(450)

        layout = QFormLayout(self)
        layout.setSpacing(12)

        # Original name
        layout.addRow("Original:", QLabel(item.original_path.name))

        # New name
        layout.addRow("New Name:", QLabel(item.new_name or "N/A"))

        # Status
        status_label = QLabel(item.status.upper())
        status_label.setStyleSheet(self._status_color(item.status))
        layout.addRow("Status:", status_label)

        if item.error_message:
            layout.addRow("Error:", QLabel(item.error_message))

        # Metadata
        if item.metadata:
            layout.addRow(QLabel(""))  # Spacer
            layout.addRow("Parsed Title:", QLabel(item.metadata.get("title_guess", "N/A")))
            layout.addRow("Media Type:", QLabel(item.metadata.get("media_type", "N/A")))

            if item.metadata.get("season") is not None:
                layout.addRow("Season:", QLabel(str(item.metadata.get("season"))))
            if item.metadata.get("episodes"):
                layout.addRow("Episode(s):", QLabel(str(item.metadata.get("episodes"))))
            if item.metadata.get("year"):
                layout.addRow("Year:", QLabel(str(item.metadata.get("year"))))

            if item.metadata.get("tmdb_id"):
                layout.addRow("TMDB ID:", QLabel(str(item.metadata.get("tmdb_id"))))
            if item.metadata.get("tmdb_title"):
                layout.addRow("TMDB Title:", QLabel(item.metadata.get("tmdb_title")))
            if item.metadata.get("episode_title"):
                layout.addRow("Episode Title:", QLabel(item.metadata.get("episode_title")))

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addRow(close_btn)

    def _status_color(self, status: str) -> str:
        colors = {
            "pending": COLORS["warning"],
            "renamed": COLORS["success"],
            "skipped": COLORS["text_muted"],
            "error": COLORS["error"],
        }
        color = colors.get(status, COLORS["text"])
        return f"color: {color}; font-weight: bold;"


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("RNMR - Media File Renamer")
        self.setMinimumSize(900, 650)
        self.resize(1100, 750)

        # Data
        self.items: list[RenameItem] = []
        self.scan_thread: QThread | None = None
        self.rename_thread: QThread | None = None

        # Setup UI
        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Top controls
        layout.addWidget(self._create_controls_group())

        # Table
        layout.addWidget(self._create_table(), stretch=1)

        # Bottom section
        layout.addWidget(self._create_bottom_section())

        # Log panel (collapsible)
        layout.addWidget(self._create_log_panel())

        # Initial state
        self._update_button_states()

    def _create_controls_group(self) -> QGroupBox:
        """Create the top controls group."""
        group = QGroupBox("Settings")
        layout = QGridLayout(group)
        layout.setSpacing(12)

        # Row 0: Folder selection
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Select a folder to scan...")
        self.folder_edit.setReadOnly(True)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)

        layout.addWidget(self.folder_edit, 0, 0, 1, 3)
        layout.addWidget(browse_btn, 0, 3)

        # Row 1: Checkboxes
        self.recursive_cb = QCheckBox("Recursive")
        self.recursive_cb.setChecked(True)
        self.recursive_cb.setToolTip("Scan subdirectories")

        self.tmdb_cb = QCheckBox("Use TMDB")
        self.tmdb_cb.setChecked(True)
        self.tmdb_cb.setToolTip("Fetch metadata from TMDB API")

        self.episode_title_cb = QCheckBox("Include Episode Titles")
        self.episode_title_cb.setChecked(True)
        self.episode_title_cb.setToolTip("Include episode names in series filenames")

        self.dry_run_cb = QCheckBox("Dry Run")
        self.dry_run_cb.setToolTip("Preview only, don't rename files")

        layout.addWidget(self.recursive_cb, 1, 0)
        layout.addWidget(self.tmdb_cb, 1, 1)
        layout.addWidget(self.episode_title_cb, 1, 2)
        layout.addWidget(self.dry_run_cb, 1, 3)

        # Row 2: Scan button
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("primaryButton")
        self.scan_btn.clicked.connect(self._start_scan)

        layout.addWidget(self.scan_btn, 2, 0, 1, 4)

        return group

    def _create_table(self) -> QTableWidget:
        """Create the main table widget."""
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", "Original Name", "New Name", "Status"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Column sizing
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(3, 100)

        # Double-click handler
        self.table.doubleClicked.connect(self._show_metadata)

        return self.table

    def _create_bottom_section(self) -> QWidget:
        """Create the bottom section with rename button and progress."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("mutedLabel")

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)

        # Rename button
        self.rename_btn = QPushButton("Rename Selected")
        self.rename_btn.setObjectName("primaryButton")
        self.rename_btn.clicked.connect(self._start_rename)
        self.rename_btn.setEnabled(False)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar, stretch=1)
        layout.addWidget(self.rename_btn)

        return widget

    def _create_log_panel(self) -> QWidget:
        """Create the collapsible log panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header with toggle button
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.log_toggle_btn = QToolButton()
        self.log_toggle_btn.setText("Log")
        self.log_toggle_btn.setArrowType(Qt.RightArrow)
        self.log_toggle_btn.setCheckable(True)
        self.log_toggle_btn.clicked.connect(self._toggle_log)

        header_layout.addWidget(self.log_toggle_btn)
        header_layout.addStretch()

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setVisible(False)

        layout.addWidget(header)
        layout.addWidget(self.log_text)

        return widget

    def _toggle_log(self):
        """Toggle log panel visibility."""
        visible = self.log_toggle_btn.isChecked()
        self.log_text.setVisible(visible)
        self.log_toggle_btn.setArrowType(Qt.DownArrow if visible else Qt.RightArrow)

    def _browse_folder(self):
        """Open folder selection dialog."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Media Folder",
            str(Path.home())
        )
        if folder:
            self.folder_edit.setText(folder)
            self._update_button_states()

    def _update_button_states(self):
        """Update button enabled states."""
        has_folder = bool(self.folder_edit.text())
        is_scanning = self.scan_thread is not None
        is_renaming = self.rename_thread is not None

        self.scan_btn.setEnabled(has_folder and not is_scanning and not is_renaming)

        # Check if there are any checked pending items
        has_pending = any(
            item.checked and item.status == "pending"
            for item in self.items
        )
        self.rename_btn.setEnabled(has_pending and not is_scanning and not is_renaming)

    def _log(self, message: str):
        """Add message to log."""
        self.log_text.append(message)

    def _start_scan(self):
        """Start the scan operation."""
        folder = self.folder_edit.text()
        if not folder:
            return

        # Clear previous results
        self.table.setRowCount(0)
        self.items.clear()
        self.log_text.clear()

        # Create worker
        self.scan_worker = ScanWorker(
            folder_path=folder,
            recursive=self.recursive_cb.isChecked(),
            use_tmdb=self.tmdb_cb.isChecked(),
            include_episode_title=self.episode_title_cb.isChecked()
        )

        # Create thread
        self.scan_thread = QThread()
        self.scan_worker.moveToThread(self.scan_thread)

        # Connect signals
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.started.connect(self._on_scan_started)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.item_found.connect(self._on_item_found)
        self.scan_worker.log.connect(self._log)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)

        # Start
        self.scan_thread.start()

    @Slot()
    def _on_scan_started(self):
        """Handle scan started."""
        self.status_label.setText("Scanning...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self._update_button_states()

    @Slot(int, int)
    def _on_scan_progress(self, current: int, total: int):
        """Handle scan progress."""
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Scanning: {current}/{total}")

    @Slot(int, object)
    def _on_item_found(self, row: int, item: RenameItem):
        """Handle item found during scan."""
        self.items.append(item)

        # Add row to table
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)

        # Checkbox
        cb_widget = QWidget()
        cb_layout = QHBoxLayout(cb_widget)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        cb_layout.setAlignment(Qt.AlignCenter)

        checkbox = QCheckBox()
        checkbox.setChecked(item.checked)
        checkbox.stateChanged.connect(lambda state, r=row_idx: self._on_checkbox_changed(r, state))
        cb_layout.addWidget(checkbox)

        self.table.setCellWidget(row_idx, 0, cb_widget)

        # Original name
        orig_item = QTableWidgetItem(item.original_path.name)
        orig_item.setToolTip(str(item.original_path))
        self.table.setItem(row_idx, 1, orig_item)

        # New name
        new_item = QTableWidgetItem(item.new_name or "")
        self.table.setItem(row_idx, 2, new_item)

        # Status
        status_item = QTableWidgetItem(item.status.capitalize())
        status_item.setToolTip(item.error_message or "")
        status_item.setForeground(self._status_color(item.status))
        self.table.setItem(row_idx, 3, status_item)

    def _on_checkbox_changed(self, row: int, state: int):
        """Handle checkbox state change."""
        if row < len(self.items):
            self.items[row].checked = state == Qt.Checked
            self._update_button_states()

    def _status_color(self, status: str) -> QColor:
        """Get color for status."""
        colors = {
            "pending": QColor(COLORS["warning"]),
            "renamed": QColor(COLORS["success"]),
            "skipped": QColor(COLORS["text_muted"]),
            "error": QColor(COLORS["error"]),
        }
        return colors.get(status, QColor(COLORS["text"]))

    @Slot()
    def _on_scan_finished(self):
        """Handle scan finished."""
        self.progress_bar.setVisible(False)

        pending = sum(1 for item in self.items if item.status == "pending")
        total = len(self.items)
        self.status_label.setText(f"Found {total} files ({pending} to rename)")

        self._log(f"Scan complete: {total} files, {pending} pending")

        # Cleanup thread
        if self.scan_thread:
            self.scan_thread.quit()
            self.scan_thread.wait()
            self.scan_thread = None

        self._update_button_states()

    @Slot(str)
    def _on_scan_error(self, error: str):
        """Handle scan error."""
        self.progress_bar.setVisible(False)
        self.status_label.setText("Error")
        self._log(f"[ERROR] {error}")

        QMessageBox.critical(self, "Scan Error", error)

        if self.scan_thread:
            self.scan_thread.quit()
            self.scan_thread.wait()
            self.scan_thread = None

        self._update_button_states()

    def _show_metadata(self, index):
        """Show metadata dialog for selected row."""
        row = index.row()
        if row < len(self.items):
            dialog = MetadataDialog(self.items[row], self)
            dialog.exec()

    def _start_rename(self):
        """Start the rename operation."""
        # Get checked pending items
        items_to_rename = [
            (i, item) for i, item in enumerate(self.items)
            if item.checked and item.status == "pending"
        ]

        if not items_to_rename:
            return

        # Confirmation dialog (if not dry run)
        if not self.dry_run_cb.isChecked():
            result = QMessageBox.question(
                self,
                "Confirm Rename",
                f"Rename {len(items_to_rename)} file(s)?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if result != QMessageBox.Yes:
                return

        if self.dry_run_cb.isChecked():
            # Dry run - just mark as renamed in UI
            for row, item in items_to_rename:
                self._update_table_status(row, "renamed", "")
                item.status = "renamed"
            self._log(f"[DRY RUN] Would rename {len(items_to_rename)} files")
            self._update_button_states()
            return

        # Create worker
        self.rename_worker = RenameWorker(items_to_rename)

        # Create thread
        self.rename_thread = QThread()
        self.rename_worker.moveToThread(self.rename_thread)

        # Connect signals
        self.rename_thread.started.connect(self.rename_worker.run)
        self.rename_worker.started.connect(self._on_rename_started)
        self.rename_worker.progress.connect(self._on_rename_progress)
        self.rename_worker.item_updated.connect(self._on_item_updated)
        self.rename_worker.log.connect(self._log)
        self.rename_worker.finished.connect(self._on_rename_finished)
        self.rename_worker.error.connect(self._on_rename_error)

        # Start
        self.rename_thread.start()

    @Slot()
    def _on_rename_started(self):
        """Handle rename started."""
        self.status_label.setText("Renaming...")
        self.progress_bar.setVisible(True)
        self._update_button_states()

    @Slot(int, int)
    def _on_rename_progress(self, current: int, total: int):
        """Handle rename progress."""
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Renaming: {current}/{total}")

    @Slot(int, str, str)
    def _on_item_updated(self, row: int, status: str, error: str):
        """Handle item status update."""
        if row < len(self.items):
            self.items[row].status = status
            self.items[row].error_message = error if error else None
            self._update_table_status(row, status, error)

    def _update_table_status(self, row: int, status: str, error: str):
        """Update status cell in table."""
        status_item = QTableWidgetItem(status.capitalize())
        status_item.setToolTip(error or "")
        status_item.setForeground(self._status_color(status))
        self.table.setItem(row, 3, status_item)

    @Slot(int, int, int)
    def _on_rename_finished(self, renamed: int, skipped: int, errors: int):
        """Handle rename finished."""
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Done: {renamed} renamed, {skipped} skipped, {errors} errors")

        self._log(f"Rename complete: {renamed} renamed, {skipped} skipped, {errors} errors")

        if self.rename_thread:
            self.rename_thread.quit()
            self.rename_thread.wait()
            self.rename_thread = None

        self._update_button_states()

    @Slot(str)
    def _on_rename_error(self, error: str):
        """Handle rename error."""
        self.progress_bar.setVisible(False)
        self.status_label.setText("Error")
        self._log(f"[ERROR] {error}")

        QMessageBox.critical(self, "Rename Error", error)

        if self.rename_thread:
            self.rename_thread.quit()
            self.rename_thread.wait()
            self.rename_thread = None

        self._update_button_states()

    def closeEvent(self, event):
        """Handle window close."""
        # Cancel any running operations
        if self.scan_thread:
            self.scan_worker.cancel()
            self.scan_thread.quit()
            self.scan_thread.wait()

        if self.rename_thread:
            self.rename_worker.cancel()
            self.rename_thread.quit()
            self.rename_thread.wait()

        event.accept()
