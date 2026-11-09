"""Model çıktısının temizlik katmanı: fazla etiket, uydurma kod, sona yığılmış satır sonu kodları."""

from __future__ import annotations

import json
from typing import Any

import pytest

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.autofix import plan_fixes
from nxceviri.core.qa.checks import SEVERITY_ERROR, run_checks
from nxceviri.core.translate import runner as runner_module
from nxceviri.core.translate.cleanup import (
    clean_output,
    collapse_repeated_punct,
    drop_invented_codes,
    drop_space_before_punct,
    foreign_markup,
    misplaced_breaks,
    split_words,
    spread_trailing_breaks,
    strip_markup,
    tidy_punctuation,
    tidy_spaces,
)
from nxceviri.core.translate.runner import ACTION_REVISE, MachineJob, run_machine_translation
from nxceviri.gui.jobs import describe_summary
from tests.fake_ollama import FakeOllama

BREAKS = ("Satır sonu", "Satır sonu", "Renk")
SOURCE = "I never thought⟦1⟧I'd see you again⟦2⟧in this town."


def test_markup_not_in_source_is_removed() -> None:
    assert foreign_markup("Hi", "<div>Selam</div>") == ["<div>", "</div>"]
    assert strip_markup("Hi", "<div>Selam</div>") == "Selam "
    assert clean_output("Hi", "<div>Selam</div>") == "Selam "  # sondaki boşluğu çalıştırıcı özgünle eşler
    assert clean_output("Hi <b>there</b>", "Selam <b>oradaki</b>") == "Selam <b>oradaki</b>"  # özgünde var
    assert clean_output("Jump!", "Zıpla&nbsp;!") == "Zıpla!"
    assert clean_output("A < B and C > D", "A < B ve C > D") == "A < B ve C > D"  # etiket değil


def test_invented_and_duplicated_codes_are_dropped() -> None:
    assert drop_invented_codes("Press ⟦3⟧ to jump.", "⟦3⟧ ⟦4⟧ tuşuna bas ⟦3⟧") == "⟦3⟧  tuşuna bas "
    assert clean_output("Press ⟦3⟧ to jump.", "Zıplamak için ⟦3⟧ ⟦4⟧ tuşuna bas.") == "Zıplamak için ⟦3⟧ tuşuna bas."


def test_trailing_line_breaks_are_spread_like_the_source() -> None:
    piled = "Seni bu kasabada bir daha göreceğimi hiç düşünmezdim.⟦1⟧⟦2⟧"
    assert misplaced_breaks(SOURCE, piled, BREAKS)
    fixed = spread_trailing_breaks(SOURCE, piled, BREAKS)
    assert fixed == "Seni bu kasabada⟦1⟧bir daha göreceğimi⟦2⟧hiç düşünmezdim."
    assert not misplaced_breaks(SOURCE, fixed, BREAKS)
    # Özgündeki boşluk düzeni korunur; özgünde de sonda duran kod sonda kalır.
    src = "Hello there ⟦1⟧ friend⟦2⟧"
    assert spread_trailing_breaks(src, "Merhaba orada dostum⟦1⟧⟦2⟧", BREAKS) == "Merhaba orada ⟦1⟧ dostum⟦2⟧"
    # Renk kodu satır sonu değildir; satır sonu olmayan kodların yerine dokunulmaz.
    assert spread_trailing_breaks("a⟦3⟧b", "x y⟦3⟧", BREAKS) is None
    assert split_words("tek", [1, 1]) is None


def test_qa_flags_markup_and_piled_codes_and_program_fix_repairs_them() -> None:
    rows = [
        TranslationRow(1, "f", "a", "Hi", "<div>Selam</div>", "machine", "", (), None),
        TranslationRow(
            2,
            "f",
            "b",
            SOURCE,
            "Seni bu kasabada bir daha göreceğimi hiç düşünmezdim.⟦1⟧⟦2⟧",
            "machine",
            "",
            BREAKS,
            None,
        ),
    ]
    issues = run_checks(rows, "", "")
    kinds = {(i.row_id, i.kind, i.severity) for i in issues}
    assert (1, "markup", SEVERITY_ERROR) in kinds
    assert any(i.row_id == 2 and i.kind == "code_position" for i in issues)
    plan = plan_fixes(rows, issues)
    assert dict(plan.changes) == {1: "Selam", 2: "Seni bu kasabada⟦1⟧bir daha göreceğimi⟦2⟧hiç düşünmezdim."}


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "RETRY_DELAYS_S", (0.0, 0.0))


