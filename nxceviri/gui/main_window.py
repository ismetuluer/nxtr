"""Ana pencere: adım gezgini, menüler, proje yönetimi ve arka plan görevleri."""

from __future__ import annotations

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
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QWidget,
)

from nxceviri import __version__
from nxceviri.core.errors import NxError
from nxceviri.core.export.layeredfs import (
    INFO_FILE,
)
from nxceviri.core.formats.derived import GraphicsSupport
from nxceviri.core.formats.registry import (
    BUILTIN_PLUGINS,
    load_user_plugins,
    member_reader,
    user_plugin_report,
)
from nxceviri.core.formats.scanner import ScanReport
from nxceviri.core.keys import KeySet
from nxceviri.core.pipeline import (
    Inputs,
    check_sources,
    clear_cache,
    default_cache_dir,
    dir_size,
    extract_texts,
    opened_view,
)
from nxceviri.core.plugins.loader import PluginInfo, PluginReport
from nxceviri.core.plugins.trust import PluginTrust
from nxceviri.core.progress import ProgressCallback, TaskContext
from nxceviri.core.project import Change, Project, SourceRecord, TranslationRow
from nxceviri.core.qa import ignored
from nxceviri.core.qa.autofix import FixPlan, plan_reflow
from nxceviri.core.qa.checks import (
    QaIssue,
)
from nxceviri.core.qa.fixrun import FixSettings
from nxceviri.core.qa.fonts import FontReport
from nxceviri.core.qa.live import LiveContext
from nxceviri.core.qa.profanity import ProfanityConfig
from nxceviri.core.qa.terms import implicit_terms
from nxceviri.core.secrets import DEEPL_API_KEY, KeyringStore, SecretStore
from nxceviri.core.selfupdate import PreparedInstall, current_install, launch_installer
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.loader import load_spell_checker
from nxceviri.core.spell.report import UnknownWordCache, replace_unknown
from nxceviri.core.spell.suggest import Suggestion
from nxceviri.core.spell.userdict import UserDictionary, default_user_dictionary_path
from nxceviri.core.translate.fitconfig import (
    FitConfig,
)
from nxceviri.core.translate.fitwidth import WidthMeasure
from nxceviri.core.translate.origin import PROVIDER_MEMORY, PROVIDER_NAMES, MachineOrigin
from nxceviri.core.translate.probe import deepl_summary, ollama_summary
from nxceviri.core.translate.providers.base import ProviderError, TranslationProvider
from nxceviri.core.translate.providers.deepl import DeepLProvider
from nxceviri.core.translate.providers.ollama import DEFAULT_URL
from nxceviri.core.translate.runner import (
    ACTION_TRANSLATE,
    MachineJob,
    RunSummary,
)
from nxceviri.core.translate.status import TRANSLATED_STATUSES, Status
from nxceviri.core.translate.terms import TermCandidate
from nxceviri.core.translate.uppercase import UppercaseRules
from nxceviri.core.translate.widths import WidthTable
from nxceviri.core.update import (
    Updater,
    app_root,
    is_packaged,
    relaunch,
)
from nxceviri.gui import motion
from nxceviri.gui.add_game_page import RELINK_ACTION, AddGamePage
from nxceviri.gui.changes_dialog import ChangesDialog
from nxceviri.gui.checks_controller import MANUAL_LIMIT_KEY, ChecksController
from nxceviri.gui.csv_dialog import CsvExportDialog
from nxceviri.gui.exchange_controller import ExchangeController
from nxceviri.gui.export_controller import ExportController
from nxceviri.gui.export_page import ExportPage
from nxceviri.gui.fonts_controller import FontsController
from nxceviri.gui.graphics_controller import GraphicsController
from nxceviri.gui.help_window import STEP_TOPICS, TOPIC_START, HelpWindow
from nxceviri.gui.history_controller import HistoryController
from nxceviri.gui.jobs import new_job_id
from nxceviri.gui.machine_controller import REVISE_INSTRUCTION_KEY, TRANSLATE_INSTRUCTION_KEY, MachineController
from nxceviri.gui.machine_dialogs import (
    PROVIDER_DEEPL,
    PROVIDER_OLLAMA,
    SCOPE_ALL,
    MachineSettings,
    make_provider,
)
from nxceviri.gui.main_layout import MASCOT_POLL_MS, build_layout, connect_pages
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
from nxceviri.gui.scan_controller import ScanController
from nxceviri.gui.scan_page import ScanPage
from nxceviri.gui.schedule_controller import ScheduleController
from nxceviri.gui.settings_dialog import PAGE_VIEW, SettingsDialog
from nxceviri.gui.shortcuts import ShortcutRegistry
from nxceviri.gui.spell_controller import SpellController
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
from nxceviri.gui.terms_controller import TermsController
from nxceviri.gui.theme import (
    DEFAULT_FONT_SIZE,
    FONT_SIZES,
    ThemeMode,
    apply_theme,
    clamp_font_size,
)
from nxceviri.gui.translate_page import TranslatePage
from nxceviri.gui.update_controller import UpdateController
from nxceviri.gui.update_dialog import UpdateDialog, UpdaterFactory
from nxceviri.gui.widgets import format_int, format_size

