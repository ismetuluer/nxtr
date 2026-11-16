"""`.fsd`/`.msg` biçimli oyunun ek çeviri verisi: resimlerdeki yazılar ve program kodundaki düşman açıklamaları.

Bu veri oyuna özgü çeviridir; uygulamayla gelmez. Kullanıcı kendi hazırladığı (ya da edindiği) iki isteğe bağlı JSON
dosyasını grafik klasörüne (`NXCEVIRI_FSD_GRAFIK`) koyar:

- `resim_yazilari.json`: `{"dosyalar": [RomFS yolları], "sayfalar": [{"ozetler": [sayfa özetleri], "etiketler":
  [{"pencere": [sol, üst, sağ, alt], "ingilizce": "…", "turkce": "…", isteğe bağlı "stil", "hiza", "murekkep",
  "parilti", "esik", "kutu", "dolgu", "boy", "kaydir"}]}]}` (sayfa özeti: `fsdmsg_images.page_key`); isteğe bağlı
  `"menuler": [{"dokular": [8 haneli onaltılık doku kimlikleri], "etiketler": [aynı etiket şeması]}]` durum menüsü
  başlık dokularını (`fsdmsg_menu`) çevirir;
- `aciklamalar.json`: `{"aciklamalar": [{"ozet": özgün İngilizce metnin SHA-256'sı, "turkce": "…"}]}`, kod sırasıyla.

Dosya yoksa o yazılar çevrilmeden kalır (dışa aktarma bilgi dosyasına not düşülür). Dosya bozuksa dışa aktarma, neyin
bozuk olduğunu söyleyen bir hatayla durur; yarım mod yazılmaz. Biçim: docs/formats/fsd-msg.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from nxceviri.core.errors import NxError
from nxceviri.core.fontpatch.labels import STYLES, Label

IMAGE_TEXTS = "resim_yazilari.json"
DESCRIPTIONS = "aciklamalar.json"

_HINT = (
    "Dosyayı bir metin düzenleyiciyle düzeltin (biçim: docs/formats/fsd-msg.md) ya da klasörden kaldırın; "
    "kaldırırsanız bu yazılar çevrilmeden kalır."
)
_PAGE_KEY = re.compile(r"[0-9a-f]{16}")
_TEXTURE_ID = re.compile(r"[0-9A-Fa-f]{8}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ALIGNS = ("center", "left", "right")
_FILLS = ("spread", "filter", "keep")
#: Etiket alanları: JSON adı → (`Label` alanı, zorunlu mu).
_LABEL_FIELDS = {
    "pencere": ("window", True),
    "ingilizce": ("english", True),
    "turkce": ("turkish", True),
    "stil": ("style", False),
    "hiza": ("align", False),
    "murekkep": ("ink", False),
    "parilti": ("glow", False),
    "esik": ("threshold", False),
    "kutu": ("box", False),
    "dolgu": ("fill", False),
    "boy": ("size", False),
    "kaydir": ("shift", False),
}


class UserDataError(NxError):
    """Ek çeviri verisi dosyası okunamadı ya da biçimi yanlış."""


@dataclass(frozen=True)
class ImageTexts:
    files: tuple[str, ...]  # sayfaların geçtiği oyun dosyaları (RomFS'e göre)
    pages: dict[str, tuple[Label, ...]]  # sayfa özeti → etiketler
    menus: dict[int, tuple[Label, ...]] | None = None  # menü doku kimliği → sözcükler (bölüm yoksa None)


@dataclass(frozen=True)
class UserData:
    image_texts: ImageTexts | None
    descriptions: tuple[tuple[str, str], ...] | None  # (özgün metnin özeti, Türkçe), kod sırasıyla

    @property
    def missing(self) -> tuple[str, ...]:
        """Klasörde bulunmayan veri dosyalarının adları."""
        found = {IMAGE_TEXTS: self.image_texts, DESCRIPTIONS: self.descriptions}
        return tuple(name for name, value in found.items() if value is None)


class _Reader:
    """Tek dosyanın şema denetimi; hatalar dosya adı ve alan yoluyla bildirilir (sıra numaraları 1'den başlar)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def fail(self, where: str, problem: str) -> UserDataError:
        return UserDataError(f"{self.name} kullanılamadı: {where or 'dosyanın tamamı'} {problem}.", _HINT)

    def object(self, value: Any, where: str, fields: dict[str, bool]) -> dict[str, Any]:
        """`fields`: alan adı → zorunlu mu. Bilinmeyen alan (ör. yazım hatası) hata sayılır."""
        if not isinstance(value, dict):
            raise self.fail(where, "bir JSON nesnesi ({…}) olmalı")
        for key in value:
            if key not in fields:
                raise self.fail(f"{where}.{key}" if where else key, "tanınmayan alan; adını denetleyin")
        for key, required in fields.items():
            if required and key not in value:
                raise self.fail(f"{where}.{key}" if where else key, "eksik")
        return value

    def items(self, value: Any, where: str) -> list[Any]:
        if not isinstance(value, list):
            raise self.fail(where, "bir liste ([…]) olmalı")
        return value

    def text(self, value: Any, where: str, *, empty: bool = False) -> str:
        if not isinstance(value, str) or (not empty and not value):
            raise self.fail(where, "boş olmayan bir metin olmalı")
        return value

    def number(self, value: Any, where: str, low: int, high: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise self.fail(where, f"{low} ile {high} arasında bir tam sayı olmalı")
        return value

    def numbers(self, value: Any, where: str, count: int, high: int) -> tuple[int, ...]:
        values = self.items(value, where)
        if len(values) != count:
            raise self.fail(where, f"{count} sayıdan oluşan bir liste olmalı")
        return tuple(self.number(v, f"{where}[{i}]", 0, high) for i, v in enumerate(values, 1))

    def box(self, value: Any, where: str) -> tuple[int, int, int, int]:
        left, top, right, bottom = self.numbers(value, where, 4, 1 << 16)
        if not (left < right and top < bottom):
            raise self.fail(where, "[sol, üst, sağ, alt] olmalı (sol < sağ, üst < alt)")
        return left, top, right, bottom

    def choice(self, value: Any, where: str, options: tuple[str, ...]) -> str:
        if value not in options:
            raise self.fail(where, "şunlardan biri olmalı: " + ", ".join(options))
        return str(value)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise UserDataError(f"{path.name} okunamadı: {exc.strerror or exc}.", _HINT) from exc
    except UnicodeDecodeError as exc:
        raise UserDataError(f"{path.name} UTF-8 metin değil.", _HINT) from exc
    except json.JSONDecodeError as exc:
        raise UserDataError(f"{path.name} geçerli JSON değil ({exc.lineno}. satır: {exc.msg}).", _HINT) from exc


def _romfs_path(reader: _Reader, value: Any, where: str) -> str:
    path = reader.text(value, where)
    parts = PurePosixPath(path).parts
    if "\\" in path or ":" in path or path.startswith("/") or ".." in parts:
        raise reader.fail(where, "RomFS'e göre göreli bir yol olmalı (ör. data/etc/menu.t32)")
    return path


def _label(reader: _Reader, value: Any, where: str) -> Label:
    row = reader.object(value, where, {key: required for key, (_name, required) in _LABEL_FIELDS.items()})
    out: dict[str, Any] = {}
    for key, raw in row.items():
        at = f"{where}.{key}"
        name = _LABEL_FIELDS[key][0]
        if key in ("pencere", "kutu"):
            out[name] = reader.box(raw, at)
        elif key in ("ingilizce", "turkce"):
            out[name] = reader.text(raw, at, empty=key == "turkce")
        elif key == "stil":
            out[name] = reader.choice(raw, at, tuple(STYLES))
        elif key == "hiza":
            out[name] = reader.choice(raw, at, _ALIGNS)
        elif key == "dolgu":
            out[name] = reader.choice(raw, at, _FILLS)
        elif key in ("murekkep", "parilti"):
            out[name] = reader.numbers(raw, at, 3, 255)
        elif key == "esik":
            out[name] = reader.number(raw, at, 0, 255)
        elif key == "boy":
            out[name] = reader.number(raw, at, 1, 1024)
        else:
            out[name] = reader.number(raw, at, -4096, 4096)
    return Label(**out)


def load_image_texts(path: Path) -> ImageTexts:
    reader = _Reader(path.name)
    root = reader.object(_read(path), "", {"dosyalar": True, "sayfalar": True, "menuler": False})
    listed = reader.items(root["dosyalar"], "dosyalar")
    files = tuple(_romfs_path(reader, p, f"dosyalar[{i}]") for i, p in enumerate(listed, 1))
    pages: dict[str, tuple[Label, ...]] = {}
    for i, raw in enumerate(reader.items(root["sayfalar"], "sayfalar"), 1):
        where = f"sayfalar[{i}]"
        page = reader.object(raw, where, {"ozetler": True, "etiketler": True})
        labels = _labels(reader, page["etiketler"], f"{where}.etiketler")
        for k, key in enumerate(reader.items(page["ozetler"], f"{where}.ozetler"), 1):
            if not isinstance(key, str) or not _PAGE_KEY.fullmatch(key):
                raise reader.fail(f"{where}.ozetler[{k}]", "16 haneli küçük harfli onaltılık sayfa özeti olmalı")
            pages[key] = labels
    menus = _menus(reader, root["menuler"]) if "menuler" in root else None
    return ImageTexts(files, pages, menus)


def _labels(reader: _Reader, raw: Any, where: str) -> tuple[Label, ...]:
    return tuple(_label(reader, row, f"{where}[{k}]") for k, row in enumerate(reader.items(raw, where), 1))


def _menus(reader: _Reader, raw: Any) -> dict[int, tuple[Label, ...]]:
    """Menü dokuları: doku kimliği (T32 başlığında 0x14) → sözcükler; bir kimlik yalnızca bir kez geçebilir."""
    out: dict[int, tuple[Label, ...]] = {}
    for i, value in enumerate(reader.items(raw, "menuler"), 1):
        where = f"menuler[{i}]"
        group = reader.object(value, where, {"dokular": True, "etiketler": True})
        labels = _labels(reader, group["etiketler"], f"{where}.etiketler")
        for k, key in enumerate(reader.items(group["dokular"], f"{where}.dokular"), 1):
            at = f"{where}.dokular[{k}]"
            if not isinstance(key, str) or not _TEXTURE_ID.fullmatch(key):
                raise reader.fail(at, "8 haneli onaltılık doku kimliği olmalı (ör. 0A1B2C3D)")
            if int(key, 16) in out:
                raise reader.fail(at, f"yineleniyor ({key.upper()} daha önce verildi)")
            out[int(key, 16)] = labels
    return out


def load_descriptions(path: Path) -> tuple[tuple[str, str], ...]:
    reader = _Reader(path.name)
    root = reader.object(_read(path), "", {"aciklamalar": True})
    rows = reader.items(root["aciklamalar"], "aciklamalar")
    if not rows:
        raise reader.fail("aciklamalar", "en az bir açıklama içermeli")
    out = []
    for i, raw in enumerate(rows, 1):
        where = f"aciklamalar[{i}]"
        row = reader.object(raw, where, {"ozet": True, "turkce": True})
        digest = row["ozet"]
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise reader.fail(f"{where}.ozet", "64 haneli küçük harfli onaltılık SHA-256 özeti olmalı")
        out.append((digest, reader.text(row["turkce"], f"{where}.turkce")))
    return tuple(out)


def load(folder: Path | None) -> UserData:
    """Klasördeki veri dosyalarını okur ve denetler; olmayan dosya None kalır, bozuk dosya `UserDataError` verir."""
    if folder is None:
        return UserData(None, None)
    texts, descriptions = folder / IMAGE_TEXTS, folder / DESCRIPTIONS
    return UserData(
        load_image_texts(texts) if texts.is_file() else None,
        load_descriptions(descriptions) if descriptions.is_file() else None,
    )


def missing_note(data: UserData, folder: Path | None, variable: str) -> str | None:
    """Eksik veri için bilgi dosyasına yazılacak satır (hiçbir şey eksik değilse None)."""
    names = list(data.missing)
    no_menus = data.image_texts is not None and data.image_texts.menus is None
    if not names and not no_menus:
        return None
    parts = []
    if names:
        what = {IMAGE_TEXTS: "resimlerdeki yazılar ve menü başlıkları", DESCRIPTIONS: "düşman açıklamaları"}
        parts.append("Ek çeviri verisi bulunamadı; " + " ve ".join(what[n] for n in names) + " İngilizce kaldı.")
        if folder is None:
            parts.append(
                f"Bunları da çevirmek için {variable} ortam değişkeni tanımlı değil (ya da gösterdiği klasör yok): "
                "değişkeni grafik klasörünüze yönlendirin ve " + ", ".join(names) + " dosyalarını oraya koyun."
            )
        else:
            parts.append("Bunları da çevirmek için " + ", ".join(names) + f" dosyasını {folder} klasörüne koyun.")
    if no_menus:
        parts.append(
            f'{IMAGE_TEXTS} dosyasında "menuler" bölümü yok; durum menüsü başlık dokuları İngilizce kaldı '
            "(bölümün biçimi: docs/formats/fsd-msg.md)."
        )
    return " ".join(parts)
