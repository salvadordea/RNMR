"""Settings dialog for RNMR GUI."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLineEdit, QComboBox, QLabel,
    QGroupBox, QTextEdit, QMessageBox, QTabWidget, QWidget
)
from PySide6.QtCore import Qt, Signal

from .settings import (
    load_settings, save_settings, validate_template,
    get_sample_data, render_template,
    SERIES_PRESETS, MOVIE_PRESETS, TEMPLATE_VARIABLES,
    DEFAULT_SERIES_TEMPLATE, DEFAULT_MOVIE_TEMPLATE
)
from .theme import COLORS


class SettingsDialog(QDialog):
    """Dialog for configuring naming templates."""

    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Naming Format Settings")
        self.setMinimumWidth(550)
        self.setMinimumHeight(500)

        self.settings = load_settings()

        self._setup_ui()
        self._load_current_settings()
        self._update_previews()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Tab widget for Series / Movies
        tabs = QTabWidget()

        # Series tab
        series_tab = self._create_series_tab()
        tabs.addTab(series_tab, "Series")

        # Movies tab
        movie_tab = self._create_movie_tab()
        tabs.addTab(movie_tab, "Movies")

        layout.addWidget(tabs)

        # Buttons
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

    def _create_series_tab(self) -> QWidget:
        """Create the series settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # Preset dropdown
        preset_group = QGroupBox("Preset")
        preset_layout = QFormLayout(preset_group)

        self.series_preset_combo = QComboBox()
        self.series_preset_combo.addItems(SERIES_PRESETS.keys())
        self.series_preset_combo.currentTextChanged.connect(self._on_series_preset_changed)

        preset_layout.addRow("Format:", self.series_preset_combo)
        layout.addWidget(preset_group)

        # Template editor
        template_group = QGroupBox("Template")
        template_layout = QVBoxLayout(template_group)

        self.series_template_edit = QLineEdit()
        self.series_template_edit.setPlaceholderText("Enter custom template...")
        self.series_template_edit.textChanged.connect(self._update_series_preview)

        template_layout.addWidget(self.series_template_edit)

        # Validation label
        self.series_validation_label = QLabel("")
        self.series_validation_label.setWordWrap(True)
        template_layout.addWidget(self.series_validation_label)

        layout.addWidget(template_group)

        # Preview
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.series_preview_label = QLabel("")
        self.series_preview_label.setStyleSheet(f"color: {COLORS['accent']}; font-weight: 500;")
        self.series_preview_label.setWordWrap(True)

        preview_layout.addWidget(self.series_preview_label)
        layout.addWidget(preview_group)

        # Variables help
        help_group = QGroupBox("Available Variables")
        help_layout = QVBoxLayout(help_group)

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setMaximumHeight(120)

        variables_html = "<table style='font-size: 12px;'>"
        for var, desc in TEMPLATE_VARIABLES["series"]:
            variables_html += f"<tr><td style='color: {COLORS['accent']};'><code>{var}</code></td>"
            variables_html += f"<td style='color: {COLORS['text_muted']};'>{desc}</td></tr>"
        variables_html += "</table>"

        help_text.setHtml(variables_html)
        help_layout.addWidget(help_text)
        layout.addWidget(help_group)

        layout.addStretch()

        return widget

    def _create_movie_tab(self) -> QWidget:
        """Create the movie settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # Preset dropdown
        preset_group = QGroupBox("Preset")
        preset_layout = QFormLayout(preset_group)

        self.movie_preset_combo = QComboBox()
        self.movie_preset_combo.addItems(MOVIE_PRESETS.keys())
        self.movie_preset_combo.currentTextChanged.connect(self._on_movie_preset_changed)

        preset_layout.addRow("Format:", self.movie_preset_combo)
        layout.addWidget(preset_group)

        # Template editor
        template_group = QGroupBox("Template")
        template_layout = QVBoxLayout(template_group)

        self.movie_template_edit = QLineEdit()
        self.movie_template_edit.setPlaceholderText("Enter custom template...")
        self.movie_template_edit.textChanged.connect(self._update_movie_preview)

        template_layout.addWidget(self.movie_template_edit)

        # Validation label
        self.movie_validation_label = QLabel("")
        self.movie_validation_label.setWordWrap(True)
        template_layout.addWidget(self.movie_validation_label)

        layout.addWidget(template_group)

        # Preview
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.movie_preview_label = QLabel("")
        self.movie_preview_label.setStyleSheet(f"color: {COLORS['accent']}; font-weight: 500;")
        self.movie_preview_label.setWordWrap(True)

        preview_layout.addWidget(self.movie_preview_label)
        layout.addWidget(preview_group)

        # Variables help
        help_group = QGroupBox("Available Variables")
        help_layout = QVBoxLayout(help_group)

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setMaximumHeight(100)

        variables_html = "<table style='font-size: 12px;'>"
        for var, desc in TEMPLATE_VARIABLES["movie"]:
            variables_html += f"<tr><td style='color: {COLORS['accent']};'><code>{var}</code></td>"
            variables_html += f"<td style='color: {COLORS['text_muted']};'>{desc}</td></tr>"
        variables_html += "</table>"

        help_text.setHtml(variables_html)
        help_layout.addWidget(help_text)
        layout.addWidget(help_group)

        layout.addStretch()

        return widget

    def _load_current_settings(self):
        """Load current settings into the UI."""
        # Series
        series_preset = self.settings.get("series_preset", "Standard")
        series_template = self.settings.get("series_template", DEFAULT_SERIES_TEMPLATE)

        idx = self.series_preset_combo.findText(series_preset)
        if idx >= 0:
            self.series_preset_combo.setCurrentIndex(idx)

        self.series_template_edit.setText(series_template)

        # Movies
        movie_preset = self.settings.get("movie_preset", "Standard")
        movie_template = self.settings.get("movie_template", DEFAULT_MOVIE_TEMPLATE)

        idx = self.movie_preset_combo.findText(movie_preset)
        if idx >= 0:
            self.movie_preset_combo.setCurrentIndex(idx)

        self.movie_template_edit.setText(movie_template)

    def _on_series_preset_changed(self, preset: str):
        """Handle series preset selection."""
        template = SERIES_PRESETS.get(preset, "")
        if template:
            self.series_template_edit.setText(template)
        self._update_series_preview()

    def _on_movie_preset_changed(self, preset: str):
        """Handle movie preset selection."""
        template = MOVIE_PRESETS.get(preset, "")
        if template:
            self.movie_template_edit.setText(template)
        self._update_movie_preview()

    def _update_previews(self):
        """Update both preview labels."""
        self._update_series_preview()
        self._update_movie_preview()

    def _update_series_preview(self):
        """Update series preview label."""
        template = self.series_template_edit.text()

        if not template:
            self.series_preview_label.setText("(empty template)")
            self.series_validation_label.setText("")
            return

        is_valid, error = validate_template(template, "series")

        if is_valid:
            try:
                sample = get_sample_data("series")
                # Handle empty episode title gracefully
                if "{episode_title}" in template and not sample.get("episode_title"):
                    sample["episode_title"] = "Episode Name"

                preview = render_template(template, sample)
                self.series_preview_label.setText(f"{preview}.mkv")
                self.series_validation_label.setText("")
                self.series_validation_label.setStyleSheet("")
            except Exception as e:
                self.series_preview_label.setText("(error)")
                self.series_validation_label.setText(str(e))
                self.series_validation_label.setStyleSheet(f"color: {COLORS['error']};")
        else:
            self.series_preview_label.setText("(invalid)")
            self.series_validation_label.setText(error)
            self.series_validation_label.setStyleSheet(f"color: {COLORS['error']};")

    def _update_movie_preview(self):
        """Update movie preview label."""
        template = self.movie_template_edit.text()

        if not template:
            self.movie_preview_label.setText("(empty template)")
            self.movie_validation_label.setText("")
            return

        is_valid, error = validate_template(template, "movie")

        if is_valid:
            try:
                sample = get_sample_data("movie")
                preview = render_template(template, sample)
                self.movie_preview_label.setText(f"{preview}.mkv")
                self.movie_validation_label.setText("")
                self.movie_validation_label.setStyleSheet("")
            except Exception as e:
                self.movie_preview_label.setText("(error)")
                self.movie_validation_label.setText(str(e))
                self.movie_validation_label.setStyleSheet(f"color: {COLORS['error']};")
        else:
            self.movie_preview_label.setText("(invalid)")
            self.movie_validation_label.setText(error)
            self.movie_validation_label.setStyleSheet(f"color: {COLORS['error']};")

    def _reset_defaults(self):
        """Reset to default templates."""
        self.series_preset_combo.setCurrentText("Standard")
        self.series_template_edit.setText(DEFAULT_SERIES_TEMPLATE)

        self.movie_preset_combo.setCurrentText("Standard")
        self.movie_template_edit.setText(DEFAULT_MOVIE_TEMPLATE)

        self._update_previews()

    def _save_and_close(self):
        """Validate, save settings and close."""
        series_template = self.series_template_edit.text()
        movie_template = self.movie_template_edit.text()

        # Validate
        is_valid, error = validate_template(series_template, "series")
        if not is_valid:
            QMessageBox.warning(
                self,
                "Invalid Series Template",
                f"The series template is invalid:\n{error}"
            )
            return

        is_valid, error = validate_template(movie_template, "movie")
        if not is_valid:
            QMessageBox.warning(
                self,
                "Invalid Movie Template",
                f"The movie template is invalid:\n{error}"
            )
            return

        # Save
        self.settings["series_template"] = series_template
        self.settings["movie_template"] = movie_template
        self.settings["series_preset"] = self.series_preset_combo.currentText()
        self.settings["movie_preset"] = self.movie_preset_combo.currentText()

        if save_settings(self.settings):
            self.settings_changed.emit()
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Save Error",
                "Could not save settings to file."
            )
