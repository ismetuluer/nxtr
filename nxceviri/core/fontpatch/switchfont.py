"""Switch oyun fontlarını (`.bfttf` / `.bfotf`) yamalama.

Switch oyunlarında gömülü fontlar `.zs` uzantılıdır ve üç katmanlıdır:

1. zstd ile sıkıştırılmış gövde,
2. 8 baytlık başlık (`d9 9b 87 1a` + 4 bayt; anlamı çözülemedi, **aynen korunur**),
3. 4 baytlık anahtarla tekrarlı XOR ile şifrelenmiş sfnt (TTF/OTF) verisi.

Tarayıcı `.zs` dosyasının içini ayrı bir iç dosya (`X.bfttf.zs>X.bfttf`) olarak da gösterir; zstd'si açılmış bu
veri (başlıkla başlayan) da kabul edilir ve yamalanmış hâli yine sıkıştırılmadan döner.

Anahtar dosyadan dosyaya değişir; bu yüzden tahmin edilmez: her aday anahtar sfnt olarak açılır ve
`cmap` tablosu okunabiliyorsa doğru kabul edilir. Glif üretimi `fontpatch.ttf` tarafından yapılır
(CID anahtarlı CFF fontlar dahil); bu modül yalnızca kapsayıcıyı çözer, yamalar ve yeniden paketler.

Yamalanan font yeniden açılıp eklenen harflerin `cmap`te göründüğü doğrulanır; doğrulama geçmezse
hata yükseltilir. Hiçbir harf eklenemezse özgün baytlar döndürülür.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import zstandard as zstd
from fontTools.ttLib import TTFont

from nxceviri.core.fontpatch import ttf

#: sfnt sürüm sihirleri: TrueType, CFF/OpenType, Apple TrueType, koleksiyon.
MAGICS = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")
#: Kapsayıcı başlığının ilk dört baytı (zstd'si açılmış veri bununla başlar).
HEADER_MAGIC = bytes.fromhex("d99b871a")
#: Oyunun kendi dosyalarıyla aynı sıkıştırma oranını korumak için.
_LEVEL = 19


@dataclass(frozen=True)
class FontPatchResult:
    """Yamalanmış `.zs` verisi ve harf raporu."""

    data: bytes  # yamalanmış font; hiçbir şey eklenmediyse özgün baytlar
    added: str = ""
    skipped: dict[str, str] = field(default_factory=dict)


def _is_sfnt(data: bytes) -> bool:
    """Veri geçerli bir sfnt mi (en az bir okunabilir Unicode cmap'i var mı)?"""
    try:
        font = TTFont(io.BytesIO(data))
    except Exception:  # bozuk aday anahtar normaldir
        return False
    try:
        return bool(font.getBestCmap())
    except Exception:
        return False
    finally:
        font.close()


def _decompress(data: bytes) -> bytes:
    """zstd gövdesini açar; çerçevede boyut yoksa akış olarak okur."""
    dctx = zstd.ZstdDecompressor()
    try:
        return dctx.decompress(data)
    except zstd.ZstdError:
        with dctx.stream_reader(io.BytesIO(data)) as reader:
            return reader.read()


def is_compressed(data: bytes) -> bool:
    """Veri zstd çerçevesi mi (`.zs` dosyası), yoksa açılmış kapsayıcı mı?"""
    return not data.startswith(HEADER_MAGIC)


def unwrap(data: bytes) -> tuple[bytes, bytes, bytes]:
    """`.zs` verisini ya da zstd'si açılmış kapsayıcıyı (8 baytlık başlık, sfnt, XOR anahtarı) olarak açar."""
    if is_compressed(data):
        try:
            raw = _decompress(data)
        except zstd.ZstdError as exc:
            raise ValueError(f"font zstd ile açılamadı: {exc}") from exc
    else:
        raw = data
    if len(raw) < 12:
        raise ValueError("font verisi çok kısa")
    header, payload = raw[:8], raw[8:]
    for magic in MAGICS:
        key = bytes(a ^ b for a, b in zip(payload[:4], magic, strict=True))
        sfnt = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
        if _is_sfnt(sfnt):
            return header, sfnt, key
    raise ValueError("font şifresi çözülemedi (sfnt sihri tanınmadı)")


def wrap(header: bytes, sfnt: bytes, key: bytes, compress: bool = True) -> bytes:
    """sfnt'yi anahtarla şifreleyip başlığın arkasına koyar; `compress` ise zstd ile sıkıştırır."""
    if len(key) != 4:
        raise ValueError("XOR anahtarı 4 bayt olmalı")
    payload = bytes(b ^ key[i % 4] for i, b in enumerate(sfnt))
    return zstd.ZstdCompressor(level=_LEVEL).compress(header + payload) if compress else header + payload


def patch_font(data: bytes, letters: str = ttf.PATCHABLE) -> FontPatchResult:
    """`.zs` fontuna eksik Türkçe harfleri ekler; eklenemeyenler raporda döner."""
    header, sfnt, key = unwrap(data)
    result = ttf.patch_font(sfnt, letters, allow_cjk=True)
    if not result.added:
        return FontPatchResult(data, "", dict(result.skipped))
    packed = wrap(header, result.data, key, compress=is_compressed(data))
    _verify(packed, result.added)
    return FontPatchResult(packed, result.added, dict(result.skipped))


def _verify(data: bytes, added: str) -> None:
    """Paketlenen font yeniden açılır: eklenen her harf cmap'te olmalı."""
    _header, sfnt, _key = unwrap(data)
    remaining, _skipped = ttf.plan(sfnt, added)
    if remaining:
        raise ValueError(f"yamalanan fontta görünmeyen harfler: {remaining}")


def patch_file(src: Path, dest: Path, letters: str = ttf.PATCHABLE) -> FontPatchResult:
    """`src` dosyasını yamalayıp `dest` konumuna yazar (hedef klasör oluşturulur)."""
    result = patch_font(src.read_bytes(), letters)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(result.data)
    return result
