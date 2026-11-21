# Akış Kurgu AI 0.6.21 Windows denetimi

21 Kasım 2026. Yerel `main` ve GitHub `main` inceleme başında `615827ba559193e5b68beecbeddd9119033a8716` commit’indeydi. Yayımlanmış 0.6.20 kurucusunun etiketi `3679f5b7c23ec8eb1b2b8ede09f5f72920df25d4` commit’ine aitti. Aradaki tek dosya 0.6.20 denetim raporuydu. Önceki Claude ve Codex denetimleri ve son iki sürümün arayüz ölçümleri kapsam seçiminde kullanıldı. Yerel kurucu senaryosu düzenlemesi ve `ui0610` örnek dosyaları çalışma kopyasında korundu.

Ortam Windows 11 Pro, Python 3.12.10, PySide6 6.10.0 ve FFmpeg 9.0.2. İki 1920×1080 ekran ve bir ses çıkışı görüldü. Windows kamera veya mikrofon bildirmedi. Kaynak kod, yerelde PyInstaller ile oluşturulan Windows uygulaması ve GitHub’ın kurucu iş akışı ayrı ayrı sınandı.

## Doğrulanan sorunlar

Aşağıdaki dokuz örneğin her biri 0.6.20 davranışında başarısız oldu. Aynı örnekleri çalıştıran regresyon testleri 0.6.21’de geçti. [Dokuz regresyon testi](../tests/test_audit_0621.py)

| Yeniden üretme | 0.6.20’de görülen etki | 0.6.21’de doğrulanan sonuç |
| --- | --- | --- |
| Altyazısı olan kurguda görünür kliple örtüşmeyen bir konuşma metnini uygula. | Yeni altyazı üretilemediği hâlde eski altyazı izi siliniyordu. | Eski iz korunuyor ve örtüşme olmadığı bildiriliyor. |
| Windows seslendirmesinin hedefi olarak açık projenin medya listesindeki WAV dosyasını seç. | Ses üreticisi kaynak dosyaya yazmak üzere başlıyordu. | İş başlatılmadan hedef reddediliyor. |
| Mevcut WAV üzerine seslendirme yazılırken üretimi yarıda kesen bir hata oluştur. | Yarım veri önceki kaydın yerini alıyordu. | Ses ayrı bir geçici dosyada oluşturuluyor. WAV’ın son karesi okunabildikten sonra hedef atomik olarak değiştiriliyor. Hata testinde önceki baytlar korundu. |
| Aynı zaman aralığı dolu 99 seslendirme izine yeni bir kayıt ekle. | Boş iz adı araması hata veriyordu. | Yeni kayıt “Seslendirme 100” izine ekleniyor. |
| Ses veya video analizi sürerken zaman çizelgesini düzenle. | Arka planda eski kurgudan hesaplanan sonuç son düzenlemeye uygulanabiliyordu. | Sonuç teslim edilmeden önce kurgu kontrol ediliyor. Aradaki düzenleme korunuyor ve kullanıcıya analizi yinelemesi bildiriliyor. |
| Ritme oturtmada ilk ses klibinin düzeyini sıfıra indir, arkasına duyulan müzik koy. | Analiz sessiz klibi seçiyordu. | Duyulan müzik klibi seçiliyor. |
| 0,10 saniyelik klibin kesimini zaten üzerinde olduğu vuruşa oturt. | Kısa klip 0,30 saniyeye doğru zorlanabiliyor, hesaplanan bitiş kaynak süresini aşabiliyordu. | Kesim aynı karede kalıyor ve değişiklik sayacı sıfır oluyor. |
| Bir söyleşiyi konuşmanın ortasından başlat, başka bir bölümünü iki kez kullan. | Kaynakta bulunan ilk geçişler işaretleniyor, yeniden kullanılan bölümdeki değişimler kayboluyordu. | Her görünür klipte duyulan ilk konuşmacı ve kurgu sırasındaki değişimler işaretleniyor. |
| Hikâyeyle birlikte sahne görseli ve videosunu yeni klasöre taşı, yeniden aç. | Sahne eski mutlak yolları kullanıyordu. | Hikâye klasöründeki dosyalara taşınabilir başvurular kaydediliyor. Taşınan sahne videosu editörün medya listesine eklendi. Eski biçimdeki hikâyeler okunabiliyor. |

