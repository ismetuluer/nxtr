"""Unity format eklentisi: Unity Localization string tabloları ve I2 Localization kaynakları.

Unity'nin resmi yerelleştirme paketi (com.unity.localization) metinleri AssetBundle'lar
içindeki `StringTable` MonoBehaviour'larında saklar:

- `StringTable`: `m_Name` (ör. "Dialogue_en"), `m_LocaleId.m_Code` ("en"),
  `m_SharedData` (anahtar adlarının durduğu `SharedTableData`'ya işaretçi),
  `m_TableData[] = {m_Id (SInt64), m_Localized (string), m_Metadata}`.
- `SharedTableData`: `m_TableCollectionName` ve `m_Entries[] = {m_Id, m_Key}`; genellikle
  ayrı bir "localization-assets-shared" bundle'ındadır.

Okuma/yazma UnityPy ile, bundle'daki tip ağacı (typetree) üzerinden yapılır; oyunun kodunu
çözmek gerekmez. Metindeki TextMeshPro zengin metin etiketleri (`<b>`, `<color=…>`,
`<sprite …>`) ve Smart String değişkenleri (`{0}`, `{input_0}`) kontrol kodu sayılır.

I2 Localization kaynakları (`i2.py`) tüm dilleri tek nesnede tutar ve çoğunlukla tip ağacı
silinmiş `resources.assets` içindedir; ham bayttan çözülür. Kullanıcının seçtiği kaynak dilin
sütunu aktarılır (seçim yoksa İngilizce) ve Türkçe aynı sütuna yazılır.

TextAsset olarak saklanan düz metin yerelleştirmesi (`loctext.py`): SRT altyazıları (dil, varlık
adındaki `[en]` etiketinden) ve dil sütunlu TSV tabloları (`es`, `en`, `fr` … sütunları). Tüm
diller aynı dosyadadır; kaynak dilin sütunu/altyazısı aktarılır, Türkçe aynı yere yazılır.

Donkey Kong Country Returns HD'nin `Localization` nesnesi de tip ağacı silinmiş `resources.assets` içindedir ve
bir `[SerializeReference]` kayıt defteridir (`dklocal.py`); İngilizce yuva aktarılır, Türkçe aynı yuvaya yazılır.

Geri yazma: yalnızca değişen tablolar yeniden serileştirilir; bundle orijinal sıkıştırma
ayarlarıyla kaydedilir ve döndürülmeden önce yeniden okunarak doğrulanır. Hiçbir metin
değişmediyse orijinal baytlar aynen döner. Ayrıntılar: docs/formats/unity.md
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

import UnityPy
from UnityPy.files import BundleFile

from nxceviri.core.formats.base import SOURCE_LANGUAGE, Context, ControlCode, FormatError, TextEntry
from nxceviri.core.formats.detection import is_unity_serialized
from nxceviri.core.formats.unity import dklocal, i2, locoliser, loctext
from nxceviri.core.languages import same_language
from nxceviri.core.translate import markup, placeholders

log = logging.getLogger(__name__)

BUNDLE_MAGIC = b"UnityFS\0"

_TAG_RE = re.compile(r"</?[A-Za-z#][^<>\n]{0,200}>")
_SIMPLE_TAGS = {
    "b": "Kalın",
    "i": "İtalik",
    "u": "Altı çizili",
    "s": "Üstü çizili",
    "color": "Renk",
    "size": "Yazı boyutu",
    "font": "Yazı tipi",
    "material": "Malzeme",
    "mark": "Vurgu",
    "align": "Hizalama",
    "link": "Bağlantı",
    "style": "Stil",
    "sup": "Üst simge",
    "sub": "Alt simge",
}


#: Metin içinde düz yazı olarak duran satır sonu (ters bölü + n); gerçek satır sonu değildir.
_LITERAL_NEWLINE = "\\n"


def _tag_label(tag: str) -> str:
    if tag == _LITERAL_NEWLINE:
        return "Satır sonu"
    if tag.startswith("{"):
        return f"Değişken {tag}" if len(tag) <= 40 else "Değişken / biçim ifadesi"
    m = re.match(r"<(/?)([A-Za-z#]+)", tag)
    if not m:
        return f"Biçim etiketi {tag}"
    closing, name = m.group(1) == "/", m.group(2).lower()
    if name == "sprite":
        return "Simge (sprite)"
    if name in ("br",):
        return "Satır sonu"
    base = _SIMPLE_TAGS.get(name)
    if base is None:
        return f"Biçim etiketi <{'/' if closing else ''}{name}>"
    return f"{base} sonu" if closing else f"{base} başı"


def tokenize(text: str, literals: tuple[str, ...] = ()) -> tuple[str, tuple[ControlCode, ...]]:
    """Metni yer tutuculu biçime çevirir: TMP etiketleri ve Smart String değişkenleri ⟦n⟧ olur."""
    return markup.tokenize(text, _TAG_RE, _tag_label, literals)


def detokenize(display: str, codes: tuple[ControlCode, ...]) -> str:
    return markup.detokenize(display, codes)


def _load(data: bytes) -> Any:
    try:
        return UnityPy.load(data)
    except Exception as exc:  # UnityPy her tür bozuklukta farklı istisna fırlatır
        raise FormatError(f"Unity dosyası açılamadı ({type(exc).__name__}).") from None


def _has_typetree(obj: Any) -> bool:
    """Tip ağacı silinmiş dosyalarda (ör. resources.assets) MonoBehaviour alanları adla okunamaz."""
    return bool(getattr(obj.assets_file, "_enable_type_tree", True))


def _read(obj: Any) -> dict[str, Any] | None:
    if not _has_typetree(obj):
        return None
    try:
        tree = obj.read_typetree()
    except Exception as exc:
        log.debug("MonoBehaviour okunamadı (path_id=%s): %s", getattr(obj, "path_id", "?"), type(exc).__name__)
        return None
    return tree if isinstance(tree, dict) else None


_GUID_RE = re.compile(r"[0-9a-f]{32}")


def _is_string_table(tree: dict[str, Any]) -> bool:
    data = tree.get("m_TableData")
    if not (
        isinstance(data, list)
        and isinstance(tree.get("m_LocaleId"), dict)
        and all(isinstance(e, dict) and "m_Id" in e and isinstance(e.get("m_Localized"), str) for e in data)
    ):
        return False
    # AssetTable (font, görsel, ses başvuruları) StringTable ile aynı yapıdadır; değerleri
    # metin değil, varlık GUID'leridir. Tüm dolu değerleri GUID olan tablo metin tablosu sayılmaz.
    values = [e["m_Localized"] for e in data if e["m_Localized"]]
    return not values or not all(_GUID_RE.fullmatch(v) for v in values)


def _tables(env: Any) -> list[tuple[Any, dict[str, Any]]]:
    tables = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = _read(obj)
        if tree is not None and _is_string_table(tree):
            tables.append((obj, tree))
    return tables


def _entry_key(tree: dict[str, Any], entry: dict[str, Any]) -> str:
    return f"{tree.get('m_Name', '')}/{entry['m_Id']}"


#: I2 girdilerinin anahtar öneki; StringTable anahtarlarıyla ("<tablo>/<id>") karışmaz.
_I2_PREFIX = "I2|"
#: I2 kaynağı olamayacak kadar küçük nesneler hiç denenmez.
_I2_MIN_SIZE = 64


def _i2_sources(env: Any) -> list[tuple[Any, i2.Source]]:
    found = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        raw = obj.get_raw_data()
        if len(raw) < _I2_MIN_SIZE:
            continue
        source = i2.parse_source(bytes(raw))
        if source is not None:
            found.append((obj, source))
    return found


def _i2_keys(path_id: int, source: i2.Source) -> list[tuple[str, int, int]]:
    """Kaynağın tüm metin hücreleri: (anahtar, terim sırası, dil sütunu)."""
    out = []
    seen: dict[str, int] = {}
    for ti, term in enumerate(source.terms):
        if term.term_type != i2.TERM_TEXT:
            continue
        n = seen.get(term.name, 0)
        seen[term.name] = n + 1
        name = term.name if n == 0 else f"{term.name}#{n + 1}"
        for col, lang in enumerate(source.languages):
            out.append((f"{_I2_PREFIX}{path_id}|{lang.code}|{name}", ti, col))
    return out


def _i2_columns(source: i2.Source, context: Context | None) -> set[int]:
    """Aktarılacak dil sütunları: bağlam yoksa hepsi; varsa seçilen dil, yoksa İngilizce."""
    codes = [lang.code for lang in source.languages]
    if context is None or SOURCE_LANGUAGE not in context:
        return set(range(len(codes)))
    wanted = context[SOURCE_LANGUAGE]
    for target in ([str(wanted)] if wanted else []) + ["en"]:
        match = next((i for i, code in enumerate(codes) if same_language(code, target)), None)
        if match is not None:
            return {match}
    return {0}


#: SRT / TSV girdilerinin anahtar önekleri; StringTable ve I2 anahtarlarıyla karışmaz.
_SRT_PREFIX = "SRT|"
_TSV_PREFIX = "TSV|"


@dataclass(frozen=True)
class _Cell:
    """Bir TextAsset içindeki tek bir çevrilebilir metin (bir altyazı veya bir TSV hücresi)."""

    key: str
    lang: str
    context: str
    text: str
    #: SRT için `(başlangıç, bitiş)` konumu; TSV için `(satır, sütun)`.
    where: tuple[int, int]


@dataclass(frozen=True)
class _LocAsset:
    data: Any  # UnityPy TextAsset
    path_id: int
    name: str
    srt: bool
    table: loctext.Table | None
    cells: tuple[_Cell, ...]

    @property
    def languages(self) -> list[str]:
        return list(dict.fromkeys(c.lang for c in self.cells))


def _loc_assets(env: Any) -> list[_LocAsset]:
    """Dosyadaki SRT altyazı ve dil sütunlu TSV TextAsset'leri."""
    found = []
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        data = obj.read()
        script = getattr(data, "m_Script", None)
        if not isinstance(script, str):
            continue
        name = str(data.m_Name)
        if loctext.is_srt(script):
            lang = loctext.srt_language(name)
            cells = tuple(
                _Cell(f"{_SRT_PREFIX}{obj.path_id}|{lang}|{n}", lang, name, cue.text, (cue.start, cue.end))
                for n, cue in enumerate(loctext.parse_srt(script))
            )
            found.append(_LocAsset(data, obj.path_id, name, True, None, cells))
            continue
        table = loctext.parse_tsv(script)
        if table is None:
            continue
        cells = tuple(
            _Cell(
                f"{_TSV_PREFIX}{obj.path_id}|{code}|{line_no}",
                code,
                f"{name}/{table.label(row)}",
                row[col],
                (line_no, col),
            )
            for code, col in table.languages.items()
            for line_no, row in table.rows
        )
        found.append(_LocAsset(data, obj.path_id, name, False, table, cells))
    return found


