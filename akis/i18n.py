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
    "Klip sesi": "Clip volume", "Metni düzenle": "Edit text", "Yakınlık": "Zoom",
    "API transkripsiyon modeli": "API transcription model",
    "Çevrimdışı Windows sistem sesi kullanılır; dil ve ses işletim sisteminde yüklü seslere bağlıdır.":
        "Uses the offline Windows system voice; the language and voice depend on the voices installed in Windows.",
    "Temel gürültü azaltma (henüz yok)": "Basic noise reduction (not available yet)",
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
