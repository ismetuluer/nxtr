"""Makine işleri için arayüzden bağımsız yardımcılar: iş başlıkları, iş kimliği ve sonuç iletileri."""

from __future__ import annotations

from datetime import datetime

from nxceviri.core.progress import TaskContext
from nxceviri.core.translate.providers.base import TranslationProvider
from nxceviri.core.translate.runner import (
    ACTION_RETRANSLATE,
    ACTION_REVISE,
    ACTION_TRANSLATE,
    MachineJob,
    RunSummary,
    run_machine_translation,
)
from nxceviri.gui.widgets import format_int

JOB_TITLES = {
    ACTION_TRANSLATE: "Otomatik çeviri",
    ACTION_RETRANSLATE: "Yeniden çeviri",
    ACTION_REVISE: "Redaksiyon",
}
_DONE_WORDS = {ACTION_TRANSLATE: "çevrildi", ACTION_RETRANSLATE: "yenilendi", ACTION_REVISE: "düzeltildi"}


def short_summary(action: str, r: RunSummary) -> tuple[str, str, str]:
    """Bildirim kartı için (düzey, başlık, tek satır özet). Ayrıntı (`describe_summary`) ayrı pencerede gösterilir."""
    parts = [f"{format_int(r.translated)} satır {_DONE_WORDS.get(action, 'yazıldı')}"]
    if r.from_memory:
        parts.append(f"{format_int(r.from_memory)} satır bellekten")
    if r.unchanged:
        parts.append(f"{format_int(r.unchanged)} satır aynı kaldı")
    failed = r.broken + r.rejected
    if failed:
        parts.append(f"{format_int(failed)} satır denetimden geçmedi")
    if r.suspicious:
        parts.append(f"{format_int(r.suspicious)} şüpheli çeviri")
    if r.missing:
        parts.append(f"{format_int(r.missing)} satır yanıtsız")
    level = "warning" if failed or r.missing or r.suspicious else "success"
    return level, f"{JOB_TITLES.get(action, 'Çeviri')} bitti", " · ".join(parts)


def describe_summary(action: str, r: RunSummary) -> tuple[str, str]:
    """İş bitince kullanıcıya gösterilecek (mesaj, durum)."""
    if action == ACTION_TRANSLATE:
        msg = (
            f"Makine çevirisi bitti: {format_int(r.translated)} satır çevrildi, "
            f"{format_int(r.from_memory)} satır çeviri belleğinden dolduruldu."
        )
        if r.from_memory and not r.translated:
            msg += (
                " Bellekteki çeviriyi istemiyorsanız satırları seçip sağ tık → “Seçili satırları yeniden çevir” "
                "deyin; bellek atlanır."
            )
    elif action == ACTION_RETRANSLATE:
        msg = f"Yeniden çeviri bitti: {format_int(r.translated)} satırın çevirisi yenilendi."
        if r.unchanged:
            msg += f" {format_int(r.unchanged)} satırda sonuç öncekiyle aynı çıktı."
    else:
        msg = (
            f"Düzeltme bitti: {format_int(r.translated)} satır düzeltildi, {format_int(r.unchanged)} satır "
            "zaten uygun bulunup aynen bırakıldı."
        )
    if r.broken:
        msg += (
            f" {format_int(r.broken)} satırda model kontrol kodlarını bozdu; bunlar “Hatalı” "
            "işaretlendi ve düzeltilene kadar dışa aktarılmaz."
        )
    if r.rejected:
        msg += (
            f" {format_int(r.rejected)} satırda modelin önerisi denetimden geçmedi; bu satırların eski çevirisi "
            "korundu. Öneriyi beğendiyseniz çeviri hücresine yapıştırıp kodları düzelterek kaydedebilirsiniz:"
        )
        for rj in r.rejections[:3]:
            msg += f"\n• {rj.key}: {' '.join(rj.issues)}\n  Modelin önerisi: “{rj.suggestion}”"
    if r.cleaned:
        msg += (
            f" {format_int(r.cleaned)} satırda modelin eklediği fazlalıklar temizlendi (özgünde olmayan etiket veya "
            "kod, sona yığılmış satır sonu kodu)."
        )
    if r.suspicious:
        msg += (
            f" {format_int(r.suspicious)} satırın çevirisinde uydurma belirtisi var (İngilizce kalmış, yabancı harf, "
            "tekrar veya orijinalden çok uzun/kısa). Kontrol Et → Denetle'de “Şüpheli çeviri” olarak listelenir; "
            "gözden geçirin."
        )
    if r.missing:
        msg += f" {format_int(r.missing)} satır yanıtsız kaldı; yeniden başlatınca tekrar denenir."
    for warning in r.warnings:
        msg += f" {warning}"
    return msg, "warning" if r.broken or r.missing or r.rejected or r.suspicious else "success"


def new_job_id(action: str) -> str:
    """Geçmişte bir işin değişikliklerini gruplayan kimlik: "revise-2026-10-25T09:30:12.123456"."""
    return f"{action}-{datetime.now().isoformat()}"


def run_and_close(provider: TranslationProvider, job: MachineJob, ctx: TaskContext) -> RunSummary:
    """Arka plan işinde çeviriyi çalıştırır; sağlayıcıyı (ör. DeepL sözlüğünü) her durumda kapatır."""
    try:
        return run_machine_translation(provider, job, ctx)
    finally:
        provider.close()
