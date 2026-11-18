"""Vektör (TrueType / CFF) fontlara eksik Türkçe harfleri ekleme.

Unity'nin dinamik TextMeshPro fontları ve eski `Font` nesneleri, atlasa eklenmemiş bir harfi çalışma anında gömülü
TTF/OTF dosyasından üretir. Dosyada harf yoksa yedek fonta (çoğunlukla LiberationSans) düşülür ve harf başka bir
yazı tipiyle görünür. Burada `ı İ ş Ş ğ Ğ` fontun kendi şekillerinden türetilip dosyaya eklenir:

| Harf | Türetme (ilk uygun kaynak; ortak sıra `fontpatch/sources.py`) |
|---|---|
| ı | `i`'nin noktası atılır; nokta gövdeden ayrılamıyorsa (birleşik/kalın fontlar) `I`, x-yüksekliğine ölçeklenir |
| İ | `I` + nokta: `i`'nin noktası → `ż Ż ċ Ċ ė Ė` noktası → `ö`/`Ö`'nün bir noktası → `period` → çizilen daire |
| ş, Ş | `s`/`S` + `ç`/`Ç`'nin taban çizgisi altındaki çengeli (diğer büyüklükteki de olur) → `comma` → çizilir |
| ğ, Ğ | `g`/`G` + `ă`/`Ă`'nın kavisi → `˘` (U+02D8) → `ŭ Ŭ ŏ Ŏ` → çizilen yarım elips (boyutu nokta ölçülerinden) |

Harften alınan işaretin konturları olduğu gibi kopyalanır, yalnızca kaydırılır (ölçeklenmez): nokta ve kavis
taban harfe ortalanır ve kaynak harfteki gövdeye uzaklığını korur; çengel kaynak harfteki gövdeye göre konumunu ve
taban çizgisindeki yüksekliğini korur. Gövdeden ayrılamayan (tek kontura kaynamış) işaret o kaynağı geçersiz
kılar, sıradaki denenir. Kullanılan kaynak `FontPatchResult.sources`'ta harf başına bildirilir.

Yeni glifler türetildikleri harfin aralık (kerning) çiftlerini sol ve sağ üye olarak devralır: `kern` tablosu
(biçim 0) ile GPOS PairPos biçim 1 (değerler kopyalanır) ve biçim 2 (glif tabanın sınıfına ve kapsamına eklenir);
Extension sarmalı açılır. Tanınmayan yapı atlanır ve `notes`'a yazılır; kerning'li font derlenemezse yama
kerning'siz yeniden yapılır. Eklenen işaret fontun üst sınırını (`hhea.ascent`, varsa OS/2 `usWinAscent`) aşıyorsa
not düşülür; metrikler değiştirilmez.

Nokta, çengel ve kavis fontun kendi çiziminden alındığı için (ör. el yazısı ya da yalnızca anahatlı fontlar)
üretilen işaretler fontun üslubuna uyar; font bunları içermiyorsa basit çokgenler çizilir. Yeni glifler sona eklenir:
var olan glif numaraları değişmez (TextMeshPro'nun önceden pişirilmiş atlasları bozulmaz).

CID anahtarlı CFF fontlarda (Japonca/Çince/Korece oyun fontları) glif adları `cidNNNNN` biçimindedir; yeni glif
sıradaki CID ile eklenir, `FDSelect` ve `vmtx` tabloları da güncellenir. Böylece harf, fontun kendi charstring
özel sözlüğüyle (Private) üretilir.
"""

from __future__ import annotations

import io
import math
import struct
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, TTLibError

from nxceviri.core.fontpatch import kerning as kerning_tables
from nxceviri.core.fontpatch import sources

PATCHABLE = "ıİşŞğĞ"
#: Harflerin türetileceği temel harf bulunamadı (tmp.py ve dışa aktarma raporuyla aynı ifade).
NO_BASE_LETTER = "kaynak harf yok"

