"""Unity dosyalarındaki fontları yamalama: TextMeshPro atlasları ve gömülü TTF/OTF `Font` nesneleri.

Bir bundle'daki her statik, Latin (dile özgü olmayan) TMP fontu için eksik Türkçe harfler
`tmp.TmpFont` ile üretilir. Değişen nesneler:

- `TMP_FontAsset` (MonoBehaviour): glif/karakter tabloları, kullanılan/boş dikdörtgenler, atlas boyu;
- atlas `Texture2D`: yeni glifler çizilmiş görüntü (aynı biçimde, Switch düzenine göre yeniden
  dizilerek; veri artık bundle'ın içinde durur, `.resS` akışına başvurmaz);
- atlası kullanan `Material`'lar: atlas büyüdüyse `_TextureHeight`.

Atlası başka bir fontla paylaşan, atlası başka dosyada olan veya tip ağacı okunamayan fontlar
atlanır ve nedeni raporlanır. Yazılan bundle yeniden okunup eklenen harflerin tablolarda ve atlasın
beklenen boyutta olduğu doğrulanır.

Dinamik TMP fontları (ve eski `Font` kullanan arayüz metinleri) eksik harfi çalışma anında gömülü TTF/OTF
dosyasından üretir; bu dosyada harf yoksa yedek fonta düşülür ve harf başka bir yazı tipiyle görünür. Bu yüzden
`Font` nesnelerinin içindeki fontlara da eksik harfler eklenir (`ttf.py`, vektör anahatlarından).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import UnityPy
from UnityPy.files import BundleFile

from nxceviri.core.errors import NxError
from nxceviri.core.fontpatch import ttf
from nxceviri.core.fontpatch.tmp import TURKISH_PATCHABLE, FontPatchResult, TmpFont

log = logging.getLogger(__name__)


#: Harf bu fontta eklenemedi ama fontun yedek (fallback) fontu çizecek; kullanıcıya uyarı gerekmez.
FALLBACK_REASON = "yedek font var"


class FontPatchError(NxError):
    """Font yaması uygulanamadı."""


@dataclass(frozen=True)
class FontPatch:
    font: str
    added: str
    skipped: dict[str, str]
    #: True: gömülü TTF/OTF (`Font` nesnesi); False: TextMeshPro atlası
    vector: bool = False


def _load(data: bytes) -> Any:
    try:
        return UnityPy.load(data)
    except Exception as exc:  # UnityPy her bozuklukta farklı istisna fırlatır
        raise FontPatchError(f"Font dosyası açılamadı ({type(exc).__name__}).") from None


def _key(obj: Any, path_id: int) -> tuple[str, int]:
    """Nesne başvurusunun tanımı: aynı serileştirilmiş dosyadaki path_id. Addressables paketlerinde birden çok
    dosya vardır ve path_id'ler dosyalar arasında çakışır."""
    return (str(obj.assets_file.name), int(path_id))


def _by_id(env: Any) -> dict[tuple[str, int], Any]:
    return {_key(obj, obj.path_id): obj for obj in env.objects}


def _tmp_fonts(env: Any) -> list[tuple[Any, dict[str, Any]]]:
    found = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception as exc:
            log.debug("Nesne okunamadı (%s): %s", obj.path_id, type(exc).__name__)
            continue
        if isinstance(tree, dict) and "m_CharacterTable" in tree and "m_GlyphTable" in tree:
            found.append((obj, tree))
    return found


def _set_float(material: dict[str, Any], name: str, value: float) -> bool:
    """Malzemenin kayıtlı float özelliğini değiştirir (UnityPy çiftleri demet olarak verir)."""
    floats = (material.get("m_SavedProperties") or {}).get("m_Floats")
    if not isinstance(floats, list):
        return False
    changed = False
    for i, pair in enumerate(floats):
        if isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[0] == name:
            floats[i] = (name, float(value))
            changed = True
    return changed


