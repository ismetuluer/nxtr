---
name: nxtr-yeni-oyun
description: NXTR'de yeni bir Switch oyununun metinlerine erişmek, çeviri tablosuna aktarmak ya da tanınmayan bir metin biçimi için eklenti yazmak gerektiğinde kullan (örn. "şu oyunu çevirmek istiyorum", "taramada 0 metin çıkıyor", "desteklenmeyen biçim", "eklenti yaz").
---

# NXTR: yeni oyun

1. `AGENTS.md`'yi baştan sona oku; anahtar, oyun dosyası, orijinal dosya ve **ana koda yazma yasağı** kuralları
   bağlayıcıdır.
2. `docs/rehber/yeni-oyun.md` rehberini baştan sona oku ("Bağlayıcı kurallar" dahil). Eklenti yazılacaksa
   `docs/rehber/eklenti-yazma.md`'yi de oku (izinli çekirdek modülleri, çok dosyalı eklenti, font/resim kancaları).
3. Bütün kod (metin, font, resim) **tek bir eklenti klasöründe** durur; `nxceviri/` altında dosya oluşturma ya da
   değiştirme. Gereken yardımcı yoksa ya da izinli değilse eklentinin içine ayrı modül olarak yaz (`from . import x`).
   "Eklenti oluşturamıyorum" kabul edilmez: yapabildiğin her parçayı teslim et, imkânsız olanı komut çıktısıyla kanıtla.
4. Rehberin adımlarını sırayla izle: `python -m nxceviri.arac teshis …` (her metin adayı dosya için kapsam tablosu) →
   `ara` → motora göre yol → `eklenti-olustur` (önce test) → `dogrula` → `python -m nxceviri.arac font …` (eksik
   harfleri önce yamayla kapat; `unsupported_letters` son çare) → resimdeki yazıları say ve bildir (istenirse
   `grafik_temizleme/orijinal` + `turkce`) → uygulamada Tara/Çevir/Dışa Aktar. Kullanıcı başka dil demedikçe yalnızca
   İngilizce. Çözülmüş biçimler için `docs/formats/README.md`'ye bak; çözülmüşse yeni kod yazma.
5. Bitti demeden: `dogrula` geçti ve `İçe aktarma:` bulgusu yok, `python -m nxceviri.arac eklentiler` temiz,
   `git status --porcelain nxceviri/` boş, font durumu raporda; komut çıktılarını göster. Cihazda denenmeyen işi öyle
   raporla.
6. Kullanıcıya kısa Türkçe rapor ver (rehberin "Kullanıcıya rapor" bölümü). Kurulum eksikse önce `docs/rehber/baslarken.md`.
