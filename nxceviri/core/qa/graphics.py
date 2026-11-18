"""Grafik denetimi: `orijinal/` ve `turkce/` resim klasörlerini karşılaştırır (Qt yok, Pillow).

Yerleştirme (`core/fontpatch/nni_graphics._read_ready`) ile aynı kural: Türkçe dosyada alfa kanalı yoksa özgünün
alfası uygulanmış hâli karşılaştırılır. İçerik kutuları yalnızca görsel kılavuzdur; kutudan otomatik sorun çıkmaz
(Türkçe yazı doğal olarak daha geniştir). Hız için numpy yok: kanal işlemleri `point`/`getbbox`/`histogram` ile.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops

from nxceviri.core.errors import OperationCancelled
from nxceviri.core.formats import derived

IMAGE_SUFFIXES = (".png", ".dds")
#: Bundan büyük alfa "içerik" (yazı) sayılır; kutular bununla hesaplanır.
CONTENT_ALPHA = 16
#: Alfası bundan küçük piksel "saydam" sayılır.
TRANSPARENT_ALPHA = 16
#: Alfası bundan büyük piksel "opak" sayılır.
OPAQUE_ALPHA = 240
#: Özgünde saydam piksel oranı bundan azsa resimde anlamlı saydamlık yok demektir.
MEANINGFUL_TRANSPARENCY = 0.10
#: Özgünde saydam olan piksellerin bu orandan fazlası Türkçede opaksa arka plan saydamlığı kaybolmuştur.
OPAQUE_BACKGROUND_RATIO = 0.60

State = Literal["missing", "unchanged", "ready", "orphan", "broken"]
Severity = Literal["error", "warning"]
Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class GraphicsIssue:
    """Bir resimde bulunan sorun; `message` ne olduğunu ve ne yapılacağını söyler."""

    kind: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class GraphicsItem:
    """Bir resmin (ada göre eşleşen özgün + Türkçe çiftinin) denetim sonucu."""

    name: str
    original: Path | None
    turkish: Path | None
    state: State
    issues: tuple[GraphicsIssue, ...]
    original_box: Box | None
    turkish_box: Box | None
    size: tuple[int, int] | None
    #: Türkçe dosya baytlarının sha1'i (onay kaydı için); dosya yoksa "".
    digest: str


@dataclass(frozen=True)
class GraphicsSummary:
    """Arayüzdeki sayaç için özet."""

    total_originals: int
    ready: int
    missing: int
    #: En az bir hata sorunu olan resim sayısı.
    errors: int
    #: Hata sorunu olmayıp uyarısı olan resim sayısı.
    warnings: int


def _images(folder: Path) -> dict[str, Path]:
    if not folder.is_dir():
        return {}
    found: dict[str, Path] = {}
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            found.setdefault(path.stem, path)
    return found


def _mask(alpha: Image.Image, test: Callable[[int], bool]) -> Image.Image:
    """Alfası `test`ten geçen pikselleri 255, diğerlerini 0 yapan maske."""
    return alpha.point([255 if test(value) else 0 for value in range(256)])


def _transparent_ratio(alpha: Image.Image) -> float:
    histogram = alpha.histogram()
    return sum(histogram[:TRANSPARENT_ALPHA]) / max(1, alpha.width * alpha.height)


def _box(content: Image.Image) -> Box | None:
    return content.getbbox()


def _edges(content: Image.Image) -> set[str]:
    """İçerik maskesinin değdiği kenarlar (üst, alt, sol, sağ)."""
    width, height = content.size
    strips = {
        "üst": (0, 0, width, 1),
        "alt": (0, height - 1, width, height),
        "sol": (0, 0, 1, height),
        "sağ": (width - 1, 0, width, height),
    }
    return {name for name, area in strips.items() if content.crop(area).getbbox() is not None}


def _check_pair(name: str, original: Path, turkish: Path) -> GraphicsItem:
    digest = hashlib.sha1(turkish.read_bytes()).hexdigest()
    try:
        with Image.open(original) as source:
            before = source.convert("RGBA")
        with Image.open(turkish) as raw:
            has_alpha = "A" in raw.getbands() or "transparency" in raw.info or turkish.suffix.lower() == ".dds"
            after = raw.convert("RGBA")
    except (OSError, ValueError, SyntaxError):
        issue = GraphicsIssue("broken", "error", "Resim açılamadı; dosya bozuk olabilir. Yeniden kaydedin.")
        return GraphicsItem(name, original, turkish, "broken", (issue,), None, None, None, digest)

    before_alpha = before.getchannel("A")
    meaningful = _transparent_ratio(before_alpha) >= MEANINGFUL_TRANSPARENCY
    original_content = _mask(before_alpha, lambda value: value > CONTENT_ALPHA)
    original_box = _box(original_content) if meaningful else None
    issues: list[GraphicsIssue] = []
    state: State = "ready"

    if after.size != before.size:
        issues.append(
            GraphicsIssue(
                "size",
                "error",
                f"Boyut {after.width}×{after.height}, özgün {before.width}×{before.height}; "
                "aynı olmalı. Resmi özgün boyda kaydedin.",
            )
        )
        turkish_box = _box(_mask(after.getchannel("A"), lambda value: value > CONTENT_ALPHA)) if meaningful else None
        return GraphicsItem(
            name, original, turkish, state, tuple(issues), original_box, turkish_box, before.size, digest
        )

    if not has_alpha:
        after.putalpha(before_alpha)
    after_alpha = after.getchannel("A")
    turkish_content = _mask(after_alpha, lambda value: value > CONTENT_ALPHA)
    turkish_box = _box(turkish_content) if meaningful else None

    if after.tobytes() == before.tobytes():
        state = "unchanged"
        issues.append(GraphicsIssue("unchanged", "warning", "Resim özgünle aynı; düzenlenmemiş. Türkçesini kaydedin."))

    if meaningful and has_alpha:
        transparent = _mask(before_alpha, lambda value: value < TRANSPARENT_ALPHA)
        opaque = _mask(after_alpha, lambda value: value > OPAQUE_ALPHA)
        total = transparent.histogram()[255]
        both = ImageChops.multiply(transparent, opaque).histogram()[255]
        if total and both / total >= OPAQUE_BACKGROUND_RATIO:
            issues.append(
                GraphicsIssue(
                    "opaque_background",
                    "error",
                    "Arka plan saydamlığı kaybolmuş; PNG'yi saydam arka planla (alfa kanalı) kaydedin.",
                )
            )

    if meaningful:
        touched = _edges(turkish_content) - _edges(original_content)
        if touched:
            issues.append(
                GraphicsIssue(
                    "edge",
                    "warning",
                    "Yazı resmin kenarına değiyor; oyunda kesilebilir, gözle bakın.",
                )
            )
    return GraphicsItem(name, original, turkish, state, tuple(issues), original_box, turkish_box, before.size, digest)


def _original_only(name: str, original: Path) -> GraphicsItem:
    try:
        with Image.open(original) as source:
            size = source.size
            alpha = source.convert("RGBA").getchannel("A")
    except (OSError, ValueError, SyntaxError):
        return GraphicsItem(name, original, None, "missing", (), None, None, None, "")
    meaningful = _transparent_ratio(alpha) >= MEANINGFUL_TRANSPARENCY
    box = _box(_mask(alpha, lambda value: value > CONTENT_ALPHA)) if meaningful else None
    return GraphicsItem(name, original, None, "missing", (), box, None, size, "")


def check_folders(
    original_dir: Path, turkish_dir: Path, *, cancel: Callable[[], bool] | None = None
) -> list[GraphicsItem]:
    """İki klasördeki resimleri adlarına göre eşleyip denetler; ada göre sıralı döner.

    Klasör yoksa boş sayılır. `cancel()` True dönerse `OperationCancelled` fırlatılır (projenin diğer uzun
    işleriyle aynı iptal sözleşmesi; yarım liste sessizce dönmez, arayüz iptali açıkça bilir)."""
    originals = _images(original_dir)
    turkish = _images(turkish_dir)
    items: list[GraphicsItem] = []
    for name in sorted(originals.keys() | turkish.keys()):
        if cancel is not None and cancel():
            raise OperationCancelled
        old = originals.get(name)
        new = turkish.get(name)
        if old is not None and new is not None:
            items.append(_check_pair(name, old, new))
        elif old is not None:
            items.append(_original_only(name, old))
        elif new is not None:
            digest = hashlib.sha1(new.read_bytes()).hexdigest()
            issue = GraphicsIssue(
                "orphan",
                "error",
                "Adı yanlış olabilir; orijinal/ içinde aynı adlı resim yok. Adı özgün resimle aynı yapın.",
            )
            items.append(GraphicsItem(name, None, new, "orphan", (issue,), None, None, None, digest))
    return items


def check_graphics_folder(folder: Path, *, cancel: Callable[[], bool] | None = None) -> list[GraphicsItem]:
    """`folder/orijinal` ile `turkce/` (yoksa eski `temiz/`) klasörünü karşılaştırır."""
    return check_folders(folder / "orijinal", derived.turkish_dir(folder), cancel=cancel)


def summary(items: list[GraphicsItem]) -> GraphicsSummary:
    """Sayaç için özet: özgün sayısı, hazır (Türkçesi var ve değişmiş), eksik, hatalı ve yalnız uyarılı resimler."""
    errors = sum(1 for item in items if any(issue.severity == "error" for issue in item.issues))
    warnings = sum(1 for item in items if item.issues and all(issue.severity == "warning" for issue in item.issues))
    return GraphicsSummary(
        total_originals=sum(1 for item in items if item.original is not None),
        ready=sum(1 for item in items if item.state == "ready"),
        missing=sum(1 for item in items if item.state == "missing"),
        errors=errors,
        warnings=warnings,
    )