def _loc_languages(asset: _LocAsset, context: Context | None) -> set[str] | None:
    """Aktarılacak dil: bağlam yoksa hepsi (None); varsa seçilen dil, seçim yoksa İngilizce.

    Altyazı varlığı tek dillidir: yalnızca o dil seçiliyse alınır (aksi hâlde iki dilin altyazısı
    birlikte gelirdi). Çok dilli TSV'de seçilen dil yoksa İngilizce, o da yoksa ilk sütun alınır.
    """
    if context is None or SOURCE_LANGUAGE not in context:
        return None
    codes = asset.languages
    if codes == [""]:
        return {""}  # dil etiketi olmayan altyazı
    wanted = context[SOURCE_LANGUAGE]
    targets = [str(wanted) if wanted else "en"]
    if not asset.srt and "en" not in targets:
        targets.append("en")
    for target in targets:
        match = next((c for c in codes if c and same_language(c, target)), None)
        if match is not None:
            return {match}
    return set() if asset.srt else set(codes[:1])


_BLANK_LINE = re.compile(r"\n[ \t]*\r?\n")
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def _readable(text: str) -> str:
    """Oyun verisindeki geçersiz UTF-8 baytlarını U+FFFD ile gösterir.

    UnityPy bu baytları tek başına vekil karakter yapar; vekil karakterler projeye (SQLite) yazılamaz.
    Metin çevrilmedikçe dosyadaki orijinal baytlara dokunulmaz.
    """
    if _LONE_SURROGATE.search(text) is None:
        return text
    return text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _loc_valid(asset: _LocAsset, original: str, text: str) -> bool:
    """Yeni metin biçimi bozmaz: TSV'de sekme/satır sonu olamaz, SRT'de özgünden fazla boş satır olamaz."""
    if asset.srt:
        return len(_BLANK_LINE.findall(text)) <= len(_BLANK_LINE.findall(original))
    return not any(ch in text for ch in "\t\r\n")


