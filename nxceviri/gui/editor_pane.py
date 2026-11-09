"""Çeviri düzenleme paneli: seçili satırın özgün ve çeviri metni, kod çipleri ve sayaç.

Panel veri değiştirmez: kayıt isteğini `commit_requested(satır_kimliği, metin)` ile bildirir, sayfa bunu
`TranslationModel.apply` yoluyla yazar (geçmiş ve geri alma aynen çalışır). Kaydedilmemiş metin `flush()` ile
kaydettirilir; sayfa satır değişiminde, panel kapanırken ve pencere kapanırken bunu çağırır.

Kurallar hücre düzenleyicisiyle aynıdır: Enter kaydeder, Shift+Enter yeni satır açar, Esc kayıtlı hâle döndürür.

Karakter sayacı yazılırken canlıdır: "En uzun satır 23 / 28". Sınır sırayla elle girilen değer (panelde "Elle
sınır"), satırın sığdırma kuralı, satırın `max_length` değeri, yoksa orijinalin en uzun satırıdır. Sınırı aşan
satırın aşan kısmı düzenleyicide vurgulanır.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QFontMetrics,
    QKeyEvent,
    QKeySequence,
    QResizeEvent,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QMenu,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.project import TranslationRow, row_group
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.codekinds import KindOf
from nxceviri.core.translate.fit import DEFAULT_VARIABLE_WIDTH, FitRules, split_lines, split_pages, visible_width
from nxceviri.core.translate.status import STATUS_LABELS, Status
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.textmarks import chip_color, chip_glyph, code_spans, trailing_space_spans
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.view_actions import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT
from nxceviri.gui.widgets import Badge, button, label

_ALIGNMENTS = {
    ALIGN_LEFT: Qt.AlignmentFlag.AlignLeft,
    ALIGN_CENTER: Qt.AlignmentFlag.AlignHCenter,
    ALIGN_RIGHT: Qt.AlignmentFlag.AlignRight,
}
_BADGE_STATES = {
    Status.UNTRANSLATED: "neutral",
    Status.MACHINE: "info",
    Status.REDACTED: "info",
    Status.APPROVED: "success",
    Status.ERROR: "danger",
}
NO_ROW_TEXT = "Satır seçin"


#: Elle sınırın varsayılan değeri (panelde "Elle sınır" ilk açıldığında).
DEFAULT_MANUAL_LIMIT = 28

BASIS_MANUAL = "manual"
BASIS_RULE = "rule"
BASIS_MAX_LENGTH = "max_length"
BASIS_ORIGINAL = "original"
BASIS_NONE = "none"
_BASIS_TIPS = {
    BASIS_MANUAL: "Sınır: panelde elle girdiğiniz değer.",
    BASIS_RULE: "Sınır: bu satırın sığdırma kuralı.",
    BASIS_MAX_LENGTH: "Sınır: oyunun bu satır için verdiği uzunluk sınırı.",
    BASIS_ORIGINAL: "Sınır: orijinalin en uzun satırı. Başka bir sınır için “Elle sınır”ı açın.",
    BASIS_NONE: "Sınır yok: orijinal metin boş.",
}


class Counter(NamedTuple):
    """Sayaç metni, durumu (`""`, `"danger"`), sınırın kaynağı (`BASIS_*`) ve satır sınırı (yoksa None)."""

    text: str
    state: str
    basis: str
    limit: int | None


def _measure_rules(rules: FitRules | None) -> FitRules:
    return FitRules(1, 1, rules.variable_width if rules is not None else DEFAULT_VARIABLE_WIDTH)


def line_widths(text: str, kind_of: KindOf, rules: FitRules | None) -> list[tuple[int, int, int]]:
    """Metnin satırları: `(başlangıç, bitiş, görünen genişlik)`. Sayfa sonu ve satır sonu kodları satırlara
    girmez; genişlik sığdırma hesabıyla (`fit.visible_width`) ölçülür."""
    measure = _measure_rules(rules)
    found: list[tuple[int, int, int]] = []
    offset = 0
    for page, separator in split_pages(text, kind_of):
        start = offset
        lines = split_lines(page, kind_of)
        for i, line in enumerate(lines):
            found.append((start, start + len(line), visible_width(line, kind_of, measure)))
            start += len(line)
            if i < len(lines) - 1:  # satırlar arasında tek ayırıcı var: "\n" ya da satır sonu kodu
                token = placeholders.TOKEN_RE.match(text, start)
                start += 1 if text[start] == "\n" or token is None else len(token.group(0))
        offset += len(page) + len(separator)
    return found


def longest_line(text: str, kind_of: KindOf, rules: FitRules | None = None) -> int:
    """Metnin en uzun satırının görünen genişliği."""
    return max((width for _s, _e, width in line_widths(text, kind_of, rules)), default=0)


def line_limit(
    source: str, kind_of: KindOf, rules: FitRules | None, max_length: int | None, manual: int | None
) -> tuple[int | None, str]:
    """Satır sınırı ve kaynağı: elle girilen, sığdırma kuralı, `max_length`, orijinalin en uzun satırı."""
    if manual:
        return manual, BASIS_MANUAL
    if rules is not None:
        return rules.width, BASIS_RULE
    if max_length is not None:
        return None, BASIS_MAX_LENGTH
    original = longest_line(source, kind_of)
    return (original, BASIS_ORIGINAL) if original else (None, BASIS_NONE)


def counter_info(
    text: str,
    kind_of: KindOf,
    rules: FitRules | None,
    max_length: int | None,
    *,
    source: str = "",
    manual: int | None = None,
) -> Counter:
    """Canlı karakter sayacı. Satır sınırı varsa "En uzun satır W / sınır" (sığdırma kuralı varsa sayfa satır
    sayısı da); yalnızca `max_length` varsa "N / sınır"; hiçbiri yoksa görünen (kodlar hariç) karakter sayısı."""
    limit, basis = line_limit(source, kind_of, rules, max_length, manual)
    if limit is not None:
        widest = longest_line(text, kind_of, rules)
        over = widest > limit
        shown = f"En uzun satır {widest} / {limit}"
        if basis == BASIS_RULE and rules is not None:
            tallest = max(len(split_lines(page, kind_of)) for page, _sep in split_pages(text, kind_of))
            shown += f" · Sayfa {tallest}/{rules.max_lines}"
            over = over or tallest > rules.max_lines
        if basis == BASIS_MANUAL:
            # Elle sınır, oyunun gerçek sınırlarını (sığdırma kuralı, biçim sınırı) gizlemez.
            real = counter_info(text, kind_of, rules, max_length, source=source)
            if real.basis in (BASIS_RULE, BASIS_MAX_LENGTH) and real.state == "danger":
                shown += " · Oyun sınırı aşıldı"
                over = True
        return Counter(shown, "danger" if over else "", basis, limit)
    visible = len(placeholders.TOKEN_RE.sub("", text))
    if basis == BASIS_MAX_LENGTH and max_length is not None:
        return Counter(f"{visible} / {max_length}", "danger" if visible > max_length else "", basis, None)
    return Counter(f"{visible} karakter", "", basis, None)


def overflow_spans(text: str, kind_of: KindOf, limit: int, rules: FitRules | None = None) -> list[tuple[int, int]]:
    """Sınırı aşan satırların aşan kısmı (satırın sonundan aşan karakter kadarı), metindeki konumlarıyla."""
    spans: list[tuple[int, int]] = []
    for start, end, width in line_widths(text, kind_of, rules):
        if width > limit:
            stop = start + len(text[start:end].rstrip())
            spans.append((max(stop - (width - limit), start), stop))
    return spans


class _PaneEdit(QPlainTextEdit):
    """Enter kaydeder, Shift+Enter yeni satır açar, Esc vazgeçer (hücre düzenleyicisiyle aynı kural)."""

    committed = Signal()
    reverted = Signal()
    navigate = Signal(int)
    #: Sağ tıkta yazım sözlüğüne eklenmesi istenen sözcük.
    spell_word_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        #: Metindeki konumdaki sözlükte olmayan sözcüğü döndürür (yoksa None); sağ tık menüsü kullanır.
        self.unknown_at: Callable[[int], str | None] = lambda _pos: None

    def build_menu(self, pos: QPoint) -> QMenu:
        """Standart menü; imlecin altındaki sözcük yazım sözlüğünde yoksa en üste "sözlüğe ekle" eylemi konur."""
        menu = self.createStandardContextMenu(pos)
        word = self.unknown_at(self.cursorForPosition(pos).position())
        if word:
            action = QAction(f"“{word}” sözcüğünü yazım sözlüğüne ekle", menu)
            action.triggered.connect(lambda: self.spell_word_requested.emit(word))
            existing = menu.actions()
            if existing:
                menu.insertAction(existing[0], action)
                menu.insertSeparator(existing[0])
            else:
                menu.addAction(action)
        return menu

    def contextMenuEvent(self, e: QContextMenuEvent) -> None:
        menu = self.build_menu(e.pos())
        menu.exec(e.globalPos())
        menu.deleteLater()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.modifiers() & Qt.KeyboardModifier.AltModifier and e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.navigate.emit(-1 if e.key() == Qt.Key.Key_Up else 1)
            return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.committed.emit()
            return
        if e.key() == Qt.Key.Key_Escape:
            self.reverted.emit()
            return
        super().keyPressEvent(e)


#: Başlık satırında satır adına ayrılan en az genişlik (px); sığmazsa önceki/sonraki okları gizlenir.
HEAD_TITLE_MIN = 96

#: Kutuların kaydırmadan göstereceği en az satır (oyun metinleri çoğu zaman üç satırlık sayfalardır).
BOX_MIN_LINES = 3


class EditorPane(QWidget):
    commit_requested = Signal(int, str)
    navigate_requested = Signal(int)
    approve_requested = Signal()
    cursor_moved = Signal(int, int)
    #: Çeviri düzenleyicisi odak aldı/bıraktı (durum çubuğundaki imleç bölmesi için).
    focus_changed = Signal(bool)
    #: Kullanıcı sağ tıkla bir sözcüğün yazım sözlüğüne eklenmesini istedi.
    spell_word_requested = Signal(str)
    #: "Elle sınır" değişti (0: kapalı); sayfa bunu uygulama ayarı olarak saklar.
    manual_limit_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("editorPane")
        self._row: TranslationRow | None = None
        self._number: int | None = None
        self._kind_of: KindOf = lambda _n: "other"
        self._rules: FitRules | None = None
        self._saved: str | None = None
        self._symbols = False
        self._loading = False
        self._selected_count = 1
        self.chip_buttons: list[QToolButton] = []
        self._spell: SpellChecker | None = None
        self._spell_extra: frozenset[str] = frozenset()

        lay = QVBoxLayout(self)
        self._outer = lay
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._title_text = NO_ROW_TEXT
        self.title_label = label(NO_ROW_TEXT, "cardTitle")
        # Satır adı artan boşluğu doldurur ve gerekirse kısalır; rozet ve düğmeler asla sıkışmaz.
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_badge = Badge("", "neutral")
        self.status_badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.prev_button = QToolButton()
        self.next_button = QToolButton()
        for tool, icon_name, tip, step in (
            (self.prev_button, "chevron-up", "Önceki satır (Alt+↑)", -1),
            (self.next_button, "chevron-down", "Sonraki satır (Alt+↓)", 1),
        ):
            tool.setAutoRaise(True)
            tool.setToolTip(tip)
            bind_icon(tool, icon_name)
            tool.clicked.connect(lambda _checked=False, s=step: self.navigate_requested.emit(s))
        self.approve_button = button("Onayla", icon="circle-check")
        self.approve_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.approve_button.clicked.connect(self.approve_requested)
        head.addWidget(self.title_label, 1)
        head.addWidget(self.status_badge)
        head.addWidget(self.prev_button)
        head.addWidget(self.next_button)
        head.addWidget(self.approve_button)
        lay.addLayout(head)

        lay.addWidget(label("Orijinal", "muted"))
        self.source_view = QPlainTextEdit()
        self.source_view.setReadOnly(True)
        # Salt okunur ama kopyalanabilir: fare ve klavye seçimi, Ctrl+C.
        self.source_view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        lay.addWidget(self.source_view, 1)

        lay.addWidget(label("Çeviri", "muted"))
        self.translation_edit = _PaneEdit()
        self.translation_edit.setTabChangesFocus(True)
        lay.addWidget(self.translation_edit, 2)

        self.chips_row = QWidget()
        chips = QHBoxLayout(self.chips_row)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(6)
        self._chips_layout = chips
        self.chips_row.hide()
        lay.addWidget(self.chips_row)

        self.counter_label = label("", "muted")
        self.limit_box = QCheckBox("Elle sınır")
        self.limit_box.setToolTip("Sayaç, satırın kuralı yerine sizin girdiğiniz satır uzunluğunu esas alır.")
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 999)
        self.limit_spin.setValue(DEFAULT_MANUAL_LIMIT)
        self.limit_spin.setToolTip("Satır başına en çok karakter.")
        self.limit_spin.hide()
        counter_row = QHBoxLayout()
        counter_row.addWidget(self.counter_label, 1)
        counter_row.addWidget(self.limit_box)
        counter_row.addWidget(self.limit_spin)
        self.warning_label = label("", "warning", wrap=True)
        self.error_label = label("", "danger", wrap=True)
        lay.addLayout(counter_row)
        lay.addWidget(self.warning_label)
        lay.addWidget(self.error_label)

        self._fit_box_heights()
        self.translation_edit.textChanged.connect(self._text_changed)
        self.translation_edit.cursorPositionChanged.connect(self._cursor_changed)
        self.translation_edit.unknown_at = self.unknown_word_at
        self.translation_edit.spell_word_requested.connect(self.spell_word_requested)
        self.translation_edit.committed.connect(self._commit)
        self.translation_edit.reverted.connect(self._revert)
        self.translation_edit.navigate.connect(self.navigate_requested)
        self.limit_box.toggled.connect(self._manual_limit_edited)
        self.limit_spin.valueChanged.connect(self._manual_limit_edited)
        self.translation_edit.installEventFilter(self)
        self.title_label.installEventFilter(self)
        for key, step in (("Alt+Up", -1), ("Alt+Down", 1)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda s=step: self.navigate_requested.emit(s))
        self._show_row(None)

    # --- dışarıdan kullanım --------------------------------------------------------------

    def set_row(
        self,
        row: TranslationRow | None,
        kind_of: KindOf,
        rules: FitRules | None,
        selected_count: int = 1,
        number: int | None = None,
    ) -> None:
        """`number`: satırın tablodaki No değeri (başlıkta "No 120 · grup" olarak görünür)."""
        self._kind_of = kind_of
        self._rules = rules
        self._number = number
        self._show_row(row, selected_count)

    @property
    def manual_limit(self) -> int | None:
        """Elle girilen satır sınırı; "Elle sınır" kapalıysa None."""
        return self.limit_spin.value() if self.limit_box.isChecked() else None

    def set_manual_limit(self, limit: int) -> None:
        """Kayıtlı elle sınırı yükler (0: kapalı); sinyal yaymaz."""
        for widget in (self.limit_box, self.limit_spin):
            widget.blockSignals(True)
        self.limit_box.setChecked(limit > 0)
        if limit > 0:
            self.limit_spin.setValue(limit)
        self.limit_spin.setVisible(limit > 0)
        for widget in (self.limit_box, self.limit_spin):
            widget.blockSignals(False)
        self._refresh_marks()
        self._refresh_counter()

    def _manual_limit_edited(self) -> None:
        self.limit_spin.setVisible(self.limit_box.isChecked())
        self.manual_limit_changed.emit(self.manual_limit or 0)
        self._refresh_marks()
        self._refresh_counter()

    def set_view(self, symbols: bool, align: str) -> None:
        self._symbols = symbols
        flag = _ALIGNMENTS.get(align, Qt.AlignmentFlag.AlignLeft)
        for edit in (self.source_view, self.translation_edit):
            option = edit.document().defaultTextOption()
            option.setAlignment(flag)
            flags = QTextOption.Flag.ShowTabsAndSpaces | QTextOption.Flag.ShowLineAndParagraphSeparators
            option.setFlags(flags if symbols else QTextOption.Flag(0))
            edit.document().setDefaultTextOption(option)
        self._refresh_marks()

    def set_read_only(self, on: bool) -> None:
        self.translation_edit.setReadOnly(on)
        self.approve_button.setEnabled(not on and self._row is not None)

    def show_error(self, text: str) -> None:
        """Kayıt başarısız oldu: metin düzenleyicide kalır ve hâlâ kaydedilmemiş sayılır."""
        self.error_label.setText(text)
        self._saved = None

    @property
    def row_id(self) -> int | None:
        return self._row.id if self._row is not None else None

    def set_selected_count(self, count: int) -> None:
        """Çok satır seçiliyse başlıkta "N satır seçili" yazar (metne dokunmaz)."""
        self._selected_count = count
        self._update_title()

    def shows(self, row: TranslationRow) -> bool:
        """Panel bu satırı bu hâliyle gösteriyor mu (dışarıdan değişmediyse True)."""
        return self._row == row

    def has_pending(self) -> bool:
        return self._row is not None and self.translation_edit.toPlainText() != self._saved

    def flush(self) -> None:
        if self.has_pending():
            self._commit()

    # --- iç işleyiş ----------------------------------------------------------------------

    def _show_row(self, row: TranslationRow | None, selected_count: int = 1) -> None:
        self._row = row
        self._selected_count = selected_count
        self._loading = True
        enabled = row is not None
        for widget in (self.translation_edit, self.source_view, self.prev_button, self.next_button):
            widget.setEnabled(enabled)
        self.approve_button.setEnabled(enabled and not self.translation_edit.isReadOnly())
        self.error_label.setText("")
        if row is None:
            self._set_title(NO_ROW_TEXT)
            self.title_label.setToolTip("")
            self.status_badge.hide()
            self._fit_head()
            self.source_view.setPlainText("")
            self.translation_edit.setPlainText("")
            self._saved = ""
        else:
            self._update_title()
            self.title_label.setToolTip(f"{row.file}\n{row.key}")
            self.status_badge.set_state(_BADGE_STATES[Status(row.status)], STATUS_LABELS[Status(row.status)])
            self.status_badge.show()
            self._fit_head()
            self.source_view.setPlainText(row.source)
            self.translation_edit.setPlainText(row.translation)
            self._saved = row.translation
            if row.status == Status.ERROR and row.note:
                self.error_label.setText(row.note)
        self._loading = False
        self._rebuild_chips()
        self._refresh_marks()
        self._refresh_counter()

    def _update_title(self) -> None:
        if self._row is None:
            return
        group = row_group(self._row)
        title = f"No {self._number} · {group}" if self._number is not None else group
        if self._selected_count > 1:
            title = f"{self._selected_count} satır seçili · {title}"
        self._set_title(title)

    def _set_title(self, title: str) -> None:
        self._title_text = title
        self._elide_title()

    def _elide_title(self) -> None:
        """Satır adını etiketin o anki genişliğine göre ortadan kısaltır (tam adı ipucunda durur)."""
        width = max(self.title_label.width(), 0) or 360
        shown = QFontMetrics(self.title_label.font()).elidedText(self._title_text, Qt.TextElideMode.ElideMiddle, width)
        if shown != self.title_label.text():
            self.title_label.setText(shown)

    def _fit_head(self) -> None:
        """Dar panelde önceki/sonraki okları gizler: rozet ve Onayla tam görünür, satır adı kısalır."""
        margins = self._outer.contentsMargins()
        inner = self.width() - margins.left() - margins.right()
        spacing = 8
        need = HEAD_TITLE_MIN + self.approve_button.sizeHint().width() + spacing
        if not self.status_badge.isHidden():
            need += self.status_badge.sizeHint().width() + spacing
        arrows = sum(t.sizeHint().width() + spacing for t in (self.prev_button, self.next_button))
        narrow = inner < need + arrows
        for tool in (self.prev_button, self.next_button):
            tool.setVisible(not narrow)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._fit_head()
        super().resizeEvent(event)

    def _rebuild_chips(self) -> None:
        while self._chips_layout.count():  # çipler ve önceki esneme boşluğu birlikte kaldırılır
            item = self._chips_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self.chip_buttons = []
        labels = self._row.code_labels if self._row is not None else ()
        tokens = current_tokens()
        for number, code_label in enumerate(labels, start=1):
            kind = self._kind_of(number)
            chip = QToolButton()
            chip.setText(f"{chip_glyph(kind)}{number}")
            chip.setToolTip(
                f"⟦{number}⟧ {code_label}\nTıklayınca imlece eklenir; kodlar çeviride aynı sırayla kalmalı."
            )
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(f"QToolButton {{ color: {chip_color(kind, tokens)}; font-weight: 600; }}")
            chip.clicked.connect(lambda _checked=False, n=number: self._insert_code(n))
            self._chips_layout.addWidget(chip)
            self.chip_buttons.append(chip)
        self._chips_layout.addStretch(1)
        self.chips_row.setVisible(bool(self.chip_buttons))

    def _insert_code(self, number: int) -> None:
        self.translation_edit.insertPlainText(placeholders.token(number))
        self.translation_edit.setFocus()

    def _commit(self) -> None:
        if self._row is None:
            return
        text = self.translation_edit.toPlainText()
        self._saved = text
        self.error_label.setText("")
        self.commit_requested.emit(self._row.id, text)

    def _revert(self) -> None:
        if self._row is None:
            return
        self.translation_edit.setPlainText(self._saved if self._saved is not None else self._row.translation)

    def _text_changed(self) -> None:
        if self._loading:
            return
        self._refresh_marks()
        self._refresh_counter()

    def _fit_box_heights(self) -> None:
        """Orijinal ve çeviri kutuları en az `BOX_MIN_LINES` satırı kaydırmadan gösterir (yazı tipine göre)."""
        for box in (self.source_view, self.translation_edit):
            text = box.fontMetrics().lineSpacing() * BOX_MIN_LINES
            box.setMinimumHeight(round(text + 2 * box.document().documentMargin() + 2 * box.frameWidth()))

    def changeEvent(self, event: QEvent) -> None:
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._fit_box_heights()
        super().changeEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.title_label and event.type() == QEvent.Type.Resize:
            self._elide_title()
        if watched is self.translation_edit:
            if event.type() == QEvent.Type.FocusIn:
                self.focus_changed.emit(True)
                self._emit_cursor()
            elif event.type() == QEvent.Type.FocusOut:
                self.focus_changed.emit(False)
        return super().eventFilter(watched, event)

    def _emit_cursor(self) -> None:
        cursor = self.translation_edit.textCursor()
        self.cursor_moved.emit(cursor.blockNumber() + 1, cursor.positionInBlock() + 1)

    def _cursor_changed(self) -> None:
        self._emit_cursor()

    def _refresh_counter(self) -> None:
        text = self.translation_edit.toPlainText()
        row = self._row
        counter = counter_info(
            text,
            self._kind_of,
            self._rules,
            row.max_length if row is not None else None,
            source=row.source if row is not None else "",
            manual=self.manual_limit,
        )
        self.counter_label.setText(counter.text)
        self.counter_label.setToolTip(_BASIS_TIPS[counter.basis])
        self.counter_label.setProperty("role", "danger" if counter.state == "danger" else "muted")
        self.counter_label.style().unpolish(self.counter_label)
        self.counter_label.style().polish(self.counter_label)
        source = self._row.source if self._row is not None else ""
        extra = bool(trailing_space_spans(text)) and not trailing_space_spans(source)
        self.warning_label.setText("Satır sonunda boşluk var" if extra and self._row is not None else "")

    def set_spell(self, spell: SpellChecker | None, extra: frozenset[str]) -> None:
        """Yazım denetleyicisini ve ek kabul edilen sözcükleri (oyun sözlüğü) ayarlar; işaretler yenilenir."""
        self._spell = spell
        self._spell_extra = extra
        self._refresh_marks()

    def _unknown_spans(self) -> list[tuple[int, int, str]]:
        if self._spell is None or self._row is None:
            return []
        return self._spell.unknown_spans(self.translation_edit.toPlainText(), self._row.source, self._spell_extra)

    def unknown_word_at(self, position: int) -> str | None:
        """Çeviri metninde `position` imleç konumundaki sözlükte olmayan sözcük; yoksa None."""
        return next((low for start, end, low in self._unknown_spans() if start <= position <= end), None)

    def _refresh_marks(self) -> None:
        tokens = current_tokens()
        for edit in (self.source_view, self.translation_edit):
            edit.setExtraSelections(self._selections(edit, tokens))

    def _selections(self, edit: QPlainTextEdit, tokens: dict[str, str]) -> list[QTextEdit.ExtraSelection]:
        text = edit.toPlainText()
        selections: list[QTextEdit.ExtraSelection] = []

        def add(start: int, end: int, fmt: QTextCharFormat) -> None:
            selection = QTextEdit.ExtraSelection()
            cursor = QTextCursor(edit.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            selection.cursor = cursor
            selection.format = fmt
            selections.append(selection)

        for start, end, number in code_spans(text):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(chip_color(self._kind_of(number), tokens)))
            fmt.setBackground(QColor(tokens["selection"]))
            fmt.setFontWeight(600)
            add(start, end, fmt)
        if edit is self.translation_edit:
            for start, end, _low in self._unknown_spans():
                fmt = QTextCharFormat()
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                fmt.setUnderlineColor(QColor(tokens["danger"]))
                add(start, end, fmt)
        if edit is self.translation_edit and self._row is not None:
            limit, _basis = line_limit(
                self._row.source, self._kind_of, self._rules, self._row.max_length, self.manual_limit
            )
            limits = [limit] if limit is not None else []
            if _basis == BASIS_MANUAL and self._rules is not None:
                limits.append(self._rules.width)  # elle sınır, kuralın gerçek sınırını gizlemesin
            for each in limits:
                for start, end in overflow_spans(text, self._kind_of, each, self._rules):
                    fmt = QTextCharFormat()
                    fmt.setBackground(QColor(tokens["danger_bg"]))
                    add(start, end, fmt)
        if self._symbols:
            for start, end in trailing_space_spans(text):
                fmt = QTextCharFormat()
                fmt.setBackground(QColor(tokens["warning_bg"]))
                add(start, end, fmt)
        return selections
