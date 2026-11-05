"""Kullanıcı eklentileri: keşif, doğrulama, öncelik, tarama/çıkarma akışı, kurma, proje kaydı, iskelet ve komutlar."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from nxceviri import __version__
from nxceviri.arac import main as tool_main
from nxceviri.core.errors import NxError
from nxceviri.core.export.layeredfs import LAYOUT_ATMOSPHERE, TextFileRef, game_file_patches, support_files
from nxceviri.core.formats import registry
from nxceviri.core.formats.base import FormatError
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import Inputs, extract_texts, importable_entries, scan_sources
from nxceviri.core.plugins import EKLENTI_API, load_plugins, user_plugin_dirs
from nxceviri.core.plugins.install import PluginExistsError, PluginInstallError, install_plugin
from nxceviri.core.plugins.record import SETTING_KEY, plugin_warnings, record_extraction
from nxceviri.core.plugins.scaffold import create_plugin, validate_name
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import Project
from tests.conftest import BASE_TID, GameFiles

PLUGIN_BODY = """
from nxceviri.core.formats.base import TextEntry
from nxceviri.core.plugins import FormatPluginBase


class Demo(FormatPluginBase):
    name = "{kind}"
    label = "Demo biçimi"
    candidates_only = False

    def detect(self, path, head):
        return path.endswith("level1.bin")

    def extract(self, data, context=None):
        return [TextEntry(key="k0", index=0, source="Merhaba", codes=())]

    def inject(self, data, translations):
        return data


