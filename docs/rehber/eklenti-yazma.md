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
ve yükleme hataları için `python -m nxceviri.arac eklentiler`. Uygulamada **Yardım → Eklentiler** (başka bir yerden
getirilen eklenti için "Eklenti Ekle…"). Kullanıcı eklentisi yerleşikten önce denenir; hatalı eklenti uygulamayı
durdurmaz, nedeniyle listelenir. `api` uyumsuzsa atlanır. `oyunlar` doluysa eklenti yalnızca o oyunlarda tanıma,
çıkarma ve dışa aktarmada kullanılır; adı yerleşik bir biçimle aynıysa (ör. `msbt`) diğer oyunlarda yerleşik olan
çalışır. `oyunlar` boşsa eklenti her oyunda geçerlidir. Aynı eklenti hem kullanıcı klasöründe hem depo
klasöründe varsa kullanıcı klasöründeki kullanılır, diğeri "gölgelendi" uyarısıyla listelenir (hata değildir).

> **Güvenlik:** Eklenti kod çalıştırır, korumalı alan yoktur. Başkasından aldığın eklentinin `plugin.py`'sini çalıştırmadan
> önce oku; kullanıcıya da söyle.

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
  olabilir (Game Freak: satır numarası; Ys Origin: betik+dizge), ama adı olan biçimlerde adı kullan; yinelenen adlara
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
- Dosyanın kodlamasıyla yazılamayan karakter varsa `FormatError`; sessizce `?` yazma.
- Metin uzunluğu değişince **bağlı tüm alanları** güncelle: ofset tabloları, uzunluklar, bölüm/dosya boyutu, hizalama,
  kapsayıcı dizini. Hangileri olduğunu `ara` çıktısı ve çözümleme notlarından çıkar; tahmin etme.

### İsteğe bağlı kancalar
Dışa aktarma bunları `getattr` ile arar; yoksa atlanır:

| Kanca | Ne işe yarar |
|---|---|
| `unsupported_letters` | Fontta olmayan harflerin dönüştürüleceği harf listesi. `""` = dönüştürme yok (font yamasıyla çözdüysen) |
| `normalize_text(text)` | Yazmadan önce çeviriyi biçime uyarlar (ör. oyunun harf tablosu); yazılan metin geri okunanla aynı olmalı |
| `support_files()` | Moda eklenecek ek dosyalar (RomFS yolu → içerik), ör. Türkçe harfli yazı dokusu |
| `game_file_patches()` | Metin dışında değiştirilecek oyun dosyaları (yol → dönüştürücü), ör. resimdeki yazılar |
| `exefs_patches(code)` | Program koduna IPS yaması (yapı kimliği → yama) |
| `derived_files(read, files, game_dir)` | Metinden bağımsız dosya/arşiv üyesi üretimi (`core/formats/derived.py`: yazı tipi, resim) |

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

Sonra gerçek dosyada `python -m nxceviri.arac dogrula <eklenti adı> <oyun dosyaları>`.

## Kullanılabilir kütüphaneler
Kaynak kurulumda `pyproject.toml`'daki bağımlılıklar kurulu: `cryptography`, `zstandard`, `UnityPy`, `httpx`,
`keyring`, `fonttools`, `lz4`, `Pillow` (Qt'yi eklentide kullanma). Hazır `NXTR.exe`'de saf Python eklentileri çalışır;
standart kütüphane (alt modülleriyle; `tkinter`, `test` ve `curses` hariç) ve yukarıdaki bağımlılıklar pakettedir,
başka kütüphaneler değildir; kaynak kodda yazdığın bir eklenti başka paket (ör. `numpy`)
gerektiriyorsa exe'de çalışmaz. Çekirdek yardımcıları (`nxceviri.core.archives.*` SARC/Yaz0/ZSTD/NNI/CPK/WAD/pak,
`nxceviri.core.translate.placeholders`) içe aktarılabilir. Yeni bir kütüphane ekleme önerisi yapma; biçim küçükse kendin
yaz.

## Çekirdeğe taşıma (kabul edilen eklenti)
Katkı olarak kabul edilen eklenti `nxceviri/core/formats/<ad>/` altına taşınır ve `registry.py`'deki `BUILTIN_PLUGINS`
tuplesine eklenir; tarama tanıması için `core/formats/detection.py` (`FileKind` ve `KIND_LABELS`) ve gerekiyorsa
`scanner.py` kuralları da genişler. Bunu bakımcı yapar; ayrıntı `katki.md`.

## Bitti ölçütü
Round-trip dahil testler yeşil; `dogrula` gerçek dosyalarda geçti; `NOT.md` yazıldı; sınırlar (okuma-yalnızca, çevrilmeyen
bölüm, cihazda denenmedi) açıkça yazıldı.

## Kullanıcıya rapor
Eklenti adı, desteklenen dosya/biçim, `dogrula` özeti (geçti/kaldı), kontrol kodu türleri ve neler korunduğu, bilinen
sınırlar, dosya konumu. Cihazda denenmediyse söyle.
