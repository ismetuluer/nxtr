---
name: nxtr-grafik
description: NXTR'de oyundaki menü, düğme, başlık veya hikâye kartı gibi resimlerin içindeki yazıları çevirmek gerektiğinde kullan (yazı çeviri tablosunda yok, "ara" bulamıyor, metin resimde).
---

# NXTR: grafik (resimlerdeki yazılar)

1. `AGENTS.md`'yi baştan sona oku (oyun resimleri telifli: depoya konmaz, paylaşılmaz; ana koda yazma yasağı).
1b. Oyunun eklentisi varsa önce klasöründeki (eklenti yoksa oyun klasöründeki) `NOT.md` ("Resimdeki yazılar") ve `CALISMA_GUNLUGU.md`'yi oku;
   resimleri yeniden arama. Hangi arşivde hangi resim, kopyaları, oyunda kullanılan kopya ve kullanıcının resim
   koyduğu klasör bulduğun anda bu iki dosyaya yazılır. Rehberdeki "Önceki oyunlardan tuzaklar" bölümünü atlama;
   yeni tuzağı oyun adı vermeden oraya ekle.
2. `docs/rehber/grafik.md` rehberini baştan sona oku; örnekler için `docs/formats/nni.md` ("Grafikler") ve
   `docs/formats/fsd-msg.md`.
3. Yazı içeren resimleri tespit et, sayısını ve örnek adlarını kullanıcıya bildir. Yazının gerçekten resimde olduğunu
   `python -m nxceviri.arac ara "<yazı>" …` ile kanıtla, resim biçimini söyle.
4. Kullanıcı isterse `grafik_temizleme/orijinal` (eklenti çıkarır) ve `grafik_temizleme/turkce` (kullanıcı
   Türkçeleştirir, aynı ad; eski `temiz` adı hâlâ okunur) düzenini kur. Kullanıcıyı resim hazırlama konusunda
   yönlendir; çizimi ajan yapmaz. Hazırlanan resimleri uygulamada **Kontrol Et → Grafik** sekmesinde denetlet
   (boyut, saydamlık, eksik, değişmemiş; onay); eklentisiz oyunda klasör orada **Klasör Seç…** ile seçilir.
5. Resim kodu (çıkarma, çözme/kodlama, geri yazma) oyunun eklentisinin içinde yazılır, `nxceviri/` altına yazılmaz.
   Geri yazmayı testle (aynı biçim, boyut, mip), moda yerleştir. Cihazda görsel doğrulamayı kullanıcıdan iste; BC7
   gibi kayıplı kodlama sınırlarını raporla.
