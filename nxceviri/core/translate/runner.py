"""Toplu makine çevirisi, yeniden çeviri ve talimatla düzeltme (redaksiyon).

Üç iş türü vardır (`MachineJob.action`):

- **translate:** çevrilmemiş (ve hatalı) satırlar çevrilir. Satırlar kaynak metne göre gruplanır:
  **aynı cümle bir kez çevrilir**; çeviri belleğinde karşılığı olan metinler sağlayıcıya hiç
  gönderilmez.
- **retranslate:** seçilen satırlar mevcut çevirileri silinmeden yeniden çevrilir. Bellek
  atlanır ve her satır kendi sahnesinde ayrı çevrilir (kısa cevaplar bağlama göre değişir).
- **revise:** mevcut çeviriler kullanıcının talimatına göre düzeltilir.

Akış:

1. Sağlayıcının bağlantısı ve modeli denetlenir.
2. Satırlar oyundaki sıralarına göre dizilir; bir parti yalnızca **aynı dosyada art arda gelen**
   satırlardan kurulur. Her partiyle birlikte sahnedeki önceki ve sonraki satırlar (varsa
   çevirileriyle) bağlam olarak gönderilir: "Not me." gibi kısa cevapların veya "it/that"
   zamirlerinin neyi kastettiği ancak böyle anlaşılır.
3. Partiler karakter ve satır sınırına göre bölünür; her partiye yalnızca o partide geçen
   sözlük terimleri eklenir.
4. Dönen her çevirinin baştaki/sondaki boşlukları özgünle eşlenir, yer tutucuları (ve varsa ek
   kabul denetimi, `check`) denetlenir. Sorunlu veya eksik dönen satır, sorunu açıkça
   yazılarak bir kez tek başına yeniden istenir. Hâlâ sorunluysa:
   - satırın geçerli bir çevirisi yoksa çeviri yine yazılır, durum "hatalı" olur (dışa
     aktarılmaz, kullanıcı düzeltir);
   - geçerli bir çevirisi varsa **eski çeviri korunur** (bozuk sonuç yazılmaz);
   - hiç dönmeyen satır olduğu gibi kalır.
5. Her partinin sonucu `on_results` ile hemen kaydettirilir. İptal veya hata durumunda o ana
   kadarki sonuçlar korunur; aynı işlem yeniden başlatıldığında yalnızca çevrilmemiş satırlar
   kalır, yani iş **kaldığı yerden devam eder**.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from nxceviri.core.progress import TaskContext
from nxceviri.core.project import TranslationRow
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.cleanup import clean_output, is_line_break, misplaced_breaks
from nxceviri.core.translate.guards import revision_problems, translation_problems
from nxceviri.core.translate.providers.base import (
    BatchItem,
    BatchResult,
    ContextLine,
    GlossaryTerm,
    PlannedBatch,
    ProviderError,
    Scene,
    TranslationProvider,
)
from nxceviri.core.translate.status import Status

log = logging.getLogger(__name__)

ACTION_TRANSLATE = "translate"
ACTION_RETRANSLATE = "retranslate"
ACTION_REVISE = "revise"

#: Geçici hatalarda (zaman aşımı, 5xx) partinin yeniden denenmesinden önceki bekleme süreleri.
RETRY_DELAYS_S = (2.0, 6.0)

#: Partinin önünde ve arkasında bağlam olarak gönderilen satır sayısı.
CONTEXT_BEFORE = 8
CONTEXT_AFTER = 3

#: (satır kimliği, çeviri) listesi; çağıran bunu tek işlemde projeye yazar.
ResultsCallback = Callable[[list[tuple[int, str]]], None]

_MISSING = "Model bu satırı döndürmedi."
_MISPLACED_BREAK = (
    "Satır sonu kodu en sona konmuş; orijinaldeki gibi cümlenin ortasında, aynı iki parçayı ayıracak yere konmalı."
)


@dataclass(frozen=True)
class MachineJob:
    rows: list[TranslationRow]
    source_lang: str
    target_lang: str = "tr"
    notes: str = ""
    glossary: list[GlossaryTerm] = field(default_factory=list)
    memory: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    action: str = ACTION_TRANSLATE
    instruction: str = ""  # redaksiyon talimatı
    #: Projenin tüm satırları, dosya ve oyun sırasıyla: komşu satırları bağlam olarak göndermek için.
    #: Boşsa `rows` kullanılır.
    all_rows: Sequence[TranslationRow] = ()


@dataclass
class RunSummary:
    rows: int = 0
    unique_sources: int = 0  # sağlayıcıya gönderilmesi gereken metin sayısı
    from_memory: int = 0  # bellekten doldurulan satır sayısı
    translated: int = 0  # geçerli yeni çevirisi yazılan satır sayısı
    unchanged: int = 0  # yeniden çeviride/düzeltmede sonucu öncekiyle aynı kalan satır sayısı
    broken: int = 0  # yer tutucuları bozuk geldiği için "hatalı" yazılan satır sayısı
    rejected: int = 0  # sonucu sorunlu geldiği için eski çevirisi korunan satır sayısı
    missing: int = 0  # sağlayıcının hiç döndürmediği satır sayısı
    retried: int = 0  # tek başına yeniden istenen metin sayısı
    cleaned: int = 0  # modelin eklediği fazlalıkları temizlik katmanının attığı (yazılan) satır sayısı
    suspicious: int = 0  # yeniden istendiği hâlde uydurma belirtisi süren, yine de yazılan yeni çeviri sayısı
    warnings: list[str] = field(default_factory=list)  # sağlayıcının uyarıları (ör. sözlük kurulamadı)
    #: Reddedilen (eski çevirisi korunan) satırlardan örnekler: kullanıcı nedenini ve öneriyi görsün.
    rejections: list[Rejection] = field(default_factory=list)


#: `RunSummary.rejections` içinde tutulan en çok örnek sayısı.
MAX_REJECTION_SAMPLES = 5


@dataclass(frozen=True)
class Rejection:
    key: str  # satırın okunur adı
    suggestion: str  # modelin önerdiği (denetimden geçmeyen) çeviri
    issues: tuple[str, ...]


def target_rows(rows: Sequence[TranslationRow], action: str, include_approved: bool = False) -> list[TranslationRow]:
    """Bir işin uygulanacağı satırlar (boş kaynaklı satırlar hiçbir zaman).

    Çeviri yalnızca çevrilmemiş ve hatalı satırlara uygulanır. Yeniden çeviri ve düzeltme
    onaylanmış satırlara yalnızca kullanıcı açıkça isterse (`include_approved`) uygulanır.
    """
    out = []
    for r in rows:
        if not r.source.strip():
            continue
        if action == ACTION_TRANSLATE:
            if r.status in (Status.UNTRANSLATED, Status.ERROR):
                out.append(r)
        elif r.status != Status.APPROVED or include_approved:
            out.append(r)
    return out


def relevant_terms(glossary: list[GlossaryTerm], texts: list[str]) -> list[GlossaryTerm]:
    """Partideki metinlerden en az birinde geçen sözlük terimleri (büyük/küçük harf duyarsız)."""
    joined = "\n".join(texts).casefold()
    return [g for g in glossary if g.term.casefold() in joined]


def match_edges(source: str, text: str) -> str:
    """Çevirinin baştaki ve sondaki boşluklarını özgün metninkiyle aynı yapar.

    Modeller bu boşlukları sık sık siler veya ekler; oyun ise metinleri yan yana dizerken bunlara
    güvenebilir. İçerideki boşluklara dokunulmaz.
    """
    core = text.strip()
    if not core:
        return text
    lead = source[: len(source) - len(source.lstrip())]
    trail = source[len(source.rstrip()) :]
    return lead + core + trail


@dataclass
class _Unit:
    """Sağlayıcıya tek madde olarak giden iş: aynı kaynak metinli satırlar (çeviri) veya tek satır."""

    item_id: str
    rows: list[TranslationRow]

    @property
    def first(self) -> TranslationRow:
        return self.rows[0]

    @property
    def source(self) -> str:
        return self.first.source


class _Runner:
    def __init__(self, provider: TranslationProvider, job: MachineJob, ctx: TaskContext) -> None:
        self.provider = provider
        self.job = job
        self.ctx = ctx
        order = list(job.all_rows) or list(job.rows)
        self.by_file: dict[str, list[TranslationRow]] = {}
        self.position: dict[int, tuple[str, int]] = {}
        for r in order:
            lst = self.by_file.setdefault(r.file, [])
            self.position[r.id] = (r.file, len(lst))
            lst.append(r)
        self.rank = {r.id: i for i, r in enumerate(order)}
        self.targets = {r.id for r in job.rows}
        self.latest: dict[int, str] = {}  # bu işte yazılan çeviriler (sonraki partilerin bağlamı için)
        self.revise = job.action == ACTION_REVISE

    # --- partiler -------------------------------------------------------------------------

    def batches(self, units: list[_Unit]) -> list[list[_Unit]]:
        units = sorted(units, key=lambda u: self.rank.get(u.first.id, len(self.rank)))
        out: list[list[_Unit]] = []
        current: list[_Unit] = []
        size = 0
        for u in units:
            if current and (
                not self._follows(current[-1], u)
                or size + len(u.source) > self.provider.max_batch_chars
                or len(current) >= self.provider.max_batch_items
            ):
                out.append(current)
                current, size = [], 0
            current.append(u)
            size += len(u.source)
        if current:
            out.append(current)
        return out

    def _follows(self, prev: _Unit, unit: _Unit) -> bool:
        """`unit`, oyunda `prev`'in hemen ardından mı geliyor (aynı dosya, sıradaki satır)?"""
        a, b = self.position.get(prev.first.id), self.position.get(unit.first.id)
        return a is not None and b is not None and a[0] == b[0] and b[1] == a[1] + 1

    def scene(self, batch: list[_Unit]) -> Scene:
        start, end = self.position.get(batch[0].first.id), self.position.get(batch[-1].first.id)
        before: tuple[ContextLine, ...] = ()
        after: tuple[ContextLine, ...] = ()
        if start is not None and end is not None:
            rows = self.by_file[start[0]]
            before = self._lines(rows[max(start[1] - CONTEXT_BEFORE, 0) : start[1]])
            after = self._lines(rows[end[1] + 1 : end[1] + 1 + CONTEXT_AFTER])
        return Scene(before, after, revise=self.revise, instruction=self.job.instruction)

    def _lines(self, rows: list[TranslationRow]) -> tuple[ContextLine, ...]:
        return tuple(ContextLine(r.source, self._known_translation(r)) for r in rows if r.source.strip())

    def _known_translation(self, r: TranslationRow) -> str:
        if r.id in self.latest:
            return self.latest[r.id]
        if r.status not in (Status.MACHINE, Status.REDACTED, Status.APPROVED):
            return ""
        if r.id in self.targets and not self.revise:
            return ""  # yeniden çevrilecek: eski çeviriyi örnek göstermeyelim
        return r.translation

    def item(self, unit: _Unit) -> BatchItem:
        first = unit.first
        return BatchItem(
            unit.item_id,
            unit.source,
            first.context or first.key,
            first.max_length,
            current=first.translation if self.revise else "",
            codes=first.code_labels,
        )

    # --- istek ve denetim -----------------------------------------------------------------

    def call(self, items: list[BatchItem], scene: Scene) -> list[BatchResult]:
        terms = relevant_terms(self.job.glossary, [i.text for i in items])
        attempt = 0
        while True:
            self.ctx.check()
            try:
                return self.provider.translate_batch(
                    items, self.job.source_lang, self.job.target_lang, self.job.notes, terms, scene=scene
                )
            except ProviderError as exc:
                if not exc.retryable or attempt >= len(RETRY_DELAYS_S):
                    raise
                delay = RETRY_DELAYS_S[attempt]
                attempt += 1
                log.info("Parti yeniden denenecek (%d. deneme, %.0f sn sonra): %s", attempt, delay, exc.message)
                if self.ctx.token.wait(delay):
                    self.ctx.check()

    def problems(self, unit: _Unit, text: str | None) -> list[str]:
        if text is None:
            return [_MISSING]
        issues = placeholders.problems(unit.source, text)
        labels = unit.first.code_labels
        if (
            not issues
            and self.keeps_old(unit)
            and misplaced_breaks(unit.source, text, labels)
            and not misplaced_breaks(unit.source, unit.first.translation, labels)
        ):
            # Çevirisi olan satırda sona taşınmış satır sonu kodu, iyi bir çevirinin yerine yazılmaz.
            issues.append(_MISPLACED_BREAK)
        if not issues and self.keeps_old(unit):
            issues += revision_problems(
                unit.source, unit.first.translation, text, self.job.source_lang, self.job.target_lang
            )
        return issues

    def suspicions(self, unit: _Unit, text: str | None) -> list[str]:
        """Eski çevirisi olmayan satırın yeni çevirisinde uydurma belirtileri (kodlar yerindeyse sonuç yine yazılır)."""
        if text is None or self.keeps_old(unit):
            return []
        return translation_problems(unit.source, text, self.job.target_lang)

    def keeps_old(self, unit: _Unit) -> bool:
        """Satırın korunması gereken geçerli bir çevirisi var mı? (Varsa bozuk sonuç yazılmaz.)"""
        return any(r.translation and r.status != Status.ERROR for r in unit.rows)


