"""Testler için elle üretilmiş Unity AssetBundle'ları (gerçek oyun dosyası kullanılmaz).

Unity Localization'ın `StringTable` ve `SharedTableData` MonoBehaviour'larını, tip ağacı
(typetree) içeren sürüm 22 bir SerializedFile'a koyar ve sıkıştırmasız bir UnityFS
bundle'ına sarar. Tip ağacı blob'u ve nesne verisi UnityPy'nin kendi yazıcılarıyla
üretilir; kabuk (başlık, meta veri, bundle) burada elle yazılır.
"""

from __future__ import annotations

import base64
import json
import struct
from typing import Any

import UnityPy
from UnityPy.helpers.TypeTreeHelper import write_typetree
from UnityPy.helpers.TypeTreeNode import TypeTreeNode
from UnityPy.streams import EndianBinaryWriter

ALIGN = 0x4000
UNITY_VERSION = "6000.3.15f1"


def _string(level: int, name: str) -> list[tuple[int, str, str, int, int, int]]:
    return [
        (level, "string", name, -1, 0x8000, 0),
        (level + 1, "Array", "Array", -1, ALIGN, 1),
        (level + 2, "int", "size", 4, 0, 0),
        (level + 2, "char", "data", 1, 0, 0),
    ]


def _pptr(level: int, type_name: str, name: str) -> list[tuple[int, str, str, int, int, int]]:
    return [
        (level, f"PPtr<{type_name}>", name, 12, 0, 0),
        (level + 1, "int", "m_FileID", 4, 0, 0),
        (level + 1, "SInt64", "m_PathID", 8, 0, 0),
    ]


def _behaviour_header() -> list[tuple[int, str, str, int, int, int]]:
    return [
        (0, "MonoBehaviour", "Base", -1, 0x8000, 0),
        *_pptr(1, "GameObject", "m_GameObject"),
        (1, "UInt8", "m_Enabled", 1, ALIGN, 0),
        *_pptr(1, "MonoScript", "m_Script"),
        *_string(1, "m_Name"),
    ]


def _vector(level: int, type_name: str, name: str, element: list[tuple[int, str, str, int, int, int]]) -> list[Any]:
    return [
        (level, type_name, name, -1, 0, 0),
        (level + 1, "Array", "Array", -1, ALIGN, 1),
        (level + 2, "int", "size", 4, 0, 0),
        *element,
    ]


STRING_TABLE_NODES = [
    *_behaviour_header(),
    (1, "LocaleIdentifier", "m_LocaleId", -1, 0, 0),
    *_string(2, "m_Code"),
    *_pptr(1, "$SharedTableData", "m_SharedData"),
    *_vector(
        1,
        "TableEntryData",
        "m_TableData",
        [(3, "TableEntryData", "data", -1, 0, 0), (4, "SInt64", "m_Id", 8, 0, 0), *_string(4, "m_Localized")],
    ),
]

SHARED_TABLE_NODES = [
    *_behaviour_header(),
    *_string(1, "m_TableCollectionName"),
    *_vector(
        1,
        "SharedTableEntry",
        "m_Entries",
        [(3, "SharedTableEntry", "data", -1, 0, 0), (4, "SInt64", "m_Id", 8, 0, 0), *_string(4, "m_Key")],
    ),
]

OTHER_NODES = [*_behaviour_header(), (1, "int", "m_Value", 4, 0, 0)]

TEXT_ASSET_NODES = [(0, "TextAsset", "Base", -1, 0x8000, 0), *_string(1, "m_Name"), *_string(1, "m_Script")]

#: Unity `Font` nesnesi (gömülü TTF/OTF); yalnızca font yamasının okuduğu alanlar.
FONT_OBJECT_NODES = [
    (0, "Font", "Base", -1, 0x8000, 0),
    *_string(1, "m_Name"),
    *_vector(1, "vector", "m_FontData", [(3, "UInt8", "data", 1, 0, 0)]),
]

TMP_FONT_NODES = [
    *_behaviour_header(),
    (1, "int", "m_AtlasPopulationMode", 4, 0, 0),
    *_vector(
        1,
        "TMP_Character",
        "m_CharacterTable",
        [(3, "TMP_Character", "data", -1, 0, 0), (4, "unsigned int", "m_Unicode", 4, 0, 0)],
    ),
]


