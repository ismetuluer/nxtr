"""Uygulama içi Yardım: konular, aranabilirlik (Türkçe harf duyarsız), güncel kısayollar, F1 ile ekranın konusu."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QKeySequence
from pytestqt.qtbot import QtBot

from nxceviri.gui.help_window import (
    STEP_TOPICS,
    TOPIC_DIR,
    TOPIC_SHORTCUTS,
    HelpWindow,
    load_topics,
    match_count,
    shortcuts_markdown,
)
from nxceviri.gui.shortcuts import ShortcutRegistry


def test_topics_load_in_order_with_titles() -> None:
    topics = load_topics()
    slugs = [t.slug for t in topics]
    assert slugs == sorted(slugs)
    assert TOPIC_SHORTCUTS in slugs
    assert len(topics) >= 12
    for topic in topics:
        assert topic.title
        assert not topic.title.startswith("#")
    for path in TOPIC_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert text.startswith("# "), path.name
        assert "C:\\Users" not in text  # kişisel yol yok
        assert "D:\\" not in text


def test_every_step_has_a_topic() -> None:
    slugs = {t.slug for t in load_topics()}
    assert set(STEP_TOPICS.values()) <= slugs
    assert set(STEP_TOPICS) == {0, 1, 2, 3, 4}


def test_search_ignores_turkish_case() -> None:
    topic = next(t for t in load_topics() if t.slug == "03-metinleri-tara")
    assert match_count(topic, "İPTAL") > 0  # metinde "İptal"
    assert match_count(topic, "iptal") == match_count(topic, "İPTAL")
    assert match_count(topic, "TARAMA") == match_count(topic, "tarama")
    assert match_count(topic, "zzzyok") == 0


def test_shortcuts_topic_follows_current_keys(qtbot: QtBot) -> None:
    registry = ShortcutRegistry()
    text = shortcuts_markdown(registry)
    assert "| Yardım | `F1` |" in text
    assert "## Sabit tuşlar" in text
    window = HelpWindow(registry)
    qtbot.addWidget(window)
    registry.set_sequence("help.contents", QKeySequence("Ctrl+F1"))
    window.show_topic(TOPIC_SHORTCUTS)
    assert "Ctrl+F1" in window.browser.toPlainText()


def test_search_filters_topics_and_highlights(qtbot: QtBot) -> None:
    window = HelpWindow()
    qtbot.addWidget(window)
    window.search.setText("atmosphère")
    visible = [
        window.topic_list.item(r).text()
        for r in range(window.topic_list.count())
        if not window.topic_list.item(r).isHidden()
    ]
    assert "Dışa Aktar" in visible
    assert "Terminoloji" not in visible
    assert window.highlight_count > 0
    assert "konuda bulundu" in window.result_label.text()
    window.search.setText("böylebirsözyok")
    assert window.result_label.text() == "Bulunamadı"
    window.search.clear()
    assert all(not window.topic_list.item(r).isHidden() for r in range(window.topic_list.count()))
    assert not window.result_label.isVisible()


@pytest.mark.gui
def test_f1_opens_the_topic_of_the_current_screen(qtbot: QtBot, tmp_path: Path) -> None:
    from nxceviri.gui.main_window import STEP_QA
    from tests.test_statusbar import _make_window, _project

    w = _make_window(qtbot, tmp_path, _project())
    action = w.menu_actions["help.contents"]
    assert action.shortcut().toString() == "F1"
    w.nav.setCurrentRow(STEP_QA)
    action.trigger()
    assert w.help_window is not None
    assert w.help_window.isVisible()
    assert w.help_window.current_slug == "07-kontrol-et"
    assert "Sorunlar" in w.help_window.browser.toPlainText()
    w.help_window.close()
    w.dirty = False
    w.close()