#: Locoliser önbelleği metinlerinin doğrulama anahtarı öneki (projeye satır olarak aktarılmaz).
_LOC_PREFIX = "LOC|"
_LOCOLISER_MIN_SIZE = 64


def _locolisers(env: Any) -> list[tuple[Any, locoliser.Locoliser]]:
    """TSV tablolarının oyuna gömülmüş, ayrıştırılmış kopyaları (Despelote `Locoliser`)."""
    found = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        raw = obj.get_raw_data()
        if len(raw) < _LOCOLISER_MIN_SIZE:
            continue
        loc = locoliser.parse(bytes(raw))
        if loc is not None:
            found.append((obj, loc))
    return found


def _locoliser_keys(path_id: int, loc: locoliser.Locoliser) -> dict[str, str]:
    out = {}
    for ei, subs in enumerate(loc.entries):
        for si, sub in enumerate(subs):
            for li, text in enumerate(sub.texts):
                out[f"{_LOC_PREFIX}{path_id}|d|{ei}|{si}|{li}"] = text
    for ri, row in enumerate(loc.ui_rows):
        for li, text in enumerate(row):
            out[f"{_LOC_PREFIX}{path_id}|u|{ri}|{li}"] = text
    return out


def _dialogue_lines(table: loctext.Table) -> dict[tuple[str, int], int]:
    """Diyalog TSV'sinde `(anahtar, altyazı sırası) → satır`. Anahtar önbellektekiyle aynı biçimdedir:
    `path` + "/" + `voice name`, küçük harf, ters bölü yerine eğik çizgi."""
    cols = {title.strip().lower(): i for i, title in enumerate(table.header)}
    path, voice, index = cols.get("path"), cols.get("voice name"), cols.get("sub index")
    if path is None or voice is None or index is None:
        return {}
    out = {}
    for line, row in table.rows:
        if row[index].strip().isdigit():
            out[((row[path].replace("\\", "/") + "/" + row[voice]).lower(), int(row[index]))] = line
    return out