def _node(spec: list[tuple[int, str, str, int, int, int]]) -> TypeTreeNode:
    nodes = [
        {
            "m_Level": level,
            "m_Type": typ,
            "m_Name": name,
            "m_ByteSize": size,
            "m_Version": 1,
            "m_TypeFlags": tflags,
            "m_Index": i,
            "m_MetaFlag": meta,
            "m_RefTypeHash": 0,
            "m_VariableCount": 0,
        }
        for i, (level, typ, name, size, meta, tflags) in enumerate(spec)
    ]
    return TypeTreeNode.from_list(nodes)  # type: ignore[arg-type]


def _base(name: str) -> dict[str, Any]:
    return {
        "m_GameObject": {"m_FileID": 0, "m_PathID": 0},
        "m_Enabled": 1,
        "m_Script": {"m_FileID": 1, "m_PathID": 77},
        "m_Name": name,
    }


def string_table(
    name: str, locale: str, shared_path_id: int, entries: list[tuple[int, str]]
) -> tuple[str, dict[str, Any]]:
    tree = {
        **_base(name),
        "m_LocaleId": {"m_Code": locale},
        "m_SharedData": {"m_FileID": 2, "m_PathID": shared_path_id},
        "m_TableData": [{"m_Id": i, "m_Localized": text} for i, text in entries],
    }
    return "string", tree


def shared_table(collection: str, keys: list[tuple[int, str]]) -> tuple[str, dict[str, Any]]:
    tree = {
        **_base(collection + " Shared Data"),
        "m_TableCollectionName": collection,
        "m_Entries": [{"m_Id": i, "m_Key": k} for i, k in keys],
    }
    return "shared", tree


def tmp_font(name: str, chars: str, dynamic: bool = False) -> tuple[str, dict[str, Any]]:
    """TextMeshPro font varlığı (yalnızca glif denetiminin okuduğu alanlar)."""
    tree = {
        **_base(name),
        "m_AtlasPopulationMode": 1 if dynamic else 0,
        "m_CharacterTable": [{"m_Unicode": ord(c)} for c in chars],
    }
    return "font", tree


def other_behaviour(name: str) -> tuple[str, dict[str, Any]]:
    return "other", {**_base(name), "m_Value": 42}


def text_asset(name: str, script: str) -> tuple[str, dict[str, Any]]:
    """Düz metin varlığı (TextAsset): altyazı (SRT) ve TSV tabloları böyle saklanır."""
    return "text", {"m_Name": name, "m_Script": script}


_NODES = {
    "string": STRING_TABLE_NODES,
    "shared": SHARED_TABLE_NODES,
    "other": OTHER_NODES,
    "font": TMP_FONT_NODES,
    "text": TEXT_ASSET_NODES,
    "fontobj": FONT_OBJECT_NODES,
}
#: MonoBehaviour dışındaki nesne türlerinin Unity sınıf kimlikleri
_CLASS_IDS = {"text": 49, "fontobj": 128}


def font_object(name: str, data: bytes) -> tuple[str, dict[str, Any]]:
    """Gömülü TTF/OTF taşıyan `Font` nesnesi."""
    return "fontobj", {"m_Name": name, "m_FontData": list(data)}


def _serialized_file(objects: list[tuple[int, str, dict[str, Any]]]) -> bytes:
    kinds = sorted({kind for _pid, kind, _tree in objects})
    type_index = {kind: i for i, kind in enumerate(kinds)}
    roots = {kind: _node(_NODES[kind]) for kind in kinds}

    meta = EndianBinaryWriter(endian="<")
    meta.write_string_to_null(UNITY_VERSION)
    meta.write_int(38)  # hedef platform: Switch
    meta.write_boolean(True)  # typetree var
    meta.write_int(len(kinds))
    for i, kind in enumerate(kinds):
        class_id = _CLASS_IDS.get(kind, 114)  # varsayılan MonoBehaviour
        meta.write_int(class_id)
        meta.write_boolean(False)
        meta.write_short(-1)
        if class_id == 114:
            meta.write_bytes(bytes([i + 1]) * 16)  # script id (yalnızca MonoBehaviour)
        meta.write_bytes(bytes([0xA0 + i]) * 16)  # eski tip özeti
        roots[kind].dump_blob(meta, 22)
        meta.write_int(0)  # tip bağımlılıkları
    data = EndianBinaryWriter(endian="<")
    meta.write_int(len(objects))
    for path_id, kind, tree in sorted(objects, key=lambda o: o[0]):
        obj = EndianBinaryWriter(endian="<")
        write_typetree(tree, roots[kind], obj)
        meta.align_stream(4)
        meta.write_long(path_id)
        meta.write_long(data.Position)
        meta.write_u_int(len(obj.bytes))
        meta.write_int(type_index[kind])
        data.write_bytes(obj.bytes)
        data.align_stream(8)
    meta.write_int(0)  # script tipleri
    meta.write_int(0)  # dış dosyalar
    meta.write_int(0)  # başvuru tipleri
    meta.write_string_to_null("")
    header_size = 48
    data_offset = header_size + len(meta.bytes)
    data_offset += -data_offset % 16
    file_size = data_offset + len(data.bytes)
    head = struct.pack(">IIIIB3xIqqq", 0, 0, 22, 0, 0, len(meta.bytes), file_size, data_offset, 0)
    body = head + meta.bytes
    return bytes(body + b"\0" * (data_offset - len(body)) + data.bytes)


