"""Kontrol Et denetleyicisi: denetim, pano yenileme, yok sayma, Düzelt ve aday seçimi.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 219). Denetleyici pencereyi bilir; pencerenin
durumunu (proje, sayfalar, iş) her çağrıda pencereden okur ve pencerede yönlendirmesi olan bir yöntemi
pencere üzerinden çağırır (`self._win.<ad>`): testler pencerenin yöntemlerini değiştirerek çalışır,
bağlı yöntem önceden saklanırsa değiştirilen yol sınanmaz. Sinyal bağlantıları ve kısayollar pencerede kalır.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from nxceviri.core.errors import NxError
from nxceviri.core.progress import ProgressCallback, TaskContext
from nxceviri.core.project import Project, TranslationRow
from nxceviri.core.qa import ignored
from nxceviri.core.qa.asciitr import apply_choice
from nxceviri.core.qa.autofix import FixPlan
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_ERROR, SEVERITY_WARNING, QaIssue, parse_word_list
from nxceviri.core.qa.checks import run_checks as run_qa_checks
from nxceviri.core.qa.fixrun import FixSettings, plan_for_issues, plan_for_rows
from nxceviri.core.qa.terms import project_terms
from nxceviri.core.translate.status import Status
from nxceviri.gui.jobs import new_job_id
from nxceviri.gui.notify import LEVEL_INFO, LEVEL_SUCCESS, NoticeAction
from nxceviri.gui.step_nav import STEP_QA
from nxceviri.gui.tasks import Task, release_thread
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

#: Proje ayarları: yazım denetiminde yoksayılan sözcükler ve "terim değil" denen ifadeler (JSON listesi).
SPELL_IGNORED_KEY = "spell_ignored"
TERMS_IGNORED_KEY = "terms_ignored"
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
        self.recheck_pending = False

    def _checks_job(self, rows: list[TranslationRow]) -> Callable[[ProgressCallback | None], list[QaIssue]]:
        """Denetimi `rows` üzerinde çalıştıran işlev (isteğe bağlı ilerleme geri çağrısı alır); ayarlar şimdi okunur
        (iş parçacığı veritabanına dokunmaz)."""
        missing, transliterated = self._win._missing_letters(), self._win._transliterate_letters()
        glossary, fit, spell = self._win.project.glossary(), self._win._fit_config(), self._win.spell
        ignored_terms, spell_ignored = self._win._terms_ignored(), self._win._spell_ignored()

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
            on_cancel=self._win.qa_page.stop_checking,
        )
        self.check_task = self._win.task

    def stop_checks(self) -> None:
        """Durdur: sürmekte olan denetim işini iptal eder (başka bir iş sürüyorsa dokunmaz)."""
        if self._win.task is not None and self._win.task is self.check_task:
            self._win.task.cancel()

    def show_check_results(self, issues: list[QaIssue], rows: list[TranslationRow]) -> list[QaIssue]:
        """Denetim sonucunu panoya verir (tek yer: yok sayılanlar burada ayrılır); gösterilen bulguları döndürür."""
        self._win._sync_live()  # Çevir'deki anlık denetim bağlamı Kontrol Et'in kullandığı güncel ayarlarla aynı olsun
        self._win.qa_page.set_code_kinds(self._win._fit_config().kinds)
        issues, hidden = self._split_ignored(issues, rows)  # yok sayılanlar listeye, sayaca ve Çevir'e girmez
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
            self._win.qa_page.show_fix_result("warning", "Bir iş sürerken düzenlenemez; iş bitince yeniden deneyin.")
            return
        try:
            rows = self._win._commit_translations([(row_id, text)])
        except NxError as exc:
            self._win.qa_page.show_fix_result("danger", exc.user_text())
            return
        if not rows:
            return
        self._win.translate_page.model.update_rows(rows)
        self._win._recheck_board_rows(rows)

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
        self._win._recheck_board_later(rows)

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
        self._win.translate_page.model.update_rows(updated)
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
