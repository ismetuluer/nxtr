"""Format tarama: birleşik oyun görünümündeki dosyaları sınıflandırır, motoru tahmin eder.

İç içe arşivlerin (SARC, Yaz0, ZSTD) içine de bakılır; bu aşamada yalnızca okunur.
İç dosyaların yolu "dış/yol.szs>iç/yol.msbt" biçimindedir.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from nxceviri.core.archives import sarc, yaz0, zstd
from nxceviri.core.archives.access import MemberReader
from nxceviri.core.archives.pak import PakFile
from nxceviri.core.container.storage import Storage
from nxceviri.core.container.view import ContentTree, GameView
from nxceviri.core.errors import ArchiveError, NxError
from nxceviri.core.formats.detection import (
    CPK_ARCHIVE_DETAIL,
    HEAD_SIZE,
    M2_ARCHIVE_DETAIL,
    NNI_ARCHIVE_DETAIL,
    WAD_ARCHIVE_DETAIL,
    Detection,
    FileKind,
    TextLikelihood,
    detect,
)
from nxceviri.core.formats.m2text import is_text_member
from nxceviri.core.formats.registry import user_plugin_for_file
from nxceviri.core.progress import TaskContext

#: İç arşivleri açarken izin verilen en büyük boyutlar (bellek koruması).
MAX_NESTED_INPUT = 64 * 1024 * 1024
MAX_NESTED_OUTPUT = 256 * 1024 * 1024
MAX_DEPTH = 4
NESTED_SEPARATOR = ">"
#: M2 arşivinde metin aranan üyelerin en büyük boyutu ve atlanan klasörler (yazı tipi, hareket, görsel).
MAX_M2_MEMBER = 4 * 1024 * 1024
_M2_SKIPPED_DIRS = ("font/", "motion/", "image/", "texture/", "sound/", "roms/", "patch/")
#: Danganronpa: betikler ve metin tabloları `Dr1/data/<dil>/script/*.lin|*.pak` (WAD içinde).
_DR_SCRIPT = re.compile(r"(?:^|/)script/[^/]+\.(?:lin|pak)$", re.IGNORECASE)
#: Dizini okunan büyük arşivlerde metin üyeleri: (tespit ayrıntısı) → (üye seçici, tür, açıklama).
#: Ys Origin: yerelleştirilmiş betikler `LOC/<DİL>/…/*.XSO`; Unicorn Overlord: `MsgSheet/*.fms`.
_MEMBER_TEXT: dict[str, tuple[Callable[[str], bool], FileKind, str]] = {
    NNI_ARCHIVE_DETAIL: (
        lambda m: m.upper().startswith("LOC/") and m.upper().endswith(".XSO"),
        FileKind.YSORIGIN,
        "Ys Origin betik metni (XSO)",
    ),
    CPK_ARCHIVE_DETAIL: (lambda m: m.lower().endswith(".fms"), FileKind.FMSB, "Vanillaware MsgSheet (FMSB)"),
    WAD_ARCHIVE_DETAIL: (
        lambda m: _DR_SCRIPT.search(m) is not None,
        FileKind.DANGANRONPA,
        "Danganronpa betiği / metin tablosu",
    ),
}


@dataclass(frozen=True)
class ScanEntry:
    title_id: str
    path: str
    size: int
    kind: str
    detail: str
    likelihood: str
    origin: str

    @property
    def is_text_candidate(self) -> bool:
        return self.likelihood != TextLikelihood.NONE


@dataclass(frozen=True)
class EngineGuess:
    engine: str  # "unity", "unreal", "nintendo", "gamefreak", "godot", "gamemaker", "renpy", "unknown"
    label: str
    confidence: str  # "high", "medium", "low", "none"
    evidence: tuple[str, ...]


ENGINE_LABELS = {
    "unity": "Unity",
    "unreal": "Unreal Engine",
    "m2": "M2 (Konami Master Collection)",
    "falcom": "Falcom (Ys Origin)",
    "vanillaware": "Vanillaware / CRI (Unicorn Overlord)",
    "spike": "Spike Chunsoft (Danganronpa)",
    "nintendo": "Nintendo LMS / NintendoWare",
    "gamefreak": "Game Freak (Pokémon)",
    "godot": "Godot",
    "gamemaker": "GameMaker",
    "renpy": "Ren'Py",
    "unknown": "Bilinmiyor",
}
CONFIDENCE_LABELS = {"high": "Yüksek", "medium": "Orta", "low": "Düşük", "none": "—"}


@dataclass
class ScanReport:
    game_name: str
    title_id: str
    base_version: int | None
    update_version: int | None
    engine: EngineGuess
    entries: list[ScanEntry]
    warnings: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def counts(self) -> dict[str, int]:
        c = Counter(e.kind for e in self.entries)
        return {k.value: c.get(k.value, 0) for k in FileKind}

    @property
    def text_candidates(self) -> list[ScanEntry]:
        order = {TextLikelihood.HIGH: 0, TextLikelihood.MEDIUM: 1}
        cands = [e for e in self.entries if e.is_text_candidate]
        return sorted(cands, key=lambda e: (order.get(TextLikelihood(e.likelihood), 2), e.path))


def _head_tail(storage: Storage) -> tuple[bytes, bytes]:
    head = storage.read(0, min(HEAD_SIZE, storage.size))
    tail_len = min(0x200, storage.size)
    tail = storage.read(storage.size - tail_len, tail_len) if tail_len else b""
    return head, tail


def _unpack(detection: Detection, data: bytes) -> list[tuple[str, bytes]]:
    """Arşivi bir seviye açar: (iç ad, veri) listesi. Sıkıştırmada tek iç dosya vardır."""
    if detection.detail.startswith("SARC"):
        return [(e.name, e.data) for e in sarc.parse(data)]
    if detection.detail.startswith("Yaz0"):
        return [("", yaz0.decompress(data, MAX_NESTED_OUTPUT))]
    if detection.detail.startswith("ZSTD"):
        return [("", zstd.decompress(data, MAX_NESTED_OUTPUT))]
    return []


def _strip_compression_suffix(path: str) -> str:
    for suffix in (".zs", ".zst", ".szs", ".yaz0"):
        if path.lower().endswith(suffix) and len(path) > len(suffix):
            return path[: -len(suffix)]
    return path


def _scan_nested(
    *,
    title_id: str,
    path: str,
    data: bytes,
    origin: str,
    depth: int,
    out: list[ScanEntry],
    warnings: list[str],
) -> None:
    leaf = path.rsplit(NESTED_SEPARATOR, maxsplit=1)[-1]
    det = detect(leaf, data[:HEAD_SIZE], data[-0x200:])
    claimed = None if det.kind == FileKind.ARCHIVE else user_plugin_for_file(title_id, leaf, data[:HEAD_SIZE])
    if claimed is not None:
        out.append(ScanEntry(title_id, path, len(data), claimed.name, claimed.label, TextLikelihood.HIGH.value, origin))
        return
    out.append(ScanEntry(title_id, path, len(data), det.kind.value, det.detail, det.likelihood.value, origin))
    if det.kind != FileKind.ARCHIVE:
        return
    if depth >= MAX_DEPTH:
        warnings.append(f"{path}: iç içe arşiv derinliği sınırı aşıldı; içine bakılmadı.")
        return
    try:
        children = _unpack(det, data)
    except ArchiveError as exc:
        warnings.append(f"{path}: {exc.message}")
        return
    for name, child in children:
        if name:
            child_path = f"{path}{NESTED_SEPARATOR}{name}"
        else:
            # Sıkıştırılmış tek dosya: ".zs" gibi uzantıyı atarak asıl adı göster.
            base = path.rsplit(NESTED_SEPARATOR, maxsplit=1)[-1].rsplit("/", 1)[-1]
            inner = _strip_compression_suffix(base)
            if inner == base:
                inner += " (açılmış)"
            child_path = f"{path}{NESTED_SEPARATOR}{inner}"
        _scan_nested(
            title_id=title_id, path=child_path, data=child, origin=origin, depth=depth + 1, out=out, warnings=warnings
        )


def _scan_pak(
    title_id: str, path: str, storage: Storage, origin: str, *, out: list[ScanEntry], warnings: list[str]
) -> None:
    """Unreal pak'ının yalnızca dizinini okur; metin adayı olan girdileri rapora ekler."""
    try:
        pak = PakFile(storage, path)
    except NxError as exc:
        warnings.append(f"{path}: {exc.message}")
        return
    listed = 0
    for name, entry in pak.entries.items():
        det = detect(name, b"", b"")
        if det.likelihood == TextLikelihood.NONE:
            continue
        listed += 1
        inner = f"{path}{NESTED_SEPARATOR}{name}"
        out.append(
            ScanEntry(
                title_id, inner, entry.uncompressed_size, det.kind.value, det.detail, det.likelihood.value, origin
            )
        )
    if pak.entries and not listed:
        warnings.append(f"{path}: {len(pak.entries):,} dosya içeren pak'ta metin adayı bulunamadı.")


