"""Güncelleme denetleyicisi: durum çubuğundaki tek düğmeyle güncelleme, açılıştaki sessiz denetim ve pencere.

Akış tek düğmededir: açılıştaki denetim yeni sürüm bulursa durum çubuğunda “Güncelle · sürüm” düğmesi çıkar.
Basınca sürüm arka planda iner ve doğrulanır, düğme ilerlemeyi gösterir; bitince uygulama sormadan kapanıp yeni
sürümle açılır (proje dosyaya kayıtlıysa zaten kaydedilmiştir; kaydedilmemiş yeni proje varsa kaydetme sorulur;
süren bir iş varsa düğme “Yeniden başlat” olur). Açılışta yeni sürümle açıldıysa “kuruldu” bildirilir.
Yardım → Güncellemeleri Denetle penceresi yalnızca elle denetim ve özel depo anahtarı içindir; oradaki Güncelle
aynı akışı başlatır.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Ayarlar, `secrets`, `updater_factory`,
`installer_launcher`, `relauncher`, `_update_task` ve `dirty` pencerede durur ve her çağrıda pencereden okunur.
Testlerin pencere modülünde değiştirdiği `UpdateDialog` pencere modülü üzerinden okunur.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from nxceviri import __version__
from nxceviri.core.errors import NxError
from nxceviri.core.progress import TaskContext
from nxceviri.core.secrets import GITHUB_UPDATE_KEY
from nxceviri.core.selfupdate import PreparedInstall, discard_prepared, prepare_package
from nxceviri.core.update import (
    RELEASES_URL,
    REPO_NAME,
    REPO_OWNER,
    GitHubUpdater,
    UpdateError,
    UpdateInfo,
    Updater,
    is_git_checkout,
    make_updater,
)
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_INFO, LEVEL_SUCCESS, NoticeAction
from nxceviri.gui.tasks import Task
from nxceviri.gui.update_dialog import Problem, auto_check_enabled, guarded

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

log = logging.getLogger("nxceviri.gui.main_window")

#: QSettings anahtarı: kurulmak üzere kapatılan sürüm. Açılışta bu sürümle açıldıysa “kuruldu” bildirilir.
INSTALLING_KEY = "update/installing"
_MB = 1024 * 1024


def _mb(size: int) -> str:
    return f"{size / _MB:.0f}"


class UpdateController:
    """Güncelleme denetimi ve kurulumu; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win
        #: Son denetimde bulunan yeni sürüm (yoksa None).
        self.info: UpdateInfo | None = None
        #: Durum çubuğundaki indirme işi (sürerken None değildir).
        self.download_task: Task | None = None
        #: İndirilip doğrulanmış, kurulmayı bekleyen sürüm: paket (`PreparedInstall`) ya da kaynak kurulumda True.
        self._ready: PreparedInstall | bool | None = None

    # --- durum çubuğu düğmesi --------------------------------------------------------------

    def _badge(self, text: str, tip: str) -> None:
        badge = self._win.update_badge
        badge.setText(text)
        badge.setToolTip(tip)
        badge.show()

    def _badge_idle(self) -> None:
        if self.info is not None:
            self._badge(f"Güncelle · {self.info.version}", "İndirip yeni sürümle yeniden açar.")
        else:
            self._win.update_badge.hide()

    def _target(self) -> tuple[Path | None, bool]:
        """(kurulum klasörü, paketlenmiş mi). Klasör yoksa ya da git deposuysa kendiliğinden güncellenemez."""
        win = self._win
        packaged = win.app_root is None and win.packaged
        root = win.install_dir if packaged else win.app_root
        if root is not None and not packaged and is_git_checkout(root):
            return None, False
        return root, packaged

    def _token(self) -> str | None:
        try:
            return self._win.secrets.get(GITHUB_UPDATE_KEY)
        except NxError:
            return None  # anahtar deposu okunamıyorsa anahtarsız denenir (açık depo)

    def start_update(self) -> None:
        """Durum çubuğundaki düğme: iner, doğrulanır, uygulama yeni sürümle açılır. İnerken basmak bir şey yapmaz."""
        if self.download_task is not None:
            return
        if self._ready is not None:
            self._finish()
            return
        info = self.info
        root, packaged = self._target()
        if info is None or root is None:
            self._win.open_updates()  # git deposu ya da bilinmeyen sürüm: pencere ne yapılacağını söyler
            return
        token = self._token()
        factory = self._win.updater_factory

        def work(ctx: TaskContext) -> object:
            updater = factory(token)
            try:
                if not isinstance(updater, GitHubUpdater):
                    raise UpdateError("Bu kurulumda otomatik güncelleme yapılamıyor.")
                if packaged:
                    return prepare_package(updater, info, root, ctx)
                updater.prepare(info, root, ctx)
                return True
            finally:
                updater.close()

        task = Task(guarded(work), "Güncelleme indiriliyor")
        task.progress.connect(self._on_progress)
        task.succeeded.connect(self._downloaded)
        task.failed.connect(self._download_failed)
        task.cancelled.connect(self._badge_idle)
        task.finished.connect(self._download_finished)
        self.download_task = task
        self._badge(f"İndiriliyor · {info.version}", "Yeni sürüm iniyor; bitince uygulama yeniden açılır.")
        task.start()

    def _on_progress(self, done: int, total: int, message: str) -> None:
        if total > 0:
            self._win.update_badge.setText(f"%{done * 100 // total} · {_mb(done)} / {_mb(total)} MB")
        elif message:
            self._win.update_badge.setText(message)

    def _downloaded(self, result: object) -> None:
        if isinstance(result, Problem):
            self._badge_idle()
            if result.kind == "key":
                self._win.open_updates()  # özel depo: anahtar adımları pencerede
                return
            self._win.notifier.notify(
                LEVEL_ERROR,
                "Güncelleme kurulamadı",
                result.text,
                (NoticeAction("Sürümler Sayfası", lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL))),),
                loud=True,
            )
            return
        self._ready = result if isinstance(result, PreparedInstall) else True
        self._finish()

    def _download_failed(self, text: str) -> None:
        self._badge_idle()
        self._win.notifier.notify(
            LEVEL_ERROR, "Güncelleme indirilemedi", text, (NoticeAction("Tekrar Dene", self._win.start_update),)
        )

    def _download_finished(self) -> None:
        if self.download_task is not None:
            self.download_task.deleteLater()
        self.download_task = None

    def _finish(self) -> None:
        """İnen sürümü kurar: uygulama kapanır ve yeni sürümle açılır. Süren iş varsa düğme bekler."""
        win = self._win
        info, ready = self.info, self._ready
        root, _packaged = self._target()
        if info is None or ready is None or root is None:
            return
        restart = f"Yeniden başlat · {info.version}"
        if win.busy:
            self._badge(restart, "Süren iş bitince basın; uygulama yeni sürümle açılır.")
            win.notify(LEVEL_INFO, "Güncelleme hazır", "Süren iş bitince “Yeniden başlat”a basın.")
            return
        if not win._confirm_discard():  # yalnızca kaydedilmemiş yeni projede sorulur
            self._badge(restart, "Uygulama yeni sürümle açılır.")
            return
        win.settings.setValue(INSTALLING_KEY, info.version)
        try:
            if isinstance(ready, PreparedInstall):
                win.installer_launcher(ready, root)
            else:
                win.relauncher(root)
        except UpdateError as exc:
            win.settings.remove(INSTALLING_KEY)
            if isinstance(ready, PreparedInstall):
                discard_prepared(ready)
            self._ready = None
            self._badge_idle()
            win.notify(LEVEL_ERROR, "Güncelleme", exc.user_text())
            return
        win.update_badge.hide()
        win.dirty = False  # kullanıcı az önce kaydetti veya değişiklikleri atmayı seçti
        win.close()

    def announce_installed(self) -> None:
        """Açılışta: son güncellemeyle bu sürüm kurulduysa kısa bir onay ve Yenilikler bağlantısı gösterir."""
        settings = self._win.settings
        target = str(settings.value(INSTALLING_KEY, "") or "")
        if not target:
            return
        settings.remove(INSTALLING_KEY)
        if target != __version__:
            return  # kurulamadı; nedeni ayrıca bildirilir (`notify_update_failure`)
        url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/tag/v{target}"
        self._win.notifier.notify(
            LEVEL_SUCCESS,
            f"{target} kuruldu",
            "",
            (NoticeAction("Yenilikler", lambda: QDesktopServices.openUrl(QUrl(url))),),
        )

    # --- pencere ---------------------------------------------------------------------------

    def open_updates(self) -> None:
        """Yardım → Güncellemeleri Denetle: denetim penceresi; Güncelle denirse durum çubuğundaki akış başlar."""
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
            updater_factory=win.updater_factory,
            git_mode=not packaged and is_git_checkout(root),
        )
        if dialog.exec() != _mw.UpdateDialog.DialogCode.Accepted or dialog.info is None or not dialog.info.newer:
            return
        self.info = dialog.info
        win.start_update()

    # --- açılış ----------------------------------------------------------------------------

    def check_updates_in_background(self) -> None:
        """Açılışta (ayar açıksa) yeni sürüm olup olmadığına sessizce bakar; varsa durum çubuğunda düğme çıkar."""
        win = self._win
        root = win.app_root
        if (root is None and not win.packaged) or win._update_task is not None or not auto_check_enabled(win.settings):
            return
        token = self._token()
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
        if not result.newer or self._ready is not None or self.download_task is not None:
            return
        self.info = result
        root, _packaged = self._target()
        if root is None:  # git deposu: güncelleme “git pull” ile yapılır, düğme pencereyi açar
            self._badge(f"Yeni sürüm · {result.version}", "Güncellemek için uygulama klasöründe “git pull”.")
        else:
            self._badge_idle()
        self._win.notifier.notify(
            LEVEL_INFO,
            f"Yeni sürüm: {result.version}",
            "",
            (NoticeAction("Güncelle", self._win.start_update), NoticeAction("Sonra", lambda: None)),
            loud=True,
        )
