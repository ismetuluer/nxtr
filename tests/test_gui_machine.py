"""Arayüz: yeniden çeviri, talimatla düzeltme, otomatik düzeltme ve uygulama güncellemesi."""

from __future__ import annotations

import io
import tempfile
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.secrets import DEEPL_API_KEY, GITHUB_UPDATE_KEY, MemoryStore
from nxceviri.core.selfupdate import PACKAGE_EXE, WORK_DIR_NAME, PreparedInstall
from nxceviri.core.translate import runner as runner_module
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.status import Status
from nxceviri.core.update import RELEASES_URL, pending_version
from nxceviri.gui import main_window as main_window_module
from nxceviri.gui.machine_dialogs import (
    PROVIDER_DEEPL,
    PROVIDER_OLLAMA,
    SCOPE_ALL,
    SCOPE_GROUPS,
    SCOPE_SELECTED,
    MachineDialog,
    MachineSettings,
)
from nxceviri.gui.main_window import STEP_TRANSLATE, MainWindow
from nxceviri.gui.update_dialog import AUTO_CHECK_KEY, UpdateDialog, auto_check_enabled
from tests.fake_ollama import FakeOllama
from tests.test_update import TOKEN, FakeGitHub

pytestmark = pytest.mark.gui

LINES = [
    ("s01", "Have a drink with me."),
    ("s02", "That's the limit!"),
    ("s03", "Not me."),
    ("s04", "Press ⟦1⟧ to jump."),
    ("s05", "Talk to the Sheriff. "),
]


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "RETRY_DELAYS_S", (0.0, 0.0))


def _project() -> Project:
    p = Project.new()
    p.import_texts(
        [
            ImportedFile(
                "Dialogue.tsv", "0100", "unity", "base", tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(LINES))
            ),
            ImportedFile("Menu.tsv", "0100", "unity", "base", (TextEntry("m01", 0, "Start", ()),)),
        ]
    )
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [
            (rows["s01"].id, "Benimle bir içki iç."),
            (rows["s02"].id, "Bu limit!"),
            (rows["s03"].id, "Ben değil."),
            (rows["s04"].id, "Zıplamak için bas."),  # kontrol kodu eksik → hatalı
            (rows["s05"].id, "Polisle konuş."),  # sözlük ve sondaki boşluk sorunu
        ],
        machine=True,
    )
    p.set_glossary([GlossaryTerm("Sheriff", "Şerif")])
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.show()
    yield w
    if w.task is not None:
        w.task.cancel()
        w.task.wait()
    w.dirty = False
    w.close()
    w.deleteLater()


def _wait_idle(qtbot: QtBot, w: MainWindow) -> None:
    qtbot.waitUntil(lambda: w.task is None, timeout=20_000)


def _rows(w: MainWindow) -> dict[str, TranslationRow]:
    return {r.key: r for r in w.project.translation_rows()}


def _select(w: MainWindow, keys: set[str]) -> None:
    page = w.translate_page
    page.table.clearSelection()
    for i in range(page.proxy.rowCount()):
        row = page.model.rows[page.proxy.mapToSource(page.proxy.index(i, 0)).row()]
        if row.key in keys:
            page.table.selectionModel().select(
                page.proxy.index(i, 0),
                page.table.selectionModel().SelectionFlag.Select | page.table.selectionModel().SelectionFlag.Rows,
            )


def _dialog(w: MainWindow, scopes: Mapping[str, Sequence[TranslationRow]], **kw: Any) -> MachineDialog:
    return MachineDialog(
        w,
        provider=kw.pop("provider", PROVIDER_OLLAMA),
        base_url="",
        model="gemma4:12b",
        notes="",
        source_language="en",
        secrets=w.secrets,
        scopes=scopes,
        **kw,
    )


