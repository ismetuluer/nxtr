"""Kontrol Et → Düzelt: onaylı satırlar da düzelir ve onaylı kalır; bildirim gerçek planla aynı; hızlı yol."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa import checks
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.status import Status
from nxceviri.gui import main_window
from nxceviri.gui.main_window import STEP_QA, MainWindow
from tests.perf import best_time

pytestmark = pytest.mark.gui

LABELS = (ControlCode(b"\x01", "Renk"), ControlCode(b"\x02", "Renk sonu"))

#: (anahtar, orijinal, çeviri, "approved" | "machine")
ROWS = [
    ("sp_app", "Hello ", "Selam", "approved"),  # onaylı; sondaki boşluk eksik
    ("sp_mac", "Hi ", "Merhaba", "machine"),  # makine; sondaki boşluk eksik
    ("code_ok", "⟦1⟧Walk.⟦2⟧", "Yürü.", "approved"),  # kod zarfı eksik: güvenle onarılır
    ("code_no", "Use this ⟦1⟧walk⟦2⟧ over there.", "Şurada yürü.", "approved"),  # onarılamaz
]


def _entries() -> tuple[TextEntry, ...]:
    out = []
    for i, (key, source, _text, _state) in enumerate(ROWS):
        out.append(TextEntry(key, i, source, LABELS if "⟦" in source else ()))
    return tuple(out)


def _project() -> Project:
    p = Project.new()
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", _entries())])
    by_key = {r.key: r for r in p.translation_rows()}
    for key, _source, text, state in ROWS:
        p.set_translations([(by_key[key].id, text)], machine=state == "machine")
    return p


@pytest.fixture
def make_window(qtbot: QtBot, tmp_path: Path) -> Iterator[Callable[[Project], MainWindow]]:
    made: list[MainWindow] = []

    def make(project: Project) -> MainWindow:
        w = MainWindow(QSettings(str(tmp_path / f"ayarlar{len(made)}.ini"), QSettings.Format.IniFormat))
        w.secrets = MemoryStore()
        w._replace_project(project)
        w.show()
        w.nav.setCurrentRow(STEP_QA)
        w.qa_page.check_button.click()
        qtbot.waitUntil(lambda: not w.busy, timeout=20000)
        made.append(w)
        return w

    yield make
    for w in made:
        w.dirty = False
        w.close()
        w.deleteLater()


def _rows(w: MainWindow) -> dict[str, TranslationRow]:
    return {r.key: r for r in w.project.translation_rows()}


def _select_row(w: MainWindow, key: str) -> None:
    page = w.qa_page
    page.table.clearSelection()
    target = _rows(w)[key].id
    for r in range(page.proxy.rowCount()):
        if page.model.issues[page.proxy.mapToSource(page.proxy.index(r, 0)).row()].row_id == target:
            page.table.selectRow(r)
            return
    raise AssertionError(f"{key} için bulgu yok")


def _numbers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", text)]


def test_approved_row_is_fixed_and_stays_approved(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    assert _rows(w)["sp_app"].status == Status.APPROVED
    _select_row(w, "sp_app")
    w.qa_page.fix_button.click()
    row = _rows(w)["sp_app"]
    assert (row.translation, row.status) == ("Selam ", Status.APPROVED)
    assert w.qa_page.last_fix_text == "1 satır düzeltildi."
    # Tablodaki model de güncel (yeniden yükleme olmadan yerinde yenilenir).
    shown = {r.key: r for r in w.translate_page.model.rows}["sp_app"]
    assert (shown.translation, shown.status) == ("Selam ", Status.APPROVED)


def test_mixed_statuses_keep_their_status_in_one_undoable_redoable_job(
    make_window: Callable[[Project], MainWindow],
) -> None:
    w = make_window(_project())
    w.qa_page.kind_list.select_kinds(["spaces"])
    w.qa_page.fix_button.click()
    rows = _rows(w)
    assert (rows["sp_app"].translation, rows["sp_app"].status) == ("Selam ", Status.APPROVED)
    assert (rows["sp_mac"].translation, rows["sp_mac"].status) == ("Merhaba ", Status.MACHINE)
    assert w.qa_page.last_fix_text == "2 satır düzeltildi."
    # "Son işte değişenler" iki satırı da gösterir.
    assert w.project.job_changes(w._last_job or "") != []
    assert len(w.project.job_changes(w._last_job or "")) == 2

    w.undo_last()  # tek adım ikisini de geri alır
    rows = _rows(w)
    assert (rows["sp_app"].translation, rows["sp_mac"].translation) == ("Selam", "Merhaba")
    assert rows["sp_app"].status == Status.APPROVED
    w.redo_last()  # tek adım ikisini de geri getirir
    rows = _rows(w)
    assert (rows["sp_app"].translation, rows["sp_mac"].translation) == ("Selam ", "Merhaba ")
    assert (rows["sp_app"].status, rows["sp_mac"].status) == (Status.APPROVED, Status.MACHINE)


def test_code_fix_on_approved_row_follows_the_same_rule(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    assert _rows(w)["code_ok"].status == Status.ERROR  # kodu eksik satır "hatalı"dır
    w.qa_page.kind_list.select_kinds(["placeholder"])
    w.qa_page.fix_button.click()
    row = _rows(w)["code_ok"]
    assert row.translation == "⟦1⟧Yürü.⟦2⟧"
    assert row.status != Status.ERROR


def test_machine_write_never_touches_approved_rows(make_window: Callable[[Project], MainWindow]) -> None:
    """Düzelt'in onaylı satırlara yazması makine çevirisinin kuralını değiştirmez."""
    w = make_window(_project())
    row = _rows(w)["sp_app"]
    w.project.set_translations([(row.id, "Makine yazdı")], machine=True)
    after = _rows(w)["sp_app"]
    assert (after.translation, after.status) == ("Selam", Status.APPROVED)


