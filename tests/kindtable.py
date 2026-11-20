"""Sığdırma sekmesindeki kod türü tablosunu kullanıcı gibi düzenleyen yardımcılar (ortak test kodu)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QStyleOptionViewItem

from nxceviri.gui.qa_page import QaPage


def kind_of(page: QaPage, row: int) -> str:
    """Satırın seçili kod türü (görünen ad değil, tür anahtarı)."""
    item = page.fit_kinds.item(row, 1)
    assert item is not None
    return str(item.data(Qt.ItemDataRole.UserRole))


def kind_text(page: QaPage, row: int) -> str:
    item = page.fit_kinds.item(row, 1)
    assert item is not None
    return item.text()


def choose_kind(page: QaPage, row: int, kind: str) -> None:
    """Hücre düzenleyicisini açar, türü seçer ve onaylar: kullanıcının çift tıklayıp seçmesi."""
    delegate = page.fit_kinds.itemDelegateForColumn(1)
    index = page.fit_kinds.model().index(row, 1)
    editor = delegate.createEditor(page.fit_kinds.viewport(), QStyleOptionViewItem(), index)
    assert isinstance(editor, QComboBox)
    delegate.setEditorData(editor, index)
    editor.setCurrentIndex(editor.findData(kind))
    delegate.setModelData(editor, page.fit_kinds.model(), index)
    editor.deleteLater()