def test_machine_dialog_actions_and_scopes(window: MainWindow) -> None:
    _select(window, {"s03"})
    scopes = window._machine_scopes()
    assert [r.key for r in scopes[SCOPE_SELECTED]] == ["s03"]
    assert {r.key for r in scopes[SCOPE_GROUPS]} == {"s01", "s02", "s03", "s04", "s05"}
    assert scopes["filtered"] == []  # filtre yok: ayrı kapsam gösterilmez

    dialog = _dialog(window, scopes, action="retranslate", scope=SCOPE_SELECTED)
    assert dialog.start.text() == "Yeniden Çevir"
    assert not dialog.instruction.isVisibleTo(dialog)  # çeviri talimatı isteğe bağlı: Gelişmiş kapalıyken gizli
    dialog.advanced_toggle.setChecked(True)
    assert dialog.instruction.isVisibleTo(dialog)
    assert dialog.instruction.toPlainText() == ""
    assert [r.key for r in dialog.target()] == ["s03"]
    labels = [dialog.scope.itemText(i) for i in range(dialog.scope.count())]
    assert labels[0] == "Seçili satırlar — 1 satır"
    assert labels[1].startswith("Seçili satırların grubu (Dialogue.tsv) — 5 satır")

    dialog.action_buttons["translate"].setChecked(True)  # çevir: yalnızca çevrilmemiş/hatalı
    assert dialog.start.text() == "Çeviriyi Başlat"
    assert not dialog.include_approved.isEnabled()
    dialog.scope.setCurrentIndex(dialog.scope.findData(SCOPE_ALL))
    assert sorted(r.key for r in dialog.target()) == ["m01", "s04"]

    dialog.action_buttons["revise"].setChecked(True)
    assert dialog.instruction.isVisibleTo(dialog)
    dialog._accept()  # talimat boş: başlamaz, uyarır
    assert "talimat" in dialog.status.text.text()
    dialog.instruction.setPlainText("Zamirleri at.")
    settings = dialog.settings()
    assert (settings.action, settings.scope, settings.instruction) == ("revise", SCOPE_ALL, "Zamirleri at.")

    # DeepL talimat izleyemez: redaksiyon başlatılamaz.
    window.secrets.set(DEEPL_API_KEY, "anahtar:fx")
    deepl = _dialog(window, scopes, provider=PROVIDER_DEEPL, action="revise")
    assert not deepl.start.isEnabled()
    assert "DeepL talimat izleyemez" in deepl.status.text.text()
    deepl.action_buttons["retranslate"].setChecked(True)
    assert deepl.start.isEnabled()


def test_retranslate_and_revise_selected_rows(qtbot: QtBot, window: MainWindow) -> None:
    server = FakeOllama(translate=lambda t: {"Not me.": "Ben içmem."}.get(t, "tr-" + t))
    window.provider_factory = lambda s: server.provider(s.model)
    window.project.set_translations([(_rows(window)["s02"].id, "Bu kadarı da fazla!")])  # onaylı
    window.translate_page.set_rows(window.project.translation_rows())
    answers: list[MachineSettings] = []

    def ask(
        scopes: Mapping[str, Sequence[TranslationRow]],
        action: str = "translate",
        scope: str = SCOPE_ALL,
    ) -> MachineSettings | None:
        return answers.pop(0)

    window.ask_machine_settings = ask  # type: ignore[method-assign]
    _select(window, {"s02", "s03"})
    answers.append(MachineSettings("ollama", "", "gemma4:12b", "Aile dramı.", SCOPE_SELECTED, "retranslate"))
    window.start_machine_translation("retranslate", from_selection=True)
    _wait_idle(qtbot, window)
    rows = _rows(window)
    assert rows["s03"].translation == "Ben içmem."  # bellek atlandı, çeviri silinmeden yenilendi
    assert rows["s02"].translation == "Bu kadarı da fazla!"  # onaylı satıra dokunulmadı
    assert "Yeniden çeviri bitti: 1 satırın" in window.translate_page.banner.text.text()

    _select(window, {"s02", "s03"})
    answers.append(
        MachineSettings("ollama", "", "gemma4:12b", "", SCOPE_SELECTED, "revise", "Doğal yaz.", include_approved=True)
    )
    window.start_machine_translation("revise", from_selection=True)
    _wait_idle(qtbot, window)
    rows = _rows(window)
    assert rows["s02"].translation == "dz-That'dz-s dz-the dz-limit!"
    assert rows["s02"].status == Status.MACHINE  # kullanıcı onaylılara da uygulamayı seçti
    assert window.project.setting("revise_instruction") == "Doğal yaz."
    assert "Düzeltme bitti: 2 satır düzeltildi" in window.translate_page.banner.text.text()


