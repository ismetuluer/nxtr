"""Çevir'deki "Hata veya uyarılı" süzgeci: büyük tabloda satırlar arka planda denetlenir (TECH_DEBT 85)."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.live import LiveChecker, LiveContext
from nxceviri.core.translate.status import Status
from nxceviri.gui import translate_page as translate_page_module
from nxceviri.gui.translate_page import ISSUES_FILTER, TranslatePage


def _row(i: int, translation: str) -> TranslationRow:
    return TranslationRow(i, "a.msbt", f"k{i}", f"Hello world {i}", translation, Status.MACHINE, "", (), None)


def _running(page: TranslatePage) -> bool:
    return page.precheck_task is not None


def _rows(n: int) -> list[TranslationRow]:
    # Tek numaralı satırlarda çift boşluk (uyarı), çiftlerde sorun yok.
    return [_row(i, f"Merhaba  dünya {i}" if i % 2 else f"Merhaba dünya {i}") for i in range(1, n + 1)]


def test_live_checker_precheck_job_fills_cache_for_current_context_only() -> None:
    live = LiveChecker()
    rows = _rows(6)
    live.set_rows(rows)
    assert live.pending(rows) == rows
    context, job = live.precheck_job(rows)
    results = job(lambda: None)
    live.store(context, results)
    assert live.pending(rows) == []
    assert [bool(live.cached(r)) for r in rows] == [True, False, True, False, True, False]

    # Bağlam bu arada değiştiyse sonuç eskidir: önbelleğe girmez.
    context, job = live.precheck_job(rows)
    results = job(lambda: None)
    live.set_context(LiveContext(kinds=frozenset({"spelling"})))
    live.store(context, results)
    assert live.pending(rows) == rows

    # Satır bu arada değiştiyse (düzenleme) yeni satırın sonucu eski sonuçla ezilmez.
    context, job = live.precheck_job(rows)
    results = job(lambda: None)
    edited = _row(1, "Merhaba dünya 1")
    live.check(edited)
    live.store(context, results)
    assert live.cached(edited) == []
    assert live.cached(rows[0]) is None  # eski satır nesnesinin sonucu yazılmadı


@pytest.mark.gui
def test_issues_filter_on_large_table_checks_in_background(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(translate_page_module, "ISSUES_PRECHECK_ROWS", 5)
    page = TranslatePage()
    qtbot.addWidget(page)
    page.set_rows(_rows(20))
    page.status_filter.set_current(ISSUES_FILTER)
    assert _running(page)  # büyük tablo: denetim arka planda
    assert "denetleniyor" in page.notice_text.lower()
    qtbot.waitUntil(lambda: page.precheck_task is None, timeout=10_000)
    assert page.proxy.rowCount() == 10  # süzgeç sonuç gelince uygulandı
    assert page.model.live.pending(page.model.rows) == []

    page.status_filter.set_current("")
    page.status_filter.set_current(ISSUES_FILTER)  # önbellek dolu: hemen süzülür
    assert not _running(page)
    assert page.proxy.rowCount() == 10


@pytest.mark.gui
def test_issues_filter_on_small_table_filters_at_once(qtbot: QtBot) -> None:
    page = TranslatePage()
    qtbot.addWidget(page)
    page.set_rows(_rows(20))
    page.status_filter.set_current(ISSUES_FILTER)
    assert not _running(page)
    assert page.proxy.rowCount() == 10
