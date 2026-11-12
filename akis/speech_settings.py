"""Which language speech is recognised in, and which names and terms the recogniser should expect.

The editor window sets these once (set_current); every transcription path reads them as its defaults, so
the workers in between need no extra parameters. Turkish stays the default, as it always was.
"""
AUTO = 'auto'
# (code, name as shown, name used when a model is asked in Turkish to transcribe that language)
LANGUAGES = (('tr', 'Türkçe', 'Türkçe'), (AUTO, 'Otomatik algıla', ''), ('en', 'English', 'İngilizce'),
             ('de', 'Deutsch', 'Almanca'), ('fr', 'Français', 'Fransızca'), ('es', 'Español', 'İspanyolca'),
             ('it', 'Italiano', 'İtalyanca'), ('ru', 'Русский', 'Rusça'), ('ar', 'العربية', 'Arapça'),
             ('az', 'Azərbaycanca', 'Azerbaycanca'))
CODES = tuple(code for code, _, _ in LANGUAGES)
DEFAULT_LANGUAGE = 'tr'
MAX_VOCABULARY = 400  # characters; recognisers read only a short hint

_current = {'language': DEFAULT_LANGUAGE, 'vocabulary': ''}


def clean_language(code):
    return code if code in CODES else DEFAULT_LANGUAGE


def _fold(term):
    """Case-insensitive key that treats Turkish dotted and dotless i alike (ANILCAN = Anılcan)."""
    return term.replace('İ', 'i').replace('I', 'i').replace('ı', 'i').lower()


def clean_vocabulary(text):
    """Comma-separated terms on one line: trimmed, without empties or repeats, capped in length."""
    terms = []
    for term in str(text or '').replace('\n', ',').replace(';', ',').split(','):
        term = ' '.join(term.split())
        if term and _fold(term) not in (_fold(seen) for seen in terms):
            terms.append(term)
    result = ''
    for term in terms:
        longer = f'{result}, {term}' if result else term
        if len(longer) > MAX_VOCABULARY:
            break
        result = longer
    return result


def set_current(language=None, vocabulary=None):
    if language is not None:
        _current['language'] = clean_language(language)
    if vocabulary is not None:
        _current['vocabulary'] = clean_vocabulary(vocabulary)


def language(value=None):
    """The language code to send, or None to let the recogniser detect it. `value` overrides the setting."""
    code = clean_language(_current['language'] if value is None else value)
    return None if code == AUTO else code


def vocabulary(value=None):
    return clean_vocabulary(_current['vocabulary'] if value is None else value)


def instruction(language_code, terms):
    """The Turkish instruction for a general model (Gemini) that transcribes from a prompt."""
    name = next((asked for code, _, asked in LANGUAGES if code == language_code), '')
    text = f'{name} konuşmayı aynen metne çevir; sadece metni döndür.' if name \
        else 'Konuşmayı konuşulduğu dilde aynen metne çevir; sadece metni döndür.'
    if terms:
        text += f' Şu özel adlar ve terimler geçebilir, doğru yaz: {terms}.'
    return text
