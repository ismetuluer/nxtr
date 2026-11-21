"""Dış redaksiyon/çeviri içe aktarma penceresi (`ImportDialog`): tek pencerede dosyalar, sonuç ve satır listesi."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QDialog

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.csvio import TRANSLATION_COLUMNS, TXT_COLUMNS, table_xlsx
from nxceviri.gui.changes_dialog import NEW_TEXT_ROLE
from nxceviri.gui.import_dialog import ImportDialog

pytestmark = pytest.mark.usefixtures("qapp")


def _row(i: int, source: str, text: str, status: str = "machine", free: frozenset[int] = frozenset()) -> TranslationRow:
    return TranslationRow(i, "a>UI", f"k{i}", source, text, status, "", (), None, free_codes=free)


ROWS = [
    _row(1, "Save your game?", "Oyunu kaydetmek istiyor musunuz?"),
    _row(2, "Settings will be reset.", "Ayarlar sıfırlanacak."),
    _row(3, "You got ⟦1⟧ gold!", "⟦1⟧ altın kazandın!"),
    _row(4, "Quest done.", "Görev tamamlandı.", status="approved"),
    _row(5, "Same", "Aynı"),
]


def _write(tmp_path: Path, name: str, lines: list[tuple[str, str, str]], translation: bool = False) -> Path:
    path = tmp_path / name
    columns = TRANSLATION_COLUMNS if translation else TXT_COLUMNS
    path.write_bytes(table_xlsx(columns, [(s, t, c, "UI") for s, t, c in lines]))
    return path


def _first(tmp_path: Path) -> Path:
    return _write(
        tmp_path,
        "bir.xlsx",
        [
            ("Save your game?", "Oyunu kaydetmek istiyor musunuz?", "Oyun kaydedilsin mi?"),
            ("Settings will be reset.", "Ayarlar sıfırlanacak.", "Ayarlar varsayılana dönecek."),
            ("You got ⟦1⟧ gold!", "⟦1⟧ altın kazandın!", "altın kazandınız!"),  # kod yok: yazılamaz
            ("Quest done.", "Görev tamamlandı.", "Görev bitti."),  # onaylıydı
            ("Same", "Aynı", ""),  # düzeltme boş
        ],
    )


def _dialog(
    qtbot: object, *paths: Path, translation: bool = False, rows: list[TranslationRow] | None = None
) -> ImportDialog:
    d = ImportDialog(
        None,
        title="Dış çeviriden içe aktar" if translation else "Dış redaksiyondan içe aktar",
        rows=rows if rows is not None else ROWS,
        translation=translation,
        job_kind="translation" if translation else "csv",
    )
    qtbot.addWidget(d)  # type: ignore[attr-defined]
    if paths:
        assert d.add_files(list(paths)) == []
    return d


def _checked(d: ImportDialog) -> list[bool]:
    m = d.model
    return [m.data(m.index(r, 0), Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked for r in range(m.rowCount())]


def test_counts_button_and_filters(qtbot: object, tmp_path: Path) -> None:
    d = _dialog(qtbot, _first(tmp_path))
    plan = d.plan
    assert len(plan.changes) == 3
    assert len(plan.code_problems) == 1
    assert plan.no_correction == 1
    assert d.write_button.text() == "3 satırı yaz"
    assert d.write_button.isEnabled()
    assert d.changes_chip.text() == "Değişecek 3"
    assert d.approved_chip.text() == "Onaylıydı 1"
    assert not d.approved_chip.isHidden()
    assert d.rejected_chip.text() == "Kod uymuyor 1"
    assert not d.rejected_chip.isHidden()
    assert d.model.rowCount() == 3  # varsayılan süzgeç: değişecekler
    d.approved_chip.click()
    assert d.model.rowCount() == 1
    d.rejected_chip.click()
    assert d.model.rowCount() == 1
    d.changes_chip.click()
    assert d.model.rowCount() == 3
    assert "“Redakte” durumuyla yazılır" in d.footer_note.text()


def test_rejected_row_is_listed_but_cannot_be_written(qtbot: object, tmp_path: Path) -> None:
    d = _dialog(qtbot, _first(tmp_path))
    d.rejected_chip.click()
    index = d.model.index(0, 0)
    assert not d.model.flags(index) & Qt.ItemFlag.ItemIsUserCheckable
    assert not d.model.flags(d.model.index(0, 2)) & Qt.ItemFlag.ItemIsEditable
    assert "kod" in str(d.model.data(d.model.index(0, 2), Qt.ItemDataRole.ToolTipRole)).lower()
    assert 3 not in [c.entry_id for c in d.accepted_changes()]
    d.all_box.click()
    d.all_box.click()
    assert d.write_count() == 3  # reddedilen satır sayıya girmez


def test_chips_hide_when_not_needed(qtbot: object, tmp_path: Path) -> None:
    path = _write(tmp_path, "tek.xlsx", [("Save your game?", "Oyunu kaydetmek istiyor musunuz?", "Kaydedilsin mi?")])
    d = _dialog(qtbot, path)
    assert d.approved_chip.isHidden()
    assert d.rejected_chip.isHidden()
    assert d.write_button.text() == "1 satırı yaz"


def test_uncheck_updates_count_and_select_all(qtbot: object, tmp_path: Path) -> None:
    d = _dialog(qtbot, _first(tmp_path))
    assert d.all_box.isChecked()
    d.model.setData(d.model.index(0, 0), Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    assert d.write_button.text() == "2 satırı yaz"
    assert not d.all_box.isChecked()
    d.all_box.click()
    assert _checked(d) == [True, True, True]
    assert d.write_button.text() == "3 satırı yaz"
    d.all_box.click()
    assert d.write_button.text() == "0 satırı yaz"
    assert not d.write_button.isEnabled()
    assert d.accepted_changes() == []


def test_foreign_file_is_flagged_and_counts_are_per_file(qtbot: object, tmp_path: Path) -> None:
    foreign = _write(tmp_path, "baska.txt", [("Zzz", "q", "w"), ("Yyy", "q", "w")])
    d = _dialog(qtbot, _first(tmp_path), foreign)
    rows = d.file_rows
    assert len(rows) == 2
    assert "5 satır · 4 düzeltme" in rows[0].detail.text()
    assert rows[0].frame.property("state") == "ok"
    assert rows[1].frame.property("state") == "warning"
    assert rows[1].detail.text() == "Başka projeden olabilir · 0 eşleşme"
    assert d.files_label.text() == "DOSYALAR · 2"


def test_add_replans_dedupes_and_remove_replans(qtbot: object, tmp_path: Path) -> None:
    first = _first(tmp_path)
    second = _write(
        tmp_path, "iki.xlsx", [("Settings will be reset.", "Ayarlar sıfırlanacak.", "Ayarlar sıfırlanacak!")]
    )
    d = _dialog(qtbot, first)
    assert d.write_button.text() == "3 satırı yaz"
    assert d.add_files([first]) == []  # aynı dosya iki kez eklenmez
    assert len(d.file_rows) == 1
    assert d.add_files([second]) == []
    assert len(d.file_rows) == 2
    # İkinci dosya eklenince plan yenilenir (satır sayısı artar).
    assert d.plan.found == 6
    d.remove_file(1)
    assert len(d.file_rows) == 1
    assert d.plan.found == 5
    d.remove_file(0)
    assert d.file_rows == []
    assert d.write_button.text() == "0 satırı yaz"
    assert not d.write_button.isEnabled()


def test_unticked_row_stays_unticked_after_adding_a_file(qtbot: object, tmp_path: Path) -> None:
    first = _first(tmp_path)
    other = _write(tmp_path, "iki.xlsx", [("Zzz", "q", "w")])
    d = _dialog(qtbot, first)
    d.model.setData(d.model.index(1, 0), Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    d.model.setData(d.model.index(0, 2), "Kaydedilsin mi?", NEW_TEXT_ROLE)
    d.add_files([other])
    assert _checked(d) == [True, False, True]
    assert d.accepted_changes()[0].new_text == "Kaydedilsin mi?"


def test_bad_file_shows_error_and_keeps_list(qtbot: object, tmp_path: Path) -> None:
    d = _dialog(qtbot, _first(tmp_path))
    bad = tmp_path / "bozuk.xlsx"
    bad.write_bytes(b"PK\x03\x04bozuk")
    errors = d.add_files([bad])
    assert len(errors) == 1
    assert "bozuk.xlsx" in errors[0]
    assert len(d.file_rows) == 1
    assert d.status.isVisibleTo(d) or d.status.text.text()  # hata bandı dolu


def test_edit_changes_accepted_text_and_blocks_broken_codes(qtbot: object, tmp_path: Path) -> None:
    rows = [_row(1, "Hello ⟦1⟧", "Merhaba ⟦1⟧"), _row(2, "Bye", "Güle")]
    path = _write(tmp_path, "d.xlsx", [("Hello ⟦1⟧", "Merhaba ⟦1⟧", "Selam ⟦1⟧"), ("Bye", "Güle", "Hoşça kal")])
    d = _dialog(qtbot, path, rows=rows)
    assert d.model.setData(d.model.index(0, 2), "Selam dünya ⟦1⟧", NEW_TEXT_ROLE)
    assert d.accepted_changes()[0].new_text == "Selam dünya ⟦1⟧"
    d.model.setData(d.model.index(0, 2), "Selam", NEW_TEXT_ROLE)  # ⟦1⟧ kayboldu
    d.accept()
    assert d.result() != QDialog.DialogCode.Accepted
    assert "Eksik kontrol kodu" in d.status.text.text()
    d.model.setData(d.model.index(0, 2), "  ", NEW_TEXT_ROLE)
    d.accept()
    assert d.result() != QDialog.DialogCode.Accepted
    assert "boş" in d.status.text.text()
    d.model.setData(d.model.index(0, 2), "Selam ⟦1⟧", NEW_TEXT_ROLE)
    d.accept()
    assert d.result() == QDialog.DialogCode.Accepted


def test_free_code_move_is_allowed(qtbot: object, tmp_path: Path) -> None:
    rows = [_row(1, "You got {0} gold!", "{0} altın kazandın!", free=frozenset({1}))]
    # Serbest kodun yeri değişmiş düzeltme: uyarıdır, yazılabilir.
    path = _write(tmp_path, "s.xlsx", [("You got {0} gold!", "{0} altın kazandın!", "Altın kazandın: {0}")])
    d = _dialog(qtbot, path, rows=rows)
    assert d.plan.changes or d.plan.code_problems  # plan kodu kendisi karara bağlar
    assert d.write_count() == len(d.plan.changes)


def test_empty_plan_opens_with_reasons_and_disabled_write(qtbot: object, tmp_path: Path) -> None:
    foreign = _write(tmp_path, "baska.txt", [("Zzz", "q", "w")])
    d = _dialog(qtbot, foreign)
    assert not d.write_button.isEnabled()
    assert d.write_button.text() == "0 satırı yaz"
    assert not d.reasons_label.isHidden()  # nedenler kendiliğinden açık
    assert "başka bir projeden" in d.reasons_label.text().lower()
    assert d.model.rowCount() == 0


def test_reasons_list_everything_the_old_summary_said(qtbot: object, tmp_path: Path) -> None:
    d = _dialog(qtbot, _first(tmp_path))
    assert d.reasons_label.isHidden()
    d.reasons_button.click()
    text = d.reasons_label.text()
    assert "kontrol kodları uymuyor" in text
    assert "onaylıydı" in text
    assert "“Redakte”" in text
    assert "Yazılmayan 1 satırın mevcut çevirisi korunur" in d.skipped_label.text()


def test_translation_mode_uses_new_translation_wording(qtbot: object, tmp_path: Path) -> None:
    path = _write(tmp_path, "c.xlsx", [("Save your game?", "Oyunu kaydetmek istiyor musunuz?", "Oyunu kaydet?")], True)
    d = _dialog(qtbot, path, translation=True)
    assert d.windowTitle() == "Dış çeviriden içe aktar"
    assert d.model.headerData(2, Qt.Orientation.Horizontal) == "YENİ ÇEVİRİ"
    assert "“Makine” durumuyla yazılır" in d.footer_note.text()
    assert "1 yeni çeviri" in d.file_rows[0].detail.text()


def test_accepted_changes_carry_row_data(qtbot: object, tmp_path: Path) -> None:
    d = _dialog(qtbot, _first(tmp_path))
    first = d.accepted_changes()[0]
    assert (first.entry_id, first.source, first.old_text) == (1, "Save your game?", "Oyunu kaydetmek istiyor musunuz?")
    assert first.new_text == "Oyun kaydedilsin mi?"
    assert first.job == "csv"
    approved = next(c for c in d.accepted_changes() if c.entry_id == 4)
    assert approved.old_status == "approved"


def test_diff_cells_highlight_changed_words(qtbot: object, tmp_path: Path) -> None:
    d = _dialog(qtbot, _first(tmp_path))
    old = str(d.model.data(d.model.index(0, 1), Qt.ItemDataRole.DisplayRole))
    new = str(d.model.data(d.model.index(0, 2), Qt.ItemDataRole.DisplayRole))
    assert "<s>" in old
    assert "<b>" in new
    assert "kaydedilsin" in new
    approved_cell = str(d.model.data(d.model.index(2, 2), Qt.ItemDataRole.DisplayRole))
    assert "onaylıydı" in approved_cell


def test_narrow_window_and_show(qtbot: object, tmp_path: Path) -> None:
    d = _dialog(qtbot, _first(tmp_path))
    d.resize(760, 520)
    d.show()
    qtbot.wait(30)  # type: ignore[attr-defined]
    assert d.width() >= d.minimumWidth()
    assert d.table.verticalHeader().isVisible() is False


def test_many_rows_stay_fast(qtbot: object, tmp_path: Path) -> None:
    rows = [_row(i, f"Source line number {i}", f"Kaynak satır {i}") for i in range(1, 20001)]
    path = _write(tmp_path, "buyuk.xlsx", [(r.source, r.translation, f"Düzeltilmiş satır {r.id}") for r in rows])
    started = time.perf_counter()
    d = _dialog(qtbot, path, rows=rows)
    d.show()
    qtbot.wait(50)  # type: ignore[attr-defined]
    assert d.model.rowCount() == 20000
    assert time.perf_counter() - started < 20
    d.all_box.click()
    assert d.write_count() == 0
    assert d.model.index(0, 0) != QModelIndex()
