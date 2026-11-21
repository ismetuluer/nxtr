"""Oyunu Ekle sayfasının oyun kartı ve ek içerikler kartı (ARCHITECTURE 246).

Oyun kartı: simge (kapak), ad, sürüm rozetleri ve oyun kimliği. Ek içerikler kartı: her DLC dosyası bir kutucuk.
Her dosya için "Kaldır" ve (dosya yoksa) "Yeni yerini göster" eylemleri sağ tık menüsünde ve kartın "Dosyalar"
düğmesinin menüsünde durur; eskiden tablodaki "Kaldır" düğmesinin yerini alır.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QImage, QPainter, QPainterPath, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.container.package import KIND_BASE, KIND_DLC, KIND_LABELS, KIND_UPDATE
from nxceviri.core.project import SourceRecord
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.scale import R12, S4, S8
from nxceviri.gui.widgets import Card, format_int, format_size, repolish, tip_html

log = logging.getLogger(__name__)

RELINK_TEXT = "Yeni Yerini Göster…"
#: Kapak karesinin kenarı (mantıksal px) ve köşe yarıçapı (`scale.R12` ile aynı).
COVER_SIDE = 112
COVER_RADIUS = R12
#: Ek içerik ızgarası bundan dar olunca tek sütuna düşer (px).
TILE_MIN_WIDTH = 260


def initials(name: str) -> str:
    """Yer tutucu kapak için oyun adının baş harfleri (iki sözcükse her birinin ilki, tekse ilk iki harf)."""
    words = re.findall(r"[^\W_]+", name)
    if not words:
        return "?"
    letters = words[0][0] + words[1][0] if len(words) > 1 else words[0][:2]
    return str(letters.upper())


def rounded_cover(data: bytes, side: int, radius: int, ratio: float) -> QPixmap | None:
    """JPEG simgeyi `side` mantıksal pikselde, yuvarlak köşeli ve ekran yoğunluğuna göre keskin bir resme çevirir."""
    image = QImage.fromData(data)
    if image.isNull():
        return None
    pixels = max(1, round(side * ratio))
    scaled = image.scaled(
        pixels, pixels, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
    )
    out = QPixmap(pixels, pixels)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, pixels, pixels, radius * ratio, radius * ratio)
    painter.setClipPath(path)
    painter.drawImage((pixels - scaled.width()) // 2, (pixels - scaled.height()) // 2, scaled)
    painter.end()
    out.setDevicePixelRatio(ratio)
    return out


class FlowLayout(QLayout):
    """Soldan sağa dizen, sığmayınca alt satıra geçen yerleşim (rozetler için)."""

    def __init__(self, parent: QWidget | None = None, spacing: int = S8) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins: QMargins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _arrange(self, rect: QRect, *, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, row_height = area.x(), area.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x > area.x() and x + hint.width() > area.right() + 1:
                x = area.x()
                y += row_height + self.spacing()
                row_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.spacing()
            row_height = max(row_height, hint.height())
        return y + row_height - rect.y() + margins.bottom()


class ElidedLabel(QLabel):
    """Sığmayan metni sonda "…" ile kısaltan etiket; tam metin ipucunda durur."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(40)
        self._elide()

    def set_full_text(self, text: str) -> None:
        self._full = text
        self._elide()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        shown = QFontMetrics(self.font()).elidedText(self._full, Qt.TextElideMode.ElideRight, max(self.width(), 40))
        super().setText(shown)


def _pill(text: str, state: str, tip: str = "") -> QLabel:
    pill = QLabel(text)
    pill.setProperty("role", "pill")
    pill.setProperty("state", state)
    if tip:
        pill.setToolTip(tip_html(tip))
    return pill


