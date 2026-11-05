---
name: nxtr-grafik
description: NXTR'de oyundaki menü, düğme, başlık veya hikâye kartı gibi resimlerin içindeki yazıları çevirmek gerektiğinde kullan (yazı çeviri tablosunda yok, "ara" bulamıyor, metin resimde).
---

# NXTR: grafik (resimlerdeki yazılar)

1. `AGENTS.md`'yi baştan sona oku (oyun resimleri telifli: depoya konmaz, paylaşılmaz).
2. `docs/rehber/grafik.md` rehberini baştan sona oku; örnekler için `docs/formats/ys-origin.md` ("Grafikler") ve
   `docs/formats/dmc1.md`.
3. Yazının gerçekten resimde olduğunu `python -m nxceviri.arac ara "<yazı>" …` ile kanıtla, resim biçimini ve sayısını
   kullanıcıya söyle.
4. `grafik_temizleme/orijinal` (uygulama çıkarır) ve `temiz` (kullanıcı Türkçeleştirir, aynı ad) düzenini kur. Kullanıcıyı
   resim hazırlama konusunda yönlendir; çizimi ajan yapmaz.
5. Geri yazmayı testle (aynı biçim, boyut, mip), moda yerleştir. Cihazda görsel doğrulamayı kullanıcıdan iste; BC7 gibi
   kayıplı kodlama sınırlarını raporla.
