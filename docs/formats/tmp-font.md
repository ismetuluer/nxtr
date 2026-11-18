# TextMeshPro fontları ve font yaması (M8)

Kod: `nxceviri/core/fontpatch/` — `sdf.py` (mesafe alanı), `tmp.py` (glif üretimi, atlas yerleşimi),
`unity.py` (bundle yazımı). Test verisi: `tests/unitybuild.py` (`synth_atlas`, `tmp_font_bundle`).

Gerçek oyunla denendi: bir Unity oyununun `fonts_assets_all.bundle` paketiyle (9 TMP fontu, 1024×1024 Alpha8
atlaslar, Switch düzeninde). Ana metin fontu Noticia Text'in üç stiline ve PapaMan, Impact fontlarına
`ı İ ş Ş ğ Ğ` eklendi; yazılan bundle yeniden okunup metin çizilerek göz kontrolü yapıldı.

## TMP_FontAsset alanları (kullanılanlar)

| Alan | Anlam |
|---|---|
| `m_AtlasPopulationMode` | 0 statik, 1 dinamik (dinamik fontlar eksik harfi kaynak fonttan üretir; yamalanmaz) |
| `m_AtlasTextures[]` | atlas `Texture2D`'leri; dizi 4/8 yuvalıdır, `m_PathID = 0` olan boş yuvalar yok sayılır (yalnızca tek gerçek atlaslı fontlar yamalanır) |
| `m_AtlasWidth/Height`, `m_AtlasPadding` | atlas boyu, glif çevresindeki dolgu (örnek oyunda 9) |
| `m_GlyphTable[]` | `m_Index`, `m_Metrics` (genişlik, yükseklik, yatay taşma X/Y, ilerleme — piksel), `m_GlyphRect` (atlasta x, y, w, h; **sol alttan**), `m_Scale`, `m_AtlasIndex` |
| `m_CharacterTable[]` | `m_Unicode` → `m_GlyphIndex` |
| `m_UsedGlyphRects[]`, `m_FreeGlyphRects[]` | MaxRects yerleşim listeleri; kullanılan dikdörtgen glifin solunda/altında `dolgu+1`, toplamda `2·dolgu+1` piksel pay bırakır |

Atlas SDF'tir (render modu 4165 = SDFAA): kenar ≈127,5; örnek oyunda eğim piksel başına ≈12,75–13
(yayılım `dolgu + 1` piksel). UnityPy dokuyu Switch düzeninden (`m_PlatformBlob`) çözer ve
`set_image` ile aynı düzende geri yazar; veri bundle'a gömülür (`m_StreamData` boşaltılır).

## Harf tarifleri

| Harf | Kaynak | Yöntem |
|---|---|---|
| ı | i | En büyük bileşen (gövde) tutulur, nokta atılır; yeni SDF uzaklık dönüşümüyle |
| ı (büyük harf fontu) | i | "i"nin noktası yoksa "ı" aynı glife bağlanır (atlasa çizilmez) |
| İ | I + nokta: i → ż Ż ċ Ċ ė Ė → ö/Ö'nün bir noktası → `.` → çizilen daire | `Ö` varsa nokta onun noktalarının yüksekliğine, yoksa kaynaktaki gövde uzaklığıyla; I'nın ortasına. Çizilen daire I'nın çizgi kalınlığında |
| ş, Ş | s/S + çengel: ç/Ç'nin taban çizgisi altı (diğer büyüklükteki de olur) → `,` → çizilen çengel | Çengel gövdeden kopuksa yukarı kaydırılıp 1 piksel bindirilir; virgül ve çizilen çengel tabana 1 piksel bindirilir. Çengel büyütülmez |
| ğ, Ğ | g/G + kavis: ă/Ă → `˘` → ŭ Ŭ ŏ Ŏ → ü/Ü'nün noktalarına göre çizilen breve | Alınan kavis tabana ortalanır, kaynaktaki gövde uzaklığını korur. Çizilen breve Pillow ile 4× örneklenir; genişliği iki noktanın açıklığı ×0,8, kalınlığı nokta yüksekliği ×0,45; ü/Ü yoksa eklenmez |

Kaynak sırası üç yamacıda ortaktır (`fontpatch/sources.py`, karar 234); sonuçta harf başına kaynak etiketi döner.

