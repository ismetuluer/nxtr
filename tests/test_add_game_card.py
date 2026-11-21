"""Oyunu Ekle sayfasının oyun kartı: rozetler, ek içerik ızgarası, eylemler, boş durum, eski projede simge doldurma."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSettings
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from nxceviri.core.project import Project, SourceRecord
from nxceviri.gui.add_game_page import RELINK_ACTION, AddGamePage
from nxceviri.gui.game_card import initials, rounded_cover
from nxceviri.gui.main_window import MainWindow
from tests import nxbuild
from tests.test_gui import _wait_idle

pytestmark = pytest.mark.gui


def _jpeg(color: str = "#3366cc", side: int = 64) -> bytes:
    image = QImage(side, side, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, format="JPG")  # type: ignore[call-overload]
    return bytes(data.data())


def _source(
    tmp_path: Path, kind: str, name: str, *, exists: bool = True, version: int = 0, **extra: object
) -> SourceRecord:
    path = tmp_path / f"{name}.nsp"
    if exists:
        path.write_bytes(b"x" * 2048)
    return SourceRecord(
        path=path,
        kind=kind,
        title_id="0100000000010000" if kind != "dlc" else "0100000000010001",
        application_id="0100000000010000",
        version=version,
        display_version="1.0.0" if kind == "base" else "",
        name=name,
        file_size=2048,
        **extra,  # type: ignore[arg-type]
    )


def _page(qtbot: QtBot) -> AddGamePage:
    page = AddGamePage()
    qtbot.addWidget(page)
    page.resize(1000, 800)
    page.show()
    return page


def _full(tmp_path: Path) -> list[SourceRecord]:
    return [
        _source(tmp_path, "base", "Deneme Oyunu", icon=_jpeg(), publisher="Test Yayıncı"),
        _source(tmp_path, "update", "Deneme Oyunu", version=65536),
        _source(tmp_path, "dlc", "Ek Paket A"),
        _source(tmp_path, "dlc", "Ek Paket B", exists=False),
    ]


def test_initials() -> None:
    assert initials("Deneme Oyunu") == "DO"
    assert initials("Tek") == "TE"
    assert initials("") == "?"
    assert initials("¡¿") == "?"


def test_rounded_cover_rejects_garbage_and_scales_to_dpr(qtbot: QtBot) -> None:
    assert rounded_cover(b"jpeg degil", 112, 12, 1.0) is None
    pixmap = rounded_cover(_jpeg(), 112, 12, 2.0)
    assert pixmap is not None
    assert (pixmap.width(), pixmap.devicePixelRatio()) == (224, 2.0)


def test_empty_page_shows_only_drop_zone_and_guide(qtbot: QtBot) -> None:
    page = _page(qtbot)
    assert page.game_card.isHidden()
    assert page.dlc_card.isHidden()
    assert page.steps_card.isVisible()
    assert page.drop.text.text() == "NSP / NSZ dosyalarını bırakın"
    assert page.drop.mascot.isVisible()


def test_game_card_pills_and_details(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    sources = _full(tmp_path)
    page.set_sources(sources)
    page.set_progress(57464, 51718)
    card = page.game_card
    assert card.name.text() == "Deneme Oyunu"
    assert card.cover.has_image()
    assert [p.text() for p in card.pills()] == [
        "Ana oyun · 1.0.0",
        "Güncelleme · v65536",
        "2 ek içerik",
        "57.464 satır · %90 çevrildi",
    ]
    assert card.meta.text() == "Oyun kimliği 0100000000010000  ·  Yayıncı · Test Yayıncı"
    tip = card.pills()[0].toolTip()
    for part in ("Deneme Oyunu.nsp", "2,0 KB", "0100000000010000", "v0", "Ana oyun"):  # eski tablodaki bilgiler
        assert part in tip
    assert page.steps_card.isHidden()
    assert not page.drop.mascot.isVisible()
    assert page.drop.text.text() == "Yeni NSP / NSZ dosyalarını buraya bırakabilirsiniz"
    page.set_progress(0, 0)
    assert len(card.pills()) == 3  # satır yoksa çeviri rozeti görünmez


def test_placeholder_cover_without_icon(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    page.set_sources([_source(tmp_path, "base", "Deneme Oyunu")])
    assert not page.game_card.cover.has_image()
    assert page.game_card.cover.text() == "DO"
    assert page.game_card.meta.text() == "Oyun kimliği 0100000000010000"  # yayıncı yoksa yazılmaz
    page.set_sources([_source(tmp_path, "base", "Bozuk", icon=b"\xff\xd8\xff-bozuk")])
    assert not page.game_card.cover.has_image()  # okunamayan simge sessizce yer tutucuya düşer


def test_missing_game_file_marks_pill_and_keeps_tooltip(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    page.set_sources([_source(tmp_path, "base", "Deneme Oyunu", exists=False)])
    pill = page.game_card.pills()[0]
    assert pill.text().endswith("bulunamadı")
    assert pill.property("state") == "danger"
    assert "Dosya bulunamadı" in pill.toolTip()


def test_dlc_card_tiles_summary_and_relink(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    page.set_sources(_full(tmp_path))
    dlc = page.dlc_card
    assert dlc.isVisible()
    assert dlc.summary.text() == "2 dosya · 1 eksik"
    assert [t.name.full_text() for t in dlc.tiles] == ["Ek Paket A", "Ek Paket B"]
    assert [t.property("state") for t in dlc.tiles] == ["success", "danger"]
    assert dlc.tiles[0].link is None
    assert dlc.tiles[1].link is not None
    with qtbot.waitSignal(page.relink_requested):
        dlc.tiles[1].link.click()
    page.set_sources([s for s in _full(tmp_path) if s.kind != "dlc"])
    assert dlc.isHidden()  # ek içerik yoksa kart görünmez
    page.set_sources([_source(tmp_path, "base", "Deneme Oyunu"), _source(tmp_path, "dlc", "Ek Paket A")])
    assert dlc.summary.text() == "1 dosya · hepsi bulundu"


def test_dlc_grid_falls_to_single_column_when_narrow(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    page.set_sources(_full(tmp_path))
    qtbot.waitUntil(lambda: page.dlc_card.grid.columns() == 2)
    page.resize(420, 800)
    qtbot.waitUntil(lambda: page.dlc_card.grid.columns() == 1)
    assert page.dlc_card.grid.width() <= 420


def test_remove_and_relink_actions_use_index_in_full_list(qtbot: QtBot, tmp_path: Path) -> None:
    """Kaldır eylemi listedeki gerçek sırayı taşır (DLC kutucuğunun ızgaradaki yeri değil)."""
    page = _page(qtbot)
    page.set_sources(_full(tmp_path))
    menu = page.game_card.manage.menu()
    assert menu is not None
    texts = [a.text() for a in menu.actions() if a.text()]
    assert texts == [
        "Kaldır: Ana oyun — Deneme Oyunu.nsp",
        "Kaldır: Güncelleme — Deneme Oyunu.nsp",
        "Kaldır: DLC — Ek Paket A.nsp",
        "Kaldır: DLC — Ek Paket B.nsp",
        RELINK_ACTION,
    ]
    remove_actions = [a for a in menu.actions() if a.text().startswith("Kaldır")]
    with qtbot.waitSignal(page.remove_source) as sig:
        remove_actions[3].trigger()
    assert sig.args == [3]
    with qtbot.waitSignal(page.remove_source) as sig:
        remove_actions[0].trigger()
    assert sig.args == [0]
    relink = next(a for a in menu.actions() if a.text() == RELINK_ACTION)
    with qtbot.waitSignal(page.relink_requested):
        relink.trigger()


def test_add_button_follows_keys_and_busy(qtbot: QtBot) -> None:
    page = _page(qtbot)
    assert page.add_button.isEnabled()
    page.set_keys_state("danger", None)
    assert not page.add_button.isEnabled()
    assert not page.drop.isEnabled()
    page.set_keys_state("success", Path("prod.keys"))
    assert page.add_button.isEnabled()
    page.set_busy(True, "okunuyor")
    assert not page.add_button.isEnabled()
    page.set_busy(False)
    assert page.add_button.isEnabled()
    with qtbot.waitSignal(page.browse_files):
        page.add_button.click()


def test_all_game_labels_are_not_selectable_pills(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    page.set_sources(_full(tmp_path))
    pills = [lbl for lbl in page.game_card.findChildren(QLabel) if lbl.property("role") == "pill"]
    assert pills
    assert all(lbl.contextMenuPolicy().name == "CustomContextMenu" for lbl in page.game_card.pills()[:2])


# --- eski projede simge doldurma -------------------------------------------------------------


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.show()
    yield w
    if w.scanning.meta_task is not None:
        w.scanning.meta_task.wait()
    if w.task is not None:
        w.task.cancel()
        w.task.wait()
    w.dirty = False
    w.close()
    w.deleteLater()


def _game_with_icon(tmp_path: Path) -> tuple[Path, Path, bytes]:
    keys = nxbuild.TestKeys.random()
    keys_path = keys.write(tmp_path / "prod.keys")
    icon = _jpeg("#cc3366")
    built = nxbuild.build_package(
        keys,
        kind="base",
        title_id=0x0100000000010000,
        application_id=0x0100000000010000,
        version=0,
        romfs_files={"Data/a.txt": b"x"},
        control_extra={"icon_AmericanEnglish.dat": icon},
    )
    nsp = tmp_path / "oyun.nsp"
    nsp.write_bytes(built.nsp)
    return keys_path, nsp, icon


def test_adding_a_game_caches_icon_and_publisher_in_project(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    keys_path, nsp, icon = _game_with_icon(tmp_path)
    assert window.load_keys_file(keys_path)
    window.add_files([nsp])
    _wait_idle(qtbot, window)
    (source,) = window.project.sources()
    assert (source.icon, source.publisher) == (icon, "Test Yayıncı")
    assert window.add_page.game_card.cover.has_image()


def test_old_project_gets_icon_in_background_without_dirty_or_busy(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    keys_path, nsp, icon = _game_with_icon(tmp_path)
    assert window.load_keys_file(keys_path)
    window.add_files([nsp])
    _wait_idle(qtbot, window)
    target = tmp_path / "eski.nxproj"
    assert window.save_to(target)
    window.project.set_sources([replace(s, icon=b"", publisher="") for s in window.project.sources()])  # eski proje
    window.new_project()
    assert window.open_project(target)
    assert not window.busy  # arka plan işi kullanıcı eylemlerini kilitlemez
    qtbot.waitUntil(window.add_page.game_card.cover.has_image, timeout=10000)
    assert not window.dirty
    assert window.sources[0].icon == icon
    assert window.project.sources()[0].icon == icon  # projeye yazıldı: bir dahaki açılışta dosya okunmaz
    window.scanning.meta_task and window.scanning.meta_task.wait()
    reopened = Project.open(target)
    assert reopened.sources()[0].icon == icon
    reopened.close()


def test_dlc_tile_shows_readable_name_with_full_file_name_in_tooltip(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    long_name = "Deneme Oyunu - Standard Edition [Tehlike Destesi][0100ABCD00005004][USA][v0]"
    page.set_sources([_source(tmp_path, "base", "Deneme Oyunu"), _source(tmp_path, "dlc", long_name)])
    (tile,) = page.dlc_card.tiles
    assert tile.name.full_text() == "Tehlike Destesi"
    assert long_name in tile.name.toolTip()


def test_header_title_never_clipped_in_narrow_page(qtbot: QtBot) -> None:
    """Dar pencerede başlık kesilmez: yer yetmeyen durum çipi gizlenir (neden düğme ipucunda kalır)."""
    page = AddGamePage()
    qtbot.addWidget(page)
    page.resize(500, 600)
    page.show()
    page.set_can_continue(False, "Anahtar dosyası seçin")
    qtbot.waitUntil(lambda: page.header.title.width() >= page.header.title.sizeHint().width())
    assert page.header.chip.isHidden()
    assert "Anahtar dosyası seçin" in page.next_button.toolTip()
    page.resize(1300, 600)
    qtbot.waitUntil(lambda: not page.header.chip.isHidden())
    assert page.header.title.width() >= page.header.title.sizeHint().width()
