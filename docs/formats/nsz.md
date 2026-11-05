# NSZ / NCZ

Kod: `nxceviri/core/container/ncz.py`. Başvuru: nicoboss/nsz (MIT), `BlockDecompressorReader.py`.

NSZ, içindeki büyük NCA'ları `.ncz` olarak sıkıştırılmış bir NSP'dir (PFS0).

## NCZ

```
0x0000  orijinal NCA'nın ilk 0x4000 baytı (şifreli başlık), olduğu gibi
0x4000  "NCZSECTN" | bölüm sayısı u64
        bölüm × 0x40: ofset u64, boyut u64, şifre türü u64, dolgu u64, anahtar 16, sayaç 16
        ── ardından ya:
        "NCZBLOCK" | sürüm u8 | tür u8 | boş u8 | blok üssü u8 (14–32) | blok sayısı u32 |
        açılmış boyut u64 | sıkıştırılmış blok boyutları u32 × n | bloklar
        ── ya da:
        0x4000 sonrasının tek parça zstd akışı
```

- Sıkıştırılan veri, NCA'nın 0x4000 sonrasının **bölüm şifresi çözülmüş** hâlidir.
  Orijinal NCA'yı geri elde etmek için her bölüm, NCZ'de yazan anahtar ve sayaçla
  (üst 8 bayt + mutlak ofset >> 4) yeniden AES-CTR ile şifrelenir. Biz de bunu yapıyoruz;
  böylece NCA okuyucusu sıkıştırılmış ve sıkıştırılmamış dosyalarda aynıdır.
- BKTR (tür 4) bölümleri nsz tarafından düz CTR (tür 3) gibi işlenir; yeniden şifreleme
  orijinal baytları verdiği için sorun olmaz.
- Bir bloğun sıkıştırılmış boyutu açılmış boyutundan küçük değilse blok **ham** saklanır.
  Son bloğun açılmış boyutu `açılmış_boyut % blok_boyutu` (sıfır değilse).
- NCA dosya adı = NCA'nın SHA-256'sının ilk 16 baytı. NSZ→NSP dönüşümünde bununla doğrulanır.

## Gerçek örnek (Silver Pines)

Her iki dosya da blok kipinde, blok üssü 20 (1 MB). NCZ bölümleri: base'de `0x4000–0x1C000`
tür 1 (şifresiz logo bölümü), RomFS ve ExeFS tür 3. Dönüşümde tüm NCA'ların SHA-256'sı tuttu.

## Bölüm sayısı

NCZSECTN tablosundaki bölüm sayısının sabit bir üst sınırı yoktur; gerçek NCZ'lerde binlerce bölüm
görüldü (Avatar Legends güncellemesi: 7171, Blasphemous, MIO, MGS). Yalnızca tablonun dosyaya
sığdığı denetlenir.

## Akış kipi ve disk alanı

Akış kipindeki NCZ rastgele okunamadığı için önce önbelleğe tam NCA olarak açılır (oyun başına
GB'larca). Açmadan önce boş alan denetlenir (NCA boyutu + 1 GB); yer yoksa veya yazarken disk
dolarsa, yarım dosya silinir ve kullanıcıya "Önbelleği Temizle" önerilir.
