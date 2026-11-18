"""Arayüz: Sığdırma sekmesindeki fontla genişlik denetimi ve çeviri panelindeki genişlik göstergesi."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.checks import SEVERITY_WARNING
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate import widths
from nxceviri.core.translate.fitconfig import BOX_ROW, WidthRules, load_config
from nxceviri.core.translate.fitwidth import KIND_TOO_WIDE, SETTING_WIDTHS
from nxceviri.core.translate.status import Status
from nxceviri.gui.main_window import STEP_QA, STEP_TRANSLATE, MainWindow
from nxceviri.gui.qa_page import QaPage
from nxceviri.gui.theme import ThemeMode, apply_theme
from tests.task_wait import finish_task

pytestmark = pytest.mark.gui

MENU = "Menu.tsv"


def _project() -> Project:
    p = Project.new()
    p.import_texts(
        [
            ImportedFile(
                MENU,
                "0100",
                "unity",
                "base",
                (
                    TextEntry("m01", 0, "New Game", ()),
                    TextEntry("m02", 1, "Load", ()),
                    TextEntry("m03", 2, "Options", ()),
                ),
            ),
            ImportedFile(
                "Dialogue.tsv", "0100", "unity", "base", (TextEntry("d01", 0, "Hello there, how are you?", ()),)
            ),
        ]
    )
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [
            (rows["m01"].id, "Yeni Oyun"),
            (rows["m02"].id, "Kayıtlı Oyunu Yükle"),  # en geniş orijinalden ("New Game") çok daha geniş
            (rows["m03"].id, "Ayarlar"),
            (rows["d01"].id, "Merhaba dostum, bugün nasılsın bakalım?"),  # kapsam dışı: genişlik denetlenmez
        ],
        machine=True,
    )
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.resize(1100, 760)
    w.show()
    yield w
    if w.task is not None:
        w.task.cancel()
        w.task.wait()
    w.dirty = False
    w.close()
    w.deleteLater()


def _page(w: MainWindow) -> QaPage:
    w.nav.setCurrentRow(STEP_QA)
    page = w.qa_page
    page.tabs.setCurrentIndex(page.fit_tab_index())
    return page


def _select_scope(page: QaPage, data: str) -> None:
    index = page.fit_scope.findData(data)
    assert index >= 0
    page.fit_scope.setCurrentIndex(index)


def _rows(w: MainWindow) -> dict[str, TranslationRow]:
    return {r.key: r for r in w.project.translation_rows()}


def _save_shot(widget: QWidget, name: str) -> None:
    """Açık temayla ekran görüntüsü (yalnızca NXTR_SHOTS klasörü verildiyse; testin sonucu buna bağlı değildir).
    Uygulamanın teması görüntüden sonra geri yüklenir."""
    folder = os.environ.get("NXTR_SHOTS")
    if not folder:
        return
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, sheet = app.palette(), app.styleSheet()
    apply_theme(app, ThemeMode.LIGHT)
    QApplication.processEvents()  # bekleyen yerleşim isteği uygulansın
    Path(folder).mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(Path(folder) / name))
    app.setStyleSheet(sheet)
    app.setPalette(palette)


def test_width_controls_persist_to_config_without_char_limits(window: MainWindow) -> None:
    page = _page(window)
    assert not page.fit_enabled.isChecked()
    _select_scope(page, MENU)
    page.fit_width_check.setChecked(True)
    assert page.fit_enabled.isChecked()  # genişliği açmak sığdırmayı açar
    config = load_config(window.project)
    assert config.default is None  # karakter sınırı eklenmedi
    assert config.per_file == {}
    assert config.width_files == {MENU: WidthRules()}
    page.fit_width_tolerance.setValue(25)
    page.fit_width_box.setCurrentIndex(page.fit_width_box.findData(BOX_ROW))
    assert load_config(window.project).width_files == {MENU: WidthRules(True, 0.25, BOX_ROW)}
    # Proje kapsamı ayrı: orada denetim kapalı görünür.
    _select_scope(page, "")
    assert not page.fit_width_check.isChecked()
    assert not page.fit_width_tolerance.isEnabled()
    _select_scope(page, MENU)
    assert page.fit_width_check.isChecked()
    assert page.fit_width_tolerance.value() == 25


def test_width_only_config_survives_reload(window: MainWindow) -> None:
    page = _page(window)
    _select_scope(page, MENU)
    page.fit_width_check.setChecked(True)
    window._refresh_qa()  # projeden yeniden okunur
    assert page.fit_enabled.isChecked()
    _select_scope(page, MENU)
    assert page.fit_width_check.isChecked()


def test_measuring_font_line_names_the_table(window: MainWindow) -> None:
    page = _page(window)
    assert page.fit_width_font.text().startswith("Ölçüm: yaklaşık tablo")
    table = widths.WidthTable({"a": 1.0}, name="Ana SDF", approximate=False)
    window.project.set_setting(SETTING_WIDTHS, widths.dump(table))
    window._refresh_qa()
    assert page.fit_width_font.text() == "Ölçüm: Ana SDF (oyunun fontu)"


def test_check_reports_width_warning_and_does_not_block(window: MainWindow) -> None:
    page = _page(window)
    _select_scope(page, MENU)
    page.fit_width_check.setChecked(True)
    page.check_button.click()
    finish_task(window)
    found = [i for i in page.model.issues if i.kind == KIND_TOO_WIDE]
    rows = _rows(window)
    assert [i.row_id for i in found] == [rows["m02"].id]
    assert found[0].severity == SEVERITY_WARNING
    assert "sınır %115" in found[0].message
    assert "oyunda taşabilir" in found[0].message
    assert not window._qa_errors  # yalnızca uyarı: dışa aktarma engellenmez
    assert rows["m02"].status == Status.MACHINE  # satır "hatalı" işaretlenmez
    assert "1 satır taşıyor" in page.fit_result.text()
    _save_shot(page, "sigdirma_genislik.png")


def test_editor_indicator_follows_scope(window: MainWindow) -> None:
    page = _page(window)
    _select_scope(page, MENU)
    page.fit_width_check.setChecked(True)
    window.nav.setCurrentRow(STEP_TRANSLATE)
    tpage = window.translate_page
    rows = _rows(window)
    tpage.select_row(rows["m02"].id)
    pane = tpage.pane
    assert pane.width_label.isVisibleTo(pane)
    reading = pane.width_reading()
    assert reading is not None
    assert pane.width_label.text() == f"Genişlik %{round(reading.ratio * 100)}"
    assert reading.over
    assert pane.width_label.property("role") == "warning"
    _save_shot(window, "panel_genislik.png")
    pane.translation_edit.setPlainText("Yükle")  # kısalınca uyarı rengi kalkar
    assert pane.width_label.property("role") == "muted"
    tpage.select_row(rows["d01"].id)  # genişlik denetimi olmayan kapsam
    assert not pane.width_label.isVisibleTo(pane)


def test_editor_indicator_hidden_when_width_off(window: MainWindow) -> None:
    window.nav.setCurrentRow(STEP_TRANSLATE)
    tpage = window.translate_page
    tpage.select_row(_rows(window)["m02"].id)
    assert not tpage.pane.width_label.isVisibleTo(tpage.pane)


def test_changing_tolerance_reuses_boxes(window: MainWindow) -> None:
    page = _page(window)
    _select_scope(page, MENU)
    page.fit_width_check.setChecked(True)
    first = window._width_measure()
    assert first is not None
    assert window._width_measure() is first  # ayar değişmedi: aynı nesne (anlık denetim önbelleği korunur)
    page.fit_width_tolerance.setValue(30)
    second = window._width_measure()
    assert second is not None
    assert second is not first
    assert second.boxes is first.boxes  # yalnızca pay değişti: kutular yeniden ölçülmedi
    assert window.translate_page.model.live._context.widths is second
