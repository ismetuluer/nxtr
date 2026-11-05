# Ys Origin (Switch, DotEmu sürümü)

Kod: `core/archives/nni.py` (arşiv), `core/formats/ysorigin/` (metin eklentisi). Test: `tests/test_ysorigin.py`.

## Nerede ne var

| RomFS yolu | İçerik |
|---|---|
| `ys_data/archives/data-<dil>.ni` + `.na` | Dil arşivi (en, fr, ge, it, sp, ja). İçinde `LOC/<DİL>/DATA/MAP/…/*.XSO` harita betikleri (diyaloglar, eşya/menü yazıları) ve hikâye resimleri (`EXTENSION/STORY/*.DDS`) |
| `ys_data/archives/data.ni` + `.na` | Ana arşiv (946 MB): modeller, dokular, dile bağlı olmayan betikler. Metin aranmaz |
| `ys_data/data/loc/strings/<dil>.xml` | Arayüz dizgeleri (`english.xml`, `japanese.xml`, `chinese-tw.xml` …), ~1.340 kayıt |
| `ys_data/data/extension/movies/yso_pro_<dil>.srt` | Açılış videosunun altyazısı (de, en, fr, it, sp, ko, zh-hans, zh-hant); video (`yso_pro.mp4`) yazısızdır, oyun altyazıyı kendi fontuyla çizer. `native_yso_pro.mp4` (Japonca sürüm) büyük olasılıkla yazısı gömülü videodur (açılıp doğrulanmadı) |
| `ys_data/data/extension/font/*.fnt` | BMFont (ikili, sürüm 3) yazı tipleri |

Arşiv içindeki dil klasörünün adı arşiv adından farklı olabilir (`data-ge.ni` → `LOC/DE` gibi);
dil, üye yolundaki `LOC/<DİL>/` klasöründen okunur (`pipeline.path_language`).

## NNI arşivi

Kaynak: Kyuuhachi'nin "Ys I/II/Origin/VI extractor" betiği (GitHub gist) ve Luigi Auriemma'nın `ysext` notları.

