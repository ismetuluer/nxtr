"""İşaretli metin üretimi: sembolleri göster/gizle, satır sonu boşluk vurgusu ve kontrol kodu çipleri.

Buradaki her şey yalnızca **çizimdir**: çeviri metni hiçbir zaman değiştirilmez, kopyalama ve kayıt ham metin
(`⟦n⟧` dahil) üzerinde yapılır. `marked_html` bir metni `QTextDocument`'in çizeceği HTML'e çevirir:

- `symbols` açıkken boşluk `·`, sekme `→`, bölünmez boşluk `°` ve satır sonu `¶` olarak görünür (genişlik korunur,
  metin kaymaz); satırın sonundaki boşluklar uyarı zeminiyle işaretlenir. `·` ve `→` sözcük sınırı olarak kalır:
  `·` bir harf gibi davranıp kaydırmayı sözcük ortasına çekmesin diye ardına sıfır genişlikli bir bölme fırsatı konur.
- `wrong` aralıkları (yazım hatalı sözcükler) tema "danger" renginde alt çizgiyle işaretlenir; hücre çizicisi bunu
  dalgalı çizgiye çevirir (Qt'nin HTML ayrıştırıcısı dalgalı çizgiyi bilmez).
- `chips` açıkken her `⟦n⟧` kod türüne göre renkli bir çip olur (simge + numara); kapalıyken ham kod görünür.

Saf işlevlerdir (arayüz nesnesi bilmez), bu yüzden kolay test edilir.
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence

from nxceviri.core.translate.codekinds import (
    KIND_LINE_BREAK,
    KIND_OTHER,
    KIND_PAGE_BREAK,
    KIND_STYLE,
    KIND_SYMBOL,
    KIND_VARIABLE,
    KindOf,
)
from nxceviri.core.translate.placeholders import TOKEN_RE

#: Kod türü → çipteki simge.
KIND_GLYPHS: dict[str, str] = {
    KIND_LINE_BREAK: "↵",
    KIND_PAGE_BREAK: "§",
    KIND_VARIABLE: "◆",
    KIND_SYMBOL: "★",
    KIND_STYLE: "●",
    KIND_OTHER: "◇",
}
#: Kod türü → çip rengi (tema belirteci).
CHIP_TOKENS: dict[str, str] = {
    KIND_LINE_BREAK: "accent",
    KIND_PAGE_BREAK: "warning",
    KIND_VARIABLE: "success",
    KIND_SYMBOL: "redacted",
    KIND_STYLE: "muted",
    KIND_OTHER: "muted",
}

_TRAILING_RE = re.compile(r"[ \t]+$")
#: Sıfır genişlikli bölme fırsatı (U+200B): `·` sembolünden sonra kaydırma sözcük sınırında olabilsin.
ZWSP = "\u200b"


def chip_glyph(kind: str) -> str:
    """Çip simgesi; bilinmeyen (kullanıcı tanımlı) türler `diğer` gibidir."""
    return KIND_GLYPHS.get(kind, KIND_GLYPHS[KIND_OTHER])


def chip_color(kind: str, tokens: Mapping[str, str]) -> str:
    return tokens[CHIP_TOKENS.get(kind, CHIP_TOKENS[KIND_OTHER])]


def code_spans(text: str) -> list[tuple[int, int, int]]:
    """Metindeki her `⟦n⟧` için `(başlangıç, bitiş, n)`."""
    return [(m.start(), m.end(), int(m.group(1))) for m in TOKEN_RE.finditer(text)]


def trailing_space_spans(text: str) -> list[tuple[int, int]]:
    """Her satırın sonundaki boşluk ve sekme aralıkları (`(başlangıç, bitiş)`, metin ofsetleriyle)."""
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in text.split("\n"):
        match = _TRAILING_RE.search(line)
        if match:
            spans.append((offset + match.start(), offset + match.end()))
        offset += len(line) + 1
    return spans


def marked_html(
    text: str,
    kind_of: KindOf,
    tokens: Mapping[str, str],
    *,
    symbols: bool,
    chips: bool,
    single_line: bool = False,
    wrong: Sequence[tuple[int, int]] = (),
) -> str:
    """Metni `QTextDocument` için HTML'e çevirir. `single_line`: satır sonu satır içinde kalır (kaydırma kapalı).

    `wrong`: alt çizgi çekilecek metin aralıkları (başlangıç, bitiş), örneğin yazım hatalı sözcükler."""
    muted = tokens["muted"]
    warning_bg = tokens["warning_bg"]
    trailing: set[int] = set()
    if symbols:
        for start, end in trailing_space_spans(text):
            trailing.update(range(start, end))

    def mark(glyph: str, index: int) -> str:
        style = f"color:{muted};"
        if index in trailing:
            style += f"background-color:{warning_bg};"
        return f'<span style="{style}">{glyph}</span>'

    wrong_at: set[int] = set()
    for start, end in wrong:
        wrong_at.update(range(start, end))
    wrong_open = f'<span style="text-decoration:underline;text-decoration-color:{tokens["danger"]};">'
    break_after = "" if single_line else ZWSP

    def char(i: int) -> str:
        ch = text[i]
        if ch == "\r":
            if i + 1 < len(text) and text[i + 1] == "\n":
                return ""  # "\r\n" tek satır sonudur
            ch = "\n"
        if ch == "\n":
            if symbols:
                return mark("¶", i) + ("" if single_line else "<br>")
            return " " if single_line else "<br>"
        if symbols and ch == " ":
            return mark("·", i) + break_after
        if symbols and ch == "\t":
            return mark("→", i) + "\t"
        if ch == " ":
            return mark("°", i) if symbols else "&nbsp;"
        return html.escape(ch, quote=False)

    def run(start: int, end: int) -> str:
        out: list[str] = []
        inside = False
        for i in range(start, end):
            if (i in wrong_at) != inside:
                inside = not inside
                out.append(wrong_open if inside else "</span>")
            out.append(char(i))
        if inside:
            out.append("</span>")
        return "".join(out)

    parts: list[str] = []
    pos = 0
    for start, end, number in code_spans(text):
        parts.append(run(pos, start))
        if chips:
            kind = kind_of(number)
            style = f"color:{chip_color(kind, tokens)};background-color:{tokens['selection']};font-weight:600;"
            parts.append(f'<span style="{style}">&nbsp;{chip_glyph(kind)}{number}&nbsp;</span>')
        else:
            parts.append(html.escape(text[start:end], quote=False))
        pos = end
    parts.append(run(pos, len(text)))
    return f'<p style="white-space:pre-wrap;margin:0;">{"".join(parts)}</p>'
