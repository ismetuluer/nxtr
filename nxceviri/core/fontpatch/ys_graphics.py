"""Ys Origin: İngilizce yazı içeren resimlerin (DDS) kullanıcının hazırladığı Türkçe karşılıklarını yerleştirme.

Menü başlıkları, düğme yazıları, ara sahne ve rehber sayfaları metin değil resimdir. Klasör düzeni
(`<oyun klasörü>/grafik_temizleme`, `NXCEVIRI_YS_GRAFIK` ortam değişkeniyle değiştirilebilir):

- `orijinal/<ad>.png`: oyundan çıkarılmış özgün resim (`export_originals` üretir; değiştirmeyin);
- `temiz/<ad>.png` (veya `.dds`): aynı adlı, yazısı Türkçe olan hazır resim. Boyutu değişmişse özgün boya ölçeklenir;
  saydamlık kaydedilmemişse özgünün alfa kanalı korunur. Özgünle aynı kalan dosyalar yok sayılır.

Resimler üç yerden gelir: dil arşivi `data-en.ni` içindeki `EXTENSION/STORY/EN/*.DDS` (140 dosya: harita ve patron
adları, hikâye ve rehber sayfaları), aynı arşivdeki `EXTENSION/MENU/*/*_EN.DDS` (8 dosya: seçenek düğmeleri, onay
kutuları) ve serbest `extension/menu/categories_atlas.dds` ile `extension/demo/demo_over.dds`. Yazma, özgün DDS
başlığını ve mip sayısını korur: BC3 (DXT5) ve BC1 (DXT1) sayfalar her mip seviyesiyle yeniden kodlanır.
Ana arşivdeki resimler (`MENU/CHRSELECT.DDS` "Character Select") henüz desteklenmez (TECH_DEBT).
"""

from __future__ import annotations

import io
import os
import struct
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from nxceviri.core.errors import NxError

ENV = "NXCEVIRI_YS_GRAFIK"
FOLDER = "grafik_temizleme"
ARCHIVE = "ys_data/archives/data-en.ni"
MEMBER_DIR = "EXTENSION/STORY/EN/"
#: Menü resimleri (düğme yazıları, onay kutuları, harita ve rehber başlıkları): ad → arşiv üyesi.
MENU_MEMBERS = {
    "OPBTN_EN": "EXTENSION/MENU/OPTION/OPBTN_EN.DDS",
    "MSGBOX_EN": "EXTENSION/MENU/MSGBOX/MSGBOX_EN.DDS",
    "ASK_DEL_EN": "EXTENSION/MENU/ASKDEL/ASK_DEL_EN.DDS",
    "ASK_LOAD_EN": "EXTENSION/MENU/ASKLOAD/ASK_LOAD_EN.DDS",
    "ASK_SAVE_EN": "EXTENSION/MENU/ASKSAVE/ASK_SAVE_EN.DDS",
    "ASK_USE_EN": "EXTENSION/MENU/ASKUSE/ASK_USE_EN.DDS",
    "MAP_EN": "EXTENSION/MENU/MAP/MAP_EN.DDS",
    "TOPIC_BUTTONS_EN": "EXTENSION/MENU/MANUAL/TOPIC_BUTTONS_EN.DDS",
}
#: Serbest dosyalar: ad → RomFS yolu.
LOOSE = {
    "categories_atlas": "ys_data/data/extension/menu/categories_atlas.dds",
    "demo_over": "ys_data/data/extension/demo/demo_over.dds",
}
#: DDS'te baş aşağı saklanan resimler: PNG'de dik gösterilir, yazarken geri çevrilir.
FLIPPED = frozenset({"demo_over"})
_FORMATS = {77: ("DXT5", 16), 71: ("DXT1", 8)}  # DXGI_FORMAT_BC3_UNORM, BC1_UNORM → (Pillow kodu, blok baytı)
README = """Ys Origin grafik çevirisi
=========================

orijinal\\   Oyundan çıkarılmış İngilizce resimler (değiştirmeyin).
temiz\\      Yazısını Türkçe yaptığınız resimleri BURAYA, orijinal\\ içindeki ADIYLA kaydedin (PNG).

Photoshop'ta: orijinal\\ içindeki resmi açın, İngilizce yazıyı silin, Türkçesini yazın,
temiz\\ içine aynı adla kaydedin.
Saydam arka planı koruyun (çoğu resim saydam zeminli yazıdır). Boyutu değiştirmeyin.

Mod üretilirken temiz\\ içinde orijinalden farklı olan her resim otomatik olarak moda yerleştirilir.
Değişmeyen resimlere dokunulmaz. Dışa aktarma raporunda hangi resimlerin yerleştiği yazar.

Hangi resim nerede görünür?
  OPBTN_EN          Seçenekler ekranı: BGM Volume, SFX Volume, Analog movements, Return to Title ... (iki durum)
  MSGBOX_EN         "Return to title screen?" kutusu ve Yes / No düğmeleri
  ASK_DEL_EN, ASK_LOAD_EN, ASK_SAVE_EN, ASK_USE_EN   Kaydet / yükle / sil / kullan soruları ve düğmeleri
  TOPIC_BUTTONS_EN  Rehber sayfalarındaki PREV / NEXT / Select / Confirm düğmeleri
  MAP_EN            Harita ekranındaki bölge adları (Tower Base, Flooded Prison ...)
  MAP_NAMEnn        Bölge adı başlıkları (Japonca adın altında İngilizce alt yazı)
  BOSS_NAMEnn       Patron adı başlıkları (Japonca adın altında İngilizce alt yazı)
  V_nnn             Hikâye sahnelerindeki yazılar ve rehber (Manual) sayfaları
  categories_atlas  Menü başlıkları: Arena, Equip, Inventory, Leaderboard, Load, Manual, Option, Save, Topic ...
  demo_over         "Thank you for playing!" ekranı
"Character Select" başlığı ana arşivde olduğu için henüz çevrilemez.
"""


