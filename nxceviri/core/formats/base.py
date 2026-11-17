"""Format eklentisi sözleşmesi (CLAUDE.md §4.1).

Her metin formatı `FormatPlugin`'i uygular:

- `detect(path, head)`: bu eklenti dosyayı tanıyor mu?
- `extract(data, context)`: metin girdileri; kontrol kodları `⟦n⟧` yer tutucularına çevrilmiş.
- `inject(data, translations)`: yalnızca metni değiştirir, yapının geri kalanını korur.
  Çeviri verilmeyen girdiler olduğu gibi kalır. Zorunlu test: tüm girdiler kendi orijinal
  metinleriyle verildiğinde çıktı orijinalle bayt bayt aynıdır.

İsteğe bağlı yardımcılar:

- `collect_context(data, path)`: başka dosyalarda duran ek bilgiyi (ör. Unity'de anahtar adları,
  GFMSG'de yan dosyadaki etiket adları)
  toplar; aktarma sırasında tüm adaylardan toplanıp `extract`'e verilir.
- `language(data)`: dosyanın dili biliniyorsa dil kodu ("en", "ja"…). Aynı metnin birden çok
  dildeki kopyası varsa yalnızca kaynak dildeki dosya aktarılır.
- `languages(data) -> list[str]`: diller dosyanın içindeyse (I2 Localization) dosyadaki dil kodları. Tarama sonunda
  çağrılır ve kodlar Metinleri Tara'daki kaynak dil listesine eklenir; seçilen dil `SOURCE_LANGUAGE` ile `extract`'e
  gelir. Dili dosya yolundan anlaşılan biçimler bildirmez; bildirmeyen eklentide davranış değişmez.
- `movable_code(code) -> bool`: bu kontrol kodu "serbest" mi, yani çeviride yeri değişebilir mi? Yalnızca tek
  başına duran ve kendisi anlam taşıyan kodlar (simge, adıyla ya da numarasıyla bağlanan değişken: `{0}`,
  `{name}`) için True. Konumsal kodlar (`%s`, `%d`: oyun argümanları sırayla bağlar), açma/kapama çiftleri,
  satır/sayfa sonları ve anlamı bilinmeyen kodlar için False. Bildirmeyen eklentide hiçbir kod serbest değildir.
  Serbest kodların yeri değişmiş çeviri hatalı sayılmaz (uyarı; `placeholders.check`).
- `paired_code(code) -> (aile, rol) | None`: bu kod bir aç/kapa çiftinin parçası mı? Rol `"open"` (`<b>`),
  `"close"` (`</b>`) ya da `"separator"` (çiftin içinde kalması gereken ayraç, ör. Unreal çoğul seçenek ayracı).
  Aynı ailenin açılışı ile kapanışı, kaynaktaki sırayla (yığınla) eşleşir; eşi bulunmayan kod katı kalır. Yalnızca
  biçim etiketleri gerçekten ayrı açılış/kapanış olarak saklıyorsa ve `inject` yeri değişen çifti doğru yazabiliyorsa
  bildirilir. Bildirmeyen eklentide çift yoktur (katı). Bütün olarak, iç içeliği bozulmadan taşınan çift hatalı
  sayılmaz (uyarı; `placeholders.check`, ürün sahibinin kararı 2026-11-17).
- `forbids_newline(key) -> bool`: bu satırın çevirisinde gerçek satır sonu (`\n`, `\r`) yasak mı? Biçim satır sonunu
  taşıyamıyorsa (ör. tırnaksız TSV hücresi: satır sonu satırı böler) True. Bildiren eklentide çeviride satır sonu
  olan satır Kontrol Et'te hatadır ve dışa aktarılmaz (orijinal kalır, bildirilir); satır sonu kodu (`⟦n⟧`) sayılmaz.
  Bildirmeyen eklentide davranış değişmez. Yalnızca yazıcının satır sonunu kesinlikle taşıyamadığı biçimde bildirin.
- `archive_formats() -> tuple[ArchiveFormat, ...]`: eklenti kendi arşiv biçimini (oyunun büyük kapsayıcı dosyası)
  taşır. Tarama arşivin üyelerinden kullanıcı eklentilerinin tanıdıklarını `arşiv>üye` yoluyla listeler, okuma bu
  yolu `ArchiveFormat.open` ile çözer, dışa aktarma değişen üyeleri `ArchiveFormat.rebuild`'e verir ve dönen
  dosyaları moda yazar. Eklentinin `oyunlar` sınırı arşiv biçimi için de geçerlidir. Eklenti arşivi aynı uzantılı
  yerleşik arşivden önce denenir. Bildirmeyen eklentide davranış değişmez.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Protocol

from nxceviri.core.errors import NxError

#: `collect_context` çıktılarının birleşimi; anlamı eklentiye özgüdür.
Context = Mapping[object, object]

#: Aktarma sırasında `extract`'e verilen bağlamda kullanıcının seçtiği kaynak dil (veya None).
#: Birden çok dili tek dosyada tutan biçimler (I2 Localization) hangi sütunun okunacağını
#: buradan öğrenir. Bağlam hiç verilmezse (dışa aktarma doğrulaması) tüm diller okunur.
SOURCE_LANGUAGE = "kaynak_dil"
#: Aktarma bağlamında, açılan dosyanın oyun içindeki yolu.
SOURCE_PATH = "kaynak_yol"


class FormatError(NxError):
    """Metin dosyası çözülemedi veya geri yazılamadı.

    `key`: hata tek bir satırın çevirisinden kaynaklanıyorsa o satırın anahtarı (`inject` reddi). Dışa aktarma
    reddedilen satırı bununla doğrudan ayıklar; verilmezse ikili bölmeyle bulur (yalnızca daha yavaş)."""

    def __init__(self, message: str, hint: str = "", *, key: str | None = None) -> None:
        super().__init__(message, hint)
        self.key = key


@dataclass(frozen=True)
class ControlCode:
    raw: bytes  # dosyadaki ham bayt dizisi (etiket işaretiyle birlikte)
    label: str  # kullanıcıya gösterilecek kısa açıklama


@dataclass(frozen=True)
class TextEntry:
    key: str  # dosya içinde benzersiz, kalıcı kimlik
    index: int  # dosyadaki sıra
    source: str  # orijinal metin; kontrol kodları ⟦1⟧, ⟦2⟧… olarak
    codes: tuple[ControlCode, ...]
    max_length: int | None = None  # biçimin koyduğu uzunluk sınırı (karakter), yoksa None
    context: str = ""  # çevirmene yardımcı okunur ad (ör. "Dialogue/Jade_Intro_01")


class FormatPlugin(Protocol):
    name: str  # "msbt" gibi; tarama raporundaki `kind` ile aynı
    label: str
    #: True ise yalnızca tarama raporunda metin adayı olan dosyalar denenir.
    candidates_only: bool
    #: Boş değilse yalnızca adı bu uzantılarla biten dosyalar açılır (büyük arşivleri boşuna okumamak için).
    path_suffixes: tuple[str, ...]

    def detect(self, path: str, head: bytes) -> bool: ...

    def collect_context(self, data: bytes, path: str) -> dict[object, object]: ...

    def language(self, data: bytes) -> str | None: ...

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]: ...

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes: ...


class ByteSource(Protocol):
    """Rastgele erişimli, salt okunur oyun dosyası: büyük arşivin tamamını belleğe almadan okumak için."""

    @property
    def size(self) -> int: ...

    def read(self, offset: int, size: int) -> bytes: ...

    def read_all(self) -> bytes: ...


class GameFiles(Protocol):
    """Bir oyunun (ana oyun + güncelleme birleşik) RomFS dosyaları; arşiv biçimi kardeş dosyaları da buradan açar."""

    @property
    def files(self) -> Collection[str]: ...

    def open(self, path: str) -> ByteSource: ...


class MemberArchive(Protocol):
    """Açılmış bir eklenti arşivi."""

    def members(self) -> Mapping[str, int]:
        """Üye yolu → boyut (bayt; bilinmiyorsa saklanan boyut). Tarama bu yolları `arşiv>üye` olarak yazar."""
        ...

    def read(self, member: str) -> bytes:
        """Üyenin açılmış içeriği; üye yoksa `NxError` (ör. `FormatError`)."""
        ...


class ArchiveFormat(Protocol):
    """Eklentinin taşıdığı arşiv biçimi (`archive_formats()` kancası; modül belgesine bakın).

    `suffixes` üst düzey RomFS dosya adının küçük harfli uzantılarıdır (ör. `(".vfs",)`); yalnızca bunlarla biten
    dosyalarda `detect` çağrılır. `rebuild(changes, game)` bir oyundaki bu biçimin bütün değişikliklerini birlikte alır
    (`{arşiv yolu: {üye: yeni içerik}}`; üye arşivde yoksa eklenecek yeni üyedir) ve moda yazılacak dosyaları
    `{RomFS yolu: içerik}` olarak döndürür; değişikliği başka bir arşive (ör. güncellemenin arşivine) koyabilir.
    Dışa aktarma her değişikliğin dönen arşivlerden birinde aynen okunduğunu ve var olan arşivlerden üye düşmediğini
    denetler; tutmazsa mod üretilmez."""

    name: str
    label: str
    suffixes: tuple[str, ...]

    def detect(self, path: str, head: bytes) -> bool: ...

    def open(self, game: GameFiles, path: str) -> MemberArchive: ...

    def rebuild(self, changes: Mapping[str, Mapping[str, bytes]], game: GameFiles) -> Mapping[str, bytes]: ...
