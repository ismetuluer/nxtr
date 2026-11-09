# Font ve harfler

Oyunun fontunda `ç ğ ı İ ö ş ü Ç Ğ Ö Ş Ü` harfleri yoksa bu harfler oyunda kutucuk ya da boşluk olarak görünür.
**Kontrol Et → Font ve harfler → Fontları Tara** her fontu denetler.

## Tablo

- **Eksik Türkçe harfler:** fontta olmayanlar.
- **Ne yapılabilir:** o font için önerilen yol.
  - *Font yaması:* bazı fontlarda eksik harfler fontun kendi harflerinden üretilir (ş = s + çengel gibi). "Eksik Türkçe
    harfleri fontlara ekle" seçeneğiyle açılır.
  - *Dinamik font:* oyun eksik harfi yedek fonttan çizer; görünüm biraz farklı olabilir.
  - *Harf dönüştürme:* eksik harfler yakın karşılığıyla yazılır (ğ→g, ş→s, ı→i…).
  - *TTF/OTF dosyası:* fontu dışarıda düzenleyebilirsiniz (aşağıda).

## Fontu dışarıda düzenlemek

Oyunda ayrı dosya olarak duran TTF/OTF fontlar için:

1. Tabloda fontu seçin, **Fontu Dışa Aktar…** ile kaydedin.
2. FontForge gibi bir programda eksik harfleri ekleyin.
3. **Düzenlenmiş Fontu İçe Al…** ile seçin; tabloda "İçe alındı" görünür. Dışa aktarılan modda özgün fontun yerine
   konur. **Özgün Fonta Dön** bunu geri alır.

Paket içindeki fontlar (Unity paketleri gibi) bu yolla düzenlenemez.

## Harf dönüştürme

Dışa aktarırken üç seçenek vardır: dönüştürme yapma, yalnızca fontta eksik harfleri dönüştür, tüm Türkçe harfleri
dönüştür.
