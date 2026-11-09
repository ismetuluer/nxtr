"""Talimat kitaplığı: kullanıcının adlandırıp sakladığı çeviri ve redaksiyon talimatları.

Kitaplık projeye değil kullanıcıya aittir (`%LOCALAPPDATA%/NXCeviri/talimatlar.json`): bir oyunda yazılan talimat
başka bir oyunda da seçilebilir. Aynı ad ve türde kayıt yenisiyle değiştirilir. Okunamayan dosya boş sayılır ve
günlüğe uyarı yazılır; yazım önce geçici dosyaya yapılıp yerine taşınır (yarıda kalan yazım dosyayı bozmaz).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

KIND_TRANSLATE = "translate"
KIND_REVISE = "revise"
_KINDS = (KIND_TRANSLATE, KIND_REVISE)


@dataclass(frozen=True)
class SavedInstruction:
    name: str
    kind: str  # KIND_TRANSLATE (çevir / yeniden çevir) ya da KIND_REVISE (redaksiyon)
    text: str


def library_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NXCeviri" / "talimatlar.json"


def load_library(path: Path | None = None) -> list[SavedInstruction]:
    path = path or library_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.warning("Talimat kitaplığı okunamadı, boş sayılıyor: %s", exc)
        return []
    items: list[SavedInstruction] = []
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict):
            continue
        name, kind, text = entry.get("name"), entry.get("kind"), entry.get("text")
        if isinstance(name, str) and name.strip() and kind in _KINDS and isinstance(text, str):
            items.append(SavedInstruction(name.strip(), str(kind), text))
    return items


def _write(items: list[SavedInstruction], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def save_instruction(item: SavedInstruction, path: Path | None = None) -> list[SavedInstruction]:
    """Kaydı ekler (aynı ad ve türde varsa yerine koyar) ve güncel kitaplığı döndürür. Yazılamazsa `OSError`."""
    path = path or library_path()
    items = load_library(path)
    for i, old in enumerate(items):
        if old.name == item.name and old.kind == item.kind:
            items[i] = item
            break
    else:
        items.append(item)
    _write(items, path)
    return items


def delete_instruction(name: str, kind: str, path: Path | None = None) -> list[SavedInstruction]:
    path = path or library_path()
    items = [i for i in load_library(path) if not (i.name == name and i.kind == kind)]
    _write(items, path)
    return items
