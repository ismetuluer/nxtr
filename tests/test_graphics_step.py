"""F aşaması: Görseller — resim çevirisini destekleyen oyunlarda özgünleri çıkarma, klasör ve durum."""

from __future__ import annotations

from collections.abc import Collection, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.derived import GraphicsSupport, graphics_status


def test_status_counts_originals_and_ready(tmp_path: Path) -> None:
    assert graphics_status(tmp_path / "yok") == (0, 0)
    (tmp_path / "orijinal").mkdir()
    (tmp_path / "temiz").mkdir()
    for name in ("a", "b", "c"):
        (tmp_path / "orijinal" / f"{name}.png").write_bytes(b"x")
    (tmp_path / "temiz" / "a.png").write_bytes(b"y")
    (tmp_path / "temiz" / "notlar.txt").write_text("-", encoding="utf-8")  # resim değil
    assert graphics_status(tmp_path) == (3, 1)


def test_ys_origin_supports_graphics() -> None:
    from nxceviri.core.formats.ysorigin.plugin import YsOriginPlugin

    support = YsOriginPlugin.graphics
    assert isinstance(support, GraphicsSupport)
    assert support.folder_name == "grafik_temizleme"


def test_export_page_card_hidden_without_support(qtbot: QtBot) -> None:
    from nxceviri.gui.export_page import ExportPage

    page = ExportPage()
    qtbot.addWidget(page)
    page.set_graphics(None, (0, 0))
    assert not page.graphics_card.isVisibleTo(page)
    page.set_graphics(Path("D:/oyun/grafik_temizleme"), (148, 12))
    assert page.graphics_card.isVisibleTo(page)
    assert "12 / 148" in page.graphics_status.text()


def test_extract_originals_from_window(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_statusbar import _make_window, _project

    w = _make_window(qtbot, tmp_path, _project())
    w.notifier._tray.show_message = lambda *_a: None  # type: ignore[method-assign]
    w.notifier._sound = lambda _level: None
    folder = tmp_path / "grafik_temizleme"

    def export(_reader: object, _files: Collection[str], target: Path) -> list[str]:
        (target / "orijinal").mkdir(parents=True, exist_ok=True)
        (target / "orijinal" / "MAP_EN.png").write_bytes(b"png")
        return ["MAP_EN"]

    support = GraphicsSupport("grafik_temizleme", export)
    monkeypatch.setattr(w, "_graphics", lambda: (support, folder))

    @contextmanager
    def fake_view(*_a: object) -> Iterator[object]:
        yield SimpleNamespace(trees=[SimpleNamespace(view=SimpleNamespace(files=set()), code=None)])

    monkeypatch.setattr("nxceviri.gui.main_window.opened_view", fake_view)
    monkeypatch.setattr("nxceviri.gui.main_window.check_sources", lambda _s: [])
    monkeypatch.setattr("nxceviri.gui.main_window.MemberReader", lambda *_a: None)
    monkeypatch.setattr(w, "_inputs", lambda: None)
    w.keys = object()  # type: ignore[assignment]
    w.extract_graphics()
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)
    assert (folder / "orijinal" / "MAP_EN.png").is_file()
    notice = w.notifier.history[0]
    assert notice.title == "Görseller çıkarıldı"
    assert "1 resim" in notice.text
    assert [a.label for a in notice.actions] == ["Klasörü Aç"]
    assert "0 / 1" in w.export_page.graphics_status.text()
    w.keys = None
    w.dirty = False
    w.close()
