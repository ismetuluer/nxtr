"""Aç/kapa kod çiftleri bütün olarak taşınabilir (ürün sahibinin kararı, 2026-11-17).

Biçim eklentisi hangi kodun bir çiftin açılışı/kapanışı olduğunu `paired_code` ile bildirir. Bir çift iç içeliği
bozulmadan bir bütün olarak yer değiştirdiyse satır hatalı değildir, uyarıdır. Çaprazlama, açılışın kapanıştan
sonra gelmesi, eksik/fazla/yinelenen kod, serbest olmayan kodların kendi aralarındaki sırasının değişmesi ve katı
bir kodun çifte girip çıkması her zaman hatadır. Bildirmeyen eklentide davranış değişmez (katı).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from nxceviri.core.archives import cpk
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.export.layeredfs import (
    ExportResult,
    TextFileRef,
    _export_member_archive,
    collect_translations,
    settle_rows,
)
from nxceviri.core.formats import registry
from nxceviri.core.formats.base import ControlCode, FormatPlugin, TextEntry
from nxceviri.core.formats.fmsb import FmsbPlugin
from nxceviri.core.formats.fmsb import plugin as fmsb
from nxceviri.core.formats.msbt import MsbtPlugin
from nxceviri.core.formats.nnitext import NniTextPlugin
from nxceviri.core.formats.nnitext import plugin as nnitext
from nxceviri.core.formats.pakyc import PakYcPlugin
from nxceviri.core.formats.pakyc import plugin as pakyc
from nxceviri.core.formats.psbtext import PsbTextPlugin
from nxceviri.core.formats.psbtext import plugin as psbtext
from nxceviri.core.formats.srt import SrtPlugin
from nxceviri.core.formats.srt import plugin as srt
from nxceviri.core.formats.unity import UnityPlugin, unity
from nxceviri.core.formats.unreal import LocresPlugin, locres
from nxceviri.core.formats.wadlin import WadLinPlugin
from nxceviri.core.formats.wadlin import plugin as wadlin
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.qa.autofix import plan_fixes
from nxceviri.core.qa.checks import check_row
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.placeholders import CodeRoles
from nxceviri.core.translate.status import Status
from tests.nnicpkbuild import build_cpk, build_fmsb, build_xso
from tests.nxbuild import build_msbt
from tests.psbbuild import build_psb
from tests.test_cpk_fmsb import TID, _tree
from tests.test_srt import build_srt
from tests.test_wadlin import build_lin
from tests.unitybuild import build_bundle, string_table
from tests.unrealbuild import build_locres
from tests.ycdbuild import LANGUAGES, UI_HEADER, table, ycd

B_OPEN, B_CLOSE = ("b", "open"), ("b", "close")
C_OPEN, C_CLOSE = ("color", "open"), ("color", "close")


def _roles(free: set[int] | None = None, **pairs: tuple[str, str]) -> CodeRoles:
    """`_roles({3}, p1=B_OPEN, p2=B_CLOSE)`: 3 serbest, 1-2 çift."""
    return CodeRoles(free or set(), {int(k[1:]): v for k, v in pairs.items()})


# --- tek karar işlevi -----------------------------------------------------------------------


def test_pair_moved_as_a_whole_is_a_warning() -> None:
    src = "Press ⟦1⟧A⟦2⟧ to ⟦3⟧jump⟦4⟧"
    roles = _roles(p1=B_OPEN, p2=B_CLOSE, p3=C_OPEN, p4=C_CLOSE)
    found = placeholders.check(src, "⟦3⟧Zıplamak⟦4⟧ için ⟦1⟧A⟦2⟧ basın", roles)
    assert not found.errors
    assert found.warnings == (placeholders.PAIR_REORDER_WARNING,)
    assert placeholders.check(src, "⟦1⟧A⟦2⟧ ile ⟦3⟧zıpla⟦4⟧", roles) == placeholders.CodeCheck()


def test_broken_pairs_are_errors() -> None:
    src = "Press ⟦1⟧A⟦2⟧ to ⟦3⟧jump⟦4⟧"
    roles = _roles(p1=B_OPEN, p2=B_CLOSE, p3=C_OPEN, p4=C_CLOSE)
    assert placeholders.check(src, "⟦1⟧⟦3⟧A⟦2⟧ zıpla⟦4⟧", roles).errors  # çaprazlama
    assert placeholders.check(src, "⟦2⟧A⟦1⟧ ⟦3⟧zıpla⟦4⟧", roles).errors  # kapanış açılıştan önce
    assert placeholders.check(src, "⟦3⟧zıpla⟦4⟧ ⟦1⟧A", roles).errors  # eksik
    assert placeholders.check(src, "⟦3⟧zıpla⟦4⟧ ⟦1⟧A⟦2⟧⟦5⟧", roles).errors  # fazla
    assert placeholders.check(src, "⟦3⟧zıpla⟦4⟧ ⟦1⟧A⟦2⟧⟦2⟧", roles).errors  # yinelenen
    assert placeholders.check(src, "⟦3⟧Zıplamak⟦4⟧ için ⟦1⟧A⟦2⟧ basın").errors  # çift bildirilmemiş: katı


def test_pairs_with_no_free_codes_still_count() -> None:
    """Serbest kodu olmayan satırın rolleri boş bir kümedir (doğruluk değeri yanlış); çiftler yine de geçerli."""
    roles = _roles(p1=B_OPEN, p2=B_CLOSE)
    assert not roles
    assert placeholders.check("⟦1⟧A⟦2⟧ b ⟦3⟧", "⟦3⟧ b ⟦1⟧A⟦2⟧", roles).warnings  # ⟦3⟧ katı ama tek: sırası aynı
    assert not placeholders.check("x ⟦1⟧A⟦2⟧ ⟦3⟧", "⟦1⟧A⟦2⟧ x ⟦3⟧", roles).errors


def test_strict_codes_keep_their_order_and_their_pair() -> None:
    # ⟦2⟧ %s çiftin içinde, ⟦4⟧ %d dışarıda: çift bütün olarak taşınsa da konumsal sıra değişirse hata.
    roles = _roles(p1=B_OPEN, p3=B_CLOSE)
    assert placeholders.check("⟦1⟧⟦2⟧⟦3⟧ has ⟦4⟧", "⟦4⟧ sahibi ⟦1⟧⟦2⟧⟦3⟧", roles).errors
    assert placeholders.check("⟦4⟧ x ⟦1⟧⟦2⟧⟦3⟧", "⟦1⟧⟦2⟧⟦3⟧ x ⟦4⟧", roles).errors  # çift %d'nin önüne geçti
    moved = placeholders.check("⟦1⟧⟦2⟧⟦3⟧ ⟦5⟧ x ⟦4⟧", "⟦5⟧ x ⟦1⟧⟦2⟧⟦3⟧ ⟦4⟧", _roles({5}, p1=B_OPEN, p3=B_CLOSE))
    assert not moved.errors
    # Satır sonu (katı) çiftin dışına çıkamaz, içine giremez.
    assert placeholders.check("⟦1⟧a⟦2⟧b⟦3⟧", "⟦1⟧a⟦3⟧⟦2⟧b", roles).errors
    roles = _roles(p1=B_OPEN, p2=B_CLOSE)
    assert placeholders.check("⟦1⟧a⟦2⟧ ⟦3⟧b", "⟦1⟧a ⟦3⟧⟦2⟧b", roles).errors


def test_nested_pair_stays_inside_its_parent() -> None:
    src = "⟦1⟧⟦2⟧a⟦3⟧ ⟦4⟧b⟦5⟧⟦6⟧ c ⟦7⟧d⟦8⟧"  # 1-6 içinde 2-3 ve 4-5; 7-8 ayrı çift
    roles = _roles(
        p1=B_OPEN,
        p6=B_CLOSE,
        p2=("i", "open"),
        p3=("i", "close"),
        p4=("u", "open"),
        p5=("u", "close"),
        p7=C_OPEN,
        p8=C_CLOSE,
    )
    pair_moved = (placeholders.PAIR_REORDER_WARNING,)
    assert placeholders.check(src, "⟦1⟧⟦4⟧b⟦5⟧ ⟦2⟧a⟦3⟧⟦6⟧ c ⟦7⟧d⟦8⟧", roles).warnings == pair_moved  # içte
    assert placeholders.check(src, "⟦7⟧d⟦8⟧ c ⟦1⟧⟦2⟧a⟦3⟧ ⟦4⟧b⟦5⟧⟦6⟧", roles).warnings == pair_moved  # içiyle
    assert placeholders.check(src, "⟦1⟧⟦4⟧b⟦5⟧⟦6⟧ ⟦2⟧a⟦3⟧ c ⟦7⟧d⟦8⟧", roles).errors  # iç çift dışarı çıktı
    assert placeholders.check(src, "⟦1⟧⟦4⟧b⟦5⟧⟦6⟧ c ⟦7⟧⟦2⟧a⟦3⟧d⟦8⟧", roles).errors  # başka çiftin içine girdi


def test_free_code_may_enter_a_pair_and_free_only_moves_keep_their_message() -> None:
    src = "⟦1⟧Red⟦2⟧ and ⟦3⟧"
    roles = _roles({3}, p1=C_OPEN, p2=C_CLOSE)
    assert placeholders.check(src, "⟦1⟧Kırmızı ⟦3⟧⟦2⟧", roles).warnings == (placeholders.FREE_REORDER_WARNING,)
    assert placeholders.check(src, "⟦3⟧ ve ⟦1⟧Kırmızı⟦2⟧", roles).warnings == (placeholders.FREE_REORDER_WARNING,)


def test_unmatched_source_codes_stay_strict() -> None:
    # Kaynakta kapanmayan açılış ve başka aileden kapanış eşleşmez: ikisi de katı kalır.
    roles = _roles(p1=C_OPEN, p2=B_CLOSE)
    assert placeholders.check("⟦1⟧a⟦2⟧", "⟦2⟧a⟦1⟧", roles).errors
    # Kaynakta çaprazlanmış etiketler: yalnızca yığınla eşleşen çift taşınabilir, kalan kodlar katıdır.
    roles = _roles(p1=B_OPEN, p2=("i", "open"), p3=B_CLOSE, p4=("i", "close"))
    assert placeholders.check("x ⟦1⟧⟦2⟧a⟦3⟧⟦4⟧", "⟦4⟧ x ⟦1⟧⟦2⟧a⟦3⟧", roles).errors  # katı ⟦2⟧ ile ⟦4⟧ yer değişti


def test_separators_move_with_their_pair_and_keep_their_order() -> None:
    p_open, p_sep, p_close = ("p", "open"), ("p", "separator"), ("p", "close")
    src = "x ⟦1⟧a⟦2⟧b⟦3⟧c⟦4⟧ ⟦5⟧y⟦6⟧"
    roles = _roles(p1=p_open, p2=p_sep, p3=p_sep, p4=p_close, p5=B_OPEN, p6=B_CLOSE)
    assert placeholders.check(src, "⟦5⟧y⟦6⟧ ⟦1⟧a⟦2⟧b⟦3⟧c⟦4⟧ x", roles).warnings  # bütün taşındı
    assert placeholders.check(src, "⟦1⟧a⟦3⟧b⟦2⟧c⟦4⟧ ⟦5⟧y⟦6⟧", roles).errors  # ayraçların sırası değişti
    assert placeholders.check(src, "⟦1⟧a⟦2⟧b⟦4⟧ ⟦5⟧⟦3⟧y⟦6⟧", roles).errors  # ayraç çiftten çıktı
    # Kendi ailesinden bir çiftin içinde olmayan ayraç katı bir koddur.
    roles = _roles(p1=p_sep, p2=B_OPEN, p3=B_CLOSE, p4=p_sep)
    assert placeholders.check("⟦1⟧ ⟦2⟧a⟦3⟧ ⟦4⟧", "⟦4⟧ ⟦2⟧a⟦3⟧ ⟦1⟧", roles).errors


def test_common_roles_keeps_only_shared_pairs() -> None:
    a = _roles({3}, p1=B_OPEN, p2=B_CLOSE)
    b = _roles({3, 4}, p1=B_OPEN, p2=B_CLOSE, p5=C_OPEN)
    common = placeholders.common_roles([a, b])
    assert common == frozenset({3})
    assert common.pairs == {1: B_OPEN, 2: B_CLOSE}
    assert placeholders.common_roles([frozenset({1}), a]).pairs == {}


# --- eklenti bildirimleri -----------------------------------------------------------------------


def _pairs(kind: str, codes: tuple[ControlCode, ...]) -> dict[str, tuple[str, str]]:
    roles = registry.free_codes(kind, codes)
    assert isinstance(roles, CodeRoles)
    return {codes[n - 1].raw.decode("utf-8", errors="replace"): role for n, role in roles.pairs.items()}


def test_builtin_pair_table() -> None:
    _s, codes = unity.tokenize("<b>x</b> <color=#f00>y</color> <sprite=1> <br> {0} <B>z</B> <space=4>")
    assert _pairs("unity", codes) == {
        "<b>": B_OPEN,
        "</b>": B_CLOSE,
        "<color=#f00>": C_OPEN,
        "</color>": C_CLOSE,
        "<B>": B_OPEN,
        "</B>": B_CLOSE,
        "<space=4>": ("space", "open"),
    }
    _s, codes = locres.tokenize('<Bold>x</> <img id="A"/> {0} <RichText.Emph>y</>')
    assert _pairs("unreal", codes) == {
        "<Bold>": ("", "open"),
        "</>": ("", "close"),
        "<RichText.Emph>": ("", "open"),
    }
    _s, codes = psbtext.tokenize("<b>a</b><br><size=0>b</size> #{color,FFFF00FF}%s#{color,clear} {x}")
    assert _pairs("psbtext", codes) == {
        "<b>": B_OPEN,
        "</b>": B_CLOSE,
        "<size=0>": ("size", "open"),
        "</size>": ("size", "close"),
    }
    _s, codes = srt.tokenize("<i>x</i> <font color=red>y</font> {\\an8}")
    assert _pairs("srt", codes) == {
        "<i>": ("i", "open"),
        "</i>": ("i", "close"),
        "<font color=red>": ("font", "open"),
        "</font>": ("font", "close"),
    }
    _s, codes = fmsb.tokenize("#c(12)a#/c @c(1)b@/c #s(0.8)c#/s #iyou#/i #bCAST#/b ^1/d^ #(56) %d <br> #w(40)")
    assert _pairs("fmsb", codes) == {
        "#c(12)": ("#c", "open"),
        "#/c": ("#c", "close"),
        "@c(1)": ("@c", "open"),
        "@/c": ("@c", "close"),
        "#s(0.8)": ("#s", "open"),
        "#/s": ("#s", "close"),
        "#i": ("#i", "open"),
        "#/i": ("#i", "close"),
        "#b": ("#b", "open"),
        "#/b": ("#b", "close"),
        "^1/": ("^", "open"),
        "^": ("^", "close"),
    }
    _s, codes = wadlin.tokenize("<CLT 4>a<CLT>")
    assert _pairs("wadlin", codes) == {"<CLT 4>": ("CLT", "open"), "<CLT>": ("CLT", "close")}
    declared = {p.name for p in registry.BUILTIN_PLUGINS if hasattr(p, "paired_code")}
    assert declared == {"unity", "unreal", "psbtext", "pakyc", "srt", "fmsb", "msbt", "nnitext", "wadlin"}


def test_nnitext_and_pakyc_pairs() -> None:
    plugin = NniTextPlugin()
    _s, codes = nnitext.tokenize("<color:0xffff3232>x<color:> <ext:17> <scale:1.3>%s")
    assert {c.raw: plugin.paired_code(c) for c in codes} == {
        b"<color:0xffff3232>": C_OPEN,
        b"<color:>": C_CLOSE,
        b"<ext:17>": None,
        b"<scale:1.3>": None,
        b"%s": None,
    }
    yc = PakYcPlugin()
    _s, codes = pakyc.tokenize("<f cn=a>Bob</f> <b action=attack></b> {v}")
    assert [yc.paired_code(c) for c in codes] == [("f", "open"), ("f", "close"), B_OPEN, B_CLOSE, None]


def test_msbt_pairs_come_from_explicit_closing_tags() -> None:
    plugin = MsbtPlugin()
    for encoding, endian in ((1, "<"), (1, ">"), (0, "<")):
        data = build_msbt(
            [("A", ["Get ", ("tag", 0, 3, b"\x00\x00"), "red", ("end", 0, 3, b""), " ", ("tag", 0, 4, b""), "x"])],
            encoding=encoding,
            endian=endian,
        )
        (entry,) = plugin.extract(data)
        roles = [plugin.paired_code(c) for c in entry.codes]
        assert roles == [("0:3", "open"), ("0:3", "close"), None]  # sayfa sonu çift değildir
    assert plugin.paired_code(ControlCode(b"\x0e\x00", "Oyun etiketi 2:7")) is None  # ham bayt tutmuyor


def test_plugin_without_pair_declaration_has_no_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    class UserPlugin:
        name = "kullanici"

        def movable_code(self, code: ControlCode) -> bool:
            return code.raw == b"{name}"

    monkeypatch.setattr(registry, "plugin_for_kind", lambda kind, title_id=None: UserPlugin())
    registry.reset_user_plugins()
    codes = (ControlCode(b"<b>", "Kalın"), ControlCode(b"</b>", "Kalın sonu"), ControlCode(b"{name}", "Ad"))
    try:
        roles = registry.free_codes("kullanici", codes)
        assert roles == frozenset({3})
        assert isinstance(roles, CodeRoles)
        assert roles.pairs == {}
    finally:
        registry.reset_user_plugins()


def test_plugin_declaring_only_pairs_is_asked_and_errors_are_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    class PairsOnly:
        name = "ciftler"

        def paired_code(self, code: ControlCode) -> tuple[str, str] | None:
            if code.raw == b"!":
                raise ValueError("bozuk")
            if code.raw == b"?":
                return ("x", "evet")  # bozuk yanıt (bilinmeyen rol): katı sayılır
            return ("b", "close" if code.raw.startswith(b"</") else "open")

    monkeypatch.setattr(registry, "plugin_for_kind", lambda kind, title_id=None: PairsOnly())
    registry.reset_user_plugins()
    codes = (
        ControlCode(b"<b>", "Kalın"),
        ControlCode(b"</b>", "Kalın sonu"),
        ControlCode(b"!", "?"),
        ControlCode(b"?", "?"),
    )
    try:
        assert registry.judges_codes("ciftler")
        roles = registry.free_codes("ciftler", codes)
        assert roles.pairs == {1: B_OPEN, 2: B_CLOSE}
    finally:
        registry.reset_user_plugins()


# --- eklentiler yeri değişen çifti yazar ----------------------------------------------------------


def _write_moved(plugin: FormatPlugin, data: bytes, key: str, move: Callable[[str], str]) -> None:
    """Değişikliksiz round-trip bayt bayt aynı; çifti taşınmış çeviri yazılır ve geri okunur."""
    entries = {e.key: e for e in plugin.extract(data)}
    assert plugin.inject(data, {k: e.source for k, e in entries.items()}) == data
    entry = entries[key]
    moved = move(entry.source)
    roles = registry.free_codes(plugin.name, entry.codes)
    found = placeholders.check(entry.source, moved, roles)
    assert not found.errors
    assert found.warnings == (placeholders.PAIR_REORDER_WARNING,)
    with placeholders.tolerate_reorder():
        out = plugin.inject(data, {key: moved})
    again = {e.key: e for e in plugin.extract(out)}[key]
    assert placeholders.renumber(again.source) == placeholders.renumber(moved)
    assert [again.codes[n - 1] for n in placeholders.tokens_in(again.source)] == [
        entry.codes[n - 1] for n in placeholders.tokens_in(moved)
    ]


def test_unity_writes_moved_pair() -> None:
    data = build_bundle([string_table("UI_en", "en", 99, [(1, "Press <b>A</b> to <color=red>jump</color>")])])
    plugin = UnityPlugin()
    key = plugin.extract(data)[0].key
    _write_moved(plugin, data, key, lambda s: "⟦3⟧Zıplamak⟦4⟧ için ⟦1⟧A⟦2⟧ basın")


def test_unreal_writes_moved_pair() -> None:
    data = build_locres([("Menu", "Hint", "Press <Bold>A</> to <Emph>jump</>"), ("Menu", "Other", "Plain")])
    _write_moved(LocresPlugin(), data, "Menu/Hint", lambda s: "⟦3⟧Zıplamak⟦4⟧ için ⟦1⟧A⟦2⟧ basın")


def test_psbtext_writes_moved_pair() -> None:
    data = build_psb({"message": {"Hint": {"eng": ["Press <b>A</b> to <size=24>jump</size>"]}}})
    plugin = PsbTextPlugin()
    key = plugin.extract(data)[0].key
    _write_moved(plugin, data, key, lambda s: "⟦3⟧Zıplamak⟦4⟧ için ⟦1⟧A⟦2⟧ basın")


def test_pakyc_writes_moved_pair() -> None:
    # Bu biçim çevrilen satırın bütün dil sütunlarını aynı metinle yazar; round-trip için sütunlar zaten aynı.
    data = ycd(table(UI_HEADER, [["hint"] + ["Press <w>A</w> to <s>jump</s>"] * len(LANGUAGES)]))
    plugin = PakYcPlugin()
    key = plugin.extract(data)[0].key
    _write_moved(plugin, data, key, lambda s: "⟦3⟧Atla⟦4⟧: ⟦1⟧A⟦2⟧")  # yerinde yazılır: özgünden kısa


def test_srt_writes_moved_pair() -> None:
    data = build_srt(cues=[("00:00:01,000 --> 00:00:02,000", "Press <i>A</i> to <b>jump</b>")])
    _write_moved(SrtPlugin(), data, "1", lambda s: "⟦3⟧Zıplamak⟦4⟧ için ⟦1⟧A⟦2⟧ basın")


def test_fmsb_writes_moved_pair() -> None:
    data = build_fmsb(["Press #c(12)A#/c to #s(0.8)jump#/s"])
    _write_moved(FmsbPlugin(), data, "0", lambda s: "⟦3⟧Zıplamak⟦4⟧ için ⟦1⟧A⟦2⟧ basın")


def test_msbt_writes_moved_pair() -> None:
    data = build_msbt(
        [
            (
                "Hint",
                [
                    "Press ",
                    ("tag", 0, 3, b"\x01\x00"),
                    "A",
                    ("end", 0, 3, b""),
                    " to ",
                    ("tag", 0, 2, b"\x02\x00"),
                    "jump",
                    ("end", 0, 2, b""),
                ],
            )
        ]
    )
    _write_moved(MsbtPlugin(), data, "Hint", lambda s: "⟦3⟧Zıplamak⟦4⟧ için ⟦1⟧A⟦2⟧ basın")


def test_nnitext_writes_moved_pair() -> None:
    data = build_xso(["Press <color:0xffff3232>A<color:> to <color:0xff3232ff>jump<color:>"])
    _write_moved(NniTextPlugin(), data, "0", lambda s: "⟦3⟧Zıplamak⟦4⟧ için ⟦1⟧A⟦2⟧ basın")


def test_wadlin_writes_moved_pair() -> None:
    data = build_lin(["<CLT 4>Press <CLT><CLT 3>A<CLT> to jump"])
    plugin = WadLinPlugin()
    key = plugin.extract(data)[0].key
    _write_moved(plugin, data, key, lambda s: "⟦3⟧A⟦4⟧ ile zıpla ⟦1⟧basın ⟦2⟧")


# --- proje ve dışa aktarma ------------------------------------------------------------------------

ARCHIVE = "Game_US.CPK"
SHEET = "MsgSheet/A.fms"
PATH = f"{ARCHIVE}>{SHEET}"
PAIR_TEXT = "Gold %d for #c(12)Red#/c"


def _project(*texts: str) -> tuple[Project, bytes]:
    sheet = build_fmsb(["##(START)", *texts])
    entries = tuple(FmsbPlugin().extract(sheet))
    project = Project.new()
    project.import_texts([ImportedFile(PATH, TID, "fmsb", "base", entries)])
    return project, build_cpk({SHEET: sheet})


def test_rows_carry_pairs_and_moved_pair_is_a_warning() -> None:
    project, _archive = _project(PAIR_TEXT)
    row = project.translation_rows()[0]
    assert placeholders.pairs_of(row.free_codes) == {2: ("#c", "open"), 3: ("#c", "close")}
    written = project.set_translations([(row.id, "⟦2⟧Kırmızı⟦3⟧ için altın ⟦1⟧")])[0]
    assert (written.status, written.note) == (Status.APPROVED, "")
    issues = check_row(written, "", "")
    assert [(i.kind, i.severity) for i in issues if i.kind in ("placeholder", "code_order")] == [
        ("code_order", "warning")
    ]
    assert project.set_translations([(row.id, "⟦3⟧Kırmızı⟦2⟧ için altın ⟦1⟧")])[0].status == Status.ERROR


def test_fix_does_not_put_a_moved_pair_back() -> None:
    project, _archive = _project(PAIR_TEXT)
    row = project.translation_rows()[0]
    project.set_translations([(row.id, "⟦2⟧Kırmızı⟦3⟧ için altın ⟦1⟧")])
    project._conn.execute("UPDATE text_entries SET status = ?, note = ? WHERE id = ?", (Status.ERROR, "eski", row.id))
    old = project.translation_rows()
    plan = plan_fixes(old, [i for r in old for i in check_row(r, "", "")], ["placeholder"])
    assert plan.changes == [(row.id, "⟦2⟧Kırmızı⟦3⟧ için altın ⟦1⟧")]


def test_export_writes_moved_pair_and_reads_back() -> None:
    project, archive = _project(PAIR_TEXT, "Plain line")
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["1"].id, "⟦2⟧Kırmızı⟦3⟧ için altın ⟦1⟧"), (rows["2"].id, "Düz satır")])
    rows_now = project.translation_rows()
    soft: dict[str, set[str]] = {}
    reordered: dict[str, set[str]] = {}
    translations, written, errors, untranslated = collect_translations(rows_now, "", soft=soft, reordered=reordered)
    assert reordered == {PATH: {"1"}}
    result = ExportResult(Path("x"), rows_written=written, rows_error=errors, rows_untranslated=untranslated)
    result.soft_keys = {p: frozenset(k) for p, k in soft.items()}
    result.reordered_keys = {p: frozenset(k) for p, k in reordered.items()}
    outputs = _export_member_archive(
        _tree({ARCHIVE: archive}),
        ARCHIVE,
        [TextFileRef(PATH, TID, "fmsb")],
        translations=translations,
        root=Path("romfs"),
        result=result,
    )
    settle_rows(result, rows_now, include_errors=False)
    sheet = cpk.CpkFile(MemoryStorage(outputs[0][1]), ARCHIVE).read(SHEET)
    assert "#c(12)Kırmızı#/c için altın %d".encode() in sheet
    assert result.rows_written == 2
    assert not result.dropped_keys.get(PATH)


def test_entries_type_is_unchanged() -> None:
    """Çift bildirimi `TextEntry`yi değiştirmez; kodların ham baytı ve etiketi yeterlidir (şema değişmez)."""
    entry = TextEntry("k", 0, "⟦1⟧a⟦2⟧", (ControlCode(b"<b>", "Kalın başı"), ControlCode(b"</b>", "Kalın sonu")))
    assert registry.free_codes("unity", entry.codes).pairs == {1: B_OPEN, 2: B_CLOSE}
