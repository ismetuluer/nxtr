"""Redaksiyonda halüsinasyon önlemleri: gemma4:12b'nin gerçek redaksiyon çıktılarından örnekler."""

from __future__ import annotations

import pytest

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.translate import runner as runner_module
from nxceviri.core.translate.guards import looks_english, repeated_pair, revision_problems
from nxceviri.core.translate.runner import ACTION_REVISE, MachineJob, run_machine_translation
from tests.fake_ollama import FakeOllama


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "RETRY_DELAYS_S", (0.0, 0.0))


def _problems(source: str, old: str, new: str) -> list[str]:
    return revision_problems(source, old, new, "en", "tr")


@pytest.mark.parametrize(
    ("source", "old", "new", "expected"),
    [
        # İngilizce yazıp cümle uydurmuş.
        ("You're crazy!", "Deli misin sen ya!", "You're crazy!\n\nDon't you think it's a bit risky?", "İngilizce"),
        # Komşu satırın metnini alıp tekrar döngüsüne girmiş.
        (
            "See? I told you we should⟦1⟧treat that ball like",
            "Gördün mü?⟦1⟧Size o topla şöyle davranmamız gerektiğini söylemiştim.",
            "Gördün mü?⟦1⟧Topa sanki kendi çocuğumuzmuş gibi,türlü türlü davranmamız gerektiğini "
            "söylemiştim,türlü türlü",
            "tekrar",
        ),
        # Cümlenin yarısı önceki satıra kaçmış.
        (
            "it's our own kid, but you don't listen.",
            "Sanki o bizim çocuğumuz gibi, ama sen dinlemiyorsun.",
            "ama sen dinlemiyorsun.",
            "kısa",
        ),
    ],
)
def test_real_small_model_failures_are_caught(source: str, old: str, new: str, expected: str) -> None:
    assert any(expected in p for p in _problems(source, old, new))


@pytest.mark.parametrize(
    ("source", "old", "new"),
    [
        ("Oh that's nice!", "Ah, ne güzel!", "Harika!"),
        ("Also, the park is too far from our house.", "Ayrıca, park evimizden çok uzak.", "Hem park da çok uzak."),
        (
            "No! How are we gonna get it down? We need a ladder.",
            "Yok! Nasıl indireceğiz? Merdiven lazım.",
            "Hayır! Onu nasıl indireceğiz? Merdiven lazım.",
        ),
        ("Make ASMR!", "ASMR yap!", "Hadi ASMR yapalım!"),
        ("We could make it, or...", "Yaparız ya da... ya da...", "Yaparız, ya da... ya da işte..."),
        ("OK.", "Tamam.", "OK."),
    ],
)
def test_normal_revisions_pass(source: str, old: str, new: str) -> None:
    assert _problems(source, old, new) == []


def test_helpers() -> None:
    assert looks_english("Don't you think it's a bit risky?")
    assert not looks_english("Bence de en iyisi bu, değil mi?")
    assert repeated_pair("türlü türlü yaptık, türlü türlü") == "türlü türlü"
    assert repeated_pair("ya da şu ya da bu") is None
    assert revision_problems("Kimi wa baka!", "Deli misin!", "You are crazy!", "ja", "tr") == []  # yalnızca en→tr


def test_revise_keeps_old_translation_when_model_writes_english() -> None:
    project = Project.new()
    project.import_texts([ImportedFile("D.tsv", "0100", "unity", "base", (TextEntry("s01", 0, "You're crazy!", ()),))])
    row = project.translation_rows()[0]
    project.set_translations([(row.id, "Deli misin sen ya!")], machine=True)
    server = FakeOllama(revise=lambda item: "You're crazy!\n\nDon't you think it's a bit risky?")
    job = MachineJob(
        rows=project.translation_rows(),
        source_lang="en",
        notes="",
        glossary=[],
        action=ACTION_REVISE,
        instruction="Doğal yaz.",
        all_rows=project.translation_rows(),
    )
    written: list[tuple[int, str]] = []
    summary = run_machine_translation(server.provider(), job, TaskContext(), written.extend)
    assert written == []
    assert (summary.retried, summary.rejected) == (1, 1)
    assert any("İngilizce" in issue for issue in summary.rejections[0].issues)