def _scan_m2(
    tree: ContentTree, path: str, origin: str, *, out: list[ScanEntry], warnings: list[str], ctx: TaskContext
) -> None:
    """M2 arşivinin (mdf kodlu PSB dizini) üyelerini tarar; yalnızca çevrilebilir metin içerenleri listeler."""
    try:
        archive = MemberReader(tree.view, tree.code).m2(path)
    except NxError as exc:
        warnings.append(f"{path}: {exc.message}")
        return
    members = [
        m
        for m, e in archive.entries.items()
        if m.lower().endswith(".psb.m") and e.size <= MAX_M2_MEMBER and not any(d in m for d in _M2_SKIPPED_DIRS)
    ]
    found = 0
    for i, member in enumerate(sorted(members)):
        ctx.report(i, len(members), f"{path}: {member}")
        try:
            data = archive.read(member)
        except NxError as exc:
            warnings.append(f"{path}{NESTED_SEPARATOR}{member}: {exc.message}")
            continue
        if is_text_member(member, data):
            found += 1
            out.append(
                ScanEntry(
                    tree.title_id,
                    f"{path}{NESTED_SEPARATOR}{member}",
                    len(data),
                    FileKind.M2TEXT.value,
                    "M2 PSB metni",
                    TextLikelihood.HIGH.value,
                    origin,
                )
            )
    if not found:
        warnings.append(f"{path}: arşivde çevrilebilir metin içeren dosya bulunamadı.")


