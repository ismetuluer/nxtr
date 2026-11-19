"""OpenAI uyumlu sohbet uç noktası (OpenAI, OpenRouter, Groq, Mistral, DeepSeek, LM Studio, özel adres).

Ağ kullanılmaz: istekler httpx.MockTransport ile yanıtlanır.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from nxceviri.core.translate.providers.base import BatchItem, ProviderError
from nxceviri.core.translate.providers.openai_compat import PRESETS, OpenAICompatProvider, preset

KEY = "sk-test-gizli-anahtar"
ITEMS = [BatchItem("0", "Hello ⟦1⟧Kael⟦2⟧!"), BatchItem("1", "Bye")]


def _answer(rows: list[dict[str, str]], finish: str = "stop", **message: Any) -> dict[str, Any]:
    content = json.dumps({"translations": rows}, ensure_ascii=False)
    return {"choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": content, **message}}]}


GOOD = _answer([{"id": "0", "text": "Merhaba ⟦1⟧Kael⟦2⟧!"}, {"id": "1", "text": "Hoşça kal"}])


def _provider(
    handler: Callable[[httpx.Request], httpx.Response], preset_id: str = "openai", key: str = KEY, **kw: Any
) -> tuple[OpenAICompatProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    return OpenAICompatProvider(preset_id, kw.pop("model", "gpt-test"), key, client=client, **kw), seen


def test_presets_have_expected_urls() -> None:
    urls = {p.id: p.base_url for p in PRESETS}
    assert urls["openai"] == "https://api.openai.com/v1"
    assert urls["openrouter"] == "https://openrouter.ai/api/v1"
    assert urls["groq"] == "https://api.groq.com/openai/v1"
    assert urls["mistral"] == "https://api.mistral.ai/v1"
    assert urls["deepseek"] == "https://api.deepseek.com/v1"
    assert urls["lmstudio"] == "http://localhost:1234/v1"
    assert not preset("lmstudio").needs_key
    assert not preset("openai_custom").needs_key
    assert preset("openai_custom").editable_url
    assert all(p.needs_key for p in PRESETS if p.id not in ("lmstudio", "openai_custom"))


def test_request_shape_and_parse() -> None:
    provider, seen = _provider(lambda r: httpx.Response(200, json=GOOD))
    results = provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert [(r.id, r.text) for r in results] == [("0", "Merhaba ⟦1⟧Kael⟦2⟧!"), ("1", "Hoşça kal")]
    req = seen[0]
    assert str(req.url) == "https://api.openai.com/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(req.content)
    assert body["model"] == "gpt-test"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema"
    schema = fmt["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["translations"]["items"]["additionalProperties"] is False
    assert fmt["json_schema"]["strict"] is True
    assert "temperature" not in body


def test_no_authorization_header_without_key() -> None:
    provider, seen = _provider(lambda r: httpx.Response(200, json=GOOD), "lmstudio", key="")
    provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert str(seen[0].url) == "http://localhost:1234/v1/chat/completions"
    assert "authorization" not in seen[0].headers


def test_custom_url_is_used() -> None:
    provider, seen = _provider(
        lambda r: httpx.Response(200, json=GOOD), "openai_custom", key="", base_url="http://sunucu:8000/v1/"
    )
    provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert str(seen[0].url) == "http://sunucu:8000/v1/chat/completions"


def test_missing_key_is_reported_before_any_request() -> None:
    with pytest.raises(ProviderError, match="API anahtarı girilmemiş"):
        OpenAICompatProvider("openai", "gpt-test", "")


def test_schema_unsupported_falls_back_to_json_object_then_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        fmt = (body.get("response_format") or {}).get("type")
        if fmt in ("json_schema", "json_object"):
            return httpx.Response(400, json={"error": {"message": f"response_format type {fmt} is not supported"}})
        return httpx.Response(200, json=GOOD)

    provider, seen = _provider(handler)
    results = provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert results[1].text == "Hoşça kal"
    kinds = [(json.loads(r.content).get("response_format") or {}).get("type") for r in seen]
    assert kinds == ["json_schema", "json_object", None]
    # Düşürülen biçim hatırlanır: sonraki istek doğrudan düz metinle gider.
    provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert "response_format" not in json.loads(seen[-1].content)


def test_other_400_is_not_a_format_fallback() -> None:
    provider, seen = _provider(lambda r: httpx.Response(400, json={"error": {"message": "model is required"}}))
    with pytest.raises(ProviderError, match="model is required") as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert not exc.value.retryable
    assert len(seen) == 1


def test_truncated_answer_is_splittable() -> None:
    provider, _ = _provider(lambda r: httpx.Response(200, json=_answer([], finish="length")))
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.splittable
    assert exc.value.per_item


@pytest.mark.parametrize("message", [{"refusal": "I can't help with that."}, {}])
def test_refusal_and_content_filter_are_per_item(message: dict[str, str]) -> None:
    finish = "stop" if message else "content_filter"
    provider, _ = _provider(lambda r: httpx.Response(200, json=_answer([], finish=finish, **message)))
    with pytest.raises(ProviderError, match="reddetti") as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.per_item
    assert not exc.value.retryable


@pytest.mark.parametrize("code", [401, 403])
def test_bad_key_is_clear_and_not_retried(code: int) -> None:
    provider, _ = _provider(lambda r: httpx.Response(code, json={"error": {"message": "Incorrect API key"}}))
    with pytest.raises(ProviderError, match="API anahtarı geçersiz") as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert not exc.value.retryable


def test_rate_limit_and_server_errors_are_retryable_with_retry_after() -> None:
    provider, _ = _provider(lambda r: httpx.Response(429, headers={"retry-after": "12"}, json={}))
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.retryable
    assert exc.value.retry_after_s == 12.0
    provider, _ = _provider(lambda r: httpx.Response(503, text="busy"))
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.retryable


def test_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("yavaş", request=request)

    provider, _ = _provider(handler)
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert exc.value.retryable


def test_model_list_and_connection_test() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "b-model"}, {"id": "gpt-test"}, {"id": "a-model"}]})

    provider, _ = _provider(handler)
    assert provider.list_models() == ["a-model", "b-model", "gpt-test"]
    status = provider.test_connection()
    assert status.ok
    assert "3 model" in status.message
    assert provider.last_models == ["a-model", "b-model", "gpt-test"]
    missing, _ = _provider(handler, model="yok")
    status = missing.test_connection()
    assert status.ok  # takma ad ya da listelenmeyen model olabilir: başlatmayı engellemez
    assert "'yok' listede görünmüyor" in status.message


def test_empty_model_asks_the_user_to_choose() -> None:
    provider, seen = _provider(lambda r: httpx.Response(200, json=GOOD), model="")
    with pytest.raises(ProviderError, match="Model seçilmedi"):
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    assert not seen


def test_key_never_leaks(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    provider, _ = _provider(lambda r: httpx.Response(401, json={"error": {"message": "bad"}}))
    status = provider.test_connection()
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch(ITEMS, "en", "tr", "", [])
    for text in (repr(provider), status.message, exc.value.user_text(), caplog.text):
        assert KEY not in text


def test_estimate_cost_has_no_price() -> None:
    provider, _ = _provider(lambda r: httpx.Response(200, json=GOOD))
    text = provider.estimate_cost(ITEMS)
    assert text is not None
    assert "belirteç" in text