_GLYPH_NAMES = {"ı": "dotlessi", "İ": "Idotaccent", "ş": "scedilla", "Ş": "Scedilla", "ğ": "gbreve", "Ğ": "Gbreve"}
_BASE = {"ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G"}
#: Değiştirilen glif tablosuyla uyumsuz kalan, yalnızca ek bilgi/doğrulama tabloları.
_DROPPED_TABLES = ("hdmx", "LTSH", "VDMX", "DSIG")

Contour = list[tuple[str, tuple[Any, ...]]]  # RecordingPen komutları: moveTo ... closePath


@dataclass(frozen=True)
class FontPatchResult:
    data: bytes  # yamalanmış font; hiçbir şey eklenmediyse özgün baytlar
    added: str
    skipped: dict[str, str]
    #: eklenen harf → işaretin kaynağı ("ç'nin çengeli", "çizildi"; `sources.label`)
    sources: dict[str, str] = field(default_factory=dict)
    #: kısa uyarılar (ör. işaret fontun üst sınırını aşıyor, kerning aktarılamadı)
    notes: tuple[str, ...] = ()


def _open(data: bytes) -> TTFont | None:
    try:
        font = TTFont(io.BytesIO(data))
    except (TTLibError, ValueError, KeyError, AssertionError, struct.error, EOFError):
        return None
    if "cmap" not in font or not ("glyf" in font or "CFF " in font):
        return None
    return font


def _unicode_cmap(font: TTFont) -> dict[int, str] | None:
    return font["cmap"].getBestCmap() or None


#: Bu kadar Çince/Japonca/Korece karakteri olan font dile özgü sayılır (Latin harfleri ona eklenmez).
_CJK_MIN_CHARS = 200


def is_cjk_chars(chars: Iterable[int]) -> bool:
    """Karakter kodlarının çoğu Çince/Japonca/Korece mi (dile özgü font)?"""
    count = sum(1 for c in chars if 0x3040 <= c <= 0x30FF or 0x4E00 <= c <= 0x9FFF or 0xAC00 <= c <= 0xD7A3)
    return count >= _CJK_MIN_CHARS


def plan(data: bytes, letters: str = PATCHABLE, allow_cjk: bool = False) -> tuple[str, dict[str, str]]:
    """Dosyaya dokunmadan: (eklenebilecek harfler, eklenemeyenler → neden).

    `allow_cjk`: çok sayıda Çince/Japonca/Korece karakter içeren fontlara da Latin harfleri eklenir
    (Switch oyun fontları Latin harfleriyle birlikte CJK glifleri taşır).
    """
    font = _open(data)
    cmap = _unicode_cmap(font) if font is not None else None
    if font is None or cmap is None:
        return "", dict.fromkeys(letters, "font okunamadı veya desteklenmeyen biçim")
    if is_cjk_chars(cmap) and not allow_cjk:
        return "", {}  # dile özgü font: Latin harfleri için kullanılmaz, uyarı da gerekmez
    todo = [c for c in letters if c in _GLYPH_NAMES and ord(c) not in cmap]
    addable = ""
    skipped: dict[str, str] = {}
    for c in todo:
        if ord(_BASE[c]) in cmap:
            addable += c
        else:
            skipped[c] = f"{NO_BASE_LETTER} ({_BASE[c]})"
    return addable, skipped


# --- geometri ------------------------------------------------------------------------------------


def _split(ops: list[tuple[str, tuple[Any, ...]]]) -> list[Contour]:
    contours: list[Contour] = []
    current: Contour = []
    for op, args in ops:
        current.append((op, args))
        if op in ("closePath", "endPath"):
            contours.append(current)
            current = []
    return contours


def _replay(contours: list[Contour], pen: Any) -> None:
    for contour in contours:
        for op, args in contour:
            getattr(pen, op)(*args)


def _outline(glyph_set: Any, name: str) -> list[Contour]:
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)
    return _split(pen.value)