def _update_dialog(window: MainWindow, root: Path, server: FakeGitHub, **kwargs: Any) -> UpdateDialog:
    return UpdateDialog(
        window,
        secrets=window.secrets,
        settings=window.settings,
        current="0.28.0",
        root=root,
        updater_factory=server.updater,
        **kwargs,
    )


def test_update_dialog_public_repo_needs_no_key(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    root = tmp_path / "uygulama"
    (root / "nxceviri").mkdir(parents=True)
    server = FakeGitHub(version="99.0.0")
    dialog = _update_dialog(window, root, server)
    assert not dialog.key_box.isVisibleTo(dialog)  # anahtar adımları baştan görünmez
    window.secrets.set(GITHUB_UPDATE_KEY, "github_pat_x")  # eski bir kayıtlı anahtar olsa bile
    dialog.check_now()
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    assert "Yeni sürüm var: 99.0.0" in dialog.status.text.text()
    assert not dialog.key_box.isVisibleTo(dialog)
    assert all("Authorization" not in r.headers for r in server.requests)
    assert "99.0.0 notları" in dialog.notes.toPlainText()  # sürüm açıklaması (markdown) gösterilir
    assert "##" not in dialog.notes.toPlainText()  # başlık işaretleri biçimlendirilmiş görünür
    with qtbot.waitSignal(dialog.accepted, timeout=10_000):
        dialog.install.click()
    assert pending_version(root) == "99.0.0"


def test_update_dialog_private_repo_shows_key_steps_then_checks(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    server = FakeGitHub(version="99.0.0", private=True)
    dialog = _update_dialog(window, tmp_path, server)
    dialog.check_now()
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    assert dialog.key_box.isVisibleTo(dialog)  # anahtarsız erişim başarısız: adımlar görünür
    assert "anahtarı gerekir" in dialog.status.text.text()
    assert dialog.key_state.text() == "Kayıtlı anahtar: yok"
    assert not dialog.manual.isVisibleTo(dialog)
    dialog.key.setText(TOKEN)
    dialog._save_key()  # kaydedince hemen yeniden denetler
    assert window.secrets.get(GITHUB_UPDATE_KEY) == TOKEN
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    assert "Yeni sürüm var: 99.0.0" in dialog.status.text.text()
    assert not dialog.key_box.isVisibleTo(dialog)  # erişim sağlandı: adımlar tekrar gizlenir
    assert server.requests[-1].headers["Authorization"] == f"Bearer {TOKEN}"


def test_update_dialog_rate_limit_is_not_a_key_problem(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    dialog = _update_dialog(window, tmp_path, FakeGitHub(rate_limited=True))
    dialog.check_now()
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    assert "istek sınırı doldu" in dialog.status.text.text()
    assert not dialog.key_box.isVisibleTo(dialog)


def test_update_dialog_auto_check_setting_persists(window: MainWindow, tmp_path: Path) -> None:
    assert auto_check_enabled(window.settings)  # varsayılan: açık
    dialog = _update_dialog(window, tmp_path, FakeGitHub())
    assert dialog.auto.isChecked()
    dialog.auto.setChecked(False)
    assert not auto_check_enabled(window.settings)
    assert not _update_dialog(window, tmp_path, FakeGitHub()).auto.isChecked()  # yeniden açılınca hatırlanır
    dialog.auto.setChecked(True)
    assert auto_check_enabled(window.settings)


def test_update_restart_prompt_in_main_window(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "uygulama"
    (root / "nxceviri").mkdir(parents=True)
    dialog = _update_dialog(window, root, FakeGitHub(version="99.0.0"))
    dialog.check_now()
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    with qtbot.waitSignal(dialog.accepted, timeout=10_000):
        dialog.install.click()

    # Ana pencere: indirme bitince yeniden başlatmayı sorar; evet denince başlatıcıyı çağırıp kapanır.
    class Accepting:
        DialogCode = UpdateDialog.DialogCode

        def __init__(self, *_a: Any, **_k: Any) -> None:
            self.info = dialog.info
            self.prepared = None

        def exec(self) -> UpdateDialog.DialogCode:
            return UpdateDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "UpdateDialog", Accepting)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    restarted: list[Path] = []
    window.app_root = root
    window.relauncher = restarted.append
    window.open_updates()
    assert restarted == [root]
    assert not window.isVisible()


def test_background_check_is_anonymous_and_shows_badge(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    server = FakeGitHub(version="99.0.0")
    window.app_root = tmp_path
    window.updater_factory = server.updater
    window.check_updates_in_background()  # anahtar kayıtlı değil: yine de denetler
    task = window._update_task
    assert task is not None
    qtbot.waitUntil(lambda: window.update_badge.isVisibleTo(window), timeout=10_000)
    assert window.update_badge.text() == "Yeni sürüm: 99.0.0 — Güncelle"
    task.wait()
    assert all("Authorization" not in r.headers for r in server.requests)


def test_background_check_respects_setting_and_stays_quiet_on_failure(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    window.app_root = tmp_path
    window.updater_factory = FakeGitHub(version="99.0.0").updater
    window.settings.setValue(AUTO_CHECK_KEY, "false")
    window.check_updates_in_background()
    assert window._update_task is None  # ayar kapalı: hiç denetlenmez
    window.settings.setValue(AUTO_CHECK_KEY, "true")
    window.updater_factory = FakeGitHub(private=True).updater  # anahtar yok: erişilemez
    window.check_updates_in_background()
    task = getattr(window, "_update_task")  # noqa: B009 - mypy önceki "None" denetimini kalıcı sanıyor
    assert task is not None
    task.wait()
    qtbot.wait(50)
    assert not window.update_badge.isVisibleTo(window)  # açılışta kullanıcı rahatsız edilmez
    assert not any(isinstance(w, QMessageBox) and w.isVisible() for w in QApplication.topLevelWidgets())


def test_packaged_build_downloads_verifies_and_hands_over_to_installer(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install = tmp_path / "Programlar" / "NXTR"
    install.mkdir(parents=True)
    (install / PACKAGE_EXE).write_bytes(b"MZ-eski")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"NXTR/{PACKAGE_EXE}", b"MZ-yeni")
    server = FakeGitHub(version="99.0.0", package=buf.getvalue())
    window.app_root = None
    window.packaged = True
    window.install_dir = install
    window.updater_factory = server.updater
    handed: list[tuple[PreparedInstall, Path]] = []
    window.installer_launcher = lambda prepared, folder: handed.append((prepared, folder))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    window.check_updates_in_background()
    task = window._update_task
    assert task is not None
    qtbot.waitUntil(lambda: window.update_badge.isVisibleTo(window), timeout=10_000)
    task.wait()
    assert window.update_badge.text() == "Yeni sürüm: 99.0.0 — Güncelle"

    def drive(dialog: UpdateDialog) -> None:
        assert dialog.windowTitle() == "Güncellemeler"
        dialog.check_now()
        qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
        assert dialog.install.text() == "İndir ve Yeniden Başlat"
        dialog.install.click()
        qtbot.waitUntil(lambda: dialog.prepared is not None, timeout=20_000)

    class Driven(UpdateDialog):
        def exec(self) -> int:
            drive(self)
            return int(UpdateDialog.DialogCode.Accepted)

    monkeypatch.setattr(main_window_module, "UpdateDialog", Driven)
    window.update_badge.click()
    assert len(handed) == 1
    assert handed[0][1] == install
    assert (handed[0][0].new_dir / PACKAGE_EXE).read_bytes() == b"MZ-yeni"
    assert (install / PACKAGE_EXE).read_bytes() == b"MZ-eski"  # kurulumu yardımcı yapar, uygulama değil
    assert not window.update_badge.isVisibleTo(window)
    assert not window.isVisible()  # yardımcı kapanmayı beklediği için uygulama kapanır


def test_packaged_build_declined_install_cleans_up(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install = tmp_path / "Programlar" / "NXTR"
    install.mkdir(parents=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"NXTR/{PACKAGE_EXE}", b"MZ-yeni")
    window.app_root = None
    window.packaged = True
    window.install_dir = install
    window.updater_factory = FakeGitHub(version="99.0.0", package=buf.getvalue()).updater
    handed: list[object] = []
    window.installer_launcher = lambda prepared, folder: handed.append(prepared)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)

    class Driven(UpdateDialog):
        def exec(self) -> int:
            self.check_now()
            qtbot.waitUntil(lambda: self._task is None, timeout=10_000)
            self.install.click()
            qtbot.waitUntil(lambda: self.prepared is not None, timeout=20_000)
            return int(UpdateDialog.DialogCode.Accepted)

    monkeypatch.setattr(main_window_module, "UpdateDialog", Driven)
    window.open_updates()
    assert handed == []
    assert not (install.parent / WORK_DIR_NAME).exists()  # indirilen paket silindi
    assert window.isVisible()


def test_packaged_unwritable_folder_offers_manual_download(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(*_a: Any, **_k: Any) -> Any:
        raise PermissionError("erişim reddedildi")

    monkeypatch.setattr(tempfile, "TemporaryFile", denied)
    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    dialog = _update_dialog(window, tmp_path, FakeGitHub(version="99.0.0"), packaged=True)
    dialog.check_now()
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    dialog.install.click()
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    assert "yazma izniniz yok" in dialog.status.text.text()
    assert RELEASES_URL in dialog.status.text.text()
    assert dialog.manual.isVisibleTo(dialog)
    dialog.manual.click()
    assert opened == [RELEASES_URL]
    assert dialog.prepared is None


def test_update_dialog_in_git_mode_suggests_git_pull(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    dialog = _update_dialog(window, tmp_path, FakeGitHub(version="99.0.0"), git_mode=True)
    dialog.check_now()
    qtbot.waitUntil(lambda: dialog._task is None, timeout=10_000)
    assert not dialog.key_box.isVisibleTo(dialog)
    assert "git pull" in dialog.status.text.text()
    assert not dialog.install.isVisibleTo(dialog)  # git deposunda kendiliğinden güncelleme yok
    assert dialog.notes.isVisibleTo(dialog)


def test_changes_dialog_after_retranslate_and_revert(qtbot: QtBot, window: MainWindow) -> None:
    server = FakeOllama(translate=lambda t: {"Not me.": "Ben içmem."}.get(t, "tr-" + t))
    window.provider_factory = lambda s: server.provider(s.model)
    window.ask_machine_settings = lambda *a, **k: MachineSettings(  # type: ignore[method-assign]
        "ollama", "", "gemma4:12b", "", SCOPE_SELECTED, "retranslate"
    )
    window.nav.setCurrentRow(STEP_TRANSLATE)
    _select(window, {"s03"})
    window.start_machine_translation("retranslate", from_selection=True)
    _wait_idle(qtbot, window)
    page = window.translate_page
    assert page.changes_button.isEnabled()
    assert page.changes_button.text() == "Son İşin Değişiklikleri (1)…"
    assert "1 satırın önceki çevirisi değişti" in page.banner.text.text()
    dialog = window.changes_dialog
    assert dialog is not None
    assert dialog.isVisible()  # yeniden çeviriden sonra kendiliğinden açılır
    assert dialog.table.rowCount() == 1
    old_cell, new_cell = dialog.table.item(0, 3), dialog.table.item(0, 4)
    assert old_cell is not None
    assert new_cell is not None
    assert "<s>değil</s>" in old_cell.text()  # yalnızca değişen sözcük vurgulanır
    assert old_cell.text().startswith("Ben ")
    assert "içmem" in new_cell.text()
    assert not dialog.revert_button.isEnabled()  # işaret yokken geri alınamaz
    dialog._check_all(Qt.CheckState.Checked)
    assert dialog.revert_button.text() == "İşaretlileri Geri Al (1)"
    dialog.revert_button.click()
    assert _rows(window)["s03"].translation == "Ben değil."
    assert _rows(window)["s03"].status == Status.MACHINE
    assert not page.changes_button.isEnabled()  # geri alınınca değişiklik kalmadı
    assert "1 satır önceki çevirisine" in page.banner.text.text()

    # Satır geçmişi: değişiklik seçilip ondan önceki hâle dönülür (geri almayı geri almak).
    window.show_row_history(_rows(window)["s03"].id)
    history = window.changes_dialog
    assert history is not None
    assert history.table.rowCount() == 3  # ilk çeviri, yeniden çeviri, geri alma
    job_cell = history.table.item(0, 1)
    assert job_cell is not None
    assert job_cell.text() == "Geri alma"
    history.table.selectRow(0)
    history.revert_button.click()
    assert _rows(window)["s03"].translation == "Ben içmem."


def test_instruction_presets_fill_the_box(window: MainWindow) -> None:
    from nxceviri.gui.machine_dialogs import INSTRUCTION_PRESETS

    dialog = _dialog(window, window._machine_scopes(), action="revise")
    assert dialog.presets.isVisibleTo(dialog)
    dialog.presets.activated.emit(1)
    assert dialog.instruction.toPlainText() == INSTRUCTION_PRESETS[0][1]
    assert dialog.presets.currentIndex() == 0
    dialog.action_buttons["retranslate"].setChecked(True)  # çeviri talimatlarının hazır listesi
    assert dialog.presets.itemText(1) == "Arayüz ve menü metinleri"
    assert dialog.instruction.toPlainText() == ""


def test_table_shows_marks_previous_column_and_live_updates(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    from nxceviri.gui.translate_page import CHANGED_FILTER, COL_PREVIOUS, COL_STATUS

    server = FakeOllama()
    window.provider_factory = lambda s: server.provider(s.model)
    window.ask_machine_settings = lambda *a, **k: MachineSettings(  # type: ignore[method-assign]
        "ollama", "", "gemma4:12b", "", SCOPE_SELECTED, "revise", "Doğal yaz."
    )
    window.nav.setCurrentRow(STEP_TRANSLATE)
    page = window.translate_page
    assert page.follow_box.isChecked()
    flashed: list[list[int]] = []
    real_show_live = page.show_live

    def recording_show_live(ids: list[int]) -> None:
        flashed.append(list(ids))
        real_show_live(ids)

    page.show_live = recording_show_live  # type: ignore[method-assign]
    _select(window, {"s01", "s02"})
    window.start_machine_translation("revise", from_selection=True)
    _wait_idle(qtbot, window)
    assert flashed  # satırlar parti parti yazıldıkça vurgulandı
    if window.changes_dialog is not None:
        window.changes_dialog.close()
    model = page.model
    row = model.position(_rows(window)["s01"].id)
    assert row is not None
    assert model.data(model.index(row, COL_STATUS)) == "● Makine · redaksiyon"
    assert "<s>" in model.data(model.index(row, COL_PREVIOUS))
    assert "Benimle bir içki iç." in model.data(model.index(row, COL_PREVIOUS), Qt.ItemDataRole.ToolTipRole)

    # "Önceki çeviri" sütunu açılıp kapanır; süzgeç yalnızca son işte değişenleri gösterir.
    assert page.table.isColumnHidden(COL_PREVIOUS)
    assert page.previous_box.isEnabled()
    page.previous_box.setChecked(True)
    assert not page.table.isColumnHidden(COL_PREVIOUS)
    page.status_filter.setCurrentIndex(page.status_filter.findData(CHANGED_FILTER))
    assert page.proxy.rowCount() == 2
    page.previous_box.setChecked(False)
    assert page.table.isColumnHidden(COL_PREVIOUS)

    # Elle düzenlenen satırın işareti kalkar.
    page.model.setData(page.model.index(row, 1), "Benimle bir şey iç.")
    assert model.data(model.index(row, COL_STATUS)) == "● Onaylandı"

    # Değişiklikler penceresinden dışa aktarma.
    window.show_job_changes()
    dialog = window.changes_dialog
    assert dialog is not None
    dialog.export_to(tmp_path / "rapor.html")
    assert "<ins>" in (tmp_path / "rapor.html").read_text(encoding="utf-8")
    assert "kaydedildi" in dialog.status.text.text()
    dialog.close()


def test_advanced_section_is_collapsed_and_summarised(window: MainWindow) -> None:
    dialog = MachineDialog(
        window,
        provider="ollama",
        base_url="",
        model="gemma4:12b",
        notes="Aile dramı.",
        source_language="en",
        secrets=window.secrets,
        scopes=window._machine_scopes(),
        translate_instruction="Kısa yaz.",
    )
    assert not dialog.advanced_toggle.isChecked()
    assert not dialog.advanced_box.isVisibleTo(dialog)
    assert not dialog.notes.isVisibleTo(dialog)
    assert dialog.advanced_toggle.text() == "Gelişmiş · notlar var, talimat var"
    dialog.notes.setPlainText("")
    assert dialog.advanced_toggle.text() == "Gelişmiş · talimat var"
    dialog.advanced_toggle.setChecked(True)  # açıkken işaret gerekmez
    assert dialog.advanced_toggle.text() == "Gelişmiş"
    assert dialog.notes.isVisibleTo(dialog)
    assert dialog.settings().instruction == "Kısa yaz."  # kapalıyken de uygulanır


def test_revise_shows_instruction_up_front(window: MainWindow) -> None:
    dialog = _dialog(window, window._machine_scopes(), action="revise")
    assert not dialog.advanced_box.isVisibleTo(dialog)
    assert dialog.instruction.isVisibleTo(dialog)  # zorunlu olduğu için ana bölümde
    assert dialog.presets.isVisibleTo(dialog)
    dialog.action_buttons["translate"].setChecked(True)
    assert not dialog.instruction.isVisibleTo(dialog)  # çevirinin talimatı Gelişmiş altına iner


def test_key_and_test_button_only_where_needed(window: MainWindow) -> None:
    scopes = window._machine_scopes()
    ollama = _dialog(window, scopes)
    assert ollama.ollama_box.isVisibleTo(ollama)
    assert not ollama.deepl_box.isVisibleTo(ollama)
    ollama.advanced_toggle.setChecked(True)
    assert ollama.test_button.isVisibleTo(ollama)
    assert ollama.url.isVisibleTo(ollama)
    deepl = _dialog(window, scopes, provider=PROVIDER_DEEPL)  # anahtar kayıtlı değil: sınanacak bir şey yok
    deepl.advanced_toggle.setChecked(True)
    assert deepl.deepl_box.isVisibleTo(deepl)
    assert not deepl.test_button.isVisibleTo(deepl)
    assert not deepl.url.isVisibleTo(deepl)
    window.secrets.set(DEEPL_API_KEY, "anahtar:fx")
    keyed = _dialog(window, scopes, provider=PROVIDER_DEEPL)
    keyed.advanced_toggle.setChecked(True)
    assert keyed.test_button.isVisibleTo(keyed)


def test_machine_dialog_rejects_invalid_ollama_address(window: MainWindow) -> None:
    dialog = _dialog(window, window._machine_scopes())
    dialog.url.setText("http://localhost:abc")
    assert dialog.test_connection() is False
    assert "adres" in dialog.status.text.text().lower()
    dialog.refresh_models()
    assert "adres" in dialog.status.text.text().lower()  # ağa gitmeden uyarır, istisna fırlatmaz
    dialog.close()
