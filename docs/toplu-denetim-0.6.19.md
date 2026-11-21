# Akış Kurgu AI 0.6.19 Windows denetimi

21 Kasım 2026. Bu rapor, programın bu Windows bilgisayarında baştan sona denetimini tek yerde toplar: başlangıç sürümü, özellik listesi, her özelliğin nasıl denendiği, bulunan sorunlar ve düzeltmeleri, sınanamayanlar.

## Başlangıç noktası

| Kaynak | Durum |
| --- | --- |
| Yerel çalışma kopyası | `main`, `5fef47e`. GitHub `main` ile aynı. |
| GitHub'daki son sürüm | 0.6.18, `062ccc5`. `5fef47e` program kodunda bununla aynı; aradaki iki commit yalnız denetim betiklerini ve raporu değiştiriyor. |
| Bu bilgisayarda kurulu program | 0.6.10, `D:\Yeni klasör\AkisKurguAI`. Eski olduğu için denemede kullanılmadı. |
| Denenen program | `5fef47e`, kaynak koddan (`main.py`) ve aynı commit'ten bu bilgisayarda PyInstaller 6.22.3 ile derlenen paket (`AkisKurguAI.exe`). Düzeltmelerden sonra paket yeniden derlenip akışlar tekrarlandı. |
| Korunan yerel çalışmalar | `scripts/installer-scenarios.ps1` üzerindeki değişiklik ve takip edilmeyen `scripts/media-audit/ui0610/` klasörüne dokunulmadı; commit'lere girmedi. |

Okunan önceki denetimler: `docs/proje-denetimi.md` (0.6.15), `toplu-denetim-0.6.12` ile `0.6.18` arası raporlar ve sürüm notları. 0.6.16 ve 0.6.17 kural tabanlı tarayıcılarını, 0.6.18 Codex'in Windows denetimini ve kayıt düzeltmelerini getirmişti.

**Ortam:** Windows 11 Pro 10.0.26300, Python 3.12.10, PySide6 6.10.0, FFmpeg 9.0.2. İki ekran var, ikisi de 1920×1080; ikincisi birincinin solunda. Bilgisayarda kamera ve mikrofon yok.

## Yöntem

1. Menüler, düğmeler, kısayollar, kaynak kod ve README karşılaştırılıp özellik listesi çıkarıldı (aşağıdaki tablo).
2. Başlangıçta bütün test kümesi ve `scripts/media-audit/run-audit.ps1` denetimi, Windows arayüz testleri ve yerel konuşma tanımayla birlikte çalıştırıldı.
3. Temel akışlar gerçek Windows arayüzünde denendi. Program ayrı bir süreç olarak başlatıldı. Düğmelere Windows UI Automation ile, klavye kısayollarına ve zaman çizelgesine gerçek tuş ve fare olaylarıyla basıldı. Dosya pencereleri Windows'un kendi pencereleriydi. Aynı akışlar paketlenmiş `.exe` üzerinde tekrarlandı. Başarı, ekrandaki yazıyla değil, üretilen dosyanın kendisi ölçülerek doğrulandı.
4. Her özellik için iptal, yeniden deneme, işlem sürerken kapatma, aynı anda iki iş, eski ve bozuk proje, taşınmış medya, Türkçe karakter, uzun ad, açık tutulan dosya ve aynı adlı çıktı denendi. Bütün denemeler geçici klasörlerde ve örnek medyayla yapıldı.
5. Bulunan sorunlar düzeltildi. Her düzeltme, hatanın görüldüğü gerçek akışta yeniden denendi. Her biri için eski kodda başarısız olup yeni kodda geçen bir test eklendi.

Akışlarda kullanılan örnek video, her karesinde kendi numarasını gri bloklarla taşır ve her saniyesinde farklı perdede bir ses çalar. Böylece dışa aktarılan videonun her karesi ve her yarım saniyelik sesi, kaynağın hangi anı olduğu okunarak denetlenebildi.

## Özellik listesi ve sonuçlar

Sütunlar: **Arayüz** = gerçek Windows arayüzünde düğmeyle denendi (K: kaynak koddan, E: paketlenmiş `.exe`); **Test** = otomatik test kümesi; **Kural** = rastgele girdili kural denetleyicileri (`scripts/media-audit/*_fuzz.py`); **CI** = GitHub Windows derlemesi.

