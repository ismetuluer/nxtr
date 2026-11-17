"""Ana pencere: adım gezgini, menüler, proje yönetimi ve arka plan görevleri."""

from __future__ import annotations

import html
import json
import logging
import os
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path

import httpx
from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri import __version__
from nxceviri.arac.teshis import RAPOR_ADI, UYARI, rapor_uret
from nxceviri.core.archives.access import MemberReader
from nxceviri.core.errors import NxError
from nxceviri.core.export.layeredfs import (
    INFO_FILE,
)
from nxceviri.core.formats.derived import GraphicsSupport, graphics_status
from nxceviri.core.formats.registry import (
    BUILTIN_PLUGINS,
    load_user_plugins,
    plugin_for_kind,
    user_plugin_report,
)
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
)
from nxceviri.core.plugins.loader import PluginInfo, PluginReport
from nxceviri.core.plugins.record import record_extraction
from nxceviri.core.plugins.trust import PluginTrust
from nxceviri.core.progress import ProgressCallback, TaskContext
from nxceviri.core.project import Change, Project, SourceRecord, TranslationRow, row_group
from nxceviri.core.qa import ignored, transliterate
from nxceviri.core.qa.autofix import FixPlan, plan_reflow
from nxceviri.core.qa.checks import (
    QaIssue,
    glossary_words,
    spell_extra_words,
)
from nxceviri.core.qa.fixrun import FixSettings
from nxceviri.core.qa.fonts import FontReport, looks_like_font
from nxceviri.core.qa.fonts import scan_fonts as scan_font_files
from nxceviri.core.qa.live import SETTING_KEY as LIVE_KINDS_KEY
from nxceviri.core.qa.live import LiveContext, format_live_kinds, parse_live_kinds
from nxceviri.core.qa.terms import implicit_terms
from nxceviri.core.secrets import DEEPL_API_KEY, GITHUB_UPDATE_KEY, KeyringStore, SecretStore
from nxceviri.core.selfupdate import PreparedInstall, current_install, discard_prepared, launch_installer
from nxceviri.core.spell.checker import SpellChecker, turkish_lower
from nxceviri.core.spell.loader import load_spell_checker
from nxceviri.core.spell.report import UnknownWordCache, replace_unknown
from nxceviri.core.spell.suggest import Suggestion, suggestions
from nxceviri.core.spell.userdict import UserDictionary, default_user_dictionary_path
from nxceviri.core.translate.codekinds import suspected_line_breaks
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
from nxceviri.core.translate.glossary_io import merge_terms, plan_terms_from_rows
from nxceviri.core.translate.origin import MEMORY_ORIGIN, NO_ORIGIN, MachineOrigin
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
    memory_filled_ids,
    target_rows,
)
from nxceviri.core.translate.status import TRANSLATED_STATUSES, Status
from nxceviri.core.translate.terms import TermCandidate, TermSuggestion, find_candidates, suggest_glossary
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
from nxceviri.gui import motion
from nxceviri.gui.add_game_page import AddGamePage
from nxceviri.gui.changes_dialog import ChangesDialog
from nxceviri.gui.checks_controller import ChecksController
from nxceviri.gui.csv_dialog import FORMAT_TXT, MODE_REDACTION, MODE_TRANSLATION, CsvExportDialog
from nxceviri.gui.export_controller import ExportController
from nxceviri.gui.export_page import ExportPage
from nxceviri.gui.help_window import STEP_TOPICS, TOPIC_START, HelpWindow
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.jobs import JOB_TITLES, describe_summary, new_job_id, run_and_close, short_summary
from nxceviri.gui.machine_dialogs import (
    PROVIDER_DEEPL,
    PROVIDER_OLLAMA,
    SCOPE_ALL,
    SCOPE_FILTERED,
    SCOPE_GROUPS,
    SCOPE_PATTERN,
    SCOPE_SELECTED,
    AddTermsDialog,
    GlossaryDialog,
    MachineDialog,
    MachineSettings,
    TermSuggestionsDialog,
    make_provider,
    rows_matching,
)
from nxceviri.gui.mascot import (
    MOOD_DONE,
    MOOD_ERROR,
    MOOD_IDLE,
    MOOD_SLEEP,
    MOOD_WORKING,
    MascotWidget,
    mascot_setting,
    set_mascot_enabled,
)
from nxceviri.gui.menus import Menus
from nxceviri.gui.motion import animations_enabled
from nxceviri.gui.notify import (
    KEY_CARD_SECONDS,
    LEVEL_ERROR,
    LEVEL_INFO,
    LEVEL_SUCCESS,
    LEVEL_WARNING,
    LONG_TASK_S,
    NOTICE_DETAIL_CHARS,
    HistoryButton,
    NoticeAction,
    NotificationCenter,
    split_notice,
)
from nxceviri.gui.plugin_approval import ask_approval, offer_pending
from nxceviri.gui.plugins_dialog import PluginsDialog
from nxceviri.gui.project_controller import ProjectController
from nxceviri.gui.provider_probe import ProviderProbe
from nxceviri.gui.qa_page import QaPage
from nxceviri.gui.recent import RecentProjects
from nxceviri.gui.recovery import RecoveryFile, RecoveryKeeper, default_recovery_dir
from nxceviri.gui.scan_page import ScanPage
from nxceviri.gui.settings_dialog import KEY_SPELL_COPIED, PAGE_PROVIDERS, PAGE_VIEW, SettingsDialog
from nxceviri.gui.shortcuts import ShortcutRegistry
from nxceviri.gui.spell_dialogs import AddSpellWordsDialog, UserDictionaryDialog
from nxceviri.gui.spell_window import SpellWindow
from nxceviri.gui.spring import SPRING_SOFT, SpringAnimator
from nxceviri.gui.statusbar import StatusSegments
from nxceviri.gui.step_nav import (
    COLLAPSED_WIDTH,
    STEP_ADD,
    STEP_EXPORT,
    STEP_QA,
    STEP_SCAN,
    STEP_TRANSLATE,
    ProjectHeader,
    StepNav,
)
from nxceviri.gui.tasks import Task, release_thread
from nxceviri.gui.theme import (
    DEFAULT_FONT_SIZE,
    FONT_SIZES,
    ThemeMode,
    apply_theme,
    clamp_font_size,
)
from nxceviri.gui.translate_page import TranslatePage
from nxceviri.gui.update_dialog import UpdateDialog, UpdaterFactory, auto_check_enabled
from nxceviri.gui.widgets import button, format_int, format_size, tip_html

#: Modülün dışa verdiği adlar; adım sabitleri `step_nav`'da tanımlıdır, buradan da alınabilsinler diye yeniden verilir.
__all__ = [
    "MANUAL_LIMIT_KEY",
    "MASCOT_SLEEP_S",
    "STEP_ADD",
    "STEP_EXPORT",
    "STEP_QA",
    "STEP_SCAN",
    "STEP_TRANSLATE",
    "MainWindow",
    "ask_full_folder",
    "build_save_box",
    "choose_button",
    "log_dir",
]

log = logging.getLogger(__name__)

APP_TITLE = "NXTR"
#: Proje ayarı: son kullanılan redaksiyon talimatı (pencere bir sonraki açılışta bunu önerir).
#: Projenin ayar tablosunda "Elle sınır" (çeviri panelinin satır sınırı); 0 = kapalı.
MANUAL_LIMIT_KEY = "translate_manual_limit"
REVISE_INSTRUCTION_KEY = "revise_instruction"
TRANSLATE_INSTRUCTION_KEY = "translate_instruction"


#: Kaydedilmemiş projenin kurtarma kopyasının yenilenme aralığı.
RECOVERY_INTERVAL_MS = 60_000
#: Satırlar değişince açık Yazım Denetimi penceresinin tazelenmesi için toplama süresi.
SPELL_REFRESH_MS = 300
#: Yazım Denetimi penceresinde bu kadardan çok satır yeniden taranacaksa tarama arka planda yapılır.
SPELL_SYNC_ROWS = 2000
#: Yazım Denetimi penceresinde satır önizlemesinin en çok karakteri.
PREVIEW_CHARS = 80
#: Bu genişlikten dar pencerede kenar çubuğu ilk açılışta daralmış başlar.
NAV_AUTO_COLLAPSE_BELOW = 1000
#: Kenar çubuğu daralma/açılma animasyonunun süresi (ms).
#: Kenar çubuğu daralt/genişlet düğmesinin boyu ve kenar boşluğu (simgelerle hizalı).
NAV_TOGGLE_SIZE = 32
NAV_TOGGLE_MARGIN = 14
#: Sağlayıcı durumu sorgularının zaman aşımı (sn); arka plandadır ama ipucunu uzun bekletmez.
PROBE_TIMEOUT_S = 2.0


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NXCeviri" / "logs"


def _preview(text: str) -> str:
    """Satır listesinde gösterilecek kısa çeviri metni (boşluklar tek, uzunsa kesilir)."""
    flat = " ".join(text.split())
    return flat if len(flat) <= PREVIEW_CHARS else flat[: PREVIEW_CHARS - 1] + "…"


#: Proje ayarı: içe alınmış düzenli fontlar (JSON: RomFS yolu → kullanıcının dosyası).
FONT_OVERRIDES_KEY = "font_overrides"

#: Arka plan işinin bildirimdeki adı ("<ad> bitti / başarısız / durduruldu"); yoksa işin açıklaması kullanılır.
_TASK_LABELS = {
    "Oyun dosyaları okunuyor": "Oyun dosyalarını okuma",
    "Dosyalar çıkarılıyor": "Dosya çıkarma",
    "Teşhis raporu hazırlanıyor": "Teşhis raporu",
    "Fontlar taranıyor": "Font tarama",
    "Denetim yenileniyor": "Denetim",
    "Düzeltmeler hazırlanıyor": "Düzeltme",
    "Mod oluşturuluyor": "Dışa aktarma",
    "Font dışa aktarılıyor": "Font dışa aktarma",
    "Görseller çıkarılıyor": "Görsel çıkarma",
    "Hazır çeviri okunuyor": "Hazır çeviriyi içe aktarma",
    "Metinler çıkarılıyor": "Metin aktarma",
}


def choose_button(parent: QWidget, text: str, buttons: list[str]) -> str:
    """Soru penceresi: verilen düğmelerden hangisine basıldı (kapatılırsa son düğme, "Vazgeç")."""
    box = QMessageBox(QMessageBox.Icon.Question, "Dışa aktar", text, parent=parent)
    made = [box.addButton(label, QMessageBox.ButtonRole.ActionRole) for label in buttons]
    box.setDefaultButton(made[0])
    box.exec()
    clicked = box.clickedButton()
    return next((label for label, b in zip(buttons, made, strict=True) if b is clicked), buttons[-1])


