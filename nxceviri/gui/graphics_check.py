"""Kontrol Et → Grafik sekmesi: özgün ve Türkçe resimleri yan yana, üst üste ya da gidip gelerek karşılaştırma.

Yalnızca görünüm: denetim, klasör seçimi ve onay kaydı `gui/graphics_controller.py`'dedir. Sekme denetleyiciden
hazır satırları (`GraphicsRow`: denetim sonucu + rozet) alır, kullanıcının isteklerini sinyallerle bildirir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.qa.graphics import Box, GraphicsItem
from nxceviri.gui.shortcuts import display_text
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import BusyState, EmptyState, ErrorState, button, label

#: Karşılaştırma kipleri.
MODE_SIDE = "side"
MODE_OVERLAY = "overlay"
MODE_FLIP = "flip"
MODE_LABELS = {MODE_SIDE: "Yan yana", MODE_OVERLAY: "Üst üste", MODE_FLIP: "Gidip gel"}

#: Liste süzgeçleri.
FILTER_PROBLEMS = "problems"
FILTER_MISSING = "missing"
FILTER_ALL = "all"
FILTER_LABELS = {FILTER_PROBLEMS: "Sorunlu", FILTER_MISSING: "Eksik", FILTER_ALL: "Hepsi"}

#: Rozet metinleri (durum sütunu).
BADGE_APPROVED = "Onaylandı"
BADGE_READY = "Hazır"
BADGE_WARNING = "Uyarı"
BADGE_ERROR = "Hata"
BADGE_MISSING = "Eksik"
BADGE_UNCHANGED = "Değişmemiş"
#: "Sorunlu" süzgecine ve sekme başlığındaki sayıya giren rozetler.
PROBLEM_BADGES = frozenset({BADGE_ERROR, BADGE_WARNING, BADGE_UNCHANGED})

#: Sekmedeki durum sayfaları.
PAGE_NO_FOLDER = 0
PAGE_NO_ORIGINALS = 1
PAGE_LOADING = 2
PAGE_ERROR = 3
PAGE_RESULTS = 4

#: Dama tahtası karesinin kenarı (mantıksal piksel).
_CHECKER = 8
#: Yan yana kipte iki resim arasındaki boşluk ve resim başlığının yüksekliği.
_GAP = 16
_CAPTION = 22
#: Sığdırma kipinde küçük resimler en çok bu kadar büyütülür.
_MAX_FIT_SCALE = 8.0
_ITEM_HEIGHT = 46
_NO_FOLDER_TEXT = "İçinde orijinal/ ve turkce/ klasörleri bulunan grafik klasörünü seçin."


@dataclass(frozen=True)
class GraphicsRow:
    """Listede bir resim: denetim sonucu, rozet metni ve rengi (`Badge` durumları), onaylanabilir mi."""

    item: GraphicsItem
    badge: str
    state: str
    approved: bool
    approvable: bool


def load_image(path: Path | None) -> QImage | None:
    """Resmi gösterim için yükler; Qt'nin açamadığı biçimler (DDS) Pillow ile açılır. Açılamazsa None."""
    if path is None:
        return None
    image = QImage(str(path))
    if not image.isNull():
        return image
    try:
        with Image.open(path) as raw:
            rgba = raw.convert("RGBA")
    except (OSError, ValueError, SyntaxError):
        return None
    data = rgba.tobytes()
    return QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()


def _checker_brush(dark: QColor, light: QColor) -> QBrush:
    tile = QPixmap(_CHECKER * 2, _CHECKER * 2)
    tile.fill(light)
    painter = QPainter(tile)
    painter.fillRect(0, 0, _CHECKER, _CHECKER, dark)
    painter.fillRect(_CHECKER, _CHECKER, _CHECKER, _CHECKER, dark)
    painter.end()
    return QBrush(tile)


