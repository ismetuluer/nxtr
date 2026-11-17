"""Format tarama: birleşik oyun görünümündeki dosyaları sınıflandırır, motoru tahmin eder.

İç içe arşivlerin (SARC, Yaz0, ZSTD) içine de bakılır; bu aşamada yalnızca okunur.
İç dosyaların yolu "dış/yol.szs>iç/yol.msbt" biçimindedir. Eklenti arşivlerinde (`archive_formats()` kancası) yalnızca
kullanıcı eklentilerinin tanıdığı üyeler listelenir; üye adı bir eklentinin `path_suffixes`'ine uymuyorsa (ya da
eklentinin uzantı süzgeci yoksa) okunmaz.
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
    NNI_ARCHIVE_DETAIL,
    PSB_ARCHIVE_DETAIL,
    WAD_ARCHIVE_DETAIL,
    Detection,
    FileKind,
    TextLikelihood,
    detect,
)
from nxceviri.core.formats.psbtext import is_text_member
from nxceviri.core.formats.registry import member_reader, user_plugin_for_file, user_plugins_for
from nxceviri.core.progress import TaskContext

#: İç arşivleri açarken izin verilen en büyük boyutlar (bellek koruması).
MAX_NESTED_INPUT = 64 * 1024 * 1024
MAX_NESTED_OUTPUT = 256 * 1024 * 1024
MAX_DEPTH = 4
NESTED_SEPARATOR = ">"
#: PSB arşivinde metin aranan üyelerin en büyük boyutu ve atlanan klasörler (yazı tipi, hareket, görsel).
MAX_PSB_ARCHIVE_MEMBER = 4 * 1024 * 1024
_PSB_ARCHIVE_SKIPPED_DIRS = ("font/", "motion/", "image/", "texture/", "sound/", "roms/", "patch/")
#: WAD arşivindeki betikler ve metin tabloları: `Dr1/data/<dil>/script/*.lin|*.pak`.
_WAD_SCRIPT = re.compile(r"(?:^|/)script/[^/]+\.(?:lin|pak)$", re.IGNORECASE)
#: Dizini okunan büyük arşivlerde metin üyeleri: (tespit ayrıntısı) → (üye seçici, tür, açıklama).
#: NNI: yerelleştirilmiş betikler `LOC/<DİL>/…/*.XSO`; CPK: `MsgSheet/*.fms`.
_MEMBER_TEXT: dict[str, tuple[Callable[[str], bool], FileKind, str]] = {
    NNI_ARCHIVE_DETAIL: (
        lambda m: m.upper().startswith("LOC/") and m.upper().endswith(".XSO"),
        FileKind.NNITEXT,
        "XSO betik metni",
    ),
    CPK_ARCHIVE_DETAIL: (lambda m: m.lower().endswith(".fms"), FileKind.FMSB, "FMSB MsgSheet"),
    WAD_ARCHIVE_DETAIL: (
        lambda m: _WAD_SCRIPT.search(m) is not None,
        FileKind.WADLIN,
        "LIN betiği / PAK metin tablosu",
    ),
}


#: Dosyanın içindeki dillerin (eklentinin `languages` kancası) tarama kaydındaki `detail` ekinde yazıldığı biçim.
#: Ek `detail` ile birlikte projeye kaydedildiği için proje yeniden açılınca dil listesi kaybolmaz.
DETAIL_LANGUAGES = " · Diller: "


def detail_languages(detail: str) -> list[str]:
    """`detail` ekine yazılmış dosya içi dil kodları; yoksa boş."""
    _, mark, tail = detail.partition(DETAIL_LANGUAGES)
    return [c for c in (p.strip() for p in tail.split(",")) if c] if mark else []


def base_detail(detail: str) -> str:
    """`detail`'in dil eki olmadan hâli (türü tanımak için karşılaştırılan metin)."""
    return detail.partition(DETAIL_LANGUAGES)[0]


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
    engine: str  # ENGINE_LABELS anahtarı: "unity", "unreal", "lms", "psb", "nni", "cpk", "wad", "unknown"…
    label: str
    confidence: str  # "high", "medium", "low", "none"
    evidence: tuple[str, ...]