def _scan_member_archive(
    tree: ContentTree, path: str, origin: str, detail: str, *, out: list[ScanEntry], warnings: list[str]
) -> None:
    """NNI/CPK/WAD arşivinin yalnızca dizinini okur; metin üyelerini adlarından seçip rapora ekler."""
    wanted, kind, label = _MEMBER_TEXT[detail]
    reader = MemberReader(tree.view, tree.code)
    try:
        if detail == NNI_ARCHIVE_DETAIL:
            sizes = {m: e.size for m, e in reader.nni(path).entries.items()}
        elif detail == WAD_ARCHIVE_DETAIL:
            sizes = {m: e.size for m, e in reader.wad(path).entries.items()}
        else:
            sizes = {m: e.extract_size for m, e in reader.cpk(path).entries.items()}
    except NxError as exc:
        warnings.append(f"{path}: {exc.message}")
        return
    for member, size in sorted(sizes.items()):
        if wanted(member):
            out.append(
                ScanEntry(
                    tree.title_id,
                    f"{path}{NESTED_SEPARATOR}{member}",
                    size,
                    kind.value,
                    label,
                    TextLikelihood.HIGH.value,
                    origin,
                )
            )


def scan_view(view: GameView, ctx: TaskContext | None = None) -> ScanReport:
    ctx = ctx or TaskContext()
    started = time.monotonic()
    entries: list[ScanEntry] = []
    warnings = list(view.warnings)
    total = view.file_count
    done = 0
    for tree in view.trees:
        for vf in tree.view.files.values():
            ctx.report(done, total, vf.path)
            done += 1
            storage = tree.view.open(vf.path)
            head, tail = _head_tail(storage)
            det = detect(vf.path, head, tail)
            claimed = None if det.kind == FileKind.ARCHIVE else user_plugin_for_file(tree.title_id, vf.path, head)
            if claimed is not None:
                # Kullanıcı eklentisi yerleşik tespitten önce gelir (arşivler hariç: onların içine bakılmalı).
                entries.append(
                    ScanEntry(
                        tree.title_id,
                        vf.path,
                        vf.size,
                        claimed.name,
                        claimed.label,
                        TextLikelihood.HIGH.value,
                        vf.origin,
                    )
                )
                continue
            if det.detail == M2_ARCHIVE_DETAIL:
                entries.append(
                    ScanEntry(
                        tree.title_id, vf.path, vf.size, det.kind.value, det.detail, det.likelihood.value, vf.origin
                    )
                )
                _scan_m2(tree, vf.path, vf.origin, out=entries, warnings=warnings, ctx=ctx)
                continue
            if det.detail in _MEMBER_TEXT:
                entries.append(
                    ScanEntry(
                        tree.title_id, vf.path, vf.size, det.kind.value, det.detail, det.likelihood.value, vf.origin
                    )
                )
                _scan_member_archive(tree, vf.path, vf.origin, det.detail, out=entries, warnings=warnings)
                continue
            if det.kind == FileKind.ARCHIVE and vf.size <= MAX_NESTED_INPUT:
                _scan_nested(
                    title_id=tree.title_id,
                    path=vf.path,
                    data=storage.read_all(),
                    origin=vf.origin,
                    depth=0,
                    out=entries,
                    warnings=warnings,
                )
                continue
            if det.kind == FileKind.ARCHIVE:
                warnings.append(f"{vf.path}: arşiv çok büyük ({vf.size:,} bayt); içine bakılmadı.")
            entries.append(
                ScanEntry(tree.title_id, vf.path, vf.size, det.kind.value, det.detail, det.likelihood.value, vf.origin)
            )
            if det.detail.startswith("Unreal .pak"):
                _scan_pak(tree.title_id, vf.path, storage, vf.origin, out=entries, warnings=warnings)
    ctx.report(total, total, "Tarama tamamlandı")
    return ScanReport(
        game_name=view.name,
        title_id=view.title_id,
        base_version=view.base_version,
        update_version=view.update_version,
        engine=guess_engine(entries),
        entries=entries,
        warnings=warnings,
        duration_s=round(time.monotonic() - started, 2),
    )


