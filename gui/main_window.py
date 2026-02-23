"""Main window for RNMR GUI."""
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QTextEdit, QLabel, QFileDialog,
    QGroupBox, QMessageBox, QDialog, QFormLayout, QToolButton,
    QAbstractItemView, QSizePolicy, QMenuBar, QMenu, QTabWidget
)
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QIcon, QColor, QAction, QBrush, QFont, QDesktopServices
from PySide6.QtCore import QUrl

from .theme import COLORS
from .worker import ScanWorker, RenameWorker, RenameItem, DuplicateScanWorker
from .settings_dialog import SettingsDialog
from .settings import SettingsManager
from .id_dialog import SetIDDialog
from .failed_lookup_dialog import FailedLookupDialog, SKIP, SEARCH_MANUALLY, ENTER_ID, SKIP_ALL
from .media_type_dialog import MediaTypeDialog, SERIES as MT_SERIES, MOVIE as MT_MOVIE, SKIP as MT_SKIP, SKIP_ALL as MT_SKIP_ALL
from .search_dialog import TMDBSearchDialog
from .tmdb_select_dialog import TMDBSelectDialog, SKIP as SEL_SKIP, SKIP_ALL as SEL_SKIP_ALL
from renamer.id_mapping import IDMapping
from renamer.history import RenameHistoryManager
from .setup_wizard import SetupWizard
from .support_dialog import SupportDialog
from .i18n import t


