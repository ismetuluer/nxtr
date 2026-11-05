"""Format tespiti, iç içe arşiv taraması ve motor tahmini."""

from __future__ import annotations

from pathlib import Path

import pytest
import zstandard

from nxceviri.core.container.package import KIND_BASE, open_package
from nxceviri.core.container.romfs import RomFs
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import ContentTree, GameView, LayeredRomFs, RomFsLayer, build_game_view
from nxceviri.core.errors import OperationCancelled
from nxceviri.core.formats.detection import FileKind, TextLikelihood, detect
from nxceviri.core.formats.scanner import ScanEntry, guess_engine, scan_view
from nxceviri.core.keys import load_keys
from nxceviri.core.progress import CancelToken, TaskContext
from tests import nxbuild
from tests.conftest import GameFiles
from tests.nxbuild import build_sarc, yaz0_literal

UNITY_SERIALIZED_HEAD = b"\0" * 8 + (22).to_bytes(4, "big") + b"\0" * 20
LOCRES = bytes.fromhex("0E147475674A03FC4A15909DC3377F1B") + b"\0" * 8


@pytest.mark.parametrize(
    ("path", "head", "kind", "likelihood"),
    [
        ("Message/a.msbt", b"MsgStdBn\0\0", FileKind.MSBT, TextLikelihood.HIGH),
        ("a.msbp", b"MsgPrjBn", FileKind.OTHER, TextLikelihood.NONE),
        (
            "Data/aa/localization-string-tables-english(en)_assets_all.bundle",
            b"UnityFS\0\0",
            FileKind.UNITY,
            TextLikelihood.HIGH,
        ),
        ("Data/aa/animations-cat.bundle", b"UnityFS\0\0", FileKind.UNITY, TextLikelihood.NONE),
        ("Data/aa/littextureblend.bundle", b"UnityFS\0\0", FileKind.UNITY, TextLikelihood.NONE),
        ("Data/resources.assets", UNITY_SERIALIZED_HEAD, FileKind.UNITY, TextLikelihood.MEDIUM),
        ("Data/globalgamemanagers", UNITY_SERIALIZED_HEAD, FileKind.UNITY, TextLikelihood.MEDIUM),
        ("Data/resources.assets.resS", b"\0" * 16, FileKind.UNITY, TextLikelihood.NONE),
        ("Game/Content/Localization/Game/tr/Game.locres", LOCRES, FileKind.UNREAL, TextLikelihood.HIGH),
        ("Game/Content/x.uasset", b"\xc1\x83\x2a\x9e\0\0", FileKind.UNREAL, TextLikelihood.NONE),
        ("Data/config.json", b'{"a": 1}', FileKind.TEXT, TextLikelihood.MEDIUM),
        ("Data/dialogue.json", b'{"a": 1}', FileKind.TEXT, TextLikelihood.HIGH),
        ("Text/menü.csv", "id,metin\n1,ğüş".encode(), FileKind.TEXT, TextLikelihood.HIGH),
        ("x.txt", b"\xff\xfeh\0i\0", FileKind.TEXT, TextLikelihood.MEDIUM),
        ("x.txt", b"\x00\x01\x02binary", FileKind.OTHER, TextLikelihood.NONE),
        ("pack.szs", b"Yaz0\0\0\0\x10", FileKind.ARCHIVE, TextLikelihood.NONE),
        ("pack.sarc", b"SARC\x00\x14", FileKind.ARCHIVE, TextLikelihood.NONE),
        ("pack.zs", b"\x28\xb5\x2f\xfd", FileKind.ARCHIVE, TextLikelihood.NONE),
        ("tex.bntx", b"BNTX\0\0", FileKind.OTHER, TextLikelihood.NONE),
        ("bilinmeyen.dat", b"\x01\x02\x03\x04", FileKind.OTHER, TextLikelihood.NONE),
    ],
)
def test_detect(path: str, head: bytes, kind: FileKind, likelihood: TextLikelihood) -> None:
    det = detect(path, head)
    assert det.kind == kind, det
    assert det.likelihood == likelihood, det


def test_detect_unreal_pak_by_footer() -> None:
    assert detect("Game/Content/Paks/a.pak", b"\0" * 16, b"\0" * 100 + b"\xe1\x12\x6f\x5a").kind == FileKind.UNREAL
    assert detect("Game/Content/Paks/a.pak", b"\0" * 16, b"\0" * 100).kind == FileKind.OTHER