def _bounds(contours: list[Contour]) -> tuple[float, float, float, float] | None:
    pen = BoundsPen(None)
    _replay(contours, pen)
    b = pen.bounds
    return None if b is None else (float(b[0]), float(b[1]), float(b[2]), float(b[3]))


def _area(contours: list[Contour]) -> float:
    pen = AreaPen(None)
    _replay(contours, pen)
    return float(pen.value)


def _moved(contours: list[Contour], matrix: tuple[float, float, float, float, float, float]) -> list[Contour]:
    rec = RecordingPen()
    _replay(contours, TransformPen(rec, matrix))
    return _split(rec.value)


def _polygon(points: list[tuple[float, float]], sign: int) -> Contour:
    """Çokgen konturu; yönü fontun dış konturlarıyla aynı olacak şekilde (sign: +1 saat yönünün tersi)."""
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, [*points[1:], points[0]], strict=True)) / 2
    if (area > 0) != (sign > 0):
        points = points[::-1]
    ops: Contour = [("moveTo", (points[0],))]
    ops += [("lineTo", (p,)) for p in points[1:]]
    ops.append(("closePath", ()))
    return ops


def _arc(
    center: tuple[float, float], radii: tuple[float, float], start: float, end: float, steps: int = 24
) -> list[tuple[float, float]]:
    """Elips yayı üzerinde `steps + 1` nokta (derece cinsinden `start` → `end`)."""
    angles = [math.radians(start + (end - start) * i / steps) for i in range(steps + 1)]
    return [(center[0] + radii[0] * math.cos(a), center[1] + radii[1] * math.sin(a)) for a in angles]


@dataclass
class _Metrics:
    upm: int
    xh: float  # küçük harf yüksekliği
    dot_w: float
    dot_h: float
    sign: int  # dış konturların yönü
    solid: bool  # harfler dolu şekil mi (iç boşluklu/halka değil)


def _largest(contours: list[Contour]) -> list[Contour]:
    return sorted(contours, key=lambda c: -abs(_area([c])))[:1]


def _metrics(glyph_set: Any, cmap: dict[int, str], upm: int) -> _Metrics:
    def outline(ch: str) -> list[Contour]:
        name = cmap.get(ord(ch))
        return _outline(glyph_set, name) if name else []

    def top(ch: str) -> float | None:
        b = _bounds(outline(ch))
        return b[3] if b else None

    cap_glyph = outline("I") or outline("H")
    ref = _largest(cap_glyph)
    sign = 1 if ref and _area(ref) > 0 else -1
    dot = _bounds(outline("."))
    if dot is None or dot[2] - dot[0] < upm * 0.01:
        dot = (0.0, 0.0, upm * 0.09, upm * 0.09)
    return _Metrics(
        upm,
        top("x") or top("s") or upm * 0.5,
        dot[2] - dot[0],
        dot[3] - dot[1],
        sign,
        len(cap_glyph) == 1,
    )


def _glyph(glyph_set: Any, cmap: dict[int, str], ch: str) -> list[Contour]:
    name = cmap.get(ord(ch))
    return _outline(glyph_set, name) if name else []


def _is(contour: Contour, group: list[Contour]) -> bool:
    return any(contour is c for c in group)


def _split_above(contours: list[Contour], upm: float) -> tuple[list[Contour], list[Contour]]:
    """(gövde, gövdenin üstündeki işaret konturları): en büyük konturun üstüyle çakışmayan konturlar işarettir."""
    body = _largest(contours)
    bb = _bounds(body)
    if bb is None or len(contours) < 2:
        return contours, []
    marks = [c for c in contours if not _is(c, body) and (b := _bounds([c])) is not None and b[1] >= bb[3] - upm * 0.02]
    return [c for c in contours if not _is(c, marks)], marks


def _one_dot(marks: list[Contour]) -> list[Contour]:
    """İki noktadan (ö) soldakini, iç boşluk konturlarıyla birlikte seçer."""
    boxes = [(c, b) for c in marks if (b := _bounds([c])) is not None]
    if not boxes:
        return []
    first = min(boxes, key=lambda item: item[1][0])[1]
    return [c for c, b in boxes if b[0] < first[2] and b[2] > first[0]]


