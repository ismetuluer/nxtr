# E aşaması: Terminoloji (tasarım)

Kaynak: `docs/inceleme/2026-11-09-kullanilabilirlik.md` §2.4, §2.13 (Ollama tarafı), §2.14, §4 E. Hedef 0.53.0.

1. **Ad:** oyun terimleri listesi her yerde **Terminoloji** (menü, kısayol, pencere, bildirim, denetim türü
   "Terminoloji"); yazım listesi **Yazım sözlüğü** olarak kalır. Kod içi adlar (`glossary`) değişmez.
2. **Sade pencere:** sütunlar Terim · Karşılık · Not; "Daha Fazla" kalkar; küçük düğmeler: Terim Ekle, Sil, İçe Aktar,
   Dışa Aktar, Terim Öner, Kitaplık ▸. Boş satır kaydedilmez (mevcut).
3. **Kısa hatalar:** Terim Öner'de Ollama yok/kapalı → bildirim "Ollama'ya bağlanılamadı" + [Ayarları Aç] [Kapat];
   uzun açıklama yok.
4. **Terminoloji kitaplığı** (`%LOCALAPPDATA%/NXCeviri/terminoloji/<ad>.json`): pencereden "Kitaplığa Kaydet…" (adla),
   "Kitaplıktan Ekle ▸ <liste>" (birden çok liste birleştirilebilir; aynı terim projede farklıysa projeninki korunur,
   kaç terimin eklendiği/atlandığı söylenir), "Listeyi Sil".
5. **Seçili satırları terminolojiye ekle** (sağ tık ve Çeviri menüsü, `Ctrl+Shift+G`; Terminoloji penceresi
   `Ctrl+Alt+G`): kaynak ve çeviri kontrol kodu, satır sonu, baştaki/sondaki noktalama, sayı ve sembollerden
   ayıklanır; boş kalan ya da çevirisiz satır atlanır; zaten olan terim atlanır, farklı karşılığı olan "çakışma"
   olarak gösterilir. Önce onay listesi (işaretini kaldırdığın eklenmez; çakışmada yeni karşılık seçilirse güncellenir).
6. **Kanonik terimler Ollama'ya:** çeviri ve yeniden çeviride, terminolojide olmayan kanonik terimler (kendi başına
   satır olan kısa özel adların en sık çevirisi; `core/qa/terms.canonical_terms`) partiye sözlük maddesi olarak eklenir
   (not: "oyunda böyle çevrildi"); yalnızca o partide geçenler gider. "Terim değil" listesindekiler gitmez.

Test: ad değişikliği (arayüz metinleri), kitaplık kaydet/yükle/birleştir/bozuk dosya, satırdan terim ayıklama,
çakışma, onay penceresi, kanonik terimlerin istekte görünmesi, kısa hata bildirimi.
