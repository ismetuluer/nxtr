"""Tema biçimi katmanı: renkten bağımsız şekil ve yazı tipi ayarları (köşe, çizgi, düğme stili, yazı aileleri).

`ThemeStyle` varsayılan değerleriyle uygulamanın bugünkü görünümünü birebir verir; konsol temaları yalnızca
farklı olan alanları değiştirir. Yazı tipi dosyaları `gui/fonts/<klasör>/` altında paketlenir (OFL-1.1) ve tema
ilk uygulandığında bir kez kaydedilir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QFontDatabase

from nxceviri.gui.scale import R4, R6, R8, R12

log = logging.getLogger(__name__)

#: Düğme stilleri: `flat` (bugünkü düz görünüm), `outline` (şeffaf, vurgu çerçeveli), `bevel` (alt kalınlık),
#: `hard` (sağ/alt sert gölge).
BUTTON_STYLES = ("flat", "outline", "bevel", "hard")
#: Adım işareti türleri (adım listesinin boyadığı simge/rozet): `default`; diğerleri sonraki aşamalar içindir.
STEP_MARKERS = ("default",)
NAV_POSITIONS = ("side", "top")


#: `TOKENS`ta olmayan, yalnızca konsol temalarının katmanında bulunan isteğe bağlı belirteçler → yoksa düşülen belirteç.
#: Gezinme sütunu: arka plan, yazı, soluk yazı, seçili zemin/yazı, üzerine gelme, simge. `edge`/`edge_primary`:
#: kabartmalı/sert gölgeli düğmenin kenar rengi (ikincil/birincil). `header_bg`/`header_text`: tablo başlığı.
#: `title`: sayfa başlığı rengi.
OPTIONAL_TOKENS: dict[str, str] = {
    "nav_bg": "surface",
    "nav_text": "text",
    "nav_muted": "muted",
    "nav_sel_bg": "selection",
    "nav_sel_text": "text",
    "nav_hover_bg": "surface2",
    "nav_icon": "accent",
    "edge": "border",
    "edge_primary": "edge",
    "header_bg": "surface2",
    "header_text": "muted",
    "title": "text",
}


def nav_color(tokens: dict[str, str], name: str) -> str:
    """İsteğe bağlı belirteç; tema tanımlamadıysa yedek belirtecin rengi (sistem vurgusuyla türetilmiş olabilir)."""
    value = tokens.get(name)
    if value:
        return value
    fallback = OPTIONAL_TOKENS[name]
    return tokens.get(fallback) or nav_color(tokens, fallback)


@dataclass(frozen=True)
class ThemeStyle:
    """Bir temanın şekli: köşe yarıçapları, çizgi kalınlığı, düğme stili, yazı tipleri, sabit şema."""

    #: Tema kimliği (QSS yapıcısını seçer); varsayılan stilde boş.
    key: str = ""

    #: Köşe yarıçapları (px): küçük gösterge/kaydırma, giriş/sekme, düğme, panel/satır, kart, çip/hap.
    radius_small: int = R4
    radius_control: int = R6
    radius_button: int = R8
    radius_panel: int = R8
    radius_card: int = R12
    radius_pill: int = R12
    #: Çerçeve kalınlığı (px).
    border: int = 1
    button: str = "flat"
    #: Yazı ailesi adları; boş = sistem yazı tipi. `heading_font` başlık etiketlerinde, `mono_font` sayılarda.
    body_font: str = ""
    heading_font: str = ""
    mono_font: str = ""
    #: Sayfa başlığı italik mi (italik dosya paketliyse).
    title_italic: bool = False
    #: Tema yalnızca bu şemada çalışır ("light" | "dark"); None = Sistem/Açık/Koyu seçimi geçerli.
    scheme: str | None = None
    #: Kaydedilecek yazı tipi klasörleri (`gui/fonts/` altında).
    fonts: tuple[str, ...] = ()
    step_marker: str = "default"
    nav_position: str = "side"
    #: Adım listesi tek renkle (nav_text / nav_sel_text) boyanır; anlamsal renkler (başarı, uyarı) kullanılmaz.
    nav_mono: bool = False

    def __post_init__(self) -> None:
        if self.button not in BUTTON_STYLES:
            raise ValueError(f"Bilinmeyen düğme stili: {self.button}")
        if self.nav_position not in NAV_POSITIONS:
            raise ValueError(f"Bilinmeyen gezinme konumu: {self.nav_position}")
        if self.scheme not in (None, "light", "dark"):
            raise ValueError(f"Bilinmeyen şema: {self.scheme}")


DEFAULT_STYLE = ThemeStyle()

FONT_ROOT = Path(__file__).parent / "fonts"

#: Kaydı yapılmış klasörler → Qt'nin verdiği aile adları (her klasör bir kez kaydedilir).
_registered: dict[str, list[str]] = {}


def register_fonts(folders: tuple[str, ...]) -> list[str]:
    """Klasörlerdeki `.ttf` dosyalarını Qt'ye kaydeder (klasör başına bir kez); kayıtlı aile adlarını döndürür."""
    families: list[str] = []
    for folder in folders:
        if folder not in _registered:
            names: list[str] = []
            for path in sorted((FONT_ROOT / folder).glob("*.ttf")):
                font_id = QFontDatabase.addApplicationFont(str(path))
                if font_id < 0:
                    log.warning("Yazı tipi yüklenemedi: %s", path)
                    continue
                names.extend(QFontDatabase.applicationFontFamilies(font_id))
            _registered[folder] = names
        families.extend(_registered[folder])
    return families
