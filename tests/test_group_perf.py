"""Gruplu görünüm süre testleri: gerçek proje büyüklüğünde (35.000 satır / 625 grup; 26.000 satır / 2.408 grup,
ortanca grup 2 satır) aç/kapa, tek grubu katla/aç, arama tuşu ve kaydırma akıcı kalır.

Her ölçüm birkaç kez alınır ve en iyisi eşikle karşılaştırılır: yük altındaki makinede tek ölçüm yanlış alarm
verebilir, gerçek bir gerileme ise bütün tekrarları yavaşlatır.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.status import Status
from nxceviri.gui.translate_page import TranslatePage

pytestmark = pytest.mark.gui


def _rows_625() -> list[TranslationRow]:
    return [
        TranslationRow(
            i,
            f"Data/f{i % 625}.msbt",
            f"k{i}",
            f"Kaynak satır {i}",
            f"Çeviri {i}",
            Status.MACHINE,
            "",
            (),
            None,
            "",
            "msbt",
        )
        for i in range(1, 35_001)
    ]


def _rows_2408() -> list[TranslationRow]:
    """2.000 iki satırlık grup (ortanca 2) + 408 büyük grup: toplam 26.000 satır."""
    rows: list[TranslationRow] = []
    for i in range(1, 26_001):
        group = (i - 1) // 2 if i <= 4_000 else 2_000 + i % 408
        rows.append(
            TranslationRow(
                i,
                f"Data/g{group}.msbt",
                f"k{i}",
                f"Kaynak satır {i}",
                "",
                Status.UNTRANSLATED,
                "",
                (),
                None,
                "",
                "msbt",
            )
        )
    return rows


def _best(action: Callable[[], None], repeat: int = 3) -> float:
    costs = []
    for _ in range(repeat):
        start = time.perf_counter()
        action()
        costs.append(time.perf_counter() - start)
    return min(costs)


@pytest.mark.parametrize(("make", "groups"), [(_rows_625, 625), (_rows_2408, 2408)])
def test_grouped_view_stays_fast_on_real_sized_projects(
    qtbot: QtBot, make: Callable[[], list[TranslationRow]], groups: int
) -> None:
    page = TranslatePage()
    qtbot.addWidget(page)
    page.resize(1200, 800)
    page.show()
    page.set_rows(make())
    assert len(page._group_rank) == groups

    def toggle() -> None:
        page._set_grouped(True)
        page._set_grouped(False)

    toggle_cost = _best(toggle)
    page._set_grouped(True)
    name = page.group_proxy.header_group(0)
    assert name is not None

    def fold() -> None:
        page.group_proxy.set_collapsed(name, True)
        page.group_proxy.set_collapsed(name, False)

    fold_cost = _best(fold)

    def keystroke() -> None:
        page.search.setText("Kaynak satır 1")
        page._apply_search_now()
        page.search.setText("")

    key_cost = _best(keystroke)
    bar = page.table.verticalScrollBar()

    def scroll() -> None:
        for step in range(20):
            bar.setValue(bar.maximum() * step // 20)
            page._fit_rows()
            page.table.viewport().repaint()

    scroll_cost = _best(scroll)
    print(
        f"{groups} grup: aç+kapa {toggle_cost * 1000:.0f} ms, katla+aç {fold_cost * 1000:.0f} ms, "
        f"arama {key_cost * 1000:.0f} ms, 20 kaydırma {scroll_cost * 1000:.0f} ms"
    )
    assert toggle_cost < 0.5
    assert fold_cost < 0.3
    assert key_cost < 2.0
    assert scroll_cost < 4.0
