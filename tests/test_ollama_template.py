"""Ollama: model şablonu denetimi (sistem metni düşüyor mu?) ve iş başına bağlam boyutu (`num_ctx`)."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from nxceviri.core.errors import NxError
from nxceviri.core.formats.base import TextEntry
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.translate import runner as runner_module
from nxceviri.core.translate.providers.base import BatchItem, ProviderError
from nxceviri.core.translate.providers.ollama import (
    MAX_NUM_CTX,
    MIN_NUM_CTX,
    choose_num_ctx,
    template_drops_system,
)
from nxceviri.core.translate.runner import MachineJob, run_machine_translation
from nxceviri.core.translate.status import Status
from tests.fake_ollama import FakeOllama

# Ollama kütüphanesindeki şablonlardan kısaltılmış örnekler.
GEMMA_TEMPLATE = """{{- range $i, $_ := .Messages }}
{{- $last := eq (len (slice $.Messages $i)) 1 }}
{{- if or (eq .Role "user") (eq .Role "system") }}<start_of_turn>user
{{ .Content }}<end_of_turn>
{{ if $last }}<start_of_turn>model
{{ end }}
{{- else if eq .Role "assistant" }}<start_of_turn>model
{{ .Content }}{{ if not $last }}<end_of_turn>
{{ end }}
{{- end }}
{{- end }}"""
LLAMA_TEMPLATE = """{{- if or .System .Tools }}<|start_header_id|>system<|end_header_id|>

{{ .System }}<|eot_id|>
{{- end }}
{{- range .Messages }}<|start_header_id|>{{ .Role }}<|end_header_id|>

{{ .Content }}<|eot_id|>
{{- end }}"""
# GGUF'tan gelen Jinja şablonu (kısaltılmış).
JINJA_TEMPLATE = (
    "{%- if messages and messages[0]['role'] in ['system', 'developer'] -%}"
    "{{- '<|turn>system\\n' -}}{{- messages[0]['content'] -}}{%- endif -%}"
)
OLD_STYLE_TEMPLATE = "{{ if .System }}<|system|>{{ .System }}{{ end }}<|user|>{{ .Prompt }}<|assistant|>"


@pytest.mark.parametrize(
    ("template", "drops"),
    [
        ("{{ .Prompt }}", True),
        ("  {{ .Prompt }}\n", True),
        ("", True),
        ("   ", True),
        (GEMMA_TEMPLATE, False),
        (LLAMA_TEMPLATE, False),
        (OLD_STYLE_TEMPLATE, False),
        (JINJA_TEMPLATE, False),
        ("{{ prompt }}", True),
        ("{{ .System }}{{ .Prompt }}", False),
        ("{{ range .Messages }}{{ .Content }}{{ end }}", False),
        ("{{ .Systemic }}{{ .Prompt }}", True),
    ],
)
def test_template_drops_system(template: str, drops: bool) -> None:
    assert template_drops_system(template) is drops


def _show_server(template: str | None, **kw: Any) -> FakeOllama:
    server = FakeOllama(**kw)
    if template is not None:
        server.templates["gemma4:12b"] = template
    return server


def _payload_of(request: dict[str, Any]) -> dict[str, Any]:
    content = request["messages"][-1]["content"]
    if len(request["messages"]) == 1:
        content = content.rsplit("\n\nInput:\n", 1)[1]
    payload: dict[str, Any] = json.loads(content)
    return payload


def test_system_text_is_prepended_when_template_drops_it() -> None:
    server = _show_server("{{ .Prompt }}")
    provider = server.provider()
    res = provider.translate_batch([BatchItem("0", "Start")], "en", "tr", "Oyun: korku.", [])
    assert [r.text for r in res] == ["tr-Start"]
    (request,) = server.requests
    assert len(request["messages"]) == 1
    assert request["messages"][0]["role"] == "user"
    content = request["messages"][0]["content"]
    assert content.startswith("Instructions:\n")
    assert "Oyun: korku." in content  # oyun notu modele ulaşıyor
    assert "Strict rules" in content
    assert _payload_of(request)["items"] == [{"id": "0", "text": "Start"}]  # JSON bozulmadı


def test_system_message_is_kept_when_template_uses_it() -> None:
    server = _show_server(GEMMA_TEMPLATE)
    provider = server.provider()
    provider.translate_batch([BatchItem("0", "Start")], "en", "tr", "", [])
    (request,) = server.requests
    assert [m["role"] for m in request["messages"]] == ["system", "user"]


def test_system_message_is_kept_when_template_unknown() -> None:
    """Eski Ollama /api/show'da şablon alanı döndürmezse sistem mesajı olduğu gibi gider."""
    server = _show_server(None)
    server.provider().translate_batch([BatchItem("0", "Start")], "en", "tr", "", [])
    assert [m["role"] for m in server.requests[0]["messages"]] == ["system", "user"]


def test_show_is_read_once_per_model_and_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    server = _show_server("{{ .Prompt }}")
    provider = server.provider()
    with caplog.at_level(logging.INFO):
        for _ in range(3):
            provider.translate_batch([BatchItem("0", "Start")], "en", "tr", "", [])
    assert server.show_calls == ["gemma4:12b"]
    assert sum("şablon" in r.getMessage() for r in caplog.records) == 1


def test_connection_warns_when_template_drops_system() -> None:
    status = _show_server("{{ .Prompt }}").provider().test_connection()
    assert status.ok
    assert "şablonu sistem talimatını yok sayıyor" in status.message
    assert "kullanıcı mesajına eklenecek" in status.message
    ok = _show_server(GEMMA_TEMPLATE).provider().test_connection()
    assert ok.ok
    assert "yok sayıyor" not in ok.message


