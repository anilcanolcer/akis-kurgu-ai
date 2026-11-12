"""Whole-string UI translation and stable keys for choices that are saved or compared in code.

The UI is written in Turkish; EN_UI maps a complete Turkish source string to its English text. Nothing
is ever translated by substring: a string that is not a key of EN_UI (a project title, a file name, text
the user typed) is shown exactly as it is.

Choice keys are the canonical Turkish item texts the app has always written to project files, so files
from every version stay readable both ways, and timeline_service.canvas_size and friends, which parse
those texts, keep receiving what they expect. The text a combo shows may be English; the key never is.
"""
from __future__ import annotations

EN_UI = {
    "Projeler": "Projects", "İlham": "Inspiration", "Şablonlar": "Templates",
    "Dışa aktarımlar": "Exports", "PROJE MEDYASI": "PROJECT MEDIA",
    "＋  Video ekle": "＋  Add video", "●  Yerel işleme": "●  Local processing",
    "Dışa aktarma bilgisayarınızda yapılır. AI yalnızca siz başlatınca çalışır.":
        "Export runs on your computer. AI only runs when you start it.",
    "Yeni proje": "New project", "Video ekleyerek başlayın": "Start by adding a video",
    "Proje aç": "Open project", "Projeyi kaydet": "Save project", "Dışa aktar  ↗": "Export  ↗",
    "Ses": "Audio", "Zaman çizelgesi": "Timeline", "Seçim: —": "Selection: —",
    "✦ AI Kurgu": "✦ AI Edit", "Düzenle": "Edit", "Yayın": "Publish",
    "Videonu anlat.\nAkış gerisini planlasın.": "Describe your video.\nLet Akış plan the rest.",
    "Ne istediğini yaz.\nAkış kurgulasın.": "Say what you want.\nAkış edits it.",
    "Videoyu keser, yeniden dizer; geçiş, ok ve daire, yazı, renk ve hız ekler. Beğenmezseniz tek tıkla geri alın.":
        "Cuts and reorders the video; adds transitions, arrows and circles, text, colour and speed. Undo in one click.",
    "İSTEĞİNİZ / PROMPT": "YOUR PROMPT", "✦  Prompt ile kurgula": "✦  Edit from prompt",
    "↶  AI kurgusunu geri al": "↶  Undo AI edit", "Öneri al": "Get suggestions",
    "↶  Son adımı geri al": "↶  Undo last step", "↶ Geri al": "↶ Undo", "↷ Yinele": "↷ Redo",
    "İptal": "Cancel",
    "ÖNERİ MODU (KESMEDEN)": "SUGGESTION MODE (NO CUTS)", "KONUŞMA METNİ VE SESLENDİRME": "TRANSCRIPT & VOICEOVER",
    "Konuşmayı da çözümle (yerel Whisper, daha yavaş)": "Also analyse speech (local Whisper, slower)",
    "Yapılan kurgunun özeti burada görünecek.": "A summary of the edit will appear here.",
    "Temsilci kareleri analiz eder; en güçlü bölüm, başlık, açıklama ve kurgu ritmi önerir.":
        "Analyzes representative frames and suggests the strongest section, title, caption and pacing.",
    "YAPAY ZEKÂ HEDEFİ": "AI GOAL", "OPENAI AYARLARI": "OPENAI SETTINGS",
    "Windows'ta güvenli sakla": "Store securely in Windows", "Göster": "Show",
    "✦  AI ile kurguyu planla": "✦  Plan edit with AI",
    "Konuşmayı Türkçe metne çevir": "Transcribe speech",
    "AI kurgu planı burada görünecek.": "The AI edit plan will appear here.",
    "TUVAL ORANI": "CANVAS RATIO", "HIZ VE GEÇİŞ": "SPEED & TRANSITION",
    "Yumuşak giriş ve çıkış geçişi": "Soft fade in and out",
    "Yumuşak giriş ve çıkış geçişi (henüz yok)": "Soft fade in and out (not available yet)",
    "GÖRÜNÜM EFEKTİ": "LOOK EFFECT",
    "Yok": "None", "Sinematik": "Cinematic", "Siyah-beyaz": "Black & white", "Yumuşak": "Soft",
    "RENK VE IŞIK": "COLOR & LIGHT", "Parlaklık": "Brightness", "Kontrast": "Contrast",
    "Doygunluk": "Saturation", "Canlı görünüm uygula": "Apply vivid look",
    "Doğal görünüme dön": "Reset to natural", "BAŞLIK KATMANI": "TITLE LAYER",
    "Videoda görünecek kısa başlık": "Short title shown on video",
    "Üstte": "Top", "Ortada": "Middle", "Altta": "Bottom", "Küçük": "Small", "Orta": "Medium", "Büyük": "Large",
    "Başlığı uygula": "Apply title",
    "Seçili yazı klibini ya da oynatma çizgisindeki yazıyı düzenler; yoksa çizgiden başlayan 3 sn'lik bir başlık ekler. Metni boşaltıp uygularsanız yazı silinir. Uzun başlıklar ekrana sığacak şekilde satırlara bölünür.":
        "Edits the selected text clip or the text under the playhead; otherwise adds a 3 s title at the playhead. Applying an empty field removes the text. Long titles are wrapped to fit the frame.",
    "Son projeleriniz. Silinen proje Geri Dönüşüm Kutusu'na taşınır; kullandığı video dosyalarına dokunulmaz.":
        "Your recent projects. A deleted project goes to the Recycle Bin; its video files are not touched.",
    "＋ Yeni proje": "＋ New project", "Aç": "Open", "Başka proje aç…": "Open another project…", "Sil": "Delete",
    "açık": "open",
    "Henüz kayıtlı proje yok. Projeyi kaydettiğinizde burada görünür.": "No saved projects yet. Saved projects appear here.",
    "Başlık alt-orta güvenli bölgede, yüksek kontrastlı kutu içinde dışa aktarılır.":
        "The title is exported in a high-contrast box within the lower safe area.",
    "YAYIN PAKETİ": "PUBLISH PACKAGE", "Dışa aktarma profili": "Export profile",
    "Temel gürültü azaltma": "Basic noise reduction",
    "Ses yüksekliğini -14 LUFS'a normalleştir": "Normalize loudness to -14 LUFS",
    "Ses yüksekliğini -14 LUFS'a normalleştir (henüz yok)": "Normalize loudness to -14 LUFS (not available yet)",
    "AI Başlık": "AI Title", "Başlık önerisi": "Title suggestion", "Açıklama": "Caption",
    "Video açıklaması": "Video caption", "Etiketler": "Hashtags",
    "Yayın metnini panoya kopyala": "Copy publish text",
    "Instagram'a doğrudan yükleme bu sürümde yoktur. Videoyu filigransız dışa aktarabilir ve yayın paketini kopyalayabilirsiniz.":
        "Direct Instagram upload is not included. Export without a watermark and copy the publish package.",
    "1:1 · Kare": "1:1 · Square", "4:5 · Instagram gönderisi": "4:5 · Instagram post",
    "Kaynak oranı": "Source ratio", "4K Dikey · 2160×3840": "4K Vertical · 2160×3840",
    "Profil oranı seçer; 4K seçenekleri seçili oranı iki kat çözünürlükte dışa aktarır.":
        "The profile picks the ratio; 4K options export the chosen ratio at twice the resolution.",
    # Self-update. Templates with {fields} are translated whole, then filled in (same fields both ways).
    "Akış Kurgu AI güncellemesi": "Akış Kurgu AI update",
    "Yeniden dene": "Retry", "Kapat": "Close", "Bağlanılıyor…": "Connecting…",
    "Akış Kurgu AI {version} indiriliyor…": "Downloading Akış Kurgu AI {version}…",
    "{done:.1f} MB / {total:.1f} MB indirildi": "{done:.1f} MB of {total:.1f} MB downloaded",
    "{done:.1f} MB indirildi (toplam boyut bilinmiyor)": "{done:.1f} MB downloaded (total size unknown)",
    "İndirme iptal ediliyor…": "Cancelling the download…",
    "İndirme tamamlandı ve doğrulandı.": "Download complete and verified.",
    "Güncelleme indirilemedi: {message}": "The update could not be downloaded: {message}",
    "Uygulama değişmedi; çalışmaya devam edebilirsiniz.": "Nothing was changed; you can keep working.",
    "Güncelleme indirmesi iptal edildi.": "Update download cancelled.",
    "{version} güncellemesi indiriliyor…": "Downloading update {version}…",
    "{version} güncellemesi indiriliyor… %{percent}": "Downloading update {version}… {percent}%",
    "{version} güncellemesi ertelendi.": "Update {version} postponed.",
    "Güncelleme hazır.": "Update ready.",
    "Güncellemeden önce devam eden işlemin bitmesini bekleyin.":
        "Wait for the running task to finish before updating.",
    "Güncelleme başlatılamadı: {message}": "The update could not be started: {message}",
    "Akış Kurgu AI {version} sürümüne güncellendi.": "Akış Kurgu AI was updated to {version}.",
    "Akış Kurgu AI {version} güncellemesi kurulamadı; {current} sürümü kullanılmaya devam ediyor.":
        "Akış Kurgu AI {version} could not be installed; you are still using {current}.",
    "Akış Kurgu AI {version} sürümü yayımlandı. İndirme boyutu: {size:.1f} MB.\n\nŞimdi indirilsin mi? İndirme "
    "arka planda yapılır; kurulumdan önce yeniden sorulur.":
        "Akış Kurgu AI {version} is available. Download size: {size:.1f} MB.\n\nDownload it now? It downloads in "
        "the background; you are asked again before installing.",
    "Akış Kurgu AI {version} sürümü yayımlandı.\n\nŞimdi indirilsin mi? İndirme arka planda yapılır; kurulumdan "
    "önce yeniden sorulur.":
        "Akış Kurgu AI {version} is available.\n\nDownload it now? It downloads in the background; you are asked "
        "again before installing.",
    "Akış Kurgu AI {version} güncellemesi önceki denemede kurulamadı; {current} sürümü değişmeden çalışıyor."
    "\n\nAyrıntılar: {log}\n\nYeniden denensin mi?":
        "Installing Akış Kurgu AI {version} failed last time; {current} is still in place and working.\n\n"
        "Details: {log}\n\nTry again?",
    "Kurulum dosyasını elle de çalıştırabilirsiniz: {path}": "You can also run the installer yourself: {path}",
    "Güncellemeyi indirmek için {folder} konumunda en az {needed:.0f} MB boş alan gerekiyor; şu anda {free:.0f} MB "
    "boş. Yer açtıktan sonra güncelleme yeniden önerilecek.":
        "Downloading the update needs at least {needed:.0f} MB free in {folder}; {free:.0f} MB is free. The "
        "update will be offered again once there is room.",
    "Güncellemeyi kurmak için {folder} sürücüsünde en az {needed:.1f} GB boş alan gerekiyor; şu anda {free:.1f} GB "
    "boş. Hiçbir şey değiştirilmedi; yer açtıktan sonra güncelleme yeniden önerilecek.":
        "Installing the update needs at least {needed:.1f} GB free on drive {folder}; {free:.1f} GB is free. "
        "Nothing was changed; the update will be offered again once there is room.",
    "Akış Kurgu AI {version} indirildi ve doğrulandı.\n\nUygulama kapanacak; bir güncelleme penceresi ilerlemeyi "
    "gösterecek ve bitince yeni sürüm açılacak. Bu birkaç dakika sürebilir; o sırada uygulamayı yeniden açmayın. "
    "Bir sorun olursa kullandığınız sürüm olduğu gibi kalır.\n\nÖnce açık projenizi kaydedin. Şimdi güncellensin mi?":
        "Akış Kurgu AI {version} is downloaded and verified.\n\nThe app will close; an update window shows the "
        "progress and the new version opens when it is done. This can take a few minutes; do not reopen the app "
        "meanwhile. If anything goes wrong, the version you use stays as it is.\n\nSave your open project first. "
        "Update now?",
    # İlham, Şablonlar and Hikâye Stüdyosu.
    "Hikâye Stüdyosu": "Story Studio", "Rastgele fikir": "Random idea", "Fikir ara…": "Search ideas…",
    "Fikri kurgu isteğine yaz": "Write idea into edit request",
    "Fikri yaz ve şablonunu uygula": "Write idea and apply its template",
    "Önce “Öneri al” ile öneri isteyin.": "Ask for suggestions with “Get suggestions” first.",
    "Görsel klibe dönüştürülemedi.": "The image could not be turned into a clip.",
}
TR_UI = {english: turkish for turkish, english in EN_UI.items()}

