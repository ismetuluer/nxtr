"""Kenar çubuğu: simgeli adım listesi, sağda rozetler ve üstte proje başlığı.

`StepNav`, `QListWidget`'in tüm arayüzünü korur (`setCurrentRow`, `currentRowChanged`, `item(i)`, öğe bayrakları);
yalnızca çizimi bir `QStyledItemDelegate` ile yapılır. Öğelerin simge adı, rozet metni ve durumu öğe verisindedir,
böylece simgeler her çizimde geçerli tema renkleriyle üretilir ve tema değişince bayatlamaz.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPersistentModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from nxceviri.gui import icons
from nxceviri.gui.step_markers import CURRENT, DONE, NODE_SIZE, PENDING, marker_slot, paint_marker
from nxceviri.gui.theme import current_style, current_tokens
from nxceviri.gui.theme_style import nav_color

#: Adımların sırası (gezgindeki satır numarası); `STEPS` bu sırayla tanımlıdır.
STEP_ADD = 0
STEP_SCAN = 1
STEP_TRANSLATE = 2
STEP_QA = 3
STEP_EXPORT = 4

#: (adım adı, simge adı); sıra yukarıdaki `STEP_*` sabitleriyle aynıdır.
STEPS: tuple[tuple[str, str], ...] = (
    ("Oyunu Ekle", "circle-plus"),
    ("Metinleri Tara", "scan-search"),
    ("Çevir", "languages"),
    ("Kontrol Et", "shield-check"),
    ("Dışa Aktar", "package"),
)
#: Tamamlanan adım kendi simgesini korur (yeşil çizilir); ipucuna ve erişilebilir ada bu ek yazılır.
DONE_SUFFIX = "tamamlandı"

ICON_ROLE = Qt.ItemDataRole.UserRole + 1
BADGE_ROLE = Qt.ItemDataRole.UserRole + 2
STATE_ROLE = Qt.ItemDataRole.UserRole + 3
DONE_ROLE = Qt.ItemDataRole.UserRole + 4

ICON_SIZE = 18
_PAD = 10
_GAP = 8
#: Rozet durumu → tema belirteci.
_BADGE_TOKENS = {"neutral": "muted", "success": "success", "warning": "warning", "danger": "danger"}
#: Rozet alanı en az bu metin kadar genişlik ayırır (örn. büyük sayılar kırpılmasın).
_WIDEST_BADGE = "%100"
_MIN_WIDTH = 188
#: Öğe çiziminin kenarlardan içeri çekildiği piksel (`paint` içindeki `adjusted`).
_ITEM_INSET = 2
#: Listenin iç dolgusu (sol + sağ); QSS'teki `padding: … 8px … 8px` ile aynı olmalı.
LIST_PADDING = 16
#: Daraltılmış çubuk: yalnızca simge; simgenin iki yanında bu kadar boşluk kalır.
_COLLAPSED_PAD = 14
COLLAPSED_WIDTH = ICON_SIZE + 2 * _COLLAPSED_PAD + 2 * _ITEM_INSET + LIST_PADDING
#: Daraltılmış çubukta rozet yerine çizilen nokta (yalnızca uyarı ve hata durumlarında) çapı.
_DOT = 7

#: Yatay (üst çubuk) kipinde hapların arası, listenin yan dolgusu; Qt'nin pencere öğesi en büyük boyu.
_PILL_SPACING = 2
_PILL_PADDING = 4
_QWIDGETSIZE_MAX = 16777215

_Index = QModelIndex | QPersistentModelIndex


def _fixed_width(badge_width: int) -> int:
    """Adım adı dışında kalan yatay pay: kenar boşlukları, işaret (simge, daire, küp…) ve (varsa) rozet."""
    badge = badge_width + _GAP if badge_width else 0
    return 2 * _ITEM_INSET + 1 + 2 * _PAD + marker_slot(current_style()) + _GAP + badge


def text_room(viewport_width: int, badge_width: int) -> int:
    """Adım adına kalan genişlik (piksel). `paint` ve `StepNav.preferred_width` aynı hesabı kullanır."""
    return viewport_width - _fixed_width(badge_width)


def _bold(font: QFont) -> QFont:
    bold = QFont(font)
    bold.setBold(True)
    return bold


def horizontal_item_width(font: QFont, text: str, badge: str) -> int:
    """Üst çubukta (yatay) bir adım hapının genişliği: işaret, ad (seçilince kalın) ve rozet."""
    metrics = QFontMetrics(_bold(font))
    return _fixed_width(metrics.horizontalAdvance(badge) if badge else 0) + metrics.horizontalAdvance(text)


class _StepDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        height = max(36, option.fontMetrics.height() + 16)
        if isinstance(option.widget, StepNav) and option.widget.horizontal:
            text = str(index.data(Qt.ItemDataRole.DisplayRole))
            return QSize(horizontal_item_width(option.font, text, str(index.data(BADGE_ROLE) or "")), height)
        return QSize(0, height)

    def _wire(self, painter: QPainter, index: _Index, rect: QRect, center_x: int, center_y: int) -> None:
        """Kare düğümlü temada ardışık adımları düşey bir telle bağlar; tel tamamlanan adımlar arasında vurguludur."""
        tokens = current_tokens()
        model = index.model()
        row = index.row()
        spans = []
        if row > 0:
            spans.append((rect.top(), center_y - NODE_SIZE, bool(model.index(row - 1, 0).data(DONE_ROLE))))
        if row < model.rowCount() - 1:
            spans.append((center_y + NODE_SIZE, rect.bottom() + 1, bool(index.data(DONE_ROLE))))
        for top, bottom, lit in spans:
            painter.setPen(QPen(QColor(tokens["accent"] if lit else tokens["border"]), 2))
            painter.drawLine(center_x, top, center_x, bottom)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        tokens = current_tokens()
        style = current_style()
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        done = bool(index.data(DONE_ROLE))
        nav = option.widget if isinstance(option.widget, StepNav) else None
        horizontal = nav is not None and nav.horizontal
        collapsed = nav is not None and nav.collapsed and not horizontal
        rect = option.rect.adjusted(_ITEM_INSET, _ITEM_INSET, -_ITEM_INSET, -_ITEM_INSET)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Üst çubukta seçili adım vurgu renginde dolu bir hap; kenar çubuğunda temanın seçili zemini.
        if horizontal:
            fill = tokens["accent"] if selected else nav_color(tokens, "nav_hover_bg")
            ink = tokens["accent_text"] if selected else nav_color(tokens, "nav_text")
            ground = QColor(fill if selected else nav_color(tokens, "nav_bg"))
        else:
            fill = nav_color(tokens, "nav_sel_bg" if selected else "nav_hover_bg")
            ink = nav_color(tokens, "nav_sel_text" if selected else "nav_text")
            ground = QColor(fill if selected else nav_color(tokens, "nav_bg"))
        if selected or (hovered and enabled):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(fill))
            radius = min(style.radius_pill if horizontal else style.radius_button, rect.height() // 2)
            painter.drawRoundedRect(rect, radius, radius)
        if option.state & QStyle.StateFlag.State_HasFocus and nav is not None and nav.keyboard_focus:
            # Klavye odağı: ince vurgu halkası (fare tıklamasında çizilmez).
            painter.setPen(QPen(QColor(tokens["accent"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 7, 7)
        text_color = QColor(ink if enabled else nav_color(tokens, "nav_muted"))
        # Temanın kendi seçili zemini varsa (siyah dolgu gibi) seçili adımın simge ve rozeti yazı rengini alır.
        own_selection = selected and (horizontal or "nav_sel_bg" in tokens)
        if not enabled:
            icon_color = nav_color(tokens, "nav_muted")
        elif style.nav_mono or own_selection:
            icon_color = ink
        else:
            icon_color = tokens["success"] if done else nav_color(tokens, "nav_icon")
        slot = marker_slot(style)
        left_edge = rect.left() + _PAD
        center_y = rect.center().y()
        if style.step_marker == "icon":
            mark = icons.icon(str(index.data(ICON_ROLE)), icon_color, ICON_SIZE).pixmap(ICON_SIZE, ICON_SIZE)
            icon_x = rect.center().x() - ICON_SIZE // 2 + 1 if collapsed else left_edge
            painter.drawPixmap(QPoint(icon_x, center_y - ICON_SIZE // 2 + 1), mark)
            dot = QPoint(icon_x + ICON_SIZE, center_y - ICON_SIZE // 2 + 2)
        else:
            if style.step_marker == "node":  # merkez karenin ortasıdır; numara sağına çizilir
                center_x = rect.center().x() if collapsed else left_edge + NODE_SIZE // 2
            else:
                center_x = rect.center().x() if collapsed else left_edge + slot // 2
            center = QPoint(center_x, center_y)
            if style.step_marker == "node" and not horizontal:
                self._wire(painter, index, option.rect, center_x, center_y)
            state = CURRENT if selected else DONE if done else PENDING
            muted = QColor(nav_color(tokens, "nav_muted"))
            paint_marker(
                painter,
                style,
                center,
                state,
                index.row() + 1,
                done=done,
                ink=text_color,
                ground=ground,
                accent=QColor(tokens["accent"]) if enabled else muted,
                muted=muted,
                font=_bold(option.font),
            )
            dot = QPoint(center_x + 10, center_y - 8)
        if collapsed:
            state_name = str(index.data(STATE_ROLE) or "neutral")
            if index.data(BADGE_ROLE) and state_name in ("warning", "danger"):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(tokens[state_name]))
                painter.drawEllipse(dot, _DOT // 2, _DOT // 2)
            painter.restore()
            return

        font = _bold(option.font) if selected else QFont(option.font)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        right = rect.right() - _PAD
        badge = str(index.data(BADGE_ROLE) or "")
        if badge:
            state_name = str(index.data(STATE_ROLE) or "neutral")
            if not enabled or style.nav_mono or own_selection:
                badge_color = text_color
            else:
                badge_color = QColor(tokens[_BADGE_TOKENS.get(state_name, "muted")])
            painter.setPen(badge_color)
            width = metrics.horizontalAdvance(badge)
            painter.drawText(
                QRect(right - width, rect.top(), width, rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                badge,
            )
            right -= width + _GAP
        left = left_edge + slot + _GAP
        room = max(0, text_room(option.rect.width(), metrics.horizontalAdvance(badge) if badge else 0))
        painter.setPen(text_color)
        text = metrics.elidedText(str(index.data(Qt.ItemDataRole.DisplayRole)), Qt.TextElideMode.ElideRight, room)
        painter.drawText(
            QRect(left, rect.top(), room, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )
        painter.restore()


class StepNav(QListWidget):
    """Beş adımlı kenar çubuğu listesi (`objectName` = `stepNav`)."""

    #: Yazı tipi değişince (genişlik yeniden hesaplansın diye).
    preferred_width_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("stepNav")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(_StepDelegate(self))
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self._collapsed = False
        self._horizontal = False
        self._keyboard_focus = False
        for name, icon_name in STEPS:
            item = QListWidgetItem(name)
            item.setData(ICON_ROLE, icon_name)
            item.setData(BADGE_ROLE, "")
            item.setData(STATE_ROLE, "neutral")
            item.setData(DONE_ROLE, False)
            self.addItem(item)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    @property
    def horizontal(self) -> bool:
        """Üst çubukta yatay hap dizisi olarak mı çiziliyor (Gece Mavisi gibi `nav_position="top"` temalar)."""
        return self._horizontal

    @property
    def keyboard_focus(self) -> bool:
        """Odak klavyeyle (Tab ya da ok tuşları) geldi; fare tıklamasında odak işareti çizilmez."""
        return self._keyboard_focus

    def _set_keyboard_focus(self, value: bool) -> None:
        if value != self._keyboard_focus:
            self._keyboard_focus = value
            self.viewport().update()

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self._set_keyboard_focus(
            event.reason()
            in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason, Qt.FocusReason.ShortcutFocusReason)
        )

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self._set_keyboard_focus(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self._set_keyboard_focus(True)
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._set_keyboard_focus(False)
        super().mousePressEvent(event)

    def set_collapsed(self, collapsed: bool) -> None:
        """Daraltılmış hâlde yalnızca simgeler çizilir; ad ve rozet sayısı ipucuna taşınır."""
        self._collapsed = collapsed
        for step in range(self.count()):
            self._refresh_tip(step)
        self.viewport().update()

    def set_horizontal(self, horizontal: bool) -> None:
        """Yatay hap dizisine ya da dikey listeye geçer; aynı nesne kalır, sinyaller ve öğeler korunur."""
        if horizontal == self._horizontal:
            return
        self._horizontal = horizontal
        if horizontal:
            self.setFlow(QListWidget.Flow.LeftToRight)
            self.setWrapping(False)
            self.setUniformItemSizes(False)
            self.setSpacing(_PILL_SPACING)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setStyleSheet(f"QListWidget#stepNav {{ padding: 0px {_PILL_PADDING}px; }}")
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self._fit_horizontal()
        else:
            self.setFlow(QListWidget.Flow.TopToBottom)
            self.setSpacing(0)
            self.setUniformItemSizes(True)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setStyleSheet("")
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.setMinimumSize(0, 0)
            self.setMaximumSize(_QWIDGETSIZE_MAX, _QWIDGETSIZE_MAX)
        self.scheduleDelayedItemsLayout()
        self.viewport().update()

    def _fit_horizontal(self) -> None:
        """Yatay kipte listeyi hapların toplam genişliğine ve satır yüksekliğine sabitler."""
        if not self._horizontal:
            return
        widths = [
            horizontal_item_width(self.font(), self.item(i).text(), str(self.item(i).data(BADGE_ROLE) or ""))
            for i in range(self.count())
        ]
        row = max(36, QFontMetrics(self.font()).height() + 16)
        frame = 2 * self.frameWidth()
        self.setFixedSize(
            sum(widths) + 2 * _PILL_SPACING * len(widths) + 2 * _PILL_PADDING + frame,
            row + 2 * _PILL_SPACING + frame,
        )
        self.scheduleDelayedItemsLayout()

    def _refresh_tip(self, step: int) -> None:
        item = self.item(step)
        badge = str(item.data(BADGE_ROLE) or "")
        label = f"{item.text()} · {badge}" if badge else item.text()
        if item.data(DONE_ROLE):
            label = f"{label} — {DONE_SUFFIX}"
        item.setToolTip(label if self._collapsed else "")
        item.setData(Qt.ItemDataRole.AccessibleTextRole, label)

    def set_badge(self, step: int, text: str = "", state: str = "neutral") -> None:
        item = self.item(step)
        item.setData(BADGE_ROLE, text)
        item.setData(STATE_ROLE, state)
        self._refresh_tip(step)
        self._fit_horizontal()
        self.viewport().update()

    def set_done(self, step: int, done: bool) -> None:
        item = self.item(step)
        item.setData(DONE_ROLE, done)
        self._refresh_tip(step)
        self.viewport().update()

    def preferred_width(self) -> int:
        """En uzun adım adı (seçilince kalın), simge ve en geniş rozet için gereken genişlik."""
        bold = QFont(self.font())
        bold.setBold(True)
        metrics = QFontMetrics(bold)
        text = max(metrics.horizontalAdvance(self.item(i).text()) for i in range(self.count()))
        badge = max(
            [metrics.horizontalAdvance(_WIDEST_BADGE)]
            + [metrics.horizontalAdvance(str(self.item(i).data(BADGE_ROLE) or "")) for i in range(self.count())]
        )
        return max(_MIN_WIDTH, text + _fixed_width(badge) + LIST_PADDING)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._fit_horizontal()
            self.preferred_width_changed.emit()


#: Üst çubuktaki proje başlığının genişliği; çubuk dar kalırsa başlık gizlenir.
TOP_HEADER_WIDTH = 200


class TopNavBar(QWidget):
    """Üst gezinme çubuğu: solda proje başlığı, ortada yatay hap dizisi olarak aynı `StepNav` (`stepNavTop`).

    `attach` ve `detach` başlığı ve listeyi kenar çubuğundan alıp geri verir; pencere öğeleri çoğaltılmaz.
    Çubuk dar kalırsa (küçük pencere) başlık ve onu dengeleyen boşluk gizlenir, adımlar ortada kalır.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("stepNavTop")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(12, 6, 12, 6)
        self._lay.setSpacing(0)
        self._lay.addStretch(1)
        self._lay.addStretch(1)
        self._balance = QWidget()
        self._balance.setFixedWidth(TOP_HEADER_WIDTH)
        self._lay.addWidget(self._balance)
        self._header: ProjectHeader | None = None
        self._nav: StepNav | None = None

    def attach(self, header: ProjectHeader, nav: StepNav) -> None:
        self._header, self._nav = header, nav
        header.set_compact(True)
        nav.installEventFilter(
            self
        )  # rozet değişince hap dizisinin genişliği değişir; başlığın sığması yeniden bakılır
        self._lay.insertWidget(0, header)
        self._lay.insertWidget(2, nav)
        header.show()
        nav.show()
        self._fit()

    def detach(self, header: ProjectHeader, nav: StepNav) -> None:
        nav.removeEventFilter(self)
        self._lay.removeWidget(header)
        self._lay.removeWidget(nav)
        header.set_compact(False)
        self._header = self._nav = None

    def _fit(self) -> None:
        if self._header is None or self._nav is None:
            return
        room = self.width() - 24 - self._nav.width()
        roomy = room >= 2 * TOP_HEADER_WIDTH
        self._header.setVisible(roomy)
        self._balance.setVisible(roomy)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._nav and event.type() == QEvent.Type.Resize:
            self._fit()
        return False