| Özellik | Nasıl denendi | Sonuç |
| --- | --- | --- |
| Video ekleme (＋ Video ekle, Ctrl+I, başlangıç panelindeki “Video seç”, sürükle-bırak) | Arayüz K+E: Türkçe karakterli klasörden düğmeyle; Test | Geçti. 8 sn'lik video zaman çizelgesine 8,00 sn olarak geldi. |
| Zaman çizelgesi: Böl (S), ◁ Kırp (Q), Kırp ▷ (W), Aralığı sil, Ripple sil, Delete, klip sürükleme, iz ekle/sil, yakınlık | Arayüz K+E (S, Q); Test; Kural (`fuzz`, `window_fuzz`, `render_fuzz`) | Geçti. Q, kodda yazıldığı gibi klibin yerini koruyup boşluk bırakıyor; dışa aktarma bu boşluğu önceden soruyor. |
| Geri al / yinele (Ctrl+Z, Ctrl+Y, düğmeler) | Arayüz K+E; Kural (`window_fuzz`: her değişiklik tek adım, hepsi geri alınınca ilk hal) | Geçti. Yinelemeden sonra kaydedilen proje kırpılmış hali taşıyor. |
| Proje kaydet, farklı kaydet, aç | Arayüz K+E: Türkçe adlı klasöre kaydet, programı kapat, yeniden aç, düğmeyle yükle; Test; Kural (`store_fuzz`, `files_fuzz`) | Geçti. Kapatma sonrası süreç 0 koduyla bitti, yeniden açılan proje aynı klipleri taşıyor. |
| Kaydedilmemiş değişiklik koruması | Arayüz K: düzenleme sonrası başka proje açma ve pencereyi kapatma | Geçti. İkisinde de “Kaydedilsin mi?” soruldu; İptal işi korudu, “At” kapattı. Yalnız eklenmiş bir video henüz değişiklik sayılmıyor (bilinçli). |
| Otomatik kayıt ve kurtarma | Arayüz K: yarıda kesilen oturumun ardından açılış; Test | Geçti. Sonraki açılışta “Kurtarılmış çalışma bulundu” soruldu. |
| Taşınmış medya | Arayüz K: medya klasörü taşındıktan sonra proje açma | Geçti. Eksik dosya soruldu, yeni yeri gösterilince proje açıldı ve dışa aktarılan video taşınan dosyanın karelerini gösterdi. |
| Eski, bozuk, yarım, daha yeni sürümlü proje | Arayüz K; yeni test; yeni kural (`store_fuzz` proje dosyası) | **Sorun bulundu ve düzeltildi** (Bulgu 2 ve 3). Açık proje her durumda korunuyordu. |
| Uzun ve Türkçe dosya adları | Arayüz K+E (Türkçe klasör ve dosya adları); Kural (`files_fuzz`: 255 karaktere kadar adlar) | Geçti. |
| Önizleme ve oynatma (▶, Boşluk, ←/→, Home/End, akıcı önizleme) | Arayüz K+E (ok tuşları ve Home ile oynatma çizgisi tam 2,00 ve 4,00 sn'ye geldi); Test; Kural (`preview_fuzz`) | Geçti. |
| Ses (klip sesi, −14 LUFS, gürültü azaltma, müziği kıs, Windows sesiyle WAV) | Arayüz K+E (dışa aktarılan sesin her yarım saniyesi doğru kaynak anından geldi); Test; Kural (`audio_fuzz`); yerel Türkçe ses sentezi | Geçti. Sesin kulakla kalitesi ölçülmedi. |
| Altyazı ve yerel konuşma tanıma | Test; yerel Whisper ile uçtan uca proje (`speech_project`) | Geçti: 10 zamanlı kelime, 5 altyazı klibi, 4,87 sn çıktı. |
| Yapay zekâ ile kurgu, öneri modu, sessizlik, tekrar, dolgu sözcüğü, konuşmacı, ritim, yakınlaştırma | Test (sağlayıcı yanıtları taklit); Kural (`ai_fuzz`: bozuk ve uç değerli yanıtlar) | Geçti. Gerçek ücretli sağlayıcı çağrılmadı. |
| Hikâye Stüdyosu | Test (Gemini yanıtları taklit); Kural (`store_fuzz`: kaydetme, açma, elle düzenlenen rehber) | Geçti. |
| İlham, şablonlar, şablonlarım | Test; Kural (`store_fuzz`) | Geçti. |
| Ekran kaydı (Kayıt al) | Arayüz K+E: düğmeyle baştan sona; Test; Kural (`record_fuzz`); iki ekranda gerçek kayıt testi | Geçti (ayrıntı aşağıda). |
| Kamera ve mikrofon kaydı | Test (taklit aygıtlar) | Bu bilgisayarda aygıt yok; gerçek çekim denenmedi. |
| Dışa aktarma (Ctrl+E) | Arayüz K+E: kare kare ve saniye saniye ölçüm; iptal, yeniden deneme, kapatma, aynı anda iki iş, açık tutulan dosya, aynı ad, kaynakla aynı ad | **Sorun bulundu ve düzeltildi** (Bulgu 1). Diğer denemeler geçti. |
| Üç biçimde aktarma, toplu aktarma, Shorts, öne çıkanlar, FCPXML, hızlı aktarma | Test; Kural (`files_fuzz`: adlar ve kaynak koruması); Windows penceresinde Shorts testi | Geçti. FCPXML'in Final Cut Pro ve DaVinci Resolve içinde açılması denenmedi. |
| Arayüz dili ve tema, kısayol listesi (F1) | Test | Geçti. |
| Güncellemeyi denetleme, indirme, doğrulama | Test; Kural (`files_fuzz`: eşzamanlı indirme, klasör temizliği); CI'da yayımlanan sürümle güncelleme denemesi | Geçti. |
| Kurulum, yerinde güncelleme, kaldırma | CI (`installer-scenarios.ps1`, `update_smoke`) | Sonuç aşağıda “Yayın” bölümünde. Bu bilgisayardaki kuruluma dokunulmadı. |

## Gerçek arayüz akışları

### Video ekle → kes → geri al/yinele → kaydet → kapat → aç → dışa aktar

Hem kaynak koddan hem paketlenmiş `.exe` ile aynı sonuç alındı:

1. “＋ Video ekle” ile `Çekim ğüşİ klasörü\örnek video çalışma.mp4` seçildi (8,00 sn).
2. Klibe tıklandı. Home ve iki kez Shift+→ ile oynatma çizgisi 2,00 sn'ye getirildi, S ile bölündü (“Klip bölündü.”).
3. İkinci parça seçildi, çizgi 4,00 sn'ye getirildi, Q ile 2–4 sn arası atıldı.
4. Ctrl+Z ile geri alındı (“Son adım geri alındı.”), Ctrl+Y ile yinelendi.
5. Ctrl+S ile `Projeler İş\Deneme projesi ğüş.akis.json` kaydedildi. Dosyadaki klipler `(0, 60, 0)` ve `(120, 120, 120)`.
6. Pencere kapatıldı; süreç 0 koduyla bitti. Program yeniden açılıp “Proje aç” ile proje yüklendi.
7. Ctrl+E ile dışa aktarıldı. Program önce boşluğu sordu: “Videoda 1 yerde görüntü yok (toplam 2,0 sn, 0:02,0)”. Ardından “Video başarıyla oluşturuldu” dedi.
8. Çıktı ölçüldü: 8,00 sn, 240 kare, 1080×1920, ses var. Karelerin 240'ı da beklenen kaynak karesini gösterdi (0–59, 60 siyah kare, 120–239). Sesin 16 yarım saniyesi de doğru kaynak saniyesinden geliyordu; boşluk sessizdi.

### Kayıt al → önizleme → başlat → küçülme → çubuktan durdurma → projeye ekleme → MP4 ölçümü

Kaynak koddan iki kez, paketlenmiş `.exe` ile bir kez:

| Adım | Ölçüm |
| --- | --- |
| Önizleme | Kayıt penceresindeki görüntü alanının piksel sapması 33,4: düz renk değil, canlı ekran görüntüsü. |
| Kaydı başlat | Ana pencere simge durumuna küçüldü. Kayıt penceresi ekrandan kalktı (görünür değil). Durdurma çubuğu kaydedilmeyen diğer ekranda açıldı (x = −1113). |
| Çubuktan durdurma | Kayıt penceresi kapandı, ana pencere geri geldi, kayıt zaman çizelgesine eklendi (5,19–5,20 sn). |
| MP4 | 1920×1080, 5,17–5,20 sn, 132–139 kare. FFmpeg dosyayı hatasız çözdü. Dosyanın süresi programın saatiyle aynı. |

Deneme kayıtları silindi. Bu bilgisayarda FFmpeg'in ekran yakalaması 30 kare/sn istendiğinde 1920×1080'de saniyede 25–27 kare verdi; dosya zaman damgaları doğru olduğu için süre ve ses uyumu etkilenmiyor.

### Uç durumlar (kaynak koddan)

| Deneme | Sonuç |
| --- | --- |
| 60 sn'lik dışa aktarmayı “İptal” ile durdurmak | Geçti. “Dışa aktarma iptal edildi.” Yarım dosya ve dışa aktarma FFmpeg'i kalmadı. Arkasından aynı dışa aktarma 60,00 sn, 1.800 kareyle tamamlandı. |
| Dışa aktarma sürerken ikinci dışa aktarma | Geçti. İkinci kayıt penceresi açılmadı, “Bir işlem devam ediyor; lütfen bitmesini bekleyin.” yazdı. İlk dışa aktarma eksiksiz bitti (1.800 kare). |
| Dışa aktarma sürerken pencereyi kapatmak | Geçti. “Devam eden işlem iptal edilip çıkılsın mı?” soruldu. Evet'ten sonra FFmpeg durdu, yarım dosya kalmadı. |
| Başka bir programın açık tuttuğu dosyanın üzerine dışa aktarmak | **Bulgu 1.** Düzeltmeden sonra geçti. |
| Var olan dosyanın üzerine, “Hayır” ile | Geçti. Windows'un kendi “değiştirilsin mi?” sorusu çıktı, eski dosya aynı kaldı. |
| Kaynak videonun kendisinin üzerine | Geçti. “Çıktı yolu kaynak medya ile aynı olamaz” denip reddedildi, kaynak baytları aynı kaldı. |
| Yazılamayan klasöre dışa aktarma | Windows'un kayıt penceresi böyle bir klasörü seçtirmiyor; program bu yola hiç ulaşmıyor. Kayıt klasörü için engelli klasör `record_fuzz` ve testlerle sınanıyor. |
| Yarım, boş, daha yeni sürümlü proje açmak | **Bulgu 2.** Düzeltmeden sonra geçti. Açık proje korundu. |

## Bulgular ve düzeltmeler

Veri kaybı ya da çökme bulunmadı. Üç sorunun hepsi, kullanıcının neyin yanlış gittiğini anlayamamasına yol açıyordu.

### 1. Başka programda açık dosyaya dışa aktarma yanlış nedeni gösteriyordu

- **Yeniden üretme:** Bir video dışa aktarılır ve bir oynatıcıda açık bırakılır (denemede dosya başka bir süreç tarafından paylaşımsız açık tutuldu). Aynı ada yeniden dışa aktarılır, Windows'un “değiştirilsin mi?” sorusuna Evet denir.
- **Beklenen:** Dosyanın başka programda açık olduğunun söylenmesi. Kilit kısa sürüyorsa (virüs taraması) beklenmesi.
- **0.6.18'de:** `[WinError 5] Erişim engellendi: '…\açık dosya.part-37c7e22b….mp4'` ve ardından “Windows Güvenliği veya antivirüs yazmayı engellediyse, klasör izinlerini… kontrol edin” önerisi. Kullanıcı hiç görmediği bir dosya adını ve yanlış bir çözümü görüyordu. Eski video yerinde kalıyor, yarım dosya siliniyordu.
- **Düzeltme:** Bitmiş video yerine taşınırken hedef kilitliyse yaklaşık 1,5 sn beklenip yeniden deneniyor. Kilit sürerse “Hedef dosya başka bir programda açık (örneğin bir video oynatıcıda). O programı kapatıp yeniden deneyin.” yazıyor (İngilizce arayüzde İngilizcesi). Normal ve hızlı dışa aktarma aynı yolu kullanıyor (`akis/timeline_render.py: place_output`).
- **Doğrulama:** Gerçek arayüzde yeni mesaj göründü, `.part` dosyası kalmadı; dosya serbest kalınca aynı dışa aktarma 240 kareyle bitti.
- **Test:** `tests/test_windows_audit_0619.py` (OutputHeldOpenTests, 3 test). Dosyayı Windows'un gerçek kilidiyle açık tutuyor. Üçü de eski kodda başarısız.

### 2. Proje açma hataları İngilizce ya da Python'un iç metniydi

- **Yeniden üretme:** “Proje aç” ile şunlardan biri seçilir: yarım kalmış, boş ya da daha yeni sürümle kaydedilmiş bir proje; içinde `[]` ya da düz metin olan bir `.akis.json`; metin olmayan bir dosya.
- **0.6.18'de gösterilen:**
  - “Proje açılamadı: Unsupported project version”
  - “Expecting value: line 1 column 47 (char 46)”
  - “'utf-8' codec can't decode byte 0xff…”
  - “'list' object has no attribute 'get'”

  Sürüm alanı `true` olan bir dosya proje sayılıyordu.
- **Düzeltme:** Üç Türkçe mesaj geldi, İngilizceleriyle birlikte:
  - “Proje dosyası bozuk ya da yarım kalmış (satır 1, sütun 47).”
  - “Bu proje programın daha yeni bir sürümüyle kaydedilmiş. Açmak için programı güncelleyin.”
  - “Bu dosya bir Akış Kurgu projesi değil.”
- **Doğrulama:** Gerçek arayüzde üç bozuk dosyada da yeni mesajlar göründü, açık proje (8,00 sn) korundu.
- **Test:** `tests/test_windows_audit_0619.py` (ProjectOpenMessageTests). Eski kodda dört testin hepsi ve alt durumlarının tümü başarısız.

### 3. Bozulmuş kurgu bölümü İngilizce model hatası gösteriyordu

- **Nasıl bulundu:** Bulgu 2'den sonra `store_fuzz` denetleyicisine eklenen kural, rastgele bozulmuş proje dosyalarını açtı. Kurgu bölümü bozuk (geçersiz iz türü, çakışan ya da sıfır uzunluklu klip, eksik alan) 2.000 denemenin 168'inde mesaj anlaşılır değildi: “Invalid clip range”, “Invalid track type”, “'NoneType' object is not subscriptable”, “Clip.__init__() got an unexpected keyword argument…”.
- **Düzeltme:** “Proje dosyasındaki kurgu okunamadı; dosya bozulmuş ya da elle değiştirilmiş olabilir.”
- **Test:** `test_a_damaged_timeline_is_named_without_model_or_python_words`, ayrıca her derlemede `store_fuzz` (proje dosyası kuralı).

### Mevcut testler bu sorunları neden kaçırdı

- **Bulgu 1:** Dışa aktarma testleri yazma hatasını `os.replace` yerine sahte bir `PermissionError` koyarak üretiyordu. O hata gerçekten izin hatası gibi davrandığı için antivirüs önerisinin görünmesi doğru sayılıyordu. Hiçbir test hedef dosyayı bir oynatıcı gibi açık tutmuyordu. Yeni test Windows'un gerçek dosya kilidini kullanıyor.
- **Bulgu 2 ve 3:** Proje testleri yalnız bir hata türünün (`ValueError`) atıldığını denetliyordu, kullanıcının göreceği metni değil. Bozuk kurgu bölümü içeren dosya hiç denenmemişti. Yeni testler metni denetliyor. Yeni kural her derlemede rastgele bozulmuş dosyalar deniyor.

## Hata sayılmayan gözlemler

- Q (◁ Kırp) klibin yerini koruyup boşluk bırakıyor. Kodda böyle tarif edilmiş ve kenarı sürüklemekle aynı. Boşluğu kapatmak için “Ripple sil” var; dışa aktarma boşluğu önceden soruyor.
- Yeni bir projeye yalnız video eklemek kaydedilmemiş değişiklik sayılmıyor. İlk düzenlemeden sonra kapatma ve başka proje açma soruyor.
- Ekran kaydı 1920×1080'de bu bilgisayarda saniyede 25–27 kare yakaladı (istenen 30). Zaman damgaları doğru.
- `run-audit.ps1`, Windows PowerShell 5.1'de çıktısı bir dosyaya yönlendirilerek çalıştırılırsa Python'un uyarı satırlarını hata sayıp duruyor. Doğrudan ya da ayrı bir PowerShell sürecinde, GitHub'da da PowerShell 7 ile sorunsuz çalışıyor.
- 0.6.18 derlemesinden sonra GitHub'da iki kez ses denetleyicisi FFmpeg beklerken takılmıştı. Bu bilgisayarda ve sonraki derlemede yeniden üretilemedi. Denetleyici artık takılan bir FFmpeg'i 3 dakikada durdurup hangi denemede takıldığını yazıyor.

## Otomatik testler ve denetim

| | Başlangıç (`5fef47e`) | Düzeltmelerden sonra |
| --- | --- | --- |
| Genel test kümesi | 1.072 test, 2 atlandı, hepsi geçti | 1.080 test, 2 atlandı, hepsi geçti |
| Windows pencere testleri (Shorts penceresi, iki ekranda gerçek kayıt) | 2 test geçti; kayıtlar 3,57 sn/94 kare ve 3,63 sn/93 kare | 2 test geçti; kayıtlar 3,63 sn/99 kare ve 3,63 sn/102 kare |
| Medya grupları (2.520 ayar birleşimi, zamanlama, derin, kurgu, çok iz, önizleme/dışa aktarma) | 6/6 geçti | 6/6 geçti |
| Kural denetleyicileri | 9 denetleyici, hepsi 0 hata | 9 denetleyici, hepsi 0 hata (`store_fuzz` proje dosyası kuralıyla) |
| Yerel konuşma projesi | 10 kelime, 5 altyazı, 4,87 sn | Aynı: 10 kelime, 5 altyazı, 4,87 sn |

Yeni testler: `tests/test_windows_audit_0619.py` (8 test). Sekizi de 0.6.18 kodunda başarısız oluyor (alt durumlarıyla 17 hata); düzeltilmiş kodda hepsi geçiyor. Yeni kural: `store_fuzz` içinde proje dosyası kuralı; derlemede 1.500 durumun beşte biri.

Düzeltmelerden sonra paket yeniden derlendi ve akışlar, projeye eklenen betiklerden (`scripts/media-audit/ui-flows`) yeniden çalıştırıldı. Paketlenmiş `.exe` üzerinde üç akış geçti:
- **Düzenleme ve dışa aktarma:** 240/240 kare ve 16/16 yarım saniye ses doğru.
- **Kayıt:** 5,17 sn, 144 kare.
- **Bozuk projeler:** Üç dosya da Türkçe mesajla reddedildi.

Kaynak koddan çalıştırılan 13 uç durumun 13'ü de geçti.

## Sınanamayan koşullar

- Gerçek ücretli yapay zekâ sağlayıcılarının (OpenAI, Gemini, xAI, Cloudflare) yanıtları. Bunların yanıtları, iptalleri ve hataları test yanıtlarıyla sınandı.
- Kamera ve mikrofonla kayıt: bu bilgisayarda aygıt yok. Bu yollar taklit aygıtlarla sınandı.
- Sesin kulakla duyulan kalitesi ve Windows seslendirmesinin doğallığı.
- Whisper'ın uzun, gürültülü ya da çok kişili gerçek kayıtlardaki doğruluğu (deneme sentetik Türkçe sesle).
- FCPXML'in Final Cut Pro ve DaVinci Resolve içinde açılması.
- Farklı ekran kartı, sürücü, ekran ölçeği ve güvenlik yazılımları.
- Kurulum, güncelleme ve kaldırma bu bilgisayarda değil, GitHub'ın temiz Windows makinesinde denendi; buradaki 0.6.10 kurulumuna dokunulmadı.
- Kurucu dijital imzalı değil.
- Bozuk bir projenin kurgu dışındaki alanlarının (`state`) pencereye uygulanırken verebileceği hatalar yalnız mevcut testlerle sınandı; rastgele bozulmuş `state` alanları denenmedi.

## Yayın

GitHub Windows derlemesi bu commit gönderildikten sonra çalışır: testler, medya grupları, kural denetleyicileri, paketleme, kurulum, yerinde güncelleme ve kaldırma. Sonuçları ve yayımlanan kurucunun SHA-256 doğrulaması bu bölüme sonraki commit'te eklenir.

## Yeniden çalıştırma

```powershell
./scripts/media-audit/run-audit.ps1 -Project . -LocalSpeech
.venv/Scripts/python.exe -m unittest tests.test_windows_audit_0619
.venv/Scripts/python.exe scripts/media-audit/store_fuzz.py . 3000
```

Gerçek arayüz akışları `scripts/media-audit/ui-flows` klasöründedir; nasıl çalıştırılacakları o klasördeki README'de yazıyor.
