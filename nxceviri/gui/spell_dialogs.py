"""Yazım denetimi pencereleri: bulunan sözcüklerin sözlüğe eklenmesi ve kullanıcı sözlüğünün yönetimi."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.spell.userdict import UserDictionary
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.widgets import Banner, button, format_int, title_row


class AddSpellWordsDialog(QDialog):
    """Seçili satırlarda "sözlükte olmayan" bulunan sözcükler: işaretlenenler kullanıcı sözlüğüne eklenir."""

    def __init__(self, parent: QWidget | None, words: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yazım Sözlüğüne Ekle")
        self.resize(460, 440)
        lay = QVBoxLayout(self)
        lay.addWidget(
            title_row(
                f"{format_int(len(words))} sözcük",
                "Bu sözcükler yazım sözlüğünde yok. Doğruysa (ör. oyundaki bir ad) işaretli bırakın; kullanıcı "
                "sözlüğüne eklenir. Gerçek yazım hatasının işaretini kaldırın.",
                "cardTitle",
            )
        )
        self.list = QListWidget()
        for word in words:
            item = QListWidgetItem(word)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list.addItem(item)
        lay.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("İşaretlileri Sözlüğe Ekle")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        bind_icon(buttons.button(QDialogButtonBox.StandardButton.Cancel), "x")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def selected(self) -> list[str]:
        items = (self.list.item(i) for i in range(self.list.count()))
        return [i.text() for i in items if i is not None and i.checkState() == Qt.CheckState.Checked]


class UserDictionaryDialog(QDialog):
    """Kullanıcı sözlüğündeki sözcükler; yanlışlıkla eklenenler buradan silinir (hemen kaydedilir)."""

    def __init__(self, parent: QWidget | None, user: UserDictionary) -> None:
        super().__init__(parent)
        self._user = user
        self.removed = False
        self.setWindowTitle("Yazım Sözlüğü")
        self.resize(420, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(
            title_row(
                "Yazım sözlüğü",
                "“Sözlüğe ekle” ile kabul ettiğiniz sözcükler; bütün projelerde geçerlidir. Sildiğiniz sözcük "
                "yeniden uyarılır.",
                "cardTitle",
            )
        )
        self.list = QListWidget()
        self.list.addItems(sorted(user.words()))
        lay.addWidget(self.list, 1)
        self.banner = Banner()
        lay.addWidget(self.banner)
        row = QHBoxLayout()
        self.remove_button = button("Seçileni Sil", icon="x")
        self.remove_button.clicked.connect(self._remove)
        row.addWidget(self.remove_button)
        row.addStretch(1)
        close = button("Kapat")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        try:
            self._user.remove([self.list.item(row).text()])
        except OSError as exc:
            self.banner.show_message("danger", f"Sözlük kaydedilemedi: {exc.strerror or exc}")
            return
        self.list.takeItem(row)
        self.removed = True