Önceki testlerde seslendirme hedefi boştu, altyazı metni kullanılan kliple eşleşiyordu ve konuşmacı örnekleri kaynağın ilk oynatımını izliyordu. Yeni testler bir işlemin mevcut çalışmaya etkisini de ölçüyor. Ayrı bir rastgele taramada 3.000 tekrarlı veya yeniden sıralanmış kurgu kare kare bir konuşmacı sırası hesabıyla karşılaştırıldı. Kısa klipler için 3.000 ritim örneğinde kaynak sınırı ve vuruşa yaklaşma yönü denetlendi. Başlangıç değeri 77.120, hata sayısı sıfırdı.

## Özellikler ve deneme yöntemi

Özellik listesi Türkçe ve İngilizce README, ana pencerenin düğme bağlantıları, kısayol tablosu, Hikâye Stüdyosu, yerel medya servisleri ve önceki modül envanteri karşılaştırılarak çıkarıldı. Aşağıdaki kaynak arayüz denemeleri bu bilgisayarda 0.6.20 tabanında ve 0.6.21 hazırlanırken, paket denemeleri ise 0.6.21 yerel derlemesinde yapıldı. “Otomatik” satırlarında belirtilen testler başlangıç ve son kodda çalıştırıldı.

| Özellik | Yöntem ve sonuç |
| --- | --- |
| Medya ekleme, klip bölme ve kırpma, geri al/yinele, kaydet, yeniden aç, dışa aktar | Paketli editörde **Video ekle** düğmesi, gerçek Windows dosya pencereleri ve klavye kullanıldı. Yeniden açılan projedeki klip sınırları ve MP4 içindeki kaynak kareleri ile ses ölçüldü. |
| Proje kurtarma, kaydedilmemiş düzenleme, taşınmış kaynak ve bozuk ayar | Kaynak arayüzünde geçici proje otomatik kayıt sonrasında zorla kapatılıp kurtarıldı. Bozuk hız, tuval, yayın ve proje alanlarında kullanıcıya verilen ileti ve yüklenen değerler okundu. Eski proje biçimleri, iki editörün kurtarma kilidi ve geçmiş kopyaları otomatik testlerle sınandı. |
| Ekran kaydı, canlı önizleme ve durdurma çubuğu | Paketli editörde düğmeden kayıt başlatıldı. Pencerenin küçülmesi, çubuktan durdurma, dosyanın projeye girmesi ve gerçek MP4’ün çözülmesi denetlendi. İki fiziksel monitör ayrıca yerel Qt penceresiyle ayrı ayrı kaydedildi. |
| Elle kurgu, aralık silme, Ripple, klip hızı, kadraj, fotoğraf, yazı, şekil ve çok izli önizleme | Başlık gerçek arayüzde üç saniyelik katman olarak kaydedildi. 2× hızda kaynak kareleri ve ses karşılaştırıldı. Diğer işlemler zaman çizelgesi, önizleme ve FFmpeg çıktı testleriyle, ayrıca rastgele düzenleme zincirleriyle sınandı. |
| Ses, seslendirme, müzik ve vurguda yakınlaştırma | Arayüzden Windows sesiyle oluşturulan WAV 3,52 saniye sürdü ve 45. kareye yerleşti. Ses normalizasyonunda −33,4 LUFS girdi −13,5 LUFS çıktı verdi. Ritme oturtma ve vurguda yakınlaştırmada kaydedilmiş proje dosyası tekrar okundu. Gürültü azaltma, müziği kısma, ses senkronu ve klip düzeyi otomatik medya testlerinden geçti. |
| Konuşma metni, altyazı, sessizlik, tekrar, dolgu ve konuşmacı ayrımı | Yerel Türkçe konuşma → Whisper → taşınmış proje → altyazılı MP4 akışında 10 zamanlı kelime, 5 altyazı klibi, 4,87 saniye çıktı ve sıfır eksik kaynak ölçüldü. Sessizlik temizliği gerçek arayüzde, tekrar ve dolgu kararları otomatik örneklerde sınandı. WeSpeaker ve işaretleme ölçümleri aşağıda. |
| Prompt ile kurgu, ilham, öneriler, stil örneği ve şablonlar | Gerçek arayüzde sabit servis yanıtıyla iki parçalı plan, onay, çıktı, geri al ve geçersiz yanıt denendi. Hazır ve kullanıcı şablonları uygulanıp geri alındı. Stil çıkarma, servis yönlendirme, yanıt doğrulama ve iptal yolları otomatik testlerle sınandı. |
| Hikâye Stüdyosu | Kaydet, aç ve seçilen sahneyi editöre ekle düğmeleri yerel Qt penceresinde denendi. Sahne klasörü arada taşındı. Dosya seçicisi için geçici yol sağlandı. Rehber, taslak, sahne, devamlılık, metin/görsel/video işçileri, hatalar ve iptal kontrollü servis yanıtlarıyla sınandı. |
| Video, üç oran, Shorts, öne çıkanlar, toplu işlem, hızlı çıktı ve FCPXML | Kaynak arayüzünde sentetik videolarla çıktı dosyaları açıldı. Oranlar, her karedeki kaynak numarası, sesin zamanı, parça sınırları ve XML’deki kesim noktaları denetlendi. Dışa aktarırken iptal, tekrar deneme ve pencereyi kapatma ayrı denendi. |
| Dil, tema, kısayollar, yayın metni, gizlilik ve güncelleme | TR ↔ EN ve açık/koyu tema gerçek arayüzde sınandı. F1 ve kurgu kısayolları arayüz ve olay testleriyle, yayın metni, gizlilik günlüğü, sürüm karşılaştırma, sağlama toplamı, kurucuya devir ve iptal otomatik testlerle kontrol edildi. |
| Başlangıç paneli ve medya kitaplığı | Dosya açma, sürükle-bırak ve çoklu kaynak ekleme, medya arama ve eksik kaynağı yeniden bağlama otomatik pencere testlerinden geçti. Gerçek arayüzde Türkçe karakterli dosyanın adı ve süresi doğrulandı. [Dosya giriş testleri](../tests/test_open_path.py) |
| Önizleme ve oynatma | Kare ilerletme, zaman çizelgesinde gezinme, kısayol odağı, küçük resim, ses dalgası, önizleme önbelleği ve eşzamanlı ses seçimi otomatik testlerden geçti. 0,5×, 1×, 1,5× ve 2× senaryolarında bölünmeden önceki ve sonraki kareler karşılaştırıldı. [Önizleme denetimi](../scripts/media-audit/preview_export.py) |
| Altyazı görünümü, dil ve kelime listesi | Cümle ve kelime zamanlarının farklı hız ve kesimlerdeki yerleşimi, vurgulanan kelimenin çizimi, tanıma dili ve sözlük ayarları otomatik testlerden geçti. [Kelime altyazıları](../tests/test_word_captions.py) · [Konuşma ayarları](../tests/test_speech_settings.py) |
| Sağlayıcı anahtarları, ilham ve yayın | Sağlayıcı değiştirince doğru anahtarın seçilmesi, anahtarın kaydı, yerel öneriye dönüş, önerinin işaretlere uygulanması ve yayın başlığı/açıklaması/etiketlerinin projede saklanması kontrollü örneklerde sınandı. Gerçek hesap anahtarı kullanılmadı. [Dil ve anahtar testleri](../tests/test_language_keys.py) · [İlham akışı](../tests/test_inspiration_flow.py) |
| Dışa aktarma ön kontrolü ve ilerleme | Boş görüntü aralığı gerçek kayıtlı kurguda uyarıldı, çıktıdaki karşılığı siyah ve sessizdi. Profil ve tuval, disk alanı, yüzde/kalan süre, kilitli hedef, geçici dosya temizliği ve iptal koşulları otomatik testlere dahil edildi. [Ön kontrol](../tests/test_preflight.py) · [İlerleme](../tests/test_export_progress.py) |
| Kurulum, yerinde güncelleme ve kaldırma | GitHub’ın temiz Windows makinesindeki senaryolar kullanıldı. Sonuçlar, kurucunun boyutu ve SHA-256 değeri aşağıdaki “Yayın” bölümünde. |

