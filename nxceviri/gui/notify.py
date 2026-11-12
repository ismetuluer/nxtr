"""Bildirim merkezi: bir iş bitince, durunca ya da hata olunca kullanıcıya tek yoldan haber verilir.

Her bildirim pencerenin sağ altında kısa bir **kart** olarak görünür ve **geçmişe** yazılır (durum çubuğundaki zil).
Kullanıcı uygulamaya bakmıyorsa (pencere etkin değil ya da iş uzun sürdü) bildirim **gürültülüdür**: Windows bildirimi
(sistem tepsisi), ses ve görev çubuğunda yanıp sönme. Üç kanal da Ayarlar → Bildirimler'den kapatılabilir; kart ve
geçmiş her zaman vardır. Kart kısa ve sadedir: tek satır başlık, en çok iki satır metin ve bağlama göre düğmeler;
teknik ayrıntı karta değil ilgili pencereye konur.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from PySide6.QtCore import QEvent, QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.gui.icons import bind_icon
from nxceviri.gui.mascot import MOOD_DONE, MOOD_ERROR, MascotWidget, mascot_enabled
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import button

log = logging.getLogger(__name__)

LEVEL_SUCCESS = "success"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"
LEVEL_INFO = "info"

KEY_SOUND = "notify/sound"
KEY_SYSTEM = "notify/system"
KEY_FLASH = "notify/flash"
KEY_CARD_SECONDS = "notify/card_seconds"

#: Geçmişte tutulan en çok bildirim.
MAX_HISTORY = 50
#: Aynı anda görünen en çok kart (eskiler kapanır; geçmişte kalır).
MAX_CARDS = 4
#: Kartın genişliği (piksel).
CARD_WIDTH = 380
#: Kartların kendiliğinden kapanma süresi (saniye); 0 ise kapanmaz. Ayarlar → Bildirimler'den değişir.
DEFAULT_CARD_SECONDS = 8
#: Bu süreden uzun süren iş, pencere önde olsa da gürültülü bildirilir (kullanıcı başka işe dönmüş olabilir).
LONG_TASK_S = 2.0

_ICONS = {LEVEL_SUCCESS: "circle-check", LEVEL_WARNING: "triangle-alert", LEVEL_ERROR: "circle-x", LEVEL_INFO: "info"}
#: Kartta maskotun hâli (bilgi kartında simge kalır).
_MOODS = {LEVEL_SUCCESS: MOOD_DONE, LEVEL_WARNING: MOOD_ERROR, LEVEL_ERROR: MOOD_ERROR}
_TONES = {LEVEL_SUCCESS: "success", LEVEL_WARNING: "warning", LEVEL_ERROR: "danger", LEVEL_INFO: "accent"}
#: Kartın metni en çok bu kadar karakter; fazlası "…" ile kesilir (tamamı geçmişte, ipucunda ve "Ayrıntılar"da).
NOTICE_DETAIL_CHARS = 180
_CARD_TEXT_CHARS = NOTICE_DETAIL_CHARS


@dataclass(frozen=True)
class NoticeAction:
    label: str
    callback: Callable[[], object]


@dataclass(frozen=True)
class Notice:
    level: str
    title: str
    text: str = ""
    actions: tuple[NoticeAction, ...] = ()
    when: datetime = field(default_factory=datetime.now)


class Tray(Protocol):
    def show_message(self, title: str, text: str, level: str) -> None: ...


_TRAY_ICONS = {
    LEVEL_ERROR: QSystemTrayIcon.MessageIcon.Critical,
    LEVEL_WARNING: QSystemTrayIcon.MessageIcon.Warning,
}


class SystemTray:
    """Windows bildirimi: sistem tepsisi simgesi ilk bildirimde kurulur; bildirime tıklayınca pencere öne gelir."""

    def __init__(self, window: QWidget) -> None:
        self._window = window
        self._icon: QSystemTrayIcon | None = None

    def show_message(self, title: str, text: str, level: str) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if self._icon is None:
            self._icon = QSystemTrayIcon(self._window.windowIcon(), self._window)
            self._icon.setToolTip(self._window.windowTitle() or "NXTR")
            self._icon.messageClicked.connect(self._raise_window)
            self._icon.activated.connect(lambda _reason: self._raise_window())
            self._icon.show()
        icon_type = _TRAY_ICONS.get(level, QSystemTrayIcon.MessageIcon.Information)
        self._icon.showMessage(title, text or title, icon_type, 10000)

    def _raise_window(self) -> None:
        window = self._window
        if window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()


def system_sound(level: str) -> None:
    """Düzeye göre Windows sesi (başarı, uyarı, hata ayrı); başka sistemlerde zil."""
    if sys.platform == "win32":
        import winsound  # noqa: PLC0415 - yalnızca Windows'ta var

        kinds = {LEVEL_ERROR: winsound.MB_ICONHAND, LEVEL_WARNING: winsound.MB_ICONEXCLAMATION}
        try:
            winsound.MessageBeep(kinds.get(level, winsound.MB_OK))
        except RuntimeError as exc:  # ses aygıtı yoksa
            log.info("Bildirim sesi çalınamadı: %s", exc)
    else:
        QApplication.beep()


_TITLE_RE = re.compile(r"(.{3,70}?)[.:!?](?:\s+|$)")


def split_notice(text: str) -> tuple[str, str]:
    """Uzun bir mesajı kart için kısa başlık ve kalan metne böler ("Bağlanılamadı. Ollama'yı açın." → iki parça)."""
    text = text.strip()
    first, _, after = text.partition("\n")
    m = _TITLE_RE.match(first)
    if m is None:
        if len(first) <= 70:
            return first, after.strip()
        return _short(first)[:70].rstrip("…") + "…", text
    rest = (first[m.end() :] + "\n" + after).strip()
    return m.group(1).strip(), rest


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _CARD_TEXT_CHARS else text[: _CARD_TEXT_CHARS - 1].rstrip() + "…"


class NoticeCard(QFrame):
    closed = Signal()

    def __init__(self, notice: Notice, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.notice = notice
        self.setObjectName("noticeCard")
        tokens = current_tokens()
        tone = tokens[_TONES[notice.level]]
        self.setStyleSheet(
            f"QFrame#noticeCard {{ background: {tokens['surface']}; border: 1px solid {tokens['border']};"
            f" border-left: 4px solid {tone}; border-radius: 10px; }}"
        )
        self.setFixedWidth(CARD_WIDTH)  # sabit genişlik: sarılan metnin yüksekliği doğru hesaplanır
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 8, 10)
        lay.setSpacing(10)
        self.icon_label = QLabel()
        bind_icon(self.icon_label, _ICONS[notice.level], size=20, tone=_TONES[notice.level])
        lay.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignTop)
        # Maskot açıksa simgenin yerinde: kart açılırken yüzünü kurup sevinir ya da endişelenir.
        self.mascot: MascotWidget | None = None
        mood = _MOODS.get(notice.level)
        if mood is not None and mascot_enabled():
            self.icon_label.hide()
            self.mascot = MascotWidget(30)
            lay.insertWidget(0, self.mascot, alignment=Qt.AlignmentFlag.AlignTop)
            face = self.mascot
            QTimer.singleShot(120, face, lambda: face.set_mood(mood))  # kart silinirse zamanlayıcı da düşer
        body = QVBoxLayout()
        body.setSpacing(4)
        self.title_label = QLabel(notice.title)
        self.title_label.setStyleSheet("font-weight: 600;")
        self.title_label.setWordWrap(True)
        body.addWidget(self.title_label)
        self.text_label = QLabel(_short(notice.text))
        self.text_label.setTextFormat(Qt.TextFormat.PlainText)
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet(f"color: {tokens['muted']};")
        self.text_label.setVisible(bool(notice.text))
        if notice.text and _short(notice.text) != notice.text:
            self.text_label.setToolTip(notice.text)
        body.addWidget(self.text_label)
        self.action_buttons: list[QPushButton] = []
        if notice.actions:
            row = QHBoxLayout()
            row.setSpacing(6)
            for i, action in enumerate(notice.actions):
                b = button(action.label, "primary" if i == 0 else "")
                b.clicked.connect(lambda _c=False, a=action: self._run(a))
                row.addWidget(b)
                self.action_buttons.append(b)
            row.addStretch(1)
            body.addLayout(row)
        lay.addLayout(body, 1)
        self.close_button = QToolButton()
        self.close_button.setAutoRaise(True)
        self.close_button.setToolTip("Kapat")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        bind_icon(self.close_button, "x", size=14)
        self.close_button.clicked.connect(self.dismiss)
        lay.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)
        self._hide_ms = 0
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.dismiss)

    def auto_hide(self, ms: int) -> None:
        """Kart `ms` milisaniye sonra kendiliğinden kapanır (0: kapanmaz). Fare kartın üstündeyken sayım durur."""
        self._hide_ms = ms
        if ms > 0 and not self.underMouse():
            self._hide_timer.start(ms)
        else:
            self._hide_timer.stop()

    def enterEvent(self, event: QEnterEvent) -> None:
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if self._hide_ms > 0:
            self._hide_timer.start(self._hide_ms)
        super().leaveEvent(event)

    def _run(self, action: NoticeAction) -> None:
        self.dismiss()
        action.callback()

    def dismiss(self) -> None:
        self.hide()
        self.closed.emit()
        self.deleteLater()


class NoticeStack(QWidget):
    """Pencerenin sağ altında üst üste duran kartlar; pencere boyutu değişince yerinde kalır."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._window = window
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self._cards: list[NoticeCard] = []
        window.installEventFilter(self)
        self.hide()

    def cards(self) -> list[NoticeCard]:
        return list(self._cards)

    def add(self, card: NoticeCard) -> None:
        card.setParent(self)
        card.closed.connect(lambda c=card: self._remove(c))
        self._cards.append(card)
        self._lay.addWidget(card)
        while len(self._cards) > MAX_CARDS:
            self._cards[0].dismiss()
        self.show()
        self.raise_()
        self._place()

    def _remove(self, card: NoticeCard) -> None:
        if card in self._cards:
            self._cards.remove(card)
            self._lay.removeWidget(card)
        if not self._cards:
            self.hide()
        else:
            self._place()

    def _place(self) -> None:
        # Sarılan etiketler yüksekliği genişliğe göre belirler; kartların gerçek toplam yüksekliği buradan.
        height = sum(
            c.heightForWidth(CARD_WIDTH) if c.hasHeightForWidth() else c.sizeHint().height() for c in self._cards
        )
        height += self._lay.spacing() * max(len(self._cards) - 1, 0)
        for card in self._cards:
            card.setFixedHeight(
                card.heightForWidth(CARD_WIDTH) if card.hasHeightForWidth() else card.sizeHint().height()
            )
        self.resize(CARD_WIDTH, height)
        margin = 18
        bottom = self._window.height() - margin
        status = getattr(self._window, "statusBar", None)
        if callable(status):
            bar = status()
            if bar is not None and bar.isVisible():
                bottom -= bar.height()
        self.move(self._window.width() - self.width() - margin, max(0, bottom - self.height()))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._window and event.type() == QEvent.Type.Resize and self._cards:
            self._place()
        return False


