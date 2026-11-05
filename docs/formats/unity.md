# Unity — Localization string tabloları

Kod: `nxceviri/core/formats/unity/unity.py` (UnityPy 1.25). Test verisi: `tests/unitybuild.py`.

## Nerede?

Unity Localization paketi (com.unity.localization) Addressables ile derlenince metinler
`Data/StreamingAssets/aa/<platform>/` altında şu bundle'larda durur (varsayılan adlar):

| Bundle | İçerik |
|---|---|
| `localization-string-tables-<dil>(<kod>)_assets_all.bundle` | O dildeki tüm `StringTable`'lar |
| `localization-asset-tables-<dil>(<kod>)_…` | `AssetTable`'lar (font, görsel, ses başvuruları — metin değil) |
| `localization-assets-shared_assets_all.bundle` | `SharedTableData` (anahtar adları), `Locale`'ler |
| `localization-locales_assets_all.bundle` | Dil tanımları |

## Bundle ve SerializedFile

UnityFS bundle (Silver Pines: Unity 6000.3.15f1, bundle biçimi 8, veri bayrakları 0x243 =
LZ4HC + birleşik blok bilgisi + blok hizalaması). İçinde tek bir SerializedFile (sürüm 22),
tip ağacı (typetree) **açık**. Tip ağacı olmasaydı nesneleri okumak için oyunun
IL2CPP meta verisinden tip üretmek gerekirdi.

## StringTable (MonoBehaviour)

```
m_GameObject, m_Enabled, m_Script, m_Name ("Dialogue_en")
m_LocaleId { m_Code ("en") }
m_SharedData  PPtr<$SharedTableData> (m_FileID başka bundle, m_PathID o bundle'daki nesne)
m_Metadata    { m_Items: managed reference dizisi }
m_TableData[] { m_Id SInt64, m_Localized string, m_Metadata }
references    (ManagedReferencesRegistry)
```

`SharedTableData`: `m_TableCollectionName` ("Dialogue"), `m_Entries[] { m_Id, m_Key }`.
Anahtar adı = `m_Entries` içinde aynı `m_Id`'nin `m_Key`'i.

`AssetTable` yapısı birebir aynıdır; `m_Localized` değerleri 32 haneli varlık GUID'leridir
(ör. Silver Pines `Fonts_en`). Bu yüzden tüm dolu değerleri GUID olan tablo metin sayılmaz.

## Metin içindeki kodlar

- TextMeshPro zengin metin: `<b>`, `</b>`, `<i>`, `<u>`, `<color=#FFCC00>`, `</color>`,
  `<sprite name="…">`, `<size=…>` …
- Smart String: `{0}`, `{input_0}`, `{ManualInput…}`; iç içe süslü parantezler bütün olarak
  tek kod sayılır.
- `\n` gerçek satır sonudur, metnin parçasıdır.

Silver Pines (İngilizce): 3.466 satır, 127'sinde kod; en sık `<b>` (77), `<color>` (58),
`{0}` (40), `{input_0}` (22), `<sprite>` (8).

## Geri yazma

`obj.save_typetree(tree)` → `bundle.save(packer="original")`. Değişmeyen tablolar yeniden
serileştirilmez; değişmeden yeniden serileştirilen bir tablo orijinalle bayt bayt aynıdır
(gerçek oyunda 24/24 tablo, İngilizce ve Japonca). Bundle'ın kabuğu (sıkıştırma blokları,
SerializedFile düzeni) bayt bayt aynı olmaz ama geçerlidir; çıktı yeniden okunup her
metin beklenenle karşılaştırılır.

## Açık sorular (M5)

- ~~Addressables kataloğundaki bundle özeti/CRC denetimi değiştirilmiş bundle'ı reddediyor mu?~~
  **Evet** (Kong: Survivor Instinct, 0.31.13). Aşağıdaki bölüme bakın.
- TextMeshPro fontlarında Türkçe glifler var mı?

## Addressables katalog CRC'si (0.31.13)

Kod: `nxceviri/core/export/addressables.py`; dışa aktarmada `layeredfs.export_mod` çağırır.

