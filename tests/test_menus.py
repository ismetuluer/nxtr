"""Menü çubuğu, kısayolların kayıt defterinden bağlanması ve Çevir tablosunun bağlam menüsü (B aşaması)."""

from __future__ import annotations

import ast
import re
import time
from collections.abc import Iterator
from itertools import chain
from pathlib import Path

import pytest
from PySide6.QtCore import SIGNAL, Qt
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMenu, QMessageBox
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.scanner import EngineGuess, ScanReport
from nxceviri.core.keys import KeySet
from nxceviri.core.project import TranslationRow
from nxceviri.gui import icons
from nxceviri.gui.main_window import STEP_ADD, STEP_EXPORT, STEP_QA, STEP_SCAN, STEP_TRANSLATE, MainWindow
from nxceviri.gui.scan_page import ScanPage
from nxceviri.gui.settings_dialog import SettingsDialog
from nxceviri.gui.shortcuts import COMMANDS
from nxceviri.gui.theme import ThemeMode
from nxceviri.gui.translate_page import COL_STATUS, TranslatePage
from tests.test_statusbar import _make_window, _project

pytestmark = pytest.mark.gui

GUI_DIR = Path(icons.__file__).parent
TITLES = ["Dosya", "Düzen", "Görünüm", "Çeviri", "Git", "Araçlar", "Yardım"]
#: Tetiklenince pencereyi kapatan ya da ağa giden öğeler: bağlandıkları denetlenir ama tetiklenmez.
NOT_TRIGGERED = {"Çıkış", "Güncellemeleri Denetle…", "Yeni Proje"}


@pytest.fixture(autouse=True)
def _restore_app(qtbot: QtBot) -> Iterator[None]:
    """Tema ve yazı boyutu öğeleri tetiklenir; uygulama düzeni sonraki testlere sızmasın."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    yield
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tetiklenen öğeler pencere açarsa testi kilitlemesin."""
    monkeypatch.setattr("nxceviri.gui.main_window.log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda _url: True)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *_a, **_k: ([], ""))
    monkeypatch.setattr(QDialog, "exec", lambda _self: 0)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "about", lambda *_a, **_k: None)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: "")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: ("", ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_k: ("", ""))


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, _project())
    w.nav.setCurrentRow(STEP_TRANSLATE)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


@pytest.fixture
def empty_window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, None)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _menu(w: MainWindow, title: str) -> QMenu:
    for action in w.menuBar().actions():
        if action.text().replace("&", "") == title:
            menu = action.menu()
            assert isinstance(menu, QMenu)
            return menu
    raise AssertionError(f"{title} menüsü yok")


def _leaf_actions(menu: QMenu) -> list[QAction]:
    """Alt menüler dahil, ayırıcı ve alt menü başlığı olmayan tüm eylemler."""
    found: list[QAction] = []
    for action in menu.actions():
        sub = action.menu()
        if isinstance(sub, QMenu):
            found.extend(_leaf_actions(sub))
        elif not action.isSeparator():
            found.append(action)
    return found


def _all_leaves(w: MainWindow) -> list[QAction]:
    return [a for action in w.menuBar().actions() if isinstance(m := action.menu(), QMenu) for a in _leaf_actions(m)]


def _by_text(menu: QMenu, text: str) -> QAction:
    return next(a for a in _leaf_actions(menu) if a.text().replace("&", "") == text)


def _select(w: MainWindow, keys: set[str]) -> None:
    page = w.translate_page
    page.table.clearSelection()
    selection = page.table.selectionModel()
    for i in range(page.proxy.rowCount()):
        row = page.model.rows[page.proxy.mapToSource(page.proxy.index(i, 0)).row()]
        if row.key in keys:
            selection.select(page.proxy.index(i, 0), selection.SelectionFlag.Select | selection.SelectionFlag.Rows)


def test_menu_bar_titles_and_order(window: MainWindow) -> None:
    assert [a.text().replace("&", "") for a in window.menuBar().actions()] == TITLES


def test_every_menu_action_has_a_handler(window: MainWindow) -> None:
    for action in _all_leaves(window):
        receivers = sum(action.receivers(SIGNAL(s)) for s in ("triggered(bool)", "toggled(bool)"))
        assert receivers > 0, f"{action.text()}: işlevsiz menü öğesi"
        assert not action.icon().isNull() or action.isCheckable() or action.actionGroup() is not None, action.text()


