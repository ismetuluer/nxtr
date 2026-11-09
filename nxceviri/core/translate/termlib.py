"""Terminoloji kitaplığı: projelerden bağımsız, adlandırılmış terim listeleri ("DMC serisi").

Listeler kullanıcıya aittir (`%LOCALAPPDATA%/NXCeviri/terminoloji/<dosya>.json`); bir oyunda kurulan terminoloji
aynı serinin başka bir oyununda doğrudan eklenebilir, birden çok liste birleştirilebilir. Listenin görünen adı
dosyanın içindedir (dosya adı yalnızca güvenli karakterlerden üretilir). Okunamayan dosya atlanır ve günlüğe uyarı
yazılır; yazım önce geçici dosyaya yapılıp yerine taşınır.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Sequence
from pathlib import Path

from nxceviri.core.translate.providers.base import GlossaryTerm

log = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^\w\- ]+")


def termlib_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NXCeviri" / "terminoloji"


def _file_for(name: str) -> Path:
    """Görünen addan dosya: güvenli karakterler + kısa özet (farklı adlar çakışmasın)."""
    safe = _UNSAFE.sub("_", name).strip(" _")[:60] or "liste"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return termlib_dir() / f"{safe}-{digest}.json"


def _read(path: Path) -> tuple[str, list[GlossaryTerm]] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.warning("Terminoloji listesi okunamadı, atlandı (%s): %s", path.name, exc)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not isinstance(data.get("terms"), list):
        log.warning("Terminoloji listesi beklenen biçimde değil, atlandı: %s", path.name)
        return None
    terms = [
        GlossaryTerm(str(t.get("term", "")), str(t.get("translation", "")), str(t.get("note", "")))
        for t in data["terms"]
        if isinstance(t, dict) and str(t.get("term", "")).strip()
    ]
    return data["name"], terms


def _entries() -> dict[str, list[GlossaryTerm]]:
    folder = termlib_dir()
    if not folder.is_dir():
        return {}
    out: dict[str, list[GlossaryTerm]] = {}
    for path in sorted(folder.glob("*.json")):
        found = _read(path)
        if found is not None:
            out[found[0]] = found[1]
    return out


def list_names() -> list[str]:
    return sorted(_entries(), key=str.casefold)


def load_list(name: str) -> list[GlossaryTerm]:
    return _entries().get(name, [])


def save_list(name: str, terms: Sequence[GlossaryTerm]) -> None:
    """Listeyi kaydeder (aynı adlı liste varsa yerine yazar). Yazılamazsa `OSError`."""
    path = _file_for(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"name": name, "terms": [{"term": t.term, "translation": t.translation, "note": t.note} for t in terms]}
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def delete_list(name: str) -> None:
    _file_for(name).unlink(missing_ok=True)


def add_missing(
    existing: Sequence[GlossaryTerm], incoming: Sequence[GlossaryTerm]
) -> tuple[list[GlossaryTerm], int, int]:
    """Kitaplık listesini projeye katar: (yeni terminoloji, eklenen, korunan). Projede olan terim (büyük/küçük harf
    duyarsız) değişmez; projenin kendi karşılığı esastır."""
    merged = list(existing)
    known = {t.term.casefold() for t in existing}
    added = kept = 0
    for term in incoming:
        key = term.term.casefold()
        if key in known:
            kept += 1
            continue
        known.add(key)
        merged.append(term)
        added += 1
    return merged, added, kept
