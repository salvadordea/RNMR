"""Dark theme stylesheet for RNMR GUI."""

# Color palette
COLORS = {
    "background": "#121212",
    "panel": "#1E1E1E",
    "panel_light": "#252525",
    "border": "#2C2C2C",
    "border_light": "#3C3C3C",
    "accent": "#3A82F7",
    "accent_hover": "#4A92FF",
    "accent_pressed": "#2A72E7",
    "text": "#EAEAEA",
    "text_muted": "#9AA0A6",
    "text_disabled": "#666666",
    "success": "#4CAF50",
    "warning": "#FF9800",
    "error": "#F44336",
    "selection": "rgba(58, 130, 247, 0.3)",
}

DARK_STYLESHEET = f"""
/* Main Window */
QMainWindow {{
    background-color: {COLORS["background"]};
}}

QWidget {{
    background-color: {COLORS["background"]};
    color: {COLORS["text"]};
    font-family: "Segoe UI", "SF Pro Display", "Arial", sans-serif;
    font-size: 13pt;
}}

/* Group Boxes */
QGroupBox {{
    background-color: {COLORS["panel"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
    padding-top: 24px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 8px;
    color: {COLORS["text_muted"]};
    font-weight: 500;
}}

/* Buttons */
QPushButton {{
    background-color: {COLORS["panel_light"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border_light"]};
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: {COLORS["border_light"]};
    border-color: {COLORS["accent"]};
}}

QPushButton:pressed {{
    background-color: {COLORS["border"]};
}}

QPushButton:disabled {{
    background-color: {COLORS["panel"]};
    color: {COLORS["text_disabled"]};
    border-color: {COLORS["border"]};
}}

QPushButton#primaryButton {{
    background-color: {COLORS["accent"]};
    border-color: {COLORS["accent"]};
    color: white;
}}

QPushButton#primaryButton:hover {{
    background-color: {COLORS["accent_hover"]};
    border-color: {COLORS["accent_hover"]};
}}

QPushButton#primaryButton:pressed {{
    background-color: {COLORS["accent_pressed"]};
}}

QPushButton#primaryButton:disabled {{
    background-color: {COLORS["border"]};
    border-color: {COLORS["border"]};
    color: {COLORS["text_disabled"]};
}}

/* Line Edit */
QLineEdit {{
    background-color: {COLORS["panel"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: {COLORS["accent"]};
}}

QLineEdit:focus {{
    border-color: {COLORS["accent"]};
}}

QLineEdit:disabled {{
    background-color: {COLORS["background"]};
    color: {COLORS["text_disabled"]};
}}

/* Checkboxes */
QCheckBox {{
    spacing: 8px;
    color: {COLORS["text"]};
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid {COLORS["border_light"]};
    background-color: {COLORS["panel"]};
}}

QCheckBox::indicator:hover {{
    border-color: {COLORS["accent"]};
}}

QCheckBox::indicator:checked {{
    background-color: {COLORS["accent"]};
    border-color: {COLORS["accent"]};
}}

QCheckBox::indicator:checked:hover {{
    background-color: {COLORS["accent_hover"]};
    border-color: {COLORS["accent_hover"]};
}}

QCheckBox:disabled {{
    color: {COLORS["text_disabled"]};
}}

/* Table Widget */
QTableWidget {{
    background-color: {COLORS["panel"]};
    alternate-background-color: {COLORS["panel_light"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    gridline-color: {COLORS["border"]};
    selection-background-color: {COLORS["selection"]};
}}

QTableWidget::item {{
    padding: 8px;
    border: none;
}}

QTableWidget::item:selected {{
    background-color: {COLORS["selection"]};
    color: {COLORS["text"]};
}}

QTableWidget::item:hover {{
    background-color: rgba(255, 255, 255, 0.05);
}}

QHeaderView::section {{
    background-color: {COLORS["panel"]};
    color: {COLORS["text_muted"]};
    padding: 10px 8px;
    border: none;
    border-bottom: 1px solid {COLORS["border"]};
    font-weight: 600;
}}

QHeaderView::section:hover {{
    background-color: {COLORS["panel_light"]};
}}

/* Scrollbars */
QScrollBar:vertical {{
    background-color: {COLORS["panel"]};
    width: 12px;
    border-radius: 6px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {COLORS["border_light"]};
    border-radius: 6px;
    min-height: 30px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {COLORS["text_muted"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background-color: {COLORS["panel"]};
    height: 12px;
    border-radius: 6px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background-color: {COLORS["border_light"]};
    border-radius: 6px;
    min-width: 30px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {COLORS["text_muted"]};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* Progress Bar */
QProgressBar {{
    background-color: {COLORS["panel"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {COLORS["accent"]};
    border-radius: 5px;
}}

/* Text Edit (Log Panel) */
QTextEdit {{
    background-color: {COLORS["panel"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12pt;
}}

/* Tool Button (Collapse) */
QToolButton {{
    background-color: transparent;
    color: {COLORS["text_muted"]};
    border: none;
    padding: 4px;
}}

QToolButton:hover {{
    color: {COLORS["text"]};
}}

/* Labels */
QLabel {{
    color: {COLORS["text"]};
}}

QLabel#mutedLabel {{
    color: {COLORS["text_muted"]};
}}

QLabel#statusLabel {{
    font-weight: 500;
}}

/* Dialog */
QDialog {{
    background-color: {COLORS["background"]};
}}

QMessageBox {{
    background-color: {COLORS["background"]};
}}

QMessageBox QLabel {{
    color: {COLORS["text"]};
}}

/* Tooltips */
QToolTip {{
    background-color: {COLORS["panel_light"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
    padding: 6px 10px;
}}
"""
