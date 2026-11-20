"""Font glif denetimi: oyunun fontlarında Türkçe harfler var mı? (CLAUDE.md §4.4)

Desteklenen font türleri:

- **TextMeshPro (Unity):** `TMP_FontAsset` MonoBehaviour'larının `m_CharacterTable`'ı. Statik
  atlaslar (`m_AtlasPopulationMode == 0`) yalnızca tablodaki karakterleri çizebilir. Dinamik
  atlaslar (`1`) eksik karakteri kaynak fonttan (`m_SourceFontFile` → Unity `Font` nesnesindeki
  TTF) çalışma anında üretir; bunun için kaynak TTF'in cmap'i okunur.
- **Unity `Font` nesneleri ve RomFS'teki .ttf/.otf dosyaları:** fontTools ile cmap.
- **Switch sistem fontları (`.bfttf` / `.bfotf`, çoğunlukla `.zs`):** `fontpatch.switchfont` kapsayıcıyı (zstd →
  başlık → XOR) açar, içindeki sfnt'nin cmap'i okunur. Her font bir kez, modun değiştireceği dosyanın yoluyla
  (`mesg/Font/X.bfttf.zs`; tarayıcının gösterdiği `>X.bfttf` iç dosyası değil) listelenir.

Hangi metnin hangi fontla çizildiği dosyalardan güvenilir biçimde anlaşılamaz; bu yüzden rapor
her fontu ayrı listeler ve harf başına "kaç Latin fontta var" sayar. Dile özgü fontlar (Japonca,
Çince, Rusça…) varsayılan hesaba katılmaz.
"""

from __future__ import annotations

import io
import logging
import re
import struct
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import UnityPy
from fontTools.ttLib import TTFont, TTLibError

from nxceviri.core.archives import nested
from nxceviri.core.container.view import GameView
from nxceviri.core.errors import NxError
from nxceviri.core.fontpatch import switchfont, ttf
from nxceviri.core.fontpatch.ttf import is_cjk_chars
from nxceviri.core.fontpatch.unity import patch_fonts
from nxceviri.core.formats.registry import member_reader
from nxceviri.core.formats.scanner import ScanReport, base_detail, scan_view
from nxceviri.core.pipeline import Inputs, opened_view
from nxceviri.core.progress import TaskContext
from nxceviri.core.translate.widths import WidthTable, table_from_tmp, table_from_ttf

log = logging.getLogger(__name__)

TURKISH_LETTERS = "çğıİöşüÇĞÖŞÜ"
_LATIN = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
_LANG_SPECIFIC = re.compile(
    r"japan|chinese|korean|russian|cyrill|thai|arab|hebrew|greek|cjk|(?<![a-z])(ja|jp|zh|ko|kr|ru|th|ar)(?![a-z])",
    re.IGNORECASE,
)
_FONT_FILE = re.compile(r"\.(ttf|otf)$", re.IGNORECASE)
_SWITCH_FONT = re.compile(r"\.bf(ttf|otf)(\.zs)?$", re.IGNORECASE)
#: Avrupa dillerinin aksanlı harfleri (Latin-1 Ek; × ve ÷ hariç). Latin metin fontu bunları taşır; yalnızca ASCII
#: taşıyan CJK font Çince/Korece gibi bir dilin fontudur.
_WESTERN_LETTERS = frozenset(chr(c) for c in range(0xC0, 0x100) if c not in (0xD7, 0xF7))
#: CJK yoğun bir Switch fontunun Latin metin fontu sayılması için taşıması gereken aksanlı harf oranı.
_WESTERN_COVERAGE = 0.75
#: Font taramasında açılacak Unity dosya türleri (tarama raporundaki ayrıntı metni).
_UNITY_CONTAINERS = ("Unity AssetBundle", "Unity serileştirilmiş dosya")
#: Bundan büyük Unity dosyaları (ses/model/video) font aramak için açılmaz.
_MAX_UNITY_SCAN_SIZE = 256 * 1024 * 1024
#: Bundan küçük MonoBehaviour'lar TMP_FontAsset olamaz (yalnızca başlık ve birkaç alan taşırlar).
_MIN_BEHAVIOUR_SIZE = 128


