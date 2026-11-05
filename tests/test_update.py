"""GitHub'dan uygulama güncellemesi: sürüm denetimi, indirme, hazırlama, uygulama ve geri alma."""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from nxceviri.core.errors import OperationCancelled
from nxceviri.core.progress import CancelToken, TaskContext
from nxceviri.core.update import (
    STAGING_DIR,
    AccessError,
    GitHubUpdater,
    GitUpdater,
    UpdateError,
    UpdateInfo,
    app_root,
    apply_staged,
    changelog_since,
    is_git_checkout,
    make_updater,
    parse_version,
    pending_version,
    relaunch,
    run_git,
    stage,
    staging_dir,
    tag_version,
)

SHA = "a" * 40
TOKEN = "github_pat_deneme"

CHANGELOG = """# Değişiklik Günlüğü

## [0.30.0] — 2026-11-01 — Yeni şey
- Üçüncü.

## [0.29.0] — 2026-10-30 — Orta
- İkinci.

## [0.28.0] — 2026-10-25 — Eski
- Birinci.
"""


def _pyproject(version: str, deps: str = '"httpx"') -> str:
    return f'[project]\nname = "nxceviri"\nversion = "{version}"\ndependencies = [{deps}]\n'


def _archive(files: dict[str, str], top: str = f"ismetuluer-nxtr-{SHA[:7]}") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{top}/", "")
        for name, text in files.items():
            zf.writestr(f"{top}/{name}", text)
    return buf.getvalue()


def _release(version: str = "0.30.0", **extra: str) -> dict[str, str]:
    return {
        "pyproject.toml": _pyproject(version),
        "nxceviri/__init__.py": f'__version__ = "{version}"\n',
        "nxceviri/core/yeni.py": "# yeni modül\n",
        "README.md": "yeni beni oku\n",
        "CHANGELOG.md": CHANGELOG,
        **extra,
    }


ASSET_API = "https://api.github.com/repos/ismetuluer/nxtr/releases/assets"
PACKAGE = b"PK-paket-icerigi"


def _releases(*versions: str, assets: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "tag_name": f"v{v}",
            "name": f"v{v}",
            "body": f"## [{v}]\n- {v} notları",
            "draft": False,
            "assets": (
                [
                    {"name": f"NXTR-{v}-windows.zip", "url": f"{ASSET_API}/1"},
                    {"name": f"NXTR-{v}-windows.zip.sha256", "url": f"{ASSET_API}/2"},
                ]
                if assets
                else []
            ),
        }
        for v in versions
    ]


@dataclass
class FakeGitHub:
    """Sahte GitHub: ağ yok. `private` iken anahtarsız istekler 404 alır."""

    version: str = "0.30.0"
    archive: bytes = b""
    status: int | None = None
    releases: list[dict[str, Any]] | None = None
    private: bool = False
    rate_limited: bool = False
    package: bytes = PACKAGE
    checksum: str | None = None  # None: pakete uyan doğru özet
    requests: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status is not None:
            return httpx.Response(self.status, json={"message": "hata"})
        if self.rate_limited:
            return httpx.Response(
                403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"}, json={}
            )
        if (
            self.private
            and request.url.host == "api.github.com"
            and request.headers.get("Authorization") != f"Bearer {TOKEN}"
        ):
            return httpx.Response(404, json={"message": "Not Found"})
        path = request.url.path
        if path.endswith("/releases"):
            default = _releases(self.version, "0.29.0", "0.28.0", assets=True)
            return httpx.Response(200, json=default if self.releases is None else self.releases)
        if path.endswith("/releases/assets/1"):
            return httpx.Response(302, headers={"location": "https://objects.example.com/paket.zip"})
        if path.endswith("/releases/assets/2"):
            digest = self.checksum or hashlib.sha256(self.package).hexdigest()
            return httpx.Response(200, text=f"{digest}  NXTR-{self.version}-windows.zip\n")
        if request.url.host == "objects.example.com":
            return httpx.Response(200, content=self.package)
        if path.endswith(f"/commits/v{self.version}"):
            return httpx.Response(200, text=SHA)
        if path.endswith(f"/zipball/{SHA}"):
            return httpx.Response(302, headers={"location": "https://codeload.github.com/arsiv.zip"})
        if request.url.host == "codeload.github.com":
            return httpx.Response(200, content=self.archive or _archive(_release(self.version)))
        return httpx.Response(404, json={"message": "Not Found"})

    def updater(self, token: str | None = None) -> GitHubUpdater:
        return GitHubUpdater(token, client=httpx.Client(transport=httpx.MockTransport(self.handler)))