## Ölçümler

| Deneme | Sonuç |
| --- | --- |
| Başlangıç | 0.6.20 kaynak kodunda 1.088 test bulundu. Ana koşuda 1.086 test geçti. İki masaüstü testi ayrıca geçti. Öncül kurucunun yerel SHA-256 değeri GitHub ile eşleşti. |
| Son kod | 0.6.21’de 1.097 test bulundu. Ekransız koşuda 1.094 test geçti. Ayrı Windows koşusunda üç testin üçü de geçti. Bunlar iki ekranda modal kayıt, kısa gerçek ekran kaydı ve Shorts arayüzünde tekrarlı analiz/kapatma denemesiydi. |
| Medya ve rastgele senaryolar | Başlangıç ve son sürümde 6/6 medya grubu geçti. 2.520 ayar birleşiminde ve 10 gruptaki 16.870 standart rastgele senaryoda hata sayısı sıfırdı. Her koşudan 17 ölçüm dosyası elde edildi. |
| Paketli editörde kayıt | Önizleme alanında piksel standart sapması 41,6 ölçüldü. Kayıt penceresi ve editör küçüldü. Çubuktan durdurunca dosya projeye girdi. 1920×1080 MP4, 5,20 saniye, 131 çözülen kare, sıfır çözme hatası. |
| Paketli editörde kes ve yeniden aç | 8 saniyelik örnekte 2. saniyede bölme, 4. saniyede kırpma, geri al ve yinele uygulandı. Kaydet → kapat → yeniden aç → dışa aktar sonunda dikey MP4’ün 240 karesi okundu. İlk 60 ve son 120 kare kaynağa karşılık geldi. Aradaki 60 kare siyah ve sessizdi. 16 yarım saniyelik ses kontrolünün tamamı geçti. |
| Paketli editörde dosya güvenliği | Kilitli çıktı korunup kilit kalkınca yazıldı. Üzerine yazmaya Hayır denilen dosya ve kaynak video korundu. Taşınan kaynak yeniden bağlanıp dışa aktarıldı. Boş, yarım ve daha yeni biçimli proje dosyaları ayrı ayrı reddedildi. Kaydedilmemiş değişiklik sorusunda İptal pencereyi açık tuttu, At ile editör kapandı. |
| Ses analizleri ve hikâye | Yerel Qt penceresinde ritim aracı kesimi 67. kareden 60. kareye taşıdı, müzik 240 kare kaldı. Vurgu aracı kaynakta 92. kareye 36 karelik yakınlaştırma kaydetti. Önbellekteki WeSpeaker modeli, süresi 5,11 saniye olan tek Windows anlatıcısını tek konuşmacı olarak buldu. Taşınmış hikâyedeki 8 saniyelik sahne açıldı ve editöre eklendi. |
| Paket tanılamaları | Yerelde derlenen EXE’de ses çıkışı ve Whisper tanılamaları geçti. Sessiz tanılama dosyası modelin yüklenmesini sınadı. Türkçe kelime ve altyazı ölçümü ayrı sesli örnekle yapıldı. |

