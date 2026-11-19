"""Claude (Anthropic) sağlayıcısı: resmî `anthropic` Python kitaplığıyla Messages API.

- Çeviri `client.beta.messages.create` ile istenir: yanıt biçimi yapılandırılmış çıktıyla
  (`output_config.format`, katı JSON şeması) zorlanır; sunucu tarafı yedek model (`fallbacks="default"`,
  `server-side-fallback-2026-07-01` betası) açıktır: model içerik politikası yüzünden yanıt vermezse aynı istek
  sunucuda yedek modelle denenir.
- Sıcaklık, top_p/top_k ve düşünme bütçesi gönderilmez (modelin varsayılanları kullanılır).
- Yanıtın içeriği okunmadan önce `stop_reason` denetlenir: `max_tokens` → parti bölünür; `refusal` → o satır atlanır.
- Kitaplığın kendi yeniden denemesi kapalıdır (`max_retries=0`): çalıştırıcı (`runner`) yeniden denemeyi zaten
  yapıyor ve `retry-after` beklemesine uyuyor; ikisi birden olunca bir parti 2×3 kez gönderilirdi.
- Model listesi `client.models.list()` ile alınır.

API anahtarı hiçbir koşulda loglanmaz, hata mesajına veya `repr`'e yazılmaz.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic
import httpx2

from nxceviri.core.translate.providers.base import ProviderError, ProviderStatus
from nxceviri.core.translate.providers.llm import (
    LLMProvider,
    connect_error,
    parse_retry_after,
    refusal_error,
    split_system,
    status_error,
    strict_schema,
    timeout_error,
    truncated_error,
    unlisted_model_note,
)

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
SERVICE = "Claude (Anthropic)"


class ClaudeProvider(LLMProvider):
    name = "anthropic"
    label = SERVICE

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        timeout_s: float = 300.0,
        http_client: httpx2.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderError(
                "Claude API anahtarı girilmemiş.",
                "Otomatik Çeviri penceresinde anahtarı yapıştırıp kaydedin (anahtar: platform.claude.com → API Keys).",
            )
        self.model = model.strip() or DEFAULT_MODEL
        self._client = anthropic.Anthropic(
            api_key=api_key.strip(), max_retries=0, timeout=timeout_s, http_client=http_client
        )
        #: Son bağlantı testinde alınan model listesi.
        self.last_models: list[str] = []

    def __repr__(self) -> str:
        return f"<ClaudeProvider {self.model}>"

    def close(self) -> None:
        self._client.close()

    def list_models(self) -> list[str]:
        try:
            return sorted((m.id for m in self._client.models.list()), key=str.casefold)
        except anthropic.AnthropicError as exc:
            raise _map_error(exc) from None

    def test_connection(self) -> ProviderStatus:
        try:
            models = self.list_models()
        except ProviderError as exc:
            return ProviderStatus(False, exc.user_text())
        self.last_models = models
        message = f"Bağlantı başarılı: {SERVICE}, model {self.model}."
        if models and self.model not in models:
            message += unlisted_model_note(self.model)
        return ProviderStatus(True, message)

    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        system, rest = split_system(messages)
        turns: list[Any] = [{"role": m["role"], "content": m["content"]} for m in rest]
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=turns,
                output_config={"format": {"type": "json_schema", "schema": strict_schema(schema)}},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.AnthropicError as exc:
            raise _map_error(exc) from None
        if response.stop_reason == "max_tokens":
            raise truncated_error(SERVICE)
        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            raise refusal_error(category or "")
        return "".join(block.text for block in response.content if block.type == "text")


def _map_error(exc: anthropic.AnthropicError) -> ProviderError:
    """Kitaplığın hata türlerini en özelden başlayarak Türkçe hataya çevirir."""
    if isinstance(exc, anthropic.APITimeoutError):  # APIConnectionError'ın alt türü: önce denetlenir
        return timeout_error(SERVICE)
    if isinstance(exc, anthropic.APIConnectionError):
        return connect_error(SERVICE)
    if isinstance(exc, anthropic.APIStatusError):
        # 401 AuthenticationError, 403 PermissionDeniedError, 429 RateLimitError, ≥500 (529 aşırı yük dahil).
        retry_after = parse_retry_after(exc.response.headers.get("retry-after"))
        return status_error(SERVICE, exc.status_code, exc.api_message or "", retry_after)
    return ProviderError(f"Claude isteği başarısız: {type(exc).__name__}")
