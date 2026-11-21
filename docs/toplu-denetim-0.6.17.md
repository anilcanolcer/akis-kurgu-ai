# Akış Kurgu AI 0.6.17 tam kapsamlı denetimi

Başlangıç noktası 0.6.16 (`e731fe3`). Windows 11, Python 3.12 ve FFmpeg 9.0.2 kullanıldı. Bu bilgisayarda iki ekran var, kamera ve mikrofon yok.

0.6.16 denetimi, zaman çizelgesi ve dışa aktarılan görüntü için kural tabanlı tarama getirdi. Bu tur aynı yöntemi programın geri kalanına uyguladı. Programdaki 88 dosyanın her biri aşağıdaki listede yer alıyor. Her dosyanın yanında onu hangi testin ve hangi kural denetleyicisinin sınadığı ya da neden sınanamadığı yazıyor.

## Kural denetleyicileri

Her denetleyici rastgele girdi üretir ve sonucu yazılı kurallarla karşılaştırır. Hepsi `scripts/media-audit` klasöründe. Her GitHub Windows derlemesinde çalışır; bir kural bozulursa sürüm yayımlanmaz.

| Denetleyici | Ne üretir | Kural | Bu turdaki çalıştırma | Derlemede |
| --- | --- | --- | --- | --- |
| `fuzz.py` (0.6.16) | Rastgele proje ve sekize kadar düzenleme | Her karede gösterilen kaynak, ses düzeyi, kelime, geçiş ve işaret, işlemin söz verdiği gibi kalır. | 10.000 proje | 2.000 |
| `render_fuzz.py` (0.6.16) | Rastgele kurgular, FFmpeg ile dışa aktarılır | Çıktının ve önizlemenin her karesi modelin söylediği kaynak karesidir. | 80 kurgu | 30 |
| `audio_fuzz.py` | Her kaynak karesi kendi perdesinde ses taşır; kurgu dışa aktarılır | Her çıktı karesinde duyulması gereken her klip doğru kaynak anından ve kendi ses düzeyinde duyulur. Sessiz olması gereken duyulmaz. Kapatılmış iz ve sessiz klip duyulmaz. Ses, görüntü kadar sürer. | 240 kurgu | 40 |
| `ai_fuzz.py` | Bozuk, yarım, uç değerli yapay zekâ yanıtları; rastgele konuşma dökümleri | Plan okuyucu yalnız anlaşılır bir hatayla reddeder; kabul ettiği her değer sınır içindedir. Plan uygulanınca zaman çizelgesi geçerlidir. Altyazı, dolgu sözcüğü, tekrar, konuşmacı, ritim ve vurgu sonuçları kendi kliplerinin içindedir. | 60.000 durum | 10.000 |
| `preview_fuzz.py` | Rastgele düzenlemeler | Akıcı önizlemenin parçaları kurguyu boşluksuz örter; birleşince bütünle aynıdır. Değişen parça eski önizleme parçasıyla karışmaz. Canlı oynatmada duyulan her ses modeldeki klipten ve doğru andan gelir. | 3.000 proje | 1.000 |
| `window_fuzz.py` | Gerçek ana pencerede rastgele düzenleme oturumları | Bölme, kırpma, silme, aralık silme, ses, hız, kadraj, iz ekleme/silme ve fareyle sürükleme hata vermez. Her değişiklik tek geri alma adımıdır. Hepsi geri alınınca proje açıldığı haline, hepsi yinelenince son haline döner. Kaydedip açınca aynıdır. | 300 oturum | 100 |
| `store_fuzz.py` | Rastgele hikâye, şablon ve sürüm etiketi | Hikâye kaydedilip açılınca aynıdır; bozuk dosya anlaşılır hatayla reddedilir. Şablon dosyası beklenen listeyi tutar. Güncelleme yalnız daha yeni bir x.y.z sürüm için önerilir. | 6.000 durum | 1.500 |

