"""Dışa ve içe aktarma pencerelerinin ortak parçaları: üst başlık, yan panel, alt çubuk, kısaltan etiket."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from nxceviri.gui.widgets import label, repolish

#: Yan panelin piksel genişliği (içe ve dışa aktarma pencereleri aynı düzeni kullanır).
SIDE_WIDTH = 300


class ElidedLabel(QLabel):
    """Tek satır; sığmayan metin sonda “…” ile kısaltılır, tamamı ipucunda görünür."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def _elide(self) -> None:
        self.setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(self.width(), 40)))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide()


def section_label(text: str) -> QLabel:
    """Yan panel bölüm başlığı (ör. “DOSYALAR · 3”)."""
    return label(text, "sectionLabel")


def named_frame(name: str) -> QFrame:
    """Tema kuralının nesne adıyla bağlandığı çerçeve (`dialogHeader`, `sidePanel`, `mainPanel`, `dialogFooter`)."""
    frame = QFrame()
    frame.setObjectName(name)
    return frame


def header_bar(title: str, description: str) -> tuple[QFrame, QHBoxLayout]:
    """Üst başlık çubuğu: sol sütunda başlık ve açıklama; döndürülen düzene sağdaki eylemler eklenir."""
    bar = named_frame("dialogHeader")
    row = QHBoxLayout(bar)
    row.setContentsMargins(24, 16, 24, 12)
    row.setSpacing(16)
    column = QVBoxLayout()
    column.setSpacing(4)
    column.addWidget(label(title, "pageTitle"))
    column.addWidget(label(description, "muted", wrap=True))
    row.addLayout(column, 1)
    return bar, row


def result_row(text: str, tone: str = "") -> tuple[QFrame, QLabel]:
    """“SONUÇ” listesinin bir satırı: soldaki ad, sağdaki kalın değer (döndürülen etiket). `tone`: info | danger."""
    frame = QFrame()
    frame.setObjectName("resultRow")
    frame.setProperty("tone", tone)
    row = QHBoxLayout(frame)
    row.setContentsMargins(8, 8, 12, 8)
    row.addWidget(QLabel(text), 1)
    value = QLabel("0")
    font = value.font()
    font.setBold(True)
    value.setFont(font)
    row.addWidget(value)
    return frame, value


def set_tone(frame: QWidget, tone: str) -> None:
    """Satırın tonunu değiştirir ve stilini yeniler."""
    frame.setProperty("tone", tone)
    repolish(frame)
