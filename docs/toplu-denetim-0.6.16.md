# Akış Kurgu AI 0.6.16 kural tabanlı denetimi

Başlangıç noktası 0.6.15 (`6e15aa6`). Windows 11, Python 3.12 ve FFmpeg 9.0.2 kullanıldı.

## Yöntem

Önceki denetimler tek tek seçilmiş senaryoları sınıyordu. Seçilmemiş birleşimlerdeki hatalar sonraki turlarda ortaya çıkıyordu. Bu turda senaryo yerine her düzenleme işleminin vermesi gereken sonuç bir kural olarak yazıldı. Ardından iki tarayıcı binlerce rastgele projede bu kuralları her kare için denetledi.

**Model tarayıcısı** (`scripts/media-audit/fuzz.py`) her denemede rastgele bir proje kurar. Projede farklı kare hızları, dokuz klip hızı, boşluklar, geçişler, ses düzeyleri, ayrı ses izi, kelime kelime altyazı, el çizimi işaret ve işaretçiler bulunur. Projeye rastgele sırayla en fazla sekiz işlem uygulanır. Her işlemden sonra zaman çizelgesindeki her karede gösterilen kaynak karesi, ses düzeyi, vurgulanan kelime, işaret animasyonu ve geçiş adımı işlem öncesiyle karşılaştırılır.

| İşlem | Kural |
| --- | --- |
| Bölme | Hiçbir kare değişmez. |
| Aralık silme | Aralıktan sonraki kareler aralığın başına kayar; başka bir şey değişmez. |
| Shorts ve uzun dışa aktarma parçası | Parça, bütün kurgunun aynı karelerini gösterir. |
| Klip silme | Klibin kareleri gider; aynı izde sonraki kareler sola kayar. |
| Sessizlik ve diğer yerel kesimler | Sonuç, aynı kareleri ana izden silmekle aynıdır. Altyazı ve işaretler görüntüyü izler. |
| Değişiklik içermeyen kurgu planı | Ana videonun sonuna kadar hiçbir kare değişmez. |
| Kenarı kırpıp geri uzatma | Proje eski haline döner. |
| Hızı değiştirip geri alma | Klip aynı görüntüyü oynatır. |
| Kaydetme ve açma | Hiçbir kare değişmez; ikinci kayıt ilkiyle aynıdır. |

**Dışa aktarma tarayıcısı** (`scripts/media-audit/render_fuzz.py`) her karesine kendi numarası ve dosya kimliği basılmış üç kaynak video üretir. Kaynaklardan biri 25 fps, ikisi 30 fps'dir. Rastgele kurgular FFmpeg ile dışa aktarılır. Çıktının her karesi geri okunur ve modelin o karede göstermesi gereken kaynak karesiyle karşılaştırılır. Her projeden iki rastgele kare ayrıca önizleme yoluyla üretilip denetlenir. Geçiş sırasındaki kareler iki görüntüyü karıştırdığı için atlanır.

## Bulunan ve düzeltilen hatalar

| Alan | 0.6.15'te tekrar üretilen sorun | 0.6.16 |
| --- | --- | --- |
| Dışa aktarma | Hızı değiştirilmiş kliplerde ve kare hızı projeden farklı kaynaklarda bazı kareler atlanıyor, yerine sonraki kare iki kez gösteriliyordu. FFmpeg'e verilen kare numarası kayan noktalı bölmede bir eksik çıkıyordu (25 fps'de 28 / 25 / 0,04 = 27,999…). 25 fps projede klip başına 14 kareye kadar, 30 fps projede klibin 4. saniyesi civarında görüldü. Etkilenenler arasında 1× hızda bile 30 fps projeye eklenmiş 25 fps video vardı. | Kare numarası yuvarlanıyor. 4 kare hızı, 2 kaynak türü, 9 hız ve kesirli başlangıçtan oluşan 112 durumun 53'ünde eski kod yanlış kare üretti; yeni kodda sıfır. |
| Kelime kelime altyazı | Bölünen, aralığı silinen ya da Shorts'a ayrılan altyazının son kelimeden sonraki parçası, vurgulu kelime yerine bütün cümleyi düz yazı olarak gösteriyordu. | Parçanın başında vurgulu olan kelime parçada kalıyor. |
| Altyazı kenarını sürükleme | Başlangıç kenarı içeri çekilip geri getirilince kırpılan kelimeler kayboluyordu. Kenar tek sürüklemede ileri geri hareket ettirilince de oluyordu. | Kırpılan kelimeler, sondan kırpmada olduğu gibi saklanıyor ve kenar geri gelince dönüyor. Kırpılmış kısımdaki kelimeler çizilmiyor. |
| Geçişler | Geçiş klibin yarı uzunluğuyla sınırlandığı ve bu sınır her seferinde yeniden hesaplandığı için bölme, kırpma ve aralık silme geçişi kısaltıyordu. Örneğin 30 karelik klip 12. karede bölününce 10 karelik geçiş 6 kareye iniyordu. Geçişin içinden bölmek ilk parçadaki geçişi hızlandırıyordu. | Geçiş uzunluğu bir kez yazılıyor ve klip kesilince değişmiyor. Eski projeler açılırken geçişler o anki uzunluklarıyla yazılıyor; görüntü değişmiyor. |
| Yerel kesimler | Sessizlik, dolgu sözcüğü, tekrar ve konuşmacı temizliği ile ritme oturtma, açılış klibinin geçişini siliyordu. | Açılış klibinin geçişi kalıyor. Yapay zekâ planları ilk klibe yeni geçiş koymamaya devam ediyor. |
| Klip hızı ve altyazı | Ana klip 3× veya 4× hızlandırılınca altyazıdaki bazı kelimeler sıfır uzunluk alıyordu. | Her kelime en az bir kare sürüyor. |

