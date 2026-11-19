"""Ollama sağlayıcısı (yerel, ücretsiz). Varsayılan sağlayıcıdır.

Kullanılan uç noktalar (Ollama HTTP API):

- `GET  /api/version` — sunucu çalışıyor mu?
- `GET  /api/tags` — yüklü modeller
- `POST /api/show` — modelin yetenekleri ("completion", "thinking", "embedding"…)
- `POST /api/chat` — çeviri; `format` alanına JSON şeması verilerek modelin yalnızca
  `{"translations": [{"id", "text"}]}` biçiminde yanıt vermesi istenir.

İstem (prompt) İngilizce yazılır (modeller talimatı en tutarlı İngilizcede izler); çıktı
Türkçedir. Her partiyle birlikte sahnedeki önceki/sonraki satırlar (`context_before`,
`context_after`) gönderilir: kısa cevapların ve "it/that" gibi zamirlerin neyi kastettiği
ancak böyle anlaşılır. Hedef Türkçe ise isteme Türkçe üslup kuralları (`TURKISH_STYLE`)
eklenir. Redaksiyonda (`Scene.revise`) model mevcut çeviriyi talimata göre düzeltir.
Ayrıntılar ve model önerileri: docs/translation.md
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from nxceviri.core.errors import OperationCancelled
from nxceviri.core.progress import CancelToken
from nxceviri.core.translate.providers.base import (
    BatchItem,
    PlannedBatch,
    ProviderError,
    ProviderStatus,
)

# Ortak istem mantığı llm.py'dedir; eski içe aktarmalar (testler) bu adları hâlâ buradan alır (`__all__`).
from nxceviri.core.translate.providers.llm import (
    _CHARS_PER_TOKEN,
    CONTEXT_LINE_CHARS,
    LANGUAGE_NAMES_EN,
    TURKISH_STYLE,
    LLMProvider,
    _key_hint,
    build_messages,
    estimate_tokens,
    extract_translations,
    language_name,
    prompt_weight,
    system_prompt,
    unreadable_answer_error,
)

__all__ = [
    "CONTEXT_LINE_CHARS",
    "DEFAULT_URL",
    "LANGUAGE_NAMES_EN",
    "MAX_NUM_CTX",
    "MIN_NUM_CTX",
    "OLLAMA_SEED",
    "RECOMMENDED_MODELS",
    "TEMPLATE_WARNING",
    "TURKISH_STYLE",
    "ModelInfo",
    "OllamaProvider",
    "_key_hint",
    "build_messages",
    "choose_num_ctx",
    "estimate_tokens",
    "extract_translations",
    "inline_system",
    "language_name",
    "prompt_weight",
    "system_prompt",
    "template_drops_system",
]

log = logging.getLogger(__name__)

DEFAULT_URL = "http://localhost:11434"
#: Çeviri isteklerinde sabit rastgelelik tohumu (aynı istem → aynı yanıt).
OLLAMA_SEED = 42
#: Çeviri isteğinde Ollama bu kadar saniye hiç yeni parça üretmezse takılmış sayılır. Model yüklenmesi ve uzun
#: istemin işlenmesi ilk parçadan önce olur; büyük modelde bile birkaç dakikayı geçmez.
STALL_TIMEOUT_S = 300.0
#: İptal isteğinin ne sıklıkla yoklandığı (saniye).
_CANCEL_POLL_S = 0.2

#: Bağlam penceresi (`num_ctx`) sınırları ve adımı; istem + yanıt payı bu aralığa sığmalıdır.
MIN_NUM_CTX = 8192
MAX_NUM_CTX = 32768
#: Yanıt için ayrılan en çok belirteç (`num_predict`).
NUM_PREDICT = 3072
#: Tekrar cezası (`repeat_penalty`): 1.0 kapalı; hafif değer döngüye girmeyi azaltır, çeviriyi bozmaz.
REPEAT_PENALTY = 1.1
_CTX_MARGIN = 1.15


#: RTX A4000 (16 GB VRAM) için önerilen modeller, tercih sırasıyla (Ekim 2026 araştırması).
RECOMMENDED_MODELS: tuple[tuple[str, str], ...] = (
    ("gemma4:12b", "Önerilen: Google'ın en yeni çok dilli modeli; 16 GB VRAM'e rahat sığar."),
    ("gemma3:12b", "Güçlü çok dilli yazım; Gemma 4 kadar yeni değil ama yaygın olarak denenmiş."),
    ("qwen3:14b", "16 GB için sık önerilen genel model; Türkçesini kendi metinlerinizle karşılaştırın."),
)


@dataclass(frozen=True)
class ModelInfo:
    name: str
    size_bytes: int
    parameters: str
    quantization: str
    capabilities: tuple[str, ...]
    #: Sohbet şablonu sistem mesajını kullanmıyor mu? (`/api/show` okunamadıysa False.)
    template_drops_system: bool = False
    #: Modelin desteklediği en uzun bağlam (belirteç); bilinmiyorsa None.
    context_length: int | None = None

    @property
    def can_chat(self) -> bool:
        # Eski Ollama sürümleri yetenek listesi döndürmez; o durumda gömme modeli olmadığını varsayarız.
        return not self.capabilities or "completion" in self.capabilities


_TEMPLATE_USES_SYSTEM = re.compile(r"\.(System|Messages)\b|\bmessages\b")

#: Sistem metni düşen modelde çeviri talimatının kullanıcı mesajına eklenme biçimi.
_INLINE_SYSTEM = "Instructions:\n{system}\n\nInput:\n{user}"

TEMPLATE_WARNING = (
    "Bu modelin şablonu sistem talimatını yok sayıyor; talimatlar kullanıcı mesajına eklenecek. "
    "En iyi sonuç için sohbet şablonu olan bir model seçin (ör. hf.co/… sürümü)."
)


def template_drops_system(template: str) -> bool:
    """Şablon `/api/chat` sistem mesajını hiç kullanmıyor mu?

    Ollama sistem mesajını Go şablonunda `.System` ya da `.Messages` ile, GGUF'tan gelen Jinja şablonunda
    `messages` değişkeniyle modele iletir; hiçbiri yoksa (ör. yalnızca `{{ .Prompt }}` ya da boş şablon) yalnızca
    son kullanıcı mesajı gider ve kurallar modele ulaşmaz.
    """
    return _TEMPLATE_USES_SYSTEM.search(template) is None


def choose_num_ctx(prompt_chars: int, context_length: int | None = None) -> int:
    """İstek için bağlam penceresi: tahmini istem + yanıt payı + %15, 8192'nin katına yuvarlanır.

    Alt sınır 8192, üst sınır modelin bağlam uzunluğu ve 32768'dir. İstem üst sınıra sığmıyorsa Türkçe hata verir.
    """
    cap = min(context_length or MAX_NUM_CTX, MAX_NUM_CTX)
    tokens = math.ceil(prompt_chars / _CHARS_PER_TOKEN)
    needed = math.ceil((tokens + NUM_PREDICT) * _CTX_MARGIN)
    if needed > cap:
        fits = max(int(cap / _CTX_MARGIN) - NUM_PREDICT, 0) * _CHARS_PER_TOKEN
        raise ProviderError(
            f"İstem modelin bağlam penceresine ({cap} belirteç) sığmıyor: oyun notları veya talimat çok uzun.",
            f"Oyun notlarını ve talimatı kısaltın: istem yaklaşık {max(prompt_chars - fits, 1)} karakter fazla.",
        )
    rounded = math.ceil(needed / MIN_NUM_CTX) * MIN_NUM_CTX
    return min(max(rounded, MIN_NUM_CTX), cap)


@dataclass(frozen=True)
class _ShowInfo:
    """`/api/show` yanıtından okunan, model başına önbelleğe alınan bilgiler."""

    capabilities: tuple[str, ...] = ()
    template_drops_system: bool = False
    context_length: int | None = None


def _parse_show(show: dict[str, Any]) -> _ShowInfo:
    template = show.get("template")
    context_length = None
    for key, value in (show.get("model_info") or {}).items():
        if str(key).endswith(".context_length") and isinstance(value, int) and value > 0:
            context_length = value
            break
    return _ShowInfo(
        tuple(str(c) for c in show.get("capabilities") or ()),
        # Eski sürümler şablon alanı döndürmez: bilinmeyen şablon sistem mesajını kullanıyor sayılır.
        isinstance(template, str) and template_drops_system(template),
        context_length,
    )


def inline_system(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sistem mesajlarını ilk kullanıcı mesajının başına ekler ("Instructions:…\n\nInput:\n…").

    Şablonu `.System`/`.Messages` kullanmayan modelde sistem mesajı hiç iletilmez; böylece kurallar yine ulaşır.
    Kullanıcı mesajının JSON'u olduğu gibi kalır (`Input:` satırından sonra).
    """
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    rest = [m for m in messages if m["role"] != "system"]
    if not system or not rest:
        return messages
    first = {"role": rest[0]["role"], "content": _INLINE_SYSTEM.format(system=system, user=rest[0]["content"])}
    return [first, *rest[1:]]


