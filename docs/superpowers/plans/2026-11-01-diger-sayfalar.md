# Diğer Sayfalar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Oyunu Ekle, Metinleri Tara, Kontrol Et ve Dışa Aktar sayfalarında ana eylemleri başlıktaki araç çubuğuna taşımak, uzun uyarı şeritlerini tıklanınca ayrıntı açan kısa durum çipine çevirmek (alt proje 3).

**Architecture:** `widgets.py` üç yeni ortak parça kazanır: `StatusChip` (kısa durum + açılır ayrıntı), `ActionBar` (solda kısa durum metni, sağda eylemler) ve `PageHeader` (simge + başlık + çip + eylemler). Sayfalar mevcut düğmelerini (aynı nesne adlarıyla) bu parçalara yerleştirir; iş mantığı ve `main_window.py` bağlantıları değişmez, yalnızca banner'a yazan iki yer çipe yazar.

**Tech Stack:** Python 3.12, PySide6 6.12, pytest + pytest-qt, ruff, mypy. Yeni bağımlılık ve yeni simge yok.

**Spec:** `docs/superpowers/specs/2026-11-01-diger-sayfalar-design.md`

## Global Constraints

- Yeni bağımlılık ve yeni simge yok; mevcut simgeler: `circle-alert`, `triangle-alert`, `circle-check`, `scan-search`, `refresh-cw`, `languages`, `shield-check`, `sparkles`, `package`, `folder-open`, `key-round`, `circle-plus`.
- Arayüz Türkçe ve kısa; çip metni en çok ~30 karakter; uzun açıklama yalnızca ipucunda ya da çip ayrıntısında. Renkler tema belirteçlerinden (`theme.py`), sabit renk yok. Açık/koyu tema ve en küçük pencere çalışır.
- **Nesne adları korunur:** `next_button`, `keys_button`, `title_keys_button`, `title_keys_clear`, `drop`, `keys_banner`, `files_banner`, `import_button`, `language`, `language_label`, `check_button`, `fix_button`, `program_fix_button`, `font_button`, `fit_enabled`, `fit_learn`, `summary` (QA ve Dışa Aktar), `fix_banner`, `export_button`, `result`, `open_button`, `stack`, `empty`, `error`, `report_scroll`. Testler bunlara erişir.
- İş mantığı değişmez; `main_window.py`'de yalnızca `version_banner.show_message(...)` çağrısı çipe döner.
- `test_button_icons.py`'deki (dosya, metin, simge) üçlüleri geçerli kalır (düğme metinleri değişmez; "Metinleri Çeviri Tablosuna Aktar  →" dahil).
- Sürüm **0.37.0**; `CHANGELOG.md`'de 0.36.0 başlığının **üstüne**; ARCHITECTURE yeni bölüm **§4.24**; TECH_DEBT gerekirse **74**'ten.
- `ruff check .`, `ruff format --check .`, `mypy nxceviri` temiz; ölü kod, sessiz `except`, açıklamasız TODO yok.
- **Git temizliği:** Çalışma ağacında başka işlere ait kaydedilmemiş değişiklikler var: `TECH_DEBT.md`, `nxceviri/core/export/layeredfs.py`, `nxceviri/core/fontpatch/dmc1_graphics.py`, `nxceviri/core/fontpatch/dmc1_images_data.py`, `nxceviri/core/qa/fonts.py`, `nxceviri/gui/jobs.py`, `nxceviri/gui/translate_page.py` (2 satır), `tests/test_dmc1_images.py`, `tests/test_export.py`, `tests/test_fontpatch_switchfont.py`, `tests/test_gui.py` (14 satırlık `version_banner` bloğu, satır ~396–409). Bunları commit etme; kendi dosyalarını tek tek `git add <yol>` ile ekle. `ruff format`'ı yalnızca kendi dosyalarına uygula. `tests/test_gui.py` değişikliği (Task 5) **yalnızca indekse** (`git apply --cached` ile kendi hunk'ın) yazılır.

## Review Focus

