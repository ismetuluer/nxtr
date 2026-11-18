"""Metin sığdırma proje ayarları: kurallar, seçenekler, kod türü eşlemesi ve orijinalden sınır öğrenme.

Ayarlar proje veritabanındaki `settings` tablosunda iki anahtarda tutulur (şema göçü gerekmez):

- `fit_config`: tek JSON; `{"enabled": bool, "default": {...} | null, "files": {"yol": {...}},
  "groups": {"grup": {...}}, "keys": {"desen": {...}}, "options": {...}, "widths": {...}}` (`enabled` yoksa — eski
  projeler — açık sayılır; `groups` / `keys` yoksa grup / anahtar kuralı yoktur). `widths` fontla genişlik denetiminin
  kapsam ayarlarıdır (`WidthRules`): `{"default": {...}, "files": {...}, "groups": {...}, "keys": {...}}`, her girdi
  `{"enabled": bool, "tolerance": 0.15, "box": "group" | "row"}`; yalnızca bir girdi varken yazılır (eski projelerde
  yoktur, denetim kapalıdır). Karakter sınırından bağımsızdır: kapsam yalnızca genişlik denetimi taşıyabilir;
- `code_kinds`: etiket -> tür eşlemesi (`CodeKinds.dump`).

Bozuk veri çökertmez: uyarı günlüğe yazılır, ilgili girdi atlanır ya da varsayılan kullanılır.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import NamedTuple

from nxceviri.core.project import Project, TranslationRow, in_collection, row_group
from nxceviri.core.translate.codekinds import KIND_OTHER, CodeKinds, KindOf
from nxceviri.core.translate.fit import DEFAULT_VARIABLE_WIDTH, FitRules, split_lines, split_pages, visible_width
from nxceviri.core.translate.widths import DEFAULT_TOLERANCE

log = logging.getLogger(__name__)

SETTING_CONFIG = "fit_config"
SETTING_KINDS = "code_kinds"

#: Kapsam seçicisinin değerleri: "" proje, düz yol dosya, `GROUP_PREFIX + ad` grup, `EACH_GROUP` "her grup ayrı".
GROUP_PREFIX = "grup:"
EACH_GROUP = "*gruplar"
#: Genişlik kutusunun kapsam kimliğinde anahtar deseni öneki (proje "", dosya düz yol, grup `GROUP_PREFIX`).
KEY_PREFIX = "anahtar:"

#: Genişlik denetiminde kutu: kapsamdaki en geniş tek satırlı orijinal ya da satırın kendi orijinali.
BOX_GROUP = "group"
BOX_ROW = "row"
BOX_MODES = (BOX_GROUP, BOX_ROW)
#: Kabul edilen en büyük tolerans (%500); üstü bozuk veri sayılır.
MAX_TOLERANCE = 5.0


@dataclass(frozen=True)
class WidthRules:
    """Bir kapsamın fontla genişlik denetimi ayarı (karakter sınırından bağımsız; `FitRules` gerekmez).

    `enabled` kapalı girdi, üst kapsamın açık ayarını o kapsamda geçersiz kılar. `tolerance`: kutunun ne kadar
    aşılabileceği (0.15 = %15). `box`: `BOX_GROUP` (kapsamdaki en geniş orijinal) ya da `BOX_ROW` (satırın kendisi).
    """

    enabled: bool = True
    tolerance: float = DEFAULT_TOLERANCE
    box: str = BOX_GROUP


@dataclass(frozen=True)
class FitConfig:
    """Bir projenin sığdırma ayarları: varsayılan kural, dosya ve grup kuralları, kod türleri, seçenekler.

    Öncelik: anahtar deseni > grup (`row_group` adı) > dosya > proje. Anahtar deseni `fnmatch` biçimindedir
    (`menu_*`, `*_title`), büyük/küçük harf ayırmaz; satırın anahtarına, koleksiyonlu biçimlerde (Unity, Unreal)
    bağlamın son parçasına (okunur anahtar adı) bakılır; birden çok desen eşleşirse en uzunu (en özgülü) kazanır.

    `enabled` kapalıyken kurallar saklanır ama hiçbir dosyaya uygulanmaz.
    """

    default: FitRules | None = None
    per_file: dict[str, FitRules] = field(default_factory=dict)
    kinds: CodeKinds = field(default_factory=lambda: CodeKinds({}))
    enabled: bool = True
    per_group: dict[str, FitRules] = field(default_factory=dict)
    per_key: dict[str, FitRules] = field(default_factory=dict)
    #: Fontla genişlik denetimi: kapsam başına ayrı ayar (hiçbiri yoksa kapalı); öncelik karakter kuralıyla aynı.
    width_default: WidthRules | None = None
    width_files: dict[str, WidthRules] = field(default_factory=dict)
    width_groups: dict[str, WidthRules] = field(default_factory=dict)
    width_keys: dict[str, WidthRules] = field(default_factory=dict)

    def rules_for(self, file: str, group: str = "") -> FitRules | None:
        """Grup kuralı, yoksa dosya kuralı, yoksa varsayılan kural (hiçbiri yoksa ya da sığdırma kapalıysa `None`)."""
        if not self.enabled:
            return None
        return self.per_group.get(group) or self.per_file.get(file, self.default)

    def rules_for_row(self, row: TranslationRow) -> FitRules | None:
        """Satıra uygulanacak kural; denetim, düzeltme ve panel sayacı bu yolu kullanır."""
        if not self.enabled:
            return None
        return _scoped(row, self.default, self.per_file, self.per_group, self.per_key)[0]

    def key_rules_for(self, row: TranslationRow) -> FitRules | None:
        """Satırın anahtarına uyan en özgül (en uzun) desenin kuralı; uyan desen yoksa `None`."""
        best = best_pattern(self.per_key, row)
        return self.per_key[best] if best else None

    @property
    def has_width_rules(self) -> bool:
        """Herhangi bir kapsamda açık genişlik denetimi var mı (sığdırma kapalıysa yok sayılır)."""
        entries = [self.width_default, *self.width_files.values(), *self.width_groups.values()]
        entries += self.width_keys.values()
        return self.enabled and any(e is not None and e.enabled for e in entries)

    def width_for_row(self, row: TranslationRow) -> tuple[WidthRules, str] | None:
        """Satırın genişlik denetimi ayarı ve kapsam kimliği (kutu bu kimlikle paylaşılır); kapalıysa `None`.

        Öncelik karakter kuralıyla aynıdır (anahtar deseni > grup > dosya > proje); en özgül girdi kapalıysa satır
        denetlenmez. Kimlik: proje "", dosya yolu, grup `GROUP_PREFIX + ad`, desen `KEY_PREFIX + desen`.
        """
        if not self.enabled:
            return None
        found, scope = _scoped(row, self.width_default, self.width_files, self.width_groups, self.width_keys)
        return (found, scope) if found is not None and found.enabled else None

    def kind_of_row(self, row: TranslationRow) -> KindOf:
        """Satırın `⟦n⟧` kod numarasından (1 tabanlı) türe çeviren işlev; aralık dışı numara `KIND_OTHER` olur."""
        return _kind_of_labels(row.code_labels, self.kinds)


def best_pattern(patterns: Collection[str], row: TranslationRow) -> str:
    """Satırın anahtarına uyan en özgül (en uzun) desen; uyan yoksa "" (eşit uzunlukta sonuç sıraya bağlı olmaz)."""
    if not patterns:
        return ""
    names = key_names(row)
    best = ""
    for pattern in patterns:
        if len(pattern) > len(best) and key_matches(pattern, names):
            best = pattern
        elif pattern != best and len(pattern) == len(best) and key_matches(pattern, names):
            best = min(best, pattern, key=str.casefold)
    return best


def _scoped[T](
    row: TranslationRow, default: T | None, files: Mapping[str, T], groups: Mapping[str, T], keys: Mapping[str, T]
) -> tuple[T | None, str]:
    """Kapsam önceliği (karakter kuralı ve genişlik ayarı ortak): (değer, kapsam kimliği)."""
    pattern = best_pattern(keys, row)
    if pattern:
        return keys[pattern], KEY_PREFIX + pattern
    if not in_collection(row) and row.file in files:
        # bağlamdan gelmeyen (dosya adı) grup kuralı, dosyanın kendi kuralını ezmez
        return files[row.file], row.file
    group = row_group(row)
    if group in groups:
        return groups[group], GROUP_PREFIX + group
    if row.file in files:
        return files[row.file], row.file
    return default, ""


def key_names(row: TranslationRow) -> tuple[str, ...]:
    """Anahtar desenlerinin denendiği adlar (küçük harfe çevrilmiş): satır anahtarı; koleksiyonlu biçimlerde
    (Unity, Unreal: bağlam `koleksiyon/…/anahtar`) ayrıca bağlamın son parçası. Diğer biçimlerde bağlam serbest
    bir açıklamadır, son parçası anahtar sayılmaz."""
    names = [row.key.casefold()]
    if in_collection(row):
        tail = row.context.rsplit("/", 1)[-1].casefold()
        if tail and tail not in names:
            names.append(tail)
    return tuple(names)


def key_matches(pattern: str, names: Sequence[str]) -> bool:
    """`pattern` (büyük/küçük harf ayırmaz) adlardan birine uyar mı."""
    folded = pattern.casefold()
    return any(fnmatchcase(name, folded) for name in names)


def _kind_of_labels(labels: Sequence[str], kinds: CodeKinds) -> KindOf:
    def kind_of(n: int) -> str:
        if 0 < n <= len(labels):
            return kinds.kind_of(labels[n - 1])
        return KIND_OTHER

    return kind_of


def _parse_rules(name: str, data: object) -> FitRules | None:
    if not isinstance(data, dict):
        log.warning("Sığdırma kuralı (%s) bir sözlük değil, atlandı.", name)
        return None
    width = data.get("width")
    max_lines = data.get("max_lines")
    variable_width = data.get("variable_width", DEFAULT_VARIABLE_WIDTH)
    if (
        not isinstance(width, int)
        or not isinstance(max_lines, int)
        or not isinstance(variable_width, int)
        or isinstance(width, bool)
        or isinstance(max_lines, bool)
        or isinstance(variable_width, bool)
    ):
        log.warning("Sığdırma kuralı (%s) sayı içermiyor, atlandı.", name)
        return None
    if width < 1 or max_lines < 1 or variable_width < 0:
        log.warning("Sığdırma kuralı (%s) geçersiz değer içeriyor, atlandı.", name)
        return None
    return FitRules(width, max_lines, variable_width)


def _parse_enabled(data: dict[str, object]) -> bool:
    value = data.get("enabled", True)
    if isinstance(value, bool):
        return value
    log.warning("Sığdırma açık/kapalı bilgisi doğru/yanlış değil, açık sayılıyor.")
    return True


def _parse_rule_map(data: object, what: str) -> dict[str, FitRules]:
    if not isinstance(data, dict):
        log.warning("%s kuralları bir sözlük değil, atlandı.", what)
        return {}
    rules_by_name: dict[str, FitRules] = {}
    for name, raw in data.items():
        rules = _parse_rules(str(name), raw)
        if rules is not None:
            rules_by_name[str(name)] = rules
    return rules_by_name


def _parse_width(name: str, data: object) -> WidthRules | None:
    """Tek genişlik ayarı; bozuk alan (yanlış tür, aralık dışı tolerans, bilinmeyen kutu) girdiyi uyarıyla atlatır."""
    if not isinstance(data, dict):
        log.warning("Genişlik ayarı (%s) bir sözlük değil, atlandı.", name)
        return None
    enabled = data.get("enabled", True)
    tolerance = data.get("tolerance", DEFAULT_TOLERANCE)
    box = data.get("box", BOX_GROUP)
    if not isinstance(enabled, bool):
        log.warning("Genişlik ayarı (%s) açık/kapalı bilgisi doğru/yanlış değil, atlandı.", name)
        return None
    if not isinstance(tolerance, int | float) or isinstance(tolerance, bool) or not 0 <= tolerance <= MAX_TOLERANCE:
        log.warning("Genişlik ayarı (%s) geçersiz tolerans içeriyor, atlandı.", name)
        return None
    if box not in BOX_MODES:
        log.warning("Genişlik ayarı (%s) bilinmeyen kutu türü içeriyor (%r), atlandı.", name, box)
        return None
    return WidthRules(enabled, float(tolerance), str(box))


def _parse_width_map(data: object, what: str) -> dict[str, WidthRules]:
    if not isinstance(data, dict):
        log.warning("%s genişlik ayarları bir sözlük değil, atlandı.", what)
        return {}
    found: dict[str, WidthRules] = {}
    for name, raw in data.items():
        rules = _parse_width(str(name), raw)
        if rules is not None:
            found[str(name)] = rules
    return found


class _Widths(NamedTuple):
    default: WidthRules | None
    files: dict[str, WidthRules]
    groups: dict[str, WidthRules]
    keys: dict[str, WidthRules]


def _parse_widths(data: object) -> _Widths:
    """`widths` bölümü; yoksa (eski proje) boş, bozuksa uyarıyla boş."""
    if data is None:
        return _Widths(None, {}, {}, {})
    if not isinstance(data, dict):
        log.warning("Genişlik ayarları bir sözlük değil, atlandı.")
        return _Widths(None, {}, {}, {})
    raw_default = data.get("default")
    return _Widths(
        _parse_width("varsayılan", raw_default) if raw_default is not None else None,
        _parse_width_map(data.get("files", {}), "Dosya"),
        _parse_width_map(data.get("groups", {}), "Grup"),
        _parse_width_map(data.get("keys", {}), "Anahtar"),
    )


class _Parsed(NamedTuple):
    default: FitRules | None
    per_file: dict[str, FitRules]
    per_group: dict[str, FitRules]
    per_key: dict[str, FitRules]
    enabled: bool
    widths: _Widths


_EMPTY = _Parsed(None, {}, {}, {}, True, _Widths(None, {}, {}, {}))


def _parse_config(text: str) -> _Parsed:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("Sığdırma ayarı okunamadı, varsayılanlar kullanılıyor: %s", exc)
        return _EMPTY
    if not isinstance(data, dict):
        log.warning("Sığdırma ayarı bir sözlük değil, varsayılanlar kullanılıyor.")
        return _EMPTY
    default = _parse_rules("varsayılan", data["default"]) if data.get("default") is not None else None
    per_file = _parse_rule_map(data.get("files", {}), "Dosya")
    per_group = _parse_rule_map(data.get("groups", {}), "Grup")
    per_key = _parse_rule_map(data.get("keys", {}), "Anahtar")
    # Eski projelerdeki "options" (üç temizlik seçeneği) yok sayılır: artık düzeltme türleri olarak seçilir.
    return _Parsed(default, per_file, per_group, per_key, _parse_enabled(data), _parse_widths(data.get("widths")))


def load_config(project: Project) -> FitConfig:
    """Projeden sığdırma ayarlarını okur; ayar yoksa sessizce, bozuksa uyarıyla varsayılan döner."""
    config_text = project.setting(SETTING_CONFIG)
    kinds_text = project.setting(SETTING_KINDS)
    parsed = _parse_config(config_text) if config_text else _EMPTY
    kinds = CodeKinds.load(kinds_text) if kinds_text else CodeKinds({})
    widths = parsed.widths
    return FitConfig(
        parsed.default,
        parsed.per_file,
        kinds,
        parsed.enabled,
        parsed.per_group,
        parsed.per_key,
        width_default=widths.default,
        width_files=dict(widths.files),
        width_groups=dict(widths.groups),
        width_keys=dict(widths.keys),
    )


def _rules_json(rules: FitRules) -> dict[str, int]:
    return {"width": rules.width, "max_lines": rules.max_lines, "variable_width": rules.variable_width}


def _width_json(rules: WidthRules) -> dict[str, object]:
    return {"enabled": rules.enabled, "tolerance": rules.tolerance, "box": rules.box}


def save_config(project: Project, config: FitConfig) -> None:
    """Sığdırma ayarlarını projeye yazar (genişlik ayarı yoksa `widths` yazılmaz: JSON eski biçimle aynı kalır)."""
    data: dict[str, object] = {
        "enabled": config.enabled,
        "default": None if config.default is None else _rules_json(config.default),
        "files": {path: _rules_json(rules) for path, rules in config.per_file.items()},
        "groups": {group: _rules_json(rules) for group, rules in config.per_group.items()},
        "keys": {pattern: _rules_json(rules) for pattern, rules in config.per_key.items()},
    }
    if config.width_default is not None or config.width_files or config.width_groups or config.width_keys:
        data["widths"] = {
            "default": None if config.width_default is None else _width_json(config.width_default),
            "files": {path: _width_json(rules) for path, rules in config.width_files.items()},
            "groups": {group: _width_json(rules) for group, rules in config.width_groups.items()},
            "keys": {pattern: _width_json(rules) for pattern, rules in config.width_keys.items()},
        }
    project.set_setting(SETTING_CONFIG, json.dumps(data, ensure_ascii=False, sort_keys=True))
    project.set_setting(SETTING_KINDS, config.kinds.dump())


def learn_rules(
    rows: Sequence[TranslationRow], kinds: CodeKinds, variable_width: int = DEFAULT_VARIABLE_WIDTH
) -> FitRules | None:
    """Orijinal metinlerden sınır öğrenir: en uzun satırın görünen uzunluğu ve bir sayfadaki en çok satır.

    Kaynağı boş olan satırlar yok sayılır; ölçülecek metin yoksa `None` döner.
    """
    width = 0
    max_lines = 0
    measured = False
    for row in rows:
        if not row.source:
            continue
        measured = True
        kind_of = _kind_of_labels(row.code_labels, kinds)
        rules = FitRules(1, 1, variable_width)
        for page, _separator in split_pages(row.source, kind_of):
            lines = split_lines(page, kind_of)
            max_lines = max(max_lines, len(lines))
            width = max([width, *(visible_width(line, kind_of, rules) for line in lines)])
    if not measured:
        return None
    return FitRules(max(width, 1), max(max_lines, 1), variable_width)


def separate_groups(rows: Sequence[TranslationRow]) -> list[str]:
    """Ayrı kapsam olarak gösterilecek ve öğrenilecek gruplar: bağlamdan gelenler (ör. Unity tablosu) ve birden çok
    dosyada geçenler. Yalnızca tek dosyanın adından ibaret grup, dosya kapsamıyla aynı şeydir; sayılmaz."""
    files: dict[str, set[str]] = {}
    explicit: set[str] = set()
    for r in rows:
        group = row_group(r)
        files.setdefault(group, set()).add(r.file)
        if in_collection(r):
            explicit.add(group)
    return sorted(g for g, paths in files.items() if g in explicit or len(paths) > 1)


def learn_group_rules(rows: Sequence[TranslationRow], config: FitConfig) -> dict[str, FitRules]:
    """Her grubun sınırını kendi orijinal metinlerinden öğrenir; yeni grup kuralları sözlüğünü döndürür.

    Öğrenilen sınır grubun üst kapsamıyla (dosya kuralı, yoksa proje kuralı) aynıysa o grup için kural yazılmaz
    (varsa eski grup kuralı silinir). Ölçülecek metni olmayan grupların ve satırlarda hiç geçmeyen grupların
    mevcut kuralı korunur. Değişken genişliği üst kapsamdan, yoksa projeden alınır.

    Yalnızca gerçek gruplar öğrenilir (`separate_groups`): tek dosyanın adından ibaret grup dosya kapsamıdır ve
    dosya kuralını ezmemesi için kural yazılmaz (eski projelerden kalan böyle kural silinir). Bağlamsız grubun tüm
    dosyalarının kendi kuralı varsa o grup için de kural yazılmaz.
    """
    by_group: dict[str, list[TranslationRow]] = {}
    for row in rows:
        by_group.setdefault(row_group(row), []).append(row)
    real = set(separate_groups(rows))
    result = dict(config.per_group)
    for group, members in by_group.items():
        if group not in real:
            result.pop(group, None)
            continue
        explicit = any(in_collection(r) for r in members)
        if not explicit and all(r.file in config.per_file for r in members):
            result.pop(group, None)
            continue
        parents = {config.per_file.get(r.file, config.default) for r in members}
        parent = next(iter(parents)) if len(parents) == 1 else None
        base = parent or config.default
        learned = learn_rules(members, config.kinds, base.variable_width if base else DEFAULT_VARIABLE_WIDTH)
        if learned is None:
            continue
        if parents == {learned}:
            result.pop(group, None)
        else:
            result[group] = learned
    return result