def _cache_text(old: str, text: str) -> str:
    """Önbellekte satır sonu çoğunlukla gerçek satır sonudur; düz `\\n` yazısıyla tutulan hücrede öyle kalır."""
    return text if _LITERAL_NEWLINE in old else text.replace(_LITERAL_NEWLINE, "\n")


def _cache_texts(original: tuple[str, ...], by_language: Mapping[str, str], codes: list[str]) -> tuple[str, ...]:
    """Satırın yalnızca çevrilen dillerini değiştirir; diğer dil yuvaları özgün kalır."""
    texts = list(original)
    for code, text in by_language.items():
        texts[codes.index(code)] = _cache_text(texts[codes.index(code)], text)
    return tuple(texts)


def _same_row(cache: tuple[str, ...], table: loctext.Table, row: tuple[str, ...]) -> bool:
    cells = tuple(row[col] for col in table.languages.values())
    return cells == cache or tuple(c.replace(_LITERAL_NEWLINE, "\n") for c in cells) == cache


def _locoliser_update(
    path_id: int,
    loc: locoliser.Locoliser,
    tables: Mapping[int, loctext.Table],
    row_text: Mapping[tuple[int, int], Mapping[str, str]],
    expected: dict[str, str],
) -> locoliser.Locoliser | None:
    """TSV satırlarına yazılan Türkçeyi önbellekteki karşılıklarına taşır; değişiklik yoksa None.

    Aynı dil yuvasına yazılır (TSV'de İngilizce sütunu çevrildiyse önbellekte de İngilizce yuvası); diğer diller
    özgün kalır. Diyalog satırları anahtar + altyazı sırasıyla eşlenir (önbellekte metin satırlara bölünmüş olabilir).
    Menü satırları sırayla eşlenir ve yalnızca özgün metinleri TSV'dekiyle aynıysa yazılır.
    """
    dialogue: dict[tuple[int, int], tuple[str, ...]] = {}
    ui: dict[int, tuple[str, ...]] = {}
    table = tables.get(loc.dialogue_file)
    if table is not None and loc.language_count == len(table.languages):
        codes = list(table.languages)
        lines = _dialogue_lines(table)
        for ei, (key, subs) in enumerate(zip(loc.keys, loc.entries, strict=True)):
            for si, sub in enumerate(subs):
                line = lines.get((key.lower(), sub.index))
                by_language = row_text.get((loc.dialogue_file, line)) if line is not None else None
                if by_language:
                    dialogue[(ei, si)] = _cache_texts(sub.texts, by_language, codes)
    ui_table = tables.get(loc.ui_file)
    if (
        ui_table is not None
        and loc.language_count == len(ui_table.languages)
        and len(ui_table.rows) == len(loc.ui_rows)
    ):
        codes = list(ui_table.languages)
        for ri, (line, row) in enumerate(ui_table.rows):
            by_language = row_text.get((loc.ui_file, line))
            if by_language and _same_row(loc.ui_rows[ri], ui_table, row):
                ui[ri] = _cache_texts(loc.ui_rows[ri], by_language, codes)
    if not dialogue and not ui:
        return None
    for (ei, si), texts in dialogue.items():
        for li, text in enumerate(texts):
            expected[f"{_LOC_PREFIX}{path_id}|d|{ei}|{si}|{li}"] = text
    for ri, texts in ui.items():
        for li, text in enumerate(texts):
            expected[f"{_LOC_PREFIX}{path_id}|u|{ri}|{li}"] = text
    return locoliser.with_texts(loc, dialogue, ui)


