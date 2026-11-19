"""Zamanlayıcı denetleyicisi: haftalık takvimde seçilen saatlerde otomatik çeviri ya da redaksiyonu başlatır.

Yalnızca program ve proje açıkken, proje bir dosyaya kaydedilmişse çalışır. Her dakika (`CHECK_MS`) saat yeniden
okunur (`clock`; testlerde sahte saat verilir) ve şu kurallar uygulanır (`ARCHITECTURE.md` karar 237):

- Dilim etkin, başka iş ve açık pencere yoksa iş, Otomatik Çeviri'nin penceresiz yolu (`_launch_machine`) ile
  zamanlayıcının hizmet ayarlarıyla başlar. Meşgulse dilim içinde boşalınca başlar.
- Dilim bitince (ya da zamanlayıcı kapatılınca) yalnızca zamanlayıcının başlattığı iş güvenli iptal yoluyla durur:
  süren parti biter, yapılanlar kaydedilir. Kullanıcının başlattığı işe dokunulmaz.
- Bir dilimde iş bir kez tamamlanır: bitince, durdurulunca ya da yapılacak satır yoksa sonraki dilime kadar bekler
  (atlanan/aynı kalan satırlar için dakikada bir yeniden başlama döngüsü olmaz).
- İş hata verirse (bağlantı yok, hizmet yanıt vermiyor…) `RETRY_DELAY` sonra yeniden denenir, dilim başına en çok
  `MAX_RETRIES` kez; sonra bildirimle sonraki dilime kalır. Anahtar gerektiren hizmette kayıtlı anahtar yoksa
  yeniden denenmez, bildirilir.
- Proje değişince durum sıfırlanır.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from nxceviri.core.errors import NxError
from nxceviri.core.project import Project
from nxceviri.core.secrets import api_key_name
from nxceviri.core.translate.providers.catalog import spec
from nxceviri.core.translate.runner import ACTION_REVISE, RunSummary
from nxceviri.core.translate.schedule import SCHEDULE_KEY, Schedule, format_slot, scheduled_rows
from nxceviri.gui.jobs import JOB_TITLES
from nxceviri.gui.machine_controller import (
    OUTCOME_FAILED,
    OUTCOME_SETUP,
    TRANSLATE_INSTRUCTION_KEY,
)
from nxceviri.gui.machine_dialogs import PROVIDER_OLLAMA, MachineSettings
from nxceviri.gui.notify import LEVEL_ERROR, LEVEL_INFO, LEVEL_WARNING
from nxceviri.gui.widgets import format_int

if TYPE_CHECKING:
    from nxceviri.gui.main_window import MainWindow

#: Denetim aralığı (ms).
CHECK_MS = 60_000
#: Hata veren işin yeniden denenmesinden önceki bekleme ve dilim başına en çok yeniden deneme.
RETRY_DELAY = timedelta(minutes=15)
MAX_RETRIES = 3
#: Zamanlayıcının bildirim başlıklarının öneki.
PREFIX = "Zamanlayıcı: "


class ScheduleController(QObject):
    """Zamanlayıcının durumu ve iş akışı; pencere `scheduler` adıyla tutar."""

    def __init__(self, win: MainWindow, clock: Callable[[], datetime] = datetime.now) -> None:
        super().__init__(win)
        self._win = win
        #: Şimdiki yerel saat (testlerde değiştirilir).
        self.clock = clock
        self._project: Project | None = None
        self._slot: datetime | None = None
        self._done = False  # bu dilimde iş tamamlandı / durduruldu / yapılacak yok / vazgeçildi
        self._failures = 0
        self._retry_at: datetime | None = None
        self._task: object | None = None  # zamanlayıcının başlattığı iş (pencerenin `task`ı)
        self.timer = QTimer(self)
        self.timer.setInterval(CHECK_MS)
        self.timer.timeout.connect(self.tick)

    # --- ayar -----------------------------------------------------------------------------

    def schedule(self) -> Schedule:
        """Projede saklanan ayar; yoksa (ya da bozuksa) Otomatik Çeviri'de son kullanılan hizmetle boş takvim."""
        stored = Schedule.load(self._win.project.setting(SCHEDULE_KEY))
        if stored is not None:
            return stored
        provider = str(self._win.settings.value("translate/provider", PROVIDER_OLLAMA))
        url, model = self._win.machine.remembered_providers().get(spec(provider).id, ("", ""))
        return Schedule(provider=spec(provider).id, model=model, base_url=url)

    def save(self, schedule: Schedule) -> bool:
        try:
            self._win.project.set_setting(SCHEDULE_KEY, schedule.dump())
        except NxError as exc:
            self._win.notify(LEVEL_ERROR, "Zamanlayıcı kaydedilemedi", exc.user_text())
            return False
        self._win._mark_changed()
        self.tick()
        return True

    def dialog_options(self) -> dict[str, Any]:
        """Zamanlayıcı penceresinin ortak bağımlılıkları (gizli depo, sağlayıcı kurucu, hizmet hafızası, saat)."""
        win = self._win
        return {
            "secrets": win.secrets,
            "provider_factory": win.provider_factory,
            "remembered": win.machine.remembered_providers(),
            "clock": self.clock,
        }

    def open_dialog(self) -> None:
        from nxceviri.gui.schedule_dialog import ScheduleDialog  # noqa: PLC0415 - pencere yalnızca açılınca yüklenir

        win = self._win
        dialog = ScheduleDialog(win, self.schedule(), saved=win.project.path is not None, **self.dialog_options())
        try:
            if dialog.exec() == ScheduleDialog.DialogCode.Accepted:
                self.save(dialog.schedule())
        finally:
            dialog.deleteLater()

    # --- durum ----------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._task is not None

    def project_replaced(self) -> None:
        self._reset()
        self.refresh_status()

    def _reset(self) -> None:
        self._project = self._win.project
        self._slot = None
        self._done = False
        self._failures = 0
        self._retry_at = None
        self._task = None

    def status_text(self) -> str:
        """Durum çubuğu metni; zamanlayıcı kapalıysa boş."""
        sched = self.schedule()
        if not sched.enabled or not sched.cells:
            return ""
        if self._win.project.path is None:
            return "Zamanlayıcı: proje kaydedilmedi"
        if self.running:
            return "Zamanlayıcı çalışıyor"
        now = self.clock()
        if sched.active_at(now) and self._retry_at is not None and not self._done:
            return f"Zamanlayıcı: yeniden deneme {self._retry_at:%H:%M}"
        start = sched.next_start(now)
        if start is None:
            return "Zamanlayıcı: her saat"
        return f"Zamanlayıcı: sonraki {format_slot(start)}"

    def refresh_status(self) -> None:
        text = self.status_text()
        tip = (
            "Program ve proje açık, bilgisayar uyanıkken seçtiğiniz saatlerde çalışır. Ayar: Çeviri → Zamanlayıcı."
            if text
            else ""
        )
        self._win.status_segments.set_schedule(text, tip)

    # --- denetim --------------------------------------------------------------------------

    def tick(self) -> None:
        win = self._win
        if win.project is not self._project:
            self._reset()
        now = self.clock()
        sched = self.schedule()
        usable = sched.enabled and bool(sched.cells) and win.project.path is not None
        active = usable and sched.active_at(now)
        if self._task is not None:
            if not active and win.task is self._task:
                win._cancel_task()  # süren parti biter, yapılanlar kaydedilir
            self.refresh_status()
            return
        if active:
            slot = sched.slot_start(now)
            if slot != self._slot:
                self._slot = slot
                self._done = False
                self._failures = 0
                self._retry_at = None
            waiting = self._retry_at is not None and now < self._retry_at
            if not (self._done or waiting or win.busy or QApplication.activeModalWidget() is not None):
                self._start(sched, now)
        self.refresh_status()

    def _give_up(self, level: str, title: str, text: str) -> None:
        self._done = True
        self._win.notify(level, PREFIX + title, text)

    def _start(self, sched: Schedule, now: datetime) -> None:
        win = self._win
        chosen = spec(sched.provider)
        revise = sched.action == ACTION_REVISE
        if revise and chosen.classic:
            self._give_up(
                LEVEL_WARNING,
                "redaksiyon başlamadı",
                f"{chosen.name} talimat izleyemez. Zamanlayıcıda bir yapay zekâ hizmeti seçin.",
            )
            return
        if revise and not sched.instruction.strip():
            self._give_up(LEVEL_WARNING, "redaksiyon başlamadı", "Zamanlayıcıya redaksiyon talimatı yazın.")
            return
        if chosen.needs_key:
            try:
                key = win.secrets.get(api_key_name(chosen.id))
            except NxError:
                key = None
            if not key:
                self._give_up(
                    LEVEL_WARNING,
                    "iş başlamadı",
                    f"{chosen.name} için kayıtlı API anahtarı yok. Anahtarı Çeviri → Otomatik Çeviri penceresinden "
                    "kaydedin; zamanlayıcı sonraki zaman diliminde yeniden dener.",
                )
                return
        last = win.project.last_jobs() if revise else {}
        target = scheduled_rows(win.project.translation_rows(), sched.action, last)
        if not target:
            self._done = True
            win.statusBar().showMessage("Zamanlayıcı: bu iş için bekleyen satır yok.", 6000)
            return
        settings = MachineSettings(
            provider=chosen.id,
            base_url=sched.base_url,
            model=sched.model,
            notes=win.project.setting("translation_notes"),
            action=sched.action,
            instruction=sched.instruction
            if revise
            else ("" if chosen.classic else win.project.setting(TRANSLATE_INSTRUCTION_KEY)),
        )
        name = JOB_TITLES[sched.action]
        end = sched.slot_end(now)
        win.notify(
            LEVEL_INFO,
            f"{PREFIX}{name} başladı",
            f"{format_int(len(target))} satır · bitiş {format_slot(end)}. Yetişmeyen satırlar sonraki zaman dilimine "
            "kalır.",
        )
        page = win.translate_page
        before = win.task
        win._launch_machine(
            settings,
            win.machine.build_job(settings, target),
            set_running=page.set_machine_running,
            on_progress=page.update_machine_progress,
            report=page.show_notice,
            on_outcome=self._outcome,
            title_prefix=PREFIX,
        )
        if win.task is not None and win.task is not before and not self._done:
            self._task = win.task

    def _outcome(self, kind: str, _summary: RunSummary | None) -> None:
        self._task = None
        if kind == OUTCOME_SETUP:
            self._give_up(LEVEL_ERROR, "iş başlamadı", "Hizmet kurulamadı; ayrıntı çeviri sayfasında.")
        elif kind == OUTCOME_FAILED:
            self._failures += 1
            if self._failures > MAX_RETRIES:
                self._give_up(
                    LEVEL_WARNING,
                    "bu zaman diliminde vazgeçti",
                    f"İş {format_int(self._failures)} kez hata verdi. Sonraki zaman diliminde yeniden denenecek.",
                )
            else:
                self._retry_at = self.clock() + RETRY_DELAY
        else:
            self._done = True  # bitti ya da durduruldu: bu dilimde yeniden başlatılmaz
        self.refresh_status()
