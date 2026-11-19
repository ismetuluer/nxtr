"""Büyük dil modeli (LLM) sağlayıcılarının ortak mantığı: istem, yanıt şeması, yanıtın okunması, hata eşlemesi.

Ollama, OpenAI uyumlu uç noktalar, Claude ve Gemini aynı istemi ve aynı `{"translations": [{"id", "text"}]}`
yanıt biçimini kullanır. Her sağlayıcı yalnızca taşımayı yazar (`LLMProvider.chat_json`): isteği gönderir,
modelin metnini döndürür ve hizmetin hatalarını `ProviderError` bayraklarına çevirir:

- 401/403 → anahtar geçersiz/yetkisiz (yeniden denenmez);
- 429, 5xx, 529, zaman aşımı → yeniden denenir (`retry-after` varsa `retry_after_s`);
- yanıt uzunluk sınırında kesildi → parti ikiye bölünür (`splittable`), tek satırda o satır atlanır (`per_item`);
- model içerik nedeniyle reddetti → o satır atlanır (`per_item`, yeniden denenmez).

İstem (prompt) İngilizce yazılır (modeller talimatı en tutarlı İngilizcede izler); çıktı Türkçedir. Her partiyle
birlikte sahnedeki önceki/sonraki satırlar (`context_before`, `context_after`) gönderilir. Hedef Türkçe ise isteme
Türkçe üslup kuralları (`TURKISH_STYLE`) eklenir. Redaksiyonda (`Scene.revise`) model mevcut çeviriyi talimata göre
düzeltir. Ayrıntılar: docs/translation.md
"""

from __future__ import annotations

import copy
import json
import logging
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Collection, Sequence
from typing import Any

from nxceviri.core.translate import placeholders
from nxceviri.core.translate.providers.base import (
    BatchItem,
    BatchResult,
    ContextLine,
    GlossaryTerm,
    ProviderError,
    Scene,
)

log = logging.getLogger(__name__)

#: Karakterden belirteç tahmini (Türkçe/İngilizce/Japonca için ihtiyatlı ortalama) ve güvenlik payı.
_CHARS_PER_TOKEN = 3

#: CJK (kana, Kanji/Çince, Hangul) karakterleri: yaygın alt sözcük sözlüklerinde bu yazılar sık geçmediğinden bir
#: karakter çoğunlukla ~1 belirteç tutar (bazen bayt düzeyine bölünüp daha fazla); Latin için /3 kalır.
_CJK_TOKENS_PER_CHAR = 1
_CJK_RANGES = (
    (0x3040, 0x30FF),  # Hiragana + Katakana
    (0x3400, 0x4DBF),  # CJK Uzantı A
    (0x4E00, 0x9FFF),  # CJK Birleşik İdeogramlar
    (0xAC00, 0xD7AF),  # Hangul heceleri
    (0xFF66, 0xFF9F),  # Yarım genişlikli katakana
)


def _count_cjk(text: str) -> int:
    return sum(1 for ch in text if any(lo <= ord(ch) <= hi for lo, hi in _CJK_RANGES))


def estimate_tokens(text: str) -> int:
    """Metnin kaba belirteç sayısı: Latin karakter/3, CJK karakter başına ~1."""
    cjk = _count_cjk(text)
    return math.ceil((len(text) - cjk) / _CHARS_PER_TOKEN) + cjk * _CJK_TOKENS_PER_CHAR


def prompt_weight(messages: Sequence[dict[str, str]]) -> int:
    """İstemin `choose_num_ctx` için "eşdeğer karakter" sayısı (tahmini belirteç × 3)."""
    return sum(estimate_tokens(m["content"]) for m in messages) * _CHARS_PER_TOKEN


LANGUAGE_NAMES_EN = {
    "en": "English",
    "ja": "Japanese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "ru": "Russian",
    "zh": "Chinese",
    "ko": "Korean",
    "pt": "Portuguese",
    "tr": "Turkish",
}

