"""Durum süzgeci şeridi: tek seçimli simge düğmeleri (Tümü, durumlar, sorunlu satırlar, son işte değişenler).

Seçili düğmeye yeniden basmak seçimi kaldırır ("Tümü"ne döner).
Şerit iş mantığı içermez: seçenekleri çağıran verir, seçilen değeri `changed` ile bildirir. Düğmeler
Sorunlar panosundaki çiplerle aynı biçemi (`role="chip"`) kullanır; seçili olan vurgulanır. Simgeler
`bind_icon` ile bağlanır, tema değişince yenilenir.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QToolButton, QWidget

from nxceviri.gui.icons import bind_icon

_ICON_SIZE = 16
_VALUE = "deger"  # düğmenin seçenek değerini taşıyan özellik adı


@dataclass(frozen=True)
class FilterOption:
    """Şeritteki bir düğme: süzgeç değeri, simge (ad ve isteğe bağlı tema rengi), erişilebilir ad, ipucu, kısa yazı."""

    value: str
    icon: str
    tone: str | None
    label: str
    tip: str
    text: str = ""


class _ChipButton(QToolButton):
    """Boşluk tuşunun yanında Enter ile de seçilebilen düğme."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            return
        super().keyPressEvent(event)


class StatusFilterBar(QWidget):
    """Tek seçimli simge düğmeleri şeridi; ilk seçenek (değeri boş) "Tümü"dür."""

    changed = Signal(str)
    #: "Tümü" düğmesine her basış (zaten seçiliyken de): sayfa bütün süzgeçleri kaldırır.
    all_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked.connect(self._clicked)
        self._buttons: dict[str, QToolButton] = {}
        self._options: list[FilterOption] = []
        self._current = ""

    def set_options(self, options: list[FilterOption]) -> None:
        """Düğmeleri kurar; seçili değer korunur (kalkmışsa "Tümü"ne düşer). Sinyal göndermez.

        Yalnızca yazılar değiştiyse düğmeler yeniden kurulmaz (klavye odağı kaybolmasın).
        """
        if [replace(o, text="", tip="") for o in options] == [replace(o, text="", tip="") for o in self._options]:
            for option in options:
                self.set_text(option.value, option.text)
                self.set_tip(option.value, option.tip)
            self._options = list(options)
            return
        self._options = list(options)
        for button in self._buttons.values():
            self._group.removeButton(button)
            self._layout.removeWidget(button)
            button.setParent(None)  # hemen çocuk listesinden çıkar; silme olay döngüsünde olur
            button.deleteLater()
        self._buttons = {}
        for option in options:
            button = _ChipButton()
            button.setCheckable(True)
            button.setProperty("role", "chip")
            button.setProperty(_VALUE, option.value)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
            button.setToolTip(option.tip)
            button.setAccessibleName(option.label)
            bind_icon(button, option.icon, _ICON_SIZE, option.tone)
            self._set_button_text(button, option.text)
            self._group.addButton(button)
            self._layout.addWidget(button)
            self._buttons[option.value] = button
        if self._current not in self._buttons:
            self._current = ""
        selected = self._buttons.get(self._current)
        if selected is not None:
            selected.setChecked(True)

    def values(self) -> list[str]:
        """Düğmelerin süzgeç değerleri, soldan sağa."""
        return list(self._buttons)

    def current(self) -> str:
        return self._current

    def set_current(self, value: str) -> None:
        """Değeri seçer (yoksa "Tümü"); seçim değiştiyse `changed` gönderir."""
        if value not in self._buttons:
            value = ""
        if value == self._current:
            return
        self._current = value
        button = self._buttons.get(value)
        if button is not None:
            button.setChecked(True)
        self.changed.emit(value)

    def set_text(self, value: str, text: str) -> None:
        """Düğmenin simge yanındaki kısa yazısını (sayı) değiştirir; boşsa yalnızca simge görünür."""
        button = self._buttons.get(value)
        if button is not None:
            self._set_button_text(button, text)

    def set_tip(self, value: str, tip: str) -> None:
        button = self._buttons.get(value)
        if button is not None:
            button.setToolTip(tip)

    def set_marked(self, value: str, marked: bool) -> None:
        """Düğmeyi "eksik gösteriyorum" biçiminde (kesikli çerçeve, vurgu rengi) işaretler ya da işareti kaldırır."""
        button = self._buttons.get(value)
        if button is not None and button.property("marked") != marked:
            button.setProperty("marked", marked)
            style = button.style()
            style.unpolish(button)
            style.polish(button)

    @staticmethod
    def _set_button_text(button: QToolButton, text: str) -> None:
        button.setText(text)
        button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text else Qt.ToolButtonStyle.ToolButtonIconOnly
        )

    def _clicked(self, button: object) -> None:
        assert isinstance(button, QToolButton)
        value = button.property(_VALUE)
        if value != "" and value == self._current:
            # Seçili düğmeye yeniden basmak süzgeci iptal eder: "Tümü"ne dönülür (öteki süzgeçlere dokunulmaz).
            self._current = ""
            all_button = self._buttons.get("")
            if all_button is not None:
                all_button.setChecked(True)
            self.changed.emit("")
            return
        if value != self._current:
            self._current = value
            self.changed.emit(value)
        if value == "":
            self.all_clicked.emit()
