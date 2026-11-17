# Eklenti yazma — metin biçimi eklentisi

## Ne zaman okunur
`yeni-oyun.md` adım 4'e geldin: oyunun metin biçimini hiçbir hazır eklenti tanımıyor ve kendi eklentini yazacaksın.
Sözleşmenin kaynağı `nxceviri/core/formats/base.py`'dir; çelişki görürsen kod doğrudur.

## Eklenti neyden oluşur
Kullanıcı eklentisi bir klasördür:

| Dosya | İçerik |
|---|---|
| `eklenti.toml` | `ad`, `surum`, `yazar`, `oyunlar` (TitleID listesi), `aciklama` (isteğe bağlı kısa metin), `api = 1` |
| `plugin.py` | Biçim eklentisi: `detect` / `extract` / `inject` (aşağıda) |
| `tests/` | Elle üretilmiş örnekle bayt bayt round-trip testi |
| `NOT.md` | Biçim notu: yapı, kaynak, tuzaklar, cihazda denendi mi |

Konum: `%LOCALAPPDATA%\NXCeviri\eklentiler\<ad>\` (her çalıştırma biçiminde; güncelleme dokunmaz) ve kaynak kurulumda
depo içi `eklentiler/<ad>/` (git'e girmez). İskelet için `python -m nxceviri.arac eklenti-olustur <ad>`; yüklü eklentiler
ve yükleme hataları için `python -m nxceviri.arac eklentiler`. Uygulamada **Araçlar → Eklentiler** (başka bir yerden
getirilen eklenti için "Eklenti Ekle…"). Kullanıcı eklentisi yerleşikten önce denenir; hatalı eklenti uygulamayı
durdurmaz, nedeniyle listelenir. `api` uyumsuzsa atlanır. `oyunlar` doluysa eklenti yalnızca o oyunlarda tanıma,
çıkarma ve dışa aktarmada kullanılır; adı yerleşik bir biçimle aynıysa (ör. `msbt`) diğer oyunlarda yerleşik olan
çalışır. `oyunlar` boşsa eklenti her oyunda geçerlidir. Aynı eklenti hem kullanıcı klasöründe hem depo
klasöründe varsa kullanıcı klasöründeki kullanılır, diğeri "gölgelendi" uyarısıyla listelenir (hata değildir).

> **Güvenlik:** Eklenti kod çalıştırır, korumalı alan yoktur. Başkasından aldığın eklentinin `plugin.py`'sini çalıştırmadan
> önce oku; kullanıcıya da söyle.
>
> **Onay:** Uygulama, kullanıcı eklenti klasörüne konmuş yeni ya da içeriği değişmiş bir eklentiyi açılışta sorar
> ("Yeni eklenti bulundu": Yükle / Şimdi Değil); onaylanana kadar kodu çalıştırılmaz, Araçlar → Eklentiler'de
> "Onay bekliyor" görünür ve oradan "Onayla ve Yükle" ile de onaylanabilir. Onay, klasördeki dosyaların parmak izi
> (SHA-256, `__pycache__` hariç) olarak `%LOCALAPPDATA%\NXCeviri\eklenti_onaylari.json` dosyasında tutulur; dosya
> değişince yeniden sorulur. "Eklenti Ekle…" ile kurulan eklenti onaylı sayılır. Depo içi `eklentiler/` klasörü ve komut
> satırı araçları (`python -m nxceviri.arac …`) onay sormaz; eklenti geliştirirken her değişiklikte uygulama yeniden
> soracağı için önce araçlarla dene. Bu, bilmeden kopyalanan eklentinin sessizce çalışmasını önler; klasöre ve onay
> dosyasına yazabilen birine karşı koruma değildir.

`plugin.py`'nin dışa açtığı ad ve düzen için `eklenti-olustur`un ürettiği iskeleti temel al; komutun bayrakları için
`--help`.

## Sözleşme

```python
class Eklenti:
    name = "benimoyun"  # tarama raporundaki tür (`kind`); benzersiz
    label = "Benim Oyun metni"  # arayüzde görünen ad
    candidates_only = True  # True: yalnızca tarama raporunda metin adayı olan dosyalar denenir
    path_suffixes = (".msg",)  # boş değilse yalnızca bu uzantılı dosyalar açılır (büyük arşivleri boşuna okumamak için)

    def detect(self, path: str, head: bytes) -> bool: ...
    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]: ...
    def language(self, data: bytes) -> str | None: ...
    def extract(self, data: bytes, context=None) -> list[TextEntry]: ...
    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes: ...
