"""Kontrol Et → Denetle: denetim sürerken maskotlu bekleme, gerçek ilerleme, Durdur ve önceki duruma dönüş."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.progress import ProgressCallback
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.checks import QaIssue
from nxceviri.core.secrets import MemoryStore
from nxceviri.gui import main_window
from nxceviri.gui.main_window import STEP_QA, MainWindow
from nxceviri.gui.mascot import mascot_enabled, set_mascot_enabled
from nxceviri.gui.qa_page import QaPage

pytestmark = pytest.mark.gui


@pytest.fixture
def mascot_on() -> Iterator[None]:
    before = mascot_enabled()
    set_mascot_enabled(True)
    yield
    set_mascot_enabled(before)


def _page_with_old_issues() -> tuple[QaPage, list[TranslationRow]]:
    rows = [
        TranslationRow(1, "f", "a", "Hello ", "Selam", "machine", "", (), None),
        TranslationRow(2, "f", "b", "Hi ", "Merhaba", "machine", "", (), None),
    ]
    page = QaPage()
    issues = [QaIssue(1, "a", "spaces", "warning", "Boşluk"), QaIssue(2, "b", "spaces", "warning", "Boşluk")]
    page.show_issues(issues, rows)
    return page, rows


def _texts(page: QaPage) -> str:
    return " ".join(
        [page.summary.text(), page.waiting.title.text(), page.waiting.text.text(), page.check_button.text()]
    )


def test_waiting_replaces_the_empty_states_and_the_zero_count(qtbot: QtBot, mascot_on: None) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    page.mark_checking()
    assert page.checking
    assert page.waiting.isVisibleTo(page)
    assert not page.table.isVisibleTo(page)
    assert page.kind_list.waiting  # sol liste: boş durum yazısı çizilmez, sayılar "—" (denetim bitmeden sayı yok)
    assert not page.kind_list.isEnabled()
    assert "Henüz denetlenmedi" not in _texts(page)
    assert page.check_button.text() == "Durdur"


def test_progress_is_real_and_shows_percent_and_detail(qtbot: QtBot, mascot_on: None) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    page.mark_checking()
    assert page.waiting.bar.maximum() == 0  # toplam henüz bilinmiyor: belirsiz kayar
    page.update_check_progress(250, 1000, "1.000 satır denetleniyor")
    assert page.waiting.bar.maximum() == 1000
    assert page.waiting.bar.value() == 250
    assert "%25" in page.waiting.title.text()
    assert page.waiting.text.text() == "1.000 satır denetleniyor"
    page.update_check_progress(900, 1000, "1.000 satır denetleniyor")
    assert page.waiting.bar.value() == 900
    assert "%90" in page.waiting.title.text()


def test_progress_is_ignored_when_not_checking(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    page.update_check_progress(5, 10, "x")
    assert not page.checking
    assert not page.waiting.isVisibleTo(page)


def test_works_with_the_mascot_turned_off(qtbot: QtBot) -> None:
    before = mascot_enabled()
    set_mascot_enabled(False)
    try:
        page = QaPage()
        qtbot.addWidget(page)
        page.show()
        page.mark_checking()
        page.update_check_progress(1, 4, "4 satır denetleniyor")
        assert page.waiting.isVisibleTo(page)
        assert not page.waiting.mascot.isVisible()  # maskotsuz yalnızca yazı ve çubuk
        assert "%25" in page.waiting.title.text()
        assert page.waiting.bar.isVisibleTo(page)
    finally:
        set_mascot_enabled(before)


def test_stop_button_emits_stop_and_not_run(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    runs: list[str] = []
    page.run_checks.connect(lambda: runs.append("run"))
    page.stop_checks.connect(lambda: runs.append("stop"))
    page.check_button.click()
    page.mark_checking()
    page.check_button.click()
    assert runs == ["run", "stop"]


def test_stopping_restores_previous_findings(qtbot: QtBot) -> None:
    page, _rows = _page_with_old_issues()
    qtbot.addWidget(page)
    before = page.kind_list.count_of("spaces")
    page.mark_checking()
    page.stop_checking()
    assert not page.checking
    assert page.summary.text() == "Denetim durduruldu."
    assert page.table.isVisibleTo(page)
    assert not page.waiting.isVisibleTo(page)
    assert not page.kind_list.waiting
    assert page.kind_list.count_of("spaces") == before == 2
    assert page.check_button.text() == "Yeniden Denetle"


def test_stopping_without_previous_findings_returns_to_the_empty_state(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    page.mark_checking()
    page.stop_checking()
    assert page.table.empty_text.startswith("Denetle")
    assert page.check_button.text() == "Denetle"
    assert page.summary.text() == "Denetim durduruldu."


def test_results_end_the_waiting_view(qtbot: QtBot) -> None:
    page, rows = _page_with_old_issues()
    qtbot.addWidget(page)
    page.mark_checking()
    page.show_issues([], rows)
    assert not page.checking
    assert page.table.isVisibleTo(page)
    assert page.summary.text() == "Sorun bulunmadı."


def test_failed_check_ends_the_waiting_view(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    page.mark_checking()
    page.show_check_failed("Bir sorun oluştu.")
    assert not page.checking
    assert not page.waiting.isVisibleTo(page)


# --- ana pencere ------------------------------------------------------------------------------------


def _project(count: int) -> Project:
    p = Project.new()
    entries = tuple(TextEntry(f"k{i}", i, f"Line {i} ", ()) for i in range(count))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    p.set_translations([(r.id, f"Satır {r.id}") for r in p.translation_rows()])
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[Callable[[Project], MainWindow]]:
    made: list[MainWindow] = []

    def make(project: Project) -> MainWindow:
        w = MainWindow(QSettings(str(tmp_path / f"ayarlar{len(made)}.ini"), QSettings.Format.IniFormat))
        w.secrets = MemoryStore()
        w._replace_project(project)
        w.show()
        w.nav.setCurrentRow(STEP_QA)
        made.append(w)
        return w

    yield make
    for w in made:
        w.dirty = False
        w.close()
        w.deleteLater()


def _slow_checks(monkeypatch: pytest.MonkeyPatch, gate: threading.Event, steps: int = 40) -> None:
    """Gerçek denetimin yerine her adımda ilerleme bildiren, `gate` açılana dek yarıda bekleyen uydurma denetim."""

    def fake(
        rows: list[TranslationRow], *_a: object, progress: ProgressCallback | None = None, **_k: object
    ) -> list[QaIssue]:
        for step in range(1, steps + 1):
            if step == steps // 2:
                gate.wait(10)
            if progress is not None:
                progress(step, steps, "")
        return []

    monkeypatch.setattr(main_window, "run_qa_checks", fake)


def test_check_shows_waiting_with_real_progress_then_results(
    window: Callable[[Project], MainWindow], qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()
    _slow_checks(monkeypatch, gate)
    w = window(_project(30))
    page = w.qa_page
    seen: list[tuple[int, int]] = []
    real = page.update_check_progress

    def spy(done: int, total: int, message: str) -> None:
        seen.append((done, total))
        real(done, total, message)

    monkeypatch.setattr(page, "update_check_progress", spy)
    page.check_button.click()
    assert w.busy
    assert page.checking
    assert page.check_button.isEnabled()
    assert page.check_button.text() == "Durdur"
    qtbot.waitUntil(lambda: bool(seen), timeout=5000)
    assert page.waiting.isVisibleTo(page)
    assert page.waiting.text.text() == "30 satır denetleniyor"
    gate.set()
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)
    assert [d for d, _t in seen] == sorted(d for d, _t in seen)
    assert seen[-1][0] == seen[-1][1] == 40
    assert not page.waiting.isVisibleTo(page)
    assert page.table.isVisibleTo(page)
    assert page.summary.text() == "Sorun bulunmadı."
    assert page.check_button.isEnabled()


def test_stop_cancels_the_check_and_restores_the_previous_state(
    window: Callable[[Project], MainWindow], qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()
    _slow_checks(monkeypatch, gate)
    w = window(_project(30))
    page = w.qa_page
    old = [QaIssue(r.id, r.key, "spaces", "warning", "Boşluk") for r in w.translate_page.model.rows[:3]]
    page.show_issues(old, list(w.translate_page.model.rows))
    seen: list[int] = []
    real = page.update_check_progress

    def spy(done: int, total: int, message: str) -> None:
        seen.append(done)
        real(done, total, message)

    monkeypatch.setattr(page, "update_check_progress", spy)
    page.check_button.click()
    qtbot.waitUntil(lambda: bool(seen), timeout=5000)
    qtbot.mouseClick(page.check_button, Qt.MouseButton.LeftButton)
    gate.set()
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)
    assert not page.checking
    assert page.summary.text() == "Denetim durduruldu."
    assert page.kind_list.count_of("spaces") == 3  # önceki bulgular geri geldi
    assert page.table.isVisibleTo(page)
    assert max(seen) < 40  # iptal edilince kalan adımlar çalışmadı
    assert page.check_button.isEnabled()
    assert page.check_button.text() == "Yeniden Denetle"


def test_fix_recheck_uses_the_same_waiting_view(
    window: Callable[[Project], MainWindow], qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()
    _slow_checks(monkeypatch, gate)
    w = window(_project(10))
    page = w.qa_page
    w.dirty = False
    w.qa_page.mark_checking()  # Düzelt sonrası arka plan denetimi bunu çağırır
    w._qa_count = (w.project, 0)
    w._recheck_if_done()
    assert w.busy
    assert page.checking
    assert page.waiting.isVisibleTo(page)
    assert page.check_button.text() == "Durdur"
    gate.set()
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)
    assert not page.waiting.isVisibleTo(page)
    assert page.table.isVisibleTo(page)
