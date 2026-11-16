"""Yinele (Ctrl+Y): geri alınan işlemi aynen geri getirir; yeni yazım yinele listesini boşaltır."""

from __future__ import annotations

from collections.abc import Callable

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import JOB_MANUAL, JOB_REVERT, JOB_UNAPPROVE, ImportedFile, Project, TranslationRow
from nxceviri.core.project.store import UNDO_LIMIT
from nxceviri.core.translate.status import Status
from tests.perf import best_time

LB = ControlCode(b"\n", "Satır sonu")

State = tuple[str, str, str]


def _project() -> Project:
    p = Project.new()
    entries = (
        TextEntry("a", 0, 'Hello, "friend"!', ()),
        TextEntry("b", 1, "We could make⟦1⟧the goal.", (LB,)),
        TextEntry("c", 2, "Not me.", ()),
    )
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    rows = _rows(p)
    p.set_translations([(rows["a"].id, 'Merhaba, "dostum"!'), (rows["b"].id, "Kale yaparız.⟦1⟧")], machine=True)
    p.set_translations([(rows["c"].id, "Ben değil.")])  # onaylı
    return p


def _rows(p: Project) -> dict[str, TranslationRow]:
    return {r.key: r for r in p.translation_rows()}


def _state(p: Project, key: str) -> State:
    r = _rows(p)[key]
    return (r.translation, r.status, r.note)


def test_redo_restores_exact_state_of_single_edit() -> None:
    p = _project()
    b = _rows(p)["b"].id
    before = _state(p, "b")
    p.set_translations([(b, "Kale yaparız.")])  # yer tutucu eksik: durum "hatalı" + açıklama
    after = _state(p, "b")
    assert after[1] == Status.ERROR
    assert after[2]
    assert p.redo_job() is None
    for _ in range(3):  # geri al → yinele döngüsü her seferinde aynı iki durumu üretir
        assert p.undo() is not None
        assert _state(p, "b") == before
        assert p.redo_job() == JOB_MANUAL
        assert p.undo_job() == JOB_MANUAL  # onaylama adımı
        job, rows = p.redo() or ("", [])
        assert (job, [r.key for r in rows]) == (JOB_MANUAL, ["b"])
        assert _state(p, "b") == after


def test_multi_part_job_is_one_step_both_ways() -> None:
    p = _project()
    rows = _rows(p)
    before = {k: _state(p, k) for k in "abc"}
    p.set_translations([(rows["a"].id, "Bir")], machine=True, overwrite_approved=True, job="translate-1")
    p.set_translations([(rows["b"].id, "Eksik")], machine=True, job="translate-1")  # yer tutucu yok: hatalı
    p.set_translations([(rows["c"].id, "Üç")], status=Status.REDACTED, overwrite_approved=True, job="translate-1")
    after = {k: _state(p, k) for k in "abc"}
    assert len({after[k][1] for k in "abc"}) == 3  # üç farklı durum
    job, undone = p.undo() or ("", [])
    assert (job, sorted(r.key for r in undone)) == ("translate-1", ["a", "b", "c"])
    assert {k: _state(p, k) for k in "abc"} == before
    assert p.redo_job() == "translate-1"
    job, redone = p.redo() or ("", [])
    assert (job, sorted(r.key for r in redone)) == ("translate-1", ["a", "b", "c"])
    assert {k: _state(p, k) for k in "abc"} == after
    assert p.redo() is None  # tek adımdı
    assert p.undo_job() == "translate-1"  # yinelenen iş yeniden geri alınabilir


def test_new_write_empties_redo() -> None:
    p = _project()
    a = _rows(p)["a"].id
    p.set_translations([(a, "Bir")])
    p.undo()
    assert p.redo_job() == JOB_MANUAL
    p.set_translations([(a, "İki")])
    assert p.redo_job() is None
    assert p.redo() is None
    assert _state(p, "a")[0] == "İki"


def test_write_that_changes_nothing_keeps_redo() -> None:
    p = _project()
    a = _rows(p)["a"].id
    p.set_translations([(a, "Bir")])
    p.undo()
    p.set_translations([(a, _rows(p)["a"].translation)], machine=True)  # aynı metin, aynı durum: yazım yok
    assert p.redo_job() == JOB_MANUAL


def test_undo_twice_redo_twice_is_lifo() -> None:
    p = _project()
    a = _rows(p)["a"].id
    p.set_translations([(a, "Bir")])
    p.set_translations([(a, "İki")])
    p.undo()
    p.undo()
    assert _state(p, "a")[0] == 'Merhaba, "dostum"!'
    p.redo()
    assert _state(p, "a")[0] == "Bir"
    p.redo()
    assert _state(p, "a")[0] == "İki"
    assert p.redo() is None
    p.undo()
    assert _state(p, "a")[0] == "Bir"  # geri al yığını da sırasını korudu


def test_undo_does_not_empty_redo_and_redo_does_not_empty_undo() -> None:
    p = _project()
    a = _rows(p)["a"].id
    p.set_translations([(a, "Bir")])
    p.set_translations([(a, "İki")])
    p.undo()
    p.undo()
    p.redo()
    assert p.redo_job() == JOB_MANUAL  # ikincisi hâlâ duruyor
    assert p.undo_job() == JOB_MANUAL


