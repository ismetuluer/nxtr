"""Addressables kataloğunda değiştirilen paketlerin CRC denetimini kapatma.

Unity Addressables, `AssetBundleRequestOptions.m_Crc` sıfırdan farklıysa yerel paketi
`AssetBundle.LoadFromFileAsync(yol, crc)` ile açar ve CRC tutmazsa yükleme başarısız olur.
Mod, paketin baytlarını değiştirdiği için katalogdaki CRC artık eşleşmez; çeviri oyunda
görünmez. Çözüm: katalogdaki ilgili kayıtların CRC'sini sıfırlamak (sıfır = denetim yok).

Katalogda `m_ExtraDataString` alanı base64'tür. Çözülen baytlar, `SerializationUtilities`
biçiminde art arda kayıtlardır ve `m_EntryDataString` içindeki konumlar bu baytlara **bayt
ofsetiyle** bağlıdır. Bu yüzden kayıt uzunluğu asla değiştirilmez: CRC değeri `0` yazılıp
kalan haneler boşlukla doldurulur (JSON'da boşluk geçerlidir).
"""

from __future__ import annotations

import base64
import binascii
import json
import re

from nxceviri.core.errors import NxError

#: `SerializationUtilities.ObjectType.JsonObject`
_JSON_OBJECT = 0x07
_REQUEST_OPTIONS = "AssetBundleRequestOptions"
_EXTRA_KEY_RE = re.compile(rb'("m_ExtraDataString"\s*:\s*")([A-Za-z0-9+/=]*)"')
_CRC_RE = re.compile(r'("m_Crc"\s*:\s*)(\d+)')


class CatalogError(NxError):
    """Addressables kataloğu beklenen biçimde değil."""


def patch_catalog_crc(data: bytes, sizes: set[int]) -> tuple[bytes, list[int]]:
    """Boyutu `sizes` içinde olan ve CRC'si sıfır olmayan paket kayıtlarının CRC'sini sıfırlar.

    Döndürür: (yeni katalog baytları, CRC'si sıfırlanan paket boyutları). Eşleşme yoksa
    `data` aynen döner. Kayıtların bayt uzunluğu korunur.
    """
    match = _EXTRA_KEY_RE.search(data)
    if match is None:
        raise CatalogError("Addressables kataloğunda 'm_ExtraDataString' alanı yok.")
    try:
        blob = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CatalogError("Addressables kataloğunun ek verisi çözülemedi.") from exc
    patched, fixed = _patch_extra(blob, sizes)
    if not fixed:
        return data, []
    encoded = base64.b64encode(patched)
    out = data[: match.start(2)] + encoded + data[match.end(2) :]
    return out, fixed


def _patch_extra(blob: bytes, sizes: set[int]) -> tuple[bytes, list[int]]:
    out = bytearray(blob)
    fixed: list[int] = []
    pos = 0
    while pos < len(blob):
        tag = blob[pos]
        pos += 1
        if tag != _JSON_OBJECT:
            pos = _skip_value(blob, pos, tag)
            continue
        _assembly, pos = _read_short_string(blob, pos)
        class_name, pos = _read_short_string(blob, pos)
        if pos + 4 > len(blob):
            raise CatalogError("Addressables kataloğunun kayıt uzunluğu okunamadı.")
        length = int.from_bytes(blob[pos : pos + 4], "little")
        pos += 4
        if length < 0 or pos + length > len(blob):
            raise CatalogError("Addressables kataloğunun kaydı beklenen uzunlukta değil.")
        raw = blob[pos : pos + length]
        pos += length
        if not class_name.endswith(_REQUEST_OPTIONS.encode("ascii")):
            continue
        try:
            record = json.loads(raw.decode("utf-16-le"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CatalogError("Addressables kataloğundaki paket kaydı okunamadı.") from exc
        size = record.get("m_BundleSize")
        crc = record.get("m_Crc")
        if not isinstance(size, int) or not isinstance(crc, int) or not crc or size not in sizes:
            continue
        text = raw.decode("utf-16-le")
        patched = _zero_crc(text)
        new_raw = patched.encode("utf-16-le")
        if len(new_raw) != length:
            raise CatalogError("Addressables kataloğundaki CRC alanı eşit uzunlukta düzeltilemedi.")
        out[pos - length : pos] = new_raw
        fixed.append(size)
    return bytes(out), fixed


def _read_short_string(data: bytes, pos: int) -> tuple[bytes, int]:
    """Tek bayt uzunluklu ASCII metin (assembly/class adı)."""
    if pos >= len(data):
        raise CatalogError("Addressables kataloğunun kaydı eksik.")
    length = data[pos]
    pos += 1
    if pos + length > len(data):
        raise CatalogError("Addressables kataloğunun kaydı eksik.")
    return data[pos : pos + length], pos + length


def _skip_value(data: bytes, pos: int, tag: int) -> int:
    """JSON dışı ek veri türlerini (`SerializationUtilities`) atlar."""
    if tag in (0, 1):  # AsciiString / UnicodeString: 4 bayt uzunluk + veri
        if pos + 4 > len(data):
            raise CatalogError("Addressables kataloğunun ek verisi eksik.")
        length = int.from_bytes(data[pos : pos + 4], "little")
        pos += 4 + length
    elif tag == 2:  # UInt16
        pos += 2
    elif tag in (3, 4):  # UInt32 / Int32
        pos += 4
    elif tag in (5, 6):  # Hash128 / Type: 1 bayt uzunluk + veri
        if pos >= len(data):
            raise CatalogError("Addressables kataloğunun ek verisi eksik.")
        pos += 1 + data[pos]
    else:
        raise CatalogError("Addressables kataloğunda bilinmeyen ek veri türü.")
    if pos > len(data):
        raise CatalogError("Addressables kataloğunun ek verisi eksik.")
    return pos


def _zero_crc(text: str) -> str:
    """`"m_Crc":<sayı>` değerini, metin uzunluğunu koruyarak sıfırlar."""
    match = _CRC_RE.search(text)
    if match is None:
        raise CatalogError("Addressables kataloğundaki paket kaydında 'm_Crc' alanı yok.")
    digits = match.group(2)
    if int(digits) == 0:
        raise CatalogError("Addressables kataloğundaki CRC zaten sıfır.")
    replacement = match.group(1) + "0" + " " * (len(digits) - 1)
    return text[: match.start()] + replacement + text[match.end() :]
