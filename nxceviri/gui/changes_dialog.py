"""Çeviri değişikliklerini gösterme ve geri alma: son işin değişiklikleri ve bir satırın geçmişi."""

from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QPersistentModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QAbstractTextDocumentLayout, QPainter, QPalette, QShowEvent, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.errors import NxError
from nxceviri.core.project import Change
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.diff import ADDED, REMOVED, word_diff
from nxceviri.core.translate.report import job_label, write_changes
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import Banner, button, format_int, label, title_row

_Index = QModelIndex | QPersistentModelIndex
#: Satır yüksekliği bu kadar satırdan fazlasında içeriğe göre ölçülmez (büyük işlerde pencere hızlı açılsın).
_MEASURE_LIMIT = 1500
#: Önizlemede düzenlenebilir “Yeni” metninin tutulduğu rol (hücrede çizilen HTML farkından ayrı).
NEW_TEXT_ROLE = Qt.ItemDataRole.UserRole + 1
#: Önizlemede “Yeni” sütununun sırası (Yaz, Satır, Orijinal, Önceki, Yeni).
_PREVIEW_NEW_COL = 4


def diff_html(old: str, new: str) -> tuple[str, str]:
    """Önceki ve yeni çevirinin HTML'i: silinenler kırmızı ve üstü çizili, eklenenler yeşil."""
    t = current_tokens()
    left, right = word_diff(old, new)

    def render(parts: list[tuple[str, str]]) -> str:
        out = []
        for kind, text in parts:
            body = html.escape(text).replace("\n", "<br>")
            if kind == REMOVED:
                out.append(f'<span style="background:{t["danger_bg"]};color:{t["danger"]}"><s>{body}</s></span>')
            elif kind == ADDED:
                out.append(f'<span style="background:{t["success_bg"]};color:{t["success"]}"><b>{body}</b></span>')
            else:
                out.append(body)
        return "".join(out)

    return render(left), render(right)


class HtmlDelegate(QStyledItemDelegate):
    """Hücre metnini HTML olarak çizer (fark vurguları için)."""

    def _document(self, option: QStyleOptionViewItem, index: _Index) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setHtml(str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
        doc.setTextWidth(max(option.rect.width() - 8, 40))
        return doc

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _Index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = self._document(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        painter.save()
        painter.translate(opt.rect.left() + 4, opt.rect.top() + 3)
        painter.setClipRect(QRectF(0, 0, opt.rect.width() - 4, opt.rect.height() - 3))
        ctx = QAbstractTextDocumentLayout.PaintContext()
        if opt.state & QStyle.StateFlag.State_Selected:
            ctx.palette.setColor(QPalette.ColorRole.Text, opt.palette.color(QPalette.ColorRole.HighlightedText))
        else:
            ctx.palette.setColor(QPalette.ColorRole.Text, opt.palette.color(QPalette.ColorRole.Text))
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = self._document(opt, index)
        return QSize(int(doc.idealWidth()) + 8, int(doc.size().height()) + 6)


class EditableDiffDelegate(HtmlDelegate):
    """HTML farkını çizer; düzenlemeye açılınca hücrenin düz metnini (satır sonlarıyla) düzenletir.

    Hücrede renkli fark görünür ama düzenleyiciye HTML değil, `NEW_TEXT_ROLE` içindeki gerçek çeviri metni
    gider. Böylece kullanıcı yeni düzeltmeyi olduğu gibi yazabilir; çok satırlı metinlerde Enter yeni satır açar.
    """

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: _Index) -> QWidget:
        editor = QPlainTextEdit(parent)
        editor.setTabChangesFocus(True)  # Tab düzenlemeyi bitirip sonraki hücreye geçer
        editor.setMinimumHeight(option.rect.height())
        return editor

    def setEditorData(self, editor: QWidget, index: _Index) -> None:
        if isinstance(editor, QPlainTextEdit):
            editor.setPlainText(str(index.data(NEW_TEXT_ROLE) or ""))

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: _Index) -> None:
        if isinstance(editor, QPlainTextEdit):
            model.setData(index, editor.toPlainText(), NEW_TEXT_ROLE)
        else:
            super().setModelData(editor, model, index)


#: "Satır" sütununun en çok genişliği (piksel).
_NAME_COLUMN_MAX = 240


