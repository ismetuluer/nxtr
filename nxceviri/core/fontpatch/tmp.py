"""TextMeshPro statik SDF fontlarına eksik Türkçe harfleri ekleme (M8).

Statik bir TMP fontu yalnızca atlas dokusunda çizili karakterleri gösterebilir. Eksik harfler,
aynı fontun var olan gliflerinden üretilir; böylece yazı tipi, kalınlık ve SDF ayarları tutarlı
kalır:

| Harf | Nasıl |
|---|---|
| ı | "i"nin noktası kaldırılır |
| İ | "I"nın üstüne "i"nin noktası konur ("Ö"nün noktalarının yüksekliğinde) |
| ş, Ş | "s"/"S"nin altına "ç"/"Ç"nin çengeli konur |
| ğ, Ğ | "g"/"G"nin üstüne kısa çizgi (breve) çizilir; boyutu "ü"/"Ü"nün noktalarından alınır |

Aynı büyüklükteki donör harf fontta yoksa (ör. yalnızca `ç` var, `Ç` yok) diğer
büyüklükteki donör kullanılır. Çengel ve breve büyük/küçük harfte aynı boyuttadır;
donörün işareti ölçeklenmez, yalnızca taban harfin boyuna göre konumlandırılır.

Yeni glifler atlastaki boş alana (MaxRects serbest dikdörtgenleri) yerleştirilir; yer yetmezse
atlas yukarı doğru iki katına çıkarılır (sol-alt başlangıçlı koordinatlar değişmediği için var olan
glifler yerinde kalır; `m_AtlasHeight` ve malzemenin `_TextureHeight` değeri güncellenir). Glif ve
karakter tabloları ile kullanılan/boş dikdörtgen listeleri güncellenir. Kaynak glif (donör)
yoksa o harf eklenmez ve raporda belirtilir; uygulama sahte veri üretmez.

Koordinatlar: TMP glif dikdörtgenleri atlasın **sol altından** ölçülür; glif metrikleri piksel
birimindedir (atlas `m_FaceInfo.m_PointSize` ile örneklenmiştir). Kullanılan dikdörtgen, glifin
çevresinde solda/altta `dolgu + 1`, toplamda `2·dolgu + 1` piksel pay bırakır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageDraw

from nxceviri.core.fontpatch import sdf

TURKISH_PATCHABLE = "ıİşŞğĞ"
_SUPERSAMPLE = 4
#: İşaret (nokta) sayılacak en küçük parça: piksel sayısı ve gövdeye oranı.
_MIN_MARK_AREA = 6
_MIN_MARK_RATIO = 0.01
#: Yer yetmezse atlas en çok bir kez (yükseklik ×2) büyütülür.
_MAX_GROW = 1


@dataclass
class Glyph:
    """Atlastan kesilmiş glif: SDF alanı (pay dahil) ve glif uzayındaki konumu."""

    field: sdf.Field
    left: int  # pay dahil alanın sol kenarının glif uzayındaki x'i (piksel)
    top: int  # pay dahil alanın üst kenarının glif uzayındaki y'si (yukarı pozitif)
    advance: float

    def ink(self) -> list[int]:
        return [i for i, m in enumerate(self.field.mask()) if m]


@dataclass
class FontPatchResult:
    added: str = ""  # eklenen harfler
    skipped: dict[str, str] = field(default_factory=dict)  # harf → neden


class _Atlas:
    """Atlas dokusunun alfa kanalı (üst-sol başlangıçlı) ve serbest alan yönetimi."""

    def __init__(self, image: Image.Image, used: list[dict[str, int]], free: list[dict[str, int]]) -> None:
        self.alpha = image.getchannel("A") if image.mode == "RGBA" else image.convert("L")
        self.width, self.height = self.alpha.size
        self.used = [dict(r) for r in used]
        self.free = [dict(r) for r in free]

    def crop(self, x: int, y: int, w: int, h: int) -> sdf.Field:
        """Sol-alt başlangıçlı (x, y, w, h) bölgesini SDF alanı olarak okur."""
        top = self.height - (y + h)
        region = self.alpha.crop((x, top, x + w, top + h))
        return sdf.Field(w, h, [float(v) for v in region.tobytes()])

    def write(self, f: sdf.Field, x: int, y: int) -> None:
        top = self.height - (y + f.height)
        patch = Image.frombytes("L", (f.width, f.height), f.to_bytes())
        self.alpha.paste(patch, (x, top))

    def grow(self) -> None:
        """Atlası yukarı doğru iki katına çıkarır; sol-alt başlangıçlı koordinatlar değişmez."""
        grown = Image.new("L", (self.width, self.height * 2), 0)
        grown.paste(self.alpha, (0, self.height))
        self.free.append({"m_X": 0, "m_Y": self.height, "m_Width": self.width, "m_Height": self.height})
        self.alpha = grown
        self.height *= 2

    def allocate(self, w: int, h: int) -> tuple[int, int] | None:
        """MaxRects "en kısa kenar" yerleşimi; bulunamazsa None."""
        best: tuple[int, int, int] | None = None
        for r in self.free:
            if r["m_Width"] >= w and r["m_Height"] >= h:
                fit = min(r["m_Width"] - w, r["m_Height"] - h)
                if best is None or fit < best[0]:
                    best = (fit, r["m_X"], r["m_Y"])
        if best is None:
            return None
        _fit, x, y = best
        self._occupy({"m_X": x, "m_Y": y, "m_Width": w, "m_Height": h})
        return x, y

    def _occupy(self, u: dict[str, int]) -> None:
        self.used.append(u)
        ux, uy, uw, uh = u["m_X"], u["m_Y"], u["m_Width"], u["m_Height"]
        out = []
        for r in self.free:
            rx, ry, rw, rh = r["m_X"], r["m_Y"], r["m_Width"], r["m_Height"]
            if ux >= rx + rw or ux + uw <= rx or uy >= ry + rh or uy + uh <= ry:
                out.append(r)
                continue
            if ux > rx:
                out.append({"m_X": rx, "m_Y": ry, "m_Width": ux - rx, "m_Height": rh})
            if ux + uw < rx + rw:
                out.append({"m_X": ux + uw, "m_Y": ry, "m_Width": rx + rw - ux - uw, "m_Height": rh})
            if uy > ry:
                out.append({"m_X": rx, "m_Y": ry, "m_Width": rw, "m_Height": uy - ry})
            if uy + uh < ry + rh:
                out.append({"m_X": rx, "m_Y": uy + uh, "m_Width": rw, "m_Height": ry + rh - uy - uh})
        # Başka bir serbest dikdörtgenin içinde kalanları at.
        pruned = []
        for i, a in enumerate(out):
            contained = any(
                j != i
                and b["m_X"] <= a["m_X"]
                and b["m_Y"] <= a["m_Y"]
                and a["m_X"] + a["m_Width"] <= b["m_X"] + b["m_Width"]
                and a["m_Y"] + a["m_Height"] <= b["m_Y"] + b["m_Height"]
                and (a != b or j < i)
                for j, b in enumerate(out)
            )
            if not contained:
                pruned.append(a)
        self.free = pruned

    def image(self) -> Image.Image:
        """Doku olarak yazılacak görüntü (Alpha8 için yalnızca alfa kanalı anlamlıdır)."""
        out = Image.new("RGBA", self.alpha.size, (255, 255, 255, 0))
        out.putalpha(self.alpha)
        return out


class TmpFont:
    """Bir `TMP_FontAsset` tip ağacı ve atlası üzerinde çalışır."""

    def __init__(self, tree: dict[str, Any], atlas_image: Image.Image) -> None:
        self.tree = tree
        self.pad = int(tree["m_AtlasPadding"])
        self.margin = self.pad + 1
        self.atlas = _Atlas(atlas_image, tree.get("m_UsedGlyphRects") or [], tree.get("m_FreeGlyphRects") or [])
        self.glyphs = {int(g["m_Index"]): g for g in tree["m_GlyphTable"]}
        self.chars = {int(c["m_Unicode"]): int(c["m_GlyphIndex"]) for c in tree["m_CharacterTable"]}
        self.slope = 12.75
        self.grown = 0
        self.placed = 0  # atlasa çizilen glif sayısı (takma adlar sayılmaz)
        sample = self.glyph("I") or self.glyph("l")
        if sample is not None:
            self.slope = sdf.estimate_slope(sample.field)

    @property
    def is_static(self) -> bool:
        return int(self.tree.get("m_AtlasPopulationMode", 0)) == 0

    def has(self, ch: str) -> bool:
        return ord(ch) in self.chars

    def glyph(self, ch: str) -> Glyph | None:
        index = self.chars.get(ord(ch))
        g = self.glyphs.get(index) if index is not None else None
        if g is None or int(g.get("m_AtlasIndex", 0)) != 0:
            return None
        r, m = g["m_GlyphRect"], g["m_Metrics"]
        if r["m_Width"] <= 0 or r["m_Height"] <= 0:
            return None
        k = self.margin
        f = self.atlas.crop(r["m_X"] - k, r["m_Y"] - k, r["m_Width"] + 2 * k - 1, r["m_Height"] + 2 * k - 1)
        # Alanın üst satırı glifin üst kenarının k-1 satır üstündedir (pay: solda/altta k, sağda/üstte k-1).
        left = round(m["m_HorizontalBearingX"]) - k
        top = round(m["m_HorizontalBearingY"]) + k - 1
        return Glyph(f, left, top, float(m["m_HorizontalAdvance"]))

    # --- harf tarifleri ---------------------------------------------------------------

    def _part(self, g: Glyph, indices: list[int]) -> Glyph:
        """Glifin bir parçasını (piksel indeksleri) yeni mesafe alanıyla ayırır."""
        w = g.field.width
        x0, y0, x1, y1 = sdf.bbox(indices, w)
        k = self.margin
        pw, ph = x1 - x0 + 2 * k, y1 - y0 + 2 * k
        mask = [False] * (pw * ph)
        for i in indices:
            mask[(i // w - y0 + k) * pw + (i % w - x0 + k)] = True
        return Glyph(sdf.from_mask(mask, pw, ph, self.slope), g.left + x0 - k, g.top - (y0 - k), g.advance)

    def _ink_box(self, g: Glyph, indices: list[int] | None = None) -> tuple[int, int, int, int]:
        """Mürekkebin glif uzayındaki kutusu: (sol, üst, sağ, alt) — y yukarı pozitif."""
        x0, y0, x1, y1 = sdf.bbox(indices if indices is not None else g.ink(), g.field.width)
        return g.left + x0, g.top - y0, g.left + x1, g.top - y1

    def _marks(self, g: Glyph) -> list[list[int]]:
        """Gövdenin üstündeki işaretler (nokta, iki nokta), büyükten küçüğe.

        Çok küçük parçalar (ör. el yazısı fontlardaki lekeler) işaret sayılmaz.
        """
        w = g.field.width
        comps = sdf.components(g.field.mask(), w, g.field.height)
        if len(comps) < 2:
            return []
        body = comps[0]
        body_top = min(i // w for i in body)
        marks = []
        for c in comps[1:]:
            x0, y0, x1, y1 = sdf.bbox(c, w)
            big_enough = len(c) >= max(_MIN_MARK_AREA, len(body) * _MIN_MARK_RATIO) and min(x1 - x0, y1 - y0) >= 2
            if big_enough and y1 <= body_top:
                marks.append(c)
        return marks

    def _marks_above(self, g: Glyph) -> list[int]:
        return [i for c in self._marks(g) for i in c]

    def _dotless(self, i: Glyph) -> Glyph | None:
        if not self._marks(i):
            return None
        return self._part(i, sdf.components(i.field.mask(), i.field.width, i.field.height)[0])

    def _compose(self, base: Glyph, parts: list[Glyph]) -> Glyph:
        """Parçaları tabanla birleştirir; tuval, hepsini ve payı kapsar."""
        everything = [base, *parts]
        left = min(p.left for p in everything)
        top = max(p.top for p in everything)
        right = max(p.left + p.field.width for p in everything)
        bottom = min(p.top - p.field.height for p in everything)
        canvas = sdf.Field.blank(right - left, top - bottom)
        for p in everything:
            sdf.union(canvas, p.field, p.left - left, top - p.top)
        return Glyph(canvas, left, top, base.advance)

    @staticmethod
    def _moved(g: Glyph, dx: int, dy: int) -> Glyph:
        return Glyph(g.field, g.left + dx, g.top + dy, g.advance)

    def _center_x(self, g: Glyph) -> float:
        x0, _t, x1, _b = self._ink_box(g)
        return (x0 + x1) / 2

    def _dot_on(self, base: Glyph, dot_source: Glyph | None, accent_ref: Glyph | None) -> Glyph | None:
        """Tabana nokta koyar: nokta "i"den, o yoksa "Ö"nün noktalarından birinden alınır."""
        ref_marks = self._marks(accent_ref) if accent_ref is not None else []
        source_marks = self._marks(dot_source) if dot_source is not None else []
        if source_marks and dot_source is not None:
            dot = self._part(dot_source, source_marks[0])
        elif ref_marks and accent_ref is not None:
            dot = self._part(accent_ref, ref_marks[0])
        else:
            return None
        _l, dot_top, _r, _b = self._ink_box(dot)
        if ref_marks and accent_ref is not None:
            target_top = self._ink_box(accent_ref, [i for c in ref_marks for i in c])[1]
        else:
            assert dot_source is not None
            stem = self._dotless(dot_source)
            if stem is None:
                return None
            gap = dot_top - self._ink_box(stem)[1]
            target_top = self._ink_box(base)[1] + gap
        dx = round(self._center_x(base) - self._center_x(dot))
        return self._compose(base, [self._moved(dot, dx, target_top - dot_top)])

    def _cedilla_on(self, base: Glyph, source: Glyph) -> Glyph | None:
        """Kaynağın (ç/Ç) taban çizgisinin altındaki kısmı (çengel) tabanın altına konur."""
        w = source.field.width
        below = [i for i in source.ink() if source.top - i // w < 0]
        if not below:
            return None
        hook = self._part(source, below)
        dx = round(self._center_x(base) - self._center_x(source))
        # Çengel gövdeden kopuk kalmasın: üst kenarı tabanın alt kenarına en az 1 piksel girsin.
        base_bottom = self._ink_box(base)[3]
        hook_top = self._ink_box(hook)[1]
        dy = max(0, base_bottom + 1 - hook_top)
        return self._compose(base, [self._moved(hook, dx, dy)])

    def _breve_on(self, base: Glyph, diaeresis_ref: Glyph) -> Glyph | None:
        marks = self._marks_above(diaeresis_ref)
        if not marks:
            return None
        x0, _top, x1, bottom = self._ink_box(diaeresis_ref, marks)
        span, height = x1 - x0, _top - bottom
        # Breve, donorun noktaları ile gövdesi arasındaki boşluk kadar yukarıya konur.
        comps = sdf.components(diaeresis_ref.field.mask(), diaeresis_ref.field.width, diaeresis_ref.field.height)
        body_top = self._ink_box(diaeresis_ref, comps[0])[1]
        target_top = self._ink_box(base)[1] + (_top - body_top)
        width = max(4, round(span * 0.8))
        thick = max(2, round(height * 0.45))
        arc_h = max(thick + 2, round(height * 1.1))
        k = self.margin
        s = _SUPERSAMPLE
        img = Image.new("L", (width * s, arc_h * s * 2), 0)
        ImageDraw.Draw(img).arc(
            (0, -arc_h * s, width * s - 1, arc_h * s - 1), start=0, end=180, fill=255, width=thick * s
        )
        img = img.crop((0, 0, width * s, arc_h * s)).resize((width, arc_h), Image.Resampling.BOX)
        pw, ph = width + 2 * k, arc_h + 2 * k
        mask = [False] * (pw * ph)
        for idx, v in enumerate(img.tobytes()):
            if v >= 128:
                mask[(idx // width + k) * pw + idx % width + k] = True
        breve = Glyph(sdf.from_mask(mask, pw, ph, self.slope), 0, 0, 0.0)
        bx0, btop, _bx1, _bb = self._ink_box(breve)
        center = self._center_x(base)
        return self._compose(base, [self._moved(breve, round(center - (bx0 + width / 2)), target_top - btop)])

    def build(self, ch: str) -> Glyph | str:
        """Harfin glifini üretir; üretemezse nedenini döndürür.

        Donör harf aynı büyüklükte yoksa (ör. fontta `Ç` yok) diğer büyüklükteki
        eşdeğeri (ör. `ç`) kullanılır; işaret aynı boyutta kalır.
        """
        if ch == "İ":
            base = self.glyph("I")
            if base is None:
                return "kaynak harf yok: I"
            if self.glyph("i") is None and self.glyph("Ö") is None:
                return "kaynak harf yok: i veya Ö"
            dotted = self._dot_on(base, self.glyph("i"), self.glyph("Ö"))
            return dotted if dotted is not None else "kaynak harfin yapısı beklenenden farklı"
        if ch == "ı":
            base = self.glyph("i")
            if base is None:
                return "kaynak harf yok: i"
            dotless = self._dotless(base)
            return dotless if dotless is not None else "kaynak harfin yapısı beklenenden farklı"

        # (taban, aynı büyüklükteki donör, diğer büyüklükteki donör)
        spec = {
            "ş": ("s", "ç", "Ç"),
            "Ş": ("S", "Ç", "ç"),
            "ğ": ("g", "ü", "Ü"),
            "Ğ": ("G", "Ü", "ü"),
        }[ch]
        base_ch, same, other = spec
        base = self.glyph(base_ch)
        if base is None:
            return f"kaynak harf yok: {base_ch}"
        source = self.glyph(same) or self.glyph(other)
        if source is None:
            return f"kaynak harf yok: {same}"
        result = self._cedilla_on(base, source) if ch in "şŞ" else self._breve_on(base, source)
        return result if result is not None else "kaynak harfin yapısı beklenenden farklı"

    # --- yazma -----------------------------------------------------------------------------

    def add(self, ch: str, g: Glyph) -> bool:
        """Glifi atlasa ve tablolara ekler; yer yoksa False."""
        k = self.margin
        ink = g.ink()
        if not ink:
            return False
        x0, y0, x1, y1 = sdf.bbox(ink, g.field.width)
        w, h = x1 - x0, y1 - y0
        need = (w + 2 * self.pad + 1, h + 2 * self.pad + 1)
        spot = self.atlas.allocate(*need)
        if spot is None and self.grown < _MAX_GROW:
            self.atlas.grow()
            self.grown += 1
            spot = self.atlas.allocate(*need)
        if spot is None:
            return False
        fx, fy = spot
        region = sdf.Field.blank(w + 2 * k - 1, h + 2 * k - 1)
        sdf.union(region, g.field, -(x0 - k), -(y0 - (k - 1)))
        # Bölgenin sol-alt köşesi (fx, fy); alanın üst satırı yukarıda.
        self.atlas.write(region, fx, fy)
        index = max(self.glyphs) + 1 if self.glyphs else 0
        entry = {
            "m_Index": index,
            "m_Metrics": {
                "m_Width": float(w),
                "m_Height": float(h),
                "m_HorizontalBearingX": float(g.left + x0),
                "m_HorizontalBearingY": float(g.top - y0),
                "m_HorizontalAdvance": g.advance,
            },
            "m_GlyphRect": {"m_X": fx + k, "m_Y": fy + k, "m_Width": w, "m_Height": h},
            "m_Scale": 1.0,
            "m_AtlasIndex": 0,
        }
        template = next(iter(self.glyphs.values()), None)
        if template is not None and "m_ClassDefinitionType" in template:
            entry["m_ClassDefinitionType"] = 0
        self.tree["m_GlyphTable"].append(entry)
        self.placed += 1
        self.glyphs[index] = entry
        char = {"m_ElementType": 1, "m_Unicode": ord(ch), "m_GlyphIndex": index, "m_Scale": 1.0}
        self.tree["m_CharacterTable"].append(char)
        self.chars[ord(ch)] = index
        return True

    def alias(self, ch: str, target: str) -> None:
        """`ch`'yi var olan bir glife bağlar (atlasta yer gerekmez)."""
        index = self.chars[ord(target)]
        self.tree["m_CharacterTable"].append(
            {"m_ElementType": 1, "m_Unicode": ord(ch), "m_GlyphIndex": index, "m_Scale": 1.0}
        )
        self.chars[ord(ch)] = index

    def _dotless_is_same(self) -> bool:
        """Büyük harf fontlarında "i" noktasızdır ("I" biçiminde); "ı" aynı glifle gösterilir."""
        i = self.glyph("i")
        return i is not None and not self._marks(i)

    def patch(self, letters: str = TURKISH_PATCHABLE) -> FontPatchResult:
        result = FontPatchResult()
        for ch in letters:
            if self.has(ch):
                continue
            if ch == "ı" and self._dotless_is_same():
                self.alias("ı", "i")
                result.added += ch
                continue
            built = self.build(ch)
            if isinstance(built, str):
                result.skipped[ch] = built
            elif self.add(ch, built):
                result.added += ch
            else:
                result.skipped[ch] = "atlasta yer yok"
        if self.placed:
            self.tree["m_UsedGlyphRects"] = self.atlas.used
            self.tree["m_FreeGlyphRects"] = self.atlas.free
            self.tree["m_AtlasHeight"] = self.atlas.height
            creation = self.tree.get("m_CreationSettings")
            if isinstance(creation, dict) and "atlasHeight" in creation:
                creation["atlasHeight"] = self.atlas.height
        return result

    def atlas_image(self) -> Image.Image:
        return self.atlas.image()