#: Modülün dışa verdiği adlar; adım sabitleri `step_nav`'da, talimat anahtarları `machine_controller`'da,
#: `MANUAL_LIMIT_KEY` `checks_controller`'da tanımlıdır, buradan da alınabilsinler diye yeniden verilir.
#: `implicit_terms`'i makine denetleyicisi bu modülden okur (testler onu burada değiştirir); `UpdateDialog`'u
#: güncelleme, `replace_unknown`'u yazım denetimi denetleyicisi okur; `opened_view`, `check_sources` ve
#: `member_reader`'ı font ve görseller denetleyicisi, `CsvExportDialog` ile `ChangesDialog`'u dış redaksiyon
#: denetleyicisi, `check_sources` ile `extract_texts`'i tarama denetleyicisi okur.
__all__ = [
    "MANUAL_LIMIT_KEY",
    "MASCOT_SLEEP_S",
    "REVISE_INSTRUCTION_KEY",
    "STEP_ADD",
    "STEP_EXPORT",
    "STEP_QA",
    "STEP_SCAN",
    "STEP_TRANSLATE",
    "TRANSLATE_INSTRUCTION_KEY",
    "ChangesDialog",
    "CsvExportDialog",
    "MainWindow",
    "UpdateDialog",
    "ask_full_folder",
    "build_save_box",
    "check_sources",
    "choose_button",
    "extract_texts",
    "implicit_terms",
    "log_dir",
    "member_reader",
    "opened_view",
    "replace_unknown",
]

log = logging.getLogger(__name__)

APP_TITLE = "NXTR"


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
#: Sağlayıcı durumu sorgularının zaman aşımı (sn); arka plandadır ama ipucunu uzun bekletmez.
PROBE_TIMEOUT_S = 2.0


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NXCeviri" / "logs"


def _preview(text: str) -> str:
    """Satır listesinde gösterilecek kısa çeviri metni (boşluklar tek, uzunsa kesilir)."""
    flat = " ".join(text.split())
    return flat if len(flat) <= PREVIEW_CHARS else flat[: PREVIEW_CHARS - 1] + "…"


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


