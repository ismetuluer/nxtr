"""Çeviri satırı durumları ve bir düzenlemenin sonucunda hangi duruma geçileceği."""

from __future__ import annotations

from enum import StrEnum

from nxceviri.core.translate import placeholders


class Status(StrEnum):
    UNTRANSLATED = "untranslated"
    MACHINE = "machine"
    REDACTED = "redacted"
    APPROVED = "approved"
    ERROR = "error"


STATUS_LABELS = {
    Status.UNTRANSLATED: "Çevrilmedi",
    Status.MACHINE: "Makine",
    Status.REDACTED: "Redakte",
    Status.APPROVED: "Onaylandı",
    Status.ERROR: "Hatalı",
}

#: "Çevrilen" sayılan durumlar (çevrilmemiş ve Hatalı satırlar hariç); ilerleme göstergeleri bunu kullanır.
TRANSLATED_STATUSES = (Status.APPROVED, Status.MACHINE, Status.REDACTED)

SOURCE_CHANGED_NOTE = "Oyundaki orijinal metin değişti; çeviriyi gözden geçirip yeniden kaydedin."


def evaluate(source: str, translation: str, ok_status: Status = Status.APPROVED) -> tuple[Status, str]:
    """Yeni çeviri metni için (durum, açıklama) döndürür.

    İnsanın elle girdiği geçerli çeviri "onaylandı" sayılır; makine çevirisi (M3)
    `ok_status=Status.MACHINE`, dış redaksiyondan gelen düzeltme `Status.REDACTED` ile çağırır.
    """
    if not translation:
        return Status.UNTRANSLATED, ""
    issues = placeholders.problems(source, translation)
    if issues:
        return Status.ERROR, " ".join(issues)
    return ok_status, ""
