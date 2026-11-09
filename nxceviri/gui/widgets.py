"""Ortak arayüz bileşenleri: kart, durum rozeti, uyarı bandı, sürükle-bırak alanı, durum sayfaları."""

from __future__ import annotations

import html
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.gui.icons import DEFAULT_SIZE, bind_icon, icon
from nxceviri.gui.mascot import MOOD_IDLE, MOOD_WORKING, MascotWidget
from nxceviri.gui.theme import current_tokens

#: Sayfa başlığındaki simgenin piksel boyutu.
TITLE_ICON_SIZE = 22

#: Ipucu balonunun piksel genişliği: uzun açıklamalar bu genişlikte kaydırılır.
TIP_WIDTH = 380


def repolish(w: QWidget) -> None:
    """Dinamik özellik değişince QSS'in yeniden uygulanmasını sağlar."""
    w.style().unpolish(w)
    w.style().polish(w)


def tip_html(text: str) -> str:
    """Düz metni, sabit genişlikte sözcük kaydıran bir ipucu balonu metnine çevirir."""
    body = html.escape(text).replace("\n", "<br>")
    return f'<table width="{TIP_WIDTH}"><tr><td>{body}</td></tr></table>'


def title_row(title: str, info: str = "", role: str = "pageTitle", icon: str | None = None) -> QWidget:
    """Başlık (solda isteğe bağlı simge). `info` boş değilse başlığın üstüne gelince ipucu olarak görünür."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    if icon:
        mark = QLabel()
        mark.setObjectName("titleIcon")
        bind_icon(mark, icon, size=TITLE_ICON_SIZE if role == "pageTitle" else DEFAULT_SIZE)
        row.addWidget(mark, alignment=Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(label(title, role, tip=info))
    row.addStretch(1)
    return box


def label(text: str = "", role: str | None = None, wrap: bool = False, tip: str = "") -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    if tip:
        lbl.setToolTip(tip_html(tip))
    lbl.setWordWrap(wrap)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


def button(text: str, kind: str | None = None, icon: str | None = None) -> QPushButton:
    btn = QPushButton(text)
    if kind:
        btn.setProperty("kind", kind)
    if icon:
        bind_icon(btn, icon)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def format_int(n: int) -> str:
    """Türkçe binlik ayırıcıyla tam sayı (ör. 2.373)."""
    return f"{n:,}".replace(",", ".")


def format_size(n: int) -> str:
    value = float(n)
    for unit in ("bayt", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            text = f"{value:,.0f}" if unit == "bayt" else f"{value:,.1f}"
            return text.replace(",", "X").replace(".", ",").replace("X", ".") + f" {unit}"
        value /= 1024
    return f"{n} bayt"


class Card(QFrame):
    """Başlıklı kart. `subtitle` kısa görünür açıklama, `hint` başlığın üstüne gelince görünen uzun ipucudur."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None, *, hint: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 18)
        outer.setSpacing(10)
        head_box = QWidget()
        head = QHBoxLayout(head_box)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        self.title = label(title, "cardTitle", tip=hint)
        head.addWidget(self.title)
        head.addStretch(1)
        self.header_right = QHBoxLayout()
        head.addLayout(self.header_right)
        head_box.setVisible(bool(title))  # başlıksız kart: başlık satırı yer kaplamaz
        outer.addWidget(head_box)
        if subtitle:
            outer.addWidget(label(subtitle, "muted", wrap=True))
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body)


class Badge(QLabel):
    def __init__(self, text: str = "", state: str = "neutral") -> None:
        super().__init__(text)
        self.setProperty("role", "badge")
        self.set_state(state, text)

    def set_state(self, state: str, text: str) -> None:
        self.setText(text)
        self.setProperty("state", state)
        repolish(self)


