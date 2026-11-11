"""Windows CI smoke test: update an installed copy with the real installer, the way the app does it.

Usage: python update_smoke.py <installer> <installed folder>
The installer runs in its update mode (/UPDATE): it waits for the app's files, swaps them with rollback,
writes the log line and restarts the app. /S keeps it unattended on the runner.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from akis.update_service import INSTALL_LOG, installer_arguments, matches, sha256_file

installer, directory = map(Path, sys.argv[1:])
app = directory / 'AkisKurguAI.exe'
if not app.is_file():
    raise SystemExit(f'Installed application not found: {app}')
with tempfile.TemporaryDirectory(prefix='akis-update-smoke-') as folder:
    copy = Path(folder) / installer.name  # the app runs a downloaded copy, never the build artifact itself
    shutil.copy2(installer, copy)
    if not matches(copy, sha256_file(installer)):
        raise SystemExit('Installer copy does not match its SHA-256')
    log = Path(folder) / INSTALL_LOG
    command = f'"{copy}" /S {installer_arguments(app, log)}'
    code = subprocess.run(command, timeout=900).returncode
    text = log.read_text(encoding='utf-8', errors='replace') if log.is_file() else ''
    print(text)
    if code != 0:
        raise SystemExit(f'Installer failed with exit code {code}')
    if 'NSIS installation completed.' not in text:
        raise SystemExit('Installer log has no completion line')
    if not app.is_file() or (directory / '_internal.old').exists() or Path(str(app) + '.old').exists():
        raise SystemExit('Installed copy is incomplete or .old copies were left behind')
print('update smoke test passed')