Her denetleyicinin gerçekten hata yakaladığı, programa bilerek hata koyularak denendi. Ses denetleyicisi örnek olarak hızlı kliplerde ses hızının değişmemesini 6 projenin 5'inde, ses düzeyinin yok sayılmasını 6'nın 5'inde, 120 ms ses gecikmesini 6'nın 6'sında yakaladı. Kapatılmış izin duyulması bu yolla sınanamadı: program kapatılmış izi iki ayrı yerde dışarıda bırakıyor ve konulan hata yalnız birini kaldırdı. Pencere denetleyicisi 12 oturumda 104 gerçek değişiklik yaptı; her işlem türü en az bir kez denendi.

## Bulunan ve düzeltilen sorunlar

| Alan | 0.6.16'da gözlenen | 0.6.17 |
| --- | --- | --- |
| Kayıt al: ekran kaydı | Kayıt penceresinin küçültme düğmesi yoktu ve ana programı kilitliyordu. Kayıt sırasında program ekrandan kaldırılamıyordu; oysa pencerenin kendi metni "bu pencereyi küçültüp" diyordu. | Kayıt başlayınca program ve kayıt penceresi küçülür. Ekranın üstünde süreyi ve "■ Durdur ve ekle" düğmesini gösteren küçük bir çubuk açılır. Windows'a bu çubuğu kayda katmaması söylenir; bu bilgisayarda doğrulandı. İki ekran varsa çubuk kaydedilmeyen ekranda durur. Pencereye küçültme düğmesi eklendi. |
| Kayıt al: pencereyi kapatma | Kayıt sürerken Esc tuşu ya da başlık çubuğundaki X kaydı sessizce durdurup siliyor, "Kaydı başlat" yeniden görünüyordu. | Esc kayıt sırasında bir şey yapmaz. X ve Alt+F4 ne yapılacağını sorar: durdurup eklemek, kaydı silmek ya da kayda devam etmek. |
| Kayıt al: önizleme | Ekran seçildiğinde yalnız yazı görünüyordu. | Seçilen ekranın canlı görüntüsü pencerede görünür. |
| Kayıt al: FFmpeg'in kendiliğinden durması | FFmpeg hata yazmadan durursa pencere "Kaydediliyor…" durumunda takılı kalıyordu. | Durum sıfırlanır; çıkış koduyla birlikte neden yazılır. |
| Kayıt al: kayıt klasörü | Videolar klasöründe "Akış Kurgu kayıtları" oluşturulamazsa (korumalı klasör, güvenlik yazılımı) hata açıklanmıyordu. | Klasör yolu ve neden yazılır. |
| Yapay zekâ kurgu planı | Planın tuttuğu bölüm hızlı ya da yavaş bir klibin kare altı bir parçasına düşünce plan uygulanamıyor, `TypeError` hatası çıkıyordu. | Sıfır uzunluklu parça yok sayılıyor; plan uygulanıyor. |
| Dışa aktarılan ses: yavaş klip | Yavaşlatılmış klibin sesinin son 50-70 ms'si kayboluyordu; birkaç karelik yavaş bir klibin sesi tümden kaybolabiliyordu. Sebep, FFmpeg'in tempo filtresinin tam pencereyi doldurmayan son parçayı atmasıydı. | Ses tempo değişiminden önce sessizlikle uzatılıp sonra klibin uzunluğuna kesiliyor. 40 yeni projenin 11'inde görülen fark kalmadı. Sondaki 50-70 ms'lik kısma inen ses, zaman germenin doğası gereği hâlâ yumuşakça kısılır. |
| Dışa aktarılan ses: uzunluk | Kurgu sessizlikle ya da boşlukla bitince dosyanın ses izi görüntüden 60-170 ms kısa kalıyordu. | Ses, görüntü kadar sürüyor. |
| Konuşmacı işaretçileri | Hızı değiştirilip bölünmüş bir klibin ilk kare kesrine düşen konuşmacı değişimi videonun başından önceye, -1. kareye konuyordu. | İşaretçi klibin içinde kalıyor. |

Kayıt sorunları bu bilgisayarda kurulu sürümle yeniden üretildi. Kurulu program arayüz otomasyonuyla açıldı ve "Kayıt al" ile "Kaydı başlat" düğmelerine basıldı. Kaydın kendisi çalışıyordu: 5,2 saniyelik, oynatılabilir bir dosya oluştu. Kullanılamaz hale getiren, pencerenin ekrandan kaldırılamaması ve kapatma tuşlarının kaydı sessizce silmesiydi. Yeni akış iki gerçek ekranla, uygulamadaki gibi kilitli pencereyle denendi: program ve pencere küçüldü, çubuk diğer ekranda göründü, çubuktan durdurunca 3,6 saniyelik kayıt eklendi.

