"""Main window for RNMR GUI."""
import json
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QTextEdit, QLabel, QFileDialog,
    QGroupBox, QMessageBox, QDialog, QFormLayout, QToolButton,
    QAbstractItemView, QSizePolicy, QMenuBar, QMenu
)
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QIcon, QColor, QAction

from .theme import COLORS
from .worker import ScanWorker, RenameWorker, RenameItem
from .settings_dialog import SettingsDialog
from .settings import SettingsManager
from .id_dialog import SetIDDialog
from .failed_lookup_dialog import FailedLookupDialog, SKIP, SEARCH_MANUALLY, ENTER_ID, SKIP_ALL
from .search_dialog import TMDBSearchDialog
from renamer.id_mapping import IDMapping


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

        # Source indicator
        if item.metadata and item.metadata.get("metadata_source"):
            source = item.metadata["metadata_source"]
            if source == "tmdb":
                source_label = QLabel("TMDB \u2714")
                source_label.setStyleSheet(
                    f"color: {COLORS['success']}; font-weight: bold;"
                )
            else:
                source_label = QLabel("Inferred from filename \u26A0")
                source_label.setStyleSheet(
                    f"color: {COLORS['warning']}; font-weight: bold;"
                )
            layout.addRow("Source:", source_label)

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
                id_label = QLabel(str(item.metadata.get("tmdb_id")))
                if item.metadata.get("mapped_id"):
                    id_label.setText(f"{item.metadata.get('tmdb_id')} (manual)")
                    id_label.setStyleSheet(f"color: {COLORS['accent']};")
                layout.addRow("TMDB ID:", id_label)
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
        self._active_lookup_dialog: QDialog | None = None
        self._last_rename_items: list[tuple[int, RenameItem]] = []

        # Settings
        self.settings = SettingsManager()

        # Setup UI
        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        # Menu bar
        self._create_menu_bar()

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

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("Edit")

        settings_action = QAction("Settings...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._show_settings)
        edit_menu.addAction(settings_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        about_action = QAction("About RNMR", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_settings(self):
        """Show the settings dialog."""
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec()

    def _on_settings_changed(self):
        """Handle settings changes."""
        self.settings.reload()
        self._log("Settings updated. Rescan to apply new naming format.")

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About RNMR",
            "<h3>RNMR - Media File Renamer</h3>"
            "<p>Version 1.3.0</p>"
            "<p>A tool for renaming media files using TMDB metadata.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>Automatic series/movie detection</li>"
            "<li>TMDB integration for official titles</li>"
            "<li>Customizable naming templates</li>"
            "<li>Subtitle renaming support</li>"
            "<li>Manual TMDB ID disambiguation</li>"
            "</ul>"
        )

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

        # Row 2: Scan, Clear, and Stop buttons
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("primaryButton")
        self.scan_btn.clicked.connect(self._start_scan)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip("Clear preview list and reset progress")
        self.clear_btn.clicked.connect(self._clear_results)
        self.clear_btn.setEnabled(False)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop_scan)
        self.stop_btn.setVisible(False)

        layout.addWidget(self.scan_btn, 2, 0, 1, 2)
        layout.addWidget(self.clear_btn, 2, 2)
        layout.addWidget(self.stop_btn, 2, 3)

        return group

    def _create_table(self) -> QTableWidget:
        """Create the main table widget."""
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["", "Original Name", "New Name", "Status", "Source"]
        )
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
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 80)

        # Double-click handler
        self.table.doubleClicked.connect(self._show_metadata)

        # Context menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

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

        # Undo button
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setToolTip("Revert the most recent rename transaction")
        self.undo_btn.clicked.connect(self._undo_last_rename)
        self.undo_btn.setEnabled(False)

        # Rename button
        self.rename_btn = QPushButton("Rename Selected")
        self.rename_btn.setObjectName("primaryButton")
        self.rename_btn.clicked.connect(self._start_rename)
        self.rename_btn.setEnabled(False)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar, stretch=1)
        layout.addWidget(self.undo_btn)
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
        # Start from last folder or home
        start_dir = self.settings.get("last_folder", "")
        if not start_dir or not Path(start_dir).exists():
            start_dir = str(Path.home())

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Media Folder",
            start_dir
        )
        if folder:
            self.folder_edit.setText(folder)
            # Save last folder
            self.settings.set("last_folder", folder)
            self.settings.save()
            self._update_button_states()

    def _update_button_states(self):
        """Update button enabled states."""
        has_folder = bool(self.folder_edit.text())
        is_scanning = self.scan_thread is not None
        is_renaming = self.rename_thread is not None
        idle = not is_scanning and not is_renaming

        self.scan_btn.setEnabled(has_folder and idle)
        self.clear_btn.setEnabled(bool(self.items) and idle)
        self.undo_btn.setEnabled(idle and self._has_undoable_transactions())

        # Check if there are any checked pending items
        has_pending = any(
            item.checked and item.status == "pending"
            for item in self.items
        )
        self.rename_btn.setEnabled(has_pending and idle)

    def _log(self, message: str):
        """Add message to log."""
        self.log_text.append(message)

    def _has_undoable_transactions(self) -> bool:
        """Check if any non-reverted transactions exist in history."""
        folder = self.folder_edit.text()
        if not folder:
            return False
        history_path = Path(folder) / ".rnmr_history.json"
        if not history_path.exists():
            return False
        try:
            history = json.loads(
                history_path.read_text(encoding="utf-8")
            )
            return any(not t.get("reverted", False) for t in history)
        except (json.JSONDecodeError, OSError):
            return False

    def _clear_results(self):
        """Clear the preview list and reset UI state."""
        self.table.setRowCount(0)
        self.items.clear()
        self.log_text.clear()
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Ready")
        self._update_button_states()

    def _undo_last_rename(self):
        """Revert the most recent non-reverted rename transaction."""
        folder = self.folder_edit.text()
        if not folder:
            return

        history_path = Path(folder) / ".rnmr_history.json"
        if not history_path.exists():
            return

        try:
            history = json.loads(
                history_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            QMessageBox.warning(
                self, "Undo Error", "Could not read history file."
            )
            return

        # Find latest non-reverted transaction
        target_idx = None
        for i in range(len(history) - 1, -1, -1):
            if not history[i].get("reverted", False):
                target_idx = i
                break

        if target_idx is None:
            QMessageBox.information(
                self, "Nothing to Undo", "No transactions to undo."
            )
            return

        target = history[target_idx]
        items = target.get("items", [])
        if not items:
            return

        # Validate all items can be reverted
        errors: list[str] = []
        for item in items:
            new_p = Path(item["new_path"]) if item.get("new_path") else Path(folder) / item["new"]
            orig_p = Path(item["original_path"]) if item.get("original_path") else Path(folder) / item["original"]

            if not new_p.exists():
                errors.append(f"Not found: {new_p.name}")
            if orig_p.exists() and orig_p.resolve() != new_p.resolve():
                errors.append(f"Already exists: {orig_p.name}")

        if errors:
            msg = "Cannot undo -- the following issues were found:\n\n"
            msg += "\n".join(errors[:10])
            if len(errors) > 10:
                msg += f"\n... and {len(errors) - 10} more"
            QMessageBox.warning(self, "Cannot Undo", msg)
            return

        # Confirm
        result = QMessageBox.question(
            self,
            "Confirm Undo",
            f"Revert {len(items)} rename(s) from "
            f"{target.get('timestamp', 'unknown')}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        # Perform revert
        reverted = 0
        revert_errors: list[str] = []
        for item in items:
            new_p = Path(item["new_path"]) if item.get("new_path") else Path(folder) / item["new"]
            orig_p = Path(item["original_path"]) if item.get("original_path") else Path(folder) / item["original"]
            try:
                new_p.rename(orig_p)
                reverted += 1
            except Exception as e:
                revert_errors.append(f"{new_p.name}: {e}")

        # Mark transaction as reverted
        history[target_idx]["reverted"] = True
        history[target_idx]["reverted_at"] = (
            datetime.now().isoformat(timespec="seconds")
        )

        try:
            history_path.write_text(
                json.dumps(history, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            self._log(f"[WARN] Could not update history: {e}")

        self._log(f"Undo complete: {reverted} file(s) reverted")
        if revert_errors:
            self._log(
                f"[WARN] {len(revert_errors)} error(s) during undo"
            )
            for err in revert_errors:
                self._log(f"  {err}")

        self.status_label.setText(
            f"Undo: {reverted} file(s) reverted"
        )
        self._update_button_states()

    def _start_scan(self):
        """Start the scan operation."""
        folder = self.folder_edit.text()
        if not folder:
            return

        # Clear previous results
        self.table.setRowCount(0)
        self.items.clear()
        self.log_text.clear()

        # Create worker with templates from settings
        use_tmdb = self.tmdb_cb.isChecked()
        self.scan_worker = ScanWorker(
            folder_path=folder,
            recursive=self.recursive_cb.isChecked(),
            use_tmdb=use_tmdb,
            include_episode_title=self.episode_title_cb.isChecked(),
            series_template=self.settings.get("series_template"),
            movie_template=self.settings.get("movie_template"),
            interactive=use_tmdb and self.settings.get("interactive_fallback", True),
            api_key=self.settings.get("tmdb_api_key") or None,
            metadata_language=self.settings.get("tmdb_language", "en-US"),
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
        self.scan_worker.lookup_failed.connect(self._on_lookup_failed)

        # Start
        self.scan_thread.start()

    def _stop_scan(self):
        """Stop the current scan operation."""
        if self.scan_thread and hasattr(self, 'scan_worker'):
            self.scan_worker.cancel()
            # Close any active lookup dialog
            if self._active_lookup_dialog is not None:
                self._active_lookup_dialog.reject()
                self._active_lookup_dialog = None
            self._log("Stopping scan...")
            self.status_label.setText("Stopping...")

    @Slot()
    def _on_scan_started(self):
        """Handle scan started."""
        self.status_label.setText("Scanning...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.stop_btn.setVisible(True)
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

        # Source indicator
        source = (
            item.metadata.get("metadata_source", "inferred")
            if item.metadata else "inferred"
        )
        if source == "tmdb":
            source_item = QTableWidgetItem("\u2714 TMDB")
            source_item.setForeground(QColor(COLORS["success"]))
            source_item.setToolTip("Metadata from TMDB")
        else:
            source_item = QTableWidgetItem("\u26A0 Inferred")
            source_item.setForeground(QColor(COLORS["warning"]))
            source_item.setToolTip("Inferred from filename, not validated with TMDB")
        self.table.setItem(row_idx, 4, source_item)

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
        self.stop_btn.setVisible(False)

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
        self.stop_btn.setVisible(False)
        self.status_label.setText("Error")
        self._log(f"[ERROR] {error}")

        QMessageBox.critical(self, "Scan Error", error)

        if self.scan_thread:
            self.scan_thread.quit()
            self.scan_thread.wait()
            self.scan_thread = None

        self._update_button_states()

    @Slot(dict)
    def _on_lookup_failed(self, info: dict):
        """Handle interactive lookup failure -- show dialog on main thread."""
        result = None

        # Show decision dialog
        dlg = FailedLookupDialog(info, self)
        self._active_lookup_dialog = dlg
        choice = dlg.exec()
        self._active_lookup_dialog = None

        if choice == SEARCH_MANUALLY:
            search_dlg = TMDBSearchDialog(
                parsed_title=info.get("parsed_title", ""),
                media_type=info.get("media_type", "series"),
                api_key=self.settings.get("tmdb_api_key") or None,
                parent=self,
            )
            self._active_lookup_dialog = search_dlg
            if search_dlg.exec() == QDialog.Accepted:
                tmdb_id, media_type, title = search_dlg.get_result()
                if tmdb_id and media_type:
                    result = {
                        "tmdb_id": tmdb_id,
                        "media_type": media_type,
                        "title": title,
                    }
            self._active_lookup_dialog = None

        elif choice == ENTER_ID:
            id_dlg = SetIDDialog(
                Path(info.get("filepath", "")).name,
                info.get("media_type", "series"),
                self
            )
            self._active_lookup_dialog = id_dlg
            if id_dlg.exec() == QDialog.Accepted:
                tmdb_id, media_type, title = id_dlg.get_result()
                if tmdb_id and media_type:
                    result = {
                        "tmdb_id": tmdb_id,
                        "media_type": media_type,
                        "title": title,
                    }
            self._active_lookup_dialog = None

        elif choice == SKIP_ALL:
            # Sentinel tells the worker to activate skip-all mode
            result = {"__skip_all__": True}

        # Wake the worker thread with the result (or None for skip)
        if hasattr(self, 'scan_worker'):
            self.scan_worker.set_lookup_result(result)

    def _show_metadata(self, index):
        """Show metadata dialog for selected row."""
        row = index.row()
        if row < len(self.items):
            dialog = MetadataDialog(self.items[row], self)
            dialog.exec()

    def _show_context_menu(self, position):
        """Show context menu for table row."""
        index = self.table.indexAt(position)
        if not index.isValid():
            return

        row = index.row()
        if row >= len(self.items):
            return

        item = self.items[row]

        menu = QMenu(self)

        # View details action
        details_action = QAction("View Details...", self)
        details_action.triggered.connect(lambda: self._show_metadata(index))
        menu.addAction(details_action)

        menu.addSeparator()

        # Set TMDB ID action
        set_id_action = QAction("Set TMDB ID...", self)
        set_id_action.triggered.connect(lambda: self._show_set_id_dialog(row))
        menu.addAction(set_id_action)

        # Clear TMDB ID action (if has mapping)
        folder = self.folder_edit.text()
        if folder:
            mapping = IDMapping(Path(folder))
            existing_id, _ = mapping.get_id(item.original_path.name)
            if existing_id:
                clear_id_action = QAction("Clear TMDB ID", self)
                clear_id_action.triggered.connect(lambda: self._clear_tmdb_id(row))
                menu.addAction(clear_id_action)

        menu.exec(self.table.viewport().mapToGlobal(position))

    def _show_set_id_dialog(self, row: int):
        """Show dialog to set TMDB ID for a file."""
        if row >= len(self.items):
            return

        item = self.items[row]
        media_type = item.metadata.get("media_type", "series") if item.metadata else "series"

        dialog = SetIDDialog(item.original_path.name, media_type, self)
        if dialog.exec() == QDialog.Accepted:
            tmdb_id, result_type, title = dialog.get_result()
            if tmdb_id and result_type:
                # Save mapping
                folder = self.folder_edit.text()
                if folder:
                    mapping = IDMapping(Path(folder))
                    mapping.set_id(item.original_path.name, tmdb_id, result_type, title)
                    self._log(f"Set TMDB ID for '{item.original_path.name}': {result_type}:{tmdb_id} ({title})")

                    # Offer to rescan
                    result = QMessageBox.question(
                        self,
                        "ID Saved",
                        f"TMDB ID saved for '{item.original_path.name}'.\n\n"
                        f"Would you like to rescan to apply the new ID?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )
                    if result == QMessageBox.Yes:
                        self._start_scan()

    def _clear_tmdb_id(self, row: int):
        """Clear TMDB ID mapping for a file."""
        if row >= len(self.items):
            return

        item = self.items[row]
        folder = self.folder_edit.text()
        if folder:
            mapping = IDMapping(Path(folder))
            if mapping.remove_id(item.original_path.name):
                self._log(f"Cleared TMDB ID for '{item.original_path.name}'")
                QMessageBox.information(
                    self,
                    "ID Cleared",
                    f"TMDB ID cleared for '{item.original_path.name}'.\n\n"
                    "Rescan to use automatic lookup."
                )

    def _start_rename(self):
        """Start the rename operation."""
        # Get checked pending items
        items_to_rename = [
            (i, item) for i, item in enumerate(self.items)
            if item.checked and item.status == "pending"
        ]

        if not items_to_rename:
            return

        # Safety check: warn about inferred metadata (once for batch)
        inferred_count = sum(
            1 for _, item in items_to_rename
            if item.metadata
            and item.metadata.get("metadata_source") == "inferred"
        )
        if inferred_count > 0 and not self.dry_run_cb.isChecked():
            result = QMessageBox.warning(
                self,
                "Unverified Metadata",
                f"{inferred_count} file(s) have metadata inferred from "
                f"filename and not validated with TMDB.\n\nProceed?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if result != QMessageBox.Yes:
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

        self._last_rename_items = items_to_rename

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

        # Save transaction history
        if renamed > 0 and self._last_rename_items:
            self._save_transaction(self._last_rename_items)

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

    def _save_transaction(
        self, items: list[tuple[int, "RenameItem"]]
    ):
        """Save a rename transaction to .rnmr_history.json."""
        folder = self.folder_edit.text()
        if not folder:
            return

        history_path = Path(folder) / ".rnmr_history.json"

        # Load existing history
        history: list[dict] = []
        if history_path.exists():
            try:
                history = json.loads(
                    history_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                history = []

        # Build transaction record
        transaction: dict = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "folder": folder,
            "items": [],
        }

        for _row, item in items:
            if item.status != "renamed":
                continue
            entry: dict = {
                "original": item.original_path.name,
                "original_path": str(item.original_path),
                "new": item.new_name,
                "new_path": str(item.new_path) if item.new_path else "",
                "status": item.status,
                "metadata_source": (
                    item.metadata.get("metadata_source", "inferred")
                    if item.metadata else "inferred"
                ),
            }
            if item.metadata and item.metadata.get("tmdb_id"):
                entry["tmdb_id"] = item.metadata["tmdb_id"]
            transaction["items"].append(entry)

        if not transaction["items"]:
            return

        history.append(transaction)

        try:
            history_path.write_text(
                json.dumps(history, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._log(
                f"Transaction saved: {len(transaction['items'])} "
                f"item(s) to {history_path.name}"
            )
        except OSError as e:
            self._log(f"[WARN] Could not save transaction: {e}")

    def closeEvent(self, event):
        """Handle window close."""
        # Close any active lookup dialog
        if self._active_lookup_dialog is not None:
            self._active_lookup_dialog.reject()
            self._active_lookup_dialog = None

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