class Banner(QFrame):
    """Kart içinde gösterilen uyarı/hata bandı. Metin boşsa gizlenir; `closable` ise kapatılabilir.

    `show_message(..., action=...)` bir eylem bağlantısı ekler; tıklanınca `action_clicked` yayılır.
    """

    action_clicked = Signal()

    def __init__(self, closable: bool = False) -> None:
        super().__init__()
        self.setObjectName("banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 8, 9)
        self.text = label(wrap=True)
        self.text.setTextFormat(Qt.TextFormat.PlainText)  # model önerisindeki "<div>" yazı olarak görünsün
        lay.addWidget(self.text, 1)
        if closable:
            close = QToolButton()
            close.setText("✕")
            close.setAutoRaise(True)
            close.setToolTip("Kapat")
            close.setCursor(Qt.CursorShape.PointingHandCursor)
            close.clicked.connect(self.hide)
            lay.addWidget(close, alignment=Qt.AlignmentFlag.AlignTop)
        self.action_button = QToolButton()
        self.action_button.setProperty("role", "link")
        self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_button.clicked.connect(self.action_clicked)
        self.action_button.hide()
        lay.insertWidget(1, self.action_button, alignment=Qt.AlignmentFlag.AlignTop)
        self.hide()

    def show_message(self, state: str, text: str, action: str = "") -> None:
        if not text:
            self.hide()
            return
        self.setProperty("state", state)
        self.text.setText(text)
        self.action_button.setText(action)
        self.action_button.setVisible(bool(action))
        repolish(self)
        self.show()


#: Durum çipinin simgesi (durum → simge adı); listede olmayan durum simgesizdir.
_CHIP_ICONS = {"danger": "circle-alert", "warning": "triangle-alert", "success": "circle-check"}
#: Çip ayrıntı penceresinin en büyük ölçüleri (piksel).
CHIP_POPUP_WIDTH = 420
CHIP_POPUP_MAX_HEIGHT = 320


class StatusChip(QToolButton):
    """Kısa durum ("2 uyarı"); tıklanınca ayrıntılar küçük bir açılır pencerede okunur."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "statusChip")
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._details: tuple[str, ...] = ()
        self.popup: QFrame | None = None
        self.clicked.connect(self._open_popup)
        self.hide()

    def show_status(self, state: str, text: str, details: Sequence[str] = ()) -> None:
        """`state` ya da `text` boşsa çip gizlenir."""
        self._details = tuple(details)
        if not state or not text:
            self.hide()
            return
        self.setText(text)
        self.setProperty("state", state)
        self.setToolTip(tip_html("\n".join(self._details)) if self._details else "")
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._details else Qt.CursorShape.ArrowCursor)
        self._apply_icon()
        repolish(self)
        self.show()

    def details(self) -> tuple[str, ...]:
        return self._details

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange and self.property("state"):
            self._apply_icon()  # tema değişti: simge yeni renkle

    def _apply_icon(self) -> None:
        state = str(self.property("state") or "")
        name = _CHIP_ICONS.get(state)
        tokens = current_tokens()
        self.setIcon(icon(name, tokens.get(state, tokens["text"])) if name else QIcon())

    def _open_popup(self) -> None:
        if not self._details:
            return
        if self.popup is not None:
            self.popup.deleteLater()
        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setObjectName("chipPopup")
        outer = QVBoxLayout(popup)
        outer.setContentsMargins(4, 4, 4, 4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        for line in self._details:
            item = label(line, wrap=True)
            item.setTextFormat(Qt.TextFormat.PlainText)
            item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lay.addWidget(item)
        lay.addStretch(1)  # fazladan yükseklik satırların arasına değil sona gider
        scroll.setWidget(body)
        outer.addWidget(scroll)
        popup.setFixedWidth(CHIP_POPUP_WIDTH)
        popup.ensurePolished()  # tema yazı tipi ölçüye girsin
        width = CHIP_POPUP_WIDTH - 8 - scroll.verticalScrollBar().sizeHint().width()
        body.setFixedWidth(width)
        # Kaydırılan satırların yüksekliği genişliğe bağlıdır; boyut ipucu bunu hesaba katmaz.
        popup.setFixedHeight(min(lay.totalHeightForWidth(width) + 10, CHIP_POPUP_MAX_HEIGHT))
        point = self.mapToGlobal(self.rect().bottomLeft())
        screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        popup.move(
            max(area.left(), min(point.x(), area.right() - popup.width())),
            max(area.top(), min(point.y() + 4, area.bottom() - popup.height())),
        )
        self.popup = popup
        popup.show()


class ActionBar(QWidget):
    """Sekme ya da bölüm eylem satırı: solda kısa durum metni, sağda eylemler."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(8)
        self.status = label("", "muted")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._row.addWidget(self.status, 1)

    def add_action(self, widget: QWidget) -> None:
        self._row.addWidget(widget)


class PageHeader(QWidget):
    """Sayfa başlığı: solda simge ve başlık, yanında durum çipi, sağda eylemler (ana eylem en sağda)."""

    def __init__(self, title: str, icon_name: str, info: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        mark = QLabel()
        mark.setObjectName("titleIcon")
        bind_icon(mark, icon_name, size=TITLE_ICON_SIZE)
        row.addWidget(mark, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.title = label(title, "pageTitle", tip=info)
        # Pencere darsa başlık kısalır; eylem düğmeleri her zaman görünür kalır.
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.title.setMinimumWidth(40)
        row.addWidget(self.title, 1)
        self.chip = StatusChip()
        row.addWidget(self.chip)
        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        row.addLayout(self._actions)

    def add_action(self, widget: QWidget) -> None:
        self._actions.addWidget(widget)


class DropZone(QFrame):
    """NSP/NSZ dosyalarının sürüklenip bırakılacağı alan."""

    files_dropped = Signal(list)

    def __init__(self, suffixes: tuple[str, ...], text: str) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self._suffixes = suffixes
        self.setMinimumHeight(110)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        # Maskot: dosya üstüne sürüklenince yüzünü toplayıp bakınır.
        self.mascot = MascotWidget(56)
        lay.addWidget(self.mascot, alignment=Qt.AlignmentFlag.AlignCenter)
        self.text = label(text, "muted", wrap=True)
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.text)
        self.button = button("Dosya Ekle…")
        self.button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        lay.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(1)

    def _paths(self, event: QDragEnterEvent | QDropEvent) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]

    def _set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        repolish(self)
        self.mascot.set_mood(MOOD_WORKING if active else MOOD_IDLE)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.isEnabled() and any(p.suffix.lower() in self._suffixes for p in self._paths(event)):
            event.acceptProposedAction()
            self._set_active(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_active(False)
        paths = self._paths(event)
        if paths and self.isEnabled():
            event.acceptProposedAction()
            self.files_dropped.emit(paths)


class EmptyState(QWidget):
    """Boş durum: maskot (Ayarlar'dan kapatılabilir), başlık, kısa yönlendirme ve isteğe bağlı düğme."""

    def __init__(self, title: str, text: str, action: QPushButton | None = None, mood: str = MOOD_IDLE) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)
        self.mascot = MascotWidget(88, mood)
        lay.addWidget(self.mascot, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(4)
        self.title = label(title, "emptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = label(text, "muted", wrap=True)
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setMinimumWidth(320)
        self.text.setMaximumWidth(520)
        lay.addWidget(self.title)
        lay.addWidget(self.text, alignment=Qt.AlignmentFlag.AlignCenter)
        if action is not None:
            lay.addSpacing(6)
            lay.addWidget(action, alignment=Qt.AlignmentFlag.AlignCenter)


class ProgressPanel(QWidget):
    """Yükleniyor durumu: aşama, ilerleme çubuğu, ayrıntı ve iptal."""

    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)
        self.stage = label("", "emptyTitle")
        self.stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bar = QProgressBar()
        self.bar.setMaximumWidth(560)
        self.bar.setMinimumWidth(260)
        self.bar.setTextVisible(False)
        self.detail = label("", "muted")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setMaximumWidth(560)
        self.cancel = button("İptal")
        self.cancel.clicked.connect(self._on_cancel)
        lay.addWidget(self.stage)
        lay.addWidget(self.bar, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.detail, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.cancel, alignment=Qt.AlignmentFlag.AlignCenter)

    def start(self, stage: str) -> None:
        self.stage.setText(stage)
        self.detail.setText("Hazırlanıyor…")
        self.bar.setRange(0, 0)
        self.cancel.setEnabled(True)
        self.cancel.setText("İptal")

    def update_progress(self, done: int, total: int, message: str) -> None:
        if total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done * 1000 / total))
        else:
            self.bar.setRange(0, 0)
        metrics = self.detail.fontMetrics()
        self.detail.setText(metrics.elidedText(message, Qt.TextElideMode.ElideMiddle, self.detail.maximumWidth()))
        self.detail.setToolTip(message)

    def _on_cancel(self) -> None:
        self.cancel.setEnabled(False)
        self.cancel.setText("İptal ediliyor…")
        self.cancel_requested.emit()


class ErrorState(QWidget):
    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)
        self.title = label("İşlem tamamlanamadı", "emptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner = Banner()
        self.banner.setMinimumWidth(340)
        self.banner.setMaximumWidth(620)
        lay.addWidget(self.title)
        lay.addWidget(self.banner, alignment=Qt.AlignmentFlag.AlignCenter)

    def show_error(self, text: str) -> None:
        self.banner.show_message("danger", text)
