# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os
import shutil

project_dir = Path(SPECPATH)
ffmpeg = os.environ.get("AKIS_FFMPEG") or shutil.which("ffmpeg")
if not ffmpeg or not Path(ffmpeg).is_file():
    raise SystemExit("FFmpeg bulunamadı: PATH veya AKIS_FFMPEG ayarlayın.")

a = Analysis(
    [str(project_dir / "main.py")],
    pathex=[str(project_dir)],
    binaries=[(ffmpeg, ".")],
    datas=[(str(project_dir / "app.ico"), ".")],
    hiddenimports=[
        "keyring.backends.Windows",
        "openai",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AkisKurguAI",
    icon=str(project_dir / "app.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AkisKurguAI",
)

