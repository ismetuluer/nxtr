"""OpenAI uyumlu sohbet uç noktaları: OpenAI, OpenRouter, Groq, Mistral, DeepSeek, LM Studio ve özel adres.

Kullanılan uç noktalar (OpenAI Chat Completions biçimi; hizmetlerin çoğu aynısını sunar):

- `GET  {base}/models` — modeller (bağlantı testi ve "Modelleri Listele")
- `POST {base}/chat/completions` — çeviri. Yanıt biçimi önce `response_format: json_schema` (katı şema) ile
  istenir; sunucu bunu reddederse (400 ve hata metninde `response_format`/`json_schema`) `json_object`, o da
  reddedilirse biçimsiz düz metin denenir (istem zaten yalnızca JSON istiyor). Düşürülen biçim sağlayıcı
  nesnesinde hatırlanır, her partide yeniden denenmez.

Anahtar `Authorization: Bearer` başlığıyla gider; anahtarsız hizmette (LM Studio, özel adres) başlık hiç
gönderilmez. Anahtar hiçbir koşulda loglanmaz, hata mesajına veya `repr`'e yazılmaz. Sıcaklık gibi örnekleme
ayarları gönderilmez: bazı modeller bunları reddediyor, hizmetin varsayılanı çeviri için yeterli.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from nxceviri.core.translate.providers.base import ProviderError, ProviderStatus
from nxceviri.core.translate.providers.llm import (
    LLMProvider,
    connect_error,
    parse_retry_after,
    refusal_error,
    status_error,
    strict_schema,
    timeout_error,
    truncated_error,
    unlisted_model_note,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Preset:
    """Hazır hizmet: kimlik (ayar ve satır kaynağı adı), görünen ad, adres, anahtar gerekir mi, adres değişir mi."""

    id: str
    label: str
    base_url: str
    needs_key: bool = True
    editable_url: bool = False
    #: Anahtarın alınacağı sayfa (ipucunda gösterilir).
    key_page: str = ""


PRESETS: tuple[Preset, ...] = (
    Preset("openai", "OpenAI", "https://api.openai.com/v1", key_page="platform.openai.com → API keys"),
    Preset("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", key_page="openrouter.ai → Keys"),
    Preset("groq", "Groq", "https://api.groq.com/openai/v1", key_page="console.groq.com → API Keys"),
    Preset("mistral", "Mistral", "https://api.mistral.ai/v1", key_page="console.mistral.ai → API Keys"),
    Preset("deepseek", "DeepSeek", "https://api.deepseek.com/v1", key_page="platform.deepseek.com → API keys"),
    Preset("lmstudio", "LM Studio (yerel)", "http://localhost:1234/v1", needs_key=False, editable_url=True),
    Preset("openai_custom", "Özel adres (OpenAI uyumlu)", "", needs_key=False, editable_url=True),
)
_BY_ID = {p.id: p for p in PRESETS}

#: Yanıt biçimi kipleri, denenme sırasıyla.
_MODES = ("json_schema", "json_object", "text")
_FORMAT_WORDS = ("response_format", "json_schema", "json_object", "structured output")


def preset(preset_id: str) -> Preset:
    found = _BY_ID.get(preset_id)
    if found is None:
        raise ProviderError(f"Bilinmeyen OpenAI uyumlu hizmet: {preset_id}")
    return found


class _FormatRejected(Exception):
    """Sunucu istenen `response_format`'ı desteklemiyor: bir sonraki kipe geçilir."""


