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
    "Proje aç": "Open project", "Projeyi kaydet": "Save project", "Farklı kaydet": "Save As",
    "Dışa aktar  ↗": "Export  ↗",
    "Projeyi başka bir konuma kaydeder (Ctrl+Shift+S)": "Save the project to another location (Ctrl+Shift+S)",
    "Projeyi farklı kaydet": "Save project as",
    "Ses": "Audio", "Zaman çizelgesi": "Timeline", "Seçim: —": "Selection: —",
    "✦ AI Kurgu": "✦ AI Edit", "Düzenle": "Edit", "Yayın": "Publish",
    "Videonu anlat.\nAkış gerisini planlasın.": "Describe your video.\nLet Akış plan the rest.",
    "Ne istediğini yaz.\nAkış kurgulasın.": "Say what you want.\nAkış edits it.",
    "Videoyu keser, yeniden dizer; geçiş, ok ve daire, yazı, renk ve hız ekler. Beğenmezseniz tek tıkla geri alın.":
        "Cuts and reorders the video; adds transitions, arrows and circles, text, colour and speed. Undo in one click.",
    "İSTEĞİNİZ": "YOUR PROMPT", "✦  Prompt ile kurgula": "✦  Edit from prompt",
    "↶  AI kurgusunu geri al": "↶  Undo AI edit", "Öneri al": "Get suggestions",
    "↶  Son adımı geri al": "↶  Undo last step", "↶ Geri al": "↶ Undo", "↷ Yinele": "↷ Redo",
    "İptal": "Cancel",
    "KONUŞMA METNİ": "TRANSCRIPT",
    "  Kayıt al": "  Record", "Kameradan, ekrandan ya da mikrofondan kayıt alıp projeye ekler.": "Records from a camera, a screen or the microphone and adds it to the project.",
    "Kayıt": "Recording", "Kaynak": "Source", "Mikrofon": "Microphone", "Mikrofon yok": "No microphone",
    "Kamera: {name}": "Camera: {name}", "Ekran: {name}": "Screen: {name}", "Yalnız ses (mikrofon)": "Sound only (microphone)",
    "Kameradan, ekrandan ya da yalnız mikrofondan kayıt alın; kayıt bitince projeye eklenir. Kayıt bilgisayarınızda kalır.":
        "Record from a camera, a screen or the microphone alone; the recording is added to the project when it ends. It stays on your computer.",
    "Yalnız ses kaydedilir. Kayıt, oynatma çizgisinin olduğu yere seslendirme olarak eklenir.":
        "Sound only. The recording is added as a voiceover where the playhead is.",
    "“{name}” ekranı kaydedilecek ({width}×{height}). Kayıt başlayınca program küçülür; ekranın üstündeki küçük çubuktan durdurabilirsiniz. Çubuk kayda girmez.":
        "The screen “{name}” will be recorded ({width}×{height}). When recording starts, the program is minimised; stop it from the small bar at the top of the screen. The bar is not recorded.",
    "Kayıt sürüyor. Ne yapılsın?": "Still recording. What should happen?",
    "Durdur ve ekle": "Stop and add", "Kaydı sil": "Delete the recording", "Kayda devam et": "Keep recording",
    "Önizleme": "Preview",
    "Ekran önizlemesi alınamadı.": "Screen preview unavailable.",
    "Kayıt klasörü": "Recording folder",
    "Kayıt dosyası açılamadı ({path}). Başka bir kayıt klasörü seçin. {error}": "Could not open the recording file ({path}). Choose another recording folder. {error}",
    "Kayıt klasörü oluşturulamadı ({folder}): {error}": "The recordings folder could not be created ({folder}): {error}",
    "Yalnız ses kaydı için bir mikrofon seçin; bu bilgisayarda mikrofon görünmüyor.": "Choose a microphone to record sound only; no microphone is visible on this computer.",
    "Yalnız ses kaydı için bir mikrofon seçin.": "Choose a microphone to record sound only.",
    "● Kaydı başlat": "● Start recording", "■ Durdur ve ekle": "■ Stop and add", "Kaydediliyor…": "Recording…",
    "Kayıt kapatılıyor…": "Finishing the recording…", "Kayıt dosyası oluşmadı.": "No recording file was made.",
    "Kayıt yapılamadı: {error}": "Could not record: {error}", "Kayıt projeye eklendi: {name}": "The recording was added to the project: {name}",
    "Kayıt eklenemedi: {error}": "The recording could not be added: {error}",
    "Ses kaydı oynatma çizgisine eklendi: {name}": "The sound recording was added at the playhead: {name}",
    "◁ Kırp": "◁ Trim", "Kırp ▷": "Trim ▷", "Aralığı sil": "Delete range",
    "Seçili klibin oynatma çizgisinden önceki kısmını atar (Q).": "Drops the selected clip's part before the playhead (Q).",
    "Seçili klibin oynatma çizgisinden sonraki kısmını atar (W).": "Drops the selected clip's part after the playhead (W).",
    "Zaman çizelgesinde boş bir yerden sürükleyerek (ya da cetvelde Shift ile) bir aralık seçin; bu düğme o aralığı bütün izlerden çıkarır ve boşluğu kapatır (Delete).":
        "Choose a range by dragging from an empty spot of the timeline (or with Shift on the ruler); this button takes it out of every track and closes the gap (Delete).",
    "Önce kırpılacak klibi seçin.": "Select the clip to trim first.",
    "Kırpılamadı: oynatma çizgisini seçili klibin içine getirin.": "Could not trim: put the playhead inside the selected clip.",
    "Klibin oynatma çizgisinden önceki kısmı atıldı.": "The clip's part before the playhead was dropped.",
    "Klibin oynatma çizgisinden sonraki kısmı atıldı.": "The clip's part after the playhead was dropped.",
    "Seçili aralık: {start} – {end} ({length} sn). Silmek için Delete ya da “Aralığı sil”.": "Selected range: {start} – {end} ({length} s). Press Delete or “Delete range” to cut it.",
    "Önce zaman çizelgesinde boş bir yerden sürükleyerek bir aralık seçin.": "First choose a range by dragging from an empty spot of the timeline.",
    "Aralık silinemedi: {error}": "The range could not be deleted: {error}",
    "{seconds} sn kesildi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).": "{seconds} s were cut. You can undo this (Ctrl+Z).",
    "Seçili klibin oynatma çizgisinden önceki kısmını at": "Drop the selected clip's part before the playhead",
    "Seçili klibin oynatma çizgisinden sonraki kısmını at": "Drop the selected clip's part after the playhead",
    "Seçili aralığı bırak": "Clear the selected range", "Seçili aralığı ya da klibi sil": "Delete the selected range or clip",
    "Bir fikirle başlayın": "Start from an idea", "Fikir listesi": "Idea list", "AÇILIŞ": "OPENING",
    "ÇEKİM LİSTESİ": "SHOT LIST", "ÖNERİLEN KURGU İSTEĞİ": "SUGGESTED EDIT REQUEST", "UYGUN ŞABLON": "MATCHING TEMPLATE",
    "Fikir, kurgu isteği kutusuna yazılır; videonuz değişmez.": "The idea goes into the edit request box; your video does not change.",
    "Örn. Sessizlikleri at, sahneler arasına geçiş koy, en komik ana ok ve daire ekle, başa dikkat çekici bir yazı yaz.":
        "E.g. cut the silences, put transitions between scenes, add an arrow and a circle at the funniest moment, write an eye-catching title at the start.",
    "{name} stili bu projeye uygulandı.": "The style {name} was applied to this project.",
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
    "Başlık alt-orta güvenli bölgede, yüksek kontrastlı kutu içinde dışa aktarılır.":
        "The title is exported in a high-contrast box within the lower safe area.",
    "YAYIN PAKETİ": "PUBLISH PACKAGE", "Dışa aktarma profili": "Export profile",
    "Temel gürültü azaltma": "Basic noise reduction",
    "Ses yüksekliğini -14 LUFS'a normalleştir": "Normalize loudness to -14 LUFS",
    "SES İYİLEŞTİRME": "SOUND CLEAN-UP", "Konuşurken müziği kıs": "Lower the music while someone speaks",
    "Kısık çekilmiş videoyu yayın düzeyine çıkarır; önizlemede ve dışa aktarmada uygulanır.":
        "Brings quiet footage up to streaming loudness; applied in the preview and the export.",
    "Videonun kendi sesindeki uğultu ve hışırtıyı hafifletir; müziğe dokunmaz. Sonucu dinleyerek karar verin.":
        "Reduces hum and hiss in the video's own sound; music is left alone. Listen before you decide.",
    "Videoda biri konuşurken ses izlerindeki müzik alçalır, susunca geri yükselir.":
        "Music on the audio tracks dips while someone speaks in the video and comes back afterwards.",
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
    # Version tag and the update check it starts.
    "Kurulu sürüm: {version}. Güncellemeleri denetlemek için tıklayın.":
        "Installed version: {version}. Click to check for updates.",
    "Sürüm {version} · kaynak koddan çalışıyor; güncelleme denetimi kurulu sürümde yapılır.":
        "Version {version} · running from source; the update check works in the installed app.",
    "Güncelleme denetimi veya indirmesi zaten sürüyor.": "An update check or download is already running.",
    "Güncellemeler denetleniyor…": "Checking for updates…",
    "Akış Kurgu AI güncel: {version} en son sürüm.": "Akış Kurgu AI is up to date: {version} is the latest version.",
    "Güncellemeler denetlenemedi. İnternet bağlantınızı kontrol edip yeniden deneyin.":
        "Could not check for updates. Check your internet connection and try again.",
    # Şablonlar dialog.
    "Bir şablonla başlayın": "Start from a template",
    "Şablon; projenize hazır izler, tuval oranı, renk stili ve tempo ekler. Medyanızı izlere siz "
    "yerleştirirsiniz; mevcut klipleriniz değişmez.":
        "A template adds ready-made tracks, a canvas ratio, a colour style and a tempo to your project. You "
        "place your media on the tracks; your existing clips are not changed.",
    "Tümü": "All", "Dikey 9:16": "Vertical 9:16", "Yatay 16:9": "Horizontal 16:9", "Kare 1:1": "Square 1:1",
    "Şablon listesi": "Template list", "PROJENİZE EKLENECEKLER": "ADDED TO YOUR PROJECT", "UYARLAYIN": "ADJUST",
    "Renk stili": "Colour style", "Oynatma hızı": "Playback speed",
    "Parlaklık, kontrast ve doygunluğu ayarlar; sonra Düzenle sekmesinden değiştirebilirsiniz.":
        "Sets brightness, contrast and saturation; you can change them later in the Edit tab.",
    "Tüm projenin oynatma hızıdır; 1.00× özgün hızdır.": "The playback speed of the whole project; 1.00× is the original speed.",
    "Tek adımda uygulanır; beğenmezseniz Ctrl+Z ile geri alabilirsiniz.":
        "Applied as one step; press Ctrl+Z to undo it.",
    "Şablonu uygula": "Apply template", "~{n} sn": "~{n} s", "~{n} dk": "~{n} min",
    "Uygun olduğu yerler: {places}": "Good for: {places}", "projede var": "already in project",
    "Düzenlenebilir başlık: “{title}” ({n} sn)": "Editable title: “{title}” ({n} s)",
    "Tuval oranı {old} yerine {new} olacak.": "The canvas ratio changes from {old} to {new}.",
    "Video izi": "Video track", "Ses izi": "Audio track", "Metin izi": "Text track",
    "Enerjik": "Energetic", "Sıcak": "Warm", "Siyah-Beyaz": "Black and white",
    "Yavaş": "Slow", "Orta": "Medium", "Hızlı": "Fast", "Dinamik": "Dynamic",
    "Reels / TikTok hızlı kesim": "Reels / TikTok fast cut", "Ürün tanıtım": "Product promo",
    "Eğitim / anlatım": "Tutorial / explainer", "Müzik klibi": "Music video",
    "Altyazılı konuşma": "Captioned talk", "Basit slideshow": "Simple slideshow",
    "Ana video": "Main video", "Müzik": "Music", "Başlık / altyazı": "Title / captions",
    "Detaylar": "Details", "Ürün": "Product", "Detay": "Detail", "Ürün adı": "Product name",
    "Anlatım": "Narration video", "Gösterim": "Demonstration", "Seslendirme": "Voice-over",
    "Konu başlıkları": "Topic headings", "Ana görüntü": "Main footage", "Bölüm başlıkları": "Chapter titles",
    "Performans": "Performance", "Ek görüntü": "Extra footage", "Şarkı adı": "Song title",
    "Konuşma": "Talking video", "Altyazılar": "Captions", "Görseller": "Images", "Başlıklar": "Titles",
    "Dikkat çekici başlık": "Attention-grabbing title", "Kısa ve net başlık": "Short, clear title",
    "Ders başlığı": "Lesson title", "Bugünün hikâyesi": "Today's story", "Konuşma başlığı": "Talk title",
    "Hikâyeniz": "Your story",
    "İlk saniyede dikkat çeken, hızlı kesimli kısa dikey video.":
        "A short vertical video with fast cuts that grabs attention in the first second.",
    "Tek bir fikri net anlatan, sade görünümlü dikey video.": "A clean vertical video that makes one point clearly.",
    "Ürünü ve ayrıntılarını öne çıkaran kare tanıtım videosu.": "A square promo that shows off a product and its details.",
    "Anlatım ile ekran gösterimini konu başlıklarıyla birleştiren ders videosu.":
        "A lesson that combines narration and demonstration under topic headings.",
    "Günlük anlatımı ara görüntüler ve bölüm başlıklarıyla toparlayan video.":
        "A day-in-the-life video held together by B-roll and chapter titles.",
    "Performans görüntüsünü müziğin ritmine göre kesmek için sinematik düzen.":
        "A cinematic layout for cutting performance footage to the beat.",
    "Kameraya konuşulan videolar için altyazı odaklı sade düzen.": "A plain, caption-first layout for talking to camera.",
    "Fotoğraf ve kısa klipleri müzik eşliğinde sakin bir tempoyla sıralar.":
        "Lines up photos and short clips to music at a calm pace.",
    "Instagram gönderisi · Reklam": "Instagram post · Ads", "YouTube · Kurs": "YouTube · Courses",
    "YouTube · Sunum": "YouTube · Presentations",
    # Sidebar navigation: the whole label, icon included, is the key.
    "▦   Projeler": "▦   Projects", "✦   İlham": "✦   Inspiration", "◈   Şablonlar": "◈   Templates",
    "✎   Hikâye Stüdyosu": "✎   Story Studio", "⇧   Dışa aktarımlar": "⇧   Exports",
    # Timeline toolbar and editor labels.
    "＋ İz": "＋ Track", "− İz": "− Track", "＋ Medya": "＋ Media", "Böl": "Split", "Ripple sil": "Ripple delete",
    "Kelime kelime: sarı vurgu": "Word by word: yellow highlight", "Kelime kelime: renkli kutu": "Word by word: coloured box",
    "Kelime kelime: karaoke": "Word by word: karaoke", "Klasik altyazı (cümle cümle)": "Classic captions (sentence by sentence)",
    "Klip hızı": "Clip speed", "Klip hızı: {value}": "Clip speed: {value}",
    "Bu klip hangi hızda oynasın? Uzunluğu buna göre değişir; izdeki sonraki klipler kayar.":
        "How fast should this clip play? Its length changes to match; later clips on its track move along.",
    "Bu hız uygulanamadı: klip kaynağın sonunu aşıyor.": "This speed could not be applied: the clip would run past the end of its source.",
    "Klip sesi": "Clip volume", "Metni düzenle": "Edit text", "Yakınlık": "Zoom",
    "API transkripsiyon modeli": "API transcription model",
    "Çevrimdışı Windows sistem sesi kullanılır; dil ve ses işletim sisteminde yüklü seslere bağlıdır.":
        "Uses the offline Windows system voice; the language and voice depend on the voices installed in Windows.",
    "Temel gürültü azaltma (henüz yok)": "Basic noise reduction (not available yet)",
    # Features added after 0.5.3: shortcuts, silence removal, export checks, framing, speech settings.
    'Boşluk': 'Space',
    'Oynat / duraklat': 'Play / pause',
    'Seçili klibi sil ve boşluğu kapat': 'Delete the selected clip and close the gap',
    'Son adımı geri al': 'Undo the last step',
    'Geri alınan adımı yinele': 'Redo the undone step',
    'Videoyu dışa aktar': 'Export the video',
    'Seçili klibi oynatma çizgisinden böl': 'Split the selected clip at the playhead',
    'Bir kare geri': 'One frame back',
    'Bir kare ileri': 'One frame forward',
    'Bir saniye geri': 'One second back',
    'Bir saniye ileri': 'One second forward',
    'Başa git': 'Go to the start',
    'Sona git': 'Go to the end',
    'Video ekle': 'Add a video',
    'Bu kısayol listesini göster': 'Show this list of shortcuts',
    'Klavye kısayolları': 'Keyboard shortcuts',
    'Yazı alanına yazarken tek tuşlu kısayollar çalışmaz; yazdığınız harf yazıya gider.': 'Single-key shortcuts do not act while you type in a text field; the letter goes into the text.',
    'Sessizlikleri çıkar': 'Remove silences',
    'Konuşma olmayan yerleri keser. Yapay zekâ, anahtar ve internet gerekmez.': 'Cuts the parts without speech. No AI, key or internet needed.',
    'Konuşma olmayan yerler kesilir. Yapay zekâ ve internet kullanılmaz; beğenmezseniz tek adımda geri alabilirsiniz.': 'Parts without speech are cut. No AI or internet is used; you can undo it in one step.',
    'Sessizlik eşiği: {value} dB': 'Silence threshold: {value} dB',
    'En kısa sessizlik: {value} sn': 'Shortest silence: {value} s',
    'Kesim payı: {value} sn': 'Cut margin: {value} s',
    'Bu düzeyin altındaki ses sessizlik sayılır. Sağa çektikçe daha çok yer kesilir.': 'Sound below this level counts as silence. Further right cuts more.',
    'Bundan kısa duraklamalara dokunulmaz.': 'Pauses shorter than this are left alone.',
    'Her kesimin iki yanında bırakılan süre; kelimelerin başı ve sonu yutulmasın diye.': 'Time kept on both sides of every cut, so word starts and ends are not clipped.',
    'Yeşil kalır, kırmızı kesilir.': 'Green stays, red is cut.',
    'Ses çözümleniyor…': 'Analysing the sound…',
    'Sessizlikleri kes': 'Cut the silences',
    'Videoda çözümlenebilir ses bulunamadı.': 'No sound that can be analysed was found in the video.',
    'Bu ayarlarla kesilecek sessizlik bulunamadı.': 'No silence to cut with these settings.',
    '{count} sessiz yer kesilecek · {before} → {after} ({saved} sn kısalır)': '{count} silent parts will be cut · {before} → {after} ({saved} s shorter)',
    'Zaman çizelgesinde kesilecek video yok.': 'There is no video on the timeline to cut.',
    'Sessizlikler kesilemedi: {error}': 'The silences could not be cut: {error}',
    '{count} sessiz yer kesildi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).': '{count} silent parts were cut. You can undo it (Ctrl+Z).',
    'Dışa aktarılıyor… %{percent}': 'Exporting… {percent}%',
    'Dışa aktarılıyor… %{percent} · bitmek üzere': 'Exporting… {percent}% · almost done',
    'Dışa aktarılıyor… %{percent} · yaklaşık {time} kaldı': 'Exporting… {percent}% · about {time} left',
    'Hedef sürücüde yaklaşık {free} boş yer var; bu video en çok {needed} yer tutabilir. Yer biterse dışa aktarma yarıda kesilir.': 'The target drive has about {free} free; this video may take up to {needed}. If space runs out, the export stops midway.',
    'Yine de devam edilsin mi?': 'Continue anyway?',
    '{count} kaynak dosya bulunamıyor ({names}); dışa aktarma bu yüzden durur.': '{count} source files cannot be found ({names}); the export will stop because of this.',
    'Videoda {count} yerde görüntü yok (toplam {seconds} sn, {places}); buralar siyah görünecek.': 'The video has no picture in {count} places ({seconds} s in total, {places}); these will be black.',
    'Görüntü bittikten sonra {seconds} sn daha yazı ya da ses sürüyor; bu bölüm siyah ekranla dışa aktarılır.': 'Text or sound runs on for {seconds} s after the picture ends; that part is exported over a black screen.',
    'Dışa aktarmadan önce bilmeniz gerekenler:': 'Before you export:',
    'Yine de dışa aktarılsın mı?': 'Export anyway?',
    'Kadraj': 'Framing',
    'Klip tuvale nasıl yerleşsin?': 'How should the clip sit on the canvas?',
    'Kadraj: {choice}': 'Framing: {choice}',
    'Önce bir video klibi seçin.': 'Select a video clip first.',
    'Sığdır (boşluk kalabilir)': 'Fit (bars may remain)',
    'Doldur · ortayı tut': 'Fill · keep the middle',
    'Doldur · solu / üstü tut': 'Fill · keep the left / top',
    'Doldur · sağı / altı tut': 'Fill · keep the right / bottom',
    'Konuşma dili': 'Speech language',
    'Altyazı ve konuşma metni bu dilde çözümlenir.': 'Captions and transcripts are recognised in this language.',
    'Özel adlar ve terimler, virgülle (örn. Anılcan, Akış Kurgu)': 'Names and terms, comma-separated (e.g. Anılcan, Akış Kurgu)',
    'Yanlış yazılan isimleri ve terimleri buraya ekleyin; tanıma bunları bekler.': 'Add names and terms that come out misspelled; recognition will expect them.',
    'Konuşma metne çevriliyor…': 'Transcribing the speech…',
    '{name} uygulandı; medyayı izlere ekleyin.': '{name} applied; add your media to the tracks.',
    # The start panel of an empty project (akis.start_panel).
    'Üç adımda ilk videonuz': 'Your first video in three steps',
    'Bilgisayarınızdan bir video seçin ya da pencereye sürükleyin.': 'Choose a video from your computer or drop it on the window.',
    'Video seç': 'Choose video',
    'Nasıl kurgulanacağını seçin': 'Choose how to edit it',
    'Hazır bir şablon uygulayın ya da AI sekmesine isteğinizi yazın.': 'Apply a ready-made template or write what you want in the AI tab.',
    'Dışa aktarın': 'Export it',
    'Beğendiğinizde sağ üstteki “Dışa aktar” düğmesiyle videonuzu kaydedin.': 'When you like it, save your video with the “Export” button at the top right.',
    # Hand-off to DaVinci Resolve / Final Cut Pro (akis.fcpxml_export).
    'Kurgu dosyası olarak aktar (DaVinci Resolve)': 'Export as an edit file (DaVinci Resolve)',
    'Kesimleri FCPXML dosyası olarak kaydeder; DaVinci Resolve ve Final Cut Pro aynı kurguyu özgün videolarla açar. Video oluşturulmaz.':
        'Saves the cuts as an FCPXML file; DaVinci Resolve and Final Cut Pro open the same edit with the original videos. No video is rendered.',
    'Kurgu dosyası yazılamadı: {error}': 'The edit file could not be written: {error}',
    'Kurgu dosyası kaydedildi: {name}': 'Edit file saved: {name}',
    'Kurgu dosyası kaydedildi:\n{path}': 'Edit file saved:\n{path}',
    'Hedef dosya: {path}': 'Target file: {path}',
    'Windows Güvenliği veya antivirüs yazmayı engellediyse, klasör izinlerini ve Denetimli klasör erişimini kontrol edin; bu uygulama ile FFmpeg’e izin verin ya da başka klasör seçin.':
        'If Windows Security or antivirus blocked the write, check folder permissions and Controlled folder access; allow this app and FFmpeg to write there, or choose another folder.',
    '{count} klip yazıldı.': '{count} clips written.',
    '{count} yazı ve altyazı klibi aktarılmadı.': '{count} text and caption clips were left out.',
    '{count} geçiş aktarılmadı.': '{count} transitions were left out.',
    '{count} klibin hızı aktarılmadı; normal hızda yazıldı.': 'The speed of {count} clips was left out; they play at normal speed.',
    # Split into Shorts (akis.shorts_split, akis.shorts_dialog).
    "Shorts'a böl…": 'Split into Shorts…',
    "Shorts'a böl": 'Split into Shorts',
    'Videonun tamamını art arda dikey kısa videolara böler ve hepsini dışa aktarır.': 'Divides the whole video into consecutive vertical short videos and exports them all.',
    'Videonun tamamı, hiçbir yeri atılmadan, art arda dikey kısa videolara bölünür. Parçalar mümkün olduğunca konuşmadaki bir duraklamadan bölünür.': 'The whole video, with nothing left out, is divided into consecutive vertical short videos. Parts are split at a pause in the speech where possible.',
    ' sn': ' s',
    'Bir parça en çok': 'Longest part',
    'YouTube Shorts en çok 3 dakika kabul eder; 60 saniye en yaygın uzunluktur.': 'YouTube Shorts accepts up to 3 minutes; 60 seconds is the most common length.',
    'Dikey ekranı doldur (yatay videonun kenarları kırpılır)': 'Fill the vertical frame (the sides of a landscape video are cropped)',
    'Her parçanın başına “Bölüm 1/N” yaz': 'Write “Part 1/N” at the start of each part',
    'Parçaları dışa aktar': 'Export the parts',
    '{total} sürelik video {count} parçaya bölünecek: {lengths}': 'The {total} video will be split into {count} parts: {lengths}',
    'Bölüm {number}/{count}': 'Part {number}/{count}',
    'Bulanık arka plan (kırpmadan doldurur)': 'Blurred background (fills without cropping)',
    'Doldur (kenarlar kırpılır)': 'Fill (the sides are cropped)',
    'Sığdır (üstte ve altta siyah boşluk)': 'Fit (black bars above and below)',
    'Görüntü': 'Picture',
    'Süre': 'Length',
    'Başlık': 'Title',
    'Üstte sıra numarası ve başlık kartı göster (ör. “4 / 7”)': 'Show a number and title card at the top (e.g. “4 / 7”)',
    'Başlıklar kartta ve dosya adında kullanılır; çift tıklayıp değiştirebilirsiniz.': 'Titles are used on the card and in the file name; double-click to change them.',
    '{total} sürelik video {count} parçaya bölünecek.': 'The {total} video will be split into {count} parts.',
    'Bulanık arka plan (kırpmadan doldur)': 'Blurred background (fill without cropping)',
    # Highlights (akis.highlights).
    'Öne çıkan anları bul…': 'Find highlights…',
    'Öne çıkan anlar': 'Highlights',
    'Videonun en canlı bölümlerini gerekçesiyle listeler; seçtiklerinizi dikey kısa video olarak kaydeder.': 'Lists the liveliest parts of the video with the reasons; saves the ones you pick as vertical short videos.',
    'Öne çıkan anlar en az bir dakikalık videolarda aranır.': 'Highlights are looked for in videos of at least a minute.',
    'Öne çıkan anlar aranıyor…': 'Looking for highlights…',
    'Öne çıkan bir an bulunamadı.': 'No highlight was found.',
    'Videonun en canlı bölümleri, sesine bakılarak bulundu. İşaretlediklerinizi dikey kısa video olarak dışa aktarabilirsiniz; başlıkları çift tıklayıp değiştirebilirsiniz.': 'The liveliest parts of the video were found from its sound. Export the ticked ones as vertical short videos; double-click a title to change it.',
    'Zaman': 'Time',
    'Neden': 'Why',
    'Seçilenleri Shorts olarak dışa aktar': 'Export the ticked ones as Shorts',
    'neredeyse kesintisiz konuşma': 'almost non-stop speech',
    'yoğun konuşma': 'dense speech',
    'sesin yükseldiği {count} an': '{count} moments where the voice rises',
    'videonun en yüksek sesli bölümlerinden': 'one of the loudest parts of the video',
    'sakin bir bölüm': 'a calm part',
    # Analyses run in the background.
    'Müziğin ritmi çözümleniyor…': 'Analysing the beat of the music…',
    'Konuşmadaki vurgular aranıyor…': 'Looking for emphasis in the speech…',
    'Konuşmadaki duraklamalar aranıyor…': 'Looking for pauses in the speech…',
    # Voiceover (akis.tts_service).
    'Konuşma diline uygun ses': 'Voice matching the speech language',
    'Seslendirmeyi okuyacak Windows sesi. Yeni ses dili Windows Ayarları › Zaman ve dil › Konuşma bölümünden eklenir.': 'The Windows voice that reads the voiceover. More voices are added in Windows Settings › Time & language › Speech.',
    'Oynatma çizgisinden zaman çizelgesine ekle': 'Add to the timeline at the playhead',
    'Ses kaydedildi: {path}': 'Audio saved: {path}',
    'Seslendirme zaman çizelgesine eklendi: {name}': 'Voiceover added to the timeline: {name}',
    # Batch export (akis.batch_export, akis.batch_dialog).
    'Toplu dışa aktar…': 'Batch export…',
    'Toplu dışa aktar': 'Batch export',
    'Birden çok videoyu aynı biçimde işleyip her birini ayrı dosya olarak kaydeder.': 'Processes several videos the same way and saves each as its own file.',
    'Seçtiğiniz her video aynı biçimde işlenip ayrı bir dosya olarak kaydedilir. Renk, hız, ses düğmeleri ve tuval oranı açık projedeki ayarlardan alınır.': 'Each chosen video is processed the same way and saved as its own file. Colour, speed, sound switches and the canvas ratio come from the open project.',
    'Seçileni çıkar': 'Remove selected',
    'Şablon': 'Template',
    'Şablon yok': 'No template',
    'Kaydedilecek klasör': 'Folder to save to',
    'Seç…': 'Choose…',
    'Başlat': 'Start',
    '{done} / {total} video dışa aktarıldı:': '{done} of {total} videos exported:',
    'Çıktı dosyası kaynak medyayla aynı olamaz.': 'The output file cannot be the same as the source media.',
    # Reviewing an AI plan (akis.plan_review).
    'Yeni kesim: {count} parça, yaklaşık {seconds} sn': 'New cut: {count} pieces, about {seconds} s',
    '{count} geçiş: {names}': '{count} transitions: {names}',
    '{count} ekran yazısı: {texts}': '{count} on-screen texts: {texts}',
    '{count} işaret (ok / daire)': '{count} marks (arrow / circle)',
    'Renk: {values}': 'Colour: {values}',
    'parlaklık': 'brightness',
    'kontrast': 'contrast',
    'doygunluk': 'saturation',
    'Hız: {value}×': 'Speed: {value}×',
    'Tuval oranı: {value}': 'Canvas ratio: {value}',
    'Video sesi: %{value}': 'Video volume: {value}%',
    'Müzik sesi: %{value}': 'Music volume: {value}%',
    'Uygulamadan önce AI planını göster': 'Show the AI plan before applying it',
    "AI'ın önerdiği her değişiklik ayrı bir kutuda gösterilir; istemediklerinizin işaretini kaldırırsınız.": 'Each change the AI proposes is shown in its own box; untick the ones you do not want.',
    'AI planı uygulanmadı.': 'The AI plan was not applied.',
    'AI planını incele': 'Review the AI plan',
    'AI şu değişiklikleri öneriyor:': 'The AI proposes these changes:',
    'İstemediğiniz kısımların işaretini kaldırın; yalnızca işaretliler uygulanır.': 'Untick the parts you do not want; only the ticked ones are applied.',
    'Seçilenleri uygula': 'Apply the ticked ones',
    'Altyazıları kaldır': 'Remove the captions',
    'AI yazılarını kaldır': 'Remove the AI texts',
    'AI işaretlerini kaldır': 'Remove the AI marks',
    'Altyazı ekle': 'Add captions',
    'Yayın başlığı, açıklaması ve etiketleri': 'Publish title, description and hashtags',
    # Punch-in zoom on emphasis (akis.emphasis).
    'Vurgu anlarında yakınlaştır': 'Punch in on emphasis',
    'Konuşmacının sesinin yükseldiği anlarda görüntü kısa bir süre hafifçe yakınlaşır. Yeniden basınca kaldırmayı sorar; internet gerekmez.':
        'Where the speaker gets louder, the picture zooms in slightly for a moment. Press again to be asked about removing them; no internet needed.',
    'Videoda vurgu yakınlaştırmaları var. Kaldırılsın mı?': 'The video has punch-in zooms. Remove them?',
    '{count} vurgu yakınlaştırması kaldırıldı.': '{count} punch-in zooms were removed.',
    'Zaman çizelgesinde video yok.': 'There is no video on the timeline.',
    'Belirgin bir vurgu anı bulunamadı.': 'No clear moment of emphasis was found.',
    '{count} vurgu anında yakınlaştırma eklendi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).': '{count} punch-in zooms were added. You can undo it (Ctrl+Z).',
    # Cuts on the beat (akis.beat_sync).
    'Kesimleri müziğin ritmine oturt': 'Put the cuts on the beat',
    'Ses izindeki müziğin vuruşlarını bulur ve video kesimlerini en yakın vuruşa kaydırır. Müziğe dokunmaz; internet gerekmez.':
        'Finds the beats of the music on the audio track and moves the video cuts to the nearest beat. The music is not touched; no internet needed.',
    'Önce bir ses izine müzik ekleyin; kesimler onun vuruşuna oturtulur.': 'First add music to an audio track; the cuts are put on its beat.',
    'Ritme oturtulacak kesim yok; önce videoyu bölün ya da birkaç klip ekleyin.': 'There are no cuts to put on the beat; split the video or add a few clips first.',
    'Müzikte belirgin bir ritim bulunamadı.': 'No clear beat was found in the music.',
    'Kesimler zaten vuruşta ya da yakınlarında vuruş yok.': 'The cuts are already on the beat, or no beat is close to them.',
    'Kesimler ritme oturtulamadı: {error}': 'The cuts could not be put on the beat: {error}',
    '{count} kesim müziğin vuruşuna oturtuldu. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).': '{count} cuts were put on the beat. You can undo it (Ctrl+Z).',
    # Retakes (akis.retakes).
    'Tekrar çekimleri temizle': 'Remove retakes',
    'Konuşmacıları ayır': 'Separate speakers',
    'Kimin ne zaman konuştuğunu bulur: değişimleri işaretler ya da yalnızca bir konuşmacıyı bırakır. Bilgisayarınızda çalışır; ilk kullanımda küçük bir ses modeli indirilir.':
        'Finds who speaks when: marks the changes or keeps one speaker only. Runs on your computer; a small voice model is downloaded on first use.',
    'Konuşmacılar ayırt ediliyor (ilk kullanımda {size} MB ses modeli indirilir)…': 'Telling the speakers apart (a {size} MB voice model is downloaded on first use)…',
    'Tek konuşmacı bulundu.': 'One speaker was found.',
    'Tek konuşmacı bulundu. (Ses modeli indirilemediği için sesler perdeden ayrıldı; iki erkek sesi gibi benzer sesler böyle ayırt edilemez.)':
        'One speaker was found. (The voice model could not be downloaded, so voices were told apart by pitch; similar voices such as two men cannot be separated that way.)',
    'Konuşmacılar ayırt ediliyor…': 'Telling the speakers apart…',
    '{count} konuşmacı bulundu:': '{count} speakers found:',
    'Konuşmacı {number}: {seconds} sn — “{sample}”': 'Speaker {number}: {seconds} s — “{sample}”',
    'Değişimleri işaretle': 'Mark the changes',
    'Yalnız Konuşmacı {number}': 'Speaker {number} only',
    '{count} konuşmacı değişimi işaretlendi.': '{count} speaker changes were marked.',
    'Kesilecek bir yer kalmadı.': 'There is nothing left to cut.',
    'Ana videoda bu konuşmacının konuştuğu bir yer yok.': 'This speaker does not speak anywhere in the main video.',
    'Dolgu sözcükleri kesilince videoda hiçbir şey kalmıyor.': 'Cutting the filler words would leave nothing of the video.',
    'Tekrarlar kesilince videoda hiçbir şey kalmıyor.': 'Cutting the retakes would leave nothing of the video.',
    'Yalnız Konuşmacı {number} kaldı. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).': 'Only speaker {number} is left. You can undo this (Ctrl+Z).',
    'Örnek videonun stilini al…': 'Take the style of a sample video…',
    'Beğendiğiniz bir videonun oranını, kadrajını, ses düzeyini ve rengini okur; şablon olarak kaydedip bu projeye uygular. İnternet gerekmez.':
        'Reads the shape, framing, loudness and colour of a video you like; saves it as a template and applies it to this project. No internet needed.',
    'Stili alınacak örnek video': 'Sample video to take the style from',
    'Örnek videonun stili okunuyor…': 'Reading the sample video’s style…',
    'Örnek: {name}': 'Sample: {name}',
    'Örnek videoda bulunanlar:': 'Found in the sample video:',
    '“{name}” adıyla Şablonlarım’a kaydedilip bu projeye uygulansın mı?': 'Save it to My templates as “{name}” and apply it to this project?',
    'Oran: {ratio} ({width}×{height})': 'Shape: {ratio} ({width}×{height})',
    'kendine özgü': 'its own',
    'Görüntü: {framing}': 'Picture: {framing}',
    'sığdırılmış (boşluklu)': 'fitted (with bars)', 'kadrajı dolduruyor': 'fills the frame',
    'bulanık arka plan üstünde': 'on a blurred background',
    'Ses: yok': 'Sound: none',
    'Ses düzeyi: {lufs} LUFS{levelled}': 'Loudness: {lufs} LUFS{levelled}',
    ' (eşitlenmiş: ses eşitleme açılacak)': ' (evened out: loudness levelling will be turned on)',
    'Renk: parlaklık {b:+d}, kontrast {c:+d}, doygunluk {s:+d} (sizin videonuza göre)': 'Colour: brightness {b:+d}, contrast {c:+d}, saturation {s:+d} (compared with your video)',
    'Renk: karşılaştırmak için önce kendi videonuzu ekleyin': 'Colour: add your own video first to compare',
    'Renk: sizin videonuza yakın, değişmeyecek': 'Colour: close to your video, left as it is',
    'Tempo: dakikada {cuts} kesim (ortalama çekim {shot} sn)': 'Pace: {cuts} cuts a minute (shots of {shot} s on average)',
    'Hızlı bir kurgu: “Sessizlikleri çıkar” ve “Dolgu sözcüklerini kes” temposuna yaklaştırır.': 'A fast edit: “Remove silences” and “Cut filler words” bring yours closer to its pace.',
    'Tempo: kesim yok, tek çekim': 'Pace: no cuts, one shot',
    'Dolgu sözcüklerini kes (ııı, eee, şey)': 'Cut filler words (um, uh, like)',
    'Duraksamaları ve “şey, yani” gibi dolgu sözcüklerini bulup keser. Yerel konuşma tanımayla çalışır; internet gerekmez.':
        'Finds hesitations and filler words such as “şey, yani” and cuts them. Uses local speech recognition; no internet needed.',
    'Dolgu sözcükleri aranıyor (yerel konuşma tanıma)…': 'Looking for filler words (local speech recognition)…',
    'Dolgu sözcüğü bulunamadı.': 'No filler words were found.',
    'Dolgu sözcükleri zaten kesilmiş.': 'The filler words are already cut.',
    'Dolgu sözcükleri kesilemedi: {error}': 'The filler words could not be cut: {error}',
    '{count} dolgu sözcüğü kesildi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).': '{count} filler words were cut. You can undo this (Ctrl+Z).',
    '{count} dolgu sözcüğü bulundu (toplam {seconds} sn):': '{count} filler words found ({seconds} s in all):',
    'Aynı cümle birkaç kez söylendiyse yalnızca son denemeyi bırakır. Önce aşağıdan yerel konuşma metnini çıkarın; internet gerekmez.':
        'When a sentence was said several times, keeps only the last try. Make the local transcript below first; no internet needed.',
    'Önce “Konuşma metni ve seslendirme” bölümünden yerel konuşma metnini çıkarın; tekrarlar bu metinden bulunur.':
        'First make the local transcript in “Transcript and voiceover”; retakes are found in it.',
    'Tekrar çekim bulunamadı.': 'No retakes were found.',
    'Konuşma metninin videosu zaman çizelgesinde yok.': "The transcript's video is not on the timeline.",
    'Tekrarlar zaten kesilmiş.': 'The retakes are already cut.',
    'Tekrarlar kesilemedi: {error}': 'The retakes could not be cut: {error}',
    '{count} tekrar çekim kesildi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).': '{count} retakes were cut. You can undo it (Ctrl+Z).',
    '{count} tekrar çekim bulundu; her birinin yalnızca son denemesi kalacak:': '{count} retakes found; only the last try of each will stay:',
    '… ve {count} tane daha.': '… and {count} more.',
    'Kesilsin mi? Beğenmezseniz tek adımda geri alabilirsiniz.': 'Cut them? You can undo it in one step.',
    # Three formats at once (akis.multi_export).
    'Üç biçimde dışa aktar': 'Export in three formats',
    'Aynı kurguyu tek seferde dikey (9:16), kare (1:1) ve yatay (16:9) üç ayrı dosya olarak kaydeder.':
        'Saves the same edit in one go as three files: vertical (9:16), square (1:1) and landscape (16:9).',
    'Şu dosyalar zaten var ve üzerine yazılacak:\n{names}\n\nDevam edilsin mi?':
        'These files already exist and will be overwritten:\n{names}\n\nContinue?',
    # Export by copying (akis.fast_export).
    'Bu kurgu yalnızca kesimlerden oluşuyor. Yeniden kodlamadan, hızlı dışa aktarılsın mı?\n\nKalite hiç düşmez ve işlem çok daha kısa sürer. Kesim noktaları en yakın anahtar kareye kayabilir; her parçanın başında genellikle iki saniyeden kısa bir fazlalık kalabilir ve birleşme yerinde tek bir kare atlanabilir.\n\n“Hayır” derseniz olağan (kare hassasiyetli) dışa aktarma yapılır.':
        'This edit is nothing but cuts. Export it quickly, without encoding it again?\n\nNo quality is lost and it takes far less time. Cuts may move to the nearest keyframe; each piece may start with usually less than two extra seconds, and a single frame may be skipped at a join.\n\nChoose “No” for the normal, frame-accurate export.',
    'Hızlı dışa aktarma yapılamadı: {error}\n\nYeniden dışa aktarıp soruya “Hayır” diyerek olağan dışa aktarmayı kullanın.':
        'The quick export failed: {error}\n\nExport again and answer “No” to use the normal export.',
    # What left the computer (akis.privacy_log).
    'Bu oturumda bilgisayarınızdan hiçbir şey gönderilmedi.': 'Nothing has been sent from your computer in this session.',
    'Bu oturumda gönderilenler:': 'Sent in this session:',
    'video kareleri ve istek metni': 'video frames and the request text', 'istek metni': 'the request text',
    'videonun sesi': "the video's sound", 'hikâye metni ve görselleri': 'story text and images',
    'sürüm denetimi (video gönderilmez)': 'update check (no video is sent)',
    # Status messages that were still Turkish-only.
    'Dosya bulunamadı: {name}': 'File not found: {name}',
    'Bu dosya türü açılamıyor: {name}': 'This kind of file cannot be opened: {name}',
    'Öneri işaretleri projeye eklendi.': 'Suggestion markers were added to the project.',
    '{count} altyazı klibi eklendi.': '{count} caption clips were added.',
    'Akıcı önizleme kullanılamadı, kare kare önizlemeye geçildi: {error}': 'Smooth playback was not available; switched to frame-by-frame preview: {error}',
    'Kaydedilecek API anahtarını girin.': 'Enter the API key to save.',
    'Anahtar güvenli kasaya kaydedilemedi: {error}': 'The key could not be saved to the secure store: {error}',
    '“{idea}” fikri kurgu isteğine yazıldı ve {layout} şablonu uygulandı.': 'The idea “{idea}” was written into the edit request and the {layout} template was applied.',
    '“{idea}” fikri kurgu isteğine yazıldı; AI sekmesinden uygulayabilirsiniz.': 'The idea “{idea}” was written into the edit request; apply it from the AI tab.',
    'Önce seslendirme metni girin.': 'Enter the voiceover text first.',
    'Dışa aktarma başlatılamadı.': 'The export could not be started.',
    'Dışa aktarma başlatılmadı.': 'The export was not started.',
    'Önizleme boyutu belirlenemedi: {error}': 'The preview size could not be worked out: {error}',
    'Burada düzenlenecek bir yazı veya işaret yok. Çift tıklamayı bir yazının ya da işaretin üstünde deneyin.': 'There is no text or mark to edit here. Try double-clicking on a text or a mark.',
    'Bu sürümde medya yalnızca video/ses izine eklenir.': 'In this version media can only be added to a video or audio track.',
    'Klip silinemedi: {error}': 'The clip could not be deleted: {error}',
    'Önizleme oluşturulamadı: {error}': 'The preview could not be made: {error}',
    'Klip sesi: %{value}': 'Clip volume: {value}%',
    'Proje açılamadı; önceki çalışma olduğu gibi korundu.': 'The project could not be opened; your previous work was kept as it was.',
    'Otomatik kayıt yapılamadı: {error}': 'Autosave failed: {error}',
    'İşlem devam ediyor; kapatmadan önce bitmesini bekleyin.': 'A task is still running; wait for it to finish before closing.',
    # Şablonlarım (the user's own templates).
    "Şablonlarım": "My templates", "Şablonlarım…": "My templates…",
    "Kendi projelerinizden kaydettiğiniz şablonlar.": "Templates you saved from your own projects.",
    "Bir projenizin izlerini, tuval oranını, renk ve hız ayarını, ses düğmelerini şablon olarak saklayın; sonraki videoya tek seçimle uygulayın.":
        "Keep a project's tracks, canvas ratio, colour and speed settings and sound switches as a template; apply it to the next video in one choice.",
    "Bu projeyi şablon olarak kaydet": "Save this project as a template", "Şablonu sil": "Delete template",
    "Henüz kayıtlı şablonunuz yok.": "You have no saved templates yet.",
    "Şablon olarak kaydet": "Save as template", "Şablonun adı:": "Template name:",
    "“{name}” adlı şablon zaten var. Üzerine yazılsın mı?": "A template named “{name}” already exists. Overwrite it?",
    "İzler: {tracks}": "Tracks: {tracks}",
    "Oran: {aspect} · Hız: {speed}× · Renk: {color} · Ses: {sound}":
        "Ratio: {aspect} · Speed: {speed}× · Colour: {color} · Sound: {sound}",
    " · Kadraj: {framing}": " · Framing: {framing}",
    "Başlık: {title}": "Title: {title}",
    "ses eşitleme": "loudness levelling", "gürültü azaltma": "noise reduction", "müzik kısma": "music ducking",
    "sığdır": "fit", "doldur": "fill", "bulanık arka plan": "blurred background", "yok": "none",
    "Şablon kaydedilemedi: {error}": "The template could not be saved: {error}",
    "“{name}” şablonu silinsin mi? Bu geri alınamaz.": "Delete the template “{name}”? This cannot be undone.",
    "Şablon silinemedi: {error}": "The template could not be deleted: {error}",
    "Videoda görünecek kısa başlık (henüz yok)": "Short title shown on video (not available yet)",
    "Başlık katmanı henüz yok. Videoya yazıyı AI kurgusu, şablonlar veya altyazılar ekler.":
        "The title layer is not available yet. Text is added to the video by AI edits, templates or captions.",
    # Tooltips (apply_language translates them too).
    "Devam eden işlemi durdurur.": "Stops the running task.",
    "Ctrl + tekerlek: yakınlaştır · sürükle: kaydır · orta tuş: sıfırla · çift tık: yazı/işaret düzenle":
        "Ctrl + wheel: zoom · drag: pan · middle button: reset · double-click: edit text/mark",
    "Son adımı geri al (Ctrl+Z)": "Undo the last step (Ctrl+Z)",
    "Geri alınan adımı yinele (Ctrl+Y)": "Redo the undone step (Ctrl+Y)",
    "Yazdığınız isteğe göre videoyu gerçekten keser, dizer ve ayarlar.":
        "Really cuts, reorders and adjusts the video according to your request.",
    "AI kurgusu dahil son düzenlemeyi geri alır (Ctrl+Z).": "Undoes the last edit, AI edits included (Ctrl+Z).",
    "Model önbellekte yoksa bu adım atlanır; kurgu kare, sessizlik ve sahne bilgisiyle yapılır.":
        "If the model is not cached this step is skipped; the edit then uses frames, silences and scenes.",
    "Ortak timeline render yolunda henüz desteklenmiyor.": "Not supported by the shared timeline renderer yet.",
    "Bu kontrol ortak timeline render yolunda henüz desteklenmiyor.":
        "This control is not supported by the shared timeline renderer yet.",
    "Kayıtlı bir projeyi açar (Ctrl+O)": "Opens a saved project (Ctrl+O)",
    "Projeyi kaydeder (Ctrl+S)": "Saves the project (Ctrl+S)",
    "Videoyu MP4 olarak dışa aktarır (Ctrl+E)": "Exports the video as MP4 (Ctrl+E)",
    "Oynat / duraklat (Boşluk)": "Play / pause (Space)",
    "Seçili klibi siler ve boşluğu kapatır. Delete tuşu klibi boşluk bırakarak siler.":
        "Deletes the selected clip and closes the gap. The Delete key deletes it and leaves the gap.",
    # Status bar and messages on common paths.
    "Bir video sürükleyin veya “Video ekle” düğmesini kullanın.": "Drag in a video or use “Add video”.",
    "Proje düzenleyicisi açık.": "The project editor is open.",
    "Dışa aktarmak için üstteki düğmeyi kullanın.": "Use the button at the top to export.",
    "Video hazır. Sağdaki kutuya isteğinizi yazıp kurgulatabilirsiniz.":
        "Video ready. Type your request in the box on the right to have it edited.",
    "Akıcı önizleme hazırlanıyor…": "Preparing smooth preview…", "Oynatılıyor.": "Playing.",
    "Duraklatıldı.": "Paused.", "API anahtarı ve model belirtin.": "Enter an API key and a model.",
    "API anahtarı sistem kasasına kaydedildi.": "API key saved to the system vault.",
    "Anahtar artık kaydedilmeyecek; kayıtlı anahtar bu sürümde silinemiyor.":
        "The key will no longer be saved; this version cannot delete a stored key.",
    "Kayıtlı anahtar silinemedi: {error}": "The stored key could not be deleted: {error}",
    "{provider} anahtarı sistem kasasından silindi.": "{provider} key removed from the system vault.",
    "Kurgu isteği kutusunda yazdığınız bir metin var. Fikirle değiştirilsin mi?":
        "The edit request box already holds your text. Replace it with the idea?",
    "Kurgu isteğiniz korundu; fikir uygulanmadı.": "Your edit request was kept; the idea was not applied.",
    "Son adım geri alındı.": "Last step undone.", "Adım yinelendi.": "Step redone.",
    "Video zaman çizelgesine eklendi.": "Video added to the timeline.",
    "Medya zaman çizelgesine eklendi.": "Media added to the timeline.",
    "Medya eklenemedi: {error}": "The media could not be added: {error}",
    "Dışa aktarma hazırlanıyor…": "Preparing export…", "Dışa aktarma tamamlandı.": "Export finished.",
    "Video başarıyla oluşturuldu:\n{path}": "The video was created:\n{path}",
    "Renk görünümü güncellendi; dışa aktarmada uygulanacak.": "Colour look updated; it is applied on export.",
    "Yayın metni panoya kopyalandı.": "Publish text copied to the clipboard.",
    "Önce bir video ekleyin ve yüklenmesini bekleyin.": "Add a video first and wait for it to load.",
    "Bir işlem devam ediyor; lütfen bitmesini bekleyin.": "A task is running; please wait for it to finish.",
    "İptal ediliyor…": "Cancelling…", "İşlem tamamlanamadı.": "The task could not be completed.",
    "İşlem iptal edildi.": "Task cancelled.", "Dışa aktarma iptal edildi.": "Export cancelled.",
    "Önce hedef izi seçin.": "Select the target track first.",
    "Önce silinecek klibi seçin.": "Select the clip to delete first.",
    "Silinecek izi seçin.": "Select the track to remove.", "Önce bir metin klibi seçin.": "Select a text clip first.",
    "Bir ses veya video klibi seçin.": "Select an audio or video clip.",
    "Önce bölünecek klibi seçin.": "Select the clip to split first.",
    "Klip bölünemedi: oynatma imlecini seçili klibin içine getirin.":
        "The clip could not be split: move the playhead inside the selected clip.",
    "Klip bölünemedi: {error}": "The clip could not be split: {error}", "Klip bölündü.": "Clip split.",
    "Klip silindi. Ctrl+Z ile geri alabilirsiniz.": "Clip deleted. Press Ctrl+Z to undo.",
    "Kaydetmek için önce bir video veya medya ekleyin.": "Add a video or media before saving.",
    "Proje ve sürüm anlık görüntüsü kaydedildi.": "Project and version snapshot saved.",
    "Proje kaydedildi; sürüm anlık görüntüsü oluşturulamadı: {error}":
        "Project saved; the version snapshot could not be created: {error}",
    "Proje kaydedilemedi: {error} (konum: {path})": "The project could not be saved: {error} (location: {path})",
    "Windows bu konuma yazmayı engelledi: {path}. Dosya başka bir uygulamada açıksa kapatın. "
    "Klasöre yazma izniniz yoksa farklı bir konum seçin. Windows Defender'da Denetimli klasör erişimi "
    "bu uygulamayı engelliyorsa, uygulamaya izin verin. Ayrıntı: {error}":
        "Windows blocked writing to this location: {path}. Close the file if another app is using it. "
        "Choose a different folder if you do not have write access. If Windows Defender Controlled folder "
        "access is blocking this app, allow the app there. Details: {error}",
    "Proje açıldı ve son ayarlar geri yüklendi.": "Project opened and its settings restored.",
    "Projede kaydedilmemiş değişiklikler var. Kaydedilsin mi?": "The project has unsaved changes. Save them?",
    # Recovery prompt: three explicit choices.
    "Kurtarılmış çalışma bulundu ({when}). Açılsın mı?": "Recovered work found ({when}). Open it?",
    "“Sonra sor” şimdilik açmaz, dosyayı saklar ve daha sonra yeniden sorar. “Sil” kurtarma dosyasını kalıcı "
    "olarak siler.":
        "“Ask later” does not open it now, keeps the file and asks again later. “Delete” removes the recovery "
        "file permanently.",
    "Aç": "Open", "Sonra sor": "Ask later", "Sil": "Delete",
    "Kurtarılan çalışma açıldı; kalıcı olması için projeyi kaydedin.":
        "Recovered work opened; save the project to keep it.",
    "Proje açılmadı; kurtarma dosyası saklandı ve bir dahaki açılışta yeniden sorulacak.":
        "The project was not opened; the recovery file is kept and you will be asked again next time.",
    # İlham dialog.
    "Yaratıcı video fikirleri: bir fikir seçin, kurgu isteğine yazın ve isterseniz uygun şablonu da uygulayın.":
        "Creative video ideas: pick one, write it into the edit request and, if you like, apply its template too.",
    "Bu aramaya uygun fikir bulunamadı.": "No ideas match this search.", "Açılış:": "Opening:",
    "Çekim listesi": "Shot list", "Önerilen kurgu isteği": "Suggested edit request", "Uygun şablon:": "Matching template:",
    "Koyu tema": "Dark theme", "Açık tema": "Light theme", "Tema": "Theme", "Görünüm değiştirildi.": "Appearance changed.",
    # Labels that used to show both languages at once.
    "Medya ara": "Search media", "Anahtarı güvenli kaydet": "Save key securely", "Stil": "Style", "Odak": "Focus",
    "Seçili öneriyi işaretlere uygula": "Apply the selected suggestion as markers", "Yerel Whisper": "Local Whisper",
    "Modeli indir (internet)": "Download the model (internet)",
    "Yerel model ilk kullanımda indirilmeli; indirme kapalıyken yalnızca önbellek kullanılır.":
        "The local model has to be downloaded on first use; with downloading off, only the cached model is used.",
    "Yerel altyazıyı zaman çizelgesine ekle": "Add local captions to the timeline", "Seslendirme metni": "Voice-over text",
    "Windows sesiyle WAV oluştur": "Create a voice-over with a Windows voice", "Video ekleyin": "Add a video to begin",
    "Öneri {number}": "Suggestion {number}", "İz ekle": "Add track", "Tür": "Type", "Ses düzeyi (%)": "Volume (%)",
    "İşareti düzenle": "Edit marker", "Renk seçin veya işareti silin": "Choose a colour or delete the marker",
    "Otomatik algıla": "Detect automatically", "AI SAĞLAYICI": "AI PROVIDER",
    "Videonun başında görünecek kısa başlık": "A short title shown at the start of the video",
    "Enter'a basınca uygulanır; yazıyı silip Enter'a basınca başlık kalkar.": "Applied when you press Enter; clear the text and press Enter to remove the title.",
    "Başlık, videonun başına 3 saniyelik bir yazı klibi olarak eklenir; zaman çizelgesinde taşıyıp uzatabilirsiniz.":
        "The title is added as a 3-second text clip at the start of the video; you can move or lengthen it on the timeline.",
    "Başlık güncellendi.": "Title updated.", "Başlık kaldırıldı.": "Title removed.",
    "Başlık videonun başına eklendi.": "Title added at the start of the video.",
    "Koyu": "Dark", "Açık": "Light", "Arayüz dili": "Interface language", "Görünüm": "Appearance",
    "OYNATMA HIZI": "PLAYBACK SPEED", "ondalık ayırıcı: ,": "decimal separator: .",
    "Kırmızı": "Red", "Sarı": "Yellow", "Beyaz": "White", "Yeşil": "Green", "Mavi": "Blue", "Pembe": "Pink",
}
TR_UI = {english: turkish for turkish, english in EN_UI.items()}

