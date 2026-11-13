"""`.nxproj` proje dosyası: kaydet/aç, göçler, bozuk dosyalar, Türkçe yollar."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nxceviri.core.errors import ProjectError
from nxceviri.core.formats.scanner import EngineGuess, ScanEntry, ScanReport
from nxceviri.core.project import SCHEMA_VERSION, Project, SourceRecord
from nxceviri.core.project import store as store_module


def _report(n: int = 3) -> ScanReport:
    entries = [
        ScanEntry("0100ABCD12340000", f"Message/bölüm_{i}.msbt", 100 + i, "msbt", "MSBT", "high", "update")
        for i in range(n)
    ]
    return ScanReport(
        game_name="Deneme Oyunu ğüş",
        title_id="0100ABCD12340000",
        base_version=0,
        update_version=65536,
        engine=EngineGuess("nintendo", "Nintendo LMS / NintendoWare", "low", ("MSBT metin dosyaları: 3",)),
        entries=entries,
        warnings=["uyarı: çğıİöşü"],
        duration_s=1.5,
    )


def _sources(folder: Path) -> list[SourceRecord]:
    return [
        SourceRecord(
            folder / "Oyunlarım ğüş" / "oyun.nsz",
            "base",
            "0100ABCD12340000",
            "0100ABCD12340000",
            0,
            "1.0.0",
            "Deneme Oyunu",
            123,
        ),
        SourceRecord(
            folder / "güncelleme İ.nsp",
            "update",
            "0100ABCD12340800",
            "0100ABCD12340000",
            65536,
            "1.0.1",
            "Deneme Oyunu",
            456,
        ),
    ]


def test_save_and_reopen_turkish_path(tmp_path: Path) -> None:
    project = Project.new()
    assert (project.path, project.cache_dir) == (None, None)
    project.set_game("Deneme Oyunu ğüş", "0100ABCD12340000")
    project.set_sources(_sources(tmp_path))
    project.save_scan(_report())
    target = tmp_path / "Projelerim çğıİöşü" / "Türkçe Çeviri"
    project.save_as(target)
    assert project.path == target.with_suffix(".nxproj")
    assert project.cache_dir is not None
    assert project.cache_dir.name == "Türkçe Çeviri_onbellek"
    project.close()

    reopened = Project.open(tmp_path / "Projelerim çğıİöşü" / "Türkçe Çeviri.nxproj")
    assert reopened.game_name == "Deneme Oyunu ğüş"
    assert reopened.title_id == "0100ABCD12340000"
    assert reopened.sources() == _sources(tmp_path)
    assert reopened.latest_scan() == _report()
    reopened.close()


def test_changes_after_save_are_written_to_file(tmp_path: Path) -> None:
    project = Project.new()
    project.save_as(tmp_path / "p.nxproj")
    project.set_sources(_sources(tmp_path))
    project.save_scan(_report(5))
    project.save_scan(_report(2))  # yeni tarama eskisinin yerine geçer
    project.close()
    reopened = Project.open(tmp_path / "p.nxproj")
    scan = reopened.latest_scan()
    assert scan is not None
    assert len(scan.entries) == 2
    reopened.clear_scan()
    assert reopened.latest_scan() is None
    reopened.close()


def test_empty_project(tmp_path: Path) -> None:
    project = Project.new()
    project.save_as(tmp_path / "bos.nxproj")
    project.close()
    reopened = Project.open(tmp_path / "bos.nxproj")
    assert reopened.sources() == []
    assert reopened.latest_scan() is None
    assert reopened.game_name == ""
    reopened.close()


def test_failed_transaction_keeps_old_data(tmp_path: Path) -> None:
    project = Project.new()
    project.save_as(tmp_path / "p.nxproj")
    project.set_sources(_sources(tmp_path))
    bad = [*_sources(tmp_path), _sources(tmp_path)[0]]  # aynı yol iki kez → UNIQUE ihlali
    with pytest.raises(sqlite3.IntegrityError):
        project.set_sources(bad)
    assert project.sources() == _sources(tmp_path)
    project.close()


def test_invalid_kind_rejected(tmp_path: Path) -> None:
    project = Project.new()
    bad = SourceRecord(tmp_path / "x.nsp", "bilinmeyen", "0", "0", 0, "", "", 0)
    with pytest.raises(sqlite3.IntegrityError):
        project.set_sources([bad])
    project.close()


def test_open_not_a_project(tmp_path: Path) -> None:
    junk = tmp_path / "çöp.nxproj"
    junk.write_bytes(b"bu bir veritabani degil" * 100)
    with pytest.raises(ProjectError, match="proje dosyası değil"):
        Project.open(junk)
    with pytest.raises(ProjectError, match="bulunamadı"):
        Project.open(tmp_path / "yok.nxproj")


def test_open_foreign_sqlite(tmp_path: Path) -> None:
    other = tmp_path / "baska.nxproj"
    conn = sqlite3.connect(other)
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()
    with pytest.raises(ProjectError, match="NXTR projesi değil"):
        Project.open(other)


def test_open_newer_schema(tmp_path: Path) -> None:
    project = Project.new()
    project.save_as(tmp_path / "yeni.nxproj")
    project.close()
    conn = sqlite3.connect(tmp_path / "yeni.nxproj")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(ProjectError, match="daha yeni"):
        Project.open(tmp_path / "yeni.nxproj")


def test_migration_runs_and_keeps_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project.new()
    project.set_game("Eski Oyun", "0100000000000000")
    project.save_as(tmp_path / "eski.nxproj")
    project.close()

    extra = "ALTER TABLE project ADD COLUMN notes TEXT NOT NULL DEFAULT 'göç';"
    monkeypatch.setattr(store_module, "MIGRATIONS", (*store_module.MIGRATIONS, extra))
    monkeypatch.setattr(store_module, "SCHEMA_VERSION", SCHEMA_VERSION + 1)
    migrated = Project.open(tmp_path / "eski.nxproj")
    assert migrated.game_name == "Eski Oyun"
    migrated.close()
    assert (tmp_path / "eski.nxproj.bak").exists()
    conn = sqlite3.connect(tmp_path / "eski.nxproj")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION + 1
    assert conn.execute("SELECT notes FROM project").fetchone()[0] == "göç"
    conn.close()


def test_failed_migration_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project.new()
    project.save_as(tmp_path / "p.nxproj")
    project.close()
    monkeypatch.setattr(store_module, "MIGRATIONS", (*store_module.MIGRATIONS, "CREATE TABLE project (x);"))
    monkeypatch.setattr(store_module, "SCHEMA_VERSION", SCHEMA_VERSION + 1)
    with pytest.raises(ProjectError, match="güncellenemedi"):
        Project.open(tmp_path / "p.nxproj")
    conn = sqlite3.connect(tmp_path / "p.nxproj")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    conn.close()


def test_save_as_failure_is_reported(tmp_path: Path) -> None:
    blocker = tmp_path / "dosya"
    blocker.write_text("x", encoding="utf-8")
    project = Project.new()
    with pytest.raises(ProjectError, match="kaydedilemedi"):
        project.save_as(blocker / "alt" / "p.nxproj")  # üst yol bir dosya
    assert project.path is None
    project.close()


def test_save_as_keeps_old_connection_when_reconnect_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project.new()
    project.set_game("Eski Bağlantı", "0100")
    real_connect = store_module._connect
    calls = {"n": 0}

    def flaky(target: str | Path) -> sqlite3.Connection:
        calls["n"] += 1
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(store_module, "_connect", flaky)
    with pytest.raises(ProjectError, match="kaydedilemedi"):
        project.save_as(tmp_path / "p.nxproj")
    monkeypatch.setattr(store_module, "_connect", real_connect)
    assert project.path is None
    assert project.game_name == "Eski Bağlantı"
    assert project.translation_rows() == []
    project.close()


def _spy_connections(monkeypatch: pytest.MonkeyPatch) -> list[sqlite3.Connection]:
    """`sqlite3.connect` çağrılarının açtığı bağlantıları kaydeder."""
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def spy(database: str, isolation_level: None = None) -> sqlite3.Connection:
        conn = real_connect(database, isolation_level=isolation_level)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", spy)
    return opened


def test_open_closes_connection_on_every_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened = _spy_connections(monkeypatch)
    junk = tmp_path / "çöp.nxproj"
    junk.write_bytes(b"bu bir veritabani degil" * 100)
    with pytest.raises(ProjectError, match="proje dosyası değil"):
        Project.open(junk)
    assert opened
    for conn in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")  # kapalı bağlantı
    junk.unlink()  # Windows'ta kilit kalmadığını da doğrular


def test_open_closes_connection_when_migration_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project.new()
    project.save_as(tmp_path / "p.nxproj")
    project.close()
    opened = _spy_connections(monkeypatch)
    monkeypatch.setattr(store_module, "MIGRATIONS", (*store_module.MIGRATIONS, "CREATE TABLE project (x);"))
    monkeypatch.setattr(store_module, "SCHEMA_VERSION", SCHEMA_VERSION + 1)
    with pytest.raises(ProjectError, match="güncellenemedi"):
        Project.open(tmp_path / "p.nxproj")
    for conn in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


class _FailingConn:
    """`_Transaction` için sahte bağlantı: verilen deyimler `sqlite3.OperationalError` verir."""

    def __init__(self, failing: set[str]) -> None:
        self.failing = failing

    def execute(self, sql: str) -> None:
        if sql in self.failing:
            raise sqlite3.OperationalError(f"{sql} başarısız")


def test_transaction_rollback_failure_does_not_mask_body_error(caplog: pytest.LogCaptureFixture) -> None:
    conn = _FailingConn({"ROLLBACK"})
    with pytest.raises(ValueError, match="gövde hatası"), store_module._Transaction(conn):  # type: ignore[arg-type]
        raise ValueError("gövde hatası")
    assert "ROLLBACK" in caplog.text


def test_transaction_rollback_failure_does_not_mask_commit_error(caplog: pytest.LogCaptureFixture) -> None:
    conn = _FailingConn({"COMMIT", "ROLLBACK"})
    with pytest.raises(ProjectError, match="yazılamadı"), store_module._Transaction(conn):  # type: ignore[arg-type]
        pass
    assert "ROLLBACK" in caplog.text


def test_large_scan_table(tmp_path: Path) -> None:
    project = Project.new()
    project.save_scan(_report(50_000))
    project.save_as(tmp_path / "buyuk.nxproj")
    project.close()
    reopened = Project.open(tmp_path / "buyuk.nxproj")
    scan = reopened.latest_scan()
    assert scan is not None
    assert len(scan.entries) == 50_000
    reopened.close()


def test_write_copy_and_open_copy_keep_original_untouched(tmp_path: Path) -> None:
    project = Project.new()
    project.set_game("Kopya Oyunu", "0100")
    copy = tmp_path / "kurtarma" / "kopya.nxproj"
    project.write_copy(copy)
    assert project.path is None  # kopya yazmak projenin dosyasını değiştirmez
    loaded = Project.open_copy(copy)
    assert loaded.path is None  # bellekte; yazımlar kopyaya gitmez
    assert loaded.game_name == "Kopya Oyunu"
    loaded.set_game("Değişti", "0100")
    loaded.close()
    reopened = Project.open(copy)
    assert reopened.game_name == "Kopya Oyunu"
    reopened.close()
