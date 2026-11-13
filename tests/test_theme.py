"""Tema erişilebilirliği: WCAG AA kontrastı ve görünür klavye odağı."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QStatusBar, QToolButton
from pytestqt.qtbot import QtBot

from nxceviri.gui import icons
from nxceviri.gui.theme import TOKENS, ThemeMode, _qss, apply_theme

_AA = 4.5

#: (ön plan belirteci, zemin belirteci) — iki temada da en az 4,5:1 olmalı.
_PAIRS = [
    *(("text", bg) for bg in ("bg", "surface", "surface2", "selection")),
    *(("muted", bg) for bg in ("bg", "surface", "surface2")),
    ("accent", "bg"),
    ("accent", "surface"),
    ("accent_text", "accent"),
    ("accent_text", "accent_hover"),
    ("success", "success_bg"),
    ("warning", "warning_bg"),
    ("danger", "danger_bg"),
]


def _luminance(color: str) -> float:
    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize(("fg", "bg"), _PAIRS)
def test_token_pairs_meet_wcag_aa(scheme: str, fg: str, bg: str) -> None:
    tokens = TOKENS[scheme]
    assert _ratio(tokens[fg], tokens[bg]) >= _AA, f"{scheme}: {fg}/{bg}"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_selection_stays_distinct_from_surface(scheme: str) -> None:
    """Tabloda seçili satır zeminden ayrışmalı (koyulaştırılan `selection` bunu bozmuştu)."""
    tokens = TOKENS[scheme]
    minimum = {"light": 1.25, "dark": 1.35}[scheme]  # özgün değerler: açık 1,28; koyu 1,40
    assert _ratio(tokens["selection"], tokens["surface"]) >= minimum


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize(
    "selector",
    [
        "QPushButton:focus",
        'QPushButton[kind="primary"]:focus',
        'QPushButton[kind="flat"]:focus',
        'QToolButton[role="statusChip"]:focus',
        'QToolButton[role="chip"]:focus',
        'QToolButton[role="viewTool"]:focus',
        'QToolButton[role="link"]:focus',
        'QStatusBar QToolButton[role="problems"]:focus',
        'QStatusBar QToolButton[role="keys"]:focus',
        "QLineEdit:focus",
        "QComboBox:focus",
        "QSpinBox:focus",
        "QPlainTextEdit:focus",
        "QCheckBox::indicator:focus",
        "QListWidget#stepNav:focus",
    ],
)
def test_qss_has_focus_rule(scheme: str, selector: str) -> None:
    qss = _qss(TOKENS[scheme])
    rules = [part for part in qss.split("}") if selector in part.split("{")[0].replace("\n", " ")]
    assert rules, f"{selector} için odak kuralı yok"
    assert TOKENS[scheme]["accent"] in "".join(rules) or TOKENS[scheme]["text"] in "".join(rules)


@pytest.fixture
def themed_app(qtbot: QtBot) -> Iterator[QApplication]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    icons.clear_cache()
    yield app
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)
    icons.clear_cache()


@pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
@pytest.mark.parametrize("kind", [None, "primary", "flat"])
def test_focus_keeps_button_size(themed_app: QApplication, qtbot: QtBot, mode: ThemeMode, kind: str | None) -> None:
    apply_theme(themed_app, mode)
    button = QPushButton("Dışa Aktar")
    if kind:
        button.setProperty("kind", kind)
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)
    button.activateWindow()
    unfocused = button.sizeHint()
    button.setFocus()
    qtbot.waitUntil(button.hasFocus)
    button.style().unpolish(button)
    button.style().polish(button)
    assert button.sizeHint() == unfocused


@pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
def test_focus_keeps_line_edit_size(themed_app: QApplication, qtbot: QtBot, mode: ThemeMode) -> None:
    apply_theme(themed_app, mode)
    edit = QLineEdit("metin")
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    edit.activateWindow()
    unfocused = edit.sizeHint()
    edit.setFocus()
    qtbot.waitUntil(edit.hasFocus)
    edit.style().unpolish(edit)
    edit.style().polish(edit)
    assert edit.sizeHint() == unfocused


#: Odak kuralları eklenmeden önceki QSS'ten, kenarlık eklenen rollerin kuralları (boyut kıyası için).
_LEGACY_TOOL_QSS = """
    QWidget { font-size: 10pt; }
    QToolButton[role="statusChip"] { border: none; border-radius: 9px; padding: 3px 10px; font-weight: 600; }
    QToolButton[role="viewTool"] { border: none; border-radius: 6px; padding: 5px; }
    QToolButton[role="link"] { border: none; background: transparent; padding: 2px 6px; }
    QStatusBar QToolButton[role="problems"] { border: none; padding: 0 2px; }
    QStatusBar QToolButton[role="keys"] { border: none; padding: 0 2px; }
"""


def _role_sizes() -> dict[str, tuple[int, int]]:
    status_bar = QStatusBar()
    sizes: dict[str, tuple[int, int]] = {}
    for role in ("problems", "keys", "viewTool", "link", "statusChip"):
        button = QToolButton(status_bar if role in ("problems", "keys") else None)
        button.setText("Sorun 3")
        button.setProperty("role", role)
        hint = button.sizeHint()
        sizes[role] = (hint.width(), hint.height())
    return sizes


def test_role_tool_buttons_keep_pre_focus_size(themed_app: QApplication) -> None:
    """Saydam kenarlık eklenen roller, değişiklikten önceki QSS ile aynı sizeHint'i verir."""
    themed_app.setStyleSheet(_LEGACY_TOOL_QSS)
    legacy = _role_sizes()
    apply_theme(themed_app, ThemeMode.LIGHT, 10)
    assert _role_sizes() == legacy
