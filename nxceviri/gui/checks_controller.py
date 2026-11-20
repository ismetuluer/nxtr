"""Kontrol Et denetleyicisi: denetim, pano yenileme, yok sayma, Düzelt, aday seçimi, sığdırma ayarı ve anlık denetim.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Denetleyici pencereyi bilir; pencerenin
durumunu (proje, sayfalar, iş) her çağrıda pencereden okur ve pencerede yönlendirmesi olan bir yöntemi
pencere üzerinden çağırır (`self._win.<ad>`): testler pencerenin yöntemlerini değiştirerek çalışır,
bağlı yöntem önceden saklanırsa değiştirilen yol sınanmaz. Sinyal bağlantıları ve kısayollar pencerede kalır.
Sığdırma ve anlık denetimin önbellek durumu (`_rows_version`, `_fit_lists_cache`, `_limits_key`, `_live_context`,
`_live_kinds`, `_width_cache`, `_width_table_cache`) ve `_fit_recheck_timer` pencerede kalır. Tabloyu projeden
yenileyen `_reload_rows` tarama, makine ve dış redaksiyon denetleyicilerinin de kullandığı genel pencere
yapıştırıcısı olduğundan pencerede kalır.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING

from nxceviri.core.errors import NxError, ProjectError
from nxceviri.core.formats import registry
from nxceviri.core.progress import ProgressCallback, TaskContext
from nxceviri.core.project import Project, TranslationRow, row_group
from nxceviri.core.qa import ignored, transliterate
from nxceviri.core.qa.asciitr import apply_choice
from nxceviri.core.qa.autofix import FixPlan
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_ERROR, SEVERITY_WARNING, QaIssue, parse_word_list
from nxceviri.core.qa.checks import run_checks as run_qa_checks
from nxceviri.core.qa.fixrun import FixSettings, plan_for_issues, plan_for_rows
from nxceviri.core.qa.live import SETTING_KEY as LIVE_KINDS_KEY
from nxceviri.core.qa.live import LiveContext, format_live_kinds, parse_live_kinds
from nxceviri.core.qa.profanity import LEVEL_LABELS as PROFANITY_LEVELS
from nxceviri.core.qa.profanity import ProfanityConfig, parse_level
from nxceviri.core.qa.terms import project_terms
from nxceviri.core.spell.checker import turkish_lower
from nxceviri.core.translate.codekinds import suspected_line_breaks
from nxceviri.core.translate.fitconfig import (
    EACH_GROUP,
    GROUP_PREFIX,
    FitConfig,
    learn_group_rules,
    learn_rules,
    load_config,
    save_config,
    separate_groups,
)
from nxceviri.core.translate.fitwidth import SETTING_WIDTHS, WidthMeasure, box_shape, build_measure, load_table
from nxceviri.core.translate.status import Status
from nxceviri.core.translate.widths import WidthTable
from nxceviri.gui.jobs import new_job_id
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_INFO, LEVEL_SUCCESS, LEVEL_WARNING, NoticeAction
from nxceviri.gui.settings_dialog import KEY_SPELL_COPIED
from nxceviri.gui.step_nav import STEP_QA
from nxceviri.gui.tasks import Task, release_thread
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

#: Projenin ayar tablosunda "Elle sınır" (çeviri panelinin satır sınırı); 0 = kapalı.
MANUAL_LIMIT_KEY = "translate_manual_limit"
#: Proje ayarları: yazım denetiminde yoksayılan sözcükler ve "terim değil" denen ifadeler (JSON listesi).
SPELL_IGNORED_KEY = "spell_ignored"
TERMS_IGNORED_KEY = "terms_ignored"
#: Proje ayarları: küfür / argo denetiminin düzeyi (`profanity.LEVEL_*`; yoksa kapalı) ve "argo değil" sözcükleri.
PROFANITY_LEVEL_KEY = "profanity_level"
PROFANITY_ALLOWED_KEY = "profanity_allowed"
#: Düzelt'in denetimi ve planı bu satır sayısına kadar ana iş parçacığında (anında), fazlası arka plan işinde yapılır.
FIX_SYNC_ROWS = 200
#: Düzeltmeden sonra değişen satırlar bu sayıya kadar panoda yerinde yenilenir; fazlası arka planda tam denetlenir.
FIX_RECHECK_ROWS = 2000
#: Denetim ilerlemesinin bekleme görünümüne en sık yansıtılma aralığı (saniye).
CHECK_PROGRESS_S = 0.2


class ChecksController:
    """Kontrol Et adımının iş akışı; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win
        #: Son denetimin (proje, hata+uyarı sayısı); başka projeye geçilince eskimiş sayılır.
        self.qa_count: tuple[Project, int] | None = None
        self.qa_errors = False
        #: Yazım düzeltmesinden sonra panoda yerinde yeniden denetim (arka planda; aynı anda tek).
        self.board_task: Task | None = None
        self.check_task: Task | None = None  # Durdur'un iptal edeceği tam denetim işi
        self.board_pending: dict[int, TranslationRow] = {}
        #: Panoyu kendisi hemen yenileyen yol (yerinde düzenleme, Düzelt) sürerken `rows_updated` bir şey yapmaz.
        self._board_handled = False
        self.recheck_pending = False
        #: İş sürerken Sorunlar'da yerinde yapılan düzenlemeler: satır → (proje, o anki çeviri, yeni metin).
        self.pending_edits: dict[int, tuple[Project, str, str]] = {}

    def _checks_job(self, rows: list[TranslationRow]) -> Callable[[ProgressCallback | None], list[QaIssue]]:
        """Denetimi `rows` üzerinde çalıştıran işlev (isteğe bağlı ilerleme geri çağrısı alır); ayarlar şimdi okunur
        (iş parçacığı veritabanına dokunmaz)."""
        missing, transliterated = self._win._missing_letters(), self._win._transliterate_letters()
        glossary, fit, spell = self._win.project.glossary(), self._win._fit_config(), self._win.spell
        ignored_terms, spell_ignored = self._win._terms_ignored(), self._win._spell_ignored()
        widths = self._win._width_measure()
        profanity = self._win._profanity_config()

        def job(progress: ProgressCallback | None = None) -> list[QaIssue]:
            return run_qa_checks(
                rows,
                missing,
                transliterated,
                glossary,
                fit,
                spell=spell,
                ignored_terms=ignored_terms,
                spell_ignored=spell_ignored,
                progress=progress,
                widths=widths,
                profanity=profanity,
            )

        return job

    def run_checks(self) -> None:
        """Denetimi hemen (bu iş parçacığında) yapar; düzeltmenin ardından ve testlerde kullanılır."""
        rows = self._win.project.translation_rows()
        self._win._show_check_results(self._checks_job(rows)(None), rows)

    def start_checks(self) -> None:
        """Kontrol Et → Denetle: denetim arka plan işinde çalışır (büyük projede arayüz donmaz), bitince bildirilir."""
        if self._win.busy:
            return
        self._win._fit_recheck_timer.stop()
        self._win.qa_page.mark_checking()
        self._win._run_full_check("Denetim", self._announce_checks)

    def _announce_checks(self, result: list[QaIssue]) -> None:
        """Denetle bitince sonucu bildirir."""
        errors = sum(1 for i in result if i.severity == SEVERITY_ERROR)
        warnings = sum(1 for i in result if i.severity == SEVERITY_WARNING)
        if errors or warnings:
            # Bulgu uygulamanın değil oyun metinlerinin sorunudur; hata simgesi yanıltıp "çöktü" sanılmasın.
            self._win.notify(
                LEVEL_INFO,
                "Denetim bitti",
                f"{format_int(errors)} hata · {format_int(warnings)} uyarı",
                (NoticeAction("Sorunları Gör", lambda: self._win.nav.setCurrentRow(STEP_QA)),),
            )
        else:
            self._win.notify(LEVEL_SUCCESS, "Denetim bitti", "Sorun bulunmadı.")

    def run_full_check(self, description: str, finished: Callable[[list[QaIssue]], None] | None = None) -> None:
        """Tüm satırların denetimini arka plan işinde çalıştırır (Denetle ve düzeltme sonrası yenileme ortak yolu).

        İlerleme gerçektir (denetlenen / toplam) ve bekleme görünümüne yansır; iş Durdur ile iptal edilebilir.
        """
        rows = self._win.project.translation_rows()
        project = self._win.project
        job = self._checks_job(rows)
        detail = f"{format_int(len(rows))} satır denetleniyor"

        def work(ctx: TaskContext) -> object:
            return job(ctx.report)

        shown = [0.0]

        def progress(done: int, total: int, message: str) -> None:
            now = time.monotonic()
            if now - shown[0] >= CHECK_PROGRESS_S or done >= total:  # arayüz saniyede birkaç kez tazelenir
                shown[0] = now
                self._win.qa_page.update_check_progress(done, total, message or detail)

        def done(result: object) -> None:
            if self._win.project is not project:
                return
            assert isinstance(result, list)
            visible = self._win._show_check_results(result, rows)  # yok sayılanlar bildirime de girmez
            if finished is not None:
                finished(visible)

        self._win._run(
            work,
            description,
            on_success=done,
            on_failure=self._win.qa_page.show_check_failed,
            on_progress=progress,
            on_cancel=self._win._on_check_cancelled,
        )
        self.check_task = self._win.task

    def on_check_cancelled(self) -> None:
        """Denetim durduruldu: düzeltme/düzenlemeyle çevirisi değişen satırların eski bulguları geri getirilmez."""
        changed = self._win.qa_page.changed_rows(self._win.translate_page.model.rows)
        self._win.qa_page.stop_checking(changed)
        self._recount_qa()

    def stop_checks(self) -> None:
        """Durdur: sürmekte olan denetim işini iptal eder (başka bir iş sürüyorsa dokunmaz)."""
        if self._win.task is not None and self._win.task is self.check_task:
            self._win.task.cancel()

    def show_check_results(self, issues: list[QaIssue], rows: list[TranslationRow]) -> list[QaIssue]:
        """Denetim sonucunu panoya verir (tek yer: yok sayılanlar burada ayrılır); gösterilen bulguları döndürür."""
        self._win._sync_live()  # Çevir'deki anlık denetim bağlamı Kontrol Et'in kullandığı güncel ayarlarla aynı olsun
        self._win.qa_page.set_code_kinds(self._win._fit_config().kinds)
        issues, hidden = self._split_ignored(issues, rows)  # yok sayılanlar listeye, sayaca ve Çevir'e girmez
        self._win._sync_ignored_to_translate()
        self._win.qa_page.show_issues(issues, rows, hidden)
        self._win.translate_page.set_qa_issues(issues, rows)
        counted = [i for i in issues if i.severity in (SEVERITY_ERROR, SEVERITY_WARNING)]
        self.qa_count = (self._win.project, len(counted))
        self.qa_errors = any(i.severity == SEVERITY_ERROR for i in counted)
        self._win._refresh_nav()
        return issues

    def edit_from_issues(self, row_id: int, text: str) -> None:
        """Sorunlar panosunda yerinde düzenleme: Çevir'deki kayıt yolundan yazılır, satır hemen yeniden denetlenir."""
        if self._win.busy:
            # Metin kaybolmasın: saklanır, iş bitince (satır bu arada değişmediyse) kaydedilir.
            base = next((r.translation for r in self._win.translate_page.model.rows if r.id == row_id), "")
            self.pending_edits[row_id] = (self._win.project, base, text)
            self._win.qa_page.show_fix_result(
                "warning",
                "Düzenlemeniz saklandı. Bir iş sürüyor; düzenleme iş bitince kaydedilecek. "
                "İş satırı değiştirirse ne yapacağınız sorulur.",
            )
            return
        self._commit_board_edit(row_id, text)

    def _commit_board_edit(self, row_id: int, text: str) -> None:
        try:
            rows = self._win._commit_translations([(row_id, text)])
        except NxError as exc:
            self._win.qa_page.show_fix_result("danger", exc.user_text())
            return
        if not rows:
            return
        self._update_rows_handled(rows)
        self._win._recheck_board_rows(rows)

    def _update_rows_handled(self, rows: list[TranslationRow]) -> None:
        """Çeviri tablosunu yeniler; panoyu çağıran yenileyeceği için `rows_updated` ikinci bir denetim açmaz."""
        self._board_handled = True
        try:
            self._win.translate_page.model.update_rows(rows)
        finally:
            self._board_handled = False

    def rows_updated(self, rows: Sequence[TranslationRow]) -> None:
        """Çeviri tablosunda satırlar değişti (Çevir'de düzenleme, Geri Al, bul-değiştir, makine işi, içe aktarma…):
        Kontrol Et çalıştırılmışsa bu satırlar panoda arka planda yeniden denetlenir, düzeltilen bulgu listeden düşer.
        """
        if not self._board_handled:
            self.recheck_board_later(rows)

    def flush_pending_edits(self) -> None:
        """İş bitince saklanan yerinde düzenlemeleri yazar. İş satırı bu arada değiştirdiyse ezmez: metin bildirimde
        gösterilir, "Yine de Kaydet" ile yazılabilir. Proje bu arada değiştiyse düzenleme o projeye ait değildir."""
        pending, self.pending_edits = self.pending_edits, {}
        current: dict[int, str] = {}
        for row_id, (project, _base, _text) in pending.items():
            if project is self._win.project:
                with suppress(ProjectError):  # satır bu arada yeniden taramayla kalktıysa aşağıda bildirilir
                    current[row_id] = self._win.project.translation_row(row_id).translation  # proje dosyası esastır
        for row_id, (project, base, text) in pending.items():
            if project is not self._win.project or row_id not in current:
                self._win.notify(
                    LEVEL_WARNING,
                    "Saklanan düzenleme kaydedilmedi",
                    f"Satır artık bu projede yok. Metniniz: {text}",
                )
            elif current[row_id] == base:
                self._commit_board_edit(row_id, text)
            elif current[row_id] != text:
                self._win.notify(
                    LEVEL_WARNING,
                    "Saklanan düzenleme kaydedilmedi",
                    f"Biten iş aynı satırı değiştirdi. Metniniz: {text}",
                    (NoticeAction("Yine de Kaydet", partial(self._commit_board_edit, row_id, text)),),
                )

    def recheck_board_rows(self, changed: Sequence[TranslationRow], *, keep_terms: bool = False) -> None:
        """Düzenlenen satırları ve aynı kaynaklı satırları (tutarsızlık değişir) panoda yerinde yeniden denetler.

        Terimler tüm projeden çıkarılır (tek satırdan çıkmaz); sayaç ve adım çubuğu güncellenir. `keep_terms`:
        terimleri yeniden çıkarmak (tüm projeyi taramak) yerine satırların panodaki terim bulguları korunur;
        biçim düzeltmeleri terim bulgusunu değiştirmez, tazesi sonraki tam denetimde gelir. Arka plan işi açmaz.
        """
        planned = self._board_recheck_job(changed, keep_terms=keep_terms)
        if planned is not None:
            self._show_board_recheck(planned[0], planned[1]())

    def _board_recheck_job(
        self, edited: Sequence[TranslationRow], *, keep_terms: bool = False
    ) -> tuple[list[TranslationRow], Callable[[], dict[int, list[QaIssue]]]] | None:
        """Düzenlenen satırlar ve aynı kaynaklı satırlar için denetim işi: (satırlar, bulguları döndüren iş).

        Durum bu iş parçacığında okunur, iş her iş parçacığında çalışabilir. Kontrol Et hiç çalıştırılmadıysa
        yapılacak bir şey yoktur (`None`).
        """
        if self.qa_count is None or self.qa_count[0] is not self._win.project:
            return None
        all_rows = list(self._win.translate_page.model.rows)
        sources = {r.source for r in edited if r.source.strip()}
        ids = {r.id for r in edited}
        group = [r for r in all_rows if r.id in ids or r.source in sources]
        group_ids = {r.id for r in group}
        glossary = self._win.project.glossary()
        ignored_terms = self._win._terms_ignored()
        missing, transliterate, fit = (
            self._win._missing_letters(),
            self._win._transliterate_letters(),
            self._win._fit_config(),
        )
        spell, spell_ignored = self._win.spell, self._win._spell_ignored()
        widths = self._win._width_measure()
        profanity = self._win._profanity_config()
        kept = (
            [i for i in self._win.qa_page.all_issues() if i.kind == "term" and i.row_id in group_ids]
            if keep_terms
            else []
        )

        def job() -> dict[int, list[QaIssue]]:
            issues = run_qa_checks(
                group,
                missing,
                transliterate,
                glossary,
                fit,
                spell=spell,
                ignored_terms=ignored_terms,
                spell_ignored=spell_ignored,
                terms={} if keep_terms else project_terms(all_rows, glossary, ignored_terms),
                widths=widths,
                profanity=profanity,
            )
            by_row: dict[int, list[QaIssue]] = {}
            for issue in [*issues, *kept]:
                by_row.setdefault(issue.row_id, []).append(issue)
            return by_row

        return group, job

    def _show_board_recheck(self, group: list[TranslationRow], by_row: dict[int, list[QaIssue]]) -> None:
        """Yeniden denetlenen satırların bulgularını panoya verir; yok sayılanlar burada da ayrılır."""
        self._replace_board_rows(group, by_row)
        self._recount_qa()

    def _replace_board_rows(self, rows: list[TranslationRow], by_row: dict[int, list[QaIssue]]) -> None:
        entries = ignored.load(self._win.project.setting(ignored.IGNORED_KEY))
        by_id = {r.id: r for r in rows}
        shown: dict[int, list[QaIssue]] = {}
        hidden: dict[int, list[QaIssue]] = {}
        for row_id, found in by_row.items():
            shown[row_id], hidden[row_id] = ignored.split(found, by_id, entries)
        self._win.qa_page.replace_rows_issues(shown, rows, hidden)

    def sync_ignored_to_translate(self) -> None:
        """Projedeki yok sayılan bulguları Çevir tablosuna bildirir (anlık denetim de onları göstermesin)."""
        self._win.translate_page.set_ignored(ignored.load(self._win.project.setting(ignored.IGNORED_KEY)))

    def _split_ignored(
        self, issues: list[QaIssue], rows: Sequence[TranslationRow]
    ) -> tuple[list[QaIssue], list[QaIssue]]:
        """Bulguları (gösterilecek, yok sayılan) diye ayırır; yok sayma çeviri değişince kendiliğinden geçersiz olur."""
        entries = ignored.load(self._win.project.setting(ignored.IGNORED_KEY))
        return ignored.split(issues, {r.id: r for r in rows}, entries)

    def ignore_issues(self, pairs: list[tuple[int, str]]) -> None:
        """Seçili bulguları yok sayar (kalıcı; hata bulguları yok sayılamaz)."""
        rows = {r.id: r for r in self._win.translate_page.model.rows}
        entries = ignored.add(ignored.load(self._win.project.setting(ignored.IGNORED_KEY)), pairs, rows)
        self._store_ignored_issues(entries, {row_id for row_id, _kind in pairs})
        self._win.statusBar().showMessage(f"{format_int(len(pairs))} bulgu yok sayıldı.", 5000)

    def unignore_issues(self, pairs: list[tuple[int, str]]) -> None:
        """Yok sayılan bulguları listeye geri getirir."""
        entries = ignored.remove(ignored.load(self._win.project.setting(ignored.IGNORED_KEY)), pairs)
        self._store_ignored_issues(entries, {row_id for row_id, _kind in pairs})
        self._win.statusBar().showMessage(f"{format_int(len(pairs))} bulgu yeniden gösterildi.", 5000)

    def _store_ignored_issues(self, entries: set[ignored.Entry], row_ids: set[int]) -> None:
        self._win.project.set_setting(ignored.IGNORED_KEY, ignored.dump(entries))
        self._win._mark_changed()
        self._win.translate_page.set_ignored(entries)  # Çevir'deki işaret de hemen kalkar (ya da geri gelir)
        rows = [r for r in self._win.translate_page.model.rows if r.id in row_ids]
        by_row: dict[int, list[QaIssue]] = {}
        for issue in self._win.qa_page.all_issues():
            if issue.row_id in row_ids:
                by_row.setdefault(issue.row_id, []).append(issue)
        self._replace_board_rows(rows, by_row)
        self._recount_qa()

    def recheck_board_later(self, edited: Sequence[TranslationRow]) -> None:
        """`_recheck_board_rows`un arka plan sürümü: çok satır değişince (toplu düzeltme) arayüz beklemez.

        Aynı anda tek denetim çalışır; sürerken gelen satırlar sonrakine eklenir. Sonuç, proje ya da denetim
        sonucu bu arada değiştiyse atılır.
        """
        if self.board_task is not None:
            self.board_pending.update({r.id: r for r in edited})
            return
        planned = self._board_recheck_job(edited)
        if planned is None:
            return
        group, job = planned
        project = self._win.project
        result: dict[str, dict[int, list[QaIssue]]] = {}

        def done(value: object) -> None:
            assert isinstance(value, dict)
            result["by_row"] = value

        def finished() -> None:
            task, self.board_task = self.board_task, None
            if task is not None:
                release_thread(task)
            if "by_row" in result and self._win.project is project and self.qa_count is not None:
                current = {r.id: r for r in self._win.translate_page.model.rows}
                if all(current.get(r.id) is r for r in group):
                    self._show_board_recheck(group, result["by_row"])
                else:  # satırlar bu arada değişti (ör. Geri Al): bu sonuç eski, güncel satırlar yeniden denetlenir
                    self.board_pending.update({r.id: current[r.id] for r in group if r.id in current})
            pending, self.board_pending = list(self.board_pending.values()), {}
            if pending:
                self._win._recheck_board_later(pending)

        task = Task(lambda _ctx: job(), "Denetim yenileniyor")
        self.board_task = task
        task.succeeded.connect(done)
        task.finished.connect(finished)
        task.start()

    def _recount_qa(self) -> None:
        """Panodaki bulgulardan Kontrol Et sayacını ve adım çubuğunu yeniler (Kontrol Et çalıştırılmışsa)."""
        if self.qa_count is None or self.qa_count[0] is not self._win.project:
            return
        counted = [i for i in self._win.qa_page.active_issues() if i.severity in (SEVERITY_ERROR, SEVERITY_WARNING)]
        self.qa_count = (self._win.project, len(counted))
        self.qa_errors = any(i.severity == SEVERITY_ERROR for i in counted)
        self._win._refresh_nav()

    def spell_ignored(self) -> list[str]:
        """Bu projede yazım bulgusu üretmeyecek sözcükler (ayar bozuksa boş, günlüğe uyarı)."""
        return parse_word_list(self._win.project.setting(SPELL_IGNORED_KEY), SPELL_IGNORED_KEY)

    def terms_ignored(self) -> list[str]:
        """Bu projede "terim değil" denen ifadeler (ayar bozuksa boş, günlüğe uyarı)."""
        return parse_word_list(self._win.project.setting(TERMS_IGNORED_KEY), TERMS_IGNORED_KEY)

    def profanity_config(self) -> ProfanityConfig:
        """Bu projenin küfür / argo denetimi ayarı (düzey yok ya da bozuksa kapalı; izin listesi bozuksa boş)."""
        project = self._win.project
        allowed = parse_word_list(project.setting(PROFANITY_ALLOWED_KEY), PROFANITY_ALLOWED_KEY)
        return ProfanityConfig(
            parse_level(project.setting(PROFANITY_LEVEL_KEY)), frozenset(turkish_lower(w) for w in allowed)
        )

    def set_profanity_level(self, level: str) -> None:
        """Araçlar → Küfür / Argo Denetimi: düzeyi projeye yazar; anlık denetim ve Kontrol Et sonucu yenilenir."""
        level = parse_level(level)
        if level == self.profanity_config().level:
            return
        self._win.project.set_setting(PROFANITY_LEVEL_KEY, level)
        self._win._mark_changed()
        self._win.statusBar().showMessage(f"Küfür / argo denetimi: {PROFANITY_LEVELS[level]}.", 5000)
        self._win._sync_live()
        self._win._recheck_if_done()

    def allow_profanity_words(self, words: list[str]) -> None:
        """Sorunlar panosunda "Bu kelime argo değil": sözcükler bu projede küfür / argo bulgusu üretmez."""
        current = [
            turkish_lower(w)
            for w in parse_word_list(self._win.project.setting(PROFANITY_ALLOWED_KEY), PROFANITY_ALLOWED_KEY)
        ]
        self._store_ignored(PROFANITY_ALLOWED_KEY, current, [turkish_lower(str(w)) for w in words])
        self._win.statusBar().showMessage(f"{format_int(len(words))} sözcük argo sayılmayacak.", 5000)
        self._win._sync_live()
        self._win._recheck_if_done()

    def _store_ignored(self, key: str, current: list[str], additions: list[str]) -> None:
        merged = list(dict.fromkeys([*current, *additions]))
        self._win.project.set_setting(key, json.dumps(merged, ensure_ascii=False))
        self._win._mark_changed()

    def recheck_if_done(self) -> None:
        """Kontrol Et sonucu varsa (ayar değiştiği için) denetimi arka planda yeniler.

        Büyük projede tam denetim uzun sürer; arayüz donmaz. Başka bir iş sürüyorsa o bitince yenilenir.
        """
        if self.qa_count is None or self.qa_count[0] is not self._win.project:
            return
        if self._win.busy:
            self.recheck_pending = True
            return
        self.recheck_pending = False
        self._win._fit_recheck_timer.stop()
        self._win._run_full_check("Denetim yenileniyor")

    def ignore_terms(self, phrases: list[str]) -> None:
        """Sorunlar panosunda "Terim değil": ifadeler projede terim sayılmaz, denetim yenilenir."""
        self._store_ignored(TERMS_IGNORED_KEY, self._win._terms_ignored(), [str(p) for p in phrases])
        self._win.statusBar().showMessage(f"{format_int(len(phrases))} ifade terim sayılmayacak.", 5000)
        self._win._recheck_if_done()

    def ignore_spell_words(self, words: list[str]) -> None:
        """Yazım Denetimi penceresinde "Yoksay": sözcükler bu projede yazım bulgusu üretmez."""
        self._store_ignored(SPELL_IGNORED_KEY, self._win._spell_ignored(), [str(w) for w in words])
        self._win._sync_spell()  # canlı denetim, editör ve tablodaki yazım çizgisi, pencere
        self._win._recheck_if_done()

    def apply_ascii_choice(self, key: str, new: str) -> None:
        """Belirsiz sözcük için seçilen yazımı projedeki bütün çevirilere uygular; tek iştir, Geri Al hepsini alır.

        Yalnızca tam sözcükler değişir; orijinalde geçen sözcüğe ve cümle ortasındaki özel ada dokunulmaz. Onaylı
        satırlar onaylı kalır. Değişen satırlar panoda yerinde yeniden denetlenir.
        """
        if self._win.busy:
            self._win.statusBar().showMessage("Bir iş sürerken değiştirilemez; iş bitince yeniden deneyin.", 5000)
            return
        changes = []
        for row in self._win.translate_page.model.rows:
            text = apply_choice(row.source, row.translation, key, new)
            if text != row.translation:
                changes.append((row.id, text))
        if not changes:
            self._win.statusBar().showMessage("Değiştirilecek satır bulunamadı.", 5000)
            return
        rows = self._win._replace_translations(changes)
        if rows is None:
            return  # neden Çevir sayfasında bildirildi
        self._win.statusBar().showMessage(f"{format_int(len(changes))} satırda değiştirildi.", 5000)

    def write_row_changes(
        self, plan: list[tuple[int, str]], rows: list[TranslationRow], job_id: str
    ) -> list[TranslationRow]:
        """Düzeltmeleri satırların durumunu koruyarak yazar (onaylı onaylı, redakte redakte, diğerleri makine kalır).

        Biçim düzeltmesi yeni çeviri değildir: çeviri belleğine yazılmaz.
        """
        status = {r.id: r.status for r in rows}
        groups: dict[str, list[tuple[int, str]]] = {}
        for entry_id, text in plan:
            groups.setdefault(status[entry_id], []).append((entry_id, text))
        updated: list[TranslationRow] = []
        for kind, changes in groups.items():
            if kind == Status.APPROVED:
                updated += self._win.project.set_translations(changes, job=job_id, remember=False)
            elif kind == Status.REDACTED:
                updated += self._win.project.set_translations(
                    changes, status=Status.REDACTED, job=job_id, remember=False
                )
            else:
                updated += self._win.project.set_translations(changes, machine=True, job=job_id, remember=False)
        return updated

    def _fix_settings(self) -> FixSettings:
        """Düzeltmenin ve düzeltme bildiriminin ortak ayarları (şimdi, ana iş parçacığında okunur)."""
        return FixSettings(
            self._win._missing_letters(),
            self._win._transliterate_letters(),
            self._win.project.glossary(),
            self._win._fit_config(),
            self._win.spell,
            self._win._terms_ignored(),
            self._win._spell_ignored(),
        )

    def plan_fix_bar(self, rows: list[TranslationRow], issues: list[QaIssue], kinds: list[str]) -> FixPlan:
        """Sorunlar panosundaki "N satır düzeltilebilir" bildiriminin planı; Düzelt aynı kuralla çalışır."""
        return plan_for_issues(rows, issues, kinds, self._fix_settings())

    def apply_fixes(self, kinds: list[str], row_ids: list[int]) -> None:
        """Seçilen türlerdeki bulguları düzeltir (`row_ids` boşsa panodaki tüm bulgular); tek iş olarak geçmişe yazılır.

        Onaylı satırlar da düzelir ve onaylı kalır. Yalnızca bulgusu olan satırlar yeniden denetlenir (tüm proje
        değil); çok satır varsa denetim ve plan arka plan işinde çalışır, arayüz donmaz. Rapor “Son İşin
        Değişiklikleri” penceresidir.
        """
        if not kinds:
            return
        if self._win.busy:
            self._win.qa_page.show_fix_result("warning", "Bir iş sürerken düzeltilemez; iş bitince yeniden deneyin.")
            return
        settings = self._fix_settings()
        if row_ids:
            wanted: set[int] | None = set(row_ids)
        elif self.qa_count is not None and self.qa_count[0] is self._win.project:
            wanted = {i.row_id for i in self._win.qa_page.active_issues() if i.kind in kinds}
        else:
            wanted = None  # hiç denetlenmemiş: tüm satırlar
        rows = [r for r in self._win.translate_page.model.rows if wanted is None or r.id in wanted]
        if len(rows) <= FIX_SYNC_ROWS:
            self._write_fixes(rows, plan_for_rows(rows, kinds, settings))
            return
        project = self._win.project

        def work(_ctx: TaskContext) -> object:
            return plan_for_rows(rows, kinds, settings)

        def done(result: object) -> None:
            if self._win.project is project:
                assert isinstance(result, FixPlan)
                self._write_fixes(rows, result)

        self._win._run(
            work,
            "Düzeltmeler hazırlanıyor",
            on_success=done,
            on_failure=lambda text: self._win.qa_page.show_fix_result("danger", text),
        )

    def _write_fixes(self, rows: list[TranslationRow], plan: FixPlan) -> None:
        """Planı tek iş olarak yazar, değişen satırları yerinde yeniler ve sonucu bildirir."""
        page = self._win.qa_page
        notes = []
        if plan.unfixed:
            notes.append(f"{format_int(plan.unfixed)} satır düzeltilemedi (anlam gerektiriyor); elle bakın.")
        if plan.empty:
            if plan.unfixed:
                page.show_fix_result(
                    "warning",
                    "Kendiliğinden düzeltilemedi. "
                    f"{format_int(plan.unfixed)} satır anlam gerektiriyor; sağ tıklayıp doğru yazımı seçin "
                    "ya da elle düzeltin.",
                )
            else:
                page.show_fix_result("warning", "Düzeltilecek bir şey bulunamadı.")
            return
        job_id = new_job_id("autofix")
        try:
            updated = self._win._write_row_changes(plan.changes, rows, job_id)
        except NxError as exc:
            page.show_fix_result("danger", exc.user_text())
            return
        self._win._mark_changed()
        self._update_rows_handled(updated)
        self._win._set_last_job(job_id)
        self._win._refresh_marks()
        self._win._fix_report = (job_id, {i: ", ".join(KIND_LABELS[k] for k in ks) for i, ks in plan.applied.items()})
        if len(updated) <= FIX_RECHECK_ROWS:
            if self.qa_count is not None and self.qa_count[0] is self._win.project:
                self._win._recheck_board_rows(updated, keep_terms=True)
        else:
            page.mark_checking()  # bulgu listesi ve çubuk eskidi: arka plandaki tam denetim bitene dek gösterilmez
            self._win._recheck_if_done()
        page.show_fix_result(
            "success", " ".join([f"{format_int(len(plan.changes))} satır düzeltildi.", *notes]), "Raporu Gör"
        )

    # --- sığdırma ve anlık denetim -----------------------------------------------------------

    def _refresh_qa(self) -> None:
        win = self._win
        notes = registry.font_support_notes((title_id, kind) for _path, title_id, kind in win.project.text_files())
        win.qa_page.show_font_report(win.font_report, win.project.setting("font_missing"), notes)
        win.qa_page.set_font_overrides(win._stored_font_overrides())
        win.qa_page.set_font_patch(win.project.setting("font_patch") == "1", win._patchable_letters())
        mode = win.project.setting("transliterate_mode", transliterate.MODE_NONE)
        win.qa_page.set_mode(mode, win._missing_letters(), win._font_patch_on())
        config = win._fit_config()
        win.qa_page.set_fit(config, *win._fit_lists())
        win.qa_page.set_width_font(win._width_table())
        win._refresh_limits()
        win._sync_live()

    def _rows_replaced(self) -> None:
        """Çeviri satırları yeniden kuruldu: satırlara bağlı önbellekler geçersiz.

        Genişlik denetimi açıksa kutular yeni orijinallerden hesaplanıp anlık denetime verilir."""
        self._win._rows_version += 1
        if self._win._fit_config().has_width_rules:
            self._win._sync_live()

    def _width_table(self) -> WidthTable:
        """Genişlik ölçümünün tablosu: fontlar tarandıysa oyunun fontu, yoksa yaklaşık tablo (ayar metnine bağlı)."""
        win = self._win
        text = win.project.setting(SETTING_WIDTHS)
        cached = win._width_table_cache
        if cached is None or cached[0] != text:
            cached = (text, load_table(text))
            win._width_table_cache = cached
        return cached[1]

    def _width_measure(self) -> WidthMeasure | None:
        """Fontla genişlik ölçümü (kapsam kutuları tüm satırlardan); hiçbir kapsamda açık değilse `None`.

        Kutular yalnızca orijinallere bağlıdır: satırlar yeniden kurulana, ayar ya da tablo değişene dek aynı nesne
        döner (anlık denetim bağlamı kimlikle karşılaştırılır, önbelleği boşalmaz). Yalnızca pay değiştiyse kutular
        yeniden ölçülmez."""
        win = self._win
        config = win._fit_config()
        if not config.has_width_rules:
            return None
        table = win._width_table()
        cached = win._width_cache
        if cached is not None and cached[0] == win._rows_version and cached[2] is table:
            if cached[1] == config:
                return cached[3]
            if box_shape(cached[1]) == box_shape(config):
                measure = WidthMeasure(config, table, cached[3].boxes)
                win._width_cache = (win._rows_version, config, table, measure)
                return measure
        measure = build_measure(win.translate_page.model.rows, config, table)
        win._width_cache = (win._rows_version, config, table, measure)
        return measure

    def _fit_lists(self) -> tuple[list[str], list[str], list[str]]:
        """Sığdırma sekmesinin dosya, kod etiketi ve grup listeleri (satırlar değişmedikçe önbellekten)."""
        win = self._win
        cached = win._fit_lists_cache
        if cached is None or cached[0] != win._rows_version:
            rows = win.translate_page.model.rows
            cached = (
                win._rows_version,
                sorted({r.file for r in rows}),
                sorted({code for r in rows for code in r.code_labels}),
                list(separate_groups(rows)),
            )
            win._fit_lists_cache = cached
        return cached[1], cached[2], cached[3]

    def _refresh_limits(self) -> None:
        """Sınırlar tablosunu doldurur; istatistik ve öğrenme tüm satırları taradığı için yalnızca Sığdırma sekmesi
        görünürken ve satırlar ya da öğrenmeyi etkileyen ayar değiştiyse yapılır."""
        win = self._win
        if not win.qa_page.fit_tab_visible():
            return
        config = win._fit_config()
        key = (
            win._rows_version,
            config.default,
            sorted(config.per_file.items()),
            config.kinds.dump(),
        )
        limits = win.qa_page.limits
        if key == win._limits_key:
            limits.set_config(config)
            return
        rows = win.translate_page.model.rows
        limits.set_data(rows, config, learn_group_rules(rows, config))
        win.qa_page.show_kind_warnings(suspected_line_breaks(((r.source, r.code_labels) for r in rows), config.kinds))
        win._limits_key = key

    def _push_fit_to_page(self) -> None:
        """Çeviri sayfasına sığdırma ayarını ve kod türlerini verir (panel sayacı ve çipler)."""
        win = self._win
        win.translate_page.set_fit_config(win._fit_config())
        win.translate_page.set_manual_limit(win._manual_limit())
        win._sync_live()

    def _load_live_kinds(self) -> frozenset[str]:
        """Ayarlardaki anlık denetim türleri (bozuk ya da yoksa hepsi)."""
        return parse_live_kinds(self._win.settings.value(LIVE_KINDS_KEY, None))

    def _sync_live(self, force: bool = False) -> None:
        """Anlık denetimin bağlamını proje, font, sözlük, sığdırma, yazım denetleyicisi ve seçili türlerle kurar.

        Bağlam değişmediyse tablo yenilenmez (büyük projede tüm hücreleri yeniden çizdirmek pahalıdır); yazım
        denetleyicisinin içi değiştiyse (sözcük eklendi) `force` verilir.
        """
        win = self._win
        context = LiveContext(
            missing_letters=win._missing_letters(),
            transliterated=win._transliterate_letters(),
            glossary=tuple(win.project.glossary()),
            fit=win._fit_config(),
            spell=win.spell,
            kinds=win._live_kinds,
            spell_ignored=frozenset(turkish_lower(w) for w in win._spell_ignored()),
            widths=win._width_measure(),
            profanity=win._profanity_config(),
        )
        if not force and context == win._live_context:
            return
        win._live_context = context
        win.translate_page.set_live_context(context)

    def _apply_spell_copied(self) -> None:
        """Kayıtlı "orijinalden kopyalanan sözcükleri de işaretle" tercihini yazım denetleyicisine uygular."""
        win = self._win
        if win.spell is not None:
            win.spell.flag_copied = str(win.settings.value(KEY_SPELL_COPIED, "0")) == "1"

    def _set_spell_copied(self, on: bool) -> None:
        win = self._win
        win.settings.setValue(KEY_SPELL_COPIED, "1" if on else "0")
        win._apply_spell_copied()
        win._sync_spell()
        win._recheck_if_done()

    def _set_live_kinds(self, kinds: list[str]) -> None:
        win = self._win
        win._live_kinds = frozenset(kinds)
        win.settings.setValue(LIVE_KINDS_KEY, format_live_kinds(kinds))
        win._sync_live()

    def _manual_limit(self) -> int:
        """Projenin kayıtlı "Elle sınır"ı (0: kapalı)."""
        try:
            return max(int(self._win.project.setting(MANUAL_LIMIT_KEY, "0")), 0)
        except ValueError:
            return 0

    def _save_manual_limit(self, limit: int) -> None:
        self._win.project.set_setting(MANUAL_LIMIT_KEY, str(limit))

    def _fit_config(self) -> FitConfig:
        """Projenin kayıtlı sığdırma ayarı (sınır yoksa denetim ve düzeltme sığdırma yapmaz)."""
        return load_config(self._win.project)

    def _save_fit(self) -> None:
        win = self._win
        try:
            save_config(win.project, win.qa_page.fit_config())
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return
        win._push_fit_to_page()
        win._mark_changed()
        if win._qa_count is not None and win._qa_count[0] is win.project:
            # Daha önce denetlendiyse yeni ayarın etkisi kendiliğinden görünür; hiç denetlenmediyse başlatılmaz.
            win.qa_page.show_fit_checking()
            win._fit_recheck_timer.start()

    def _fit_recheck_due(self) -> None:
        self._win._recheck_if_done()

    def _learn_rules(self, scope: str) -> None:
        """Kapsamdaki (proje, dosya ya da grup) orijinal metinlerden sınır önerir; öneri kaydedilmez.

        "Her grup ayrı" kapsamında her grubun sınırı ayrı öğrenilir ve hemen kaydedilir.
        """
        win = self._win
        config = win.qa_page.fit_config()
        all_rows = win.translate_page.model.rows
        if scope == EACH_GROUP:
            learned = learn_group_rules(all_rows, config)
            win.qa_page.show_learned_groups(learned)
            win.qa_page.limits.set_learned(learned)
            return
        if scope.startswith(GROUP_PREFIX):
            group = scope[len(GROUP_PREFIX) :]
            rows = [r for r in all_rows if row_group(r) == group]
            current = config.per_group.get(group) or config.default
        else:
            rows = [r for r in all_rows if not scope or r.file == scope]
            current = config.rules_for(scope) if scope else config.default
        if current is None:
            rules = learn_rules(rows, config.kinds)
        else:
            rules = learn_rules(rows, config.kinds, current.variable_width)
        win.qa_page.show_learned(rules)
