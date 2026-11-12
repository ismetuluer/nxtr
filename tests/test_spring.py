"""Yay animasyonu: designbookmark.com/motion paylaşılan yay çözücüsünün (yarı örtük Euler, 4 alt adım, dt ≤ 1/30 s)
birebir taşınması ve kenar çubuğunun yayla daralıp açılması."""

from __future__ import annotations

import math

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from pytestqt.qtbot import QtBot

from nxceviri.gui.spring import SPRING_SOFT, Spring, SpringAnimator, integrate


def test_step_matches_the_reference_solver() -> None:
    """motion.js: a = -k(x - t) - c·v; v += a·dt; x += v·dt (kütle 1, yarı örtük Euler)."""
    s = Spring(x=0.0, v=0.0, target=100.0, k=260.0, c=24.0)
    s.step(0.01)
    assert s.v == pytest.approx(260.0 * 100.0 * 0.01)  # a = 26000 → v = 260
    assert s.x == pytest.approx(260.0 * 0.01)
    s.step(0.01)
    a = -260.0 * (s.x - 100.0) - 24.0 * s.v
    assert a > 0  # hâlâ hedefe doğru ivmelenir


def test_integrate_uses_four_substeps_and_clamps_dt() -> None:
    a = Spring(0.0, 0.0, 100.0, 260.0, 24.0)
    b = Spring(0.0, 0.0, 100.0, 260.0, 24.0)
    integrate(a, 1 / 30)  # 4 alt adım
    for _ in range(4):
        b.step(1 / 30 / 4)
    assert a.x == pytest.approx(b.x)
    c = Spring(0.0, 0.0, 100.0, 260.0, 24.0)
    integrate(c, 5.0)  # uzun duraksama (ör. pencere donması): dt 1/30'a kırpılır
    assert c.x == pytest.approx(a.x)


def test_soft_spring_overshoots_slightly_then_settles() -> None:
    k, c = SPRING_SOFT
    assert (k, c) == (260, 24)  # tokens.css --spring-soft
    assert c / (2 * math.sqrt(k)) < 1  # az sönümlü: hafif taşar, yay hissi buradan gelir
    s = Spring(0.0, 0.0, 100.0, k, c)
    peak = 0.0
    for _ in range(600):
        integrate(s, 1 / 60)
        peak = max(peak, s.x)
    assert 100.0 < peak < 110.0
    assert s.x == pytest.approx(100.0, abs=0.01)


def test_animator_reaches_target_exactly_and_finishes_once(qtbot: QtBot) -> None:
    seen: list[float] = []
    done: list[bool] = []
    anim = SpringAnimator(None, 0.0, 120.0, *SPRING_SOFT, on_value=seen.append, on_done=lambda: done.append(True))
    anim.start()
    qtbot.waitUntil(lambda: bool(done), timeout=5000)
    assert seen[-1] == 120.0  # son değer tam hedef (yuvarlama kalıntısı yok)
    assert done == [True]
    assert not anim.running


def test_animator_stop_is_silent_and_safe(qtbot: QtBot) -> None:
    done: list[bool] = []
    anim = SpringAnimator(None, 0.0, 50.0, *SPRING_SOFT, on_value=lambda _v: None, on_done=lambda: done.append(True))
    anim.start()
    anim.stop()
    anim.stop()
    qtbot.wait(100)
    assert done == []
    assert not anim.running


def test_retarget_keeps_velocity(qtbot: QtBot) -> None:
    seen: list[float] = []
    anim = SpringAnimator(None, 0.0, 100.0, *SPRING_SOFT, on_value=seen.append, on_done=lambda: None)
    anim.start()
    qtbot.waitUntil(lambda: len(seen) > 3, timeout=2000)
    velocity = anim.spring.v
    anim.retarget(0.0)
    assert anim.spring.v == velocity  # yön değişirken hız korunur: hareket sıçramaz
    assert anim.spring.target == 0.0
    anim.stop()


@pytest.mark.gui
def test_sidebar_uses_the_spring_and_clamps_to_the_icon_width(
    qtbot: QtBot, tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path

    from nxceviri.gui.step_nav import COLLAPSED_WIDTH
    from tests.test_statusbar import _make_window, _project

    assert isinstance(tmp_path, Path)
    monkeypatch.setattr("nxceviri.gui.main_window.animations_enabled", lambda: True)
    w = _make_window(qtbot, tmp_path, _project())
    w.show()
    widths: list[int] = []
    w.set_nav_collapsed(True)
    assert isinstance(w._nav_anim, SpringAnimator)

    def sample() -> bool:
        widths.append(w.nav_column.width())
        return w._nav_anim is None

    qtbot.waitUntil(sample, timeout=5000)
    assert min(widths) >= COLLAPSED_WIDTH  # yay taşsa da simgeler kırpılmaz
    assert w.nav_column.width() == COLLAPSED_WIDTH
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    w.dirty = False
    w.close()
