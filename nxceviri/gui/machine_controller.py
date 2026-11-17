"""Makine işleri denetleyicisi: çevir, yeniden çevir, talimatla düzelt (redaksiyon) penceresi ve işin yürütülmesi.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Denetleyici durum tutmaz; proje, ayarlar,
`secrets`, `provider_factory` ve son işin kimliği pencerede durur ve her çağrıda pencereden okunur. Pencerede
yönlendirmesi olan bir yöntem pencere üzerinden çağrılır (`self._win.<ad>`): testler `ask_machine_settings`,
`_launch_machine`, `provider_factory` gibi adları pencerede değiştirir. Testlerin pencere modülünde değiştirdiği
`implicit_terms` pencere modülü üzerinden okunur. Son işin değişiklikleri, satır geçmişi ve terim önerileri
pencerede kalır.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from nxceviri.core.errors import NxError
from nxceviri.core.project import TranslationRow, row_group
from nxceviri.core.translate.origin import MEMORY_ORIGIN, MachineOrigin
from nxceviri.core.translate.providers.ollama import DEFAULT_URL
from nxceviri.core.translate.report import mark_label
from nxceviri.core.translate.runner import (
    ACTION_REVISE,
    ACTION_TRANSLATE,
    MachineJob,
    RunSummary,
    memory_filled_ids,
    target_rows,
)
from nxceviri.gui.jobs import JOB_TITLES, describe_summary, new_job_id, run_and_close, short_summary
from nxceviri.gui.machine_dialogs import (
    PROVIDER_OLLAMA,
    SCOPE_ALL,
    SCOPE_FILTERED,
    SCOPE_GROUPS,
    SCOPE_PATTERN,
    SCOPE_SELECTED,
    MachineDialog,
    MachineSettings,
    rows_matching,
)
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_SUCCESS, LEVEL_WARNING, NoticeAction

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

#: Proje ayarında saklanan talimatların anahtarları (pencere modülü de aynı adlarla yeniden verir).
REVISE_INSTRUCTION_KEY = "revise_instruction"
TRANSLATE_INSTRUCTION_KEY = "translate_instruction"


class MachineController:
    """Makine işlerinin iş akışı; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win

    def ask_machine_settings(
        self,
        scopes: Mapping[str, Sequence[TranslationRow]],
        action: str = ACTION_TRANSLATE,
        scope: str = SCOPE_ALL,
    ) -> MachineSettings | None:
        win = self._win
        dialog = MachineDialog(
            win,
            provider=str(win.settings.value("translate/provider", PROVIDER_OLLAMA)),
            base_url=str(win.settings.value("ollama/url", DEFAULT_URL)),
            model=str(win.settings.value("ollama/model", "")),
            notes=win.project.setting("translation_notes"),
            source_language=win.project.setting("source_language", "en"),
            secrets=win.secrets,
            scopes=scopes,
            action=action,
            scope=scope,
            instruction=win.project.setting(REVISE_INSTRUCTION_KEY),
            translate_instruction=win.project.setting(TRANSLATE_INSTRUCTION_KEY),
        )
        try:
            if dialog.exec() != MachineDialog.DialogCode.Accepted:
                return None
            return dialog.settings()
        finally:
            dialog.deleteLater()  # her açılışta ana pencerenin çocuğu olarak kalıyordu (sızıntı)

    def machine_scopes(self) -> dict[str, list[TranslationRow]]:
        """Pencerede sunulan kapsamlar: seçili satırlar, onların grupları, filtrelenen satırlar, tümü."""
        page = self._win.translate_page
        rows = page.model.rows
        selected = page.selected_rows()
        groups = {row_group(r) for r in selected}
        filtered = page.filtered_rows()
        return {
            SCOPE_SELECTED: selected,
            SCOPE_GROUPS: [r for r in rows if row_group(r) in groups],
            SCOPE_FILTERED: filtered if len(filtered) < len(rows) else [],
            SCOPE_ALL: rows,
        }

    def remember_machine_settings(self, chosen: MachineSettings) -> bool:
        win = self._win
        win.settings.setValue("translate/provider", chosen.provider)
        win.settings.setValue("ollama/url", chosen.base_url)
        win.settings.setValue("ollama/model", chosen.model)
        win._refresh_status()
        try:
            win.project.set_setting("translation_notes", chosen.notes)
            if chosen.action == ACTION_REVISE:
                if chosen.instruction:
                    win.project.set_setting(REVISE_INSTRUCTION_KEY, chosen.instruction)
            elif chosen.provider == PROVIDER_OLLAMA:
                # Çeviri talimatı isteğe bağlıdır: kutu boşaltılınca saklanan talimat da silinir.
                win.project.set_setting(TRANSLATE_INSTRUCTION_KEY, chosen.instruction)
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return False
        return True

    def start_machine_translation(self, action: str = ACTION_TRANSLATE, from_selection: bool = False) -> None:
        """Çevir / yeniden çevir / talimatla düzelt penceresini açar ve seçilen işi başlatır."""
        # Döngüsel içe aktarma; testler `implicit_terms`'i pencere modülünde değiştirir.
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        if win.busy:
            return
        page = win.translate_page
        if from_selection and not page.table.selectionModel().hasSelection():
            page.show_notice("warning", "Önce çevirmek istediğiniz satırları seçin.")
            return
        scopes = win._machine_scopes()
        chosen = win.ask_machine_settings(scopes, action, SCOPE_SELECTED if from_selection else SCOPE_ALL)
        if chosen is None or not win._remember_machine_settings(chosen):
            return
        scope_rows = (
            rows_matching(scopes.get(SCOPE_ALL, []), chosen.pattern)
            if chosen.scope == SCOPE_PATTERN
            else scopes.get(chosen.scope, [])
        )
        target = target_rows(scope_rows, chosen.action, chosen.include_approved)
        job = MachineJob(
            rows=target,
            source_lang=win.project.setting("source_language", "en"),
            notes=chosen.notes,
            # Terminoloji + örtük terimler (menüde/başlıkta nasıl çevrildiyse cümlede de öyle; partide geçenler gider).
            glossary=[
                *win.project.glossary(),
                *_mw.implicit_terms(win.project.translation_rows(), win.project.glossary(), win._terms_ignored()),
            ],
            memory=win.project.memory_lookup(r.source for r in target) if chosen.action == ACTION_TRANSLATE else {},
            action=chosen.action,
            instruction=chosen.instruction,
            all_rows=win.project.translation_rows(),
        )
        win._launch_machine(
            chosen,
            job,
            set_running=page.set_machine_running,
            on_progress=page.update_machine_progress,
            report=page.show_notice,
        )

    def launch_machine(
        self,
        chosen: MachineSettings,
        job: MachineJob,
        *,
        set_running: Callable[[bool], None],
        on_progress: Callable[[int, int, str], None],
        report: Callable[[str, str], None],
        job_id: str = "",
    ) -> None:
        """Makine işini arka planda çalıştırır; sonuçlar parti parti projeye yazılır.

        Değişen her satırın önceki hâli `job_id` adıyla geçmişe yazılır; iş bitince değişiklikler
        "Son İşin Değişiklikleri" penceresinde gösterilir (çeviri işinde yalnızca düğmeyle).
        """
        win = self._win
        job_id = job_id or new_job_id(job.action)
        try:
            provider = win.provider_factory(chosen)
        except NxError as exc:
            report("danger", exc.user_text())
            return
        set_running(True)
        report("success", "")
        # Satırın kaynağı olarak yalnızca sağlayıcı kimliği ve Ollama modeli yazılır (adres ya da anahtar asla).
        origin = MachineOrigin(chosen.provider, chosen.model if chosen.provider == PROVIDER_OLLAMA else "")
        memory_ids = frozenset(memory_filled_ids(job))

        def finish(level: str, title: str, text: str, details: str = "") -> None:
            set_running(False)
            win._reload_rows()  # filtrelere "Makine" durumu eklensin
            changed = win._set_last_job(job_id)
            actions: list[NoticeAction] = []
            if level == LEVEL_ERROR:
                actions.append(NoticeAction("Tekrar Dene", lambda: win.start_machine_translation(job.action)))
            if changed:
                actions.append(NoticeAction("Değişiklikleri Gör", win.show_job_changes))
            if details:
                actions.append(NoticeAction("Ayrıntılar", lambda: QMessageBox.information(win, title, details)))
            win.notify(level, title, text, tuple(actions))

        def done(result: object) -> None:
            assert isinstance(result, RunSummary)
            level, title, text = short_summary(job.action, result)
            details, _state = describe_summary(job.action, result)
            finish(level, title, text, details if level != LEVEL_SUCCESS else "")

        resume = (
            "Yeniden başlatınca kaldığı yerden devam eder."
            if job.action == ACTION_TRANSLATE
            else "Kalan satırlar için işi yeniden başlatabilirsiniz."
        )
        name = JOB_TITLES[job.action]
        win._run(
            lambda ctx: run_and_close(provider, job, ctx),
            name,
            on_success=done,
            on_failure=lambda text: finish(LEVEL_ERROR, f"{name} durdu", f"{text} Yapılanlar kaydedildi. {resume}"),
            on_progress=on_progress,
            on_cancel=lambda: finish(LEVEL_WARNING, f"{name} durduruldu", f"Yapılanlar kaydedildi. {resume}"),
            on_partial=lambda results: win._machine_results(
                results, chosen.include_approved, job_id, origin=origin, memory_ids=memory_ids
            ),
        )

    def machine_results(
        self,
        results: object,
        overwrite_approved: bool = False,
        job_id: str = "",
        *,
        origin: MachineOrigin | None = None,
        memory_ids: frozenset[int] = frozenset(),
    ) -> None:
        """Makine işinin bir partisini yazar; `origin` satırın kaynağı olarak kaydedilir, bellekten dolanlar
        (`memory_ids`) "Çeviri belleği" olarak."""
        win = self._win
        assert isinstance(results, list)
        job = job_id or new_job_id("translate")
        from_memory = [r for r in results if r[0] in memory_ids]
        from_provider = [r for r in results if r[0] not in memory_ids]
        try:
            rows = []
            if from_memory:
                rows += win.project.set_translations(
                    from_memory, machine=True, overwrite_approved=overwrite_approved, job=job, origin=MEMORY_ORIGIN
                )
            if from_provider:
                rows += win.project.set_translations(
                    from_provider, machine=True, overwrite_approved=overwrite_approved, job=job, origin=origin
                )
        except NxError as exc:
            win.translate_page.show_notice("danger", exc.user_text())
            win._cancel_task()
            return
        page = win.translate_page
        page.model.update_rows(rows)
        label = mark_label(job_id)
        marks = dict(page.model.marks)
        for r in rows:
            if label:
                marks[r.id] = label
            else:
                marks.pop(r.id, None)
        page.model.set_marks(marks)
        page.show_live([r.id for r in rows])
        win._mark_changed()
