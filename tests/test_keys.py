"""Anahtar dosyası okuma, doğrulama ve anahtar sızdırmama testleri."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from nxceviri.core.container.nca import Nca
from nxceviri.core.container.package import open_package
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import build_game_view
from nxceviri.core.errors import ContainerError, KeyFileError, MissingKeyError, NxError
from nxceviri.core.formats.scanner import scan_view
from nxceviri.core.keys import KeySet, load_keys, load_title_keys
from nxceviri.core.project import Project, SourceRecord
from tests import nxbuild
from tests.conftest import GameFiles


def test_valid_keys_file_loads(game: GameFiles) -> None:
    keys = load_keys(game.keys_path)
    summary = keys.summary()
    assert summary.key_area_generations == (0, 1, 2)
    assert summary.titlekek_generations == (0, 1, 2)
    assert summary.newest_generation == 2
    assert keys.header_key == game.keys.header_key


def test_turkish_path_and_bom(tmp_path: Path) -> None:
    folder = tmp_path / "Anahtarlarım ğüşıöç İ"
    folder.mkdir()
    keys = nxbuild.TestKeys.random()
    path = folder / "prod.keys"
    path.write_bytes(b"\xef\xbb\xbf" + "\r\n".join(keys.lines()).encode())
    assert load_keys(path).header_key == keys.header_key


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"", "boş"),
        (b"\xff\xfe\x00\x01garbage\x80\x81", "metin dosyası değil"),
        (b"header_key = 00112233\nbu satir bozuk\n", "2. satır"),
        (b"header_key = 0011223\n", "1. satır"),  # tek sayıda onaltılık hane
        (b"titlekek_00 = " + b"00" * 16 + b"\nkey_area_key_application_00 = " + b"00" * 16 + b"\n", "header_key"),
        (b"header_key = " + b"00" * 32 + b"\n", "key_area_key_application_XX"),
        (b"header_key = " + b"00" * 16 + b"\n", "uzunluğu hatalı"),
        (b"; sadece yorum\n\n", "hiç anahtar yok"),
    ],
)
def test_broken_keys_file(tmp_path: Path, content: bytes, expected: str) -> None:
    path = tmp_path / "prod.keys"
    path.write_bytes(content)
    with pytest.raises(KeyFileError) as exc:
        load_keys(path)
    assert expected in exc.value.message
    assert exc.value.hint  # kullanıcıya ne yapacağı söylenir


def test_missing_and_directory(tmp_path: Path) -> None:
    with pytest.raises(KeyFileError, match="bulunamadı"):
        load_keys(tmp_path / "yok.keys")
    with pytest.raises(KeyFileError, match="dosya değil"):
        load_keys(tmp_path)


def test_too_large_file(tmp_path: Path) -> None:
    path = tmp_path / "prod.keys"
    path.write_bytes(b"a" * (1024 * 1024 + 1))
    with pytest.raises(KeyFileError, match="kadar büyük"):
        load_keys(path)


def test_title_keys(tmp_path: Path) -> None:
    rid, tkey = os.urandom(16), os.urandom(16)
    path = tmp_path / "title.keys"
    path.write_text(f"{rid.hex()} = {tkey.hex()}\n", encoding="utf-8")
    assert load_title_keys(path) == {rid: tkey}
    path.write_text(f"{rid.hex()[:-2]} = {tkey.hex()}\n", encoding="utf-8")
    with pytest.raises(KeyFileError):
        load_title_keys(path)


def test_missing_generation_is_reported_by_name() -> None:
    keys = KeySet({"header_key": b"\0" * 32})
    with pytest.raises(MissingKeyError) as exc:
        keys.titlekek(5)
    assert "titlekek_04" in exc.value.message


def test_wrong_header_key_gives_clear_error(game: GameFiles, tmp_path: Path) -> None:
    other = nxbuild.TestKeys.random().write(tmp_path / "baska.keys")
    with pytest.raises(ContainerError) as exc:
        open_package(game.base_nsp, load_keys(other))
    assert "header_key" in exc.value.hint


def test_wrong_title_key_gives_clear_error(game: GameFiles, tmp_path: Path) -> None:
    # Doğru header_key, yanlış titlekek: RomFS başlığı çözülemez.
    wrong = nxbuild.TestKeys(game.keys.header_key, game.keys.key_area, {g: os.urandom(16) for g in range(3)})
    keys = load_keys(wrong.write(tmp_path / "yanlis.keys"))
    with open_package(game.base_nsp, keys) as pkg, pytest.raises(ContainerError, match="başlığı geçersiz"):
        build_game_view([pkg])


def test_key_values_never_leak(game: GameFiles, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Anahtar değerleri log'a, hata mesajına, repr'e veya proje dosyasına asla yazılmaz."""
    caplog.set_level(logging.DEBUG)
    secrets = game.keys.all_secret_hex()
    texts: list[str] = []

    keys = load_keys(game.keys_path)
    texts += [repr(keys), str(keys), str(keys.summary())]
    with open_package(game.base_nsp, keys) as base, open_package(game.update_nsp, keys) as upd:
        view = build_game_view([base, upd])
        report = scan_view(view)
        program = base.program_nca()
        assert program is not None
        assert len(program.content_key()) == 16  # anahtar hesaplanır ama hiçbir yere yazılmaz
        texts += [repr(base), repr(upd)]

        project = Project.new()
        project.set_sources(
            [SourceRecord(base.path, base.kind, base.title_id, base.application_id, 0, "1.0.0", "x", 1)]
        )
        project.save_scan(report)
        project.save_as(tmp_path / "proje.nxproj")
        project.close()

    # Hata yolları: yanlış/eksik anahtarlarla oluşan mesajlar.
    for builder in (
        lambda: Nca(MemoryStorage(b"\0" * 0xC00), keys),
        lambda: load_keys(game.keys_path.with_name("yok.keys")),
        lambda: KeySet({}).header_key,
    ):
        with pytest.raises(NxError) as exc:
            builder()
        texts.append(exc.value.user_text())

    texts.append(caplog.text)
    project_bytes = (tmp_path / "proje.nxproj").read_bytes()
    blob = "\n".join(texts).lower()
    for secret in secrets:
        assert secret not in blob
        assert secret.encode() not in project_bytes.lower()
        assert bytes.fromhex(secret) not in project_bytes
