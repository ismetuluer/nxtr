# BKTR güncelleme yamaları

Kod: `nxceviri/core/container/patch.py`, `buckettree.py` (ortak ağaç okuyucu ve IndirectStorage).
Aynı ağaç yapısı seyrek bölümler ve sıkıştırma tabloları için de kullanılır (bkz. nca.md).

Güncelleme paketindeki Program NCA'nın RomFS bölümü şifreleme türü 4 (CTR_EX) taşır ve
tek başına bir dosya sistemi değildir.

## Yama bilgisi (FS başlığı 0x100)

İki adet `{ofset u64, boyut u64, "BKTR", sürüm u32, girdi sayısı i32, ayrılmış u32}`:
önce **Indirect**, sonra **AesCtrEx** tablosu. Ofsetler bölüm başına göredir. Tablolar
bölümün sonunda durur ve **standart** AES-CTR (FS başlığındaki generation) ile şifrelidir.

## Bucket tree

Düğüm boyutu 0x4000. Tablo = düğüm deposu + girdi deposu.

- Kök (L1) düğüm: `{index i32 = 0, count i32, bitiş ofseti i64}` + girdi kümelerinin
  başlangıç ofsetleri (i64). Küme sayısı 2046'yı aşarsa araya L2 düğümleri girer
  (LibHac formülü `patch.py` içinde).
- Girdi kümeleri düğüm deposundan hemen sonra **ardışıktır**: her biri
  `{index i32, count i32, küme bitişi i64}` + girdiler. Okurken düğümlere gerek kalmadan
  kümeleri sırayla okuyoruz; küme indeksleri ve toplam girdi sayısı doğrulanır.

## Girdiler

- Indirect (0x14): sanal ofset i64, fiziksel ofset i64, kaynak i32 (0 = base RomFS
  bölümünün çözülmüş hâli, 1 = yamanın kendi verisi).
- AesCtrEx (0x10): ofset i64, şifreleme u8 (0 şifreli, 1 şifresiz), 3 bayt ayrılmış,
  generation i32. Bu aralıktaki veri, sayacın üst 8 baytı
  `secure_value ‖ generation(girdi)` olacak şekilde CTR ile çözülür.

Sanal bölüm (yamalanmış RomFS bölümü) üzerinde **güncellemenin** FS başlığındaki IVFC
bilgisi geçerlidir; RomFS verisi son IVFC katmanındadır.

## Doğrulama

Silver Pines (8031 Indirect, 1 AesCtrEx girdisi): yamalanmış bölümden rastgele 200 veri
bloğunun SHA-256'sı, oyunun IVFC hash katmanındaki değerlerle birebir eşleşti. Testlerde
`tests/nxbuild.py::build_patch_nca` iki farklı generation ve bir şifresiz bölge içeren
yamalar üretir.
