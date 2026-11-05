"""Adım 5 — Dışa Aktar: LayeredFS mod klasörü üretimi."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.export.layeredfs import LAYOUT_ATMOSPHERE, LAYOUT_EMULATOR, LAYOUT_LABELS, safe_mod_name
from nxceviri.gui.widgets import Banner, Card, PageHeader, ProgressPanel, button, format_int, label, tip_html


class ExportPage(QWidget):
    choose_folder = Signal()
    export_requested = Signal()
    include_errors_changed = Signal(bool)
    open_folder = Signal()
    cancel = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget()
        content.setObjectName("page")
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(14)
        self.header = PageHeader(
            "Dışa Aktar",
            "package",
            "Çevirileriniz oyunun orijinal dosyalarına işlenir ve yalnızca değişen dosyalardan oluşan bir mod "
            "klasörü üretilir. Oyun dosyalarınız değişmez; tam oyun kopyası üretilmez.",
        )
        self.export_button = button("Modu Oluştur", "primary", icon="package")
        self.export_button.clicked.connect(self.export_requested)
        self.header.add_action(self.export_button)
        self._can_export = False
        lay.addWidget(self.header)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        form_box = QWidget()
        fl = QVBoxLayout(form_box)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(14)

        card = Card("Mod ayarları")
        form = QFormLayout()
        self.layout_group = QButtonGroup(self)
        self.layout_buttons: dict[str, QRadioButton] = {}
        layouts = QVBoxLayout()
        for key in (LAYOUT_ATMOSPHERE, LAYOUT_EMULATOR):
            rb = QRadioButton(LAYOUT_LABELS[key])
            self.layout_group.addButton(rb)
            self.layout_buttons[key] = rb
            layouts.addWidget(rb)
        self.layout_buttons[LAYOUT_ATMOSPHERE].setChecked(True)
        form.addRow("Hedef:", layouts)
        self.mod_name = QLineEdit()
        form.addRow("Mod adı:", self.mod_name)
        folder_row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setReadOnly(True)
        self.folder.setPlaceholderText("Modun oluşturulacağı klasörü seçin")
        pick = button("Seç…", icon="folder-open")
        pick.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(pick)
        form.addRow("Konum:", folder_row)
        card.body.addLayout(form)
        self.target = label("", "muted", wrap=True)
        card.body.addWidget(self.target)
        self.include_errors_box = QCheckBox("Hatalı satırları da aktar")
        self.include_errors_box.setToolTip(
            tip_html(
                "Oyunun kabul ettiği hatalı satırlar çevirisiyle yazılır; oyun çökebilir. "
                "Kontrol kodu bozuk satırlar orijinal bırakılır."
            )
        )
        self.include_errors_box.toggled.connect(self.include_errors_changed)
        card.body.addWidget(self.include_errors_box)
        # Sinyaller tüm alanlar kurulduktan sonra bağlanır.
        for rb in self.layout_buttons.values():
            rb.toggled.connect(self.update_target)
        self.mod_name.textChanged.connect(self.update_target)
        fl.addWidget(card)

        summary = Card("Özet")
        self.summary = label("", wrap=True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        summary.body.addWidget(self.summary)
        fl.addWidget(summary)

        self.result = Banner()
        fl.addWidget(self.result)
        self.open_button = button("Mod Klasörünü Aç", icon="folder-open")
        self.open_button.clicked.connect(self.open_folder)
        self.open_button.hide()
        fl.addWidget(self.open_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.stack.addWidget(form_box)
        self.form_box = form_box

        self.progress = ProgressPanel()
        self.progress.cancel_requested.connect(self.cancel)
        self.stack.addWidget(self.progress)
        lay.addStretch(1)

    @property
    def layout_key(self) -> str:
        for key, rb in self.layout_buttons.items():
            if rb.isChecked():
                return key
        return LAYOUT_ATMOSPHERE

    def destination(self) -> Path | None:
        if not self.folder.text():
            return None
        return Path(self.folder.text()) / safe_mod_name(self.mod_name.text())

    def update_target(self) -> None:
        dest = self.destination()
        if dest is None:
            self.target.setText("Konum seçilmedi.")
            return
        if self.layout_key == LAYOUT_ATMOSPHERE:
            inner = "atmosphere/contents/<TitleID>/romfs/…"
        else:
            inner = f"<TitleID>/{safe_mod_name(self.mod_name.text())}/romfs/…"
        self.target.setText(f"Oluşturulacak klasör: {dest}\nİçeriği: {inner}")

    def set_include_errors(self, *, errors: int, checked: bool) -> None:
        """Kutuyu proje ayarına göre kurar; hatalı satır yoksa kutu gizlenir."""
        self.include_errors_box.blockSignals(True)
        self.include_errors_box.setChecked(checked)
        self.include_errors_box.blockSignals(False)
        self.include_errors_box.setVisible(errors > 0)

    def set_summary(
        self,
        *,
        written: int,
        errors: int,
        untranslated: int,
        conversion: str,
        can_export: bool,
        include_errors: bool = False,
    ) -> None:
        wrong = "hatalı (uygun olanlar denenecek)" if include_errors and errors else "hatalı"
        self.summary.setText(
            f"{format_int(written)} yazılacak · {format_int(errors)} {wrong} · "
            f"{format_int(untranslated)} çevrilmemiş · Harf dönüştürme: {conversion}"
        )
        self.summary.setToolTip(
            "Hatalı satırlar kutu işaretlenmedikçe yazılmaz; çevrilmemiş satırlar oyunda orijinal hâliyle kalır."
        )
        self._can_export = can_export
        self.export_button.setEnabled(can_export and self.stack.currentWidget() is not self.progress)

    def set_notes(self, problems: list[str], warnings: list[str]) -> None:
        """Dışa aktarma öncesi sorunlar ve uyarılar: başlıktaki çipte sayı, ayrıntıda cümleler (sorunlar önce)."""
        parts = []
        if problems:
            parts.append(f"{len(problems)} sorun")
        if warnings:
            parts.append(f"{len(warnings)} uyarı")
        state = "danger" if problems else "warning" if warnings else ""
        self.header.chip.show_status(state, " · ".join(parts), [*problems, *warnings])

    def show_running(self) -> None:
        self.progress.start("Mod oluşturuluyor")
        self.stack.setCurrentWidget(self.progress)
        self.export_button.setEnabled(False)

    def show_form(self) -> None:
        self.stack.setCurrentWidget(self.form_box)
        self.export_button.setEnabled(self._can_export)
