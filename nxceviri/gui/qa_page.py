"""Adım 4 — Kontrol Et: satır denetimleri, satır sığdırma ayarları, font glif denetimi, font yaması ve harf
dönüştürme seçimi."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QSettings,
    QSortFilterProxyModel,
    Qt,
    Signal,
    SignalInstance,
)
from PySide6.QtGui import QAction, QActionGroup
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
    QMessageBox,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa import transliterate
from nxceviri.core.qa.autofix import FIX_KINDS, FixPlan
from nxceviri.core.qa.checks import (
    KIND_LABELS,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_LABELS,
    SEVERITY_WARNING,
    QaIssue,
)
from nxceviri.core.qa.fonts import FontReport, font_advice, is_editable_font
from nxceviri.core.translate.codekinds import KIND_NAMES, CodeKinds
from nxceviri.core.translate.fit import DEFAULT_VARIABLE_WIDTH, PROBLEM_LINE, PROBLEM_PAGE, FitRules
from nxceviri.core.translate.fitconfig import BOX_GROUP, BOX_ROW, EACH_GROUP, GROUP_PREFIX, FitConfig, WidthRules
from nxceviri.core.translate.fitwidth import KIND_TOO_WIDE
from nxceviri.core.translate.limits import SCOPE_GROUP, SCOPE_KEY
from nxceviri.core.translate.widths import DEFAULT_TOLERANCE, WidthTable
from nxceviri.gui.graphics_check import GraphicsCheckTab
from nxceviri.gui.icons import bind_icon, icon
from nxceviri.gui.issue_chips import Disclosure
from nxceviri.gui.issue_kinds import IGNORED_KIND, KIND_GROUPS, KindList
from nxceviri.gui.issue_rows import ROLE_NUMBER, ROLE_SEVERITY, ROLE_SOURCE, ROLE_TRANSLATION, IssueRowView
from nxceviri.gui.limits_table import LimitsTable
from nxceviri.gui.marked_delegate import ROW_ROLE
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import ActionBar, Banner, BusyState, Card, PageHeader, button, format_int, label, tip_html

_Index = QModelIndex | QPersistentModelIndex
#: Bu kadar bulguya kadar satırlar metne göre yükseltilir (üstünde ipucundan okunur).
_FIT_ROWS_LIMIT = 3000
#: Sığdırma ilk açıldığında (henüz sınır yokken) kutularda görünen değerler.
_FIT_START_WIDTH, _FIT_START_LINES = 40, 3
_FIT_OFF_TEXT = "Sınır girilmedi; sığdırma kapalı."
_FIT_KEPT_TEXT = "Sığdırma kapalı; sınırlar saklanıyor."
#: Bulgu listesi boşken görünen yazılar.
_EMPTY_UNCHECKED = "Denetle’ye basınca bulunan sorunlar burada listelenir."
_EMPTY_CLEAN = "Sorun bulunmadı."
_EMPTY_FILTERED = "Bu süzgeçte gösterilecek bulgu yok."
#: Riskli türler kapsamdayken düzeltme çubuğunun ikinci satırı.
_FIX_WARNING = "Bu düzeltmeler yanılabilir; sonucu gözden geçirin."
#: Düzelt bildirimi için plan, kapsam bu satır sayısına kadar hesaplanır (her seçim değişiminde bekletmemek için).
_FIX_PLAN_ROWS = 1500
_FIT_RESULT_EMPTY = "Henüz denetlenmedi. Önce Sorunlar sekmesinde “Denetle”ye basın."
_FIT_RESULT_CHECKING = "Denetleniyor…"
#: Denetim sürerken sağdaki liste yerine görünen bekleme: başlık (ardına "%N" gelir) ve ilk açıklama.
_CHECKING_TITLE = "Denetleniyor…"
GRAPHICS_TAB_TITLE = "Grafik"
_CHECKING_PREPARING = "Denetim hazırlanıyor…"
_CHECK_STOPPED = "Denetim durduruldu."
_CHECK_STOPPED_CHANGED = "Denetim durduruldu; değişen {count} satır denetlenmedi. Denetle'ye basın."
_FIT_RESULT_FAILED = "Denetim yenilenemedi. Sorunlar sekmesinde “Denetle”ye basarak yeniden deneyin."
#: "Taşıyor" sayılan bulgu türleri: satır ya da sayfa sınırını ve fontla ölçülen kutuyu aşanlar (kötü bölünme taşma
#: değildir).
_OVERFLOW_KINDS = (PROBLEM_LINE, PROBLEM_PAGE, KIND_TOO_WIDE)
#: Genişlik denetiminin kutu seçenekleri (gösterilen ad, değer).
_WIDTH_BOXES = (("Kapsamdaki en geniş orijinal", BOX_GROUP), ("Satırın kendi orijinali", BOX_ROW))
_WIDTH_FONT_APPROX = "Ölçüm: yaklaşık tablo — Font ve harfler'den fontları tarayın"


#: Satırın çeviri ekranında nasıl açılacağı; hücre ipuçlarının sonuna eklenir.
OPEN_HINT = "Çift tıklayın veya Enter'a basın: satır çeviri ekranında düzenlemeye açılır."
#: Çeviri hücresi bu tabloda yerinde düzenlenir.
EDIT_HINT = (
    "Çift tıklayın veya F2'ye basın: çeviriyi burada düzenleyin "
    "(Enter kaydeder ve satırı onaylar, Shift+Enter satır sonu)."
)
#: Font tablosu hücresinde fontun kendi "Ne yapılabilir" önerisi (İçe alındı yazısı kalkınca geri konur).
_ADVICE_ROLE = Qt.ItemDataRole.UserRole + 1
_FONT_EXPORT_TIP = "Seçili fontu bir klasöre kaydeder; bir font düzenleyicide açabilirsiniz."
_FONT_IMPORT_TIP = "Düzenlediğiniz TTF/OTF dosyası dışa aktarılan moda bu fontun yerine konur."
_FONT_LOCKED_TIP = (
    "Bu font dışarıda düzenlenemez; yalnızca oyunda serbest duran TTF/OTF dosyaları dışa aktarılıp içe alınabilir."
)
#: Font tablosunda Dosya sütunu dar başlar (tam yol ipucunda).
_FILE_WIDTH = 150
#: Satır ipucunda orijinal ve çeviriden en çok bu kadar karakter gösterilir.
_TIP_CHARS = 1500
#: Varsayılan sıra: önce önem, sonra türün listedeki yeri.
_KIND_ORDER = {kind: n for n, kind in enumerate(k for _title, kinds in KIND_GROUPS for k in kinds)}

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
#: Metni yeniden biçimleyen ya da kod yerini değiştiren türler: "Tüm bulgular"da düzeltilmez; yalnızca türü solda
#: ya da satırı listede seçilince düzeltilir; birden çok satırda uygulanmadan önce onay sorulur (`ask_risky_fix`).
RISKY_FIX_KINDS = frozenset(
    {"ascii_turkish", "end_punctuation", "code_position", "newlines", "line_too_long", "page_too_tall", "bad_break"}
)


def ask_risky_fix(parent: QWidget, text: str) -> bool:
    """Riskli toplu düzeltmenin onay sorusu (testler bu işlevi değiştirir; kipli pencere açmasın diye)."""
    answer = QMessageBox.question(parent, "Toplu düzeltme", text)
    return answer == QMessageBox.StandardButton.Yes


#: Bulgu listesinin sıralama düzenleri (ayarda saklanan değer) ve sağ tık menüsündeki adları.
SORT_SEVERITY, SORT_NUMBER, SORT_FINDING, SORT_FILE = "severity", "number", "finding", "file"
SORT_LABELS = {
    SORT_SEVERITY: "Önem sırası",
    SORT_NUMBER: "Satır numarası",
    SORT_FINDING: "Bulguya göre",
    SORT_FILE: "Dosyaya göre",
}
_SORT_SETTING = "qa/sort"
_SortKey = tuple[int | str, ...]


class IssueModel(QAbstractTableModel):
    """Bulgu listesi modeli: tek sütun; her satırın bilgisi rollerle (açıklama, orijinal, çeviri, No, önem) okunur.

    Varsayılan sıra: önem (hata, uyarı, bilgi) → tür (listedeki sırayla) → çeviri satırı numarası; `set_sort` ile
    satır numarasına, bulgu metnine ya da dosyaya göre de sıralanabilir.
    """

    #: Kullanıcı çeviriyi değiştirdi: (satır kimliği, yeni metin). Model metni kendisi değiştirmez.
    translation_edited = Signal(int, str)

    def __init__(self) -> None:
        super().__init__()
        self.issues: list[QaIssue] = []
        self.rows: dict[int, TranslationRow] = {}
        #: Satır kimliğinden çeviri tablosundaki No'ya; yoksa (0) No gösterilmez.
        self.number_of: Callable[[int], int] | None = None
        self._keys: list[_SortKey] = []
        self.sort_mode = SORT_SEVERITY

    def _number(self, row_id: int) -> int:
        return self.number_of(row_id) if self.number_of is not None else 0

    def _key(self, issue: QaIssue) -> _SortKey:
        number = self._number(issue.row_id) or issue.row_id
        severity = -_SEVERITY_ORDER.get(issue.severity, 0)
        kind = _KIND_ORDER.get(issue.kind, len(_KIND_ORDER))
        if self.sort_mode == SORT_NUMBER:
            return (number, severity, kind, issue.row_id)
        if self.sort_mode == SORT_FINDING:
            return (issue.message.casefold(), number, issue.row_id)
        if self.sort_mode == SORT_FILE:
            row = self.rows.get(issue.row_id)
            return (row.file if row is not None else "", number, issue.row_id)
        return (severity, kind, number, issue.row_id)

    def set_sort(self, mode: str) -> None:
        """Sıralama düzenini değiştirir ve listeyi yeniden sıralar; bilinmeyen değer varsayılana düşer."""
        self.sort_mode = mode if mode in SORT_LABELS else SORT_SEVERITY
        self.set_issues(self.issues, self.rows)

    def set_issues(self, issues: list[QaIssue], rows: dict[int, TranslationRow] | None = None) -> None:
        self.beginResetModel()
        self.rows = rows or {}
        keyed = sorted(((self._key(i), n, i) for n, i in enumerate(issues)), key=lambda t: (t[0], t[1]))
        self.issues = [i for _k, _n, i in keyed]
        self._keys = [k for k, _n, _i in keyed]
        self.endResetModel()

    def replace_row(self, row_id: int, issues: list[QaIssue], row: TranslationRow) -> None:
        """Satırın bulgularını yenisiyle değiştirir; yenileri sıralı yerlerine girer, öteki satırlara dokunulmaz."""
        self.rows[row_id] = row
        for n in reversed([n for n, i in enumerate(self.issues) if i.row_id == row_id]):
            self.beginRemoveRows(QModelIndex(), n, n)
            del self.issues[n]
            del self._keys[n]
            self.endRemoveRows()
        for issue in issues:
            key = self._key(issue)
            at = bisect_right(self._keys, key)
            self.beginInsertRows(QModelIndex(), at, at)
            self.issues.insert(at, issue)
            self._keys.insert(at, key)
            self.endInsertRows()

    def flags(self, index: _Index) -> Qt.ItemFlag:
        flags = super().flags(index)
        if index.isValid() and self.issues[index.row()].row_id in self.rows:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: _Index, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
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
        return 0 if parent.isValid() else 1

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        i = self.issues[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return i.message
        if role == ROLE_SEVERITY:
            return i.severity
        if role == ROLE_SOURCE:
            return self._texts(i)[0]
        if role in (ROLE_TRANSLATION, Qt.ItemDataRole.EditRole):
            return self._texts(i)[1]
        if role == ROLE_NUMBER:
            return self._number(i.row_id)
        if role == ROW_ROLE:
            return self.rows.get(i.row_id)
        kind = KIND_LABELS.get(i.kind, i.kind)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f"{SEVERITY_LABELS[i.severity]}, {kind}: {i.message}"
        if role == Qt.ItemDataRole.ToolTipRole:
            source, translation = self._texts(i)
            parts = [f"{kind} ({SEVERITY_LABELS[i.severity]})", i.message]
            if source:
                parts.append(f"Orijinal:\n{source[:_TIP_CHARS]}")
            if translation:
                parts.append(f"Çeviri:\n{translation[:_TIP_CHARS]}")
            parts.append(f"{OPEN_HINT}\n{EDIT_HINT}")
            return tip_html("\n\n".join(parts))
        return None


class IssueFilter(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.kinds: frozenset[str] = frozenset()
        self.show_info = False

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


class QaPage(QWidget):
    translation_edited = Signal(int, str)  # satır kimliği, yeni çeviri (yerinde düzenleme)
    scan_fonts = Signal()
    run_checks = Signal()
    stop_checks = Signal()  # Denetim sürerken düğme "Durdur" olur; tıklanınca bu yayılır
    transliterate_changed = Signal(str)
    font_patch_changed = Signal(bool)
    open_row = Signal(int)  # satır kimliği → çeviri tablosunda o satırı aç
    fix_requested = Signal(list, list)  # düzeltilecek türler, satır kimlikleri (boş: tüm bulgular)
    export_findings_requested = (
        Signal()
    )  # "Bulguları dışa aktar…": görünen/seçili bulguları dış redaksiyon dosyasına yaz
    #: Düzelt bildiriminin planı: (satırlar, o satırların bulguları, türler) → plan; verilmezse bulgu sayısı yazılır.
    fix_planner: Callable[[list[TranslationRow], list[QaIssue], list[str]], FixPlan] | None = None
    _plan_cache: tuple[tuple[tuple[str, ...], tuple[int, ...]], FixPlan] | None = None
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
    not_profanity_requested = Signal(list)  # seçili küfür / argo bulgularındaki sözcükler: "argo değil"
    user_dictionary_requested = Signal()
    #: Belirsiz bir sözcük için seçilen yazım: (sözcük anahtarı, seçilen aday); projedeki bütün satırlara uygulanır.
    ascii_choice_requested = Signal(str, str)
    ignore_requested = Signal(list)  # [(satır kimliği, tür)]: bulguları yok say
    unignore_requested = Signal(list)  # [(satır kimliği, tür)]: yok saymayı kaldır
    fit_tab_shown = Signal()  # Sığdırma sekmesi görünür oldu (sınırlar tablosu ağır hesaplar ister)
    graphics_tab_shown = Signal()  # Grafik sekmesi görünür oldu (bayatsa resimler denetlenir)

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
        self.font_button.setToolTip(
            tip_html("Oyunun fontlarında Türkçe harflerin (ç ğ ı İ ö ş ü) olup olmadığına bakar.")
        )
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
        fh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for c in (0, 1, 2):
            fh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        fh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # "Ne yapılabilir" en önemli sütun: kalanı alır
        fh.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.font_table.setColumnWidth(4, _FILE_WIDTH)
        self.font_table.setTextElideMode(Qt.TextElideMode.ElideMiddle)  # uzun dosya adı ortadan kısalır
        self.font_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.font_table.setMinimumHeight(180)
        self.font_table.setSortingEnabled(True)
        self.font_table.hide()
        self.font_card.body.addWidget(self.font_table)
        # Serbest TTF/OTF fontlar dışarıda (FontForge vb.) düzenlenip moda konabilir.
        self._font_overrides: dict[str, str] = {}
        self._editable_fonts: set[str] = set()
        font_row = QHBoxLayout()
        self.font_export_button = button("Fontu Dışa Aktar…", icon="file-up")
        self.font_export_button.setToolTip(_FONT_EXPORT_TIP)
        self.font_import_button = button("Düzenlenmiş Fontu İçe Al…", icon="file-down")
        self.font_import_button.setToolTip(_FONT_IMPORT_TIP)
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
            rb.setToolTip(tip_html(_MODE_TIPS[mode]))
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
        self.check_button.setToolTip(
            tip_html("Çevirileri kontrol kodu, uzunluk, terim ve yazım sorunlarına karşı tarar; çeviriler değişmez.")
        )
        self.check_button.clicked.connect(self._check_clicked)
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
        self._checking = False  # denetim sürüyor (bekleme görünür)
        self.kind_list = KindList()
        self.kind_list.selection_changed.connect(self._refilter)
        self._settings: QSettings | None = None
        #: Yok sayılan bulgular; "Yok sayılanlar" seçiliyken tablo bunları, `_normal` de gerçek bulguları tutar.
        self._ignored: list[QaIssue] = []
        self._ignored_view = False
        self._normal: list[QaIssue] = []
        self._rows: dict[int, TranslationRow] = {}
        self.model = IssueModel()
        self.model.translation_edited.connect(self.translation_edited)
        self.proxy = IssueFilter()
        self.proxy.setSourceModel(self.model)
        self.table = IssueRowView()
        self.table.setModel(self.proxy)
        # Yazım sözlüğü eylemleri bulgu listesinin sağ tık menüsünde.
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
        right = QVBoxLayout()
        right.setSpacing(10)
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self._build_fix_bar())
        right.addWidget(self.table, 1)
        results = QWidget()
        results.setLayout(right)
        # Denetim sürerken bulgu listesinin yerini maskotlu bekleme alır (boş liste "denetlenmedi" gibi görünmesin).
        self.waiting = BusyState(_CHECKING_TITLE, _CHECKING_PREPARING)
        self.stack = QStackedWidget()
        self.stack.addWidget(results)
        self.stack.addWidget(self.waiting)
        split = QHBoxLayout()
        split.setSpacing(12)
        split.addWidget(self.kind_list)
        split.addWidget(self.stack, 1)
        self.check_card.body.addLayout(split, 1)
        self.table.selectionModel().selectionChanged.connect(lambda *_a: self._selection_changed())
        check_lay.addWidget(self.check_bar)
        check_lay.addWidget(self.check_card, 1)
        self.tabs.addTab(check_tab, "Sorunlar")
        self._fit_tab = self.tabs.addTab(self._build_fit_tab(), "Sığdırma")
        self.tabs.addTab(scroll, "Font ve harfler")
        #: Özgün ve Türkçe resimlerin karşılaştırılması (iş akışı `GraphicsController`'da).
        self.graphics = GraphicsCheckTab()
        self._graphics_tab = self.tabs.addTab(self.graphics, GRAPHICS_TAB_TITLE)
        self.tabs.currentChanged.connect(self._tab_changed)
        self._refilter()
        self._update_check_button()

    def fit_tab_index(self) -> int:
        return self._fit_tab

    def fit_tab_visible(self) -> bool:
        return self.tabs.currentIndex() == self._fit_tab

    def _tab_changed(self, index: int) -> None:
        if index == self._fit_tab:
            self.fit_tab_shown.emit()
        elif index == self._graphics_tab:
            self.graphics_tab_shown.emit()

    def set_graphics_count(self, count: int) -> None:
        """Grafik sekmesinin başlığı sorunlu resim sayısını gösterir: "Grafik (3)"; sorun yoksa yalnızca "Grafik"."""
        title = f"{GRAPHICS_TAB_TITLE} ({format_int(count)})" if count > 0 else GRAPHICS_TAB_TITLE
        self.tabs.setTabText(self._graphics_tab, title)

    # --- satır sığdırma -----------------------------------------------------------------

    def _build_fit_tab(self) -> QScrollArea:
        self._default: FitRules | None = None
        self._per_file: dict[str, FitRules] = {}
        self._per_group: dict[str, FitRules] = {}
        self._per_key: dict[str, FitRules] = {}
        self._width_default: WidthRules | None = None
        self._width_files: dict[str, WidthRules] = {}
        self._width_groups: dict[str, WidthRules] = {}
        self._width_keys: dict[str, WidthRules] = {}
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
        self.fit_enabled.setToolTip(
            tip_html("Açıkken çevirilerin oyunun metin kutusuna sığıp sığmadığı aşağıdaki sınırlara göre denetlenir.")
        )
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
        self.fit_inherit.setToolTip(tip_html("Seçili dosya ya da grup, tüm projenin sınırlarını kullanır."))
        self.fit_inherit.toggled.connect(self._inherit_toggled)
        scope_row.addWidget(self.fit_scope)
        scope_row.addWidget(self.fit_inherit)
        form.addRow("Kapsam:", scope_row)
        self.fit_width = QSpinBox()
        self.fit_width.setRange(1, 999)
        self.fit_width.setValue(_FIT_START_WIDTH)
        self.fit_width.setToolTip(tip_html("Oyundaki metin kutusunun bir satırına sığan en fazla harf sayısı."))
        self.fit_width.valueChanged.connect(lambda _v: self._fit_changed())
        form.addRow("Satırda en çok karakter:", self.fit_width)
        self.fit_lines = QSpinBox()
        self.fit_lines.setRange(1, 99)
        self.fit_lines.setValue(_FIT_START_LINES)
        self.fit_lines.setToolTip(
            tip_html("Metin kutusunun bir sayfasına sığan satır sayısı; fazlası sonraki sayfaya geçer.")
        )
        self.fit_lines.valueChanged.connect(lambda _v: self._fit_changed())
        form.addRow("Sayfada en çok satır:", self.fit_lines)
        self.fit_width_check = QCheckBox("Genişliği fontla denetle")
        self.fit_width_check.setToolTip(
            tip_html(
                "Seçili kapsamda çevirinin ekrandaki genişliği oyunun fontuyla ölçülür ve orijinal kutuyla "
                "karşılaştırılır. Menü ve düğme gibi kısa metinler için; aşan satır uyarı olarak görünür."
            )
        )
        self.fit_width_check.toggled.connect(lambda _c: self._width_changed())
        form.addRow("Genişlik:", self.fit_width_check)
        self.fit_width_tolerance = QSpinBox()
        self.fit_width_tolerance.setRange(0, 200)
        self.fit_width_tolerance.setPrefix("%")
        self.fit_width_tolerance.setValue(round(DEFAULT_TOLERANCE * 100))
        self.fit_width_tolerance.setToolTip(tip_html("Çevirinin kutudan ne kadar geniş olabileceği; fazlası uyarıdır."))
        self.fit_width_tolerance.valueChanged.connect(lambda _v: self._width_changed())
        form.addRow("Genişlik payı:", self.fit_width_tolerance)
        self.fit_width_box = QComboBox()
        for name, value in _WIDTH_BOXES:
            self.fit_width_box.addItem(name, value)
        self.fit_width_box.setToolTip(
            tip_html(
                "Kutu: kapsamdaki en geniş tek satırlı orijinal (menü öğeleri aynı kutuyu paylaşır; daha az yanlış "
                "uyarı) ya da satırın kendi orijinali."
            )
        )
        self.fit_width_box.currentIndexChanged.connect(lambda _i: self._width_changed())
        form.addRow("Kutu:", self.fit_width_box)
        body.addLayout(form)
        self.fit_width_font = label(
            _WIDTH_FONT_APPROX,
            "muted",
            wrap=True,
            tip="Genişlik bu tabloyla ölçülür. Fontlar taranınca oyunun fontu kullanılır; sonuç daha doğru olur.",
        )
        body.addWidget(self.fit_width_font)
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
        kh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
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
        self.limits.setMinimumHeight(150)
        self.limits.rule_edited.connect(self._limits_edited)
        self.fit_changed.connect(self._sync_limits)
        self.limits.learn_all_requested.connect(
            lambda: self._commit_pending(lambda: self.learn_rules_requested.emit(EACH_GROUP))
        )
        self.limits_card.body.addWidget(self.limits)
        lay.addWidget(self.limits_card, 1)  # sekmede kalan yüksekliği doldurur; sığmazsa sayfa kayar
        self._apply_fit_widgets([], [], [])
        return scroll

    def _show_fit_result(self, text: str, can_show: bool = False) -> None:
        self.fit_result.setText(text)
        self.fit_result.setVisible(self.fit_enabled.isChecked())  # kapalıyken üstteki özet yeter
        self.fit_result_show.setVisible(can_show)

    def show_fit_checking(self) -> None:
        """Sığdırma sekmesinde sonuç özeti: denetim sürüyor."""
        self._show_fit_result(_FIT_RESULT_CHECKING)

    @property
    def checking(self) -> bool:
        return self._checking

    def mark_checking(self) -> None:
        """Denetim arka planda sürüyor (Denetle ya da düzeltme sonrası tam denetim): bulgu listesinin yerini bekleme
        alır, sayılar "—" olur, düzeltme çubuğu gizlenir, "Denetle" düğmesi "Durdur" olur."""
        self._plan_cache = None
        self.summary.setText(_CHECKING_TITLE)
        self.summary_icon.hide()
        self.fix_bar.hide()
        self._show_fit_result(_FIT_RESULT_CHECKING)
        self.waiting.update_progress(0, 0, _CHECKING_PREPARING)
        self._set_checking(True)

    def update_check_progress(self, done: int, total: int, message: str) -> None:
        """Gerçek ilerleme (denetlenen / toplam); denetim sürmüyorsa (arka plan yenilemesi) bir şey yapmaz."""
        if self._checking:
            self.waiting.update_progress(done, total, message)

    def changed_rows(self, current: Sequence[TranslationRow]) -> list[TranslationRow]:
        """Bulgusu olup çevirisi panodaki anlık görüntüden ayrılmış satırlar (güncel hâliyle): bulguları eskimiştir."""
        with_issues = {i.row_id for i in self.all_issues()}
        return [
            r
            for r in current
            if r.id in with_issues and r.id in self._rows and self._rows[r.id].translation != r.translation
        ]

    def stop_checking(self, changed: Sequence[TranslationRow] = ()) -> None:
        """Denetim durduruldu: önceki bulgular (varsa) ya da boş durum geri gelir.

        `changed`: denetim öncesinden beri çevirisi değişmiş satırlar (`changed_rows`); bulguları yanlış olduğundan
        (yok sayılanlar dahil) panodan çıkarılır ve özet kaç satırın denetlenmediğini söyler.
        """
        if not self._checking:
            return
        self._set_checking(False)
        if changed:
            self.replace_rows_issues({}, changed)
            self.summary.setText(_CHECK_STOPPED_CHANGED.format(count=format_int(len(changed))))
        else:
            self.summary.setText(_CHECK_STOPPED)
        self._update_fit_result_after_stop()
        self._refilter()

    def _set_checking(self, checking: bool) -> None:
        self._checking = checking
        self.stack.setCurrentIndex(1 if checking else 0)
        self.kind_list.set_waiting(checking)
        self._update_check_button()

    def _update_fit_result_after_stop(self) -> None:
        """Sığdırma özeti: denetim yarıda kaldı; önceki sonuç varsa o, yoksa "henüz denetlenmedi"."""
        if self._checked:
            self._update_fit_result(self.model.issues)
        else:
            self._show_fit_result(_FIT_RESULT_EMPTY)

    def _check_clicked(self) -> None:
        if self._checking:
            self.stop_checks.emit()
        else:
            self._commit_pending(self.run_checks.emit)

    def show_check_failed(self, text: str) -> None:
        """Denetim çalışmadı: Sorunlar sekmesinde hata, Sığdırma sekmesinde "yenilenemedi" gösterilir."""
        self._set_checking(False)
        self.show_fix_result("danger", text)
        self._show_fit_result(_FIT_RESULT_FAILED)
        self._refilter()

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
        self.kind_list.select_kinds(_OVERFLOW_KINDS)
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
        self._width_default = config.width_default
        self._width_files = dict(config.width_files)
        self._width_groups = dict(config.width_groups)
        self._width_keys = dict(config.width_keys)
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
            width_default=self._width_default,
            width_files=dict(self._width_files),
            width_groups=dict(self._width_groups),
            width_keys=dict(self._width_keys),
        )

    def set_width_font(self, table: WidthTable) -> None:
        """Genişlik ölçümünde kullanılan tablonun adı (oyunun fontu ya da yaklaşık tablo)."""
        text = _WIDTH_FONT_APPROX if table.approximate else f"Ölçüm: {table.name} (oyunun fontu)"
        self.fit_width_font.setText(text)

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
        self._show_width()
        self._pending = False
        self.fit_learn_note.setText("")
        self._update_fit_enabled()

    def _own_width(self, scope: str) -> tuple[dict[str, WidthRules], str] | None:
        """Kapsamın kendi genişlik ayarı sözlüğü ve anahtarı (proje ayarı `_width_default`'tadır)."""
        if scope.startswith(GROUP_PREFIX):
            return self._width_groups, scope[len(GROUP_PREFIX) :]
        if scope and scope != EACH_GROUP:
            return self._width_files, scope
        return None

    def _scope_width(self, scope: str) -> WidthRules | None:
        """Kapsamda geçerli genişlik ayarı: kendi girdisi, yoksa proje ayarı."""
        own = self._own_width(scope)
        if own is not None and own[1] in own[0]:
            return own[0][own[1]]
        return self._width_default

    def _show_width(self) -> None:
        """Seçili kapsamın genişlik ayarını denetimlere yazar (kayıt yapılmaz)."""
        rules = self._scope_width(self._scope()) or WidthRules(enabled=False)
        with _Blocked(self.fit_width_check, self.fit_width_tolerance, self.fit_width_box):
            self.fit_width_check.setChecked(rules.enabled)
            self.fit_width_tolerance.setValue(round(rules.tolerance * 100))
            self.fit_width_box.setCurrentIndex(max(self.fit_width_box.findData(rules.box), 0))

    def _width_changed(self) -> None:
        """Genişlik denetimlerini seçili kapsamın ayarı yapar. Açmak sığdırmayı da açar ama karakter sınırı eklemez."""
        scope = self._scope()
        if scope == EACH_GROUP:
            return
        rules = WidthRules(
            self.fit_width_check.isChecked(),
            self.fit_width_tolerance.value() / 100,
            str(self.fit_width_box.currentData() or BOX_GROUP),
        )
        own = self._own_width(scope)
        if own is None:
            self._width_default = rules
        else:
            own[0][own[1]] = rules
        if rules.enabled and not self.fit_enabled.isChecked():
            with _Blocked(self.fit_enabled):
                self.fit_enabled.setChecked(True)
            self._enabled = True
        self._update_fit_enabled()
        self.fit_changed.emit()

    def _has_rules(self) -> bool:
        """Kaydedilmiş bir sınır ya da açık genişlik denetimi var mı (yalnızca genişlik de sığdırmayı açık tutar)."""
        widths = [self._width_default, *self._width_files.values(), *self._width_groups.values()]
        widths += self._width_keys.values()
        return (
            self._default is not None
            or bool(self._per_file)
            or bool(self._per_group)
            or bool(self._per_key)
            or any(w is not None and w.enabled for w in widths)
        )

    def _update_fit_enabled(self) -> None:
        on = self.fit_enabled.isChecked()
        self.fit_note.setText(_FIT_KEPT_TEXT if self._has_rules() else _FIT_OFF_TEXT)
        self.fit_note.setVisible(not on)
        self.fit_result.setVisible(on)
        scope = self._scope()
        inherit = scope == EACH_GROUP or (self._own_rules(scope) is not None and self.fit_inherit.isChecked())
        for widget in (
            self.fit_inherit,
            self.fit_learn,
            self.fit_kinds,
        ):
            widget.setEnabled(on)
        for spin in (self.fit_width, self.fit_lines):
            spin.setEnabled(on and not inherit)
        # Kapsam ve genişlik denetimi sığdırma kapalıyken de seçilebilir: yalnızca genişlik denetimi isteyen kullanıcı
        # karakter sınırı girmek zorunda kalmaz. "Her grup ayrı"nın tek bir genişlik ayarı yoktur.
        width_on = scope != EACH_GROUP
        self.fit_width_check.setEnabled(width_on)
        self.fit_width_tolerance.setEnabled(width_on and self.fit_width_check.isChecked())
        self.fit_width_box.setEnabled(width_on and self.fit_width_check.isChecked())

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

    def show_font_report(
        self, report: FontReport | None, missing: str, plugin_notes: Sequence[tuple[str, str]] = ()
    ) -> None:
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
        if not report.fonts and plugin_notes:
            ad, cumle = plugin_notes[0]
            self.font_banner.show_message(
                "success",
                f"Bu oyunun fontları “{ad}” eklentisinde: {cumle} Eklenen harfler dışa aktarmada bilgi dosyasında "
                "listelenir.",
            )
        elif not report.fonts:
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
                # Kırpılan metin ipucunda tam görünür: dosya sütununda tam yol, öneri sütununda öneri ve not.
                item.setToolTip(f.source if col == 4 else "\n".join(p for p in (value, f.note) if p))
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
        # Seçili font düzenlenemiyorsa (paket içi, Switch sistem fontu…) düğmeler nedenini söyler.
        locked = source is not None and not editable
        self.font_export_button.setToolTip(_FONT_LOCKED_TIP if locked else _FONT_EXPORT_TIP)
        self.font_import_button.setToolTip(_FONT_LOCKED_TIP if locked else _FONT_IMPORT_TIP)

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

    def show_issues(self, issues: list[QaIssue], rows: list[TranslationRow], ignored: Sequence[QaIssue] = ()) -> None:
        """Denetim sonucunu gösterir; `ignored`: kullanıcının yok saydığı bulgular (listede ve sayaçta yer almaz)."""
        self._rows = {r.id: r for r in rows}
        self._ignored = list(ignored)
        self._normal = list(issues)
        self.model.set_issues(self._ignored if self._ignored_view else self._normal, self._rows)
        self._set_checking(False)
        self._issues_changed()

    def active_issues(self) -> list[QaIssue]:
        """Listede, sayaçta ve düzeltmede sayılan bulgular (yok sayılanlar değil)."""
        return self._normal if self._ignored_view else self.model.issues

    def all_issues(self) -> list[QaIssue]:
        """Yok sayılanlar dahil bütün bulgular."""
        return [*self.active_issues(), *self._ignored]

    def _set_ignored_view(self, show: bool) -> None:
        """Tabloyu yok sayılan bulgulara ya da gerçek bulgulara çevirir."""
        if show == self._ignored_view:
            return
        if show:
            self._normal = list(self.model.issues)
        self._ignored_view = show
        self.model.set_issues(self._ignored if show else self._normal, self._rows)

    def set_code_kinds(self, kinds: CodeKinds) -> None:
        """Proje kod türü eşlemesi: bulgu satırlarındaki kod çiplerinin simgesi ve rengi."""
        self.table.row_delegate.set_kinds(kinds)
        self.table.viewport().update()

    def reset(self) -> None:
        """Denetim sonuçlarını siler (başka proje açıldı): liste, özet, tür listesi ve düzeltme sayıları boşalır."""
        self._ignored, self._normal, self._rows, self._ignored_view = [], [], {}, False
        self.model.set_issues([])
        self.kind_list.set_counts({}, {}, 0)
        self._checked = False
        self._set_checking(False)
        self._refilter()
        self.summary.setText("Henüz denetlenmedi.")
        self.summary_icon.hide()
        self.last_fix_text = ""
        self._update_check_button()
        self._show_fit_result(_FIT_RESULT_EMPTY)

    def replace_row_issues(self, row_id: int, issues: list[QaIssue], row: TranslationRow) -> None:
        """Tek satırın bulgularını yenisiyle değiştirir (yerinde düzenleme sonrası); bulgu kalmadıysa satır düşer.

        Seçim ve kaydırma konumu korunur; tür listesi, düzeltme sayıları ve özet güncellenir.
        """
        self.replace_rows_issues({row_id: issues}, [row])

    def replace_rows_issues(
        self,
        issues_by_row: dict[int, list[QaIssue]],
        rows: Sequence[TranslationRow],
        ignored_by_row: Mapping[int, list[QaIssue]] | None = None,
    ) -> None:
        """Birkaç satırın bulgularını tek seferde yenisiyle değiştirir (düzenlenen satır ve eşdeşleri).

        Özet, tür listesi ve düzeltme sayıları yalnızca bir kez hesaplanır; seçim ve kaydırma konumu korunur.
        `ignored_by_row`: aynı satırların yok sayılan bulguları.
        """
        selected = set(self._selected_row_ids())
        scroll = self.table.verticalScrollBar().value()
        ids = {r.id for r in rows}
        ignored = ignored_by_row or {}
        self._ignored = [i for i in self._ignored if i.row_id not in ids] + [
            i for r in rows for i in ignored.get(r.id, [])
        ]
        for row in rows:
            self._rows[row.id] = row
        if self._ignored_view:
            self._normal = [i for i in self._normal if i.row_id not in ids] + [
                i for r in rows for i in issues_by_row.get(r.id, [])
            ]
            self.model.set_issues(self._ignored, self._rows)
        else:
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
        """Bulgu listesi değişti: özet, tür listesi ve düzeltme sayıları yeniden hesaplanır."""
        self._plan_cache = None  # bulgular ya da satır metinleri değişti: bildirim planı eskidi
        issues = self.active_issues()
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
        self.kind_list.set_counts(
            counts,
            severities,
            sum(1 for i in issues if i.severity != SEVERITY_INFO),
            len(self._ignored),
            sum(1 for i in issues if i.severity == SEVERITY_INFO),
        )
        self._refilter()
        self._update_check_button()

    def _refilter(self) -> None:
        kinds = self.kind_list.selected_kinds()
        self._set_ignored_view(IGNORED_KIND in kinds)
        self.proxy.update(frozenset() if self._ignored_view else kinds, show_info=False)
        if not self._checked:
            self.table.empty_text = _EMPTY_UNCHECKED
        else:
            self.table.empty_text = _EMPTY_FILTERED if self.active_issues() else _EMPTY_CLEAN
        self.table.viewport().update()
        self._update_fix_bar()

    def _update_check_button(self) -> None:
        """Denetim yapılmadıysa dolu "Denetle" (tek ana eylem); yapıldıysa ikincil "Yeniden Denetle"; sürerken
        ikincil "Durdur"."""
        done = self._checked or self._checking
        self.check_button.setText("Durdur" if self._checking else "Yeniden Denetle" if done else "Denetle")
        bind_icon(self.check_button, "x" if self._checking else "shield-check")
        self.check_button.setProperty("kind", None if done else "primary")
        style = self.check_button.style()
        style.unpolish(self.check_button)
        style.polish(self.check_button)

    # --- düzeltmeler --------------------------------------------------------------------

    def _build_fix_bar(self) -> QWidget:
        """Bulgu listesinin üstündeki düzeltme çubuğu: kapsamdaki bulgulardan kendiliğinden düzeltilebilenler."""
        self.fix_bar = QFrame()
        self.fix_bar.setObjectName("fixBar")
        row = QHBoxLayout(self.fix_bar)
        row.setContentsMargins(14, 8, 8, 8)
        row.setSpacing(8)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.fix_text = label("")
        self.fix_warning = label(_FIX_WARNING, "muted")
        texts.addWidget(self.fix_text)
        texts.addWidget(self.fix_warning)
        row.addLayout(texts, 1)
        self.fix_button = button("Düzelt", "primary", icon="refresh-cw")
        self.fix_button.clicked.connect(lambda: self._commit_pending(self._request_fix))
        row.addWidget(self.fix_button)
        self._fix_scope: list[QaIssue] = []
        self._plan_cache = None
        self._update_fix_bar()
        return self.fix_bar

    def _request_fix(self) -> None:
        kinds, row_ids = self._fix_plan()
        if self._confirm_risky(kinds, row_ids):
            self.fix_requested.emit(kinds, row_ids)

    def _confirm_risky(self, kinds: list[str], row_ids: list[int]) -> bool:
        """Riskli türleri birden çok satırda (ya da türün bütün bulgularında) düzeltmeden önce kısa onay ister.

        Tek satırın düzeltmesi sorulmaz: satırı seçmek zaten açık onaydır. Geri Al işi bütünüyle geri alır.
        """
        risky = [k for k in kinds if k in RISKY_FIX_KINDS]
        if not risky or len(row_ids) == 1:
            return True
        names = ", ".join(KIND_LABELS[k] for k in risky)
        where = f"{format_int(len(row_ids))} satırda" if row_ids else "bu türün bütün bulgularında"
        return ask_risky_fix(
            self,
            f"{names} düzeltmesi metni yeniden biçimler ve yanılabilir; {where} uygulanacak.\n\n"
            "Sonucu “Raporu Gör” ile gözden geçirebilir, Geri Al ile bütünüyle geri alabilirsiniz. Sürdürülsün mü?",
        )

    def _fix_plan(self) -> tuple[list[str], list[int]]:
        """Düğmenin uygulayacağı türler (liste sırasıyla) ve satır kimlikleri."""
        present = {i.kind for i in self._fix_scope}
        return [k for k in FIX_KINDS if k in present], sorted({i.row_id for i in self._fix_scope})

    def _visible_issues(self) -> list[QaIssue]:
        issues = self.model.issues
        return [issues[self.proxy.mapToSource(self.proxy.index(r, 0)).row()] for r in range(self.proxy.rowCount())]

    def visible_findings(self) -> list[QaIssue]:
        """Tabloda şu an görünen bulgular (süzgeçlere uyanlar, tablodaki sırayla); yok sayılanlar girmez."""
        return [] if self._ignored_view else self._visible_issues()

    def selected_findings(self) -> list[QaIssue]:
        """Tabloda seçili bulgular; yok sayılanlar girmez."""
        return [] if self._ignored_view else self._selected_issues()

    def _compute_scope(self) -> tuple[list[QaIssue], bool]:
        """Düzeltmenin kapsamı ve seçili satırlardan gelip gelmediği.

        Seçili satırlarda düzeltilebilir bulgu varsa hepsi (riskliler dahil; birden çok satırsa Düzelt onay sorar);
        yoksa solda tür seçiliyse görünen düzeltilebilir bulguların hepsi; "Tüm bulgular"da yalnızca riskli olmayan
        türler.
        """
        if self._ignored_view:
            return [], False
        selected = [i for i in self._selected_issues() if i.kind in FIX_KINDS]
        if selected:
            return selected, True
        fixable = [i for i in self._visible_issues() if i.kind in FIX_KINDS]
        if self.kind_list.selected_kinds():
            return fixable, False
        return [i for i in fixable if i.kind not in RISKY_FIX_KINDS], False

    def _scope_plan(self, scope: list[QaIssue]) -> FixPlan | None:
        """Kapsamın gerçek düzeltme planı (Düzelt'in uygulayacağıyla aynı kural); hesaplanamazsa None.

        Planlayıcı verilmemişse ya da kapsam çok genişse (her seçim değişiminde bekletmemek için) hesaplanmaz.
        Plan, kapsamdaki satırların panodaki tüm bulgularından çıkarılır: Düzelt de aynı satırları aynı türlerle işler.
        """
        planner = self.fix_planner
        row_ids = {i.row_id for i in scope}
        if planner is None or len(row_ids) > _FIX_PLAN_ROWS:
            return None
        kinds = [k for k in FIX_KINDS if any(i.kind == k for i in scope)]
        key = (tuple(kinds), tuple(sorted(row_ids)))
        if self._plan_cache is not None and self._plan_cache[0] == key:
            return self._plan_cache[1]
        rows = [self._rows[r] for r in sorted(row_ids) if r in self._rows]
        plan = planner(rows, [i for i in self.active_issues() if i.row_id in row_ids], kinds)
        self._plan_cache = (key, plan)
        return plan

    def _update_fix_bar(self) -> None:
        """Çubuğun yazısını, düğmesini ve görünürlüğünü tazeler; kapsam boşsa çubuk gizlenir.

        Sayı, Düzelt'in gerçekten değiştireceği satır sayısıdır (aynı plandan); düzeltilemeyenler de söylenir.
        """
        scope, from_selection = self._compute_scope()
        self._fix_scope = scope
        self.fix_bar.setVisible(bool(scope) and not self._checking)
        if not scope:
            return
        tips = {i.kind for i in scope}
        explicit = from_selection or bool(self.kind_list.selected_kinds())
        plan = self._scope_plan(scope)
        prefix = "Seçili " if from_selection else ""
        can_fix = True
        if (
            plan is None and self.fix_planner is None
        ):  # planlayıcı yok (sayfa tek başına): yalnızca bulgu sayısı bilinir
            n = format_int(len(scope))
            if from_selection:
                self.fix_text.setText(f"Seçili {n} bulgu kendiliğinden düzeltilebilir.")
            elif explicit:
                self.fix_text.setText(f"Bu {n} bulgu kendiliğinden düzeltilebilir.")
            else:
                self.fix_text.setText(f"{n} bulgu güvenle düzeltilebilir.")
            self.fix_button.setText(f"{prefix}{n} bulguyu düzelt")
        elif plan is None:
            n = format_int(len(scope))
            self.fix_text.setText(
                f"{prefix or 'Bu '}{n} bulgu için düzeltme denenecek; kaç satırın düzeldiği sonuçta yazılır."
            )
            self.fix_button.setText(f"{prefix}{n} bulguyu düzelt")
        elif not plan.changes:
            can_fix = False
            self.fix_text.setText(f"{prefix or 'Bu '}bulgular kendiliğinden düzeltilemiyor; elle bakın.")
        else:
            n = format_int(len(plan.changes))
            if from_selection:
                text = f"Seçili {n} satır kendiliğinden düzeltilebilir."
            elif explicit:
                text = f"Bu {n} satır kendiliğinden düzeltilebilir."
            else:
                text = f"{n} satır güvenle düzeltilebilir."
            if plan.unfixed:
                text += f" {format_int(plan.unfixed)} satır düzeltilemez; elle bakın."
            self.fix_text.setText(text)
            self.fix_button.setText(f"{prefix}{n} satırı düzelt")
        self.fix_button.setVisible(can_fix)
        self.fix_warning.setVisible(explicit and can_fix and bool(tips & RISKY_FIX_KINDS))
        self.fix_button.setToolTip(
            tip_html("\n\n".join(f"{KIND_LABELS[k]}: {FIX_TIPS[k]}" for k in FIX_KINDS if k in tips))
        )

    def show_fix_result(self, state: str, text: str, action: str = "") -> None:
        """Düzeltme/denetim sonucunu bildirim merkezine iletir (sayfada kalıcı kutu yok); `action`: düğme adı."""
        self.last_fix_text = text
        if text:
            self.fix_notice.emit(state, text, action)

    def _selected_row_ids(self) -> list[int]:
        """Bulgu listesinde seçili satırların çeviri satırı kimlikleri; seçim yoksa boş."""
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        return sorted({self.model.issues[r].row_id for r in rows})

    def _selection_changed(self) -> None:
        self._update_fix_bar()
        self.spell_add_button.setEnabled(bool(self._selected_spelling_words()))

    def _selected_issues(self) -> list[QaIssue]:
        rows = sorted({self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.issues[r] for r in rows]

    def _fix_now(self, kinds: list[str], row_ids: list[int]) -> None:
        if self._confirm_risky(kinds, row_ids):
            self._commit_pending(lambda: self.fix_requested.emit(kinds, row_ids))

    def bind_settings(self, settings: QSettings) -> None:
        """Kayıtlı sıralama düzenini geri yükler (bilinmeyen değer varsayılana düşer)."""
        self._settings = settings
        self.model.set_sort(str(settings.value(_SORT_SETTING, SORT_SEVERITY)))

    def set_sort_mode(self, mode: str) -> None:
        self.model.set_sort(mode)
        if self._settings is not None:
            self._settings.setValue(_SORT_SETTING, self.model.sort_mode)

    def context_menu(self) -> QMenu:
        """Seçili bulguya göre bağlam menüsü; her öğe kullanılabilir olduğunda görünür."""
        menu = QMenu(self)
        issues = self._selected_issues()
        if issues and self._ignored_view:
            pairs = [(i.row_id, i.kind) for i in issues]
            restore = menu.addAction(
                icon("undo-2"), "Yok saymayı kaldır" if len(issues) == 1 else "Yok saymayı kaldır (seçili bulgular)"
            )
            restore.triggered.connect(lambda: self.unignore_requested.emit(pairs))
            show = menu.addAction(icon("arrow-left-right"), "Çevir'de göster")
            show.triggered.connect(lambda: self.open_row.emit(issues[0].row_id))
            menu.addSeparator()
        elif issues:
            self._add_fix_actions(menu, issues)
            show = menu.addAction(icon("arrow-left-right"), "Çevir'de göster")
            show.triggered.connect(lambda: self.open_row.emit(issues[0].row_id))
            # Hata (oyunu bozabilecek) bulgular yok sayılamaz.
            ignorable = [(i.row_id, i.kind) for i in issues if i.severity != SEVERITY_ERROR]
            if ignorable:
                ignore = menu.addAction(icon("x"), "Bulguyu yok say" if len(issues) == 1 else "Bu bulguları yok say")
                ignore.setToolTip(
                    tip_html(
                        "Listeden çıkar; çeviri değişirse yeniden görünür. Soldaki “Yok sayılanlar”dan geri alınır."
                    )
                )
                ignore.triggered.connect(lambda: self.ignore_requested.emit(ignorable))
            menu.addSeparator()
        if issues and not self._ignored_view:
            export = menu.addAction(icon("file-up"), "Bulguları dışa aktar…")
            export.setToolTip(
                tip_html(
                    "Görünen ya da seçili bulguları satırlarıyla bir TXT/XLSX dosyasına yazar; "
                    "dış redaksiyon gibi geri yüklenir."
                )
            )
            export.triggered.connect(self.export_findings_requested)
        if self.spell_add_button.isEnabled():
            menu.addAction(self.spell_add_button)
        phrases = self._selected_term_phrases()
        if phrases:
            not_term = menu.addAction(icon("x"), "Terim değil")
            not_term.setToolTip("Seçili ifadeler bu projede terim sayılmaz; tutarsızlık aranmaz.")
            not_term.triggered.connect(lambda: self.not_term_requested.emit(phrases))
        rude = self._selected_profanity_words()
        if rude:
            not_rude = menu.addAction(icon("x"), "Bu kelime argo değil")
            not_rude.setToolTip(
                tip_html("Seçili sözcükler bu projede küfür ya da argo sayılmaz; bir daha işaretlenmez.")
            )
            not_rude.triggered.connect(lambda: self.not_profanity_requested.emit(rude))
        menu.addAction(self.user_dict_button)
        menu.addSeparator()
        sort_menu = menu.addMenu("Sırala")
        group = QActionGroup(sort_menu)
        for mode, text in SORT_LABELS.items():
            action = sort_menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(mode == self.model.sort_mode)
            group.addAction(action)
            action.triggered.connect(lambda _checked=False, m=mode: self.set_sort_mode(m))
        return menu

    def _add_fix_actions(self, menu: QMenu, issues: list[QaIssue]) -> None:
        """Düzeltme eylemleri: satır, tür ve belirsiz sözcük için aday seçenekleri.

        Plan hesaplanabiliyorsa ve hiçbir satırı düzeltmeyecekse ilgili eylem hiç çıkmaz; tür eyleminin adı türü ve
        düzeltilecek satır sayısını söyler.
        """
        present = {i.kind for i in issues}
        kinds = [k for k in FIX_KINDS if k in present]
        row_ids = sorted({i.row_id for i in issues})
        if kinds:
            row_plan = self._scope_plan([i for i in issues if i.kind in FIX_KINDS])
            if row_plan is None or row_plan.changes:
                fix_row = menu.addAction(
                    icon("refresh-cw"), "Bu satırları düzelt" if len(row_ids) > 1 else "Bu satırı düzelt"
                )
                fix_row.triggered.connect(lambda: self._fix_now(kinds, row_ids))
            kind_plan = self._kind_plan(kinds)
            if kind_plan is None or kind_plan.changes:
                title = self._kinds_title(kinds)
                if kind_plan is not None:
                    title += f" ({format_int(len(kind_plan.changes))} satır)"
                fix_kind = menu.addAction(icon("replace-all"), title)
                fix_kind.triggered.connect(lambda: self._fix_now(kinds, []))
        choices: dict[str, tuple[str, ...]] = {}
        for issue in issues:
            for key, candidates in issue.choices:
                choices.setdefault(key, candidates)
        if choices:
            choose = menu.addMenu(icon("spell-check"), "Şununla düzelt")
            choose.setToolTip(tip_html("Seçtiğiniz yazım, bu sözcüğün geçtiği projedeki bütün çevirilere uygulanır."))
            for key, candidates in choices.items():
                target = choose if len(choices) == 1 else choose.addMenu(key)
                for candidate in candidates:
                    action = target.addAction(f"{key} → {candidate}")
                    action.triggered.connect(lambda _c=False, k=key, c=candidate: self._choose(k, c))

    def _choose(self, key: str, candidate: str) -> None:
        self._commit_pending(lambda: self.ascii_choice_requested.emit(key, candidate))

    @staticmethod
    def _kinds_title(kinds: list[str]) -> str:
        """ "Tüm “Türkçe harf eksik” bulgularını düzelt"; birkaç türde türler sayılır."""
        if len(kinds) == 1:
            return f"Tüm “{KIND_LABELS[kinds[0]]}” bulgularını düzelt"
        return "Bu türlerdeki tüm bulguları düzelt"

    def _kind_plan(self, kinds: list[str]) -> FixPlan | None:
        """Türlerin bütün bulgularının planı (menüdeki satır sayısı); çok genişse ya da planlayıcı yoksa None."""
        planner = self.fix_planner
        issues = [i for i in self.active_issues() if i.kind in kinds]
        row_ids = {i.row_id for i in issues}
        if planner is None or len(row_ids) > _FIX_PLAN_ROWS:
            return None
        rows = [self._rows[r] for r in sorted(row_ids) if r in self._rows]
        return planner(rows, [i for i in self.active_issues() if i.row_id in row_ids], kinds)

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

    def _selected_profanity_words(self) -> list[str]:
        """Seçili küfür / argo bulgularındaki sözcükler (tekrarsız)."""
        words: dict[str, None] = {}
        for issue in self._selected_issues():
            if issue.kind == "profanity":
                words.update(dict.fromkeys(issue.words))
        return list(words)

    def _add_spelling(self) -> None:
        words = self._selected_spelling_words()
        if words:
            self.add_spelling_requested.emit(words)

    def _open(self, index: QModelIndex) -> None:
        issue = self.model.issues[self.proxy.mapToSource(index).row()]
        self.open_row.emit(issue.row_id)


_SEVERITY_ORDER = {"": 0, "info": 1, SEVERITY_WARNING: 2, SEVERITY_ERROR: 3}
#: Harf dönüştürme seçeneklerinin ipuçları.
_MODE_TIPS = {
    transliterate.MODE_NONE: "Fontta Türkçe harf varsa ya da font yaması yaptıysanız bunu seçin.",
    transliterate.MODE_MISSING: "Yalnızca fontta olmayan harfler benzerine çevrilir (ör. ğ→g); olanlar korunur.",
    transliterate.MODE_ALL: "Font hiçbir Türkçe harfi göstermiyorsa en güvenli seçenek.",
}


def _worse(a: str, b: str) -> str:
    return a if _SEVERITY_ORDER.get(a, 0) >= _SEVERITY_ORDER.get(b, 0) else b


class _Blocked:
    """Programla değer yazarken pencere öğelerinin ve eylemlerin sinyallerini geçici olarak susturur."""

    def __init__(self, *widgets: QObject) -> None:
        self.widgets = widgets
        self._previous: list[bool] = []

    def __enter__(self) -> None:
        self._previous = [w.blockSignals(True) for w in self.widgets]

    def __exit__(self, *_exc: object) -> None:
        for w, previous in zip(self.widgets, self._previous, strict=True):
            w.blockSignals(previous)
