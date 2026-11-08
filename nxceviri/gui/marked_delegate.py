"""Çeviri tablosunun özgün/çeviri hücreleri: semboller, hiza ve kod çipleri (yalnızca çizim).

`MarkedDelegate` hücre metnini `textmarks.marked_html` ile HTML'e çevirip `QTextDocument` ile çizer. Satır modelden
`ROW_ROLE` ile alınır; metin hiçbir zaman değiştirilmez (kopyalama ve düzenleme ham metin üzerindedir).
Binlerce satırda akıcı kalmak için üretilen HTML sınırlı bir ön bellekte (en az kullanılan atılır) tutulur.

Çeviri hücresinde yazım sözlüğünde olmayan sözcüklerin altına, panelle aynı kurallarla, kırmızı dalgalı çizgi çizilir
(sözcükler yalnızca HTML üretilirken, yani yalnızca görünen hücreler için ve ön bellekten bir kez hesaplanır).
Bul ve Değiştir eşleşmeleri modelden `FIND_SPANS_ROLE` ile gelir ve sözcük düzeyinde boyanır.
Orijinal hücresine çift tıklanınca salt okunur, seçilebilir bir düzenleyici açılır (kopyalamak için).
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Collection

from PySide6.QtCore import QAbstractItemModel, QEvent, QModelIndex, QPersistentModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QFocusEvent,
    QKeyEvent,
    QPainter,
    QPalette,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import (
    QApplication,
    QPlainTextEdit,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from nxceviri.core.project import TranslationRow
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.translate.codekinds import KIND_OTHER, CodeKinds, KindOf
from nxceviri.gui.find_replace import FIND_SPANS_ROLE, FindCell
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


class _SourceViewer(QPlainTextEdit):
    """Orijinal metni gösteren salt okunur, seçilebilir düzenleyici: Ctrl+C çalışır, Esc ya da odak kaybı kapatır."""

    def __init__(self, parent: QWidget, text: str) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlainText(text)
        self.selectAll()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e: QFocusEvent) -> None:
        super().focusOutEvent(e)
        self.close()

    def closeEvent(self, e: object) -> None:
        self.deleteLater()


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
        self._spell: SpellChecker | None = None
        self._spell_extra: Collection[str] = frozenset()
        self._spell_version = 0
        self.viewer: _SourceViewer | None = None

    # --- ayarlar ---------------------------------------------------------------------------

    def configure(self, *, symbols: bool, align: str, wrap: bool) -> None:
        self.symbols, self.align, self.wrap = symbols, align, wrap

    def set_kinds(self, kinds: CodeKinds) -> None:
        self.kinds = kinds
        self._cache.clear()

    def set_spell(self, spell: SpellChecker | None, extra: Collection[str]) -> None:
        """Yazım denetleyicisi ve ek kabul edilen sözcükler (oyun sözlüğü); yalnızca çeviri hücresi kullanır."""
        self._spell, self._spell_extra = spell, extra
        self._spell_version += 1
        self._cache.clear()

    def cache_size(self) -> int:
        return len(self._cache)

    # --- üretim ----------------------------------------------------------------------------

    def html_for(self, index: _Index, *, selected: bool = False) -> str:
        row = index.data(ROW_ROLE)
        if not isinstance(row, TranslationRow):
            return ""
        text = str(getattr(row, self.field))
        tokens = current_tokens()
        spell = self._spell if self.field == "translation" else None
        cell = index.data(FIND_SPANS_ROLE)
        found = cell.spans if isinstance(cell, FindCell) else ()
        found_current = isinstance(cell, FindCell) and cell.current
        key = (
            row.id,
            self.field,
            text,
            row.source if spell else "",
            row.code_labels,
            self.symbols,
            self.wrap,
            tokens["bg"],
            tokens["accent"],
            self._spell_version if spell else 0,
            found,
            found_current,
            selected and bool(found),
        )
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        wrong = [(a, b) for a, b, _low in spell.unknown_spans(text, row.source, self._spell_extra)] if spell else ()
        markup = marked_html(
            text,
            kind_of_row(row, self.kinds),
            tokens,
            symbols=self.symbols,
            chips=True,
            single_line=not self.wrap,
            wrong=wrong,
            found=found,
            found_current=found_current,
            selected_row=selected,
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
        markup = self.html_for(index, selected=bool(option.state & QStyle.StateFlag.State_Selected))
        doc.setHtml(markup)
        if "text-decoration" in markup:
            self._waves(doc, QColor(current_tokens()["danger"]))
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        block = QTextBlockFormat()
        block.setAlignment(flag)
        cursor.mergeBlockFormat(block)
        doc.setTextWidth(max(option.rect.width() - 2 * _PAD_X, 40) if self.wrap else -1)
        return doc

    @staticmethod
    def _waves(doc: QTextDocument, color: QColor) -> None:
        """HTML'in tek çizgiyle işaretlediği yazım hatalarını dalgalı çizgiye çevirir (Qt HTML'de dalga bilmez)."""
        found: list[tuple[int, int]] = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                fmt = fragment.charFormat()
                if (
                    fmt.underlineStyle() == QTextCharFormat.UnderlineStyle.SingleUnderline
                    and fmt.underlineColor() == color
                ):
                    found.append((fragment.position(), fragment.length()))
                it += 1
            block = block.next()
        wave = QTextCharFormat()
        wave.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        wave.setUnderlineColor(color)
        for position, length in found:
            cursor = QTextCursor(doc)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(wave)

    # --- Orijinal hücresi: salt okunur, seçilebilir görünüm ---------------------------------

    def editorEvent(
        self, event: QEvent, model: QAbstractItemModel, option: QStyleOptionViewItem, index: _Index
    ) -> bool:
        """Orijinal hücresine çift tıklayınca metni kopyalanabilsin diye salt okunur bir düzenleyici açar."""
        if self.field == "source" and event.type() == QEvent.Type.MouseButtonDblClick:
            self.open_viewer(option, index)
            return True
        return super().editorEvent(event, model, option, index)

    def open_viewer(self, option: QStyleOptionViewItem, index: _Index) -> None:
        row = index.data(ROW_ROLE)
        parent = option.widget
        if not isinstance(row, TranslationRow) or parent is None:
            return
        if self.viewer is not None:
            self.viewer.close()
        viewer = _SourceViewer(parent, str(getattr(row, self.field)))
        rect = option.rect
        rect.setHeight(max(rect.height(), 6 * option.fontMetrics.height()))
        viewer.setGeometry(rect)
        viewer.show()
        viewer.setFocus()
        self.viewer = viewer
        viewer.destroyed.connect(self._viewer_gone)

    def _viewer_gone(self) -> None:
        self.viewer = None

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
