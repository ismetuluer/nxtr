"""Otomatik Çeviri, çeviri sağlayıcısı ayarları ve Terminoloji pencereleri."""

from __future__ import annotations

import fnmatch
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nxceviri.core.errors import NxError
from nxceviri.core.project import TranslationRow, row_group
from nxceviri.core.secrets import DEEPL_API_KEY, SecretStore
from nxceviri.core.translate.glossary_io import export_glossary_xlsx, merge_terms, read_glossary_xlsx
from nxceviri.core.translate.instructions import (
    KIND_NOTES,
    KIND_REVISE,
    KIND_TRANSLATE,
    SavedInstruction,
    delete_instruction,
    load_library,
    save_instruction,
)
from nxceviri.core.translate.providers.base import GlossaryTerm, ProviderError, TranslationProvider
from nxceviri.core.translate.providers.deepl import DeepLProvider, plan_label
from nxceviri.core.translate.providers.ollama import (
    DEFAULT_URL,
    RECOMMENDED_MODELS,
    TEMPLATE_WARNING,
    OllamaProvider,
)
from nxceviri.core.translate.runner import ACTION_RETRANSLATE, ACTION_REVISE, ACTION_TRANSLATE, target_rows
from nxceviri.core.translate.termlib import add_missing, delete_list, list_names, load_list, save_list
from nxceviri.core.translate.terms import TermSuggestion
from nxceviri.gui.icons import bind_icon
from nxceviri.gui.settings_dialog import check_with_wait_cursor, valid_ollama_url
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.widgets import Banner, button, format_int, format_size, label, tip_html, title_row

SCOPE_SELECTED = "selected"
SCOPE_GROUPS = "groups"
SCOPE_FILTERED = "filtered"
SCOPE_ALL = "all"
SCOPE_PATTERN = "pattern"
PROVIDER_OLLAMA = "ollama"
PROVIDER_DEEPL = "deepl"

_ACTIONS = (
    (
        ACTION_TRANSLATE,
        "Çevir",
        "Çevrilmemiş ve hatalı satırlar çevrilir; belleği olan cümleler modele gitmeden doldurulur.",
    ),
    (
        ACTION_RETRANSLATE,
        "Yeniden çevir",
        "Kapsamdaki satırlar baştan çevrilir; bozuk gelen satırın eski çevirisi korunur.",
    ),
    (
        ACTION_REVISE,
        "Redaksiyon",
        "Mevcut çeviriler yazdığınız talimata göre düzeltilir. Yalnızca Ollama ile yapılabilir.",
    ),
)

_SCOPE_LABELS = {
    SCOPE_SELECTED: "Seçili satırlar",
    SCOPE_GROUPS: "Seçili satırların grubu",
    SCOPE_FILTERED: "Tabloda görünen satırlar",
    SCOPE_ALL: "Projedeki tüm satırlar",
    SCOPE_PATTERN: "Grup ya da anahtar deseni",
}


def rows_matching(rows: Sequence[TranslationRow], pattern: str) -> list[TranslationRow]:
    """Grubu, anahtarı ya da bağlamın son parçası desene uyan satırlar (`menu_*`, `*Chapter1*`; büyük/küçük
    harf duyarsız). Boş desen hiçbir satır seçmez."""
    pattern = pattern.strip().casefold()
    if not pattern:
        return []

    def names(r: TranslationRow) -> tuple[str, ...]:
        return (row_group(r), r.key, r.context.rsplit("/", 1)[-1])

    return [r for r in rows if any(fnmatch.fnmatchcase(n.casefold(), pattern) for n in names(r) if n)]


_START_LABELS = {
    ACTION_TRANSLATE: "Çeviriyi Başlat",
    ACTION_RETRANSLATE: "Yeniden Çevir",
    ACTION_REVISE: "Redaksiyonu Başlat",
}

#: Hazır redaksiyon talimatları: (menüdeki ad, talimat metni).
INSTRUCTION_PRESETS: tuple[tuple[str, str], ...] = (
    (
        "Doğal konuşma dili (makine çevirisi izlerini temizle)",
        "Bu çeviriler makine çevirisi gibi duruyor. Anlamı değiştirmeden, Türkçe konuşan birinin o sahnede "
        "gerçekten söyleyeceği gibi yeniden yaz.\n"
        "- Gereksiz zamirleri at: ben, sen, o, biz, onlar, bu, şu, bunu, onu yalnızca vurgu veya karşıtlık "
        "varsa kalsın (“Sen çık, ben gelmem!” gibi). İngilizcedeki it/that/they her yerde karşılık istemez.\n"
        "- Cümleye “Ve” ile başlama; gerekiyorsa “Bir de”, “Hem”, “Üstelik” kullan ya da hiç koyma.\n"
        "- Cevabın başındaki Yes/No/Well'i anlamına göre yaz: “Olsun”, “İyi de”, “Ama”, “Yok”, “Hı hı” ya da "
        "hiç.\n"
        "- Sözlük anlamıyla değil, o durumda söylenen kalıpla yaz; deyim varsa kullan (“That's the limit!” → "
        "“Bu kadarı da fazla!”).\n"
        "- Kısa cevapları bir önceki satıra göre çevir (“Have a drink.” → “Not me.” → “Ben içmem.”).\n"
        "- Aile ve arkadaşlar gündelik, samimi konuşur, birbirine “sen” der; ya, ki, işte, hadi, baksana gibi "
        "konuşma sözcükleri yerinde kullanılabilir ama abartma.\n"
        "- Aynı İngilizce kalıp her satırda aynı Türkçe kalıba dönüşmesin; doğal olanı seç.\n"
        "- Karakter ve yer adlarına, terminolojideki terimlere dokunma.\n"
        "- Kontrol kodlarını (⟦1⟧, ⟦2⟧ …) aynı sayıda ve aynı sırayla koru; satır sonu kodlarını cümlenin doğal "
        "kırıldığı yere koy.\n"
        "- Satır uzunluğunu kabaca koru; altyazı kısa ve kolay okunur kalsın.\n"
        "- Zaten doğal olan satırı olduğu gibi bırak.",
    ),
    (
        "Kısalt (kutuya / altyazıya sığsın)",
        "Çevirileri anlamı ve tonu koruyarak kısalt: gereksiz sözcükleri at, daha kısa eş anlamlıları seç. "
        "Kontrol kodlarını (⟦1⟧, ⟦2⟧ …) aynı sayıda ve sırayla koru. Zaten kısa olan satırı değiştirme.",
    ),
    (
        "Hitap tutarlılığı (sen / siz)",
        "Karakterler birbirine tutarlı hitap etsin: aile içi ve arkadaşlar arasında “sen”, yabancılara ve "
        "yaşlılara “siz”. Yalnızca hitabı düzelt, başka bir şeyi değiştirme. Kontrol kodlarını aynen koru.",
    ),
)