def test_list_models_reports_template_and_context_length() -> None:
    server = _show_server("{{ .Prompt }}", context_lengths={"gemma4:12b": 131072})
    (model,) = [m for m in server.provider().list_models() if m.can_chat]
    assert model.template_drops_system
    assert model.context_length == 131072
    other = _show_server(GEMMA_TEMPLATE).provider().list_models()[0]
    assert not other.template_drops_system
    assert other.context_length is None


# --- bağlam boyutu --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("chars", "ctx_len", "expected"),
    [
        (0, None, 8192),
        (3000, None, 8192),  # (1000 + 3072) * 1,15 ≈ 4684
        (6000, None, 8192),  # (2000 + 3072) * 1,15 ≈ 5833
        (15000, None, 16384),  # ≈ 9283
        (40000, None, 24576),  # ≈ 18867
        (75000, None, 32768),  # ≈ 32283: sınıra sığıyor
        (15000, 12288, 12288),  # yuvarlanmış değer modelin sınırını aşmaz
        (3000, 4096 * 4, 8192),
    ],
)
def test_choose_num_ctx(chars: int, ctx_len: int | None, expected: int) -> None:
    assert choose_num_ctx(chars, ctx_len) == expected


def test_choose_num_ctx_bounds_constants() -> None:
    assert (MIN_NUM_CTX, MAX_NUM_CTX) == (8192, 32768)


def test_choose_num_ctx_errors_when_prompt_does_not_fit() -> None:
    with pytest.raises(ProviderError) as exc:
        choose_num_ctx(80000, None)
    assert not exc.value.retryable
    assert "çok uzun" in exc.value.message
    assert "kısaltın" in exc.value.hint
    assert "karakter" in exc.value.hint
    # Modelin kendi sınırı daha küçükse ona göre hata verir.
    with pytest.raises(ProviderError, match="çok uzun"):
        choose_num_ctx(15000, 8192)


def test_excess_in_error_is_positive_and_roughly_exact() -> None:
    with pytest.raises(ProviderError) as exc:
        choose_num_ctx(90000, None)
    digits = "".join(ch for ch in exc.value.hint.split("yaklaşık ")[1].split(" karakter")[0] if ch.isdigit())
    assert 13000 < int(digits) < 14500  # 90000 - ~76300 (sığan en çok karakter) ≈ 13700


# --- iş içinde -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "RETRY_DELAYS_S", (0.0, 0.0))


def _project(count: int = 30) -> Project:
    p = Project.new()
    entries = tuple(TextEntry(f"k{i}", i, f"Line number {i}", ()) for i in range(count))
    p.import_texts([ImportedFile("Message/a.msbt", "0100", "msbt", "base", entries)])
    return p


def _job(project: Project, **kw: Any) -> MachineJob:
    rows = [r for r in project.translation_rows() if r.status == Status.UNTRANSLATED]
    return MachineJob(rows=rows, source_lang="en", **kw)


def _run(server: FakeOllama, project: Project, **kw: Any) -> None:
    def write(results: list[tuple[int, str]]) -> None:
        project.set_translations(results, machine=True)

    run_machine_translation(server.provider(), _job(project, **kw), TaskContext(), write)


def test_num_ctx_is_fixed_for_the_whole_job_and_default_is_8192() -> None:
    server = FakeOllama(break_texts={"Line number 3": 1})  # yeniden deneme de aynı değeri kullanmalı
    _run(server, _project())
    sizes = {r["options"]["num_ctx"] for r in server.requests}
    assert len(server.requests) > 2
    assert sizes == {8192}


def test_num_ctx_grows_with_long_notes_and_stays_constant() -> None:
    server = FakeOllama(break_texts={"Line number 3": 1})
    notes = "Oyun notu. " * 1500  # ≈ 16.500 karakter → 16384
    _run(server, _project(), notes=notes)
    assert {r["options"]["num_ctx"] for r in server.requests} == {16384}


def test_num_ctx_respects_model_context_length() -> None:
    server = FakeOllama(context_lengths={"gemma4:12b": 12288})
    _run(server, _project(), notes="x" * 12000)  # gereken 16384 olurdu; modelin sınırı 12288
    assert {r["options"]["num_ctx"] for r in server.requests} == {12288}


def test_job_fails_before_any_request_when_notes_are_too_long() -> None:
    server = FakeOllama()
    with pytest.raises(NxError) as exc:
        _run(server, _project(), notes="x" * 120_000)
    assert "çok uzun" in exc.value.message
    assert "kısaltın" in exc.value.hint
    assert server.requests == []  # iş başlamadı, hiçbir parti gönderilmedi


def test_num_ctx_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        _run(FakeOllama(), _project(5))
    assert any("num_ctx" in r.getMessage() and "8192" in r.getMessage() for r in caplog.records)


def test_num_ctx_rises_if_a_batch_is_longer_than_planned_and_errors_beyond_the_limit() -> None:
    server = FakeOllama()
    provider = server.provider()
    provider.translate_batch([BatchItem("0", "Start")], "en", "tr", "", [])
    assert server.requests[-1]["options"]["num_ctx"] == 8192
    provider.translate_batch([BatchItem("0", "x" * 40_000)], "en", "tr", "", [])  # hazırlıksız çağrı: istemine göre
    assert server.requests[-1]["options"]["num_ctx"] == 24576
    with pytest.raises(ProviderError, match="çok uzun"):
        provider.translate_batch([BatchItem("0", "x" * 90_000)], "en", "tr", "", [])