class GraphicsError(NxError):
    """Resim çözülemedi veya yazılamadı."""


@dataclass(frozen=True)
class Layout:
    header: int  # DDS başlığının bayt uzunluğu (DX10 ek başlığı dahil)
    width: int
    height: int
    mips: int
    code: str  # Pillow'un DDS pixel_format adı
    block: int


def _layout(dds: bytes) -> Layout:
    if len(dds) < 128 or not dds.startswith(b"DDS "):
        raise GraphicsError("DDS dosyası değil veya kesik.")
    height, width = struct.unpack_from("<II", dds, 12)
    mips = max(1, struct.unpack_from("<I", dds, 28)[0])
    fourcc = dds[84:88]
    if fourcc == b"DX10":
        dxgi = struct.unpack_from("<I", dds, 128)[0]
        if dxgi not in _FORMATS:
            raise GraphicsError(f"Desteklenmeyen DDS biçimi (DXGI {dxgi}); yalnızca BC1 ve BC3.")
        return Layout(148, width, height, mips, *_FORMATS[dxgi])
    if fourcc in (b"DXT1", b"DXT5"):
        return Layout(128, width, height, mips, fourcc.decode(), 8 if fourcc == b"DXT1" else 16)
    raise GraphicsError("Desteklenmeyen DDS biçimi; yalnızca BC1 ve BC3.")


def decode(dds: bytes, name: str = "") -> Image.Image:
    """DDS'in ilk (en büyük) seviyesi, RGBA; baş aşağı saklananlar dik çevrilir."""
    _layout(dds)
    try:
        image = Image.open(io.BytesIO(dds)).convert("RGBA")
    except (OSError, ValueError, SyntaxError) as exc:
        raise GraphicsError(f"DDS çözülemedi: {exc}") from None
    return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM) if name in FLIPPED else image


