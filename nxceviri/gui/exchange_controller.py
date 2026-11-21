"""Dış redaksiyon / dış çeviri ve hazır çeviri denetleyicisi: dış TXT/XLSX/CSV dışa aktarma, redakte edilmiş ya da
çevrilmiş dosyaları içe aktarma ve oyunun hazır yamasındaki çevirileri projeye alma.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Denetleyici durum tutmaz; proje, çeviri sayfası ve `busy`
her çağrıda pencereden okunur. Pencerede yönlendirmesi olan her yöntem (`notify`, `_run`, `_mark_changed`,
`_reload_rows`, `_refresh_marks`, `_set_last_job`, `_to_translate_step`) pencere üzerinden çağrılır; testler bu adları
pencerede değiştirir. Testlerin `nxceviri.gui.main_window` üzerinde değiştirdiği `CsvExportDialog` adı çağrı anında
`_mw.<ad>` ile okunur; `ImportDialog` bu modülden okunur (testler `exchange_controller.ImportDialog`'u değiştirir).
Onay kaldırma, çeviri kaydetme ve geri alma/geçmiş sonraki adımlara aittir;
pencerede kalır.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMessageBox

from nxceviri.core.errors import NxError
from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import QaIssue
from nxceviri.core.translate.csvio import (
    CsvError,
    export_findings_txt,
    export_findings_xlsx,
    export_translation_txt,
    export_translation_xlsx,
    export_txt,
    export_xlsx,
    finding_notes,
    prepare_correction,
)
from nxceviri.core.translate.origin import NO_ORIGIN
from nxceviri.core.translate.port import ReadyTranslations, port_translations, read_ready_translations
from nxceviri.core.translate.status import Status
from nxceviri.gui.csv_dialog import FORMAT_TXT, MODE_FINDINGS, MODE_REDACTION, MODE_TRANSLATION
from nxceviri.gui.import_dialog import ImportDialog
from nxceviri.gui.jobs import new_job_id
from nxceviri.gui.machine_controller import REVISE_INSTRUCTION_KEY
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_INFO, LEVEL_SUCCESS
from nxceviri.gui.step_nav import STEP_TRANSLATE
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow


class ExchangeController:
    """Dış dosya alışverişi ve hazır çeviri içe aktarma; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win

    def import_ready_translation(self) -> None:
        """Oyunun hazır bir Türkçe yamasındaki (Unity metin tabloları) çevirileri projeye aktarır."""
        win = self._win
        if win.busy:
            return
        if not win.project.translation_rows():
            win.notify(
                LEVEL_INFO,
                "Hazır çeviriyi içe aktar",
                "Önce “Metinleri Tara” adımından metinleri çeviri tablosuna aktarın.",
            )
            return
        start = str(win.settings.value("import/dir", str(Path.home())))
        folder = QFileDialog.getExistingDirectory(win, "Çeviri yamasının klasörünü seçin", start)
        if not folder:
            return
        win.settings.setValue("import/dir", folder)
        root = Path(folder)

        def confirm(result: object) -> None:
            assert isinstance(result, ReadyTranslations)
            win.statusBar().showMessage("Hazır", 2000)
            plan = port_translations(win.project, result, apply=False)
            lines = [
                f"Yamada {format_int(plan.found)} metin var; {format_int(plan.matched)} tanesi bu projeyle eşleşti.",
                f"Yazılacak: {format_int(plan.applied)} satır (zaten aynı olan {format_int(plan.unchanged)}).",
                f"Onayladığınız veya redakte ettiğiniz {format_int(plan.protected)} satıra dokunulmaz.",
            ]
            if plan.source_changed:
                lines.append(
                    f"{format_int(plan.source_changed)} satırın özgün metni oyunun bu sürümünde yamadan farklı; "
                    "bunlara dokunulmaz, çevrilmeleri gerekir."
                )
            if plan.code_problems:
                lines.append(
                    f"{format_int(len(plan.code_problems))} satırın kontrol kodları uyuşmuyor; bunlar yazılmaz "
                    "ve mevcut çevirileri korunur."
                )
            lines.append("\nÇeviriler “Makine” durumuyla yazılır; gözden geçirebilirsiniz. Devam edilsin mi?")
            if plan.applied == 0:
                win.notify(
                    LEVEL_INFO, "Hazır çeviriyi içe aktar", "Yazılacak yeni bir çeviri yok.\n\n" + "\n".join(lines[:3])
                )
                return
            answer = QMessageBox.question(win, "Hazır çeviriyi içe aktar", "\n".join(lines))
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                report = port_translations(win.project, result)
            except NxError as exc:
                win.notify(LEVEL_ERROR, "Hazır çeviriyi içe aktar", exc.user_text())
                return
            win._mark_changed()
            win._reload_rows()
            text = f"{format_int(report.applied)} satır hazır çeviriden aktarıldı."
            if report.code_problems:
                text += f" {format_int(len(report.code_problems))} satır kontrol kodları uyuşmadığı için atlandı."
            win.nav.setCurrentRow(STEP_TRANSLATE)
            win.translate_page.show_notice("success", text)

        def failed(text: str) -> None:
            win.notify(LEVEL_ERROR, "Hazır çeviriyi içe aktar", text)

        win._run(
            lambda ctx: read_ready_translations(root, ctx),
            "Hazır çeviri okunuyor",
            on_success=confirm,
            on_failure=failed,
            on_progress=lambda _d, _t, message: win.statusBar().showMessage(message),
        )

    def export_csv(self) -> None:
        """Çevirileri dış redaksiyon için TXT/XLSX olarak dışa aktarır."""
        self._export_external(translation=False)

    def export_translation(self) -> None:
        """Çevirileri dış çeviri (çevirmen/model) için TXT/XLSX olarak dışa aktarır."""
        self._export_external(translation=True)

    def _export_external(self, *, translation: bool) -> None:
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        page = win.translate_page
        if win.busy or not win._to_translate_step():
            return
        dialog = _mw.CsvExportDialog(
            win,
            selected=page.selected_rows(),
            visible=page.filtered_rows(),
            all_rows=page.model.rows,
            instruction=win.project.setting(REVISE_INSTRUCTION_KEY),
            mode=MODE_TRANSLATION if translation else MODE_REDACTION,
            name_hint=(win.project.path.stem if win.project.path else "ceviriler") + ("_ceviri" if translation else ""),
        )
        if dialog.exec() != _mw.CsvExportDialog.DialogCode.Accepted or not dialog.rows():
            return
        txt = dialog.format() == FORMAT_TXT
        suffix = ".txt" if txt else ".xlsx"
        name = win.project.path.stem if win.project.path else "ceviriler"
        if translation:
            name += "_ceviri"
        start = Path(str(win.settings.value("csv/dir", str(Path.home())))) / f"{name}{suffix}"
        filters = (
            "Metin dosyaları (*.txt);;Excel dosyaları (*.xlsx);;Tüm dosyalar (*)"
            if txt
            else "Excel dosyaları (*.xlsx);;Metin dosyaları (*.txt);;Tüm dosyalar (*)"
        )
        title = "Dış çeviri dosyasını kaydet" if translation else "Dış redaksiyon dosyasını kaydet"
        target, _ = QFileDialog.getSaveFileName(win, title, str(start), filters)
        if not target:
            return
        path = Path(target)
        if path.suffix.lower() != suffix:
            path = path.with_name(path.name + suffix)
        win.settings.setValue("csv/dir", str(path.parent))
        try:
            if translation:
                export = export_translation_txt if txt else export_translation_xlsx
            else:
                export = export_txt if txt else export_xlsx
            paths = export(dialog.rows(), path, by_group=dialog.by_group(), parts=dialog.parts())
        except CsvError as exc:
            page.show_notice("danger", exc.user_text())
            return
        QGuiApplication.clipboard().setText(dialog.prompt.toPlainText())
        files = paths[0].name if len(paths) == 1 else f"{format_int(len(paths))} dosya ({paths[0].name} …)"
        if translation:
            shown = "TXT" if txt else "XLSX"
            page.show_notice(
                "success",
                f"{format_int(len(dialog.rows()))} satır yazıldı ({shown}): {files}. Talimat panoya kopyalandı.",
            )
        else:
            page.show_notice(
                "success",
                f"{format_int(len(dialog.rows()))} satır yazıldı: {files}. Talimat panoya kopyalandı.",
            )

    def export_findings(self) -> None:
        """Kontrol Et'te görünen (ya da seçili) bulguları satırlarıyla dış redaksiyon dosyasına yazar.

        Dosya redaksiyon dosyasıyla aynıdır, sonunda salt okunur `bulgu` sütunu bulunur; düzeltilmiş dosya
        Çeviri → Dış Redaksiyon → “İçe Aktar” ile geri yüklenir.
        """
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        title = "Bulguları dışa aktar"
        if win.busy:
            return
        visible = win.qa_page.visible_findings()
        if not visible:
            win.notify(
                LEVEL_INFO,
                title,
                "Dışa aktarılacak bulgu yok. Kontrol Et'te önce “Denetle”yi çalıştırın; soldaki süzgeç "
                "bulguları gizliyorsa “Tüm bulgular”ı seçin.",
            )
            return
        by_id = {r.id: r for r in win.project.translation_rows()}

        def rows_of(issues: list[QaIssue]) -> list[TranslationRow]:
            ids = dict.fromkeys(i.row_id for i in issues)  # tablodaki sıra, her satır bir kez
            return [by_id[i] for i in ids if i in by_id]

        dialog = _mw.CsvExportDialog(
            win,
            selected=rows_of(win.qa_page.selected_findings()),
            visible=rows_of(visible),
            all_rows=[],
            instruction=win.project.setting(REVISE_INSTRUCTION_KEY),
            mode=MODE_FINDINGS,
            notes=finding_notes(visible),
            name_hint=(win.project.path.stem if win.project.path else "ceviriler") + "_bulgular",
        )
        if dialog.exec() != _mw.CsvExportDialog.DialogCode.Accepted or not dialog.rows():
            return
        rows = dialog.rows()
        txt = dialog.format() == FORMAT_TXT
        suffix = ".txt" if txt else ".xlsx"
        name = (win.project.path.stem if win.project.path else "ceviriler") + "_bulgular"
        start = Path(str(win.settings.value("csv/dir", str(Path.home())))) / f"{name}{suffix}"
        filters = (
            "Metin dosyaları (*.txt);;Excel dosyaları (*.xlsx);;Tüm dosyalar (*)"
            if txt
            else "Excel dosyaları (*.xlsx);;Metin dosyaları (*.txt);;Tüm dosyalar (*)"
        )
        target, _ = QFileDialog.getSaveFileName(win, "Bulgu dosyasını kaydet", str(start), filters)
        if not target:
            return
        path = Path(target)
        if path.suffix.lower() != suffix:
            path = path.with_name(path.name + suffix)
        win.settings.setValue("csv/dir", str(path.parent))
        try:
            export = export_findings_txt if txt else export_findings_xlsx
            paths = export(rows, finding_notes(visible), path, by_group=dialog.by_group(), parts=dialog.parts())
        except CsvError as exc:
            win.notify(LEVEL_ERROR, title, exc.user_text())
            return
        QGuiApplication.clipboard().setText(dialog.prompt.toPlainText())
        files = paths[0].name if len(paths) == 1 else f"{format_int(len(paths))} dosya ({paths[0].name} …)"
        win.notify(
            LEVEL_SUCCESS,
            title,
            f"{format_int(len(rows))} satır bulgularıyla yazıldı: {files}. Talimat panoya kopyalandı.",
        )

    def import_csv(self) -> None:
        """Redakte edilmiş dış TXT/XLSX/CSV dosyalarını projeye aktarır."""
        self._import_external(translation=False)

    def import_translation(self) -> None:
        """Dış çeviri dosyalarındaki yeni çevirileri projeye aktarır."""
        self._import_external(translation=True)

    def _import_external(self, *, translation: bool) -> None:
        win = self._win
        page = win.translate_page
        if win.busy:
            return
        title = "Dış çeviriden içe aktar" if translation else "Dış redaksiyondan içe aktar"
        job_kind = "translation" if translation else "csv"
        if not page.model.rows:
            win.notify(LEVEL_INFO, title, "Önce “Metinleri Tara” adımından metinleri çeviri tablosuna aktarın.")
            return
        start = str(win.settings.value("csv/dir", str(Path.home())))
        pick_title = (
            "Çevrilmiş TXT, XLSX veya CSV dosyalarını seçin"
            if translation
            else "Redakte edilmiş TXT, XLSX veya CSV dosyalarını seçin"
        )
        targets, _ = QFileDialog.getOpenFileNames(
            win,
            pick_title,
            start,
            "TXT/XLSX/CSV dosyaları (*.txt *.xlsx *.csv);;Metin dosyaları (*.txt);;"
            "Excel dosyaları (*.xlsx);;CSV dosyaları (*.csv);;Tüm dosyalar (*)",
        )
        if not targets:
            return
        win.settings.setValue("csv/dir", str(Path(targets[0]).parent))
        rows = win.project.translation_rows()
        dialog = ImportDialog(
            win,
            title=title,
            rows=rows,
            translation=translation,
            job_kind=job_kind,
            start_dir=str(Path(targets[0]).parent),
            context_fn=win._context_html,
            settings=win.settings,
            kinds=win.translate_page.code_kinds,
        )
        errors = dialog.add_files([Path(t) for t in targets])
        if errors and not dialog.import_files:
            dialog.deleteLater()
            win.notify(LEVEL_ERROR, title, "\n".join(errors))
            return
        if dialog.exec() != ImportDialog.DialogCode.Accepted:
            return
        win.settings.setValue("csv/dir", dialog.last_dir)
        plan = dialog.plan
        accepted = dialog.accepted_changes()
        by_id = {r.id: r for r in rows}
        planned = dict(plan.changes)
        applied: list[tuple[int, str]] = []
        edit_problems: list[str] = []
        for change in accepted:
            row = by_id.get(change.entry_id)
            if row is None:
                continue
            final: str
            issues: list[str]
            if change.new_text == planned.get(row.id):
                final, issues = change.new_text, []  # plan zaten onardı ve denetledi
            else:
                final, issues = prepare_correction(row, change.new_text)
            if issues:
                edit_problems.append(f"• {change.label}: {' '.join(issues)}")
                continue
            if final == row.translation:
                continue  # kullanıcı düzeltmeyi eski metne çevirdi: yazacak bir şey yok
            applied.append((row.id, final))
        if not applied:
            note = "Hiçbir satır yazılmadı: seçilen düzeltmeler değişiklik bırakmadı."
            if edit_problems:
                note += "\n\n" + "\n".join(edit_problems[:8])
            win.notify(LEVEL_INFO, title, note)
            return
        job_id = new_job_id(job_kind)
        try:
            updated = win.project.set_translations(
                applied,
                status=None if translation else Status.REDACTED,
                machine=translation,
                overwrite_approved=True,
                job=job_id,
                # Dış çeviri metni baştan değiştirir (makine kaynağı artık bilinmez); redaksiyon taslağı düzeltir.
                origin=NO_ORIGIN if translation else None,
            )
        except NxError as exc:
            win.notify(LEVEL_ERROR, title, exc.user_text())
            return
        page.model.update_rows(updated)
        win._mark_changed()
        win._refresh_marks()
        count = win._set_last_job(job_id)
        win._to_translate_step()
        source_word = "dış çeviriden" if translation else "dış redaksiyondan"
        text = f"{format_int(count)} satırın çevirisi {source_word} güncellendi."
        skipped_count = len(plan.code_problems) + len(edit_problems)
        if skipped_count:
            text += f" {format_int(skipped_count)} satır kontrol kodları uymadığı için yazılmadı."
        page.show_notice("success" if not skipped_count else "warning", text)
