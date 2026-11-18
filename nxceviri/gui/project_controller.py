"""Proje yaşam döngüsü denetleyicisi: yeni, aç, kaydet, farklı kaydet, son projeler, kurtarma kopyası.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Denetleyici durum tutmaz; proje, kaynaklar,
`dirty`, `recent`, `recovery` ve `_recovery_due` pencerede durur ve her çağrıda pencereden okunur. Pencerede
yönlendirmesi olan bir yöntem pencere üzerinden çağrılır (`self._win.<ad>`): testler `ask_save_changes`,
`ask_recovery`, `save_project` gibi yöntemleri pencerede değiştirir. Kaydetme sorusunun kutusu
(`main_window.build_save_box`) ve pencere kapanışı (`closeEvent`) pencerede kalır.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QMessageBox

from nxceviri.core.errors import NxError
from nxceviri.core.plugins.record import plugin_warnings
from nxceviri.core.project import PROJECT_SUFFIX, Project
from nxceviri.gui.notify import LEVEL_ERROR
from nxceviri.gui.recovery import RecoveryFile, discard, leftover_files
from nxceviri.gui.step_nav import STEP_ADD

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow


class ProjectController:
    """Projeyi açma, kaydetme ve kurtarma iş akışı; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win

    def confirm_discard(self, closing: bool = False) -> bool:
        """Kaydedilmemiş değişiklik varsa kullanıcıya sorar. Devam edilebilirse True."""
        if not self._win.dirty:
            return True
        answer = self._win.ask_save_changes(closing)
        if answer == "save":
            return self._win.save_project()
        return answer == "discard"

    def new_project(self) -> None:
        if self._win.busy or not self._win._confirm_discard():
            return
        self._win._replace_project(Project.new())

    def replace_project(self, project: Project) -> bool:
        """Açık projeyi `project` ile değiştirir. Panel metni kaydedilemezse eski proje kalır, False döner."""
        win = self._win
        # Panelde bekleyen metin, satır kimlikleri başka projeye karışmasın diye eski projeye yazılır.
        if not win.translate_page.flush_pending():
            project.close()  # kullanılmayacak yeni proje dosyayı kilitli bırakmasın
            return False
        win.project.close()
        win.recovery.clear()  # önceki proje kaydedildi ya da kullanıcı ondan vazgeçti
        win._recovery_due = False
        win.project = project
        win.sources = project.sources()
        win.report = project.latest_scan()
        win.translate_page.set_uppercase(project.uppercase_rules())
        win._last_job = None
        win.translate_page.set_last_changes({})
        win._refresh_marks()
        win._push_fit_to_page()
        win.translate_page.set_qa_issues([], [])  # önceki projenin denetim sonuçları taşınmaz
        win._fit_recheck_timer.stop()  # bekleyen ayar yenilemesi eski projeye aitti
        win.qa_page.reset()
        win.graphics_check.project_replaced()  # süren grafik denetimi durur; klasör yeni projeden bulunur
        win._qa_count = None
        win._qa_errors = False
        win.translate_page.set_project_key(
            str(project.path) if project.path else None
        )  # süzgeçler projeye göre hatırlanır
        win.translate_page.set_rows(project.translation_rows())
        win._sync_ignored_to_translate()
        win._sync_spell()
        win.font_report = None
        win._sync_live()  # font raporu sıfırlandı: eksik harf bağlamı projenin kayıtlı değerinden gelir
        win.last_export = None
        win.dirty = False
        win.add_page.set_files_message("warning", "")
        win.nav.setCurrentRow(STEP_ADD)
        win._refresh()
        return True

    def open_project_dialog(self) -> None:
        win = self._win
        if win.busy or not win._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            win,
            "Proje aç",
            str(win.settings.value("ui/project_dir", str(Path.home()))),
            f"NXTR projesi (*{PROJECT_SUFFIX})",
        )
        if path:
            win.open_project(Path(path))

    def open_project(self, path: Path) -> bool:
        win = self._win
        try:
            project = Project.open(path)
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje açılamadı", exc.user_text())
            return False
        if not win._replace_project(project):
            return False
        win.settings.setValue("ui/project_dir", str(path.parent))
        win.recent.remember(path)
        missing = [s.path.name for s in win.sources if not s.path.is_file()]
        notes = []
        if missing:
            notes.append(
                "Projedeki bazı oyun dosyaları bulunamadı: "
                + ", ".join(missing)
                + ". Dosyaları taşıdıysanız listeden kaldırıp yeniden ekleyin."
            )
        notes += plugin_warnings(win.project)
        if notes:
            win.add_page.set_files_message("warning", " ".join(notes))
        win.statusBar().showMessage(f"Proje açıldı: {path.name}", 5000)
        return True

    def save_project(self) -> bool:
        win = self._win
        if win.project.path is None:
            return win.save_project_as()
        win.statusBar().showMessage("Tüm değişiklikler proje dosyasına kaydedildi.", 4000)
        return True

    def save_project_as(self) -> bool:
        win = self._win
        if win.busy:
            return False
        suggested = win.report.game_name if win.report and win.report.game_name else "Yeni Çeviri Projesi"
        start = Path(str(win.settings.value("ui/project_dir", str(Path.home())))) / f"{suggested}{PROJECT_SUFFIX}"
        path, _ = QFileDialog.getSaveFileName(win, "Projeyi kaydet", str(start), f"NXTR projesi (*{PROJECT_SUFFIX})")
        if not path:
            return False
        return win.save_to(Path(path))

    def save_to(self, path: Path) -> bool:
        win = self._win
        try:
            win.project.save_as(path)
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje kaydedilemedi", exc.user_text())
            return False
        assert win.project.path is not None
        win.settings.setValue("ui/project_dir", str(win.project.path.parent))
        win.recent.remember(win.project.path)
        win.recovery.clear()
        win._recovery_due = False
        win.dirty = False
        win._refresh()
        win.statusBar().showMessage(f"Proje kaydedildi: {win.project.path}", 5000)
        return True

    # --- kurtarma ve son projeler ----------------------------------------------------------

    def write_recovery(self) -> None:
        """Kaydedilmemiş projede değişiklik varsa kurtarma kopyasını yeniler (arayüz iş parçacığında, hızlı)."""
        win = self._win
        if win.project.path is not None or not win.dirty or not win._recovery_due:
            return
        if win.recovery.write(win.project):
            win._recovery_due = False

    def offer_recovery(self) -> bool:
        """Önceki oturumdan kalmış kurtarma kopyası varsa kurtarılmasını önerir. Proje kurtarıldıysa True."""
        win = self._win
        files = leftover_files(win.recovery.folder)
        if not files:
            return False
        choice = win.ask_recovery(files[0], len(files))
        if choice == "recover":
            return win.recover_from(files[0])
        if choice == "discard":
            discard(files[0].path)
        return False

    def ask_recovery(self, newest: RecoveryFile, count: int) -> str:
        """ "recover", "discard" ya da "later"."""
        box = QMessageBox(self._win)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Kaydedilmemiş proje bulundu")
        more = f"\n\n(Toplam {count} kurtarma kopyası var; en yenisi önerildi.)" if count > 1 else ""
        box.setText(
            "Program önceki sefer kaydedilmeden kapanmış. Kaydedilmemiş projenin son kopyası duruyor:\n\n"
            f"{newest.describe()}{more}\n\nKurtarmak ister misiniz? Kurtardıktan sonra “Kaydet” ile bir proje "
            "dosyasına kaydedin."
        )
        recover = box.addButton("Kurtar", QMessageBox.ButtonRole.AcceptRole)
        delete = box.addButton("Sil", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Sonra", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(recover)
        box.exec()
        clicked = box.clickedButton()
        return "recover" if clicked is recover else "discard" if clicked is delete else "later"

    def recover_from(self, leftover: RecoveryFile) -> bool:
        win = self._win
        try:
            project = Project.open_copy(leftover.path)
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje kurtarılamadı", exc.user_text())
            return False
        if not win._replace_project(project):
            return False
        win.dirty = True
        win._recovery_due = True
        win.write_recovery()  # kopya artık bu pencerenin; eskisi silinebilir
        if not win._recovery_due:  # yazım başarısızsa eski kopya kalır, zamanlayıcı yeniden dener
            discard(leftover.path)
        win._refresh()
        win.statusBar().showMessage("Proje kurtarıldı. Kaydetmeyi unutmayın.", 8000)
        return True

    def fill_recent_menu(self) -> None:
        self._win.recent.fill_menu(self._win.recent_menu, self._win.open_recent)

    def open_recent(self, path: Path) -> None:
        win = self._win
        if win.busy or not win._confirm_discard():
            return
        win.open_project(path)