# Stable keys (= canonical Turkish item texts) of the combos whose value is saved or compared in code.
ASPECTS = ("9:16 · Reels / Shorts", "16:9 · YouTube", "1:1 · Kare", "4:5 · Instagram gönderisi", "Kaynak oranı")
EXPORT_PROFILES = ("Reels · 1080×1920", "TikTok · 1080×1920", "YouTube · 1920×1080",
                   "4K Dikey · 2160×3840", "4K UHD · 3840×2160")
EFFECTS = ("Yok", "Sinematik", "Siyah-beyaz", "Yumuşak")
SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
DEFAULT_ASPECT = ASPECTS[0]
DEFAULT_EXPORT_PROFILE = EXPORT_PROFILES[0]


# English texts whose noun and verb change when {count} is 1 (Turkish keeps the noun singular after a number).
_EN_SINGULAR = {
    "{count} silent parts will be cut · {before} → {after} ({saved} s shorter)":
        "{count} silent part will be cut · {before} → {after} ({saved} s shorter)",
    "{count} silent parts were cut. You can undo it (Ctrl+Z).": "{count} silent part was cut. You can undo it (Ctrl+Z).",
    "{count} source files cannot be found ({names}); the export will stop because of this.":
        "{count} source file cannot be found ({names}); the export will stop because of this.",
    "The video has no picture in {count} places ({seconds} s in total, {places}); these will be black.":
        "The video has no picture in {count} place ({seconds} s in total, {places}); it will be black.",
    "{count} clips written.": "{count} clip written.",
    "{count} text and caption clips were left out.": "{count} text or caption clip was left out.",
    "{count} transitions were left out.": "{count} transition was left out.",
    "The speed of {count} clips was left out; they play at normal speed.":
        "The speed of {count} clip was left out; it plays at normal speed.",
    "The {total} video will be split into {count} parts: {lengths}": "The {total} video will stay in {count} part: {lengths}",
    "The {total} video will be split into {count} parts.": "The {total} video will stay in {count} part.",
    "{count} moments where the voice rises": "{count} moment where the voice rises",
    "New cut: {count} pieces, about {seconds} s": "New cut: {count} piece, about {seconds} s",
    "{count} transitions: {names}": "{count} transition: {names}",
    "{count} on-screen texts: {texts}": "{count} on-screen text: {texts}",
    "{count} marks (arrow / circle)": "{count} mark (arrow / circle)",
    "{count} punch-in zooms were removed.": "{count} punch-in zoom was removed.",
    "{count} punch-in zooms were added. You can undo it (Ctrl+Z).": "{count} punch-in zoom was added. You can undo it (Ctrl+Z).",
    "{count} cuts were put on the beat. You can undo it (Ctrl+Z).": "{count} cut was put on the beat. You can undo it (Ctrl+Z).",
    "{count} speakers found:": "{count} speaker found:",
    "{count} speaker changes were marked.": "{count} speaker change was marked.",
    "{count} filler words were cut. You can undo this (Ctrl+Z).": "{count} filler word was cut. You can undo this (Ctrl+Z).",
    "{count} filler words found ({seconds} s in all):": "{count} filler word found ({seconds} s in all):",
    "{count} retakes were cut. You can undo it (Ctrl+Z).": "{count} retake was cut. You can undo it (Ctrl+Z).",
    "{count} retakes found; only the last try of each will stay:": "{count} retake found; only its last try will stay:",
    "{count} caption clips were added.": "{count} caption clip was added.",
}