def test_enabled_menu_actions_trigger_without_error(window: MainWindow) -> None:
    _select(window, {"d01"})
    window.update_menu_state()
    count = 0
    for action in _all_leaves(window):
        text = action.text().replace("&", "")
        if text in NOT_TRIGGERED or not action.isEnabled():
            continue
        action.trigger()
        count += 1
    assert count > 15  # her şey pasif olsaydı bu döngü hiçbir şeyi sınamazdı


def test_expected_entries_exist(window: MainWindow) -> None:
    texts = {m: [a.text().replace("&", "") for a in _leaf_actions(_menu(window, m))] for m in TITLES}
    assert "Ayarlar…" in texts["Dosya"]
    assert "Çeviri Ayarları…" not in texts["Araçlar"]
    assert "Otomatik Çeviri…" in texts["Çeviri"]
    assert "Redaksiyon…" in texts["Çeviri"]
    assert "Terminoloji…" in texts["Çeviri"]
    assert "Seçili Satırları Terminolojiye Ekle…" in texts["Çeviri"]
    assert "Teşhis Raporu…" in texts["Araçlar"]
    assert "Eklentiler…" in texts["Araçlar"]
    assert "Eklentiler…" not in texts["Yardım"]
    everything = list(chain.from_iterable(texts.values()))
    assert not [t for t in everything if "Makine" in t]
    assert not [t for t in everything if "\t" in t]  # tuş metni elle yazılmaz


def test_settings_entry_opens_settings_dialog(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    from nxceviri.gui.settings_dialog import SettingsDialog
    from nxceviri.gui.theme import ThemeMode

    opened: list[SettingsDialog] = []
    previous = window._theme_mode()

    def fake_exec(dialog: SettingsDialog) -> int:
        opened.append(dialog)
        assert dialog.stack.currentIndex() == 0  # Görünüm sayfası
        dialog.theme_changed.emit(ThemeMode.DARK)  # pencereden gelen tema menüye yansır
        return 0

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    _by_text(_menu(window, "Dosya"), "Ayarlar…").trigger()
    assert len(opened) == 1
    checked = [a.data() for a in window.theme_group.actions() if a.isChecked()]
    assert checked == [ThemeMode.DARK.value]
    window._set_theme(previous)  # uygulama temasını sonraki testlere sızdırma
    assert window.menu_actions["app.settings"].shortcut().toString() == "Ctrl+,"


def test_every_command_is_bound_somewhere(window: MainWindow) -> None:
    unbound = [c.id for c in COMMANDS if not window.shortcuts._bound.get(c.id)]
    assert unbound == []


def test_shortcut_change_updates_menu_and_tips(window: MainWindow) -> None:
    find = window.menu_actions["edit.find"]
    assert find.shortcut().toString() == "Ctrl+F"
    window.shortcuts.set_sequence("edit.find", QKeySequence("Ctrl+Alt+F"))
    assert find.shortcut().toString() == "Ctrl+Alt+F"
    assert _by_text(_menu(window, "Düzen"), "Bul…") is find
    view = window.translate_page.view_actions
    assert view.pane_toggle.toolTip().endswith("(Ctrl+J)")
    window.shortcuts.set_sequence("view.pane", QKeySequence("Ctrl+Alt+J"))
    assert "Ctrl+Alt+J" in view.pane_toggle.toolTip()
    assert "Ctrl+J)" not in view.pane_toggle.toolTip()
    assert window.translate_page.machine_button.toolTip().count("Ctrl+T") == 1
    window.shortcuts.set_sequence("translate.auto", QKeySequence("Ctrl+Alt+T"))
    assert "Ctrl+Alt+T" in window.translate_page.machine_button.toolTip()
    assert "(Ctrl+T)" not in window.translate_page.machine_button.toolTip()


def test_revise_and_auto_translate_shortcuts_start_jobs(window: MainWindow, qtbot: QtBot) -> None:
    asked: list[tuple[str, str]] = []

    def settings(scopes: object, action: str = "translate", scope: str = "all") -> None:
        asked.append((action, scope))

    window.ask_machine_settings = settings  # type: ignore[method-assign]
    revise = window.menu_actions["translate.revise"]
    auto = window.menu_actions["translate.auto"]
    assert revise.shortcut().toString() == "Ctrl+R"
    assert auto.shortcut().toString() == "Ctrl+T"
    _select(window, {"d01"})
    window.update_menu_state()
    revise.trigger()
    auto.trigger()
    assert asked == [("revise", "selected"), ("translate", "all")]
    # Gerçek tuş vuruşu: Ctrl+T pencerede Otomatik Çeviri penceresini ister.
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow, timeout=3000)
    window.translate_page.table.setFocus()
    QTest.keyClick(window, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)
    assert asked[-1] == ("translate", "all")
    assert len(asked) == 3


