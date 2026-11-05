"""Çeviri sayfası: düzenleme paneli yerleşimi, seçim eşleşmesi, kayıt güvenliği ve araç çubuğu."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QToolButton
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.core.translate.status import Status
from nxceviri.gui.translate_page import TranslatePage
from nxceviri.gui.view_actions import ALIGN_CENTER, PANE_BOTTOM, PANE_RIGHT
from tests.test_marked_delegate import make_row

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _restore_app(qtbot: QtBot) -> Iterator[None]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    yield
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)


class FakeCommit:
    """`MainWindow._commit_translations` yerine: çağrıları kaydeder ve satırları günceller."""

    def __init__(self, page: TranslatePage) -> None:
        self.page = page
        self.calls: list[list[tuple[int, str]]] = []

    def __call__(self, changes: list[tuple[int, str]]) -> list[TranslationRow]:
        self.calls.append(list(changes))
        updated: list[TranslationRow] = []
        for row_id, text in changes:
            row = self.page.model.row_by_id(row_id)
            assert row is not None
            updated.append(replace(row, translation=text, status=Status.APPROVED if text else Status.UNTRANSLATED))
        return updated


def default_rows() -> list[TranslationRow]:
    return [
        make_row(1, "One", "Bir"),
        make_row(2, "Two ⟦1⟧ here", "İki ⟦1⟧ burada", labels=("Satır sonu",)),
        make_row(3, "Three", "Üç"),
        make_row(4, "Four", "Dört"),
    ]


def make_page(
    qtbot: QtBot,
    rows: list[TranslationRow] | None = None,
    *,
    width: int = 1300,
    height: int = 1000,
    settings: QSettings | None = None,
) -> tuple[TranslatePage, FakeCommit]:
    page = TranslatePage()
    qtbot.addWidget(page)
    page.resize(width, height)
    page.show()
    fake = FakeCommit(page)
    page.model.commit = fake
    if settings is not None:
        page.bind_settings(settings)
    page.set_rows(rows if rows is not None else default_rows())
    return page, fake


def type_in_pane(qtbot: QtBot, page: TranslatePage, text: str) -> None:
    page.pane.translation_edit.setFocus()
    page.pane.translation_edit.selectAll()
    qtbot.keyClicks(page.pane.translation_edit, text)


def test_pane_default_bottom_open(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    assert page.splitter.orientation() == Qt.Orientation.Vertical
    assert page.pane.isVisibleTo(page)
    assert page.view_actions.pane == PANE_BOTTOM


def test_position_switching_and_off(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    actions = page.view_actions.pane_actions
    actions[PANE_RIGHT].trigger()
    assert page.splitter.orientation() == Qt.Orientation.Horizontal
    assert page.pane.isVisibleTo(page)
    actions[PANE_RIGHT].trigger()  # etkine tıklamak kapatır
    assert not page.pane.isVisibleTo(page)
    actions[PANE_BOTTOM].trigger()
    assert page.splitter.orientation() == Qt.Orientation.Vertical
    assert page.pane.isVisibleTo(page)


def test_selection_fills_pane(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    assert page.pane.title_label.text() == "Satır seçin"
    page._select_proxy_row(1)
    assert page.pane.source_view.toPlainText() == "Two ⟦1⟧ here"
    assert page.pane.translation_edit.toPlainText() == "İki ⟦1⟧ burada"
    assert len(page.pane.chip_buttons) == 1  # satırın tek kontrol kodu


def test_pane_commit_goes_through_model_apply_once(qtbot: QtBot) -> None:
    page, fake = make_page(qtbot)
    page._select_proxy_row(0)
    type_in_pane(qtbot, page, "yeni")
    qtbot.keyClick(page.pane.translation_edit, Qt.Key.Key_Return)
    assert fake.calls == [[(1, "yeni")]]
    assert page.model.row_by_id(1) is not None
    assert page.model.rows[0].translation == "yeni"
    assert not page.pane.has_pending()


def test_pending_text_saved_on_row_change(qtbot: QtBot) -> None:
    page, fake = make_page(qtbot)
    page._select_proxy_row(0)
    type_in_pane(qtbot, page, "bekleyen")
    page._select_proxy_row(2)
    assert fake.calls == [[(1, "bekleyen")]]
    assert page.pane.source_view.toPlainText() == "Three"


def test_pending_saved_on_pane_close_and_machine_start(qtbot: QtBot) -> None:
    page, fake = make_page(qtbot)
    page._select_proxy_row(0)
    type_in_pane(qtbot, page, "makine oncesi")
    page.set_machine_running(True)
    assert fake.calls == [[(1, "makine oncesi")]]
    assert page.pane.translation_edit.isReadOnly()
    page.set_machine_running(False)
    assert not page.pane.translation_edit.isReadOnly()
    page._select_proxy_row(0)
    type_in_pane(qtbot, page, "kapanmadan once")
    page.view_actions.pane_actions[PANE_BOTTOM].trigger()  # paneli kapat
    assert fake.calls[-1] == [(1, "kapanmadan once")]
    assert not page.pane.isVisibleTo(page)


def test_filter_removes_edited_row_pane_leaves_it_without_misdirected_write(qtbot: QtBot) -> None:
    page, fake = make_page(qtbot)
    page._select_proxy_row(0)
    type_in_pane(qtbot, page, "suzgec")
    page.search.setText("Four")  # düzenlenen 1. satır listeden çıkar
    assert fake.calls == [[(1, "suzgec")]]  # yalnızca düzenlenen satırın kimliğiyle
    assert (
        page.pane.row_id != 1
    )  # panel artık listeden çıkan satırı göstermez (pasif ya da tablonun yeni geçerli satırı)
    other = page.model.row_by_id(4)
    assert other is not None
    assert other.translation == "Dört"  # başka satıra yazılmadı


def test_prev_next_navigates_filtered_order(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page.search.setText("e")  # One, Three, Four (iki, "Two" 'e' içermez... )
    visible = [r.key for r in page.filtered_rows()]
    assert len(visible) >= 2
    page._select_proxy_row(0)
    page.pane.navigate_requested.emit(1)
    current = page.current_row()
    assert current is not None
    assert current.key == visible[1]
    page.pane.navigate_requested.emit(-1)
    first = page.current_row()
    assert first is not None
    assert first.key == visible[0]


def test_approve_button_uses_approve_path(qtbot: QtBot) -> None:
    page, fake = make_page(qtbot)
    page._select_proxy_row(2)
    qtbot.mouseClick(page.pane.approve_button, Qt.MouseButton.LeftButton)
    assert fake.calls == [[(3, "Üç")]]  # çeviri aynen onaylanır


def test_counter_uses_fit_rules(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page.set_fit_config(FitConfig(default=FitRules(40, 3)))
    page._select_proxy_row(0)
    assert page.pane.counter_label.text().startswith("Satır ")
    page.set_fit_config(FitConfig())
    page._select_proxy_row(2)
    assert page.pane.counter_label.text().endswith("karakter")


def test_narrow_window_right_falls_back_to_bottom(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page.view_actions.pane_actions[PANE_RIGHT].trigger()
    assert page.splitter.orientation() == Qt.Orientation.Horizontal
    page.resize(800, 1000)
    assert page.splitter.orientation() == Qt.Orientation.Vertical  # dar: altta gösterilir
    assert page.view_actions.pane == PANE_RIGHT  # seçim değişmez
    page.resize(1300, 1000)
    assert page.splitter.orientation() == Qt.Orientation.Horizontal


def test_splitter_sizes_persist_per_position(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "panel.ini"), QSettings.Format.IniFormat)
    page, _ = make_page(qtbot, settings=settings)
    page.splitter.setSizes([420, 200])
    page._save_pane_sizes()
    assert str(settings.value("translate/pane_sizes_bottom")) == ",".join(str(s) for s in page.splitter.sizes())
    other, _ = make_page(qtbot, settings=QSettings(str(tmp_path / "panel.ini"), QSettings.Format.IniFormat))
    sizes = other.splitter.sizes()
    assert sizes[0] > sizes[1]


def test_toolbar_has_no_duplicate_view_buttons(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    assert not [t for t in page.findChildren(QToolButton) if t.property("role") == "viewTool"]
    for act in (*page.view_actions.align_actions.values(), *page.view_actions.pane_actions.values()):
        assert act.toolTip()


def test_view_changes_reach_table_and_pane(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page.view_actions.symbols.trigger()
    page.view_actions.align_actions[ALIGN_CENTER].trigger()
    assert page.source_delegate.symbols
    assert page.source_delegate.align == ALIGN_CENTER
    assert page.translation_delegate.symbols
    assert page.pane.translation_edit.document().defaultTextOption().alignment() & Qt.AlignmentFlag.AlignHCenter


def test_ctrl_e_does_not_change_text(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page._select_proxy_row(0)
    page.pane.translation_edit.setFocus()
    before = page.pane.translation_edit.toPlainText()
    qtbot.keyClick(page.pane.translation_edit, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
    assert page.pane.translation_edit.toPlainText() == before


def test_view_settings_restored_via_bind_settings(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "gorunum.ini"), QSettings.Format.IniFormat)
    settings.setValue("translate/symbols", "1")
    settings.setValue("translate/align", "center")
    settings.setValue("translate/pane", "right")
    page, _ = make_page(qtbot, settings=settings)
    assert page.source_delegate.symbols
    assert page.source_delegate.align == ALIGN_CENTER
    assert page.splitter.orientation() == Qt.Orientation.Horizontal
    assert page.view_actions.symbols.isChecked()


def test_short_wide_window_uses_right_layout(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    assert page.splitter.orientation() == Qt.Orientation.Vertical
    page.setMinimumSize(1, 1)  # bağımsız sayfa, panel yüzünden ana penceredeki gibi küçülemez
    page.resize(1300, 560)  # altta sığmaz ama genişlik yeterli
    qtbot.waitUntil(lambda: page.splitter.orientation() == Qt.Orientation.Horizontal, timeout=3000)
    assert page.pane.isVisibleTo(page)
    assert page.view_actions.pane == PANE_BOTTOM  # seçim değişmez


def test_tiny_window_hides_pane_without_changing_choice(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page.setMinimumSize(1, 1)  # bağımsız sayfa, panel yüzünden ana penceredeki gibi küçülemez
    page.resize(820, 520)
    qtbot.waitUntil(lambda: not page.pane.isVisibleTo(page), timeout=3000)
    assert page.view_actions.pane == PANE_BOTTOM
    page.resize(1300, 1000)
    qtbot.waitUntil(lambda: page.pane.isVisibleTo(page), timeout=3000)


def test_external_update_refreshes_idle_pane(qtbot: QtBot) -> None:
    page, fake = make_page(qtbot)
    page._select_proxy_row(0)
    row = page.model.row_by_id(1)
    assert row is not None
    page.model.update_rows([replace(row, translation="Dis guncelleme", status=Status.MACHINE)])
    assert page.pane.translation_edit.toPlainText() == "Dis guncelleme"
    qtbot.keyClick(page.pane.translation_edit, Qt.Key.Key_Return)  # Enter eski metni geri yazmamalı
    assert fake.calls[-1] == [(1, "Dis guncelleme")]


def test_external_update_keeps_pending_pane_text(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page._select_proxy_row(0)
    type_in_pane(qtbot, page, "yazdim")
    row = page.model.row_by_id(1)
    assert row is not None
    page.model.update_rows([replace(row, translation="Dis", status=Status.MACHINE)])
    assert page.pane.translation_edit.toPlainText() == "yazdim"


def test_failed_save_keeps_text_when_row_changes(qtbot: QtBot) -> None:
    from nxceviri.core.errors import NxError

    page, _ = make_page(qtbot)

    def failing(_changes: list[tuple[int, str]]) -> list[TranslationRow]:
        raise NxError("Kayit basarisiz")

    page.model.commit = failing
    page._select_proxy_row(0)
    type_in_pane(qtbot, page, "kaybolmasin")
    page._select_proxy_row(1)
    assert page.pane.row_id == 1
    assert page.pane.translation_edit.toPlainText() == "kaybolmasin"
    assert page.pane.error_label.text()


def test_code_kinds_push_does_not_commit_pending_text(qtbot: QtBot) -> None:
    from nxceviri.core.translate.codekinds import CodeKinds

    page, fake = make_page(qtbot)
    page._select_proxy_row(0)
    type_in_pane(qtbot, page, "bekleyen")
    page.set_code_kinds(CodeKinds({}))
    assert fake.calls == []
    assert page.pane.translation_edit.toPlainText() == "bekleyen"


def test_bottom_pane_grows_when_chips_appear(qtbot: QtBot) -> None:
    # Kod çipleri ve uyarılar sonradan belirince panel büyür; etiketler kutuların üstüne binmez.
    page, _ = make_page(qtbot, height=760)
    qtbot.wait(50)
    page._select_proxy_row(1)  # kontrol kodlu satır: çip satırı görünür
    qtbot.waitUntil(lambda: page.pane.height() >= page.pane.minimumSizeHint().height())
    assert page.pane.minimumHeight() <= page.pane.minimumSizeHint().height()