class OpenAICompatProvider(LLMProvider):
    def __init__(
        self,
        preset_id: str,
        model: str,
        api_key: str = "",
        *,
        base_url: str | None = None,
        timeout_s: float = 180.0,
        client: httpx.Client | None = None,
    ) -> None:
        chosen = preset(preset_id)
        self.name = chosen.id
        self.label = chosen.label
        self.requires_api_key = chosen.needs_key
        self.model = model.strip()
        self._key = api_key.strip()
        if chosen.needs_key and not self._key:
            raise ProviderError(
                f"{chosen.label} API anahtarı girilmemiş.",
                "Otomatik Çeviri penceresinde anahtarı yapıştırıp kaydedin"
                + (f" (anahtar: {chosen.key_page})." if chosen.key_page else "."),
            )
        url = (base_url if chosen.editable_url and base_url else chosen.base_url).strip().rstrip("/")
        if not url:
            raise ProviderError(
                "OpenAI uyumlu sunucunun adresi girilmemiş.", "Adresi yazın, ör. http://localhost:8000/v1."
            )
        self.base_url = url
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=10.0))
        self._mode = _MODES[0]
        #: Son bağlantı testinde alınan model listesi (arayüz "Bağlantıyı Test Et" sonrası listeyi doldurur).
        self.last_models: list[str] = []

    def __repr__(self) -> str:
        return f"<OpenAICompatProvider {self.label} {self.model}>"

    def close(self) -> None:
        self._client.close()

    # --- HTTP ------------------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        try:
            response = self._client.request(method, f"{self.base_url}{path}", json=body, headers=headers)
        except httpx.InvalidURL:
            raise ProviderError(
                f"{self.label} adresi geçersiz.", "Adres http:// ya da https:// ile başlamalıdır."
            ) from None
        except httpx.ConnectError:
            raise connect_error(self.label) from None
        except httpx.TimeoutException:
            raise timeout_error(self.label) from None
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.label} isteği başarısız: {type(exc).__name__}", retryable=True) from None
        if response.status_code >= 400:
            detail = _detail(response)
            if (
                body is not None
                and "response_format" in body
                and response.status_code in (400, 422)
                and any(w in detail.lower() for w in _FORMAT_WORDS)
            ):
                raise _FormatRejected(detail)
            raise status_error(
                self.label, response.status_code, detail, parse_retry_after(response.headers.get("retry-after"))
            )
        try:
            return response.json()
        except ValueError:
            raise ProviderError(f"{self.label} anlaşılmayan bir yanıt döndürdü.", retryable=True) from None

    # --- sözleşme ----------------------------------------------------------------------------

    def list_models(self) -> list[str]:
        data = self._request("GET", "/models")
        rows = data.get("data") if isinstance(data, dict) else None
        names = {str(m.get("id")) for m in rows or [] if isinstance(m, dict) and m.get("id")}
        return sorted(names, key=str.casefold)

    def test_connection(self) -> ProviderStatus:
        try:
            models = self.list_models()
        except ProviderError as exc:
            return ProviderStatus(False, exc.user_text())
        self.last_models = models
        if not self.model:
            return ProviderStatus(False, f"{self.label} bağlantısı çalışıyor; listeden bir model seçin.")
        message = f"Bağlantı başarılı: {self.label}, model {self.model} ({len(models)} model)."
        if models and self.model not in models:
            # Bazı sunucular takma adları ya da her modeli listelemez: başlatmayı engellemez, yalnızca uyarır.
            message += unlisted_model_note(self.model)
        return ProviderStatus(True, message)

    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        if not self.model:
            raise ProviderError("Model seçilmedi.", "“Modelleri Listele” ile bir model seçin ya da adını yazın.")
        while True:
            body: dict[str, Any] = {"model": self.model, "messages": messages}
            if self._mode == "json_schema":
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "answer", "strict": True, "schema": strict_schema(schema)},
                }
            elif self._mode == "json_object":
                body["response_format"] = {"type": "json_object"}
            try:
                data = self._request("POST", "/chat/completions", body)
                break
            except _FormatRejected as exc:
                self._mode = _MODES[_MODES.index(self._mode) + 1]
                log.info("%s yanıt biçimini desteklemiyor (%s); %s kipine geçildi.", self.label, exc, self._mode)
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderError(f"{self.label} boş yanıt döndürdü.", retryable=True, per_item=True)
        choice = choices[0]
        message = choice.get("message") or {}
        finish = str(choice.get("finish_reason") or "")
        if message.get("refusal"):
            raise refusal_error(str(message["refusal"])[:200])
        if finish == "content_filter":
            raise refusal_error("içerik süzgeci")
        if finish == "length":
            raise truncated_error(self.label)
        return str(message.get("content") or "")


def _detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:300]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or "")
        if error:
            return str(error)
        return str(data.get("message") or data.get("detail") or "")
    return ""