Her düzeltme için `tests/test_project_audit_20261121.py` dosyasında bir test var. Testlerin sekizi 0.6.15 koduyla başarısız oluyor. Kalan ikisi eski projelerin aynı geçişle açıldığını ve saklanan kelimelerin yerel kesimi bozmadığını denetliyor.

## Düzeltmeden sonraki ölçümler

- Model tarayıcısı: 10.000 rastgele proje ve her birinde en fazla sekiz işlem çalıştırıldı. Kurala aykırı kare bulunmadı.
- Dışa aktarma tarayıcısı: 140 rastgele kurgu dışa aktarıldı ve her karesi okundu. Her kurgudan iki önizleme karesi de denetlendi. Fark bulunmadı. Ayrıca 112 durumluk tek klip taramasında, 200 kareye kadar kliplerde fark bulunmadı.
- Shorts bölme: 20.000 rastgele süre, sınır ve duraklama listesinde parçalar boşluksuz, çakışmasız ve sınırın altında kaldı.
- Uzun dışa aktarma parçaları: 3.000 projede parçalar boşluksuz birleşti. Birleşen parçalar bütün kurguyla kare kare aynıydı.
- Genel test kümesi: 1.050 test.

Model tarayıcısı her GitHub Windows derlemesinde 2.000 projeyle, dışa aktarma tarayıcısı 30 kurguyla çalışıyor. Kurallardan biri bozulursa derleme ve yayın duruyor.

## Bilinçli davranışlar

Aşağıdakiler hata sayılmadı. Tarayıcı bunları kural olarak kabul ediyor.

- Hızı değiştirip geri almak, klip tam kareye sığmadığında birkaç kare fark yaratabilir. Örneğin 31 karelik klip 2× hızda 15,5 kare olamaz.
- Geçişin tam içinden bölünen klipte geçiş ikinci parçada biter. İlk parça bölmeden önceki karelerini aynen gösterir.
- Yerel kesimde konuşma anı kesilen kelime altyazıdan da çıkar. Kesim bir işaretin başlangıcını alırsa işaretin giriş animasyonu baştan oynar.
- Yerel kesimden sonra ana videonun bittiği yerden sonraki ses, işaret ve işaretçiler ana videoyla birlikte biter.
- Kare hızı projeden farklı bir kaynak kesirli hızda oynatılırken önce proje karelerine oturtulur.

## Kapsam dışı

Tarayıcılar zaman çizelgesi modelini, düzenleme işlemlerini, kaydetmeyi, Shorts ve uzun dışa aktarma bölmesini ve dışa aktarılan görüntü karelerini denetler. Sesin kulakla duyulan kalitesi, yapay zekâ sağlayıcılarının gerçek yanıtları, Whisper doğruluğu, kamera ve mikrofon kaydı ve FCPXML'in Final Cut Pro veya DaVinci Resolve içinde açılması bu turda ölçülmedi.

## Yeniden çalıştırma

```powershell
./scripts/media-audit/run-audit.ps1 -Project .
.venv/Scripts/python.exe scripts/media-audit/fuzz.py . 10000
.venv/Scripts/python.exe scripts/media-audit/render_fuzz.py . 100
```

Tarayıcılar her hatayı yeniden üreten tohum (seed) değerini ve işlem sırasını JSON olarak yazar.
