"""Uygulamayı GitHub'daki depodan güncelleme.

Güncellemenin üç yolu vardır; hepsinde önce **denetle** (`check`): depodaki en yeni **sürüm
(release)** bulunur. Sürümler `v0.28.0` gibi etiketlerdir; master'a sürüm numarası değişmiş bir
commit gelince GitHub Actions (`.github/workflows/release.yml`) etiketi ve release'i CHANGELOG
bölümüyle kendiliğinden oluşturur. Böylece kullanıcıya yalnızca bilerek yayımlanan sürümler gider;
master'daki ara commit'ler gitmez. Release açıklaması güncelleme penceresinde değişiklik notu olur.

**GitHub erişimi** (`GitHubUpdater`): her istek önce anahtarsız yapılır (depo herkese açıksa
anahtar hiç gerekmez). Depo özelse (404/401) ve kayıtlı bir anahtar varsa istek anahtarla
yinelenir; anahtar da yoksa `AccessError` fırlatılır ve arayüz anahtar adımlarını gösterir.
Anahtar Windows Kimlik Bilgisi Yöneticisi'nde saklanır; loglanmaz, hata mesajlarına yazılmaz.
İstek sınırı (403/429) ve ağ hataları Türkçe, anlaşılır mesajlara çevrilir.

1. **Paketlenmiş sürüm** (`NXTR.exe`): kendi klasörünü çalışırken değiştiremez. Kurulum
   `selfupdate.py`'dedir: `NXTR-<sürüm>-windows.zip` indirilir, release'teki `.sha256` ile
   doğrulanır, açılır ve uygulama kapanınca çalışan küçük bir PowerShell yardımcısı klasörü değiştirir.
2. **Kaynak kurulum, git deposu değil** (arşiv yolu): commit'in zip arşivi indirilir,
   `.guncelleme/hazir/` klasörüne açılır ve doğrulanır (sürüm beklenen sürüm mü, paket eksiksiz mi,
   arşivden klasör dışına yol çıkıyor mu). `apply_staged` uygulama yeniden başlatılırken, hiçbir
   modül veya yazı tipi henüz açılmamışken dosyaları yerine yazar; üzerine yazılan ve silinen
   dosyalar önce `.guncelleme/yedek/` klasörüne alınır, yazım yarıda kalırsa hepsi geri konur.
   Başlatıcı `pyproject.toml` değiştiyse yeni paketleri kurar. Kullanıcının verisine dokunulmaz:
   `.venv`, `projeler`, `games`, proje dosyaları ve önbellekler arşivde olmadığı için ne silinir ne
   de üzerine yazılır. Yalnızca `nxceviri/` ve `tests/` içinde, yeni sürümde artık bulunmayan kaynak
   dosyaları silinir (eski modül kalıntısı kalmasın diye).
3. **Kaynak kurulum, git deposu** (`GitUpdater`): yalnızca denetlenir (`git fetch --tags`; kimlik
   bilgisi git'in kendi yöneticisinden gelir). Kendiliğinden güncelleme yapılmaz; kullanıcıya
   "git pull ile güncelleyin" denir (yerel değişiklikler ve ajan çalışmaları bozulmasın diye).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import httpx

from nxceviri.core.errors import NxError
from nxceviri.core.progress import TaskContext

log = logging.getLogger(__name__)

REPO_OWNER = "ismetuluer"
REPO_NAME = "nxtr"
API_URL = "https://api.github.com"
#: Paketlenmiş (kurulumsuz) sürümde yeni sürüm bu sayfadan indirilir.
RELEASES_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/latest"
#: GitHub'da yalnızca bu depoyu okuyabilen anahtar oluşturma sayfası.
ACCESS_KEY_HELP_URL = "https://github.com/settings/personal-access-tokens/new"

STAGING_DIR = ".guncelleme"
#: Git komutlarının en uzun süresi (saniye); ağ işlemleri bunu aşarsa durdurulur.
GIT_TIMEOUT_S = 180
LAUNCHER = "NX Ceviri Studyosu.bat"
#: Release'e paketle birlikte yüklenen SHA-256 dosyasının ek adı.
CHECKSUM_SUFFIX = ".sha256"
#: Yeni sürümde bulunmayan dosyaların silindiği klasörler (yalnızca kaynak kodu).
PRUNED_DIRS = ("nxceviri", "tests")
#: İndirilecek kaynak arşivinin üst sınırı; depo bunun çok altında (~1 MB).
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
#: İndirilecek taşınabilir paketin (PySide6 ile birlikte) üst sınırı.
MAX_PACKAGE_BYTES = 1024 * 1024 * 1024
#: Sürüm varlıklarının (asset) API adresi öneki; anahtar başka bir adrese gönderilmesin diye denetlenir.
_ASSET_PREFIX = f"{API_URL}/repos/{REPO_OWNER}/{REPO_NAME}/releases/assets/"
#: Anahtarsız istekte bu durumlarda (özel depo veya istek sınırı) kayıtlı anahtarla yinelenir.
_RETRY_WITH_KEY = (401, 403, 404, 429)
#: Changelog notlarının gösterilen en çok uzunluğu.
MAX_NOTES_CHARS = 6000

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
#: Sürüm etiketi: "v0.28.0" (önekli veya öneksiz, başka ek yok).
_TAG_RE = re.compile(r"^v?(\d+\.\d+\.\d+)$")
_CHANGELOG_HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)


class UpdateError(NxError):
    """Güncelleme denetlenemedi, indirilemedi veya uygulanamadı."""


class AccessError(UpdateError):
    """Depoya anahtarsız (ve varsa kayıtlı anahtarla) erişilemedi; arayüz anahtar adımlarını gösterir."""


class ManualInstallError(UpdateError):
    """Otomatik kurulum yapılamıyor; yeni sürüm elle indirilmeli (arayüz sürümler sayfasını önerir)."""


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    version: str  # depodaki sürüm
    sha: str  # depodaki son commit
    notes: str  # kurulu sürümden sonraki sürüm açıklamaları (markdown)
    package_url: str = ""  # taşınabilir paketin (zip) API adresi; release'te yoksa boş
    checksum_url: str = ""  # paketin SHA-256 dosyasının API adresi

    @property
    def newer(self) -> bool:
        return parse_version(self.version) > parse_version(self.current)


@dataclass(frozen=True)
class ApplyResult:
    version: str
    files: int
    removed: int
    dependencies_changed: bool


def parse_version(text: str) -> tuple[int, int, int]:
    m = _VERSION_RE.match(text.strip())
    if m is None:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def dependency_spec(data: bytes) -> object:
    """Kurulumu etkileyen kısım (Python sürümü ve paketler); karşılaştırma satır sonlarından ve sürümden bağımsız.

    Okunamazsa ham içerik döner: karşılaştırma "değişti" der ve paketler yeniden kurulur (güvenli taraf).
    """
    try:
        project = tomllib.loads(data.decode("utf-8"))["project"]
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, KeyError, TypeError):
        return data
    if not isinstance(project, dict):
        return data
    return (
        project.get("requires-python"),
        sorted(project.get("dependencies") or []),
        sorted((k, sorted(v)) for k, v in (project.get("optional-dependencies") or {}).items()),
    )


def version_of_pyproject(data: bytes) -> str:
    try:
        version = tomllib.loads(data.decode("utf-8"))["project"]["version"]
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, KeyError, TypeError):
        raise UpdateError("Depodaki sürüm bilgisi okunamadı.", "Daha sonra yeniden deneyin.") from None
    return str(version)


def changelog_since(changelog: str, current: str) -> str:
    """CHANGELOG'dan kurulu sürümden yeni bölümleri döndürür (en yeni önce, kısaltılmış)."""
    headings = list(_CHANGELOG_HEADING.finditer(changelog))
    parts = []
    for i, m in enumerate(headings):
        if parse_version(m.group(1)) <= parse_version(current):
            break
        end = headings[i + 1].start() if i + 1 < len(headings) else len(changelog)
        parts.append(changelog[m.start() : end].strip())
    notes = "\n\n".join(parts)
    if len(notes) > MAX_NOTES_CHARS:
        notes = notes[:MAX_NOTES_CHARS].rstrip() + "\n…"
    return notes