def build_bundle(objects: list[tuple[str, dict[str, Any]]], compress: bool = True) -> bytes:
    """MonoBehaviour'lardan bir UnityFS bundle'ı üretir. `compress` ise UnityPy ile LZ4'e çevrilir."""
    numbered = [(i + 1, kind, tree) for i, (kind, tree) in enumerate(objects)]
    sf = _serialized_file(numbered)
    name = b"CAB-nxceviri-test\0"
    info = b"\0" * 16 + struct.pack(">iIIH", 1, len(sf), len(sf), 0)
    info += struct.pack(">iqqI", 1, 0, len(sf), 4) + name
    head = b"UnityFS\0" + struct.pack(">I", 8) + b"5.x.x\0" + UNITY_VERSION.encode() + b"\0"
    fixed_len = len(head) + 8 + 12
    pad = -fixed_len % 16
    total = fixed_len + pad + len(info) + len(sf)
    raw = head + struct.pack(">qIII", total, len(info), len(info), 0x40) + b"\0" * pad + info + sf
    if not compress:
        return bytes(raw)
    bundle: Any = UnityPy.load(raw).file
    return bytes(bundle.save(packer="lz4"))


# --- Addressables kataloğu: paket kayıtları (`m_ExtraDataString`) --------------------------


def bundle_record(size: int, crc: int, hash_: str = "") -> dict[str, Any]:
    """`AssetBundleRequestOptions` kaydı (katalogda CRC denetimi için gereken alanlar)."""
    return {
        "m_Hash": hash_,
        "m_Crc": crc,
        "m_Timeout": 0,
        "m_ChunkedTransfer": False,
        "m_RedirectLimit": -1,
        "m_RetryCount": 0,
        "m_BundleName": "0123456789abcdef0123456789abcdef",
        "m_AssetLoadMode": 0,
        "m_BundleSize": size,
        "m_UseCrcForCachedBundles": True,
        "m_UseUWRForLocalBundles": False,
        "m_ClearOtherCachedVersionsWhenLoaded": False,
    }


def addressables_catalog(records: list[dict[str, Any]]) -> bytes:
    """Gerçek katalogla aynı biçimde `m_ExtraDataString` taşıyan küçük bir catalog.json."""
    extra = bytearray()
    for record in records:
        raw = json.dumps(record).encode("utf-16-le")
        assembly = b"Unity.ResourceManager, Version=0.0.0.0, Culture=neutral, PublicKeyToken=null"
        class_name = b"UnityEngine.ResourceManagement.ResourceProviders.AssetBundleRequestOptions"
        extra += bytes([0x07, len(assembly)]) + assembly
        extra += bytes([len(class_name)]) + class_name
        extra += len(raw).to_bytes(4, "little") + raw
    catalog = {
        "m_LocatorId": "AddressablesMainContentCatalog",
        "m_InternalIds": [],
        "m_ExtraDataString": base64.b64encode(bytes(extra)).decode("ascii"),
    }
    return json.dumps(catalog, separators=(",", ":")).encode("utf-8")


def catalog_records(data: bytes) -> list[dict[str, Any]]:
    """`catalog.json` içindeki paket kayıtlarını (`m_ExtraDataString`) çözer."""
    catalog = json.loads(data)
    blob = base64.b64decode(catalog["m_ExtraDataString"])
    records: list[dict[str, Any]] = []
    pos = 0
    while pos < len(blob):
        assert blob[pos] == 0x07
        pos += 1
        assembly_len = blob[pos]
        pos += 1 + assembly_len
        class_len = blob[pos]
        pos += 1 + class_len
        json_len = int.from_bytes(blob[pos : pos + 4], "little")
        pos += 4
        records.append(json.loads(blob[pos : pos + json_len].decode("utf-16-le")))
        pos += json_len
    return records


# --- I2 Localization: tip ağacı silinmiş dosya (resources.assets gibi) ---------------------

I2Term = tuple[str, int, list[str]]  # (terim adı, TermType, dillere göre metinler)


