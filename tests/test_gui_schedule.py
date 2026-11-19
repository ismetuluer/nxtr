"""Arayüz: zamanlayıcı (haftalık takvimde otomatik çeviri / redaksiyon), saat ve sağlayıcı sahte."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import MemoryStore, api_key_name
from nxceviri.core.translate.providers.base import BatchItem, BatchResult, ProviderError, ProviderStatus, Scene
from nxceviri.core.translate.runner import ACTION_REVISE, ACTION_TRANSLATE
from nxceviri.core.translate.schedule import SCHEDULE_KEY, Schedule
from nxceviri.core.translate.status import Status
from nxceviri.gui.machine_dialogs import MachineSettings
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.schedule_controller import CHECK_MS, MAX_RETRIES, RETRY_DELAY
from nxceviri.gui.schedule_dialog import ScheduleDialog
from nxceviri.gui.step_nav import STEP_QA, STEP_TRANSLATE

pytestmark = pytest.mark.gui

# 2026-11-16 pazartesi; dilim pazartesi 01:00–03:00.
SLOT = frozenset({(0, 1), (0, 2)})
START = datetime(2026, 11, 16, 1, 0, 30)
END = datetime(2026, 11, 16, 3, 0, 30)


class FakeProvider:
    """Ağ kullanmayan sağlayıcı: `gate` verilirse her parti kapı açılana kadar bekler."""

    name = "fake"
    label = "Sahte"
    requires_api_key = False
    supports_glossary = False
    supports_instructions = True
    max_batch_chars = 10_000
    max_batch_items = 1

    def __init__(self, gate: threading.Event | None = None, *, ok: bool = True) -> None:
        self.gate = gate
        self.ok = ok

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(self.ok, "Bağlandı." if self.ok else "Hizmete bağlanılamadı.")

    def translate_batch(
        self,
        items: list[BatchItem],
        source_lang: str,
        target_lang: str,
        context: str,
        glossary: Any,
        *,
        scene: Scene | None = None,
    ) -> list[BatchResult]:
        if self.gate is not None:
            self.gate.wait(10)
        prefix = "dz-" if scene is not None and scene.revise else "tr-"
        return [BatchResult(i.id, prefix + i.text) for i in items]

    def estimate_cost(self, items: list[BatchItem]) -> str | None:
        return None

    def close(self) -> None:
        return None


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _project() -> Project:
    p = Project.new()
    p.import_texts(
        [
            ImportedFile(
                "Dialogue.tsv",
                "0100",
                "unity",
                "base",
                tuple(TextEntry(f"s{i}", i, f"Line {i}", ()) for i in range(4)),
            )
        ]
    )
    return p


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


def _save(w: MainWindow, tmp_path: Path) -> None:
    assert w.save_to(tmp_path / "proje.nxproj")


def _set_schedule(w: MainWindow, **kw: Any) -> None:
    base: dict[str, Any] = {"enabled": True, "cells": SLOT, "provider": "ollama", "model": "fake-model"}
    base.update(kw)
    w.project.set_setting(SCHEDULE_KEY, Schedule(**base).dump())


def _use(w: MainWindow, provider: FakeProvider) -> list[MachineSettings]:
    calls: list[MachineSettings] = []

    def factory(s: MachineSettings) -> FakeProvider:
        calls.append(s)
        return provider

    w.provider_factory = factory
    return calls


def _busy(w: MainWindow) -> bool:
    return w.task is not None


def _wait_idle(qtbot: QtBot, w: MainWindow) -> None:
    qtbot.waitUntil(lambda: w.task is None, timeout=20_000)


def _titles(w: MainWindow) -> list[str]:
    return [n.title for n in w.notifier.history]


def _statuses(w: MainWindow) -> list[str]:
    return [r.status for r in w.project.translation_rows()]


def test_starts_at_slot_start_and_translates(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    _set_schedule(window)
    calls = _use(window, FakeProvider())
    clock = Clock(datetime(2026, 11, 16, 0, 59))
    window.scheduler.clock = clock
    window.scheduler.tick()
    assert window.task is None
    assert not calls
    assert "Pzt 01:00" in window.scheduler.status_text()
    assert window.status_segments.schedule_label.text() == "Zamanlayıcı: sonraki Pzt 01:00"
    clock.now = START
    window.scheduler.tick()
    assert _busy(window)
    assert window.scheduler.status_text() == "Zamanlayıcı çalışıyor"
    _wait_idle(qtbot, window)
    assert calls[0].provider == "ollama"
    assert calls[0].model == "fake-model"
    assert all(s == Status.MACHINE for s in _statuses(window))
    titles = _titles(window)
    assert any(t.startswith("Zamanlayıcı") and "başladı" in t for t in titles)
    assert any(t.startswith("Zamanlayıcı") and "bitti" in t for t in titles)
    # Satır kalmadı: aynı dilimde yeniden başlamaz.
    clock.now = START + timedelta(minutes=30)
    window.scheduler.tick()
    assert window.task is None
    assert len(calls) == 1


def test_timer_drives_checks(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    timer = window.scheduler.timer
    assert timer.isActive()
    assert timer.interval() == CHECK_MS
    _save(window, tmp_path)
    _set_schedule(window)
    calls = _use(window, FakeProvider())
    window.scheduler.clock = Clock(START)
    timer.timeout.emit()
    _wait_idle(qtbot, window)
    assert calls
    window.dirty = False
    window.close()
    assert not timer.isActive()


def test_start_switches_to_translate_step(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    """İlerleme ve Durdur düğmesi Çevir adımında; iş sürerken kenar çubuğu kilitli olduğundan oraya geçilir."""
    _save(window, tmp_path)
    _set_schedule(window)
    _use(window, FakeProvider())
    window.nav.setCurrentRow(STEP_QA)
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    assert window.nav.currentRow() == STEP_TRANSLATE
    _wait_idle(qtbot, window)


def test_setup_failure_has_no_start_notice(window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    _set_schedule(window)

    def broken(_s: MachineSettings) -> FakeProvider:
        raise ProviderError("Hizmet kurulamadı.")

    window.provider_factory = broken
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    titles = _titles(window)
    assert not any("başladı" in t for t in titles)
    assert any("başlamadı" in t for t in titles)


def test_no_rows_no_restart(window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    rows = window.project.translation_rows()
    window.project.set_translations([(r.id, "hazır") for r in rows], machine=True)
    _set_schedule(window)
    calls = _use(window, FakeProvider())
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    window.scheduler.tick()
    assert window.task is None
    assert not calls


def test_waits_while_busy_then_starts(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    _set_schedule(window)
    calls = _use(window, FakeProvider())
    gate = threading.Event()

    def other(_ctx: TaskContext) -> None:
        gate.wait(10)

    window._run(other, "Başka iş", on_success=lambda _r: None, on_failure=lambda _t: None)
    other_task = window.task
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    assert window.task is other_task
    assert not calls
    gate.set()
    _wait_idle(qtbot, window)
    window.scheduler.tick()
    assert calls
    _wait_idle(qtbot, window)


def test_waits_while_modal_dialog_open(window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Açık pencere (ör. Otomatik Çeviri) kabul edilince ikinci iş başlamasın diye zamanlayıcı bekler."""
    _save(window, tmp_path)
    _set_schedule(window)
    calls = _use(window, FakeProvider())
    monkeypatch.setattr(QApplication, "activeModalWidget", staticmethod(lambda: window))
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    assert window.task is None
    assert not calls


