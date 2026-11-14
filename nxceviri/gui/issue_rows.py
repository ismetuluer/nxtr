"""Kontrol Et → Sorunlar: bulguları tablo yerine liste gibi gösteren görünüm ve satır çizici.

Her bulgu üç satırlık sabit yükseklikli bir kart satırıdır: (1) önem simgesi, kalın açıklama ve sağda soluk "No N",
(2) soluk orijinal metin, (3) çeviri metni. Metinler tek satıra sığmazsa sonda "…" ile kısalır; tam metin ipucundadır.
Satır yüksekliği yazı tipinden hesaplanır, içerikten ölçülmez. Kontrol kodu (`⟦n⟧`) ya da özel işaret içeren metin
çeviri tablosuyla aynı çip görünümüyle (`textmarks.marked_html`) çizilir ve taşan kısmı kırpılır; kodsuz metin düz
çizilir. Çip belgeleri sınırlı bir ön bellekte tutulur, bu yüzden binlerce bulguda kaydırma akıcı kalır.
"""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.codekinds import CodeKinds
from nxceviri.gui.icons import icon
from nxceviri.gui.marked_delegate import ROW_ROLE, kind_of_row
from nxceviri.gui.table_columns import FitTableView
from nxceviri.gui.textmarks import code_spans, marked_html, pua_spans
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.translate_page import _Editor

_Index = QModelIndex | QPersistentModelIndex

#: Modelin bu rollerde döndürdüğü satır bilgileri.
ROLE_SEVERITY = Qt.ItemDataRole.UserRole + 20  # "error" / "warning" / "info"
ROLE_SOURCE = Qt.ItemDataRole.UserRole + 21
ROLE_TRANSLATION = Qt.ItemDataRole.UserRole + 22
ROLE_NUMBER = Qt.ItemDataRole.UserRole + 23  # çeviri tablosundaki satır numarası; yoksa 0

#: Önem → (simge adı, tema rengi).
SEVERITY_MARKS = {
    "error": ("circle-x", "danger"),
    "warning": ("triangle-alert", "warning"),
    "info": ("info", "muted"),
}
ICON_SIZE = 16
_PAD_X, _PAD_Y, _LINE_GAP, _ICON_GAP = 14, 8, 2, 8
#: Çok uzun metinde kısaltma maliyeti artmasın: bu kadar karakterden fazlası zaten sığmaz.
_MAX_CHARS = 300
#: Model satır vermediğinde (kodların türü bilinmez) çiplerin kullandığı boş satır.
_NO_ROW = TranslationRow(0, "", "", "", "", "", "", (), None)


def row_height(metrics: QFontMetrics) -> int:
    """Üç metin satırı, satır araları ve dolgu; yazı tipine göre hesaplanır, içeriğe bağlı değildir."""
    return 3 * metrics.height() + 2 * _LINE_GAP + 2 * _PAD_Y + 1


def line_tops(rect: QRect, line_height: int) -> tuple[int, int, int]:
    """Satırın üç metin satırının üst kenarları."""
    first = rect.top() + _PAD_Y
    second = first + line_height + _LINE_GAP
    return first, second, second + line_height + _LINE_GAP


def one_line(text: str) -> str:
    """Satır sonlarını görünür işarete çevirip tek satıra indirir."""
    return text[:_MAX_CHARS].replace("\r", "").replace("\n", " ⏎ ")


