"""Çalıştırıcı, hizmetin `retry-after` ile istediği beklemeye uyar (sabit bekleme daha kısa olsa da)."""

from __future__ import annotations

from typing import Any

import pytest

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.progress import CancelToken, TaskContext
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.translate import runner as runner_module
from nxceviri.core.translate.providers.base import ProviderError
from nxceviri.core.translate.runner import MachineJob, run_machine_translation
from tests.fake_ollama import FakeOllama


def _project() -> Project:
    p = Project.new()
    entries = (TextEntry("A", 0, "Hello", ()), TextEntry("B", 1, "Bye", ()))
    p.import_texts([ImportedFile("Message/a.msbt", "0100", "msbt", "base", entries)])
    return p


@pytest.mark.parametrize(("retry_after", "expected"), [(9.0, 9.0), (None, 2.0), (0.5, 2.0)])
def test_retry_waits_for_retry_after(
    monkeypatch: pytest.MonkeyPatch, retry_after: float | None, expected: float
) -> None:
    monkeypatch.setattr(runner_module, "RETRY_DELAYS_S", (2.0, 6.0))
    project = _project()
    provider = FakeOllama().provider()
    real = provider.translate_batch
    failures = [ProviderError("çok istek", retryable=True, retry_after_s=retry_after)]

    def flaky(*args: Any, **kwargs: Any) -> Any:
        if failures:
            raise failures.pop()
        return real(*args, **kwargs)

    monkeypatch.setattr(provider, "translate_batch", flaky)
    waits: list[float] = []

    def fake_wait(_self: CancelToken, seconds: float) -> bool:
        waits.append(seconds)
        return False

    monkeypatch.setattr(CancelToken, "wait", fake_wait)
    rows = project.translation_rows()
    job = MachineJob(rows=rows, source_lang="en", memory=project.memory_lookup(r.source for r in rows))
    got: list[tuple[int, str]] = []
    run_machine_translation(provider, job, TaskContext(), got.extend)
    assert got
    assert waits == [expected]