def is_language_specific(name: str) -> bool:
    """Adı Japonca, Çince, Rusça… gibi belirli bir dile ait olduğunu gösteren font/dosya mı?"""
    return bool(_LANG_SPECIFIC.search(name))


KIND_TMP_STATIC = "TextMeshPro (statik atlas)"
KIND_TMP_DYNAMIC = "TextMeshPro (dinamik)"
KIND_TTF = "TrueType/OpenType"
KIND_SWITCH = "Switch sistem fontu"


def is_switch_font_path(path: str) -> bool:
    """Yolun son parçası Switch sistem fontu mu (`.bfttf`, `.bfotf`, ya da `.zs` ile sıkıştırılmışı)?"""
    return bool(_SWITCH_FONT.search(nested.split(path)[-1]))


def switch_font_source(path: str) -> str | None:
    """Tarama yolundaki Switch fontunun tek (kanonik) yolu: adı font olan en dıştaki parça.

    `mesg/Font/X.bfttf.zs>X.bfttf` → `mesg/Font/X.bfttf.zs`: mod sıkıştırılmış dosyanın yerine konur. Font değilse
    `None`.
    """
    parts = nested.split(path)
    for i, part in enumerate(parts):
        if _SWITCH_FONT.search(part):
            return nested.SEPARATOR.join(parts[: i + 1])
    return None


def is_language_specific_switch_font(name: str, chars: frozenset[str] | None) -> bool:
    """Switch fontu bir dile mi özgü? Adı öyle diyorsa ya da CJK yoğun olup Avrupa harflerinin çoğunu taşımıyorsa.

    Switch oyunlarının Latin metin fontları da Japonca glif taşır (`switchfont` bu yüzden CJK fontlara da harf ekler);
    onları Çince/Korece fontlardan ayıran, Avrupa dillerinin aksanlı harfleridir (é, ö, ç…). Çince fontlar pinyin
    için birkaç aksanlı harf (ü, é, à) taşıdığından ölçüt "hiç yok" değil, "çoğu yok"tur (gerçek oyunda görüldü).
    """
    if is_language_specific(name):
        return True
    if chars is None or not is_cjk_chars(map(ord, chars)):
        return False
    return len(chars & _WESTERN_LETTERS) < _WESTERN_COVERAGE * len(_WESTERN_LETTERS)


@dataclass(frozen=True)
class FontInfo:
    name: str
    source: str  # bulunduğu dosya
    kind: str
    chars: frozenset[str] | None  # None: karakter kümesi belirlenemedi
    language_specific: bool
    note: str = ""
    patchable: str = ""  # font yamasıyla eklenebilecek eksik harfler
    #: Harf genişlikleri (sığdırmada fontla ölçüm); okuyucu ilerleme vermiyorsa `None`. Font verisi saklanmaz.
    widths: WidthTable | None = field(default=None, compare=False, repr=False)

    @property
    def is_latin(self) -> bool:
        return self.chars is not None and self.chars >= _LATIN and not self.language_specific

    def missing(self, letters: str = TURKISH_LETTERS, patched: bool = False) -> str:
        if self.chars is None:
            return ""
        return "".join(c for c in letters if c not in self.chars and not (patched and c in self.patchable))


