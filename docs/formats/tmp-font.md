# TextMeshPro fontları ve font yaması (M8)

Kod: `nxceviri/core/fontpatch/` — `sdf.py` (mesafe alanı), `tmp.py` (glif üretimi, atlas yerleşimi),
`unity.py` (bundle yazımı). Test verisi: `tests/unitybuild.py` (`synth_atlas`, `tmp_font_bundle`).

Gerçek oyunla denendi: **Silver Pines** `fonts_assets_all.bundle` (9 TMP fontu, 1024×1024 Alpha8
atlaslar, Switch düzeninde). Ana metin fontu Noticia Text'in üç stiline ve PapaMan, Impact fontlarına
`ı İ ş Ş ğ Ğ` eklendi; yazılan bundle yeniden okunup metin çizilerek göz kontrolü yapıldı.

## TMP_FontAsset alanları (kullanılanlar)

| Alan | Anlam |
|---|---|
| `m_AtlasPopulationMode` | 0 statik, 1 dinamik (dinamik fontlar eksik harfi kaynak fonttan üretir; yamalanmaz) |
| `m_AtlasTextures[]` | atlas `Texture2D`'leri; dizi 4/8 yuvalıdır, `m_PathID = 0` olan boş yuvalar yok sayılır (yalnızca tek gerçek atlaslı fontlar yamalanır) |
| `m_AtlasWidth/Height`, `m_AtlasPadding` | atlas boyu, glif çevresindeki dolgu (Silver Pines: 9) |
| `m_GlyphTable[]` | `m_Index`, `m_Metrics` (genişlik, yükseklik, yatay taşma X/Y, ilerleme — piksel), `m_GlyphRect` (atlasta x, y, w, h; **sol alttan**), `m_Scale`, `m_AtlasIndex` |
| `m_CharacterTable[]` | `m_Unicode` → `m_GlyphIndex` |
| `m_UsedGlyphRects[]`, `m_FreeGlyphRects[]` | MaxRects yerleşim listeleri; kullanılan dikdörtgen glifin solunda/altında `dolgu+1`, toplamda `2·dolgu+1` piksel pay bırakır |

Atlas SDF'tir (render modu 4165 = SDFAA): kenar ≈127,5; Silver Pines'ta eğim piksel başına ≈12,75–13
(yayılım `dolgu + 1` piksel). UnityPy dokuyu Switch düzeninden (`m_PlatformBlob`) çözer ve
`set_image` ile aynı düzende geri yazar; veri bundle'a gömülür (`m_StreamData` boşaltılır).

## Harf tarifleri

| Harf | Kaynak | Yöntem |
|---|---|---|
| ı | i | En büyük bileşen (gövde) tutulur, nokta atılır; yeni SDF uzaklık dönüşümüyle |
| ı (büyük harf fontu) | i | "i"nin noktası yoksa "ı" aynı glife bağlanır (atlasa çizilmez) |
| İ | I + (i'nin noktası, yoksa Ö'nün noktalarından biri) | Nokta, Ö'nün noktalarının yüksekliğine, I'nın ortasına |
| ş, Ş | s/S + ç/Ç'nin taban çizgisi altı | Çengel gövdeden kopuksa yukarı kaydırılıp 1 piksel bindirilir. Aynı büyüklükte donör yoksa (`Ç` yok) `ç` kullanılır; çengel büyütülmez |
| ğ, Ğ | g/G + ü/Ü'nün noktaları | Kısa çizgi (breve) Pillow ile 4× örneklenip çizilir; genişliği iki noktanın açıklığı ×0,8, kalınlığı nokta yüksekliği ×0,45. Aynı büyüklükte donör yoksa (`Ü` yok) `ü` kullanılır; breve büyütülmez |

"İşaret" sayılması için parça en az 6 piksel ve gövdenin %1'i kadar olmalı (el yazısı fontlardaki
lekeler nokta sanılmaz). Parçalar birleştirilirken SDF değerlerinin en büyüğü alınır; özgün glif
pikselleri değişmez.

## Atlas yeri

Önce MaxRects "en kısa kenar" yerleşimiyle boş dikdörtgenlere yerleştirilir. Yer yetmezse atlas
**yukarı doğru iki katına** çıkarılır: koordinatlar sol alttan ölçüldüğü için var olan glifler yerinde
kalır; `m_AtlasHeight`, `m_CreationSettings.atlasHeight` ve atlası kullanan malzemelerin
`_TextureHeight` değeri güncellenir. Silver Pines'ta atlasların çoğu doluydu ve büyütüldü (1024×2048).

## Atlanan durumlar (raporlanır)

- Dinamik fontlar, gerçekten birden çok atlaslı fontlar, atlası başka dosyada veya başka fontla ortak olanlar.
- Dile özgü bundle'lar (`fonts-japanese…`) ve dile özgü adlı fontlar.
- Kaynak harfi olmayan fontlar (ör. yalnızca rakam içeren saat fontu) veya yapısı beklenmedik olanlar
  (ör. harflerin kutu içinde olduğu "etiket" fontu).
- Tip ağacı silinmiş dosyalardaki fontlar (Blasphemous `resources.assets`) — okunamaz.

## Vektör fontlar (TTF/OTF): `core/fontpatch/ttf.py`

Dinamik TMP fontları (ve eski `Font` kullanan arayüz) harfleri gömülü TTF/OTF'ten üretir. Bu dosyalara harf eklenir;
yeni glifler **sona** eklenir (glif numaraları kaymaz, atlaslar bozulmaz). Hem TrueType (`glyf`) hem CFF desteklenir; CID
anahtarlı CFF'ler ve Çince/Japonca/Korece (≥ 200 CJK karakteri olan) fontlar atlanır.

| Harf | Türetme |
|---|---|
| ı | `i`'nin noktası atılır (gövdenin üstünde, onunla çakışmayan konturlar). Nokta gövdeye kaynamışsa `I`, x-yüksekliğine ölçeklenir |
| İ | `I` + fontun `period` şekli, büyük harf yüksekliğinin üstüne (boşluk = nokta yüksekliğinin yarısı) |
| ş, Ş | `s`/`S` + fontun `comma` şekli (×0,85), tabanın altına; dolu fontlarda kuşak taban çizgisine biraz bindirilir |
| ğ, Ğ | `g`/`G` + yarım elips kuşağı; genişlik gövdenin %55'i, kalınlık nokta genişliğinin yarısı |

Nokta/virgül fontun kendi çiziminden alındığından el yazısı ve halka (yalnızca anahatlı) fontlarda işaretler fontun
üslubuna uyar; font bunları içermiyorsa çokgen çizilir (yönü fontun dış konturlarıyla aynı). Tablolardan `hdmx`, `LTSH`,
`VDMX`, `DSIG` silinir (glif sayısıyla tutarsız kalırlar). Yazılan font yeniden okunup her harfin cmap'te ve boş olmayan
bir anahatla var olduğu doğrulanır.
