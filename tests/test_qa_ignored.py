"""Yok sayılan bulgular: kayıt biçimi, ayırma, çeviri değişince geçersiz olma, hata bulgusunun yok sayılamaması."""

from __future__ import annotations

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa import ignored
from nxceviri.core.qa.checks import SEVERITY_ERROR, SEVERITY_WARNING, QaIssue
from nxceviri.core.translate.status import Status


def _row(row_id: int, translation: str) -> TranslationRow:
    return TranslationRow(row_id, "f", f"k{row_id}", "Source", translation, Status.MACHINE, "", (), None)


def _issue(row_id: int, kind: str = "ascii_turkish", severity: str = SEVERITY_WARNING) -> QaIssue:
    return QaIssue(row_id, f"k{row_id}", kind, severity, "ileti")


def test_round_trip_and_bad_setting() -> None:
    entries = {(1, "ascii_turkish", "abc"), (2, "spaces", "def")}
    assert ignored.load(ignored.dump(entries)) == entries
    assert ignored.load("") == set()
    assert ignored.load("{bozuk") == set()
    assert ignored.load('[[1, "a"]]') == set()  # eksik alan: hiçbir bulgu gizlenmez


def test_split_hides_only_matching_non_error_issues() -> None:
    rows = {1: _row(1, "bir"), 2: _row(2, "iki"), 3: _row(3, "üç")}
    entries = ignored.add(set(), [(1, "ascii_turkish"), (3, "placeholder")], rows)
    issues = [_issue(1), _issue(1, "spaces"), _issue(2), _issue(3, "placeholder", SEVERITY_ERROR)]
    shown, hidden = ignored.split(issues, rows, entries)
    assert [(i.row_id, i.kind) for i in hidden] == [(1, "ascii_turkish")]
    assert [(i.row_id, i.kind) for i in shown] == [(1, "spaces"), (2, "ascii_turkish"), (3, "placeholder")]


def test_error_issue_is_never_hidden_even_if_stored() -> None:
    rows = {3: _row(3, "üç")}
    entries = {(3, "placeholder", ignored.digest("üç"))}
    shown, hidden = ignored.split([_issue(3, "placeholder", SEVERITY_ERROR)], rows, entries)
    assert len(shown) == 1
    assert not hidden


def test_changed_translation_brings_the_issue_back() -> None:
    rows = {1: _row(1, "bir")}
    entries = ignored.add(set(), [(1, "ascii_turkish")], rows)
    assert ignored.split([_issue(1)], rows, entries)[1]
    changed = {1: _row(1, "bir!")}
    shown, hidden = ignored.split([_issue(1)], changed, entries)
    assert shown
    assert not hidden


def test_add_prunes_stale_entries_and_remove_clears_pairs() -> None:
    rows = {1: _row(1, "bir"), 2: _row(2, "iki")}
    entries = ignored.add(set(), [(1, "a"), (2, "b")], rows)
    rows[1] = _row(1, "değişti")
    entries = ignored.add(entries, [(2, "c")], rows)
    assert {(i, k) for i, k, _d in entries} == {(2, "b"), (2, "c")}  # satır 1'in eski kaydı atıldı
    assert {(i, k) for i, k, _d in ignored.remove(entries, [(2, "b")])} == {(2, "c")}
    assert ignored.add(set(), [(99, "a")], rows) == set()  # olmayan satır kaydedilmez
