"""Kontrol Et: belirsiz Türkçe harf sözcüğü için sağ tık aday seçimi, bulguyu yok sayma, bildirim metinleri."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa import ignored
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.translate.status import Status
from nxceviri.gui.issue_kinds import IGNORED_KIND
from nxceviri.gui.main_window import STEP_QA, MainWindow

pytestmark = pytest.mark.gui

LABELS = (ControlCode(b"\x01", "Renk"), ControlCode(b"\x02", "Renk sonu"))
WORDS = ["sürat", "şurat", "burada", "gitti", "hızlı", "mermi", "ve", "yürü", "kitap"]
#: (anahtar, orijinal, çeviri, "approved" | "machine")
ROWS = [
    ("a", "Go", "surat burada", "machine"),  # belirsiz: sürat / şurat
    ("b", "Run", "Surat gitti ve surat", "approved"),  # aynı sözcük, onaylı
    ("c", "Walk", "suratlar burada", "machine"),  # başka sözcük: dokunulmaz
    ("d", "Shot", "mun-hizli mermi", "machine"),  # tireli: tek aday olan parça düzelir
    ("e", "⟦1⟧Walk.⟦2⟧", "Yürü.", "machine"),  # kontrol kodu eksik: hata, yok sayılamaz
    ("f", "Book ", "kitap", "machine"),  # boşluk uyarısı
]


def _project() -> Project:
    p = Project.new()
    entries = tuple(
        TextEntry(key, i, source, LABELS if "⟦" in source else ()) for i, (key, source, _t, _s) in enumerate(ROWS)
    )
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    by_key = {r.key: r for r in p.translation_rows()}
    for key, _source, text, state in ROWS:
        p.set_translations([(by_key[key].id, text)], machine=state == "machine")
        if state == "approved":
            p.set_translations([(by_key[key].id, text)], status=Status.APPROVED)
    return p


@pytest.fixture
def make_window(qtbot: QtBot, tmp_path: Path) -> Iterator[Callable[[Project], MainWindow]]:
    made: list[MainWindow] = []

    def make(project: Project) -> MainWindow:
        w = MainWindow(QSettings(str(tmp_path / f"ayarlar{len(made)}.ini"), QSettings.Format.IniFormat))
        w.secrets = MemoryStore()
        w.spell = SpellChecker(BloomFilter.build(WORDS, error_rate=0.00001))
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


def _select(w: MainWindow, key: str, kind: str) -> None:
    page = w.qa_page
    page.table.clearSelection()
    target = _rows(w)[key].id
    for r in range(page.proxy.rowCount()):
        issue = page.model.issues[page.proxy.mapToSource(page.proxy.index(r, 0)).row()]
        if issue.row_id == target and issue.kind == kind:
            page.table.selectRow(r)
            return
    raise AssertionError(f"{key} için {kind} bulgusu yok")


def _action(menu: QMenu, text: str) -> QAction:
    found = [a for a in menu.actions() if a.text() == text]
    assert found, [a.text() for a in menu.actions()]
    return found[0]


def _texts(menu: QMenu) -> list[str]:
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def _ascii_count(w: MainWindow) -> int:
    return sum(1 for i in w.qa_page.active_issues() if i.kind == "ascii_turkish")


def test_hyphenated_part_is_repaired_by_fix(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    _select(w, "d", "ascii_turkish")
    w.qa_page.fix_button.click()
    assert _rows(w)["d"].translation == "mun-hızlı mermi"  # "mun"un sözlükte adayı yok: olduğu gibi kalır


def test_menu_offers_candidates_and_applies_to_the_whole_project(
    make_window: Callable[[Project], MainWindow], qtbot: QtBot
) -> None:
    w = make_window(_project())
    _select(w, "a", "ascii_turkish")
    menu = w.qa_page.context_menu()
    submenu = _action(menu, "Şununla düzelt").menu()
    assert isinstance(submenu, QMenu)
    assert _texts(submenu) == ["surat → sürat", "surat → şurat"]
    before = _ascii_count(w)
    _action(submenu, "surat → sürat").trigger()
    rows = _rows(w)
    assert rows["a"].translation == "sürat burada"
    assert rows["b"].translation == "Sürat gitti ve sürat"
    assert rows["b"].status == Status.APPROVED  # onaylı satır onaylı kalır
    assert rows["c"].translation == "suratlar burada"  # tam sözcük değil
    qtbot.waitUntil(lambda: _ascii_count(w) < before)  # satırlar arka planda yeniden denetlenir
    w.undo_last()  # tek adım hepsini geri alır
    assert _rows(w)["a"].translation == "surat burada"
    assert _rows(w)["b"].translation == "Surat gitti ve surat"


def test_unfixable_finding_has_no_fix_actions_and_says_so(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    _select(w, "a", "ascii_turkish")
    texts = _texts(w.qa_page.context_menu())
    assert "Bu satırı düzelt" not in texts  # plan 0 satır düzeltecek
    assert not any(t.startswith("Tüm “Türkçe harf eksik”") and "(0 satır)" in t for t in texts)
    w.apply_fixes(["ascii_turkish"], [_rows(w)["a"].id])
    assert w.qa_page.last_fix_text.startswith("Kendiliğinden düzeltilemedi.")
    assert "anlam gerektiriyor" in w.qa_page.last_fix_text
    assert "bulunamadı" not in w.qa_page.last_fix_text


def test_kind_action_names_the_kind_and_counts_rows(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    _select(w, "d", "ascii_turkish")
    texts = _texts(w.qa_page.context_menu())
    assert "Tüm “Türkçe harf eksik” bulgularını düzelt (1 satır)" in texts


def test_ignore_hides_issue_persists_and_returns_when_translation_changes(
    make_window: Callable[[Project], MainWindow], qtbot: QtBot
) -> None:
    w = make_window(_project())
    page = w.qa_page
    _select(w, "f", "spaces")
    before = w._qa_count
    assert before is not None
    _action(page.context_menu(), "Bulguyu yok say").trigger()
    assert not any(i.row_id == _rows(w)["f"].id and i.kind == "spaces" for i in page.active_issues())
    assert w._qa_count is not None
    assert w._qa_count[1] == before[1] - 1
    assert IGNORED_KIND in page.kind_list.visible_kinds()

    # Yeniden denetim: yok sayma kalıcıdır.
    w.run_checks()
    assert not any(i.kind == "spaces" and i.row_id == _rows(w)["f"].id for i in page.active_issues())
    assert [i.kind for i in page.all_issues() if i.row_id == _rows(w)["f"].id and i.kind == "spaces"] == ["spaces"]

    # Yok sayılanlar görünümü ve geri alma.
    page.kind_list.select_kinds([IGNORED_KIND])
    assert [page.model.issues[r].kind for r in range(page.model.rowCount())] == ["spaces"]
    page.table.selectRow(0)
    menu = page.context_menu()
    assert "Bulguyu yok say" not in _texts(menu)
    assert not page.fix_bar.isVisibleTo(page)
    _action(menu, "Yok saymayı kaldır").trigger()
    assert any(i.kind == "spaces" for i in page.active_issues())
    assert IGNORED_KIND not in page.kind_list.visible_kinds()
    assert not page._ignored_view


def test_ignore_is_dropped_when_the_translation_changes(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    row = _rows(w)["f"]
    _select(w, "f", "spaces")
    _action(w.qa_page.context_menu(), "Bulguyu yok say").trigger()
    w.project.set_translations([(row.id, "kitap!")], machine=True)
    w.run_checks()
    assert any(i.row_id == row.id and i.kind == "spaces" for i in w.qa_page.active_issues())


def test_errors_cannot_be_ignored(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    _select(w, "e", "placeholder")
    assert "Bulguyu yok say" not in _texts(w.qa_page.context_menu())
    w.ignore_issues([(_rows(w)["e"].id, "placeholder")])  # doğrudan çağrılsa da hata gizlenmez
    assert any(i.kind == "placeholder" for i in w.qa_page.active_issues())


def test_ignored_setting_survives_reopening(make_window: Callable[[Project], MainWindow], tmp_path: Path) -> None:
    w = make_window(_project())
    _select(w, "f", "spaces")
    _action(w.qa_page.context_menu(), "Bulguyu yok say").trigger()
    saved = ignored.load(w.project.setting(ignored.IGNORED_KEY))
    assert len(saved) == 1
    path = tmp_path / "p.nxproj"
    w.project.save_as(path)
    reopened = Project.open(path)
    assert ignored.load(reopened.setting(ignored.IGNORED_KEY)) == saved
    reopened.close()


def test_board_recheck_in_ignored_view_keeps_both_lists(make_window: Callable[[Project], MainWindow]) -> None:
    w = make_window(_project())
    page = w.qa_page
    _select(w, "f", "spaces")
    _action(page.context_menu(), "Bulguyu yok say").trigger()
    active = len(page.active_issues())
    page.kind_list.select_kinds([IGNORED_KIND])
    assert page._ignored_view
    shown = {r.key: r for r in w.translate_page.model.rows}
    w._recheck_board_rows([shown["a"], shown["f"]])  # f'nin bulgusu yine yok sayılır, a'nınkiler gerçek listede kalır
    assert len(page.active_issues()) == active
    assert [i.kind for i in page.model.issues] == ["spaces"]
    page.kind_list.select_kinds([])
    assert len(page.model.issues) == active
