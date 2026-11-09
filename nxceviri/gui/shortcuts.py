"""Klavye kısayollarının tek kaynağı: komut kataloğu ve kullanıcının değiştirdiği tuşlar.

Her komutun sabit bir kimliği (`"translate.auto"`), Kısayollar listesinde görünen adı, kategorisi ve varsayılan
tuşu vardır. Eylemler (`QAction`) ve sayfa kısayolları (`QShortcut`) tuşlarını kendileri yazmaz; `bind` ile kayıt
defterine bağlanır. Kullanıcı Ayarlar → Kısayollar'dan tuşu değiştirince bağlı her nesne ve ipucu hemen güncellenir.

Kullanıcının seçtiği tuşlar `QSettings`te `shortcuts/<kimlik>` altında saklanır (uygulama ayarı, proje başına değil).
Varsayılana dönen komutun kaydı silinir; "kısayolsuz" bırakılan komut boş metinle saklanır. Tanınmayan ya da bozuk
değer varsayılana döner ve günlüğe uyarı yazılır.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut

log = logging.getLogger(__name__)

KEY_PREFIX = "shortcuts/"

CATEGORY_FILE = "Dosya"
CATEGORY_EDIT = "Düzen"
CATEGORY_VIEW = "Görünüm"
CATEGORY_TRANSLATE = "Çeviri"
CATEGORY_GO = "Git"
CATEGORY_TOOLS = "Araçlar"
CATEGORIES = (CATEGORY_FILE, CATEGORY_EDIT, CATEGORY_VIEW, CATEGORY_TRANSLATE, CATEGORY_GO, CATEGORY_TOOLS)


@dataclass(frozen=True)
class Command:
    """Kısayol atanabilen bir komut. `default`: `QKeySequence` taşınabilir metni; boşsa kısayolsuz başlar."""

    id: str
    label: str
    category: str
    default: str = ""


COMMANDS: tuple[Command, ...] = (
    # Dosya
    Command("file.new", "Yeni Proje", CATEGORY_FILE, "Ctrl+N"),
    Command("file.open", "Proje Aç", CATEGORY_FILE, "Ctrl+O"),
    Command("file.save", "Kaydet", CATEGORY_FILE, "Ctrl+S"),
    Command("file.save_as", "Farklı Kaydet", CATEGORY_FILE, "Ctrl+Shift+S"),
    Command("app.settings", "Ayarlar", CATEGORY_FILE, "Ctrl+,"),
    Command("app.quit", "Çıkış", CATEGORY_FILE, "Ctrl+Q"),
    # Düzen
    Command("edit.undo", "Geri Al", CATEGORY_EDIT, "Ctrl+Z"),
    Command("edit.find", "Bul", CATEGORY_EDIT, "Ctrl+F"),
    Command("edit.replace", "Değiştir", CATEGORY_EDIT, "Ctrl+H"),
    Command("edit.filter", "Tabloyu Süz", CATEGORY_EDIT, "Ctrl+Shift+F"),
    Command("edit.find_next", "Sonrakini Bul", CATEGORY_EDIT, "F3"),
    Command("edit.find_prev", "Öncekini Bul", CATEGORY_EDIT, "Shift+F3"),
    Command("edit.reflow", "Satırları Yeniden Böl", CATEGORY_EDIT, "Ctrl+Shift+B"),
    Command("edit.copy_source", "Orijinali Çeviri Olarak Yaz", CATEGORY_EDIT, "Ctrl+Shift+O"),
    Command("edit.clear", "Çeviriyi Temizle", CATEGORY_EDIT),
    # Görünüm
    Command("view.nav", "Kenar Çubuğu", CATEGORY_VIEW, "Ctrl+Alt+S"),
    Command("view.pane", "Çeviri Paneli", CATEGORY_VIEW, "Ctrl+J"),
    Command("view.pane_bottom", "Paneli Altta Göster", CATEGORY_VIEW, "Ctrl+Alt+B"),
    Command("view.pane_right", "Paneli Sağda Göster", CATEGORY_VIEW, "Ctrl+Alt+R"),
    Command("view.symbols", "Sembolleri Göster", CATEGORY_VIEW, "Ctrl+Shift+8"),
    Command("view.align_left", "Sola Hizala", CATEGORY_VIEW, "Ctrl+Shift+L"),
    Command("view.align_center", "Ortaya Hizala", CATEGORY_VIEW, "Ctrl+Shift+E"),
    Command("view.align_right", "Sağa Hizala", CATEGORY_VIEW, "Ctrl+Shift+R"),
    Command("view.wrap", "Metni Kaydır", CATEGORY_VIEW),
    Command("view.issue_colors", "Sorunları Renkle Göster", CATEGORY_VIEW),
    Command("view.error_rows", "Hatalı Satırları Vurgula", CATEGORY_VIEW),
    Command("view.previous", "Önceki Çeviri Sütunu", CATEGORY_VIEW),
    Command("view.font_bigger", "Yazıyı Büyüt", CATEGORY_VIEW, "Ctrl+="),
    Command("view.font_smaller", "Yazıyı Küçült", CATEGORY_VIEW, "Ctrl+-"),
    Command("view.font_reset", "Varsayılan Yazı Boyutu", CATEGORY_VIEW, "Ctrl+0"),
    # Çeviri
    Command("translate.auto", "Otomatik Çeviri", CATEGORY_TRANSLATE, "Ctrl+T"),
    Command("translate.selected", "Seçili Satırları Çevir", CATEGORY_TRANSLATE),
    Command("translate.retranslate", "Seçili Satırları Yeniden Çevir", CATEGORY_TRANSLATE, "Ctrl+Shift+T"),
    Command("translate.revise", "Redaksiyon (Talimatla Düzelt)", CATEGORY_TRANSLATE, "Ctrl+R"),
    Command("translate.approve", "Onayla", CATEGORY_TRANSLATE, "Ctrl+Shift+A"),
    Command("translate.unapprove", "Onayı Kaldır", CATEGORY_TRANSLATE),
    Command("translate.glossary", "Sözlük", CATEGORY_TRANSLATE, "Ctrl+Shift+G"),
    Command("translate.changes", "Son İşin Değişiklikleri", CATEGORY_TRANSLATE),
    Command("translate.history", "Çeviri Geçmişi", CATEGORY_TRANSLATE),
    # Git (adımlar)
    Command("go.add", "Oyunu Ekle", CATEGORY_GO, "Ctrl+1"),
    Command("go.scan", "Metinleri Tara", CATEGORY_GO, "Ctrl+2"),
    Command("go.translate", "Çevir", CATEGORY_GO, "Ctrl+3"),
    Command("go.qa", "Kontrol Et", CATEGORY_GO, "Ctrl+4"),
    Command("go.export", "Dışa Aktar", CATEGORY_GO, "Ctrl+5"),
    # Araçlar
    Command("tools.spell_dictionary", "Yazım Sözlüğü", CATEGORY_TOOLS),
    Command("tools.plugins", "Eklentiler", CATEGORY_TOOLS),
    Command("tools.diagnosis", "Teşhis Raporu", CATEGORY_TOOLS),
)

COMMANDS_BY_ID: dict[str, Command] = {c.id: c for c in COMMANDS}

#: Bağlanabilen nesneler: menü/araç eylemi ya da sayfaya özel kısayol.
Bindable = QAction | QShortcut


def _portable(seq: QKeySequence) -> str:
    return seq.toString(QKeySequence.SequenceFormat.PortableText)


def display_text(seq: QKeySequence) -> str:
    """Kısayolun arayüzde görünen metni ("Ctrl+Shift+T"); kısayolsuzsa boş metin."""
    return seq.toString(QKeySequence.SequenceFormat.NativeText)


class ShortcutRegistry(QObject):
    #: Bir komutun tuşu değişti (kimlik).
    changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings: QSettings | None = None
        self._custom: dict[str, str] = {}
        self._bound: dict[str, list[tuple[Bindable, str | None]]] = {}

    # --- ayarlar -------------------------------------------------------------------------

    def bind_settings(self, settings: QSettings) -> None:
        """Kullanıcının kayıtlı tuşlarını yükler; bundan sonraki değişiklikler buraya yazılır."""
        self._settings = settings
        self._custom = {}
        settings.beginGroup(KEY_PREFIX.rstrip("/"))
        try:
            names = settings.childKeys()
            values = {name: str(settings.value(name, "")) for name in names}
        finally:
            settings.endGroup()
        for name, raw in values.items():
            if name not in COMMANDS_BY_ID:
                log.warning("Tanınmayan kısayol ayarı yok sayıldı: %s", name)
                continue
            parsed = _portable(QKeySequence(raw))
            if raw and not parsed:  # çözülemeyen tuş metni boş diziye düşer; "kısayolsuz" ile karışmasın
                log.warning("Kısayol ayarı geçersiz (%s = %r); varsayılan kullanılıyor", name, raw)
                continue
            self._custom[name] = parsed
        for command_id in self._bound:
            self._apply(command_id)

    # --- okuma ---------------------------------------------------------------------------

    def sequence(self, command_id: str) -> QKeySequence:
        command = COMMANDS_BY_ID[command_id]
        return QKeySequence(self._custom.get(command_id, command.default))

    def text(self, command_id: str) -> str:
        return display_text(self.sequence(command_id))

    def is_custom(self, command_id: str) -> bool:
        return command_id in self._custom

    def conflicts(self, command_id: str, seq: QKeySequence) -> list[Command]:
        """`seq` başka hangi komutlarda kullanılıyor (kendisi hariç); boş tuş hiçbir şeyle çakışmaz."""
        if seq.isEmpty():
            return []
        wanted = _portable(seq)
        return [c for c in COMMANDS if c.id != command_id and _portable(self.sequence(c.id)) == wanted]

    # --- bağlama -------------------------------------------------------------------------

    def bind(self, command_id: str, target: Bindable, tip: str | None = None) -> Bindable:
        """Nesnenin tuşunu kayıt defterine bağlar. `tip` verilirse ipucu "metin (Ctrl+J)" olarak güncel tutulur."""
        if command_id not in COMMANDS_BY_ID:
            raise KeyError(f"Bilinmeyen komut: {command_id}")
        self._bound.setdefault(command_id, []).append((target, tip))
        target.destroyed.connect(lambda _obj=None, t=target, c=command_id: self._forget(c, t))
        self._apply_one(command_id, target, tip)
        return target

    def _forget(self, command_id: str, target: Bindable) -> None:
        self._bound[command_id] = [(t, tip) for t, tip in self._bound.get(command_id, []) if t is not target]

    def _apply(self, command_id: str) -> None:
        for target, tip in self._bound.get(command_id, []):
            self._apply_one(command_id, target, tip)

    def _apply_one(self, command_id: str, target: Bindable, tip: str | None) -> None:
        seq = self.sequence(command_id)
        if isinstance(target, QShortcut):
            target.setKey(seq)
        else:
            target.setShortcut(seq)
        if tip is not None:
            key = display_text(seq)
            target_tip = f"{tip} ({key})" if key else tip
            if isinstance(target, QShortcut):
                target.setWhatsThis(target_tip)
            else:
                target.setToolTip(target_tip)

    # --- değiştirme ----------------------------------------------------------------------

    def set_sequence(self, command_id: str, seq: QKeySequence) -> None:
        """Komutun tuşunu değiştirir (boş: kısayolsuz). Çakışmayı çağıran denetler (`conflicts`)."""
        command = COMMANDS_BY_ID[command_id]
        value = _portable(seq)
        if value == _portable(QKeySequence(command.default)):
            self._custom.pop(command_id, None)
            if self._settings is not None:
                self._settings.remove(KEY_PREFIX + command_id)
        else:
            self._custom[command_id] = value
            if self._settings is not None:
                self._settings.setValue(KEY_PREFIX + command_id, value)
        self._apply(command_id)
        self.changed.emit(command_id)

    def reset(self, command_id: str) -> None:
        self.set_sequence(command_id, QKeySequence(COMMANDS_BY_ID[command_id].default))

    def reset_all(self) -> None:
        for command_id in list(self._custom):
            self.reset(command_id)
