---
name: nxtr-yeni-oyun
description: NXTR'de yeni bir Switch oyununun metinlerine erişmek, çeviri tablosuna aktarmak ya da tanınmayan bir metin biçimi için eklenti yazmak gerektiğinde kullan (örn. "şu oyunu çevirmek istiyorum", "taramada 0 metin çıkıyor", "desteklenmeyen biçim", "eklenti yaz").
---

# NXTR: yeni oyun

1. `AGENTS.md`'yi baştan sona oku; anahtar, oyun dosyası ve orijinal dosya kuralları bağlayıcıdır.
2. `docs/rehber/yeni-oyun.md` rehberini baştan sona oku. Eklenti yazılacaksa `docs/rehber/eklenti-yazma.md`'yi de oku.
3. Rehberin adımlarını sırayla izle: `python -m nxceviri.arac teshis …` → `ara` → motora göre yol → `eklenti-olustur`
   (önce test) → `dogrula` → uygulamada Tara/Çevir/Dışa Aktar. Çözülmüş biçimler için `docs/formats/README.md`'ye bak;
   çözülmüşse yeni kod yazma.
4. `dogrula` geçmeden bitti deme; komut çıktısını göster. Cihazda denenmeyen işi öyle raporla.
5. Kullanıcıya kısa Türkçe rapor ver (rehberin "Kullanıcıya rapor" bölümü). Kurulum eksikse önce `docs/rehber/baslarken.md`.
