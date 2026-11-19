"""Kontrol Et pürüzleri: yok sayılan bulgu Çevir'de hemen kalkar, durdurulan denetim eskimiş bulguyu geri getirmez,
"Tüm bulgular" ipucu, dar pencerede bekleme ekranının hizası."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.progress import ProgressCallback
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.checks import QaIssue
from nxceviri.core.secrets import MemoryStore
from nxceviri.gui import checks_controller as main_window  # denetim işlevi burada değiştirilir
from nxceviri.gui.issue_kinds import ALL_TITLE, KindList
from nxceviri.gui.main_window import STEP_QA, MainWindow
from nxceviri.gui.widgets import BusyState

pytestmark = pytest.mark.gui


def _project() -> Project:
    p = Project.new()
    entries = tuple(TextEntry(f"k{i}", i, f"Line {i} ", ()) for i in range(4))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    for r in p.translation_rows():
        p.set_translations([(r.id, f"Satır {r.id}")])
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


def _board(w: MainWindow, kind: str, count: int = 3) -> list[TranslationRow]:
    """Panoya ilk `count` satır için `kind` uyarısı koyar ve Kontrol Et çalışmış sayılır."""
    rows = list(w.translate_page.model.rows)
    issues = [QaIssue(r.id, r.key, kind, "warning", "x") for r in rows[:count]]
    w.qa_page.show_issues(issues, rows)
    w.translate_page.set_qa_issues(issues, rows)
    w._qa_count = (w.project, count)
    return rows


# --- A: yok sayılan bulgu Çevir'de hemen kalkar ----------------------------------------------------------


def _kinds(w: MainWindow, row: TranslationRow, kind: str) -> list[str]:
    return [i.kind for i in w.translate_page.model.issues(row) if i.kind == kind]


def test_ignored_issue_leaves_translate_table_at_once_and_returns(window: Callable[[Project], MainWindow]) -> None:
    w = window(_project())
    rows = _board(w, "term")  # anlık denetimin bilmediği tür: Çevir son Kontrol Et sonucundan alır
    target = rows[0]
    assert _kinds(w, target, "term") == ["term"]
    w.ignore_issues([(target.id, "term")])
    assert _kinds(w, target, "term") == []
    assert _kinds(w, rows[1], "term") == ["term"]  # öteki satırlar etkilenmez
    w.unignore_issues([(target.id, "term")])
    assert _kinds(w, target, "term") == ["term"]


def test_ignore_filters_live_kinds_and_expires_with_the_translation(
    window: Callable[[Project], MainWindow],
) -> None:
    w = window(_project())
    model = w.translate_page.model
    rows = _board(w, "spaces")  # özgün sonda boşluklu, çeviri değil: anlık denetim de "spaces" üretir
    target = rows[0]
    assert _kinds(w, target, "spaces") == ["spaces"]
    w.ignore_issues([(target.id, "spaces")])
    assert _kinds(w, target, "spaces") == []
    assert not model.known_problem(target)
    w.project.set_translations([(target.id, "Başka")])
    model.update_rows([next(r for r in w.project.translation_rows() if r.id == target.id)])
    changed = model.rows[model.position(target.id) or 0]
    assert _kinds(w, changed, "spaces") == ["spaces"]  # çeviri değişince yok sayma geçersiz


# --- B: durdurulan denetim eskimiş bulguyu geri getirmez --------------------------------------------------


def test_stopped_check_drops_issues_of_rows_changed_since(
    window: Callable[[Project], MainWindow], qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()

    def fake(
        rows: list[TranslationRow], *_a: object, progress: ProgressCallback | None = None, **_k: object
    ) -> list[QaIssue]:
        for step in range(1, 41):
            if step == 20:
                gate.wait(10)
            if progress is not None:
                progress(step, 40, "")
        return []

    monkeypatch.setattr(main_window, "run_qa_checks", fake)
    w = window(_project())
    page = w.qa_page
    rows = _board(w, "spaces")
    first = rows[0]
    w.project.set_translations([(first.id, "Düzeltildi")])  # Düzelt/düzenleme: çeviri panodaki anlık görüntüden ayrıldı
    # Tablo değişikliği panoyu artık kendiliğinden yeniler; panonun eski kaldığı durumu (değişiklik denetim
    # sürerken gelir) kurmak için yenilemeyi çağıranın üstlendiği yol kullanılır.
    w.checks._update_rows_handled([next(r for r in w.project.translation_rows() if r.id == first.id)])
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
    left = {i.row_id for i in page.all_issues()}
    assert first.id not in left
    assert left == {rows[1].id, rows[2].id}
    assert page.kind_list.count_of("spaces") == 2
    assert page.summary.text() == "Denetim durduruldu; değişen 1 satır denetlenmedi. Denetle'ye basın."
    assert w._qa_count is not None
    assert w._qa_count[1] == 2


def test_stopped_check_without_changed_rows_keeps_plain_text(window: Callable[[Project], MainWindow]) -> None:
    w = window(_project())
    _board(w, "spaces")
    w.qa_page.mark_checking()
    w._on_check_cancelled()
    assert w.qa_page.summary.text() == "Denetim durduruldu."
    assert w.qa_page.kind_list.count_of("spaces") == 3


# --- C: "Tüm bulgular" ipucu -------------------------------------------------------------------------------


def test_all_item_explains_info_findings_only_when_present(qtbot: QtBot) -> None:
    kinds = KindList()
    qtbot.addWidget(kinds)
    kinds.set_counts({"spelling": 4, "spaces": 2}, {"spelling": "info", "spaces": "warning"}, 2, info=4)
    tip = kinds.all_item.toolTip()
    assert "yazım" in tip
    assert "soldan" in tip
    kinds.set_counts({"spaces": 2}, {"spaces": "warning"}, 2)
    assert kinds.all_item.toolTip() == ""
    assert kinds.all_item.text() == ALL_TITLE


# --- D: bekleme ekranı dar pencerede ortalı ---------------------------------------------------------------


@pytest.mark.parametrize("width", [260, 304, 360])
def test_busy_state_subtitle_is_centered_when_narrow(qtbot: QtBot, width: int) -> None:
    host = (
        QWidget()
    )  # düzensiz kapsayıcı: dar alanı düzen en az boyutuyla şişirmesin (gerçekte liste alanı böyle daralır)
    qtbot.addWidget(host)
    host.resize(width, 500)
    busy = BusyState("Denetleniyor…", "Denetim hazırlanıyor.")
    busy.setParent(host)
    busy.setGeometry(0, 0, width, 500)
    host.show()
    qtbot.waitExposed(host)
    busy.update_progress(10, 100, "12.000 satır denetleniyor ve her satır için birçok kural çalıştırılıyor")
    qtbot.wait(50)
    assert busy.width() == width
    center = busy.text.mapTo(busy, busy.text.rect().center()).x()
    assert abs(center - width / 2) <= 2
    assert busy.text.geometry().left() >= 0
    assert busy.text.geometry().right() <= width
