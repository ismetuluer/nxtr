"""Adım 1 — Oyunu Ekle: anahtar dosyası ve NSP/NSZ dosyaları."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget

from nxceviri.core.pipeline import SUPPORTED_SUFFIXES
from nxceviri.core.project import SourceRecord
from nxceviri.gui.game_card import RELINK_TEXT, DlcCard, GameCard
from nxceviri.gui.widgets import Banner, Card, DropZone, PageHeader, button, label, tip_html

KEYS_HELP = (
    "Anahtarları kendi konsolunuzdan Lockpick_RCM ile çıkarıp prod.keys dosyasını seçin. Uygulama "
    "anahtar içermez veya indirmez; yalnızca dosyanın yolunu hatırlar."
)
DROP_READY_TEXT = "NSP / NSZ dosyalarını bırakın"
#: Oyun eklenmişken şeritteki metin.
DROP_COMPACT_TEXT = "Yeni NSP / NSZ dosyalarını buraya bırakabilirsiniz"
RELINK_ACTION = RELINK_TEXT
DROP_LOCKED_TEXT = "Önce anahtar dosyası seçin"
#: Bundan uzun neden çipte "Devam edilemiyor" olarak, tam metni ayrıntıda gösterilir.
CHIP_TEXT_LIMIT = 40
#: Son projeler kartında en çok kaç satır görünür.
RECENT_SHOWN = 8
RECENT_NAME_WIDTH = 200
#: Boş ekranda gösterilen akış: (adım adı, tek cümlelik açıklama); sıra `step_nav.STEPS` ile aynıdır.
HOW_IT_WORKS: tuple[tuple[str, str], ...] = (
    ("Oyunu Ekle", "Anahtar dosyanızı seçin, oyunun NSP ya da NSZ dosyasını bırakın."),
    ("Metinleri Tara", "Oyunun içindeki metinler ayıklanır."),
    ("Çevir", "Makine çevirisi yapın, satırları elle düzeltin."),
    ("Kontrol Et", "Kod, uzunluk ve yazım sorunlarını görün ve düzeltin."),
    ("Dışa Aktar", "Oyuna geri yüklenecek mod klasörünü oluşturun."),
)
STEP_NAME_WIDTH = 150


class AddGamePage(QWidget):
    choose_keys = Signal()
    add_files = Signal(list)
    browse_files = Signal()
    remove_source = Signal(int)
    relink_requested = Signal()
    next_step = Signal()
    open_recent = Signal(Path)

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
        self.add_button = button("Dosya Ekle…", icon="file-plus")
        self.add_button.setToolTip("NSP / NSZ dosyası seç")
        self.add_button.clicked.connect(self.browse_files)
        self.header.add_action(self.add_button)
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

        # --- uyarı bandı (eksik dosya, çakışan sürüm, okunamayan dosya…) ---
        self.files_banner = Banner()
        self.files_banner.action_clicked.connect(self.relink_requested)
        lay.addWidget(self.files_banner)

        # --- oyun kartı ve ek içerikler (oyun eklenince görünür) ---
        self.game_card = GameCard()
        self.game_card.remove_requested.connect(self.remove_source)
        self.game_card.relink_requested.connect(self.relink_requested)
        self.game_card.hide()
        lay.addWidget(self.game_card)
        self.dlc_card = DlcCard()
        self.dlc_card.remove_requested.connect(self.remove_source)
        self.dlc_card.relink_requested.connect(self.relink_requested)
        self.dlc_card.hide()
        lay.addWidget(self.dlc_card)

        # --- bırakma alanı: boş ekranda maskotlu, oyun eklenince tek satırlık şerit ---
        self.drop = DropZone(SUPPORTED_SUFFIXES, DROP_READY_TEXT)
        self.drop.files_dropped.connect(self.add_files)
        self.drop.button.hide()  # dosya seçme eylemi başlıktaki "Dosya Ekle…" düğmesindedir
        lay.addWidget(self.drop)
        self._keys_ready = True
        self._busy = False
        self._chip: tuple[str, str, list[str]] = ("", "", [])

        # --- son projeler (yalnızca ekran boşken) ---
        self.recent_card = Card("Son projeler")
        self.recent_card.hide()
        self.recent_list = QVBoxLayout()
        self.recent_list.setSpacing(4)
        self.recent_card.body.addLayout(self.recent_list)
        lay.addWidget(self.recent_card)
        self._recent: list[Path] = []
        self._has_sources = False

        # --- beş adımın kısa yolu (yalnızca ekran boşken) ---
        self.steps_card = Card("Beş adımda çeviri")
        for number, (name, text) in enumerate(HOW_IT_WORKS, start=1):
            row = QHBoxLayout()
            row.setSpacing(12)
            title = label(f"{number} {name}", "stepName")
            title.setFixedWidth(STEP_NAME_WIDTH)
            row.addWidget(title, alignment=Qt.AlignmentFlag.AlignTop)
            row.addWidget(label(text, "muted", wrap=True), 1)
            self.steps_card.body.addLayout(row)
        lay.addWidget(self.steps_card)

        lay.addStretch(1)

    # --- güncelleme yöntemleri ----------------------------------------------------------

    def set_keys_state(self, state: str, path: Path | None, message: str = "") -> None:
        """Anahtar kartı yalnızca geçerli anahtar yokken görünür; durum ayrıca durum çubuğunda gösterilir."""
        self._keys_ready = state == "success"
        self.keys_card.setVisible(not self._keys_ready)
        self.keys_path.setText(str(path) if path else "prod.keys henüz seçilmedi")
        self.keys_button.setText("Başka Dosya Seç…" if path else "prod.keys Seç…")
        self.keys_banner.show_message("danger" if state == "danger" else "warning", message)
        self._sync_drop()

    def _sync_drop(self) -> None:
        """Bırakma alanı: anahtar yokken kilitli, oyun varken şerit; başlıktaki "Dosya Ekle…" da aynı koşula bağlı."""
        self.drop.setEnabled(self._keys_ready)
        self.drop.set_compact(self._has_sources)
        if not self._keys_ready:
            self.drop.text.setText(DROP_LOCKED_TEXT)
        else:
            self.drop.text.setText(DROP_COMPACT_TEXT if self._has_sources else DROP_READY_TEXT)
        self.add_button.setEnabled(self._keys_ready and not self._busy)

    def set_recent(self, paths: list[Path]) -> None:
        """Son projeler kartı; diskte olmayanlar atlanır. Kart yalnızca kaynak yokken ve liste doluyken görünür."""
        existing = [p for p in paths if p.is_file()][:RECENT_SHOWN]
        if existing != self._recent:
            self._recent = existing
            while (item := self.recent_list.takeAt(0)) is not None:
                if (widget := item.widget()) is not None:
                    widget.setParent(None)
                    widget.deleteLater()
            for path in existing:
                self.recent_list.addWidget(self._recent_row(path))
        self._sync_recent_visible()

    def _recent_row(self, path: Path) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        link = QToolButton()
        link.setText(path.stem)
        link.setProperty("role", "link")
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.setToolTip(str(path))
        link.clicked.connect(lambda _=False, p=path: self.open_recent.emit(p))
        name_cell = QHBoxLayout()  # ad sola yaslı, klasör sütunu aynı hizada başlar
        name_cell.setContentsMargins(0, 0, 0, 0)
        name_cell.addWidget(link, alignment=Qt.AlignmentFlag.AlignLeft)
        name_box = QWidget()
        name_box.setFixedWidth(RECENT_NAME_WIDTH)
        name_box.setLayout(name_cell)
        lay.addWidget(name_box)
        folder = label(str(path.parent), "muted", tip=str(path))
        lay.addWidget(folder, 1)
        return row

    def _sync_recent_visible(self) -> None:
        self.recent_card.setVisible(bool(self._recent) and not self._has_sources)
        self.steps_card.setVisible(not self._has_sources)

    def set_sources(self, sources: list[SourceRecord]) -> None:
        """Oyun kartı ve ek içerikler kartını kurar; `remove_source` sinyali bu listedeki sırayı taşır."""
        self._has_sources = bool(sources)
        self._sync_recent_visible()
        self.game_card.set_sources(sources)
        self.game_card.setVisible(bool(sources))
        self.dlc_card.set_sources(sources)
        self._sync_drop()

    def set_progress(self, total: int, translated: int) -> None:
        """Oyun kartındaki "N satır · %P çevrildi" rozeti; satır yoksa rozet görünmez."""
        self.game_card.set_progress(total, translated)

    def set_files_message(self, state: str, text: str, action: str = "") -> None:
        self.files_banner.show_message(state, text, action)

    def set_busy(self, busy: bool, text: str = "") -> None:
        self._busy = busy
        self.keys_button.setEnabled(not busy)
        self.drop.setAcceptDrops(not busy)
        self._sync_drop()
        self._show_chip("neutral", text)

    def set_can_continue(self, ok: bool, reason: str) -> None:
        """Devam düğmesi; devam edilemiyorsa neden başlıktaki çipte (uzunsa ayrıntısında) ve düğme ipucunda."""
        self.next_button.setEnabled(ok)
        if ok:
            self._show_chip("", "")
            self.next_button.setToolTip("Metinleri taramaya geç")
            return
        self.next_button.setToolTip(tip_html(reason))
        if len(reason) <= CHIP_TEXT_LIMIT:
            self._show_chip("neutral", reason)
        else:
            self._show_chip("neutral", "Devam edilemiyor", [reason])

    def _show_chip(self, state: str, text: str, details: list[str] | None = None) -> None:
        self._chip = (state, text, details or [])
        self.header.chip.show_status(state, text, self._chip[2])
        self._fit_header()

    def _fit_header(self) -> None:
        """Başlık asla kesilmez: durum çipi ve düğmelerle birlikte sığmıyorsa çip gizlenir (neden düğme ipucunda ve
        durum çubuğundaki anahtar bölmesinde zaten durur)."""
        header = self.header
        header.title.setMinimumWidth(header.title.sizeHint().width())
        chip = header.chip
        if not self.isVisible() or (chip.isHidden() and not self._chip[1]):
            return
        mark = header.findChild(QLabel, "titleIcon")
        spacing = 10
        needed = (
            (mark.sizeHint().width() if mark else 0)
            + header.title.sizeHint().width()
            + chip.sizeHint().width()
            + self.add_button.sizeHint().width()
            + self.next_button.sizeHint().width()
            + 8
            + 4 * spacing
        )
        state, text, details = self._chip
        if header.width() < needed:
            chip.hide()
        elif state and text and chip.isHidden():
            chip.show_status(state, text, details)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_header()
