"""Geçmiş ve geri al denetleyicisi: son işin değişiklikleri, satır geçmişi, geri döndürme, bul-değiştir yazımı ve
Geri Al / Yinele eylemleri.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Denetleyici durum tutmaz; proje, çeviri sayfası, `busy`,
son iş (`_last_job`) ve düzeltme raporu (`_fix_report`) her çağrıda pencereden okunur. Pencerede yönlendirmesi olan her
yöntem (`notify`, `_mark_changed`, `_commit_translations`, `_to_translate_step`, ayrıca bu dosyadaki yöntemlerin
kendileri) pencere üzerinden çağrılır; testler bu adları pencerede değiştirir. Testlerin `nxceviri.gui.main_window`
üzerinde değiştirdiği `ChangesDialog` adı çağrı anında `_mw.ChangesDialog` ile okunur. `_to_translate_step` ve
`_menu_*` gezinti, `_machine_results` makine yapıştırıcısı, `_save_uppercase` ise geçmişle ilgisiz olduğundan
pencerede kalır.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from typing import TYPE_CHECKING

from nxceviri.core.errors import NxError
from nxceviri.core.project import Change, TranslationRow
from nxceviri.core.translate.report import job_label, mark_label
from nxceviri.core.translate.status import Status
from nxceviri.gui.jobs import new_job_id
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.changes_dialog import ChangesDialog
    from nxceviri.gui.main_window import MainWindow


class HistoryController:
    """Değişiklik geçmişi ve geri al/yinele; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win

    def set_last_job(self, job_id: str) -> int:
        """Son işi hatırlar; işte değişen (geri alınmamış) satır sayısını döndürür."""
        win = self._win
        win._last_job = job_id
        changes = win.project.job_changes(job_id)
        win.translate_page.set_last_changes({c.entry_id: c.old_text for c in changes})
        return len(changes)

    def refresh_marks(self, ids: Sequence[int] | None = None) -> None:
        """Durum sütunundaki "· redaksiyon" gibi işaretler: satırın son değişikliğini yapan iş.

        `ids` verilirse yalnızca o satırların işareti yenilenir (az satır değişen işlerde bütün geçmişi okumaz).
        """
        win = self._win
        model = win.translate_page.model
        if ids is None:
            marks = {eid: label for eid, job in win.project.last_jobs().items() if (label := mark_label(job))}
        else:
            marks = dict(model.marks)
            latest = win.project.last_jobs(ids)
            for eid in ids:
                text = mark_label(latest[eid]) if eid in latest else ""
                if text:
                    marks[eid] = text
                else:
                    marks.pop(eid, None)
        model.set_marks(marks)

    def show_job_changes(self) -> None:
        """Son işin değişikliklerini gösterir; işaretlenenler geri alınır."""
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        if win._last_job is None:
            return
        changes = win.project.job_changes(win._last_job)
        if not changes:
            win.translate_page.set_last_changes({})
            win.translate_page.show_notice("success", "Son işte değişen (geri alınmamış) satır kalmadı.")
            return
        applied = win._fix_report[1] if win._fix_report is not None and win._fix_report[0] == win._last_job else None
        win._open_changes(
            _mw.ChangesDialog(
                win,
                f"{job_label(win._last_job)}: değişiklikler",
                changes,
                kinds=applied,
                edit_fn=win._edit_from_changes,
                context_fn=win._context_html,
                settings=win.settings,
            )
        )

    def edit_from_changes(self, row_id: int, text: str) -> str | None:
        """Değişiklikler penceresinde "Yeni" hücresinin elle düzeltilmesi: Çevir'deki kayıt yoluyla yazılır."""
        win = self._win
        if win.busy:
            return "Bir iş sürerken düzenlenemez; iş bitince yeniden deneyin."
        try:
            rows = win._commit_translations([(row_id, text)])
        except NxError as exc:
            return exc.user_text()
        win.translate_page.model.update_rows(rows)
        return None

    def context_html(self, row_id: int) -> str:
        """Satırın bağlamı: aynı dosyada önceki ve sonraki iki satırın orijinali ve çevirisi (ipucu için HTML)."""
        before, after = self._win.translate_page.model.neighbors(row_id)

        def line(r: TranslationRow) -> str:
            translation = html.escape(r.translation) if r.translation else "<i>çevrilmedi</i>"
            return f"{html.escape(r.source)}<br><span style='color:gray'>{translation}</span>"

        parts = [line(r) for r in before]
        parts.append("<b>▶ bu satır</b>")
        parts += [line(r) for r in after]
        return "<br><br>".join(parts) if before or after else ""

    def replace_translations(self, changes: list[tuple[int, str]]) -> list[TranslationRow] | None:
        """Bul ve Değiştir çubuğunun yazma yolu: her eylem tek iştir, Ctrl+Z hepsini geri alır.

        Onaylı satırlar onaylı kalır, diğerleri makine durumunda yazılır. Hata olursa None döner ve neden
        sayfada bildirilir.
        """
        win = self._win
        if win.busy:
            return None
        page = win.translate_page
        job_id = new_job_id("replace")
        status = {r.id: r.status for r in page.model.rows}
        approved = [c for c in changes if status.get(c[0]) == Status.APPROVED]
        others = [c for c in changes if status.get(c[0]) != Status.APPROVED]
        try:
            rows = win.project.set_translations(approved, job=job_id)
            rows += win.project.set_translations(others, machine=True, job=job_id)
        except NxError as exc:
            page.show_notice("danger", exc.user_text())
            return None
        page.model.update_rows(rows)
        win._mark_changed()
        win._refresh_marks([r.id for r in rows])
        win._set_last_job(job_id)
        return rows

    def show_row_history(self, entry_id: int) -> None:
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        changes = win.project.row_history(entry_id)
        if not changes:
            win.translate_page.show_notice("success", "Bu satırın çevirisi henüz hiç değişmedi.")
            return
        win._open_changes(_mw.ChangesDialog(win, "Çeviri geçmişi", changes, history=True))

    def open_changes(self, dialog: ChangesDialog) -> None:
        win = self._win
        win.changes_dialog = dialog
        dialog.accepted.connect(lambda: win._revert(dialog.to_revert))
        dialog.open()  # pencereyi engellemez; kapanınca geri alma uygulanır

    def revert(self, changes: list[Change]) -> None:
        win = self._win
        if not changes or win.busy:
            return
        try:
            rows = win.project.revert(changes)
        except NxError as exc:
            win.translate_page.show_notice("danger", exc.user_text())
            return
        win.translate_page.model.update_rows(rows)
        win._mark_changed()
        win._refresh_marks()
        if win._last_job is not None:
            win._set_last_job(win._last_job)
        win.translate_page.show_notice(
            "success", f"{format_int(len(rows))} satır önceki çevirisine ve durumuna döndürüldü."
        )

    def update_undo_action(self) -> None:
        win = self._win
        job = win.project.undo_job()
        win.undo_action.setText("Geri Al" if job is None else f"Geri Al: {job_label(job)}")
        win.undo_action.setEnabled(job is not None and not win.busy)

    def update_redo_action(self) -> None:
        win = self._win
        job = win.project.redo_job()
        win.redo_action.setText("Yinele" if job is None else f"Yinele: {job_label(job)}")
        win.redo_action.setEnabled(job is not None and not win.busy)

    def undo_last(self) -> None:
        """Çeviri tablosundaki son işlemi (elle düzenleme, onay, makine işi, bul-değiştir, içe aktarma …) geri alır."""
        win = self._win
        page = win.translate_page
        if win.busy:
            page.show_notice("warning", "Bir iş sürerken geri alınamaz; iş bitince veya durdurulunca deneyin.")
            return
        try:
            result = win.project.undo()
        except NxError as exc:
            page.show_notice("danger", exc.user_text())
            return
        win._to_translate_step()
        if result is None:
            page.show_notice("warning", "Geri alınacak bir işlem yok.")
            return
        job, rows = result
        win._show_stepped_rows(rows)
        page.show_notice(
            "success", f"Geri alındı ({job_label(job)}): {format_int(len(rows))} satır önceki hâline döndü."
        )

    def redo_last(self) -> None:
        """Geri alınan son işlemi aynen geri getirir; arada yeni bir düzenleme yapıldıysa yinelenecek bir şey kalmaz."""
        win = self._win
        page = win.translate_page
        if win.busy:
            page.show_notice("warning", "Bir iş sürerken yinelenemez; iş bitince veya durdurulunca deneyin.")
            return
        try:
            result = win.project.redo()
        except NxError as exc:
            page.show_notice("danger", exc.user_text())
            return
        win._to_translate_step()
        if result is None:
            page.show_notice("warning", "Yinelenecek bir işlem yok.")
            return
        job, rows = result
        win._show_stepped_rows(rows)
        page.show_notice("success", f"Yinelendi ({job_label(job)}): {format_int(len(rows))} satır yeniden uygulandı.")

    def show_stepped_rows(self, rows: list[TranslationRow]) -> None:
        """Geri al / yinele sonrası: tabloyu, iş işaretlerini ve "Son işte değişenler"i yeniler."""
        win = self._win
        page = win.translate_page
        page.model.update_rows(rows)
        win._mark_changed()
        win._refresh_marks()
        win._update_undo_action()  # art arda Ctrl+Z / Ctrl+Y zamanlayıcıyı beklemeden doğru eylemi bulsun
        win._update_redo_action()
        if win._last_job is not None:
            win._set_last_job(win._last_job)
        if len(rows) == 1:
            page.select_row(rows[0].id)
