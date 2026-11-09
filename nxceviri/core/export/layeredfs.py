"""LayeredFS mod klasörü üretimi (CLAUDE.md §4.6).

- **Atmosphère (Switch):** `atmosphere/contents/<TitleID>/romfs/<yol>` — SD kartın köküne kopyalanır.
- **Emülatör:** `<TitleID>/<Mod Adı>/romfs/<yol>` — Ryujinx'te `mods/contents/`, Yuzu türevlerinde
  `load/` klasörüne kopyalanır.

Yalnızca değişen dosyalar yazılır. Çeviriler "Onaylandı", "Makine" veya "Redakte" durumundaki satırlardan
alınır; "Hatalı" satırlar yazılmaz (oyunda orijinal metin kalır). Her dosya önce bellekte üretilir,
yeniden açılıp her metnin beklenen değerde olduğu doğrulanır, sonra geçici klasöre yazılır; iş bitince
geçici klasör tek hamlede hedefe taşınır. Hata veya iptalde hedefte hiçbir şey kalmaz. Oyunun orijinal
dosyaları yalnızca okunur.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from collections.abc import Callable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from nxceviri import __version__
from nxceviri.core.archives import cpk, m2, nested, nni, wad
from nxceviri.core.archives.access import (
    MemberReader,
    is_cpk_path,
    is_m2_path,
    is_nni_path,
    is_pak_path,
    is_wad_path,
)
from nxceviri.core.archives.pak import PakFile, build_patch_pak, relative_to_mount
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import ContentTree, safe_relative_path
from nxceviri.core.errors import ContainerError, NxError, OperationCancelled
from nxceviri.core.export import extras
from nxceviri.core.export.addressables import CatalogError, patch_catalog_crc
from nxceviri.core.fontpatch.unity import FALLBACK_REASON, patch_fonts
from nxceviri.core.formats.base import FormatPlugin
from nxceviri.core.formats.registry import plugin_for_kind
from nxceviri.core.pipeline import Inputs, opened_view
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import TranslationRow, row_group
from nxceviri.core.qa import transliterate
from nxceviri.core.qa.fonts import is_language_specific, is_patchable_font_bundle
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.codekinds import KIND_SYMBOL, KIND_VARIABLE, guess_kind
from nxceviri.core.translate.status import Status
from nxceviri.core.translate.uppercase import UppercaseRules, dotted_capitals

LAYOUT_ATMOSPHERE = "atmosphere"
LAYOUT_EMULATOR = "emulator"
LAYOUT_LABELS = {
    LAYOUT_ATMOSPHERE: "Atmosphère (Switch, SD kart)",
    LAYOUT_EMULATOR: "Emülatör (Ryujinx / Yuzu türevleri)",
}
INFO_FILE = "NXTR - Bilgi.txt"
_EXPORTABLE = (Status.APPROVED, Status.MACHINE, Status.REDACTED)
#: Font yamasının, harfi türetebileceği temel harf fontta olmadığında verdiği neden öneki.
_NO_BASE_LETTER = "kaynak harf yok"


class ExportError(NxError):
    """Mod üretilemedi."""


@dataclass(frozen=True)
class TextFileRef:
    path: str  # tarama yolu (iç arşiv yolu olabilir)
    title_id: str
    format: str


@dataclass(frozen=True)
class ExportOptions:
    layout: str
    dest: Path
    mod_name: str
    transliterate_letters: str = ""
    patch_fonts: bool = False  # TMP fontlarına eksik Türkçe harfleri ekle (M8)
    #: Adında "font" geçmese de yamalanacak fontları içeren dosyalar (Kontrol Et → Fontları Tara bulur)
    font_files: frozenset[str] = frozenset()
    uppercase: UppercaseRules = field(default_factory=UppercaseRules)  # büyük harfle çizilen satırlar: i → İ
    #: Ürün sahibinin bilinçli istisnası (CLAUDE.md §4.3): "Hatalı" satırlar da çevirileriyle yazılır; biçim
    #: eklentisi bir satırı reddederse o satır orijinal kalır. Yalnızca kullanıcı açıkça seçerse True olur.
    include_errors: bool = False
    #: Hedef doluysa eski modun yerine yaz (yalnızca NXTR'nin ürettiği, bilgi dosyası olan bir mod klasörüyse).
    overwrite: bool = False
    #: Moda olduğu gibi eklenecek dosyalar: TitleID (16 hane) → {RomFS yolu: içerik} (ör. elle düzenlenmiş font).
    extra_files: Mapping[str, Mapping[str, bytes]] = field(default_factory=dict)


@dataclass(frozen=True)
class ExportInfo:
    game_name: str
    title_id: str
    base_version: int | None
    update_version: int | None


@dataclass
class ExportResult:
    dest: Path
    files: list[str] = field(default_factory=list)  # yazılan dosyaların mod köküne göre yolları
    rows_written: int = 0
    rows_error: int = 0
    rows_error_written: int = 0  # include_errors açıkken çevirisiyle yazılan hatalı satır sayısı
    rows_error_kept: int = 0  # include_errors açıkken orijinal bırakılan hatalı satır (reddedilen veya çevirisiz)
    rows_untranslated: int = 0
    rows_uppercase: int = 0  # i → İ dönüşümü uygulanan satır sayısı
    unchanged_files: int = 0
    warnings: list[str] = field(default_factory=list)
    font_patches: list[str] = field(default_factory=list)  # "Font: eklenen harfler" satırları
    font_notes: list[str] = field(default_factory=list)  # harf eklenemeyen/atlanan fontların nedenleri
    extra_notes: list[str] = field(default_factory=list)  # eklentilerin ek dosyaları (ör. grafik çevirisi) satırları
    catalog_crc_fixes: list[int] = field(default_factory=list)  # CRC'si sıfırlanan paketlerin boyutları
    #: Dosya yolu → hatalı olduğu hâlde yazılmayı deneyecek anahtarlar (yalnızca include_errors açıkken dolu)
    soft_keys: dict[str, frozenset[str]] = field(default_factory=dict, repr=False)
    #: Dosya yolu → biçim eklentisinin reddettiği, orijinal bırakılan hatalı anahtarlar
    dropped_keys: dict[str, frozenset[str]] = field(default_factory=dict, repr=False)
    #: Dosya yolu → yalnızca kod sırası orijinalden farklı olduğu için hatalı sayılan, yazılmayı deneyecek anahtarlar
    reordered_keys: dict[str, frozenset[str]] = field(default_factory=dict, repr=False)
    #: Dosya yolu → dışa aktarma sırasında gerçekten denenen hatalı anahtarlar (işlenmeyen dosyalar burada olmaz)
    attempted_keys: dict[str, frozenset[str]] = field(default_factory=dict, repr=False)
    #: İptal denetimi (`TaskContext.check`); uzun ikili bölme döngüsü bunu çağırır.
    cancel_check: Callable[[], None] = field(default=lambda: None, repr=False)


#: Sırası değişince oyunu bozmayan kod türleri (eşi olmayan, tek başına duran kodlar).
_FREE_KINDS = frozenset({KIND_VARIABLE, KIND_SYMBOL})


def safe_mod_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip().rstrip(".")
    return cleaned or "Turkce Ceviri"


def _mod_root(layout: str, title_id: str, mod_name: str) -> Path:
    if layout == LAYOUT_ATMOSPHERE:
        return Path("atmosphere", "contents", title_id, "romfs")
    if layout == LAYOUT_EMULATOR:
        return Path(title_id, safe_mod_name(mod_name), "romfs")
    raise ExportError(f"Bilinmeyen mod yapısı: {layout}")


def collect_translations(
    rows: list[TranslationRow],
    letters: str,
    uppercase: UppercaseRules | None = None,
    *,
    include_errors: bool = False,
    soft: dict[str, set[str]] | None = None,
    reordered: dict[str, set[str]] | None = None,
) -> tuple[dict[str, dict[str, str]], int, int, int]:
    """Dosya → {anahtar → yazılacak metin}; ayrıca (yazılacak, hatalı, çevrilmemiş) satır sayıları.

    `include_errors` kapalıyken (varsayılan) hatalı satırlar yazılmaz. Açıkken çevirisi olan hatalı satırlar
    da metin tablosuna girer ama "yazılacak" sayısına katılmaz; anahtarları `soft` sözlüğüne (dosya → anahtarlar)
    eklenir ki dışa aktarma bunları reddedilirse orijinale döndürebilsin. "Hatalı" sayısı her iki durumda
    da tüm hatalı satırlardır.

    Kontrol kodu sorunu olan hatalı satırlar (eksik, fazla, kodun sayısı farklı) biçim eklentisi zaten reddedeceği
    için hiç denenmez; tabloya girmez, orijinal kalır. Tek farkı kod sırası olan satır, yalnızca serbest kodların
    (değişken, simge) yeri değiştiyse denenir; anahtarı ayrıca `reordered` sözlüğüne yazılır.
    """
    uppercase = uppercase or UppercaseRules()
    by_file: dict[str, dict[str, str]] = {}
    written = errors = untranslated = 0
    for r in rows:
        if r.status in _EXPORTABLE and r.translation:
            text = dotted_capitals(r.translation) if uppercase.applies(r.file, r.key, row_group(r)) else r.translation
            by_file.setdefault(r.file, {})[r.key] = transliterate.apply(text, letters)
            written += 1
        elif r.status == Status.ERROR:
            errors += 1
            if include_errors and r.translation:
                reorder = False
                if placeholders.problems(r.source, r.translation):
                    if not placeholders.order_only_problem(r.source, r.translation, _free_code_of(r)):
                        continue
                    reorder = True
                text = (
                    dotted_capitals(r.translation) if uppercase.applies(r.file, r.key, row_group(r)) else r.translation
                )
                by_file.setdefault(r.file, {})[r.key] = transliterate.apply(text, letters)
                if soft is not None:
                    soft.setdefault(r.file, set()).add(r.key)
                if reorder and reordered is not None:
                    reordered.setdefault(r.file, set()).add(r.key)
        elif r.source.strip():
            untranslated += 1
    return by_file, written, errors, untranslated


def _free_code_of(row: TranslationRow) -> Callable[[int], bool]:
    """Satırın `⟦n⟧` kodunun serbest (yeri değişebilir) olup olmadığı: değişken ve simge tek başına durur."""

    def free(n: int) -> bool:
        return 0 < n <= len(row.code_labels) and guess_kind(row.code_labels[n - 1]) in _FREE_KINDS

    return free


def fold_unsupported_letters(translations: dict[str, dict[str, str]], files: list[TextFileRef]) -> str:
    """Biçim eklentisinin fontunda olmayan Türkçe harfleri (ör. ğ ş ı İ) o dosyalarda dönüştürür.

    Kullanıcının seçtiği harf dönüştürmesine ek olarak çalışır; yalnızca eklentinin bildirdiği harfler
    değişir. Dönüştürülen harflerin birleşimini döndürür (rapor için)."""
    folded = ""
    for ref in files:
        plugin = plugin_for_kind(ref.format, ref.title_id)
        if ref.path not in translations:
            continue
        normalize = getattr(plugin, "normalize_text", None)
        if normalize is not None:
            translations[ref.path] = {k: normalize(v) for k, v in translations[ref.path].items()}
        letters = getattr(plugin, "unsupported_letters", "")
        if not letters:
            continue
        translations[ref.path] = {k: transliterate.apply(v, letters) for k, v in translations[ref.path].items()}
        folded += "".join(c for c in letters if c not in folded)
    return folded


def support_files(files: list[TextFileRef], layout: str, mod_name: str) -> list[tuple[Path, bytes]]:
    """Biçim eklentilerinin moda eklediği dosyalar (ör. Devil May Cry'nin Türkçe harfli yazı dokusu)."""
    out: list[tuple[Path, bytes]] = []
    seen: set[tuple[str, str]] = set()
    for ref in files:
        plugin = plugin_for_kind(ref.format, ref.title_id)
        provider = getattr(plugin, "support_files", None)
        if provider is None or (ref.title_id, ref.format) in seen:
            continue
        seen.add((ref.title_id, ref.format))
        root = _mod_root(layout, ref.title_id, mod_name)
        out.extend((root / safe_relative_path(rel), data) for rel, data in provider().items())
    return out


def game_file_patches(files: list[TextFileRef]) -> dict[tuple[str, str], Callable[[bytes], bytes]]:
    """Biçim eklentilerinin metinden bağımsız değiştirdiği oyun dosyaları ((TitleID, yol) → dönüştürücü).

    Ör. Devil May Cry'nin menü başlığı resimleri; dosya metin de içeriyorsa dönüştürücü çeviriler yazıldıktan
    sonra uygulanır.
    """
    out: dict[tuple[str, str], Callable[[bytes], bytes]] = {}
    for ref in files:
        provider = getattr(plugin_for_kind(ref.format, ref.title_id), "game_file_patches", None)
        if provider is not None:
            out.update({(ref.title_id, path): patch for path, patch in provider().items()})
    return out


def exefs_patch_path(layout: str, title_id: str, mod_name: str, build_id: str) -> Path:
    """Program yamasının (IPS) mod içindeki yeri: Atmosphère `exefs_patches`, emülatör `exefs` klasörü."""
    if layout == LAYOUT_ATMOSPHERE:
        return Path("atmosphere", "exefs_patches", safe_mod_name(mod_name), f"{build_id}.ips")
    return Path(title_id, safe_mod_name(mod_name), "exefs", f"{build_id}.ips")


def _info_text(info: ExportInfo, options: ExportOptions, result: ExportResult) -> str:
    versions = f"ana oyun v{info.base_version}" if info.base_version is not None else "ana oyun yok"
    if info.update_version is not None:
        versions += f", güncelleme v{info.update_version}"
    if options.layout == LAYOUT_ATMOSPHERE:
        howto = (
            "Kurulum (Switch, Atmosphère): bu klasördeki 'atmosphere' klasörünü SD kartın köküne kopyalayın\n"
            "(var olan 'atmosphere' klasörüyle birleştirin). Oyunu kapatıp yeniden açın."
        )
    else:
        howto = (
            f"Kurulum (emülatör): '{info.title_id}' klasörünü emülatörün mod klasörüne kopyalayın.\n"
            "Ryujinx: oyuna sağ tık → 'Open Mods Directory' (mods/contents/<TitleID>/ içine).\n"
            "Yuzu türevleri: oyuna sağ tık → 'Open Mod Data Location' (load/<TitleID>/ içine)."
        )
    if any(f.endswith(m2.INDEX_SUFFIX) for f in result.files):
        howto += (
            "\nM2 (Metal Gear Solid): oyunun arşiv dizini ('alldata.psb.m', değişen dosyaların kaydı çıkarılmış) ve "
            "değişen dosyaların kendisi verilir; 8 GB'lık 'alldata.bin' değiştirilmez."
        )
    if any(f.endswith(".ips") for f in result.files):
        howto += (
            "\nProgram yaması: oyun kodundaki metinler (ör. düşman açıklamaları) '.ips' yamasıyla değiştirilir; "
            "Atmosphère'de 'atmosphere/exefs_patches', emülatörde modun 'exefs' klasörü. Yama yalnızca bu oyun "
            "sürümünde çalışır."
        )
    if any(f.endswith("_NXCeviri_P.pak") for f in result.files):
        howto += (
            "\nUnreal: çeviriler orijinal pak'ın yanına konan '..._NXCeviri_P.pak' yama pak'ındadır; orijinal "
            "pak'a dokunulmaz. Oyun pak'ları imzalıysa yama yok sayılabilir."
        )
    letters = options.transliterate_letters
    conversion = f"{' '.join(letters)} → {' '.join(transliterate.apply(letters, letters))}" if letters else "yok"
    return (
        f"NXTR {__version__} ile üretildi — {datetime.now():%Y-%m-%d %H:%M}\n\n"
        f"Oyun: {info.game_name}\nTitleID: {info.title_id}\nÜretildiği sürüm: {versions}\n"
        "Bu mod yalnızca bu sürümle kullanılmalıdır; oyun güncellenirse modu yeniden üretin.\n\n"
        f"Yazılan çeviri satırı: {result.rows_written}\n"
        + (
            f"Hatalı olduğu hâlde çevirisiyle yazılan satır (oyun çökebilir): {result.rows_error_written}\n"
            f"Hatalı olduğu için orijinal bırakılan satır: {result.rows_error_kept}\n"
            if options.include_errors
            else f"Hatalı olduğu için yazılmayan satır: {result.rows_error}\n"
        )
        + f"Çevrilmemiş (orijinal kalan) satır: {result.rows_untranslated}\n"
        f"Harf dönüştürme: {conversion}\n"
        + (f"Büyük harfle gösterilen satır (i → İ yazıldı): {result.rows_uppercase}\n" if result.rows_uppercase else "")
        + (
            "Font yaması (eklenen harfler):\n" + "".join(f"  {line}\n" for line in result.font_patches)
            if result.font_patches
            else ""
        )
        + (
            "Font yaması (eklenemeyen / atlanan fontlar):\n" + "".join(f"  {line}\n" for line in result.font_notes)
            if result.font_notes
            else ""
        )
        + "".join(f"{line}\n" for line in result.extra_notes)
        + (
            "Addressables katalog CRC düzeltmesi: "
            f"{len(result.catalog_crc_fixes)} paket ("
            + ", ".join(str(size) for size in result.catalog_crc_fixes)
            + " bayt) — değiştirilen paketlerin CRC denetimi kapatıldı.\n"
            if result.catalog_crc_fixes
            else ""
        )
        + f"Değiştirilen dosya sayısı: {len(result.files)}\n\n{howto}\n"
    )


def export_mod(
    inputs: Inputs,
    files: list[TextFileRef],
    rows: list[TranslationRow],
    *,
    options: ExportOptions,
    info: ExportInfo,
    ctx: TaskContext | None = None,
) -> ExportResult:
    ctx = ctx or TaskContext()
    dest = options.dest
    replace_old = False
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        if not options.overwrite:
            raise ExportError(
                f"Hedef klasör boş değil: {dest}",
                "Modu yeni veya boş bir klasöre üretin ya da eski modun üzerine yazmayı seçin.",
            )
        if not (dest / INFO_FILE).is_file():
            raise ExportError(
                f"Bu klasör NXTR'nin ürettiği bir mod değil: {dest}",
                "Güvenlik için silinmez. Boş ya da yeni bir klasör seçin.",
            )
        replace_old = True
    soft: dict[str, set[str]] = {}
    reordered: dict[str, set[str]] = {}
    translations, written, errors, untranslated = collect_translations(
        rows,
        options.transliterate_letters,
        options.uppercase,
        include_errors=options.include_errors,
        soft=soft,
        reordered=reordered,
    )
    result = ExportResult(dest, rows_written=written, rows_error=errors, rows_untranslated=untranslated)
    result.cancel_check = ctx.check
    result.soft_keys = {path: frozenset(keys) for path, keys in soft.items()}
    result.reordered_keys = {path: frozenset(keys) for path, keys in reordered.items()}
    folded = fold_unsupported_letters(translations, files)
    if folded:
        result.warnings.append(
            f"Bu oyunun fontunda olmayan harfler dönüştürüldü: {' '.join(folded)} → "
            f"{' '.join(transliterate.apply(folded, folded))}."
        )
    result.rows_uppercase = sum(
        1
        for r in rows
        if r.status in _EXPORTABLE and r.translation and options.uppercase.applies(r.file, r.key, row_group(r))
    )
    if not translations:
        raise ExportError(
            "Dışa aktarılacak çeviri yok.",
            "Önce “Çevir” adımında metinleri çevirin (elle veya makine çevirisiyle).",
        )
    refs = {f.path: f for f in files if f.path in translations}
    groups: dict[tuple[str, str], list[TextFileRef]] = {}
    for ref in refs.values():
        groups.setdefault((ref.title_id, nested.split(ref.path)[0]), []).append(ref)
    title_ids = {ref.title_id for ref in refs.values()}

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.{uuid.uuid4().hex[:8]}.gecici"
    tmp.mkdir()
    try:
        with opened_view(inputs, ctx) as view:
            trees = {t.title_id: t for t in view.trees}
            extra_patches = game_file_patches(list(refs.values()))
            for title_id, path in extra_patches:
                tree = trees.get(title_id)
                if tree is not None and path in tree.view.files:
                    groups.setdefault((title_id, path), [])
            if options.patch_fonts:
                for title_id in title_ids:
                    tree = trees.get(title_id)
                    for path in tree.view.files if tree is not None else []:
                        if is_patchable_font_bundle(path) or path in options.font_files:
                            groups.setdefault((title_id, path), [])
            derived = extras.collect(
                {(r.title_id, r.format) for r in refs.values()}, trees, inputs.paths[0].parent if inputs.paths else None
            )
            extra_members: dict[tuple[str, str], dict[str, bytes]] = {}
            for title_id, found in derived.items():
                result.font_patches += found.font_notes
                result.extra_notes += found.notes
                result.warnings += found.warnings
                for top, members in extras.split_members(found).items():
                    extra_members[(title_id, top)] = members
                    groups.setdefault((title_id, top), [])
            changed_sizes: set[int] = set()
            addressables_changed = False
            for i, ((title_id, top), group) in enumerate(sorted(groups.items())):
                ctx.report(i, len(groups), f"Yazılıyor: {top}")
                tree = trees.get(title_id)
                if tree is None or top not in tree.view.files:
                    raise ExportError(
                        f"Oyunda bulunamadı: {top}",
                        "Projedeki metinler başka bir oyun sürümünden aktarılmış olabilir. "
                        "Metinleri yeniden tarayıp aktarın.",
                    )
                root = _mod_root(options.layout, title_id, options.mod_name)
                outputs: list[tuple[Path, bytes]]
                if is_pak_path(top):
                    patch = _export_pak(tree, top, group, translations=translations, root=root, result=result)
                    outputs = [patch] if patch is not None else []
                elif any(is_m2_path(ref.path) for ref in group):
                    outputs = _export_m2(tree, top, group, translations=translations, root=root, result=result)
                elif (
                    any(is_nni_path(ref.path) or is_cpk_path(ref.path) or is_wad_path(ref.path) for ref in group)
                    or (title_id, top) in extra_members
                ):
                    outputs = _export_member_archive(
                        tree,
                        top,
                        group,
                        translations=translations,
                        root=root,
                        result=result,
                        extra=extra_members.get((title_id, top), {}),
                    )
                else:
                    original = tree.view.open(top).read_all()
                    data = _apply_group(original, group, translations, skip=1, result=result)
                    if group:
                        _verify_group(data, group, translations, skip=1, result=result)
                    if options.patch_fonts and (is_patchable_font_bundle(top) or top in options.font_files):
                        data = _patch_font_file(data, top, result)
                    extra = extra_patches.get((title_id, top))
                    if extra is not None:
                        try:
                            data = extra(data)
                        except NxError as exc:
                            raise ExportError(f"'{top}' değiştirilemedi: {exc.message}", exc.hint) from None
                    if data == original:
                        result.unchanged_files += 1
                        continue
                    changed_sizes.add(len(original))
                    if "/aa/" in f"/{top}":
                        addressables_changed = True
                    outputs = [(root / safe_relative_path(top), data)]
                for rel, data in outputs:
                    target = tmp / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    if target.read_bytes() != data:
                        raise ExportError(
                            f"'{rel.as_posix()}' diske doğru yazılamadı; disk dolu veya arızalı olabilir."
                        )
                    result.files.append(rel.as_posix())
            for title_id, found in derived.items():
                for path, data in found.files.items():
                    rel = _mod_root(options.layout, title_id, options.mod_name) / safe_relative_path(path)
                    target = tmp / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    result.files.append(rel.as_posix())
            _patch_catalogs(
                trees,
                changed_sizes,
                addressables_changed=addressables_changed,
                options=options,
                tmp=tmp,
                result=result,
            )
            for ref in {(r.title_id, r.format): r for r in refs.values()}.values():
                provider = getattr(plugin_for_kind(ref.format, ref.title_id), "exefs_patches", None)
                tree = trees.get(ref.title_id)
                if provider is None or tree is None or tree.code is None:
                    continue
                code = tree.code()
                if code is None:
                    continue
                try:
                    patches = provider(code)
                except NxError as exc:
                    result.warnings.append(f"Program yaması üretilemedi: {exc.message}")
                    continue
                for build_id, data in patches.items():
                    rel = exefs_patch_path(options.layout, ref.title_id, options.mod_name, build_id)
                    target = tmp / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    result.files.append(rel.as_posix())
        for title_id, added in sorted(options.extra_files.items()):
            root = _mod_root(options.layout, title_id, options.mod_name)
            for path, data in sorted(added.items()):
                rel = root / safe_relative_path(path)
                target = tmp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                if rel.as_posix() not in result.files:
                    result.files.append(rel.as_posix())
        for rel, data in support_files(list(refs.values()), options.layout, options.mod_name):
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            result.files.append(rel.as_posix())
        if not result.files:
            raise ExportError(
                "Hiçbir dosya değişmedi; çeviriler orijinal metinlerle aynı.",
                "Çeviri tablosunda gerçekten çevrilmiş satır olduğundan emin olun.",
            )
        if options.include_errors:
            dropped = sum(len(keys) for keys in result.dropped_keys.values())
            attempted = sum(len(keys) for keys in result.attempted_keys.values())
            result.rows_error_written = attempted - dropped
            result.rows_error_kept = result.rows_error - result.rows_error_written
        (tmp / INFO_FILE).write_text(_info_text(info, options, result), encoding="utf-8")
        ctx.check()
        if replace_old:
            # Eski mod önce yedeğe taşınır; yeni yerine konamazsa geri gelir, konunca silinir (kalıntı karışmaz).
            backup = dest.parent / f".{dest.name}.{uuid.uuid4().hex[:8]}.eski"
            os.replace(dest, backup)
            try:
                os.replace(tmp, dest)
            except BaseException:
                os.replace(backup, dest)
                raise
            shutil.rmtree(backup, ignore_errors=True)
        else:
            if dest.exists():
                dest.rmdir()
            os.replace(tmp, dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    ctx.report(len(groups), len(groups), "Mod oluşturuldu")
    return result


def _patch_catalogs(
    trees: Mapping[str, ContentTree],
    sizes: set[int],
    *,
    addressables_changed: bool,
    options: ExportOptions,
    tmp: Path,
    result: ExportResult,
) -> None:
    """Değiştirilen Addressables paketlerinin CRC'sini katalogda sıfırlar; kataloğu moda ekler."""
    found = False
    for title_id, tree in trees.items():
        for path in tree.view.files:
            if path.rsplit("/", 1)[-1] != "catalog.json":
                continue
            try:
                data = tree.view.open(path).read_all()
            except NxError as exc:
                result.warnings.append(f"Addressables kataloğu okunamadı: {exc.message}")
                continue
            if b'"m_ExtraDataString"' not in data:
                continue
            found = True
            try:
                patched, fixed = patch_catalog_crc(data, sizes)
                if not fixed:
                    continue
                # Yazmadan önce doğrula: aynı boyutlarla tekrar uygulanınca değişiklik kalmamalı.
                _check, again = patch_catalog_crc(patched, sizes)
                if again:
                    raise CatalogError("Addressables kataloğu doğrulanamadı.")
            except NxError as exc:
                result.warnings.append(
                    f"Addressables kataloğu düzeltilemedi: {exc.message} "
                    "Değiştirilen paketler CRC denetimi nedeniyle oyunda yüklenmeyebilir."
                )
                continue
            rel = _mod_root(options.layout, title_id, options.mod_name) / safe_relative_path(path)
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(patched)
            result.files.append(rel.as_posix())
            result.catalog_crc_fixes.extend(fixed)
    if not found and addressables_changed:
        result.warnings.append(
            "Addressables kataloğu (catalog.json) bulunamadı. Değiştirilen paketlerde CRC denetimi "
            "varsa oyun çeviriyi yüklemeyebilir."
        )


def _patch_font_file(data: bytes, path: str, result: ExportResult) -> bytes:
    """Bundle'daki TMP fontlarına eksik Türkçe harfleri ekler; sonucu rapora yazar."""
    try:
        out, patches = patch_fonts(data, skip=is_language_specific)
    except NxError as exc:
        raise ExportError(f"'{path}' fontları yamalanamadı: {exc.message}", exc.hint) from None
    name = path.rsplit("/", 1)[-1]
    partial = []
    for p in patches:
        missed = {c: why for c, why in p.skipped.items() if not why.startswith(("dinamik", FALLBACK_REASON))}
        detail = "; ".join(f"{c} ({why})" for c, why in missed.items())
        if p.added:
            line = f"{p.font} ({name}): {' '.join(p.added)}"
            if missed:
                line += " — eklenemeyen: " + detail
            result.font_patches.append(line)
        elif missed and all(why.startswith(_NO_BASE_LETTER) for why in missed.values()):
            # Harflerin türetileceği temel harfler (i, s, g …) fontta hiç yok: metin çizmeyen bir
            # yer tutucu/simge fontudur; uyarı verilmez, yalnızca bilgi dosyasına not düşülür.
            result.font_notes.append(f"{p.font} ({name}): temel Latin harfleri yok, metin fontu değil; atlandı")
            continue
        elif missed:
            result.font_notes.append(f"{p.font} ({name}): harf eklenemedi — {detail}")
        if missed:
            partial.append(f"{p.font} ({' '.join(missed)})")
    if partial:
        result.warnings.append(
            f"{name}: bazı fontlara bazı harfler eklenemedi: {', '.join(partial)}. Ayrıntı bilgi dosyasında."
        )
    return out


def _accept_soft(
    plugin: FormatPlugin,
    data: bytes,
    accepted: dict[str, str],
    pending: list[tuple[str, str]],
    check: Callable[[], None],
) -> dict[str, str]:
    """`accepted` çevirilerine eklenebilen en çok hatalı satırı bulur (ikili bölme); reddedilenler dışarıda kalır."""
    if not pending:
        return accepted
    check()
    trial = {**accepted, **dict(pending)}
    try:
        plugin.inject(data, trial)
    except NxError:
        if len(pending) == 1:
            return accepted
        mid = len(pending) // 2
        accepted = _accept_soft(plugin, data, accepted, pending[:mid], check)
        return _accept_soft(plugin, data, accepted, pending[mid:], check)
    return trial


def _inject_tolerant(
    plugin: FormatPlugin, data: bytes, translations: Mapping[str, str], path: str, result: ExportResult
) -> bytes:
    """`inject`; hatalı satırlar dışa aktarılırken eklentinin reddettiği hatalı satırlar orijinal bırakılır."""
    soft = result.soft_keys.get(path, frozenset())
    result.attempted_keys[path] = frozenset(k for k in translations if k in soft)
    # Yalnızca kod sırası farklı satırlar varken eklentinin sıra denetimi gevşetilir; sayı/tür farkı olan satırlar
    # zaten ayıklanmıştır, gevşetme başka bir şeyi geçirmez.
    relaxed = placeholders.tolerate_reorder() if result.reordered_keys.get(path) else nullcontext()
    with relaxed:
        try:
            return plugin.inject(data, translations)
        except NxError:
            pending = [(k, v) for k, v in translations.items() if k in soft]
            if not pending:
                raise
            result.cancel_check()
            # Hatalı olmayanlar tek başına da yazılamıyorsa sorun hatalı satırlarda değildir; hata olduğu gibi çıkar.
            base = {k: v for k, v in translations.items() if k not in soft}
            plugin.inject(data, base)
            accepted = _accept_soft(plugin, data, base, pending, result.cancel_check)
            result.dropped_keys[path] = frozenset(k for k, _v in pending if k not in accepted)
            return plugin.inject(data, accepted)


def _apply_group(
    data: bytes,
    group: list[TextFileRef],
    translations: Mapping[str, Mapping[str, str]],
    *,
    skip: int,
    result: ExportResult,
) -> bytes:
    for ref in group:
        plugin = plugin_for_kind(ref.format, ref.title_id)
        if plugin is None:
            raise ExportError(f"'{ref.path}' için format eklentisi yok ({ref.format}).")
        tr = translations[ref.path]
        inner = nested.split(ref.path)[skip:]

        def transform(d: bytes, p: FormatPlugin = plugin, t: Mapping[str, str] = tr, path: str = ref.path) -> bytes:
            return _inject_tolerant(p, d, t, path, result)

        try:
            data = nested.replace_inner(data, inner, transform)
        except OperationCancelled:
            raise
        except NxError as exc:
            raise ExportError(f"'{ref.path}' yazılamadı: {exc.message}", exc.hint) from None
    return data


def _verify_group(
    data: bytes,
    group: list[TextFileRef],
    translations: Mapping[str, Mapping[str, str]],
    *,
    skip: int,
    result: ExportResult,
) -> None:
    for ref in group:
        plugin = plugin_for_kind(ref.format, ref.title_id)
        assert plugin is not None
        inner = nested.split(ref.path)[skip:]
        try:
            got = {e.key: e.source for e in plugin.extract(nested.open_inner(data, inner))}
        except NxError as exc:
            raise ExportError(f"'{ref.path}' yazıldıktan sonra okunamadı: {exc.message}") from None
        dropped = result.dropped_keys.get(ref.path, frozenset())
        reordered = result.reordered_keys.get(ref.path, frozenset())
        wrong = [
            k
            for k, text in translations[ref.path].items()
            if k not in dropped
            and (
                placeholders.renumber(got.get(k, "")) != placeholders.renumber(text)
                if k in reordered
                else got.get(k) != text
            )
        ]
        if wrong:
            raise ContainerError(
                f"'{ref.path}' doğrulanamadı: {len(wrong)} metin beklenen değerde değil.",
                "Mod üretilmedi. Bu bir hatadır; log dosyasını geliştiriciyle paylaşın.",
            )


def _export_m2(
    tree: ContentTree,
    top: str,
    group: list[TextFileRef],
    *,
    translations: Mapping[str, Mapping[str, str]],
    root: Path,
    result: ExportResult,
) -> list[tuple[Path, bytes]]:
    """M2 arşivindeki değişen üyeleri gevşek dosya olarak, dizinden çıkarılmış girdileriyle verir.

    8 GB'lık veri dosyasına (`.bin`) dokunulmaz. Oyun, dizinde kaydı olmayan dosyayı dosya
    sisteminde (RomFS katmanında) arar; bu yüzden değişen üyelerin girdisi `.psb.m` dizininden
    çıkarılır ve üyenin kendisi (mdf kodlu) aynı yolda verilir. Cihazda doğrulandı (docs/formats/m2.md).
    """
    try:
        archive = MemberReader(tree.view, tree.code).m2(top)
    except NxError as exc:
        raise ExportError(f"'{top}' okunamadı: {exc.message}", exc.hint) from None
    by_member: dict[str, list[TextFileRef]] = {}
    for ref in group:
        by_member.setdefault(nested.split(ref.path)[1], []).append(ref)
    changed: dict[str, bytes] = {}
    for member, refs in sorted(by_member.items()):
        try:
            original = archive.read(member)
        except NxError as exc:
            raise ExportError(f"'{top}' içindeki '{member}' okunamadı: {exc.message}", exc.hint) from None
        data = _apply_group(original, refs, translations, skip=2, result=result)
        if data == original:
            result.unchanged_files += 1
            continue
        _verify_group(data, refs, translations, skip=2, result=result)
        encoded = m2.encode(data, member, archive.key)
        if m2.decode(encoded, member, archive.key) != data:
            raise ExportError(f"'{member}' arşiv biçimine doğru kodlanamadı.")
        changed[member] = encoded
    if not changed:
        return []
    index = archive.index_without(set(changed))
    check = m2.M2Archive(top, index, tree.view.open(m2.M2Archive.data_name(top)), archive.key)
    if set(check.entries) != set(archive.entries) - set(changed):
        raise ExportError(f"'{top}' dizini doğrulanamadı.")
    outputs = [(root / safe_relative_path(top), index)]
    outputs += [(root / safe_relative_path(member), blob) for member, blob in sorted(changed.items())]
    return outputs


def _export_member_archive(
    tree: ContentTree,
    top: str,
    group: list[TextFileRef],
    *,
    translations: Mapping[str, Mapping[str, str]],
    root: Path,
    result: ExportResult,
    extra: Mapping[str, bytes] | None = None,
) -> list[tuple[Path, bytes]]:
    """NNI (Ys Origin), CPK (Unicorn Overlord) veya WAD (Danganronpa) arşivini değişen üyeleriyle yeniden kurar.

    NNI: orijinal `.na` korunur, değişen üyeler sonuna eklenir; `.ni` dizini ve `.na` birlikte verilir.
    CPK: değişen dosyalar sıkıştırılmadan konmuş tüm arşiv verilir. WAD: tüm arşiv, üyeler aynı sırada.
    Hepsi yeniden açılıp doğrulanır.
    """
    reader = MemberReader(tree.view, tree.code)
    archive: nni.NniArchive | cpk.CpkFile | wad.WadArchive
    try:
        if top.lower().endswith(nni.INDEX_SUFFIX):
            archive = reader.nni(top)
        elif top.lower().endswith(wad.SUFFIX):
            archive = reader.wad(top)
        else:
            archive = reader.cpk(top)
    except NxError as exc:
        raise ExportError(f"'{top}' okunamadı: {exc.message}", exc.hint) from None
    by_member: dict[str, list[TextFileRef]] = {}
    for ref in group:
        by_member.setdefault(nested.split(ref.path)[1], []).append(ref)
    changed: dict[str, bytes] = {}
    for member, refs in sorted(by_member.items()):
        try:
            original = archive.read(member)
        except NxError as exc:
            raise ExportError(f"'{top}' içindeki '{member}' okunamadı: {exc.message}", exc.hint) from None
        data = _apply_group(original, refs, translations, skip=2, result=result)
        if data == original:
            result.unchanged_files += 1
            continue
        _verify_group(data, refs, translations, skip=2, result=result)
        changed[member] = data
    for member, data in sorted((extra or {}).items()):  # eklentilerin hazır ürettiği üyeler (ör. çevrilmiş resimler)
        try:
            same = archive.read(member) == data
        except NxError as exc:
            raise ExportError(f"'{top}' içindeki '{member}' okunamadı: {exc.message}", exc.hint) from None
        if same:
            result.unchanged_files += 1
        else:
            changed[member] = data
    if not changed:
        return []
    try:
        if isinstance(archive, nni.NniArchive):
            index, blob = archive.rebuild(changed)
            check: nni.NniArchive | cpk.CpkFile | wad.WadArchive = nni.NniArchive(top, index, MemoryStorage(blob))
            outputs = [
                (root / safe_relative_path(top), index),
                (root / safe_relative_path(nni.data_name(top)), blob),
            ]
        elif isinstance(archive, wad.WadArchive):
            built = archive.rebuild(changed)
            check = wad.WadArchive(MemoryStorage(built), top)
            outputs = [(root / safe_relative_path(top), built)]
        else:
            built = archive.rebuild(changed)
            check = cpk.CpkFile(MemoryStorage(built), top)
            outputs = [(root / safe_relative_path(top), built)]
        wrong = [m for m, data in changed.items() if check.read(m) != data]
    except NxError as exc:
        raise ExportError(f"'{top}' yeniden kurulamadı: {exc.message}", exc.hint) from None
    if wrong or set(check.entries) != set(archive.entries):
        raise ExportError(f"'{top}' arşivi doğrulanamadı.")
    return outputs


def patch_pak_name(top: str) -> str:
    """Yama pak'ının RomFS yolu: orijinalin yanında, adı `_P` ile biter (Unreal önceliği)."""
    folder, _, name = top.rpartition("/")
    stem = name[: -len(".pak")]
    if stem.endswith("_P"):
        stem = stem[:-2]
    return f"{folder}/{stem}_NXCeviri_P.pak" if folder else f"{stem}_NXCeviri_P.pak"


def _export_pak(
    tree: ContentTree,
    top: str,
    group: list[TextFileRef],
    *,
    translations: Mapping[str, Mapping[str, str]],
    root: Path,
    result: ExportResult,
) -> tuple[Path, bytes] | None:
    """Pak içindeki değişen dosyalardan bir yama pak'ı üretir; orijinal pak'a dokunulmaz."""
    try:
        pak = PakFile(tree.view.open(top), top)
    except NxError as exc:
        raise ExportError(f"'{top}' okunamadı: {exc.message}", exc.hint) from None
    by_member: dict[str, list[TextFileRef]] = {}
    for ref in group:
        by_member.setdefault(nested.split(ref.path)[1], []).append(ref)
    files: dict[str, bytes] = {}
    for member, refs in sorted(by_member.items()):
        try:
            original = pak.read(member)
        except NxError as exc:
            raise ExportError(f"'{top}' içindeki '{member}' okunamadı: {exc.message}", exc.hint) from None
        data = _apply_group(original, refs, translations, skip=2, result=result)
        if data == original:
            result.unchanged_files += 1
            continue
        _verify_group(data, refs, translations, skip=2, result=result)
        files[relative_to_mount(pak.mount_point, member)] = data
    if not files:
        return None
    built = build_patch_pak(pak.mount_point, files, pak.version)
    check = PakFile(MemoryStorage(built), "yama")
    for name, data in files.items():
        full = check._normalize(name)
        if check.read(full) != data:
            raise ExportError(f"Yama pak'ı doğrulanamadı: {name}")
    if f"{top[: -len('.pak')]}.sig" in tree.view.files:
        result.warnings.append(
            f"{top} imzalı (.sig dosyası var). Oyun imzasız yama pak'larını reddedebilir; böyle olursa çeviri görünmez."
        )
    return root / safe_relative_path(patch_pak_name(top)), built