def source_tip(source: SourceRecord) -> str:
    """Rozet/kutucuk ipucu: eski tablodaki bütün bilgiler (tür, dosya, boyut, oyun kimliği, sürüm, durum)."""
    exists = source.path.is_file()
    version = f"v{source.version}" + (f" ({source.display_version})" if source.display_version else "")
    lines = [
        KIND_LABELS.get(source.kind, source.kind),
        f"{source.path.name}  ·  {format_size(source.file_size)}",
        str(source.path),
        f"Oyun kimliği (TitleID): {source.title_id}",
        f"Sürüm: {version}",
    ]
    if not exists:
        lines.append("Dosya bulunamadı; Yeni Yerini Göster ile bağlayın.")
    return "\n".join(lines)


def source_menu(
    parent: QWidget,
    entries: Sequence[tuple[int, SourceRecord]],
    *,
    per_file: bool,
    remove: Callable[[int], None],
    relink: Callable[[], None],
) -> QMenu:
    """Dosya eylemleri menüsü. `entries`: (listedeki sıra, kayıt). `per_file` ise her giriş "Kaldır: <tür> — <dosya>"
    biçiminde adlanır; dosyası bulunamayan kayıt varsa "Yeni Yerini Göster…" eklenir."""
    menu = QMenu(parent)
    for index, source in entries:
        title = "Kaldır"
        if per_file:
            title = f"Kaldır: {KIND_LABELS.get(source.kind, source.kind)} — {source.path.name}"
        menu.addAction(title).triggered.connect(lambda _=False, i=index: remove(i))
    if any(not s.path.is_file() for _, s in entries):
        menu.addSeparator()
        menu.addAction(RELINK_TEXT).triggered.connect(lambda _=False: relink())
    return menu


