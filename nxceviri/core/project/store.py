"""`.nxproj` proje dosyası: tek bir SQLite veritabanı.

- Şema sürümü `PRAGMA user_version` ile izlenir; göçler (`MIGRATIONS`) sırayla,
  her biri tek bir işlem (transaction) içinde uygulanır. Göçten önce `.nxproj.bak`
  yedeği alınır.
- Dosyanın bize ait olduğu `PRAGMA application_id` ile anlaşılır.
- Kaydedilmemiş yeni proje bellekte tutulur; "Farklı kaydet" SQLite yedekleme API'siyle
  önce geçici dosyaya yazar, sonra atomik olarak yerine taşır.
- Anahtar dosyası *içeriği* asla burada saklanmaz.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from nxceviri import __version__
from nxceviri.core.errors import ProjectError
from nxceviri.core.formats.base import TextEntry
from nxceviri.core.formats.scanner import EngineGuess, ScanEntry, ScanReport
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.status import SOURCE_CHANGED_NOTE, Status, evaluate
from nxceviri.core.translate.uppercase import EXCEPT_KEY, GROUPS_KEY, ROWS_KEY, UppercaseRules

log = logging.getLogger(__name__)

APPLICATION_ID = 0x4E585052  # "NXPR"
PROJECT_SUFFIX = ".nxproj"

MIGRATIONS: tuple[str, ...] = (
    # 1: ilk şema
    """
    CREATE TABLE project (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        game_name TEXT NOT NULL DEFAULT '',
        title_id TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        app_version TEXT NOT NULL
    );
    CREATE TABLE sources (
        id INTEGER PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL CHECK (kind IN ('base', 'update', 'dlc')),
        title_id TEXT NOT NULL,
        application_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        display_version TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '',
        file_size INTEGER NOT NULL,
        added_at TEXT NOT NULL
    );
    CREATE TABLE scans (
        id INTEGER PRIMARY KEY,
        created_at TEXT NOT NULL,
        game_name TEXT NOT NULL,
        title_id TEXT NOT NULL,
        base_version INTEGER,
        update_version INTEGER,
        engine TEXT NOT NULL,
        engine_label TEXT NOT NULL,
        engine_confidence TEXT NOT NULL,
        engine_evidence TEXT NOT NULL,
        warnings TEXT NOT NULL,
        duration_s REAL NOT NULL
    );
    CREATE TABLE scan_files (
        id INTEGER PRIMARY KEY,
        scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
        title_id TEXT NOT NULL,
        path TEXT NOT NULL,
        size INTEGER NOT NULL,
        kind TEXT NOT NULL,
        detail TEXT NOT NULL,
        likelihood TEXT NOT NULL,
        origin TEXT NOT NULL
    );
    CREATE INDEX scan_files_by_scan ON scan_files(scan_id, kind);
    """,
    # 2: çeviri tablosu (M2)
    """
    CREATE TABLE text_files (
        id INTEGER PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        title_id TEXT NOT NULL,
        format TEXT NOT NULL,
        origin TEXT NOT NULL,
        imported_at TEXT NOT NULL
    );
    CREATE TABLE text_entries (
        id INTEGER PRIMARY KEY,
        file_id INTEGER NOT NULL REFERENCES text_files(id) ON DELETE CASCADE,
        key TEXT NOT NULL,
        idx INTEGER NOT NULL,
        source TEXT NOT NULL,
        codes TEXT NOT NULL,
        max_length INTEGER,
        translation TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'untranslated'
            CHECK (status IN ('untranslated', 'machine', 'approved', 'error')),
        note TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        UNIQUE (file_id, key)
    );
    CREATE INDEX text_entries_by_file ON text_entries(file_id, idx);
    CREATE INDEX text_entries_by_status ON text_entries(status);
    """,
    # 3: okunur anahtar adı (Unity Localization anahtarları gibi) (M6)
    """
    ALTER TABLE text_entries ADD COLUMN context TEXT NOT NULL DEFAULT '';
    """,
    # 4: çeviri belleği, sözlük, proje ayarları (M3)
    """
    CREATE TABLE memory (
        source TEXT PRIMARY KEY,
        translation TEXT NOT NULL,
        origin TEXT NOT NULL CHECK (origin IN ('human', 'machine')),
        updated_at TEXT NOT NULL
    );
    CREATE TABLE glossary (
        id INTEGER PRIMARY KEY,
        term TEXT NOT NULL,
        translation TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # 5: çeviri geçmişi (her değişiklikte önceki çeviri; işe göre gruplanır, geri alınabilir)
    """
    CREATE TABLE history (
        id INTEGER PRIMARY KEY,
        entry_id INTEGER NOT NULL REFERENCES text_entries(id) ON DELETE CASCADE,
        old_text TEXT NOT NULL,
        old_status TEXT NOT NULL,
        old_note TEXT NOT NULL,
        new_text TEXT NOT NULL,
        job TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE INDEX history_by_entry ON history(entry_id, id);
    CREATE INDEX history_by_job ON history(job);
    """,
    # 6: "redakte" durumu (dış redaksiyondan gelen düzeltmeler); CHECK kısıtı tablo yeniden kurularak değişir
    """
    CREATE TABLE text_entries_new (
        id INTEGER PRIMARY KEY,
        file_id INTEGER NOT NULL REFERENCES text_files(id) ON DELETE CASCADE,
        key TEXT NOT NULL,
        idx INTEGER NOT NULL,
        source TEXT NOT NULL,
        codes TEXT NOT NULL,
        max_length INTEGER,
        translation TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'untranslated'
            CHECK (status IN ('untranslated', 'machine', 'redacted', 'approved', 'error')),
        note TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        context TEXT NOT NULL DEFAULT '',
        UNIQUE (file_id, key)
    );
    INSERT INTO text_entries_new
        (id, file_id, key, idx, source, codes, max_length, translation, status, note, updated_at, context)
        SELECT id, file_id, key, idx, source, codes, max_length, translation, status, note, updated_at, context
        FROM text_entries;
    DROP TABLE text_entries;
    ALTER TABLE text_entries_new RENAME TO text_entries;
    CREATE INDEX text_entries_by_file ON text_entries(file_id, idx);
    CREATE INDEX text_entries_by_status ON text_entries(status);
    """,
)
SCHEMA_VERSION = len(MIGRATIONS)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def row_group(r: TranslationRow) -> str:
    """Satırın grubu: Unity'de tablo koleksiyonu (ör. "Dialogue"), diğerlerinde dosya adı."""
    if "/" in r.context:
        return r.context.split("/", 1)[0]
    return r.file.rsplit(">", 1)[-1].rsplit("/", 1)[-1]