@pytest.fixture
def app(tmp_path: Path) -> Path:
    """Kurulu eski sürümün klasörü (kullanıcı verisiyle)."""
    root = tmp_path / "uygulama"
    files = {
        "pyproject.toml": _pyproject("0.28.0"),
        "nxceviri/__init__.py": '__version__ = "0.28.0"\n',
        "nxceviri/core/eski.py": "# kaldırılan modül\n",
        "nxceviri/core/__pycache__/eski.cpython-313.pyc": "önbellek",
        "README.md": "eski beni oku\n",
        "projeler/Despelote.nxproj": "kullanıcı projesi",
        ".venv/kurulu_pyproject.toml": "kurulum izi",
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


# --- sürüm ve notlar ------------------------------------------------------------------------


def test_parse_version_and_changelog() -> None:
    assert parse_version("0.28.0") < parse_version("0.29.0") < parse_version("1.0.0")
    assert parse_version("bozuk") == (0, 0, 0)
    notes = changelog_since(CHANGELOG, "0.28.0")
    assert notes.startswith("## [0.30.0]")
    assert "İkinci" in notes
    assert "Birinci" not in notes
    assert changelog_since(CHANGELOG, "0.30.0") == ""


def test_check_is_anonymous_first_and_never_sends_key_to_public_repo() -> None:
    server = FakeGitHub()
    info = server.updater(TOKEN).check("0.28.0")
    assert (info.version, info.sha, info.newer) == ("0.30.0", SHA, True)
    assert info.notes.index("0.30.0 notları") < info.notes.index("0.29.0 notları")  # yeniden eskiye
    assert "0.28.0 notları" not in info.notes
    assert info.package_url == f"{ASSET_API}/1"
    assert info.checksum_url == f"{ASSET_API}/2"
    assert all("Authorization" not in r.headers for r in server.requests)  # açık depoda anahtar gitmez
    assert TOKEN not in repr(server.updater(TOKEN))
    same = FakeGitHub(version="0.28.0", releases=_releases("0.28.0")).updater().check("0.28.0")
    assert not same.newer
    assert same.notes == ""
    assert same.package_url == ""  # varlık yoksa boş


def test_private_repo_falls_back_to_key() -> None:
    server = FakeGitHub(private=True)
    updater = server.updater(TOKEN)
    assert updater.check("0.28.0").version == "0.30.0"
    assert "Authorization" not in server.requests[0].headers  # önce anahtarsız
    assert server.requests[1].headers["Authorization"] == f"Bearer {TOKEN}"
    before = len(server.requests)
    updater.check("0.28.0")
    # Anahtarsız deneme bir kez başarısız oldu; sonraki isteklerde boşuna yinelenmez.
    assert all(r.headers.get("Authorization") == f"Bearer {TOKEN}" for r in server.requests[before:])


def test_private_repo_without_key_needs_key() -> None:
    with pytest.raises(AccessError) as exc:
        FakeGitHub(private=True).updater(None).check("0.28.0")
    assert "anahtarı gerekir" in exc.value.user_text()


def test_rate_limit_message_is_turkish() -> None:
    with pytest.raises(UpdateError) as exc:
        FakeGitHub(rate_limited=True).updater().check("0.28.0")
    assert not isinstance(exc.value, AccessError)  # anahtar adımları gösterilmez
    assert "istek sınırı" in exc.value.message
    assert "dakika sonra" in exc.value.hint
    with pytest.raises(UpdateError, match="istek sınırı"):
        FakeGitHub(status=429).updater().check("0.28.0")


def test_check_ignores_drafts_prereleases_and_other_tags() -> None:
    releases = [
        {"tag_name": "v9.0.0", "draft": True},
        {"tag_name": "v8.0.0", "prerelease": True},
        {"tag_name": "deneme", "draft": False},
        *_releases("0.30.0", "0.29.0"),
    ]
    info = FakeGitHub(releases=releases).updater().check("0.28.0")
    assert info.version == "0.30.0"
    with pytest.raises(UpdateError, match="henüz yayımlanmış bir sürüm"):
        FakeGitHub(releases=[]).updater().check("0.28.0")


def test_tag_version() -> None:
    assert tag_version("v0.28.0") == "0.28.0"
    assert tag_version("0.28.0") == "0.28.0"
    assert tag_version("v0.28.0-beta") is None
    assert tag_version("son") is None


@pytest.mark.parametrize(
    ("status", "token", "message"),
    [
        (401, TOKEN, "geçersiz"),
        (401, None, "erişim anahtarı gerekir"),
        (404, None, "erişim anahtarı gerekir"),
        (404, TOKEN, "Contents: Read-only"),
        (500, TOKEN, "HTTP 500"),
    ],
)
def test_check_errors_are_turkish(status: int, token: str | None, message: str) -> None:
    with pytest.raises(UpdateError) as exc:
        FakeGitHub(status=status).updater(token).check("0.28.0")
    assert message in exc.value.user_text()
    assert TOKEN not in exc.value.user_text()


def test_network_failure() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("yok", request=request)

    updater = GitHubUpdater(TOKEN, client=httpx.Client(transport=httpx.MockTransport(down)))
    with pytest.raises(UpdateError, match="bağlanılamadı"):
        updater.check("0.28.0")

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("yavaş", request=request)

    with pytest.raises(UpdateError, match="zamanında"):
        GitHubUpdater(None, client=httpx.Client(transport=httpx.MockTransport(slow))).check("0.28.0")


# --- indirme ve hazırlama -------------------------------------------------------------------


def _info(version: str = "0.30.0") -> UpdateInfo:
    return UpdateInfo("0.28.0", version, SHA, "")


def test_download_and_stage(app: Path) -> None:
    progress: list[int] = []
    ctx = TaskContext(lambda done, total, msg: progress.append(done))
    archive = FakeGitHub().updater().download(_info(), app / STAGING_DIR, ctx)
    assert archive.is_file()
    assert progress
    staged = stage(archive, app, "0.30.0")
    assert staged == staging_dir(app)
    assert (staged / "nxceviri" / "core" / "yeni.py").is_file()
    assert pending_version(app) == "0.30.0"
    assert not (app / STAGING_DIR / "aciliyor").exists()


def test_download_can_be_cancelled(app: Path) -> None:
    token = CancelToken()
    token.cancel()
    with pytest.raises(OperationCancelled):
        FakeGitHub().updater().download(_info(), app / STAGING_DIR, TaskContext(token=token))
    assert list((app / STAGING_DIR).iterdir()) == []  # yarım dosya kalmaz


@pytest.mark.parametrize(
    ("archive", "message"),
    [
        (_archive(_release("0.29.0")), "beklenen sürüm"),
        (_archive({"README.md": "eksik"}), "eksik"),
        (_archive({**_release(), "../../kotu.py": "x"}), "güvensiz"),
        (b"zip degil", "bozuk"),
    ],
)
def test_stage_rejects_bad_archives(app: Path, archive: bytes, message: str) -> None:
    path = app / "arsiv.zip"
    path.write_bytes(archive)
    with pytest.raises(UpdateError, match=message):
        stage(path, app, "0.30.0")
    assert pending_version(app) is None
    assert not (app.parent / "kotu.py").exists()


def test_stage_rejects_archive_with_two_top_folders(app: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a/pyproject.toml", _pyproject("0.30.0"))
        zf.writestr("b/README.md", "x")
    (app / "arsiv.zip").write_bytes(buf.getvalue())
    with pytest.raises(UpdateError, match="yapısı"):
        stage(app / "arsiv.zip", app, "0.30.0")


# --- uygulama --------------------------------------------------------------------------------


def _stage_release(app: Path, files: dict[str, str]) -> None:
    (app / "arsiv.zip").write_bytes(_archive(files))
    stage(app / "arsiv.zip", app, "0.30.0")


def test_apply_replaces_code_and_keeps_user_data(app: Path) -> None:
    assert apply_staged(app) is None  # hazır güncelleme yok
    _stage_release(app, _release(**{"pyproject.toml": _pyproject("0.30.0", deps='"httpx", "yeni-paket"')}))
    result = apply_staged(app)
    assert result is not None
    assert (result.version, result.removed) == ("0.30.0", 1)
    assert result.dependencies_changed
    assert (app / "nxceviri" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "0.30.0"\n'
    assert (app / "README.md").read_text(encoding="utf-8") == "yeni beni oku\n"
    assert (app / "nxceviri" / "core" / "yeni.py").is_file()
    assert not (app / "nxceviri" / "core" / "eski.py").exists()  # yeni sürümde olmayan modül silindi
    assert (app / "nxceviri" / "core" / "__pycache__" / "eski.cpython-313.pyc").exists()  # önbelleğe dokunulmaz
    assert (app / "projeler" / "Despelote.nxproj").read_text(encoding="utf-8") == "kullanıcı projesi"
    assert (app / ".venv" / "kurulu_pyproject.toml").exists()
    assert pending_version(app) is None  # hazır klasör temizlendi
    assert (app / STAGING_DIR / "yedek" / "nxceviri" / "core" / "eski.py").is_file()  # eski dosyalar yedekte


def test_apply_without_dependency_change(app: Path) -> None:
    # Yalnızca sürüm numarası ve satır sonları (Windows'ta CRLF) farklı: paketler yeniden kurulmaz.
    (app / "pyproject.toml").write_bytes(_pyproject("0.28.0").replace("\n", "\r\n").encode("utf-8"))
    _stage_release(app, _release())
    result = apply_staged(app)
    assert result is not None
    assert not result.dependencies_changed


def test_apply_rolls_back_on_failure(app: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage_release(app, _release())
    real_copy = shutil.copy2
    calls = {"n": 0}

    def failing_copy(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
        if "yedek" not in str(dst) and str(dst).endswith("yeni.py"):
            calls["n"] += 1
            raise PermissionError("kullanımda")
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", failing_copy)
    with pytest.raises(UpdateError, match="uygulanamadı"):
        apply_staged(app, attempts=2, wait_s=0)
    assert calls["n"] == 2  # yeniden denendi
    # Her şey eski hâline döndü; hazırlanan sürüm bir sonraki açılış için duruyor.
    assert (app / "nxceviri" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "0.28.0"\n'
    assert (app / "README.md").read_text(encoding="utf-8") == "eski beni oku\n"
    assert (app / "nxceviri" / "core" / "eski.py").is_file()
    assert pending_version(app) == "0.30.0"


def test_relaunch_uses_python_outside_windows(app: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr("os.name", "posix")
    relaunch(app, popen=lambda cmd, **kw: calls.append((cmd, kw)))
    assert calls[0][0][1:] == ["-m", "nxceviri"]
    assert calls[0][1]["cwd"] == str(app)


def test_relaunch_uses_launcher_on_windows(app: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (app / "NX Ceviri Studyosu.bat").write_text("@echo off", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr("os.name", "nt")
    relaunch(app, popen=lambda cmd, **kw: calls.append(cmd))
    assert calls == [["cmd.exe", "/c", str(app / "NX Ceviri Studyosu.bat")]]


def test_app_root_is_this_checkout() -> None:
    root = app_root()
    assert root is not None
    assert (root / "nxceviri" / "core" / "update.py").is_file()


# --- git yolu ------------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _commit(work: Path, files: dict[str, str], message: str, tag: str = "") -> str:
    for name, text in files.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text(text, encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", message)
    _git(work, "push", "-q", "origin", "master")
    if tag:  # GitHub Actions'ın release oluştururken attığı etiket
        _git(work, "tag", tag)
        _git(work, "push", "-q", "origin", tag)
    return _git(work, "rev-parse", "HEAD").strip()


@pytest.fixture
def git_app(tmp_path: Path) -> tuple[Path, Path]:
    """(kullanıcının git deposu olan uygulama klasörü, geliştiricinin çalışma kopyası)."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    work = tmp_path / "yazar"
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _git(work, "checkout", "-q", "-b", "master")
    _commit(
        work,
        {
            "pyproject.toml": _pyproject("0.28.0"),
            "nxceviri/__init__.py": '__version__ = "0.28.0"\n',
            "CHANGELOG.md": CHANGELOG,
            ".gitignore": ".guncelleme/\nprojeler/\n",
        },
        "0.28.0",
        tag="v0.28.0",
    )
    app = tmp_path / "uygulama"
    _git(tmp_path, "clone", "-q", str(origin), str(app))
    (app / "projeler").mkdir()
    (app / "projeler" / "Despelote.nxproj").write_text("kullanıcı projesi", encoding="utf-8")
    _commit(
        work,
        {
            "pyproject.toml": _pyproject("0.30.0", deps='"httpx", "yeni-paket"'),
            "nxceviri/__init__.py": '__version__ = "0.30.0"\n',
            "nxceviri/core/yeni.py": "# yeni\n",
        },
        "0.30.0",
        tag="v0.30.0",
    )
    _commit(work, {"README.md": "yayımlanmamış ara değişiklik\n"}, "ara commit")  # etiketsiz: kullanıcıya gitmez
    return app, work


def test_git_checkout_uses_git_updater(git_app: tuple[Path, Path], tmp_path: Path) -> None:
    app, _ = git_app
    assert is_git_checkout(app)
    assert isinstance(make_updater(app, None), GitUpdater)
    assert isinstance(make_updater(tmp_path, TOKEN), GitHubUpdater)


def test_git_check_only_reports_and_never_applies(git_app: tuple[Path, Path]) -> None:
    app, work = git_app
    updater = make_updater(app, None)
    assert updater.uses_git
    info = updater.check("0.28.0")
    assert (info.version, info.newer) == ("0.30.0", True)
    assert info.sha == _git(work, "rev-parse", "v0.30.0").strip()  # son commit değil, son sürüm
    assert "Üçüncü" in info.notes
    assert not hasattr(updater, "prepare")  # git deposunda kendiliğinden güncelleme yok: "git pull" önerilir
    assert pending_version(app) is None
    assert _git(app, "rev-parse", "HEAD").strip() != info.sha


def test_git_without_release_tags(git_app: tuple[Path, Path]) -> None:
    app, work = git_app
    for tag in ("v0.28.0", "v0.30.0"):
        _git(work, "push", "-q", "origin", f":refs/tags/{tag}")
    _git(app, "tag", "-d", "v0.28.0")  # klonda yalnızca o anda var olan etiket
    with pytest.raises(UpdateError, match="henüz yayımlanmış bir sürüm"):
        make_updater(app, None).check("0.28.0")


def test_git_tag_must_match_pyproject(git_app: tuple[Path, Path]) -> None:
    app, work = git_app
    _git(work, "tag", "v0.31.0", "v0.30.0")  # sürüm numarası 0.30.0 olan commit'e yanlış etiket
    _git(work, "push", "-q", "origin", "v0.31.0")
    with pytest.raises(UpdateError, match="uyuşmuyor"):
        make_updater(app, None).check("0.28.0")


def test_git_errors_are_readable(tmp_path: Path) -> None:
    with pytest.raises(UpdateError, match="git rev-parse"):
        run_git(tmp_path, "rev-parse", "HEAD")
