"""Büyük harfle çizilen metinler: küçük büyük harf (smallcaps) / hepsi büyük harf stilleri.

Unity'nin TextMeshPro'su bu stillerde küçük harfleri .NET'in kültürden bağımsız kurallarıyla
büyütür; Türkçe kuralı bilmediği için `i` → `I` olur (`İ` olmalı). `ı` → `I` zaten doğrudur.
Çözüm: bu stille çizilen satırlarda çeviriyi dışa aktarırken `i` harflerini doğrudan `İ` yazmak;
büyük harf olduğundan oyun onu değiştirmez. Çeviri tablosundaki metin olduğu gibi kalır,
dönüşüm yalnızca moda yazılırken yapılır.

Hangi satırların büyük harfle çizildiği metinden anlaşılmaz (etiket yok, stil yazı bileşeninde);
kullanıcı tabloya (grup) veya tek tek satıra göre işaretler. İşaretler projede saklanır.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

GROUPS_KEY = "uppercase_groups"
ROWS_KEY = "uppercase_rows"
EXCEPT_KEY = "uppercase_except"


def dotted_capitals(text: str) -> str:
    """Küçük `i` harflerini `İ` yapar; yer tutucular (⟦n⟧) ve diğer harfler değişmez."""
    return text.replace("i", "İ")


Pair = tuple[str, str]  # (dosya, anahtar)


def _dump_pairs(pairs: frozenset[Pair]) -> str:
    return json.dumps(sorted([f, k] for f, k in pairs), ensure_ascii=False)


def _load_pairs(text: str) -> frozenset[Pair]:
    try:
        data = json.loads(text) if text else []
    except ValueError:
        return frozenset()
    if not isinstance(data, list):
        return frozenset()
    return frozenset(
        (x[0], x[1]) for x in data if isinstance(x, list) and len(x) == 2 and all(isinstance(s, str) for s in x)
    )


@dataclass(frozen=True)
class UppercaseRules:
    """Hangi satırlarda `i` → `İ` uygulanır.

    Bir satıra uygulanır: tablosu (grup) işaretliyse ya da kendisi işaretliyse; ama istisna
    listesindeyse uygulanmaz (ör. işaretli bir tabloda büyük harfle çizilmeyen tek satır).
    """

    groups: frozenset[str] = frozenset()  # grup adı (ör. "World_Sign"), grubun tüm satırları
    rows: frozenset[Pair] = frozenset()  # tek tek işaretli satırlar
    excluded: frozenset[Pair] = frozenset()  # istisna: tablo işaretli olsa da uygulanmayacak satırlar

    def applies(self, file: str, key: str, group: str) -> bool:
        if (file, key) in self.excluded:
            return False
        return group in self.groups or (file, key) in self.rows

    def __bool__(self) -> bool:
        return bool(self.groups or self.rows)

    def with_row(self, file: str, key: str, group: str, on: bool) -> UppercaseRules:
        """Tek satırı açar/kapatır. Tablo işaretliyken kapatmak satırı istisna yapar."""
        pair = (file, key)
        if on:
            return UppercaseRules(self.groups, self.rows | {pair}, self.excluded - {pair})
        rows = self.rows - {pair}
        excluded = self.excluded | {pair} if group in self.groups else self.excluded
        return UppercaseRules(self.groups, rows, excluded)

    def with_group(self, group: str, on: bool) -> UppercaseRules:
        return UppercaseRules(self.groups | {group} if on else self.groups - {group}, self.rows, self.excluded)

    def dump(self) -> tuple[str, str, str]:
        """Proje ayarlarına yazılacak (gruplar, satırlar, istisnalar) JSON metinleri."""
        return json.dumps(sorted(self.groups), ensure_ascii=False), _dump_pairs(self.rows), _dump_pairs(self.excluded)

    @classmethod
    def load(cls, groups: str, rows: str, excluded: str = "") -> UppercaseRules:
        """Kayıtlı JSON'dan okur; bozuk ya da boş değer işaretsiz sayılır."""
        try:
            g = json.loads(groups) if groups else []
        except ValueError:
            g = []
        names = frozenset(x for x in g if isinstance(x, str)) if isinstance(g, list) else frozenset()
        return cls(names, _load_pairs(rows), _load_pairs(excluded))
