"""Kontrol Et sekme karolarının rozet kuralları (Qt'siz, saf işlevler).

Her işlev sayılardan ya da durumlardan `Badge` ya da `None` (rozet yok) üretir; çizim `qa_tabbar.py`'dedir.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

TONE_DANGER = "danger"
TONE_WARNING = "warning"
TONE_SUCCESS = "success"

#: Rozetin içinde sayı ya da "!" yerine çizilen simgeler (simge adları `icons/` klasöründedir).
GLYPH_CHECK = "check"
GLYPH_BRUSH = "brush"


@dataclass(frozen=True)
class Badge:
    """`tone`: tema rengi anahtarı; `text`: rozetteki yazı (en çok 4 karakter) ya da boş; `glyph`: yazı yerine simge;
    `description`: ekran okuyucu ve ipucu için durum cümlesi."""

    tone: str
    description: str
    text: str = ""
    glyph: str = ""


def format_full(n: int) -> str:
    """Türkçe binlik ayırıcıyla tam sayı (2.223)."""
    return f"{n:,}".replace(",", ".")


def short_count(n: int) -> str:
    """Rozete sığan kısa sayı: 999 → "999", 2223 → "2,2B", 12345 → "12B", 1_250_000 → "1,2M" (hep ≤ 4 karakter)."""
    if n < 1000:
        return str(n)
    for unit, size in (("B", 1000), ("M", 1_000_000)):
        value = n / size
        if value < 1000 or unit == "M":
            if value >= 10:
                return f"{int(value)}{unit}"
            tenth = int(value * 10) / 10  # aşağı yuvarla: 9,99 "10B" görünmesin
            return f"{tenth:.1f}".replace(".", ",").removesuffix(",0") + unit
    return str(n)  # ulaşılmaz: M birimi koşulsuz döner


def issues_badge(checked: bool, errors: int, warnings: int) -> Badge | None:
    """Sorunlar: hata + uyarı sayısı, kırmızı; denetlenmediyse ya da sıfırsa rozet yok."""
    total = errors + warnings
    if not checked or total <= 0:
        return None
    return Badge(TONE_DANGER, f"{format_full(total)} bulgu", short_count(total))


def fit_badge(overflow_rows: int) -> Badge | None:
    """Sığdırma: taşabilecek satır sayısı, turuncu; sıfırsa rozet yok."""
    if overflow_rows <= 0:
        return None
    return Badge(TONE_WARNING, f"{format_full(overflow_rows)} satır taşıyor", short_count(overflow_rows))


def font_badge(scanned: bool, missing_letters: Sequence[str], covered_by_plugin: bool) -> Badge | None:
    """Font ve harfler: harflerin hepsi var ya da eklenti fontu yönetiyor → yeşil onay; eksik harf var → kırmızı "!".

    Fontlar taranmadıysa (ve eklenti de bir şey bildirmiyorsa) rozet yok."""
    if covered_by_plugin:
        return Badge(TONE_SUCCESS, "fontlar oyunun eklentisinde, harfler yönetiliyor", glyph=GLYPH_CHECK)
    if not scanned and not missing_letters:
        return None
    if missing_letters:
        return Badge(TONE_DANGER, f"eksik harf var: {' '.join(missing_letters)}", "!")
    return Badge(TONE_SUCCESS, "tüm Türkçe harfler var", glyph=GLYPH_CHECK)


def graphics_badge(checked: bool, problems: int, missing: int) -> Badge | None:
    """Grafik: çevrilmemiş ya da sorunlu resim varsa kırmızı fırça; hepsi hazırsa yeşil fırça; denetlenmediyse yok."""
    if not checked:
        return None
    if problems + missing > 0:
        return Badge(
            TONE_DANGER,
            f"{format_full(problems + missing)} resim çevrilmemiş ya da sorunlu",
            glyph=GLYPH_BRUSH,
        )
    return Badge(TONE_SUCCESS, "tüm resimler hazır", glyph=GLYPH_BRUSH)


def accessible_name(title: str, badge: Badge | None) -> str:
    """Karonun ekran okuyucu adı: "Sorunlar, 2.223 bulgu"."""
    return f"{title}, {badge.description}" if badge is not None else title
