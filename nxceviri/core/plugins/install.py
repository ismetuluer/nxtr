"""Eklenti kurma: bir zip dosyasını ya da klasörü kullanıcı eklenti klasörüne güvenle kopyalar.

Zip yol geçişine karşı güvenli açılır (`..`, mutlak yol, sürücü harfi, simge bağı reddedilir) ve boyut
sınırı vardır. Önce geçici bir klasöre açılıp doğrulanır, sonra yerine taşınır; yarıda kalan kurulum
eski eklentiye dokunmaz.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from nxceviri.core.errors import NxError
from nxceviri.core.plugins.loader import (
    ENTRY_NAME,
    MANIFEST_NAME,
    manifest_problem,
    read_manifest,
    slug,
    user_plugin_dirs,
)

#: Bir eklentinin en çok dosya sayısı ve açılmış toplam boyutu (zip bombasına karşı).
MAX_FILES = 500
MAX_TOTAL_BYTES = 50 * 1024 * 1024
_CHUNK = 64 * 1024
_SYMLINK = 0o120000


class PluginInstallError(NxError):
    """Eklenti kurulamadı."""


class PluginExistsError(PluginInstallError):
    """Aynı adlı eklenti zaten kurulu; `replace=True` ile değiştirilebilir."""


def _safe_member(name: str) -> PurePosixPath:
    """Zip girdi adını doğrular; güvenli göreli yolu döndürür, değilse hata verir."""
    unified = name.replace("\\", "/")
    parts = unified.split("/")
    first = parts[0]
    if (
        not unified
        or "\x00" in unified
        or unified.startswith("/")
        or (len(first) >= 2 and first[1] == ":")
        or any(p == ".." for p in parts)
    ):
        raise PluginInstallError(
            f"Zip dosyası güvensiz bir yol içeriyor (“{name}”).",
            "Eklenti zip'i yalnızca kendi klasörünün içindeki dosyaları içermeli. Güvenmediğiniz bir kaynaktan "
            "geldiyse kurmayın.",
        )
    return PurePosixPath(unified)


def _extract_zip(archive: Path, target: Path) -> None:
    try:
        zf = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as exc:
        raise PluginInstallError(
            f"Zip dosyası açılamadı ({exc}).", "Dosyanın bozulmadığından emin olun ya da yeniden indirin."
        ) from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES:
            raise PluginInstallError(f"Zip çok fazla dosya içeriyor ({len(infos)}); bir eklenti en çok {MAX_FILES}.")
        total = 0
        for info in infos:
            rel = _safe_member(info.filename)
            if (info.external_attr >> 16) & 0o170000 == _SYMLINK:
                raise PluginInstallError(f"Zip simge bağı içeriyor (“{info.filename}”); bu desteklenmez.")
            dest = target.joinpath(*rel.parts)
            if not dest.resolve().is_relative_to(target.resolve()):
                raise PluginInstallError(f"Zip güvensiz bir yol içeriyor (“{info.filename}”).")
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, dest.open("wb") as out:
                while chunk := src.read(_CHUNK):
                    total += len(chunk)
                    if total > MAX_TOTAL_BYTES:
                        raise PluginInstallError(
                            f"Zip açıldığında {MAX_TOTAL_BYTES // (1024 * 1024)} MB'ı aşıyor; kurulmadı."
                        )
                    out.write(chunk)


def _copy_folder(source: Path, target: Path) -> None:
    for entry in source.rglob("*"):
        if entry.is_symlink() or entry.is_junction():
            raise PluginInstallError(
                f"Klasör simge bağı ya da bağlantı noktası içeriyor (“{entry.relative_to(source)}”); bu desteklenmez.",
                "Bağları gerçek dosyalarla değiştirin ya da klasörü zip yapıp ekleyin.",
            )
    files = [p for p in source.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    if len(files) > MAX_FILES or sum(p.stat().st_size for p in files) > MAX_TOTAL_BYTES:
        raise PluginInstallError(
            "Klasör çok büyük ya da çok fazla dosya içeriyor.",
            f"Bir eklenti en çok {MAX_FILES} dosya ve {MAX_TOTAL_BYTES // (1024 * 1024)} MB olabilir.",
        )
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".git"))


def _plugin_root(staged: Path) -> Path:
    """Açılmış içerikte `eklenti.toml`'un durduğu klasör: kökte ya da tek bir üst klasörün içinde."""
    if (staged / MANIFEST_NAME).is_file():
        return staged
    children = [c for c in staged.iterdir() if c.is_dir()]
    if len(children) == 1 and (children[0] / MANIFEST_NAME).is_file():
        return children[0]
    raise PluginInstallError(
        f"Seçilen dosyada {MANIFEST_NAME} bulunamadı.",
        f"Eklenti klasörünün (ya da zip'in kökünün) içinde {MANIFEST_NAME} ve {ENTRY_NAME} olmalı.",
    )


def install_plugin(source: Path, dest_root: Path | None = None, *, replace: bool = False) -> Path:
    """`source` (zip ya da klasör) eklentisini `dest_root` altına kurar; kurulan klasörü döndürür.

    Aynı adlı eklenti varsa `PluginExistsError` verilir; `replace=True` eskisini değiştirir.
    """
    root = dest_root if dest_root is not None else user_plugin_dirs()[0]
    if not source.exists():
        raise PluginInstallError("Seçilen dosya ya da klasör bulunamadı.", str(source))
    try:
        root.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".kurulum_", dir=root))
    except OSError as exc:
        raise PluginInstallError(f"Eklenti klasörü hazırlanamadı ({exc}).", f"Konum: {root}") from exc
    try:
        content = stage / "icerik"
        if source.is_dir():
            _copy_folder(source, content)
        elif source.suffix.lower() == ".zip":
            content.mkdir()
            _extract_zip(source, content)
        else:
            raise PluginInstallError("Yalnızca .zip dosyası ya da eklenti klasörü seçilebilir.")
        folder = _plugin_root(content)
        data, error = read_manifest(folder)
        problem = error or (manifest_problem(data) if data is not None else "")
        if problem:
            raise PluginInstallError(f"Eklenti kurulamadı: {problem}")
        if not (folder / ENTRY_NAME).is_file():
            raise PluginInstallError(f"Eklenti kurulamadı: {ENTRY_NAME} bulunamadı.")
        assert data is not None
        target = root / slug(str(data["ad"]))
        old = stage / "eski"
        if target.exists():
            if not replace:
                raise PluginExistsError(
                    f"“{data['ad']}” eklentisi zaten kurulu.", f"Konum: {target}. Değiştirmek için onaylayın."
                )
            shutil.move(str(target), str(old))
        try:
            shutil.move(str(folder), str(target))
        except OSError as exc:
            if old.exists():
                shutil.move(str(old), str(target))
            raise PluginInstallError(f"Eklenti yerine taşınamadı ({exc}).", f"Konum: {target}") from exc
        return target
    except OSError as exc:
        raise PluginInstallError(f"Eklenti kurulamadı ({exc}).", "Dosya izinlerini ve boş alanı denetleyin.") from exc
    finally:
        shutil.rmtree(stage, ignore_errors=True)
