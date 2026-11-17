"""Satırın hangi sağlayıcı/modelle çevrildiği: şema göçü, yazım yolları, Geri Al/Yinele ve geçmişten geri alma."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nxceviri.core.errors import ProjectError
from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.project import store as store_module
from nxceviri.core.translate.origin import MEMORY_ORIGIN, NO_ORIGIN, MachineOrigin, origin_label
from nxceviri.core.translate.runner import MachineJob, memory_filled_ids
from nxceviri.core.translate.status import Status

DEEPL = MachineOrigin("deepl")
OLLAMA = MachineOrigin("ollama", "gemma4:12b")
LINES = [("a", "Hello."), ("b", "Not me.")]


def _project() -> Project:
    p = Project.new()
    p.import_texts(
        [
            ImportedFile(
                "Dialogue.tsv", "0100", "unity", "base", tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(LINES))
            )
        ]
    )
    return p


def _rows(p: Project) -> dict[str, TranslationRow]:
    return {r.key: r for r in p.translation_rows()}


def _origin(r: TranslationRow) -> tuple[str, str]:
    return (r.mt_provider, r.mt_model)


def _v6_project(path: Path) -> None:
    """Sağlayıcı sütunları olmayan (şema 6) eski proje: elle kurulur, bir satırı çevrilmiş."""
    conn = sqlite3.connect(path)
    for i, script in enumerate(store_module.MIGRATIONS[:6], start=1):
        conn.executescript(f"{script}\nPRAGMA user_version = {i};")
    conn.execute(f"PRAGMA application_id = {store_module.APPLICATION_ID}")
    conn.execute("INSERT INTO project (id, created_at, updated_at, app_version) VALUES (1, 'x', 'x', '0.62.0')")
    conn.execute(
        "INSERT INTO text_files (id, path, title_id, format, origin, imported_at) "
        "VALUES (1, 'Dialogue.tsv', '0100', 'unity', 'base', 'x')"
    )
    conn.execute(
        "INSERT INTO text_entries (id, file_id, key, idx, source, codes, translation, status, updated_at) "
        "VALUES (1, 1, 'a', 0, 'Hello.', '[]', 'Merhaba.', 'machine', 'x')"
    )
    conn.execute(
        "INSERT INTO history (entry_id, old_text, old_status, old_note, new_text, job, created_at) "
        "VALUES (1, '', 'untranslated', '', 'Merhaba.', 'translate-1', 'x')"
    )
    conn.commit()
    conn.close()


def _columns(path: Path, table: str) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


def test_old_project_migrates_and_keeps_rows(tmp_path: Path) -> None:
    old = tmp_path / "eski.nxproj"
    _v6_project(old)
    project = Project.open(old)
    (row,) = project.translation_rows()
    assert (row.translation, row.status, _origin(row)) == ("Merhaba.", Status.MACHINE, ("", ""))  # bilinmiyor
    assert project.job_changes("translate-1")[0].new_text == "Merhaba."
    project.close()
    assert (tmp_path / "eski.nxproj.bak").exists()
    assert {"mt_provider", "mt_model"} <= set(_columns(old, "text_entries"))
    assert {"old_mt_provider", "old_mt_model"} <= set(_columns(old, "history"))


def test_interrupted_migration_leaves_project_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = tmp_path / "eski.nxproj"
    _v6_project(old)
    broken = (*store_module.MIGRATIONS[:6], store_module.MIGRATIONS[6] + "\nCREATE TABLE project (x);")
    with monkeypatch.context() as m:
        m.setattr(store_module, "MIGRATIONS", broken)
        with pytest.raises(ProjectError, match="güncellenemedi"):
            Project.open(old)
    conn = sqlite3.connect(old)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
    conn.close()
    assert "mt_provider" not in _columns(old, "text_entries")  # göçün yarısı da geri alındı
    assert (tmp_path / "eski.nxproj.bak").exists()
    project = Project.open(old)  # sonraki açılışta göç baştan ve eksiksiz yapılır
    assert project.translation_rows()[0].translation == "Merhaba."
    project.close()


def test_machine_translation_records_provider_and_model() -> None:
    p = _project()
    r = _rows(p)
    (row,) = p.set_translations([(r["a"].id, "Merhaba.")], machine=True, origin=OLLAMA, job="translate-1")
    assert _origin(row) == ("ollama", "gemma4:12b")
    (row,) = p.set_translations([(r["b"].id, "Ben değil.")], machine=True, origin=DEEPL, job="translate-2")
    assert _origin(row) == ("deepl", "")
    assert _origin(_rows(p)["a"]) == ("ollama", "gemma4:12b")  # öteki satıra dokunulmadı


def test_other_write_paths_keep_or_clear_origin_as_decided() -> None:
    p = _project()
    r = _rows(p)
    p.set_translations([(r["a"].id, "Merhaba."), (r["b"].id, "Ben değil.")], machine=True, origin=DEEPL)
    # Elle düzenleme, Bul-Değiştir, otomatik düzeltme, onay kaldırma: makine taslağının kaynağı kalır.
    (row,) = p.set_translations([(r["a"].id, "Selam.")])
    assert (row.status, _origin(row)) == (Status.APPROVED, ("deepl", ""))
    (row,) = p.set_translations([(r["b"].id, "Ben değilim.")], machine=True, job="autofix-1", remember=False)
    assert _origin(row) == ("deepl", "")
    (row,) = p.unapprove([r["a"].id])
    assert _origin(row) == ("deepl", "")
    # Dışarıdan gelen hazır çeviri metni baştan değiştirir: kaynak artık bilinmez.
    (row,) = p.set_translations([(r["b"].id, "Ben hariç.")], machine=True, origin=NO_ORIGIN, job="import")
    assert _origin(row) == ("", "")


def test_undo_and_redo_restore_origin() -> None:
    p = _project()
    r = _rows(p)
    p.set_translations([(r["a"].id, "Merhaba.")], machine=True, origin=DEEPL, job="translate-1")
    p.set_translations(
        [(r["a"].id, "Selamlar.")], machine=True, origin=OLLAMA, job="retranslate-1", overwrite_approved=True
    )
    assert _origin(_rows(p)["a"]) == ("ollama", "gemma4:12b")
    p.undo()
    assert (_rows(p)["a"].translation, _origin(_rows(p)["a"])) == ("Merhaba.", ("deepl", ""))
    p.redo()
    assert (_rows(p)["a"].translation, _origin(_rows(p)["a"])) == ("Selamlar.", ("ollama", "gemma4:12b"))


def test_same_text_from_new_provider_is_undoable() -> None:
    p = _project()
    r = _rows(p)
    p.set_translations([(r["a"].id, "Merhaba.")], machine=True, origin=DEEPL, job="translate-1")
    p.set_translations([(r["a"].id, "Merhaba.")], machine=True, origin=OLLAMA, job="retranslate-1")
    assert p.undo_job() == "retranslate-1"  # yalnızca kaynak değişti: yine de geri alınabilir bir adım
    p.undo()
    assert _origin(_rows(p)["a"]) == ("deepl", "")


def test_revert_from_history_restores_origin() -> None:
    p = _project()
    r = _rows(p)
    p.set_translations([(r["a"].id, "Merhaba.")], machine=True, origin=DEEPL, job="translate-1")
    p.set_translations([(r["a"].id, "Selamlar.")], machine=True, origin=OLLAMA, job="retranslate-1")
    (change,) = p.job_changes("retranslate-1")
    assert (change.old_mt_provider, change.old_mt_model) == ("deepl", "")
    (row,) = p.revert([change])
    assert (row.translation, _origin(row)) == ("Merhaba.", ("deepl", ""))


def test_origin_survives_save(tmp_path: Path) -> None:
    p = _project()
    r = _rows(p)
    p.set_translations([(r["a"].id, "Merhaba.")], machine=True, origin=OLLAMA)
    p.save_as(tmp_path / "proje.nxproj")
    p.close()
    reopened = Project.open(tmp_path / "proje.nxproj")
    assert _origin(_rows(reopened)["a"]) == ("ollama", "gemma4:12b")
    reopened.close()


def test_origin_label() -> None:
    assert origin_label("deepl", "") == "DeepL"
    assert origin_label("ollama", "gemma4:12b") == "Ollama (gemma4:12b)"
    assert origin_label("memory", "") == "Çeviri belleği"
    assert origin_label("", "") == ""
    assert origin_label("yeni", "") == "yeni"  # bilinmeyen sağlayıcı adıyla gösterilir
    assert MEMORY_ORIGIN.provider == "memory"


def test_memory_filled_ids_only_for_plain_translation() -> None:
    p = _project()
    rows = p.translation_rows()
    memory = {"Hello.": ("Merhaba.", "human")}
    job = MachineJob(rows=rows, source_lang="en", memory=memory)
    assert memory_filled_ids(job) == {r.id for r in rows if r.source == "Hello."}
    assert memory_filled_ids(MachineJob(rows=rows, source_lang="en", memory=memory, action="retranslate")) == set()
