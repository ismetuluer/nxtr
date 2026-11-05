"""Çeviri sayfasının görünüm durumu: semboller, metin hizası ve düzenleme paneli konumu.

Üç durum da `QAction`dır ve **tek bir nesnede** yaşar; araç çubuğu düğmeleri, Görünüm menüsü ve durum çubuğundaki ¶
düğmesi aynı eylemleri paylaşır (biri değişince hepsi değişir). Değerler `QSettings`te saklanır; bozuk bir değer
varsayılana döner ve günlüğe uyarı yazılır.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence

from nxceviri.gui.icons import bind_icon

log = logging.getLogger(__name__)

ALIGN_LEFT = "left"
ALIGN_CENTER = "center"
ALIGN_RIGHT = "right"
ALIGNMENTS = (ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT)

PANE_OFF = "off"
PANE_BOTTOM = "bottom"
PANE_RIGHT = "right"
PANES = (PANE_OFF, PANE_BOTTOM, PANE_RIGHT)

KEY_SYMBOLS = "translate/symbols"
KEY_ALIGN = "translate/align"
KEY_PANE = "translate/pane"

_ALIGN_SPECS = {
    ALIGN_LEFT: ("Sola Hizala", "align-left", "Ctrl+L", "Metni sola hizala (yalnızca görünüm)"),
    ALIGN_CENTER: ("Ortaya Hizala", "align-center", "Ctrl+E", "Metni ortala (yalnızca görünüm)"),
    ALIGN_RIGHT: ("Sağa Hizala", "align-right", "Ctrl+R", "Metni sağa hizala (yalnızca görünüm)"),
}
_PANE_SPECS = {
    PANE_BOTTOM: ("Çeviri Panelini Altta Göster", "panel-bottom", "Ctrl+Alt+B", "Çeviri panelini altta aç/kapat"),
    PANE_RIGHT: ("Çeviri Panelini Sağda Göster", "panel-right", "Ctrl+Alt+R", "Çeviri panelini sağda aç/kapat"),
}


class ViewActions(QObject):
    symbols_changed = Signal(bool)
    align_changed = Signal(str)
    pane_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings: QSettings | None = None
        self._align = ALIGN_LEFT
        self._pane = PANE_BOTTOM

        self.symbols = QAction("Sembolleri Göster/Gizle", self)
        self.symbols.setCheckable(True)
        self.symbols.setShortcut(QKeySequence("Ctrl+Shift+8"))
        self.symbols.setToolTip("Boşluk, satır sonu ve sekmeleri göster/gizle (Ctrl+Shift+8)")
        bind_icon(self.symbols, "pilcrow")
        self.symbols.toggled.connect(self._on_symbols)

        group = QActionGroup(self)
        group.setExclusive(True)
        self.align_actions: dict[str, QAction] = {}
        for key, (text, icon_name, shortcut, tip) in _ALIGN_SPECS.items():
            action = QAction(text, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(shortcut))
            action.setToolTip(f"{tip} ({shortcut})")
            bind_icon(action, icon_name)
            group.addAction(action)
            action.triggered.connect(lambda _checked=False, k=key: self._on_align(k))
            self.align_actions[key] = action
        self.align_actions[ALIGN_LEFT].setChecked(True)

        self.pane_actions: dict[str, QAction] = {}
        for key, (text, icon_name, shortcut, tip) in _PANE_SPECS.items():
            action = QAction(text, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(shortcut))
            action.setToolTip(f"{tip} ({shortcut})")
            bind_icon(action, icon_name)
            action.triggered.connect(lambda checked=False, k=key: self._on_pane(k, checked))
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
        return self._pane

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

    def _on_pane(self, key: str, checked: bool) -> None:
        new = key if checked else PANE_OFF  # etkin olana tekrar tıklamak paneli kapatır
        self._set_pane(new)
        self._save(KEY_PANE, new)
        self.pane_changed.emit(new)

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
        if raw_pane not in PANES:
            log.warning("Panel ayarı geçersiz (%r); altta kullanılıyor", raw_pane)
            raw_pane = PANE_BOTTOM
        self.symbols.blockSignals(True)
        self.symbols.setChecked(raw_symbols == "1")
        self.symbols.blockSignals(False)
        self._align = raw_align
        for key, action in self.align_actions.items():
            action.blockSignals(True)
            action.setChecked(key == raw_align)
            action.blockSignals(False)
        self._set_pane(raw_pane)

    def bind_settings(self, settings: QSettings) -> None:
        """Ayarları yükler ve bundan sonraki her değişikliği yazar."""
        self.load(settings)
        self._settings = settings