class IssueRowDelegate(QStyledItemDelegate):
    """Bulgu satırını üç satır olarak çizer; çeviriyi yerinde düzenleme penceresi de buradadır."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kinds = CodeKinds({})
        self.cache_limit = 512
        self._cache: OrderedDict[tuple[object, ...], QTextDocument] = OrderedDict()

    def set_kinds(self, kinds: CodeKinds) -> None:
        """Proje kod türü eşlemesi (çip simgeleri ve renkleri bundan gelir)."""
        self.kinds = kinds
        self._cache.clear()

    def cache_size(self) -> int:
        return len(self._cache)

    def line_html(self, index: _Index, role: int, *, selected: bool) -> str:
        """Metin satırının çip biçimli HTML'i; kod ya da özel işaret yoksa boş döner (düz çizilir)."""
        text = one_line(str(index.data(role) or ""))
        if not code_spans(text) and not pua_spans(text):
            return ""
        row = index.data(ROW_ROLE)
        kind_of = kind_of_row(row if isinstance(row, TranslationRow) else _NO_ROW, self.kinds)
        return marked_html(
            text, kind_of, current_tokens(), symbols=False, chips=True, single_line=True, selected_row=selected
        )

    def _document(self, index: _Index, role: int, font: QFont, *, selected: bool) -> QTextDocument | None:
        tokens = current_tokens()
        row = index.data(ROW_ROLE)
        key = (
            role,
            str(index.data(role) or ""),
            row.code_labels if isinstance(row, TranslationRow) else (),
            font.key(),
            tokens["bg"],
            tokens["accent"],
            tokens["selection"],
            selected,
        )
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        markup = self.line_html(index, role, selected=selected)
        if not markup:
            return None
        doc = QTextDocument()
        doc.setDefaultFont(font)
        text_option = doc.defaultTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.NoWrap)
        doc.setDefaultTextOption(text_option)
        doc.setDocumentMargin(0)
        doc.setHtml(markup)
        self._cache[key] = doc
        while len(self._cache) > self.cache_limit:
            self._cache.popitem(last=False)
        return doc

    @staticmethod
    def _draw_document(painter: QPainter, doc: QTextDocument, rect: QRect, color: QColor) -> None:
        """Belgeyi `rect` içine, dikey ortalı ve sağda kırpılmış olarak çizer."""
        painter.save()
        painter.setClipRect(rect)
        painter.translate(rect.left(), rect.top() + (rect.height() - doc.size().height()) / 2)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(QPalette.ColorRole.Text, color)
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        return QSize(0, row_height(option.fontMetrics))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        tokens = current_tokens()
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.save()
        if selected or hovered:
            painter.fillRect(rect, QColor(tokens["selection" if selected else "surface2"]))
        painter.setPen(QColor(tokens["border"]))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        metrics = option.fontMetrics
        height = metrics.height()
        first, second, third = line_tops(rect, height)
        left = rect.left() + _PAD_X
        right = rect.right() - _PAD_X
        text_left = left + ICON_SIZE + _ICON_GAP
        severity = index.data(ROLE_SEVERITY)
        if severity in SEVERITY_MARKS:
            name, tone = SEVERITY_MARKS[severity]
            icon(name, tokens[tone], ICON_SIZE).paint(
                painter, QRect(left, first + (height - ICON_SIZE) // 2, ICON_SIZE, ICON_SIZE)
            )
        number = index.data(ROLE_NUMBER)
        no_width = 0
        if number:
            no_text = f"No {number}"
            no_width = metrics.horizontalAdvance(no_text)
            painter.setPen(QColor(tokens["muted"]))
            painter.drawText(
                QRect(right - no_width, first, no_width, height),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                no_text,
            )
        bold = QFont(option.font)
        bold.setWeight(QFont.Weight.DemiBold)
        painter.setFont(bold)
        painter.setPen(QColor(tokens["text"]))
        message_width = max(right - no_width - (_ICON_GAP if no_width else 0) - text_left, 20)
        message = QFontMetrics(bold).elidedText(str(index.data() or ""), Qt.TextElideMode.ElideRight, message_width)
        painter.drawText(
            QRect(text_left, first, message_width, height),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            message,
        )
        painter.setFont(option.font)
        width = max(right - text_left, 20)
        for top, role, tone in ((second, ROLE_SOURCE, "muted"), (third, ROLE_TRANSLATION, "text")):
            text = one_line(str(index.data(role) or ""))
            if not text:
                continue
            doc = self._document(index, role, option.font, selected=selected)
            if doc is not None:
                self._draw_document(painter, doc, QRect(text_left, top, width, height), QColor(tokens[tone]))
                continue
            painter.setPen(QColor(tokens[tone]))
            painter.drawText(
                QRect(text_left, top, width, height),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                metrics.elidedText(text, Qt.TextElideMode.ElideRight, width),
            )
        if option.state & QStyle.StateFlag.State_HasFocus and option.state & QStyle.StateFlag.State_KeyboardFocusChange:
            painter.setPen(QColor(tokens["accent"]))
            painter.drawRect(rect.adjusted(1, 1, -2, -2))
        painter.restore()

    # --- yerinde düzenleme (çeviri satırının üstünde açılır; Enter kaydeder, Shift+Enter satır sonu, Esc vazgeçer) ---

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: _Index) -> QWidget:
        editor = _Editor(parent)
        editor.setTabChangesFocus(True)
        editor.committed.connect(lambda: self._finish(editor))
        return editor

    def _finish(self, editor: _Editor) -> None:
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.NoHint)

    def setEditorData(self, editor: QWidget, index: _Index) -> None:
        assert isinstance(editor, _Editor)
        editor.setPlainText(str(index.data(Qt.ItemDataRole.EditRole) or ""))
        editor.selectAll()

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: _Index) -> None:
        assert isinstance(editor, _Editor)
        model.setData(index, editor.toPlainText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem, index: _Index) -> None:
        height = option.fontMetrics.height()
        _first, _second, third = line_tops(option.rect, height)
        left = option.rect.left() + _PAD_X + ICON_SIZE + _ICON_GAP - 4
        box = QRect(left, third - 4, option.rect.right() - _PAD_X - left + 4, 4 * height)
        editor.setGeometry(box)


class IssueRowView(FitTableView):
    """Tek sütunlu, sabit satır yüksekliğli bulgu listesi.

    Çeviri satırına (alt bölüm) çift tıklamak çeviriyi yerinde düzenler; başka yere çift tıklamak ya da Enter satırı
    çeviri ekranında açar (`doubleClicked` / `activated`). F2 her yerde düzenler.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("issueTable")
        self.row_delegate = IssueRowDelegate(self)
        self.setItemDelegate(self.row_delegate)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setShowGrid(False)
        self.setMouseTracking(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.horizontalHeader().hide()
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().hide()
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.setMinimumHeight(80)
        #: Liste boşken ortada soluk yazıyla gösterilir.
        self.empty_text = ""
        self.refit_rows()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self.empty_text and self.model() is not None and self.model().rowCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor(current_tokens()["muted"]))
            painter.drawText(
                self.viewport().rect().adjusted(24, 24, -24, -24),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
                self.empty_text,
            )
            painter.end()

    def refit_rows(self) -> None:
        """Satır yüksekliğini geçerli yazı tipine göre yeniden kurar."""
        self.verticalHeader().setDefaultSectionSize(row_height(self.fontMetrics()))

    def wheel_step(self) -> int:
        return self.verticalHeader().defaultSectionSize()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.refit_rows()

    def in_translation_band(self, pos: QPoint) -> bool:
        """`pos` (görünüm koordinatı) satırın çeviri bölümünde mi?"""
        index = self.indexAt(pos)
        if not index.isValid():
            return False
        rect = self.visualRect(index)
        _first, _second, third = line_tops(rect, self.fontMetrics().height())
        return pos.y() >= third - _LINE_GAP

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.position().toPoint())
        if (
            index.isValid()
            and self.in_translation_band(event.position().toPoint())
            and index.flags() & Qt.ItemFlag.ItemIsEditable
        ):
            self.setCurrentIndex(index)
            self.edit(index)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
