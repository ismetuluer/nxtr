"""Ayarlar penceresi: sayfalar, görünüm, kısayollar, çeviri sağlayıcıları ve güncelleme ayarları."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import QAbstractButton, QMessageBox, QTreeWidgetItem
from pytestqt.qtbot import QtBot

from nxceviri.core.secrets import DEEPL_API_KEY, MemoryStore
from nxceviri.core.translate.providers.base import ProviderStatus
from nxceviri.core.translate.providers.deepl import DeepLProvider
from nxceviri.core.translate.providers.ollama import DEFAULT_URL, OllamaProvider
from nxceviri.gui.settings_dialog import (
    PAGE_PROVIDERS,
    PAGE_SHORTCUTS,
    PAGE_UPDATES,
    PAGE_VIEW,
    SettingsDialog,
)
from nxceviri.gui.shortcuts import COMMANDS_BY_ID, ShortcutRegistry
from nxceviri.gui.theme import DEFAULT_FONT_SIZE, THEME_LABELS, ThemeMode
from nxceviri.gui.update_dialog import AUTO_CHECK_KEY
from nxceviri.gui.view_actions import ALIGN_CENTER, ALIGN_LEFT, PANE_BOTTOM, PANE_RIGHT, ViewActions

DEEPL_TEST_KEY = "deneme-anahtar-123:fx"


class Env:
    """Pencerenin bağımlılıkları: geçici ayar dosyası, kayıt defteri, görünüm eylemleri, sahte gizli depo."""

    def __init__(self, tmp_path: Path) -> None:
        self.settings = QSettings(str(tmp_path / "ayar.ini"), QSettings.Format.IniFormat)
        self.registry = ShortcutRegistry()
        self.registry.bind_settings(self.settings)
        self.view = ViewActions()
        self.view.bind_settings(self.settings)
        self.secrets = MemoryStore()
        self.wrap = QAction("Metni Kaydır")
        self.wrap.setCheckable(True)
        self.issue_colors = QAction("Sorunları Renkle Göster")
        self.issue_colors.setCheckable(True)

    def dialog(self, **kwargs: Any) -> SettingsDialog:
        options: dict[str, Any] = {
            "theme": ThemeMode.SYSTEM,
            "font_size": DEFAULT_FONT_SIZE,
            "wrap": self.wrap,
            "issue_colors": self.issue_colors,
            "updates_available": True,
        }
        options.update(kwargs)
        return SettingsDialog(None, self.settings, self.registry, self.view, self.secrets, **options)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def _item(dialog: SettingsDialog, command_id: str) -> QTreeWidgetItem:
    item = dialog.shortcut_item(command_id)
    assert item is not None, command_id
    return item


def _pick_button(text: str) -> Callable[[QMessageBox], int]:
    """`QMessageBox.exec` yerine: adı `text` olan düğmeye basar (kullanıcının seçimi)."""

    def run(box: QMessageBox) -> int:
        buttons: list[QAbstractButton] = [b for b in box.buttons() if b.text() == text]
        assert buttons, [b.text() for b in box.buttons()]
        buttons[0].click()
        return 0

    return run


# --- sayfalar ----------------------------------------------------------------------------------


def test_window_title_pages_and_close_button(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Ayarlar"
    assert [dialog.pages.item(i).text() for i in range(dialog.pages.count())] == [
        "Görünüm",
        "Kısayollar",
        "Çeviri",
        "Güncelleme",
    ]
    assert all(not dialog.pages.item(i).icon().isNull() for i in range(dialog.pages.count()))
    assert dialog.close_button.text() == "Kapat"
    assert dialog.minimumWidth() <= 720
    assert dialog.minimumHeight() <= 480


def test_page_switching_and_show_page(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    assert dialog.current_page == PAGE_VIEW
    dialog.pages.setCurrentRow(1)
    assert dialog.current_page == PAGE_SHORTCUTS
    assert dialog.stack.currentIndex() == 1
    dialog.show_page(PAGE_UPDATES)
    assert dialog.current_page == PAGE_UPDATES
    assert dialog.pages.currentRow() == 3
    dialog.show_page(PAGE_PROVIDERS)
    assert dialog.stack.currentWidget() is dialog.providers_page


def test_initial_page_argument(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog(page=PAGE_PROVIDERS)
    qtbot.addWidget(dialog)
    assert dialog.current_page == PAGE_PROVIDERS


def test_unknown_page_is_ignored(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    dialog.show_page("yok")
    assert dialog.current_page == PAGE_VIEW


# --- görünüm -----------------------------------------------------------------------------------


def test_theme_and_font_signals_and_persistence(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog(theme=ThemeMode.LIGHT, font_size=12)
    qtbot.addWidget(dialog)
    assert dialog.theme_combo.currentData() == ThemeMode.LIGHT
    assert dialog.font_combo.currentData() == 12
    assert [dialog.theme_combo.itemText(i) for i in range(3)] == list(THEME_LABELS.values())
    with qtbot.waitSignal(dialog.theme_changed) as theme_signal:
        dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData(ThemeMode.DARK))
    assert theme_signal.args == [ThemeMode.DARK]
    with qtbot.waitSignal(dialog.font_size_changed) as font_signal:
        dialog.font_combo.setCurrentIndex(dialog.font_combo.findData(16))
    assert font_signal.args == [16]
    assert env.settings.value("ui/theme") == "dark"
    assert int(str(env.settings.value("ui/font_size"))) == 16


def test_initial_values_do_not_emit_signals(qtbot: QtBot, env: Env) -> None:
    emitted: list[object] = []
    dialog = env.dialog(theme=ThemeMode.DARK, font_size=14)
    qtbot.addWidget(dialog)
    dialog.theme_changed.connect(emitted.append)
    dialog.font_size_changed.connect(emitted.append)
    dialog.show_page(PAGE_VIEW)
    assert emitted == []


def test_odd_font_size_is_clamped_to_listed_value(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog(font_size=13)
    qtbot.addWidget(dialog)
    assert dialog.font_combo.currentData() in (12, 14)


def test_symbols_checkbox_is_two_way(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    assert not dialog.symbols_check.isChecked()
    dialog.symbols_check.setChecked(True)
    assert env.view.symbols.isChecked()
    env.view.symbols.setChecked(False)
    assert not dialog.symbols_check.isChecked()


def test_wrap_and_issue_colors_are_two_way(qtbot: QtBot, env: Env) -> None:
    env.wrap.setChecked(True)
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    assert dialog.wrap_check.isChecked()
    assert not dialog.issue_check.isChecked()
    dialog.wrap_check.setChecked(False)
    assert not env.wrap.isChecked()
    dialog.issue_check.setChecked(True)
    assert env.issue_colors.isChecked()
    env.issue_colors.setChecked(False)
    assert not dialog.issue_check.isChecked()
    env.wrap.setChecked(True)
    assert dialog.wrap_check.isChecked()


def test_alignment_selection_is_two_way(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    assert dialog.align_combo.currentData() == ALIGN_LEFT
    dialog.align_combo.setCurrentIndex(dialog.align_combo.findData(ALIGN_CENTER))
    assert env.view.align == ALIGN_CENTER
    assert env.view.align_actions[ALIGN_CENTER].isChecked()
    env.view.align_actions[ALIGN_LEFT].trigger()
    assert dialog.align_combo.currentData() == ALIGN_LEFT


def test_pane_selection_is_two_way(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    assert dialog.pane_combo.currentData() == PANE_BOTTOM
    dialog.pane_combo.setCurrentIndex(dialog.pane_combo.findData(PANE_RIGHT))
    assert env.view.pane == PANE_RIGHT
    env.view.pane_actions[PANE_BOTTOM].trigger()
    assert dialog.pane_combo.currentData() == PANE_BOTTOM


# --- kısayollar --------------------------------------------------------------------------------


def test_shortcut_tree_lists_categories_and_commands(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    item = _item(dialog, "translate.auto")
    assert item.text(0) == "Otomatik Çeviri"
    assert item.text(1) == "Ctrl+T"
    category = item.parent()
    assert category is not None
    assert category.text(0) == "Çeviri"
    assert _item(dialog, "edit.clear").text(1) == ""


def test_assign_shortcut_saves_and_updates_tree(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    assert dialog.assign_shortcut("translate.auto", QKeySequence("Ctrl+Shift+Y"))
    assert env.registry.text("translate.auto") == "Ctrl+Shift+Y"
    assert _item(dialog, "translate.auto").text(1) == "Ctrl+Shift+Y"
    assert _item(dialog, "translate.auto").font(0).bold()
    assert not _item(dialog, "file.save").font(0).bold()
    assert str(env.settings.value("shortcuts/translate.auto")) == "Ctrl+Shift+Y"
    reloaded = ShortcutRegistry()
    reloaded.bind_settings(env.settings)
    assert reloaded.text("translate.auto") == "Ctrl+Shift+Y"


def test_change_button_uses_selected_row_and_asks_key(qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    asked: list[str] = []

    def fake_ask(command_id: str) -> QKeySequence | None:
        asked.append(command_id)
        return QKeySequence("Ctrl+Shift+Y")

    monkeypatch.setattr(dialog, "ask_sequence", fake_ask)
    dialog.shortcut_tree.setCurrentItem(_item(dialog, "translate.auto"))
    dialog.change_button.click()
    assert asked == ["translate.auto"]
    assert env.registry.text("translate.auto") == "Ctrl+Shift+Y"


def test_cancelled_key_entry_changes_nothing(qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    monkeypatch.setattr(dialog, "ask_sequence", lambda _command_id: None)
    dialog.shortcut_tree.setCurrentItem(_item(dialog, "translate.auto"))
    dialog.change_button.click()
    assert env.registry.text("translate.auto") == "Ctrl+T"
    assert not env.registry.is_custom("translate.auto")


def test_category_row_cannot_be_changed(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    category = dialog.shortcut_tree.topLevelItem(0)
    assert category is not None
    dialog.shortcut_tree.setCurrentItem(category)
    assert not dialog.change_button.isEnabled()
    assert not dialog.remove_button.isEnabled()
    assert not dialog.reset_button.isEnabled()


def test_conflict_cancel_changes_nothing(qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    shown: list[str] = []

    def run(box: QMessageBox) -> int:
        shown.append(box.text())
        return _pick_button("Vazgeç")(box)

    monkeypatch.setattr(QMessageBox, "exec", run)
    assert not dialog.assign_shortcut("translate.auto", QKeySequence("Ctrl+F"))
    assert shown == ["“Ctrl+F” zaten “Bul” için kullanılıyor."]
    assert env.registry.text("translate.auto") == "Ctrl+T"
    assert env.registry.text("edit.find") == "Ctrl+F"
    assert not env.registry.is_custom("translate.auto")
    assert not env.registry.is_custom("edit.find")


def test_conflict_assign_anyway_unbinds_the_other(qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QMessageBox, "exec", _pick_button("Yine de ata"))
    assert dialog.assign_shortcut("translate.auto", QKeySequence("Ctrl+F"))
    assert env.registry.text("translate.auto") == "Ctrl+F"
    assert env.registry.text("edit.find") == ""
    assert env.registry.is_custom("edit.find")
    assert _item(dialog, "edit.find").text(1) == ""
    assert _item(dialog, "translate.auto").text(1) == "Ctrl+F"


def test_assigning_current_key_again_is_not_a_conflict(qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)

    def fail(_box: QMessageBox) -> int:
        raise AssertionError("çakışma sorusu açılmamalıydı")

    monkeypatch.setattr(QMessageBox, "exec", fail)
    assert dialog.assign_shortcut("translate.auto", QKeySequence("Ctrl+T"))
    assert not env.registry.is_custom("translate.auto")


def test_remove_shortcut(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    dialog.shortcut_tree.setCurrentItem(_item(dialog, "translate.auto"))
    dialog.remove_button.click()
    assert env.registry.text("translate.auto") == ""
    assert _item(dialog, "translate.auto").text(1) == ""
    assert _item(dialog, "translate.auto").font(0).bold()


def test_reset_selected_to_default(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    dialog.assign_shortcut("translate.auto", QKeySequence("Ctrl+Shift+Y"))
    dialog.shortcut_tree.setCurrentItem(_item(dialog, "translate.auto"))
    assert dialog.reset_button.isEnabled()
    dialog.reset_button.click()
    assert env.registry.text("translate.auto") == "Ctrl+T"
    assert not env.registry.is_custom("translate.auto")
    assert not _item(dialog, "translate.auto").font(0).bold()
    assert not dialog.reset_button.isEnabled()


def test_reset_all_asks_and_resets(qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    dialog.assign_shortcut("translate.auto", QKeySequence("Ctrl+Shift+Y"))
    dialog.assign_shortcut("file.save", QKeySequence())
    monkeypatch.setattr(QMessageBox, "exec", _pick_button("Vazgeç"))
    dialog.reset_all_button.click()
    assert env.registry.is_custom("translate.auto")
    monkeypatch.setattr(QMessageBox, "exec", _pick_button("Tümünü Döndür"))
    dialog.reset_all_button.click()
    assert env.registry.text("translate.auto") == "Ctrl+T"
    assert env.registry.text("file.save") == "Ctrl+S"
    assert _item(dialog, "file.save").text(1) == "Ctrl+S"


def test_shortcut_search_filters_commands(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    dialog.shortcut_search.setText("kaydet")
    assert not _item(dialog, "file.save").isHidden()
    assert _item(dialog, "translate.auto").isHidden()
    dialog.shortcut_search.setText("ctrl+t")
    assert not _item(dialog, "translate.auto").isHidden()
    dialog.shortcut_search.setText("")
    assert not _item(dialog, "translate.auto").isHidden()


def test_registry_change_from_outside_refreshes_tree(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    env.registry.set_sequence("translate.auto", QKeySequence("Ctrl+Shift+Y"))
    assert _item(dialog, "translate.auto").text(1) == "Ctrl+Shift+Y"


def test_key_entry_dialog_returns_typed_sequence(qtbot: QtBot, env: Env) -> None:
    from nxceviri.gui.settings_dialog import KeyEntryDialog

    entry = KeyEntryDialog(None, COMMANDS_BY_ID["translate.auto"].label)
    qtbot.addWidget(entry)
    entry.editor.setKeySequence(QKeySequence("Ctrl+Shift+Y, Ctrl+K"))
    assert entry.sequence() == QKeySequence("Ctrl+Shift+Y")  # yalnızca tek kombinasyon


# --- çeviri sağlayıcıları ---------------------------------------------------------------------


def test_deepl_key_save_and_delete(qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DeepLProvider, "test_connection", lambda _self: ProviderStatus(True, "Bağlantı başarılı"))
    dialog = env.dialog(page=PAGE_PROVIDERS)
    qtbot.addWidget(dialog)
    panel = dialog.deepl_panel
    assert panel.state.text() == "Kayıtlı anahtar: yok"
    assert not panel.remove.isEnabled()
    panel.key.setText(DEEPL_TEST_KEY)
    panel.save.click()
    assert env.secrets.get(DEEPL_API_KEY) == DEEPL_TEST_KEY
    assert panel.state.text() == "Kayıtlı anahtar: var (DeepL API Free)"
    assert panel.key.text() == ""
    assert panel.status.text.text() == "Bağlantı başarılı"
    assert panel.remove.isEnabled()
    for key in env.settings.allKeys():
        assert DEEPL_TEST_KEY not in str(env.settings.value(key))
    env.settings.setValue("deneme", "1")  # dosya oluşsun
    env.settings.sync()
    assert DEEPL_TEST_KEY not in (Path(env.settings.fileName())).read_text(encoding="utf-8")
    panel.remove.click()
    assert env.secrets.get(DEEPL_API_KEY) is None
    assert panel.state.text() == "Kayıtlı anahtar: yok"
    assert not panel.test.isEnabled()


def test_deepl_empty_key_warns(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog(page=PAGE_PROVIDERS)
    qtbot.addWidget(dialog)
    dialog.deepl_panel.save.click()
    assert "Önce anahtarı" in dialog.deepl_panel.status.text.text()
    assert env.secrets.get(DEEPL_API_KEY) is None


def test_deepl_test_button_shows_failure(qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DeepLProvider, "test_connection", lambda _self: ProviderStatus(False, "Anahtar geçersiz"))
    env.secrets.set(DEEPL_API_KEY, DEEPL_TEST_KEY)
    dialog = env.dialog(page=PAGE_PROVIDERS)
    qtbot.addWidget(dialog)
    dialog.deepl_panel.test.click()
    assert dialog.deepl_panel.status.text.text() == "Anahtar geçersiz"


def test_ollama_url_default_and_save(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog(page=PAGE_PROVIDERS)
    qtbot.addWidget(dialog)
    assert dialog.ollama_url.text() == DEFAULT_URL
    dialog.ollama_url.setText("http://192.168.1.20:11434")
    dialog.ollama_url.editingFinished.emit()
    assert env.settings.value("ollama/url") == "http://192.168.1.20:11434"


def test_ollama_url_loaded_from_settings(qtbot: QtBot, env: Env) -> None:
    env.settings.setValue("ollama/url", "http://sunucu:11434")
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    assert dialog.ollama_url.text() == "http://sunucu:11434"


@pytest.mark.parametrize("bad", ["", "   ", "sunucu", "ftp://sunucu", "http://"])
def test_ollama_invalid_url_is_rejected(qtbot: QtBot, env: Env, bad: str) -> None:
    env.settings.setValue("ollama/url", "http://sunucu:11434")
    dialog = env.dialog(page=PAGE_PROVIDERS)
    qtbot.addWidget(dialog)
    dialog.ollama_url.setText(bad)
    dialog.ollama_url.editingFinished.emit()
    assert env.settings.value("ollama/url") == "http://sunucu:11434"
    assert dialog.ollama_url.text() == "http://sunucu:11434"
    assert "adres" in dialog.ollama_status.text.text().lower()


def test_ollama_test_button_uses_saved_address_and_model(
    qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str]] = []

    def fake_test(self: OllamaProvider) -> ProviderStatus:
        seen.append((self.base_url, self.model))
        return ProviderStatus(True, "Bağlantı başarılı: Ollama 0.1")

    monkeypatch.setattr(OllamaProvider, "test_connection", fake_test)
    env.settings.setValue("ollama/model", "gemma3")
    dialog = env.dialog(page=PAGE_PROVIDERS)
    qtbot.addWidget(dialog)
    dialog.ollama_url.setText("http://sunucu:11434")
    dialog.ollama_test.click()
    assert seen == [("http://sunucu:11434", "gemma3")]
    assert env.settings.value("ollama/url") == "http://sunucu:11434"
    assert dialog.ollama_status.text.text() == "Bağlantı başarılı: Ollama 0.1"


def test_ollama_test_without_model_lists_models(qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    from nxceviri.core.translate.providers.ollama import ModelInfo

    def fail(_self: OllamaProvider) -> ProviderStatus:
        raise AssertionError("model seçilmeden test_connection çağrılmamalı")

    models = [ModelInfo("gemma3", 1, "4B", "Q4", ("completion",))]
    monkeypatch.setattr(OllamaProvider, "test_connection", fail)
    monkeypatch.setattr(OllamaProvider, "list_models", lambda _self: models)
    dialog = env.dialog(page=PAGE_PROVIDERS)
    qtbot.addWidget(dialog)
    dialog.ollama_test.click()
    assert "1 model" in dialog.ollama_status.text.text()


def test_ollama_test_rejects_invalid_address_without_network(
    qtbot: QtBot, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_self: OllamaProvider) -> ProviderStatus:
        raise AssertionError("ağ çağrısı yapılmamalı")

    monkeypatch.setattr(OllamaProvider, "test_connection", fail)
    dialog = env.dialog(page=PAGE_PROVIDERS)
    qtbot.addWidget(dialog)
    dialog.ollama_url.setText("sunucu")
    dialog.ollama_test.click()
    assert "adres" in dialog.ollama_status.text.text().lower()


# --- güncelleme --------------------------------------------------------------------------------


def test_auto_check_checkbox_writes_setting(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    assert dialog.auto_check.isChecked()
    dialog.auto_check.setChecked(False)
    assert env.settings.value(AUTO_CHECK_KEY) == "false"
    dialog.auto_check.setChecked(True)
    assert env.settings.value(AUTO_CHECK_KEY) == "true"


def test_auto_check_reads_existing_setting(qtbot: QtBot, env: Env) -> None:
    env.settings.setValue(AUTO_CHECK_KEY, "false")
    dialog = env.dialog()
    qtbot.addWidget(dialog)
    assert not dialog.auto_check.isChecked()


def test_check_now_emits_signal(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog(page=PAGE_UPDATES)
    qtbot.addWidget(dialog)
    assert dialog.check_now.isEnabled()
    with qtbot.waitSignal(dialog.check_updates_requested):
        dialog.check_now.click()


def test_check_now_disabled_when_updates_unavailable(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog(page=PAGE_UPDATES, updates_available=False)
    qtbot.addWidget(dialog)
    assert not dialog.check_now.isEnabled()
    assert dialog.check_now.toolTip()
    assert dialog.auto_check.isEnabled()


def test_dialog_builds_with_large_font(qtbot: QtBot, env: Env) -> None:
    dialog = env.dialog(font_size=18)
    qtbot.addWidget(dialog)
    dialog.setFont(QFont("Segoe UI", 18))
    dialog.resize(dialog.minimumSize())
    dialog.show()
    assert dialog.isVisible()
