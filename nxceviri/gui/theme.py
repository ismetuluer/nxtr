"""Açık / koyu tema. Renkler tek yerde (TOKENS) tanımlanır; QSS bunlardan üretilir."""

from __future__ import annotations

import tempfile
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication


class ThemeMode(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


THEME_LABELS = {ThemeMode.SYSTEM: "Sistem", ThemeMode.LIGHT: "Açık", ThemeMode.DARK: "Koyu"}

TOKENS: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#F4F5F7",
        "surface": "#FFFFFF",
        "surface2": "#EEF0F3",
        "border": "#D8DCE2",
        "text": "#1B1F24",
        "muted": "#5B6470",
        "accent": "#2F6FEB",
        "accent_hover": "#2459C2",
        "accent_text": "#FFFFFF",
        "selection": "#D6E4FD",
        "success": "#1A7F37",
        "success_bg": "#E4F3E8",
        "redacted": "#6F42C1",
        "warning": "#8A5A00",
        "warning_bg": "#FFF3D1",
        "danger": "#B42318",
        "danger_bg": "#FDECEA",
        "drop_bg": "#F7F9FC",
        "issue_markup": "#A21CAF",
        "issue_length": "#C2410C",
        "issue_lines": "#0E7490",
    },
    "dark": {
        "bg": "#15171B",
        "surface": "#1E2126",
        "surface2": "#292D34",
        "border": "#363B44",
        "text": "#E6E8EB",
        "muted": "#9AA3AE",
        "accent": "#5B8DEF",
        "accent_hover": "#77A1F2",
        "accent_text": "#0E1116",
        "selection": "#24395F",
        "success": "#4AC26B",
        "success_bg": "#13301C",
        "redacted": "#B392F0",
        "warning": "#E3B341",
        "warning_bg": "#3A2E0F",
        "danger": "#F47067",
        "danger_bg": "#3D1717",
        "drop_bg": "#1A1D22",
        "issue_markup": "#E879F9",
        "issue_length": "#FB923C",
        "issue_lines": "#22D3EE",
    },
}


def resolve(mode: ThemeMode) -> str:
    if mode == ThemeMode.SYSTEM:
        scheme = QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
    return mode.value


#: Seçilebilir yazı boyutları (punto). Varsayılan 10.
FONT_SIZES = (9, 10, 11, 12, 14, 16, 18)
DEFAULT_FONT_SIZE = 10


def clamp_font_size(value: float) -> int:
    """Geçerli en yakın yazı boyutu (geçersiz ayar değerlerine karşı)."""
    return int(min(FONT_SIZES, key=lambda size: abs(size - value)))


_CHECK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="3.2" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
)


def _check_mark(color: str) -> str:
    """İşaretli onay kutusunun tik simgesi (QSS `image:` için dosya yolu; renk başına bir kez yazılır)."""
    folder = Path(tempfile.gettempdir()) / "nxtr-tema"
    path = folder / f"tik-{color.lstrip('#').lower()}.svg"
    if not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(_CHECK_SVG.format(color=color), encoding="utf-8")
    return path.as_posix()


