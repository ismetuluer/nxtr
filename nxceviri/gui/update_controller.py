"""Güncelleme denetleyicisi: Güncellemeleri Denetle penceresi, paket kurulumu ve açılıştaki sessiz denetim.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Denetleyici durum tutmaz; ayarlar, `secrets`,
`updater_factory`, `installer_launcher`, `relauncher`, `_update_task` ve `dirty` pencerede durur ve her çağrıda
pencereden okunur. Pencerede yönlendirmesi olan bir yöntem pencere üzerinden çağrılır (`self._win.<ad>`): testler
`updater_factory`, `_install_package`, `open_updates` gibi adları pencerede değiştirir. Testlerin pencere
modülünde değiştirdiği `UpdateDialog` pencere modülü üzerinden okunur. Bildirim denemesi (`_test_notification`),
görev düzeneği (`Task`) ve sinyal bağlantıları pencerede kalır.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from nxceviri import __version__
from nxceviri.core.errors import NxError
from nxceviri.core.progress import TaskContext
from nxceviri.core.secrets import GITHUB_UPDATE_KEY
from nxceviri.core.selfupdate import PreparedInstall, discard_prepared
from nxceviri.core.update import (
    GitHubUpdater,
    UpdateError,
    UpdateInfo,
    Updater,
    is_git_checkout,
    make_updater,
)
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_INFO, NoticeAction
from nxceviri.gui.tasks import Task
from nxceviri.gui.update_dialog import auto_check_enabled

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

log = logging.getLogger("nxceviri.gui.main_window")


class UpdateController:
    """Güncelleme denetimi ve kurulumu; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win

    def open_updates(self) -> None:
        # Döngüsel içe aktarma; testler `UpdateDialog`'u pencere modülünde değiştirir.
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        packaged = win.app_root is None and win.packaged
        root = win.install_dir if packaged else win.app_root
        if root is None:
            return
        dialog = _mw.UpdateDialog(
            win,
            secrets=win.secrets,
            settings=win.settings,
            current=__version__,
            root=root,
            updater_factory=win.updater_factory,
            git_mode=not packaged and is_git_checkout(root),
            packaged=packaged,
        )
        if dialog.exec() != _mw.UpdateDialog.DialogCode.Accepted or dialog.info is None:
            return
        win.update_badge.hide()
        version = dialog.info.version
        prepared = dialog.prepared
        if packaged:
            if prepared is not None and not win._install_package(prepared, root):
                discard_prepared(prepared)
            return
        later = f"{version} sürümü uygulama bir sonraki açılışında kurulacak."
        answer = QMessageBox.question(
            win,
            "Güncelleme hazır",
            f"{version} sürümü indirildi. Uygulama şimdi yeniden başlatılıp güncellensin mi?\n\n"
            "Hayır derseniz güncelleme bir sonraki açılışta kurulur.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            win.statusBar().showMessage(later, 10000)
            return
        if win.busy:
            win.notify(LEVEL_INFO, "Güncelleme hazır", "Önce süren işlemi bitirin veya iptal edin. " + later)
            return
        if not win._confirm_discard():
            win.statusBar().showMessage(later, 10000)
            return
        win.dirty = False  # kullanıcı az önce kaydetti veya değişiklikleri atmayı seçti
        win.relauncher(root)
        win.close()

    def _install_package(self, prepared: PreparedInstall, install_dir: Path) -> bool:
        """İndirilip doğrulanan paketi kurdurur: uygulama kapanır, yardımcı klasörü değiştirip yeniden açar.

        False dönerse kurulmadı (çağıran hazırlığı siler); sonra Yardım → Güncellemeleri Denetle ile yinelenebilir.
        """
        win = self._win
        retry = "Güncelleme yapılmadı. Daha sonra Yardım → Güncellemeleri Denetle ile yineleyebilirsiniz."
        answer = QMessageBox.question(
            win,
            "Güncelleme hazır",
            f"{prepared.version} sürümü indirildi ve doğrulandı. Uygulama şimdi kapatılıp güncellensin ve "
            "yeniden açılsın mı?\n\nProjeleriniz, eklentileriniz ve ayarlarınız olduğu gibi kalır.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            win.statusBar().showMessage(retry, 10000)
            return False
        if win.busy:
            win.notify(LEVEL_INFO, "Güncelleme hazır", "Önce süren işlemi bitirin veya iptal edin. " + retry)
            return False
        if not win._confirm_discard():
            win.statusBar().showMessage(retry, 10000)
            return False
        try:
            win.installer_launcher(prepared, install_dir)
        except UpdateError as exc:
            win.notify(LEVEL_ERROR, "Güncelleme", exc.user_text())
            return False
        win.dirty = False  # kullanıcı az önce kaydetti veya değişiklikleri atmayı seçti
        win.close()
        return True

    def check_updates_in_background(self) -> None:
        """Açılışta (ayar açıksa) yeni sürüm olup olmadığına sessizce bakar; varsa durum çubuğunda rozet çıkar."""
        win = self._win
        root = win.app_root
        if (root is None and not win.packaged) or win._update_task is not None or not auto_check_enabled(win.settings):
            return
        try:
            token = win.secrets.get(GITHUB_UPDATE_KEY)
        except NxError:
            token = None  # anahtar deposu okunamıyorsa anahtarsız denenir (açık depo); açılış bozulmaz
        factory = win.updater_factory

        def work(_ctx: TaskContext) -> object:
            updater = factory(token)
            try:
                return updater.check(__version__)
            finally:
                updater.close()

        task = Task(work, "Güncelleme denetimi")
        task.succeeded.connect(win._update_checked)
        task.failed.connect(lambda text: log.info("Açılıştaki güncelleme denetimi başarısız: %s", text))
        win._update_task = task
        task.start()

    def _default_updater(self, token: str | None) -> Updater:
        win = self._win
        if win.app_root is None:  # paketlenmiş sürüm: yalnızca yeni sürüm olup olmadığına bakılır
            return GitHubUpdater(token)
        return make_updater(win.app_root, token)

    def notify_update_failure(self, reason: str) -> None:
        """Önceki güncelleme kurulamadıysa açılışta bildirir; Tekrar Dene güncelleme penceresini açar."""
        win = self._win
        actions = (NoticeAction("Tekrar Dene", win.open_updates),) if win.update_action.isEnabled() else ()
        win.notifier.notify(LEVEL_ERROR, "Güncelleme kurulamadı", reason, actions, loud=True)

    def _update_checked(self, result: object) -> None:
        assert isinstance(result, UpdateInfo)
        win = self._win
        if result.newer:
            win.update_badge.setText(f"Yeni sürüm: {result.version} — Güncelle")
            win.update_badge.show()
            win.notifier.notify(
                LEVEL_INFO,
                f"Yeni sürüm: {result.version}",
                "Yenilikleri görmek ve kurmak için Şimdi Güncelle'ye basın.",
                (NoticeAction("Şimdi Güncelle", win.open_updates), NoticeAction("Sonra", lambda: None)),
                loud=True,
            )
