"""Dil kodlarının yoldan tanınması ve eşleştirilmesi; önbellek için disk alanı denetimi."""

from __future__ import annotations

import errno
from collections import namedtuple
from pathlib import Path

import pytest

from nxceviri.core.container import package
from nxceviri.core.container.package import open_package
from nxceviri.core.errors import ContainerError
from nxceviri.core.keys import load_keys
from nxceviri.core.languages import same_language
from nxceviri.core.pipeline import default_source_language, language_label, path_language
from tests.conftest import GameFiles


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("aa/Switch/localization-string-tables-english(en)_assets_all.bundle", "en"),
        ("aa/Switch/localization-asset-tables-english(unitedstates)(en-us)_assets_all.bundle", "en-us"),
        ("mesg/US/USen/menu.msbt", "en-us"),
        ("mesg/EU/EUfr/menu.msbt", "fr-eu"),
        ("Mals/CNzh.Product.sarc.zs>Msg/CNzh/a.msbt", "zh-cn"),
        ("G/Paks/G-Switch.pak>Game/Content/Localization/Game/pt-BR/Game.locres", "pt-br"),
        ("G/Paks/G-Switch.pak>Engine/Content/Localization/Engine/zh-Hans/Engine.locres", "zh-hans"),
        ("Message/Ana_Menü.msbt", None),
        ("Data/USen.txt", None),  # dosya adı klasör değildir
    ],
)
def test_path_language(path: str, expected: str | None) -> None:
    assert path_language(path) == expected


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("en", "en-us", True),  # Kong: dosya adında "en-us", tabloda "en"
        ("en-US", "en-us", True),
        ("en-us", "en-eu", False),  # Rhythm Heaven: USen ve EUen ayrı dosyalar
        ("zh-cn", "zh-tw", False),
        ("zh", "zh-hant", False),  # yazı alt etiketi ayrı bir dildir
        ("zh-Hant", "zh-hant", True),
        ("pt", "pt-br", True),
        ("de", "fr", False),
    ],
)
def test_same_language(a: str, b: str, same: bool) -> None:
    assert same_language(a, b) is same
    assert same_language(b, a) is same


def test_default_source_language_prefers_english() -> None:
    assert default_source_language(["de-de", "en-us", "fr-fr"]) == "en-us"
    assert default_source_language(["en", "en-us"]) == "en"
    assert default_source_language(["de-eu", "en-eu", "en-us", "ja-jp"]) == "en-us"
    assert default_source_language(["de", "ja"]) == "de"
    assert default_source_language([]) is None


def test_language_label_with_region() -> None:
    assert language_label("en-us") == "İngilizce (ABD) (en-us)"
    assert language_label("en-eu") == "İngilizce (Avrupa) (en-eu)"
    assert language_label("zh-hant") == "Çince (Geleneksel) (zh-hant)"
    assert language_label("xx-yy") == "xx-yy (xx-yy)"


Usage = namedtuple("Usage", "total used free")


def test_stream_ncz_refuses_when_disk_is_full(game: GameFiles, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nxceviri.core.container.package.shutil.disk_usage", lambda _p: Usage(10, 10, 1024))
    keys = load_keys(game.keys_path)
    cache = tmp_path / "önbellek"
    with open_package(game.base_nsz_stream, keys, cache_dir=cache) as pkg, pytest.raises(ContainerError) as err:
        pkg.program_nca()
    assert "Diskte yer yok" in err.value.message
    assert "Geçici Dosyaları Temizle" in err.value.user_text()
    assert not any(cache.rglob("*.nca*"))


def test_stream_ncz_disk_full_while_writing(game: GameFiles, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def full(*_args: object, **_kwargs: object) -> object:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(package, "iter_ncz_as_nca", full)
    keys = load_keys(game.keys_path)
    cache = tmp_path / "önbellek"
    with (
        open_package(game.base_nsz_stream, keys, cache_dir=cache) as pkg,
        pytest.raises(ContainerError, match="yer yok"),
    ):
        pkg.program_nca()
    assert not any(cache.rglob("*.yaziliyor"))


def test_turkish_sort_key() -> None:
    from nxceviri.core.languages import sort_key

    words = ["zeytin", "çilek", "Cevap", "dünya", "ışık", "İzmir", "hat", "iğne", "şeker", "sarı", "Item", "ice", "ğ"]
    assert sorted(words, key=sort_key) == [
        "Cevap", "çilek", "dünya", "ğ", "hat", "ışık", "ice", "iğne", "Item", "İzmir", "sarı", "şeker", "zeytin",
    ]  # fmt: skip
    assert sort_key("Item") == sort_key("item") == sort_key("İtem")  # büyük/küçük harf ve İ/I ayırt edilmez
    assert sort_key("2 Kat") < sort_key("Anahtar")  # rakamlar ve noktalama harflerden önce