- `.ni` başlığı 16 bayt: `NNI\0`, girdi sayısı, ad tablosu boyutu, bayraklar (bit 0 = artımlı bağlama; desteklenmez).
- Girdi tablosu (16 bayt): ad özeti, boyut, `.na` ofseti, ad ofseti. Ad tablosu: sıfırla biten CP932 adlar, `\` ayraçlı.
- İki tablo ayrı ayrı karıştırılır: `k = 0x7C53F961`; her baytta önce `k *= 0x3D09` (32 bit), sonra
  `bayt -= (k >> 16) & 0xFF`. Yazarken toplanır.
- Ad özeti: `Σ (b − 32) << (i mod 5 · 5)` mod 0xFFF1. Ad değişmediği için yeniden hesaplanmaz.
- Adı `.Z` ile biten üyeler: CRC32 + açık boyut + zlib akışı.
- (0, 0) ofset/boyutlu kayıtlar boştur.

**Yazma:** orijinal `.na` kopyalanır, değişen üyeler sona eklenir, yalnızca dizindeki boyut/ofset alanları
değişir. Mod klasörüne `.ni` ve `.na` birlikte konur (~75 MB). Oyunun gevşek dosya okuyup okumadığı
bilinmediği için arşiv yolu seçildi.

## XSO betikleri

```
0x00  "XSR\0"  u16 0x10  u16 0xCCCC  u32 1  u32 0  u32 0  u32 2  u32 0
0x1C  u32 kod uzunluğu (u32 sayısı)
0x20  u32 dizge sayısı
0x24  kod … | dizge sayısı × u32 ofset (havuz başına göre, artan) | sıfırla biten UTF-8 havuz | 4 bayta sıfır dolgu
```

Kod dizgelere **sıra numarasıyla** başvurur (gerçek oyunda 2.207 dosyada doğrulandı: ofsetler her zaman
art arda, havuz dosya sonuna kadar). Bu yüzden çeviriler istenen uzunlukta olabilir; kod bölümüne
dokunulmaz. Tek istisna `S_9000/APLDESU_2.XSO`: dizgesi yok, başlık alanları tutarsız; atlanır.

Dizge tablosunda metinlerle betik kimlikleri karışıktır (`V_180` ses, `OPEN`, `@Flag_Inv`, `s_10\s_1000\`).
Ayırma: aynı betiğin Japonca kopyası (`data-ja.ni>LOC/JP/…`) bağlam olarak toplanır; İngilizcede farklı olan
dizgeler metindir. Gerçek veride 2.098 eşleşen dosyada boşluklu hiçbir dizge iki dilde aynı değildi; tek sözcüklü
`Yes`, `Cancel`, `Saul` metin olarak, `Battle`, `Back`, `Default` kimlik olarak doğru ayrıldı. Dizge sayısı
tutmayan 109 dosyada sezgisel kural kullanılır (boşluk, ASCII dışı harf veya cümle sonu noktalaması).

Kodlar: `\n` (ters bölü + n, satır sonu; tabloda gerçek satır sonu gösterilir), `<color:0xffRRGGBB>` … `<color:>`,
`<scale:1.3>`, `<ext:17>` (simge), `%s`, `%d`. Ham `0x0A` hiç geçmez.

## Arayüz XML'i

`<string id="KİMLİK">metin</string>`; boş olanlar `<string id="…"/>`. Dizge içindeki satır sonu **gerçek satır sonudur** (gerçek dosyada LF; `\n` dizisi hiç geçmez ve oyunda "¥n"
görünür). Dosya CRLF kullanıyorsa yazılırken CRLF korunur. Varlıklar (`&amp;`)
okunurken çözülür; değişmeyen satırların ham baytları aynen kalır, değişenlerde `& < >` kodlanır.

## Altyazı (`.srt`)

`core/formats/srt/` (genel SubRip eklentisi). Tabloda her blok bir satırdır; zaman damgaları, sıra numaraları, LF/CRLF ve
BOM korunur. Blok içi boş satır olamaz (bloğu bitirir). Dosyalar RomFS'te serbest durduğu için moda doğrudan konur
(`ys_data/data/extension/movies/yso_pro_en.srt`). Altyazı `linux*`/`ysfont` yazı tipleriyle çizilir (Libertine);
yazı tipi yaması bunları da kapsar. Korece ve Çince altyazıların kendi `yso_pro_*.fnt` yazı tipleri vardır.

## Yazı tipi yaması

`extension/font/*.fnt` (ikili BMFont v3) + `.png` atlas. Latin metin için beş yazı tipi kullanılır: `arial` (diyalog ve
menü açıklamaları, yalnızca alfa kanallı), `ysfont`, `linuxwhite`, `linuxshadow`, `linuxwhitesmall` (Linux Libertine:
dış çizgi, gölge, altın dolgu). Hepsinde `ç ö ü Ç Ö Ü` vardır, `ğ Ğ ş Ş ı İ` yoktur. `arialuni_*` (`ç` bile yok),
`jejugothic_*`, `msgothic` (altı harf de var) ve `yso_pro_*.fnt` Latin metin için kullanılmaz/yamalanmaz.

Dışa aktarma bu altı harfi **yazı tipinin kendi glifleriyle** türetip ekler (`fontpatch/bmfont.py`):

- `ı` = `i`nin gövdesi (nokta atılır), `İ` = `I` + `i`nin noktası (aynı boşlukla);
- `ş`/`Ş` = `s`/`S` + `ç`/`Ç`nin sedili; `ğ`/`Ğ` = `g`/`G` + breve (noktalardan yaylanır).

Parçalar "açık olan kazanır" (kanal başına en büyük değer) ile birleşir. Glif kutuları gölge payı içerdiğinden satır
ayırma opak çekirdek (dolgu) satırlarına göre yapılır. Yeni glifler atlasın boş bir yerine konur; yer yoksa atlasın
yüksekliği ikiye katlanır (`common` bloğu güncellenir). Çıktı mod klasörüne serbest dosya olarak konur. Harf
dönüştürme yapılmaz. Breve fontun kendi çizimi değildir (TECH_DEBT 76).

## Grafikler (`grafik_temizleme`)

Seçenek ekranı düğmeleri, onay kutuları, harita/patron adları, hikâye ve rehber sayfaları ve menü başlıkları resimdir
(DDS: BC3 = DXGI 77 veya BC1; mip zincirli; DX10 başlığı). Çevrilebilen 150 resim: `data-en.ni` içinde
`EXTENSION/STORY/EN/*.DDS` (140) ve `EXTENSION/MENU/*/*_EN.DDS` (8), serbest `menu/categories_atlas.dds` ve
`demo/demo_over.dds` (baş aşağı saklanır; PNG'de dik gösterilir). Klasör düzeni ve kullanım `fontpatch/ys_graphics.py`
başında ve klasördeki `OKUBENI.txt` dosyasında. Yazma: özgün başlık ve mip sayısı korunur, her mip seviyesi
(saydam renkler önceden çarpılarak küçültülür) yeniden kodlanır, dosya boyu doğrulanır. Ana arşivdeki resimler
(`MENU/CHRSELECT.DDS` "Character Select") kapsam dışı (TECH_DEBT 74).

## Gerçek oyunda ölçülenler (güncelleme v65536 ile)

Tarama ~1 sn; İngilizce kaynakla 527 dosyadan 10.805 satır (9.823 XSO + 964 XML + 18 altyazı) aktarılıyor, ~2 sn.
Değiştirilmemiş aktarma → geri yazma tüm 2.207 XSO ve XML'de bayt bayt aynı. Mod: `data-en.ni`, `data-en.na`,
`english.xml`. **Cihazda henüz denenmedi.**