1. Tarama sayfasında durum değişimi (boş → yükleniyor → hata → rapor → yeniden tara): başlıkta her an yalnızca o duruma ait eylemler görünür; "Kaynak dil" yalnızca birden çok dil varken, "Aktar" yalnızca desteklenen dosya varken görünür. (Task 3)
2. Uzun çip ayrıntısı (20+ satır, 400+ karakterlik tek satır): açılır pencere ekrana sığar, kaydırılır, uygulamayı dondurmaz; ayrıntısız çip tıklanınca hiçbir şey açılmaz. (Task 1)
3. En küçük pencerede (test_layout'taki asgari boyut) başlık eylemleri görünür kalır, başlık metni kısalır. (Task 1, 5)
4. Dışa Aktar'da sorun/uyarı yokken çip gizlidir; sorun varken (`danger`) uyarıdan (`warning`) önce gelir ve rengi danger'dır. (Task 5)
5. Kontrol Et'te "Otomatik Düzelt" sürerken eylem satırındaki düğmelerin etkin/pasif durumları ve İptal paneli eskisi gibi çalışır. (Task 4)

---

### Task 1: Ortak parçalar — `StatusChip`, `ActionBar`, `PageHeader`

**Files:**
- Modify: `nxceviri/gui/widgets.py`, `nxceviri/gui/theme.py`
- Test: `tests/test_page_header.py` (yeni)

**Interfaces:**
- Produces:
  - `StatusChip(QToolButton)`: `show_status(state: str, text: str, details: Sequence[str] = ()) -> None`; `state` ∈ `""|info|success|warning|danger`; `text == ""` ya da `state == ""` → gizli. `details() -> tuple[str, ...]`; `popup: QFrame | None` (ilk tıklamada kurulur); `property("state")` = state. Ayrıntı yoksa `isEnabled()` False değil ama tıklama pencere açmaz; imleç ok olur.
  - `ActionBar(QWidget)`: `status: QLabel` (role `muted`, solda, esner, `ElideRight` değil — kelime kaydırmasız tek satır, uzunsa ipucunda tam metin), `add_action(widget: QWidget) -> None` (sağa, ekleme sırasıyla).
  - `PageHeader(QWidget)`: `__init__(title: str, icon: str, info: str = "")`; `title: QLabel` (role `pageTitle`, `info` ipucu, `QSizePolicy.Ignored` yatay — sığmazsa kısalır), `chip: StatusChip`, `add_action(widget: QWidget) -> None`.
  - `Card(title="")` → başlık satırı (başlık + `header_right`) gizlenir.
  - `EmptyState` değişmez.

- [ ] **Step 1: Write the failing tests** (`tests/test_page_header.py`, `pytestmark = pytest.mark.gui`)

```python
def test_chip_hidden_without_text(qtbot): chip = StatusChip(); qtbot.addWidget(chip); chip.show_status("warning", "", ["x"]); assert chip.isHidden()
def test_chip_shows_state_and_text(qtbot): chip.show_status("danger", "2 sorun", ["a", "b"]); assert not chip.isHidden(); assert chip.text() == "2 sorun"; assert chip.property("state") == "danger"; assert "a" in chip.toolTip() and "b" in chip.toolTip()
def test_chip_click_opens_details_popup(qtbot): show_status("warning", "1 uyarı", ["Ayrıntı satırı"]); chip.show(); qtbot.mouseClick(chip, LeftButton); assert chip.popup is not None and chip.popup.isVisible(); assert "Ayrıntı satırı" in " ".join(l.text() for l in chip.popup.findChildren(QLabel))
def test_chip_popup_closes_on_escape(qtbot): ...açtıktan sonra qtbot.keyClick(chip.popup, Key_Escape); assert not chip.popup.isVisible()
def test_chip_without_details_does_not_open(qtbot): show_status("info", "Hazır", []); click; assert chip.popup is None or not chip.popup.isVisible()
def test_chip_long_details_fit_on_screen(qtbot): details = ["x" * 420] + [f"satır {i}" for i in range(30)]; click; geo = chip.popup.geometry(); assert geo.width() <= 440 and geo.height() <= 340
def test_header_actions_in_order_right_side(qtbot): h = PageHeader("Başlık", "package"); a, b = button("A"), button("B", "primary"); h.add_action(a); h.add_action(b); h.resize(800, 60); h.show(); assert a.geometry().x() < b.geometry().x(); assert b.geometry().right() > h.title.geometry().right()
def test_header_long_title_keeps_actions_visible(qtbot): h = PageHeader("Çok uzun başlık " * 10, "package"); b = button("Modu Oluştur", "primary"); h.add_action(b); h.resize(420, 60); h.show(); qtbot.waitExposed(h); assert b.isVisible() and b.geometry().right() <= h.width()
def test_header_info_is_title_tooltip(qtbot): h = PageHeader("Başlık", "package", info="uzun bilgi"); assert "uzun bilgi" in h.title.toolTip()
def test_action_bar_status_and_actions(qtbot): bar = ActionBar(); x = button("X"); bar.add_action(x); bar.status.setText("Henüz denetlenmedi."); assert x.parent() is bar
def test_card_without_title_hides_header(qtbot): card = Card(""); assert card.title.isHidden()
```

(Kısaltılmış yazım; her test tam bir pytest işlevi olarak yazılır, `qtbot.addWidget` ile.)

- [ ] **Step 2:** `pytest tests/test_page_header.py -q` → FAIL (ImportError: StatusChip).
- [ ] **Step 3: Implement** in `widgets.py`:
  - `StatusChip`: `setProperty("role", "statusChip")`, `setToolButtonStyle(TextBesideIcon)`, `setAutoRaise(True)`, simge `bind_icon` ile (danger→`circle-alert`, warning→`triangle-alert`, success→`circle-check`, info/diğer→simgesiz). Tıklamada `_open_popup()`: `QFrame(self, Qt.WindowType.Popup)`, `objectName("chipPopup")`, içinde `QScrollArea` (en çok 320 px yükseklik) ve her ayrıntı için `label(text, wrap=True)` + `TextSelectableByMouse`; genişlik 420 px; konum `mapToGlobal(rect().bottomLeft())`, ekranın `availableGeometry()` içine kırpılır. Esc `Popup` olduğu için kendiliğinden kapatır; değilse `keyPressEvent`'te kapat.
  - `ActionBar` ve `PageHeader`: `QHBoxLayout`, kenar boşluğu 0, aralık 8. `PageHeader` başlık satırı `title_row` ile aynı simge/başlık yapısını kullanır (simge `titleIcon`, `TITLE_ICON_SIZE`).
  - `Card("")`: başlık etiketi ve `header_right` düzeni gizlenir (`head` satırını içeren bir `QWidget`'a sarıp `setVisible(bool(title))`).
  - `theme.py`: `QToolButton[role="statusChip"]` için `state` başına arka plan/ön plan (mevcut `badge` renkleri), `border-radius: 9px; padding: 3px 10px; font-weight: 600;`; `QFrame#chipPopup` yüzey + kenarlık + 8 px yarıçap.
- [ ] **Step 4:** `pytest tests/test_page_header.py tests/test_widgets_info.py -q` → PASS.
- [ ] **Step 5: Commit** `git add nxceviri/gui/widgets.py nxceviri/gui/theme.py tests/test_page_header.py` → "Ortak parçalar: durum çipi, eylem satırı, sayfa başlığı".

### Task 2: Oyunu Ekle

**Files:** Modify `nxceviri/gui/add_game_page.py`; Test `tests/test_page_header.py` (sayfa testleri eklenir)

**Interfaces:** Consumes `PageHeader`, `StatusChip`. Produces `AddGamePage.header: PageHeader`.

- [ ] **Step 1: Failing tests**

```python
def test_add_page_next_in_header(qtbot):
    page = AddGamePage()
    assert page.next_button.parent() is page.header or page.header.isAncestorOf(page.next_button)


def test_add_page_reason_in_chip_and_tooltip(qtbot):
    page.set_can_continue(False, "Önce anahtar seçin")
    assert page.header.chip.text() == "Önce anahtar seçin"
    assert "Önce anahtar seçin" in page.next_button.toolTip()
    page.set_can_continue(True, "")
    assert page.header.chip.isHidden()
    assert page.next_button.isEnabled()


def test_add_page_busy_text_in_chip(qtbot):
    page.set_busy(True, "Dosya okunuyor…")
    assert page.header.chip.text() == "Dosya okunuyor…"
    page.set_busy(False, "")
    assert page.header.chip.isHidden()


def test_add_page_drop_texts_short(qtbot):
    page.set_keys_state("danger", "Geçersiz", None)
    assert page.drop.text.text() == "Önce anahtar dosyası seçin"
    page.set_keys_state("success", "Geçerli", Path("prod.keys"))
    assert page.drop.text.text() == "NSP / NSZ dosyalarını bırakın"
```

- [ ] **Step 2:** Run → FAIL (`header` yok).
- [ ] **Step 3: Implement:** `title_row(...)` yerine `self.header = PageHeader("Oyunu Ekle", "circle-plus")`; `next_button` başlığa eklenir, alt satır (`bottom`) kalkar. `self.status` etiketi kaldırılır (hiçbir test ya da çağıran kullanmıyor; 2026-11-01'de doğrulandı). `set_can_continue`: `ok` → çip gizli, düğme ipucu "Metinleri taramaya geç"; değil → `chip.show_status("info", reason)` ve `next_button.setToolTip(reason)`. `set_busy(busy, text)`: `text` varsa `chip.show_status("info", text)`, yoksa çipi gizler. Anahtar kartı başlığı "Anahtarlar". Bırakma alanı metinleri spec §3.1. `keys_banner`/`files_banner` yerinde kalır.
- [ ] **Step 4:** `pytest tests/test_page_header.py tests/test_button_icons.py tests/test_widgets_info.py tests/test_gui.py -q` → PASS.
- [ ] **Step 5: Commit** "Oyunu Ekle: devam düğmesi başlıkta, neden çipte".

### Task 3: Metinleri Tara

**Files:** Modify `nxceviri/gui/scan_page.py`; Test `tests/test_page_header.py`

**Interfaces:** Produces `ScanPage.header`, `ScanPage.start_button`, `ScanPage.retry_button`, `ScanPage.back_button`, `ReportView.rescan_button`, `ReportView.can_import: bool`, `ReportView.has_language_choice: bool`, `ScanPage._sync_header() -> None`. `ReportView` artık `support`/`warnings` banner'ı taşımaz; bunun yerine `ReportView.status_changed = Signal(str, str, list)` (state, kısa metin, ayrıntılar) yayar ve `ScanPage` bunu `header.chip.show_status`'a bağlar.

- [ ] **Step 1: Failing tests**

```python
def _visible(page):
    return {
        w
        for w in (
            page.start_button,
            page.retry_button,
            page.back_button,
            page.report.rescan_button,
            page.report.language,
            page.report.import_button,
        )
        if not w.isHidden()
    }


def test_scan_header_empty_state(qtbot):
    page = ScanPage()
    page.show_empty()
    assert _visible(page) == {page.start_button}
    assert not page.empty.findChildren(QPushButton)


def test_scan_header_loading_has_no_actions(qtbot):
    page.show_loading("Taranıyor")
    assert _visible(page) == set()


def test_scan_header_error_state(qtbot):
    page.show_error("bozuk")
    assert _visible(page) == {page.retry_button, page.back_button}


def test_scan_header_report_state(qtbot):
    page.show_report(report_with_one_language_and_supported_msbt)
    assert _visible(page) == {page.report.rescan_button, page.report.import_button}


def test_scan_header_language_only_with_choice(qtbot):
    page.show_report(report_with_two_languages)
    assert page.report.language in _visible(page)


def test_scan_warnings_go_to_chip(qtbot):
    page.show_report(report_with_warnings(["a", "b"]))
    chip = page.header.chip
    assert not chip.isHidden()
    assert "a" in chip.details() and "b" in chip.details()


def test_scan_unsupported_chip_is_warning(qtbot):
    page.show_report(report_without_supported_entries)
    assert page.header.chip.property("state") == "warning"
    assert not page.report.import_button.isVisibleTo(page)
```

Rapor nesnelerini `tests/test_gui.py`/`tests/test_detection.py`'deki mevcut yardımcıları kullanarak kur (`ScanReport` + `EngineGuess` + `ScanEntry`); `grep -n "def .*report\|ScanReport(" tests/*.py` ile bul, yoksa testte küçük bir `ScanReport` oluştur.

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement:** `ScanPage` başlığı `PageHeader("Metinleri Tara", "scan-search", info=<mevcut uzun metin>)`. Başlığa sırasıyla: `back_button` ("Oyunu Ekle adımına dön"), `retry_button` ("Tekrar Dene", primary), `report.rescan_button` ("Yeniden Tara"), `report.language_label`, `report.language`, `report.import_button`, `start_button` ("Taramayı Başlat", primary). `EmptyState("Henüz tarama yapılmadı", "Büyük oyunlarda birkaç dakika sürebilir.")` düğmesiz. `ErrorState`'in `buttons_row`'u boş kalır. `show_empty/show_loading/show_error/show_report` her biri `self._mode`'u ayarlayıp `_sync_header()` çağırır; `_sync_header` görünürlüğü moda ve `report.can_import`/`report.has_language_choice`'a göre ayarlar; `show_report` dışındaki modlarda çip gizlenir. `ReportView.show_report` banner yerine tek çip durumu üretir: desteklenen yoksa `("warning", "Desteklenmeyen biçim", [<eski cümle>])`; uyarı varsa `("warning", f"{n} uyarı", [destek notu, *uyarılar])`; yalnız destek notu varsa `("success", f"{n} dosya aktarılabilir", [destek notu])`. Uyarı listesi kırpılmaz (açılır pencere kaydırılır).
- [ ] **Step 4:** `pytest tests/test_page_header.py tests/test_gui.py tests/test_button_icons.py tests/test_widgets_info.py tests/test_unity.py -q` → PASS.
- [ ] **Step 5: Commit** "Metinleri Tara: eylemler başlıkta, uyarılar çipte".

### Task 4: Kontrol Et

**Files:** Modify `nxceviri/gui/qa_page.py`; Test `tests/test_page_header.py`

**Interfaces:** Produces `QaPage.check_bar: ActionBar`, `QaPage.fit_bar: ActionBar`, `QaPage.font_bar: ActionBar`. `QaPage.summary` (QLabel) = `check_bar.status`.

- [ ] **Step 1: Failing tests**

```python
def test_qa_check_actions_in_bar(qtbot): qa = QaPage(); for b in (qa.program_fix_button, qa.fix_button, qa.check_button): assert qa.check_bar.isAncestorOf(b)
def test_qa_summary_is_bar_status(qtbot): assert qa.summary is qa.check_bar.status; assert qa.summary.text() == "Henüz denetlenmedi."
def test_qa_fit_and_font_bars(qtbot): assert qa.fit_bar.isAncestorOf(qa.fit_enabled); assert qa.fit_bar.isAncestorOf(qa.fit_learn); assert qa.font_bar.isAncestorOf(qa.font_button)
def test_qa_cards_have_no_tab_title(qtbot): assert qa.check_card.title.isHidden(); assert qa.fit_card.title.isHidden(); assert qa.font_card.title.isHidden()
def test_qa_open_hint_is_table_tooltip(qtbot): assert "Çift tıklayın" in qa.table.toolTip(); assert not [l for l in qa.findChildren(QLabel) if l.text().startswith("Çift tıklayın")]
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement:** başlık `PageHeader("Kontrol Et", "shield-check", info=<mevcut uzun metin>)` (eylemsiz). Her sekmede kartın üstüne `ActionBar`: Satır denetimi → `program_fix_button`, `fix_button`, `check_button`; `summary` = `check_bar.status`. Sığdırma → `fit_enabled`, `fit_learn` (`fit_learn_note` gövdede kalır). Font ve harfler → `font_button`. Kartlar `Card("")`; eski kart ipuçları (`hint=`) `ActionBar.status`'un ipucuna taşınır (Sığdırma ve Font sekmelerinin `status` metni boş, ipucu dolu). "Çift tıklayın…" etiketi kalkar, `table.setToolTip(...)`. `fix_banner` ve `fix_panel` yerinde.
- [ ] **Step 4:** `pytest tests/test_page_header.py tests/test_gui.py tests/test_gui_fit.py tests/test_layout.py tests/test_button_icons.py tests/test_widgets_info.py -q` → PASS.
- [ ] **Step 5: Commit** "Kontrol Et: sekme eylem satırları, tekrar eden kart başlıkları kalktı".

### Task 5: Dışa Aktar

**Files:** Modify `nxceviri/gui/export_page.py`, `nxceviri/gui/main_window.py` (yalnızca `_refresh_export` içindeki `version_banner` satırı), `tests/test_gui.py` (yalnızca indekse kendi hunk'ı; çalışma ağacında yabancı bloktaki iki `version_banner.text.text()` da çipe çevrilir ki yabancı test bozulmasın); Test `tests/test_page_header.py`

**Interfaces:** Produces `ExportPage.header: PageHeader`, `ExportPage.set_notes(problems: list[str], warnings: list[str]) -> None`. `version_banner` kaldırılır.

- [ ] **Step 1: Failing tests**

```python
def test_export_button_in_header(qtbot):
    page = ExportPage()
    assert page.header.isAncestorOf(page.export_button)


def test_export_notes_problems_first(qtbot):
    page.set_notes(["Anahtar dosyası seçilmedi."], ["Fontlar henüz taranmadı."])
    c = page.header.chip
    assert c.property("state") == "danger"
    assert c.text() == "1 sorun · 1 uyarı"
    assert c.details() == ("Anahtar dosyası seçilmedi.", "Fontlar henüz taranmadı.")


def test_export_notes_only_warnings(qtbot):
    page.set_notes([], ["a", "b"])
    assert page.header.chip.property("state") == "warning"
    assert page.header.chip.text() == "2 uyarı"


def test_export_notes_empty_hides_chip(qtbot):
    page.set_notes([], [])
    assert page.header.chip.isHidden()


def test_export_summary_one_line(qtbot):
    page.set_summary(written=21, errors=0, untranslated=10, conversion="yok", can_export=True)
    assert page.summary.text() == "21 yazılacak · 0 hatalı · 10 çevrilmemiş · Harf dönüştürme: yok"


def test_export_running_disables_header_action(qtbot):
    page.set_summary(..., can_export=True)
    page.show_running()
    assert not page.export_button.isEnabled()
    page.show_form()
    assert page.export_button.isEnabled()
```

`tests/test_gui.py`: `"Yazılacak çeviri satırı: <b>1</b>" in export.summary.text()` → `export.summary.text().startswith("1 yazılacak")`; yabancı bloktaki `export.version_banner.text.text()` → `" ".join(export.header.chip.details())` (yalnızca çalışma ağacında).

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement:** `PageHeader("Dışa Aktar", "package", info=<mevcut uzun metin>)`, `export_button` başlığa; özet kartı başlığı "Özet" kalır, `summary` düz metin (`format_int` ile) tek satır. `set_notes`: metin `"N sorun · M uyarı"` (boş olan kısım yazılmaz), state danger/warning, ayrıntı = sorunlar + uyarılar. `show_running`: `export_button.setEnabled(False)` ve önceki etkinlik durumunu sakla; `show_form`: geri yükle. `main_window._refresh_export`: `notes` listesini `problems` ve geri kalan uyarılar olarak ayırıp `page.set_notes(problems, warnings)` çağır.
- [ ] **Step 4:** `pytest tests/test_page_header.py tests/test_gui.py tests/test_export.py tests/test_button_icons.py tests/test_widgets_info.py tests/test_layout.py -q` → PASS.
- [ ] **Step 5: Commit:** `git add nxceviri/gui/export_page.py nxceviri/gui/main_window.py tests/test_page_header.py`; `tests/test_gui.py` için yalnızca kendi hunk'ını içeren yamayı `git apply --cached` ile indekse yaz; `git diff --cached --stat` ile doğrula. "Dışa Aktar: Modu Oluştur başlıkta, notlar çipte, tek satır özet".

### Task 6: Görsel denetim, belgeler, sürüm

**Files:** `pyproject.toml`, `nxceviri/__init__.py` (0.37.0), `CHANGELOG.md` (0.36.0'ın üstüne), `ARCHITECTURE.md` (§4.24), `docs/` içinde sayfa anlatımı varsa kısa güncelleme.

- [ ] **Step 1:** Ekran görüntüleri (scratchpad betiği, depo dışı): açık/koyu, 1180×780 ve en küçük pencere, dört sayfa; çip açılır penceresi açıkken bir görüntü. Taşma, üst üste binme, kesilen düğme yok. Sorun bulunursa önce onu yakalayan test yazılır.
- [ ] **Step 2:** Belgeler ve sürüm. ARCHITECTURE §4.24: ortak parçalar, "nesne adları korunur" kuralı, çip/şerit ayrımı (anlık sonuç yerinde, kalıcı durum çipte).
- [ ] **Step 3:** `ruff check .`, `ruff format --check` (kendi dosyaları), `mypy nxceviri`, `pytest -q` → hepsi temiz.
- [ ] **Step 4: Commit** "0.37.0: diğer sayfalar".