def test_runner_cleans_model_output_before_writing() -> None:
    project = Project.new()
    codes = (ControlCode(b"\n", "Satır sonu"), ControlCode(b"\n", "Satır sonu"))
    project.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", (TextEntry("s01", 0, SOURCE, codes),))])
    row = project.translation_rows()[0]
    project.set_translations([(row.id, "Seni⟦1⟧burada⟦2⟧görmezdim.")], machine=True)

    def revise(item: dict[str, Any]) -> str:
        return "<div>Seni bu kasabada bir daha göreceğimi hiç düşünmezdim.</div>⟦1⟧⟦2⟧"

    server = FakeOllama(revise=revise)
    written: list[tuple[int, str]] = []
    job = MachineJob(
        rows=project.translation_rows(),
        source_lang="en",
        notes="",
        glossary=[],
        action=ACTION_REVISE,
        instruction="Doğal yaz.",
        all_rows=project.translation_rows(),
    )
    summary = run_machine_translation(server.provider(), job, TaskContext(), written.extend)
    assert written == [(row.id, "Seni bu kasabada⟦1⟧bir daha göreceğimi⟦2⟧hiç düşünmezdim.")]
    assert (summary.translated, summary.cleaned) == (1, 1)
    message, state = describe_summary(ACTION_REVISE, summary)
    assert "1 satırda modelin eklediği fazlalıklar temizlendi" in message
    assert state == "success"


def test_partly_piled_breaks_are_flagged_and_left_to_the_model() -> None:
    src = "We could make⟦1⟧the goal out of sticks, or...⟦2⟧out of..."
    text = "Çubuklardan bir kale yaparız, ya da... ne bileyim...⟦1⟧başka bir şeyden...⟦2⟧"  # gemma'nın gerçek çıktısı
    assert misplaced_breaks(src, text, BREAKS)
    assert spread_trailing_breaks(src, text, BREAKS) is None  # oranla bölmek cümleyi bozardı
    row = TranslationRow(3, "f", "c", src, text, "machine", "", BREAKS, None)
    plan = plan_fixes([row], run_checks([row], "", ""))
    assert plan.changes == []  # oranla bölmek cümleyi bozardı; satır elle bakılsın
    assert plan.unfixed == 1
    assert not misplaced_breaks(src, "Çubuklardan⟦1⟧bir kale yaparız, ya da...⟦2⟧başka bir şeyden...", BREAKS)


def test_revise_retries_then_keeps_old_when_break_code_is_moved_to_the_end() -> None:
    src = "We could make⟦1⟧the goal out of sticks, or...⟦2⟧out of..."
    project = Project.new()
    codes = (ControlCode(b"\n", "Satır sonu"), ControlCode(b"\n", "Satır sonu"))
    project.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", (TextEntry("s01", 0, src, codes),))])
    row = project.translation_rows()[0]
    old = "Çubuklardan kale yaparız⟦1⟧ya da...⟦2⟧ne bileyim..."
    project.set_translations([(row.id, old)], machine=True)
    answers = iter(
        [
            "Çubuklardan bir kale yaparız, ya da... ne bileyim...⟦1⟧başka bir şeyden...⟦2⟧",  # gemma'nın çıktısı
            "Çubuklardan bir kale yaparız, ya da...⟦1⟧başka bir şeyden...⟦2⟧",  # yeniden istekte de aynı hata
        ]
    )
    server = FakeOllama(revise=lambda item: next(answers))
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
    assert written == []  # iyi çevirinin yerine yazılmadı
    assert (summary.retried, summary.rejected) == (1, 1)
    retry_items = json.loads(server.requests[1]["messages"][1]["content"])["items"]
    assert "en sona konmuş" in retry_items[0]["fix"]


def test_repeated_punct_collapsed() -> None:
    assert tidy_punctuation("Wait.", "Dur....") == "Dur..."
    assert tidy_punctuation("Hey!", "Hey!!!!") == "Hey!!!"
    assert tidy_punctuation("Yes, okay", "Evet,, tamam") == "Evet, tamam"
    assert tidy_punctuation("A ⟦1⟧ b", "A ⟦1⟧;; b") == "A ⟦1⟧; b"


def test_repeated_punct_kept_when_source_has_it() -> None:
    assert tidy_punctuation("Wait.....", "Bekle.....") == "Bekle....."
    assert tidy_punctuation("Hmm,,", "Hmm,,") == "Hmm,,"


def test_single_cleanups() -> None:
    assert collapse_repeated_punct("Hi", "Hayır!!!! Dur,,") == "Hayır!!! Dur,"
    assert collapse_repeated_punct("Hi!!!!", "Hayır!!!!") == "Hayır!!!!"  # özgünde de var
    assert drop_space_before_punct("Hi", "Merhaba !") == "Merhaba!"
    assert drop_space_before_punct("Hi !", "Merhaba !") == "Merhaba !"


def test_options_can_be_disabled() -> None:
    assert tidy_punctuation("Wait.", "Dur....", repeated=False) == "Dur...."
    assert tidy_punctuation("Hi", "Bir  iki", spaces=False) == "Bir  iki"
    assert tidy_punctuation("Hi", "Merhaba !", before_punct=False) == "Merhaba !"
    assert tidy_punctuation("Hi", "Bir  iki") == "Bir iki"
    assert tidy_punctuation("Hi", "Merhaba !") == "Merhaba!"


def test_tidy_spaces_unchanged_behaviour() -> None:
    assert tidy_spaces("Hi", "Dur....  Merhaba !") == "Dur.... Merhaba!"
    assert tidy_spaces("Hi !", "Merhaba !") == "Merhaba !"
