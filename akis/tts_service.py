"""Offline speech synthesis via an installed Windows system voice."""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$data = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([Console]::In.ReadToEnd().Trim())) | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SetOutputToWaveFile($data.path)
    $speaker.Speak($data.text)
} finally { $speaker.Dispose() }
'''

def synthesize(text, destination, runner=subprocess.run):
    if sys.platform != 'win32':
        raise RuntimeError('Yerel sistem sesi yalnızca Windows üzerinde kullanılabilir.')
    if not text.strip():
        raise ValueError('Konuşma metni boş olamaz.')
    payload = base64.b64encode(json.dumps({'text': text, 'path': str(Path(destination).resolve())}, ensure_ascii=False).encode('utf-8')).decode('ascii')
    result = runner(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', _SCRIPT], input=payload, capture_output=True, text=True, timeout=300, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode != 0 or not Path(destination).is_file():
        raise RuntimeError('Windows ses üretimi başarısız: ' + result.stderr[-1000:])
    return str(destination)