def test_bar_count_is_the_number_of_rows_fix_changes(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    page = w.qa_page
    page.kind_list.select_kinds(["spaces"])
    announced = _numbers(page.fix_text.text())[0]
    assert page.fix_text.text() == "Bu 2 satır kendiliğinden düzeltilebilir."
    before = {k: r.translation for k, r in _rows(w).items()}
    page.fix_button.click()
    changed = sum(1 for k, r in _rows(w).items() if r.translation != before[k])
    assert announced == changed == _numbers(page.last_fix_text)[0]


def test_bar_does_not_promise_what_cannot_be_fixed(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    page = w.qa_page
    _select_row(w, "code_no")
    text = page.fix_text.text()
    assert "kendiliğinden düzeltilebilir" not in text
    assert "düzeltilemiyor" in text
    assert not page.fix_button.isVisibleTo(page.fix_bar)

    # Karışık kapsam: biri düzelir, biri düzelmez; bildirim ikisini de söyler, sonuç iletisi aynı sayıları verir.
    page.table.clearSelection()
    page.kind_list.select_kinds(["placeholder"])
    assert page.fix_text.text().startswith("Bu 1 satır kendiliğinden düzeltilebilir.")
    assert "1 satır düzeltilemez" in page.fix_text.text()
    assert page.fix_button.isVisibleTo(page.fix_bar)
    page.fix_button.click()
    assert _rows(w)["code_ok"].translation == "⟦1⟧Yürü.⟦2⟧"
    assert _rows(w)["code_no"].translation == "Şurada yürü."
    assert page.last_fix_text.startswith("1 satır düzeltildi.")
    assert "1 satır düzeltilemedi" in page.last_fix_text


def test_selected_fix_checks_only_the_selected_rows(
    make_window: Callable[[Project], MainWindow], monkeypatch: pytest.MonkeyPatch
) -> None:
    w = make_window(_project())
    seen: list[int] = []
    real = checks.check_row

    def counting(row: TranslationRow, *args: object, **kwargs: object) -> list[checks.QaIssue]:
        seen.append(row.id)
        return real(row, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(checks, "check_row", counting)
    _select_row(w, "sp_app")
    w.qa_page.fix_button.click()
    assert _rows(w)["sp_app"].translation == "Selam "
    assert set(seen) == {_rows(w)["sp_app"].id}  # yalnızca seçili satır denetlendi


def test_large_fix_runs_in_background_and_hides_the_stale_bar(
    make_window: Callable[[Project], MainWindow], qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_window, "FIX_SYNC_ROWS", 0)  # plan arka plan işinde
    monkeypatch.setattr(main_window, "FIX_RECHECK_ROWS", 0)  # yazımdan sonra tam denetim arka planda
    w = make_window(_project())
    page = w.qa_page
    bar_while_checking: list[bool] = []
    real_mark = page.mark_checking

    def mark_checking() -> None:
        real_mark()
        bar_while_checking.append(page.fix_bar.isVisibleTo(page))

    monkeypatch.setattr(page, "mark_checking", mark_checking)
    page.kind_list.select_kinds(["spaces"])
    page.fix_button.click()
    assert w.busy  # plan hazırlanıyor: arayüz donmaz, iş sürüyor
    qtbot.waitUntil(lambda: not w.busy, timeout=20000)
    # Yazımdan sonra tam denetim sürerken eski bulgu çubuğu görünmez (tıklayınca sessizce hiçbir şey olmazdı).
    # Durum işaretlendiği anda okunur: hızlı makinede denetim, test bakmadan bitebilir.
    assert bar_while_checking == [False]
    assert _rows(w)["sp_app"].translation == "Selam "
    assert page.kind_list.count_of("spaces") == 0
    assert _rows(w)["sp_mac"].translation == "Merhaba "


def test_fix_while_busy_says_so(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    w.task = object()  # type: ignore[assignment]  # sürmekte olan iş
    try:
        w.apply_fixes(["spaces"], [_rows(w)["sp_app"].id])
    finally:
        w.task = None
    assert "iş sürerken" in w.qa_page.last_fix_text
    assert _rows(w)["sp_app"].translation == "Selam"


def test_single_fix_in_35000_approved_rows_is_instant_and_skips_full_check(
    make_window: Callable[[Project], MainWindow], monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Project.new()
    entries = tuple(TextEntry(f"k{i}", i, f"Line number {i} ", ()) for i in range(35000))
    project.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    project.set_translations([(r.id, f"Satır numarası {r.id}") for r in project.translation_rows()])  # hepsi onaylı
    # 35.000 satırın tam denetimi bu testin konusu değil: pencere denetimsiz kurulur, panoya tek bulgu verilir.
    monkeypatch.setattr(MainWindow, "start_checks", lambda self: None)
    win = make_window(project)
    first = win.translate_page.model.rows[0]
    issues = checks.check_row(first, "", "")
    win.qa_page.show_issues(issues, [first])
    win._qa_count = (win.project, len(issues))
    win.qa_page.table.selectRow(0)
    assert [i.kind for i in win.qa_page.model.issues] == ["spaces"]

    seen: list[int] = []
    real = checks.check_row

    def counting(row: TranslationRow, *args: object, **kwargs: object) -> list[checks.QaIssue]:
        seen.append(row.id)
        return real(row, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(checks, "check_row", counting)
    elapsed = best_time(lambda: win.qa_page.fix_button.click, under=1.0, attempts=1)
    assert elapsed < 1.0
    assert set(seen) == {first.id}  # 35.000 satırın tam denetimi yapılmadı
    fixed = win.translate_page.model.rows[0]
    assert (fixed.translation, fixed.status) == (f"Satır numarası {first.id} ", Status.APPROVED)
