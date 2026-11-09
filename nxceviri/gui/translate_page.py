"""Adım 3 — Çevir: çeviri tablosu (sanal model, satır içi düzenleme, arama, filtre, toplu işlem)."""

from __future__ import annotations

import dataclasses
import hashlib
import html
import re
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QSettings,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QHideEvent, QKeyEvent, QKeySequence, QResizeEvent, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QSplitter,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.errors import NxError
from nxceviri.core.languages import natural_sort_key
from nxceviri.core.project import TranslationRow, row_group
from nxceviri.core.qa.checks import (
    KIND_LABELS,
    ROW_FLAG_KINDS,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    QaIssue,
)
from nxceviri.core.qa.live import LIVE_KINDS, LiveChecker, LiveContext
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.translate.codekinds import CodeKinds
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.core.translate.runner import ACTION_RETRANSLATE, ACTION_REVISE, ACTION_TRANSLATE, target_rows
from nxceviri.core.translate.status import STATUS_LABELS, Status
from nxceviri.core.translate.uppercase import UppercaseRules
from nxceviri.gui.changes_dialog import HtmlDelegate, diff_html
from nxceviri.gui.editor_pane import EditorPane
from nxceviri.gui.find_replace import (
    FIELD_SOURCE,
    FIND_SPANS_ROLE,
    SCOPE_ALL,
    SCOPE_VISIBLE,
    FindBar,
    FindCell,
    FindMarks,
    FindWindow,
)
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.marked_delegate import ROW_ROLE, MarkedDelegate, kind_of_row
from nxceviri.gui.shortcuts import ShortcutRegistry, display_text
from nxceviri.gui.status_cell import STATUS_ICONS, STATUS_ROLE, StatusDelegate, cell_width, issue_icon, status_icon
from nxceviri.gui.table_columns import ColumnFitter, FitTableView, HeaderColumnMenu
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.value_filter import FilterHeader, FilterPopup, ValueFilter
from nxceviri.gui.view_actions import PANE_RIGHT, ViewActions
from nxceviri.gui.widgets import Banner, Card, EmptyState, button, format_int, label, tip_html, title_row

COL_SOURCE, COL_TRANSLATION, COL_STATUS, COL_FILE, COL_KEY, COL_PREVIOUS, COL_NO = range(7)
_COLUMNS = ("Orijinal", "Çeviri", "Durum", "Dosya", "Anahtar", "Önceki çeviri", "No")
#: Arama kutusuna "#120" yazılınca 120 numaralı satıra gidilir.
_NUMBER_QUERY = re.compile(r"#\s*(\d+)")
#: Durum süzgecinde "son işte değişen satırlar" seçeneğinin değeri.
CHANGED_FILTER = "@changed"
#: Durum süzgecinde yalnızca renkle işaretli (sorunlu) satırlar.
ISSUES_FILTER = "@issues"
#: Sorun türü → çeviri metninin rengi (tema belirteci).
ISSUE_COLORS = {
    "placeholder": "danger",
    "markup": "issue_markup",
    "max_length": "issue_length",
    "code_position": "issue_lines",
    "newlines": "issue_lines",
    "overflow": "warning",
}
#: Son işte değişiklik yokken "Önceki Çeviri Sütunu" ve "Son İşin Değişiklikleri" öğelerinin ipucu.
NO_CHANGES_TIP = "Son işte değişiklik yok"
_PREVIOUS_TIP = (
    "Son yeniden çeviri, düzeltme veya otomatik düzeltmede değişen satırların önceki çevirisini ayrı "
    "sütunda gösterir. Yalnızca değişenleri görmek için durum süzgecinden “Son işte değişenler”i seçin."
)
_MACHINE_TIP = "Ollama veya DeepL ile toplu çeviri, yeniden çeviri ve redaksiyon."
#: Canlı izlemede yeni yazılan satırların vurgulu kaldığı süre (ms).
_FLASH_MS = 2500
#: Durum sütunu sıralanırken kullanılan sıra: sorunlu satırlar önce gelir.
_STATUS_RANK = {
    Status.ERROR: 0,
    Status.UNTRANSLATED: 1,
    Status.MACHINE: 2,
    Status.REDACTED: 3,
    Status.APPROVED: 4,
}
#: Durum sütununda son işi ("· redaksiyon") gösterilen durumlar.
_MARKED_STATUSES = (Status.MACHINE, Status.REDACTED, Status.ERROR)
#: Dar sütunların (varsayılan, en az) genişliği; kalan alan Orijinal/Çeviri (ve açıksa Önceki çeviri) arasında bölünür.
_NARROW_COLUMNS = {
    COL_NO: (52, 40),
    COL_STATUS: (cell_width(), cell_width() - 8),
    COL_FILE: (130, 60),
    COL_KEY: (140, 60),
}
#: Esnek sütunlar: (ağırlık, en az genişlik). "Önceki çeviri" yalnızca açıkken esnektir.
_FLEX_COLUMNS = {COL_SOURCE: (0.45, 120), COL_TRANSLATION: (0.55, 120)}
_PREVIOUS_FLEX = (0.55, 120)
_MIN_COLUMN_WIDTH = 40
#: "Önceki çeviri" sütunu açılınca en az bu genişlikte gösterilir.
_MIN_PREVIOUS_WIDTH = 200
#: Başlık menüsünde gizlenebilen sütunlar; Orijinal ve Çeviri her zaman görünür.
_MENU_COLUMNS = {COL_NO: "No", COL_SOURCE: "Orijinal", COL_TRANSLATION: "Çeviri", COL_STATUS: "Durum"}
_MENU_COLUMNS_EXTRA = {COL_FILE: "Dosya", COL_KEY: "Anahtar"}
_RESIZE_DELAY_MS = 60
#: Büyük harfle gösterilen satırların anahtar sütunundaki işareti.
_UPPERCASE_MARK = "⇧ "
#: Görünen satırların üstünde/altında da ölçülen satır sayısı (kaydırırken boşluk görünmesin).
_ROW_MARGIN = 8
#: Görünür alan bilinmiyorken (yerleşim oturmadan) önizlenecek en çok satır sayısı.
_VIEW_ROWS_CAP = 200

_Index = QModelIndex | QPersistentModelIndex


@dataclasses.dataclass(frozen=True)
class SelectionCounts:
    """Seçili satırların menülerde gösterilen sayıları."""

    selected: int
    translate: int
    retranslate: int
    revise: int
    approvable: int
    approved: int
    with_translation: int


#: Panel sağdayken en az bu genişlikte (px) gösterilir.
PANE_MIN_WIDTH = 280
#: Değişiklikleri kaydeder ve güncellenmiş satırları döndürür; hata olursa NxError fırlatır.
CommitFn = Callable[[list[tuple[int, str]]], list[TranslationRow]]


def clipboard_text(rows: list[TranslationRow], what: str) -> str:
    """Panoya konacak metin. "both": her satır için orijinal, alt satırda çeviri; satırlar arasında boş satır."""
    if what == "source":
        return "\n".join(r.source for r in rows)
    if what == "translation":
        return "\n".join(r.translation for r in rows)
    return "\n\n".join(f"{r.source}\n{r.translation}" for r in rows)


def issue_legend_html() -> str:
    """Renk açıklaması (Görünüm menüsündeki seçeneğin ipucu)."""
    t = current_tokens()
    names = {
        "placeholder": "Kontrol kodu hatası (eksik, fazla, sırası bozuk)",
        "markup": "Orijinalde olmayan etiket (<div> …)",
        "max_length": "Uzunluk sınırı aşıldı",
        "code_position": "Satır sonu kodları yanlış yerde / satır sonu sayısı farklı",
        "overflow": "Orijinalden belirgin uzun (olası taşma)",
    }
    rows = "".join(
        f"<tr><td style='color:{t[ISSUE_COLORS[k]]}'>■</td><td>{html.escape(v)}</td></tr>" for k, v in names.items()
    )
    return f"<b>Çeviri metninin rengi sorunu gösterir:</b><table>{rows}</table>Ayrıntı satırın ipucunda."


def status_legend_html() -> str:
    """Durum simgelerinin açıklaması (Durum başlığının ipucu)."""
    t = current_tokens()
    names = {
        Status.UNTRANSLATED: "Çevrilmedi (gri boş daire)",
        Status.MACHINE: "Makine çevirisi (mavi bilgisayar)",
        Status.REDACTED: "Redakte edildi (yeşil bilgisayar)",
        Status.APPROVED: "Onaylandı (yeşil kişi)",
        Status.ERROR: "Hatalı, dışa aktarılmaz (kırmızı üçgen)",
    }
    rows = "".join(
        f"<tr><td style='color:{t[STATUS_ICONS[s][1]]}'>■</td><td>{html.escape(v)}</td></tr>" for s, v in names.items()
    )
    return (
        f"<b>Durum simgeleri:</b><table>{rows}"
        f"<tr><td style='color:{t['warning']}'>■</td><td>Uyarısı olan satır (sarı üçgen)</td></tr></table>"
    )


