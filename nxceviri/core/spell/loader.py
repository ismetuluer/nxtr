"""Paketlenen Türkçe sözcük süzgecini ve kullanıcı sözlüğünü yükler."""

from __future__ import annotations

import functools
import logging
from importlib import resources
from pathlib import Path

from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.userdict import UserDictionary

log = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def bundled_filter() -> BloomFilter | None:
    """Paketlenen `tr.bloom`; dosya eksik veya bozuksa None (yazım denetimi kapalı kalır, çökmez)."""
    try:
        return BloomFilter.from_bytes((resources.files("nxceviri") / "assets" / "spell" / "tr.bloom").read_bytes())
    except (OSError, ValueError) as exc:
        log.warning("Yazım süzgeci yüklenemedi: %s", exc)
        return None


def load_spell_checker(user_dictionary: UserDictionary | Path | None = None) -> SpellChecker | None:
    bloom = bundled_filter()
    if bloom is None:
        return None
    user = UserDictionary(user_dictionary) if isinstance(user_dictionary, Path) else user_dictionary
    return SpellChecker(bloom, user.words() if user is not None else ())
