"""Durum çubuğu: kalıcı bölmeler (satırlar, ilerleme, sorunlar, sağlayıcı, kayıt) ve güncelleme rozeti."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QFileDialog
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import DEEPL_API_KEY, MemoryStore
from nxceviri.gui import icons
from nxceviri.gui.main_window import STEP_QA, MainWindow
from nxceviri.gui.provider_probe import TTL_S

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


def _project(*, changed_source: bool = False) -> Project:
    p = Project.new()
    last = "Start!" if changed_source else "Start"

    def texts(third: str) -> list[ImportedFile]:
        return [
            ImportedFile(
                "Dialogue.tsv",
                "0100",
                "unity",
                "base",
                (
                    TextEntry("d01", 0, "Hello there", ()),
                    TextEntry("d02", 1, "Goodbye", ()),
                    TextEntry("m01", 2, third, ()),
                ),
            )
        ]

    p.import_texts(texts("Start"))
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations([(rows["d01"].id, "Merhaba"), (rows["m01"].id, "Başla")], machine=True)
    if changed_source:
        p.import_texts(texts(last))  # çevirisi olan satırın kaynağı değişti → Hatalı
    return p


def _make_window(qtbot: QtBot, tmp_path: Path, project: Project | None) -> MainWindow:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    if project is not None:
        w._replace_project(project)
    w.show()
    return w


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, _project())
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


@pytest.fixture
def empty_window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, None)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_empty_project_shows_only_save(empty_window: MainWindow) -> None:
    seg = empty_window.status_segments
    assert not seg.rows_label.isVisibleTo(empty_window)
    assert not seg.progress.isVisibleTo(empty_window)
    assert not seg.problems_button.isVisibleTo(empty_window)
    assert not seg.provider_label.isVisibleTo(empty_window)
    assert seg.save_dot.isVisibleTo(empty_window)
    assert seg.keys_button.isVisibleTo(empty_window)  # anahtar durumu her zaman görünür
    assert seg.keys_button.text() == ""  # yalnızca simge; durum ipucunda
    assert seg.keys_button.toolTip().startswith("Anahtar seçilmedi")
    assert "Dosya → Anahtarlar" in seg.keys_button.toolTip()


def test_keys_icon_color_follows_state(window: MainWindow) -> None:
    seg = window.status_segments

    def tone() -> str:
        return str(icons._bound[seg.keys_button][2])

    assert tone() == "muted"  # seçilmedi: gri
    seg.set_keys("success", "Anahtarlar doğrulandı", "ayrıntı")
    assert tone() == "success"
    seg.set_keys("danger", "Anahtar geçersiz", "ayrıntı")
    assert tone() == "danger"
    assert seg.keys_button.toolTip() == "Anahtar geçersiz\nayrıntı"


def test_counts_after_translation_commit(qtbot: QtBot, window: MainWindow) -> None:
    seg = window.status_segments
    assert seg.rows_label.isVisibleTo(window)
    assert seg.rows_label.text() == "3"
    assert seg._rows.toolTip() == "3 satır"
    assert seg.progress_label.text() == "%67"
    assert seg.progress.value() == 67
    tip = seg._progress.toolTip()
    assert "Çevrilen: 2 / 3" in tip
    assert "Onaylı: 0" in tip
    assert "Hatalı: 0" in tip
    row = next(r for r in window.translate_page.model.rows if r.key == "d02")
    assert window.translate_page.model.apply([(row.id, "Hoşça kal")])  # tablodan düzenleme yolu
    qtbot.waitUntil(lambda: seg.progress_label.text() == "%100", timeout=3000)
    assert seg.progress.value() == 100


def test_row_segment_shows_filtered_count(qtbot: QtBot, window: MainWindow) -> None:
    seg = window.status_segments
    page = window.translate_page
    page.search.setText("Goodbye")
    qtbot.waitUntil(lambda: seg.rows_label.text() == "1 / 3", timeout=3000)
    assert "3 satırdan 1 tanesi" in seg._rows.toolTip()
    page.search.setText("")
    qtbot.waitUntil(lambda: seg.rows_label.text() == "3", timeout=3000)


def test_page_no_longer_repeats_row_counts(window: MainWindow) -> None:
    page = window.translate_page
    assert not hasattr(page, "count_label")
    assert not hasattr(page, "progress_label")
    assert not hasattr(page, "progress")


def test_problems_segment_visible_only_with_errors(qtbot: QtBot, tmp_path: Path, window: MainWindow) -> None:
    seg = window.status_segments
    assert not seg.problems_button.isVisibleTo(window)
    broken = _make_window(qtbot, tmp_path, _project(changed_source=True))
    try:
        seg2 = broken.status_segments
        assert seg2.problems_button.isVisibleTo(broken)
        assert seg2.problems_button.text() == "1"
        assert "1 hatalı satır" in seg2.problems_button.toolTip()
        qtbot.mouseClick(seg2.problems_button, Qt.MouseButton.LeftButton)
        assert broken.pages.currentIndex() == STEP_QA
    finally:
        broken.dirty = False
        broken.close()
        broken.deleteLater()


def test_provider_segment(window: MainWindow) -> None:
    seg = window.status_segments
    assert not seg.provider_label.isVisibleTo(window)
    window.settings.setValue("translate/provider", "ollama")
    window.settings.setValue("ollama/model", "qwen3:14b")
    window._refresh_status()
    assert seg.provider_label.isVisibleTo(window)
    assert seg.provider_label.text() == "Ollama"
    window.settings.setValue("translate/provider", "deepl")
    window._refresh_status()
    assert seg.provider_label.text() == "DeepL"
    window.settings.setValue("translate/provider", "")
    window._refresh_status()
    assert not seg.provider_label.isVisibleTo(window)


def _fake_http(window: MainWindow, handler: Callable[[httpx.Request], httpx.Response]) -> list[str]:
    """Sağlayıcı sorgularını sahte HTTP'ye yönlendirir (gerçek ağ yok); istenen yolları kaydeder."""
    paths: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return handler(request)

    window.probe_client_factory = lambda: httpx.Client(transport=httpx.MockTransport(record))
    return paths


