"""Yardım → Güncellemeleri Denetle: sürüm denetimi, değişiklik notu, indirme ve hazırlama.

Denetim önce anahtarsız yapılır. GitHub erişim anahtarı adımları yalnızca depo anahtarsız
okunamadığında (özel depo) görünür; açık depoda hiç çıkmaz.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QProgressBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.errors import NxError
from nxceviri.core.progress import TaskContext
from nxceviri.core.secrets import GITHUB_UPDATE_KEY, SecretStore
from nxceviri.core.selfupdate import PreparedInstall, prepare_package
from nxceviri.core.update import (
    ACCESS_KEY_HELP_URL,
    RELEASES_URL,
    REPO_NAME,
    REPO_OWNER,
    AccessError,
    GitHubUpdater,
    ManualInstallError,
    UpdateError,
    UpdateInfo,
    Updater,
)
from nxceviri.gui.tasks import Task
from nxceviri.gui.widgets import Banner, button, label, title_row

#: QSettings anahtarı: açılışta güncelleme denetlensin mi?
AUTO_CHECK_KEY = "update/auto_check"

#: Kayıtlı erişim anahtarı (yoksa None) → güncelleyici.
UpdaterFactory = Callable[[str | None], Updater]

_KEY_STEPS = (
    "Depoya anahtarsız erişilemedi (depo özel olabilir). Bir kez erişim anahtarı gerekir:\n"
    "1. “GitHub'da Anahtar Oluştur” düğmesine tıklayın.\n"
    f"2. Repository access: Only select repositories → {REPO_NAME}; Contents: Read-only.\n"
    "3. “Generate token” deyin, anahtarı aşağıya yapıştırıp Kaydet'e basın. Anahtar Windows Kimlik Bilgisi "
    "Yöneticisi'nde saklanır."
)


def auto_check_enabled(settings: QSettings) -> bool:
    return str(settings.value(AUTO_CHECK_KEY, "true")).lower() == "true"


@dataclass(frozen=True)
class _Problem:
    """Arayüzün özel karşılık verdiği hata: "key" (anahtar gerekir) veya "manual" (elle indirin)."""

    kind: str
    text: str


def _guarded(fn: Callable[[TaskContext], object]) -> Callable[[TaskContext], object]:
    def run(ctx: TaskContext) -> object:
        try:
            return fn(ctx)
        except AccessError as exc:
            return _Problem("key", exc.user_text())
        except ManualInstallError as exc:
            return _Problem("manual", exc.user_text())

    return run


class UpdateDialog(QDialog):
    """Sürüm denetimi ve indirme. İndirilen sürüm hazırlanınca pencere `Accepted` ile kapanır."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        secrets: SecretStore,
        settings: QSettings,
        current: str,
        root: Path,
        updater_factory: UpdaterFactory,
        git_mode: bool = False,
        packaged: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Güncellemeler")
        self.setMinimumWidth(620)
        self._secrets = secrets
        self._settings = settings
        self._current = current
        self._root = root
        self._factory = updater_factory
        self._task: Task | None = None
        self._git_mode = git_mode
        self._packaged = packaged
        self.info: UpdateInfo | None = None
        #: Paketlenmiş sürümde indirilip doğrulanmış, yerine konmayı bekleyen yeni sürüm.
        self.prepared: PreparedInstall | None = None

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(
            title_row(
                "Uygulama güncellemesi",
                f"Yeni sürümler GitHub'daki {REPO_OWNER}/{REPO_NAME} deposunun yayımlanan sürümlerinden alınır. "
                "Projeleriniz, oyun dosyalarınız, eklentileriniz ve ayarlarınız olduğu gibi kalır.",
                "cardTitle",
            )
        )
        lay.addWidget(label(f"Kurulu sürüm: {current}"))
        if git_mode:
            lay.addWidget(
                label(
                    "Bu klasör bir git deposu: yeni sürüm denetlenir, güncellemek için “git pull” çalıştırılır.",
                    "muted",
                    wrap=True,
                )
            )

        self.key_box = QWidget()
        kl = QVBoxLayout(self.key_box)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.addWidget(label("GitHub erişim anahtarı", "cardTitle"))
        self.key_state = label("")
        kl.addWidget(self.key_state)
        kl.addWidget(label(_KEY_STEPS, "muted", wrap=True))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("github_pat_… anahtarını buraya yapıştırın")
        kl.addWidget(self.key)
        key_row = QHBoxLayout()
        create = button("GitHub'da Anahtar Oluştur")
        create.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ACCESS_KEY_HELP_URL)))
        self.save_key = button("Anahtarı Kaydet")
        self.save_key.clicked.connect(self._save_key)
        self.delete_key = button("Kayıtlı Anahtarı Sil")
        self.delete_key.clicked.connect(self._delete_key)
        key_row.addWidget(create)
        key_row.addWidget(self.save_key)
        key_row.addWidget(self.delete_key)
        key_row.addStretch(1)
        kl.addLayout(key_row)
        lay.addWidget(self.key_box)
        self.key_box.hide()  # yalnızca anahtarsız erişim başarısız olunca görünür

        self.auto = QCheckBox("Uygulama açılırken yeni sürüm olup olmadığını denetle")
        self.auto.setChecked(auto_check_enabled(settings))
        self.auto.toggled.connect(lambda on: settings.setValue(AUTO_CHECK_KEY, "true" if on else "false"))
        lay.addWidget(self.auto)

        self.status = Banner()
        lay.addWidget(self.status)
        self.notes = QTextBrowser()  # sürüm açıklaması (markdown); bağlantılar açılmaz
        self.notes.setOpenLinks(False)
        self.notes.setMinimumHeight(160)
        self.notes.hide()
        lay.addWidget(self.notes)
        progress = QHBoxLayout()
        self.progress_label = label("", "muted")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        progress.addWidget(self.progress_label, 1)
        progress.addWidget(self.progress, 1)
        self.progress_box = QWidget()
        self.progress_box.setLayout(progress)
        self.progress_box.hide()
        lay.addWidget(self.progress_box)

        buttons = QHBoxLayout()
        self.check = button("Güncellemeleri Denetle", "primary")
        self.check.clicked.connect(self.check_now)
        self.install = button("Güncelle ve Yeniden Başlat" if git_mode else "İndir ve Yeniden Başlat", "primary")
        self.install.clicked.connect(self.download)
        self.install.hide()
        self.manual = button("Sürümler Sayfasını Aç")
        self.manual.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)))
        self.manual.hide()
        self.close_button = button("Kapat")
        self.close_button.clicked.connect(self._close_or_cancel)
        buttons.addStretch(1)
        buttons.addWidget(self.check)
        buttons.addWidget(self.install)
        buttons.addWidget(self.manual)
        buttons.addWidget(self.close_button)
        lay.addLayout(buttons)

    # --- anahtar -------------------------------------------------------------------------

    def _stored_key(self) -> str | None:
        try:
            return self._secrets.get(GITHUB_UPDATE_KEY)
        except NxError as exc:
            self.status.show_message("danger", exc.user_text())
            return None

    def _refresh_key_state(self) -> None:
        stored = bool(self._stored_key())
        self.key_state.setText("Kayıtlı anahtar: var" if stored else "Kayıtlı anahtar: yok")
        self.delete_key.setEnabled(stored)

    def _save_key(self) -> None:
        value = self.key.text().strip()
        if not value:
            self.status.show_message("warning", "Önce anahtarı alana yapıştırın.")
            return
        try:
            self._secrets.set(GITHUB_UPDATE_KEY, value)
        except NxError as exc:
            self.status.show_message("danger", exc.user_text())
            return
        self.key.clear()
        self._refresh_key_state()
        self.check_now()

    def _delete_key(self) -> None:
        try:
            self._secrets.delete(GITHUB_UPDATE_KEY)
        except NxError as exc:
            self.status.show_message("danger", exc.user_text())
            return
        self._refresh_key_state()
        self.status.show_message("success", "Kayıtlı GitHub anahtarı silindi.")

    # --- denetim ve indirme --------------------------------------------------------------

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.check.setEnabled(not busy)
        self.install.setEnabled(not busy)
        self.save_key.setEnabled(not busy)
        self.progress_box.setVisible(busy)
        self.progress.setRange(0, 0)
        self.progress_label.setText(text)
        self.close_button.setText("İptal" if busy else "Kapat")

    def _start(
        self, fn: Callable[[TaskContext], object], description: str, on_success: Callable[[object], None]
    ) -> None:
        task = Task(_guarded(fn), description)
        self._task = task
        task.progress.connect(self._on_progress)
        task.succeeded.connect(lambda result: self._succeeded(result, on_success))
        task.failed.connect(lambda text: self.status.show_message("danger", text))
        task.cancelled.connect(lambda: self.status.show_message("warning", "Güncelleme durduruldu."))
        task.finished.connect(self._finished)
        self._set_busy(True, description + "…")
        self.status.show_message("success", "")
        task.start()

    def _succeeded(self, result: object, on_success: Callable[[object], None]) -> None:
        if isinstance(result, _Problem):
            self.status.show_message("danger", result.text)
            if result.kind == "key" and not self._git_mode:
                self.key_box.show()
                self._refresh_key_state()
            else:
                self.manual.show()
            return
        on_success(result)

    def _on_progress(self, done: int, total: int, message: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        self.progress_label.setText(message)

    def _finished(self) -> None:
        if self._task is not None:
            self._task.deleteLater()
        self._task = None
        self._set_busy(False)
        self.install.setEnabled(self.info is not None and self.info.newer)

    def check_now(self) -> None:
        if self._task is not None:
            return
        token = self._stored_key()

        def work(_ctx: TaskContext) -> object:
            updater = self._factory(token)
            try:
                return updater.check(self._current)
            finally:
                updater.close()

        self._start(work, "Denetleniyor", self._checked)

    def _checked(self, result: object) -> None:
        assert isinstance(result, UpdateInfo)
        self.info = result
        self.key_box.hide()  # erişim sağlandı
        self.manual.hide()
        if not result.newer:
            self.status.show_message("success", f"Uygulama güncel (en son sürüm {result.version}).")
            self.notes.hide()
            self.install.hide()
            return
        self.notes.setMarkdown(result.notes or "Değişiklik notu bulunamadı.")
        self.notes.show()
        if self._git_mode:
            self.status.show_message(
                "warning",
                f"Yeni sürüm var: {result.version} (kurulu: {result.current}). "
                "Güncellemek için uygulama klasöründe “git pull” çalıştırın.",
            )
            return
        self.status.show_message("warning", f"Yeni sürüm var: {result.version} (kurulu: {result.current}).")
        self.install.show()

    def download(self) -> None:
        info = self.info
        if self._task is not None or info is None or not info.newer:
            return
        token = self._stored_key()
        root = self._root

        packaged = self._packaged

        def work(ctx: TaskContext) -> object:
            updater = self._factory(token)
            try:
                if not isinstance(updater, GitHubUpdater):
                    raise UpdateError("Bu kurulumda otomatik güncelleme yapılamıyor.")
                if packaged:
                    return prepare_package(updater, info, root, ctx)
                updater.prepare(info, root, ctx)
                return None
            finally:
                updater.close()

        self._start(work, "Hazırlanıyor", self._staged)

    def _staged(self, result: object) -> None:
        if isinstance(result, PreparedInstall):
            self.prepared = result
        self.accept()

    def _close_or_cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()
            return
        self.reject()

    def reject(self) -> None:
        if self._task is not None:  # iş sürerken pencere kapanmaz; önce iptal edilir
            self._task.cancel()
            return
        super().reject()