Her düzeltme için test var: `tests/test_record.py` (StayingAwayTests, 6 test) ve `tests/test_full_audit_20261121.py` (3 test). Dokuz testin dokuzu 0.6.16 koduyla başarısız oluyor.

### 0.6.16 raporunda düzeltme

0.6.16 raporu altyazı kenarındaki kelime kaybının "kenar tek sürüklemede ileri geri hareket ettirilince de" oluştuğunu söylüyordu. Bu yanlıştı. Zaman çizelgesi sürükleme sırasında her harekette klibin özgün halinden başlar; kayıp, kenar bırakılıp ayrı bir sürüklemeyle geri getirildiğinde oluşuyordu. 0.6.16'nın düzeltmesi bu durumu kapsıyor; raporun metni düzeltildi.

## Sorun bulunmayan alanlar

- Dışa aktarılan seste senkron, ses düzeyi, müzik izi ve Shorts parçası (yavaş kliplerin sonu ve ses uzunluğu dışında).
- Yapay zekâ planlarının okunması ve uygulanması (bulunan çökme dışında), altyazı üretimi, dolgu sözcüğü, tekrar, ritim ve vurgu.
- Akıcı önizleme parçaları, parça yeniden kullanımı, canlı oynatmada ses seçimi.
- Ana penceredeki düzenleme işlemleri, fareyle sürükleme, geri alma ve yineleme, kaydetme ve açma.
- Hikâye Stüdyosu dosyaları, kişisel şablonlar, güncelleme sürüm karşılaştırması.

Canlı oynatmanın Qt tarafı (`timeline_audio`, `window/playback`) otomatik denetlenemediği için satır satır okundu. Sesin oynatma çizgisindeki klibi izlemesinde, hız ve ses değişiminin aktarılmasında ve kare kare oynatmadan akıcı kopyaya geçişte hata bulunmadı.

## Denetlenemeyenler

Bunları bu bilgisayarda doğrulamak mümkün değil. Sonraki bir analizde bulunacak bir sorun ya bu listeden ya da yeni eklenen koddan gelir.

- Gerçek ücretli yapay zekâ yanıtlarının içeriği (OpenAI, Gemini, xAI, Cloudflare). Yanıtların biçimi ve hataları taklitle sınanır.
- Kamera ve mikrofonla kayıt: bu bilgisayarda kamera ve mikrofon yok. Bu yollar yalnız testlerle sınanır.
- Sesin kulakla duyulan kalitesi (gürültü azaltma, ses dengeleme), Windows seslendirmesinin doğallığı.
- Whisper'ın uzun, gürültülü ya da çok kişili gerçek kayıtlardaki doğruluğu ve konuşmacı ayırmanın gerçek kayıtlardaki başarısı.
- FCPXML'in Final Cut Pro ve DaVinci Resolve içinde açılması.
- Farklı ekran kartı, sürücü, ekran ölçeklendirmesi ve güvenlik yazılımlarıyla davranış.

## Dosya dosya kapsam

"Test dosyası", dosyayı doğrudan ya da ana pencere üzerinden kullanan test dosyalarının sayısıdır. Genel test kümesi 1.059 testtir.