_CODE_RULES = """1. Tokens like ⟦1⟧, ⟦2⟧ are game control codes (colors, variables, button icons, line styles). \
Copy every token exactly, keep the same number of tokens and keep them in the same order. Never translate, renumber, \
remove or add tokens. A token that means a line break must stay between the same parts of the sentence as in \
the source (split the translation at the matching place); never move such tokens to the end of the text.
2. Output plain text only: never add HTML/XML tags (<div>, <p>, <br>, <b> …), entities (&nbsp;) or Markdown \
that are not in the source. Keep line breaks (\\n) where they are; do not add new ones. No translated line may \
be longer than the longest line of its source text.
3. Use the glossary translations exactly when a glossary term appears. Glossary entries without a translation \
are background notes (who a character is, how they speak, what a place is): use them to understand the scene and \
to keep voices consistent, but never copy the note into a translation. Tokens that wrap a word or phrase \
(for example highlighted names) must wrap the translation of that same word or phrase.
4. If an item has max_length, the translation must not be longer than that many characters.
5. Keep names, tone and each speaker's voice consistent; a sentence may continue from one item to the next.
6. Answer only with JSON, one entry for every item, no explanations or notes:
{{"translations": [{{"id": "<item id>", "text": "<translation>"}}]}}"""

_INPUT_NOTES = """- "items" are consecutive lines of the game (dialogue, subtitles or menu text) in the order they \
appear.
- "context_before" and "context_after" are the lines right before and after the items, with their \
current translation when there is one. Use them only to understand the scene: who speaks, what "it", "that" \
or "they" refers to, what a short reply answers. Never translate or return them.
- "fix" on an item names a problem found in an earlier attempt. Your answer for that \
item must not have it.
- "codes" on an item says what each token is, for example "Satır sonu" (a line break: the text continues on a \
new line there; put the token where a natural line break falls in your translation) or "Değişken" (a value the \
game inserts, such as a name or number)."""

_TRANSLATE_PROMPT = (
    """You are an experienced video game localizer. Translate game text from {source} into {target}. Write \
what a native {target} speaker would actually say in this scene: natural, idiomatic and in the game's tone. \
A word-for-word translation is a failure.

Input:
"""
    + _INPUT_NOTES
    + """

Strict rules:
"""
    + _CODE_RULES
)

_REVISE_PROMPT = (
    """You are an experienced {target} video game editor. Every item has the {source} original ("text") and its \
current {target} translation ("current"). Rewrite the translations as the editor's "instruction" asks. If there \
is no instruction, only fix the problems named in "fix" and change nothing else.

Input:
"""
    + _INPUT_NOTES
    + """
- An item with an empty "current" has no translation yet: translate it.

Strict rules:
0. Stay faithful to the original's meaning. Keep what is already good: if an item already follows the \
instruction and these rules, return its current translation unchanged.
"""
    + _CODE_RULES
)

#: Türkçe makine çevirisinin tipik kusurları ve doğal karşılıkları (istemde modele kural olarak verilir).
TURKISH_STYLE = """

Turkish style (machine translations usually fail here):
- Turkish drops subject pronouns. Do not write ben/sen/o/biz/siz/onlar unless the original stresses or contrasts \
them ("You enjoy it! I won't!" → "Sen çıkar keyfini! Ben çıkarmam!").
- Do not render every "it", "this", "that", "they", "there" or "some" as bu/şu/o/onlar/orada/bazı. Turkish \
usually leaves the object implicit or names it: "I can't believe it." → "İnanamıyorum.", "They like soccer." → \
"Futbolu seviyorlar."
- Do not start a sentence with "Ve" for "And": use "Bir de", "Hem", "Üstelik" or drop it.
- "Yes", "No" or "Well" at the start of a reply are often fillers. Write what the speaker means ("Olsun", \
"İyi de", "Ama", "Yok", "Hı hı") or drop it.
- Prefer spoken Turkish and idioms to dictionary meanings: "Seriously!" → "Ciddiyim!", "That's the limit!" → \
"Bu kadarı da fazla!", "Let's just relax." → "Biraz kafa dinleyelim."
- A short reply ("Not me.", "Me too.", "Why?") answers the line before it; say what a Turkish speaker would say \
there ("Have a drink." → "Not me." → "Ben içmem.").
- Repetition for emotion stays natural: "No, no, no." → "Yok, yok, yok." or "Olmaz, olmaz."
- Use Turkish word order (verb last) and possessive suffixes instead of benim/senin unless stressed.
- Keep the register of the scene: friends and family speak casually (sen)."""

#: Bağlam satırlarının istemde kapladığı yeri sınırlar (çok uzun satırlar kısaltılır).
CONTEXT_LINE_CHARS = 300

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["id", "text"],
            },
        }
    },
    "required": ["translations"],
}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES_EN.get(code.split("-", maxsplit=1)[0].lower(), code)


_HINT_WORD_RE = re.compile(r"[^\W_]+")


