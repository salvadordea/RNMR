"""Settings dialog for RNMR GUI."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLineEdit, QComboBox, QLabel,
    QGroupBox, QTextEdit, QMessageBox, QTabWidget,
    QWidget, QCheckBox
)
from PySide6.QtCore import Qt, Signal

from .settings import (
    SettingsManager,
    validate_template, get_sample_data, render_template,
    SERIES_PRESETS, MOVIE_PRESETS, TEMPLATE_VARIABLES,
    DEFAULT_SERIES_TEMPLATE, DEFAULT_MOVIE_TEMPLATE,
    DEFAULT_SETTINGS,
)
from .theme import COLORS


class SettingsDialog(QDialog):
    """Application settings dialog with General / TMDB / Behavior sections."""

    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Settings")
        self.setMinimumWidth(550)
        self.setMinimumHeight(520)

        self.mgr = SettingsManager()

        self._setup_ui()
        self._load_current_settings()
        self._update_previews()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        tabs = QTabWidget()
        tabs.addTab(self._create_general_tab(), "General")
        tabs.addTab(self._create_tmdb_tab(), "TMDB")
        tabs.addTab(self._create_behavior_tab(), "Behavior")
        layout.addWidget(tabs)

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_and_close)

        button_layout.addWidget(reset_btn)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    # -- General tab ---------------------------------------------------

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # ---- Series section ----
        series_group = QGroupBox("Series Naming")
        series_layout = QVBoxLayout(series_group)

        preset_form = QFormLayout()
        self.series_preset_combo = QComboBox()
        self.series_preset_combo.addItems(SERIES_PRESETS.keys())
        self.series_preset_combo.currentTextChanged.connect(
            self._on_series_preset_changed
        )
        preset_form.addRow("Preset:", self.series_preset_combo)
        series_layout.addLayout(preset_form)

        self.series_template_edit = QLineEdit()
        self.series_template_edit.setPlaceholderText("Enter custom template...")
        self.series_template_edit.textChanged.connect(self._update_series_preview)
        series_layout.addWidget(self.series_template_edit)

        self.series_validation_label = QLabel("")
        self.series_validation_label.setWordWrap(True)
        series_layout.addWidget(self.series_validation_label)

        self.series_preview_label = QLabel("")
        self.series_preview_label.setStyleSheet(
            f"color: {COLORS['accent']}; font-weight: 500;"
        )
        self.series_preview_label.setWordWrap(True)
        series_layout.addWidget(self.series_preview_label)

        layout.addWidget(series_group)

        # ---- Movie section ----
        movie_group = QGroupBox("Movie Naming")
        movie_layout = QVBoxLayout(movie_group)

        preset_form2 = QFormLayout()
        self.movie_preset_combo = QComboBox()
        self.movie_preset_combo.addItems(MOVIE_PRESETS.keys())
        self.movie_preset_combo.currentTextChanged.connect(
            self._on_movie_preset_changed
        )
        preset_form2.addRow("Preset:", self.movie_preset_combo)
        movie_layout.addLayout(preset_form2)

        self.movie_template_edit = QLineEdit()
        self.movie_template_edit.setPlaceholderText("Enter custom template...")
        self.movie_template_edit.textChanged.connect(self._update_movie_preview)
        movie_layout.addWidget(self.movie_template_edit)

        self.movie_validation_label = QLabel("")
        self.movie_validation_label.setWordWrap(True)
        movie_layout.addWidget(self.movie_validation_label)

        self.movie_preview_label = QLabel("")
        self.movie_preview_label.setStyleSheet(
            f"color: {COLORS['accent']}; font-weight: 500;"
        )
        self.movie_preview_label.setWordWrap(True)
        movie_layout.addWidget(self.movie_preview_label)

        layout.addWidget(movie_group)

        # ---- Template variables reference ----
        help_group = QGroupBox("Available Variables")
        help_layout = QVBoxLayout(help_group)
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setMaximumHeight(110)
        html = "<table>"
        html += "<tr><td colspan='2' style='font-weight:600;'>Series</td></tr>"
        for var, desc in TEMPLATE_VARIABLES["series"]:
            html += (
                f"<tr><td style='color:{COLORS['accent']};'>"
                f"<code>{var}</code></td>"
                f"<td style='color:{COLORS['text_muted']};'>{desc}</td></tr>"
            )
        html += "<tr><td colspan='2' style='font-weight:600;'>Movie</td></tr>"
        for var, desc in TEMPLATE_VARIABLES["movie"]:
            html += (
                f"<tr><td style='color:{COLORS['accent']};'>"
                f"<code>{var}</code></td>"
                f"<td style='color:{COLORS['text_muted']};'>{desc}</td></tr>"
            )
        html += "</table>"
        help_text.setHtml(html)
        help_layout.addWidget(help_text)
        layout.addWidget(help_group)

        layout.addStretch()
        return widget

    # -- TMDB tab ------------------------------------------------------

    def _create_tmdb_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        group = QGroupBox("TMDB Configuration")
        form = QFormLayout(group)
        form.setSpacing(12)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Enter your TMDB API key...")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        form.addRow("API Key:", self.api_key_edit)

        # Toggle visibility
        show_btn = QPushButton("Show")
        show_btn.setCheckable(True)
        show_btn.toggled.connect(
            lambda checked: self.api_key_edit.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        show_btn.toggled.connect(
            lambda checked: show_btn.setText("Hide" if checked else "Show")
        )
        form.addRow("", show_btn)

        self.language_edit = QLineEdit()
        self.language_edit.setPlaceholderText("en-US")
        form.addRow("Language:", self.language_edit)

        layout.addWidget(group)

        help_label = QLabel(
            "Get a free API key at "
            "<a href='https://www.themoviedb.org/settings/api' "
            "style='color:" + COLORS["accent"] + ";'>"
            "themoviedb.org/settings/api</a>.<br>"
            "If left blank, the TMDB_API_KEY environment variable is used."
        )
        help_label.setOpenExternalLinks(True)
        help_label.setWordWrap(True)
        help_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        layout.addWidget(help_label)

        layout.addStretch()
        return widget

    # -- Behavior tab --------------------------------------------------

    def _create_behavior_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        group = QGroupBox("Rename Behavior")
        form = QVBoxLayout(group)
        form.setSpacing(14)

        self.overwrite_cb = QCheckBox("Ask before overwriting files")
        self.overwrite_cb.setToolTip(
            "Show a confirmation dialog when a destination file already exists."
        )
        form.addWidget(self.overwrite_cb)

        self.interactive_cb = QCheckBox("Enable manual search fallback")
        self.interactive_cb.setToolTip(
            "When automatic TMDB detection fails, show a search dialog "
            "so you can find the correct title manually."
        )
        form.addWidget(self.interactive_cb)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load_current_settings(self):
        # General - series
        idx = self.series_preset_combo.findText(
            self.mgr.get("series_preset", "Standard")
        )
        if idx >= 0:
            self.series_preset_combo.setCurrentIndex(idx)
        self.series_template_edit.setText(
            self.mgr.get("series_template", DEFAULT_SERIES_TEMPLATE)
        )

        # General - movie
        idx = self.movie_preset_combo.findText(
            self.mgr.get("movie_preset", "Standard")
        )
        if idx >= 0:
            self.movie_preset_combo.setCurrentIndex(idx)
        self.movie_template_edit.setText(
            self.mgr.get("movie_template", DEFAULT_MOVIE_TEMPLATE)
        )

        # TMDB
        self.api_key_edit.setText(self.mgr.get("tmdb_api_key", ""))
        self.language_edit.setText(self.mgr.get("tmdb_language", "en-US"))

        # Behavior
        self.overwrite_cb.setChecked(self.mgr.get("ask_before_overwrite", True))
        self.interactive_cb.setChecked(self.mgr.get("interactive_fallback", True))

    def _save_and_close(self):
        series_template = self.series_template_edit.text()
        movie_template = self.movie_template_edit.text()

        ok, err = validate_template(series_template, "series")
        if not ok:
            QMessageBox.warning(
                self, "Invalid Series Template",
                f"The series template is invalid:\n{err}",
            )
            return

        ok, err = validate_template(movie_template, "movie")
        if not ok:
            QMessageBox.warning(
                self, "Invalid Movie Template",
                f"The movie template is invalid:\n{err}",
            )
            return

        # Persist everything through SettingsManager
        self.mgr.set("series_template", series_template)
        self.mgr.set("movie_template", movie_template)
        self.mgr.set("series_preset", self.series_preset_combo.currentText())
        self.mgr.set("movie_preset", self.movie_preset_combo.currentText())
        self.mgr.set("tmdb_api_key", self.api_key_edit.text().strip())
        self.mgr.set("tmdb_language", self.language_edit.text().strip() or "en-US")
        self.mgr.set("ask_before_overwrite", self.overwrite_cb.isChecked())
        self.mgr.set("interactive_fallback", self.interactive_cb.isChecked())

        if self.mgr.save():
            self.settings_changed.emit()
            self.accept()
        else:
            QMessageBox.warning(
                self, "Save Error", "Could not save settings to file."
            )

    def _reset_defaults(self):
        self.series_preset_combo.setCurrentText("Standard")
        self.series_template_edit.setText(DEFAULT_SERIES_TEMPLATE)
        self.movie_preset_combo.setCurrentText("Standard")
        self.movie_template_edit.setText(DEFAULT_MOVIE_TEMPLATE)
        self.api_key_edit.setText("")
        self.language_edit.setText("en-US")
        self.overwrite_cb.setChecked(True)
        self.interactive_cb.setChecked(True)
        self._update_previews()

    # ------------------------------------------------------------------
    # Preset / preview helpers
    # ------------------------------------------------------------------

    def _on_series_preset_changed(self, preset: str):
        template = SERIES_PRESETS.get(preset, "")
        if template:
            self.series_template_edit.setText(template)
        self._update_series_preview()

    def _on_movie_preset_changed(self, preset: str):
        template = MOVIE_PRESETS.get(preset, "")
        if template:
            self.movie_template_edit.setText(template)
        self._update_movie_preview()

    def _update_previews(self):
        self._update_series_preview()
        self._update_movie_preview()

    def _update_series_preview(self):
        template = self.series_template_edit.text()
        if not template:
            self.series_preview_label.setText("(empty template)")
            self.series_validation_label.setText("")
            return

        ok, err = validate_template(template, "series")
        if ok:
            try:
                sample = get_sample_data("series")
                if "{episode_title}" in template and not sample.get("episode_title"):
                    sample["episode_title"] = "Episode Name"
                preview = render_template(template, sample)
                self.series_preview_label.setText(f"{preview}.mkv")
                self.series_validation_label.setText("")
                self.series_validation_label.setStyleSheet("")
            except Exception as e:
                self.series_preview_label.setText("(error)")
                self.series_validation_label.setText(str(e))
                self.series_validation_label.setStyleSheet(
                    f"color: {COLORS['error']};"
                )
        else:
            self.series_preview_label.setText("(invalid)")
            self.series_validation_label.setText(err)
            self.series_validation_label.setStyleSheet(
                f"color: {COLORS['error']};"
            )

    def _update_movie_preview(self):
        template = self.movie_template_edit.text()
        if not template:
            self.movie_preview_label.setText("(empty template)")
            self.movie_validation_label.setText("")
            return

        ok, err = validate_template(template, "movie")
        if ok:
            try:
                sample = get_sample_data("movie")
                preview = render_template(template, sample)
                self.movie_preview_label.setText(f"{preview}.mkv")
                self.movie_validation_label.setText("")
                self.movie_validation_label.setStyleSheet("")
            except Exception as e:
                self.movie_preview_label.setText("(error)")
                self.movie_validation_label.setText(str(e))
                self.movie_validation_label.setStyleSheet(
                    f"color: {COLORS['error']};"
                )
        else:
            self.movie_preview_label.setText("(invalid)")
            self.movie_validation_label.setText(err)
            self.movie_validation_label.setStyleSheet(
                f"color: {COLORS['error']};"
            )