def _hover_provider(qtbot: QtBot, window: MainWindow) -> str:
    """İpucunu açar ve arka plan sorgusunun bitmesini bekler; ipucu metnini döndürür."""
    with qtbot.waitSignal(window.provider_probe.fetched, timeout=5000):
        window.status_segments.provider_tip_requested.emit()
    return window.status_segments._provider.toolTip()


def _expiry(seconds: int) -> str:
    moment = datetime.now(UTC) + timedelta(seconds=seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.123456789+00:00")


def test_ollama_tip_shows_loaded_model_gpu_share_and_remaining_time(qtbot: QtBot, window: MainWindow) -> None:
    window.settings.setValue("translate/provider", "ollama")
    window.settings.setValue("ollama/model", "qwen3:14b")

    def handler(_request: httpx.Request) -> httpx.Response:
        model = {"name": "qwen3:14b", "size": 1000, "size_vram": 620, "expires_at": _expiry(4 * 60 + 5)}
        return httpx.Response(200, json={"models": [model]})

    paths = _fake_http(window, handler)
    tip = _hover_provider(qtbot, window)
    assert paths == ["/api/ps"]
    assert tip.splitlines()[0] == "Ollama"
    assert "Model: qwen3:14b" in tip
    assert "Bellekte: GPU %62 · CPU %38" in tip
    assert "Kalan süre: 4 dk" in tip


def test_ollama_tip_when_model_not_loaded(qtbot: QtBot, window: MainWindow) -> None:
    window.settings.setValue("translate/provider", "ollama")
    window.settings.setValue("ollama/model", "qwen3:14b")
    _fake_http(window, lambda _r: httpx.Response(200, json={"models": [{"name": "baska:1b", "size": 5}]}))
    assert "Bellekte değil" in _hover_provider(qtbot, window)


def test_ollama_tip_when_unreachable(qtbot: QtBot, window: MainWindow) -> None:
    window.settings.setValue("translate/provider", "ollama")
    window.settings.setValue("ollama/model", "qwen3:14b")

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("reddedildi", request=request)

    _fake_http(window, refuse)
    assert _hover_provider(qtbot, window).splitlines() == ["Ollama", "Ollama'ya bağlanılamadı."]


def test_deepl_tip_shows_remaining_quota(qtbot: QtBot, window: MainWindow) -> None:
    window.secrets = MemoryStore()
    window.secrets.set(DEEPL_API_KEY, "anahtar:fx")
    window.settings.setValue("translate/provider", "deepl")
    paths = _fake_http(
        window, lambda _r: httpx.Response(200, json={"character_count": 123_456, "character_limit": 500_000})
    )
    tip = _hover_provider(qtbot, window)
    assert paths == ["/v2/usage"]
    assert tip.splitlines()[0] == "DeepL"
    assert "Kalan kota: 376.544 karakter" in tip


def test_deepl_tip_without_key_does_not_touch_network(qtbot: QtBot, window: MainWindow) -> None:
    window.secrets = MemoryStore()
    window.settings.setValue("translate/provider", "deepl")
    paths = _fake_http(window, lambda _r: httpx.Response(500))
    tip = _hover_provider(qtbot, window)
    assert paths == []
    assert "API anahtarı girilmemiş" in tip


def test_provider_tip_is_cached_for_thirty_seconds(qtbot: QtBot, window: MainWindow) -> None:
    window.settings.setValue("translate/provider", "ollama")
    window.settings.setValue("ollama/model", "m")
    paths = _fake_http(window, lambda _r: httpx.Response(200, json={"models": []}))
    now = [100.0]
    window.provider_probe._clock = lambda: now[0]
    _hover_provider(qtbot, window)
    _hover_provider(qtbot, window)  # önbellekten, ağa çıkmadan
    assert paths == ["/api/ps"]
    now[0] += TTL_S + 1
    _hover_provider(qtbot, window)
    assert paths == ["/api/ps", "/api/ps"]


def test_save_state(window: MainWindow) -> None:
    seg = window.status_segments
    assert seg._save.toolTip() == "Kaydedildi"
    assert seg.save_dot.property("state") == "success"
    window.dirty = True
    window._refresh_status()
    assert seg._save.toolTip() == "Kaydedilmedi"
    assert seg.save_dot.property("state") == "warning"
    window.dirty = False
    window._refresh_status()
    assert seg._save.toolTip() == "Kaydedildi"


def test_update_badge_behaviour_unchanged(window: MainWindow) -> None:
    assert window.update_badge.parent() is not None
    assert not window.update_badge.isVisibleTo(window)
    window.update_badge.show()
    assert window.update_badge.isVisibleTo(window)
    window.update_badge.hide()
    assert not window.update_badge.isVisibleTo(window)
    assert window.statusBar().isAncestorOf(window.update_badge)


def test_transient_message_still_shown(window: MainWindow) -> None:
    window.statusBar().showMessage("Deneme iletisi")
    assert window.statusBar().currentMessage() == "Deneme iletisi"


def test_keys_segment_opens_key_dialog(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    titles: list[str] = []

    def fake_dialog(_parent: object, title: str, *_args: object) -> tuple[str, str]:
        titles.append(title)
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_dialog)
    window.status_segments.keys_button.click()
    assert titles == ["prod.keys dosyasını seçin"]
