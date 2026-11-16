"""`.fsd`/`.msg` ek çeviri verisi: kullanıcının grafik klasöründeki resim yazıları ve düşman açıklamaları.

Veri uygulamayla gelmez; buradaki her örnek elle uydurulmuştur (gerçek oyun verisi değil).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from importlib import resources
from pathlib import Path
from typing import Any

import pytest

from nxceviri.core.export.layeredfs import (
    INFO_FILE,
    LAYOUT_ATMOSPHERE,
    ExportInfo,
    ExportOptions,
    TextFileRef,
    export_mod,
)
from nxceviri.core.fontpatch import fsdmsg_graphics, fsdmsg_userdata
from nxceviri.core.fontpatch.fsdmsg_images import iter_pages, page_key
from nxceviri.core.fontpatch.fsdmsg_userdata import DESCRIPTIONS, IMAGE_TEXTS, UserDataError
from nxceviri.core.fontpatch.labels import Label
from nxceviri.core.formats import legacy
from nxceviri.core.formats.fsdmsg import FsdMsgPlugin, exe
from nxceviri.core.formats.fsdmsg.plugin import MENU_FILES
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import Inputs, extract_texts, scan_sources
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import Project
from tests import nxbuild
from tests.fsdmsgbuild import fsd, message, table
from tests.psbbuild import build_nso
from tests.test_fsdmsg_exe import TEXTS, _code
from tests.test_fsdmsg_images import _bgra_page, _label_page

TID = 0x0100000000AB0000
FSD_PATH = "data/dmc1/fsd/r100.fsd"
PAGE_PATH = "data/dmc1/etc/sayfa.t32"


@pytest.fixture(autouse=True)
def _no_folder(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Geliştiricinin kendi grafik klasörü testlere karışmasın."""
    monkeypatch.delenv(fsdmsg_graphics.ENV, raising=False)
    monkeypatch.delenv(legacy.ENV_NAMES[fsdmsg_graphics.ENV], raising=False)
    fsdmsg_graphics.from_environment.cache_clear()
    yield
    fsdmsg_graphics.from_environment.cache_clear()


def _image_texts(key: str = "0" * 16, **label: Any) -> dict[str, Any]:
    row = {"pencere": [0, 4, 128, 50], "ingilizce": "Blue Stone", "turkce": "Mavi Taş", "stil": "brush", **label}
    return {"dosyalar": [PAGE_PATH], "sayfalar": [{"ozetler": [key], "etiketler": [row]}]}


MENU_ROW = {"pencere": [3, 4, 80, 50], "ingilizce": "Lamp", "turkce": "Fener", "hiza": "left"}


def _with_menus(*ids: str) -> dict[str, Any]:
    return {**_image_texts(), "menuler": [{"dokular": list(ids or ("1234ABCD", "0000beef")), "etiketler": [MENU_ROW]}]}


def _descriptions() -> dict[str, Any]:
    turkish = ["Kötü\nruhlardır.", "Sol Çubuğu salla.", "Vur."]
    return {"aciklamalar": [{"ozet": exe.digest(en), "turkce": tr} for en, tr in zip(TEXTS, turkish, strict=True)]}


def _folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **files: Any) -> Path:
    """Ortam değişkeninin gösterdiği klasör; `files`: dosya adı → JSON nesnesi ya da ham metin."""
    folder = tmp_path / "grafik"
    folder.mkdir(exist_ok=True)
    for name, content in files.items():
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        (folder / name).write_text(text, encoding="utf-8")
    monkeypatch.setenv(fsdmsg_graphics.ENV, str(folder))
    return folder


# --- okuma ve şema --------------------------------------------------------------------------


