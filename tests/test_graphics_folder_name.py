"""Türkçe resim klasörünün adı `turkce/`; eski kurulumların `temiz/` klasörü `turkce/` yokken okunmaya devam eder."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from nxceviri.core.fontpatch import fsdmsg_graphics, nni_graphics
from nxceviri.core.fontpatch.fsdmsg_images import page_key
from nxceviri.core.formats.derived import (
    LEGACY_TURKISH_DIR,
    TURKISH_DIR,
    graphics_status,
    legacy_ignored,
    turkish_dir,
)
from tests.nnicpkbuild import build_dds


def _picture(text: str) -> Image.Image:
    image = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for i, ch in enumerate(text):
        draw.rectangle((4 + i * 12, 8, 12 + i * 12, 24), fill=(255, 255, 255, 255) if ch == "x" else (230, 40, 40, 255))
    return image


def test_constants_and_resolution(tmp_path: Path) -> None:
    assert (TURKISH_DIR, LEGACY_TURKISH_DIR) == ("turkce", "temiz")
    assert turkish_dir(tmp_path) == tmp_path / "turkce"  # hiçbiri yoksa yeni ad
    (tmp_path / "temiz").mkdir()
    assert turkish_dir(tmp_path) == tmp_path / "temiz"  # yalnızca eski
    assert not legacy_ignored(tmp_path)
    (tmp_path / "turkce").mkdir()
    assert turkish_dir(tmp_path) == tmp_path / "turkce"  # ikisi de varsa yeni
    assert legacy_ignored(tmp_path)


def test_status_reads_legacy_folder_and_prefers_turkce(tmp_path: Path) -> None:
    (tmp_path / "orijinal").mkdir()
    (tmp_path / "temiz").mkdir()
    (tmp_path / "orijinal" / "a.png").write_bytes(b"x")
    (tmp_path / "temiz" / "a.png").write_bytes(b"y")
    assert graphics_status(tmp_path) == (1, 1)
    (tmp_path / "turkce").mkdir()
    assert graphics_status(tmp_path) == (1, 0)


def test_nni_legacy_folder_is_read_and_warnings_name_it(tmp_path: Path) -> None:
    (tmp_path / "orijinal").mkdir()
    (tmp_path / "temiz").mkdir()
    _picture("xx").save(tmp_path / "orijinal" / "V_1.png")
    _picture("zz").save(tmp_path / "temiz" / "V_1.png")
    _picture("xx").save(tmp_path / "temiz" / "B.png")  # özgünü yok
    images, warnings = nni_graphics.load(tmp_path)
    assert list(images) == ["V_1"]
    assert warnings == ["temiz/B.png: orijinal/ içinde aynı adlı resim yok; atlandı."]
    assert not (tmp_path / "turkce").exists()  # yeniden adlandırılmadı


def test_nni_turkce_wins_and_legacy_is_warned_about(tmp_path: Path) -> None:
    (tmp_path / "orijinal").mkdir()
    for sub, text in (("turkce", "zz"), ("temiz", "yy")):
        (tmp_path / sub).mkdir()
        _picture(text).save(tmp_path / sub / "V_1.png")
    _picture("xx").save(tmp_path / "orijinal" / "V_1.png")
    images, warnings = nni_graphics.load(tmp_path)
    assert images["V_1"].tobytes() == _picture("zz").tobytes()
    assert len(warnings) == 1
    assert "temiz/" in warnings[0]
    assert "turkce/" in warnings[0]


def test_nni_warning_names_the_active_folder(tmp_path: Path) -> None:
    (tmp_path / "orijinal").mkdir()
    (tmp_path / "turkce").mkdir()
    _picture("xx").save(tmp_path / "turkce" / "B.png")
    _, warnings = nni_graphics.load(tmp_path)
    assert warnings == ["turkce/B.png: orijinal/ içinde aynı adlı resim yok; atlandı."]


def test_nni_folder_for_accepts_either_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(nni_graphics.ENV, raising=False)
    monkeypatch.delenv("NXCEVIRI_YS_GRAFIK", raising=False)
    (tmp_path / nni_graphics.FOLDER / "temiz").mkdir(parents=True)
    assert nni_graphics.folder_for(tmp_path) == tmp_path / nni_graphics.FOLDER


def test_export_originals_creates_turkce_when_fresh_and_keeps_legacy(tmp_path: Path) -> None:
    member = "EXTENSION/STORY/EN/V_1.DDS"
    dds = {nni_graphics.member_path("V_1"): build_dds(_picture("xx"))}
    fresh = tmp_path / "yeni"
    nni_graphics.export_originals(dds.__getitem__, [member], fresh)
    assert (fresh / "turkce").is_dir()
    assert not (fresh / "temiz").exists()
    assert "turkce" in (fresh / "OKUBENI.txt").read_text(encoding="utf-8")
    old = tmp_path / "eski"
    (old / "temiz").mkdir(parents=True)
    nni_graphics.export_originals(dds.__getitem__, [member], old)
    assert not (old / "turkce").exists()


def test_fsdmsg_reads_legacy_folder_and_warns_when_both_exist(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    original = _picture("xx")
    turkish = _picture("zz")
    (tmp_path / "orijinal").mkdir()
    (tmp_path / "temiz").mkdir()
    original.save(tmp_path / "orijinal" / "a.png")
    turkish.save(tmp_path / "temiz" / "a.png")
    assert list(fsdmsg_graphics.load(tmp_path).pages) == [page_key(original)]
    (tmp_path / "turkce").mkdir()
    assert fsdmsg_graphics.load(tmp_path).pages == {}  # turkce/ boş ve öncelikli
    with caplog.at_level(logging.WARNING):
        fsdmsg_graphics.load(tmp_path)
    assert any("temiz/" in r.getMessage() for r in caplog.records)