#: Modelin satır sonu kodu yerine yazdığı gerçek satır sonu veya "\n" yazısı.
_NEWLINE_LIKE = re.compile(r"\\n|\r?\n")


def repair_codes(source: str, text: str, labels: Sequence[str] = ()) -> str:
    """Modelin yer tutucuyu bozduğu sık durumları onarır (sonuç yine denetlenir).

    - `[1]`, `【1】` gibi benzer yazımlar `⟦1⟧` olur (`placeholders.repair`).
    - Eksik kodların hepsi "satır sonu" ise ve özgünde hiç satır sonu yokken modelin yazdığı satır
      sonu sayısı eksik kod sayısına eşitse, satır sonları sırayla bu kodlara çevrilir.
    """
    text = placeholders.repair(source, text)
    got = set(placeholders.tokens_in(text))
    missing = [n for n in placeholders.tokens_in(source) if n not in got]
    if (
        missing
        and all(0 < n <= len(labels) and is_line_break(labels[n - 1]) for n in missing)
        and not _NEWLINE_LIKE.search(source)
    ):
        breaks = list(_NEWLINE_LIKE.finditer(text))
        if len(breaks) == len(missing):
            for m, n in zip(reversed(breaks), reversed(missing), strict=True):
                text = text[: m.start()] + placeholders.token(n) + text[m.end() :]
    return text