#: Hazır çeviri talimatları (çevir ve yeniden çevir; yalnızca Ollama): (menüdeki ad, talimat metni). Kapsam olarak
#: "Seçili satırların grubu" seçilerek bir dosya/grup (ör. menüler) kendi talimatıyla çevrilebilir.
TRANSLATE_PRESETS: tuple[tuple[str, str], ...] = (
    (
        "Arayüz ve menü metinleri",
        "Bu satırlar oyunun arayüz metni: menü, düğme, ayar ve sekme adları.\n"
        "- Kısa ve net yaz; düğmelerde Türk oyunlarındaki yerleşik karşılıkları kullan (Yeni Oyun, Devam Et, "
        "Kaydet, Yükle, Ayarlar, Çıkış, Geri, Onayla, İptal).\n"
        "- Emir kipini kullan (Kaydet, Başlat); İngilizcedeki fiil + nesne kalıbını Türkçe söz dizimine çevir "
        "(Start Game → Oyunu Başlat).\n"
        "- Orijinalde nokta yoksa sona nokta, ünlem veya üç nokta koyma.\n"
        "- Her sözcüğün ilk harfini büyük yazan İngilizce düzeni izleme; yalnızca ilk sözcük büyük harfle başlasın "
        "(özel adlar hariç).\n"
        "- Aynı kavram her satırda aynı sözcükle karşılansın.",
    ),
    (
        "Diyalog ve altyazı",
        "Bu satırlar karakterlerin konuşması veya altyazı.\n"
        "- Türkçe konuşan birinin o sahnede gerçekten söyleyeceği gibi, doğal ve akıcı yaz; birebir çevirme.\n"
        "- Gereksiz zamirleri (ben, sen, o, bu, onlar) at; cümleye “Ve” ile başlama.\n"
        "- Karakterin sesini ve hitabını (sen/siz) sahne boyunca koru.\n"
        "- Altyazı kısa ve kolay okunur kalsın; satır uzunluğunu kabaca koru.",
    ),
    (
        "Eşya, yetenek ve açıklama metinleri",
        "Bu satırlar eşya, yetenek, görev veya karakter açıklaması.\n"
        "- Ad satırlarını kısa ad olarak çevir (Iron Sword → Demir Kılıç); açıklamaları tam cümle yaz.\n"
        "- Etkileri geniş zamanla, tutarlı kalıpla yaz (Increases attack → Saldırıyı artırır).\n"
        "- Sayıları, birimleri ve oyun terimlerini aynen koru; terminolojideki terimleri kullan.\n"
        "- Aynı istatistik adı (Attack, Defense, HP) her yerde aynı karşılıkla çevrilsin.",
    ),
    (
        "Eğitim ve ipucu metinleri",
        "Bu satırlar oyuncuya yol gösteren eğitim, ipucu veya yükleme ekranı metni.\n"
        "- Oyuncuya “sen” diye, kısa ve anlaşılır cümlelerle seslen.\n"
        "- Düğme ve tuş adlarını, kontrol kodlarını (⟦1⟧ …) olduğu yerde bırak; tuşu anlatan cümleyi kodun yerine "
        "göre kur (Press ⟦1⟧ to jump → Zıplamak için ⟦1⟧ tuşuna bas).\n"
        "- Menü ve seçenek adlarını arayüzdeki çevirileriyle aynı yaz.",
    ),
    (
        "Resmî ve eski dil (fantastik, tarihî)",
        "Bu oyun fantastik veya tarihî bir dünyada geçiyor.\n"
        "- Ağırbaşlı, hafif eski bir dil kullan; günümüz argosu ve yabancı kökenli yeni sözcüklerden kaçın.\n"
        "- Soylular, büyükler ve yabancılar birbirine “siz” der; unvanları (Lord, Lady, Sir) tutarlı karşıla.\n"
        "- Abartılı veya yapay bir eski Türkçe kurma; okunaklı kalsın.",
    ),
)

_TRANSLATE_INSTRUCTION_EXAMPLE = (
    "İsteğe bağlı: bu işteki satırlar için modele ek talimat.\nÖrn. Bu satırlar menü metni: kısa yaz, sona nokta koyma."
)

_INSTRUCTION_EXAMPLE = (
    "Örnekler:\n"
    "• Makine çevirisi gibi duruyor: gereksiz zamirleri at, gündelik konuşma diliyle yaz.\n"
    "• Anne çocuğuna “sen” desin; Patricia'ya “siz” desinler.\n"
    "• Daha kısa yaz, altyazı ekrana sığsın."
)


@dataclass(frozen=True)
class MachineSettings:
    provider: str
    base_url: str
    model: str
    notes: str
    scope: str = SCOPE_ALL
    action: str = ACTION_TRANSLATE
    instruction: str = ""
    include_approved: bool = False
    #: Kapsam "Grup ya da anahtar deseni" ise desen.
    pattern: str = ""


def make_provider(settings: MachineSettings, secrets: SecretStore) -> TranslationProvider:
    """Seçilen ayarlara göre sağlayıcıyı kurar. DeepL anahtarı gizli depodan okunur."""
    if settings.provider == PROVIDER_DEEPL:
        return DeepLProvider(secrets.get(DEEPL_API_KEY) or "")
    return OllamaProvider(settings.model, settings.base_url or DEFAULT_URL)


def _recommendation_text() -> str:
    lines = [f"• {name} — {why}" for name, why in RECOMMENDED_MODELS]
    return (
        "RTX A4000 (16 GB) gibi bir ekran kartı için önerilen modeller:\n"
        + "\n".join(lines)
        + f"\nİndirmek için komut satırında: ollama pull {RECOMMENDED_MODELS[0][0]}"
    )


