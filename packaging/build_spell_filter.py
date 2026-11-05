"""Türkçe yazım süzgecini hunspell-tr sözlüğünden üretir (MPL-2.0; https://github.com/tdd-ai/hunspell-tr).

    python packaging/build_spell_filter.py <tr_TR.aff> <tr_TR.dic>

Sözlük her kökün yanında geçerli ekleri tek tek sayılı bayraklarla listeler (her bayrak tek bir ek dizisidir, çıkarma
ve koşul yoktur); kök + her ek ve kökün kendisi toplam ~6,1 milyon sözcük biçimidir. Biçimler Türkçe küçük harfe
çevrilip `nxceviri/assets/spell/tr.bloom` süzgecine yazılır. Çıktı depoya eklenir; sözlük güncellenmedikçe yeniden
üretmek gerekmez. Dosya küçük olsun diye yanlış olumlu oranı %0,1'dir.
"""

from __future__ import annotations

import sys
from pathlib import Path

from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import turkish_lower

OUT = Path(__file__).resolve().parent.parent / "nxceviri" / "assets" / "spell" / "tr.bloom"
ERROR_RATE = 0.001


def read_suffixes(aff: Path) -> dict[str, str]:
    """`SFX <bayrak> 0 <ek> .` satırlarından bayrak → ek. Başka biçimdeki satır sözlüğün değiştiğini gösterir."""
    out: dict[str, str] = {}
    for line in aff.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "SFX":
            flag, strip, add, cond = parts[1:5]
            if strip != "0" or cond != ".":
                raise SystemExit(f"Beklenmeyen ek kuralı (çıkarma/koşul var): {line}")
            out[flag] = "" if add == "0" else add
    return out


def entries(dic: Path) -> list[tuple[str, list[str]]]:
    lines = dic.read_text(encoding="utf-8").splitlines()[1:]  # ilk satır sözcük sayısı
    out = []
    for line in lines:
        stem, _, flags = line.partition("/")
        if stem:
            out.append((turkish_lower(stem), flags.split(",") if flags else []))
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    suffixes = read_suffixes(Path(argv[1]))
    stems = entries(Path(argv[2]))
    total = sum(1 + len(flags) for _, flags in stems)
    print(f"{len(stems)} kök, {len(suffixes)} ek, en çok {total} sözcük biçimi")
    bloom = BloomFilter.sized(total, ERROR_RATE)
    for stem, flags in stems:
        bloom.add(stem)
        for flag in flags:
            suffix = suffixes.get(flag)
            if suffix is None:
                raise SystemExit(f"Tanımsız bayrak: {flag} ({stem})")
            bloom.add(stem + suffix)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = bloom.to_bytes()
    OUT.write_bytes(data)
    print(f"{OUT} yazıldı ({len(data) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
