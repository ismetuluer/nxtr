"""Çeviri tablosu: klavye akışı, onaylama, bul ve değiştir, sorun renkleri."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QMenu, QTableWidget, QTableWidgetItem
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import Change, ImportedFile, Project, TranslationRow, row_group
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.replace import plan_replace
from nxceviri.core.translate.status import Status
from nxceviri.gui import main_window as main_window_module
from nxceviri.gui.changes_dialog import NEW_TEXT_ROLE, ChangesDialog
from nxceviri.gui.main_window import STEP_TRANSLATE, MainWindow

LB = ControlCode(b"\\n", "Satır sonu")
LINES = [
    ("s01", "Have a drink with me.", ()),
    ("s02", "That's the limit!", ()),
    ("s03", "We could make⟦1⟧the goal out of sticks.", (LB,)),
    ("s04", "Not me.", ()),
]


def _project() -> Project:
    p = Project.new()
    p.import_texts(
        [
            ImportedFile(
                "Dialogue.tsv",
                "0100",
                "unity",
                "base",
                tuple(TextEntry(k, i, s, codes) for i, (k, s, codes) in enumerate(LINES)),
            )
        ]
    )
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations([(rows["s01"].id, "Benimle bir içki iç."), (rows["s02"].id, "Bu limit!")], machine=True)
    p.set_translations([(rows["s04"].id, "Ben içmem.")])  # onaylı
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = MainWindow(QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat))
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.resize(1180, 780)
    w.show()
    w.nav.setCurrentRow(STEP_TRANSLATE)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _rows(w: MainWindow) -> dict[str, TranslationRow]:
    return {r.key: r for r in w.project.translation_rows()}


def test_plan_replace() -> None:
    rows = [
        TranslationRow(1, "f", "a", "Talk to the Sheriff.", "Polise git.", "machine", "", (), None),
        TranslationRow(2, "f", "b", "Press ⟦1⟧", "⟦1⟧ bas polis", "approved", "", (), None),
        TranslationRow(3, "f", "c", "a ⟦1⟧", "x ⟦1⟧", "machine", "", (), None),
        TranslationRow(4, "f", "d", "Empty", "", "untranslated", "", (), None),
    ]
    plan = plan_replace(rows, "polis", "Şerif")
    assert plan.changes == [(1, "Şerife git."), (2, "⟦1⟧ bas Şerif")]
    assert plan.matches == 2
    assert plan_replace(rows, "polis", "Şerif", case=True).changes == [(2, "⟦1⟧ bas Şerif")]
    assert plan_replace(rows, "Polis", "Şerif", whole_word=True).changes == [(2, "⟦1⟧ bas Şerif")]
    broken = plan_replace(rows, "1", "2")  # yer tutucunun içi değişirdi
    assert (broken.changes, broken.skipped) == ([], 2)
    assert plan_replace(rows, "", "x").changes == []


def test_plan_replace_regex() -> None:
    rows = [
        TranslationRow(1, "f", "a", "Kapı aç", "Kapi aç", "machine", "", (), None),
        TranslationRow(2, "f", "b", "a.b", "a.b", "machine", "", (), None),
        TranslationRow(3, "f", "c", "axb", "axb", "machine", "", (), None),
    ]
    # Düzenli ifade kapalıyken "." joker değil, gerçek noktadır.
    assert plan_replace(rows, "a.b", "x").changes == [(2, "x")]
    assert {row_id for row_id, _ in plan_replace(rows, "a.b", "x", regex=True).changes} == {2, 3}
    # Grup başvuruları düzenli ifadede çalışır; düz metinde "\1" olduğu gibi yazılır.
    assert plan_replace(rows, r"(\w+) (aç)", r"\2 \1", regex=True).changes == [(1, "aç Kapi")]
    # Düz metin aramasında "\1" grup başvurusu değil, olduğu gibi yazılan metindir.
    assert plan_replace(rows, "Kapi", r"\1").changes == [(1, "\\1 aç")]
    invalid = plan_replace(rows, "(", "x", regex=True)
    assert invalid.error.startswith("Düzenli ifade geçersiz")
    assert invalid.changes == []
    # Düzenli ifade de kontrol kodlarını bozamaz.
    guarded = plan_replace(
        [TranslationRow(4, "f", "d", "a ⟦1⟧", "a ⟦1⟧", "machine", "", (), None)], r"1", "2", regex=True
    )
    assert (guarded.changes, guarded.skipped) == ([], 1)


def test_next_open_skips_approved_and_wraps(window: MainWindow) -> None:
    page = window.translate_page
    page._select_proxy_row(3)  # s04 onaylı, son satır
    page.next_open()
    current = page.current_row()
    assert current is not None
    assert current.key == "s01"  # başa döndü; s01 makine
    page.approve([_rows(window)["s01"], _rows(window)["s02"]])
    assert {_rows(window)[k].status for k in ("s01", "s02")} == {Status.APPROVED}
    assert "2 satır onaylandı" in page.banner.text.text()
    page.next_open()
    current = page.current_row()
    assert current is not None
    assert current.key == "s03"  # çevrilmemiş tek satır


def test_approve_from_context_menu(window: MainWindow) -> None:
    page = window.translate_page
    page.table.selectRow(0)
    page._show_context_menu(page.table.visualRect(page.proxy.index(0, 0)).center())
    menu = page.table.findChild(QMenu)
    assert menu is not None
    approve = next(a for a in menu.actions() if a.text().startswith("Onayla ("))
    assert approve.text() == "Onayla (1)" + chr(9) + "Ctrl+Shift+A"  # kısayol sağ sütunda görünür
    approve.trigger()
    menu.close()
    assert _rows(window)["s01"].status == Status.APPROVED


def test_show_row_in_place_clears_filters(window: MainWindow) -> None:
    """Arama sonucunda tek başına görünen satır, komşularıyla birlikte gerçek yerinde gösterilir."""
    page = window.translate_page
    s03 = _rows(window)["s03"]
    page.status_filter.setCurrentIndex(page.status_filter.findData(Status.UNTRANSLATED.value))
    page.group_filter.set_selected([row_group(s03)])
    page.search.setText("goal")
    assert page.proxy.rowCount() == 1
    page._show_context_menu(page.table.visualRect(page.proxy.index(0, 0)).center())
    menu = page.table.findChild(QMenu)
    assert menu is not None
    reveal = next(a for a in menu.actions() if a.text() == "Yerinde göster")
    assert reveal.isEnabled()
    reveal.trigger()
    menu.close()
    assert page.search.text() == ""
    assert page.status_filter.currentIndex() == 0
    assert not page.group_filter.active
    assert page.proxy.rowCount() == page.model.rowCount()
    current = page.current_row()
    assert current is not None
    assert current.id == s03.id
    assert page.table.currentIndex().row() == page.model.position(s03.id)
    assert "kendi yerinde gösteriliyor" in page.banner.text.text()


def test_show_row_in_place_needs_a_single_row(window: MainWindow) -> None:
    page = window.translate_page
    page.table.selectAll()
    page._show_context_menu(page.table.visualRect(page.proxy.index(0, 0)).center())
    menu = page.table.findChild(QMenu)
    assert menu is not None
    reveal = next(a for a in menu.actions() if a.text() == "Yerinde göster")
    assert not reveal.isEnabled()
    menu.close()


def test_banner_can_be_closed(window: MainWindow) -> None:
    page = window.translate_page
    page.show_notice("warning", "Uzun bir bildirim")
    assert page.banner.isVisibleTo(window)
    from PySide6.QtWidgets import QToolButton

    close = page.banner.findChild(QToolButton)
    assert close is not None
    close.click()
    assert not page.banner.isVisibleTo(window)


def test_minimum_window_keeps_layout(qtbot: QtBot, window: MainWindow) -> None:
    window.resize(window.minimumSize())
    qtbot.wait(50)
    page = window.translate_page
    table_bottom = page.table.mapTo(page, page.table.rect().bottomLeft()).y()
    assert table_bottom <= page.height()  # tablo en küçük pencerede de sayfanın dışına taşmıyor


def test_issue_colors_filter_and_toggle(window: MainWindow) -> None:
    from nxceviri.gui.theme import current_tokens
    from nxceviri.gui.translate_page import COL_TRANSLATION, ISSUES_FILTER

    rows = _rows(window)
    window.project.set_translations(
        [
            (rows["s01"].id, "<div>Benimle bir içki iç.</div>"),  # fazla etiket
            (rows["s03"].id, "Kaleyi çubuklardan yapabiliriz.⟦1⟧"),  # satır sonu kodu sona yığılmış
        ],
        machine=True,
    )
    page = window.translate_page
    page.set_rows(window.project.translation_rows())
    model = page.model
    t = current_tokens()

    def color(key: str) -> object:
        index = model.index(model.position(_rows(window)[key].id) or 0, COL_TRANSLATION)
        value = model.data(index, Qt.ItemDataRole.ForegroundRole)
        return None if value is None else value.name().upper()

    assert color("s01") == t["issue_markup"].upper()
    assert color("s03") == t["issue_lines"].upper()
    assert color("s02") is None
    tip = model.data(
        model.index(model.position(_rows(window)["s01"].id) or 0, COL_TRANSLATION), Qt.ItemDataRole.ToolTipRole
    )
    assert "⚠ Fazla etiket" in tip
    assert "&lt;div&gt;" in tip  # etiket ipucunda biçim olarak yorumlanmaz

    page.status_filter.setCurrentIndex(page.status_filter.findData(ISSUES_FILTER))
    assert page.proxy.rowCount() == 2
    page.colors_box.setChecked(False)
    assert color("s01") is None
    assert window.settings.value("translate/issue_colors") == "0"


def test_approved_rows_can_be_revised_and_unapproved(window: MainWindow) -> None:
    from nxceviri.gui.machine_dialogs import PROVIDER_OLLAMA, SCOPE_SELECTED, MachineDialog

    page = window.translate_page
    s04 = _rows(window)["s04"]
    assert s04.status == Status.APPROVED
    page.select_row(s04.id)
    page._show_context_menu(page.table.visualRect(page.table.currentIndex()).center())
    menu = page.table.findChild(QMenu)
    assert menu is not None
    texts = {a.text(): a for a in menu.actions()}
    translate = menu.actions()[0].menu()
    assert isinstance(translate, QMenu)
    revise = next(a for a in translate.actions() if a.text().startswith("Redaksiyon (1)"))
    assert revise.isEnabled()  # eskiden onaylı satır sayılmadığı için (0) ve pasifti

    dialog = MachineDialog(
        window,
        provider=PROVIDER_OLLAMA,
        base_url="",
        model="gemma4:12b",
        notes="",
        source_language="en",
        secrets=window.secrets,
        scopes={SCOPE_SELECTED: [s04]},
        action="revise",
        scope=SCOPE_SELECTED,
    )
    assert dialog.include_approved.isChecked()  # yalnızca onaylı satır seçildi: kendiliğinden işaretli
    assert [r.key for r in dialog.target()] == ["s04"]
    dialog.close()

    texts["Onayı kaldır (1)"].trigger()
    menu.close()
    after = _rows(window)["s04"]
    assert (after.status, after.translation) == (Status.MACHINE, "Ben içmem.")
    assert "onayı kaldırıldı" in page.banner.text.text()


def test_ctrl_z_undoes_last_operation(qtbot: QtBot, window: MainWindow) -> None:
    from PySide6.QtTest import QTest

    page = window.translate_page
    s01 = _rows(window)["s01"]
    page.approve([s01])
    page.table.setFocus()
    QTest.keyClick(page.table, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert _rows(window)["s01"].status == Status.MACHINE
    assert "Geri alındı (Elle düzenleme): 1 satır" in page.banner.text.text()
    window._update_undo_action()
    assert window.undo_action.text() == "Geri Al: Elle düzenleme"  # projeyi kurarken yapılan onay
    window.undo_last()
    window.undo_last()
    window.undo_last()
    assert "Geri alınacak bir işlem yok" in page.banner.text.text()


@pytest.mark.parametrize("fmt", ["txt", "xlsx"])
def test_revision_export_and_import(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fmt: str
) -> None:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QDialog, QFileDialog, QWidget

    from nxceviri.core.translate.csvio import TXT_COLUMNS, parse_xlsx, table_xlsx
    from nxceviri.gui.csv_dialog import CsvExportDialog

    page = window.translate_page
    page.table.selectAll()

    class Accepting(CsvExportDialog):
        def exec(self) -> int:
            assert self.scope_group.checkedId() == 0  # birden çok satır seçiliyken "Seçili satırlar"
            assert not self.group_box.isEnabled()  # tek grup (Dialogue.tsv)
            if fmt == "xlsx":
                self.xlsx_radio.setChecked(True)
                assert "XLSX (Excel)" in self.prompt.toPlainText()
            else:
                assert self.txt_radio.isChecked()  # varsayılan TXT
                assert "düzeltme" in self.prompt.toPlainText()
            self.split_box.setChecked(False)
            return CsvExportDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "CsvExportDialog", Accepting)
    target = tmp_path / f"redaksiyon.{fmt}"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window.export_csv()
    assert target.exists()
    assert "4 satır yazıldı" in page.banner.text.text()
    assert "⟦1⟧" in QGuiApplication.clipboard().text()  # hazır istem panoda

    if fmt == "txt":
        text = target.read_text(encoding="utf-8-sig")
        # Düzeltme sütununu doldur (orijinal ve çeviri değişmez).
        text = text.replace(
            "Have a drink with me.\tBenimle bir içki iç.\t",
            "Have a drink with me.\tBenimle bir içki iç.\tBenimle bir kadeh iç.",
        )
        text = text.replace(
            "That's the limit!\tBu limit!\t",
            "That's the limit!\tBu limit!\tBu son sınır!",
        )
        with target.open("w", encoding="utf-8-sig", newline="") as fh:
            fh.write(text)
    else:
        parsed = parse_xlsx(target.read_bytes())
        fix = {"Have a drink with me.": "Benimle bir kadeh iç.", "That's the limit!": "Bu son sınır!"}
        fixed = [(r.source or "", r.text, fix.get(r.source or "", ""), r.group) for r in parsed]
        target.write_bytes(table_xlsx(TXT_COLUMNS, fixed))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(target)], ""))
    asked: list[str] = []

    class Preview(ChangesDialog):
        def __init__(
            self,
            parent: QWidget | None,
            title: str,
            changes: list[Change],
            *,
            history: bool = False,
            preview: bool = False,
            summary: Sequence[str] = (),
        ) -> None:
            asked.append("\n".join(summary))
            super().__init__(parent, title, changes, history=history, preview=preview, summary=summary)

        def exec(self) -> int:
            # Uygulamadan önce satır satır karşılaştırma gösterilir: "Yaz, Satır, Orijinal, Önceki, Yeni".
            assert self.table.columnCount() == 5
            assert self.table.rowCount() == 2
            old, new = _cell(self.table, 0, 3), _cell(self.table, 0, 4)
            assert "<s>içki</s>" in old.text()
            assert "kadeh" in new.text()
            assert _cell(self.table, 0, 0).checkState() == Qt.CheckState.Checked
            assert _cell(self.table, 1, 0).checkState() == Qt.CheckState.Checked
            # İkinci satırı beğenmedik: işareti kaldır. Birinci satırın önerisini düzenle.
            _cell(self.table, 1, 0).setCheckState(Qt.CheckState.Unchecked)
            _cell(self.table, 0, 4).setData(NEW_TEXT_ROLE, "Benimle bir kadeh içelim.")
            assert "Çevirilere Yaz (1)" in self.revert_button.text()
            assert [c.new_text for c in self.accepted_changes()] == ["Benimle bir kadeh içelim."]
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "ChangesDialog", Preview)
    window.import_csv()
    assert "Değişecek: 2 satır" in asked[0]
    assert "Redakte" in asked[0]
    imported = _rows(window)["s01"]
    assert (imported.translation, imported.status) == ("Benimle bir kadeh içelim.", Status.REDACTED)
    rejected = _rows(window)["s02"]  # işareti kaldırılan satır eski çevirisiyle kalır
    assert (rejected.translation, rejected.status) == ("Bu limit!", Status.MACHINE)
    assert page.changes_button.text() == "Son İşin Değişiklikleri (1)…"
    window.undo_last()
    assert _rows(window)["s01"].translation == "Benimle bir içki iç."


def test_translation_export_and_import_uses_translation_columns(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from PySide6.QtWidgets import QDialog, QFileDialog, QWidget

    from nxceviri.gui.csv_dialog import CsvExportDialog

    page = window.translate_page
    page.table.selectAll()

    class Accepting(CsvExportDialog):
        def exec(self) -> int:
            assert self._translation
            assert self.scope_group.checkedId() == 0
            assert self.txt_radio.isChecked()
            assert "yeni çeviri" in self.prompt.toPlainText()
            assert "düzeltme" not in self.prompt.toPlainText()
            self.split_box.setChecked(False)
            return CsvExportDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "CsvExportDialog", Accepting)
    target = tmp_path / "oyun_ceviri.txt"
    seen: dict[str, str] = {}

    def save(_parent: object, title: str, start: str, _filters: str) -> tuple[str, str]:
        seen["title"] = title
        seen["start"] = start
        return str(target), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", save)
    window.export_translation()
    assert seen["title"] == "Dış çeviri dosyasını kaydet"
    assert seen["start"].endswith("_ceviri.txt")
    assert target.exists()
    assert "çeviri dosyasına yazıldı" in page.banner.text.text()
    assert "yeni çeviri" in target.read_text(encoding="utf-8-sig").splitlines()[0]

    text = target.read_text(encoding="utf-8-sig")
    text = text.replace(
        "Have a drink with me.\tBenimle bir içki iç.\t",
        "Have a drink with me.\tBenimle bir içki iç.\tBenimle bir kadeh iç.",
    )
    text = text.replace(
        "That's the limit!\tBu limit!\t",
        "That's the limit!\tBu limit!\tBu son sınır!",
    )
    target.write_text(text, encoding="utf-8-sig")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(target)], ""))
    asked: list[str] = []

    class Preview(ChangesDialog):
        def __init__(
            self,
            parent: QWidget | None,
            title: str,
            changes: list[Change],
            *,
            history: bool = False,
            preview: bool = False,
            summary: Sequence[str] = (),
        ) -> None:
            assert title == "Dış çeviriden içe aktar"
            asked.append("\n".join(summary))
            super().__init__(parent, title, changes, history=history, preview=preview, summary=summary)

        def exec(self) -> int:
            # İkinci satırı beğenmedik: işareti kaldır; birinci satır yazılsın.
            _cell(self.table, 1, 0).setCheckState(Qt.CheckState.Unchecked)
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "ChangesDialog", Preview)
    window.import_translation()
    assert "Yeni çeviri sütunu boş: 0 satır" not in asked[0]
    assert "Değişecek: 2 satır" in asked[0]
    assert "“Makine”" in asked[0]
    imported = _rows(window)["s01"]
    assert (imported.translation, imported.status) == ("Benimle bir kadeh iç.", Status.MACHINE)
    rejected = _rows(window)["s02"]
    assert (rejected.translation, rejected.status) == ("Bu limit!", Status.MACHINE)
    assert page.changes_button.text() == "Son İşin Değişiklikleri (1)…"

    window.undo_last()
    assert _rows(window)["s01"].translation == "Benimle bir içki iç."


def _cell(table: QTableWidget, row: int, column: int) -> QTableWidgetItem:
    item = table.item(row, column)
    assert item is not None
    return item


def _preview_dialog(qtbot: QtBot) -> ChangesDialog:
    changes = [
        Change(1, "s01", "Hello ⟦1⟧", "Merhaba ⟦1⟧", "machine", "", "Selam ⟦1⟧", "csv", ""),
        Change(2, "s02", "Bye", "Hoşça kal", "machine", "", "Güle güle", "csv", ""),
    ]
    dialog = ChangesDialog(None, "Dış redaksiyondan içe aktar", changes, preview=True)
    qtbot.addWidget(dialog)
    return dialog


def test_preview_accepts_rejects_and_edits_individual_rows(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = _preview_dialog(qtbot)
    assert dialog.table.columnCount() == 5
    assert [_cell(dialog.table, r, 0).checkState() for r in range(2)] == [
        Qt.CheckState.Checked,
        Qt.CheckState.Checked,
    ]
    assert "Çevirilere Yaz (2)" in dialog.revert_button.text()

    # İkinci satırı beğenmedik: işareti kaldırılınca ne sayıya ne de yazılacaklara girer.
    _cell(dialog.table, 1, 0).setCheckState(Qt.CheckState.Unchecked)
    assert "Çevirilere Yaz (1)" in dialog.revert_button.text()
    assert [c.entry_id for c in dialog.accepted_changes()] == [1]

    # Birinci satırın önerisini düzenle: hücredeki renkli fark tazelenir, yazılacak metin değişir.
    _cell(dialog.table, 0, 4).setData(NEW_TEXT_ROLE, "Merhaba dünya ⟦1⟧")
    assert "dünya" in _cell(dialog.table, 0, 4).text()
    assert dialog.accepted_changes()[0].new_text == "Merhaba dünya ⟦1⟧"

    _cell(dialog.table, 0, 0).setCheckState(Qt.CheckState.Unchecked)
    assert "Çevirilere Yaz (0)" in dialog.revert_button.text()
    assert not dialog.revert_button.isEnabled()
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted  # yazılacak satır kalmadı
    assert "Yazılacak değişiklik kalmadı" in dialog.status.text.text()

    # Tekrar işaretleyince kabul edilir.
    _cell(dialog.table, 0, 0).setCheckState(Qt.CheckState.Checked)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_preview_new_cell_editor_shows_plain_text(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QPlainTextEdit

    dialog = _preview_dialog(qtbot)
    dialog.show()
    qtbot.wait(10)
    item = _cell(dialog.table, 0, 4)
    dialog.table.setCurrentCell(0, 4)
    dialog.table.editItem(item)
    editor = dialog.table.findChild(QPlainTextEdit)
    assert editor is not None
    assert editor.toPlainText() == "Selam ⟦1⟧"  # HTML etiketi değil, gerçek metin
    editor.setPlainText("Merhaba dünya ⟦1⟧")
    dialog.table.setCurrentCell(0, 1)  # hücre dışına geç: düzenleme yazılır
    qtbot.waitUntil(lambda: dialog.accepted_changes()[0].new_text == "Merhaba dünya ⟦1⟧")
    assert "dünya" in item.text()


def test_preview_blocks_empty_or_broken_corrections(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = _preview_dialog(qtbot)
    _cell(dialog.table, 0, 4).setData(NEW_TEXT_ROLE, "Selam")  # ⟦1⟧ kayboldu
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "Eksik kontrol kodu" in dialog.status.text.text()

    _cell(dialog.table, 0, 4).setData(NEW_TEXT_ROLE, "   ")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "düzeltme boş" in dialog.status.text.text()

    _cell(dialog.table, 0, 4).setData(NEW_TEXT_ROLE, "Selam ⟦1⟧")
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_status_cell_shows_row_problems_under_status(qtbot: QtBot, window: MainWindow) -> None:
    from nxceviri.core.translate.providers.base import GlossaryTerm
    from nxceviri.gui.translate_page import COL_STATUS

    window.project.set_glossary([GlossaryTerm("drink", "kadeh", ""), GlossaryTerm("Not me", "Bana değil", "")])
    rows = _rows(window)
    window.project.set_translations([(rows["s02"].id, "<b>Bu limit!</b>")], machine=True)
    page = window.translate_page
    page.set_rows(window.project.translation_rows())
    model = page.model

    def cell(key: str, role: int = Qt.ItemDataRole.DisplayRole) -> str:
        index = model.index(model.position(_rows(window)[key].id) or 0, COL_STATUS)
        return str(model.data(index, role) or "")

    # Hızlı denetimler (etiket, kod) Kontrol Et çalışmadan da durumun altında görünür.
    assert cell("s02").startswith("● Makine")
    assert "1 hata" in cell("s02")
    assert "Orijinalde olmayan etiket" in cell("s02", Qt.ItemDataRole.ToolTipRole)
    assert "uyarı" not in cell("s01")  # sözlük denetimi henüz yapılmadı

    window.run_checks()
    assert "1 uyarı" in cell("s01")
    # Durumun altındaki sorun satırı kesilmesin: satır yüksekliği yeniden ölçülür.
    table = page.table
    single = table.fontMetrics().height() + 14
    s01_row = page.proxy.mapFromSource(model.index(model.position(rows["s01"].id) or 0, 0)).row()
    qtbot.waitUntil(lambda: table.rowHeight(s01_row) > single)
    assert "kadeh" in cell("s01", Qt.ItemDataRole.ToolTipRole)
    # Onaylı satırın sorunu da gösterilir (Kontrol Et onaylı satırları da denetler).
    assert cell("s04").startswith("● Onaylandı")
    assert "1 uyarı" in cell("s04")

    # Çeviri değişince eski denetim sonucu düşer.
    window.project.set_translations([(rows["s01"].id, "Benimle bir kadeh iç.")], machine=True)
    page.model.update_rows([r for r in window.project.translation_rows() if r.id == rows["s01"].id])
    assert "uyarı" not in cell("s01")
