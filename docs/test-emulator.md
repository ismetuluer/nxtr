# Modu Switch olmadan denemek

Üretilen mod klasörü (LayeredFS) bir Switch emülatöründe de çalışır. Dışa aktarırken **"Emülatör"**
yapısını seçin; klasörün içinde `<TitleID>/<Mod Adı>/romfs/...` oluşur.

## Gerekenler

- Kendi konsolunuzdan çıkardığınız `prod.keys` ve **firmware** (emülatör ikisini de ister).
- Oyunun kendisi (NSP/NSZ/XCI). Emülatörler çoğunlukla NSZ'yi doğrudan açmaz; NSP'ye dönüştürmeniz
  gerekebilir (uygulama bunu yalnızca okumak için bellekte yapar, dosya üretmez).
- Yeterli bir ekran kartı. 3D bir oyun (Silver Pines gibi) zayıf bir dizüstü bilgisayarda yavaş çalışabilir.

## Mod klasörünü nereye koymalı

| Emülatör ailesi | Konum |
|---|---|
| Ryujinx ve devam projeleri | Oyuna sağ tık → "Open Mods Directory"; `mods/contents/<TitleID>/` içine `<Mod Adı>` klasörünü koyun |
| Yuzu ve türevleri (Eden, Citron, Suyu, Sudachi…) | Oyuna sağ tık → "Open Mod Data Location"; `load/<TitleID>/` içine `<Mod Adı>` klasörünü koyun |

Emülatörlerin adları ve bakımı zamanla değişiyor (Yuzu ve Ryujinx'in resmî geliştirmesi durdu, devam
projeleri var); güncel olanı kendiniz araştırın. Mod klasörü yapısı hepsinde aynıdır. Emülatör
ayarlarında modun etkin olduğundan emin olun (bazılarında oyun özelliklerinden mod listesinden
işaretlenir).

## Kısa deneme sırası (oyunu baştan sona oynamanız gerekmez)

1. **Önce küçük bir mod üretin.** Çeviri tablosunda yalnızca ana menü etiketlerini (Yeni Oyun, Seçenekler,
   Ses…) çevirip dışa aktarın. Böylece mod yükleniyor mu, oyun açılıyor mu görürsünüz. Oyun çöküyorsa
   hata bir dosyadadır; modu küçültüp hangisi olduğunu bulursunuz.
2. **Oyun dilini kaynak dile ayarlayın.** Uygulama Türkçeyi seçtiğiniz kaynak dilin yerine yazar
   (ör. İngilizce). Emülatörün sistem dilini ve oyunun dilini o dile ayarlayın.
3. **Ana menüyü ve ayarlar ekranını açın.** Türkçe harfleri (ç ğ ı İ ö ş ü) kontrol edin. Kutucuk
   görürseniz font yaması kapalıdır veya o fontta eklenememiştir (Kontrol Et ekranındaki tabloya bakın).
4. **İlk diyaloğa ve envantere bakın:** metin kutusundan taşan satırlar, `{input_0}` gibi bozuk
   görünen yerler, düğme simgelerinin yerinde olup olmadığı.
5. Sorun bulursanız ilgili satırı çeviri tablosunda arayıp düzeltin ve modu yeniden üretin
   (hedef klasör boş olmalı; yeni bir ad verin veya eskisini silin).

## Hâlâ doğrulanamayan şey

Uygulama yazdığı dosyaları yeniden okuyup doğrular, ama oyunun değiştirilmiş dosyaları kabul edip
etmediğini yalnızca oyun söyleyebilir. Bu yüzden ilk deneme küçük tutulur.
