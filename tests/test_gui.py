"""Arayüz testleri (pytest-qt). Gerçek iş parçacıkları ve elle üretilmiş oyun dosyalarıyla çalışır."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QMimeData, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.core.errors import ProjectError
from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.gui.main_window import STEP_SCAN, STEP_TRANSLATE, MainWindow
from nxceviri.gui.theme import TOKENS, ThemeMode, apply_theme
from nxceviri.gui.translate_page import COL_TRANSLATION
from tests.conftest import GameFiles
from tests.task_wait import finish_task

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.show()
    yield w
    # pytest-qt'nin otomatik kapatması yerine elle kapatırız: "kaydedilmemiş proje" sorusu testi bekletmesin.
    if w.task is not None:
        w.task.cancel()
        w.task.wait()
    w.dirty = False
    w.close()
    w.deleteLater()


def _dirty(w: MainWindow) -> bool:
    return w.dirty


def _wait_idle(qtbot: QtBot, w: MainWindow) -> None:
    qtbot.waitUntil(lambda: w.task is None, timeout=20_000)


def _all_text(w: MainWindow) -> str:
    parts = [w.windowTitle()]
    for child in w.findChildren(QWidget):
        for attr in ("text", "title", "placeholderText"):
            fn = getattr(child, attr, None)
            if callable(fn):
                try:
                    value = fn()
                except TypeError:
                    continue
                if isinstance(value, str):
                    parts.append(value)
    for menu_action in w.menuBar().actions():
        parts.append(menu_action.text())
        menu = menu_action.menu()
        if isinstance(menu, QMenu):
            parts += [a.text() for a in menu.actions()]
    return "\n".join(parts)


def test_only_implemented_steps_visible(window: MainWindow) -> None:
    assert window.nav.count() == 5
    assert [window.nav.item(i).text() for i in range(5)] == [
        "Oyunu Ekle",
        "Metinleri Tara",
        "Çevir",
        "Kontrol Et",
        "Dışa Aktar",
    ]
    text = _all_text(window)
    for hidden in ("yakında", "Yakında", "Font yama", "Fontu yamala"):
        assert hidden not in text  # henüz yapılmamış özellik (font yamalama, M8) görünmez
    # Anahtar yokken tarama adımı, metin yokken çeviri adımı kapalıdır; oyun eklenemez.
    assert not window.nav.item(STEP_SCAN).flags() & Qt.ItemFlag.ItemIsEnabled
    assert not window.nav.item(STEP_TRANSLATE).flags() & Qt.ItemFlag.ItemIsEnabled
    assert not window.nav.item(4).flags() & Qt.ItemFlag.ItemIsEnabled  # dışa aktarma
    assert not window.add_page.drop.isEnabled()
    assert not window.add_page.next_button.isEnabled()


def test_invalid_key_file_shows_error(window: MainWindow, tmp_path: Path) -> None:
    bad = tmp_path / "prod.keys"
    bad.write_text("bu bir anahtar dosyası değil\n", encoding="utf-8")
    assert not window.load_keys_file(bad)
    assert window.status_segments.keys_button.toolTip().startswith("Anahtar geçersiz")
    assert not window.add_page.keys_card.isHidden()
    assert window.add_page.keys_banner.isVisible()
    assert "1. satır" in window.add_page.keys_banner.text.text()


def _drop(window: MainWindow, paths: list[Path]) -> None:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    zone = window.add_page.drop
    event = QDropEvent(
        QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    zone.dropEvent(event)


def test_full_flow_drop_scan_save_reopen(qtbot: QtBot, window: MainWindow, game: GameFiles, tmp_path: Path) -> None:
    assert window.load_keys_file(game.keys_path)
    assert window.status_segments.keys_button.toolTip().startswith("Anahtarlar doğrulandı")
    assert window.add_page.keys_card.isHidden()  # anahtar hazırsa ana ekranda yer kaplamaz
    assert window.add_page.drop.isEnabled()

    _drop(window, [game.base_nsz_block, game.update_nsp, tmp_path / "belge.txt"])
    _wait_idle(qtbot, window)
    assert [s.kind for s in window.sources] == ["base", "update"]
    assert window.add_page.table.rowCount() == 2
    assert window.add_page.next_button.isEnabled()
    assert _dirty(window)

    # Aynı dosyayı yeniden eklemek çift kayıt oluşturmaz.
    window.add_files([game.base_nsz_block])
    assert len(window.sources) == 2

    # "Metinleri Tara" tarama sayfasına geçer ve taramayı hemen başlatır (ikinci düğmeye basmak gerekmez).
    window.add_page.next_button.click()
    assert window.pages.currentIndex() == STEP_SCAN
    assert window.scan_page.stack.currentWidget() is window.scan_page.loading
    _wait_idle(qtbot, window)
    assert window.scan_page.stack.currentWidget() is window.scan_page.report_scroll
    report = window.scan_page.report
    assert report.stat_values["msbt"].text() == "3"
    assert "Deneme Oyunu" in report.game_line.text()
    assert report.proxy.rowCount() > 0
    report.search.setText("yeni_dosya")
    assert report.proxy.rowCount() == 1

    # Metinleri çeviri tablosuna aktar ve düzenle.
    assert report.import_button.isVisible()
    report.import_button.click()
    _wait_idle(qtbot, window)
    assert window.pages.currentIndex() == STEP_TRANSLATE
    page = window.translate_page
    assert page.stack.currentWidget() is page.content
    assert page.model.rowCount() == 6
    assert "Bozuk.msbt" in page.notice_text  # açılamayan dosya bildirildi
    hello = next(i for i, r in enumerate(page.model.rows) if r.key == "Menu_Hello")
    idx = page.model.index(hello, COL_TRANSLATION)
    assert page.model.setData(idx, "Merhaba ⟦1⟧Link⟦2⟧!")
    assert page.model.rows[hello].status == "approved"
    assert page.model.setData(idx, "Merhaba Link!")  # kontrol kodları silindi
    assert page.model.rows[hello].status == "error"
    assert "Eksik kontrol kodu" in page.model.rows[hello].note
    page.search.setText("wait")
    assert page.proxy.rowCount() == 1
    page.table.selectAll()
    page.copy_source_selected()
    wait_row = next(r for r in page.model.rows if r.key == "Wait")
    assert (wait_row.translation, wait_row.status) == ("Please wait⟦1⟧", "approved")
    page.search.clear()
    page.status_filter.setCurrentIndex(page.status_filter.findData("error"))
    assert page.proxy.rowCount() == 1

    target = tmp_path / "Projelerim ğüş" / "Deneme Çeviri.nxproj"
    assert window.save_to(target)
    assert not _dirty(window)
    assert "Deneme Çeviri" in window.windowTitle()

    window.new_project()
    assert (window.sources, window.report) == ([], None)

    assert window.open_project(target)
    assert [s.kind for s in window.sources] == ["base", "update"]
    assert window.report is not None
    window.nav.setCurrentRow(STEP_SCAN)
    assert window.scan_page.stack.currentWidget() is window.scan_page.report_scroll
    reopened = {r.key: r for r in window.translate_page.model.rows}
    assert reopened["Menu_Hello"].status == "error"
    assert reopened["Wait"].translation == "Please wait⟦1⟧"
    assert window.nav.item(STEP_TRANSLATE).flags() & Qt.ItemFlag.ItemIsEnabled


def test_scan_cancel_returns_to_empty(qtbot: QtBot, window: MainWindow, game: GameFiles) -> None:
    window.load_keys_file(game.keys_path)
    window.add_files([game.base_nsp])
    _wait_idle(qtbot, window)
    window.start_scan()
    window.scan_page.loading.cancel.click()  # iptal hemen istenir; iş parçacığı ilk kontrolde durur
    _wait_idle(qtbot, window)
    assert window.report is None
    assert window.scan_page.stack.currentWidget() in (window.scan_page.empty, window.scan_page.report_scroll)


def test_scan_error_state(qtbot: QtBot, window: MainWindow, game: GameFiles, tmp_path: Path) -> None:
    window.load_keys_file(game.keys_path)
    copy = tmp_path / "geçici kopya.nsp"
    copy.write_bytes(game.base_nsp.read_bytes())
    window.add_files([copy])
    _wait_idle(qtbot, window)
    copy.write_bytes(copy.read_bytes()[:0x4000])  # dosya sonradan bozuldu
    window.start_scan()
    _wait_idle(qtbot, window)
    assert window.scan_page.stack.currentWidget() is window.scan_page.error
    assert window.scan_page.error.banner.text.text()


def test_update_without_base_blocks_scan(qtbot: QtBot, window: MainWindow, game: GameFiles) -> None:
    window.load_keys_file(game.keys_path)
    window.add_files([game.update_nsp])
    _wait_idle(qtbot, window)
    assert not window.add_page.next_button.isEnabled()
    assert "ana oyunu" in window.add_page.files_banner.text.text()
    window.add_page.remove_source.emit(0)
    assert window.sources == []


def test_bad_package_reports_error(qtbot: QtBot, window: MainWindow, game: GameFiles, tmp_path: Path) -> None:
    window.load_keys_file(game.keys_path)
    bad = tmp_path / "bozuk.nsp"
    bad.write_bytes(b"\0" * 100)
    window.add_files([bad])
    _wait_idle(qtbot, window)
    assert window.sources == []
    assert "bozuk.nsp" in window.add_page.files_banner.text.text()


def test_close_unsaved_asks(qtbot: QtBot, window: MainWindow, game: GameFiles, monkeypatch: pytest.MonkeyPatch) -> None:
    window.load_keys_file(game.keys_path)
    window.add_files([game.base_nsp])
    _wait_idle(qtbot, window)
    asked: list[str] = []

    def fake_question(*args: object, **_kw: object) -> QMessageBox.StandardButton:
        asked.append(str(args[1]))
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", fake_question)
    window.close()
    assert asked == ["Kaydedilmemiş proje"]
    assert window.isVisible()


def test_close_keeps_window_when_pending_pane_text_cannot_be_saved(
    qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.project.import_texts(
        [ImportedFile("Menu.tsv", "0100", "unity", "base", (TextEntry("m01", 0, "Start", ()),))]
    )
    window._reload_rows()
    page = window.translate_page
    page._select_proxy_row(0)
    page.pane.translation_edit.setPlainText("Başla")

    def fail(changes: list[tuple[int, str]]) -> list[object]:
        raise ProjectError("Proje dosyasına yazılamadı.", "Diskte yer olduğundan emin olun.")

    monkeypatch.setattr(window.project, "set_translations", fail)
    window.dirty = False  # kapanış sorusu çıkmasın; kayıp yalnızca panel metninden gelebilir
    window.close()
    assert window.isVisible()  # kapanma iptal edildi
    assert page.pane.translation_edit.toPlainText() == "Başla"
    assert "yazılamadı" in page.pane.error_label.text()
    monkeypatch.undo()
    assert page.flush_pending()  # hata giderilince kayıt geçer; fixture kapanışta soru çıkmasın
    window.dirty = False


def test_project_switch_keeps_old_project_when_pending_pane_text_cannot_be_saved(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = Project.new()
    other_path = tmp_path / "Diğer.nxproj"
    other.save_as(other_path)
    other.close()
    window.project.import_texts(
        [ImportedFile("Menu.tsv", "0100", "unity", "base", (TextEntry("m01", 0, "Start", ()),))]
    )
    window._reload_rows()
    old_project = window.project
    page = window.translate_page
    page._select_proxy_row(0)
    page.pane.translation_edit.setPlainText("Başla")

    def fail(changes: list[tuple[int, str]]) -> list[object]:
        raise ProjectError("Proje dosyasına yazılamadı.", "Diskte yer olduğundan emin olun.")

    monkeypatch.setattr(old_project, "set_translations", fail)
    window.dirty = False  # soru çıkmasın; kayıp yalnızca panel metninden gelebilir
    window.new_project()
    assert window.project is old_project
    assert not window.open_project(other_path)
    assert window.project is old_project
    assert page.pane.translation_edit.toPlainText() == "Başla"
    assert "yazılamadı" in page.pane.error_label.text()
    monkeypatch.undo()
    assert page.flush_pending()
    window.dirty = False


@pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
def test_themes_apply(qtbot: QtBot, mode: ThemeMode) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    old_font, old_palette, old_style = app.font(), app.palette(), app.styleSheet()
    try:
        scheme = apply_theme(app, mode)
        assert scheme == mode.value
        assert TOKENS[scheme]["bg"] in app.styleSheet()
    finally:
        # Tema uygulaması uygulama genelindedir; sonraki testlerin ölçülerini etkilememesi için geri alınır.
        app.setFont(old_font)
        app.setPalette(old_palette)
        app.setStyleSheet(old_style)


def test_machine_translation_flow(qtbot: QtBot, window: MainWindow, game: GameFiles) -> None:
    from nxceviri.core.translate.providers.base import GlossaryTerm
    from nxceviri.gui.machine_dialogs import SCOPE_ALL, GlossaryDialog, MachineDialog, MachineSettings
    from tests.fake_ollama import FakeOllama

    window.load_keys_file(game.keys_path)
    window.add_files([game.base_nsp, game.update_nsp])
    _wait_idle(qtbot, window)
    window.start_scan()
    _wait_idle(qtbot, window)
    window.import_texts()
    _wait_idle(qtbot, window)
    page = window.translate_page
    rows = {r.key: r for r in page.model.rows}
    page.model.setData(page.model.index(page.model.rows.index(rows["Yes"]), COL_TRANSLATION), "Evet")

    server = FakeOllama()
    window.provider_factory = lambda s: server.provider(s.model)
    asked: list[tuple[int, int, str, str]] = []

    def settings(scopes: dict[str, list[Any]], action: str = "translate", scope: str = SCOPE_ALL) -> MachineSettings:
        asked.append((len(scopes[SCOPE_ALL]), len(scopes["selected"]), action, scope))
        return MachineSettings("ollama", "http://localhost:11434", "gemma4:12b", "Deneme notu", SCOPE_ALL)

    window.ask_machine_settings = settings  # type: ignore[assignment]
    page.machine_button.click()
    assert page.run_panel.isVisibleTo(window)
    _wait_idle(qtbot, window)
    assert not page.run_panel.isVisibleTo(window)
    assert asked == [(6, 0, "translate", SCOPE_ALL)]
    after = {r.key: r for r in page.model.rows}
    assert after["Menu_Hello"].translation == "tr-Hello ⟦1⟧tr-Link⟦2⟧!"
    assert after["Menu_Hello"].status == "machine"
    assert after["Yes"].translation == "Evet"  # onaylanan satıra dokunulmadı
    assert window.notifier.history[0].title == "Otomatik çeviri bitti"
    assert page.status_filter.findData("machine") > 0  # makine satırları olunca filtrede görünür
    assert window.project.setting("translation_notes") == "Deneme notu"

    # Ollama kapalıysa anlaşılır hata ve hiçbir satır değişmez.
    window.provider_factory = lambda s: FakeOllama(down=True).provider(s.model)
    page.machine_button.click()
    _wait_idle(qtbot, window)
    last = window.notifier.history[0]
    assert "bağlanılamadı" in last.title + last.text

    # Sözlük penceresi: boş satırlar kaydedilmez.
    dialog = GlossaryDialog(window, [GlossaryTerm("Link", "Link", "ad")])
    dialog._add("Sheriff", "Şerif", "")
    dialog._add("", "boş", "")
    assert dialog.terms() == [GlossaryTerm("Link", "Link", "ad"), GlossaryTerm("Sheriff", "Şerif", "")]
    from nxceviri.core.secrets import DEEPL_API_KEY, MemoryStore
    from nxceviri.gui.machine_dialogs import PROVIDER_DEEPL
    from nxceviri.gui.settings_dialog import DeepLKeyPanel

    secrets = MemoryStore()
    done_rows = [r for r in page.model.rows if r.translation]
    machine = MachineDialog(
        window,
        provider="ollama",
        base_url="",
        model="",
        notes="",
        source_language="en",
        secrets=secrets,
        scopes={SCOPE_ALL: done_rows},
    )
    assert not machine.start.isEnabled()  # yapılacak iş yok: hepsi çevrilmiş

    # DeepL: anahtar yokken başlatılamaz; ayarlardan kaydedilince seçilebilir.
    deepl = MachineDialog(
        window,
        provider=PROVIDER_DEEPL,
        base_url="",
        model="",
        notes="",
        source_language="en",
        secrets=secrets,
        scopes={SCOPE_ALL: page.model.rows},
        action="retranslate",
    )
    assert deepl.provider_name == PROVIDER_DEEPL
    assert not deepl.ollama_box.isVisibleTo(deepl)
    assert not deepl.start.isEnabled()
    settings_dialog = DeepLKeyPanel(secrets)
    qtbot.addWidget(settings_dialog)
    assert settings_dialog.state.text() == "Kayıtlı anahtar: yok"
    settings_dialog.key.setText("deneme-anahtar:fx")
    settings_dialog.save_key()
    assert secrets.get(DEEPL_API_KEY) == "deneme-anahtar:fx"
    assert settings_dialog.state.text() == "Kayıtlı anahtar: var (DeepL API Free)"
    assert settings_dialog.key.text() == ""
    settings_dialog.delete_key()
    assert secrets.get(DEEPL_API_KEY) is None


def test_qa_and_export_flow(qtbot: QtBot, window: MainWindow, game: GameFiles, tmp_path: Path) -> None:
    from nxceviri.gui.main_window import STEP_EXPORT, STEP_QA

    window.load_keys_file(game.keys_path)
    window.add_files([game.base_nsp, game.update_nsp])
    _wait_idle(qtbot, window)
    window.start_scan()
    _wait_idle(qtbot, window)
    window.import_texts()
    _wait_idle(qtbot, window)
    page = window.translate_page
    rows = {r.key: r for r in page.model.rows}
    page.model.apply([(rows["Menu_Start"].id, "Maceraya Başla"), (rows["Wait"].id, "Bekleyin")])

    window.nav.setCurrentRow(STEP_QA)
    qa = window.qa_page
    window.scan_fonts()
    _wait_idle(qtbot, window)
    assert "font bulunamadı" in qa.font_banner.text.text()  # deneme oyununda font yok
    qa.check_button.click()
    finish_task(window)
    assert "1 hata" in qa.summary.text()
    assert qa.proxy.rowCount() == 1  # bilgiler (çevrilmedi) varsayılan olarak gizli
    assert qa.proxy.index(0, 4).data() == "Bekleyin"  # bulguda çeviri metni görünür
    page.search.setText("Maceraya")  # filtre hedef satırı gizlese bile tam o satır açılır
    qa.table.doubleClicked.emit(qa.proxy.index(0, 0))
    assert window.pages.currentIndex() == STEP_TRANSLATE
    assert page.search.text() == ""
    opened = page.current_row()
    assert opened is not None
    assert opened.id == rows["Wait"].id

    window.nav.setCurrentRow(STEP_QA)
    qa.mode_buttons["all"].setChecked(True)
    assert window.project.setting("transliterate_mode") == "all"

    window.nav.setCurrentRow(STEP_EXPORT)
    export = window.export_page
    export.folder.setText(str(tmp_path / "Çıktılar"))
    export.mod_name.setText("Deneme Türkçe")
    assert export.export_button.isEnabled()
    assert export.summary.text().startswith("1 yazılacak")
    export.export_button.click()
    _wait_idle(qtbot, window)
    assert "Mod oluşturuldu" in export.result.text.text()
    out = tmp_path / "Çıktılar" / "Deneme Türkçe" / "atmosphere" / "contents"
    written = [p for p in out.rglob("*") if p.is_file()]
    assert [p.name for p in written] == ["Ana_Menü.msbt"]
    from nxceviri.core.formats.msbt import MsbtPlugin

    assert MsbtPlugin().extract(written[0].read_bytes())[0].source == "Maceraya Basla"
    # Aynı klasöre ikinci kez üretmek sorulur: Vazgeç hiçbir şeye dokunmaz, Üzerine Yaz eski modu değiştirir.

    answers = ["Vazgeç", "Üzerine Yaz"]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("nxceviri.gui.main_window.choose_button", lambda _p, _t, _b: answers.pop(0))
        stamp = written[0].stat().st_mtime_ns
        export.export_button.click()
        assert window.task is None  # vazgeçildi: iş başlamadı
        assert written[0].stat().st_mtime_ns == stamp
        export.export_button.click()
        _wait_idle(qtbot, window)
    assert "Mod oluşturuldu" in export.result.text.text()
    assert not answers


def test_qt_standard_texts_are_turkish(qtbot: QtBot) -> None:
    """Qt'nin kendi metinleri (düzenleme menüsü, standart düğmeler) Türkçe olur."""
    from PySide6.QtWidgets import QDialogButtonBox, QPlainTextEdit

    from nxceviri.gui.app import install_qt_translations

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    translator = install_qt_translations(app)
    assert translator is not None
    try:
        edit = QPlainTextEdit()
        qtbot.addWidget(edit)
        menu = edit.createStandardContextMenu()
        texts = " ".join(a.text().replace("&", "") for a in menu.actions())
        assert "Kopyala" in texts
        assert "Yapıştır" in texts
        assert "Copy" not in texts
        assert "Paste" not in texts
        yes = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        qtbot.addWidget(yes)
        assert yes.button(QDialogButtonBox.StandardButton.Yes).text().replace("&", "") == "Evet"
    finally:
        app.removeTranslator(translator)


