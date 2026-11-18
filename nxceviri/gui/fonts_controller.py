"""Font ve Görseller denetleyicisi: font taraması, font yaması/harf dönüştürme ayarları, düzenli font içe alma,
oyun resimlerini çıkarma.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Denetleyici durum tutmaz; proje, font raporu ve `busy` her
çağrıda pencereden okunur (`font_report` pencerede kalır). Pencerede yönlendirmesi olan her yöntem (`notify`, `_run`,
`_inputs`, `_mark_changed`, `_refresh_qa`, `_graphics`...) pencere üzerinden çağrılır; testler bu adları pencerede
değiştirir. Testlerin `nxceviri.gui.main_window` üzerinde değiştirdiği `opened_view`, `check_sources` ve
`member_reader` adları çağrı anında `_mw.<ad>` ile okunur. Font ayarlarını arayüze yansıtan `_refresh_qa` Kontrol Et
akışına ait olduğu için Kontrol Et denetleyicisindedir.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from nxceviri.core.errors import NxError
from nxceviri.core.formats.derived import GraphicsSupport, graphics_status
from nxceviri.core.formats.registry import plugin_for_kind
from nxceviri.core.progress import TaskContext
from nxceviri.core.qa import transliterate
from nxceviri.core.qa.fonts import FontReport, looks_like_font
from nxceviri.core.qa.fonts import scan_fonts as scan_font_files
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_INFO, LEVEL_SUCCESS, LEVEL_WARNING, NoticeAction
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

log = logging.getLogger(__name__)

#: İçe alınmış düzenli fontların proje ayarı anahtarı.
FONT_OVERRIDES_KEY = "font_overrides"


class FontsController:
    """Font ve görsel işleri; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win

    def _font_patch_on(self) -> bool:
        win = self._win
        return win.project.setting("font_patch") == "1" and bool(win._patchable_letters())

    def _stored_font_overrides(self) -> dict[str, str]:
        """İçe alınmış düzenli fontlar: RomFS yolu → kullanıcının dosyası (proje ayarı; bozuksa boş)."""
        win = self._win
        try:
            data = json.loads(win.project.setting(FONT_OVERRIDES_KEY) or "{}")
        except ValueError:
            log.warning("İçe alınan font ayarı bozuk; yok sayıldı")
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _save_font_overrides(self, overrides: dict[str, str]) -> None:
        win = self._win
        win.project.set_setting(FONT_OVERRIDES_KEY, json.dumps(overrides, ensure_ascii=False))
        win._mark_changed()
        win.qa_page.set_font_overrides(overrides)

    def _title_id_hex(self) -> str:
        """Modun klasör adı olan TitleID (metin dosyalarınınki; yoksa projeninki)."""
        win = self._win
        files = win.project.text_files()
        return str(files[0][1]) if files else win.project.title_id

    def _font_overrides(self) -> dict[str, dict[str, bytes]]:
        """Dışa aktarmada moda konacak düzenli fontlar; dosyası bulunamayan atlanır ve bildirilir."""
        win = self._win
        found: dict[str, bytes] = {}
        lost: list[str] = []
        for source, stored in win._stored_font_overrides().items():
            try:
                found[source] = Path(stored).read_bytes()
            except OSError:
                lost.append(Path(stored).name)
        if lost:
            win.notify(
                LEVEL_WARNING,
                "İçe alınan font bulunamadı",
                f"{', '.join(lost)} taşınmış ya da silinmiş; modda özgün font kalır.",
            )
        return {win._title_id_hex(): found} if found else {}

    def import_edited_font(self, source: str) -> None:
        """Kontrol Et → Font: dışarıda düzenlenen TTF/OTF dosyası, dışa aktarılan modda bu fontun yerine konur."""
        win = self._win
        start = str(win.settings.value("fonts/dir", str(Path.home())))
        path, _ = QFileDialog.getOpenFileName(
            win, "Düzenlenmiş fontu seçin", start, "Fontlar (*.ttf *.otf);;Tüm dosyalar (*)"
        )
        if not path:
            return
        win.settings.setValue("fonts/dir", str(Path(path).parent))
        if not looks_like_font(Path(path)):
            win.notify(LEVEL_ERROR, "Bu dosya bir font değil", "TTF ya da OTF dosyası seçin.")
            return
        overrides = win._stored_font_overrides()
        overrides[source] = path
        win._save_font_overrides(overrides)
        win.notify(
            LEVEL_SUCCESS,
            "Düzenlenmiş font içe alındı",
            f"{Path(path).name}, dışa aktarılan modda {source.rsplit('/', 1)[-1]} yerine kullanılacak.",
        )

    def reset_edited_font(self, source: str) -> None:
        win = self._win
        overrides = win._stored_font_overrides()
        if overrides.pop(source, None) is not None:
            win._save_font_overrides(overrides)
            win.notify(
                LEVEL_INFO, "Özgün fonta dönüldü", f"Modda oyunun özgün {source.rsplit('/', 1)[-1]} fontu kalır."
            )

    def export_font_file(self, source: str) -> None:
        """Seçili fontu oyun dosyalarından okuyup bir klasöre kaydeder (font düzenleyicide açmak için)."""
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        if win.busy:
            return
        problems = _mw.check_sources(win.sources)
        if win.keys is None or problems:
            win.notify(LEVEL_ERROR, "Font okunamadı", " ".join(problems) or "Önce anahtar dosyasını seçin.")
            return
        start = str(win.settings.value("fonts/dir", str(Path.home())))
        folder = QFileDialog.getExistingDirectory(win, "Fontun kaydedileceği klasörü seçin", start)
        if not folder:
            return
        win.settings.setValue("fonts/dir", folder)
        target = Path(folder) / source.rsplit("/", 1)[-1]
        inputs = win._inputs()

        def work(ctx: TaskContext) -> object:
            with _mw.opened_view(inputs, ctx) as view:
                for tree in view.trees:  # fontun bulunduğu içerik ağacı (oyun, DLC)
                    if source in tree.view.files:
                        data = tree.view.open(source).read_all()
                        break
                else:
                    raise NxError(f"Font oyun dosyalarında bulunamadı: {source}")
            target.write_bytes(data)
            return target

        def done(_result: object) -> None:
            win.notify(
                LEVEL_SUCCESS,
                "Font dışa aktarıldı",
                f"{target.name} kaydedildi. Düzenledikten sonra “Düzenlenmiş Fontu İçe Al” ile geri alın.",
                (NoticeAction("Klasörü Aç", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder))),),
            )

        win._run(work, "Font dışa aktarılıyor", on_success=done, on_failure=lambda _t: None)

    def _font_files(self) -> frozenset[str]:
        """Font yamasının uygulanacağı dosyalar (son font taramasından)."""
        win = self._win
        if win.font_report is not None:
            return frozenset(win.font_report.patch_files)
        try:
            files = json.loads(win.project.setting("font_files") or "[]")
        except ValueError:
            return frozenset()
        return frozenset(f for f in files if isinstance(f, str))

    def _patchable_letters(self) -> str:
        win = self._win
        if win.font_report is not None:
            return win.font_report.patchable_letters
        return win.project.setting("font_patchable")

    def _missing_letters(self) -> str:
        """Dönüştürülecek "eksik" harfler; font yaması açıksa yamanın ekleyeceği harfler hariç."""
        win = self._win
        patched = win._font_patch_on()
        if win.font_report is not None:
            return win.font_report.missing_letters(patched=patched)
        return win.project.setting("font_missing_patched" if patched else "font_missing")

    def _transliterate_letters(self) -> str:
        win = self._win
        mode = win.project.setting("transliterate_mode", transliterate.MODE_NONE)
        return transliterate.letters_for(mode, win._missing_letters())

    def scan_fonts(self) -> None:
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        if win.busy:
            return
        problems = _mw.check_sources(win.sources)
        if win.keys is None or problems or win.report is None:
            reason = " ".join(problems) or "Fontları taramak için anahtar dosyası ve tarama sonucu gerekli."
            win.qa_page.font_banner.show_message("danger", reason)
            return
        inputs = win._inputs()
        report = win.report

        def work(ctx: TaskContext) -> object:
            with _mw.opened_view(inputs, ctx) as view:
                return scan_font_files(view, report, ctx)

        def done(result: object) -> None:
            assert isinstance(result, FontReport)
            win.font_report = result
            try:
                win.project.set_setting("font_missing", result.missing_letters())
                win.project.set_setting("font_missing_patched", result.missing_letters(patched=True))
                win.project.set_setting("font_patchable", result.patchable_letters)
                win.project.set_setting("font_files", json.dumps(list(result.patch_files), ensure_ascii=False))
            except NxError as exc:
                win.notify(LEVEL_ERROR, "Proje", exc.user_text())
            win._mark_changed()
            win.qa_page.set_font_busy(False)
            win._refresh_qa()

        def failed(text: str) -> None:
            win.qa_page.set_font_busy(False)
            win.qa_page.font_banner.show_message("danger", text)

        win.qa_page.set_font_busy(True)
        win._run(
            work,
            "Fontlar taranıyor",
            on_success=done,
            on_failure=failed,
            on_cancel=lambda: win.qa_page.set_font_busy(False),
        )

    def _set_transliterate(self, mode: str) -> None:
        win = self._win
        try:
            win.project.set_setting("transliterate_mode", mode)
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return
        win._mark_changed()
        win.qa_page.set_mode(mode, win._missing_letters(), win._font_patch_on())
        win._sync_live()

    def _set_font_patch(self, enabled: bool) -> None:
        win = self._win
        try:
            win.project.set_setting("font_patch", "1" if enabled else "")
        except NxError as exc:
            win.notify(LEVEL_ERROR, "Proje", exc.user_text())
            return
        win._mark_changed()
        win._refresh_qa()

    def _graphics(self) -> tuple[GraphicsSupport, Path] | None:
        """Projenin oyunu resim çevirisini destekliyorsa (destek, klasör); klasör oyun dosyalarının yanındadır."""
        win = self._win
        if not win.sources:
            return None
        for _path, title_id, kind in win.project.text_files():
            support = getattr(plugin_for_kind(kind, title_id), "graphics", None)
            if isinstance(support, GraphicsSupport):
                return support, win.sources[0].path.parent / support.folder_name
        return None

    def _refresh_graphics(self) -> None:
        win = self._win
        found = win._graphics()
        if found is None:
            win.export_page.set_graphics(None, (0, 0))
            return
        win.export_page.set_graphics(found[1], graphics_status(found[1]))

    def extract_graphics(self) -> None:
        """Dışa Aktar → Görseller: yazı içeren resimlerin özgünlerini PNG olarak oyun klasörünün yanına çıkarır."""
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win
        found = win._graphics()
        if win.busy or found is None:
            return
        support, folder = found
        problems = _mw.check_sources(win.sources)
        if win.keys is None or problems:
            win.notify(LEVEL_ERROR, "Görseller çıkarılamadı", " ".join(problems) or "Önce anahtar dosyasını seçin.")
            return
        inputs = win._inputs()

        def work(ctx: TaskContext) -> object:
            names: list[str] = []
            with _mw.opened_view(inputs, ctx) as view:
                for tree in view.trees:
                    names += support.export(_mw.member_reader(tree), tree.view.files, folder)
            return names

        def done(result: object) -> None:
            assert isinstance(result, list)
            win._refresh_graphics()
            win.notify(
                LEVEL_SUCCESS,
                "Görseller çıkarıldı",
                f"{format_int(len(result))} resim orijinal/ klasöründe. Türkçesini turkce/ klasörüne aynı adla koyun.",
                (NoticeAction("Klasörü Aç", win.open_graphics),),
            )

        win._run(work, "Görseller çıkarılıyor", on_success=done, on_failure=lambda _t: None)

    def open_graphics(self) -> None:
        win = self._win
        found = win._graphics()
        if found is None:
            return
        found[1].mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(found[1])))