"İşaret" sayılması için parça en az 6 piksel ve gövdenin %1'i kadar olmalı (el yazısı fontlardaki
lekeler nokta sanılmaz). Parçalar birleştirilirken SDF değerlerinin en büyüğü alınır; özgün glif
pikselleri değişmez.

## Atlas yeri

Önce MaxRects "en kısa kenar" yerleşimiyle boş dikdörtgenlere yerleştirilir. Yer yetmezse atlas
**yukarı doğru iki katına** çıkarılır: koordinatlar sol alttan ölçüldüğü için var olan glifler yerinde
kalır; `m_AtlasHeight`, `m_CreationSettings.atlasHeight` ve atlası kullanan malzemelerin
`_TextureHeight` değeri güncellenir. örnek oyunda atlasların çoğu doluydu ve büyütüldü (1024×2048).

## Atlanan durumlar (raporlanır)

- Dinamik fontlar, gerçekten birden çok atlaslı fontlar, atlası başka dosyada veya başka fontla ortak olanlar.
- Dile özgü bundle'lar (`fonts-japanese…`) ve dile özgü adlı fontlar.
- Taban harfi (I, i, s, S, g, G) olmayan fontlar (ör. yalnızca rakam içeren saat fontu); ğ/Ğ için kavis
  kaynağı da ü/Ü de olmayan fontlar; yapısı beklenmedik olanlar (ör. harflerin kutu içinde olduğu "etiket"
  fontunda ğ, Ğ). Nokta ve çengel kaynağı olmayan fontlarda bu işaretler artık çizilir ("çizildi").
- Tip ağacı silinmiş dosyalardaki fontlar (bir I2 oyununun `resources.assets` dosyası) — okunamaz.

## Vektör fontlar (TTF/OTF): `core/fontpatch/ttf.py`

Dinamik TMP fontları (ve eski `Font` kullanan arayüz) harfleri gömülü TTF/OTF'ten üretir. Bu dosyalara harf eklenir;
yeni glifler **sona** eklenir (glif numaraları kaymaz, atlaslar bozulmaz). Hem TrueType (`glyf`) hem CFF desteklenir; CID
anahtarlı CFF'ler ve Çince/Japonca/Korece (≥ 200 CJK karakteri olan) fontlar atlanır.

| Harf | Türetme |
|---|---|
| ı | `i`'nin noktası atılır (gövdenin üstünde, onunla çakışmayan konturlar). Nokta gövdeye kaynamışsa `I`, x-yüksekliğine ölçeklenir |
| İ | `I` + nokta: `i` → `ż Ż ċ Ċ ė Ė` → `ö`/`Ö`'nün soldaki noktası (konturlar kopyalanır, kaynaktaki gövde uzaklığıyla) → `period` (boşluk = nokta yüksekliğinin yarısı) → çizilen daire |
| ş, Ş | `s`/`S` + `ç`/`Ç`'nin taban çizgisi altındaki ayrı kontur(lar)ı (yatay konumu ç gövdesine göre, yüksekliği aynı) → `comma` (×0,85, tabanın altına; dolu fontlarda biraz bindirilir) → çizilen kuşak |
| ğ, Ğ | `g`/`G` + `ă`/`Ă`'nın kavisi → `˘` → `ŭ Ŭ ŏ Ŏ` → yarım elips kuşağı (genişlik gövdenin %55'i, kalınlık nokta genişliğinin yarısı) |

İşaret tek kontura kaynamışsa (gövdeden ayrılamıyorsa) o kaynak geçilir. Yeni glifler taban harfin kerning'ini devralır
(`kern` biçim 0, GPOS PairPos biçim 1/2, Extension; `fontpatch/kerning.py`); kerning'li font derlenemezse yama
kerning'siz yapılır ve not düşülür. İşaret `hhea.ascent` / `usWinAscent`'i aşarsa not düşülür.

Nokta/virgül fontun kendi çiziminden alındığından el yazısı ve halka (yalnızca anahatlı) fontlarda işaretler fontun
üslubuna uyar; font bunları içermiyorsa çokgen çizilir (yönü fontun dış konturlarıyla aynı). Tablolardan `hdmx`, `LTSH`,
`VDMX`, `DSIG` silinir (glif sayısıyla tutarsız kalırlar). Yazılan font yeniden okunup her harfin cmap'te ve boş olmayan
bir anahatla var olduğu doğrulanır.
