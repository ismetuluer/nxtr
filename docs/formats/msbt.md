# MSBT (Nintendo LMS "MsgStdBn")

Kod: `nxceviri/core/formats/msbt/msbt.py`. Test verisi: `tests/nxbuild.py::build_msbt`.

## Başlık (0x20)

| Ofset | Alan |
|---|---|
| 0x00 | `MsgStdBn` |
| 0x08 | BOM: `FF FE` little-endian, `FE FF` big-endian |
| 0x0C | Kodlama: 0 UTF-8, 1 UTF-16, 2 UTF-32 (desteklenmiyor) |
| 0x0D | Sürüm (genellikle 3) |
| 0x0E | Bölüm sayısı u16 |
| 0x12 | Dosya boyutu u32 (geri yazarken güncellenir) |

## Bölümler

`imza(4) | veri boyutu u32 | 8 bayt | veri | 0x10 hizasına kadar 0xAB`. Son bölümde dolgu
bazen yoktur; geri yazarken orijinal davranış korunur.

- **LBL1**: kova sayısı u32; kovalar `{etiket sayısı u32, ofset u32}`; etiketler
  `{uzunluk u8, ad, metin indeksi u32}`. Kova = ad hash'i (h = h·0x492 + bayt) mod kova sayısı.
  Etiket adı, girdinin projedeki kalıcı kimliğidir (yoksa `#indeks`).
- **TXT2**: metin sayısı u32, ofsetler u32[] (bölüm verisinin başına göre), metinler.
- **ATR1, TSY1, NLI1, ATO1**: dokunulmadan korunur.

## Metin içindeki kontrol kodları

Kod birimi UTF-16'da 2, UTF-8'de 1 bayttır; etiket alanları her durumda u16'dır.

- `0x0E` grup u16, tür u16, parametre boyutu u16, parametreler → açılış/tekil etiket
- `0x0F` grup u16, tür u16 → kapanış etiketi
- `0x00` → metin sonu. Sonra bir sonraki metne kadar kalan baytlar (varsa) korunur.

Grup 0 sistem etiketleridir: 0 okunuş (ruby), 1 yazı tipi, 2 boyut, 3 renk, 4 sayfa sonu.
Diğer gruplar oyuna özgüdür (oyuncu adı, sayı, ikon…).

Her etiket, tam ham baytlarıyla birlikte sırayla `⟦1⟧`, `⟦2⟧`… yer tutucusuna çevrilir.
Geri yazarken yer tutucular aynı baytlarla değiştirilir; sayı, tür veya sıra uymazsa
yazma reddedilir (`core/translate/placeholders.py`).

## Geri yazma

Yalnızca TXT2 yeniden kurulur: metinler indeks sırasıyla arka arkaya, ofset tablosu
yeniden hesaplanır. Diğer bölümlerin baytları aynen kalır. Tüm girdiler kendi orijinal
metinleriyle verildiğinde çıktı orijinalle bayt bayt aynıdır (zorunlu round-trip testi,
6 farklı varyant: LE/BE, UTF-8, etiketsiz, dolgusuz son bölüm, metin sonu artığı).

## Tuzaklar

- Ofsetleri sıralı olmayan (metinleri karışık sırada saklayan) dosyalar desteklenmez;
  açık hata verilir.
- Orijinal metinde `⟦`/`⟧` karakteri geçerse yer tutucu sayımı karışır (bkz. TECH_DEBT).
- Çeviride kullanılan karakterin oyunun fontunda bulunması M5'te denetlenecek.