class Updater(Protocol):
    #: Git yolu mu? (Git deposunda kendiliğinden güncelleme yapılmaz, yalnızca denetlenir.)
    uses_git: bool

    def check(self, current: str) -> UpdateInfo: ...

    def close(self) -> None: ...


def is_git_checkout(root: Path) -> bool:
    return (root / ".git").exists() and shutil.which("git") is not None


def make_updater(root: Path, token: str | None) -> Updater:
    """Kurulum türüne göre güncelleyici: git deposuysa git, değilse GitHub arşivi."""
    if is_git_checkout(root):
        return GitUpdater(root)
    return GitHubUpdater(token)


def tag_version(tag: str) -> str | None:
    """ "v0.28.0" → "0.28.0"; sürüm etiketi değilse None."""
    m = _TAG_RE.match(tag.strip())
    return m.group(1) if m else None


def _no_release() -> UpdateError:
    return UpdateError(
        "Depoda henüz yayımlanmış bir sürüm (release) yok.",
        "Yeni sürüm yayımlandığında burada görünür.",
    )


def is_packaged() -> bool:
    """PyInstaller ile paketlenmiş taşınabilir sürüm mü? (Kendi dosyalarını değiştiremez; sayfadan indirilir.)"""
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path | None:
    """Kaynak koduyla çalışan uygulamanın klasörü; paketlenmiş veya tanınmayan kurulumda None."""
    root = Path(__file__).resolve().parents[2]
    if (root / "pyproject.toml").is_file() and (root / "nxceviri" / "__init__.py").is_file():
        return root
    return None


