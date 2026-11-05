"""Ortak bileşenler: "i" düğmesi yerine başlık ipucu, başlık ve düğme simgeleri, kısa sayfa metinleri."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QToolButton, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.gui import widgets
from nxceviri.gui.add_game_page import AddGamePage
from nxceviri.gui.export_page import ExportPage
from nxceviri.gui.qa_page import QaPage
from nxceviri.gui.scan_page import ScanPage
from nxceviri.gui.translate_page import TranslatePage
from nxceviri.gui.widgets import Card, button, title_row


def _labels(root: QWidget, role: str) -> list[QLabel]:
    return [lbl for lbl in root.findChildren(QLabel) if lbl.property("role") == role]


def test_no_info_button_class() -> None:
    assert not hasattr(widgets, "InfoButton")


def test_title_row_info_becomes_tooltip(qtbot: QtBot) -> None:
    box = title_row("Başlık", "Uzun açıklama metni")
    qtbot.addWidget(box)
    (title,) = _labels(box, "pageTitle")
    assert title.text() == "Başlık"
    assert "Uzun açıklama metni" in title.toolTip()
    assert not box.findChildren(QToolButton)


def test_title_row_icon(qtbot: QtBot) -> None:
    box = title_row("Çevir", icon="languages")
    qtbot.addWidget(box)
    icon_labels = [lbl for lbl in box.findChildren(QLabel) if lbl.objectName() == "titleIcon"]
    assert len(icon_labels) == 1
    pixmap = icon_labels[0].pixmap()
    assert pixmap is not None
    assert not pixmap.isNull()


def test_title_row_without_icon_has_no_icon_label(qtbot: QtBot) -> None:
    box = title_row("Başlık")
    qtbot.addWidget(box)
    assert not [lbl for lbl in box.findChildren(QLabel) if lbl.objectName() == "titleIcon"]


def test_card_hint_is_title_tooltip(qtbot: QtBot) -> None:
    card = Card("Kart", hint="uzun bilgi")
    qtbot.addWidget(card)
    assert "uzun bilgi" in card.title.toolTip()
    assert not card.findChildren(QToolButton)


def test_button_icon(qtbot: QtBot) -> None:
    with_icon = button("A", icon="search")
    without = button("B")
    qtbot.addWidget(with_icon)
    qtbot.addWidget(without)
    assert not with_icon.icon().isNull()
    assert without.icon().isNull()


@pytest.mark.parametrize("page_class", [AddGamePage, ScanPage, QaPage, ExportPage, TranslatePage])
def test_no_static_long_labels_in_pages(qtbot: QtBot, page_class: type[QWidget]) -> None:
    page = page_class()
    qtbot.addWidget(page)
    long_labels = [lbl.text() for lbl in _labels(page, "muted") if len(lbl.text()) > 80]
    assert long_labels == []


@pytest.mark.parametrize(
    ("page_class", "title", "icon_name"),
    [
        (AddGamePage, "Oyunu Ekle", "circle-plus"),
        (ScanPage, "Metinleri Tara", "scan-search"),
        (QaPage, "Kontrol Et", "shield-check"),
        (ExportPage, "Dışa Aktar", "package"),
    ],
)
def test_page_titles_are_unnumbered_with_icon(
    qtbot: QtBot, page_class: type[QWidget], title: str, icon_name: str
) -> None:
    page = page_class()
    qtbot.addWidget(page)
    (title_label,) = _labels(page, "pageTitle")
    assert title_label.text() == title
    assert [lbl for lbl in page.findChildren(QLabel) if lbl.objectName() == "titleIcon"]


def test_redundant_subtitle_labels_are_gone(qtbot: QtBot) -> None:
    gone = {
        "Anahtar dosyasını seçin, sonra oyun dosyalarını ekleyin.",
        "Oyundaki metin dosyalarını bulur.",
        "Çevirilerden oyuna kopyalanacak bir mod klasörü üretir.",
    }
    for page_class in (AddGamePage, ScanPage, ExportPage):
        page = page_class()
        qtbot.addWidget(page)
        assert gone.isdisjoint({lbl.text() for lbl in page.findChildren(QLabel)})
