# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os
import shutil
from PyInstaller.utils.hooks import collect_all

extra_datas, extra_binaries, extra_hidden = [], [], []
for module in ("faster_whisper", "ctranslate2", "av", "onnxruntime", "tokenizers", "huggingface_hub"):
    data, binaries, hidden = collect_all(module)
    extra_datas += data
    extra_binaries += binaries
    extra_hidden += hidden

project_dir = Path(SPECPATH)

# Version resource: security products score executables without publisher/version details as anonymous.
import re
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)
app_version = re.search(r"__version__\s*=\s*'([^']+)'", (project_dir / "akis" / "__init__.py").read_text(encoding="utf-8")).group(1)
numbers = tuple(int(part) for part in app_version.split(".")) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Anılcan Ölçer"),
            StringStruct("FileDescription", "Akış Kurgu AI"),
            StringStruct("FileVersion", app_version),
            StringStruct("InternalName", "AkisKurguAI"),
            StringStruct("LegalCopyright", "© Anılcan Ölçer"),
            StringStruct("OriginalFilename", "AkisKurguAI.exe"),
            StringStruct("ProductName", "Akış Kurgu AI"),
            StringStruct("ProductVersion", app_version),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)
ffmpeg = os.environ.get("AKIS_FFMPEG") or shutil.which("ffmpeg")
if not ffmpeg or not Path(ffmpeg).is_file():
    raise SystemExit("FFmpeg bulunamadı: PATH veya AKIS_FFMPEG ayarlayın.")

# FFmpeg's licence travels with it (the gyan.dev build keeps LICENSE beside its bin folder), and the
# notice naming every bundled third-party program goes into _internal with it.
licence_datas = [(str(project_dir / "THIRD_PARTY_NOTICES.txt"), ".")]
ffmpeg_licence = Path(ffmpeg).resolve().parent.parent / "LICENSE"
if ffmpeg_licence.is_file():
    licence_datas.append((str(ffmpeg_licence), "licenses/ffmpeg"))

a = Analysis(
    [str(project_dir / "main.py")],
    pathex=[str(project_dir)],
    binaries=[(ffmpeg, ".")] + extra_binaries,
    datas=[(str(project_dir / "app.ico"), ".")] + licence_datas + extra_datas,
    hiddenimports=[
        "keyring.backends.Windows",
        "openai",
        # Voiceovers through the Windows speech API (akis.tts_service imports these lazily).
        "winrt.windows.media.speechsynthesis",
        "winrt.windows.storage.streams",
        "winrt.windows.foundation",
        "winrt.windows.foundation.collections",
    ] + extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
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
    version=version_info,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name="AkisKurguAI",
)

