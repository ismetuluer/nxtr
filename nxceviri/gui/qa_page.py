"""Adım 4 — Kontrol Et: satır denetimleri, satır sığdırma ayarları, font glif denetimi, font yaması ve harf
dönüştürme seçimi."""

from __future__ import annotations

import math
from collections.abc import Callable, Collection, Sequence
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QSettings,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.languages import natural_sort_key
from nxceviri.core.project import TranslationRow
from nxceviri.core.qa import transliterate
from nxceviri.core.qa.autofix import FIX_KINDS
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_ERROR, SEVERITY_LABELS, SEVERITY_WARNING, QaIssue
from nxceviri.core.qa.fonts import FontReport
from nxceviri.core.translate.codekinds import KIND_NAMES, CodeKinds
from nxceviri.core.translate.fit import DEFAULT_VARIABLE_WIDTH, FitRules
from nxceviri.core.translate.fitconfig import EACH_GROUP, GROUP_PREFIX, FitConfig, FitOptions
from nxceviri.gui.table_columns import ColumnFitter, FitTableView, HeaderColumnMenu
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import ActionBar, Banner, Card, PageHeader, button, format_int, label, tip_html

_Index = QModelIndex | QPersistentModelIndex
#: Bu kadar bulguya kadar satırlar metne göre yükseltilir (üstünde ipucundan okunur).
_FIT_ROWS_LIMIT = 3000
_COLUMNS = ("Önem", "Tür", "Açıklama", "Orijinal", "Çeviri")
COL_SEVERITY, COL_KIND, COL_DESCRIPTION, COL_SOURCE, COL_TRANSLATION = range(5)
#: Sığdırma ilk açıldığında (henüz sınır yokken) kutularda görünen değerler.
_FIT_START_WIDTH, _FIT_START_LINES = 40, 3
_FIT_OFF_TEXT = "Sınır girilmedi; sığdırma kapalı."
_FIT_KEPT_TEXT = "Sığdırma kapalı; sınırlar saklanıyor."


#: Satırın çeviri ekranında nasıl açılacağı; hücre ipuçlarının sonuna eklenir.
OPEN_HINT = "Çift tıklayın veya Enter'a basın: satır çeviri ekranında düzenlemeye açılır."


class IssueModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.issues: list[QaIssue] = []
        self.rows: dict[int, TranslationRow] = {}

    def set_issues(self, issues: list[QaIssue], rows: dict[int, TranslationRow] | None = None) -> None:
        self.beginResetModel()
        self.issues = issues
        self.rows = rows or {}
        self.endResetModel()

    def _texts(self, issue: QaIssue) -> tuple[str, str]:
        row = self.rows.get(issue.row_id)
        return ("", "") if row is None else (row.source, row.translation)

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else len(self.issues)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008 - Qt imzası
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        return None

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        i = self.issues[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            source, translation = self._texts(i)
            return (
                SEVERITY_LABELS[i.severity],
                KIND_LABELS[i.kind],
                i.message,
                source,
                translation,
            )[col]
        if role == Qt.ItemDataRole.ToolTipRole:
            source, translation = self._texts(i)
            if col == COL_SOURCE and source:
                text = source
            elif col == COL_TRANSLATION and translation:
                text = translation
            else:
                text = f"{i.message}\n\nAnahtar: {i.key}"
            return tip_html(f"{text}\n\n{OPEN_HINT}")
        if role == Qt.ItemDataRole.ForegroundRole and col == 0:
            t = current_tokens()
            return QColor(
                t["danger"]
                if i.severity == SEVERITY_ERROR
                else t["warning"]
                if i.severity == SEVERITY_WARNING
                else t["muted"]
            )
        return None


class IssueFilter(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.kind = ""
        self.show_info = False

    def lessThan(self, left: _Index, right: _Index) -> bool:
        """Doğal sıralama: sayılar değerine göre (1, 2, 10), harfler Türkçe sırayla."""
        return natural_sort_key(str(left.data() or "")) < natural_sort_key(str(right.data() or ""))

    def update(self, kind: str, show_info: bool) -> None:
        self.beginFilterChange()
        self.kind, self.show_info = kind, show_info
        self.endFilterChange()

    def filterAcceptsRow(self, source_row: int, source_parent: _Index) -> bool:
        model = self.sourceModel()
        assert isinstance(model, IssueModel)
        i = model.issues[source_row]
        if self.kind:
            return i.kind == self.kind
        return self.show_info or i.severity != "info"


class QaPage(QWidget):
    scan_fonts = Signal()
    run_checks = Signal()
    transliterate_changed = Signal(str)
    font_patch_changed = Signal(bool)
    open_row = Signal(int)  # satır kimliği → çeviri tablosunda o satırı aç
    fix_requested = Signal(list, list)  # düzeltilecek türler, satır kimlikleri (boş: tüm bulgular)
    fix_kinds_changed = Signal(list)  # kullanıcının işaretlediği türler (kalıcı saklanır)
    report_requested = Signal()  # bildirimdeki "Raporu Gör"
    fit_changed = Signal()  # kullanıcı sığdırma sınırını, kod türünü veya bir seçeneği değiştirdi
    learn_rules_requested = Signal(str)  # kapsam: "" proje, dosya yolu, GROUP_PREFIX+grup ya da EACH_GROUP
    add_spelling_requested = Signal(list)  # seçili yazım bulgularındaki sözcükler
    user_dictionary_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 22)
        outer.setSpacing(14)
        outer.addWidget(
            PageHeader(
                "Kontrol Et",
                "shield-check",
                "Dışa aktarmadan önce oyunun fontlarında Türkçe harflerin olup olmadığını ve çevirilerdeki "
                "olası sorunları denetleyin. Hatalı satırlar dışa aktarılmaz; uyarılar yalnızca bilgi içindir.",
            )
        )
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        outer.addWidget(self.tabs, 1)
        check_tab = QWidget()
        check_lay = QVBoxLayout(check_tab)
        check_lay.setContentsMargins(0, 12, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("page")
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(14)

        # --- fontlar ---
        # Sekmenin eylem satırı kartın üstünde; sekme adını tekrar eden kart başlığı yok.
        self.font_bar = ActionBar()
        self.font_bar.status.setToolTip(
            tip_html(
                "Oyunun fontlarında ç ğ ı İ ö ş ü Ç Ğ Ö Ş Ü harfleri aranır. Eksik harfler oyunda kutucuk veya "
                "boşluk olarak görünebilir."
            )
        )
        self.font_button = button("Fontları Tara", "primary", icon="scan-search")
        self.font_button.clicked.connect(self.scan_fonts)
        self.font_bar.add_action(self.font_button)
        lay.addWidget(self.font_bar)
        self.font_card = Card("")
        self.letters = label("", wrap=True)
        self.letters.setTextFormat(Qt.TextFormat.RichText)
        self.font_card.body.addWidget(self.letters)
        self.font_banner = Banner()
        self.font_card.body.addWidget(self.font_banner)
        self.font_table = QTableWidget(0, 5)
        self.font_table.setHorizontalHeaderLabels(["Font", "Tür", "Eksik Türkçe harfler", "Yamayla eklenir", "Dosya"])
        self.font_table.verticalHeader().hide()
        self.font_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        fh = self.font_table.horizontalHeader()
        for c in range(4):
            fh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        fh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.font_table.setMinimumHeight(180)
        self.font_table.setSortingEnabled(True)
        self.font_table.hide()
        self.font_card.body.addWidget(self.font_table)

        self.patch_box = QCheckBox("Eksik Türkçe harfleri fontlara ekle (font yaması)")
        self.patch_box.setToolTip(
            tip_html(
                "TextMeshPro statik fontlarına ı İ ş Ş ğ Ğ harfleri, aynı fontun var olan harflerinden üretilerek "
                "eklenir (ör. ş = s + ç'nin çengeli). Yalnızca üretilen moddaki font dosyaları değişir."
            )
        )
        self.patch_box.toggled.connect(self.font_patch_changed.emit)
        self.font_card.body.addWidget(self.patch_box)
        self.patch_note = label("", "muted", wrap=True)
        self.font_card.body.addWidget(self.patch_note)

        self.font_card.body.addWidget(label("Dışa aktarırken harf dönüştürme:", "cardTitle"))
        self.mode_group = QButtonGroup(self)
        self.mode_buttons: dict[str, QRadioButton] = {}
        for mode in (transliterate.MODE_NONE, transliterate.MODE_MISSING, transliterate.MODE_ALL):
            rb = QRadioButton(transliterate.MODE_LABELS[mode])
            self.mode_group.addButton(rb)
            self.mode_buttons[mode] = rb
            rb.toggled.connect(lambda checked, m=mode: self._mode_toggled(checked, m))
            self.font_card.body.addWidget(rb)
        self.mode_note = label("", "muted", wrap=True)
        self.font_card.body.addWidget(self.mode_note)
        lay.addWidget(self.font_card)
        lay.addStretch(1)

        # --- satır denetimi ---
        self.check_bar = ActionBar()
        self.check_card = Card("")
        self.check_button = button("Denetle", "primary", icon="shield-check")
        self.check_button.clicked.connect(lambda: self._commit_pending(self.run_checks.emit))
        self.check_bar.add_action(self.check_button)
        self.summary = self.check_bar.status
        self.summary.setWordWrap(True)  # denetim özeti tür sayımlarıyla uzayabilir
        self.summary.setText("Henüz denetlenmedi.")
        self.fix_banner = Banner()
        self.fix_banner.action_clicked.connect(self.report_requested)
        self.check_card.body.addWidget(self.fix_banner)
        filters = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.addItem("Hatalar ve uyarılar", "")
        for kind, text in KIND_LABELS.items():
            self.kind.addItem(text, kind)
        filters.addWidget(self.kind)
        filters.addStretch(1)
        self.check_card.body.addLayout(filters)
        self.model = IssueModel()
        self.proxy = IssueFilter()
        self.proxy.setSourceModel(self.model)
        self.table = FitTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)  # başlığa tıklayınca sıralar; üçüncü tıklama özgün sıraya döner
        self.table.horizontalHeader().setSortIndicatorClearable(True)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.table.setMinimumHeight(80)
        self.table.setWordWrap(True)  # açıklama, orijinal ve çeviri kesilmeden okunsun
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)  # sütunlar sürüklenerek ayarlanır
        h.setMinimumSectionSize(40)
        self.fitter = ColumnFitter(
            self.table,
            {COL_SEVERITY: (80, 50), COL_KIND: (140, 60)},
            {COL_DESCRIPTION: (0.3, 100), COL_SOURCE: (0.35, 100), COL_TRANSLATION: (0.35, 100)},
        )
        self.column_menu = HeaderColumnMenu(
            self.table,
            dict(enumerate(_COLUMNS)),
            frozenset({COL_DESCRIPTION, COL_SOURCE, COL_TRANSLATION}),
            self.fitter,
        )
        # Sütun genişliği değişince (pencere boyutu) satır yükseklikleri yeniden hesaplanır; art arda gelen
        # değişiklikler tek seferde.
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(80)
        self._fit_timer.timeout.connect(self._fit_rows)
        h.sectionResized.connect(lambda *_args: self._fit_timer.start())
        self.fitter.resized.connect(self._fit_timer.start)
        # Yazım sözlüğü eylemleri bulgu tablosunun sağ tık menüsünde.
        self.spell_add_button = QAction("Yazım sözlüğüne ekle…", self)
        self.spell_add_button.setEnabled(False)
        self.spell_add_button.triggered.connect(self._add_spelling)
        self.user_dict_button = QAction("Yazım sözlüğünü aç…", self)
        self.user_dict_button.triggered.connect(self.user_dictionary_requested)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._open)
        self.table.activated.connect(self._open)
        self.table.setToolTip(OPEN_HINT)
        self.check_card.body.addWidget(self.table, 1)
        self.check_card.body.addWidget(self._build_fix_section())
        self.table.selectionModel().selectionChanged.connect(lambda *_a: self._selection_changed())
        check_lay.addWidget(self.check_bar)
        check_lay.addWidget(self.check_card, 1)
        self.tabs.addTab(check_tab, "Satır denetimi")
        self.tabs.addTab(self._build_fit_tab(), "Sığdırma")
        self.tabs.addTab(scroll, "Font ve harfler")
        self.kind.currentIndexChanged.connect(self._refilter)

    # --- satır sığdırma -----------------------------------------------------------------

    def _build_fit_tab(self) -> QScrollArea:
        self._default: FitRules | None = None
        self._per_file: dict[str, FitRules] = {}
        self._per_group: dict[str, FitRules] = {}
        self._kinds: dict[str, str] = {}
        self._options = FitOptions()
        self._enabled = True
        self._pending = False  # "Orijinalden öğren" önerisi kutularda, henüz kaydedilmedi
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("page")
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(14)
        self.fit_bar = ActionBar()
        self.fit_bar.status.setToolTip(
            tip_html(
                "Sınır girilince “Denetle” uzun satırları, uzun sayfaları ve kötü bölünmeleri gösterir; "
                "“Satır denetimi” sekmesindeki düzeltmeler satırları sınıra göre yeniden böler. Sınırlar, oyundaki "
                "metin kutusuna sığan karakter ve satır sayısıdır."
            )
        )
        lay.addWidget(self.fit_bar)
        self.fit_card = Card("")
        self.fit_enabled = QCheckBox("Sığdırmayı aç")
        self.fit_enabled.toggled.connect(self._fit_toggled)
        self.fit_bar.add_action(self.fit_enabled)
        body = self.fit_card.body
        self.fit_note = label(_FIT_OFF_TEXT, "muted", wrap=True)
        body.addWidget(self.fit_note)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        scope_row = QHBoxLayout()
        self.fit_scope = QComboBox()
        self.fit_scope.addItem("Tüm proje", "")
        self.fit_scope.setToolTip(tip_html("Bir dosya ya da grup seçerek ona ayrı sınır verebilirsiniz."))
        self.fit_scope.currentIndexChanged.connect(self._show_scope)
        self.fit_inherit = QCheckBox("Proje sınırını kullan")
        self.fit_inherit.toggled.connect(self._inherit_toggled)
        scope_row.addWidget(self.fit_scope)
        scope_row.addWidget(self.fit_inherit)
        form.addRow("Kapsam:", scope_row)
        self.fit_width = QSpinBox()
        self.fit_width.setRange(1, 999)
        self.fit_width.setValue(_FIT_START_WIDTH)
        self.fit_width.valueChanged.connect(lambda _v: self._fit_changed())
        form.addRow("Satırda en çok karakter:", self.fit_width)
        self.fit_lines = QSpinBox()
        self.fit_lines.setRange(1, 99)
        self.fit_lines.setValue(_FIT_START_LINES)
        self.fit_lines.valueChanged.connect(lambda _v: self._fit_changed())
        form.addRow("Sayfada en çok satır:", self.fit_lines)
        body.addLayout(form)
        learn_row = QHBoxLayout()
        self.fit_learn = button("Orijinalden öğren")
        self.fit_learn.setToolTip(
            tip_html(
                "Kapsamdaki orijinal metinlerde en uzun satırı ve bir sayfadaki en çok satırı ölçüp kutulara yazar. "
                "Öneri kendiliğinden uygulanmaz; değiştirebilirsiniz. Bir değeri değiştirince veya “Denetle” ya da "
                "“Seçilenleri Düzelt”e basınca kaydedilir. “Her grup ayrı” seçiliyken her grubun sınırı ayrı "
                "öğrenilip hemen kaydedilir; üst kapsamla aynı çıkan gruplara kural yazılmaz."
            )
        )
        self.fit_learn.clicked.connect(lambda: self.learn_rules_requested.emit(self._scope()))
        self.fit_learn_note = label("", "muted", wrap=True)
        self.fit_bar.add_action(self.fit_learn)
        learn_row.addWidget(self.fit_learn_note, 1)
        body.addLayout(learn_row)

        body.addWidget(
            label(
                "Kod türleri",
                "cardTitle",
                tip="Satır sonu ve sayfa sonu metni böler; değişken birkaç karakter, sembol bir karakter sayılır; "
                "biçim ve diğer kodlar yer kaplamaz ve bitişik sözcükten ayrılmaz.",
            )
        )
        self.fit_kinds = QTableWidget(0, 2)
        self.fit_kinds.setHorizontalHeaderLabels(["Kod", "Tür"])
        self.fit_kinds.verticalHeader().hide()
        self.fit_kinds.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.fit_kinds.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        kh = self.fit_kinds.horizontalHeader()
        kh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        kh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        body.addWidget(self.fit_kinds)
        self.fit_kinds_empty = label("Metinlerde kontrol kodu yok.", "muted")
        body.addWidget(self.fit_kinds_empty)

        body.addWidget(
            label("Düzeltirken temizle", "cardTitle", tip="Yalnızca orijinalde olmayan kalıplara dokunulur.")
        )
        options = QHBoxLayout()
        self.fit_spaces = QCheckBox("Gereksiz boşluk")
        self.fit_spaces.setToolTip(tip_html("Sözcükler arasındaki çift boşluk teke indirilir."))
        self.fit_before_punct = QCheckBox("Noktalama öncesi boşluk")
        self.fit_before_punct.setToolTip(tip_html("“Merhaba !” → “Merhaba!”"))
        self.fit_repeated = QCheckBox("Tekrarlı noktalama")
        self.fit_repeated.setToolTip(tip_html("“!!!!” → “!!!”, “.....” → “...”, “,,” → “,”"))
        for box in (self.fit_spaces, self.fit_before_punct, self.fit_repeated):
            box.toggled.connect(self._option_toggled)
            options.addWidget(box)
        options.addStretch(1)
        body.addLayout(options)
        lay.addWidget(self.fit_card)
        lay.addStretch(1)
        self._apply_fit_widgets([], [], [])
        return scroll

    def set_fit(self, config: FitConfig, files: list[str], labels: list[str], groups: Sequence[str] = ()) -> None:
        """Ayarı ve kapsam/kod listelerini gösterir; `fit_changed` yayılmaz. Seçili kapsam korunur.

        `groups`: kapsam seçicisinde ayrıca gösterilecek gruplar (kuralı olan gruplar da eklenir).
        """
        self._default = config.default
        self._per_file = dict(config.per_file)
        self._per_group = dict(config.per_group)
        self._kinds = dict(config.kinds.mapping)
        self._options = config.options
        self._enabled = config.enabled
        self._apply_fit_widgets(files, labels, groups)

    def fit_config(self) -> FitConfig:
        """Kartın gösterdiği ayar; sığdırma kapalıyken sınırlar saklanır ama uygulanmaz (`enabled=False`)."""
        kinds = CodeKinds(dict(self._kinds))
        return FitConfig(
            self._default,
            dict(self._per_file),
            kinds,
            self._options,
            self.fit_enabled.isChecked(),
            dict(self._per_group),
        )

    def show_learned(self, rules: FitRules | None) -> None:
        """Öğrenilen öneriyi kutulara yazar; kullanıcı bir değeri değiştirene veya denetleyene dek kaydedilmez."""
        if rules is None:
            self.fit_learn_note.setText("Ölçülecek orijinal metin yok.")
            return
        with _Blocked(self.fit_width, self.fit_lines, self.fit_inherit):
            self.fit_inherit.setChecked(False)
            self.fit_width.setValue(rules.width)
            self.fit_lines.setValue(rules.max_lines)
        self._pending = True
        self.fit_learn_note.setText("Öneri yazıldı, henüz kaydedilmedi.")
        self._update_fit_enabled()

    def show_learned_groups(self, per_group: dict[str, FitRules]) -> None:
        """Her grup için ayrı öğrenilen sınırları uygular ve kaydettirir (kutularda gösterilecek tek sınır yoktur)."""
        changed = sum(
            1 for g in per_group.keys() | self._per_group.keys() if per_group.get(g) != self._per_group.get(g)
        )
        self._per_group = dict(per_group)
        self._show_scope()
        self.fit_learn_note.setText(
            f"{format_int(changed)} grubun sınırı güncellendi." if changed else "Gruplar için ayrı sınır gerekmedi."
        )
        self.fit_changed.emit()

    def _scope(self) -> str:
        return str(self.fit_scope.currentData() or "")

    def _own_rules(self, scope: str) -> tuple[dict[str, FitRules], str] | None:
        """Kapsamın kendi kural sözlüğü ve anahtarı; proje ve "her grup ayrı" kapsamının kendi sözlüğü yoktur."""
        if scope.startswith(GROUP_PREFIX):
            return self._per_group, scope[len(GROUP_PREFIX) :]
        if scope and scope != EACH_GROUP:
            return self._per_file, scope
        return None

    def _apply_fit_widgets(self, files: list[str], labels: list[str], groups: Sequence[str]) -> None:
        scope = self._scope()
        with _Blocked(self.fit_enabled, self.fit_scope, self.fit_spaces, self.fit_before_punct, self.fit_repeated):
            self.fit_enabled.setChecked(self._enabled and self._has_rules())
            self.fit_scope.clear()
            self.fit_scope.addItem("Tüm proje", "")
            for path in files:
                self.fit_scope.addItem(path, path)
            names = {path.rsplit(">", 1)[-1].rsplit("/", 1)[-1] for path in files}
            stale = {g for g in self._per_group if g in names and g not in groups}  # eski tek-dosya taban ad kuralı
            for group in sorted({*groups, *self._per_group} - stale, key=str.casefold):
                self.fit_scope.addItem(f"Grup: {group}", GROUP_PREFIX + group)
            if files:
                self.fit_scope.addItem("Her grup ayrı", EACH_GROUP)
            self.fit_scope.setCurrentIndex(max(self.fit_scope.findData(scope), 0))
            self.fit_spaces.setChecked(self._options.spaces)
            self.fit_before_punct.setChecked(self._options.space_before_punct)
            self.fit_repeated.setChecked(self._options.repeated_punct)
        kinds = CodeKinds(self._kinds)
        self.fit_kinds.setRowCount(len(labels))
        for r, code in enumerate(labels):
            item = QTableWidgetItem(code)
            item.setToolTip(code)
            self.fit_kinds.setItem(r, 0, item)
            combo = QComboBox()
            for kind, name in KIND_NAMES.items():
                combo.addItem(name, kind)
            current = kinds.kind_of(code)
            if combo.findData(current) < 0:  # kullanıcının kendi adlandırdığı tür
                combo.addItem(current, current)
            combo.setCurrentIndex(combo.findData(current))
            combo.currentIndexChanged.connect(lambda _i, c=code, box=combo: self._kind_changed(c, box))
            self.fit_kinds.setCellWidget(r, 1, combo)
        # Tablo satırları kadar uzar (en çok ~6 satır), kalanı kaydırılır; kart gereksiz uzamasın.
        shown = min(len(labels), 6)
        frame = 2 * self.fit_kinds.frameWidth()
        header = self.fit_kinds.horizontalHeader().sizeHint().height()
        self.fit_kinds.setFixedHeight(header + shown * self.fit_kinds.verticalHeader().defaultSectionSize() + frame)
        self.fit_kinds.setVisible(bool(labels))
        self.fit_kinds_empty.setVisible(not labels)
        self._show_scope()

    def _show_scope(self) -> None:
        """Seçili kapsamın sınırını kutulara yazar; kayıt yapılmaz, bekleyen öneri bırakılır."""
        own = self._own_rules(self._scope())
        rules = own[0].get(own[1], self._default) if own else self._default
        with _Blocked(self.fit_width, self.fit_lines, self.fit_inherit):
            self.fit_inherit.setChecked(own is not None and own[1] not in own[0])
            self.fit_width.setValue(rules.width if rules else _FIT_START_WIDTH)
            self.fit_lines.setValue(rules.max_lines if rules else _FIT_START_LINES)
        self.fit_inherit.setVisible(own is not None)
        self._pending = False
        self.fit_learn_note.setText("")
        self._update_fit_enabled()

    def _has_rules(self) -> bool:
        return self._default is not None or bool(self._per_file) or bool(self._per_group)

    def _update_fit_enabled(self) -> None:
        on = self.fit_enabled.isChecked()
        self.fit_note.setText(_FIT_KEPT_TEXT if self._has_rules() else _FIT_OFF_TEXT)
        self.fit_note.setVisible(not on)
        scope = self._scope()
        inherit = scope == EACH_GROUP or (self._own_rules(scope) is not None and self.fit_inherit.isChecked())
        for widget in (
            self.fit_scope,
            self.fit_inherit,
            self.fit_learn,
            self.fit_kinds,
            self.fit_spaces,
            self.fit_before_punct,
            self.fit_repeated,
        ):
            widget.setEnabled(on)
        for spin in (self.fit_width, self.fit_lines):
            spin.setEnabled(on and not inherit)

    def _fit_changed(self) -> None:
        """Kutulardaki değerleri seçili kapsamın sınırı yapar (değişken genişliği korunur) ve bildirir."""
        scope = self._scope()
        own = self._own_rules(scope)
        base = own[0].get(own[1], self._default) if own else self._default
        variable = base.variable_width if base else DEFAULT_VARIABLE_WIDTH
        rules = FitRules(self.fit_width.value(), self.fit_lines.value(), variable)
        if own is None:
            if not scope:
                self._default = rules
        elif not self.fit_inherit.isChecked():
            own[0][own[1]] = rules
        self._pending = False
        self.fit_learn_note.setText("")
        self.fit_changed.emit()

    def _commit_pending(self, then: Callable[[], object]) -> None:
        """Kutularda bekleyen bir öneri varsa önce onu kaydeder, sonra istenen işlemi başlatır."""
        if self._pending and self.fit_enabled.isChecked():
            self._fit_changed()
        then()

    def _fit_toggled(self, checked: bool) -> None:
        """Kapatınca sınırlar saklanır, yalnızca uygulanmaz; açınca proje sınırı yoksa başlangıç değeriyle kurulur."""
        if checked and self._default is None:
            self._default = FitRules(_FIT_START_WIDTH, _FIT_START_LINES)
        self._show_scope()
        self.fit_changed.emit()

    def _inherit_toggled(self, checked: bool) -> None:
        own = self._own_rules(self._scope())
        if checked and own is not None:
            own[0].pop(own[1], None)
            self._show_scope()
            self.fit_changed.emit()
        else:
            self._update_fit_enabled()
            self._fit_changed()

    def _kind_changed(self, code: str, combo: QComboBox) -> None:
        self._kinds[code] = str(combo.currentData())
        self.fit_changed.emit()

    def _option_toggled(self) -> None:
        self._options = FitOptions(
            self.fit_spaces.isChecked(), self.fit_before_punct.isChecked(), self.fit_repeated.isChecked()
        )
        self.fit_changed.emit()

    # --- fontlar ------------------------------------------------------------------------

    def _mode_toggled(self, checked: bool, mode: str) -> None:
        if checked:
            self.transliterate_changed.emit(mode)

    def set_font_busy(self, busy: bool) -> None:
        self.font_button.setEnabled(not busy)
        self.font_button.setText("Taranıyor…" if busy else "Fontları Tara")

    def set_font_patch(self, enabled: bool, patchable: str) -> None:
        """Font yaması seçeneğinin durumu; yamayla eklenebilecek harf yoksa seçenek kapalıdır."""
        self.patch_box.blockSignals(True)
        self.patch_box.setChecked(enabled and bool(patchable))
        self.patch_box.blockSignals(False)
        self.patch_box.setEnabled(bool(patchable))
        if not patchable:
            self.patch_note.setText("Yamayla eklenebilecek harf yok.")
            self.patch_note.setToolTip(tip_html("Fontlar taranmadı, harfler zaten var veya fontlar desteklenmiyor."))
        elif enabled:
            self.patch_note.setText(f"Eklenecek harfler: {' '.join(patchable)}")
            self.patch_note.setToolTip(
                tip_html(
                    "Tabloda bir harfin eklenemediği fontlar (“Yamayla eklenir” sütununda olmayanlar) o harfi "
                    "göstermeyebilir. Sonucu oyunda kontrol edin."
                )
            )
        else:
            self.patch_note.setText(f"Eklenebilecek harfler: {' '.join(patchable)}")
            self.patch_note.setToolTip("")

    def show_font_report(self, report: FontReport | None, missing: str) -> None:
        if report is None:
            if missing:
                self.letters.setText(f"Son taramada eksik bulunan harfler: <b>{' '.join(missing)}</b>")
            else:
                self.letters.setText("Fontlar henüz taranmadı.")
            self.font_table.hide()
            self.font_banner.show_message("warning", "")
            return
        t = current_tokens()
        chips = []
        for c, (have, total) in report.coverage().items():
            ok = total and have * 2 >= total
            color = t["success"] if ok else t["danger"]
            chips.append(f"<span style='color:{color}'><b>{c}</b> {have}/{total}</span>")
        if report.latin_static:
            self.letters.setText("Latin fontlarda bulunma oranı: " + " &nbsp; ".join(chips))
        else:
            self.letters.setText("Latin font bulunamadı.")
        missing_now = report.missing_letters()
        dynamic = report.dynamic_fallback_letters()
        if not report.fonts:
            self.font_banner.show_message(
                "warning", "Oyunda okunabilen font bulunamadı; harflerin görünüp görünmeyeceği bilinmiyor."
            )
        elif not missing_now:
            self.font_banner.show_message("success", "Fontlar tüm Türkçe harfleri içeriyor. Dönüştürme gerekmez.")
        else:
            text = f"Çoğu fontta eksik harfler: {' '.join(missing_now)}."
            if dynamic:
                text += (
                    f" Bu harfler ({' '.join(dynamic)}) oyundaki dinamik bir yedek fontta var; oyun ayarına bağlı "
                    "olarak farklı bir yazı tipiyle görünebilir. Emin olmak için önce “Yalnızca eksik harfleri "
                    "dönüştür” ile deneyin, ya da dönüştürmeden üretip oyunda kontrol edin."
                )
            elif report.patchable_letters:
                text += (
                    f" Font yaması bunlardan {' '.join(report.patchable_letters)} harflerini ekleyebilir (aşağıdaki "
                    "seçenek); kalanlar için “Yalnızca eksik harfleri dönüştür” önerilir."
                )
            else:
                text += " Bu harfler oyunda görünmeyebilir; “Yalnızca eksik harfleri dönüştür” seçeneği önerilir."
            self.font_banner.show_message("warning", text)
        self.font_table.setSortingEnabled(False)  # doldurulurken satırlar yer değiştirmesin
        self.font_table.setRowCount(len(report.fonts))
        for r, f in enumerate(sorted(report.fonts, key=lambda x: (x.language_specific, x.name))):
            miss = "?" if f.chars is None else (f.missing() or "yok")
            kind = f.kind + (" — dile özgü, hesaba katılmadı" if f.language_specific else "")
            patch = " ".join(f.patchable) if f.patchable else "—"
            for col, value in enumerate((f.name, kind, miss, patch, f.source.rsplit("/", 1)[-1])):
                item = QTableWidgetItem(value)
                item.setToolTip(f.note or f.source)
                self.font_table.setItem(r, col, item)
        self.font_table.setSortingEnabled(True)
        self.font_table.setVisible(bool(report.fonts))

    def set_mode(self, mode: str, missing: str, patched: bool = False) -> None:
        rb = self.mode_buttons.get(mode) or self.mode_buttons[transliterate.MODE_NONE]
        rb.blockSignals(True)
        rb.setChecked(True)
        rb.blockSignals(False)
        letters = transliterate.letters_for(mode, missing)
        if mode == transliterate.MODE_MISSING and not missing and patched:
            self.mode_note.setText("Font yaması tüm eksik harfleri ekleyecek; dönüştürülecek harf kalmadı.")
        elif mode == transliterate.MODE_MISSING and not missing:
            self.mode_note.setText("Eksik harf bilinmiyor veya yok; önce fontları tarayın.")
        elif letters:
            self.mode_note.setText(
                f"Dönüştürülecek: {' '.join(letters)} → {' '.join(transliterate.apply(letters, letters))}. "
                "Projedeki çeviriler değişmez; yalnızca üretilen modda uygulanır."
            )
        else:
            self.mode_note.setText("Türkçe harfler olduğu gibi yazılır.")

    # --- satır denetimi -----------------------------------------------------------------

    def show_issues(self, issues: list[QaIssue], rows: list[TranslationRow]) -> None:
        total_rows = len(rows)
        self.model.set_issues(issues, {r.id: r for r in rows})
        errors = sum(1 for i in issues if i.severity == SEVERITY_ERROR)
        warnings = sum(1 for i in issues if i.severity == SEVERITY_WARNING)
        self.summary.setText(
            f"{format_int(total_rows)} satır denetlendi — {format_int(errors)} hata, {format_int(warnings)} uyarı."
            if errors or warnings
            else f"{format_int(total_rows)} satır denetlendi — sorun bulunmadı."
        )
        self.summary.setProperty("role", None)
        self._update_fix_counts(issues)
        self._refilter()

    def bind_settings(self, settings: QSettings) -> None:
        """Bulgu tablosunun sütun genişliklerini ve gizli sütunlarını geri yükler."""
        self.fitter.bind_settings(settings, "qa/column_widths")
        self.column_menu.bind_settings(settings, "qa/hidden_columns")

    def _refilter(self) -> None:
        kind = str(self.kind.currentData() or "")
        self.proxy.update(kind, show_info=False)
        self._fit_rows()

    def _fit_rows(self) -> None:
        """Satır yüksekliğini metne göre ayarlar; çok büyük listede pencere donmasın diye yalnızca sınıra kadar."""
        if self.proxy.rowCount() <= _FIT_ROWS_LIMIT:
            self.table.resizeRowsToContents()

    # --- düzeltmeler --------------------------------------------------------------------

    def _build_fix_section(self) -> QWidget:
        """Düzeltilebilir türlerin onay kutuları (iki sütun), "Tümü / Hiçbiri" ve tek düzeltme düğmesi."""
        self.fix_counts: dict[str, int] = dict.fromkeys(FIX_KINDS, 0)
        self.fix_boxes: dict[str, QCheckBox] = {}
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)
        head = QHBoxLayout()
        head.addWidget(
            label(
                "Düzeltmeler",
                "cardTitle",
                tip="İşaretlediğiniz türlerdeki sorunlar düzeltilir; yanındaki sayı o türden bulgu sayısıdır. "
                "Onaylı satırlara dokunulmaz. Düzeltme tek işlemdir: Geri Al hepsini geri alır.",
            )
        )
        head.addStretch(1)
        self.fix_all = QToolButton()
        self.fix_all.setText("Tümü")
        self.fix_none = QToolButton()
        self.fix_none.setText("Hiçbiri")
        for link in (self.fix_all, self.fix_none):
            link.setProperty("role", "link")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            head.addWidget(link)
        self.fix_all.clicked.connect(lambda: self._check_all_kinds(True))
        self.fix_none.clicked.connect(lambda: self._check_all_kinds(False))
        lay.addLayout(head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(2)
        per_column = math.ceil(len(FIX_KINDS) / 2)
        for n, kind in enumerate(FIX_KINDS):
            check = QCheckBox()
            check.setChecked(True)
            check.toggled.connect(self._fix_selection_changed)
            self.fix_boxes[kind] = check
            grid.addWidget(check, n % per_column, n // per_column)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.fix_button = button("Seçilenleri Düzelt", "primary", icon="refresh-cw")
        self.fix_button.clicked.connect(lambda: self._commit_pending(self._request_fix))
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(self.fix_button)
        lay.addLayout(foot)
        self._update_fix_boxes()
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)  # dar pencerede tablo kısalır
        return box

    def _request_fix(self) -> None:
        self.fix_requested.emit(self.fix_kinds_to_apply(), self._selected_row_ids())

    def fix_kinds_to_apply(self) -> list[str]:
        """İşaretli ve bulgusu olan düzeltme türleri (liste sırasıyla)."""
        return [k for k in FIX_KINDS if self.fix_boxes[k].isChecked() and self.fix_counts[k] > 0]

    def checked_fix_kinds(self) -> list[str]:
        """İşaretli tüm türler (bulgusu olmayanlar dahil); ayar olarak saklanır."""
        return [k for k in FIX_KINDS if self.fix_boxes[k].isChecked()]

    def set_checked_fix_kinds(self, kinds: Collection[str]) -> None:
        """Kayıtlı seçimi yazar; `fix_kinds_changed` yayılmaz."""
        with _Blocked(*self.fix_boxes.values()):
            for kind, check in self.fix_boxes.items():
                check.setChecked(kind in kinds)
        self._update_fix_boxes()

    def _check_all_kinds(self, checked: bool) -> None:
        with _Blocked(*self.fix_boxes.values()):
            for check in self.fix_boxes.values():
                check.setChecked(checked)
        self._fix_selection_changed()

    def _fix_selection_changed(self) -> None:
        self._update_fix_boxes()
        self.fix_kinds_changed.emit(self.checked_fix_kinds())

    def _update_fix_counts(self, issues: Sequence[QaIssue]) -> None:
        self.fix_counts = dict.fromkeys(FIX_KINDS, 0)
        for issue in issues:
            if issue.kind in self.fix_counts:
                self.fix_counts[issue.kind] += 1
        self._update_fix_boxes()

    def _update_fix_boxes(self) -> None:
        """Onay kutularının yazısını (tür adı + bulgu sayısı) ve düğmenin durumunu tazeler; bulgusuz tür soluk kalır."""
        for kind, check in self.fix_boxes.items():
            n = self.fix_counts[kind]
            check.setText(f"{KIND_LABELS[kind]}  {format_int(n)}")
            check.setEnabled(n > 0)
        self.fix_button.setEnabled(bool(self.fix_kinds_to_apply()))
        self.fix_button.setText("Seçili Satırlarda Düzelt" if self._selected_row_ids() else "Seçilenleri Düzelt")

    def show_fix_result(self, state: str, text: str, action: str = "") -> None:
        self.fix_banner.show_message(state, text, action)

    def _selected_row_ids(self) -> list[int]:
        """Bulgu tablosunda seçili satırların çeviri satırı kimlikleri; seçim yoksa boş (tüm bulgular)."""
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        return sorted({self.model.issues[r].row_id for r in rows})

    def _selection_changed(self) -> None:
        self._update_fix_boxes()
        self.spell_add_button.setEnabled(bool(self._selected_spelling_words()))

    def context_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(self.spell_add_button)
        menu.addAction(self.user_dict_button)
        return menu

    def _show_context_menu(self, pos: QPoint) -> None:
        index = self.table.indexAt(pos)
        if index.isValid() and not self.table.selectionModel().isRowSelected(index.row()):
            self.table.selectRow(index.row())
        self.context_menu().exec(self.table.viewport().mapToGlobal(pos))

    def _selected_spelling_words(self) -> list[str]:
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        words: dict[str, None] = {}
        for r in sorted(rows):
            issue = self.model.issues[r]
            if issue.kind == "spelling":
                words.update(dict.fromkeys(issue.words))
        return list(words)

    def _add_spelling(self) -> None:
        words = self._selected_spelling_words()
        if words:
            self.add_spelling_requested.emit(words)

    def _open(self, index: QModelIndex) -> None:
        issue = self.model.issues[self.proxy.mapToSource(index).row()]
        self.open_row.emit(issue.row_id)


class _Blocked:
    """Programla değer yazarken pencere öğelerinin sinyallerini geçici olarak susturur."""

    def __init__(self, *widgets: QWidget) -> None:
        self.widgets = widgets
        self._previous: list[bool] = []

    def __enter__(self) -> None:
        self._previous = [w.blockSignals(True) for w in self.widgets]

    def __exit__(self, *_exc: object) -> None:
        for w, previous in zip(self.widgets, self._previous, strict=True):
            w.blockSignals(previous)
