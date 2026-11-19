"""Arayüz: Otomatik Çeviri penceresinde Ollama ve DeepL dışındaki hizmetler (Claude, Gemini, OpenAI uyumlu,
Google Translate): seçim, anahtar, adres, model listesi, redaksiyonun kapatılması ve ayarların hatırlanması."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.secrets import MemoryStore, api_key_name
from nxceviri.core.translate.providers.base import ProviderStatus
from nxceviri.core.translate.providers.catalog import OPENAI_GROUP, SPECS
from nxceviri.gui import machine_dialogs
from nxceviri.gui.machine_dialogs import SCOPE_ALL, MachineDialog, MachineSettings, make_provider
from nxceviri.gui.main_window import MainWindow

pytestmark = pytest.mark.gui


def _rows() -> list[TranslationRow]:
    p = Project.new()
    entries = (TextEntry("a", 0, "Hello", ()), TextEntry("b", 1, "Bye", ()))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    rows = p.translation_rows()
    p.set_translations([(rows[0].id, "Merhaba")], machine=True)
    return p.translation_rows()


def _dialog(qtbot: QtBot, provider: str, secrets: MemoryStore | None = None, **kw: Any) -> MachineDialog:
    dialog = MachineDialog(
        None,
        provider=provider,
        base_url="",
        model=kw.pop("model", "gemma4:12b"),
        notes="",
        source_language="en",
        secrets=secrets or MemoryStore(),
        scopes={SCOPE_ALL: _rows()},
        **kw,
    )
    qtbot.addWidget(dialog)
    return dialog


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_dialog_builds_every_provider(qtbot: QtBot, spec: Any) -> None:
    secrets = MemoryStore()
    secrets.set(api_key_name(spec.id), "test-anahtari")
    dialog = _dialog(qtbot, spec.id, secrets, remembered={spec.id: ("http://sunucu:1/v1", "model-x")})
    assert dialog.provider_name == spec.id
    chosen = dialog.settings()
    assert chosen.provider == spec.id
    if spec.has_models and spec.id != "ollama":
        assert chosen.model == "model-x"
    provider = make_provider(chosen, secrets)
    try:
        assert provider.name == spec.id
    finally:
        provider.close()


def test_openai_compatible_services_are_chosen_from_a_preset_list(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot, "ollama")
    dialog.provider.setCurrentIndex(dialog.provider.findData(OPENAI_GROUP))
    assert dialog.preset.isVisibleTo(dialog)
    dialog.preset.setCurrentIndex(dialog.preset.findData("groq"))
    assert dialog.provider_name == "groq"
    assert dialog.key_box.isVisibleTo(dialog)
    assert not dialog.api_url.isVisibleTo(dialog)  # Groq'un adresi sabit
    dialog.preset.setCurrentIndex(dialog.preset.findData("openai_custom"))
    assert dialog.api_url.isVisibleTo(dialog)
    dialog.api_url.setText("http://sunucu:9000/v1")
    dialog.model.setEditText("yerel-model")
    chosen = dialog.settings()
    assert (chosen.provider, chosen.base_url, chosen.model) == ("openai_custom", "http://sunucu:9000/v1", "yerel-model")
    dialog.provider.setCurrentIndex(dialog.provider.findData("ollama"))
    assert not dialog.preset.isVisibleTo(dialog)


def test_key_is_saved_per_provider(qtbot: QtBot) -> None:
    secrets = MemoryStore()
    dialog = _dialog(qtbot, "anthropic", secrets)
    assert not dialog.start.isEnabled()  # anahtar yok
    assert not dialog.test_button.isVisibleTo(dialog)
    dialog.key.setText("  claude-anahtari  ")
    dialog.save_key()
    assert secrets.get(api_key_name("anthropic")) == "claude-anahtari"
    assert secrets.get(api_key_name("gemini")) is None
    assert dialog.key.text() == ""
    assert "Kayıtlı" in dialog.key_state.text()
    assert dialog.start.isEnabled()
    assert dialog.test_button.isVisibleTo(dialog)
    dialog.provider.setCurrentIndex(dialog.provider.findData("gemini"))
    assert "yok" in dialog.key_state.text()


def test_claude_model_defaults_and_is_editable(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot, "anthropic")
    assert dialog.settings().model == "claude-opus-5-5"
    dialog.model.setEditText("claude-baska")
    assert dialog.settings().model == "claude-baska"


def test_switching_providers_keeps_each_model(qtbot: QtBot) -> None:
    dialog = _dialog(qtbot, "ollama", remembered={"gemini": ("", "gemini-a")})
    dialog.provider.setCurrentIndex(dialog.provider.findData("gemini"))
    assert dialog.model.currentText() == "gemini-a"
    dialog.model.setEditText("gemini-b")
    dialog.provider.setCurrentIndex(dialog.provider.findData("ollama"))
    assert dialog.model.currentText() == "gemma4:12b"
    dialog.provider.setCurrentIndex(dialog.provider.findData("gemini"))
    assert dialog.model.currentText() == "gemini-b"


def test_classic_service_cannot_revise(qtbot: QtBot) -> None:
    secrets = MemoryStore()
    secrets.set(api_key_name("google_translate"), "k")
    dialog = _dialog(qtbot, "google_translate", secrets, action="revise")
    assert not dialog.start.isEnabled()
    assert "talimat izleyemez" in dialog.status.text.text()
    assert not dialog.ollama_box.isVisibleTo(dialog)  # model seçimi yok
    dialog.action_buttons["retranslate"].setChecked(True)
    assert dialog.start.isEnabled()
    assert not dialog.instruction_box.isVisibleTo(dialog)


def test_llm_service_can_revise(qtbot: QtBot) -> None:
    secrets = MemoryStore()
    secrets.set(api_key_name("openrouter"), "k")
    dialog = _dialog(qtbot, "openrouter", secrets, action="revise", remembered={"openrouter": ("", "m")})
    dialog.instruction.setPlainText("Daha kısa yaz.")
    assert dialog.start.isEnabled()
    assert dialog.settings().instruction == "Daha kısa yaz."


class _FakeLister:
    name = "gemini"

    def __init__(self) -> None:
        self.closed = False

    def list_models(self) -> list[str]:
        return ["gemini-a", "gemini-b"]

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(True, "Bağlantı başarılı: sahte")

    def close(self) -> None:
        self.closed = True


def test_list_models_for_cloud_service(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeLister()
    built: list[MachineSettings] = []

    def factory(settings: MachineSettings, _secrets: object) -> _FakeLister:
        built.append(settings)
        return fake

    monkeypatch.setattr(machine_dialogs, "make_provider", factory)
    secrets = MemoryStore()
    secrets.set(api_key_name("gemini"), "k")
    dialog = _dialog(qtbot, "gemini", secrets)
    dialog.refresh_models()
    assert [dialog.model.itemText(i) for i in range(dialog.model.count())] == ["gemini-a", "gemini-b"]
    assert built[0].provider == "gemini"
    assert fake.closed
    assert "2 model" in dialog.status.text.text()
    assert dialog.test_connection()


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_settings_are_remembered_per_provider(window: MainWindow) -> None:
    chosen = MachineSettings("openai_custom", "http://sunucu:9000/v1", "yerel-model", "")
    window._remember_machine_settings(chosen)
    window._remember_machine_settings(MachineSettings("ollama", "http://localhost:11434", "gemma4:12b", ""))
    remembered = window.machine.remembered_providers()
    assert remembered["openai_custom"] == ("http://sunucu:9000/v1", "yerel-model")
    assert remembered["ollama"] == ("http://localhost:11434", "gemma4:12b")
    assert str(window.settings.value("ollama/model")) == "gemma4:12b"  # eski anahtar korunur
    assert str(window.settings.value("translate/provider")) == "ollama"
    for key in window.settings.allKeys():  # anahtar değeri ayar dosyasına yazılmaz
        assert "api_key" not in key


def test_status_bar_names_cloud_service_without_network(window: MainWindow) -> None:
    window._remember_machine_settings(MachineSettings("anthropic", "", "claude-opus-5-5", ""))
    assert window._provider_kind() == "anthropic"
    window._probe_provider()  # ağa gitmez: yalnızca seçili model
    assert window._provider_tip_title == "Claude"