#: Donkey Kong Country Returns HD `Localization` metinlerinin anahtar öneki (`DK|<nesne>|<dil sırası>|<yuva>`).
_DK_PREFIX = "DK|"
#: Bundan küçük nesne bu yapıda olamaz; büyük dosyalardaki binlerce küçük nesne okunmaz.
_DK_MIN_SIZE = 4096
#: Ses ve animasyon kimlikleri (`\3630bddf\27b05a76`, `\\boss_clingpound`) metin gibi durur ama çevrilmez.
_DK_ASSET_ID = re.compile(r"\\[\\0-9A-Za-z_]*")


def _dk_documents(env: Any) -> list[tuple[Any, dklocal.Document]]:
    found = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour" or obj.byte_size < _DK_MIN_SIZE:
            continue
        raw = bytes(obj.get_raw_data())
        if raw[32:44] != b"Localization":
            continue
        doc = dklocal.parse(raw)
        if doc is not None:
            found.append((obj, doc))
    return found


def _dk_key(path_id: int, language: int, slot: str) -> str:
    return f"{_DK_PREFIX}{path_id}|{language}|{slot}"


def _dk_translatable(text: str) -> bool:
    return not _DK_ASSET_ID.fullmatch(text) and any(ch.isalpha() for ch in _TAG_RE.sub("", text))


