"""Maskot: hâller, sekerek yer değiştiren gözler, animasyonsuz geçiş, gizleme ve her boyutta çizim."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.gui import mascot
from nxceviri.gui.mascot import (
    FACE_MOODS,
    MOOD_DONE,
    MOOD_ERROR,
    MOOD_IDLE,
    MOOD_SLEEP,
    MOOD_WORKING,
    TRAVEL_MS,
    MascotWidget,
    bounce_point,
    rest_pose,
    set_mascot_enabled,
)


@pytest.fixture(autouse=True)
def _enabled() -> Iterator[None]:
    set_mascot_enabled(True)
    yield
    set_mascot_enabled(True)


def test_left_eye_bounces_off_the_floor_and_right_eye_off_the_ceiling() -> None:
    start, end = QPointF(65, 78), QPointF(68, 104)
    assert bounce_point(start, end, 200, 0) == start
    assert bounce_point(start, end, 200, 1).y() == pytest.approx(end.y())
    lowest = max(bounce_point(start, end, 200, t / 100).y() for t in range(101))
    assert lowest == pytest.approx(200, abs=1)  # yere kadar düştü
    r_start, r_end = QPointF(190, 182), QPointF(188, 104)
    highest = min(bounce_point(r_start, r_end, 56, t / 100).y() for t in range(101))
    assert highest == pytest.approx(56, abs=1)  # tavana kadar zıpladı


def test_idle_keeps_logo_positions_and_moods_build_a_face() -> None:
    idle = rest_pose(MOOD_IDLE)
    assert idle.left.y() < idle.right.y()  # logodaki gibi: sol üstte, sağ altta
    for mood in FACE_MOODS:
        face = rest_pose(mood)
        assert face.left.y() == face.right.y()  # yüz: gözler aynı hizada


def test_without_animations_mood_changes_instantly(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mascot, "animations_enabled", lambda: False)
    widget = MascotWidget(48)
    qtbot.addWidget(widget)
    widget.set_mood(MOOD_DONE)
    assert widget.pose == rest_pose(MOOD_DONE)
    assert not widget.animating
    assert widget.toolTip() == "Bitti"


def test_eyes_travel_by_bouncing_then_settle_into_the_face(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mascot, "animations_enabled", lambda: True)
    widget = MascotWidget(64)
    qtbot.addWidget(widget)
    widget.show()
    idle, face = rest_pose(MOOD_IDLE), rest_pose(MOOD_ERROR)
    widget.set_mood(MOOD_ERROR)
    lowest_left, highest_right = idle.left.y(), idle.right.y()

    def sample() -> bool:
        nonlocal lowest_left, highest_right
        lowest_left = max(lowest_left, widget.pose.left.y())
        highest_right = min(highest_right, widget.pose.right.y())
        return not widget.animating

    qtbot.waitUntil(sample, timeout=TRAVEL_MS * 4)
    assert lowest_left > max(idle.left.y(), face.left.y()) + 40  # sol göz aşağı düştü
    assert highest_right < min(idle.right.y(), face.right.y()) - 20  # sağ göz yukarı zıpladı
    assert widget.pose.left == face.left
    assert widget.pose.right == face.right
    # Geri dönüş de sekerek: sol yine yerden, sağ yine tavandan.
    widget.set_mood(MOOD_IDLE)
    lowest_left, highest_right = face.left.y(), face.right.y()
    qtbot.waitUntil(sample, timeout=TRAVEL_MS * 4)
    assert lowest_left > idle.left.y() + 40
    assert highest_right < face.right.y() - 20
    assert widget.pose.left == idle.left
    assert widget.pose.right == idle.right


def test_working_looks_around_and_stays_animated(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mascot, "animations_enabled", lambda: False)
    widget = MascotWidget(24)
    qtbot.addWidget(widget)
    widget.set_mood(MOOD_WORKING)
    monkeypatch.setattr(mascot, "animations_enabled", lambda: True)
    widget.set_mood(MOOD_DONE)
    widget.set_mood(MOOD_WORKING)
    looks: set[float] = set()

    def looked_around() -> bool:
        looks.add(round(widget.pose.look, 1))
        return len(looks) > 3

    qtbot.waitUntil(looked_around, timeout=3000)
    assert widget.animating


def test_disabling_hides_every_mascot_and_enabling_restores(qtbot: QtBot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    lay = QVBoxLayout(host)
    shown, kept_hidden = MascotWidget(24), MascotWidget(24)
    lay.addWidget(shown)
    lay.addWidget(kept_hidden)
    kept_hidden.setVisible(False)
    host.show()
    assert shown.isVisible()
    set_mascot_enabled(False)
    assert not shown.isVisible()
    late = MascotWidget(24)
    lay.addWidget(late)
    assert not late.isVisible()  # kapalıyken yeni oluşan da görünmez
    set_mascot_enabled(True)
    assert shown.isVisible()
    assert late.isVisible()
    assert not kept_hidden.isVisible()  # kendi isteğiyle gizli olan gizli kalır


@pytest.mark.parametrize("mood", [MOOD_IDLE, MOOD_WORKING, MOOD_DONE, MOOD_ERROR, MOOD_SLEEP])
@pytest.mark.parametrize("size", [16, 24, 96])
def test_paints_at_every_size(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, mood: str, size: int) -> None:
    monkeypatch.setattr(mascot, "animations_enabled", lambda: False)
    widget = MascotWidget(size, mood)
    qtbot.addWidget(widget)
    image = widget.grab().toImage()
    center_left = image.pixelColor(size // 4, size * 4 // 5)
    assert center_left.blue() > 150  # mavi yarı çizildi
    assert center_left.red() < 80
    assert image.pixelColor(size * 3 // 4, size * 3 // 4 - 1) != QColor(0, 0, 0, 0)