class NotificationCenter(QObject):
    #: Yeni bildirim (geçmiş düğmesi sayacını günceller).
    posted = Signal(object)

    def __init__(
        self,
        window: QWidget,
        settings: QSettings | None = None,
        *,
        tray: Tray | None = None,
        sound: Callable[[str], None] | None = None,
        alert: Callable[[QWidget], None] | None = None,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._settings = settings
        self._tray: Tray = tray if tray is not None else SystemTray(window)
        self._sound = sound if sound is not None else system_sound
        self._alert = alert if alert is not None else (lambda w: QApplication.alert(w, 0))
        self.stack = NoticeStack(window)
        self.history: list[Notice] = []
        self.unread = 0

    def card_ms(self) -> int:
        """Kartın kapanma süresi (ms); 0 ise kart kendiliğinden kapanmaz."""
        raw = DEFAULT_CARD_SECONDS if self._settings is None else self._settings.value(KEY_CARD_SECONDS)
        try:
            seconds = float(raw) if raw is not None else DEFAULT_CARD_SECONDS
        except (TypeError, ValueError):
            seconds = DEFAULT_CARD_SECONDS
        return max(0, round(seconds * 1000))

    def show_card(self, notice: Notice) -> None:
        """Bildirimi kart olarak gösterir; süre dolunca kart kapanır, bildirim geçmişte kalır."""
        card = NoticeCard(notice)
        self.stack.add(card)
        card.auto_hide(self.card_ms())

    def enabled(self, key: str) -> bool:
        if self._settings is None:
            return True
        return str(self._settings.value(key, "1")) != "0"

    def notify(
        self,
        level: str,
        title: str,
        text: str = "",
        actions: Sequence[NoticeAction] = (),
        *,
        loud: bool | None = None,
    ) -> Notice:
        """Bildirim gösterir. `loud` verilmezse pencere etkin değilken gürültülüdür (Windows bildirimi, ses, uyarı)."""
        notice = Notice(level, title, text, tuple(actions))
        self.history.insert(0, notice)
        del self.history[MAX_HISTORY:]
        self.unread = min(self.unread + 1, MAX_HISTORY)
        self.show_card(notice)
        if loud is None:
            loud = not self._window.isActiveWindow()
        if loud:
            if self.enabled(KEY_SYSTEM):
                self._tray.show_message(title, _short(text), level)
            if self.enabled(KEY_SOUND):
                self._sound(level)
            if self.enabled(KEY_FLASH) and not self._window.isActiveWindow():
                self._alert(self._window)
        log.info("Bildirim (%s): %s %s", level, title, text)
        self.posted.emit(notice)
        return notice

    def mark_read(self) -> None:
        self.unread = 0


class HistoryButton(QToolButton):
    """Durum çubuğundaki zil: okunmamış bildirim sayısı; tıklayınca son bildirimler (seçilen yeniden kart olur)."""

    def __init__(self, center: NotificationCenter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._center = center
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bind_icon(self, "bell", size=14, tone="muted")
        self.menu_widget = QMenu(self)
        self.menu_widget.setToolTipsVisible(True)
        self.menu_widget.aboutToShow.connect(self._fill)
        self.setMenu(self.menu_widget)
        center.posted.connect(lambda _n: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        n = self._center.unread
        self.setText(str(n) if n else "")
        self.setToolTip(f"Bildirimler: {n} yeni" if n else "Bildirimler")

    def _fill(self) -> None:
        menu = self.menu_widget
        menu.clear()
        history = self._center.history
        if not history:
            empty = menu.addAction("Henüz bildirim yok")
            empty.setEnabled(False)
        for notice in history[: MAX_CARDS * 5]:
            action = menu.addAction(f"{notice.when:%H:%M}  {notice.title}")
            bind_icon(action, _ICONS[notice.level], size=14, tone=_TONES[notice.level])
            if notice.text:
                action.setToolTip(notice.text)
            action.triggered.connect(lambda _c=False, n=notice: self._center.show_card(n))
        if history:
            menu.addSeparator()
            menu.addAction("Geçmişi Temizle").triggered.connect(self._clear)
        self._center.mark_read()
        self.refresh()

    def _clear(self) -> None:
        self._center.history.clear()
        self._center.mark_read()
        self.refresh()