#: Maskot: "bitti" ve "hata" hâllerinin süresi (ms); sistem bu kadar saniye boştaysa uyur
#: (boşta denetim aralığı `main_layout.MASCOT_POLL_MS`).
MASCOT_DONE_MS = 4000
MASCOT_ERROR_MS = 10000
MASCOT_SLEEP_S = 5 * 60


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

    # `main_layout.build_layout`'un kurduğu parçalar (mypy için burada bildirilir).
    nav_column: QWidget
    nav_header: ProjectHeader
    nav: StepNav
    nav_toggle: QToolButton
    pages: QStackedWidget
    add_page: AddGamePage
    scan_page: ScanPage
    translate_page: TranslatePage
    qa_page: QaPage
    export_page: ExportPage
    update_badge: QPushButton
    status_segments: StatusSegments
    notifier: NotificationCenter
    notice_button: HistoryButton
    help_window: HelpWindow | None
    mascot: MascotWidget
    _nav_anim: SpringAnimator | None
    _nav_collapsed: bool
    _mascot_rest: QTimer
    _mascot_poll: QTimer

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
        self._import_language: str  # son aktarmanın kaynak dili (aktarma başlarken yazılır)
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
        self.updates = UpdateController(self)
        self.spelling = SpellController(self)
        self.terms = TermsController(self)
        self.fonts = FontsController(self)
        #: Kontrol Et → Grafik: resim klasörü, arka plan denetimi, klasör izleme, onay; durumu da orada.
        self.graphics_check = GraphicsController(self)
        self.exchange = ExchangeController(self)
        self.history = HistoryController(self)
        #: Anahtarlar, kaynak dosyalar, tarama ve metin aktarma; durum pencerede kalır.
        self.scanning = ScanController(self)
        #: Makine işleri (çevir, yeniden çevir, talimatla düzelt); durum pencerede kalır.
        self.machine = MachineController(self)
        #: Çeviri satırları her yeniden kurulduğunda artar; satırlara bağlı ağır hesapların önbelleği buna bağlıdır.
        self._rows_version = 0
        self._fit_lists_cache: tuple[int, list[str], list[str], list[str]] | None = None
        self._limits_key: tuple[object, ...] | None = None
        #: Genişlik ölçümü: (satır sürümü, sığdırma ayarı, tablo, ölçüm) ve ölçüm tablosu (ayar metni, tablo).
        self._width_cache: tuple[int, FitConfig, WidthTable, WidthMeasure] | None = None
        self._width_table_cache: tuple[str, WidthTable] | None = None
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

        build_layout(self)
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

        connect_pages(self)

        #: Haftalık zamanlayıcı (seçilen saatlerde otomatik çeviri / redaksiyon); dakikada bir denetler.
        self.scheduler = ScheduleController(self)
        self.scheduler.timer.start()
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
        return self.updates.open_updates()

    def _install_package(self, prepared: PreparedInstall, install_dir: Path) -> bool:
        return self.updates._install_package(prepared, install_dir)

    def check_updates_in_background(self) -> None:
        return self.updates.check_updates_in_background()

    def _default_updater(self, token: str | None) -> Updater:
        return self.updates._default_updater(token)

    def _test_notification(self) -> None:
        """Ayarlar → Bildirimler'deki deneme: seçili kanallarla (Windows bildirimi, ses) örnek bildirim."""
        self.notifier.notify(LEVEL_SUCCESS, "Deneme bildirimi", "Bildirimler böyle görünür.", loud=True)

    def notify_update_failure(self, reason: str) -> None:
        return self.updates.notify_update_failure(reason)

    def _update_checked(self, result: object) -> None:
        return self.updates._update_checked(result)

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
        missing = any(not s.path.is_file() for s in self.sources)
        self.add_page.set_files_message(
            "warning", " ".join(problems) if self.sources else "", RELINK_ACTION if missing else ""
        )
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
        """Son kullanılan çeviri sağlayıcısının kimliği ("ollama", "deepl", "anthropic"…); seçilmediyse boş."""
        kind = str(self.settings.value("translate/provider", ""))
        return kind if kind in PROVIDER_NAMES and kind != PROVIDER_MEMORY else ""

    def _probe_provider(self) -> None:
        """Sağlayıcı bölmesinin ipucu açılırken durumu (kota / bellekteki model) arka planda yeniler."""
        kind = self._provider_kind()
        if not kind:
            return
        if kind not in (PROVIDER_OLLAMA, PROVIDER_DEEPL):
            # Bulut hizmetlerinde her ipucunda ağa gidilmez (ücretli olabilir): yalnızca seçili model gösterilir.
            self._provider_tip_title = PROVIDER_NAMES[kind]
            model = self.machine.remembered_providers().get(kind, ("", ""))[1]
            self._show_provider_tip([f"Model: {model}"] if model else [])
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
            self.graphics_check.shown()
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
        return self.scanning._restore_keys()

    def _choose_keys(self) -> None:
        return self.scanning._choose_keys()

    def load_keys_file(self, path: Path, remember: bool = True) -> bool:
        return self.scanning.load_keys_file(path, remember)

    def _choose_title_keys(self) -> None:
        return self.scanning._choose_title_keys()

    def load_title_keys_file(self, path: Path, remember: bool = True) -> bool:
        return self.scanning.load_title_keys_file(path, remember)

    def _clear_title_keys(self) -> None:
        return self.scanning._clear_title_keys()

    def _keys_path(self) -> Path | None:
        return self.scanning._keys_path()

    def _show_keys_status(self, path: Path | None = None) -> None:
        return self.scanning._show_keys_status(path)

    # --- kaynak dosyalar -------------------------------------------------------------------

    def _browse_files(self) -> None:
        return self.scanning._browse_files()

    def add_files(self, paths: list[Path]) -> None:
        return self.scanning.add_files(paths)

    def _files_added(self, result: object, skipped: list[str]) -> None:
        return self.scanning._files_added(result, skipped)

    def _files_failed(self, text: str) -> None:
        return self.scanning._files_failed(text)

    def _remove_source(self, row: int) -> None:
        return self.scanning._remove_source(row)

    def _sources_changed(self) -> None:
        return self.scanning._sources_changed()

    def relink_sources(self, folders: list[Path]) -> int:
        return self.scanning.relink_sources(folders)

    def relink_sources_dialog(self) -> None:
        return self.scanning.relink_sources_dialog()

    def ask_relink_folder(self, start: Path) -> Path | None:
        return self.scanning.ask_relink_folder(start)

    # --- tarama ----------------------------------------------------------------------------

    def _go_scan(self) -> None:
        return self.scanning._go_scan()

    def start_scan(self) -> None:
        return self.scanning.start_scan()

    def _scan_done(self, result: object) -> None:
        return self.scanning._scan_done(result)

    def _scan_cancelled(self) -> None:
        return self.scanning._scan_cancelled()

    def _extract(self, mode: str) -> None:
        return self.scanning._extract(mode)

    def _diagnosis_report(self) -> None:
        return self.scanning._diagnosis_report()

    # --- kontrol (QA) ----------------------------------------------------------------------

    def _font_patch_on(self) -> bool:
        return self.fonts._font_patch_on()

    def _stored_font_overrides(self) -> dict[str, str]:
        return self.fonts._stored_font_overrides()

    def _save_font_overrides(self, overrides: dict[str, str]) -> None:
        return self.fonts._save_font_overrides(overrides)

    def _title_id_hex(self) -> str:
        return self.fonts._title_id_hex()

    def _font_overrides(self) -> dict[str, dict[str, bytes]]:
        return self.fonts._font_overrides()

    def import_edited_font(self, source: str) -> None:
        return self.fonts.import_edited_font(source)

    def reset_edited_font(self, source: str) -> None:
        return self.fonts.reset_edited_font(source)

    def export_font_file(self, source: str) -> None:
        return self.fonts.export_font_file(source)

    def _font_files(self) -> frozenset[str]:
        return self.fonts._font_files()

    def _patchable_letters(self) -> str:
        return self.fonts._patchable_letters()

    def _missing_letters(self) -> str:
        return self.fonts._missing_letters()

    def _transliterate_letters(self) -> str:
        return self.fonts._transliterate_letters()

    def _refresh_qa(self) -> None:
        return self.checks._refresh_qa()

    def _rows_replaced(self) -> None:
        return self.checks._rows_replaced()

    def _fit_lists(self) -> tuple[list[str], list[str], list[str]]:
        return self.checks._fit_lists()

    def _refresh_limits(self) -> None:
        return self.checks._refresh_limits()

    def _reload_rows(self) -> None:
        """Tabloyu projeden yeniler; panelde bekleyen metin önce kaydedilir ki yenilenen satırlar bayat kalmasın."""
        self.translate_page.flush_pending()
        self.translate_page.set_rows(self.project.translation_rows())

    def _push_fit_to_page(self) -> None:
        return self.checks._push_fit_to_page()

    def _load_live_kinds(self) -> frozenset[str]:
        return self.checks._load_live_kinds()

    def _sync_live(self, force: bool = False) -> None:
        return self.checks._sync_live(force)

    def _apply_spell_copied(self) -> None:
        return self.checks._apply_spell_copied()

    def _set_spell_copied(self, on: bool) -> None:
        return self.checks._set_spell_copied(on)

    def _set_live_kinds(self, kinds: list[str]) -> None:
        return self.checks._set_live_kinds(kinds)

    def _manual_limit(self) -> int:
        return self.checks._manual_limit()

    def _save_manual_limit(self, limit: int) -> None:
        return self.checks._save_manual_limit(limit)

    def _fit_config(self) -> FitConfig:
        return self.checks._fit_config()

    def _width_table(self) -> WidthTable:
        return self.checks._width_table()

    def _width_measure(self) -> WidthMeasure | None:
        return self.checks._width_measure()

    def _save_fit(self) -> None:
        return self.checks._save_fit()

    def _fit_recheck_due(self) -> None:
        return self.checks._fit_recheck_due()

    def _learn_rules(self, scope: str) -> None:
        return self.checks._learn_rules(scope)

    def scan_fonts(self) -> None:
        return self.fonts.scan_fonts()

    def _set_transliterate(self, mode: str) -> None:
        return self.fonts._set_transliterate(mode)

    def _set_font_patch(self, enabled: bool) -> None:
        return self.fonts._set_font_patch(enabled)

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

    def _profanity_config(self) -> ProfanityConfig:
        return self.checks.profanity_config()

    def set_profanity_level(self, level: str) -> None:
        self.checks.set_profanity_level(level)

    def allow_profanity_words(self, words: list[str]) -> None:
        self.checks.allow_profanity_words(words)

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
        return self.spelling.open_spell_window()

    def _refresh_spell_window(self, force: bool = False) -> None:
        return self.spelling._refresh_spell_window(force)

    def _start_spell_scan(self, stale: list[TranslationRow], spell: SpellChecker, extra: frozenset[str]) -> None:
        return self.spelling._start_spell_scan(stale, spell, extra)

    def _spell_scan_finished(self) -> None:
        return self.spelling._spell_scan_finished()

    def _add_from_spell_window(self, words: list[str]) -> None:
        return self.spelling._add_from_spell_window(words)

    def _spell_hint(self, word: str, edits: bool) -> Suggestion:
        return self.spelling._spell_hint(word, edits)

    def _spell_word_rows(self, words: list[str]) -> dict[str, list[TranslationRow]] | None:
        return self.spelling._spell_word_rows(words)

    def _spell_changes(self, pairs: list[tuple[str, str]]) -> list[tuple[int, str]] | None:
        return self.spelling._spell_changes(pairs)

    def _replace_spell_word(self, old: str, new: str) -> None:
        return self.spelling._replace_spell_word(old, new)

    def _fix_spell_words(self, pairs: list[tuple[str, str]]) -> None:
        return self.spelling._fix_spell_words(pairs)

    def _apply_spell_changes(self, pairs: list[tuple[str, str]]) -> None:
        return self.spelling._apply_spell_changes(pairs)

    def _sync_spell(self) -> None:
        return self.spelling._sync_spell()

    def add_spell_words(self, words: list[str]) -> None:
        return self.spelling.add_spell_words(words)

    def add_spelling_from_qa(self, words: list[str]) -> None:
        return self.spelling.add_spelling_from_qa(words)

    def edit_user_dictionary(self) -> None:
        return self.spelling.edit_user_dictionary()

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
        return self.fonts._graphics()

    def _refresh_graphics(self) -> None:
        return self.fonts._refresh_graphics()

    def extract_graphics(self) -> None:
        return self.fonts.extract_graphics()

    def open_graphics(self) -> None:
        return self.fonts.open_graphics()

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

    def _kept_rows_text(self, ids: Sequence[int], rows: Sequence[TranslationRow], *labels: str) -> str:
        return self.exporter.kept_rows_text(ids, rows, *labels)

    def _open_export_folder(self) -> None:
        self.exporter.open_export_folder()

    # --- hazır çeviriyi içe aktarma -----------------------------------------------------------

    def import_ready_translation(self) -> None:
        return self.exchange.import_ready_translation()

    # --- çeviri tablosu ---------------------------------------------------------------------

    def import_texts(self) -> None:
        return self.scanning.import_texts()

    def _files_to_remove(self, kept: Collection[str]) -> set[str]:
        return self.scanning._files_to_remove(kept)

    def _confirm_removal(self, paths: Collection[str]) -> bool:
        return self.scanning._confirm_removal(paths)

    def ask_remove_files(self, files: int, translated: int) -> bool:
        return self.scanning.ask_remove_files(files, translated)

    def _texts_extracted(self, result: object) -> None:
        return self.scanning._texts_extracted(result)

    # --- makine çevirisi ve sözlük ---------------------------------------------------------

    def edit_glossary(self) -> None:
        return self.terms.edit_glossary()

    def add_rows_to_terminology(self) -> None:
        return self.terms.add_rows_to_terminology()

    def find_term_candidates(self) -> list[TermCandidate]:
        return self.terms.find_term_candidates()

    def suggest_glossary_terms(self) -> None:
        return self.terms.suggest_glossary_terms()

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
        return self.machine.ask_machine_settings(scopes, action, scope)

    def _machine_scopes(self) -> dict[str, list[TranslationRow]]:
        """Pencerede sunulan kapsamlar: seçili satırlar, onların grupları, filtrelenen satırlar, tümü."""
        return self.machine.machine_scopes()

    def _remember_machine_settings(self, chosen: MachineSettings) -> bool:
        return self.machine.remember_machine_settings(chosen)

    def start_machine_translation(self, action: str = ACTION_TRANSLATE, from_selection: bool = False) -> None:
        """Çevir / yeniden çevir / talimatla düzelt penceresini açar ve seçilen işi başlatır."""
        self.machine.start_machine_translation(action, from_selection)

    def _launch_machine(
        self,
        chosen: MachineSettings,
        job: MachineJob,
        *,
        set_running: Callable[[bool], None],
        on_progress: Callable[[int, int, str], None],
        report: Callable[[str, str], None],
        job_id: str = "",
        on_outcome: Callable[[str, RunSummary | None], None] | None = None,
        title_prefix: str = "",
    ) -> None:
        """Makine işini arka planda çalıştırır; sonuçlar parti parti projeye yazılır."""
        self.machine.launch_machine(
            chosen,
            job,
            set_running=set_running,
            on_progress=on_progress,
            report=report,
            job_id=job_id,
            on_outcome=on_outcome,
            title_prefix=title_prefix,
        )

    # --- değişiklikler ve geçmiş -------------------------------------------------------------

    def _set_last_job(self, job_id: str) -> int:
        return self.history.set_last_job(job_id)

    def _refresh_marks(self, ids: Sequence[int] | None = None) -> None:
        return self.history.refresh_marks(ids)

    def show_job_changes(self) -> None:
        return self.history.show_job_changes()

    def _edit_from_changes(self, row_id: int, text: str) -> str | None:
        return self.history.edit_from_changes(row_id, text)

    def _context_html(self, row_id: int) -> str:
        return self.history.context_html(row_id)

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
        return self.history.replace_translations(changes)

    def show_row_history(self, entry_id: int) -> None:
        return self.history.show_row_history(entry_id)

    def _open_changes(self, dialog: ChangesDialog) -> None:
        return self.history.open_changes(dialog)

    def _revert(self, changes: list[Change]) -> None:
        return self.history.revert(changes)

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
        """Makine işinin bir partisini yazar (`machine_controller.MachineController.machine_results`)."""
        self.machine.machine_results(results, overwrite_approved, job_id, origin=origin, memory_ids=memory_ids)

    def _update_undo_action(self) -> None:
        return self.history.update_undo_action()

    def _update_redo_action(self) -> None:
        return self.history.update_redo_action()

    def undo_last(self) -> None:
        return self.history.undo_last()

    def redo_last(self) -> None:
        return self.history.redo_last()

    def _show_stepped_rows(self, rows: list[TranslationRow]) -> None:
        return self.history.show_stepped_rows(rows)

    # --- dış dosya: dışa / içe aktarma (redaksiyon ve çeviri) ------------------------------------

    def export_csv(self) -> None:
        return self.exchange.export_csv()

    def export_translation(self) -> None:
        return self.exchange.export_translation()

    def export_findings(self) -> None:
        return self.exchange.export_findings()

    def _export_external(self, *, translation: bool) -> None:
        return self.exchange._export_external(translation=translation)

    def import_csv(self) -> None:
        return self.exchange.import_csv()

    def import_translation(self) -> None:
        return self.exchange.import_translation()

    def _import_external(self, *, translation: bool) -> None:
        return self.exchange._import_external(translation=translation)

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
        self.scheduler.timer.stop()  # kapanırken yeni iş başlatılmasın
        running = [t for t in (self.task, self._update_task, self._spell_scan, self._board_task) if t is not None]
        for thread in running:
            thread.cancel()
        self.hide()  # bekleme sürerken pencere "yanıt vermiyor" görünmesin
        for thread in running:
            thread.wait()  # ağ zaman aşımlarıyla sınırlı; çalışan iş parçacığı yok edilemez
        self.graphics_check.shutdown()  # izleyici durur, süren grafik denetimi iptal edilip beklenir
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
