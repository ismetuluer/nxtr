"""Küfür / argo denetimi: eşleştirici (çekirdek), sözlük dosyası ve Kontrol Et bulgusu."""

from __future__ import annotations

import pytest

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa import profanity
from nxceviri.core.qa.checks import SEVERITY_WARNING, check_row, run_checks
from nxceviri.core.qa.profanity import LEVEL_ALL, LEVEL_HEAVY, LEVEL_OFF, ProfanityConfig, find_profanity

HEAVY = ProfanityConfig(LEVEL_HEAVY)
ALL = ProfanityConfig(LEVEL_ALL)


def _words(text: str, config: ProfanityConfig = ALL, source: str = "") -> list[tuple[str, str]]:
    return [(m.word, m.level) for m in find_profanity(text, config, source)]


def test_sozluk_dosyasi_gecerli_ve_makul_buyuklukte() -> None:
    entries = profanity.load_entries()
    assert 80 <= len(entries.heavy) + len(entries.slang) <= 200
    assert entries.heavy
    assert entries.slang
    assert entries.exceptions


@pytest.mark.parametrize(
    "text",
    ["Siktir git!", "Seni siker miyim", "Orospu çocuğu", "Piç kurusu", "Götünü kaldır", "Yarrak gibi", "AMK"],
)
def test_agir_kufur_ekli_bicimlerle_yakalanir(text: str) -> None:
    found = _words(text, HEAVY)
    assert found
    assert all(level == LEVEL_HEAVY for _word, level in found)


@pytest.mark.parametrize(
    "text", ["Lan buraya gel", "Ulan ne yapıyorsun", "Bu çok boktan", "Defol buradan", "Dangalak!"]
)
def test_argo_yakalanir_ve_yalnizca_agir_seviyede_gorulmez(text: str) -> None:
    assert _words(text, ALL)
    assert not _words(text, HEAVY)


@pytest.mark.parametrize(
    "text",
    [
        "Eski bir sikke buldum",
        "Sikkeler sandıkta",
        "Siklet sınıfı",
        "Siklon yaklaşıyor",
        "Sıkıntı yok, sıkı dur",
        "Kutuyu götürmek zorundayız",
        "Götürü usulü ödeme",
        "Göteborg'a gidiyoruz",
        "Amcam geldi, ama sen gitme, amaç bu",
        "Boks maçı ve boksör",
        "Boksit madeni",
        "Malzeme topla",
        "Dalya dedi",
        "Sıçrama yap, sıçan kaçtı",
        "Kodumu düzelt",
        "Bir porsiyon çorba",
        "Piyade birliği",
        "Yaralı asker",
        "Taşıyıcı ve taş",
        "Osman burada",
    ],
)
def test_masum_sozcukler_yakalanmaz(text: str) -> None:
    assert _words(text, ALL) == []


def test_buyuk_kucuk_harf_turkce_kuralina_gore() -> None:
    assert _words("SİKTİR", HEAVY)  # İ → i
    assert _words("SIKTIR", HEAVY) == []  # I → ı: "sıktır" başka sözcük, küfür değil
    assert _words("Orospu", HEAVY)
    assert _words("OROSPU", HEAVY)


def test_kisa_buyuk_harfli_kisaltma_argoda_atlanir_ama_agirda_atlanmaz() -> None:
    assert _words("LAN bağlantısı kuruldu", ALL) == []
    assert _words("Lan bağlantısı", ALL)
    assert _words("AMK", HEAVY)


def test_yer_tutucu_ve_etiketler_gorunen_metne_katilmaz() -> None:
    assert _words("⟦1⟧Merhaba⟦2⟧", ALL) == []
    # Yer tutucu sözcüğü bölmez: "si⟦1⟧ktir" iki parça olarak görünür, küfür değildir.
    assert _words("si⟦1⟧ktir", HEAVY) == []
    assert _words("⟦1⟧Siktir⟦2⟧", HEAVY)