def _compress(image: Image.Image, layout: Layout, size: int) -> bytes:
    """Tek mip seviyesinin sıkıştırılmış baytları (blok çözünürlüğüne tamamlanarak)."""
    w, h = image.size
    padded = Image.new("RGBA", (max(4, -(-w // 4) * 4), max(4, -(-h // 4) * 4)), (0, 0, 0, 0))
    padded.paste(image, (0, 0))
    buf = io.BytesIO()
    padded.save(buf, "DDS", pixel_format=layout.code)
    data = buf.getvalue()[128:]
    if len(data) != size:
        raise GraphicsError(f"Sıkıştırılmış mip boyutu beklenenden farklı ({len(data)} ≠ {size}).")
    return data


def encode(original: bytes, image: Image.Image, name: str = "") -> bytes:
    """`image`i özgün DDS ile aynı başlık, boyut, biçim ve mip sayısıyla kodlar."""
    layout = _layout(original)
    base = image.convert("RGBA")
    if name in FLIPPED:
        base = base.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if base.size != (layout.width, layout.height):
        base = base.resize((layout.width, layout.height), Image.Resampling.LANCZOS)
    premultiplied = base.convert("RGBa")  # küçültürken saydam piksellerin rengi bulaşmasın
    payload = bytearray()
    for level in range(layout.mips):
        w, h = max(1, layout.width >> level), max(1, layout.height >> level)
        level_image = base if level == 0 else premultiplied.resize((w, h), Image.Resampling.LANCZOS).convert("RGBA")
        size = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * layout.block
        payload += _compress(level_image, layout, size)
    out = original[: layout.header] + bytes(payload)
    if len(out) != len(original):
        raise GraphicsError(f"Kodlanan DDS ({len(out)} bayt) özgünle ({len(original)} bayt) aynı boyda değil.")
    return out


def folder_for(game_dir: Path | None) -> Path | None:
    """Grafik klasörü: ortam değişkeni, yoksa oyun dosyalarının yanındaki `grafik_temizleme`; yoksa None."""
    value = os.environ.get(ENV)
    folder = Path(value) if value else (game_dir / FOLDER if game_dir is not None else None)
    return folder if folder is not None and (folder / "temiz").is_dir() else None


def member_of(stem: str) -> str:
    """Resmin dil arşivindeki üye adı."""
    return MENU_MEMBERS.get(stem, f"{MEMBER_DIR}{stem}.DDS")


def member_path(stem: str) -> str:
    return f"{ARCHIVE}>{member_of(stem)}"


def source_path(stem: str) -> str:
    """Resmin tarama yolu: serbest dosya ya da dil arşivinin üyesi (`arşiv>üye`)."""
    return LOOSE.get(stem, member_path(stem))


def export_originals(
    read: Callable[[str], bytes], members: Collection[str], folder: Path, loose_present: Collection[str] = ()
) -> list[str]:
    """Çevrilebilir resimlerin PNG'lerini `orijinal/`e yazar, `temiz/` ve açıklamayı oluşturur; yazılan adlar."""
    (folder / "orijinal").mkdir(parents=True, exist_ok=True)
    (folder / "temiz").mkdir(exist_ok=True)
    (folder / "OKUBENI.txt").write_text(README, encoding="utf-8")
    stems = sorted(
        {m[len(MEMBER_DIR) : -len(".DDS")] for m in members if m.startswith(MEMBER_DIR) and m.upper().endswith(".DDS")}
        | {stem for stem, member in MENU_MEMBERS.items() if member in members}
        | {stem for stem, path in LOOSE.items() if path in loose_present}
    )
    written = []
    for stem in stems:
        decode(read(source_path(stem)), stem).save(folder / "orijinal" / f"{stem}.png")
        written.append(stem)
    return written


def _read_ready(path: Path, original: Image.Image) -> Image.Image:
    """Hazır resmi özgünle aynı boyda RGBA okur; saydamlık kaydedilmemişse özgünün alfa kanalı korunur."""
    raw = Image.open(path)
    has_alpha = "A" in raw.getbands() or "transparency" in raw.info or path.suffix.lower() == ".dds"
    ready = raw.convert("RGBA")
    if ready.size != original.size:
        ready = ready.resize(original.size, Image.Resampling.LANCZOS)
    if not has_alpha:
        ready.putalpha(original.getchannel("A"))
    return ready


def load(folder: Path) -> tuple[dict[str, Image.Image], list[str]]:
    """`temiz/`deki, özgününden gerçekten farklı resimler ({ad → RGBA}) ve uyarılar."""
    ready: dict[str, Image.Image] = {}
    warnings: list[str] = []
    for new in sorted((folder / "temiz").iterdir()):
        if new.suffix.lower() not in (".png", ".dds"):
            continue
        old = folder / "orijinal" / f"{new.stem}.png"
        if not old.is_file():
            warnings.append(f"temiz/{new.name}: orijinal/ içinde aynı adlı resim yok; atlandı.")
            continue
        before = Image.open(old).convert("RGBA")
        try:
            after = _read_ready(new, before)
        except (OSError, ValueError, SyntaxError):
            warnings.append(f"temiz/{new.name}: resim açılamadı; atlandı.")
            continue
        if before.size != Image.open(new).size:
            warnings.append(
                f"temiz/{new.name}: boyutu özgünden farklı ({Image.open(new).size}); özgün boya ölçeklendi."
            )
        if before.tobytes() != after.tobytes():
            ready[new.stem] = after
    return ready, warnings


def replacements(
    read: Callable[[str], bytes], files: Collection[str], folder: Path
) -> tuple[dict[str, bytes], list[str], list[str]]:
    """({yol → yeni DDS baytları}, yerleşen resimleri anlatan satırlar, uyarılar).

    Yol, serbest dosyada RomFS yolu, arşiv üyesinde `arşiv>üye` biçimindedir."""
    images, warnings = load(folder)
    out: dict[str, bytes] = {}
    notes: list[str] = []
    for stem, image in images.items():
        path = source_path(stem)
        top = path.split(">")[0]
        if top not in files:
            warnings.append(f"temiz/{stem}: oyunda {top} yok; atlandı.")
            continue
        try:
            out[path] = encode(read(path), image, stem)
        except NxError as exc:
            warnings.append(f"temiz/{stem}: yerleştirilemedi: {exc.message}")
            continue
        notes.append(stem)
    return out, notes, warnings