Addressables, `AssetBundleRequestOptions.m_Crc` sıfırdan farklıysa yerel paketi
`AssetBundle.LoadFromFileAsync(yol, crc)` ile açar ve CRC tutmazsa **yükleme başarısız olur**
(paket hiç açılmaz; çeviri oyunda görünmez). CRC, paketin derleme anındaki içeriğine bağlıdır;
metin bundle'ı yeniden yazıldığı için eski CRC eşleşmez. Katalogdaki CRC 0 ise denetim atlanır.

Kong'da 372 paket kaydından yalnızca dördünde CRC sıfırdan farklıydı; değiştirilen tek paket
olan `localization-string-tables-english(unitedstates)(en-us)_assets_all.bundle` (46.548 bayt,
CRC 1109416191) bunlardan biriydi. Diğer üçü (paylaşılan varlıklar 11.135.377, dil tanımları
5.280, Lehçe tablo 46.524 bayt) değiştirilmediği için dokunulmadı.

`catalog.json` → `m_ExtraDataString` base64'ünün içi `SerializationUtilities` biçimidir:
art arda `[tür baytı][veri]` kayıtları, paket seçenekleri `0x07` (JsonObject) +
assembly adı + sınıf adı + `int32` JSON uzunluğu + UTF-16LE JSON. `m_EntryDataString`
içindeki konumlar bu baytlara **bayt ofsetiyle** bağlıdır; bu yüzden kayıt uzunluğu
değiştirilemez. Düzeltme, `"m_Crc":<sayı>` değerini `0` yapıp kalan haneleri boşlukla
doldurur (JSON'da değerden sonra boşluk geçerlidir) ve katalogdaki diğer baytlara dokunmaz.

Eşleşme paket boyutundan yapılır (`m_BundleSize` = diskteki dosya boyutu); boyutu değişen
dosyaların **özgün** boyutları toplanır. Aynı boyutu paylaşan başka bir paket varsa onun CRC'si
de sıfırlanır; bu zararsızdır (CRC 0 yalnızca denetimi kapatır). Düzeltilmiş `catalog.json`
moda aynı romfs yoluyla eklenir; böylece LayeredFS birleşik romfs'te oyunun okuduğu katalog
değişir. `catalog.hash` yoksa ayrıca güncelleme denetimi yapılmaz (Kong'da yok).


## I2 Localization

Kod: `nxceviri/core/formats/unity/i2.py` (ham bayt okuyucu/yazıcı), `unity.py` (bağlama).
Test verisi: `tests/unitybuild.py` (`i2_source_raw`, `serialized_without_typetree`).

I2 Localization tüm dilleri tek bir `LanguageSource` MonoBehaviour'unda tutar. Blasphemous'ta üç
kaynak `Data/resources.assets` içindedir (eşyalar 621, diyaloglar 804, arayüz 613 terim; 10 dil).
Bu dosyada **tip ağacı yoktur** (`_enable_type_tree = False`), UnityPy alanları adla okuyamaz;
bu yüzden nesnenin ham baytı çözülür.

Yapı (Unity serileştirmesi: int32 uzunluklu UTF-8 dizgi, 4 bayt hizalama):

    MonoBehaviour ortak alanları (28 bayt) + m_Name
    başlık: Google_WebServiceURL, SpreadsheetKey, SpreadsheetName, LastUpdatedVersion (dizgi),
            GoogleUpdateFrequency (int), GoogleUpdateDelay (float)   ← sürüme göre değişir
    mTerms: int sayı + TermData[]
    (sürüme göre birkaç alan)
    mLanguages: int sayı + LanguageData{Name, Code, Flags (bayt)}[]
    ...

TermData dizilimi (I2 sürümüne göre):

| Düzen | Alanlar | Durum |
|---|---|---|
| A (2.6.x) | Term, TermType, Description, Languages[], Languages_Touch[], Flags[] | Blasphemous ile doğrulandı |
| B (2.8.x) | Term, TermType, Languages[], Flags[], Languages_Touch[] | Gerçek oyunda denenmedi |

Alan sırası IL2CPP meta verisindeki (`global-metadata.dat`) adlarla ve ham bayttaki desenle
çıkarıldı. Başlık tahmin edilmez: terim listesi m_Name'den sonraki ilk 1 KB içinde aranır ve
ancak şu koşulların hepsi tutarsa kabul edilir: tüm terimler çözülür, her terimde dil sayısı
aynıdır, hemen ardından (≤256 bayt) aynı sayıda geçerli dil kodlu `mLanguages` listesi gelir.
`Languages_Touch` ve `Flags` eski kalmış olabilir (Blasphemous'ta 10 dil varken 9 elemanlı); uzunlukları
serbesttir.

- Yalnızca `TermType = 0` (metin) terimleri çevrilir; diğerleri font/görsel/ses başvurusudur.
- Anahtar: `I2|<path_id>|<dil kodu>|<terim>`; aynı adlı ikinci terim `#2` alır.
- Aktarılan sütun: kullanıcının seçtiği kaynak dil, yoksa İngilizce (`en`), o da yoksa ilk sütun.
  Türkçe aynı sütuna yazılır (oyun o dilde çalıştırılınca Türkçe görünür). Boş hücreler aktarılmaz.
- Kontrol kodları Unity ile aynı: TMP etiketleri ve `{purgepoints}` gibi değişkenler.
- Geri yazma: yalnızca metni değişen terimler yeniden serileştirilir; başlık, değişmeyen terimler ve
  listeden sonrası özgün baytlarıyla kalır. Değişiklik yoksa dosya bayt bayt aynıdır. Gerçek
  `resources.assets` (36 MB, 10.942 nesne) yazıldığında yalnızca I2 nesnesi değişti.

Blasphemous'un `AssetBundles/Switch/dialog/*` paketlerindeki `dialogLines` alanları İspanyolca özgün
metinlerdir; oyunda gösterilen çeviriler I2 terimlerinden (`ST03_TIRSO/…`) gelir.


## Düz metin yerelleştirmesi: SRT altyazı ve TSV tablo (`TextAsset`)

Kod: `nxceviri/core/formats/unity/loctext.py` (ayrıştırıcı), `unity.py` (bağlama). Test verisi:
`tests/unitybuild.py` (`text_asset`), `tests/test_unity_loctext.py`.

Despelote gibi oyunlar metni Unity Localization ya da I2 yerine `Resources` klasöründeki düz metin
varlıklarında (`TextAsset`, sınıf 49: `m_Name`, `m_Script`) tutar; `Data/resources.assets` içindedir.

| Varlık | Biçim | Dil nasıl anlaşılır |
|---|---|---|
| `Nina1[en]`, `[es]shop convo_x` (2.822 adet) | SRT altyazı: `numara / 0:00:00,292 --> 0:00:04,000 / metin` | Addaki `[en]`, `[es]` etiketi |
| `despelote_loc_monsterFile` | TSV: `path, voice name, voice type, sub index, sub timestamp, [es] [en] [fr] [de] [br] [chs]` (6.042 satır) | Başlık sütunu |
| `despelote_loc_UI`, `despelote_loc_UI_original` | TSV: `ID, es, en, fr, de, br, chs` (menü) | Başlık sütunu |

Kurallar ve tuzaklar:
- SRT zaman damgasında milisaniye 1-3 hane olabilir (`00:00:06,7`); bazı dosyalar BOM (`\ufeff`) ile başlar;
  bir bloğun metni iki satır olabilir ve (nadiren) içinde boş satır bulunur. Blok metni "sonraki numara + zaman
  satırı"na ya da dosya sonuna kadar sürer; yalnızca bu aralık değiştirilir.
- TSV satırları `\r\n` ile ayrılır; hücre içindeki satır sonu gerçek satır sonu değil, düz `\n` yazısıdır
  (ters bölü + n). Bu yazı ve `{}` / `{0}` değişkenleri yer tutucu olur. `ID` başlığı dil kodu sayılmaz.
- Anahtarlar: `SRT|<path_id>|<dil>|<blok sırası>`, `TSV|<path_id>|<dil>|<satır sırası>`.
- Kaynak dil: seçilen dil, yoksa İngilizce. Altyazı varlıkları tek dillidir; yalnızca o dil seçiliyse alınır.
  Çeviri aynı yere yazılır (oyun İngilizce çalıştırılınca Türkçe görünür).
- Aynı diyalog hem SRT'de hem `monsterFile` TSV'sinde bulunur; oyun ikisini de değil, aşağıdaki `Locoliser`
  önbelleğini okur. Tutarlılık için üçü de yazılır. Çeviri belleği aynı cümleyi bir kez çevirir, iki kopya tutarlı kalır.
- **Dil yuvası:** Türkçe yalnızca kaynak dil sütununa/altyazısına (varsayılan İngilizce) yazılır; diğer diller özgün
  kalır (0.25.0'da tüm dillere yazmak denendi, yanlış varsayımdı ve dil seçeneklerini bozuyordu).
- Yazma: değişen `TextAsset.m_Script` UnityPy ile kaydedilir, dosya yeniden okunup tüm metinler doğrulanır.

### Oyunun okuduğu kopya: `Locoliser` (MonoBehaviour)

Kod: `nxceviri/core/formats/unity/locoliser.py`. Test verisi: `tests/unitybuild.py` (`locoliser_raw`).

Despelote metni çalışırken TSV'lerden değil, `resources.assets` içindeki `Locoliser` MonoBehaviour'undan okur
(path_id 3322, 1,8 MB, tip ağacı silinmiş). 0.24.0–0.25.0'da yalnızca TSV/SRT değiştirildiği için cihazda Türkçe
görünmedi. Bulmak için tüm RomFS (UnityFS paketlerinin nesneleri dahil) belirgin cümlelerle tarandı; metinler
yalnızca TSV TextAsset'lerinde ve bu nesnede geçiyor.

```
MonoBehaviour başlığı (m_Name "Locoliser")
int 0, int 1                         bilinmiyor (aynen)
PPtr<TextAsset> despelote_loc_monsterFile
string[1013]     anahtar             "01_kids/conversations/armararcodiscussion/nina1_01"
Entry[1013]      Sub[] { int sıra; float başlangıç; float bitiş; string[6] es,en,fr,de,br,chs }
PPtr<TextAsset> despelote_loc_UI
Row[164]         string[6]
100 bayt         font başvuruları vb. (aynen)
```

- Önbellekteki diyalog metni TSV'dekinden farklı olabilir (ekrana sığsın diye satırlara bölünmüş: 3.460/6.042 harfi
  harfine aynı). Eşleme bu yüzden anahtar (`path` + "/" + `voice name`, küçük harf, `\` → `/`) + `sub index` ile
  yapılır: 6.042/6.042.
- Menü satırları TSV satır sırasıyla eşlenir; yalnızca önbellekteki özgün metin TSV'dekiyle (düz ya da `\n` → satır
  sonu çevrilmiş hâliyle) aynıysa yazılır.
- Önbellekte satır sonu genellikle gerçek satır sonudur; birkaç menü hücresi düz `\n` yazısını tutar, onlarda öyle kalır.
- Önbellek projeye ayrı satır olarak aktarılmaz; TSV satırının çevirisi dışa aktarmada önbelleğe taşınır.

### Harfler: oyunun fontlarına `ı İ ş Ş ğ Ğ` ekleme

Despelote'nin fontları (Despelote-Regular 45 KB glyf, DespeloteFill3/Outline3 CFF) bu harfleri içermez; TextMeshPro
fontları **dinamik** (`m_AtlasPopulationMode = 1`) olduğundan eksik harf çalışma anında gömülü TTF/OTF'ten üretilir,
orada da yoksa yedek fonta (LiberationSans) düşülür ve harf başka bir yazı tipiyle çizilir. Çözüm: `Font` nesnelerindeki
TTF/OTF'e harfleri eklemek (`nxceviri/core/fontpatch/ttf.py`, ayrıntı `docs/formats/tmp-font.md`).

- Fontlar yalnızca adında "font" geçen paketlerde değildir: Despelote'de ana sahne paketinde (`Font` 991–994),
  `despelotini_scene_scenes_all.bundle` içinde ve `resources.assets` içindedir. Font taraması boyutu ≤ 256 MB tüm Unity
  dosyalarını açar; yamalanacak dosyalar projeye `font_files` ayarı olarak kaydedilir.
- Kullanım (Despelote için): **4. Kontrol Et → Fontları Tara → "Font yaması" seçeneğini işaretle → 5. Dışa Aktar.**
