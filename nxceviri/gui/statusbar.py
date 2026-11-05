"""Durum çubuğunun kalıcı bölmeleri: anahtar durumu, satır sayısı, ilerleme, hatalı satırlar, sağlayıcı ve kayıt.

Geçici mesajlar (`QStatusBar.showMessage`) olduğu gibi çalışır; bölmeler sağda kalıcı bileşenlerdir ve en
sağdaki bileşen "Yeni sürüm" rozetidir. Bölmeler yalnızca anlamlı olduğunda görünür (metin aktarılmadan satır
sayısı ve ilerleme, hatalı satır yokken sorunlar, sağlayıcı seçilmeden sağlayıcı gösterilmez).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QStatusBar, QToolButton, QWidget

from nxceviri.gui.icons import bind_icon
from nxceviri.gui.widgets import format_int, repolish

PROGRESS_WIDTH = 90
PROGRESS_HEIGHT = 5


class _Segment(QFrame):
    """Solunda ince ayırıcı çizgi olan durum çubuğu bölmesi."""

    def __init__(self, *children: QWidget) -> None:
        super().__init__()
        self.setProperty("segment", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(6)
        for child in children:
            lay.addWidget(child, alignment=Qt.AlignmentFlag.AlignVCenter)


class StatusSegments(QObject):
    """`QStatusBar`a kalıcı bölmeleri kurar ve `update` ile günceller."""

    #: "N hatalı" düğmesine tıklandı (Kontrol Et adımına gidilsin).
    problems_clicked = Signal()
    #: Anahtar bölmesine tıklandı (prod.keys seçme penceresi açılsın).
    keys_clicked = Signal()

    def __init__(self, bar: QStatusBar, update_badge: QWidget) -> None:
        super().__init__(bar)
        self.keys_button = QToolButton()
        self.keys_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.keys_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.keys_button.setAutoRaise(True)
        self.keys_button.setProperty("role", "keys")
        bind_icon(self.keys_button, "key-round", size=14)
        self.keys_button.clicked.connect(self.keys_clicked)
        self.rows_label = QLabel()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(PROGRESS_WIDTH, PROGRESS_HEIGHT)
        self.progress_label = QLabel()
        self.problems_button = QToolButton()
        self.problems_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.problems_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.problems_button.setAutoRaise(True)
        self.problems_button.setProperty("role", "problems")
        bind_icon(self.problems_button, "triangle-alert", size=14)
        self.problems_button.clicked.connect(self.problems_clicked)
        self.provider_icon = QLabel()
        bind_icon(self.provider_icon, "cpu", size=14)
        self.provider_label = QLabel()
        self.cursor_label = QLabel()
        self.symbols_button = QToolButton()
        self.symbols_button.setProperty("role", "viewTool")
        self.symbols_button.setAutoRaise(True)
        self.symbols_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.symbols_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_dot = QLabel()
        self.save_dot.setObjectName("saveDot")
        self.save_dot.setFixedSize(8, 8)
        self.save_label = QLabel()

        self._keys = _Segment(self.keys_button)
        self._rows = _Segment(self.rows_label)
        self._progress = _Segment(self.progress, self.progress_label)
        self._problems = _Segment(self.problems_button)
        self._provider = _Segment(self.provider_icon, self.provider_label)
        self._cursor = _Segment(self.cursor_label)
        self._symbols = _Segment(self.symbols_button)
        self._save = _Segment(self.save_dot, self.save_label)
        for segment in (
            self._keys,
            self._rows,
            self._progress,
            self._problems,
            self._provider,
            self._cursor,
            self._symbols,
            self._save,
        ):
            bar.addPermanentWidget(segment)
        bar.addPermanentWidget(update_badge)
        for segment in (self._rows, self._progress, self._problems, self._provider, self._cursor):
            segment.hide()

    def set_keys(self, state: str, text: str, tip: str) -> None:
        """Anahtar durumu: `state` "success", "danger" ya da "neutral" (renk), `tip` ayrıntı (yol, title.keys)."""
        self.keys_button.setText(text)
        self.keys_button.setToolTip(tip)
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
            self.cursor_label.setText(f"Satır {line} · Sütun {column}")

    def update(self, rows: int, translated: int, errors: int, provider: str, saved: bool) -> None:
        has_rows = rows > 0
        percent = round(100 * translated / rows) if has_rows else 0
        self._rows.setVisible(has_rows)
        self.rows_label.setText(f"{format_int(rows)} satır")
        self._progress.setVisible(has_rows)
        self.progress.setValue(percent)
        self.progress_label.setText(f"%{percent} çevrildi")
        self._problems.setVisible(errors > 0)
        self.problems_button.setText(f"{format_int(errors)} hatalı")
        self._provider.setVisible(bool(provider))
        self.provider_label.setText(provider)
        self.save_label.setText("Kaydedildi" if saved else "Kaydedilmedi")
        self.save_dot.setProperty("state", "success" if saved else "warning")
        repolish(self.save_dot)
