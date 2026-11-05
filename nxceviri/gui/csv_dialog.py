"""Çevirileri dış redaksiyon veya dış çeviri için TXT (dört sütun) ya da XLSX (Excel) olarak dışa aktarma penceresi."""

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
    DEFAULT_PART_ROWS,
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


class CsvExportDialog(QDialog):
    """Hangi biçimde, hangi satırların, kaç parçada yazılacağını seçtirir ve dış model için hazır istemi gösterir.

    `accepted` ile kapanırsa `format()`, `rows()` ve `part_rows()` kullanılır; dosya adını çağıran sorar.
    `mode=MODE_TRANSLATION` ise sütunlar ve hazır istem dış çeviri içindir.
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
        if self._translation:
            self.setWindowTitle("Dış çeviri dosyası oluştur")
            heading = "Çevirileri dış çeviri için dışa aktar"
            description = (
                "Dosyayı bir çevirmene veya sohbet modeline aşağıdaki istemle verip çevirtebilir, sonucu "
                "Araçlar → “Dış Çeviriden İçe Aktar” ile geri yükleyebilirsiniz."
            )
            column_word = "yeni çeviri"
        else:
            self.setWindowTitle("Dış redaksiyon dosyası oluştur")
            heading = "Çevirileri dış redaksiyon için dışa aktar"
            description = (
                "Dosyayı bir sohbet modeline (ör. ücretsiz bir web modeli) aşağıdaki istemle verip redakte "
                "ettirebilir, sonucu Araçlar → “Dış Redaksiyondan İçe Aktar” ile geri yükleyebilirsiniz."
            )
            column_word = "düzeltme"
        self.setMinimumWidth(660)
        lay = QVBoxLayout(self)
        lay.addWidget(title_row(heading, description, "cardTitle"))

        self.format_group = QButtonGroup(self)
        self.txt_radio = QRadioButton(f"TXT — dört sütun: orijinal, çeviri, {column_word}, grup")
        self.txt_radio.setToolTip(
            f"Model yalnızca “{column_word}” sütununu doldurur; boş bıraktığı satır değişmez. “grup” sütunu "
            "bağlam verir, salt okunurdur. Kontrol kodları en az bozulur."
        )
        self.xlsx_radio = QRadioButton(f"XLSX — Excel'de dört sütun: orijinal, çeviri, {column_word}, grup")
        self.xlsx_radio.setToolTip(
            f"Excel'de açılır; {column_word} hücreleri boş bırakılabilir. “grup” sütunu bağlam verir, "
            "değiştirilmez. Çok kontrol kodu olan metinde TXT daha güvenlidir."
        )
        self.format_group.addButton(self.txt_radio, 0)
        self.format_group.addButton(self.xlsx_radio, 1)
        self.txt_radio.setChecked(True)
        lay.addWidget(self.txt_radio)
        lay.addWidget(self.xlsx_radio)

        self._scopes: list[Sequence[TranslationRow]] = []
        self.scope_group = QButtonGroup(self)
        for text, rows in (
            ("Seçili satırlar", selected),
            ("Tabloda görünen satırlar (arama ve filtrelere uyanlar)", visible),
            ("Tüm satırlar", all_rows),
        ):
            radio = QRadioButton(f"{text} ({format_int(len(rows))})")
            radio.setEnabled(bool(rows))
            self.scope_group.addButton(radio, len(self._scopes))
            self._scopes.append(rows)
            lay.addWidget(radio)
        default = 0 if len(selected) > 1 else 1 if 0 < len(visible) < len(all_rows) else 2
        default_button = self.scope_group.button(default)
        assert default_button is not None
        default_button.setChecked(True)

        self.group_box = QCheckBox()
        self.group_box.setToolTip(
            "Her grup (ör. Unity'de “Dialogue”, “UI” tabloları; diğer oyunlarda dosya) ayrı bir dosyaya "
            "yazılır: ad_Dialogue, ad_UI … Böylece metinleri konu konu "
            + ("çevirtebilirsiniz." if self._translation else "redakte ettirebilirsiniz.")
        )
        self.scope_group.idClicked.connect(lambda _id: self._update_group_box())
        self._update_group_box()
        lay.addWidget(self.group_box)

        split_row = QHBoxLayout()
        self.split_box = QCheckBox("Parçalara böl, dosya başına en çok")
        self.split_box.setChecked(True)
        self.split_box.setToolTip(
            "Ücretsiz sohbet modelleri uzun dosyaları yarıda keser; parçalar ayrı ayrı verilip geri yüklenebilir "
            "(içe aktarırken birden çok dosya seçilebilir)."
        )
        self.part_spin = QSpinBox()
        self.part_spin.setRange(10, 5000)
        self.part_spin.setSingleStep(50)
        self.part_spin.setValue(DEFAULT_PART_ROWS)
        self.part_spin.setSuffix(" satır")
        self.split_box.toggled.connect(self.part_spin.setEnabled)
        split_row.addWidget(self.split_box)
        split_row.addWidget(self.part_spin)
        split_row.addStretch(1)
        lay.addLayout(split_row)

        lay.addWidget(label("Model için hazır istem (dosyayla birlikte verin):", "muted"))
        self.prompt = QPlainTextEdit()
        self.prompt.setReadOnly(True)
        self.prompt.setMinimumHeight(220)
        lay.addWidget(self.prompt, 1)
        self.format_group.buttonToggled.connect(lambda *_: self._update_prompt())
        self._update_prompt()

        buttons = QHBoxLayout()
        self.copy_button = button("İstemi Kopyala")
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
        """Seçilen dosya biçimi: `FORMAT_TXT` (varsayılan) veya `FORMAT_XLSX`."""
        return FORMAT_XLSX if self.format_group.checkedId() == 1 else FORMAT_TXT

    def _update_prompt(self) -> None:
        if self._translation:
            prompt = translation_prompt_txt if self.format() == FORMAT_TXT else translation_prompt_xlsx
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

    def part_rows(self) -> int:
        """Parça başına satır; bölünmeyecekse 0."""
        return self.part_spin.value() if self.split_box.isChecked() else 0

    def copy_prompt(self) -> None:
        QGuiApplication.clipboard().setText(self.prompt.toPlainText())
        self.copy_button.setText("Kopyalandı ✓")
