"""Yazım Denetimi penceresi: öneriler, tek önerili sözcüklerde ön doldurma, toplu düzeltme ve hızlı değiştirme."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import JOB_MANUAL, ImportedFile, Project, TranslationRow
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.spell import report
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.report import UnknownWordCache, WordUse
from nxceviri.core.spell.suggest import Suggestion
from nxceviri.core.spell.userdict import UserDictionary
from nxceviri.core.translate.status import Status
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.spell_window import SpellWindow
from tests.perf import best_time

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def confirm_yes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Toplu düzeltme onay penceresi: varsayılan "Evet"; sorulan metinler döndürülen listede."""
    asked: list[str] = []

    def question(_parent: object, _title: str, text: str, *_args: object) -> QMessageBox.StandardButton:
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", question)
    return asked


WORDS = [
    "buradasın",
    "şapkadır",
    "şırıl",
    "kitap",
    "oyun",
    "başlat",
    "kış",
    "kis",
    "yine",
    "güzel",
    "burada",
    "neredesin",
    "dün",
    "geldi",
]


def _bloom(words: list[str]) -> BloomFilter:
    return BloomFilter.build([*words, *(f"x{n}q" for n in range(5000))], error_rate=1e-9)


# --- Pencerenin kendisi (uydurma öneri kaynağıyla) --------------------------------------------------

HINTS = {
    "buradaşın": Suggestion(("buradasın",), True, 7),
    "şapkadir": Suggestion(("şapkadır",), True, 3),
    "kıs": Suggestion(("kis", "kış"), True, 3),
    "kitapp": Suggestion(("kitap",), False, 100),
    "zzz": Suggestion(),
}
USES = [WordUse(w, i + 1, (i + 1,)) for i, w in enumerate(HINTS)]


def _hint(word: str, edits: bool) -> Suggestion:
    found = HINTS[word]
    return found if edits or found.letters else Suggestion()


@pytest.fixture
def win(qtbot: QtBot) -> SpellWindow:
    w = SpellWindow(None)
    qtbot.addWidget(w)
    w.suggest_fn = _hint
    w.set_words(USES)
    w.show()
    return w


def _select(w: SpellWindow, word: str) -> None:
    w.table.clearSelection()
    for r in range(w.table.rowCount()):
        item = w.table.item(r, 0)
        if item is not None and item.text() == word:
            item.setSelected(True)


def _chips(w: SpellWindow) -> list[str]:
    return [b.text() for b in w.suggestion_buttons]


def _column(w: SpellWindow) -> dict[str, str]:
    return {w.table.item(r, 0).text(): w.table.item(r, 2).text() for r in range(w.table.rowCount())}  # type: ignore[union-attr]


def test_list_shows_letter_suggestions_at_a_glance(win: SpellWindow) -> None:
    assert win.table.horizontalHeaderItem(2).text() == "Öneri"  # type: ignore[union-attr]
    col = _column(win)
    assert col["buradaşın"] == "buradasın"
    assert col["kıs"] == "kis  +1"
    assert col["kitapp"] == ""  # tek düzenleme listede aranmaz, sözcük seçilince gelir
    assert col["zzz"] == ""


def test_selecting_word_lists_suggestions_and_edit_distance_joins_the_cell(win: SpellWindow) -> None:
    _select(win, "kitapp")
    assert _chips(win) == ["kitap"]
    assert _column(win)["kitapp"] == "kitap"
    assert win.replace_edit.text() == "kitap"  # tek öneri: kutu önceden dolar
    _select(win, "kıs")
    assert _chips(win) == ["kis", "kış"]
    assert win.replace_edit.text() == ""  # birden çok: kullanıcı seçer
    _select(win, "zzz")
    assert _chips(win) == []
    assert "öneri bulunamadı" in win.suggest_caption.text()


def test_clicking_a_suggestion_fills_the_box_and_replace_sends_it(win: SpellWindow, qtbot: QtBot) -> None:
    _select(win, "kıs")
    win.suggestion_buttons[1].click()
    assert win.replace_edit.text() == "kış"
    with qtbot.waitSignal(win.replace_requested) as sig:
        win.replace_button.click()
    assert sig.args == ["kıs", "kış"]


