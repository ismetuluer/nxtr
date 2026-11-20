"""Kontrol Et → Grafik denetleyicisi: klasörü bulma ve seçme, arka planda denetim, klasör izleme, onay kaydı.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221 düzeni; karar 231). Denetleyici Qt nesnesi değildir;
pencereyi tutar, pencerede yönlendirmesi olan yöntemleri pencere üzerinden çağırır (`win._graphics()`,
`win._mark_changed()`, `win.extract_graphics()`; testler bunları pencerede değiştirir). Kendi durumunu (son sonuçlar,
arka plan işi, izleyici, zamanlayıcı) tutar; izleyici ve zamanlayıcı pencerenin çocuğudur.

Denetim pencerenin tek-iş kilidini (`win.task`) tutmaz (yazım taraması gibi): kullanıcı resim kaydederken başka iş
sürebilir. Denetim yalnızca sekme görünürken başlar; görünmezken değişiklik "bayat" olarak işaretlenir ve sekme
açılınca denetlenir. Böylece açılışta ve sekmeye hiç bakılmayan oturumlarda iş parçacığı açılmaz.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QFileSystemWatcher, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from nxceviri.core.errors import NxError
from nxceviri.core.formats import derived
from nxceviri.core.formats.derived import GraphicsSupport
from nxceviri.core.progress import TaskContext
from nxceviri.core.qa import graphics
from nxceviri.core.qa.graphics import IMAGE_SUFFIXES, GraphicsItem, summary
from nxceviri.gui.graphics_check import (
    BADGE_APPROVED,
    BADGE_ERROR,
    BADGE_MISSING,
    BADGE_READY,
    BADGE_UNCHANGED,
    BADGE_WARNING,
    PAGE_ERROR,
    PROBLEM_BADGES,
    GraphicsRow,
)
from nxceviri.gui.notify import LEVEL_ERROR
from nxceviri.gui.step_nav import STEP_QA
from nxceviri.gui.tasks import Task, release_thread
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

log = logging.getLogger(__name__)

#: Elle seçilen grafik klasörü (proje ayarı; oyunun eklentisi klasör bildirmiyorsa kullanılır).
FOLDER_KEY = "graphics/folder"
#: Onaylanan resimler: {ad: Türkçe dosyanın sha1'i} (proje ayarı, JSON).
APPROVED_KEY = "graphics/approved"
#: Klasör değişikliklerinin toplandığı süre (ms): resim düzenleyicisi kaydederken birkaç olay art arda gelir.
WATCH_DEBOUNCE_MS = 300
#: İzleyicinin tetiklediği denetimde dosya okunamazsa (yarım yazılmış) en çok bu kadar kez yeniden denenir.
WATCH_RETRIES = 3

INFO_NO_SUPPORT = "Bu oyunda resimler moda kendiliğinden yerleşmez; burada yalnızca karşılaştırılır."
ORIGINAL_DIR = "orijinal"


@dataclass(frozen=True)
class _ReadFailed:
    """Denetim sırasında bir dosya okunamadı (ör. resim düzenleyicisi hâlâ yazıyor)."""

    reason: str


@dataclass(frozen=True)
class _Source:
    folder: Path
    support: GraphicsSupport | None


def badge(item: GraphicsItem, approved: dict[str, str]) -> tuple[str, str]:
    """Resmin rozeti ve rengi. Öncelik: Eksik, Hata, Onaylandı, Değişmemiş, Uyarı, Hazır.

    Onay yalnızca kayıtlı özet güncel Türkçe dosyanınkiyle aynıysa geçerlidir; dosya değişince kendiliğinden düşer.
    Hata onayla örtülmez (hatalı resim onaylanamaz)."""
    if item.state == "missing":
        return BADGE_MISSING, "neutral"
    if any(issue.severity == "error" for issue in item.issues):
        return BADGE_ERROR, "danger"
    if item.digest and approved.get(item.name) == item.digest:
        return BADGE_APPROVED, "success"
    if item.state == "unchanged":
        return BADGE_UNCHANGED, "warning"
    if item.issues:
        return BADGE_WARNING, "warning"
    return BADGE_READY, "info"


def _approvable(item: GraphicsItem) -> bool:
    return bool(item.digest) and item.turkish is not None and not any(i.severity == "error" for i in item.issues)


def _has_images(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    return any(p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES for p in folder.iterdir())


class GraphicsController:
    """Grafik sekmesinin iş akışı; pencere `self.graphics_check` olarak tutar."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win
        #: Süren arka plan denetimi (pencerenin `task`ından ayrı).
        self.task: Task | None = None
        #: Son başarılı denetimin sonuçları; None: henüz denetlenmedi ya da klasör değişti.
        self.items: list[GraphicsItem] | None = None
        self._generation = 0
        self._again = False
        self._stale = True
        self._quiet = False
        self._retries = 0
        self._folder_key: Path | None = None
        #: Klasör değişiklikleri bu zamanlayıcıda toplanır (her olay yeniden başlatır).
        self.timer = QTimer(win)
        self.timer.setSingleShot(True)
        self.timer.setInterval(WATCH_DEBOUNCE_MS)
        self.timer.timeout.connect(self._watch_due)
        #: Dosyaları değil klasörleri izler: düzenleyiciler kaydederken dosyayı silip yeniden yazabilir.
        self.watcher = QFileSystemWatcher(win)
        self.watcher.directoryChanged.connect(lambda _path: self.timer.start())

    # --- klasör -------------------------------------------------------------------------

    def source(self) -> _Source | None:
        """Grafik klasörü: oyunun eklentisinin klasörü, yoksa projede elle seçilen klasör, yoksa None."""
        win = self._win
        found = win._graphics()
        if found is not None:
            return _Source(found[1], found[0])
        stored = win.project.setting(FOLDER_KEY)
        return _Source(Path(stored), None) if stored else None

    def _watch(self) -> bool:
        """İzlenen klasörleri günceller (yalnızca var olanlar); küme değiştiyse True."""
        source = self.source()
        wanted: set[str] = set()
        if source is not None:
            for path in (source.folder, source.folder / ORIGINAL_DIR, derived.turkish_dir(source.folder)):
                if path.is_dir():
                    wanted.add(str(path))
        current = set(self.watcher.directories())
        if wanted == current:
            return False
        if current - wanted:
            self.watcher.removePaths(sorted(current - wanted))
        if wanted - current:
            self.watcher.addPaths(sorted(wanted - current))
        return True

    def visible(self) -> bool:
        win = self._win
        return win.nav.currentRow() == STEP_QA and win.qa_page.tabs.currentWidget() is win.qa_page.graphics

    # --- tetikleyiciler -----------------------------------------------------------------

    def shown(self) -> None:
        """Sekme ya da Kontrol Et adımı açıldı: bayatsa denetlenir."""
        if self.visible() and not self.sync_folder():  # klasör değiştiyse sync_folder görünümü zaten günceller
            self._update(check=self._stale or self.items is None)

    def sync_folder(self) -> bool:
        """Klasör değişmiş olabilir (proje, görsel çıkarma, Dışa Aktar sayfası): izleyici ve görünüm güncellenir.

        Klasör ve izlenen alt klasörler aynıysa bir şey yapılmaz (Dışa Aktar sayfası her açılışta çağırır);
        görünüm güncellendiyse True."""
        source = self.source()
        folder = source.folder if source is not None else None
        changed = folder != self._folder_key
        if changed:
            self._folder_key = folder
            self.items = None
            self._generation += 1
            self._set_count(0)  # önceki klasörün sorun sayısı başlıkta kalmasın
        if self._watch() or changed:
            self._stale = True
            self._update(check=self.visible())
            return True
        return False

    def project_replaced(self) -> None:
        """Başka proje açıldı: süren denetim durdurulup beklenir, sonuçlar atılır, klasör yeniden bulunur."""
        self.timer.stop()
        self._stop_task()
        self.items = None
        self._folder_key = None
        self._stale = True
        self._retries = 0
        self._set_count(0)
        if not self.sync_folder():
            self._update(check=self.visible())

    def shutdown(self) -> None:
        """Pencere kapanıyor: izleyici ve zamanlayıcı durur, süren denetim iptal edilip beklenir."""
        self.timer.stop()
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        self._stop_task()

    def _stop_task(self) -> None:
        """Süren denetimi iptal edip bekler ve bırakır; geç gelen sonucu ve bitiş sinyali yok sayılır."""
        self._generation += 1
        self._again = False
        task, self.task = self.task, None
        if task is not None:
            task.cancel()
            release_thread(task)  # bekler: iptal resim başına denetlenir, kısa sürer

    def _watch_due(self) -> None:
        """Klasörde değişiklik (toplanmış): yeniden izlenir, sekme görünürse sessizce yeniden denetlenir."""
        self._watch()
        self._stale = True
        if self.visible():
            self.check(quiet=True)

    def refresh(self) -> None:
        """Yenile düğmesi: her zaman yeniden denetler; okuma hatası gösterilir."""
        self._retries = 0
        self.sync_folder()
        self.check(quiet=False)

    # --- görünüm ------------------------------------------------------------------------

    def _update(self, *, check: bool) -> None:
        """Sekmenin durum sayfasını klasöre göre seçer; `check` ise ve klasör hazırsa denetimi başlatır."""
        tab = self._win.qa_page.graphics
        source = self.source()
        tab.set_info(INFO_NO_SUPPORT if source is None or source.support is None else "")
        tab.set_can_choose(source is None or source.support is None)
        if source is None:
            self._set_count(0)
            tab.show_no_folder()
            return
        if source.support is None and not source.folder.is_dir():
            self._set_count(0)
            tab.show_no_folder(
                f"Seçilen klasör bulunamadı: {source.folder}. Taşındıysa ya da silindiyse yeniden seçin."
            )
            return
        if not _has_images(source.folder / ORIGINAL_DIR):
            self._set_count(0)
            tab.show_no_originals(source.folder, can_extract=source.support is not None)
            return
        if check:
            self.check(quiet=False)
        elif self.items is not None:
            self._render()

    def _set_count(self, count: int, missing: int | None = None) -> None:
        """Sekme başlığındaki sorun sayısı ve karo rozeti; `missing` yoksa resimler denetlenmemiştir (rozet yok)."""
        self._win.qa_page.set_graphics_count(count)
        self._win.qa_page.set_graphics_status(None if missing is None else (count, missing))

    def _approved(self) -> dict[str, str]:
        try:
            data = json.loads(self._win.project.setting(APPROVED_KEY) or "{}")
        except ValueError:
            log.warning("Grafik onay ayarı bozuk; yok sayıldı")
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def rows(self) -> list[GraphicsRow]:
        approved = self._approved()
        result = []
        for item in self.items or []:
            text, state = badge(item, approved)
            result.append(GraphicsRow(item, text, state, text == BADGE_APPROVED, _approvable(item)))
        return result

    def _render(self) -> None:
        rows = self.rows()
        items = self.items or []
        totals = summary(items)
        problems = sum(1 for row in rows if row.badge in PROBLEM_BADGES)
        approved = sum(1 for row in rows if row.approved)
        parts = [
            f"{format_int(totals.ready)} / {format_int(totals.total_originals)} hazır",
            f"{format_int(problems)} sorun",
            f"{format_int(totals.missing)} eksik",
        ]
        if approved:
            parts.append(f"{format_int(approved)} onaylı")
        self._win.qa_page.graphics.set_results(rows, " · ".join(parts))
        self._set_count(problems, totals.missing)

    # --- denetim ------------------------------------------------------------------------

    def check(self, *, quiet: bool = False) -> None:
        """Denetimi arka planda başlatır. Biri sürüyorsa iptal edilir, bitince yenisi başlar (eski sonuç atılır).

        `quiet`: izleyicinin tetiklediği denetim; dosya okunamazsa önceki liste kalır ve kısa süre sonra yeniden
        denenir (resim düzenleyicisi dosyayı yazarken)."""
        source = self.source()
        if source is None or not _has_images(source.folder / ORIGINAL_DIR):
            self._update(check=False)
            return
        self._quiet = quiet
        self._generation += 1
        if self.task is not None:
            self.task.cancel()
            self._again = True
            return
        self._start(source.folder)

    def _start(self, folder: Path) -> None:
        tab = self._win.qa_page.graphics
        if self.items is None:
            tab.show_loading()
        else:
            tab.set_checking(True)
        self._stale = False
        original_dir, turkish_dir = folder / ORIGINAL_DIR, derived.turkish_dir(folder)
        generation = self._generation
        owner = self._win.project

        def work(ctx: TaskContext) -> object:
            try:
                return graphics.check_folders(original_dir, turkish_dir, cancel=lambda: ctx.token.cancelled)
            except OSError as exc:  # yarım yazılmış ya da kilitli dosya; çekirdek okuma hatasını yükseltir
                return _ReadFailed(exc.strerror or str(exc))

        def done(result: object) -> None:
            if generation != self._generation or owner is not self._win.project:
                return  # bayat: klasör, proje ya da istek değişti
            if isinstance(result, _ReadFailed):
                self._read_failed(result.reason)
                return
            assert isinstance(result, list)
            self._retries = 0
            self.items = result
            self._render()

        def failed(text: str) -> None:
            if generation == self._generation and owner is self._win.project:
                self._win.qa_page.graphics.show_error(text)
                self._set_count(0)

        task = Task(work, "Grafik denetimi")
        self.task = task
        task.succeeded.connect(done)
        task.failed.connect(failed)
        task.finished.connect(lambda t=task: self._finished(t))
        task.start()

    def _read_failed(self, reason: str) -> None:
        tab = self._win.qa_page.graphics
        if self._quiet and self.items is not None and self._retries < WATCH_RETRIES:
            self._retries += 1
            self._stale = True
            self._render()  # sayaç satırı "Denetleniyor…"dan geri döner; liste aynı kalır
            self.timer.start()
            return
        self._retries = 0
        tab.show_error(
            f"Bir resim okunamadı ({reason}). Resim başka bir programda açıksa kaydetmeyi bitirip Yenile'ye basın."
        )
        self._set_count(0)

    def _finished(self, task: Task) -> None:
        if task is not self.task:
            return  # `_stop_task` durdurup bıraktı
        self.task = None
        release_thread(task)
        if self._again:
            self._again = False
            source = self.source()
            if source is not None and _has_images(source.folder / ORIGINAL_DIR):
                self._start(source.folder)
            else:
                self._update(check=False)
        elif self.items is not None and self._win.qa_page.graphics.page() != PAGE_ERROR:
            self._win.qa_page.graphics.set_checking(False)

    # --- kullanıcı işlemleri ------------------------------------------------------------

    def choose_folder(self) -> None:
        """Klasör Seç…: `orijinal/` ve `turkce/` (ya da eski `temiz/`) içeren klasör projeye kaydedilir."""
        win = self._win
        start = win.project.setting(FOLDER_KEY) or str(win.settings.value("graphics/dir", str(Path.home())))
        path = QFileDialog.getExistingDirectory(win, "Grafik klasörünü seçin", start)
        if not path:
            return
        folder = Path(path)
        win.settings.setValue("graphics/dir", str(folder.parent))
        has_turkish = (folder / derived.TURKISH_DIR).is_dir() or (folder / derived.LEGACY_TURKISH_DIR).is_dir()
        if not (folder / ORIGINAL_DIR).is_dir() or not has_turkish:
            win.notify(
                LEVEL_ERROR,
                "Bu klasör grafik klasörü değil",
                f"{folder.name} içinde {ORIGINAL_DIR}/ ve {derived.TURKISH_DIR}/ klasörleri olmalı: özgün resimler "
                f"{ORIGINAL_DIR}/, Türkçeleri aynı adla {derived.TURKISH_DIR}/ içinde durur.",
            )
            return
        try:
            win.project.set_setting(FOLDER_KEY, str(folder))
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return
        win._mark_changed()
        self._retries = 0
        self.sync_folder()

    def open_folder(self) -> None:
        source = self.source()
        if source is None:
            return
        source.folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(source.folder)))

    def extract(self) -> None:
        self._win.extract_graphics()

    def toggle_approval(self, name: str) -> None:
        """Onayla / Onayı Kaldır: onay, Türkçe dosyanın o anki özetiyle saklanır."""
        win = self._win
        item = next((i for i in self.items or [] if i.name == name), None)
        if item is None:
            return
        approved = self._approved()
        if item.digest and approved.get(name) == item.digest:
            del approved[name]
        elif _approvable(item):
            approved[name] = item.digest
        else:
            return
        try:
            win.project.set_setting(APPROVED_KEY, json.dumps(approved, ensure_ascii=False, sort_keys=True))
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return
        win._mark_changed()
        self._render()
