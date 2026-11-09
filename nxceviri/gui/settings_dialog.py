"""Ayarlar penceresi: görünüm, klavye kısayolları, çeviri sağlayıcıları ve güncelleme ayarları.

Solda sayfa listesi, sağda seçili sayfa durur; değişiklikler anında uygulanır ve kaydedilir (Kaydet düğmesi yoktur).
Görünüm sayfasındaki seçimler menülerdeki `QAction`larla iki yönlüdür: menüden değişince pencere, pencereden
değişince menü güncellenir. Tema ve yazı boyutu sinyalle bildirilir; temayı uygulamak pencereyi açanın işidir.
"""

from __future__ import annotations

from collections.abc import Collection
from urllib.parse import urlsplit

from PySide6.QtCore import QEvent, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QAction, QFont, QGuiApplication, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.errors import NxError
from nxceviri.core.qa.checks import KIND_LABELS
from nxceviri.core.qa.live import DEFAULT_LIVE_KINDS, KIND_HINTS, LIVE_KINDS
from nxceviri.core.secrets import DEEPL_API_KEY, SecretStore
from nxceviri.core.translate.providers.base import ProviderError, ProviderStatus, TranslationProvider
from nxceviri.core.translate.providers.deepl import DeepLProvider, plan_label
from nxceviri.core.translate.providers.ollama import DEFAULT_URL, RECOMMENDED_MODELS, OllamaProvider
from nxceviri.gui.icons import icon
from nxceviri.gui.shortcuts import (
    CATEGORIES,
    COMMANDS,
    COMMANDS_BY_ID,
    ShortcutRegistry,
    display_text,
    reserved_reason,
)
from nxceviri.gui.theme import FONT_SIZES, THEME_LABELS, ThemeMode, clamp_font_size
from nxceviri.gui.update_dialog import AUTO_CHECK_KEY, auto_check_enabled
from nxceviri.gui.view_actions import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, PANE_BOTTOM, PANE_RIGHT, ViewActions
from nxceviri.gui.widgets import Banner, button, label

PAGE_VIEW = "view"
PAGE_SHORTCUTS = "shortcuts"
PAGE_LIVE = "live"
PAGE_PROVIDERS = "providers"
PAGE_UPDATES = "updates"

#: Sayfalar: (kimlik, listedeki ad, simge adı). Sıra, listedeki ve yığındaki sıradır.
_PAGES = (
    (PAGE_VIEW, "Görünüm", "palette"),
    (PAGE_SHORTCUTS, "Kısayollar", "keyboard"),
    (PAGE_LIVE, "Anlık Denetimler", "shield-check"),
    (PAGE_PROVIDERS, "Çeviri", "sparkles"),
    (PAGE_UPDATES, "Güncelleme", "refresh-cw"),
)

KEY_OLLAMA_URL = "ollama/url"
KEY_OLLAMA_MODEL = "ollama/model"

_ALIGN_LABELS = ((ALIGN_LEFT, "Sola"), (ALIGN_CENTER, "Ortaya"), (ALIGN_RIGHT, "Sağa"))
_PANE_LABELS = ((PANE_BOTTOM, "Altta"), (PANE_RIGHT, "Sağda"))
_ROLE_COMMAND = Qt.ItemDataRole.UserRole


def check_with_wait_cursor(provider: TranslationProvider) -> ProviderStatus:
    """Sağlayıcının bağlantısını bekleme imleciyle sınar ve sağlayıcıyı kapatır."""
    QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        return provider.test_connection()
    finally:
        QGuiApplication.restoreOverrideCursor()
        provider.close()


def valid_ollama_url(text: str) -> str | None:
    """Ollama adresi geçerliyse (http/https, ana makine adı, varsa sayısal bağlantı noktası, boşluksuz) kırpılmış
    hâli, değilse None."""
    value = text.strip()
    if any(ch.isspace() or ord(ch) < 32 for ch in value):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        _port = parts.port  # geçersiz ya da aralık dışı bağlantı noktası ValueError verir
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host:
        return None
    return value


