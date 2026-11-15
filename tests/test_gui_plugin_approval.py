"""Eklenti onayı arayüzü: açılış sorusu, Eklentiler penceresinde "Onay bekliyor" ve "Onayla ve Yükle"."""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QAbstractButton, QMessageBox
from pytestqt.qtbot import QtBot

from nxceviri.core.formats import registry
from nxceviri.core.plugins import loader
from nxceviri.core.plugins.loader import PluginInfo, PluginReport, plugin_fingerprint
from nxceviri.core.plugins.trust import PluginTrust
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.plugin_approval import WARNING_TEXT, approval_text, ask_approval
from nxceviri.gui.plugins_dialog import STATUS_OK, STATUS_PENDING, PluginsDialog
from tests.test_plugins import PLUGIN_BODY, make_plugin

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(loader, "repo_plugin_dir", lambda: None)  # makinedeki depo eklentileri yüklenmesin
    registry.reset_user_plugins()
    yield
    registry.reset_user_plugins()


def _side_effect_plugin(root: Path, marker: Path) -> Path:
    body = f"from pathlib import Path\nPath({str(marker)!r}).write_text('calisti')\n" + PLUGIN_BODY.format(
        kind="demo_kind"
    )
    return make_plugin(root, "demo", body=body)


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = MainWindow(QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat))
    w.show()
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_trust_store_uses_isolated_user_data_dir(window: MainWindow, tmp_path: Path) -> None:
    assert window.plugin_trust.path == loader.user_data_dir() / "eklenti_onaylari.json"
    assert not window.plugin_trust.path.exists()  # pencere kurulurken yazılmaz


def test_approval_text_mentions_manifest_folder_and_warning(tmp_path: Path) -> None:
    info = PluginInfo(
        ad="demo", surum="1.2", yazar="Ayşe", yol=tmp_path / "demo", api=1, oyunlar=(), onay_bekliyor=True
    )
    text = approval_text(info, changed=False)
    for part in ("demo", "1.2", "Ayşe", str(tmp_path / "demo"), WARNING_TEXT):
        assert part in text
    assert "değişti" not in text
    assert "değişti" in approval_text(info, changed=True)


def test_question_box_defaults_to_not_now(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str, str, list[str]]] = []

    def fake_exec(box: QMessageBox) -> int:
        default, escape = box.defaultButton(), box.escapeButton()
        assert default is not None
        assert isinstance(escape, QAbstractButton)
        seen.append((box.windowTitle(), default.text(), escape.text(), [b.text() for b in box.buttons()]))
        return 0  # tıklanmadan kapandı

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    info = PluginInfo(ad="demo", surum="1", yazar="y", yol=tmp_path, api=1, oyunlar=(), onay_bekliyor=True)
    assert ask_approval(None, info, changed=False) is False
    assert seen == [("Yeni eklenti bulundu", "Şimdi Değil", "Şimdi Değil", ["Yükle", "Şimdi Değil"])]