class LibraryButton(QPushButton):
    """ "Kitaplık" düğmesi: kayıtlı metinleri (talimat ya da oyun notu) menüde listeler; seçilen kutuya yazılır.

    Kayıtlar kullanıcıya aittir ve bütün projelerde ortaktır (`core/translate/instructions.py`). `kind`: o anki
    kayıt türünü veren işlev (iş türü değişince talimat türü de değişir); `report(durum, metin)`: sonucu bildirir.
    """

    def __init__(
        self,
        kind: Callable[[], str],
        editor: QPlainTextEdit,
        report: Callable[[str, str], None],
        save_text: str,
    ) -> None:
        super().__init__()
        self._kind = kind
        self._editor = editor
        self._report = report
        self._save_text = save_text
        self.setText("Kitaplık")
        self.setToolTip("Kaydedin; başka projelerde de seçebilirsiniz.")
        bind_icon(self, "book-open")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_widget = QMenu(self)
        self.menu_widget.aboutToShow.connect(self.fill)
        self.setMenu(self.menu_widget)

    def fill(self) -> None:
        menu = self.menu_widget
        menu.clear()
        kind = self._kind()
        saved = [i for i in load_library() if i.kind == kind]
        for item in saved:
            action = menu.addAction(item.name)
            action.setToolTip(item.text)
            action.triggered.connect(lambda _c=False, n=item.name: self.use(n))
        if not saved:
            empty = menu.addAction("Kayıtlı yok")
            empty.setEnabled(False)
        menu.addSeparator()
        menu.addAction(self._save_text).triggered.connect(self.save)
        if saved:
            remove = menu.addMenu("Sil")
            for item in saved:
                remove.addAction(item.name).triggered.connect(lambda _c=False, n=item.name: self._delete(n))

    def use(self, name: str) -> None:
        kind = self._kind()
        found = next((i for i in load_library() if i.kind == kind and i.name == name), None)
        if found is not None:
            self._editor.setPlainText(found.text)

    def save(self) -> None:
        text = self._editor.toPlainText().strip()
        if not text:
            self._report("warning", "Kaydetmek için önce metni yazın.")
            return
        name, ok = QInputDialog.getText(self, "Kitaplığa kaydet", "Adı:")
        if not ok or not name.strip():
            return
        try:
            save_instruction(SavedInstruction(name.strip(), self._kind(), text))
        except OSError as exc:
            self._report("danger", f"Kaydedilemedi: {exc}")
            return
        self._report("success", f"“{name.strip()}” kitaplığa kaydedildi.")
        self.fill()

    def _delete(self, name: str) -> None:
        try:
            delete_instruction(name, self._kind())
        except OSError as exc:
            self._report("danger", f"Silinemedi: {exc}")
            return
        self.fill()


