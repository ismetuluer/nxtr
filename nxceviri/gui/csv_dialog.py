"""Çevirileri dış redaksiyon veya dış çeviri için XLSX (Excel) ya da TXT olarak dışa aktarma penceresi."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.csvio import (
    MODE_FINDINGS,
    MODE_REDACTION,
    MODE_TRANSLATION,
    PlannedFile,
    file_plan,
    findings_prompt_txt,
    findings_prompt_xlsx,
    group_rows,
    plan_files,
    preview_table,
    revision_prompt_txt,
    revision_prompt_xlsx,
    translation_prompt_txt,
    translation_prompt_xlsx,
    without_empty_source,
)
from nxceviri.gui.dialog_parts import SIDE_WIDTH, header_bar, named_frame, section_label
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import button, format_int, label

FORMAT_TXT = "txt"
FORMAT_XLSX = "xlsx"
#: QSettings anahtarları: dışa aktarma penceresinde son kabul edilen biçim, gruplama, parça sayısı.
CHOICE_FORMAT = "csv/format"
CHOICE_GROUP = "csv/by_group"
CHOICE_PARTS = "csv/parts"


def saved_choices(settings: QSettings) -> tuple[str, bool, int]:
    """(biçim, gruplu mu, parça sayısı; 0 = bölünmez): hiç seçilmediyse XLSX, tek dosya."""
    fmt = FORMAT_TXT if str(settings.value(CHOICE_FORMAT, FORMAT_XLSX)) == FORMAT_TXT else FORMAT_XLSX
    try:
        parts = max(int(str(settings.value(CHOICE_PARTS, 0) or 0)), 0)
    except ValueError:
        parts = 0
    return fmt, bool(settings.value(CHOICE_GROUP, "")), parts


__all__ = [
    "FORMAT_TXT",
    "FORMAT_XLSX",
    "MODE_FINDINGS",
    "MODE_REDACTION",
    "MODE_TRANSLATION",
    "CsvExportDialog",
]

#: Önizleme tablosunda gösterilen ilk satır sayısı.
PREVIEW_ROWS = 20
#: Çıkacak dosya kartlarından en çoğu; fazlası “ve K dosya daha” olarak yazılır (parça sayısı satır kadar olabilir).
MAX_CARDS = 12
#: Önizlemede bir hücrenin en çok karakteri (uzun metin tek satırda kısaltılır).
_CELL_CHARS = 160


def _one_line(text: str) -> str:
    flat = text.replace("\r", "").replace("\n", " ↵ ")
    return flat if len(flat) <= _CELL_CHARS else flat[: _CELL_CHARS - 1] + "…"


class CsvExportDialog(QDialog):
    """Hangi biçimde, hangi satırların, kaç parçada yazılacağını seçtirir; çıkacak dosyaları ve ilk satırlarını
    göstererek dış model için hazır istemi sunar.

    `accepted` ile kapanırsa `format()`, `rows()`, `by_group()` ve `parts()` kullanılır; dosya adını çağıran sorar.
    `mode=MODE_TRANSLATION` ise sütunlar ve hazır istem dış çeviri içindir; `mode=MODE_FINDINGS` ise Kontrol Et
    bulgularının dosyasıdır (`bulgu` sütunu eklenir; kapsam yalnızca seçili ya da görünen bulgular). `notes`:
    bulgu kipinde satır kimliği → bulgu metni (yalnızca önizleme için; dosyayı çağıran yazar). `name_hint`: kaydet
    penceresinin önereceği dosya adı gövdesi (kartlarda gösterilir). Kaynağı boş satırlar hiçbir kapsamda yazılmaz.
    """

    def __init__(
        self,
        parent: QWidget | None,
        *,
        selected: Sequence[TranslationRow],
        visible: Sequence[TranslationRow],
        all_rows: Sequence[TranslationRow],
        instruction: str = "",
        mode: str = MODE_REDACTION,
        notes: Mapping[int, str] | None = None,
        name_hint: str = "",
        settings: QSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._name_hint = name_hint
        self._instruction = instruction
        self._mode = mode
        self._notes = notes or {}
        self._translation = mode == MODE_TRANSLATION
        self._findings = mode == MODE_FINDINGS
        if self._translation:
            self.setWindowTitle("Dış çeviri dosyası oluştur")
            heading = "Dış çeviri"
            description = "Sonucu Dış Çeviri → İçe Aktar ile yükleyin."
            column_word = "yeni çeviri"
        elif self._findings:
            self.setWindowTitle("Kontrol bulgularını dışa aktar")
            heading = "Bulguları dışa aktar"
            description = "Sonucu Dış Redaksiyon → İçe Aktar ile yükleyin."
            column_word = "düzeltme"
        else:
            self.setWindowTitle("Dış redaksiyon dosyası oluştur")
            heading = "Dış redaksiyon"
            description = "Sonucu Dış Redaksiyon → İçe Aktar ile yükleyin."
            column_word = "düzeltme"
        self.resize(1100, 720)
        self.setMinimumSize(720, 520)
        self._groups_cache: dict[int, dict[str, list[TranslationRow]]] = {}
        self._planned: list[PlannedFile] = []
        self.cards: list[QToolButton] = []
        self._selected_card = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header, _ = header_bar(heading, description)
        root.addWidget(header)
        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._build_side(column_word, selected, visible, all_rows))
        body.addWidget(self._build_main(), 1)
        root.addLayout(body, 1)
        root.addWidget(self._build_footer())

        self.scope_group.idClicked.connect(lambda _id: self._scope_changed())
        self.group_box.toggled.connect(lambda _on: self._update_split())
        self.split_box.toggled.connect(lambda _on: self._update_split())
        self.part_spin.valueChanged.connect(lambda _v: self._update_split())
        self.format_group.buttonToggled.connect(lambda *_: self._format_changed())
        self._update_group_box()
        self._restore_choices()
        self._update_split()
        self._update_prompt()

    # --- yapı -----------------------------------------------------------------------------------------------
    def _tile(self, text: str, tip: str) -> QRadioButton:
        radio = QRadioButton(text)
        radio.setProperty("role", "tile")
        radio.setToolTip(tip)
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        return radio

    def _build_side(
        self,
        column_word: str,
        selected: Sequence[TranslationRow],
        visible: Sequence[TranslationRow],
        all_rows: Sequence[TranslationRow],
    ) -> QFrame:
        side = named_frame("sidePanel")
        side.setFixedWidth(SIDE_WIDTH + 60)
        outer = QVBoxLayout(side)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(24, 20, 24, 16)
        col.setSpacing(8)

        columns, extra = ("beş sütun", ", bulgu") if self._findings else ("dört sütun", "")
        col.addWidget(section_label("BİÇİM"))
        self.format_group = QButtonGroup(self)
        self.txt_radio = self._tile(
            "Metin (TXT)",
            f"Sütunlar ({columns}): orijinal, çeviri, {column_word}, grup{extra}. Model yalnızca “{column_word}” "
            "sütununu doldurur; boş bıraktığı satır değişmez. “grup” sütunu bağlam verir, salt okunurdur. "
            "Kontrol kodları en az bozulur.",
        )
        self.xlsx_radio = self._tile(
            "Excel (XLSX)",
            f"Excel'de açılır. Sütunlar ({columns}): orijinal, çeviri, {column_word}, grup{extra}. "
            f"{column_word.capitalize()} hücreleri boş bırakılabilir; “grup” sütunu bağlam verir, değiştirilmez. "
            "Çok kontrol kodu olan metinde TXT daha güvenlidir.",
        )
        self.format_group.addButton(self.txt_radio, 0)
        self.format_group.addButton(self.xlsx_radio, 1)
        self.xlsx_radio.setChecked(True)
        tiles = QHBoxLayout()
        tiles.setSpacing(8)
        tiles.addWidget(self.xlsx_radio)
        tiles.addWidget(self.txt_radio)
        col.addLayout(tiles)
        col.addSpacing(8)

        col.addWidget(section_label("SATIRLAR"))
        self._scopes: list[Sequence[TranslationRow]] = []
        self._skipped: list[int] = []
        self.scope_group = QButtonGroup(self)
        choices = (
            (("Seçili bulguların satırları", selected), ("Görünen bulguların satırları", visible))
            if self._findings
            else (
                ("Seçili satırlar", selected),
                ("Tabloda görünenler", visible),
                ("Tüm satırlar", all_rows),
            )
        )
        for text, raw in choices:
            rows = without_empty_source(raw)
            self._skipped.append(len(raw) - len(rows))
            radio = QRadioButton(f"{text} ({format_int(len(rows))})")
            if text == "Tabloda görünenler":
                radio.setToolTip("Çeviri tablosunda şu an görünen satırlar: arama ve süzgeçlere uyanlar.")
            radio.setEnabled(bool(rows))
            self.scope_group.addButton(radio, len(self._scopes))
            self._scopes.append(rows)
            col.addWidget(radio)
        # Varsayılan kapsam her zaman her şeyi kapsayan seçenektir (bulgularda: görünen bulguların satırları).
        default_button = self.scope_group.button(1 if self._findings else 2)
        assert default_button is not None
        default_button.setChecked(True)
        col.addSpacing(8)

        col.addWidget(section_label("DOSYALAR"))
        self.group_box = QCheckBox()
        self.group_box.setToolTip(
            "Her grup (ör. Unity'de “Dialogue”, “UI” tabloları; diğer oyunlarda dosya) ayrı bir dosyaya "
            "yazılır: ad_Dialogue, ad_UI … Böylece metinleri konu konu "
            + ("çevirtebilirsiniz." if self._translation else "redakte ettirebilirsiniz.")
        )
        col.addWidget(self.group_box)
        split_row = QHBoxLayout()
        self.split_box = QCheckBox("Parçalara böl:")
        self.split_box.setToolTip(
            "Ücretsiz sohbet modelleri uzun dosyaları yarıda keser; parçalar ayrı ayrı verilip geri yüklenebilir "
            "(içe aktarırken birden çok dosya seçilebilir). Satırlar parçalara eşit dağıtılır."
        )
        self.part_spin = QSpinBox()
        self.part_spin.setMinimum(2)
        self.part_spin.setSuffix(" parça")
        self.part_spin.setEnabled(False)
        split_row.addWidget(self.split_box)
        split_row.addWidget(self.part_spin)
        split_row.addStretch(1)
        col.addLayout(split_row)
        col.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        box = QFrame()
        box.setObjectName("summaryBox")
        box_row = QHBoxLayout(box)
        box_row.setContentsMargins(16, 12, 16, 12)
        self.split_label = label("", wrap=True)
        font = self.split_label.font()
        font.setBold(True)
        self.split_label.setFont(font)
        box_col = QVBoxLayout()
        box_col.addWidget(self.split_label)
        self.skipped_label = label("", "muted", wrap=True)
        box_col.addWidget(self.skipped_label)
        box_row.addLayout(box_col)
        wrap = QVBoxLayout()
        wrap.setContentsMargins(24, 8, 24, 20)
        wrap.addWidget(box)
        outer.addLayout(wrap)
        return side

    def _build_main(self) -> QFrame:
        main = named_frame("mainPanel")
        col = QVBoxLayout(main)
        col.setContentsMargins(24, 20, 24, 16)
        col.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(label("Çıkacak dosyalar", "cardTitle"))
        head.addStretch(1)
        head.addWidget(label("ayarı değiştirdikçe güncellenir", "muted"))
        col.addLayout(head)

        self._card_scroll = QScrollArea()
        self._card_scroll.setObjectName("cardStrip")
        self._card_scroll.setWidgetResizable(True)
        self._card_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._card_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._card_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        strip = QWidget()
        self._card_row = QHBoxLayout(strip)
        self._card_row.setContentsMargins(0, 0, 0, 0)
        self._card_row.setSpacing(8)
        self._card_scroll.setWidget(strip)
        self._card_scroll.setFixedHeight(self.fontMetrics().height() * 2 + 56)
        col.addWidget(self._card_scroll)
        self._cards_group = QButtonGroup(self)
        self.more_label = label("", "muted")
        self._card_row.addWidget(self.more_label)
        self._card_row.addStretch(1)

        self.preview_table = QTableWidget()
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.preview_table.setWordWrap(False)
        self.preview_table.verticalHeader().hide()
        self.preview_table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        col.addWidget(self.preview_table, 1)
        self.preview_more = label("", "muted")
        col.addWidget(self.preview_more)

        self.prompt_toggle = QToolButton()
        self.prompt_toggle.setProperty("role", "link")
        self.prompt_toggle.setCheckable(True)
        self.prompt_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prompt_toggle.setText("▸ Model için hazır talimat")
        self.prompt_toggle.toggled.connect(self._prompt_toggled)
        col.addWidget(self.prompt_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self.prompt = QPlainTextEdit()
        self.prompt.setReadOnly(True)
        self.prompt.setMinimumHeight(90)
        self.prompt.setMaximumHeight(150)
        self.prompt.hide()
        col.addWidget(self.prompt)
        return main

    def _build_footer(self) -> QFrame:
        footer = named_frame("dialogFooter")
        row = QHBoxLayout(footer)
        row.setContentsMargins(24, 12, 24, 12)
        row.setSpacing(12)
        self.copy_button = button("Talimatı Kopyala")
        self.copy_button.clicked.connect(self.copy_prompt)
        row.addWidget(self.copy_button)
        row.addStretch(1)
        cancel = button("Vazgeç", icon="x")
        cancel.clicked.connect(self.reject)
        self.save_button = button("Kaydet…", "primary")
        self.save_button.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self.save_button)
        return footer

    # --- seçimler -------------------------------------------------------------------------------------------
    def format(self) -> str:
        """Seçilen dosya biçimi: `FORMAT_XLSX` (varsayılan) veya `FORMAT_TXT`."""
        return FORMAT_TXT if self.format_group.checkedId() == 0 else FORMAT_XLSX

    def rows(self) -> Sequence[TranslationRow]:
        return self._scopes[max(self.scope_group.checkedId(), 0)]

    def by_group(self) -> bool:
        return self.group_box.isChecked()

    def parts(self) -> int:
        """Her kümenin kaç parçaya bölüneceği; bölünmeyecekse 0."""
        return self.part_spin.value() if self.split_box.isChecked() else 0

    def _groups(self) -> dict[str, list[TranslationRow]]:
        """Geçerli kapsamın grupları (kapsam başına bir kez hesaplanır; her ayar değişiminde yinelenmez)."""
        scope = max(self.scope_group.checkedId(), 0)
        if scope not in self._groups_cache:
            self._groups_cache[scope] = group_rows(self.rows())
        return self._groups_cache[scope]

    # --- güncelleme -----------------------------------------------------------------------------------------
    def _restore_choices(self) -> None:
        """Son kabul edilen biçim, gruplama ve parça sayısı (tek tıkla dışa aktarma da bunları kullanır)."""
        if self._settings is None:
            return
        fmt, by_group, parts = saved_choices(self._settings)
        (self.txt_radio if fmt == FORMAT_TXT else self.xlsx_radio).setChecked(True)
        if self.group_box.isEnabled():
            self.group_box.setChecked(by_group)
        self._update_split()
        if parts and self.split_box.isEnabled():
            self.split_box.setChecked(True)
            self.part_spin.setValue(parts)

    def save_choices(self) -> None:
        """Kabul edilen biçim, gruplama ve parça sayısını sonraki tek tıklar için saklar (pencereyi açan çağırır)."""
        if self._settings is not None:
            self._settings.setValue(CHOICE_FORMAT, self.format())
            self._settings.setValue(CHOICE_GROUP, "1" if self.by_group() else "")
            self._settings.setValue(CHOICE_PARTS, self.parts())

    def _update_group_box(self) -> None:
        count = len(self._groups())
        self.group_box.setText(f"Her grup ayrı dosyaya ({format_int(count)} grup)")
        self.group_box.setEnabled(count > 1)
        if count <= 1:
            self.group_box.setChecked(False)

    def _scope_changed(self) -> None:
        self._update_group_box()
        self._update_split()

    def _sizes(self) -> list[int]:
        """Dosya kümelerinin satır sayıları: gruplama açıksa grup başına, değilse tek küme."""
        return [len(g) for g in self._groups().values()] if self.by_group() else [len(self.rows())]

    def _update_split(self) -> None:
        sizes = self._sizes()
        biggest = max(sizes, default=0)
        self.split_box.setEnabled(biggest >= 2)
        if biggest < 2:
            self.split_box.setChecked(False)
        self.part_spin.setMaximum(max(biggest, 2))
        self.part_spin.setEnabled(self.split_box.isChecked())
        plan = file_plan(sizes, self.parts(), by_group=True)
        if self.parts() == 0:
            text = (
                f"{format_int(plan.groups)} grup = {format_int(plan.files)} dosya"
                if self.by_group()
                else f"1 dosya, {format_int(sum(sizes))} satır"
            )
        elif self.by_group() and len(set(plan.per_group)) == 1:
            text = (
                f"{format_int(plan.groups)} grup × {format_int(plan.per_group[0])} parça = "
                f"{format_int(plan.files)} dosya"
            )
        elif self.by_group():
            text = (
                f"{format_int(plan.groups)} grup, toplam {format_int(plan.files)} dosya "
                f"(her biri en çok {format_int(plan.max_rows)} satır)"
            )
        else:
            text = f"{format_int(plan.files)} dosya, her biri en çok {format_int(plan.max_rows)} satır"
        self.split_label.setText(text)
        skipped = self._skipped[max(self.scope_group.checkedId(), 0)]
        self.skipped_label.setText(f"{format_int(skipped)} boş satır atlandı")
        self.skipped_label.setVisible(skipped > 0)
        self._planned = plan_files(
            self.rows(),
            by_group=self.by_group(),
            parts=self.parts(),
            groups=self._groups() if self.by_group() else None,
        )
        self._selected_card = 0
        self._show_cards()
        self._show_preview()
        n = len(self._planned)
        self.save_button.setText("Kaydet…" if n == 1 else f"{format_int(n)} dosyayı kaydet…")

    def _format_changed(self) -> None:
        self._update_prompt()
        self._show_cards()

    def _update_prompt(self) -> None:
        if self._translation:
            prompt = translation_prompt_txt if self.format() == FORMAT_TXT else translation_prompt_xlsx
        elif self._findings:
            prompt = findings_prompt_txt if self.format() == FORMAT_TXT else findings_prompt_xlsx
        else:
            prompt = revision_prompt_txt if self.format() == FORMAT_TXT else revision_prompt_xlsx
        self.prompt.setPlainText(prompt(self._instruction))

    def _prompt_toggled(self, on: bool) -> None:
        self.prompt_toggle.setText(("▾" if on else "▸") + " Model için hazır talimat")
        self.prompt.setVisible(on)

    def _file_name(self, planned: PlannedFile) -> str:
        """Kaydedilecek adın şablonu: adın kendisini çağıran sorar, burada “…” ile gösterilir."""
        ext = ".txt" if self.format() == FORMAT_TXT else ".xlsx"
        if self._name_hint:
            return f"{self._name_hint}{planned.suffix}{ext}"
        return f"ad{ext}" if not planned.suffix else f"…{planned.suffix}{ext}"

    def _show_cards(self) -> None:
        for card in self.cards:
            self._cards_group.removeButton(card)
            self._card_row.removeWidget(card)
            card.setParent(None)  # hemen çocuk listesinden çıkar; silme olay döngüsünde olur
            card.deleteLater()
        self.cards = []
        shown = self._planned[:MAX_CARDS]
        for n, planned in enumerate(shown):
            card = QToolButton()
            card.setProperty("role", "fileCard")
            card.setCheckable(True)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            card.setText(f"{self._file_name(planned)}\n{format_int(len(planned.rows))} satır")
            card.setToolTip("Önizlemede bu dosyanın ilk satırlarını göster.")
            card.setChecked(n == self._selected_card)
            card.clicked.connect(lambda _c=False, i=n: self._select_card(i))
            self._cards_group.addButton(card)
            self._card_row.insertWidget(n, card)
            self.cards.append(card)
        extra = len(self._planned) - len(shown)
        self.more_label.setText(f"ve {format_int(extra)} dosya daha")
        self.more_label.setVisible(extra > 0)

    def _select_card(self, index: int) -> None:
        self._selected_card = index
        for n, card in enumerate(self.cards):
            card.setChecked(n == index)
        self._show_preview()

    def _show_preview(self) -> None:
        """Seçili dosyanın ilk satırları: yazıcının yazacağı sütunlar; yalnızca gösterilenler hazırlanır."""
        table = self.preview_table
        planned = self._planned[self._selected_card] if self._planned else None
        rows = planned.rows if planned is not None else []
        header, body = preview_table(rows, mode=self._mode, notes=self._notes, limit=PREVIEW_ROWS)
        table.clear()
        table.setColumnCount(len(header))
        table.setRowCount(len(body))
        table.setHorizontalHeaderLabels(list(header))
        accent = QColor(current_tokens()["warning"])
        accent.setAlpha(38)  # hafif vurgu: açık, koyu ve palet temalarında metin okunur kalır
        tint = QBrush(accent)
        bold = QFont(table.font())
        bold.setBold(True)
        fill_col = 2  # model yalnızca “düzeltme” / “yeni çeviri” sütununu doldurur
        for c in range(len(header)):
            head_item = table.horizontalHeaderItem(c)
            if head_item is not None and c == fill_col:
                head_item.setFont(bold)
        for r, cells in enumerate(body):
            for c, text in enumerate(cells):
                item = QTableWidgetItem(_one_line(text))
                item.setToolTip(text)
                if c == fill_col:
                    item.setBackground(tint)
                table.setItem(r, c, item)
        more = len(rows) - len(body)
        self.preview_more.setText(f"… ve {format_int(more)} satır daha")
        self.preview_more.setVisible(more > 0)

    def copy_prompt(self) -> None:
        QGuiApplication.clipboard().setText(self.prompt.toPlainText())
        self.copy_button.setText("Kopyalandı ✓")
