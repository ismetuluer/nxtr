"""Yazım Denetimi penceresi: projede sözlükte olmayan sözcükler, kaç satırda geçtikleri ve toplu işlemler.

Pencere yalnızca gösterir ve istek bildirir (Yoksay, Sözlüğe Ekle, Değiştir, Tek önerisi olanları düzelt); işleri ana
pencere yapar. Öneriler `suggest_fn` ile ana pencereden gelir.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

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
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.languages import sort_key
from nxceviri.core.spell.report import WordUse
from nxceviri.core.spell.suggest import Suggestion
from nxceviri.gui.widgets import BusyState, button, format_int, label, title_row

_EMPTY_TEXT = "Bilinmeyen sözcük yok"
_SCANNING_TEXT = "Sözcükler taranıyor"
_SCANNING_HINT = ""
_WORD_COLUMN = 0
_COUNT_COLUMN = 1
_SUGGEST_COLUMN = 2
_FIX_ALL_TEXT = "Tek önerisi olanları düzelt"
_CONFIRM_LISTED = 12


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
    #: [(eski, yeni)]: Türkçe harf değişimiyle tek önerisi olan sözcükler tek işte düzeltilsin.
    fix_all_requested = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yazım Denetimi")
        self.setModal(False)
        self.resize(560, 560)
        self._uses: dict[str, WordUse] = {}
        self._previews: Mapping[int, str] = {}
        #: (sözcük, tek düzenleme de aransın mı) → öneri; ana pencere bağlar. Bağlı değilse öneri gösterilmez.
        self.suggest_fn: Callable[[str, bool], Suggestion] | None = None
        self._shown_for: str | None = None  # öneri çubuğunun ve kutunun hazırlandığı sözcük
        lay = QVBoxLayout(self)
        lay.addWidget(
            title_row(
                "Yazım Denetimi",
                "Çevirilerde Türkçe sözlükte olmayan sözcükler. Doğru olanları yoksayın ya da sözlüğe ekleyin; "
                "yanlışları önerilen yazımla hepsinde birden düzeltin.",
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
        self.scanning = BusyState(_SCANNING_TEXT, _SCANNING_HINT)
        self.scanning.setVisible(False)
        lay.addWidget(self.scanning, 1)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Sözcük", "Sayı", "Öneri"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        count_head = self.table.horizontalHeaderItem(_COUNT_COLUMN)
        if count_head is not None:  # sayı sütunu: başlık sağa yaslı hücrelerle aynı hizada
            count_head.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(_WORD_COLUMN, QHeaderView.ResizeMode.Stretch)
        # İçeriğe göre boyutlandırma her hücre eklenişinde bütün sütunu yeniden ölçer (binlerce sözcükte saniyeler);
        # sayı sütunu sabit, sözcük ve öneri sütunu kalan genişliği paylaşır.
        header.setSectionResizeMode(_COUNT_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COUNT_COLUMN, 64)
        header.setSectionResizeMode(_SUGGEST_COLUMN, QHeaderView.ResizeMode.Stretch)
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
        self.fix_all_button = button(_FIX_ALL_TEXT, icon="circle-check")
        self.fix_all_button.setToolTip(
            "Öneri sütununda tek harf değişimi önerisi olan sözcükleri (aramada görünenler) tek işte düzeltir; "
            "Geri Al ile döner."
        )
        self.fix_all_button.clicked.connect(self._fix_all)
        actions.addWidget(self.fix_all_button)
        lay.addLayout(actions)

        suggest_row = QHBoxLayout()
        self.suggest_caption = label("", "muted")
        suggest_row.addWidget(self.suggest_caption)
        self._chips = QHBoxLayout()
        #: Seçili sözcüğün öneri düğmeleri (tıklayınca yeni sözcük kutusuna yazar).
        self.suggestion_buttons: list[QPushButton] = []
        suggest_row.addLayout(self._chips)
        suggest_row.addStretch(1)
        lay.addLayout(suggest_row)

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
        """Büyük projede tarama arka planda sürerken boş durum yerine maskotlu "taranıyor" ekranı gösterilir."""
        self.scanning.setVisible(scanning)
        if scanning:
            self.empty_label.setVisible(False)
            self.table.setVisible(False)
            self.search.setEnabled(False)
        else:
            self.empty_label.setText(_EMPTY_TEXT)
            self.empty_label.setVisible(not self.table.isVisibleTo(self))

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
            self.table.setItem(r, _SUGGEST_COLUMN, self._suggest_item(use.word))
            if use.word in keep:
                word_item.setSelected(True)
        self.table.blockSignals(False)
        self.scanning.setVisible(False)
        self.empty_label.setText(_EMPTY_TEXT)
        empty = not words
        self.empty_label.setVisible(empty)
        self.table.setVisible(not empty)
        self.search.setEnabled(not empty)
        self._filter(self.search.text())
        self._selection_changed()

    def _suggestion(self, word: str, edits: bool) -> Suggestion | None:
        return self.suggest_fn(word, edits) if self.suggest_fn is not None else None

    def _suggest_item(self, word: str) -> QTableWidgetItem:
        """Öneri sütunu: ilk öneri (birden çoksa "+N"); tek düzenleme yalnızca sözcük seçilince aranır."""
        item = QTableWidgetItem()
        self._set_suggest_item(item, self._suggestion(word, False))
        return item

    @staticmethod
    def _set_suggest_item(item: QTableWidgetItem, found: Suggestion | None) -> None:
        words = found.words if found is not None else ()
        item.setText(words[0] + (f"  +{len(words) - 1}" if len(words) > 1 else "") if words else "")
        item.setToolTip("\n".join(words))

    def fix_all_pairs(self) -> list[tuple[str, str]]:
        """Aramada görünen, harf değişimiyle tek önerisi olan sözcükler: (sözcük, öneri). Tek düzenleme girmez."""
        pairs = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, _WORD_COLUMN)
            if item is None or self.table.isRowHidden(r):
                continue
            found = self._suggestion(item.text(), False)
            if found is not None and found.safe:
                pairs.append((item.text(), found.words[0]))
        return pairs

    def _fix_all(self) -> None:
        """Onaydan sonra istek bildirir: öneriler sözlük kapsamına dayanır, yanlış olanlar önce yoksayılabilsin."""
        pairs = self.fix_all_pairs()
        if not pairs:
            return
        listed = "\n".join(f"{old} → {new}" for old, new in pairs[:_CONFIRM_LISTED])
        if len(pairs) > _CONFIRM_LISTED:
            listed += f"\n… ve {format_int(len(pairs) - _CONFIRM_LISTED)} sözcük daha"
        answer = QMessageBox.question(
            self,
            _FIX_ALL_TEXT,
            f"{format_int(len(pairs))} sözcük önerilen yazımla değiştirilecek:\n\n{listed}\n\n"
            "Yanlış önerileri önce Yoksay ile ayırabilirsiniz. Geri Al hepsini geri alır. Devam edilsin mi?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.fix_all_requested.emit(pairs)

    def selected_words(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return [it.text() for r in rows if (it := self.table.item(r, _WORD_COLUMN)) is not None]

    def _filter(self, text: str) -> None:
        needle = sort_key(text.strip())
        for r in range(self.table.rowCount()):
            item = self.table.item(r, _WORD_COLUMN)
            self.table.setRowHidden(r, item is None or needle not in sort_key(item.text()))
        self._update_fix_all()

    def _selection_changed(self) -> None:
        self.rows_list.clear()
        ids = sorted({i for w in self.selected_words() if (use := self._uses.get(w)) for i in use.row_ids})
        for row_id in ids:
            preview = self._previews.get(row_id)
            item = QListWidgetItem(preview if preview else f"Satır {format_int(row_id)}")
            item.setData(Qt.ItemDataRole.UserRole, row_id)
            self.rows_list.addItem(item)
        self._update_suggestions()
        self._update_buttons()

    def _update_suggestions(self) -> None:
        """Tek sözcük seçiliyse önerileri düğme olarak dizer; tek öneri varsa değiştirme kutusunu onunla doldurur."""
        for chip in self.suggestion_buttons:
            self._chips.removeWidget(chip)
            chip.hide()
            chip.deleteLater()
        self.suggestion_buttons = []
        selected = self.selected_words()
        if len(selected) != 1:
            self._shown_for = None
            self.suggest_caption.setText("")
            return
        word = selected[0]
        found = self._suggestion(word, True)
        if found is None:
            self.suggest_caption.setText("")
            return
        row = next(
            (r for r in range(self.table.rowCount()) if (i := self.table.item(r, _WORD_COLUMN)) and i.text() == word),
            -1,
        )
        cell = self.table.item(row, _SUGGEST_COLUMN)
        if cell is not None:
            self._set_suggest_item(cell, found)
        self.suggest_caption.setText("Öneri:" if found.words else "Bu sözcük için öneri bulunamadı.")
        for text in found.words:
            chip = QPushButton(text)
            chip.setProperty("kind", "flat")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip("Değiştirme kutusuna yazar.")
            chip.clicked.connect(lambda _checked=False, value=text: self._use_suggestion(value))
            self._chips.addWidget(chip)
            self.suggestion_buttons.append(chip)
        if word != self._shown_for:
            self._shown_for = word
            self.replace_edit.setText(found.words[0] if len(found.words) == 1 else "")

    def _use_suggestion(self, value: str) -> None:
        self.replace_edit.setText(value)
        self.replace_edit.setFocus()

    def _update_fix_all(self) -> None:
        count = len(self.fix_all_pairs())
        self.fix_all_button.setEnabled(count > 0)
        self.fix_all_button.setText(f"Tek önerisi olanları düzelt ({format_int(count)})" if count else _FIX_ALL_TEXT)

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
