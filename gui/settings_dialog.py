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
from .i18n import SUPPORTED_LANGUAGES, t


class SettingsDialog(QDialog):
    """Application settings dialog with General / TMDB / Behavior sections."""

    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(t("Settings"))
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
        tabs.addTab(self._create_general_tab(), t("General"))
        tabs.addTab(self._create_tmdb_tab(), t("TMDB"))
        tabs.addTab(self._create_behavior_tab(), t("Behavior"))
        layout.addWidget(tabs)

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        reset_btn = QPushButton(t("Reset to Defaults"))
        reset_btn.clicked.connect(self._reset_defaults)

        cancel_btn = QPushButton(t("Cancel"))
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton(t("Save"))
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

        # ---- App language ----
        app_group = QGroupBox(t("App Language"))
        app_form = QFormLayout(app_group)
        self.app_lang_combo = QComboBox()
        for code, label in SUPPORTED_LANGUAGES.items():
            self.app_lang_combo.addItem(label, code)
        app_form.addRow(t("Language") + ":", self.app_lang_combo)
        app_note = QLabel(t("Restart the app to apply language changes everywhere."))
        app_note.setWordWrap(True)
        app_note.setStyleSheet(f"color: {COLORS['text_muted']};")
        app_form.addRow("", app_note)
        layout.addWidget(app_group)

        # ---- Series section ----
        series_group = QGroupBox(t("Series Naming"))
        series_layout = QVBoxLayout(series_group)

        preset_form = QFormLayout()
        self.series_preset_combo = QComboBox()
        self.series_preset_combo.addItems(SERIES_PRESETS.keys())
        self.series_preset_combo.currentTextChanged.connect(
            self._on_series_preset_changed
        )
        preset_form.addRow(t("Preset:"), self.series_preset_combo)
        series_layout.addLayout(preset_form)

        self.series_template_edit = QLineEdit()
        self.series_template_edit.setPlaceholderText(t("Enter custom template..."))
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
        movie_group = QGroupBox(t("Movie Naming"))
        movie_layout = QVBoxLayout(movie_group)

        preset_form2 = QFormLayout()
        self.movie_preset_combo = QComboBox()
        self.movie_preset_combo.addItems(MOVIE_PRESETS.keys())
        self.movie_preset_combo.currentTextChanged.connect(
            self._on_movie_preset_changed
        )
        preset_form2.addRow(t("Preset:"), self.movie_preset_combo)
        movie_layout.addLayout(preset_form2)

        self.movie_template_edit = QLineEdit()
        self.movie_template_edit.setPlaceholderText(t("Enter custom template..."))
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
        help_group = QGroupBox(t("Available Variables"))
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

        group = QGroupBox(t("TMDB Configuration"))
        form = QFormLayout(group)
        form.setSpacing(12)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText(t("Enter your TMDB API key..."))
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        form.addRow(t("API Key:"), self.api_key_edit)

        # Toggle visibility
        show_btn = QPushButton(t("Show"))
        show_btn.setCheckable(True)
        show_btn.toggled.connect(
            lambda checked: self.api_key_edit.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        show_btn.toggled.connect(
            lambda checked: show_btn.setText(t("Hide") if checked else t("Show"))
        )
        form.addRow("", show_btn)

        # Key action buttons
        key_btn_layout = QHBoxLayout()
        remove_key_btn = QPushButton(t("Remove API Key"))
        remove_key_btn.setToolTip(t("Clear the stored API key"))
        remove_key_btn.clicked.connect(self._remove_api_key)
        key_btn_layout.addWidget(remove_key_btn)

        dashboard_btn = QPushButton(t("Open TMDB Dashboard"))
        dashboard_btn.setToolTip(t("Open your TMDB API settings in a browser"))
        dashboard_btn.clicked.connect(self._open_tmdb_dashboard)
        key_btn_layout.addWidget(dashboard_btn)

        key_btn_layout.addStretch()
        form.addRow("", key_btn_layout)

        self.language_edit = QLineEdit()
        self.language_edit.setPlaceholderText("en-US")
        form.addRow(t("Language:") , self.language_edit)

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

    def _remove_api_key(self):
        """Clear the API key field and persist immediately."""
        result = QMessageBox.question(
            self,
            "Remove API Key",
            "Remove the stored TMDB API key?\n\n"
            "Scanning will be disabled until a new key is set.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result == QMessageBox.Yes:
            self.api_key_edit.clear()
            self.mgr.set("tmdb_api_key", "")
            self.mgr.save()
            self.settings_changed.emit()

    @staticmethod
    def _open_tmdb_dashboard():
        """Open the TMDB API settings page in the default browser."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(
            QUrl("https://www.themoviedb.org/settings/api")
        )

    # -- Behavior tab --------------------------------------------------

    def _create_behavior_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        group = QGroupBox(t("Rename Behavior"))
        form = QVBoxLayout(group)
        form.setSpacing(14)

        self.overwrite_cb = QCheckBox(t("Ask before overwriting files"))
        self.overwrite_cb.setToolTip(
            "Show a confirmation dialog when a destination file already exists."
        )
        form.addWidget(self.overwrite_cb)

        self.interactive_cb = QCheckBox(t("Enable manual search fallback"))
        self.interactive_cb.setToolTip(
            "When automatic TMDB detection fails, show a search dialog "
            "so you can find the correct title manually."
        )
        form.addWidget(self.interactive_cb)

        self.confirm_tmdb_cb = QCheckBox(t("Always confirm TMDB match"))
        self.confirm_tmdb_cb.setToolTip(
            "Show a selection dialog with the top TMDB results before "
            "committing to a match, even when confidence is high."
        )
        form.addWidget(self.confirm_tmdb_cb)

        self.ask_media_type_cb = QCheckBox(t("Always ask media type before search"))
        self.ask_media_type_cb.setToolTip(
            "Before searching TMDB, show a dialog to confirm whether "
            "each title group is a TV series or movie."
        )
        form.addWidget(self.ask_media_type_cb)

        layout.addWidget(group)

        # -- Episode Title Language --
        ep_group = QGroupBox(t("Episode Title Language"))
        ep_layout = QVBoxLayout(ep_group)
        ep_layout.setSpacing(14)

        ep_form = QFormLayout()
        ep_form.setSpacing(10)

        self.ep_lang_combo = QComboBox()
        self.ep_lang_combo.addItem(t("Same as metadata language"), "same")
        self.ep_lang_combo.addItem(t("Original language"), "original")
        self.ep_lang_combo.addItem(t("English (forced)"), "en")
        self.ep_lang_combo.setToolTip(
            "Controls the language used when fetching episode titles from TMDB."
        )
        ep_form.addRow(t("Mode:"), self.ep_lang_combo)
        ep_layout.addLayout(ep_form)

        self.force_english_cb = QCheckBox(t("Force episode titles to English"))
        self.force_english_cb.setToolTip(
            "Override the episode title language to English regardless "
            "of the mode above. Useful for anime and foreign-language series."
        )
        self.force_english_cb.toggled.connect(self._on_force_english_toggled)
        ep_layout.addWidget(self.force_english_cb)

        layout.addWidget(ep_group)

        layout.addStretch()
        return widget

    def _on_force_english_toggled(self, checked: bool):
        """Disable language combo when force-English is active."""
        self.ep_lang_combo.setEnabled(not checked)

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load_current_settings(self):
        # App language
        app_lang = self.mgr.get("app_language", "en")
        idx = self.app_lang_combo.findData(app_lang)
        if idx >= 0:
            self.app_lang_combo.setCurrentIndex(idx)

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
        self.confirm_tmdb_cb.setChecked(self.mgr.get("always_confirm_tmdb", False))
        self.ask_media_type_cb.setChecked(self.mgr.get("always_ask_media_type", False))

        # Episode title language
        ep_lang = self.mgr.get("episode_title_language", "same")
        idx = self.ep_lang_combo.findData(ep_lang)
        if idx >= 0:
            self.ep_lang_combo.setCurrentIndex(idx)
        force_en = self.mgr.get("force_english_episode_titles", False)
        self.force_english_cb.setChecked(force_en)
        self.ep_lang_combo.setEnabled(not force_en)

    def _save_and_close(self):
        old_lang = self.mgr.get("app_language", "en")
        new_lang = self.app_lang_combo.currentData() or "en"

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
        self.mgr.set("app_language", new_lang)
        self.mgr.set("series_preset", self.series_preset_combo.currentText())
        self.mgr.set("movie_preset", self.movie_preset_combo.currentText())
        self.mgr.set("tmdb_api_key", self.api_key_edit.text().strip())
        self.mgr.set("tmdb_language", self.language_edit.text().strip() or "en-US")
        self.mgr.set("ask_before_overwrite", self.overwrite_cb.isChecked())
        self.mgr.set("interactive_fallback", self.interactive_cb.isChecked())
        self.mgr.set("always_confirm_tmdb", self.confirm_tmdb_cb.isChecked())
        self.mgr.set("always_ask_media_type", self.ask_media_type_cb.isChecked())
        self.mgr.set(
            "episode_title_language",
            self.ep_lang_combo.currentData() or "same",
        )
        self.mgr.set(
            "force_english_episode_titles",
            self.force_english_cb.isChecked(),
        )

        if self.mgr.save():
            self.settings_changed.emit()
            if old_lang != new_lang:
                QMessageBox.information(
                    self,
                    t("App Language"),
                    t("Restart the app to apply language changes everywhere."),
                )
            self.accept()
        else:
            QMessageBox.warning(
                self, "Save Error", "Could not save settings to file."
            )

    def _reset_defaults(self):
        idx_lang = self.app_lang_combo.findData(DEFAULT_SETTINGS["app_language"])
        if idx_lang >= 0:
            self.app_lang_combo.setCurrentIndex(idx_lang)
        self.series_preset_combo.setCurrentText("Standard")
        self.series_template_edit.setText(DEFAULT_SERIES_TEMPLATE)
        self.movie_preset_combo.setCurrentText("Standard")
        self.movie_template_edit.setText(DEFAULT_MOVIE_TEMPLATE)
        self.api_key_edit.setText("")
        self.language_edit.setText("en-US")
        self.overwrite_cb.setChecked(True)
        self.interactive_cb.setChecked(True)
        self.confirm_tmdb_cb.setChecked(False)
        self.ask_media_type_cb.setChecked(False)
        idx = self.ep_lang_combo.findData("same")
        if idx >= 0:
            self.ep_lang_combo.setCurrentIndex(idx)
        self.force_english_cb.setChecked(False)
        self.ep_lang_combo.setEnabled(True)
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