def test_translate_page_has_one_primary_button(qtbot: QtBot) -> None:
    page = TranslatePage()
    qtbot.addWidget(page)
    assert not hasattr(page, "more_button")
    assert not hasattr(page, "view_button")
    assert not hasattr(page, "action_row")
    assert page.machine_button.text() == "Otomatik Çeviri"
    assert not page.machine_button.icon().isNull()
    # Birincil düğme süzgeç satırının sağında, panel düğmesinin solunda durur.
    item = page.card.body.itemAt(0)
    assert item is not None
    layout = item.layout()
    assert layout is not None
    widgets = [w.widget() if (w := layout.itemAt(i)) is not None else None for i in range(layout.count())]
    assert widgets[-2:] == [page.machine_button, page.pane_button]


def test_scan_page_has_no_more_menu(qtbot: QtBot) -> None:
    page = ScanPage()
    qtbot.addWidget(page)
    assert not hasattr(page.report, "more_button")


def test_selection_dependent_items_follow_selection(window: MainWindow) -> None:
    names = ["translate.selected", "translate.retranslate", "translate.revise", "edit.reflow", "edit.copy_source"]
    window.translate_page.table.clearSelection()
    _open_selection_menus(window)
    assert not any(window.menu_actions[n].isEnabled() for n in names)
    assert window.menu_actions["translate.auto"].isEnabled()
    _select(window, {"d02"})  # çevrilmemiş tek satır
    _open_selection_menus(window)
    assert window.menu_actions["translate.selected"].isEnabled()
    assert window.menu_actions["translate.history"].isEnabled()
    assert not window.menu_actions["edit.reflow"].isEnabled()  # çevirisi olmayan satır bölünmez
    _select(window, {"d01", "d02"})
    _open_selection_menus(window)
    assert not window.menu_actions["translate.history"].isEnabled()  # geçmiş tek satır ister
    # Çevir sayfası açık değilken seçime bağlı öğeler pasiftir.
    window.nav.setCurrentRow(STEP_ADD)
    _open_selection_menus(window)
    assert not window.menu_actions["translate.selected"].isEnabled()


def test_empty_project_disables_meaningless_items(empty_window: MainWindow) -> None:
    w = empty_window
    for name in ("edit.find", "edit.replace", "edit.filter", "translate.auto", "translate.selected", "go.translate"):
        assert not w.menu_actions[name].isEnabled(), name
    assert w.menu_actions["go.add"].isEnabled()
    assert w.menu_actions["file.new"].isEnabled()
    assert not _by_text(_menu(w, "Araçlar"), "Olası Metin Dosyalarını Çıkar…").isEnabled()  # tarama raporu yok
    assert not _by_text(_menu(w, "Araçlar"), "Teşhis Raporu…").isEnabled()


def test_previous_column_item_explains_why_it_is_disabled(window: MainWindow) -> None:
    previous = window.translate_page.previous_box
    assert not previous.isEnabled()
    assert previous.toolTip() == "Son işte değişiklik yok"
    window.translate_page.set_last_changes({1: "eski"})
    assert previous.isEnabled()
    assert previous.toolTip() != "Son işte değişiklik yok"
    assert window.translate_page.changes_button.isEnabled()
    window.translate_page.set_last_changes({})
    assert not window.translate_page.changes_button.isEnabled()


