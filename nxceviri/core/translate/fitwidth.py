"""Fontla genişlik denetimi: kapsam ayarını (`fitconfig.WidthRules`) ölçüm tablosu ve kutularla satırlara uygular.

Kutunun gerçek boyutu bilinmez; ölçüt oyunun kutuya sığdırdığı orijinal metnin aynı fontla ölçülen genişliğidir
(`widths`). Satır başına oran (çeviri / kendi orijinali) kısa metinlerde çok gürültülüdür (Türkçe doğal olarak
%20-30 uzun); bu yüzden varsayılan kutu kapsamdaki en geniş tek satırlı orijinaldir (`BOX_GROUP`, menü öğeleri aynı
kutuyu paylaşır). Kutular yalnızca orijinal metinlere bağlıdır: `build_measure` tüm satırlardan bir kez hesaplar,
denetimler ve düzenleme paneli aynı ölçümü kullanır (çeviri düzenlemek kutuyu değiştirmez).

Ölçüm tablosu proje ayarı `fit_widths`'te durur (`widths.dump`; yalnızca harf genişlikleri, font verisi değil):
fontlar tarandığında oyunun Latin fontundan yazılır, yoksa yerleşik yaklaşık tablo kullanılır (`load_table`).

Modül saftır; arayüz bilmez.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import NamedTuple

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.fit import DEFAULT_VARIABLE_WIDTH, split_lines
from nxceviri.core.translate.fitconfig import BOX_GROUP, FitConfig, WidthRules
from nxceviri.core.translate.widths import WidthTable, approximate_table, is_single_line, load, visible_pixels

#: Proje ayarı: ölçüm tablosu (`widths.dump` JSON'u); boş ya da yoksa yaklaşık tablo.
SETTING_WIDTHS = "fit_widths"
#: QA bulgu türü: çeviri satırı kutudan geniş (uyarı; dışa aktarmayı engellemez).
KIND_TOO_WIDE = "too_wide"

#: Kayan nokta payı: tam sınırdaki satır sorun değildir.
_EPSILON = 1e-9


def load_table(text: str) -> WidthTable:
    """Kayıtlı ölçüm tablosu; yoksa ya da bozuksa (uyarı `widths.load`'da) yaklaşık tablo."""
    stored = load(text) if text else None
    return stored if stored is not None else approximate_table()


def width_message(ratio: float, tolerance: float, box: str) -> str:
    """Bulgu iletisi: oran ve sınır yüzde olarak, kutunun neye göre alındığı."""
    basis = "kapsamdaki en geniş orijinale göre" if box == BOX_GROUP else "satırın kendi orijinaline göre"
    return f"Genişlik %{round(ratio * 100)}, sınır %{round((1 + tolerance) * 100)} ({basis}); oyunda taşabilir."


class WidthReading(NamedTuple):
    """Bir metnin kutuya göre genişliği: `ratio` 1.12 = %112; `limit` tolerans dahil üst oran (1.15)."""

    ratio: float
    limit: float
    over: bool
    box: str
    tolerance: float


@dataclass(frozen=True, eq=False)
class WidthMeasure:
    """Bir denetim turunun genişlik ölçümü: ayar, tablo ve kapsam kutuları (kapsam kimliği → genişlik).

    Kimlikle karşılaştırılır (`eq=False`): anlık denetim bağlamı aynı nesne kaldıkça önbelleğini korur.
    """

    config: FitConfig
    table: WidthTable
    boxes: Mapping[str, float]

    @property
    def active(self) -> bool:
        """Herhangi bir kapsamda genişlik denetimi açık mı."""
        return self.config.has_width_rules

    def _variable_width(self, row: TranslationRow) -> int:
        rules = self.config.rules_for_row(row)
        return rules.variable_width if rules is not None else DEFAULT_VARIABLE_WIDTH

    def reading(self, row: TranslationRow, text: str) -> WidthReading | None:
        """`text` (satırın düzenlenen çevirisi) kutuya göre ne kadar geniş; denetim kapalıysa ya da orijinal çok
        satırlıysa (diyalog; satırlar yeniden bölünür) `None`. Sınırın altındayken de oran verir (panel göstergesi)."""
        found = self.config.width_for_row(row) if self.active else None
        if found is None:
            return None
        rules, scope = found
        kind_of = self.config.kind_of_row(row)
        if not row.source.strip() or not is_single_line(row.source, kind_of):
            return None
        variable = self._variable_width(row)
        box = self.boxes.get(scope) if rules.box == BOX_GROUP else None
        base = box if box is not None else visible_pixels(row.source, kind_of, self.table, variable_width=variable)
        if base <= 0:
            return None
        measured = max(
            visible_pixels(line, kind_of, self.table, variable_width=variable) for line in split_lines(text, kind_of)
        )
        ratio = measured / base
        limit = 1 + rules.tolerance
        return WidthReading(ratio, limit, ratio > limit * (1 + _EPSILON), rules.box, rules.tolerance)

    def problem(self, row: TranslationRow) -> WidthReading | None:
        """Satırın çevirisi kutuyu toleranstan fazla aşıyorsa ölçümü; aşmıyorsa ya da çeviri boşsa `None`."""
        if not row.translation.strip():
            return None
        found = self.reading(row, row.translation)
        return found if found is not None and found.over else None


def _box_of(config: FitConfig, row: TranslationRow) -> tuple[str, WidthRules] | None:
    found = config.width_for_row(row)
    return (found[1], found[0]) if found is not None else None


def build_measure(rows: Iterable[TranslationRow], config: FitConfig, table: WidthTable) -> WidthMeasure:
    """Tüm satırlardan kapsam kutularını bir kez hesaplar (yalnızca kutusu kapsamdan alınan ayarlar için).

    Genişlik denetimi hiçbir kapsamda açık değilse satırlara bakılmaz.
    """
    boxes: dict[str, float] = {}
    if config.has_width_rules:
        for row in rows:
            found = _box_of(config, row)
            if found is None or found[1].box != BOX_GROUP or not row.source.strip():
                continue
            kind_of = config.kind_of_row(row)
            if not is_single_line(row.source, kind_of):
                continue
            rules = config.rules_for_row(row)
            variable = rules.variable_width if rules is not None else DEFAULT_VARIABLE_WIDTH
            width = visible_pixels(row.source, kind_of, table, variable_width=variable)
            scope = found[0]
            if width > boxes.get(scope, 0.0):
                boxes[scope] = width
    return WidthMeasure(config, table, boxes)
