"""Sözlük önerisi: metinlerden aday terimlerin bulunması ve Ollama'dan karşılık istenmesi."""

from __future__ import annotations

import json

import pytest

from nxceviri.core.errors import OperationCancelled
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.status import Status
from nxceviri.core.translate.terms import TermSuggestion, find_candidates, suggest_glossary
from tests.fake_ollama import FakeOllama


def _rows(*sources: str) -> list[TranslationRow]:
    return [TranslationRow(i, "f", f"k{i}", s, "", Status.UNTRANSLATED, "", (), None) for i, s in enumerate(sources)]


ROWS = _rows(
    "Welcome to Silver Pines, stranger.",
    "The Sheriff is waiting at the Old Mill.",
    "Ask the Sheriff about Silver Pines.",
    "Did you see the Old Mill?",
    "Yes. I saw it.",  # cümle başı sözcükler aday değil
    "Yes, Mara went home.",
    "Mara is late again.",  # cümle başında olsa da başka yerde de geçtiği için aday
    "Press ⟦1⟧ to OPEN the MENU.",  # kodlar ve büyük harfli arayüz sözcükleri atlanır
    "OPEN the MENU now.",
    "Once upon a time.",  # tek geçen aday değil
)


def test_find_candidates_collects_repeated_names() -> None:
    found = find_candidates(ROWS, [GlossaryTerm("sheriff", "Şerif")])
    assert [(c.term, c.count) for c in found] == [("Silver Pines", 2), ("Old Mill", 2), ("Mara", 2)]
    assert found[0].examples == ("Welcome to Silver Pines, stranger.", "Ask the Sheriff about Silver Pines.")


def test_find_candidates_limit_and_empty() -> None:
    assert [c.term for c in find_candidates(ROWS, [], limit=2)] == ["Silver Pines", "Sheriff"]
    assert find_candidates([], []) == []


def test_suggest_glossary_asks_model_in_batches() -> None:
    server = FakeOllama()
    candidates = find_candidates(ROWS, [])
    progress: list[tuple[int, int]] = []
    ctx = TaskContext(progress=lambda done, total, _msg: progress.append((done, total)))
    got = suggest_glossary(server.provider(), candidates, "en", "Kasaba korku oyunu.", ctx, batch_size=2)
    assert got == [
        TermSuggestion("Silver Pines", "tr-Silver Pines", "öneri notu", 2),
        TermSuggestion("Sheriff", "tr-Sheriff", "öneri notu", 2),
        TermSuggestion("Old Mill", "tr-Old Mill", "öneri notu", 2),
        TermSuggestion("Mara", "tr-Mara", "öneri notu", 2),
    ]
    chats = [r for r in server.requests if "format" in r]
    assert len(chats) == 2
    payload = json.loads(chats[0]["messages"][1]["content"])
    assert payload["terms"][0] == {
        "term": "Silver Pines",
        "examples": ["Welcome to Silver Pines, stranger.", "Ask the Sheriff about Silver Pines."],
    }
    assert "Kasaba korku oyunu." in chats[0]["messages"][0]["content"]
    assert progress[-1] == (4, 4)


def test_suggest_glossary_drops_terms_model_rejects_or_invents() -> None:
    def suggest(payload: dict[str, object]) -> list[dict[str, object]]:
        return [
            {"term": "Silver Pines", "translation": "Silver Pines", "note": "yer adı", "add": True},
            {"term": "Sheriff", "translation": "Şerif", "note": "", "add": False},  # model gereksiz buldu
            {"term": "Ghost Town", "translation": "Hayalet Kasaba", "note": "", "add": True},  # listede yoktu
            {"term": "Old Mill", "translation": "  ", "note": "", "add": True},  # boş çeviri
        ]

    server = FakeOllama(suggest=suggest)
    got = suggest_glossary(server.provider(), find_candidates(ROWS, [])[:3], "en", "", TaskContext())
    assert got == [TermSuggestion("Silver Pines", "Silver Pines", "yer adı", 2)]


def test_suggest_glossary_can_be_cancelled() -> None:
    ctx = TaskContext()
    ctx.token.cancel()
    with pytest.raises(OperationCancelled):
        suggest_glossary(FakeOllama().provider(), find_candidates(ROWS, []), "en", "", ctx)


def test_connectors_join_multiword_names() -> None:
    rows = _rows(
        "Take the Sword of the Moon.", "Is the Sword of the Moon here?", "Ask him, Lord Varen.", "Lord Varen is here."
    )
    assert [c.term for c in find_candidates(rows, [])] == ["Sword of the Moon", "Lord Varen"]
