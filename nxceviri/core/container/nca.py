"""NCA (Nintendo Content Archive) okuyucu.

Yalnızca NCA3 başlıkları desteklenir (2017 sonrası tüm yayınlar). Başlık
`header_key` ile AES-XTS, bölümler içerik anahtarıyla AES-CTR şifrelidir. İçerik
anahtarı ya başlıktaki anahtar alanından (key_area_key) ya da Rights ID varsa
bilet/title.keys'teki başlık anahtarından (titlekek) elde edilir.
Ayrıntılar: docs/formats/nca.md
"""

from __future__ import annotations

import hashlib
import logging
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum

from nxceviri.core.container.buckettree import IndirectStorage, ZeroStorage, read_bucket_tree
from nxceviri.core.container.compression import CompressedStorage, open_compressed
from nxceviri.core.container.crypto import AesCtrStorage, aes_ecb_decrypt, aes_xts_decrypt
from nxceviri.core.container.pfs0 import Pfs0
from nxceviri.core.container.storage import Storage, SubStorage
from nxceviri.core.errors import ContainerError, MissingKeyError, UnsupportedFormatError
from nxceviri.core.keys import KeySet

log = logging.getLogger(__name__)

HEADER_SIZE = 0xC00
MEDIA_UNIT = 0x200
_SPARSE_ENTRY = 0x14  # Indirect girdisiyle aynı: sanal, fiziksel, kaynak


class ContentType(IntEnum):
    PROGRAM = 0
    META = 1
    CONTROL = 2
    MANUAL = 3
    DATA = 4
    PUBLIC_DATA = 5


class FsType(IntEnum):
    ROMFS = 0
    PFS0 = 1


class EncryptionType(IntEnum):
    AUTO = 0
    NONE = 1
    XTS = 2
    CTR = 3
    CTR_EX = 4
    CTR_SKIP_LAYER_HASH = 5
    CTR_EX_SKIP_LAYER_HASH = 6


_SHA256_HASH_TYPES = (2, 5)  # HierarchicalSha256 / HierarchicalSha3256
_IVFC_HASH_TYPES = (3, 6)  # HierarchicalIntegrity / HierarchicalIntegritySha3


@dataclass(frozen=True)
class BucketTreeHeader:
    """Bir bucket tree tablosunun konumu (bölüm başına göre) ve başlığı."""

    offset: int
    size: int
    magic: bytes
    version: int
    entry_count: int

    @classmethod
    def parse(cls, raw: bytes) -> BucketTreeHeader:
        offset, size, magic, version, count, _ = struct.unpack_from("<QQ4sIiI", raw)
        return cls(offset, size, magic, version, count)

    @property
    def present(self) -> bool:
        return self.size > 0 and self.entry_count > 0


@dataclass(frozen=True)
class FsHeader:
    index: int
    start: int  # NCA içindeki mutlak bayt ofseti
    end: int
    fs_type: int
    hash_type: int
    encryption_type: int
    hash_data: bytes
    indirect: BucketTreeHeader
    aes_ctr_ex: BucketTreeHeader
    generation: int
    secure_value: int
    sparse: BucketTreeHeader
    compression: BucketTreeHeader
    sparse_physical_offset: int = 0  # seyrek bölümün dosyadaki gerçek verisinin başlangıcı
    sparse_generation: int = 0

    @property
    def size(self) -> int:
        return self.end - self.start

    @property
    def is_sparse(self) -> bool:
        """Bölüm seyrek mi (verinin bir kısmı veya tamamı yalnızca güncellemede)?"""
        return self.sparse.magic == b"BKTR"

    @property
    def ctr_upper(self) -> bytes:
        """CTR sayacının üst 8 baytı: secure_value | generation (big-endian)."""
        return self.secure_value.to_bytes(4, "big") + self.generation.to_bytes(4, "big")

    def data_region(self) -> tuple[int, int]:
        """Hash katmanları atlanmış asıl verinin (RomFS veya PFS0) bölüm içi konumu."""
        hd = self.hash_data
        if self.hash_type in _IVFC_HASH_TYPES:
            if hd[:4] != b"IVFC":
                raise ContainerError("NCA bölümü bozuk: IVFC başlığı bulunamadı.")
            (levels,) = struct.unpack_from("<I", hd, 0x0C)
            if not 2 <= levels <= 7:
                raise ContainerError("NCA bölümü bozuk: IVFC katman sayısı geçersiz.")
            off, size = struct.unpack_from("<QQ", hd, 0x10 + (levels - 2) * 0x18)
            return off, size
        if self.hash_type in _SHA256_HASH_TYPES:
            (layers,) = struct.unpack_from("<I", hd, 0x24)
            if not 1 <= layers <= 5:
                raise ContainerError("NCA bölümü bozuk: hash katman sayısı geçersiz.")
            off, size = struct.unpack_from("<QQ", hd, 0x28 + (layers - 1) * 0x10)
            return off, size
        raise UnsupportedFormatError(f"Desteklenmeyen NCA hash türü: {self.hash_type}")