def test_refresh_keeps_what_the_user_typed(win: SpellWindow) -> None:
    _select(win, "buradaşın")
    win.replace_edit.setText("başka")
    win.set_words(USES)  # tazeleme (arka plan taraması bitti, satır değişti …)
    assert win.replace_edit.text() == "başka"


def test_fix_all_lists_only_single_letter_suggestions(win: SpellWindow, qtbot: QtBot) -> None:
    assert win.fix_all_pairs() == [("buradaşın", "buradasın"), ("şapkadir", "şapkadır")]
    assert "(2)" in win.fix_all_button.text()
    with qtbot.waitSignal(win.fix_all_requested) as sig:
        win.fix_all_button.click()
    assert sig.args == [[("buradaşın", "buradasın"), ("şapkadir", "şapkadır")]]


def test_fix_all_asks_first_and_does_nothing_when_declined(
    win: SpellWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, confirm_yes: list[str]
) -> None:
    win.fix_all_button.click()
    assert "2 sözcük" in confirm_yes[0]
    assert "buradaşın → buradasın" in confirm_yes[0]
    monkeypatch.setattr(QMessageBox, "question", lambda *_a: QMessageBox.StandardButton.No)
    with qtbot.assertNotEmitted(win.fix_all_requested):
        win.fix_all_button.click()


def test_fix_all_follows_the_search_filter_and_disables_when_empty(win: SpellWindow) -> None:
    win.search.setText("şapka")
    assert win.fix_all_pairs() == [("şapkadir", "şapkadır")]
    assert "(1)" in win.fix_all_button.text()
    win.search.setText("kitapp")
    assert win.fix_all_pairs() == []
    assert not win.fix_all_button.isEnabled()


def test_window_without_suggestion_source_still_works(qtbot: QtBot) -> None:
    w = SpellWindow(None)
    qtbot.addWidget(w)
    w.set_words(USES)
    _select(w, "buradaşın")
    assert _chips(w) == []
    assert not w.fix_all_button.isEnabled()


# --- Ana pencere ------------------------------------------------------------------------------------


def _project(filler: int = 0) -> Project:
    p = Project.new()
    entries = [
        TextEntry("a", 0, "Where are you", ()),
        TextEntry("b", 1, "Hat", ()),
        TextEntry("c", 2, "Where", ()),
        TextEntry("d", 3, "Hat is here", ()),
        TextEntry("e", 4, "Stream", ()),
        TextEntry("f", 5, "Where", ()),
        *(TextEntry(f"k{i}", 10 + i, f"Line {i}", ()) for i in range(filler)),
    ]
    p.import_texts([ImportedFile("Menu.tsv", "0100", "unity", "base", tuple(entries))])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [
            (rows["a"].id, "Neredesin buradaşın"),
            (rows["b"].id, "Şapkadir"),
            (rows["d"].id, "Şapkadir burada"),
            (rows["e"].id, "Şiril şiril"),
            (rows["f"].id, "buradaşın"),
            *((rows[f"k{i}"].id, "Oyun yine güzel") for i in range(filler)),
        ],
        machine=True,
    )
    p.set_translations([(rows["c"].id, "Kitapp buradaşın")], status=Status.APPROVED)
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w.user_dictionary = UserDictionary(tmp_path / "yazim.txt")
    w.spell = SpellChecker(_bloom(WORDS))
    w._replace_project(_project())
    w.show()
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _open(window: MainWindow) -> SpellWindow:
    window.open_spell_window()
    win = window._spell_window
    assert win is not None
    return win


def _translations(window: MainWindow) -> dict[str, str]:
    return {r.key: r.translation for r in window.project.translation_rows()}


def test_window_gets_suggestions_from_the_app_dictionary(window: MainWindow) -> None:
    win = _open(window)
    assert _column(win) == {"buradaşın": "buradasın", "şapkadir": "şapkadır", "şiril": "şırıl", "kitapp": ""}
    _select(win, "kitapp")
    assert _chips(win) == ["kitap"]
    assert win.replace_edit.text() == "kitap"


