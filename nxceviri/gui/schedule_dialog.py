"""Zamanlayıcı penceresi: 7 × 24 haftalık takvim, iş türü, çeviri hizmeti ve redaksiyon talimatı.

Takvimde hücreye tıklamak saati açar/kapatır; basılı tutup sürüklemek, ilk hücreyle imleç arasındaki dikdörtgeni
ilk hücrenin tersine göre boyar ya da siler (boş hücreden başlayan sürükleme boyar, seçiliden başlayan siler).
Hizmet alanları Otomatik Çeviri penceresiyle aynı kataloğu (`providers.catalog`) ve hizmet başına hatırlanan adres /
modeli kullanır; anahtar burada girilmez (Otomatik Çeviri penceresinde kaydedilir, gizli depoda durur).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.errors import NxError
from nxceviri.core.secrets import SecretStore, api_key_name
from nxceviri.core.translate.providers.base import TranslationProvider
from nxceviri.core.translate.providers.catalog import OPENAI_GROUP, SPECS, ProviderSpec, spec
from nxceviri.core.translate.providers.ollama import DEFAULT_URL
from nxceviri.core.translate.runner import ACTION_REVISE, ACTION_TRANSLATE
from nxceviri.core.translate.schedule import DAY_NAMES, HOURS, WEEKDAYS, Cell, Schedule, format_slot
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.machine_dialogs import (
    OPENAI_GROUP_LABEL,
    PROVIDER_OLLAMA,
    PROVIDER_ORDER,
    MachineSettings,
)
from nxceviri.gui.settings_dialog import check_with_wait_cursor
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import Banner, button, label, tip_html, title_row

#: Hücrenin en küçük ve tercih edilen boyutu (mantıksal piksel; yüksek DPI'da Qt ölçekler).
MIN_CELL = QSize(14, 18)
PREFERRED_CELL = QSize(24, 26)
_GAP = 2


class ScheduleGrid(QWidget):
    """Haftalık takvim: satırlar Pzt…Paz, sütunlar 00…23. Tıkla aç/kapat, sürükleyerek dikdörtgen boya/sil."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cells: set[Cell] = set()
        self._paint_on: bool | None = None  # sürüklerken boyanıyor mu siliniyor mu (None: sürükleme yok)
        self._anchor: Cell | None = None  # sürüklemenin başladığı hücre
        self._before: set[Cell] = set()  # sürükleme başlarken seçili hücreler
        self.setMouseTracking(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName("Haftalık takvim")
        self.setToolTip(tip_html("Saate tıklayın ya da basılı tutup sürükleyin. Koyu hücrelerde iş çalışır."))

    # --- veri -----------------------------------------------------------------------------

    def cells(self) -> set[Cell]:
        return set(self._cells)

    def set_cells(self, cells: Iterable[Cell]) -> None:
        self._cells = {(d, h) for d, h in cells if 0 <= d < WEEKDAYS and 0 <= h < HOURS}
        self.update()
        self.changed.emit()

    # --- ölçü -----------------------------------------------------------------------------

    def _left(self) -> int:
        fm = self.fontMetrics()
        return max(fm.horizontalAdvance(name) for name in DAY_NAMES) + 10

    def _top(self) -> int:
        return self.fontMetrics().height() + 6

    def minimumSizeHint(self) -> QSize:
        return QSize(
            self._left() + HOURS * MIN_CELL.width(),
            self._top() + WEEKDAYS * MIN_CELL.height(),
        )

    def sizeHint(self) -> QSize:
        return QSize(
            self._left() + HOURS * PREFERRED_CELL.width(),
            self._top() + WEEKDAYS * PREFERRED_CELL.height(),
        )

    def _cell_size(self) -> tuple[float, float]:
        return (
            (self.width() - self._left()) / HOURS,
            (self.height() - self._top()) / WEEKDAYS,
        )

    def cell_rect(self, day: int, hour: int) -> QRect:
        w, h = self._cell_size()
        x = self._left() + round(hour * w)
        y = self._top() + round(day * h)
        return QRect(x, y, max(1, round((hour + 1) * w) - round(hour * w) - _GAP), max(1, round(h) - _GAP))

    def cell_at(self, pos: QPoint) -> Cell | None:
        w, h = self._cell_size()
        if w <= 0 or h <= 0:
            return None
        hour = int((pos.x() - self._left()) // w)
        day = int((pos.y() - self._top()) // h)
        if pos.x() < self._left() or pos.y() < self._top() or not (0 <= day < WEEKDAYS and 0 <= hour < HOURS):
            return None
        return day, hour

    # --- çizim ----------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        tokens = current_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        fm = self.fontMetrics()
        cell_w, _cell_h = self._cell_size()
        # Saat başlıkları: sığmıyorsa her 2 ya da 3 saatte bir.
        step = next((s for s in (1, 2, 3, 4, 6) if fm.horizontalAdvance("00") + 4 <= cell_w * s), 6)
        painter.setPen(QColor(tokens["muted"]))
        for hour in range(0, HOURS, step):
            rect = self.cell_rect(0, hour)
            painter.drawText(
                QRect(rect.x(), 0, rect.width() + _GAP, self._top()), Qt.AlignmentFlag.AlignCenter, f"{hour:02d}"
            )
        for day, name in enumerate(DAY_NAMES):
            rect = self.cell_rect(day, 0)
            painter.drawText(
                QRect(0, rect.y(), self._left() - 6, rect.height()),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                name,
            )
        off = QColor(tokens["surface2"])
        on = QColor(tokens["accent"])
        border = QPen(QColor(tokens["border"]))
        for day in range(WEEKDAYS):
            for hour in range(HOURS):
                rect = self.cell_rect(day, hour)
                selected = (day, hour) in self._cells
                painter.fillRect(rect, on if selected else off)
                if not selected:
                    painter.setPen(border)
                    painter.drawRect(rect.adjusted(0, 0, -1, -1))
        if self.hasFocus():
            painter.setPen(QPen(QColor(tokens["accent"]), 1, Qt.PenStyle.DotLine))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    # --- fare -----------------------------------------------------------------------------

    def _apply(self, cell: Cell) -> None:
        """Sürüklemenin başladığı hücreyle `cell` arasındaki dikdörtgeni boyar ya da siler."""
        if self._paint_on is None or self._anchor is None:
            return
        (d0, h0), (d1, h1) = self._anchor, cell
        area = {(d, h) for d in range(min(d0, d1), max(d0, d1) + 1) for h in range(min(h0, h1), max(h0, h1) + 1)}
        cells = self._before | area if self._paint_on else self._before - area
        if cells != self._cells:
            self._cells = cells
            self.update()
            self.changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        cell = self.cell_at(event.position().toPoint())
        if event.button() != Qt.MouseButton.LeftButton or cell is None:
            super().mousePressEvent(event)
            return
        self._paint_on = cell not in self._cells
        self._anchor = cell
        self._before = set(self._cells)
        self._apply(cell)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        cell = self.cell_at(event.position().toPoint())
        if cell is not None:
            self._apply(cell)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._paint_on = None
        self._anchor = None
        super().mouseReleaseEvent(event)


#: İş türleri: (değer, görünen ad).
_ACTIONS = ((ACTION_TRANSLATE, "Otomatik çeviri"), (ACTION_REVISE, "Redaksiyon"))


class ScheduleDialog(QDialog):
    """Zamanlayıcı ayarı. `saved` False ise (proje dosyaya kaydedilmemiş) zamanlayıcı açılamaz."""

    def __init__(
        self,
        parent: QWidget | None,
        schedule: Schedule,
        *,
        saved: bool,
        secrets: SecretStore,
        provider_factory: Callable[[MachineSettings], TranslationProvider],
        remembered: Mapping[str, tuple[str, str]],
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zamanlayıcı")
        self._secrets = secrets
        self._factory = provider_factory
        self._clock = clock
        self._saved = saved
        #: Hizmet başına adres ve model; hizmet değişince alanlar buradan dolar, değişen alan geri yazılır.
        self._memory: dict[str, tuple[str, str]] = dict(remembered)
        first = spec(schedule.provider)
        self._memory[first.id] = (schedule.base_url or self._memory.get(first.id, ("", ""))[0], schedule.model)
        self._shown_provider = ""

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(
            title_row(
                "Zamanlayıcı",
                "Seçtiğiniz saatlerde otomatik çeviri ya da redaksiyon yapar; zaman dilimi bitince iş güvenle durur.",
                "cardTitle",
                icon="clock",
            )
        )
        self.notice = Banner()
        lay.addWidget(self.notice)
        if not saved:
            self.notice.show_message(
                "warning",
                "Proje henüz bir dosyaya kaydedilmedi. Zamanlayıcıyı açmak için önce Dosya → Kaydet ile projeyi "
                "kaydedin.",
            )
        self.enabled = QCheckBox("Zamanlayıcı açık")
        self.enabled.setChecked(schedule.enabled and saved)
        self.enabled.setEnabled(saved)
        lay.addWidget(self.enabled)

        self.grid = ScheduleGrid()
        self.grid.set_cells(schedule.cells)
        lay.addWidget(self.grid, 1)
        grid_row = QHBoxLayout()
        self.next_label = label("", "muted")
        grid_row.addWidget(self.next_label, 1)
        clear = button("Temizle", icon="eraser")
        clear.clicked.connect(lambda: self.grid.set_cells(()))
        grid_row.addWidget(clear)
        lay.addLayout(grid_row)

        form = QFormLayout()
        self.action = QComboBox()
        for value, text in _ACTIONS:
            self.action.addItem(text, value)
        self.action.setCurrentIndex(max(self.action.findData(schedule.action), 0))
        form.addRow("İş:", self.action)
        self.provider = QComboBox()
        for item in PROVIDER_ORDER:
            self.provider.addItem(OPENAI_GROUP_LABEL if item == OPENAI_GROUP else spec(item).label, item)
        # Uzun hizmet adları pencereyi genişletmesin (küçük pencerede de sığsın; tam ad açılır listede görünür).
        self.provider.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.provider.setMinimumContentsLength(18)
        self.test_button = button("Bağlantıyı Test Et", icon="activity")
        self.test_button.clicked.connect(self.test_connection)
        provider_row = QHBoxLayout()
        provider_row.addWidget(self.provider, 1)
        provider_row.addWidget(self.test_button)
        form.addRow("Sağlayıcı:", provider_row)
        self.preset = QComboBox()
        for item_spec in SPECS:
            if item_spec.openai_compat:
                self.preset.addItem(item_spec.label, item_spec.id)
        self.preset_label = label("Hizmet:")
        form.addRow(self.preset_label, self.preset)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumContentsLength(18)
        self.model_label = label("Model:")
        form.addRow(self.model_label, self.model)
        self.url = QLineEdit()
        self.url_label = label("Sunucu adresi:")
        form.addRow(self.url_label, self.url)
        self.key_state = label("", "muted", wrap=True)
        form.addRow(self.key_state)
        lay.addLayout(form)

        self.revise_note = label("", "muted", wrap=True)
        lay.addWidget(self.revise_note)
        self.instruction_label = label("Redaksiyon talimatı:")
        lay.addWidget(self.instruction_label)
        self.instruction = QPlainTextEdit(schedule.instruction)
        self.instruction.setPlaceholderText("Örn. Gereksiz zamirleri at, gündelik konuşma diliyle yaz.")
        self.instruction.setFixedHeight(72)
        lay.addWidget(self.instruction)

        self.status = Banner()
        lay.addWidget(self.status)
        lay.addWidget(
            label(
                "Zamanlayıcı yalnızca program ve bu proje açıkken çalışır; bilgisayar o saatlerde uyku modunda "
                "olmamalı. Çeviride yalnızca çevrilmemiş satırlar, redaksiyonda yalnızca henüz redakte edilmemiş "
                "makine çevirileri işlenir.",
                "muted",
                wrap=True,
            )
        )
        buttons = QDialogButtonBox()
        save = buttons.addButton("Kaydet", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setProperty("kind", "primary")
        bind_icon(save, "save")
        bind_icon(buttons.addButton("Vazgeç", QDialogButtonBox.ButtonRole.RejectRole), "x")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        if first.openai_compat:
            self.preset.setCurrentIndex(max(self.preset.findData(first.id), 0))
        self.provider.setCurrentIndex(max(self.provider.findData(OPENAI_GROUP if first.openai_compat else first.id), 0))
        self.provider.currentIndexChanged.connect(self._update)
        self.preset.currentIndexChanged.connect(self._update)
        self.action.currentIndexChanged.connect(self._update)
        self.grid.changed.connect(self._update_next)
        self.enabled.toggled.connect(self._update_next)
        self._update()

    # --- hizmet ---------------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        chosen = str(self.provider.currentData())
        return str(self.preset.currentData()) if chosen == OPENAI_GROUP else chosen

    @property
    def provider_spec(self) -> ProviderSpec:
        return spec(self.provider_name)

    def set_provider(self, provider_id: str) -> None:
        chosen = spec(provider_id)
        if chosen.openai_compat:
            self.preset.setCurrentIndex(max(self.preset.findData(chosen.id), 0))
        self.provider.setCurrentIndex(
            max(self.provider.findData(OPENAI_GROUP if chosen.openai_compat else chosen.id), 0)
        )

    def _switch_provider(self) -> None:
        name = self.provider_name
        if name == self._shown_provider:
            return
        if self._shown_provider:
            self._memory[self._shown_provider] = (self.url.text().strip(), self.model.currentText().strip())
        self._shown_provider = name
        current = self.provider_spec
        url, model = self._memory.get(name, ("", ""))
        model = model or current.default_model
        self.model.clear()
        if model:
            self.model.addItem(model)
        self.model.setEditText(model)
        default_url = DEFAULT_URL if current.id == PROVIDER_OLLAMA else current.default_url
        self.url.setText(url or default_url)

    def _stored_key(self) -> bool:
        try:
            return bool(self._secrets.get(api_key_name(self.provider_name)))
        except NxError:
            return False

    def _update(self) -> None:
        self.preset.setVisible(self.provider.currentData() == OPENAI_GROUP)
        self.preset_label.setVisible(self.preset.isVisibleTo(self))
        self._switch_provider()
        chosen = self.provider_spec
        self.model.setVisible(chosen.has_models)
        self.model_label.setVisible(chosen.has_models)
        self.url.setVisible(chosen.url_editable)
        self.url_label.setVisible(chosen.url_editable)
        if chosen.needs_key:
            self.key_state.setText(
                "Kayıtlı anahtar var."
                if self._stored_key()
                else "Kayıtlı anahtar yok. Anahtarı Çeviri → Otomatik Çeviri penceresinden kaydedin."
            )
        self.key_state.setVisible(chosen.needs_key)
        # Klasik hizmet (DeepL, Google Translate) talimat izleyemez: redaksiyon seçilemez.
        model = self.action.model()
        assert isinstance(model, QStandardItemModel)
        revise_item = model.item(self.action.findData(ACTION_REVISE))
        revise_item.setEnabled(not chosen.classic)
        if chosen.classic and self.action.currentData() == ACTION_REVISE:
            self.action.setCurrentIndex(self.action.findData(ACTION_TRANSLATE))
        self.revise_note.setText(
            f"{chosen.name} talimat izleyemez; redaksiyon için bir yapay zekâ hizmeti seçin." if chosen.classic else ""
        )
        self.revise_note.setVisible(chosen.classic)
        revise = self.action.currentData() == ACTION_REVISE
        self.instruction_label.setVisible(revise)
        self.instruction.setVisible(revise)
        self.status.show_message("success", "")
        self._update_next()

    def _update_next(self) -> None:
        sched = self.schedule()
        now = self._clock()
        if not sched.cells:
            text = "Sonraki çalışma: yok (takvimde saat seçin)"
        elif sched.active_at(now):
            text = f"Sonraki çalışma: şimdi · bitiş {format_slot(sched.slot_end(now))}"
        else:
            start = sched.next_start(now)
            text = f"Sonraki çalışma: {format_slot(start)}" if start is not None else "Sonraki çalışma: her saat"
        if not sched.enabled:
            text += " (zamanlayıcı kapalı)"
        self.next_label.setText(text)

    def _base_url(self) -> str:
        return self.url.text().strip() if self.provider_spec.url_editable else ""

    def schedule(self) -> Schedule:
        chosen = self.provider_spec
        return Schedule(
            enabled=self.enabled.isChecked() and self._saved,
            cells=frozenset(self.grid.cells()),
            action=str(self.action.currentData()),
            provider=chosen.id,
            model=self.model.currentText().strip() if chosen.has_models else "",
            base_url=self._base_url(),
            instruction=self.instruction.toPlainText().strip(),
        )

    def test_connection(self) -> bool:
        sched = self.schedule()
        settings = MachineSettings(provider=sched.provider, base_url=sched.base_url, model=sched.model, notes="")
        try:
            provider = self._factory(settings)
        except NxError as exc:
            self.status.show_message("danger", exc.user_text())
            return False
        status = check_with_wait_cursor(provider)
        self.status.show_message("success" if status.ok else "danger", status.message)
        return status.ok

    def validate(self) -> bool:
        """Kaydetmeden önce denetim; sorun varsa bantta gösterir."""
        sched = self.schedule()
        problem = ""
        if sched.enabled and not sched.cells:
            problem = "Takvimde en az bir saat seçin."
        elif sched.enabled and self.provider_spec.has_models and not sched.model:
            problem = "Bir model seçin veya adını yazın."
        elif sched.enabled and sched.action == ACTION_REVISE and not sched.instruction:
            problem = "Modelin neyi düzeltmesini istediğinizi talimat kutusuna yazın."
        if problem:
            self.status.show_message("warning", problem)
            return False
        return True

    def _accept(self) -> None:
        if self.validate():
            self.accept()
