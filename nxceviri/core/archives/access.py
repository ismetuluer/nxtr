"""Oyun içindeki bir dosyayı, iç içe yolundan (arşiv içindekiler dahil) okuma.

Yol biçimi tarayıcınınkiyle aynıdır: `dış.sarc.zs>…>a.msbt`. İlk parça bir Unreal `.pak` ise
pak tamamen okunmaz: yalnızca dizini ve istenen girdi okunur (pak'lar GB'larca olabilir). Falcom NNI
(`data-en.ni>LOC/…/X.XSO`), CRI CPK (`Unicorn_US.CPK>MsgSheet/X.fms`) ve Spike Chunsoft WAD
(`dr1_data.wad>Dr1/data/us/script/X.lin`) arşivleri de aynı biçimde okunur.
"""

from __future__ import annotations

from collections.abc import Callable

from nxceviri.core.archives import cpk, m2, nested, nni, wad
from nxceviri.core.archives.pak import PakFile
from nxceviri.core.container.view import LayeredRomFs
from nxceviri.core.errors import ArchiveError


def is_pak_path(path: str) -> bool:
    return path.split(nested.SEPARATOR, 1)[0].lower().endswith(".pak")


def is_m2_path(path: str) -> bool:
    """`alldata.psb.m>system/config/menu_item.psb.m` gibi, M2 arşivinin içindeki bir üyenin yolu."""
    parts = nested.split(path)
    return len(parts) > 1 and parts[0].lower().endswith(m2.INDEX_SUFFIX)


def is_nni_path(path: str) -> bool:
    """`ys_data/archives/data-en.ni>LOC/EN/…/X.XSO` gibi, Falcom NNI arşivinin içindeki bir üyenin yolu."""
    parts = nested.split(path)
    return len(parts) > 1 and parts[0].lower().endswith(nni.INDEX_SUFFIX)


def is_cpk_path(path: str) -> bool:
    """`Unicorn_US.CPK>MsgSheet/UcSysMsg.fms` gibi, CRI CPK arşivinin içindeki bir üyenin yolu."""
    parts = nested.split(path)
    return len(parts) > 1 and parts[0].lower().endswith(cpk.SUFFIX)


def is_wad_path(path: str) -> bool:
    """`dr1_data.wad>Dr1/data/us/script/e00_001_000.lin` gibi, Spike Chunsoft WAD arşivinin içindeki bir üyenin yolu."""
    parts = nested.split(path)
    return len(parts) > 1 and parts[0].lower().endswith(wad.SUFFIX)


def is_member_path(path: str) -> bool:
    """Büyük arşivlerin içindeki (pak, M2, NNI, CPK, WAD) üyeler: dış dosya tamamen okunmadan yalnızca üye okunur."""
    return is_pak_path(path) or is_m2_path(path) or is_nni_path(path) or is_cpk_path(path) or is_wad_path(path)


class MemberReader:
    """Aynı işlem boyunca açılan pak, M2, NNI ve CPK dizinlerini saklar.

    `code`, oyunun çalıştırılabilir kodunu veren işlevdir (`ContentTree.code`); M2 arşivlerinin
    anahtarı yalnızca buradan bulunur.
    """

    def __init__(self, romfs: LayeredRomFs, code: Callable[[], bytes | None] | None = None) -> None:
        self.romfs = romfs
        self._code = code
        self._paks: dict[str, PakFile] = {}
        self._m2: dict[str, m2.M2Archive] = {}
        self._nni: dict[str, nni.NniArchive] = {}
        self._cpk: dict[str, cpk.CpkFile] = {}
        self._wad: dict[str, wad.WadArchive] = {}

    def pak(self, top: str) -> PakFile:
        if top not in self._paks:
            self._paks[top] = PakFile(self.romfs.open(top), top)
        return self._paks[top]

    def m2(self, top: str) -> m2.M2Archive:
        if top not in self._m2:
            data_name = m2.M2Archive.data_name(top)
            if data_name not in self.romfs.files:
                raise ArchiveError(
                    f"{top} için veri dosyası ({data_name}) oyunda bulunamadı.",
                    "Oyunun ana dosyasını ve varsa güncellemesini birlikte ekleyin.",
                )
            index = self.romfs.open(top).read_all()
            code = self._code() if self._code is not None else None
            key = m2.find_key(code, top, index) if code is not None else None
            if key is None:
                raise ArchiveError(
                    f"{top} arşivinin anahtarı oyunun kodunda bulunamadı.",
                    "Oyunun güncelleme dosyasını da ekleyin; dosyalar kendi konsolunuzdan alınmış olmalı.",
                )
            self._m2[top] = m2.M2Archive(top, index, self.romfs.open(data_name), key)
        return self._m2[top]

    def nni(self, top: str) -> nni.NniArchive:
        if top not in self._nni:
            data_name = nni.data_name(top)
            if data_name not in self.romfs.files:
                raise ArchiveError(
                    f"{top} için veri dosyası ({data_name}) oyunda bulunamadı.",
                    "Oyunun ana dosyasını ve varsa güncellemesini birlikte ekleyin.",
                )
            self._nni[top] = nni.NniArchive(top, self.romfs.open(top).read_all(), self.romfs.open(data_name))
        return self._nni[top]

    def cpk(self, top: str) -> cpk.CpkFile:
        if top not in self._cpk:
            self._cpk[top] = cpk.CpkFile(self.romfs.open(top), top)
        return self._cpk[top]

    def wad(self, top: str) -> wad.WadArchive:
        if top not in self._wad:
            self._wad[top] = wad.WadArchive(self.romfs.open(top), top)
        return self._wad[top]

    def read(self, path: str) -> bytes:
        parts = nested.split(path)
        if len(parts) > 1 and is_pak_path(path):
            return nested.open_inner(self.pak(parts[0]).read(parts[1]), parts[2:])
        if len(parts) > 1 and is_m2_path(path):
            return nested.open_inner(self.m2(parts[0]).read(parts[1]), parts[2:])
        if len(parts) > 1 and is_nni_path(path):
            return nested.open_inner(self.nni(parts[0]).read(parts[1]), parts[2:])
        if len(parts) > 1 and is_cpk_path(path):
            return nested.open_inner(self.cpk(parts[0]).read(parts[1]), parts[2:])
        if len(parts) > 1 and is_wad_path(path):
            return nested.open_inner(self.wad(parts[0]).read(parts[1]), parts[2:])
        return nested.open_inner(self.romfs.open(parts[0]).read_all(), parts[1:])