def test_cancels_own_job_at_slot_end(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    _set_schedule(window)
    gate = threading.Event()
    _use(window, FakeProvider(gate))
    clock = Clock(START)
    window.scheduler.clock = clock
    window.scheduler.tick()
    assert _busy(window)
    clock.now = END
    window.scheduler.tick()
    gate.set()
    _wait_idle(qtbot, window)
    assert any("durduruldu" in t for t in _titles(window))
    # Dilim dışında yeniden başlamaz; kalan satırlar çevrilmemiş kalır.
    window.scheduler.tick()
    assert window.task is None
    assert Status.UNTRANSLATED in _statuses(window)


def test_never_cancels_users_job(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    _set_schedule(window)
    gate = threading.Event()
    cancelled: list[bool] = []

    def other(ctx: TaskContext) -> None:
        gate.wait(10)
        cancelled.append(ctx.token.cancelled)

    window._run(other, "Başka iş", on_success=lambda _r: None, on_failure=lambda _t: None)
    window.scheduler.clock = Clock(END)
    window.scheduler.tick()
    gate.set()
    _wait_idle(qtbot, window)
    assert cancelled == [False]


def test_manual_stop_is_not_restarted(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    _set_schedule(window)
    gate = threading.Event()
    calls = _use(window, FakeProvider(gate))
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    window._cancel_task()  # kullanıcı Durdur'a bastı
    gate.set()
    _wait_idle(qtbot, window)
    window.scheduler.tick()
    assert window.task is None
    assert len(calls) == 1


def test_retries_failures_with_cap(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    _set_schedule(window)
    calls = _use(window, FakeProvider(ok=False))
    clock = Clock(START)
    window.scheduler.clock = clock
    window.scheduler.tick()
    _wait_idle(qtbot, window)
    assert len(calls) == 1
    clock.now = START + timedelta(minutes=5)
    window.scheduler.tick()
    assert window.task is None
    assert len(calls) == 1
    for attempt in range(MAX_RETRIES):
        clock.now += RETRY_DELAY
        window.scheduler.tick()
        _wait_idle(qtbot, window)
        assert len(calls) == attempt + 2
    clock.now += RETRY_DELAY
    window.scheduler.tick()
    assert window.task is None
    assert len(calls) == 1 + MAX_RETRIES
    assert any("vazgeçti" in t for t in _titles(window))
    # Sonraki dilimde yeniden dener.
    clock.now = START + timedelta(days=7)
    window.scheduler.tick()
    _wait_idle(qtbot, window)
    assert len(calls) == 2 + MAX_RETRIES


def test_missing_key_notifies_without_retry(window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    _set_schedule(window, provider="anthropic", model="claude-x")
    calls = _use(window, FakeProvider())
    clock = Clock(START)
    window.scheduler.clock = clock
    window.scheduler.tick()
    assert window.task is None
    assert not calls
    assert any("anahtar" in n.text.casefold() for n in window.notifier.history)
    clock.now = START + RETRY_DELAY * 2
    window.scheduler.tick()
    assert not calls


def test_key_present_starts_cloud_provider(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    window.secrets.set(api_key_name("anthropic"), "sk-deneme")
    _set_schedule(window, provider="anthropic", model="claude-x")
    calls = _use(window, FakeProvider())
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    _wait_idle(qtbot, window)
    assert calls
    assert calls[0].provider == "anthropic"


def test_refuses_unsaved_project(window: MainWindow) -> None:
    assert window.project.path is None
    _set_schedule(window)
    calls = _use(window, FakeProvider())
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    assert window.task is None
    assert not calls
    assert "kaydedilmedi" in window.scheduler.status_text()
    dialog = ScheduleDialog(window, window.scheduler.schedule(), saved=False, **window.scheduler.dialog_options())
    assert not dialog.enabled.isEnabled()
    assert not dialog.enabled.isChecked()
    assert dialog.notice.isVisibleTo(dialog)
    dialog.deleteLater()


def test_revise_scope_skips_already_revised(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    rows = window.project.translation_rows()
    window.project.set_translations([(r.id, "çeviri") for r in rows], machine=True, job="translate-1")
    window.project.set_translations([(rows[0].id, "redakte")], machine=True, job="revise-1")
    _set_schedule(window, action=ACTION_REVISE, instruction="Kısa yaz.")
    calls = _use(window, FakeProvider())
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    _wait_idle(qtbot, window)
    assert calls
    assert calls[0].action == ACTION_REVISE
    assert calls[0].instruction == "Kısa yaz."
    texts = {r.id: r.translation for r in window.project.translation_rows()}
    assert texts[rows[0].id] == "redakte"
    assert all(texts[r.id].startswith("dz-") for r in rows[1:])


def test_disabling_cancels_running_job(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    _set_schedule(window)
    gate = threading.Event()
    _use(window, FakeProvider(gate))
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    assert _busy(window)
    _set_schedule(window, enabled=False)
    window.scheduler.tick()
    gate.set()
    _wait_idle(qtbot, window)
    assert any("durduruldu" in t for t in _titles(window))


def test_project_switch_resets_state(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    _set_schedule(window)
    calls = _use(window, FakeProvider(ok=False))
    window.scheduler.clock = Clock(START)
    window.scheduler.tick()
    _wait_idle(qtbot, window)
    assert len(calls) == 1
    window._replace_project(_project())
    window.save_to(tmp_path / "ikinci.nxproj")
    _set_schedule(window)
    window.scheduler.tick()  # yeni projenin bekleyen yeniden denemesi yok
    _wait_idle(qtbot, window)
    assert len(calls) == 2


# --- pencere ----------------------------------------------------------------------------------


def _dialog(window: MainWindow, schedule: Schedule | None = None) -> ScheduleDialog:
    return ScheduleDialog(
        window, schedule or window.scheduler.schedule(), saved=True, **window.scheduler.dialog_options()
    )


def _center(dialog: ScheduleDialog, day: int, hour: int) -> QPoint:
    return dialog.grid.cell_rect(day, hour).center()


def test_grid_click_toggles_and_drag_paints(window: MainWindow) -> None:
    dialog = _dialog(window)
    grid = dialog.grid
    dialog.show()
    QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=_center(dialog, 0, 1))
    assert grid.cells() == {(0, 1)}
    QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=_center(dialog, 0, 1))
    assert grid.cells() == set()
    # Sürükle: başlangıç boşsa boyar.
    QTest.mousePress(grid, Qt.MouseButton.LeftButton, pos=_center(dialog, 2, 3))
    QTest.mouseMove(grid, _center(dialog, 2, 5))
    QTest.mouseMove(grid, _center(dialog, 3, 5))
    QTest.mouseRelease(grid, Qt.MouseButton.LeftButton, pos=_center(dialog, 3, 5))
    assert grid.cells() == {(2, 3), (2, 4), (2, 5), (3, 3), (3, 4), (3, 5)}
    # Seçili hücreden başlayan sürükleme siler.
    QTest.mousePress(grid, Qt.MouseButton.LeftButton, pos=_center(dialog, 2, 3))
    QTest.mouseMove(grid, _center(dialog, 3, 3))
    QTest.mouseRelease(grid, Qt.MouseButton.LeftButton, pos=_center(dialog, 3, 3))
    assert grid.cells() == {(2, 4), (2, 5), (3, 4), (3, 5)}
    assert "Sonraki çalışma:" in dialog.next_label.text()
    dialog.close()
    dialog.deleteLater()


def test_dialog_revise_needs_instruction_capable_provider(window: MainWindow) -> None:
    dialog = _dialog(window, Schedule(provider="deepl"))
    revise = dialog.action.findData(ACTION_REVISE)
    assert not dialog.action.model().item(revise).isEnabled()  # type: ignore[attr-defined]
    dialog.set_provider("ollama")
    assert dialog.action.model().item(revise).isEnabled()  # type: ignore[attr-defined]
    dialog.action.setCurrentIndex(revise)
    assert dialog.instruction.isVisibleTo(dialog)
    dialog.deleteLater()


def test_dialog_defaults_to_last_used_provider(window: MainWindow) -> None:
    window.settings.setValue("translate/provider", "gemini")
    window.settings.setValue("provider/gemini/model", "gemini-pro")
    dialog = _dialog(window)
    assert dialog.provider_name == "gemini"
    assert dialog.model.currentText() == "gemini-pro"
    dialog.deleteLater()


def test_dialog_settings_persist_in_project(window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    # `save` hemen denetler: gerçek saat ve gerçek sağlayıcı kullanılmasın (dilim dışında sahte saat).
    window.scheduler.clock = Clock(datetime(2026, 11, 15, 12))
    _use(window, FakeProvider())
    dialog = _dialog(window)
    dialog.set_provider("ollama")
    dialog.model.setEditText("gemma4:12b")
    dialog.grid.set_cells({(0, 1), (0, 2)})
    dialog.enabled.setChecked(True)
    dialog.action.setCurrentIndex(dialog.action.findData(ACTION_TRANSLATE))
    assert dialog.validate()
    window.scheduler.save(dialog.schedule())
    dialog.deleteLater()
    path = window.project.path
    assert path is not None
    window._replace_project(Project.open(path))
    saved = window.scheduler.schedule()
    assert saved.enabled
    assert saved.cells == {(0, 1), (0, 2)}
    assert saved.provider == "ollama"
    assert saved.model == "gemma4:12b"
    window.scheduler.clock = Clock(datetime(2026, 11, 15, 12))
    window.scheduler.tick()
    assert window.scheduler.status_text() == "Zamanlayıcı: sonraki Pzt 01:00"


def test_dialog_test_connection(window: MainWindow) -> None:
    provider = FakeProvider()
    calls = _use(window, provider)
    dialog = _dialog(window, Schedule(provider="ollama", model="m"))
    assert dialog.test_connection()
    assert calls[-1].model == "m"
    assert "Bağlandı" in dialog.status.text.text()
    provider.ok = False
    assert not dialog.test_connection()
    assert "bağlanılamadı" in dialog.status.text.text()
    dialog.deleteLater()


def test_dialog_refuses_enable_without_hours(window: MainWindow) -> None:
    dialog = _dialog(window, Schedule(provider="ollama", model="m"))
    dialog.enabled.setChecked(True)
    assert not dialog.validate()
    assert dialog.status.isVisibleTo(dialog)
    dialog.deleteLater()


def test_menu_command_opens_dialog(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[bool] = []
    monkeypatch.setattr(window.scheduler, "open_dialog", lambda: opened.append(True))
    action = window.menu_actions["translate.schedule"]
    assert action.isEnabled()
    action.trigger()
    assert opened == [True]


class UnchangedProvider(FakeProvider):
    """Redaksiyonda metni değiştirmeden geri veren sağlayıcı (geçmişe redaksiyon yazılmaz)."""

    def translate_batch(
        self,
        items: list[BatchItem],
        source_lang: str,
        target_lang: str,
        context: str,
        glossary: Any,
        *,
        scene: Scene | None = None,
    ) -> list[BatchResult]:
        return [BatchResult(i.id, i.current or i.text) for i in items]


def test_revise_does_not_resend_rows_left_unchanged(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _save(window, tmp_path)
    rows = window.project.translation_rows()
    window.project.set_translations([(r.id, "çeviri") for r in rows], machine=True, job="translate-1")
    _set_schedule(window, action=ACTION_REVISE, instruction="Kısa yaz.")
    calls = _use(window, UnchangedProvider())
    clock = Clock(START)
    window.scheduler.clock = clock
    window.scheduler.tick()
    _wait_idle(qtbot, window)
    assert len(calls) == 1
    # Ertesi haftanın aynı dilimi: model hiçbir şeyi değiştirmemişti, satırlar yeniden gönderilmez.
    clock.now = START + timedelta(days=7)
    window.scheduler.tick()
    assert window.task is None
    assert len(calls) == 1
    # Metni sonradan değişen satır yeniden adaydır.
    window.project.set_translations([(rows[0].id, "yeni çeviri")], machine=True, job="translate-2")
    clock.now = START + timedelta(days=14)
    window.scheduler.tick()
    _wait_idle(qtbot, window)
    assert len(calls) == 2
