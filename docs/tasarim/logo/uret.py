"""NXTR yatay logosunu ve uygulama simgelerini SVG olarak üretir (yazı yol olarak çizilir).

    python docs/tasarim/logo/uret.py

Çıktılar: bu klasörde `nxtr-logo.svg` (açık zemin) ve `nxtr-logo-koyu.svg` (koyu zemin); uygulama simgesi kaynakları
`nxceviri/gui/appicon/nxtr.svg` (32 px ve üstü, düğmeli) ve `nxtr-kucuk.svg` (24 px ve altı, yalnızca çubuk daireleri).
.ico/.png dosyaları sonra `packaging/make_icon.py` ile üretilir.
"""

from __future__ import annotations

from pathlib import Path

DIR = Path(__file__).resolve().parent
ICON_DIR = DIR.parent.parent.parent / "nxceviri" / "gui" / "appicon"
BLUE = "#00B4E6"
RED = "#FF3C28"

# Dar ve çok kalın harfler, 100 birim yüksekliğinde; (yol, genişlik)
LETTERS: dict[str, tuple[str, int]] = {
    "N": ("M0 100V0H19L37 56V0H56V100H37L19 44V100Z", 56),
    "X": ("M0 0H21L29 33L37 0H58L40 50L58 100H37L29 67L21 100H0L18 50Z", 58),
    "T": ("M0 0H56V14H38V100H18V14H0Z", 56),
    "R": (
        "M0 100V0H32C49 0 58 11 58 28C58 40 52 48 44 52L60 100H39L26 59H20V100Z"
        "M20 12V46H31C38 46 39 41 39 29C39 17 38 12 31 12Z",
        60,
    ),
}
LETTER_GAP = 4


def word(text: str, x: float, y: float, *, scale_x: float, scale_y: float, colors: dict[str, str]) -> tuple[str, float]:
    """ "NXTR" harflerini (x, y) sol-üst köşesinden çizer; (svg parçası, toplam genişlik) döner."""
    parts: list[str] = []
    cursor = 0.0
    for ch in text:
        path, width = LETTERS[ch]
        parts.append(
            f'<path transform="translate({x + cursor * scale_x:g} {y:g}) scale({scale_x:g} {scale_y:g})" d="{path}" '
            f'fill="{colors[ch]}" fill-rule="evenodd"/>'
        )
        cursor += width + LETTER_GAP
    return "\n  ".join(parts), (cursor - LETTER_GAP) * scale_x


def half_pill(x: float, y: float, w: float, h: float, *, left: bool, color: str, r: float) -> str:
    """Dış kenarı yuvarlak, iç kenarı (yazıya/karşıdaki yarıya bakan) düz ve keskin köşeli yarım hap."""
    top, bottom = y + r, y + h - r
    if left:
        arc = f"A{r:g} {r:g} 0 0 0"
        d = f"M{x + w:g} {y:g}H{x + r:g}{arc} {x:g} {top:g}V{bottom:g}{arc} {x + r:g} {y + h:g}H{x + w:g}Z"
    else:
        arc = f"A{r:g} {r:g} 0 0 1"
        d = f"M{x:g} {y:g}H{x + w - r:g}{arc} {x + w:g} {top:g}V{bottom:g}{arc} {x + w - r:g} {y + h:g}H{x:g}Z"
    return f'<path d="{d}" fill="{color}"/>'


DARK = "#1E1E1E"
CAP = "#4A4A4A"


def dot(cx: float, cy: float, r: float, fill: str) -> str:
    return f'<circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="{fill}"/>'


def rect(cx: float, cy: float, w: float, h: float, r: float = 0) -> str:
    return f'<rect x="{cx - w / 2:g}" y="{cy - h / 2:g}" width="{w:g}" height="{h:g}" rx="{r:g}" fill="{DARK}"/>'


def stick(cx: float, cy: float, r: float) -> str:
    """Koyu çubuk: dış daire, daha açık gri şapka ve küçük beyaz parlama yayı."""
    cap = r * 0.62
    arc = (
        f'<path d="M{cx - cap * 0.7:g} {cy - cap * 0.25:g}A{cap * 0.75:g} {cap * 0.75:g} 0 0 1 '
        f'{cx - cap * 0.25:g} {cy - cap * 0.7:g}" fill="none" stroke="#FFFFFF" stroke-width="{max(r * 0.09, 0.5):g}" '
        'stroke-linecap="round"/>'
    )
    return "\n  ".join([dot(cx, cy, r, DARK), dot(cx, cy, cap, CAP), arc])


def diamond(cx: float, cy: float, spread: float, radius: float) -> str:
    points = [(cx, cy - spread), (cx, cy + spread), (cx - spread, cy), (cx + spread, cy)]
    return "\n  ".join(dot(px, py, radius, DARK) for px, py in points)


