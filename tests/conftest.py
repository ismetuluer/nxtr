"""Ortak test verileri: rastgele anahtarlar ve elle üretilmiş oyun paketleri.

Klasör adları bilerek Türkçe karakter içerir (ç ğ ı İ ö ş ü).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import zstandard
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from tests import nxbuild


@pytest.fixture(autouse=True)
def _private_app_data(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kurtarma kopyaları, günlükler ve önbellek testlerde gerçek kullanıcı klasörüne yazılmasın."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path_factory.mktemp("appdata")))


@pytest.fixture(autouse=True)
def _free_top_level_widgets() -> Iterator[None]:
    """Her testten sonra kalan üst düzey pencereleri gerçekten siler.

    `deleteLater` olayı `processEvents` ile işlenmez; silinmeyen pencereler yığılınca `app.setStyleSheet` (yazı boyutu
    ve tema değişimi her widget'ı yeniden düzenler) tam test setinde dakikalar sürüyordu."""
    yield
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    for widget in app.topLevelWidgets():
        widget.hide()  # close() olmaz: ana pencere kaydedilmemiş değişiklik sorusu açıp testi bekletir
        widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


BASE_TID = 0x0100ABCD12340000
UPDATE_TID = BASE_TID | 0x800
DLC_TID = BASE_TID + 0x1000 + 1

MENU_MSBT = nxbuild.build_msbt(
    [
        ("Menu_Start", ["Start Game"]),
        ("Menu_Hello", ["Hello ", ("tag", 0, 3, b"\x01\x00"), "Link", ("end", 0, 3, b""), "!"]),
    ]
)
COMMON_MSBT = nxbuild.build_msbt([("Yes", ["Yes"]), ("No", ["No"]), ("Wait", ["Please wait", ("tag", 0, 4, b"")])])

BASE_FILES: dict[str, bytes] = {
    "Message/Ana_Menü.msbt": MENU_MSBT,
    "Mals/TRtr.Product.sarc.zs": zstandard.ZstdCompressor().compress(
        nxbuild.build_sarc({"Msg/Ortak.msbt": COMMON_MSBT, "Msg/Bozuk.msbt": b"MsgStdBn" + b"\xff" * 40})
    ),
    "Data/config.json": b'{"dil": "en", "s\xc3\xbcr\xc3\xbcm": 1}',
    "Data/strings.csv": b"id,text\n1,Hello\n",
    "Data/level1.bin": bytes(range(256)) * 8,
    "Data/büyük_doku.bntx": b"BNTX" + b"\x11" * 3000,
    "Sound/ses.bwav": b"BWAV" + b"\x22" * 100,
}

UPDATE_FILES: dict[str, bytes] = {
    **BASE_FILES,
    "Message/Ana_Menü.msbt": nxbuild.build_msbt(  # değişti: bir metin güncellendi, biri eklendi
        [
            ("Menu_Start", ["Start Adventure"]),
            ("Menu_Hello", ["Hello ", ("tag", 0, 3, b"\x01\x00"), "Link", ("end", 0, 3, b""), "!"]),
            ("Menu_New", ["New option"]),
        ]
    ),
    "Data/yeni_dosya.txt": "Yeni metin: çğıİöşü".encode(),  # eklendi
}

DLC_FILES: dict[str, bytes] = {"DLC/Message/ek.msbt": b"MsgStdBn" + b"\x05" * 40}


@dataclass
class GameFiles:
    keys: nxbuild.TestKeys
    keys_path: Path
    folder: Path
    base_nsp: Path
    update_nsp: Path
    dlc_nsp: Path
    base_nsz_block: Path
    base_nsz_stream: Path
    update_nsz: Path


@pytest.fixture(scope="session")
def game(tmp_path_factory: pytest.TempPathFactory) -> GameFiles:
    folder = tmp_path_factory.mktemp("Oyun Dosyaları ğüşıöçİ")
    keys = nxbuild.TestKeys.random()
    keys_path = keys.write(folder / "prod.keys")

    base = nxbuild.build_package(
        keys, kind="base", title_id=BASE_TID, application_id=BASE_TID, version=0, romfs_files=BASE_FILES
    )
    assert base.program is not None
    patch = nxbuild.build_patch_nca(keys, BASE_TID, base.program, nxbuild.build_romfs(UPDATE_FILES))
    update = nxbuild.build_package(
        keys,
        kind="update",
        title_id=UPDATE_TID,
        application_id=BASE_TID,
        version=65536,
        display_version="1.0.1",
        program=patch,
    )
    dlc = nxbuild.build_package(
        keys, kind="dlc", title_id=DLC_TID, application_id=BASE_TID, version=0, romfs_files=DLC_FILES
    )
    paths = {}
    for name, data in {
        "Deneme Oyunu [base].nsp": base.nsp,
        "Deneme Oyunu [update].nsp": update.nsp,
        "Deneme Oyunu [dlc].nsp": dlc.nsp,
        "Deneme Oyunu [base] blok.nsz": nxbuild.nsp_to_nsz(base, block_mode=True),
        "Deneme Oyunu [base] akış.nsz": nxbuild.nsp_to_nsz(base, block_mode=False),
        "Deneme Oyunu [update].nsz": nxbuild.nsp_to_nsz(update, block_mode=True),
    }.items():
        p = folder / name
        p.write_bytes(data)
        paths[name] = p
    return GameFiles(
        keys=keys,
        keys_path=keys_path,
        folder=folder,
        base_nsp=paths["Deneme Oyunu [base].nsp"],
        update_nsp=paths["Deneme Oyunu [update].nsp"],
        dlc_nsp=paths["Deneme Oyunu [dlc].nsp"],
        base_nsz_block=paths["Deneme Oyunu [base] blok.nsz"],
        base_nsz_stream=paths["Deneme Oyunu [base] akış.nsz"],
        update_nsz=paths["Deneme Oyunu [update].nsz"],
    )
