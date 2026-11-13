"""Adım 4 — Kontrol Et: satır denetimleri, satır sığdırma ayarları, font glif denetimi, font yaması ve harf
dönüştürme seçimi."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractTableModel,
    QItemSelectionModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QSettings,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    Signal,
    SignalInstance,
)
from PySide6.QtGui import QAction, QColor, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
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
from nxceviri.core.qa.fonts import FontReport, font_advice, is_editable_font
from nxceviri.core.translate.codekinds import KIND_NAMES, CodeKinds
from nxceviri.core.translate.fit import DEFAULT_VARIABLE_WIDTH, PROBLEM_LINE, PROBLEM_PAGE, FitRules
from nxceviri.core.translate.fitconfig import EACH_GROUP, GROUP_PREFIX, FitConfig
from nxceviri.core.translate.limits import SCOPE_GROUP, SCOPE_KEY
from nxceviri.gui.icons import bind_icon, icon
from nxceviri.gui.issue_chips import ChipBar, Disclosure
from nxceviri.gui.limits_table import LimitsTable
from nxceviri.gui.table_columns import ColumnFitter, FitTableView, HeaderColumnMenu
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.translate_page import _Editor
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
_FIT_RESULT_EMPTY = (
    "Henüz denetlenmedi. Sorunlar sekmesinde “Denetle”ye basın; sonra ayarı değiştirdikçe sonuç burada kendiliğinden "
    "yenilenir."
)
_FIT_RESULT_CHECKING = "Denetleniyor…"
_FIT_RESULT_FAILED = "Denetim yenilenemedi. Sorunlar sekmesinde “Denetle”ye basarak yeniden deneyin."
#: "Taşıyor" sayılan bulgu türleri: satır ya da sayfa sınırını aşanlar (kötü bölünme taşma değildir).
_OVERFLOW_KINDS = (PROBLEM_LINE, PROBLEM_PAGE)


#: Satırın çeviri ekranında nasıl açılacağı; hücre ipuçlarının sonuna eklenir.
OPEN_HINT = "Çift tıklayın veya Enter'a basın: satır çeviri ekranında düzenlemeye açılır."
#: Çeviri hücresi bu tabloda yerinde düzenlenir.
EDIT_HINT = (
    "Çift tıklayın veya F2'ye basın: çeviriyi burada düzenleyin "
    "(Enter kaydeder ve satırı onaylar, Shift+Enter satır sonu)."
)
#: Bu genişliğin altında düzeltme paneli, kullanıcı seçim yapmadıysa kapalı başlar.
_NARROW_WIDTH = 1100
_FIX_PANEL_WIDTH = 260
#: Font tablosu hücresinde fontun kendi "Ne yapılabilir" önerisi (İçe alındı yazısı kalkınca geri konur).
_ADVICE_ROLE = Qt.ItemDataRole.UserRole + 1

#: Her düzeltme türünün tek cümlelik ipucu ve örneği.
FIX_TIPS: dict[str, str] = {
    "placeholder": (
        "Orijinalde olmayan kontrol kodlarını atar, karışmış kod sırasını düzeltir (⟦2⟧ ⟦1⟧ → ⟦1⟧ ⟦2⟧), "
        "yarım yazılmış kodu onarır ([1] → ⟦1⟧) ve metnin tamamını kaplayan eksik renk/biçim çiftini ekler: "
        "‘Yürü.’ → ‘⟦1⟧Yürü.⟦2⟧’. Yalnızca bir bölümü kaplayan kodlar elle düzeltilir."
    ),
    "markup": "Orijinalde olmayan HTML/XML etiketlerini siler: ‘<b>Tamam</b>’ → ‘Tamam’.",
    "code_position": "Sona yığılmış satır sonlarını orijinaldeki yerlerine dağıtır: ‘A B ⏎⏎’ → ‘A ⏎ B ⏎’.",
    "newlines": "Satır sonu sayısını orijinale uydurur, gerekirse metni yeniden böler: ‘Bir ⏎ iki’ → ‘Bir iki’.",
    "spaces": "Baştaki ve sondaki boşlukları orijinalle eşler: ‘ Tamam’ → ‘Tamam’.",
    "glossary": "İngilizce kalmış terminoloji terimini karşılığıyla değiştirir: ‘Sheriff’e’ → ‘Şerif’e’.",
    "ascii_turkish": (
        "Sözlükte olmayan sözcüklerde ASCII’ye çevrilmiş Türkçe harfleri geri koyar: ‘tesekkur’ → ‘teşekkür’, "
        "‘Iste’ → ‘İşte’, ‘Kitap mi’ → ‘Kitap mı’. Birden çok olasılığı olan sözcüğe dokunmaz; "
        "yanlış sözcük çıkabileceği için değişiklikleri önizleyerek açın."
    ),
    "end_punctuation": "Orijinalde olmayan son noktayı siler: ‘Tamam.’ → ‘Tamam’.",
    "double_space": "Sözcükler arasındaki çift boşluğu teke indirir: ‘Çok  güzel’ → ‘Çok güzel’.",
    "repeated_word": "Art arda tekrarlanan sözcüğü teke indirir: ‘ve ve bitir’ → ‘ve bitir’.",
    "extra_dots": "Tekrarlı noktalamayı toplar: ‘Bekle.....’ → ‘Bekle...’, ‘Hayır!!!!’ → ‘Hayır!!!’.",
    "space_before_punct": "Noktalamadan önceki boşluğu siler: ‘Merhaba !’ → ‘Merhaba!’.",
    "line_too_long": "Sığdırma sınırını aşan satırları sözcük sınırlarından yeniden böler.",
    "page_too_tall": "Sınırdan fazla satırlı sayfaları yeniden böler.",
    "bad_break": "Kötü yerden bölünmüş satırları noktalama ve sözcük sınırlarına göre yeniden böler.",
}
#: Metni yeniden biçimleyen ya da kod yerini değiştiren türler: ilk açılışta işaretsizdir, kullanıcı bilerek açar.
RISKY_FIX_KINDS = frozenset(
    {"ascii_turkish", "end_punctuation", "code_position", "newlines", "line_too_long", "page_too_tall", "bad_break"}
)


class IssueModel(QAbstractTableModel):
    #: Kullanıcı çeviri hücresini değiştirdi: (satır kimliği, yeni metin). Model metni kendisi değiştirmez.
    translation_edited = Signal(int, str)

    def __init__(self) -> None:
        super().__init__()
        self.issues: list[QaIssue] = []
        self.rows: dict[int, TranslationRow] = {}

    def set_issues(self, issues: list[QaIssue], rows: dict[int, TranslationRow] | None = None) -> None:
        self.beginResetModel()
        self.issues = issues
        self.rows = rows or {}
        self.endResetModel()

    def replace_row(self, row_id: int, issues: list[QaIssue], row: TranslationRow) -> None:
        """Satırın bulgularını yenisiyle değiştirir; ilk eski bulgunun yerine yazılır, öteki satırlara dokunulmaz."""
        self.rows[row_id] = row
        old = [n for n, i in enumerate(self.issues) if i.row_id == row_id]
        at = old[0] if old else len(self.issues)
        for n in reversed(old):
            self.beginRemoveRows(QModelIndex(), n, n)
            del self.issues[n]
            self.endRemoveRows()
        if issues:
            self.beginInsertRows(QModelIndex(), at, at + len(issues) - 1)
            self.issues[at:at] = issues
            self.endInsertRows()

    def flags(self, index: _Index) -> Qt.ItemFlag:
        flags = super().flags(index)
        if index.isValid() and index.column() == COL_TRANSLATION and self.issues[index.row()].row_id in self.rows:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: _Index, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole or index.column() != COL_TRANSLATION:
            return False
        issue = self.issues[index.row()]
        row = self.rows.get(issue.row_id)
        text = str(value)
        if row is not None and text != row.translation:
            self.translation_edited.emit(issue.row_id, text)
        return False

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
        if role == Qt.ItemDataRole.EditRole and col == COL_TRANSLATION:
            return self._texts(i)[1]
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
            return tip_html(f"{text}\n\n{EDIT_HINT if col == COL_TRANSLATION else OPEN_HINT}")
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
        self.kinds: frozenset[str] = frozenset()
        self.show_info = False

    def lessThan(self, left: _Index, right: _Index) -> bool:
        """Doğal sıralama: sayılar değerine göre (1, 2, 10), harfler Türkçe sırayla."""
        return natural_sort_key(str(left.data() or "")) < natural_sort_key(str(right.data() or ""))

    def update(self, kinds: frozenset[str], show_info: bool) -> None:
        self.beginFilterChange()
        self.kinds, self.show_info = kinds, show_info
        self.endFilterChange()

    def filterAcceptsRow(self, source_row: int, source_parent: _Index) -> bool:
        model = self.sourceModel()
        assert isinstance(model, IssueModel)
        i = model.issues[source_row]
        if self.kinds:
            return i.kind in self.kinds
        return self.show_info or i.severity != "info"


class _TranslationDelegate(QStyledItemDelegate):
    """Çeviri hücresi düzenleyicisi: Enter kaydeder, Shift+Enter satır sonu, Esc vazgeçer (Çevir tablosundaki gibi)."""

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
        rect.setHeight(max(rect.height(), 4 * option.fontMetrics.height()))
        editor.setGeometry(rect)


class QaPage(QWidget):
    translation_edited = Signal(int, str)  # satır kimliği, yeni çeviri (yerinde düzenleme)
    scan_fonts = Signal()
    run_checks = Signal()
    transliterate_changed = Signal(str)
    font_patch_changed = Signal(bool)
    open_row = Signal(int)  # satır kimliği → çeviri tablosunda o satırı aç
    fix_requested = Signal(list, list)  # düzeltilecek türler, satır kimlikleri (boş: tüm bulgular)
    fix_kinds_changed = Signal(list)  # kullanıcının işaretlediği türler (kalıcı saklanır)
    report_requested = Signal()  # bildirimdeki "Raporu Gör"
    #: Düzeltme sonucu (durum, metin, düğme adı): ana pencere bildirim olarak gösterir.
    fix_notice = Signal(str, str, str)
    #: Seçili serbest fontun RomFS yolu: dışa aktar / düzenlenmişi içe al / özgüne dön.
    font_export_requested = Signal(str)
    font_import_requested = Signal(str)
    font_reset_requested = Signal(str)
    fit_changed = Signal()  # kullanıcı sığdırma sınırını, kod türünü veya bir seçeneği değiştirdi
    learn_rules_requested = Signal(str)  # kapsam: "" proje, dosya yolu, GROUP_PREFIX+grup ya da EACH_GROUP
    add_spelling_requested = Signal(list)  # seçili yazım bulgularındaki sözcükler
    not_term_requested = Signal(list)  # seçili terim bulgularındaki ifadeler: "terim değil"
    user_dictionary_requested = Signal()
    fit_tab_shown = Signal()  # Sığdırma sekmesi görünür oldu (sınırlar tablosu ağır hesaplar ister)

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
        self.font_table.setHorizontalHeaderLabels(["Font", "Tür", "Eksik Türkçe harfler", "Ne yapılabilir", "Dosya"])
        self.font_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.font_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.font_table.setWordWrap(True)
        self.font_table.verticalHeader().hide()
        self.font_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        fh = self.font_table.horizontalHeader()
        for c in (0, 1, 2, 4):
            fh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        fh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.font_table.setMinimumHeight(180)
        self.font_table.setSortingEnabled(True)
        self.font_table.hide()
        self.font_card.body.addWidget(self.font_table)
        # Serbest TTF/OTF fontlar dışarıda (FontForge vb.) düzenlenip moda konabilir.
        self._font_overrides: dict[str, str] = {}
        self._editable_fonts: set[str] = set()
        font_row = QHBoxLayout()
        self.font_export_button = button("Fontu Dışa Aktar…", icon="file-up")
        self.font_export_button.setToolTip("Seçili fontu bir klasöre kaydeder; bir font düzenleyicide açabilirsiniz.")
        self.font_import_button = button("Düzenlenmiş Fontu İçe Al…", icon="file-down")
        self.font_import_button.setToolTip("Düzenlediğiniz TTF/OTF dosyası dışa aktarılan moda bu fontun yerine konur.")
        self.font_reset_button = button("Özgün Fonta Dön", icon="undo-2")
        self.font_reset_button.setToolTip("İçe alınan fontu bırakır; modda oyunun özgün fontu kalır.")
        self.font_export_button.clicked.connect(lambda: self._emit_font(self.font_export_requested))
        self.font_import_button.clicked.connect(lambda: self._emit_font(self.font_import_requested))
        self.font_reset_button.clicked.connect(lambda: self._emit_font(self.font_reset_requested))
        for b in (self.font_export_button, self.font_import_button, self.font_reset_button):
            font_row.addWidget(b)
        font_row.addStretch(1)
        self.font_tools = QWidget()
        self.font_tools.setLayout(font_row)
        self.font_tools.hide()
        self.font_card.body.addWidget(self.font_tools)
        self.font_table.itemSelectionChanged.connect(self._update_font_buttons)
        self._update_font_buttons()

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
        self.summary.setText("Henüz denetlenmedi.")
        self.summary_icon = QLabel()
        self.summary_icon.hide()
        row = self.check_bar.layout()
        assert isinstance(row, QHBoxLayout)
        row.insertWidget(0, self.summary_icon)
        #: Son düzeltme sonucu (bildirim merkezine gönderilen metin).
        self.last_fix_text = ""
        self.chip_bar = ChipBar()
        self.chip_bar.selection_changed.connect(self._refilter)
        self.check_card.body.addWidget(self.chip_bar)
        self.model = IssueModel()
        self.model.translation_edited.connect(self.translation_edited)
        self.proxy = IssueFilter()
        self.proxy.setSourceModel(self.model)
        self.table = FitTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setItemDelegateForColumn(COL_TRANSLATION, _TranslationDelegate(self.table))
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
        bind_icon(self.spell_add_button, "spell-check")
        self.user_dict_button = QAction("Yazım sözlüğünü aç…", self)
        self.user_dict_button.triggered.connect(self.user_dictionary_requested)
        bind_icon(self.user_dict_button, "book-open")
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._open)
        self.table.activated.connect(self._open)
        self.table.setToolTip(OPEN_HINT)
        self._fixes_collapsed_saved = False
        split = QHBoxLayout()
        split.setSpacing(12)
        split.addWidget(self.table, 1)
        split.addWidget(self._build_fix_section(), 0, Qt.AlignmentFlag.AlignTop)
        self.check_card.body.addLayout(split, 1)
        self.table.selectionModel().selectionChanged.connect(lambda *_a: self._selection_changed())
        check_lay.addWidget(self.check_bar)
        check_lay.addWidget(self.check_card, 1)
        self.tabs.addTab(check_tab, "Sorunlar")
        self._fit_tab = self.tabs.addTab(self._build_fit_tab(), "Sığdırma")
        self.tabs.addTab(scroll, "Font ve harfler")
        self.tabs.currentChanged.connect(self._tab_changed)

    def fit_tab_index(self) -> int:
        return self._fit_tab

    def fit_tab_visible(self) -> bool:
        return self.tabs.currentIndex() == self._fit_tab

    def _tab_changed(self, index: int) -> None:
        if index == self._fit_tab:
            self.fit_tab_shown.emit()

    # --- satır sığdırma -----------------------------------------------------------------

    def _build_fit_tab(self) -> QScrollArea:
        self._default: FitRules | None = None
        self._per_file: dict[str, FitRules] = {}
        self._per_group: dict[str, FitRules] = {}
        self._per_key: dict[str, FitRules] = {}
        self._kinds: dict[str, str] = {}
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

        # Ayarın etkisi: denetim sonucu burada görünür, ayar değişince ana pencere denetimi kendiliğinden yeniler.
        self._checked = False
        self._overflow_rows = 0
        result_row = QHBoxLayout()
        self.fit_result = label(_FIT_RESULT_EMPTY, "muted", wrap=True)
        result_row.addWidget(self.fit_result, 1)
        self.fit_result_show = QToolButton()
        self.fit_result_show.setText("Göster")
        self.fit_result_show.setProperty("role", "link")
        self.fit_result_show.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fit_result_show.setToolTip(tip_html("Taşan satırları Sorunlar sekmesinde gösterir."))
        self.fit_result_show.clicked.connect(self._show_overflow)
        self.fit_result_show.hide()
        result_row.addWidget(self.fit_result_show)
        body.addLayout(result_row)

        # Kod türü tahmini şüpheliyse (satır sonu gibi davranan "diğer" kod) kullanıcı Gelişmiş'i açmadan görür.
        self.fit_kind_warning = QToolButton()
        self.fit_kind_warning.setProperty("role", "link")
        self.fit_kind_warning.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fit_kind_warning.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        bind_icon(self.fit_kind_warning, "triangle-alert", size=14, tone="warning")
        self.fit_kind_warning.clicked.connect(self._open_fit_advanced)
        self.fit_kind_warning.hide()
        body.addWidget(self.fit_kind_warning, alignment=Qt.AlignmentFlag.AlignLeft)
        self.fit_advanced = Disclosure("Gelişmiş")
        body.addWidget(self.fit_advanced)
        adv = self.fit_advanced.body_layout
        adv.addWidget(
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
        adv.addWidget(self.fit_kinds)
        self.fit_kinds_empty = label("Metinlerde kontrol kodu yok.", "muted")
        adv.addWidget(self.fit_kinds_empty)

        lay.addWidget(self.fit_card)
        # Grup ve anahtar deseni başına sınırlar tek tabloda; elle sınır burada yazılır, "Hepsini Öğren" her grubu
        # ayrı öğrenir.
        self.limits_card = Card("Grup ve anahtar sınırları")
        self.limits = LimitsTable()
        self.limits.setMinimumHeight(260)
        self.limits.rule_edited.connect(self._limits_edited)
        self.fit_changed.connect(self._sync_limits)
        self.limits.learn_all_requested.connect(
            lambda: self._commit_pending(lambda: self.learn_rules_requested.emit(EACH_GROUP))
        )
        self.limits_card.body.addWidget(self.limits)
        lay.addWidget(self.limits_card)
        lay.addStretch(1)
        self._apply_fit_widgets([], [], [])
        return scroll

    def _show_fit_result(self, text: str, can_show: bool = False) -> None:
        self.fit_result.setText(text)
        self.fit_result_show.setVisible(can_show)

    def show_fit_checking(self) -> None:
        """Sığdırma sekmesinde sonuç özeti: denetim sürüyor."""
        self._show_fit_result(_FIT_RESULT_CHECKING)

    def show_check_failed(self, text: str) -> None:
        """Denetim çalışmadı: Sorunlar sekmesinde hata, Sığdırma sekmesinde "yenilenemedi" gösterilir."""
        self.show_fix_result("danger", text)
        self._show_fit_result(_FIT_RESULT_FAILED)

    def _update_fit_result(self, issues: Sequence[QaIssue]) -> None:
        """Denetim sonucundan sığdırma özetini yazar: sınırı aşan (satır uzun, sayfa uzun) satırlar sayılır."""
        self._checked = True
        if not self.fit_enabled.isChecked():
            self._overflow_rows = 0
            self._show_fit_result("Sığdırma kapalı; taşma denetlenmiyor.")
            return
        self._overflow_rows = len({i.row_id for i in issues if i.kind in _OVERFLOW_KINDS})
        if self._overflow_rows:
            self._show_fit_result(f"Bu ayarla {format_int(self._overflow_rows)} satır taşıyor.", True)
        else:
            self._show_fit_result("Taşan satır yok.")

    def _show_overflow(self) -> None:
        """Göster: Sorunlar sekmesi taşma türleriyle süzülmüş olarak açılır."""
        for kind, chip in self.chip_bar.chips.items():
            chip.blockSignals(True)
            chip.setChecked(kind in _OVERFLOW_KINDS)
            chip.blockSignals(False)
        self._refilter()
        self.tabs.setCurrentIndex(0)

    def _open_fit_advanced(self) -> None:
        self.fit_advanced.toggle.setChecked(True)

    def show_kind_warnings(self, labels: Sequence[str]) -> None:
        """Satır sonu olabilecek ama "Diğer" sayılan kodlar: tıklanınca Gelişmiş → Kod türleri açılır."""
        if not labels:
            self.fit_kind_warning.hide()
            return
        names = ", ".join(f"“{label}”" for label in labels[:3]) + (" …" if len(labels) > 3 else "")
        self.fit_kind_warning.setText(f"{names} satır sonu olabilir; kod türünü kontrol edin")
        self.fit_kind_warning.setToolTip(
            tip_html(
                "Bu kod sözcüklerin arasına boşluksuz giriyor. Satır sonuysa Gelişmiş → Kod türleri'nden türünü "
                "“Satır sonu” yapın; sınır hesabı ve satır bölme buna göre yapılır."
            )
        )
        self.fit_kind_warning.show()

    def _limits_edited(self, scope: str, rules: FitRules | None) -> None:
        """Sınırlar tablosunda bir grup ya da anahtar deseni sınırı değişti: yalnızca o girdi kartın ayarına işlenir."""
        if scope.startswith(SCOPE_GROUP):
            target, name = self._per_group, scope[len(SCOPE_GROUP) :]
        else:
            target, name = self._per_key, scope[len(SCOPE_KEY) :]
        if rules is None:
            target.pop(name, None)
        else:
            target[name] = rules
            if not self.fit_enabled.isChecked():
                # Sınır yazan kullanıcı onun uygulanmasını bekler: sığdırma açılır (proje sınırı eklenmez).
                with _Blocked(self.fit_enabled):
                    self.fit_enabled.setChecked(True)
                self._enabled = True
        self._show_scope()
        self.fit_changed.emit()

    def _sync_limits(self) -> None:
        """Kartın ve tablonun ayarı tek kaynaktan (kart) beslenir: ayar değişince tabloya güncel hali verilir."""
        self.limits.set_config(self.fit_config())

    def set_fit(self, config: FitConfig, files: list[str], labels: list[str], groups: Sequence[str] = ()) -> None:
        """Ayarı ve kapsam/kod listelerini gösterir; `fit_changed` yayılmaz. Seçili kapsam korunur.

        `groups`: kapsam seçicisinde ayrıca gösterilecek gruplar (kuralı olan gruplar da eklenir).
        """
        self._default = config.default
        self._per_file = dict(config.per_file)
        self._per_group = dict(config.per_group)
        self._per_key = dict(config.per_key)
        self._kinds = dict(config.kinds.mapping)
        self._enabled = config.enabled
        self._apply_fit_widgets(files, labels, groups)

    def fit_config(self) -> FitConfig:
        """Kartın gösterdiği ayar; sığdırma kapalıyken sınırlar saklanır ama uygulanmaz (`enabled=False`)."""
        kinds = CodeKinds(dict(self._kinds))
        return FitConfig(
            self._default,
            dict(self._per_file),
            kinds,
            self.fit_enabled.isChecked(),
            dict(self._per_group),
            dict(self._per_key),
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
        with _Blocked(self.fit_enabled, self.fit_scope):
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
        return self._default is not None or bool(self._per_file) or bool(self._per_group) or bool(self._per_key)

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
        self._editable_fonts = {f.source for f in report.fonts if is_editable_font(f)}
        for r, f in enumerate(sorted(report.fonts, key=lambda x: (x.language_specific, x.name))):
            miss = "?" if f.chars is None else (f.missing() or "yok")
            kind = f.kind + (" — dile özgü" if f.language_specific else "")
            advice = font_advice(f)
            for col, value in enumerate((f.name, kind, miss, advice, f.source.rsplit("/", 1)[-1])):
                item = QTableWidgetItem(value)
                item.setToolTip(f.source if col == 4 else (f.note or value))
                item.setData(Qt.ItemDataRole.UserRole, f.source)
                # Aynı paketteki fontlar (ör. data.unity3d) aynı yolu paylaşır; öneri satırın kendisinde tutulur.
                item.setData(_ADVICE_ROLE, advice)
                self.font_table.setItem(r, col, item)
        self.font_table.setSortingEnabled(True)
        self.font_table.setVisible(bool(report.fonts))
        self.font_tools.setVisible(bool(self._editable_fonts))
        self._show_overrides()
        self._update_font_buttons()

    def set_font_overrides(self, overrides: Mapping[str, str]) -> None:
        """İçe alınmış düzenli fontlar (RomFS yolu → dosya yolu): tabloda gösterilir, düğmeler buna göre."""
        self._font_overrides = dict(overrides)
        self._show_overrides()
        self._update_font_buttons()

    def _show_overrides(self) -> None:
        for r in range(self.font_table.rowCount()):
            item = self.font_table.item(r, 3)
            if item is None:
                continue
            stored = self._font_overrides.get(str(item.data(Qt.ItemDataRole.UserRole)))
            item.setText(f"İçe alındı: {Path(stored).name}" if stored else str(item.data(_ADVICE_ROLE)))

    def selected_font(self) -> str | None:
        items = self.font_table.selectedItems()
        return str(items[0].data(Qt.ItemDataRole.UserRole)) if items else None

    def _update_font_buttons(self) -> None:
        source = self.selected_font()
        editable = source is not None and source in self._editable_fonts
        self.font_export_button.setEnabled(editable)
        self.font_import_button.setEnabled(editable)
        self.font_reset_button.setEnabled(editable and source in self._font_overrides)

    def _emit_font(self, signal: SignalInstance) -> None:
        source = self.selected_font()
        if source is not None:
            signal.emit(source)

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
        self.model.set_issues(issues, {r.id: r for r in rows})
        self._issues_changed()

    def reset(self) -> None:
        """Denetim sonuçlarını siler (başka proje açıldı): liste, özet, çipler ve düzeltme sayıları boşalır."""
        self.model.set_issues([])
        self.chip_bar.set_counts({}, {})
        self._update_fix_counts([])
        self._refilter()
        self.summary.setText("Henüz denetlenmedi.")
        self.summary_icon.hide()
        self.last_fix_text = ""
        self._checked = False
        self._show_fit_result(_FIT_RESULT_EMPTY)

    def replace_row_issues(self, row_id: int, issues: list[QaIssue], row: TranslationRow) -> None:
        """Tek satırın bulgularını yenisiyle değiştirir (yerinde düzenleme sonrası); bulgu kalmadıysa satır düşer.

        Seçim ve kaydırma konumu korunur; çipler, düzeltme sayıları ve özet güncellenir.
        """
        self.replace_rows_issues({row_id: issues}, [row])

    def replace_rows_issues(self, issues_by_row: dict[int, list[QaIssue]], rows: Sequence[TranslationRow]) -> None:
        """Birkaç satırın bulgularını tek seferde yenisiyle değiştirir (düzenlenen satır ve eşdeşleri).

        Özet, çipler ve düzeltme sayıları yalnızca bir kez hesaplanır; seçim ve kaydırma konumu korunur.
        """
        selected = set(self._selected_row_ids())
        scroll = self.table.verticalScrollBar().value()
        for row in rows:
            self.model.replace_row(row.id, issues_by_row.get(row.id, []), row)
        self._issues_changed()
        for row_id in selected & issues_by_row.keys():
            self._select_row_id(row_id)
        self.table.verticalScrollBar().setValue(scroll)

    def _select_row_id(self, row_id: int) -> None:
        selection = self.table.selectionModel()
        for r in range(self.proxy.rowCount()):
            index = self.proxy.index(r, 0)
            if self.model.issues[self.proxy.mapToSource(index).row()].row_id == row_id:
                selection.select(
                    index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
                )

    def _issues_changed(self) -> None:
        """Bulgu listesi değişti: özet, çipler ve düzeltme sayıları yeniden hesaplanır."""
        issues = self.model.issues
        errors = sum(1 for i in issues if i.severity == SEVERITY_ERROR)
        warnings = sum(1 for i in issues if i.severity == SEVERITY_WARNING)
        if errors or warnings:
            parts = []
            if errors:
                parts.append(f"{format_int(errors)} hata")
            if warnings:
                parts.append(f"{format_int(warnings)} uyarı")
            self.summary.setText(" · ".join(parts))
            bind_icon(
                self.summary_icon,
                "circle-x" if errors else "triangle-alert",
                size=16,
                tone="danger" if errors else "warning",
            )
        else:
            self.summary.setText("Sorun bulunmadı.")
            bind_icon(self.summary_icon, "circle-check", size=16, tone="success")
        self.summary_icon.show()
        self.summary.setProperty("role", None)
        self._update_fit_result(issues)
        counts: dict[str, int] = {}
        severities: dict[str, str] = {}
        for i in issues:
            counts[i.kind] = counts.get(i.kind, 0) + 1
            severities[i.kind] = _worse(severities.get(i.kind, ""), i.severity)
        self.chip_bar.set_counts(counts, severities)
        self._update_fix_counts(issues)
        self._refilter()

    def bind_settings(self, settings: QSettings) -> None:
        """Bulgu tablosunun sütun genişliklerini ve gizli sütunlarını geri yükler."""
        self.fitter.bind_settings(settings, "qa/column_widths")
        self.column_menu.bind_settings(settings, "qa/hidden_columns")
        self._fix_settings: QSettings | None = settings
        saved = settings.value("qa/fixes_collapsed", None)
        if saved is not None:
            self.set_fixes_collapsed(str(saved).lower() in ("1", "true"))

    def _refilter(self) -> None:
        self.proxy.update(self.chip_bar.selected_kinds(), show_info=False)
        self._fit_rows()
        self._update_fix_boxes()

    def _fit_rows(self) -> None:
        """Satır yüksekliğini metne göre ayarlar; çok büyük listede pencere donmasın diye yalnızca sınıra kadar."""
        if self.proxy.rowCount() <= _FIT_ROWS_LIMIT:
            self.table.resizeRowsToContents()

    # --- düzeltmeler --------------------------------------------------------------------

    def _build_fix_section(self) -> QWidget:
        """Sağdaki daraltılabilir düzeltme paneli: bulgusu olan türler, kapsam seçimi ve düzeltme düğmesi."""
        self.fix_counts: dict[str, int] = dict.fromkeys(FIX_KINDS, 0)
        self.fix_boxes: dict[str, QCheckBox] = {}
        self._fixes_collapsed = False
        self._fixes_decided = False
        self._fix_settings = None
        panel = QFrame()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self.fix_toggle = QToolButton()
        self.fix_toggle.setText("Düzeltmeler")
        self.fix_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.fix_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fix_toggle.setToolTip(
            tip_html("İşaretli türlerdeki sorunlar düzeltilir. Onaylı satırlara dokunulmaz; Geri Al hepsini geri alır.")
        )
        bind_icon(self.fix_toggle, "panel-right")
        self.fix_toggle.clicked.connect(lambda: self.set_fixes_collapsed(not self._fixes_collapsed, save=True))
        outer.addWidget(self.fix_toggle)
        self.fix_body = QWidget()
        self.fix_body.setFixedWidth(_FIX_PANEL_WIDTH)
        lay = QVBoxLayout(self.fix_body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.fix_empty = label("Düzeltilecek sorun yok.", "muted")
        lay.addWidget(self.fix_empty)
        self.fix_links = QWidget()
        head = QHBoxLayout(self.fix_links)
        head.setContentsMargins(0, 0, 0, 0)
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
        lay.addWidget(self.fix_links)
        for kind in FIX_KINDS:
            check = QCheckBox()
            check.setChecked(kind not in RISKY_FIX_KINDS)
            check.setToolTip(tip_html(FIX_TIPS[kind]))
            check.toggled.connect(self._fix_selection_changed)
            self.fix_boxes[kind] = check
            lay.addWidget(check)
        self.fix_scope = QWidget()
        scope = QVBoxLayout(self.fix_scope)
        scope.setContentsMargins(0, 8, 0, 0)
        scope.setSpacing(2)
        self.scope_selected = QRadioButton("Listede seçili 0 bulgu")
        self.scope_all = QRadioButton("Tüm bulgular (0)")
        self.scope_all.setChecked(True)
        group = QButtonGroup(self)
        for radio in (self.scope_selected, self.scope_all):
            group.addButton(radio)
            scope.addWidget(radio)
            radio.toggled.connect(lambda _c: self._update_fix_boxes())
        lay.addWidget(self.fix_scope)
        self.fix_button = button("Seçilenleri Düzelt", "primary", icon="refresh-cw")
        self.fix_button.clicked.connect(lambda: self._commit_pending(self._request_fix))
        lay.addWidget(self.fix_button)
        outer.addWidget(self.fix_body)
        self._update_fix_boxes()
        panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        return panel

    def fixes_collapsed(self) -> bool:
        return self._fixes_collapsed

    def set_fixes_collapsed(self, collapsed: bool, save: bool = False) -> None:
        """Düzeltme panelini açar/kapatır; `save` ise seçim ayara yazılır (kullanıcının kendi seçimi)."""
        self._fixes_collapsed = collapsed
        self._fixes_decided = True
        self.fix_body.setVisible(not collapsed)
        if save and self._fix_settings is not None:
            self._fix_settings.setValue("qa/fixes_collapsed", int(collapsed))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._fixes_decided:  # kayıtlı seçim yoksa dar pencerede kapalı başlar
            self.set_fixes_collapsed(self.width() < _NARROW_WIDTH)

    def _request_fix(self) -> None:
        self.fix_requested.emit(self.fix_kinds_to_apply(), self._scope_row_ids())

    def _scope_row_ids(self) -> list[int]:
        return self._selected_row_ids() if self.scope_selected.isChecked() and self.scope_selected.isEnabled() else []

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
        """Panelin yazılarını, görünürlüğünü ve düğme durumunu tazeler; bulgusu olmayan tür görünmez."""
        for kind, check in self.fix_boxes.items():
            n = self.fix_counts[kind]
            check.setText(f"{KIND_LABELS[kind]}  {format_int(n)}")
            check.setVisible(n > 0)
        any_fixable = any(self.fix_counts.values())
        self.fix_empty.setVisible(not any_fixable)
        for part in (self.fix_links, self.fix_scope, self.fix_button):
            part.setVisible(any_fixable)
        selected = len(self.table.selectionModel().selectedRows())
        planned = sum(self.fix_counts[k] for k in self.checked_fix_kinds())
        self.scope_selected.setText(f"Listede seçili {format_int(selected)} bulgu")
        self.scope_selected.setEnabled(selected > 0)
        self.scope_all.setText(f"Tüm bulgular ({format_int(planned)})")
        if not selected and self.scope_selected.isChecked():
            self.scope_all.setChecked(True)
        self.fix_button.setEnabled(bool(self.fix_kinds_to_apply()))

    def show_fix_result(self, state: str, text: str, action: str = "") -> None:
        """Düzeltme/denetim sonucunu bildirim merkezine iletir (sayfada kalıcı kutu yok); `action`: düğme adı."""
        self.last_fix_text = text
        if text:
            self.fix_notice.emit(state, text, action)

    def _selected_row_ids(self) -> list[int]:
        """Bulgu tablosunda seçili satırların çeviri satırı kimlikleri; seçim yoksa boş (tüm bulgular)."""
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        return sorted({self.model.issues[r].row_id for r in rows})

    def _selection_changed(self) -> None:
        had = self.scope_selected.isEnabled()
        self._update_fix_boxes()
        if self.scope_selected.isEnabled() and not had:  # seçim başladı: kapsam seçilenler olur
            self.scope_selected.setChecked(True)
        self.spell_add_button.setEnabled(bool(self._selected_spelling_words()))

    def _selected_issues(self) -> list[QaIssue]:
        rows = sorted({self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.issues[r] for r in rows]

    def _fix_now(self, kinds: list[str], row_ids: list[int]) -> None:
        self._commit_pending(lambda: self.fix_requested.emit(kinds, row_ids))

    def context_menu(self) -> QMenu:
        """Seçili bulguya göre bağlam menüsü; her öğe kullanılabilir olduğunda görünür."""
        menu = QMenu(self)
        issues = self._selected_issues()
        if issues:
            present = {i.kind for i in issues}
            kinds = [k for k in FIX_KINDS if k in present]
            row_ids = sorted({i.row_id for i in issues})
            if kinds:
                fix_row = menu.addAction(
                    icon("refresh-cw"), "Bu satırları düzelt" if len(row_ids) > 1 else "Bu satırı düzelt"
                )
                fix_row.triggered.connect(lambda: self._fix_now(kinds, row_ids))
                fix_kind = menu.addAction(icon("replace-all"), "Bu türdeki tümünü düzelt")
                fix_kind.triggered.connect(lambda: self._fix_now(kinds, []))
            show = menu.addAction(icon("arrow-left-right"), "Çevir'de göster")
            show.triggered.connect(lambda: self.open_row.emit(issues[0].row_id))
            menu.addSeparator()
        if self.spell_add_button.isEnabled():
            menu.addAction(self.spell_add_button)
        phrases = self._selected_term_phrases()
        if phrases:
            not_term = menu.addAction(icon("x"), "Terim değil")
            not_term.setToolTip("Seçili ifadeler bu projede terim sayılmaz; tutarsızlık aranmaz.")
            not_term.triggered.connect(lambda: self.not_term_requested.emit(phrases))
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

    def _selected_term_phrases(self) -> list[str]:
        """Seçili terim bulgularındaki ifadeler (tekrarsız)."""
        phrases: dict[str, None] = {}
        for issue in self._selected_issues():
            if issue.kind == "term":
                phrases.update(dict.fromkeys(issue.words))
        return list(phrases)

    def _add_spelling(self) -> None:
        words = self._selected_spelling_words()
        if words:
            self.add_spelling_requested.emit(words)

    def _open(self, index: QModelIndex) -> None:
        if index.column() == COL_TRANSLATION:  # çeviri hücresi yerinde düzenlenir
            return
        issue = self.model.issues[self.proxy.mapToSource(index).row()]
        self.open_row.emit(issue.row_id)


_SEVERITY_ORDER = {"": 0, "info": 1, SEVERITY_WARNING: 2, SEVERITY_ERROR: 3}


def _worse(a: str, b: str) -> str:
    return a if _SEVERITY_ORDER.get(a, 0) >= _SEVERITY_ORDER.get(b, 0) else b


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
