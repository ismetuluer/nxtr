# RomFS ve PFS0

Kod: `nxceviri/core/container/romfs.py`, `pfs0.py`

## RomFS

Başlık 0x50: on adet u64 — başlık boyutu (0x50), dizin hash tablosu ofset/boyut, dizin meta
tablosu ofset/boyut, dosya hash tablosu ofset/boyut, dosya meta tablosu ofset/boyut, dosya
verisi ofseti.

- Dizin girdisi: üst, kardeş, ilk alt dizin, ilk dosya, hash zinciri, ad uzunluğu (u32×6) + ad
  (4 bayta hizalı). Kök dizin meta tablosunun 0. ofsetindedir.
- Dosya girdisi: üst (u32), kardeş (u32), veri ofseti (u64), boyut (u64), hash zinciri (u32),
  ad uzunluğu (u32) + ad.
- "Yok" = 0xFFFFFFFF. Hash tabloları yalnızca hızlı arama içindir; ağacı gezerken
  kullanılmaz. Döngü ve tablo dışına taşan bağlantılar hata sayılır.
- Adlar UTF-8; Türkçe karakterli adlar desteklenir.

## PFS0

`"PFS0" | dosya sayısı u32 | ad tablosu boyutu u32 | 0` + girdiler
`{ofset u64, boyut u64, ad ofseti u32, 0}` + ad tablosu + veri. NSP/NSZ, ExeFS ve meta
NCA'nın bölümü bu biçimdedir. Dosyanın sonunu aşan girdi = eksik dosya.

## Çıkarma güvenliği

RomFS adları `..`, `:`, `\`, denetim karakterleri, Windows'un yasak karakterleri veya sonda
nokta/boşluk içeriyorsa çıkarma reddedilir (klasör dışına yazmayı önler).
