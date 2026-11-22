"""Arayüz: tek düğmeyle güncelleme (durum çubuğu), açılıştaki onay ve Güncellemeleri Denetle penceresi."""

from __future__ import annotations

import io
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from nxceviri import __version__
from nxceviri.core.secrets import GITHUB_UPDATE_KEY, MemoryStore
from nxceviri.core.selfupdate import PACKAGE_EXE, PreparedInstall
from nxceviri.core.update import RELEASES_URL, pending_version
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.update_controller import INSTALLING_KEY
from nxceviri.gui.update_dialog import AUTO_CHECK_KEY, UpdateDialog, auto_check_enabled
from tests.test_update import TOKEN, FakeGitHub

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    # Hiçbir akış soru penceresi açmamalı; açarsa test burada yakalar.
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("beklenmeyen soru penceresi"))
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w.show()
    yield w
    task = w.updates.download_task
    if task is not None:
        task.cancel()
        task.wait()
    w.dirty = False
    w.close()
    w.deleteLater()


def _source_install(tmp_path: Path) -> Path:
    root = tmp_path / "uygulama"
    (root / "nxceviri").mkdir(parents=True)
    return root


def _package() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"NXTR/{PACKAGE_EXE}", b"MZ-yeni")
    return buf.getvalue()


def _packaged(window: MainWindow, tmp_path: Path, server: FakeGitHub) -> tuple[Path, list[PreparedInstall]]:
    install = tmp_path / "Programlar" / "NXTR"
    install.mkdir(parents=True)
    (install / PACKAGE_EXE).write_bytes(b"MZ-eski")
    window.app_root = None
    window.packaged = True
    window.install_dir = install
    window.updater_factory = server.updater
    handed: list[PreparedInstall] = []
    window.installer_launcher = lambda prepared, folder: handed.append(prepared)
    return install, handed


def _found(qtbot: QtBot, window: MainWindow) -> None:
    window.check_updates_in_background()
    task = window._update_task
    assert task is not None
    qtbot.waitUntil(lambda: window.update_badge.isVisibleTo(window), timeout=10_000)
    task.wait()