def _clean(unit: _Unit, result: BatchResult | None) -> tuple[str | None, bool]:
    """Modelin sonucunu onarır ve temizler: (metin, temizlik katmanı bir şey değiştirdi mi)."""
    if result is None or result.text is None:
        return None, False
    labels = unit.first.code_labels
    repaired = repair_codes(unit.source, result.text, labels)
    cleaned = clean_output(unit.source, repaired, labels)
    return match_edges(unit.source, cleaned), cleaned != repaired


def _retry_fix(item: BatchItem, issues: list[str]) -> str:
    """Yeniden istekte modele söylenecek sorun: bulunan sorunlar + beklenen kod dizisi."""
    parts = [item.fix, *issues]
    expected = placeholders.tokens_in(item.text)
    if expected:
        parts.append(
            "Çeviride şu kodlar bu sırayla ve her biri bir kez bulunmalı: "
            + " ".join(placeholders.token(n) for n in expected)
            + "."
        )
    return " ".join(x for x in parts if x)


_VERBS = {ACTION_TRANSLATE: "Çevriliyor", ACTION_RETRANSLATE: "Yeniden çevriliyor", ACTION_REVISE: "Düzeltiliyor"}
_DONE = {
    ACTION_TRANSLATE: "Makine çevirisi tamamlandı",
    ACTION_RETRANSLATE: "Yeniden çeviri tamamlandı",
    ACTION_REVISE: "Düzeltme tamamlandı",
}


