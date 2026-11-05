# Unicorn Overlord (Vanillaware / ATLUS)

Kod: `core/archives/cpk.py` (CRI CPK + CRILAYLA), `core/formats/fmsb/` (metin eklentisi). Test: `tests/test_unicorn.py`.

## Nerede ne var

| RomFS dosyası | İçerik |
|---|---|
| `Unicorn.CPK` (2,9 GB) | Ana arşiv: 4.752 dosya; `MsgSheet/*.fms` burada **Japonca** |
| `UnicornPatch.CPK` (güncelleme) | Ana arşivin yamaları; yine Japonca MsgSheet |
| `Unicorn_US.CPK`, `_DE`, `_ES`, `_FR`, `_IT` (~5 MB) | Dil arşivleri: 32 `MsgSheet/*.fms`, 14 `Help/*.ftx` (yazılı yardım resimleri), `Debug/*.inc` |

Dil arşivi ana arşivdeki aynı adlı sayfanın üstüne biner. Türkçe mod yalnızca `Unicorn_US.CPK`'yı değiştirir
(Rusça topluluk yaması da aynısını yapıyor). Dil, arşiv adından (`_US` → en) okunur; ana arşivdeki sayfalar
içerikten Japonca tanınır (dizgelerin %10'undan fazlasında kana/kanji; gerçek veride Japonca sayfalarda en az
%24, İngilizce/Fransızcada en çok %3) ve İngilizce kaynak seçilince atlanır.

## CPK

Kaynaklar: CRI'nin açık belgelenmemiş biçimi; topluluk araçları (CriPakTools, YACpkTool) ile aynı yorum.

- Her bölüm: imza (`CPK `, `TOC `, `ETOC`, `ITOC`, `GTOC`) + u32 + u64 boyut + `@UTF` tablosu.
- `@UTF` tablosu büyük sonlu; çoğu zaman karıştırılmış: `m = 0x655F`, her bayt `^= m & 0xFF`, `m *= 0x4115`.
- Sütun bayrağı: üst 4 bit depolama (0x10 boş, 0x30 sabit, 0x50 satırda), alt 4 bit tür (0–7 tamsayı,
  8 float, 0xA dizge, 0xB veri).
- `CpkHeader`: `TocOffset`, `ContentOffset`, `ContentSize`, `EtocOffset`, `Align` (2048),
  `EnabledPackedSize` (açık boyutlar toplamı), `EnabledDataSize` (arşivdeki boyutlar toplamı).
- TOC satırı: `DirName`, `FileName`, `FileSize`, `ExtractSize`, `FileOffset` (TOC başına göre), `ID`.
- Yalnızca kimlikli (ITOC, adsız) arşivler desteklenmez.

**CRILAYLA:** `CRILAYLA` | açık boyut u32 | sıkıştırılmış uzunluk u32 | veri | 0x100 bayt sıkıştırılmamış baş.
Veri sondan başa okunur, bitler bayt içinde en anlamlıdan. Bit 0 → 8 bit sabit bayt; bit 1 → 13 bit (uzaklık − 3)
ve uzunluk: 3 + 2 bit, hepsi birse + 3 bit, + 5 bit, sonra 0xFF olmayana kadar 8'er bit. Çıktı da sondan başa yazılır.
Açma saf Python: 6 MB'lık diyalog dosyası ~2 sn.

**Yazma:** değişen dosyalar sıkıştırılmadan (`FileSize == ExtractSize`) konur — Rusça yamadaki tüm dosyalar da
böyle, oyun kabul ediyor. Dosyalar aynı sırayla, 2048 hizalı yeniden dizilir; TOC ve başlıktaki sayısal alanlar
yerinde güncellenir, tablolar aynı şekilde karıştırılır, ETOC olduğu gibi sona kopyalanır. Değişiklik yoksa
çıktı orijinalle bayt bayt aynı (gerçek `Unicorn_US.CPK` ile doğrulandı). 512 MB'tan büyük arşivler
(ana arşiv) yeniden yazılmaz; açık hata verilir.

## FMSB (MsgSheet)

```
0x00 "FMSB"  u32 veri boyutu (= dosya − 0x30)  u32 0x20  u32 0  u32 0  u32 dizge sayısı  u32 3  u32 0
0x20 dizge sayısı × 8 bayt sıfır (oyun yüklerken işaretçi yazar)
     dizgeler: sırayla, sıfırla biten UTF-8; boş dizge = boş yuva
     sıfır dolgu (16 bayt hizası)
     "FEOC" u32 0 u32 0x10 u32 0
```

Anahtar dizgenin sıra numarasıdır. `UcScriptMsgConv.fms` (diyaloglar) 490.000 yuvanın yalnızca ~26.700'ünde
metin taşır. `##(START)` gibi bölüm işaretleri aktarılmaz.

Kodlar: `#c(12)` … `#/c` renk, `#s(0.8)` … `#/s` boyut, `#i` … `#/i` eğik, `#b` kalın, `#w(40)` bekleme,
`#(56)` simge, `#FN(C5北の町)` / `#CN(…)` yer ve karakter adı değişkeni, `@c(18)` … `@/c`, `^1/` … `^` vurgu,
`%s` / `%d`, `<br>`, `<1>`, `<C>` (jenerik yerleşimi). Satır sonu (`0x0A`) metnin parçasıdır.

## Yazı tipi

Rusça yama Kiril harflerini Latin-1 karakterlerinin yerine (`Âîñõîä…`) yazıp font dokusunu değiştirmiş; yani
oyunun fontu yalnızca Latin-1 içeriyor. Bu yüzden eklenti `ğ Ğ ş Ş ı İ` harflerini `unsupported_letters` olarak
bildirir (dışa aktarmada ğ→g, ş→s, ı→i, İ→I); `ç ö ü` Latin-1'de olduğu için korunur. Fontlar (`Font_4K/`)
henüz çözülmedi; doğrudan glif denetimi yapılmadı.

## Gerçek oyunda ölçülenler (güncelleme v262144 ile)

Tarama 0,2 sn; İngilizce kaynakla 32 sayfadan 49.242 satır aktarılıyor (~27 sn, çoğu CRILAYLA açma). Dışa aktarma
~3 sn, çıktı tek dosya: `Unicorn_US.CPK`. **Cihazda henüz denenmedi.**
