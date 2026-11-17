"""Oyun içindeki bir dosyayı, iç içe yolundan (arşiv içindekiler dahil) okuma.

Yol biçimi tarayıcınınkiyle aynıdır: `dış.sarc.zs>…>a.msbt`. İlk parça bir Unreal `.pak` ise
pak tamamen okunmaz: yalnızca dizini ve istenen girdi okunur (pak'lar GB'larca olabilir). NNI
(`data-en.ni>LOC/…/X.XSO`), CPK (`<ad>_US.CPK>MsgSheet/X.fms`) ve WAD
(`dr1_data.wad>Dr1/data/us/script/X.lin`) arşivleri de aynı biçimde okunur. Eklentilerin taşıdığı arşiv biçimleri
(`ArchiveFormat`, `formats/base.py`) yerleşiklerden önce denenir; okuyucuya oyunun geçerli biçimleri verilir
(`registry.member_reader`), böylece eklentinin `oyunlar` sınırı burada da uygulanır.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence

from nxceviri.core.archives import cpk, nested, nni, psb_archive, wad
from nxceviri.core.archives.pak import PakFile
from nxceviri.core.container.storage import MemoryStorage, Storage
from nxceviri.core.container.view import LayeredRomFs
from nxceviri.core.errors import ArchiveError
from nxceviri.core.formats.base import ArchiveFormat, GameFiles, MemberArchive

#: Eklenti arşivinin `detect`'ine verilen baş bölümün boyutu.
ARCHIVE_HEAD_SIZE = 4096


def is_pak_path(path: str) -> bool:
    return path.split(nested.SEPARATOR, 1)[0].lower().endswith(".pak")


def is_psb_archive_path(path: str) -> bool:
    """`alldata.psb.m>system/config/menu_item.psb.m` gibi, PSB arşivinin (mdf) içindeki bir üyenin yolu."""
    parts = nested.split(path)
    return len(parts) > 1 and parts[0].lower().endswith(psb_archive.INDEX_SUFFIX)


def is_nni_path(path: str) -> bool:
    """`ys_data/archives/data-en.ni>LOC/EN/…/X.XSO` gibi, NNI arşivinin içindeki bir üyenin yolu."""
    parts = nested.split(path)
    return len(parts) > 1 and parts[0].lower().endswith(nni.INDEX_SUFFIX)


def is_cpk_path(path: str) -> bool:
    """`<ad>_US.CPK>MsgSheet/<ad>.fms` gibi, CPK arşivinin içindeki bir üyenin yolu."""
    parts = nested.split(path)
    return len(parts) > 1 and parts[0].lower().endswith(cpk.SUFFIX)


def is_wad_path(path: str) -> bool:
    """`dr1_data.wad>Dr1/data/us/script/e00_001_000.lin` gibi, WAD arşivinin içindeki bir üyenin yolu."""
    parts = nested.split(path)
    return len(parts) > 1 and parts[0].lower().endswith(wad.SUFFIX)


def is_plugin_archive_path(path: str, archives: Sequence[ArchiveFormat]) -> bool:
    """Bir eklenti arşivinin (uzantısı `archives`'tan birine uyan dosya) içindeki üyenin yolu."""
    parts = nested.split(path)
    return len(parts) > 1 and any(parts[0].lower().endswith(fmt.suffixes) for fmt in archives)


def is_member_path(path: str, archives: Sequence[ArchiveFormat] = ()) -> bool:
    """Büyük arşivlerin içindeki (pak, PSB, NNI, CPK, WAD; eklentilerin `archives` biçimleri) üyeler: dış dosya
    tamamen okunmadan yalnızca üye okunur."""
    return (
        is_plugin_archive_path(path, archives)
        or is_pak_path(path)
        or is_psb_archive_path(path)
        or is_nni_path(path)
        or is_cpk_path(path)
        or is_wad_path(path)
    )


class RomFsFiles:
    """Oyunun RomFS dosyaları, eklenti arşiv biçimine verilen biçimde (`GameFiles`)."""

    def __init__(self, romfs: LayeredRomFs) -> None:
        self._romfs = romfs

    @property
    def files(self) -> Collection[str]:
        return self._romfs.files.keys()

    def open(self, path: str) -> Storage:
        return self._romfs.open(path)


class OverlayFiles:
    """Oyun dosyalarının üstüne moda yazılacak dosyalar bindirilmiş görünüm: dışa aktarmada yeniden kurulan arşivin
    oyunda nasıl okunacağını denetlemek için."""

    def __init__(self, base: GameFiles, outputs: Mapping[str, bytes]) -> None:
        self._base = base
        self._outputs = outputs

    @property
    def files(self) -> Collection[str]:
        return {*self._base.files, *self._outputs}

    def open(self, path: str) -> Storage:
        data = self._outputs.get(path)
        if data is not None:
            return MemoryStorage(data)
        source = self._base.open(path)
        return source if isinstance(source, Storage) else MemoryStorage(source.read_all())


class MemberReader:
    """Aynı işlem boyunca açılan pak, PSB, NNI ve CPK dizinlerini saklar.

    `code`, oyunun çalıştırılabilir kodunu veren işlevdir (`ContentTree.code`); PSB arşivlerinin
    anahtarı yalnızca buradan bulunur.
    """

    def __init__(
        self,
        romfs: LayeredRomFs,
        code: Callable[[], bytes | None] | None = None,
        archives: Sequence[ArchiveFormat] = (),
    ) -> None:
        self.romfs = romfs
        self._code = code
        self.archives = tuple(archives)
        self._formats: dict[str, ArchiveFormat | None] = {}
        self._plugin: dict[str, MemberArchive] = {}
        self._paks: dict[str, PakFile] = {}
        self._psb_archive: dict[str, psb_archive.PsbArchive] = {}
        self._nni: dict[str, nni.NniArchive] = {}
        self._cpk: dict[str, cpk.CpkFile] = {}
        self._wad: dict[str, wad.WadArchive] = {}

    def pak(self, top: str) -> PakFile:
        if top not in self._paks:
            self._paks[top] = PakFile(self.romfs.open(top), top)
        return self._paks[top]

    def psb_archive(self, top: str) -> psb_archive.PsbArchive:
        if top not in self._psb_archive:
            data_name = psb_archive.PsbArchive.data_name(top)
            if data_name not in self.romfs.files:
                raise ArchiveError(
                    f"{top} için veri dosyası ({data_name}) oyunda bulunamadı.",
                    "Oyunun ana dosyasını ve varsa güncellemesini birlikte ekleyin.",
                )
            index = self.romfs.open(top).read_all()
            code = self._code() if self._code is not None else None
            key = psb_archive.find_key(code, top, index) if code is not None else None
            if key is None:
                raise ArchiveError(
                    f"{top} arşivinin anahtarı oyunun kodunda bulunamadı.",
                    "Oyunun güncelleme dosyasını da ekleyin; dosyalar kendi konsolunuzdan alınmış olmalı.",
                )
            self._psb_archive[top] = psb_archive.PsbArchive(top, index, self.romfs.open(data_name), key)
        return self._psb_archive[top]

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

    def plugin_format(self, top: str) -> ArchiveFormat | None:
        """`top` dosyasını tanıyan eklenti arşiv biçimi (uzantı ve `detect`); yoksa None."""
        if top not in self._formats:
            found = None
            candidates = [fmt for fmt in self.archives if top.lower().endswith(fmt.suffixes)]
            if candidates and top in self.romfs.files:
                storage = self.romfs.open(top)
                head = storage.read(0, min(ARCHIVE_HEAD_SIZE, storage.size))
                found = next((fmt for fmt in candidates if fmt.detect(top, head)), None)
            self._formats[top] = found
        return self._formats[top]

    def plugin_archive(self, top: str) -> MemberArchive:
        """`top` eklenti arşivini açar (aynı okuyucu boyunca bir kez)."""
        if top not in self._plugin:
            fmt = self.plugin_format(top)
            if fmt is None:
                raise ArchiveError(f"{top} hiçbir eklentinin arşiv biçimi olarak tanınmadı.")
            self._plugin[top] = fmt.open(RomFsFiles(self.romfs), top)
        return self._plugin[top]

    def read(self, path: str) -> bytes:
        parts = nested.split(path)
        if len(parts) > 1 and self.plugin_format(parts[0]) is not None:
            return nested.open_inner(self.plugin_archive(parts[0]).read(parts[1]), parts[2:])
        if len(parts) > 1 and is_pak_path(path):
            return nested.open_inner(self.pak(parts[0]).read(parts[1]), parts[2:])
        if len(parts) > 1 and is_psb_archive_path(path):
            return nested.open_inner(self.psb_archive(parts[0]).read(parts[1]), parts[2:])
        if len(parts) > 1 and is_nni_path(path):
            return nested.open_inner(self.nni(parts[0]).read(parts[1]), parts[2:])
        if len(parts) > 1 and is_cpk_path(path):
            return nested.open_inner(self.cpk(parts[0]).read(parts[1]), parts[2:])
        if len(parts) > 1 and is_wad_path(path):
            return nested.open_inner(self.wad(parts[0]).read(parts[1]), parts[2:])
        return nested.open_inner(self.romfs.open(parts[0]).read_all(), parts[1:])
