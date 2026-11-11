"""Safe GitHub release checks and verified installer downloads.

Flow: check_update() reads the release metadata only. The caller asks the user, then download()
fetches the installer into one fixed folder (update_dir) as `<name>.part`, verifies its SHA-256 and
only then renames it into place. launch_installer() verifies the hash again right before spawning the
helper, and the PowerShell helper verifies it once more right before Start-Process, holding the file
open without write/delete sharing so it cannot be swapped between that check and the launch.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.request
from pathlib import Path
from akis import __version__

VERSION = __version__
API = 'https://api.github.com/repos/anilcanolcer/akis-kurgu-ai/releases/latest'
ASSET = 'AkisKurguAI-Setup.exe'
DOWNLOAD_PREFIX = 'https://github.com/anilcanolcer/akis-kurgu-ai/releases/download/'
INSTALLER_PREFIX = 'AkisKurguAI-Setup-'
INSTALL_LOG = 'install.log'
LEGACY_TEMP_PREFIX = 'akis_update_'  # versions up to 0.4.2 downloaded into a new mkdtemp per launch
CHUNK_SIZE = 256 * 1024
READ_TIMEOUT = 20  # seconds per socket operation; bounds how long a stalled download ignores cancellation
VERIFY_FAILED = ('Güncelleme dosyasının SHA-256 doğrulaması başarısız; dosya indirildikten sonra değişmiş '
                 'olabilir. Kurulum başlatılmadı, güncellemeyi yeniden indirin.')


class DownloadCancelled(Exception):
    """The download was interrupted on request; the partial file has been deleted."""


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value)
    return tuple(map(int, match.groups())) if match else None


def find_update(data, current=VERSION):
    version = version_tuple(data.get('tag_name', ''))
    if data.get('draft') or data.get('prerelease') or version is None or version <= version_tuple(current):
        return None
    for asset in data.get('assets', []):
        url, digest = asset.get('browser_download_url', ''), asset.get('digest', '')
        if (asset.get('name') == ASSET and url.startswith(DOWNLOAD_PREFIX)
                and re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest)):
            size = asset.get('size')
            return {'version': data['tag_name'], 'url': url, 'sha256': digest[7:].lower(),
                    'size': size if isinstance(size, int) and size > 0 else None}
    raise ValueError('Sürüm için doğrulanabilir kurucu bulunamadı.')


def check_update():
    request = urllib.request.Request(API, headers={'User-Agent': 'AkisKurguAI', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return find_update(json.load(response))


def update_dir(app_data):
    """The one folder installers are downloaded to, under the per-user app-data folder."""
    return Path(app_data) / 'updates'


def installer_path(folder, update):
    """Where the installer of `update` is stored: one file per version, never a fresh temp folder."""
    numbers = version_tuple(update['version'])
    if numbers is None:
        raise ValueError('Geçersiz sürüm numarası.')
    return Path(folder) / f"{INSTALLER_PREFIX}{'.'.join(map(str, numbers))}.exe"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def matches(path, expected):
    """Whether the file exists and its SHA-256 equals `expected` (hex, any case)."""
    try:
        return sha256_file(path).lower() == str(expected).lower()
    except OSError:
        return False


def cleanup_update_dir(folder, keep=None):
    """Delete every downloaded installer and partial download in `folder` except `keep`.

    The installer's own log is kept for diagnosis. Never raises; returns the names removed.
    """
    removed = []
    folder = Path(folder)
    keep_name = Path(keep).name.lower() if keep else None
    try:
        entries = list(folder.iterdir())
    except OSError:
        return removed
    for entry in entries:
        name = entry.name.lower()
        if name == keep_name or name == INSTALL_LOG:
            continue
        try:
            if entry.is_file() and not entry.is_symlink():
                entry.unlink()
                removed.append(entry.name)
        except OSError:
            continue  # e.g. an installer still running from an earlier update
    return removed


def cleanup_legacy_temp(root=None, *, now=None, max_age=24 * 3600):
    """Delete `akis_update_*` folders older versions left in %TEMP%, one per launch. Never raises."""
    removed = []
    try:
        root = Path(root or tempfile.gettempdir())
        now = time.time() if now is None else now
        entries = list(root.iterdir())
    except OSError:
        return removed
    for entry in entries:
        try:
            if (entry.name.startswith(LEGACY_TEMP_PREFIX) and entry.is_dir() and not entry.is_symlink()
                    and now - entry.stat().st_mtime >= max_age):
                shutil.rmtree(entry, ignore_errors=True)
                if not entry.exists():
                    removed.append(entry.name)
        except OSError:
            continue
    return removed


def download(update, destination, *, should_stop=None, progress=None, opener=None):
    """Download and verify the installer to `destination`; returns its path.

    should_stop(): polled between chunks; True raises DownloadCancelled. progress(done, total): total is 0
    when unknown. Data goes to `<destination>.part` and is renamed into place only after the SHA-256
    matched, so `destination` is either absent or a verified installer. A file already there that verifies
    is reused without downloading again.
    """
    target = Path(destination)
    if target.is_file():
        if matches(target, update['sha256']):
            return str(target)
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.part')
    request = urllib.request.Request(update['url'], headers={'User-Agent': 'AkisKurguAI'})
    digest = hashlib.sha256()
    try:
        with (opener or urllib.request.urlopen)(request, timeout=READ_TIMEOUT) as response, partial.open('wb') as output:
            try:
                total = int(response.headers.get('Content-Length') or 0)
            except (AttributeError, TypeError, ValueError):
                total = 0
            total = total or update.get('size') or 0
            done = 0
            while True:
                if should_stop is not None and should_stop():
                    raise DownloadCancelled('Güncelleme indirmesi iptal edildi.')
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
                output.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
        if digest.hexdigest() != update['sha256'].lower():
            raise ValueError('Güncelleme dosyasının doğrulaması başarısız.')
        os.replace(partial, target)
        return str(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def launch_installer(installer, app, pid, *, sha256, popen=None):
    """Run the verified installer after the application exits; report failures visibly.

    The SHA-256 is checked here immediately before spawning the helper, and again by the helper
    immediately before it starts the (possibly elevated) installer.
    """
    import base64
    import subprocess
    if popen is None:
        popen = subprocess.Popen
    if not re.fullmatch(r'[0-9a-fA-F]{64}', str(sha256 or '')):
        raise ValueError('Güncelleme dosyasının beklenen SHA-256 değeri geçersiz.')
    installer_path_ = Path(installer).resolve()
    app_path = Path(app).resolve()
    if not installer_path_.is_file() or not app_path.is_file() or int(pid) <= 0:
        raise ValueError('Güncelleme dosyası veya uygulama yolu bulunamadı.')
    if not matches(installer_path_, sha256):
        raise ValueError(VERIFY_FAILED)
    payload = base64.b64encode(json.dumps({
        'pid': int(pid), 'installer': str(installer_path_), 'app': str(app_path), 'sha256': sha256.lower(),
        'directory': str(app_path.parent), 'log': str(installer_path_.parent / INSTALL_LOG),
    }, ensure_ascii=False).encode('utf-8')).decode('ascii')
    script = r'''
$ErrorActionPreference = 'Stop'
$d = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PAYLOAD')) | ConvertFrom-Json
$verified = $false
$lock = $null
try {
    Wait-Process -Id $d.pid -ErrorAction SilentlyContinue
    # Verify right before running: the file stays open without write/delete sharing until the installer is done.
    $lock = [IO.File]::Open($d.installer, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $sha = [Security.Cryptography.SHA256]::Create()
    $actual = ([BitConverter]::ToString($sha.ComputeHash($lock))).Replace('-', '')
    if (-not $actual.Equals([string]$d.sha256, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'VERIFY_FAILED'
    }
    $verified = $true
    $arguments = @('/VERYSILENT', '/NORESTART', '/SP-', ('/DIR="' + $d.directory + '"'), ('/LOG="' + $d.log + '"'))
    $protected = @($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ -and ($d.directory.Equals($_, [StringComparison]::OrdinalIgnoreCase) -or $d.directory.StartsWith($_ + '\', [StringComparison]::OrdinalIgnoreCase)) }
    if ($protected) {
        $p = Start-Process -FilePath $d.installer -ArgumentList $arguments -Verb RunAs -Wait -PassThru
    } else {
        $p = Start-Process -FilePath $d.installer -ArgumentList $arguments -Wait -PassThru
    }
    $lock.Dispose(); $lock = $null
    if ($p.ExitCode -ne 0) { throw ("Kurucu hata kodu: " + $p.ExitCode) }
    Start-Process -FilePath $d.app
} catch {
    if ($lock) { $lock.Dispose(); $lock = $null }
    if ($verified) {
        $text = "Güncelleme tamamlanamadı: " + $_.Exception.Message + "`nKayıt: " + $d.log + "`nİndirilen Setup dosyasını elle çalıştırabilirsiniz: " + $d.installer
    } else {
        $text = "Güncelleme tamamlanamadı: " + $_.Exception.Message
        Remove-Item -LiteralPath $d.installer -Force -ErrorAction SilentlyContinue
    }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($text, 'Akış Kurgu AI') | Out-Null
    if (Test-Path -LiteralPath $d.app) { Start-Process -FilePath $d.app -ErrorAction SilentlyContinue }
    exit 1
}
'''.replace("'VERIFY_FAILED'", "'" + VERIFY_FAILED.replace("'", "''") + "'").replace('PAYLOAD', payload)
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    return popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