def _qss(t: dict[str, str], pt: int = DEFAULT_FONT_SIZE) -> str:
    def size(factor: float) -> str:
        return f"{round(pt * factor, 1)}pt"

    check = _check_mark(t["accent_text"])
    return f"""
    QCheckBox::indicator, QAbstractItemView::indicator {{
        width: 14px; height: 14px; border: 1px solid {t["muted"]}; border-radius: 3px; background: {t["surface"]};
    }}
    QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{
        background: {t["accent"]}; border-color: {t["accent"]}; image: url({check});
    }}
    QCheckBox::indicator:disabled, QAbstractItemView::indicator:disabled {{ border-color: {t["border"]}; }}
    QWidget {{ color: {t["text"]}; font-size: {pt}pt; }}
    QMainWindow, QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {t["bg"]}; }}
    QFrame#card {{ background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 10px; }}
    QFrame#statCard {{ background: {t["surface2"]}; border-radius: 8px; }}
    QLabel[role="pageTitle"] {{ font-size: {size(1.7)}; font-weight: 600; }}
    QLabel[role="cardTitle"] {{ font-size: {size(1.2)}; font-weight: 600; }}
    QLabel[role="muted"] {{ color: {t["muted"]}; }}
    QLabel[role="statValue"] {{ font-size: {size(1.8)}; font-weight: 600; }}
    QLabel[role="emptyTitle"] {{ font-size: {size(1.3)}; font-weight: 600; }}
    QLabel[role="badge"] {{ border-radius: 9px; padding: 3px 10px; font-weight: 600; }}
    QLabel[state="neutral"] {{ background: {t["surface2"]}; color: {t["muted"]}; }}
    QLabel[state="success"] {{ background: {t["success_bg"]}; color: {t["success"]}; }}
    QLabel[state="warning"] {{ background: {t["warning_bg"]}; color: {t["warning"]}; }}
    QLabel[state="danger"] {{ background: {t["danger_bg"]}; color: {t["danger"]}; }}
    QLabel[state="info"] {{ background: {t["selection"]}; color: {t["accent"]}; }}
    QToolButton[role="statusChip"] {{ border: none; border-radius: 9px; padding: 3px 10px; font-weight: 600; }}
    QToolButton[role="statusChip"][state="success"] {{ background: {t["success_bg"]}; color: {t["success"]}; }}
    QToolButton[role="statusChip"][state="warning"] {{ background: {t["warning_bg"]}; color: {t["warning"]}; }}
    QToolButton[role="statusChip"][state="danger"] {{ background: {t["danger_bg"]}; color: {t["danger"]}; }}
    QToolButton[role="statusChip"][state="neutral"] {{ background: {t["surface2"]}; color: {t["muted"]}; }}
    QToolButton[role="statusChip"][state="info"] {{ background: {t["selection"]}; color: {t["accent"]}; }}
    QToolButton[role="chip"] {{
        background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 12px; padding: 3px 10px;
    }}
    QToolButton[role="chip"]:hover {{ background: {t["surface2"]}; }}
    QToolButton[role="chip"]:checked {{
        background: {t["selection"]}; border-color: {t["accent"]}; color: {t["accent"]};
    }}
    QFrame#chipPopup {{ background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 8px; }}
    QLabel[role="danger"] {{ color: {t["danger"]}; }}
    QLabel[role="warning"] {{ color: {t["warning"]}; }}
    QLabel[role="fieldLabel"] {{ color: {t["muted"]}; font-weight: 600; }}
    QFrame#banner {{ border-radius: 8px; }}
    QFrame#banner[state="warning"] {{ background: {t["warning_bg"]}; }}
    QFrame#banner[state="danger"] {{ background: {t["danger_bg"]}; }}
    QFrame#banner[state="success"] {{ background: {t["success_bg"]}; }}
    QFrame#banner[state="warning"] QLabel {{ color: {t["warning"]}; }}
    QFrame#banner[state="danger"] QLabel {{ color: {t["danger"]}; }}
    QFrame#banner[state="success"] QLabel {{ color: {t["success"]}; }}
    QFrame#dropZone {{ background: {t["drop_bg"]}; border: 2px dashed {t["border"]}; border-radius: 10px; }}
    QFrame#dropZone[active="true"] {{ border-color: {t["accent"]}; background: {t["selection"]}; }}
    QFrame#dropZone:disabled {{ border-style: dotted; }}
    QPushButton {{
        background: {t["surface2"]}; border: 1px solid {t["border"]}; border-radius: 7px;
        padding: 6px 14px; min-height: 20px;
    }}
    QPushButton:hover {{ border-color: {t["accent"]}; }}
    QPushButton:disabled {{ color: {t["muted"]}; border-color: {t["surface2"]}; }}
    QPushButton[kind="primary"] {{
        background: {t["accent"]}; color: {t["accent_text"]}; border: none; font-weight: 600;
    }}
    QPushButton[kind="primary"]:hover {{ background: {t["accent_hover"]}; }}
    QPushButton[kind="primary"]:disabled {{ background: {t["surface2"]}; color: {t["muted"]}; }}
    QPushButton[kind="flat"] {{ background: transparent; border: none; color: {t["accent"]}; padding: 4px 6px; }}
    QWidget#stepNavColumn {{ background: {t["surface"]}; border-right: 1px solid {t["border"]}; }}
    QListWidget#stepNav {{ background: transparent; border: none; outline: none; padding: 4px 8px 12px 8px; }}
    QLabel[role="navTitle"] {{ font-weight: 600; font-size: {size(1.1)}; }}
    QTableView, QTableWidget, QTreeWidget, QListWidget, QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
        background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 6px;
        selection-background-color: {t["selection"]}; selection-color: {t["text"]};
        alternate-background-color: {t["surface2"]};
    }}
    QLineEdit, QComboBox, QSpinBox {{ padding: 4px 8px; min-height: 20px; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        background: {t["surface2"]}; color: {t["muted"]}; border-color: {t["surface2"]};
    }}
    QHeaderView::section {{
        background: {t["surface2"]}; color: {t["muted"]}; border: none; border-bottom: 1px solid {t["border"]};
        padding: 5px 8px; font-weight: 600;
    }}
    QProgressBar {{
        background: {t["surface2"]}; border: none; border-radius: 6px; height: 12px; text-align: center;
        color: {t["text"]};
    }}
    QProgressBar::chunk {{ background: {t["accent"]}; border-radius: 6px; }}
    QStatusBar {{ background: {t["surface"]}; color: {t["muted"]}; border-top: 1px solid {t["border"]}; }}
    QStatusBar::item {{ border: none; }}
    QStatusBar QFrame[segment="true"] {{ border: none; border-left: 1px solid {t["border"]}; background: transparent; }}
    QStatusBar QLabel {{ color: {t["muted"]}; }}
    QStatusBar QToolButton[role="problems"] {{ color: {t["danger"]}; border: none; padding: 0 2px; }}
    QStatusBar QToolButton[role="keys"] {{ border: none; padding: 0 2px; }}
    QStatusBar QProgressBar {{ background: {t["surface2"]}; border: none; border-radius: 2px; }}
    QStatusBar QProgressBar::chunk {{ background: {t["accent"]}; border-radius: 2px; }}
    QLabel#saveDot {{ border-radius: 4px; background: {t["muted"]}; }}
    QLabel#saveDot[state="success"] {{ background: {t["success"]}; }}
    QLabel#saveDot[state="warning"] {{ background: {t["warning"]}; }}
    QMenuBar {{ background: {t["surface"]}; }}
    QMenuBar::item:selected, QMenu::item:selected {{ background: {t["selection"]}; color: {t["text"]}; }}
    QMenu {{ background: {t["surface"]}; border: 1px solid {t["border"]}; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
    QScrollBar::handle {{ background: {t["border"]}; border-radius: 4px; min-height: 28px; min-width: 28px; }}
    QScrollBar::handle:hover {{ background: {t["muted"]}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QToolTip {{ background: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["border"]}; padding: 4px; }}
    QToolButton#viewButton {{ padding: 4px 22px 4px 10px; }}
    QToolButton[role="viewTool"] {{ border: none; border-radius: 6px; padding: 5px; }}
    QToolButton[role="viewTool"]:hover {{ background: {t["surface2"]}; }}
    QToolButton[role="viewTool"]:checked {{ background: {t["selection"]}; }}
    QCheckBox:disabled {{ color: {t["muted"]}; }}
    QToolButton[role="link"] {{ border: none; background: transparent; color: {t["accent"]}; padding: 2px 6px; }}
    QToolButton[role="link"]:hover {{ text-decoration: underline; }}
    QToolButton[role="link"]:disabled {{ color: {t["muted"]}; }}
    QToolButton#viewButton::menu-indicator {{ subcontrol-position: right center; right: 6px; }}
    """


