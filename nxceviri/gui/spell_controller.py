"""Yazım denetimi denetleyicisi: Yazım Denetimi penceresi, sözcük değiştirme, kullanıcı sözlüğü.

Ana pencereden ayrılmıştır (`ARCHITECTURE.md` karar 221). Denetleyici durum tutmaz; `_spell_window`, `_spell_timer`,
`spell`, `user_dictionary`, `_spell_cache`, `_spell_hints`, `_spell_extra_key` ve `_spell_scan` pencerede durur ve
her çağrıda pencereden okunur (testler bunları pencerede kurar). Pencerede yönlendirmesi olan her yöntem, bu
denetleyicinin kendi yöntemleri dahil, pencere üzerinden çağrılır (`self._win.<ad>`). Testlerin pencere modülünde
değiştirdiği `replace_unknown` ile `SPELL_SYNC_ROWS` ve `_preview` pencere modülü üzerinden okunur. Zamanlayıcının
`timeout` bağlantısı ve Çeviri/Kontrol Et sayfalarının sinyal bağlantıları pencerede kalır.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nxceviri.core.progress import TaskContext
from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import glossary_words, spell_extra_words
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.loader import load_spell_checker
from nxceviri.core.spell.report import UnknownWordCache
from nxceviri.core.spell.suggest import Suggestion, suggestions
from nxceviri.gui.notify import LEVEL_ERROR
from nxceviri.gui.spell_dialogs import AddSpellWordsDialog, UserDictionaryDialog
from nxceviri.gui.spell_window import SpellWindow
from nxceviri.gui.tasks import Task, release_thread
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow


class SpellController:
    """Yazım denetimi penceresi ve sözlük işleri; pencere bunun yöntemlerine ince yönlendirmelerle bağlanır."""

    def __init__(self, win: MainWindow) -> None:
        self._win = win

    def open_spell_window(self) -> None:
        """Araçlar → Yazım Denetimi: kipsiz tek pencere; açıksa öne gelir."""
        if self._win.spell is None or not self._win.translate_page.model.rows:
            return
        win = self._win._spell_window
        if win is None:
            win = SpellWindow(self._win)
            win.show_row.connect(self._win._open_row)
            win.ignore_requested.connect(self._win.ignore_spell_words)
            win.add_requested.connect(self._win._add_from_spell_window)
            win.replace_requested.connect(self._win._replace_spell_word)
            win.fix_all_requested.connect(self._win._fix_spell_words)
            win.suggest_fn = self._win._spell_hint
            self._win._spell_window = win
        self._win._refresh_spell_window(force=True)
        win.show()
        win.raise_()
        win.activateWindow()

    def _refresh_spell_window(self, force: bool = False) -> None:
        """Pencere görünürken (ya da `force`) sözcük listesini güncel satırlardan kurar."""
        # Döngüsel içe aktarma; testler bu adları pencere modülünde değiştirir.
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        win = self._win._spell_window
        if win is None or not (force or win.isVisible()):
            return
        if self._win.spell is None:
            win.set_words([])
            return
        rows = self._win.translate_page.model.rows
        extra = glossary_words(self._win.project.glossary())
        if extra != self._win._spell_extra_key:
            self._win._spell_cache.clear()
            self._win._spell_hints.clear()
            self._win._spell_extra_key = extra
        stale = self._win._spell_cache.stale(rows)
        if len(stale) > _mw.SPELL_SYNC_ROWS:
            win.set_scanning(True)
            self._win._start_spell_scan(stale, self._win.spell, extra)
            return
        self._win._spell_cache.store(self._win._spell_cache.scan(stale, self._win.spell, extra))
        words = self._win._spell_cache.words(rows, self._win._spell_ignored())
        wanted = {i for w in words for i in w.row_ids}
        previews = {r.id: _mw._preview(r.translation) for r in rows if r.id in wanted}
        win.set_words(words, previews)

    def _start_spell_scan(self, stale: list[TranslationRow], spell: SpellChecker, extra: frozenset[str]) -> None:
        """Çok sayıda satırı arka planda tarar (aynı anda tek tarama); biterken pencere yeniden tazelenir."""
        # Döngüsel içe aktarma; testler bu adları pencere modülünde değiştirir.
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        if self._win._spell_scan is not None:
            return  # sürüyor: bitince kalan değişen satırlar için yeniden başlatılır

        def work(ctx: TaskContext) -> object:
            scanned: dict[int, tuple[TranslationRow, tuple[str, ...]]] = {}
            for start in range(0, len(stale), _mw.SPELL_SYNC_ROWS):
                ctx.check()
                scanned |= UnknownWordCache.scan(stale[start : start + _mw.SPELL_SYNC_ROWS], spell, extra)
            return scanned

        owner = self._win.project

        def done(result: object) -> None:
            assert isinstance(result, dict)
            # Tarama sürerken proje ya da sözlük değiştiyse sonuç atılır (satır kimlikleri başka projeye karışmaz).
            if owner is self._win.project and spell is self._win.spell and extra == self._win._spell_extra_key:
                self._win._spell_cache.store(result)
            self._win._spell_scan_ok = True

        scan = Task(work, "Yazım taraması")
        self._win._spell_scan = scan
        self._win._spell_scan_ok = False
        scan.succeeded.connect(done)
        scan.finished.connect(self._win._spell_scan_finished)
        scan.start()

    def _spell_scan_finished(self) -> None:
        scan, self._win._spell_scan = self._win._spell_scan, None
        if scan is not None:
            release_thread(scan)
        if self._win._spell_scan_ok:
            self._win._refresh_spell_window()  # tarama sürerken değişen satırlar için
        elif self._win._spell_window is not None:
            self._win._spell_window.set_scanning(False)

    def _add_from_spell_window(self, words: list[str]) -> None:
        self._win.add_spell_words([str(w) for w in words])
        self._win._refresh_spell_window()

    def _spell_hint(self, word: str, edits: bool) -> Suggestion:
        """Pencerenin öneri kaynağı: yazım sözlüğü ve oyun sözlüğüyle üretilir, sözcük başına bellekte tutulur."""
        key = (word, edits)
        found = self._win._spell_hints.get(key)
        if found is None:
            if self._win.spell is None:
                return Suggestion()
            extra = self._win._spell_extra_key if self._win._spell_extra_key is not None else frozenset()
            found = self._win._spell_hints[key] = suggestions(word, self._win.spell, extra, edits=edits)
        return found

    def _spell_word_rows(self, words: list[str]) -> dict[str, list[TranslationRow]] | None:
        """Her sözcüğün geçtiği satırlar (pencerenin listelediği geçişler); yalnızca değişen satırlar taranır.

        Tarama büyük bir değişiklikten sonra arka planda sürüyorsa `None` döner ve neden durum çubuğunda söylenir.
        """
        # Döngüsel içe aktarma; testler bu adları pencere modülünde değiştirir.
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        spell = self._win.spell
        if spell is None:
            return None
        rows = self._win.translate_page.model.rows
        extra = glossary_words(self._win.project.glossary())
        if extra != self._win._spell_extra_key:
            self._win._spell_cache.clear()
            self._win._spell_hints.clear()
            self._win._spell_extra_key = extra
        stale = self._win._spell_cache.stale(rows)
        if len(stale) > _mw.SPELL_SYNC_ROWS:
            self._win.statusBar().showMessage("Sözcükler taranıyor; tarama bitince yeniden deneyin.", 5000)
            return None
        self._win._spell_cache.store(self._win._spell_cache.scan(stale, spell, extra))
        by_id = {r.id: r for r in rows}
        return {w: [by_id[i] for i in ids if i in by_id] for w, ids in self._win._spell_cache.row_ids(words).items()}

    def _spell_changes(self, pairs: list[tuple[str, str]]) -> list[tuple[int, str]] | None:
        """Sözcük çiftlerinin yalnızca geçtiği satırlardaki değişiklikleri; her satır için tek yeni metin.

        Kaynakta da geçen, tamamı büyük harfli, özel ad ve çevrilmemiş kopya geçişlere dokunulmaz (pencere de
        bunları saymaz); böylece değişen satır sayısı penceredeki sayıyla aynıdır.
        """
        # Döngüsel içe aktarma; testler bu adları pencere modülünde değiştirir.
        from nxceviri.gui import main_window as _mw  # noqa: PLC0415

        spell = self._win.spell
        found = self._win._spell_word_rows([old for old, _new in pairs])
        if spell is None or found is None:
            return None
        extra = glossary_words(self._win.project.glossary())
        texts: dict[int, str] = {}
        for old, new in pairs:
            for row in found[old]:
                text = _mw.replace_unknown(
                    texts.get(row.id, row.translation), row.source, spell, extra, word=old, new=new
                )
                if text != row.translation:
                    texts[row.id] = text
        return list(texts.items())

    def _replace_spell_word(self, old: str, new: str) -> None:
        """Sözcüğü pencerenin listelediği geçişlerde değiştirir; tek iştir, Geri Al hepsini geri alır."""
        self._win._apply_spell_changes([(old, new)])

    def _fix_spell_words(self, pairs: list[tuple[str, str]]) -> None:
        """ "Tek önerisi olanları düzelt": bütün çiftler tek işte uygulanır; onaylı satırlar onaylı kalır."""
        self._win._apply_spell_changes([(str(old), str(new)) for old, new in pairs])

    def _apply_spell_changes(self, pairs: list[tuple[str, str]]) -> None:
        if not pairs or self._win.spell is None:
            return
        if self._win.busy:
            self._win.statusBar().showMessage("Bir iş sürerken değiştirilemez; iş bitince yeniden deneyin.", 5000)
            return
        changes = self._win._spell_changes(pairs)
        if not changes:
            return
        rows = self._win._replace_translations(changes)
        if rows is None:
            return  # neden Çevir sayfasında bildirildi
        self._win.statusBar().showMessage(f"{format_int(len(changes))} satırda değiştirildi.", 5000)
        self._win._refresh_spell_window()  # pano, tablonun `rows_updated` bildirimiyle yenilenir

    def _sync_spell(self) -> None:
        """Editördeki yazım işaretlerini güncel denetleyici ve oyun sözlüğüyle yeniler."""
        self._win._spell_cache.clear()  # sözlük ya da yoksayılanlar değişti
        self._win._spell_hints.clear()
        self._win.translate_page.set_spell(
            self._win.spell, spell_extra_words(self._win.project.glossary(), self._win._spell_ignored())
        )
        self._win._sync_live(force=True)
        self._win.update_menu_state()
        self._win._refresh_spell_window()

    def add_spell_words(self, words: list[str]) -> None:
        """Sözcükleri kalıcı kullanıcı sözlüğüne ekler; editör ve (yapıldıysa) denetim sonucu yenilenir."""
        try:
            added = self._win.user_dictionary.add(words)
        except OSError as exc:
            self._win.notify(LEVEL_ERROR, "Yazım sözlüğü", f"Sözlük kaydedilemedi: {exc.strerror or exc}")
            return
        if self._win.spell is not None:
            self._win.spell.add_user_words(words)
        self._win._sync_spell()
        self._win.statusBar().showMessage(f"{format_int(added)} sözcük yazım sözlüğüne eklendi.", 5000)
        self._win._recheck_if_done()

    def add_spelling_from_qa(self, words: list[str]) -> None:
        dialog = AddSpellWordsDialog(self._win, [str(w) for w in words])
        if dialog.exec() == AddSpellWordsDialog.DialogCode.Accepted and dialog.selected():
            self._win.add_spell_words(dialog.selected())

    def edit_user_dictionary(self) -> None:
        dialog = UserDictionaryDialog(self._win, self._win.user_dictionary)
        dialog.exec()
        if dialog.removed:
            self._win.spell = load_spell_checker(self._win.user_dictionary)
            self._win._apply_spell_copied()
            self._win._sync_spell()
            self._win._recheck_if_done()
