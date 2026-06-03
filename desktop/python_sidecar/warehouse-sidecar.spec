# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata


SPEC_DIR = Path(SPECPATH)
PROJECT_ROOT = SPEC_DIR.parents[1]

datas = []
binaries = []
hiddenimports = []

for package_name in ("django", "openpyxl", "waitress"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package_name)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

hiddenimports += collect_submodules("warehouse_app")
hiddenimports += collect_submodules("config")
hiddenimports += [
    "config.settings",
    "config.urls",
    "config.wsgi",
    "warehouse_app",
    "warehouse_app.apps",
    "warehouse_app.context_processors",
    "warehouse_app.urls",
    "warehouse_app.views",
    "warehouse_app.forms",
    "warehouse_app.services",
    "warehouse_app.models",
    "warehouse_app.admin",
    "warehouse_app.demo",
    "warehouse_app.migrations",
    "warehouse_app.migrations.0001_initial",
    "warehouse_app.migrations.0002_unit_display_precision",
    "warehouse_app.templatetags.warehouse_tags",
]

datas += copy_metadata("Django")
datas += copy_metadata("openpyxl")
datas += [
    (str(PROJECT_ROOT / "templates"), "templates"),
    (str(PROJECT_ROOT / "static"), "static"),
]


a = Analysis(
    [str(PROJECT_ROOT / "desktop" / "python_sidecar" / "serve.py")],
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
    name="warehouse-sidecar",
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
    name="warehouse-sidecar",
)
