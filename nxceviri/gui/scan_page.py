"""Adım 2 — Metinleri Tara: tarama, ilerleme ve okunaklı tarama raporu."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.formats.detection import KIND_LABELS, LIKELIHOOD_LABELS, FileKind, TextLikelihood
from nxceviri.core.formats.registry import all_plugins, kind_label
from nxceviri.core.formats.scanner import CONFIDENCE_LABELS, ScanEntry, ScanReport
from nxceviri.core.languages import same_language
from nxceviri.core.pipeline import (
    available_languages,
    default_source_language,
    importable_entries,
    language_label,
    path_language,
    source_label,
    unsupported_text_kinds,
)
from nxceviri.gui.issue_chips import Disclosure
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import (
    Banner,
    Card,
    EmptyState,
    ErrorState,
    PageHeader,
    ProgressPanel,
    button,
    format_int,
    format_size,
    label,
    tip_html,
)

COL_IMPORT, COL_LIKELIHOOD, COL_KIND, COL_DETAIL, COL_LANGUAGE, COL_PATH, COL_SIZE, COL_ORIGIN = range(8)
_COLUMNS = ("Aktar", "Metin olasılığı", "Tür", "Ayrıntı", "Dil", "Dosya yolu", "Boyut", "Kaynak")
#: Sütun başlıklarının üstüne gelince görünen açıklamalar (kodda gerçekte gösterilen değerlere göre).
_HEADER_TIPS = {
    COL_IMPORT: (
        "İşaretli dosyaların metinleri çeviri tablosuna aktarılır. Kutusu olmayan dosyalar için henüz destek yok."
    ),
    COL_LIKELIHOOD: (
        "Dosyanın metin içerme ihtimali. Yüksek: biçimi ya da adı metne işaret ediyor; "
        "Olası: metin barındırabilir ama emin değil."
    ),
    COL_KIND: "Dosyanın tanınan biçimi (ör. MSBT, Unity). Aktarma, biçime özel eklentiyle yapılır.",
    COL_DETAIL: "Taramanın dosya hakkında bulduğu kısa not, ör. “Unity AssetBundle”.",
    COL_LANGUAGE: "Dosya yolundan anlaşılan dil. Anlaşılamazsa dosya, kaynak dile uymasa da aktarılır.",
    COL_PATH: "Dosyanın oyun içindeki yolu. İç içe arşivlerde “dış › iç” biçiminde gösterilir.",
    COL_SIZE: "Dosyanın oyundaki boyutu.",
    COL_ORIGIN: (
        "Dosyanın geldiği paket: Ana oyun, Güncelleme ya da DLC (ek içerik). "
        "Güncellemedeki dosya, ana oyundaki aynı yolun yerini alır."
    ),
}
_SORT_ROLE = Qt.ItemDataRole.UserRole + 1
#: Kısa, içeriğe göre boyutlanan sütunlar; hücre ipucu tam metni taşır.
_SHORT_COLUMNS = (COL_KIND, COL_DETAIL, COL_LANGUAGE)
#: Dosya yolu sütununun en az genişliği (piksel): dar pencerede yol kırpılır, kısa sütunlar değil.
_PATH_MIN = 160
_LIKELIHOOD_ORDER = {TextLikelihood.HIGH.value: 0, TextLikelihood.MEDIUM.value: 1, TextLikelihood.NONE.value: 2}
#: Süzgeç listesindeki görünüm seçenekleri.
MODE_CANDIDATES, MODE_ALL, MODE_UNKNOWN_LANGUAGE = "candidates", "all", "unknown_language"

_Index = QModelIndex | QPersistentModelIndex


class ScanTableModel(QAbstractTableModel):
    """Binlerce satırda akıcı çalışan sanal tablo modeli.

    "Aktar" sütunu, bir eklentinin tanıdığı (aktarılabilir) dosyalarda onay kutusu taşır. Seçim yalnızca bu
    modelde, bellekte tutulur; proje dosyasına yazılmaz: her taramada ve proje açılışında varsayılan küme
    yeniden kurulur (aktarılabilir ve dili kaynak dille uyumlu ya da bilinmeyen dosyalar işaretli).
    """

    #: İşaretli dosya kümesi değişti (kutu, toplu seçim ya da kaynak dil değişimi).
    selection_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[ScanEntry] = []
        self._importable: list[bool] = []
        self._language: list[str | None] = []
        self._enabled: list[bool] = []
        self._checked: list[bool] = []
        #: Kullanıcının elle yaptığı işaretler (satır → işaretli mi); kaynak dil değişse de korunur.
        self._manual: dict[int, bool] = {}
        self._source: str | None = None
        self._in_project: list[bool] = []
        self._default: list[bool] = []
        self._has_project = False

    def set_entries(
        self,
        entries: list[ScanEntry],
        importable: Collection[ScanEntry],
        source: str | None,
        in_project: Collection[str] = (),
    ) -> None:
        wanted = set(importable)
        project = set(in_project)
        self.beginResetModel()
        self.entries = entries
        self._importable = [e in wanted for e in entries]
        # Dil yalnızca dosya yolundan okunur; dosya adından tahmin yürütülmez (yanlış tahmin veri kaybettirir).
        self._language = [
            path_language(e.path) if ok else None for e, ok in zip(entries, self._importable, strict=True)
        ]
        self._manual = {}
        self._source = source
        # Projede aktarılmış dosya varsa varsayılan küme onlardır (önceki daraltma yeniden taramada korunur ve
        # yanlışlıkla yeniden aktarma dosya silmez); proje boşsa hepsi işaretli gelir.
        self._in_project = [e.path in project for e in entries]
        self._default = [e.path in project if project else True for e in entries]
        self._has_project = bool(project)
        self._enabled = [False] * len(entries)
        self._checked = [False] * len(entries)
        self._apply_source()
        self.endResetModel()
        self.selection_changed.emit()

    def set_source_language(self, code: str | None) -> None:
        """Kaynak dil değişti: başka dildeki dosyaların kutusu kapanır; elle yapılan işaretler korunur."""
        self._source = code
        self._apply_source()
        self._notify()

    def _apply_source(self) -> None:
        source = self._source
        for row, ok in enumerate(self._importable):
            lang = self._language[row]
            other = source is not None and lang is not None and not same_language(lang, source)
            self._enabled[row] = ok and not other
            self._checked[row] = self._enabled[row] and self._manual.get(row, self._default[row])

    def _notify(self) -> None:
        if self.entries:
            self.dataChanged.emit(self.index(0, COL_IMPORT), self.index(len(self.entries) - 1, COL_IMPORT))
        self.selection_changed.emit()

    # --- seçim -----------------------------------------------------------------------------

    def is_importable(self, row: int) -> bool:
        return self._importable[row]

    def is_enabled(self, row: int) -> bool:
        return self._enabled[row]

    def is_checked(self, row: int) -> bool:
        return self._checked[row]

    def language_of(self, row: int) -> str | None:
        return self._language[row]

    def has_unknown_language(self, row: int) -> bool:
        return self._importable[row] and self._language[row] is None

    def importable_count(self) -> int:
        return sum(self._importable)

    def checked_count(self) -> int:
        return sum(self._checked)

    def unchecked_not_in_project_count(self) -> int:
        """Projede olmayan, işaretsiz ama işaretlenebilir dosyalar (proje boşsa 0)."""
        if not self._has_project:
            return 0
        return sum(1 for r, ok in enumerate(self._enabled) if ok and not self._checked[r] and not self._in_project[r])

    def checked_unknown_language_count(self) -> int:
        return sum(1 for r, on in enumerate(self._checked) if on and self._language[r] is None)

    def selected_paths(self) -> set[str]:
        return {e.path for e, on in zip(self.entries, self._checked, strict=True) if on}

    def set_checked(self, rows: Iterable[int], value: bool) -> None:
        """Etkin kutuları işaretler ya da kaldırır (kapalı kutulara dokunulmaz)."""
        changed = False
        for row in rows:
            if self._enabled[row]:
                self._manual[row] = value
                self._checked[row] = value
                changed = True
        if changed:
            self._notify()

    def toggle(self, rows: Iterable[int]) -> None:
        """Etkin kutulardan biri bile boşsa hepsini işaretler; hepsi doluysa hepsini kaldırır."""
        usable = [r for r in rows if self._enabled[r]]
        if usable:
            self.set_checked(usable, not all(self._checked[r] for r in usable))

    # --- Qt modeli -------------------------------------------------------------------------

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        if role == Qt.ItemDataRole.ToolTipRole:
            return tip_html(_HEADER_TIPS[section])
        if role == Qt.ItemDataRole.TextAlignmentRole and section == COL_SIZE:
            return int(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )  # başlık, sağa yaslı hücrelerle aynı hizada
        return None

    def flags(self, index: _Index) -> Qt.ItemFlag:
        flags = super().flags(index)
        if index.column() == COL_IMPORT and self._importable[index.row()]:
            if self._enabled[index.row()]:
                return flags | Qt.ItemFlag.ItemIsUserCheckable
            return flags & ~Qt.ItemFlag.ItemIsEnabled  # kutu soluk çizilir (kaynak dilde değil)
        return flags

    def setData(self, index: _Index, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        row = index.row()
        if role != Qt.ItemDataRole.CheckStateRole or index.column() != COL_IMPORT or not self._enabled[row]:
            return False
        self.set_checked([row], value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value))
        return True

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        e = self.entries[row]
        col = index.column()
        if role == Qt.ItemDataRole.CheckStateRole and col == COL_IMPORT and self._importable[row]:
            return Qt.CheckState.Checked if self._checked[row] else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                "",
                LIKELIHOOD_LABELS[TextLikelihood(e.likelihood)],
                kind_label(e.kind),
                e.detail,
                self._language_text(row),
                e.path,
                format_size(e.size),
                source_label(e.origin),
            )[col]
        if role == _SORT_ROLE:
            return (
                int(not self._checked[row]),
                _LIKELIHOOD_ORDER[e.likelihood],
                e.kind,
                e.detail,
                self._language[row] or "~",
                e.path.lower(),
                e.size,
                e.origin,
            )[col]
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == COL_PATH:
                return e.path.replace(">", "  ›  ")
            if col in _SHORT_COLUMNS:
                return self.data(index) or None  # dar sütunda kırpılan metnin tamamı
            if col == COL_IMPORT:
                if not self._importable[row]:
                    return "Bu dosya türü için henüz metin aktarma desteği yok."
                if not self._enabled[row]:
                    return "Seçili kaynak dilde değil"
        if role == Qt.ItemDataRole.ForegroundRole and col == COL_LANGUAGE and self.has_unknown_language(row):
            return QBrush(QColor(current_tokens()["muted"]))
        if role == Qt.ItemDataRole.TextAlignmentRole and col == COL_SIZE:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def _language_text(self, row: int) -> str:
        if not self._importable[row]:
            return ""
        code = self._language[row]
        return language_label(code) if code else "Bilinmiyor"


class ScanFilterProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.mode = MODE_CANDIDATES
        self.kind = ""
        self.text = ""
        self.setSortRole(_SORT_ROLE)

    def update(self, mode: str, kind: str, text: str) -> None:
        self.beginFilterChange()
        self.mode = mode
        self.kind = kind
        self.text = text.casefold()
        self.endFilterChange()

    def filterAcceptsRow(self, source_row: int, source_parent: _Index) -> bool:
        model = self.sourceModel()
        assert isinstance(model, ScanTableModel)
        e = model.entries[source_row]
        if self.mode == MODE_UNKNOWN_LANGUAGE:
            if not model.has_unknown_language(source_row):
                return False
        elif self.mode == MODE_CANDIDATES and not e.is_text_candidate:
            return False
        if self.kind and e.kind != self.kind:
            return False
        return not self.text or self.text in e.path.casefold() or self.text in e.detail.casefold()


class _ElideDelegate(QStyledItemDelegate):
    """Dosya yolu ortadan (başı ve sonu görünür), diğer sütunlar sağdan kırpılır."""

    def initStyleOption(self, option: QStyleOptionViewItem, index: _Index) -> None:
        super().initStyleOption(option, index)
        if index.column() != COL_PATH:
            option.textElideMode = Qt.TextElideMode.ElideRight


class ScanTable(QTableView):
    """Boşluk tuşu, seçili satırların kutusunu değiştirir (etkin kutular; hepsi doluysa boşaltır)."""

    resized = Signal()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.resized.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        proxy = self.model()
        source = proxy.sourceModel() if isinstance(proxy, QSortFilterProxyModel) else None
        if (
            event.key() == Qt.Key.Key_Space
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
            and isinstance(proxy, QSortFilterProxyModel)
            and isinstance(source, ScanTableModel)
        ):
            source.toggle([proxy.mapToSource(i).row() for i in self.selectionModel().selectedRows()])
            event.accept()
            return
        super().keyPressEvent(event)


class ReportView(QWidget):
    rescan_requested = Signal()
    import_requested = Signal()
    #: Rapor durumu (durum, kısa metin, ayrıntılar): sayfa başlığındaki çipe yazılır.
    status_changed = Signal(str, str, list)

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        self.summary = Card("Özet")
        self.game_line = label(
            "",
            wrap=True,
            tip="“Olası metin dosyası”, metin içerebileceği düşünülen dosyadır (Metin olasılığı Yüksek ya da Olası). "
            "Hepsi aktarılamaz; aktarılabilenler tabloda işaretlidir.",
        )
        self.summary.body.addWidget(self.game_line)
        self.stats = QGridLayout()
        self.stats.setSpacing(10)
        self.stat_values: dict[str, Any] = {}
        self.stat_boxes: dict[str, QFrame] = {}
        for i, kind in enumerate(FileKind):
            box = QFrame()
            box.setObjectName("statCard")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(12, 10, 12, 10)
            value = label("0", "statValue")
            bl.addWidget(value)
            bl.addWidget(label(KIND_LABELS[kind], "muted", wrap=True))
            box.setToolTip(
                tip_html(
                    "Taramada bu türe giren dosya sayısı. Hepsinde metin olmayabilir; "
                    "metin olasılığı aşağıdaki tabloda görünür."
                )
            )
            self.stat_values[kind.value] = value
            self.stat_boxes[kind.value] = box
            self.stats.addWidget(box, i // 3, i % 3)
        self.summary.body.addLayout(self.stats)
        # Yeniden tara ve aktar düğmeleri sayfa başlığına yerleştirilir (ScanPage); kaynak dil bir ayar olduğu için
        # özet kartında kalır (en küçük pencerede başlığa sığmaz).
        self.rescan_button = button("Yeniden Tara", icon="refresh-cw")
        self.rescan_button.clicked.connect(self.rescan_requested)
        self.language_label = label("Kaynak dil:", "muted")
        self.language = QComboBox()
        self.language.setToolTip(
            tip_html("Oyunda aynı metin birden çok dilde var. Kaynak dili seçin; Türkçe metin bu dilin yerine yazılır.")
        )
        self.summary.header_right.addWidget(self.language_label)
        self.summary.header_right.addWidget(self.language)
        self.import_button = button("Aktar  →", "primary", icon="languages")
        self.import_button.setToolTip("Seçili dosyaların metinlerini çeviri tablosuna aktar")
        self.import_button.clicked.connect(self.import_requested)
        self.can_import = False
        self.has_language_choice = False
        #: Rapor eski (projedeki metin dosyası raporda yok); kendiliğinden aktarma yapılmaz.
        self._stale = False
        #: Çipin dayanağı (durum, not, uyarılar); desteklenen dosya yoksa None. Metni seçime göre kurulur.
        self._status: tuple[str, str, list[str]] | None = None
        lay.addWidget(self.summary)

        self.engine_card = Card("Tahmini oyun motoru")
        self.engine_line = label("", "cardTitle")
        self.engine_evidence = label("", "muted", wrap=True)
        self.engine_line.setToolTip(
            tip_html(
                "Güven, tahminin kaç farklı kanıta dayandığını gösterir: 3 ya da daha fazlası Yüksek, 2 Orta, "
                "1 Düşük. Motor tahmini yalnızca bilgidir; aktarılacak dosyaları etkilemez."
            )
        )
        self.engine_evidence.setToolTip(
            tip_html("Tahminin dayandığı izler. Her biri bir dosya türünü ve oyunda kaç tane bulunduğunu gösterir.")
        )
        self.engine_card.body.addWidget(self.engine_line)
        self.engine_details = Disclosure("Ayrıntılar")
        self.engine_details.toggle.setAccessibleName("Ayrıntılar")
        self.engine_details.toggle.setToolTip(tip_html("Tahminin dayandığı izleri gösterir ya da gizler."))
        self.engine_details.body_layout.addWidget(self.engine_evidence)
        self.engine_details.hide()  # kanıt yokken ya da rapor gelmeden görünmez
        self.engine_card.body.addWidget(self.engine_details)
        lay.addWidget(self.engine_card)

        # Dili anlaşılamayan dosyalar için uyarı; dosya kartının hemen üstünde durur.
        self.unknown_banner = Banner()
        self.unknown_banner.action_clicked.connect(self._show_unknown_only)
        lay.addWidget(self.unknown_banner)

        self.files_card = Card(
            "Metin dosyaları",
            hint="Metin içermesi muhtemel dosyalar. İç içe arşivlerdeki dosyalar “dış › iç” biçiminde gösterilir.",
        )
        filters = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem("Yalnızca metin adayları", MODE_CANDIDATES)
        self.mode.addItem("Tüm dosyalar", MODE_ALL)
        self.mode.addItem("Dili bilinmeyenler", MODE_UNKNOWN_LANGUAGE)
        self.kind = QComboBox()
        self.kind.addItem("Tüm türler", "")
        for kind in FileKind:
            self.kind.addItem(KIND_LABELS[kind], kind.value)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Dosya yolunda ara…")
        self.search.setClearButtonEnabled(True)
        filters.addWidget(self.mode)
        filters.addWidget(self.kind)
        filters.addWidget(self.search, 1)
        self.files_card.body.addLayout(filters)
        # Toplu seçim: yalnızca süzgeç ve aramaya göre görünen, kutusu etkin satırlara uygulanır. Bağlantılar kart
        # başlığının sağında durur: süzgeç satırına en küçük pencerede sığmazlar, ayrı satır da yer harcar.
        self.select_visible = QToolButton()
        self.select_visible.setText("Görünenleri seç")
        self.deselect_visible = QToolButton()
        self.deselect_visible.setText("Görünenlerin seçimini kaldır")
        for link, mark in ((self.select_visible, True), (self.deselect_visible, False)):
            link.setProperty("role", "link")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(lambda _checked=False, v=mark: self._check_visible(v))
            self.files_card.header_right.addWidget(link)

        self.model = ScanTableModel()
        self.proxy = ScanFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.table = ScanTable()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(COL_LIKELIHOOD, Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setItemDelegate(_ElideDelegate(self.table))
        self.table.setMinimumHeight(160)  # ~5 satır; sığmazsa sayfa kayar
        # Tercih edilen yükseklik yok sayılır: tablo kalan yüksekliği doldurur, sayfa gereksiz kaymaz.
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        h = self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for col in range(len(_COLUMNS)):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_PATH, QHeaderView.ResizeMode.Interactive)  # genişliğini `_fit_path` verir
        h.setSectionResizeMode(COL_IMPORT, QHeaderView.ResizeMode.Fixed)  # yalnızca bir onay kutusu taşır
        h.resizeSection(COL_IMPORT, 56)
        self.table.resized.connect(self._fit_path)
        h.sectionResized.connect(self._section_resized)
        self.files_card.body.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.count_label = label("", "muted")
        bottom.addWidget(self.count_label, 1)
        self.files_card.body.addLayout(bottom)
        lay.addWidget(self.files_card, 1)

        self.mode.currentIndexChanged.connect(self._refilter)
        self.kind.currentIndexChanged.connect(self._refilter)
        self.search.textChanged.connect(self._refilter)
        self.language.currentIndexChanged.connect(self._language_changed)
        self.model.selection_changed.connect(self._update_selection)

    def _refilter(self) -> None:
        self.proxy.update(str(self.mode.currentData()), str(self.kind.currentData()), self.search.text())
        self._update_counts()
        self._fit_path()

    def _section_resized(self, section: int) -> None:
        if section != COL_PATH:  # kısa sütunlar içerikle değişince yol kalanı alır
            self._fit_path()

    def _fit_path(self) -> None:
        """Dosya yolu, diğer sütunlardan kalan genişliği alır (en az `_PATH_MIN`); dar pencerede kırpılan odur.

        `Stretch` kullanılmaz: kısa sütunların içeriği pencereyi aşınca yol 34 pikseline kadar ezilirdi.
        """
        h = self.table.horizontalHeader()
        others = sum(h.sectionSize(c) for c in range(len(_COLUMNS)) if c != COL_PATH)
        width = max(_PATH_MIN, self.table.viewport().width() - others)
        if h.sectionSize(COL_PATH) != width:
            h.resizeSection(COL_PATH, width)

    def _source_language(self) -> str | None:
        code = self.language.currentData()
        return str(code) if code else None

    def _language_changed(self) -> None:
        self.model.set_source_language(self._source_language())

    def selected_paths(self) -> set[str]:
        """İşaretli dosyaların yolları: aktarma yalnızca bunları alır."""
        return self.model.selected_paths()

    def auto_import_ready(self) -> bool:
        """Seçim kendiliğinden aktarılacak kadar kesin mi: aktarılabilir dosya seçili, rapor güncel ve birden çok dil
        varsa seçili her dosyanın dili biliniyor (bilinmeyen dil başka dil olabilir; o zaman kullanıcı seçer)."""
        if not self.can_import or self._stale or not self.model.checked_count():
            return False
        return not self.has_language_choice or not self.model.checked_unknown_language_count()

    def _check_visible(self, value: bool) -> None:
        rows = (self.proxy.mapToSource(self.proxy.index(i, 0)).row() for i in range(self.proxy.rowCount()))
        self.model.set_checked(rows, value)

    def _show_unknown_only(self) -> None:
        self.mode.setCurrentIndex(self.mode.findData(MODE_UNKNOWN_LANGUAGE))

    def _update_counts(self) -> None:
        text = f"{format_int(self.proxy.rowCount())} dosya gösteriliyor"
        if self.model.importable_count():
            text += f" · {format_int(self.model.checked_count())} dosya aktarılacak"
            missing = self.model.unchecked_not_in_project_count()
            if missing:
                text += f" · {format_int(missing)} projede olmayan dosya işaretsiz"
        self.count_label.setText(text)

    def _update_selection(self) -> None:
        """İşaretli dosya kümesi değişince sayaç, düğme, uyarı şeridi ve başlıktaki çip güncellenir."""
        self._update_counts()
        total = self.model.importable_count()
        chosen = self.model.checked_count()
        self.import_button.setEnabled(chosen > 0)
        self.import_button.setToolTip(
            "" if chosen else tip_html("Aktarmak için tabloda en az bir dosyayı işaretleyin.")
        )
        unknown = self.model.checked_unknown_language_count()
        if unknown > 1:
            self.unknown_banner.show_message(
                "warning",
                f"{format_int(unknown)} dosyanın dili anlaşılamadı; hepsi aktarılacak. "
                "İstemediklerinizin işaretini kaldırın.",
                "Yalnızca bunları göster",
            )
        else:
            self.unknown_banner.show_message("", "")
        if self._status is None:
            return
        state, note, warnings = self._status
        if warnings:
            text = f"{len(warnings)} uyarı"
        elif not chosen:
            state, text = "warning", "Hiç dosya seçilmedi"
        elif chosen == total:
            text = f"{format_int(total)} dosya aktarılabilir"
        else:
            text = f"{format_int(chosen)} / {format_int(total)} dosya seçili"
        self.status_changed.emit(state, text, [f"{note} {format_int(chosen)} dosya işaretli.", *warnings])

    def show_report(self, report: ScanReport, imported_paths: Collection[str] = ()) -> None:
        versions = f"ana oyun v{report.base_version}" if report.base_version is not None else "ana oyun yok"
        if report.update_version is not None:
            versions += f", güncelleme v{report.update_version}"
        total = len(report.entries)
        self.game_line.setText(
            f"<b>{report.game_name or 'Adsız oyun'}</b> &nbsp;·&nbsp; "
            f"Oyun kimliği (TitleID) {report.title_id} &nbsp;·&nbsp; "
            f"{versions} &nbsp;·&nbsp; {format_int(total)} dosya &nbsp;·&nbsp; "
            f"{format_int(len(report.text_candidates))} olası metin dosyası"
        )
        for kind, n in report.counts.items():
            self.stat_values[kind].setText(format_int(n))
        # Yalnızca bulunan türler gösterilir; onlarca "0" kutusu önemli bilgiyi gömüyordu.
        for box in self.stat_boxes.values():
            self.stats.removeWidget(box)
            box.hide()
        shown = [k for k in self.stat_boxes if report.counts.get(k, 0)] or [FileKind.OTHER.value]
        for i, kind_value in enumerate(shown):
            self.stats.addWidget(self.stat_boxes[kind_value], i // 3, i % 3)
            self.stat_boxes[kind_value].show()
        eng = report.engine
        self.engine_details.toggle.setChecked(False)  # her rapor kapalı başlar
        if eng.engine == "unknown":
            self.engine_line.setText("Belirlenemedi  —  bilinen bir motorun izine rastlanmadı")
            self.engine_evidence.clear()
        else:
            self.engine_line.setText(f"{eng.label}  —  güven: {CONFIDENCE_LABELS[eng.confidence]}")
            self.engine_evidence.setText("Kanıtlar: " + "; ".join(eng.evidence))
        self.engine_details.setVisible(bool(eng.evidence) and eng.engine != "unknown")
        supported = importable_entries(report)
        others = unsupported_text_kinds(report)
        self.can_import = bool(supported)
        languages = available_languages(report)
        self.language.blockSignals(True)  # kaynak dil modele aşağıda, varsayılan seçimle birlikte bildirilir
        self.language.clear()
        for code in languages:
            self.language.addItem(language_label(code), code)
        default = default_source_language(languages)
        self.language.setCurrentIndex(max(self.language.findData(default), 0))
        self.language.blockSignals(False)
        has_choice = bool(supported) and len(languages) > 1
        self.has_language_choice = has_choice
        # Projede aktarılmış ama raporda olmayan metin dosyası varsa rapor eskidir (ör. eklentiden önce taranmış).
        listed = {e.path for e in supported}
        missing = sum(1 for path in imported_paths if path not in listed)
        stale = f"{format_int(missing)} metin dosyası raporda yok. Yeniden Tara'ya basın." if missing else ""
        self._stale = bool(stale)
        if stale and not supported:
            self._status = None
            self.status_changed.emit("warning", "Tarama eski", [stale, *report.warnings])
        elif supported:
            formats = sorted({kind_label(e.kind) for e in supported})
            note = f"{format_int(len(supported))} dosyadan metin aktarılabilir ({', '.join(formats)})."
            if has_choice:
                note += f" {len(languages)} dil var; başka dildeki dosyalar işaretlenmez."
            if others:
                note += f" Henüz desteklenmeyen metin türleri de var: {', '.join(others)}."
            warnings = [stale, *report.warnings] if stale else list(report.warnings)
            self._status = ("warning" if warnings else "success", note, warnings)
        else:
            note = (
                "Bu oyunda henüz desteklenen bir metin biçimi bulunamadı"
                + (f" (bulunan: {', '.join(others)})" if others else "")
                + ". Şu an desteklenen biçimler: "
                + ", ".join(p.label for p in all_plugins())
                + "."
            )
            self._status = None
            self.status_changed.emit("warning", "Desteklenmeyen biçim", [note, *report.warnings])
        self.model.set_entries(report.entries, supported, self._source_language(), imported_paths)
        for link in (self.select_visible, self.deselect_visible):
            link.setVisible(bool(supported))  # seçilecek kutu yoksa bağlantılar işlevsiz kalırdı
        # Aktarılabilir dosya yoksa kutu ve dil sütunları boş kalırdı.
        self.table.setColumnHidden(COL_IMPORT, not supported)
        self.table.setColumnHidden(COL_LANGUAGE, not supported)
        self.mode.setCurrentIndex(self.mode.findData(MODE_CANDIDATES if report.text_candidates else MODE_ALL))
        self._refilter()


class ScanPage(QWidget):
    start_scan = Signal()
    cancel = Signal()
    go_back = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(14)
        self.header = PageHeader(
            "Metinleri Tara",
            "scan-search",
            "Oyun dosyaları açılır, güncelleme uygulanır ve metin dosyaları bulunur. Oyun dosyalarınız "
            "yalnızca okunur.",
        )
        lay.addWidget(self.header)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        self.start_button = button("Tara ve Aktar", "primary", icon="scan-search")
        self.start_button.clicked.connect(self.start_scan)
        self.empty = EmptyState("Henüz tarama yapılmadı", "Büyük oyunlarda birkaç dakika sürebilir.")
        self.loading = ProgressPanel()
        self.loading.cancel_requested.connect(self.cancel)
        self.error = ErrorState()
        self.retry_button = button("Tekrar Dene", "primary", icon="refresh-cw")
        self.retry_button.clicked.connect(self.start_scan)
        self.back_button = button("Oyunu Ekle adımına dön")
        self.back_button.clicked.connect(self.go_back)
        self.report = ReportView()
        self.report.status_changed.connect(self._report_status)
        # Başlık eylemleri soldan sağa; her an yalnızca geçerli duruma ait olanlar görünür (`_sync_header`).
        for widget in (
            self.back_button,
            self.retry_button,
            self.report.rescan_button,
            self.report.import_button,
            self.start_button,
        ):
            self.header.add_action(widget)
        self._mode = "empty"
        self._status: tuple[str, str, list[str]] = ("", "", [])
        self.report_scroll = QScrollArea()
        self.report_scroll.setWidgetResizable(True)
        self.report_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.report_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.report_scroll.setWidget(self.report)
        for w in (self.empty, self.loading, self.error, self.report_scroll):
            self.stack.addWidget(w)
        self._sync_header()

    def show_empty(self, auto_import: bool = True) -> None:
        """Tarama yok. `auto_import`: proje boş, tarama bitince metinler kendiliğinden aktarılacak."""
        self.start_button.setText("Tara ve Aktar" if auto_import else "Taramayı Başlat")
        self.stack.setCurrentWidget(self.empty)
        self._set_mode("empty")

    def show_loading(self, stage: str) -> None:
        self.loading.start(stage)
        self.stack.setCurrentWidget(self.loading)
        self._set_mode("loading")

    def show_error(self, text: str, title: str = "Tarama tamamlanamadı") -> None:
        self.error.title.setText(title)
        self.error.show_error(text)
        self.stack.setCurrentWidget(self.error)
        self._set_mode("error")

    def show_report(self, report: ScanReport, imported_paths: Collection[str] = ()) -> None:
        """`imported_paths`: projede zaten aktarılmış dosyaların yolları (ana pencere verir)."""
        self.report.show_report(report, imported_paths)
        self.stack.setCurrentWidget(self.report_scroll)
        self._set_mode("report")

    def _report_status(self, state: str, text: str, details: list[str]) -> None:
        self._status = (state, text, details)
        self._sync_header()

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._sync_header()

    def _sync_header(self) -> None:
        """Başlıkta yalnızca geçerli duruma ait eylemler ve (raporda) durum çipi görünür; kaynak dil özet kartında."""
        report = self._mode == "report"
        self.start_button.setVisible(self._mode == "empty")
        self.retry_button.setVisible(self._mode == "error")
        self.back_button.setVisible(self._mode == "error")
        self.report.rescan_button.setVisible(report)
        self.report.import_button.setVisible(report and self.report.can_import)
        choice = report and self.report.has_language_choice
        self.report.language_label.setVisible(choice)
        self.report.language.setVisible(choice)
        if report:
            self.header.chip.show_status(*self._status)
        else:
            self.header.chip.show_status("", "")
