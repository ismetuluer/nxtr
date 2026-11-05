"""Paketlenmiş (PyInstaller) sürümün kendiliğinden güncellenmesi.

Çalışan `NXTR.exe` kendi klasörünü değiştiremez; bu yüzden güncelleme iki parçadır:

1. **Hazırla** (`prepare_package`, uygulama çalışırken, arka plan işi): release'teki
   `NXTR-<sürüm>-windows.zip` indirilir, yanındaki `.sha256` dosyasıyla doğrulanır (uyuşmazsa
   hiçbir şey kurulmaz) ve uygulama klasörünün **yanındaki** bir çalışma klasörüne açılır (aynı
   sürücü, böylece son adım yeniden adlandırmadır, kopyalama değil).
2. **Kur** (`launch_installer`): küçük bir PowerShell yardımcısı başlatılır. Yardımcı uygulama
   sürecinin bitmesini bekler, eski klasörü yedek adla yeniden adlandırır, yenisini yerine koyar ve
   yeni `NXTR.exe`'yi başlatır. Herhangi bir adım başarısız olursa yedeği geri koyar, eski sürümü
   yeniden açar ve `hata.txt` bırakır; uygulama bir sonraki açılışta bunu kullanıcıya gösterir
   (`take_install_failure`).

Uygulama klasörü dışındaki hiçbir şeye dokunulmaz: eklentiler, kurtarma, loglar
(`%LOCALAPPDATA%\\NXCeviri`), projeler ve ayarlar oradadır.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nxceviri.core.progress import TaskContext
from nxceviri.core.update import (
    MAX_PACKAGE_BYTES,
    RELEASES_URL,
    GitHubUpdater,
    ManualInstallError,
    UpdateError,
    UpdateInfo,
    extract_archive,
)

log = logging.getLogger(__name__)

PACKAGE_EXE = "NXTR.exe"
#: Uygulama klasörünün yanında açılan çalışma klasörü (indirilen zip ve açılmış yeni sürüm).
WORK_DIR_NAME = ".nxtr-guncelleme"
FAILURE_FILE = "hata.txt"
SCRIPT_FILE = "guncelle.ps1"
#: Yardımcının eski klasörü yeniden adlandırmayı deneme sayısı ve aralığı (virüs tarayıcısı geçici kilit tutabilir).
RENAME_ATTEMPTS = 20
RENAME_DELAY_S = 1
#: Uygulama sürecinin kapanmasını bekleme süresi (saniye).
EXIT_WAIT_S = 120

_CHECKSUM_RE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$")


@dataclass(frozen=True)
class PreparedInstall:
    """İndirilip doğrulanmış, yerine konmayı bekleyen yeni sürüm."""

    version: str
    new_dir: Path  # açılmış yeni klasör (içinde NXTR.exe)
    work_dir: Path  # silinecek çalışma klasörü


def state_dir() -> Path:
    """Yardımcı betiğin ve hata dosyasının durduğu yer; uygulama klasörünün dışındadır."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NXCeviri" / "guncelleme"


def current_install() -> Path:
    """Çalışan paketlenmiş uygulamanın klasörü."""
    return Path(sys.executable).resolve().parent


def ensure_installable(install_dir: Path) -> None:
    """Uygulama klasörüne ve üst klasörüne yazılabiliyor mu? Değilse elle indirme önerilir."""
    for folder in (install_dir, install_dir.parent):
        try:
            with tempfile.TemporaryFile(dir=folder):
                pass
        except OSError:
            raise ManualInstallError(
                f"Uygulama klasörüne yazma izniniz yok: {install_dir}",
                f"Yeni sürümü elle indirip eski klasörün yerine açın: {RELEASES_URL}",
            ) from None


