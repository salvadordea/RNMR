# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for RNMR - Media File Renamer.

Usage:
    pyinstaller app.spec

Output:
    dist/RNMR.exe

Notes:
    - Place ffprobe.exe in resources/ before building to bundle it.
    - If resources/ffprobe.exe is absent the build still succeeds;
      ffprobe features will fall back to PATH lookup at runtime.
"""

import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SPEC_DIR = os.path.abspath(SPECPATH)
RESOURCES_DIR = os.path.join(SPEC_DIR, "resources")

# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------

datas = []

# Bundle the resources directory (icons, etc.)
if os.path.isdir(RESOURCES_DIR):
    datas.append((RESOURCES_DIR, "resources"))

# Bundle LICENSE_FFMPEG.txt alongside the executable (if present)
_license_ffmpeg = os.path.join(SPEC_DIR, "LICENSE_FFMPEG.txt")
if os.path.isfile(_license_ffmpeg):
    datas.append((_license_ffmpeg, "."))

# ---------------------------------------------------------------------------
# Binaries
# ---------------------------------------------------------------------------

binaries = []

# Bundle ffprobe.exe as a binary in resources/ (if present)
_ffprobe = os.path.join(RESOURCES_DIR, "ffprobe.exe")
if os.path.isfile(_ffprobe):
    binaries.append((_ffprobe, "resources"))

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------

hiddenimports = [
    # Keep Qt modules explicit to avoid pulling in the entire Qt stack.
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    # Third-party
    "requests",
    "urllib3",
    "charset_normalizer",
    "certifi",
    "idna",
    "dotenv",
]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ["gui/main.py"],
    pathex=[SPEC_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "test",
        "xmlrpc",
        "pydoc",
    ],
    noarchive=False,
)

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RNMR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed mode -- no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(RESOURCES_DIR, "rnmr.ico"),
)