class MetadataDialog(QDialog):
    """Dialog to show file metadata details."""

    def __init__(self, item: RenameItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("File Details"))
        self.setMinimumWidth(450)

        layout = QFormLayout(self)
        layout.setSpacing(12)

        # Original name
        layout.addRow(t("Original:") , QLabel(item.original_path.name))

        # New name
        layout.addRow(t("New Name:"), QLabel(item.new_name or t("N/A")))

        # Status
        status_label = QLabel(item.status.upper())
        status_label.setStyleSheet(self._status_color(item.status))
        layout.addRow(t("Status:"), status_label)

        if item.error_message:
            layout.addRow(t("Error:"), QLabel(item.error_message))

        # Source indicator
        if item.metadata and item.metadata.get("metadata_source"):
            source = item.metadata["metadata_source"]
            if source == "tmdb":
                source_label = QLabel("TMDB \u2714")
                source_label.setStyleSheet(
                    f"color: {COLORS['success']}; font-weight: bold;"
                )
            elif source == "ffprobe":
                source_label = QLabel("TMDB (via embedded metadata) \u2714")
                source_label.setStyleSheet(
                    f"color: {COLORS['accent']}; font-weight: bold;"
                )
            elif source == "unidentified":
                source_label = QLabel("Unknown \u2716")
                source_label.setStyleSheet(
                    f"color: {COLORS['error']}; font-weight: bold;"
                )
            else:
                source_label = QLabel("Inferred from filename \u26A0")
                source_label.setStyleSheet(
                    f"color: {COLORS['warning']}; font-weight: bold;"
                )
            layout.addRow(t("Source:"), source_label)

        # Metadata
        if item.metadata:
            layout.addRow(QLabel(""))  # Spacer
            layout.addRow(t("Parsed Title:"), QLabel(item.metadata.get("title_guess", t("N/A"))))
            layout.addRow(t("Media Type:"), QLabel(item.metadata.get("media_type", t("N/A"))))

            if item.metadata.get("season") is not None:
                layout.addRow(t("Season:"), QLabel(str(item.metadata.get("season"))))
            if item.metadata.get("episodes"):
                layout.addRow(t("Episode(s):"), QLabel(str(item.metadata.get("episodes"))))
            if item.metadata.get("year"):
                layout.addRow(t("Year:"), QLabel(str(item.metadata.get("year"))))

            if item.metadata.get("tmdb_id"):
                id_label = QLabel(str(item.metadata.get("tmdb_id")))
                if item.metadata.get("mapped_id"):
                    id_label.setText(f"{item.metadata.get('tmdb_id')} (manual)")
                    id_label.setStyleSheet(f"color: {COLORS['accent']};")
                layout.addRow(t("TMDB ID:"), id_label)
            if item.metadata.get("tmdb_title"):
                layout.addRow(t("TMDB Title:"), QLabel(item.metadata.get("tmdb_title")))
            if item.metadata.get("episode_title"):
                layout.addRow(t("Episode Title:"), QLabel(item.metadata.get("episode_title")))

        # Close button
        close_btn = QPushButton(t("Close"))
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

        self.setWindowTitle(t("RNMR - Media File Renamer"))
        self.setMinimumSize(900, 650)
        self.resize(1100, 750)

        # Data
        self.items: list[RenameItem] = []
        self.scan_thread: QThread | None = None
        self.rename_thread: QThread | None = None
        self.dup_scan_thread: QThread | None = None
        self.dup_groups: list[dict] = []
        self._dup_row_map: list[dict | None] = []
        self._dup_header_rows: set[int] = set()
        self._active_lookup_dialog: QDialog | None = None
        self._last_rename_items: list[tuple[int, RenameItem]] = []

        # Settings
        self.settings = SettingsManager()

        # Persistent rename history
        self._history = RenameHistoryManager()

        # Setup UI
        self._setup_ui()

        # First-run setup wizard (after UI is built so badge can update)
        self._check_api_key_on_startup()

    def _has_api_key(self) -> bool:
        """Return True if a TMDB API key is configured (settings or env)."""
        key = self.settings.get("tmdb_api_key", "")
        if key:
            return True
        import os
        return bool(os.environ.get("TMDB_API_KEY"))

    def _check_api_key_on_startup(self):
        """Show setup wizard if no API key is configured."""
        if self._has_api_key():
            self._update_api_key_badge()
            return

        self._update_api_key_badge()

        wizard = SetupWizard(self)
        if wizard.exec() == SetupWizard.Accepted:
            api_key = wizard.get_api_key()
            if api_key:
                self.settings.set("tmdb_api_key", api_key)
                self.settings.save()
                self._log(t("TMDB API key saved."))
        self._update_api_key_badge()
        self._update_button_states()

    def _update_api_key_badge(self):
        """Show or hide the 'API Key Required' badge."""
        if self._has_api_key():
            self._api_key_badge.setVisible(False)
        else:
            self._api_key_badge.setVisible(True)

    def _setup_ui(self):
        """Setup the user interface."""
        # Menu bar
        self._create_menu_bar()

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.addTab(self._create_renamer_tab(), t("Renamer"))
        tabs.addTab(self._create_duplicate_tab(), t("Duplicate Finder"))
        layout.addWidget(tabs)

        # Initial state
        self._update_button_states()
        self._update_dup_button_states()

    def _create_renamer_tab(self) -> QWidget:
        """Create the renamer tab content."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Top controls
        layout.addWidget(self._create_controls_group())

        # Table
        layout.addWidget(self._create_table(), stretch=1)

        # Bottom section
        layout.addWidget(self._create_bottom_section())

        # Log panel (collapsible)
        layout.addWidget(self._create_log_panel())

        return widget

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu(t("File"))

        exit_action = QAction(t("Exit"), self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu(t("Edit"))

        settings_action = QAction(t("Settings..."), self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._show_settings)
        edit_menu.addAction(settings_action)

        # Help menu
        help_menu = menubar.addMenu(t("Help"))

        about_action = QAction(t("About RNMR"), self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        help_menu.addSeparator()

        support_action = QAction(t("Support RNMR..."), self)
        support_action.triggered.connect(self._show_support)
        help_menu.addAction(support_action)

    def _show_settings(self):
        """Show the settings dialog."""
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec()

    def _on_settings_changed(self):
        """Handle settings changes."""
        self.settings.reload()
        self._update_api_key_badge()
        self._update_button_states()
        self._log(t("Settings updated. Rescan to apply new naming format."))

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

    def _show_support(self):
        """Show the support/donate dialog."""
        dlg = SupportDialog(self)
        dlg.exec()

    def _create_controls_group(self) -> QGroupBox:
        """Create the top controls group."""
        group = QGroupBox(t("Settings"))
        layout = QGridLayout(group)
        layout.setSpacing(12)

        # Row 0: Folder selection
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(t("Select a folder to scan..."))
        self.folder_edit.setReadOnly(True)

        browse_btn = QPushButton(t("Browse..."))
        browse_btn.clicked.connect(self._browse_folder)

        layout.addWidget(self.folder_edit, 0, 0, 1, 3)
        layout.addWidget(browse_btn, 0, 3)

        # Row 1: Checkboxes
        self.recursive_cb = QCheckBox(t("Recursive"))
        self.recursive_cb.setChecked(True)
        self.recursive_cb.setToolTip(t("Scan subdirectories"))

        self.tmdb_cb = QCheckBox(t("Use TMDB"))
        self.tmdb_cb.setChecked(True)
        self.tmdb_cb.setToolTip(t("Fetch metadata from TMDB API"))

        self.episode_title_cb = QCheckBox(t("Include Episode Titles"))
        self.episode_title_cb.setChecked(True)
        self.episode_title_cb.setToolTip(t("Include episode names in series filenames"))

        self.dry_run_cb = QCheckBox(t("Dry Run"))
        self.dry_run_cb.setToolTip(t("Preview only, don't rename files"))

        layout.addWidget(self.recursive_cb, 1, 0)
        layout.addWidget(self.tmdb_cb, 1, 1)
        layout.addWidget(self.episode_title_cb, 1, 2)
        layout.addWidget(self.dry_run_cb, 1, 3)

        # Row 2: Scan, Clear, and Stop buttons
        self.scan_btn = QPushButton(t("Scan"))
        self.scan_btn.setObjectName("primaryButton")
        self.scan_btn.clicked.connect(self._start_scan)

        self.clear_btn = QPushButton(t("Clear"))
        self.clear_btn.setToolTip(t("Clear preview list and reset progress"))
        self.clear_btn.clicked.connect(self._clear_results)
        self.clear_btn.setEnabled(False)

        self.stop_btn = QPushButton(t("Stop"))
        self.stop_btn.clicked.connect(self._stop_scan)
        self.stop_btn.setVisible(False)

        layout.addWidget(self.scan_btn, 2, 0, 1, 2)
        layout.addWidget(self.clear_btn, 2, 2)
        layout.addWidget(self.stop_btn, 2, 3)

        # Row 3: API key badge (hidden when key is present)
        self._api_key_badge = QLabel(t("API Key Required  --  Set one in Edit > Settings"))
        self._api_key_badge.setAlignment(Qt.AlignCenter)
        self._api_key_badge.setStyleSheet(
            f"color: {COLORS['error']}; font-weight: bold; "
            f"background-color: rgba(244, 67, 54, 0.12); "
            f"border: 1px solid {COLORS['error']}; border-radius: 4px; "
            f"padding: 4px;"
        )
        self._api_key_badge.setVisible(False)
        layout.addWidget(self._api_key_badge, 3, 0, 1, 4)

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

    def _create_duplicate_tab(self) -> QWidget:
        """Create the Duplicate Finder tab content."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Controls
        layout.addWidget(self._create_duplicate_controls())

        # Table
        layout.addWidget(self._create_duplicate_table(), stretch=1)

        # Bottom actions
        layout.addWidget(self._create_duplicate_actions())

        return widget

    def _create_duplicate_controls(self) -> QGroupBox:
        """Create the duplicate scan controls."""
        group = QGroupBox(t("Duplicate Finder"))
        layout = QGridLayout(group)
        layout.setSpacing(12)

        self.dup_folder_edit = QLineEdit()
        self.dup_folder_edit.setPlaceholderText(t("Select a folder to scan for duplicates..."))
        self.dup_folder_edit.setReadOnly(True)

        browse_btn = QPushButton(t("Browse..."))
        browse_btn.clicked.connect(self._browse_dup_folder)

        layout.addWidget(self.dup_folder_edit, 0, 0, 1, 3)
        layout.addWidget(browse_btn, 0, 3)

        self.dup_recursive_cb = QCheckBox(t("Recursive"))
        self.dup_recursive_cb.setChecked(True)
        self.dup_recursive_cb.setToolTip(t("Scan subdirectories"))

        layout.addWidget(self.dup_recursive_cb, 1, 0)

        self.dup_all_files_cb = QCheckBox(t("Include all files"))
        self.dup_all_files_cb.setChecked(False)
        self.dup_all_files_cb.setToolTip(t("Scan all files, not just media"))

        layout.addWidget(self.dup_all_files_cb, 1, 1)

        dup_hint = QLabel(
            t(
                "Safe delete moves files to .rnmr_trash (undoable). Use the Trash menu to open or empty it."
            )
        )
        dup_hint.setWordWrap(True)
        dup_hint.setObjectName("mutedLabel")
        layout.addWidget(dup_hint, 3, 0, 1, 4)

        self.dup_scan_btn = QPushButton(t("Scan Duplicates"))
        self.dup_scan_btn.setObjectName("primaryButton")
        self.dup_scan_btn.clicked.connect(self._start_dup_scan)

        self.dup_clear_btn = QPushButton(t("Clear"))
        self.dup_clear_btn.clicked.connect(self._clear_dup_results)
        self.dup_clear_btn.setEnabled(False)

        self.dup_stop_btn = QPushButton(t("Stop"))
        self.dup_stop_btn.clicked.connect(self._stop_dup_scan)
        self.dup_stop_btn.setVisible(False)

        layout.addWidget(self.dup_scan_btn, 2, 0, 1, 2)
        layout.addWidget(self.dup_clear_btn, 2, 2)
        layout.addWidget(self.dup_stop_btn, 2, 3)

        self.dup_status_label = QLabel(t("Ready"))
        self.dup_status_label.setObjectName("mutedLabel")
        layout.addWidget(self.dup_status_label, 4, 0, 1, 4)

        self.dup_progress_bar = QProgressBar()
        self.dup_progress_bar.setVisible(False)
        self.dup_progress_bar.setTextVisible(False)
        self.dup_progress_bar.setFixedHeight(6)
        layout.addWidget(self.dup_progress_bar, 5, 0, 1, 4)

        return group

    def _create_duplicate_table(self) -> QTableWidget:
        """Create the duplicates table widget."""
        self.dup_table = QTableWidget()
        self.dup_table.setColumnCount(5)
        self.dup_table.setHorizontalHeaderLabels(
            ["", t("Path"), t("Size"), t("Modified"), t("Hash (MD5)")]
        )
        self.dup_table.setAlternatingRowColors(True)
        self.dup_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.dup_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.dup_table.verticalHeader().setVisible(False)
        self.dup_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        header = self.dup_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.dup_table.setColumnWidth(0, 40)
        self.dup_table.setColumnWidth(2, 110)
        self.dup_table.setColumnWidth(3, 160)

        return self.dup_table

    def _create_duplicate_actions(self) -> QWidget:
        """Create the duplicate actions section."""
        widget = QWidget()
        root_layout = QVBoxLayout(widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        keep_newest_btn = QPushButton(t("Keep Newest"))
        keep_newest_btn.setToolTip("Select all duplicates except the newest file in each group")
        keep_newest_btn.clicked.connect(self._keep_dup_newest)

        keep_largest_btn = QPushButton(t("Keep Largest"))
        keep_largest_btn.setToolTip("Select all duplicates except the largest file in each group")
        keep_largest_btn.clicked.connect(self._keep_dup_largest)

        manual_btn = QPushButton(t("Manual Pick"))
        manual_btn.setToolTip("Clear selections for manual picking")
        manual_btn.clicked.connect(self._clear_dup_selections)

        export_btn = QPushButton(t("Export"))
        export_btn.setToolTip("Export duplicate report")
        export_menu = QMenu(export_btn)
        export_csv_action = export_menu.addAction(t("Export CSV"))
        export_csv_action.triggered.connect(self._export_dup_csv)
        export_json_action = export_menu.addAction(t("Export JSON"))
        export_json_action.triggered.connect(self._export_dup_json)
        export_btn.setMenu(export_menu)

        trash_btn = QPushButton(t("Trash"))
        trash_btn.setToolTip("Open or empty .rnmr_trash")
        trash_menu = QMenu(trash_btn)
        open_trash_action = trash_menu.addAction(t("Open Trash"))
        open_trash_action.triggered.connect(self._open_dup_trash)
        empty_trash_action = trash_menu.addAction(t("Empty Trash"))
        empty_trash_action.triggered.connect(self._empty_dup_trash)
        trash_btn.setMenu(trash_menu)

        delete_btn = QPushButton(t("Safe Delete"))
        delete_btn.setToolTip("Safely move selected files to .rnmr_trash (undoable)")
        delete_btn.setStyleSheet(
            f"background-color: {COLORS['warning']};"
            "color: white;"
            f"border: 1px solid {COLORS['warning']};"
            "font-weight: 700;"
        )
        delete_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        delete_btn.clicked.connect(self._delete_dup_selected)

        hard_delete_btn = QPushButton(t("Permanent Delete"))
        hard_delete_btn.setToolTip("Irreversibly delete selected files")
        hard_delete_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        hard_delete_btn.clicked.connect(self._hard_delete_dup_selected)

        top_row.addWidget(keep_newest_btn)
        top_row.addWidget(keep_largest_btn)
        top_row.addWidget(manual_btn)
        top_row.addStretch()
        top_row.addWidget(export_btn)
        top_row.addWidget(trash_btn)

        bottom_row.addStretch()
        bottom_row.addWidget(delete_btn)
        bottom_row.addWidget(hard_delete_btn)

        root_layout.addLayout(top_row)
        root_layout.addLayout(bottom_row)

        return widget

    def _create_bottom_section(self) -> QWidget:
        """Create the bottom section with rename button and progress."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Status label
        self.status_label = QLabel(t("Ready"))
        self.status_label.setObjectName("mutedLabel")

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)

        # Undo button
        self.undo_btn = QPushButton(t("Undo Last Rename"))
        self.undo_btn.setToolTip(t("Revert the most recent rename batch"))
        self.undo_btn.clicked.connect(self._undo_last_rename)
        self.undo_btn.setEnabled(False)

        # Rename button
        self.rename_btn = QPushButton(t("Rename Selected"))
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
        self.log_toggle_btn.setText(t("Log"))
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
            t("Select Media Folder"),
            start_dir
        )
        if folder:
            self.folder_edit.setText(folder)
            # Save last folder
            self.settings.set("last_folder", folder)
            self.settings.save()
            self._update_button_states()

    def _browse_dup_folder(self):
        """Open folder selection dialog for duplicate scan."""
        start_dir = self.settings.get("last_folder", "")
        if not start_dir or not Path(start_dir).exists():
            start_dir = str(Path.home())

        folder = QFileDialog.getExistingDirectory(
            self,
            t("Select Folder to Scan for Duplicates"),
            start_dir
        )
        if folder:
            self.dup_folder_edit.setText(folder)
            self.settings.set("last_folder", folder)
            self.settings.save()
            self._update_dup_button_states()

    def _update_button_states(self):
        """Update button enabled states."""
        has_folder = bool(self.folder_edit.text())
        has_key = self._has_api_key()
        is_scanning = self.scan_thread is not None
        is_renaming = self.rename_thread is not None
        idle = not is_scanning and not is_renaming

        self.scan_btn.setEnabled(has_folder and has_key and idle)
        self.clear_btn.setEnabled(bool(self.items) and idle)
        self.undo_btn.setEnabled(idle and self._has_undoable_transactions())

        # Check if there are any checked pending items
        has_pending = any(
            item.checked and item.status == "pending"
            for item in self.items
        )
        self.rename_btn.setEnabled(has_pending and idle)

    def _update_dup_button_states(self):
        """Update duplicate finder button states."""
        has_folder = bool(self.dup_folder_edit.text())
        is_scanning = self.dup_scan_thread is not None
        idle = not is_scanning

        self.dup_scan_btn.setEnabled(has_folder and idle)
        self.dup_clear_btn.setEnabled(bool(self.dup_groups) and idle)

    def _log(self, message: str):
        """Add message to log."""
        self.log_text.append(message)

    def _has_undoable_transactions(self) -> bool:
        """Check if any non-reverted transactions exist in history."""
        return self._history.has_undoable()

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
        """Revert the most recent non-reverted rename transaction.

        Safety rules:
        - If any old_path already exists (conflict), abort the entire
          batch and show a warning.  No partial reverts.
        - If the renamed file is missing (e.g. user moved it), skip it
          safely but still mark the transaction as reverted.
        """
        tx = self._history.get_last_undoable()
        if tx is None:
            QMessageBox.information(
            self, t("Nothing to Undo"), t("No transactions to undo.")
            )
            return

        if not tx.items:
            self._history.mark_reverted(tx.batch_id)
            self._update_button_states()
            return

        # --- Pre-flight: detect conflicts (old_path already exists) ---
        conflicts: list[str] = []
        missing: list[str] = []
        for entry in tx.items:
            new_p = Path(entry.new_path)
            old_p = Path(entry.old_path)
            if not new_p.exists():
                missing.append(new_p.name)
            elif old_p.exists() and old_p.resolve() != new_p.resolve():
                conflicts.append(old_p.name)

        # Hard-abort on conflicts -- no partial revert
        if conflicts:
            msg = (
                "Cannot undo -- the following original filenames "
                "already exist:\n\n"
            )
            msg += "\n".join(conflicts[:10])
            if len(conflicts) > 10:
                msg += f"\n... and {len(conflicts) - 10} more"
            QMessageBox.warning(self, t("Cannot Undo"), msg)
            return

        # Build confirmation message
        revertable = len(tx.items) - len(missing)
        confirm_text = (
            f"Revert {revertable} rename(s) from batch {tx.batch_id}?\n"
            f"(timestamp: {tx.timestamp})"
        )
        if missing:
            confirm_text += (
                f"\n\n{len(missing)} file(s) no longer exist and will "
                f"be skipped."
            )

        result = QMessageBox.question(
            self,
            t("Confirm Undo"),
            confirm_text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        # --- Execute revert ---
        reverted = 0
        skipped = 0
        for entry in tx.items:
            new_p = Path(entry.new_path)
            old_p = Path(entry.old_path)

            if not new_p.exists():
                skipped += 1
                self._log(f"[UNDO] Skipped (missing): {new_p.name}")
                continue

            try:
                new_p.rename(old_p)
                reverted += 1
            except Exception as e:
                self._log(f"[UNDO] Error reverting {new_p.name}: {e}")

        # Always mark as reverted (even if some files were missing)
        self._history.mark_reverted(tx.batch_id)

        summary = f"Undo complete: {reverted} file(s) reverted"
        if skipped:
            summary += f", {skipped} skipped (missing)"
        self._log(summary)
        self.status_label.setText(summary)
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
            episode_title_language=self.settings.get("episode_title_language", "same"),
            force_english_episode_titles=self.settings.get("force_english_episode_titles", False),
            always_confirm_tmdb=use_tmdb and self.settings.get("always_confirm_tmdb", False),
            always_ask_media_type=use_tmdb and self.settings.get("always_ask_media_type", False),
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
        self.scan_worker.status_update.connect(self._on_status_update)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.lookup_failed.connect(self._on_lookup_failed)
        self.scan_worker.tmdb_select_requested.connect(self._on_tmdb_select_requested)
        self.scan_worker.type_select_requested.connect(self._on_type_select_requested)

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
        self._log(t("Stopping scan..."))
        self.status_label.setText(t("Stopping..."))

    @Slot()
    def _on_scan_started(self):
        """Handle scan started."""
        self.status_label.setText(t("Scanning..."))
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
        self.status_label.setText(t("Scanning: {current}/{total}").replace("{current}", str(current)).replace("{total}", str(total)))

    @Slot(str)
    def _on_status_update(self, message: str):
        """Handle non-blocking status bar updates from the worker."""
        self.status_label.setText(message)

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
        elif source == "ffprobe":
            source_item = QTableWidgetItem("\u2714 Probe")
            source_item.setForeground(QColor(COLORS["accent"]))
            source_item.setToolTip("TMDB (via embedded metadata)")
        elif source == "unidentified":
            source_item = QTableWidgetItem("\u2716 Unknown")
            source_item.setForeground(QColor(COLORS["error"]))
            source_item.setToolTip("TMDB was available but no match was found")
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
        self.status_label.setText(
            t("Found {total} files ({pending} to rename)")
            .replace("{total}", str(total))
            .replace("{pending}", str(pending))
        )

        self._log(
            t("Scan complete: {total} files, {pending} pending")
            .replace("{total}", str(total))
            .replace("{pending}", str(pending))
        )

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
        self.status_label.setText(t("Error"))
        self._log(f"[ERROR] {error}")

        QMessageBox.critical(self, t("Scan Error"), error)

        if self.scan_thread:
            self.scan_thread.quit()
            self.scan_thread.wait()
            self.scan_thread = None

        self._update_button_states()

    # ------------------------------------------------------------------
    # Duplicate Finder
    # ------------------------------------------------------------------

    def _start_dup_scan(self):
        """Start duplicate scan operation."""
        folder = self.dup_folder_edit.text()
        if not folder:
            return

        self._clear_dup_results()

        self.dup_worker = DuplicateScanWorker(
            folder_path=folder,
            recursive=self.dup_recursive_cb.isChecked(),
            include_all_files=self.dup_all_files_cb.isChecked(),
        )

        self.dup_scan_thread = QThread()
        self.dup_worker.moveToThread(self.dup_scan_thread)

        self.dup_scan_thread.started.connect(self.dup_worker.run)
        self.dup_worker.started.connect(self._on_dup_scan_started)
        self.dup_worker.progress.connect(self._on_dup_scan_progress)
        self.dup_worker.status_update.connect(self._on_dup_status_update)
        self.dup_worker.log.connect(self._log)
        self.dup_worker.finished.connect(self._on_dup_scan_finished)
        self.dup_worker.error.connect(self._on_dup_scan_error)

        self.dup_scan_thread.start()

    def _stop_dup_scan(self):
        """Stop duplicate scan operation."""
        if self.dup_scan_thread and hasattr(self, "dup_worker"):
            self.dup_worker.cancel()
            self._log(t("Stopping duplicate scan..."))
            self.dup_status_label.setText(t("Stopping..."))

    @Slot()
    def _on_dup_scan_started(self):
        """Handle duplicate scan started."""
        self.dup_status_label.setText(t("Scanning..."))
        self.dup_progress_bar.setVisible(True)
        self.dup_progress_bar.setRange(0, 1)
        self.dup_progress_bar.setValue(0)
        self.dup_stop_btn.setVisible(True)
        self._update_dup_button_states()

    @Slot(int, int)
    def _on_dup_scan_progress(self, current: int, total: int):
        """Handle duplicate scan progress."""
        if total <= 0:
            return
        self.dup_progress_bar.setRange(0, total)
        self.dup_progress_bar.setValue(current)

    @Slot(str)
    def _on_dup_status_update(self, message: str):
        """Handle duplicate scan status updates."""
        self.dup_status_label.setText(message)

    @Slot(object)
    def _on_dup_scan_finished(self, groups: list[dict]):
        """Handle duplicate scan finished."""
        self.dup_progress_bar.setVisible(False)
        self.dup_stop_btn.setVisible(False)

        self.dup_groups = groups or []
        self._render_dup_groups()

        total_groups = len(self.dup_groups)
        total_files = sum(len(g["items"]) for g in self.dup_groups)
        if total_groups == 0:
            self.dup_status_label.setText(t("No duplicates found."))
        else:
            self.dup_status_label.setText(
                t("Found {groups} group(s), {files} file(s)")
                .replace("{groups}", str(total_groups))
                .replace("{files}", str(total_files))
            )

        if self.dup_scan_thread:
            self.dup_scan_thread.quit()
            self.dup_scan_thread.wait()
            self.dup_scan_thread = None

        self._update_dup_button_states()

    @Slot(str)
    def _on_dup_scan_error(self, error: str):
        """Handle duplicate scan error."""
        self.dup_progress_bar.setVisible(False)
        self.dup_stop_btn.setVisible(False)
        self.dup_status_label.setText(t("Error"))

        QMessageBox.critical(self, t("Duplicate Scan Error"), error)

        if self.dup_scan_thread:
            self.dup_scan_thread.quit()
            self.dup_scan_thread.wait()
            self.dup_scan_thread = None

        self._update_dup_button_states()

    def _clear_dup_results(self, keep_status: bool = False):
        """Clear duplicate results and reset UI state."""
        self.dup_table.setRowCount(0)
        self.dup_groups = []
        self._dup_row_map = []
        self._dup_header_rows = set()
        self.dup_progress_bar.setVisible(False)
        self.dup_progress_bar.setValue(0)
        if not keep_status:
            self.dup_status_label.setText(t("Ready"))
        self._update_dup_button_states()

    def _render_dup_groups(self):
        """Render duplicate groups into the table."""
        self.dup_table.setRowCount(0)
        self._dup_row_map = []
        self._dup_header_rows = set()

        if not self.dup_groups:
            return

        group_num = 0
        for group in self.dup_groups:
            group_num += 1
            group_type = group.get("group_type", "name")
            items = group.get("items", [])
            if not items:
                continue

            header_text = (
                f"Group {group_num} - "
                f"{'Exact Hash' if group_type == 'hash' else 'Name Match'} "
                f"({len(items)} files)"
            )
            header_row = self.dup_table.rowCount()
            self.dup_table.insertRow(header_row)
            header_item = QTableWidgetItem(header_text)
            header_item.setFlags(Qt.ItemIsEnabled)
            header_item.setBackground(QBrush(QColor(COLORS["panel_light"])))
            header_font = QFont()
            header_font.setBold(True)
            header_item.setFont(header_font)
            self.dup_table.setItem(header_row, 1, header_item)
            self.dup_table.setSpan(header_row, 1, 1, 4)
            self._dup_row_map.append(None)
            self._dup_header_rows.add(header_row)

            for item in items:
                self._add_dup_item_row(item)

        self.dup_table.resizeRowsToContents()

    def _add_dup_item_row(self, item):
        """Add a duplicate item row."""
        row_idx = self.dup_table.rowCount()
        self.dup_table.insertRow(row_idx)

        cb_widget = QWidget()
        cb_layout = QHBoxLayout(cb_widget)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        cb_layout.setAlignment(Qt.AlignCenter)
        checkbox = QCheckBox()
        checkbox.setChecked(False)
        checkbox.stateChanged.connect(lambda state, r=row_idx: self._on_dup_checkbox_changed(r, state))
        cb_layout.addWidget(checkbox)
        self.dup_table.setCellWidget(row_idx, 0, cb_widget)

        path_item = QTableWidgetItem(str(item.path))
        path_item.setToolTip(str(item.path))
        self.dup_table.setItem(row_idx, 1, path_item)

        size_item = QTableWidgetItem(self._format_size(item.size))
        self.dup_table.setItem(row_idx, 2, size_item)

        mod_time = datetime.fromtimestamp(item.mtime).strftime("%Y-%m-%d %H:%M")
        mod_item = QTableWidgetItem(mod_time)
        self.dup_table.setItem(row_idx, 3, mod_item)

        hash_item = QTableWidgetItem(item.hash or "")
        self.dup_table.setItem(row_idx, 4, hash_item)

        self._dup_row_map.append({
            "item": item,
            "selected": False,
            "row": row_idx,
        })

    def _on_dup_checkbox_changed(self, row: int, state: int):
        """Handle duplicate checkbox change."""
        if row < len(self._dup_row_map) and self._dup_row_map[row]:
            self._dup_row_map[row]["selected"] = state == Qt.Checked

    def _set_dup_row_checked(self, row: int, checked: bool):
        """Set checkbox state for a duplicate row."""
        if row >= self.dup_table.rowCount():
            return
        widget = self.dup_table.cellWidget(row, 0)
        if widget is None:
            return
        cb = widget.findChild(QCheckBox)
        if cb is not None:
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        if row < len(self._dup_row_map) and self._dup_row_map[row]:
            self._dup_row_map[row]["selected"] = checked

    def _clear_dup_selections(self):
        """Clear all duplicate selections."""
        for row, info in enumerate(self._dup_row_map):
            if info is None:
                continue
            self._set_dup_row_checked(row, False)

    def _keep_dup_newest(self):
        """Select all except newest file in each group."""
        if not self.dup_groups:
            return
        self._clear_dup_selections()
        for group in self.dup_groups:
            items = group.get("items", [])
            if len(items) < 2:
                continue
            newest = max(items, key=lambda i: (i.mtime, i.size))
            for info in self._dup_row_map:
                if info and info["item"] in items and info["item"] != newest:
                    self._set_dup_row_checked(info["row"], True)

    def _keep_dup_largest(self):
        """Select all except largest file in each group."""
        if not self.dup_groups:
            return
        self._clear_dup_selections()
        for group in self.dup_groups:
            items = group.get("items", [])
            if len(items) < 2:
                continue
            largest = max(items, key=lambda i: (i.size, i.mtime))
            for info in self._dup_row_map:
                if info and info["item"] in items and info["item"] != largest:
                    self._set_dup_row_checked(info["row"], True)

    def _get_selected_dup_items(self) -> list:
        """Return selected duplicate items."""
        selected = []
        for info in self._dup_row_map:
            if info and info["selected"]:
                selected.append(info["item"])
        return selected

    def _delete_dup_selected(self):
        """Delete (move) selected duplicates with confirmation."""
        selected = self._get_selected_dup_items()
        if not selected:
            QMessageBox.information(self, t("No Selection"), t("No files selected for deletion."))
            return

        folder = self.dup_folder_edit.text()
        if not folder:
            return

        trash_path = Path(folder) / ".rnmr_trash"
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle(t("Confirm Safe Delete"))
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            f"<b>{t('Safe delete will move files to trash, not permanently delete them.')}</b>"
        )
        msg.setInformativeText(
            f"Files selected: {len(selected)}\n"
            f"Destination: {trash_path}\n\n"
            + t("You can recover them using 'Undo Last Rename' or from the Trash menu.")
        )
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        preview = "\n".join(str(i.path) for i in selected[:8])
        if len(selected) > 8:
            preview += f"\n... and {len(selected) - 8} more"
        msg.setDetailedText(preview)

        if msg.exec() != QMessageBox.Yes:
            return

        base = Path(folder)
        trash_root = trash_path
        trash_root.mkdir(parents=True, exist_ok=True)

        moved = 0
        errors = 0
        entries = []
        for item in selected:
            try:
                rel = item.path.relative_to(base)
                dest = trash_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    dest = dest.with_name(f"{dest.stem}_{int(datetime.now().timestamp())}{dest.suffix}")
                item.path.rename(dest)
                entries.append({
                    "old_path": str(item.path),
                    "new_path": str(dest),
                })
                moved += 1
            except Exception as e:
                errors += 1
                self._log(f"[DUP DELETE] Failed {item.path.name}: {e}")

        if entries:
            try:
                self._history.save_transaction(
                    folder=folder,
                    items=entries,
                    metadata_source="duplicate_finder",
                )
            except Exception as e:
                self._log(f"[WARN] Could not save delete transaction: {e}")

        summary = f"Moved {moved} file(s) to .rnmr_trash"
        if errors:
            summary += f", {errors} error(s)"
        self.dup_status_label.setText(summary)
        QMessageBox.information(self, t("Delete Complete"), summary)
        self._update_button_states()
        self._clear_dup_results(keep_status=True)

    def _open_dup_trash(self):
        """Open the .rnmr_trash folder."""
        folder = self.dup_folder_edit.text()
        if not folder:
            return
        trash_root = Path(folder) / ".rnmr_trash"
        trash_root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(trash_root)))

    def _empty_dup_trash(self):
        """Permanently delete everything in .rnmr_trash."""
        folder = self.dup_folder_edit.text()
        if not folder:
            return
        trash_root = Path(folder) / ".rnmr_trash"
        if not trash_root.exists():
            QMessageBox.information(self, t("Trash Empty"), t("Trash folder does not exist."))
            return

        result = QMessageBox.warning(
            self,
            t("Empty Trash"),
            (
                "This will permanently delete everything in:\n"
                f"{trash_root}\n\n"
                "This cannot be undone. Proceed?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        import shutil
        try:
            shutil.rmtree(trash_root)
            trash_root.mkdir(parents=True, exist_ok=True)
            self.dup_status_label.setText(t("Trash emptied."))
        except Exception as e:
            QMessageBox.critical(self, t("Empty Trash Failed"), str(e))

    def _hard_delete_dup_selected(self):
        """Permanently delete selected duplicates with confirmation."""
        selected = self._get_selected_dup_items()
        if not selected:
            QMessageBox.information(self, t("No Selection"), t("No files selected for deletion."))
            return

        result = QMessageBox.warning(
            self,
            t("Confirm Permanent Delete"),
            (
                f"You are about to PERMANENTLY delete {len(selected)} file(s).\n\n"
                "This cannot be undone. Proceed?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        deleted = 0
        errors = 0
        for item in selected:
            try:
                item.path.unlink()
                deleted += 1
            except Exception as e:
                errors += 1
                self._log(f"[DUP DELETE] Failed {item.path.name}: {e}")

        summary = f"Deleted {deleted} file(s) permanently"
        if errors:
            summary += f", {errors} error(s)"
        self.dup_status_label.setText(summary)
        QMessageBox.information(self, t("Delete Complete"), summary)
        self._clear_dup_results(keep_status=True)

    def _export_dup_csv(self):
        """Export duplicate report to CSV."""
        if not self.dup_groups:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            t("Export Duplicate Report (CSV)"),
            "duplicates.csv",
            "CSV Files (*.csv)"
        )
        if not filename:
            return

        try:
            lines = ["group,group_type,path,size,modified,hash,norm_name"]
            group_num = 0
            for group in self.dup_groups:
                group_num += 1
                group_type = group.get("group_type", "name")
                for item in group.get("items", []):
                    mod_time = datetime.fromtimestamp(item.mtime).isoformat(sep=" ", timespec="minutes")
                    line = (
                        f"{group_num},{group_type},"
                        f"\"{item.path}\",{item.size},\"{mod_time}\","
                        f"{item.hash},{item.norm_name}"
                    )
                    lines.append(line)
            Path(filename).write_text("\n".join(lines), encoding="utf-8")
            self.dup_status_label.setText(f"Report exported: {filename}")
        except Exception as e:
            QMessageBox.critical(self, t("Export Error"), str(e))

    def _export_dup_json(self):
        """Export duplicate report to JSON."""
        if not self.dup_groups:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            t("Export Duplicate Report (JSON)"),
            "duplicates.json",
            "JSON Files (*.json)"
        )
        if not filename:
            return

        try:
            out = []
            group_num = 0
            for group in self.dup_groups:
                group_num += 1
                group_type = group.get("group_type", "name")
                out.append({
                    "group": group_num,
                    "group_type": group_type,
                    "items": [
                        {
                            "path": str(item.path),
                            "size": item.size,
                            "modified": datetime.fromtimestamp(item.mtime).isoformat(timespec="seconds"),
                            "hash": item.hash,
                            "norm_name": item.norm_name,
                        }
                        for item in group.get("items", [])
                    ],
                })
            import json
            Path(filename).write_text(json.dumps(out, indent=2), encoding="utf-8")
            self.dup_status_label.setText(f"Report exported: {filename}")
        except Exception as e:
            QMessageBox.critical(self, t("Export Error"), str(e))

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Human-readable size formatting."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        for unit in ["KB", "MB", "GB", "TB"]:
            size_bytes /= 1024.0
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
        return f"{size_bytes:.2f} PB"

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

    @Slot(dict)
    def _on_tmdb_select_requested(self, info: dict):
        """Handle TMDB selection prompt -- show dialog on main thread."""
        result = None

        api_key = self.settings.get("tmdb_api_key", "")
        if not api_key:
            import os
            api_key = os.environ.get("TMDB_API_KEY", "")

        dlg = TMDBSelectDialog(
            results=info.get("results", []),
            parsed_title=info.get("parsed_title", ""),
            media_type=info.get("media_type", "series"),
            file_count=info.get("file_count", 1),
            api_key=api_key,
            parent=self,
        )
        self._active_lookup_dialog = dlg
        choice = dlg.exec()
        self._active_lookup_dialog = None

        if choice == QDialog.Accepted:
            tmdb_id, media_type, title = dlg.get_result()
            if tmdb_id and media_type:
                result = {
                    "tmdb_id": tmdb_id,
                    "media_type": media_type,
                    "title": title,
                }
        elif choice == SEL_SKIP_ALL:
            result = {"__skip_all__": True}
        # SEL_SKIP and reject both leave result as None (skip batch)

        if hasattr(self, 'scan_worker'):
            self.scan_worker.set_lookup_result(result)

    @Slot(dict)
    def _on_type_select_requested(self, info: dict):
        """Handle media-type confirmation prompt."""
        dlg = MediaTypeDialog(info, self)
        self._active_lookup_dialog = dlg
        choice = dlg.exec()
        self._active_lookup_dialog = None

        if choice == MT_SERIES:
            result = {"media_type": "series"}
        elif choice == MT_MOVIE:
            result = {"media_type": "movie"}
        elif choice == MT_SKIP_ALL:
            result = {"__skip_all__": True}
        else:
            result = None

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
        """Persist a rename transaction to the centralized history DB."""
        folder = self.folder_edit.text()
        if not folder:
            return

        # Collect successfully renamed entries
        entries: list[dict] = []
        metadata_source = "inferred"
        for _row, item in items:
            if item.status != "renamed":
                continue
            entries.append({
                "old_path": str(item.original_path),
                "new_path": str(item.new_path) if item.new_path else "",
            })
            # Use the metadata source from the first renamed item
            if item.metadata and item.metadata.get("metadata_source"):
                metadata_source = item.metadata["metadata_source"]

        if not entries:
            return

        try:
            batch_id = self._history.save_transaction(
                folder=folder,
                items=entries,
                metadata_source=metadata_source,
            )
            self._log(
                f"Transaction saved: {len(entries)} item(s), "
                f"batch {batch_id}"
            )
        except Exception as e:
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

        if self.dup_scan_thread and hasattr(self, "dup_worker"):
            self.dup_worker.cancel()
            self.dup_scan_thread.quit()
            self.dup_scan_thread.wait()

        event.accept()


