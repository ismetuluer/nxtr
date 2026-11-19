"""Sağlayıcıdan bağımsız büyük dil modeli mantığı (`providers/llm.py`): istem, yanıt okuma, hata eşlemesi."""

from __future__ import annotations

import json
from typing import Any

import pytest

from nxceviri.core.translate.providers import ollama
from nxceviri.core.translate.providers.base import BatchItem, ProviderError
from nxceviri.core.translate.providers.llm import (
    RESPONSE_SCHEMA,
    LLMProvider,
    build_messages,
    extract_translations,
    parse_retry_after,
    split_system,
    status_error,
    strict_schema,
    strip_schema_keys,
)


class _Echo(LLMProvider):
    """`chat_json`'u verilen metni döndüren en küçük LLM sağlayıcısı."""

    name = "echo"
    label = "Echo"

    def __init__(self, answer: str) -> None:
        self.model = "m"
        self.answer = answer
        self.calls: list[list[dict[str, str]]] = []

    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        self.calls.append(messages)
        return self.answer

    def close(self) -> None:
        self.calls.clear()


def test_ollama_reuses_the_shared_prompt_logic() -> None:
    assert ollama.build_messages is build_messages
    assert ollama.extract_translations is extract_translations
    assert issubclass(ollama.OllamaProvider, LLMProvider)


def test_translate_batch_parses_rows_and_reports_missing() -> None:
    provider = _Echo(json.dumps({"translations": [{"id": "0", "text": "Merhaba"}]}))
    items = [BatchItem("0", "Hello"), BatchItem("1", "Bye")]
    results = provider.translate_batch(items, "en", "tr", "", [])
    assert [(r.id, r.text) for r in results] == [("0", "Merhaba"), ("1", None)]
    assert results[1].error
    assert provider.calls[0][0]["role"] == "system"


def test_unreadable_answer_is_retryable_and_per_item() -> None:
    with pytest.raises(ProviderError) as exc:
        _Echo("Üzgünüm, yapamam.").translate_batch([BatchItem("0", "Hello")], "en", "tr", "", [])
    assert exc.value.retryable
    assert exc.value.per_item


def test_estimate_cost_is_a_token_estimate_without_prices() -> None:
    text = _Echo("").estimate_cost([BatchItem("0", "Hello world " * 10)])
    assert text is not None
    assert "belirteç" in text
    assert "$" not in text
    assert "€" not in text


def test_split_system_joins_system_messages() -> None:
    system, rest = split_system(
        [{"role": "system", "content": "a"}, {"role": "system", "content": "b"}, {"role": "user", "content": "u"}]
    )
    assert system == "a\n\nb"
    assert rest == [{"role": "user", "content": "u"}]


def test_strict_schema_closes_every_object_and_keeps_the_original() -> None:
    strict = strict_schema(RESPONSE_SCHEMA)
    assert strict["additionalProperties"] is False
    row = strict["properties"]["translations"]["items"]
    assert row["additionalProperties"] is False
    assert row["required"] == ["id", "text"]
    assert "additionalProperties" not in RESPONSE_SCHEMA


def test_strip_schema_keys_removes_unsupported_keys_everywhere() -> None:
    stripped = strip_schema_keys(strict_schema(RESPONSE_SCHEMA), {"additionalProperties"})
    assert "additionalProperties" not in json.dumps(stripped)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("3", 3.0), ("1.5", 1.5), (None, None), ("", None), ("yarın", None), ("-2", None)],
)
def test_parse_retry_after(value: str | None, expected: float | None) -> None:
    assert parse_retry_after(value) == expected


def test_status_error_mapping() -> None:
    for code in (401, 403):
        err = status_error("Servis", code, "invalid key")
        assert not err.retryable
        assert "API anahtarı geçersiz" in err.message
    limited = status_error("Servis", 429, "", retry_after_s=7.0)
    assert limited.retryable
    assert limited.retry_after_s == 7.0
    for code in (500, 503, 529):
        assert status_error("Servis", code, "").retryable
    bad = status_error("Servis", 400, "bad things")
    assert not bad.retryable
    assert "bad things" in bad.message