def test_go_menu_mirrors_locked_steps(empty_window: MainWindow, qtbot: QtBot) -> None:
    w = empty_window
    steps = {
        "go.add": STEP_ADD,
        "go.scan": STEP_SCAN,
        "go.translate": STEP_TRANSLATE,
        "go.qa": STEP_QA,
        "go.export": STEP_EXPORT,
    }
    for command, step in steps.items():
        locked = not bool(w.nav.item(step).flags() & Qt.ItemFlag.ItemIsEnabled)
        assert w.menu_actions[command].isEnabled() != locked, command
    assert not w.menu_actions["go.translate"].isEnabled()
    w._replace_project(_project())
    for command, step in steps.items():
        assert w.menu_actions[command].isEnabled() == bool(w.nav.item(step).flags() & Qt.ItemFlag.ItemIsEnabled)
    assert w.menu_actions["go.translate"].isEnabled()
    w.menu_actions["go.qa"].trigger()
    assert w.pages.currentIndex() == STEP_QA
    assert [w.menu_actions[c].shortcut().toString() for c in steps] == [f"Ctrl+{i}" for i in range(1, 6)]
    w.menu_actions["go.add"].trigger()
    assert w.pages.currentIndex() == STEP_ADD


def _open_context_menu(w: MainWindow, keys: set[str]) -> QMenu:
    page = w.translate_page
    _select(w, keys)
    return page.build_context_menu(page.selected_rows())


def _items(action: QAction) -> list[QAction]:
    sub = action.menu()
    assert isinstance(sub, QMenu)
    return sub.actions()


def _group(menu: QMenu, title: str) -> list[QAction]:
    """Alt menünün (başlığı tuş metni olmadan) eylemleri."""
    return _items(next(a for a in menu.actions() if _strip_key(a.text()) == title))


def _strip_key(text: str) -> str:
    return text.split("\t", maxsplit=1)[0]


def test_context_menu_is_grouped_and_short(window: MainWindow) -> None:
    menu = _open_context_menu(window, {"d01", "d02"})
    top = [(_strip_key(a.text()), a.menu() is not None) for a in menu.actions() if not a.isSeparator()]
    assert top == [
        ("Çevir", True),
        ("Onayla (1)", False),
        ("Onayı kaldır (0)", False),
        ("Terminolojiye ekle…", False),
        ("Düzenle", True),
        ("Kopyala", True),
        ("Dışa aktar", True),
        ("Büyük harf", True),
        ("Geçmiş…", False),
        ("Yerinde göster", False),
    ]
    groups = {
        _strip_key(a.text()): [_strip_key(x.text()) for x in _items(a) if not x.isSeparator()]
        for a in menu.actions()
        if a.menu() is not None
    }
    assert groups["Çevir"] == ["Çevir (1)", "Yeniden çevir (2)", "Redaksiyon (2)"]
    assert groups["Düzenle"] == ["Satırları yeniden böl", "Orijinali yaz", "Temizle"]
    assert groups["Kopyala"] == ["Orijinal ve çeviri", "Yalnızca orijinal", "Yalnızca çeviri"]
    assert groups["Dışa aktar"] == ["Dış redaksiyon dosyası (2)…", "Dış çeviri dosyası (2)…"]
    assert groups["Büyük harf"][0] == "Seçili satırlar (i → İ)"
    assert not [a for a in menu.actions() if _strip_key(a.text()) == "Daha fazla"]
    for action in _leaf_actions(menu):
        assert action.isCheckable() or not action.icon().isNull(), action.text()
    menu.close()


def test_context_menu_shows_registry_shortcuts(window: MainWindow) -> None:
    menu = _open_context_menu(window, {"d01", "d02"})
    sub = _group(menu, "Çevir")
    keyed = {_strip_key(a.text()): a.text().partition("\t")[2] for a in sub}
    assert keyed == {"Çevir (1)": "", "Yeniden çevir (2)": "Ctrl+Shift+T", "Redaksiyon (2)": "Ctrl+R"}
    menu.close()
    window.shortcuts.set_sequence("translate.revise", QKeySequence("Ctrl+Alt+R"))
    menu = _open_context_menu(window, {"d01", "d02"})
    sub = _group(menu, "Çevir")
    assert next(a for a in sub if a.text().startswith("Redaksiyon")).text().endswith("\tCtrl+Alt+R")
    menu.close()


def test_context_menu_actions_start_jobs(window: MainWindow) -> None:
    asked: list[tuple[str, str]] = []

    def settings(scopes: object, action: str = "translate", scope: str = "all") -> None:
        asked.append((action, scope))

    window.ask_machine_settings = settings  # type: ignore[method-assign]
    menu = _open_context_menu(window, {"d01", "d02"})
    sub = _group(menu, "Çevir")
    for action in sub:
        action.trigger()
    menu.close()
    assert asked == [("translate", "selected"), ("retranslate", "selected"), ("revise", "selected")]


