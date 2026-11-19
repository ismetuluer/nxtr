"""Arayüz: Küfür / argo denetimi ayarı (Araçlar menüsü), anlık denetim ve "Bu kelime argo değil" eylemi."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.checks import QaIssue
from nxceviri.core.qa.profanity import LEVEL_ALL, LEVEL_HEAVY, LEVEL_OFF
from nxceviri.core.secrets import MemoryStore
from nxceviri.gui.main_window import STEP_QA, MainWindow
from nxceviri.gui.qa_page import QaPage

pytestmark = pytest.mark.gui

LINES = [("a", "Start Game"), ("b", "Hey you!"), ("c", "Come here")]
TRANSLATIONS = {"a": "Oyunu Başlat.", "b": "Siktir git!", "c": "Lan buraya gel."}


def _project() -> Project:
    p = Project.new()
    entries = tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(LINES))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations([(rows[k].id, t) for k, t in TRANSLATIONS.items()], machine=True)
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.show()
    w.nav.setCurrentRow(STEP_QA)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _profanity_issues(w: MainWindow) -> list[QaIssue]:
    return [i for i in w.qa_page.model.issues if i.kind == "profanity"]


def _check(qtbot: QtBot, w: MainWindow) -> None:
    w.qa_page.check_button.click()
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)


def test_varsayilan_kapali(qtbot: QtBot, window: MainWindow) -> None:
    _check(qtbot, window)
    assert _profanity_issues(window) == []
    assert window.menus.profanity_actions[LEVEL_OFF].isChecked()


def test_menuden_duzey_secimi_kaydedilir_ve_denetimi_yeniler(qtbot: QtBot, window: MainWindow) -> None:
    _check(qtbot, window)
    window.menus.profanity_actions[LEVEL_HEAVY].trigger()
    assert window.project.setting("profanity_level") == LEVEL_HEAVY
    qtbot.waitUntil(lambda: not window.busy)  # denetim arka planda yenilenir
    assert [i.row_id for i in _profanity_issues(window)] == [_row_id(window, "b")]
    window.menus.profanity_actions[LEVEL_ALL].trigger()
    qtbot.waitUntil(lambda: not window.busy)
    assert len(_profanity_issues(window)) == 2
    window.menus.profanity_actions[LEVEL_OFF].trigger()
    qtbot.waitUntil(lambda: not window.busy)
    assert _profanity_issues(window) == []


def test_secim_menude_gosterilir(window: MainWindow) -> None:
    window.project.set_setting("profanity_level", LEVEL_ALL)
    window.menus.refresh()
    assert window.menus.profanity_actions[LEVEL_ALL].isChecked()
    assert not window.menus.profanity_actions[LEVEL_OFF].isChecked()


def test_bozuk_duzey_ayari_kapali_sayilir(window: MainWindow) -> None:
    window.project.set_setting("profanity_level", "bozuk")
    assert window._profanity_config().level == LEVEL_OFF


def test_canli_denetim_duzeyi_izler(window: MainWindow) -> None:
    assert not window._profanity_config().enabled
    window.menus.profanity_actions[LEVEL_HEAVY].trigger()
    assert window._live_context is not None
    assert window._live_context.profanity.level == LEVEL_HEAVY


def test_kayitli_duzey_proje_acilinca_canli_denetime_gecer(window: MainWindow) -> None:
    project = _project()
    project.set_setting("profanity_level", LEVEL_HEAVY)
    project.set_setting("profanity_allowed", json.dumps(["lan"]))
    assert window._replace_project(project)
    assert window._live_context is not None
    assert window._live_context.profanity.level == LEVEL_HEAVY
    assert window._live_context.profanity.allowed == frozenset({"lan"})


def _row_id(w: MainWindow, key: str) -> int:
    return next(r.id for r in w.project.translation_rows() if r.key == key)


def test_argo_degil_izin_listesine_yazilir_ve_bulgu_kalkar(qtbot: QtBot, window: MainWindow) -> None:
    window.project.set_setting("profanity_level", LEVEL_ALL)
    _check(qtbot, window)
    assert len(_profanity_issues(window)) == 2
    window.qa_page.not_profanity_requested.emit(["lan"])
    assert json.loads(window.project.setting("profanity_allowed")) == ["lan"]
    qtbot.waitUntil(lambda: not window.busy)
    assert [i.row_id for i in _profanity_issues(window)] == [_row_id(window, "b")]
    window.qa_page.not_profanity_requested.emit(["lan"])  # tekrar eklemek listeyi çoğaltmaz
    assert json.loads(window.project.setting("profanity_allowed")) == ["lan"]


def test_bulguyu_yok_say_calisir(qtbot: QtBot, window: MainWindow) -> None:
    window.project.set_setting("profanity_level", LEVEL_HEAVY)
    _check(qtbot, window)
    row = _row_id(window, "b")
    window.qa_page.ignore_requested.emit([(row, "profanity")])
    assert _profanity_issues(window) == []  # yok sayılanlar ayrı listededir


def test_sag_tik_menusunde_argo_degil_eylemi(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    page.resize(1400, 800)
    page.show()
    rows = [TranslationRow(1, "f", "k1", "Hey", "Lan gel", "machine", "", (), None)]
    page.show_issues(
        [
            QaIssue(1, "k1", "profanity", "warning", "Argo: Lan", ("lan",)),
        ],
        rows,
    )
    page.table.selectRow(0)
    action = next(a for a in page.context_menu().actions() if a.text() == "Bu kelime argo değil")
    with qtbot.waitSignal(page.not_profanity_requested) as sig:
        action.trigger()
    assert sig.args == [["lan"]]


def test_sag_tik_menusunde_baska_bulguda_eylem_yok(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    page.resize(1400, 800)
    page.show()
    rows = [TranslationRow(1, "f", "k1", "Hey", "Merhaba ", "machine", "", (), None)]
    page.show_issues([QaIssue(1, "k1", "spaces", "warning", "boşluk")], rows)
    page.table.selectRow(0)
    assert "Bu kelime argo değil" not in [a.text() for a in page.context_menu().actions()]
