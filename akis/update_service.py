"""Safe GitHub release checks, verified installer downloads and the install hand-over.

Flow: check_update() reads the release metadata only. The caller asks the user, then download()
fetches the installer into one fixed folder (update_dir) as `<name>.part`, verifies its SHA-256 and
only then renames it into place; nothing in the install folder is touched until then. Before the
install the caller checks free space (space_shortfall / required_install_space). launch_installer()
verifies the hash again and starts the installer directly in its visible /UPDATE mode: no helper
process and no PowerShell, which security products treat as an attack pattern.

The installer itself waits for the app to exit, moves the old AkisKurguAI.exe and _internal aside
(`.old`), extracts the new files, rolls back on any error (exit codes in INSTALLER_EXIT_CODES),
tells the user in Turkish when it failed and restarts the app, new or old.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from akis import __version__

VERSION = __version__
API = 'https://api.github.com/repos/anilcanolcer/akis-kurgu-ai/releases/latest'
ASSET = 'AkisKurguAI-Setup.exe'
# The API allows 60 anonymous requests an hour per IP address, shared by everyone behind one router or
# mobile carrier. When it refuses, the same facts are read from pages that have no such limit: the
# "latest release" redirect gives the version, and a small checksum file published with every release
# gives the installer's SHA-256.
LATEST_PAGE = 'https://github.com/anilcanolcer/akis-kurgu-ai/releases/latest'
TAG_PAGE = 'https://github.com/anilcanolcer/akis-kurgu-ai/releases/tag/'
CHECKSUM_ASSET = ASSET + '.sha256'
API_REFUSED = (403, 429)
CHECK_TIMEOUT = 15
DOWNLOAD_PREFIX = 'https://github.com/anilcanolcer/akis-kurgu-ai/releases/download/'
INSTALLER_PREFIX = 'AkisKurguAI-Setup-'
INSTALL_LOG = 'install.log'
LEGACY_TEMP_PREFIX = 'akis_update_'  # versions up to 0.4.2 downloaded into a new mkdtemp per launch
CHUNK_SIZE = 256 * 1024
READ_TIMEOUT = 20  # seconds per socket operation; bounds how long a stalled download ignores cancellation
VERIFY_FAILED = ('Güncelleme dosyasının SHA-256 doğrulaması başarısız; dosya indirildikten sonra değişmiş '
                 'olabilir. Kurulum başlatılmadı, güncellemeyi yeniden indirin.')
APP_EXE = 'AkisKurguAI.exe'
APP_LIBS = '_internal'  # PyInstaller onedir: the install folder holds only APP_EXE and APP_LIBS
MIN_INSTALL_SPACE = 1024 ** 3
DOWNLOAD_SPACE_MARGIN = 64 * 1024 ** 2
INSTALL_LOG_LIMIT = 1024 ** 2  # the installer and helper append; a log past this size is started afresh
# Exit codes of installer.nsi besides 0; the helper shows the matching text.
INSTALLER_EXIT_CODES = {
    1: 'Kurulum iptal edildi; önceki sürüm değişmedi.',
    2: 'Kurulum yarıda kesildi.',
    10: 'Uygulama dosyaları kullanımda olduğu için hiçbir dosya değiştirilmedi.',
    11: 'Yeni dosyalar yazılamadı (disk dolu olabilir); önceki sürüm geri yüklendi.',
    12: 'Yeni dosyalar yazılamadı ve önceki sürüm otomatik olarak geri yüklenemedi.',
    13: 'Kurulumun son adımı başarısız oldu; önceki sürüm geri yüklendi.',
    14: 'Yarım kalmış önceki bir güncelleme onarılamadı.',
}


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


def check_update(current=VERSION, opener=None):
    """The newer release as a dict (version, url, sha256, size), or None when this version is current."""
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(API, headers={'User-Agent': 'AkisKurguAI', 'Accept': 'application/vnd.github+json'})
    try:
        with opener(request, timeout=CHECK_TIMEOUT) as response:
            return find_update(json.load(response), current)
    except urllib.error.HTTPError as exc:
        if exc.code not in API_REFUSED and exc.code < 500:
            raise
    return check_update_without_api(current, opener)


def check_update_without_api(current=VERSION, opener=None):
    """check_update() from the release pages instead of the rate-limited API."""
    opener = opener or urllib.request.urlopen
    headers = {'User-Agent': 'AkisKurguAI', 'Accept': '*/*'}  # without Accept GitHub answers 404 for the checksum file
    with opener(urllib.request.Request(LATEST_PAGE, headers=headers, method='HEAD'), timeout=CHECK_TIMEOUT) as response:
        landed = response.geturl()
    # Only this repository's own release page is believed; anything else is not a version.
    tag = landed[len(TAG_PAGE):] if landed.startswith(TAG_PAGE) else ''
    version = version_tuple(tag)
    if version is None:
        raise ValueError('En son sürüm okunamadı.')
    if version <= version_tuple(current):
        return None
    try:
        with opener(urllib.request.Request(f'{DOWNLOAD_PREFIX}{tag}/{CHECKSUM_ASSET}', headers=headers),
                    timeout=CHECK_TIMEOUT) as response:
            listed = response.read(4096).decode('ascii', 'replace')
    except urllib.error.HTTPError as exc:
        raise ValueError('Sürüm için doğrulanabilir kurucu bulunamadı.') from exc
    match = re.match(r'\s*([0-9a-fA-F]{64})(?![0-9a-fA-F])', listed)
    if not match:
        raise ValueError('Sürüm için doğrulanabilir kurucu bulunamadı.')
    return {'version': tag, 'url': f'{DOWNLOAD_PREFIX}{tag}/{ASSET}', 'sha256': match.group(1).lower(), 'size': None}


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
        if name == keep_name:
            continue
        if name == INSTALL_LOG:
            try:
                if entry.stat().st_size <= INSTALL_LOG_LIMIT:
                    continue
            except OSError:
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


def folder_size(path):
    """Total bytes of the files under `path` (or of `path` itself); 0 when it cannot be read. Never raises."""
    path = Path(path)
    try:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.lstat(os.path.join(root, name)).st_size
                except OSError:
                    continue
        return total
    except OSError:
        return 0


def install_size(directory):
    """Bytes taken by the installed application (its exe and _internal folder) in `directory`."""
    directory = Path(directory)
    return folder_size(directory / APP_EXE) + folder_size(directory / APP_LIBS)


def required_install_space(directory):
    """Free bytes the install drive needs for an update.

    The old copy is only renamed aside (no extra space on the same drive), so the new files are what
    needs room: about the current install size. Half again on top covers a larger new version, the
    installer's own temporary files and file-system slack; 1 GiB is the floor when the current size is
    small or unreadable (a typical install is ~0.5 GB).
    """
    return max(int(install_size(directory) * 1.5), MIN_INSTALL_SPACE)


def free_space(path, usage=shutil.disk_usage):
    """Free bytes on the drive of `path` (its nearest existing parent), or None when unknown."""
    path = Path(path)
    for candidate in (path, *path.parents):
        try:
            if candidate.exists():
                return usage(candidate).free
        except OSError:
            return None
    return None


def space_shortfall(path, needed, usage=shutil.disk_usage):
    """(needed, free) when the drive of `path` has less than `needed` bytes free, else None (also when unknown)."""
    free = free_space(path, usage)
    if free is None or free >= needed:
        return None
    return needed, free


def download_space_needed(update):
    return (update.get('size') or 200 * 1024 ** 2) + DOWNLOAD_SPACE_MARGIN


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


UAC_DECLINED = 'Kurulum için izin verilmedi; güncelleme kurulmadı.'
SE_ERR_ACCESSDENIED = 5  # ShellExecute's answer when the UAC prompt is declined


def installer_arguments(app, log):
    """The installer's update mode: it waits for the app to exit, swaps the files with rollback, shows its
    own progress window and restarts the app. No helper process is involved."""
    return f'/UPDATE /DIR="{Path(app).parent}" /LOG="{log}"'


def _shell_execute(path, arguments, directory):
    """Start a program through the shell (UAC is raised by the installer's own manifest). > 32 means started."""
    import ctypes
    return int(ctypes.windll.shell32.ShellExecuteW(None, 'open', str(path), arguments, str(directory), 1))


def launch_installer(installer, app, pid=None, *, sha256, start=None):
    """Verify the downloaded installer once more and start it in update mode.

    Raises PermissionError when the user declined the elevation prompt and OSError when the installer could
    not be started; in both cases nothing was changed and the application must keep running. `pid` is unused
    (the installer waits for the application's files itself) and kept for older callers.
    """
    if not re.fullmatch(r'[0-9a-fA-F]{64}', str(sha256 or '')):
        raise ValueError('Güncelleme dosyasının beklenen SHA-256 değeri geçersiz.')
    installer_path_ = Path(installer).resolve()
    app_path = Path(app).resolve()
    if not installer_path_.is_file() or not app_path.is_file():
        raise ValueError('Güncelleme dosyası veya uygulama yolu bulunamadı.')
    if not matches(installer_path_, sha256):
        raise ValueError(VERIFY_FAILED)
    arguments = installer_arguments(app_path, installer_path_.parent / INSTALL_LOG)
    code = (start or _shell_execute)(installer_path_, arguments, installer_path_.parent)
    if code <= 32:
        if code == SE_ERR_ACCESSDENIED:
            raise PermissionError(UAC_DECLINED)
        raise OSError(f'Kurulum başlatılamadı (kod {code}).')
    return code
