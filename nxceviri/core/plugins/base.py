"""Eklenti yazarları için taban sınıf: sözleşmenin isteğe bağlı üyelerine makul varsayılanlar verir.

Bir eklenti yalnızca `name`, `label`, `detect`, `extract` ve `inject`'i tanımlar; gerisi (bağlam toplama,
dil, aday süzgeci) gerekmedikçe varsayılan kalır.
"""

from __future__ import annotations

from collections.abc import Mapping

from nxceviri.core.formats.base import Context, TextEntry


class FormatPluginBase:
    name: str = ""
    label: str = ""
    #: True ise yalnızca tarama raporunda metin adayı olan dosyalar denenir.
    candidates_only: bool = False
    #: Boş değilse yalnızca adı bu uzantılarla biten (küçük harf) dosyalar açılır.
    path_suffixes: tuple[str, ...] = ()

    def detect(self, path: str, head: bytes) -> bool:
        raise NotImplementedError

    def collect_context(self, data: bytes, path: str) -> dict[object, object]:
        return {}

    def language(self, data: bytes) -> str | None:
        return None

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        raise NotImplementedError

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        raise NotImplementedError
