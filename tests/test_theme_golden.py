"""Varsayılan ve Neon Gün Batımı QSS çıktısı donmuştur: tema altyapısı değişse de bayt bayt aynı kalmalı.

Bilerek değiştirmek için: `NXTR_GOLDEN_YAZ=1 python -m pytest tests/test_theme_golden.py` ile dosyayı yeniden üret.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from nxceviri.gui import theme

_GOLDEN = Path(__file__).parent / "data" / "qss_golden.json"
_CASES = [(p, s, pt) for p in ("Varsayılan", "Neon Gün Batımı") for s in ("light", "dark") for pt in (10, 14)]


def _qss_for(palette: str, scheme: str, pt: int) -> str:
    qss = theme._qss(theme.palette_tokens(scheme, palette), pt)
    return qss.replace((Path(tempfile.gettempdir()) / "nxtr-tema").as_posix(), "<TMP>")


def _key(case: tuple[str, str, int]) -> str:
    return f"{case[0]}|{case[1]}|{case[2]}"


def test_regenerate_golden_when_asked() -> None:
    if os.environ.get("NXTR_GOLDEN_YAZ") != "1":
        pytest.skip("yalnızca NXTR_GOLDEN_YAZ=1 ile çalışır")
    data = {_key(c): _qss_for(*c) for c in _CASES}
    _GOLDEN.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


@pytest.mark.parametrize("case", _CASES, ids=[_key(c) for c in _CASES])
def test_default_and_neon_qss_unchanged(case: tuple[str, str, int]) -> None:
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert _qss_for(*case) == golden[_key(case)]