def _mark_above(glyph_set: Any, cmap: dict[int, str], donor: str, m: _Metrics) -> tuple[list[Contour], float] | None:
    """Kaynak harfin üstteki işareti ve işaretin yüksekliğinin ölçüldüğü gövde üstü; ayrılamıyorsa None."""
    contours = _glyph(glyph_set, cmap, donor)
    if not contours:
        return None
    if donor == sources.SPACING_BREVE:
        return contours, m.xh  # tek başına işaret: küçük harf yüksekliğine göre çizilmiştir
    body, marks = _split_above(contours, m.upm)
    if donor in "öÖ":
        marks = _one_dot(marks)
    body_box = _bounds(body)
    if not marks or body_box is None:
        return None
    return marks, body_box[3]


def _hook(glyph_set: Any, cmap: dict[int, str], donor: str) -> tuple[list[Contour], float] | None:
    """`ç`/`Ç`'nin taban çizgisinin altındaki çengeli ve gövdenin yatay ortası; çengel ayrı kontur değilse None."""
    contours = _glyph(glyph_set, cmap, donor)
    body = _largest(contours)
    hook = [c for c in contours if not _is(c, body) and (b := _bounds([c])) is not None and b[1] + b[3] < 0]
    body_box = _bounds([c for c in contours if not _is(c, hook)])
    if not hook or body_box is None:
        return None
    return hook, _center_x(body_box)


def _drawn_dot(m: _Metrics) -> list[Contour]:
    r = m.dot_w / 2
    return [_polygon(_arc((0, 0), (r, r), 0, 360)[:-1], m.sign)]


def _drawn_cedilla(m: _Metrics) -> list[Contour]:
    w, h = m.dot_w * 0.55, m.dot_h * 2.0
    return [_polygon([(0, 0), (w, 0), (w * 0.8, -h), (-w * 0.1, -h * 0.9)], m.sign)]


def _breve(width: float, m: _Metrics) -> list[Contour]:
    """Altı yuvarlak bir kuşak: dış yarım elipsten iç yarım elipse; çizgi kalınlığı noktanın yarısı kadar."""
    thick = max(m.dot_w * 0.5, m.upm * 0.03)
    depth = max(m.dot_h * 0.9, thick * 1.6)
    half = max(width / 2, m.dot_w)
    outer = _arc((0, depth), (half, depth), 180, 360)
    inner = _arc((0, depth), (max(half - thick, half * 0.3), max(depth - thick, depth * 0.3)), 360, 180)
    return [_polygon(outer + inner, m.sign)]


def _center_x(b: tuple[float, float, float, float]) -> float:
    return (b[0] + b[2]) / 2


def _dotless_i(glyph_set: Any, cmap: dict[int, str], m: _Metrics) -> tuple[list[Contour], str]:
    stem = _outline(glyph_set, cmap[ord("i")])
    body, marks = _split_above(stem, m.upm)
    if marks and body:
        return body, sources.DOTLESS_FROM_I
    # Nokta gövdeye kaynamış: büyük harf I'yı x-yüksekliğine indir.
    cap = _outline(glyph_set, cmap[ord("I")]) if ord("I") in cmap else stem
    cb = _bounds(cap)
    ib = _bounds(stem)
    if cb is None or ib is None:
        return stem, sources.DOTLESS_FROM_I
    sy = m.xh / cb[3] if cb[3] > 0 else 1.0
    sx = min(1.0, (ib[2] - ib[0]) / (cb[2] - cb[0])) if cb[2] > cb[0] else 1.0
    scaled = _moved(cap, (sx, 0, 0, sy, _center_x(ib) - _center_x(cb) * sx, 0))
    return scaled, sources.DOTLESS_FROM_CAPITAL


