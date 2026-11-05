"""Format eklentisi sözleşmesi (CLAUDE.md §4.1).

Her metin formatı `FormatPlugin`'i uygular:

- `detect(path, head)`: bu eklenti dosyayı tanıyor mu?
- `extract(data, context)`: metin girdileri; kontrol kodları `⟦n⟧` yer tutucularına çevrilmiş.
- `inject(data, translations)`: yalnızca metni değiştirir, yapının geri kalanını korur.
  Çeviri verilmeyen girdiler olduğu gibi kalır. Zorunlu test: tüm girdiler kendi orijinal
  metinleriyle verildiğinde çıktı orijinalle bayt bayt aynıdır.

İsteğe bağlı yardımcılar:

- `collect_context(data, path)`: başka dosyalarda duran ek bilgiyi (ör. Unity'de anahtar adları,
  Game Freak'te yan dosyadaki etiket adları)
  toplar; aktarma sırasında tüm adaylardan toplanıp `extract`'e verilir.
- `language(data)`: dosyanın dili biliniyorsa dil kodu ("en", "ja"…). Aynı metnin birden çok
  dildeki kopyası varsa yalnızca kaynak dildeki dosya aktarılır.
"""

from __future__ import annotations

from collections.abc import Mapping
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
    """Metin dosyası çözülemedi veya geri yazılamadı."""


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
