"""Claude (Anthropic) sağlayıcısı: resmî kitaplık, ağsız (httpx2.MockTransport) yanıtlarla."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from nxceviri.core.translate.providers.anthropic_claude import DEFAULT_MODEL, FALLBACK_BETA, ClaudeProvider
from nxceviri.core.translate.providers.base import BatchItem, ProviderError

KEY = "sk-ant-test-gizli"
ITEMS = [BatchItem("0", "Hello ⟦1⟧Kael⟦2⟧!"), BatchItem("1", "Bye")]


def _message(text: str, stop: str = "end_turn", details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": DEFAULT_MODEL,
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop,
        "stop_details": details,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


GOOD = _message(
    json.dumps({"translations": [{"id": "0", "text": "Merhaba ⟦1⟧Kael⟦2⟧!"}, {"id": "1", "text": "Hoşça kal"}]})
)


def _provider(
    handler: Callable[[httpx2.Request], httpx2.Response], **kw: Any
) -> tuple[ClaudeProvider, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)

    client = httpx2.Client(transport=httpx2.MockTransport(record))
    return ClaudeProvider(KEY, http_client=client, **kw), seen


def _error(code: int, headers: dict[str, str] | None = None) -> Callable[[httpx2.Request], httpx2.Response]:
    body = {"type": "error", "error": {"type": "x", "message": "hata ayrıntısı"}}
    return lambda r: httpx2.Response(code, json=body, headers=headers or {})


def test_request_shape_and_parse() -> None:
    provider, seen = _provider(lambda r: httpx2.Response(200, json=GOOD))
    results = provider.translate_batch(ITEMS, "en", "tr", "Korku oyunu.", [])
    assert [(r.id, r.text) for r in results] == [("0", "Merhaba ⟦1⟧Kael⟦2⟧!"), ("1", "Hoşça kal")]
    assert len(seen) == 1
    req = seen[0]
    assert req.url.path == "/v1/messages"
    # Kitaplığın 2.x sürümü anahtarı Bearer olarak gönderir (eski sürümler x-api-key kullanırdı).
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert FALLBACK_BETA in req.headers["anthropic-beta"]
    body = json.loads(req.content)
    assert body["model"] == "claude-opus-5-5"
    assert body["max_tokens"] == 16000
    assert "Korku oyunu." in body["system"]
    assert [m["role"] for m in body["messages"]] == ["user"]
    assert body["fallbacks"] == "default"
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["additionalProperties"] is False
    assert fmt["schema"]["properties"]["translations"]["items"]["required"] == ["id", "text"]
    for unwanted in ("temperature", "top_p", "top_k", "thinking"):
        assert unwanted not in body


def test_max_tokens_is_splittable() -> None:
    provider, _ = _provider(lambda r: httpx2.Response(200, json=_message('{"translations": [', "max_tokens")))
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.splittable
    assert exc.value.per_item


def test_refusal_is_per_item() -> None:
    provider, _ = _provider(lambda r: httpx2.Response(200, json=_message("", "refusal", {"category": None})))
    with pytest.raises(ProviderError, match="Model bu satırları çevirmeyi reddetti") as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.per_item
    assert not exc.value.retryable


@pytest.mark.parametrize("code", [401, 403])
def test_bad_key(code: int) -> None:
    provider, seen = _provider(_error(code))
    with pytest.raises(ProviderError, match="API anahtarı geçersiz") as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert not exc.value.retryable
    assert len(seen) == 1  # kitaplık kendi başına yeniden denemez


@pytest.mark.parametrize("code", [429, 500, 529])
def test_rate_limit_and_overload_are_retryable(code: int) -> None:
    provider, seen = _provider(_error(code, {"retry-after": "4"}))
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.retryable
    assert exc.value.retry_after_s == 4.0
    assert len(seen) == 1


def test_timeout_and_connection_errors_are_retryable() -> None:
    def timeout(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("yavaş", request=request)

    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("yok", request=request)

    for handler, words in ((timeout, "zamanında"), (down, "bağlanılamadı")):
        provider, _ = _provider(handler)
        with pytest.raises(ProviderError, match=words) as exc:
            provider.translate_batch(ITEMS, "en", "tr", "", [])
        assert exc.value.retryable


def test_model_list_and_connection() -> None:
    page = {
        "data": [
            {"id": "claude-opus-5-5", "type": "model", "display_name": "Opus", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "claude-a", "type": "model", "display_name": "A", "created_at": "2026-01-01T00:00:00Z"},
        ],
        "has_more": False,
        "first_id": "claude-opus-5-5",
        "last_id": "claude-a",
    }
    provider, seen = _provider(lambda r: httpx2.Response(200, json=page))
    assert provider.list_models() == ["claude-a", "claude-opus-5-5"]
    assert seen[0].url.path == "/v1/models"
    assert provider.test_connection().ok
    other, _ = _provider(lambda r: httpx2.Response(200, json=page), model="claude-yok")
    status = other.test_connection()
    assert status.ok  # takma ad listede olmayabilir: başlatmayı engellemez
    assert "'claude-yok' listede görünmüyor" in status.message
    assert other.last_models == ["claude-a", "claude-opus-5-5"]


def test_missing_key() -> None:
    with pytest.raises(ProviderError, match="API anahtarı girilmemiş"):
        ClaudeProvider("  ")


def test_key_never_leaks(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    provider, _ = _provider(_error(401))
    status = provider.test_connection()
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    for text in (repr(provider), status.message, exc.value.user_text(), caplog.text):
        assert KEY not in text
