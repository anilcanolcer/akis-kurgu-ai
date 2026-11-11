# Güvenlik yazılımları ve kod imzalama

## Sorun

Kurulum paketi ve uygulama dijital olarak imzalı değildir. İmzasız, yeni ve az indirilen dosyaları güvenlik
yazılımları "tanınmayan" sayar; kurumsal ürünler (ör. Bitdefender Endpoint Security) bunları çalışırken
durdurabilir veya silebilir. 0.4.2'ye kadarki güncelleyici ayrıca kötü amaçlı yazılımlara benzeyen bir
yol izliyordu: gizli bir PowerShell `-EncodedCommand` betiği, indirilen imzasız kurucuyu sessizce ve yönetici
olarak çalıştırıyordu. Kurucu yarıda kesilince program klasörü yarım kalıyordu.

## Bu sürümde değişenler

- PowerShell yardımcısı tamamen kaldırıldı. Uygulama, SHA-256 doğrulamasından sonra kurucuyu doğrudan başlatır.
- Kurucu görünür bir ilerleme penceresiyle çalışır; uygulamanın kapanmasını kendisi bekler ve bitince
  uygulamayı kendisi açar.
- Eski sürüm silinmez, `.old` olarak kenara alınır; herhangi bir hatada geri yüklenir.
- Paket UPX ile sıkıştırılmaz (UPX'li PyInstaller paketleri sık sık yanlış alarm üretir).
- `AkisKurguAI.exe` ve kurucu, sürüm ve yayıncı bilgisi (sürüm kaynağı) taşır.

Bunlar yanlış alarmları azaltır, ama imzanın yerini tutmaz.

## Kalıcı çözüm: imzalama

1. **Açık kaynak projeler için ücretsiz imzalama:** SignPath Foundation, GitHub'da barınan açık kaynak
   projelere ücretsiz kod imzalama verir. Başvuru için projenin açık kaynak lisansı, herkese açık deposu ve
   derlemenin GitHub Actions üzerinde yapılması gerekir. Onaydan sonra derleme çıktısı (uygulama exe'si ve
   kurucu) GitHub Actions adımıyla SignPath'e gönderilip imzalı olarak geri alınır.
2. **Ücretli seçenek:** Microsoft'un bulut imzalama hizmeti (Trusted Signing / Azure Artifact Signing) aylık
   düşük bir ücretle `signtool` üzerinden imzalama sağlar.

İmzalama eklendiğinde derleme iş akışında, kurucu oluşturulduktan sonra ve yayın adımından önce bir imzalama
adımı gerekir; `scripts/check-windows-signatures.ps1` imzaları denetler.

## Yanlış alarm bildirimi

İmza olmadan da yapılabilecekler:

- Güvenlik üreticisine "false positive" bildirimi: Bitdefender ve Microsoft (Defender) dosya gönderme
  sayfaları üzerinden kurucuyu ve SHA-256 değerini gönderin. Onaylanan dosya o üreticide engellenmez; her
  yeni sürüm için yinelemek gerekir.
- Kurumsal Bitdefender'da yönetici, uygulama klasörünü ve güncelleme klasörünü
  (`%LOCALAPPDATA%\AkisStudio\Akış Kurgu AI\updates`) istisnaya ekleyebilir.

## İndirilen dosyayı doğrulama

Her sürümün kurucusunun SHA-256 değeri GitHub sürüm sayfasındaki dosya ayrıntılarında yazar. Denetlemek için:

```powershell
Get-FileHash .\AkisKurguAI-Setup.exe -Algorithm SHA256
```

## Henüz yapılmayan

- Yöneticisiz (kullanıcı düzeyinde) kurulum: kurucu hâlâ yönetici izni ister. Kullanıcı klasörüne yönetici
  izni istemeden kurulum, güvenlik yazılımlarının en az tepki verdiği yoldur ve sıradaki iyileştirmedir.
