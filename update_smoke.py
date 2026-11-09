"""Windows CI smoke test: update an installed copy using the real installer."""
import subprocess
import sys
import time
from pathlib import Path
from akis.update_service import launch_installer

installer, directory = map(Path, sys.argv[1:])
app = directory / 'AkisKurguAI.exe'
parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'])
try:
    helper = launch_installer(installer, app, parent.pid)
    code = helper.wait(timeout=600)
    if code:
        raise RuntimeError(f'Update helper failed: {code}')
    if not (installer.parent / 'install.log').is_file():
        raise RuntimeError('Installer log missing')
finally:
    parent.wait(timeout=10)
