# Gerçek arayüz akışları

Bu betikler programı ayrı bir süreç olarak başlatır. Düğmelere Windows UI Automation ile, kısayollara ve zaman çizelgesine gerçek tuş ve fare olaylarıyla basar. Dosya pencereleri Windows'un kendi pencereleridir. Her akış, ekrandaki yazıyı değil üretilen dosyayı ölçer: dışa aktarılan videonun her karesinde gösterilen kaynak karesini ve her yarım saniyesinde duyulan kaynak anını okur.

Masaüstünde çalışırlar ve fareyi ve klavyeyi kullanırlar; çalışırken bilgisayarı kullanmayın. Ayarlar geçici bir dosyaya yazılır. Kurtarma klasöründe yalnız bu betiklerin oluşturduğu dosyalar silinir. Kayıt akışı Videolar klasörüne yazdığı kaydı siler.

## Kurulum

`pywinauto` programın bağımlılığı değildir. Bu klasörün yanına kurun (BSD lisanslı):

```powershell
.venv/Scripts/python.exe -m pip install --target scripts/media-audit/ui-flows/.uia pywinauto
```

Başka bir klasöre kurduysanız `AKIS_UIA_LIBS` ortam değişkeniyle gösterin.

## Çalıştırma

Son bağımsız değişken verilirse aynı akış paketlenmiş program üzerinde çalışır.

```powershell
$work = "$env:TEMP\akis-ui"
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_edit.py "$work\edit" [dist\AkisKurguAI\AkisKurguAI.exe]
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_record.py "$work\record" [exe]
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_edges.py "$work\edges" [exe]
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_edges2.py "$work\edges" [exe]
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_broken.py "$work\edges" [exe]
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_unsaved.py "$work\edges" [exe]
```

| Betik | Akış |
| --- | --- |
| `flow_edit.py` | Video ekle → böl (S) → kırp (Q) → geri al/yinele → kaydet → kapat → aç → dışa aktar; çıktının her karesi ve sesi |
| `flow_record.py` | Kayıt al → önizleme → başlat → küçülme ve çubuk → çubuktan durdur → projeye ekleme → MP4'ün süresi ve kareleri |
| `flow_edges.py` | Dışa aktarmayı iptal edip yeniden deneme; dışa aktarma sürerken kapatma |
| `flow_edges2.py` | Aynı anda iki iş; başka programın açık tuttuğu çıktı; var olan dosya ve kaynak videonun adı; taşınmış medya |
| `flow_broken.py` | Yarım, boş ve daha yeni sürümlü proje dosyaları |
| `flow_unsaved.py` | Düzenlemeden sonra başka proje açma ve pencereyi kapatma |

Her betik sonuçlarını çalışma klasörüne JSON olarak yazar.
