"""Bağlamlı çeviri, yeniden çeviri ve talimatla düzeltme (redaksiyon)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.translate import placeholders
from nxceviri.core.translate import runner as runner_module
from nxceviri.core.translate.providers.base import BatchItem, ContextLine, ProviderError, Scene
from nxceviri.core.translate.providers.deepl import deepl_context
from nxceviri.core.translate.providers.ollama import TURKISH_STYLE, build_messages, system_prompt
from nxceviri.core.translate.runner import (
    ACTION_RETRANSLATE,
    ACTION_REVISE,
    ACTION_TRANSLATE,
    MachineJob,
    match_edges,
    repair_codes,
    run_machine_translation,
    target_rows,
)
from nxceviri.core.translate.status import Status
from nxceviri.gui.jobs import describe_summary
from tests.fake_deepl import FakeDeepL
from tests.fake_ollama import FakeOllama

#: Despelote'den kısaltılmış bir sahne (aynı dosyada art arda gelen satırlar).
SCENE = [
    ("s01", "It's not just your family. Look how many of them there are,"),
    ("s02", "they're already putting it up.⟦1⟧People are already there. No, no, no."),
    ("s03", "Yes, but they like soccer."),
    ("s04", "Have a drink with me. Have a drink, a little wine."),
    ("s05", "That's the limit!"),
    ("s06", "Not me."),
    ("s07", "Not me."),
]
MENU = [("m01", "Start"), ("m02", "Options")]


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "RETRY_DELAYS_S", (0.0, 0.0))


@pytest.fixture
def project() -> Project:
    p = Project.new()
    p.import_texts(
        [
            ImportedFile(
                "Dialogue.tsv", "0100", "unity", "base", tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(SCENE))
            ),
            ImportedFile(
                "Menu.tsv", "0100", "unity", "base", tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(MENU))
            ),
        ]
    )
    return p


def _rows(project: Project) -> dict[str, TranslationRow]:
    return {r.key: r for r in project.translation_rows()}


def _write(project: Project, overwrite_approved: bool = False) -> runner_module.ResultsCallback:
    def write(results: list[tuple[int, str]]) -> None:
        project.set_translations(results, machine=True, overwrite_approved=overwrite_approved)

    return write


def _payloads(server: FakeOllama) -> list[dict[str, Any]]:
    return [json.loads(r["messages"][1]["content"]) for r in server.requests]


def _job(project: Project, rows: list[TranslationRow], action: str = ACTION_TRANSLATE, **kw: Any) -> MachineJob:
    memory = project.memory_lookup(r.source for r in rows) if action == ACTION_TRANSLATE else {}
    return MachineJob(
        rows=rows, source_lang="en", memory=memory, action=action, all_rows=project.translation_rows(), **kw
    )


# --- istem ---------------------------------------------------------------------------------


def test_turkish_style_rules_only_for_turkish_target() -> None:
    assert TURKISH_STYLE in system_prompt("en", "tr")
    assert "drops subject pronouns" in system_prompt("en", "tr")
    assert TURKISH_STYLE not in system_prompt("en", "de")
    assert "context_before" in system_prompt("en", "tr")
    assert "editor" in system_prompt("en", "tr", revise=True)
    assert "current" in system_prompt("en", "tr", revise=True)


def test_payload_carries_scene_current_fix_and_instruction() -> None:
    scene = Scene(
        before=(ContextLine("Have a drink.", "Bir şey iç."), ContextLine("x" * 500)),
        after=(ContextLine("Fine."),),
        revise=True,
        instruction="Zamirleri at.",
    )
    items = [BatchItem("0", "Not me.", "Dialogue/s06", None, current="Ben değil.", fix="Eksik kontrol kodu: ⟦1⟧")]
    messages = build_messages(items, "en", "tr", "Notlar", [], scene=scene)
    assert "editor" in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["instruction"] == "Zamirleri at."
    assert payload["context_before"][0] == {"text": "Have a drink.", "translation": "Bir şey iç."}
    assert len(payload["context_before"][1]["text"]) == 300  # çok uzun bağlam satırı kısaltılır
    assert payload["context_after"] == [{"text": "Fine."}]
    assert payload["items"] == [
        {
            "id": "0",
            "text": "Not me.",
            "current": "Ben değil.",
            "where": "Dialogue s06",
            "fix": "Eksik kontrol kodu: ⟦1⟧",
        }
    ]
    # Çeviride talimat ve "current" gönderilmez.
    plain = json.loads(build_messages(items, "en", "tr", "", [], scene=Scene(instruction="yok sayılır"))[1]["content"])
    assert "instruction" not in plain
    assert "current" not in plain["items"][0]


def test_match_edges() -> None:
    assert match_edges("  Hello ", "Merhaba") == "  Merhaba "
    assert match_edges("Hello", " Merhaba\n") == "Merhaba"
    assert match_edges("Hello ", "   ") == "   "  # boş sonuç olduğu gibi kalır (yer tutucu denetimi karar verir)


# --- satır seçimi ---------------------------------------------------------------------------


def test_target_rows_by_action(project: Project) -> None:
    rows = _rows(project)
    project.set_translations([(rows["s01"].id, "Onaylı")])
    project.set_translations([(rows["s02"].id, "Makine")], machine=True)  # yer tutucu eksik → hatalı
    project.set_translations([(rows["s03"].id, "Makine çevirisi")], machine=True)
    all_rows = project.translation_rows()

    def keys(rs: list[TranslationRow]) -> list[str]:
        return [r.key for r in rs]

    assert keys(target_rows(all_rows, ACTION_TRANSLATE)) == ["s02", "s04", "s05", "s06", "s07", "m01", "m02"]
    assert "s01" not in keys(target_rows(all_rows, ACTION_RETRANSLATE))
    assert "s03" in keys(target_rows(all_rows, ACTION_RETRANSLATE))
    assert "s01" in keys(target_rows(all_rows, ACTION_REVISE, include_approved=True))


# --- bağlamlı partiler ----------------------------------------------------------------------


def test_batches_follow_scene_order_and_carry_context(project: Project) -> None:
    rows = _rows(project)
    project.set_translations([(rows["s04"].id, "Benimle bir şey iç.")])  # insan çevirisi: bağlamda görünür
    server = FakeOllama()
    todo = [r for r in project.translation_rows() if r.status == Status.UNTRANSLATED]
    run_machine_translation(server.provider(), _job(project, todo), TaskContext(), _write(project))
    payloads = _payloads(server)
    # Parti dosya sınırını ve atlanmış satırları aşmaz: s01-s03 | s05-s06 (s07 = s06, tek çeviri) | m01-m02
    assert [[it["text"] for it in p["items"]] for p in payloads] == [
        [SCENE[0][1], SCENE[1][1], SCENE[2][1]],
        ["That's the limit!", "Not me."],
        ["Start", "Options"],
    ]
    second = payloads[1]
    assert second["context_before"][-1] == {"text": SCENE[3][1], "translation": "Benimle bir şey iç."}
    # Önceki partide çevrilen satırlar sonraki partinin bağlamında yeni çevirileriyle görünür.
    assert second["context_before"][0]["translation"].startswith("tr-")
    assert second["context_after"] == [{"text": "Not me."}]
    assert "context_before" not in payloads[2]  # menü dosyasının başı: önünde satır yok
    assert _rows(project)["s07"].translation == _rows(project)["s06"].translation


def test_retranslate_ignores_memory_and_each_row_gets_own_context(project: Project) -> None:
    rows = _rows(project)
    project.set_translations([(rows["s06"].id, "Ben değil.")], machine=True)  # makine belleği: "Not me." → "Ben değil."
    project.set_translations([(rows["s07"].id, "Ben değil.")], machine=True)
    project.set_translations([(rows["s05"].id, "Bu kadarı da fazla!")])  # onaylı
    server = FakeOllama(translate=lambda t: {"Not me.": "Ben içmem."}.get(t, "tr-" + t))
    targets = target_rows([_rows(project)[k] for k in ("s05", "s06", "s07")], ACTION_RETRANSLATE)
    assert [r.key for r in targets] == ["s06", "s07"]  # onaylı satır kendiliğinden dahil edilmez
    summary = run_machine_translation(
        server.provider(), _job(project, targets, ACTION_RETRANSLATE), TaskContext(), _write(project)
    )
    sent = [it["text"] for p in _payloads(server) for it in p["items"]]
    assert sent == ["Not me.", "Not me."]  # bellek atlandı; aynı cümle her satırda ayrı çevrildi
    after = _rows(project)
    assert (after["s06"].translation, after["s07"].translation) == ("Ben içmem.", "Ben içmem.")
    assert after["s06"].status == Status.MACHINE
    assert summary.translated == 2
    assert summary.from_memory == 0
    # Yeniden çevrilen satırın eski çevirisi bağlamda örnek gösterilmez.
    assert len(server.requests) == 1  # art arda iki satır tek partide; dosyanın sonu: arkasında satır yok
    first = _payloads(server)[0]
    assert first["context_before"][-1] == {"text": "That's the limit!", "translation": "Bu kadarı da fazla!"}
    assert "context_after" not in first


def test_retranslate_keeps_old_translation_when_result_is_broken(project: Project) -> None:
    rows = _rows(project)
    project.set_translations([(rows["s02"].id, "Zaten kuruyorlar.⟦1⟧Millet çoktan gelmiş.")], machine=True)
    server = FakeOllama(break_texts={SCENE[1][1]: 5})
    summary = run_machine_translation(
        server.provider(), _job(project, [_rows(project)["s02"]], ACTION_RETRANSLATE), TaskContext(), _write(project)
    )
    assert summary.rejected == 1
    assert summary.retried == 1
    retry = _payloads(server)[1]["items"][0]
    assert "Eksik kontrol kodu: ⟦1⟧" in retry["fix"]  # yeniden istekte sorun açıkça yazılır
    row = _rows(project)["s02"]
    assert row.translation == "Zaten kuruyorlar.⟦1⟧Millet çoktan gelmiş."
    assert row.status == Status.MACHINE


def test_revise_sends_current_and_instruction_and_counts_unchanged(project: Project) -> None:
    rows = _rows(project)
    project.set_translations([(rows["s03"].id, "Evet, ama onlar futbolu seviyorlar.")], machine=True)
    project.set_translations([(rows["s05"].id, "Bu kadarı da fazla!")], machine=True)
    project.set_translations([(rows["s06"].id, "Ben değil.")])  # onaylı

    def revise(item: dict[str, Any]) -> str:
        return {"Yes, but they like soccer.": "Ama futbolu seviyorlar ki."}.get(item["text"], str(item["current"]))

    server = FakeOllama(revise=revise)
    targets = target_rows([_rows(project)[k] for k in ("s03", "s05", "s06")], ACTION_REVISE, include_approved=True)
    summary = run_machine_translation(
        server.provider(),
        _job(project, targets, ACTION_REVISE, instruction="Zamirleri at, doğal konuş."),
        TaskContext(),
        _write(project, overwrite_approved=True),
    )
    payloads = _payloads(server)
    assert all(p["instruction"] == "Zamirleri at, doğal konuş." for p in payloads)
    assert payloads[0]["items"][0]["current"] == "Evet, ama onlar futbolu seviyorlar."
    assert "editor" in server.requests[0]["messages"][0]["content"]
    after = _rows(project)
    assert after["s03"].translation == "Ama futbolu seviyorlar ki."
    assert (summary.translated, summary.unchanged) == (1, 2)
    assert after["s06"].status == Status.APPROVED  # aynen kalan onaylı satırın durumu değişmez


def test_revise_overwrites_approved_only_when_asked(project: Project) -> None:
    rows = _rows(project)
    project.set_translations([(rows["s06"].id, "Ben değil.")])
    server = FakeOllama()
    job = _job(project, [_rows(project)["s06"]], ACTION_REVISE, instruction="Doğal yaz.")
    run_machine_translation(server.provider(), job, TaskContext(), _write(project))
    assert _rows(project)["s06"].translation == "Ben değil."  # onaylı satır korunur
    run_machine_translation(server.provider(), job, TaskContext(), _write(project, overwrite_approved=True))
    row = _rows(project)["s06"]
    assert (row.translation, row.status) == ("dz-Not dz-me.", Status.MACHINE)


def test_revise_requires_instruction_capable_provider(project: Project) -> None:
    job = _job(project, [_rows(project)["s06"]], ACTION_REVISE, instruction="Doğal yaz.")
    with pytest.raises(ProviderError, match="talimatla düzeltme"):
        run_machine_translation(FakeDeepL().provider(), job, TaskContext(), _write(project))


def test_unknown_action_is_rejected(project: Project) -> None:
    with pytest.raises(ValueError, match="Bilinmeyen"):
        run_machine_translation(FakeOllama().provider(), _job(project, [], "uydurma"), TaskContext(), _write(project))


# --- DeepL bağlamı --------------------------------------------------------------------------


def test_deepl_context_uses_neighbour_sources() -> None:
    scene = Scene(before=(ContextLine("Have a ⟦1⟧drink.", "Bir şey iç."),), after=(ContextLine("  "),))
    assert deepl_context("A family drama.", scene) == "A family drama.\n\nHave a drink."
    assert deepl_context("", None) == ""


def test_deepl_receives_scene_context(project: Project) -> None:
    server = FakeDeepL()
    rows = [_rows(project)[k] for k in ("s05", "s06")]
    run_machine_translation(server.provider(), _job(project, rows, ACTION_RETRANSLATE), TaskContext(), _write(project))
    translate_calls = [body for _method, path, body, _host in server.requests if path == "/v2/translate"]
    assert SCENE[3][1] in translate_calls[0]["context"]


# --- kontrol kodu onarımı ve açıklaması -----------------------------------------------------

LINE_BREAK = ControlCode(b"\\n", "Satır sonu")
SUBTITLE = "We could make⟦1⟧the goal out of sticks, or...⟦2⟧out of..."


def test_placeholder_repair() -> None:
    assert placeholders.repair("a⟦1⟧b⟦2⟧", "x[1]y【 2 】") == "x⟦1⟧y⟦2⟧"
    assert placeholders.repair("[1] ⟦1⟧", "[1] z [1]") == "[1] z [1]"  # kaynakta da geçen yazım onarılmaz
    assert placeholders.repair("a⟦1⟧", "a⟦1⟧ [1]") == "a⟦1⟧ [1]"  # eksik değilse dokunulmaz
    assert placeholders.repair("a⟦1⟧", "{1} ve {1}") == "⟦1⟧ ve {1}"  # yalnızca ilk eşleşme


def test_line_break_codes_are_restored_from_newlines() -> None:
    labels = ("Satır sonu", "Satır sonu")
    assert repair_codes(SUBTITLE, "Kaleyi\nçubuklardan, ya da...\nşeyden...", labels) == (
        "Kaleyi⟦1⟧çubuklardan, ya da...⟦2⟧şeyden..."
    )
    assert repair_codes(SUBTITLE, "Kaleyi\\nçubuklardan\\nşeyden", labels) == "Kaleyi⟦1⟧çubuklardan⟦2⟧şeyden"
    assert repair_codes(SUBTITLE, "Kaleyi\nçubuklardan", labels) == "Kaleyi\nçubuklardan"  # sayı tutmuyor
    assert repair_codes("a⟦1⟧b", "x\ny", ("Değişken {0}",)) == "x\ny"  # satır sonu olmayan kod tahmin edilmez
    assert repair_codes("a\n⟦1⟧b", "x\n\ny", labels) == "x\n\ny"  # özgünde satır sonu varsa dokunulmaz


def _subtitle_project(translation: str) -> Project:
    p = Project.new()
    entry = TextEntry("sub", 0, SUBTITLE, (LINE_BREAK, LINE_BREAK))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", (entry,))])
    p.set_translations([(p.translation_rows()[0].id, translation)], machine=True)
    return p


def test_code_meanings_are_sent_and_newlines_accepted() -> None:
    p = _subtitle_project("Kalesini çubuklardan yapabiliriz⟦1⟧, ya da...⟦2⟧şeyden...")
    server = FakeOllama(translate=lambda t: "Kaleyi çubuklardan\nyapabiliriz ya da...\nbaşka bir şeyden...")
    summary = run_machine_translation(
        server.provider(), _job(p, p.translation_rows(), ACTION_RETRANSLATE), TaskContext(), _write(p)
    )
    item = _payloads(server)[0]["items"][0]
    assert item["codes"] == {"⟦1⟧": "Satır sonu", "⟦2⟧": "Satır sonu"}
    assert "Satır sonu" in server.requests[0]["messages"][0]["content"]
    assert (summary.translated, summary.rejected, summary.retried) == (1, 0, 0)
    assert p.translation_rows()[0].translation == "Kaleyi çubuklardan⟦1⟧yapabiliriz ya da...⟦2⟧başka bir şeyden..."


def test_rejection_keeps_suggestion_and_retry_names_expected_codes() -> None:
    old = "Kalesini çubuklardan yapabiliriz⟦1⟧, ya da...⟦2⟧şeyden..."
    p = _subtitle_project(old)
    server = FakeOllama(translate=lambda t: "Kaleyi çubuklardan yapabiliriz ya da başka şeyden.")
    summary = run_machine_translation(
        server.provider(), _job(p, p.translation_rows(), ACTION_RETRANSLATE), TaskContext(), _write(p)
    )
    assert summary.rejected == 1
    assert p.translation_rows()[0].translation == old
    retry_fix = _payloads(server)[1]["items"][0]["fix"]
    assert "şu kodlar bu sırayla ve her biri bir kez bulunmalı: ⟦1⟧ ⟦2⟧" in retry_fix
    (rj,) = summary.rejections
    assert rj.suggestion == "Kaleyi çubuklardan yapabiliriz ya da başka şeyden."
    assert any("Eksik kontrol kodu" in i for i in rj.issues)
    msg, state = describe_summary(ACTION_RETRANSLATE, summary)
    assert state == "warning"
    assert "Modelin önerisi: “Kaleyi çubuklardan yapabiliriz ya da başka şeyden.”" in msg