def _above(
    letter: str, base_box: tuple[float, float, float, float], glyph_set: Any, cmap: dict[int, str], m: _Metrics
) -> tuple[list[Contour], str]:
    """İ'nin noktası ya da ğ/Ğ'nin kavisi, taban harfe yerleştirilmiş olarak (ortak kaynak sırasıyla)."""
    gap = m.dot_h * 0.5
    for donor in sources.donors(letter):
        if donor == sources.PERIOD:
            period = _glyph(glyph_set, cmap, donor)
            pb = _bounds(period)
            if pb is not None and pb[2] - pb[0] >= m.upm * 0.01:
                matrix = (1, 0, 0, 1, _center_x(base_box) - _center_x(pb), base_box[3] + gap - pb[1])
                return _moved(period, matrix), sources.label(letter, donor)
            continue
        found = _mark_above(glyph_set, cmap, donor, m)
        if found is None:
            continue
        mark, ref_top = found
        mb = _bounds(mark)
        if mb is None:
            continue
        matrix = (1, 0, 0, 1, _center_x(base_box) - _center_x(mb), base_box[3] - ref_top)
        return _moved(mark, matrix), sources.label(letter, donor)
    drawn = _drawn_dot(m) if letter == "İ" else _breve(max(base_box[2] - base_box[0], 1) * 0.55, m)
    db = _bounds(drawn)
    assert db is not None  # çizilen şekil boş değildir
    matrix = (1, 0, 0, 1, _center_x(base_box) - _center_x(db), base_box[3] + gap - db[1])
    return _moved(drawn, matrix), sources.DRAWN


def _below(
    letter: str, base_box: tuple[float, float, float, float], glyph_set: Any, cmap: dict[int, str], m: _Metrics
) -> tuple[list[Contour], str]:
    """ş/Ş'nin çengeli, taban harfe yerleştirilmiş olarak (ortak kaynak sırasıyla)."""
    for donor in sources.donors(letter):
        if donor == sources.COMMA:
            comma = _glyph(glyph_set, cmap, donor)
            if _bounds(comma) is None:
                continue
            return _attach_below(_moved(comma, (0.85, 0, 0, 0.85, 0, 0)), base_box, m), sources.label(letter, donor)
        found = _hook(glyph_set, cmap, donor)
        if found is not None:
            hook, body_center = found
            # Çengel kaynak harfteki yerini korur: gövdenin ortasına göre aynı yatay konum, aynı yükseklik.
            return _moved(hook, (1, 0, 0, 1, _center_x(base_box) - body_center, 0)), sources.label(letter, donor)
    return _attach_below(_drawn_cedilla(m), base_box, m), sources.DRAWN


def _attach_below(ced: list[Contour], base_box: tuple[float, float, float, float], m: _Metrics) -> list[Contour]:
    cb = _bounds(ced)
    assert cb is not None  # çağıran boş olmayan şekil verir
    overlap = m.dot_h * 0.25 if m.solid else 0.0
    return _moved(ced, (1, 0, 0, 1, _center_x(base_box) - _center_x(cb), base_box[1] + overlap - cb[3]))


def _build(
    letter: str, glyph_set: Any, cmap: dict[int, str], widths: dict[str, float], m: _Metrics
) -> tuple[list[Contour], float, str] | None:
    """(konturlar, ilerleme, kaynak etiketi); taban harfin şekli boşsa None."""
    base_name = cmap[ord(_BASE[letter])]
    base = _outline(glyph_set, base_name)
    bb = _bounds(base)
    if bb is None:
        return None
    advance = widths[base_name]
    if letter == "ı":
        contours, why = _dotless_i(glyph_set, cmap, m)
        return contours, advance, why
    mark, why = _below(letter, bb, glyph_set, cmap, m) if letter in "şŞ" else _above(letter, bb, glyph_set, cmap, m)
    return base + mark, advance, why


# --- fonta yazma ---------------------------------------------------------------------------------


