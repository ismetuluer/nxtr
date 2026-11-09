"""E aşaması: Terminoloji — ad, sade pencere, kısa hatalar, kitaplık, satırlardan terim, kanonik terimler."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.terms import TermCandidate
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.notify import LEVEL_ERROR
from tests.fake_ollama import FakeOllama
from tests.test_statusbar import _make_window, _project

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, _project())
    w.notifier._tray.show_message = lambda *_a: None  # type: ignore[method-assign]
    w.notifier._sound = lambda _level: None
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _wait(qtbot: QtBot, w: MainWindow) -> None:
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)


def test_names_say_terminology() -> None:
    from nxceviri.core.qa.checks import KIND_LABELS
    from nxceviri.gui.shortcuts import COMMANDS_BY_ID

    assert KIND_LABELS["glossary"] == "Terminoloji"
    assert COMMANDS_BY_ID["translate.glossary"].label == "Terminoloji"
    assert COMMANDS_BY_ID["translate.add_terms"].default == "Ctrl+Shift+G"


def test_suggest_without_ollama_model_gives_short_notice_with_action(window: MainWindow) -> None:
    window.settings.setValue("ollama/model", "")
    window.suggest_glossary_terms()
    notice = window.notifier.history[0]
    assert notice.title == "Terim önerisi için Ollama gerekli"
    assert len(notice.text) < 90  # kısa; uzun açıklama paragrafı yok
    assert [a.label for a in notice.actions] == ["Otomatik Çeviri…"]


def test_suggest_when_ollama_is_down_says_so_briefly(qtbot: QtBot, window: MainWindow) -> None:
    window.settings.setValue("translate/provider", "ollama")
    window.settings.setValue("ollama/model", "gemma4:12b")
    window.provider_factory = lambda s: FakeOllama(down=True).provider(s.model)
    window.find_term_candidates = lambda: [TermCandidate("Link", 2, ("Link geldi.",))]  # type: ignore[method-assign]
    window.suggest_glossary_terms()
    _wait(qtbot, window)
    notice = window.notifier.history[0]
    assert notice.level == LEVEL_ERROR
    assert notice.title == "Ollama'ya bağlanılamadı"
    assert "Ayarları Aç" in [a.label for a in notice.actions]


def test_dialog_is_plain_and_has_no_more_menu(qtbot: QtBot) -> None:
    from nxceviri.gui.machine_dialogs import GlossaryDialog

    dialog = GlossaryDialog(None, [GlossaryTerm("Link", "Link", "ad")])
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Terminoloji"
    headers = [dialog.table.horizontalHeaderItem(i).text() for i in range(3)]  # type: ignore[union-attr]
    assert headers == ["Terim", "Karşılık", "Not"]
    assert not hasattr(dialog, "more_button")
    labels = [b.text() for b in (dialog.import_button, dialog.export_button, dialog.suggest_button)]
    assert labels == ["İçe Aktar…", "Dışa Aktar…", "Terim Öner…"]


def test_term_text_is_cleaned() -> None:
    from nxceviri.core.translate.glossary_io import term_text

    assert term_text("⟦1⟧Silver Pines⟦2⟧!") == "Silver Pines"
    assert term_text("Gümüş\nÇamlar.") == "Gümüş Çamlar"
    assert term_text("  “Kılıç” x3 ") == "Kılıç x"  # sayı ve semboller ayıklanır
    assert term_text("Ana'nın Evi") == "Ana'nın Evi"  # sözcük içi kesme kalır
    assert term_text("42!") == ""


def test_plan_terms_from_rows_skips_known_and_reports_conflicts() -> None:
    from nxceviri.core.project import TranslationRow
    from nxceviri.core.translate.glossary_io import plan_terms_from_rows
    from nxceviri.core.translate.status import Status

    def row(i: int, src: str, tr: str) -> TranslationRow:
        return TranslationRow(i, "a", f"k{i}", src, tr, Status.MACHINE, "", (), None)

    existing = [GlossaryTerm("Link", "Link", "ad"), GlossaryTerm("Hyrule", "Hyrule", "")]
    plan = plan_terms_from_rows(
        [
            row(1, "Silver Pines", "Gümüş Çamlar."),
            row(2, "Link", "Link"),  # zaten aynı: atlanır
            row(3, "hyrule", "Hayrul"),  # farklı karşılık: çakışma
            row(4, "Untranslated", ""),  # çevirisiz: atlanır
            row(5, "Silver Pines", "Gümüş Çamlar"),  # aynı terim ikinci kez: bir kez
        ],
        existing,
    )
    assert plan.new == [GlossaryTerm("Silver Pines", "Gümüş Çamlar", "")]
    assert plan.conflicts == [(GlossaryTerm("Hyrule", "Hyrule", ""), GlossaryTerm("hyrule", "Hayrul", ""))]
    assert plan.skipped == 2


def test_add_selected_rows_to_terminology(qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    from nxceviri.gui.machine_dialogs import AddTermsDialog

    page = window.translate_page
    rows = {r.key: r for r in window.project.translation_rows()}
    window.project.set_glossary([GlossaryTerm("Start", "Başlat", "")])
    window.project.set_translations([(rows["d01"].id, "Merhaba!"), (rows["m01"].id, "Başla")])
    window._reload_rows()
    selection = page.table.selectionModel()
    for i in range(page.proxy.rowCount()):
        if page.model.rows[page.proxy.mapToSource(page.proxy.index(i, 0)).row()].key in ("d01", "m01"):
            selection.select(page.proxy.index(i, 0), selection.SelectionFlag.Select | selection.SelectionFlag.Rows)
    shown: list[AddTermsDialog] = []

    def accept(dialog: AddTermsDialog) -> int:
        shown.append(dialog)
        return AddTermsDialog.DialogCode.Accepted

    monkeypatch.setattr(AddTermsDialog, "exec", accept)
    window.menu_actions["translate.add_terms"].trigger()
    dialog = shown[0]
    texts = [dialog.list.item(i).text() for i in range(dialog.list.count())]
    assert texts[0] == "Hello there → Merhaba"
    assert "Start: Başlat → Başla" in texts[1]  # çakışma, işaretsiz başlar
    glossary = {t.term: t.translation for t in window.project.glossary()}
    assert glossary == {"Start": "Başlat", "Hello there": "Merhaba"}
    assert window.notifier.history[0].title == "Terminoloji güncellendi"


def test_add_terms_without_selection_says_so(window: MainWindow) -> None:
    window.translate_page.table.clearSelection()
    window.add_rows_to_terminology()
    assert window.notifier.history[0].title == "Önce satır seçin"