# Stable keys (= canonical Turkish item texts) of the combos whose value is saved or compared in code.
ASPECTS = ("9:16 · Reels / Shorts", "16:9 · YouTube", "1:1 · Kare", "4:5 · Instagram gönderisi", "Kaynak oranı")
EXPORT_PROFILES = ("Reels · 1080×1920", "TikTok · 1080×1920", "YouTube · 1920×1080",
                   "4K Dikey · 2160×3840", "4K UHD · 3840×2160")
EFFECTS = ("Yok", "Sinematik", "Siyah-beyaz", "Yumuşak")
SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
TITLE_POSITIONS = ("Üstte", "Ortada", "Altta")
TITLE_SIZES = ("Küçük", "Orta", "Büyük")
DEFAULT_ASPECT = ASPECTS[0]
DEFAULT_EXPORT_PROFILE = EXPORT_PROFILES[0]


def translate(source: str, code: str) -> str:
    """The text to show for a Turkish source string in language `code` ('tr' or 'en'); whole strings only."""
    return EN_UI.get(source, source) if code == "en" else source


def source_of(text: str) -> str:
    """The Turkish source of a shown string: its own text unless it is exactly a known English translation."""
    return TR_UI.get(text, text)


def choice_key(keys, value, default=None):
    """Map a stored or shown choice to its key.

    Accepts the key itself, its English display text (projects saved while the UI was English by
    versions that stored display text) and a bare leading part such as '16:9' or '4K UHD' (AI plans).
    Returns `default` for anything else.
    """
    if value is None:
        return default
    text = str(value).strip()
    if text in keys:
        return text
    turkish = source_of(text)
    if turkish in keys:
        return turkish
    for key in keys:
        if key.split(" · ")[0] == text or EN_UI.get(key, key).split(" · ")[0] == text:
            return key
    return default


def speed_key(value) -> float:
    """1.25, '1.25' or '1.25×' -> the nearest offered speed. Raises ValueError for anything not a number."""
    number = float(str(value).replace("×", "").replace("x", "").strip()) if isinstance(value, str) else float(value)
    return min(SPEEDS, key=lambda speed: abs(speed - number))
