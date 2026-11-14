"""Tema erişilebilirliği: WCAG AA kontrastı ve görünür klavye odağı."""

from __future__ import annotations

import logging
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton, QSpinBox, QStatusBar, QToolButton
from pytestqt.qtbot import QtBot

from nxceviri.gui import icons
from nxceviri.gui.theme import _CHECK_SVG, TOKENS, ThemeMode, _check_mark, _qss, _svg_file, apply_theme

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
    ],
)
def test_qss_has_focus_rule(scheme: str, selector: str) -> None:
    qss = _qss(TOKENS[scheme])
    rules = [part for part in qss.split("}") if selector in part.split("{")[0].replace("\n", " ")]
    assert rules, f"{selector} için odak kuralı yok"
    assert TOKENS[scheme]["accent"] in "".join(rules) or TOKENS[scheme]["text"] in "".join(rules)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_qss_step_nav_has_no_focus_frame(scheme: str) -> None:
    """Kenar çubuğu listesi çevresinde odak çerçevesi çizilmez (seçim dolgusu yeter)."""
    assert "stepNav:focus" not in _qss(TOKENS[scheme])


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


def test_check_mark_rewrites_corrupted_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    path = Path(_check_mark("#FFFFFF"))
    path.write_text("", encoding="utf-8")  # boşalmış dosya
    assert Path(_check_mark("#FFFFFF")) == path
    assert path.read_text(encoding="utf-8") == _CHECK_SVG.format(color="#FFFFFF")


def test_check_mark_does_not_rewrite_valid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    path = Path(_check_mark("#FFFFFF"))
    writes: list[Path] = []
    real_write = Path.write_text

    def spy(self: Path, *args: object, **kwargs: object) -> int:
        writes.append(self)
        return real_write(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", spy)
    assert Path(_check_mark("#FFFFFF")) == path
    assert writes == []


def test_check_mark_survives_io_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    def broken(self: Path, *args: object, **kwargs: object) -> int:
        raise OSError("yazılamaz")

    monkeypatch.setattr(Path, "write_text", broken)
    with caplog.at_level(logging.WARNING):
        result = _check_mark("#ABCDEF")
    assert result.endswith("tik-abcdef.svg")
    assert any("tik" in r.message.lower() for r in caplog.records)


_ARROW_SELECTORS = (
    "QSpinBox::up-arrow",
    "QSpinBox::down-arrow",
    "QComboBox::down-arrow",
    "QRadioButton::indicator",
    "QRadioButton::indicator:checked",
)


def _rules_for(qss: str, selector: str) -> str:
    """`selector`ü tam olarak (virgüllü listelerin bir öğesi olarak) taşıyan kuralların gövdeleri."""
    bodies = []
    for part in qss.split("}"):
        head, _, body = part.partition("{")
        if selector in [s.strip() for s in head.split(",")]:
            bodies.append(body)
    return "\n".join(bodies)


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("selector", _ARROW_SELECTORS)
def test_qss_arrow_images_exist_as_svg(scheme: str, selector: str) -> None:
    rules = _rules_for(_qss(TOKENS[scheme]), selector)
    assert rules, f"{selector} için kural yok"
    paths = re.findall(r"image:\s*url\(([^)]+)\)", rules)
    if selector != "QRadioButton::indicator":
        assert paths, f"{selector} için image yok"
    for raw in paths:
        path = Path(raw)
        assert path.is_file()
        assert path.read_text(encoding="utf-8").lstrip().startswith("<svg")


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_qss_checked_radio_uses_accent(scheme: str) -> None:
    rules = _rules_for(_qss(TOKENS[scheme]), "QRadioButton::indicator:checked")
    assert TOKENS[scheme]["accent"] in rules


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_qss_radio_indicator_is_round(scheme: str) -> None:
    rules = _rules_for(_qss(TOKENS[scheme]), "QRadioButton::indicator")
    assert "width: 14px" in rules
    assert "border-radius: 7px" in rules


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("selector", ["QRadioButton::indicator:disabled", "QRadioButton::indicator:focus"])
def test_qss_radio_has_state_rules(scheme: str, selector: str) -> None:
    assert _rules_for(_qss(TOKENS[scheme]), selector)


def test_arrow_files_are_shared_helper_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    first = Path(_svg_file("deneme-abc", "<svg/>"))
    assert first.read_text(encoding="utf-8") == "<svg/>"
    assert first.parent == tmp_path / "nxtr-tema"
    assert _svg_file("deneme-abc", "<svg/>") == first.as_posix()


@pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
def test_spin_and_combo_keep_line_edit_height(themed_app: QApplication, qtbot: QtBot, mode: ThemeMode) -> None:
    """Ok düğmeleri eklenince yükseklikler düz metin kutusununkine yakın kalır (sayı kutusu özgünde 3 px uzundu)."""
    apply_theme(themed_app, mode)
    edit, spin, combo = QLineEdit("1"), QSpinBox(), QComboBox()
    combo.addItems(["a", "b"])
    for widget in (edit, spin, combo):
        qtbot.addWidget(widget)
    assert abs(spin.sizeHint().height() - edit.sizeHint().height()) <= 3
    assert abs(combo.sizeHint().height() - edit.sizeHint().height()) <= 2
