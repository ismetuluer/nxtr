"""Dış redaksiyon ve dış çeviri dosyalarını içe aktarma penceresi: dosyalar, sonuç ve satır listesi tek pencerede.

Sol panel dosyaları ve sonucu (kaç satır değişir, kaçı yazılmaz) gösterir; sağda yazılacak satırlar sanal bir
tabloda, önceki ve yeni metin farkıyla listelenir. Kodu uymayan satırlar listelenir ama yazılamaz. Pencere
`Accepted` ile kapanırsa yazılacak satırlar `accepted_changes()` içindedir; yazma işini çağıran yapar.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSettings,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.project import Change, TranslationRow
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.csvio import (
    CsvError,
    CsvPlan,
    CsvRow,
    ImportFile,
    describe_import,
    plan_import_files,
    read_revision_file,
)
from nxceviri.gui.changes_dialog import (
    CONTEXT_KEY,
    NEW_TEXT_ROLE,
    EditableDiffDelegate,
    HtmlDelegate,
    diff_html,
    fit_visible_rows,
)
from nxceviri.gui.dialog_parts import (
    SIDE_WIDTH,
    ElidedLabel,
    header_bar,
    named_frame,
    result_row,
    section_label,
    set_tone,
)
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import Badge, Banner, button, format_int, label, tip_html

_Index = QModelIndex | QPersistentModelIndex

FILTER_CHANGES = "changes"
FILTER_APPROVED = "approved"
FILTER_REJECTED = "rejected"
#: Satır yükseklikleri kaydırma/boyut değişikliğinden bu kadar sonra ölçülür (art arda olaylar birleşir).
_FIT_DELAY_MS = 30
_BADGE_STATES = {".xlsx": "success", ".txt": "info", ".csv": "neutral"}
_PICK_FILTER = (
    "TXT/XLSX/CSV dosyaları (*.txt *.xlsx *.csv);;Metin dosyaları (*.txt);;Excel dosyaları (*.xlsx);;"
    "CSV dosyaları (*.csv);;Tüm dosyalar (*)"
)


@dataclass
class _Item:
    """Listedeki bir satır: yazılabilir değişiklik ya da kodu uymadığı için yazılamayan düzeltme."""

    change: Change
    planned: str  # plan_import'un önerdiği metin (düzenlenmemiş)
    text: str  # şu anki “yeni” metin (kullanıcı düzenlemiş olabilir)
    checked: bool
    approved: bool
    reason: str = ""  # boş değilse satır yazılamaz
    html: tuple[str, str] | None = None

    @property
    def writable(self) -> bool:
        return not self.reason

    def effective(self) -> bool:
        """İşaretli ve gerçekten bir şey yazacak mı (boş ya da önceki çeviriyle aynı metin yazmaz)."""
        return self.writable and self.checked and bool(self.text.strip()) and self.text != self.change.old_text


class ImportModel(QAbstractTableModel):
    """Satır listesi (sanal): sütunlar onay kutusu, ŞU AN, DÜZELTME; süzgeç görünen satırları seçer."""

    #: İşaret ya da metin değişti (yazılacak sayısı değişmiş olabilir).
    edited = Signal()

    def __init__(self, new_header: str) -> None:
        super().__init__()
        self._headers = ("", "ŞU AN", new_header)
        self._items: list[_Item] = []
        self._view: list[int] = []
        self._filter = FILTER_CHANGES
        self._n_write = 0
        #: Satır kimliğinden bağlam metnine (HTML); verilirse ve `show_context` açıksa ipucunda görünür.
        self.context_fn: Callable[[int], str] | None = None
        self.show_context = False

    # --- veri -----------------------------------------------------------------------------------------------
    def items(self) -> list[_Item]:
        return self._items

    def set_items(self, items: list[_Item]) -> None:
        self.beginResetModel()
        self._items = items
        self._n_write = sum(1 for i in items if i.effective())
        self._rebuild_view()
        self.endResetModel()
        self.edited.emit()

    def counts(self) -> tuple[int, int, int]:
        """(değişecek, onaylıydı, kodu uymayan) satır sayıları."""
        writable = [i for i in self._items if i.writable]
        return len(writable), sum(1 for i in writable if i.approved), len(self._items) - len(writable)

    def write_count(self) -> int:
        return self._n_write

    def all_checked(self) -> bool:
        writable = [i for i in self._items if i.writable]
        return bool(writable) and all(i.checked for i in writable)

    def set_all_checked(self, checked: bool) -> None:
        for item in self._items:
            if item.writable:
                item.checked = checked
        self._n_write = sum(1 for i in self._items if i.effective())
        if self._view:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._view) - 1, 0))
        self.edited.emit()

    def set_filter(self, name: str) -> None:
        self.beginResetModel()
        self._filter = name
        self._rebuild_view()
        self.endResetModel()

    def current_filter(self) -> str:
        return self._filter

    def _rebuild_view(self) -> None:
        def shown(item: _Item) -> bool:
            if self._filter == FILTER_REJECTED:
                return not item.writable
            return item.writable and (self._filter != FILTER_APPROVED or item.approved)

        self._view = [n for n, item in enumerate(self._items) if shown(item)]

    def item_at(self, row: int) -> _Item:
        return self._items[self._view[row]]

    # --- Qt arayüzü -----------------------------------------------------------------------------------------
    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else len(self._view)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else 3

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._headers[section]
        return None

    def flags(self, index: _Index) -> Qt.ItemFlag:
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.isValid() and self.item_at(index.row()).writable:
            if index.column() == 0:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
            elif index.column() == 2:
                flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def _html(self, item: _Item) -> tuple[str, str]:
        if item.html is None:
            left, right = diff_html(item.change.old_text, item.text)
            t = current_tokens()
            if item.reason:
                right += f'<br><span style="color:{t["danger"]}"><i>{item.reason}</i></span>'
            if item.approved:
                right += f' <span style="background:{t["selection"]};color:{t["text"]}">&nbsp;onaylıydı&nbsp;</span>'
            item.html = (left, right)
        return item.html

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        item = self.item_at(index.row())
        col = index.column()
        if role == Qt.ItemDataRole.CheckStateRole and col == 0 and item.writable:
            return Qt.CheckState.Checked if item.checked else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DisplayRole and col > 0:
            return self._html(item)[col - 1]
        if role == NEW_TEXT_ROLE and col == 2:
            return item.text
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tip(item, col)
        return None

    def _tip(self, item: _Item, col: int) -> str:
        if item.reason:
            tip = f"Bu satır yazılamaz: {item.reason}\nMevcut çevirisi korunur."
        elif col == 0:
            tip = "Bu satırın düzeltmesini yaz. İşareti kaldırırsanız satırın mevcut çevirisi korunur."
        elif col == 2:
            tip = "Düzenlemek için çift tıklayın veya F2'ye basın. Satır sonu için Enter."
        else:
            tip = ""
        text = tip_html(tip) if tip else ""
        if self.show_context and self.context_fn is not None:
            text += self.context_fn(item.change.entry_id)
        return text

    def setData(self, index: _Index, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid():
            return False
        item = self.item_at(index.row())
        if not item.writable:
            return False
        before = item.effective()
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            item.checked = Qt.CheckState(value) == Qt.CheckState.Checked
        elif role == NEW_TEXT_ROLE and index.column() == 2:
            item.text = str(value)
            item.html = None
        else:
            return False
        self._n_write += int(item.effective()) - int(before)
        self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), 2))
        self.edited.emit()
        return True


class _FileRow:
    """Sol paneldeki bir dosya satırı: tür rozeti, ad, “<satır> satır · <düzeltme>” ve kaldırma düğmesi."""

    def __init__(self, info: ImportFile, column_word: str, on_remove: Callable[[], None]) -> None:
        self.frame = QFrame()
        self.frame.setObjectName("fileRow")
        row = QHBoxLayout(self.frame)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(8)
        suffix = Path(info.name).suffix.lower()
        self.badge = Badge(
            suffix.lstrip(".").upper() or "DOSYA", "warning" if info.foreign else _BADGE_STATES.get(suffix, "neutral")
        )
        row.addWidget(self.badge)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.name = ElidedLabel(info.name)
        self.detail = label("", "muted", wrap=True)
        texts.addWidget(self.name)
        texts.addWidget(self.detail)
        row.addLayout(texts, 1)
        if info.foreign:
            self.frame.setProperty("state", "warning")
            self.detail.setText("Başka projeden olabilir · 0 eşleşme")
        else:
            self.frame.setProperty("state", "ok")
            self.detail.setText(f"{format_int(info.lines)} satır · {format_int(info.corrections)} {column_word}")
        self.remove = QToolButton()
        self.remove.setProperty("role", "viewTool")
        self.remove.setText("✕")
        self.remove.setToolTip("Dosyayı listeden kaldır")
        self.remove.setAccessibleName(f"{info.name} dosyasını listeden kaldır")
        self.remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove.clicked.connect(on_remove)
        row.addWidget(self.remove)


class ImportDialog(QDialog):
    """Dış redaksiyon/çeviri dosyalarını önizleyip hangi satırların yazılacağını seçtirir.

    `rows`: projenin çeviri satırları. `translation`: dış çeviri (sütun “yeni çeviri”, durum “Makine”); değilse dış
    redaksiyon (“düzeltme”, “Redakte”). `job_kind`: değişikliklerin iş türü. Dosyalar `add_files` ile eklenir;
    her ekleme ve kaldırma planı yeniden hesaplar, kullanıcının işaretleri ve düzenlemeleri (plan aynıysa) korunur.
    """

    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        rows: Sequence[TranslationRow],
        translation: bool = False,
        job_kind: str = "csv",
        start_dir: str = "",
        context_fn: Callable[[int], str] | None = None,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1100, 720)
        self.setMinimumSize(720, 480)
        self._rows = list(rows)
        self._by_id = {r.id: r for r in self._rows}
        self._column_word = "yeni çeviri" if translation else "düzeltme"
        self._column_header = "YENİ ÇEVİRİ" if translation else "DÜZELTME"
        self._status_name = "Makine" if translation else "Redakte"
        self._job_kind = job_kind
        self._settings = settings
        self._sources: list[tuple[Path, list[CsvRow]]] = []
        self.start_dir = start_dir
        self.last_dir = start_dir
        self.plan = CsvPlan()
        self.import_files: list[ImportFile] = []
        self.file_rows: list[_FileRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header, header_row = header_bar(
            title,
            "Yalnızca değişen satırlar yazılır.",
        )
        self.add_button = button("Dosya ekle", icon="file-plus")
        self.add_button.setToolTip("Aynı projeye ait başka dosyaları da ekleyin (ör. parçalara bölünmüş dosyalar).")
        self.add_button.clicked.connect(self._choose_files)
        header_row.addWidget(self.add_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(header)
        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._build_side())
        body.addWidget(self._build_main(context_fn), 1)
        root.addLayout(body, 1)
        root.addWidget(self._build_footer())

        self.model.context_fn = context_fn
        self.model.show_context = self.context_box.isChecked()
        self.model.edited.connect(self._refresh)
        self._fitted: set[int] = set()
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(_FIT_DELAY_MS)
        self._fit_timer.timeout.connect(lambda: fit_visible_rows(self.table, self._fitted))
        self.table.verticalScrollBar().valueChanged.connect(lambda _v: self._fit_timer.start())
        self.table.horizontalHeader().sectionResized.connect(lambda *_a: self._refit_all())
        self.model.modelReset.connect(self._refit_all)
        self._replan()

    # --- yapı -----------------------------------------------------------------------------------------------
    def _build_side(self) -> QFrame:
        side = named_frame("sidePanel")
        side.setFixedWidth(SIDE_WIDTH + 30)
        outer = QVBoxLayout(side)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(20, 16, 20, 16)
        col.setSpacing(12)
        self.files_label = section_label("DOSYALAR · 0")
        col.addWidget(self.files_label)
        self.files_box = QVBoxLayout()
        self.files_box.setSpacing(8)
        col.addLayout(self.files_box)
        self.no_files_label = label("Henüz dosya eklenmedi. “Dosya ekle” ile başlayın.", "muted", wrap=True)
        col.addWidget(self.no_files_label)
        col.addSpacing(4)
        col.addWidget(section_label("SONUÇ"))
        self.changes_row, self.changes_value = result_row("Değişecek", "info")
        self.same_row, self.same_value = result_row("Zaten aynı")
        self.empty_row, self.empty_value = result_row(f"{self._column_word.capitalize()} sütunu boş")
        self.blocked_row, self.blocked_value = result_row("Yazılmayacak")
        for frame in (self.changes_row, self.same_row, self.empty_row, self.blocked_row):
            col.addWidget(frame)
        self.skipped_label = label("", "muted", wrap=True)
        col.addWidget(self.skipped_label)
        self.reasons_button = QToolButton()
        self.reasons_button.setProperty("role", "link")
        self.reasons_button.setCheckable(True)
        self.reasons_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reasons_button.toggled.connect(self._reasons_toggled)
        col.addWidget(self.reasons_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.reasons_label = label("", wrap=True)
        self.reasons_label.hide()
        col.addWidget(self.reasons_label)
        col.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return side

    def _build_main(self, context_fn: Callable[[int], str] | None) -> QFrame:
        main = named_frame("mainPanel")
        col = QVBoxLayout(main)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self._bar = QGridLayout()
        self._bar.setContentsMargins(20, 12, 20, 12)
        self._bar.setSpacing(8)
        self._chips = QButtonGroup(self)
        self.changes_chip = self._chip(FILTER_CHANGES, "Satırları ve yazılacak düzeltmeleri göster.")
        self.approved_chip = self._chip(
            FILTER_APPROVED, "Değişecek satırlardan onaylı olanlar; yazılırsa onayı kalkar."
        )
        self.rejected_chip = self._chip(
            FILTER_REJECTED, "Kontrol kodları uymadığı için yazılamayan satırlar; mevcut çevirileri korunur."
        )
        for n, chip in enumerate((self.changes_chip, self.approved_chip, self.rejected_chip)):
            chip.setMinimumWidth(chip.sizeHint().width() + 24)  # dar pencerede “Değ… 447” gibi kısalmasın
            self._bar.addWidget(chip, 0, n)
        self._bar.setColumnStretch(3, 1)
        self._checks = QWidget()
        checks = QHBoxLayout(self._checks)
        checks.setContentsMargins(0, 0, 0, 0)
        checks.setSpacing(12)
        self.context_box = QCheckBox("Bağlamı göster")
        self.context_box.setToolTip("Açıkken satırın üzerinde bekleyince önceki ve sonraki satırlar görünür.")
        self.context_box.setChecked(self._settings is not None and str(self._settings.value(CONTEXT_KEY, "0")) == "1")
        self.context_box.toggled.connect(self._context_toggled)
        self.context_box.setVisible(context_fn is not None)
        checks.addWidget(self.context_box)
        self.all_box = QCheckBox("Hepsini yaz")
        self.all_box.setToolTip("Yazılabilir bütün satırları işaretler; kaldırınca hiçbiri yazılmaz.")
        self.all_box.clicked.connect(self._all_clicked)
        checks.addWidget(self.all_box)
        self._bar.addWidget(self._checks, 0, 4)
        col.addLayout(self._bar)
        self.status = Banner()
        status_row = QHBoxLayout()
        status_row.setContentsMargins(20, 0, 20, 8)
        status_row.addWidget(self.status)
        col.addLayout(status_row)

        self.model = ImportModel(self._column_header)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setItemDelegateForColumn(1, HtmlDelegate(self.table))
        self.table.setItemDelegateForColumn(2, EditableDiffDelegate(self.table))
        head = self.table.horizontalHeader()
        head.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        head.resizeSection(0, 40)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(self.fontMetrics().height() * 2 + 12)
        table_row = QHBoxLayout()
        table_row.setContentsMargins(20, 0, 20, 16)
        table_row.addWidget(self.table)
        self.empty_label = label("", "muted", wrap=True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        table_row.addWidget(self.empty_label)
        col.addLayout(table_row, 1)
        return main

    def _chip(self, name: str, tip: str) -> QToolButton:
        chip = QToolButton()
        chip.setProperty("role", "chip")
        chip.setCheckable(True)
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setToolTip(tip)
        chip.setChecked(name == FILTER_CHANGES)
        self._chips.addButton(chip)
        chip.clicked.connect(lambda _c=False, n=name: self._select_filter(n))
        return chip

    def _build_footer(self) -> QFrame:
        footer = named_frame("dialogFooter")
        row = QHBoxLayout(footer)
        row.setContentsMargins(24, 12, 24, 12)
        row.setSpacing(12)
        self.footer_note = label(
            f"“{self._status_name}” durumuyla yazılır · Geri Al ile geri alınabilir", "muted", wrap=True
        )
        row.addWidget(self.footer_note, 1)
        cancel = button("Vazgeç", icon="x")
        cancel.clicked.connect(self.reject)
        self.write_button = button("0 satırı yaz", "primary")
        self.write_button.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self.write_button)
        return footer

    # --- dosyalar -------------------------------------------------------------------------------------------
    def _choose_files(self) -> None:
        targets, _ = QFileDialog.getOpenFileNames(
            self, f"{self._column_word.capitalize()} dosyalarını seçin", self.last_dir or str(Path.home()), _PICK_FILTER
        )
        if targets:
            self.last_dir = str(Path(targets[0]).parent)
            self.add_files([Path(t) for t in targets])

    def add_files(self, paths: Sequence[Path]) -> list[str]:
        """Dosyaları okuyup listeye ekler ve planı yeniler; aynı dosya ikinci kez eklenmez. Okunamayanların
        hata metinleri döner (pencerede de gösterilir)."""
        known = {os.path.normcase(str(p.resolve())) for p, _ in self._sources}
        errors: list[str] = []
        for path in paths:
            key = os.path.normcase(str(path.resolve()))
            if key in known:
                continue
            try:
                lines = read_revision_file(path)
            except CsvError as exc:
                errors.append(exc.user_text())
                continue
            self._sources.append((path, lines))
            known.add(key)
        self.status.show_message("danger", "\n".join(errors))
        self._replan()
        return errors

    def remove_file(self, index: int) -> None:
        """Dosyayı listeden çıkarır ve planı yeniler (dosyanın kendisine dokunulmaz)."""
        if 0 <= index < len(self._sources):
            del self._sources[index]
            self.status.show_message("", "")
            self._replan()

    def _replan(self) -> None:
        result = plan_import_files(self._rows, [(p.name, lines) for p, lines in self._sources])
        self.plan = result.plan
        self.import_files = result.files
        self._show_files(result.files)
        self._show_result(result.plan)
        self.model.set_items(self._items_for(result.plan))
        n_changes, n_approved, n_rejected = self.model.counts()
        self.changes_chip.setText(f"Değişecek {format_int(n_changes)}")
        self.approved_chip.setText(f"Onaylıydı {format_int(n_approved)}")
        self.rejected_chip.setText(f"Kod uymuyor {format_int(n_rejected)}")
        self.approved_chip.setVisible(n_approved > 0)
        self.rejected_chip.setVisible(n_rejected > 0)
        current = self.model.current_filter()
        if (current == FILTER_APPROVED and not n_approved) or (current == FILTER_REJECTED and not n_rejected):
            current = FILTER_CHANGES
        if current == FILTER_CHANGES and not n_changes and n_rejected:
            current = FILTER_REJECTED
        self._select_filter(current)
        self._refresh()

    def _items_for(self, plan: CsvPlan) -> list[_Item]:
        previous = {i.change.entry_id: (i.planned, i.text, i.checked) for i in self.model.items()}
        changed = dict(plan.changes)
        problems = dict(plan.code_problems)
        items: list[_Item] = []
        rejected: list[_Item] = []
        for row in self._rows:
            new = changed.get(row.id)
            if new is None and row.id not in plan.rejected:
                continue
            candidate = new if new is not None else plan.rejected[row.id]
            change = Change(
                row.id,
                row.context or row.key,
                row.source,
                row.translation,
                row.status,
                row.note,
                candidate,
                self._job_kind,
                "",
            )
            kept = previous.get(row.id)
            same = kept is not None and kept[0] == candidate
            item = _Item(
                change,
                candidate,
                kept[1] if kept is not None and same else candidate,
                kept[2] if kept is not None and same else True,
                new is not None and row.status == "approved",
                "" if new is not None else problems.get(row.id, "Kontrol kodları uymuyor."),
            )
            (items if new is not None else rejected).append(item)
        return items + rejected

    def _show_files(self, files: list[ImportFile]) -> None:
        while self.files_box.count():
            item = self.files_box.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.file_rows = []
        for n, info in enumerate(files):
            file_row = _FileRow(info, self._column_word, self._remover(n))
            self.file_rows.append(file_row)
            self.files_box.addWidget(file_row.frame)
        self.files_label.setText(f"DOSYALAR · {len(files)}")
        self.no_files_label.setVisible(not files)

    def _remover(self, index: int) -> Callable[[], None]:
        return lambda: self.remove_file(index)

    def _show_result(self, plan: CsvPlan) -> None:
        self.changes_value.setText(format_int(len(plan.changes)))
        self.same_value.setText(format_int(plan.unchanged))
        self.empty_value.setText(format_int(plan.no_correction))
        self.blocked_value.setText(format_int(plan.skipped))
        set_tone(self.blocked_row, "danger" if plan.skipped else "")
        labels = {i: r.context or r.key for i in (e for e, _ in plan.code_problems) if (r := self._by_id.get(i))}
        lines = describe_import(plan, labels, self._status_name)
        if plan.skipped:
            self.skipped_label.setText(f"Yazılmayan {format_int(plan.skipped)} satırın mevcut çevirisi korunur.")
        else:
            self.skipped_label.setText("Yazılmayan satır yok." if self._sources else "")
        self.reasons_label.setText("\n".join(lines))
        self.reasons_button.setVisible(bool(lines))
        self.reasons_button.blockSignals(True)
        self.reasons_button.setChecked(bool(lines) and not plan.changes and bool(self._sources))
        self.reasons_button.blockSignals(False)
        self._reasons_toggled(self.reasons_button.isChecked())

    def _reasons_toggled(self, on: bool) -> None:
        self.reasons_button.setText("Nedenleri gizle" if on else "Nedenleri göster")
        self.reasons_label.setVisible(on and bool(self.reasons_label.text()))

    # --- liste ----------------------------------------------------------------------------------------------
    def _select_filter(self, name: str) -> None:
        chips = {
            FILTER_CHANGES: self.changes_chip,
            FILTER_APPROVED: self.approved_chip,
            FILTER_REJECTED: self.rejected_chip,
        }
        for key, chip in chips.items():
            chip.setChecked(key == name)
        if name != self.model.current_filter():
            self.model.set_filter(name)
        self._update_empty()

    def _update_empty(self) -> None:
        empty = self.model.rowCount() == 0
        if not self._sources:
            text = "Henüz dosya eklenmedi."
        elif not self.plan.changes and not self.plan.rejected:
            text = "Yazılacak değişiklik yok. Nedenleri soldaki bölümden görebilirsiniz."
        else:
            text = "Bu süzgeçte satır yok."
        self.empty_label.setText(text)
        self.empty_label.setVisible(empty)
        self.table.setVisible(not empty)

    def _all_clicked(self, checked: bool) -> None:
        self.model.set_all_checked(checked)

    def _context_toggled(self, on: bool) -> None:
        self.model.show_context = on
        if self._settings is not None:
            self._settings.setValue(CONTEXT_KEY, "1" if on else "0")

    def _refit_all(self) -> None:
        self._fitted.clear()
        self._fit_timer.start()

    def _arrange_toolbar(self) -> None:
        """Dar pencerede onay kutuları süzgeç düğmelerinin altına iner (düğme metinleri kısalmasın)."""
        narrow = self.width() - SIDE_WIDTH - 30 < 540
        self._bar.removeWidget(self._checks)
        if narrow:
            self._bar.addWidget(self._checks, 1, 0, 1, 5, Qt.AlignmentFlag.AlignRight)
        else:
            self._bar.addWidget(self._checks, 0, 4)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._arrange_toolbar()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.model.show_context = self.context_box.isChecked()
        self._refit_all()

    # --- sonuç ----------------------------------------------------------------------------------------------
    def write_count(self) -> int:
        """Gerçekten yazılacak işaretli satır sayısı."""
        return self.model.write_count()

    def _refresh(self) -> None:
        n = self.model.write_count()
        self.write_button.setText(f"{format_int(n)} satırı yaz")
        self.write_button.setEnabled(n > 0)
        self.write_button.setToolTip(
            f"Değişiklikleri “{self._status_name}” durumuyla yazar; Geri Al ile geri alınabilir."
            if n
            else "Yazılacak satır yok: en az bir satırı işaretleyin."
        )
        blocker = self.all_box.blockSignals(True)
        self.all_box.setChecked(self.model.all_checked())
        self.all_box.setEnabled(self.model.counts()[0] > 0)
        self.all_box.blockSignals(blocker)
        self._update_empty()

    def accepted_changes(self) -> list[Change]:
        """Yazılacak işaretli satırlar; “yeni” sütunundaki düzenlemeler uygulanmış hâlde (kodu uymayanlar dönmez)."""
        return [replace(i.change, new_text=i.text) for i in self.model.items() if i.writable and i.checked]

    def _problems(self) -> list[str]:
        """İşaretli satırlarda yazmayı engelleyen sorunlar (boş metin, uymayan kontrol kodu)."""
        problems: list[str] = []
        free: Mapping[int, frozenset[int]] = {r.id: r.free_codes for r in self._rows}
        for item in self.model.items():
            if not (item.writable and item.checked):
                continue
            change = item.change
            if not item.text.strip():
                problems.append(f"• {change.label}: düzeltme boş. Yazmayacaksanız işareti kaldırın.")
                continue
            if item.text == change.old_text:
                continue  # yazılmayacak (eski çeviriyle aynı) satırın kodları denetlenmez
            fixed = placeholders.repair(change.source, item.text)
            issues = placeholders.check(change.source, fixed, free.get(change.entry_id, frozenset())).errors
            if issues:
                problems.append(f"• {change.label}: {' '.join(issues)}")
        return problems

    def accept(self) -> None:
        problems = self._problems()
        if problems:
            text = "Bu satırlar yazılamaz:\n" + "\n".join(problems[:8])
            if len(problems) > 8:
                text += f"\n… ve {format_int(len(problems) - 8)} satır daha."
            self.status.show_message("danger", text)
            return
        if not self.model.write_count():
            self.status.show_message(
                "warning", "Yazılacak değişiklik kalmadı. En az bir satırı işaretleyin ya da “Vazgeç”e basın."
            )
            return
        super().accept()