def test_shortcut_key_names_stay_short_english(qtbot: QtBot) -> None:
    """Menü kısayollarında "Kontrol+Üst Karakter" yerine Windows'taki gibi "Ctrl+Shift" görünür."""
    from PySide6.QtGui import QKeySequence

    from nxceviri.gui.app import install_qt_translations

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    translator = install_qt_translations(app)
    assert translator is not None
    try:
        native = QKeySequence.SequenceFormat.NativeText
        assert QKeySequence("Ctrl+Shift+A").toString(native) == "Ctrl+Shift+A"
        assert QKeySequence("Alt+Del").toString(native) == "Alt+Del"
        assert QKeySequence("PgDown").toString(native) == "PgDown"
        from nxceviri.gui.shortcuts import display_text

        assert display_text(QKeySequence("Ctrl+Shift+T")) == "Ctrl+Shift+T"
        # Tuş adı olmayan Qt metinleri Türkçe kalır.
        assert QApplication.translate("QShortcut", "Print") != "Print"
    finally:
        app.removeTranslator(translator)


def test_row_context_menu_translates_selected(
    qtbot: QtBot, window: MainWindow, game: GameFiles, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.load_keys_file(game.keys_path)
    window.add_files([game.base_nsp, game.update_nsp])
    _wait_idle(qtbot, window)
    window.start_scan()
    _wait_idle(qtbot, window)
    window.import_texts()
    _wait_idle(qtbot, window)
    page = window.translate_page
    page.table.selectRow(0)
    page._show_context_menu(page.table.visualRect(page.proxy.index(0, 0)).center())
    menu = page.table.findChild(QMenu)
    assert menu is not None
    translate = menu.actions()[0].menu()
    assert isinstance(translate, QMenu)
    items = translate.actions()
    assert [a.text().split("\t", maxsplit=1)[0] for a in items] == ["Çevir (1)", "Yeniden çevir (1)", "Redaksiyon (1)"]
    assert all(a.isEnabled() for a in items)

    asked: list[tuple[str, str, int]] = []

    def settings(scopes: dict[str, list[Any]], action: str = "translate", scope: str = "all") -> None:
        asked.append((action, scope, len(scopes["selected"])))

    window.ask_machine_settings = settings  # type: ignore[assignment]
    items[0].trigger()
    items[1].trigger()
    assert asked == [("translate", "selected", 1), ("retranslate", "selected", 1)]
    menu.close()


def test_uppercase_marking_from_context_menu(qtbot: QtBot, window: MainWindow, game: GameFiles) -> None:
    window.load_keys_file(game.keys_path)
    window.add_files([game.base_nsp, game.update_nsp])
    _wait_idle(qtbot, window)
    window.start_scan()
    _wait_idle(qtbot, window)
    window.import_texts()
    _wait_idle(qtbot, window)
    page = window.translate_page
    page.table.selectRow(0)
    page._show_context_menu(page.table.visualRect(page.proxy.index(0, 0)).center())
    menu = page.table.findChild(QMenu)
    assert menu is not None
    upper = next(x.menu() for x in menu.actions() if x.text() == "Büyük harf")
    assert isinstance(upper, QMenu)
    by_text = {a.text(): a for a in upper.actions() if a.text()}
    row_action = by_text["Seçili satırlar (i → İ)"]
    assert row_action.isCheckable()
    assert not row_action.isChecked()
    group_action = next(a for t, a in by_text.items() if t.endswith("tablosunun tamamı"))
    group_action.trigger()
    rules = window.project.uppercase_rules()
    assert len(rules.groups) == 1
    assert window._dirty if hasattr(window, "_dirty") else window.dirty
    assert page.model.data(page.model.index(0, 4)).startswith("⇧ ")
    menu.close()


def test_recovery_copy_is_offered_and_restored(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    crashed = MainWindow(settings)
    crashed.project.import_texts(
        [ImportedFile("Menu.tsv", "0100", "unity", "base", (TextEntry("m01", 0, "Start", ()),))]
    )
    crashed.project.set_game("Deneme Oyunu", "0100")
    crashed._mark_changed()
    crashed.write_recovery()
    copy = crashed.recovery.path
    assert copy.is_file()
    crashed.recovery._lock.unlock()  # type: ignore[union-attr]  # süreç çökmüş gibi: kilit bırakıldı
    crashed.recovery._lock = None
    crashed.recovery.path = tmp_path / "yok.nxproj"  # çökmüş pencere kapanırken kopyayı silmesin

    w = MainWindow(settings)
    qtbot.addWidget(w)
    offered: list[str] = []

    def ask(newest: object, count: int) -> str:
        offered.append(str(newest))
        return "recover"

    w.ask_recovery = ask  # type: ignore[method-assign]
    assert w.offer_recovery()
    assert "Deneme Oyunu" in offered[0]
    assert [r.key for r in w.project.translation_rows()] == ["m01"]
    assert w.project.path is None
    assert w.dirty
    assert not copy.exists()  # eski kopya devralındı
    assert w.recovery.path.is_file()

    target = tmp_path / "Kurtarılan.nxproj"
    assert w.save_to(target)
    assert not w.recovery.path.exists()  # kaydedilince kurtarma kopyası silinir
    assert w.recent_projects() == [target]
    w._fill_recent_menu()
    assert w.recent_menu.actions()[0].text() == "&1  Kurtarılan"
    crashed.dirty = w.dirty = False
    crashed.close()
    w.close()


def test_recovery_keeps_old_copy_when_new_copy_cannot_be_written(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    crashed = MainWindow(settings)
    crashed._mark_changed()
    crashed.write_recovery()
    copy = crashed.recovery.path
    assert copy.is_file()
    crashed.recovery._lock.unlock()  # type: ignore[union-attr]  # süreç çökmüş gibi: kilit bırakıldı
    crashed.recovery._lock = None
    crashed.recovery.path = tmp_path / "yok.nxproj"  # çökmüş pencere kapanırken kopyayı silmesin

    w = MainWindow(settings)
    qtbot.addWidget(w)
    monkeypatch.setattr(w.recovery, "write", lambda project: False)  # disk dolu / izin yok
    w.ask_recovery = lambda newest, count: "recover"  # type: ignore[method-assign]
    assert w.offer_recovery()  # proje yine kurtarılmış sayılır
    assert copy.is_file()  # yeni kopya yazılamadığı için eskisi diskte kalır
    assert w._recovery_due  # zamanlayıcı yeniden dener
    crashed.dirty = w.dirty = False
    crashed.close()
    w.close()


def test_open_window_recovery_copy_is_not_offered(tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    first = MainWindow(settings)
    first._mark_changed()
    first.write_recovery()
    second = MainWindow(settings)
    assert second.offer_recovery() is False  # ilk pencere hâlâ açık; kopyası onun
    first.dirty = second.dirty = False
    first.close()
    second.close()
    assert not first.recovery.path.exists()


def test_next_step_shows_existing_report_without_rescanning(qtbot: QtBot, window: MainWindow, game: GameFiles) -> None:
    window.load_keys_file(game.keys_path)
    window.add_files([game.base_nsp])
    _wait_idle(qtbot, window)
    window.add_page.next_button.click()
    _wait_idle(qtbot, window)
    report = window.report
    assert report is not None
    window.nav.setCurrentRow(0)
    window.add_page.next_button.click()  # rapor güncel: yeniden taranmaz
    assert window.scan_page.stack.currentWidget() is window.scan_page.report_scroll
    assert window.report is report


def test_keys_menu_lives_under_file_menu(window: MainWindow, game: GameFiles, tmp_path: Path) -> None:
    file_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Dosya")
    assert isinstance(file_menu, QMenu)
    keys_menu = next(a.menu() for a in file_menu.actions() if a.text() == "Anahtarlar")
    assert isinstance(keys_menu, QMenu)
    texts = [a.text() for a in keys_menu.actions() if not a.isSeparator()]
    assert texts == ["prod.keys Seç…", "title.keys Seç…", "title.keys Dosyasını Kaldır"]
    window.load_keys_file(game.keys_path)
    assert not window.title_keys_clear_action.isEnabled()
    title = tmp_path / "title.keys"
    title.write_text("01000000000100000000000000000000 = " + "00" * 16 + "\n", encoding="utf-8")
    assert window.load_title_keys_file(title)
    assert window.title_keys_clear_action.isEnabled()
    assert "title.keys" in window.status_segments.keys_button.toolTip()
    window._clear_title_keys()
    assert not window.title_keys_clear_action.isEnabled()


def test_scan_page_diagnosis_report(
    qtbot: QtBot, window: MainWindow, game: GameFiles, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QFileDialog

    from nxceviri.arac.teshis import RAPOR_ADI, UYARI

    assert window.load_keys_file(game.keys_path)
    _drop(window, [game.base_nsp])
    _wait_idle(qtbot, window)
    window.add_page.next_button.click()
    _wait_idle(qtbot, window)
    page = window.scan_page
    assert not hasattr(page.report, "more_button")  # sayfadaki "Daha Fazla" kalktı; işler Araçlar menüsünde
    tools = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Araçlar")
    assert isinstance(tools, QMenu)
    entries = [a for a in tools.actions() if a.text() and not a.menu()]
    assert [a.text() for a in entries[:3]] == ["Metin Adaylarını Çıkar…", "Tüm RomFS'i Çıkar…", "Teşhis Raporu…"]
    assert all(a.isEnabled() for a in entries[:3])  # tarama raporu var

    hedef = tmp_path / "rapor klasörü"
    hedef.mkdir()
    acilan: list[str] = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(hedef))

    def url_ac(url: QUrl) -> bool:
        acilan.append(url.toLocalFile())
        return True

    monkeypatch.setattr(QDesktopServices, "openUrl", url_ac)
    entries[2].trigger()
    assert page.stack.currentWidget() is page.loading
    _wait_idle(qtbot, window)
    assert (hedef / RAPOR_ADI).is_file()
    assert page.stack.currentWidget() is page.report_scroll
    bildirim = window.notifier.history[0]  # bilgi penceresi değil, bildirim
    assert str(hedef / RAPOR_ADI) in bildirim.text
    assert UYARI in bildirim.text
    assert [Path(a) for a in acilan] == [hedef]
