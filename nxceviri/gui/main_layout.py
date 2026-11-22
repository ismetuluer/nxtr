"""Ana pencerenin arayüz kurulumu: sütun, sayfalar, durum çubuğu parçaları ve sayfa sinyal bağlantıları.

`build_layout` pencerenin parçalarını (adım gezgini, sayfa yığını ve beş sayfa, durum çubuğu, bildirim merkezi,
maskot) kurar ve pencerenin öznitelikleri olarak atar; `connect_pages` sayfaların sinyallerini pencerenin
yöntemlerine bağlar. Burada iş mantığı yoktur, yalnızca kurulum ve bağlantı vardır. İkisi de `MainWindow.__init__`
içinde eskiden satırların durduğu yerde çağrılır (sıra önemlidir: örneğin başlık, ebeveynine eklendikten sonra
gizlenir; kenar çubuğunun ilk durumu `resize`'dan sonra okunur). Durum alanları, mantığa ait zamanlayıcılar ve
sağlayıcı sorgusu pencerede kalır. Bağlantılarda bağlı yöntemler, eskisi gibi, bağlama anında alınır.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from nxceviri.gui.add_game_page import AddGamePage
from nxceviri.gui.export_page import ExportPage
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.mascot import MascotWidget
from nxceviri.gui.notify import HistoryButton, NotificationCenter
from nxceviri.gui.qa_page import QaPage
from nxceviri.gui.scan_page import ScanPage
from nxceviri.gui.statusbar import StatusSegments
from nxceviri.gui.step_nav import STEP_ADD, STEP_SCAN, ProjectHeader, StepNav, TopNavBar
from nxceviri.gui.theme import current_style
from nxceviri.gui.translate_page import TranslatePage
from nxceviri.gui.widgets import button

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

#: Kenar çubuğu daralt/genişlet düğmesinin boyu ve kenar boşluğu (simgelerle hizalı).
NAV_TOGGLE_SIZE = 32
NAV_TOGGLE_MARGIN = 14
#: Maskot: sistemin boşta süresine bakma aralığı (ms).
MASCOT_POLL_MS = 5000


def build_layout(win: MainWindow) -> None:
    """Pencerenin parçalarını kurar ve öznitelik olarak atar (`MainWindow`'daki sınıf düzeyi bildirimler)."""
    win.setMinimumSize(820, 560)
    win.nav_is_top = False
    win.resize(1180, 780)

    central = QWidget()
    root = QHBoxLayout(central)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    win.nav_column = QWidget()
    win.nav_column.setObjectName("stepNavColumn")
    column = QVBoxLayout(win.nav_column)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    win.nav_header = ProjectHeader()
    win.nav = StepNav()
    win._nav_anim = None
    win._nav_collapsed = win._initial_nav_collapsed()
    win.nav.set_collapsed(win._nav_collapsed)
    win.nav.preferred_width_changed.connect(win._update_nav_width)
    column.addWidget(win.nav_header)
    win.nav_header.setHidden(win._nav_collapsed)  # ebeveynden sonra: yoksa bir anlığına ayrı pencere açılır
    column.addWidget(win.nav, 1)
    # Görünür daralt/genişlet düğmesi (menü ve Ctrl+Alt+S'nin yanında): daralmış hâlde de görünür kalır.
    win.nav_toggle = QToolButton()
    win.nav_toggle.setProperty("role", "viewTool")
    win.nav_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
    win.nav_toggle.setFixedSize(NAV_TOGGLE_SIZE, NAV_TOGGLE_SIZE)
    bind_icon(win.nav_toggle, "panel-left", size=18)
    win.nav_toggle.clicked.connect(lambda: win.set_nav_collapsed(not win._nav_collapsed))
    toggle_row = QHBoxLayout()
    toggle_row.setContentsMargins(NAV_TOGGLE_MARGIN, 4, NAV_TOGGLE_MARGIN, 12)
    toggle_row.addWidget(win.nav_toggle)
    toggle_row.addStretch(1)
    column.addLayout(toggle_row)
    win._refresh_nav_toggle()
    root.addWidget(win.nav_column)
    win._update_nav_width()
    # İçerik alanı: üstte (yalnızca üst gezinmeli temalarda görünen) adım çubuğu, altında sayfa yığını.
    win.content_area = QWidget()
    content = QVBoxLayout(win.content_area)
    content.setContentsMargins(0, 0, 0, 0)
    content.setSpacing(0)
    win.nav_top = TopNavBar()
    win.nav_top.hide()
    content.addWidget(win.nav_top)
    win.pages = QStackedWidget()
    win.add_page = AddGamePage()
    win.scan_page = ScanPage()
    win.translate_page = TranslatePage(win.shortcuts)
    win.translate_page.model.commit = win._commit_translations
    win.translate_page.replace_fn = win._replace_translations
    win.translate_page.bind_settings(win.settings)
    win.pages.addWidget(win.add_page)
    win.pages.addWidget(win.scan_page)
    win.pages.addWidget(win.translate_page)
    win.qa_page = QaPage()
    win.qa_page.model.number_of = win.translate_page.model.number
    win.qa_page.bind_settings(win.settings)
    win.export_page = ExportPage()
    win.pages.addWidget(win.qa_page)
    win.pages.addWidget(win.export_page)
    content.addWidget(win.pages, 1)
    root.addWidget(win.content_area, 1)
    win.setCentralWidget(central)
    win.statusBar().showMessage("Hazır")
    win.update_badge = button("Güncelle", "primary", icon="download")
    win.update_badge.clicked.connect(win.start_update)
    win.update_badge.hide()
    win.status_segments = StatusSegments(win.statusBar(), win.update_badge)
    win.status_segments.problems_clicked.connect(win._open_qa_from_status)
    win.status_segments.keys_clicked.connect(win._choose_keys)
    win.status_segments.bind_symbols_action(win.translate_page.view_actions.symbols)
    #: Bütün işlerin ve hataların sonucu buradan bildirilir (kart, geçmiş; arkadayken Windows bildirimi ve ses).
    win.notifier = NotificationCenter(win, win.settings)
    win.notice_button = HistoryButton(win.notifier)
    win.help_window = None
    #: Maskot: işin durumunu gösterir (çalışıyor, bitti, hata; uzun boşta uyur). Ayarlar → Görünüm'den kapatılır.
    win.mascot = MascotWidget(20)
    win.statusBar().addPermanentWidget(win.mascot)
    win.statusBar().addPermanentWidget(win.notice_button)
    win._mascot_rest = QTimer(win)
    win._mascot_rest.setSingleShot(True)
    win._mascot_rest.timeout.connect(win._mascot_settle)
    #: Uyku/uyanma: sistemin boşta süresine birkaç saniyede bir bakılır (Qt olay süzgeci yok).
    win._mascot_poll = QTimer(win)
    win._mascot_poll.setInterval(MASCOT_POLL_MS)
    win._mascot_poll.timeout.connect(win._mascot_check_idle)
    win._mascot_poll.start()
    apply_nav_position(win)


def apply_nav_position(win: MainWindow) -> None:
    """Etkin temanın gezinme konumuna göre adım listesini yerleştirir (`side`: sol sütun, `top`: üst çubuk).

    Aynı `StepNav` ve `ProjectHeader` nesneleri taşınır (ikinci bir pencere öğesi kurulmaz), böylece geçerli adım,
    sinyaller, rozetler ve adımların etkinliği korunur. Başlangıçta ve tema değişince çağrılır; değişmediyse hiçbir
    şey yapmaz. Daralt/genişlet tercihi üst kipte durur, kenar çubuğuna dönünce geri uygulanır.
    """
    top = current_style().nav_position == "top"
    if top == win.nav_is_top:
        return
    win.nav_is_top = top
    column = win.nav_column.layout()
    assert isinstance(column, QVBoxLayout)
    if top:
        column.removeWidget(win.nav_header)
        column.removeWidget(win.nav)
        win.nav_column.hide()
        win.nav.set_collapsed(False)
        win.nav.set_horizontal(True)
        win.nav_top.attach(win.nav_header, win.nav)
        win.nav_top.show()
    else:
        win.nav_top.hide()
        win.nav_top.detach(win.nav_header, win.nav)
        win.nav.set_horizontal(False)
        column.insertWidget(0, win.nav_header)
        column.insertWidget(1, win.nav, 1)
        win.nav_header.setHidden(win._nav_collapsed)
        win.nav.set_collapsed(win._nav_collapsed)
        win.nav_column.show()
        win._update_nav_width()
    nav_action = getattr(win, "nav_action", None)
    if nav_action is not None:  # menü kurulduktan sonra: üst kipte daralt/genişlet anlamsızdır
        nav_action.setEnabled(not top)


def connect_pages(win: MainWindow) -> None:
    """Sayfaların sinyallerini pencerenin yöntemlerine bağlar."""
    win.nav.currentRowChanged.connect(win._go_to)
    win.add_page.choose_keys.connect(win._choose_keys)
    win.add_page.browse_files.connect(win._browse_files)
    win.add_page.add_files.connect(win.add_files)
    win.add_page.remove_source.connect(win._remove_source)
    win.add_page.relink_requested.connect(win.relink_sources_dialog)
    win.add_page.next_step.connect(win._go_scan)
    win.add_page.open_recent.connect(win.open_recent)
    win.scan_page.start_scan.connect(lambda: win.start_scan(auto_import=True))
    win.scan_page.cancel.connect(win._cancel_task)
    win.scan_page.go_back.connect(lambda: win.nav.setCurrentRow(STEP_ADD))
    win.scan_page.report.rescan_requested.connect(win.start_scan)
    win.scan_page.report.import_requested.connect(win.import_texts)
    win.translate_page.go_to_scan.connect(lambda: win.nav.setCurrentRow(STEP_SCAN))
    win.translate_page.machine_requested.connect(win.start_machine_translation)
    win.translate_page.uppercase_changed.connect(win._save_uppercase)
    win.translate_page.machine_action_requested.connect(lambda a: win.start_machine_translation(a, True))
    win.translate_page.pane.spell_word_requested.connect(lambda w: win.add_spell_words([w]))
    win.qa_page.add_spelling_requested.connect(win.add_spelling_from_qa)
    win.qa_page.not_term_requested.connect(win.ignore_terms)
    win.qa_page.not_profanity_requested.connect(win.allow_profanity_words)
    win.qa_page.ascii_choice_requested.connect(win.apply_ascii_choice)
    win.qa_page.ignore_requested.connect(win.ignore_issues)
    win.qa_page.unignore_requested.connect(win.unignore_issues)
    win.qa_page.user_dictionary_requested.connect(win.edit_user_dictionary)
    win.translate_page.changes_requested.connect(win.show_job_changes)
    win.translate_page.fix_requested.connect(lambda kinds, ids: win.checks.apply_fixes(kinds, ids, on_translate=True))
    win.translate_page.ascii_choice_requested.connect(win.apply_ascii_choice)
    win.translate_page.history_requested.connect(win.show_row_history)
    win.translate_page.unapprove_requested.connect(win.unapprove)
    win.translate_page.reflow_requested.connect(win.reflow_selected)
    win.translate_page.csv_export_requested.connect(win.export_csv)
    win.translate_page.csv_import_requested.connect(win.import_csv)
    win.translate_page.translation_export_requested.connect(win.export_translation)
    win.translate_page.translation_import_requested.connect(win.import_translation)
    win.translate_page.cancel_machine.connect(win._cancel_task)
    win.qa_page.scan_fonts.connect(win.scan_fonts)
    win.export_page.extract_graphics.connect(win.extract_graphics)
    win.export_page.open_graphics.connect(win.open_graphics)
    win.qa_page.font_export_requested.connect(win.export_font_file)
    win.qa_page.font_import_requested.connect(win.import_edited_font)
    win.qa_page.font_reset_requested.connect(win.reset_edited_font)
    win.qa_page.run_checks.connect(win.start_checks)
    win.qa_page.stop_checks.connect(win._stop_checks)
    win.qa_page.transliterate_changed.connect(win._set_transliterate)
    win.qa_page.font_patch_changed.connect(win._set_font_patch)
    win.qa_page.open_row.connect(win._open_row)
    win.qa_page.fix_requested.connect(win.apply_fixes)
    win.qa_page.export_findings_requested.connect(win.export_findings)
    win.qa_page.fix_planner = win._plan_fix_bar
    win.qa_page.translation_edited.connect(win._edit_from_issues)
    # Çevir'de, Geri Al'da, makine işinde… değişen satırlar Kontrol Et listesinde de yeniden denetlenir.
    win.translate_page.model.rows_updated.connect(win.checks.rows_updated)
    win.qa_page.report_requested.connect(win.show_job_changes)
    win.qa_page.fix_notice.connect(win._fix_notice)
    win.qa_page.fit_changed.connect(win._save_fit)
    win.qa_page.learn_rules_requested.connect(win._learn_rules)
    win.qa_page.fit_tab_shown.connect(win._refresh_limits)
    graphics = win.qa_page.graphics
    win.qa_page.graphics_tab_shown.connect(win.graphics_check.shown)
    graphics.choose_folder.connect(win.graphics_check.choose_folder)
    graphics.extract_requested.connect(win.graphics_check.extract)
    graphics.open_folder.connect(win.graphics_check.open_folder)
    graphics.refresh_requested.connect(win.graphics_check.refresh)
    graphics.approve_toggled.connect(win.graphics_check.toggle_approval)
    win.shortcuts.bind("qa.graphics_approve", graphics.approve_action, "Grafiği onayla")
    win.export_page.choose_folder.connect(win._choose_export_folder)
    win.export_page.export_requested.connect(win.export_mod)
    win.export_page.include_errors_changed.connect(win._set_include_errors)
    win.export_page.open_folder.connect(win._open_export_folder)
    win.export_page.cancel.connect(win._cancel_task)
