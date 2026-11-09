"""Sözlük önerisi: metinlerde sık geçen özel adları bulup Ollama'dan Türkçe karşılık istemek.

İki adımlıdır ve uydurmaya karşı sınırlıdır:

1. **Adaylar programla bulunur** (`find_candidates`): en az iki kez geçen, büyük harfle başlayan sözcük dizileri
   ("Silver Pines", "Old Mill", "Mara"). Yalnızca cümle başında geçen tek sözcükler (Welcome, Yes), tamamı büyük harf
   arayüz sözcükleri (MENU), sözlükte zaten olan terimler ve kontrol kodları atlanır.
2. **Model yalnızca bu adaylara karşılık önerir** (`suggest_glossary`): her aday örnek cümleleriyle gider; model
   çeviriyi, kısa bir notu (karakter adı, yer…) ve sözlüğe eklemeye değip değmediğini (`add`) döndürür. Listede
   olmayan terimler ve boş çeviriler atılır. Öneriler kullanıcı onaylamadan sözlüğe yazılmaz.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from nxceviri.core.progress import TaskContext
from nxceviri.core.project import TranslationRow
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.providers.base import GlossaryTerm, ProviderError
from nxceviri.core.translate.providers.ollama import extract_translations, language_name

log = logging.getLogger(__name__)

#: Bir istekte modele gönderilen aday sayısı.
BATCH_SIZE = 30
#: Varsayılan en çok aday sayısı (en sık geçenler).
MAX_CANDIDATES = 120
#: Aday sayılması için en az geçiş sayısı.
MIN_COUNT = 2
#: Her aday için modele gönderilen en çok örnek cümle.
MAX_EXAMPLES = 2

#: Sözcük ("O'Neil", "Saint-Clair" tek sözcük).
_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
#: Büyük harfli iki sözcüğün arasında izin verilen bağlaçlar ("Sword of Light", "Tower of the Moon").
_CONNECTORS = frozenset(("of", "de", "du", "la", "von", "van"))
#: Dizinin başından atılan sözcükler ("The Sheriff" → "Sheriff").
_LEADING = frozenset(("the", "a", "an"))
#: Hiç aday sayılmayan sözcükler.
_STOP = frozenset(("i", "i'm", "i'll", "i've", "i'd", "ok", "okay", "mr", "mrs", "ms", "dr"))
#: Cümle başı: metnin başı, satır başı veya cümle sonu işaretinden sonrası (tırnak ve boşluk atlanır).
_SENTENCE_START = re.compile(r"(?:^|[.!?…:]\s+|\n)[\s\"“'‘(«]*$")


@dataclass(frozen=True)
class TermCandidate:
    term: str
    count: int
    examples: tuple[str, ...]


@dataclass(frozen=True)
class TermSuggestion:
    term: str
    translation: str
    note: str
    count: int


class JsonChat(Protocol):
    """Sözlük önerisi için gereken model arayüzü (Ollama)."""

    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str: ...


def _runs(text: str) -> list[tuple[int, list[str]]]:
    """Yalnızca boşlukla ayrılmış, büyük harfle başlayan sözcük dizileri: (başlangıç konumu, sözcükler)."""
    words = list(_WORD.finditer(text))

    def joined(a: int) -> bool:  # a. ve a+1. sözcük yalnızca boşlukla mı ayrılmış?
        return a + 1 < len(words) and not text[words[a].end() : words[a + 1].start()].strip()

    def cap(a: int) -> bool:
        return words[a].group(0)[0].isupper()

    runs: list[tuple[int, list[str]]] = []
    i = 0
    while i < len(words):
        if not cap(i):
            i += 1
            continue
        j = i
        while joined(j):
            k = j + 1
            if not cap(k) and words[k].group(0) in _CONNECTORS:
                if joined(k) and words[k + 1].group(0) == "the":
                    k += 1
                if not (joined(k) and cap(k + 1)):
                    break
                k += 1
            elif not cap(k):
                break
            j = k
        runs.append((words[i].start(), [w.group(0) for w in words[i : j + 1]]))
        i = j + 1
    return runs


def _sequences(text: str) -> list[tuple[str, bool]]:
    """Metindeki büyük harfli diziler: (dizi, cümle başında mı)."""
    out: list[tuple[str, bool]] = []
    for start, run in _runs(text):
        words = run
        initial = bool(_SENTENCE_START.search(text[:start]))
        while words and words[0].casefold() in _LEADING:
            words = words[1:]
            initial = False
        if not words:
            continue
        term = " ".join(words)
        if term.casefold() in _STOP or any(len(w) > 1 and w.isupper() for w in words):
            continue
        out.append((term, initial and len(words) == 1))
    return out


def find_candidates(
    rows: Sequence[TranslationRow], existing: Sequence[GlossaryTerm], limit: int = MAX_CANDIDATES
) -> list[TermCandidate]:
    """Sözlüğe aday özel adlar, en sık geçenden başlayarak (eşitlikte ilk geçen önce)."""
    known = {t.term.casefold() for t in existing}
    counts: dict[str, int] = {}
    named: dict[str, str] = {}  # casefold → ilk görülen yazım
    examples: dict[str, list[str]] = {}
    mid_sentence: set[str] = set()
    for row in rows:
        text = placeholders.TOKEN_RE.sub(" ", row.source)
        for term, initial in _sequences(text):
            key = term.casefold()
            if key in known:
                continue
            named.setdefault(key, term)
            counts[key] = counts.get(key, 0) + 1
            if not initial:
                mid_sentence.add(key)
            shown = examples.setdefault(key, [])
            if len(shown) < MAX_EXAMPLES and row.source not in shown:
                shown.append(row.source)
    ranked = sorted((k for k in counts if counts[k] >= MIN_COUNT and k in mid_sentence), key=lambda k: -counts[k])
    return [TermCandidate(named[k], counts[k], tuple(examples[k])) for k in ranked[:limit]]


_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "translation": {"type": "string"},
                    "note": {"type": "string"},
                    "add": {"type": "boolean"},
                },
                "required": ["term", "translation", "note", "add"],
            },
        }
    },
    "required": ["terms"],
}

_PROMPT = """You are an experienced video game localizer building a glossary for translating a game from {source} \
into {target}. You get candidate terms found in the game text, each with example lines.

