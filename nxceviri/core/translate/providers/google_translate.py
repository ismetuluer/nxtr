"""Google Translate sağlayıcısı: Cloud Translation Basic (v2), klasik makine çevirisi.

- `POST https://translation.googleapis.com/language/translate/v2` — gövdede `q` (metin listesi, en çok 128),
  `source`, `target`, `format: "html"`; yanıt `data.translations[].translatedText`.
- `GET  …/v2/languages` — bağlantı testi (çeviri kotası harcamaz).
- Anahtar `x-goog-api-key` başlığında gider (Google'ın önerdiği yol; `?key=` adreste kalır ve adres günlüğe
  yazılabilir).
- Kontrol kodları DeepL'deki gibi `<x id="n"/>` etiketi olarak gönderilir (`deepl.to_xml/from_xml` ortak kod);
  HTML kipinde satır sonu yutulduğundan `\\n` de `<br/>` etiketiyle korunur ve dönüşte geri çevrilir.
- Talimat (redaksiyon) izleyemez, sözlük desteklemez (Basic sürümünde sözlük yoktur), oyun notlarını kullanmaz.

API anahtarı hiçbir koşulda loglanmaz, hata mesajına veya `repr`'e yazılmaz.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from nxceviri.core.translate.providers.base import (
    BatchItem,
    BatchResult,
    GlossaryTerm,
    ProviderError,
    ProviderStatus,
    Scene,
)
from nxceviri.core.translate.providers.deepl import from_xml, to_xml
from nxceviri.core.translate.providers.llm import connect_error, parse_retry_after, status_error, timeout_error

log = logging.getLogger(__name__)

BASE_URL = "https://translation.googleapis.com/language/translate/v2"
SERVICE = "Google Translate"
_BREAK_TAG = "<br/>"
#: Dönüşte satır sonu etiketi; hizmetin etiketin çevresine eklediği tek boşluk da atılır.
_BREAK_BACK_RE = re.compile(r" ?<br\s*/?> ?", re.I)


def google_lang(code: str) -> str:
    """Uygulamanın dil kodunu Google koduna çevirir (ör. "pt-BR" → "pt", "zh-Hant" → "zh-TW")."""
    base, _, variant = code.partition("-")
    base = base.lower()
    if base == "zh":
        return "zh-TW" if variant.lower() in ("hant", "tw") else "zh-CN"
    return base


def _encode(text: str) -> str:
    return to_xml(text).replace("\n", _BREAK_TAG)


def _decode(text: str) -> str:
    return from_xml(_BREAK_BACK_RE.sub("\n", text))


class GoogleTranslateProvider:
    name = "google_translate"
    label = SERVICE
    requires_api_key = True
    supports_glossary = False
    supports_instructions = False
    #: Belgelenen sınır istek başına 128 metin; karakter sınırı belgede yok, istekler küçük tutulur.
    max_batch_items = 100
    max_batch_chars = 5000

    def __init__(
        self, api_key: str, *, base_url: str = BASE_URL, timeout_s: float = 60.0, client: httpx.Client | None = None
    ) -> None:
        if not api_key.strip():
            raise ProviderError(
                "Google Translate API anahtarı girilmemiş.",
                "Otomatik Çeviri penceresinde anahtarı yapıştırıp kaydedin (anahtar: Google Cloud Console → "
                "API'ler ve Hizmetler → Kimlik Bilgileri; Cloud Translation API etkin olmalı).",
            )
        self._key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=10.0))

    def __repr__(self) -> str:
        return "<GoogleTranslateProvider>"

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
            raise ProviderError(f"Google Translate isteği başarısız: {type(exc).__name__}", retryable=True) from None
        if response.status_code >= 400:
            code = response.status_code
            text = response.text
            if code == 400 and ("keyInvalid" in text or "API_KEY_INVALID" in text or "API key not valid" in text):
                code = 401  # Google geçersiz anahtarı 400 olarak bildirir
            raise status_error(SERVICE, code, _detail(response), parse_retry_after(response.headers.get("retry-after")))
        try:
            return response.json()
        except ValueError:
            raise ProviderError("Google Translate anlaşılmayan bir yanıt döndürdü.", retryable=True) from None

    def test_connection(self) -> ProviderStatus:
        try:
            data = self._request("GET", "/languages", params={"target": "tr"})
        except ProviderError as exc:
            return ProviderStatus(False, exc.user_text())
        count = len((data.get("data") or {}).get("languages") or [])
        return ProviderStatus(True, f"Bağlantı başarılı: {SERVICE} ({count} dil).")

    def estimate_cost(self, items: list[BatchItem]) -> str | None:
        chars = sum(len(i.text) for i in items)
        return f"Yaklaşık {chars:,} karakter kullanılacak (Google karakter sayar).".replace(",", ".")

    def translate_batch(
        self,
        items: list[BatchItem],
        source_lang: str,
        target_lang: str,
        context: str,
        glossary: list[GlossaryTerm],
        *,
        scene: Scene | None = None,
    ) -> list[BatchResult]:
        if not items:
            return []
        if scene is not None and scene.revise:
            raise ProviderError(
                "Google Translate talimatla düzeltme (redaksiyon) yapamaz.",
                "Redaksiyon için bir yapay zekâ sağlayıcısı (Ollama, Claude, Gemini, OpenAI uyumlu) seçin.",
            )
        body = {
            "q": [_encode(i.text) for i in items],
            "source": google_lang(source_lang),
            "target": google_lang(target_lang),
            "format": "html",
        }
        data = self._request("POST", "", body)
        rows = (data.get("data") or {}).get("translations") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) != len(items):
            raise ProviderError("Google Translate beklenmeyen sayıda çeviri döndürdü.", retryable=True)
        return [
            BatchResult(it.id, _decode(str(row.get("translatedText", "")))) for it, row in zip(items, rows, strict=True)
        ]


def _detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:300]
    error = data.get("error") if isinstance(data, dict) else None
    return str(error.get("message") or "") if isinstance(error, dict) else ""
