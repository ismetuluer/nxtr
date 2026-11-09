"""Yazım Denetimi penceresi: projede sözlükte olmayan sözcükler, kaç satırda geçtikleri ve toplu işlemler.

Pencere yalnızca gösterir ve istek bildirir (Yoksay, Sözlüğe Ekle, Değiştir); işleri ana pencere yapar.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.languages import sort_key
from nxceviri.core.spell.report import WordUse
from nxceviri.gui.widgets import button, format_int, label, title_row

_EMPTY_TEXT = "Bilinmeyen sözcük yok"
_SCANNING_TEXT = "Sözcükler taranıyor…"
_WORD_COLUMN = 0
_COUNT_COLUMN = 1


class SpellWindow(QDialog):
    """Sözlükte olmayan sözcükler tablosu (Sözcük · Sayı) ve seçili sözcüğün geçtiği satırlar."""

    #: Satır listesinde çift tıklanan satırın kimliği (ana pencere Çevir'de gösterir).
    show_row = Signal(int)
    #: Seçili sözcükler: bu projede yoksayılsın (proje ayarı).
    ignore_requested = Signal(list)
    #: Seçili sözcükler: kullanıcı yazım sözlüğüne eklensin.
    add_requested = Signal(list)
    #: (eski, yeni): projedeki çevirilerde eski sözcük yenisiyle değiştirilsin.
    replace_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yazım Denetimi")
        self.setModal(False)
        self.resize(560, 560)
        self._uses: dict[str, WordUse] = {}
        self._previews: Mapping[int, str] = {}
        lay = QVBoxLayout(self)
        lay.addWidget(
            title_row(
                "Yazım Denetimi",
                "Çevirilerde Türkçe sözlükte olmayan sözcükler. Doğru olanları yoksayın ya da sözlüğe ekleyin; "
                "yanlışları hepsinde birden düzeltin.",
                "cardTitle",
                icon="spell-check",
            )
        )
        self.search = QLineEdit()
        self.search.setPlaceholderText("Sözcük ara")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        self.empty_label: QLabel = label(_EMPTY_TEXT, "emptyTitle")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty_label, 1)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Sözcük", "Sayı"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_WORD_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COUNT_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        lay.addWidget(self.table, 3)

        self.rows_caption = label("Geçtiği satırlar", "muted")
        lay.addWidget(self.rows_caption)
        self.rows_list = QListWidget()
        self.rows_list.itemDoubleClicked.connect(self._row_activated)
        lay.addWidget(self.rows_list, 2)

        actions = QHBoxLayout()
        self.ignore_button = button("Yoksay", icon="x")
        self.ignore_button.setToolTip("Seçili sözcükleri bu projede yoksayar.")
        self.ignore_button.clicked.connect(lambda: self.ignore_requested.emit(self.selected_words()))
        self.add_button = button("Sözlüğe Ekle", icon="circle-plus")
        self.add_button.setToolTip("Seçili sözcükleri yazım sözlüğüne ekler; bütün projelerde geçerlidir.")
        self.add_button.clicked.connect(lambda: self.add_requested.emit(self.selected_words()))
        actions.addWidget(self.ignore_button)
        actions.addWidget(self.add_button)
        actions.addStretch(1)
        lay.addLayout(actions)

        replace = QHBoxLayout()
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Yeni sözcük")
        self.replace_edit.textChanged.connect(self._update_buttons)
        self.replace_edit.returnPressed.connect(self._replace)
        self.replace_button = button("Hepsini Şununla Değiştir", icon="replace-all")
        self.replace_button.setToolTip("Seçili sözcüğü bütün çevirilerde değiştirir; Geri Al ile döner.")
        self.replace_button.clicked.connect(self._replace)
        replace.addWidget(self.replace_edit, 1)
        replace.addWidget(self.replace_button)
        lay.addLayout(replace)
        self.set_words([])

    def set_scanning(self, scanning: bool) -> None:
        """Büyük projede tarama arka planda sürerken boş durum yerine "taranıyor" gösterilir."""
        self.empty_label.setText(_SCANNING_TEXT if scanning else _EMPTY_TEXT)
        if scanning:
            self.empty_label.setVisible(True)
            self.table.setVisible(False)
            self.search.setEnabled(False)

    def set_words(self, words: list[WordUse], previews: Mapping[int, str] | None = None) -> None:
        """Tabloyu tazeler; seçili sözcükler hâlâ varsa seçim korunur. `previews`: satır kimliği → kısa metin."""
        keep = set(self.selected_words())
        self._uses = {w.word: w for w in words}
        self._previews = previews or {}
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(words))
        for r, use in enumerate(words):
            word_item = QTableWidgetItem(use.word)
            count_item = QTableWidgetItem(format_int(use.count))
            count_item.setData(Qt.ItemDataRole.UserRole, use.count)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, _WORD_COLUMN, word_item)
            self.table.setItem(r, _COUNT_COLUMN, count_item)
            if use.word in keep:
                word_item.setSelected(True)
        self.table.blockSignals(False)
        self.empty_label.setText(_EMPTY_TEXT)
        empty = not words
        self.empty_label.setVisible(empty)
        self.table.setVisible(not empty)
        self.search.setEnabled(not empty)
        self._filter(self.search.text())
        self._selection_changed()

    def selected_words(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return [it.text() for r in rows if (it := self.table.item(r, _WORD_COLUMN)) is not None]

    def _filter(self, text: str) -> None:
        needle = sort_key(text.strip())
        for r in range(self.table.rowCount()):
            item = self.table.item(r, _WORD_COLUMN)
            self.table.setRowHidden(r, item is None or needle not in sort_key(item.text()))

    def _selection_changed(self) -> None:
        self.rows_list.clear()
        ids = sorted({i for w in self.selected_words() if (use := self._uses.get(w)) for i in use.row_ids})
        for row_id in ids:
            preview = self._previews.get(row_id)
            item = QListWidgetItem(preview if preview else f"Satır {format_int(row_id)}")
            item.setData(Qt.ItemDataRole.UserRole, row_id)
            self.rows_list.addItem(item)
        self._update_buttons()

    def _update_buttons(self) -> None:
        selected = self.selected_words()
        self.ignore_button.setEnabled(bool(selected))
        self.add_button.setEnabled(bool(selected))
        self.replace_button.setEnabled(len(selected) == 1 and bool(self.replace_edit.text().strip()))

    def _row_activated(self, item: QListWidgetItem) -> None:
        row_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(row_id, int):
            self.show_row.emit(row_id)

    def _replace(self) -> None:
        selected = self.selected_words()
        new = self.replace_edit.text().strip()
        if len(selected) == 1 and new:
            self.replace_requested.emit(selected[0], new)
            self.replace_edit.clear()
