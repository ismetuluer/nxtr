"""Çeviri talimatı: çevir ve yeniden çevir işlerinde Ollama'ya giden, hazır listeden seçilebilen talimat."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.providers.base import BatchItem, Scene
from nxceviri.core.translate.providers.ollama import build_messages
from nxceviri.core.translate.runner import MachineJob, run_machine_translation
from nxceviri.gui.machine_dialogs import (
    INSTRUCTION_PRESETS,
    PROVIDER_DEEPL,
    PROVIDER_OLLAMA,
    SCOPE_ALL,
    TRANSLATE_PRESETS,
    MachineDialog,
    MachineSettings,
)
from nxceviri.gui.main_window import MainWindow
from tests.fake_ollama import FakeOllama

UI = "Bu satırlar menü ve düğme metni: kısa yaz, sona nokta koyma."


def test_translate_instruction_goes_to_system_prompt() -> None:
    messages = build_messages(
        [BatchItem("0", "Start Game")], "en", "tr", "Korku oyunu.", [], scene=Scene(instruction=UI)
    )
    assert UI in messages[0]["content"]
    assert messages[0]["content"].index("Korku oyunu.") < messages[0]["content"].index(UI)
    assert "instruction" not in json.loads(messages[1]["content"])
    revise = build_messages(
        [BatchItem("0", "Start Game", current="Oyunu başlat")],
        "en",
        "tr",
        "",
        [],
        scene=Scene(revise=True, instruction=UI),
    )
    assert json.loads(revise[1]["content"])["instruction"] == UI  # redaksiyonda eskisi gibi kullanıcı mesajında


def _project() -> Project:
    p = Project.new()
    entries = (TextEntry("m01", 0, "Start Game", ()), TextEntry("m02", 1, "Options", ()))
    p.import_texts([ImportedFile("Menu.tsv", "0100", "unity", "base", entries)])
    return p


def test_runner_sends_translate_instruction() -> None:
    project = _project()
    rows = project.translation_rows()
    server = FakeOllama()
    job = MachineJob(rows=rows, source_lang="en", instruction=UI, all_rows=rows)
    run_machine_translation(server.provider(), job, TaskContext(), lambda _r: None)
    assert all(UI in r["messages"][0]["content"] for r in server.requests if "messages" in r)


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.show()
    yield w
    if w.task is not None:
        w.task.cancel()
        w.task.wait()
    w.dirty = False
    w.close()
    w.deleteLater()


def _dialog(w: MainWindow, **kw: object) -> MachineDialog:
    return MachineDialog(
        w,
        provider=str(kw.pop("provider", PROVIDER_OLLAMA)),
        base_url="",
        model="gemma4:12b",
        notes="",
        source_language="en",
        secrets=w.secrets,
        scopes=w._machine_scopes(),
        **kw,  # type: ignore[arg-type]
    )


@pytest.mark.gui
def test_dialog_keeps_translate_and_revise_instructions_apart(window: MainWindow) -> None:
    dialog = _dialog(window, action="translate", instruction="Doğal yaz.", translate_instruction="Eski talimat")
    dialog.advanced_toggle.setChecked(True)  # çeviri talimatı Gelişmiş altındadır
    assert dialog.instruction.isVisibleTo(dialog)
    assert dialog.instruction.toPlainText() == "Eski talimat"
    names = [dialog.presets.itemText(i) for i in range(1, dialog.presets.count())]
    assert names == [name for name, _ in TRANSLATE_PRESETS]
    assert names[0] == "Arayüz ve menü metinleri"
    dialog.presets.activated.emit(1)
    assert dialog.instruction.toPlainText() == TRANSLATE_PRESETS[0][1]
    assert dialog.settings().instruction == TRANSLATE_PRESETS[0][1]

    dialog.action_buttons["revise"].setChecked(True)  # redaksiyonun kendi talimatı ve hazır listesi
    assert dialog.instruction.toPlainText() == "Doğal yaz."
    assert dialog.presets.itemText(1) == INSTRUCTION_PRESETS[0][0]
    dialog.action_buttons["retranslate"].setChecked(True)  # yeniden çeviri, çeviri talimatını paylaşır
    assert dialog.instruction.toPlainText() == TRANSLATE_PRESETS[0][1]

    dialog.instruction.setPlainText("")
    dialog._accept()  # çeviri talimatı isteğe bağlıdır: boşken uyarı yok
    assert "talimat" not in dialog.status.text.text()


@pytest.mark.gui
def test_deepl_hides_translate_instruction(window: MainWindow) -> None:
    dialog = _dialog(window, provider=PROVIDER_DEEPL, action="translate", translate_instruction=UI)
    assert not dialog.instruction.isVisibleTo(dialog)
    assert not dialog.presets.isVisibleTo(dialog)
    assert dialog.settings().instruction == ""  # DeepL talimat izleyemez; gönderilmez


@pytest.mark.gui
def test_window_remembers_translate_instruction(qtbot: QtBot, window: MainWindow) -> None:
    server = FakeOllama()
    window.provider_factory = lambda s: server.provider(s.model)
    seen: list[str] = []

    def ask(
        scopes: Mapping[str, Sequence[TranslationRow]],
        action: str = "translate",
        scope: str = SCOPE_ALL,
    ) -> MachineSettings | None:
        return MachineSettings("ollama", "", "gemma4:12b", "", SCOPE_ALL, "translate", UI)

    window.ask_machine_settings = ask  # type: ignore[method-assign]
    window.start_machine_translation("translate")
    qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
    seen = [r["messages"][0]["content"] for r in server.requests if "messages" in r]
    assert seen
    assert all(UI in s for s in seen)
    assert window.project.setting("translate_instruction") == UI
    assert window.project.setting("revise_instruction") == ""  # redaksiyon talimatı değişmedi