def open_data_region(region: Storage, fs: FsHeader) -> Storage:
    """Veri bölgesinin son hâli: sıkıştırma katmanı (varsa) bölgenin sonundaki tabloyla açılır."""
    return open_compressed(region, fs.compression) if fs.compression.present else region


def physical_span(data: Storage, offset: int, size: int) -> tuple[int, int]:
    """Açılmış veri bölgesindeki bir aralığın sıkıştırılmış bölgedeki karşılığı."""
    return data.physical_span(offset, size) if isinstance(data, CompressedStorage) else (offset, size)


class Nca:
    """Tek bir NCA. `storage` NCA'nın ham (şifreli) baytlarıdır."""

    def __init__(
        self,
        storage: Storage,
        keys: KeySet,
        title_keys: Mapping[bytes, bytes] | None = None,
        name: str = "NCA",
    ) -> None:
        self.storage = storage
        self.name = name
        if storage.size < HEADER_SIZE:
            raise ContainerError(f"{name} bozuk: başlık için dosya çok kısa.")
        header = aes_xts_decrypt(keys.header_key, storage.read(0, HEADER_SIZE))
        magic = header[0x200:0x204]
        if magic in (b"NCA2", b"NCA0"):
            raise UnsupportedFormatError(f"{name}: eski {magic.decode()} biçimi desteklenmiyor.")
        if magic != b"NCA3":
            raise ContainerError(
                f"{name} çözülemedi: NCA başlığı okunamadı.",
                "Anahtar dosyanızdaki header_key yanlış olabilir veya dosya bozuk. "
                "prod.keys dosyasını kendi konsolunuzdan yeniden çıkarın.",
            )
        self.distribution = header[0x204]
        self.content_type = ContentType(header[0x205]) if header[0x205] <= 5 else header[0x205]
        self.key_generation = max(header[0x206], header[0x220])
        self.key_area_index = header[0x207]
        (self.content_size,) = struct.unpack_from("<Q", header, 0x208)
        (self.program_id,) = struct.unpack_from("<Q", header, 0x210)
        self.content_index = struct.unpack_from("<I", header, 0x218)[0]
        self.sdk_version = struct.unpack_from("<I", header, 0x21C)[0]
        self.rights_id = header[0x230:0x240]
        if self.content_size != storage.size:
            raise ContainerError(
                f"{name} eksik veya bozuk: başlıktaki boyut ({self.content_size:,} bayt) "
                f"dosyayla ({storage.size:,} bayt) uyuşmuyor.",
                "Oyun dosyasını yeniden kopyalayın veya çıkarın.",
            )

        self.sections: list[FsHeader] = []
        for i in range(4):
            start_mu, end_mu = struct.unpack_from("<II", header, 0x240 + i * 0x10)
            if end_mu == 0:
                continue
            fsh = header[0x400 + i * 0x200 : 0x600 + i * 0x200]
            if hashlib.sha256(fsh).digest() != header[0x280 + i * 0x20 : 0x2A0 + i * 0x20]:
                raise ContainerError(f"{name} bozuk: {i}. bölüm başlığının özeti tutmuyor.")
            gen, secure = struct.unpack_from("<II", fsh, 0x140)
            self.sections.append(
                FsHeader(
                    index=i,
                    start=start_mu * MEDIA_UNIT,
                    end=end_mu * MEDIA_UNIT,
                    fs_type=fsh[0x2],
                    hash_type=fsh[0x3],
                    encryption_type=fsh[0x4],
                    hash_data=fsh[0x8:0x100],
                    indirect=BucketTreeHeader.parse(fsh[0x100:0x120]),
                    aes_ctr_ex=BucketTreeHeader.parse(fsh[0x120:0x140]),
                    generation=gen,
                    secure_value=secure,
                    sparse=BucketTreeHeader.parse(fsh[0x148:0x168]),
                    compression=BucketTreeHeader.parse(fsh[0x178:0x198]),
                    sparse_physical_offset=struct.unpack_from("<Q", fsh, 0x168)[0],
                    sparse_generation=struct.unpack_from("<H", fsh, 0x170)[0],
                )
            )
            if self._physical_end(self.sections[-1]) > storage.size:
                raise ContainerError(f"{name} eksik: {i}. bölüm dosyanın sonunu aşıyor.")

        self._key_area = header[0x300:0x340]
        self._keys = keys
        self._title_keys = title_keys or {}
        self._content_key: bytes | None = None

    @property
    def has_rights_id(self) -> bool:
        return any(self.rights_id)

    @property
    def title_id_hex(self) -> str:
        return f"{self.program_id:016X}"

    def content_key(self) -> bytes:
        if self._content_key is not None:
            return self._content_key
        if self.has_rights_id:
            enc = self._title_keys.get(self.rights_id)
            if enc is None:
                raise MissingKeyError(
                    f"{self.name} için başlık anahtarı bulunamadı (Rights ID {self.rights_id.hex().upper()}).",
                    "NSP içindeki bilet (.tik) eksik. Kendi konsolunuzdan çıkardığınız title.keys dosyasını da seçin.",
                )
            key = aes_ecb_decrypt(self._keys.titlekek(self.key_generation), enc)
        else:
            area = aes_ecb_decrypt(self._keys.key_area_key(self.key_area_index, self.key_generation), self._key_area)
            key = area[0x20:0x30]
        self._content_key = key
        return key

    def section(self, index: int) -> FsHeader:
        for s in self.sections:
            if s.index == index:
                return s
        raise ContainerError(f"{self.name}: {index}. bölüm yok.")

    @staticmethod
    def _physical_end(fs: FsHeader) -> int:
        """Bölümün dosyada kapladığı son bayt; seyrek bölümde yalnızca gerçek veri ve tablo."""
        if not fs.is_sparse:
            return fs.end
        if fs.sparse.entry_count == 0:
            return 0
        return fs.sparse_physical_offset + fs.sparse.offset + fs.sparse.size

    def raw_section(self, fs: FsHeader) -> Storage:
        """Bölümün ham (şifreli) verisi; seyrek bölümde boş aralıklar sıfırla doldurulur."""
        if fs.is_sparse:
            return self._sparse_section(fs)
        return SubStorage(self.storage, fs.start, fs.size)

    def _sparse_section(self, fs: FsHeader) -> Storage:
        """Seyrek bölüm: tablo, sanal bölümün hangi aralıklarının dosyada olduğunu söyler.

        Ana oyun güncellemeyle birlikte dağıtıldığında, güncellemenin yeniden yazdığı veri
        base pakete konmaz. Eksik aralıklar okunursa sıfır döner; bu aralıklar yalnızca
        güncellemeyle birlikte anlamlıdır.
        """
        if fs.sparse.entry_count == 0:
            return ZeroStorage(fs.size)
        table_start = fs.sparse_physical_offset + fs.sparse.offset
        table: Storage = SubStorage(self.storage, table_start, fs.sparse.size)
        if fs.encryption_type != EncryptionType.NONE:
            upper = fs.secure_value.to_bytes(4, "big") + (fs.sparse_generation << 16).to_bytes(4, "big")
            table = AesCtrStorage(table, self.content_key(), upper, table_start)
        raw, end = read_bucket_tree(table, fs.sparse, _SPARSE_ENTRY)
        if end != fs.size:
            raise ContainerError(f"{self.name} bozuk: seyrek bölüm tablosu bölüm boyutuyla uyuşmuyor.")
        data = SubStorage(self.storage, fs.sparse_physical_offset, fs.sparse.offset)
        entries = [struct.unpack("<qqi", e) for e in raw]
        # Sıfır kaynağındaki fiziksel ofset anlamsızdır; her ofseti karşılayacak kadar büyük tutulur.
        return IndirectStorage((data, ZeroStorage(1 << 62)), entries, end)

    def ctr_section(self, fs: FsHeader) -> Storage:
        """Bölümün standart AES-CTR ile çözülmüş görünümü (CTR_EX tabloları da böyle okunur)."""
        return AesCtrStorage(self.raw_section(fs), self.content_key(), fs.ctr_upper, fs.start)

    def decrypted_section(self, fs: FsHeader) -> Storage:
        """Yama gerektirmeyen bir bölümün çözülmüş verisi (bölüm başından itibaren)."""
        enc = fs.encryption_type
        if enc == EncryptionType.NONE:
            return self.raw_section(fs)
        if enc == EncryptionType.CTR:
            return self.ctr_section(fs)
        if enc in (EncryptionType.CTR_EX, EncryptionType.CTR_EX_SKIP_LAYER_HASH):
            raise ContainerError(
                f"{self.name} bir güncelleme yamasıdır; tek başına okunamaz.",
                "Bu güncellemenin ait olduğu ana oyunu (base) da ekleyin.",
            )
        raise UnsupportedFormatError(f"{self.name}: desteklenmeyen şifreleme türü ({enc}).")

    def data_storage(self, fs: FsHeader) -> Storage:
        """Hash katmanları atlanmış asıl veri; sıkıştırma katmanı varsa açılmış hâliyle."""
        off, size = fs.data_region()
        return open_data_region(SubStorage(self.decrypted_section(fs), off, size), fs)

    def find_section(self, fs_type: FsType) -> FsHeader | None:
        return next((s for s in self.sections if s.fs_type == fs_type), None)

    def open_pfs0(self, fs: FsHeader) -> Pfs0:
        pfs_storage = self.data_storage(fs)
        try:
            return Pfs0(pfs_storage, self.name)
        except ContainerError:
            raise self._wrong_content_key() from None

    def _wrong_content_key(self) -> ContainerError:
        if self.has_rights_id:
            return ContainerError(
                f"{self.name} çözülemedi: başlık anahtarı (title key) yanlış görünüyor.",
                "title.keys dosyasındaki kayıt bu oyuna ait olmayabilir veya prod.keys'teki titlekek yanlış.",
            )
        return ContainerError(
            f"{self.name} çözülemedi: içerik anahtarı yanlış görünüyor.",
            "prod.keys dosyanızdaki key_area_key değerleri yanlış olabilir. Dosyayı yeniden çıkarın.",
        )