PLUGIN = Demo()
"""


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    registry.reset_user_plugins()
    yield
    registry.reset_user_plugins()


def make_plugin(
    root: Path,
    folder: str,
    *,
    ad: str = "demo",
    kind: str = "demo_kind",
    surum: str = "1.0.0",
    api: int = EKLENTI_API,
    oyunlar: tuple[str, ...] = (),
    body: str | None = None,
    toml: str | None = None,
) -> Path:
    path = root / folder
    path.mkdir(parents=True)
    games = ", ".join(f'"{g}"' for g in oyunlar)
    manifest = toml or f'ad = "{ad}"\nsurum = "{surum}"\nyazar = "Deneme"\napi = {api}\noyunlar = [{games}]\n'
    (path / "eklenti.toml").write_text(manifest, encoding="utf-8")
    (path / "plugin.py").write_text(body if body is not None else PLUGIN_BODY.format(kind=kind), encoding="utf-8")
    return path


def test_valid_plugin_loads(tmp_path: Path) -> None:
    make_plugin(tmp_path, "demo", oyunlar=("0100abcd12340000",))
    report = load_plugins([tmp_path], set())
    (info,) = report.infos
    assert info.yuklu
    assert not info.hata
    assert (info.ad, info.surum, info.yazar, info.api, info.tur) == ("demo", "1.0.0", "Deneme", 1, "demo_kind")
    assert info.oyunlar == ("0100ABCD12340000",)
    assert info.yol == tmp_path / "demo"
    assert [p.name for p in report.plugins] == ["demo_kind"]


def test_broken_plugins_do_not_stop_the_others(tmp_path: Path) -> None:
    make_plugin(tmp_path, "a_iyi", ad="iyi", kind="iyi_kind")
    make_plugin(tmp_path, "b_bozuk_toml", toml="ad = [\n")
    (tmp_path / "c_toml_yok").mkdir()
    make_plugin(tmp_path, "d_alan_eksik", toml='ad = "x"\nsurum = "1"\napi = 1\n')
    make_plugin(tmp_path, "e_ice_aktarma", body="import olmayan_modul_xyz\n")
    make_plugin(tmp_path, "f_plugin_yok", body="X = 1\n")
    make_plugin(tmp_path, "g_sozlesme", body="class A:\n    name = 'a'\nPLUGIN = A()\n")
    make_plugin(tmp_path, "h_oyunlar", toml='ad = "h"\nsurum = "1"\nyazar = "y"\napi = 1\noyunlar = ["kisa"]\n')
    report = load_plugins([tmp_path], set())
    by_folder = {i.yol.name: i for i in report.infos if i.yol}
    assert by_folder["a_iyi"].yuklu
    assert "bozuk" in by_folder["b_bozuk_toml"].hata
    assert "eklenti.toml bulunamadı" in by_folder["c_toml_yok"].hata
    assert "“yazar”" in by_folder["d_alan_eksik"].hata
    assert "olmayan_modul_xyz" in by_folder["e_ice_aktarma"].hata
    assert "PLUGIN nesnesi yok" in by_folder["f_plugin_yok"].hata
    assert "sözleşmesini karşılamıyor" in by_folder["g_sozlesme"].hata
    assert "TitleID" in by_folder["h_oyunlar"].hata
    assert len(report.errors) == 7
    assert len(report.plugins) == 1


@pytest.mark.parametrize(("api", "text"), [(2, "Uygulamayı güncelleyin"), (0, "güncel sürümünü isteyin")])
def test_incompatible_api_is_skipped_with_advice(tmp_path: Path, api: int, text: str) -> None:
    make_plugin(tmp_path, "x", api=api)
    (info,) = load_plugins([tmp_path], set()).infos
    assert not info.yuklu
    assert text in info.hata
    assert info.plugin is None


def test_same_kind_twice_reports_conflict(tmp_path: Path) -> None:
    make_plugin(tmp_path, "a", ad="birinci", kind="ayni")
    make_plugin(tmp_path, "b", ad="ikinci", kind="ayni")
    first, second = load_plugins([tmp_path], set()).infos
    assert first.yuklu
    assert "çakışıyor" in second.hata
    assert "birinci" in second.hata


def test_user_plugin_wins_over_builtin_and_says_so(tmp_path: Path) -> None:
    make_plugin(tmp_path / "ek", "msbt_benim", ad="msbt_benim", kind="msbt")
    report = registry.load_user_plugins([tmp_path / "ek"])
    (info,) = report.infos
    assert info.yuklu
    assert "yerleşik" in info.uyari.lower()
    assert registry.plugin_for_kind("msbt") is info.plugin
    assert registry.all_plugins()[0] is info.plugin
    assert len(registry.all_plugins()) == len(registry.BUILTIN_PLUGINS) + 1


def test_registry_before_loading_is_only_builtin() -> None:
    assert registry.all_plugins() == registry.BUILTIN_PLUGINS
    assert registry.plugin_for_kind("demo_kind") is None


def test_unexpected_plugin_error_becomes_format_error(tmp_path: Path) -> None:
    body = PLUGIN_BODY.format(kind="kotu").replace("return data", "raise ZeroDivisionError('bölme')")
    make_plugin(tmp_path, "kotu", ad="kotu", kind="kotu", body=body)
    (info,) = load_plugins([tmp_path], set()).infos
    assert info.plugin is not None
    with pytest.raises(FormatError, match=r"“kotu” eklentisi hata verdi.*ZeroDivisionError"):
        info.plugin.inject(b"", {})


def test_user_plugin_dirs_use_localappdata_and_repo_only_from_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    dirs = user_plugin_dirs()
    assert dirs[0] == tmp_path / "NXCeviri" / "eklentiler"
    assert dirs[1].name == "eklentiler"
    assert (dirs[1].parent / "pyproject.toml").is_file()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert user_plugin_dirs() == [tmp_path / "NXCeviri" / "eklentiler"]


def test_user_plugin_is_used_in_scan_and_extract(game: GameFiles, tmp_path: Path) -> None:
    make_plugin(tmp_path / "ek", "demo", oyunlar=(f"{BASE_TID:016X}",))
    registry.load_user_plugins([tmp_path / "ek"])
    keys = load_keys(game.keys_path)
    inputs = Inputs((game.base_nsp,), keys, cache_dir=tmp_path / "onbellek")
    report = scan_sources(inputs, TaskContext())
    claimed = [e for e in report.entries if e.kind == "demo_kind"]
    assert [e.path for e in claimed] == ["Data/level1.bin"]
    assert claimed[0].detail == "Demo biçimi"
    assert claimed[0].is_text_candidate
    assert claimed[0] in importable_entries(report)
    result = extract_texts(inputs, report, TaskContext())
    demo_files = [f for f in result.files if f.format == "demo_kind"]
    assert [e.source for f in demo_files for e in f.entries] == ["Merhaba"]


def test_user_plugin_ignores_other_games(game: GameFiles, tmp_path: Path) -> None:
    make_plugin(tmp_path / "ek", "demo", oyunlar=("0100000000000001",))
    registry.load_user_plugins([tmp_path / "ek"])
    report = scan_sources(Inputs((game.base_nsp,), load_keys(game.keys_path), cache_dir=tmp_path / "o"), TaskContext())
    assert not [e for e in report.entries if e.kind == "demo_kind"]
    assert report.counts["other"] >= 1


def test_kind_label_covers_builtin_user_and_unknown(tmp_path: Path) -> None:
    make_plugin(tmp_path / "ek", "demo")
    registry.load_user_plugins([tmp_path / "ek"])
    assert registry.kind_label("msbt") == "MSBT"
    assert registry.kind_label("demo_kind") == "Demo biçimi"
    assert registry.kind_label("bilinmeyen") == "bilinmeyen"


# --- kurma ---------------------------------------------------------------------------------


def _zip(path: Path, files: dict[str, bytes | str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return path


def _plugin_files(prefix: str = "") -> dict[str, bytes | str]:
    return {
        f"{prefix}eklenti.toml": 'ad = "zip eklentisi"\nsurum = "2.0"\nyazar = "Ben"\napi = 1\n',
        f"{prefix}plugin.py": PLUGIN_BODY.format(kind="zipli"),
        f"{prefix}tests/test_x.py": "",
    }


@pytest.mark.parametrize("prefix", ["", "paketim/"])
def test_install_zip_with_or_without_top_folder(tmp_path: Path, prefix: str) -> None:
    archive = _zip(tmp_path / "e.zip", _plugin_files(prefix))
    target = install_plugin(archive, tmp_path / "hedef")
    assert target == tmp_path / "hedef" / "zip_eklentisi"
    assert (target / "plugin.py").is_file()
    assert (target / "tests" / "test_x.py").is_file()
    assert [i.yuklu for i in load_plugins([tmp_path / "hedef"], set()).infos] == [True]
    assert not [p for p in (tmp_path / "hedef").iterdir() if p.name.startswith(".")]  # geçici klasör kalmaz


@pytest.mark.parametrize(
    "bad", ["../kacak.py", "/mutlak.py", "C:/mutlak.py", "..\\kacak.py", "a/../../kacak.py", "\\\\sunucu\\x.py"]
)
def test_install_zip_rejects_path_traversal(tmp_path: Path, bad: str) -> None:
    archive = _zip(tmp_path / "e.zip", {**_plugin_files(), bad: "x"})
    with pytest.raises(PluginInstallError, match="güvensiz bir yol"):
        install_plugin(archive, tmp_path / "hedef")
    assert not (tmp_path / "kacak.py").exists()
    assert list((tmp_path / "hedef").iterdir()) == []  # hiçbir şey kurulmadı, geçici klasör de silindi


def test_install_rejects_symlink_zip_bad_zip_missing_manifest_and_wrong_type(tmp_path: Path) -> None:
    link = tmp_path / "l.zip"
    with zipfile.ZipFile(link, "w") as zf:
        info = zipfile.ZipInfo("baglanti")
        info.external_attr = 0o120777 << 16
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(PluginInstallError, match="simge bağı"):
        install_plugin(link, tmp_path / "h")
    (tmp_path / "bozuk.zip").write_bytes(b"zip degil")
    with pytest.raises(PluginInstallError, match="açılamadı"):
        install_plugin(tmp_path / "bozuk.zip", tmp_path / "h")
    with pytest.raises(PluginInstallError, match=r"eklenti.toml bulunamadı"):
        install_plugin(_zip(tmp_path / "bos.zip", {"a.txt": "x"}), tmp_path / "h")
    (tmp_path / "x.txt").write_text("x")
    with pytest.raises(PluginInstallError, match=r"Yalnızca .zip"):
        install_plugin(tmp_path / "x.txt", tmp_path / "h")
    with pytest.raises(PluginInstallError, match="bulunamadı"):
        install_plugin(tmp_path / "yok.zip", tmp_path / "h")


def test_install_folder_and_replace(tmp_path: Path) -> None:
    source = make_plugin(tmp_path / "kaynak", "benim", ad="benim", kind="benim")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "x.pyc").write_bytes(b"x")
    target = install_plugin(source, tmp_path / "hedef")
    assert (target / "plugin.py").is_file()
    assert not (target / "__pycache__").exists()
    with pytest.raises(PluginExistsError):
        install_plugin(source, tmp_path / "hedef")
    (source / "eklenti.toml").write_text('ad = "benim"\nsurum = "9.9"\nyazar = "y"\napi = 1\n', encoding="utf-8")
    install_plugin(source, tmp_path / "hedef", replace=True)
    assert load_plugins([tmp_path / "hedef"], set()).infos[0].surum == "9.9"


def test_install_rejects_invalid_manifest(tmp_path: Path) -> None:
    archive = _zip(tmp_path / "e.zip", {"eklenti.toml": 'ad = "x"\n', "plugin.py": ""})
    with pytest.raises(NxError, match="surum"):
        install_plugin(archive, tmp_path / "hedef")


# --- proje kaydı --------------------------------------------------------------------------


def test_project_record_and_warnings(tmp_path: Path) -> None:
    make_plugin(tmp_path / "ek", "demo", surum="1.0.0")
    registry.load_user_plugins([tmp_path / "ek"])
    project = Project.new()
    record_extraction(project, ["msbt", "demo_kind", "msbt"])
    saved = json.loads(project.setting(SETTING_KEY))
    assert saved["msbt"] == {"ad": "msbt", "surum": __version__, "yerlesik": True}
    assert saved["demo_kind"] == {"ad": "demo", "surum": "1.0.0", "yerlesik": False}
    assert plugin_warnings(project) == []  # aynı eklenti, aynı sürüm; yerleşik için uyarı yok

    registry.reset_user_plugins()
    (missing,) = plugin_warnings(project)
    assert "“demo”" in missing
    assert "yüklü değil" in missing

    make_plugin(tmp_path / "ek2", "demo", surum="2.0.0")
    registry.load_user_plugins([tmp_path / "ek2"])
    (differs,) = plugin_warnings(project)
    assert "1.0.0" in differs
    assert "2.0.0" in differs
    assert "yeniden aktarmanız" in differs
    project.close()


def test_plugin_warnings_ignore_missing_or_corrupt_record() -> None:
    project = Project.new()
    assert plugin_warnings(project) == []
    project.set_setting(SETTING_KEY, "{bozuk")
    assert plugin_warnings(project) == []
    project.close()


# --- iskelet ve komutlar ------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "A", "ab", "Büyük", "1sayi", "bosluk var", "msbt", "unity", "x" * 40])
def test_scaffold_rejects_bad_names(bad: str) -> None:
    with pytest.raises(PluginInstallError):
        validate_name(bad)


def test_scaffold_output_loads_and_its_own_tests_pass(tmp_path: Path) -> None:
    folder = create_plugin("ornek_oyun", tmp_path)
    assert {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} == {
        "eklenti.toml",
        "plugin.py",
        "NOT.md",
        "tests/test_ornek_oyun.py",
    }
    (info,) = load_plugins([tmp_path], set()).infos
    assert info.yuklu
    assert info.tur == "ornek_oyun"
    assert info.api == EKLENTI_API
    with pytest.raises(PluginInstallError, match="zaten var"):
        create_plugin("ornek_oyun", tmp_path)
    repo = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(repo)}
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(folder / "tests")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "4 passed" in done.stdout


def test_create_command_and_list_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert tool_main(["eklenti-olustur", "komut_deneme", "--hedef", str(tmp_path)]) == 0
    assert "iskeleti oluşturuldu" in capsys.readouterr().out
    assert (tmp_path / "komut_deneme" / "plugin.py").is_file()
    assert tool_main(["eklenti-olustur", "Kotu Ad", "--hedef", str(tmp_path)]) == 1
    assert "geçerli bir eklenti adı değil" in capsys.readouterr().out

    local = Path(os.environ["LOCALAPPDATA"]) / "NXCeviri" / "eklentiler"
    make_plugin(local, "iyi", ad="iyi", kind="iyi_kind")
    make_plugin(local, "kotu", toml="ad = [\n")
    assert tool_main(["eklentiler"]) == 1  # hata varsa çıkış kodu 1
    out = capsys.readouterr().out
    assert "[TAMAM] iyi 1.0.0" in out
    assert "[HATA] kotu" in out
    registry.reset_user_plugins()


# --- `oyunlar` sınırı: kullanıcı eklentisi yerleşik biçimi yalnızca kendi oyunlarında ezer -----------


def test_plugin_for_kind_respects_game_restriction(tmp_path: Path) -> None:
    game_a, game_b = "0100000000000001", "0100000000000002"
    make_plugin(tmp_path / "ek", "msbt_user", kind="msbt", oyunlar=(game_a,))
    registry.load_user_plugins([tmp_path / "ek"])
    assert registry.plugin_for_kind("msbt", game_a.lower()) is not None
    assert registry.plugin_for_kind("msbt", game_a).label == "Demo biçimi"  # type: ignore[union-attr]
    assert registry.plugin_for_kind("msbt", game_b) is registry.BUILTIN_PLUGINS[0]  # yerleşik MSBT
    assert registry.plugin_for_kind("msbt") is not registry.BUILTIN_PLUGINS[0]  # TitleID'siz arama sınırsız


HOOKS_BODY = PLUGIN_BODY.replace(
    "PLUGIN = Demo()",
    """    def game_file_patches(self):
        return {"Data/a.bin": lambda data: data + b"!"}

    def support_files(self):
        return {"ek.txt": b"x"}


