"""Ana pencere: adım gezgini, menüler, proje yönetimi ve arka plan görevleri."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import httpx
from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, QUrl, QVariantAnimation
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from nxceviri import __version__
from nxceviri.arac.teshis import RAPOR_ADI, UYARI, rapor_uret
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
from nxceviri.core.formats.registry import BUILTIN_PLUGINS, user_plugin_report
from nxceviri.core.formats.scanner import ScanReport
from nxceviri.core.keys import KeySet, load_keys, load_title_keys
from nxceviri.core.pipeline import (
    Inputs,
    TextExtraction,
    check_sources,
    clear_cache,
    default_cache_dir,
    dir_size,
    extract_sources,
    extract_texts,
    is_supported_file,
    opened_view,
    read_source,
    scan_sources,
    version_warnings,
)
from nxceviri.core.plugins.record import plugin_warnings, record_extraction
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import PROJECT_SUFFIX, Change, Project, SourceRecord, TranslationRow, row_group
from nxceviri.core.qa import transliterate
from nxceviri.core.qa.autofix import plan_fixes, plan_reflow
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_ERROR, SEVERITY_WARNING, glossary_words
from nxceviri.core.qa.checks import run_checks as run_qa_checks
from nxceviri.core.qa.fonts import FontReport
from nxceviri.core.qa.fonts import scan_fonts as scan_font_files
from nxceviri.core.secrets import DEEPL_API_KEY, GITHUB_UPDATE_KEY, KeyringStore, SecretStore
from nxceviri.core.selfupdate import PreparedInstall, current_install, discard_prepared, launch_installer
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.loader import load_spell_checker
from nxceviri.core.spell.userdict import UserDictionary, default_user_dictionary_path
from nxceviri.core.translate.csvio import (
    CsvError,
    export_translation_txt,
    export_translation_xlsx,
    export_txt,
    export_xlsx,
    plan_import,
    prepare_correction,
    read_revision_file,
)
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
from nxceviri.core.translate.glossary_io import merge_terms
from nxceviri.core.translate.port import ReadyTranslations, port_translations, read_ready_translations
from nxceviri.core.translate.probe import deepl_summary, ollama_summary
from nxceviri.core.translate.providers.base import ProviderError, TranslationProvider
from nxceviri.core.translate.providers.deepl import DeepLProvider
from nxceviri.core.translate.providers.ollama import DEFAULT_URL, OllamaProvider
from nxceviri.core.translate.report import job_label, mark_label
from nxceviri.core.translate.runner import (
    ACTION_REVISE,
    ACTION_TRANSLATE,
    MachineJob,
    RunSummary,
    target_rows,
)
from nxceviri.core.translate.status import TRANSLATED_STATUSES, Status
from nxceviri.core.translate.terms import TermSuggestion, find_candidates, suggest_glossary
from nxceviri.core.translate.uppercase import UppercaseRules
from nxceviri.core.update import (
    GitHubUpdater,
    UpdateError,
    UpdateInfo,
    Updater,
    app_root,
    is_git_checkout,
    is_packaged,
    make_updater,
    relaunch,
)
from nxceviri.gui.add_game_page import AddGamePage
from nxceviri.gui.changes_dialog import ChangesDialog
from nxceviri.gui.csv_dialog import FORMAT_TXT, MODE_REDACTION, MODE_TRANSLATION, CsvExportDialog
from nxceviri.gui.export_page import ExportPage
from nxceviri.gui.jobs import JOB_TITLES, describe_summary, new_job_id, run_and_close
from nxceviri.gui.machine_dialogs import (
    PROVIDER_DEEPL,
    PROVIDER_OLLAMA,
    SCOPE_ALL,
    SCOPE_FILTERED,
    SCOPE_GROUPS,
    SCOPE_SELECTED,
    GlossaryDialog,
    MachineDialog,
    MachineSettings,
    ProviderSettingsDialog,
    TermSuggestionsDialog,
    make_provider,
)
from nxceviri.gui.motion import animations_enabled
from nxceviri.gui.plugins_dialog import PluginsDialog
from nxceviri.gui.provider_probe import ProviderProbe
from nxceviri.gui.qa_page import QaPage
from nxceviri.gui.recent import RecentProjects
from nxceviri.gui.recovery import RecoveryFile, RecoveryKeeper, default_recovery_dir, discard, leftover_files
from nxceviri.gui.scan_page import ScanPage
from nxceviri.gui.spell_dialogs import AddSpellWordsDialog, UserDictionaryDialog
from nxceviri.gui.statusbar import StatusSegments
from nxceviri.gui.step_nav import COLLAPSED_WIDTH, ProjectHeader, StepNav
from nxceviri.gui.tasks import Task
from nxceviri.gui.theme import (
    DEFAULT_FONT_SIZE,
    FONT_SIZES,
    THEME_LABELS,
    ThemeMode,
    apply_theme,
    clamp_font_size,
)
from nxceviri.gui.translate_page import TranslatePage
from nxceviri.gui.update_dialog import UpdateDialog, UpdaterFactory, auto_check_enabled
from nxceviri.gui.widgets import button, format_int, format_size, tip_html

log = logging.getLogger(__name__)

APP_TITLE = "NXTR"
STEP_ADD = 0
STEP_SCAN = 1
STEP_TRANSLATE = 2
STEP_QA = 3
STEP_EXPORT = 4
#: Proje ayarı: son kullanılan redaksiyon talimatı (pencere bir sonraki açılışta bunu önerir).
REVISE_INSTRUCTION_KEY = "revise_instruction"
TRANSLATE_INSTRUCTION_KEY = "translate_instruction"


#: Kaydedilmemiş projenin kurtarma kopyasının yenilenme aralığı.
RECOVERY_INTERVAL_MS = 60_000
#: Bu genişlikten dar pencerede kenar çubuğu ilk açılışta daralmış başlar.
NAV_AUTO_COLLAPSE_BELOW = 1000
#: Kenar çubuğu daralma/açılma animasyonunun süresi (ms).
NAV_ANIMATION_MS = 150
#: Sağlayıcı durumu sorgularının zaman aşımı (sn); arka plandadır ama ipucunu uzun bekletmez.
PROBE_TIMEOUT_S = 2.0


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NXCeviri" / "logs"


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings) -> None:
        super().__init__()
        self.settings = settings
        self.keys: KeySet | None = None
        self.title_keys: dict[bytes, bytes] | None = None
        self.title_keys_path: Path | None = None
        self._keys_detail = ""
        self.sources: list[SourceRecord] = []
        self.report: ScanReport | None = None
        self.project = Project.new()
        self.dirty = False
        self.task: Task | None = None
        self.font_report: FontReport | None = None
        self.last_export: Path | None = None
        #: Son denetimin (proje, hata+uyarı sayısı); başka projeye geçilince eskimiş sayılır.
        self._qa_count: tuple[Project, int] | None = None
        self._qa_errors = False
        #: Kalıcı kullanıcı sözlüğü ve Türkçe yazım denetleyicisi (paketlenen süzgeç eksikse None: denetim kapalı).
        self.user_dictionary = UserDictionary(default_user_dictionary_path())
        self.spell: SpellChecker | None = load_spell_checker(self.user_dictionary)
        #: Testlerde sahte sağlayıcı verebilmek için değiştirilebilir.
        self.secrets: SecretStore = KeyringStore()
        self.provider_factory: Callable[[MachineSettings], TranslationProvider] = lambda s: make_provider(
            s, self.secrets
        )
        #: Testlerde sahte GitHub ve yeniden başlatma verebilmek için değiştirilebilir.
        self.updater_factory: UpdaterFactory = self._default_updater
        self.relauncher: Callable[[Path], None] = relaunch
        self.installer_launcher: Callable[[PreparedInstall, Path], None] = launch_installer
        self.app_root: Path | None = app_root()
        #: Paketlenmiş sürüm: klasörünü çalışırken değiştiremez; yeni sürüm indirilir, kapanınca yardımcı kurar.
        self.packaged = is_packaged()
        self.install_dir: Path | None = current_install() if self.packaged else None
        self._last_job: str | None = None  # son makine işinin kimliği (değişiklikler penceresi için)
        self.changes_dialog: ChangesDialog | None = None
        #: Son satır denetimi düzeltmesi: iş kimliği ve satır kimliği → uygulanan düzeltme türleri (rapor sütunu).
        self._fix_report: tuple[str, dict[int, str]] | None = None
        self._update_task: Task | None = None
        self.recent = RecentProjects(settings)
        self.recovery = RecoveryKeeper(default_recovery_dir())
        self._recovery_due = False  # son kopyadan beri değişiklik var mı
        self._recovery_timer = QTimer(self)
        self._recovery_timer.setInterval(RECOVERY_INTERVAL_MS)
        self._recovery_timer.timeout.connect(self.write_recovery)
        self._recovery_timer.start()

        self.setMinimumSize(820, 560)
        self.resize(1180, 780)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.nav_column = QWidget()
        self.nav_column.setObjectName("stepNavColumn")
        column = QVBoxLayout(self.nav_column)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.nav_header = ProjectHeader()
        self.nav = StepNav()
        self._nav_anim: QVariantAnimation | None = None
        self._nav_collapsed = self._initial_nav_collapsed()
        self.nav.set_collapsed(self._nav_collapsed)
        self.nav_header.setVisible(not self._nav_collapsed)
        self.nav.preferred_width_changed.connect(self._update_nav_width)
        column.addWidget(self.nav_header)
        column.addWidget(self.nav, 1)
        root.addWidget(self.nav_column)
        self._update_nav_width()
        self.pages = QStackedWidget()
        self.add_page = AddGamePage()
        self.scan_page = ScanPage()
        self.translate_page = TranslatePage()
        self.translate_page.model.commit = self._commit_translations
        self.translate_page.replace_fn = self._replace_translations
        self.translate_page.bind_settings(self.settings)
        self.pages.addWidget(self.add_page)
        self.pages.addWidget(self.scan_page)
        self.pages.addWidget(self.translate_page)
        self.qa_page = QaPage()
        self.qa_page.bind_settings(self.settings)
        self.export_page = ExportPage()
        self.pages.addWidget(self.qa_page)
        self.pages.addWidget(self.export_page)
        root.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Hazır")
        self.update_badge = button("Yeni sürüm var", icon="download")
        self.update_badge.setToolTip(tip_html("Yeni sürümü görmek ve kurmak için tıklayın."))
        self.update_badge.clicked.connect(self.open_updates)
        self.update_badge.hide()
        self.status_segments = StatusSegments(self.statusBar(), self.update_badge)
        self.status_segments.problems_clicked.connect(self._open_qa_from_status)
        self.status_segments.keys_clicked.connect(self._choose_keys)
        self.status_segments.bind_symbols_action(self.translate_page.view_actions.symbols)
        #: Testlerde sahte HTTP verebilmek için değiştirilebilir.
        self.probe_client_factory: Callable[[], httpx.Client] = lambda: httpx.Client(
            timeout=httpx.Timeout(PROBE_TIMEOUT_S)
        )
        self.provider_probe = ProviderProbe(self, lambda: self.probe_client_factory())  # noqa: PLW0108 (alan sonradan değiştirilebilir)
        self.provider_probe.fetched.connect(self._show_provider_tip)
        self.status_segments.provider_tip_requested.connect(self._probe_provider)
        self._provider_tip_title = ""
        self._pane_focused = False
        pane = self.translate_page.pane
        pane.focus_changed.connect(self._pane_focus_changed)
        pane.cursor_moved.connect(self._pane_cursor_moved)
        # Satırlar tablo modelinde değişince (düzenleme, içe aktarma, otomatik düzeltme) rozetler ve durum çubuğu
        # bir sonraki olay turunda yenilenir: yeni satırlar yazılmadan okunmazlar, art arda değişiklikler tek
        # yenilemeye iner.
        self._derived_timer = QTimer(self)
        self._derived_timer.setSingleShot(True)
        self._derived_timer.setInterval(0)
        self._derived_timer.timeout.connect(self._refresh_derived)
        self.translate_page.view_changed.connect(self._refresh_status)
        self.translate_page.model.modelReset.connect(self._derived_timer.start)
        self.translate_page.model.dataChanged.connect(lambda *_args: self._derived_timer.start())

        self.nav.currentRowChanged.connect(self._go_to)
        self.add_page.choose_keys.connect(self._choose_keys)
        self.add_page.browse_files.connect(self._browse_files)
        self.add_page.add_files.connect(self.add_files)
        self.add_page.remove_source.connect(self._remove_source)
        self.add_page.next_step.connect(self._go_scan)
        self.scan_page.start_scan.connect(self.start_scan)
        self.scan_page.cancel.connect(self._cancel_task)
        self.scan_page.go_back.connect(lambda: self.nav.setCurrentRow(STEP_ADD))
        self.scan_page.report.extract_requested.connect(self._extract)
        self.scan_page.report.diagnosis_requested.connect(self._diagnosis_report)
        self.scan_page.report.rescan_requested.connect(self.start_scan)
        self.scan_page.report.import_requested.connect(self.import_texts)
        self.translate_page.go_to_scan.connect(lambda: self.nav.setCurrentRow(STEP_SCAN))
        self.translate_page.machine_requested.connect(self.start_machine_translation)
        self.translate_page.uppercase_changed.connect(self._save_uppercase)
        self.translate_page.machine_action_requested.connect(lambda a: self.start_machine_translation(a, True))
        self.translate_page.glossary_requested.connect(self.edit_glossary)
        self.translate_page.pane.spell_word_requested.connect(lambda w: self.add_spell_words([w]))
        self.qa_page.add_spelling_requested.connect(self.add_spelling_from_qa)
        self.qa_page.user_dictionary_requested.connect(self.edit_user_dictionary)
        self.translate_page.changes_requested.connect(self.show_job_changes)
        self.translate_page.history_requested.connect(self.show_row_history)
        self.translate_page.unapprove_requested.connect(self.unapprove)
        self.translate_page.reflow_requested.connect(self.reflow_selected)
        self.translate_page.csv_export_requested.connect(self.export_csv)
        self.translate_page.csv_import_requested.connect(self.import_csv)
        self.translate_page.translation_export_requested.connect(self.export_translation)
        self.translate_page.translation_import_requested.connect(self.import_translation)
        self.translate_page.cancel_machine.connect(self._cancel_task)
        self.qa_page.scan_fonts.connect(self.scan_fonts)
        self.qa_page.run_checks.connect(self.run_checks)
        self.qa_page.transliterate_changed.connect(self._set_transliterate)
        self.qa_page.font_patch_changed.connect(self._set_font_patch)
        self.qa_page.open_row.connect(self._open_row)
        self.qa_page.fix_requested.connect(self.apply_fixes)
        self.qa_page.fix_kinds_changed.connect(self._save_fix_kinds)
        self.qa_page.report_requested.connect(self.show_job_changes)
        self.qa_page.fit_changed.connect(self._save_fit)
        self.qa_page.learn_rules_requested.connect(self._learn_rules)
        self.export_page.choose_folder.connect(self._choose_export_folder)
        self.export_page.export_requested.connect(self.export_mod)
        self.export_page.include_errors_changed.connect(self._set_include_errors)
        self.export_page.open_folder.connect(self._open_export_folder)
        self.export_page.cancel.connect(self._cancel_task)

        saved_kinds = self.settings.value("qa/fix_kinds", None)
        if saved_kinds is not None:
            self.qa_page.set_checked_fix_kinds(str(saved_kinds).split(","))
        self._build_menus()
        self._restore_keys()
        self.nav.setCurrentRow(STEP_ADD)
        self._push_fit_to_page()
        self._refresh()

    def _initial_nav_collapsed(self) -> bool:
        """Kayıtlı tercih; yoksa dar pencere ya da dar ekranda daralmış başlar (tercih kaydedilmez)."""
        saved = self.settings.value("ui/nav_collapsed")
        if saved is not None:
            return str(saved) == "1"
        width = self.width()
        screen = self.screen()
        # Offscreen platformun sanal ekranı 800 px'tir; gerçek bir dar ekranı temsil etmez.
        if screen is not None and QGuiApplication.platformName() != "offscreen":
            width = min(width, screen.availableGeometry().width())
        return width < NAV_AUTO_COLLAPSE_BELOW

    def _nav_width(self) -> int:
        return COLLAPSED_WIDTH if self._nav_collapsed else self.nav.preferred_width()

    def _update_nav_width(self) -> None:
        """Kenar çubuğu sütunu en uzun adımı, simgeyi ve rozeti yazı boyutuna göre sığdırır (daraltılmışsa simgeye)."""
        if self._nav_anim is None:
            self.nav_column.setFixedWidth(self._nav_width())

    def set_nav_collapsed(self, collapsed: bool, *, animate: bool = True) -> None:
        """Kenar çubuğunu daraltır ya da açar; tercih kaydedilir. Animasyon kapalıysa anında olur."""
        self.settings.setValue("ui/nav_collapsed", "1" if collapsed else "0")
        self.nav_action.setChecked(not collapsed)
        if self._nav_anim is not None:
            self._nav_anim.stop()
            self._nav_anim = None
        self._nav_collapsed = collapsed
        target = self._nav_width()
        start = self.nav_column.width()
        if not (animate and self.isVisible() and animations_enabled()) or start == target:
            self._finish_nav(collapsed)
            return
        if not collapsed:  # açılırken önce ad ve başlık görünür, sonra genişlik büyür
            self.nav.set_collapsed(False)
            self.nav_header.setVisible(True)
        anim = QVariantAnimation(self)
        anim.setDuration(NAV_ANIMATION_MS)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.valueChanged.connect(lambda value: self.nav_column.setFixedWidth(int(value)))
        anim.finished.connect(lambda: self._finish_nav(collapsed))
        self._nav_anim = anim
        anim.start()

    def _finish_nav(self, collapsed: bool) -> None:
        self._nav_anim = None
        self.nav.set_collapsed(collapsed)
        self.nav_header.setVisible(not collapsed)
        self.nav_column.setFixedWidth(self._nav_width())

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and hasattr(self, "nav"):
            self._update_nav_width()

    # --- menüler -------------------------------------------------------------------------

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&Dosya")
        self._action(file_menu, "Yeni Proje", self.new_project, QKeySequence.StandardKey.New)
        self._action(file_menu, "Proje Aç…", self._open_project_dialog, QKeySequence.StandardKey.Open)
        self.recent_menu = file_menu.addMenu("Son Projeler")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        file_menu.addSeparator()
        self.save_action = self._action(file_menu, "Kaydet", self.save_project, QKeySequence.StandardKey.Save)
        self._action(file_menu, "Farklı Kaydet…", self.save_project_as, QKeySequence.StandardKey.SaveAs)
        file_menu.addSeparator()
        keys_menu = file_menu.addMenu("Anahtarlar")
        self.keys_action = self._action(keys_menu, "prod.keys Seç…", self._choose_keys)
        self._action(keys_menu, "title.keys Seç…", self._choose_title_keys)
        self.title_keys_clear_action = self._action(keys_menu, "title.keys Dosyasını Kaldır", self._clear_title_keys)
        self.title_keys_clear_action.setEnabled(False)
        file_menu.addSeparator()
        self.cache_action = self._action(file_menu, "Önbelleği Temizle…", self._clear_cache)
        file_menu.addSeparator()
        self._action(file_menu, "Çıkış", self.close, QKeySequence.StandardKey.Quit)

        view_menu = self.menuBar().addMenu("&Görünüm")
        self.nav_action = QAction("Kenar Çubuğu", self, checkable=True)
        self.nav_action.setChecked(not self._nav_collapsed)
        self.nav_action.setShortcut(QKeySequence("Ctrl+Alt+S"))
        self.nav_action.triggered.connect(lambda checked: self.set_nav_collapsed(not checked))
        view_menu.addAction(self.nav_action)
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("Tema")
        group = QActionGroup(self)
        current = self._theme_mode()
        for mode in ThemeMode:
            act = QAction(THEME_LABELS[mode], self, checkable=True)
            act.setChecked(mode == current)
            act.triggered.connect(lambda _=False, m=mode: self._set_theme(m))
            group.addAction(act)
            theme_menu.addAction(act)

        view_menu.addSeparator()
        size_menu = view_menu.addMenu("Yazı boyutu")
        self.size_group = QActionGroup(self)
        current_size = self._font_size()
        for size in FONT_SIZES:
            act = QAction(
                f"{size} punto" + ("  (varsayılan)" if size == DEFAULT_FONT_SIZE else ""), self, checkable=True
            )
            act.setChecked(size == current_size)
            act.triggered.connect(lambda _=False, n=size: self._set_font_size(n))
            self.size_group.addAction(act)
            size_menu.addAction(act)
        size_menu.addSeparator()
        for text, shortcut, step in (("Büyüt", "Ctrl+=", 1), ("Küçült", "Ctrl+-", -1)):
            act = QAction(text, self)
            act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(lambda _=False, d=step: self._step_font_size(d))
            size_menu.addAction(act)
            self.addAction(act)  # menü kapalıyken de kısayol çalışsın
        reset = QAction("Varsayılan boyut", self)
        reset.setShortcut(QKeySequence("Ctrl+0"))
        reset.triggered.connect(lambda: self._set_font_size(DEFAULT_FONT_SIZE))
        size_menu.addAction(reset)
        self.addAction(reset)

        view_menu.addSeparator()
        view = self.translate_page.view_actions
        view_menu.addAction(view.symbols)
        align_menu = view_menu.addMenu("Hizala")
        for action in view.align_actions.values():
            align_menu.addAction(action)
        view_menu.addAction(view.pane_toggle)
        pane_menu = view_menu.addMenu("Panel Konumu")
        for action in view.pane_actions.values():
            pane_menu.addAction(action)

        edit_menu = self.menuBar().addMenu("Dü&zen")
        self.undo_action = self._action(edit_menu, "Geri Al", self.undo_last, QKeySequence.StandardKey.Undo)
        edit_menu.aboutToShow.connect(self._update_undo_action)
        edit_menu.addSeparator()
        for text, slot in (
            ("Bul…\tCtrl+F", self._menu_find),
            ("Değiştir…\tCtrl+H", self._menu_find_replace),
            ("Tabloyu Süz…\tCtrl+Shift+F", self._menu_search),
            ("Sonraki Bakılacak Satır\tF3", self._menu_next_open),
        ):
            self._action(edit_menu, text, slot)

        tools_menu = self.menuBar().addMenu("&Araçlar")
        self._action(tools_menu, "Çeviri Ayarları…", self.edit_provider_settings)
        self._action(tools_menu, "Hazır Çeviriyi İçe Aktar…", self.import_ready_translation)
        tools_menu.addSeparator()
        self._action(tools_menu, "Dış Redaksiyon Dosyası Oluştur (TXT/XLSX)…", self.export_csv)
        self._action(tools_menu, "Dış Redaksiyondan İçe Aktar…", self.import_csv)
        self._action(tools_menu, "Dış Çeviri Dosyası Oluştur (TXT/XLSX)…", self.export_translation)
        self._action(tools_menu, "Dış Çeviriden İçe Aktar…", self.import_translation)

        help_menu = self.menuBar().addMenu("&Yardım")
        self.update_action = self._action(help_menu, "Güncellemeleri Denetle…", self.open_updates)
        self.update_action.setEnabled(self.app_root is not None or self.packaged)
        if self.app_root is None and not self.packaged:
            self.update_action.setToolTip("Bu kurulum kaynak koduyla çalışmadığı için uygulama içinden güncellenemez.")
        self._action(help_menu, "Eklentiler…", self.open_plugins)
        self._action(help_menu, "Log Klasörünü Aç", self._open_logs)
        self._action(help_menu, "Hakkında", self._about)

    def _action(
        self, menu: QWidget, text: str, slot: Callable[[], object], shortcut: QKeySequence.StandardKey | None = None
    ) -> QAction:
        act = QAction(text, self)
        if shortcut is not None:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def _theme_mode(self) -> ThemeMode:
        try:
            return ThemeMode(str(self.settings.value("ui/theme", ThemeMode.SYSTEM.value)))
        except ValueError:
            return ThemeMode.SYSTEM

    def _font_size(self) -> int:
        try:
            return clamp_font_size(float(str(self.settings.value("ui/font_size", DEFAULT_FONT_SIZE))))
        except ValueError:
            return DEFAULT_FONT_SIZE

    def _set_theme(self, mode: ThemeMode) -> None:
        self.settings.setValue("ui/theme", mode.value)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, mode, self._font_size())

    def _set_font_size(self, size: int) -> None:
        size = clamp_font_size(size)
        self.settings.setValue("ui/font_size", size)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, self._theme_mode(), size)
        for act in self.size_group.actions():
            act.setChecked(act.text().startswith(f"{size} punto"))
        self.statusBar().showMessage(f"Yazı boyutu: {size} punto", 3000)

    def _step_font_size(self, direction: int) -> None:
        sizes = list(FONT_SIZES)
        i = sizes.index(self._font_size()) + direction
        self._set_font_size(sizes[max(0, min(len(sizes) - 1, i))])

    def open_plugins(self) -> None:
        PluginsDialog(self, report=user_plugin_report(), builtin=BUILTIN_PLUGINS).exec()

    def _open_logs(self) -> None:
        log_dir().mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "Hakkında",
            f"<b>{APP_TITLE}</b> {__version__}<br><br>"
            "Kendi sahip olduğunuz Nintendo Switch oyunlarının metinlerini Türkçeye çevirmek için bir araç.<br><br>"
            "Uygulama hiçbir şifreleme anahtarı veya oyun dosyası içermez, indirmez, paylaşmaz. "
            "Anahtarlarınızı ve oyun dosyalarınızı kendi konsolunuzdan çıkarmanız gerekir.",
        )

    # --- güncelleme ----------------------------------------------------------------------

    def open_updates(self) -> None:
        packaged = self.app_root is None and self.packaged
        root = self.install_dir if packaged else self.app_root
        if root is None:
            return
        dialog = UpdateDialog(
            self,
            secrets=self.secrets,
            settings=self.settings,
            current=__version__,
            root=root,
            updater_factory=self.updater_factory,
            git_mode=not packaged and is_git_checkout(root),
            packaged=packaged,
        )
        if dialog.exec() != UpdateDialog.DialogCode.Accepted or dialog.info is None:
            return
        self.update_badge.hide()
        version = dialog.info.version
        prepared = dialog.prepared
        if packaged:
            if prepared is not None and not self._install_package(prepared, root):
                discard_prepared(prepared)
            return
        later = f"{version} sürümü uygulama bir sonraki açılışında kurulacak."
        answer = QMessageBox.question(
            self,
            "Güncelleme hazır",
            f"{version} sürümü indirildi. Uygulama şimdi yeniden başlatılıp güncellensin mi?\n\n"
            "Hayır derseniz güncelleme bir sonraki açılışta kurulur.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage(later, 10000)
            return
        if self.busy:
            QMessageBox.information(self, "Güncelleme hazır", "Önce süren işlemi bitirin veya iptal edin. " + later)
            return
        if not self._confirm_discard():
            self.statusBar().showMessage(later, 10000)
            return
        self.dirty = False  # kullanıcı az önce kaydetti veya değişiklikleri atmayı seçti
        self.relauncher(root)
        self.close()

    def _install_package(self, prepared: PreparedInstall, install_dir: Path) -> bool:
        """İndirilip doğrulanan paketi kurdurur: uygulama kapanır, yardımcı klasörü değiştirip yeniden açar.

        False dönerse kurulmadı (çağıran hazırlığı siler); sonra Yardım → Güncellemeleri Denetle ile yinelenebilir.
        """
        retry = "Güncelleme yapılmadı. Daha sonra Yardım → Güncellemeleri Denetle ile yineleyebilirsiniz."
        answer = QMessageBox.question(
            self,
            "Güncelleme hazır",
            f"{prepared.version} sürümü indirildi ve doğrulandı. Uygulama şimdi kapatılıp güncellensin ve "
            "yeniden açılsın mı?\n\nProjeleriniz, eklentileriniz ve ayarlarınız olduğu gibi kalır.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage(retry, 10000)
            return False
        if self.busy:
            QMessageBox.information(self, "Güncelleme hazır", "Önce süren işlemi bitirin veya iptal edin. " + retry)
            return False
        if not self._confirm_discard():
            self.statusBar().showMessage(retry, 10000)
            return False
        try:
            self.installer_launcher(prepared, install_dir)
        except UpdateError as exc:
            QMessageBox.warning(self, "Güncelleme", exc.user_text())
            return False
        self.dirty = False  # kullanıcı az önce kaydetti veya değişiklikleri atmayı seçti
        self.close()
        return True

    def check_updates_in_background(self) -> None:
        """Açılışta (ayar açıksa) yeni sürüm olup olmadığına sessizce bakar; varsa durum çubuğunda rozet çıkar."""
        root = self.app_root
        if (
            (root is None and not self.packaged)
            or self._update_task is not None
            or not auto_check_enabled(self.settings)
        ):
            return
        try:
            token = self.secrets.get(GITHUB_UPDATE_KEY)
        except NxError:
            token = None  # anahtar deposu okunamıyorsa anahtarsız denenir (açık depo); açılış bozulmaz
        factory = self.updater_factory

        def work(_ctx: TaskContext) -> object:
            updater = factory(token)
            try:
                return updater.check(__version__)
            finally:
                updater.close()

        task = Task(work, "Güncelleme denetimi")
        task.succeeded.connect(self._update_checked)
        task.failed.connect(lambda text: log.info("Açılıştaki güncelleme denetimi başarısız: %s", text))
        self._update_task = task
        task.start()

    def _default_updater(self, token: str | None) -> Updater:
        if self.app_root is None:  # paketlenmiş sürüm: yalnızca yeni sürüm olup olmadığına bakılır
            return GitHubUpdater(token)
        return make_updater(self.app_root, token)

    def _update_checked(self, result: object) -> None:
        assert isinstance(result, UpdateInfo)
        if result.newer:
            self.update_badge.setText(f"Yeni sürüm: {result.version} — Güncelle")
            self.update_badge.show()

    # --- genel durum ---------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self.task is not None

    def _refresh(self) -> None:
        name = self.project.path.stem if self.project.path else "Kaydedilmemiş proje"
        self.setWindowTitle(f"{name}{' *' if self.dirty else ''} — {APP_TITLE}")
        self.add_page.set_sources(self.sources)
        problems = check_sources(self.sources) if self.sources else []
        if self.keys is None:
            reason = "Anahtar dosyası seçin"
        elif not self.sources:
            reason = "Oyun dosyası ekleyin"
        else:
            reason = " ".join(problems)
        can_scan = self.keys is not None and bool(self.sources) and not problems
        if not self.busy:
            self.add_page.set_can_continue(can_scan, reason)
        self.add_page.set_files_message("warning", " ".join(problems) if self.sources else "")
        scan_item = self.nav.item(STEP_SCAN)
        flags = scan_item.flags()
        if can_scan or self.report is not None:
            scan_item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled)
        else:
            scan_item.setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)
        for step in (STEP_TRANSLATE, STEP_QA, STEP_EXPORT):
            item = self.nav.item(step)
            if self.translate_page.model.rows:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        self.nav.setEnabled(not self.busy)
        for act in (self.save_action, self.cache_action):
            act.setEnabled(not self.busy)
        self._refresh_nav()
        self._refresh_status()

    def _pane_focus_changed(self, focused: bool) -> None:
        self._pane_focused = focused
        if not focused:
            self.status_segments.set_cursor(None, None)

    def _pane_cursor_moved(self, line: int, column: int) -> None:
        """İmleç konumu yalnızca panelin çeviri düzenleyicisi odaktayken durum çubuğunda görünür."""
        if self._pane_focused:
            self.status_segments.set_cursor(line, column)

    def _refresh_derived(self) -> None:
        """Tablodaki satırlardan türetilen göstergeler: kenar çubuğu rozetleri ve durum çubuğu."""
        self._refresh_nav()
        self._refresh_status()

    def _open_qa_from_status(self) -> None:
        """Durum çubuğundaki "N hatalı" tıklaması; iş sürerken kenar çubuğu kilidi aşılmaz."""
        if not self.busy:
            self.nav.setCurrentRow(STEP_QA)

    def _refresh_status(self) -> None:
        """Durum çubuğu bölmeleri; satır sayıları, hatalı satırlar, sağlayıcı ve kayıt durumundan türetilir."""
        rows = self.translate_page.model.rows
        self.status_segments.update(
            rows=len(rows),
            shown=self.translate_page.proxy.rowCount(),
            translated=sum(1 for r in rows if r.status in TRANSLATED_STATUSES),
            approved=sum(1 for r in rows if r.status == Status.APPROVED),
            errors=sum(1 for r in rows if r.status == Status.ERROR),
            provider=self._provider_kind(),
            saved=not self.dirty,
        )

    def _provider_kind(self) -> str:
        """Son kullanılan çeviri sağlayıcısı ("ollama" ya da "deepl"); seçilmediyse boş."""
        kind = str(self.settings.value("translate/provider", ""))
        return kind if kind in (PROVIDER_OLLAMA, PROVIDER_DEEPL) else ""

    def _probe_provider(self) -> None:
        """Sağlayıcı bölmesinin ipucu açılırken durumu (kota / bellekteki model) arka planda yeniler."""
        kind = self._provider_kind()
        if not kind:
            return
        if kind == PROVIDER_OLLAMA:
            url = str(self.settings.value("ollama/url", DEFAULT_URL))
            model = str(self.settings.value("ollama/model", ""))
            key: tuple[str, ...] = (kind, url, model)
            self._provider_tip_title = "Ollama"

            def fetch(client: httpx.Client) -> list[str]:
                return ollama_summary(url, model, client)

        else:
            key = (kind,)
            self._provider_tip_title = "DeepL"
            secrets = self.secrets

            def fetch(client: httpx.Client) -> list[str]:
                try:
                    provider = DeepLProvider(secrets.get(DEEPL_API_KEY) or "", client=client)
                except ProviderError as exc:
                    return [exc.message]
                return deepl_summary(provider)

        known = self.provider_probe.lines_for(key)
        self._show_provider_tip(known or ["Durum alınıyor…"])
        self.provider_probe.request(key, fetch)

    def _show_provider_tip(self, lines: list[str]) -> None:
        self.status_segments.set_provider_tip("\n".join([self._provider_tip_title, *lines]))

    def _refresh_nav(self) -> None:
        """Kenar çubuğu rozetleri ve proje başlığı; projedeki durumdan türetilir."""
        nav = self.nav
        count = len(self.sources)
        nav.set_badge(STEP_ADD, str(count) if count else "")
        nav.set_done(STEP_ADD, count > 0)
        found = len(self.report.entries) if self.report is not None else 0
        nav.set_badge(STEP_SCAN, str(found) if self.report is not None else "")
        nav.set_done(STEP_SCAN, self.report is not None)
        rows = self.translate_page.model.rows
        if rows:
            translated = sum(1 for r in rows if r.status in TRANSLATED_STATUSES)
            percent = round(100 * translated / len(rows))
            nav.set_badge(STEP_TRANSLATE, f"%{percent}", "success" if translated == len(rows) else "neutral")
            nav.set_done(STEP_TRANSLATE, translated == len(rows))
        else:
            nav.set_badge(STEP_TRANSLATE)
            nav.set_done(STEP_TRANSLATE, False)
        qa = self._qa_count
        issues = qa[1] if qa is not None and qa[0] is self.project else None
        if issues:
            nav.set_badge(STEP_QA, str(issues), "danger" if self._qa_errors else "warning")
        else:
            nav.set_badge(STEP_QA)
        nav.set_done(STEP_QA, issues == 0)
        nav.set_badge(STEP_EXPORT)
        nav.set_done(STEP_EXPORT, self.last_export is not None)
        name = self.project.path.stem if self.project.path else "Kaydedilmemiş proje"
        detail_parts: list[str] = []
        if self.report is not None:
            detail_parts = [self.report.game_name, self.report.title_id]
        elif self.sources:
            detail_parts = [self.sources[0].name, self.sources[0].title_id]
        if self.sources:
            detail_parts.append(self.sources[0].display_version)
        self.nav_header.set_project(name, " · ".join(part for part in detail_parts if part))
        self._update_nav_width()

    def _go_to(self, row: int) -> None:
        if row < 0:
            return
        self.pages.setCurrentIndex(row)
        if row == STEP_SCAN and not self.busy:
            if self.report is not None:
                self.scan_page.show_report(self.report)
            else:
                self.scan_page.show_empty()
        elif row == STEP_QA:
            self._refresh_qa()
        elif row == STEP_EXPORT and not self.busy:
            self._refresh_export()

    def _mark_changed(self) -> None:
        if self.project.path is None:
            self.dirty = True
            self._recovery_due = True
        self._refresh()

    def _run(
        self,
        fn: Callable[[TaskContext], object],
        description: str,
        *,
        on_success: Callable[[object], None],
        on_failure: Callable[[str], None],
        on_progress: Callable[[int, int, str], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        on_partial: Callable[[object], None] | None = None,
    ) -> None:
        task = Task(fn, description)
        self.task = task
        if on_progress is not None:
            task.progress.connect(on_progress)
        if on_partial is not None:
            task.partial.connect(on_partial)
        task.succeeded.connect(on_success)
        task.failed.connect(on_failure)
        if on_cancel is not None:
            task.cancelled.connect(on_cancel)
        task.finished.connect(self._task_finished)
        self.statusBar().showMessage(description + "…")
        self._refresh()
        task.start()

    def _task_finished(self) -> None:
        if self.task is not None:
            self.task.deleteLater()
        self.task = None
        self.statusBar().showMessage("Hazır")
        self.add_page.set_busy(False)
        self._refresh()

    def _cancel_task(self) -> None:
        if self.task is not None:
            self.task.cancel()

    def _cache_dir(self) -> Path:
        return self.project.cache_dir or default_cache_dir()

    def _inputs(self) -> Inputs:
        assert self.keys is not None
        return Inputs(tuple(s.path for s in self.sources), self.keys, self.title_keys, self._cache_dir())

    # --- anahtarlar ----------------------------------------------------------------------

    def _restore_keys(self) -> None:
        saved = self.settings.value("keys/prod", "")
        if saved:
            self.load_keys_file(Path(str(saved)), remember=False)
        else:
            self.add_page.set_keys_state("neutral", None)
            self._show_keys_status()
        saved_title = self.settings.value("keys/title", "")
        if saved_title:
            self.load_title_keys_file(Path(str(saved_title)), remember=False)

    def _choose_keys(self) -> None:
        start = str(self.keys.source_path.parent) if self.keys and self.keys.source_path else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "prod.keys dosyasını seçin", start, "Anahtar dosyası (*.keys *.txt);;Tüm dosyalar (*)"
        )
        if path:
            self.load_keys_file(Path(path))

    def load_keys_file(self, path: Path, remember: bool = True) -> bool:
        try:
            keys = load_keys(path)
        except NxError as exc:
            self.keys = None
            self.add_page.set_keys_state("danger", path, exc.user_text())
            self._show_keys_status(path)
            self._refresh()
            return False
        self.keys = keys
        summary = keys.summary()
        newest = summary.newest_generation
        self.add_page.set_keys_state("success", path)
        self._keys_detail = f"{len(keys)} anahtar, nesiller 0–{max(summary.key_area_generations)}."
        if newest < 0:
            self._keys_detail += "\nUyarı: anahtar alanı ve titlekek nesilleri eşleşmiyor; bazı oyunlar açılamayabilir."
        self._show_keys_status(path)
        if remember:
            self.settings.setValue("keys/prod", str(path))
        self._refresh()
        return True

    def _choose_title_keys(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "title.keys dosyasını seçin", str(Path.home()), "Anahtar dosyası (*.keys *.txt);;Tüm dosyalar (*)"
        )
        if path:
            self.load_title_keys_file(Path(path))

    def load_title_keys_file(self, path: Path, remember: bool = True) -> bool:
        try:
            self.title_keys = load_title_keys(path)
        except NxError as exc:
            self.title_keys = None
            self.title_keys_path = None
            self.add_page.set_files_message("danger", exc.user_text())
            self._show_keys_status(self._keys_path())
            return False
        self.title_keys_path = path
        self._show_keys_status(self._keys_path())
        if remember:
            self.settings.setValue("keys/title", str(path))
        return True

    def _clear_title_keys(self) -> None:
        self.title_keys = None
        self.title_keys_path = None
        self.settings.remove("keys/title")
        self._show_keys_status(self._keys_path())

    def _keys_path(self) -> Path | None:
        return self.keys.source_path if self.keys is not None else None

    def _show_keys_status(self, path: Path | None = None) -> None:
        """Durum çubuğundaki anahtar bölmesi ve menüdeki title.keys eylemi (anahtar değerleri gösterilmez)."""
        if self.keys is not None:
            state, text, lines = "success", "Anahtarlar doğrulandı", [f"prod.keys: {path}", self._keys_detail]
        elif path is not None:
            state, text, lines = "danger", "Anahtar geçersiz", [f"prod.keys okunamadı: {path}"]
        else:
            state, text, lines = "neutral", "Anahtar seçilmedi", ["prod.keys seçmek için tıklayın."]
        if self.title_keys_path is not None and self.title_keys is not None:
            lines.append(f"title.keys: {self.title_keys_path} ({len(self.title_keys)} kayıt)")
        else:
            lines.append("title.keys: seçilmedi (isteğe bağlı; oyun dosyasında bilet yoksa gerekir)")
        lines.append("Değiştirmek için: Dosya → Anahtarlar")
        self.status_segments.set_keys(state, text, "\n".join(lines))
        self.title_keys_clear_action.setEnabled(self.title_keys_path is not None)

    # --- kaynak dosyalar -------------------------------------------------------------------

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Oyun dosyalarını seçin",
            str(self.settings.value("ui/last_dir", str(Path.home()))),
            "Switch oyun dosyaları (*.nsp *.nsz)",
        )
        if paths:
            self.settings.setValue("ui/last_dir", str(Path(paths[0]).parent))
            self.add_files([Path(p) for p in paths])

    def add_files(self, paths: list[Path]) -> None:
        if self.busy or self.keys is None:
            return
        known = {s.path.resolve() for s in self.sources}
        new = [p for p in paths if is_supported_file(p) and p.resolve() not in known]
        skipped = [p.name for p in paths if not is_supported_file(p)]
        if not new:
            msg = "Bu dosyalar zaten eklenmiş." if not skipped else "Yalnızca .nsp ve .nsz dosyaları eklenebilir."
            self.add_page.set_files_message("warning", msg)
            return
        keys = self.keys
        title_keys = self.title_keys

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

        self.add_page.set_busy(True, f"{len(new)} dosya okunuyor…")
        self._run(
            work,
            "Oyun dosyaları okunuyor",
            on_success=lambda r: self._files_added(r, skipped),
            on_failure=self._files_failed,
        )

    def _files_added(self, result: object, skipped: list[str]) -> None:
        assert isinstance(result, tuple)
        records, errors = result
        self.sources = sorted(
            [*self.sources, *records], key=lambda s: ({"base": 0, "update": 1}.get(s.kind, 2), s.title_id, s.version)
        )
        self._sources_changed()
        messages = list(errors)
        if skipped:
            messages.append("Desteklenmeyen dosyalar atlandı: " + ", ".join(skipped))
        if messages:
            self.add_page.set_files_message("danger" if errors else "warning", "\n\n".join(messages))
        if records:
            self.statusBar().showMessage(f"{len(records)} dosya eklendi.", 5000)

    def _files_failed(self, text: str) -> None:
        self.add_page.set_files_message("danger", text)

    def _remove_source(self, row: int) -> None:
        if self.busy or not 0 <= row < len(self.sources):
            return
        del self.sources[row]
        self._sources_changed()

    def _sources_changed(self) -> None:
        try:
            self.project.set_sources(self.sources)
            if self.report is not None:
                self.project.clear_scan()
        except NxError as exc:
            QMessageBox.warning(self, "Proje", exc.user_text())
        self.report = None
        self._mark_changed()

    # --- tarama ----------------------------------------------------------------------------

    def _go_scan(self) -> None:
        """“Metinleri Tara”: güncel rapor varsa onu gösterir, yoksa taramayı hemen başlatır."""
        if self.report is None:
            self.start_scan()
        else:
            self.nav.setCurrentRow(STEP_SCAN)

    def start_scan(self) -> None:
        if self.busy:
            return
        problems = check_sources(self.sources)
        if self.keys is None or problems:
            self.scan_page.show_error(" ".join(problems) or "Önce geçerli bir anahtar dosyası seçin.")
            return
        inputs = self._inputs()
        self.nav.setCurrentRow(STEP_SCAN)
        self.scan_page.show_loading("Oyun dosyaları taranıyor")
        self._run(
            lambda ctx: scan_sources(inputs, ctx),
            "Tarama",
            on_success=self._scan_done,
            on_failure=self.scan_page.show_error,
            on_progress=self.scan_page.loading.update_progress,
            on_cancel=self._scan_cancelled,
        )

    def _scan_done(self, result: object) -> None:
        assert isinstance(result, ScanReport)
        self.report = result
        try:
            self.project.set_game(result.game_name, result.title_id)
            self.project.save_scan(result)
        except NxError as exc:
            QMessageBox.warning(self, "Proje", exc.user_text())
        self._mark_changed()
        self.scan_page.show_report(result)
        self.statusBar().showMessage(f"Tarama {result.duration_s:.1f} saniyede tamamlandı.", 8000)

    def _scan_cancelled(self) -> None:
        if self.report is not None:
            self.scan_page.show_report(self.report)
        else:
            self.scan_page.show_empty()
        self.statusBar().showMessage("Tarama iptal edildi.", 5000)

    def _extract(self, mode: str) -> None:
        if self.busy or self.report is None or self.keys is None:
            return
        problems = check_sources(self.sources)
        if problems:
            QMessageBox.warning(self, "Dosyalar çıkarılamıyor", " ".join(problems))
            return
        folder = QFileDialog.getExistingDirectory(self, "Dosyaların çıkarılacağı boş klasörü seçin", str(Path.home()))
        if not folder:
            return
        dest = Path(folder)
        only = {e.path for e in self.report.text_candidates} if mode == "candidates" else None
        inputs = self._inputs()
        report = self.report
        self.scan_page.show_loading("Dosyalar klasöre çıkarılıyor")

        def done(result: object) -> None:
            self.scan_page.show_report(report)
            QMessageBox.information(self, "Çıkarma tamamlandı", f"{result} dosya şuraya yazıldı:\n{dest}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest)))

        def failed(text: str) -> None:
            self.scan_page.show_report(report)
            QMessageBox.warning(self, "Çıkarma tamamlanamadı", text)

        def cancelled() -> None:
            self.scan_page.show_report(report)
            self.statusBar().showMessage("Çıkarma iptal edildi; yarım kalan dosyalar silindi.", 6000)

        self._run(
            lambda ctx: extract_sources(inputs, dest, only, ctx),
            "Dosyalar çıkarılıyor",
            on_success=done,
            on_failure=failed,
            on_progress=self.scan_page.loading.update_progress,
            on_cancel=cancelled,
        )

    def _diagnosis_report(self) -> None:
        """Metinleri Tara > Daha Fazla > Teşhis Raporu Oluştur: oyunun yapısını inceleyen bir rapor yazar."""
        if self.busy or self.report is None or self.keys is None:
            return
        problems = check_sources(self.sources)
        if problems:
            QMessageBox.warning(self, "Teşhis raporu oluşturulamıyor", " ".join(problems))
            return
        start = str(self.settings.value("ui/last_dir", str(Path.home())))
        folder = QFileDialog.getExistingDirectory(self, f"{RAPOR_ADI} dosyasının yazılacağı klasörü seçin", start)
        if not folder:
            return
        dest = Path(folder)
        inputs = self._inputs()
        report = self.report
        self.scan_page.show_loading("Teşhis raporu hazırlanıyor")

        def done(result: object) -> None:
            self.scan_page.show_report(report)
            QMessageBox.information(self, "Teşhis raporu hazır", f"{result}\n\n{UYARI}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest)))

        def failed(text: str) -> None:
            self.scan_page.show_report(report)
            QMessageBox.warning(self, "Teşhis raporu oluşturulamadı", text)

        def cancelled() -> None:
            self.scan_page.show_report(report)
            self.statusBar().showMessage("Teşhis raporu iptal edildi.", 5000)

        self._run(
            lambda ctx: str(rapor_uret(inputs, dest, ctx)),
            "Teşhis raporu hazırlanıyor",
            on_success=done,
            on_failure=failed,
            on_progress=self.scan_page.loading.update_progress,
            on_cancel=cancelled,
        )

    # --- kontrol (QA) ----------------------------------------------------------------------

    def _font_patch_on(self) -> bool:
        return self.project.setting("font_patch") == "1" and bool(self._patchable_letters())

    def _font_files(self) -> frozenset[str]:
        """Font yamasının uygulanacağı dosyalar (son font taramasından)."""
        if self.font_report is not None:
            return frozenset(self.font_report.patch_files)
        try:
            files = json.loads(self.project.setting("font_files") or "[]")
        except ValueError:
            return frozenset()
        return frozenset(f for f in files if isinstance(f, str))

    def _patchable_letters(self) -> str:
        if self.font_report is not None:
            return self.font_report.patchable_letters
        return self.project.setting("font_patchable")

    def _missing_letters(self) -> str:
        """Dönüştürülecek "eksik" harfler; font yaması açıksa yamanın ekleyeceği harfler hariç."""
        patched = self._font_patch_on()
        if self.font_report is not None:
            return self.font_report.missing_letters(patched=patched)
        return self.project.setting("font_missing_patched" if patched else "font_missing")

    def _transliterate_letters(self) -> str:
        mode = self.project.setting("transliterate_mode", transliterate.MODE_NONE)
        return transliterate.letters_for(mode, self._missing_letters())

    def _refresh_qa(self) -> None:
        self.qa_page.show_font_report(self.font_report, self.project.setting("font_missing"))
        self.qa_page.set_font_patch(self.project.setting("font_patch") == "1", self._patchable_letters())
        mode = self.project.setting("transliterate_mode", transliterate.MODE_NONE)
        self.qa_page.set_mode(mode, self._missing_letters(), self._font_patch_on())
        rows = self.translate_page.model.rows
        files = sorted({r.file for r in rows})
        labels = sorted({code for r in rows for code in r.code_labels})
        self.qa_page.set_fit(self._fit_config(), files, labels, separate_groups(rows))

    def _reload_rows(self) -> None:
        """Tabloyu projeden yeniler; panelde bekleyen metin önce kaydedilir ki yenilenen satırlar bayat kalmasın."""
        self.translate_page.flush_pending()
        self.translate_page.set_rows(self.project.translation_rows())

    def _push_fit_to_page(self) -> None:
        """Çeviri sayfasına sığdırma ayarını ve kod türlerini verir (panel sayacı ve çipler)."""
        self.translate_page.set_fit_config(self._fit_config())

    def _fit_config(self) -> FitConfig:
        """Projenin kayıtlı sığdırma ayarı (sınır yoksa denetim ve düzeltme sığdırma yapmaz)."""
        return load_config(self.project)

    def _save_fit(self) -> None:
        try:
            save_config(self.project, self.qa_page.fit_config())
        except NxError as exc:
            QMessageBox.warning(self, "Proje", exc.user_text())
            return
        self._push_fit_to_page()
        self._mark_changed()

    def _learn_rules(self, scope: str) -> None:
        """Kapsamdaki (proje, dosya ya da grup) orijinal metinlerden sınır önerir; öneri kaydedilmez.

        "Her grup ayrı" kapsamında her grubun sınırı ayrı öğrenilir ve hemen kaydedilir.
        """
        config = self.qa_page.fit_config()
        all_rows = self.translate_page.model.rows
        if scope == EACH_GROUP:
            self.qa_page.show_learned_groups(learn_group_rules(all_rows, config))
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
        self.qa_page.show_learned(rules)

    def scan_fonts(self) -> None:
        if self.busy:
            return
        problems = check_sources(self.sources)
        if self.keys is None or problems or self.report is None:
            reason = " ".join(problems) or "Fontları taramak için anahtar dosyası ve tarama sonucu gerekli."
            self.qa_page.font_banner.show_message("danger", reason)
            return
        inputs = self._inputs()
        report = self.report

        def work(ctx: TaskContext) -> object:
            with opened_view(inputs, ctx) as view:
                return scan_font_files(view, report, ctx)

        def done(result: object) -> None:
            assert isinstance(result, FontReport)
            self.font_report = result
            try:
                self.project.set_setting("font_missing", result.missing_letters())
                self.project.set_setting("font_missing_patched", result.missing_letters(patched=True))
                self.project.set_setting("font_patchable", result.patchable_letters)
                self.project.set_setting("font_files", json.dumps(list(result.patch_files), ensure_ascii=False))
            except NxError as exc:
                QMessageBox.warning(self, "Proje", exc.user_text())
            self._mark_changed()
            self.qa_page.set_font_busy(False)
            self._refresh_qa()

        def failed(text: str) -> None:
            self.qa_page.set_font_busy(False)
            self.qa_page.font_banner.show_message("danger", text)

        self.qa_page.set_font_busy(True)
        self._run(
            work,
            "Fontlar taranıyor",
            on_success=done,
            on_failure=failed,
            on_cancel=lambda: self.qa_page.set_font_busy(False),
        )

    def _set_transliterate(self, mode: str) -> None:
        try:
            self.project.set_setting("transliterate_mode", mode)
        except NxError as exc:
            QMessageBox.warning(self, "Proje", exc.user_text())
            return
        self._mark_changed()
        self.qa_page.set_mode(mode, self._missing_letters(), self._font_patch_on())

    def _set_font_patch(self, enabled: bool) -> None:
        try:
            self.project.set_setting("font_patch", "1" if enabled else "")
        except NxError as exc:
            QMessageBox.warning(self, "Proje", exc.user_text())
            return
        self._mark_changed()
        self._refresh_qa()

    def run_checks(self) -> None:
        rows = self.project.translation_rows()
        issues = run_qa_checks(
            rows,
            self._missing_letters(),
            self._transliterate_letters(),
            self.project.glossary(),
            self._fit_config(),
            spell=self.spell,
        )
        self.qa_page.show_issues(issues, rows)
        self.translate_page.set_qa_issues(issues, rows)
        counted = [i for i in issues if i.severity in (SEVERITY_ERROR, SEVERITY_WARNING)]
        self._qa_count = (self.project, len(counted))
        self._qa_errors = any(i.severity == SEVERITY_ERROR for i in counted)
        self._refresh_nav()

    def _sync_spell(self) -> None:
        """Editördeki yazım işaretlerini güncel denetleyici ve oyun sözlüğüyle yeniler."""
        self.translate_page.set_spell(self.spell, glossary_words(self.project.glossary()))

    def add_spell_words(self, words: list[str]) -> None:
        """Sözcükleri kalıcı kullanıcı sözlüğüne ekler; editör ve (yapıldıysa) denetim sonucu yenilenir."""
        try:
            added = self.user_dictionary.add(words)
        except OSError as exc:
            QMessageBox.warning(self, "Yazım sözlüğü", f"Sözlük kaydedilemedi: {exc.strerror or exc}")
            return
        if self.spell is not None:
            self.spell.add_user_words(words)
        self._sync_spell()
        self.statusBar().showMessage(f"{format_int(added)} sözcük yazım sözlüğüne eklendi.", 5000)
        if self._qa_count is not None and self._qa_count[0] is self.project:
            self.run_checks()

    def add_spelling_from_qa(self, words: list[str]) -> None:
        dialog = AddSpellWordsDialog(self, [str(w) for w in words])
        if dialog.exec() == AddSpellWordsDialog.DialogCode.Accepted and dialog.selected():
            self.add_spell_words(dialog.selected())

    def edit_user_dictionary(self) -> None:
        dialog = UserDictionaryDialog(self, self.user_dictionary)
        dialog.exec()
        if dialog.removed:
            self.spell = load_spell_checker(self.user_dictionary)
            self._sync_spell()
            if self._qa_count is not None and self._qa_count[0] is self.project:
                self.run_checks()

    def _save_fix_kinds(self, kinds: list[str]) -> None:
        self.settings.setValue("qa/fix_kinds", ",".join(kinds))

    def _write_row_changes(
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
                updated += self.project.set_translations(changes, job=job_id, remember=False)
            elif kind == Status.REDACTED:
                updated += self.project.set_translations(changes, status=Status.REDACTED, job=job_id, remember=False)
            else:
                updated += self.project.set_translations(changes, machine=True, job=job_id, remember=False)
        return updated

    def _reflow(self, rows: list[TranslationRow]) -> list[TranslationRow] | None:
        """Satırların satır sonlarını yeniden böler; tek iş olarak geçmişe yazılır (Ctrl+Z). Hata olursa `None`.

        Satırın durumu korunur: onaylı satır onaylı, redakte satır redakte, diğerleri makine kalır.
        """
        plan = plan_reflow(rows, self._fit_config())
        if not plan:
            return []
        job_id = new_job_id("reflow")
        try:
            updated = self._write_row_changes(plan, rows, job_id)
        except NxError as exc:
            self.translate_page.show_notice("danger", exc.user_text())
            return None
        self._mark_changed()
        self.translate_page.model.update_rows(updated)
        self._set_last_job(job_id)
        self._refresh_marks()
        return updated

    def reflow_selected(self, ids: list[int]) -> None:
        """Çeviri tablosunda seçili satırların satır sonlarını yeniden böler."""
        if self.busy:
            return
        wanted = set(ids)
        rows = [r for r in self.translate_page.model.rows if r.id in wanted]
        updated = self._reflow(rows)
        if updated is None:
            return
        left = len(rows) - len(updated)
        text = f"{format_int(len(updated))} satır yeniden bölündü." if updated else "Yeniden bölünecek satır yok."
        if left and updated:
            text += f" {format_int(left)} satır zaten uygundu ya da bölünemedi."
        self.translate_page.show_notice("success" if updated else "warning", text)

    def apply_fixes(self, kinds: list[str], row_ids: list[int]) -> None:
        """Seçilen türlerdeki bulguları düzeltir (`row_ids` boşsa tüm bulgular); tek iş olarak geçmişe yazılır.

        Sonra denetim yeniden çalışır ve sayılar güncellenir; rapor “Son İşin Değişiklikleri” penceresidir.
        """
        if self.busy or not kinds:
            return
        page = self.qa_page
        rows = self.project.translation_rows()
        glossary = self.project.glossary()
        fit = self._fit_config()
        issues = run_qa_checks(rows, self._missing_letters(), self._transliterate_letters(), glossary, fit)
        if row_ids:
            wanted = set(row_ids)
            issues = [i for i in issues if i.row_id in wanted]
        plan = plan_fixes(rows, issues, kinds, glossary=glossary, fit=fit)
        notes = []
        if plan.approved:
            notes.append(f"Onayladığınız {format_int(plan.approved)} satıra dokunulmadı.")
        if plan.unfixed:
            notes.append(f"{format_int(plan.unfixed)} satırdaki sorun programla düzeltilemedi; elle bakın.")
        if plan.empty:
            page.show_fix_result("warning", " ".join(["Düzeltilecek bir şey bulunamadı.", *notes]))
            return
        job_id = new_job_id("autofix")
        try:
            self._write_row_changes(plan.changes, rows, job_id)
        except NxError as exc:
            page.show_fix_result("danger", exc.user_text())
            return
        self._mark_changed()
        self._reload_rows()
        self._set_last_job(job_id)
        self._refresh_marks()
        self._fix_report = (job_id, {i: ", ".join(KIND_LABELS[k] for k in ks) for i, ks in plan.applied.items()})
        self.run_checks()
        page.show_fix_result(
            "success", " ".join([f"{format_int(len(plan.changes))} satır düzeltildi.", *notes]), "Raporu Gör"
        )

    def _open_row(self, row_id: int) -> None:
        self.nav.setCurrentRow(STEP_TRANSLATE)
        self.translate_page.select_row(row_id)

    # --- dışa aktarma ----------------------------------------------------------------------

    def _refresh_export(self) -> None:
        page = self.export_page
        page.show_form()
        if not page.mod_name.text():
            page.mod_name.setText(f"{self.project.game_name or 'Oyun'} Türkçe")
        if not page.folder.text():
            page.folder.setText(str(self.settings.value("export/dir", str(Path.home() / "Desktop"))))
        letters = self._transliterate_letters()
        include_errors = self._include_errors_on()
        by_file, written, errors, untranslated = collect_translations(
            self.project.translation_rows(), letters, include_errors=include_errors
        )
        page.set_include_errors(errors=errors, checked=include_errors)
        conversion = f"{' '.join(letters)} → {' '.join(transliterate.apply(letters, letters))}" if letters else "yok"
        if self._font_patch_on():
            conversion += f"; font yaması: {' '.join(self._patchable_letters())} eklenecek"
        problems = check_sources(self.sources) if self.sources else ["Oyun dosyası eklenmedi."]
        if self.keys is None:
            problems.append("Anahtar dosyası seçilmedi.")
        notes = problems + (version_warnings(self.sources, self.report) if self.sources else [])
        unfixed = "".join(c for c in self._patchable_letters() if c not in letters)
        if unfixed and not self._font_patch_on():
            notes.append(
                f"Oyun fontlarında {' '.join(unfixed)} harfleri yok; oyunda kutu veya başka fontla görünürler. "
                "“Kontrol Et” adımında “Eksik Türkçe harfleri fontlara ekle” kutusunu işaretleyin."
            )
        if not self.project.setting("font_missing") and self.font_report is None:
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
        return bool(self.project.setting("export_include_errors"))

    def _set_include_errors(self, enabled: bool) -> None:
        try:
            self.project.set_setting("export_include_errors", "1" if enabled else "")
        except NxError as exc:
            QMessageBox.warning(self, "Proje", exc.user_text())
            return
        self._mark_changed()
        self._refresh_export()

    def _choose_export_folder(self) -> None:
        start = self.export_page.folder.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Modun oluşturulacağı klasörü seçin", start)
        if folder:
            self.export_page.folder.setText(folder)
            self.settings.setValue("export/dir", folder)
            self.export_page.update_target()

    def export_mod(self) -> None:
        if self.busy:
            return
        page = self.export_page
        dest = page.destination()
        if dest is None:
            page.result.show_message("danger", "Önce modun oluşturulacağı konumu seçin.")
            return
        problems = check_sources(self.sources)
        if self.keys is None or problems:
            page.result.show_message("danger", " ".join(problems) or "Anahtar dosyası seçilmedi.")
            return
        inputs = self._inputs()
        files = [TextFileRef(*f) for f in self.project.text_files()]
        rows = self.project.translation_rows()
        updates = [s.version for s in self.sources if s.kind == "update"]
        bases = [s.version for s in self.sources if s.kind == "base"]
        info = ExportInfo(
            self.project.game_name or "Oyun",
            self.project.title_id,
            bases[0] if bases else None,
            max(updates) if updates else None,
        )
        options = ExportOptions(
            page.layout_key,
            dest,
            page.mod_name.text(),
            self._transliterate_letters(),
            patch_fonts=self._font_patch_on(),
            font_files=self._font_files(),
            uppercase=self.project.uppercase_rules(),
            include_errors=self._include_errors_on(),
        )
        page.result.show_message("success", "")
        page.open_button.hide()
        page.show_running()

        def done(result: object) -> None:
            assert isinstance(result, ExportResult)
            page.show_form()
            self.last_export = result.dest
            if options.layout == LAYOUT_ATMOSPHERE:
                where = "Bu klasördeki 'atmosphere' klasörünü SD kartın köküne kopyalayın."
            else:
                where = f"'{info.title_id}' klasörünü emülatörün mod klasörüne kopyalayın."
            message = (
                f"Mod oluşturuldu: {result.dest}\n{format_int(len(result.files))} dosya, "
                f"{format_int(result.rows_written)} çeviri satırı. {where} Ayrıntılı kurulum bilgisi "
                f"klasördeki “{INFO_FILE}” dosyasında."
            )
            if options.include_errors and result.rows_error:
                message += (
                    f"\n\nHatalı satırlar: {format_int(result.rows_error_written)} tanesi çevirisiyle yazıldı, "
                    f"{format_int(result.rows_error_kept)} tanesi orijinal bırakıldı. Oyun çökerse bu satırları "
                    "düzeltip modu yeniden oluşturun."
                )
            if result.font_patches:
                message += f"\n\nFont yaması: {format_int(len(result.font_patches))} fonta Türkçe harf eklendi."
            if result.warnings:
                message += "\n\nDikkat: " + " ".join(result.warnings)
            page.result.show_message("warning" if result.warnings else "success", message)
            page.open_button.show()

        def failed(text: str) -> None:
            page.show_form()
            page.result.show_message("danger", text)

        def cancelled() -> None:
            page.show_form()
            page.result.show_message("warning", "Dışa aktarma iptal edildi; hedefte hiçbir dosya bırakılmadı.")

        self._run(
            lambda ctx: export_layeredfs(inputs, files, rows, options=options, info=info, ctx=ctx),
            "Mod oluşturuluyor",
            on_success=done,
            on_failure=failed,
            on_progress=page.progress.update_progress,
            on_cancel=cancelled,
        )

    def _open_export_folder(self) -> None:
        if self.last_export is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_export)))

    # --- hazır çeviriyi içe aktarma -----------------------------------------------------------

    def import_ready_translation(self) -> None:
        """Oyunun hazır bir Türkçe yamasındaki (Unity metin tabloları) çevirileri projeye aktarır."""
        if self.busy:
            return
        if not self.project.translation_rows():
            QMessageBox.information(
                self,
                "Hazır çeviriyi içe aktar",
                "Önce “Metinleri Tara” adımından metinleri çeviri tablosuna aktarın.",
            )
            return
        start = str(self.settings.value("import/dir", str(Path.home())))
        folder = QFileDialog.getExistingDirectory(self, "Çeviri yamasının klasörünü seçin", start)
        if not folder:
            return
        self.settings.setValue("import/dir", folder)
        root = Path(folder)

        def confirm(result: object) -> None:
            assert isinstance(result, ReadyTranslations)
            self.statusBar().showMessage("Hazır", 2000)
            plan = port_translations(self.project, result, apply=False)
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
                QMessageBox.information(
                    self, "Hazır çeviriyi içe aktar", "Yazılacak yeni bir çeviri yok.\n\n" + "\n".join(lines[:3])
                )
                return
            answer = QMessageBox.question(self, "Hazır çeviriyi içe aktar", "\n".join(lines))
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                report = port_translations(self.project, result)
            except NxError as exc:
                QMessageBox.warning(self, "Hazır çeviriyi içe aktar", exc.user_text())
                return
            self._mark_changed()
            self._reload_rows()
            text = f"{format_int(report.applied)} satır hazır çeviriden aktarıldı."
            if report.code_problems:
                text += f" {format_int(len(report.code_problems))} satır kontrol kodları uyuşmadığı için atlandı."
            self.nav.setCurrentRow(STEP_TRANSLATE)
            self.translate_page.show_notice("success", text)

        def failed(text: str) -> None:
            QMessageBox.warning(self, "Hazır çeviriyi içe aktar", text)

        self._run(
            lambda ctx: read_ready_translations(root, ctx),
            "Hazır çeviri okunuyor",
            on_success=confirm,
            on_failure=failed,
            on_progress=lambda _d, _t, message: self.statusBar().showMessage(message),
        )

    # --- çeviri tablosu ---------------------------------------------------------------------

    def import_texts(self) -> None:
        if self.busy or self.report is None or self.keys is None:
            return
        problems = check_sources(self.sources)
        if problems:
            QMessageBox.warning(self, "Metinler aktarılamıyor", " ".join(problems))
            return
        inputs = self._inputs()
        report = self.report
        language = self.scan_page.report.language.currentData()
        source_language = str(language) if language else None
        self._import_language = source_language or "en"
        self.scan_page.show_loading("Metinler oyundan çıkarılıyor")

        def failed(text: str) -> None:
            self.scan_page.show_report(report)
            QMessageBox.warning(self, "Metinler aktarılamadı", text)

        def cancelled() -> None:
            self.scan_page.show_report(report)
            self.statusBar().showMessage("Aktarma iptal edildi; projede değişiklik yapılmadı.", 6000)

        self._run(
            lambda ctx: extract_texts(inputs, report, ctx, source_language),
            "Metinler çıkarılıyor",
            on_success=self._texts_extracted,
            on_failure=failed,
            on_progress=self.scan_page.loading.update_progress,
            on_cancel=cancelled,
        )

    def _texts_extracted(self, result: object) -> None:
        assert isinstance(result, TextExtraction)
        if self.report is not None:
            self.scan_page.show_report(self.report)
        try:
            stats = self.project.import_texts(result.files)
            self.project.set_setting("source_language", self._import_language)
            record_extraction(self.project, (fmt for _path, _tid, fmt in self.project.text_files()))
        except NxError as exc:
            QMessageBox.warning(self, "Metinler aktarılamadı", exc.user_text())
            return
        self._reload_rows()
        self._mark_changed()
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
        self.translate_page.show_notice("warning" if result.warnings else "success", summary)
        self.nav.setCurrentRow(STEP_TRANSLATE)

    # --- makine çevirisi ve sözlük ---------------------------------------------------------

    def edit_glossary(self) -> None:
        start = Path(str(self.settings.value("glossary/dir", str(Path.home()))))
        dialog = GlossaryDialog(self, self.project.glossary(), start, can_suggest=not self.busy)
        accepted = dialog.exec() == GlossaryDialog.DialogCode.Accepted
        self.settings.setValue("glossary/dir", str(dialog.start_dir))
        if not accepted:
            return
        try:
            self.project.set_glossary(dialog.terms())
        except NxError as exc:
            QMessageBox.warning(self, "Sözlük kaydedilemedi", exc.user_text())
            return
        self._mark_changed()
        self._sync_spell()
        self.statusBar().showMessage(f"Sözlük kaydedildi ({len(dialog.terms())} terim).", 5000)
        if dialog.wants_suggestions:
            self.suggest_glossary_terms()

    def suggest_glossary_terms(self) -> None:
        """Metinlerde sık geçen adları bulur, Ollama'dan karşılık ister; onaylananlar sözlüğe katılır."""
        if self.busy:
            return
        page = self.translate_page
        model = str(self.settings.value("ollama/model", ""))
        if str(self.settings.value("translate/provider", PROVIDER_OLLAMA)) != PROVIDER_OLLAMA or not model:
            page.show_notice(
                "warning",
                "Terim önerisi için Ollama gerekli. Önce “Makine Çevirisi…” penceresinde sağlayıcı olarak Ollama'yı "
                "ve bir model seçip bir iş başlatın (ayarlar kaydedilir); sonra Sözlük → Terim Öner'i yeniden deneyin.",
            )
            return
        candidates = find_candidates(self.project.translation_rows(), self.project.glossary())
        if not candidates:
            page.show_notice(
                "warning",
                "Metinlerde sözlüğe aday özel ad bulunamadı (en az iki kez, cümle ortasında büyük harfle geçen adlar "
                "aranır; sözlükte olanlar atlanır).",
            )
            return
        notes = self.project.setting("translation_notes")
        chosen = MachineSettings(PROVIDER_OLLAMA, str(self.settings.value("ollama/url", DEFAULT_URL)), model, notes)
        try:
            provider = self.provider_factory(chosen)
        except NxError as exc:
            page.show_notice("danger", exc.user_text())
            return
        if not isinstance(provider, OllamaProvider):
            page.show_notice("danger", "Terim önerisi yalnızca Ollama ile yapılabilir.")
            return
        source_lang = self.project.setting("source_language", "en")

        def work(ctx: TaskContext) -> list[TermSuggestion]:
            provider.cancel_token = ctx.token
            try:
                status = provider.test_connection()
                if not status.ok:
                    raise ProviderError(status.message)
                return suggest_glossary(provider, candidates, source_lang, notes, ctx)
            finally:
                provider.close()

        def finish(state: str, text: str) -> None:
            page.set_machine_running(False)
            page.show_notice(state, text)

        def done(result: object) -> None:
            assert isinstance(result, list)
            page.set_machine_running(False)
            if not result:
                page.show_notice(
                    "warning", f"Model {format_int(len(candidates))} aday için sözlüğe eklenecek terim önermedi."
                )
                return
            dialog = TermSuggestionsDialog(self, result)
            if dialog.exec() != TermSuggestionsDialog.DialogCode.Accepted or not dialog.selected():
                page.show_notice("success", "Sözlük önerileri eklenmedi.")
                return
            merged, added, updated = merge_terms(self.project.glossary(), dialog.selected())
            try:
                self.project.set_glossary(merged)
            except NxError as exc:
                page.show_notice("danger", exc.user_text())
                return
            self._mark_changed()
            self._sync_spell()
            page.show_notice(
                "success",
                f"Sözlüğe {format_int(added)} terim eklendi, {format_int(updated)} terim güncellendi. "
                "Yeni çeviriler bu karşılıkları kullanır.",
            )

        page.set_machine_running(True)
        page.show_notice("success", "")
        self._run(
            work,
            "Sözlük önerisi",
            on_success=done,
            on_failure=lambda text: finish("danger", text),
            on_progress=page.update_machine_progress,
            on_cancel=lambda: finish("warning", "Sözlük önerisi durduruldu; sözlük değişmedi."),
        )

    def edit_provider_settings(self) -> None:
        ProviderSettingsDialog(self, self.secrets).exec()

    def ask_machine_settings(
        self,
        scopes: Mapping[str, Sequence[TranslationRow]],
        action: str = ACTION_TRANSLATE,
        scope: str = SCOPE_ALL,
    ) -> MachineSettings | None:
        dialog = MachineDialog(
            self,
            provider=str(self.settings.value("translate/provider", PROVIDER_OLLAMA)),
            base_url=str(self.settings.value("ollama/url", DEFAULT_URL)),
            model=str(self.settings.value("ollama/model", "")),
            notes=self.project.setting("translation_notes"),
            source_language=self.project.setting("source_language", "en"),
            secrets=self.secrets,
            scopes=scopes,
            action=action,
            scope=scope,
            instruction=self.project.setting(REVISE_INSTRUCTION_KEY),
            translate_instruction=self.project.setting(TRANSLATE_INSTRUCTION_KEY),
        )
        if dialog.exec() != MachineDialog.DialogCode.Accepted:
            return None
        return dialog.settings()

    def _machine_scopes(self) -> dict[str, list[TranslationRow]]:
        """Pencerede sunulan kapsamlar: seçili satırlar, onların grupları, filtrelenen satırlar, tümü."""
        page = self.translate_page
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

    def _remember_machine_settings(self, chosen: MachineSettings) -> bool:
        self.settings.setValue("translate/provider", chosen.provider)
        self.settings.setValue("ollama/url", chosen.base_url)
        self.settings.setValue("ollama/model", chosen.model)
        self._refresh_status()
        try:
            self.project.set_setting("translation_notes", chosen.notes)
            if chosen.action == ACTION_REVISE:
                if chosen.instruction:
                    self.project.set_setting(REVISE_INSTRUCTION_KEY, chosen.instruction)
            elif chosen.provider == PROVIDER_OLLAMA:
                # Çeviri talimatı isteğe bağlıdır: kutu boşaltılınca saklanan talimat da silinir.
                self.project.set_setting(TRANSLATE_INSTRUCTION_KEY, chosen.instruction)
        except NxError as exc:
            QMessageBox.warning(self, "Proje", exc.user_text())
            return False
        return True

    def start_machine_translation(self, action: str = ACTION_TRANSLATE, from_selection: bool = False) -> None:
        """Çevir / yeniden çevir / talimatla düzelt penceresini açar ve seçilen işi başlatır."""
        if self.busy:
            return
        page = self.translate_page
        scopes = self._machine_scopes()
        chosen = self.ask_machine_settings(scopes, action, SCOPE_SELECTED if from_selection else SCOPE_ALL)
        if chosen is None or not self._remember_machine_settings(chosen):
            return
        target = target_rows(scopes.get(chosen.scope, []), chosen.action, chosen.include_approved)
        job = MachineJob(
            rows=target,
            source_lang=self.project.setting("source_language", "en"),
            notes=chosen.notes,
            glossary=self.project.glossary(),
            memory=self.project.memory_lookup(r.source for r in target) if chosen.action == ACTION_TRANSLATE else {},
            action=chosen.action,
            instruction=chosen.instruction,
            all_rows=self.project.translation_rows(),
        )
        self._launch_machine(
            chosen,
            job,
            set_running=page.set_machine_running,
            on_progress=page.update_machine_progress,
            report=page.show_notice,
        )

    def _launch_machine(
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
        job_id = job_id or new_job_id(job.action)
        try:
            provider = self.provider_factory(chosen)
        except NxError as exc:
            report("danger", exc.user_text())
            return
        set_running(True)
        report("success", "")

        def finish(text: str, state: str) -> None:
            set_running(False)
            self._reload_rows()  # filtrelere "Makine" durumu eklensin
            changed = self._set_last_job(job_id)
            if changed:
                text += (
                    f"\n\n{format_int(changed)} satırın önceki çevirisi değişti. Değişiklikleri görmek veya geri "
                    "almak için Çevir sayfasındaki “Son İşin Değişiklikleri” düğmesini kullanın."
                )
            report(state, text)
            if changed and job.action != ACTION_TRANSLATE:
                self.show_job_changes()

        def done(result: object) -> None:
            assert isinstance(result, RunSummary)
            finish(*describe_summary(job.action, result))

        resume = (
            "yeniden başlattığınızda kaldığı yerden devam eder."
            if job.action == ACTION_TRANSLATE
            else "kalan satırlar için işi yeniden başlatabilirsiniz."
        )
        self._run(
            lambda ctx: run_and_close(provider, job, ctx),
            JOB_TITLES[job.action],
            on_success=done,
            on_failure=lambda text: finish(text + f"\n\nO ana kadar yapılanlar kaydedildi; {resume}", "danger"),
            on_progress=on_progress,
            on_cancel=lambda: finish(f"İşlem durduruldu. O ana kadar yapılanlar kaydedildi; {resume}", "warning"),
            on_partial=lambda results: self._machine_results(results, chosen.include_approved, job_id),
        )

    # --- değişiklikler ve geçmiş -------------------------------------------------------------

    def _set_last_job(self, job_id: str) -> int:
        """Son işi hatırlar; işte değişen (geri alınmamış) satır sayısını döndürür."""
        self._last_job = job_id
        changes = self.project.job_changes(job_id)
        self.translate_page.set_last_changes({c.entry_id: c.old_text for c in changes})
        return len(changes)

    def _refresh_marks(self) -> None:
        """Durum sütunundaki "· redaksiyon" gibi işaretler: satırın son değişikliğini yapan iş."""
        marks = {eid: label for eid, job in self.project.last_jobs().items() if (label := mark_label(job))}
        self.translate_page.model.set_marks(marks)

    def show_job_changes(self) -> None:
        """Son işin değişikliklerini gösterir; işaretlenenler geri alınır."""
        if self._last_job is None:
            return
        changes = self.project.job_changes(self._last_job)
        if not changes:
            self.translate_page.set_last_changes({})
            self.translate_page.show_notice("success", "Son işte değişen (geri alınmamış) satır kalmadı.")
            return
        applied = (
            self._fix_report[1] if self._fix_report is not None and self._fix_report[0] == self._last_job else None
        )
        self._open_changes(ChangesDialog(self, f"{job_label(self._last_job)}: değişiklikler", changes, kinds=applied))

    def _to_translate_step(self) -> bool:
        if not self.translate_page.model.rows:
            return False
        self.nav.setCurrentRow(STEP_TRANSLATE)
        return True

    def _menu_search(self) -> None:
        if self._to_translate_step():
            self.translate_page.focus_search()

    def _menu_find(self) -> None:
        if self._to_translate_step():
            self.translate_page.open_find(False)

    def _menu_find_replace(self) -> None:
        if self._to_translate_step():
            self.translate_page.open_find(True)

    def _menu_next_open(self) -> None:
        if self._to_translate_step():
            self.translate_page.next_open()

    def _replace_translations(self, changes: list[tuple[int, str]]) -> list[TranslationRow] | None:
        """Bul ve Değiştir çubuğunun yazma yolu: her eylem tek iştir, Ctrl+Z hepsini geri alır.

        Onaylı satırlar onaylı kalır, diğerleri makine durumunda yazılır. Hata olursa None döner ve neden
        sayfada bildirilir.
        """
        if self.busy:
            return None
        page = self.translate_page
        job_id = new_job_id("replace")
        status = {r.id: r.status for r in page.model.rows}
        approved = [c for c in changes if status.get(c[0]) == Status.APPROVED]
        others = [c for c in changes if status.get(c[0]) != Status.APPROVED]
        try:
            rows = self.project.set_translations(approved, job=job_id)
            rows += self.project.set_translations(others, machine=True, job=job_id)
        except NxError as exc:
            page.show_notice("danger", exc.user_text())
            return None
        page.model.update_rows(rows)
        self._mark_changed()
        self._refresh_marks()
        self._set_last_job(job_id)
        return rows

    def show_row_history(self, entry_id: int) -> None:
        changes = self.project.row_history(entry_id)
        if not changes:
            self.translate_page.show_notice("success", "Bu satırın çevirisi henüz hiç değişmedi.")
            return
        self._open_changes(ChangesDialog(self, "Çeviri geçmişi", changes, history=True))

    def _open_changes(self, dialog: ChangesDialog) -> None:
        self.changes_dialog = dialog
        dialog.accepted.connect(lambda: self._revert(dialog.to_revert))
        dialog.open()  # pencereyi engellemez; kapanınca geri alma uygulanır

    def _revert(self, changes: list[Change]) -> None:
        if not changes or self.busy:
            return
        try:
            rows = self.project.revert(changes)
        except NxError as exc:
            self.translate_page.show_notice("danger", exc.user_text())
            return
        self.translate_page.model.update_rows(rows)
        self._mark_changed()
        self._refresh_marks()
        if self._last_job is not None:
            self._set_last_job(self._last_job)
        self.translate_page.show_notice(
            "success", f"{format_int(len(rows))} satır önceki çevirisine ve durumuna döndürüldü."
        )

    def _save_uppercase(self, rules: object) -> None:
        assert isinstance(rules, UppercaseRules)
        try:
            self.project.set_uppercase_rules(rules)
        except NxError as exc:
            QMessageBox.warning(self, "Proje", exc.user_text())
            self.translate_page.set_uppercase(self.project.uppercase_rules())
            return
        self._mark_changed()

    def _machine_results(self, results: object, overwrite_approved: bool = False, job_id: str = "") -> None:
        assert isinstance(results, list)
        try:
            rows = self.project.set_translations(
                results, machine=True, overwrite_approved=overwrite_approved, job=job_id or new_job_id("translate")
            )
        except NxError as exc:
            self.translate_page.show_notice("danger", exc.user_text())
            self._cancel_task()
            return
        page = self.translate_page
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
        self._mark_changed()

    def _update_undo_action(self) -> None:
        job = self.project.undo_job()
        self.undo_action.setText("Geri Al" if job is None else f"Geri Al: {job_label(job)}")
        self.undo_action.setEnabled(job is not None and not self.busy)

    def undo_last(self) -> None:
        """Çeviri tablosundaki son işlemi (elle düzenleme, onay, makine işi, bul-değiştir, içe aktarma …) geri alır."""
        page = self.translate_page
        if self.busy:
            page.show_notice("warning", "Bir iş sürerken geri alınamaz; iş bitince veya durdurulunca deneyin.")
            return
        try:
            result = self.project.undo()
        except NxError as exc:
            page.show_notice("danger", exc.user_text())
            return
        self._to_translate_step()
        if result is None:
            page.show_notice("warning", "Geri alınacak bir işlem yok.")
            return
        job, rows = result
        page.model.update_rows(rows)
        self._mark_changed()
        self._refresh_marks()
        if self._last_job is not None:
            self._set_last_job(self._last_job)
        if len(rows) == 1:
            page.select_row(rows[0].id)
        page.show_notice(
            "success", f"Geri alındı ({job_label(job)}): {format_int(len(rows))} satır önceki hâline döndü."
        )

    # --- dış dosya: dışa / içe aktarma (redaksiyon ve çeviri) ------------------------------------

    def export_csv(self) -> None:
        """Çevirileri dış redaksiyon için TXT/XLSX olarak dışa aktarır."""
        self._export_external(translation=False)

    def export_translation(self) -> None:
        """Çevirileri dış çeviri (çevirmen/model) için TXT/XLSX olarak dışa aktarır."""
        self._export_external(translation=True)

    def _export_external(self, *, translation: bool) -> None:
        page = self.translate_page
        if self.busy or not self._to_translate_step():
            return
        dialog = CsvExportDialog(
            self,
            selected=page.selected_rows(),
            visible=page.filtered_rows(),
            all_rows=page.model.rows,
            instruction=self.project.setting(REVISE_INSTRUCTION_KEY),
            mode=MODE_TRANSLATION if translation else MODE_REDACTION,
        )
        if dialog.exec() != CsvExportDialog.DialogCode.Accepted or not dialog.rows():
            return
        txt = dialog.format() == FORMAT_TXT
        suffix = ".txt" if txt else ".xlsx"
        name = self.project.path.stem if self.project.path else "ceviriler"
        if translation:
            name += "_ceviri"
        start = Path(str(self.settings.value("csv/dir", str(Path.home())))) / f"{name}{suffix}"
        filters = (
            "Metin dosyaları (*.txt);;Excel dosyaları (*.xlsx);;Tüm dosyalar (*)"
            if txt
            else "Excel dosyaları (*.xlsx);;Metin dosyaları (*.txt);;Tüm dosyalar (*)"
        )
        title = "Dış çeviri dosyasını kaydet" if translation else "Dış redaksiyon dosyasını kaydet"
        target, _ = QFileDialog.getSaveFileName(self, title, str(start), filters)
        if not target:
            return
        path = Path(target)
        if path.suffix.lower() != suffix:
            path = path.with_name(path.name + suffix)
        self.settings.setValue("csv/dir", str(path.parent))
        try:
            if translation:
                export = export_translation_txt if txt else export_translation_xlsx
            else:
                export = export_txt if txt else export_xlsx
            paths = export(dialog.rows(), path, dialog.part_rows(), by_group=dialog.by_group())
        except CsvError as exc:
            page.show_notice("danger", exc.user_text())
            return
        QGuiApplication.clipboard().setText(dialog.prompt.toPlainText())
        files = paths[0].name if len(paths) == 1 else f"{format_int(len(paths))} dosya ({paths[0].name} …)"
        if translation:
            shown = "TXT" if txt else "XLSX"
            page.show_notice(
                "success",
                f"{format_int(len(dialog.rows()))} satır {shown} çeviri dosyasına yazıldı: {files}. Çeviri istemi "
                "panoya kopyalandı. Çevrilen dosyaları Araçlar → “Dış Çeviriden İçe Aktar” ile geri yükleyin.",
            )
        else:
            page.show_notice(
                "success",
                f"{format_int(len(dialog.rows()))} satır yazıldı: {files}. Model için hazır istem panoya kopyalandı. "
                "Redakte edilen dosyaları Araçlar → “Dış Redaksiyondan İçe Aktar” ile geri yükleyin.",
            )

    def import_csv(self) -> None:
        """Redakte edilmiş dış TXT/XLSX/CSV dosyalarını projeye aktarır."""
        self._import_external(translation=False)

    def import_translation(self) -> None:
        """Dış çeviri dosyalarındaki yeni çevirileri projeye aktarır."""
        self._import_external(translation=True)

    def _import_external(self, *, translation: bool) -> None:
        page = self.translate_page
        if self.busy:
            return
        title = "Dış çeviriden içe aktar" if translation else "Dış redaksiyondan içe aktar"
        column = "yeni çeviri" if translation else "düzeltme"
        status_name = "Makine" if translation else "Redakte"
        job_kind = "translation" if translation else "csv"
        if not page.model.rows:
            QMessageBox.information(
                self,
                title,
                "Önce “Metinleri Tara” adımından metinleri çeviri tablosuna aktarın.",
            )
            return
        start = str(self.settings.value("csv/dir", str(Path.home())))
        pick_title = (
            "Çevrilmiş TXT, XLSX veya CSV dosyalarını seçin"
            if translation
            else "Redakte edilmiş TXT, XLSX veya CSV dosyalarını seçin"
        )
        targets, _ = QFileDialog.getOpenFileNames(
            self,
            pick_title,
            start,
            "TXT/XLSX/CSV dosyaları (*.txt *.xlsx *.csv);;Metin dosyaları (*.txt);;"
            "Excel dosyaları (*.xlsx);;CSV dosyaları (*.csv);;Tüm dosyalar (*)",
        )
        if not targets:
            return
        self.settings.setValue("csv/dir", str(Path(targets[0]).parent))
        try:
            csv_rows = [r for t in targets for r in read_revision_file(Path(t))]
        except CsvError as exc:
            QMessageBox.warning(self, title, exc.user_text())
            return
        rows = self.project.translation_rows()
        plan = plan_import(rows, csv_rows)
        labels = {r.id: r.context or r.key for r in rows}
        lines = [f"Dosyalarda {format_int(plan.found)} satır var."]
        if plan.no_correction:
            lines.append(
                f"{column.capitalize()} sütunu boş: {format_int(plan.no_correction)} satırın çevirisi değişmeyecek."
            )
        lines.append(
            f"Değişecek: {format_int(len(plan.changes))} satır (zaten aynı olan {format_int(plan.unchanged)})."
        )
        if plan.approved:
            lines.append(f"Değişenlerin {format_int(plan.approved)} tanesi onaylıydı; durumları “{status_name}” olur.")
        if plan.cleaned:
            lines.append(
                f"{format_int(plan.cleaned)} satırdaki fazla etiket veya bozuk kod yazımı programca düzeltildi."
            )
        skipped = []
        if plan.code_problems:
            skipped.append(f"{format_int(len(plan.code_problems))} satırın kontrol kodları uymuyor")
        if plan.source_mismatch:
            skipped.append(f"{format_int(len(plan.source_mismatch))} satırın orijinal metni projedekinden farklı")
        if plan.unknown:
            skipped.append(f"{format_int(plan.unknown)} satırın kimliği bu projede yok")
        if plan.unmatched:
            skipped.append(f"{format_int(plan.unmatched)} satır projedeki bir satırla eşleşmedi")
        if plan.empty:
            skipped.append(f"{format_int(plan.empty)} satırın çevirisi boş")
        if skipped:
            lines.append("Yazılmayacak: " + "; ".join(skipped) + ". Bu satırların mevcut çevirileri korunur.")
        for entry_id, problem in plan.code_problems[:5]:
            lines.append(f"  • {labels.get(entry_id, entry_id)}: {problem}")
        if len(plan.code_problems) > 5:
            lines.append(f"  … ve {format_int(len(plan.code_problems) - 5)} satır daha.")
        if plan.unknown and plan.unknown == plan.found:
            lines.append("\nDosya başka bir projeden dışa aktarılmış olabilir.")
        if plan.unmatched and plan.unmatched == plan.found:
            lines.append(
                "\nDosya başka bir projeden dışa aktarılmış veya orijinal/çeviri metinleri değiştirilmiş olabilir."
            )
        if not plan.changes:
            QMessageBox.information(self, title, "Yazılacak bir değişiklik yok.\n\n" + "\n".join(lines))
            return
        lines.append(
            f"Değişiklikler “{status_name}” durumuyla yazılır; “Son İşin Değişiklikleri” veya Ctrl+Z ile geri "
            "alabilirsiniz."
        )
        changed = dict(plan.changes)
        preview = [
            Change(
                row.id,
                labels.get(row.id, row.key),
                row.source,
                row.translation,
                row.status,
                row.note,
                changed[row.id],
                job_kind,
                "",
            )
            for row in rows
            if row.id in changed
        ]
        dialog = ChangesDialog(self, title, preview, preview=True, summary=lines)
        if dialog.exec() != ChangesDialog.DialogCode.Accepted:
            return
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
            QMessageBox.information(self, title, note)
            return
        job_id = new_job_id(job_kind)
        try:
            updated = self.project.set_translations(
                applied,
                status=None if translation else Status.REDACTED,
                machine=translation,
                overwrite_approved=True,
                job=job_id,
            )
        except NxError as exc:
            QMessageBox.warning(self, title, exc.user_text())
            return
        page.model.update_rows(updated)
        self._mark_changed()
        self._refresh_marks()
        count = self._set_last_job(job_id)
        self._to_translate_step()
        source_word = "dış çeviriden" if translation else "dış redaksiyondan"
        text = f"{format_int(count)} satırın çevirisi {source_word} güncellendi."
        skipped_count = len(plan.code_problems) + len(edit_problems)
        if skipped_count:
            text += f" {format_int(skipped_count)} satır kontrol kodları uymadığı için yazılmadı."
        page.show_notice("success" if not skipped_count else "warning", text)

    def unapprove(self, ids: list[int]) -> None:
        try:
            rows = self.project.unapprove(ids)
        except NxError as exc:
            self.translate_page.show_notice("danger", exc.user_text())
            return
        self.translate_page.model.update_rows(rows)
        self._mark_changed()
        self.translate_page.show_notice(
            "success",
            f"{format_int(len(rows))} satırın onayı kaldırıldı; yeniden çeviri ve redaksiyon artık bu satırlara da "
            "uygulanır.",
        )

    def _commit_translations(self, changes: list[tuple[int, str]]) -> list[TranslationRow]:
        rows = self.project.set_translations(changes)
        marks = dict(self.translate_page.model.marks)
        for r in rows:
            marks.pop(r.id, None)  # elle düzenlenen satırın son değişikliği artık kullanıcınındır
        self.translate_page.model.set_marks(marks)
        self._mark_changed()
        return rows

    # --- proje -----------------------------------------------------------------------------

    def _confirm_discard(self) -> bool:
        """Kaydedilmemiş değişiklik varsa kullanıcıya sorar. Devam edilebilirse True."""
        if not self.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Kaydedilmemiş proje",
            "Projede kaydedilmemiş değişiklikler var. Kaydetmek ister misiniz?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project()
        return answer == QMessageBox.StandardButton.Discard

    def new_project(self) -> None:
        if self.busy or not self._confirm_discard():
            return
        self._replace_project(Project.new())

    def _replace_project(self, project: Project) -> None:
        # Panelde bekleyen metin, satır kimlikleri başka projeye karışmasın diye eski projeye yazılır.
        self.translate_page.flush_pending()
        self.project.close()
        self.recovery.clear()  # önceki proje kaydedildi ya da kullanıcı ondan vazgeçti
        self._recovery_due = False
        self.project = project
        self.sources = project.sources()
        self.report = project.latest_scan()
        self.translate_page.set_uppercase(project.uppercase_rules())
        self._last_job = None
        self.translate_page.set_last_changes({})
        self._refresh_marks()
        self._push_fit_to_page()
        self.translate_page.set_qa_issues([], [])  # önceki projenin denetim sonuçları taşınmaz
        self.translate_page.set_project_key(
            str(project.path) if project.path else None
        )  # süzgeçler projeye göre hatırlanır
        self.translate_page.set_rows(project.translation_rows())
        self._sync_spell()
        self.font_report = None
        self.last_export = None
        self.dirty = False
        self.add_page.set_files_message("warning", "")
        self.nav.setCurrentRow(STEP_ADD)
        self._refresh()

    def _open_project_dialog(self) -> None:
        if self.busy or not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Proje aç",
            str(self.settings.value("ui/project_dir", str(Path.home()))),
            f"NXTR projesi (*{PROJECT_SUFFIX})",
        )
        if path:
            self.open_project(Path(path))

    def open_project(self, path: Path) -> bool:
        try:
            project = Project.open(path)
        except NxError as exc:
            QMessageBox.warning(self, "Proje açılamadı", exc.user_text())
            return False
        self.settings.setValue("ui/project_dir", str(path.parent))
        self._replace_project(project)
        self.recent.remember(path)
        missing = [s.path.name for s in self.sources if not s.path.is_file()]
        notes = []
        if missing:
            notes.append(
                "Projedeki bazı oyun dosyaları bulunamadı: "
                + ", ".join(missing)
                + ". Dosyaları taşıdıysanız listeden kaldırıp yeniden ekleyin."
            )
        notes += plugin_warnings(self.project)
        if notes:
            self.add_page.set_files_message("warning", " ".join(notes))
        self.statusBar().showMessage(f"Proje açıldı: {path.name}", 5000)
        return True

    def save_project(self) -> bool:
        if self.project.path is None:
            return self.save_project_as()
        self.statusBar().showMessage("Tüm değişiklikler proje dosyasına kaydedildi.", 4000)
        return True

    def save_project_as(self) -> bool:
        if self.busy:
            return False
        suggested = self.report.game_name if self.report and self.report.game_name else "Yeni Çeviri Projesi"
        start = Path(str(self.settings.value("ui/project_dir", str(Path.home())))) / f"{suggested}{PROJECT_SUFFIX}"
        path, _ = QFileDialog.getSaveFileName(self, "Projeyi kaydet", str(start), f"NXTR projesi (*{PROJECT_SUFFIX})")
        if not path:
            return False
        return self.save_to(Path(path))

    def save_to(self, path: Path) -> bool:
        try:
            self.project.save_as(path)
        except NxError as exc:
            QMessageBox.warning(self, "Proje kaydedilemedi", exc.user_text())
            return False
        assert self.project.path is not None
        self.settings.setValue("ui/project_dir", str(self.project.path.parent))
        self.recent.remember(self.project.path)
        self.recovery.clear()
        self._recovery_due = False
        self.dirty = False
        self._refresh()
        self.statusBar().showMessage(f"Proje kaydedildi: {self.project.path}", 5000)
        return True

    def _clear_cache(self) -> None:
        cache = self._cache_dir()
        size = dir_size(cache)
        if size == 0:
            QMessageBox.information(self, "Önbellek", f"Önbellek boş.\n\nKonum: {cache}")
            return
        answer = QMessageBox.question(
            self,
            "Önbelleği temizle",
            f"Önbellek {format_size(size)} yer kaplıyor.\n\nKonum: {cache}\n\n"
            "Silinen veriler gerektiğinde oyun dosyalarından yeniden oluşturulur. Silinsin mi?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            clear_cache(cache)
        except NxError as exc:
            QMessageBox.warning(self, "Önbellek", exc.user_text())
            return
        self.statusBar().showMessage(f"Önbellek temizlendi ({format_size(size)}).", 5000)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.translate_page.flush_pending()  # panelde yazılıp kaydedilmemiş metin kaybolmasın
        if self._update_task is not None:
            self._update_task.wait()  # ağ zaman aşımlarıyla sınırlı; çalışan iş parçacığı yok edilemez
        if self.busy:
            answer = QMessageBox.question(
                self, "İşlem sürüyor", "Bir işlem devam ediyor. İptal edip çıkmak istiyor musunuz?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            assert self.task is not None
            self.task.cancel()
            self.task.wait()
        if not self._confirm_discard():
            event.ignore()
            return
        self._recovery_timer.stop()
        self.provider_probe.close()
        self.recovery.clear()
        self.project.close()
        event.accept()

    # --- kurtarma ve son projeler ----------------------------------------------------------

    def write_recovery(self) -> None:
        """Kaydedilmemiş projede değişiklik varsa kurtarma kopyasını yeniler (arayüz iş parçacığında, hızlı)."""
        if self.project.path is not None or not self.dirty or not self._recovery_due:
            return
        if self.recovery.write(self.project):
            self._recovery_due = False

    def offer_recovery(self) -> bool:
        """Önceki oturumdan kalmış kurtarma kopyası varsa kurtarılmasını önerir. Proje kurtarıldıysa True."""
        files = leftover_files(self.recovery.folder)
        if not files:
            return False
        choice = self.ask_recovery(files[0], len(files))
        if choice == "recover":
            return self.recover_from(files[0])
        if choice == "discard":
            discard(files[0].path)
        return False

    def ask_recovery(self, newest: RecoveryFile, count: int) -> str:
        """ "recover", "discard" ya da "later" (testlerde değiştirilir)."""
        box = QMessageBox(self)
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
        try:
            project = Project.open_copy(leftover.path)
        except NxError as exc:
            QMessageBox.warning(self, "Proje kurtarılamadı", exc.user_text())
            return False
        self._replace_project(project)
        self.dirty = True
        self._recovery_due = True
        self.write_recovery()  # kopya artık bu pencerenin; eskisi silinebilir
        discard(leftover.path)
        self._refresh()
        self.statusBar().showMessage("Proje kurtarıldı. Kaydetmeyi unutmayın.", 8000)
        return True

    def recent_projects(self) -> list[Path]:
        return self.recent.paths()

    def _fill_recent_menu(self) -> None:
        self.recent.fill_menu(self.recent_menu, self.open_recent)

    def open_recent(self, path: Path) -> None:
        if self.busy or not self._confirm_discard():
            return
        self.open_project(path)
