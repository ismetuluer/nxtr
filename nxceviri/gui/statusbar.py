"""Durum çubuğunun kalıcı bölmeleri: simge + kısa sayı ve etiket; ayrıntı ipucundadır.

Bölmeler: anahtar durumu, satır sayısı, çeviri ilerlemesi, sorunlar, sağlayıcı ve kayıt. Geçici mesajlar
(`QStatusBar.showMessage`) olduğu gibi çalışır; bölmeler sağda kalıcı bileşenlerdir ve en sağdaki bileşen
"Yeni sürüm" rozetidir. Bölmeler yalnızca anlamlı olduğunda görünür (metin aktarılmadan satır sayısı ve
ilerleme, hatalı satır yokken sorunlar, sağlayıcı seçilmeden sağlayıcı gösterilmez).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QStatusBar,
    QToolButton,
    QToolTip,
    QWidget,
)

from nxceviri.core.translate.origin import PROVIDER_NAMES
from nxceviri.core.translate.providers.catalog import spec
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.widgets import format_int, repolish

PROGRESS_WIDTH = 60
PROGRESS_HEIGHT = 4
#: Anahtar düğmesinin görünen kısa etiketi (durum ve ayrıntı erişilebilir ad ile ipucundadır).
KEYS_LABEL = "Anahtarlar"
#: Çubuğun kenar boşluğu, boyut tutamacı ve geçici mesaj alanı için pay (px; ölçülen ~70).
BAR_SLACK = 80
#: Anahtar durumu → simge rengi (tema belirteci).
_KEYS_TOKENS = {"success": "success", "danger": "danger", "neutral": "muted"}


#: Sağlayıcı türü → simge (Lucide'de marka simgesi yok: bulut = DeepL, işlemci = yerel Ollama).
def _provider_icon(provider: str) -> str:
    """Yerel hizmet (Ollama, LM Studio) işlemci, bulut hizmeti bulut simgesiyle gösterilir."""
    return "cpu" if spec(provider).local else "cloud"


class _Segment(QFrame):
    """Solunda ince ayırıcı çizgi olan durum çubuğu bölmesi."""

    #: İpucu istendi (fare bölmenin üstünde bekledi); ayrıntıyı tembel yüklemek için.
    tooltip_requested = Signal()

    def __init__(self, *children: QWidget) -> None:
        super().__init__()
        self.setProperty("segment", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(6)
        for child in children:
            lay.addWidget(child, alignment=Qt.AlignmentFlag.AlignVCenter)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            self.tooltip_requested.emit()
        return super().event(event)


def _icon_label(name: str, tone: str = "muted") -> QLabel:
    label = QLabel()
    bind_icon(label, name, size=14, tone=tone)
    return label


def _tool_button(role: str) -> QToolButton:
    button = QToolButton()
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setAutoRaise(True)
    button.setProperty("role", role)
    return button


class StatusSegments(QObject):
    """`QStatusBar`a kalıcı bölmeleri kurar ve `update` ile günceller."""

    #: Sorunlar düğmesine tıklandı (Kontrol Et adımına gidilsin).
    problems_clicked = Signal()
    #: Anahtar bölmesine tıklandı (prod.keys seçme penceresi açılsın).
    keys_clicked = Signal()
    #: Sağlayıcı bölmesinin ipucu istendi (ayrıntı arka planda yenilensin).
    provider_tip_requested = Signal()

    def __init__(self, bar: QStatusBar, update_badge: QWidget) -> None:
        super().__init__(bar)
        self._bar = bar
        self._badge = update_badge
        #: Her etiketin (görünen bileşen, kısa metin, uzun ek); çubuk darsa ek düşer.
        self._texts: dict[QLabel | QToolButton, tuple[str, str]] = {}
        self.keys_button = _tool_button("keys")
        bind_icon(self.keys_button, "key-round", size=14, tone="muted")
        self.keys_button.clicked.connect(self.keys_clicked)
        self.rows_icon = _icon_label("list")
        self.rows_label = QLabel()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(PROGRESS_WIDTH, PROGRESS_HEIGHT)
        self.progress_label = QLabel()
        self.problems_button = _tool_button("problems")
        bind_icon(self.problems_button, "triangle-alert", size=14, tone="danger")
        self.problems_button.clicked.connect(self.problems_clicked)
        self.provider_icon = _icon_label("cpu")
        self.provider_label = QLabel()
        self.schedule_icon = _icon_label("clock")
        self.schedule_label = QLabel()
        self.cursor_label = QLabel()
        self.symbols_button = QToolButton()
        self.symbols_button.setProperty("role", "viewTool")
        self.symbols_button.setAutoRaise(True)
        self.symbols_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.symbols_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_dot = QLabel()
        self.save_dot.setObjectName("saveDot")
        self.save_dot.setFixedSize(8, 8)

        self._keys = _Segment(self.keys_button)
        self._rows = _Segment(self.rows_icon, self.rows_label)
        self._progress = _Segment(self.progress, self.progress_label)
        self._problems = _Segment(self.problems_button)
        self._provider = _Segment(self.provider_icon, self.provider_label)
        self._provider.tooltip_requested.connect(self.provider_tip_requested)
        self._schedule = _Segment(self.schedule_icon, self.schedule_label)
        self._cursor = _Segment(self.cursor_label)
        self._symbols = _Segment(self.symbols_button)
        self._save = _Segment(self.save_dot)
        self._segments = (
            self._keys,
            self._rows,
            self._progress,
            self._problems,
            self._provider,
            self._schedule,
            self._cursor,
            self._symbols,
            self._save,
        )
        for segment in self._segments:
            bar.addPermanentWidget(segment)
        bar.addPermanentWidget(update_badge)
        for segment in (self._rows, self._progress, self._problems, self._provider, self._schedule, self._cursor):
            segment.hide()
        self._texts[self.keys_button] = ("", KEYS_LABEL)
        bar.installEventFilter(self)
        self._refit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._bar and event.type() == QEvent.Type.Resize:
            self._refit()
        return False

    def _set_text(self, widget: QLabel | QToolButton, short: str, suffix: str = "") -> None:
        """Etiketin kısa metnini ve (çubuk genişse eklenecek) ekini kaydeder, yerleşimi yeniden ölçer."""
        self._texts[widget] = (short, suffix)
        self._refit()

    @staticmethod
    def _segment_width(segment: _Segment) -> int:
        """Bölmenin güncel ihtiyacı; yerleşim önbelleği eski kalmasın diye önce geçersiz kılınır."""
        layout = segment.layout()
        assert layout is not None
        layout.invalidate()
        return layout.sizeHint().width()

    def _refit(self) -> None:
        """Uzun metinler çubuğa sığıyorsa hepsi görünür, sığmıyorsa tüm ekler birlikte düşer (yarım sözcük yok)."""
        for compact in (False, True):
            for widget, (short, suffix) in self._texts.items():
                widget.setMinimumWidth(0)
                widget.setText(short if compact else f"{short}{suffix}")
                widget.setMinimumWidth(widget.sizeHint().width())
            need = sum(self._segment_width(seg) for seg in self._segments if seg.isVisibleTo(self._bar.window()))
            need += self._badge.sizeHint().width() + BAR_SLACK
            if need <= self._bar.width():
                break

    def set_keys(self, state: str, text: str, tip: str) -> None:
        """Anahtar durumu: `state` "success", "danger" ya da "neutral" (simge rengi), `text` başlık, `tip` ayrıntı."""
        bind_icon(self.keys_button, "key-round", size=14, tone=_KEYS_TOKENS.get(state, "muted"))
        self.keys_button.setAccessibleName(text)
        self.keys_button.setToolTip(f"{text}\n{tip}")
        self.keys_button.setProperty("state", state)
        repolish(self.keys_button)

    def bind_symbols_action(self, action: QAction) -> None:
        """¶ düğmesi araç çubuğu ve menüyle aynı eylemi paylaşır."""
        self.symbols_button.setDefaultAction(action)

    def set_cursor(self, line: int | None, column: int | None) -> None:
        """Panelin imleç konumu ("Satır 3 · Sütun 14"); `None` verilirse bölme gizlenir."""
        visible = line is not None and column is not None
        self._cursor.setVisible(visible)
        if visible:
            self._set_text(self.cursor_label, f"Satır {line} · Sütun {column}")

    def set_schedule(self, text: str, tip: str = "") -> None:
        """Zamanlayıcı durumu ("Zamanlayıcı: sonraki Pzt 01:00"); boş metin bölmeyi gizler."""
        self._schedule.setVisible(bool(text))
        self._schedule.setToolTip(tip)
        self._set_text(self.schedule_label, text)

    def set_provider_tip(self, text: str) -> None:
        """Sağlayıcı ipucunu günceller; ipucu o sırada açıksa yerinde yenilenir."""
        self._provider.setToolTip(text)
        if QToolTip.isVisible() and self._provider.underMouse():
            QToolTip.showText(QCursor.pos(), text, self._provider)

    def update(
        self,
        *,
        rows: int,
        shown: int,
        translated: int,
        approved: int,
        errors: int,
        provider: str,
        saved: bool,
    ) -> None:
        """`shown` süzgeçten geçen satır sayısıdır; `provider` sağlayıcı kimliği ("ollama", "deepl"…) ya da boş."""
        has_rows = rows > 0
        percent = round(100 * translated / rows) if has_rows else 0
        self._rows.setVisible(has_rows)
        filtered = shown != rows
        self._set_text(
            self.rows_label, f"{format_int(shown)} / {format_int(rows)}" if filtered else format_int(rows), " satır"
        )
        self._rows.setToolTip(
            f"{format_int(rows)} satırdan {format_int(shown)} tanesi süzgeçte gösteriliyor"
            if filtered
            else f"{format_int(rows)} satır"
        )
        self._progress.setVisible(has_rows)
        self.progress.setValue(percent)
        self._set_text(self.progress_label, f"%{percent}", " çevrildi")
        self._progress.setToolTip(
            f"Çevrilen: {format_int(translated)} / {format_int(rows)}\n"
            f"Onaylı: {format_int(approved)}\nHatalı: {format_int(errors)}"
        )
        self._problems.setVisible(errors > 0)
        self._set_text(self.problems_button, format_int(errors), " hatalı")
        self.problems_button.setToolTip(
            f"{format_int(errors)} hatalı satır var (dışa aktarılmaz). Kontrol Et için tıklayın."
        )
        self._provider.setVisible(bool(provider))
        if provider:
            bind_icon(self.provider_icon, _provider_icon(provider), size=14, tone="muted")
            self._set_text(self.provider_label, PROVIDER_NAMES.get(provider, provider))
        self.save_dot.setProperty("state", "success" if saved else "warning")
        state_text = "Kaydedildi" if saved else "Kaydedilmedi"
        self._save.setToolTip(state_text)
        self.save_dot.setAccessibleName(f"Kayıt durumu: {state_text}")
        repolish(self.save_dot)
        self._refit()