PLUGIN = Demo()""",
)


def test_export_hooks_of_user_plugin_apply_only_to_its_games(tmp_path: Path) -> None:
    game_a, game_b = "0100000000000001", "0100000000000002"
    make_plugin(tmp_path / "ek", "msbt_user", kind="msbt", oyunlar=(game_a,), body=HOOKS_BODY.replace("{kind}", "msbt"))
    registry.load_user_plugins([tmp_path / "ek"])
    files = [TextFileRef("Data/x.msbt", game_a, "msbt"), TextFileRef("Data/y.msbt", game_b, "msbt")]
    assert list(game_file_patches(files)) == [(game_a, "Data/a.bin")]
    assert [p.name for p, _ in support_files(files, LAYOUT_ATMOSPHERE, "mod")] == ["ek.txt"]


# --- isteğe bağlı kancalardaki hatalar FormatError olur --------------------------------------

BROKEN_HOOKS_BODY = PLUGIN_BODY.replace(
    "PLUGIN = Demo()",
    """    def derived_files(self, read, files, game_dir):
        raise RuntimeError("derived patladi")

    def game_file_patches(self):
        def patch(data):
            raise RuntimeError("donusturucu patladi")

        return {"Data/a.bin": patch}

    def exefs_patches(self, code):
        raise RuntimeError("exefs patladi")

    def normalize_text(self, text):
        raise RuntimeError("normalize patladi")

    def support_files(self):
        raise RuntimeError("destek patladi")

    unsupported_letters = "ğş"