class ProjectHeader(QWidget):
    """Kenar çubuğunun üstündeki proje adı ve oyun bilgisi (uzunsa sonu kısaltılır, tamamı ipucundadır)."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("navHeader")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 16, 8)
        lay.setSpacing(2)
        self.name_label = QLabel()
        self.name_label.setProperty("role", "navTitle")
        self.detail_label = QLabel()
        self.detail_label.setProperty("role", "muted")
        lay.addWidget(self.name_label)
        lay.addWidget(self.detail_label)
        self._lay = lay
        self._name = ""
        self._detail = ""
        self.set_project("")

    def set_compact(self, compact: bool) -> None:
        """Üst çubukta başlık dar boşluklarla ve sabit genişlikte durur; kenar çubuğunda eski boşluklar geri gelir."""
        self._lay.setContentsMargins(*((8, 2, 8, 2) if compact else (20, 16, 16, 8)))
        if compact:
            self.setFixedWidth(TOP_HEADER_WIDTH)
        else:
            self.setMinimumWidth(0)
            self.setMaximumWidth(_QWIDGETSIZE_MAX)
        self._elide()

    def set_project(self, name: str, detail: str = "") -> None:
        self._name = name
        self._detail = detail
        self.name_label.setToolTip(name)
        self.detail_label.setToolTip(detail)
        self.detail_label.setVisible(bool(detail))
        self._elide()

    def _elide(self) -> None:
        room = max(40, self.width() - 36)
        for label, full in ((self.name_label, self._name), (self.detail_label, self._detail)):
            label.setText(QFontMetrics(label.font()).elidedText(full, Qt.TextElideMode.ElideRight, room))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide()