```

Gerçek örnekler: en küçük `core/formats/msbt/msbt.py` (`MsbtPlugin`), kayıtlı listesi `core/formats/registry.py`.

### `extract`
- Her metin için `TextEntry(key, index, source, codes, max_length=None, context="")` döndür.
- **`key` dosya içinde benzersiz ve kalıcı olmalı** (oyun güncellenince de aynı satırı göstermeli). Sıra numarası yeterli
  olabilir (GFMSG: satır numarası; NNI/XSO: betik+dizge), ama adı olan biçimlerde adı kullan; yinelenen adlara
  `#i` ekle (MSBT böyle yapar). Anahtar çeviri belleğinde, projede ve `inject`'te kimliktir; sonradan değiştirme.
- **Kontrol kodları** metinden çıkarılıp `ControlCode(raw, label)` olur; metinde yerine
  `placeholders.token(n)` (`⟦1⟧`, `⟦2⟧`…, 1'den, metin içindeki sırayla) konur. `raw` dosyadaki ham bayt dizisidir ve
  `inject` bunu aynen geri yazar. `label` kullanıcıya gösterilen kısa Türkçe açıklamadır ("Renk", "Satır sonu").
  Satır sonu `\n` gerçek satır sonu olarak metinde kalabilir ya da kod olabilir; dosyada hangisiyse ona uy.
  Kod yoksa yer tutucu yok.
- `max_length`: biçimin kendisinin koyduğu sınır varsa (sabit genişlikli alan). Yalnızca görsel sığma sınırları buraya
  girmez (onlar Kontrol Et'te kullanıcı ayarıdır).
- Dil: dosyanın dili biliniyorsa `language(data)` ("en", "ja"…) döndür; aynı metnin birden çok dildeki kopyası varsa
  yalnızca kaynak dildeki aktarılır. Dil dosya yolundan anlaşılıyorsa `None` ver (yol, tarama raporundan çıkarılır).
- Başka dosyada duran ek bilgi (anahtar adları, etiket tablosu) `collect_context` ile toplanır ve `extract`'e
  `context` olarak verilir; `base.SOURCE_LANGUAGE` ve `SOURCE_PATH` anahtarları kullanıcının seçtiği kaynak dili ve
  açılan dosyanın yolunu taşır.
- Boş ya da bozuk dosyada çökme; `FormatError` (Türkçe, ne yapılacağını söyleyen mesajla) fırlat.

### `inject`
- Yalnızca metni değiştir; yapının geri kalanını **bayt düzeyinde koru** (dolgu baytları, bilinmeyen alanlar,
  bölüm sırası, hizalama, dosya sonu).
- `translations` içinde olmayan girdi olduğu gibi kalır. Hiç çeviri yoksa `data`'yı aynen döndür.
- Bilinmeyen `key` için çeviri verilmişse `FormatError`.
- Kontrol kodlarını doğrula: `placeholders.problems(entry.source, yeni)` boş değilse `FormatError` (sayı, tür, sıra).
  Çeviride `⟦n⟧` kodunu `codes[n-1].raw` ile geri yaz.
- Ret tek bir satırın çevirisinden geliyorsa anahtarını ver: `FormatError(f"'{key}' çevirisi yazılamadı: …", key=key)`.
  Dışa aktarma reddedilen satırı orijinal bırakıp dosyanın geri kalanını yazar; anahtar verilirse satırı doğrudan
  bulur, verilmezse ikili bölmeyle (daha yavaş) arar.
- Dosyanın kodlamasıyla yazılamayan karakter varsa `FormatError`; sessizce `?` yazma.
- Metin uzunluğu değişince **bağlı tüm alanları** güncelle: ofset tabloları, uzunluklar, bölüm/dosya boyutu, hizalama,
  kapsayıcı dizini. Hangileri olduğunu `ara` çıktısı ve çözümleme notlarından çıkar; tahmin etme.

### İsteğe bağlı kancalar
Dışa aktarma bunları `getattr` ile arar; yoksa atlanır. Türkçe harfle ilgili olanları (`unsupported_letters`,
`normalize_text`, `support_files`) `python -m nxceviri.arac font …` sonucuna göre ayarla (`yeni-oyun.md` adım 6):

| Kanca | Ne işe yarar |
|---|---|
| `unsupported_letters` | Fontta olmayan harflerin dönüştürüleceği harf listesi. `""` = dönüştürme yok: `arac font` sonucu (a) ya da (b) iken. (c) iken sonuç satırındaki harfleri yaz |
| `normalize_text(text)` | Yazmadan önce çeviriyi biçime uyarlar (ör. oyunun harf tablosu); yazılan metin geri okunanla aynı olmalı |
| `support_files()` | Moda eklenecek ek dosyalar (RomFS yolu → içerik), ör. Türkçe harfli yazı dokusu |
| `game_file_patches()` | Metin dışında değiştirilecek oyun dosyaları (yol → dönüştürücü), ör. resimdeki yazılar |
| `exefs_patches(code)` | Program koduna IPS yaması (yapı kimliği → yama) |
| `languages(data)` | Diller dosyanın içindeyse (I2 gibi) dosyadaki dil kodları (`["en", "ja"]`). Tarama sonunda çağrılır; kodlar Metinleri Tara'daki kaynak dil listesine eklenir, seçilen dil `SOURCE_LANGUAGE` ile `extract`'e gelir. Dili dosya yolundan anlaşılan biçimler bildirmez; bildirmeyen eklentide davranış değişmez |
| `movable_code(code)` | Bu kod çeviride yer değiştirebilir mi (`True` = serbest: tek başına simge, adıyla/numarasıyla bağlanan değişken). Konumsal kodlar (`%s`), aç/kapa çiftleri, satır/sayfa sonu için `False`. Yoksa hiçbir kod serbest değildir; `inject` sırası değişmiş serbest kodu yazabilmeli ya da reddetmeli |
| `paired_code(code)` | Bu kod bir aç/kapa çiftinin parçası mı: `(aile, "open")`, `(aile, "close")`, çiftin içinde kalması gereken ayraç için `(aile, "separator")`, değilse `None`. Aynı ailenin açılışı ve kapanışı kaynaktaki sırayla eşleşir (`</>` gibi genel kapanışta bütün açılışlara aynı aile adını ver); eşi olmayan kod katı kalır. Çift iç içeliği bozulmadan bütün olarak taşınırsa satır uyarıdır, hatalı değildir. Yalnızca biçim etiketleri gerçekten ayrı açılış/kapanış olarak saklıyorsa bildir; `inject` yeri değişmiş çifti yazabilmeli ya da reddetmeli. XML benzeri etiketler için hazır yardımcı: `markup.tag_pair` |
| `forbids_newline(key)` | Bu satırın çevirisinde gerçek satır sonu (`\n`, `\r`) yasak mı (`True`: ör. tırnaksız TSV/CSV hücresi, satır sonu satırı böler). Bildirilirse çeviride satır sonu olan satır Kontrol Et'te "Satır sonu" hatasıdır ve dışa aktarılmaz (orijinal kalır, bilgi dosyasında listelenir); satır sonu kodu (`⟦n⟧`) sayılmaz. Yalnızca yazıcı satır sonunu kesinlikle taşıyamıyorsa bildir; yoksa davranış değişmez |
| `derived_files(read, files, game_dir)` | Metinden bağımsız dosya/arşiv üyesi üretimi (`core/formats/derived.py`: yazı tipi, resim) |
| `archive_formats()` | Oyunun kendine özgü büyük arşivi (kapsayıcı dosya) için eklentinin taşıdığı arşiv biçimleri: `ArchiveFormat` nesnelerinden oluşan demet (`core/formats/base.py`; aşağıda "Arşiv biçimi") |
| `graphics` (nitelik) | `GraphicsSupport(folder_name, export)`: Dışa Aktar → Görseller; `export(okuyucu, dosyalar, klasör)` özgün resimleri `orijinal/`e yazar ve adlarını döndürür |

## Test (önce yaz)
1. **Üretici:** gerçek dosya yerine elle üretilmiş küçük örnek kuran bir işlev yaz (`tests/nxbuild.py::build_msbt`,
   `tests/unitybuild.py` örnek alınır). Birkaç metin, kontrol kodlu bir metin, boş metin, Türkçe karakterli metin
   (`ığİöüşç`), iki bayt sırası/kodlama varyantı varsa ikisi de.
2. **Round-trip (zorunlu):** `extract` → her girdiyi kendi `source`'uyla `inject` → çıktı `== orijinal` (bayt bayt).
3. **Değişiklik:** bir metni değiştir, `inject`, yeniden `extract`; yalnızca o satır değişmiş olmalı, diğerleri ve
   dosyanın geri kalanı aynı.
4. **Kod bozma:** `⟦n⟧`'yi silince/çoğaltınca `FormatError`.
5. **Bozuk dosya / boş / yanlış sihirli sayı:** `detect` yanlışsa `False`, `extract` açıklayıcı `FormatError`.
6. Örnekler yalnızca elle üretilmiş olur; gerçek oyundan kopya konmaz (`AGENTS.md` §1). Testleri çalıştır:
   `python -m pytest -q eklentiler/<ad>/tests` (yerleşik eklentiler için `tests/`).

Sonra gerçek dosyada `python -m nxceviri.arac dogrula <eklenti adı> <oyun dosyaları>` ve
`python -m nxceviri.arac font <oyun dosyaları>`; sonuca göre `unsupported_letters`'ı ayarla.

## Kullanılabilir kütüphaneler
Kaynak kurulumda `pyproject.toml`'daki bağımlılıklar kurulu: `cryptography`, `zstandard`, `UnityPy`, `httpx`,
`keyring`, `fonttools`, `lz4`, `Pillow` (Qt'yi eklentide kullanma). Hazır `NXTR.exe`'de saf Python eklentileri çalışır;
standart kütüphane (alt modülleriyle; `tkinter`, `test` ve `curses` hariç) ve yukarıdaki bağımlılıklar pakettedir,
başka kütüphaneler değildir; kaynak kodda yazdığın bir eklenti başka paket (ör. `numpy`)
gerektiriyorsa exe'de çalışmaz. Yeni bir kütüphane ekleme önerisi yapma; biçim küçükse kendin yaz.

### İzinli çekirdek modülleri
Ana koddan (`nxceviri`) **yalnızca** aşağıdakiler içe aktarılır. Liste kodda tek yerde durur
(`nxceviri/core/plugins/imports.py`, `ALLOWED_MODULES`); bir test bu bölümle aynı olduğunu denetler.

| Modül | Ne için |
|---|---|
| `nxceviri.core.plugins` | `FormatPluginBase` (iskeletin temel sınıfı) |
| `nxceviri.core.formats.base` | `TextEntry`, `ControlCode`, `FormatError`, `Context`, `SOURCE_LANGUAGE`, `SOURCE_PATH` |
| `nxceviri.core.formats.derived` | `Derived` (`derived_files` dönüşü), `GraphicsSupport` (`graphics` kancası) |
| `nxceviri.core.formats.msbt`, `nxceviri.core.formats.msbt.msbt` | Yerleşik MSBT okuyucusunu bir oyuna uyarlamak (`MsbtPlugin`'den türetme) |
| `nxceviri.core.translate.placeholders` | `token`, `problems`: `⟦n⟧` yer tutucuları |
| `nxceviri.core.translate.markup` | `tag_pair` gibi etiket yardımcıları |
| `nxceviri.core.archives.sarc`, `nxceviri.core.archives.yaz0`, `nxceviri.core.archives.zstd`, `nxceviri.core.archives.nni`, `nxceviri.core.archives.cpk`, `nxceviri.core.archives.wad`, `nxceviri.core.archives.pak`, `nxceviri.core.archives.psb`, `nxceviri.core.archives.psb_archive`, `nxceviri.core.archives.nested`, `nxceviri.core.archives.access` | Arşiv okuma/yazma (`psb_archive`: mdf ve `.psb.m` + `.bin`) |

Listede olmayan her çekirdek modülü (ör. `nxceviri.core.fontpatch.*`, `nxceviri.gui.*`, `nxceviri.core.export.*`)
**yasaktır**: sürümler arasında değişebilir ve başka bir kopyada eklenmiş bir modül bu kopyada hiç yoktur. Gereken
kodun bir eşi çekirdekte varsa bile eklentinin içine yaz (kendi modülün olarak; aşağıda). Denetim:
`python -m nxceviri.arac eklentiler` her eklentinin altında `İçe aktarma:` satırıyla bulguları gösterir;
`python -m nxceviri.arac dogrula` izinsiz ya da bu kopyada olmayan içe aktarmayı **KALDI** sayar; yükleyici böyle bir
modül yüzünden içe aktaramazsa hata metninde aynı açıklamayı verir. Denetim `tests/` klasörünü taramaz.

## Ana koda yazma yasağı ve çok dosyalı eklenti
- Yeni bir oyun için yazılan **bütün kod eklenti klasöründe** durur (`eklentiler/<ad>/` ya da
  `%LOCALAPPDATA%\NXCeviri\eklentiler\<ad>\`). `nxceviri/` altında hiçbir dosya oluşturulmaz ya da değiştirilmez;
  `git status --porcelain nxceviri/` boş kalmalı. Çekirdeğe taşıma yalnızca bakımcının işidir (`katki.md`).
- Eklenti bir pakettir: yükleyici `plugin.py`'yi klasörü paket sayarak yükler. Yardımcıları (arşiv okuyucu, font
  yamacı, doku kodlayıcı, resim çıkarıcı) `plugin.py`'nin yanına ayrı dosya olarak yaz ve göreli içe aktar:

  ```
  eklentiler/<ad>/
      plugin.py        from . import arsiv, font, resim
      arsiv.py         kapsayıcıyı açma/yeniden kurma
      font.py          eksik Türkçe harfleri fonta ekleme
      resim.py         doku çözme/kodlama, grafik_temizleme/turkce/ yerleştirme
      tests/           her modül için elle üretilmiş örnekle test
  ```
  Alt klasör de olur (`from .alt.kod import x`; alt klasörde `__init__.py` olsun). Mutlak `import arsiv` kullanma
  (çalışmaz). İskeletin testi `plugin.py`'yi aynı biçimde paket olarak yükler; yeni modül testten de görünür.
- "Eklenti oluşturamıyorum" diye çekirdeğe yazmak kabul edilmez: sözleşme her biçim için aynıdır, gereken her şey
  bu klasöre sığar.

### Arşiv biçimi (`archive_formats`)
Metin dosyaları oyunun tanınmayan bir arşivinin içindeyse (yerleşikler: SARC, Yaz0, ZSTD, pak, PSB arşivi, NNI, CPK,
WAD) arşiv okuyucusunu ve yazıcısını da eklentiye yaz; uygulama onu yerleşik arşivlerle aynı yerlerde kullanır:

```python
class BenimArsivim:
    name = "benimarsiv"            # eklentide benzersiz kısa ad
    label = "Benim arşivim"        # tarama raporunda görünen ad
    suffixes = (".arc",)           # üst düzey RomFS dosya uzantıları (küçük harf)

    def detect(self, path, head): ...           # head: dosyanın ilk 4 KB'ı
    def open(self, game, path): ...             # -> members() ve read(üye) sunan nesne
    def rebuild(self, changes, game): ...       # {arşiv: {üye: yeni bayt}} -> {RomFS yolu: bayt}

class Eklenti(FormatPluginBase):
    def archive_formats(self):
        return (BenimArsivim(),)
```

- `game` oyunun dosyalarıdır: `game.files` (RomFS yolları), `game.open(yol)` (`size`, `read(ofset, boyut)`,
  `read_all()`). Büyük arşivi `read_all()` ile belleğe alma; dizini ve istenen üyeyi `read` ile oku.
- `open(...).members()` `{üye yolu: boyut}` döndürür; tarama yalnızca kullanıcı eklentilerinin `path_suffixes`'ine uyan
  üyeleri okur ve `detect`'in tanıdıklarını `arşiv>üye` yoluyla listeler. `read(üye)` açılmış içeriği verir; üye yoksa
  `FormatError`. Okuyucu kısa ad gibi eş adları da çözebilir, ama `members()`'taki ad projeye yazılan addır.
- `rebuild` bir oyundaki bu biçimin bütün değişikliklerini birlikte alır; arşivde olmayan üye (ör. `derived_files`'ın
  `Derived.members`'ı) eklenecek yeni üyedir. Değişmeyen üyeleri bayt bayt koru. Değişikliği başka bir arşive
  (ör. güncellemenin arşivi) koyabilir. Uygulama dönen dosyaları oyunun üstüne bindirip `open` ile yeniden açar: her
  değişiklik dönen arşivlerden birinde aynen okunmalı, var olan arşivden üye düşmemeli; tutmazsa mod üretilmez.
- `oyunlar` sınırı arşiv biçimi için de geçerlidir; eklenti arşivi aynı uzantılı yerleşik arşivden önce denenir.
  `dogrula` da arşivin üyelerini gezer. Geçersiz biçim (eksik `rebuild` gibi) eklentiyi yükleme hatasıyla durdurur.
- Testte küçük bir arşivi elle kur: üyeleri listele, oku; bir üyeyi değiştirip `rebuild` et; değişen üye yeni
  içerikte, diğerleri bayt bayt aynı olmalı. Uygulamanın kendi testi: `tests/test_plugin_archives.py`.

## Font ve resim kancaları (aynı eklentide)
Metin, font ve resim işi **tek eklentide** toplanır:
- **Font:** `arac font` eksik harf gösterir ve uygulamanın yerleşik yaması o fontu kapsamıyorsa (sonuç c ya da
  "atlandı"), yama eklentinin kendi modülünde yazılır (`font.py`; `fontTools`/`Pillow` kullanılabilir). Yamalanan
  font `derived_files(read, files, game_dir)` dönüşünde `Derived(files=…)` (serbest dosya) ya da
  `Derived(members=…)` (arşiv üyesi) olarak; oyunun özel harf dokusu ise `support_files()` ile moda girer.
  `Derived.font_notes`'a "font adı: eklenen harfler" yaz. Yazdığın fontu yeniden okuyup harfin varlığını test et.
- **Resim:** `graphics = GraphicsSupport(folder_name, export)` uygulamanın Dışa Aktar → Görseller adımına bağlanır
  (`export` özgünleri `grafik_temizleme/orijinal/`e PNG yazar). Kullanıcının `grafik_temizleme/turkce/`e koyduğu
  resimler `derived_files` (ya da yerinde dönüştürme gerekiyorsa `game_file_patches`) ile aynı biçim ve boyutta
  geri yazılır; okunacak klasörü `derived.turkish_dir(klasör)` verir (eski `temiz/` adını da tanır). Ayrıntı
  `grafik.md`.

## Çekirdeğe taşıma (kabul edilen eklenti)
Katkı olarak kabul edilen eklenti `nxceviri/core/formats/<ad>/` altına taşınır ve `registry.py`'deki `BUILTIN_PLUGINS`
tuplesine eklenir; tarama tanıması için `core/formats/detection.py` (`FileKind` ve `KIND_LABELS`) ve gerekiyorsa
`scanner.py` kuralları da genişler. Bunu **yalnızca bakımcı** yapar (ayrıntı `katki.md`); yeni oyun üzerinde çalışan
ajan bu adımı uygulamaz, eklentiyi klasöründe teslim eder.

## Bitti ölçütü
Round-trip dahil testler yeşil; `dogrula` gerçek dosyalarda geçti ve içe aktarma bulgusu yok; `arac eklentiler`
eklentinin altında `İçe aktarma:` satırı göstermiyor; `git status --porcelain nxceviri/` boş; `arac font` sonucu
(a/b/c) belirlendi, eksik harfler önce font yamasıyla (yerleşik ya da eklentideki) kapatıldı, `unsupported_letters`
yalnızca yamanın kanıtla imkânsız olduğu harfleri içeriyor; `NOT.md` yazıldı; sınırlar (çevrilmeyen bölüm, cihazda
denenmedi) ve yapılamayan parça komut çıktısıyla açıkça yazıldı.

## Kullanıcıya rapor
Eklenti adı, desteklenen dosya/biçim, `dogrula` özeti (geçti/kaldı), `arac font` sonucu (a/b/c), kontrol kodu türleri ve neler korunduğu, bilinen
sınırlar, dosya konumu. Cihazda denenmediyse söyle.
