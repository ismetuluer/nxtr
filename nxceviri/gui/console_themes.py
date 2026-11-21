"""Konsol temaları: yalnızca renk değil şekil (köşe, çizgi, düğme stili) ve yazı tipi de farklı beş tema.

Her tema bir `ThemeStyle` (şekil, yazı tipi, sabit şema) ile bir belirteç katmanından (`TOKENS` üstüne bindirilir)
oluşur. Katmanda isteğe bağlı belirteçler de bulunur (`theme_style.OPTIONAL_TOKENS`: gezinme sütunu renkleri,
düğme kenar rengi, tablo başlığı, sayfa başlığı rengi); olmayan belirteç bugünkü renge düşer.
`extra_qss` varsayılan stil için boş döner; böylece varsayılan temanın QSS'i değişmez.
"""

from __future__ import annotations

from collections.abc import Callable

from nxceviri.gui.scale import R4, R8, R12, R16, R24
from nxceviri.gui.theme_style import DEFAULT_STYLE, ThemeStyle

#: Konsol teması adı → (stil, belirteç katmanı). Katman, stilin sabit şemasının `TOKENS` tablosuna bindirilir.
CONSOLE_THEMES: dict[str, tuple[ThemeStyle, dict[str, str]]] = {}


def _q(family: str) -> str:
    return f'"{family}"'


def _fonts(t: dict[str, str], st: ThemeStyle) -> str:
    rules: list[str] = []
    heading_roles = ("pageTitle", "cardTitle", "gameName", "navTitle", "emptyTitle")
    if st.heading_font:
        selectors = ", ".join(f'QLabel[role="{r}"]' for r in heading_roles)
        rules.append(f"{selectors} {{ font-family: {_q(st.heading_font)}; }}")
    stat_font = st.mono_font or st.heading_font
    if stat_font:
        rules.append(f'QLabel[role="statValue"] {{ font-family: {_q(stat_font)}; }}')
    if st.title_italic:
        rules.append('QLabel[role="pageTitle"] { font-style: italic; }')
    if "title" in t:
        rules.append(f'QLabel[role="pageTitle"] {{ color: {t["title"]}; }}')
    return "\n    ".join(rules)


def _buttons(t: dict[str, str], st: ThemeStyle) -> str:
    bw = st.border
    edge = t.get("edge", t["border"])
    edge_primary = t.get("edge_primary", edge)
    if st.button == "outline":
        return f"""
    QPushButton {{ background: transparent; border: 2px solid {t["accent"]}; color: {t["accent"]}; }}
    QPushButton:hover {{ background: {t["selection"]}; }}
    QPushButton:disabled {{ color: {t["muted"]}; border-color: {t["border"]}; background: transparent; }}
    QPushButton[kind="primary"] {{ background: {t["accent"]}; color: {t["accent_text"]}; }}
    QPushButton[kind="primary"]:hover {{ background: {t["accent_hover"]}; }}
    QPushButton[kind="primary"]:disabled {{
        background: {t["surface2"]}; color: {t["muted"]}; border-color: {t["surface2"]};
    }}
    QPushButton[kind="flat"] {{ background: transparent; border: {bw}px solid transparent; color: {t["accent"]}; }}"""
    if st.button == "bevel":
        return f"""
    QPushButton {{ border: {bw}px solid {t["border"]}; border-bottom: 4px solid {edge}; }}
    QPushButton[kind="primary"] {{ border-color: {t["accent"]}; border-bottom: 4px solid {edge_primary}; }}
    QPushButton:pressed {{ border-bottom-width: 1px; padding-top: 11px; }}
    QPushButton[kind="flat"] {{ background: transparent; border: {bw}px solid transparent; }}
    QPushButton[kind="flat"]:pressed {{ padding-top: 4px; }}"""
    if st.button == "hard":
        return f"""
    QPushButton {{
        background: {t["surface"]}; border: {bw}px solid {edge}; border-right-width: 4px; border-bottom-width: 4px;
    }}
    QPushButton:hover {{ background: {t["selection"]}; border-color: {edge}; }}
    QPushButton:pressed {{ border-right-width: {bw}px; border-bottom-width: {bw}px; padding: 10px 14px 6px 18px; }}
    QPushButton:disabled {{ color: {t["muted"]}; border-color: {t["muted"]}; background: {t["surface2"]}; }}
    QPushButton[kind="primary"] {{
        background: {t["accent"]}; color: {t["accent_text"]}; border-color: {edge_primary};
    }}
    QPushButton[kind="primary"]:hover {{ background: {t["accent_hover"]}; border-color: {edge_primary}; }}
    QPushButton[kind="primary"]:disabled {{
        background: {t["surface2"]}; color: {t["muted"]}; border-color: {t["muted"]};
    }}
    QPushButton[kind="flat"] {{
        background: transparent; border: {bw}px solid transparent; color: {t["accent"]}; padding: 4px;
    }}
    QPushButton[kind="flat"]:hover {{ background: {t["selection"]}; border-color: transparent; }}"""
    return ""


