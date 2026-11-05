# Danganronpa (Spike Chunsoft) — Trigger Happy Havoc Anniversary Edition (Switch)

Kod: `core/archives/wad.py` (AGAR arşivi), `core/formats/danganronpa/` (`.lin` ve `.pak` metin eklentisi).
Test: `tests/test_danganronpa.py`.

## Nerede ne var

Oyun Unity 2020.1 ile çalışır ama **metinler Unity dosyalarında değildir**. Unity tarafında (`sharedassets*.assets`, `level*`)
çevrilebilir metin yoktur; bu yüzden eski sürümler "0 satır" bulur.

| RomFS dosyası | İçerik |
|---|---|
| `Data/StreamingAssets/Initialpack/dr1_data.wad` (50 MB) | **Metinler burada.** 7.886 üye; `Dr1/data/{us,jp,ch}/script/` altında dil başına 2.016 dosya |
| `switch-dr1-{us,jp,all}.tp` | Ses (`voice`), görsel (`cg`), animasyon (`flash`) ve doku UnityFS paketleri; metin yok |
| `common-dr1-all.tp` | Galeri resimleri ve `.pb` (protobuf) ana veri tabloları (karakter adları) |

Dil klasörleri: `us` = İngilizce, `jp` = Japonca, `ch` = **geleneksel** Çince (`zh-hant`; 樂 鹽 麵 gibi).

## WAD (`AGAR`)

Küçük sonlu. Başlık: `AGAR` | sürüm u32 | alt sürüm u32 | ek başlık boyutu u32 (hep 0).
Dosya tablosu: sayı u32; her dosya için ad uzunluğu u32, UTF-8 ad, boyut u64, ofset u64 (veri bölümünün başına göre).
Klasör tablosu: sayı u32; her klasör için ad, çocuk sayısı u32, her çocuk için ad ve klasör mü baytı. Veri bölümü
klasör tablosunun hemen ardından başlar; üyeler boşluksuz ve dosya tablosu sırasıyla dizilidir (gerçek dosyada boşluk 0).

**Yazma:** başlık ve klasör tablosu aynı kalır, üyeler aynı sırayla yeniden dizilir, tablodaki boyut/ofset alanları yerinde
güncellenir. Değişiklik yoksa çıktı orijinalle bayt bayt aynıdır (gerçek `dr1_data.wad` ile doğrulandı). Tüm arşiv
bellekte kurulur; 1 GB'tan büyük arşivlerde açık hata verilir.

## `.lin` betikleri

Başlık: tür u32 (**1** metinsiz, **2** metinli) | başlık boyutu u32 (tür 1: 12, tür 2: 16) | [tür 2] metin bloğu ofseti u32 |
dosya boyutu u32. Ardından `0x70 <komut> …` biçiminde betik komutları (anlaşılması gerekmez; metne sıra numarasıyla
başvururlar, bu yüzden metin uzunluğu değişse de betik bölümü aynen kalır).

Metin bloğu: dizge sayısı u32 | (sayı + 1) × ofset u32 (bloğa göre, sonuncusu bloğun sonu) | dizgeler. Blok 4 bayta hizalanır
(824 dosyada 2 bayt sıfır dolgu var, 1.113 dosyada yok). Dizgeler **UTF-16LE**, `FF FE` BOM'u ile başlar, `00 00` ile biter.
Satır sonu metnin içinde gerçek `\n`'dir.

Metin kodları: `<CLT 4>…<CLT>` renk/biçim etiketleri (`<CLT 3>` vurgu gibi). Kontrol kodu sayılır (`⟦n⟧`). Gerçek oyunda
başka etiket yok. 1.937 betiğin 1.937'sinde (`us`) değişiklik yapılmadan geri yazım özdeş.

## `.pak`

`öğe sayısı u32 | sayı × ofset u32 (dosyanın başına göre) | öğeler`, boşluksuz. İki tür vardır:

- **Metin tabloları** (`00_System.pak` … `47_SurvivalTitle.pak`, 38 tane): her öğe bir dizge (öğe 0 çoğu zaman boş). Eşya adları,
  açıklamalar, harita adları, menüler, ipuçları, kredi metni burada. Anahtar öğe sırasıdır (`"1"`).
- **Betik paketleri** (`script_pak_e00.pak` …): her öğe bir `.lin` betiği. Anahtar `<öğe>.<dizge>` (`"2.1"`). Metinsiz
  betikler olduğu gibi kalır.

`bin/` klasöründeki pak'lar (Flash/arayüz kaynakları, `bin_*_l.pak`) bu eklentinin kapsamı **dışındadır**: içlerindeki
yazılar resim/Flash olarak gelir (bkz. TECH_DEBT).

## Dışa aktarma

Değişen `.lin`/`.pak` üyeleri `dr1_data.wad` içinde yeniden dizilir; mod tek dosya üretir:
`…/romfs/Data/StreamingAssets/Initialpack/dr1_data.wad` (≈50 MB). Yazım sonrası arşiv yeniden açılıp her üye doğrulanır.

## Bilinen sınırlar

- **Cihazda denenmedi.** Oyunun WAD'ı doğrulama toplamıyla (checksum) sınayıp sınamadığı, `.tp` paketlerindeki 16 baytlık
  özetlerin WAD'ı da kapsayıp kapsamadığı bilinmiyor.
- **Türkçe harfler:** oyunun yazı tipinde `ğ ş ı İ` gliflerinin olup olmadığı denetlenmedi; yoksa dışa aktarmadaki harf
  dönüştürme (ğ→g…) kullanılır. Font yaması bu oyun için yapılmadı.
- Danganronpa 2, V3 ve Another Episode aynı biçimi kullanıyor olabilir ama denenmedi; yalnızca Trigger Happy Havoc doğrulandı.
- Resim olarak gelen yazılar (başlık ekranı, menü düğmeleri) çevrilemez.