PLUGIN = Demo()""",
).replace("{kind}", "demo_kind")


def test_optional_hook_errors_become_format_errors_with_plugin_name(tmp_path: Path) -> None:
    make_plugin(tmp_path / "ek", "kanca", ad="bozuk kanca", body=BROKEN_HOOKS_BODY)
    registry.load_user_plugins([tmp_path / "ek"])
    plugin = registry.plugin_for_kind("demo_kind")
    assert plugin is not None
    assert plugin.unsupported_letters == "ğş"  # type: ignore[attr-defined]  # çağrılabilir olmayan nitelik olduğu gibi geçer
    calls: dict[str, tuple[object, ...]] = {
        "derived_files": (lambda _p: None, {}, None),
        "exefs_patches": (b"",),
        "normalize_text": ("x",),
        "support_files": (),
    }
    for hook, args in calls.items():
        with pytest.raises(FormatError, match="bozuk kanca") as exc:
            getattr(plugin, hook)(*args)
        assert "patladi" in str(exc.value.message)
    patch = plugin.game_file_patches()["Data/a.bin"]  # type: ignore[attr-defined]
    with pytest.raises(FormatError, match="bozuk kanca"):
        patch(b"")


def test_same_plugin_in_two_folders_shadows_second_without_error(tmp_path: Path) -> None:
    make_plugin(tmp_path / "kullanici", "demo", ad="ayni eklenti", kind="ayni")
    make_plugin(tmp_path / "depo", "demo", ad="ayni eklenti", kind="ayni")
    report = load_plugins([tmp_path / "kullanici", tmp_path / "depo"], set())
    first, second = report.infos
    assert first.yuklu
    assert second.yuklu
    assert second.golge
    assert second.plugin is None
    assert "gölgelendi" in second.uyari
    assert not report.errors
    assert len(report.plugins) == 1
    assert first.yol is not None
    assert first.yol.parent.name == "kullanici"


def _plugin_folder(root: Path) -> Path:
    return make_plugin(root, "kaynak", ad="baglantili", kind="baglantili")


def test_install_folder_rejects_symlink(tmp_path: Path) -> None:
    folder = _plugin_folder(tmp_path)
    secret = tmp_path / "prod.keys"
    secret.write_text("gizli", encoding="utf-8")
    try:
        (folder / "anahtar.txt").symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("Bu ortamda simge bağı oluşturma yetkisi yok")
    with pytest.raises(PluginInstallError, match="simge bağı"):
        install_plugin(folder, tmp_path / "hedef")
    assert not any((tmp_path / "hedef").iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Bağlantı noktası (junction) yalnızca Windows'ta vardır")
def test_install_folder_rejects_junction(tmp_path: Path) -> None:
    folder = _plugin_folder(tmp_path)
    outside = tmp_path / "dis"
    outside.mkdir()
    (outside / "prod.keys").write_text("gizli", encoding="utf-8")
    made = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(folder / "bag"), str(outside)], capture_output=True, check=False
    )
    if made.returncode != 0:
        pytest.skip("Bağlantı noktası oluşturulamadı")
    with pytest.raises(PluginInstallError, match="simge bağı ya da bağlantı"):
        install_plugin(folder, tmp_path / "hedef")
    assert not any((tmp_path / "hedef").iterdir())
