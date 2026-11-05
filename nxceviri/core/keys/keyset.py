"""`prod.keys` ve `title.keys` dosyalarını okuma ve doğrulama.

Güvenlik kuralı: anahtar değerleri hiçbir koşulda loglanmaz, hata mesajına,
`repr`/`str` çıktısına veya proje dosyasına yazılmaz. Hata mesajlarında yalnızca
anahtarın *adı* ve satır numarası geçer.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from nxceviri.core.errors import KeyFileError, MissingKeyError

log = logging.getLogger(__name__)

#: Bir anahtar dosyası bundan büyükse anahtar dosyası değildir (gerçek dosyalar ~20 KB).
MAX_KEY_FILE_SIZE = 1024 * 1024

_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*[=,]\s*([0-9A-Fa-f]+)\s*$")
_GEN_KEY_RE = re.compile(r"^(key_area_key_application|key_area_key_ocean|key_area_key_system|titlekek)_([0-9a-f]{2})$")

#: Anahtar adına göre beklenen uzunluk (bayt). Listede olmayanların uzunluğu denetlenmez.
_EXPECTED_LENGTHS = {"header_key": 32}

KEY_AREA_KINDS = ("key_area_key_application", "key_area_key_ocean", "key_area_key_system")

_HELP_DUMP = (
    "prod.keys dosyasını kendi konsolunuzdan Lockpick_RCM ile yeniden çıkarın ve dosyanın tamamını değiştirmeden seçin."
)


def master_key_index(key_generation: int) -> int:
    """NCA/bilet anahtar neslini anahtar adlarındaki sıra numarasına çevirir (0 ve 1 → 00)."""
    return key_generation - 1 if key_generation > 0 else 0


@dataclass(frozen=True)
class KeySummary:
    """Arayüzde gösterilecek, değer içermeyen özet."""

    key_count: int
    key_area_generations: tuple[int, ...]
    titlekek_generations: tuple[int, ...]

    @property
    def newest_generation(self) -> int:
        gens = set(self.key_area_generations) & set(self.titlekek_generations)
        return max(gens) if gens else -1


class KeySet:
    """Yüklenmiş anahtarlar. Değerlere yalnızca kripto kodu erişir."""

    __slots__ = ("_keys", "source_path")

    def __init__(self, keys: Mapping[str, bytes], source_path: Path | None = None) -> None:
        self._keys = dict(keys)
        self.source_path = source_path

    def __repr__(self) -> str:
        return f"<KeySet: {len(self._keys)} anahtar>"

    __str__ = __repr__

    def __len__(self) -> int:
        return len(self._keys)

    def names(self) -> list[str]:
        return sorted(self._keys)

    def has(self, name: str) -> bool:
        return name in self._keys

    def require(self, name: str) -> bytes:
        try:
            return self._keys[name]
        except KeyError:
            raise MissingKeyError(
                f"Gerekli anahtar bulunamadı: {name}",
                "Bu içerik, anahtar dosyanızda olmayan daha yeni bir anahtar nesli "
                "gerektiriyor. Konsolunuzu güncelledikten sonra " + _HELP_DUMP,
            ) from None

    @property
    def header_key(self) -> bytes:
        return self.require("header_key")

    def key_area_key(self, kind: int, key_generation: int) -> bytes:
        if not 0 <= kind < len(KEY_AREA_KINDS):
            raise MissingKeyError(f"Bilinmeyen anahtar alanı türü: {kind}")
        return self.require(f"{KEY_AREA_KINDS[kind]}_{master_key_index(key_generation):02x}")

    def titlekek(self, key_generation: int) -> bytes:
        return self.require(f"titlekek_{master_key_index(key_generation):02x}")

    def summary(self) -> KeySummary:
        area: set[int] = set()
        kek: set[int] = set()
        for name in self._keys:
            m = _GEN_KEY_RE.match(name)
            if not m:
                continue
            gen = int(m.group(2), 16)
            if m.group(1) == "titlekek":
                kek.add(gen)
            elif m.group(1) == "key_area_key_application":
                area.add(gen)
        return KeySummary(len(self._keys), tuple(sorted(area)), tuple(sorted(kek)))


def _read_key_text(path: Path, what: str) -> str:
    if not path.exists():
        raise KeyFileError(f"{what} bulunamadı: {path}", "Dosyanın yerini kontrol edip yeniden seçin.")
    if not path.is_file():
        raise KeyFileError(f"Seçilen yol bir dosya değil: {path}", f"{what} dosyasını seçin.")
    try:
        size = path.stat().st_size
        if size == 0:
            raise KeyFileError(f"{what} boş: {path}", _HELP_DUMP)
        if size > MAX_KEY_FILE_SIZE:
            raise KeyFileError(
                f"Seçilen dosya bir anahtar dosyası olamayacak kadar büyük: {path}",
                f"Doğru dosyayı ({what}) seçtiğinizden emin olun.",
            )
        raw = path.read_bytes()
    except OSError as exc:
        raise KeyFileError(
            f"{what} okunamadı: {path}",
            f"Dosya başka bir program tarafından kilitlenmiş veya erişim izni yok olabilir. ({exc.strerror})",
        ) from None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise KeyFileError(f"{what} metin dosyası değil veya bozuk: {path}", _HELP_DUMP) from None


def _parse_lines(text: str, path: Path, what: str) -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith((";", "#", "//")):
            continue
        m = _LINE_RE.match(stripped)
        if not m or len(m.group(2)) % 2:
            raise KeyFileError(
                f"{what} bozuk: {line_no}. satır 'ad = onaltılık değer' biçiminde değil ({path.name}).",
                _HELP_DUMP,
            )
        values[m.group(1).lower()] = bytes.fromhex(m.group(2))
    return values


def load_keys(path: Path) -> KeySet:
    """`prod.keys` dosyasını okur ve M1 için gerekli anahtarların varlığını doğrular."""
    what = "Anahtar dosyası (prod.keys)"
    keys = _parse_lines(_read_key_text(path, what), path, what)
    if not keys:
        raise KeyFileError(f"{what} içinde hiç anahtar yok: {path}", _HELP_DUMP)

    for name, expected in _EXPECTED_LENGTHS.items():
        if name in keys and len(keys[name]) != expected:
            raise KeyFileError(f"'{name}' anahtarının uzunluğu hatalı; dosya bozuk olabilir.", _HELP_DUMP)
    for name, value in keys.items():
        if _GEN_KEY_RE.match(name) and len(value) != 16:
            raise KeyFileError(f"'{name}' anahtarının uzunluğu hatalı; dosya bozuk olabilir.", _HELP_DUMP)

    keyset = KeySet(keys, path)
    summary = keyset.summary()
    missing = []
    if "header_key" not in keys:
        missing.append("header_key")
    if not summary.key_area_generations:
        missing.append("key_area_key_application_XX")
    if not summary.titlekek_generations:
        missing.append("titlekek_XX")
    if missing:
        raise KeyFileError(
            "Anahtar dosyasında gerekli anahtarlar eksik: " + ", ".join(missing),
            "Bu dosya tam bir prod.keys değil gibi görünüyor. " + _HELP_DUMP,
        )
    log.info("Anahtar dosyası yüklendi (%d anahtar): %s", len(keyset), path)
    return keyset


def load_title_keys(path: Path) -> dict[bytes, bytes]:
    """`title.keys` dosyasını okur: Rights ID (16 bayt) → şifreli başlık anahtarı (16 bayt)."""
    what = "Başlık anahtarı dosyası (title.keys)"
    entries = _parse_lines(_read_key_text(path, what), path, what)
    result: dict[bytes, bytes] = {}
    for name, value in entries.items():
        try:
            rights_id = bytes.fromhex(name)
        except ValueError:
            raise KeyFileError(f"{what} bozuk: Rights ID onaltılık değil.", _HELP_DUMP) from None
        if len(rights_id) != 16 or len(value) != 16:
            raise KeyFileError(f"{what} bozuk: bir satırın uzunluğu hatalı.", _HELP_DUMP)
        result[rights_id] = value
    log.info("Başlık anahtarı dosyası yüklendi (%d kayıt): %s", len(result), path)
    return result