class OllamaProvider(LLMProvider):
    name = "ollama"
    label = "Ollama (yerel)"
    requires_api_key = False
    supports_glossary = True
    supports_instructions = True
    #: Küçük partiler: büyük modelde her istek kısa sürer, ilerleme görünür, zaman aşımı riski düşer.
    max_batch_chars = 1500
    max_batch_items = 8

    def __init__(
        self,
        model: str,
        base_url: str = DEFAULT_URL,
        *,
        timeout_s: float = 600.0,
        stall_timeout_s: float = STALL_TIMEOUT_S,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=5.0))
        self._stall_timeout_s = stall_timeout_s
        self._show_cache: dict[str, _ShowInfo] = {}
        #: İş başında hesaplanan bağlam penceresi (`prepare_job`); 0: hesaplanmadı. İş boyunca sabit kalır ki
        #: Ollama modeli yeniden yüklemesin ve istem önek önbelleği korunsun.
        self._job_num_ctx = 0
        #: Çalıştırıcı verir: iptal istenince süren istek hemen kesilir (yanıt beklenmez).
        self.cancel_token: CancelToken | None = None
        self._last_done_reason = ""  # son yanıtın bitiş nedeni ("stop", "length" …)

    def close(self) -> None:
        self._client.close()

    # --- HTTP yardımcıları -------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self._client.request(method, url, json=body)
        except httpx.InvalidURL:
            raise _invalid_url_error(self.base_url) from None
        except httpx.ConnectError:
            raise _connect_error(self.base_url) from None
        except httpx.TimeoutException:
            raise ProviderError(
                "Ollama zamanında yanıt vermedi.",
                "Model ilk kez yükleniyor olabilir veya parti çok büyük. Biraz bekleyip tekrar deneyin; "
                "sorun sürerse daha küçük bir model seçin.",
                retryable=True,
            ) from None
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama isteği başarısız: {type(exc).__name__}", retryable=True) from None
        if response.status_code >= 400:
            raise self._http_error(response)
        try:
            return response.json()
        except ValueError:
            raise ProviderError("Ollama anlaşılmayan bir yanıt döndürdü.", retryable=True) from None

    def _chat(self, body: dict[str, Any]) -> str:
        """/api/chat'i akış hâlinde çağırır ve modelin metnini döndürür.

        Akış sayesinde iki şey olur: iptal istenince bağlantı hemen kapatılır (yanıtın bitmesi beklenmez) ve
        Ollama `stall_timeout_s` boyunca hiç parça üretmezse takıldığı anlaşılır (toplam süre sınırsızdır;
        uzun ama ilerleyen bir yanıt kesilmez).
        """
        url = f"{self.base_url}/api/chat"
        token = self.cancel_token
        self._last_done_reason = ""
        finished = threading.Event()
        parts: list[str] = []
        timeout = httpx.Timeout(self._stall_timeout_s, connect=5.0)
        try:
            with self._client.stream("POST", url, json={**body, "stream": True}, timeout=timeout) as response:
                if token is not None:
                    threading.Thread(target=_close_on_cancel, args=(token, finished, response), daemon=True).start()
                if response.status_code >= 400:
                    response.read()
                    raise self._http_error(response)
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        raise ProviderError("Ollama anlaşılmayan bir yanıt döndürdü.", retryable=True) from None
                    if chunk.get("error"):
                        error = str(chunk["error"])
                        if _is_generation_abort(error):
                            raise ProviderError(
                                f"Model aynı şeyi tekrarlayıp takıldı; Ollama üretimi kesti ({error}).",
                                retryable=True,
                                per_item=True,
                            )
                        raise ProviderError(f"Ollama hata bildirdi: {error}", retryable=True)
                    parts.append(str((chunk.get("message") or {}).get("content", "")))
                    if chunk.get("done"):
                        self._last_done_reason = str(chunk.get("done_reason") or "")
                        break
        except httpx.InvalidURL:
            raise _invalid_url_error(self.base_url) from None
        except httpx.ConnectError:
            raise _connect_error(self.base_url) from None
        except httpx.TimeoutException:
            if token is not None and token.cancelled:
                raise OperationCancelled() from None
            raise ProviderError(
                f"Ollama {round(self._stall_timeout_s / 60)} dakikadır hiç yanıt üretmiyor; takılmış görünüyor.",
                "Ollama'yı kapatıp yeniden açın (saatin yanındaki simge → Quit Ollama). Sık oluyorsa model ekran "
                "kartına sığmıyor olabilir: komut satırında `ollama ps` ile bakın, gerekirse daha küçük bir model "
                "seçin. Biten partiler kaydedildi; işi yeniden başlatınca kaldığı yerden devam eder.",
                retryable=False,
            ) from None
        except (httpx.HTTPError, httpx.StreamError, OSError) as exc:
            if token is not None and token.cancelled:
                raise OperationCancelled() from None
            raise ProviderError(f"Ollama isteği başarısız: {type(exc).__name__}", retryable=True) from None
        finally:
            finished.set()
        if token is not None and token.cancelled:
            raise OperationCancelled()
        return "".join(parts)

    def _http_error(self, response: httpx.Response) -> ProviderError:
        try:
            detail = str(response.json().get("error", ""))
        except ValueError:
            detail = response.text[:200]
        low = detail.lower()
        if response.status_code == 404 or "not found" in low:
            return ProviderError(
                f"Model bulunamadı: {self.model}",
                f"Modeli indirmek için komut satırında `ollama pull {self.model}` çalıştırın "
                "veya listeden yüklü bir model seçin.",
            )
        if "memory" in low or "cuda" in low:
            return ProviderError(
                "Model ekran kartı belleğine sığmadı.",
                "Daha küçük bir model veya daha düşük nicemlemeli (ör. q4) bir sürüm seçin.",
            )
        return ProviderError(
            f"Ollama hata döndürdü (HTTP {response.status_code}): {detail}", retryable=response.status_code >= 500
        )

    # --- sözleşme ----------------------------------------------------------------------

    def list_models(self) -> list[ModelInfo]:
        data = self._request("GET", "/api/tags")
        models = []
        for m in data.get("models", []):
            name = str(m.get("name") or m.get("model") or "")
            if not name:
                continue
            details = m.get("details") or {}
            info = self._model_info(name)
            models.append(
                ModelInfo(
                    name=name,
                    size_bytes=int(m.get("size") or 0),
                    parameters=str(details.get("parameter_size", "")),
                    quantization=str(details.get("quantization_level", "")),
                    capabilities=info.capabilities,
                    template_drops_system=info.template_drops_system,
                    context_length=info.context_length,
                )
            )
        return models

    def test_connection(self) -> ProviderStatus:
        try:
            version = self._request("GET", "/api/version").get("version", "?")
            models = self.list_models()
        except ProviderError as exc:
            return ProviderStatus(False, exc.user_text())
        chat = [m for m in models if m.can_chat]
        if not chat:
            names = ", ".join(n for n, _ in RECOMMENDED_MODELS)
            return ProviderStatus(
                False,
                f"Ollama {version} çalışıyor ama çeviri yapabilecek model yüklü değil. "
                f"Önerilenlerden birini indirin, ör. `ollama pull {RECOMMENDED_MODELS[0][0]}` ({names}).",
            )
        found = next((m for m in chat if m.name == self.model), None)
        if found is None:
            return ProviderStatus(
                False, f"Ollama {version} çalışıyor ama '{self.model}' modeli yüklü değil. Listeden bir model seçin."
            )
        message = f"Bağlantı başarılı: Ollama {version}, model {found.name} {found.parameters}".strip()
        if found.template_drops_system:
            message += f". {TEMPLATE_WARNING}"
        return ProviderStatus(True, message)

    def _model_info(self, model: str | None = None) -> _ShowInfo:
        """Modelin yetenekleri, şablon durumu ve bağlam uzunluğu (`/api/show`); model başına bir kez okunur."""
        name = model or self.model
        info = self._show_cache.get(name)
        if info is None:
            try:
                info = _parse_show(self._request("POST", "/api/show", {"model": name}))
            except ProviderError as exc:
                log.info("Model bilgisi okunamadı (%s): %s", name, exc.message)
                info = _ShowInfo()
            self._show_cache[name] = info
            if info.template_drops_system:
                log.info(
                    "%s: model şablonu sistem mesajını kullanmıyor; talimatlar kullanıcı mesajına eklenecek.",
                    name,
                )
        return info

    def prepare_job(self, batches: Sequence[PlannedBatch], source_lang: str, target_lang: str, context: str) -> None:
        """İşin bağlam penceresini en uzun partiye göre bir kez belirler (iş boyunca sabit kalır).

        İstem sığmıyorsa iş başlamadan Türkçe hata verir (oyun notları/talimat çok uzun).
        """
        info = self._model_info()
        longest = 0
        for b in batches:
            messages = build_messages(b.items, source_lang, target_lang, context, b.glossary, scene=b.scene)
            longest = max(longest, prompt_weight(messages))
        self._job_num_ctx = choose_num_ctx(longest, info.context_length)
        log.info(
            "%s: bağlam penceresi (num_ctx) %d (en uzun istem ≈ %d karakter eşdeğeri)",
            self.model,
            self._job_num_ctx,
            longest,
        )

    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        """Modelden `schema` biçiminde JSON yanıt ister ve metni döndürür (çeviri ve sözlük önerisi bunu kullanır)."""
        info = self._model_info()
        if info.template_drops_system:
            messages = inline_system(messages)
        num_ctx = choose_num_ctx(prompt_weight(messages), info.context_length)
        if self._job_num_ctx:
            if num_ctx > self._job_num_ctx:  # bağlam satırlarındaki çeviriler beklenenden uzun çıktı
                log.info("%s: istem beklenenden uzun; num_ctx %d → %d", self.model, self._job_num_ctx, num_ctx)
                self._job_num_ctx = num_ctx
            num_ctx = self._job_num_ctx
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "format": schema,
            # Düşük sıcaklık ve sabit tohum: aynı istem aynı çeviriyi verir (tutarlılık), model daha az uydurur.
            # Yeniden denemede istem değiştiği ("fix") için sonuç yine değişebilir.
            "options": {
                "temperature": 0.2,
                "seed": OLLAMA_SEED,
                "num_ctx": num_ctx,
                "num_predict": NUM_PREDICT,
                # Aynı sözcüğü/harfi döngüyle tekrarlayan satırlarda ("Nooo!!!") modelin takılmasını azaltır.
                "repeat_penalty": REPEAT_PENALTY,
            },
            "keep_alive": "15m",
        }
        if "thinking" in info.capabilities:
            body["think"] = False  # düşünme modu çeviriyi yavaşlatır, katkısı yok
        return self._chat(body)

    def unreadable_error(self, content: str) -> ProviderError:
        # Model metni günlüğe yazılır (oyun metni; anahtar veya gizli bilgi içermez): sorunun nedeni görülsün.
        log.warning("%s JSON yerine şunu döndürdü (bitiş: %s): %r", self.model, self._last_done_reason, content[:600])
        if self._last_done_reason == "length":
            return ProviderError(
                "Modelin yanıtı uzunluk sınırında kesildi.",
                'Model yanıttan önce uzun bir "düşünme" bölümü yazıyor olabilir. Ollama\'nın kütüphanesindeki '
                "bir modeli (ör. gemma4:26b) deneyin ya da modelin düşünme modunu kapatın.",
                retryable=True,
                splittable=True,
                per_item=True,
            )
        return unreadable_answer_error()

    def estimate_cost(self, items: list[BatchItem]) -> str | None:
        return None  # yerel model: ücretsiz


