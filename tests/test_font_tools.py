"""F aşaması: fontun neden yamanabildiği/yamanamadığı ve düzenlenebilir fontun dışa/içe aktarılması."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.qa.fonts import (
    KIND_TMP_DYNAMIC,
    KIND_TMP_STATIC,
    KIND_TTF,
    FontInfo,
    FontReport,
    font_advice,
    is_editable_font,
    looks_like_font,
)

LATIN = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


def _font(kind: str, source: str = "Font/a.ttf", chars: frozenset[str] = LATIN, patchable: str = "") -> FontInfo:
    return FontInfo("A", source, kind, chars, False, "", patchable)


def test_advice_explains_each_kind() -> None:
    assert "yaması" in font_advice(_font(KIND_TMP_STATIC, patchable="ışğ"))
    assert "dönüştürme" in font_advice(_font(KIND_TMP_STATIC))  # eksik ama üretilemiyor
    assert "yedek" in font_advice(_font(KIND_TMP_DYNAMIC))
    assert "Dışa Aktar" in font_advice(_font(KIND_TTF))
    assert "dönüştürme" in font_advice(_font(KIND_TTF, source="data.unity3d"))  # paket içi TTF
    full = LATIN | frozenset("çğıİöşüÇĞÖŞÜ")
    assert font_advice(_font(KIND_TTF, chars=full)) == "Türkçe harflerin hepsi var."
    assert "dile özgü" in font_advice(FontInfo("J", "Font/ja.ttf", KIND_TTF, LATIN, True))


def test_editable_only_for_loose_ttf_otf() -> None:
    assert is_editable_font(_font(KIND_TTF, "Font/a.ttf"))
    assert is_editable_font(_font(KIND_TTF, "Font/b.OTF"))
    assert not is_editable_font(_font(KIND_TTF, "pak.unity3d"))
    assert not is_editable_font(_font(KIND_TTF, "arsiv.sarc>Font/a.ttf"))
    assert not is_editable_font(_font(KIND_TMP_STATIC, "Font/a.ttf"))


def test_looks_like_font(tmp_path: Path) -> None:
    good = tmp_path / "a.ttf"
    good.write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 20)
    otf = tmp_path / "b.otf"
    otf.write_bytes(b"OTTO" + b"\x00" * 20)
    bad = tmp_path / "c.ttf"
    bad.write_bytes(b"PK\x03\x04")
    assert looks_like_font(good)
    assert looks_like_font(otf)
    assert not looks_like_font(bad)


def test_font_tab_buttons_follow_selection(qtbot: QtBot) -> None:
    from nxceviri.gui.qa_page import QaPage

    page = QaPage()
    qtbot.addWidget(page)
    report = FontReport([_font(KIND_TTF, "Font/a.ttf"), FontInfo("B", "x.unity3d", KIND_TMP_STATIC, LATIN, False)])
    page.show_font_report(report, "")
    page.set_font_overrides({"Font/a.ttf": "C:/duzenli/a.ttf"})
    sources = [page.font_table.item(r, 4).toolTip() for r in range(page.font_table.rowCount())]  # type: ignore[union-attr]
    ttf_row = next(r for r, s in enumerate(sources) if s == "Font/a.ttf")
    page.font_table.selectRow(ttf_row)
    assert page.font_export_button.isEnabled()
    assert page.font_import_button.isEnabled()
    assert page.font_reset_button.isEnabled()  # içe alınmış düzenli font var
    advice = page.font_table.item(ttf_row, 3)
    assert advice is not None
    assert "İçe alındı" in advice.text()
    page.font_table.selectRow(1 - ttf_row)
    assert not page.font_export_button.isEnabled()
    got: list[str] = []
    page.font_export_requested.connect(got.append)
    page.font_table.selectRow(ttf_row)
    page.font_export_button.click()
    assert got == ["Font/a.ttf"]


@pytest.mark.parametrize("missing", [True, False])
def test_reset_disabled_without_override(qtbot: QtBot, missing: bool) -> None:
    from nxceviri.gui.qa_page import QaPage

    page = QaPage()
    qtbot.addWidget(page)
    page.show_font_report(FontReport([_font(KIND_TTF)]), "")
    page.set_font_overrides({} if missing else {"Font/b.ttf": "x"})
    page.font_table.selectRow(0)
    assert not page.font_reset_button.isEnabled()


def test_window_imports_and_resets_edited_font(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    from tests.test_statusbar import _make_window, _project

    w = _make_window(qtbot, tmp_path, _project())
    w.notifier._tray.show_message = lambda *_a: None  # type: ignore[method-assign]
    w.notifier._sound = lambda _level: None
    edited = tmp_path / "duzenli.ttf"
    edited.write_bytes(b"\x00\x01\x00\x00duzenlenmis")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: (str(edited), ""))
    w.import_edited_font("Font/a.ttf")
    tid = w._title_id_hex()
    assert w._font_overrides() == {tid: {"Font/a.ttf": edited.read_bytes()}}
    assert w.notifier.history[0].title == "Düzenlenmiş font içe alındı"

    bad = tmp_path / "bozuk.ttf"
    bad.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: (str(bad), ""))
    w.import_edited_font("Font/b.ttf")
    assert w.notifier.history[0].title == "Bu dosya bir font değil"
    assert "Font/b.ttf" not in w._font_overrides()[tid]

    edited.unlink()  # dosya taşındı/silindi: dışa aktarmada atlanır ve söylenir
    assert w._font_overrides() == {}
    assert w.notifier.history[0].title == "İçe alınan font bulunamadı"
    w.reset_edited_font("Font/a.ttf")
    assert w.project.setting("font_overrides") in ("", "{}")
    w.dirty = False
    w.close()


def test_window_exports_font_file(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from collections.abc import Iterator
    from contextlib import contextmanager
    from types import SimpleNamespace

    from PySide6.QtWidgets import QFileDialog

    from tests.test_statusbar import _make_window, _project

    w = _make_window(qtbot, tmp_path, _project())
    w.notifier._tray.show_message = lambda *_a: None  # type: ignore[method-assign]
    w.notifier._sound = lambda _level: None
    tree = SimpleNamespace(
        view=SimpleNamespace(
            files={"Font/a.ttf"}, open=lambda _p: SimpleNamespace(read_all=lambda: b"\x00\x01\x00\x00f")
        )
    )

    @contextmanager
    def fake_view(*_a: object) -> Iterator[object]:
        yield SimpleNamespace(trees=[tree])

    monkeypatch.setattr("nxceviri.gui.main_window.opened_view", fake_view)
    monkeypatch.setattr("nxceviri.gui.main_window.check_sources", lambda _s: [])
    monkeypatch.setattr(w, "_inputs", lambda: None)
    w.keys = object()  # type: ignore[assignment]
    out = tmp_path / "fontlar"
    out.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(out))
    w.export_font_file("Font/a.ttf")
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)
    assert (out / "a.ttf").read_bytes() == b"\x00\x01\x00\x00f"
    assert w.notifier.history[0].title == "Font dışa aktarıldı"
    w.keys = None
    w.dirty = False
    w.close()
