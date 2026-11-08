"""Çeviri tablosunun üstünde açılan ince “Bul ve Değiştir” çubuğu (Ctrl+F bul, Ctrl+H değiştir).

Pencere gibi tabloyu kilitlemez: yazdıkça eşleşen satırlar tabloda boyanır, sayaç “3 / 41” gösterir, Sonraki
(F3 / Enter) ve Önceki (Shift+F3) satırı seçip yerinde gösterir; tablo süzülmez, kullanıcı gezinip elle
düzenleyebilir.

Çubuk tabloyu ve projeyi doğrudan tanımaz; sayfa `FindHost` sözleşmesini uygular. Tabloya boyama bilgisi
`FindMarks` ile gider (modelde `FIND_SPANS_ROLE` olarak okunur; hücre çizimi bunu kullanır). Önizleme açıkken
eşleşen satırların çevirisi yeni metinle gösterilir ama yazılmaz. “Değiştir” ve “Tümünü Değiştir” sayfanın
`find_apply` yoluyla yazar; her eylem tek iştir, Ctrl+Z hepsini geri alır.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QMenu, QToolButton, QVBoxLayout, QWidget

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.replace import ReplacePlan, find_pattern, plan_replace
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.widgets import button, format_int, label

SCOPE_ALL = 0
SCOPE_VISIBLE = 1
SCOPE_SELECTED = 2
_SCOPE_NAMES = {SCOPE_ALL: "Tümü", SCOPE_VISIBLE: "Görünenler", SCOPE_SELECTED: "Seçili"}

FIELD_TRANSLATION = "translation"
FIELD_SOURCE = "source"
_FIELD_NAMES = {FIELD_TRANSLATION: "Çeviri", FIELD_SOURCE: "Orijinal"}

#: Modelin hücre için verdiği bul-vurgusu: `FindCell`. Hücre çizimi eşleşen aralıkları bununla boyar.
FIND_SPANS_ROLE = Qt.ItemDataRole.UserRole + 20


@dataclass(frozen=True)
class FindCell:
    """Bir hücredeki eşleşmeler: `spans` gösterilen metindeki [başlangıç, bitiş) aralıkları; `current` o anki
    satır mı (daha belirgin boyanır)."""

    spans: tuple[tuple[int, int], ...]
    current: bool


@dataclass(frozen=True)
class FindMarks:
    """Tabloya iletilen bul durumu. `field` hangi sütunda arandığı; `spans` satır kimliği → aralıklar;
    `preview` satır kimliği → çeviri sütununda yazılmadan gösterilecek yeni metin."""

    field: str = FIELD_TRANSLATION
    spans: Mapping[int, tuple[tuple[int, int], ...]] = dataclasses.field(default_factory=dict)
    current: int | None = None
    preview: Mapping[int, str] = dataclasses.field(default_factory=dict)


class FindHost(Protocol):
    """Çubuğun bağlı olduğu sayfanın sağlaması gerekenler."""

    def find_rows(self, scope: int) -> Sequence[TranslationRow]: ...

    def find_current_id(self) -> int | None: ...

    def find_goto(self, row_id: int) -> None: ...

    def find_apply(self, changes: list[tuple[int, str]]) -> list[TranslationRow] | None: ...

    def find_set_marks(self, marks: FindMarks) -> None: ...


def match_spans(pattern: re.Pattern[str], text: str) -> tuple[tuple[int, int], ...]:
    """Metindeki boş olmayan eşleşme aralıkları."""
    return tuple((m.start(), m.end()) for m in pattern.finditer(text) if m.end() > m.start())


class FindBar(QWidget):
    closed = Signal()

    def __init__(self, host: FindHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("findBar")
        self._host = host
        self._matches: list[int] = []
        self._spans: dict[int, tuple[tuple[int, int], ...]] = {}
        self._order: dict[int, int] = {}
        self._cursor = 0
        self._current_id: int | None = None
        self._selected_ids: frozenset[int] = frozenset()
        self._updating = False
        self._busy = False
        self.error = ""
        self.scope = SCOPE_ALL
        self.field = FIELD_TRANSLATION

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(4)
        self.replace_toggle = self._tool("replace", "Değiştir alanını aç/kapat (Ctrl+H)", checkable=True)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Bul…")
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.setMinimumWidth(140)
        self.count_label = label("", "muted")
        self.prev_button = self._tool("chevron-up", "Önceki eşleşme (Shift+F3)")
        self.next_button = self._tool("chevron-down", "Sonraki eşleşme (F3)")
        self.case_button = self._tool("case-sensitive", "Büyük/küçük harfe duyarlı", checkable=True)
        self.word_button = self._tool("whole-word", "Tam sözcük", checkable=True)
        self.regex_button = self._tool(
            "regex", "Düzenli ifade. Grup kullanabilirsiniz: (\\w+) ve yerine \\1.", checkable=True
        )
        self.scope_button, self._scope_actions = self._choice_button("Kapsam", _SCOPE_NAMES, self.set_scope)
        self.field_button, self._field_actions = self._choice_button("Alan", _FIELD_NAMES, self.set_field)
        self.scope_button.setText(_SCOPE_NAMES[SCOPE_ALL])
        self.field_button.setText(_FIELD_NAMES[FIELD_TRANSLATION])
        self.close_button = self._tool("x", "Kapat (Esc)")
        top.addWidget(self.replace_toggle)
        top.addWidget(self.find_edit, 1)
        top.addWidget(self.count_label)
        for widget in (self.prev_button, self.next_button, self.case_button, self.word_button, self.regex_button):
            top.addWidget(widget)
        top.addWidget(self.scope_button)
        top.addWidget(self.field_button)
        top.addWidget(self.close_button)
        outer.addLayout(top)

        self.replace_row = QWidget()
        bottom = QHBoxLayout(self.replace_row)
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(4)
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Yerine…")
        self.replace_edit.setMinimumWidth(140)
        self.preview_box = QCheckBox("Önizle")
        self.preview_box.setToolTip("Değişikliği tabloda yazmadan gösterir.")
        self.replace_button = button("Değiştir", icon="replace")
        self.replace_button.setToolTip("Gösterilen satırdaki eşleşmeleri değiştirir ve sonrakine geçer.")
        self.replace_all_button = button("Tümünü Değiştir", icon="replace-all")
        self.replace_all_button.setToolTip("Kapsamdaki bütün eşleşmeleri değiştirir. Ctrl+Z hepsini geri alır.")
        self.status_label = label("", "muted")
        bottom.addWidget(self.replace_edit, 1)
        bottom.addWidget(self.preview_box)
        bottom.addWidget(self.replace_button)
        bottom.addWidget(self.replace_all_button)
        bottom.addWidget(self.status_label)
        self.replace_row.hide()
        outer.addWidget(self.replace_row)

        self.find_edit.textChanged.connect(self._criteria_changed)
        self.replace_edit.textChanged.connect(self._replacement_changed)
        self.find_edit.returnPressed.connect(self.next)
        self.replace_edit.returnPressed.connect(self.replace_current)
        for toggle in (self.case_button, self.word_button, self.regex_button):
            toggle.toggled.connect(self._criteria_changed)
        self.preview_box.toggled.connect(self._refresh_marks)
        self.replace_toggle.toggled.connect(self._set_replace_visible)
        self.prev_button.clicked.connect(self.previous)
        self.next_button.clicked.connect(self.next)
        self.replace_button.clicked.connect(self.replace_current)
        self.replace_all_button.clicked.connect(self.replace_all)
        self.close_button.clicked.connect(self.close_bar)
        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.close_bar)
        # Tablo değişince (düzenleme, geri alma, yeni satırlar) eşleşmeler bir olay turu sonra yenilenir.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self._recompute_keep)
        self.hide()
        self._update_state()

    # --- kurulum yardımcıları ------------------------------------------------------------

    @staticmethod
    def _tool(icon_name: str, tip: str, *, checkable: bool = False) -> QToolButton:
        tool = QToolButton()
        tool.setProperty("role", "viewTool")
        tool.setToolTip(tip)
        tool.setCheckable(checkable)
        tool.setCursor(Qt.CursorShape.PointingHandCursor)
        bind_icon(tool, icon_name)
        return tool

    @staticmethod
    def _choice_button[K](
        title: str, names: Mapping[K, str], choose: Callable[[K], None]
    ) -> tuple[QToolButton, dict[K, QAction]]:
        """Açılır seçim düğmesi: seçilen seçenek düğme metni olur (metni `choose` sonrası çağıran ayarlar)."""
        tool = QToolButton()
        tool.setObjectName("viewButton")
        tool.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        tool.setToolTip(title)
        menu = QMenu(tool)
        group = QActionGroup(menu)
        actions: dict[K, QAction] = {}
        for key, name in names.items():
            action = QAction(name, menu, checkable=True)
            group.addAction(action)
            menu.addAction(action)
            action.triggered.connect(lambda _checked=False, k=key: choose(k))
            actions[key] = action
        next(iter(actions.values())).setChecked(True)
        tool.setMenu(menu)
        return tool, actions

    # --- açma / kapama ---------------------------------------------------------------------

    def open_bar(self, replace: bool = False) -> None:
        """Çubuğu açar (zaten açıksa bul alanına döner); `replace` değiştir alanını da açar."""
        self.show()
        if replace:
            self.replace_toggle.setChecked(True)
        self.find_edit.setFocus()
        self.find_edit.selectAll()
        self._recompute_from_start()

    def close_bar(self) -> None:
        if self.isHidden():
            return
        self.hide()
        self._matches = []
        self._spans = {}
        self._set_marks(FindMarks())
        self.closed.emit()

    def set_busy(self, busy: bool) -> None:
        """Makine çevirisi sürerken yazma eylemleri kapanır."""
        self._busy = busy
        self._update_state()

    # --- seçenekler ------------------------------------------------------------------------

    def set_scope(self, scope: int) -> None:
        self.scope = scope
        self._scope_actions[scope].setChecked(True)
        self.scope_button.setText(_SCOPE_NAMES[scope])
        if scope == SCOPE_SELECTED:  # gezinirken seçim değişir; kapsam seçildiği andaki satırlarda kalır
            self._selected_ids = frozenset(r.id for r in self._host.find_rows(SCOPE_SELECTED))
        self._recompute_from_start()

    def set_field(self, field_name: str) -> None:
        self.field = field_name
        self._field_actions[field_name].setChecked(True)
        self.field_button.setText(_FIELD_NAMES[field_name])
        self._recompute_from_start()

    @property
    def replace_visible(self) -> bool:
        return not self.replace_row.isHidden()

    def _set_replace_visible(self, on: bool) -> None:
        self.replace_row.setVisible(on)
        self._refresh_marks()

    def _can_replace(self) -> bool:
        return self.field == FIELD_TRANSLATION and not self._busy

    # --- eşleşmeleri hesaplama ---------------------------------------------------------------

    def _scope_rows(self) -> list[TranslationRow]:
        if self.scope == SCOPE_SELECTED:
            return [r for r in self._host.find_rows(SCOPE_ALL) if r.id in self._selected_ids]
        return list(self._host.find_rows(self.scope))

    def _text_of(self, row: TranslationRow) -> str:
        return row.source if self.field == FIELD_SOURCE else row.translation

    def _pattern(self) -> re.Pattern[str] | None:
        self.error = ""
        try:
            return find_pattern(
                self.find_edit.text(),
                case=self.case_button.isChecked(),
                whole_word=self.word_button.isChecked(),
                regex=self.regex_button.isChecked(),
            )
        except re.error as exc:
            self.error = f"Düzenli ifade geçersiz: {exc}"
            return None

    def _recompute(self) -> None:
        pattern = self._pattern()
        self._matches = []
        self._spans = {}
        self._order = {r.id: i for i, r in enumerate(self._host.find_rows(SCOPE_ALL))}
        if pattern is not None:
            for row in self._scope_rows():
                spans = match_spans(pattern, self._text_of(row))
                if spans:
                    self._matches.append(row.id)
                    self._spans[row.id] = spans

    def _recompute_from_start(self) -> None:
        """Ölçüt değişti: eşleşmeler yenilenir, imleç tablodaki geçerli satırdan sonraki ilk eşleşmeye gider."""
        if self.isHidden():
            return
        self._recompute()
        self._cursor = self._start_index()
        self._show_current(goto=True)

    def _recompute_keep(self) -> None:
        """Tablo değişti: imleç aynı satırda kalır (satır artık eşleşmiyorsa sıradaki eşleşmede)."""
        if self.isHidden() or self._updating:
            return
        self._recompute()
        if self._current_id in self._matches:
            self._cursor = self._matches.index(self._current_id)
        self._show_current(goto=False)

    def rows_changed(self) -> None:
        """Sayfa satırların değiştiğini bildirir (düzenleme, geri alma, yeni satırlar)."""
        if not self.isHidden() and not self._updating:
            self._refresh_timer.start()

    def _start_index(self) -> int:
        if not self._matches:
            return 0
        current = self._host.find_current_id()
        start = self._order.get(current, 0) if current is not None else 0
        return next((i for i, rid in enumerate(self._matches) if self._order.get(rid, 0) >= start), 0)

    def _criteria_changed(self) -> None:
        self.status_label.setText("")
        self._recompute_from_start()

    def _replacement_changed(self) -> None:
        self.status_label.setText("")
        self._refresh_marks()

    # --- gezinme -----------------------------------------------------------------------------

    def next(self) -> None:
        self._step(1)

    def previous(self) -> None:
        self._step(-1)

    def _step(self, delta: int) -> None:
        if not self._matches:
            return
        self._cursor = (self._cursor + delta) % len(self._matches)
        self._show_current(goto=True)

    def _show_current(self, *, goto: bool) -> None:
        count = len(self._matches)
        if count:
            self._cursor = min(self._cursor, count - 1)
            self._current_id = self._matches[self._cursor]
        else:
            self._cursor = 0
            self._current_id = None
        self._update_state()
        self._refresh_marks()
        if goto and self._current_id is not None:
            self._updating = True
            try:
                self._host.find_goto(self._current_id)
            finally:
                self._updating = False

    @property
    def match_count(self) -> int:
        return len(self._matches)

    @property
    def current_id(self) -> int | None:
        return self._current_id

    # --- görünüm -----------------------------------------------------------------------------

    def _update_state(self) -> None:
        count = len(self._matches)
        self.count_label.setToolTip(self.error)
        if self.error:
            self.count_label.setText("Geçersiz")
        elif not self.find_edit.text():
            self.count_label.setText("")
        else:
            self.count_label.setText(
                f"{format_int(self._cursor + 1)} / {format_int(count)}" if count else "Eşleşme yok"
            )
        for tool in (self.prev_button, self.next_button):
            tool.setEnabled(count > 0)
        can = count > 0 and self._can_replace() and not self.error
        self.replace_button.setEnabled(can)
        self.replace_all_button.setEnabled(can)
        self.replace_edit.setEnabled(self._can_replace())
        self.preview_box.setEnabled(self._can_replace())
        self.replace_edit.setToolTip("" if self._can_replace() else "Orijinal metinde yalnızca bulunur.")

    def _refresh_marks(self) -> None:
        preview: dict[int, str] = {}
        if self.preview_box.isChecked() and self.replace_visible and self._can_replace() and self._matches:
            preview = dict(self._plan(self._rows_by_id(self._matches)).changes)
        self._set_marks(FindMarks(self.field, dict(self._spans), self._current_id, preview))

    def _set_marks(self, marks: FindMarks) -> None:
        self._updating = True
        try:
            self._host.find_set_marks(marks)
        finally:
            self._updating = False

    # --- değiştirme --------------------------------------------------------------------------

    def _rows_by_id(self, ids: Sequence[int]) -> list[TranslationRow]:
        wanted = set(ids)
        return [r for r in self._scope_rows() if r.id in wanted]

    def _plan(self, rows: Sequence[TranslationRow]) -> ReplacePlan:
        return plan_replace(
            rows,
            self.find_edit.text(),
            self.replace_edit.text(),
            case=self.case_button.isChecked(),
            whole_word=self.word_button.isChecked(),
            regex=self.regex_button.isChecked(),
        )

    def replace_current(self) -> None:
        """Gösterilen satırdaki eşleşmeleri değiştirir ve sonraki eşleşmeye geçer."""
        if not self._matches or not self._can_replace() or self.error or self._current_id is None:
            return
        replaced_id = self._current_id
        if not self._write(self._plan(self._rows_by_id([replaced_id]))):
            return
        self._recompute()
        if replaced_id in self._matches:  # yerine yazılan metin aranan metni içeriyor: sonrakine geç
            self._cursor = (self._matches.index(replaced_id) + 1) % len(self._matches)
        self._show_current(goto=True)

    def replace_all(self) -> None:
        """Kapsamdaki bütün eşleşmeleri tek iş olarak değiştirir."""
        if not self._matches or not self._can_replace() or self.error:
            return
        if self._write(self._plan(self._rows_by_id(self._matches))):
            self._recompute()
            self._show_current(goto=False)

    def _write(self, plan: ReplacePlan) -> bool:
        """Planı yazar ve sonucu çubukta bildirir; yazılamazsa False (ayrıntıyı sayfa bildirir)."""
        if plan.changes:
            self._updating = True
            try:
                written = self._host.find_apply(list(plan.changes))
            finally:
                self._updating = False
            if written is None:
                self.status_label.setText("Değiştirilemedi.")
                return False
        text = f"{format_int(len(plan.changes))} satır değiştirildi"
        if plan.skipped:
            text += f" · {format_int(plan.skipped)} satır atlandı (kontrol kodunu bozardı)"
        self.status_label.setText(text)
        return True