| Dosya | Satır | Test dosyası | Kural denetleyicisi | Not |
| --- | ---: | ---: | --- | --- |
| `ai_providers` | 655 | 15 | yapay zekâ/konuşma | Sağlayıcı yanıtları testlerde taklit edilir; gerçek ücretli yanıt denetlenmez. |
| `ai_service` | 189 | 5 | konuşma projesi |  |
| `ai_workers` | 285 | 6 | — |  |
| `analysis_cache` | 78 | 1 | — |  |
| `app_support` | 226 | 53 | pencere |  |
| `audio_diagnostic` | 53 | 0 | — | Paket ses tanılaması GitHub derlemesinde çalıştırılır. |
| `audio_polish` | 61 | 1 | — |  |
| `batch_dialog` | 97 | 1 | — |  |
| `batch_export` | 137 | 1 | — |  |
| `beat_sync` | 101 | 2 | kurgu araçları, yapay zekâ/konuşma |  |
| `call_worker` | 23 | 2 | — |  |
| `caption_layout` | 64 | 1 | — |  |
| `caption_service` | 80 | 7 | gerçek medya, konuşma projesi, yapay zekâ/konuşma |  |
| `caption_worker` | 16 | 0 | — | İnce arka plan işi; caption_service üzerinden sınanır. |
| `chunk_preview` | 103 | 1 | önizleme |  |
| `clip_fit` | 74 | 4 | pencere |  |
| `edit_plan` | 1275 | 11 | görüntü, kesim matrisi, kurgu araçları, model, ses, yapay zekâ/konuşma, çok iz |  |
| `emphasis` | 103 | 2 | yapay zekâ/konuşma |  |
| `export_progress` | 84 | 7 | — |  |
| `fast_export` | 138 | 2 | gerçek medya, önizleme/dışa aktarma |  |
| `fcpxml_export` | 177 | 3 | gerçek medya, konuşma projesi | XML yapısı ve zamanlar testlerle; Final Cut Pro ve DaVinci Resolve içinde açılış denetlenmedi. |
| `fillers` | 102 | 1 | yapay zekâ/konuşma |  |
| `frame_plan` | 38 | 2 | — |  |
| `gemini_api` | 608 | 6 | — | Gemini yanıtları testlerde taklit edilir; gerçek ücretli üretim denetlenmez. |
| `highlights` | 111 | 2 | kurgu araçları |  |
| `highlights_dialog` | 65 | 1 | — |  |
| `i18n` | 1385 | 17 | — | Dil anahtarları testi her Türkçe metnin İngilizcesini denetler. |
| `inspiration_dialog` | 356 | 3 | — |  |
| `inspiration_en` | 182 | 1 | — | Metin; dil testleri. |
| `inspiration_service` | 213 | 3 | — |  |
| `media_bin` | 15 | 1 | — | Testler. |
| `media_service` | 246 | 53 | gerçek medya, görüntü, kare zamanlaması, konuşma projesi, kurgu araçları, pencere, ses, çok iz, önizleme/dışa aktarma |  |
| `messages` | 187 | 1 | — | Testler. |
| `multi_export` | 66 | 1 | — |  |
| `multitrack_widget` | 371 | 53 | pencere |  |
| `plan_review` | 130 | 1 | yapay zekâ/konuşma |  |
| `preflight` | 74 | 3 | — | Testler. |
| `preview_controller` | 91 | 53 | pencere |  |
| `preview_widget` | 329 | 5 | gerçek medya |  |
| `privacy_log` | 54 | 2 | — | Testler. |
| `project_service` | 365 | 10 | gerçek medya, konuşma projesi, pencere |  |
| `record_dialog` | 495 | 1 | — | Gerçek ekran kaydı bu bilgisayarda iki ekranla denendi. Kamera ve mikrofon bu bilgisayarda yok; o yollar yalnız testlerle. |
| `render_worker` | 54 | 4 | — |  |
| `retakes` | 109 | 2 | yapay zekâ/konuşma |  |
| `saved_templates_dialog` | 110 | 1 | — |  |
| `screen_record` | 122 | 1 | — | Gerçek FFmpeg ekran kaydı bu bilgisayarda denendi. |
| `shape_art` | 152 | 1 | — |  |
| `shortcuts` | 131 | 3 | — |  |
| `shorts_dialog` | 102 | 3 | — |  |
| `shorts_split` | 206 | 5 | kurgu araçları |  |
| `silence_cut` | 154 | 8 | görüntü, kurgu araçları, model, ses, yapay zekâ/konuşma, çok iz |  |
| `silence_dialog` | 223 | 3 | — |  |
| `speaker_model` | 123 | 2 | — | Konuşmacı ayırma modeli; gerçek iki kişilik kayıtla doğruluk ölçülmedi. |
| `speakers` | 215 | 2 | yapay zekâ/konuşma |  |
| `speech_settings` | 68 | 3 | — |  |
| `start_panel` | 72 | 2 | — |  |
| `story_dialog` | 1027 | 3 | — | Arayüz; açma, kaydetme ve iptal testleri. Gerçek yapay zekâ yanıtı denetlenmez. |
| `story_service` | 962 | 4 | kayıt/şablon |  |
| `story_workers` | 215 | 5 | — | Arka plan işleri; yanıtlar taklit edilir. |
| `style_sample` | 174 | 1 | — | Gerçek medyayla testler. |
| `switch_icons` | 56 | 0 | — | Yalnız çizim; ana pencere testlerinde oluşturulur. |
| `temp_cleanup` | 36 | 1 | — | Testler. |
| `template_dialog` | 306 | 6 | — |  |
| `template_service` | 61 | 4 | — |  |
| `theme` | 152 | 2 | — | İki tema arayüz testleriyle. |
| `thumbnail_service` | 76 | 1 | — | Gerçek medyayla testler. |
| `timeline_audio` | 157 | 53 | pencere |  |
| `timeline_model` | 369 | 65 | gerçek medya, görüntü, kare zamanlaması, kayıt/şablon, kesim matrisi, konuşma projesi, kurgu araçları, model, pencere, ses, yapay zekâ/konuşma, çok iz, önizleme/dışa aktarma |  |
| `timeline_render` | 756 | 24 | gerçek medya, görüntü, kare zamanlaması, konuşma projesi, kurgu araçları, model, ses, yapay zekâ/konuşma, çok iz, önizleme, önizleme/dışa aktarma |  |
| `timeline_service` | 350 | 9 | görüntü, model, ses, önizleme |  |
| `timeline_slice` | 123 | 7 | görüntü, model, ses, önizleme |  |
| `tts_service` | 93 | 2 | konuşma projesi | Windows sesleriyle; sesin kalitesi kulakla değerlendirilmedi. |
| `tts_worker` | 15 | 0 | — | İnce arka plan işi; tts_service üzerinden sınanır. |
| `ui_style` | 91 | 0 | — | Yalnız görünüm; ana pencere testlerinde uygulanır. |
| `update_dialog` | 107 | 0 | — | Doğrudan testi yok; ana pencerenin güncelleme akışı üzerinden açılır. Kurulum GitHub derlemesinde gerçek paketle sınanır. |
| `update_service` | 349 | 7 | kayıt/şablon | İndirme, özet doğrulama ve kurulum ayrıca GitHub derlemesinde gerçek paketle sınanır. |
| `update_worker` | 55 | 1 | — | update_service üzerinden. |
| `user_templates` | 162 | 2 | kayıt/şablon |  |
| `waveform_service` | 28 | 1 | — | Gerçek medyayla testler. |
| `whisper_diagnostic` | 15 | 0 | — | Paketlenmiş Whisper GitHub derlemesinde ayrıca çalıştırılır. |
| `window.assistant` | 557 | 53 | pencere |  |
| `window.exporting` | 371 | 53 | pencere |  |
| `window.layout` | 859 | 53 | pencere |  |
| `window.playback` | 292 | 53 | pencere |  |
| `window.project` | 725 | 53 | gerçek medya, pencere |  |
| `window.timeline_edit` | 1037 | 53 | kurgu araçları, pencere |  |
| `window.updates` | 264 | 53 | pencere | Arayüz testleri ve GitHub derlemesindeki kurulum adımı. |
| `word_captions` | 171 | 4 | gerçek medya, model, çok iz |  |

88 dosya, 21354 satır.

## Yeniden çalıştırma

```powershell
./scripts/media-audit/run-audit.ps1 -Project .
```

Her denetleyici ayrıca tek başına çalışır; ilk sayı deneme sayısı, ikincisi başlangıç tohumudur. Örnek:

```powershell
.venv/Scripts/python.exe scripts/media-audit/ai_fuzz.py . 20000
.venv/Scripts/python.exe scripts/media-audit/window_fuzz.py . 200 1000
```

Bir hata bulunursa denetleyici onu yeniden üreten tohum değerini ve adımları JSON olarak yazar.