#: `apply_theme`nin kurduğu etkin belirteçler (sistem modunda Windows vurgu rengiyle türetilmiş olabilir).
_active: list[dict[str, str]] = []

_ACCENT_TEXT_CANDIDATES = ("#FFFFFF", "#0E1116")
#: Vurgu rengi zemine (`surface`) bundan az kontrastlıysa kullanılmaz; sabit renge dönülür.
_MIN_ACCENT_SURFACE_CONTRAST = 2.0
_MIN_TEXT_CONTRAST = 4.5


_system_accent_color: list[QColor] = []


def _system_accent() -> QColor:
    """Windows'un vurgu rengi: uygulamanın kendi paleti kurulmadan önceki sistem paletinin `Accent` rolü.

    PySide6'da `QStyleHints.accentColor` açık değildir; ilk çağrıda okunup saklanır (testlerde değiştirilebilir).
    """
    if not _system_accent_color:
        _system_accent_color.append(QGuiApplication.palette().color(QPalette.ColorRole.Accent))
    return _system_accent_color[0]


def _relative_luminance(color: QColor) -> float:
    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color.redF()) + 0.7152 * channel(color.greenF()) + 0.0722 * channel(color.blueF())


def contrast_ratio(a: QColor, b: QColor) -> float:
    """WCAG kontrast oranı (1–21)."""
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _mix(top: QColor, bottom: QColor, amount: float) -> QColor:
    return QColor(
        round(top.red() * amount + bottom.red() * (1 - amount)),
        round(top.green() * amount + bottom.green() * (1 - amount)),
        round(top.blue() * amount + bottom.blue() * (1 - amount)),
    )