class GitHubUpdater:
    uses_git = False

    def __init__(
        self,
        token: str | None,
        *,
        owner: str = REPO_OWNER,
        repo: str = REPO_NAME,
        client: httpx.Client | None = None,
    ) -> None:
        self.owner, self.repo = owner, repo
        self._token = token.strip() if token and token.strip() else None
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        #: Anahtarsız istek özel depoda başarısız olunca sonraki isteklerde boşuna denenmez.
        self._anonymous_ok = True

    def __repr__(self) -> str:
        return f"<GitHubUpdater {self.owner}/{self.repo}>"  # anahtar asla görünmez

    def close(self) -> None:
        self._client.close()

    def _headers(self, accept: str, with_token: bool) -> dict[str, str]:
        headers = {"X-GitHub-Api-Version": "2022-11-28", "User-Agent": "NXCeviriStudyosu", "Accept": accept}
        if with_token and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _attempts(self) -> list[bool]:
        """İstek denemeleri: her biri "anahtarla mı?"; önce anahtarsız, gerekirse anahtarla."""
        if self._token is None:
            return [False]
        return [False, True] if self._anonymous_ok else [True]

    def _retry(self, with_token: bool, status: int) -> bool:
        """Anahtarsız istek reddedildiyse ve kayıtlı anahtar varsa anahtarla yinelenir."""
        if with_token or self._token is None or status not in _RETRY_WITH_KEY:
            return False
        self._anonymous_ok = False
        return True

    def _get(self, target: str, accept: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        url = target if target.startswith("https://") else f"{API_URL}{target}"
        for with_token in self._attempts():
            try:
                response = self._client.get(
                    url, params=params, headers=self._headers(accept, with_token), follow_redirects=True
                )
            except httpx.TimeoutException:
                raise UpdateError(
                    "GitHub zamanında yanıt vermedi.", "İnternet bağlantınızı kontrol edip yeniden deneyin."
                ) from None
            except httpx.HTTPError:
                raise UpdateError(
                    "GitHub'a bağlanılamadı.", "İnternet bağlantınızı kontrol edip yeniden deneyin."
                ) from None
            if response.status_code < 400:
                return response
            if not self._retry(with_token, response.status_code):
                raise self._http_error(response, with_token)
        raise AssertionError("en az bir deneme yapılır")  # pragma: no cover

    def _http_error(self, response: httpx.Response, with_token: bool) -> UpdateError:
        code = response.status_code
        if code == 429 or (code == 403 and response.headers.get("x-ratelimit-remaining") == "0"):
            return UpdateError(
                "GitHub istek sınırı doldu.", _rate_limit_hint(response.headers.get("x-ratelimit-reset"))
            )
        if code == 401 and with_token:
            return AccessError(
                "GitHub erişim anahtarı geçersiz veya süresi dolmuş.",
                "Yeni bir anahtar girin ya da depo herkese açıldıysa kayıtlı anahtarı silin.",
            )
        if code in (401, 403, 404):
            hint = (
                "Anahtarın bu depoyu okuma izni (Contents: Read-only) olduğundan emin olun."
                if with_token
                else "Depo özel olduğu için GitHub erişim anahtarı gerekir; pencereden anahtar girin."
            )
            return AccessError(f"Depoya erişilemedi: {self.owner}/{self.repo}", hint)
        return UpdateError(f"GitHub hata döndürdü (HTTP {code}).", "Daha sonra yeniden deneyin.")

    def check(self, current: str) -> UpdateInfo:
        data = self._get(
            f"/repos/{self.owner}/{self.repo}/releases", "application/vnd.github+json", params={"per_page": "30"}
        ).json()
        releases = sorted(
            (
                (version, r)
                for r in (data if isinstance(data, list) else [])
                if isinstance(r, dict) and not r.get("draft") and not r.get("prerelease")
                for version in [tag_version(str(r.get("tag_name", "")))]
                if version is not None
            ),
            key=lambda vr: parse_version(vr[0]),
            reverse=True,
        )
        if not releases:
            raise _no_release()
        version, latest = releases[0]
        sha = self._get(
            f"/repos/{self.owner}/{self.repo}/commits/{latest['tag_name']}", "application/vnd.github.sha"
        ).text.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise UpdateError("GitHub beklenmeyen bir yanıt döndürdü.", "Daha sonra yeniden deneyin.")
        newer = [r for v, r in releases if parse_version(v) > parse_version(current)]
        notes = "\n\n".join(str(r.get("body") or "").strip() or str(r.get("name") or r["tag_name"]) for r in newer)
        if len(notes) > MAX_NOTES_CHARS:
            notes = notes[:MAX_NOTES_CHARS].rstrip() + "\n…"
        package = package_asset_name(version)
        return UpdateInfo(
            current,
            version,
            sha,
            notes.strip(),
            package_url=_asset_url(latest, package),
            checksum_url=_asset_url(latest, package + CHECKSUM_SUFFIX),
        )

    def prepare(self, info: UpdateInfo, root: Path, ctx: TaskContext) -> None:
        """Kaynak kurulum: yeni sürümü bir sonraki açılışta uygulanmak üzere hazırlar."""
        archive = self.download(info, root / STAGING_DIR, ctx)
        try:
            stage(archive, root, info.version)
        finally:
            archive.unlink(missing_ok=True)

    def download(self, info: UpdateInfo, folder: Path, ctx: TaskContext) -> Path:
        """Commit'in zip arşivini `folder`'a indirir (ilerleme ve iptal destekli)."""
        target = folder / f"nxceviri-{info.version}.zip"
        url = f"{API_URL}/repos/{self.owner}/{self.repo}/zipball/{info.sha}"
        self.download_file(url, target, MAX_ARCHIVE_BYTES, ctx)
        return target

    def fetch_text(self, url: str) -> str:
        """Küçük bir sürüm varlığının (ör. SHA-256 dosyası) metnini okur."""
        return self._get(url, "application/octet-stream").text

    def download_file(self, url: str, target: Path, limit: int, ctx: TaskContext) -> None:
        """`url`'yi `target`'a indirir (ilerleme ve iptal destekli); yarım dosya kalmaz."""
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".indiriliyor")
        try:
            self._stream_to(url, part, limit, ctx)
            os.replace(part, target)
        except httpx.TimeoutException:
            raise UpdateError(
                "GitHub zamanında yanıt vermedi.", "İnternet bağlantınızı kontrol edip yeniden deneyin."
            ) from None
        except httpx.HTTPError:
            raise UpdateError(
                "Güncelleme indirilemedi.", "İnternet bağlantınızı kontrol edip yeniden deneyin."
            ) from None
        except OSError as exc:
            raise UpdateError("Güncelleme diske yazılamadı.", f"Diskte yer olduğundan emin olun. ({exc})") from None
        finally:
            part.unlink(missing_ok=True)

    def _stream_to(self, url: str, part: Path, limit: int, ctx: TaskContext) -> None:
        for with_token in self._attempts():
            headers = self._headers("application/octet-stream", with_token)
            with self._client.stream("GET", url, headers=headers, follow_redirects=True) as response:
                if response.status_code >= 400:
                    response.read()
                    if self._retry(with_token, response.status_code):
                        continue
                    raise self._http_error(response, with_token)
                total = int(response.headers.get("content-length") or 0)
                done = 0
                with part.open("wb") as fh:
                    for chunk in response.iter_bytes(64 * 1024):
                        ctx.check()
                        done += len(chunk)
                        if done > limit:
                            raise UpdateError("İndirilen dosya beklenenden çok büyük; güncelleme durduruldu.")
                        fh.write(chunk)
                        ctx.report(done, total, f"İndiriliyor: {done / 1048576:.1f} MB".replace(".", ","))
                return


