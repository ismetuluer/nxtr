"""Sağlayıcı kataloğu: arayüzün sunduğu çeviri hizmetleri, özellikleri ve sağlayıcının kurulması.

Kimlik (`id`) ayarlarda ve satırın makine çevirisi kaynağında (`text_entries.mt_provider`) saklanır; değiştirilmez.
Arayüz bu kataloğa bakarak alanları gösterir (anahtar, adres, model listesi) ve klasik çeviri hizmetlerinde
(talimat izleyemeyen) redaksiyonu kapatır.
"""

from __future__ import annotations

from dataclasses import dataclass

from nxceviri.core.translate.providers.base import TranslationProvider
from nxceviri.core.translate.providers.deepl import DeepLProvider
from nxceviri.core.translate.providers.gemini import GeminiProvider
from nxceviri.core.translate.providers.google_translate import GoogleTranslateProvider
from nxceviri.core.translate.providers.ollama import DEFAULT_URL, OllamaProvider
from nxceviri.core.translate.providers.openai_compat import PRESETS, OpenAICompatProvider

#: Claude'un varsayılan modeli (alan düzenlenebilir); kitaplığı içe aktarmadan bilinsin diye burada da yazılı.
CLAUDE_DEFAULT_MODEL = "claude-opus-5-5"
#: OpenAI uyumlu hizmetlerin arayüzde tek seçenek olarak görünen grup kimliği (hizmet ayrı listeden seçilir).
OPENAI_GROUP = "openai_compat"


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    #: Kısa ad: durum çubuğu, satır ipucu ("Çeviren: …").
    name: str
    #: Seçim listesindeki açıklamalı ad.
    label: str
    needs_key: bool = False
    #: Anahtar isteğe bağlı (yerel ya da özel sunucu): alan gösterilir, boş bırakılabilir.
    key_optional: bool = False
    #: Talimat izleyemeyen klasik çeviri hizmeti (DeepL, Google Translate): redaksiyon sunulmaz.
    classic: bool = False
    #: Model listesi alınabilir ve model seçilir (yapay zekâ hizmetleri).
    has_models: bool = True
    #: Sunucu adresi kullanıcı tarafından değiştirilebilir.
    url_editable: bool = False
    default_url: str = ""
    default_model: str = ""
    #: OpenAI uyumlu hizmetlerden biri mi? (Arayüzde "OpenAI uyumlu" altında listelenir.)
    openai_compat: bool = False
    #: Metinler bilgisayardan çıkmaz.
    local: bool = False
    #: Anahtarın alındığı yer (ipucu).
    key_page: str = ""


SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        "ollama", "Ollama", "Ollama (yerel, ücretsiz)", url_editable=True, default_url=DEFAULT_URL, local=True
    ),
    ProviderSpec("deepl", "DeepL", "DeepL (bulut, kota kullanır)", needs_key=True, classic=True, has_models=False),
    ProviderSpec(
        "anthropic",
        "Claude",
        "Claude — Anthropic (bulut, ücretli)",
        needs_key=True,
        default_model=CLAUDE_DEFAULT_MODEL,
        key_page="platform.claude.com → API Keys",
    ),
    ProviderSpec(
        "gemini", "Gemini", "Gemini — Google (bulut)", needs_key=True, key_page="aistudio.google.com → API keys"
    ),
    *(
        ProviderSpec(
            p.id,
            p.label.removesuffix(" (OpenAI uyumlu)"),
            p.label,
            needs_key=p.needs_key,
            key_optional=not p.needs_key,
            url_editable=p.editable_url,
            default_url=p.base_url,
            openai_compat=True,
            local=p.id == "lmstudio",
            key_page=p.key_page,
        )
        for p in PRESETS
    ),
    ProviderSpec(
        "google_translate",
        "Google Translate",
        "Google Translate (bulut, kota kullanır)",
        needs_key=True,
        classic=True,
        has_models=False,
        key_page="Google Cloud Console → Kimlik Bilgileri",
    ),
)
_BY_ID = {s.id: s for s in SPECS}


def spec(provider_id: str) -> ProviderSpec:
    """Kimliğin özellikleri; bilinmeyen kimlik (eski/bozuk ayar) Ollama sayılır."""
    return _BY_ID.get(provider_id, SPECS[0])


def build_provider(provider_id: str, *, model: str, base_url: str, api_key: str) -> TranslationProvider:
    """Seçilen hizmetin sağlayıcısını kurar. Anahtar gerekip verilmemişse sağlayıcı Türkçe `ProviderError` verir."""
    chosen = spec(provider_id)
    if chosen.id == "deepl":
        return DeepLProvider(api_key)
    if chosen.id == "google_translate":
        return GoogleTranslateProvider(api_key)
    if chosen.id == "gemini":
        return GeminiProvider(api_key, model)
    if chosen.id == "anthropic":
        # Kitaplık (anthropic + pydantic) ilk içe aktarmada saniyeler sürüyor: uygulama açılışı yavaşlamasın diye
        # yalnızca Claude seçilince yüklenir.
        from nxceviri.core.translate.providers.anthropic_claude import ClaudeProvider  # noqa: PLC0415

        return ClaudeProvider(api_key, model or CLAUDE_DEFAULT_MODEL)
    if chosen.openai_compat:
        return OpenAICompatProvider(chosen.id, model, api_key, base_url=base_url or None)
    return OllamaProvider(model, base_url or DEFAULT_URL)