def derive_accent(tokens: dict[str, str], accent: QColor, dark: bool) -> dict[str, str]:
    """Verilen belirteçlerin kopyasında vurgu renklerini `accent`ten türetir.

    Vurgu geçersiz/saydamsa veya zemine (`surface`) kontrastı yetersizse belirteçler değişmeden döner.
    Vurgu üstündeki yazı rengi, kontrastı ≥ 4.5 olan beyaz ya da koyu renktir; ikisi de olmuyorsa daha iyisi.
    """
    result = dict(tokens)
    if not accent.isValid() or accent.alpha() < 255:
        return result
    surface = QColor(tokens["surface"])
    if contrast_ratio(accent, surface) < _MIN_ACCENT_SURFACE_CONTRAST:
        return result
    text = max(_ACCENT_TEXT_CANDIDATES, key=lambda c: contrast_ratio(QColor(c), accent))
    result["accent"] = accent.name()
    result["accent_hover"] = (accent.lighter(115) if dark else accent.darker(115)).name()
    result["selection"] = _mix(accent, surface, 0.30 if dark else 0.20).name()
    result["accent_text"] = text
    return result


def current_tokens() -> dict[str, str]:
    """Şu an uygulanmış temanın renkleri."""
    palette_bg = QApplication.palette().window().color()
    if _active and QColor(_active[0]["bg"]) == palette_bg:
        return _active[0]
    return TOKENS["dark" if palette_bg.lightness() < 128 else "light"]


def apply_theme(app: QApplication, mode: ThemeMode, font_size: int = DEFAULT_FONT_SIZE) -> str:
    """Temayı ve yazı boyutunu uygular; kullanılan şemayı ("light"/"dark") döndürür."""
    scheme = resolve(mode)
    font_size = clamp_font_size(font_size)
    font = app.font()
    font.setPointSizeF(float(font_size))
    app.setFont(font)
    system_accent = _system_accent()  # kendi paletimiz kurulmadan önce okunmalı
    t = TOKENS[scheme]
    if mode == ThemeMode.SYSTEM:
        t = derive_accent(t, system_accent, scheme == "dark")
    _active[:] = [t]
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: t["bg"],
        QPalette.ColorRole.WindowText: t["text"],
        QPalette.ColorRole.Base: t["surface"],
        QPalette.ColorRole.AlternateBase: t["surface2"],
        QPalette.ColorRole.Text: t["text"],
        QPalette.ColorRole.Button: t["surface2"],
        QPalette.ColorRole.ButtonText: t["text"],
        QPalette.ColorRole.Highlight: t["accent"],
        QPalette.ColorRole.HighlightedText: t["accent_text"],
        QPalette.ColorRole.PlaceholderText: t["muted"],
        QPalette.ColorRole.ToolTipBase: t["surface"],
        QPalette.ColorRole.ToolTipText: t["text"],
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t["muted"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t["muted"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(t["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(_qss(t, font_size))
    # `icons` temayı içe aktardığı için burada, işlev içinde alınır (döngüsel içe aktarma olmasın).
    from nxceviri.gui import icons  # noqa: PLC0415 - döngüsel içe aktarma

    icons.clear_cache()
    icons.refresh_icons()
    return scheme