def test_one_click_packaged_update_installs_without_questions(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    install, handed = _packaged(window, tmp_path, FakeGitHub(version="99.0.0", package=_package()))
    _found(qtbot, window)
    assert window.update_badge.text() == "Güncelle · 99.0.0"
    window.update_badge.click()  # tek tık: iner, doğrulanır, kurulum yardımcısına verilir, uygulama kapanır
    qtbot.waitUntil(lambda: len(handed) == 1, timeout=20_000)
    assert (handed[0].new_dir / PACKAGE_EXE).read_bytes() == b"MZ-yeni"
    assert (install / PACKAGE_EXE).read_bytes() == b"MZ-eski"  # kurulumu yardımcı yapar, uygulama değil
    assert window.settings.value(INSTALLING_KEY) == "99.0.0"
    assert not window.isVisible()


def test_one_click_source_update_relaunches(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    root = _source_install(tmp_path)
    window.app_root = root
    window.updater_factory = FakeGitHub(version="99.0.0").updater
    restarted: list[Path] = []
    window.relauncher = restarted.append
    _found(qtbot, window)
    window.start_update()
    qtbot.waitUntil(lambda: restarted == [root], timeout=20_000)
    assert pending_version(root) == "99.0.0"
    assert not window.isVisible()


def test_badge_shows_download_progress(window: MainWindow) -> None:
    window.updates._on_progress(47 * 1024 * 1024, 87 * 1024 * 1024, "İndiriliyor")
    assert window.update_badge.text() == "%54 · 47 / 87 MB"


def test_unsaved_new_project_asks_once_then_badge_waits(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install, handed = _packaged(window, tmp_path, FakeGitHub(version="99.0.0", package=_package()))
    window.dirty = True  # kaydedilmemiş yeni proje
    answers = ["cancel", "discard"]
    monkeypatch.setattr(window, "ask_save_changes", lambda closing: answers.pop(0))
    _found(qtbot, window)
    window.update_badge.click()
    qtbot.waitUntil(lambda: window.update_badge.text() == "Yeniden başlat · 99.0.0", timeout=20_000)
    assert handed == []
    assert window.isVisible()
    window.update_badge.click()  # inen sürüm bekliyor: yeniden indirilmez
    assert len(handed) == 1
    assert not window.isVisible()


def test_failed_download_offers_retry(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    _packaged(window, tmp_path, FakeGitHub(version="99.0.0", package=_package(), checksum="0" * 64))
    _found(qtbot, window)
    window.update_badge.click()
    qtbot.waitUntil(lambda: window.updates.download_task is None, timeout=20_000)
    notice = window.notifier.history[0]
    assert notice.title == "Güncelleme indirilemedi"
    assert [a.label for a in notice.actions] == ["Tekrar Dene"]
    assert window.update_badge.text() == "Güncelle · 99.0.0"
    assert window.isVisible()


def test_unwritable_folder_points_to_manual_download(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(*_a: Any, **_k: Any) -> Any:
        raise PermissionError("erişim reddedildi")

    monkeypatch.setattr(tempfile, "TemporaryFile", denied)
    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    _packaged(window, tmp_path, FakeGitHub(version="99.0.0", package=_package()))
    _found(qtbot, window)
    window.update_badge.click()
    qtbot.waitUntil(lambda: window.updates.download_task is None, timeout=20_000)
    notice = window.notifier.history[0]
    assert notice.title == "Güncelleme kurulamadı"
    assert "yazma izniniz yok" in notice.text
    notice.actions[0].callback()
    assert opened == [RELEASES_URL]


def test_startup_announces_installed_version_once(window: MainWindow) -> None:
    window.settings.setValue(INSTALLING_KEY, __version__)
    window.announce_update_installed()
    notice = window.notifier.history[0]
    assert notice.title == f"{__version__} kuruldu"
    assert [a.label for a in notice.actions] == ["Yenilikler"]
    assert window.settings.value(INSTALLING_KEY) is None
    window.announce_update_installed()
    assert len(window.notifier.history) == 1


def test_startup_stays_quiet_when_install_did_not_happen(window: MainWindow) -> None:
    window.settings.setValue(INSTALLING_KEY, "99.0.0")  # kurulamadı: eski sürümle açıldı
    window.announce_update_installed()
    assert window.notifier.history == []
    assert window.settings.value(INSTALLING_KEY) is None


def test_background_check_is_anonymous_and_shows_badge(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    server = FakeGitHub(version="99.0.0")
    window.app_root = _source_install(tmp_path)
    window.updater_factory = server.updater
    _found(qtbot, window)  # anahtar kayıtlı değil: yine de denetler
    assert window.update_badge.text() == "Güncelle · 99.0.0"
    assert all("Authorization" not in r.headers for r in server.requests)


def test_background_check_respects_setting_and_stays_quiet_on_failure(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    window.app_root = tmp_path
    window.updater_factory = FakeGitHub(version="99.0.0").updater
    window.settings.setValue(AUTO_CHECK_KEY, "false")
    window.check_updates_in_background()
    assert window._update_task is None  # ayar kapalı: hiç denetlenmez
    window.settings.setValue(AUTO_CHECK_KEY, "true")
    window.updater_factory = FakeGitHub(private=True).updater  # anahtar yok: erişilemez
    window.check_updates_in_background()
    task = getattr(window, "_update_task")  # noqa: B009 - mypy önceki "None" denetimini kalıcı sanıyor
    assert task is not None
    task.wait()
    qtbot.wait(50)
    assert not window.update_badge.isVisibleTo(window)  # açılışta kullanıcı rahatsız edilmez
    assert not any(isinstance(w, QMessageBox) and w.isVisible() for w in QApplication.topLevelWidgets())


# --- Güncellemeleri Denetle penceresi ------------------------------------------------------


def _update_dialog(window: MainWindow, server: FakeGitHub, **kwargs: Any) -> UpdateDialog:
    return UpdateDialog(
        window,
        secrets=window.secrets,
        settings=window.settings,
        current="0.28.0",
        updater_factory=server.updater,
        **kwargs,
    )


def test_dialog_checks_on_open_and_update_starts_one_click_flow(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = FakeGitHub(version="99.0.0")
    dialog = _update_dialog(window, server)
    qtbot.addWidget(dialog)
    assert not dialog.key_box.isVisibleTo(dialog)  # anahtar adımları baştan görünmez
    window.secrets.set(GITHUB_UPDATE_KEY, "github_pat_x")  # eski bir kayıtlı anahtar olsa bile
    dialog.show()  # açılınca kendiliğinden denetler
    qtbot.waitUntil(lambda: dialog._task is None and dialog.info is not None, timeout=10_000)
    assert "Yeni sürüm var: 99.0.0" in dialog.status.text.text()
    assert all("Authorization" not in r.headers for r in server.requests)
    assert "99.0.0 notları" in dialog.notes.toPlainText()
    assert "##" not in dialog.notes.toPlainText()
    assert dialog.install.text() == "Güncelle"
    with qtbot.waitSignal(dialog.accepted, timeout=1_000):
        dialog.install.click()  # pencerede indirme yok: durum çubuğundaki akış sürdürür

    started: list[bool] = []
    monkeypatch.setattr(window, "start_update", lambda: started.append(True))

    class Accepting:
        DialogCode = UpdateDialog.DialogCode

        def __init__(self, *_a: Any, **_k: Any) -> None:
            self.info = dialog.info

        def exec(self) -> UpdateDialog.DialogCode:
            return UpdateDialog.DialogCode.Accepted

    from nxceviri.gui import main_window as main_window_module

    monkeypatch.setattr(main_window_module, "UpdateDialog", Accepting)
    window.app_root = _source_install(tmp_path)
    window.open_updates()
    assert started == [True]
    assert window.updates.info is dialog.info


def test_dialog_private_repo_shows_key_steps_then_checks(qtbot: QtBot, window: MainWindow) -> None:
    server = FakeGitHub(version="99.0.0", private=True)
    dialog = _update_dialog(window, server)
    qtbot.addWidget(dialog)
    dialog.check_now()
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    assert dialog.key_box.isVisibleTo(dialog)  # anahtarsız erişim başarısız: adımlar görünür
    assert "anahtarı gerekir" in dialog.status.text.text()
    assert dialog.key_state.text() == "Kayıtlı anahtar: yok"
    assert not dialog.manual.isVisibleTo(dialog)
    dialog.key.setText(TOKEN)
    dialog._save_key()  # kaydedince hemen yeniden denetler
    assert window.secrets.get(GITHUB_UPDATE_KEY) == TOKEN
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    assert "Yeni sürüm var: 99.0.0" in dialog.status.text.text()
    assert not dialog.key_box.isVisibleTo(dialog)
    assert server.requests[-1].headers["Authorization"] == f"Bearer {TOKEN}"


def test_dialog_rate_limit_is_not_a_key_problem(qtbot: QtBot, window: MainWindow) -> None:
    dialog = _update_dialog(window, FakeGitHub(rate_limited=True))
    qtbot.addWidget(dialog)
    dialog.check_now()
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    assert "istek sınırı doldu" in dialog.status.text.text()
    assert not dialog.key_box.isVisibleTo(dialog)


def test_dialog_auto_check_setting_persists(qtbot: QtBot, window: MainWindow) -> None:
    assert auto_check_enabled(window.settings)  # varsayılan: açık
    dialog = _update_dialog(window, FakeGitHub())
    qtbot.addWidget(dialog)
    assert dialog.auto.isChecked()
    dialog.auto.setChecked(False)
    assert not auto_check_enabled(window.settings)
    again = _update_dialog(window, FakeGitHub())
    qtbot.addWidget(again)
    assert not again.auto.isChecked()  # yeniden açılınca hatırlanır
    dialog.auto.setChecked(True)
    assert auto_check_enabled(window.settings)


def test_dialog_in_git_mode_suggests_git_pull(qtbot: QtBot, window: MainWindow) -> None:
    dialog = _update_dialog(window, FakeGitHub(version="99.0.0"), git_mode=True)
    qtbot.addWidget(dialog)
    dialog.check_now()
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    assert not dialog.key_box.isVisibleTo(dialog)
    assert "git pull" in dialog.status.text.text()
    assert not dialog.install.isVisibleTo(dialog)  # git deposunda kendiliğinden güncelleme yok
    assert dialog.notes.isVisibleTo(dialog)
