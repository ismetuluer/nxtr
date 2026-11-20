"""Çevirileri dış redaksiyon veya dış çeviri için XLSX (Excel) ya da TXT olarak dışa aktarma penceresi."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.csvio import (
    file_plan,
    findings_prompt_txt,
    findings_prompt_xlsx,
    group_rows,
    revision_prompt_txt,
    revision_prompt_xlsx,
    translation_prompt_txt,
    translation_prompt_xlsx,
)
from nxceviri.gui.widgets import button, format_int, label, title_row

FORMAT_TXT = "txt"
FORMAT_XLSX = "xlsx"
MODE_REDACTION = "redaction"
MODE_TRANSLATION = "translation"
MODE_FINDINGS = "findings"


class CsvExportDialog(QDialog):
    """Hangi biçimde, hangi satırların, kaç parçada yazılacağını seçtirir ve dış model için hazır istemi gösterir.

    `accepted` ile kapanırsa `format()`, `rows()`, `by_group()` ve `parts()` kullanılır; dosya adını çağıran sorar.
    `mode=MODE_TRANSLATION` ise sütunlar ve hazır istem dış çeviri içindir; `mode=MODE_FINDINGS` ise Kontrol Et
    bulgularının dosyasıdır (`bulgu` sütunu eklenir; kapsam yalnızca seçili ya da görünen bulgular).
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
    ) -> None:
        super().__init__(parent)
        self._instruction = instruction
        self._translation = mode == MODE_TRANSLATION
        self._findings = mode == MODE_FINDINGS
        if self._translation:
            self.setWindowTitle("Dış çeviri dosyası oluştur")
            heading = "Çevirileri dış çeviri için dışa aktar"
            description = (
                "Dosyayı bir çevirmene veya sohbet modeline aşağıdaki talimatla verip çevirtebilir, sonucu "
                "Araçlar → “Dış Çeviriden İçe Aktar” ile geri yükleyebilirsiniz."
            )
            column_word = "yeni çeviri"
        elif self._findings:
            self.setWindowTitle("Kontrol bulgularını dışa aktar")
            heading = "Kontrol Et bulgularını satırlarıyla dışa aktar"
            description = (
                "Her satırın bulguları “bulgu” sütununa yazılır (yalnızca bilgi içindir). Dosyayı bir sohbet "
                "modeline aşağıdaki talimatla verip düzelttirebilir, sonucu Çeviri → Dış Redaksiyon → "
                "“İçe Aktar” ile geri yükleyebilirsiniz."
            )
            column_word = "düzeltme"
        else:
            self.setWindowTitle("Dış redaksiyon dosyası oluştur")
            heading = "Çevirileri dış redaksiyon için dışa aktar"
            description = (
                "Dosyayı bir sohbet modeline (ör. ücretsiz bir web modeli) aşağıdaki talimatla verip redakte "
                "ettirebilir, sonucu Çeviri → Dış Redaksiyon → “İçe Aktar” ile geri yükleyebilirsiniz."
            )
            column_word = "düzeltme"
        self.setMinimumWidth(660)
        lay = QVBoxLayout(self)
        lay.addWidget(title_row(heading, description, "cardTitle"))

        columns, extra = ("beş sütun", ", bulgu") if self._findings else ("dört sütun", "")
        self.format_group = QButtonGroup(self)
        self.txt_radio = QRadioButton("Metin (TXT)")
        self.txt_radio.setToolTip(
            f"Sütunlar ({columns}): orijinal, çeviri, {column_word}, grup{extra}. Model yalnızca “{column_word}” "
            "sütununu doldurur; boş bıraktığı satır değişmez. “grup” sütunu bağlam verir, salt okunurdur. "
            "Kontrol kodları en az bozulur."
        )
        self.xlsx_radio = QRadioButton("Excel (XLSX)")
        self.xlsx_radio.setToolTip(
            f"Excel'de açılır. Sütunlar ({columns}): orijinal, çeviri, {column_word}, grup{extra}. "
            f"{column_word.capitalize()} hücreleri boş bırakılabilir; “grup” sütunu bağlam verir, değiştirilmez. "
            "Çok kontrol kodu olan metinde TXT daha güvenlidir."
        )
        self.format_group.addButton(self.txt_radio, 0)
        self.format_group.addButton(self.xlsx_radio, 1)
        self.xlsx_radio.setChecked(True)
        lay.addWidget(self.xlsx_radio)
        lay.addWidget(self.txt_radio)

        self._scopes: list[Sequence[TranslationRow]] = []
        self.scope_group = QButtonGroup(self)
        choices = (
            (("Seçili bulguların satırları", selected), ("Görünen bulguların satırları", visible))
            if self._findings
            else (
                ("Seçili satırlar", selected),
                ("Tabloda görünen satırlar (arama ve filtrelere uyanlar)", visible),
                ("Tüm satırlar", all_rows),
            )
        )
        for text, rows in choices:
            radio = QRadioButton(f"{text} ({format_int(len(rows))})")
            radio.setEnabled(bool(rows))
            self.scope_group.addButton(radio, len(self._scopes))
            self._scopes.append(rows)
            lay.addWidget(radio)
        # Varsayılan kapsam her zaman her şeyi kapsayan seçenektir (bulgularda: görünen bulguların satırları).
        default = 1 if self._findings else 2
        default_button = self.scope_group.button(default)
        assert default_button is not None
        default_button.setChecked(True)

        self.group_box = QCheckBox()
        self.group_box.setToolTip(
            "Her grup (ör. Unity'de “Dialogue”, “UI” tabloları; diğer oyunlarda dosya) ayrı bir dosyaya "
            "yazılır: ad_Dialogue, ad_UI … Böylece metinleri konu konu "
            + ("çevirtebilirsiniz." if self._translation else "redakte ettirebilirsiniz.")
        )
        self._update_group_box()
        lay.addWidget(self.group_box)

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
        self.split_label = label("", "muted")
        split_row.addWidget(self.split_box)
        split_row.addWidget(self.part_spin)
        split_row.addWidget(self.split_label)
        split_row.addStretch(1)
        lay.addLayout(split_row)
        self._update_split()
        self.scope_group.idClicked.connect(lambda _id: self._scope_changed())
        self.group_box.toggled.connect(lambda _on: self._update_split())
        self.split_box.toggled.connect(lambda _on: self._update_split())
        self.part_spin.valueChanged.connect(lambda _v: self._update_split())

        lay.addWidget(label("Model için hazır talimat (dosyayla birlikte verin):", "muted"))
        self.prompt = QPlainTextEdit()
        self.prompt.setReadOnly(True)
        self.prompt.setMinimumHeight(220)
        lay.addWidget(self.prompt, 1)
        self.format_group.buttonToggled.connect(lambda *_: self._update_prompt())
        self._update_prompt()

        buttons = QHBoxLayout()
        self.copy_button = button("Talimatı Kopyala")
        self.copy_button.clicked.connect(self.copy_prompt)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        self.save_button = button("Kaydet…", "primary")
        self.save_button.clicked.connect(self.accept)
        cancel = button("Vazgeç", icon="x")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.save_button)
        buttons.addWidget(cancel)
        lay.addLayout(buttons)

    def format(self) -> str:
        """Seçilen dosya biçimi: `FORMAT_XLSX` (varsayılan) veya `FORMAT_TXT`."""
        return FORMAT_TXT if self.format_group.checkedId() == 0 else FORMAT_XLSX

    def _update_prompt(self) -> None:
        if self._translation:
            prompt = translation_prompt_txt if self.format() == FORMAT_TXT else translation_prompt_xlsx
        elif self._findings:
            prompt = findings_prompt_txt if self.format() == FORMAT_TXT else findings_prompt_xlsx
        else:
            prompt = revision_prompt_txt if self.format() == FORMAT_TXT else revision_prompt_xlsx
        self.prompt.setPlainText(prompt(self._instruction))

    def rows(self) -> Sequence[TranslationRow]:
        return self._scopes[max(self.scope_group.checkedId(), 0)]

    def by_group(self) -> bool:
        return self.group_box.isChecked()

    def _update_group_box(self) -> None:
        count = len(group_rows(self.rows()))
        self.group_box.setText(f"Her grup ayrı dosyaya ({format_int(count)} grup)")
        self.group_box.setEnabled(count > 1)
        if count <= 1:
            self.group_box.setChecked(False)

    def _scope_changed(self) -> None:
        self._update_group_box()
        self._update_split()

    def _sizes(self) -> list[int]:
        """Dosya kümelerinin satır sayıları: gruplama açıksa grup başına, değilse tek küme."""
        rows = self.rows()
        return [len(g) for g in group_rows(rows).values()] if self.by_group() else [len(rows)]

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

    def parts(self) -> int:
        """Her kümenin kaç parçaya bölüneceği; bölünmeyecekse 0."""
        return self.part_spin.value() if self.split_box.isChecked() else 0

    def copy_prompt(self) -> None:
        QGuiApplication.clipboard().setText(self.prompt.toPlainText())
        self.copy_button.setText("Kopyalandı ✓")