# Decimal separator: comma in Turkish ("1,5 sn"), point in English ("1.5 s"). Modules that only get a
# `say` function find it with decimal(value, say).
DECIMAL_KEY = "ondalık ayırıcı: ,"


def decimal(text: str, say=str) -> str:
    """A number already written with a point ('1.5', '0:03.5'), with the separator of `say`'s language."""
    return str(text).replace(".", say(DECIMAL_KEY)[-1])


class _Counted(str):
    """An English text that formats with its singular form when count=1 (callers just call .format)."""
    singular = ""

    def format(self, *args, **values):
        if values.get("count") == 1:
            return self.singular.format(*args, **values)
        return str.format(self, *args, **values)


def translate(source: str, code: str) -> str:
    """The text to show for a Turkish source string in language `code` ('tr' or 'en'); whole strings only."""
    if code != "en":
        return source
    text = EN_UI.get(source, source)
    if text in _EN_SINGULAR:
        text = _Counted(text)
        text.singular = _EN_SINGULAR[str(text)]
    return text


# Track names the program itself gives (stored in projects as they are) and how each language shows them.
TRACK_NAMES = {
    "Video": ("Video", "Video"), "Audio": ("Ses", "Audio"), "Ses": ("Ses", "Audio"),
    "Text": ("Yazı", "Text"), "Yazı": ("Yazı", "Text"), "Overlay": ("Katman", "Overlay"),
    "Altyazı / Captions": ("Altyazı", "Captions"), "Müzik": ("Müzik", "Music"),
}