def _uses_texture(material: dict[str, Any], path_id: int) -> bool:
    for pair in (material.get("m_SavedProperties") or {}).get("m_TexEnvs") or []:
        env = pair[1] if isinstance(pair, (list, tuple)) else pair.get("second", {})
        tex = (env or {}).get("m_Texture") or {}
        if tex.get("m_FileID") == 0 and tex.get("m_PathID") == path_id:
            return True
    return False


def _atlas_texture(tree: dict[str, Any]) -> dict[str, Any] | None:
    """Fontun kullandığı tek atlas dokusu.

    TMP fontları `m_AtlasTextures` dizisini sabit uzunlukta (genelde 4 veya 8 yuva) yazar;
    kullanılmayan yuvaların `m_PathID` değeri 0'dır. Bu boş yuvalar "birden çok atlas" sayılmamalı.
    """
    refs = [
        ref for ref in tree.get("m_AtlasTextures") or [] if isinstance(ref, dict) and int(ref.get("m_PathID", 0)) != 0
    ]
    if len(refs) != 1 or refs[0].get("m_FileID") != 0:
        return None
    return refs[0]


def patch_fonts(
    data: bytes,
    letters: str = TURKISH_PATCHABLE,
    *,
    write: bool = True,
    skip: Callable[[str], bool] | None = None,
) -> tuple[bytes, list[FontPatch]]:
    """Bundle'daki uygun TMP fontlarına `letters` içindeki eksik harfleri ekler.

    `write=False` yalnızca hangi harflerin eklenebileceğini hesaplar (Kontrol Et ekranı için);
    dosya değiştirilmez. `skip(ad)` doğruysa font hiç denenmez (ör. Japonca fontlar). Hiçbir
    font değişmezse özgün baytlar döner.
    """
    env = _load(data)
    objects = _by_id(env)
    fonts = _tmp_fonts(env)
    shared = Counter(_key(o, int(ref["m_PathID"])) for o, t in fonts if (ref := _atlas_texture(t)) is not None)
    reports: list[FontPatch] = []
    changed = False
    for obj, tree in fonts:
        name = str(tree.get("m_Name", ""))
        wanted = "".join(c for c in letters if ord(c) not in {int(x["m_Unicode"]) for x in tree["m_CharacterTable"]})
        if not wanted:
            continue
        if skip is not None and skip(name):
            continue
        if int(tree.get("m_AtlasPopulationMode", 0)) != 0:
            reports.append(FontPatch(name, "", dict.fromkeys(wanted, "dinamik font: harfler kaynak fonttan üretilir")))
            continue
        textures = _atlas_texture(tree)
        if textures is None or _key(obj, int(textures.get("m_PathID", 0))) not in objects:
            reports.append(FontPatch(name, "", dict.fromkeys(wanted, "atlas dokusu bu dosyada değil veya birden çok")))
            continue
        tex_id = int(textures["m_PathID"])
        if shared[_key(obj, tex_id)] > 1:
            reports.append(FontPatch(name, "", dict.fromkeys(wanted, "atlas başka bir fontla ortak")))
            continue
        tex = objects[_key(obj, tex_id)].read()
        try:
            image = tex.image
        except Exception as exc:
            reason = f"atlas okunamadı ({type(exc).__name__})"
            if tree.get("m_FallbackFontAssetTable"):
                # Varsayılan TMP fontlarında (ör. LiberationSans SDF) eksik harfi yedek dinamik font çizer.
                reason = f"{FALLBACK_REASON}: {reason}"
            reports.append(FontPatch(name, "", dict.fromkeys(wanted, reason)))
            continue
        font = TmpFont(tree, image)
        result: FontPatchResult = font.patch(wanted)
        reports.append(FontPatch(name, result.added, result.skipped))
        if not write or not result.added:
            continue
        old_height = image.height
        try:
            if font.placed:
                tex.set_image(font.atlas_image(), target_format=tex.m_TextureFormat)
                tex.save()
            obj.save_typetree(tree)
            if font.atlas.height != old_height:
                for mat_obj in env.objects:
                    if mat_obj.type.name != "Material" or mat_obj.assets_file is not obj.assets_file:
                        continue
                    material = mat_obj.read_typetree()
                    if _uses_texture(material, tex_id) and _set_float(material, "_TextureHeight", font.atlas.height):
                        mat_obj.save_typetree(material)
        except Exception as exc:
            raise FontPatchError(f"'{name}' fontu yazılamadı ({type(exc).__name__}).") from None
        changed = True
    changed = _patch_vector_fonts(env, letters, write=write, skip=skip, reports=reports) or changed
    if not changed:
        return data, reports
    try:
        file_obj: Any = env.file
        options = {"packer": "original"} if isinstance(file_obj, BundleFile) else {}
        out = bytes(file_obj.save(**options))
    except Exception as exc:
        raise FontPatchError(f"Font dosyası yeniden yazılamadı ({type(exc).__name__}).") from None
    _verify(out, reports)
    return out, reports