def _key_hint(context: str) -> str:
    """Anahtar adından yalnızca sözcük ipucu ("Dialogue/Greet" → "Dialogue Greet", "ursa_desc" → "ursa desc").

    Kod gibi görünen ifade modelin çeviriye kopyalamasına yol açıyordu (ör. "/(ursa_desc)" çevirinin sonuna eklenip
    oyun dosyasında satırı bölüyordu); sözcük olarak verilince yine ipucu olur ama kopyalanacak bir kod kalmaz.
    """
    return " ".join(_HINT_WORD_RE.findall(context))


def _context_lines(lines: tuple[ContextLine, ...]) -> list[dict[str, str]]:
    out = []
    for line in lines:
        entry = {"text": line.source[:CONTEXT_LINE_CHARS]}
        if line.translation:
            entry["translation"] = line.translation[:CONTEXT_LINE_CHARS]
        out.append(entry)
    return out


def _code_notes(item: BatchItem) -> dict[str, str]:
    """Maddede geçen yer tutucuların anlamı: {"⟦1⟧": "Satır sonu"}."""
    out = {}
    for n in dict.fromkeys(placeholders.tokens_in(item.text)):
        if 0 < n <= len(item.codes) and item.codes[n - 1]:
            out[placeholders.token(n)] = item.codes[n - 1]
    return out


_GAME_NOTES = """

Game notes from the translator (the game, its characters, the wanted tone and word choices). Follow them in every item:
"""


_JOB_INSTRUCTION = """

Instruction from the translator for the lines in this job (for example what kind of text they are). Follow it \
together with the rules above; the rules on tokens and JSON always win:
"""


def system_prompt(
    source_lang: str, target_lang: str, revise: bool = False, notes: str = "", instruction: str = ""
) -> str:
    """Sistem istemi. Oyun notları (`notes`) ve çeviri talimatı (`instruction`, yalnızca çeviride) her partide
    aynı olduğu için buradadır, kullanıcı mesajında değil: modeller sistem talimatına daha sıkı uyar ve Ollama
    değişmeyen istem başını yeniden işlemez. Redaksiyon talimatı kullanıcı mesajında gider (`instruction`)."""
    template = _REVISE_PROMPT if revise else _TRANSLATE_PROMPT
    prompt = template.format(source=language_name(source_lang), target=language_name(target_lang))
    if target_lang.split("-", maxsplit=1)[0].lower() == "tr":
        prompt += TURKISH_STYLE
    if notes.strip():
        prompt += _GAME_NOTES + notes.strip()
    if instruction.strip() and not revise:
        prompt += _JOB_INSTRUCTION + instruction.strip()
    return prompt


