"""Ek içerik (DLC) dosya adından okunur görüntü adı türetme."""

from __future__ import annotations

import pytest

from nxceviri.core.container.display_name import readable_name

BASE = "Deneme Oyunu"


@pytest.mark.parametrize(
    ("stem", "base", "expected"),
    [
        ("Deneme Oyunu - Standard Edition [Tehlike Destesi][0100ABCD00005004][USA][v0]", "", "Tehlike Destesi"),
        ("Deneme Oyunu [Ek – Paket: Bir][0100ABCD00005004][v65536]", BASE, "Ek – Paket: Bir"),
        ("Deneme Oyunu - Ek Paket [0100ABCD00005004][EUR][v0]", BASE, "Ek Paket"),
        ("Deneme Oyunu [0100ABCD00005004][UPD][v0]", BASE, "Deneme Oyunu [0100ABCD00005004][UPD][v0]"),
        ("Deneme Oyunu: Gece Paketi", BASE, "Gece Paketi"),
        ("Bağımsız Ad", BASE, "Bağımsız Ad"),
        ("[DLC][v0]", "", "[DLC][v0]"),
    ],
)
def test_readable_name(stem: str, base: str, expected: str) -> None:
    assert readable_name(stem, base) == expected