def test_valid_data_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    texts = _image_texts(hiza="left", murekkep=[250, 240, 230], boy=20)
    folder = _folder(tmp_path, monkeypatch, **{IMAGE_TEXTS: texts, DESCRIPTIONS: _descriptions()})
    data = fsdmsg_userdata.load(folder)
    assert data.image_texts is not None
    assert data.image_texts.files == (PAGE_PATH,)
    label = Label((0, 4, 128, 50), "Blue Stone", "Mavi Taş", "brush", align="left", ink=(250, 240, 230), size=20)
    assert data.image_texts.pages == {"0" * 16: (label,)}
    expected = [(row["ozet"], row["turkce"]) for row in _descriptions()["aciklamalar"]]
    assert data.descriptions == tuple(expected)
    assert data.missing == ()
    assert data.image_texts.menus is None  # bölüm yok


def test_menu_section_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(tmp_path, monkeypatch, **{IMAGE_TEXTS: _with_menus()})
    texts = fsdmsg_userdata.load(folder).image_texts
    assert texts is not None
    label = Label((3, 4, 80, 50), "Lamp", "Fener", align="left")
    assert texts.menus == {0x1234ABCD: (label,), 0xBEEF: (label,)}


def test_byte_order_mark_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(tmp_path, monkeypatch)
    (folder / DESCRIPTIONS).write_bytes(b"\xef\xbb\xbf" + json.dumps(_descriptions()).encode())
    assert len(fsdmsg_userdata.load(folder).descriptions or ()) == 3


def test_missing_folder_and_files_mean_no_data() -> None:
    empty = fsdmsg_userdata.load(None)
    assert (empty.image_texts, empty.descriptions) == (None, None)
    assert empty.missing == (IMAGE_TEXTS, DESCRIPTIONS)


def _broken_cases() -> list[tuple[str, Any, str]]:
    def label(**change: Any) -> dict[str, Any]:
        texts = _image_texts()
        texts["sayfalar"][0]["etiketler"][0].update(change)
        return texts

    no_turkish = _image_texts()
    del no_turkish["sayfalar"][0]["etiketler"][0]["turkce"]
    return [
        (IMAGE_TEXTS, "{ bozuk", "JSON"),
        (IMAGE_TEXTS, [], "nesne"),
        (IMAGE_TEXTS, {"sayfalar": []}, "dosyalar"),
        (IMAGE_TEXTS, no_turkish, "sayfalar[1].etiketler[1].turkce"),
        (IMAGE_TEXTS, label(pencere=[0, 4, 128]), "pencere"),
        (IMAGE_TEXTS, label(pencere=[0, 4, "128", 50]), "pencere"),
        (IMAGE_TEXTS, label(pencere=[100, 4, 50, 50]), "pencere"),
        (IMAGE_TEXTS, label(boy=True), "boy"),
        (IMAGE_TEXTS, label(stil="yok"), "stil"),
        (IMAGE_TEXTS, label(hiza="orta"), "hiza"),
        (IMAGE_TEXTS, label(dolgu="boya"), "dolgu"),
        (IMAGE_TEXTS, label(turkçe="Mavi Taş"), "turkçe"),
        (IMAGE_TEXTS, label(murekkep=[1, 2, 300]), "murekkep"),
        (IMAGE_TEXTS, {**_image_texts(), "dosyalar": ["../disari.t32"]}, "dosyalar[1]"),
        (IMAGE_TEXTS, {**_image_texts(), "dosyalar": ["C:/oyun.t32"]}, "dosyalar[1]"),
        (IMAGE_TEXTS, {**_image_texts(), "sayfalar": [{"ozetler": ["xyz"], "etiketler": []}]}, "ozetler"),
        (DESCRIPTIONS, {"aciklamalar": [{"ozet": "ab", "turkce": "x"}]}, "aciklamalar[1].ozet"),
        (DESCRIPTIONS, {"aciklamalar": [{"ozet": "a" * 64}]}, "aciklamalar[1].turkce"),
        (DESCRIPTIONS, {"aciklamalar": {"ozet": "a" * 64}}, "aciklamalar"),
        (DESCRIPTIONS, {"aciklamalar": []}, "aciklamalar"),
        (IMAGE_TEXTS, _with_menus("XYZ"), "menuler[1].dokular[1]"),
        (IMAGE_TEXTS, _with_menus("1234ABCD", "1234abcd"), "menuler[1].dokular[2]"),
        (IMAGE_TEXTS, {**_image_texts(), "menuler": [{"dokular": ["1234ABCD"]}]}, "menuler[1].etiketler"),
        (IMAGE_TEXTS, {**_image_texts(), "menuler": {}}, "menuler"),
        (DESCRIPTIONS, {"aciklamalar": [{"ozet": "a" * 64, "turkce": 5}]}, "turkce"),
    ]