def _w_str(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<i", len(raw)) + raw + b"\0" * (-len(raw) % 4)


def _w_strs(items: list[str]) -> bytes:
    return struct.pack("<i", len(items)) + b"".join(_w_str(s) for s in items)


def i2_source_raw(terms: list[I2Term], languages: list[tuple[str, str]], layout: str = "A", name: str = "") -> bytes:
    """I2 `LanguageSource` MonoBehaviour'unun ham baytları (Unity serileştirme kurallarıyla).

    Düzen A: Term, TermType, Description, Languages, Languages_Touch, Flags (I2 2.6).
    Düzen B: Term, TermType, Languages, Flags, Languages_Touch (I2 2.8).
    """
    out = struct.pack("<iq", 0, 0) + struct.pack("<B3x", 1) + struct.pack("<iq", 1, 88) + _w_str(name)
    out += _w_str("https://script.google.com/örnek") + _w_str("anahtar") + _w_str("Tablo") + _w_str("1")
    out += struct.pack("<if", 1, 5.0)  # GoogleUpdateFrequency, GoogleUpdateDelay
    out += struct.pack("<i", len(terms))
    for term, term_type, texts in terms:
        flags = bytes(len(texts))
        flag_block = struct.pack("<i", len(flags)) + flags + b"\0" * (-len(flags) % 4)
        touch = _w_strs([""] * len(texts))
        if layout == "A":
            out += _w_str(term) + struct.pack("<i", term_type) + _w_str("") + _w_strs(texts) + touch + flag_block
        else:
            out += _w_str(term) + struct.pack("<i", term_type) + _w_strs(texts) + flag_block + touch
    out += struct.pack("<i", 0)  # CaseInsensitiveTerms (bool, hizalı)
    out += struct.pack("<i", len(languages))
    for lang_name, code in languages:
        out += _w_str(lang_name) + _w_str(code) + struct.pack("<B3x", 0)
    out += struct.pack("<i", 0) + struct.pack("<B3x", 1)  # Assets (boş), NeverDestroy
    return out


def text_asset_raw(name: str, script: str) -> bytes:
    """Tip ağacı olmayan dosyadaki TextAsset (m_Name, m_Script)."""
    return _w_str(name) + _w_str(script)


#: Despelote `Locoliser` altyazısı: (sıra, metinler)
LocoSub = tuple[int, list[str]]


def locoliser_raw(
    dialogue_file: int,
    entries: list[tuple[str, list[LocoSub]]],
    ui_file: int,
    ui_rows: list[list[str]],
    tail: bytes = b"\x02\0\0\0" + b"\0" * 8,
) -> bytes:
    """Despelote `Locoliser` MonoBehaviour'unun ham baytları (TSV'lerin gömülü, ayrıştırılmış kopyası)."""
    out = struct.pack("<iq", 0, 0) + struct.pack("<B3x", 1) + struct.pack("<iq", 1, 47) + _w_str("Locoliser")
    out += struct.pack("<ii", 0, 1) + struct.pack("<iq", 0, dialogue_file)
    out += _w_strs([key for key, _subs in entries])
    out += struct.pack("<i", len(entries))
    for _key, subs in entries:
        out += struct.pack("<i", len(subs))
        for index, texts in subs:
            out += struct.pack("<iff", index, 1.5, 2.25) + _w_strs(texts)
    out += struct.pack("<iq", 0, ui_file) + struct.pack("<i", len(ui_rows))
    for row in ui_rows:
        out += _w_strs(row)
    return out + tail


#: DKCR HD `Localization` yuvası: metin (tekli öğe) ya da çoklu öğe (çocuklar: yeni metin, ya da `int` = aynı dilin
#: o sıradaki doğrudan yuvasına başvuru).
DkSlot = str | list[str | int]


def dk_localization_raw(languages: list[tuple[int, list[DkSlot]]], named: bool = False, tag: str = "*") -> bytes:
    """DKCR HD `Localization` MonoBehaviour'unun ham baytları (SerializeReference kayıt defteri, elle yazılmış)."""
    entries: list[bytes] = []
    next_rid = [1000]

    def rid() -> int:
        next_rid[0] += 1
        return next_rid[0]

    def entry(kind: str, body: bytes, own: int | None = None) -> int:
        own = own if own is not None else rid()
        entries.append(struct.pack("<q", own) + _w_str(kind) + _w_str("dk3ds") + _w_str("Assembly-CSharp") + body)
        return own

    def single(text: str, number: int) -> int:
        body = (_w_str(f"NewText_{number}") if named else b"") + _w_str(text)
        body += struct.pack("<I", 0xA1000000 + number) + _w_str(tag) + struct.pack("<II", 1, 0)
        return entry("SingleLanguageDataItem", body)

    entries.append(struct.pack("<q", -2) + _w_str("") * 3)
    language_rids: list[int] = []
    for index, slots in languages:
        language_rid = rid()
        language_rids.append(language_rid)
        direct = {i: single(slot, i) for i, slot in enumerate(slots) if isinstance(slot, str)}
        body_refs: list[int] = []
        pending: list[bytes] = []
        for i, slot in enumerate(slots):
            if isinstance(slot, str):
                body_refs.append(direct[i])
                continue
            children = [direct[c] if isinstance(c, int) else single(c, 500 + i) for c in slot]
            multi = rid()
            name = _w_str(f"Multi_{i}") if named else b""
            pending.append(
                struct.pack("<q", multi)
                + _w_str("MultipleLanguageDataItem")
                + _w_str("dk3ds")
                + _w_str("Assembly-CSharp")
                + struct.pack("<I", 0xB1000000 + i)
                + name
                + struct.pack("<i", len(children))
                + b"".join(struct.pack("<q", c) for c in children)
            )
            body_refs.append(multi)
        entries.append(  # LanguageData, öğelerinden önce de sonra da gelebilir; gerçek dosyada araya karışır
            struct.pack("<q", language_rid)
            + _w_str("LanguageData")
            + _w_str("dk3ds")
            + _w_str("Assembly-CSharp")
            + struct.pack("<ii", index, len(body_refs))
            + b"".join(struct.pack("<q", r) for r in body_refs)
        )
        entries.extend(pending)
    out = struct.pack("<iq", 0, 0) + struct.pack("<B3x", 1) + struct.pack("<iq", 1, 100) + _w_str("Localization")
    out += struct.pack("<i", len(language_rids)) + b"".join(struct.pack("<q", r) for r in language_rids)
    out += struct.pack("<ii", 2, len(entries)) + b"".join(entries)
    return out


def serialized_without_typetree(raw_objects: list[bytes], classes: list[int] | None = None) -> bytes:
    """Ham nesne verilerinden, tip ağacı olmayan sürüm 22 bir SerializedFile. Nesneler `100 + sıra` path_id alır.

    `classes`: her nesnenin sınıf kimliği (varsayılan hepsi MonoBehaviour = 114; TextAsset = 49).
    """
    class_of = classes or [114] * len(raw_objects)
    kinds = list(dict.fromkeys(class_of))
    meta = EndianBinaryWriter(endian="<")
    meta.write_string_to_null("2017.4.28f1")
    meta.write_int(38)  # Switch
    meta.write_boolean(False)  # tip ağacı yok (oyun derlemelerindeki gibi)
    meta.write_int(len(kinds))
    for class_id in kinds:
        meta.write_int(class_id)
        meta.write_boolean(False)
        meta.write_short(-1)
        if class_id == 114:
            meta.write_bytes(b"\x07" * 16)  # script id (yalnızca MonoBehaviour)
        meta.write_bytes(b"\x09" * 16)  # eski tip özeti
    data = EndianBinaryWriter(endian="<")
    meta.write_int(len(raw_objects))
    for i, raw in enumerate(raw_objects):
        meta.align_stream(4)
        meta.write_long(100 + i)
        meta.write_long(data.Position)
        meta.write_u_int(len(raw))
        meta.write_int(kinds.index(class_of[i]))
        data.write_bytes(raw)
        data.align_stream(8)
    meta.write_int(0)  # script tipleri
    meta.write_int(0)  # dış dosyalar
    meta.write_int(0)  # başvuru tipleri
    meta.write_string_to_null("")
    header_size = 48
    data_offset = header_size + len(meta.bytes)
    data_offset += -data_offset % 16
    file_size = data_offset + len(data.bytes)
    head = struct.pack(">IIIIB3xIqqq", 0, 0, 22, 0, 0, len(meta.bytes), file_size, data_offset, 0)
    body = head + meta.bytes
    return bytes(body + b"\0" * (data_offset - len(body)) + data.bytes)


# --- TextMeshPro font paketi: font + atlas dokusu + malzeme (font yaması testleri) ----------

Rect = tuple[int, int, int, int]  # glif uzayında (x0, y0, x1, y1), y yukarı pozitif

#: Dikdörtgenlerden oluşan basit "glifler": yamanın kullandığı yapıları taşır (nokta, çengel…).
SYNTH_GLYPHS: dict[str, list[Rect]] = {
    "I": [(0, 0, 6, 40)],
    "i": [(0, 0, 6, 28), (0, 34, 6, 40)],
    "s": [(0, 0, 20, 28)],
    "S": [(0, 0, 24, 40)],
    "ç": [(0, 0, 20, 28), (8, -10, 13, 0)],
    "Ç": [(0, 0, 24, 40), (10, -10, 15, 0)],
    "g": [(0, -12, 22, 28)],
    "G": [(0, 0, 26, 40)],
    "ü": [(0, 0, 22, 28), (2, 33, 8, 39), (14, 33, 20, 39)],
    "Ü": [(0, 0, 26, 40), (3, 45, 9, 51), (17, 45, 23, 51)],
    "Ö": [(0, 0, 26, 40), (3, 45, 9, 51), (17, 45, 23, 51)],
    "A": [(0, 0, 26, 40)],
}


def _rect_vector(name: str) -> list[tuple[int, str, str, int, int, int]]:
    return _vector(
        1,
        "vector",
        name,
        [
            (3, "GlyphRect", "data", 16, 0, 0),
            (4, "int", "m_X", 4, 0, 0),
            (4, "int", "m_Y", 4, 0, 0),
            (4, "int", "m_Width", 4, 0, 0),
            (4, "int", "m_Height", 4, 0, 0),
        ],
    )


TMP_FULL_FONT_NODES = [
    *_behaviour_header(),
    *_pptr(1, "Material", "m_Material"),
    (1, "int", "m_AtlasPopulationMode", 4, 0, 0),
    *_vector(1, "vector", "m_AtlasTextures", [*_pptr(3, "Texture2D", "data")]),
    (1, "int", "m_AtlasWidth", 4, 0, 0),
    (1, "int", "m_AtlasHeight", 4, 0, 0),
    (1, "int", "m_AtlasPadding", 4, 0, 0),
    *_vector(
        1,
        "vector",
        "m_GlyphTable",
        [
            (3, "Glyph", "data", -1, 0, 0),
            (4, "unsigned int", "m_Index", 4, 0, 0),
            (4, "GlyphMetrics", "m_Metrics", 20, 0, 0),
            (5, "float", "m_Width", 4, 0, 0),
            (5, "float", "m_Height", 4, 0, 0),
            (5, "float", "m_HorizontalBearingX", 4, 0, 0),
            (5, "float", "m_HorizontalBearingY", 4, 0, 0),
            (5, "float", "m_HorizontalAdvance", 4, 0, 0),
            (4, "GlyphRect", "m_GlyphRect", 16, 0, 0),
            (5, "int", "m_X", 4, 0, 0),
            (5, "int", "m_Y", 4, 0, 0),
            (5, "int", "m_Width", 4, 0, 0),
            (5, "int", "m_Height", 4, 0, 0),
            (4, "float", "m_Scale", 4, 0, 0),
            (4, "int", "m_AtlasIndex", 4, 0, 0),
        ],
    ),
    *_vector(
        1,
        "vector",
        "m_CharacterTable",
        [
            (3, "TMP_Character", "data", -1, 0, 0),
            (4, "int", "m_ElementType", 4, 0, 0),
            (4, "unsigned int", "m_Unicode", 4, 0, 0),
            (4, "unsigned int", "m_GlyphIndex", 4, 0, 0),
            (4, "float", "m_Scale", 4, 0, 0),
        ],
    ),
    *_rect_vector("m_UsedGlyphRects"),
    *_rect_vector("m_FreeGlyphRects"),
]


def _complete(root: Any) -> Any:
    """TPK'den gelen düğümlerde boş kalan sayısal alanları doldurur (blob yazımı için)."""
    for i, n in enumerate(root.traverse()):
        for attr in ("m_Version", "m_TypeFlags", "m_ByteSize", "m_MetaFlag", "m_RefTypeHash", "m_VariableCount"):
            if getattr(n, attr, None) is None:
                setattr(n, attr, -1 if attr == "m_ByteSize" else (1 if attr == "m_Version" else 0))
        n.m_Index = i
    return root


def _default(node: Any) -> Any:
    """Tip ağacı düğümünden boş/sıfır değerli bir nesne üretir (yerleşik Unity sınıfları için)."""
    t = node.m_Type
    if t == "string":
        return ""
    if t in ("vector", "map", "staticvector", "set"):
        return []
    if t == "TypelessData":
        return b""
    if t == "bool":
        return False
    if t in ("float", "double"):
        return 0.0
    if not node.m_Children:
        return 0
    return {c.m_Name: _default(c) for c in node.m_Children}


def synth_atlas(
    glyphs: dict[str, list[Rect]], size: tuple[int, int], pad: int = 4, slope: float = 12.75
) -> tuple[Any, dict[str, Any]]:
    """Gliflerin SDF'lerini bir atlasa dizer; (PIL RGBA görüntüsü, TMP tablo alanları) döndürür."""
    from PIL import Image

    from nxceviri.core.fontpatch import sdf

    width, height = size
    alpha = Image.new("L", size, 0)
    k = pad + 1
    glyph_table: list[dict[str, Any]] = []
    char_table: list[dict[str, Any]] = []
    used: list[dict[str, int]] = []
    x = y = row_h = 0
    for n, (ch, rects) in enumerate(glyphs.items()):
        gx0, gy0 = min(r[0] for r in rects), min(r[1] for r in rects)
        gx1, gy1 = max(r[2] for r in rects), max(r[3] for r in rects)
        w, h = gx1 - gx0, gy1 - gy0
        cw, chh = w + 2 * pad + 1, h + 2 * pad + 1
        if x + cw > width:
            x, y, row_h = 0, y + row_h, 0
        mask = [False] * (cw * chh)
        for r0x, r0y, r1x, r1y in rects:
            for yy in range(r0y, r1y):
                for xx in range(r0x, r1x):
                    mask[((gy1 - 1 - yy) + (k - 1)) * cw + (xx - gx0) + k] = True
        field = sdf.from_mask(mask, cw, chh, slope)
        alpha.paste(Image.frombytes("L", (cw, chh), field.to_bytes()), (x, height - (y + chh)))
        glyph_table.append(
            {
                "m_Index": n + 1,
                "m_Metrics": {
                    "m_Width": float(w),
                    "m_Height": float(h),
                    "m_HorizontalBearingX": float(gx0),
                    "m_HorizontalBearingY": float(gy1),
                    "m_HorizontalAdvance": float(w + 4),
                },
                "m_GlyphRect": {"m_X": x + k, "m_Y": y + k, "m_Width": w, "m_Height": h},
                "m_Scale": 1.0,
                "m_AtlasIndex": 0,
            }
        )
        char_table.append({"m_ElementType": 1, "m_Unicode": ord(ch), "m_GlyphIndex": n + 1, "m_Scale": 1.0})
        used.append({"m_X": x, "m_Y": y, "m_Width": cw, "m_Height": chh})
        x += cw
        row_h = max(row_h, chh)
    top_used = y + row_h
    free = [{"m_X": 0, "m_Y": top_used, "m_Width": width, "m_Height": height - top_used}] if top_used < height else []
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    image.putalpha(alpha)
    fields = {
        "m_AtlasPopulationMode": 0,
        "m_AtlasWidth": width,
        "m_AtlasHeight": height,
        "m_AtlasPadding": pad,
        "m_GlyphTable": glyph_table,
        "m_CharacterTable": char_table,
        "m_UsedGlyphRects": used,
        "m_FreeGlyphRects": free,
    }
    return image, fields


FontSpec = tuple[str, dict[str, list[Rect]], tuple[int, int]]  # (ad, glifler, atlas boyutu)


def tmp_font_bundle(fonts: list[FontSpec], share_atlas: bool = False, atlas_slots: int = 1) -> bytes:
    """TMP fontları, Alpha8 atlas dokuları ve malzemeleriyle sıkıştırmasız bir UnityFS bundle'ı.

    `atlas_slots`: gerçek TMP fontlarındaki gibi `m_AtlasTextures` dizisine boş (pathID 0)
    yuva ekler; yama yalnızca gerçek doku başvurularını saymalıdır.
    """
    from PIL import Image
    from UnityPy.helpers.Tpk import get_typetree_node
    from UnityPy.helpers.UnityVersion import UnityVersion

    version = UnityVersion.from_str(UNITY_VERSION)
    tex_node = _complete(get_typetree_node(28, version))
    mat_node = _complete(get_typetree_node(21, version))
    font_node = _node(TMP_FULL_FONT_NODES)
    objects: list[tuple[int, int, Any, dict[str, Any]]] = []
    next_id = 1
    shared_tex = 0
    for name, glyphs, size in fonts:
        image, fields = synth_atlas(glyphs, size)
        if share_atlas and shared_tex:
            tex_id = shared_tex
            fields["m_AtlasHeight"] = fonts[0][2][1]
        else:
            tex_id = next_id
            next_id += 1
            tex = _default(tex_node)
            rows = image.getchannel("A").transpose(Image.Transpose.FLIP_TOP_BOTTOM)  # Unity: alt satır önce
            tex.update(
                {
                    "m_Name": f"{name} Atlas",
                    "m_Width": size[0],
                    "m_Height": size[1],
                    "m_CompleteImageSize": size[0] * size[1],
                    "m_TextureFormat": 1,  # Alpha8
                    "m_MipCount": 1,
                    "m_ImageCount": 1,
                    "m_TextureDimension": 2,
                    "image data": rows.tobytes(),
                }
            )
            objects.append((tex_id, 28, tex_node, tex))
            shared_tex = tex_id
        mat_id = next_id
        next_id += 1
        mat = _default(mat_node)
        mat["m_Name"] = f"{name} Material"
        props = mat["m_SavedProperties"]
        main_tex = {"m_Texture": {"m_FileID": 0, "m_PathID": tex_id}, "m_Scale": {"x": 1.0, "y": 1.0}}
        main_tex["m_Offset"] = {"x": 0.0, "y": 0.0}
        props["m_TexEnvs"] = [("_MainTex", main_tex)]
        props["m_Floats"] = [("_TextureHeight", float(size[1])), ("_TextureWidth", float(size[0]))]
        objects.append((mat_id, 21, mat_node, mat))
        font = {
            **_base(name),
            "m_Material": {"m_FileID": 0, "m_PathID": mat_id},
            "m_AtlasTextures": [{"m_FileID": 0, "m_PathID": tex_id}]
            + [{"m_FileID": 0, "m_PathID": 0}] * max(0, atlas_slots - 1),
            **fields,
        }
        objects.append((next_id, 114, font_node, font))
        next_id += 1
    return _wrap_bundle(_mixed_serialized_file(objects))


def _mixed_serialized_file(objects: list[tuple[int, int, Any, dict[str, Any]]]) -> bytes:
    """Yerleşik sınıflar (Texture2D, Material) ve MonoBehaviour'lar içeren sürüm 22 SerializedFile."""
    kinds: list[tuple[int, Any]] = []
    for _pid, class_id, node, _tree in objects:
        if all(n is not node for _c, n in kinds):
            kinds.append((class_id, node))
    meta = EndianBinaryWriter(endian="<")
    meta.write_string_to_null(UNITY_VERSION)
    meta.write_int(38)
    meta.write_boolean(True)
    meta.write_int(len(kinds))
    for i, (class_id, node) in enumerate(kinds):
        meta.write_int(class_id)
        meta.write_boolean(False)
        meta.write_short(-1)
        if class_id == 114:
            meta.write_bytes(bytes([i + 1]) * 16)
        meta.write_bytes(bytes([0xB0 + i]) * 16)
        node.dump_blob(meta, 22)
        meta.write_int(0)
    data = EndianBinaryWriter(endian="<")
    meta.write_int(len(objects))
    for path_id, _class_id, node, tree in sorted(objects, key=lambda o: o[0]):
        obj = EndianBinaryWriter(endian="<")
        write_typetree(tree, node, obj)
        meta.align_stream(4)
        meta.write_long(path_id)
        meta.write_long(data.Position)
        meta.write_u_int(len(obj.bytes))
        meta.write_int(next(i for i, (_c, n) in enumerate(kinds) if n is node))
        data.write_bytes(obj.bytes)
        data.align_stream(8)
    meta.write_int(0)
    meta.write_int(0)
    meta.write_int(0)
    meta.write_string_to_null("")
    header_size = 48
    data_offset = header_size + len(meta.bytes)
    data_offset += -data_offset % 16
    file_size = data_offset + len(data.bytes)
    head = struct.pack(">IIIIB3xIqqq", 0, 0, 22, 0, 0, len(meta.bytes), file_size, data_offset, 0)
    body = head + meta.bytes
    return bytes(body + b"\0" * (data_offset - len(body)) + data.bytes)


def _wrap_bundle(sf: bytes) -> bytes:
    name = b"CAB-nxceviri-font\0"
    info = b"\0" * 16 + struct.pack(">iIIH", 1, len(sf), len(sf), 0)
    info += struct.pack(">iqqI", 1, 0, len(sf), 4) + name
    head = b"UnityFS\0" + struct.pack(">I", 8) + b"5.x.x\0" + UNITY_VERSION.encode() + b"\0"
    fixed_len = len(head) + 8 + 12
    pad = -fixed_len % 16
    total = fixed_len + pad + len(info) + len(sf)
    return bytes(head + struct.pack(">qIII", total, len(info), len(info), 0x40) + b"\0" * pad + info + sf)
