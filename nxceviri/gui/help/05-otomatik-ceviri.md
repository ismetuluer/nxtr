# Otomatik Çeviri

**Çeviri → Otomatik Çeviri** (`Ctrl+T`) satırları bir yapay zekâ modeliyle çevirir.

## Sağlayıcı

- **Ollama** (bilgisayarınızda, ücretsiz): Ollama'yı kurup bir model indirin; uygulama yüklü modelleri listeler.
  **Bağlantıyı Test Et** her şeyin hazır olduğunu söyler.
- **DeepL** (internet, API anahtarı): anahtar Windows Kimlik Bilgisi Yöneticisi'nde saklanır, proje dosyasına yazılmaz.
  Kalan karakter kotası gösterilir.
- **Claude**, **Gemini** ve **OpenAI uyumlu** hizmetler (OpenAI, OpenRouter, Groq, Mistral, DeepSeek; bilgisayarınızda
  LM Studio ya da kendi sunucunuz için **Özel adres**): hizmetin sitesinden aldığınız API anahtarını pencerede
  yapıştırıp **Anahtarı Kaydet**'e basın. Her hizmetin anahtarı ayrı saklanır. **Modelleri Listele** hizmetteki
  modelleri getirir; listeden seçin ya da adını yazın. Metinler hizmete gönderilir; kullanım ücreti hizmetteki
  hesabınızdan düşer (pencere fiyat göstermez).
- **Google Translate** (internet, API anahtarı): DeepL gibi klasik çeviri yapar.

**Redaksiyon** ve **Bu iş için talimat** yalnızca yapay zekâ modelleriyle (Ollama, Claude, Gemini, OpenAI uyumlu)
çalışır; DeepL ve Google Translate talimat izleyemez.

## İş türü ve kapsam

- **Çevir** boş satırları, **Yeniden çevir** seçilenleri baştan çevirir; **Redaksiyon** var olan çeviriyi talimatla
  düzeltir.
- Kapsam: tüm satırlar, seçili satırlar ya da onların grubu (ör. bütün menüler), süzgeçte görünenler ya da bir anahtar
  deseni (`d0*` gibi).

## Daha iyi sonuç için

- **Oyun hakkında:** türü, dönemi, karakterlerin konuşma tarzını yazın; her işte modele gider.
- **Bu iş için talimat:** yalnızca bu işe özel istek ("hitaplar 'siz' olsun"). Sık kullandıklarınızı **Kitaplık**'a
  kaydedin.
- **Terminoloji:** adlar ve sabit karşılıklar modele terim olarak verilir.

## Güvenlik

Kontrol kodları çeviriden önce `⟦1⟧` gibi işaretlere dönüştürülür ve sonra geri konur; sayısı ya da sırası bozulan
satır **Hatalı** olur ve dışa aktarılmaz. İş yarıda kalırsa (bağlantı koptu, iptal) yapılanlar kaydedilir; yeniden
başlatınca kaldığı yerden devam eder. İş bitince bildirim gelir; **Değişiklikleri Gör** ile ne değiştiğine bakın.
