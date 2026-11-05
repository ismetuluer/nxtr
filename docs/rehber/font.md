# Font — Türkçe harflerin oyunda görünmesi

## Ne zaman okunur
Kullanıcı oyunda `ğ ş ı İ` gibi harflerin kutucuk, boşluk ya da başka bir harf olarak göründüğünü söylüyor; ya da
yeni bir oyunda dışa aktarmadan önce fontları denetlemek istiyor. Hedef harfler: `ç ğ ı İ ö ş ü Ç Ğ Ö Ş Ü`.
Önce `AGENTS.md` (kontrol kodları, dürüst rapor). Sorun yalnızca "kutucuk" değilse `sorun-giderme.md`.

## Ana fikir
Oyun metni bir **fontla** çizer. Fontta bir harfin çizimi (glif) yoksa Türkçe çeviri doğru dosyaya yazılsa bile
oyunda görünmez. Üç çözüm vardır; bu sırayla düşün:

1. **Fontta zaten var** (Mina the Hollower, çoğu Latin font `ç ö ü` için): yapacak bir şey yok.
2. **Font yaması:** uygulama eksik harfleri **fontun kendi glifleriyle** türetip fonta ekler (ı = i'nin noktasız
   gövdesi, İ = I + nokta, ş = s + ç'nin çengeli, ğ = g + üstte yay). Yazı tipi değişmez, dış çizgi ve gölge korunur.
3. **Harf dönüştürme:** eksik harf yakın karşılığa çevrilir (ğ→g, ş→s, ı→i, İ→I). Yalnızca üretilen moda uygulanır,
   projedeki çeviriler değişmez. Font yaması hiç olmuyorsa son çare.

## Adımlar (uygulamadaki yol)
1. **4. Kontrol Et → "Font ve harfler" sekmesi → Fontları Tara.** Tablo: Font, Tür, Eksik Türkçe harfler, Yamayla
   eklenir, Dosya. Okuma:
   - "Eksik harf" = Latin fontların çoğunluğunda (yarıdan fazlasında) olmayan harf. Dile özgü fontlar (japanese,
     chinese, russian… adlı) sayılmaz.
   - "Yamayla eklenir" sütununda olmayan harf o fontta eklenemiyor demektir.
2. Eksik harf varsa **"Eksik Türkçe harfleri fontlara ekle (font yaması)"** kutusunu işaretle. Kapalıysa harf dönüştürme
   seçeneğini ("yok / yalnızca eksik harfler / tüm Türkçe harfler") belirle; yama açıkken dönüştürme yalnızca
   yamanın ekleyemediği harflere uygulanır.
3. **5. Dışa Aktar.** Yamalanan font dosyaları moda yazılır; `NXTR - Bilgi.txt` hangi fontlara hangi harflerin
   eklendiğini, hangilerinin eklenemediğini listeler. Dışa aktarma yazdığı fontu yeniden açıp harflerin gerçekten
   var olduğunu doğrular.
4. **Cihazda / emülatörde göz kontrolü kullanıcıdan istenir** (`docs/test-emulator.md`): ana menü ve ayarlar
   ekranında `ç ğ ı İ ö ş ü` yazan bir satır. Kutucuk varsa tabloya geri dön.

## Font türleri ve ne yapar

| Tür | Nerede | Ne yapılır | Not |
|---|---|---|---|
| Unity **TextMeshPro, statik** atlas | `TMP_FontAsset` (bundle veya `.assets`) | Glifler SDF olarak atlasa çizilir; atlas dolarsa iki katına büyür | `docs/formats/tmp-font.md` |
| Unity **TMP dinamik** / eski `Font` | Gömülü TTF/OTF `Font` nesneleri | TTF/OTF'e glif eklenir (sona eklenir, numaralar kaymaz) | Dinamik font harfi çalışma anında gömülü TTF'den üretir; orada yoksa yedek fonta düşüp farklı görünür |
| **TTF / OTF** (RomFS'te serbest) | `*.ttf`, `*.otf` | Aynı glif ekleme | CID anahtarlı CFF ve CJK (≥200 CJK karakteri) fontlar atlanır |
| **Switch sistem fontu** `.bfttf`/`.bfotf` (`.zs`) | Oyun içi gömülü | Önce zstd + XOR katmanı çözülür, yamalanır, yeniden paketlenir | `fontpatch/switchfont.py` |
| **BMFont** (`*.fnt` ikili v3 + `*.png`) | Ys Origin | Eksik glifler atlasa çizilir, `.fnt`'e eklenir; atlas dolarsa yüksekliği ikiye katlanır | `docs/formats/ys-origin.md` |
| **Oyunun kendi harf dokusu** | Devil May Cry `msg_tex.t32` | Eklenti `support_files` ile Türkçe harfli yeni doku üretir | Harf kodları da özel (`0x72` + hücre); `dmc1.md` |
| Font tip ağacı olmayan dosyada | Ör. Donkey Kong Country Returns HD | Okunamaz; `ğ ş ı İ` denetlenemez | Cihazda deneyip gerekirse harf dönüştürme |

Atlanan durumlar raporlanır: dinamik fontlar (atlas yok), gerçekten çok atlaslı fontlar, atlası başka dosyada ya da
başka fontla ortak olanlar, kaynak harfi olmayan fontlar (yalnızca rakam içeren saat fontu), tip ağacı silinmiş
dosyalar. Raporda "atlandı" gördüğünde o fontun gerçekten oyunda kullanılıp kullanılmadığını sor.

## Karar noktaları
- **Yamayı açmalı mıyım?** Eksik harf ve "Yamayla eklenir" sütunu doluysa evet. Yama çıktısı kullanıcının cihazında
  denenmeden "çalışıyor" deme.
- **Yama bir fonta uygulanamadı:** uyarı verilir, sessizce dönüştürmeye geçilmez. Kullanıcıya iki seçenek sun:
  harf dönüştürme ya da (yeni bir biçimse) font biçimini çözüp `fontpatch/` altına yeni bir yama yazmak.
- **Yeni font biçimi:** fontun glif tablosunu çözmeden başlama. Sırayla: (1) fontun hangi harfleri taşıdığını
  `fontTools` ile / biçimin kendi tablosundan oku; (2) eksik harfi hangi parçalardan türeteceğini seç (i, I, s, ç, g…);
  (3) yeni glifi biçimin kendi atlasına/tablosuna yaz; (4) yazılan dosyayı yeniden oku ve harfin gerçekten orada
  olduğunu doğrula; (5) elle üretilmiş örnek fontla test yaz (`tests/test_fontpatch_*.py` örnektir);
  (6) `unsupported_letters = ""` olan eklentiyle birlikte kullan (yama her zaman çalışır).
- **Harf dönüştürme mi font yaması mı?** Yama görünümü korur ama gerçek cihaz testi ister; dönüştürme her zaman
  çalışır ama metin yazım kuralını bozar. Kullanıcıya önerini kısa gerekçeyle söyle.

## Bilinen tuzaklar
- Atlas büyütülünce `m_AtlasHeight`, `m_CreationSettings.atlasHeight` ve atlası kullanan malzemelerin
  `_TextureHeight` değeri güncellenir; elle yazıyorsan unutma.
- Breve (ğ'nin üstü) fontun kendi çizimi değildir (TECH_DEBT 50/76); el yazısı fontlarda biraz farklı görünür.
- Despelote gibi bazı Unity oyunlarında fontlar yalnızca "font" adlı paketlerde değil, ana sahne paketinde ve
  `resources.assets` içindedir; tarama bunları bulur ve projeye `font_files` olarak kaydeder.
- Unity Addressables kataloğu değiştirilmiş bir bundle'ı CRC nedeniyle reddedebilir (`docs/formats/unity.md`
  "Addressables katalog CRC'si"); font bundle'ı yamalandıktan sonra oyun açılmıyorsa buna bak.

## Bitti ölçütü
1. Fontları Tara tablosunda tüm Latin fontlar için eksik harf yok ya da "Yamayla eklenir" sütunu eksiği kapatıyor.
2. Dışa aktarma hatasız bitti; `NXTR - Bilgi.txt` eklenen harfleri listeliyor.
3. Kullanıcı cihazda/emülatörde Türkçe harfleri gördü. (Görmediyse rapor "cihazda denenmedi" der.)

## Kullanıcıya rapor
Kaç fontta hangi harf eksikti, hangilerine eklendi/hangileri atlandı ve neden, dönüştürme açık mı, kullanıcının
cihazda bakacağı yer ("Seçenekler ekranı"). Tahmin değil, tablodaki sayıları yaz.
