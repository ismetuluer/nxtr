"""Denetimin ilerleme geri çağrısı: gerçek ilerleme (denetlenen / toplam), tek yönlü, iptal edilebilir."""

from __future__ import annotations

import pytest

from nxceviri.core.errors import OperationCancelled
from nxceviri.core.progress import CancelToken, TaskContext
from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import run_checks
from nxceviri.core.translate.status import Status


def _rows(count: int) -> list[TranslationRow]:
    return [
        TranslationRow(i, "f", f"k{i}", f"Line {i} ", f"Satır {i}", Status.MACHINE, "", (), None)
        for i in range(1, count + 1)
    ]


def test_progress_is_monotonic_and_reaches_the_total() -> None:
    seen: list[tuple[int, int]] = []
    run_checks(_rows(200), "", "", progress=lambda done, total, _message: seen.append((done, total)))
    assert seen
    assert len({total for _done, total in seen}) == 1
    dones = [done for done, _total in seen]
    assert dones == sorted(dones)
    assert dones[-1] == seen[-1][1]
    assert dones[0] < dones[-1]


def test_progress_does_not_change_the_result() -> None:
    rows = _rows(50)
    plain = run_checks(rows, "", "")
    with_progress = run_checks(rows, "", "", progress=lambda *_a: None)
    assert [(i.row_id, i.kind) for i in with_progress] == [(i.row_id, i.kind) for i in plain]


def test_empty_rows_report_nothing_wrong() -> None:
    seen: list[tuple[int, int]] = []
    assert run_checks([], "", "", progress=lambda done, total, _m: seen.append((done, total))) == []
    assert all(done <= total for done, total in seen)


def test_cancel_through_task_context_stops_the_loop() -> None:
    token = CancelToken()
    ctx = TaskContext(token=token)
    checked: list[int] = []

    def progress(done: int, total: int, message: str) -> None:
        checked.append(done)
        if done >= 10:
            token.cancel()
        ctx.report(done, total, message)

    with pytest.raises(OperationCancelled):
        run_checks(_rows(500), "", "", progress=progress)
    assert max(checked) < 500  # iptal edilince kalan satırlar denetlenmedi
