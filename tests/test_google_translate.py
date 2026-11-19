"""Google Translate (Cloud Translation Basic v2): klasik makine çevirisi, yer tutucu koruması, ağsız yanıtlar."""

from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Callable

import httpx
import pytest

from nxceviri.core.translate.providers.base import BatchItem, ProviderError, Scene
from nxceviri.core.translate.providers.google_translate import GoogleTranslateProvider, google_lang

KEY = "AIza-gt-gizli"


def _echo_upper(request: httpx.Request) -> httpx.Response:
    """Etiketlere dokunmadan metni büyük harfe çeviren sahte hizmet (Google gibi ' karakterini kaçışlar)."""
    body = json.loads(request.content)
    out = []
    for q in body["q"]:
        text = re.sub(r"(^|>)([^<]*)", lambda m: m.group(1) + m.group(2).upper(), q)
        out.append({"translatedText": text.replace("'", "&#39;")})
    return httpx.Response(200, json={"data": {"translations": out}})


def _provider(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[GoogleTranslateProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return GoogleTranslateProvider(KEY, client=httpx.Client(transport=httpx.MockTransport(record))), seen


def test_request_shape_and_placeholder_protection() -> None:
    provider, seen = _provider(_echo_upper)
    items = [BatchItem("0", "Hi ⟦1⟧Kael⟦2⟧ & <you>"), BatchItem("1", "Line one\nline two"), BatchItem("2", "it's")]
    results = provider.translate_batch(items, "en", "tr", "notlar", [])
    assert [r.text for r in results] == ["HI ⟦1⟧KAEL⟦2⟧ & <YOU>", "LINE ONE\nLINE TWO", "IT'S"]
    req = seen[0]
    assert str(req.url) == "https://translation.googleapis.com/language/translate/v2"
    assert req.headers["x-goog-api-key"] == KEY
    assert "key=" not in str(req.url)
    body = json.loads(req.content)
    assert body["source"] == "en"
    assert body["target"] == "tr"
    assert body["format"] == "html"
    assert body["q"][0] == 'Hi <x id="1"/>Kael<x id="2"/> &amp; &lt;you&gt;'
    assert "\n" not in body["q"][1]  # HTML kipinde satır sonu yutulur: etiketle korunur
    assert html.unescape(body["q"][2]) == "it's"


def test_language_codes() -> None:
    assert google_lang("en") == "en"
    assert google_lang("pt-BR") == "pt"
    assert google_lang("zh") == "zh-CN"
    assert google_lang("zh-Hant") == "zh-TW"
    assert google_lang("JA") == "ja"


def test_classic_mt_flags_and_revision_is_refused() -> None:
    provider, seen = _provider(_echo_upper)
    assert not provider.supports_instructions
    assert not provider.supports_glossary
    assert provider.max_batch_items <= 128
    with pytest.raises(ProviderError, match="redaksiyon"):
        provider.translate_batch([BatchItem("0", "x", current="y")], "en", "tr", "", [], scene=Scene(revise=True))
    assert not seen


def test_wrong_count_is_retryable() -> None:
    provider, _ = _provider(lambda r: httpx.Response(200, json={"data": {"translations": []}}))
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch([BatchItem("0", "x")], "en", "tr", "", [])
    assert exc.value.retryable


def test_bad_key_reported_as_400_and_403() -> None:
    invalid: dict[str, object] = {
        "error": {"code": 400, "message": "API key not valid.", "errors": [{"reason": "keyInvalid"}]}
    }
    forbidden: dict[str, object] = {"error": {"code": 403, "message": "forbidden"}}
    for code, body in ((400, invalid), (403, forbidden)):

        def handler(_r: httpx.Request, c: int = code, b: dict[str, object] = body) -> httpx.Response:
            return httpx.Response(c, json=b)

        provider, _ = _provider(handler)
        with pytest.raises(ProviderError, match="API anahtarı geçersiz") as exc:
            provider.translate_batch([BatchItem("0", "x")], "en", "tr", "", [])
        assert not exc.value.retryable


def test_rate_limit_is_retryable() -> None:
    provider, _ = _provider(lambda r: httpx.Response(429, headers={"retry-after": "5"}, json={}))
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch([BatchItem("0", "x")], "en", "tr", "", [])
    assert exc.value.retryable
    assert exc.value.retry_after_s == 5.0


def test_connection_uses_language_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/language/translate/v2/languages"
        return httpx.Response(200, json={"data": {"languages": [{"language": "tr"}, {"language": "en"}]}})

    provider, _ = _provider(handler)
    status = provider.test_connection()
    assert status.ok
    assert "Google Translate" in status.message


def test_estimate_is_character_count() -> None:
    provider, _ = _provider(_echo_upper)
    text = provider.estimate_cost([BatchItem("0", "abcd"), BatchItem("1", "ef")])
    assert text is not None
    assert "6 karakter" in text


def test_missing_key_and_no_leak(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ProviderError, match="API anahtarı girilmemiş"):
        GoogleTranslateProvider("")
    caplog.set_level(logging.DEBUG)
    provider, _ = _provider(lambda r: httpx.Response(403, json={"error": {"message": "denied"}}))
    status = provider.test_connection()
    for text in (repr(provider), status.message, caplog.text):
        assert KEY not in text
