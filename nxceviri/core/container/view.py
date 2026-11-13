"""Birleşik oyun görünümü: base + update (+ DLC) → okunacak tek dosya ağacı.

İki durum vardır:

- Güncelleme RomFS'i bir BKTR yamasıysa (neredeyse her zaman), base ile birleştirilip
  güncel RomFS elde edilir. Bir dosyanın verisinin herhangi bir kısmı yamadan
  geliyorsa o dosyanın kaynağı "update", aksi hâlde "base" sayılır.
- Güncelleme tam bir RomFS taşıyorsa dosya düzeyinde katmanlama yapılır: aynı yoldaki
  dosyada güncellemedeki sürüm base'dekini geçersiz kılar.

DLC'ler ayrı başlıklardır (kendi TitleID'leri, kendi LayeredFS klasörleri); ayrı bir
ağaç olarak eklenir.
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from nxceviri.core.container import nso
from nxceviri.core.container.nca import EncryptionType, FsType, Nca, open_data_region, physical_span
from nxceviri.core.container.package import KIND_BASE, KIND_DLC, KIND_UPDATE, GamePackage
from nxceviri.core.container.patch import open_patched_romfs_section
from nxceviri.core.container.romfs import RomFs, RomFsFile
from nxceviri.core.container.storage import Storage, SubStorage
from nxceviri.core.errors import ContainerError
from nxceviri.core.progress import TaskContext

_FORBIDDEN_CHARS = set('<>:"|?*\\') | {chr(c) for c in range(32)}


@dataclass(frozen=True)
class ViewFile:
    path: str
    size: int
    origin: str  # KIND_BASE / KIND_UPDATE / KIND_DLC


@dataclass
class RomFsLayer:
    origin: str
    romfs: RomFs
    origin_of: Callable[[RomFsFile], str] | None = None


class LayeredRomFs:
    """Katmanlı RomFS: listede sonra gelen katman, aynı yoldaki dosyayı geçersiz kılar."""

    def __init__(self, layers: list[RomFsLayer]) -> None:
        self.layers = layers
        self._owner: dict[str, RomFsLayer] = {}
        for layer in layers:
            for path in layer.romfs.files:
                self._owner[path] = layer
        self.files: dict[str, ViewFile] = {}
        for path in sorted(self._owner):
            layer = self._owner[path]
            entry = layer.romfs.files[path]
            origin = layer.origin_of(entry) if layer.origin_of else layer.origin
            self.files[path] = ViewFile(path, entry.size, origin)

    def open(self, path: str) -> Storage:
        layer = self._owner.get(path)
        if layer is None:
            raise ContainerError(f"Dosya bulunamadı: {path}")
        return layer.romfs.open(path)


@dataclass
class ContentTree:
    title_id: str
    label: str
    view: LayeredRomFs
    #: Oyunun çalıştırılabilir kodu (ExeFS `main`), isteğe bağlı ve tembel okunur. M2 arşivlerinin
    #: anahtarı bu koddaki dizgelerden bulunur; kod yalnızca okunur, çalıştırılmaz.
    code: Callable[[], bytes | None] | None = None


@dataclass
class GameView:
    title_id: str
    name: str
    base_version: int | None
    update_version: int | None
    trees: list[ContentTree]
    warnings: list[str] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return sum(len(t.view.files) for t in self.trees)


def _code_loader(packages: list[GamePackage]) -> Callable[[], bytes | None]:
    """Önce güncellemenin, yoksa ana oyunun `main` kodunu (ilk istendiğinde) okuyan işlev."""
    cache: list[bytes | None] = []

    def load() -> bytes | None:
        if not cache:
            found: bytes | None = None
            for pkg in packages:
                program = pkg.program_nca()
                found = nso.read_main(program) if program is not None else None
                if found is not None:
                    break
            cache.append(found)
        return cache[0]

    return load


def _romfs_of(nca: Nca) -> RomFs | None:
    fs = nca.find_section(FsType.ROMFS)
    if fs is None:
        return None
    return RomFs(nca.data_storage(fs), nca.name)


def build_game_view(packages: list[GamePackage], ctx: TaskContext | None = None) -> GameView:
    """Paketleri doğrulayıp birleşik görünümü kurar."""
    ctx = ctx or TaskContext()
    if not packages:
        raise ContainerError("Hiç oyun dosyası eklenmedi.", "Önce oyununuzun NSP veya NSZ dosyasını ekleyin.")
    bases = [p for p in packages if p.kind == KIND_BASE]
    updates = [p for p in packages if p.kind == KIND_UPDATE]
    dlcs = [p for p in packages if p.kind == KIND_DLC]
    warnings: list[str] = []

    if len(bases) > 1:
        raise ContainerError(
            "Birden fazla ana oyun dosyası eklendi.",
            "Bir projede yalnızca tek bir oyunun ana dosyası olabilir. Fazla olanı kaldırın.",
        )
    base = bases[0] if bases else None
    if updates and base is None:
        raise ContainerError(
            "Güncelleme dosyası tek başına okunamaz.",
            "Güncellemeler yalnızca değişen kısımları içerir. Bu güncellemenin ait olduğu ana oyunu da ekleyin.",
        )
    app_id = base.title_id if base else (dlcs[0].application_id if dlcs else "")
    for pkg in updates + dlcs:
        if pkg.application_id != app_id:
            raise ContainerError(
                f"{pkg.path.name} bu oyuna ait değil (ait olduğu oyun: {pkg.application_id}, "
                f"projedeki oyun: {app_id}).",
                "Yanlış dosyayı kaldırıp doğru oyunun dosyasını ekleyin.",
            )
    update = max(updates, key=lambda p: p.version) if updates else None
    if len(updates) > 1 and update is not None:
        warnings.append(f"Birden fazla güncelleme eklendi; yalnızca en yenisi (v{update.version}) kullanılıyor.")

    trees: list[ContentTree] = []
    code = _code_loader([p for p in (update, base) if p is not None])
    if base is not None:
        ctx.report(0, 0, "Ana oyun okunuyor")
        base_program = base.program_nca(ctx)
        if base_program is None:
            raise ContainerError(f"{base.path.name} içinde program içeriği yok; paket eksik.")
        layers: list[RomFsLayer] = []
        base_fs = base_program.find_section(FsType.ROMFS)
        # Seyrek base: verinin bir kısmı yalnızca güncellemede; tek başına anlamlı bir RomFS değildir.
        sparse_base = base_fs is not None and base_fs.is_sparse
        if sparse_base and update is None:
            raise ContainerError(
                f"{base.path.name} tek başına okunamaz: oyun verisinin bir kısmı yalnızca güncellemede.",
                "Bu oyunun güncelleme (update) dosyasını da ekleyin.",
            )
        base_romfs = None if sparse_base else _romfs_of(base_program)
        if base_romfs is not None:
            layers.append(RomFsLayer(KIND_BASE, base_romfs))
        if update is not None:
            ctx.report(0, 0, "Güncelleme uygulanıyor")
            layers = _apply_update(update, base_program, layers)
        if layers:
            trees.append(ContentTree(base.title_id, "Ana oyun", LayeredRomFs(layers), code))
        else:
            warnings.append(
                "Oyunda veri klasörü yok: oyunun tüm verisi program dosyasının içinde. "
                "Bu tür oyunların metinleri ayrı dosyalarda olmadığı için çıkarılamaz."
            )

    for dlc in sorted(dlcs, key=lambda p: p.title_id):
        ctx.report(0, 0, f"DLC okunuyor: {dlc.title_id}")
        data = dlc.data_nca(ctx)
        romfs = _romfs_of(data) if data else None
        if romfs is None:
            warnings.append(f"DLC {dlc.title_id} içinde okunacak veri yok.")
            continue
        trees.append(
            ContentTree(dlc.title_id, f"DLC {dlc.title_id}", LayeredRomFs([RomFsLayer(KIND_DLC, romfs)]), code)
        )

    names = [p.nacp.name for p in (update, base) if p is not None and p.nacp is not None and p.nacp.name]
    name = names[0] if names else packages[0].display_name
    return GameView(
        title_id=app_id,
        name=name,
        base_version=base.version if base else None,
        update_version=update.version if update else None,
        trees=trees,
        warnings=warnings,
    )


def _apply_update(update: GamePackage, base_program: Nca, layers: list[RomFsLayer]) -> list[RomFsLayer]:
    program = update.program_nca()
    if program is None:
        return layers
    fs = program.find_section(FsType.ROMFS)
    if fs is None:
        return layers  # güncelleme yalnızca kodu (ExeFS) değiştiriyor
    if fs.encryption_type in (EncryptionType.CTR_EX, EncryptionType.CTR_EX_SKIP_LAYER_HASH):
        patched = open_patched_romfs_section(program, fs, base_program)
        data_off, data_size = fs.data_region()
        # Sıkıştırma katmanı (varsa) yamalanmış veri bölgesinin üzerinde, yamanın tablosuyla açılır.
        data = open_data_region(SubStorage(patched, data_off, data_size), fs)
        romfs = RomFs(data, program.name)

        def origin_of(entry: RomFsFile) -> str:
            off, size = physical_span(data, entry.offset, entry.size)
            return KIND_UPDATE if patched.touches_patch(data_off + off, size) else KIND_BASE

        # Yamalı RomFS tam ve günceldir; base katmanı yerine geçer.
        return [RomFsLayer(KIND_UPDATE, romfs, origin_of)]
    full = _romfs_of(program)
    return [*layers, RomFsLayer(KIND_UPDATE, full)] if full else layers


def safe_relative_path(path: str) -> Path:
    """RomFS yolunu güvenli bir göreli yola çevirir; klasör dışına çıkmayı engeller."""
    parts = path.split("/")
    for part in parts:
        if part in ("", ".", "..") or any(ch in _FORBIDDEN_CHARS for ch in part) or part.endswith((" ", ".")):
            raise ContainerError(f"Dosya adı Windows'ta güvenle yazılamıyor: {path}")
    return Path(*parts)


def extract_tree(
    tree: ContentTree,
    dest: Path,
    ctx: TaskContext | None = None,
    only: Callable[[str], bool] | None = None,
) -> int:
    """Ağacı `dest` klasörüne çıkarır. Önce geçici klasöre yazar, bitince yerine taşır.

    `dest` zaten varsa ve boş değilse hata verir; var olan veri asla üzerine yazılmaz.
    Yazılan dosya sayısını döndürür.
    """
    ctx = ctx or TaskContext()
    if dest.exists() and any(dest.iterdir()):
        raise ContainerError(
            f"Hedef klasör boş değil: {dest}",
            "Boş bir klasör seçin veya yeni bir klasör adı verin.",
        )
    selected = [f for f in tree.view.files.values() if only is None or only(f.path)]
    rel_paths = {f.path: safe_relative_path(f.path) for f in selected}
    total = sum(f.size for f in selected)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.{uuid.uuid4().hex[:8]}.gecici"
    tmp.mkdir()
    try:
        done = 0
        for f in selected:
            target = tmp / rel_paths[f.path]
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as out:
                for chunk in tree.view.open(f.path).iter_chunks():
                    out.write(chunk)
                    done += len(chunk)
                    ctx.report(done, total, f.path)
            if target.stat().st_size != f.size:
                raise ContainerError(f"'{f.path}' yazılırken boyut uyuşmadı; disk dolu olabilir.")
        if dest.exists():
            dest.rmdir()
        os.replace(tmp, dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return len(selected)
