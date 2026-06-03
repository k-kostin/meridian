# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata


SPEC_DIR = Path(SPECPATH)
PROJECT_ROOT = SPEC_DIR.parents[1]
SIDECAR_DIR = Path(
    os.getenv(
        "WAREHOUSE_SIDECAR_DIST",
        PROJECT_ROOT / "dist" / "warehouse-sidecar",
    )
)
SIDECAR_BINARY = SIDECAR_DIR / "warehouse-sidecar.exe"

if not SIDECAR_BINARY.exists():
    raise SystemExit(
        "Sidecar build not found. Build desktop/python_sidecar/warehouse-sidecar.spec first "
        "or set WAREHOUSE_SIDECAR_DIST to the sidecar dist folder."
    )

datas = []
binaries = [(str(SIDECAR_BINARY), ".")]
hiddenimports = []

for package_name in ("webview",):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package_name)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

datas += copy_metadata("pywebview")


a = Analysis(
    [str(PROJECT_ROOT / "desktop" / "pywebview_shell" / "run_desktop.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="warehouse-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="warehouse-desktop",
)
