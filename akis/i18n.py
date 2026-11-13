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
    'Video ekleyin': 'Add your video',
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
    '{count} klip yazıldı.': '{count} clips written.',
    '{count} yazı ve altyazı klibi aktarılmadı.': '{count} text and caption clips were left out.',
    '{count} geçiş aktarılmadı.': '{count} transitions were left out.',
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
