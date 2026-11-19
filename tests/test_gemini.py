"""Gemini (Google) sağlayıcısı: generateContent, ağsız (httpx.MockTransport) yanıtlarla."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from nxceviri.core.translate.providers.base import BatchItem, ProviderError
from nxceviri.core.translate.providers.gemini import GeminiProvider

KEY = "AIza-test-gizli"
ITEMS = [BatchItem("0", "Hello ⟦1⟧Kael⟦2⟧!"), BatchItem("1", "Bye")]


def _answer(text: str, finish: str = "STOP") -> dict[str, Any]:
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": finish}]}


GOOD = _answer(
    json.dumps({"translations": [{"id": "0", "text": "Merhaba ⟦1⟧Kael⟦2⟧!"}, {"id": "1", "text": "Hoşça kal"}]})
)


def _provider(
    handler: Callable[[httpx.Request], httpx.Response], model: str = "gemini-test"
) -> tuple[GeminiProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return GeminiProvider(KEY, model, client=httpx.Client(transport=httpx.MockTransport(record))), seen


def test_request_shape_and_parse() -> None:
    provider, seen = _provider(lambda r: httpx.Response(200, json=GOOD))
    results = provider.translate_batch(ITEMS, "en", "tr", "Korku oyunu.", [])
    assert [(r.id, r.text) for r in results] == [("0", "Merhaba ⟦1⟧Kael⟦2⟧!"), ("1", "Hoşça kal")]
    req = seen[0]
    assert str(req.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    assert req.headers["x-goog-api-key"] == KEY
    assert "key=" not in str(req.url)  # anahtar adreste değil başlıkta (günlüğe adres yazılabilir)
    body = json.loads(req.content)
    assert "Korku oyunu." in body["systemInstruction"]["parts"][0]["text"]
    assert body["contents"][0]["role"] == "user"
    assert json.loads(body["contents"][0]["parts"][0]["text"])["items"][0]["id"] == "0"
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert "additionalProperties" not in json.dumps(config["responseSchema"])
    assert config["responseSchema"]["required"] == ["translations"]


def test_model_name_with_prefix_is_accepted() -> None:
    provider, seen = _provider(lambda r: httpx.Response(200, json=GOOD), model="models/gemini-x")
    provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert seen[0].url.path == "/v1beta/models/gemini-x:generateContent"


def test_max_tokens_is_splittable() -> None:
    provider, _ = _provider(lambda r: httpx.Response(200, json=_answer('{"translations": [', "MAX_TOKENS")))
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.splittable
    assert exc.value.per_item


@pytest.mark.parametrize("finish", ["SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"])
def test_safety_stops_are_per_item(finish: str) -> None:
    provider, _ = _provider(lambda r: httpx.Response(200, json=_answer("", finish)))
    with pytest.raises(ProviderError, match="reddetti") as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.per_item
    assert not exc.value.retryable


def test_blocked_prompt_without_candidates_is_per_item() -> None:
    blocked = {"promptFeedback": {"blockReason": "SAFETY"}}
    provider, _ = _provider(lambda r: httpx.Response(200, json=blocked))
    with pytest.raises(ProviderError, match="reddetti") as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.per_item


@pytest.mark.parametrize("code", [401, 403])
def test_bad_key(code: int) -> None:
    body = {"error": {"code": code, "message": "API key not valid", "status": "PERMISSION_DENIED"}}
    provider, _ = _provider(lambda r: httpx.Response(code, json=body))
    with pytest.raises(ProviderError, match="API anahtarı geçersiz") as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert not exc.value.retryable


def test_invalid_key_reported_as_400_is_mapped_to_key_error() -> None:
    """Gemini geçersiz anahtarı 400 API_KEY_INVALID olarak bildirir."""
    body = {
        "error": {
            "code": 400,
            "message": "API key not valid. Please pass a valid API key.",
            "status": "INVALID_ARGUMENT",
            "details": [{"reason": "API_KEY_INVALID"}],
        }
    }
    provider, _ = _provider(lambda r: httpx.Response(400, json=body))
    with pytest.raises(ProviderError, match="API anahtarı geçersiz"):
        provider.translate_batch(ITEMS, "en", "tr", "", [])


@pytest.mark.parametrize("code", [429, 500, 503])
def test_rate_limit_and_server_errors_are_retryable(code: int) -> None:
    provider, _ = _provider(lambda r: httpx.Response(code, headers={"retry-after": "3"}, json={}))
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.retryable
    assert exc.value.retry_after_s == 3.0


def test_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("yavaş", request=request)

    provider, _ = _provider(handler)
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.retryable


def test_model_list_follows_pages_and_keeps_generate_models() -> None:
    pages = {
        "": {
            "models": [
                {"name": "models/gemini-b", "supportedGenerationMethods": ["generateContent", "countTokens"]},
                {"name": "models/embed-1", "supportedGenerationMethods": ["embedContent"]},
            ],
            "nextPageToken": "p2",
        },
        "p2": {"models": [{"name": "models/gemini-test", "supportedGenerationMethods": ["generateContent"]}]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1beta/models"
        return httpx.Response(200, json=pages[request.url.params.get("pageToken", "")])

    provider, _ = _provider(handler)
    assert provider.list_models() == ["gemini-b", "gemini-test"]
    assert provider.test_connection().ok
    other, _ = _provider(handler, model="gemini-yok")
    assert not other.test_connection().ok


def test_missing_key() -> None:
    with pytest.raises(ProviderError, match="API anahtarı girilmemiş"):
        GeminiProvider("", "gemini-test")


def test_key_never_leaks(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    provider, _ = _provider(lambda r: httpx.Response(403, json={"error": {"message": "denied"}}))
    status = provider.test_connection()
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    for text in (repr(provider), status.message, exc.value.user_text(), caplog.text):
        assert KEY not in text