@pytest.mark.parametrize(("name", "content", "where"), _broken_cases())
def test_broken_data_is_a_clear_error(
    name: str, content: Any, where: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path, monkeypatch, **{name: content})
    with pytest.raises(UserDataError) as caught:
        fsdmsg_userdata.load(folder)
    assert name in caught.value.message
    assert where in caught.value.message
    assert caught.value.hint  # ne yapılacağı söylenir


def test_application_package_holds_no_extra_translation_data() -> None:
    assert not (resources.files("nxceviri") / "assets" / "fsdmsg").is_dir()
    source = Path(exe.__file__).read_text(encoding="utf-8")
    assert "resources" not in source
    assert not hasattr(exe, "translations")


# --- eklenti kancaları ---------------------------------------------------------------------


def test_without_data_only_menu_textures_are_patched_and_no_program_patch() -> None:
    plugin = FsdMsgPlugin()
    assert plugin.game_file_patches() == {}  # menü dokuları da değişmez
    code, _starts = _code()
    assert plugin.exefs_patches(code) == {}
    notes = plugin.derived_files(lambda _p: b"", [], None).notes
    assert len(notes) == 1
    assert IMAGE_TEXTS in notes[0]
    assert DESCRIPTIONS in notes[0]
    assert fsdmsg_graphics.ENV in notes[0]
    assert "tanımlı değil" in notes[0]  # değişken yok: önce onu tanımlamak gerekir
    assert "menü" in notes[0]


def test_with_data_pages_and_descriptions_are_patched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = _label_page()
    texts = {**_with_menus(), **_image_texts(page_key(page))}
    _folder(tmp_path, monkeypatch, **{IMAGE_TEXTS: texts, DESCRIPTIONS: _descriptions()})
    plugin = FsdMsgPlugin()
    patches = plugin.game_file_patches()
    assert set(patches) == {*MENU_FILES, PAGE_PATH}
    data = b"HEAD" + _bgra_page(page) + b"TAIL"
    out = patches[PAGE_PATH](data)
    assert len(out) == len(data)
    assert next(iter(iter_pages(out))).image.tobytes() != page.tobytes()
    code, _starts = _code()
    (build_id, blob), *rest = plugin.exefs_patches(code).items()
    assert not rest
    assert build_id == exe.BUILD_ID
    assert blob.startswith(b"IPS32")
    assert plugin.derived_files(lambda _p: b"", [], None).notes == []


def test_only_one_file_names_only_the_missing_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _folder(tmp_path, monkeypatch, **{DESCRIPTIONS: _descriptions()})
    (note,) = FsdMsgPlugin().derived_files(lambda _p: b"", [], None).notes
    assert IMAGE_TEXTS in note
    assert DESCRIPTIONS not in note
    assert "tanımlı değil" not in note


