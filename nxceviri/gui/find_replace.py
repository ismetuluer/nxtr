"""Çevirilerde bul ve değiştir penceresi (Ctrl+H).

Satır satır çalışılabilir: “Sonrakini Bul” (F3) eşleşmeler arasında gezer, “Sonrakini Değiştir” yalnızca
gösterilen eşleşmeyi yazar. “Tümünü Değiştir” kalan eşleşmelerin hepsini yazar. Kapsam seçilebilir: tüm
satırlar, tabloda görünenler veya seçili satırlar.

Yazarken `plan` yeniden hesaplanır (projeye yazmaz). Tek tek değiştirme, ana pencerenin verdiği `apply`
geri çağrısıyla hemen yazılır; aynı iş kimliği kullanıldığı için Ctrl+Z hepsini tek işlem olarak geri alır.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.replace import ReplacePlan, plan_replace
from nxceviri.gui.widgets import button, format_int, label, title_row

SCOPE_ALL = 0
SCOPE_VISIBLE = 1
SCOPE_SELECTED = 2

_PREVIEW_ROWS = 3

Apply = Callable[[list[tuple[int, str]]], list[TranslationRow] | None]


class FindReplaceDialog(QDialog):
    """Eşleşmeleri tek tek veya toplu değiştirir; `applied` yazılan değişiklikleri tutar."""

    def __init__(
        self,
        parent: QWidget | None,
        all_rows: Sequence[TranslationRow],
        visible_rows: Sequence[TranslationRow],
        selected_rows: Sequence[TranslationRow] = (),
        find: str = "",
        *,
        apply: Apply | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bul ve Değiştir")
        self.setMinimumWidth(600)
        self._all = list(all_rows)
        self._visible = list(visible_rows)
        self._selected = list(selected_rows)
        self._apply = apply
        self._matches: list[tuple[TranslationRow, str]] = []
        self._cursor = 0
        self.plan = ReplacePlan()
        self.applied: list[tuple[int, str]] = []  # gerçekten yazılan (satır kimliği, yeni çeviri)
        lay = QVBoxLayout(self)
        lay.addWidget(
            title_row(
                "Çevirilerde bul ve değiştir",
                "Yalnızca çeviri metni değişir; kontrol kodunu bozacak değişiklikler yapılmaz, onaylı satırlar "
                "onaylı kalır. Ctrl+Z ile geri alabilirsiniz.",
                "cardTitle",
            )
        )
        form = QFormLayout()
        self.find_edit = QLineEdit(find)
        self.find_edit.setPlaceholderText("Aranacak metin (Ctrl+F buraya gelir)")
        self.replace_edit = QLineEdit()
        form.addRow("Aranan:", self.find_edit)
        form.addRow("Yerine:", self.replace_edit)
        self.scope = QComboBox()
        self.scope.addItem(f"Tüm satırlar ({format_int(len(self._all))})", SCOPE_ALL)
        self.scope.addItem(f"Tabloda görünenler ({format_int(len(self._visible))})", SCOPE_VISIBLE)
        self.scope.addItem(f"Seçili satırlar ({format_int(len(self._selected))})", SCOPE_SELECTED)
        if len(self._visible) >= len(self._all):
            self._disable_scope(SCOPE_VISIBLE)
        if not self._selected:
            self._disable_scope(SCOPE_SELECTED)
        form.addRow("Kapsam:", self.scope)
        lay.addLayout(form)
        self.case = QCheckBox("Büyük/küçük harfe duyarlı")
        self.whole = QCheckBox("Tam sözcük")
        self.regex = QCheckBox("Düzenli ifade (regex)")
        self.regex.setToolTip(
            "Aranan metni düzenli ifade olarak yorumlar. Grup kullanabilirsiniz: (\\w+) ve yerine \\1. "
            "Örnek: Kap[ıi] → Kapı"
        )
        for box in (self.case, self.whole, self.regex):
            lay.addWidget(box)
        self.summary = label("", "muted", wrap=True)
        lay.addWidget(self.summary)
        self.match_label = label("", "muted", wrap=True)
        lay.addWidget(self.match_label)
        self.preview = label("", "muted", wrap=True)
        lay.addWidget(self.preview)
        buttons = QHBoxLayout()
        self.next_button = button("Sonrakini Bul", icon="search")
        self.next_button.setToolTip("Sonraki eşleşmeye geçer (F3).")
        self.next_button.clicked.connect(self._next_match)
        self.replace_button = button("Sonrakini Değiştir", "primary")
        self.replace_button.setToolTip("Gösterilen eşleşmeyi yazar ve sonrakine geçer.")
        self.replace_button.clicked.connect(self._replace_next)
        self.apply_button = button("Tümünü Değiştir")
        self.apply_button.setToolTip("Kalan eşleşmelerin hepsini yazar.")
        self.apply_button.clicked.connect(self._replace_all)
        close = button("Kapat")
        close.clicked.connect(self.reject)
        buttons.addWidget(self.next_button)
        buttons.addWidget(self.replace_button)
        buttons.addStretch(1)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(close)
        lay.addLayout(buttons)
        for edit in (self.find_edit, self.replace_edit):
            edit.textChanged.connect(self._update)
        self.find_edit.returnPressed.connect(self._next_match)
        self.replace_edit.returnPressed.connect(self._replace_next)
        for box in (self.case, self.whole, self.regex):
            box.toggled.connect(self._update)
        self.scope.currentIndexChanged.connect(self._update)
        for keys, slot in (
            (QKeySequence.StandardKey.Find, self._focus_find),
            (QKeySequence("F3"), self._next_match),
        ):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)
        self._update()

    def _disable_scope(self, scope: int) -> None:
        index = self.scope.findData(scope)
        model = self.scope.model()
        if index >= 0 and isinstance(model, QStandardItemModel):
            item = model.item(index)
            if item is not None:
                item.setEnabled(False)

    def _focus_find(self) -> None:
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def _rows(self) -> list[TranslationRow]:
        scope = self.scope.currentData()
        if scope == SCOPE_VISIBLE:
            return self._visible
        if scope == SCOPE_SELECTED:
            return self._selected
        return self._all

    def _update(self) -> None:
        """Arama ölçütü değişti: eşleşmeleri baştan hesaplar, ilk eşleşmeye döner."""
        self._cursor = 0
        self._recompute()

    def _recompute(self) -> None:
        """Geçerli satır listesine göre `plan` ve `_matches` yenilenir; imleç korunur."""
        rows = self._rows()
        self.plan = plan_replace(
            rows,
            self.find_edit.text(),
            self.replace_edit.text(),
            case=self.case.isChecked(),
            whole_word=self.whole.isChecked(),
            regex=self.regex.isChecked(),
        )
        by_id = {r.id: r for r in rows}
        self._matches = [(by_id[rid], new) for rid, new in self.plan.changes if rid in by_id]
        if self._matches:
            self._cursor = min(self._cursor, len(self._matches) - 1)
        else:
            self._cursor = 0
        self._refresh()

    def _refresh(self) -> None:
        has_matches = bool(self._matches)
        self.next_button.setEnabled(has_matches)
        self.replace_button.setEnabled(has_matches)
        self.apply_button.setEnabled(has_matches)
        self.match_label.setText(self._match_text())
        self.preview.setText(self._preview_text())
        if self.plan.error:
            self.summary.setText(self.plan.error)
            return
        if not self.find_edit.text():
            self.summary.setText("Aranacak metni yazın.")
            return
        if not has_matches and not self.plan.skipped:
            self.summary.setText("Eşleşme yok.")
            return
        text = f"{format_int(len(self._matches))} satırda {format_int(self.plan.matches)} eşleşme bulundu."
        if self.plan.skipped:
            text += f" {format_int(self.plan.skipped)} satır kontrol kodunu bozacağı için atlanacak."
        self.summary.setText(text)

    def _match_text(self) -> str:
        if not self._matches:
            return ""
        row, new = self._matches[self._cursor]
        return "\n".join(
            (
                f"Eşleşme {format_int(self._cursor + 1)} / {format_int(len(self._matches))} — {row.file} · {row.key}",
                f"Orijinal: {_short(row.source)}",
                f"Şu an:  {_short(row.translation)}",
                f"Yeni:   {_short(new)}",
            )
        )

    def _preview_text(self) -> str:
        lines = [f"{_short(row.translation)} → {_short(new)}" for row, new in self._matches[:_PREVIEW_ROWS]]
        if len(self._matches) > _PREVIEW_ROWS:
            lines.append(f"… ve {format_int(len(self._matches) - _PREVIEW_ROWS)} satır daha")
        return "Örnek:\n" + "\n".join(lines) if lines else ""

    def _next_match(self) -> None:
        if not self._matches:
            return
        self._cursor = (self._cursor + 1) % len(self._matches)
        self._refresh()

    def _replace_next(self) -> None:
        if not self._matches or self.plan.error:
            return
        self._replace_rows(self._matches[self._cursor : self._cursor + 1])

    def _replace_all(self) -> None:
        if not self._matches or self.plan.error:
            return
        if self._replace_rows(list(self._matches)):
            self.accept()

    def _replace_rows(self, matches: Sequence[tuple[TranslationRow, str]]) -> bool:
        """Verilen eşleşmeleri yazar; başarılıysa True. Yazılanlar `applied` içinde birikir."""
        changes = [(row.id, new) for row, new in matches]
        if not changes:
            return False
        if self._apply is not None:
            updated = self._apply(changes)
            if updated is None:
                self._recompute()
                self.summary.setText("Değiştirilemedi; ayrıntı için ana penceredeki uyarıya bakın.")
                return False
            self._update_rows(updated)
        else:
            self._update_rows([dataclasses.replace(row, translation=new) for row, new in matches])
        self.applied.extend(changes)
        self._recompute()
        return True

    def _update_rows(self, updated: Sequence[TranslationRow]) -> None:
        """Yazılan satırların yeni hâllerini kapsam listelerine işler (sonraki hesap güncel olsun)."""
        by_id = {r.id: r for r in updated}
        if not by_id:
            return
        self._all = [by_id.get(r.id, r) for r in self._all]
        self._visible = [by_id.get(r.id, r) for r in self._visible]
        self._selected = [by_id.get(r.id, r) for r in self._selected]


def _short(text: str, limit: int = 60) -> str:
    line = text.replace("\n", " ")
    return line if len(line) <= limit else line[: limit - 3] + "…"
