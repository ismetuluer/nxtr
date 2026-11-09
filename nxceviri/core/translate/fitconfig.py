"""Metin sığdırma proje ayarları: kurallar, seçenekler, kod türü eşlemesi ve orijinalden sınır öğrenme.

Ayarlar proje veritabanındaki `settings` tablosunda iki anahtarda tutulur (şema göçü gerekmez):

- `fit_config`: tek JSON; `{"enabled": bool, "default": {...} | null, "files": {"yol": {...}},
  "groups": {"grup": {...}}, "keys": {"desen": {...}}, "options": {...}}` (`enabled` yoksa — eski projeler — açık
  sayılır; `groups` / `keys` yoksa grup / anahtar kuralı yoktur),
- `code_kinds`: etiket -> tür eşlemesi (`CodeKinds.dump`).

Bozuk veri çökertmez: uyarı günlüğe yazılır, ilgili girdi atlanır ya da varsayılan kullanılır.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import NamedTuple

from nxceviri.core.project import Project, TranslationRow, row_group
from nxceviri.core.translate.codekinds import KIND_OTHER, CodeKinds, KindOf
from nxceviri.core.translate.fit import DEFAULT_VARIABLE_WIDTH, FitRules, split_lines, split_pages, visible_width

log = logging.getLogger(__name__)

SETTING_CONFIG = "fit_config"
SETTING_KINDS = "code_kinds"

#: Kapsam seçicisinin değerleri: "" proje, düz yol dosya, `GROUP_PREFIX + ad` grup, `EACH_GROUP` "her grup ayrı".
GROUP_PREFIX = "grup:"
EACH_GROUP = "*gruplar"


@dataclass(frozen=True)
class FitConfig:
    """Bir projenin sığdırma ayarları: varsayılan kural, dosya ve grup kuralları, kod türleri, seçenekler.

    Öncelik: anahtar deseni > grup (`row_group` adı) > dosya > proje. Anahtar deseni `fnmatch` biçimindedir
    (`menu_*`, `*_title`), büyük/küçük harf ayırmaz; satırın anahtarına, Unity'de bağlamın son parçasına (okunur
    anahtar adı) bakılır; birden çok desen eşleşirse en uzunu (en özgülü) kazanır.

    `enabled` kapalıyken kurallar saklanır ama hiçbir dosyaya uygulanmaz.
    """

    default: FitRules | None = None
    per_file: dict[str, FitRules] = field(default_factory=dict)
    kinds: CodeKinds = field(default_factory=lambda: CodeKinds({}))
    enabled: bool = True
    per_group: dict[str, FitRules] = field(default_factory=dict)
    per_key: dict[str, FitRules] = field(default_factory=dict)

    def rules_for(self, file: str, group: str = "") -> FitRules | None:
        """Grup kuralı, yoksa dosya kuralı, yoksa varsayılan kural (hiçbiri yoksa ya da sığdırma kapalıysa `None`)."""
        if not self.enabled:
            return None
        return self.per_group.get(group) or self.per_file.get(file, self.default)

    def rules_for_row(self, row: TranslationRow) -> FitRules | None:
        """Satıra uygulanacak kural; denetim, düzeltme ve panel sayacı bu yolu kullanır."""
        if self.enabled and self.per_key:
            by_key = self.key_rules_for(row)
            if by_key is not None:
                return by_key
        group = row_group(row)
        if "/" not in row.context and row.file in self.per_file:
            group = ""  # bağlamdan gelmeyen (dosya adı) grup kuralı, dosyanın kendi kuralını ezmez
        return self.rules_for(row.file, group)

    def key_rules_for(self, row: TranslationRow) -> FitRules | None:
        """Satırın anahtarına uyan en özgül (en uzun) desenin kuralı; uyan desen yoksa `None`."""
        names = key_names(row)
        best = ""
        for pattern in self.per_key:
            if len(pattern) > len(best) and key_matches(pattern, names):
                best = pattern
            elif pattern != best and len(pattern) == len(best) and key_matches(pattern, names):
                best = min(best, pattern, key=str.casefold)  # eşit uzunlukta sonuç sıraya bağlı olmasın
        return self.per_key[best] if best else None

    def kind_of_row(self, row: TranslationRow) -> KindOf:
        """Satırın `⟦n⟧` kod numarasından (1 tabanlı) türe çeviren işlev; aralık dışı numara `KIND_OTHER` olur."""
        return _kind_of_labels(row.code_labels, self.kinds)


def key_names(row: TranslationRow) -> tuple[str, ...]:
    """Anahtar desenlerinin denendiği adlar (küçük harfe çevrilmiş): satır anahtarı ve bağlamın son parçası."""
    names = [row.key.casefold()]
    if "/" in row.context:
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


class _Parsed(NamedTuple):
    default: FitRules | None
    per_file: dict[str, FitRules]
    per_group: dict[str, FitRules]
    per_key: dict[str, FitRules]
    enabled: bool


def _parse_config(text: str) -> _Parsed:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("Sığdırma ayarı okunamadı, varsayılanlar kullanılıyor: %s", exc)
        return _Parsed(None, {}, {}, {}, True)
    if not isinstance(data, dict):
        log.warning("Sığdırma ayarı bir sözlük değil, varsayılanlar kullanılıyor.")
        return _Parsed(None, {}, {}, {}, True)
    default = _parse_rules("varsayılan", data["default"]) if data.get("default") is not None else None
    per_file = _parse_rule_map(data.get("files", {}), "Dosya")
    per_group = _parse_rule_map(data.get("groups", {}), "Grup")
    per_key = _parse_rule_map(data.get("keys", {}), "Anahtar")
    # Eski projelerdeki "options" (üç temizlik seçeneği) yok sayılır: artık düzeltme türleri olarak seçilir.
    return _Parsed(default, per_file, per_group, per_key, _parse_enabled(data))


def load_config(project: Project) -> FitConfig:
    """Projeden sığdırma ayarlarını okur; ayar yoksa sessizce, bozuksa uyarıyla varsayılan döner."""
    config_text = project.setting(SETTING_CONFIG)
    kinds_text = project.setting(SETTING_KINDS)
    parsed = _parse_config(config_text) if config_text else _Parsed(None, {}, {}, {}, True)
    kinds = CodeKinds.load(kinds_text) if kinds_text else CodeKinds({})
    return FitConfig(parsed.default, parsed.per_file, kinds, parsed.enabled, parsed.per_group, parsed.per_key)


def _rules_json(rules: FitRules) -> dict[str, int]:
    return {"width": rules.width, "max_lines": rules.max_lines, "variable_width": rules.variable_width}


def save_config(project: Project, config: FitConfig) -> None:
    """Sığdırma ayarlarını projeye yazar."""
    data = {
        "enabled": config.enabled,
        "default": None if config.default is None else _rules_json(config.default),
        "files": {path: _rules_json(rules) for path, rules in config.per_file.items()},
        "groups": {group: _rules_json(rules) for group, rules in config.per_group.items()},
        "keys": {pattern: _rules_json(rules) for pattern, rules in config.per_key.items()},
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
        if "/" in r.context:
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
        explicit = any("/" in r.context for r in members)
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