def build_save_box(parent: QWidget, closing: bool) -> tuple[QMessageBox, QPushButton, QPushButton]:
    """Kaydedilmemiş değişiklik sorusu: (pencere, "Evet" düğmesi, "Hayır" düğmesi); "İptal" Esc ve çarpı düğmesidir."""
    when = "Çıkmadan önce" if closing else "Devam etmeden önce"
    box = QMessageBox(
        QMessageBox.Icon.Question,
        "Kaydedilmemiş değişiklikler",
        f"Projede kaydedilmemiş değişiklikler var. {when} kaydedilsin mi?",
        parent=parent,
    )
    save = box.addButton("Evet", QMessageBox.ButtonRole.AcceptRole)
    discard_button = box.addButton("Hayır", QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton("İptal", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(save)
    box.setEscapeButton(cancel)
    return box, save, discard_button


def ask_full_folder(parent: QWidget, dest: Path) -> str:
    """Hedef doluysa ne yapılacağını sorar: "empty" (sorun yok), "overwrite", "other" ya da "cancel".

    Üzerine yazma yalnızca NXTR'nin ürettiği (bilgi dosyası olan) mod klasörü için önerilir; başka bir klasör silinmez.
    """
    if not dest.exists() or (dest.is_dir() and not any(dest.iterdir())):
        return "empty"
    if (dest / INFO_FILE).is_file():
        choice = choose_button(
            parent,
            f"“{dest.name}” klasöründe daha önce üretilmiş bir mod var. Eski mod silinip yenisi yazılsın mı?",
            ["Üzerine Yaz", "Başka Klasör…", "Vazgeç"],
        )
    else:
        choice = choose_button(
            parent,
            f"“{dest.name}” klasörü dolu ve NXTR'nin ürettiği bir mod değil; güvenlik için silinmez. "
            "Başka bir klasör seçin.",
            ["Başka Klasör…", "Vazgeç"],
        )
    return {"Üzerine Yaz": "overwrite", "Başka Klasör…": "other"}.get(choice, "cancel")


#: Maskot: "bitti" ve "hata" hâllerinin süresi (ms); sistem bu kadar saniye boştaysa uyur; boşta denetim aralığı (ms).
MASCOT_DONE_MS = 4000
MASCOT_ERROR_MS = 10000
MASCOT_SLEEP_S = 5 * 60
MASCOT_POLL_MS = 5000


class MainWindow(QMainWindow):
    # Menü çubuğunun (`menus.Menus`) kurduğu eylemler.
    recent_menu: QMenu
    save_action: QAction
    keys_action: QAction
    title_keys_clear_action: QAction
    cache_action: QAction
    nav_action: QAction
    size_group: QActionGroup
    theme_group: QActionGroup
    undo_action: QAction
    redo_action: QAction
    update_action: QAction

    def __init__(self, settings: QSettings) -> None:
        super().__init__()
        self.settings = settings
        set_mascot_enabled(mascot_setting(settings))  # sayfalar (boş ekran maskotları) kurulmadan önce
        #: Kısayolların tek kaynağı (komut kataloğu + kullanıcının değiştirdiği tuşlar).
        self.shortcuts = ShortcutRegistry(self)
        self.shortcuts.bind_settings(settings)
        self.keys: KeySet | None = None
        self.title_keys: dict[bytes, bytes] | None = None
        self.title_keys_path: Path | None = None
        self._keys_detail = ""
        self.sources: list[SourceRecord] = []
        self.report: ScanReport | None = None
        self._confirmed_removals: set[str] = (
            set()
        )  # son aktarmada kullanıcının kaldırılmasını onayladığı proje dosyaları
        self.project = Project.new()
        self.dirty = False
        self.task: Task | None = None
        self.font_report: FontReport | None = None
        self.last_export: Path | None = None
        #: Kontrol Et adımının iş akışı (denetim, pano, yok sayma, Düzelt); durumu da orada tutulur.
        self.checks = ChecksController(self)
        #: Dışa Aktar adımının iş akışı (özet, hedef klasör, mod oluşturma); durum pencerede kalır.
        self.exporter = ExportController(self)
        #: Proje yaşam döngüsü (yeni, aç, kaydet, son projeler, kurtarma); durum pencerede kalır.
        self.projects = ProjectController(self)
        #: Çeviri satırları her yeniden kurulduğunda artar; satırlara bağlı ağır hesapların önbelleği buna bağlıdır.
        self._rows_version = 0
        self._fit_lists_cache: tuple[int, list[str], list[str], list[str]] | None = None
        self._limits_key: tuple[object, ...] | None = None
        self._live_context: LiveContext | None = None
        #: Açık Yazım Denetimi penceresi için satır başına bilinmeyen sözcükler (yalnızca değişen satırlar taranır).
        self._spell_cache = UnknownWordCache()
        #: (sözcük, tek düzenleme de arandı mı) → öneri; yazım ya da oyun sözlüğü, yoksayılanlar değişince silinir.
        self._spell_hints: dict[tuple[str, bool], Suggestion] = {}
        self._spell_extra_key: frozenset[str] | None = None
        self._spell_scan: Task | None = None
        self._spell_scan_ok = False
        #: Sığdırma ayarı değişince art arda değişiklikler tek denetimde toplanır.
        self._fit_recheck_timer = QTimer(self)
        self._fit_recheck_timer.setSingleShot(True)
        self._fit_recheck_timer.setInterval(500)
        self._fit_recheck_timer.timeout.connect(self._fit_recheck_due)
        #: Kalıcı kullanıcı sözlüğü ve Türkçe yazım denetleyicisi (paketlenen süzgeç eksikse None: denetim kapalı).
        self.user_dictionary = UserDictionary(default_user_dictionary_path())
        self.spell: SpellChecker | None = load_spell_checker(self.user_dictionary)
        self._apply_spell_copied()
        self._live_kinds = self._load_live_kinds()
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
        self.plugin_trust = PluginTrust()  # yalnızca kullanıcı bir eklentiyi onaylayınca yazılır
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
        self._nav_anim: SpringAnimator | None = None
        self._nav_collapsed = self._initial_nav_collapsed()
        self.nav.set_collapsed(self._nav_collapsed)
        self.nav_header.setVisible(not self._nav_collapsed)
        self.nav.preferred_width_changed.connect(self._update_nav_width)
        column.addWidget(self.nav_header)
        column.addWidget(self.nav, 1)
        # Görünür daralt/genişlet düğmesi (menü ve Ctrl+Alt+S'nin yanında): daralmış hâlde de görünür kalır.
        self.nav_toggle = QToolButton()
        self.nav_toggle.setProperty("role", "viewTool")
        self.nav_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.nav_toggle.setFixedSize(NAV_TOGGLE_SIZE, NAV_TOGGLE_SIZE)
        bind_icon(self.nav_toggle, "panel-left", size=18)
        self.nav_toggle.clicked.connect(lambda: self.set_nav_collapsed(not self._nav_collapsed))
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(NAV_TOGGLE_MARGIN, 4, NAV_TOGGLE_MARGIN, 12)
        toggle_row.addWidget(self.nav_toggle)
        toggle_row.addStretch(1)
        column.addLayout(toggle_row)
        self._refresh_nav_toggle()
        root.addWidget(self.nav_column)
        self._update_nav_width()
        self.pages = QStackedWidget()
        self.add_page = AddGamePage()
        self.scan_page = ScanPage()
        self.translate_page = TranslatePage(self.shortcuts)
        self.translate_page.model.commit = self._commit_translations
        self.translate_page.replace_fn = self._replace_translations
        self.translate_page.bind_settings(self.settings)
        self.pages.addWidget(self.add_page)
        self.pages.addWidget(self.scan_page)
        self.pages.addWidget(self.translate_page)
        self.qa_page = QaPage()
        self.qa_page.model.number_of = self.translate_page.model.number
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
        #: Bütün işlerin ve hataların sonucu buradan bildirilir (kart, geçmiş; arkadayken Windows bildirimi ve ses).
        self.notifier = NotificationCenter(self, self.settings)
        self.notice_button = HistoryButton(self.notifier)
        self.help_window: HelpWindow | None = None
        #: Maskot: işin durumunu gösterir (çalışıyor, bitti, hata; uzun boşta uyur). Ayarlar → Görünüm'den kapatılır.
        self.mascot = MascotWidget(20)
        self.statusBar().addPermanentWidget(self.mascot)
        self.statusBar().addPermanentWidget(self.notice_button)
        self._mascot_rest = QTimer(self)
        self._mascot_rest.setSingleShot(True)
        self._mascot_rest.timeout.connect(self._mascot_settle)
        #: Uyku/uyanma: sistemin boşta süresine birkaç saniyede bir bakılır (Qt olay süzgeci yok).
        self._mascot_poll = QTimer(self)
        self._mascot_poll.setInterval(MASCOT_POLL_MS)
        self._mascot_poll.timeout.connect(self._mascot_check_idle)
        self._mascot_poll.start()
        self.translate_page.notice_requested.connect(self._page_notice)
        self.translate_page.add_terms_requested.connect(self.add_rows_to_terminology)
        #: Bir işin sonucu işlenirken: bildirim gürültülü olsun mu (uzun iş) ve işleyici kendi bildirimini verdi mi.
        self._outcome_loud: bool | None = None
        self._outcome_noticed = False
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
        # Açık Yazım Denetimi penceresi, satırlar değişince 300 ms toplanarak tek seferde tazelenir.
        self._spell_window: SpellWindow | None = None
        self._spell_timer = QTimer(self)
        self._spell_timer.setSingleShot(True)
        self._spell_timer.setInterval(SPELL_REFRESH_MS)
        self._spell_timer.timeout.connect(self._refresh_spell_window)
        self._menu_timer = QTimer(self)
        self._menu_timer.setSingleShot(True)
        self._menu_timer.setInterval(0)
        self._menu_timer.timeout.connect(self.update_menu_state)
        self.translate_page.selection_changed.connect(self._menu_timer.start)
        self.translate_page.view_changed.connect(self._refresh_status)
        self.translate_page.manual_limit_changed.connect(self._save_manual_limit)
        self.translate_page.hint.connect(lambda text: self.statusBar().showMessage(text, 6000))
        self.translate_page.model.modelReset.connect(self._rows_replaced)
        self.translate_page.model.modelReset.connect(self._derived_timer.start)
        self.translate_page.model.modelReset.connect(self._spell_timer.start)
        self.translate_page.model.dataChanged.connect(lambda *_args: self._derived_timer.start())
        self.translate_page.model.dataChanged.connect(lambda *_args: self._spell_timer.start())

        self.nav.currentRowChanged.connect(self._go_to)
        self.add_page.choose_keys.connect(self._choose_keys)
        self.add_page.browse_files.connect(self._browse_files)
        self.add_page.add_files.connect(self.add_files)
        self.add_page.remove_source.connect(self._remove_source)
        self.add_page.next_step.connect(self._go_scan)
        self.add_page.open_recent.connect(self.open_recent)
        self.scan_page.start_scan.connect(self.start_scan)
        self.scan_page.cancel.connect(self._cancel_task)
        self.scan_page.go_back.connect(lambda: self.nav.setCurrentRow(STEP_ADD))
        self.scan_page.report.rescan_requested.connect(self.start_scan)
        self.scan_page.report.import_requested.connect(self.import_texts)
        self.translate_page.go_to_scan.connect(lambda: self.nav.setCurrentRow(STEP_SCAN))
        self.translate_page.machine_requested.connect(self.start_machine_translation)
        self.translate_page.uppercase_changed.connect(self._save_uppercase)
        self.translate_page.machine_action_requested.connect(lambda a: self.start_machine_translation(a, True))
        self.translate_page.pane.spell_word_requested.connect(lambda w: self.add_spell_words([w]))
        self.qa_page.add_spelling_requested.connect(self.add_spelling_from_qa)
        self.qa_page.not_term_requested.connect(self.ignore_terms)
        self.qa_page.ascii_choice_requested.connect(self.apply_ascii_choice)
        self.qa_page.ignore_requested.connect(self.ignore_issues)
        self.qa_page.unignore_requested.connect(self.unignore_issues)
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
        self.export_page.extract_graphics.connect(self.extract_graphics)
        self.export_page.open_graphics.connect(self.open_graphics)
        self.qa_page.font_export_requested.connect(self.export_font_file)
        self.qa_page.font_import_requested.connect(self.import_edited_font)
        self.qa_page.font_reset_requested.connect(self.reset_edited_font)
        self.qa_page.run_checks.connect(self.start_checks)
        self.qa_page.stop_checks.connect(self._stop_checks)
        self.qa_page.transliterate_changed.connect(self._set_transliterate)
        self.qa_page.font_patch_changed.connect(self._set_font_patch)
        self.qa_page.open_row.connect(self._open_row)
        self.qa_page.fix_requested.connect(self.apply_fixes)
        self.qa_page.fix_planner = self._plan_fix_bar
        self.qa_page.translation_edited.connect(self._edit_from_issues)
        self.qa_page.report_requested.connect(self.show_job_changes)
        self.qa_page.fix_notice.connect(self._fix_notice)
        self.qa_page.fit_changed.connect(self._save_fit)
        self.qa_page.learn_rules_requested.connect(self._learn_rules)
        self.qa_page.fit_tab_shown.connect(self._refresh_limits)
        self.export_page.choose_folder.connect(self._choose_export_folder)
        self.export_page.export_requested.connect(self.export_mod)
        self.export_page.include_errors_changed.connect(self._set_include_errors)
        self.export_page.open_folder.connect(self._open_export_folder)
        self.export_page.cancel.connect(self._cancel_task)

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
            self._nav_anim.deleteLater()  # durdurulan animasyon nesnesi pencereyle birlikte birikmesin
            self._nav_anim = None
        self._nav_collapsed = collapsed
        self._refresh_nav_toggle()
        target = self._nav_width()
        start = self.nav_column.width()
        if not (animate and self.isVisible() and animations_enabled()) or start == target:
            self._finish_nav(collapsed)
            return
        if not collapsed:  # açılırken önce ad ve başlık görünür, sonra genişlik büyür
            self.nav.set_collapsed(False)
            self.nav_header.setVisible(True)
        # Yay (designbookmark "Sidebar collapse"): süre yok, hareket yay dengeye gelince biter; az sönümlü olduğundan
        # hedefi hafif aşıp döner. Daralırken simge genişliğinin altına inilmez (simgeler kırpılmasın).
        anim = SpringAnimator(
            self,
            float(start),
            float(target),
            *SPRING_SOFT,
            on_value=lambda value: self.nav_column.setFixedWidth(max(COLLAPSED_WIDTH, round(value))),
            on_done=lambda: self._finish_nav(collapsed),
        )
        self._nav_anim = anim
        anim.start()

    def _finish_nav(self, collapsed: bool) -> None:
        if self._nav_anim is not None:
            self._nav_anim.deleteLater()
        self._nav_anim = None
        self.nav.set_collapsed(collapsed)
        self.nav_header.setVisible(not collapsed)
        self.nav_column.setFixedWidth(self._nav_width())

    def _refresh_nav_toggle(self) -> None:
        """Düğmenin ipucu: şu an ne yapacağını ve kısayolunu söyler."""
        key = self.shortcuts.text("view.nav")
        action = "Kenar çubuğunu genişlet" if self._nav_collapsed else "Kenar çubuğunu daralt"
        self.nav_toggle.setToolTip(f"{action} ({key})" if key else action)
        self.nav_toggle.setAccessibleName(action)  # ipucu gibi, o an yapacağı işi söyler

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and hasattr(self, "nav"):
            self._update_nav_width()

    # --- menüler -------------------------------------------------------------------------

    def _build_menus(self) -> None:
        self.menus = Menus(self)
        self.menus.build()

    @property
    def menu_actions(self) -> dict[str, QAction]:
        """Komut kimliği → menüdeki eylem (kısayolu kayıt defterine bağlı olanlar)."""
        return self.menus.actions

    def update_menu_state(self) -> None:
        """Menü öğelerinin etkinliğini projenin, açık sayfanın, seçimin ve süren işin durumuna göre günceller."""
        self.menus.refresh()

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
        for act in self.theme_group.actions():
            act.setChecked(act.data() == mode.value)

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
        PluginsDialog(
            self,
            report=user_plugin_report(),
            builtin=BUILTIN_PLUGINS,
            trust=self.plugin_trust,
            reload=lambda: None if self.busy else self.reload_plugins(),
        ).exec()

    def reload_plugins(self, dirs: Sequence[Path] | None = None) -> PluginReport:
        """Kayıt defterini onay denetimiyle yeniden yükler (yalnızca iş çalışmıyorken çağrılır)."""
        return load_user_plugins(dirs, self.plugin_trust.is_trusted)

    def offer_new_plugins(self, dirs: Sequence[Path] | None = None) -> None:
        """Açılışta: onay bekleyen her kullanıcı eklentisini bir kez sorar; onaylananlar hemen yüklenir."""
        if self.busy:
            return
        errors = offer_pending(
            user_plugin_report(), self.plugin_trust, self.ask_plugin_approval, lambda: self.reload_plugins(dirs)
        )
        for exc in errors:
            self.notify(LEVEL_ERROR, "Eklenti onayı kaydedilemedi", exc.user_text())

    def ask_plugin_approval(self, info: PluginInfo, changed: bool) -> bool:
        """Yeni/değişmiş eklenti sorusu; "Yükle" seçildiyse True (testlerde değiştirilir)."""
        return ask_approval(self, info, changed)

    def _open_logs(self) -> None:
        log_dir().mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "Hakkında",
            f"<b>{APP_TITLE}</b> {__version__}<br><br>"
            "Kendi sahip olduğunuz Switch oyunlarının metinlerini Türkçeye çevirmek için bir araç.<br><br>"
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
            self.notify(LEVEL_INFO, "Güncelleme hazır", "Önce süren işlemi bitirin veya iptal edin. " + later)
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
            self.notify(LEVEL_INFO, "Güncelleme hazır", "Önce süren işlemi bitirin veya iptal edin. " + retry)
            return False
        if not self._confirm_discard():
            self.statusBar().showMessage(retry, 10000)
            return False
        try:
            self.installer_launcher(prepared, install_dir)
        except UpdateError as exc:
            self.notify(LEVEL_ERROR, "Güncelleme", exc.user_text())
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

    def _test_notification(self) -> None:
        """Ayarlar → Bildirimler'deki deneme: seçili kanallarla (Windows bildirimi, ses) örnek bildirim."""
        self.notifier.notify(LEVEL_SUCCESS, "Deneme bildirimi", "Bildirimler böyle görünür.", loud=True)

    def notify_update_failure(self, reason: str) -> None:
        """Önceki güncelleme kurulamadıysa açılışta bildirir; Tekrar Dene güncelleme penceresini açar."""
        actions = (NoticeAction("Tekrar Dene", self.open_updates),) if self.update_action.isEnabled() else ()
        self.notifier.notify(LEVEL_ERROR, "Güncelleme kurulamadı", reason, actions, loud=True)

    def _update_checked(self, result: object) -> None:
        assert isinstance(result, UpdateInfo)
        if result.newer:
            self.update_badge.setText(f"Yeni sürüm: {result.version} — Güncelle")
            self.update_badge.show()
            self.notifier.notify(
                LEVEL_INFO,
                f"Yeni sürüm: {result.version}",
                "Yenilikleri görmek ve kurmak için Şimdi Güncelle'ye basın.",
                (NoticeAction("Şimdi Güncelle", self.open_updates), NoticeAction("Sonra", lambda: None)),
                loud=True,
            )

    # --- genel durum ---------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self.task is not None

    def _refresh(self) -> None:
        name = self.project.path.stem if self.project.path else "Kaydedilmemiş proje"
        self.setWindowTitle(f"{name}{' *' if self.dirty else ''} — {APP_TITLE}")
        self.add_page.set_sources(self.sources)
        self.add_page.set_recent(self.recent.paths())
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
        self.qa_page.check_button.setEnabled(not self.busy or self.qa_page.checking)
        self._refresh_nav()
        self._refresh_status()
        self.update_menu_state()

    def _pane_focus_changed(self, focused: bool) -> None:
        self._pane_focused = focused
        if not focused:
            self.status_segments.set_cursor(None, None)

    def _pane_cursor_moved(self, line: int, column: int) -> None:
        """İmleç konumu yalnızca panelin çeviri düzenleyicisi odaktayken durum çubuğunda görünür."""
        if self._pane_focused:
            self.status_segments.set_cursor(line, column)

    def _refresh_derived(self) -> None:
        """Tablodaki satırlardan türetilen göstergeler: kenar çubuğu rozetleri, durum çubuğu ve menü öğeleri."""
        self._refresh_nav()
        self._refresh_status()
        self._update_undo_action()
        self._update_redo_action()
        self.update_menu_state()

    def _open_qa_from_status(self) -> None:
        """Durum çubuğundaki "N hatalı" tıklaması; iş sürerken kenar çubuğu kilidi aşılmaz."""
        if not self.busy:
            self.nav.setCurrentRow(STEP_QA)

    def _refresh_status(self) -> None:
        """Durum çubuğu bölmeleri; satır sayıları, hatalı satırlar, sağlayıcı ve kayıt durumundan türetilir."""
        rows = self.translate_page.model.rows
        self.status_segments.update(
            rows=len(rows),
            shown=self.translate_page.filter.rowCount(),  # grup başlıkları ve katlama sayılmaz
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

    def _show_scan_report(self, report: ScanReport) -> None:
        """Tarama raporunu gösterir; varsayılan seçim projede aktarılmış dosyalara göre kurulur."""
        self.scan_page.show_report(report, [path for path, _tid, _fmt in self.project.text_files()])

    def _go_to(self, row: int) -> None:
        if row < 0:
            return
        self.pages.setCurrentIndex(row)
        self.update_menu_state()
        if row == STEP_SCAN and not self.busy:
            if self.report is not None:
                self._show_scan_report(self.report)
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
        started = time.monotonic()
        label = _TASK_LABELS.get(description, description)

        def retry() -> None:
            if not self.busy:
                self._run(
                    fn,
                    description,
                    on_success=on_success,
                    on_failure=on_failure,
                    on_progress=on_progress,
                    on_cancel=on_cancel,
                    on_partial=on_partial,
                )

        if on_progress is not None:
            task.progress.connect(on_progress)
        if on_partial is not None:
            task.partial.connect(on_partial)
        # Sonuç işleyicilerinden önce: işleyicinin vereceği bildirim uzun işte gürültülü olur.
        for signal in (task.succeeded, task.failed, task.cancelled):
            signal.connect(lambda *_a: self._begin_outcome(started))
        task.succeeded.connect(on_success)
        task.failed.connect(on_failure)
        if on_cancel is not None:
            task.cancelled.connect(on_cancel)
        # İşleyici kendi bildirimini vermediyse genel bildirim.
        task.succeeded.connect(lambda _r: self._end_outcome(LEVEL_SUCCESS, f"{label} bitti", ""))
        task.failed.connect(
            lambda text: self._end_outcome(
                LEVEL_ERROR, f"{label} başarısız", text, (NoticeAction("Tekrar Dene", retry),)
            )
        )
        task.cancelled.connect(lambda: self._end_outcome(LEVEL_WARNING, f"{label} durduruldu", ""))
        task.finished.connect(self._task_finished)
        self.statusBar().showMessage(description + "…")
        self._set_mascot(MOOD_WORKING)
        self._refresh()
        task.start()

    def notify(self, level: str, title: str, text: str = "", actions: tuple[NoticeAction, ...] = ()) -> None:
        """Kullanıcıya bildirim verir; bir işin sonucu işlenirken iş uzun sürdüyse gürültülüdür."""
        self._outcome_noticed = True
        if len(text) > NOTICE_DETAIL_CHARS or "\n" in text.strip():
            # Kart kısa kalır; uzun ya da çok satırlı açıklamanın tamamı ayrı pencerede.
            actions = (*actions, NoticeAction("Ayrıntılar", lambda: QMessageBox.information(self, title, text)))
        self.notifier.notify(level, title, text, actions, loud=self._outcome_loud)
        mood = {LEVEL_SUCCESS: MOOD_DONE, LEVEL_WARNING: MOOD_ERROR, LEVEL_ERROR: MOOD_ERROR}.get(level)
        if mood is not None:
            self._set_mascot(mood)

    def _begin_outcome(self, started: float) -> None:
        self._outcome_noticed = False
        self._outcome_loud = True if time.monotonic() - started >= LONG_TASK_S else None

    def _end_outcome(self, level: str, title: str, text: str, actions: tuple[NoticeAction, ...] = ()) -> None:
        if not self._outcome_noticed:
            self.notify(level, title, text, actions)
        self._outcome_loud = None
        self._outcome_noticed = False

    # --- yardım ------------------------------------------------------------------------------

    def open_help(self, topic: str | None = None) -> None:
        """Yardım penceresi (F1): konu verilmezse açık ekranın konusu."""
        if self.help_window is None:
            self.help_window = HelpWindow(self.shortcuts, self)
        self.help_window.show_topic(topic or STEP_TOPICS.get(self.nav.currentRow(), TOPIC_START))
        self.help_window.show()
        self.help_window.raise_()
        self.help_window.activateWindow()

    # --- maskot ------------------------------------------------------------------------------

    def _set_mascot(self, mood: str) -> None:
        """Maskotun hâli: "bitti" birkaç saniye, "hata" biraz daha uzun sürer, sonra işe ya da boşa döner."""
        self.mascot.set_mood(mood)
        self._mascot_rest.stop()
        if mood == MOOD_DONE:
            self._mascot_rest.start(MASCOT_DONE_MS)
        elif mood == MOOD_ERROR:
            self._mascot_rest.start(MASCOT_ERROR_MS)

    def _mascot_settle(self) -> None:
        self._set_mascot(MOOD_WORKING if self.busy else MOOD_IDLE)

    def _mascot_check_idle(self) -> None:
        """Sistem uzun süre boştaysa (iş yok) maskot uyur; kullanıcı dokununca uyanır."""
        idle = motion.idle_seconds()
        if self.mascot.mood == MOOD_SLEEP:
            if idle < MASCOT_POLL_MS / 1000:
                self.mascot.set_mood(MOOD_IDLE)
        elif idle >= MASCOT_SLEEP_S and not self.busy and self.mascot.mood == MOOD_IDLE:
            self.mascot.set_mood(MOOD_SLEEP)

    def _fix_notice(self, state: str, text: str, action: str) -> None:
        level = {"success": LEVEL_SUCCESS, "warning": LEVEL_WARNING, "danger": LEVEL_ERROR}.get(state, LEVEL_INFO)
        title, rest = split_notice(text)
        actions = (NoticeAction(action, self.show_job_changes),) if action else ()
        self.notify(level, title, rest, actions)

    def _page_notice(self, state: str, text: str) -> None:
        """Sayfaların kısa sonuç mesajları: uzun metin kartta başlık + özet olur, tamamı geçmişte ve ipucunda."""
        level = {"success": LEVEL_SUCCESS, "warning": LEVEL_WARNING, "danger": LEVEL_ERROR}.get(state, LEVEL_INFO)
        title, rest = split_notice(text)
        self.notify(level, title, rest)

    def _task_finished(self) -> None:
        if self.task is not None:
            release_thread(self.task)
        self.task = None
        self.statusBar().showMessage("Hazır")
        if self.mascot.mood == MOOD_WORKING:
            self._set_mascot(MOOD_IDLE)
        self.add_page.set_busy(False)
        self._refresh()
        if self.checks.pending_edits:
            self.checks.flush_pending_edits()  # iş sürerken Sorunlar'da yapılan düzenlemeler
        if self._recheck_pending:
            self._recheck_if_done()

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
            self.notify(LEVEL_ERROR, "Proje", exc.user_text())
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
            self.notify(LEVEL_ERROR, "Proje", exc.user_text())
        self._mark_changed()
        self._show_scan_report(result)
        self.statusBar().showMessage(f"Tarama {result.duration_s:.1f} saniyede tamamlandı.", 8000)

    def _scan_cancelled(self) -> None:
        if self.report is not None:
            self._show_scan_report(self.report)
        else:
            self.scan_page.show_empty()
        self.statusBar().showMessage("Tarama iptal edildi.", 5000)

    def _extract(self, mode: str) -> None:
        if self.busy or self.report is None or self.keys is None:
            return
        problems = check_sources(self.sources)
        if problems:
            self.notify(LEVEL_ERROR, "Dosyalar çıkarılamıyor", " ".join(problems))
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
            self._show_scan_report(report)
            self.notify(LEVEL_INFO, "Çıkarma tamamlandı", f"{result} dosya şuraya yazıldı:\n{dest}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest)))

        def failed(text: str) -> None:
            self._show_scan_report(report)
            self.notify(LEVEL_ERROR, "Çıkarma tamamlanamadı", text)

        def cancelled() -> None:
            self._show_scan_report(report)
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
        """Araçlar > Teşhis Raporu: oyunun yapısını inceleyen bir rapor yazar."""
        if self.busy or self.report is None or self.keys is None:
            return
        problems = check_sources(self.sources)
        if problems:
            self.notify(LEVEL_ERROR, "Teşhis raporu oluşturulamıyor", " ".join(problems))
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
            self._show_scan_report(report)
            self.notify(LEVEL_INFO, "Teşhis raporu hazır", f"{result}\n\n{UYARI}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest)))

        def failed(text: str) -> None:
            self._show_scan_report(report)
            self.notify(LEVEL_ERROR, "Teşhis raporu oluşturulamadı", text)

        def cancelled() -> None:
            self._show_scan_report(report)
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

    def _stored_font_overrides(self) -> dict[str, str]:
        """İçe alınmış düzenli fontlar: RomFS yolu → kullanıcının dosyası (proje ayarı; bozuksa boş)."""
        try:
            data = json.loads(self.project.setting(FONT_OVERRIDES_KEY) or "{}")
        except ValueError:
            log.warning("İçe alınan font ayarı bozuk; yok sayıldı")
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _save_font_overrides(self, overrides: dict[str, str]) -> None:
        self.project.set_setting(FONT_OVERRIDES_KEY, json.dumps(overrides, ensure_ascii=False))
        self._mark_changed()
        self.qa_page.set_font_overrides(overrides)

    def _title_id_hex(self) -> str:
        """Modun klasör adı olan TitleID (metin dosyalarınınki; yoksa projeninki)."""
        files = self.project.text_files()
        return str(files[0][1]) if files else self.project.title_id

    def _font_overrides(self) -> dict[str, dict[str, bytes]]:
        """Dışa aktarmada moda konacak düzenli fontlar; dosyası bulunamayan atlanır ve bildirilir."""
        found: dict[str, bytes] = {}
        lost: list[str] = []
        for source, stored in self._stored_font_overrides().items():
            try:
                found[source] = Path(stored).read_bytes()
            except OSError:
                lost.append(Path(stored).name)
        if lost:
            self.notify(
                LEVEL_WARNING,
                "İçe alınan font bulunamadı",
                f"{', '.join(lost)} taşınmış ya da silinmiş; modda özgün font kalır.",
            )
        return {self._title_id_hex(): found} if found else {}

    def import_edited_font(self, source: str) -> None:
        """Kontrol Et → Font: dışarıda düzenlenen TTF/OTF dosyası, dışa aktarılan modda bu fontun yerine konur."""
        start = str(self.settings.value("fonts/dir", str(Path.home())))
        path, _ = QFileDialog.getOpenFileName(
            self, "Düzenlenmiş fontu seçin", start, "Fontlar (*.ttf *.otf);;Tüm dosyalar (*)"
        )
        if not path:
            return
        self.settings.setValue("fonts/dir", str(Path(path).parent))
        if not looks_like_font(Path(path)):
            self.notify(LEVEL_ERROR, "Bu dosya bir font değil", "TTF ya da OTF dosyası seçin.")
            return
        overrides = self._stored_font_overrides()
        overrides[source] = path
        self._save_font_overrides(overrides)
        self.notify(
            LEVEL_SUCCESS,
            "Düzenlenmiş font içe alındı",
            f"{Path(path).name}, dışa aktarılan modda {source.rsplit('/', 1)[-1]} yerine kullanılacak.",
        )

    def reset_edited_font(self, source: str) -> None:
        overrides = self._stored_font_overrides()
        if overrides.pop(source, None) is not None:
            self._save_font_overrides(overrides)
            self.notify(
                LEVEL_INFO, "Özgün fonta dönüldü", f"Modda oyunun özgün {source.rsplit('/', 1)[-1]} fontu kalır."
            )

    def export_font_file(self, source: str) -> None:
        """Seçili fontu oyun dosyalarından okuyup bir klasöre kaydeder (font düzenleyicide açmak için)."""
        if self.busy:
            return
        problems = check_sources(self.sources)
        if self.keys is None or problems:
            self.notify(LEVEL_ERROR, "Font okunamadı", " ".join(problems) or "Önce anahtar dosyasını seçin.")
            return
        start = str(self.settings.value("fonts/dir", str(Path.home())))
        folder = QFileDialog.getExistingDirectory(self, "Fontun kaydedileceği klasörü seçin", start)
        if not folder:
            return
        self.settings.setValue("fonts/dir", folder)
        target = Path(folder) / source.rsplit("/", 1)[-1]
        inputs = self._inputs()

        def work(ctx: TaskContext) -> object:
            with opened_view(inputs, ctx) as view:
                for tree in view.trees:  # fontun bulunduğu içerik ağacı (oyun, DLC)
                    if source in tree.view.files:
                        data = tree.view.open(source).read_all()
                        break
                else:
                    raise NxError(f"Font oyun dosyalarında bulunamadı: {source}")
            target.write_bytes(data)
            return target

        def done(_result: object) -> None:
            self.notify(
                LEVEL_SUCCESS,
                "Font dışa aktarıldı",
                f"{target.name} kaydedildi. Düzenledikten sonra “Düzenlenmiş Fontu İçe Al” ile geri alın.",
                (NoticeAction("Klasörü Aç", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder))),),
            )

        self._run(work, "Font dışa aktarılıyor", on_success=done, on_failure=lambda _t: None)

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
        self.qa_page.set_font_overrides(self._stored_font_overrides())
        self.qa_page.set_font_patch(self.project.setting("font_patch") == "1", self._patchable_letters())
        mode = self.project.setting("transliterate_mode", transliterate.MODE_NONE)
        self.qa_page.set_mode(mode, self._missing_letters(), self._font_patch_on())
        config = self._fit_config()
        self.qa_page.set_fit(config, *self._fit_lists())
        self._refresh_limits()
        self._sync_live()

    def _rows_replaced(self) -> None:
        """Çeviri satırları yeniden kuruldu: satırlara bağlı önbellekler geçersiz."""
        self._rows_version += 1

    def _fit_lists(self) -> tuple[list[str], list[str], list[str]]:
        """Sığdırma sekmesinin dosya, kod etiketi ve grup listeleri (satırlar değişmedikçe önbellekten)."""
        cached = self._fit_lists_cache
        if cached is None or cached[0] != self._rows_version:
            rows = self.translate_page.model.rows
            cached = (
                self._rows_version,
                sorted({r.file for r in rows}),
                sorted({code for r in rows for code in r.code_labels}),
                list(separate_groups(rows)),
            )
            self._fit_lists_cache = cached
        return cached[1], cached[2], cached[3]

    def _refresh_limits(self) -> None:
        """Sınırlar tablosunu doldurur; istatistik ve öğrenme tüm satırları taradığı için yalnızca Sığdırma sekmesi
        görünürken ve satırlar ya da öğrenmeyi etkileyen ayar değiştiyse yapılır."""
        if not self.qa_page.fit_tab_visible():
            return
        config = self._fit_config()
        key = (
            self._rows_version,
            config.default,
            sorted(config.per_file.items()),
            config.kinds.dump(),
        )
        limits = self.qa_page.limits
        if key == self._limits_key:
            limits.set_config(config)
            return
        rows = self.translate_page.model.rows
        limits.set_data(rows, config, learn_group_rules(rows, config))
        self.qa_page.show_kind_warnings(suspected_line_breaks(((r.source, r.code_labels) for r in rows), config.kinds))
        self._limits_key = key

    def _reload_rows(self) -> None:
        """Tabloyu projeden yeniler; panelde bekleyen metin önce kaydedilir ki yenilenen satırlar bayat kalmasın."""
        self.translate_page.flush_pending()
        self.translate_page.set_rows(self.project.translation_rows())

    def _push_fit_to_page(self) -> None:
        """Çeviri sayfasına sığdırma ayarını ve kod türlerini verir (panel sayacı ve çipler)."""
        self.translate_page.set_fit_config(self._fit_config())
        self.translate_page.set_manual_limit(self._manual_limit())
        self._sync_live()

    def _load_live_kinds(self) -> frozenset[str]:
        """Ayarlardaki anlık denetim türleri (bozuk ya da yoksa hepsi)."""
        return parse_live_kinds(self.settings.value(LIVE_KINDS_KEY, None))

    def _sync_live(self, force: bool = False) -> None:
        """Anlık denetimin bağlamını proje, font, sözlük, sığdırma, yazım denetleyicisi ve seçili türlerle kurar.

        Bağlam değişmediyse tablo yenilenmez (büyük projede tüm hücreleri yeniden çizdirmek pahalıdır); yazım
        denetleyicisinin içi değiştiyse (sözcük eklendi) `force` verilir.
        """
        context = LiveContext(
            missing_letters=self._missing_letters(),
            transliterated=self._transliterate_letters(),
            glossary=tuple(self.project.glossary()),
            fit=self._fit_config(),
            spell=self.spell,
            kinds=self._live_kinds,
            spell_ignored=frozenset(turkish_lower(w) for w in self._spell_ignored()),
        )
        if not force and context == self._live_context:
            return
        self._live_context = context
        self.translate_page.set_live_context(context)

    def _apply_spell_copied(self) -> None:
        """Kayıtlı "orijinalden kopyalanan sözcükleri de işaretle" tercihini yazım denetleyicisine uygular."""
        if self.spell is not None:
            self.spell.flag_copied = str(self.settings.value(KEY_SPELL_COPIED, "0")) == "1"

    def _set_spell_copied(self, on: bool) -> None:
        self.settings.setValue(KEY_SPELL_COPIED, "1" if on else "0")
        self._apply_spell_copied()
        self._sync_spell()
        self._recheck_if_done()

    def _set_live_kinds(self, kinds: list[str]) -> None:
        self._live_kinds = frozenset(kinds)
        self.settings.setValue(LIVE_KINDS_KEY, format_live_kinds(kinds))
        self._sync_live()

    def _manual_limit(self) -> int:
        """Projenin kayıtlı "Elle sınır"ı (0: kapalı)."""
        try:
            return max(int(self.project.setting(MANUAL_LIMIT_KEY, "0")), 0)
        except ValueError:
            return 0

    def _save_manual_limit(self, limit: int) -> None:
        self.project.set_setting(MANUAL_LIMIT_KEY, str(limit))

    def _fit_config(self) -> FitConfig:
        """Projenin kayıtlı sığdırma ayarı (sınır yoksa denetim ve düzeltme sığdırma yapmaz)."""
        return load_config(self.project)

    def _save_fit(self) -> None:
        try:
            save_config(self.project, self.qa_page.fit_config())
        except NxError as exc:
            self.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return
        self._push_fit_to_page()
        self._mark_changed()
        if self._qa_count is not None and self._qa_count[0] is self.project:
            # Daha önce denetlendiyse yeni ayarın etkisi kendiliğinden görünür; hiç denetlenmediyse başlatılmaz.
            self.qa_page.show_fit_checking()
            self._fit_recheck_timer.start()

    def _fit_recheck_due(self) -> None:
        self._recheck_if_done()

    def _learn_rules(self, scope: str) -> None:
        """Kapsamdaki (proje, dosya ya da grup) orijinal metinlerden sınır önerir; öneri kaydedilmez.

        "Her grup ayrı" kapsamında her grubun sınırı ayrı öğrenilir ve hemen kaydedilir.
        """
        config = self.qa_page.fit_config()
        all_rows = self.translate_page.model.rows
        if scope == EACH_GROUP:
            learned = learn_group_rules(all_rows, config)
            self.qa_page.show_learned_groups(learned)
            self.qa_page.limits.set_learned(learned)
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
                self.notify(LEVEL_ERROR, "Proje", exc.user_text())
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
            self.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return
        self._mark_changed()
        self.qa_page.set_mode(mode, self._missing_letters(), self._font_patch_on())
        self._sync_live()

    def _set_font_patch(self, enabled: bool) -> None:
        try:
            self.project.set_setting("font_patch", "1" if enabled else "")
        except NxError as exc:
            self.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return
        self._mark_changed()
        self._refresh_qa()

    # --- Kontrol Et: iş akışı `checks_controller.ChecksController`'dadır ------------------------------------
    # Aşağıdakiler yalnızca yönlendirmedir: sinyaller, menüler ve testler pencerenin bu adlarını kullanır.

    @property
    def _qa_count(self) -> tuple[Project, int] | None:
        return self.checks.qa_count

    @_qa_count.setter
    def _qa_count(self, value: tuple[Project, int] | None) -> None:
        self.checks.qa_count = value

    @property
    def _qa_errors(self) -> bool:
        return self.checks.qa_errors

    @_qa_errors.setter
    def _qa_errors(self, value: bool) -> None:
        self.checks.qa_errors = value

    @property
    def _board_task(self) -> Task | None:
        return self.checks.board_task

    @_board_task.setter
    def _board_task(self, value: Task | None) -> None:
        self.checks.board_task = value

    @property
    def _check_task(self) -> Task | None:
        return self.checks.check_task

    @_check_task.setter
    def _check_task(self, value: Task | None) -> None:
        self.checks.check_task = value

    @property
    def _board_pending(self) -> dict[int, TranslationRow]:
        return self.checks.board_pending

    @_board_pending.setter
    def _board_pending(self, value: dict[int, TranslationRow]) -> None:
        self.checks.board_pending = value

    @property
    def _recheck_pending(self) -> bool:
        return self.checks.recheck_pending

    @_recheck_pending.setter
    def _recheck_pending(self, value: bool) -> None:
        self.checks.recheck_pending = value

    def run_checks(self) -> None:
        self.checks.run_checks()

    def start_checks(self) -> None:
        self.checks.start_checks()

    def _run_full_check(self, description: str, finished: Callable[[list[QaIssue]], None] | None = None) -> None:
        self.checks.run_full_check(description, finished)

    def _on_check_cancelled(self) -> None:
        self.checks.on_check_cancelled()

    def _stop_checks(self) -> None:
        self.checks.stop_checks()

    def _show_check_results(self, issues: list[QaIssue], rows: list[TranslationRow]) -> list[QaIssue]:
        return self.checks.show_check_results(issues, rows)

    def _edit_from_issues(self, row_id: int, text: str) -> None:
        self.checks.edit_from_issues(row_id, text)

    def _recheck_board_rows(self, changed: Sequence[TranslationRow], *, keep_terms: bool = False) -> None:
        self.checks.recheck_board_rows(changed, keep_terms=keep_terms)

    def _recheck_board_later(self, edited: Sequence[TranslationRow]) -> None:
        self.checks.recheck_board_later(edited)

    def _recheck_if_done(self) -> None:
        self.checks.recheck_if_done()

    def ignore_issues(self, pairs: list[tuple[int, str]]) -> None:
        self.checks.ignore_issues(pairs)

    def unignore_issues(self, pairs: list[tuple[int, str]]) -> None:
        self.checks.unignore_issues(pairs)

    def _spell_ignored(self) -> list[str]:
        return self.checks.spell_ignored()

    def _terms_ignored(self) -> list[str]:
        return self.checks.terms_ignored()

    def ignore_terms(self, phrases: list[str]) -> None:
        self.checks.ignore_terms(phrases)

    def ignore_spell_words(self, words: list[str]) -> None:
        self.checks.ignore_spell_words(words)

    def apply_ascii_choice(self, key: str, new: str) -> None:
        self.checks.apply_ascii_choice(key, new)

    def _write_row_changes(
        self, plan: list[tuple[int, str]], rows: list[TranslationRow], job_id: str
    ) -> list[TranslationRow]:
        return self.checks.write_row_changes(plan, rows, job_id)

    def _plan_fix_bar(self, rows: list[TranslationRow], issues: list[QaIssue], kinds: list[str]) -> FixPlan:
        return self.checks.plan_fix_bar(rows, issues, kinds)

    def apply_fixes(self, kinds: list[str], row_ids: list[int]) -> None:
        self.checks.apply_fixes(kinds, row_ids)

    # Denetleyicinin iç yardımcıları da eski adlarıyla erişilebilir kalır (testler ve ölçüm betikleri için);
    # denetleyici bunları kendi içinde doğrudan çağırır.

    def _checks_job(self, rows: list[TranslationRow]) -> Callable[[ProgressCallback | None], list[QaIssue]]:
        return self.checks._checks_job(rows)

    def _announce_checks(self, result: list[QaIssue]) -> None:
        self.checks._announce_checks(result)

    def _board_recheck_job(
        self, edited: Sequence[TranslationRow], *, keep_terms: bool = False
    ) -> tuple[list[TranslationRow], Callable[[], dict[int, list[QaIssue]]]] | None:
        return self.checks._board_recheck_job(edited, keep_terms=keep_terms)

    def _show_board_recheck(self, group: list[TranslationRow], by_row: dict[int, list[QaIssue]]) -> None:
        self.checks._show_board_recheck(group, by_row)

    def _replace_board_rows(self, rows: list[TranslationRow], by_row: dict[int, list[QaIssue]]) -> None:
        self.checks._replace_board_rows(rows, by_row)

    def _sync_ignored_to_translate(self) -> None:
        self.checks.sync_ignored_to_translate()

    def _split_ignored(
        self, issues: list[QaIssue], rows: Sequence[TranslationRow]
    ) -> tuple[list[QaIssue], list[QaIssue]]:
        return self.checks._split_ignored(issues, rows)

    def _store_ignored_issues(self, entries: set[ignored.Entry], row_ids: set[int]) -> None:
        self.checks._store_ignored_issues(entries, row_ids)

    def _recount_qa(self) -> None:
        self.checks._recount_qa()

    def _store_ignored(self, key: str, current: list[str], additions: list[str]) -> None:
        self.checks._store_ignored(key, current, additions)

    def _fix_settings(self) -> FixSettings:
        return self.checks._fix_settings()

    def _write_fixes(self, rows: list[TranslationRow], plan: FixPlan) -> None:
        self.checks._write_fixes(rows, plan)

    # --- Yazım Denetimi penceresi ----------------------------------------------------------

    def open_spell_window(self) -> None:
        """Araçlar → Yazım Denetimi: kipsiz tek pencere; açıksa öne gelir."""
        if self.spell is None or not self.translate_page.model.rows:
            return
        win = self._spell_window
        if win is None:
            win = SpellWindow(self)
            win.show_row.connect(self._open_row)
            win.ignore_requested.connect(self.ignore_spell_words)
            win.add_requested.connect(self._add_from_spell_window)
            win.replace_requested.connect(self._replace_spell_word)
            win.fix_all_requested.connect(self._fix_spell_words)
            win.suggest_fn = self._spell_hint
            self._spell_window = win
        self._refresh_spell_window(force=True)
        win.show()
        win.raise_()
        win.activateWindow()

    def _refresh_spell_window(self, force: bool = False) -> None:
        """Pencere görünürken (ya da `force`) sözcük listesini güncel satırlardan kurar."""
        win = self._spell_window
        if win is None or not (force or win.isVisible()):
            return
        if self.spell is None:
            win.set_words([])
            return
        rows = self.translate_page.model.rows
        extra = glossary_words(self.project.glossary())
        if extra != self._spell_extra_key:
            self._spell_cache.clear()
            self._spell_hints.clear()
            self._spell_extra_key = extra
        stale = self._spell_cache.stale(rows)
        if len(stale) > SPELL_SYNC_ROWS:
            win.set_scanning(True)
            self._start_spell_scan(stale, self.spell, extra)
            return
        self._spell_cache.store(self._spell_cache.scan(stale, self.spell, extra))
        words = self._spell_cache.words(rows, self._spell_ignored())
        wanted = {i for w in words for i in w.row_ids}
        previews = {r.id: _preview(r.translation) for r in rows if r.id in wanted}
        win.set_words(words, previews)

    def _start_spell_scan(self, stale: list[TranslationRow], spell: SpellChecker, extra: frozenset[str]) -> None:
        """Çok sayıda satırı arka planda tarar (aynı anda tek tarama); biterken pencere yeniden tazelenir."""
        if self._spell_scan is not None:
            return  # sürüyor: bitince kalan değişen satırlar için yeniden başlatılır

        def work(ctx: TaskContext) -> object:
            scanned: dict[int, tuple[TranslationRow, tuple[str, ...]]] = {}
            for start in range(0, len(stale), SPELL_SYNC_ROWS):
                ctx.check()
                scanned |= UnknownWordCache.scan(stale[start : start + SPELL_SYNC_ROWS], spell, extra)
            return scanned

        owner = self.project

        def done(result: object) -> None:
            assert isinstance(result, dict)
            # Tarama sürerken proje ya da sözlük değiştiyse sonuç atılır (satır kimlikleri başka projeye karışmaz).
            if owner is self.project and spell is self.spell and extra == self._spell_extra_key:
                self._spell_cache.store(result)
            self._spell_scan_ok = True

        scan = Task(work, "Yazım taraması")
        self._spell_scan = scan
        self._spell_scan_ok = False
        scan.succeeded.connect(done)
        scan.finished.connect(self._spell_scan_finished)
        scan.start()

    def _spell_scan_finished(self) -> None:
        scan, self._spell_scan = self._spell_scan, None
        if scan is not None:
            release_thread(scan)
        if self._spell_scan_ok:
            self._refresh_spell_window()  # tarama sürerken değişen satırlar için
        elif self._spell_window is not None:
            self._spell_window.set_scanning(False)

    def _add_from_spell_window(self, words: list[str]) -> None:
        self.add_spell_words([str(w) for w in words])
        self._refresh_spell_window()

    def _spell_hint(self, word: str, edits: bool) -> Suggestion:
        """Pencerenin öneri kaynağı: yazım sözlüğü ve oyun sözlüğüyle üretilir, sözcük başına bellekte tutulur."""
        key = (word, edits)
        found = self._spell_hints.get(key)
        if found is None:
            if self.spell is None:
                return Suggestion()
            extra = self._spell_extra_key if self._spell_extra_key is not None else frozenset()
            found = self._spell_hints[key] = suggestions(word, self.spell, extra, edits=edits)
        return found

    def _spell_word_rows(self, words: list[str]) -> dict[str, list[TranslationRow]] | None:
        """Her sözcüğün geçtiği satırlar (pencerenin listelediği geçişler); yalnızca değişen satırlar taranır.

        Tarama büyük bir değişiklikten sonra arka planda sürüyorsa `None` döner ve neden durum çubuğunda söylenir.
        """
        spell = self.spell
        if spell is None:
            return None
        rows = self.translate_page.model.rows
        extra = glossary_words(self.project.glossary())
        if extra != self._spell_extra_key:
            self._spell_cache.clear()
            self._spell_hints.clear()
            self._spell_extra_key = extra
        stale = self._spell_cache.stale(rows)
        if len(stale) > SPELL_SYNC_ROWS:
            self.statusBar().showMessage("Sözcükler taranıyor; tarama bitince yeniden deneyin.", 5000)
            return None
        self._spell_cache.store(self._spell_cache.scan(stale, spell, extra))
        by_id = {r.id: r for r in rows}
        return {w: [by_id[i] for i in ids if i in by_id] for w, ids in self._spell_cache.row_ids(words).items()}

    def _spell_changes(self, pairs: list[tuple[str, str]]) -> list[tuple[int, str]] | None:
        """Sözcük çiftlerinin yalnızca geçtiği satırlardaki değişiklikleri; her satır için tek yeni metin.

        Kaynakta da geçen, tamamı büyük harfli, özel ad ve çevrilmemiş kopya geçişlere dokunulmaz (pencere de
        bunları saymaz); böylece değişen satır sayısı penceredeki sayıyla aynıdır.
        """
        spell = self.spell
        found = self._spell_word_rows([old for old, _new in pairs])
        if spell is None or found is None:
            return None
        extra = glossary_words(self.project.glossary())
        texts: dict[int, str] = {}
        for old, new in pairs:
            for row in found[old]:
                text = replace_unknown(texts.get(row.id, row.translation), row.source, spell, extra, word=old, new=new)
                if text != row.translation:
                    texts[row.id] = text
        return list(texts.items())

    def _replace_spell_word(self, old: str, new: str) -> None:
        """Sözcüğü pencerenin listelediği geçişlerde değiştirir; tek iştir, Geri Al hepsini geri alır."""
        self._apply_spell_changes([(old, new)])

    def _fix_spell_words(self, pairs: list[tuple[str, str]]) -> None:
        """ "Tek önerisi olanları düzelt": bütün çiftler tek işte uygulanır; onaylı satırlar onaylı kalır."""
        self._apply_spell_changes([(str(old), str(new)) for old, new in pairs])

    def _apply_spell_changes(self, pairs: list[tuple[str, str]]) -> None:
        if not pairs or self.spell is None:
            return
        if self.busy:
            self.statusBar().showMessage("Bir iş sürerken değiştirilemez; iş bitince yeniden deneyin.", 5000)
            return
        changes = self._spell_changes(pairs)
        if not changes:
            return
        rows = self._replace_translations(changes)
        if rows is None:
            return  # neden Çevir sayfasında bildirildi
        self.statusBar().showMessage(f"{format_int(len(changes))} satırda değiştirildi.", 5000)
        self._refresh_spell_window()
        self._recheck_board_later(rows)

    def _sync_spell(self) -> None:
        """Editördeki yazım işaretlerini güncel denetleyici ve oyun sözlüğüyle yeniler."""
        self._spell_cache.clear()  # sözlük ya da yoksayılanlar değişti
        self._spell_hints.clear()
        self.translate_page.set_spell(self.spell, spell_extra_words(self.project.glossary(), self._spell_ignored()))
        self._sync_live(force=True)
        self.update_menu_state()
        self._refresh_spell_window()

    def add_spell_words(self, words: list[str]) -> None:
        """Sözcükleri kalıcı kullanıcı sözlüğüne ekler; editör ve (yapıldıysa) denetim sonucu yenilenir."""
        try:
            added = self.user_dictionary.add(words)
        except OSError as exc:
            self.notify(LEVEL_ERROR, "Yazım sözlüğü", f"Sözlük kaydedilemedi: {exc.strerror or exc}")
            return
        if self.spell is not None:
            self.spell.add_user_words(words)
        self._sync_spell()
        self.statusBar().showMessage(f"{format_int(added)} sözcük yazım sözlüğüne eklendi.", 5000)
        self._recheck_if_done()

    def add_spelling_from_qa(self, words: list[str]) -> None:
        dialog = AddSpellWordsDialog(self, [str(w) for w in words])
        if dialog.exec() == AddSpellWordsDialog.DialogCode.Accepted and dialog.selected():
            self.add_spell_words(dialog.selected())

    def edit_user_dictionary(self) -> None:
        dialog = UserDictionaryDialog(self, self.user_dictionary)
        dialog.exec()
        if dialog.removed:
            self.spell = load_spell_checker(self.user_dictionary)
            self._apply_spell_copied()
            self._sync_spell()
            self._recheck_if_done()

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

    def _open_row(self, row_id: int) -> None:
        self.nav.setCurrentRow(STEP_TRANSLATE)
        self.translate_page.select_row(row_id)

    # --- dışa aktarma ----------------------------------------------------------------------

    def _graphics(self) -> tuple[GraphicsSupport, Path] | None:
        """Projenin oyunu resim çevirisini destekliyorsa (destek, klasör); klasör oyun dosyalarının yanındadır."""
        if not self.sources:
            return None
        for _path, title_id, kind in self.project.text_files():
            support = getattr(plugin_for_kind(kind, title_id), "graphics", None)
            if isinstance(support, GraphicsSupport):
                return support, self.sources[0].path.parent / support.folder_name
        return None

    def _refresh_graphics(self) -> None:
        found = self._graphics()
        if found is None:
            self.export_page.set_graphics(None, (0, 0))
            return
        self.export_page.set_graphics(found[1], graphics_status(found[1]))

    def extract_graphics(self) -> None:
        """Dışa Aktar → Görseller: yazı içeren resimlerin özgünlerini PNG olarak oyun klasörünün yanına çıkarır."""
        found = self._graphics()
        if self.busy or found is None:
            return
        support, folder = found
        problems = check_sources(self.sources)
        if self.keys is None or problems:
            self.notify(LEVEL_ERROR, "Görseller çıkarılamadı", " ".join(problems) or "Önce anahtar dosyasını seçin.")
            return
        inputs = self._inputs()

        def work(ctx: TaskContext) -> object:
            names: list[str] = []
            with opened_view(inputs, ctx) as view:
                for tree in view.trees:
                    names += support.export(MemberReader(tree.view, tree.code), tree.view.files, folder)
            return names

        def done(result: object) -> None:
            assert isinstance(result, list)
            self._refresh_graphics()
            self.notify(
                LEVEL_SUCCESS,
                "Görseller çıkarıldı",
                f"{format_int(len(result))} resim orijinal/ klasöründe. Türkçesini temiz/ klasörüne aynı adla koyun.",
                (NoticeAction("Klasörü Aç", self.open_graphics),),
            )

        self._run(work, "Görseller çıkarılıyor", on_success=done, on_failure=lambda _t: None)

    def open_graphics(self) -> None:
        found = self._graphics()
        if found is None:
            return
        found[1].mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(found[1])))

    # --- Dışa Aktar: iş akışı `export_controller.ExportController`'dadır -------------------------------------
    # Aşağıdakiler yalnızca yönlendirmedir: sinyaller, adım geçişi ve testler pencerenin bu adlarını kullanır.

    def _refresh_export(self) -> None:
        self.exporter.refresh_export()

    def _include_errors_on(self) -> bool:
        return self.exporter._include_errors_on()

    def _set_include_errors(self, enabled: bool) -> None:
        self.exporter.set_include_errors(enabled)

    def _choose_export_folder(self) -> None:
        self.exporter.choose_export_folder()

    def _ask_full_folder(self, dest: Path) -> str:
        """Dolu hedef klasör sorusu (`ask_full_folder`; testler `choose_button`'ı bu modülde değiştirir)."""
        return ask_full_folder(self, dest)

    def export_mod(self) -> None:
        self.exporter.export_mod()

    def _kept_rows_text(self, ids: Sequence[int], rows: Sequence[TranslationRow]) -> str:
        return self.exporter.kept_rows_text(ids, rows)

    def _open_export_folder(self) -> None:
        self.exporter.open_export_folder()

    # --- hazır çeviriyi içe aktarma -----------------------------------------------------------

    def import_ready_translation(self) -> None:
        """Oyunun hazır bir Türkçe yamasındaki (Unity metin tabloları) çevirileri projeye aktarır."""
        if self.busy:
            return
        if not self.project.translation_rows():
            self.notify(
                LEVEL_INFO,
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
                self.notify(
                    LEVEL_INFO, "Hazır çeviriyi içe aktar", "Yazılacak yeni bir çeviri yok.\n\n" + "\n".join(lines[:3])
                )
                return
            answer = QMessageBox.question(self, "Hazır çeviriyi içe aktar", "\n".join(lines))
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                report = port_translations(self.project, result)
            except NxError as exc:
                self.notify(LEVEL_ERROR, "Hazır çeviriyi içe aktar", exc.user_text())
                return
            self._mark_changed()
            self._reload_rows()
            text = f"{format_int(report.applied)} satır hazır çeviriden aktarıldı."
            if report.code_problems:
                text += f" {format_int(len(report.code_problems))} satır kontrol kodları uyuşmadığı için atlandı."
            self.nav.setCurrentRow(STEP_TRANSLATE)
            self.translate_page.show_notice("success", text)

        def failed(text: str) -> None:
            self.notify(LEVEL_ERROR, "Hazır çeviriyi içe aktar", text)

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
            self.notify(LEVEL_ERROR, "Metinler aktarılamıyor", " ".join(problems))
            return
        inputs = self._inputs()
        report = self.report
        language = self.scan_page.report.language.currentData()
        source_language = str(language) if language else None
        chosen = self.scan_page.report.selected_paths()  # tarama sayfasında işaretli dosyalar
        self._import_language = source_language or "en"
        # Aktarma, projeyi seçime göre eşitler: seçilmeyen proje dosyaları çevirileriyle silinir. Önce sorulur.
        self._confirmed_removals = set()
        dropped = self._files_to_remove(chosen)
        if dropped and not self._confirm_removal(dropped):
            return
        self._confirmed_removals = dropped
        self.scan_page.show_loading("Metinler oyundan çıkarılıyor")

        def failed(text: str) -> None:
            self._show_scan_report(report)
            self.notify(LEVEL_ERROR, "Metinler aktarılamadı", text)

        def cancelled() -> None:
            self._show_scan_report(report)
            self.statusBar().showMessage("Aktarma iptal edildi; projede değişiklik yapılmadı.", 6000)

        self._run(
            lambda ctx: extract_texts(inputs, report, ctx, source_language, chosen),
            "Metinler çıkarılıyor",
            on_success=self._texts_extracted,
            on_failure=failed,
            on_progress=self.scan_page.loading.update_progress,
            on_cancel=cancelled,
        )

    def _files_to_remove(self, kept: Collection[str]) -> set[str]:
        """Projede aktarılmış olup `kept` içinde olmayan dosyalar (aktarma bunları çevirileriyle siler)."""
        return {path for path in self.project.translated_counts_by_file() if path not in kept}

    def _confirm_removal(self, paths: Collection[str]) -> bool:
        counts = self.project.translated_counts_by_file()
        return self.ask_remove_files(len(paths), sum(counts.get(p, 0) for p in paths))

    def ask_remove_files(self, files: int, translated: int) -> bool:
        """Seçilmeyen dosyaların projeden kaldırılmasını onaylatır (testlerde değiştirilir)."""
        box = QMessageBox(self)
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
        assert isinstance(result, TextExtraction)
        if self.report is not None:
            self._show_scan_report(self.report)
        # İçerikten dil nedeniyle düşen dosyalar da silinir: onaylanandan fazlası yazmadan önce yeniden sorulur.
        actual = self._files_to_remove({f.path for f in result.files})
        if actual - self._confirmed_removals and not self._confirm_removal(actual):
            self.statusBar().showMessage("Aktarma durduruldu; projede değişiklik yapılmadı.", 6000)
            return
        try:
            stats = self.project.import_texts(result.files)
            self.project.set_setting("source_language", self._import_language)
            record_extraction(self.project, (fmt for _path, _tid, fmt in self.project.text_files()))
        except NxError as exc:
            self.notify(LEVEL_ERROR, "Metinler aktarılamadı", exc.user_text())
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
            self.notify(LEVEL_ERROR, "Terminoloji kaydedilemedi", exc.user_text())
            return
        self._mark_changed()
        self._sync_spell()
        self.statusBar().showMessage(f"Terminoloji kaydedildi ({len(dialog.terms())} terim).", 5000)
        if dialog.wants_suggestions:
            self.suggest_glossary_terms()

    def add_rows_to_terminology(self) -> None:
        """Seçili satırların orijinal ve çevirisi (ayıklanarak) onaydan sonra terminolojiye eklenir."""
        rows = self.translate_page.selected_rows()
        if not rows:
            self.notify(LEVEL_WARNING, "Önce satır seçin", "Terminolojiye eklenecek satırları tabloda seçin.")
            return
        plan = plan_terms_from_rows(rows, self.project.glossary())
        if not plan.new and not plan.conflicts:
            self.notify(LEVEL_INFO, "Eklenecek terim yok", "Seçili satırlar zaten terminolojide ya da çevirisiz.")
            return
        dialog = AddTermsDialog(self, plan.new, plan.conflicts)
        if dialog.exec() != AddTermsDialog.DialogCode.Accepted or not dialog.selected():
            return
        merged, added, updated = merge_terms(self.project.glossary(), dialog.selected())
        try:
            self.project.set_glossary(merged)
        except NxError as exc:
            self.notify(LEVEL_ERROR, "Terminoloji kaydedilemedi", exc.user_text())
            return
        self._mark_changed()
        self._sync_spell()
        self._sync_live()
        self.notify(
            LEVEL_SUCCESS,
            "Terminoloji güncellendi",
            f"{format_int(added)} terim eklendi · {format_int(updated)} terim güncellendi",
        )

    def find_term_candidates(self) -> list[TermCandidate]:
        """Terim önerisinin adayları: metinlerde sık geçen, terminolojide olmayan özel adlar."""
        return find_candidates(self.project.translation_rows(), self.project.glossary())

    def suggest_glossary_terms(self) -> None:
        """Metinlerde sık geçen adları bulur, Ollama'dan karşılık ister; onaylananlar terminolojiye katılır."""
        if self.busy:
            return
        page = self.translate_page
        model = str(self.settings.value("ollama/model", ""))
        if str(self.settings.value("translate/provider", PROVIDER_OLLAMA)) != PROVIDER_OLLAMA or not model:
            self.notify(
                LEVEL_WARNING,
                "Terim önerisi için Ollama gerekli",
                "Otomatik Çeviri'de sağlayıcı olarak Ollama'yı ve bir model seçin.",
                (NoticeAction("Otomatik Çeviri…", lambda: self.start_machine_translation(ACTION_TRANSLATE)),),
            )
            return
        candidates = self.find_term_candidates()
        if not candidates:
            self.notify(
                LEVEL_INFO,
                "Önerilecek terim yok",
                "Cümle ortasında en az iki kez büyük harfle geçen yeni bir ad bulunamadı.",
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

        def failed(text: str) -> None:
            page.set_machine_running(False)
            title, rest = split_notice(text)
            if "bağlanılamadı" in title:
                title = "Ollama'ya bağlanılamadı"
            self.notify(
                LEVEL_ERROR,
                title,
                rest,
                (NoticeAction("Ayarları Aç", lambda: self.open_settings(PAGE_PROVIDERS)),),
            )

        def cancelled() -> None:
            page.set_machine_running(False)
            self.notify(LEVEL_WARNING, "Terim önerisi durduruldu", "Terminoloji değişmedi.")

        def done(result: object) -> None:
            assert isinstance(result, list)
            page.set_machine_running(False)
            if not result:
                self.notify(
                    LEVEL_INFO, "Terim önerilmedi", f"Model {format_int(len(candidates))} aday için bir terim önermedi."
                )
                return
            dialog = TermSuggestionsDialog(self, result)
            if dialog.exec() != TermSuggestionsDialog.DialogCode.Accepted or not dialog.selected():
                page.show_notice("success", "Terim önerileri eklenmedi.")
                return
            merged, added, updated = merge_terms(self.project.glossary(), dialog.selected())
            try:
                self.project.set_glossary(merged)
            except NxError as exc:
                page.show_notice("danger", exc.user_text())
                return
            self._mark_changed()
            self._sync_spell()
            self.notify(
                LEVEL_SUCCESS,
                "Terminoloji güncellendi",
                f"{format_int(added)} terim eklendi · {format_int(updated)} terim güncellendi",
            )

        page.set_machine_running(True)
        page.show_notice("success", "")
        self._run(
            work,
            "Terim önerisi",
            on_success=done,
            on_failure=failed,
            on_progress=page.update_machine_progress,
            on_cancel=cancelled,
        )

    def open_settings(self, page: str | None = None) -> None:
        """Ayarlar penceresini açar (`page`: açılacak sayfa, ör. `PAGE_PROVIDERS`)."""
        dialog = SettingsDialog(
            self,
            self.settings,
            self.shortcuts,
            self.translate_page.view_actions,
            self.secrets,
            theme=self._theme_mode(),
            font_size=self._font_size(),
            wrap=self.translate_page.wrap_box,
            issue_colors=self.translate_page.colors_box,
            error_rows=self.translate_page.error_rows_box,
            updates_available=self.update_action.isEnabled(),
            live_kinds=self._live_kinds,
            page=page or PAGE_VIEW,
        )
        dialog.live_kinds_changed.connect(self._set_live_kinds)
        dialog.spell_copied_changed.connect(self._set_spell_copied)
        dialog.notify_option_changed.connect(lambda key, on: self.settings.setValue(key, "1" if on else "0"))
        dialog.notify_card_seconds_changed.connect(lambda sec: self.settings.setValue(KEY_CARD_SECONDS, sec))
        dialog.test_notification_requested.connect(self._test_notification)
        dialog.theme_changed.connect(self._set_theme)
        dialog.font_size_changed.connect(self._set_font_size)
        dialog.check_updates_requested.connect(self.open_updates)
        dialog.exec()
        dialog.deleteLater()

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
        try:
            if dialog.exec() != MachineDialog.DialogCode.Accepted:
                return None
            return dialog.settings()
        finally:
            dialog.deleteLater()  # her açılışta ana pencerenin çocuğu olarak kalıyordu (sızıntı)

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
            self.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return False
        return True

    def start_machine_translation(self, action: str = ACTION_TRANSLATE, from_selection: bool = False) -> None:
        """Çevir / yeniden çevir / talimatla düzelt penceresini açar ve seçilen işi başlatır."""
        if self.busy:
            return
        page = self.translate_page
        if from_selection and not page.table.selectionModel().hasSelection():
            page.show_notice("warning", "Önce çevirmek istediğiniz satırları seçin.")
            return
        scopes = self._machine_scopes()
        chosen = self.ask_machine_settings(scopes, action, SCOPE_SELECTED if from_selection else SCOPE_ALL)
        if chosen is None or not self._remember_machine_settings(chosen):
            return
        scope_rows = (
            rows_matching(scopes.get(SCOPE_ALL, []), chosen.pattern)
            if chosen.scope == SCOPE_PATTERN
            else scopes.get(chosen.scope, [])
        )
        target = target_rows(scope_rows, chosen.action, chosen.include_approved)
        job = MachineJob(
            rows=target,
            source_lang=self.project.setting("source_language", "en"),
            notes=chosen.notes,
            # Terminoloji + örtük terimler (menüde/başlıkta nasıl çevrildiyse cümlede de öyle; partide geçenler gider).
            glossary=[
                *self.project.glossary(),
                *implicit_terms(self.project.translation_rows(), self.project.glossary(), self._terms_ignored()),
            ],
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
        # Satırın kaynağı olarak yalnızca sağlayıcı kimliği ve Ollama modeli yazılır (adres ya da anahtar asla).
        origin = MachineOrigin(chosen.provider, chosen.model if chosen.provider == PROVIDER_OLLAMA else "")
        memory_ids = frozenset(memory_filled_ids(job))

        def finish(level: str, title: str, text: str, details: str = "") -> None:
            set_running(False)
            self._reload_rows()  # filtrelere "Makine" durumu eklensin
            changed = self._set_last_job(job_id)
            actions: list[NoticeAction] = []
            if level == LEVEL_ERROR:
                actions.append(NoticeAction("Tekrar Dene", lambda: self.start_machine_translation(job.action)))
            if changed:
                actions.append(NoticeAction("Değişiklikleri Gör", self.show_job_changes))
            if details:
                actions.append(NoticeAction("Ayrıntılar", lambda: QMessageBox.information(self, title, details)))
            self.notify(level, title, text, tuple(actions))

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
        self._run(
            lambda ctx: run_and_close(provider, job, ctx),
            name,
            on_success=done,
            on_failure=lambda text: finish(LEVEL_ERROR, f"{name} durdu", f"{text} Yapılanlar kaydedildi. {resume}"),
            on_progress=on_progress,
            on_cancel=lambda: finish(LEVEL_WARNING, f"{name} durduruldu", f"Yapılanlar kaydedildi. {resume}"),
            on_partial=lambda results: self._machine_results(
                results, chosen.include_approved, job_id, origin=origin, memory_ids=memory_ids
            ),
        )

    # --- değişiklikler ve geçmiş -------------------------------------------------------------

    def _set_last_job(self, job_id: str) -> int:
        """Son işi hatırlar; işte değişen (geri alınmamış) satır sayısını döndürür."""
        self._last_job = job_id
        changes = self.project.job_changes(job_id)
        self.translate_page.set_last_changes({c.entry_id: c.old_text for c in changes})
        return len(changes)

    def _refresh_marks(self, ids: Sequence[int] | None = None) -> None:
        """Durum sütunundaki "· redaksiyon" gibi işaretler: satırın son değişikliğini yapan iş.

        `ids` verilirse yalnızca o satırların işareti yenilenir (az satır değişen işlerde bütün geçmişi okumaz).
        """
        model = self.translate_page.model
        if ids is None:
            marks = {eid: label for eid, job in self.project.last_jobs().items() if (label := mark_label(job))}
        else:
            marks = dict(model.marks)
            latest = self.project.last_jobs(ids)
            for eid in ids:
                text = mark_label(latest[eid]) if eid in latest else ""
                if text:
                    marks[eid] = text
                else:
                    marks.pop(eid, None)
        model.set_marks(marks)

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
        self._open_changes(
            ChangesDialog(
                self,
                f"{job_label(self._last_job)}: değişiklikler",
                changes,
                kinds=applied,
                edit_fn=self._edit_from_changes,
                context_fn=self._context_html,
                settings=self.settings,
            )
        )

    def _edit_from_changes(self, row_id: int, text: str) -> str | None:
        """Değişiklikler penceresinde "Yeni" hücresinin elle düzeltilmesi: Çevir'deki kayıt yoluyla yazılır."""
        if self.busy:
            return "Bir iş sürerken düzenlenemez; iş bitince yeniden deneyin."
        try:
            rows = self._commit_translations([(row_id, text)])
        except NxError as exc:
            return exc.user_text()
        self.translate_page.model.update_rows(rows)
        return None

    def _context_html(self, row_id: int) -> str:
        """Satırın bağlamı: aynı dosyada önceki ve sonraki iki satırın orijinali ve çevirisi (ipucu için HTML)."""
        before, after = self.translate_page.model.neighbors(row_id)

        def line(r: TranslationRow) -> str:
            translation = html.escape(r.translation) if r.translation else "<i>çevrilmedi</i>"
            return f"{html.escape(r.source)}<br><span style='color:gray'>{translation}</span>"

        parts = [line(r) for r in before]
        parts.append("<b>▶ bu satır</b>")
        parts += [line(r) for r in after]
        return "<br><br>".join(parts) if before or after else ""

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

    def _menu_find_next(self) -> None:
        if self._to_translate_step():
            self.translate_page.find_next()

    def _menu_find_previous(self) -> None:
        if self._to_translate_step():
            self.translate_page.find_previous()

    def _menu_machine(self) -> None:
        if self._to_translate_step():
            self.start_machine_translation()

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
        self._refresh_marks([r.id for r in rows])
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
            self.notify(LEVEL_ERROR, "Proje", exc.user_text())
            self.translate_page.set_uppercase(self.project.uppercase_rules())
            return
        self._mark_changed()

    def _machine_results(
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
        assert isinstance(results, list)
        job = job_id or new_job_id("translate")
        from_memory = [r for r in results if r[0] in memory_ids]
        from_provider = [r for r in results if r[0] not in memory_ids]
        try:
            rows = []
            if from_memory:
                rows += self.project.set_translations(
                    from_memory, machine=True, overwrite_approved=overwrite_approved, job=job, origin=MEMORY_ORIGIN
                )
            if from_provider:
                rows += self.project.set_translations(
                    from_provider, machine=True, overwrite_approved=overwrite_approved, job=job, origin=origin
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

    def _update_redo_action(self) -> None:
        job = self.project.redo_job()
        self.redo_action.setText("Yinele" if job is None else f"Yinele: {job_label(job)}")
        self.redo_action.setEnabled(job is not None and not self.busy)

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
        self._show_stepped_rows(rows)
        page.show_notice(
            "success", f"Geri alındı ({job_label(job)}): {format_int(len(rows))} satır önceki hâline döndü."
        )

    def redo_last(self) -> None:
        """Geri alınan son işlemi aynen geri getirir; arada yeni bir düzenleme yapıldıysa yinelenecek bir şey kalmaz."""
        page = self.translate_page
        if self.busy:
            page.show_notice("warning", "Bir iş sürerken yinelenemez; iş bitince veya durdurulunca deneyin.")
            return
        try:
            result = self.project.redo()
        except NxError as exc:
            page.show_notice("danger", exc.user_text())
            return
        self._to_translate_step()
        if result is None:
            page.show_notice("warning", "Yinelenecek bir işlem yok.")
            return
        job, rows = result
        self._show_stepped_rows(rows)
        page.show_notice("success", f"Yinelendi ({job_label(job)}): {format_int(len(rows))} satır yeniden uygulandı.")

    def _show_stepped_rows(self, rows: list[TranslationRow]) -> None:
        """Geri al / yinele sonrası: tabloyu, iş işaretlerini ve "Son işte değişenler"i yeniler."""
        page = self.translate_page
        page.model.update_rows(rows)
        self._mark_changed()
        self._refresh_marks()
        self._update_undo_action()  # art arda Ctrl+Z / Ctrl+Y zamanlayıcıyı beklemeden doğru eylemi bulsun
        self._update_redo_action()
        if self._last_job is not None:
            self._set_last_job(self._last_job)
        if len(rows) == 1:
            page.select_row(rows[0].id)

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
                f"{format_int(len(dialog.rows()))} satır {shown} çeviri dosyasına yazıldı: {files}. Çeviri talimatı "
                "panoya kopyalandı. Çevrilen dosyaları Araçlar → “Dış Çeviriden İçe Aktar” ile geri yükleyin.",
            )
        else:
            page.show_notice(
                "success",
                f"{format_int(len(dialog.rows()))} satır yazıldı: {files}. Model için hazır talimat panoya kopyalandı. "
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
            self.notify(LEVEL_INFO, title, "Önce “Metinleri Tara” adımından metinleri çeviri tablosuna aktarın.")
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
            self.notify(LEVEL_ERROR, title, exc.user_text())
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
            self.notify(LEVEL_INFO, title, "Yazılacak bir değişiklik yok.\n\n" + "\n".join(lines))
            return
        lines.append(
            f"Değişiklikler “{status_name}” durumuyla yazılır; “Son İşin Değişiklikleri” veya Geri Al ile geri "
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
        dialog = ChangesDialog(
            self,
            title,
            preview,
            preview=True,
            summary=lines,
            free_codes={r.id: r.free_codes for r in rows if r.id in changed},
        )
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
            self.notify(LEVEL_INFO, title, note)
            return
        job_id = new_job_id(job_kind)
        try:
            updated = self.project.set_translations(
                applied,
                status=None if translation else Status.REDACTED,
                machine=translation,
                overwrite_approved=True,
                job=job_id,
                # Dış çeviri metni baştan değiştirir (makine kaynağı artık bilinmez); redaksiyon taslağı düzeltir.
                origin=NO_ORIGIN if translation else None,
            )
        except NxError as exc:
            self.notify(LEVEL_ERROR, title, exc.user_text())
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

    def _confirm_discard(self, closing: bool = False) -> bool:
        """Kaydedilmemiş değişiklik varsa kullanıcıya sorar. Devam edilebilirse True."""
        return self.projects.confirm_discard(closing)

    def ask_save_changes(self, closing: bool) -> str:
        """ "save", "discard" ya da "cancel" (testlerde değiştirilir)."""
        box, save, discard_button = build_save_box(self, closing)
        box.exec()
        clicked = box.clickedButton()
        return "save" if clicked is save else "discard" if clicked is discard_button else "cancel"

    def new_project(self) -> None:
        self.projects.new_project()

    def _replace_project(self, project: Project) -> bool:
        """Açık projeyi `project` ile değiştirir. Panel metni kaydedilemezse eski proje kalır, False döner."""
        return self.projects.replace_project(project)

    def _open_project_dialog(self) -> None:
        self.projects.open_project_dialog()

    def open_project(self, path: Path) -> bool:
        return self.projects.open_project(path)

    def save_project(self) -> bool:
        return self.projects.save_project()

    def save_project_as(self) -> bool:
        return self.projects.save_project_as()

    def save_to(self, path: Path) -> bool:
        return self.projects.save_to(path)

    def _clear_cache(self) -> None:
        cache = self._cache_dir()
        size = dir_size(cache)
        if size == 0:
            self.notify(LEVEL_INFO, "Geçici dosyalar", f"Geçici dosya yok.\n\nKonum: {cache}")
            return
        answer = QMessageBox.question(
            self,
            "Geçici dosyaları temizle",
            f"Geçici dosyalar {format_size(size)} yer kaplıyor.\n\nKonum: {cache}\n\n"
            "Silinen veriler gerektiğinde oyun dosyalarından yeniden oluşturulur. Silinsin mi?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            clear_cache(cache)
        except NxError as exc:
            self.notify(LEVEL_ERROR, "Geçici dosyalar", exc.user_text())
            return
        self.statusBar().showMessage(f"Geçici dosyalar temizlendi ({format_size(size)}).", 5000)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.translate_page.flush_pending():  # panelde yazılıp kaydedilemeyen metin kaybolmasın
            event.ignore()
            return
        if self.busy:
            text = "Bir işlem devam ediyor. İptal edip çıkmak istiyor musunuz?"
            if self.checks.pending_edits:
                text += (
                    "\n\nSorunlar'da iş bitince kaydedilmek üzere saklanan "
                    f"{format_int(len(self.checks.pending_edits))} düzenleme de kaydedilmeyecek. "
                    "Kaydetmek için Hayır deyip işin bitmesini bekleyin."
                )
            answer = QMessageBox.question(self, "İşlem sürüyor", text)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if not self._confirm_discard(closing=True):
            event.ignore()
            return
        # Tüm onaylar alındı: önce iptaller, sonra pencere gizlenir, ardından iş parçacıkları beklenir
        # (beklenmeden bırakılan iş parçacığı çökmeye yol açar; bkz. tasks.release_thread).
        self.translate_page.find_window.close()  # açık Bul penceresinin konumu kaybolmasın
        self.translate_page.cancel_precheck()
        self.checks.pending_edits.clear()  # kullanıcı vazgeçmeyi onayladı; kapanan projeye geç yazılmasın
        running = [t for t in (self.task, self._update_task, self._spell_scan, self._board_task) if t is not None]
        for thread in running:
            thread.cancel()
        self.hide()  # bekleme sürerken pencere "yanıt vermiyor" görünmesin
        for thread in running:
            thread.wait()  # ağ zaman aşımlarıyla sınırlı; çalışan iş parçacığı yok edilemez
        self._recovery_timer.stop()
        self._mascot_rest.stop()
        self._mascot_poll.stop()
        self.provider_probe.close()
        self.recovery.clear()
        self.project.close()
        event.accept()

    # --- kurtarma ve son projeler ----------------------------------------------------------

    def write_recovery(self) -> None:
        """Kaydedilmemiş projede değişiklik varsa kurtarma kopyasını yeniler (arayüz iş parçacığında, hızlı)."""
        self.projects.write_recovery()

    def offer_recovery(self) -> bool:
        """Önceki oturumdan kalmış kurtarma kopyası varsa kurtarılmasını önerir. Proje kurtarıldıysa True."""
        return self.projects.offer_recovery()

    def ask_recovery(self, newest: RecoveryFile, count: int) -> str:
        """ "recover", "discard" ya da "later" (testlerde değiştirilir)."""
        return self.projects.ask_recovery(newest, count)

    def recover_from(self, leftover: RecoveryFile) -> bool:
        return self.projects.recover_from(leftover)

    def recent_projects(self) -> list[Path]:
        return self.recent.paths()

    def _fill_recent_menu(self) -> None:
        self.projects.fill_recent_menu()

    def open_recent(self, path: Path) -> None:
        self.projects.open_recent(path)
