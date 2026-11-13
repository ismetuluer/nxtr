"""DeepL sağlayıcısı (bulut, ücretli/ücretsiz kota).

- Free ve Pro uç noktaları anahtardan otomatik ayırt edilir: Free anahtarlar ":fx" ile biter.
- Kontrol kodları XML etiketi olarak gönderilir: `⟦3⟧` → `<x id="3"/>` (`tag_handling=xml`);
  DeepL etiketleri çeviride uygun yere taşır, dönüşte yeniden `⟦3⟧` olur. Metindeki `& < >`
  karakterleri XML için kaçışlanır.
- Sözlük: partide geçen terimler DeepL sözlüğüne (v2 glossaries) yüklenir; yeni terim geldikçe
  sözlük birleşimle yeniden kurulur, iş bitince (`close`) silinir. Dil çifti desteklenmezse
  sözlüksüz devam edilir ve uyarı kaydedilir.
- Kota: `/v2/usage` ile okunur, arayüzde gösterilir.
- Bağlam: oyun notları ve sahnedeki komşu satırlar `context` alanında gönderilir; DeepL bunu
  çevirmez, kotadan düşmez, yalnızca anlamı netleştirmek için kullanır. Serbest talimatı
  (redaksiyon) izleyemez; böyle bir iş reddedilir.

API anahtarı hiçbir koşulda loglanmaz, hata mesajına veya `repr`'e yazılmaz.
Ayrıntılar: docs/translation.md
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

import httpx

from nxceviri.core.translate import placeholders
from nxceviri.core.translate.providers.base import (
    BatchItem,
    BatchResult,
    GlossaryTerm,
    ProviderError,
    ProviderStatus,
    Scene,
)

log = logging.getLogger(__name__)

FREE_URL = "https://api-free.deepl.com"
PRO_URL = "https://api.deepl.com"

_TAG_BACK_RE = re.compile(r'<x\s+id\s*=\s*"(\d+)"\s*/>|<x\s+id\s*=\s*"(\d+)"\s*>\s*</x>')


def endpoint_for(api_key: str) -> str:
    return FREE_URL if api_key.strip().endswith(":fx") else PRO_URL


def plan_label(api_key: str) -> str:
    return "DeepL API Free" if endpoint_for(api_key) == FREE_URL else "DeepL API Pro"


def deepl_lang(code: str, *, target: bool) -> str:
    """Uygulamanın dil kodunu DeepL koduna çevirir (ör. "pt-BR" → kaynakta "PT", hedefte "PT-BR")."""
    base, _, variant = code.partition("-")
    base = base.upper()
    if target and base in ("EN", "PT"):
        return f"{base}-{(variant or ('US' if base == 'EN' else 'BR')).upper()}"
    if target and base == "ZH":
        return "ZH-HANT" if variant.lower() == "hant" else "ZH-HANS"
    return base


#: DeepL `context` alanına konan komşu satır metninin üst sınırı (karakter).
CONTEXT_CHARS = 2000


def deepl_context(notes: str, scene: Scene | None) -> str:
    """Oyun notları + sahnedeki önceki/sonraki satırların özgün metni (DeepL bağlamı kaynak dilde ister)."""
    parts = [notes.strip()] if notes.strip() else []
    if scene is not None:
        lines = [placeholders.TOKEN_RE.sub("", ln.source).strip() for ln in (*scene.before, *scene.after)]
        joined = "\n".join(ln for ln in lines if ln)
        if joined:
            parts.append(joined[-CONTEXT_CHARS:])
    return "\n\n".join(parts)


def to_xml(text: str) -> str:
    """Yer tutuculu metni DeepL'e gidecek XML'e çevirir."""
    parts = []
    for piece in placeholders.split(text):
        if isinstance(piece, int):
            parts.append(f'<x id="{piece}"/>')
        else:
            parts.append(html.escape(piece, quote=False))
    return "".join(parts)


def from_xml(text: str) -> str:
    """DeepL'den dönen XML'i yer tutuculu metne geri çevirir."""
    replaced = _TAG_BACK_RE.sub(lambda m: placeholders.token(int(m.group(1) or m.group(2))), text)
    return html.unescape(replaced)


class DeepLProvider:
    name = "deepl"
    label = "DeepL"
    requires_api_key = True
    supports_glossary = True
    supports_instructions = False
    max_batch_chars = 30_000  # istek sınırı 128 KiB; Türkçe karakterler 2 bayt
    max_batch_items = 50

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout_s: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderError("DeepL API anahtarı girilmemiş.", "Çeviri ayarlarından API anahtarınızı kaydedin.")
        self._key = api_key.strip()
        self.base_url = (base_url or endpoint_for(self._key)).rstrip("/")
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=10.0))
        self._glossary_id: str | None = None
        self._glossary_terms: dict[str, GlossaryTerm] = {}
        self._glossary_pair: tuple[str, str] | None = None
        self.warnings: list[str] = []

    def __repr__(self) -> str:
        return f"<DeepLProvider {plan_label(self._key)}>"

    # --- HTTP ------------------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"DeepL-Auth-Key {self._key}"}
        try:
            response = self._client.request(method, f"{self.base_url}{path}", json=body, headers=headers)
        except httpx.ConnectError:
            raise ProviderError(
                "DeepL'e bağlanılamadı.", "İnternet bağlantınızı kontrol edin.", retryable=True
            ) from None
        except httpx.TimeoutException:
            raise ProviderError("DeepL zamanında yanıt vermedi.", retryable=True) from None
        except httpx.HTTPError as exc:
            raise ProviderError(f"DeepL isteği başarısız: {type(exc).__name__}", retryable=True) from None
        if response.status_code >= 400:
            raise self._http_error(response)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            raise ProviderError("DeepL anlaşılmayan bir yanıt döndürdü.", retryable=True) from None

    @staticmethod
    def _http_error(response: httpx.Response) -> ProviderError:
        try:
            data = response.json()
            detail = str(data.get("message") or (data.get("error") or {}).get("message") or "")
        except (ValueError, AttributeError):
            detail = ""
        code = response.status_code
        if code == 403:
            return ProviderError(
                "DeepL API anahtarı geçersiz veya bu işlem için yetkisiz.",
                "Anahtarı DeepL hesabınızdan (Hesap → API Anahtarları) kopyalayıp çeviri ayarlarına yeniden girin.",
            )
        if code == 456:
            return ProviderError(
                "DeepL karakter kotanız doldu.",
                "Kota dönem başında yenilenir. Bu arada Ollama ile devam edebilirsiniz; çevrilenler kaydedildi.",
            )
        if code in (429, 529):
            return ProviderError("DeepL çok fazla istek aldı; kısa bir süre beklenecek.", retryable=True)
        if code == 413:
            return ProviderError("DeepL isteği çok büyük buldu.", "Bu bir hatadır; hata kaydı dosyasını paylaşın.")
        if code >= 500:
            return ProviderError(f"DeepL geçici bir hata döndürdü (HTTP {code}).", retryable=True)
        return ProviderError(f"DeepL isteği reddetti (HTTP {code}): {detail}")

    # --- sözleşme ----------------------------------------------------------------------------

    def usage(self) -> tuple[int, int]:
        data = self._request("GET", "/v2/usage")
        return int(data.get("character_count", 0)), int(data.get("character_limit", 0))

    def test_connection(self) -> ProviderStatus:
        try:
            used, limit = self.usage()
        except ProviderError as exc:
            return ProviderStatus(False, exc.user_text())
        if limit and used >= limit:
            return ProviderStatus(False, f"{plan_label(self._key)}: karakter kotası dolu ({used:,} / {limit:,}).")
        quota = f"{used:,} / {limit:,} karakter kullanıldı" if limit else f"{used:,} karakter kullanıldı"
        return ProviderStatus(True, f"Bağlantı başarılı: {plan_label(self._key)} — {quota}.".replace(",", "."))

    def estimate_cost(self, items: list[BatchItem]) -> str | None:
        chars = sum(len(i.text) for i in items)
        try:
            used, limit = self.usage()
        except ProviderError:
            return f"Yaklaşık {chars:,} karakter kullanılacak.".replace(",", ".")
        left = max(limit - used, 0)
        note = f"Yaklaşık {chars:,} karakter kullanılacak; kalan kota {left:,} karakter.".replace(",", ".")
        if limit and chars > left:
            note += " Kota yetmeyebilir; iş kota dolunca durur, çevrilenler kaydedilir."
        return note

    def _ensure_glossary(self, terms: list[GlossaryTerm], source: str, target: str) -> str | None:
        pair = (source, target)
        new = {t.term: t for t in terms if t.term not in self._glossary_terms}
        if self._glossary_id is not None and not new and self._glossary_pair == pair:
            return self._glossary_id
        if not terms and self._glossary_id is None:
            return None
        merged = {**self._glossary_terms, **new}
        entries = "\n".join(f"{t.term}\t{t.translation}" for t in merged.values() if "\t" not in t.term + t.translation)
        try:
            created = self._request(
                "POST",
                "/v2/glossaries",
                {
                    "name": "NXTR",
                    "source_lang": source.split("-", maxsplit=1)[0].lower(),
                    "target_lang": target.split("-", maxsplit=1)[0].lower(),
                    "entries": entries,
                    "entries_format": "tsv",
                },
            )
        except ProviderError as exc:
            if exc.retryable:
                raise
            msg = f"DeepL sözlüğü oluşturulamadı; sözlüksüz devam ediliyor ({exc.message})."
            if msg not in self.warnings:
                self.warnings.append(msg)
                log.warning(msg)
            return self._glossary_id
        self._delete_glossary()
        self._glossary_id = str(created.get("glossary_id", "")) or None
        self._glossary_terms = merged
        self._glossary_pair = pair
        return self._glossary_id

    def _delete_glossary(self) -> None:
        if self._glossary_id is None:
            return
        try:
            self._request("DELETE", f"/v2/glossaries/{self._glossary_id}")
        except ProviderError as exc:
            log.info("Eski DeepL sözlüğü silinemedi: %s", exc.message)
        self._glossary_id = None

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
                "DeepL talimatla düzeltme (redaksiyon) yapamaz.",
                "Redaksiyon için sağlayıcı olarak Ollama'yı seçin.",
            )
        source = deepl_lang(source_lang, target=False)
        target = deepl_lang(target_lang, target=True)
        body: dict[str, Any] = {
            "text": [to_xml(i.text) for i in items],
            "source_lang": source,
            "target_lang": target,
            "tag_handling": "xml",
            "preserve_formatting": True,
            "split_sentences": "nonewlines",
        }
        context_text = deepl_context(context, scene)
        if context_text:
            body["context"] = context_text
        fixed = [g for g in glossary if g.translation]  # lore maddelerinin sabit çevirisi yok
        glossary_id = self._ensure_glossary(fixed, source, target) if fixed else self._glossary_id
        if glossary_id:
            body["glossary_id"] = glossary_id
        data = self._request("POST", "/v2/translate", body)
        rows = data.get("translations")
        if not isinstance(rows, list) or len(rows) != len(items):
            raise ProviderError("DeepL beklenmeyen sayıda çeviri döndürdü.", retryable=True)
        return [BatchResult(it.id, from_xml(str(row.get("text", "")))) for it, row in zip(items, rows, strict=True)]

    def close(self) -> None:
        self._delete_glossary()
        self._client.close()
