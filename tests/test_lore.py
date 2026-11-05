"""Lore maddeleri: çevirisi boş, notu olan sözlük maddeleri. Modele bilgi olarak gider, çeviriye zorlanmaz."""

from __future__ import annotations

import json

from nxceviri.core.project import Project
from nxceviri.core.qa.checks import glossary_patterns
from nxceviri.core.translate.providers.base import BatchItem, GlossaryTerm
from nxceviri.core.translate.providers.ollama import build_messages
from tests.fake_deepl import FREE_KEY, FakeDeepL

LORE = GlossaryTerm("Elara", "", "Kahramanın ablası; resmî konuşur, ona 'siz' denir.")


def test_project_keeps_lore_entries() -> None:
    project = Project.new()
    project.set_glossary([GlossaryTerm("Sheriff", "Şerif"), LORE, GlossaryTerm("Boş", "", "")])
    assert project.glossary() == [GlossaryTerm("Sheriff", "Şerif"), LORE]


def test_ollama_sends_lore_as_background_note() -> None:
    messages = build_messages([BatchItem("0", "Elara, wait!")], "en", "tr", "", [LORE])
    payload = json.loads(messages[1]["content"])
    assert payload["glossary"] == [{"term": "Elara", "note": LORE.note}]
    assert "without a translation" in messages[0]["content"]


def test_lore_is_not_a_fixed_translation() -> None:
    assert glossary_patterns([LORE]) == []  # QA sözlük uyarısı vermez
    server = FakeDeepL()
    provider = server.provider(FREE_KEY)
    provider.translate_batch([BatchItem("0", "Elara, wait!")], "en", "tr", "", [LORE, GlossaryTerm("wait", "bekle")])
    assert list(server.glossaries.values()) == ["wait\tbekle"]  # DeepL sözlüğüne yalnızca çevirisi olanlar
