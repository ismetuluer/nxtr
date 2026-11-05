# NCA (Nintendo Content Archive)

Kod: `nxceviri/core/container/nca.py`, `crypto.py`

## Başlık (0xC00 bayt)

AES-128-XTS, anahtar `header_key` (32 bayt), sektör 0x200, tweak = sektör numarası
**big-endian** 16 bayt (standart XTS'ten farklı). NCA3'te 0–5. sektörler sırayla.

| Ofset | Boyut | Alan |
|---|---|---|
| 0x200 | 4 | Sihirli değer `NCA3` |
| 0x204 | 1 | Dağıtım türü |
| 0x205 | 1 | İçerik türü: 0 Program, 1 Meta, 2 Control, 3 Manual, 4 Data, 5 PublicData |
| 0x206 | 1 | Anahtar nesli (eski) |
| 0x207 | 1 | Anahtar alanı türü: 0 application, 1 ocean, 2 system |
| 0x208 | 8 | NCA boyutu (dosya boyutuyla karşılaştırılır → eksik dosya tespiti) |
| 0x210 | 8 | Program ID (güncelleme NCA'larında da *ana oyunun* ID'si) |
| 0x220 | 1 | Anahtar nesli (yeni); kullanılan = max(eski, yeni) |
| 0x230 | 16 | Rights ID (sıfır değilse başlık anahtarı gerekir) |
| 0x240 | 4×16 | Bölüm tablosu: başlangıç/bitiş (×0x200 "media unit") |
| 0x280 | 4×32 | Her bölüm başlığının SHA-256'sı (doğrulanır) |
| 0x300 | 4×16 | Şifreli anahtar alanı (AES-ECB, `key_area_key_<tür>_<nesil-1>`) |
| 0x400 | 4×0x200 | Bölüm (FS) başlıkları |

Anahtar adındaki sıra = nesil − 1 (nesil 0 ve 1 → `_00`).

## İçerik anahtarı

- Rights ID yoksa: anahtar alanının 2. girdisi (0x20–0x30) AES-CTR anahtarıdır.
- Rights ID varsa: biletteki (veya title.keys'teki) şifreli başlık anahtarı
  `titlekek_<nesil-1>` ile AES-ECB çözülür.

## Bölüm (FS) başlığı (0x200)

| Ofset | Alan |
|---|---|
| 0x02 | FS türü: 0 RomFS, 1 PFS0 |
| 0x03 | Hash türü: 2 HierarchicalSha256, 3 HierarchicalIntegrity (IVFC); 5/6 SHA3 karşılıkları |
| 0x04 | Şifreleme: 1 yok, 2 XTS, 3 CTR, 4 CTR_EX (BKTR), 5/6 "skip layer hash" türevleri |
| 0x08 | Hash verisi (0xF8) |
| 0x100 | Yama bilgisi: Indirect ve AesCtrEx bucket tree başlıkları (bkz. bktr.md) |
| 0x140 | generation u32, secure_value u32 |
| 0x148 | Seyrek (sparse) bilgi (0x30): tablo ofseti/boyutu, BKTR başlığı, fiziksel ofset u64, generation u16 |
| 0x178 | Sıkıştırma bilgisi (0x28): tablo ofseti/boyutu, BKTR başlığı |

CTR sayacı: üst 8 bayt = `secure_value` (BE) ‖ `generation` (BE); alt 8 bayt =
**NCA içindeki mutlak** ofset >> 4.

Verinin bölüm içindeki yeri: IVFC'de son katman (`levels[katman_sayısı-2]`, ofset 0x10'dan
itibaren 0x18'lik girdiler); HierarchicalSha256'da son bölge (0x28'den itibaren 0x10'luk
girdiler).

## Seyrek (sparse) bölümler

Kod: `nca.py` (`_sparse_section`). Güncellemeyle birlikte dağıtılan bazı ana oyunlarda
(ör. Castlevania: Belmont's Curse) Program NCA'nın RomFS bölümü **seyrektir**: güncellemenin
yeniden yazdığı veri base pakete hiç konmaz. Başlıktaki bölüm sonu dosyanın dışına düşebilir.

- Dosyadaki gerçek veri `fiziksel ofset`ten başlar; tablo `fiziksel ofset + tablo ofseti`ndedir.
- Tablo AES-CTR ile şifrelidir; sayacın üst 8 baytı `secure_value` (BE) ‖ `generation << 16` (BE).
- Girdiler Indirect ile aynıdır (0x14): kaynak 0 = fiziksel veri (ofset fiziksel başlangıca göre),
  kaynak 1 = sıfırlar. Ağacın bitişi bölüm boyutuna eşittir.
- Bu sanal (ham) bölümün üzerine normal AES-CTR, bölümün mutlak ofsetiyle uygulanır.
- Girdi sayısı 0 olan seyrek bölüm (ör. aynı oyunun ExeFS'i) tamamen güncellemededir.

Seyrek base tek başına okunamaz; uygulama güncellemenin de eklenmesini ister.

## Sıkıştırma katmanı

Kod: `compression.py`. Yeni SDK'larla (ör. Avatar Legends, SDK 21) RomFS verisi bloklar hâlinde
LZ4 ile sıkıştırılır. **Katman, hash katmanları atlanmış veri bölgesinin üzerindedir** (bölümün
değil): tablo ofseti + boyutu, IVFC veri bölgesinin boyutuna eşittir; tablo bölgenin sonundadır.

- Girdi (0x18): sanal ofset i64, fiziksel ofset i64, tür u8 (0 ham, 1 sıfır, 3 LZ4), seviye i8,
  2 bayt boşluk, fiziksel boyut u32. Ham bloklarda boyut alanı 0xFFFFFFFF'dir; uzunluk sanal
  aralığınkiyle aynıdır.
- Açılmış veri (sanal) RomFS'tir; ağacın bitişi onun boyutudur.
- Güncellemeli oyunda: önce yama (Indirect) base'in **sıkıştırılmış** veri bölgesiyle birleştirilir,
  sonra yamanın kendi sıkıştırma tablosuyla açılır.

## Tuzaklar

- XTS tweak'i big-endian; `cryptography`'ye tweak olarak doğrudan bu 16 bayt verilir.
- Bir oyunda RomFS her zaman 0. bölüm değildir (Silver Pines'ta 1. bölüm); FS türüne göre aranır.
- Yanlış `titlekek`/başlık anahtarı CTR'de hata vermez; çöp veri çıkar. RomFS başlık
  boyutu (0x50) kontrolüyle yakalanıp anlaşılır hataya çevrilir.
