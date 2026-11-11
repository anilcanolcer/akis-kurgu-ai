"""Generate an NSIS uninstall list that never deletes unowned user files.

Also checks the PyInstaller onedir layout installer.nsi relies on: the application folder holds only
AkisKurguAI.exe and _internal (the installer swaps exactly these two during an update).
"""
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
if not root.is_dir() or not (root / 'AkisKurguAI.exe').is_file():
    raise SystemExit('Built application directory is missing')
if not (root / '_internal').is_dir():
    raise SystemExit('Built application has no _internal folder')
unexpected = sorted(p.name for p in root.iterdir() if p.name not in ('AkisKurguAI.exe', '_internal'))
if unexpected:
    raise SystemExit('Unexpected top-level entries the installer would not update: ' + ', '.join(unexpected))
def escape(path):
    return str(path).replace('/', '\\').replace('$', '$$')
files = sorted(p for p in root.rglob('*') if p.is_file())
directories = sorted((p for p in root.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True)
lines = [f'Delete "$INSTDIR\\{escape(p.relative_to(root))}"' for p in files]
lines += [f'RMDir "$INSTDIR\\{escape(p.relative_to(root))}"' for p in directories]
out.write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')