@dataclass(frozen=True)
class SourceRecord:
    path: Path
    kind: str
    title_id: str
    application_id: str
    version: int
    display_version: str
    name: str
    file_size: int


def _connect(target: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(target), isolation_level=None)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = FULL")
    except BaseException:
        conn.close()  # yarım kalan bağlantı dosyayı kilitli bırakmasın
        raise
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    (version,) = conn.execute("PRAGMA user_version").fetchone()
    if version >= SCHEMA_VERSION:
        return
    # Tablo yeniden kuran göçlerde (ör. CHECK kısıtı değişimi) yabancı anahtarlar geçici olarak kapatılır;
    # aksi hâlde DROP TABLE, bağlı geçmiş satırlarını ON DELETE CASCADE ile siler.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for target in range(version + 1, SCHEMA_VERSION + 1):
            try:
                conn.executescript(
                    f"BEGIN;\n{MIGRATIONS[target - 1]}\nPRAGMA user_version = {target};\n"
                    f"PRAGMA application_id = {APPLICATION_ID};\nCOMMIT;"
                )
            except sqlite3.Error as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise ProjectError(
                    f"Proje dosyası güncellenemedi (proje sürümü {target}): {exc}",
                    "Proje dosyasının yanındaki .bak yedeğini kullanabilirsiniz.",
                ) from None
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise ProjectError(
                "Proje dosyası güncellenirken bağlı kayıtlar bozuldu.",
                "Proje dosyasının yanındaki .bak yedeğini kullanabilirsiniz.",
            )
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


@dataclass(frozen=True)
class ImportedFile:
    """Oyundan çıkarılmış bir metin dosyası (projeye aktarılmak üzere)."""

    path: str  # tarama raporundaki yol (iç arşiv yolu olabilir)
    title_id: str
    format: str
    origin: str
    entries: tuple[TextEntry, ...]


@dataclass(frozen=True)
class ImportStats:
    files: int
    added: int
    changed: int
    unchanged: int
    removed: int


@dataclass(frozen=True)
class Change:
    """Bir satırın çevirisindeki bir değişiklik (geçmişten); `old_*` alanlarıyla geri alınabilir."""

    entry_id: int
    label: str  # satırın okunur adı (bağlam veya anahtar)
    source: str
    old_text: str
    old_status: str
    old_note: str
    new_text: str
    job: str
    created_at: str


#: Geçmiş kaydında elle yapılan değişikliklerin iş adı.
JOB_MANUAL = "elle"
#: Geri alma işleminin iş adı.
JOB_REVERT = "geri-al"
#: Onay kaldırma işleminin (geri alma yığınındaki) adı.
JOB_UNAPPROVE = "onay-kaldir"
#: Geri alma yığınında tutulan en çok işlem.
UNDO_LIMIT = 100


@dataclass(frozen=True)
class UndoStep:
    """Geri alınabilir bir işlem: iş adı ve değiştirdiği satırların önceki (metin, durum, açıklama) hâli."""

    job: str
    before: dict[int, tuple[str, str, str]]