İlk kaynak arayüz denemesinde kapanmış pencerenin erişilebilirlik nesnesi sorgulanınca betik hata verdi. Kayıt betiği de önizleme yerine düz renkli bir etiketi ölçtü. Betikler artık süreç çıkışını bekliyor ve önizlemeyi kendi denetim kimliğiyle buluyor. Gerekli örnek dosyaları ortak çalışma klasöründen kullanan sınır durumu betikleri doğru klasörde yeniden çalıştırıldı.

Denetim aracındaki iki dosya sahipliği sorunu da giderildi. Arayüz testleri ortak kurtarma klasöründe deneme sırasında beliren dosyaları silebiliyor, şablon denemesi kişisel şablon dosyasının eski kopyasını geri yazabiliyordu. Her test çalıştırmasına özel bir uygulama veri klasörü oluşturuldu. Kayıt denemesi de kendi geçici kayıt klasörünü seçiyor. Dosya pencereleri Windows panosunu kullanmadan dolduruluyor.

## Devralma ve bağımsız doğrulama (Claude)

Bu denetimi Codex başlattı; kod, testler ve bu raporun yukarısı onun çalışmasıdır. Codex yayından önce durduğu için çalışma, commit edilmemiş hâliyle Claude tarafından devralındı ve yayımlanmadan önce bağımsız olarak denetlendi:

