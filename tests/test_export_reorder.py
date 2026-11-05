"""Hatalı satırları aktarırken yalnızca kod sırası farklı olan satırlar: serbest kodlar yazılır, çiftler yazılmaz."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxceviri.core.archives import cpk
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.export.layeredfs import ExportResult, TextFileRef, _export_member_archive, collect_translations
from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.fmsb import FmsbPlugin
from nxceviri.core.project import TranslationRow
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.status import Status
from tests.test_unicorn import TID, _tree
from tests.ysuobuild import build_cpk, build_fmsb

VAR = "Değişken %d"
NAME = "Ad değişkeni #FN(Bob)"
OPEN = "Renk #c(15)"
CLOSE = "Renk sonu #/c"


def _free_vars(n: int) -> bool:
    return n in (1, 2)


def test_order_only_problem_distinguishes_safe_reorder() -> None:
    src = "Altın ⟦1⟧, ad ⟦2⟧, ⟦3⟧renkli⟦4⟧"
    assert placeholders.order_only_problem(src, "Ad ⟦2⟧, altın ⟦1⟧, ⟦3⟧renkli⟦4⟧", _free_vars)
    assert not placeholders.order_only_problem(src, "Ad ⟦2⟧, altın ⟦1⟧, ⟦4⟧renkli⟦3⟧", _free_vars)  # çift ters
    assert not placeholders.order_only_problem(src, "Ad ⟦2⟧, altın ⟦1⟧, ⟦3⟧renkli", _free_vars)  # kod eksik
    assert not placeholders.order_only_problem(src, src, _free_vars)  # sorun yok: sıra farkı da yok
    assert placeholders.problems(src, "Ad ⟦2⟧, altın ⟦1⟧, ⟦3⟧renkli⟦4⟧")
    with placeholders.tolerate_reorder():
        assert not placeholders.problems(src, "Ad ⟦2⟧, altın ⟦1⟧, ⟦3⟧renkli⟦4⟧")
        assert placeholders.problems(src, "Altın ⟦1⟧, ad ⟦2⟧, ⟦3⟧renkli")  # sayı farkı hâlâ sorun
    assert placeholders.problems(src, "Ad ⟦2⟧, altın ⟦1⟧, ⟦3⟧renkli⟦4⟧")  # blok bitince eski hâle döner


def test_renumber() -> None:
    assert placeholders.renumber("a ⟦2⟧ b ⟦1⟧ ⟦2⟧") == "a ⟦1⟧ b ⟦2⟧ ⟦3⟧"


def _row(key: str, source: str, translation: str, labels: tuple[str, ...]) -> TranslationRow:
    return TranslationRow(1, "f.fms", key, source, translation, Status.ERROR, "", labels, None)


def test_collect_translations_tries_only_free_code_reorders() -> None:
    rows = [
        _row("a", "Altın ⟦1⟧ ad ⟦2⟧", "Ad ⟦2⟧ altın ⟦1⟧", (VAR, NAME)),
        _row("b", "⟦1⟧renkli⟦2⟧", "⟦2⟧renkli⟦1⟧", (OPEN, CLOSE)),
        _row("c", "Altın ⟦1⟧", "Altın", (VAR,)),
    ]
    soft: dict[str, set[str]] = {}
    reordered: dict[str, set[str]] = {}
    by_file, written, errors, _u = collect_translations(rows, "", include_errors=True, soft=soft, reordered=reordered)
    assert by_file == {"f.fms": {"a": "Ad ⟦2⟧ altın ⟦1⟧"}}
    assert (written, errors) == (0, 3)
    assert soft == {"f.fms": {"a"}}
    assert reordered == {"f.fms": {"a"}}


def test_fmsb_export_writes_reordered_free_codes_and_verifies() -> None:
    plugin = FmsbPlugin()
    sheet = build_fmsb(["##(START)", "", "Gold: %d, name: #FN(Bob)"])
    archive = build_cpk({"MsgSheet/A.fms": sheet})
    path = "Unicorn_US.CPK>MsgSheet/A.fms"
    key = plugin.extract(sheet)[0].key
    translations = {path: {key: "Ad: ⟦2⟧, altın: ⟦1⟧"}}
    tree = _tree({"Unicorn_US.CPK": archive})
    with pytest.raises(FormatError):  # sıra gevşetmesi olmadan eklenti reddeder
        plugin.inject(sheet, translations[path])
    result = ExportResult(Path("x"))
    result.soft_keys = {path: frozenset({key})}
    result.reordered_keys = {path: frozenset({key})}
    outputs = _export_member_archive(
        tree,
        "Unicorn_US.CPK",
        [TextFileRef(path, TID, "fmsb")],
        translations=translations,
        root=Path("romfs"),
        result=result,
    )
    arc = cpk.CpkFile(MemoryStorage(outputs[0][1]), "Unicorn_US.CPK")
    written = arc.read("MsgSheet/A.fms")
    assert b"Ad: #FN(Bob), alt\xc4\xb1n: %d" in written  # her kod kendi ham biçimine döndü
    assert not result.dropped_keys.get(path)
    assert result.attempted_keys[path] == frozenset({key})