ENGINE_LABELS = {
    "unity": "Unity",
    "unreal": "Unreal Engine",
    "psb": "PSB arşivi (mdf)",
    "nni": "NNI arşivi",
    "cpk": "CPK arşivi (FMSB)",
    "wad": "WAD arşivi (LIN/PAK)",
    "lms": "LMS (MSBT)",
    "gfmsg": "GFMSG mesajları",
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
        warnings.append(f"{path}: {len(pak.entries):,} dosya içeren pak'ta olası metin dosyası bulunamadı.")


def _scan_psb_archive(
    tree: ContentTree, path: str, origin: str, *, out: list[ScanEntry], warnings: list[str], ctx: TaskContext
) -> None:
    """PSB arşivinin (mdf kodlu PSB dizini) üyelerini tarar; yalnızca çevrilebilir metin içerenleri listeler."""
    try:
        archive = member_reader(tree).psb_archive(path)
    except NxError as exc:
        warnings.append(f"{path}: {exc.message}")
        return
    members = [
        m
        for m, e in archive.entries.items()
        if m.lower().endswith(".psb.m")
        and e.size <= MAX_PSB_ARCHIVE_MEMBER
        and not any(d in m for d in _PSB_ARCHIVE_SKIPPED_DIRS)
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
                    FileKind.PSBTEXT.value,
                    "PSB metni",
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
    reader = member_reader(tree)
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


def _scan_plugin_archive(
    tree: ContentTree,
    reader: MemberReader,
    path: str,
    origin: str,
    *,
    out: list[ScanEntry],
    warnings: list[str],
    ctx: TaskContext,
) -> None:
    """Eklenti arşivinin üyelerinden kullanıcı eklentilerinin tanıdıklarını rapora ekler."""
    plugins = user_plugins_for(tree.title_id)
    try:
        members = reader.plugin_archive(path).members()
    except NxError as exc:
        warnings.append(f"{path}: {exc.message}")
        return
    wanted = sorted(
        m for m in members if any(not p.path_suffixes or m.lower().endswith(p.path_suffixes) for p in plugins)
    )
    found = 0
    for i, member in enumerate(wanted):
        ctx.report(i, len(wanted), f"{path}: {member}")
        try:
            data = reader.read(f"{path}{NESTED_SEPARATOR}{member}")
        except NxError as exc:
            warnings.append(f"{path}{NESTED_SEPARATOR}{member}: {exc.message}")
            continue
        claimed = user_plugin_for_file(tree.title_id, member, data[:HEAD_SIZE])
        if claimed is not None:
            found += 1
            out.append(
                ScanEntry(
                    tree.title_id,
                    f"{path}{NESTED_SEPARATOR}{member}",
                    len(data),
                    claimed.name,
                    claimed.label,
                    TextLikelihood.HIGH.value,
                    origin,
                )
            )
    if not found:
        warnings.append(f"{path}: arşivde eklentilerin tanıdığı metin dosyası bulunamadı.")


def scan_view(view: GameView, ctx: TaskContext | None = None) -> ScanReport:
    ctx = ctx or TaskContext()
    started = time.monotonic()
    entries: list[ScanEntry] = []
    warnings = list(view.warnings)
    total = view.file_count
    done = 0
    for tree in view.trees:
        reader = member_reader(tree)
        for vf in tree.view.files.values():
            ctx.report(done, total, vf.path)
            done += 1
            archive = reader.plugin_format(vf.path)
            if archive is not None:
                # Eklentinin arşiv biçimi yerleşik tespitten önce gelir (eklenti metin biçimleri gibi).
                entries.append(
                    ScanEntry(
                        tree.title_id,
                        vf.path,
                        vf.size,
                        FileKind.ARCHIVE.value,
                        archive.label,
                        TextLikelihood.NONE.value,
                        vf.origin,
                    )
                )
                _scan_plugin_archive(tree, reader, vf.path, vf.origin, out=entries, warnings=warnings, ctx=ctx)
                continue
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
            if det.detail == PSB_ARCHIVE_DETAIL:
                entries.append(
                    ScanEntry(
                        tree.title_id, vf.path, vf.size, det.kind.value, det.detail, det.likelihood.value, vf.origin
                    )
                )
                _scan_psb_archive(tree, vf.path, vf.origin, out=entries, warnings=warnings, ctx=ctx)
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
    ("unity", "IL2CPP meta verisi", _count(lambda e: base_detail(e.detail) == "Unity IL2CPP meta verisi")),
    ("unity", "Unity AssetBundle dosyaları", _count(lambda e: base_detail(e.detail) == "Unity AssetBundle")),
    (
        "unity",
        "Unity serileştirilmiş dosyaları",
        _count(lambda e: base_detail(e.detail) == "Unity serileştirilmiş dosya"),
    ),
    ("unity", "Unity Managed klasörü", _count(lambda e: "/Managed/" in e.path or e.path.startswith("Managed/"))),
    (
        "unreal",
        "Unreal .pak / IoStore arşivleri",
        _count(lambda e: e.detail.startswith(("Unreal .pak", "Unreal IoStore"))),
    ),
    ("unreal", "Unreal yerelleştirme dosyaları", _count(lambda e: e.detail.startswith("Unreal yerelleştirme"))),
    ("unreal", "Unreal varlıkları (.uasset)", _count(lambda e: e.detail.startswith("Unreal varlığı"))),
    ("unreal", "Unreal Content/Paks klasörü", _count(lambda e: "/Content/Paks/" in e.path)),
    ("psb", "PSB arşivleri (mdf)", _count(lambda e: e.detail == PSB_ARCHIVE_DETAIL)),
    ("psb", "PSB metin dosyaları", _count(lambda e: e.kind == FileKind.PSBTEXT)),
    ("nni", "NNI arşivleri", _count(lambda e: e.detail == NNI_ARCHIVE_DETAIL)),
    ("nni", "NNI betik/arayüz metinleri", _count(lambda e: e.kind == FileKind.NNITEXT)),
    ("cpk", "CPK arşivleri", _count(lambda e: e.detail == CPK_ARCHIVE_DETAIL)),
    ("cpk", "FMSB MsgSheet dosyaları", _count(lambda e: e.kind == FileKind.FMSB)),
    ("wad", "WAD arşivleri", _count(lambda e: e.detail == WAD_ARCHIVE_DETAIL)),
    ("wad", "LIN/PAK betik ve metin tabloları", _count(lambda e: e.kind == FileKind.WADLIN)),
    ("lms", "MSBT metin dosyaları", _count(lambda e: e.kind == FileKind.MSBT)),
    ("gfmsg", "GFMSG mesaj dosyaları", _count(lambda e: e.detail == "GFMSG mesaj dosyası")),
    ("gfmsg", "AHTB etiket tabloları", _count(lambda e: e.detail.startswith("AHTB etiket"))),
    ("gfmsg", "GFPAK paketleri (.gfpak)", _count(lambda e: e.path.lower().endswith(".gfpak"))),
    ("lms", "LMS proje/akış dosyaları", _count(lambda e: e.detail.startswith(("MSBP", "MSBF")))),
    ("lms", "SARC/Yaz0 arşivleri", _count(lambda e: e.detail.startswith(("SARC", "Yaz0")))),
    (
        "lms",
        "BFRES/BNTX/BFFNT kaynakları",
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
