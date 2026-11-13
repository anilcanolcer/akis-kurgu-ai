"""Offline speech synthesis with the voices installed in Windows.

The Windows speech API (WinRT) is used directly: it has the modern voices, Turkish ones included, and
runs in this process. The older System.Speech route through a hidden PowerShell sees only the classic
desktop voices (often English only) and is kept as a last resort for systems where the WinRT packages
cannot be loaded.
"""
import asyncio
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


def _winrt():
    """The WinRT speech classes, or None when they cannot be loaded."""
    try:
        from winrt.windows.media.speechsynthesis import SpeechSynthesizer
        from winrt.windows.storage.streams import DataReader
    except Exception:
        return None
    return SpeechSynthesizer, DataReader


def voices():
    """[(voice id, shown name, language)] of the installed voices; [] when none can be listed."""
    classes = _winrt()
    if classes is None:
        return []
    try:
        return [(voice.id, voice.display_name, voice.language) for voice in classes[0].all_voices]
    except Exception:
        return []


def pick_voice(available, voice_id=None, language='tr'):
    """The id to use: the asked one when installed, else the first voice of `language`, else None."""
    ids = [item[0] for item in available]
    if voice_id in ids:
        return voice_id
    prefix = (language or '').lower().split('-')[0]
    return next((vid for vid, _, lang in available if prefix and lang.lower().startswith(prefix)), None)


def _synthesize_winrt(classes, text, destination, voice_id):
    synthesizer_class, reader_class = classes

    async def run():
        synthesizer = synthesizer_class()
        if voice_id:
            synthesizer.voice = next(v for v in synthesizer_class.all_voices if v.id == voice_id)
        stream = await synthesizer.synthesize_text_to_stream_async(text)
        size = stream.size
        reader = reader_class(stream.get_input_stream_at(0))
        await reader.load_async(size)
        data = bytearray(size)
        reader.read_bytes(data)
        return bytes(data)

    data = asyncio.run(run())
    if len(data) < 64 or data[:4] != b'RIFF':
        raise RuntimeError('Windows ses üretimi boş sonuç verdi.')
    Path(destination).write_bytes(data)
    return str(destination)


def synthesize(text, destination, runner=subprocess.run, *, voice_id=None, language='tr'):
    """Speak `text` into a WAV file at `destination`; returns its path."""
    if sys.platform != 'win32':
        raise RuntimeError('Yerel sistem sesi yalnızca Windows üzerinde kullanılabilir.')
    if not text.strip():
        raise ValueError('Konuşma metni boş olamaz.')
    classes = _winrt() if runner is subprocess.run else None   # an injected runner means the PowerShell route
    if classes is not None:
        return _synthesize_winrt(classes, text, destination, pick_voice(voices(), voice_id, language))
    payload = base64.b64encode(json.dumps({'text': text, 'path': str(Path(destination).resolve())}, ensure_ascii=False).encode('utf-8')).decode('ascii')
    result = runner(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', _SCRIPT], input=payload, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode != 0 or not Path(destination).is_file():
        raise RuntimeError('Windows ses üretimi başarısız: ' + result.stderr[-1000:])
    return str(destination)
