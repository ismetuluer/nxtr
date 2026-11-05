"""Kullanıcının hazırladığı Türkçe oyun grafiklerini (Photoshop vb. ile temizlenip çevrilmiş sayfalar) yerleştirme.

Klasör düzeni (`games/Devil May Cry/grafik_temizleme`):

- `orijinal/<ad>.png`: oyundan çıkarılmış özgün sayfa (uygulamanın `iter_pages` çözümüyle üretilir);
- `temiz/<ad>.png`: aynı adlı, yazısı Türkçe olan hazır sayfa (aynı boyut; alfa kanalı özgünle aynı kalır);
- `dizin.json` (isteğe bağlı): özgün sayfanın geçtiği tüm oyun dosyaları (`build_index` üretir).

Sayfalar içerik özetiyle eşleşir (`dmc1_images.page_key`): özgün sayfa her geçtiği dosyada hazırıyla değiştirilir.
Oyun grafikleri telifli olduğu için depoya konmaz; klasör kullanıcıda kalır ve `NXCEVIRI_DMC1_GRAFIK` ortam
değişkeniyle gösterilir (arayüzde ayar penceresi TECH_DEBT'te).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

from nxceviri.core.fontpatch.dmc1_images import iter_pages, page_key

ENV = "NXCEVIRI_DMC1_GRAFIK"
INDEX = "dizin.json"
#: Animasyon karelerinin son kareleri bu adı taşır; sayfa olarak değil, animasyon olarak ele alınır.
ANIMATION_MARK = "son_kare"
_SKIP_SUFFIXES = (".mp4", ".bank", ".nbz", ".msg", ".atm")
_MAX_SCAN_SIZE = 60_000_000


@dataclass(frozen=True)
class Graphics:
    pages: dict[str, Image.Image]  # özgün sayfa özeti → hazır Türkçe sayfa
    files: tuple[str, ...]  # özgün sayfaların geçtiği oyun dosyaları (RomFS'e göre)
    animations: dict[str, tuple[Image.Image, Image.Image]]  # görev girişi dosyası → (özgün, Türkçe) son kare


def load(folder: Path) -> Graphics:
    """`orijinal`/`temiz` çiftlerinden gerçekten değişmiş olanları okur."""
    pages: dict[str, Image.Image] = {}
    animations: dict[str, tuple[Image.Image, Image.Image]] = {}
    for new in sorted((folder / "temiz").glob("*.png")):
        old = folder / "orijinal" / new.name
        if not old.is_file():
            continue
        before, after = Image.open(old).convert("RGBA"), Image.open(new).convert("RGBA")
        if before.size != after.size or before.tobytes() == after.tobytes():
            continue
        if ANIMATION_MARK in new.name:  # `status_u__mssn_ips_16.ip2__son_kare.png` → data/dmc1/status_u/mssn_ips_16.ip2
            folder_name, _, rest = new.name.partition("__")
            animations[f"data/dmc1/{folder_name}/{rest.partition('__')[0]}"] = (before, after)
        else:
            pages[page_key(before)] = after
    index = folder / INDEX
    files = tuple(json.loads(index.read_text(encoding="utf-8")).get("dosyalar", [])) if index.is_file() else ()
    return Graphics(pages, files, animations)


@lru_cache(maxsize=1)
def from_environment() -> Graphics | None:
    """`NXCEVIRI_DMC1_GRAFIK` klasöründeki grafikler (ortam değişkeni yoksa ya da klasör yoksa None)."""
    value = os.environ.get(ENV)
    if not value or not Path(value).is_dir():
        return None
    return load(Path(value))


def build_index(folder: Path, roots: list[Path]) -> int:
    """Hazır sayfaların geçtiği dosyaları `roots` altında bulup `dizin.json`a yazar; sayısını döndürür."""
    graphics = load(folder)
    found: set[str] = set()
    for root in roots:
        base = root / "data" / "dmc1"
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix in _SKIP_SUFFIXES or path.stat().st_size > _MAX_SCAN_SIZE:
                continue
            if any(page_key(p.image) in graphics.pages for p in iter_pages(path.read_bytes())):
                found.add(path.relative_to(root).as_posix())
    (folder / INDEX).write_text(json.dumps({"dosyalar": sorted(found)}, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(found)
