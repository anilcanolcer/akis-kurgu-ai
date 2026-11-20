"""Error and service messages in the UI language.

Workers, providers and services raise their errors in Turkish (the application's source language) and
the window shows them; message() translates such a text at the place it is displayed. A fixed sentence or
a template is translated whole, never by substring: the values filled into a template (a file name, a
provider, another message) stay as they are, except that a filled-in value that is itself a known message
is translated too. Anything unknown (FFmpeg output, an operating-system error) is shown unchanged.

EN_MESSAGES holds the texts of the editor's own modules; Story Studio's are in i18n.STORY_EN, which
message() also consults. Template fields are named a, b, c in the order the Turkish source fills them.
"""
from __future__ import annotations

import re
import string

from akis import i18n

EN_MESSAGES = {
    # AI providers
    '{a} izin verilen toplam sürede yanıt vermedi. Başka bir model deneyin veya tekrar deneyin.':
        '{a} did not respond within the allowed total time. Try another model or try again.',
    '{a} bu isteği güvenlik/içerik politikası nedeniyle engelledi veya yanıtlamayı reddetti{b}. '
    'İsteği farklı ifade edip tekrar deneyin.':
        '{a} blocked or declined this request under its safety/content policy{b}. Rephrase the request and try again.',
    '{a} bu isteği güvenlik/içerik politikası nedeniyle engelledi{b}. İsteği farklı ifade edip tekrar deneyin.':
        '{a} blocked this request under its safety/content policy{b}. Rephrase the request and try again.',
    '{a} yanıtı çıktı sınırına takıldı ve yarıda kesildi. Daha kısa bir istekle, daha az videoyla ya da başka '
    'bir modelle tekrar deneyin.':
        '{a} reached the output limit and the response was cut off. Try again with a shorter request, less video '
        'or another model.',
    '{a} boş yanıt döndürdü{b}. Tekrar deneyin ya da başka bir model seçin.':
        '{a} returned an empty response{b}. Try again or choose another model.',
    'Cloudflare için anahtarı "Hesap Kimliği:API anahtarı" biçiminde girin. Hesap kimliği (Account ID) '
    'Cloudflare panelinde Workers AI sayfasında yazan 32 karakterlik değerdir.':
        'Enter the Cloudflare key as "Account ID:API token". The Account ID is the 32-character value shown on '
        'the Workers AI page of the Cloudflare dashboard.',
    '{a} yanıt üretemedi: {b}': '{a} could not produce a response: {b}',
    'Sağlayıcı, API anahtarı ve model gereklidir.': 'A provider, an API key and a model are required.',
    '{a} beklenmeyen biçimde bir yanıt döndürdü (yanıt okunamadı); daha sonra tekrar deneyin ya da başka bir '
    'model seçin.':
        '{a} returned a response in an unexpected format (it could not be read); try again later or choose '
        'another model.',
    'Gemini için ses dosyası çok büyük (en fazla 14 MB).': 'The audio file is too large for Gemini (14 MB at most).',
    'Bu sağlayıcı için transkripsiyon desteklenmiyor.': 'Transcription is not supported for this provider.',
    '{a} {b} saniyede yanıt vermedi. Başka bir model deneyin veya tekrar deneyin.':
        '{a} did not respond within {b} seconds. Try another model or try again.',
    '{a} sunucusuna bağlanılamadı. İnternet bağlantınızı kontrol edin.':
        'Could not connect to the {a} server. Check your internet connection.',
    '{a} sunucusuna bağlanılamadı. İnternet bağlantınızı kontrol edin. ({b})':
        'Could not connect to the {a} server. Check your internet connection. ({b})',
    '{a} video üretemedi ({b}){c}.': '{a} could not generate the video ({b}){c}.',
    '{a} bozuk video verisi döndürdü.': '{a} returned invalid video data.',
    # AI suggestions and edit plans
    'Önerideki "{a}" değeri sayı değil.': 'The value "{a}" in the suggestion is not a number.',
    'Önerideki "{a}" değeri sayı değil: {b}': 'The value "{a}" in the suggestion is not a number: {b}',
    'AI yanıtında geçerli JSON bulunamadı.': 'The AI response contains no valid JSON.',
    'AI kullanılabilir bir öneri döndürmedi; lütfen tekrar deneyin.': 'The AI returned no usable suggestion; please try again.',
    'AI yanıtındaki JSON bir kurgu planı içermiyor.': 'The JSON in the AI response does not contain an edit plan.',
    'AI yanıtı kurgu planı olarak okunamadı (JSON eksik veya bozuk).':
        'The AI response could not be read as an edit plan (JSON missing or broken).',
    'Planda geçersiz sayı: {a}': 'Invalid number in the plan: {a}',
    'Planda kaynak numarası tam sayı olmalı ({a}: {b}).': 'Source numbers in the plan must be whole numbers ({a}: {b}).',
    'Planda "segments" bir liste olmalı.': '"segments" in the plan must be a list.',
    'Plan çok fazla parça içeriyor ({a}; en çok {b}). İsteği sadeleştirip tekrar deneyin.':
        'The plan has too many pieces ({a}; at most {b}). Simplify the request and try again.',
    'Plan videonun tamamını kesiyor; geçerli parça yok.': 'The plan cuts the whole video; no valid piece is left.',
    'Plan uygulanınca boş bir video oluşuyor.': 'Applying the plan would leave an empty video.',
    'Planda geçersiz parça.': 'The plan contains an invalid piece.',
    'Plan olmayan bir kaynağı kullanıyor: {a}': 'The plan uses a source that does not exist: {a}',
    # Local speech, voices and analysis
    'Yerel altyazı için faster-whisper kurulmalı: pip install -r requirements-local-ai.txt':
        'Local captions need faster-whisper: pip install -r requirements-local-ai.txt',
    'Yerel Whisper modeli ({a}) bulunamadı. İlk kullanımda internet bağlantısıyla “Modeli indir” seçeneğini '
    'işaretleyin. Ayrıntı: {b}':
        'The local Whisper model ({a}) was not found. On first use, tick “Download model” while connected to the '
        'internet. Details: {b}',
    'Videodan analiz karesi çıkarılamadı.': 'Could not extract analysis frames from the video.',
    'Videodan ses parçası çıkarılamadı.': 'Could not extract audio from the video.',
    'İndirilen konuşmacı modeli doğrulanamadı (SHA-256 uyuşmuyor).':
        'The downloaded speaker model could not be verified (SHA-256 mismatch).',
    'Ses okunamadı.': 'Could not read the audio.',
    'Windows ses üretimi boş sonuç verdi.': 'Windows speech synthesis returned nothing.',
    'Yerel sistem sesi yalnızca Windows üzerinde kullanılabilir.': 'Local system voices are only available on Windows.',
    'Konuşma metni boş olamaz.': 'The speech text cannot be empty.',
    'Windows ses üretimi başarısız: {a}': 'Windows speech synthesis failed: {a}',
    # Media, timeline and projects
    'FFmpeg bulunamadı. Uygulamayı yeniden kurmayı deneyin.': 'FFmpeg was not found. Try reinstalling the application.',
    'Geçersiz kadraj seçimi.': 'Invalid framing choice.',
    'Medya süresi okunamadı.': 'Could not read the media duration.',
    'Video boyutları okunamadı.': 'Could not read the video dimensions.',
    'Projede kullanılan kaynak video bulunamadı.': 'The source video used in the project was not found.',
    'Medya bulunamadı: {a}': 'Media not found: {a}',
    'Kaynak video bulunamadı.': 'The source video was not found.',
    'Bu iz için ses içeren bir dosya seçin.': 'Choose a file with sound for this track.',
    'Dosyada desteklenen görüntü veya ses akışı bulunamadı.': 'The file has no supported picture or sound stream.',
    'Bu iz için görüntü içeren bir dosya seçin.': 'Choose a file with a picture for this track.',
    'Görsel dosyası bulunamadı.': 'The image file was not found.',
    'Kurtarma dosyası kilitlenemedi: {a}': 'The recovery file could not be locked: {a}',
    'Kayıt zaten sürüyor.': 'A recording is already running.',
    'Kayıt başlamadı.': 'The recording did not start.',
    'Şablon dosyası okunamadığı için değişiklik kaydedilemedi.':
        'The changes could not be saved because the template file could not be read.',
    'Şablon dosyası yazma için kilitlenemedi.': 'Could not lock the template file for writing.',
    'Şablona bir ad verin.': 'Give the template a name.',
    'Şablon kaydedilemedi: geçersiz içerik.': 'The template could not be saved: invalid content.',
    'En çok {a} şablon saklanabilir; önce birini silin.': 'At most {a} templates can be kept; delete one first.',
    # Updates
    'Sürüm için doğrulanabilir kurucu bulunamadı.': 'No verifiable installer was found for the release.',
    'En son sürüm okunamadı.': 'Could not read the latest version.',
    'Geçersiz sürüm numarası.': 'Invalid version number.',
    'Güncelleme dosyasının beklenen SHA-256 değeri geçersiz.': 'The expected SHA-256 value of the update file is invalid.',
    'Güncelleme dosyası veya uygulama yolu bulunamadı.': 'The update file or the application path was not found.',
    'Kurulum başlatılamadı (kod {a}).': 'The installer could not be started (code {a}).',
    'Güncelleme dosyasının doğrulaması başarısız.': 'Verification of the update file failed.',
    'Güncelleme dosyasının SHA-256 doğrulaması başarısız; dosya indirildikten sonra değişmiş olabilir. '
    'Kurulum başlatılmadı, güncellemeyi yeniden indirin.':
        'SHA-256 verification of the update file failed; the file may have changed after it was downloaded. '
        'The installer was not started; download the update again.',
    'Kurulum için izin verilmedi; güncelleme kurulmadı.': 'Permission to install was not given; the update was not installed.',
    # Progress and results the window shows in its status bar
    'Videodan temsilci kareler seçiliyor…': 'Choosing representative frames from the video…',
    'Ses parçası hazırlanıyor…': 'Preparing the audio…',
    'Video çözümleniyor ({a}/{b}): ses, sahne ve kareler…': 'Analysing video ({a}/{b}): sound, scenes and frames…',
    'AI kurgu kararlarını veriyor…': 'The AI is making the edit decisions…',
    'AI kurgu planı hazırlanıyor…': 'The AI is preparing the edit plan…',
    'Konuşma yerel Whisper ile çözümleniyor…': 'Transcribing speech with local Whisper…',
    'Yerel model yükleniyor ve konuşma çözümleniyor…': 'Loading the local model and transcribing speech…',
    'Ses önizlemesi: {a}': 'Audio preview: {a}',
    'Ses önizlemesi kullanılamıyor: Qt medya arka ucu yüklenemedi.':
        'Audio preview is unavailable: the Qt media backend could not be loaded.',
    'AI analizi başlatılıyor…': 'Starting the AI analysis…',
    'Prompt kurgusu başlatılıyor…': 'Starting the prompt edit…',
    'AI kurgusu uygulandı. Beğenmezseniz geri alabilir veya yeni bir istek yazabilirsiniz.':
        'The AI edit was applied. If you do not like it, undo it or write a new request.',
    'Öneriler hazır; birini seçip işaret olarak uygulayabilirsiniz.':
        'Suggestions are ready; choose one to apply it as markers.',
    'Ses hazırlanıyor…': 'Preparing audio…',
    'Windows sesi oluşturuluyor…': 'Creating the Windows voice-over…',
    'Türkçe konuşma metni hazır.': 'The transcript is ready.',
    'AI planı uygulanmadı; zaman çizelgesindeki değişiklikleriniz korundu.':
        'The AI plan was not applied; your changes on the timeline were kept.',
    'AI planı uygulanmadı.': 'The AI plan was not applied.',
    'Kurgu planı uygulanamadı: {a}': 'The edit plan could not be applied: {a}',
    'Akıcı önizleme hazırlanıyor; bu sırada kare kare oynatılıyor…':
        'Preparing smooth playback; playing frame by frame meanwhile…',
    'Kurulum iptal edildi; önceki sürüm değişmedi.': 'The installation was cancelled; the previous version is unchanged.',
    'Kurulum yarıda kesildi.': 'The installation was interrupted.',
    'Uygulama dosyaları kullanımda olduğu için hiçbir dosya değiştirilmedi.':
        'No file was changed because the application files are in use.',
    'Yeni dosyalar yazılamadı (disk dolu olabilir); önceki sürüm geri yüklendi.':
        'The new files could not be written (the disk may be full); the previous version was restored.',
    'Yeni dosyalar yazılamadı ve önceki sürüm otomatik olarak geri yüklenemedi.':
        'The new files could not be written and the previous version could not be restored automatically.',
    'Kurulumun son adımı başarısız oldu; önceki sürüm geri yüklendi.':
        'The last step of the installation failed; the previous version was restored.',
    'Yarım kalmış önceki bir güncelleme onarılamadı.': 'An earlier unfinished update could not be repaired.',
}

_patterns = None


def _compiled():
    """(pattern, English template) pairs, longest Turkish template first so specific ones win."""
    global _patterns
    if _patterns is None:
        pairs = []
        for template, english in sorted(EN_MESSAGES.items(), key=lambda item: len(item[0]), reverse=True):
            regex = ''.join(re.escape(literal) + (f'(?P<{field}>.*?)' if field else '')
                            for literal, field, _, _ in string.Formatter().parse(template))
            pairs.append((re.compile(regex, re.DOTALL), english))
        _patterns = pairs
    return _patterns


def message(text, code: str) -> str:
    """`text` (an application message, often str(exception)) in language `code` ('tr' or 'en')."""
    text = str(text)
    if code != 'en' or not text:
        return text
    if text in EN_MESSAGES:
        return EN_MESSAGES[text]
    for pattern, english in _compiled():
        match = pattern.fullmatch(text)
        if match:
            return english.format(**{key: message(value, code) for key, value in match.groupdict().items()})
    return i18n.story_text(text, code)