def build_messages(
    items: list[BatchItem],
    source_lang: str,
    target_lang: str,
    context: str,
    glossary: list[GlossaryTerm],
    *,
    scene: Scene | None = None,
) -> list[dict[str, str]]:
    """Modele gidecek sohbet mesajlarını kurar (test edilebilsin diye ayrı)."""
    scene = scene or Scene()
    payload: dict[str, Any] = {}
    if scene.revise and scene.instruction.strip():
        payload["instruction"] = scene.instruction.strip()
    if glossary:
        payload["glossary"] = [
            {
                "term": g.term,
                **({"translation": g.translation} if g.translation else {}),
                **({"note": g.note} if g.note else {}),
            }
            for g in glossary
        ]
    if scene.before:
        payload["context_before"] = _context_lines(scene.before)
    payload["items"] = [
        {
            "id": it.id,
            "text": it.text,
            **({"current": it.current} if scene.revise else {}),
            **({"where": hint} if (hint := _key_hint(it.context)) else {}),
            **({"max_length": it.max_length} if it.max_length else {}),
            **({"fix": it.fix} if it.fix else {}),
            **({"codes": codes} if (codes := _code_notes(it)) else {}),
        }
        for it in items
    ]
    if scene.after:
        payload["context_after"] = _context_lines(scene.after)
    return [
        {
            "role": "system",
            "content": system_prompt(source_lang, target_lang, scene.revise, context, scene.instruction),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


#: Bazı modellerin (özellikle Hugging Face'ten içe aktarılanların) yanıttan önce yazdığı düşünme bölümü:
#: <think>…</think> ve Gemma 4'ün kanal işaretleri (<|channel>thought … <channel|>).
_THINK_RE = re.compile(
    r"<(think|thinking|reasoning)>.*?</\1>|<\|channel\|?>.*?<\|?channel\|>",
    re.S | re.I,
)


def extract_translations(content: str, key: str = "translations") -> list[Any] | None:
    """Yanıttaki {"translations": [...]} (veya `key` adlı) liste; okunamıyorsa None.

    Biçim kısıtı (JSON şeması) çoğu modelde yalnızca JSON döndürür; içe aktarılmış modellerde JSON'un önünde
    düşünme bölümü, kod çiti (```json) veya açıklama olabilir. Düşünme bölümleri atılır, sonra metindeki her
    "{" konumundan JSON nesnesi okunmaya çalışılır; birden çok geçerli nesne varsa (ör. düşünürken yazılmış
    taslak) sonuncusu alınır.
    """
    text = _THINK_RE.sub("", content)
    decoder = json.JSONDecoder()
    found: list[Any] | None = None
    pos = text.find("{")
    while pos >= 0:
        try:
            parsed, end = decoder.raw_decode(text, pos)
        except ValueError:
            pos = text.find("{", pos + 1)
            continue
        rows = parsed.get(key) if isinstance(parsed, dict) else None
        if isinstance(rows, list):
            found = rows
        pos = text.find("{", end)
    return found


def results_from_rows(items: list[BatchItem], rows: list[Any]) -> list[BatchResult]:
    """Yanıttaki satırları maddelerle eşler; dönmeyen madde `None` ve açıklamayla gelir."""
    got: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str) and isinstance(row.get("text"), str):
            got.setdefault(row["id"], row["text"])
    return [BatchResult(it.id, got.get(it.id), "" if it.id in got else "Model bu satırı döndürmedi.") for it in items]


def split_system(messages: Sequence[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    """Sistem mesajlarını birleştirip ayırır (sistem metnini ayrı alanda isteyen API'ler için)."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    return system, [m for m in messages if m["role"] != "system"]


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Şemanın kopyası; her nesnede `additionalProperties: false` ve bütün alanlar `required` (katı JSON şeması
    isteyen API'ler: OpenAI `strict`, Claude yapılandırılmış çıktı)."""
    out = copy.deepcopy(schema)

    def close(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and isinstance(node.get("properties"), dict):
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                close(value)
        elif isinstance(node, list):
            for value in node:
                close(value)

    close(out)
    return out


def strip_schema_keys(schema: Any, keys: Collection[str]) -> Any:
    """Şemanın `keys` alanları atılmış kopyası (desteklemeyen API'ler için, ör. Gemini'de `additionalProperties`)."""
    if isinstance(schema, dict):
        return {k: strip_schema_keys(v, keys) for k, v in schema.items() if k not in keys}
    if isinstance(schema, list):
        return [strip_schema_keys(v, keys) for v in schema]
    return schema


#: `retry-after` başlığının en çok bu kadar saniyesine uyulur (daha uzun bekleme işi kilitlemesin).
MAX_RETRY_AFTER_S = 120.0


def parse_retry_after(value: str | None) -> float | None:
    """`retry-after` başlığındaki saniye; yoksa ya da okunamıyorsa None (tarih biçimi desteklenmez)."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    if seconds < 0 or not math.isfinite(seconds):
        return None
    return min(seconds, MAX_RETRY_AFTER_S)


def status_error(service: str, code: int, detail: str, retry_after_s: float | None = None) -> ProviderError:
    """Bir HTTP durum kodunu kullanıcıya gösterilecek Türkçe hataya ve yeniden deneme bayraklarına çevirir."""
    detail = detail.strip()[:300]
    if code in (401, 403):
        return ProviderError(
            f"{service} API anahtarı geçersiz ya da bu işlem için yetkisiz.",
            "Anahtarı hizmetin hesap sayfasından yeniden kopyalayıp Otomatik Çeviri penceresinde kaydedin."
            + (f" Hizmetin yanıtı: {detail}" if detail else ""),
        )
    if code == 404:
        return ProviderError(
            f"{service} modeli ya da adresi bulunamadı." + (f" ({detail})" if detail else ""),
            "Model adını denetleyin: “Modelleri Listele” ile hizmetteki modelleri görebilirsiniz.",
        )
    if code == 402:
        return ProviderError(
            f"{service} hesabınızda kredi ya da ödeme sorunu var.",
            "Hizmetin hesap sayfasından bakiyenizi denetleyin; çevrilenler kaydedildi.",
        )
    if code in (408, 409, 429, 529) or code >= 500:
        what = "çok fazla istek aldı" if code == 429 else f"geçici bir hata döndürdü (HTTP {code})"
        return ProviderError(
            f"{service} {what}; kısa bir süre beklenip yeniden denenecek.", retryable=True, retry_after_s=retry_after_s
        )
    return ProviderError(f"{service} isteği reddetti (HTTP {code})" + (f": {detail}" if detail else "."))


def timeout_error(service: str) -> ProviderError:
    return ProviderError(f"{service} zamanında yanıt vermedi.", "Parti yeniden denenecek.", retryable=True)


def connect_error(service: str) -> ProviderError:
    return ProviderError(
        f"{service} hizmetine bağlanılamadı.",
        "İnternet bağlantınızı ve adresi denetleyin; yerel sunucuysa çalıştığından emin olun.",
        retryable=True,
    )


def truncated_error(service: str) -> ProviderError:
    """Yanıt uzunluk sınırında kesildi: parti bölünür; tek satırda da kesiliyorsa o satır atlanır."""
    return ProviderError(
        f"{service}: modelin yanıtı uzunluk sınırında kesildi.",
        "Parti küçültülerek yeniden istenecek.",
        splittable=True,
        per_item=True,
    )


def unlisted_model_note(model: str) -> str:
    """Bağlantı testinde model listede yoksa eklenen not. Engel değildir: bazı hizmetler takma adları ya da her
    modeli listelemez; model gerçekten yoksa çeviri isteği zaten açık bir hata verir."""
    return f" '{model}' listede görünmüyor; adı doğruysa sorun değil, çeviride model hatası alırsanız listeden seçin."


def refusal_error(detail: str = "") -> ProviderError:
    """Model içerik nedeniyle yanıt vermedi: yeniden denemek işe yaramaz, tek satıra inilip o satır atlanır."""
    return ProviderError(
        "Model bu satırları çevirmeyi reddetti." + (f" ({detail})" if detail else ""),
        "Atlanan satırları elle ya da başka bir sağlayıcıyla çevirin.",
        per_item=True,
    )


def unreadable_answer_error() -> ProviderError:
    """Yanıt istenen JSON değil: parti yeniden denenir, sürerse bölünüp tek satırda o satır atlanır."""
    return ProviderError(
        "Model istenen biçimde yanıt vermedi.",
        "Parti tekrar denenecek; sorun sürerse başka bir model seçin. Modelin ne yazdığı günlükte "
        "(Yardım → Hata Kayıtları Klasörünü Aç).",
        retryable=True,
        per_item=True,
    )


class LLMProvider(ABC):
    """İstem kurma ve yanıt okuma ortaktır; alt sınıf yalnızca `chat_json` (taşıma) yazar."""

    name: str
    label: str
    model: str
    requires_api_key = True
    supports_glossary = True
    supports_instructions = True
    #: Bulut modellerinde istek başına gecikme yüksek, bağlam geniştir: partiler Ollama'dakinden büyüktür.
    max_batch_chars = 4000
    max_batch_items = 25

    @abstractmethod
    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        """Modelden `schema` biçiminde JSON yanıt ister ve metni döndürür (çeviri ve sözlük önerisi bunu kullanır)."""

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
        messages = build_messages(items, source_lang, target_lang, context, glossary, scene=scene)
        content = self.chat_json(messages, RESPONSE_SCHEMA)
        rows = extract_translations(content)
        if rows is None:
            raise self.unreadable_error(content)
        return results_from_rows(items, rows)

    def unreadable_error(self, content: str) -> ProviderError:
        """Yanıt istenen JSON değil: günlüğe yazılır (oyun metni; anahtar içermez), parti yeniden denenir."""
        log.warning("%s (%s) JSON yerine şunu döndürdü: %r", self.label, self.model, content[:600])
        return unreadable_answer_error()

    def estimate_cost(self, items: list[BatchItem]) -> str | None:
        """Fiyat yazılmaz (hizmete ve modele göre değişir); yalnızca gönderilecek metnin kaba belirteç sayısı."""
        tokens = sum(estimate_tokens(i.text) for i in items)
        return (
            f"Çevrilecek metin yaklaşık {tokens:,} belirteç; istem, bağlam satırları ve yanıtla birlikte "
            "kullanım bunun birkaç katı olur.".replace(",", ".")
        )

    @abstractmethod
    def close(self) -> None:
        """Bağlantıyı kapatır."""
