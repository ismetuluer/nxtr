"""Gemini (Google) sağlayıcısı: Gemini API'nin `generateContent` uç noktası (httpx, kitaplıksız).

Kullanılan uç noktalar (`https://generativelanguage.googleapis.com/v1beta`):

- `GET  /models` — modeller (`supportedGenerationMethods` içinde `generateContent` olanlar listelenir;
  sayfalama `pageToken`/`nextPageToken`)
- `POST /models/{model}:generateContent` — çeviri. Sistem istemi `systemInstruction`, kullanıcı mesajı `contents`
  içinde gider; JSON yanıt `generationConfig.responseMimeType = application/json` ve `responseSchema` ile istenir.
  `responseSchema` OpenAPI şemasının bir alt kümesidir: `additionalProperties` desteklenmediği için atılır.

Anahtar `x-goog-api-key` başlığında gider (adreste değil: istek adresi günlüğe yazılabilir). Yanıtta `finishReason`
`MAX_TOKENS` ise parti bölünür; güvenlik/telif/yasak içerik nedenleriyle durmuşsa ya da istem engellenmişse
(`promptFeedback.blockReason`) o satır atlanır.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from nxceviri.core.translate.providers.base import ProviderError, ProviderStatus
from nxceviri.core.translate.providers.llm import (
    LLMProvider,
    connect_error,
    parse_retry_after,
    refusal_error,
    split_system,
    status_error,
    strip_schema_keys,
    timeout_error,
    truncated_error,
)

log = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
SERVICE = "Gemini (Google)"
#: Modelin içerik nedeniyle durduğunu gösteren bitiş nedenleri (Gemini API `FinishReason`).
_REFUSAL_REASONS = frozenset(("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "LANGUAGE"))
#: `responseSchema`'nın tanımadığı JSON şeması alanları.
_UNSUPPORTED_SCHEMA_KEYS = frozenset(("additionalProperties",))
#: Model listesinde en çok bu kadar sayfa okunur (sonsuz sayfalamaya karşı).
_MAX_PAGES = 20


class GeminiProvider(LLMProvider):
    name = "gemini"
    label = SERVICE

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = BASE_URL,
        timeout_s: float = 180.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderError(
                "Gemini API anahtarı girilmemiş.",
                "Otomatik Çeviri penceresinde anahtarı yapıştırıp kaydedin (anahtar: aistudio.google.com → API keys).",
            )
        self._key = api_key.strip()
        self.model = model.strip().removeprefix("models/")
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=10.0))

    def __repr__(self) -> str:
        return f"<GeminiProvider {self.model}>"

    def close(self) -> None:
        self._client.close()

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None, params: dict[str, str] | None = None
    ) -> Any:
        try:
            response = self._client.request(
                method, f"{self.base_url}{path}", json=body, params=params, headers={"x-goog-api-key": self._key}
            )
        except httpx.ConnectError:
            raise connect_error(SERVICE) from None
        except httpx.TimeoutException:
            raise timeout_error(SERVICE) from None
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini isteği başarısız: {type(exc).__name__}", retryable=True) from None
        if response.status_code >= 400:
            code, detail = response.status_code, _detail(response)
            if code == 400 and "API_KEY_INVALID" in response.text:
                code = 401  # Gemini geçersiz anahtarı 400 olarak bildirir
            raise status_error(SERVICE, code, detail, parse_retry_after(response.headers.get("retry-after")))
        try:
            return response.json()
        except ValueError:
            raise ProviderError("Gemini anlaşılmayan bir yanıt döndürdü.", retryable=True) from None

    def list_models(self) -> list[str]:
        names: set[str] = set()
        token = ""
        for _ in range(_MAX_PAGES):
            data = self._request("GET", "/models", params={"pageToken": token} if token else None)
            for m in data.get("models") or []:
                if isinstance(m, dict) and "generateContent" in (m.get("supportedGenerationMethods") or []):
                    names.add(str(m.get("name", "")).removeprefix("models/"))
            token = str(data.get("nextPageToken") or "")
            if not token:
                break
        names.discard("")
        return sorted(names, key=str.casefold)

    def test_connection(self) -> ProviderStatus:
        try:
            models = self.list_models()
        except ProviderError as exc:
            return ProviderStatus(False, exc.user_text())
        if not self.model:
            return ProviderStatus(False, "Gemini bağlantısı çalışıyor; listeden bir model seçin.")
        if models and self.model not in models:
            return ProviderStatus(
                False, f"Gemini çalışıyor ama '{self.model}' modeli listede yok. Listeden bir model seçin."
            )
        return ProviderStatus(True, f"Bağlantı başarılı: {SERVICE}, model {self.model}.")

    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        if not self.model:
            raise ProviderError("Model seçilmedi.", "“Modelleri Listele” ile bir model seçin ya da adını yazın.")
        system, rest = split_system(messages)
        body: dict[str, Any] = {
            "contents": [
                {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in rest
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": strip_schema_keys(schema, _UNSUPPORTED_SCHEMA_KEYS),
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        data = self._request("POST", f"/models/{self.model}:generateContent", body)
        candidates = data.get("candidates") if isinstance(data, dict) else None
        if not candidates:
            blocked = str(((data or {}).get("promptFeedback") or {}).get("blockReason") or "")
            if blocked:
                raise refusal_error(blocked)
            raise ProviderError("Gemini boş yanıt döndürdü.", retryable=True, per_item=True)
        first = candidates[0] if isinstance(candidates[0], dict) else {}
        finish = str(first.get("finishReason") or "")
        if finish == "MAX_TOKENS":
            raise truncated_error(SERVICE)
        if finish in _REFUSAL_REASONS:
            raise refusal_error(finish)
        parts = (first.get("content") or {}).get("parts") or []
        # Düşünen modellerin düşünce parçaları (`thought: true`) yanıta katılmaz.
        return "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict) and not p.get("thought"))


def _detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:300]
    error = data.get("error") if isinstance(data, dict) else None
    return str(error.get("message") or "") if isinstance(error, dict) else ""