class CompareView(QWidget):
    """Özgün ve Türkçe resmi çizer. Gidip gel kipinde tıklama ya da Boşluk iki resim arasında geçer."""

    flipped = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.original: QImage | None = None
        self.turkish: QImage | None = None
        self.original_box: Box | None = None
        self.turkish_box: Box | None = None
        self.mode = MODE_SIDE
        #: Üst üste kipte Türkçenin opaklığı (0 = yalnızca özgün, 1 = yalnızca Türkçe).
        self.blend = 0.5
        #: Gidip gel kipinde Türkçe mi görünüyor.
        self.show_turkish = True
        self.guide = False
        self.fit = True

    # --- dışarıdan ----------------------------------------------------------------------

    def set_images(
        self, original: QImage | None, turkish: QImage | None, original_box: Box | None, turkish_box: Box | None
    ) -> None:
        self.original, self.turkish = original, turkish
        self.original_box, self.turkish_box = original_box, turkish_box
        self._resize_for_zoom()
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._resize_for_zoom()
        self.update()

    def set_blend(self, value: float) -> None:
        self.blend = min(1.0, max(0.0, value))
        self.update()

    def set_guide(self, on: bool) -> None:
        self.guide = on
        self.update()

    def set_fit(self, fit: bool) -> None:
        self.fit = fit
        self._resize_for_zoom()
        self.update()

    def toggle_flip(self) -> None:
        if self.mode != MODE_FLIP:
            return
        self.show_turkish = not self.show_turkish
        self.flipped.emit(self.show_turkish)
        self.update()

    # --- boyut --------------------------------------------------------------------------

    def _image_size(self, image: QImage | None) -> QSize:
        """Resmin %100'deki mantıksal boyutu: bir resim pikseli bir ekran pikseli (yüksek DPI'da keskin)."""
        if image is None:
            other = self.original or self.turkish
            return self._image_size(other) if other is not None and image is not other else QSize(160, 90)
        ratio = max(1.0, self.devicePixelRatioF())
        return QSize(max(1, round(image.width() / ratio)), max(1, round(image.height() / ratio)))

    def natural_size(self) -> QSize:
        first, second = self._image_size(self.original), self._image_size(self.turkish)
        if self.mode == MODE_SIDE:
            return QSize(first.width() + _GAP + second.width(), max(first.height(), second.height()) + _CAPTION)
        return QSize(max(first.width(), second.width()), max(first.height(), second.height()) + _CAPTION)

    def _resize_for_zoom(self) -> None:
        if self.fit:
            self.setMinimumSize(0, 0)
        else:
            self.setMinimumSize(self.natural_size())
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        return self.natural_size() if not self.fit else QSize(320, 200)

    def _scale(self) -> float:
        if not self.fit:
            return 1.0
        natural = self.natural_size()
        width = max(1, natural.width())
        height = max(1, natural.height() - _CAPTION)
        available_w = max(1, self.width() - (_GAP if self.mode == MODE_SIDE else 0))
        available_h = max(1, self.height() - _CAPTION)
        content_w = max(1, width - (_GAP if self.mode == MODE_SIDE else 0))
        return min(_MAX_FIT_SCALE, available_w / content_w, available_h / height)

    # --- çizim --------------------------------------------------------------------------

    def paintEvent(self, _event: QPaintEvent) -> None:
        tokens = current_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        scale = self._scale()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, scale != 1.0)  # %100: piksel piksel
        checker = _checker_brush(QColor(tokens["surface2"]), QColor(tokens["surface"]))
        first = self._image_size(self.original)
        second = self._image_size(self.turkish)
        if self.mode == MODE_SIDE:
            w1, h1 = round(first.width() * scale), round(first.height() * scale)
            w2, h2 = round(second.width() * scale), round(second.height() * scale)
            total = w1 + _GAP + w2
            left = max(0, (self.width() - total) // 2)
            top = self._top(max(h1, h2))
            first_rect = QRect(left, top, w1, h1)
            second_rect = QRect(left + w1 + _GAP, top, w2, h2)
            self._caption(painter, tokens, first_rect, "Orijinal")
            self._caption(painter, tokens, second_rect, "Türkçe")
            self._image(
                painter=painter,
                tokens=tokens,
                checker=checker,
                rect=first_rect,
                image=self.original,
                missing_text="Orijinal resim açılamadı",
            )
            self._image(
                painter=painter,
                tokens=tokens,
                checker=checker,
                rect=second_rect,
                image=self.turkish,
                missing_text="Türkçe resim yok",
            )
            if self.guide:
                self._guides(painter, tokens, first_rect, first, with_turkish=False)
                self._guides(painter, tokens, second_rect, second, with_turkish=True)
            painter.end()
            return
        width = round(max(first.width(), second.width()) * scale)
        height = round(max(first.height(), second.height()) * scale)
        left = max(0, (self.width() - width) // 2)
        top = self._top(height)
        area = QRect(left, top, width, height)
        painter.fillRect(area, checker)
        rect1 = QRect(left, top, round(first.width() * scale), round(first.height() * scale))
        rect2 = QRect(left, top, round(second.width() * scale), round(second.height() * scale))
        if self.mode == MODE_OVERLAY:
            caption = f"Orijinal → Türkçe  %{round(self.blend * 100)}"
            if self.original is not None:
                painter.setOpacity(1.0 - self.blend if self.turkish is not None else 1.0)
                painter.drawImage(rect1, self.original)
            if self.turkish is not None:
                painter.setOpacity(self.blend if self.original is not None else 1.0)
                painter.drawImage(rect2, self.turkish)
            painter.setOpacity(1.0)
        else:
            shown = self.turkish if self.show_turkish else self.original
            name = "Türkçe" if self.show_turkish else "Orijinal"
            caption = f"{name}  (tıklayın ya da Boşluk: geçiş)"
            if shown is not None:
                painter.drawImage(rect2 if self.show_turkish else rect1, shown)
            else:
                self._placeholder(painter, tokens, area, "Türkçe resim yok" if self.show_turkish else "Resim yok")
        self._caption(painter, tokens, area, caption)
        if self.guide:
            self._guides(painter, tokens, rect1, first, with_turkish=False)
            self._guides(painter, tokens, rect2, second, with_turkish=True, original_too=False)
        painter.end()

    def _top(self, content_height: int) -> int:
        """Resimlerin üst kenarı: sığdırma kipinde dikeyde ortalanır, başlık için yer bırakılır."""
        if not self.fit:
            return _CAPTION
        return _CAPTION + max(0, (self.height() - _CAPTION - content_height) // 2)

    def _caption(self, painter: QPainter, tokens: dict[str, str], rect: QRect, text: str) -> None:
        painter.setPen(QColor(tokens["muted"]))
        metrics = QFontMetrics(painter.font())
        shown = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(40, rect.width()))
        area = QRect(rect.left(), rect.top() - _CAPTION, max(rect.width(), 40), _CAPTION - 4)
        painter.drawText(area, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, shown)

    def _image(
        self,
        *,
        painter: QPainter,
        tokens: dict[str, str],
        checker: QBrush,
        rect: QRect,
        image: QImage | None,
        missing_text: str,
    ) -> None:
        if image is None:
            self._placeholder(painter, tokens, rect, missing_text)
            return
        painter.fillRect(rect, checker)
        painter.drawImage(rect, image)

    def _placeholder(self, painter: QPainter, tokens: dict[str, str], rect: QRect, text: str) -> None:
        pen = QPen(QColor(tokens["border"]))
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setPen(QColor(tokens["muted"]))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

    def _guides(
        self,
        painter: QPainter,
        tokens: dict[str, str],
        rect: QRect,
        logical: QSize,
        *,
        with_turkish: bool,
        original_too: bool = True,
    ) -> None:
        """Kılavuz: özgünün içerik kutusu kesikli, Türkçenin kutusu düz çizgi (özgün kutuyu aşıyorsa kırmızı)."""
        image = self.turkish if with_turkish else self.original
        pixel_w = image.width() if image is not None else 0
        if pixel_w <= 0 or logical.width() <= 0:
            return
        factor = rect.width() / pixel_w

        def to_rect(box: Box) -> QRectF:
            x0, y0, x1, y1 = box
            return QRectF(rect.left() + x0 * factor, rect.top() + y0 * factor, (x1 - x0) * factor, (y1 - y0) * factor)

        if original_too and self.original_box is not None:
            pen = QPen(QColor(tokens["accent"]))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(to_rect(self.original_box))
        if with_turkish and self.turkish_box is not None:
            inside = self.original_box is None or _contains(self.original_box, self.turkish_box)
            pen = QPen(QColor(tokens["success" if inside else "danger"]))
            pen.setWidth(2 if not inside else 1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(to_rect(self.turkish_box))

    # --- etkileşim ----------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.mode == MODE_FLIP and event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.toggle_flip()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.mode == MODE_FLIP and event.key() == Qt.Key.Key_Space and not event.modifiers():
            self.toggle_flip()
            return
        super().keyPressEvent(event)


def _contains(outer: Box, inner: Box) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


class _RowDelegate(QStyledItemDelegate):
    """Liste satırı: ad, altında ilk sorun (soluk), sağda durum rozeti."""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(200, _ITEM_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        row = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(row, GraphicsRow):
            super().paint(painter, option, index)
            return
        tokens = current_tokens()
        painter.save()
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect, QColor(tokens["selection"]))
        font = option.font
        metrics = QFontMetrics(font)
        badge_w = metrics.horizontalAdvance(row.badge) + 16
        badge_h = metrics.height() + 4
        badge = QRect(rect.right() - badge_w - 8, rect.top() + (rect.height() - badge_h) // 2, badge_w, badge_h)
        background, foreground = _badge_colors(tokens, row.state)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(badge, 8, 8)
        bold = QFont(font)
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor(foreground))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, row.badge)
        text_w = max(20, badge.left() - rect.left() - 18)
        painter.setPen(QColor(tokens["text"]))
        name = QFontMetrics(bold).elidedText(row.item.name, Qt.TextElideMode.ElideMiddle, text_w)
        line_h = metrics.height()
        top = rect.top() + (rect.height() - 2 * line_h) // 2
        painter.drawText(QRect(rect.left() + 10, top, text_w, line_h), Qt.AlignmentFlag.AlignVCenter, name)
        painter.setFont(font)
        painter.setPen(QColor(tokens["muted"]))
        detail = row.item.issues[0].message if row.item.issues else _quiet_detail(row)
        painter.drawText(
            QRect(rect.left() + 10, top + line_h, text_w, line_h),
            Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(detail, Qt.TextElideMode.ElideRight, text_w),
        )
        painter.restore()


def _badge_colors(tokens: dict[str, str], state: str) -> tuple[str, str]:
    return {
        "success": (tokens["success_bg"], tokens["success"]),
        "warning": (tokens["warning_bg"], tokens["warning"]),
        "danger": (tokens["danger_bg"], tokens["danger"]),
        "info": (tokens["selection"], tokens["text"]),
    }.get(state, (tokens["surface2"], tokens["muted"]))


def _quiet_detail(row: GraphicsRow) -> str:
    if row.item.state == "missing":
        return "Türkçesi yok"
    return "Onaylandı" if row.approved else "Sorun bulunmadı"


def _chip(text: str) -> QToolButton:
    chip = QToolButton()
    chip.setText(text)
    chip.setCheckable(True)
    chip.setProperty("role", "chip")
    chip.setCursor(Qt.CursorShape.PointingHandCursor)
    return chip


class GraphicsCheckTab(QWidget):
    """Grafik sekmesi: durum sayfaları (klasör yok, özgün yok, denetleniyor, hata) ve sonuçlar."""

    choose_folder = Signal()
    extract_requested = Signal()
    open_folder = Signal()
    refresh_requested = Signal()
    #: Seçili resmin onayını değiştir (onaylıysa kaldırır); resim adı.
    approve_toggled = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[GraphicsRow] = []
        self._filter = FILTER_ALL
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.setSpacing(10)
        self.info = label("", "muted", wrap=True)
        outer.addWidget(self.info)
        self.info.setHidden(True)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        # Klasör yok.
        self.choose_empty = button("Klasör Seç…", "primary", icon="folder-open")
        self.choose_empty.clicked.connect(self.choose_folder)
        self.no_folder = EmptyState(
            "Grafik klasörü seçilmedi",
            _NO_FOLDER_TEXT,
            self.choose_empty,
        )
        self.stack.addWidget(self.no_folder)

        # Özgün resim yok.
        actions = QWidget()
        actions_lay = QHBoxLayout(actions)
        actions_lay.setContentsMargins(0, 0, 0, 0)
        self.extract_button = button("Görselleri Çıkar", "primary", icon="image")
        self.extract_button.clicked.connect(self.extract_requested)
        self.choose_originals = button("Klasör Seç…", icon="folder-open")
        self.choose_originals.clicked.connect(self.choose_folder)
        actions_lay.addWidget(self.extract_button)
        actions_lay.addWidget(self.choose_originals)
        self.no_originals = EmptyState("Orijinal resim yok", "", actions)
        self.stack.addWidget(self.no_originals)

        # Denetleniyor.
        self.loading = BusyState("Resimler denetleniyor", "Özgün ve Türkçe resimler karşılaştırılıyor.")
        self.stack.addWidget(self.loading)

        # Hata.
        error_page = QWidget()
        error_lay = QVBoxLayout(error_page)
        error_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error = ErrorState()
        self.error.title.setText("Resimler denetlenemedi")
        self.retry_button = button("Tekrar Dene", icon="refresh-cw")
        self.retry_button.clicked.connect(self.refresh_requested)
        error_lay.addWidget(self.error)
        error_lay.addWidget(self.retry_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(error_page)

        self.stack.addWidget(self._build_results())
        self.stack.setCurrentIndex(PAGE_NO_FOLDER)

        #: Onay kısayolu (komut kataloğundan bağlanır); yalnızca bu sekme odaktayken çalışır.
        self.approve_action = QAction("Onayla", self)
        self.approve_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.approve_action.triggered.connect(self._approve_current)
        self.addAction(self.approve_action)
        self.approve_action.changed.connect(self._sync_approve_tip)
        self._show_row(None)

    # --- kurulum ------------------------------------------------------------------------

    def _build_results(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        lay.addWidget(split, 1)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(8)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.filter_chips: dict[str, QToolButton] = {}
        for key, text in FILTER_LABELS.items():
            chip = _chip(text)
            chip.clicked.connect(lambda _c=False, k=key: self.set_filter(k))
            self.filter_group.addButton(chip)
            self.filter_chips[key] = chip
            chips.addWidget(chip)
        chips.addStretch(1)
        self.filter_chips[FILTER_ALL].setChecked(True)
        left_lay.addLayout(chips)
        self.counter = label("", "muted", wrap=True)
        left_lay.addWidget(self.counter)
        self.list = QListWidget()
        self.list.setItemDelegate(_RowDelegate(self.list))
        self.list.setUniformItemSizes(True)
        self.list.currentItemChanged.connect(lambda *_a: self._current_changed())
        left_lay.addWidget(self.list, 1)
        self.list_empty = label("", "muted", wrap=True)
        self.list_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_lay.addWidget(self.list_empty)
        self.list_empty.setHidden(True)
        left.setMinimumWidth(220)
        split.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(8)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_chips: dict[str, QToolButton] = {}
        for key, text in MODE_LABELS.items():
            chip = _chip(text)
            chip.clicked.connect(lambda _c=False, k=key: self.set_mode(k))
            self.mode_group.addButton(chip)
            self.mode_chips[key] = chip
            tools.addWidget(chip)
        self.mode_chips[MODE_SIDE].setChecked(True)
        self.compare = CompareView()
        self.blend = QSlider(Qt.Orientation.Horizontal)
        self.blend.setRange(0, 100)
        self.blend.setValue(50)
        self.blend.setMaximumWidth(160)
        self.blend.setToolTip("Sola: orijinal, sağa: Türkçe")
        self.blend.valueChanged.connect(lambda v: self.compare.set_blend(v / 100))
        tools.addWidget(self.blend)
        tools.addStretch(1)
        self.guide_box = QCheckBox("Kılavuz")
        self.guide_box.setToolTip(
            "Kesikli çerçeve: özgün yazının alanı. Düz çerçeve: Türkçe yazının alanı (özgün alanı aşıyorsa kırmızı)."
        )
        self.guide_box.toggled.connect(self._set_guide)
        tools.addWidget(self.guide_box)
        self.zoom_group = QButtonGroup(self)
        self.zoom_group.setExclusive(True)
        self.fit_chip = _chip("Sığdır")
        self.actual_chip = _chip("%100")
        for chip, fit in ((self.fit_chip, True), (self.actual_chip, False)):
            chip.clicked.connect(lambda _c=False, f=fit: self.set_fit(f))
            self.zoom_group.addButton(chip)
            tools.addWidget(chip)
        self.fit_chip.setChecked(True)
        right_lay.addLayout(tools)
        self.view_scroll = QScrollArea()
        self.view_scroll.setWidgetResizable(True)
        self.view_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.view_scroll.setWidget(self.compare)
        right_lay.addWidget(self.view_scroll, 1)
        self.issues = label("", wrap=True)
        self.issues.setTextFormat(Qt.TextFormat.RichText)
        right_lay.addWidget(self.issues)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 720])

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.approve_button = button("Onayla", "primary", icon="circle-check")
        self.approve_button.clicked.connect(self._approve_current)
        bar.addWidget(self.approve_button)
        bar.addStretch(1)
        self.choose_button = button("Klasör Seç…", icon="folder-open")
        self.choose_button.clicked.connect(self.choose_folder)
        self.open_button = button("Klasörü Aç", icon="folder-open")
        self.open_button.clicked.connect(self.open_folder)
        self.refresh_button = button("Yenile", icon="refresh-cw")
        self.refresh_button.clicked.connect(self.refresh_requested)
        for widget in (self.choose_button, self.open_button, self.refresh_button):
            bar.addWidget(widget)
        lay.addLayout(bar)
        self.blend.setHidden(True)  # yalnızca üst üste kipte
        return page

    # --- durumlar -----------------------------------------------------------------------

    def set_info(self, text: str) -> None:
        self.info.setText(text)
        self.info.setHidden(not text)

    def set_can_choose(self, can: bool) -> None:
        """Klasör oyunun eklentisinden geliyorsa elle seçilemez; düğmeler gizlenir."""
        self.choose_button.setHidden(not can)
        self.choose_originals.setHidden(not can)

    def show_no_folder(self, text: str = "") -> None:
        if text:
            self.no_folder.text.setText(text)
        else:
            self.no_folder.text.setText(_NO_FOLDER_TEXT)
        self.stack.setCurrentIndex(PAGE_NO_FOLDER)

    def show_no_originals(self, folder: Path, can_extract: bool) -> None:
        if can_extract:
            text = "Önce Dışa Aktar → Görseller'den orijinalleri çıkarın; ya da buradan çıkarın."
        else:
            text = (
                f"{folder / 'orijinal'} içinde resim yok. Oyunun özgün resimlerini (PNG/DDS) buraya koyun "
                "ya da başka bir klasör seçin."
            )
        self.no_originals.text.setText(text)
        self.extract_button.setHidden(not can_extract)
        self.stack.setCurrentIndex(PAGE_NO_ORIGINALS)

    def show_loading(self) -> None:
        self.stack.setCurrentIndex(PAGE_LOADING)

    def show_error(self, text: str) -> None:
        self.error.show_error(text)
        self.stack.setCurrentIndex(PAGE_ERROR)

    def page(self) -> int:
        return self.stack.currentIndex()

    def set_checking(self, checking: bool) -> None:
        """Sonuçlar görünürken yeniden denetim: liste yerinde kalır, sayaç satırı denetlendiğini söyler."""
        self.refresh_button.setEnabled(not checking)
        if checking:
            self.counter.setText("Denetleniyor…")

    def set_results(self, rows: list[GraphicsRow], counter: str) -> None:
        """Sonuçları gösterir; seçili resim listede kaldıysa seçili kalır, kalmadıysa aynı sıradaki seçilir."""
        current = self.current_name()
        old_row = self.list.currentRow()
        self._rows = rows
        self.counter.setText(counter)
        self.refresh_button.setEnabled(True)
        self.stack.setCurrentIndex(PAGE_RESULTS)
        self._fill(current, old_row, reload=True)

    def set_filter(self, key: str) -> None:
        self._filter = key
        self.filter_chips[key].setChecked(True)
        self._fill(self.current_name(), 0, reload=False)

    def set_mode(self, mode: str) -> None:
        self.mode_chips[mode].setChecked(True)
        self.blend.setHidden(mode != MODE_OVERLAY)
        self.compare.set_mode(mode)
        if mode == MODE_FLIP:
            self.compare.setFocus()

    def _set_guide(self, on: bool) -> None:
        self.compare.set_guide(on)

    def set_fit(self, fit: bool) -> None:
        (self.fit_chip if fit else self.actual_chip).setChecked(True)
        self.view_scroll.setWidgetResizable(fit)
        self.compare.set_fit(fit)
        if not fit:
            self.compare.resize(self.compare.natural_size())

    def visible_names(self) -> list[str]:
        names = []
        for index in range(self.list.count()):
            row = self.list.item(index).data(Qt.ItemDataRole.UserRole)
            if isinstance(row, GraphicsRow):
                names.append(row.item.name)
        return names

    def current_name(self) -> str | None:
        row = self.current_row()
        return row.item.name if row is not None else None

    def current_row(self) -> GraphicsRow | None:
        item = self.list.currentItem()
        row = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return row if isinstance(row, GraphicsRow) else None

    def select(self, name: str) -> None:
        for index in range(self.list.count()):
            row = self.list.item(index).data(Qt.ItemDataRole.UserRole)
            if isinstance(row, GraphicsRow) and row.item.name == name:
                self.list.setCurrentRow(index)
                return

    # --- iç -----------------------------------------------------------------------------

    def _wanted(self, row: GraphicsRow) -> bool:
        if self._filter == FILTER_PROBLEMS:
            return row.badge in PROBLEM_BADGES
        if self._filter == FILTER_MISSING:
            return row.badge == BADGE_MISSING
        return True

    def _fill(self, keep: str | None, fallback_row: int, *, reload: bool) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        shown = [row for row in self._rows if self._wanted(row)]
        target = -1
        for index, row in enumerate(shown):
            item = QListWidgetItem(row.item.name)
            item.setData(Qt.ItemDataRole.UserRole, row)
            item.setToolTip("\n".join(issue.message for issue in row.item.issues) or row.badge)
            self.list.addItem(item)
            if row.item.name == keep:
                target = index
        if target < 0 and shown:
            target = min(max(0, fallback_row), len(shown) - 1)
        self.list.setCurrentRow(target)
        self.list.blockSignals(False)
        self.list.setHidden(not shown)
        self.list_empty.setHidden(bool(shown))
        if not shown:
            self.list_empty.setText(
                {
                    FILTER_PROBLEMS: "Sorunlu resim yok.",
                    FILTER_MISSING: "Türkçesi eksik resim yok.",
                }.get(self._filter, "Klasörde resim yok.")
            )
        current = self.current_row()
        if reload or current is None or current.item.name != keep:
            self._show_row(current)
        else:
            self._update_details(current)

    def _current_changed(self) -> None:
        self._show_row(self.current_row())

    def _show_row(self, row: GraphicsRow | None) -> None:
        if row is None:
            self.compare.set_images(None, None, None, None)
        else:
            self.compare.set_images(
                load_image(row.item.original),
                load_image(row.item.turkish),
                row.item.original_box,
                row.item.turkish_box,
            )
        if not self.compare.fit:
            self.compare.resize(self.compare.natural_size())
        self._update_details(row)

    def _update_details(self, row: GraphicsRow | None) -> None:
        tokens = current_tokens()
        if row is None:
            self.issues.setText("")
            self.approve_button.setEnabled(False)
            self.approve_button.setText("Onayla")
            return
        lines = []
        for issue in row.item.issues:
            color = tokens["danger" if issue.severity == "error" else "warning"]
            kind = "Hata" if issue.severity == "error" else "Uyarı"
            lines.append(f'<span style="color:{color}; font-weight:600">{kind}:</span> {_escape(issue.message)}')
        if not lines:
            if row.item.state == "missing":
                name = row.item.original.name if row.item.original is not None else row.item.name
                lines.append(f"Türkçesi yok: turkce/ klasörüne aynı adla ({_escape(name)}) koyun.")
            else:
                lines.append("Sorun bulunmadı.")
        if row.approved:
            lines.append(f'<span style="color:{tokens["success"]}; font-weight:600">Onaylandı.</span>')
        self.issues.setText("<br>".join(lines))
        self.approve_button.setText("Onayı Kaldır" if row.approved else "Onayla")
        self.approve_button.setEnabled(row.approved or row.approvable)
        self._sync_approve_tip()

    def _sync_approve_tip(self) -> None:
        key = display_text(self.approve_action.shortcut())
        tip = "Resmi gözle kontrol ettiğinizi işaretler; dosya değişirse onay kalkar."
        self.approve_button.setToolTip(f"{tip} ({key})" if key else tip)

    def _approve_current(self) -> None:
        row = self.current_row()
        if row is not None and (row.approved or row.approvable):
            self.approve_toggled.emit(row.item.name)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
