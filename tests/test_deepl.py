"""DeepL sağlayıcısı (sahte sunucuyla), gizli anahtar deposu ve sağlayıcılar arası geçiş."""

from __future__ import annotations

import logging

import pytest

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import DEEPL_API_KEY, KeyringStore, MemoryStore
from nxceviri.core.translate import runner as runner_module
from nxceviri.core.translate.providers.base import BatchItem, GlossaryTerm, ProviderError
from nxceviri.core.translate.providers.deepl import (
    FREE_URL,
    PRO_URL,
    DeepLProvider,
    deepl_lang,
    endpoint_for,
    from_xml,
    plan_label,
    to_xml,
)
from nxceviri.core.translate.runner import MachineJob, run_machine_translation
from nxceviri.core.translate.status import Status
from tests.fake_deepl import FREE_KEY, PRO_KEY, FakeDeepL
from tests.fake_ollama import FakeOllama


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "RETRY_DELAYS_S", (0.0, 0.0))


def test_endpoint_detection() -> None:
    assert endpoint_for(FREE_KEY) == FREE_URL
    assert endpoint_for(PRO_KEY) == PRO_URL
    assert plan_label(FREE_KEY) == "DeepL API Free"
    assert FakeDeepL().provider(FREE_KEY).base_url == FREE_URL
    assert FakeDeepL().provider(PRO_KEY).base_url == PRO_URL
    with pytest.raises(ProviderError, match="girilmemiş"):
        DeepLProvider("  ")


@pytest.mark.parametrize(
    ("code", "target", "expected"),
    [
        ("en", False, "EN"),
        ("en", True, "EN-US"),
        ("pt-BR", False, "PT"),
        ("pt-BR", True, "PT-BR"),
        ("zh-Hant", True, "ZH-HANT"),
        ("zh", True, "ZH-HANS"),
        ("tr", True, "TR"),
        ("ja", False, "JA"),
    ],
)
def test_language_codes(code: str, target: bool, expected: str) -> None:
    assert deepl_lang(code, target=target) == expected


def test_xml_round_trip() -> None:
    text = 'Press ⟦1⟧ & <wait> ⟦2⟧ "now"\nok'
    xml = to_xml(text)
    assert xml == 'Press <x id="1"/> &amp; &lt;wait&gt; <x id="2"/> "now"\nok'
    assert from_xml(xml) == text
    assert from_xml('A <x id="1"></x> b <x id = "2" />') == "A ⟦1⟧ b ⟦2⟧"


def test_connection_and_quota() -> None:
    server = FakeDeepL(used=12_345, limit=500_000)
    status = server.provider().test_connection()
    assert status.ok
    assert "DeepL API Free" in status.message
    assert "12.345 / 500.000" in status.message
    full = FakeDeepL(used=500_000, limit=500_000).provider().test_connection()
    assert not full.ok
    assert "kotası dolu" in full.message
    bad = FakeDeepL(status=403).provider().test_connection()
    assert not bad.ok
    assert "geçersiz" in bad.message
    est = server.provider().estimate_cost([BatchItem("0", "x" * 600_000)])
    assert est is not None
    assert "Kota yetmeyebilir" in est


def test_translate_batch_request() -> None:
    server = FakeDeepL()
    provider = server.provider()
    res = provider.translate_batch(
        [BatchItem("0", "Hello ⟦1⟧Link⟦2⟧!"), BatchItem("1", "Talk to the Sheriff")],
        "en",
        "tr",
        "Korku oyunu.",
        [GlossaryTerm("Sheriff", "Şerif")],
    )
    assert [r.text for r in res] == ["tr-Hello ⟦1⟧tr-Link⟦2⟧!", "tr-Talk tr-to tr-the tr-Sheriff"]
    translate = next(b for m, p, b, _ in server.requests if p == "/v2/translate")
    assert translate["text"][0] == 'Hello <x id="1"/>Link<x id="2"/>!'
    assert (translate["source_lang"], translate["target_lang"]) == ("EN", "TR")
    assert translate["tag_handling"] == "xml"
    assert translate["context"] == "Korku oyunu."
    assert translate["glossary_id"] == "sozluk-1"
    assert server.glossaries == {"sozluk-1": "Sheriff\tŞerif"}
    # Yeni terim gelince sözlük birleşimle yeniden kurulur, eskisi silinir.
    provider.translate_batch([BatchItem("2", "A Motel")], "en", "tr", "", [GlossaryTerm("Motel", "Motel")])
    assert server.glossaries == {"sozluk-2": "Sheriff\tŞerif\nMotel\tMotel"}
    provider.close()
    assert server.glossaries == {}