def parse_checksum(text: str, file_name: str) -> str:
    """`<hex>  <dosya adı>` biçimindeki SHA-256 dosyasından `file_name` için özeti okur."""
    for line in text.splitlines():
        m = _CHECKSUM_RE.match(line)
        if m and m.group(2) == file_name:
            return m.group(1).lower()
    raise UpdateError(
        "Sürümün SHA-256 doğrulama dosyası okunamadı; güncelleme yapılmadı.",
        "Yayımda bir aksaklık olabilir. Daha sonra yeniden deneyin veya elle indirin.",
    )


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_package(updater: GitHubUpdater, info: UpdateInfo, install_dir: Path, ctx: TaskContext) -> PreparedInstall:
    """Paketi indirir, SHA-256 ile doğrular ve `install_dir`'in yanına açar."""
    if not info.package_url or not info.checksum_url:
        raise ManualInstallError(
            f"{info.version} sürümünde otomatik kurulum paketi veya doğrulama dosyası yok.",
            f"Yeni sürümü elle indirin: {RELEASES_URL}",
        )
    ensure_installable(install_dir)
    work = install_dir.parent / WORK_DIR_NAME
    shutil.rmtree(work, ignore_errors=True)
    name = f"NXTR-{info.version}-windows.zip"
    archive = work / name
    try:
        expected = parse_checksum(updater.fetch_text(info.checksum_url), name)
        updater.download_file(info.package_url, archive, MAX_PACKAGE_BYTES, ctx)
        ctx.report(0, 0, "Doğrulanıyor")
        if sha256_of(archive) != expected:
            raise UpdateError(
                "İndirilen dosya doğrulanamadı (SHA-256 uyuşmuyor); güncelleme yapılmadı.",
                "Dosya indirilirken bozulmuş olabilir. Yeniden deneyin.",
            )
        ctx.check()
        ctx.report(0, 0, "Açılıyor")
        extracted = work / "acilan"
        extracted.mkdir()
        new_dir = extract_archive(archive, extracted)
        archive.unlink()
        if not (new_dir / PACKAGE_EXE).is_file():
            raise UpdateError("İndirilen paket eksik; güncelleme yapılmadı.", "Daha sonra yeniden deneyin.")
    except OSError as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise UpdateError("Güncelleme hazırlanamadı.", f"Diskte yer olduğundan emin olun. ({exc})") from None
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)  # hata veya iptal: yarım dosya kalmaz
        raise
    return PreparedInstall(info.version, new_dir, work)


def discard_prepared(prepared: PreparedInstall) -> None:
    """Kurulmayacak hazırlığı siler."""
    shutil.rmtree(prepared.work_dir, ignore_errors=True)


def backup_dir_for(install_dir: Path) -> Path:
    return install_dir.with_name(install_dir.name + ".eski")


def helper_arguments(*, pid: int, install_dir: Path, new_dir: Path, work_dir: Path, failure_file: Path) -> list[str]:
    """Betiğe komut satırı bağımsız değişkeni olarak geçen yollar (betik metnine gömülmez; tırnak türü sorun olmaz)."""
    return [
        str(int(pid)),
        str(install_dir),
        str(new_dir),
        str(backup_dir_for(install_dir)),
        str(work_dir),
        PACKAGE_EXE,
        str(failure_file),
    ]