def _is_generation_abort(error: str) -> bool:
    """Ollama üretimi modelin döngüye girmesi yüzünden kesti mi? (Bağlantı/sunucu hatası değil, o metne özgü sorun.)"""
    low = error.lower()
    return "repeat limit" in low or "prediction aborted" in low


def _invalid_url_error(base_url: str) -> ProviderError:
    return ProviderError(
        f"Ollama adresi geçersiz ({base_url}).",
        "Adres http:// ya da https:// ile başlamalı ve bağlantı noktası sayı olmalıdır, ör. http://localhost:11434.",
        retryable=False,
    )


def _connect_error(base_url: str) -> ProviderError:
    return ProviderError(
        f"Ollama'ya bağlanılamadı ({base_url}).",
        "Ollama'nın kurulu ve çalışıyor olduğundan emin olun: Başlat menüsünden Ollama'yı açın "
        "veya komut satırında `ollama serve` çalıştırın. Adres farklıysa ayarlardan düzeltin.",
        retryable=False,
    )


def _close_on_cancel(token: CancelToken, finished: threading.Event, response: httpx.Response) -> None:
    """İstek sürerken iptal istenirse bağlantıyı kapatır; okuyan iş parçacığı hemen hata alıp durur."""
    while not finished.wait(_CANCEL_POLL_S):
        if token.cancelled:
            response.close()
            return
