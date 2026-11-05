"""Zstandard sıkıştırmalı dosyaları açma ve sıkıştırma."""

from __future__ import annotations

import io

import zstandard

from nxceviri.core.errors import ArchiveError

MAGIC = b"\x28\xb5\x2f\xfd"


def decompress(data: bytes, max_size: int) -> bytes:
    """Bir veya birden çok zstd çerçevesini açar; `max_size`'ı aşarsa hata verir."""
    reader = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data), read_across_frames=True)
    out = bytearray()
    try:
        while True:
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            out += chunk
            if len(out) > max_size:
                raise ArchiveError(f"ZSTD verisi çok büyük (>{max_size:,} bayt); bu aşamada atlanıyor.")
    except zstandard.ZstdError as exc:
        if "dictionary" in str(exc).lower():
            raise ArchiveError("ZSTD verisi bir sözlük (dictionary) gerektiriyor; açılamadı.") from None
        raise ArchiveError("ZSTD verisi bozuk veya desteklenmeyen biçimde.") from None
    return bytes(out)


def compress(data: bytes, level: int = 19) -> bytes:
    """Tek çerçeveli zstd; içerik boyutu çerçeve başlığına yazılır."""
    return zstandard.ZstdCompressor(level=level, write_content_size=True).compress(data)
