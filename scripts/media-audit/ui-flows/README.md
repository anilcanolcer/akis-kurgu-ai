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
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_publish.py "$work\publish" [exe]
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_tools.py "$work\tools" [exe]
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_settings.py "$work\settings" [exe]
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_language.py "$work\language" [exe]
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_templates.py "$work\templates" [exe]
.venv/Scripts/python.exe -X utf8 scripts/media-audit/ui-flows/flow_ai.py "$work\ai"
```

`flow_publish.py` bölümleri `FLOW_SECTIONS` ortam değişkeniyle seçilebilir (örn. `cut,fcpxml,export cut`).

| Betik | Akış |
| --- | --- |
| `flow_edit.py` | Video ekle → böl (S) → kırp (Q) → geri al/yinele → kaydet → kapat → aç → dışa aktar; çıktının her karesi ve sesi |
| `flow_record.py` | Kayıt al → önizleme → başlat → küçülme ve çubuk → çubuktan durdur → projeye ekleme → MP4'ün süresi ve kareleri |
| `flow_edges.py` | Dışa aktarmayı iptal edip yeniden deneme; dışa aktarma sürerken kapatma |
| `flow_edges2.py` | Aynı anda iki iş; başka programın açık tuttuğu çıktı; var olan dosya ve kaynak videonun adı; taşınmış medya |
| `flow_broken.py` | Yarım, boş ve daha yeni sürümlü proje dosyaları |
| `flow_unsaved.py` | Düzenlemeden sonra başka proje açma ve pencereyi kapatma |
| `flow_publish.py` | Üç biçimde dışa aktarma, Shorts'a bölme, öne çıkan anlar, kesim → FCPXML, normal ve hızlı dışa aktarma, sessizlikleri çıkararak toplu dışa aktarma; her çıktının kareleri ve sesi |
| `flow_tools.py` | Başlık katmanı, 2× hız, −14 LUFS, Windows sesiyle seslendirme, kapanmayla kesilen oturumun kurtarılması, yerel Whisper altyazısı, sessizlikleri çıkarma |
| `flow_settings.py` | Ayar bölümü bozuk projeleri “Proje aç” ile açma; gösterilen her ileti |
| `flow_language.py` | Arayüzü English yapıp ana pencerede ve on pencerede Türkçe kalan yazıları arama; geri dönüş; açık/koyu tema |
| `flow_templates.py` | Hazır şablon uygulama ve geri alma; Şablonlarım'a kaydetme, uygulama, silme (şablon dosyası yedeklenip geri konur) |
| `flow_ai.py` | “Prompt ile kurgula”, yapay zekâ servisi yerine sabit yanıt veren `fake_ai_launch.py` ile; plan onayı, dışa aktarılan kareler, geri al/yinele, plan olmayan yanıt |

`longmedia.py` uzun deneme videosu üretir (64 sn'ye kadar; her karede kendi numarası, her saniyede 1 kHz altında kendi perdesi, her 4 sn'de 1 sn duraklama). `probe_*.py` betikleri, akışlarda görülen bir belirtinin programdan mı betikten mi geldiğini ayırmak için kullanılan küçük yoklamalardır.

Her betik sonuçlarını çalışma klasörüne JSON olarak yazar.
