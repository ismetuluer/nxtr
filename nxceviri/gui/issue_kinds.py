"""Kontrol Et → Sorunlar: önem sırasına göre gruplanmış bulgu türü listesi.

Liste tablonun solunda durur; yalnızca bulgusu olan türleri ve bulgusu olan grupları gösterir. Seçim tablonun süzgecini
belirler: bir tür seçilince yalnızca o tür, Ctrl/Shift ile birkaç tür, grup başlığına tıklayınca grubun tüm türleri,
"Tüm bulgular" ya da hiçbiri seçili değilse süzgeç yok.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_ERROR
from nxceviri.gui.icons import icon
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import format_int, tip_html

#: Sunum bilgisi: türlerin önem grupları ve sırası (tür adları `KIND_LABELS`'tan gelir).
KIND_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Oyunu bozabilir",
        ("placeholder", "code_position", "newlines", "markup", "missing_markup", "identifier", "protected", "glyph"),
    ),
    ("Ekrana sığmayabilir", ("max_length", "line_too_long", "page_too_tall", "overflow", "bad_break", "too_wide")),
    ("Dil ve tutarlılık", ("glossary", "term", "inconsistent", "suspicious", "code_order", "spelling", "untranslated")),
    (
        "Küçük düzeltmeler",
        (
            "ascii_turkish",
            "end_punctuation",
            "spaces",
            "double_space",
            "repeated_word",
            "extra_dots",
            "space_before_punct",
        ),
    ),
)
#: Eşlemede olmayan (sonradan eklenen) türlerin düştüğü grup.
OTHER_GROUP = "Diğer"
ALL_TITLE = "Tüm bulgular"
#: Bilgi düzeyindeki öneriler (ör. yazım) "Tüm bulgular" sayısına girmez ve onda listelenmez; bunu söyleyen ipucu.
_INFO_NOT_COUNTED = "Bilgi önerileri (ör. yazım) bu sayıya girmez; görmek için türünü soldan seçin."
EMPTY_TEXT = "Bulunan sorunların türleri burada listelenir."
#: "Yok sayılanlar" girişinin sahte türü: seçilince tablo yok sayılan bulguları gösterir (başka türle karışmaz).
IGNORED_KIND = "ignored"
IGNORED_TITLE = "Yok sayılanlar"
LIST_WIDTH = 232

_ROLE_TYPE = Qt.ItemDataRole.UserRole + 1
_ROLE_KIND = Qt.ItemDataRole.UserRole + 2
_ROLE_COUNT = Qt.ItemDataRole.UserRole + 3
_ROLE_ERROR = Qt.ItemDataRole.UserRole + 4
_TYPE_ALL, _TYPE_GROUP, _TYPE_KIND = "all", "group", "kind"
_ICON_SIZE = 14
_SIDE = 10
#: Denetim sürerken listenin soluklığı.
_WAITING_OPACITY = 0.45


def _label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


class KindList(QListWidget):
    """Gruplu tür listesi: "Tüm bulgular", grup başlıkları ve bulgusu olan türler (ad + sayı)."""

    #: Seçilen türler değişti (süzgeç yeniden uygulanmalı).
    selection_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("kindList")
        self.setAccessibleName("Bulgu türleri")
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setItemDelegate(_KindDelegate(self))
        self.setFixedWidth(LIST_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.empty_text = EMPTY_TEXT
        #: Denetim sürüyor: sayılar henüz doğru değil, liste soluk ve tıklanamaz görünür.
        self.waiting = False
        self._busy = False
        self._all_was_selected = True
        self._last: frozenset[str] = frozenset()
        self._total = 0
        self._counts: dict[str, int] = {}
        self._errors: set[str] = set()
        self._kind_items: dict[str, QListWidgetItem] = {}
        self._group_items: dict[str, QListWidgetItem] = {}
        self._group_kinds: dict[str, list[str]] = {}
        self.itemSelectionChanged.connect(self._selection_changed)
        self.set_counts({}, {}, 0)

    # --- içerik -------------------------------------------------------------------------

    def set_counts(
        self, counts: Mapping[str, int], severities: Mapping[str, str], total: int, ignored: int = 0, info: int = 0
    ) -> None:
        """Listeyi yeniden kurar; bulgusu kalmayan türün seçimi bırakılır, kalan seçim korunur.

        `ignored`: yok sayılan bulgu sayısı; sıfırdan büyükse listenin sonuna "Yok sayılanlar" girişi eklenir.
        `info`: bilgi düzeyindeki bulgu sayısı; `total`a girmez, sıfırdan büyükse "Tüm bulgular" bunu ipucuyla söyler.
        """
        previous = self._last
        scroll = self.verticalScrollBar().value()
        self._busy = True
        try:
            self.clear()
            self._kind_items.clear()
            self._group_items.clear()
            self._group_kinds.clear()
            self._counts = {k: n for k, n in counts.items() if n > 0}
            self._errors = {k for k in self._counts if severities.get(k) == SEVERITY_ERROR}
            self._total = total
            self.all_item = self._add(ALL_TITLE, _TYPE_ALL, total, "")
            if info > 0:
                self.all_item.setToolTip(tip_html(_INFO_NOT_COUNTED))
            known = {k for _title, kinds in KIND_GROUPS for k in kinds}
            others = [k for k in self._counts if k not in known]
            groups = [*KIND_GROUPS, (OTHER_GROUP, tuple(others))]
            for title, kinds in groups:
                present = [k for k in kinds if k in self._counts]
                if not present:
                    continue
                self._group_items[title] = self._add(title, _TYPE_GROUP, 0, "")
                self._group_kinds[title] = present
                for kind in present:
                    self._kind_items[kind] = self._add(_label(kind), _TYPE_KIND, self._counts[kind], kind)
            selectable = set(self._counts)
            if ignored > 0:
                item = self._add(IGNORED_TITLE, _TYPE_KIND, ignored, IGNORED_KIND)
                item.setToolTip(
                    tip_html("Yok saydığınız bulgular. Birini seçip sağ tıklayarak yok saymayı kaldırabilirsiniz.")
                )
                self._kind_items[IGNORED_KIND] = item
                selectable.add(IGNORED_KIND)
            kept = previous & selectable
            self._apply(kept)
            self._all_was_selected = not kept
            self._last = frozenset(kept)
        finally:
            self._busy = False
        self.verticalScrollBar().setValue(scroll)
        self.viewport().update()
        if kept != previous:
            self.selection_changed.emit()

    def _add(self, text: str, kind_type: str, count: int, kind: str) -> QListWidgetItem:
        item = QListWidgetItem(text)
        item.setData(_ROLE_TYPE, kind_type)
        item.setData(_ROLE_KIND, kind)
        item.setData(_ROLE_COUNT, count)
        item.setData(_ROLE_ERROR, kind in self._errors)
        if kind_type == _TYPE_GROUP:
            item.setData(Qt.ItemDataRole.AccessibleTextRole, f"Grup: {text}")
        else:
            item.setData(Qt.ItemDataRole.AccessibleTextRole, f"{text}, {format_int(count)} bulgu")
        if kind_type == _TYPE_KIND:
            hint = "Bu türdeki bulguları göster. Ctrl ile birden çok tür seçilebilir."
            item.setToolTip(tip_html(hint))
        self.addItem(item)
        return item

    def set_waiting(self, waiting: bool) -> None:
        """Denetim sürerken sayılar "—" olur, boş durum yazısı gizlenir, liste soluklaşır ve tıklanamaz."""
        self.waiting = waiting
        self.setEnabled(not waiting)
        self.viewport().update()

    # --- sorgular -----------------------------------------------------------------------

    def kind_item(self, kind: str) -> QListWidgetItem:
        return self._kind_items[kind]

    def group_item(self, title: str) -> QListWidgetItem:
        return self._group_items[title]

    def visible_kinds(self) -> list[str]:
        return list(self._kind_items)

    def count_of(self, kind: str) -> int:
        return self._counts.get(kind, 0)

    def total(self) -> int:
        return self._total

    def has_errors(self, kind: str) -> bool:
        return kind in self._errors

    def is_empty(self) -> bool:
        return not self._kind_items

    def selected_kinds(self) -> frozenset[str]:
        return self._last

    # --- seçim --------------------------------------------------------------------------

    def select_kinds(self, kinds: Collection[str]) -> None:
        """Seçimi verilen türlere ayarlar (listede olmayanlar yok sayılır; hiçbiri kalmazsa süzgeç kalkar)."""
        wanted = frozenset(kinds) & (self._counts.keys() | self._kind_items.keys() & {IGNORED_KIND})
        self._busy = True
        try:
            self._apply(wanted)
        finally:
            self._busy = False
        self._all_was_selected = not wanted
        self._commit(wanted)
        first = next((self._kind_items[k] for k in self._kind_items if k in wanted), None)
        if first is not None:
            self.scrollToItem(first)

    def _apply(self, kinds: Collection[str]) -> None:
        """Seçili öğeleri tam olarak `kinds` yapar; boşsa "Tüm bulgular" seçili görünür."""
        self.clearSelection()
        for kind in kinds:
            self._kind_items[kind].setSelected(True)
        if not kinds:
            self.all_item.setSelected(True)

    def _commit(self, kinds: frozenset[str]) -> None:
        if kinds != self._last:
            self._last = kinds
            self.selection_changed.emit()

    def _selection_changed(self) -> None:
        """Kullanıcı seçimi: başlık tıklaması grubun türlerine, "Tüm bulgular" tıklaması boş seçime dönüşür."""
        if self._busy:
            return
        kinds: set[str] = set()
        all_selected = False
        for item in self.selectedItems():
            kind_type = item.data(_ROLE_TYPE)
            if kind_type == _TYPE_ALL:
                all_selected = True
            elif kind_type == _TYPE_GROUP:
                kinds.update(self._group_kinds[item.text()])
            else:
                kinds.add(str(item.data(_ROLE_KIND)))
        if all_selected and kinds and not self._all_was_selected:
            kinds.clear()  # "Tüm bulgular" seçildi: öteki seçimler kalkar
        if IGNORED_KIND in kinds and len(kinds) > 1:
            # Yok sayılanlar öteki türlerle karışmaz: yeni seçilen kazanır.
            kinds = {IGNORED_KIND} if IGNORED_KIND not in self._last else kinds - {IGNORED_KIND}
        self._all_was_selected = not kinds
        self._busy = True
        try:
            self._apply(kinds)
        finally:
            self._busy = False
        self._commit(frozenset(kinds))

    # --- çizim --------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if not self.is_empty() or self.waiting:
            return
        tokens = current_tokens()
        painter = QPainter(self.viewport())
        painter.setPen(QColor(tokens["muted"]))
        top = self.visualItemRect(self.all_item).bottom() + 14
        area = QRect(_SIDE + 4, top, self.viewport().width() - 2 * (_SIDE + 4), 90)
        painter.drawText(
            area,
            int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
            self.empty_text,
        )
        painter.end()


class _KindDelegate(QStyledItemDelegate):
    """Satırları kendisi çizer: başlıklar soluk ve küçük, türler ad + sağda sayı; seçili satır `selection` zeminli."""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        height = option.fontMetrics.height()
        if index.data(_ROLE_TYPE) == _TYPE_GROUP:
            return QSize(0, height + 16)
        return QSize(0, height + 10)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        tokens = current_tokens()
        kind_type = index.data(_ROLE_TYPE)
        waiting = isinstance(option.widget, KindList) and option.widget.waiting
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if waiting:
            painter.setOpacity(_WAITING_OPACITY)
        rect = option.rect.adjusted(4, 1, -4, -1)
        if kind_type == _TYPE_GROUP:
            font = QFont(option.font)
            font.setPointSizeF(max(option.font.pointSizeF() * 0.85, 7.0))
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            painter.setPen(QColor(tokens["muted"]))
            text_rect = rect.adjusted(_SIDE - 2, 6, 0, 0)
            painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), index.data())
            painter.restore()
            return
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens["selection" if selected else "surface2"]))
            painter.drawRoundedRect(rect, 6, 6)
        left = rect.left() + _SIDE - 2
        if index.data(_ROLE_ERROR):
            mark = icon("circle-x", tokens["danger"], _ICON_SIZE)
            mark.paint(painter, QRect(left, rect.center().y() - _ICON_SIZE // 2 + 1, _ICON_SIZE, _ICON_SIZE))
        text_left = left + _ICON_SIZE + 6 if kind_type == _TYPE_KIND else left
        count = "—" if waiting else f"{format_int(int(index.data(_ROLE_COUNT)))}"
        count_width = painter.fontMetrics().horizontalAdvance(count)
        right = rect.right() - _SIDE + 2
        painter.setPen(QColor(tokens["text"] if selected else tokens["muted"]))
        painter.drawText(
            QRect(right - count_width, rect.top(), count_width, rect.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
            count,
        )
        painter.setPen(QColor(tokens["text"]))
        name_width = right - count_width - 8 - text_left
        name = painter.fontMetrics().elidedText(index.data(), Qt.TextElideMode.ElideRight, max(name_width, 20))
        painter.drawText(
            QRect(text_left, rect.top(), max(name_width, 20), rect.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            name,
        )
        if option.state & QStyle.StateFlag.State_HasFocus and option.state & QStyle.StateFlag.State_KeyboardFocusChange:
            painter.setPen(QColor(tokens["accent"]))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)
        painter.restore()