def _dk_source(doc: dklocal.Document, context: Context | None) -> dklocal.Language:
    """Aktarılacak dil: seçilen dil, yoksa İngilizce (Rusça topluluk yaması da yalnızca bu yuvayı değiştirir)."""
    wanted = context.get(SOURCE_LANGUAGE) if context else None
    for target in ([str(wanted)] if wanted else []) + ["en"]:
        for language in doc.languages:
            code = dklocal.language_code(language)
            if code and same_language(code, target):
                return language
    return doc.languages[0]


def _dk_snapshot(path_id: int, doc: dklocal.Document) -> dict[str, str]:
    return {
        _dk_key(path_id, language.index, slot): single.text
        for language in doc.languages
        for slot, single in dklocal.unique_slots(doc, language)
    }


def _dk_inject(
    path_id: int,
    doc: dklocal.Document,
    translations: Mapping[str, str],
    known: set[str],
    expected: dict[str, str],
) -> dklocal.Document | None:
    """Çevirileri kayıt defterine işler; değişiklik yoksa None.

    Aynı dili taşıyan ikinci yuvada (İngilizce 0 ve 7) aynı sıradaki satır özgün metinde de özdeşse aynı çeviri oraya
    da yazılır; böylece oyun hangi İngilizce yuvayı okursa okusun Türkçe görünür.
    """
    by_language = {language.index: dklocal.unique_slots(doc, language) for language in doc.languages}
    changes: dict[int, str] = {}
    for language in doc.languages:
        code = dklocal.language_code(language)
        for slot, single in by_language[language.index]:
            key = _dk_key(path_id, language.index, slot)
            known.add(key)
            new = translations.get(key)
            if new is None:
                continue
            shown = _readable(single.text)
            text = _apply(key, shown, new)
            if text == shown:
                continue
            changes[single.rid] = text
            expected[key] = text
            for other in doc.languages:
                if other.index == language.index or not code or dklocal.language_code(other) != code:
                    continue
                twin = dict(by_language[other.index]).get(slot)
                if twin is not None and twin.text == single.text and twin.rid not in changes:
                    changes[twin.rid] = text
                    expected[_dk_key(path_id, other.index, slot)] = text
    return dklocal.with_texts(doc, changes) if changes else None


def _snapshot(env: Any) -> dict[str, str]:
    """Dosyadaki tüm metinler (tablolar, I2 hücreleri, altyazılar, önbellekler); yazım sonrası doğrulama için."""
    got = {_entry_key(tree, e): e["m_Localized"] for _obj, tree in _tables(env) for e in tree["m_TableData"]}
    for obj, source in _i2_sources(env):
        for key, ti, col in _i2_keys(obj.path_id, source):
            got[key] = source.terms[ti].languages[col]
    for asset in _loc_assets(env):
        for cell in asset.cells:
            got[cell.key] = cell.text
    for obj, loc in _locolisers(env):
        got.update(_locoliser_keys(obj.path_id, loc))
    for obj, doc in _dk_documents(env):
        got.update(_dk_snapshot(obj.path_id, doc))
    return got


def _names_for(tree: dict[str, Any], context: Context | None) -> tuple[str, Mapping[int, str]] | None:
    if not context:
        return None
    shared = tree.get("m_SharedData") or {}
    found = context.get(("shared", shared.get("m_PathID")))
    if found is None:
        # Tablo adı genellikle "<koleksiyon>_<dil>" biçimindedir.
        code = str(tree.get("m_LocaleId", {}).get("m_Code", ""))
        name = str(tree.get("m_Name", ""))
        if code and name.endswith("_" + code):
            found = context.get(("collection", name[: -len(code) - 1]))
    if isinstance(found, tuple) and len(found) == 2:
        return str(found[0]), found[1]
    return None


def _apply(key: str, original: str, new: str, literals: tuple[str, ...] = ()) -> str:
    """Yer tutuculu çeviriyi özgün kontrol kodlarıyla birleştirir; uyuşmazlıkta yazmaz."""
    display, codes = tokenize(original, literals)
    issues = placeholders.problems(display, new)
    if issues:
        raise FormatError(f"'{key}' çevirisi yazılamadı: {' '.join(issues)}")
    return detokenize(new, codes)


