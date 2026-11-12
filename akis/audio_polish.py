"""One-switch sound clean-up for the export and the playback proxy, done with ffmpeg's own filters.

Three independent options, all off by default:
    'level'    bring the finished mix to streaming loudness (-14 LUFS), so quiet footage is not quiet
    'denoise'  take hum and hiss off the video clips' own sound (speech); music is left alone
    'duck'     lower the music while someone speaks, let it come back when they stop

TimelineRenderer builds one label per sounding clip; this module turns those labels into the mix.
With no option on, the result is exactly the mix the renderer made before these options existed.
"""
OPTIONS = ('level', 'denoise', 'duck')

# Single-pass loudnorm works at 192 kHz internally and would hand that rate to the encoder.
LEVEL = 'loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000'
# Mild on purpose: a rumble filter and 10 dB of broadband reduction. Stronger settings make speech metallic.
DENOISE = 'highpass=f=80,afftdn=nr=10:nf=-45'
# Speech above about -30 dB pulls the music down 8:1; quick to duck, half a second to return.
DUCK = 'sidechaincompress=threshold=0.03:ratio=8:attack=20:release=500'


def clean(options):
    """The valid options as a sorted tuple (a stable value for signatures and project files)."""
    unknown = set(options or ()) - set(OPTIONS)
    if unknown:
        raise ValueError(f'Unknown audio option: {sorted(unknown)[0]}')
    return tuple(sorted(set(options or ())))


def voice_filter(options):
    """Filter text (with its trailing comma) put into each video clip's own audio chain, or ''."""
    return f'{DENOISE},' if 'denoise' in options else ''


def _sum(labels, out):
    """One graph line that mixes the labels at full level into [out]."""
    if len(labels) == 1:
        return f'{labels[0]}anull[{out}]'
    return f'{"".join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0[{out}]'


def mix(voices, music, options, limiter, tail=''):
    """Graph lines that mix the clip labels into [aout].

    voices: labels of the video clips' sound; music: labels of the audio-track clips.
    limiter: the peak limiter filter, used when more than one source is summed.
    tail: filter text appended last (the playback-speed change), with its leading comma.
    """
    labels = list(voices) + list(music)
    if not labels:
        return []
    post = (f',{LEVEL}' if 'level' in options else '') + (f',{limiter}' if len(labels) > 1 else '') + tail
    if 'duck' in options and voices and music:
        # The key copy is padded with silence: the compressor stops when its key ends, and the speech
        # usually ends before the music does.
        return [_sum(voices, 'voice'),
                '[voice]asplit[voicemain][voicekey]',
                '[voicekey]apad[voicepad]',
                _sum(music, 'music'),
                f'[music][voicepad]{DUCK}[ducked]',
                f'[voicemain][ducked]amix=inputs=2:duration=longest:normalize=0{post}[aout]']
    return [f'{"".join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0{post}[aout]']
