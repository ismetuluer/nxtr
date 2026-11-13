"""`font` aracı (`python -m nxceviri.arac font`): elle üretilmiş küçük Unity oyunlarıyla."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nxceviri.arac import main
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import Inputs, opened_view, scan_sources
from nxceviri.core.progress import TaskContext
from nxceviri.core.qa.fonts import TURKISH_LETTERS, FontReport, font_verdict, scan_fonts
from tests import nxbuild
from tests.conftest import GameFiles
from tests.unitybuild import SYNTH_GLYPHS, build_bundle, string_table, tmp_font, tmp_font_bundle

AA = "Data/StreamingAssets/aa/Switch/"
LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
#: Yamanın kaynak glifleri (SYNTH_GLYPHS) + "ö"; böylece eksik kalan tüm harfler yamayla eklenebilir.
YAMALI_GLIFLER = {
    **{c: [(0, 0, 10, 20)] for c in LATIN},
    **SYNTH_GLYPHS,
    "ö": [(0, 0, 22, 28), (2, 33, 8, 39), (14, 33, 20, 39)],
}


def _oyun(tmp_path: Path, bundles: dict[str, bytes]) -> tuple[Path, Path]:
    keys = nxbuild.TestKeys.random()
    files = {
        "Data/globalgamemanagers": b"\0" * 8 + (22).to_bytes(4, "big") + b"\0" * 20,
        AA + "localization-string-tables-english(en)_assets_all.bundle": build_bundle(
            [string_table("UI_en", "en", 0, [(1, "Start"), (2, "Exit")])]
        ),
        **{AA + ad: veri for ad, veri in bundles.items()},
    }
    pkg = nxbuild.build_package(
        keys,
        kind="base",
        title_id=0x0100DDDD00000000,
        application_id=0x0100DDDD00000000,
        version=0,
        romfs_files=files,
        name="Font Aracı Oyunu",
    )
    nsp = tmp_path / "oyun.nsp"
    nsp.write_bytes(pkg.nsp)
    return nsp, keys.write(tmp_path / "prod.keys")


def _calistir(nsp: Path, keys: Path, *ek: str) -> None:
    assert main(["font", str(nsp), "--anahtar", str(keys), *ek]) == 0


def test_hepsi_var(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    nsp, keys = _oyun(
        tmp_path, {"fonts_assets_all.bundle": build_bundle([tmp_font("Ana SDF", LATIN + TURKISH_LETTERS)])}
    )
    _calistir(nsp, keys)
    out = capsys.readouterr().out
    assert "Ana SDF" in out
    assert "Sonuç: Türkçe harflerin tümü var: ek iş gerekmez" in out.strip().splitlines()[-1]


def test_yamalanabilir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_font_bundle([("Ana SDF", YAMALI_GLIFLER, (512, 512))])
    nsp, keys = _oyun(tmp_path, {"fonts_assets_all.bundle": bundle})
    _calistir(nsp, keys)
    out = capsys.readouterr().out
    assert "ğıİşĞŞ" in out.split("Eksik")[1].splitlines()[0].replace(" ", "")
    son = out.strip().splitlines()[-1]
    assert son.startswith("Sonuç: Eksik harfler font yamasıyla eklenebilir")
    assert "ğ ı İ ş Ğ Ş" in son


def test_yamalanamaz(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    nsp, keys = _oyun(tmp_path, {"fonts_assets_all.bundle": build_bundle([tmp_font("Ana SDF", LATIN)])})
    _calistir(nsp, keys)
    son = capsys.readouterr().out.strip().splitlines()[-1]
    assert son.startswith("Sonuç: Font yamalanamıyor: harf dönüştürme gerekir (ğ→g, ş→s, ı→i…)")
    assert "unsupported_letters" in son


def test_font_bulunamadi(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    nsp, keys = _oyun(tmp_path, {})
    _calistir(nsp, keys)
    out = capsys.readouterr().out
    assert "font bulunamadı" in out
    assert out.strip().splitlines()[-1].startswith("Sonuç: Font yamalanamıyor")


def test_json_ayni_bilgiyi_verir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_font_bundle([("Ana SDF", YAMALI_GLIFLER, (512, 512))])
    nsp, keys = _oyun(tmp_path, {"fonts_assets_all.bundle": bundle})
    _calistir(nsp, keys, "--json")
    veri = json.loads(capsys.readouterr().out)
    assert veri["sonuc"] == "yamalanabilir"
    assert veri["eksik"] == "ğıİşĞŞ"
    assert veri["yamalanabilir"] == "ğıİşĞŞ"
    assert "yamasıyla" in veri["oneri"]
    font = veri["fontlar"][0]
    assert font["ad"] == "Ana SDF"
    assert font["dosya"].endswith("fonts_assets_all.bundle")
    assert font["eksik"] == "ğıİşĞŞ"
    assert font["tur"]
    assert font["ne_yapilabilir"]
    assert font["dile_ozgu"] is False


def test_ui_ile_ayni_cekirdek(tmp_path: Path) -> None:
    """Araç ve arayüz aynı `scan_fonts` + `font_verdict` yolunu kullanır; sonuçlar eşit olmalı."""
    bundle = tmp_font_bundle([("Ana SDF", YAMALI_GLIFLER, (512, 512))])
    nsp, keys = _oyun(tmp_path, {"fonts_assets_all.bundle": bundle})
    girdi = Inputs((nsp,), load_keys(keys))
    rapor = scan_sources(girdi, TaskContext())
    with opened_view(girdi, TaskContext()) as view:
        fonts: FontReport = scan_fonts(view, rapor)
    v = font_verdict(fonts)
    assert (v.durum, v.eksik, v.yamalanabilir) == ("yamalanabilir", "ğıİşĞŞ", "ğıİşĞŞ")


def test_acilamayan_dosya(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kod = main(["font", str(tmp_path / "yok.nsp")])
    err = capsys.readouterr().err
    assert kod == 1
    assert "bulunamadı" in err
    assert "yok.nsp" in err


def test_anahtarsiz_acik_mesaj(
    game: GameFiles, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nxceviri.arac import ortak

    monkeypatch.setattr(ortak, "ayardaki_yol", lambda _a: None)
    assert main(["font", str(game.base_nsp)]) == 1
    assert "--anahtar" in capsys.readouterr().err