def test_prepared_pages_work_without_image_texts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hazır Türkçe sayfalar (`orijinal`/`temiz` + `dizin.json`) resim yazıları dosyası olmadan da çalışır."""
    folder = _folder(tmp_path, monkeypatch)
    original = _label_page()
    turkish = original.copy()
    turkish.paste((250, 0, 0, 255), (60, 0, 127, 20))
    for sub, image in (("orijinal", original), ("temiz", turkish)):
        (folder / sub).mkdir()
        image.save(folder / sub / "a.png")
    (folder / "dizin.json").write_text(json.dumps({"dosyalar": [PAGE_PATH]}), encoding="utf-8")
    patches = FsdMsgPlugin().game_file_patches()
    out = patches[PAGE_PATH](b"HEAD" + _bgra_page(original) + b"TAIL")
    assert next(iter(iter_pages(out))).image.tobytes() == turkish.tobytes()


# --- uçtan uca dışa aktarma ---------------------------------------------------------------


def _export(tmp_path: Path, name: str = "Mod") -> tuple[Path, Any]:
    keys = nxbuild.TestKeys.random()
    keys_path = keys.write(tmp_path / "prod.keys")
    files = {
        FSD_PATH: fsd(table([message("Do you have the key?"), message("Go now!")])),
        PAGE_PATH: b"T32 " + _bgra_page(_label_page()) + b"SON",
    }
    main = build_nso((b"\0" * 0x100,) * 3, (False, False, False))  # geçerli ama boş oyun kodu
    sections = [
        nxbuild.pfs0_section(nxbuild.build_pfs0([("main", main)])),
        nxbuild.romfs_section(nxbuild.build_romfs(files)),
    ]
    program = nxbuild.build_nca(keys, 0, TID, sections)
    package = nxbuild.build_package(keys, kind="base", title_id=TID, application_id=TID, version=0, program=program)
    nsp = tmp_path / "Deneme [base].nsp"
    nsp.write_bytes(package.nsp)
    inputs = Inputs((nsp,), load_keys(keys_path))
    project = Project.new()
    project.import_texts(extract_texts(inputs, scan_sources(inputs, TaskContext()), TaskContext()).files)
    rows = {r.source: r for r in project.translation_rows()}
    project.set_translations([(rows["Go now!"].id, "Hemen git!")])
    dest = tmp_path / "çıktı" / name
    result = export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, name),
        info=ExportInfo("Deneme", f"{TID:016X}", 0, None),
        ctx=TaskContext(),
    )
    return dest, result


def _romfs(path: str) -> str:
    return f"atmosphere/contents/{TID:016X}/romfs/{path}"


def test_export_without_data_writes_text_and_tells_the_user(tmp_path: Path) -> None:
    dest, result = _export(tmp_path)
    assert _romfs(FSD_PATH) in result.files
    assert _romfs(PAGE_PATH) not in result.files  # resim yazısı çevrilmeden kaldı
    assert not [f for f in result.files if "exefs" in f]
    assert not [w for w in result.warnings if "Program yaması" in w]
    info = (dest / INFO_FILE).read_text(encoding="utf-8")
    assert IMAGE_TEXTS in info
    assert DESCRIPTIONS in info


def test_export_with_data_patches_pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    texts = {**_with_menus(), **_image_texts(page_key(_label_page()))}
    _folder(tmp_path, monkeypatch, **{IMAGE_TEXTS: texts})
    dest, result = _export(tmp_path)
    assert _romfs(PAGE_PATH) in result.files
    written = (dest / _romfs(PAGE_PATH)).read_bytes()
    assert written.startswith(b"T32 ")
    assert next(iter(iter_pages(written))).image.tobytes() != _label_page().tobytes()
    info = (dest / INFO_FILE).read_text(encoding="utf-8")
    assert IMAGE_TEXTS not in info
    assert DESCRIPTIONS in info  # yalnızca eksik olan söylenir


@pytest.mark.parametrize("name", [IMAGE_TEXTS, DESCRIPTIONS])
def test_export_with_broken_data_stops_without_partial_output(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _folder(tmp_path, monkeypatch, **{name: "{ bozuk"})
    with pytest.raises(UserDataError) as caught:
        _export(tmp_path)
    assert name in caught.value.message
    out = tmp_path / "çıktı"
    assert not out.exists() or not list(out.iterdir())  # yarım mod ya da geçici klasör kalmadı


def test_missing_menu_section_is_named_separately(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _folder(tmp_path, monkeypatch, **{IMAGE_TEXTS: _image_texts(), DESCRIPTIONS: _descriptions()})
    plugin = FsdMsgPlugin()
    assert not set(plugin.game_file_patches()) & set(MENU_FILES)
    (note,) = plugin.derived_files(lambda _p: b"", [], None).notes
    assert '"menuler"' in note
    assert DESCRIPTIONS not in note
