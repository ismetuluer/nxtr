"""Uygulama giriş noktası: günlük (log) kurulumu, tema ve ana pencere."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QSettings, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from nxceviri import __version__
from nxceviri.core.formats.registry import load_user_plugins
from nxceviri.core.selfupdate import take_install_failure
from nxceviri.core.update import UpdateError, app_root, apply_staged, relaunch
from nxceviri.gui.main_window import APP_TITLE, MainWindow, log_dir
from nxceviri.gui.theme import DEFAULT_FONT_SIZE, ThemeMode, apply_theme

#: Uygulama simgesi (kaynak: `nxtr.svg`; .ico/.png `packaging/make_icon.py` ile üretilir).
APP_ICON_DIR = Path(__file__).parent / "appicon"


def app_icon() -> QIcon:
    """Pencere ve görev çubuğu simgesi; .exe'nin kendi simgesi PyInstaller tarifinde ayrıca verilir."""
    return QIcon(str(APP_ICON_DIR / "nxtr.ico"))


def setup_logging() -> Path:
    folder = log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "nxceviri.log"
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return path


def install_qt_translations(app: QApplication) -> QTranslator | None:
    """Qt'nin kendi metinlerini (Kes/Kopyala/Yapıştır, Evet/Hayır, dosya penceresi) Türkçeleştirir.

    PySide6 ile gelen `qtbase_tr.qm` yüklenir. Dosya bulunamazsa arayüz çalışır, yalnızca bu
    standart metinler İngilizce kalır; bu durum günlüğe yazılır.
    """
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    translator = QTranslator(app)
    if translator.load("qtbase_tr", folder):
        app.installTranslator(translator)
        return translator
    logging.getLogger(__name__).warning("Qt Türkçe çeviri dosyası bulunamadı: %s", folder)
    return None


def apply_pending_update() -> tuple[bool, str]:
    """Hazırlanmış güncelleme varsa, hiçbir yazı tipi veya proje açılmadan önce uygular.

    (yeniden başlatılmalı mı, kullanıcıya gösterilecek hata) döndürür.
    """
    root = app_root()
    if root is None:
        return False, ""
    try:
        result = apply_staged(root)
    except UpdateError as exc:
        return False, exc.user_text()
    if result is None:
        return False, ""
    relaunch(root)  # yeni kod (ve gerekiyorsa yeni paketler) yeni süreçte yüklenir
    return True, ""


def main(argv: list[str] | None = None) -> int:
    args = sys.argv if argv is None else argv
    setup_logging()
    logging.getLogger(__name__).info("%s %s başlatıldı", APP_TITLE, __version__)
    restart, update_error = apply_pending_update()
    if restart:
        return 0
    app = QApplication(args)
    app.setApplicationName("NXCeviri")
    app.setOrganizationName("NXCeviri")
    app.setApplicationDisplayName(APP_TITLE)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    install_qt_translations(app)
    load_user_plugins()  # hatalı eklenti uygulamayı durdurmaz; nedeni Yardım → Eklentiler'de görünür
    settings = QSettings()
    try:
        mode = ThemeMode(str(settings.value("ui/theme", ThemeMode.SYSTEM.value)))
    except ValueError:
        mode = ThemeMode.SYSTEM
    try:
        font_size = int(str(settings.value("ui/font_size", DEFAULT_FONT_SIZE)))
    except ValueError:
        font_size = DEFAULT_FONT_SIZE
    apply_theme(app, mode, font_size)
    window = MainWindow(settings)
    project_args = [Path(a) for a in args[1:] if a.lower().endswith(".nxproj")]
    window.show()
    if update_error:
        window.notify_update_failure(update_error)
    install_failure = take_install_failure()
    if install_failure:
        window.notify_update_failure(f"Eski sürümle açıldı; projeleriniz etkilenmedi. Neden: {install_failure}")
    if project_args:
        window.open_project(project_args[0])
    else:
        window.offer_recovery()
    window.check_updates_in_background()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
