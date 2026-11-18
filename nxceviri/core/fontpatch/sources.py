"""Türkçe harflerin işaretinin (nokta, çengel, kavis) fontun hangi harfinden alınacağı: yamacıların ortak sırası.

Üç yamacı (`ttf` vektör fontlar, `tmp` TextMeshPro SDF atlası, `bmfont` bit eşlem atlas) aynı aday sırasını
izler; her yamacı işareti kendi geometrisiyle keser ve yerleştirir. Sıradaki ilk uygun aday kullanılır; hiçbiri
uygun değilse işaret çizilir. Kullanılan kaynak, sonuçta harf başına kısa bir Türkçe etiketle bildirilir.

| Harf | Sıra |
|---|---|
| ı | `i`'nin noktası silinir → (yalnızca vektör) `I` x-yüksekliğine küçültülür |
| İ | `i`'nin noktası → `ż Ż ċ Ċ ė Ė` noktası → `ö`/`Ö`'nün bir noktası → nokta (`.`) → çizilir |
| ş | `ç`'nin taban çizgisi altındaki çengeli → `Ç`'ninki → virgül (`,`) → çizilir |
| Ş | `Ç`'nin çengeli → `ç`'ninki → virgül → çizilir |
| ğ | `ă`'nın kavisi → `˘` (U+02D8) → `ŭ` / `ŏ` → `Ă` / `Ŭ` / `Ŏ` → çizilir |
| Ğ | `Ă`'nın kavisi → `˘` → `Ŭ` / `Ŏ` → `ă` / `ŭ` / `ŏ` → çizilir |

Küçük harften alınan işaret büyük harfe konduğunda ölçeklenmez; yalnızca yüksekliği taban harfe göre ayarlanır.
"""

from __future__ import annotations

#: İşaret fontun kendi şekillerinden alınamadı, program çizdi.
DRAWN = "çizildi"
#: ı: i'nin gövdesi (nokta silindi) / nokta gövdeye kaynamış, I küçültüldü / i zaten noktasız.
DOTLESS_FROM_I = "i'den nokta silindi"
DOTLESS_FROM_CAPITAL = "I küçültüldü"
DOTLESS_SAME_AS_I = "i ile aynı (noktasız)"

PERIOD, COMMA, SPACING_BREVE = ".", ",", "˘"

DOT_DONORS: tuple[str, ...] = ("i", "ż", "Ż", "ċ", "Ċ", "ė", "Ė", "ö", "Ö", PERIOD)
CEDILLA_DONORS: dict[str, tuple[str, ...]] = {"ş": ("ç", "Ç", COMMA), "Ş": ("Ç", "ç", COMMA)}
BREVE_DONORS: dict[str, tuple[str, ...]] = {
    "ğ": ("ă", SPACING_BREVE, "ŭ", "ŏ", "Ă", "Ŭ", "Ŏ"),
    "Ğ": ("Ă", SPACING_BREVE, "Ŭ", "Ŏ", "ă", "ŭ", "ŏ"),
}

#: Harf adının iyelik eki (Türkçe okunuşa göre: "i'nin", "ö'nün", "ă'nın", "ŭ'nun").
_GENITIVE = {
    **dict.fromkeys("iżŻċĊėĖçÇ", "'nin"),
    **dict.fromkeys("öÖ", "'nün"),
    **dict.fromkeys("ăĂ", "'nın"),
    **dict.fromkeys("ŭŬŏŎ", "'nun"),
}
_MARK = {"İ": "noktası", "ş": "çengeli", "Ş": "çengeli", "ğ": "kavisi", "Ğ": "kavisi"}
_PUNCTUATION = {PERIOD: "nokta işareti", COMMA: "virgül", SPACING_BREVE: "˘ işareti"}


def donors(letter: str) -> tuple[str, ...]:
    """`letter` (İ ş Ş ğ Ğ) için işaretin alınacağı harfler, öncelik sırasıyla."""
    if letter == "İ":
        return DOT_DONORS
    if letter in CEDILLA_DONORS:
        return CEDILLA_DONORS[letter]
    return BREVE_DONORS.get(letter, ())


def label(letter: str, donor: str) -> str:
    """Kaynağın kısa Türkçe etiketi: "ç'nin çengeli", "ă'nın kavisi", "virgül"; `donor` boşsa "çizildi"."""
    if not donor:
        return DRAWN
    if donor in _PUNCTUATION:
        return _PUNCTUATION[donor]
    return f"{donor}{_GENITIVE[donor]} {_MARK[letter]}"


def describe(sources: dict[str, str]) -> str:
    """Rapor satırı için: "ş: ç'nin çengeli, ğ: çizildi"."""
    return ", ".join(f"{c}: {why}" for c, why in sources.items())