def track_label(name: str, code: str) -> str:
    """The name shown on the timeline for a track: built-in names follow the language, the user's own stay."""
    if name in TRACK_NAMES:
        return TRACK_NAMES[name][1 if code == "en" else 0]
    return translate(name, code)


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


_qt_translator = None


def use_qt_language(code: str) -> bool:
    """Show Qt's own texts (Yes/No, OK/Cancel, Save/Discard, file dialog buttons) in `code` too.

    Qt is English by itself; for Turkish its qtbase_tr catalogue, shipped with PySide6, is installed on
    the application. Returns True when the catalogue for `code` is in use.
    """
    global _qt_translator
    from pathlib import Path
    from PySide6.QtCore import QCoreApplication, QLibraryInfo, QTranslator
    app = QCoreApplication.instance()
    if app is None:
        return False
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if code == 'en':
        return False
    translator = QTranslator(app)
    places = [QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)]
    try:
        import PySide6
        places.append(str(Path(PySide6.__file__).parent / 'translations'))
    except (ImportError, TypeError):
        pass
    for place in places:
        if place and translator.load(f'qtbase_{code}', place):
            app.installTranslator(translator)
            _qt_translator = translator
            return True
    return False


# Story Studio owns these strings; story content and model identifiers remain untouched.
STORY_EN = {
    'Hikâye Stüdyosu':
        'Story Studio',
    'Fikir ve rehber':
        'Idea and story bible',
    'Sahneler':
        'Scenes',
    'Görsel ve video':
        'Image and video',
    'Taslak':
        'Draft',
    'Final':
        'Final',
    'Modelleri denetle':
        'Check models',
    'Metin':
        'Text',
    'Kalite':
        'Quality',
    'Hikâyenin ana fikri: kim, ne istiyor, ne engel oluyor, nerede geçiyor…':
        'Story premise: who, what they want, what stands in their way, where it happens…',
    'Tür (ör. dram, polisiye, fantastik)':
        'Genre (e.g. drama, crime, fantasy)',
    'Ana fikir':
        'Premise',
    'Üslup':
        'Style',
    'Anlatıcı':
        'Point of view',
    'Anlatı zamanı':
        'Narrative tense',
    'Tür':
        'Genre',
    'Rehberi üret':
        'Generate story bible',
    'Taslak çıkar':
        'Generate outline',
    'Rehberdeki değişiklikleri uygula':
        'Apply story bible changes',
    'Hikâye rehberi (JSON; karakterlerin "visual" alanı görsellerde aynen kullanılır)':
        'Story bible (JSON; character "visual" fields are used verbatim in images)',
    'Boş sahne ekle':
        'Add empty scene',
    'Sahneyi sil':
        'Delete scene',
    'Metni sahnelere böl':
        'Split text into scenes',
    'Seçili sahnenin metnini model yardımıyla sahnelere ayırır.':
        'Split the selected scene text into scenes using AI.',
    'Sahne başlığı':
        'Scene title',
    'Talimat (isteğe bağlı): ne olsun, neye odaklanılsın…':
        'Instruction (optional): what should happen, what to focus on…',
    'Kelime':
        'Words',
    'Sahneyi yaz':
        'Write scene',
    'Hikâyenin sonuna yeni bir sahne yazar.':
        'Write a new scene at the end of the story.',
    'Devam et':
        'Continue',
    'Yeniden yaz':
        'Rewrite',
    'Uzat':
        'Extend',
    'Kısalt':
        'Shorten',
    'Sonra özeti güncelle':
        'Update summary afterwards',
    'İstemler (İngilizce; üretmeden önce düzenleyebilirsiniz)':
        'Prompts (English; edit before generating)',
    'İstemleri sahneden çıkar':
        'Extract prompts from scene',
    'Görsel istemi':
        'Image prompt',
    'Hareket ve ses istemi (video)':
        'Motion and sound prompt (video)',
    'Görsel':
        'Image',
    'Yok':
        'None',
    'Stil referansı seç':
        'Choose style reference',
    'Karakter referansları seç':
        'Choose character references',
    'Referansları temizle':
        'Clear references',
    'Bu sahnenin görselini üret':
        'Generate image for this scene',
    'En-boy':
        'Aspect ratio',
    'Boyut':
        'Size',
    'Görselden video üret':
        'Generate video from image',
    'Metinden video üret':
        'Generate video from text',
    'Süre':
        'Duration',
    'Çözünürlük':
        'Resolution',
    'Sonuç':
        'Result',
    'Görsel yok':
        'No image',
    'Video yok':
        'No video',
    'Görseli projeye ekle':
        'Add image to project',
    'Videoyu projeye ekle':
        'Add video to project',
    'Hazır.':
        'Ready.',
    'İptal':
        'Cancel',
    'Hikâyeyi kaydet':
        'Save story',
    'Hikâye aç':
        'Open story',
    'Kapat':
        'Close',
    'Edebi':
        'Literary',
    'Sade':
        'Plain',
    'Masalsı':
        'Fairy tale',
    'Gerilim':
        'Thriller',
    'Mizahi':
        'Humorous',
    'Üçüncü tekil sınırlı':
        'Third person limited',
    'Birinci tekil (ben)':
        'First person (I)',
    'Üçüncü tekil tanrısal':
        'Third person omniscient',
    'İkinci tekil (sen)':
        'Second person (you)',
    "Di'li geçmiş":
        'Simple past',
    'Şimdiki zaman':
        'Present',
    "Miş'li geçmiş (masal)":
        'Reported past (fairy tale)',
    'Hikâyede kaydedilmemiş değişiklikler var (üretilen sahneler dahil). Kaydedilsin mi?':
        'The story has unsaved changes (including generated scenes). Save them?',
    '"{title}" sahnesi silinsin mi? Bu işlem geri alınamaz.':
        'Delete scene "{title}"? This cannot be undone.',
    'Rehberdeki karakterler ve olay örgüsü yeni üretilen rehberle değiştirilecek; elle yaptığınız düzenlemeler kaybolur. Devam edilsin mi?':
        'The characters and plot in the story bible will be replaced with a newly generated bible; your manual edits will be lost. Continue?',
    'Rehber geçerli JSON değil; düzeltip tekrar uygulayın.':
        'The story bible is not valid JSON; correct it and apply again.',
    'Rehber güncellendi.':
        'Story bible updated.',
    'Adsız':
        'Untitled',
    'Önce süren işlemin bitmesini bekleyin.':
        'Wait for the current operation to finish first.',
    'Sonuç işlenemedi: {detail}':
        'Could not process result: {detail}',
    'Hikâye işlem sırasında değiştirildi; düzenlemeleriniz korundu. Sonucu uygulamak için işlemi yeniden başlatın.':
        'The story changed during generation; your edits were preserved. Run the operation again to apply a result.',
    'Hata: {detail}':
        'Error: {detail}',
    'İşlem iptal edildi; sonucu kullanılmayacak.':
        'Operation cancelled; its result will be discarded.',
    'İptal ediliyor…':
        'Cancelling…',
    'Gemini API anahtarı yok. Ana penceredeki AI ayarlarından Gemini anahtarını girin.':
        'No Gemini API key. Enter your Gemini key in the main window AI settings.',
    'Hikâye rehberi hazır. Gözden geçirip düzenleyebilirsiniz.':
        'Story bible ready. You can review and edit it.',
    'Olay örgüsü taslağı rehbere eklendi.':
        'Plot outline added to the story bible.',
    'Sahne hazır.':
        'Scene ready.',
    'Yanıt çıktı sınırında kesildi; metin eksik olabilir. "Devam et" ile tamamlayabilirsiniz.':
        'The response reached the output limit; the text may be incomplete. Use "Continue" to finish it.',
    '{prefix} Yedek model kullanıldı: {model}.':
        '{prefix} Fallback model used: {model}.',
    '{prefix} Özet ve süreklilik notları güncellendi.':
        '{prefix} Summary and continuity notes updated.',
    '{prefix} Özet güncellenemedi (geçersiz yanıt); eski notlar korundu.':
        '{prefix} Summary could not be updated (invalid response); previous notes were kept.',
    'Bölmek için metni bir sahneye yapıştırın ve o sahneyi seçin.':
        'Paste text into a scene and select it to split it.',
    'Metin {count} sahneye bölündü.':
        'Text split into {count} scenes.',
    'Görsel ve hareket istemleri hazır; üretmeden önce düzenleyebilirsiniz.':
        'Image and motion prompts ready; you can edit them before generating.',
    'Model listesi güncellendi.':
        'Model list updated.',
    '{prefix} Bu anahtarla görünmeyen: {models}':
        '{prefix} Unavailable with this key: {models}',
    'Modeller denetleniyor…':
        'Checking models…',
    'Görsel (*.png *.jpg *.jpeg *.webp)':
        'Images (*.png *.jpg *.jpeg *.webp)',
    'Önce bir sahne seçin.':
        'Select a scene first.',
    'Görsel kaydedildi: {path}':
        'Image saved: {path}',
    'Video kaydedildi: {path}':
        'Video saved: {path}',
    'Bu sahnenin görseli yok; önce görsel üretin ya da "Metinden video üret"i kullanın.':
        'This scene has no image; generate one first or use "Generate video from text".',
    'Eklenecek dosya yok; önce üretin.':
        'No file to add; generate one first.',
    'Projeye eklenemedi: {detail}':
        'Could not add to project: {detail}',
    'Ana pencere dosyayı eklemedi.':
        'The main window did not add the file.',
    'Projeye eklendi: {path}':
        'Added to project: {path}',
    'Kaydedilemedi: {detail}':
        'Could not save: {detail}',
    'Hikâye kaydedildi: {path}':
        'Story saved: {path}',
    'Hikâye açıldı: {path}':
        'Story opened: {path}',
    'Hikâye (*.hikaye.json *.json)':
        'Story (*.hikaye.json *.json)',
    'Bu hikâye dosyasının sürümü desteklenmiyor.': 'This story file version is unsupported.',
    'Hikâye dosyası geçersiz.':
        'Invalid story file.',
    'Hikâye dosyası okunamadı: {detail}':
        'Could not read story file: {detail}',
    'Önce hikâyenin ana fikrini yazın.':
        'Write the story premise first.',
    'Model geçerli bir hikâye rehberi döndürmedi; tekrar deneyin.':
        'The model did not return a valid story bible; try again.',
    'Model geçerli bir taslak döndürmedi; tekrar deneyin.':
        'The model did not return a valid outline; try again.',
    'Sahne bulunamadı.':
        'Scene not found.',
    'Devam edilecek metin yok; önce sahneyi yazın.':
        'No text to continue; write the scene first.',
    'Bilinmeyen yeniden yazma biçimi: {mode}':
        'Unknown rewrite mode: {mode}',
    'Yeniden yazılacak metin yok.':
        'No text to rewrite.',
    'Sahne artık yok.':
        'The scene no longer exists.',
    'Bölünecek metin en az iki paragraf olmalı.':
        'Text to split must contain at least two paragraphs.',
    'Görsel istemi için önce sahne metni gerekli.':
        'Scene text is required before creating an image prompt.',
    'fiyat bilinmiyor':
        'price unknown',
    'fiyat belgelenmedi':
        'price undocumented',
    'Tahmini maliyet: {cost} (1 görsel, {model}, {size})':
        'Estimated cost: {cost} (1 image, {model}, {size})',
    'Tahmini maliyet: {cost} ({model}, {resolution}, {seconds} sn)':
        'Estimated cost: {cost} ({model}, {resolution}, {seconds} s)',
    'Tahmini video çıktı maliyeti: {cost} + girdi/metin/düşünme; ücretli katman ({model}, {resolution}, {seconds} sn)':
        'Estimated video output cost: {cost} + input/text/thinking; paid tier ({model}, {resolution}, {seconds} s)',
    '{cost} — görsel üretiliyor…':
        '{cost} — generating image…',
    '{cost} — video üretiliyor; birkaç dakika sürebilir…':
        '{cost} — generating video; this may take a few minutes…',
    'Görsel — {image} · Video — {video}':
        'Image — {image} · Video — {video}',
    'Görsel üretiliyor ({model}, {size})…':
        'Generating image ({model}, {size})…',
    'Video üretiliyor ({model}, {resolution}, {seconds} sn); bu birkaç dakika sürebilir…':
        'Generating video ({model}, {resolution}, {seconds} s); this may take a few minutes…',
    '{prefix} — {seconds} sn':
        '{prefix} — {seconds} s',
    'Sahne yazılıyor':
        'Writing scene',
    'Sahneye devam ediliyor':
        'Continuing scene',
    'Sahne yeniden yazılıyor':
        'Rewriting scene',
    'Özet ve süreklilik notları güncelleniyor':
        'Updating summary and continuity notes',
    'Görsel istemi hazırlanıyor':
        'Preparing image prompt',
    'Hikâye rehberi oluşturuluyor':
        'Creating story bible',
    'Olay örgüsü taslağı çıkarılıyor':
        'Generating plot outline',
    'Metin sahnelere bölünüyor':
        'Splitting text into scenes',
    'Metin üretiliyor':
        'Generating text',
    '{prefix} ({model})…':
        '{prefix} ({model})…',
    'Token: {prompt} girdi{cached} · {output} çıktı ({thoughts} düşünme) · {cost} · {model}':
        'Tokens: {prompt} input{cached} · {output} output ({thoughts} thinking) · {cost} · {model}',
    ' ({count} önbellek)':
        ' ({count} cached)',
    '{prefix} (yedek model; {reason})':
        '{prefix} (fallback model; {reason})',
    'Plan / taslak / özet':
        'Plan / outline / summary',
    'Sahne yazımı':
        'Scene writing',
    'Son görsel':
        'Final image',
    'Hızlı küçük resim':
        'Quick thumbnail',
    'Premium görsel':
        'Premium image',
    'Video önizleme':
        'Video preview',
    'Son video':
        'Final video',
    'En hızlı/ucuz; çoklu referansta zayıf':
        'Fastest/cheapest; weak with multiple references',
    '≈0,134 $/görsel; yalnızca istenirse':
        '≈$0.134/image; only on request',
    '≈0,050 $/görsel':
        '≈$0.050/image',
    '≈0,070 $/sn çıktı + girdi; ücretli katman':
        '≈$0.070/s output + input; paid tier',
    '≈0,104 $/sn çıktı + girdi; ücretli katman':
        '≈$0.104/s output + input; paid tier',
    '720p, 5–8 sn':
        '720p, 5–8 s',
    'Çıktı klasörü belirlenmemiş.':
        'No output folder selected.',
    'Taslak sahne, deneme, devam':
        'Draft scene, trial, continuation',
    'medium (hızlı denemede low)':
        'medium (low for quick trials)',
    'Ucuz, hızlı, ücretsiz katmanı var':
        'Cheap, fast, free tier available',
    'Son okuma, cilalama, karmaşık olay örgüsü':
        'Proofreading, polishing, complex plots',
    'Daha tutarlı ve derin; ücretsiz katmanı yok':
        'More consistent and deeper; no free tier',
    'Özet, süreklilik, görsel istemi':
        'Summary, continuity, image prompt',
    'Kısa, yapılandırılmış iş':
        'Short, structured tasks',
    'Görsel taslağı':
        'Draft image',
    '≈0,034 $/görsel':
        '≈$0.034/image',
    'API anahtarı ve model gereklidir.':
        'An API key and model are required.',
    'API anahtarı gereklidir.':
        'An API key is required.',
    'Görsel istemi boş olamaz.':
        'The image prompt cannot be empty.',
    'Video istemi boş olamaz.':
        'The video prompt cannot be empty.',
    'İstek metni boş olamaz.':
        'Request text cannot be empty.',
    'Desteklenmeyen görsel türü: {name} (PNG, JPEG ya da WEBP seçin).':
        'Unsupported image type: {name} (choose PNG, JPEG or WEBP).',
    '{name}: desteklenmeyen görsel türü ({mime}).':
        '{name}: unsupported image type ({mime}).',
    '{name}: görsel dosyası boş.':
        '{name}: the image file is empty.',
    '{name}: görsel çok büyük (en fazla {limit} MB).':
        '{name}: image too large (maximum {limit} MB).',
    'Referans görsellerin toplamı çok büyük (en fazla {limit} MB).':
        'Reference images are too large in total (maximum {limit} MB).',
    'Geçersiz düşünme düzeyi: {level} (low, medium ya da high).':
        'Invalid thinking level: {level} (low, medium or high).',
    'Çıktı sınırı 1 ile {limit} token arasında olmalı.':
        'The output limit must be between 1 and {limit} tokens.',
    'Geçersiz rol: {role}':
        'Invalid role: {role}',
    'Geçersiz en-boy oranı: {ratio}. Geçerli değerler: {values}.':
        'Invalid aspect ratio: {ratio}. Valid values: {values}.',
    '"512" boyutu yalnızca gemini-3.1-flash-image modelinde kullanılabilir.':
        'The "512" size is only available with gemini-3.1-flash-image.',
    'Geçersiz görsel boyutu: {size} (1K, 2K ya da 4K; büyük K harfiyle).':
        'Invalid image size: {size} (1K, 2K or 4K; with an uppercase K).',
    'En fazla {limit} referans görsel gönderilebilir.':
        'You can submit at most {limit} reference images.',
    'En fazla {limit} karakter referansı gönderilebilir.':
        'You can submit at most {limit} character references.',
    'En fazla {limit} nesne/stil referansı gönderilebilir.':
        'You can submit at most {limit} object/style references.',
    'Video için en-boy oranı 16:9 ya da 9:16 olmalı.':
        'Video aspect ratio must be 16:9 or 9:16.',
    'Geçersiz çözünürlük: {resolution} ({values}).':
        'Invalid resolution: {resolution} ({values}).',
    'Video süresi {range} arası tam saniye olmalı.':
        'Video duration must be a whole number of seconds between {range}.',
    'Videoya en fazla {limit} görsel eklenebilir.':
        'You can add at most {limit} images to a video.',
    'İlk ve son kare modu tam iki görsel ister.':
        'First and last frame mode requires exactly two images.',
    'İlk/son kare modunda süre en fazla {limit} saniye olabilir.':
        'First/last frame mode supports at most {limit} seconds.',
    'delivery "inline" ya da "uri" olmalı.':
        'delivery must be "inline" or "uri".',
    '{provider} beklenmeyen bir yanıt döndürdü; daha sonra tekrar deneyin.':
        '{provider} returned an unexpected response; try again later.',
    '{provider} boş yanıt döndürdü. Tekrar deneyin ya da başka bir model seçin.':
        '{provider} returned an empty response. Try again or choose another model.',
    '{provider} yanıtı çıktı sınırına takıldı ve yarıda kesildi (düşünme tokenları da bu sınıra dahildir).':
        '{provider} reached the output limit and the response was truncated (thinking tokens count toward this limit).',
    '{provider} bozuk görsel verisi döndürdü.':
        '{provider} returned invalid image data.',
    '{provider} görseli tamamlayamadı (çıktı sınırı).':
        '{provider} could not complete the image (output limit).',
    '{provider} görsel döndürmedi{note}. İstemi değiştirip tekrar deneyin.':
        '{provider} returned no image{note}. Change the prompt and try again.',
    '{provider} {seconds} saniyede görsel döndürmedi. Tekrar denemeden önce birkaç dakika bekleyin.':
        '{provider} returned no image within {seconds} seconds. Wait a few minutes before trying again.',
    '{provider} video döndürmedi{note}. Bu genellikle içerik engeli ya da bölgesel kısıtlama demektir; istemi değiştirip tekrar deneyin.':
        '{provider} returned no video{note}. This usually indicates a content block or regional restriction; change the prompt and try again.',
    '{provider} tanınmayan bir video adresi döndürdü.':
        '{provider} returned an unrecognized video address.',
    '{provider} video dosyasını hazırlayamadı.':
        '{provider} could not prepare the video file.',
    '{provider} video dosyası {seconds} saniyede hazır olmadı.':
        '{provider} video file was not ready within {seconds} seconds.',
    '{provider} video dosyası indirilemedi: {detail}':
        '{provider} video file could not be downloaded: {detail}',
    '{provider} model listesi alınamadı: {detail}':
        '{provider} model list could not be retrieved: {detail}',
    'Video {seconds} saniyede tamamlanmadı. Ücretlendirilmiş olabileceği için otomatik olarak tekrar denenmedi; Google AI Studio kullanımınızı kontrol edip sonra tekrar deneyin.':
        'The video did not finish within {seconds} seconds. It was not retried automatically because it may have been billed; check your Google AI Studio usage before trying again.',
    '{provider} boş video dosyası döndürdü.':
        '{provider} returned an empty video file.',
    '{model} ücretsiz katmanda kullanılamıyor':
        '{model} unavailable on the free tier',
    '{model} bulunamadı':
        '{model} not found',
    '{model} istek sınırına takıldı':
        '{model} rate limited',
    '{model} yoğun (HTTP {code})':
        '{model} busy (HTTP {code})',
    '{model} zamanında yanıt vermedi':
        '{model} did not respond in time',
    '{detail}\n(Önce denenen: {reason})':
        '{detail}\n(Previously tried: {reason})',
}


