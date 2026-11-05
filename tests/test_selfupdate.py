"""Paketlenmiş sürümün kendiliğinden güncellenmesi: indirme, SHA-256 doğrulama, yardımcı betik ve geri alma."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

from nxceviri.core import selfupdate
from nxceviri.core.errors import OperationCancelled
from nxceviri.core.progress import CancelToken, TaskContext
from nxceviri.core.selfupdate import (
    FAILURE_FILE,
    PACKAGE_EXE,
    WORK_DIR_NAME,
    PreparedInstall,
    backup_dir_for,
    build_helper_script,
    ensure_installable,
    helper_arguments,
    launch_installer,
    parse_checksum,
    powershell_path,
    prepare_package,
    take_install_failure,
)
from nxceviri.core.update import RELEASES_URL, ManualInstallError, UpdateError
from tests.test_update import TOKEN, FakeGitHub

DIGEST = "ab" * 32
WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="PowerShell yardımcısı yalnızca Windows'ta çalışır")


def _package(files: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in (files or {PACKAGE_EXE: b"MZ-yeni", "_internal/x.dll": b"x"}).items():
            zf.writestr(f"NXTR/{name}", data)
    return buf.getvalue()


@pytest.fixture
def install(tmp_path: Path) -> Path:
    """Kurulu eski sürümün klasörü."""
    folder = tmp_path / "Programlar" / "NXTR"
    folder.mkdir(parents=True)
    (folder / PACKAGE_EXE).write_bytes(b"MZ-eski")
    return folder


# --- SHA-256 dosyası -------------------------------------------------------------------------


def test_parse_checksum_reads_matching_file_name() -> None:
    text = f"{DIGEST.upper()}  NXTR-1.0.0-windows.zip\n{'cd' * 32} *baska.zip\n"
    assert parse_checksum(text, "NXTR-1.0.0-windows.zip") == DIGEST
    assert parse_checksum(text, "baska.zip") == "cd" * 32


@pytest.mark.parametrize("text", ["", "bozuk", f"{DIGEST}  baska-dosya.zip", "abc  NXTR-1.0.0-windows.zip"])
def test_parse_checksum_rejects_unusable_file(text: str) -> None:
    with pytest.raises(UpdateError, match="SHA-256"):
        parse_checksum(text, "NXTR-1.0.0-windows.zip")


# --- hazırlama -------------------------------------------------------------------------------


def _check(server: FakeGitHub, token: str | None = None) -> tuple[Any, Any]:
    updater = server.updater(token)
    return updater, updater.check("0.28.0")


def test_prepare_package_downloads_verifies_and_extracts(install: Path) -> None:
    server = FakeGitHub(package=_package())
    updater, info = _check(server)
    progress: list[str] = []
    prepared = prepare_package(updater, info, install, TaskContext(lambda _d, _t, msg: progress.append(msg)))
    assert prepared.version == "0.30.0"
    assert (prepared.new_dir / PACKAGE_EXE).read_bytes() == b"MZ-yeni"
    assert prepared.new_dir.parent.parent == install.parent / WORK_DIR_NAME
    assert not list(prepared.work_dir.glob("*.zip"))  # indirilen zip açıldıktan sonra silindi
    assert (install / PACKAGE_EXE).read_bytes() == b"MZ-eski"  # kurulu sürüme dokunulmadı
    assert any(m.startswith("İndiriliyor") for m in progress)
    assert all("Authorization" not in r.headers for r in server.requests)


def test_prepare_package_works_in_private_repo_with_key(install: Path) -> None:
    server = FakeGitHub(package=_package(), private=True)
    updater, info = _check(server, TOKEN)
    prepared = prepare_package(updater, info, install, TaskContext())
    assert (prepared.new_dir / PACKAGE_EXE).is_file()


def test_prepare_package_refuses_checksum_mismatch(install: Path) -> None:
    server = FakeGitHub(package=_package(), checksum=DIGEST)
    updater, info = _check(server)
    with pytest.raises(UpdateError, match="SHA-256 uyuşmuyor"):
        prepare_package(updater, info, install, TaskContext())
    assert not (install.parent / WORK_DIR_NAME).exists()  # hiçbir şey kurulmaz, kalıntı kalmaz


def test_prepare_package_refuses_incomplete_package(install: Path) -> None:
    server = FakeGitHub(package=_package({"baska.txt": b"x"}))
    updater, info = _check(server)
    with pytest.raises(UpdateError, match="paket eksik"):
        prepare_package(updater, info, install, TaskContext())
    assert not (install.parent / WORK_DIR_NAME).exists()


def test_prepare_package_refuses_unsafe_paths(install: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"NXTR/{PACKAGE_EXE}", b"x")
        zf.writestr("NXTR/../../kotu.txt", b"x")
    updater, info = _check(FakeGitHub(package=buf.getvalue()))
    with pytest.raises(UpdateError, match="güvensiz"):
        prepare_package(updater, info, install, TaskContext())
    assert not (install.parent.parent / "kotu.txt").exists()


def test_prepare_package_needs_assets_in_release(install: Path) -> None:
    server = FakeGitHub(releases=[{"tag_name": "v0.30.0", "name": "v0.30.0", "body": "", "draft": False}])
    updater, info = _check(server)
    with pytest.raises(ManualInstallError) as exc:
        prepare_package(updater, info, install, TaskContext())
    assert RELEASES_URL in exc.value.user_text()


def test_prepare_package_can_be_cancelled(install: Path) -> None:
    updater, info = _check(FakeGitHub(package=_package()))
    token = CancelToken()
    token.cancel()
    with pytest.raises(OperationCancelled):
        prepare_package(updater, info, install, TaskContext(token=token))
    assert not (install.parent / WORK_DIR_NAME).exists()


def test_unwritable_install_folder_suggests_manual_download(install: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_a: Any, **_k: Any) -> Any:
        raise PermissionError("erişim reddedildi")

    monkeypatch.setattr(tempfile, "TemporaryFile", denied)
    with pytest.raises(ManualInstallError) as exc:
        ensure_installable(install)
    assert "yazma izniniz yok" in exc.value.message
    assert RELEASES_URL in exc.value.hint
    server = FakeGitHub(package=_package())
    updater, info = _check(server)
    before = len(server.requests)
    with pytest.raises(ManualInstallError):
        prepare_package(updater, info, install, TaskContext())
    assert len(server.requests) == before  # yetki yoksa boşuna indirilmez


# --- yardımcı betik üretimi ------------------------------------------------------------------


def test_helper_script_receives_paths_as_arguments_not_text(tmp_path: Path) -> None:
    app = tmp_path / "Ali’s ‘Games’ Çeviri's" / "NXTR"
    args = helper_arguments(
        pid=4242,
        install_dir=app,
        new_dir=tmp_path / "yeni",
        work_dir=tmp_path / "is",
        failure_file=tmp_path / FAILURE_FILE,
    )
    script = build_helper_script()
    assert args[:3] == ["4242", str(app), str(tmp_path / "yeni")]
    assert args[3] == str(backup_dir_for(app))
    assert str(app) not in script  # yol betik metnine gömülmez: hiçbir tırnak türü onu bozamaz
    assert "param(" in script
    assert "[System.IO.Directory]::Move($backup, $app)" in script  # geri alma var
    assert "Set-Content -LiteralPath $failureFile" in script  # hata dosyası bırakılır
    assert "Set-Location" in script  # nötr çalışma dizinine geçilir


def test_helper_does_not_restart_old_app_when_it_never_closed() -> None:
    script = build_helper_script()
    assert "$restartOld = $false" in script
    assert "if ($restartOld -and" in script  # kapanmayan uygulamanın ikinci kopyası açılmaz


def test_launch_installer_writes_script_and_starts_detached(tmp_path: Path, install: Path) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    prepared = PreparedInstall("0.30.0", tmp_path / "yeni", tmp_path / "is")
    state = tmp_path / "durum"
    launch_installer(prepared, install, pid=77, state=state, popen=lambda cmd, **kw: calls.append((cmd, kw)))
    script = state / selfupdate.SCRIPT_FILE
    assert script.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM: yollardaki Türkçe harfler doğru okunsun
    cmd, kwargs = calls[0]
    assert cmd[cmd.index("-File") : cmd.index("-File") + 3] == ["-File", str(script), "77"]
    assert str(install) in cmd
    assert "Bypass" in cmd
    assert kwargs["close_fds"]
    assert kwargs["cwd"] == state  # uygulama klasörü çalışma dizini olarak devralınmaz


def test_launch_installer_reports_start_failure(tmp_path: Path, install: Path) -> None:
    def broken(*_a: Any, **_k: Any) -> Any:
        raise OSError("başlatılamadı")

    prepared = PreparedInstall("0.30.0", tmp_path / "yeni", tmp_path / "is")
    with pytest.raises(UpdateError, match="yardımcısı başlatılamadı"):
        launch_installer(prepared, install, pid=1, state=tmp_path / "durum", popen=broken)


def test_take_install_failure_is_shown_once(tmp_path: Path) -> None:
    assert take_install_failure(tmp_path) is None
    (tmp_path / FAILURE_FILE).write_text("Dosya kullanımda.", encoding="utf-8-sig")
    assert take_install_failure(tmp_path) == "Dosya kullanımda."
    assert take_install_failure(tmp_path) is None


# --- yardımcı betiği gerçekten çalıştırma (yalnızca Windows) ---------------------------------


def _run_helper(
    install: Path,
    new_dir: Path,
    work: Path,
    state: Path,
    *,
    attempts: int = 2,
    cwd: Path | None = None,
    pid: int = 2_000_000_000,  # çalışan bir süreç değil: beklenecek bir şey yok
    exit_wait_s: int = 120,
) -> subprocess.CompletedProcess[str]:
    state.mkdir(parents=True, exist_ok=True)
    script = state / "deneme.ps1"
    script.write_text(build_helper_script(attempts=attempts, delay_s=0, exit_wait_s=exit_wait_s), encoding="utf-8-sig")
    arguments = helper_arguments(
        pid=pid, install_dir=install, new_dir=new_dir, work_dir=work, failure_file=state / FAILURE_FILE
    )
    return subprocess.run(
        [powershell_path(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=cwd,
    )


def _fake_exe(folder: Path, marker: str) -> None:
    """Başlatılınca hemen çıkan gerçek bir .exe (Windows'un kendi `whoami.exe`'sinin kopyası) + işaret dosyası."""
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "whoami.exe", folder / PACKAGE_EXE)
    (folder / "surum.txt").write_text(marker, encoding="utf-8")


@pytest.fixture
def swap(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """(kurulu klasör, yeni klasör, çalışma klasörü, durum klasörü); yollarda Türkçe harf ve boşluk var."""
    parent = tmp_path / "Çeviri Stüdyosu"
    install = parent / "NXTR"
    work = parent / WORK_DIR_NAME
    new_dir = work / "acilan" / "NXTR"
    _fake_exe(install, "eski")
    (install / "kullanici.txt").write_text("dokunulmamalı", encoding="utf-8")
    _fake_exe(new_dir, "yeni")
    return install, new_dir, work, tmp_path / "durum"


@WINDOWS_ONLY
def test_helper_swaps_folder_and_cleans_up(swap: tuple[Path, Path, Path, Path]) -> None:
    install, new_dir, work, state = swap
    done = _run_helper(install, new_dir, work, state)
    assert done.returncode == 0, done.stderr
    assert (install / "surum.txt").read_text(encoding="utf-8") == "yeni"
    assert not (install / "kullanici.txt").exists()  # klasör olduğu gibi değişir; kullanıcı verisi klasör dışındadır
    assert not backup_dir_for(install).exists()  # başarıda yedek silinir
    assert not work.exists()
    assert take_install_failure(state) is None


@WINDOWS_ONLY
def test_helper_rolls_back_when_old_folder_is_locked(swap: tuple[Path, Path, Path, Path]) -> None:
    install, new_dir, work, state = swap
    with (install / "kullanici.txt").open("rb"):  # açık dosya klasörün yeniden adlandırılmasını engeller
        done = _run_helper(install, new_dir, work, state)
    assert done.returncode == 0, done.stderr
    assert (install / "surum.txt").read_text(encoding="utf-8") == "eski"
    assert (install / "kullanici.txt").read_text(encoding="utf-8") == "dokunulmamalı"
    assert not backup_dir_for(install).exists()
    failure = take_install_failure(state)
    assert failure is not None
    assert "yeniden adlandırılamadı" in failure


@WINDOWS_ONLY
def test_helper_restores_backup_when_new_folder_cannot_be_placed(swap: tuple[Path, Path, Path, Path]) -> None:
    install, new_dir, work, state = swap
    shutil.rmtree(new_dir)  # yerine konacak klasör kayboldu
    done = _run_helper(install, new_dir, work, state)
    assert done.returncode == 0, done.stderr
    assert (install / "surum.txt").read_text(encoding="utf-8") == "eski"  # eski sürüm geri kondu
    assert (install / "kullanici.txt").exists()
    assert not backup_dir_for(install).exists()
    failure = take_install_failure(state)
    assert failure is not None
    assert "geri konuldu" in failure


@WINDOWS_ONLY
def test_helper_swaps_when_started_from_the_app_folder(swap: tuple[Path, Path, Path, Path]) -> None:
    """Gerçek akışta yardımcı uygulama klasörünü çalışma dizini olarak devralabilir; değişim yine başarmalı."""
    install, new_dir, work, state = swap
    done = _run_helper(install, new_dir, work, state, cwd=install)
    assert done.returncode == 0, done.stderr
    assert (install / "surum.txt").read_text(encoding="utf-8") == "yeni"
    assert take_install_failure(state) is None


@WINDOWS_ONLY
def test_helper_handles_typographic_quotes_in_paths(tmp_path: Path) -> None:
    parent = tmp_path / "Ali’s ‘Games’ ‚x‛ Çeviri's"
    install = parent / "NXTR"
    work = parent / WORK_DIR_NAME
    new_dir = work / "acilan" / "NXTR"
    _fake_exe(install, "eski")
    _fake_exe(new_dir, "yeni")
    state = tmp_path / "durum"
    done = _run_helper(install, new_dir, work, state)
    assert done.returncode == 0, done.stderr
    assert (install / "surum.txt").read_text(encoding="utf-8") == "yeni"
    assert take_install_failure(state) is None


@WINDOWS_ONLY
def test_helper_does_not_execute_injection_text_in_path(tmp_path: Path) -> None:
    parent = tmp_path / "x’; New-Item -Path enjekte.txt -ItemType File; ‘"
    install = parent / "NXTR"
    work = parent / WORK_DIR_NAME
    new_dir = work / "acilan" / "NXTR"
    _fake_exe(install, "eski")
    _fake_exe(new_dir, "yeni")
    done = _run_helper(install, new_dir, work, tmp_path / "durum")
    assert done.returncode == 0, done.stderr
    assert not list(tmp_path.rglob("enjekte.txt"))
    assert (install / "surum.txt").read_text(encoding="utf-8") == "yeni"