def test_kapali_seviye_hicbir_sey_bulmaz() -> None:
    assert _words("Siktir lan", ProfanityConfig(LEVEL_OFF)) == []
    assert not ProfanityConfig(LEVEL_OFF).enabled


def test_izin_listesi_sozcugu_susturur() -> None:
    config = ProfanityConfig(LEVEL_ALL, frozenset({"lan"}))
    assert _words("Lan bu ne?", config) == []
    assert _words("Lan, siktir!", config) == [("siktir", LEVEL_HEAVY)]


def test_kaynakta_aynen_gecen_sozcuk_ozel_ad_sayilir() -> None:
    assert _words("Lan Ying geldi", ALL, source="Lan Ying arrived") == []
    assert _words("Lan Ying geldi", ALL, source="Ying arrived")


def test_ayni_sozcuk_bir_kez_ve_ilk_gorunen_yazimla_bildirilir() -> None:
    assert _words("Siktir, SİKTİR!", HEAVY) == [("Siktir", LEVEL_HEAVY)]


def test_ingilizce_kaba_ifade_orijinalde() -> None:
    assert profanity.english_rude("What the fuck is this?")
    assert profanity.english_rude("You bastard!")
    assert not profanity.english_rude("Pass the class, assistant")
    assert not profanity.english_rude("Scunthorpe")


def _row(source: str, translation: str, row_id: int = 1) -> TranslationRow:
    return TranslationRow(row_id, "f", f"k{row_id}", source, translation, "machine", "", (), None)


def test_kontrol_varsayilan_kapali() -> None:
    issues = check_row(_row("Damn it", "Siktir"), "", "")
    assert all(i.kind != "profanity" for i in issues)


def test_kontrol_bulgusu_uyari_ve_tek_bulgu() -> None:
    issues = check_row(_row("Hey you!", "Hey lan, siktir git, piç"), "", "", profanity=ALL)
    found = [i for i in issues if i.kind == "profanity"]
    assert len(found) == 1
    issue = found[0]
    assert issue.severity == SEVERITY_WARNING
    assert issue.message.startswith("Ağır küfür: ")
    assert "siktir" in issue.message
    assert "Argo: lan" in issue.message
    assert sorted(issue.words) == ["lan", "piç", "siktir"]
    assert "orijinalde" not in issue.message


def test_kontrol_yalnizca_agir_seviye() -> None:
    issues = check_row(_row("Hey you!", "Hey lan, siktir git"), "", "", profanity=HEAVY)
    found = [i for i in issues if i.kind == "profanity"]
    assert len(found) == 1
    assert "Argo" not in found[0].message


def test_kontrol_orijinalde_de_kaba_ifade_notu() -> None:
    issues = check_row(_row("What the fuck!", "Ne siktiriboktan"), "", "", profanity=ALL)
    found = [i for i in issues if i.kind == "profanity"]
    assert found
    assert "orijinalde de kaba ifade var" in found[0].message


def test_run_checks_profanity_gecirir() -> None:
    rows = [_row("Hello", "Merhaba", 1), _row("Hey", "Siktir", 2)]
    issues = run_checks(rows, "", "", profanity=HEAVY)
    assert [i.row_id for i in issues if i.kind == "profanity"] == [2]
    assert not [i for i in run_checks(rows, "", "") if i.kind == "profanity"]


def test_canli_denetim_destekler() -> None:
    from nxceviri.core.qa.live import LIVE_KINDS, LiveChecker, LiveContext

    assert "profanity" in LIVE_KINDS
    checker = LiveChecker()
    checker.set_context(LiveContext(profanity=HEAVY))
    row = _row("Hey", "Siktir")
    assert any(i.kind == "profanity" for i in checker.check(row))
    checker.set_context(LiveContext())
    assert not any(i.kind == "profanity" for i in checker.check(row))