def run_machine_translation(
    provider: TranslationProvider,
    job: MachineJob,
    ctx: TaskContext,
    on_results: ResultsCallback | None = None,
) -> RunSummary:
    publish = on_results or ctx.publish
    if publish is None:
        raise ValueError("Sonuçları kaydedecek bir geri çağrı gerekli (on_results veya ctx.publish).")
    if job.action not in _VERBS:
        raise ValueError(f"Bilinmeyen iş türü: {job.action}")
    if job.action == ACTION_REVISE and not provider.supports_instructions:
        raise ProviderError(
            f"{provider.label} talimatla düzeltme (redaksiyon) yapamaz.",
            "Redaksiyon için sağlayıcı olarak Ollama'yı seçin.",
        )
    summary = RunSummary(rows=len(job.rows))
    if hasattr(provider, "cancel_token"):
        # İsteğe bağlı kanca (Ollama): iptal istenince süren istek beklenmeden kesilir.
        setattr(provider, "cancel_token", ctx.token)  # noqa: B010 - sözleşmede olmayan isteğe bağlı alan
    status = provider.test_connection()
    if not status.ok:
        raise ProviderError(status.message)

    runner = _Runner(provider, job, ctx)
    units: list[_Unit] = []
    if job.action == ACTION_TRANSLATE:
        by_source: dict[str, list[TranslationRow]] = {}
        for r in job.rows:
            if r.source.strip():
                by_source.setdefault(r.source, []).append(r)
        memory_hits: list[tuple[int, str]] = []
        for i, (source, rows) in enumerate(by_source.items()):
            hit = job.memory.get(source)
            if hit is not None:
                memory_hits += [(r.id, hit[0]) for r in rows]
                runner.latest.update((r.id, hit[0]) for r in rows)
                continue
            units.append(_Unit(str(i), rows))
        if memory_hits:
            publish(memory_hits)
            summary.from_memory = len(memory_hits)
    else:
        units = [_Unit(str(i), [r]) for i, r in enumerate(r for r in job.rows if r.source.strip())]
    summary.unique_sources = len(units)

    verb = _VERBS[job.action]
    done_units = 0
    all_batches = runner.batches(units)
    prepare = getattr(provider, "prepare_job", None)
    if callable(prepare):
        # İsteğe bağlı kanca (Ollama): istek boyutuna göre iş boyunca sabit bağlam penceresi seçilir;
        # istem hiçbir şekilde sığmıyorsa iş başlamadan hata verilir.
        prepare(
            [
                PlannedBatch(
                    [runner.item(u) for u in b],
                    runner.scene(b),
                    relevant_terms(job.glossary, [u.source for u in b]),
                )
                for b in all_batches
            ],
            job.source_lang,
            job.target_lang,
            job.notes,
        )
    for batch in all_batches:
        ctx.report(done_units, len(units), f"{verb}: {len(units) - done_units} metin kaldı")
        scene = runner.scene(batch)
        items = {u.item_id: runner.item(u) for u in batch}
        results = {r.id: r for r in runner.call(list(items.values()), scene)}
        accepted: list[tuple[_Unit, str]] = []
        for unit in batch:
            n = len(unit.rows)
            text, cleaned = _clean(unit, results.get(unit.item_id))
            issues = runner.problems(unit, text)
            doubts = runner.suspicions(unit, text) if not issues else []
            if issues or doubts:
                # Sorunlu veya eksik: sorunu açıkça yazarak tek başına bir kez daha iste.
                summary.retried += 1
                item = items[unit.item_id]
                retry = replace(item, fix=_retry_fix(item, issues + doubts))
                retry_text: str | None = None
                retry_cleaned = False
                try:
                    again = runner.call([retry], scene)
                    retry_text, retry_cleaned = _clean(unit, again[0] if again else None)
                except ProviderError as exc:
                    if not exc.retryable:
                        raise
                    log.info("Tekil yeniden deneme başarısız: %s", exc.message)
                # Yalnızca uydurma şüphesi olan sonuç, kodları bozuk bir yeniden denemeyle değiştirilmez.
                if retry_text is not None and (issues or not runner.problems(unit, retry_text)):
                    text, cleaned = retry_text, retry_cleaned
                issues = runner.problems(unit, text)
                doubts = runner.suspicions(unit, text) if not issues else []
            if text is None:
                summary.missing += n
                continue
            if issues:
                if runner.keeps_old(unit):
                    summary.rejected += n
                    if len(summary.rejections) < MAX_REJECTION_SAMPLES:
                        first = unit.first
                        summary.rejections.append(Rejection(first.context or first.key, text, tuple(issues)))
                    continue
                summary.broken += n
            elif (
                job.action != ACTION_TRANSLATE and text == unit.first.translation and unit.first.status != Status.ERROR
            ):
                summary.unchanged += n
                continue
            else:
                summary.translated += n
                if doubts:
                    summary.suspicious += n
            if cleaned:
                summary.cleaned += n
            accepted.append((unit, text))
        out = [(r.id, text) for unit, text in accepted for r in unit.rows]
        if out:
            publish(out)
            runner.latest.update(out)
        done_units += len(batch)
    ctx.report(len(units), len(units), _DONE[job.action])
    summary.warnings = list(getattr(provider, "warnings", []))
    return summary
