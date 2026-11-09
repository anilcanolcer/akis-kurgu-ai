"""Diagnostic exercised in the built package with a small downloaded model."""
import tempfile
import wave
from pathlib import Path
from ai_service import local_transcribe

def diagnose():
    with tempfile.TemporaryDirectory() as folder:
        audio = Path(folder) / 'silence.wav'
        with wave.open(str(audio), 'wb') as stream:
            stream.setparams((1, 2, 16000, 16000, 'NONE', 'not compressed'))
            stream.writeframes(b'\0\0' * 16000)
        first = local_transcribe(audio, 'tiny', download=True, timed=True)
        second = local_transcribe(audio, 'tiny', download=False, timed=True)
        return {'status': 'passed', 'online_segments': len(first), 'offline_segments': len(second)}
