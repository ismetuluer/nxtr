"""Uydurma (halüsinasyon) belirtileri ve tutarlılık: yeni çevirilerin denetimi, şüpheli ve tutarsız satır uyarıları."""

from __future__ import annotations

import pytest

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_WARNING, check_row, run_checks
from nxceviri.core.translate import runner as runner_module
from nxceviri.core.translate.guards import translation_problems
from nxceviri.core.translate.runner import ACTION_TRANSLATE, MachineJob, RunSummary, run_machine_translation
from nxceviri.core.translate.status import Status
from nxceviri.gui.jobs import describe_summary
from tests.fake_ollama import FakeOllama


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "RETRY_DELAYS_S", (0.0, 0.0))


def _problems(source: str, new: str) -> list[str]:
    return translation_problems(source, new, "tr")


@pytest.mark.parametrize(
    ("source", "new", "expected"),
    [
        ("You're crazy!", "You're crazy! Don't you think it's a bit risky?", "İngilizce"),
        ("Hello there, friend.", "Merhaba 朋友, nasılsın?", "alfabe"),
        ("Привет is Russian for hi.", "Привет, Rusçada selam demek; 你好 ise Çince.", "你"),
        ("Treat that ball like our kid.", "Topa türlü türlü davran, türlü türlü sev, türlü türlü", "tekrar"),
        ("Yes, of course.", "Evet, elbette; ama önce kapıyı aç, sonra ışıkları kapat ve beni bekle.", "uzun"),
        ("I told you we should treat that ball like it's our own kid.", "Evet.", "kısa"),
    ],
)
def test_fresh_translation_symptoms_are_caught(source: str, new: str, expected: str) -> None:
    problems = _problems(source, new)
    assert problems
    assert any(expected in p for p in problems), problems


@pytest.mark.parametrize(
    ("source", "new"),
    [
        ("Hello ⟦1⟧Link⟦2⟧!", "Merhaba ⟦1⟧Link⟦2⟧!"),
        ("Oh, that's really nice of you!", "Ne kadar naziksin!"),
        ("OK", "Tamam"),
        ("Pokémon Center", "Pokémon Merkezi"),  # Latin harfi, Türkçede olmasa da kaynakta var
        ("「勇者」の剣", "「Kahraman」 kılıcı"),  # kaynaktaki yazı işaretleri çeviride kalabilir
    ],
)
def test_normal_fresh_translations_pass(source: str, new: str) -> None:
    assert _problems(source, new) == []


def _project(*sources: str) -> Project:
    project = Project.new()
    entries = tuple(TextEntry(f"s{i:02}", i, s, ()) for i, s in enumerate(sources))
    project.import_texts([ImportedFile("D.tsv", "0100", "unity", "base", entries)])
    return project


def _job(project: Project) -> MachineJob:
    rows = project.translation_rows()
    return MachineJob(rows=rows, source_lang="en", all_rows=rows)


def test_suspicious_fresh_translation_is_retried_then_written() -> None:
    project = _project("You're crazy!")
    server = FakeOllama(translate=lambda text: "You're crazy! Don't you think it's a bit risky?")
    written: list[tuple[int, str]] = []
    summary = run_machine_translation(server.provider(), _job(project), TaskContext(), written.extend)
    # Kodları sağlam olduğu için satır boş kalmaz; şüpheli olarak yazılır, Kontrol Et'te ve tabloda görünür.
    assert [t for _, t in written] == ["You're crazy! Don't you think it's a bit risky?"]
    assert (summary.retried, summary.suspicious, summary.translated, summary.broken) == (1, 1, 1, 0)
    assert "İngilizce" in server.requests[-1]["messages"][1]["content"]


def test_suspicious_fresh_translation_fixed_on_retry() -> None:
    project = _project("You're crazy!")
    answers = iter(["You're crazy!", "Deli misin sen?"])
    server = FakeOllama(translate=lambda text: next(answers))
    written: list[tuple[int, str]] = []
    summary = run_machine_translation(server.provider(), _job(project), TaskContext(), written.extend)
    assert [t for _, t in written] == ["Deli misin sen?"]
    assert (summary.retried, summary.suspicious, summary.translated) == (1, 0, 1)


def _row(i: int, source: str, translation: str, status: str = Status.MACHINE) -> TranslationRow:
    return TranslationRow(i, "f", f"k{i}", source, translation, status, "", (), None, f"C/{i}")


def test_check_row_marks_suspicious_translation() -> None:
    issues = check_row(_row(1, "Hello there, friend.", "Merhaba 朋友, nasılsın?"), "", "")
    suspicious = [i for i in issues if i.kind == "suspicious"]
    assert len(suspicious) == 1
    assert suspicious[0].severity == SEVERITY_WARNING
    assert KIND_LABELS["suspicious"] == "Şüpheli çeviri"
    # Bilerek orijinal bırakılan satır şüpheli sayılmaz.
    assert not [i for i in check_row(_row(2, "You're crazy!", "You're crazy!"), "", "") if i.kind == "suspicious"]


def _inconsistent(rows: list[TranslationRow]) -> list[tuple[int, str]]:
    return [(i.row_id, i.message) for i in run_checks(rows, "", "") if i.kind == "inconsistent"]


def test_same_source_translated_differently_is_flagged() -> None:
    rows = [
        _row(1, "Save the game?", "Oyun kaydedilsin mi?"),
        _row(2, "Save the game?", "Oyunu kaydet?"),
        _row(3, "Save the game?", "Oyun kaydedilsin mi?"),
        _row(4, "Load", "Yükle"),
        _row(5, "Load", "Yükle"),
        _row(6, "Quit", ""),  # çevrilmemiş satır karşılaştırılmaz
        _row(7, "Quit", "Çık"),
    ]
    found = _inconsistent(rows)
    assert [rid for rid, _ in found] == [1, 2, 3]
    assert found[0][1] == (
        "Aynı metin 2 farklı biçimde çevrilmiş: “Oyun kaydedilsin mi?” (2 satır), “Oyunu kaydet?” (1 satır)."
    )
    assert KIND_LABELS["inconsistent"] == "Tutarsız çeviri"


def test_differences_chosen_by_the_user_are_not_flagged() -> None:
    # Bütün farklı biçimler onaylandıysa kullanıcı bilerek seçmiştir (ör. bağlama göre farklı kısa cevaplar).
    rows = [
        _row(1, "Not me.", "Ben değilim.", Status.APPROVED),
        _row(2, "Not me.", "Benden değil.", Status.APPROVED),
    ]
    assert _inconsistent(rows) == []
    rows.append(_row(3, "Not me.", "Ben değil.", Status.MACHINE))
    assert [rid for rid, _ in _inconsistent(rows)] == [1, 2, 3]


def test_summary_message_points_to_suspicious_rows() -> None:
    message, state = describe_summary(ACTION_TRANSLATE, RunSummary(rows=3, translated=3, suspicious=2))
    assert "2 satırın çevirisinde uydurma belirtisi" in message
    assert "Şüpheli çeviri" in message
    assert state == "warning"