def test_no_hard_coded_shortcuts_in_gui_code() -> None:
    """Tuşlar `shortcuts.COMMANDS` kataloğundan gelir; kodda sabit kısayol ya da elle yazılmış tuş metni kalmaz."""
    pattern = re.compile(
        r"QKeySequence\(\s*f?[\"'](?!Alt\+(Up|Down)\b)|\\t(Ctrl|Shift|Alt|F\d)|\((Ctrl|Shift|Alt)\+[^)↑↓]*\)\""
    )
    offenders: list[str] = []
    for path in sorted(GUI_DIR.glob("*.py")):
        if path.name == "shortcuts.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == []


def test_find_items_open_the_find_bar_and_keep_default_keys(window: MainWindow) -> None:
    page = window.translate_page
    window.menu_actions["edit.find"].trigger()
    assert page.find_bar.isVisibleTo(page)
    assert not page.find_bar.replace_row.isVisibleTo(page)
    window.menu_actions["edit.replace"].trigger()
    assert page.find_bar.replace_row.isVisibleTo(page)
    keys = {
        c: window.menu_actions[c].shortcut().toString() for c in ("edit.filter", "edit.find_next", "edit.find_prev")
    }
    assert keys == {"edit.filter": "Ctrl+Shift+F", "edit.find_next": "F3", "edit.find_prev": "Shift+F3"}
    # Bul çubuğunun düğme ipuçları da kayıt defterinden gelir.
    assert page.find_bar.next_button.toolTip().endswith("(F3)")
    window.shortcuts.set_sequence("edit.find_next", QKeySequence("F4"))
    assert page.find_bar.next_button.toolTip().endswith("(F4)")


def test_context_menu_pops_up_from_the_table(window: MainWindow) -> None:
    page = window.translate_page
    page.table.selectRow(0)
    page._show_context_menu(page.table.visualRect(page.proxy.index(0, 0)).center())
    menu = page.table.findChild(QMenu)
    assert menu is not None
    assert menu.isVisible()
    menu.close()


def test_align_shortcuts_moved_and_revise_owns_ctrl_r(window: MainWindow) -> None:
    keys = {
        c: window.menu_actions[c].shortcut().toString()
        for c in ("view.align_left", "view.align_center", "view.align_right")
    }
    assert keys == {
        "view.align_left": "Ctrl+Shift+L",
        "view.align_center": "Ctrl+Shift+E",
        "view.align_right": "Ctrl+Shift+R",
    }
    assert window.menu_actions["translate.revise"].shortcut().toString() == "Ctrl+R"


def _open_selection_menus(w: MainWindow) -> None:
    """Düzen ve Çeviri menüleri açılırken seçime bağlı öğeler yenilenir (menü çubuğundan açılış taklidi)."""
    for title in ("Düzen", "Çeviri"):
        _menu(w, title).aboutToShow.emit()


def _synthetic_rows(count: int) -> list[TranslationRow]:
    return [
        TranslationRow(i + 1, "Dialogue.tsv", f"k{i}", f"Source {i}", "", "untranslated", "", (), None)
        for i in range(count)
    ]


