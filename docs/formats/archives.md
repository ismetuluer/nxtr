# İç arşivler: SARC, Yaz0, ZSTD

Kod: `nxceviri/core/archives/` (okuma ve yazma)

## Yaz0

`"Yaz0" | açılmış boyut u32 BE | hizalama u32 | 4 bayt` + veri. Her grup bir bayrak baytıyla
başlar (yüksek bitten başlayarak): 1 = düz bayt; 0 = geri başvuru, 2 bayt
`[uuuu dddd][dddd dddd]`: mesafe = d+1; uzunluk = u+2, u = 0 ise üçüncü bayt + 0x12.
Mesafe < uzunluk olduğunda çakışan kopya bayt bayt yapılmalıdır.

## SARC

Başlık 0x14: `"SARC"`, başlık boyutu u16, BOM u16 (`FE FF` big-endian, `FF FE` little),
dosya boyutu u32, veri ofseti u32, sürüm u16. SFAT: `"SFAT"`, başlık boyutu u16, düğüm
sayısı u16, hash anahtarı u32, düğümler `{ad hash u32, öznitelik u32, veri başı u32,
veri sonu u32}`. Öznitelik üst baytı ≠ 0 ise alt 24 bit × 4 = SFNT ad tablosundaki ofset.
SFNT: `"SFNT"`, başlık boyutu u16, ayrılmış u16, 4 bayta hizalı adlar.

## ZSTD

İmza `28 B5 2F FD`. Birden çok çerçeve olabilir. Bazı oyunlar sözlük (dictionary) kullanır;
bu M1'de desteklenmez ve tarama raporunda uyarı olarak görünür.

## Tarama sınırları

İç dosyaları açarken giriş en fazla 64 MB, çıkış en fazla 256 MB, iç içe derinlik en fazla 4.
Sınırı aşan arşivler atlanır ve raporda uyarı olarak listelenir.

## Yazma (0.3.0)

- **SARC:** `sarc.read` → `replace` → `sarc.build`. Dosyalar orijinal sırayla yerleşir; her
  dosyanın hizalaması orijinal ofsetini bölen en büyük ikinin kuvvetidir (en çok 0x10000),
  böylece BFRES gibi büyük hizalama isteyen dosyalar bozulmaz. Ad tablosu, hash anahtarı ve
  sondaki artık baytlar aynen korunur. Değişiklik yoksa çıktı bayt bayt aynıdır.
- **Yaz0:** açgözlü LZ77 (3 baytlık hash zincirleri, pencere 0x1000, en uzun eşleşme 0x111).
  Başlıktaki hizalama alanı korunur.
- **ZSTD:** tek çerçeve, içerik boyutu başlıkta, seviye 19.
- **İç içe yollar:** `nested.replace_inner(dış_veri, parçalar, dönüştür)` iç dosyayı değiştirip
  üstteki her katmanı yeniden kapatır; içerik değişmeyen katmanların orijinal baytları kullanılır.
