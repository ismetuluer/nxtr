---
name: nxtr-font
description: NXTR'de oyunda Türkçe harfler (ğ ş ı İ gibi) kutucuk ya da yanlış harf olarak görünüyorsa, font yaması veya harf dönüştürme gerekiyorsa ya da yeni bir font biçimi yamalanacaksa kullan.
---

# NXTR: font ve Türkçe harfler

1. `AGENTS.md`'yi baştan sona oku (ana koda yazma yasağı dahil).
1b. Oyunun eklentisi varsa önce klasöründeki (eklenti yoksa oyun klasöründeki) `NOT.md` ("Fontlar" bölümü) ve `CALISMA_GUNLUGU.md`'yi oku;
   orada yazan font incelemelerini baştan yapma. Bulduğun her şeyi (font dosyaları, biçim, harf kodlaması, yama
   sonucu) bulduğun anda `NOT.md`'ye, adımları günlüğe yaz; başka oyunda da geçerli tuzağı oyun adı vermeden
   `docs/rehber/font.md` "Bilinen tuzaklar"a ekle.
2. `docs/rehber/font.md` rehberini baştan sona oku; ayrıntı için `docs/formats/tmp-font.md`.
3. Önce `python -m nxceviri.arac font <oyun dosyaları>` çalıştır (sonuç a/b/c). Sonra uygulamada Kontrol Et → Fontları Tara çalıştır ve
   tablodaki sayıları (eksik harfler, "Yamayla eklenir") kullanıcıya aktar. Sırayla: fontta zaten var mı → yerleşik font
   yaması → yerleşik yama tanımıyorsa oyunun eklentisinde yazılan yama → harf dönüştürme (yalnızca yamanın kanıtla
   imkânsız olduğu harflerde).
4. Yeni font biçiminde yama kodu **oyunun eklentisinin içinde** yazılır (`eklentiler/<ad>/font.py`), `nxceviri/`
   altına yazılmaz; moda `derived_files` / `support_files` / `game_file_patches` ile girer. Önce biçimi çöz, elle
   üretilmiş örnek fontla test yaz, yazılan dosyayı yeniden okuyup harfin gerçekten var olduğunu doğrula.
5. Dışa aktar, `NXTR - Bilgi.txt`'teki eklenen/eklenemeyen harfleri raporla. Cihazda göz kontrolünü kullanıcıdan iste;
   denenmediyse "cihazda denenmedi" yaz.
