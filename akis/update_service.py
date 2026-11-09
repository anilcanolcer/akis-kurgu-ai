"""Safe GitHub release checks and verified installer downloads."""
import hashlib
import json
import re
import urllib.request
from pathlib import Path

VERSION = '0.3.1'
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