@dataclass(frozen=True)
class TranslationRow:
    id: int
    file: str
    key: str
    source: str
    translation: str
    status: str
    note: str
    code_labels: tuple[str, ...]
    max_length: int | None
    context: str = ""


def _codes_json(entry: TextEntry) -> str:
    return json.dumps([[c.raw.hex(), c.label] for c in entry.codes], ensure_ascii=False)


_ROW_SQL = (
    "SELECT e.id, f.path, e.key, e.source, e.translation, e.status, e.note, e.codes, e.max_length, e.context "
    "FROM text_entries e JOIN text_files f ON f.id = e.file_id"
)


def _row(r: tuple[object, ...]) -> TranslationRow:
    codes = json.loads(str(r[7]))
    return TranslationRow(
        id=int(str(r[0])),
        file=str(r[1]),
        key=str(r[2]),
        source=str(r[3]),
        translation=str(r[4]),
        status=str(r[5]),
        note=str(r[6]),
        code_labels=tuple(str(c[1]) for c in codes),
        max_length=None if r[8] is None else int(str(r[8])),
        context=str(r[9]),
    )


class Project:
    """Açık bir proje. Tüm yazımlar işlem içinde yapılır."""

    def __init__(self, conn: sqlite3.Connection, path: Path | None) -> None:
        self._conn = conn
        self.path = path
        #: Bu oturumda yapılan işlemler (Ctrl+Z); proje kapanınca unutulur, kalıcı geçmiş `history` tablosundadır.
        self._undo: list[UndoStep] = []

    # --- yaşam döngüsü -------------------------------------------------------------

    @classmethod
    def new(cls) -> Project:
        conn = _connect(":memory:")
        _migrate(conn)
        now = _now()
        with _Transaction(conn):
            conn.execute(
                "INSERT INTO project (id, created_at, updated_at, app_version) VALUES (1, ?, ?, ?)",
                (now, now, __version__),
            )
        return cls(conn, None)

    @classmethod
    def open(cls, path: Path) -> Project:
        if not path.is_file():
            raise ProjectError(f"Proje dosyası bulunamadı: {path}", "Dosyanın yerini kontrol edin.")
        try:
            conn = _connect(path)
        except sqlite3.DatabaseError:
            raise ProjectError(
                f"Dosya bir proje dosyası değil veya bozuk: {path.name}",
                "Yalnızca NXTR ile oluşturulmuş .nxproj dosyalarını açabilirsiniz.",
            ) from None
        return cls(cls._validate_and_migrate(conn, path), path)

    @staticmethod
    def _validate_and_migrate(conn: sqlite3.Connection, path: Path) -> sqlite3.Connection:
        """Açılan bağlantıyı doğrular, gerekirse göç ettirir; hata fırlatırsa elindeki son bağlantıyı kapatır."""
        try:
            try:
                app_id = conn.execute("PRAGMA application_id").fetchone()[0]
                (version,) = conn.execute("PRAGMA user_version").fetchone()
            except sqlite3.DatabaseError:
                raise ProjectError(
                    f"Dosya bir proje dosyası değil veya bozuk: {path.name}",
                    "Yalnızca NXTR ile oluşturulmuş .nxproj dosyalarını açabilirsiniz.",
                ) from None
            if app_id != APPLICATION_ID:
                raise ProjectError(
                    f"Bu dosya bir NXTR projesi değil: {path.name}",
                    "Yalnızca bu uygulamayla kaydedilmiş .nxproj dosyalarını açabilirsiniz.",
                )
            if version > SCHEMA_VERSION:
                raise ProjectError(
                    f"Proje, uygulamanın daha yeni bir sürümüyle kaydedilmiş (proje sürümü {version}).",
                    "Uygulamayı güncelleyip yeniden deneyin.",
                )
            if version < SCHEMA_VERSION:
                conn.close()
                shutil.copy2(path, path.with_name(path.name + ".bak"))
                conn = _connect(path)
                _migrate(conn)
            try:
                ok = conn.execute("PRAGMA quick_check").fetchone()[0]
                row = conn.execute("SELECT COUNT(*) FROM project").fetchone()[0]
            except sqlite3.DatabaseError:
                ok, row = "bozuk", 0
            if ok != "ok" or row != 1:
                raise ProjectError(f"Proje dosyası bozuk: {path.name}", "Varsa .nxproj.bak yedeğini açmayı deneyin.")
            return conn
        except BaseException:
            conn.close()  # hangi hata olursa olsun dosya kilitli kalmasın
            raise

    def save_as(self, path: Path) -> None:
        """Projeyi `path`'e atomik olarak yazar ve bundan sonra o dosyayla çalışır."""
        if path.suffix.lower() != PROJECT_SUFFIX:
            path = path.with_name(path.name + PROJECT_SUFFIX)
        if self.path is not None and path.resolve() == self.path.resolve():
            return  # zaten bu dosyaya doğrudan yazılıyor
        self.write_copy(path)
        try:
            new_conn = _connect(path)
        except (OSError, sqlite3.Error) as exc:
            raise ProjectError(
                f"Proje kaydedilemedi: {path}",
                (
                    "Dosya yazıldı ama açılamadı; proje eski yerinde açık kalıyor. "
                    f"Dosyanın kilitli olmadığından emin olun. ({exc})"
                ),
            ) from None
        self._conn.close()
        self._conn = new_conn
        self.path = path

    def write_copy(self, path: Path) -> None:
        """Projenin anlık kopyasını `path`'e atomik olarak yazar; proje kendi dosyasıyla çalışmayı sürdürür."""
        tmp = path.with_name(path.name + ".yaziliyor")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            dst = sqlite3.connect(str(tmp))
            try:
                self._conn.backup(dst)
            finally:
                dst.close()
            os.replace(tmp, path)
        except (OSError, sqlite3.Error) as exc:
            raise ProjectError(
                f"Proje kaydedilemedi: {path}",
                f"Klasöre yazma izniniz olduğundan ve diskte yer bulunduğundan emin olun. ({exc})",
            ) from None
        finally:
            tmp.unlink(missing_ok=True)

    @classmethod
    def open_copy(cls, path: Path) -> Project:
        """Proje dosyasını belleğe yükler: kaydedilmemiş yeni bir proje gibi davranır, dosyaya yazılmaz."""
        source = cls.open(path)
        conn = _connect(":memory:")
        try:
            source._conn.backup(conn)
        finally:
            source.close()
        return cls(conn, None)

    def close(self) -> None:
        self._conn.close()

    @property
    def cache_dir(self) -> Path | None:
        """Projeye ait önbellek klasörü (kaydedilmemiş projede yok)."""
        if self.path is None:
            return None
        return self.path.with_name(self.path.stem + "_onbellek")

    # --- proje bilgileri ------------------------------------------------------------

    @property
    def game_name(self) -> str:
        return str(self._conn.execute("SELECT game_name FROM project").fetchone()[0])

    @property
    def title_id(self) -> str:
        return str(self._conn.execute("SELECT title_id FROM project").fetchone()[0])

    def set_game(self, name: str, title_id: str) -> None:
        with _Transaction(self._conn):
            self._conn.execute(
                "UPDATE project SET game_name = ?, title_id = ?, updated_at = ?", (name, title_id, _now())
            )

    # --- kaynak dosyalar -------------------------------------------------------------

    def sources(self) -> list[SourceRecord]:
        rows = self._conn.execute(
            "SELECT path, kind, title_id, application_id, version, display_version, name, file_size "
            "FROM sources ORDER BY CASE kind WHEN 'base' THEN 0 WHEN 'update' THEN 1 ELSE 2 END, title_id, version"
        ).fetchall()
        return [SourceRecord(Path(r[0]), *r[1:]) for r in rows]

    def set_sources(self, sources: list[SourceRecord]) -> None:
        """Kaynak listesini tek işlemde değiştirir."""
        now = _now()
        with _Transaction(self._conn):
            self._conn.execute("DELETE FROM sources")
            self._conn.executemany(
                "INSERT INTO sources (path, kind, title_id, application_id, version, display_version, name, "
                "file_size, added_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        str(s.path),
                        s.kind,
                        s.title_id,
                        s.application_id,
                        s.version,
                        s.display_version,
                        s.name,
                        s.file_size,
                        now,
                    )
                    for s in sources
                ],
            )
            self._conn.execute("UPDATE project SET updated_at = ?", (now,))

    # --- tarama sonucu ----------------------------------------------------------------

    def save_scan(self, report: ScanReport) -> None:
        """Tarama sonucunu yazar; önceki taramaların yerine geçer."""
        with _Transaction(self._conn):
            self._conn.execute("DELETE FROM scans")
            cur = self._conn.execute(
                "INSERT INTO scans (created_at, game_name, title_id, base_version, update_version, engine, "
                "engine_label, engine_confidence, engine_evidence, warnings, duration_s) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _now(),
                    report.game_name,
                    report.title_id,
                    report.base_version,
                    report.update_version,
                    report.engine.engine,
                    report.engine.label,
                    report.engine.confidence,
                    json.dumps(list(report.engine.evidence), ensure_ascii=False),
                    json.dumps(report.warnings, ensure_ascii=False),
                    report.duration_s,
                ),
            )
            scan_id = cur.lastrowid
            self._conn.executemany(
                "INSERT INTO scan_files (scan_id, title_id, path, size, kind, detail, likelihood, origin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (scan_id, e.title_id, e.path, e.size, e.kind, e.detail, e.likelihood, e.origin)
                    for e in report.entries
                ],
            )
            self._conn.execute("UPDATE project SET updated_at = ?", (_now(),))

    def clear_scan(self) -> None:
        with _Transaction(self._conn):
            self._conn.execute("DELETE FROM scans")

    def latest_scan(self) -> ScanReport | None:
        row = self._conn.execute(
            "SELECT id, game_name, title_id, base_version, update_version, engine, engine_label, "
            "engine_confidence, engine_evidence, warnings, duration_s FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        files = self._conn.execute(
            "SELECT title_id, path, size, kind, detail, likelihood, origin FROM scan_files "
            "WHERE scan_id = ? ORDER BY id",
            (row[0],),
        ).fetchall()
        return ScanReport(
            game_name=row[1],
            title_id=row[2],
            base_version=row[3],
            update_version=row[4],
            engine=EngineGuess(row[5], row[6], row[7], tuple(json.loads(row[8]))),
            entries=[ScanEntry(*f) for f in files],
            warnings=list(json.loads(row[9])),
            duration_s=row[10],
        )

    # --- çeviri tablosu ---------------------------------------------------------------------

    def import_texts(self, files: list[ImportedFile]) -> ImportStats:
        """Çıkarılan metinleri tek işlemde projeyle eşitler.

        Var olan çeviriler korunur. Orijinal metni değişen girdinin çevirisi silinmez,
        "hatalı" işaretlenip gözden geçirilmeye bırakılır. Artık oyunda olmayan dosya ve
        girdiler kaldırılır. Geri alma yığını boşalır (önceki işlemler eski metinlere göredir).
        """
        self._undo.clear()
        now = _now()
        added = changed = unchanged = removed = 0
        conn = self._conn
        with _Transaction(conn):
            keep_paths = {f.path for f in files}
            for fid, path in conn.execute("SELECT id, path FROM text_files").fetchall():
                if path not in keep_paths:
                    removed += conn.execute("SELECT COUNT(*) FROM text_entries WHERE file_id = ?", (fid,)).fetchone()[0]
                    conn.execute("DELETE FROM text_files WHERE id = ?", (fid,))
            for f in files:
                row = conn.execute("SELECT id FROM text_files WHERE path = ?", (f.path,)).fetchone()
                if row is None:
                    cur = conn.execute(
                        "INSERT INTO text_files (path, title_id, format, origin, imported_at) VALUES (?, ?, ?, ?, ?)",
                        (f.path, f.title_id, f.format, f.origin, now),
                    )
                    fid = cur.lastrowid
                else:
                    fid = row[0]
                    conn.execute(
                        "UPDATE text_files SET title_id = ?, format = ?, origin = ?, imported_at = ? WHERE id = ?",
                        (f.title_id, f.format, f.origin, now, fid),
                    )
                existing = {
                    r[0]: (r[1], r[2], r[3])
                    for r in conn.execute(
                        "SELECT key, id, source, translation FROM text_entries WHERE file_id = ?", (fid,)
                    ).fetchall()
                }
                keys = set()
                for e in f.entries:
                    keys.add(e.key)
                    old = existing.get(e.key)
                    if old is None:
                        conn.execute(
                            "INSERT INTO text_entries "
                            "(file_id, key, idx, source, codes, max_length, context, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (fid, e.key, e.index, e.source, _codes_json(e), e.max_length, e.context, now),
                        )
                        added += 1
                    elif old[1] == e.source:
                        conn.execute(
                            "UPDATE text_entries SET idx = ?, codes = ?, max_length = ?, context = ? WHERE id = ?",
                            (e.index, _codes_json(e), e.max_length, e.context, old[0]),
                        )
                        unchanged += 1
                    else:
                        status, note = (Status.ERROR, SOURCE_CHANGED_NOTE) if old[2] else (Status.UNTRANSLATED, "")
                        conn.execute(
                            "UPDATE text_entries SET idx = ?, source = ?, codes = ?, max_length = ?, context = ?, "
                            "status = ?, "
                            "note = ?, updated_at = ? WHERE id = ?",
                            (e.index, e.source, _codes_json(e), e.max_length, e.context, status, note, now, old[0]),
                        )
                        changed += 1
                for key, (eid, _src, _tr) in existing.items():
                    if key not in keys:
                        conn.execute("DELETE FROM text_entries WHERE id = ?", (eid,))
                        removed += 1
            conn.execute("UPDATE project SET updated_at = ?", (now,))
        return ImportStats(len(files), added, changed, unchanged, removed)

    def text_files(self) -> list[tuple[str, str, str]]:
        """Aktarılmış metin dosyaları: (tarama yolu, TitleID, biçim)."""
        rows = self._conn.execute("SELECT path, title_id, format FROM text_files ORDER BY path").fetchall()
        return [(str(p), str(t), str(f)) for p, t, f in rows]

    def translation_rows(self) -> list[TranslationRow]:
        return [_row(r) for r in self._conn.execute(_ROW_SQL + " ORDER BY f.path, e.idx").fetchall()]

    def translation_row(self, entry_id: int) -> TranslationRow:
        r = self._conn.execute(_ROW_SQL + " WHERE e.id = ?", (entry_id,)).fetchone()
        if r is None:
            raise ProjectError("Çeviri satırı bulunamadı; proje başka bir yerde değiştirilmiş olabilir.")
        return _row(r)

    def set_translations(
        self,
        changes: Iterable[tuple[int, str]],
        *,
        machine: bool = False,
        status: Status | None = None,
        overwrite_approved: bool = False,
        job: str = JOB_MANUAL,
        remember: bool = True,
    ) -> list[TranslationRow]:
        """Çevirileri tek işlemde yazar; her satırın durumu yer tutuculara göre belirlenir.

        Elle girilen geçerli çeviri "onaylandı", makine çevirisi (`machine=True`) "makine", dış redaksiyondan
        gelen düzeltme (`status=Status.REDACTED`) "redakte" olur. Makine çevirisi ve redaksiyon onaylanmış
        satıra yalnızca kullanıcı bunu açıkça istediyse (`overwrite_approved=True`) yazar. Geçerli çeviriler
        çeviri belleğine de yazılır; makine çevirisi bellekteki insan çevirisinin üzerine yazmaz.
        Metni değişen her satırın önceki hâli geçmişe `job` adıyla yazılır (geri alınabilsin).
        `remember=False` çeviri belleğine dokunmaz (yalnızca satır sonu yerleşimi değişen yeniden bölme gibi işler).
        """
        now = _now()
        ids = []
        before: dict[int, tuple[str, str, str]] = {}
        ok_status = status if status is not None else (Status.MACHINE if machine else Status.APPROVED)
        # Redaksiyon insan denetiminden geçmiş sayılır: çeviri belleğinde makine çevirisinin önüne geçer.
        origin = "human" if ok_status in (Status.APPROVED, Status.REDACTED) else "machine"
        with _Transaction(self._conn):
            for entry_id, text in changes:
                row = self._conn.execute(
                    "SELECT source, status, translation, note FROM text_entries WHERE id = ?", (entry_id,)
                ).fetchone()
                if row is None:
                    raise ProjectError("Çeviri satırı bulunamadı; proje başka bir yerde değiştirilmiş olabilir.")
                if ok_status != Status.APPROVED and row[1] == Status.APPROVED and not overwrite_approved:
                    continue  # makine çevirisi/redaksiyon insanın onayladığı satıra kendiliğinden yazmaz
                new_status, note = evaluate(row[0], text, ok_status)
                if row[2] != text:
                    self._record(entry_id, (row[2], row[1], row[3]), text, job=job, now=now)
                if (row[2], row[1], row[3]) != (text, new_status, note):
                    before.setdefault(entry_id, (row[2], row[1], row[3]))
                self._conn.execute(
                    "UPDATE text_entries SET translation = ?, status = ?, note = ?, updated_at = ? WHERE id = ?",
                    (text, new_status, note, now, entry_id),
                )
                if remember and new_status == ok_status and row[0]:
                    self._conn.execute(
                        "INSERT INTO memory (source, translation, origin, updated_at) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(source) DO UPDATE SET translation = excluded.translation, "
                        "origin = excluded.origin, updated_at = excluded.updated_at "
                        "WHERE excluded.origin = 'human' OR memory.origin = 'machine'",
                        (row[0], text, origin, now),
                    )
                ids.append(entry_id)
            self._conn.execute("UPDATE project SET updated_at = ?", (now,))
        self._push_undo(job, before)
        return [self.translation_row(i) for i in ids]

    def unapprove(self, entry_ids: Iterable[int]) -> list[TranslationRow]:
        """Onaylanmış satırları metnine dokunmadan "makine" durumuna döndürür (yanlışlıkla onaylananlar için).

        Böylece yeniden çeviri ve redaksiyon onlara "onaylananlara da uygula" gerekmeden uygulanır.
        """
        rows = [self.translation_row(i) for i in entry_ids]
        approved = [r for r in rows if r.status == Status.APPROVED]
        with _Transaction(self._conn):
            self._conn.executemany(
                "UPDATE text_entries SET status = ?, updated_at = ? WHERE id = ?",
                [(Status.MACHINE, _now(), r.id) for r in approved],
            )
        self._push_undo(JOB_UNAPPROVE, {r.id: (r.translation, r.status, r.note) for r in approved})
        return [self.translation_row(r.id) for r in rows]

    # --- geri alma (Ctrl+Z) -------------------------------------------------------------------

    def _push_undo(self, job: str, before: dict[int, tuple[str, str, str]]) -> None:
        """İşlemi geri alma yığınına ekler. Aynı makine işinin parça parça yazımları tek işlem sayılır."""
        if not before:
            return
        top = self._undo[-1] if self._undo else None
        if top is not None and top.job == job and job not in (JOB_MANUAL, JOB_REVERT, JOB_UNAPPROVE):
            self._undo[-1] = UndoStep(job, {**before, **top.before})  # her satırın işten önceki ilk hâli kalır
            return
        self._undo.append(UndoStep(job, before))
        del self._undo[:-UNDO_LIMIT]

    def undo_job(self) -> str | None:
        """Geri alınabilecek son işlemin iş adı; yoksa None."""
        return self._undo[-1].job if self._undo else None

    def undo(self) -> tuple[str, list[TranslationRow]] | None:
        """Son işlemi geri alır: satırlar işlemden önceki metin, durum ve açıklamaya döner.

        Metni değişen satırlar geçmişe "geri alma" olarak yazılır. Geri alınacak işlem yoksa None.
        """
        if not self._undo:
            return None
        step = self._undo[-1]
        now = _now()
        ids = []
        with _Transaction(self._conn):
            for entry_id, (text, status, note) in step.before.items():
                row = self._conn.execute(
                    "SELECT status, translation, note FROM text_entries WHERE id = ?", (entry_id,)
                ).fetchone()
                if row is None:
                    continue  # satır bu arada yeniden taramayla kalkmış
                if row[1] != text:
                    self._record(entry_id, (row[1], row[0], row[2]), text, job=JOB_REVERT, now=now)
                self._conn.execute(
                    "UPDATE text_entries SET translation = ?, status = ?, note = ?, updated_at = ? WHERE id = ?",
                    (text, status, note, now, entry_id),
                )
                ids.append(entry_id)
            self._conn.execute("UPDATE project SET updated_at = ?", (now,))
        self._undo.pop()
        return step.job, [self.translation_row(i) for i in ids]

    # --- çeviri geçmişi -----------------------------------------------------------------------

    def _record(self, entry_id: int, before: tuple[str, str, str], new: str, *, job: str, now: str) -> None:
        """Geçmişe yazar; `before` = (eski metin, eski durum, eski açıklama)."""
        self._conn.execute(
            "INSERT INTO history (entry_id, old_text, old_status, old_note, new_text, job, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry_id, *before, new, job, now),
        )

    _CHANGE_SQL = (
        "SELECT h.entry_id, CASE WHEN e.context != '' THEN e.context ELSE e.key END, e.source, h.old_text, "
        "h.old_status, h.old_note, h.new_text, h.job, h.created_at "
        "FROM history h JOIN text_entries e ON e.id = h.entry_id"
    )

    def job_changes(self, job: str) -> list[Change]:
        """Bir işte metni değişen satırlar: işten önceki ilk hâl → işin sonundaki son hâl (oyun sırasıyla).

        Sonradan geri alınmış (çevirisi yeniden işten önceki hâline dönmüş) satırlar listelenmez.
        """
        first: dict[int, Change] = {}
        last: dict[int, str] = {}
        for r in self._conn.execute(self._CHANGE_SQL + " WHERE h.job = ? ORDER BY h.id", (job,)):
            change = Change(*r)
            first.setdefault(change.entry_id, change)
            last[change.entry_id] = change.new_text
        order: dict[int, int] = {}
        current: dict[int, str] = {}
        for i, (eid, text) in enumerate(
            self._conn.execute(
                "SELECT e.id, e.translation FROM text_entries e JOIN text_files f ON f.id = e.file_id "
                "ORDER BY f.path, e.idx"
            )
        ):
            order[eid], current[eid] = i, text
        out = [
            replace(c, new_text=last[eid])
            for eid, c in first.items()
            if c.old_text != last[eid] and current.get(eid) != c.old_text
        ]
        return sorted(out, key=lambda c: order.get(c.entry_id, 0))

    def last_jobs(self) -> dict[int, str]:
        """Satır kimliği → çevirisini en son değiştiren iş (geçmişi olan satırlar)."""
        rows = self._conn.execute(
            "SELECT h.entry_id, h.job FROM history h "
            "JOIN (SELECT entry_id, MAX(id) AS id FROM history GROUP BY entry_id) m ON m.id = h.id"
        )
        return {int(eid): str(job) for eid, job in rows}

    def row_history(self, entry_id: int) -> list[Change]:
        """Bir satırın bütün değişiklikleri, en yeniden eskiye."""
        rows = self._conn.execute(self._CHANGE_SQL + " WHERE h.entry_id = ? ORDER BY h.id DESC", (entry_id,))
        return [Change(*r) for r in rows]

    def revert(self, changes: Iterable[Change]) -> list[TranslationRow]:
        """Değişiklikleri geri alır: satırlar değişiklikten önceki metin, durum ve açıklamaya döner.

        Geri alma da geçmişe yazılır (yeniden ileri alınabilsin). Çeviri belleğine dokunulmaz.
        """
        now = _now()
        ids = []
        before: dict[int, tuple[str, str, str]] = {}
        with _Transaction(self._conn):
            for c in changes:
                row = self._conn.execute(
                    "SELECT status, translation, note FROM text_entries WHERE id = ?", (c.entry_id,)
                ).fetchone()
                if row is None:
                    continue  # satır bu arada oyundan kalkmış
                before.setdefault(c.entry_id, (row[1], row[0], row[2]))
                if row[1] != c.old_text:
                    self._record(c.entry_id, (row[1], row[0], row[2]), c.old_text, job=JOB_REVERT, now=now)
                self._conn.execute(
                    "UPDATE text_entries SET translation = ?, status = ?, note = ?, updated_at = ? WHERE id = ?",
                    (c.old_text, c.old_status, c.old_note, now, c.entry_id),
                )
                ids.append(c.entry_id)
            self._conn.execute("UPDATE project SET updated_at = ?", (now,))
        self._push_undo(JOB_REVERT, before)
        return [self.translation_row(i) for i in ids]

    # --- çeviri belleği, sözlük, ayarlar ----------------------------------------------------

    def memory_lookup(self, sources: Iterable[str]) -> dict[str, tuple[str, str]]:
        """Kaynak metin → (çeviri, köken "human"/"machine")."""
        result: dict[str, tuple[str, str]] = {}
        unique = list(dict.fromkeys(sources))
        for i in range(0, len(unique), 500):
            chunk = unique[i : i + 500]
            marks = ",".join("?" * len(chunk))
            for src, tr, origin in self._conn.execute(
                f"SELECT source, translation, origin FROM memory WHERE source IN ({marks})",  # noqa: S608 - yalnızca ? işaretleri
                chunk,
            ):
                result[src] = (tr, origin)
        return result

    def memory_size(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0])

    def glossary(self) -> list[GlossaryTerm]:
        rows = self._conn.execute("SELECT term, translation, note FROM glossary ORDER BY id").fetchall()
        return [GlossaryTerm(t, tr, n) for t, tr, n in rows]

    def set_glossary(self, terms: Iterable[GlossaryTerm]) -> None:
        # Çevirisi boş ama notu olan madde "lore"dur: modele bilgi olarak gider, çeviriye zorlanmaz.
        clean = [t for t in terms if t.term.strip() and (t.translation.strip() or t.note.strip())]
        with _Transaction(self._conn):
            self._conn.execute("DELETE FROM glossary")
            self._conn.executemany(
                "INSERT INTO glossary (term, translation, note) VALUES (?, ?, ?)",
                [(t.term.strip(), t.translation.strip(), t.note.strip()) for t in clean],
            )
            self._conn.execute("UPDATE project SET updated_at = ?", (_now(),))

    def setting(self, key: str, default: str = "") -> str:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with _Transaction(self._conn):
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def uppercase_rules(self) -> UppercaseRules:
        return UppercaseRules.load(self.setting(GROUPS_KEY), self.setting(ROWS_KEY), self.setting(EXCEPT_KEY))

    def set_uppercase_rules(self, rules: UppercaseRules) -> None:
        groups, rows, excluded = rules.dump()
        with _Transaction(self._conn):
            for key, value in ((GROUPS_KEY, groups), (ROWS_KEY, rows), (EXCEPT_KEY, excluded)):
                self._conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
            self._conn.execute("UPDATE project SET updated_at = ?", (_now(),))

    def translation_counts(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Status}
        for status, n in self._conn.execute("SELECT status, COUNT(*) FROM text_entries GROUP BY status"):
            counts[status] = n
        return counts


class _Transaction:
    """`with _Transaction(conn):` — BEGIN IMMEDIATE … COMMIT, hata olursa ROLLBACK."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> None:
        self._conn.execute("BEGIN IMMEDIATE")

    def __exit__(self, exc_type: type[BaseException] | None, *_: object) -> None:
        if exc_type is None:
            try:
                self._conn.execute("COMMIT")
            except sqlite3.Error as exc:
                self._rollback()
                raise ProjectError(
                    "Proje dosyasına yazılamadı.", f"Disk dolu veya dosya kilitli olabilir. ({exc})"
                ) from None
        else:
            self._rollback()

    def _rollback(self) -> None:
        """ROLLBACK başarısız olursa asıl hata örtülmesin; yalnızca uyarı olarak günlüğe yazılır."""
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error as exc:
            log.warning("ROLLBACK başarısız oldu (işlem zaten geri alınmış olabilir): %s", exc)
