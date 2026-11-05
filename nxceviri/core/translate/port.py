"""Hazır çeviriyi (ör. oyunun topluluk Türkçe yaması) projeye aktarma.

Unity Localization kullanan oyunların topluluk yamaları genellikle İngilizce string tablosu
paketini Türkçe metinle değiştirir. Yamadaki tablolar oyunun tablolarıyla aynı adı ve aynı
satır kimliklerini (`m_Id`) taşıdığı için satırlar anahtarla birebir eşleşir ("Dialogue_en/123").

Yamadaki kontrol kodları (`<color=white>`, `{input_0}`) yalnızca sayı, tür ve sıra denetimi için
kullanılır; dışa aktarırken oyunun kendi özgün kodları geri konur. Kontrol kodu uyuşmayan satırlar
yazılmaz ve ayrıca raporlanır. Çeviriler "Makine" durumuyla yazılır: onayladığınız veya redakte ettiğiniz
satırlara asla dokunulmaz ve hâlâ gözden geçirmeniz gerektiği görünür kalır.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from nxceviri.core.errors import NxError
from nxceviri.core.formats.dmc1 import yama as dmc1_yama
from nxceviri.core.formats.mina import ycd
from nxceviri.core.formats.mina.plugin import table_key, tokenize
from nxceviri.core.formats.unity import UnityPlugin
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import Project, TranslationRow
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.status import Status

#: Çok büyük dosyalar (ses/doku paketleri) metin tablosu içermez; okunmaz.
_MAX_BUNDLE_BYTES = 256 * 1024 * 1024
#: Tablo adındaki dil soneki: "Dialogue_en/12" → "Dialogue/12".
_LANG_SUFFIX = re.compile(r"_[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,4})?(?=/)")


class PortError(NxError):
    """Hazır çeviri okunamadı veya uygulanamadı."""


@dataclass
class PortReport:
    found: int = 0  # yamada okunan metin sayısı
    matched: int = 0  # projedeki satırlarla eşleşen
    applied: int = 0  # projeye yazılan
    unchanged: int = 0  # zaten aynı çeviri olan
    protected: int = 0  # onaylı veya redakte olduğu için dokunulmayan
    identical_to_source: int = 0  # yazılanlardan kaynakla aynı olanlar (özel ad, sayı…)
    empty: int = 0  # yamada boş olan
    unmatched_rows: int = 0  # projede olup yamada karşılığı olmayan
    source_changed: int = 0  # yamanın çevirdiği özgün metin, bu oyun sürümünde değişmiş
    matched_by_text: int = 0  # kimliği tutmadığı halde özgün metni yamadakiyle birebir aynı olan
    code_problems: list[tuple[str, str, str]] = field(default_factory=list)  # (anahtar, kaynak, sorun)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReadyTranslations:
    """Yamadan okunan çeviriler: anahtar → metin (⟦n⟧ yer tutuculu)."""

    texts: dict[str, str]
    #: Anahtar → yamanın o satırı çevirirken dayandığı özgün metinler. Verilmişse satır yalnızca
    #: projedeki özgün metin bunlardan birine eşitse eşleşir (sürümler arasında kimlikler
    #: kayabilen biçimlerde yanlış satıra çeviri yazılmasını önler).
    sources: dict[str, frozenset[str]] | None = None
    #: Özgün metin → çeviri (yalnızca tek çevirisi olan metinler). Kimliği kaymış satırlar için ikinci şans.
    by_source: dict[str, str] | None = None
    #: Satırın yamadaki arama anahtarını verir (varsayılan: satırın kendi anahtarı). Anahtarları dosya
    #: konumuna bağlı olan biçimlerde (Devil May Cry: dosya adı + sıra) eşleşmeyi kurar.
    row_key: Callable[[TranslationRow], str] | None = None


def _normalized(key: str) -> str:
    return _LANG_SUFFIX.sub("", key, count=1)


def read_unity_translations(root: Path, ctx: TaskContext | None = None) -> dict[str, str]:
    """Klasördeki (veya tek) Unity paketlerinden metin tablolarını okur: anahtar → metin (⟦n⟧ yer tutuculu)."""
    ctx = ctx or TaskContext()
    if root.is_file():
        files = [root]
    elif root.is_dir():
        files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in (".bundle", ".assets", ""))
    else:
        raise PortError("Klasör bulunamadı.", "Çeviri yamasının bulunduğu klasörü seçin.")
    plugin = UnityPlugin()
    result: dict[str, str] = {}
    candidates = []
    for p in files:
        try:
            with p.open("rb") as fh:
                head = fh.read(64)
            if p.stat().st_size <= _MAX_BUNDLE_BYTES and plugin.detect(p.name, head):
                candidates.append(p)
        except OSError:
            continue
    for i, p in enumerate(candidates):
        ctx.report(i, len(candidates), f"Okunuyor: {p.name}")
        ctx.check()
        try:
            for entry in plugin.extract(p.read_bytes()):
                if entry.key.startswith("I2|"):
                    continue
                result[entry.key] = entry.source
        except NxError:
            continue  # metin tablosu olmayan paket (font, ses): atlanır
    ctx.report(len(candidates), len(candidates), "Okuma tamamlandı")
    if not result:
        raise PortError(
            "Seçilen klasörde Unity metin tablosu bulunamadı.",
            "Yama, oyunun “localization-string-tables-…” paketlerini içermelidir. Klasörün içindeki "
            "Data/StreamingAssets/aa/… klasörünü veya paketleri seçin.",
        )
    ctx.report(len(candidates), len(candidates), f"{len(result)} metin okundu")
    return result


def _mina_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir():
        raise PortError("Klasör bulunamadı.", "Çeviri yamasının bulunduğu klasörü seçin.")
    return sorted(p for p in root.rglob("*.yc") if p.is_file())


def is_mina_patch(root: Path) -> bool:
    """Klasörde (veya dosyada) Yacht Club YCD paketi var mı?"""
    for p in _mina_files(root) if root.exists() else []:
        try:
            with p.open("rb") as fh:
                if ycd.is_ycd(fh.read(4)):
                    return True
        except OSError:
            continue
    return False


def _extra_translations(root: Path) -> dict[str, str]:
    """Klasördeki `*.json` dosyaları: {"ui/anahtar": "çeviri"} biçiminde elle yazılmış ek çeviriler."""
    if not root.is_dir():
        return {}
    extra: dict[str, str] = {}
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PortError(
                f"'{path.name}' okunamadı: {exc}", 'Dosya {"anahtar": "çeviri"} biçiminde olmalı.'
            ) from None
        if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise PortError(f"'{path.name}' beklenen biçimde değil.", 'Dosya {"anahtar": "çeviri"} biçiminde olmalı.')
        extra.update(data)
    return extra


def read_mina_translations(root: Path, ctx: TaskContext | None = None) -> ReadyTranslations:
    """Mina the Hollower yamasındaki Türkçe tabloları okur.

    Yama, her dil tablosunun yeni bir kopyasını dosyanın sonuna ekler ve Türkçe metni
    İngilizce sütununa koyar; özgün kopyalar yerinde kalır. Aynı başlığa sahip tablolardan
    sonuncusu Türkçedir, öncekiler yamanın dayandığı İngilizce metni verir.
    """
    ctx = ctx or TaskContext()
    texts: dict[str, str] = {}
    sources: dict[str, set[str]] = {}
    files = [p for p in _mina_files(root) if p.stat().st_size <= _MAX_BUNDLE_BYTES]
    for i, path in enumerate(files):
        ctx.report(i, len(files), f"Okunuyor: {path.name}")
        ctx.check()
        data = path.read_bytes()
        if not ycd.is_ycd(data[:4]):
            continue
        by_header: dict[tuple[str, ...], list[ycd.Table]] = {}
        for table in ycd.read_tables(data):
            by_header.setdefault(table.header, []).append(table)
        for tables in by_header.values():
            if len(tables) < 2:
                continue  # Türkçe kopya yok: yama bu tabloya dokunmamış
            for original in tables[:-1]:
                seen: set[str] = set()
                column = original.column("English")
                for row in original.rows:
                    key = table_key(original.kind, row.cells[0], seen)
                    sources.setdefault(key, set()).add(tokenize(row.cells[column])[0])
            turkish = tables[-1]
            seen = set()
            column = turkish.column("English")
            for row in turkish.rows:
                key = table_key(turkish.kind, row.cells[0], seen)
                if row.cells[column].strip():
                    texts[key] = tokenize(row.cells[column])[0]
    ctx.report(len(files), len(files), f"{len(texts)} metin okundu")
    if not texts:
        raise PortError(
            "Seçilen klasörde Mina the Hollower çeviri tablosu bulunamadı.",
            "Yama, oyunun “global.pak.yc” ve “global_startup.pak.yc” dosyalarını içermelidir.",
        )
    candidates: dict[str, set[str]] = {}
    for key, text in texts.items():
        for source in sources.get(key, ()):
            candidates.setdefault(source, set()).add(text)
    by_source = {s: next(iter(v)) for s, v in candidates.items() if len(v) == 1}
    for key, text in _extra_translations(root).items():
        texts[key] = text  # elle yazılmış ek çeviri yamanınkinden önceliklidir ve kaynak denetimine tabi değildir
        sources.pop(key, None)
    return ReadyTranslations(texts, {k: frozenset(v) for k, v in sources.items()}, by_source)


def _dmc1_yama_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.name == "fsd_tr.yama" else []
    return sorted(root.rglob("fsd_tr.yama")) if root.is_dir() else []


def is_dmc1_patch(root: Path) -> bool:
    """Klasörde Devil May Cry HD Collection Türkçe yaması (`fsd_tr.yama`) var mı?"""
    return bool(_dmc1_yama_files(root))


def read_dmc1_translations(root: Path, ctx: TaskContext | None = None) -> ReadyTranslations:
    """PC (HD Collection) Türkçe yamasından DMC1 çevirilerini okur: `fsd_tr.yama` + `common.msg`."""
    ctx = ctx or TaskContext()
    texts: dict[str, str] = {}
    for yama_path in _dmc1_yama_files(root):
        ctx.check()
        for table in dmc1_yama.read_yama(yama_path.read_bytes()):
            for i, text in enumerate(table.texts):
                texts[f"{table.file}|{i}"] = text
        base = root if root.is_dir() else root.parent
        for msg in sorted(base.rglob("common.msg")):
            table = dmc1_yama.read_message_file(msg.read_bytes(), msg.name)
            for i, text in enumerate(table.texts):
                texts[f"{table.file}|{i}"] = text
        for status in sorted(base.rglob("st_init.dat")):
            table = dmc1_yama.read_status_file(status.read_bytes(), status.name)
            for i, text in enumerate(table.texts):
                texts[f"{table.file}|{i}"] = text
    if not texts:
        raise PortError("Yamada Devil May Cry mesaj tablosu bulunamadı.", "DMC_HD_Turkce_Yama klasörünü seçin.")
    ctx.report(1, 1, f"{len(texts)} metin okundu")
    return ReadyTranslations(texts, row_key=lambda r: f"{r.file.rsplit('/', 1)[-1]}|{r.key.rsplit('/', 1)[-1]}")


def read_ready_translations(root: Path, ctx: TaskContext | None = None) -> ReadyTranslations:
    """Klasörün yama türünü (Mina YCD, DMC1 yaması veya Unity metin tabloları) anlayıp çevirileri okur."""
    if is_dmc1_patch(root):
        return read_dmc1_translations(root, ctx)
    if is_mina_patch(root):
        return read_mina_translations(root, ctx)
    return ReadyTranslations(read_unity_translations(root, ctx))


def port_translations(
    project: Project, translations: Mapping[str, str] | ReadyTranslations, *, apply: bool = True
) -> PortReport:
    """Eşleşen satırlara çevirileri yazar. `apply=False` yalnızca ne olacağını sayar."""
    ready = translations if isinstance(translations, ReadyTranslations) else ReadyTranslations(dict(translations))
    texts = ready.texts
    report = PortReport(found=len(texts))
    by_norm: dict[str, str] = {}
    for key, value in texts.items():
        by_norm.setdefault(_normalized(key), value)
    changes: list[tuple[int, str]] = []
    for row in project.translation_rows():
        if not row.source.strip():
            continue
        key = ready.row_key(row) if ready.row_key is not None else row.key
        found = texts.get(key)
        text = found if found is not None else by_norm.get(_normalized(key))
        known = ready.sources.get(key) if ready.sources is not None else None
        stale = text is not None and known is not None and row.source not in known
        if (text is None or stale) and ready.by_source is not None and row.source in ready.by_source:
            text = ready.by_source[row.source]
            report.matched_by_text += 1
        elif text is None:
            report.unmatched_rows += 1
            continue
        elif stale:
            report.source_changed += 1
            continue
        report.matched += 1
        if not text.strip():
            report.empty += 1
            continue
        issues = placeholders.problems(row.source, text)
        if issues:
            report.code_problems.append((row.key, row.source, " ".join(issues)))
            continue
        if row.status in (Status.APPROVED, Status.REDACTED):
            report.protected += 1
            continue
        if row.translation == text:
            report.unchanged += 1
            continue
        changes.append((row.id, text))
        if text.strip() == row.source.strip():
            report.identical_to_source += 1
    report.applied = len(changes)
    if apply and changes:
        project.set_translations(changes, machine=True, job="import")
    return report
