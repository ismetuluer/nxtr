"""Zamanlayıcı çekirdeği: haftalık hücreler, JSON, etkin dilim, dilim sonu, sonraki başlangıç ve satır kapsamı."""

from __future__ import annotations

from datetime import datetime

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.report import job_kind
from nxceviri.core.translate.runner import ACTION_REVISE, ACTION_TRANSLATE
from nxceviri.core.translate.schedule import (
    HOURS,
    WEEKDAYS,
    Schedule,
    format_slot,
    scheduled_rows,
)
from nxceviri.core.translate.status import Status

# 2026-11-16 bir pazartesidir.
MON = datetime(2026, 11, 16)


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return MON.replace(day=16 + day, hour=hour, minute=minute)


def _row(rid: int, status: str, source: str = "Hello") -> TranslationRow:
    return TranslationRow(rid, "f.txt", f"k{rid}", source, "", status, "", (), None)


def test_week_shape() -> None:
    assert WEEKDAYS == 7
    assert HOURS == 24
    assert MON.weekday() == 0


def test_json_round_trip() -> None:
    s = Schedule(
        enabled=True,
        cells=frozenset({(0, 1), (6, 23)}),
        action=ACTION_REVISE,
        provider="anthropic",
        model="claude-x",
        base_url="",
        instruction="Kısa yaz.",
    )
    assert Schedule.load(s.dump()) == s
    assert "api" not in s.dump().lower()  # anahtar hiçbir zaman yazılmaz


def test_load_rejects_garbage() -> None:
    for text in ("", "{", "[]", "null", '{"cells": "x"}', '{"cells": [[9, 1]]}', '{"cells": [[0, 24]]}'):
        assert Schedule.load(text) is None, text
    assert Schedule.load('{"enabled": "evet"}') is None
    assert Schedule.load('{"action": "retranslate"}') is None


def test_load_fills_defaults() -> None:
    s = Schedule.load("{}")
    assert s == Schedule()
    assert not s.enabled
    assert s.action == ACTION_TRANSLATE


def test_active_at() -> None:
    s = Schedule(cells=frozenset({(0, 1), (0, 2)}))
    assert not s.active_at(_at(0, 0, 59))
    assert s.active_at(_at(0, 1))
    assert s.active_at(_at(0, 2, 59))
    assert not s.active_at(_at(0, 3))
    assert not s.active_at(_at(1, 1))


def test_slot_end_joins_adjacent_hours_across_midnight() -> None:
    s = Schedule(cells=frozenset({(2, 22), (2, 23), (3, 0), (3, 1)}))
    assert s.slot_start(_at(3, 0, 30)) == _at(2, 22)
    assert s.slot_end(_at(2, 22, 15)) == _at(3, 2)
    assert s.slot_end(_at(3, 1, 59)) == _at(3, 2)


def test_slot_wraps_sunday_to_monday() -> None:
    s = Schedule(cells=frozenset({(6, 23), (0, 0)}))
    sunday = _at(6, 23, 10)
    assert s.active_at(sunday)
    assert s.slot_end(sunday) == datetime(2026, 11, 23, 1)
    monday = _at(0, 0, 30)
    assert s.slot_start(monday) == datetime(2026, 11, 15, 23)
    assert s.slot_end(monday) == _at(0, 1)


def test_next_start() -> None:
    s = Schedule(cells=frozenset({(0, 1), (0, 2), (4, 20)}))
    assert s.next_start(_at(0, 0, 30)) == _at(0, 1)
    assert s.next_start(_at(0, 1, 30)) == _at(4, 20)  # içindeki dilimin başlangıcı geçti
    assert s.next_start(_at(5, 0)) == datetime(2026, 11, 23, 1)  # hafta başına sarar
    assert s.next_start(_at(0, 1)) == _at(4, 20)  # tam başlangıç anı "sonra" sayılmaz


def test_next_start_wraps_slot_across_week() -> None:
    s = Schedule(cells=frozenset({(6, 23), (0, 0)}))
    assert s.next_start(_at(2, 12)) == _at(6, 23)


def test_empty_and_full_week() -> None:
    empty = Schedule()
    assert not empty.active_at(MON)
    assert empty.next_start(MON) is None
    full = Schedule(cells=frozenset((d, h) for d in range(7) for h in range(24)))
    assert full.active_at(_at(3, 5))
    assert full.next_start(MON) is None  # hiç başlangıç yok: her zaman etkin
    assert full.slot_start(_at(3, 5)) == MON
    assert full.slot_end(_at(3, 5)) == datetime(2026, 11, 23)


def test_format_slot() -> None:
    assert format_slot(_at(0, 1)) == "Pzt 01:00"
    assert format_slot(_at(6, 23)) == "Paz 23:00"


def test_translate_scope_only_untranslated() -> None:
    rows = [
        _row(1, Status.UNTRANSLATED),
        _row(2, Status.ERROR),
        _row(3, Status.MACHINE),
        _row(4, Status.UNTRANSLATED, source="  "),
        _row(5, Status.APPROVED),
    ]
    assert [r.id for r in scheduled_rows(rows, ACTION_TRANSLATE, {})] == [1]


def test_revise_scope_skips_revised_and_human_rows() -> None:
    rows = [
        _row(1, Status.MACHINE),
        _row(2, Status.MACHINE),
        _row(3, Status.REDACTED),
        _row(4, Status.APPROVED),
        _row(5, Status.UNTRANSLATED),
        _row(6, Status.MACHINE),
        _row(7, Status.MACHINE, source=""),
    ]
    last = {1: "translate-2026-11-16T01:00:00", 2: "revise-2026-11-16T02:00:00", 6: "retranslate-x"}
    assert [r.id for r in scheduled_rows(rows, ACTION_REVISE, last)] == [1, 6]


def test_job_kind() -> None:
    assert job_kind("revise-2026-10-25T09:30:12") == "revise"
    assert job_kind("manual") == "manual"
    assert job_kind("") == ""