def test_utf8_head_cut_in_middle_of_character() -> None:
    head = ("a" * 63 + "ğ").encode()[:64]  # ğ iki bayt, ikincisi kesilmiş
    assert detect("x.txt", head).kind == FileKind.TEXT


def _view(files: dict[str, bytes]) -> GameView:
    romfs = RomFs(MemoryStorage(nxbuild.build_romfs(files)))
    tree = ContentTree("0100000000001000", "Ana oyun", LayeredRomFs([RomFsLayer(KIND_BASE, romfs)]))
    return GameView("0100000000001000", "Deneme", 0, None, [tree])


def test_scan_nested_archives() -> None:
    inner_sarc = build_sarc({"Msg/a.msbt": b"MsgStdBn" + b"\0" * 8, "Msg/b.msbt": b"MsgStdBn" + b"\1" * 8})
    files = {
        "Mals/TRtr.Product.sarc.zs": zstandard.ZstdCompressor().compress(inner_sarc),
        "Layout/menu.szs": yaz0_literal(build_sarc({"blyt/menü.bflyt": b"FLYT", "metin.txt": b"merhaba"})),
        "Data/oyun.json": b'{"ad": "x"}',
        "Data/bozuk.zs": b"\x28\xb5\x2f\xfd bozuk",
    }
    report = scan_view(_view(files))
    paths = {e.path: e for e in report.entries}
    assert "Mals/TRtr.Product.sarc.zs>TRtr.Product.sarc>Msg/a.msbt" in paths
    assert paths["Mals/TRtr.Product.sarc.zs>TRtr.Product.sarc>Msg/b.msbt"].kind == FileKind.MSBT
    assert paths["Layout/menu.szs>menu>metin.txt"].kind == FileKind.TEXT
    assert paths["Mals/TRtr.Product.sarc.zs"].kind == FileKind.ARCHIVE
    assert report.counts[FileKind.MSBT] == 2
    assert any("bozuk.zs" in w for w in report.warnings)
    cand = [e.path for e in report.text_candidates]
    assert cand[0].endswith(".msbt")  # yüksek olasılıklılar önce
    assert report.engine.engine == "nintendo"


def test_scan_cancel() -> None:
    token = CancelToken()
    token.cancel()
    with pytest.raises(OperationCancelled):
        scan_view(_view({"a.txt": b"x"}), TaskContext(token=token))


def test_scan_real_pipeline(game: GameFiles) -> None:
    keys = load_keys(game.keys_path)
    progress: list[int] = []
    with open_package(game.base_nsp, keys) as base, open_package(game.update_nsp, keys) as upd:
        report = scan_view(build_game_view([base, upd]), TaskContext(lambda d, _t, _m: progress.append(d)))
    assert report.game_name == "Deneme Oyunu"
    assert report.update_version == 65536
    kinds = {e.path: e.kind for e in report.entries}
    assert kinds["Message/Ana_Menü.msbt"] == FileKind.MSBT
    assert kinds["Data/yeni_dosya.txt"] == FileKind.TEXT
    assert kinds["Data/strings.csv"] == FileKind.TEXT
    assert progress == sorted(progress)


def _entries(*specs: tuple[str, str, str]) -> list[ScanEntry]:
    return [ScanEntry("0", p, 1, k, d, "none", "base") for p, k, d in specs]


def test_engine_guess() -> None:
    unity = guess_engine(
        _entries(
            ("Data/globalgamemanagers", "unity", "Unity serileştirilmiş dosya"),
            ("Data/Managed/Metadata/global-metadata.dat", "unity", "Unity IL2CPP meta verisi"),
            ("Data/aa/x.bundle", "unity", "Unity AssetBundle"),
        )
    )
    assert (unity.engine, unity.confidence) == ("unity", "high")
    unreal = guess_engine(_entries(("G/Content/Paks/a.pak", "unreal", "Unreal .pak arşivi")))
    assert (unreal.engine, unreal.confidence) == ("unreal", "medium")  # .pak + Content/Paks klasörü
    assert guess_engine([]).engine == "unknown"
    assert guess_engine(_entries(("a.bin", "other", "Bilinmeyen"))).confidence == "none"


def test_large_table_scan_is_fast(tmp_path: Path) -> None:
    """Binlerce dosyalık bir RomFS hızlı taranır (sanal görünüm kopyalama yapmaz)."""
    import time

    files = {f"Message/bölüm_{i:05d}.msbt": b"MsgStdBn" + i.to_bytes(4, "little") for i in range(5000)}
    view = _view(files)
    start = time.monotonic()
    report = scan_view(view)
    assert len(report.entries) == 5000
    assert time.monotonic() - start < 10