def story_text(source, code):
    """Translate Story-owned display messages, preserving interpolated paths and user content.

    Workers/services keep their Turkish message contract. Match only complete known templates;
    recurse only into fields explicitly carrying another application message.
    """
    if code != 'en':
        return source
    if source in STORY_EN:
        return STORY_EN[source]
    # Usage includes a free-form model/reason tail; peel its known suffix before matching
    # the token line so the model placeholder cannot swallow the fallback annotation.
    if source.endswith(')') and ' (yedek model; ' in source:
        prefix, reason = source.rsplit(' (yedek model; ', 1)
        return story_text(prefix, code) + ' (fallback model; ' + '; '.join(story_text(item, code) for item in reason[:-1].split('; ')) + ')'
    import re
    import string
    for suffix in (' Özet ve süreklilik notları güncellendi.',
                   ' Özet güncellenemedi (geçersiz yanıt); eski notlar korundu.'):
        if source.endswith(suffix):
            prefix = source[:-len(suffix)]
            return STORY_EN['{prefix}' + suffix].format(prefix=story_text(prefix, code))
    for template, english in sorted(STORY_EN.items(), key=lambda item: len(item[0]), reverse=True):
        if '{' not in template:
            continue
        parts = list(string.Formatter().parse(template))
        pattern = ''.join(re.escape(literal) + (f'(?P<{field}>.*?)' if field else '')
                          for literal, field, _, _ in parts)
        match = re.fullmatch(pattern, source, re.DOTALL)
        if match:
            values = match.groupdict()
            for key in ('prefix', 'detail', 'cost', 'image', 'video', 'cached', 'reason'):
                if key in values:
                    values[key] = story_text(values[key], code)
            return english.format(**values)
    return translate(source, code)


