# CNMT, NACP ve bilet (.tik)

Kod: `nxceviri/core/container/metadata.py`

## CNMT (Meta NCA → PFS0 → `*.cnmt`)

| Ofset | Alan |
|---|---|
| 0x00 | TitleID u64 |
| 0x08 | Sürüm u32 (güncellemelerde 65536 = 1. yama …) |
| 0x0C | Tür u8: 0x80 Application, 0x81 Patch, 0x82 AddOnContent, 0x83 Delta |
| 0x0E | Genişletilmiş başlık boyutu u16 |
| 0x10 | İçerik sayısı u16 |
| 0x20 | Genişletilmiş başlık (Patch/AddOn: ait olduğu ana oyun ID'si u64 ile başlar) |
| sonra | İçerik kayıtları × 0x38: SHA-256 (0x20), içerik ID (0x10), boyut (6 bayt), tür, id ofseti |

İçerik türü: 0 Meta, 1 Program, 2 Data, 3 Control, 4 HtmlDocument, 5 LegalInformation.

Güncelleme TitleID'si = ana oyun ID'si | 0x800. Uygulama güncellemenin ana oyuna ait olup
olmadığını CNMT'deki ana oyun ID'siyle denetler.

## NACP (Control NCA → RomFS → `control.nacp`)

16 dil × 0x300: ad (0x200) + yayıncı (0x100). Görünen sürüm 0x3060'ta (0x10). Ad için önce
İngilizce kayıtlara bakılır.

## Bilet (.tik)

İmza türü u32 (0x10004 = RSA-2048/SHA-256) → imza + dolgu atlanır (RSA-2048: 0x13C bayt).
Gövde: veren (0x40), başlık anahtarı bloğu (0x100; common bilette ilk 16 bayt şifreli
başlık anahtarı), sürüm, anahtar türü (0 common, 1 personalized) ... Rights ID gövdenin
0x160. baytında. Kişiselleştirilmiş biletler desteklenmez (title.keys istenir).
