"""Adım 1 — Oyunu Ekle: anahtar dosyası ve NSP/NSZ dosyaları."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.pipeline import SUPPORTED_SUFFIXES, source_label
from nxceviri.core.project import SourceRecord
from nxceviri.gui.widgets import Banner, Card, DropZone, PageHeader, button, format_size, label, tip_html

KEYS_HELP = (
    "Anahtarları kendi konsolunuzdan Lockpick_RCM ile çıkarıp prod.keys dosyasını seçin. Uygulama "
    "anahtar içermez veya indirmez; yalnızca dosyanın yolunu hatırlar."
)
DROP_READY_TEXT = "NSP / NSZ dosyalarını bırakın"
DROP_LOCKED_TEXT = "Önce anahtar dosyası seçin"
#: Bundan uzun neden çipte "Devam edilemiyor" olarak, tam metni ayrıntıda gösterilir.
CHIP_TEXT_LIMIT = 40


class AddGamePage(QWidget):
    choose_keys = Signal()
    add_files = Signal(list)
    browse_files = Signal()
    remove_source = Signal(int)
    next_step = Signal()

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
        lay.setSpacing(16)

        self.header = PageHeader("Oyunu Ekle", "circle-plus")
        self.next_button = button("Metinleri Tara  →", "primary", icon="scan-search")
        self.next_button.clicked.connect(self.next_step)
        self.next_button.setEnabled(False)
        self.header.add_action(self.next_button)
        lay.addWidget(self.header)

        # --- anahtarlar (yalnızca geçerli prod.keys yokken; sonra Dosya > Anahtarlar menüsünden) ---
        self.keys_card = Card("Anahtar dosyası gerekli", hint=KEYS_HELP)
        row = QHBoxLayout()
        self.keys_path = label("prod.keys henüz seçilmedi", "muted")
        self.keys_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.keys_path, 1)
        self.keys_button = button("prod.keys Seç…", "primary", icon="key-round")
        self.keys_button.clicked.connect(self.choose_keys)
        row.addWidget(self.keys_button)
        self.keys_card.body.addLayout(row)
        self.keys_banner = Banner()
        self.keys_card.body.addWidget(self.keys_banner)
        lay.addWidget(self.keys_card)

        # --- oyun dosyaları ---
        self.files_card = Card(
            "Oyun dosyaları",
            hint="Ana oyun (base) dosyasını ekleyin. Güncelleme ve DLC dosyalarını da eklerseniz metinler "
            "en güncel hâlleriyle taranır.",
        )
        self.drop = DropZone(SUPPORTED_SUFFIXES, DROP_READY_TEXT)
        self.drop.files_dropped.connect(self.add_files)
        self.drop.button.clicked.connect(self.browse_files)
        self.files_card.body.addWidget(self.drop)
        self.files_banner = Banner()
        self.files_card.body.addWidget(self.files_banner)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Tür", "Oyun", "TitleID", "Sürüm", "Dosya", ""])
        self.table.verticalHeader().hide()
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.hide()
        self.files_card.body.addWidget(self.table)
        lay.addWidget(self.files_card)

        lay.addStretch(1)

    # --- güncelleme yöntemleri ----------------------------------------------------------

    def set_keys_state(self, state: str, path: Path | None, message: str = "") -> None:
        """Anahtar kartı yalnızca geçerli anahtar yokken görünür; durum ayrıca durum çubuğunda gösterilir."""
        ready = state == "success"
        self.keys_card.setVisible(not ready)
        self.keys_path.setText(str(path) if path else "prod.keys henüz seçilmedi")
        self.keys_button.setText("Başka Dosya Seç…" if path else "prod.keys Seç…")
        self.keys_banner.show_message("danger" if state == "danger" else "warning", message)
        self.drop.setEnabled(ready)
        self.drop.text.setText(DROP_READY_TEXT if ready else DROP_LOCKED_TEXT)

    def set_sources(self, sources: list[SourceRecord]) -> None:
        self.table.setRowCount(len(sources))
        for row, s in enumerate(sources):
            exists = s.path.is_file()
            version = f"v{s.version}" + (f"  ({s.display_version})" if s.display_version else "")
            values = [source_label(s.kind), s.name, s.title_id, version, s.path.name]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                tip = f"{s.path}\n{format_size(s.file_size)}"
                item.setToolTip(tip if exists else f"Dosya bulunamadı: {s.path}")
                if not exists and col == 4:
                    item.setText(f"{s.path.name}  (bulunamadı)")
                self.table.setItem(row, col, item)
            remove = button("Kaldır", "flat")
            remove.clicked.connect(lambda _=False, r=row: self.remove_source.emit(r))
            self.table.setCellWidget(row, 5, remove)
        self.table.setVisible(bool(sources))
        height = self.table.horizontalHeader().height() + sum(self.table.rowHeight(r) for r in range(len(sources)))
        self.table.setFixedHeight(height + 4)

    def set_files_message(self, state: str, text: str) -> None:
        self.files_banner.show_message(state, text)

    def set_busy(self, busy: bool, text: str = "") -> None:
        for w in (self.keys_button, self.drop.button):
            w.setEnabled(not busy)
        self.drop.setAcceptDrops(not busy)
        self.header.chip.show_status("neutral", text)

    def set_can_continue(self, ok: bool, reason: str) -> None:
        """Devam düğmesi; devam edilemiyorsa neden başlıktaki çipte (uzunsa ayrıntısında) ve düğme ipucunda."""
        self.next_button.setEnabled(ok)
        if ok:
            self.header.chip.show_status("", "")
            self.next_button.setToolTip("Metinleri taramaya geç")
            return
        self.next_button.setToolTip(tip_html(reason))
        if len(reason) <= CHIP_TEXT_LIMIT:
            self.header.chip.show_status("neutral", reason)
        else:
            self.header.chip.show_status("neutral", "Devam edilemiyor", [reason])