_Rule = tuple[str, str, Callable[[list[ScanEntry]], int]]


def _count(pred: Callable[[ScanEntry], bool]) -> Callable[[list[ScanEntry]], int]:
    return lambda entries: sum(1 for e in entries if pred(e))


_RULES: tuple[_Rule, ...] = (
    ("unity", "Unity yönetici dosyası (globalgamemanagers)", _count(lambda e: e.path.endswith("globalgamemanagers"))),
    ("unity", "IL2CPP meta verisi", _count(lambda e: e.detail == "Unity IL2CPP meta verisi")),
    ("unity", "Unity AssetBundle dosyaları", _count(lambda e: e.detail == "Unity AssetBundle")),
    ("unity", "Unity serileştirilmiş dosyaları", _count(lambda e: e.detail == "Unity serileştirilmiş dosya")),
    ("unity", "Unity Managed klasörü", _count(lambda e: "/Managed/" in e.path or e.path.startswith("Managed/"))),
    (
        "unreal",
        "Unreal .pak / IoStore arşivleri",
        _count(lambda e: e.detail.startswith(("Unreal .pak", "Unreal IoStore"))),
    ),
    ("unreal", "Unreal yerelleştirme dosyaları", _count(lambda e: e.detail.startswith("Unreal yerelleştirme"))),
    ("unreal", "Unreal varlıkları (.uasset)", _count(lambda e: e.detail.startswith("Unreal varlığı"))),
    ("unreal", "Unreal Content/Paks klasörü", _count(lambda e: "/Content/Paks/" in e.path)),
    ("m2", "M2 arşivleri (mdf)", _count(lambda e: e.detail == M2_ARCHIVE_DETAIL)),
    ("m2", "M2 PSB metin dosyaları", _count(lambda e: e.kind == FileKind.M2TEXT)),
    ("falcom", "Falcom NNI arşivleri", _count(lambda e: e.detail == NNI_ARCHIVE_DETAIL)),
    ("falcom", "Ys Origin betik/arayüz metinleri", _count(lambda e: e.kind == FileKind.YSORIGIN)),
    ("vanillaware", "CRI CPK arşivleri", _count(lambda e: e.detail == CPK_ARCHIVE_DETAIL)),
    ("vanillaware", "Vanillaware MsgSheet dosyaları", _count(lambda e: e.kind == FileKind.FMSB)),
    ("spike", "Spike Chunsoft WAD arşivleri", _count(lambda e: e.detail == WAD_ARCHIVE_DETAIL)),
    ("spike", "Danganronpa betik ve metin tabloları", _count(lambda e: e.kind == FileKind.DANGANRONPA)),
    ("nintendo", "MSBT metin dosyaları", _count(lambda e: e.kind == FileKind.MSBT)),
    ("gamefreak", "Game Freak mesaj dosyaları", _count(lambda e: e.detail == "Game Freak mesaj dosyası")),
    ("gamefreak", "AHTB etiket tabloları", _count(lambda e: e.detail.startswith("Game Freak etiket"))),
    ("gamefreak", "Game Freak paketleri (.gfpak)", _count(lambda e: e.path.lower().endswith(".gfpak"))),
    ("nintendo", "LMS proje/akış dosyaları", _count(lambda e: e.detail.startswith(("MSBP", "MSBF")))),
    ("nintendo", "SARC/Yaz0 arşivleri", _count(lambda e: e.detail.startswith(("SARC", "Yaz0")))),
    (
        "nintendo",
        "NintendoWare kaynakları (BFRES/BNTX/BFFNT)",
        _count(lambda e: e.detail.startswith(("BFRES", "BNTX", "BFFNT"))),
    ),
    ("godot", "Godot paketi", _count(lambda e: e.detail.startswith("Godot"))),
    ("gamemaker", "GameMaker veri dosyası", _count(lambda e: e.path.lower().endswith("data.win"))),
    ("renpy", "Ren'Py arşivi/betikleri", _count(lambda e: e.detail.startswith("Ren'Py") or e.path.endswith(".rpyc"))),
)


def guess_engine(entries: list[ScanEntry]) -> EngineGuess:
    """Kanıt türü sayısına göre motoru tahmin eder (ör. Unity için 5 ayrı kanıt türü var)."""
    evidence: dict[str, list[str]] = {}
    for engine, label, counter in _RULES:
        n = counter(entries)
        if n:
            evidence.setdefault(engine, []).append(f"{label}: {n}")
    if not evidence:
        return EngineGuess("unknown", ENGINE_LABELS["unknown"], "none", ())
    engine = max(evidence, key=lambda k: len(evidence[k]))
    n = len(evidence[engine])
    confidence = "high" if n >= 3 else "medium" if n == 2 else "low"
    return EngineGuess(engine, ENGINE_LABELS[engine], confidence, tuple(evidence[engine]))
