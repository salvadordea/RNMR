"""Headless GUI smoke test.

Uses ``skip_setup=True`` so the first-run setup wizard (a blocking modal)
does not hang an automated run.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402


def test_main_window_constructs_headless():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(skip_setup=True)
    assert window is not None
    window.close()