EN_UI.update({
    'Seçilen mikrofon ekran kaydı için bulunamadı; başka bir mikrofon seçin veya mikrofonsuz kaydedin.':
        'The selected microphone could not be found for screen recording; choose another microphone or record without one.',
    'Kurgu ayarları veya içerik bu sırada değişti. Plan yine de uygulansın mı?':
        'The edit settings or content changed while the request was running. Apply the plan anyway?',
    '＋ Müzik':
        '＋ Music',
    'Ses dosyası seçip zaman çizelgesinin ses izine ekler.':
        'Choose an audio file and add it to the timeline’s audio track.',
    'Bir ses klibi seçin; bu düzey dışa aktarılan videoda da kullanılır.':
        'Select an audio clip; this level is also used in the exported video.',
    'Müzik zaman çizelgesine eklendi.':
        'Music added to the timeline.',
    'Görsel klibe dönüştürülemedi: {error}':
        'Could not convert image to a clip: {error}',
    'Medya seç':
        'Select media',
    'Müzik seç':
        'Select music',
    'Ses dosyaları (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma);;Tüm dosyalar (*.*)':
        'Audio files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma);;All files (*.*)',
    'Ses ya da video klibini seçin; düzeyi dışa aktarılan videoya da uygulanır.':
        'Select an audio or video clip; its volume level also applies to the export.',
})
TR_UI.update({english: turkish for turkish, english in EN_UI.items()})
EN_UI.update({
    'Medya dosyaları (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.png *.jpg *.jpeg *.webp *.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma);;Tüm dosyalar (*.*)':
        'Media files (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.png *.jpg *.jpeg *.webp *.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma);;All files (*.*)',
    'Fotoğraf 5 saniyelik klip olarak eklendi.': 'Photo added as a 5-second clip.',
    'Ses düzeyi artışlarında yakınlaştır': 'Punch in on loudness peaks',
    'Kaynak sesindeki belirgin ses düzeyi artışlarında görüntü kısa süre yakınlaşır; müzik vuruşları da bunu tetikleyebilir. Yeniden basınca kaldırmayı sorar; internet gerekmez.':
        'The picture briefly zooms in on strong loudness peaks in the source audio; music peaks can trigger it too. Press again to be asked about removing them; no internet needed.',
    'Ses düzeyi artışlarında yakınlaştırmalar var. Kaldırılsın mı?': 'There are loudness-peak zooms on the video. Remove them?',
    '{count} ses düzeyi artışı yakınlaştırması kaldırıldı.': '{count} loudness-peak zooms were removed.',
    'Kaynak sesindeki ani ses düzeyi artışları aranıyor…': 'Looking for loudness peaks in the source audio…',
    'Belirgin ses düzeyi artışı bulunamadı.': 'No clear loudness peak was found.',
    '{count} ses düzeyi artışı anında yakınlaştırma eklendi. Beğenmezseniz geri alabilirsiniz (Ctrl+Z).':
        '{count} punch-in zooms were added on loudness peaks. You can undo it (Ctrl+Z).',
    'Analiz işlemi sonuç vermeden kapandı.': 'Analysis finished without a result.',
})
TR_UI.update({english: turkish for turkish, english in EN_UI.items()})

