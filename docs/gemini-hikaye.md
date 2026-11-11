# Gemini ile hikâye, görsel ve video

Hikâye Stüdyosu (kenar çubuğu → **Hikâye Stüdyosu**) üç ayrı Gemini çağrısını birbirine bağlar:

```
öncül → hikâye künyesi (karakterler, üslup, dünya) → sahne metni
      → sahnenin görsel istemi → görsel (Nano Banana)
      → hareket istemi + görsel → video (Omni Flash) → proje medyası
```

Kod: `akis/gemini_api.py` (ham HTTP çağrıları), `akis/story_service.py` (sistem talimatı, künye, bağlam
yönetimi, model seçimi, maliyet tahmini), `akis/story_workers.py` (arka plan işçileri),
`akis/story_dialog.py` (pencere). Anahtar AI sekmesindeki Gemini anahtarıdır.

## Metin (kurgu)

- Uç nokta: `POST /v1beta/models/{model}:generateContent`, başlık `x-goog-api-key`.
- Gemini 3.6 ve sonrası `temperature`, `top_p`, `top_k` değerlerini yok sayar; gönderilmez. Üslup yalnızca
  sistem talimatı ve üslup profilleri (edebi, sade, masalsı, noir…) ile yönlendirilir.
- `thinkingLevel` her istekte açıkça verilir (`low` / `medium` / `high`); çıktı sınırı düşünme
  token'larını da içerdiği için pay bırakılır.
- Bağlam sırası her istekte aynıdır: sistem talimatı → hikâye künyesi (bayt düzeyinde aynı kalır, böylece
  Google'ın örtük önbelleği devreye girer) → eski sahnelerin özeti ve süreklilik notları → son sahneler →
  görev. Her sahneden sonra ucuz bir çağrı özeti ve süreklilik notlarını günceller.
- Model yoğunsa (503) veya yanıt vermezse metin için yedek zincir kullanılır:
  `gemini-4-argon → gemini-3.8-flash → gemini-3.6-flash`. Görsel ve videoda otomatik yedek yoktur (maliyet).

## Hangi model, ne zaman

Fiyatlar 11.11.2026 tarihinde Google'ın fiyat sayfasından alınmıştır (1 milyon token başına, USD).

| İş | Model | Not |
|---|---|---|
| Taslak, deneme, özet, görsel istemi | `gemini-3.8-flash` | 0,75 giriş / 3,75 çıkış (01.01.2027'den sonra 1,50 / 7,50); ücretsiz katman var |
| Son okuma, karmaşık olay örgüsü | `gemini-4-argon` | 2 / 10 (01.12.2026'dan sonra 4 / 20); ücretsiz katman yok |
| Taslak görsel | `gemini-nano-banana-2.1`, 1K | ≈ 0,034 $ / görsel |
| Son görsel | `gemini-nano-banana-2.1`, 2K | ≈ 0,050 $ / görsel (4K ≈ 0,113 $) |
| Hızlı küçük görsel | `gemini-3.1-flash-lite-image` | çoklu referansta zayıf |
| Video önizleme | `gemini-omni-1.2-flash`, 720p, 5–8 sn | fiyat doğrulanamadı |
| Son video | `gemini-omni-1.2-flash`, 1080p | 3–15 sn, yalnızca 16:9 ve 9:16 |

## Görsel çağrısı (Nano Banana)

```python
from pathlib import Path
from akis import gemini_api

result = gemini_api.generate_image(
    key, 'gemini-nano-banana-2.1',
    'Cinematic still: a young woman in a red raincoat running toward a ferry on a rainy Istanbul night',
    aspect_ratio='16:9',          # 1:1, 9:16, 16:9, 4:5, 21:9 …
    image_size='2K',              # 1K, 2K, 4K (büyük K zorunlu)
    references=[gemini_api.load_image('elif.png', role='character', label='Elif'),
                gemini_api.load_image('stil.png', role='style')],
)
Path('sahne.png').write_bytes(result.data)
```

Gönderilen gövde: `contents[0].parts` içinde önce metin, sonra `inline_data` olarak referans görseller;
`generationConfig.responseModalities = ["IMAGE"]`, `generationConfig.imageConfig = {aspectRatio, imageSize}`.
Yanıtta görsel `candidates[0].content.parts[].inlineData.data` alanında base64 olarak gelir.

## Video çağrısı (Omni Flash)

```python
# Metinden video
clip = gemini_api.generate_video(key, 'A ferry leaving a rainy Istanbul pier at night, slow push-in',
                                 aspect_ratio='16:9', resolution='720p', duration=6)
# Mevcut görselden video
clip = gemini_api.generate_video(key, 'She runs toward the ferry, camera tracks alongside, rain falling',
                                 images=[gemini_api.load_image('sahne.png')], duration=6)
Path('sahne.mp4').write_bytes(clip.data)
```

Uç nokta: `POST /v1beta/interactions`. Gövde: `{"model": "gemini-omni-1.2-flash", "input": <metin veya
[görsel, metin] parçaları>, "response_format": {"type": "video", "aspect_ratio", "resolution", "duration": "6s"}}`.
Üretim eşzamanlıdır ve dakikalar sürebilir; zaman aşımı 15 dakikadır ve istek asla otomatik yinelenmez.
Yanıtta video `steps[].content[]` içindeki `type: "video"` öğesinde base64 MP4 olarak gelir.

## Canlı denemede görülenler (11.11.2026)

- `gemini-3.6-flash` ile metin üretimi çalıştı (8 sn).
- `gemini-3.8-flash` bir denemede 503 "yoğun talep" verdi, diğerinde 90 sn içinde yanıt vermedi; yedek zincir
  bu yüzden var.
- Ücretsiz katmandaki anahtarda görsel ve video modellerinin günlük kotası 0'dır (HTTP 429, "limit: 0 …
  Free Tier"). Uygulama bu durumda yeniden denemeden "faturalandırmayı etkinleştirin" iletisi gösterir.
- Görsel ve video istekleri adres, başlık ve kota denetimine kadar kabul edildi; **başarılı bir görsel veya
  video yanıtı canlı olarak görülmedi**. Yanıt ayrıştırma belgelerdeki biçime göre yazıldı ve sahte
  yanıtlarla test edildi.