def _install_glyf(font: TTFont, name: str, contours: list[Contour], advance: float, _base: str = "") -> str:
    pen = TTGlyphPen(font.getGlyphSet())
    _replay(contours, pen)
    glyph = pen.glyph()
    font["glyf"][name] = glyph
    glyph.recalcBounds(font["glyf"])
    font["hmtx"][name] = (round(advance), round(getattr(glyph, "xMin", 0)))
    _install_vmtx(font, name)
    return name


def _install_vmtx(font: TTFont, name: str) -> None:
    """Dikey metrik tablosu varsa (CJK fontları) yeni glif için de bir kayıt ekler."""
    if "vmtx" not in font:
        return
    metrics = font["vmtx"].metrics
    height = next(reversed(metrics.values()), (0, 0))[0]
    metrics[name] = (height, 0)


def _next_cid(top: Any) -> int:
    """CID anahtarlı fontta kullanılmayan ilk CID."""
    cids = [int(str(n)[3:]) for n in top.charset if str(n).startswith("cid") and str(n)[3:].isdigit()]
    return max(cids, default=0) + 1


def _install_cff(font: TTFont, name: str, contours: list[Contour], advance: float, base: str = "") -> str:
    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    is_cid = hasattr(top, "ROS")
    chars = top.CharStrings
    fd_index = 0
    private = getattr(top, "Private", None)
    if is_cid:
        # Yeni glif, türetildiği harfin charstring sözlüğünü (Private) kullanır.
        base_gid = chars.charStrings.get(base)
        if base_gid is not None and getattr(top, "FDSelect", None) is not None:
            fd_index = top.FDSelect.gidArray[base_gid]
            private = top.FDArray[fd_index].Private
        name = f"cid{_next_cid(top):05d}"
    pen = T2CharStringPen(round(advance), font.getGlyphSet())
    _replay(contours, pen)
    charstring = pen.getCharString(private, cff.GlobalSubrs)
    chars.charStrings[name] = len(chars.charStringsIndex)
    chars.charStringsIndex.append(charstring)
    top.charset.append(name)
    if is_cid and getattr(top, "FDSelect", None) is not None:
        top.FDSelect.gidArray.append(fd_index)
    bounds = _bounds(contours)
    font["hmtx"][name] = (round(advance), round(bounds[0]) if bounds else 0)
    _install_vmtx(font, name)
    return name


def _register(font: TTFont, name: str, codepoint: int) -> None:
    # CFF'te glif sırası doğrudan charset listesidir; kopya üzerinde çalışmazsak charset de değişir.
    order = list(font.getGlyphOrder())
    if name not in order:
        order.append(name)
        font.setGlyphOrder(order)
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap[codepoint] = name


#: İşareti fontun üst sınırını aşabilecek harfler (büyük harf + üst işaret).
_TALL = "İĞ"


def _over_ascent(font: TTFont, letter: str, contours: list[Contour]) -> str | None:
    """Büyük harfin üst işareti `hhea.ascent`'i ya da (varsa) OS/2 `usWinAscent`'i aşıyorsa not."""
    box = _bounds(contours)
    if letter not in _TALL or box is None:
        return None
    limits = [int(font["hhea"].ascent)] if "hhea" in font else []
    win = int(getattr(font["OS/2"], "usWinAscent", 0)) if "OS/2" in font else 0
    if win > 0:
        limits.append(win)
    if any(box[3] > limit for limit in limits):
        return f"{letter}: işaret fontun üst sınırını aşıyor; oyunda kesilebilir"
    return None


def patch_font(data: bytes, letters: str = PATCHABLE, allow_cjk: bool = False) -> FontPatchResult:
    """`letters` içinde fontta olmayan ve türetilebilen harfleri ekler; hiçbiri eklenemezse özgün baytlar döner.

    Yeni glifler taban harflerinin kerning çiftlerini devralır; kerning'li font derlenemezse yama kerning'siz
    yeniden yapılır ve bu `notes`'ta bildirilir.
    """
    try:
        return _patch(data, letters, allow_cjk, kerning=True)
    except _KerningCompileError as exc:
        result = _patch(data, letters, allow_cjk, kerning=False)
        note = f"kerning aktarılamadı ({exc.reason}); harfler kerning'siz eklendi"
        return FontPatchResult(result.data, result.added, result.skipped, result.sources, (*result.notes, note))