def _patch_vector_fonts(
    env: Any, letters: str, *, write: bool, skip: Callable[[str], bool] | None, reports: list[FontPatch]
) -> bool:
    """`Font` nesnelerindeki TTF/OTF'lere eksik harfleri ekler (`write=False` ise yalnızca planlar)."""
    changed = False
    for obj in env.objects:
        if obj.type.name != "Font":
            continue
        font = obj.read()
        name = str(font.m_Name)
        raw = bytes(font.m_FontData or b"")
        if not raw or (skip is not None and skip(name)):
            continue
        if write:
            result = ttf.patch_font(raw, letters)
            added, skipped = result.added, result.skipped
        else:
            added, skipped = ttf.plan(raw, letters)
        if not added and not skipped:
            continue  # istenen harflerin hepsi zaten var
        reports.append(FontPatch(name, added, skipped, vector=True))
        if write and added:
            try:
                font.m_FontData = result.data
                font.save()
            except Exception as exc:
                raise FontPatchError(f"'{name}' fontu yazılamadı ({type(exc).__name__}).") from None
            changed = True
    return changed


def _verify(out: bytes, reports: list[FontPatch]) -> None:
    """Yazılan bundle'da eklenen harfler tablolarda ve atlas boyutu tablolarla tutarlı mı?"""
    env = _load(out)
    objects = _by_id(env)
    _verify_vector(env, [r for r in reports if r.vector and r.added])
    reports = [r for r in reports if not r.vector]
    expected = {r.font: r.added for r in reports if r.added}
    for _obj, tree in _tmp_fonts(env):
        added = expected.pop(str(tree.get("m_Name", "")), None)
        if added is None:
            continue
        chars = {int(x["m_Unicode"]) for x in tree["m_CharacterTable"]}
        atlas_ref = _atlas_texture(tree)
        if atlas_ref is None:
            raise FontPatchError("Font yaması yazıldıktan sonra atlas bulunamadı; mod üretilmedi.")
        tex = objects[_key(_obj, int(atlas_ref["m_PathID"]))].read()
        if any(ord(c) not in chars for c in added) or tex.image.height != int(tree["m_AtlasHeight"]):
            raise FontPatchError(
                "Font yaması yazıldıktan sonra doğrulanamadı; mod üretilmedi.",
                "Bu bir hata olabilir; log dosyasını geliştiriciyle paylaşın.",
            )
    if expected:
        raise FontPatchError("Font yaması yazıldıktan sonra bazı fontlar bulunamadı; mod üretilmedi.")


def _verify_vector(env: Any, reports: list[FontPatch]) -> None:
    """Yazılan `Font` nesnelerinde eklenen harfler cmap'te var mı?"""
    expected = {r.font: r.added for r in reports}
    for obj in env.objects:
        if obj.type.name != "Font":
            continue
        font = obj.read()
        added = expected.pop(str(font.m_Name), None)
        if added is not None and ttf.plan(bytes(font.m_FontData), added) != ("", {}):
            raise FontPatchError(
                "Font yaması yazıldıktan sonra doğrulanamadı; mod üretilmedi.",
                "Bu bir hata olabilir; log dosyasını geliştiriciyle paylaşın.",
            )
    if expected:
        raise FontPatchError("Font yaması yazıldıktan sonra bazı fontlar bulunamadı; mod üretilmedi.")
