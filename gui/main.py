#!/usr/bin/env python3
"""
RNMR GUI - Media File Renamer

Entry point for the graphical user interface.
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from gui.main_window import MainWindow
from gui.theme import DARK_STYLESHEET
from gui.settings import SettingsManager
from gui.i18n import i18n
from renamer.runtime import resource_path


def main():
    """Main entry point."""
    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    mgr = SettingsManager()
    i18n.set_language(app, mgr.get("app_language", "en"))

    # Application icon (window + taskbar)
    icon_path = resource_path("resources/rnmr.png")
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Apply dark theme
    app.setStyleSheet(DARK_STYLESHEET)

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
