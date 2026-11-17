"""Dışa Aktar denetleyicisi: özet ve uyarılar, hedef klasör, hatalı satır seçeneği, mod oluşturma.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 219). Denetleyici durum tutmaz; pencerenin durumunu
(proje, kaynaklar, anahtar, son çıktı) her çağrıda pencereden okur ve pencerede yönlendirmesi olan bir
yöntemi pencere üzerinden çağırır (`self._win.<ad>`), testlerin değiştirdiği yollar böylece sınanır.
Görsel çıkarma (Görseller) ve dolu klasör sorusu (`main_window.ask_full_folder`) pencerede kalır.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from nxceviri.core.errors import NxError
from nxceviri.core.export.layeredfs import (
    INFO_FILE,
    LAYOUT_ATMOSPHERE,
    ExportInfo,
    ExportOptions,
    ExportResult,
    TextFileRef,
    collect_translations,
)
from nxceviri.core.export.layeredfs import export_mod as export_layeredfs
from nxceviri.core.pipeline import check_sources, version_warnings
from nxceviri.core.project import TranslationRow
from nxceviri.core.qa import transliterate
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_SUCCESS, LEVEL_WARNING, NoticeAction
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

#: Dışa aktarma bildiriminde en çok bu kadar orijinal bırakılan hatalı satır listelenir; metinler bu kadar kısalır.
KEPT_ROWS_SHOWN = 12
_CLIP_CHARS = 70


def _clip(text: str) -> str:
    return text if len(text) <= _CLIP_CHARS else text[: _CLIP_CHARS - 1].rstrip() + "…"


class ExportController:
    """Dışa Aktar adımının iş akışı; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win

    def refresh_export(self) -> None:
        page = self._win.export_page
        page.show_form()
        self._win._refresh_graphics()
        if not page.mod_name.text():
            page.mod_name.setText(f"{self._win.project.game_name or 'Oyun'} Türkçe")
        if not page.folder.text():
            page.folder.setText(str(self._win.settings.value("export/dir", str(Path.home() / "Desktop"))))
        letters = self._win._transliterate_letters()
        include_errors = self._include_errors_on()
        by_file, written, errors, untranslated = collect_translations(
            self._win.project.translation_rows(), letters, include_errors=include_errors
        )
        page.set_include_errors(errors=errors, checked=include_errors)
        conversion = f"{' '.join(letters)} → {' '.join(transliterate.apply(letters, letters))}" if letters else "yok"
        if self._win._font_patch_on():
            conversion += f"; font yaması: {' '.join(self._win._patchable_letters())} eklenecek"
        problems = check_sources(self._win.sources) if self._win.sources else ["Oyun dosyası eklenmedi."]
        if self._win.keys is None:
            problems.append("Anahtar dosyası seçilmedi.")
        notes = problems + (version_warnings(self._win.sources, self._win.report) if self._win.sources else [])
        unfixed = "".join(c for c in self._win._patchable_letters() if c not in letters)
        if unfixed and not self._win._font_patch_on():
            notes.append(
                f"Oyun fontlarında {' '.join(unfixed)} harfleri yok; oyunda kutu veya başka fontla görünürler. "
                "“Kontrol Et” adımında “Eksik Türkçe harfleri fontlara ekle” kutusunu işaretleyin."
            )
        if not self._win.project.setting("font_missing") and self._win.font_report is None:
            notes.append("Fontlar henüz taranmadı; “Kontrol Et” adımında Türkçe harfleri denetlemeniz önerilir.")
        page.set_notes(problems, notes[len(problems) :])
        page.set_summary(
            written=written,
            errors=errors,
            untranslated=untranslated,
            conversion=conversion,
            can_export=sum(len(texts) for texts in by_file.values()) > 0 and not problems,
            include_errors=include_errors,
        )
        page.update_target()

    def _include_errors_on(self) -> bool:
        """Hatalı satırlar da aktarılsın mı (CLAUDE.md §4.3'ün bilinçli istisnası); proje başına, varsayılan kapalı."""
        return bool(self._win.project.setting("export_include_errors"))

    def set_include_errors(self, enabled: bool) -> None:
        try:
            self._win.project.set_setting("export_include_errors", "1" if enabled else "")
        except NxError as exc:
            self._win.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return
        self._win._mark_changed()
        self._win._refresh_export()

    def choose_export_folder(self) -> None:
        start = self._win.export_page.folder.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self._win, "Modun oluşturulacağı klasörü seçin", start)
        if folder:
            self._win.export_page.folder.setText(folder)
            self._win.settings.setValue("export/dir", folder)
            self._win.export_page.update_target()

    def export_mod(self) -> None:
        if self._win.busy:
            return
        page = self._win.export_page
        dest = page.destination()
        if dest is None:
            page.result.show_message("danger", "Önce modun oluşturulacağı konumu seçin.")
            return
        problems = check_sources(self._win.sources)
        if self._win.keys is None or problems:
            page.result.show_message("danger", " ".join(problems) or "Anahtar dosyası seçilmedi.")
            return
        decision = self._win._ask_full_folder(dest)
        if decision == "cancel":
            return
        if decision == "other":
            before = page.folder.text()
            self._win._choose_export_folder()
            if page.folder.text() != before:
                self._win.export_mod()
            return
        inputs = self._win._inputs()
        files = [TextFileRef(*f) for f in self._win.project.text_files()]
        rows = self._win.project.translation_rows()
        updates = [s.version for s in self._win.sources if s.kind == "update"]
        bases = [s.version for s in self._win.sources if s.kind == "base"]
        info = ExportInfo(
            self._win.project.game_name or "Oyun",
            self._win.project.title_id,
            bases[0] if bases else None,
            max(updates) if updates else None,
        )
        options = ExportOptions(
            page.layout_key,
            dest,
            page.mod_name.text(),
            self._win._transliterate_letters(),
            patch_fonts=self._win._font_patch_on(),
            font_files=self._win._font_files(),
            uppercase=self._win.project.uppercase_rules(),
            include_errors=self._include_errors_on(),
            overwrite=decision == "overwrite",
            extra_files=self._win._font_overrides(),
        )
        page.result.show_message("success", "")
        page.open_button.hide()
        page.show_running()

        def done(result: object) -> None:
            assert isinstance(result, ExportResult)
            page.show_form()
            self._win.last_export = result.dest
            if options.layout == LAYOUT_ATMOSPHERE:
                where = "Bu klasördeki 'atmosphere' klasörünü SD kartın köküne kopyalayın."
            else:
                where = f"'{info.title_id}' klasörünü emülatörün mod klasörüne kopyalayın."
            message = (
                f"{result.dest}\n{format_int(len(result.files))} dosya, "
                f"{format_int(result.rows_written)} çeviri satırı. {where} Ayrıntılı kurulum bilgisi "
                f"klasördeki “{INFO_FILE}” dosyasında."
            )
            if options.include_errors and result.rows_error:
                message += (
                    f"\n\nHatalı satırlar: {format_int(result.rows_error_written)} tanesi çevirisiyle yazıldı, "
                    f"{format_int(result.rows_error_kept)} tanesi orijinal bırakıldı. Oyun çökerse bu satırları "
                    "düzeltip modu yeniden oluşturun."
                )
            kept = self._win._kept_rows_text(result.error_kept_ids, rows)
            if kept:
                message += "\n\n" + kept
            if result.font_patches:
                message += f"\n\nFont yaması: {format_int(len(result.font_patches))} fonta Türkçe harf eklendi."
            if result.warnings:
                message += "\n\nDikkat: " + " ".join(result.warnings)
            # Sayfada kısa durum; ayrıntılar (kurulum, hatalı satırlar, uyarılar) bildirimin "Ayrıntılar"ında.
            page.result.show_message("warning" if result.warnings else "success", f"Mod oluşturuldu: {result.dest}")
            page.open_button.show()
            self._win.notify(
                LEVEL_WARNING if result.warnings else LEVEL_SUCCESS,
                "Mod oluşturuldu",
                message,
                (NoticeAction("Klasörü Aç", page.open_folder.emit),),
            )

        def failed(text: str) -> None:
            page.show_form()
            page.result.show_message("danger", text)

        def cancelled() -> None:
            page.show_form()
            page.result.show_message("warning", "Dışa aktarma iptal edildi; hedefte hiçbir dosya bırakılmadı.")

        self._win._run(
            lambda ctx: export_layeredfs(inputs, files, rows, options=options, info=info, ctx=ctx),
            "Mod oluşturuluyor",
            on_success=done,
            on_failure=failed,
            on_progress=page.progress.update_progress,
            on_cancel=cancelled,
        )

    def kept_rows_text(self, ids: Sequence[int], rows: Sequence[TranslationRow]) -> str:
        """Hatalı olduğu için modda orijinal kalan satırlar: tablodaki No, orijinal ve çeviri (en çok ilk birkaçı)."""
        if not ids:
            return ""
        by_id = {r.id: r for r in rows}
        model = self._win.translate_page.model
        lines = []
        for row_id in ids[:KEPT_ROWS_SHOWN]:
            row = by_id.get(row_id)
            if row is None:
                continue
            first = _clip(" ".join(row.source.split()))
            second = _clip(" ".join(row.translation.split())) or "çeviri yok"
            lines.append(f"  No {format_int(model.number(row_id))}: “{first}” → “{second}”")
        more = len(ids) - KEPT_ROWS_SHOWN
        if more > 0:
            lines.append(f"  … ve {format_int(more)} satır daha (Kontrol Et → Sorunlar).")
        return "Orijinal bırakılan hatalı satırlar:\n" + "\n".join(lines)

    def open_export_folder(self) -> None:
        if self._win.last_export is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._win.last_export)))
