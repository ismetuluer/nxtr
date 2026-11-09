"""C aşaması inceleme bulgularının düzeltmeleri (K1, Ö1-Ö7): her bulgu için regresyon testi."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.checks import QaIssue
from nxceviri.core.qa.live import DEFAULT_LIVE_KINDS, LiveContext
from nxceviri.core.qa.terms import term_issues
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.report import WordUse
from nxceviri.core.spell.userdict import UserDictionary
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.gui.main_window import STEP_QA, MainWindow
from nxceviri.gui.qa_page import EDIT_HINT, QaPage
from nxceviri.gui.spell_window import SpellWindow
from nxceviri.gui.tasks import Task
from nxceviri.gui.translate_page import TranslatePage
from tests.test_marked_delegate import make_page, make_row

pytestmark = pytest.mark.gui


def fake_spell() -> SpellChecker:
    return SpellChecker(BloomFilter.build(["merhaba", "dünya", "selam"], error_rate=0.0001))


def _row(row_id: int, key: str, source: str, file: str, context: str = "", translation: str = "") -> TranslationRow:
    status = "machine" if translation else "untranslated"
    return TranslationRow(row_id, file, key, source, translation, status, "", (), None, context)


LIMIT_ROWS = [
    _row(1, "menu_a", "kısa", "Dialogue.tsv", "Dialogue/menu_a"),
    _row(2, "menu_b", "iki\nsatır", "Menu.tsv", "Menu/menu_b"),
    _row(3, "talk_1", "uzun bir konuşma satırı", "Story.tsv", "Story/talk_1"),
]


def _find(page: QaPage, scope: str) -> int:
    table = page.limits
    for r in range(table.model_row_count()):
        if table.scope_at(r) == scope:
            return r
    raise AssertionError(scope)


def _qa_page(qtbot: QtBot, config: FitConfig | None = None) -> QaPage:
    page = QaPage()
    qtbot.addWidget(page)
    config = config or FitConfig()
    page.set_fit(config, ["Dialogue.tsv", "Menu.tsv", "Story.tsv"], [], ["Dialogue", "Menu", "Story"])
    page.limits.set_data(LIMIT_ROWS, config, {})
    return page


# --- K1: sınırlar tablosu ile kart tek kaynaktan beslenir ----------------------------------------


def test_k1_tablo_duzenlemesi_kartta_yazilan_grup_kuralini_silmez(qtbot: QtBot) -> None:
    page = _qa_page(qtbot, FitConfig(default=FitRules(40, 3)))
    page.fit_scope.setCurrentIndex(page.fit_scope.findData("grup:Dialogue"))
    page.fit_inherit.setChecked(False)
    page.fit_width.setValue(50)
    assert page.fit_config().per_group["Dialogue"].width == 50
    # kartı değiştirmeden, sayfadan çıkmadan tabloda başka grup düzenlenir
    assert page.limits.edit_cell(_find(page, "group:Menu"), 4, "30 × 2")
    assert page.fit_config().per_group == {"Dialogue": FitRules(50, 3), "Menu": FitRules(30, 2)}


def test_k1_ogrenilen_grup_kurallari_tablo_duzenlemesinde_geri_alinmaz(qtbot: QtBot) -> None:
    page = _qa_page(qtbot)
    page.show_learned_groups({"Dialogue": FitRules(11, 1), "Story": FitRules(23, 1)})
    assert page.limits.edit_cell(_find(page, "group:Menu"), 4, "30 × 2")
    assert page.fit_config().per_group == {
        "Dialogue": FitRules(11, 1),
        "Story": FitRules(23, 1),
        "Menu": FitRules(30, 2),
    }
    # tablo de güncel kuralları gösterir
    assert page.limits.cell_text(_find(page, "group:Dialogue"), 4) == "11 × 1"


def test_k1_kart_degisince_tablo_elle_sutunu_guncellenir(qtbot: QtBot) -> None:
    page = _qa_page(qtbot, FitConfig(default=FitRules(40, 3)))
    page.fit_scope.setCurrentIndex(page.fit_scope.findData("grup:Story"))
    page.fit_inherit.setChecked(False)
    page.fit_width.setValue(33)
    assert page.limits.cell_text(_find(page, "group:Story"), 4).startswith("33 ×")


def test_k1_anahtar_deseni_duzenlemesi_grup_kurallarini_korur(qtbot: QtBot) -> None:
    page = _qa_page(qtbot, FitConfig(default=FitRules(40, 3), per_group={"Story": FitRules(20, 2)}))
    page.limits.add_pattern("menu_*")
    assert page.limits.edit_cell(_find(page, "key:menu_*"), 4, "12 × 1")
    config = page.fit_config()
    assert config.per_group == {"Story": FitRules(20, 2)}
    assert config.per_key == {"menu_*": FitRules(12, 1)}


# --- Ö1: yalnızca anahtar deseni kuralı olsa da sığdırma etkin -------------------------------------


def test_o1_yalniz_anahtar_deseni_kurali_sigdirmayi_acar(qtbot: QtBot) -> None:
    page = _qa_page(qtbot)
    assert not page.fit_enabled.isChecked()
    page.limits.add_pattern("menu_*")
    assert page.limits.edit_cell(_find(page, "key:menu_*"), 4, "5 × 1")
    config = page.fit_config()
    assert config.enabled
    assert config.per_key == {"menu_*": FitRules(5, 1)}
    assert config.rules_for_row(LIMIT_ROWS[0]) == FitRules(5, 1)


def test_o1_yalniz_anahtar_deseni_olan_proje_acik_gelir(qtbot: QtBot) -> None:
    page = _qa_page(qtbot, FitConfig(per_key={"menu_*": FitRules(5, 1)}))
    assert page.fit_enabled.isChecked()
    assert page.fit_config().enabled


# --- Ö2: anlık sonuç + son Kontrol Et sonucu birleşimi -------------------------------------------------


def _qa_issue(row: TranslationRow, kind: str, message: str) -> QaIssue:
    return QaIssue(row.id, row.key, kind, "warning", message)


def _kinds(page: TranslatePage, row_id: int) -> list[str]:
    row = page.model.row_by_id(row_id)
    assert row is not None
    return [i.kind for i in page.model._all_issues(row)]


def test_o2_esdes_satir_duzelince_bayat_tutarsiz_uyarisi_kalmaz(qtbot: QtBot) -> None:
    a, b = make_row(1, "Hello", "Merhaba"), make_row(2, "Hello", "Selam")
    page = make_page(qtbot, [a, b])
    page.set_qa_issues(
        [_qa_issue(a, "inconsistent", "Aynı metin…"), _qa_issue(b, "inconsistent", "Aynı metin…")], [a, b]
    )
    assert _kinds(page, 2) == ["inconsistent"]
    page.model.update_rows([make_row(1, "Hello", "Selam")])
    assert _kinds(page, 2) == []  # canlı sonuç geçerli: bayat Kontrol Et bulgusu geri gelmez


def test_o2_ayni_tur_iki_kez_sayilmaz(qtbot: QtBot) -> None:
    row = make_row(1, "Hello there my friend", "Merhaba dostum, nasılsın?")
    page = make_page(qtbot, [row])
    page.set_live_context(LiveContext(fit=FitConfig(default=FitRules(20, 3))))
    page.set_qa_issues([_qa_issue(row, "line_too_long", "Satır 25 karakter; sınır 15.")], [row])
    assert _kinds(page, 1).count("line_too_long") == 1


def test_o2_kapatilan_anlik_tur_kontrol_et_sonucundan_geri_gelmez(qtbot: QtBot) -> None:
    row = make_row(1, "Hello", "Merhaba vurp")
    page = make_page(qtbot, [row])
    page.set_live_context(LiveContext(spell=fake_spell()))
    assert _kinds(page, 1) == ["spelling"]
    page.set_qa_issues([_qa_issue(row, "spelling", "Yazım: vurp")], [row])
    page.set_live_context(LiveContext(spell=fake_spell(), kinds=DEFAULT_LIVE_KINDS - {"spelling"}))
    assert _kinds(page, 1) == []


def test_o2_canlida_olmayan_turler_kontrol_et_sonucundan_gelir(qtbot: QtBot) -> None:
    row = make_row(1, "Welcome to Silver Pines", "Merhaba")
    page = make_page(qtbot, [row])
    page.set_qa_issues([_qa_issue(row, "term", "‘Silver Pines’ burada…")], [row])
    assert _kinds(page, 1) == ["term"]
    page.model.update_rows([make_row(1, "Welcome to Silver Pines", "Başka")])
    assert _kinds(page, 1) == []  # çeviri değişti: eski terim bulgusu geçersiz


# --- ana pencere: Ö3, Ö5, Ö6 -------------------------------------------------------------------------

WORDS = ["merhaba", "oyun", "başlat", "yükle", "iyi", "ile", "hoş", "geldin", "selam", "gümüş", "çamlar", "dedi"]


def _window_project() -> Project:
    p = Project.new()
    entries = (
        TextEntry("s1", 0, "Silver Pines", ()),
        TextEntry("s2", 1, "Silver Pines", ()),
        TextEntry("w", 2, "Welcome to Silver Pines", ()),
        TextEntry("x1", 3, "Hello there", ()),
        TextEntry("x2", 4, "Hello there", ()),
        TextEntry("a", 5, "Start", ()),
        TextEntry("b", 6, "Başlatt", ()),
        TextEntry("c", 7, "Load", ()),
        TextEntry("d", 8, "Resume", ()),
    )
    p.import_texts([ImportedFile("Menu.tsv", "0100", "unity", "base", entries)])
    ids = {r.key: r.id for r in p.translation_rows()}
    p.set_translations(
        [
            (ids["s1"], "Gümüş Çamlar"),
            (ids["s2"], "Gümüş Çamlar"),
            (ids["w"], "Silver Pines'a hoş geldin!"),
            (ids["x1"], "Merhaba"),
            (ids["x2"], "Selam"),
            (ids["a"], "Oyun başlatt"),
            (ids["b"], "Başlatt oyun"),  # kaynakta da geçen sözcük: listelenmez
            (ids["c"], "Yükle başlatt Mara dedi"),  # "Mara" özel ad
            (ids["d"], "BAŞLATT"),  # tamamı büyük harf: listelenmez
        ],
        machine=True,
    )
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w.user_dictionary = UserDictionary(tmp_path / "yazim.txt")
    w.spell = SpellChecker(BloomFilter.build(WORDS, error_rate=0.0001), w.user_dictionary.words())
    w._replace_project(_window_project())
    w.show()
    yield w
    if w.task is not None:
        w.task.cancel()
        w.task.wait()
    w.dirty = False
    w.close()
    w.deleteLater()


def _ids(window: MainWindow) -> dict[str, int]:
    return {r.key: r.id for r in window.project.translation_rows()}


def _board(window: MainWindow, key: str) -> set[str]:
    row_id = _ids(window)[key]
    return {i.kind for i in window.qa_page.model.issues if i.row_id == row_id}


def test_o3_yerinde_duzenleme_terim_bulgusunu_korur_ya_da_giderir(window: MainWindow) -> None:
    window.run_checks()
    assert {"term", "end_punctuation"} <= _board(window, "w")
    ids = _ids(window)
    window.qa_page.translation_edited.emit(ids["w"], "Silver Pines'a hoş geldin")  # terim hâlâ çevrilmemiş
    assert _board(window, "w") == {"term"}
    window.qa_page.translation_edited.emit(ids["w"], "Gümüş Çamlar'a hoş geldin")
    assert _board(window, "w") == set()


def test_o3_yerinde_duzenleme_esdes_satirlarin_tutarsizligini_yeniler(window: MainWindow) -> None:
    window.run_checks()
    assert "inconsistent" in _board(window, "x1")
    assert "inconsistent" in _board(window, "x2")
    window.qa_page.translation_edited.emit(_ids(window)["x1"], "Selam")
    assert "inconsistent" not in _board(window, "x1")
    assert "inconsistent" not in _board(window, "x2")  # düzenlenmeyen eşdeş satır da yenilenir


def test_o3_yerinde_duzenleme_sayaci_gunceller(window: MainWindow) -> None:
    window.run_checks()
    window.qa_page.translation_edited.emit(_ids(window)["x1"], "Selam")
    counted = [i for i in window.qa_page.model.issues if i.severity in ("error", "warning")]
    assert window._qa_count == (window.project, len(counted))


# --- Ö5 -----------------------------------------------------------------------------------------------


def test_o5_hepsini_degistir_yalnizca_listelenen_satirlari_degistirir(window: MainWindow) -> None:
    window.menu_actions["tools.spell_check"].trigger()
    win = window._spell_window
    assert win is not None
    row = _uses(win).index("başlatt")
    count_item = win.table.item(row, 1)
    assert count_item is not None
    assert count_item.text() == "2"  # a ve c; b kaynakta, d tamamı büyük harf
    win.table.selectRow(row)
    win.replace_edit.setText("başla")
    win.replace_button.click()
    after = {r.key: r.translation for r in window.project.translation_rows()}
    assert after["a"] == "Oyun başla"
    assert after["c"] == "Yükle başla Mara dedi"
    assert after["b"] == "Başlatt oyun"
    assert after["d"] == "BAŞLATT"
    assert "2 satırda değiştirildi" in window.statusBar().currentMessage()


def _uses(win: SpellWindow) -> list[str]:
    return [it.text() for r in range(win.table.rowCount()) if (it := win.table.item(r, 0)) is not None]


# --- Ö6 -----------------------------------------------------------------------------------------------


def test_o6_yoksayilan_sozcuk_editor_ve_tabloda_cizilmez(window: MainWindow) -> None:
    page = window.translate_page
    assert "başlatt" not in page.translation_delegate._spell_extra
    window.ignore_spell_words(["başlatt"])
    assert "başlatt" in page.translation_delegate._spell_extra
    assert "başlatt" in page.pane._spell_extra


# --- Ö7: 50.000 satırda donma yok ---------------------------------------------------------------------


def _big_rows(count: int = 50_000) -> list[TranslationRow]:
    return [
        TranslationRow(
            i + 1,
            f"File{i % 40}.tsv",
            f"key{i}",
            f"Source line number {i}\nsecond line",
            f"Kaynak satır numarası {i} vurp\nikinci satır",
            "machine",
            "",
            (),
            None,
            f"Group{i % 40}/key{i}",
        )
        for i in range(count)
    ]


def test_o7_yazim_penceresi_buyuk_projede_arka_planda_taranir_ve_artimli_tazelenir(
    qtbot: QtBot, window: MainWindow
) -> None:
    window.translate_page.set_rows(_big_rows())
    start = time.perf_counter()
    window.open_spell_window()
    assert time.perf_counter() - start < 2.0  # tarama arka planda; pencere hemen açılır
    win = window._spell_window
    assert win is not None
    qtbot.waitUntil(lambda: "vurp" in _uses(win), timeout=120_000)
    row = window.translate_page.model.rows[10]
    window.translate_page.model.update_rows([replace(row, translation=row.translation + " blip")])
    start = time.perf_counter()
    window._refresh_spell_window()
    assert time.perf_counter() - start < 1.5  # yalnızca değişen satır taranır
    assert "blip" in _uses(win)


def test_o7_kontrol_et_sayfasi_sigdirma_sekmesi_gorunmeden_istatistik_hesaplamaz(
    qtbot: QtBot, window: MainWindow
) -> None:
    window.translate_page.set_rows(_big_rows())
    calls: list[int] = []
    original = window.qa_page.limits.set_data

    def counting(*args: object, **kwargs: object) -> None:
        calls.append(1)
        original(*args, **kwargs)  # type: ignore[arg-type]

    window.qa_page.limits.set_data = counting  # type: ignore[method-assign]
    window.qa_page.tabs.setCurrentIndex(0)
    start = time.perf_counter()
    window.nav.setCurrentRow(STEP_QA)
    assert time.perf_counter() - start < 2.0
    assert calls == []  # sınırlar tablosu görünmüyor: hesap yok
    window.qa_page.tabs.setCurrentIndex(window.qa_page.fit_tab_index())
    assert calls == [1]
    assert window.qa_page.limits.model_row_count() > 0
    window.qa_page.tabs.setCurrentIndex(0)
    window.nav.setCurrentRow(2)
    start = time.perf_counter()
    window.nav.setCurrentRow(STEP_QA)
    window.qa_page.tabs.setCurrentIndex(window.qa_page.fit_tab_index())
    assert time.perf_counter() - start < 1.5  # veri değişmedi: önbellekten
    assert calls == [1]


def test_o7_terim_degil_sonrasi_denetim_arka_planda_yenilenir(qtbot: QtBot, window: MainWindow) -> None:
    window.run_checks()
    assert any(i.kind == "term" for i in window.qa_page.model.issues)
    window.qa_page.not_term_requested.emit(["Silver Pines"])
    assert window.busy  # denetim arka plan işi olarak başladı, arayüz beklemedi
    qtbot.waitUntil(lambda: not window.busy, timeout=30_000)
    assert not any(i.kind == "term" for i in window.qa_page.model.issues)


# --- Küçük bulgular -------------------------------------------------------------------------------------


def test_k8_ayni_kaynakli_buyuk_grup_toplu_guncellemesi_dogrusaldir(qtbot: QtBot) -> None:
    rows = [make_row(i, "???", f"t{i}") for i in range(1, 6001)]
    page = make_page(qtbot, rows)
    start = time.perf_counter()
    page.model.update_rows([make_row(i, "???", f"u{i}") for i in range(1, 6001)])
    assert time.perf_counter() - start < 2.0


def test_k2_anahtar_deseni_icin_yalniz_genislik_yazilinca_satir_sayisi_desenden_ogrenilir(qtbot: QtBot) -> None:
    rows = [_row(1, "menu_a", "bir\nüç\nsatır", "Menu.tsv", "Menu/menu_a"), _row(2, "menu_b", "kısa", "Menu.tsv")]
    page = QaPage()
    qtbot.addWidget(page)
    page.set_fit(FitConfig(), ["Menu.tsv"], [], ["Menu"])
    page.limits.set_data(rows, FitConfig(), {})
    page.limits.add_pattern("menu_*")
    assert page.limits.edit_cell(_find(page, "key:menu_*"), 4, "40")
    assert page.fit_config().per_key == {"menu_*": FitRules(40, 3)}


def test_k3_oturumda_eklenen_desenler_baska_projeye_sizmaz(qtbot: QtBot) -> None:
    page = _qa_page(qtbot)
    page.limits.add_pattern("menu_*")
    page.limits.set_data(LIMIT_ROWS, FitConfig(), {})  # başka proje açıldı
    assert all(not page.limits.scope_at(r).startswith("key:") for r in range(page.limits.model_row_count()))


def test_k5_yerinde_duzenleme_ipucu_onaylamayi_soyler() -> None:
    assert "onayla" in EDIT_HINT


def test_k6_cok_satir_secilince_menu_cogul_olur(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    page.resize(1400, 800)
    page.show()
    rows = [_row(1, "k1", "A", "f", "", " x"), _row(2, "k2", "B", "f", "", " y")]
    page.show_issues([_qa_issue(rows[0], "spaces", "a"), _qa_issue(rows[1], "spaces", "b")], rows)
    page.table.selectRow(0)
    assert "Bu satırı düzelt" in [a.text() for a in page.context_menu().actions()]
    page.table.selectAll()
    texts = [a.text() for a in page.context_menu().actions()]
    assert "Bu satırları düzelt" in texts
    assert "Bu satırı düzelt" not in texts


def test_k7_otomatik_duzeltme_terim_denetimi_calistirmaz(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise AssertionError("terim denetimi çalıştı")

    monkeypatch.setattr("nxceviri.core.qa.terms.canonical_terms", boom)
    monkeypatch.setattr(window, "run_checks", lambda: None)  # düzeltme sonrası tam denetim terimleri yine arar
    window.apply_fixes(["end_punctuation"], [])
    after = {r.key: r.translation for r in window.project.translation_rows()}
    assert after["w"] == "Silver Pines'a hoş geldin"  # sondaki "!" düzeltildi


def test_k9_kanonik_ceviri_sonda_noktalama_icerse_de_cumle_ici_gecis_uyari_almaz() -> None:
    canon = {"Silver Pines": "Gümüş Çamlar."}
    row = make_row(1, "Go to Silver Pines now", "Gümüş Çamlar'a git")
    assert term_issues([row], canon) == []


def test_k10_degistirme_sonrasi_yeni_sozcuk_kutusu_temizlenir(qtbot: QtBot) -> None:
    win = SpellWindow()
    qtbot.addWidget(win)
    win.set_words([WordUse("vurp", 1, (1,))])
    win.table.selectRow(0)
    win.replace_edit.setText("yuva")
    with qtbot.waitSignal(win.replace_requested):
        win.replace_button.click()
    assert win.replace_edit.text() == ""


def test_o7_sozluge_sozcuk_eklenince_denetim_arka_planda_yenilenir(qtbot: QtBot, window: MainWindow) -> None:
    window.run_checks()
    assert any(i.kind == "spelling" and "başlatt" in i.words for i in window.qa_page.model.issues)
    window.add_spell_words(["başlatt"])
    assert window.busy
    qtbot.waitUntil(lambda: not window.busy, timeout=30_000)
    assert not any(i.kind == "spelling" and "başlatt" in i.words for i in window.qa_page.model.issues)


def test_o7_baska_is_surerken_denetim_yenilemesi_is_bitince_yapilir(qtbot: QtBot, window: MainWindow) -> None:
    window.run_checks()
    window.task = Task(lambda _ctx: None, "başka iş")  # başlatılmamış, yalnızca meşgul göstergesi
    window._recheck_if_done()
    assert window._recheck_pending
    window.task = None
    window._task_finished()
    assert window.busy  # bekleyen yenileme şimdi başladı
    qtbot.waitUntil(lambda: not window.busy, timeout=30_000)
    assert not window._recheck_pending