| Deneme | Sonuç |
| --- | --- |
| Değişikliklerin okunması | 13 program dosyasındaki değişiklik okundu. Altyazı değişikliğinde örtüşme yoksa iz hiç eklenmediği, erken dönüşün güvenli olduğu doğrulandı. |
| Dokuz regresyon testi 0.6.20 üzerinde | 0.6.20'nin (`615827b`) ayrı bir kopyasında dokuzunun dokuzu başarısız (7 hata, 2 istisna); 0.6.21'de dokuzu da geçti. |
| Tam denetim (`run-audit.ps1 -LocalSpeech`) | 1.097 test geçti (2 atlandı). 6/6 medya grubu. 10 kural denetleyicisinin hepsi 0 hata. Yerel konuşma projesi 10 kelime, 5 altyazı. İki ekranda gerçek kayıt 3,60 sn, 92 ve 91 kare. |
| Paketlenmiş 0.6.21'de gerçek arayüz | Yayın sekmesinin 9 bölümü, düzenleme araçlarının 10 bölümü, bozuk ayarlı 3 proje, İngilizce arayüz ve tema, hazır şablon ve Şablonlarım, temel düzenleme (240/240 kare, 16/16 yarım saniye ses) geçti. Güncelleme düğmesi “0.6.21 is the latest version” dedi. |
| Seslendirme düzeltmesi, gerçek arayüzde | Projede kullanılan WAV'a yeni seslendirme yazdırıldı (Windows'un “değiştirilsin mi?” sorusuna Evet). 0.6.21: “Çıktı yolu kaynak medya ile aynı olamaz…” dendi, dosya baytı baytına aynı kaldı. 0.6.20 paketinde uyarı çıkmadı ve dosya yeniden yazıldı. |
| Altyazı düzeltmesi, gerçek arayüzde | Yerel Whisper ile 7 altyazı klibi eklendi, konuşma klibi silindi, aynı metin yeniden uygulandı. 0.6.21: “Konuşma metni zaman çizelgesindeki görüntüyle örtüşmüyor.” dendi, 7 altyazı klibi yerinde kaldı. 0.6.20 paketinde “0 altyazı klibi eklendi” dendi ve önceki 7 altyazının hepsi silindi. |

Bu iki adım `scripts/media-audit/ui-flows/flow_tools.py` akışına eklendi (“voiceover over its own wav”, “captions kept without overlap”).

Devralmada düzeltilenler:
- Raporun kurulum satırı, iş akışının üretmediği bir sürüm dosyasına (`windows-audit-v0.6.21.json`) bağlanıyordu. Bu bağlantı aşağıdaki “Yayın” bölümüyle değiştirildi.
- Arayüz betiklerinin geçici profil temizliği, kapanan editörün hâlâ tuttuğu kilit dosyasını silmeye çalışınca betiği düşürüyordu. Kilitli dosya artık atlanıyor; profil zaten geçici.

## Doğrulama sınırları

Fiziksel kamera ve mikrofon takılı değildi. Ücretli bulut sağlayıcılarına gerçek üretim isteği gönderilmedi. Tek sentetik anlatıcının tanınması, uzun ve gürültülü çok konuşmacılı bir röportajın doğruluğunu ölçmez. Ses kalitesi kulakla değerlendirilmedi. FCPXML, Final Cut Pro veya DaVinci Resolve içine alınmadı. Yerel Windows uygulaması ayrı klasörde paketlendi. Bilgisayardaki kişisel kurulumun üzerine kurulum yapılmadı.

## Yayın

Sonuçlar yayından sonra eklenecek.

## Yeniden çalıştırma

```powershell
./scripts/media-audit/run-audit.ps1 -Project . -Python ./.venv/Scripts/python.exe -LocalSpeech
.venv/Scripts/python.exe -m unittest tests.test_audit_0621 -v
.venv/Scripts/python.exe scripts/media-audit/sound_story_windows.py . "$env:TEMP/akis-ses-hikaye-yeni"
```

Son komut için yeni bir çalışma klasörü kullanın. Ekran ve kurgu akışlarının kaynak ve paketli uygulamada nasıl çalıştırılacağı denetim betiklerinde açıklanır. [Arayüz denemeleri](../scripts/media-audit/ui-flows/README.md)