class TranslationModel(QAbstractTableModel):
    """Binlerce satırda akıcı çalışan sanal model. Düzenlemeler `commit` ile hemen kaydedilir."""

    commit_failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[TranslationRow] = []  # görüntülenen sıra
        self._pos: dict[int, int] = {}  # satır kimliği → görüntülenen sıra
        self._original: list[int] = []  # özgün (veritabanı) sırasındaki satır kimlikleri
        self._number: dict[
            int, int
        ] = {}  # satır kimliği → No (özgün sıradaki yeri, 1'den başlar; sıralamadan etkilenmez)
        self.find_marks = FindMarks()  # Bul ve Değiştir çubuğunun tabloya bildirdiği eşleşmeler ve önizleme
        self.sort_column = -1
        self.sort_order = Qt.SortOrder.AscendingOrder
        self.commit: CommitFn | None = None
        self.uppercase = UppercaseRules()
        self.marks: dict[int, str] = {}  # satır kimliği → son değişikliği yapan işin kısa adı ("redaksiyon")
        self.previous: dict[int, str] = {}  # son işte değişen satırların önceki çevirisi
        self._flash: set[int] = set()  # canlı izlemede az önce yazılan satırlar
        self.issue_colors = True  # çeviri metni sorun türüne göre renklendirilir
        self.error_rows = False  # hatalı satırın bütün hücreleri hata rengine boyanır (isteğe bağlı)
        self.wrap = True  # tabloda metin kaydırma açık mı (satır sonları gerçek satır olarak gösterilir)
        self.live = LiveChecker()  # anlık denetim: görünen satırlar için, önbellekli
        #: Son "Kontrol Et" sonucu: satır → (denetlenen çeviri, sorunları). Çeviri değişince geçersiz sayılır.
        self._qa: dict[int, tuple[str, list[QaIssue]]] = {}

    def set_live_context(self, context: LiveContext) -> None:
        """Anlık denetimin bağlamını (font, sözlük, sığdırma, yazım, seçili türler) değiştirir; hücreler yenilenir."""
        self.live.set_context(context)
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(_COLUMNS) - 1))

    def flag(self, r: TranslationRow) -> QaIssue | None:
        """Çeviri metnini renklendiren en önemli sorun (yoksa None)."""
        found = {i.kind: i for i in self.live.check(r)}
        return next((found[k] for k in ROW_FLAG_KINDS if k in found), None)

    def _all_issues(self, r: TranslationRow) -> list[QaIssue]:
        """Anlık denetim + çeviri değişmediyse son Kontrol Et sonucunun anlık denetimin kapsamadığı türleri.

        Anlık denetimin bildiği türler (`LIVE_KINDS`) her zaman canlı sonuçtan gelir: Kontrol Et'ten bu yana
        değişen bağlam bayat ya da çift bulgu üretmez, Ayarlar'da kapatılan tür geri gelmez. Kontrol Et
        sayfasındaki liste bundan bağımsızdır. Bilgi düzeyi dahil.
        """
        out = {(i.kind, i.message): i for i in self.live.check(r)}
        qa = self._qa.get(r.id)
        if qa is not None and qa[0] == r.translation:
            for i in qa[1]:
                if i.kind not in LIVE_KINDS:
                    out.setdefault((i.kind, i.message), i)
        return list(out.values())

    def issues(self, r: TranslationRow) -> list[QaIssue]:
        """Satırın hata ve uyarıları (bilgi düzeyi sayılmaz)."""
        return [i for i in self._all_issues(r) if i.severity in (SEVERITY_ERROR, SEVERITY_WARNING)]

    def set_qa_issues(self, issues: list[QaIssue], checked: list[TranslationRow]) -> None:
        """Kontrol Et sonuçlarını (`checked` satırlarının o anki çevirisiyle) durum hücresine bağlar."""
        by_row: dict[int, list[QaIssue]] = {}
        for i in issues:
            by_row.setdefault(i.row_id, []).append(i)
        self._qa = {r.id: (r.translation, by_row[r.id]) for r in checked if r.id in by_row}
        if self.rows:
            # "Hatalı satırları vurgula" açıkken satırın bütün hücreleri hata rengine boyanır.
            first = 0 if self.error_rows else COL_STATUS
            last = self.columnCount() - 1 if self.error_rows else COL_STATUS
            self.dataChanged.emit(self.index(0, first), self.index(len(self.rows) - 1, last))

    def _issue_summary(self, r: TranslationRow) -> str:
        found = self.issues(r)
        errors = sum(i.severity == SEVERITY_ERROR for i in found)
        warnings = len(found) - errors
        parts = ([f"✖ {errors} hata"] if errors else []) + ([f"⚠ {warnings} uyarı"] if warnings else [])
        return " · ".join(parts)

    def _issue_severity(self, r: TranslationRow) -> str | None:
        """Durum hücresindeki üçgenin türü: "error", "warning" ya da sorun yoksa None."""
        found = self.issues(r)
        if not found:
            return None
        return "error" if any(i.severity == SEVERITY_ERROR for i in found) else "warning"

    def set_rows(self, rows: list[TranslationRow]) -> None:
        self.beginResetModel()
        self.live.set_rows(rows)
        self._original = [r.id for r in rows]
        self._number = {row_id: n for n, row_id in enumerate(self._original, start=1)}
        self.rows = list(rows)
        self._reorder()
        self.endResetModel()

    def update_rows(self, rows: list[TranslationRow]) -> None:
        known = [r for r in rows if r.id in self._pos]
        for r in known:
            self.rows[self._pos[r.id]] = r
        # Dizin, hücreler yenilenmeden önce güncellenir (yenileme anlık denetimi okur).
        peers = self.live.update_rows(known)
        for r in known:
            self._row_changed(self._pos[r.id])
        # Aynı kaynaklı öteki satırların "tutarsız" durumu değişmiş olabilir.
        self._ids_changed(peers)

    def position(self, row_id: int) -> int | None:
        return self._pos.get(row_id)

    def number(self, row_id: int) -> int:
        """Satırın No'su: projeye aktarım sırası (1'den başlar); sıralama ve süzgeçle değişmez."""
        return self._number.get(row_id, 0)

    def row_by_number(self, number: int) -> TranslationRow | None:
        if not 1 <= number <= len(self._original):
            return None
        return self.row_by_id(self._original[number - 1])

    def set_find_marks(self, marks: FindMarks) -> None:
        """Bul çubuğunun eşleşme aralıklarını ve (açıksa) yazılmamış önizleme metinlerini tabloya bildirir."""
        old = self.find_marks
        self.find_marks = marks
        changed = {*old.spans, *old.preview, *marks.spans, *marks.preview, old.current, marks.current}
        positions = [p for i in changed if i is not None and (p := self._pos.get(i)) is not None]
        if positions:
            # Satır satır yerine tek aralık: 50.000 eşleşmede bile tek sinyal; yalnızca bul rolleri değişir.
            self.dataChanged.emit(
                self.index(min(positions), 0),
                self.index(max(positions), len(_COLUMNS) - 1),
                [FIND_SPANS_ROLE, ROW_ROLE, Qt.ItemDataRole.DisplayRole],
            )

    def row_by_id(self, row_id: int) -> TranslationRow | None:
        i = self._pos.get(row_id)
        return None if i is None else self.rows[i]

    def _row_changed(self, i: int) -> None:
        self.dataChanged.emit(self.index(i, 0), self.index(i, len(_COLUMNS) - 1))

    def _ids_changed(self, ids: set[int] | list[int]) -> None:
        for row_id in ids:
            i = self._pos.get(row_id)
            if i is not None:
                self._row_changed(i)

    def set_marks(self, marks: dict[int, str]) -> None:
        changed = set(self.marks) ^ set(marks) | {k for k in marks if self.marks.get(k) != marks[k]}
        self.marks = dict(marks)
        self._ids_changed(changed)

    def set_previous(self, previous: dict[int, str]) -> None:
        changed = set(self.previous) | set(previous)
        self.previous = dict(previous)
        self._ids_changed(changed)

    def set_flash(self, ids: list[int], on: bool) -> None:
        if on:
            self._flash.update(ids)
        else:
            self._flash.difference_update(ids)
        self._ids_changed(ids)

    def _sort_key(self, r: TranslationRow, col: int) -> Any:
        """Sütun sıralama anahtarı: metinlerde doğal sıralama (1, 2, 10), Türkçe harf sırasıyla; No ve durum sayısal."""
        if col == COL_NO:
            return self._number.get(r.id, 0)
        if col == COL_SOURCE:
            return natural_sort_key(r.source)
        if col == COL_TRANSLATION:
            return natural_sort_key(r.translation)
        if col == COL_STATUS:
            return _STATUS_RANK[Status(r.status)]
        if col == COL_FILE:
            return natural_sort_key(r.file.rsplit(">", 1)[-1].rsplit("/", 1)[-1])
        if col == COL_PREVIOUS:
            return natural_sort_key(self.previous.get(r.id, ""))
        return natural_sort_key(r.context or r.key)

    def _reorder(self) -> None:
        """`rows` listesini geçerli sıralamaya göre dizer (eşit olanlar özgün sırayı korur)."""
        by_id = {r.id: r for r in self.rows}
        ordered = [by_id[i] for i in self._original if i in by_id]
        if self.sort_column >= 0:
            col = self.sort_column
            ordered.sort(key=lambda r: self._sort_key(r, col), reverse=self.sort_order == Qt.SortOrder.DescendingOrder)
        self.rows = ordered
        self._pos = {r.id: i for i, r in enumerate(ordered)}

    def sort_by(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Sütuna göre sıralar; `column < 0` özgün sıraya döner. Sıralama modelde yapılır: milyonlarca
        Python karşılaştırması yerine tek bir `list.sort` çağrısı yeterlidir."""
        self.beginResetModel()
        self.sort_column, self.sort_order = column, order
        self._reorder()
        self.endResetModel()

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.ToolTipRole and section == COL_STATUS:
            return status_legend_html()
        return None

    def flags(self, index: _Index) -> Qt.ItemFlag:
        base = super().flags(index)
        if index.isValid() and index.column() == COL_TRANSLATION:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def _cell_text(self, text: str) -> str:
        """Hücrede gösterilecek metin: satır sonları simgeye çevrilmez, gerçek satır sonu olarak kalır.

        Kaydırma kapalıyken satır yüksekliği tek satıra indiği için satır sonları boşluğa dönüşür; aksi hâlde
        metnin ilk satırdan sonrası görünmezdi.
        """
        return text if self.wrap else text.replace("\n", " ")

    def refresh_display(self) -> None:
        """Kaydırma değişince görünen metinleri yeniden çizdirir (satır yükseklikleri de yeniden ölçülür)."""
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(_COLUMNS) - 1))

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        col = index.column()
        if role == ROW_ROLE:
            preview = self.find_marks.preview.get(r.id)
            # Bul çubuğu önizlemesi: hücre çizimi satırın çevirisini ROW_ROLE'dan okur; önizlenen satır yeni
            # metinle verilir (yazılmaz; EditRole ve `rows` gerçek metni korur).
            return r if preview is None else dataclasses.replace(r, translation=preview)
        if role == STATUS_ROLE and col == COL_STATUS:
            return Status(r.status), self._issue_severity(r)
        if role == Qt.ItemDataRole.TextAlignmentRole and col == COL_NO:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole and col == COL_NO:
            return QColor(current_tokens()["muted"])
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_NO:
                return str(self._number.get(r.id, 0))
            if col == COL_SOURCE:
                return self._cell_text(r.source)
            if col == COL_TRANSLATION:
                return self._cell_text(self.find_marks.preview.get(r.id, r.translation))
            if col == COL_STATUS:
                mark = self.marks.get(r.id, "") if r.status in _MARKED_STATUSES else ""
                text = "● " + STATUS_LABELS[Status(r.status)] + (f" · {mark}" if mark else "")
                summary = self._issue_summary(r)
                if summary:
                    text += ("\n" if self.wrap else " · ") + summary  # sorunlar durumun altında
                return text
            if col == COL_PREVIOUS:
                if r.id not in self.previous:
                    return ""
                return diff_html(self.previous[r.id], r.translation)[0]
            if col == COL_FILE:
                return r.file.rsplit(">", 1)[-1].rsplit("/", 1)[-1]
            marker = _UPPERCASE_MARK if self.uppercase.applies(r.file, r.key, row_group(r)) else ""
            return marker + (r.context or r.key)
        if role == Qt.ItemDataRole.EditRole:
            return r.translation if col == COL_TRANSLATION else None
        if role == FIND_SPANS_ROLE:
            marks = self.find_marks
            found = COL_SOURCE if marks.field == FIELD_SOURCE else COL_TRANSLATION
            if col != found or r.id not in marks.spans or r.id in marks.preview:
                return None  # önizlenen satırın aralıkları eski metne ait olduğundan boyanmaz
            return FindCell(marks.spans[r.id], r.id == marks.current)
        if role == Qt.ItemDataRole.ForegroundRole and col == COL_TRANSLATION and self.issue_colors:
            issue = self.flag(r)
            return None if issue is None else QColor(current_tokens()[ISSUE_COLORS[issue.kind]])
        if role == Qt.ItemDataRole.BackgroundRole:
            if r.id in self._flash:
                return QColor(current_tokens()["warning_bg"])
            if self.error_rows and self._issue_severity(r) == "error":
                return QColor(current_tokens()["danger_bg"])
            return None
        if role == Qt.ItemDataRole.ToolTipRole:
            tip = self._tooltip(r, col)
            if col == COL_KEY and self.uppercase.applies(r.file, r.key, row_group(r)):
                tip = (tip or "") + "\n\nBüyük harfle gösterilir: dışa aktarırken i harfleri İ yazılır."
            return tip
        return None

    def _tooltip(self, r: TranslationRow, col: int) -> str | None:
        if col == COL_NO:
            n = self._number.get(r.id, 0)
            return f"Satır {n}: projeye aktarım sırası. Arama kutusuna #{n} yazarak bu satıra gidilir."
        if col == COL_STATUS:
            mark = self.marks.get(r.id, "")
            parts = [STATUS_LABELS[Status(r.status)]]
            if r.note:
                parts.append(r.note)
            found = self.issues(r)
            if found:
                parts.append("\n".join(f"{'✖' if i.severity == SEVERITY_ERROR else '⚠'} {i.message}" for i in found))
            if mark and r.status in _MARKED_STATUSES:
                parts.append(f"Son değişiklik: {mark}. Önceki hâli için sağ tık → Çeviri geçmişi.")
            return "\n\n".join(parts) or None
        if col == COL_PREVIOUS:
            previous = self.previous.get(r.id)
            return tip_html(previous) if previous else None
        if col in (COL_SOURCE, COL_TRANSLATION):
            text = r.source if col == COL_SOURCE else r.translation
            lines = [text or "(boş)"]
            if r.code_labels:
                lines.append("")
                lines.append("Kontrol kodları (çeviride aynı sırayla korunmalı):")
                lines += [f"  ⟦{i}⟧  {lbl}" for i, lbl in enumerate(r.code_labels, start=1)]
            if r.note:
                lines += ["", r.note]
            issue = self.flag(r) if col == COL_TRANSLATION else None
            if issue is not None and issue.message != r.note:
                lines += ["", f"⚠ {KIND_LABELS[issue.kind]}: {issue.message}"]
            return tip_html("\n".join(lines))  # düz metin: çevirideki "<div>" biçim sanılmasın
        if col == COL_FILE:
            return r.file.replace(">", "  ›  ")
        if col == COL_KEY:
            return f"{r.context}\nKimlik: {r.key}" if r.context else r.key
        return None

    def setData(self, index: _Index, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or index.column() != COL_TRANSLATION or self.commit is None:
            return False
        r = self.rows[index.row()]
        text = str(value)
        if text == r.translation:
            return False
        return self.apply([(r.id, text)])

    def apply(self, changes: list[tuple[int, str]]) -> bool:
        if self.commit is None or not changes:
            return False
        try:
            updated = self.commit(changes)
        except NxError as exc:
            self.commit_failed.emit(exc.user_text())
            return False
        self.update_rows(updated)
        return True


class TranslationFilter(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.status = ""
        self.groups: frozenset[str] | None = None  # None: grup süzgeci yok
        self.keys: frozenset[str] | None = None  # None: anahtar süzgeci yok
        self.text = ""
        # Düzenleme sırasında satırlar süzgeçten çıkıp yer değiştirmesin: süzgeç yalnızca süzgeç
        # değişince yeniden uygulanır. Sıralama proxy'de değil modelde yapılır (bkz. TranslationModel.sort_by).
        self.setDynamicSortFilter(False)

    def update(self, status: str, groups: frozenset[str] | None, keys: frozenset[str] | None, text: str) -> None:
        self.beginFilterChange()
        self.status, self.groups, self.keys = status, groups, keys
        # "#120" satıra gitmek içindir, metin araması değildir.
        self.text = "" if _NUMBER_QUERY.fullmatch(text.strip()) else text.casefold()
        self.endFilterChange()

    def filterAcceptsRow(self, source_row: int, source_parent: _Index) -> bool:
        model = self.sourceModel()
        assert isinstance(model, TranslationModel)
        r = model.rows[source_row]
        if self.status == CHANGED_FILTER:
            if r.id not in model.previous:
                return False
        elif self.status == ISSUES_FILTER:
            if not model.issues(r):
                return False
        elif self.status and r.status != self.status:
            return False
        if self.groups is not None and row_group(r) not in self.groups:
            return False
        if self.keys is not None and (r.context or r.key) not in self.keys:
            return False
        if not self.text:
            return True
        return any(self.text in s.casefold() for s in (r.source, r.translation, r.key, r.context))


class _Editor(QPlainTextEdit):
    """Çok satırlı düzenleyici: Enter kaydeder, Shift+Enter yeni satır, Esc vazgeçer."""

    committed = Signal()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.committed.emit()
            return
        super().keyPressEvent(e)


class _ElideLeftDelegate(QStyledItemDelegate):
    """Yol ve anahtar gibi sonu önemli metinleri tek satırda, baştan kısaltarak gösterir.

    "Metni kaydır" açıkken bile alt satıra kaymaz: uzun bir anahtar satırı dört satır yüksekliğe çıkarmasın.
    Tamamı ipucunda görünür.
    """

    def initStyleOption(self, option: QStyleOptionViewItem, index: _Index) -> None:
        super().initStyleOption(option, index)
        option.textElideMode = Qt.TextElideMode.ElideLeft
        option.features &= ~QStyleOptionViewItem.ViewItemFeature.WrapText

    def sizeHint(self, option: QStyleOptionViewItem, index: _Index) -> QSize:
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), option.fontMetrics.height() + 8)


class TranslationDelegate(MarkedDelegate):
    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent, "translation")

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
        rect = option.rect
        rect.setHeight(max(rect.height(), 6 * option.fontMetrics.height()))
        editor.setGeometry(rect)


class TranslatePage(QWidget):
    go_to_scan = Signal()
    #: Süzgeç değişti ya da satırlar yenilendi (durum çubuğundaki "N / M satır" güncellensin).
    view_changed = Signal()
    #: Kısa, geçici bilgi (durum çubuğunda birkaç saniye gösterilir).
    hint = Signal(str)
    #: Kullanıcı "Elle sınır"ı değiştirdi (0: kapalı); proje ayarına yazılır.
    manual_limit_changed = Signal(int)
    machine_requested = Signal()
    uppercase_changed = Signal(object)  # UppercaseRules
    machine_action_requested = Signal(str)  # bağlam menüsü: seçili satırlara iş (çevir/yeniden çevir/düzelt)
    changes_requested = Signal()  # son makine işinin değişiklikleri
    history_requested = Signal(int)  # bir satırın çeviri geçmişi (satır kimliği)
    unapprove_requested = Signal(list)  # onayı kaldırılacak satır kimlikleri
    reflow_requested = Signal(list)  # satır sonları yeniden bölünecek satır kimlikleri
    cancel_machine = Signal()
    csv_export_requested = Signal()
    csv_import_requested = Signal()
    translation_export_requested = Signal()
    translation_import_requested = Signal()

    #: Seçim (ya da seçili satırların durumu) değişti; menü çubuğu seçime bağlı öğeleri günceller.
    selection_changed = Signal()

    def __init__(self, shortcuts: ShortcutRegistry | None = None) -> None:
        super().__init__()
        self.setObjectName("page")
        #: Tuşların tek kaynağı; verilmezse sayfa varsayılan tuşlarla tek başına çalışır (ana pencere kaydını verir).
        self.shortcuts = shortcuts if shortcuts is not None else ShortcutRegistry(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(14)
        lay.addWidget(
            title_row(
                "Çevir",
                "Çeviri sütununa çift tıklayarak yazın; değişiklikler hemen kaydedilir. "
                "⟦1⟧ gibi işaretler kontrol kodlarıdır ve çeviride aynı sırayla kalmalıdır.",
                icon="languages",
            )
        )
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        to_scan = button("Metinleri Tara adımına git", "primary")
        to_scan.clicked.connect(self.go_to_scan)
        self.empty = EmptyState(
            "Henüz metin aktarılmadı",
            "“Metinleri Tara” adımından sonra metinler burada görünür.",
            to_scan,
        )
        self.stack.addWidget(self.empty)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)
        self.banner = Banner(closable=True)
        cl.addWidget(self.banner)
        # Birincil eylem süzgeç satırının sağındadır; gerisi menü çubuğundadır.
        self.machine_button = button("Otomatik Çeviri", "primary", icon="sparkles")
        self.machine_button.clicked.connect(self.machine_requested)
        self.changes_button = QAction("Son İşin Değişiklikleri…", self)
        self.changes_button.triggered.connect(self.changes_requested)
        self.changes_button.setEnabled(False)
        self.changes_button.setToolTip(NO_CHANGES_TIP)
        self.shortcuts.bind("translate.changes", self.changes_button)
        self.shortcuts.changed.connect(self._shortcut_changed)
        self._refresh_machine_tip()

        # Makine çevirisi sürerken görünen şerit.
        self.run_panel = QWidget()
        run = QHBoxLayout(self.run_panel)
        run.setContentsMargins(0, 0, 0, 0)
        self.run_label = label("", "muted")
        self.run_bar = QProgressBar()
        self.run_bar.setTextVisible(False)
        self.run_cancel = button("İptal", icon="x")
        self.run_cancel.clicked.connect(self._on_cancel_machine)
        self.follow_box = QCheckBox("Canlı izle")
        self.follow_box.setChecked(True)
        self.follow_box.setToolTip(
            tip_html(
                "Açıkken tablo, her parti yazıldıkça o satırlara kayar. Yeni yazılan satırlar her durumda kısa "
                "süre sarı vurgulanır."
            )
        )
        run.addWidget(self.run_label, 1)
        run.addWidget(self.follow_box)
        run.addWidget(self.run_bar, 1)
        run.addWidget(self.run_cancel)
        self.run_panel.hide()
        cl.addWidget(self.run_panel)

        self._fit = FitConfig()
        self._kinds = CodeKinds({})
        self._last_commit_error: str | None = None
        self._syncing = False
        self._pane_layout: str | None = "?"  # henüz uygulanmadı
        self._pane_room = True  # seçili konumda panele yer var mı (yerleşim oturdukça `_check_pane_room` günceller)
        self._pane_timer = QTimer(self)
        self._pane_timer.setSingleShot(True)
        self._pane_timer.setInterval(0)
        self._pane_timer.timeout.connect(self._check_pane_room)
        #: Bul ve Değiştir'in yazma yolu (iş kimliği, geçmiş ve durum kuralları ana pencerede); satırları ya da hata
        #: olursa None döndürür.
        self.replace_fn: Callable[[list[tuple[int, str]]], list[TranslationRow] | None] | None = None
        self.view_actions = ViewActions(self, self.shortcuts)
        self.view_actions.symbols_changed.connect(lambda _on: self._apply_view())
        self.view_actions.align_changed.connect(lambda _align: self._apply_view())
        self.view_actions.pane_changed.connect(lambda _pane: self._apply_pane())
        self.view_actions.pane_visible_changed.connect(self._pane_visible_changed)
        self.card = Card("Çeviri tablosu")
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Ara…")
        self.search.setToolTip("Orijinal metinde, çeviride ve anahtarda arar.")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(110)  # dar pencerede arama kutusu süzgeçlerden önce ezilmesin
        self.status_filter = QComboBox()
        # Dosya/grup ve anahtar süzgeçleri sütun başlığındaki huniyle açılır (Excel tarzı, çoklu seçim).
        self.group_filter = ValueFilter("Dosya ve grup")
        self.key_filter = ValueFilter("Anahtar")
        filters.addWidget(self.search, 2)
        filters.addWidget(self.status_filter)
        # Süzgeç etkinken satırların neden azaldığını gösterir; süzgeç yokken görünmez (kalıcı düğme değil).
        self.filter_chip = QToolButton()
        self.filter_chip.setProperty("role", "link")
        self.filter_chip.setText("Süzgeç etkin · Temizle")
        self.filter_chip.setToolTip("Arama ve süzgeçlerin hepsini kaldırır.")
        self.filter_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filter_chip.clicked.connect(self._clear_filters)
        self.filter_chip.hide()
        filters.addWidget(self.filter_chip)
        filters.addStretch(1)
        # Görünüm seçenekleri menü çubuğundadır (Görünüm menüsü); eylemler burada yaşar, tablo durumu bunlara bağlıdır.
        self.wrap_box = QAction("Metni Kaydır", self, checkable=True)
        self.wrap_box.setChecked(True)
        self.wrap_box.setToolTip(
            "Açıkken uzun metinler ve satır sonları hücre içinde gerçek satırlara kaydırılır, tamamı görünür. "
            "Kapalıyken her satır tek satır yüksekliğinde kalır."
        )
        self.previous_box = QAction("Önceki Çeviri Sütunu", self, checkable=True)
        self.previous_box.setToolTip(NO_CHANGES_TIP)
        self.previous_box.setEnabled(False)
        self.colors_box = QAction("Sorunları Renkle Göster", self, checkable=True)
        self.colors_box.setChecked(True)
        self.colors_box.setToolTip(issue_legend_html())
        self.shortcuts.bind("view.wrap", self.wrap_box)
        self.shortcuts.bind("view.previous", self.previous_box)
        self.shortcuts.bind("view.issue_colors", self.colors_box)
        self.error_rows_box = QAction("Hatalı Satırları Vurgula", self, checkable=True)
        self.error_rows_box.setToolTip("Hatası olan satırların arka planı hata rengine boyanır (dışa aktarılmazlar).")
        self.shortcuts.bind("view.error_rows", self.error_rows_box)
        # Birincil eylem: tablonun sağ üstünde, panel düğmesinin solunda.
        filters.addWidget(self.machine_button)
        # Panel göster/gizle: tablonun sağ üstünde küçük simge düğmesi (Görünüm menüsüyle aynı eylem).
        self.pane_button = QToolButton()
        self.pane_button.setDefaultAction(self.view_actions.pane_toggle)
        self.pane_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.pane_button.setAutoRaise(True)
        filters.addWidget(self.pane_button)
        self.card.body.addLayout(filters)

        self.model = TranslationModel()
        self.model.setParent(self)  # model sayfayla birlikte yok olsun (geç kalan sinyaller ölü tabloya gitmesin)
        self.proxy = TranslationFilter()
        self.proxy.setSourceModel(self.model)
        self.table = FitTableView()
        self.filter_header = FilterHeader(self.table)
        self.table.setHorizontalHeader(self.filter_header)
        self.table.setModel(self.proxy)
        self.source_delegate = MarkedDelegate(self.table, "source")
        self.translation_delegate = TranslationDelegate(self.table)
        self.table.setItemDelegateForColumn(COL_SOURCE, self.source_delegate)
        self.table.setItemDelegateForColumn(COL_TRANSLATION, self.translation_delegate)
        self.table.setItemDelegateForColumn(COL_PREVIOUS, HtmlDelegate(self.table))
        self.table.setItemDelegateForColumn(COL_STATUS, StatusDelegate(self.table))
        self.table.setColumnHidden(COL_PREVIOUS, True)
        # No en solda; Önceki çeviri, karşılaştırması kolay olsun diye Çeviri sütununun hemen yanında görünür.
        self.table.horizontalHeader().moveSection(self.table.horizontalHeader().visualIndex(COL_NO), 0)
        self.table.horizontalHeader().moveSection(
            self.table.horizontalHeader().visualIndex(COL_PREVIOUS),
            self.table.horizontalHeader().visualIndex(COL_TRANSLATION) + 1,
        )
        for col in (COL_FILE, COL_KEY):
            self.table.setItemDelegateForColumn(col, _ElideLeftDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        # Yalnızca tablo odaktayken: çeviri hücresi düzenlenirken Ctrl+C kendi düzenleyicisinde çalışır.
        copy_keys = QShortcut(QKeySequence(QKeySequence.StandardKey.Copy), self.table)
        copy_keys.setContext(Qt.ShortcutContext.WidgetShortcut)
        copy_keys.activated.connect(lambda: self.copy_to_clipboard("both"))
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setMinimumHeight(120)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)  # her sütun sürüklenerek ayarlanır
        h.setStretchLastSection(False)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h.setMinimumSectionSize(_MIN_COLUMN_WIDTH)
        h.setSectionsClickable(True)
        h.setSortIndicatorShown(True)
        h.setSortIndicatorClearable(True)
        h.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        h.sortIndicatorChanged.connect(self._sort_changed)
        self.find_bar = FindBar(self, shortcuts=self.shortcuts)
        self.find_bar.closed.connect(self.table.setFocus)
        self.find_window = FindWindow(self.find_bar, self.table, self)
        self.card.body.addWidget(self.table, 1)
        self.settings: QSettings | None = None
        self._machine_running = False
        self.fitter = ColumnFitter(self.table, _NARROW_COLUMNS, {**_FLEX_COLUMNS, COL_PREVIOUS: _PREVIOUS_FLEX})
        self.fitter.resized.connect(self._schedule_fit_rows)
        self.column_menu = HeaderColumnMenu(
            self.table,
            {**_MENU_COLUMNS, **_MENU_COLUMNS_EXTRA},
            frozenset({COL_SOURCE, COL_TRANSLATION}),
            self.fitter,
        )
        self.column_menu.toggled.connect(self._column_toggled)
        self.filter_header.set_filter(COL_FILE, self.group_filter)
        self.filter_header.set_filter(COL_KEY, self.key_filter)
        self.filter_header.filter_clicked.connect(self._open_filter)
        self._project_key: str | None = None
        self._pending_filters: tuple[str, str] | None = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._fit_rows)
        # Süzgeç değişince görünümün başa dönmemesi için seçili satıra dönüş, yerleşim oturduktan sonra yapılır.
        self._scroll_row_id: int | None = None
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(0)
        self._scroll_timer.timeout.connect(self._scroll_row_into_view)
        self.table.verticalScrollBar().valueChanged.connect(lambda _v: self._schedule_fit_rows())
        self.table.verticalScrollBar().valueChanged.connect(lambda _v: self.find_bar.view_scrolled())
        self.wrap_box.toggled.connect(self._set_wrap)
        self.colors_box.toggled.connect(self._set_issue_colors)
        self.error_rows_box.toggled.connect(self._set_error_rows)
        self.previous_box.toggled.connect(self._show_previous)
        self.follow_box.toggled.connect(
            lambda on: self.settings.setValue("translate/follow", "1" if on else "0") if self.settings else None
        )
        self._fit_rows()

        self.pane = EditorPane()
        self.pane.manual_limit_changed.connect(self.manual_limit_changed)
        self.pane.commit_requested.connect(self._on_pane_commit)
        self.pane.navigate_requested.connect(self._navigate)
        self.pane.approve_requested.connect(self._approve_from_pane)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.card)
        self.splitter.addWidget(self.pane)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.splitterMoved.connect(lambda *_args: self._save_pane_sizes())
        cl.addWidget(self.splitter, 1)
        self.stack.addWidget(content)
        self.content = content

        self.search.textChanged.connect(self._refilter)
        self.status_filter.currentIndexChanged.connect(self._refilter)
        self.group_filter.changed.connect(self._filters_edited)
        self.key_filter.changed.connect(self._filters_edited)
        self.model.dataChanged.connect(lambda *_args: self.find_bar.rows_changed())
        self.model.modelReset.connect(self.find_bar.rows_changed)
        self.model.commit_failed.connect(lambda text: self.banner.show_message("danger", text))
        self.model.commit_failed.connect(self._remember_commit_error)
        selection = self.table.selectionModel()
        selection.selectionChanged.connect(lambda *_args: self._sync_pane())
        selection.selectionChanged.connect(lambda *_args: self.selection_changed.emit())
        selection.currentChanged.connect(lambda *_args: self._sync_pane())
        self.proxy.rowsRemoved.connect(lambda *_args: self._sync_pane())
        self.proxy.layoutChanged.connect(lambda *_args: self._sync_pane())
        self.proxy.modelReset.connect(lambda *_args: self._sync_pane())
        self.model.dataChanged.connect(lambda *_args: self._refresh_idle_pane())
        self._apply_pane()
        self._sync_pane(force=True)

    # --- tablo düzeni: sütun genişlikleri, sözcük kaydırma ---------------------------------

    def bind_settings(self, settings: QSettings) -> None:
        """Kayıtlı sütun genişliklerini ve kaydırma tercihini geri yükler."""
        self.settings = settings
        self.fitter.bind_settings(settings, "translate/column_widths")
        self.column_menu.bind_settings(settings, "translate/hidden_columns")
        self.wrap_box.setChecked(str(settings.value("translate/wrap", "1")) != "0")
        self.colors_box.setChecked(str(settings.value("translate/issue_colors", "1")) != "0")
        self.error_rows_box.setChecked(str(settings.value("translate/error_rows", "0")) == "1")
        self.follow_box.setChecked(str(settings.value("translate/follow", "1")) != "0")
        self.view_actions.bind_settings(settings)
        self.find_window.bind_settings(settings)
        self._apply_view()
        self._apply_pane()

    def set_manual_limit(self, limit: int) -> None:
        """Projenin kayıtlı "Elle sınır"ını panele yükler (0: kapalı); sinyal yaymaz."""
        self.pane.set_manual_limit(limit)

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self.find_window.suspend()  # sayfa görünmezken gizli tabloda arama/değiştirme yapılmasın

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.find_window.resume()
        self.fitter.fit()
        self._schedule_fit_rows()
        self._pane_timer.start()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:  # yazı boyutu değişince satır yükseklikleri yeniden hesaplanır
            self._schedule_fit_rows()

    def _sort_changed(self, column: int, order: Qt.SortOrder) -> None:
        self.model.sort_by(column, order)
        self.table.scrollToTop()
        self._refilter()

    def _refresh_machine_tip(self) -> None:
        key = self.shortcuts.text("translate.auto")
        self.machine_button.setToolTip(tip_html(f"{_MACHINE_TIP} ({key})" if key else _MACHINE_TIP))

    def _shortcut_changed(self, command_id: str) -> None:
        if command_id == "translate.auto":
            self._refresh_machine_tip()

    def refresh_legend(self) -> None:
        """Sorun renk açıklamasını geçerli temayla yeniler (Görünüm menüsü açılırken; tema değişmiş olabilir)."""
        self.colors_box.setToolTip(issue_legend_html())

    def _set_error_rows(self, on: bool) -> None:
        self.model.error_rows = on
        self.table.viewport().update()
        if self.settings is not None:
            self.settings.setValue("translate/error_rows", "1" if on else "0")

    def _set_issue_colors(self, on: bool) -> None:
        self.model.issue_colors = on
        self.table.viewport().update()
        if self.settings is not None:
            self.settings.setValue("translate/issue_colors", "1" if on else "0")

    # --- düzenleme paneli: yerleşim, seçim eşleşmesi, kayıt -----------------------------------

    def set_fit_config(self, config: FitConfig) -> None:
        """Sığdırma ayarı (panelin sayacı) ve kod türleri (çipler) buradan gelir."""
        self._fit = config
        self.set_code_kinds(config.kinds)

    def flush_pending(self) -> None:
        """Panelde kaydedilmemiş metin varsa kaydettirir (pencere kapanırken, proje değişirken)."""
        self.pane.flush()

    def _pane_has_room(self) -> bool:
        """Seçili konumda panel, tablo kartını en küçük ölçüsünün altına sıkıştırmadan sığıyor mu?"""
        self._relayout()  # bölme ölçüsü güncel olsun
        handle = self.splitter.handleWidth()
        if self.view_actions.pane == PANE_RIGHT:
            return self.splitter.width() >= self.card.minimumSizeHint().width() + PANE_MIN_WIDTH + handle
        needed = self.card.minimumSizeHint().height() + self.pane.minimumSizeHint().height() + handle
        return self.splitter.height() >= needed

    def _wanted_pane_layout(self) -> str | None:
        """Panelin gösterileceği yer: kullanıcının seçtiği konum (`"bottom"`, `"right"`) ya da `None`.

        Konum hiçbir zaman kendiliğinden değişmez (altta seçiliyken sağa geçmez). Panel kapalıysa ya da seçili
        konumda yer yoksa gizlenir: tablo ezilmez; yer açılınca panel kendiliğinden döner. Kullanıcının açık/kapalı
        seçimi (`view_actions.pane_visible`) bundan etkilenmez.
        """
        if not self.view_actions.pane_visible or not self._pane_room:
            return None
        return self.view_actions.pane

    def _pane_visible_changed(self, visible: bool) -> None:
        """Panel açılmak istenip yer yoksa kullanıcıya bir kez nedeni söylenir (panel gizli kalır)."""
        self._apply_pane()
        if visible and self.isVisible():
            self._check_pane_room()
            if not self._pane_room:
                self.hint.emit("Panel için yer yok; pencereyi büyütün ya da paneli sağa alın.")

    def _check_pane_room(self) -> None:
        """Yerleşim oturduktan sonra (zamanlayıcıyla) panele yer olup olmadığına bakar."""
        if not self.isVisible() or self.splitter.height() <= 0:
            return
        room = self._pane_has_room()
        if room == self._pane_room:
            return
        self._pane_room = room
        # Bildirim şeridi yer kaplayıp tabloyu daha da sıkıştırırdı; neden gizli olduğu düğmenin ipucunda yazar.
        self.view_actions.set_pane_room(room)
        self._apply_pane()

    def _relayout(self) -> None:
        """Panel görünür/gizli olunca yerleşimi hemen yeniler (bir olay turu bayat geometri kalmasın)."""
        layout = self.layout()
        if layout is not None:
            layout.activate()

    def _apply_pane(self) -> None:
        layout = self._wanted_pane_layout()
        if layout == self._pane_layout:
            return
        self._pane_layout = layout
        if layout is None:
            self.pane.flush()
            self.pane.hide()
            self._relayout()
            return
        horizontal = layout == "right"
        self.splitter.setOrientation(Qt.Orientation.Horizontal if horizontal else Qt.Orientation.Vertical)
        # Sağda en az PANE_MIN_WIDTH genişlik. Altta sabit yükseklik verilmez: bölücü panelin güncel en küçük
        # ölçüsünü (minimumSizeHint) kullanır, çipler veya uyarılar sonradan belirince panel de büyür.
        self.pane.setMinimumSize(PANE_MIN_WIDTH if horizontal else 0, 0)
        self.pane.show()
        self._restore_pane_sizes(layout)
        self._relayout()

    def _restore_pane_sizes(self, position: str) -> None:
        saved = str(self.settings.value(f"translate/pane_sizes_{position}", "")) if self.settings is not None else ""
        try:
            sizes = [int(x) for x in saved.split(",")] if saved else []
        except ValueError:
            sizes = []
        if len(sizes) == 2 and all(size > 0 for size in sizes):
            self.splitter.setSizes(sizes)
            return
        total = self.splitter.width() if position == "right" else self.splitter.height()
        total = max(total, 600)
        self.splitter.setSizes([int(total * 0.62), int(total * 0.38)])

    def _save_pane_sizes(self) -> None:
        if self.settings is None or not self.pane.isVisibleTo(self):
            return
        position = "right" if self.splitter.orientation() == Qt.Orientation.Horizontal else "bottom"
        self.settings.setValue(f"translate/pane_sizes_{position}", ",".join(str(x) for x in self.splitter.sizes()))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._check_pane_room()  # görünürken hemen; ilk yerleşimde ölçü bayat olabilir, zamanlayıcı yeniden bakar
        self._pane_timer.start()

    def _sync_pane(self, force: bool = False) -> None:
        """Panelde tablonun geçerli satırını gösterir; önce önceki satırın bekleyen metni kaydedilir."""
        if self._syncing:
            return
        self._syncing = True
        try:
            current = self.current_row()
            selected = self.selected_rows()
            row = current if current is not None else (selected[0] if selected else None)
            count = max(len(selected), 1)
            if not force and row is not None and self.pane.row_id == row.id:
                self.pane.set_selected_count(count)
                return
            self.pane.flush()
            if self.pane.has_pending():
                return  # kayıt başarısız: yazılan metin kaybolmasın, panel eski satırda kalır
            current = self.current_row()  # kayıt satırı güncellemiş olabilir
            if current is None and selected:
                selected = self.selected_rows()
                current = selected[0] if selected else None
            self._show_in_pane(current, count)
        finally:
            self._syncing = False

    def _show_in_pane(self, row: TranslationRow | None, count: int = 1) -> None:
        if row is None:
            self.pane.set_row(None, lambda _n: "other", None)
            return
        self.pane.set_row(
            row,
            kind_of_row(row, self._kinds),
            self._fit.rules_for_row(row),
            count,
            number=self.model.number(row.id),
        )

    def _refresh_idle_pane(self) -> None:
        """Satır dışarıdan değiştiyse (satır içi düzenleme, geri alma, toplu işlem) panel bayat metin göstermesin."""
        row_id = self.pane.row_id
        if row_id is None or self._syncing or self.pane.has_pending():
            return
        row = self.model.row_by_id(row_id)
        if row is not None and not self.pane.shows(row):
            self._refresh_pane_row(row_id)

    def _remember_commit_error(self, text: str) -> None:
        self._last_commit_error = text

    def _commit_error(self) -> str | None:
        return self._last_commit_error

    def _on_pane_commit(self, row_id: int, text: str) -> None:
        self._last_commit_error = None
        applied = self.model.apply([(row_id, text)])
        error = self._commit_error()  # `apply` başarısız olunca `commit_failed` sinyaliyle doldurulur
        if applied:
            if not self._syncing and self.pane.row_id == row_id:
                self._refresh_pane_row(row_id)
        elif error is not None:
            self.pane.show_error(error)

    def _refresh_pane_row(self, row_id: int) -> None:
        row = self.model.row_by_id(row_id)
        if row is None:
            return
        edit = self.pane.translation_edit
        position = edit.textCursor().position()
        self._show_in_pane(row, max(len(self.selected_rows()), 1))
        cursor = edit.textCursor()
        cursor.setPosition(min(position, len(edit.toPlainText())))
        edit.setTextCursor(cursor)

    def _navigate(self, step: int) -> None:
        total = self.proxy.rowCount()
        if not total:
            return
        index = self.table.currentIndex().row()
        target = (0 if step > 0 else total - 1) if index < 0 else min(max(index + step, 0), total - 1)
        self._select_proxy_row(target)
        self.pane.translation_edit.setFocus()

    def _approve_from_pane(self) -> None:
        self.pane.flush()
        row = self.current_row()
        if row is not None:
            self.approve([row])
            self._refresh_pane_row(row.id)

    def set_code_kinds(self, kinds: CodeKinds) -> None:
        """Proje kod türü eşlemesi (çip simgeleri ve renkleri bundan gelir)."""
        self._kinds = kinds
        self.source_delegate.set_kinds(kinds)
        self.translation_delegate.set_kinds(kinds)
        self.table.viewport().update()
        self._schedule_fit_rows()
        if self.pane.row_id is not None and not self.pane.has_pending():
            self._refresh_pane_row(self.pane.row_id)  # çip renkleri/simge türleri paneli de etkiler

    def set_view(self, symbols: bool, align: str) -> None:
        """Sembolleri ve hizayı hücrelere uygular (yalnızca görünüm)."""
        wrap = self.table.wordWrap()
        for delegate in (self.source_delegate, self.translation_delegate):
            delegate.configure(symbols=symbols, align=align, wrap=wrap)
        self.pane.set_view(symbols, align)
        self.model.refresh_display()
        self._schedule_fit_rows()

    def set_live_context(self, context: LiveContext) -> None:
        """Anlık denetimin bağlamı: durum simgesi, ipucu ve renkler bundan beslenir."""
        self.model.set_live_context(context)
        self._schedule_fit_rows()

    def set_spell(self, spell: SpellChecker | None, extra: frozenset[str]) -> None:
        """Yazım denetleyicisi: panelde ve çeviri hücrelerinde yazım hatalı sözcüklerin altı çizilir."""
        self.pane.set_spell(spell, extra)
        self.translation_delegate.set_spell(spell, extra)
        self.table.viewport().update()
        self._schedule_fit_rows()

    def _apply_view(self) -> None:
        self.set_view(self.view_actions.symbols_on, self.view_actions.align)

    def _set_wrap(self, on: bool) -> None:
        self.table.setWordWrap(on)
        self.model.wrap = on
        self._apply_view()
        self.model.refresh_display()
        if self.settings is not None:
            self.settings.setValue("translate/wrap", "1" if on else "0")
        self._schedule_fit_rows()

    def set_qa_issues(self, issues: list[QaIssue], checked: list[TranslationRow]) -> None:
        """Kontrol Et sonuçlarını tabloya bağlar; durum hücresi uzayabileceği için satır yükseklikleri yenilenir."""
        self.model.set_qa_issues(issues, checked)
        self._schedule_fit_rows()

    def _schedule_fit_rows(self) -> None:
        self._resize_timer.start(_RESIZE_DELAY_MS)

    def _fit_rows(self) -> None:
        """Ekrandaki satırların (ve çevresinin) yüksekliğini ayarlar: kaydırma açıksa metnin tamamına göre,
        kapalıysa tek satır. Binlerce satırın hepsini ölçmek arayüzü saniyelerce dondururdu; ekran dışındaki
        satırlar ekrana gelince (kaydırma, süzgeç, sıralama) ölçülür."""
        vh = self.table.verticalHeader()
        single = self.table.fontMetrics().height() + 14
        vh.setDefaultSectionSize(single)
        total = self.proxy.rowCount()
        if not total:
            return
        wrap = self.table.wordWrap()
        first = max(self.table.rowAt(0), 0)
        last = self.table.rowAt(self.table.viewport().height() - 1)
        last = total - 1 if last < 0 else last
        for row in range(max(first - _ROW_MARGIN, 0), min(last + _ROW_MARGIN, total - 1) + 1):
            if wrap:
                self.table.resizeRowToContents(row)
            else:
                self.table.setRowHeight(row, single)

    # --- veri --------------------------------------------------------------------------

    def set_rows(self, rows: list[TranslationRow]) -> None:
        self.find_bar.close_bar()  # eski satırlardaki arama yeni proje/satırlarda anlamsızdır
        self.pane.flush()  # kaydedilmemiş panel metni satırlar yenilenmeden önce kaydedilir (kimlikle)
        # Satırlar yeniden kurulurken önceki süzgeçten kalan "seçili satıra dön" isteği geçersizdir.
        self._scroll_row_id = None
        self._scroll_timer.stop()
        self.model.set_rows(rows)
        # "Makine" ve "Redakte" durumları yalnızca o durumda satır varsa listelenir.
        present = {r.status for r in rows}
        current_status = self.status_filter.currentData()
        self.status_filter.blockSignals(True)
        self.status_filter.clear()
        self.status_filter.addItem("Tüm durumlar", "")
        for s in Status:
            if s not in (Status.MACHINE, Status.REDACTED) or s in present:
                self.status_filter.addItem(status_icon(s), STATUS_LABELS[s], s.value)
        self.status_filter.addItem(issue_icon("warning"), "Hata veya uyarısı olan satırlar", ISSUES_FILTER)
        if self.model.previous:
            self.status_filter.addItem(f"Son işte değişenler ({format_int(len(self.model.previous))})", CHANGED_FILTER)
        self.status_filter.setCurrentIndex(max(self.status_filter.findData(current_status), 0))
        self.status_filter.blockSignals(False)
        groups: dict[str, int] = {}
        keys: dict[str, int] = {}
        for r in rows:
            g = row_group(r)
            groups[g] = groups.get(g, 0) + 1
            k = r.context or r.key
            keys[k] = keys.get(k, 0) + 1
        self.group_filter.set_values(groups)
        self.key_filter.set_values(keys)
        if self._pending_filters is not None:  # proje değişti: kayıtlı süzgeçler artık değerler bilindiği için yüklenir
            # Sütunu gizli olan (başlıkta huni görünmeyen) süzgeç yok sayılıp kayıttan da silinir: satırları
            # görünmeden gizlemesin. Sütun gizleme uygulama geneli, süzgeç proje başınadır.
            dropped = False
            for col, vf, saved in (
                (COL_FILE, self.group_filter, self._pending_filters[0]),
                (COL_KEY, self.key_filter, self._pending_filters[1]),
            ):
                if self.table.isColumnHidden(col):
                    dropped = dropped or bool(saved)
                else:
                    vf.load_json(saved)
            self._pending_filters = None
            if dropped:
                self._save_filters()
        self.stack.setCurrentWidget(self.content if rows else self.empty)
        self.banner.show_message("danger", "")
        self._refilter()
        self._schedule_fit_rows()

    def show_notice(self, state: str, text: str) -> None:
        self.banner.show_message(state, text)

    def _refilter(self) -> None:
        # Süzgeç gevşeyince görünüm başa dönmesin: seçili (geçerli) satır görünür kalırsa oraya dönülür.
        current = self.current_row()
        self.proxy.update(
            str(self.status_filter.currentData()),
            self.group_filter.selected,
            self.key_filter.selected,
            self.search.text(),
        )
        self.filter_chip.setVisible(self.find_filters_active())
        self.view_changed.emit()
        self._schedule_fit_rows()
        if current is not None:
            self._scroll_row_id = current.id
            self._scroll_timer.start()
        number = _NUMBER_QUERY.fullmatch(self.search.text().strip())
        if number is not None:
            self.go_to_number(int(number.group(1)))

    def go_to_number(self, number: int) -> bool:
        """No'su verilen satırı seçer ve ortalar (arama kutusuna "#120" yazılınca). Satır yoksa ya da süzgeçle
        gizliyse False döner."""
        row = self.model.row_by_number(number)
        source = None if row is None else self.model.position(row.id)
        if source is None:
            return False
        index = self.proxy.mapFromSource(self.model.index(source, 0))
        if not index.isValid():
            return False
        self._select_proxy_row(index.row(), center=True)
        return True

    # --- Dosya/grup ve Anahtar süzgeçleri (başlıktaki huni) ----------------------------------

    def open_filter(self, col: int) -> FilterPopup:
        """Sütunun süzgeç panelini başlığın altında açar (huniye tıklayınca)."""
        vf = self.group_filter if col == COL_FILE else self.key_filter
        popup = FilterPopup(vf, self.table)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        header = self.table.horizontalHeader()
        corner = QPoint(header.sectionViewportPosition(col), header.height())
        popup.popup_below(header.mapToGlobal(corner))
        return popup

    def _open_filter(self, col: int) -> None:
        self.open_filter(col)

    def _filters_edited(self) -> None:
        self._save_filters()
        self._refilter()

    def _column_toggled(self, col: int, hidden: bool) -> None:
        """Gizlenen sütunun süzgeci kaldırılır: görünmeyen bir süzgeç satırları sessizce gizlemesin."""
        if hidden and col == COL_FILE:
            self.group_filter.clear()
        elif hidden and col == COL_KEY:
            self.key_filter.clear()
        self._schedule_fit_rows()

    def set_project_key(self, key: str | None) -> None:
        """Süzgeç seçimlerinin hatırlanacağı proje kimliği (ör. dosya yolu); `set_rows`tan önce çağrılır."""
        self._project_key = key
        self.group_filter.selected = None
        self.key_filter.selected = None
        self._pending_filters = None
        if key is None or self.settings is None:
            return
        base = self._filters_setting(key)
        self._pending_filters = (
            str(self.settings.value(f"{base}/groups", "")),
            str(self.settings.value(f"{base}/keys", "")),
        )

    @staticmethod
    def _filters_setting(key: str) -> str:
        return "translate/filters/" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def _save_filters(self) -> None:
        if self.settings is None or self._project_key is None:
            return
        base = self._filters_setting(self._project_key)
        for name, vf in (("groups", self.group_filter), ("keys", self.key_filter)):
            text = vf.to_json()
            if text:
                self.settings.setValue(f"{base}/{name}", text)
            else:
                self.settings.remove(f"{base}/{name}")

    def _scroll_row_into_view(self) -> None:
        """Bekleyen satırı görünür alanda tutar; satır süzgeçten çıktıysa bir şey yapmaz."""
        row_id, self._scroll_row_id = self._scroll_row_id, None
        if row_id is not None:
            self._scroll_to_row(row_id)

    def _scroll_to_row(self, row_id: int) -> None:
        """Kimliği verilen satırı görünür alanda tutar (arama temizlenince görünüm başa dönmez)."""
        source = self.model.position(row_id)
        if source is None:
            return
        index = self.proxy.mapFromSource(self.model.index(source, COL_TRANSLATION))
        if index.isValid():
            self.table.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

    def selected_rows(self) -> list[TranslationRow]:
        """Seçili satırlar (tablodaki sırayla). Tüm satır seçimi olduğundan seçim aralıkları gezilir;
        `selectedRows()` her satırı sütun sütun sorguladığından 50.000 satırda saniyelerce sürer."""
        rows = self.model.rows
        proxy = self.proxy
        picked: set[int] = set()
        for part in self.table.selectionModel().selection():  # type: ignore[attr-defined]
            picked.update(range(part.top(), part.bottom() + 1))
        return [rows[proxy.mapToSource(proxy.index(r, 0)).row()] for r in sorted(picked)]

    def filtered_rows(self) -> list[TranslationRow]:
        """Arama ve filtrelere uyan (tabloda görünen) satırlar."""
        return [
            self.model.rows[self.proxy.mapToSource(self.proxy.index(i, 0)).row()] for i in range(self.proxy.rowCount())
        ]

    # --- gezinme ve seçim -----------------------------------------------------------------------

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    # --- Bul ve Değiştir çubuğu ----------------------------------------------------------------

    def open_find(self, replace: bool) -> None:
        """Tablonun üstünde Bul çubuğunu açar (`replace`: değiştir alanıyla)."""
        if self.model.rows:
            self.find_bar.open_bar(replace)

    def find_next(self) -> None:
        """Bul çubuğu açıkken sonraki eşleşme; değilse sonraki bakılacak satır."""
        if not self.find_bar.isHidden():
            self.find_bar.next()
        else:
            self.next_open()

    def find_previous(self) -> None:
        """Bul çubuğu açıkken önceki eşleşme; değilse önceki bakılacak satır."""
        if not self.find_bar.isHidden():
            self.find_bar.previous()
        else:
            self.next_open(-1)

    def find_rows(self, scope: int) -> list[TranslationRow]:
        if scope == SCOPE_VISIBLE:
            return self.filtered_rows()
        if scope == SCOPE_ALL:
            return list(self.model.rows)
        return self.selected_rows()

    def find_current_id(self) -> int | None:
        row = self.current_row()
        return None if row is None else row.id

    def find_order(self, row_id: int) -> int:
        return self.model.position(row_id) or 0

    def find_view_ids(self) -> frozenset[int]:
        """Tabloda görünen (ve çevresindeki) satırların kimlikleri; önizleme yalnızca bunlar için hesaplanır."""
        total = self.proxy.rowCount()
        if not total:
            return frozenset()
        first = max(self.table.rowAt(0), 0)
        last = self.table.rowAt(self.table.viewport().height() - 1)
        last = min(first + _VIEW_ROWS_CAP, total - 1) if last < 0 else last
        return frozenset(
            self.model.rows[self.proxy.mapToSource(self.proxy.index(i, 0)).row()].id
            for i in range(max(first - _ROW_MARGIN, 0), min(last + _ROW_MARGIN, total - 1) + 1)
        )

    def find_filters_active(self) -> bool:
        return bool(
            self.proxy.status or self.proxy.text or self.proxy.groups is not None or self.proxy.keys is not None
        )

    def find_clear_filters(self) -> None:
        self._clear_filters()

    def find_goto(self, row_id: int) -> bool:
        """Eşleşen satırı odağı çalmadan seçer ve görünür yapar. Satırı süzgeç gizliyorsa süzgeçlere
        dokunulmaz ve False döner."""
        source = self.model.position(row_id)
        if source is None:
            return False
        index = self.proxy.mapFromSource(self.model.index(source, 0))
        if not index.isValid():
            return False
        self._select_proxy_row(index.row())
        return True

    def find_apply(self, changes: list[tuple[int, str]]) -> list[TranslationRow] | None:
        return None if self.replace_fn is None else self.replace_fn(changes)

    def find_set_marks(self, marks: FindMarks) -> None:
        preview_changed = self.model.find_marks.preview != marks.preview
        self.model.set_find_marks(marks)
        if preview_changed:
            self._schedule_fit_rows()  # önizleme metni satır yüksekliğini değiştirir

    def current_row(self) -> TranslationRow | None:
        index = self.table.currentIndex()
        if not index.isValid():
            return None
        return self.model.rows[self.proxy.mapToSource(index).row()]

    def next_open(self, step: int = 1) -> None:
        """Sonraki (`step` = -1: önceki) bakılacak satır: onaylanmamış (çevrilmemiş, makine, redakte, hatalı),
        uca gelince öbür uca döner."""
        total = self.proxy.rowCount()
        start = self.table.currentIndex().row()
        for offset in range(1, total + 1):
            i = (start + step * offset) % total
            r = self.model.rows[self.proxy.mapToSource(self.proxy.index(i, 0)).row()]
            if r.status != Status.APPROVED and r.source.strip():
                self._select_proxy_row(i)
                self.table.setFocus()
                return
        self.show_notice("success", "Görünen satırların hepsi onaylanmış.")

    def select_row(self, row_id: int) -> None:
        """Kimliği verilen satırı (gerekirse filtreleri temizleyerek) seçer."""
        source = self.model.position(row_id)
        if source is None:
            return
        index = self.proxy.mapFromSource(self.model.index(source, 0))
        if not index.isValid():
            self._clear_filters()
            index = self.proxy.mapFromSource(self.model.index(source, 0))
        if index.isValid():
            self._select_proxy_row(index.row())
            self.table.setFocus()

    def reveal_in_place(self, row_id: int) -> None:
        """Satırı, arama ve süzgeçleri kaldırıp tablodaki gerçek yerinde gösterir.

        Arama sonucunda tek başına görünen satırın komşularını görebilmek içindir: satırı gizleyen
        bütün süzgeçler temizlenir ve satır ekranın ortasına kaydırılır.
        """
        source = self.model.position(row_id)
        if source is None:
            return
        cleared = self._clear_filters()
        index = self.proxy.mapFromSource(self.model.index(source, 0))
        if not index.isValid():  # süzgeçler temizlendiğine göre buraya düşmemeli
            return
        self._select_proxy_row(index.row(), center=True)
        self.table.setFocus()
        if cleared:
            self.show_notice("success", "Arama ve süzgeçler temizlendi; satır kendi yerinde gösteriliyor.")

    def _clear_filters(self) -> bool:
        """Arama metnini, durum, grup ve anahtar süzgeçlerini birlikte temizler; bir şey değiştiyse True döner."""
        changed = (
            bool(self.search.text())
            or bool(str(self.status_filter.currentData() or ""))
            or self.group_filter.active
            or self.key_filter.active
        )
        if not changed:
            return False
        widgets = (self.search, self.status_filter, self.group_filter, self.key_filter)
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.search.clear()
            self.status_filter.setCurrentIndex(0)
            self.group_filter.clear()
            self.key_filter.clear()
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._save_filters()
        self._refilter()
        return True

    def _select_proxy_row(self, i: int, center: bool = False) -> None:
        # Açıkça seçilen satır, süzgeç değişikliğinden kalan "seçili satıra dön" isteğini geçersiz kılar.
        self._scroll_row_id = None
        self._scroll_timer.stop()
        index = self.proxy.index(i, COL_TRANSLATION)
        self.table.setCurrentIndex(index)
        self.table.selectRow(i)
        hint = QAbstractItemView.ScrollHint.PositionAtCenter if center else QAbstractItemView.ScrollHint.EnsureVisible
        self.table.scrollTo(index, hint)

    def approve(self, rows: list[TranslationRow]) -> None:
        """Makine veya dış redaksiyondan gelen çevirileri değiştirmeden onaylar."""
        if rows and self.model.apply([(r.id, r.translation) for r in rows]):
            self.show_notice("success", f"{format_int(len(rows))} satır onaylandı.")

    def _show_context_menu(self, pos: QPoint) -> None:
        """Sağ tık menüsü: tıklanan satır seçili değilse yalnızca o satır seçilir."""
        index = self.table.indexAt(pos)
        selection = self.table.selectionModel()
        if index.isValid() and not selection.isRowSelected(index.row(), index.parent()):
            self.table.selectRow(index.row())
        if not selection.selectedRows():
            return
        self.build_context_menu(self.selected_rows()).popup(self.table.viewport().mapToGlobal(pos))

    def _menu_action(self, menu: QMenu, text: str, icon_name: str | None, command: str | None = None) -> QAction:
        """Bağlam menüsü satırı; kısayolu varsa kayıt defterindeki güncel tuş sağ sütunda görünür."""
        key = display_text(self.shortcuts.sequence(command)) if command else ""
        action = menu.addAction(f"{text}\t{key}" if key else text)
        if icon_name is not None:
            bind_icon(action, icon_name)
        return action

    @staticmethod
    def _submenu(menu: QMenu, title: str, icon_name: str) -> QMenu:
        sub = menu.addMenu(title)
        sub.setToolTipsVisible(True)
        bind_icon(sub.menuAction(), icon_name)
        return sub

    def build_context_menu(self, rows: list[TranslationRow]) -> QMenu:
        """Satırların sağ tık menüsü: gruplu ve kısa; sayılar parantez içinde, kısayollar sağ sütunda."""
        menu = QMenu(self.table)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.setToolTipsVisible(True)
        counts = self._counts(rows)
        translate = self._submenu(menu, "Çevir", "languages")
        for action, text, command, n, icon_name in (
            (ACTION_TRANSLATE, "Çevir", "translate.selected", counts.translate, "languages"),
            (ACTION_RETRANSLATE, "Yeniden çevir", "translate.retranslate", counts.retranslate, "refresh-cw"),
            (ACTION_REVISE, "Redaksiyon", "translate.revise", counts.revise, "pen-line"),
        ):
            # Onaylı satırlar da sayılır: yeniden çeviri ve düzeltme penceresinde "onaylananlara da uygula"
            # kendiliğinden işaretlenir.
            act = self._menu_action(translate, f"{text} ({format_int(n)})", icon_name, command)
            act.setEnabled(n > 0 and not self._machine_running)
            act.triggered.connect(lambda _=False, a=action: self.machine_action_requested.emit(a))
        approve = self._menu_action(
            menu, f"Onayla ({format_int(counts.approvable)})", "circle-check", "translate.approve"
        )
        approve.setToolTip("Makine çevirisini veya dış redaksiyonu değiştirmeden onaylar.")
        approve.setEnabled(counts.approvable > 0)
        approve.triggered.connect(self.approve_selected)
        unapprove = self._menu_action(
            menu, f"Onayı kaldır ({format_int(counts.approved)})", "circle-x", "translate.unapprove"
        )
        unapprove.setToolTip("Metni değiştirmeden durumu “Makine”ye döndürür (yanlışlıkla onaylanan satırlar için).")
        unapprove.setEnabled(counts.approved > 0)
        unapprove.triggered.connect(self.unapprove_selected)
        menu.addSeparator()

        edit = self._submenu(menu, "Düzenle", "pen-line")
        reflow = self._menu_action(edit, "Satırları yeniden böl", "wrap-text", "edit.reflow")
        reflow.setToolTip(
            "Çevirideki satır sonlarını kaldırıp satırı sınıra ya da orijinale göre dengeli yeniden böler."
        )
        reflow.setEnabled(counts.with_translation > 0 and not self._machine_running)
        reflow.triggered.connect(self.reflow_selected)
        source = self._menu_action(edit, "Orijinali yaz", "copy", "edit.copy_source")
        source.setToolTip("Orijinal metni çeviri olarak yazar. Çevrilmeyecek metinler (özel adlar, sayılar) için.")
        source.setEnabled(not self._machine_running)
        source.triggered.connect(self.copy_source_selected)
        clear = self._menu_action(edit, "Temizle", "eraser", "edit.clear")
        clear.setToolTip("Seçili satırların çevirisini siler.")
        clear.setEnabled(counts.with_translation > 0 and not self._machine_running)
        clear.triggered.connect(self.clear_selected)

        copy_menu = self._submenu(menu, "Kopyala", "copy")
        copy_both = copy_menu.addAction(
            f"Orijinal ve çeviri\t{display_text(QKeySequence(QKeySequence.StandardKey.Copy))}"
        )
        bind_icon(copy_both, "copy")
        copy_both.triggered.connect(lambda: self.copy_to_clipboard("both"))
        self._menu_action(copy_menu, "Yalnızca orijinal", "file-text").triggered.connect(
            lambda: self.copy_to_clipboard("source")
        )
        self._menu_action(copy_menu, "Yalnızca çeviri", "languages").triggered.connect(
            lambda: self.copy_to_clipboard("translation")
        )

        export = self._submenu(menu, "Dışa aktar", "file-up")
        count = format_int(len(rows))
        self._menu_action(export, f"Dış redaksiyon dosyası ({count})…", "user-check").triggered.connect(
            self.csv_export_requested
        )
        self._menu_action(export, f"Dış çeviri dosyası ({count})…", "languages").triggered.connect(
            self.translation_export_requested
        )

        upper = self._submenu(menu, "Büyük harf", "case-sensitive")
        rules = self.model.uppercase
        marked = upper.addAction("Seçili satırlar (i → İ)")
        marked.setCheckable(True)
        marked.setChecked(all(rules.applies(r.file, r.key, row_group(r)) for r in rows))
        marked.setToolTip(
            "Menü ve başlık gibi büyük harfle çizilen metinlerde i harfi İ yazılır. Tablosu işaretliyken "
            "işareti kaldırırsanız yalnızca bu satırlarda uygulanmaz."
        )
        marked.triggered.connect(lambda on: self._set_uppercase_rows(rows, on))
        for group in sorted({row_group(r) for r in rows}):
            whole = upper.addAction(f"“{group}” tablosunun tamamı")
            whole.setCheckable(True)
            whole.setChecked(group in rules.groups)
            whole.setToolTip("Bu tablodaki bütün metinlerde i harfi İ yazılır.")
            whole.triggered.connect(lambda on, g=group: self._set_uppercase_group(g, on))

        menu.addSeparator()
        history = self._menu_action(menu, "Geçmiş…", "history", "translate.history")
        history.setEnabled(len(rows) == 1)
        history.triggered.connect(self.history_selected)
        reveal = self._menu_action(menu, "Yerinde göster", "scan-search")
        reveal.setToolTip(
            "Arama metnini ve süzgeçleri temizleyip satırı tablodaki gerçek yerinde, komşu satırlarla birlikte "
            "gösterir. Tek satır seçiliyken kullanılabilir."
        )
        reveal.setEnabled(len(rows) == 1)
        reveal.triggered.connect(self.reveal_selected)
        return menu

    # --- seçili satırlara iş (menü çubuğu, bağlam menüsü ve kısayollar aynı yolu kullanır) --------

    @staticmethod
    def _counts(rows: list[TranslationRow]) -> SelectionCounts:
        return SelectionCounts(
            selected=len(rows),
            translate=len(target_rows(rows, ACTION_TRANSLATE, include_approved=False)),
            retranslate=len(target_rows(rows, ACTION_RETRANSLATE, include_approved=True)),
            revise=len(target_rows(rows, ACTION_REVISE, include_approved=True)),
            approvable=sum(1 for r in rows if r.status in (Status.MACHINE, Status.REDACTED)),
            approved=sum(1 for r in rows if r.status == Status.APPROVED),
            with_translation=sum(1 for r in rows if r.translation),
        )

    def selection_counts(self) -> SelectionCounts:
        """Seçili satırların sayıları (menü öğelerinin etkinliği buradan hesaplanır)."""
        return self._counts(self.selected_rows())

    def approve_selected(self) -> None:
        self.approve([r for r in self.selected_rows() if r.status in (Status.MACHINE, Status.REDACTED)])

    def unapprove_selected(self) -> None:
        ids = [r.id for r in self.selected_rows() if r.status == Status.APPROVED]
        if ids:
            self.unapprove_requested.emit(ids)

    def reflow_selected(self) -> None:
        rows = self.selected_rows()
        if any(r.translation for r in rows):
            self.reflow_requested.emit([r.id for r in rows])

    def history_selected(self) -> None:
        rows = self.selected_rows()
        if len(rows) == 1:
            self.history_requested.emit(rows[0].id)

    def reveal_selected(self) -> None:
        rows = self.selected_rows()
        if len(rows) == 1:
            self.reveal_in_place(rows[0].id)

    def set_uppercase(self, rules: UppercaseRules) -> None:
        self.model.uppercase = rules
        self._redraw_keys()

    def _redraw_keys(self) -> None:
        if self.model.rows:
            self.model.dataChanged.emit(
                self.model.index(0, COL_KEY), self.model.index(len(self.model.rows) - 1, COL_KEY)
            )

    def _set_uppercase_rows(self, rows: list[TranslationRow], on: bool) -> None:
        rules = self.model.uppercase
        for r in rows:
            rules = rules.with_row(r.file, r.key, row_group(r), on)
        self._apply_uppercase(rules)

    def _set_uppercase_group(self, group: str, on: bool) -> None:
        self._apply_uppercase(self.model.uppercase.with_group(group, on))

    def _apply_uppercase(self, rules: UppercaseRules) -> None:
        self.set_uppercase(rules)
        self.uppercase_changed.emit(rules)

    def copy_to_clipboard(self, what: str) -> None:
        """Seçili satırların metnini panoya koyar: "source", "translation" veya "both" (orijinal + çeviri)."""
        indexes = sorted(self.table.selectionModel().selectedRows(), key=lambda i: i.row())  # tablodaki sırayla
        rows = [self.model.rows[self.proxy.mapToSource(i).row()] for i in indexes]
        if not rows:
            return
        QApplication.clipboard().setText(clipboard_text(rows, what))
        self.show_notice("success", f"{format_int(len(rows))} satırın metni panoya kopyalandı.")

    def copy_source_selected(self) -> None:
        """Seçili satırlarda orijinal metni çeviri olarak yazar."""
        self.model.apply([(r.id, r.source) for r in self.selected_rows()])

    def clear_selected(self) -> None:
        """Seçili satırların çevirisini siler."""
        self.model.apply([(r.id, "") for r in self.selected_rows() if r.translation])

    # --- makine çevirisi şeridi -----------------------------------------------------------

    def set_last_changes(self, previous: dict[int, str]) -> None:
        """Son işte değişen satırlar (kimlik → önceki çeviri): düğme, "Önceki çeviri" sütunu ve süzgeç güncellenir."""
        count = len(previous)
        self.changes_button.setText(
            f"Son İşin Değişiklikleri ({format_int(count)})…" if count else "Son İşin Değişiklikleri…"
        )
        self.changes_button.setEnabled(count > 0)
        self.changes_button.setToolTip("" if count else NO_CHANGES_TIP)
        self.model.set_previous(previous)
        self.previous_box.setEnabled(count > 0)
        self.previous_box.setToolTip(_PREVIOUS_TIP if count else NO_CHANGES_TIP)
        if not count and self.previous_box.isChecked():
            self.previous_box.setChecked(False)
        current = self.status_filter.currentData()
        self.status_filter.blockSignals(True)
        idx = self.status_filter.findData(CHANGED_FILTER)
        if idx >= 0:
            self.status_filter.removeItem(idx)
        if count:
            self.status_filter.addItem(f"Son işte değişenler ({format_int(count)})", CHANGED_FILTER)
        self.status_filter.setCurrentIndex(max(self.status_filter.findData(current), 0))
        self.status_filter.blockSignals(False)
        if current == CHANGED_FILTER or self.status_filter.currentData() != current:
            self._refilter()

    def _show_previous(self, on: bool) -> None:
        self.fitter.set_hidden(COL_PREVIOUS, not on)
        if on and self.fitter.user_sized and self.table.columnWidth(COL_PREVIOUS) < _MIN_PREVIOUS_WIDTH:
            # Elle ayarlanmış düzende de okunur olsun.
            self.table.horizontalHeader().resizeSection(
                COL_PREVIOUS, max(_MIN_PREVIOUS_WIDTH, self.table.columnWidth(COL_TRANSLATION))
            )
        self._schedule_fit_rows()

    def show_live(self, ids: list[int]) -> None:
        """Az önce yazılan satırları kısa süre vurgular; "Canlı izle" açıksa tabloyu onlara kaydırır."""
        if not ids:
            return
        self.model.set_flash(ids, True)
        QTimer.singleShot(_FLASH_MS, self, lambda: self.model.set_flash(ids, False))  # sayfa kapanırsa çalışmaz
        pos = self.model.position(ids[-1])
        if self.follow_box.isChecked() and pos is not None:
            index = self.proxy.mapFromSource(self.model.index(pos, 0))
            if index.isValid():
                self.table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        self._schedule_fit_rows()

    def set_machine_running(self, running: bool) -> None:
        if running:
            self.pane.flush()
        self.pane.set_read_only(running)
        self.find_bar.set_busy(running)
        self._machine_running = running
        self.run_panel.setVisible(running)
        self.machine_button.setEnabled(not running)
        if running:
            self.run_cancel.setEnabled(True)
            self.run_cancel.setText("İptal")
            self.run_bar.setRange(0, 0)
            self.run_label.setText("Sağlayıcıya bağlanılıyor…")

    def update_machine_progress(self, done: int, total: int, message: str) -> None:
        if total > 0:
            self.run_bar.setRange(0, total)
            self.run_bar.setValue(done)
        self.run_label.setText(message)

    def _on_cancel_machine(self) -> None:
        self.run_cancel.setEnabled(False)
        self.run_cancel.setText("Durduruluyor…")
        self.cancel_machine.emit()
