"""Menü çubuğu: Dosya, Düzen, Görünüm, Çeviri, Git, Araçlar, Yardım.

Her komutun tuşu `shortcuts.COMMANDS` kataloğundan gelir ve `ShortcutRegistry.bind` ile eyleme bağlanır; burada
tuş yazılmaz. Kullanıcı bir tuşu değiştirince menüdeki eylem ve ipucu kendiliğinden güncellenir. Menü öğeleri
gizlenmez, anlamsız olduklarında pasif olur: sayfa/proje yokken ya da işlem sürerken (`refresh`). Seçime bağlı
öğeler yalnızca Çevir sayfası açıkken ve uygun satır seçiliyken etkindir.

Bu modül ana pencerenin yöntemlerini çağırır; iş mantığı içermez (menü yalnızca bir giriş noktasıdır).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu

from nxceviri.core.translate.runner import ACTION_RETRANSLATE, ACTION_REVISE, ACTION_TRANSLATE
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.theme import DEFAULT_FONT_SIZE, FONT_SIZES, THEME_LABELS, ThemeMode
from nxceviri.gui.view_actions import PANE_BOTTOM, PANE_RIGHT

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

#: Git menüsü: (komut kimliği, simge); sırası kenar çubuğundaki adımlarla aynıdır.
_GO_COMMANDS = (
    ("go.add", "circle-plus"),
    ("go.scan", "scan-search"),
    ("go.translate", "languages"),
    ("go.qa", "shield-check"),
    ("go.export", "package"),
)


class Menus:
    """Ana pencerenin menü çubuğunu kurar ve öğelerin etkinliğini güncel tutar."""

    extract_candidates: QAction
    extract_all: QAction
    diagnosis: QAction

    def __init__(self, window: MainWindow) -> None:
        self.window = window
        #: Komut kimliği → menüdeki eylem (kayıt defterine bağlı olanlar).
        self.actions: dict[str, QAction] = {}
        #: Hazır çeviri ve dış redaksiyon/çeviri öğeleri: çeviri tablosunda satır yokken pasiftir.
        self._needs_rows: list[QAction] = []

    # --- kurma ---------------------------------------------------------------------------

    def _menu(self, title: str, *, tips: bool = False) -> QMenu:
        menu = self.window.menuBar().addMenu(title)
        menu.setToolTipsVisible(tips)
        return menu

    def _add(
        self,
        menu: QMenu,
        text: str,
        slot: Callable[[], object],
        *,
        command: str | None = None,
        icon: str | None = None,
        tip: str | None = None,
    ) -> QAction:
        window = self.window
        action = QAction(text, window)
        # Slot, `triggered(bool)` işaretini almasın (isteğe bağlı parametreli yöntemler yanlış değer görmesin).
        action.triggered.connect(lambda _checked=False, fn=slot: fn())
        self._finish(menu, action, command, icon, tip)
        return action

    def _finish(self, menu: QMenu, action: QAction, command: str | None, icon: str | None, tip: str | None) -> None:
        if icon is not None:
            bind_icon(action, icon)
        if command is not None:
            self.window.shortcuts.bind(command, action, tip=tip)
            self.actions[command] = action
        elif tip is not None:
            action.setToolTip(tip)
        menu.addAction(action)

    def _share(self, menu: QMenu, action: QAction, command: str | None = None, icon: str | None = None) -> None:
        """Başka bir yerde (sayfa, durum çubuğu) yaşayan eylemi menüye koyar; tuşu kayıt defterinden alır."""
        if icon is not None:
            bind_icon(action, icon)
        if command is not None:
            self.actions[command] = action
        menu.addAction(action)

    def _submenu(self, menu: QMenu, title: str, icon: str) -> QMenu:
        sub = menu.addMenu(title)
        sub.setToolTipsVisible(menu.toolTipsVisible())
        bind_icon(sub.menuAction(), icon)
        return sub

    def build(self) -> None:
        self._file_menu()
        self._edit_menu()
        self._view_menu()
        self._translate_menu()
        self._go_menu()
        self._tools_menu()
        self._help_menu()
        self.refresh()

    def _track_selection(self, menu: QMenu) -> None:
        """Menü açılırken seçime bağlı öğeler gerçek duruma getirilir; kapanınca kısayollar için yeniden açılır."""
        menu.aboutToShow.connect(self.refresh)
        menu.aboutToShow.connect(self.refresh_selection)
        menu.aboutToHide.connect(self.refresh)

    def _file_menu(self) -> None:
        w = self.window
        menu = self._menu("&Dosya")
        self._add(menu, "Yeni Proje", w.new_project, command="file.new", icon="file-plus")
        self._add(menu, "Proje Aç…", w._open_project_dialog, command="file.open", icon="folder-open")
        w.recent_menu = self._submenu(menu, "Son Projeler", "history")
        w.recent_menu.aboutToShow.connect(w._fill_recent_menu)
        menu.addSeparator()
        w.save_action = self._add(menu, "Kaydet", w.save_project, command="file.save", icon="save")
        self._add(menu, "Farklı Kaydet…", w.save_project_as, command="file.save_as", icon="save-all")
        menu.addSeparator()
        keys_menu = self._submenu(menu, "Anahtarlar", "key-round")
        w.keys_action = self._add(keys_menu, "prod.keys Seç…", w._choose_keys, icon="key-round")
        self._add(keys_menu, "title.keys Seç…", w._choose_title_keys, icon="key-round")
        w.title_keys_clear_action = self._add(keys_menu, "title.keys Dosyasını Kaldır", w._clear_title_keys, icon="x")
        w.title_keys_clear_action.setEnabled(False)
        menu.addSeparator()
        w.cache_action = self._add(menu, "Önbelleği Temizle…", w._clear_cache, icon="trash-2")
        menu.addSeparator()
        self._add(menu, "Ayarlar…", w.open_settings, command="app.settings", icon="settings")
        menu.addSeparator()
        self._add(menu, "Çıkış", w.close, command="app.quit", icon="log-out")

    def _edit_menu(self) -> None:
        w = self.window
        page = w.translate_page
        menu = self._menu("Dü&zen", tips=True)
        w.undo_action = self._add(menu, "Geri Al", w.undo_last, command="edit.undo", icon="undo-2")
        menu.aboutToShow.connect(w._update_undo_action)
        self._track_selection(menu)
        menu.addSeparator()
        self._add(menu, "Bul…", w._menu_find, command="edit.find", icon="search")
        self._add(menu, "Değiştir…", w._menu_find_replace, command="edit.replace", icon="replace")
        self._add(
            menu,
            "Tabloyu Süz…",
            w._menu_search,
            command="edit.filter",
            icon="funnel",
            tip="Çeviri tablosunun arama kutusuna gider.",
        )
        self._add(
            menu,
            "Sonrakini Bul",
            w._menu_find_next,
            command="edit.find_next",
            icon="chevron-down",
            tip="Bul çubuğu açıkken sonraki eşleşme; kapalıyken sonraki bakılacak satır.",
        )
        self._add(
            menu,
            "Öncekini Bul",
            w._menu_find_previous,
            command="edit.find_prev",
            icon="chevron-up",
            tip="Bul çubuğu açıkken önceki eşleşme; kapalıyken önceki bakılacak satır.",
        )
        menu.addSeparator()
        self._add(
            menu,
            "Satırları Yeniden Böl",
            page.reflow_selected,
            command="edit.reflow",
            icon="wrap-text",
            tip="Seçili satırların çevirisindeki satır sonlarını sınıra ya da orijinale göre dengeli yeniden böler.",
        )
        self._add(
            menu,
            "Orijinali Çeviri Olarak Yaz",
            page.copy_source_selected,
            command="edit.copy_source",
            icon="copy",
            tip="Çevrilmeyecek metinler (özel adlar, sayılar) için.",
        )
        self._add(
            menu,
            "Çeviriyi Temizle",
            page.clear_selected,
            command="edit.clear",
            icon="eraser",
            tip="Seçili satırların çevirisini siler.",
        )

    def _view_menu(self) -> None:
        w = self.window
        page = w.translate_page
        view = page.view_actions
        menu = self._menu("&Görünüm", tips=True)
        menu.aboutToShow.connect(page.refresh_legend)  # tema değişmiş olabilir
        menu.aboutToShow.connect(self.refresh)
        w.nav_action = QAction("Kenar Çubuğu", w, checkable=True)
        w.nav_action.setChecked(not w._nav_collapsed)
        w.nav_action.triggered.connect(lambda checked: w.set_nav_collapsed(not checked))
        self._finish(menu, w.nav_action, "view.nav", "panel-left", "Soldaki adım listesini daralt ya da aç.")
        self._share(menu, view.pane_toggle, "view.pane")
        pane_menu = self._submenu(menu, "Panel Konumu", "panel-right")
        for action in view.pane_actions.values():
            pane_menu.addAction(action)
        self.actions["view.pane_bottom"] = view.pane_actions[PANE_BOTTOM]
        self.actions["view.pane_right"] = view.pane_actions[PANE_RIGHT]
        menu.addSeparator()
        self._share(menu, view.symbols, "view.symbols")
        align_menu = self._submenu(menu, "Hizala", "align-left")
        for key, action in view.align_actions.items():
            align_menu.addAction(action)
            self.actions[f"view.align_{key}"] = action
        self._share(menu, page.wrap_box, "view.wrap", "wrap-text")
        self._share(menu, page.colors_box, "view.issue_colors", "triangle-alert")
        self._share(menu, page.error_rows_box, "view.error_rows", "circle-x")
        self._share(menu, page.previous_box, "view.previous", "git-compare")
        menu.addSeparator()
        theme_menu = self._submenu(menu, "Tema", "monitor")
        w.theme_group = QActionGroup(w)
        current = w._theme_mode()
        for mode in ThemeMode:
            act = QAction(THEME_LABELS[mode], w, checkable=True)
            act.setData(mode.value)
            act.setChecked(mode == current)
            act.triggered.connect(lambda _=False, m=mode: w._set_theme(m))
            w.theme_group.addAction(act)
            theme_menu.addAction(act)
        size_menu = self._submenu(menu, "Yazı Boyutu", "case-sensitive")
        w.size_group = QActionGroup(w)
        current_size = w._font_size()
        for size in FONT_SIZES:
            act = QAction(f"{size} punto" + ("  (varsayılan)" if size == DEFAULT_FONT_SIZE else ""), w, checkable=True)
            act.setChecked(size == current_size)
            act.triggered.connect(lambda _=False, n=size: w._set_font_size(n))
            w.size_group.addAction(act)
            size_menu.addAction(act)
        size_menu.addSeparator()
        for text, command, icon, step in (
            ("Büyüt", "view.font_bigger", "chevron-up", 1),
            ("Küçült", "view.font_smaller", "chevron-down", -1),
        ):
            self._add(size_menu, text, partial(w._step_font_size, step), command=command, icon=icon)
        self._add(
            size_menu,
            "Varsayılan boyut",
            lambda: w._set_font_size(DEFAULT_FONT_SIZE),
            command="view.font_reset",
            icon="undo-2",
        )
        for command in ("view.font_bigger", "view.font_smaller", "view.font_reset"):
            w.addAction(self.actions[command])  # menü kapalıyken de kısayol çalışsın

    def _translate_menu(self) -> None:
        w = self.window
        page = w.translate_page
        menu = self._menu("&Çeviri", tips=True)
        self._track_selection(menu)
        self._add(
            menu,
            "Otomatik Çeviri…",
            w._menu_machine,
            command="translate.auto",
            icon="sparkles",
            tip="Ollama veya DeepL ile toplu çeviri, yeniden çeviri ve redaksiyon.",
        )
        self._add(
            menu,
            "Seçili Satırları Çevir…",
            lambda: w.start_machine_translation(ACTION_TRANSLATE, True),
            command="translate.selected",
            icon="languages",
        )
        self._add(
            menu,
            "Seçili Satırları Yeniden Çevir…",
            lambda: w.start_machine_translation(ACTION_RETRANSLATE, True),
            command="translate.retranslate",
            icon="refresh-cw",
        )
        self._add(
            menu,
            "Redaksiyon…",
            lambda: w.start_machine_translation(ACTION_REVISE, True),
            command="translate.revise",
            icon="pen-line",
            tip="Seçili satırları bir talimata göre düzeltir.",
        )
        menu.addSeparator()
        self._add(
            menu,
            "Onayla",
            page.approve_selected,
            command="translate.approve",
            icon="circle-check",
            tip="Makine çevirisini veya dış redaksiyonu değiştirmeden onaylar.",
        )
        self._add(
            menu,
            "Onayı Kaldır",
            page.unapprove_selected,
            command="translate.unapprove",
            icon="circle-x",
            tip="Metni değiştirmeden durumu “Makine”ye döndürür.",
        )
        menu.addSeparator()
        self._add(menu, "Terminoloji…", w.edit_glossary, command="translate.glossary", icon="book-open")
        self._add(
            menu,
            "Seçili Satırları Terminolojiye Ekle…",
            w.add_rows_to_terminology,
            command="translate.add_terms",
            icon="circle-plus",
            tip="Seçili satırların orijinali ve çevirisi (kod, sayı ve sembollerden ayıklanarak) terim olur.",
        )
        self._share(menu, page.changes_button, "translate.changes", "git-compare")
        self._add(menu, "Çeviri Geçmişi…", page.history_selected, command="translate.history", icon="history")
        menu.addSeparator()
        self._needs_rows.append(
            self._add(menu, "Hazır Çeviriyi İçe Aktar…", w.import_ready_translation, icon="file-down")
        )
        redaction = self._submenu(menu, "Dış Redaksiyon", "user-check")
        self._needs_rows.append(self._add(redaction, "Dosya Oluştur (TXT/XLSX)…", w.export_csv, icon="file-up"))
        self._needs_rows.append(self._add(redaction, "İçe Aktar…", w.import_csv, icon="file-down"))
        external = self._submenu(menu, "Dış Çeviri", "languages")
        self._needs_rows.append(self._add(external, "Dosya Oluştur (TXT/XLSX)…", w.export_translation, icon="file-up"))
        self._needs_rows.append(self._add(external, "İçe Aktar…", w.import_translation, icon="file-down"))

    def _go_menu(self) -> None:
        w = self.window
        menu = self._menu("G&it")
        menu.aboutToShow.connect(self.refresh)
        labels = ("Oyunu Ekle", "Metinleri Tara", "Çevir", "Kontrol Et", "Dışa Aktar")
        for step, ((command, icon), text) in enumerate(zip(_GO_COMMANDS, labels, strict=True)):
            self._add(menu, text, partial(w.nav.setCurrentRow, step), command=command, icon=icon)

    def _tools_menu(self) -> None:
        w = self.window
        menu = self._menu("&Araçlar")
        menu.aboutToShow.connect(self.refresh)
        self.extract_candidates = self._add(
            menu, "Metin Adaylarını Çıkar…", lambda: w._extract("candidates"), icon="folder-output"
        )
        self.extract_all = self._add(menu, "Tüm RomFS'i Çıkar…", lambda: w._extract("all"), icon="package")
        self.diagnosis = self._add(
            menu, "Teşhis Raporu…", w._diagnosis_report, command="tools.diagnosis", icon="activity"
        )
        menu.addSeparator()
        self._add(menu, "Yazım Denetimi…", w.open_spell_window, command="tools.spell_check", icon="spell-check")
        self._add(menu, "Yazım Sözlüğü…", w.edit_user_dictionary, command="tools.spell_dictionary", icon="spell-check")
        self._add(menu, "Eklentiler…", w.open_plugins, command="tools.plugins", icon="puzzle")

    def _help_menu(self) -> None:
        w = self.window
        menu = self._menu("&Yardım")
        w.update_action = self._add(menu, "Güncellemeleri Denetle…", w.open_updates, icon="download")
        w.update_action.setEnabled(w.app_root is not None or w.packaged)
        if w.app_root is None and not w.packaged:
            w.update_action.setToolTip("Bu kurulum kaynak koduyla çalışmadığı için uygulama içinden güncellenemez.")
        self._add(menu, "Log Klasörünü Aç", w._open_logs, icon="folder-open")
        self._add(menu, "Hakkında", w._about, icon="info")

    # --- etkinlik ------------------------------------------------------------------------

    #: Seçime bağlı komutlar: kısayolla tetiklenebilsin diye "Çevir sayfası ve satır var" düzeyinde açık kalır;
    #: yuvalar boş seçimi kendileri denetler. Gerçek duruma göre pasifleştirme menü açılırken yapılır.
    _SELECTION_COMMANDS = (
        "edit.reflow",
        "edit.copy_source",
        "edit.clear",
        "translate.selected",
        "translate.retranslate",
        "translate.revise",
        "translate.approve",
        "translate.unapprove",
        "translate.history",
    )

    #: İş sürerken de açık kalan seçime bağlı komutlar (satırların çevirisine dokunmazlar).
    _ALLOWED_WHILE_BUSY = ("translate.approve", "translate.unapprove", "translate.history")

    def refresh(self) -> None:
        """Öğelerin etkinliğini projenin, açık sayfanın ve süren işin durumuna göre günceller (seçimi saymaz)."""
        w = self.window
        page = w.translate_page
        a = self.actions
        busy = w.busy
        has_rows = bool(page.model.rows)
        selectable = w.pages.currentWidget() is page and has_rows

        w.save_action.setEnabled(not busy)
        w.cache_action.setEnabled(not busy)
        for command in ("edit.find", "edit.replace", "edit.filter", "edit.find_next", "edit.find_prev"):
            a[command].setEnabled(has_rows)
        for command in self._SELECTION_COMMANDS:
            a[command].setEnabled(selectable and not (busy and command not in self._ALLOWED_WHILE_BUSY))

        a["translate.auto"].setEnabled(has_rows and not busy)
        a["translate.glossary"].setEnabled(has_rows)
        for action in self._needs_rows:
            action.setEnabled(has_rows and not busy)

        report = w.report
        ready = not busy and report is not None and w.keys is not None
        self.extract_candidates.setEnabled(ready and report is not None and bool(report.text_candidates))
        self.extract_all.setEnabled(ready)
        self.diagnosis.setEnabled(ready)

        a["tools.spell_check"].setEnabled(w.spell is not None and has_rows)

        for step, (command, _icon) in enumerate(_GO_COMMANDS):
            unlocked = bool(w.nav.item(step).flags() & Qt.ItemFlag.ItemIsEnabled)
            a[command].setEnabled(unlocked and not busy)

    def refresh_selection(self) -> None:
        """Seçime bağlı öğeleri seçili satırların gerçek durumuna göre günceller (yalnızca menü açılırken çağrılır).

        Seçili satırları saymak büyük seçimlerde pahalıdır; bu yüzden seçim ya da tablo her değiştiğinde değil,
        yalnızca kullanıcı menüyü açınca yapılır.
        """
        w = self.window
        page = w.translate_page
        a = self.actions
        if w.pages.currentWidget() is not page or not page.model.rows:
            return
        counts = page.selection_counts()
        free = not w.busy
        a["edit.reflow"].setEnabled(free and counts.with_translation > 0)
        a["edit.copy_source"].setEnabled(free and counts.selected > 0)
        a["edit.clear"].setEnabled(free and counts.with_translation > 0)
        a["translate.selected"].setEnabled(free and counts.translate > 0)
        a["translate.retranslate"].setEnabled(free and counts.retranslate > 0)
        a["translate.revise"].setEnabled(free and counts.revise > 0)
        a["translate.approve"].setEnabled(counts.approvable > 0)
        a["translate.unapprove"].setEnabled(counts.approved > 0)
        a["translate.history"].setEnabled(counts.selected == 1)
        a["translate.add_terms"].setEnabled(counts.with_translation > 0)
