"""Switch içeriklerinde kullanılan AES kipleri (`cryptography` kütüphanesi üzerinden).

- Başlıklar: AES-128-XTS, 0x200 baytlık sektörler, sektör numarası *big-endian* tweak.
- Bölümler: AES-128-CTR; sayacın üst 8 baytı bölüme özgü, alt 8 baytı mutlak ofset >> 4.
- Anahtar alanı ve başlık anahtarları: AES-128-ECB.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from nxceviri.core.container.storage import Storage

XTS_SECTOR_SIZE = 0x200


def aes_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()  # noqa: S305 - biçim ECB kullanır
    return dec.update(data) + dec.finalize()


def aes_ecb_encrypt(key: bytes, data: bytes) -> bytes:
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()  # noqa: S305 - biçim ECB kullanır
    return enc.update(data) + enc.finalize()


def ctr_counter(upper: bytes, absolute_offset: int) -> bytes:
    """16 baytlık CTR sayacı: 8 bayt bölüm değeri + (ofset >> 4) big-endian."""
    return upper[:8] + (absolute_offset >> 4).to_bytes(8, "big")


def aes_ctr(key: bytes, upper: bytes, absolute_offset: int, data: bytes) -> bytes:
    """CTR şifreleme/çözme (simetriktir). `absolute_offset` 16'nın katı olmalıdır."""
    if absolute_offset % 16:
        raise ValueError("CTR ofseti 16 baytlık sınırda olmalı")
    c = Cipher(algorithms.AES(key), modes.CTR(ctr_counter(upper, absolute_offset))).encryptor()
    return c.update(data) + c.finalize()


def _xts(key: bytes, data: bytes, first_sector: int, encrypt: bool) -> bytes:
    if len(data) % XTS_SECTOR_SIZE:
        raise ValueError("XTS verisi sektör boyutunun katı olmalı")
    out = bytearray()
    for i in range(len(data) // XTS_SECTOR_SIZE):
        tweak = (first_sector + i).to_bytes(16, "big")
        cipher = Cipher(algorithms.AES(key), modes.XTS(tweak))
        ctx = cipher.encryptor() if encrypt else cipher.decryptor()
        out += ctx.update(data[i * XTS_SECTOR_SIZE : (i + 1) * XTS_SECTOR_SIZE]) + ctx.finalize()
    return bytes(out)


def aes_xts_decrypt(key: bytes, data: bytes, first_sector: int = 0) -> bytes:
    return _xts(key, data, first_sector, encrypt=False)


def aes_xts_encrypt(key: bytes, data: bytes, first_sector: int = 0) -> bytes:
    return _xts(key, data, first_sector, encrypt=True)


class AesCtrStorage(Storage):
    """Bir NCA bölümünün AES-CTR ile çözülmüş görünümü.

    `base` bölümün ham (şifreli) verisidir; `section_offset` bölümün NCA içindeki
    mutlak başlangıcıdır (sayaç mutlak ofsetle hesaplanır).
    """

    def __init__(self, base: Storage, key: bytes, upper: bytes, section_offset: int) -> None:
        self._base = base
        self._key = key
        self._upper = upper
        self._section_offset = section_offset

    @property
    def size(self) -> int:
        return self._base.size

    def _read(self, offset: int, size: int) -> bytes:
        start = offset & ~0xF
        end = min(self._base.size, (offset + size + 0xF) & ~0xF)
        raw = self._base.read(start, end - start)
        plain = aes_ctr(self._key, self._upper, self._section_offset + start, raw)
        return plain[offset - start : offset - start + size]
