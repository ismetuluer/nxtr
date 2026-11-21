"""Ek içerik (DLC) dosya adından okunur görüntü adı; yalnızca arayüzde gösterim içindir, hiçbir yere yazılmaz."""

from __future__ import annotations

import re

_GROUP = re.compile(r"\[([^\]]*)\]")
_TITLE_ID = re.compile(r"[0-9A-Fa-f]{16}")
_REGION_OR_KIND = re.compile(r"[A-Z]{2,4}")  # [USA] [EUR] [JPN] [UPD] [DLC]
_VERSION = re.compile(r"v\d+")
_SEPARATORS = " -–—:_.,"


def _is_meta(group: str) -> bool:
    text = group.strip()
    return bool(_TITLE_ID.fullmatch(text) or _REGION_OR_KIND.fullmatch(text) or _VERSION.fullmatch(text) or not text)


def readable_name(stem: str, base_name: str = "") -> str:
    """Dosya adından (uzantısız) DLC adı: TitleID, bölge ve sürüm olmayan ilk köşeli parantez grubu; yoksa ana oyun adı
    öneki atılmış gövde; o da boşsa dosya adının kendisi."""
    for match in _GROUP.finditer(stem):
        if not _is_meta(match.group(1)):
            return match.group(1).strip()
    body = _GROUP.sub("", stem).strip()
    prefix = base_name.strip()
    if prefix and body.casefold().startswith(prefix.casefold()):
        body = body[len(prefix) :]
    body = body.strip(_SEPARATORS)
    if body.casefold().endswith("standard edition"):
        body = body[: -len("standard edition")].strip(_SEPARATORS)
    return body or stem
