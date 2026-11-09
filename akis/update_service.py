"""Safe GitHub release checks and verified installer downloads."""
import hashlib
import json
import re
import urllib.request
from pathlib import Path

VERSION = '0.3.5'
API = 'https://api.github.com/repos/anilcanolcer/akis-kurgu-ai/releases/latest'
ASSET = 'AkisKurguAI-Setup.exe'

def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value)
    return tuple(map(int, match.groups())) if match else None

def find_update(data, current=VERSION):
    version = version_tuple(data.get('tag_name', ''))
    if data.get('draft') or data.get('prerelease') or version is None or version <= version_tuple(current):
        return None
    for asset in data.get('assets', []):
        url, digest = asset.get('browser_download_url', ''), asset.get('digest', '')
        if (asset.get('name') == ASSET and url.startswith('https://github.com/anilcanolcer/akis-kurgu-ai/releases/download/')
                and re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest)):
            return {'version': data['tag_name'], 'url': url, 'sha256': digest[7:].lower()}
    raise ValueError('Sürüm için doğrulanabilir kurucu bulunamadı.')

def check_update():
    request = urllib.request.Request(API, headers={'User-Agent': 'AkisKurguAI', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return find_update(json.load(response))

def download(update, destination):
    request = urllib.request.Request(update['url'], headers={'User-Agent': 'AkisKurguAI'})
    digest = hashlib.sha256()
    target = Path(destination)
    try:
        with urllib.request.urlopen(request, timeout=30) as response, target.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk); output.write(chunk)
        if digest.hexdigest() != update['sha256']:
            raise ValueError('Güncelleme dosyasının doğrulaması başarısız.')
        return str(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def launch_installer(installer, app, pid, *, popen=None):
    """Run the verified installer after the application exits; report failures visibly."""
    import base64
    import os
    import subprocess
    if popen is None:
        popen = subprocess.Popen
    installer_path = Path(installer).resolve()
    app_path = Path(app).resolve()
    if not installer_path.is_file() or not app_path.is_file() or int(pid) <= 0:
        raise ValueError('Güncelleme dosyası veya uygulama yolu bulunamadı.')
    payload = base64.b64encode(json.dumps({
        'pid': int(pid), 'installer': str(installer_path), 'app': str(app_path),
        'directory': str(app_path.parent), 'log': str(installer_path.parent / 'install.log'),
    }, ensure_ascii=False).encode('utf-8')).decode('ascii')
    script = r'''
$ErrorActionPreference = 'Stop'
$d = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PAYLOAD')) | ConvertFrom-Json
try {
    Wait-Process -Id $d.pid -ErrorAction SilentlyContinue
    $arguments = @('/VERYSILENT', '/NORESTART', '/SP-', ('/DIR="' + $d.directory + '"'), ('/LOG="' + $d.log + '"'))
    $protected = @($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ -and ($d.directory.Equals($_, [StringComparison]::OrdinalIgnoreCase) -or $d.directory.StartsWith($_ + '\', [StringComparison]::OrdinalIgnoreCase)) }
    if ($protected) {
        $p = Start-Process -FilePath $d.installer -ArgumentList $arguments -Verb RunAs -Wait -PassThru
    } else {
        $p = Start-Process -FilePath $d.installer -ArgumentList $arguments -Wait -PassThru
    }
    if ($p.ExitCode -ne 0) { throw ("Kurucu hata kodu: " + $p.ExitCode) }
    Start-Process -FilePath $d.app
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(("Güncelleme tamamlanamadı: " + $_.Exception.Message + "`nKayıt: " + $d.log + "`nİndirilen Setup dosyasını elle çalıştırabilirsiniz: " + $d.installer), 'Akış Kurgu AI') | Out-Null
    if (Test-Path -LiteralPath $d.app) { Start-Process -FilePath $d.app -ErrorAction SilentlyContinue }
    exit 1
}
'''.replace('PAYLOAD', payload)
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    return popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
