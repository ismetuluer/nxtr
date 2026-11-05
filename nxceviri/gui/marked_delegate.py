"""Çeviri tablosunun özgün/çeviri hücreleri: semboller, hiza ve kod çipleri (yalnızca çizim).

`MarkedDelegate` hücre metnini `textmarks.marked_html` ile HTML'e çevirip `QTextDocument` ile çizer. Satır modelden
`ROW_ROLE` ile alınır; metin hiçbir zaman değiştirilmez (kopyalama ve düzenleme ham metin üzerindedir).
Binlerce satırda akıcı kalmak için üretilen HTML sınırlı bir ön bellekte (en az kullanılan atılır) tutulur.
"""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QPainter,
    QPalette,
    QTextBlockFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.codekinds import KIND_OTHER, CodeKinds, KindOf
from nxceviri.gui.textmarks import marked_html
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.view_actions import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT

#: Modelin bu rolde döndürdüğü `TranslationRow`.
ROW_ROLE = Qt.ItemDataRole.UserRole + 10

_Index = QModelIndex | QPersistentModelIndex
_ALIGNMENTS = {
    ALIGN_LEFT: Qt.AlignmentFlag.AlignLeft,
    ALIGN_CENTER: Qt.AlignmentFlag.AlignHCenter,
    ALIGN_RIGHT: Qt.AlignmentFlag.AlignRight,
}
_PAD_X = 4
_PAD_Y = 3


def kind_of_row(row: TranslationRow, kinds: CodeKinds) -> KindOf:
    """Satırın `⟦n⟧` kodlarının türü (etiket listesinde olmayan numara `diğer`)."""
    labels = row.code_labels

    def kind_of(number: int) -> str:
        return kinds.kind_of(labels[number - 1]) if 0 < number <= len(labels) else KIND_OTHER

    return kind_of


class MarkedDelegate(QStyledItemDelegate):
    """`field` ("source" veya "translation") alanını işaretli metin olarak çizer."""

    def __init__(self, parent: QWidget | None, field: str) -> None:
        super().__init__(parent)
        self.field = field
        self.symbols = False
        self.align = ALIGN_LEFT
        self.wrap = True
        self.kinds = CodeKinds({})
        self.cache_limit = 4096
        self._cache: OrderedDict[tuple[object, ...], str] = OrderedDict()

    # --- ayarlar ---------------------------------------------------------------------------

    def configure(self, *, symbols: bool, align: str, wrap: bool) -> None:
        self.symbols, self.align, self.wrap = symbols, align, wrap

    def set_kinds(self, kinds: CodeKinds) -> None:
        self.kinds = kinds
        self._cache.clear()

    def cache_size(self) -> int:
        return len(self._cache)

    # --- üretim ----------------------------------------------------------------------------

    def html_for(self, index: _Index) -> str:
        row = index.data(ROW_ROLE)
        if not isinstance(row, TranslationRow):
            return ""
        text = str(getattr(row, self.field))
        tokens = current_tokens()
        key = (row.id, self.field, text, row.code_labels, self.symbols, self.wrap, tokens["bg"], tokens["accent"])
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        markup = marked_html(
            text, kind_of_row(row, self.kinds), tokens, symbols=self.symbols, chips=True, single_line=not self.wrap
        )
        self._cache[key] = markup
        while len(self._cache) > self.cache_limit:
            self._cache.popitem(last=False)
        return markup

    def text_color(self, option: QStyleOptionViewItem, index: _Index) -> QColor:
        """Metin rengi: seçiliyse vurgu üstü renk, değilse satırın sorun rengi, yoksa varsayılan."""
        if option.state & QStyle.StateFlag.State_Selected:
            return option.palette.color(QPalette.ColorRole.HighlightedText)
        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        if isinstance(brush, QColor):
            return brush
        return option.palette.color(QPalette.ColorRole.Text)

    def document(self, option: QStyleOptionViewItem, index: _Index) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        text_option = doc.defaultTextOption()
        flag = _ALIGNMENTS.get(self.align, Qt.AlignmentFlag.AlignLeft)
        text_option.setAlignment(flag)
        text_option.setWrapMode(
            QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere if self.wrap else QTextOption.WrapMode.NoWrap
        )
        doc.setDefaultTextOption(text_option)
        doc.setHtml(self.html_for(index))
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        block = QTextBlockFormat()
        block.setAlignment(flag)
        cursor.mergeBlockFormat(block)
        doc.setTextWidth(max(option.rect.width() - 2 * _PAD_X, 40) if self.wrap else -1)
        return doc

    # --- çizim -----------------------------------------------------------------------------

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = self.document(opt, index)
        color = self.text_color(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        painter.save()
        painter.translate(opt.rect.left() + _PAD_X, opt.rect.top() + _PAD_Y)
        painter.setClipRect(QRectF(0, 0, opt.rect.width() - _PAD_X, opt.rect.height() - _PAD_Y))
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(QPalette.ColorRole.Text, color)
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = self.document(opt, index)
        return QSize(int(doc.idealWidth()) + 2 * _PAD_X, int(doc.size().height()) + 2 * _PAD_Y)