class _SingleLineDelegate(QStyledItemDelegate):
    """Tek satır, baştan kısaltılmış metin (anahtarın sonu önemli)."""

    def initStyleOption(self, option: QStyleOptionViewItem, index: _Index) -> None:
        super().initStyleOption(option, index)
        option.textElideMode = Qt.TextElideMode.ElideLeft
        option.features &= ~QStyleOptionViewItem.ViewItemFeature.WrapText

    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), option.fontMetrics.height() + 8)


class ChangesDialog(QDialog):
    """Değişiklik listesi; işaretlenenler (veya geçmişte seçilen sürüm) geri alınır.

    `history=False`: bir işin değişiklikleri, her satır işaretlenebilir, "Seçilenleri Geri Al".
    `history=True`: tek satırın geçmişi (en yeni üstte), seçilen değişiklikten önceki hâle dönülür.
    `preview=True`: henüz yazılmamış değişiklikler yalnızca gösterilir; "Çevirilere Yaz" ile onaylanır.
    `kinds`: satır kimliği → o satıra uygulanan düzeltme türleri; verilirse sondaki “Düzeltme” sütununda gösterilir.
    Pencere `Accepted` ile kapanırsa geri alınacaklar `to_revert` içindedir (önizlemede boştur).
    """

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        changes: list[Change],
        *,
        history: bool = False,
        preview: bool = False,
        summary: Sequence[str] = (),
        kinds: Mapping[int, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1100, 640)
        self._changes = changes
        self._history = history
        self._preview = preview
        self._title = title
        self._texts = [c.new_text for c in changes]  # önizlemede düzenlenmiş “Yeni” metinleri
        self._updating = False
        self.to_revert: list[Change] = []
        self._boxes: list[QTableWidgetItem] = []  # “Yaz”/“Geri al” işaret kutuları, değişikliklerle aynı sırada
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        if history:
            info = (
                "Bu satırın çevirisindeki değişiklikler, en yenisi üstte. Birini seçip “Bu Değişiklikten Önceki "
                "Hâle Dön” derseniz satır o değişiklikten önceki metne ve duruma döner."
            )
        elif preview:
            info = (
                "Kırmızı sözcükler çıkarılan, yeşil sözcükler eklenen kısımlardır. Beğenmediğiniz satırın “Yaz” "
                "işaretini kaldırın; “Çevirilere Yaz” demeden hiçbir şey değişmez."
            )
        else:
            info = (
                "Kırmızı sözcükler çıkarılan, yeşil sözcükler eklenen kısımlardır. Beğenmediğiniz satırları "
                "işaretleyip geri alabilirsiniz."
            )
        lay.addWidget(title_row(title, info, "cardTitle"))
        lay.addWidget(label(f"{format_int(len(changes))} değişiklik", "muted"))
        if summary:
            notes = label("\n".join(summary), "muted", wrap=True)
            notes.setObjectName("importSummary")
            lay.addWidget(notes)
        if history:
            headers = ["Ne zaman", "İş", "Önceki", "Yeni"]
        elif preview:
            headers = ["Yaz", "Satır", "Orijinal", "Önceki", "Yeni"]
        else:
            headers = ["Geri al", "Satır", "Orijinal", "Önceki", "Yeni"]
            if kinds is not None:
                headers.append("Düzeltme")
        self.table = QTableWidget(len(changes), len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().hide()
        self.table.setWordWrap(True)
        if preview:  # yalnızca “Yeni” hücresi düzenlenebilir (aşağıda ItemIsEditable verilir)
            self.table.setEditTriggers(
                QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
            )
        else:
            self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
            if history or preview
            else QAbstractItemView.SelectionMode.ExtendedSelection
        )
        delegate = HtmlDelegate(self.table)
        diff_cols = (2, 3) if history else (3, 4)
        name_col = 1
        for col in diff_cols:
            self.table.setItemDelegateForColumn(col, delegate)
        if preview:
            self.table.setItemDelegateForColumn(_PREVIEW_NEW_COL, EditableDiffDelegate(self.table))
        for row, change in enumerate(changes):
            old_html, new_html = diff_html(change.old_text, change.new_text)
            if history:
                cells = [change.created_at.replace("T", " ")[:16], job_label(change.job), old_html, new_html]
            else:
                cells = ["", change.label, change.source, old_html, new_html]
                if kinds is not None and not preview:
                    cells.append(kinds.get(change.entry_id, ""))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if preview and col != 0:
                    # Diğer hücreler düzenlenemez; yalnızca “Yeni” metni değiştirilebilir.
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if col == name_col:
                    item.setToolTip(change.label)  # uzun anahtarın tamamı; hücrede sonu görünür
                if col == name_col + 1:
                    item.setToolTip(change.source)
                if col == 0 and not history:
                    item.setFlags(
                        Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                    )
                    item.setCheckState(Qt.CheckState.Checked if preview else Qt.CheckState.Unchecked)
                    if preview:
                        item.setToolTip(
                            "Bu satırın düzeltmesini yaz. İşareti kaldırırsanız satırın mevcut çevirisi korunur."
                        )
                    self._boxes.append(item)
                if preview and col == _PREVIEW_NEW_COL:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    item.setData(NEW_TEXT_ROLE, change.new_text)
                    item.setToolTip(
                        "Düzenlemek için çift tıklayın veya F2'ye basın. Satır sonu için Enter; bitirmek için "
                        "hücre dışına tıklayın."
                    )
                self.table.setItem(row, col, item)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        # "Satır"/"İş" sütunu sabit genişlikte ve tek satır: uzun bir anahtar (ör. Despelote'nin yol biçimli
        # anahtarları) metin sütunlarını birkaç piksele sıkıştırmasın. Anahtarın sonu görünür, tamamı ipucunda.
        h.setSectionResizeMode(name_col, QHeaderView.ResizeMode.Interactive)
        self.table.setItemDelegateForColumn(name_col, _SingleLineDelegate(self.table))
        self.table.resizeColumnToContents(name_col)
        h.resizeSection(name_col, min(h.sectionSize(name_col), _NAME_COLUMN_MAX))
        for col in range(name_col + 1, len(headers)):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        if kinds is not None and not history and not preview:
            h.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        if not history:
            check_all = button("Tümünü Yaz" if preview else "Tümünü İşaretle")
            check_all.clicked.connect(lambda: self._check_all(Qt.CheckState.Checked))
            check_none = button("Hiçbirini Yazma" if preview else "İşaretleri Kaldır")
            check_none.clicked.connect(lambda: self._check_all(Qt.CheckState.Unchecked))
            buttons.addWidget(check_all)
            buttons.addWidget(check_none)
            if not preview:
                check_selected = button("Seçili Satırları İşaretle")
                check_selected.clicked.connect(self._check_selected)
                buttons.addWidget(check_selected)
        if not preview:
            export = button("Dışa Aktar…")
            export.setToolTip("Değişiklikleri Excel'de açılan CSV veya tarayıcıda açılan renkli HTML olarak kaydeder.")
            export.clicked.connect(self._choose_export)
            buttons.addWidget(export)
        buttons.addStretch(1)
        if preview:
            self.revert_button = button("Çevirilere Yaz", "primary")
            self.revert_button.setToolTip("Değişiklikleri “Redakte” durumuyla yazar; Ctrl+Z ile geri alınabilir.")
            self.revert_button.clicked.connect(self.accept)
        else:
            self.revert_button = button(
                "Bu Değişiklikten Önceki Hâle Dön" if history else "İşaretlileri Geri Al", "primary"
            )
            self.revert_button.clicked.connect(self._revert)
        close = button("Vazgeç" if preview else "Kapat")
        close.clicked.connect(self.reject)
        buttons.addWidget(self.revert_button)
        buttons.addWidget(close)
        lay.addLayout(buttons)
        self.status = Banner()
        lay.addWidget(self.status)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._update_button)
        self._update_button()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Önizlemede düzenlenen “Yeni” metnini saklar ve hücredeki renkli farkı tazeler."""
        if self._updating:
            self._update_button()
            return
        if self._preview:
            if item.column() == _PREVIEW_NEW_COL:
                row = item.row()
                text = str(item.data(NEW_TEXT_ROLE) or "")
                self._texts[row] = text
                self._updating = True
                item.setText(diff_html(self._changes[row].old_text, text)[1])
                self._updating = False
                self.table.resizeRowToContents(row)
            self.status.show_message("", "")  # önceki uyarı (boş/kontrol kodu) güncel değil
        self._update_button()

    def _choose_export(self) -> None:
        name = re.sub(r"[^\w\- ]+", "", self._title).strip() or "degisiklikler"
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Değişiklikleri dışa aktar",
            str(Path.home() / f"{name}.csv"),
            "Excel için CSV (*.csv);;Renkli karşılaştırma sayfası (*.html)",
        )
        if path:
            self.export_to(Path(path))

    def export_to(self, path: Path) -> None:
        """Listedeki bütün değişiklikleri dosyaya yazar (uzantı .html ise renkli sayfa, değilse CSV)."""
        try:
            write_changes(path, self._changes, self._title)
        except NxError as exc:
            self.status.show_message("danger", exc.user_text())
            return
        self.status.show_message("success", f"{format_int(len(self._changes))} değişiklik kaydedildi: {path}")

    def showEvent(self, event: QShowEvent) -> None:
        """Satır yükseklikleri sütunlar son genişliğini aldıktan sonra ölçülür (önce ölçülürse dar sütuna göre
        hesaplanıp gereksiz uzun olur)."""
        super().showEvent(event)
        if len(self._changes) <= _MEASURE_LIMIT:
            self.table.resizeRowsToContents()

    def _check_all(self, state: Qt.CheckState) -> None:
        for row in range(self.table.rowCount()):
            self._boxes[row].setCheckState(state)

    def _check_selected(self) -> None:
        for index in self.table.selectionModel().selectedRows():
            self._boxes[index.row()].setCheckState(Qt.CheckState.Checked)

    def selected_changes(self) -> list[Change]:
        if self._history:
            rows = [i.row() for i in self.table.selectionModel().selectedRows()]
            return [self._changes[r] for r in rows]
        return [
            c for c, box in zip(self._changes, self._boxes, strict=True) if box.checkState() == Qt.CheckState.Checked
        ]

    def accepted_changes(self) -> list[Change]:
        """Önizlemede yazılacak işaretli satırlar; “Yeni” sütunundaki düzenlemeler uygulanmış hâlde.

        Önizleme dışında `selected_changes()` ile aynıdır. İşareti kaldırılan satırlar dönmez; metni boş
        bırakılanlar da döner ve `accept()` bunları yazmadan önce uyarır.
        """
        if not self._preview:
            return self.selected_changes()
        return [
            replace(change, new_text=self._texts[i])
            for i, (change, box) in enumerate(zip(self._changes, self._boxes, strict=True))
            if box.checkState() == Qt.CheckState.Checked
        ]

    def _write_count(self) -> int:
        """Gerçekten değişecek işaretli satır sayısı (boş ya da öncekiyle aynı olanlar sayılmaz)."""
        return sum(
            1
            for i, box in enumerate(self._boxes)
            if box.checkState() == Qt.CheckState.Checked
            and self._texts[i].strip()
            and self._texts[i] != self._changes[i].old_text
        )

    def _preview_problems(self) -> list[str]:
        """Kabul edilen satırlarda yazmayı engelleyen sorunlar (boş metin, uymayan kontrol kodu)."""
        problems: list[str] = []
        for i, box in enumerate(self._boxes):
            if box.checkState() != Qt.CheckState.Checked:
                continue
            change = self._changes[i]
            text = self._texts[i]
            if not text.strip():
                problems.append(f"• {change.label}: düzeltme boş. Yazmayacaksanız “Yaz” işaretini kaldırın.")
                continue
            if text == change.old_text:
                continue  # yazılmayacak (eski çeviriyle aynı) satırın kodları denetlenmez
            fixed = placeholders.repair(change.source, text)
            issues = placeholders.problems(change.source, fixed)
            if issues:
                problems.append(f"• {change.label}: {' '.join(issues)}")
        return problems

    def accept(self) -> None:
        if self._preview:
            problems = self._preview_problems()
            if problems:
                text = "Bu satırlar yazılamaz:\n" + "\n".join(problems[:8])
                if len(problems) > 8:
                    text += f"\n… ve {format_int(len(problems) - 8)} satır daha."
                self.status.show_message("danger", text)
                return
            if not self._write_count():
                self.status.show_message(
                    "warning",
                    "Yazılacak değişiklik kalmadı. En az bir satırı işaretleyip “Yeni” metnini düzeltin veya "
                    "“Vazgeç”e basın.",
                )
                return
        super().accept()

    def _update_button(self) -> None:
        if self._preview:
            n = self._write_count()
            self.revert_button.setEnabled(n > 0)
            self.revert_button.setText(f"Çevirilere Yaz ({format_int(n)})")
            self.revert_button.setToolTip(
                "Değişiklikleri “Redakte” durumuyla yazar; Ctrl+Z ile geri alınabilir."
                if n
                else "Yazılacak değişiklik yok: en az bir satırı işaretleyin ve “Yeni” metnini düzeltin."
            )
            return
        n = len(self.selected_changes())
        self.revert_button.setEnabled(n > 0)
        if not self._history:
            self.revert_button.setText(f"İşaretlileri Geri Al ({format_int(n)})")

    def _revert(self) -> None:
        self.to_revert = self.selected_changes()
        if self.to_revert:
            self.accept()
