"""Adım 2 — Metinleri Tara: tarama, ilerleme ve okunaklı tarama raporu."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QScrollArea,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.formats.detection import KIND_LABELS, LIKELIHOOD_LABELS, FileKind, TextLikelihood
from nxceviri.core.formats.registry import all_plugins, kind_label
from nxceviri.core.formats.scanner import CONFIDENCE_LABELS, ScanEntry, ScanReport
from nxceviri.core.pipeline import (
    available_languages,
    default_source_language,
    importable_entries,
    language_label,
    source_label,
    unsupported_text_kinds,
)
from nxceviri.gui.widgets import (
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

_COLUMNS = ("Metin olasılığı", "Tür", "Ayrıntı", "Dosya yolu", "Boyut", "Kaynak")
_SORT_ROLE = Qt.ItemDataRole.UserRole + 1
_LIKELIHOOD_ORDER = {TextLikelihood.HIGH.value: 0, TextLikelihood.MEDIUM.value: 1, TextLikelihood.NONE.value: 2}

_Index = QModelIndex | QPersistentModelIndex


class ScanTableModel(QAbstractTableModel):
    """Binlerce satırda akıcı çalışan sanal tablo modeli."""

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[ScanEntry] = []

    def set_entries(self, entries: list[ScanEntry]) -> None:
        self.beginResetModel()
        self.entries = entries
        self.endResetModel()

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        return None

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        e = self.entries[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                LIKELIHOOD_LABELS[TextLikelihood(e.likelihood)],
                kind_label(e.kind),
                e.detail,
                e.path,
                format_size(e.size),
                source_label(e.origin),
            )[col]
        if role == _SORT_ROLE:
            return (_LIKELIHOOD_ORDER[e.likelihood], e.kind, e.detail, e.path.lower(), e.size, e.origin)[col]
        if role == Qt.ItemDataRole.ToolTipRole and col == 3:
            return e.path.replace(">", "  ›  ")
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 4:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class ScanFilterProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.only_candidates = True
        self.kind = ""
        self.text = ""
        self.setSortRole(_SORT_ROLE)

    def update(self, only_candidates: bool, kind: str, text: str) -> None:
        self.beginFilterChange()
        self.only_candidates = only_candidates
        self.kind = kind
        self.text = text.casefold()
        self.endFilterChange()

    def filterAcceptsRow(self, source_row: int, source_parent: _Index) -> bool:
        model = self.sourceModel()
        assert isinstance(model, ScanTableModel)
        e = model.entries[source_row]
        if self.only_candidates and not e.is_text_candidate:
            return False
        if self.kind and e.kind != self.kind:
            return False
        return not self.text or self.text in e.path.casefold() or self.text in e.detail.casefold()


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
        self.game_line = label("", wrap=True)
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
        self.import_button = button("Metinleri Çeviri Tablosuna Aktar  →", "primary", icon="languages")
        self.import_button.clicked.connect(self.import_requested)
        self.can_import = False
        self.has_language_choice = False
        lay.addWidget(self.summary)

        self.engine_card = Card("Tahmini oyun motoru")
        self.engine_line = label("", "cardTitle")
        self.engine_evidence = label("", "muted", wrap=True)
        self.engine_card.body.addWidget(self.engine_line)
        self.engine_card.body.addWidget(self.engine_evidence)
        lay.addWidget(self.engine_card)

        self.files_card = Card(
            "Metin dosyaları",
            hint="Metin içermesi muhtemel dosyalar. İç içe arşivlerdeki dosyalar “dış › iç” biçiminde gösterilir.",
        )
        filters = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem("Yalnızca metin adayları", True)
        self.mode.addItem("Tüm dosyalar", False)
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

        self.model = ScanTableModel()
        self.proxy = ScanFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideLeft)
        self.table.setMinimumHeight(320)
        h = self.table.horizontalHeader()
        for col in range(len(_COLUMNS)):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.files_card.body.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.count_label = label("", "muted")
        bottom.addWidget(self.count_label, 1)
        self.files_card.body.addLayout(bottom)
        lay.addWidget(self.files_card, 1)

        self.mode.currentIndexChanged.connect(self._refilter)
        self.kind.currentIndexChanged.connect(self._refilter)
        self.search.textChanged.connect(self._refilter)

    def _refilter(self) -> None:
        self.proxy.update(bool(self.mode.currentData()), str(self.kind.currentData()), self.search.text())
        self.count_label.setText(f"{format_int(self.proxy.rowCount())} dosya gösteriliyor")

    def show_report(self, report: ScanReport) -> None:
        versions = f"ana oyun v{report.base_version}" if report.base_version is not None else "ana oyun yok"
        if report.update_version is not None:
            versions += f", güncelleme v{report.update_version}"
        total = len(report.entries)
        self.game_line.setText(
            f"<b>{report.game_name or 'Adsız oyun'}</b> &nbsp;·&nbsp; TitleID {report.title_id} &nbsp;·&nbsp; "
            f"{versions} &nbsp;·&nbsp; {format_int(total)} dosya &nbsp;·&nbsp; "
            f"{format_int(len(report.text_candidates))} metin adayı"
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
        if eng.engine == "unknown":
            self.engine_line.setText("Belirlenemedi")
            self.engine_evidence.setText("Bilinen bir motorun izine rastlanmadı.")
        else:
            self.engine_line.setText(f"{eng.label}  —  güven: {CONFIDENCE_LABELS[eng.confidence]}")
            self.engine_evidence.setText("Kanıtlar: " + "; ".join(eng.evidence))
        supported = importable_entries(report)
        others = unsupported_text_kinds(report)
        self.can_import = bool(supported)
        languages = available_languages(report)
        self.language.clear()
        for code in languages:
            self.language.addItem(language_label(code), code)
        default = default_source_language(languages)
        self.language.setCurrentIndex(max(self.language.findData(default), 0))
        has_choice = bool(supported) and len(languages) > 1
        self.has_language_choice = has_choice
        if supported:
            formats = sorted({kind_label(e.kind) for e in supported})
            note = f"{format_int(len(supported))} dosyadan metin aktarılabilir ({', '.join(formats)})."
            if has_choice:
                note += f" {len(languages)} dil var; yalnızca seçtiğiniz kaynak dil aktarılır."
            if others:
                note += f" Henüz desteklenmeyen metin türleri de var: {', '.join(others)}."
            if report.warnings:
                self.status_changed.emit("warning", f"{len(report.warnings)} uyarı", [note, *report.warnings])
            else:
                self.status_changed.emit("success", f"{format_int(len(supported))} dosya aktarılabilir", [note])
        else:
            note = (
                "Bu oyunda henüz desteklenen bir metin biçimi bulunamadı"
                + (f" (bulunan: {', '.join(others)})" if others else "")
                + ". Şu an desteklenen biçimler: "
                + ", ".join(p.label for p in all_plugins())
                + "."
            )
            self.status_changed.emit("warning", "Desteklenmeyen biçim", [note, *report.warnings])
        self.model.set_entries(report.entries)
        self.mode.setCurrentIndex(0 if report.text_candidates else 1)
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

        self.start_button = button("Taramayı Başlat", "primary", icon="scan-search")
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

    def show_empty(self) -> None:
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

    def show_report(self, report: ScanReport) -> None:
        self.report.show_report(report)
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