def _rate_limit_hint(reset: str | None) -> str:
    try:
        minutes = max(1, -(-(int(reset or "") - int(time.time())) // 60))
    except ValueError:
        return "Bir saat kadar sonra yeniden deneyin."
    return f"Yaklaşık {minutes} dakika sonra yeniden deneyin."


def _asset_url(release: dict[str, Any], name: str) -> str:
    """Release'teki `name` adlı varlığın API adresi; yoksa veya adres beklenen yerde değilse boş."""
    for asset in release.get("assets") or []:
        if isinstance(asset, dict) and asset.get("name") == name:
            url = str(asset.get("url") or "")
            return url if url.startswith(_ASSET_PREFIX) else ""
    return ""


def package_asset_name(version: str) -> str:
    """Release iş akışının yüklediği taşınabilir paketin dosya adı."""
    return f"NXTR-{version}-windows.zip"


class GitUpdater:
    """Git deposu olan kurulumda güncelleme (`git fetch` + `git merge --ff-only`)."""

    uses_git = True

    def __init__(self, root: Path, *, remote: str = "origin") -> None:
        self.root = root
        self.remote = remote

    def close(self) -> None:
        """Açık kaynak tutmaz; sözleşme gereği vardır."""

    def check(self, current: str) -> UpdateInfo:
        run_git(self.root, "fetch", "--quiet", "--tags", self.remote)
        tags = [(v, t) for t in run_git(self.root, "tag", "--list", "v*").split() if (v := tag_version(t))]
        if not tags:
            raise _no_release()
        version, tag = max(tags, key=lambda vt: parse_version(vt[0]))
        sha = run_git(self.root, "rev-list", "-n", "1", tag).strip()
        if version_of_pyproject(run_git(self.root, "show", f"{sha}:pyproject.toml").encode("utf-8")) != version:
            raise UpdateError(f"{tag} etiketindeki sürüm bilgisi etiketle uyuşmuyor; güncelleme yapılmadı.")
        notes = ""
        if parse_version(version) > parse_version(current):
            try:
                notes = changelog_since(run_git(self.root, "show", f"{sha}:CHANGELOG.md"), current)
            except UpdateError as exc:
                log.info("Değişiklik günlüğü okunamadı: %s", exc.message)
        return UpdateInfo(current, version, sha, notes)


def run_git(root: Path, *args: str, timeout: float = GIT_TIMEOUT_S) -> str:
    """Uygulama klasöründe git çalıştırır; hata olursa anlaşılır `UpdateError` fırlatır."""
    try:
        done = subprocess.run(  # noqa: S603 - sabit "git" komutu, kabuk kullanılmaz
            ["git", *args],  # noqa: S607 - git PATH'ten bulunur (is_git_checkout denetler)
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise UpdateError(
            "Git zamanında yanıt vermedi.", "İnternet bağlantınızı kontrol edip yeniden deneyin."
        ) from None
    except OSError as exc:
        raise UpdateError("Git çalıştırılamadı.", f"Git kurulu olmayabilir. ({exc})") from None
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise UpdateError(
            f"Git komutu başarısız oldu: git {args[0]}",
            (detail[-1] if detail else "")
            + "\nGitHub'a erişilemiyorsa Git'in kayıtlı oturumunu (Git Credential Manager) kontrol edin.",
        )
    return done.stdout


# --- hazırlama ve uygulama ------------------------------------------------------------------


def staging_dir(root: Path) -> Path:
    return root / STAGING_DIR / "hazir"


def pending_version(root: Path) -> str | None:
    """Hazırlanmış (henüz uygulanmamış) güncellemenin sürümü."""
    pyproject = staging_dir(root) / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        return version_of_pyproject(pyproject.read_bytes())
    except (UpdateError, OSError):
        return None


def extract_archive(archive: Path, work: Path) -> Path:
    """Zip'i `work` klasörüne açar (klasör dışına yol çıkışı reddedilir); tek üst klasörün yolunu döndürür."""
    try:
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            tops = {PurePosixPath(m.filename).parts[0] for m in members if m.filename.strip("/")}
            if len(tops) != 1:
                raise UpdateError("İndirilen arşivin yapısı beklenmedik; güncelleme yapılmadı.")
            for m in members:
                rel = PurePosixPath(m.filename)
                if rel.is_absolute() or ".." in rel.parts:
                    raise UpdateError("İndirilen arşivde güvensiz bir dosya yolu var; güncelleme yapılmadı.")
                dest = work.joinpath(*rel.parts)
                if m.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(m) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
    except zipfile.BadZipFile:
        raise UpdateError("İndirilen arşiv bozuk; güncelleme yapılmadı.", "Yeniden deneyin.") from None
    return work / tops.pop()


def stage(archive: Path, root: Path, expected_version: str) -> Path:
    """Arşivi `.guncelleme/hazir/` klasörüne açar ve doğrular."""
    base = root / STAGING_DIR
    work = base / "aciliyor"
    shutil.rmtree(work, ignore_errors=True)
    try:
        work.mkdir(parents=True)
        content = extract_archive(archive, work)
        pyproject = content / "pyproject.toml"
        if not pyproject.is_file() or not (content / "nxceviri" / "__init__.py").is_file():
            raise UpdateError("İndirilen arşiv eksik; güncelleme yapılmadı.", "Daha sonra yeniden deneyin.")
        version = version_of_pyproject(pyproject.read_bytes())
        if version != expected_version:
            raise UpdateError(
                f"İndirilen sürüm ({version}) beklenen sürüm ({expected_version}) değil.",
                "Depo bu arada değişmiş olabilir; yeniden denetleyin.",
            )
        target = staging_dir(root)
        shutil.rmtree(target, ignore_errors=True)
        os.replace(content, target)
    except OSError as exc:
        raise UpdateError("Güncelleme hazırlanamadı.", f"Uygulama klasörüne yazılamıyor olabilir. ({exc})") from None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return target


def _is_cache(rel: Path) -> bool:
    return "__pycache__" in rel.parts or rel.suffix in (".pyc", ".pyo")


def apply_staged(root: Path, *, attempts: int = 5, wait_s: float = 1.0) -> ApplyResult | None:
    """Hazırlanmış arşivi uygulama klasörüne yazar. Hazırlanmış arşiv yoksa None.

    Önceki uygulama penceresi kapanırken dosyalar kısa süre kilitli kalabilir; yazım başarısız
    olursa her şey geri alınır ve birkaç kez yeniden denenir.
    """
    staged = staging_dir(root)
    if not (staged / "pyproject.toml").is_file():
        return None
    version = version_of_pyproject((staged / "pyproject.toml").read_bytes())
    new_files = sorted(p.relative_to(staged) for p in staged.rglob("*") if p.is_file())
    new_set = set(new_files)
    stale = sorted(
        p.relative_to(root)
        for folder in PRUNED_DIRS
        if (root / folder).is_dir()
        for p in (root / folder).rglob("*")
        if p.is_file() and p.relative_to(root) not in new_set and not _is_cache(p.relative_to(root))
    )
    old_pyproject = (root / "pyproject.toml").read_bytes() if (root / "pyproject.toml").is_file() else b""
    new_pyproject = (staged / "pyproject.toml").read_bytes()
    backup = root / STAGING_DIR / "yedek"
    for attempt in range(1, attempts + 1):
        try:
            _replace_files(root, staged, backup, new_files, stale)
            break
        except OSError as exc:
            log.warning("Güncelleme uygulanamadı (%d. deneme): %s", attempt, exc)
            if attempt == attempts:
                raise UpdateError(
                    f"{version} sürümü uygulanamadı; uygulama eski sürümle açılıyor.",
                    "Uygulama klasöründeki bir dosya kullanımda olabilir. Uygulamayı kapatıp yeniden açın; "
                    "güncelleme bir sonraki açılışta yeniden denenir.",
                ) from None
            time.sleep(wait_s)
    shutil.rmtree(staged, ignore_errors=True)
    log.info("Güncelleme uygulandı: %s (%d dosya, %d eski dosya silindi)", version, len(new_files), len(stale))
    changed_deps = dependency_spec(old_pyproject) != dependency_spec(new_pyproject)
    return ApplyResult(version, len(new_files), len(stale), changed_deps)


def _replace_files(root: Path, staged: Path, backup: Path, new_files: list[Path], stale: list[Path]) -> None:
    """Dosyaları yazar; herhangi bir hata olursa yedekten geri alıp hatayı yeniden fırlatır."""
    shutil.rmtree(backup, ignore_errors=True)
    backup.mkdir(parents=True)
    saved: list[Path] = []
    created: list[Path] = []
    try:
        for rel in [*new_files, *stale]:
            if (root / rel).is_file():
                (backup / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / rel, backup / rel)
                saved.append(rel)
        for rel in new_files:
            dest = root / rel
            if not dest.exists():
                created.append(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged / rel, dest)
        for rel in stale:
            (root / rel).unlink()
    except OSError:
        for rel in created:
            (root / rel).unlink(missing_ok=True)
        for rel in saved:
            shutil.copy2(backup / rel, root / rel)
        raise


def relaunch(root: Path, popen: Callable[..., Any] = subprocess.Popen) -> None:
    """Uygulamayı yeniden başlatır: Windows'ta başlatıcıyla (gerekirse paketleri kurar)."""
    launcher = root / LAUNCHER
    if os.name == "nt" and launcher.is_file():
        popen(
            ["cmd.exe", "/c", str(launcher)],
            cwd=str(root),
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
    else:
        popen([sys.executable, "-m", "nxceviri"], cwd=str(root))
