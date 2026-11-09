"""“Bul ve Değiştir” (Ctrl+F bul, Ctrl+H değiştir): tablonun üstünde yer kaplamayan, taşınabilir küçük pencere.

`FindBar` aramanın kendisidir; `FindWindow` onu ana pencerenin üstünde duran, istenen yere sürüklenebilen bir araç
penceresine koyar (konumu ve boyutu hatırlanır). Pencere tabloyu kilitlemez: yazdıkça eşleşen satırlar tabloda
boyanır, sayaç “3 / 41” gösterir, Sonraki (F3 / Enter) ve Önceki (Shift+F3) satırı seçip yerinde gösterir; tablo
süzülmez, kullanıcı gezinip elle düzenleyebilir.

Çubuk tabloyu ve projeyi doğrudan tanımaz; sayfa `FindHost` sözleşmesini uygular. Tabloya boyama bilgisi
`FindMarks` ile gider (modelde `FIND_SPANS_ROLE` olarak okunur; hücre çizimi bunu kullanır). Önizleme açıkken
eşleşen satırların çevirisi yeni metinle gösterilir ama yazılmaz. “Değiştir” ve “Tümünü Değiştir” sayfanın
`find_apply` yoluyla yazar; her eylem tek iştir, Ctrl+Z hepsini geri alır.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QByteArray, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QMenu, QToolButton, QVBoxLayout, QWidget

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.regexguard import (
    RISKY_MESSAGE,
    SEARCH_BUDGET,
    TIMEOUT_MESSAGE,
    Deadline,
    RiskyPattern,
    SearchTimeout,
)
from nxceviri.core.translate.replace import ReplacePlan, find_pattern, plan_replace, replacement_error
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.shortcuts import ShortcutRegistry
from nxceviri.gui.widgets import button, format_int, label

SCOPE_ALL = 0
SCOPE_VISIBLE = 1
SCOPE_SELECTED = 2
_SCOPE_NAMES = {SCOPE_ALL: "Tümü", SCOPE_VISIBLE: "Görünenler", SCOPE_SELECTED: "Seçili"}

FIELD_TRANSLATION = "translation"
FIELD_SOURCE = "source"
_FIELD_NAMES = {FIELD_TRANSLATION: "Çeviri", FIELD_SOURCE: "Orijinal"}

#: Büyük tablolarda (bu kadar satırdan çoksa) her tuş vuruşu için eşleştirme yazma durunca yapılır.
_DEBOUNCE_ROWS = 2000
_DEBOUNCE_MS = 150
#: Önizleme yalnızca görünen satırlar için hesaplanır; kaydırınca bu gecikmeyle tazelenir.
_SCROLL_REFRESH_MS = 60

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

    def find_order(self, row_id: int) -> int: ...

    def find_view_ids(self) -> frozenset[int]: ...

    def find_filters_active(self) -> bool: ...

    def find_clear_filters(self) -> None: ...

    def find_goto(self, row_id: int) -> bool: ...

    def find_apply(self, changes: list[tuple[int, str]]) -> list[TranslationRow] | None: ...

    def find_set_marks(self, marks: FindMarks) -> None: ...


def match_spans(pattern: re.Pattern[str], text: str) -> tuple[tuple[int, int], ...]:
    """Metindeki boş olmayan eşleşme aralıkları."""
    return tuple((m.start(), m.end()) for m in pattern.finditer(text) if m.end() > m.start())


class LazySpans(Mapping[int, tuple[tuple[int, int], ...]]):
    """Satır kimliği → eşleşme aralıkları; aralıklar yalnızca istenen (çizilen) satırlar için hesaplanır.

    Çok sayıda eşleşmede (ör. 50.000 satır) her tuş vuruşunda hepsinin aralığını çıkarmak arayüzü donduruyordu.
    """

    def __init__(self, pattern: re.Pattern[str], rows: Mapping[int, str]) -> None:
        self._pattern = pattern
        self._texts = rows
        self._cache: dict[int, tuple[tuple[int, int], ...]] = {}

    def __getitem__(self, row_id: int) -> tuple[tuple[int, int], ...]:
        if row_id not in self._texts:
            raise KeyError(row_id)
        if row_id not in self._cache:
            self._cache[row_id] = match_spans(self._pattern, self._texts[row_id])
        return self._cache[row_id]

    def __iter__(self) -> Iterator[int]:
        return iter(self._texts)

    def __len__(self) -> int:
        return len(self._texts)

    def __contains__(self, row_id: object) -> bool:
        return row_id in self._texts


class FindBar(QWidget):
    #: Arama açıldı (pencere kendini gösterir) / kapandı.
    opened = Signal()
    closed = Signal()

    def __init__(
        self, host: FindHost, parent: QWidget | None = None, shortcuts: ShortcutRegistry | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("findBar")
        self._host = host
        self._shortcuts = shortcuts if shortcuts is not None else ShortcutRegistry(self)
        self._matches: list[int] = []
        self._spans: Mapping[int, tuple[tuple[int, int], ...]] = {}
        self._match_rows: dict[int, TranslationRow] = {}
        self._cursor = 0
        self._current_id: int | None = None
        self._selected_ids: frozenset[int] = frozenset()
        self._updating = False
        self._busy = False
        self._hidden_match = False
        self.error = ""
        self.replace_error = ""
        self._scope_chosen = False
        self.scope = SCOPE_ALL
        self.field = FIELD_TRANSLATION

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(4)
        self.replace_toggle = self._tool("replace", "Değiştir alanını aç/kapat", checkable=True)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Bul…")
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.setMinimumWidth(140)
        self.count_label = label("", "muted")
        self.prev_button = self._tool("chevron-up", "Önceki eşleşme")
        self.next_button = self._tool("chevron-down", "Sonraki eşleşme")
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
        # Tuşlu ipuçları kayıt defterinden üretilir; tuş değişince yenilenir.
        self._key_tips = (
            (self.replace_toggle, "Değiştir alanını aç/kapat", "edit.replace"),
            (self.prev_button, "Önceki eşleşme", "edit.find_prev"),
            (self.next_button, "Sonraki eşleşme", "edit.find_next"),
        )
        self._shortcuts.changed.connect(lambda _command: self._refresh_tips())
        self._refresh_tips()
        top.addWidget(self.replace_toggle)
        top.addWidget(self.find_edit, 1)
        top.addWidget(self.count_label)
        for widget in (self.prev_button, self.next_button, self.case_button, self.word_button, self.regex_button):
            top.addWidget(widget)
        top.addWidget(self.scope_button)
        top.addWidget(self.field_button)
        top.addWidget(self.close_button)
        outer.addLayout(top)

        self.notice_row = QWidget()
        notice = QHBoxLayout(self.notice_row)
        notice.setContentsMargins(0, 0, 0, 0)
        notice.setSpacing(4)
        self.notice_label = label("", "muted")
        self.clear_filters_link = QToolButton()
        self.clear_filters_link.setProperty("role", "link")
        self.clear_filters_link.setText("Süzgeci Temizle")
        self.clear_filters_link.setCursor(Qt.CursorShape.PointingHandCursor)
        notice.addWidget(self.notice_label)
        notice.addWidget(self.clear_filters_link)
        notice.addStretch(1)
        self.notice_row.hide()
        outer.addWidget(self.notice_row)

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
        self.clear_filters_link.clicked.connect(self._clear_filters_clicked)
        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.close_bar)
        # Tablo değişince (düzenleme, geri alma, yeni satırlar) eşleşmeler bir olay turu sonra yenilenir.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self._recompute_keep)
        # Büyük tabloda tuş vuruşları birikmesin: eşleştirme yazma durunca bir kez yapılır.
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.setInterval(_DEBOUNCE_MS)
        self._typing_timer.timeout.connect(self._recompute_from_start)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(_SCROLL_REFRESH_MS)
        self._scroll_timer.timeout.connect(self._refresh_marks)
        self.hide()
        self._update_state()

    # --- kurulum yardımcıları ------------------------------------------------------------

    def _refresh_tips(self) -> None:
        for tool, tip, command in self._key_tips:
            key = self._shortcuts.text(command)
            tool.setToolTip(f"{tip} ({key})" if key else tip)

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
        """Aramayı açar (zaten açıksa bul alanına döner); `replace` değiştir alanını da açar."""
        self.show()
        self.opened.emit()
        if replace:
            self.replace_toggle.setChecked(True)
        if not self._scope_chosen:  # süzgeç etkinken varsayılan kapsam görünen satırlardır
            self._apply_scope(SCOPE_VISIBLE if self._host.find_filters_active() else SCOPE_ALL)
        self.find_edit.setFocus()
        self.find_edit.selectAll()
        self._recompute_from_start()

    def close_bar(self) -> None:
        if self.isHidden():
            return
        self.hide()
        self._typing_timer.stop()
        self._scroll_timer.stop()
        self._scope_chosen = False
        self._matches = []
        self._spans = {}
        self._match_rows = {}
        self._set_marks(FindMarks())
        self.closed.emit()

    def set_busy(self, busy: bool) -> None:
        """Makine çevirisi sürerken yazma eylemleri kapanır."""
        self._busy = busy
        self._update_state()

    # --- seçenekler ------------------------------------------------------------------------

    def set_scope(self, scope: int) -> None:
        """Kullanıcının seçtiği kapsam; süzgeç etkinken bile bu seçim korunur."""
        self._scope_chosen = True
        self._apply_scope(scope)
        self._recompute_from_start()

    def _apply_scope(self, scope: int) -> None:
        self.scope = scope
        self._scope_actions[scope].setChecked(True)
        self.scope_button.setText(_SCOPE_NAMES[scope])
        if scope == SCOPE_SELECTED:  # gezinirken seçim değişir; kapsam seçildiği andaki satırlarda kalır
            self._selected_ids = frozenset(r.id for r in self._host.find_rows(SCOPE_SELECTED))

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
        except RiskyPattern:
            self.error = RISKY_MESSAGE
        return None

    def _recompute(self) -> None:
        pattern = self._pattern()
        self._matches = []
        self._spans = {}
        self._match_rows = {}
        if pattern is not None:
            deadline = Deadline(SEARCH_BUDGET)
            try:
                texts: dict[int, str] = {}
                for row in self._scope_rows():
                    deadline.check()
                    text = self._text_of(row)
                    found = pattern.search(text)
                    # Yalnızca boş eşleşen satır eşleşme sayılmaz (aralıklar boş eşleşmeleri atlar).
                    if found is not None and (found.end() > found.start() or match_spans(pattern, text)):
                        self._matches.append(row.id)
                        self._match_rows[row.id] = row
                        texts[row.id] = text
                self._spans = LazySpans(pattern, texts)
            except SearchTimeout:
                self._matches, self._spans, self._match_rows = [], {}, {}
                self.error = TIMEOUT_MESSAGE
        self._sync_replace_error(pattern)

    def _sync_replace_error(self, pattern: re.Pattern[str] | None) -> None:
        """Düzenli ifade değiştirme metni geçersizse hata çubukta gösterilir; değiştirme ve önizleme pasifleşir."""
        previous = self.replace_error
        regex = self.regex_button.isChecked() and pattern is not None
        self.replace_error = replacement_error(pattern, self.replace_edit.text()) if regex and pattern else ""
        if self.replace_error:
            self.status_label.setText(self.replace_error)
        elif previous and self.status_label.text() == previous:
            self.status_label.setText("")

    def _recompute_from_start(self) -> None:
        """Ölçüt değişti: eşleşmeler yenilenir, imleç tablodaki geçerli satırdan sonraki ilk eşleşmeye gider."""
        self._typing_timer.stop()
        if self.isHidden():
            return
        self._recompute()
        self._cursor = self._start_index()
        self._show_current(goto=True)

    def flush(self) -> None:
        """Bekleyen (gecikmeli) arama varsa hemen yapar."""
        if self._typing_timer.isActive():
            self._recompute_from_start()

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

    def view_scrolled(self) -> None:
        """Tablo kaydırıldı: önizleme açıksa yeni görünen satırlar için tazelenir."""
        if not self.isHidden() and self._preview_on():
            self._scroll_timer.start()

    def _start_index(self) -> int:
        if not self._matches:
            return 0
        current = self._host.find_current_id()
        start = self._host.find_order(current) if current is not None else 0
        return next((i for i, rid in enumerate(self._matches) if self._host.find_order(rid) >= start), 0)

    def _criteria_changed(self, *_args: object) -> None:
        self.status_label.setText("")
        if len(self._host.find_rows(SCOPE_ALL)) > _DEBOUNCE_ROWS:
            self._typing_timer.start()
        else:
            self._recompute_from_start()

    def _replacement_changed(self) -> None:
        self.status_label.setText("")
        self._sync_replace_error(self._pattern_if_valid())
        self._update_state()
        self._refresh_marks()

    def _pattern_if_valid(self) -> re.Pattern[str] | None:
        """Bul hatası durumunu bozmadan geçerli kalıbı verir (değiştirme metni denetimi için)."""
        saved = self.error
        pattern = self._pattern()
        self.error = saved
        return pattern

    # --- gezinme -----------------------------------------------------------------------------

    def next(self) -> None:
        self._step(1)

    def previous(self) -> None:
        self._step(-1)

    def _step(self, delta: int) -> None:
        self.flush()
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
        self._hidden_match = False
        if goto and self._current_id is not None:
            self._updating = True
            try:
                self._hidden_match = not self._host.find_goto(self._current_id)
            finally:
                self._updating = False
        self._update_state()
        self._refresh_marks()

    def _clear_filters_clicked(self) -> None:
        """Kullanıcı süzgeci kendisi temizler; sonra o eşleşmeye gidilir."""
        self._host.find_clear_filters()
        self._recompute()
        if self._current_id in self._matches:
            self._cursor = self._matches.index(self._current_id)
        self._show_current(goto=True)

    @property
    def match_count(self) -> int:
        return len(self._matches)

    @property
    def current_id(self) -> int | None:
        return self._current_id

    # --- görünüm -----------------------------------------------------------------------------

    def _update_state(self) -> None:
        count = len(self._matches)
        stopped = self.error in (RISKY_MESSAGE, TIMEOUT_MESSAGE)
        self.count_label.setToolTip(self.error)
        if stopped:
            self.count_label.setText("Durduruldu")
        elif self.error:
            self.count_label.setText("Geçersiz")
        elif not self.find_edit.text():
            self.count_label.setText("")
        else:
            text = f"{format_int(self._cursor + 1)} / {format_int(count)}" if count else "Eşleşme yok"
            if count and self.scope == SCOPE_VISIBLE and self._host.find_filters_active():
                text += " · süzgeçli"
            self.count_label.setText(text)
        notice = self.error if stopped else ("Bu eşleşme süzgeç nedeniyle gizli" if self._hidden_match else "")
        self.notice_label.setText(notice)
        self.clear_filters_link.setVisible(self._hidden_match and not stopped)
        self.notice_row.setVisible(bool(notice))
        for tool in (self.prev_button, self.next_button):
            tool.setEnabled(count > 0)
        can = count > 0 and self._can_replace() and not self.error and not self.replace_error
        self.replace_button.setEnabled(can)
        self.replace_all_button.setEnabled(can)
        self.replace_edit.setEnabled(self._can_replace())
        self.preview_box.setEnabled(self._can_replace() and not self.replace_error)
        self.replace_edit.setToolTip("" if self._can_replace() else "Orijinal metinde yalnızca bulunur.")

    def _preview_on(self) -> bool:
        return (
            self.preview_box.isChecked()
            and self.replace_visible
            and self._can_replace()
            and not self.replace_error
            and not self.error
        )

    def _refresh_marks(self) -> None:
        preview: dict[int, str] = {}
        if self._preview_on() and self._matches:
            # Yalnızca görünen satırlar önizlenir; “Tümünü Değiştir” yine kapsamın tamamında planlar.
            visible = self._host.find_view_ids()
            rows = [self._match_rows[i] for i in self._matches if i in visible]
            preview = dict(self._plan(rows, budget=SEARCH_BUDGET).changes)
        self._set_marks(FindMarks(self.field, self._spans, self._current_id, preview))

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

    def _plan(self, rows: Sequence[TranslationRow], budget: float = 2.0) -> ReplacePlan:
        return plan_replace(
            rows,
            self.find_edit.text(),
            self.replace_edit.text(),
            case=self.case_button.isChecked(),
            whole_word=self.word_button.isChecked(),
            regex=self.regex_button.isChecked(),
            budget=budget,
        )

    def replace_current(self) -> None:
        """Gösterilen satırdaki eşleşmeleri değiştirir ve sonraki eşleşmeye geçer."""
        self.flush()
        if not self._matches or not self._can_replace() or self.error or self.replace_error or self._current_id is None:
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
        self.flush()
        if not self._matches or not self._can_replace() or self.error or self.replace_error:
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


#: Bul penceresinin konumu ve boyutu (uygulama ayarı).
KEY_FIND_GEOMETRY = "translate/find_geometry"
#: İlk açılışta pencerenin, tablonun sağ üst köşesinden uzaklığı (piksel).
_FIRST_MARGIN = 24


class FindWindow(QWidget):
    """`FindBar`ı taşıyan araç penceresi: ana pencerenin üstünde durur, tabloyu kapatmadan istenen yere taşınır.

    İlk açılışta `anchor` bileşeninin (tablo) sağ üst köşesine yerleşir; sonra kullanıcının bıraktığı yer ve boyut
    hatırlanır. Pencerenin kapat düğmesi aramayı kapatır (çubuktaki Esc ile aynı yol).
    """

    def __init__(self, bar: FindBar, anchor: QWidget, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("Bul ve Değiştir")
        self.setObjectName("findWindow")
        self._bar = bar
        self._anchor = anchor
        self._settings: QSettings | None = None
        self._placed = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(bar)
        bar.close_button.hide()  # pencerenin kendi kapat düğmesi var
        bar.opened.connect(self._show_window)
        bar.closed.connect(self._hide_window)
        bar.replace_toggle.toggled.connect(lambda _on: QTimer.singleShot(0, self._fit_height))
        self.setMinimumWidth(520)

    def bind_settings(self, settings: QSettings) -> None:
        self._settings = settings
        saved = settings.value(KEY_FIND_GEOMETRY)
        if isinstance(saved, QByteArray | bytes) and self.restoreGeometry(QByteArray(saved)):
            self._placed = True

    def _show_window(self) -> None:
        if not self._placed:
            self._place_first()
        self.show()
        self.raise_()
        self.activateWindow()
        self._bar.find_edit.setFocus()

    def _place_first(self) -> None:
        self.adjustSize()
        corner = self._anchor.mapToGlobal(self._anchor.rect().topRight())
        self.move(corner.x() - self.width() - _FIRST_MARGIN, corner.y() + _FIRST_MARGIN)
        self._placed = True

    def _fit_height(self) -> None:
        self.resize(self.width(), self.sizeHint().height())

    def _hide_window(self) -> None:
        if self.isVisible():
            self._remember()
        self.hide()
        owner = self.parentWidget()
        if owner is not None:
            owner.window().activateWindow()  # odak tabloya dönebilsin

    def _remember(self) -> None:
        if self._settings is not None:
            self._settings.setValue(KEY_FIND_GEOMETRY, self.saveGeometry())

    def closeEvent(self, event: QCloseEvent) -> None:
        self._remember()
        super().closeEvent(event)
        self._bar.close_bar()