def test_selection_counts_are_computed_only_when_a_menu_opens(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = window.translate_page
    calls: list[int] = []
    original = page.selection_counts

    def counting() -> object:
        calls.append(1)
        return original()

    monkeypatch.setattr(page, "selection_counts", counting)
    _select(window, {"d01", "d02"})
    window.update_menu_state()
    page.model.dataChanged.emit(page.model.index(0, 0), page.model.index(0, 0))
    window._refresh_derived()
    assert calls == []  # seçim ve tablo değişiklikleri yolunda sayım yok
    _open_selection_menus(window)
    assert calls  # menü açılırken sayılır


def test_shortcut_actions_stay_enabled_without_selection_until_a_menu_opens(window: MainWindow) -> None:
    window.translate_page.table.clearSelection()
    window.update_menu_state()
    for name in ("translate.selected", "translate.retranslate", "translate.revise", "edit.copy_source", "edit.reflow"):
        assert window.menu_actions[name].isEnabled(), name  # kısayolla tetiklenebilir; yuva boş seçimi denetler
    _open_selection_menus(window)
    assert not window.menu_actions["translate.selected"].isEnabled()  # menüde gerçek duruma göre pasif
    window.update_menu_state()
    assert window.menu_actions["translate.selected"].isEnabled()  # menü kapanınca kısayol yeniden kullanılabilir


def test_selected_scope_actions_ignore_an_empty_selection(window: MainWindow) -> None:
    asked: list[str] = []
    window.ask_machine_settings = lambda *_a, **_k: asked.append("soruldu")  # type: ignore[method-assign]
    window.translate_page.table.clearSelection()
    window.menu_actions["translate.selected"].trigger()
    assert asked == []
    assert window.statusBar().currentMessage() or window.notifier.history


def test_menu_state_updates_stay_fast_with_50k_selected_rows(window: MainWindow) -> None:
    page = window.translate_page
    page.set_rows(_synthetic_rows(50_000))
    page.table.selectAll()
    QApplication.processEvents()
    started = time.perf_counter()
    window.update_menu_state()  # seçim değişikliği yolu
    page.model.dataChanged.emit(page.model.index(0, 0), page.model.index(49_999, 0))
    window._refresh_derived()  # tablo değişikliği yolu
    assert time.perf_counter() - started < 0.2


def test_settings_dialog_signals_are_persisted_by_the_main_window(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_exec(dialog: SettingsDialog) -> int:
        dialog.theme_changed.emit(ThemeMode.DARK)
        dialog.font_size_changed.emit(16)
        return 0

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    window.open_settings()
    assert window.settings.value("ui/theme") == "dark"
    assert int(str(window.settings.value("ui/font_size"))) == 16


def test_extract_tools_need_the_key_file(window: MainWindow) -> None:
    window.report = ScanReport("Oyun", "0100", None, None, EngineGuess("unknown", "?", "none", ()), [])
    window.keys = None
    window.update_menu_state()
    tools = _menu(window, "Araçlar")
    for text in ("Oyunun Tüm Dosyalarını Çıkar…", "Teşhis Raporu…"):
        assert not _by_text(tools, text).isEnabled(), text  # anahtarsız yuva sessizce dönerdi
    window.keys = KeySet({})
    window.update_menu_state()
    for text in ("Oyunun Tüm Dosyalarını Çıkar…", "Teşhis Raporu…"):
        assert _by_text(tools, text).isEnabled(), text


def test_context_menu_edit_group_follows_running_machine_job(window: MainWindow) -> None:
    page = window.translate_page
    page.set_machine_running(True)
    menu = _open_context_menu(window, {"d01"})
    assert [a.isEnabled() for a in _group(menu, "Düzenle")] == [False, False, False]
    menu.close()
    page.set_machine_running(False)
    menu = _open_context_menu(window, {"d01"})
    assert _group(menu, "Düzenle")[1].isEnabled()  # orijinali yaz
    menu.close()


def test_error_rows_repaint_all_columns_when_qa_results_arrive(window: MainWindow) -> None:
    page = window.translate_page
    page.error_rows_box.setChecked(True)
    seen: list[tuple[int, int]] = []
    page.model.dataChanged.connect(lambda top, bottom, *_r: seen.append((top.column(), bottom.column())))
    page.model.set_qa_issues([], page.model.rows)
    assert seen[-1] == (0, page.model.columnCount() - 1)
    page.error_rows_box.setChecked(False)
    page.model.set_qa_issues([], page.model.rows)
    assert seen[-1] == (COL_STATUS, COL_STATUS)


def test_no_user_facing_text_hard_codes_the_undo_key() -> None:
    """Geri Al tuşu değiştirilebilir; ipuçları ve iletiler "Ctrl+Z" yazmaz (belge dizeleri hariç)."""
    offenders: list[str] = []
    for path in sorted(GUI_DIR.glob("*.py")):
        if path.name == "shortcuts.py":
            continue  # komut kataloğu varsayılan tuşları tutar
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            is_text = isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
            if is_text and "Ctrl+Z" in node.value:  # type: ignore[attr-defined]
                offenders.append(f"{path.name}:{node.lineno}")  # type: ignore[attr-defined]
    assert offenders == []
