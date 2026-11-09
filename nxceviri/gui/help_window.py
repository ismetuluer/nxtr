"""Uygulama içi Yardım (F1): aranabilir konu listesi ve konu metni.

Konular `gui/help/NN-ad.md` dosyalarıdır (ilk satır `# Başlık`); kullanıcı için, ekran adlarıyla yazılır. "Kısayollar"
konusu dosya değildir: o anki tuşlardan üretilir, kullanıcı tuş değiştirince güncel kalır. `F1` açık ekranın konusunu
açar (`STEP_TOPICS`). Arama Türkçe büyük/küçük harf farkını gözetmez (İ/i, I/ı); eşleşmeyen konular listeden gizlenir,
açık konudaki eşleşmeler boyanır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.spell.checker import turkish_lower
from nxceviri.gui.shortcuts import CATEGORIES, COMMANDS, ShortcutRegistry, fixed_keys
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import label

TOPIC_DIR = Path(__file__).with_name("help")
TOPIC_START = "01-baslarken"
TOPIC_SHORTCUTS = "11-kisayollar"
#: Ana penceredeki adım (kenar çubuğu satırı) → F1'in açacağı konu.
STEP_TOPICS = {0: "02-oyunu-ekle", 1: "03-metinleri-tara", 2: "04-cevir", 3: "07-kontrol-et", 4: "09-disa-aktar"}
#: Kısayol listesinde gösterilmeyen, herkesin bildiği yazma tuşları.
_OBVIOUS_KEYS = frozenset(
    {"Return", "Enter", "Tab", "Backtab", "Backspace", "Delete", "Space", "Ctrl+Insert", "Shift+Insert", "Shift+Delete"}
)


@dataclass(frozen=True)
class HelpTopic:
    slug: str
    title: str
    markdown: str


def _title_of(markdown: str, fallback: str) -> str:
    first = markdown.lstrip().splitlines()[0] if markdown.strip() else ""
    return first[2:].strip() if first.startswith("# ") else fallback


def shortcuts_markdown(registry: ShortcutRegistry | None) -> str:
    """O anki tuşlarla "Kısayollar" konusu (atanmamış komutlar listelenmez)."""
    lines = [
        "# Kısayollar",
        "",
        "Tuşları **Ayarlar → Kısayollar**'dan değiştirebilirsiniz; bu liste o anki tuşları gösterir.",
        "",
    ]
    for category in CATEGORIES:
        rows = []
        for command in COMMANDS:
            if command.category != category:
                continue
            key = registry.text(command.id) if registry is not None else command.default
            if key:
                rows.append(f"| {command.label} | `{key}` |")
        if rows:
            lines += [f"## {category}", "", "| Komut | Tuş |", "|---|---|", *rows, ""]
    fixed = [
        f"| {what[:1].upper() + what[1:]} | `{key}` |" for key, what in fixed_keys().items() if key not in _OBVIOUS_KEYS
    ]
    lines += ["## Sabit tuşlar", "", "| Ne yapar | Tuş |", "|---|---|", *fixed, ""]
    return "\n".join(lines)


def load_topics(registry: ShortcutRegistry | None = None) -> list[HelpTopic]:
    """Konular dosya adı sırasıyla; "Kısayollar" kendi sırasına üretilerek eklenir."""
    topics = []
    for path in sorted(TOPIC_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        topics.append(HelpTopic(path.stem, _title_of(text, path.stem), text))
    topics.append(HelpTopic(TOPIC_SHORTCUTS, "Kısayollar", shortcuts_markdown(registry)))
    return sorted(topics, key=lambda t: t.slug)


def match_count(topic: HelpTopic, query: str) -> int:
    """Konuda sorgunun kaç kez geçtiği (Türkçe büyük/küçük harf farkı gözetilmez; başlıktaki eşleşme önce gelir)."""
    needle = turkish_lower(query.strip())
    if not needle:
        return 0
    return turkish_lower(topic.markdown).count(needle) + (100 if needle in turkish_lower(topic.title) else 0)


class HelpWindow(QWidget):
    """Yardım penceresi: solda arama ve konular, sağda metin. Ana pencereden bağımsız taşınır ve açık kalabilir."""

    def __init__(self, registry: ShortcutRegistry | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Yardım — NXTR")
        self.setObjectName("helpWindow")
        self.resize(920, 620)
        self._registry = registry
        self.topics = load_topics(registry)
        if registry is not None:
            registry.changed.connect(lambda _command: self._refresh_shortcuts())

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        split = QSplitter()
        lay.addWidget(split)

        left = QWidget()
        side = QVBoxLayout(left)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Yardımda ara…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._open_first_visible)
        side.addWidget(self.search)
        self.result_label = label("", "muted")
        self.result_label.hide()
        side.addWidget(self.result_label)
        self.topic_list = QListWidget()
        self.topic_list.setSpacing(3)
        for topic in self.topics:
            item = QListWidgetItem(topic.title)
            item.setData(Qt.ItemDataRole.UserRole, topic.slug)
            self.topic_list.addItem(item)
        self.topic_list.currentItemChanged.connect(lambda item, _prev: self._show_item(item))
        side.addWidget(self.topic_list, 1)
        split.addWidget(left)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.document().setDocumentMargin(16)
        split.addWidget(self.browser)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 680])
        self.show_topic(TOPIC_START)

    # --- konu ------------------------------------------------------------------------------

    @property
    def current_slug(self) -> str | None:
        item = self.topic_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def show_topic(self, slug: str) -> None:
        for row in range(self.topic_list.count()):
            item = self.topic_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == slug:
                item.setHidden(False)
                self.topic_list.setCurrentItem(item)
                self._show_item(item)
                return

    def _topic(self, slug: str) -> HelpTopic | None:
        return next((t for t in self.topics if t.slug == slug), None)

    def _show_item(self, item: QListWidgetItem | None) -> None:
        topic = self._topic(str(item.data(Qt.ItemDataRole.UserRole))) if item is not None else None
        if topic is None:
            return
        self.browser.setMarkdown(topic.markdown)
        self._highlight()

    def _refresh_shortcuts(self) -> None:
        self.topics = [
            HelpTopic(t.slug, t.title, shortcuts_markdown(self._registry)) if t.slug == TOPIC_SHORTCUTS else t
            for t in self.topics
        ]
        if self.current_slug == TOPIC_SHORTCUTS:
            self.show_topic(TOPIC_SHORTCUTS)

    # --- arama -----------------------------------------------------------------------------

    def _filter(self, query: str) -> None:
        query = query.strip()
        visible = 0
        best: tuple[int, int] | None = None  # (eşleşme, satır)
        for row in range(self.topic_list.count()):
            item = self.topic_list.item(row)
            topic = self._topic(str(item.data(Qt.ItemDataRole.UserRole)))
            hits = match_count(topic, query) if topic is not None and query else 0
            item.setHidden(bool(query) and hits == 0)
            if not item.isHidden():
                visible += 1
            if hits and (best is None or hits > best[0]):
                best = (hits, row)
        self.result_label.setVisible(bool(query))
        self.result_label.setText(f"{visible} konuda bulundu" if visible else "Bulunamadı")
        current = self.topic_list.currentItem()
        if best is not None and (current is None or current.isHidden()):
            self.topic_list.setCurrentRow(best[1])
        self._highlight()

    def _open_first_visible(self) -> None:
        for row in range(self.topic_list.count()):
            if not self.topic_list.item(row).isHidden():
                self.topic_list.setCurrentRow(row)
                self.browser.setFocus()
                return

    def _highlight(self) -> None:
        """Açık konudaki eşleşmeleri boyar ve ilkine kaydırır."""
        needle = turkish_lower(self.search.text().strip())
        selections: list[QTextEdit.ExtraSelection] = []
        if needle:
            text = turkish_lower(self.browser.toPlainText())
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(current_tokens()["warning"]))
            fmt.setForeground(QColor("#000000"))
            start = text.find(needle)
            while start >= 0:
                cursor = QTextCursor(self.browser.document())
                cursor.setPosition(start)
                cursor.setPosition(start + len(needle), QTextCursor.MoveMode.KeepAnchor)
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format = fmt
                selections.append(selection)
                start = text.find(needle, start + len(needle))
        self.browser.setExtraSelections(selections)
        if selections:
            self.browser.setTextCursor(selections[0].cursor)
            self.browser.ensureCursorVisible()

    @property
    def highlight_count(self) -> int:
        return len(self.browser.extraSelections())