def test_replace_touches_only_rows_that_contain_the_word(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    win = _open(window)
    calls: list[str] = []
    original = report.replace_unknown

    def counting(translation: str, *args: object, **kwargs: object) -> str:
        calls.append(translation)
        return original(translation, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("nxceviri.gui.main_window.replace_unknown", counting)
    _select(win, "buradaşın")
    win.replace_edit.setText("buradasın")
    win.replace_button.click()
    assert len(calls) == 3  # a, c ve f; öteki satırlara bakılmaz
    after = _translations(window)
    assert after["a"] == "Neredesin buradasın"
    assert after["c"] == "Kitapp buradasın"
    assert after["b"] == "Şapkadir"


def test_fix_all_is_one_job_keeps_approved_and_undo_redo_work(window: MainWindow) -> None:
    win = _open(window)
    before = _translations(window)
    win.fix_all_button.click()
    after = _translations(window)
    assert after["a"] == "Neredesin buradasın"
    assert after["b"] == "Şapkadır"
    assert after["d"] == "Şapkadır burada"
    assert after["e"] == "Şırıl şırıl"
    assert after["c"] == "Kitapp buradasın"  # (b) sınıfı (kitapp) toplu düzeltmeye girmez
    status = {r.key: r.status for r in window.project.translation_rows()}
    assert status["c"] == Status.APPROVED  # onaylı satır onaylı kalır
    window.undo_last()  # tek adım hepsini geri alır
    assert _translations(window) == before
    window.redo_last()
    assert _translations(window) == after


def test_fix_all_leaves_unknown_words_with_two_candidates_alone(window: MainWindow) -> None:
    window.spell = SpellChecker(_bloom([*WORDS, "şapkadır", "sapkadır"]))
    window._sync_spell()
    win = _open(window)
    assert ("şapkadir", "şapkadır") not in win.fix_all_pairs()  # "sapkadır" da var: tek öneri değil
    win.fix_all_button.click()
    assert _translations(window)["b"] == "Şapkadir"


def test_replace_updates_the_issue_board_in_place_in_the_background(qtbot: QtBot, window: MainWindow) -> None:
    window.run_checks()
    page = window.qa_page
    assert any(i.kind == "spelling" and "şapkadir" in i.words for i in page.model.issues)
    win = _open(window)
    _select(win, "şapkadir")
    win.replace_button.click()  # öneriyle dolu kutu: "şapkadır"
    assert not window.busy  # arka plan işi uygulamayı "meşgul" yapmaz
    qtbot.waitUntil(lambda: window._board_task is None, timeout=30_000)
    assert not any(i.kind == "spelling" and "şapkadir" in i.words for i in page.model.issues)
    assert any(i.kind == "spelling" and "buradaşın" in i.words for i in page.model.issues)  # ötekilere dokunulmadı


def test_marks_refresh_for_changed_rows_matches_full_refresh(window: MainWindow) -> None:
    model = window.translate_page.model
    first, second = model.rows[0], model.rows[1]
    window.project.set_translations([(first.id, "x1"), (second.id, "x2")], machine=True, job="revise-1")
    window._refresh_marks()
    assert model.marks == {first.id: "redaksiyon", second.id: "redaksiyon"}
    window.project.set_translations([(first.id, "x3")], machine=True, job=JOB_MANUAL)  # işareti kaybeder
    window._refresh_marks([first.id])  # yalnızca değişen satır yenilenir
    partial = dict(model.marks)
    window._refresh_marks()  # bütün geçmişten yeniden kurulan işaretler aynı olmalı
    assert partial == dict(model.marks) == {second.id: "redaksiyon"}


def test_last_jobs_for_some_rows_only(window: MainWindow) -> None:
    win = _open(window)
    win.fix_all_button.click()
    everything = window.project.last_jobs()
    some = sorted(everything)[:2]
    assert window.project.last_jobs(some) == {k: everything[k] for k in some}
    assert window.project.last_jobs([]) == {}


def _name_project() -> Project:
    p = Project.new()
    entries = (
        TextEntry("a", 0, "Yesterday Hat came", ()),
        TextEntry("b", 1, "Hat came", ()),
        TextEntry("c", 2, "Hat", ()),
    )
    p.import_texts([ImportedFile("Menu.tsv", "0100", "unity", "base", entries)])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [(rows["a"].id, "Dün Şapkadir geldi"), (rows["b"].id, "şapkadir geldi"), (rows["c"].id, "Şapkadir")],
        machine=True,
    )
    return p


def test_proper_names_mid_sentence_get_no_suggestion_and_are_never_replaced(window: MainWindow) -> None:
    window._replace_project(_name_project())
    win = _open(window)
    assert _column(win) == {"şapkadir": "şapkadır"}  # "Dün Şapkadir geldi" özel ad sayılır: listelenmez
    win.fix_all_button.click()
    after = _translations(window)
    assert after["a"] == "Dün Şapkadir geldi"  # cümle ortasında büyük harfli: dokunulmadı
    assert after["b"] == "şapkadır geldi"
    assert after["c"] == "Şapkadır"  # cümle başındaki büyük harfli geçiş sıradan sözcük; harf büyüklüğü korunur


def test_board_recheck_is_redone_when_rows_change_meanwhile(qtbot: QtBot, window: MainWindow) -> None:
    window.run_checks()
    page = window.qa_page
    win = _open(window)
    _select(win, "şapkadir")
    win.replace_button.click()
    window.undo_last()  # arka plan denetimi bitmeden satırlar eski hâline döndü
    qtbot.waitUntil(lambda: window._board_task is None and not window._board_pending, timeout=30_000)
    assert any(i.kind == "spelling" and "şapkadir" in i.words for i in page.model.issues)  # eski sonuç uygulanmadı


# --- Hız ----------------------------------------------------------------------------------------------


def test_replace_in_35000_rows_does_not_scan_every_row(qtbot: QtBot, window: MainWindow) -> None:
    window._replace_project(_project(filler=35_000))
    win = _open(window)
    qtbot.waitUntil(lambda: window._spell_scan is None and win.table.rowCount() > 0, timeout=120_000)
    window._qa_count = (window.project, 0)  # Kontrol Et çalıştırılmış: yerinde yeniden denetim yolu da ölçülür

    def prepare() -> object:
        _select(win, "buradaşın")
        win.replace_edit.setText("buradasın")
        return win.replace_button.click

    spent = best_time(prepare, attempts=1)  # type: ignore[arg-type]
    assert spent < 0.5
    after = _translations(window)
    assert after["a"] == "Neredesin buradasın"
    assert after["k0"] == "Oyun yine güzel"
    tries: list[int] = []

    def prepare_fix() -> object:
        # Tek ölçüm arka plandaki denetim iş parçacığıyla yarıştığında (yavaş CI makinesi) sınırı aşabiliyor;
        # her yeni denemeden önce düzeltme geri alınır, en iyi süre sayılır (yapılan iş her denemede aynıdır).
        if tries:
            window.undo_last()
        tries.append(1)
        qtbot.waitUntil(lambda: window._board_task is None and win.fix_all_button.isEnabled(), timeout=30_000)
        return win.fix_all_button.click

    fix_time = best_time(prepare_fix, under=0.5, attempts=3)  # type: ignore[arg-type]  # şapkadir ve şiril
    assert fix_time < 0.5
    assert _translations(window)["b"] == "Şapkadır"


def test_cache_row_ids_in_one_pass() -> None:
    spell = SpellChecker(_bloom(WORDS))
    rows = [
        TranslationRow(1, "f", "a", "x", "buradaşın şapkadir", "machine", "", (), None, "g/a", "unity"),
        TranslationRow(2, "f", "b", "y", "şapkadir", "machine", "", (), None, "g/b", "unity"),
        TranslationRow(3, "f", "c", "z", "oyun", "machine", "", (), None, "g/c", "unity"),
    ]
    cache = UnknownWordCache()
    cache.store(cache.scan(rows, spell, frozenset()))
    assert cache.row_ids(["şapkadir", "buradaşın", "yok"]) == {"şapkadir": [1, 2], "buradaşın": [1], "yok": []}