class MachineDialog(QDialog):
    """Makine çevirisi, yeniden çeviri ve redaksiyon: sağlayıcı, model, oyun notları, iş türü ve kapsam.

    `scopes`: kapsam → o kapsamdaki satırlar (seçili, seçililerin grubu, filtrelenen, tümü). İşin
    uygulanacağı satırlar iş türüne göre bunların içinden seçilir (`target_rows`).
    """

    def __init__(
        self,
        parent: QWidget | None,
        *,
        provider: str,
        base_url: str,
        model: str,
        notes: str,
        source_language: str,
        secrets: SecretStore,
        scopes: Mapping[str, Sequence[TranslationRow]],
        action: str = ACTION_TRANSLATE,
        scope: str = SCOPE_ALL,
        instruction: str = "",
        translate_instruction: str = "",
    ) -> None:
        super().__init__(parent)
        #: İş türüne göre talimat metni: redaksiyonun ve çevirinin (çevir + yeniden çevir) ayrı talimatı var.
        self._texts = {ACTION_REVISE: instruction, ACTION_TRANSLATE: translate_instruction}
        self._shown_kind: str | None = None
        self.setWindowTitle("Otomatik Çeviri")
        self.setMinimumWidth(620)
        self._secrets = secrets
        self._scopes = scopes
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(
            title_row(
                "Otomatik Çeviri",
                "Onaylı satırlara dokunulmaz. İşlem her partide kaydedilir; yarıda kalırsa kaldığı yerden devam eder.",
                "cardTitle",
            )
        )
        form = QFormLayout()
        self.provider = QComboBox()
        self.provider.addItem("Ollama (yerel, ücretsiz)", PROVIDER_OLLAMA)
        self.provider.addItem("DeepL (bulut, kota kullanır)", PROVIDER_DEEPL)
        self.provider.setToolTip(
            tip_html("Ollama metinleri bilgisayarınızdan çıkarmaz. DeepL metinleri buluta gönderir ve kota kullanır.")
        )
        provider_row = QHBoxLayout()
        provider_row.addWidget(self.provider, 1)
        # Bağlantı testi her zaman görünür (eskiden Gelişmiş altındaydı).
        self.test_button = button("Bağlantıyı Test Et", icon="activity")
        self.test_button.clicked.connect(self.test_connection)
        provider_row.addWidget(self.test_button)
        form.addRow("Sağlayıcı:", provider_row)

        self.ollama_box = QWidget()
        of = QFormLayout(self.ollama_box)
        of.setContentsMargins(0, 0, 0, 0)
        model_row = QHBoxLayout()
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumContentsLength(22)
        if model:
            self.model.addItem(model)
        refresh = button("Modelleri Listele", icon="refresh-cw")
        refresh.clicked.connect(self.refresh_models)
        model_row.addWidget(self.model, 1)
        model_row.addWidget(refresh)
        of.addRow("Model:", model_row)
        #: Şablonu sistem talimatını yok sayan modeller (Modelleri Listele ile öğrenilir).
        self._template_ignores_system: set[str] = set()
        self.template_note = label(
            TEMPLATE_WARNING,
            "muted",
            wrap=True,
            tip="Ollama sistem mesajını yalnızca şablonunda .System veya .Messages geçen modellere iletir. "
            "Denetlemek için komut satırında: ollama show <model> --template",
        )
        self.template_note.hide()
        of.addRow(self.template_note)
        self.model.currentTextChanged.connect(self._update_template_note)
        form.addRow(self.ollama_box)

        self.deepl_box = QWidget()
        df = QFormLayout(self.deepl_box)
        df.setContentsMargins(0, 0, 0, 0)
        key = secrets.get(DEEPL_API_KEY)
        self.deepl_key_label = label(
            f"Kayıtlı ({plan_label(key)})" if key else "Anahtar yok — Dosya → Ayarlar → Çeviri sayfasından girin.",
            None if key else "muted",
        )
        df.addRow("DeepL API anahtarı:", self.deepl_key_label)
        form.addRow(self.deepl_box)
        lay.addLayout(form)

        # --- iş türü ve kapsam ---
        self.job_box = QWidget()
        jl = QVBoxLayout(self.job_box)
        jl.setContentsMargins(0, 0, 0, 0)
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        action_row.addWidget(label("İş:"))
        self.action_group = QButtonGroup(self)
        self.action_group.setExclusive(True)
        self.action_buttons: dict[str, QToolButton] = {}
        for value, text, tip in _ACTIONS:
            rb = QToolButton()
            rb.setText(text)
            rb.setCheckable(True)
            rb.setProperty("role", "chip")  # yan yana, seçili olan vurgulu (Sorunlar panosundaki çiplerle aynı)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            rb.setToolTip(tip_html(tip))
            self.action_group.addButton(rb)
            self.action_buttons[value] = rb
            action_row.addWidget(rb)
        action_row.addStretch(1)
        self.action_buttons.get(action, self.action_buttons[ACTION_TRANSLATE]).setChecked(True)
        jl.addLayout(action_row)
        # Talimat: talimatla düzeltmede zorunlu olduğu için ana bölümde, öteki işlerde "Gelişmiş" altında durur.
        self.main_instruction_host = QVBoxLayout()
        self.main_instruction_host.setContentsMargins(0, 0, 0, 0)
        jl.addLayout(self.main_instruction_host)
        scope_row = QHBoxLayout()
        scope_row.addWidget(label("Kapsam:"))
        self.scope = QComboBox()
        scope_row.addWidget(self.scope, 1)
        jl.addLayout(scope_row)
        self.pattern = QLineEdit()
        self.pattern.setPlaceholderText("Örn. menu_* ya da *Chapter1*")
        self.pattern.setToolTip(
            tip_html("Grubu ya da anahtarı desene uyan satırlar. * herhangi bir metin, ? tek harf demektir.")
        )
        self.pattern.setClearButtonEnabled(True)
        self.pattern.hide()
        jl.addWidget(self.pattern)
        self.count = label("", "muted", wrap=True)
        jl.addWidget(self.count)
        lay.addWidget(self.job_box)
        self._initial_scope = scope

        # --- gelişmiş (kapalı başlar) ---
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setAutoRaise(True)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        lay.addWidget(self.advanced_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self.advanced_box = QWidget()
        al = QVBoxLayout(self.advanced_box)
        al.setContentsMargins(0, 0, 0, 0)
        af = QFormLayout()
        self.url = QLineEdit(base_url or DEFAULT_URL)
        self.url_row = label("Ollama adresi:")
        af.addRow(self.url_row, self.url)
        af.addRow("Kaynak dil:", label(source_language or "en"))
        self.notes = QPlainTextEdit(notes)
        self.notes.setPlaceholderText(
            "Oyunu, karakterleri ve istediğiniz üslubu kısaca anlatın.\n"
            "Örn. 2001 Quito; çocuk ve ailesi gündelik, samimi konuşur."
        )
        self.notes.setToolTip(
            tip_html("Ollama: tür, ton ve hitap isteklerini Türkçe yazın. DeepL: kaynak dilde 1-2 cümle bağlam yazın.")
        )
        self.notes.setFixedHeight(64)
        self.notes_label = label(
            "Oyun hakkında:",
            tip="Bu projede kalıcıdır ve her işte modele gider: oyunun türü, dönemi, karakterleri, istenen ton.",
        )
        notes_box = QVBoxLayout()
        notes_box.setSpacing(4)
        notes_box.addWidget(self.notes)
        self.notes_library = LibraryButton(lambda: KIND_NOTES, self.notes, self._report, "Bu Notu Kaydet…")
        notes_box.addWidget(self.notes_library, alignment=Qt.AlignmentFlag.AlignRight)
        af.addRow(self.notes_label, notes_box)
        al.addLayout(af)
        self.advanced_instruction_host = QVBoxLayout()
        self.advanced_instruction_host.setContentsMargins(0, 0, 0, 0)
        al.addLayout(self.advanced_instruction_host)
        self.instruction_box = QWidget()
        il = QVBoxLayout(self.instruction_box)
        il.setContentsMargins(0, 0, 0, 0)
        self.instruction_label = label("Bu iş için talimat (isteğe bağlı)", "cardTitle")
        il.addWidget(self.instruction_label)
        preset_row = QHBoxLayout()
        self.presets = QComboBox()
        self.presets.activated.connect(self._use_preset)
        preset_row.addWidget(self.presets, 1)
        # Talimat kitaplığı: kullanıcının kaydettiği talimatlar (bütün projelerde ortak).
        self.instruction = QPlainTextEdit()
        self.library_button = LibraryButton(self._library_kind, self.instruction, self._report, "Bu Talimatı Kaydet…")
        self.library_menu = self.library_button.menu_widget
        preset_row.addWidget(self.library_button)
        il.addLayout(preset_row)
        self.instruction.setFixedHeight(120)
        il.addWidget(self.instruction)
        self.advanced_instruction_host.addWidget(self.instruction_box)
        self.include_approved = QCheckBox("Onayladığım satırlara da uygula")
        self.include_approved.setToolTip(
            tip_html("Açıksa onaylanmış satırlar da yeniden çevrilir veya düzeltilir; durumları “Makine” olur.")
        )
        al.addWidget(self.include_approved)
        lay.addWidget(self.advanced_box)
        self.advanced_box.hide()

        self.status = Banner()
        lay.addWidget(self.status)
        self.help = label(_recommendation_text(), "muted", wrap=True)
        self.help.hide()
        lay.addWidget(self.help)

        buttons = QDialogButtonBox()
        self.start = buttons.addButton("Çeviriyi Başlat", QDialogButtonBox.ButtonRole.AcceptRole)
        bind_icon(self.start, "play")
        self.start.setProperty("kind", "primary")
        bind_icon(buttons.addButton("Vazgeç", QDialogButtonBox.ButtonRole.RejectRole), "x")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.provider.setCurrentIndex(max(self.provider.findData(provider), 0))
        self.provider.currentIndexChanged.connect(self._update)
        self.action_group.buttonToggled.connect(self._update)
        self.include_approved.toggled.connect(self._update)
        self.notes.textChanged.connect(self._update_advanced_title)
        self.instruction.textChanged.connect(self._update_advanced_title)
        self.scope.currentIndexChanged.connect(self._scope_changed)
        self.pattern.textChanged.connect(self._update_count)
        # Seçilen satırların hepsi onaylıysa (ör. yanlışlıkla düzenlenip onaylanmış) iş onlara uygulanabilsin.
        initial = self._scopes.get(scope, ())
        if (
            self.action != ACTION_TRANSLATE
            and not target_rows(initial, self.action)
            and target_rows(initial, self.action, include_approved=True)
        ):
            self.include_approved.setChecked(True)
        self._update()

    @property
    def provider_name(self) -> str:
        return str(self.provider.currentData())

    @property
    def action(self) -> str:
        return next((a for a, rb in self.action_buttons.items() if rb.isChecked()), ACTION_TRANSLATE)

    def _scope(self) -> str:
        return str(self.scope.currentData() or SCOPE_ALL)

    def _scope_rows(self, scope: str) -> Sequence[TranslationRow]:
        if scope == SCOPE_PATTERN:
            return rows_matching(self._scopes.get(SCOPE_ALL, ()), self.pattern.text())
        return self._scopes.get(scope, ())

    def target(self) -> list[TranslationRow]:
        """İşin uygulanacağı satırlar (seçili kapsam, iş türü ve onay seçeneğine göre)."""
        return target_rows(self._scope_rows(self._scope()), self.action, self.include_approved.isChecked())

    def _scope_changed(self) -> None:
        pattern = self._scope() == SCOPE_PATTERN
        self.pattern.setVisible(pattern)
        if pattern:
            self.pattern.setFocus()
        self._update_count()

    def _scope_label(self, scope: str) -> str:
        text = _SCOPE_LABELS[scope]
        if scope == SCOPE_GROUPS:
            groups = sorted({row_group(r) for r in self._scopes.get(SCOPE_SELECTED, ())}, key=str.casefold)
            shown = ", ".join(groups[:3]) + (f" +{len(groups) - 3}" if len(groups) > 3 else "")
            text += f" ({shown})" if shown else ""
        return text

    def _update(self) -> None:
        deepl = self.provider_name == PROVIDER_DEEPL
        self.ollama_box.setVisible(not deepl)
        self.deepl_box.setVisible(deepl)
        self.url.setVisible(not deepl)
        self.url_row.setVisible(not deepl)
        self.test_button.setVisible(not deepl or bool(self._secrets.get(DEEPL_API_KEY)))
        self.help.hide()
        self.status.show_message("success", "")
        action = self.action
        self._show_instruction_kind(ACTION_REVISE if action == ACTION_REVISE else ACTION_TRANSLATE)
        # Talimatla düzeltmede talimat ana bölümde görünür; öteki işlerde "Gelişmiş" altındadır.
        host = self.main_instruction_host if action == ACTION_REVISE else self.advanced_instruction_host
        if host.indexOf(self.instruction_box) < 0:
            host.addWidget(self.instruction_box)
        self.instruction_box.setVisible(self._instruction_enabled())
        self.include_approved.setEnabled(action != ACTION_TRANSLATE)
        current = self.scope.currentData() or self._initial_scope
        include = self.include_approved.isChecked()
        self.scope.blockSignals(True)
        self.scope.clear()
        for scope in (SCOPE_SELECTED, SCOPE_GROUPS, SCOPE_FILTERED, SCOPE_ALL):
            rows = self._scopes.get(scope, ())
            if not rows:
                continue
            n = len(target_rows(rows, action, include))
            self.scope.addItem(f"{self._scope_label(scope)} — {format_int(n)} satır", scope)
        if self._scopes.get(SCOPE_ALL):
            self.scope.addItem(_SCOPE_LABELS[SCOPE_PATTERN], SCOPE_PATTERN)
        self.scope.setCurrentIndex(max(self.scope.findData(current), 0))
        self.scope.blockSignals(False)
        self.pattern.setVisible(self._scope() == SCOPE_PATTERN)
        self.start.setText(_START_LABELS[action])
        self._update_count()
        self._update_advanced_title()

    def _toggle_advanced(self, opened: bool) -> None:
        self.advanced_box.setVisible(opened)
        self._update_advanced_title()
        self.adjustSize()

    def _update_advanced_title(self) -> None:
        """Gelişmiş bölüm kapalıyken içindeki etkin ayarları başlıkta gösterir (kullanıcı uygulandığını bilsin)."""
        opened = self.advanced_toggle.isChecked()
        bind_icon(self.advanced_toggle, "chevron-up" if opened else "chevron-down")
        parts: list[str] = []
        if self.notes.toPlainText().strip():
            parts.append("notlar var")
        if self._instruction_enabled() and self.action != ACTION_REVISE and self.instruction.toPlainText().strip():
            parts.append("talimat var")
        if self.include_approved.isChecked() and self.action != ACTION_TRANSLATE:
            parts.append("onaylılar dahil")
        self.advanced_toggle.setText("Gelişmiş" + ("" if opened or not parts else " · " + ", ".join(parts)))

    def _update_count(self) -> None:
        rows = self.target()
        chars = sum(len(r.source) for r in rows)
        deepl = self.provider_name == PROVIDER_DEEPL
        no_key = deepl and not self._secrets.get(DEEPL_API_KEY)
        revise_on_deepl = deepl and self.action == ACTION_REVISE
        if rows:
            text = f"Bu iş {format_int(len(rows))} satıra uygulanacak (yaklaşık {format_int(chars)} karakter)."
        elif self._scope() == SCOPE_PATTERN and not self.pattern.text().strip():
            text = "Grup ya da anahtar deseni yazın."
        else:
            text = "Bu kapsamda bu işe uygun satır yok."
        self.count.setText(text)
        if revise_on_deepl:
            self.status.show_message(
                "warning", "DeepL talimat izleyemez; redaksiyon için sağlayıcı olarak Ollama'yı seçin."
            )
        self.start.setEnabled(bool(rows) and not no_key and not revise_on_deepl)

    def _instruction_enabled(self) -> bool:
        """Talimat kutusu bu işte kullanılıyor mu? (Redaksiyonda her zaman; çeviride yalnızca Ollama ile.)"""
        return self.action == ACTION_REVISE or self.provider_name == PROVIDER_OLLAMA

    def _show_instruction_kind(self, kind: str) -> None:
        """Kutuyu iş türünün talimatı ve hazır listesiyle doldurur; önceki türün metni saklanır."""
        if kind == self._shown_kind:
            return
        if self._shown_kind is not None:
            self._texts[self._shown_kind] = self.instruction.toPlainText()
        self._shown_kind = kind
        revise = kind == ACTION_REVISE
        self.instruction.setPlainText(self._texts[kind])
        self.instruction.setPlaceholderText(_INSTRUCTION_EXAMPLE if revise else _TRANSLATE_INSTRUCTION_EXAMPLE)
        self.presets.clear()
        self.presets.addItem("Hazır talimat…", "")
        for name, text in INSTRUCTION_PRESETS if revise else TRANSLATE_PRESETS:
            self.presets.addItem(name, text)

    def _use_preset(self, index: int) -> None:
        text = str(self.presets.itemData(index) or "")
        if text:
            self.instruction.setPlainText(text)
            self.status.show_message("success", "")
        self.presets.setCurrentIndex(0)

    def _library_kind(self) -> str:
        return KIND_REVISE if self.action == ACTION_REVISE else KIND_TRANSLATE

    def _report(self, state: str, text: str) -> None:
        self.status.show_message(state, text)

    def use_saved(self, name: str) -> None:
        self.library_button.use(name)

    def save_to_library(self) -> None:
        self.library_button.save()

    def _update_template_note(self) -> None:
        self.template_note.setVisible(self.model.currentText().strip() in self._template_ignores_system)

    def _ollama_url(self) -> str | None:
        """Alandaki Ollama adresi (boşsa varsayılan); geçersizse durumu bildirir ve None döndürür."""
        url = valid_ollama_url(self.url.text() or DEFAULT_URL)
        if url is None:
            self.status.show_message("danger", f"Geçerli bir Ollama adresi yazın, örneğin {DEFAULT_URL}.")
            self.help.hide()
        return url

    def refresh_models(self) -> None:
        url = self._ollama_url()
        if url is None:
            return
        provider = OllamaProvider(self.model.currentText().strip(), url, timeout_s=15)
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            models = [m for m in provider.list_models() if m.can_chat]
        except ProviderError as exc:
            self.status.show_message("danger", exc.user_text())
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
            provider.close()
        current = self.model.currentText()
        self._template_ignores_system = {m.name for m in models if m.template_drops_system}
        self.model.clear()
        for m in models:
            detail = " · ".join(x for x in (m.parameters, m.quantization, format_size(m.size_bytes)) if x)
            self.model.addItem(m.name)
            self.model.setItemData(self.model.count() - 1, detail, Qt.ItemDataRole.ToolTipRole)
        for name in [current] + [n for n, _ in RECOMMENDED_MODELS]:
            idx = self.model.findText(name)
            if idx >= 0:
                self.model.setCurrentIndex(idx)
                break
        if models:
            self.status.show_message("success", f"{len(models)} çeviri yapabilecek model bulundu.")
            self.help.hide()
        else:
            self.status.show_message("warning", "Ollama çalışıyor ama çeviri yapabilecek model yüklü değil.")
            self.help.show()

    def test_connection(self) -> bool:
        if self.provider_name == PROVIDER_OLLAMA and self._ollama_url() is None:
            return False
        try:
            provider = make_provider(self.settings(), self._secrets)
        except NxError as exc:
            self.status.show_message("danger", exc.user_text())
            return False
        status = check_with_wait_cursor(provider)
        message = status.message
        if status.ok and self.provider_name == PROVIDER_DEEPL:
            chars = sum(len(r.source) for r in self.target())
            message += f" Bu iş yaklaşık {format_int(chars)} karakter kullanacak."
        self.status.show_message("success" if status.ok else "danger", message)
        self.help.setVisible(not status.ok and self.provider_name == PROVIDER_OLLAMA)
        return status.ok

    def _accept(self) -> None:
        if self.provider_name == PROVIDER_OLLAMA and not self.model.currentText().strip():
            self.status.show_message("danger", "Bir model seçin veya adını yazın.")
            self.help.show()
            return
        if self.action == ACTION_REVISE and not self.instruction.toPlainText().strip():
            self.status.show_message("warning", "Modelin neyi düzeltmesini istediğinizi talimat kutusuna yazın.")
            self.instruction.setFocus()
            return
        if self.test_connection():
            self.accept()

    def settings(self) -> MachineSettings:
        return MachineSettings(
            provider=self.provider_name,
            base_url=self.url.text().strip() or DEFAULT_URL,
            model=self.model.currentText().strip(),
            notes=self.notes.toPlainText().strip(),
            scope=self._scope(),
            action=self.action,
            instruction=self.instruction.toPlainText().strip() if self._instruction_enabled() else "",
            include_approved=self.include_approved.isChecked() and self.action != ACTION_TRANSLATE,
            pattern=self.pattern.text().strip() if self._scope() == SCOPE_PATTERN else "",
        )


class TermLibraryButton(QPushButton):
    """Terminoloji penceresinin "Kitaplık" düğmesi: listeyi kitaplığa kaydet, kitaplıktaki listeleri ekle ya da sil.

    Kitaplık bütün projelerde ortaktır; eklerken projede olan terimin karşılığı korunur (`termlib.add_missing`).
    """

    def __init__(self, dialog: GlossaryDialog) -> None:
        super().__init__()
        self._dialog = dialog
        self.setText("Kitaplık")
        self.setToolTip("Terimleri adlandırılmış liste olarak saklayın; aynı serinin başka oyununda ekleyin.")
        bind_icon(self, "book-open")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_widget = QMenu(self)
        self.menu_widget.aboutToShow.connect(self.fill)
        self.setMenu(self.menu_widget)
        self.fill()

    def fill(self) -> None:
        menu = self.menu_widget
        menu.clear()
        names = list_names()
        add_menu = menu.addMenu("Kitaplıktan Ekle")
        delete_menu = menu.addMenu("Listeyi Sil")
        for name in names:
            add_menu.addAction(name).triggered.connect(lambda _c=False, n=name: self.add_from(n))
            delete_menu.addAction(name).triggered.connect(lambda _c=False, n=name: self.delete(n))
        for sub in (add_menu, delete_menu):
            sub.setEnabled(bool(names))
        menu.addSeparator()
        menu.addAction("Kitaplığa Kaydet…").triggered.connect(self.save_current)

    def save_current(self) -> None:
        terms = self._dialog.terms()
        if not terms:
            self._dialog.banner.show_message("warning", "Kaydedilecek terim yok.")
            return
        name, ok = QInputDialog.getText(self, "Kitaplığa kaydet", "Listenin adı (ör. oyun serisi):")
        name = name.strip()
        if not ok or not name:
            return
        if name in list_names():
            answer = QMessageBox.question(self, "Kitaplığa kaydet", f"“{name}” listesi var. Üzerine yazılsın mı?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            save_list(name, terms)
        except OSError as exc:
            self._dialog.banner.show_message("danger", f"Liste kaydedilemedi: {exc}")
            return
        self._dialog.banner.show_message("success", f"“{name}” kitaplığa kaydedildi ({format_int(len(terms))} terim).")
        self.fill()

    def add_from(self, name: str) -> None:
        merged, added, kept = add_missing(self._dialog.terms(), load_list(name))
        self._dialog.set_terms(merged)
        text = f"“{name}”: {format_int(added)} terim eklendi"
        if kept:
            text += f", {format_int(kept)} terim projede zaten olduğu için korundu"
        self._dialog.banner.show_message("success", text + ". Saklamak için Kaydet'e basın.")

    def delete(self, name: str) -> None:
        answer = QMessageBox.question(self, "Listeyi sil", f"“{name}” kitaplıktan silinsin mi? Projeler etkilenmez.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_list(name)
        except OSError as exc:
            self._dialog.banner.show_message("danger", f"Liste silinemedi: {exc}")
            return
        self.fill()


class GlossaryDialog(QDialog):
    """Terminoloji: karakter, yer, eşya adları, sabit çeviriler ve çevirisiz bilgi notları (lore)."""

    def __init__(
        self,
        parent: QWidget | None,
        terms: list[GlossaryTerm],
        start_dir: Path | None = None,
        can_suggest: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Terminoloji")
        self.resize(760, 520)
        self.start_dir = start_dir or Path.home()
        #: Kullanıcı "Terim Öner"e bastı: terminoloji kaydedilir, ardından öneri işi başlatılır.
        self.wants_suggestions = False
        lay = QVBoxLayout(self)
        lay.addWidget(
            title_row(
                "Terminoloji",
                "Oyunun adları ve sabit karşılıkları; çeviride aynen kullanılır.",
                "cardTitle",
            )
        )
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Terim", "Karşılık", "Not"])
        for col, tip in enumerate(
            (
                "Kaynak dildeki ad. Çok anlamlı tek sözcükleri (On, Safe) eklemeyin.",
                "Türkçe karşılığı; çevrilmeyecek ada aynı adı yazın. Boşsa madde bilgi notudur: ad geçince modele "
                "not gider.",
                "Modele giden açıklama (karakter, yer, ton).",
            )
        ):
            header = self.table.horizontalHeaderItem(col)
            if header is not None:
                header.setToolTip(tip)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        h = self.table.horizontalHeader()
        for col in range(3):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)
        self.set_terms(terms)
        self.banner = Banner()
        lay.addWidget(self.banner)
        row = QHBoxLayout()
        add = button("Terim Ekle", icon="circle-plus")
        add.clicked.connect(lambda: self._add("", "", "", edit=True))
        remove = button("Seçilenleri Sil", icon="x")
        remove.clicked.connect(self._remove)
        self.import_button = button("İçe Aktar…", icon="file-down")
        self.import_button.setToolTip("İki sütunlu (terim, karşılık) Excel dosyasındaki terimleri ekler.")
        self.import_button.clicked.connect(self._import)
        self.export_button = button("Dışa Aktar…", icon="file-up")
        self.export_button.setToolTip("Karşılığı olan terimleri iki sütunlu Excel dosyasına yazar.")
        self.export_button.clicked.connect(self._export)
        self.suggest_button = button("Terim Öner…", icon="sparkles")
        self.suggest_button.setToolTip("Sık geçen adlar için Ollama'dan öneri ister; onaylamadan eklenmez.")
        self.suggest_button.clicked.connect(self._suggest)
        self.suggest_button.setVisible(can_suggest)
        self.library = TermLibraryButton(self)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        for b in (self.import_button, self.export_button, self.suggest_button):
            row.addWidget(b)
        row.addWidget(self.library)
        lay.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Kaydet")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        bind_icon(buttons.button(QDialogButtonBox.StandardButton.Cancel), "x")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _add(self, term: str, translation: str, note: str, edit: bool = False) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        items = [QTableWidgetItem(value) for value in (term, translation, note)]
        for col, item in enumerate(items):
            self.table.setItem(r, col, item)
        if edit:
            self.table.setCurrentCell(r, 0)
            self.table.editItem(items[0])

    def _remove(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def set_terms(self, terms: list[GlossaryTerm]) -> None:
        self.table.setRowCount(0)
        for t in terms:
            self._add(t.term, t.translation, t.note)

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Terminoloji dosyasını seç", str(self.start_dir), "Excel dosyaları (*.xlsx);;Tüm dosyalar (*)"
        )
        if not path:
            return
        self.start_dir = Path(path).parent
        try:
            imported = read_glossary_xlsx(Path(path))
        except NxError as exc:
            self.banner.show_message("danger", exc.user_text())
            return
        merged, added, updated = merge_terms(self.terms(), imported)
        self.set_terms(merged)
        self.banner.show_message(
            "success",
            f"{format_int(added)} terim eklendi, {format_int(updated)} terim güncellendi. "
            "Saklamak için Kaydet'e basın.",
        )

    def _export(self) -> None:
        terms = self.terms()
        fixed = [t for t in terms if t.translation]
        if not fixed:
            self.banner.show_message("warning", "Dışa aktarılacak, Türkçe karşılığı olan terim yok.")
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Terminolojiyi kaydet", str(self.start_dir / "terminoloji.xlsx"), "Excel dosyaları (*.xlsx)"
        )
        if not target:
            return
        path = Path(target)
        if path.suffix.lower() != ".xlsx":
            path = path.with_name(path.name + ".xlsx")
        self.start_dir = path.parent
        try:
            export_glossary_xlsx(fixed, path)
        except NxError as exc:
            self.banner.show_message("danger", exc.user_text())
            return
        text = f"{format_int(len(fixed))} terim {path.name} dosyasına yazıldı."
        if len(fixed) < len(terms):
            text += (
                f" {format_int(len(terms) - len(fixed))} bilgi notu (çevirisiz madde) iki sütuna sığmadığı için "
                "yazılmadı."
            )
        self.banner.show_message("success", text)

    def _suggest(self) -> None:
        self.wants_suggestions = True
        self.accept()

    def terms(self) -> list[GlossaryTerm]:
        out = []
        for r in range(self.table.rowCount()):
            cells = []
            for c in range(3):
                item = self.table.item(r, c)
                cells.append(item.text().strip() if item is not None else "")
            if cells[0] and (cells[1] or cells[2]):
                out.append(GlossaryTerm(cells[0], cells[1], cells[2]))
        return out


class TermSuggestionsDialog(QDialog):
    """Modelin terim önerileri: kullanıcı işaretlediklerini (düzelterek) terminolojiye ekler."""

    def __init__(self, parent: QWidget | None, suggestions: list[TermSuggestion]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Terim Önerileri")
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(
            title_row(
                f"{format_int(len(suggestions))} terim önerisi",
                "Eklemek istediklerinizi işaretli bırakın; çeviriyi ve notu tabloda düzeltebilirsiniz. Model "
                "yanılabilir: karakter adlarının çevrilmediğinden emin olun.",
                "cardTitle",
            )
        )
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Terim", "Türkçe karşılığı", "Not", "Geçiş"])
        self.table.verticalHeader().hide()
        h = self.table.horizontalHeader()
        for col in range(3):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table, 1)
        for s in suggestions:
            r = self.table.rowCount()
            self.table.insertRow(r)
            term = QTableWidgetItem(s.term)
            term.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            term.setCheckState(Qt.CheckState.Checked)
            count = QTableWidgetItem(format_int(s.count))
            count.setFlags(Qt.ItemFlag.ItemIsEnabled)
            count.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            for col, item in enumerate((term, QTableWidgetItem(s.translation), QTableWidgetItem(s.note), count)):
                self.table.setItem(r, col, item)
        row = QHBoxLayout()
        all_on = button("Tümünü İşaretle")
        all_on.clicked.connect(lambda: self._check_all(Qt.CheckState.Checked))
        all_off = button("İşaretleri Kaldır")
        all_off.clicked.connect(lambda: self._check_all(Qt.CheckState.Unchecked))
        row.addWidget(all_on)
        row.addWidget(all_off)
        row.addStretch(1)
        lay.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Seçilenleri Terminolojiye Ekle")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        bind_icon(buttons.button(QDialogButtonBox.StandardButton.Cancel), "x")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _check_all(self, state: Qt.CheckState) -> None:
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None:
                item.setCheckState(state)

    def _text(self, r: int, c: int) -> str:
        item = self.table.item(r, c)
        return item.text().strip() if item is not None else ""

    def selected(self) -> list[GlossaryTerm]:
        out = []
        for r in range(self.table.rowCount()):
            term = self.table.item(r, 0)
            if term is None or term.checkState() != Qt.CheckState.Checked:
                continue
            translation, note = self._text(r, 1), self._text(r, 2)
            if translation or note:
                out.append(GlossaryTerm(term.text(), translation, note))
        return out


class AddTermsDialog(QDialog):
    """Seçili satırlardan çıkan terimler: işaretlenenler terminolojiye eklenir (çakışmalar işaretsiz başlar)."""

    def __init__(
        self,
        parent: QWidget | None,
        new: Sequence[GlossaryTerm],
        conflicts: Sequence[tuple[GlossaryTerm, GlossaryTerm]],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Terminolojiye Ekle")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(
            title_row(
                "Terminolojiye ekle",
                "İşaretlediğiniz terimler eklenir. Turuncu satırlar terminolojide başka bir karşılıkla var; "
                "işaretlerseniz karşılık güncellenir.",
                "cardTitle",
            )
        )
        self.list = QListWidget()
        self._terms: list[GlossaryTerm] = []
        for term in new:
            self._item(f"{term.term} → {term.translation}", term, checked=True)
        for old, candidate in conflicts:
            item = self._item(
                f"{old.term}: {old.translation} → {candidate.translation}",
                GlossaryTerm(old.term, candidate.translation, old.note),
                checked=False,
            )
            item.setForeground(QColor(current_tokens()["warning"]))
            item.setToolTip("Terminolojide başka bir karşılıkla var; işaretlerseniz yeni karşılık yazılır.")
        lay.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Ekle")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _item(self, text: str, term: GlossaryTerm, *, checked: bool) -> QListWidgetItem:
        item = QListWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.list.addItem(item)
        self._terms.append(term)
        return item

    def selected(self) -> list[GlossaryTerm]:
        return [
            term
            for i, term in enumerate(self._terms)
            if (item := self.list.item(i)) is not None and item.checkState() == Qt.CheckState.Checked
        ]
