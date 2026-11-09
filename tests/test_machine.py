"""Makine çevirisi: Ollama sağlayıcısı (sahte sunucuyla), toplu çeviri, bellek, sözlük, devam etme."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from nxceviri.core.errors import OperationCancelled
from nxceviri.core.formats.base import TextEntry
from nxceviri.core.progress import CancelToken, TaskContext
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.translate import runner as runner_module
from nxceviri.core.translate.providers.base import BatchItem, GlossaryTerm, ProviderError
from nxceviri.core.translate.providers.ollama import (
    OLLAMA_SEED,
    RECOMMENDED_MODELS,
    OllamaProvider,
    build_messages,
    extract_translations,
)
from nxceviri.core.translate.runner import MachineJob, relevant_terms, run_machine_translation
from nxceviri.core.translate.status import Status
from tests.fake_ollama import FakeOllama, fake_translate


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "RETRY_DELAYS_S", (0.0, 0.0))


# --- sağlayıcı ---------------------------------------------------------------------------


def test_connection_ok_and_models() -> None:
    server = FakeOllama()
    provider = server.provider()
    status = provider.test_connection()
    assert status.ok
    assert "0.34.4" in status.message
    models = provider.list_models()
    assert [m.name for m in models if m.can_chat] == ["gemma4:12b"]  # gömme modeli elenir
    assert models[0].parameters == "12B"


def test_connection_problems() -> None:
    down = FakeOllama(down=True).provider().test_connection()
    assert not down.ok
    assert "bağlanılamadı" in down.message
    assert "ollama serve" in down.message
    missing = FakeOllama().provider("yok:7b").test_connection()
    assert not missing.ok
    assert "yüklü değil" in missing.message
    only_embedding = FakeOllama(
        models=[{"name": "bge-m3:latest"}], capabilities={"bge-m3:latest": ["embedding"]}
    ).provider("bge-m3:latest")
    status = only_embedding.test_connection()
    assert not status.ok
    assert f"ollama pull {RECOMMENDED_MODELS[0][0]}" in status.message


def test_translate_batch_request_shape() -> None:
    server = FakeOllama()
    provider = server.provider()
    assert provider.test_connection().ok
    items = [BatchItem("0", "Hello ⟦1⟧Link⟦2⟧!", "Dialogue/Greet"), BatchItem("1", "Sword", "", 10)]
    glossary = [GlossaryTerm("Link", "Link", "karakter adı; çevrilmez")]
    results = provider.translate_batch(items, "en", "tr", "Korku oyunu, ciddi ton.", glossary)
    assert [(r.id, r.text) for r in results] == [("0", "tr-Hello ⟦1⟧tr-Link⟦2⟧!"), ("1", "tr-Sword")]
    body = server.requests[0]
    assert body["stream"] is True  # akış: iptal anında kesilir, takılma anlaşılır
    assert body["think"] is False  # model düşünme destekliyor; kapatıldı
    assert body["format"]["required"] == ["translations"]
    assert "Turkish" in body["messages"][0]["content"]
    assert "⟦1⟧" in body["messages"][0]["content"]
    # Oyun notları her partide aynıdır: sistem isteminde durur (model daha sıkı uyar, Ollama istemi önbellekten okur).
    assert "Korku oyunu, ciddi ton." in body["messages"][0]["content"]
    # Düşük sıcaklık ve sabit tohum: aynı istem aynı çeviriyi verir, ifadeler partiden partiye değişmez.
    assert body["options"]["temperature"] == 0.2
    assert body["options"]["seed"] == OLLAMA_SEED
    payload = json.loads(body["messages"][1]["content"])
    assert "game_notes" not in payload
    assert payload["glossary"] == [{"term": "Link", "translation": "Link", "note": "karakter adı; çevrilmez"}]
    assert payload["items"][0]["key"] == "Dialogue/Greet"
    assert payload["items"][1]["max_length"] == 10


def test_translate_batch_errors() -> None:
    server = FakeOllama(bad_json=1, timeouts=0)
    provider = server.provider()
    with pytest.raises(ProviderError, match="JSON") as exc:
        provider.translate_batch([BatchItem("0", "a")], "en", "tr", "", [])
    assert exc.value.retryable
    server.timeouts = 1
    with pytest.raises(ProviderError, match="takılmış") as exc:
        provider.translate_batch([BatchItem("0", "a")], "en", "tr", "", [])
    assert not exc.value.retryable  # takılan Ollama'yı tekrar beklemek dakikalar kaybettirir
    assert "Quit Ollama" in exc.value.hint
    with pytest.raises(ProviderError, match="Model bulunamadı") as exc:
        server.provider("yok:1b").translate_batch([BatchItem("0", "a")], "en", "tr", "", [])
    assert "ollama pull yok:1b" in exc.value.hint
    assert not exc.value.retryable
    server.drop_texts = {"b": 1}
    res = provider.translate_batch([BatchItem("0", "a"), BatchItem("1", "b")], "en", "tr", "", [])
    assert res[1].text is None
    assert res[1].error


def test_build_messages_without_extras() -> None:
    payload = json.loads(build_messages([BatchItem("0", "x")], "ja", "tr", "  ", [])[1]["content"])
    assert payload == {"items": [{"id": "0", "text": "x"}]}


def test_relevant_terms() -> None:
    gl = [
        GlossaryTerm("Silver Pines", "Silver Pines"),
        GlossaryTerm("Sheriff", "Şerif"),
        GlossaryTerm("Motel", "Motel"),
    ]
    assert [g.term for g in relevant_terms(gl, ["Go to the sheriff.", "Welcome to Silver Pines"])] == [
        "Silver Pines",
        "Sheriff",
    ]


# --- toplu çeviri ve proje ------------------------------------------------------------------

SOURCES = [
    ("Menu_Start", "Start Game"),
    ("Menu_Hello", "Hello ⟦1⟧Link⟦2⟧!"),
    ("Yes_1", "Yes"),
    ("Yes_2", "Yes"),
    ("Yes_3", "Yes"),
    ("Empty", ""),
    ("Sheriff", "Talk to the Sheriff"),
] + [(f"Line_{i:03d}", f"Line number {i}") for i in range(60)]


@pytest.fixture
def project() -> Project:
    p = Project.new()
    entries = tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(SOURCES))
    p.import_texts([ImportedFile("Message/a.msbt", "0100", "msbt", "base", entries)])
    return p


def _job(project: Project, **kw: object) -> MachineJob:
    rows = [r for r in project.translation_rows() if r.status == Status.UNTRANSLATED]
    return MachineJob(rows=rows, source_lang="en", memory=project.memory_lookup(r.source for r in rows), **kw)  # type: ignore[arg-type]


def _write(project: Project) -> runner_module.ResultsCallback:
    def write(results: list[tuple[int, str]]) -> None:
        project.set_translations(results, machine=True)

    return write


def test_full_run_dedupes_and_marks_machine(project: Project) -> None:
    server = FakeOllama()
    summary = run_machine_translation(server.provider(), _job(project), TaskContext(), _write(project))
    rows = {r.key: r for r in project.translation_rows()}
    assert rows["Menu_Hello"].translation == "tr-Hello ⟦1⟧tr-Link⟦2⟧!"
    assert {rows[k].translation for k in ("Yes_1", "Yes_2", "Yes_3")} == {"tr-Yes"}
    assert all(rows[k].status == Status.MACHINE for k in rows if k != "Empty")
    assert rows["Empty"].status == Status.UNTRANSLATED
    sent = [it["text"] for req in server.requests for it in json.loads(req["messages"][1]["content"])["items"]]
    assert sent.count("Yes") == 1  # aynı cümle bir kez çevrilir
    assert summary.unique_sources == len(sent)
    assert summary.translated == len(SOURCES) - 1
    assert len(server.requests) > 1  # partilere bölündü
    assert all(len(json.loads(r["messages"][1]["content"])["items"]) <= 25 for r in server.requests)
    assert project.memory_size() == summary.unique_sources


def test_memory_hits_are_not_sent(project: Project) -> None:
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["Yes_1"].id, "Evet")])  # insan çevirisi belleğe girer
    server = FakeOllama()
    summary = run_machine_translation(server.provider(), _job(project), TaskContext(), _write(project))
    after = {r.key: r for r in project.translation_rows()}
    assert (after["Yes_2"].translation, after["Yes_3"].translation) == ("Evet", "Evet")
    sent = [it["text"] for req in server.requests for it in json.loads(req["messages"][1]["content"])["items"]]
    assert "Yes" not in sent
    assert summary.from_memory == 2
    assert after["Yes_1"].status == Status.APPROVED


def test_machine_does_not_overwrite_human_memory(project: Project) -> None:
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["Yes_1"].id, "Evet")])
    project.set_translations([(rows["Yes_2"].id, "Makine evet")], machine=True)
    assert project.memory_lookup(["Yes"]) == {"Yes": ("Evet", "human")}
    project.set_translations([(rows["Yes_3"].id, "Tamam")])  # yeni insan çevirisi güncelleyebilir
    assert project.memory_lookup(["Yes"]) == {"Yes": ("Tamam", "human")}


def test_glossary_only_relevant_terms_sent(project: Project) -> None:
    server = FakeOllama()
    glossary = [GlossaryTerm("Sheriff", "Şerif"), GlossaryTerm("Dragon", "Ejderha")]
    run_machine_translation(server.provider(), _job(project, glossary=glossary), TaskContext(), _write(project))
    sent_glossaries = [json.loads(r["messages"][1]["content"]).get("glossary") for r in server.requests]
    with_terms = [g for g in sent_glossaries if g]
    assert with_terms == [[{"term": "Sheriff", "translation": "Şerif"}]]


def test_broken_placeholders_are_retried_then_marked(project: Project) -> None:
    server = FakeOllama(break_texts={"Hello ⟦1⟧Link⟦2⟧!": 1})
    summary = run_machine_translation(server.provider(), _job(project), TaskContext(), _write(project))
    assert summary.retried == 1
    assert {r.key: r for r in project.translation_rows()}["Menu_Hello"].status == Status.MACHINE

    p2 = Project.new()
    entries = (TextEntry("Hello", 0, "Hello ⟦1⟧Link⟦2⟧!", ()),)
    p2.import_texts([ImportedFile("a", "0", "msbt", "base", entries)])
    stubborn = FakeOllama(break_texts={"Hello ⟦1⟧Link⟦2⟧!": 5})
    summary = run_machine_translation(stubborn.provider(), _job(p2), TaskContext(), _write(p2))
    row = p2.translation_rows()[0]
    assert summary.broken == 1
    assert row.status == Status.ERROR  # dışa aktarılmaz, kullanıcı düzeltir
    assert "Eksik kontrol kodu" in row.note
    assert row.translation  # çeviri silinmez, düzeltilmek üzere görünür


def test_dropped_rows_stay_untranslated(project: Project) -> None:
    server = FakeOllama(drop_texts={"Start Game": 2})
    summary = run_machine_translation(server.provider(), _job(project), TaskContext(), _write(project))
    assert summary.missing == 1
    assert {r.key: r for r in project.translation_rows()}["Menu_Start"].status == Status.UNTRANSLATED


def test_transient_errors_are_retried(project: Project) -> None:
    server = FakeOllama(bad_json=2)
    run_machine_translation(server.provider(), _job(project), TaskContext(), _write(project))
    assert project.translation_counts()["untranslated"] == 1  # yalnızca boş satır


def test_failure_keeps_progress_and_resumes(project: Project) -> None:
    """Sunucu yarıda çökerse o ana kadarki partiler kayıtlı kalır; yeniden başlatınca kalanlar çevrilir."""
    server = FakeOllama(fail_after=1)
    with pytest.raises(ProviderError, match="HTTP 500"):
        run_machine_translation(server.provider(), _job(project), TaskContext(), _write(project))
    counts = project.translation_counts()
    assert counts["machine"] > 0
    assert counts["untranslated"] > 1
    done_before = {r.key for r in project.translation_rows() if r.status == Status.MACHINE}

    healthy = FakeOllama()
    run_machine_translation(healthy.provider(), _job(project), TaskContext(), _write(project))
    sent = {it["text"] for req in healthy.requests for it in json.loads(req["messages"][1]["content"])["items"]}
    rows = {r.key: r for r in project.translation_rows()}
    assert not {rows[k].source for k in done_before} & sent  # bitenler tekrar gönderilmedi
    assert project.translation_counts()["untranslated"] == 1


def test_cancel_keeps_progress(project: Project) -> None:
    token = CancelToken()
    calls: list[int] = []

    def write(results: list[tuple[int, str]]) -> None:
        project.set_translations(results, machine=True)
        calls.append(len(results))
        token.cancel()

    with pytest.raises(OperationCancelled):
        run_machine_translation(FakeOllama().provider(), _job(project), TaskContext(token=token), write)
    assert len(calls) == 1
    assert project.translation_counts()["machine"] == calls[0]


def test_connection_failure_stops_before_anything(project: Project) -> None:
    with pytest.raises(ProviderError, match="bağlanılamadı"):
        run_machine_translation(FakeOllama(down=True).provider(), _job(project), TaskContext(), _write(project))
    assert project.translation_counts()["machine"] == 0


def test_requires_result_callback(project: Project) -> None:
    with pytest.raises(ValueError, match="geri çağrı"):
        run_machine_translation(FakeOllama().provider(), _job(project), TaskContext())


def test_publish_via_context(project: Project) -> None:
    got: list[object] = []
    run_machine_translation(FakeOllama().provider(), _job(project), TaskContext(publish=got.append))
    assert got


def test_glossary_settings_persist(tmp_path: Path) -> None:
    p = Project.new()
    p.set_glossary([GlossaryTerm("Sheriff", "Şerif", "unvan"), GlossaryTerm("  ", "boş"), GlossaryTerm("Link", "Link")])
    p.set_setting("translation_notes", "Korku oyunu; ciddi, kısa cümleler.")
    p.save_as(tmp_path / "ayarlı ğüş.nxproj")
    p.close()
    q = Project.open(tmp_path / "ayarlı ğüş.nxproj")
    assert q.glossary() == [GlossaryTerm("Sheriff", "Şerif", "unvan"), GlossaryTerm("Link", "Link", "")]
    assert q.setting("translation_notes") == "Korku oyunu; ciddi, kısa cümleler."
    assert q.setting("yok", "varsayılan") == "varsayılan"
    q.close()


def test_fake_translate_keeps_tokens() -> None:
    assert fake_translate("Press ⟦1⟧ to open") == "tr-Press ⟦1⟧ tr-to tr-open"


def test_machine_never_overwrites_approved(project: Project) -> None:
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["Menu_Start"].id, "Oyuna Başla")])
    updated = project.set_translations(
        [(rows["Menu_Start"].id, "Makine yazdı"), (rows["Yes_1"].id, "Evet")], machine=True
    )
    assert [r.key for r in updated] == ["Yes_1"]
    after = {r.key: r for r in project.translation_rows()}
    assert (after["Menu_Start"].translation, after["Menu_Start"].status) == ("Oyuna Başla", Status.APPROVED)


class _HangingStream(httpx.SyncByteStream):
    """Ollama takılmış gibi: ilk parçayı verir, sonra bağlantı kapatılana kadar bekler."""

    def __init__(self) -> None:
        self.closed = threading.Event()

    def __iter__(self) -> Iterator[bytes]:
        yield b'{"message": {"content": "{\\"transl"}, "done": false}\n'
        self.closed.wait(10)
        raise httpx.ReadError("bağlantı kapatıldı")

    def close(self) -> None:
        self.closed.set()


def test_cancel_interrupts_a_hanging_request() -> None:
    stream = _HangingStream()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        return httpx.Response(200, stream=stream)

    provider = OllamaProvider("gemma4:12b", client=httpx.Client(transport=httpx.MockTransport(handler)))
    token = CancelToken()
    provider.cancel_token = token
    threading.Timer(0.3, token.cancel).start()
    started = time.monotonic()
    with pytest.raises(OperationCancelled):
        provider.translate_batch([BatchItem("0", "a")], "en", "tr", "", [])
    assert time.monotonic() - started < 3  # yanıtın bitmesi beklenmedi
    assert stream.closed.is_set()


def test_runner_hands_cancel_token_to_provider(project: Project) -> None:
    provider = FakeOllama().provider()
    ctx = TaskContext()
    run_machine_translation(provider, _job(project), ctx, _write(project))
    assert provider.cancel_token is ctx.token


@pytest.mark.parametrize(
    "content",
    [
        '{"translations": [{"id": "0", "text": "Merhaba"}]}',
        '```json\n{"translations": [{"id": "0", "text": "Merhaba"}]}\n```',
        '<think>Önce sahneyi düşüneyim...</think>\n{"translations": [{"id": "0", "text": "Merhaba"}]}',
        'İşte çeviri:\n{"translations": [{"id": "0", "text": "Merhaba"}]}\nUmarım yardımcı olur.',
    ],
)
def test_extract_translations_tolerates_wrappers(content: str) -> None:
    assert extract_translations(content) == [{"id": "0", "text": "Merhaba"}]


@pytest.mark.parametrize("content", ["", "Tabii! İşte çeviri:", '{"translations": "yok"}', '[{"id": "0"}]'])
def test_extract_translations_rejects_non_json(content: str) -> None:
    assert extract_translations(content) is None


def test_truncated_answer_is_explained(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        lines = [
            json.dumps({"message": {"content": "<think>Uzun uzun düşünüyorum"}, "done": False}),
            json.dumps({"message": {"content": "..."}, "done": True, "done_reason": "length"}),
        ]
        return httpx.Response(200, content="\n".join(lines).encode())

    provider = OllamaProvider("hf.co/deneme:Q3", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderError, match="uzunluk sınırında kesildi") as exc:
        provider.translate_batch([BatchItem("0", "Hello")], "en", "tr", "", [])
    assert "düşünme" in exc.value.hint
    assert "Uzun uzun düşünüyorum" in caplog.text  # model ne yazdıysa günlükte


@pytest.mark.parametrize(
    "content",
    [
        # Gemma 4 kanal işaretleri, içinde süslü parantezli taslak düşünce.
        '<|channel>thought\nTaslak: {"id": "0"} olmaz, düzelteyim.<channel|>'
        '{"translations": [{"id": "0", "text": "Merhaba"}]}',
        # Düşünürken yazılmış taslak JSON ve ardından son cevap: sonuncusu alınır.
        '{"translations": [{"id": "0", "text": "Selam"}]}\nDaha doğal olsun:\n'
        '{"translations": [{"id": "0", "text": "Merhaba"}]}',
    ],
)
def test_extract_translations_handles_gemma_channels_and_drafts(content: str) -> None:
    assert extract_translations(content) == [{"id": "0", "text": "Merhaba"}]


def test_truncated_answer_splits_the_batch_and_retries(project: Project) -> None:
    """Yarım kalan (uzunluk sınırında kesilen) yanıt: parti ikiye bölünerek yeniden istenir, satır kaybolmaz."""
    server = FakeOllama(truncate_over=2)
    summary = run_machine_translation(server.provider(), _job(project), TaskContext(), _write(project))
    rows = {r.key: r for r in project.translation_rows()}
    assert rows["Menu_Hello"].translation == "tr-Hello ⟦1⟧tr-Link⟦2⟧!"
    assert summary.missing == 0
    assert summary.translated == len(SOURCES) - 1
    sizes = [len(json.loads(r["messages"][1]["content"])["items"]) for r in server.requests]
    assert max(sizes) > 2  # ilk parti büyüktü ve kesildi
    assert summary.split >= 1


def test_truncated_single_item_still_fails_clearly(project: Project) -> None:
    server = FakeOllama(truncate_over=0)
    with pytest.raises(ProviderError, match="kesildi"):
        run_machine_translation(server.provider(), _job(project), TaskContext(), _write(project))