def build_helper_script(
    *,
    attempts: int = RENAME_ATTEMPTS,
    delay_s: int = RENAME_DELAY_S,
    exit_wait_s: int = EXIT_WAIT_S,
) -> str:
    """Yardımcı PowerShell betiğinin metni (UTF-8 BOM ile yazılmalı); yollar `helper_arguments` ile verilir."""
    return f"""param(
    [int]$appPid,
    [string]$app,
    [string]$new,
    [string]$backup,
    [string]$work,
    [string]$exe,
    [string]$failureFile
)
$ErrorActionPreference = 'Stop'
# Uygulama klasörü bu sürecin çalışma dizini olarak kalırsa Windows klasörün yeniden adlandırılmasını engeller.
$neutral = Split-Path -Parent $failureFile
[System.IO.Directory]::CreateDirectory($neutral) | Out-Null
Set-Location -LiteralPath $neutral
[System.Environment]::CurrentDirectory = $neutral
Remove-Item -LiteralPath $failureFile -Force -ErrorAction SilentlyContinue
$restartOld = $true
try {{
    $proc = Get-Process -Id $appPid -ErrorAction SilentlyContinue
    if ($proc -and -not $proc.WaitForExit({int(exit_wait_s) * 1000})) {{
        $restartOld = $false
        throw 'Uygulama kapanmadı; güncelleme yapılmadı. Uygulamayı kapatıp yeniden deneyin.'
    }}
    if (Test-Path -LiteralPath $backup) {{
        Remove-Item -LiteralPath $backup -Recurse -Force
    }}
    $moved = $false
    $reason = ''
    for ($i = 0; $i -lt {int(attempts)} -and -not $moved; $i++) {{
        try {{
            [System.IO.Directory]::Move($app, $backup)
            $moved = $true
        }} catch {{
            $reason = $_.Exception.Message
            Start-Sleep -Seconds {int(delay_s)}
        }}
    }}
    if (-not $moved) {{
        throw "Eski klasör yeniden adlandırılamadı (bir dosya kullanımda olabilir): $reason"
    }}
    try {{
        [System.IO.Directory]::Move($new, $app)
    }} catch {{
        $reason = $_.Exception.Message
        [System.IO.Directory]::Move($backup, $app)
        throw "Yeni klasör yerine konamadı, eski sürüm geri konuldu: $reason"
    }}
    Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    Start-Process -FilePath (Join-Path $app $exe) -WorkingDirectory $app
}} catch {{
    $message = $_.Exception.Message
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $failureFile) | Out-Null
    Set-Content -LiteralPath $failureFile -Value $message -Encoding UTF8
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $app) -and (Test-Path -LiteralPath $backup)) {{
        [System.IO.Directory]::Move($backup, $app)
    }}
    $old = Join-Path $app $exe
    if ($restartOld -and (Test-Path -LiteralPath $old)) {{
        Start-Process -FilePath $old -WorkingDirectory $app -ErrorAction SilentlyContinue
    }}
}}
"""


def powershell_path() -> str:
    root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    system = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if system.is_file():
        return str(system)
    found = shutil.which("powershell.exe")
    if found is None:
        raise UpdateError("PowerShell bulunamadı; güncelleme kurulamadı.", f"Yeni sürümü elle indirin: {RELEASES_URL}")
    return found


def launch_installer(
    prepared: PreparedInstall,
    install_dir: Path,
    *,
    pid: int | None = None,
    state: Path | None = None,
    popen: Callable[..., Any] = subprocess.Popen,
) -> None:
    """Yardımcıyı başlatır. Çağıran bundan sonra uygulamayı kapatmalıdır (yardımcı kapanmasını bekler)."""
    folder = state if state is not None else state_dir()
    script = folder / SCRIPT_FILE
    try:
        folder.mkdir(parents=True, exist_ok=True)
        script.write_text(
            build_helper_script(),
            encoding="utf-8-sig",
        )
        popen(
            [
                powershell_path(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(script),
                *helper_arguments(
                    pid=os.getpid() if pid is None else pid,
                    install_dir=install_dir,
                    new_dir=prepared.new_dir,
                    work_dir=prepared.work_dir,
                    failure_file=folder / FAILURE_FILE,
                ),
            ],
            cwd=folder,  # uygulama klasörü çalışma dizini olursa kendi yeniden adlandırması engellenir
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=(
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            ),
        )
    except OSError as exc:
        raise UpdateError(
            "Güncelleme yardımcısı başlatılamadı.", f"Yeni sürümü elle indirin: {RELEASES_URL} ({exc})"
        ) from None
    log.info("Güncelleme yardımcısı başlatıldı: %s", prepared.version)


def take_install_failure(state: Path | None = None) -> str | None:
    """Önceki kurulum denemesi başarısız olduysa nedenini döndürür ve dosyayı siler (bir kez gösterilir)."""
    path = (state if state is not None else state_dir()) / FAILURE_FILE
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None
    path.unlink(missing_ok=True)
    return text or "Bilinmeyen bir neden."
