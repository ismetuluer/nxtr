"""Sığdırma sekmesi: grup ve anahtar deseni başına sınırlar tablosu (istatistik, öğrenilen ve elle sınır)."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLineEdit, QTableView, QVBoxLayout, QWidget

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.fit import DEFAULT_VARIABLE_WIDTH, FitRules
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.core.translate.limits import SCOPE_GROUP, SCOPE_KEY, LimitStat, group_stats, key_stats, valid_pattern
from nxceviri.gui.widgets import button, format_int, label

_COLUMNS = (
    "Kapsam",
    "Satır",
    "En uzun satır (orijinal)",
    "Öğrenilen (genişlik × satır)",
    "Elle sınır (genişlik × satır)",
)
_MANUAL_COLUMN = 4
_SORT_ROLE = Qt.ItemDataRole.UserRole + 1
_MANUAL_RE = re.compile(r"(\d+)(?:\s*[×x,;\s]\s*(\d+))?", re.IGNORECASE)
_Index = QModelIndex | QPersistentModelIndex


@dataclass(frozen=True)
class _Entry:
    stat: LimitStat
    learned: FitRules | None


class _Invalid:
    """`_parse_manual` sonucu: yazılan metin anlaşılamadı."""


_INVALID = _Invalid()


def _fmt(rules: FitRules | None) -> str:
    return "" if rules is None else f"{rules.width} × {rules.max_lines}"


def _parse_manual(text: str) -> tuple[int, int | None] | _Invalid | None:
    """ "40 × 3", "40x3", "40, 3" -> (40, 3); "40" -> (40, None); boş ya da "0" -> `None` (kaldır)."""
    stripped = text.strip()
    if not stripped:
        return None
    m = _MANUAL_RE.fullmatch(stripped)
    if m is None:
        return _INVALID
    width = int(m.group(1))
    lines = int(m.group(2)) if m.group(2) is not None else None
    if lines is None and width == 0:
        return None
    if width < 1 or (lines is not None and lines < 1):
        return _INVALID
    return width, lines


class _Model(QAbstractTableModel):
    """Satırlar: önce gruplar, sonra anahtar desenleri. Elle sınır sütunu düzenlenebilir."""

    def __init__(self, on_edit: Callable[[str, str], bool], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._on_edit = on_edit
        self._entries: list[_Entry] = []
        self._manual: dict[str, FitRules] = {}

    def reset(self, entries: list[_Entry], manual: dict[str, FitRules]) -> None:
        self.beginResetModel()
        self._entries = entries
        self._manual = manual
        self.endResetModel()

    def set_manual(self, scope: str, rules: FitRules | None) -> None:
        if rules is None:
            self._manual.pop(scope, None)
        else:
            self._manual[scope] = rules

    def manual_for(self, scope: str) -> FitRules | None:
        return self._manual.get(scope)

    def entry(self, row: int) -> _Entry:
        return self._entries[row]

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        return None

    def flags(self, index: _Index) -> Qt.ItemFlag:
        base = super().flags(index)
        return base | Qt.ItemFlag.ItemIsEditable if index.column() == _MANUAL_COLUMN else base

    def _sort_value(self, entry: _Entry, col: int) -> str | int:
        stat = entry.stat
        if col == 0:
            return ("1" if stat.scope.startswith(SCOPE_KEY) else "0") + stat.label.casefold()  # gruplar önce
        if col == 1:
            return stat.rows
        if col == 2:
            return stat.longest_source_line
        rules = entry.learned if col == 3 else self._manual.get(stat.scope)
        return rules.width if rules else 0

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        stat, col = entry.stat, index.column()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if col == 0:
                return f"Anahtar: {stat.label}" if stat.scope.startswith(SCOPE_KEY) else stat.label
            if col == 1:
                return format_int(stat.rows)
            if col == 2:
                return str(stat.longest_source_line)
            if col == 3:
                return _fmt(entry.learned) or "—"
            return _fmt(self._manual.get(stat.scope))
        if role == _SORT_ROLE:
            return self._sort_value(entry, col)
        if role == Qt.ItemDataRole.TextAlignmentRole and col > 0:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and col == _MANUAL_COLUMN:
            return "Örn. 40 × 3. Boş bırakın ya da 0 yazın: elle sınırı kaldırır."
        return None

    def setData(self, index: _Index, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or index.column() != _MANUAL_COLUMN or not index.isValid():
            return False
        if not self._on_edit(self._entries[index.row()].stat.scope, str(value)):
            return False
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
        return True


class LimitsTable(QWidget):
    """Grup ve anahtar deseni sınırları. Elle sınır düzenlenince `config_edited(FitConfig)` gelir."""

    config_edited = Signal(object)
    learn_all_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._rows: Sequence[TranslationRow] = ()
        self._config = FitConfig()
        self._learned: Mapping[str, FitRules] = {}
        self._patterns: list[str] = []  # ayarlardakiler ve oturumda eklenen, henüz sınırı olmayan desenler

        self.search = QLineEdit()
        self.search.setPlaceholderText("Ara…")
        self.search.setClearButtonEnabled(True)
        self.pattern_input = QLineEdit()
        self.pattern_input.setPlaceholderText("Anahtar deseni, örn. menu_*")
        self.pattern_input.setToolTip("* her şeye, ? tek harfe uyar. Büyük/küçük harf ayırmaz.")
        self.add_button = button("Anahtar deseni ekle…")
        self.remove_button = button("Seçili deseni kaldır")
        self.remove_button.setEnabled(False)
        self.learn_button = button("Hepsini Öğren")
        self.learn_button.setToolTip("Her grubun sınırını kendi orijinal metinlerinden öğrenir.")
        self._status = label("", "muted", wrap=True)

        self._model = _Model(self._on_manual_edited, self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterKeyColumn(0)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setSortRole(_SORT_ROLE)
        self.view = QTableView()
        self.view.setModel(self._proxy)
        self.view.setSortingEnabled(True)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(28)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setColumnWidth(0, 220)
        for col in (1, 2, 3):
            self.view.setColumnWidth(col, 150)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.learn_button)
        add = QHBoxLayout()
        add.addWidget(self.pattern_input, 1)
        add.addWidget(self.add_button)
        add.addWidget(self.remove_button)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addWidget(self.view, 1)
        lay.addLayout(add)
        lay.addWidget(self._status)

        self.search.textChanged.connect(self._proxy.setFilterFixedString)
        self.add_button.clicked.connect(lambda: self.add_pattern(self.pattern_input.text()))
        self.pattern_input.returnPressed.connect(self.add_button.click)
        self.remove_button.clicked.connect(self.remove_selected_pattern)
        self.learn_button.clicked.connect(self.learn_all_requested)
        self.view.selectionModel().selectionChanged.connect(lambda *_: self._update_remove())

    # --- veri ---

    def set_data(self, rows: Sequence[TranslationRow], config: FitConfig, learned: Mapping[str, FitRules]) -> None:
        """Tabloyu satırlardan, ayarlardan ve öğrenilen grup kurallarından (grup adı → kural) yeniden kurar."""
        self._rows, self._config, self._learned = rows, config, learned
        known = {p.casefold() for p in self._patterns}
        self._patterns += [p for p in config.per_key if p.casefold() not in known]
        self._rebuild()

    def _rebuild(self) -> None:
        config = self._config
        stats = {s.scope: s for s in group_stats(self._rows, config.kinds)}
        for group in config.per_group:
            stats.setdefault(SCOPE_GROUP + group, LimitStat(SCOPE_GROUP + group, group, 0, 0, 0))
        entries = [_Entry(s, self._learned.get(s.label)) for s in stats.values()]
        entries += [_Entry(s, None) for s in key_stats(self._rows, self._patterns, config.kinds)]
        manual = {SCOPE_GROUP + g: r for g, r in config.per_group.items()}
        manual |= {SCOPE_KEY + p: r for p, r in config.per_key.items()}
        self._model.reset(entries, manual)
        self._update_remove()

    # --- eylemler ---

    def add_pattern(self, text: str) -> bool:
        """Anahtar deseni ekler; boş/geçersiz ya da var olan desen reddedilir. Eşleşen satır sayısını bildirir."""
        pattern = text.strip()
        if not valid_pattern(pattern):
            self._status.setText("Geçerli bir anahtar deseni yazın, örn. menu_* ya da *_title.")
            return False
        if pattern.casefold() in {p.casefold() for p in self._patterns}:
            self._status.setText(f"‘{pattern}’ deseni zaten listede.")
            return False
        self._patterns.append(pattern)
        self._rebuild()
        count = key_stats(self._rows, [pattern], self._config.kinds)[0].rows
        self._status.setText(f"‘{pattern}’ deseni {format_int(count)} satıra uyuyor. Elle sınır sütununa sınır yazın.")
        self.pattern_input.clear()
        return True

    def remove_selected_pattern(self) -> None:
        scope = self.selected_scope()
        if not scope.startswith(SCOPE_KEY):
            return
        pattern = scope[len(SCOPE_KEY) :]
        self._patterns = [p for p in self._patterns if p != pattern]
        per_key = {p: r for p, r in self._config.per_key.items() if p != pattern}
        had_rule = len(per_key) != len(self._config.per_key)
        self._config = replace(self._config, per_key=per_key)
        self._rebuild()
        self._status.setText(f"‘{pattern}’ deseni kaldırıldı.")
        if had_rule:
            self.config_edited.emit(self._config)

    def _on_manual_edited(self, scope: str, text: str) -> bool:
        parsed = _parse_manual(text)
        if isinstance(parsed, _Invalid):
            self._status.setText(
                "Elle sınırı ‘genişlik × satır’ biçiminde, 1 veya daha büyük sayılarla yazın (örn. 40 × 3)."
            )
            return False
        current = self._model.manual_for(scope)
        rules: FitRules | None = None
        if parsed is not None:
            width, lines = parsed
            if lines is None:
                lines = current.max_lines if current else self._fallback_lines(scope)
            variable = current.variable_width if current else self._variable_width()
            rules = FitRules(width, lines, variable)
        self._model.set_manual(scope, rules)
        self._apply_manual(scope, rules)
        self._status.setText("Elle sınır kaldırıldı." if rules is None else "Elle sınır kaydedilecek.")
        return True

    def _fallback_lines(self, scope: str) -> int:
        """Yalnızca genişlik yazıldığında satır sayısı: grubun öğrenilen değeri, yoksa 1."""
        learned = self._learned.get(scope[len(SCOPE_GROUP) :]) if scope.startswith(SCOPE_GROUP) else None
        return learned.max_lines if learned else 1

    def _variable_width(self) -> int:
        return self._config.default.variable_width if self._config.default else DEFAULT_VARIABLE_WIDTH

    def _apply_manual(self, scope: str, rules: FitRules | None) -> None:
        if scope.startswith(SCOPE_GROUP):
            target, name = dict(self._config.per_group), scope[len(SCOPE_GROUP) :]
        else:
            target, name = dict(self._config.per_key), scope[len(SCOPE_KEY) :]
        if rules is None:
            target.pop(name, None)
        else:
            target[name] = rules
        if scope.startswith(SCOPE_GROUP):
            self._config = replace(self._config, per_group=target)
        else:
            self._config = replace(self._config, per_key=target)
        self.config_edited.emit(self._config)

    def _update_remove(self) -> None:
        self.remove_button.setEnabled(self.selected_scope().startswith(SCOPE_KEY))

    # --- sorgular (arayüz ve testler için) ---

    def selected_scope(self) -> str:
        rows = self.view.selectionModel().selectedRows()
        if not rows:
            return ""
        return self._model.entry(self._proxy.mapToSource(rows[0]).row()).stat.scope

    def select_row(self, row: int) -> None:
        """Kaynak model satırını seçer."""
        self.view.selectRow(self._proxy.mapFromSource(self._model.index(row, 0)).row())

    def model_row_count(self) -> int:
        return self._model.rowCount()

    def visible_row_count(self) -> int:
        return self._proxy.rowCount()

    def scope_at(self, row: int) -> str:
        return self._model.entry(row).stat.scope

    def cell_text(self, row: int, column: int) -> str:
        return str(self._model.index(row, column).data(Qt.ItemDataRole.DisplayRole))

    def cell_flags(self, row: int, column: int) -> Qt.ItemFlag:
        return self._model.flags(self._model.index(row, column))

    def edit_cell(self, row: int, column: int, text: str) -> bool:
        """Hücreyi kullanıcı gibi düzenler; değer kabul edildiyse `True`."""
        return self._model.setData(self._model.index(row, column), text)

    def status_text(self) -> str:
        return self._status.text()