For every candidate return:
- "translation": how the term should be written in {target}. Keep personal names, brand names and most place \
names unchanged. Translate titles, ranks, items, skills and descriptive place names naturally (for example \
"Old Mill" → "Eski Değirmen").
- "note": a very short {target} note on what the term is (for example "karakter adı", "yer adı", "eşya"), written \
from the examples only. Do not invent facts.
- "add": false if the term is an ordinary word that happens to be capitalized (start of a sentence, a common \
greeting or exclamation) and does not need a fixed translation; otherwise true.

Answer only with JSON: {{"terms": [{{"term": "<candidate exactly as given>", "translation": "...", "note": "...", \
"add": true}}]}}"""

_NOTES = "\n\nNotes from the translator about the game:\n"


def _messages(batch: Sequence[TermCandidate], source_lang: str, target_lang: str, notes: str) -> list[dict[str, str]]:
    system = _PROMPT.format(source=language_name(source_lang), target=language_name(target_lang))
    if notes.strip():
        system += _NOTES + notes.strip()
    payload = {"terms": [{"term": c.term, "examples": list(c.examples)} for c in batch]}
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _ask(provider: JsonChat, batch: Sequence[TermCandidate], source_lang: str, notes: str) -> list[Any]:
    """Modelden partinin önerilerini ister; okunamayan yanıt bir kez yeniden istenir."""
    for attempt in range(2):
        try:
            content = provider.chat_json(_messages(batch, source_lang, "tr", notes), _SCHEMA)
        except ProviderError as exc:
            if not exc.retryable or attempt:
                raise
            log.info("Sözlük önerisi yeniden denenecek: %s", exc.message)
            continue
        rows = extract_translations(content, key="terms")
        if rows is not None:
            return rows
        log.warning("Sözlük önerisinde model JSON yerine şunu döndürdü: %r", content[:600])
    raise ProviderError(
        "Model terim önerilerini istenen biçimde (JSON) vermedi.",
        "Başka bir Ollama modeli seçip yeniden deneyin.",
    )


def suggest_glossary(
    provider: JsonChat,
    candidates: Sequence[TermCandidate],
    source_lang: str,
    notes: str,
    ctx: TaskContext,
    *,
    batch_size: int = BATCH_SIZE,
) -> list[TermSuggestion]:
    """Adaylar için modelin önerdiği sözlük maddeleri (adayların sırasıyla); onay kullanıcıdadır."""
    by_key = {c.term.casefold(): c for c in candidates}
    found: dict[str, TermSuggestion] = {}
    total = len(candidates)
    for start in range(0, total, batch_size):
        ctx.report(start, total, f"Terim önerileri: {total - start} terim kaldı")
        batch = candidates[start : start + batch_size]
        for row in _ask(provider, batch, source_lang, notes):
            if not isinstance(row, dict) or row.get("add") is not True:
                continue
            term, translation = str(row.get("term", "")).strip(), str(row.get("translation", "")).strip()
            candidate = by_key.get(term.casefold())
            if candidate is None or not translation:
                continue  # listede olmayan (uydurulmuş) terim veya boş çeviri
            found[candidate.term.casefold()] = TermSuggestion(
                candidate.term, translation, str(row.get("note", "")).strip(), candidate.count
            )
    ctx.report(total, total, "Terim önerileri hazır")
    return [found[k] for k in by_key if k in found]