def _cift(t: dict[str, str], st: ThemeStyle, pt: int) -> str:
    return f"""
    QWidget#stepNavColumn {{
        background: {t["nav_bg"]}; border: none;
        border-top-right-radius: {R24}px; border-bottom-right-radius: {R24}px;
    }}
    QWidget#stepNavColumn QLabel {{ color: {t["nav_text"]}; }}
    QWidget#stepNavColumn QLabel[role="muted"] {{ color: {t["nav_muted"]}; }}
    QWidget#stepNavColumn QToolButton {{ color: {t["nav_text"]}; }}
    QWidget#stepNavColumn QToolButton:hover {{ background: {t["nav_hover_bg"]}; }}
    QToolButton[role="chip"], QToolButton[role="statusChip"] {{ padding: {R4}px {R12}px; }}"""


def _mor(t: dict[str, str], st: ThemeStyle, pt: int) -> str:
    edge = t["edge"]
    return f"""
    QFrame#card, QFrame#noticeCard {{ border-bottom: 5px solid {edge}; }}
    QHeaderView::section {{ color: {t["header_text"]}; background: {t["surface2"]}; }}
    QTabBar::tab:selected {{ color: {t["accent"]}; }}
    QToolButton[role="chip"] {{ border-bottom: 3px solid {edge}; }}"""


def _yesil(t: dict[str, str], st: ThemeStyle, pt: int) -> str:
    return f"""
    QTableView::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{
        border-left: 2px solid {t["accent"]}; color: {t["accent"]};
    }}
    QHeaderView::section {{ color: {t["accent"]}; background: {t["surface"]}; letter-spacing: 1px; }}
    QTabBar::tab:selected {{ background: transparent; color: {t["accent"]}; border-bottom: 2px solid {t["accent"]}; }}
    QProgressBar {{ border: 1px solid {t["border"]}; }}"""


def _gece(t: dict[str, str], st: ThemeStyle, pt: int) -> str:
    gradient = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0B1230, stop:1 #060A1C)"
    return f"""
    QMainWindow, QWidget#page {{ background: {gradient}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QWidget#stepNavColumn {{ background: rgba(17, 26, 58, 140); border-right: {st.border}px solid {t["border"]}; }}
    QTabBar::tab {{
        border-radius: 0; padding: {R8}px {R16}px; margin: 0 {R4}px 0 0; border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{ background: transparent; color: {t["accent"]}; border-bottom: 2px solid {t["accent"]}; }}
    QTabBar::tab:hover {{ background: transparent; border-bottom: 2px solid {t["border"]}; }}"""


def _piksel(t: dict[str, str], st: ThemeStyle, pt: int) -> str:
    edge = t["edge"]
    return f"""
    QFrame#card, QFrame#noticeCard, QFrame#fileRow, QFrame#chipPopup {{
        border: {st.border}px solid {edge}; border-right-width: 4px; border-bottom-width: 4px;
    }}
    QHeaderView::section {{ background: {t["header_bg"]}; color: {t["header_text"]}; border: none; }}
    QTabBar::tab:selected {{ background: {t["text"]}; color: {t["surface"]}; }}
    QTabBar::tab:hover {{ background: {t["surface2"]}; }}
    QToolButton[role="chip"] {{ border: {st.border}px solid {edge}; }}
    QProgressBar {{ border: {st.border}px solid {edge}; }}
    QMenu {{ border: {st.border}px solid {edge}; }}"""


_BUILDERS: dict[str, Callable[[dict[str, str], ThemeStyle, int], str]] = {
    "cift_kumanda": _cift,
    "mor_kup": _mor,
    "yesil_isik": _yesil,
    "gece_mavisi": _gece,
    "piksel_gri": _piksel,
}


def extra_qss(t: dict[str, str], st: ThemeStyle, pt: int) -> str:
    """Temanın temel QSS'in üstüne eklenen kuralları; varsayılan stil için boş metin döner."""
    if st == DEFAULT_STYLE:
        return ""
    parts = [_fonts(t, st), _buttons(t, st)]
    builder = _BUILDERS.get(st.key)
    if builder is not None:
        parts.append(builder(t, st, pt))
    return "\n    " + "\n".join(p for p in parts if p) + "\n    "