@dataclass
class FontReport:
    fonts: list[FontInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def latin_static(self) -> list[FontInfo]:
        return [f for f in self.fonts if f.is_latin and f.kind != KIND_TMP_DYNAMIC]

    @property
    def latin_dynamic(self) -> list[FontInfo]:
        return [f for f in self.fonts if f.is_latin and f.kind == KIND_TMP_DYNAMIC]

    def coverage(self, patched: bool = False) -> dict[str, tuple[int, int]]:
        """Harf → (bulunduğu Latin statik font sayısı, Latin statik font sayısı).

        `patched` ise font yamasıyla eklenebilecek harfler de var sayılır.
        """
        fonts = self.latin_static
        return {
            c: (sum(1 for f in fonts if f.chars is not None and c not in f.missing(c, patched)), len(fonts))
            for c in TURKISH_LETTERS
        }

    def missing_letters(self, patched: bool = False) -> str:
        """Latin statik fontların en az yarısında olmayan harfler (dönüştürme için varsayılan küme)."""
        result = ""
        for c, (have, total) in self.coverage(patched).items():
            if total and have * 2 < total:
                result += c
        return result

    @property
    def patchable_letters(self) -> str:
        """En az bir fontta yamayla eklenebilecek harfler."""
        return "".join(c for c in TURKISH_LETTERS if any(c in f.patchable for f in self.fonts))

    def dynamic_fallback_letters(self) -> str:
        """Statik fontlarda eksik olup dinamik bir TMP fontunda bulunan harfler."""
        dynamic = [f for f in self.latin_dynamic if f.chars is not None]
        return "".join(c for c in self.missing_letters() if any(c in f.chars for f in dynamic if f.chars))

    @property
    def patch_files(self) -> tuple[str, ...]:
        """Font yamasının uygulanacağı dosyalar: eksik harfi eklenebilen en az bir fontu olan Unity dosyaları."""
        return tuple(sorted({f.source for f in self.fonts if f.patchable}))

    def to_settings(self) -> str:
        return self.missing_letters()

    def measuring_table(self) -> WidthTable | None:
        """Sığdırmada genişlik ölçümünün fontu: ASCII harflerin en çoğunu kapsayan Latin statik font (eşitlikte büyük
        tablo, sonra ad). Genişlik tablosu olan Latin statik font yoksa `None` (yaklaşık tablo kullanılır)."""
        candidates = [f for f in self.latin_static if f.widths is not None]

        def rank(font: FontInfo) -> tuple[int, int, str]:
            advances = font.widths.advances if font.widths is not None else {}
            return (sum(1 for c in _LATIN if c in advances), len(advances), font.name)

        return max(candidates, key=rank).widths if candidates else None


def _ttf_chars(raw: bytes) -> frozenset[str] | None:
    try:
        cmap = TTFont(io.BytesIO(raw), lazy=True).getBestCmap()
    except (TTLibError, ValueError, KeyError, AssertionError, struct.error):
        return None
    return frozenset(chr(c) for c in (cmap or {}) if c < 0x110000)


def _ttf_widths(raw: bytes, chars: frozenset[str] | None, name: str, allow_cjk: bool = False) -> WidthTable | None:
    """TTF/OTF'un harf genişlikleri; okunamayan ya da Çince/Japonca/Korece font için `None` (ölçüm fontu olamaz,
    büyük tabloyu boşuna açmayalım). `allow_cjk`: CJK glifleri de taşıyan Latin fontu (Switch) ölçülür."""
    if chars is None or (not allow_cjk and is_cjk_chars(map(ord, chars))):
        return None
    try:
        return table_from_ttf(raw, name)
    except (TTLibError, ValueError, KeyError, AssertionError, struct.error, EOFError) as exc:
        log.debug("Font genişlikleri okunamadı (%s): %s", name, type(exc).__name__)
        return None


def _is_font_bundle(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    return name.endswith(".bundle") and "font" in name


#: Bir `Font` nesnesinin tanımı: (dosya adı, path_id). Addressables paketlerinde birden çok serileştirilmiş
#: dosya vardır ve path_id'ler dosyalar arasında çakışır.
_FontKey = tuple[str, int]


def _tmp_script_ids(objects: list[Any]) -> tuple[bool, set[_FontKey]]:
    """(dosyada betik bilgisi var mı, `TMP_FontAsset` betiklerinin tanımları)."""
    scripts = [o for o in objects if o.type.name == "MonoScript"]
    found = set()
    for obj in scripts:
        try:
            if str(obj.read().m_ClassName) == "TMP_FontAsset":
                found.add((str(obj.assets_file.name), int(obj.path_id)))
        except Exception as exc:
            log.debug("MonoScript okunamadı (%s): %s", obj.path_id, type(exc).__name__)
    return bool(scripts), found


def _is_tmp_candidate(obj: Any, have_scripts: bool, tmp_scripts: set[_FontKey]) -> bool:
    """Sahnelerde binlerce MonoBehaviour vardır; tip ağacı yalnızca olası `TMP_FontAsset`'ler için okunur."""
    raw = obj.get_raw_data()
    if len(raw) < _MIN_BEHAVIOUR_SIZE:
        return False
    if not have_scripts:
        return True
    # MonoBehaviour başlığı: m_GameObject (12), m_Enabled (4, hizalı), m_Script (fileID 4 + path_id 8)
    script = int.from_bytes(raw[20:28], "little", signed=True)
    return (str(obj.assets_file.name), script) in tmp_scripts


def _unity_fonts(
    data: bytes, source: str
) -> tuple[list[dict[str, Any]], dict[_FontKey, tuple[str, frozenset[str] | None]]]:
    """Bir Unity dosyasındaki TMP fontlarını ve `Font` nesnelerini okur.

    İkinci değer: `Font` nesnelerinin `(dosya, path_id) → (ad, karakter kümesi)`; dinamik TMP fontlarının kaynak
    fontunu çözmek için gerekir.
    """
    try:
        env = UnityPy.load(data)
    except Exception as exc:  # UnityPy her bozukluktta farklı istisna fırlatır
        raise NxError(f"{source}: font dosyası açılamadı ({type(exc).__name__}).") from None
    objects = list(env.objects)
    have_scripts, tmp_scripts = _tmp_script_ids(objects)
    found: list[dict[str, Any]] = []
    sources: dict[_FontKey, tuple[str, frozenset[str] | None]] = {}
    for obj in objects:
        name = obj.type.name
        if name not in ("Font", "MonoBehaviour"):
            continue
        if name == "MonoBehaviour" and not _is_tmp_candidate(obj, have_scripts, tmp_scripts):
            continue
        try:
            tree = obj.read_typetree()
        except Exception as exc:
            log.debug("Nesne okunamadı (%s, %s): %s", source, obj.path_id, type(exc).__name__)
            continue
        file_name = str(obj.assets_file.name)
        if name == "Font":
            raw = bytes(tree.get("m_FontData") or b"")
            chars = _ttf_chars(raw) if raw else None
            font_name = str(tree.get("m_Name", ""))
            sources[(file_name, int(obj.path_id))] = (font_name, chars)
            if raw:
                found.append(
                    {"name": font_name, "kind": KIND_TTF, "chars": chars, "widths": _ttf_widths(raw, chars, font_name)}
                )
        elif "m_CharacterTable" in tree:
            chars = frozenset(
                chr(int(c["m_Unicode"]))
                for c in tree["m_CharacterTable"]
                if 0 <= int(c.get("m_Unicode", -1)) < 0x110000
            )
            dynamic = int(tree.get("m_AtlasPopulationMode", 0)) != 0
            src = (tree.get("m_SourceFontFile") or {}).get("m_PathID", 0)
            tmp_name = str(tree.get("m_Name", ""))
            found.append(
                {
                    "name": tmp_name,
                    "kind": KIND_TMP_DYNAMIC if dynamic else KIND_TMP_STATIC,
                    "chars": chars,
                    "source_font": (file_name, int(src)) if dynamic else None,
                    "widths": table_from_tmp(tree.get("m_GlyphTable") or [], tree["m_CharacterTable"], tmp_name),
                }
            )
    return found, sources


def switch_font_chars(data: bytes) -> frozenset[str] | None:
    """Switch fontunun karakterleri (kapsayıcı açılarak); kapsayıcı çözülemezse `ValueError`."""
    return _ttf_chars(switchfont.unwrap(data)[1])


def read_switch_font(data: bytes, source: str) -> tuple[dict[str, Any] | None, str]:
    """Switch fontunu açar: (font bilgisi, uyarı). Kapsayıcı çözülemezse bilgi `None`, uyarı dolu."""
    name = source.rsplit(nested.SEPARATOR, 1)[-1].rsplit("/", 1)[-1]
    if name.lower().endswith(".zs"):
        name = name[:-3]
    try:
        _header, sfnt, _key = switchfont.unwrap(data)
    except ValueError as exc:
        return None, f"{source}: Switch fontu açılamadı ({exc})."
    chars = _ttf_chars(sfnt)
    lang = is_language_specific_switch_font(name, chars)
    info: dict[str, Any] = {
        "name": name,
        "kind": KIND_SWITCH,
        "chars": chars,
        "lang": lang,
        "patchable": "" if lang else ttf.plan(sfnt, ttf.PATCHABLE, allow_cjk=True)[0],
        "widths": None if lang else _ttf_widths(sfnt, chars, name, allow_cjk=True),
    }
    return info, ""


def is_font_bundle(path: str) -> bool:
    """Font içerdiği adından anlaşılan Unity bundle'ı (ör. "fonts_assets_all.bundle")."""
    return ">" not in path and _is_font_bundle(path)


def is_patchable_font_bundle(path: str) -> bool:
    """Font yamasının deneneceği bundle: dile özgü olmayan (ör. "fonts-japanese…" değil) font bundle'ı."""
    return is_font_bundle(path) and not is_language_specific(path.rsplit("/", 1)[-1])


def _patch_plan(data: bytes, source: str, result: FontReport) -> list[Any]:
    """Font yamasının bu bundle'da hangi harfleri ekleyebileceği (dosyaya dokunmadan)."""
    try:
        return patch_fonts(data, write=False, skip=is_language_specific)[1]
    except NxError as exc:
        result.warnings.append(f"{source}: {exc.message}")
        return []


def scan_fonts(view: GameView, report: ScanReport, ctx: TaskContext | None = None) -> FontReport:
    """Oyundaki fontları bulur ve karakter kümelerini okur.

    Fontlar yalnızca adında "font" geçen bundle'larda değildir (ör. kimi oyunda sahne paketinde ve `resources.assets`
    içindedir); bu yüzden boyutu makul tüm Unity dosyaları açılır.
    """
    ctx = ctx or TaskContext()
    result = FontReport()
    trees = {t.title_id: t for t in view.trees}
    switch_fonts: dict[str, str] = {}  # kanonik yol → TitleID (aynı fontun iç dosyası ikinci kez sayılmaz)
    for e in report.entries:
        source = switch_font_source(e.path)
        if source is not None:
            switch_fonts.setdefault(source, e.title_id)
    targets = [
        e
        for e in report.entries
        if switch_font_source(e.path) is None
        and (
            (
                e.kind == "unity"
                and ">" not in e.path
                and base_detail(e.detail) in _UNITY_CONTAINERS
                and e.size <= _MAX_UNITY_SCAN_SIZE
            )
            or _FONT_FILE.search(e.path.split(">")[-1])
            or base_detail(e.detail) in ("OpenType font", "Font")
        )
    ]
    pending: list[tuple[str, dict[str, Any]]] = []
    total = len(targets) + len(switch_fonts)
    for j, (source, title_id) in enumerate(sorted(switch_fonts.items())):
        ctx.report(len(targets) + j, total, f"Font okunuyor: {source}")
        tree = trees.get(title_id)
        if tree is None:
            continue
        try:
            info, warning = read_switch_font(member_reader(tree).read(source), source)
        except NxError as exc:
            result.warnings.append(exc.message)
            continue
        if info is None:
            result.warnings.append(warning)
        else:
            pending.append((source, info))
    for i, entry in enumerate(targets):
        ctx.report(i, total, f"Font okunuyor: {entry.path}")
        tree = trees.get(entry.title_id)
        if tree is None:
            continue
        parts = nested.split(entry.path)
        try:
            data = member_reader(tree).read(entry.path)
            if entry.kind == "unity":
                found, sources = _unity_fonts(data, entry.path)
                if not found:
                    continue
                plans = (
                    {p.font: p.added for p in _patch_plan(data, entry.path, result)}
                    if not is_language_specific(entry.path.rsplit("/", 1)[-1])
                    else {}
                )
                for font in found:
                    if font["kind"] == KIND_TMP_DYNAMIC:
                        source_name, source_chars = sources.get(font["source_font"] or ("", 0), ("", None))
                        font["source_chars"] = source_chars
                        font["patchable"] = plans.get(source_name, "")
                    else:
                        font["patchable"] = plans.get(font["name"], "")
                    pending.append((entry.path, font))
            else:
                name = parts[-1].rsplit("/", 1)[-1]
                chars = _ttf_chars(data)
                pending.append(
                    (
                        entry.path,
                        {"name": name, "kind": KIND_TTF, "chars": chars, "widths": _ttf_widths(data, chars, name)},
                    )
                )
        except NxError as exc:
            result.warnings.append(exc.message)
    for source, f in pending:
        chars = f["chars"]
        note = ""
        if f["kind"] == KIND_TMP_DYNAMIC:
            src_chars = f.get("source_chars")
            if src_chars is not None:
                chars = frozenset(chars | src_chars)
                note = "Eksik karakterleri kaynak fonttan çalışma anında üretir."
            else:
                note = "Kaynak fontu bulunamadı; yalnızca atlastaki karakterler sayıldı."
        lang = (
            f["lang"]
            if "lang" in f
            else (
                is_language_specific(source.rsplit("/", 1)[-1])
                or is_language_specific(f["name"])
                or (f["kind"] == KIND_TTF and chars is not None and is_cjk_chars(map(ord, chars)))
            )
        )
        result.fonts.append(
            FontInfo(f["name"], source, f["kind"], chars, lang, note, f.get("patchable", ""), f.get("widths"))
        )
    ctx.report(total, total, "Font denetimi tamamlandı")
    return result


#: Elle düzenlenebilen font dosyalarının başlık imzaları (TrueType, OpenType/CFF, Apple TrueType).
_FONT_MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")


def is_editable_font(font: FontInfo) -> bool:
    """RomFS'te serbest duran TTF/OTF dosyası mı? Yalnızca bunlar dışa aktarılıp düzenlenmiş hâli moda konabilir."""
    return font.kind == KIND_TTF and ">" not in font.source and bool(_FONT_FILE.search(font.source))


def looks_like_font(path: Path) -> bool:
    """Dosya TTF/OTF başlığıyla mı başlıyor? (İçe alınan dosyanın yanlışlıkla başka bir şey olmasın.)"""
    try:
        with path.open("rb") as fh:
            return fh.read(4) in _FONT_MAGIC
    except OSError:
        return False


def font_advice(font: FontInfo) -> str:
    """Fontun Türkçe harfler için ne yapılabileceği: neden yamanabilir/yamanamaz, hangi yol önerilir (kısa)."""
    if font.language_specific:
        return "Bu dile özgü font; Türkçe metinde kullanılmaz."
    missing = font.missing()
    # Yama harf ekleyebiliyorsa her türde öneri yamadır (genel sonuçla aynı); diğer iletiler yamalanamayan fontlar için.
    if font.patchable and (font.chars is None or missing):
        rest = "".join(c for c in missing if c not in font.patchable)
        text = f"Font yaması {' '.join(font.patchable)} harflerini ekler"
        return text + ("; kalanlara harf dönüştürme." if rest else ".")
    if font.kind == KIND_TMP_DYNAMIC:
        return "Dinamik font: oyun eksik harfleri yedek fonttan çizer; görünüm biraz farklı olabilir."
    if font.chars is not None and not missing:
        return "Türkçe harflerin hepsi var."
    if font.kind in (KIND_TMP_STATIC, KIND_SWITCH):
        return "Eksik harflerin parçaları fontta yok; harf dönüştürme kullanın."
    if is_editable_font(font):
        return "TTF/OTF dosyası: Fontu Dışa Aktar ile FontForge gibi bir araçta düzenleyip içe alın."
    if font.kind == KIND_TTF:
        return "Paket içindeki font dışarıda düzenlenemez; harf dönüştürme kullanın."
    return "Bu font türü yamanamıyor; harf dönüştürme kullanın."


def scan_game_fonts(inputs: Inputs, ctx: TaskContext | None = None) -> FontReport:
    """Oyunu açar, dosya taramasını yapar ve fontları okur (arayüzsüz yol; komut satırı aracı kullanır)."""
    ctx = ctx or TaskContext()
    with opened_view(inputs, ctx) as view:
        return scan_fonts(view, scan_view(view, ctx), ctx)


DURUM_TAMAM = "tamam"
DURUM_YAMALANABILIR = "yamalanabilir"
DURUM_DONUSTURME = "donusturme"


@dataclass(frozen=True)
class FontVerdict:
    """Font taramasının tek satırlık sonucu: üç durumdan biri ve öneri metni."""

    durum: str
    eksik: str  # Latin statik fontların çoğunda olmayan harfler
    yamalanabilir: str  # font yamasıyla eklenebilecek harfler
    kalan: str  # yamadan sonra da eksik kalacak harfler (dönüştürme gerekir)
    oneri: str


def font_verdict(report: FontReport, plugin_notes: Sequence[tuple[str, str]] = ()) -> FontVerdict:
    """Raporun özeti: ek iş gerekmez / font yaması yeter / harf dönüştürme gerekir.

    `plugin_notes`: etkin eklentilerin `font_support` bildirimleri (`registry.font_support_notes`). Okunabilen font
    yokken eklenti fontları kendisi yamalıyorsa harf dönüştürme önerilmez."""
    usable = [f for f in report.fonts if f.chars is not None and not f.language_specific]
    if not usable and plugin_notes:
        ad = ", ".join(f"“{a}”" for a, _ in plugin_notes)
        cumle = " ".join(c for _, c in plugin_notes)
        return FontVerdict(
            DURUM_TAMAM,
            "",
            "",
            "",
            f"Fontları {ad} eklentisi yönetiyor: {cumle} Eklenen harfler dışa aktarmada bilgi dosyasında listelenir.",
        )
    if not usable:
        return FontVerdict(
            DURUM_DONUSTURME,
            "",
            "",
            TURKISH_LETTERS,
            "Font yamalanamıyor: harf dönüştürme gerekir (ğ→g, ş→s, ı→i…); okunabilen font bulunamadı, "
            f'eklentide `unsupported_letters` = "{TURKISH_LETTERS}" verin ya da fontu elle inceleyin.',
        )
    missing = report.missing_letters()
    if not missing:
        return FontVerdict(DURUM_TAMAM, "", "", "", "Türkçe harflerin tümü var: ek iş gerekmez.")
    patchable = "".join(c for c in missing if c in report.patchable_letters)
    rest = report.missing_letters(patched=True)
    if not rest:
        return FontVerdict(
            DURUM_YAMALANABILIR,
            missing,
            patchable,
            "",
            f"Eksik harfler font yamasıyla eklenebilir: {' '.join(missing)} (uygulamada Kontrol Et > Fontları Tara, "
            "sonra font yamasını açın).",
        )
    return FontVerdict(
        DURUM_DONUSTURME,
        missing,
        patchable,
        rest,
        f'Font yamalanamıyor: harf dönüştürme gerekir (ğ→g, ş→s, ı→i…); eklentide `unsupported_letters` = "{rest}" '
        "verin." + (f" ({' '.join(patchable)} yamayla eklenebilir.)" if patchable else ""),
    )