def test_glossary_unsupported_continues_with_warning() -> None:
    server = FakeDeepL(glossary_error=400)
    provider = server.provider()
    res = provider.translate_batch([BatchItem("0", "Sheriff")], "en", "tr", "", [GlossaryTerm("Sheriff", "Şerif")])
    assert res[0].text == "tr-Sheriff"
    assert provider.warnings
    assert "sözlüksüz" in provider.warnings[0]


@pytest.mark.parametrize(
    ("code", "message", "retryable"),
    [
        (403, "geçersiz", False),
        (456, "kotanız doldu", False),
        (429, "çok fazla istek", True),
        (500, "geçici", True),
        (413, "çok büyük", False),
        (400, "reddetti", False),
    ],
)
def test_error_mapping(code: int, message: str, retryable: bool) -> None:
    with pytest.raises(ProviderError, match=message) as exc:
        FakeDeepL(status=code).provider().translate_batch([BatchItem("0", "a")], "en", "tr", "", [])
    assert exc.value.retryable is retryable


def test_api_key_never_leaks(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    provider = FakeDeepL(status=403).provider(FREE_KEY)
    status = provider.test_connection()
    with pytest.raises(ProviderError) as exc:
        provider.translate_batch([BatchItem("0", "a")], "en", "tr", "", [])
    secret = FREE_KEY.split(":")[0]
    for text in (repr(provider), status.message, exc.value.user_text(), caplog.text):
        assert secret not in text


# --- toplu çeviri, sağlayıcı geçişi --------------------------------------------------------


@pytest.fixture
def project() -> Project:
    p = Project.new()
    entries = (
        TextEntry("a", 0, "Hello ⟦1⟧Link⟦2⟧!", ()),
        TextEntry("b", 1, "Start Game", ()),
        TextEntry("c", 2, "Options", ()),
    )
    p.import_texts([ImportedFile("m.msbt", "0", "msbt", "base", entries)])
    return p


def _run(project: Project, provider: object) -> runner_module.RunSummary:
    rows = [r for r in project.translation_rows() if r.status == Status.UNTRANSLATED]
    job = MachineJob(rows=rows, source_lang="en", memory=project.memory_lookup(r.source for r in rows))

    def write(results: list[tuple[int, str]]) -> None:
        project.set_translations(results, machine=True)

    return run_machine_translation(provider, job, TaskContext(), write)  # type: ignore[arg-type]


def test_deepl_job_and_moved_tags_marked(project: Project) -> None:
    summary = _run(project, FakeDeepL(move_tags=True).provider())
    rows = {r.key: r for r in project.translation_rows()}
    assert rows["b"].status == Status.MACHINE
    # DeepL etiketleri yer değiştirdi: sıra kuralı gereği "hatalı" (yeniden denemede de aynı).
    assert rows["a"].status == Status.ERROR
    assert summary.broken == 1


def test_switching_providers_in_same_project(project: Project) -> None:
    """Aynı projede önce DeepL (kota dolunca durur), sonra Ollama ile kalanlar çevrilir."""
    deepl = FakeDeepL(translate_status=[200, 456])
    deepl_provider = deepl.provider()
    deepl_provider.max_batch_items = 1  # her satır ayrı istek
    with pytest.raises(ProviderError, match="kotanız doldu"):
        _run(project, deepl_provider)
    counts = project.translation_counts()
    assert counts["machine"] == 1
    _run(project, FakeOllama().provider())
    assert project.translation_counts() == {
        "untranslated": 0,
        "machine": 3,
        "redacted": 0,
        "approved": 0,
        "error": 0,
    }


def test_secret_stores() -> None:
    mem = MemoryStore()
    assert mem.get(DEEPL_API_KEY) is None
    mem.set(DEEPL_API_KEY, FREE_KEY)
    assert mem.get(DEEPL_API_KEY) == FREE_KEY
    assert FREE_KEY not in repr(mem)
    mem.delete(DEEPL_API_KEY)
    mem.delete(DEEPL_API_KEY)  # yoksa sessiz
    assert mem.get(DEEPL_API_KEY) is None


def test_keyring_store_round_trip() -> None:
    """Gerçek Windows Kimlik Bilgisi Yöneticisi; test için ayrı servis adı kullanılır."""
    store = KeyringStore("NXCeviriStudyosu-Test")
    store.set("deneme", "değer-ğüş")
    try:
        assert store.get("deneme") == "değer-ğüş"
    finally:
        store.delete("deneme")
    assert store.get("deneme") is None
    store.delete("deneme")