def test_startup_question_not_now_keeps_plugin_unloaded(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "calisti.txt"
    _side_effect_plugin(tmp_path / "ek", marker)
    registry.load_user_plugins([tmp_path / "ek"], trusted=window.plugin_trust.is_trusted)
    asked: list[tuple[str, bool]] = []

    def decline(info: PluginInfo, changed: bool) -> bool:
        asked.append((info.ad, changed))
        return False

    monkeypatch.setattr(window, "ask_plugin_approval", decline)
    window.offer_new_plugins([tmp_path / "ek"])
    assert asked == [("demo", False)]
    assert not marker.exists()
    assert registry.plugin_for_kind("demo_kind") is None
    assert not window.plugin_trust.path.exists()


def test_startup_question_load_saves_approval_and_loads_now(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "calisti.txt"
    folder = _side_effect_plugin(tmp_path / "ek", marker)
    registry.load_user_plugins([tmp_path / "ek"], trusted=window.plugin_trust.is_trusted)
    monkeypatch.setattr(window, "ask_plugin_approval", lambda _info, _changed: True)
    window.offer_new_plugins([tmp_path / "ek"])
    assert marker.exists()
    assert registry.plugin_for_kind("demo_kind") is not None
    assert window.plugin_trust.is_trusted(folder, plugin_fingerprint(folder))

    (folder / "ek.py").write_text("X = 1\n", encoding="utf-8")  # içerik değişti: yine sorulur, "değişti" bilgisiyle
    registry.load_user_plugins([tmp_path / "ek"], trusted=window.plugin_trust.is_trusted)
    asked: list[bool] = []

    def decline(_info: PluginInfo, changed: bool) -> bool:
        asked.append(changed)
        return False

    monkeypatch.setattr(window, "ask_plugin_approval", decline)
    window.offer_new_plugins([tmp_path / "ek"])
    assert asked == [True]
    assert registry.plugin_for_kind("demo_kind") is None


def test_startup_question_skipped_while_busy(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _side_effect_plugin(tmp_path / "ek", tmp_path / "calisti.txt")
    registry.load_user_plugins([tmp_path / "ek"], trusted=window.plugin_trust.is_trusted)
    asked: list[str] = []

    def accept(info: PluginInfo, _changed: bool) -> bool:
        asked.append(info.ad)
        return True

    monkeypatch.setattr(window, "ask_plugin_approval", accept)
    with monkeypatch.context() as busy:  # pencere kapanmadan geri alınır (kapanış "iş çalışıyor" diye sormasın)
        busy.setattr(MainWindow, "busy", property(lambda _self: True))
        window.offer_new_plugins([tmp_path / "ek"])
    assert asked == []


def _pending_dialog(qtbot: QtBot, tmp_path: Path, marker: Path) -> tuple[PluginsDialog, PluginTrust]:
    _side_effect_plugin(tmp_path / "ek", marker)
    trust = PluginTrust(tmp_path / "onay.json")
    report = registry.load_user_plugins([tmp_path / "ek"], trusted=trust.is_trusted)

    def reload() -> PluginReport | None:
        return registry.load_user_plugins([tmp_path / "ek"], trusted=trust.is_trusted)

    dialog = PluginsDialog(
        None,
        report=report,
        builtin=registry.BUILTIN_PLUGINS,
        install_dir=tmp_path / "kurulum",
        trust=trust,
        reload=reload,
    )
    qtbot.addWidget(dialog)
    return dialog, trust


def test_dialog_shows_pending_and_approves_and_loads(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "calisti.txt"
    dialog, trust = _pending_dialog(qtbot, tmp_path, marker)
    assert dialog.table.item(0, 4).text() == STATUS_PENDING  # type: ignore[union-attr]
    assert not dialog.approve_button.isEnabled()
    dialog.table.selectRow(0)
    assert dialog.approve_button.isEnabled()
    assert dialog.approve_button.text() == "Onayla ve Yükle"

    monkeypatch.setattr(dialog, "confirm_approval", lambda _info, _changed: False)
    dialog.approve_selected()
    assert not marker.exists()
    assert not trust.path.exists()

    monkeypatch.setattr(dialog, "confirm_approval", lambda _info, _changed: True)
    dialog.table.selectRow(0)
    dialog.approve_selected()
    assert marker.exists()
    assert registry.plugin_for_kind("demo_kind") is not None
    assert dialog.table.item(0, 4).text() == STATUS_OK  # type: ignore[union-attr]
    assert dialog.banner.property("state") == "success"


def test_dialog_approval_without_reload_asks_for_restart(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "calisti.txt"
    dialog, trust = _pending_dialog(qtbot, tmp_path, marker)
    monkeypatch.setattr(dialog, "_reload", lambda: None)  # ör. bir iş çalışıyor
    monkeypatch.setattr(dialog, "confirm_approval", lambda _info, _changed: True)
    dialog.table.selectRow(0)
    dialog.approve_selected()
    assert not marker.exists()
    assert trust.path.exists()
    assert "yeniden başlatın" in dialog.banner.text.text()


def test_plugin_installed_from_dialog_counts_as_approved(qtbot: QtBot, tmp_path: Path) -> None:
    marker = tmp_path / "calisti.txt"
    dialog, trust = _pending_dialog(qtbot, tmp_path, marker)
    archive = tmp_path / "e.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("eklenti.toml", 'ad = "yeni"\nsurum = "1"\nyazar = "y"\napi = 1\n')
        zf.writestr("plugin.py", PLUGIN_BODY.format(kind="yeni_kind"))
    assert dialog.install(archive)
    target = tmp_path / "kurulum" / "yeni"
    assert trust.is_trusted(target, plugin_fingerprint(target))
    report = registry.load_user_plugins([tmp_path / "kurulum"], trusted=trust.is_trusted)
    assert report.infos[0].yuklu