class _KerningCompileError(Exception):
    """Kerning aktarılmış font derlenemedi (fontTools'un herhangi bir hatası)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _patch(data: bytes, letters: str, allow_cjk: bool, *, kerning: bool) -> FontPatchResult:
    addable, skipped = plan(data, letters, allow_cjk)
    font = _open(data)
    if not addable or font is None:
        return FontPatchResult(data, "", skipped)
    cmap = dict(_unicode_cmap(font) or {})
    glyph_set = font.getGlyphSet()
    widths = {name: float(font["hmtx"][name][0]) for name in font.getGlyphOrder()}
    metrics = _metrics(glyph_set, cmap, int(font["head"].unitsPerEm))
    install = _install_glyf if "glyf" in font else _install_cff
    added = ""
    found: dict[str, str] = {}
    notes: list[str] = []
    inherited: dict[str, str] = {}  # yeni glif → kerning'ini devraldığı taban glif
    # Önce hepsi üretilir (türetme özgün glif kümesinden yapılır), sonra yazılır.
    built = {c: _build(c, glyph_set, cmap, widths, metrics) for c in addable}
    for letter, result in built.items():
        if result is None:
            skipped[letter] = "temel harfin şekli boş"
            continue
        name = _GLYPH_NAMES[letter]
        if name in font.getGlyphOrder():
            name = f"{name}.tr"
        contours, advance, source = result
        base_name = cmap[ord(_BASE[letter])]
        installed = install(font, name, contours, advance, base_name)
        _register(font, installed, ord(letter))
        inherited[installed] = base_name
        added += letter
        found[letter] = source
        if (note := _over_ascent(font, letter, contours)) is not None:
            notes.append(note)
    if not added:
        return FontPatchResult(data, "", skipped)
    out = io.BytesIO()
    # fontTools'un okuma/derleme hataları tek türde değildir (struct.error, KeyError, taşma…): kerning adımında ya da
    # kerning'li fontu yazıp yeniden okurken çıkan her hata, yamayı özgün baytlardan kerning'siz yeniden yaptırır.
    try:
        if kerning:
            notes += kerning_tables.inherit(font, inherited)
        for tag in _DROPPED_TABLES:
            if tag in font:
                del font[tag]
        font.save(out)
        if kerning:
            _reopen_kerning(out.getvalue())
    except Exception as exc:
        if not kerning:
            raise
        raise _KerningCompileError(type(exc).__name__) from exc
    result_bytes = out.getvalue()
    _verify(result_bytes, added)
    return FontPatchResult(result_bytes, added, skipped, found, tuple(dict.fromkeys(notes)))


def _reopen_kerning(data: bytes) -> None:
    """Yazılan fontun kerning tabloları baştan sona yeniden çözülür (bozuksa fontTools hata yükseltir)."""
    font = TTFont(io.BytesIO(data))
    for tag in ("kern", "GPOS"):
        if tag in font:
            table = font[tag]
            if hasattr(table, "ensureDecompiled"):
                table.ensureDecompiled(recurse=True)


def _verify(data: bytes, added: str) -> None:
    """Yazılan font yeniden okunur: eklenen her harf cmap'te ve çizilebilir (boş değil) olmalı."""
    font = _open(data)
    cmap = _unicode_cmap(font) if font is not None else None
    if font is None or cmap is None:
        raise ValueError("yamalanan font yeniden okunamadı")
    glyph_set = font.getGlyphSet()
    for letter in added:
        name = cmap.get(ord(letter))
        if name is None or _bounds(_outline(glyph_set, name)) is None:
            raise ValueError(f"'{letter}' harfi yamalanan fontta görünmüyor")