class GameCover(QLabel):
    """Oyunun simgesi; simge yoksa ya da okunamazsa oyun adının baş harfleriyle koyu kare yer tutucu."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(COVER_SIDE, COVER_SIDE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_game("", b"")

    def set_game(self, name: str, icon: bytes) -> None:
        pixmap = rounded_cover(icon, COVER_SIDE, COVER_RADIUS, self.devicePixelRatioF()) if icon else None
        if icon and pixmap is None:
            log.warning("Oyun simgesi Qt tarafından okunamadı; yer tutucu gösteriliyor.")
        if pixmap is not None:
            self.setPixmap(pixmap)
            self.setText("")
            self.setProperty("role", "coverImage")
        else:
            self.setPixmap(QPixmap())
            self.setText(initials(name))
            self.setProperty("role", "cover")
        self.setAccessibleName(f"{name} simgesi" if name else "Oyun simgesi")
        repolish(self)

    def has_image(self) -> bool:
        return bool(self.property("role") == "coverImage")


class GameCard(Card):
    """Oyun kartı: kapak, ad, rozetler (ana oyun, güncelleme, ek içerik sayısı, çeviri durumu), oyun kimliği."""

    remove_requested = Signal(int)
    relink_requested = Signal()

    def __init__(self) -> None:
        super().__init__("")
        row = QHBoxLayout()
        row.setSpacing(24)
        self.cover = GameCover()
        row.addWidget(self.cover, alignment=Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(12)
        self.name = QLabel()
        self.name.setProperty("role", "gameName")
        self.name.setWordWrap(True)
        self.name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.addWidget(self.name)
        self._pills_box = QWidget()
        self._pills = FlowLayout(self._pills_box)
        info.addWidget(self._pills_box)
        self.meta = QLabel()
        self.meta.setProperty("role", "muted")
        self.meta.setWordWrap(True)
        self.meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.addWidget(self.meta)
        info.addStretch(1)
        row.addLayout(info, 1)
        self.manage = QToolButton()
        self.manage.setObjectName("manageButton")
        self.manage.setProperty("role", "viewTool")
        self.manage.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.manage.setToolTip("Oyun dosyaları: listeden kaldır, yeni yerini göster")
        self.manage.setAccessibleName("Oyun dosyaları")
        self.manage.setCursor(Qt.CursorShape.PointingHandCursor)
        bind_icon(self.manage, "ellipsis")
        row.addWidget(self.manage, alignment=Qt.AlignmentFlag.AlignTop)
        self.body.addLayout(row)
        self._sources: list[SourceRecord] = []
        self._progress: tuple[int, int] = (0, 0)

    def set_sources(self, sources: Sequence[SourceRecord]) -> None:
        self._sources = list(sources)
        indexed = list(enumerate(self._sources))
        games = [(i, s) for i, s in indexed if s.kind in (KIND_BASE, KIND_UPDATE)]
        dlcs = [(i, s) for i, s in indexed if s.kind == KIND_DLC]
        main = next((s for _, s in indexed if s.kind == KIND_BASE), None) or (
            self._sources[0] if self._sources else None
        )
        if main is None:
            self.name.setText("")
            self.meta.setText("")
            self.cover.set_game("", b"")
            self._fill_pills([], 0)
            self.manage.setMenu(QMenu(self.manage))  # boş menü: oyun yokken kart zaten görünmez
            return
        # Ad: ana oyunun adı; simge: ilk bulunan (ana oyun önce). Güncelleme adı da NACP'den gelir.
        name = main.name
        icon = next((s.icon for _, s in indexed if s.icon), b"")
        publisher = next((s.publisher for _, s in indexed if s.publisher), "")
        self.name.setText(name)
        self.cover.set_game(name, icon)
        meta = f"Oyun kimliği {main.application_id}"
        if publisher:
            meta += f"  ·  Yayıncı · {publisher}"
        self.meta.setText(meta)
        self._fill_pills(games, len(dlcs))
        self.manage.setMenu(
            source_menu(
                self.manage,
                indexed,
                per_file=True,
                remove=self.remove_requested.emit,
                relink=self.relink_requested.emit,
            )
        )

    def set_progress(self, total: int, translated: int) -> None:
        """Tablodaki satır sayısı ve çevrilenler; satır yoksa (proje taranmamış) rozet gösterilmez."""
        if (total, translated) == self._progress:
            return  # tablo her düzenlemede bildirir; değişmediyse rozetler yeniden kurulmaz
        self._progress = (total, translated)
        indexed = list(enumerate(self._sources))
        games = [(i, s) for i, s in indexed if s.kind in (KIND_BASE, KIND_UPDATE)]
        self._fill_pills(games, sum(1 for s in self._sources if s.kind == KIND_DLC))

    def _fill_pills(self, games: Sequence[tuple[int, SourceRecord]], dlc_count: int) -> None:
        while (item := self._pills.takeAt(0)) is not None:
            if (widget := item.widget()) is not None:
                widget.setParent(None)
                widget.deleteLater()
        for index, source in games:
            state = "success" if source.path.is_file() else "danger"
            if source.kind == KIND_BASE:
                version = source.display_version or f"v{source.version}"
                text = f"Ana oyun · {version}"
            else:
                text = f"Güncelleme · v{source.version}"
            if state == "danger":
                text += " · bulunamadı"
            pill = _pill(text, state, source_tip(source))
            pill.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            pill.customContextMenuRequested.connect(lambda pos, p=pill, e=(index, source): self._popup(p, pos, e))
            self._pills.addWidget(pill)
        if dlc_count:
            self._pills.addWidget(_pill(f"{dlc_count} ek içerik", "info"))
        total, translated = self._progress
        if total:
            percent = round(100 * translated / total)
            self._pills.addWidget(_pill(f"{format_int(total)} satır · %{percent} çevrildi", "neutral"))
        self._pills_box.updateGeometry()

    def _popup(self, anchor: QWidget, pos: QPoint, entry: tuple[int, SourceRecord]) -> None:
        menu = source_menu(
            anchor, [entry], per_file=False, remove=self.remove_requested.emit, relink=self.relink_requested.emit
        )
        menu.exec(anchor.mapToGlobal(pos))

    def pills(self) -> list[QLabel]:
        found = []
        for i in range(self._pills.count()):
            item = self._pills.itemAt(i)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QLabel):
                found.append(widget)
        return found


class _Tile(QFrame):
    def __init__(self, source: SourceRecord) -> None:
        super().__init__()
        self.setObjectName("dlcTile")
        exists = source.path.is_file()
        self.setProperty("state", "success" if exists else "danger")
        row = QHBoxLayout(self)
        row.setContentsMargins(S8 + S4, S8, S8 + S4, S8)
        row.setSpacing(S8 + S4)
        self.dot = QLabel()
        self.dot.setProperty("role", "dot")
        self.dot.setProperty("state", "success" if exists else "danger")
        self.dot.setFixedSize(8, 8)
        row.addWidget(self.dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.name = ElidedLabel(source.name)
        self.name.setToolTip(tip_html(f"{source.name}\n{source_tip(source)}"))
        row.addWidget(self.name, 1)
        self.link: QToolButton | None = None
        if exists:
            version = QLabel(f"v{source.version}")
            version.setProperty("role", "muted")
            row.addWidget(version, alignment=Qt.AlignmentFlag.AlignVCenter)
        else:
            self.link = QToolButton()
            self.link.setText("Yerini göster")
            self.link.setProperty("role", "link")
            self.link.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(self.link)


class _TileGrid(QWidget):
    """Kutucukları iki sütunlu ızgarada dizer; dar pencerede tek sütuna düşer."""

    def __init__(self) -> None:
        super().__init__()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(S8)
        self._tiles: list[_Tile] = []
        self._columns = 0

    def set_tiles(self, tiles: list[_Tile]) -> None:
        for tile in self._tiles:
            self._grid.removeWidget(tile)
            tile.setParent(None)
            tile.deleteLater()
        self._tiles = tiles
        self._columns = 0
        self._relayout()

    def columns(self) -> int:
        return self._columns

    def _wanted_columns(self) -> int:
        return 2 if self.width() >= 2 * TILE_MIN_WIDTH + self._grid.spacing() else 1

    def _relayout(self) -> None:
        cols = self._wanted_columns()
        if cols == self._columns and self._grid.count() == len(self._tiles):
            return
        self._columns = cols
        for tile in self._tiles:
            self._grid.removeWidget(tile)
        for i, tile in enumerate(self._tiles):
            self._grid.addWidget(tile, i // cols, i % cols)
        for c in range(2):
            self._grid.setColumnStretch(c, 1 if c < cols else 0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout()


class DlcCard(Card):
    """Ek içerikler (DLC) kartı: "N dosya · hepsi bulundu / K eksik" ve her dosya için bir kutucuk."""

    remove_requested = Signal(int)
    relink_requested = Signal()

    def __init__(self) -> None:
        super().__init__("Ek içerikler")
        self.summary = QLabel()
        self.summary.setProperty("role", "muted")
        self.header_right.addWidget(self.summary)
        self.grid = _TileGrid()
        self.tiles: list[_Tile] = []
        self.body.addWidget(self.grid)

    def _popup(self, anchor: QWidget, pos: QPoint, entry: tuple[int, SourceRecord]) -> None:
        menu = source_menu(
            anchor, [entry], per_file=False, remove=self.remove_requested.emit, relink=self.relink_requested.emit
        )
        menu.exec(anchor.mapToGlobal(pos))

    def set_sources(self, sources: Sequence[SourceRecord]) -> None:
        dlcs = [(i, s) for i, s in enumerate(sources) if s.kind == KIND_DLC]
        tiles: list[_Tile] = []
        for index, source in dlcs:
            tile = _Tile(source)
            tile.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tile.customContextMenuRequested.connect(lambda pos, t=tile, e=(index, source): self._popup(t, pos, e))
            if tile.link is not None:
                tile.link.clicked.connect(self.relink_requested)
            tiles.append(tile)
        self.grid.set_tiles(tiles)
        self.tiles = tiles
        missing = sum(1 for _, s in dlcs if not s.path.is_file())
        self.summary.setText(f"{len(dlcs)} dosya · " + (f"{missing} eksik" if missing else "hepsi bulundu"))
        self.setVisible(bool(dlcs))
