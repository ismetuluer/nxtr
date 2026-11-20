"""İngilizce işlev sözcükleri ve kısaltmalar: "çevrilmemiş sözcük" ve "terim" denetimlerinde sayılmaz.

Oyun metninde "you", "the", "vs." gibi sözcükler her yerde geçer ve çoğu zaman bilinçli kalır (kısaltma, ses/söz
oyunu, arayüz etiketi). Bunları Türkçe sözlükte yok diye işaretlemek ya da kendi başına satır diye terim saymak
yanlış alarm üretir. Liste küçük harfli ve noktasızdır; karşılaştırma `is_function_word` ile yapılır.
"""

from __future__ import annotations

#: Küçük harfli, noktasız. Yalnızca İngilizce işlev sözcükleri ve yaygın kısaltmalar (içerik sözcüğü yok).
ENGLISH_FUNCTION_WORDS = frozenset(
    (  # noqa: SIM905 - uzun liste tek satır tek sözcük olmasın diye boşlukla ayrılmış metin
        "a an the and or but nor so yet of to in on at by for from with without into onto "
        "as is am are was were be been being it its it's i i'm i'll i've i'd me my we our you you're you'll "
        "you've you'd your yours he him his she her hers they them their this that these those there here who whom "
        "what which when where why how do does did don't doesn't didn't not ok okay can't won't "
        "would should could might must have has had if then than too very just also vs v etc eg ie mr mrs ms dr"
    ).split()
)


def is_function_word(word: str) -> bool:
    """`word` (büyük/küçük harf ve sondaki nokta fark etmez) bir İngilizce işlev sözcüğü ya da kısaltması mı."""
    return word.strip(".").replace("’", "'").lower() in ENGLISH_FUNCTION_WORDS
