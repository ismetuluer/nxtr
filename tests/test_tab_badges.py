"""Kontrol Et sekme rozetlerinin kuralları (Qt'siz)."""

from __future__ import annotations

import pytest

from nxceviri.gui.tab_badges import (
    GLYPH_BRUSH,
    GLYPH_CHECK,
    TONE_DANGER,
    TONE_SUCCESS,
    TONE_WARNING,
    accessible_name,
    fit_badge,
    font_badge,
    graphics_badge,
    issues_badge,
    short_count,
)


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (0, "0"),
        (7, "7"),
        (999, "999"),
        (1000, "1B"),
        (1049, "1B"),
        (2223, "2,2B"),
        (9999, "9,9B"),
        (12345, "12B"),
        (999_999, "999B"),
        (1_000_000, "1M"),
        (1_250_000, "1,2M"),
        (57_000_000, "57M"),
    ],
)
def test_short_count(n: int, text: str) -> None:
    assert short_count(n) == text
    assert len(text) <= 4


def test_issues_badge_rules() -> None:
    assert issues_badge(False, 5, 5) is None  # henüz denetlenmedi
    assert issues_badge(True, 0, 0) is None
    badge = issues_badge(True, 1000, 1223)
    assert badge is not None
    assert (badge.tone, badge.text) == (TONE_DANGER, "2,2B")
    assert accessible_name("Sorunlar", badge) == "Sorunlar, 2.223 bulgu"


def test_fit_badge_rules() -> None:
    assert fit_badge(0) is None
    badge = fit_badge(12)
    assert badge is not None
    assert (badge.tone, badge.text) == (TONE_WARNING, "12")
    assert accessible_name("Sığdırma", badge) == "Sığdırma, 12 satır taşıyor"


def test_font_badge_rules() -> None:
    assert font_badge(False, "", False) is None  # taranmadı
    ok = font_badge(True, "", False)
    assert ok is not None
    assert (ok.tone, ok.glyph, ok.text) == (TONE_SUCCESS, GLYPH_CHECK, "")
    bad = font_badge(True, "ğş", False)
    assert bad is not None
    assert (bad.tone, bad.text) == (TONE_DANGER, "!")
    assert "ğ ş" in bad.description
    covered = font_badge(True, "ğş", True)  # eksik harf var ama eklenti fontu yönetiyor
    assert covered is not None
    assert (covered.tone, covered.glyph) == (TONE_SUCCESS, GLYPH_CHECK)
    unscanned_covered = font_badge(False, "", True)
    assert unscanned_covered is not None
    assert unscanned_covered.tone == TONE_SUCCESS
    previous = font_badge(False, "ğ", False)  # son taramada eksik bulunmuştu
    assert previous is not None
    assert previous.tone == TONE_DANGER


def test_graphics_badge_rules() -> None:
    assert graphics_badge(False, 3, 3) is None  # denetlenmedi
    ready = graphics_badge(True, 0, 0)
    assert ready is not None
    assert (ready.tone, ready.glyph) == (TONE_SUCCESS, GLYPH_BRUSH)
    for problems, missing in ((2, 0), (0, 4), (1, 1)):
        bad = graphics_badge(True, problems, missing)
        assert bad is not None
        assert (bad.tone, bad.glyph) == (TONE_DANGER, GLYPH_BRUSH)
    two = graphics_badge(True, 1, 1)
    assert two is not None
    assert "2 resim" in two.description


def test_accessible_name_without_badge() -> None:
    assert accessible_name("Grafik", None) == "Grafik"
