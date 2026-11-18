"""Tarama denetleyicisi: anahtar dosyaları, oyun dosyalarını ekleme/kaldırma, tarama, dosya çıkarma, teşhis raporu ve
metinleri projeye aktarma.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Denetleyici durum tutmaz; anahtarlar (`keys`,
`title_keys`, `title_keys_path`, `_keys_detail`), kaynaklar (`sources`), tarama raporu (`report`), aktarma dili
(`_import_language`) ve onaylanan silmeler (`_confirmed_removals`) her çağrıda pencereden okunur; testler bunları
pencerede değiştirir. Pencerede yönlendirmesi olan her yöntem (`_inputs`, `_run`, `notify`, `ask_remove_files`,
ayrıca bu dosyadaki yöntemlerin kendileri) pencere üzerinden çağrılır. Testlerin `nxceviri.gui.main_window` üzerinde
değiştirdiği `check_sources` ve `extract_texts` adları çağrı anında `_mw.<ad>` ile okunur. `_cache_dir` ve `_inputs`
font, görsel ve dışa aktarma yollarınca da kullanıldığından, `_show_scan_report` gezinti ile birlikte pencerede kalır.
Anahtar dosyasının içeriği hiçbir yerde gösterilmez ya da yazılmaz; yalnızca yolu ve kayıt sayısı gösterilir.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox

from nxceviri.arac.teshis import RAPOR_ADI, UYARI, rapor_uret
from nxceviri.core.errors import NxError
from nxceviri.core.formats.scanner import ScanReport
from nxceviri.core.keys import load_keys, load_title_keys
from nxceviri.core.pipeline import (
    TextExtraction,
    extract_sources,
    is_supported_file,
    read_source,
    scan_sources,
)
from nxceviri.core.plugins.record import record_extraction
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import SourceRecord
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_INFO
from nxceviri.gui.step_nav import STEP_SCAN, STEP_TRANSLATE
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow


class ScanController:
    """Anahtarlar, kaynak dosyalar, tarama ve metin aktarma; pencere buna ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win

    # --- anahtarlar ----------------------------------------------------------------------

    def _restore_keys(self) -> None:
        win = self._win
        saved = win.settings.value("keys/prod", "")
        if saved:
            win.load_keys_file(Path(str(saved)), remember=False)
        else:
            win.add_page.set_keys_state("neutral", None)
            win._show_keys_status()
        saved_title = win.settings.value("keys/title", "")
        if saved_title:
            win.load_title_keys_file(Path(str(saved_title)), remember=False)

    def _choose_keys(self) -> None:
        win = self._win
        start = str(win.keys.source_path.parent) if win.keys and win.keys.source_path else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            win, "prod.keys dosyasını seçin", start, "Anahtar dosyası (*.keys *.txt);;Tüm dosyalar (*)"
        )
        if path:
            win.load_keys_file(Path(path))

    def load_keys_file(self, path: Path, remember: bool = True) -> bool:
        win = self._win
        try:
            keys = load_keys(path)
        except NxError as exc:
            win.keys = None
            win.add_page.set_keys_state("danger", path, exc.user_text())
            win._show_keys_status(path)
            win._refresh()
            return False
        win.keys = keys
        summary = keys.summary()
        newest = summary.newest_generation
        win.add_page.set_keys_state("success", path)
        win._keys_detail = f"{len(keys)} anahtar, nesiller 0–{max(summary.key_area_generations)}."
        if newest < 0:
            win._keys_detail += "\nUyarı: anahtar alanı ve titlekek nesilleri eşleşmiyor; bazı oyunlar açılamayabilir."
        win._show_keys_status(path)
        if remember:
            win.settings.setValue("keys/prod", str(path))
        win._refresh()
        return True

    def _choose_title_keys(self) -> None:
        win = self._win
        path, _ = QFileDialog.getOpenFileName(
            win, "title.keys dosyasını seçin", str(Path.home()), "Anahtar dosyası (*.keys *.txt);;Tüm dosyalar (*)"
        )
        if path:
            win.load_title_keys_file(Path(path))

    def load_title_keys_file(self, path: Path, remember: bool = True) -> bool:
        win = self._win
        try:
            win.title_keys = load_title_keys(path)
        except NxError as exc:
            win.title_keys = None
            win.title_keys_path = None
            win.add_page.set_files_message("danger", exc.user_text())
            win._show_keys_status(win._keys_path())
            return False
        win.title_keys_path = path
        win._show_keys_status(win._keys_path())
        if remember:
            win.settings.setValue("keys/title", str(path))
        return True

    def _clear_title_keys(self) -> None:
        win = self._win
        win.title_keys = None
        win.title_keys_path = None
        win.settings.remove("keys/title")
        win._show_keys_status(win._keys_path())

    def _keys_path(self) -> Path | None:
        win = self._win
        return win.keys.source_path if win.keys is not None else None

    def _show_keys_status(self, path: Path | None = None) -> None:
        """Durum çubuğundaki anahtar bölmesi ve menüdeki title.keys eylemi (anahtar değerleri gösterilmez)."""
        win = self._win
        if win.keys is not None:
            state, text, lines = "success", "Anahtarlar doğrulandı", [f"prod.keys: {path}", win._keys_detail]
        elif path is not None:
            state, text, lines = "danger", "Anahtar geçersiz", [f"prod.keys okunamadı: {path}"]
        else:
            state, text, lines = "neutral", "Anahtar seçilmedi", ["prod.keys seçmek için tıklayın."]
        if win.title_keys_path is not None and win.title_keys is not None:
            lines.append(f"title.keys: {win.title_keys_path} ({len(win.title_keys)} kayıt)")
        else:
            lines.append("title.keys: seçilmedi (isteğe bağlı; oyun dosyasında bilet yoksa gerekir)")
        lines.append("Değiştirmek için: Dosya → Anahtarlar")
        win.status_segments.set_keys(state, text, "\n".join(lines))
        win.title_keys_clear_action.setEnabled(win.title_keys_path is not None)

    # --- kaynak dosyalar -------------------------------------------------------------------

    def _browse_files(self) -> None:
        win = self._win
        paths, _ = QFileDialog.getOpenFileNames(
            win,
            "Oyun dosyalarını seçin",
            str(win.settings.value("ui/last_dir", str(Path.home()))),
            "Switch oyun dosyaları (*.nsp *.nsz)",
        )
        if paths:
            win.settings.setValue("ui/last_dir", str(Path(paths[0]).parent))
            win.add_files([Path(p) for p in paths])

    def add_files(self, paths: list[Path]) -> None:
        win = self._win
        if win.busy or win.keys is None:
            return
        known = {s.path.resolve() for s in win.sources}
        new = [p for p in paths if is_supported_file(p) and p.resolve() not in known]
        skipped = [p.name for p in paths if not is_supported_file(p)]
        if not new:
            msg = "Bu dosyalar zaten eklenmiş." if not skipped else "Yalnızca .nsp ve .nsz dosyaları eklenebilir."
            win.add_page.set_files_message("warning", msg)
            return
        keys = win.keys
        title_keys = win.title_keys

        def work(ctx: TaskContext) -> object:
            records: list[SourceRecord] = []
            errors: list[str] = []
            for i, p in enumerate(new):
                ctx.report(i, len(new), f"Okunuyor: {p.name}")
                try:
                    records.append(read_source(p, keys, title_keys))
                except NxError as exc:
                    errors.append(f"{p.name}: {exc.user_text()}")
            return records, errors

        win.add_page.set_busy(True, f"{len(new)} dosya okunuyor…")
        win._run(
            work,
            "Oyun dosyaları okunuyor",
            on_success=lambda r: win._files_added(r, skipped),
            on_failure=win._files_failed,
        )

    def _files_added(self, result: object, skipped: list[str]) -> None:
        win = self._win
        assert isinstance(result, tuple)
        records, errors = result
        win.sources = sorted(
            [*win.sources, *records], key=lambda s: ({"base": 0, "update": 1}.get(s.kind, 2), s.title_id, s.version)
        )
        win._sources_changed()
        messages = list(errors)
        if skipped:
            messages.append("Desteklenmeyen dosyalar atlandı: " + ", ".join(skipped))
        if messages:
            win.add_page.set_files_message("danger" if errors else "warning", "\n\n".join(messages))
        if records:
            win.statusBar().showMessage(f"{len(records)} dosya eklendi.", 5000)

    def _files_failed(self, text: str) -> None:
        self._win.add_page.set_files_message("danger", text)

    def _remove_source(self, row: int) -> None:
        win = self._win
        if win.busy or not 0 <= row < len(win.sources):
            return
        del win.sources[row]
        win._sources_changed()

    def _sources_changed(self) -> None:
        win = self._win
        try:
            win.project.set_sources(win.sources)
            if win.report is not None:
                win.project.clear_scan()
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje", exc.user_text())
        win.report = None
        win._mark_changed()

    # --- tarama ----------------------------------------------------------------------------

    def _go_scan(self) -> None:
        """“Metinleri Tara”: güncel rapor varsa onu gösterir, yoksa taramayı hemen başlatır."""
        win = self._win
        if win.report is None:
            win.start_scan()
        else:
            win.nav.setCurrentRow(STEP_SCAN)

    def start_scan(self) -> None:
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        if win.busy:
            return
        problems = _mw.check_sources(win.sources)
        if win.keys is None or problems:
            win.scan_page.show_error(" ".join(problems) or "Önce geçerli bir anahtar dosyası seçin.")
            return
        inputs = win._inputs()
        win.nav.setCurrentRow(STEP_SCAN)
        win.scan_page.show_loading("Oyun dosyaları taranıyor")
        win._run(
            lambda ctx: scan_sources(inputs, ctx),
            "Tarama",
            on_success=win._scan_done,
            on_failure=win.scan_page.show_error,
            on_progress=win.scan_page.loading.update_progress,
            on_cancel=win._scan_cancelled,
        )

    def _scan_done(self, result: object) -> None:
        win = self._win
        assert isinstance(result, ScanReport)
        win.report = result
        try:
            win.project.set_game(result.game_name, result.title_id)
            win.project.save_scan(result)
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje", exc.user_text())
        win._mark_changed()
        win._show_scan_report(result)
        win.statusBar().showMessage(f"Tarama {result.duration_s:.1f} saniyede tamamlandı.", 8000)

    def _scan_cancelled(self) -> None:
        win = self._win
        if win.report is not None:
            win._show_scan_report(win.report)
        else:
            win.scan_page.show_empty()
        win.statusBar().showMessage("Tarama iptal edildi.", 5000)

    def _extract(self, mode: str) -> None:
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        if win.busy or win.report is None or win.keys is None:
            return
        problems = _mw.check_sources(win.sources)
        if problems:
            win.notify(LEVEL_ERROR, "Dosyalar çıkarılamıyor", " ".join(problems))
            return
        folder = QFileDialog.getExistingDirectory(win, "Dosyaların çıkarılacağı boş klasörü seçin", str(Path.home()))
        if not folder:
            return
        dest = Path(folder)
        only = {e.path for e in win.report.text_candidates} if mode == "candidates" else None
        inputs = win._inputs()
        report = win.report
        win.scan_page.show_loading("Dosyalar klasöre çıkarılıyor")

        def done(result: object) -> None:
            win._show_scan_report(report)
            win.notify(LEVEL_INFO, "Çıkarma tamamlandı", f"{result} dosya şuraya yazıldı:\n{dest}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest)))

        def failed(text: str) -> None:
            win._show_scan_report(report)
            win.notify(LEVEL_ERROR, "Çıkarma tamamlanamadı", text)

        def cancelled() -> None:
            win._show_scan_report(report)
            win.statusBar().showMessage("Çıkarma iptal edildi; yarım kalan dosyalar silindi.", 6000)

        win._run(
            lambda ctx: extract_sources(inputs, dest, only, ctx),
            "Dosyalar çıkarılıyor",
            on_success=done,
            on_failure=failed,
            on_progress=win.scan_page.loading.update_progress,
            on_cancel=cancelled,
        )

    def _diagnosis_report(self) -> None:
        """Araçlar > Teşhis Raporu: oyunun yapısını inceleyen bir rapor yazar."""
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        if win.busy or win.report is None or win.keys is None:
            return
        problems = _mw.check_sources(win.sources)
        if problems:
            win.notify(LEVEL_ERROR, "Teşhis raporu oluşturulamıyor", " ".join(problems))
            return
        start = str(win.settings.value("ui/last_dir", str(Path.home())))
        folder = QFileDialog.getExistingDirectory(win, f"{RAPOR_ADI} dosyasının yazılacağı klasörü seçin", start)
        if not folder:
            return
        dest = Path(folder)
        inputs = win._inputs()
        report = win.report
        win.scan_page.show_loading("Teşhis raporu hazırlanıyor")

        def done(result: object) -> None:
            win._show_scan_report(report)
            win.notify(LEVEL_INFO, "Teşhis raporu hazır", f"{result}\n\n{UYARI}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest)))

        def failed(text: str) -> None:
            win._show_scan_report(report)
            win.notify(LEVEL_ERROR, "Teşhis raporu oluşturulamadı", text)

        def cancelled() -> None:
            win._show_scan_report(report)
            win.statusBar().showMessage("Teşhis raporu iptal edildi.", 5000)

        win._run(
            lambda ctx: str(rapor_uret(inputs, dest, ctx)),
            "Teşhis raporu hazırlanıyor",
            on_success=done,
            on_failure=failed,
            on_progress=win.scan_page.loading.update_progress,
            on_cancel=cancelled,
        )

    # --- metinleri aktarma -------------------------------------------------------------------

    def import_texts(self) -> None:
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        if win.busy or win.report is None or win.keys is None:
            return
        problems = _mw.check_sources(win.sources)
        if problems:
            win.notify(LEVEL_ERROR, "Metinler aktarılamıyor", " ".join(problems))
            return
        inputs = win._inputs()
        report = win.report
        language = win.scan_page.report.language.currentData()
        source_language = str(language) if language else None
        chosen = win.scan_page.report.selected_paths()  # tarama sayfasında işaretli dosyalar
        win._import_language = source_language or "en"
        # Aktarma, projeyi seçime göre eşitler: seçilmeyen proje dosyaları çevirileriyle silinir. Önce sorulur.
        win._confirmed_removals = set()
        dropped = win._files_to_remove(chosen)
        if dropped and not win._confirm_removal(dropped):
            return
        win._confirmed_removals = dropped
        win.scan_page.show_loading("Metinler oyundan çıkarılıyor")

        def failed(text: str) -> None:
            win._show_scan_report(report)
            win.notify(LEVEL_ERROR, "Metinler aktarılamadı", text)

        def cancelled() -> None:
            win._show_scan_report(report)
            win.statusBar().showMessage("Aktarma iptal edildi; projede değişiklik yapılmadı.", 6000)

        win._run(
            lambda ctx: _mw.extract_texts(inputs, report, ctx, source_language, chosen),
            "Metinler çıkarılıyor",
            on_success=win._texts_extracted,
            on_failure=failed,
            on_progress=win.scan_page.loading.update_progress,
            on_cancel=cancelled,
        )

    def _files_to_remove(self, kept: Collection[str]) -> set[str]:
        """Projede aktarılmış olup `kept` içinde olmayan dosyalar (aktarma bunları çevirileriyle siler)."""
        return {path for path in self._win.project.translated_counts_by_file() if path not in kept}

    def _confirm_removal(self, paths: Collection[str]) -> bool:
        win = self._win
        counts = win.project.translated_counts_by_file()
        return win.ask_remove_files(len(paths), sum(counts.get(p, 0) for p in paths))

    def ask_remove_files(self, files: int, translated: int) -> bool:
        """Seçilmeyen dosyaların projeden kaldırılmasını onaylatır (testlerde değiştirilir)."""
        box = QMessageBox(self._win)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Dosyalar projeden kaldırılacak")
        lines = (
            f"Bu dosyalarda {format_int(translated)} çevrilmiş satır var; çevirileri silinir ve geri alınamaz."
            if translated
            else "Bu dosyalarda çevrilmiş satır yok."
        )
        box.setText(f"Seçmediğiniz {format_int(files)} dosya projeden kaldırılacak. {lines}")
        remove = box.addButton("Kaldır ve Aktar", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Vazgeç", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is remove

    def _texts_extracted(self, result: object) -> None:
        win = self._win
        assert isinstance(result, TextExtraction)
        if win.report is not None:
            win._show_scan_report(win.report)
        # İçerikten dil nedeniyle düşen dosyalar da silinir: onaylanandan fazlası yazmadan önce yeniden sorulur.
        actual = win._files_to_remove({f.path for f in result.files})
        if actual - win._confirmed_removals and not win._confirm_removal(actual):
            win.statusBar().showMessage("Aktarma durduruldu; projede değişiklik yapılmadı.", 6000)
            return
        try:
            stats = win.project.import_texts(result.files)
            win.project.set_setting("source_language", win._import_language)
            record_extraction(win.project, (fmt for _path, _tid, fmt in win.project.text_files()))
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Metinler aktarılamadı", exc.user_text())
            return
        win._reload_rows()
        win._mark_changed()
        summary = (
            f"{format_int(stats.files)} dosyadan metinler aktarıldı: {format_int(stats.added)} yeni, "
            f"{format_int(stats.changed)} değişen, {format_int(stats.unchanged)} aynı kalan, "
            f"{format_int(stats.removed)} kaldırılan satır."
        )
        if result.skipped_languages:
            skipped = sum(result.skipped_languages.values())
            summary += f" Kaynak dil dışındaki {format_int(skipped)} dil dosyası atlandı."
        if stats.changed:
            summary += " Orijinali değişen ve çevirisi olan satırlar gözden geçirilmek üzere “Hatalı” işaretlendi."
        if result.warnings:
            shown = result.warnings[:5]
            more = len(result.warnings) - len(shown)
            summary += "\n\nAçılamayan dosyalar:\n• " + "\n• ".join(shown)
            if more > 0:
                summary += f"\n… ve {more} dosya daha"
        win.translate_page.show_notice("warning" if result.warnings else "success", summary)
        win.nav.setCurrentRow(STEP_TRANSLATE)