def _confirm(parent: QWidget, text: str, info: str, accept_label: str) -> bool:
    """Evet/vazgeç sorusu; varsayılan düğme "Vazgeç"tir. Onaylanırsa True."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Ayarlar")
    box.setText(text)
    box.setInformativeText(info)
    accept = box.addButton(accept_label, QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton("Vazgeç", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    box.exec()
    return box.clickedButton() is accept


class DeepLKeyPanel(QWidget):
    """DeepL API anahtarı: kaydet, sil, bağlantıyı sına (anahtar Windows Kimlik Bilgisi Yöneticisi'nde durur)."""

    def __init__(self, secrets: SecretStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._secrets = secrets
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(
            label(
                "DeepL hesabınızdan kopyaladığınız API anahtarı.",
                "muted",
                wrap=True,
                tip="Anahtarı DeepL hesabınızdan (Hesap → API Anahtarları) kopyalayın. Windows Kimlik Bilgisi "
                "Yöneticisi'nde saklanır. Free anahtarlar “:fx” ile biter; Free/Pro adresi otomatik seçilir.",
            )
        )
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Yeni anahtarı buraya yapıştırın")
        lay.addWidget(self.key)
        self.state = label("")
        lay.addWidget(self.state)
        row = QHBoxLayout()
        self.save = button("Anahtarı Kaydet", "primary")
        self.save.clicked.connect(self._save_and_test)
        self.remove = button("Kayıtlı Anahtarı Sil")
        self.remove.clicked.connect(self.delete_key)
        self.test = button("Bağlantıyı Test Et")
        self.test.clicked.connect(self.test_key)
        row.addWidget(self.save)
        row.addWidget(self.remove)
        row.addWidget(self.test)
        row.addStretch(1)
        lay.addLayout(row)
        self.status = Banner()
        lay.addWidget(self.status)
        self.refresh()

    def _stored(self) -> str | None:
        try:
            return self._secrets.get(DEEPL_API_KEY)
        except NxError as exc:
            self.status.show_message("danger", exc.user_text())
            return None

    def refresh(self) -> None:
        stored = self._stored()
        self.state.setText(f"Kayıtlı anahtar: var ({plan_label(stored)})" if stored else "Kayıtlı anahtar: yok")
        self.remove.setEnabled(bool(stored))
        self.test.setEnabled(bool(stored))

    def save_key(self) -> bool:
        """Alandaki anahtarı gizli depoya yazar; yazıldıysa True."""
        value = self.key.text().strip()
        if not value:
            self.status.show_message("warning", "Önce anahtarı alana yapıştırın.")
            return False
        try:
            self._secrets.set(DEEPL_API_KEY, value)
        except NxError as exc:
            self.status.show_message("danger", exc.user_text())
            return False
        self.key.clear()
        self.refresh()
        return True

    def _save_and_test(self) -> None:
        if self.save_key():
            self.test_key()

    def delete_key(self) -> None:
        try:
            self._secrets.delete(DEEPL_API_KEY)
        except NxError as exc:
            self.status.show_message("danger", exc.user_text())
            return
        self.status.show_message("success", "Kayıtlı DeepL anahtarı silindi.")
        self.refresh()

    def test_key(self) -> None:
        stored = self._stored()
        if not stored:
            return
        try:
            provider = DeepLProvider(stored)
        except ProviderError as exc:
            self.status.show_message("danger", exc.user_text())
            return
        status = check_with_wait_cursor(provider)
        self.status.show_message("success" if status.ok else "danger", status.message)


class _SingleKeyEdit(QKeySequenceEdit):
    """Tek tuş kombinasyonu kaydeder; Esc kaydetmez, pencereyi kapatır (vazgeç)."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            dialog = self.window()
            if isinstance(dialog, QDialog):
                dialog.reject()
                return
        super().keyPressEvent(event)


class KeyEntryDialog(QDialog):
    """Bir komut için yeni tuş kombinasyonunu yakalar. Tuşa basınca kabul eder, Esc vazgeçer."""

    def __init__(self, parent: QWidget | None, command_label: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kısayol Ata")
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        lay.addWidget(label(f"“{command_label}” için yeni kısayola basın.", wrap=True))
        self.editor = _SingleKeyEdit()
        self.editor.setClearButtonEnabled(True)
        self.editor.editingFinished.connect(self._finished)
        lay.addWidget(self.editor)
        lay.addWidget(label("Vazgeçmek için Esc tuşuna basın.", "muted"))
        row = QHBoxLayout()
        self.ok = button("Ata", "primary")
        self.ok.setEnabled(False)  # tuş yazılmadan "Ata" kısayolu sessizce silmesin
        self.ok.clicked.connect(self.accept)
        self.editor.keySequenceChanged.connect(lambda _seq: self.ok.setEnabled(not self.sequence().isEmpty()))
        cancel = button("Vazgeç", icon="x")
        cancel.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(self.ok)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _finished(self) -> None:
        if not self.sequence().isEmpty():
            self.accept()

    def sequence(self) -> QKeySequence:
        """Yazılan kombinasyon; birden çok adımlı dizide yalnızca ilki alınır."""
        seq = self.editor.keySequence()
        # PySide6 çalışma anında QKeySequence[i] verir (QKeyCombination); tür taslaklarında yok.
        return QKeySequence(seq[0]) if seq.count() else QKeySequence()  # type: ignore[index]


def _scrolled(content: QWidget) -> QScrollArea:
    """Sayfa içeriğini kaydırılabilir yapar (küçük pencerede ve büyük yazıda taşmasın)."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(content)
    return area


def _page_layout() -> tuple[QWidget, QVBoxLayout]:
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(12, 4, 12, 4)
    lay.setSpacing(12)
    return page, lay


class SettingsDialog(QDialog):
    theme_changed = Signal(object)  # ThemeMode
    font_size_changed = Signal(int)
    check_updates_requested = Signal()
    live_kinds_changed = Signal(list)  # seçili türler, gösterim sırasıyla; yazmak ve uygulamak pencereyi açanın işidir

    def __init__(
        self,
        parent: QWidget | None,
        settings: QSettings,
        registry: ShortcutRegistry,
        view: ViewActions,
        secrets: SecretStore,
        *,
        theme: ThemeMode,
        font_size: int,
        wrap: QAction,
        issue_colors: QAction,
        error_rows: QAction,
        updates_available: bool,
        live_kinds: Collection[str] = DEFAULT_LIVE_KINDS,
        page: str = PAGE_VIEW,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ayarlar")
        self.setMinimumSize(720, 480)
        self.resize(800, 540)
        self._settings = settings
        self._registry = registry
        self._view = view
        self._secrets = secrets

        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        self.pages = QListWidget()
        self.pages.setFixedWidth(190)
        self.pages.setIconSize(QSize(18, 18))
        self.pages.setFrameShape(QFrame.Shape.NoFrame)
        self.stack = QStackedWidget()
        body.addWidget(self.pages)
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.close_button = button("Kapat", "primary")
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        outer.addLayout(footer)

        self.view_page = _scrolled(self._build_view_page(theme, font_size, wrap, issue_colors, error_rows))
        self.shortcuts_page = self._build_shortcuts_page()
        self.live_page = _scrolled(self._build_live_page(live_kinds))
        self.providers_page = _scrolled(self._build_providers_page())
        self.updates_page = _scrolled(self._build_updates_page(updates_available))
        widgets = {
            PAGE_VIEW: self.view_page,
            PAGE_SHORTCUTS: self.shortcuts_page,
            PAGE_LIVE: self.live_page,
            PAGE_PROVIDERS: self.providers_page,
            PAGE_UPDATES: self.updates_page,
        }
        for page_id, text, _icon_name in _PAGES:
            self.pages.addItem(QListWidgetItem(text))
            self.stack.addWidget(widgets[page_id])
        self._refresh_page_icons()
        self.pages.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.pages.setCurrentRow(0)
        self.show_page(page)

    # --- sayfalar ------------------------------------------------------------------------

    @property
    def current_page(self) -> str:
        return _PAGES[max(self.stack.currentIndex(), 0)][0]

    def show_page(self, page: str) -> None:
        for row, (page_id, _text, _icon_name) in enumerate(_PAGES):
            if page_id == page:
                self.pages.setCurrentRow(row)
                return

    def _refresh_page_icons(self) -> None:
        for row, (_page_id, _text, icon_name) in enumerate(_PAGES):
            self.pages.item(row).setIcon(icon(icon_name))

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and self.pages.count() == len(_PAGES):
            self._refresh_page_icons()  # tema değişince sayfa simgeleri yeni renkle çizilir

    # --- görünüm -------------------------------------------------------------------------

    def _build_view_page(
        self, theme: ThemeMode, font_size: int, wrap: QAction, issue_colors: QAction, error_rows: QAction
    ) -> QWidget:
        page, lay = _page_layout()
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.theme_combo = QComboBox()
        for mode, text in THEME_LABELS.items():
            self.theme_combo.addItem(text, mode)
        self.theme_combo.setCurrentIndex(max(self.theme_combo.findData(theme), 0))
        self.theme_combo.currentIndexChanged.connect(self._on_theme)
        form.addRow("Tema:", self.theme_combo)

        self.font_combo = QComboBox()
        for size in FONT_SIZES:
            self.font_combo.addItem(f"{size} pt", size)
        self.font_combo.setCurrentIndex(max(self.font_combo.findData(clamp_font_size(font_size)), 0))
        self.font_combo.currentIndexChanged.connect(self._on_font_size)
        form.addRow("Yazı boyutu:", self.font_combo)

        self.align_combo = QComboBox()
        for key, text in _ALIGN_LABELS:
            self.align_combo.addItem(text, key)
        self.align_combo.setCurrentIndex(max(self.align_combo.findData(self._view.align), 0))
        self.align_combo.currentIndexChanged.connect(self._on_align)
        self._view.align_changed.connect(self._show_align)
        form.addRow("Metin hizası:", self.align_combo)

        self.pane_combo = QComboBox()
        for key, text in _PANE_LABELS:
            self.pane_combo.addItem(text, key)
        self.pane_combo.setCurrentIndex(max(self.pane_combo.findData(self._view.pane), 0))
        self.pane_combo.currentIndexChanged.connect(self._on_pane)
        self._view.pane_changed.connect(self._show_pane)
        form.addRow("Çeviri paneli:", self.pane_combo)
        lay.addLayout(form)

        self.symbols_check = self._linked_check("Boşluk ve satır sonu sembollerini göster", self._view.symbols)
        self.wrap_check = self._linked_check("Uzun metni satırlara kaydır", wrap)
        self.issue_check = self._linked_check("Sorunlu satırları renkle göster", issue_colors)
        self.error_rows_check = self._linked_check("Hatalı satırların arka planını hata rengine boya", error_rows)
        for check in (self.symbols_check, self.wrap_check, self.issue_check, self.error_rows_check):
            lay.addWidget(check)
        lay.addStretch(1)
        return page

    def _linked_check(self, text: str, action: QAction) -> QCheckBox:
        """Onay kutusu ile eylemi iki yönlü eşler (aynı değerde sinyal yayılmadığı için döngü olmaz)."""
        check = QCheckBox(text)
        check.setChecked(action.isChecked())
        check.toggled.connect(action.setChecked)
        action.toggled.connect(check.setChecked)
        return check

    def _on_theme(self) -> None:
        self.theme_changed.emit(ThemeMode(str(self.theme_combo.currentData())))

    def _on_font_size(self) -> None:
        self.font_size_changed.emit(int(self.font_combo.currentData()))

    def _on_align(self) -> None:
        self._view.align_actions[str(self.align_combo.currentData())].trigger()

    def _show_align(self, key: str) -> None:
        self.align_combo.setCurrentIndex(max(self.align_combo.findData(key), 0))

    def _on_pane(self) -> None:
        self._view.pane_actions[str(self.pane_combo.currentData())].trigger()

    def _show_pane(self, key: str) -> None:
        self.pane_combo.setCurrentIndex(max(self.pane_combo.findData(key), 0))

    # --- kısayollar ----------------------------------------------------------------------

    def _build_shortcuts_page(self) -> QWidget:
        page, lay = _page_layout()
        self.shortcut_search = QLineEdit()
        self.shortcut_search.setPlaceholderText("Komut ya da kısayol ara")
        self.shortcut_search.setClearButtonEnabled(True)
        self.shortcut_search.textChanged.connect(self._filter_shortcuts)
        lay.addWidget(self.shortcut_search)

        self.shortcut_tree = QTreeWidget()
        self.shortcut_tree.setColumnCount(2)
        self.shortcut_tree.setHeaderLabels(["Komut", "Kısayol"])
        self.shortcut_tree.setRootIsDecorated(True)
        self.shortcut_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.shortcut_tree.setUniformRowHeights(True)
        self.shortcut_tree.header().setStretchLastSection(False)
        self.shortcut_tree.header().setSectionResizeMode(0, self.shortcut_tree.header().ResizeMode.Stretch)
        self.shortcut_tree.header().setSectionResizeMode(1, self.shortcut_tree.header().ResizeMode.ResizeToContents)
        self._shortcut_items: dict[str, QTreeWidgetItem] = {}
        for category in CATEGORIES:
            parent_item = QTreeWidgetItem([category])
            self.shortcut_tree.addTopLevelItem(parent_item)
            for command in (c for c in COMMANDS if c.category == category):
                child = QTreeWidgetItem([command.label, ""])
                child.setData(0, _ROLE_COMMAND, command.id)
                parent_item.addChild(child)
                self._shortcut_items[command.id] = child
            parent_item.setExpanded(True)
        for command_id in self._shortcut_items:
            self._paint_shortcut_item(command_id)
        self.shortcut_tree.currentItemChanged.connect(self._update_shortcut_buttons)
        self.shortcut_tree.itemDoubleClicked.connect(lambda _item, _column: self.change_selected())
        lay.addWidget(self.shortcut_tree, 1)

        row = QHBoxLayout()
        self.change_button = button("Değiştir…", "primary", icon="keyboard")
        self.change_button.clicked.connect(self.change_selected)
        self.remove_button = button("Kısayolu Kaldır")
        self.remove_button.clicked.connect(self.remove_selected)
        self.reset_button = button("Varsayılana Dön")
        self.reset_button.clicked.connect(self.reset_selected)
        self.reset_all_button = button("Tümünü Varsayılana Döndür")
        self.reset_all_button.clicked.connect(self.reset_all)
        for b in (self.change_button, self.remove_button, self.reset_button):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        reset_all_row = QHBoxLayout()  # dar pencerede dört düğme sığmaz: toplu sıfırlama ayrı satırda
        reset_all_row.addStretch(1)
        reset_all_row.addWidget(self.reset_all_button)
        lay.addLayout(reset_all_row)
        self._registry.changed.connect(self._refresh_shortcut_item)
        self._update_shortcut_buttons()
        return page

    def shortcut_item(self, command_id: str) -> QTreeWidgetItem | None:
        return self._shortcut_items.get(command_id)

    def _selected_command(self) -> str | None:
        item = self.shortcut_tree.currentItem()
        if item is None:
            return None
        command_id = item.data(0, _ROLE_COMMAND)
        return str(command_id) if command_id else None

    def _refresh_shortcut_item(self, command_id: str) -> None:
        self._paint_shortcut_item(command_id)
        self._update_shortcut_buttons()

    def _paint_shortcut_item(self, command_id: str) -> None:
        item = self._shortcut_items.get(command_id)
        if item is None:
            return
        item.setText(1, self._registry.text(command_id))
        custom = self._registry.is_custom(command_id)
        for column in (0, 1):
            font = QFont(item.font(column))
            font.setBold(custom)
            item.setFont(column, font)

    def _update_shortcut_buttons(self) -> None:
        command_id = self._selected_command()
        self.change_button.setEnabled(command_id is not None)
        self.remove_button.setEnabled(command_id is not None and not self._registry.sequence(command_id).isEmpty())
        self.reset_button.setEnabled(command_id is not None and self._registry.is_custom(command_id))
        self.reset_all_button.setEnabled(any(self._registry.is_custom(c.id) for c in COMMANDS))

    def _filter_shortcuts(self, text: str) -> None:
        query = text.strip().casefold()
        for category_index in range(self.shortcut_tree.topLevelItemCount()):
            category = self.shortcut_tree.topLevelItem(category_index)
            if category is None:
                continue
            visible = 0
            for child_index in range(category.childCount()):
                child = category.child(child_index)
                if child is None:
                    continue
                hit = not query or query in f"{child.text(0)} {child.text(1)} {category.text(0)}".casefold()
                child.setHidden(not hit)
                visible += int(hit)
            category.setHidden(visible == 0)
            category.setExpanded(True)

    def ask_sequence(self, command_id: str) -> QKeySequence | None:
        """Kullanıcıdan yeni tuşu ister; vazgeçilirse None."""
        dialog = KeyEntryDialog(self, COMMANDS_BY_ID[command_id].label)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.sequence()

    def change_selected(self) -> None:
        command_id = self._selected_command()
        if command_id is None:
            return
        seq = self.ask_sequence(command_id)
        if seq is not None:
            self.assign_shortcut(command_id, seq)

    def assign_shortcut(self, command_id: str, seq: QKeySequence) -> bool:
        """Tuşu atar. Ayrılmış tuşlar reddedilir. Başka komutla çakışırsa sorar ("Yine de ata" ötekini kısayolsuz
        bırakır). Atandıysa True."""
        reserved = reserved_reason(seq)
        if reserved is not None:
            QMessageBox.warning(self, "Ayarlar", f"Bu tuş uygulamada ayrılmış: {display_text(seq)} {reserved}.")
            return False
        clashes = self._registry.conflicts(command_id, seq)
        if clashes:
            names = ", ".join(f"“{c.label}”" for c in clashes)
            others = "öteki komutlar" if len(clashes) > 1 else f"“{clashes[0].label}”"
            if not _confirm(
                self,
                f"“{display_text(seq)}” zaten {names} için kullanılıyor.",
                f"Yine de atarsanız {others} kısayolsuz kalır.",
                "Yine de ata",
            ):
                return False
            for clash in clashes:
                self._registry.set_sequence(clash.id, QKeySequence())
        self._registry.set_sequence(command_id, seq)
        return True

    def remove_selected(self) -> None:
        command_id = self._selected_command()
        if command_id is not None:
            self._registry.set_sequence(command_id, QKeySequence())

    def reset_selected(self) -> None:
        command_id = self._selected_command()
        if command_id is not None:
            self.assign_shortcut(command_id, QKeySequence(COMMANDS_BY_ID[command_id].default))

    def reset_all(self) -> None:
        if _confirm(
            self,
            "Tüm kısayollar varsayılana döndürülsün mü?",
            "Değiştirdiğiniz ve kaldırdığınız kısayolların hepsi eski hâline gelir.",
            "Tümünü Döndür",
        ):
            self._registry.reset_all()

    # --- anlık denetimler ----------------------------------------------------------------

    def _build_live_page(self, live_kinds: Collection[str]) -> QWidget:
        page, lay = _page_layout()
        lay.addWidget(
            label(
                "Çeviri tablosunda satırlar yazılırken hangi sorunların hemen gösterileceği. "
                "Kapalı türler yine de Kontrol Et'te bulunur.",
                "muted",
                wrap=True,
            )
        )
        row = QHBoxLayout()
        self.live_all = button("Tümü")
        self.live_all.clicked.connect(lambda: self._set_all_live(True))
        self.live_none = button("Hiçbiri")
        self.live_none.clicked.connect(lambda: self._set_all_live(False))
        row.addWidget(self.live_all)
        row.addWidget(self.live_none)
        row.addStretch(1)
        lay.addLayout(row)
        chosen = set(live_kinds)
        self.live_checks: dict[str, QCheckBox] = {}
        for kind in LIVE_KINDS:
            box = QCheckBox(KIND_LABELS[kind])
            box.setToolTip(KIND_HINTS[kind])
            box.setChecked(kind in chosen)
            box.toggled.connect(self._emit_live_kinds)
            self.live_checks[kind] = box
            lay.addWidget(box)
            lay.addWidget(label(KIND_HINTS[kind], "muted", wrap=True))
        lay.addStretch(1)
        return page

    def _chosen_live_kinds(self) -> list[str]:
        return [k for k in LIVE_KINDS if self.live_checks[k].isChecked()]

    def _emit_live_kinds(self) -> None:
        self.live_kinds_changed.emit(self._chosen_live_kinds())

    def _set_all_live(self, on: bool) -> None:
        for box in self.live_checks.values():
            box.blockSignals(True)
            box.setChecked(on)
            box.blockSignals(False)
        self._emit_live_kinds()

    # --- çeviri sağlayıcıları ------------------------------------------------------------

    def _build_providers_page(self) -> QWidget:
        page, lay = _page_layout()
        lay.addWidget(label("Ollama (yerel)", "cardTitle"))
        lay.addWidget(
            label(
                "Metinler bilgisayarınızdan çıkmaz. Model, çeviri başlarken seçilir.",
                "muted",
                wrap=True,
            )
        )
        form = QFormLayout()
        self.ollama_url = QLineEdit(str(self._settings.value(KEY_OLLAMA_URL, DEFAULT_URL)) or DEFAULT_URL)
        self.ollama_url.editingFinished.connect(self._commit_ollama_url)
        form.addRow("Adres:", self.ollama_url)
        lay.addLayout(form)
        row = QHBoxLayout()
        self.ollama_test = button("Bağlantıyı Test Et", icon="refresh-cw")
        self.ollama_test.clicked.connect(self.test_ollama)
        row.addWidget(self.ollama_test)
        row.addStretch(1)
        lay.addLayout(row)
        self.ollama_status = Banner()
        lay.addWidget(self.ollama_status)

        lay.addSpacing(8)
        lay.addWidget(label("DeepL (bulut)", "cardTitle"))
        self.deepl_panel = DeepLKeyPanel(self._secrets)
        lay.addWidget(self.deepl_panel)
        lay.addStretch(1)
        return page

    def _saved_ollama_url(self) -> str:
        return str(self._settings.value(KEY_OLLAMA_URL, DEFAULT_URL)) or DEFAULT_URL

    def _commit_ollama_url(self) -> bool:
        """Alandaki adres geçerliyse ayara yazar; değilse uyarır ve alanı kayıtlı adrese geri döndürür."""
        url = valid_ollama_url(self.ollama_url.text())
        if url is None:
            self.ollama_url.setText(self._saved_ollama_url())
            self.ollama_status.show_message(
                "warning", f"Geçerli bir adres yazın, örneğin {DEFAULT_URL}. Eski adres korundu."
            )
            return False
        self._settings.setValue(KEY_OLLAMA_URL, url)
        return True

    def test_ollama(self) -> None:
        if not self._commit_ollama_url():
            return
        url = self._saved_ollama_url()
        model = str(self._settings.value(KEY_OLLAMA_MODEL, "")).strip()
        provider = OllamaProvider(model, url, timeout_s=15)
        status = check_with_wait_cursor(provider) if model else self._list_models_status(provider)
        self.ollama_status.show_message("success" if status.ok else "danger", status.message)

    def _list_models_status(self, provider: OllamaProvider) -> ProviderStatus:
        """Model henüz seçilmediyse bağlantı, yüklü modellerin listelenmesiyle sınanır."""
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            models = [m for m in provider.list_models() if m.can_chat]
        except ProviderError as exc:
            return ProviderStatus(False, exc.user_text())
        finally:
            QGuiApplication.restoreOverrideCursor()
            provider.close()
        if not models:
            return ProviderStatus(
                False,
                "Ollama çalışıyor ama çeviri yapabilecek model yüklü değil. "
                f"Önerilenlerden birini indirin, ör. `ollama pull {RECOMMENDED_MODELS[0][0]}`.",
            )
        return ProviderStatus(True, f"Ollama'ya bağlanıldı, {len(models)} model bulundu.")

    # --- güncelleme ----------------------------------------------------------------------

    def _build_updates_page(self, available: bool) -> QWidget:
        page, lay = _page_layout()
        self.auto_check = QCheckBox("Açılışta güncellemeleri denetle")
        self.auto_check.setChecked(auto_check_enabled(self._settings))
        self.auto_check.toggled.connect(lambda on: self._settings.setValue(AUTO_CHECK_KEY, "true" if on else "false"))
        lay.addWidget(self.auto_check)
        row = QHBoxLayout()
        self.check_now = button("Şimdi Denetle", icon="refresh-cw")
        self.check_now.clicked.connect(self.check_updates_requested)
        if not available:
            self.check_now.setEnabled(False)
            self.check_now.setToolTip(
                "Bu kurulum ne paketlenmiş uygulama ne de kaynak klasör; güncelleme denetlenemez."
            )
        row.addWidget(self.check_now)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return page
