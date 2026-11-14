"""Sorunlar panosu yardımcıları: açılır "Gelişmiş" bölümü."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget

from nxceviri.gui.icons import bind_icon


class Disclosure(QWidget):
    """Başlığa tıklayınca açılıp kapanan bölüm ("Gelişmiş")."""

    def __init__(self, title: str) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setProperty("role", "link")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        bind_icon(self.toggle, "chevron-down", size=14)
        self.toggle.toggled.connect(self._toggled)
        lay.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        self.body.hide()
        lay.addWidget(self.body)

    def _toggled(self, open_: bool) -> None:
        self.body.setVisible(open_)
        bind_icon(self.toggle, "chevron-up" if open_ else "chevron-down", size=14)