class UnityPlugin:
    name = "unity"
    label = "Unity (Localization string tabloları, I2 Localization, TextAsset altyazı/TSV)"
    candidates_only = True
    path_suffixes: tuple[str, ...] = ()

    def detect(self, path: str, head: bytes) -> bool:
        return head.startswith(BUNDLE_MAGIC) or is_unity_serialized(path, head)

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        """`SharedTableData` nesnelerinden anahtar adlarını toplar."""
        env = _load(data)
        result: dict[object, object] = {}
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            tree = _read(obj)
            if not tree or "m_TableCollectionName" not in tree or not isinstance(tree.get("m_Entries"), list):
                continue
            names = {int(e["m_Id"]): str(e["m_Key"]) for e in tree["m_Entries"] if "m_Id" in e and "m_Key" in e}
            value = (str(tree["m_TableCollectionName"]), names)
            result[("shared", obj.path_id)] = value
            result[("collection", value[0])] = value
        return result

    def language(self, data: bytes) -> str | None:
        env = _load(data)
        if _i2_sources(env):
            return None  # I2 kaynağı tüm dilleri birlikte tutar
        codes = {str(tree["m_LocaleId"].get("m_Code", "")) for _obj, tree in _tables(env)}
        codes.discard("")
        return sorted(codes)[0] if len(codes) == 1 else None

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        env = _load(data)
        entries: list[TextEntry] = []
        for _obj, tree in _tables(env):
            names = _names_for(tree, context)
            for entry in tree["m_TableData"]:
                display, codes = tokenize(entry["m_Localized"])
                ctx = ""
                if names is not None:
                    key_name = names[1].get(int(entry["m_Id"]))
                    ctx = f"{names[0]}/{key_name}" if key_name else names[0]
                entries.append(TextEntry(_entry_key(tree, entry), len(entries), display, codes, context=ctx))
        for obj, source in _i2_sources(env):
            columns = _i2_columns(source, context)
            for key, ti, col in _i2_keys(obj.path_id, source):
                text = source.terms[ti].languages[col]
                if col not in columns or not text.strip():
                    continue  # boş hücre oyunda görünmez; çevrilecek bir şey yok
                display, codes = tokenize(text)
                entries.append(TextEntry(key, len(entries), display, codes, context=source.terms[ti].name))
        for asset in _loc_assets(env):
            wanted = _loc_languages(asset, context)
            for cell in asset.cells:
                if (wanted is not None and cell.lang not in wanted) or not cell.text.strip():
                    continue
                display, codes = tokenize(_readable(cell.text), (_LITERAL_NEWLINE,))
                entries.append(TextEntry(cell.key, len(entries), display, codes, context=cell.context))
        for obj, doc in _dk_documents(env):
            language = _dk_source(doc, context)
            for slot, single in dklocal.unique_slots(doc, language):
                text = _readable(single.text)
                if not _dk_translatable(text):
                    continue
                display, codes = tokenize(text)
                note = single.name or (single.tag if single.tag.isalpha() else "")
                entries.append(
                    TextEntry(_dk_key(obj.path_id, language.index, slot), len(entries), display, codes, context=note)
                )
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        if not translations:
            return data
        env = _load(data)
        tables = _tables(env)
        known: set[str] = set()
        changed: list[tuple[Any, dict[str, Any]]] = []
        expected = _snapshot(env)
        for obj, tree in tables:
            dirty = False
            for entry in tree["m_TableData"]:
                key = _entry_key(tree, entry)
                known.add(key)
                original = entry["m_Localized"]
                new = translations.get(key)
                if new is None:
                    continue
                text = _apply(key, original, new)
                expected[key] = text
                if text != original:
                    entry["m_Localized"] = text
                    dirty = True
            if dirty:
                changed.append((obj, tree))
        raw_changes: list[tuple[Any, bytes]] = []
        for obj, source in _i2_sources(env):
            terms = list(source.terms)
            for key, ti, col in _i2_keys(obj.path_id, source):
                known.add(key)
                new = translations.get(key)
                if new is None:
                    continue
                original = source.terms[ti].languages[col]
                text = _apply(key, original, new)
                expected[key] = text
                if text != original:
                    terms[ti] = i2.with_text(terms[ti], col, text)
            if terms != list(source.terms):
                raw_changes.append((obj, i2.serialize(replace(source, terms=tuple(terms)))))
        text_changes: list[tuple[Any, str]] = []
        assets = _loc_assets(env)
        translated: list[tuple[_LocAsset, _Cell, str]] = []
        for asset in assets:
            edits: list[tuple[int, int, str]] = []
            cell_changes: dict[tuple[int, int], str] = {}
            for cell in asset.cells:
                known.add(cell.key)
                new = translations.get(cell.key)
                if new is None:
                    continue
                shown = _readable(cell.text)
                text = _apply(cell.key, shown, new, (_LITERAL_NEWLINE,))
                if not _loc_valid(asset, cell.text, text):
                    raise FormatError(
                        f"'{cell.key}' çevirisi yazılamadı: metin biçimi bozacak satır sonu veya sekme içeriyor."
                    )
                if text == shown:
                    continue  # ekranda görünen özgün metin geri verildi: dosya değişmez
                expected[cell.key] = text
                translated.append((asset, cell, text))
                if asset.srt:
                    edits.append((*cell.where, text))
                else:
                    cell_changes[cell.where] = text
            if asset.srt and edits:
                text_changes.append((asset.data, loctext.replace_spans(asset.data.m_Script, edits)))
            elif asset.table is not None and cell_changes:
                text_changes.append((asset.data, loctext.replace_cells(asset.table, cell_changes)))
        # Oyun metni TSV'den değil, onun gömülü kopyasından (Locoliser) okur: Türkçe oraya da taşınır.
        tsv_tables = {a.path_id: a.table for a in assets if a.table is not None}
        row_text: dict[tuple[int, int], dict[str, str]] = {}
        for asset, cell, text in translated:
            if asset.table is not None:
                row_text.setdefault((asset.path_id, cell.where[0]), {})[cell.lang] = text
        for obj, loc in _locolisers(env) if row_text else []:
            updated = _locoliser_update(obj.path_id, loc, tsv_tables, row_text, expected)
            if updated is not None:
                raw_changes.append((obj, locoliser.serialize(updated)))
        for obj, dk_doc in _dk_documents(env):
            updated_doc = _dk_inject(obj.path_id, dk_doc, translations, known, expected)
            if updated_doc is not None:
                raw_changes.append((obj, dklocal.serialize(updated_doc)))
        unknown = [k for k in translations if k not in known]
        if unknown:
            raise FormatError(f"Unity dosyasında olmayan girdiler için çeviri verildi: {', '.join(unknown[:5])}")
        if not changed and not raw_changes and not text_changes:
            return data
        try:
            for obj, tree in changed:
                obj.save_typetree(tree)
            for obj, raw in raw_changes:
                obj.set_raw_data(raw)
            for text_asset, script in text_changes:
                text_asset.m_Script = script
                text_asset.save()
            file_obj: Any = env.file
            options = {"packer": "original"} if isinstance(file_obj, BundleFile) else {}
            out = file_obj.save(**options)
        except Exception as exc:
            raise FormatError(f"Unity dosyası yeniden yazılamadı ({type(exc).__name__}).") from None
        self._verify(bytes(out), expected)
        return bytes(out)

    def _verify(self, out: bytes, expected: Mapping[str, str]) -> None:
        """Yazılan dosyayı yeniden okuyup her metnin beklenen değerde olduğunu doğrular."""
        if _snapshot(_load(out)) != dict(expected):
            raise FormatError(
                "Unity dosyası yazıldıktan sonra doğrulanamadı; değişiklik uygulanmadı.",
                "Bu bir hata olabilir; log dosyasını geliştiriciyle paylaşın.",
            )