# Messages the window used to show in Turkish only, and finding moved media when a project opens.
EN_UI.update({
    'Desteklenen bir video dosyası seçin.': 'Choose a supported video file.',
    'Proje açılamadı: {error}': 'The project could not be opened: {error}',
    'Dışa aktarma boyutu belirlenemedi: {error}': 'The export size could not be determined: {error}',
    'Çıktı yolu kaynak medya ile aynı olamaz; başka bir dosya adı seçin.':
        'The output cannot be the same file as the source media; choose another file name.',
    '“{name}” zaten var. Üzerine yazılsın mı?': '“{name}” already exists. Replace it?',
    'Önce videoyu nasıl kurgulamak istediğinizi yazın.': 'First write how you want the video edited.',
    'Video okunamadı: {error}': 'The video could not be read: {error}',
    'Kurgulanacak video dosyası bulunamadı.': 'No video file to edit was found.',
    '{provider} için API anahtarı ve modeli girin.': 'Enter the API key and model for {provider}.',
    '“{name}” izi ve içindeki {count} klip silinsin mi? Ctrl+Z ile geri alabilirsiniz.':
        'Delete the track “{name}” and the {count} clips on it? You can undo it with Ctrl+Z.',
    'Beklenmeyen bir hata oluştu: {error}': 'An unexpected error occurred: {error}',
    'Ayrıntılar günlük dosyasına yazıldı:\n{path}': 'Details were written to the log file:\n{path}',
    '{count} medya dosyası yeni yerinden bağlandı; kalıcı olması için projeyi kaydedin.':
        '{count} media files were linked from their new location; save the project to keep this.',
    'Projede kullanılan şu medya dosyaları bulunamadı:\n{names}\n\n'
    'Proje açıldı; bu dosyaları kullanan klipler önizlemede ve dışa aktarmada eksik kalabilir.':
        'These media files used in the project were not found:\n{names}\n\n'
        'The project was opened; clips that use them may be missing from the preview and the export.',
    'Projede kullanılan {count} medya dosyası bulunamadı:\n{names}\n\nTaşındılarsa yeni yerlerini göstermek ister misiniz?':
        '{count} media files used in the project were not found:\n{names}\n\nIf they were moved, do you want to show where they are now?',
    '“{name}” dosyasını bulun': 'Locate “{name}”',
    'Akış projesi (*.akis.json);;JSON (*.json)': 'Akış project (*.akis.json);;JSON (*.json)',
    '◯ daire': '◯ circle',
    '➜ ok': '➜ arrow',
})
_EN_SINGULAR.update({
    'Delete the track “{name}” and the {count} clips on it? You can undo it with Ctrl+Z.':
        'Delete the track “{name}” and the {count} clip on it? You can undo it with Ctrl+Z.',
    '{count} media files were linked from their new location; save the project to keep this.':
        '{count} media file was linked from its new location; save the project to keep this.',
    '{count} media files used in the project were not found:\n{names}\n\nIf they were moved, do you want to show where they are now?':
        '{count} media file used in the project was not found:\n{names}\n\nIf it was moved, do you want to show where it is now?',
})
TR_UI.update({english: turkish for turkish, english in EN_UI.items()})

EN_UI.update({'Seslendirmeyi kaydet': 'Save the voice-over'})
TR_UI.update({english: turkish for turkish, english in EN_UI.items()})