def test_unapprove_and_revert_are_redoable() -> None:
    p = _project()
    rows = _rows(p)
    p.unapprove([rows["c"].id])
    assert _state(p, "c")[1] == Status.MACHINE
    p.undo()
    assert _state(p, "c")[1] == Status.APPROVED
    assert p.redo_job() == JOB_UNAPPROVE
    p.redo()
    assert _state(p, "c") == ("Ben değil.", Status.MACHINE, "")

    p.set_translations([(rows["a"].id, "Dört")], machine=True, job="revise-2")
    p.revert(p.job_changes("revise-2"))
    assert _state(p, "a")[0] == 'Merhaba, "dostum"!'
    p.undo()  # geri almayı geri al
    assert _state(p, "a")[0] == "Dört"
    assert p.redo_job() == JOB_REVERT
    p.redo()  # ... ve onu yinele: yeniden geri alınmış hâl
    assert _state(p, "a")[0] == 'Merhaba, "dostum"!'


def test_import_texts_empties_redo() -> None:
    p = _project()
    a = _rows(p)["a"].id
    p.set_translations([(a, "Bir")])
    p.undo()
    p.import_texts(
        [ImportedFile("Dialogue.tsv", "0100", "unity", "base", (TextEntry("a", 0, 'Hello, "friend"!', ()),))]
    )
    assert p.redo_job() is None
    assert p.redo() is None


def test_stack_is_bounded() -> None:
    p = _project()
    a = _rows(p)["a"].id
    for i in range(UNDO_LIMIT + 5):
        p.set_translations([(a, f"Sürüm {i}")])
    undone = 0
    while p.undo() is not None:
        undone += 1
    assert undone == UNDO_LIMIT
    redone = 0
    while p.redo() is not None:
        redone += 1
    assert redone == UNDO_LIMIT
    assert _state(p, "a")[0] == f"Sürüm {UNDO_LIMIT + 4}"
    assert p.redo() is None


def test_rows_removed_meanwhile_are_skipped_silently_like_undo() -> None:
    p = _project()
    rows = _rows(p)
    p.set_translations([(rows["a"].id, "Bir"), (rows["c"].id, "Üç")], overwrite_approved=True, job="j")
    p.undo()
    p._conn.execute("DELETE FROM text_entries WHERE id = ?", (rows["c"].id,))  # yeniden tarama benzeri
    job, redone = p.redo() or ("", [])
    assert (job, [r.key for r in redone]) == ("j", ["a"])
    assert p.undo_job() == "j"
    # geri alırken de aynı: satır kalktıysa atlanır
    p._conn.execute("DELETE FROM text_entries WHERE id = ?", (rows["a"].id,))
    job, undone = p.undo() or ("", [])
    assert (job, undone) == ("j", [])


def test_history_keeps_original_job_and_only_grows() -> None:
    p = _project()
    rows = _rows(p)
    a = rows["a"].id
    p.set_translations([(a, "Bir")], machine=True, overwrite_approved=True, job="revise-9")
    count = len(p.row_history(a))
    assert p.last_jobs()[a] == "revise-9"
    assert [c.entry_id for c in p.job_changes("revise-9")] == [a]

    p.undo()
    assert len(p.row_history(a)) == count + 1
    assert p.last_jobs()[a] == JOB_REVERT
    assert p.job_changes("revise-9") == []  # geri alınmış: "Son işte değişenler" boş

    p.redo()
    history = p.row_history(a)
    assert len(history) == count + 2  # geçmiş yalnızca artar
    assert [c.job for c in history[:2]] == ["revise-9", JOB_REVERT]  # yinele işin kendi adıyla yazılır
    assert (history[0].old_text, history[0].new_text) == ('Merhaba, "dostum"!', "Bir")
    assert p.last_jobs()[a] == "revise-9"  # durum sütunundaki iş işareti yineleyince geri gelir
    (change,) = p.job_changes("revise-9")
    assert (change.old_text, change.new_text) == ('Merhaba, "dostum"!', "Bir")  # "Önceki Çeviri" sütunu aynı

    for _ in range(3):  # döngü geçmişi yalnızca büyütür, işin değişikliği tek ve tutarlı kalır
        p.undo()
        p.redo()
    assert len(p.row_history(a)) == count + 8
    (change,) = p.job_changes("revise-9")
    assert (change.old_text, change.new_text) == ('Merhaba, "dostum"!', "Bir")


def test_status_only_step_writes_no_history() -> None:
    p = _project()
    c = _rows(p)["c"].id
    count = len(p.row_history(c))
    p.unapprove([c])
    p.undo()
    p.redo()
    assert len(p.row_history(c)) == count  # metin değişmedi: geçmişe yazılmaz (geri al ile aynı kural)


def test_translation_memory_is_untouched_by_undo_and_redo() -> None:
    p = _project()
    a = _rows(p)["a"]
    p.set_translations([(a.id, "Bir")])
    remembered = p.memory_lookup([a.source])
    size = p.memory_size()
    p.undo()
    assert (p.memory_lookup([a.source]), p.memory_size()) == (remembered, size)
    p.redo()
    assert (p.memory_lookup([a.source]), p.memory_size()) == (remembered, size)


def test_fifty_thousand_row_job_undo_and_redo_are_fast() -> None:
    n = 50_000
    entries = tuple(TextEntry(f"k{i}", i, f"Line {i}", ()) for i in range(n))

    def prepare() -> Callable[[], object]:
        p = Project.new()
        p.import_texts([ImportedFile("Big.tsv", "0100", "unity", "base", entries)])
        ids = [r.id for r in p.translation_rows()]
        p.set_translations([(i, f"Satır {i}") for i in ids], machine=True, job="translate-big")

        def undo_then_redo() -> None:
            assert p.undo() is not None
            assert p.redo() is not None

        return undo_then_redo

    # Ölçüm: geri al ≈ 2,4 sn + yinele ≈ 2,4 sn (50.000 satır); eşik bunun yaklaşık üç katı.
    assert best_time(prepare, under=15.0) < 15.0