def joycon(x: float, y: float, w: float, h: float, *, left: bool, details: bool, r: float, stick_r: float) -> str:
    """Joy-Con çizimi: ince koyu konturlu gövde; sol mavide üstte çubuk, sağ kırmızıda ortanın altında.

    `details` kapalıyken (küçük simge) yalnızca gövde ve koyu çubuk dairesi çizilir.
    """
    color = BLUE if left else RED
    cx = x + w / 2 + (-w * 0.04 if left else w * 0.04)
    if not details:
        stick_y = y + h * (0.27 if left else 0.75)
        return "\n  ".join([half_pill(x, y, w, h, left=left, color=color, r=r), dot(cx, stick_y, stick_r, DARK)])
    sw = w * 0.03
    body = half_pill(x + sw / 2, y + sw / 2, w - sw, h - sw, left=left, color=color, r=r - sw / 2)
    body = body.replace("/>", f' stroke="{DARK}" stroke-width="{sw:g}" stroke-linejoin="round"/>')
    inner = x + w if left else x
    bar_x = inner + (-w * 0.3 if left else w * 0.3)
    bar_y = y + h * 0.09
    if left:
        parts = [
            body,
            rect(bar_x, bar_y, w * 0.2, w * 0.04),
            stick(cx, y + h * 0.28, stick_r),
            diamond(cx, y + h * 0.6, stick_r * 0.72, stick_r * 0.27),
            rect(cx, y + h * 0.84, w * 0.15, w * 0.15, w * 0.03),
        ]
    else:
        parts = [
            body,
            rect(bar_x, bar_y, w * 0.2, w * 0.04),
            rect(bar_x, bar_y, w * 0.04, w * 0.2),
            diamond(cx, y + h * 0.3, stick_r * 0.72, stick_r * 0.27),
            stick(cx, y + h * 0.62, stick_r),
            dot(cx, y + h * 0.85, w * 0.075, DARK),
        ]
    return "\n  ".join(parts)


def svg(width: int, height: int, comment: str, body: list[str]) -> str:
    inner = "\n  ".join(body)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f"  <!-- {comment} -->\n  {inner}\n</svg>\n"
    )


def logo(comment: str) -> str:
    colors = {"N": BLUE, "X": BLUE, "T": RED, "R": RED}
    pill_w, pill_h, gap = 84.0, 224.0, 12.0
    text, tw = word("NXTR", 8 + pill_w + gap, 16, scale_x=1.55, scale_y=pill_h / 100, colors=colors)
    right = 8 + pill_w + gap + tw + gap
    body = [
        joycon(8, 16, pill_w, pill_h, left=True, details=True, r=60, stick_r=24),
        text,
        joycon(right, 16, pill_w, pill_h, left=False, details=True, r=60, stick_r=24),
    ]
    return svg(int(right + pill_w + 8), 256, comment, body)


def square_logo(*, comment: str) -> str:
    """Kare logo: solda mavi, sağda kırmızı Joy-Con; ortada iki satır yazı ("NX" mavi, "TR" kırmızı), hizalı."""
    pill_w, top, height, gap = 64.0, 8.0, 240.0, 8.0
    text_w = 256 - 2 * (8 + pill_w + gap)
    row_gap = 10.0
    row_h = (height - row_gap) / 2
    x0 = 8 + pill_w + gap
    nx, _ = word("NX", x0, top, scale_x=text_w / 118, scale_y=row_h / 100, colors=dict.fromkeys("NX", BLUE))
    tr, _ = word(
        "TR", x0, top + row_h + row_gap, scale_x=text_w / 120, scale_y=row_h / 100, colors=dict.fromkeys("TR", RED)
    )
    body = [
        joycon(8, top, pill_w, height, left=True, details=True, r=44, stick_r=19),
        nx,
        tr,
        joycon(256 - 8 - pill_w, top, pill_w, height, left=False, details=True, r=44, stick_r=19),
    ]
    return svg(256, 256, comment, body)


def icon(*, details: bool, comment: str) -> str:
    stick = 27 if details else 30
    return svg(
        256,
        256,
        comment,
        [
            joycon(16, 20, 108, 216, left=True, details=details, r=68, stick_r=stick),
            joycon(132, 20, 108, 216, left=False, details=details, r=68, stick_r=stick),
        ],
    )


def main() -> None:
    square = square_logo(
        comment="NXTR kare logo ve uygulama simgesi (32 px ve üstü): Joy-Con'lar ve ortada NX/TR. "
        "Kaynak dosyadır; nxtr.ico ve nxtr.png packaging/make_icon.py ile üretilir."
    )
    (ICON_DIR / "nxtr.svg").write_text(square, encoding="utf-8")
    (DIR / "nxtr-kare.svg").write_text(square, encoding="utf-8")
    (ICON_DIR / "nxtr-kucuk.svg").write_text(
        icon(details=False, comment="NXTR simgesinin sadeleştirilmiş hâli (24 px ve altı): yalnızca çubuk daireleri."),
        encoding="utf-8",
    )
    # Mavi ve kırmızı iki zeminde de okunduğundan renkler aynıdır; ayrı dosya yalnızca adlandırma kolaylığı içindir.
    (DIR / "nxtr-logo.svg").write_text(logo("NXTR yatay logo (açık zemin)."), encoding="utf-8")
    (DIR / "nxtr-logo-koyu.svg").write_text(logo("NXTR yatay logo (koyu zemin)."), encoding="utf-8")


if __name__ == "__main__":
    main()
