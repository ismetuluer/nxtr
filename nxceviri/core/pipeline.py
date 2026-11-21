"""Ana akışın arayüzden bağımsız adımları: kaynak ekleme, doğrulama, tarama, çıkarma.

Arayüz yalnızca bu fonksiyonları arka plan iş parçacığında çağırır. Paketler her
işlemde açılır ve işlem bitince kapatılır; böylece kullanıcının dosyaları gereğinden
uzun süre kilitli kalmaz.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Collection, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

from nxceviri.core.archives import nested
from nxceviri.core.archives.access import MemberReader, is_member_path
from nxceviri.core.container.package import KIND_BASE, KIND_LABELS, KIND_UPDATE, GamePackage, open_package
from nxceviri.core.container.view import ContentTree, GameView, LayeredRomFs, build_game_view, extract_tree
from nxceviri.core.errors import ContainerError, NxError
from nxceviri.core.formats.base import SOURCE_LANGUAGE, SOURCE_PATH, FormatPlugin
from nxceviri.core.formats.registry import (
    all_plugins,
    archive_formats,
    kind_label,
    member_reader,
    plugin_for_kind,
    supported_kinds,
)
from nxceviri.core.formats.scanner import (
    DETAIL_LANGUAGES,
    NESTED_SEPARATOR,
    ScanEntry,
    ScanReport,
    detail_languages,
    scan_view,
)
from nxceviri.core.keys import KeySet
from nxceviri.core.languages import same_language
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, SourceRecord

SUPPORTED_SUFFIXES = (".nsp", ".nsz")


def is_supported_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def read_source(path: Path, keys: KeySet, title_keys: Mapping[bytes, bytes] | None = None) -> SourceRecord:
    """Paketin meta verilerini okur ve kapatır."""
    if not is_supported_file(path):
        raise ContainerError(
            f"Desteklenmeyen dosya türü: {path.name}",
            "Yalnızca .nsp ve .nsz dosyaları eklenebilir.",
        )
    with open_package(path, keys, title_keys) as pkg:
        return SourceRecord(
            path=path,
            kind=pkg.kind,
            title_id=pkg.title_id,
            application_id=pkg.application_id,
            version=pkg.version,
            display_version=pkg.nacp.display_version if pkg.nacp else "",
            name=pkg.display_name,
            file_size=path.stat().st_size,
            publisher=pkg.nacp.publisher if pkg.nacp else "",
            icon=pkg.icon,
        )


def check_sources(sources: list[SourceRecord]) -> list[str]:
    """Taramayı engelleyen sorunları Türkçe olarak döndürür (boş liste = sorun yok)."""
    problems: list[str] = []
    if not sources:
        return ["Henüz oyun dosyası eklenmedi."]
    bases = [s for s in sources if s.kind == KIND_BASE]
    updates = [s for s in sources if s.kind == KIND_UPDATE]
    if len(bases) > 1:
        problems.append("Birden fazla ana oyun dosyası var; yalnızca birini bırakın.")
    if updates and not bases:
        problems.append("Güncelleme tek başına taranamaz; ait olduğu ana oyunu da ekleyin.")
    app_ids = {s.application_id for s in sources}
    if len(app_ids) > 1:
        problems.append("Eklenen dosyalar farklı oyunlara ait; aynı oyunun dosyalarını ekleyin.")
    missing = [s.path.name for s in sources if not s.path.is_file()]
    if missing:
        problems.append("Şu dosyalar artık bulunamıyor: " + ", ".join(missing))
    return problems


def source_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


@dataclass(frozen=True)
class Inputs:
    """Bir tarama/çıkarma işleminin girdileri."""

    paths: tuple[Path, ...]
    keys: KeySet
    title_keys: Mapping[bytes, bytes] | None = None
    cache_dir: Path | None = None


@contextmanager
def opened_view(inputs: Inputs, ctx: TaskContext) -> Iterator[GameView]:
    with ExitStack() as stack:
        packages: list[GamePackage] = []
        for i, path in enumerate(inputs.paths):
            ctx.report(i, len(inputs.paths), f"Açılıyor: {path.name}")
            packages.append(stack.enter_context(open_package(path, inputs.keys, inputs.title_keys, inputs.cache_dir)))
        yield build_game_view(packages, ctx)


def _annotate_content_languages(view: GameView, report: ScanReport, ctx: TaskContext) -> None:
    """Eklentisi `languages` kancası bildiren dosyaları okuyup dil kodlarını kayıt ayrıntısına ekler.

    Yalnızca kancayı uygulayan eklentilerin dosyaları okunur; diğer eklentilerde hiçbir şey değişmez. Bozuk bir dosya
    taramayı durdurmaz, uyarı olarak raporlanır.
    """
    trees = {t.title_id: t for t in view.trees}
    readers: dict[str, MemberReader] = {}
    cache: dict[tuple[str, ...], bytes] = {}
    importable = set(importable_entries(report))
    for i, entry in enumerate(report.entries):
        plugin = plugin_for_kind(entry.kind, entry.title_id)
        hook = getattr(plugin, "languages", None) if plugin is not None else None
        tree = trees.get(entry.title_id)
        if plugin is None or hook is None or tree is None or entry not in importable:
            continue
        if plugin.path_suffixes and not entry.path.lower().endswith(plugin.path_suffixes):
            continue
        ctx.report(i, len(report.entries), f"Diller okunuyor: {entry.path}")
        try:
            data = _read(readers, cache, tree, entry.path)
            codes = [str(c) for c in hook(data)] if plugin.detect(entry.path, data[:64]) else []
        except NxError as exc:
            report.warnings.append(f"{entry.path}: {exc.message}")
            continue
        if codes:
            report.entries[i] = replace(entry, detail=f"{entry.detail}{DETAIL_LANGUAGES}{', '.join(codes)}")


def scan_sources(inputs: Inputs, ctx: TaskContext) -> ScanReport:
    with opened_view(inputs, ctx) as view:
        report = scan_view(view, ctx)
        _annotate_content_languages(view, report, ctx)
        return report


def extract_sources(inputs: Inputs, dest: Path, only: set[str] | None, ctx: TaskContext) -> int:
    """Birleşik görünümü `dest/<TitleID>/` altına çıkarır.

    `only` verilirse yalnızca bu yollar (iç arşiv yolu verilmişse dıştaki dosya) çıkarılır.
    """
    selected = {p.split(NESTED_SEPARATOR, 1)[0] for p in only} if only is not None else None

    def predicate(path: str) -> bool:
        return selected is None or path in selected

    written = 0
    with opened_view(inputs, ctx) as view:
        for tree in view.trees:
            if any(predicate(p) for p in tree.view.files):
                written += extract_tree(tree, dest / tree.title_id, ctx, predicate)
    return written


@dataclass
class TextExtraction:
    files: list[ImportedFile]
    warnings: list[str]
    #: Kaynak dil dışında kaldığı için atlanan dosya sayısı, dile göre.
    skipped_languages: dict[str, int] = field(default_factory=dict)


#: Unity Localization'ın varsayılan adlandırması: "...-english(en)_assets_all.bundle".
_LANG_IN_NAME = re.compile(r"\(([a-z]{2,3}(?:-[a-z]{2,4})?)\)", re.IGNORECASE)
#: Bölge+dil klasörleri: "USen", "EUfr", "JPja", "CNzh"…
_REGION_LANG_DIR = re.compile(r"^(US|EU|JP|KR|CN|TW|AU)(en|fr|de|es|it|nl|pt|ru|ja|ko|zh)$")
#: GFMSG: "bin/message/English/common/…" (klasör adı dilin İngilizce adı).
_NAMED_LANG_DIRS = {
    "english": "en",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "spanish": "es",
    "korean": "ko",
    "jpn": "ja",
    "jpn_kanji": "ja-jpan",
    "simp_chinese": "zh-hans",
    "trad_chinese": "zh-hant",
}
#: Unreal: ".../Localization/<hedef>/<dil>/<hedef>.locres"
_UNREAL_LANG_DIR = re.compile(r"(?:^|/)Localization/[^/>]+/([A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,4})?)/[^/>]+$")
#: Biçime özgü dil işaretleri: NNI arşiv üyeleri "LOC/EN/…" ve arayüz dosyaları
#: "loc/strings/english.xml"; CPK dil arşivleri "<ad>_US.CPK>…".
_NNI_LOC_DIR = re.compile(r">LOC/([A-Z]{2})/", re.IGNORECASE)
_NNI_LOC_CODES = {"en": "en", "fr": "fr", "de": "de", "ge": "de", "it": "it", "es": "es", "sp": "es", "jp": "ja"}
_NNI_STRINGS_FILE = re.compile(r"(?:^|/)loc/strings/([a-z-]+)\.xml$", re.IGNORECASE)
_NNI_STRINGS_CODES = {
    "english": "en",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "spanish": "es",
    "japanese": "ja",
    "korean": "ko",
    "chinese-ch": "zh-hans",
    "chinese-tw": "zh-hant",
}
#: Altyazı dosyaları: `yso_pro_en.srt` (NNI biçimli oyun: de, en, fr, it, sp, ko, zh-hans, zh-hant).
_SRT_LANG = re.compile(r"_([a-z]{2}(?:-[a-z]{4})?)\.srt$", re.IGNORECASE)
_SRT_LANG_CODES = {"sp": "es"}
_CPK_LANG_SUFFIX = re.compile(r"_(US|DE|ES|FR|IT|JP)\.cpk>", re.IGNORECASE)
_CPK_LANG_CODES = {"us": "en", "de": "de", "es": "es", "fr": "fr", "it": "it", "jp": "ja"}
#: WAD: "dr1_data.wad>Dr1/data/us/script/…" (`ch` klasörü geleneksel Çincedir).
_WAD_LANG_DIR = re.compile(r">Dr\d+/data/(us|jp|ch)/", re.IGNORECASE)
_WAD_LANG_CODES = {"us": "en", "jp": "ja", "ch": "zh-hant"}

LANGUAGE_NAMES = {
    "en": "İngilizce",
    "fr": "Fransızca",
    "de": "Almanca",
    "es": "İspanyolca",
    "es-mx": "İspanyolca (Meksika)",
    "it": "İtalyanca",
    "pt": "Portekizce",
    "pt-br": "Portekizce (Brezilya)",
    "ru": "Rusça",
    "ja": "Japonca",
    "ko": "Korece",
    "zh": "Çince (Basitleştirilmiş)",
    "zh-hans": "Çince (Basitleştirilmiş)",
    "zh-hant": "Çince (Geleneksel)",
    "pl": "Lehçe",
    "nl": "Felemenkçe",
    "tr": "Türkçe",
}

REGION_NAMES = {
    "us": "ABD",
    "eu": "Avrupa",
    "gb": "Birleşik Krallık",
    "jp": "Japonya",
    "kr": "Kore",
    "cn": "Çin",
    "tw": "Tayvan",
    "au": "Avustralya",
    "br": "Brezilya",
    "mx": "Meksika",
    "419": "Latin Amerika",
    "jpan": "Kanji",
}


def language_label(code: str) -> str:
    lower = code.lower()
    name = LANGUAGE_NAMES.get(lower)
    if name is None:
        base, _, region = lower.partition("-")
        if base in LANGUAGE_NAMES and region:
            name = f"{LANGUAGE_NAMES[base]} ({REGION_NAMES.get(region, region.upper())})"
    return f"{name or code} ({code})"


def path_language(path: str) -> str | None:
    """Dosyanın yolundan anlaşılan dil kodu; yoksa None.

    Unity adlandırması "(en)", LMS klasörü "USen" → "en-us", GFMSG klasörü
    "English" → "en", Unreal klasörü "Localization/Game/pt-BR/" → "pt-br"; NNI "LOC/GE/" → "de",
    "loc/strings/english.xml" → "en"; CPK "<ad>_US.CPK" → "en"; WAD
    "dr1_data.wad>Dr1/data/us/" → "en".
    """
    special = _NNI_LOC_DIR.search(path)
    if special and special.group(1).lower() in _NNI_LOC_CODES:
        return _NNI_LOC_CODES[special.group(1).lower()]
    special = _NNI_STRINGS_FILE.search(path)
    if special and special.group(1).lower() in _NNI_STRINGS_CODES:
        return _NNI_STRINGS_CODES[special.group(1).lower()]
    special = _SRT_LANG.search(path)
    if special:
        code = special.group(1).lower()
        return _SRT_LANG_CODES.get(code, code)
    special = _CPK_LANG_SUFFIX.search(path)
    if special:
        return _CPK_LANG_CODES[special.group(1).lower()]
    special = _WAD_LANG_DIR.search(path)
    if special:
        return _WAD_LANG_CODES[special.group(1).lower()]
    inner = path.rsplit(">", 1)[-1]
    m = _LANG_IN_NAME.search(inner.rsplit("/", 1)[-1])
    if m:
        return m.group(1).lower()
    for part in inner.split("/")[:-1]:
        n = _REGION_LANG_DIR.match(part)
        if n:
            return f"{n.group(2)}-{n.group(1)}".lower()
        named = _NAMED_LANG_DIRS.get(part.lower())
        if named:
            return named
    u = _UNREAL_LANG_DIR.search(inner)
    return u.group(1).lower() if u else None


def file_language(plugin: FormatPlugin | None, path: str) -> str | None:
    """Dosyanın yolundan anlaşılan dil: önce eklentinin `path_language(path)` bildirimi (oyuna özgü adlandırma,
    ör. `…_text_de.cfg.bin`), yoksa ya da None dönerse genel kurallar (`path_language`)."""
    hook = getattr(plugin, "path_language", None)
    code = hook(path) if hook is not None else None
    return str(code).lower() if code else path_language(path)


def unsupported_text_kinds(report: ScanReport) -> list[str]:
    """Raporda metin adayı olan ama henüz eklentisi olmayan türlerin Türkçe adları."""
    supported = supported_kinds()
    kinds = {e.kind for e in report.text_candidates if e.kind not in supported}
    return sorted(kind_label(k) for k in kinds)


def importable_entries(report: ScanReport) -> list[ScanEntry]:
    """Aktarma sırasında açılacak dosyalar (eklentisi olan ve gerekiyorsa metin adayı olanlar)."""
    out = []
    for e in report.entries:
        plugin = plugin_for_kind(e.kind, e.title_id)
        if plugin is not None and (not plugin.candidates_only or e.is_text_candidate):
            out.append(e)
    return sorted(out, key=lambda e: (e.title_id, e.path))


def available_languages(report: ScanReport) -> list[str]:
    """Aktarılabilecek dosyaların yolunda ve (eklenti bildiriyorsa) içinde görülen dil kodları (ör. ["en", "ja"])."""
    entries = importable_entries(report)
    codes = {file_language(plugin_for_kind(e.kind, e.title_id), e.path) for e in entries}
    codes.update(code.lower() for e in entries for code in detail_languages(e.detail))
    codes.discard(None)
    return sorted(c for c in codes if c is not None)


def default_source_language(languages: list[str]) -> str | None:
    if not languages:
        return None
    english = [code for code in languages if same_language(code, "en")]
    if not english:
        return languages[0]
    for preferred in ("en", "en-us"):
        if preferred in english:
            return preferred
    return english[0]


def extract_texts(
    inputs: Inputs,
    report: ScanReport,
    ctx: TaskContext,
    source_language: str | None = None,
    only_paths: Collection[str] | None = None,
) -> TextExtraction:
    """Tarama raporundaki desteklenen metin dosyalarını açıp girdilerini çıkarır.

    `source_language` verilirse, dili bilinen ve bu dilden farklı olan dosyalar atlanır
    (aynı metnin diğer dillerdeki kopyaları). `only_paths` verilirse yalnızca bu yollardaki dosyalar
    açılır (kullanıcının tarama sayfasında işaretledikleri); None, desteklenen tüm dosyalar demektir.
    Dil atlama kuralı seçilen dosyalara da uygulanır. Bozuk bir dosya tüm işlemi durdurmaz;
    uyarı olarak raporlanır. İki geçiş yapılır: önce eklentilerin ihtiyaç duyduğu bağlam
    (ör. Unity anahtar adları) toplanır, sonra metinler çıkarılır.
    """
    targets = importable_entries(report)
    if only_paths is not None:
        chosen = frozenset(only_paths)
        targets = [e for e in targets if e.path in chosen]
        if not targets:
            raise ContainerError(
                "Aktarılacak dosya seçilmedi.",
                "Metin dosyaları tablosunda aktarmak istediğiniz dosyaları işaretleyip yeniden deneyin.",
            )
    if not targets:
        others = unsupported_text_kinds(report)
        raise ContainerError(
            "Bu oyunda henüz desteklenen bir metin biçimi bulunamadı.",
            "Şu an desteklenen biçimler: "
            + ", ".join(p.label for p in all_plugins())
            + "."
            + (f" Bu oyunda bulunan metin türleri: {', '.join(others)}." if others else ""),
        )
    files: list[ImportedFile] = []
    warnings: list[str] = []
    skipped: dict[str, int] = {}
    cache: dict[tuple[str, ...], bytes] = {}
    contexts: dict[str, dict[object, object]] = {}
    readers: dict[str, MemberReader] = {}
    steps = 2 * len(targets)
    with opened_view(inputs, ctx) as view:
        trees = {t.title_id: t for t in view.trees}
        readable: list[tuple[ScanEntry, FormatPlugin]] = []
        for i, entry in enumerate(targets):
            ctx.report(i, steps, f"Hazırlanıyor: {entry.path}")
            plugin = plugin_for_kind(entry.kind, entry.title_id)
            tree = trees.get(entry.title_id)
            if plugin is None or tree is None:
                warnings.append(f"{entry.path}: dosya artık oyunda bulunamadı; yeniden tarayın.")
                continue
            if plugin.path_suffixes and not entry.path.lower().endswith(plugin.path_suffixes):
                continue
            try:
                data = _read(readers, cache, tree, entry.path)
                if not plugin.detect(entry.path, data[:64]):
                    continue
                contexts.setdefault(plugin.name, {}).update(plugin.collect_context(data, entry.path))
            except NxError as exc:
                warnings.append(f"{entry.path}: {exc.message}")
                continue
            readable.append((entry, plugin))
        for i, (entry, plugin) in enumerate(readable):
            ctx.report(len(targets) + i, steps, entry.path)
            tree = trees[entry.title_id]
            try:
                data = _read(readers, cache, tree, entry.path)
                lang = plugin.language(data) or file_language(plugin, entry.path)
                if source_language and lang and not same_language(lang, source_language):
                    skipped[lang] = skipped.get(lang, 0) + 1
                    continue
                plugin_context = {
                    **contexts.get(plugin.name, {}),
                    SOURCE_LANGUAGE: source_language,
                    SOURCE_PATH: entry.path,
                }
                extracted = plugin.extract(data, plugin_context)
            except NxError as exc:
                warnings.append(f"{entry.path}: {exc.message}")
                continue
            if extracted:
                files.append(ImportedFile(entry.path, entry.title_id, plugin.name, entry.origin, tuple(extracted)))
    if not files:
        raise _nothing_extracted(report, len(readable), warnings, skipped, source_language)
    ctx.report(steps, steps, "Metinler çıkarıldı")
    return TextExtraction(files, warnings, skipped)


def _nothing_extracted(
    report: ScanReport, opened: int, warnings: list[str], skipped: dict[str, int], source_language: str | None
) -> ContainerError:
    """Hiç metin çıkmadığında "0 satır aktarıldı" başarısı yerine verilen açıklama."""
    if skipped and source_language:
        found = ", ".join(language_label(code) for code in sorted(skipped))
        return ContainerError(
            f"Seçilen kaynak dilde ({language_label(source_language)}) metin bulunamadı.",
            f"Oyundaki metin dosyalarının dili: {found}. Kaynak dili bunlardan biri olarak seçip yeniden deneyin.",
        )
    hint = (
        f"{opened:,} dosya açıldı ama hiçbirinde tanınan bir metin tablosu yoktu "
        f"(tahmin edilen motor: {report.engine.label}). Oyun metinlerini kendine özgü bir biçimde "
        "saklıyor olabilir; bu biçim için destek eklenmesi gerekir."
    )
    if warnings:
        hint += " Açılamayan dosyalar: " + "; ".join(warnings[:3])
        if len(warnings) > 3:
            hint += f" … ve {len(warnings) - 3:,} dosya daha."
    return ContainerError("Bu oyunda desteklenen biçimde çevrilebilir metin bulunamadı.", hint)


def _read(readers: dict[str, MemberReader], cache: dict[tuple[str, ...], bytes], tree: ContentTree, path: str) -> bytes:
    """Pak ve PSB arşivi içindekileri dizinden, diğerlerini (kardeşleri için ara katmanları saklayarak) okur."""
    if is_member_path(path, archive_formats(tree.title_id)):
        reader = readers.get(tree.title_id)
        if reader is None:
            reader = readers[tree.title_id] = member_reader(tree)
        return reader.read(path)
    return _open_cached(cache, tree.title_id, nested.split(path), tree.view)


def _open_cached(cache: dict[tuple[str, ...], bytes], title_id: str, parts: list[str], romfs: LayeredRomFs) -> bytes:
    """İç içe yolu açar; aynı arşivdeki kardeş dosyalar için açılmış ara katmanları saklar."""
    top_key = (title_id, parts[0])
    if top_key not in cache:
        # Yeni bir dış dosyaya geçildi: önceki arşivin ara katmanlarını bellekten at.
        cache.clear()
        cache[top_key] = romfs.open(parts[0]).read_all()
    data = cache[top_key]
    for depth in range(1, len(parts)):
        key = (title_id, *parts[: depth + 1])
        if key not in cache:
            cache[key] = nested.open_inner(data, [parts[depth]])
        data = cache[key]
    return data


def default_cache_dir() -> Path:
    """Kaydedilmemiş projeler için kullanıcıya özel önbellek klasörü."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NXCeviri" / "onbellek"


def dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue  # silinmekte olan dosya; boyuta katmayız
    return total


def clear_cache(path: Path) -> None:
    """Önbellek klasörünü siler. Yalnızca önbellek adını taşıyan klasörlere izin verilir."""
    if not path.exists():
        return
    if not path.name.endswith("onbellek"):
        raise ContainerError(f"Geçici dosyalar klasörü beklenmeyen bir yerde: {path}", "Güvenlik için silinmedi.")
    try:
        shutil.rmtree(path)
    except OSError as exc:
        raise ContainerError(
            f"Geçici dosyalar silinemedi: {path}",
            f"Dosyalar başka bir programda açık olabilir. ({exc.strerror})",
        ) from None


def version_warnings(sources: list[SourceRecord], report: ScanReport | None) -> list[str]:
    """Metinlerin aktarıldığı sürümle şu anki oyun dosyalarının sürümü uyuşmuyorsa uyarılar."""
    if report is None:
        return ["Bu projede tarama sonucu yok; metinlerin hangi sürümden aktarıldığı bilinmiyor."]
    warnings = []
    updates = [s for s in sources if s.kind == KIND_UPDATE]
    current = max((s.version for s in updates), default=None)
    if report.update_version != current:
        was = f"v{report.update_version}" if report.update_version is not None else "güncellemesiz"
        now = f"v{current}" if current is not None else "güncellemesiz"
        warnings.append(
            f"Metinler {was} sürümden aktarıldı ama şu an eklenen dosyalar {now}. Mod bu sürüme göre "
            "üretilecek; oyunda hangi sürümü kullanıyorsanız onunla aynı olmalı. Emin değilseniz yeniden "
            "tarayıp metinleri aktarın."
        )
    return warnings
