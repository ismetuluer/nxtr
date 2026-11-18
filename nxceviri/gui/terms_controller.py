"""Terimler denetleyicisi: Terminoloji penceresi, satırlardan terim ekleme, Ollama ile terim önerisi.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Denetleyici durum tutmaz; proje, ayarlar ve `busy` her
çağrıda pencereden okunur. Pencerede yönlendirmesi olan her yöntem (`notify`, `_run`, `_sync_spell`,
`find_term_candidates`, `suggest_glossary_terms`, `open_settings`...) pencere üzerinden çağrılır. Terim yok sayma
(`ignore_terms`, `_terms_ignored`) Kontrol Et denetleyicisine, Ayarlar penceresi (`open_settings`) ana pencereye aittir.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from nxceviri.core.errors import NxError
from nxceviri.core.progress import TaskContext
from nxceviri.core.translate.glossary_io import merge_terms, plan_terms_from_rows
from nxceviri.core.translate.providers.base import ProviderError
from nxceviri.core.translate.providers.ollama import DEFAULT_URL, OllamaProvider
from nxceviri.core.translate.runner import ACTION_TRANSLATE
from nxceviri.core.translate.terms import TermCandidate, TermSuggestion, find_candidates, suggest_glossary
from nxceviri.gui.machine_dialogs import (
    PROVIDER_OLLAMA,
    AddTermsDialog,
    GlossaryDialog,
    MachineSettings,
    TermSuggestionsDialog,
)
from nxceviri.gui.notify import (
    LEVEL_ERROR,
    LEVEL_INFO,
    LEVEL_SUCCESS,
    LEVEL_WARNING,
    NoticeAction,
    split_notice,
)
from nxceviri.gui.settings_dialog import PAGE_PROVIDERS
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow


class TermsController:
    """Terminoloji işleri; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win

    def edit_glossary(self) -> None:
        win = self._win
        start = Path(str(win.settings.value("glossary/dir", str(Path.home()))))
        dialog = GlossaryDialog(win, win.project.glossary(), start, can_suggest=not win.busy)
        accepted = dialog.exec() == GlossaryDialog.DialogCode.Accepted
        win.settings.setValue("glossary/dir", str(dialog.start_dir))
        if not accepted:
            return
        try:
            win.project.set_glossary(dialog.terms())
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Terminoloji kaydedilemedi", exc.user_text())
            return
        win._mark_changed()
        win._sync_spell()
        win.statusBar().showMessage(f"Terminoloji kaydedildi ({len(dialog.terms())} terim).", 5000)
        if dialog.wants_suggestions:
            win.suggest_glossary_terms()

    def add_rows_to_terminology(self) -> None:
        """Seçili satırların orijinal ve çevirisi (ayıklanarak) onaydan sonra terminolojiye eklenir."""
        win = self._win
        rows = win.translate_page.selected_rows()
        if not rows:
            win.notify(LEVEL_WARNING, "Önce satır seçin", "Terminolojiye eklenecek satırları tabloda seçin.")
            return
        plan = plan_terms_from_rows(rows, win.project.glossary())
        if not plan.new and not plan.conflicts:
            win.notify(LEVEL_INFO, "Eklenecek terim yok", "Seçili satırlar zaten terminolojide ya da çevirisiz.")
            return
        dialog = AddTermsDialog(win, plan.new, plan.conflicts)
        if dialog.exec() != AddTermsDialog.DialogCode.Accepted or not dialog.selected():
            return
        merged, added, updated = merge_terms(win.project.glossary(), dialog.selected())
        try:
            win.project.set_glossary(merged)
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Terminoloji kaydedilemedi", exc.user_text())
            return
        win._mark_changed()
        win._sync_spell()
        win._sync_live()
        win.notify(
            LEVEL_SUCCESS,
            "Terminoloji güncellendi",
            f"{format_int(added)} terim eklendi · {format_int(updated)} terim güncellendi",
        )

    def find_term_candidates(self) -> list[TermCandidate]:
        """Terim önerisinin adayları: metinlerde sık geçen, terminolojide olmayan özel adlar."""
        win = self._win
        return find_candidates(win.project.translation_rows(), win.project.glossary())

    def suggest_glossary_terms(self) -> None:
        """Metinlerde sık geçen adları bulur, Ollama'dan karşılık ister; onaylananlar terminolojiye katılır."""
        win = self._win
        if win.busy:
            return
        page = win.translate_page
        model = str(win.settings.value("ollama/model", ""))
        if str(win.settings.value("translate/provider", PROVIDER_OLLAMA)) != PROVIDER_OLLAMA or not model:
            win.notify(
                LEVEL_WARNING,
                "Terim önerisi için Ollama gerekli",
                "Otomatik Çeviri'de sağlayıcı olarak Ollama'yı ve bir model seçin.",
                (NoticeAction("Otomatik Çeviri…", lambda: win.start_machine_translation(ACTION_TRANSLATE)),),
            )
            return
        candidates = win.find_term_candidates()
        if not candidates:
            win.notify(
                LEVEL_INFO,
                "Önerilecek terim yok",
                "Cümle ortasında en az iki kez büyük harfle geçen yeni bir ad bulunamadı.",
            )
            return
        notes = win.project.setting("translation_notes")
        chosen = MachineSettings(PROVIDER_OLLAMA, str(win.settings.value("ollama/url", DEFAULT_URL)), model, notes)
        try:
            provider = win.provider_factory(chosen)
        except NxError as exc:
            page.show_notice("danger", exc.user_text())
            return
        if not isinstance(provider, OllamaProvider):
            page.show_notice("danger", "Terim önerisi yalnızca Ollama ile yapılabilir.")
            return
        source_lang = win.project.setting("source_language", "en")

        def work(ctx: TaskContext) -> list[TermSuggestion]:
            provider.cancel_token = ctx.token
            try:
                status = provider.test_connection()
                if not status.ok:
                    raise ProviderError(status.message)
                return suggest_glossary(provider, candidates, source_lang, notes, ctx)
            finally:
                provider.close()

        def failed(text: str) -> None:
            page.set_machine_running(False)
            title, rest = split_notice(text)
            if "bağlanılamadı" in title:
                title = "Ollama'ya bağlanılamadı"
            win.notify(
                LEVEL_ERROR,
                title,
                rest,
                (NoticeAction("Ayarları Aç", lambda: win.open_settings(PAGE_PROVIDERS)),),
            )

        def cancelled() -> None:
            page.set_machine_running(False)
            win.notify(LEVEL_WARNING, "Terim önerisi durduruldu", "Terminoloji değişmedi.")

        def done(result: object) -> None:
            assert isinstance(result, list)
            page.set_machine_running(False)
            if not result:
                win.notify(
                    LEVEL_INFO, "Terim önerilmedi", f"Model {format_int(len(candidates))} aday için bir terim önermedi."
                )
                return
            dialog = TermSuggestionsDialog(win, result)
            if dialog.exec() != TermSuggestionsDialog.DialogCode.Accepted or not dialog.selected():
                page.show_notice("success", "Terim önerileri eklenmedi.")
                return
            merged, added, updated = merge_terms(win.project.glossary(), dialog.selected())
            try:
                win.project.set_glossary(merged)
            except NxError as exc:
                page.show_notice("danger", exc.user_text())
                return
            win._mark_changed()
            win._sync_spell()
            win.notify(
                LEVEL_SUCCESS,
                "Terminoloji güncellendi",
                f"{format_int(added)} terim eklendi · {format_int(updated)} terim güncellendi",
            )

        page.set_machine_running(True)
        page.show_notice("success", "")
        win._run(
            work,
            "Terim önerisi",
            on_success=done,
            on_failure=failed,
            on_progress=page.update_machine_progress,
            on_cancel=cancelled,
        )
