# Game Freak mesaj biçimi (.dat + .tbl)

Kod: `nxceviri/core/formats/gfmsg/gfmsg.py`. Test verisi: `tests/test_gfmsg.py` (bağımsız yazıcı).

Gerçek oyunlarla doğrulandı: **Pokémon: Let's Go, Pikachu!** (618 İngilizce/Japonca mesaj dosyası)
ve **Pokémon Legends: Arceus** (317 İngilizce dosya). Hepsi okunup değişiklik yapılmadan geri
yazıldığında bayt bayt aynı.

## Yerleşim

`romfs/bin/message/<Dil>/{common,script}/<ad>.dat` ve aynı adla `.tbl`. Dil klasörleri:
`English`, `French`, `German`, `Italian`, `Spanish`, `Korean`, `JPN` (kana), `JPN_KANJI`,
`Simp_Chinese`, `Trad_Chinese`. `bin/message/grammar` ve `sort_string` içindeki `.dat`'lar mesaj
değildir (başlıkları uymaz, taranmaz).

## .dat

| Ofset | Alan |
|---|---|
| 0x00 | bölüm sayısı u16 (=1) |
| 0x02 | satır sayısı u16 |
| 0x04 | bölüm boyutu u32 |
| 0x08 | ilk anahtar u32 (=0) |
| 0x0C | bölüm ofseti u32 (=0x10) |
| 0x10 | bölüm: boyut u32, satır tablosu, satırlar |

Satır tablosu: `{ofset u32 (bölüm başına göre), uzunluk u16 (karakter, sondaki 0 dahil),
bayraklar u16}`. Bayraklar (0, 4, 64, 512…) anlamı bilinmeden korunur. Satırlar UTF-16LE, 4 bayta
hizalı, sırayla durur.

**Şifre:** satır `i` için anahtar `0x7C89 + 0x2983·i` (16 bit) ile başlar; her karakter anahtarla
XOR'lanır, sonra anahtar 3 bit sola döndürülür.

## Kontrol kodları

`0x0010`, ardından argüman sayısı `n`, ardından `n` adet u16 (ilki kod türü):

| Tür | Anlam |
|---|---|
| 0x01xx | Değişken: ad, Pokémon, hareket, eşya… (`0x0102` takma ad, `0x0107` hareket…) |
| 0x02xx | Sayı |
| 0x1000–0x1003, 0x13xx | Dilbilgisi (artikel, çoğul biçimi) |
| **0x1100** | Cinsiyete göre seçim: `my [1100(FF,0403)]boygirl` |
| **0x1101** | Sayıya göre seçim: `Point[1101(1,0100)]s` |
| 0xBE00 / 0xBE01 / 0xBE02 | Yeni paragraf / sayfa sonu / bekleme |
| 0xBDFF, 0xBD06, 0xBE05, 0x0114 | Metin kutusu kontrolleri |
| 0xFF00 | Renk |

0xE000–0xF8FF arası özel kullanım karakterleri oyuna özgü simgelerdir (kod sayılır).

### Seçimler (en önemli tuzak)

0x1100 ve 0x1101'in **son argümanı**, koddan hemen sonra gelen iki seçeneğin uzunluğudur: alt bayt
birinci, üst bayt ikinci seçenek. Seçenekler düz metindir ve art arda yazılır (`boy` + `girl`).
Metin değişince uzunluklar da değişmeli; aksi hâlde oyun yanlış harfleri gösterir.

Uygulama seçimi üç yer tutucuyla gösterir: `my ⟦1⟧boy⟦2⟧girl⟦3⟧` (başı, ayraç, son). Çevirmen iki
seçeneği de değiştirebilir veya boş bırakabilir (Türkçede çoğul eki sayıdan sonra gelmez:
`⟦1⟧ Başarı Puanı⟦2⟧⟦3⟧⟦4⟧`); uzunluklar yazarken yeniden hesaplanır (her biri en çok 255).
Ayraç ve son yer tutucuları dosyaya yazılmaz.

## .tbl (AHTB)

`"AHTB"`, girdi sayısı u32, sonra `{özet u64, uzunluk u16 (sondaki 0 dahil), ad}`. `i`. ad,
`i`. satırın adıdır; sonda fazladan bir `…_max` girdisi olabilir. Adlar çevirmene bağlam olarak
gösterilir; anahtar satır numarasıdır (geri yazma `.tbl`'e ihtiyaç duymaz).
