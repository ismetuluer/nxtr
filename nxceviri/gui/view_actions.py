"""Çeviri sayfasının görünüm durumu: semboller, metin hizası ve çeviri panelinin konumu ile açık/kapalı durumu.

Durumların hepsi `QAction`dır ve **tek bir nesnede** yaşar; araç çubuğu düğmeleri, Görünüm menüsü ve durum
çubuğundaki ¶ düğmesi aynı eylemleri paylaşır (biri değişince hepsi değişir). Panelin konumu (altta/sağda) ile
açık/kapalı olması ayrı durumlardır: `Ctrl+J` açıp kapatır, konum seçimi paneli de açar. Değerler `QSettings`te
(uygulama ayarı, proje başına değil) saklanır; bozuk bir değer varsayılana döner ve günlüğe uyarı yazılır.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QAction, QActionGroup

from nxceviri.gui.icons import bind_icon
from nxceviri.gui.shortcuts import ShortcutRegistry

log = logging.getLogger(__name__)

ALIGN_LEFT = "left"
ALIGN_CENTER = "center"
ALIGN_RIGHT = "right"
ALIGNMENTS = (ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT)

PANE_BOTTOM = "bottom"
PANE_RIGHT = "right"
PANES = (PANE_BOTTOM, PANE_RIGHT)
#: Eski sürümlerde "kapalı" konum değeriydi; artık ayrı `pane_visible` ayarıdır.
_LEGACY_PANE_OFF = "off"

KEY_SYMBOLS = "translate/symbols"
KEY_ALIGN = "translate/align"
KEY_PANE = "translate/pane"
KEY_PANE_VISIBLE = "translate/pane_visible"

#: (metin, simge, kısayol kimliği, ipucu); tuşlar kayıt defterinden gelir (`shortcuts.COMMANDS`).
_ALIGN_SPECS = {
    ALIGN_LEFT: ("Sola Hizala", "align-left", "view.align_left", "Metni sola hizala (yalnızca görünüm)"),
    ALIGN_CENTER: ("Ortaya Hizala", "align-center", "view.align_center", "Metni ortala (yalnızca görünüm)"),
    ALIGN_RIGHT: ("Sağa Hizala", "align-right", "view.align_right", "Metni sağa hizala (yalnızca görünüm)"),
}
_PANE_SPECS = {
    PANE_BOTTOM: ("Çeviri Panelini Altta Göster", "panel-bottom", "view.pane_bottom", "Çeviri panelini altta aç/kapat"),
    PANE_RIGHT: ("Çeviri Panelini Sağda Göster", "panel-right", "view.pane_right", "Çeviri panelini sağda aç/kapat"),
}
_PANE_TOGGLE_TIP = "Çeviri panelini aç/kapat"


class ViewActions(QObject):
    symbols_changed = Signal(bool)
    align_changed = Signal(str)
    pane_changed = Signal(str)
    pane_visible_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None, shortcuts: ShortcutRegistry | None = None) -> None:
        super().__init__(parent)
        #: Tuşların tek kaynağı; verilmezse eylemler varsayılan tuşlarla çalışır (ana pencere kendi kaydını verir).
        self.shortcuts = shortcuts if shortcuts is not None else ShortcutRegistry(self)
        self._settings: QSettings | None = None
        self._pane_room = True
        self._align = ALIGN_LEFT
        self._pane = PANE_BOTTOM
        self._pane_visible = True

        self.symbols = QAction("Sembolleri Göster/Gizle", self)
        self.symbols.setCheckable(True)
        self.shortcuts.bind("view.symbols", self.symbols, tip="Boşluk, satır sonu ve sekmeleri göster/gizle")
        bind_icon(self.symbols, "pilcrow")
        self.symbols.toggled.connect(self._on_symbols)

        group = QActionGroup(self)
        group.setExclusive(True)
        self.align_actions: dict[str, QAction] = {}
        for key, (text, icon_name, command, tip) in _ALIGN_SPECS.items():
            action = QAction(text, self)
            action.setCheckable(True)
            self.shortcuts.bind(command, action, tip=tip)
            bind_icon(action, icon_name)
            group.addAction(action)
            action.triggered.connect(lambda _checked=False, k=key: self._on_align(k))
            self.align_actions[key] = action
        self.align_actions[ALIGN_LEFT].setChecked(True)

        self.pane_toggle = QAction("Çeviri Paneli", self)
        self.pane_toggle.setCheckable(True)
        self.pane_toggle.setChecked(True)
        self.shortcuts.bind("view.pane", self.pane_toggle)
        self._refresh_pane_tip()
        self.shortcuts.changed.connect(self._shortcut_changed)
        bind_icon(self.pane_toggle, "panel-bottom")
        self.pane_toggle.toggled.connect(self._on_pane_visible)

        pane_group = QActionGroup(self)
        pane_group.setExclusive(True)
        self.pane_actions: dict[str, QAction] = {}
        for key, (text, icon_name, command, tip) in _PANE_SPECS.items():
            action = QAction(text, self)
            action.setCheckable(True)
            self.shortcuts.bind(command, action, tip=tip)
            bind_icon(action, icon_name)
            pane_group.addAction(action)
            action.triggered.connect(lambda _checked=False, k=key: self._on_pane(k))
            self.pane_actions[key] = action
        self.pane_actions[PANE_BOTTOM].setChecked(True)

    # --- durum -------------------------------------------------------------------------

    @property
    def symbols_on(self) -> bool:
        return self.symbols.isChecked()

    @property
    def align(self) -> str:
        return self._align

    @property
    def pane(self) -> str:
        """Panelin konumu (`PANE_BOTTOM` ya da `PANE_RIGHT`); panel kapalıyken de seçili konumdur."""
        return self._pane

    @property
    def pane_visible(self) -> bool:
        return self._pane_visible

    def set_pane_visible(self, visible: bool) -> None:
        """Paneli açar/kapatır (kısayol ve menüyle aynı yol: durum kaydedilir, sinyal yayılır)."""
        self.pane_toggle.setChecked(visible)

    def set_pane_room(self, room: bool) -> None:
        """Panele yer yoksa ipucu bunu söyler (panel gizlenir, seçim değişmez)."""
        self._pane_room = room
        self._refresh_pane_tip()

    def _refresh_pane_tip(self) -> None:
        key = self.shortcuts.text("view.pane")
        tip = f"{_PANE_TOGGLE_TIP} ({key})" if key else _PANE_TOGGLE_TIP
        self.pane_toggle.setToolTip(tip if self._pane_room else f"{tip}. Pencere küçük olduğu için panele yer yok.")

    def _shortcut_changed(self, command_id: str) -> None:
        if command_id == "view.pane":
            self._refresh_pane_tip()

    # --- kullanıcı eylemleri -------------------------------------------------------------

    def _save(self, key: str, value: str) -> None:
        if self._settings is not None:
            self._settings.setValue(key, value)

    def _on_symbols(self, checked: bool) -> None:
        self._save(KEY_SYMBOLS, "1" if checked else "0")
        self.symbols_changed.emit(checked)

    def _on_align(self, key: str) -> None:
        if key == self._align:
            return
        self._align = key
        self._save(KEY_ALIGN, key)
        self.align_changed.emit(key)

    def _on_pane(self, key: str) -> None:
        """Konum seçimi paneli de açar."""
        self._set_pane(key)
        self._save(KEY_PANE, key)
        self.pane_changed.emit(key)
        self.set_pane_visible(True)

    def _on_pane_visible(self, visible: bool) -> None:
        self._pane_visible = visible
        self._save(KEY_PANE_VISIBLE, "1" if visible else "0")
        self.pane_visible_changed.emit(visible)

    def _set_pane(self, pane: str) -> None:
        self._pane = pane
        for key, action in self.pane_actions.items():
            action.blockSignals(True)
            action.setChecked(key == pane)
            action.blockSignals(False)

    # --- ayarlar -------------------------------------------------------------------------

    def load(self, settings: QSettings) -> None:
        """Kayıtlı durumu eylemlere yükler (sinyal yaymadan); bozuk değerler varsayılana döner."""
        raw_symbols = str(settings.value(KEY_SYMBOLS, "0"))
        if raw_symbols not in ("0", "1"):
            log.warning("Sembol ayarı geçersiz (%r); kapalı kullanılıyor", raw_symbols)
        raw_align = str(settings.value(KEY_ALIGN, ALIGN_LEFT))
        if raw_align not in ALIGNMENTS:
            log.warning("Hiza ayarı geçersiz (%r); sola hizalı kullanılıyor", raw_align)
            raw_align = ALIGN_LEFT
        raw_pane = str(settings.value(KEY_PANE, PANE_BOTTOM))
        raw_visible = str(settings.value(KEY_PANE_VISIBLE, "0" if raw_pane == _LEGACY_PANE_OFF else "1"))
        if raw_pane == _LEGACY_PANE_OFF:
            raw_pane = PANE_BOTTOM
        if raw_pane not in PANES:
            log.warning("Panel ayarı geçersiz (%r); altta kullanılıyor", raw_pane)
            raw_pane = PANE_BOTTOM
        if raw_visible not in ("0", "1"):
            log.warning("Panel açık/kapalı ayarı geçersiz (%r); açık kullanılıyor", raw_visible)
            raw_visible = "1"
        self.symbols.blockSignals(True)
        self.symbols.setChecked(raw_symbols == "1")
        self.symbols.blockSignals(False)
        self._align = raw_align
        for key, action in self.align_actions.items():
            action.blockSignals(True)
            action.setChecked(key == raw_align)
            action.blockSignals(False)
        self._set_pane(raw_pane)
        self._pane_visible = raw_visible == "1"
        self.pane_toggle.blockSignals(True)
        self.pane_toggle.setChecked(self._pane_visible)
        self.pane_toggle.blockSignals(False)

    def bind_settings(self, settings: QSettings) -> None:
        """Ayarları yükler ve bundan sonraki her değişikliği yazar."""
        self.load(settings)
        self._settings = settings
