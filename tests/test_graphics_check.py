"""Kontrol Et grafik denetimi çekirdeği (core/qa/graphics.py): elle üretilmiş küçük resimlerle."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest
from PIL import Image

from nxceviri.core.errors import OperationCancelled
from nxceviri.core.qa.graphics import GraphicsItem, check_folders, check_graphics_folder, summary

W, H = 64, 32


def _original(box: tuple[int, int, int, int] = (10, 8, 50, 24)) -> Image.Image:
    """Saydam zemin üstünde opak 'yazı' dikdörtgeni."""
    image = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    image.paste((255, 255, 255, 255), box)
    return image


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    original = tmp_path / "orijinal"
    turkish = tmp_path / "turkce"
    original.mkdir()
    turkish.mkdir()
    return original, turkish


def _one(items: list[GraphicsItem], name: str = "a") -> GraphicsItem:
    return next(item for item in items if item.name == name)


def _kinds(item: GraphicsItem) -> set[str]:
    return {issue.kind for issue in item.issues}


def test_ready_without_issues_and_boxes(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    _original((8, 8, 56, 24)).save(turkish / "a.png")  # yazı geniş: sorun DEĞİL
    item = _one(check_folders(original, turkish))
    assert item.state == "ready"
    assert item.issues == ()
    assert item.original_box == (10, 8, 50, 24)
    assert item.turkish_box == (8, 8, 56, 24)
    assert item.size == (W, H)
    assert item.digest == hashlib.sha1((turkish / "a.png").read_bytes()).hexdigest()


def test_missing(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    item = _one(check_folders(original, turkish))
    assert item.state == "missing"
    assert item.turkish is None
    assert item.digest == ""
    assert item.issues == ()


def test_orphan_is_error(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(turkish / "a.png")
    item = _one(check_folders(original, turkish))
    assert item.state == "orphan"
    assert item.original is None
    assert [(i.kind, i.severity) for i in item.issues] == [("orphan", "error")]


def test_missing_directories_count_as_empty(tmp_path: Path) -> None:
    assert check_folders(tmp_path / "yok1", tmp_path / "yok2") == []


def test_broken_file(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    (turkish / "a.png").write_bytes(b"bu bir resim degil")
    item = _one(check_folders(original, turkish))
    assert item.state == "broken"
    assert [(i.kind, i.severity) for i in item.issues] == [("broken", "error")]
    assert item.digest != ""


def test_broken_dds_counts(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    (turkish / "a.DDS").write_bytes(b"bozuk")
    item = _one(check_folders(original, turkish))
    assert item.state == "broken"
    assert item.turkish == turkish / "a.DDS"


def test_size_mismatch_is_error_with_wording(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    Image.new("RGBA", (W - 4, H), (0, 0, 0, 0)).save(turkish / "a.png")
    item = _one(check_folders(original, turkish))
    issue = next(i for i in item.issues if i.kind == "size")
    assert issue.severity == "error"
    assert "Boyut 60×32, özgün 64×32; aynı olmalı." in issue.message
    assert item.state == "ready"


def test_unchanged_copy_is_warning(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    _original().save(turkish / "a.png")
    item = _one(check_folders(original, turkish))
    assert item.state == "unchanged"
    assert [(i.kind, i.severity) for i in item.issues] == [("unchanged", "warning")]


def test_unchanged_when_turkish_has_no_alpha_but_same_after_original_alpha(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    source = _original()
    source.save(original / "a.png")
    source.convert("RGB").save(turkish / "a.png")  # alfa yok; özgünün alfası uygulanınca aynı
    item = _one(check_folders(original, turkish))
    assert item.state == "unchanged"


def test_opaque_background_is_error(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    Image.new("RGBA", (W, H), (20, 20, 20, 255)).save(turkish / "a.png")
    item = _one(check_folders(original, turkish))
    assert next(i for i in item.issues if i.kind == "opaque_background").severity == "error"


def test_opaque_background_skipped_without_alpha_channel(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    Image.new("RGB", (W, H), (20, 20, 20)).save(turkish / "a.png")
    item = _one(check_folders(original, turkish))
    assert "opaque_background" not in _kinds(item)


def test_edge_touch_is_warning(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    _original((0, 8, 50, 24)).save(turkish / "a.png")  # sol kenara değiyor
    item = _one(check_folders(original, turkish))
    issue = next(i for i in item.issues if i.kind == "edge")
    assert issue.severity == "warning"
    assert "kenarına değiyor" in issue.message


def test_edge_not_flagged_when_original_touches_too(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original((0, 8, 50, 24)).save(original / "a.png")
    _original((0, 6, 52, 26)).save(turkish / "a.png")
    assert "edge" not in _kinds(_one(check_folders(original, turkish)))


def test_no_transparency_gives_no_boxes_or_edge(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    Image.new("RGBA", (W, H), (9, 9, 9, 255)).save(original / "a.png")
    Image.new("RGBA", (W, H), (200, 9, 9, 255)).save(turkish / "a.png")
    item = _one(check_folders(original, turkish))
    assert item.original_box is None
    assert item.turkish_box is None
    assert item.issues == ()


def test_legacy_temiz_folder(tmp_path: Path) -> None:
    (tmp_path / "orijinal").mkdir()
    (tmp_path / "temiz").mkdir()
    _original().save(tmp_path / "orijinal" / "a.png")
    _original((8, 8, 56, 24)).save(tmp_path / "temiz" / "a.png")
    assert _one(check_graphics_folder(tmp_path)).state == "ready"


def test_sorted_and_case_insensitive_suffix(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    for name in ("b", "a"):
        _original().save(original / f"{name}.png")
    _original((8, 8, 56, 24)).save(turkish / "a.PNG")
    (turkish / "not.txt").write_text("x")
    items = check_folders(original, turkish)
    assert [item.name for item in items] == ["a", "b"]
    assert items[0].state == "ready"


def test_cancel_raises(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    with pytest.raises(OperationCancelled):
        check_folders(original, turkish, cancel=lambda: True)


def test_digest_changes_with_file(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    _original().save(original / "a.png")
    _original((8, 8, 56, 24)).save(turkish / "a.png")
    first = _one(check_folders(original, turkish)).digest
    _original((6, 8, 56, 24)).save(turkish / "a.png")
    assert _one(check_folders(original, turkish)).digest != first


def test_summary_counts(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    for name in ("a", "b", "c", "d"):
        _original().save(original / f"{name}.png")
    _original((8, 8, 56, 24)).save(turkish / "a.png")  # hazır
    _original().save(turkish / "b.png")  # değişmemiş (uyarı)
    Image.new("RGBA", (W, H), (1, 1, 1, 255)).save(turkish / "c.png")  # saydamlık kaybı (hata)
    _original().save(turkish / "zzz.png")  # yetim (hata)
    result = summary(check_folders(original, turkish))
    assert result.total_originals == 4
    assert result.ready == 2  # a ve c: Türkçesi var, değişmiş, açılabiliyor
    assert result.missing == 1  # d
    assert result.errors == 2  # c ve zzz
    assert result.warnings == 1  # b


def test_big_pair_is_fast(tmp_path: Path) -> None:
    original, turkish = _dirs(tmp_path)
    big = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    big.paste((255, 255, 255, 255), (300, 400, 1500, 700))
    big.save(original / "a.png")
    other = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    other.paste((255, 255, 255, 255), (200, 400, 1600, 700))
    other.save(turkish / "a.png")
    start = time.perf_counter()
    item = _one(check_folders(original, turkish))
    assert item.state == "ready"
    assert time.perf_counter() - start < 2.0
