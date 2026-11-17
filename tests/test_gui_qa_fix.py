"""Arayüz: Kontrol Et → Satır denetimi düzeltmeleri (tür seçimi, kapsam, rapor, ayar kalıcılığı)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractButton
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.status import Status
from nxceviri.gui.main_window import STEP_QA, MainWindow

pytestmark = pytest.mark.gui

LINES = [
    ("a", "Start Game"),
    ("b", "Hello "),
    ("c", "Go on and on"),
    ("d", "Hello "),
]


def _project() -> Project:
    p = Project.new()
    entries = tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(LINES))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [(rows["a"].id, "Oyunu Başlat."), (rows["b"].id, "Merhaba"), (rows["c"].id, "Devam et ve ve bitir")],
        machine=True,
    )
    p.set_translations([(rows["d"].id, "Selam")])  # onaylı; sondaki boşluk eksik, Düzelt onaylıyı da düzeltir
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.show()
    w.nav.setCurrentRow(STEP_QA)
    w.qa_page.check_button.click()
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)  # Denetle arka planda çalışır
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _rows(w: MainWindow) -> dict[str, TranslationRow]:
    return {r.key: r for r in w.project.translation_rows()}


def _only(w: MainWindow, *kinds: str) -> None:
    """Soldaki listeden yalnızca bu türleri seçer (türü seçmek düzeltme isteğidir)."""
    w.qa_page.kind_list.select_kinds(kinds)


def _select_issue_row(w: MainWindow, key: str) -> None:
    page = w.qa_page
    page.table.clearSelection()
    target = _rows(w)[key].id
    for r in range(page.proxy.rowCount()):
        if page.model.issues[page.proxy.mapToSource(page.proxy.index(r, 0)).row()].row_id == target:
            page.table.selectRow(r)
            return
    raise AssertionError(f"{key} için bulgu yok")


def test_counts_and_bar_in_all_view(window: MainWindow) -> None:
    page = window.qa_page
    kl = page.kind_list
    assert (kl.count_of("spaces"), kl.count_of("end_punctuation"), kl.count_of("repeated_word")) == (2, 1, 1)
    # "Tüm bulgular": yalnızca güvenli türler (boşluk 2 + tekrarlı sözcük 1); sondaki noktalama riskli, sayılmaz.
    # Düzelt onaylı satırlarda da çalışır: b, c ve onaylı d satırı, yani 3 satır.
    assert page.fix_text.text() == "3 satır güvenle düzeltilebilir."
    assert page.fix_button.text() == "3 satırı düzelt"


def test_fix_selected_kinds_report_and_second_round(window: MainWindow) -> None:
    page = window.qa_page
    _only(window, "end_punctuation")
    page.fix_button.click()
    rows = _rows(window)
    assert rows["a"].translation == "Oyunu Başlat"
    assert rows["b"].translation == "Merhaba"  # seçilmeyen tür uygulanmadı
    assert rows["c"].translation == "Devam et ve ve bitir"
    assert page.last_fix_text == "1 satır düzeltildi."
    notice = window.notifier.history[0]  # sayfada kutu değil, bildirim
    assert notice.title == "1 satır düzeltildi"
    assert [a.label for a in notice.actions] == ["Raporu Gör"]
    assert page.kind_list.count_of("end_punctuation") == 0  # denetim kendiliğinden yeniden çalıştı
    assert page.kind_list.count_of("spaces") == 2

    notice.actions[0].callback()
    dialog = window.changes_dialog
    assert dialog is not None
    assert dialog.table.rowCount() == 1
    header, cell = dialog.table.horizontalHeaderItem(5), dialog.table.item(0, 5)
    assert header is not None
    assert cell is not None
    assert (header.text(), cell.text()) == ("Düzeltme", "Sondaki noktalama")
    dialog.close()

    # Başka bir türü seçip yeniden düzelt: onaylı satır da düzelir ve onaylı kalır.
    _only(window, "spaces")
    page.fix_button.click()
    rows = _rows(window)
    assert rows["b"].translation == "Merhaba "
    assert rows["d"].translation == "Selam "
    assert rows["d"].status == Status.APPROVED
    assert page.last_fix_text == "2 satır düzeltildi."


def test_fix_is_one_undoable_job(window: MainWindow) -> None:
    page = window.qa_page
    _only(window, "end_punctuation", "repeated_word")
    page.fix_button.click()
    rows = _rows(window)
    assert (rows["a"].translation, rows["c"].translation) == ("Oyunu Başlat", "Devam et ve bitir")
    window.undo_last()
    rows = _rows(window)
    assert (rows["a"].translation, rows["c"].translation) == ("Oyunu Başlat.", "Devam et ve ve bitir")


def test_selected_rows_scope(window: MainWindow) -> None:
    page = window.qa_page
    _select_issue_row(window, "c")
    assert page.fix_button.text() == "Seçili 1 satırı düzelt"
    page.fix_button.click()
    rows = _rows(window)
    assert rows["c"].translation == "Devam et ve bitir"
    assert rows["a"].translation == "Oyunu Başlat."  # seçili olmayan satırlara dokunulmadı
    assert rows["b"].translation == "Merhaba"
    assert page.last_fix_text == "1 satır düzeltildi."


def test_ollama_fix_is_gone(window: MainWindow) -> None:
    page = window.qa_page
    texts = [b.text() for b in page.findChildren(QAbstractButton)]
    texts += [a.text() for a in page.findChildren(QAction)]
    texts += [a.text() for a in page.context_menu().actions()]
    assert not [t for t in texts if "Otomatik Düzelt" in t or "Ollama" in t or "Programla" in t]
    assert not hasattr(window, "auto_fix")
    assert not hasattr(window, "program_fix")
    assert [a.text() for a in page.context_menu().actions()] == ["Yazım sözlüğünü aç…", "", "Sırala"]


def test_risky_bulk_fix_asks_first(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    from nxceviri.gui import qa_page as qa_page_module

    asked: list[str] = []
    answer = [False]

    def ask(_parent: object, text: str) -> bool:
        asked.append(text)
        return answer[0]

    monkeypatch.setattr(qa_page_module, "ask_risky_fix", ask)
    page = window.qa_page
    page._fix_now(["end_punctuation"], [])  # türün bütün bulguları: toplu ve riskli
    assert len(asked) == 1
    assert "Sondaki noktalama" in asked[0]
    assert _rows(window)["a"].translation == "Oyunu Başlat."  # vazgeçildi: dokunulmadı
    answer[0] = True
    page._fix_now(["end_punctuation"], [])
    assert _rows(window)["a"].translation == "Oyunu Başlat"
    asked.clear()
    page._fix_now(["repeated_word"], [])  # riskli olmayan tür: sorulmaz
    assert asked == []
    page._fix_now(["end_punctuation"], [_rows(window)["a"].id])  # tek satır: açık seçim yeter, sorulmaz
    assert asked == []
