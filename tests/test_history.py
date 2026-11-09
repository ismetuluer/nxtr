"""Çeviri geçmişi, işe göre değişiklikler, geri alma ve sözcük farkı."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import JOB_MANUAL, JOB_REVERT, ImportedFile, Project, TranslationRow
from nxceviri.core.project import store as store_module
from nxceviri.core.translate.diff import ADDED, REMOVED, SAME, word_diff
from nxceviri.core.translate.status import SOURCE_CHANGED_NOTE, Status

LINES = [("a", "Yes, but they like soccer."), ("b", "Not me."), ("c", "Press ⟦1⟧ now")]


@pytest.fixture
def project() -> Project:
    p = Project.new()
    entries = tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(LINES))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    return p


def _rows(p: Project) -> dict[str, TranslationRow]:
    return {r.key: r for r in p.translation_rows()}


def test_changes_are_recorded_per_job(project: Project) -> None:
    r = _rows(project)
    project.set_translations([(r["a"].id, "Evet, ama onlar futbolu seviyorlar."), (r["b"].id, "Ben değil.")])
    project.set_translations([(r["b"].id, "Ben değil.")])  # aynı metin: geçmişe yazılmaz
    project.set_translations([(r["a"].id, "Ama futbolu seviyorlar.")], machine=True, overwrite_approved=True, job="j1")
    project.set_translations([(r["a"].id, "Ama futbolu seviyorlar ki.")], machine=True, job="j1")
    project.set_translations([(r["b"].id, "Ben içmem.")], machine=True, overwrite_approved=True, job="j1")
    (a, b) = project.job_changes("j1")  # oyun sırasıyla
    assert (a.label, a.old_text, a.new_text, a.old_status) == (
        "a",
        "Evet, ama onlar futbolu seviyorlar.",
        "Ama futbolu seviyorlar ki.",  # işin içindeki ilk hâl → son hâl
        Status.APPROVED,
    )
    assert (b.old_text, b.new_text) == ("Ben değil.", "Ben içmem.")
    history = project.row_history(r["b"].id)
    assert [(c.job, c.old_text, c.new_text) for c in history] == [
        ("j1", "Ben değil.", "Ben içmem."),
        (JOB_MANUAL, "", "Ben değil."),
    ]
    assert project.job_changes("yok") == []


def test_revert_restores_text_status_and_note(project: Project) -> None:
    r = _rows(project)
    project.set_translations([(r["c"].id, "Şimdi ⟦1⟧ bas")])
    project._conn.execute(  # oyunda özgün metin değişmiş gibi: hatalı + açıklama
        "UPDATE text_entries SET status = ?, note = ? WHERE id = ?", (Status.ERROR, SOURCE_CHANGED_NOTE, r["c"].id)
    )
    project.set_translations([(r["c"].id, "⟦1⟧ tuşuna bas")], machine=True, job="j2")
    (change,) = project.job_changes("j2")
    rows = project.revert([change])
    assert (rows[0].translation, rows[0].status, rows[0].note) == ("Şimdi ⟦1⟧ bas", Status.ERROR, SOURCE_CHANGED_NOTE)
    assert project.job_changes("j2") == []  # geri alınan satır artık listelenmez
    assert project.row_history(r["c"].id)[0].job == JOB_REVERT  # geri alma da geçmişte (yeniden ileri alınabilir)
    assert project.revert([project.row_history(r["c"].id)[0]])[0].translation == "⟦1⟧ tuşuna bas"


def test_history_survives_save_and_old_projects_migrate(project: Project, tmp_path: Path) -> None:
    r = _rows(project)
    project.set_translations([(r["a"].id, "Bir")], machine=True)
    project.set_translations([(r["a"].id, "İki")], machine=True, job="j")
    project.save_as(tmp_path / "geçmiş.nxproj")
    project.close()
    reopened = Project.open(tmp_path / "geçmiş.nxproj")
    assert [c.new_text for c in reopened.job_changes("j")] == ["İki"]
    reopened.close()

    old = tmp_path / "eski.nxproj"
    conn = sqlite3.connect(old)
    for i, script in enumerate(store_module.MIGRATIONS[:4], start=1):
        conn.executescript(f"{script}\nPRAGMA user_version = {i};")
    conn.execute(f"PRAGMA application_id = {store_module.APPLICATION_ID}")
    conn.execute("INSERT INTO project (id, created_at, updated_at, app_version) VALUES (1, 'x', 'x', '0.27.0')")
    conn.commit()
    conn.close()
    migrated = Project.open(old)
    assert migrated._conn.execute("PRAGMA user_version").fetchone()[0] == store_module.SCHEMA_VERSION
    assert migrated.job_changes("j") == []
    migrated.close()


def test_word_diff() -> None:
    left, right = word_diff("Evet, ama onlar futbolu seviyorlar.", "Ama futbolu seviyorlar ki.")
    assert (REMOVED, "Evet, ama onlar") in left
    assert (ADDED, "Ama") in right
    assert (ADDED, " ki") in right
    assert "".join(t for _, t in left) == "Evet, ama onlar futbolu seviyorlar."
    assert "".join(t for _, t in right) == "Ama futbolu seviyorlar ki."
    same_left, same_right = word_diff("Aynı ⟦1⟧ metin", "Aynı ⟦1⟧ metin")
    assert {k for k, _ in same_left + same_right} == {SAME}
    left, right = word_diff("⟦1⟧ bas", "⟦2⟧ bas")
    assert (REMOVED, "⟦1⟧") in left  # yer tutucu tek parça


def test_last_jobs_and_labels(project: Project) -> None:
    from nxceviri.core.translate.report import job_label, mark_label

    r = _rows(project)
    project.set_translations([(r["a"].id, "Bir")], machine=True, job="translate-1")
    project.set_translations([(r["a"].id, "İki")], machine=True, job="revise-2026-10-25T09:30:00")
    project.set_translations([(r["b"].id, "Üç")], machine=True, job="retranslate-x")
    project.set_translations([(r["b"].id, "Dört")])  # elle: son iş elle
    assert project.last_jobs() == {r["a"].id: "revise-2026-10-25T09:30:00", r["b"].id: JOB_MANUAL}
    assert mark_label("revise-2026-10-25T09:30:00") == "redaksiyon"
    assert mark_label("autofix-x") == "otomatik düzeltme"
    assert mark_label("retranslate-x") == "yeniden çeviri"
    assert mark_label("translate-x") == mark_label(JOB_MANUAL) == mark_label(JOB_REVERT) == ""
    assert job_label(JOB_REVERT) == "Geri alma"
    assert job_label("revise-2026") == "Redaksiyon"
    assert job_label("bilinmeyen") == "bilinmeyen"


def test_changes_export_csv_and_html(project: Project, tmp_path: Path) -> None:
    from nxceviri.core.translate.report import ReportError, write_changes

    r = _rows(project)
    project.set_translations([(r["a"].id, 'Evet; ama "onlar" seviyor.')], machine=True)
    project.set_translations([(r["a"].id, "Ama seviyorlar ki.")], machine=True, job="revise-1")
    changes = project.job_changes("revise-1")
    write_changes(tmp_path / "rapor.csv", changes, "Talimatla düzeltme")
    raw = (tmp_path / "rapor.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # Excel UTF-8'i tanısın
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines[0] == "Satır;Orijinal;Önceki çeviri;Yeni çeviri;İş;Zaman"
    assert lines[1].startswith('a;Yes, but they like soccer.;"Evet; ama ""onlar"" seviyor.";Ama seviyorlar ki.;')
    write_changes(tmp_path / "rapor.html", changes, "Talimatla <düzeltme>")
    page = (tmp_path / "rapor.html").read_text(encoding="utf-8")
    assert "<del>" in page
    assert "<ins>Ama</ins>" in page
    assert "Talimatla &lt;düzeltme&gt;" in page
    with pytest.raises(ReportError, match="kaydedilemedi"):
        write_changes(tmp_path / "yok" / "rapor.csv", changes, "x")
