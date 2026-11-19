"""Sağlayıcı kataloğu: kimlikler, görünen adlar, anahtar adları ve sağlayıcının kurulması."""

from __future__ import annotations

import pytest

from nxceviri.core.secrets import DEEPL_API_KEY, api_key_name
from nxceviri.core.translate.origin import PROVIDER_NAMES, origin_label
from nxceviri.core.translate.providers.anthropic_claude import ClaudeProvider
from nxceviri.core.translate.providers.base import ProviderError
from nxceviri.core.translate.providers.catalog import SPECS, build_provider, spec
from nxceviri.core.translate.providers.deepl import DeepLProvider
from nxceviri.core.translate.providers.gemini import GeminiProvider
from nxceviri.core.translate.providers.google_translate import GoogleTranslateProvider
from nxceviri.core.translate.providers.ollama import OllamaProvider
from nxceviri.core.translate.providers.openai_compat import PRESETS, OpenAICompatProvider


def test_every_provider_has_a_name_and_a_distinct_key() -> None:
    ids = [s.id for s in SPECS]
    assert len(ids) == len(set(ids))
    assert {"ollama", "deepl", "anthropic", "gemini", "google_translate"} <= set(ids)
    assert {p.id for p in PRESETS} <= set(ids)
    for s in SPECS:
        assert PROVIDER_NAMES[s.id] == s.name
    keys = [api_key_name(s.id) for s in SPECS if s.needs_key or s.key_optional]
    assert len(keys) == len(set(keys))
    assert api_key_name("deepl") == DEEPL_API_KEY  # eski kayıtlı anahtar okunmaya devam eder


def test_classic_providers_cannot_follow_instructions() -> None:
    assert spec("deepl").classic
    assert spec("google_translate").classic
    assert not spec("anthropic").classic
    assert not spec("openrouter").classic
    assert spec("bilinmeyen").id == "ollama"


@pytest.mark.parametrize(
    ("provider_id", "kind"),
    [
        ("ollama", OllamaProvider),
        ("deepl", DeepLProvider),
        ("anthropic", ClaudeProvider),
        ("gemini", GeminiProvider),
        ("google_translate", GoogleTranslateProvider),
        ("openrouter", OpenAICompatProvider),
        ("lmstudio", OpenAICompatProvider),
    ],
)
def test_build_provider(provider_id: str, kind: type) -> None:
    provider = build_provider(provider_id, model="m", base_url="", api_key="anahtar")
    try:
        assert isinstance(provider, kind)
        assert provider.name == provider_id
    finally:
        provider.close()


def test_custom_url_and_missing_key() -> None:
    custom = build_provider("openai_custom", model="m", base_url="http://sunucu:9000/v1", api_key="")
    assert isinstance(custom, OpenAICompatProvider)
    assert custom.base_url == "http://sunucu:9000/v1"
    custom.close()
    with pytest.raises(ProviderError, match="API anahtarı girilmemiş"):
        build_provider("anthropic", model="m", base_url="", api_key="")


def test_origin_label_names_the_service() -> None:
    assert origin_label("openrouter", "x/y") == "OpenRouter (x/y)"
    assert origin_label("anthropic", "claude-opus-5-5") == "Claude (claude-opus-5-5)"
    assert origin_label("google_translate") == "Google Translate"
