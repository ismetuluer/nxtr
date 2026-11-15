"""Yeni ya da değişmiş kullanıcı eklentisi için onay sorusu ve açılıştaki onay akışı."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QMessageBox, QWidget

from nxceviri.core.plugins.loader import PluginInfo, PluginReport
from nxceviri.core.plugins.trust import PluginTrust, PluginTrustError

TITLE = "Yeni eklenti bulundu"
WARNING_TEXT = "Bu eklenti bilgisayarınızda kod çalıştırır. Yalnızca güvendiğiniz kişiden aldıysanız yükleyin."
LOAD = "Yükle"
NOT_NOW = "Şimdi Değil"


def approval_text(info: PluginInfo, changed: bool) -> str:
    folder = info.yol.name if info.yol is not None else "?"
    lines = [
        f"Eklenti: {info.ad or folder}",
        f"Sürüm: {info.surum}",
        f"Yazar: {info.yazar}",
        f"Klasör: {info.yol}",
    ]
    head = "Onayladığınız bu eklentinin dosyaları o zamandan beri değişti.\n\n" if changed else ""
    return head + "\n".join(lines) + "\n\n" + WARNING_TEXT


def ask_approval(parent: QWidget | None, info: PluginInfo, changed: bool) -> bool:
    """ "Yükle" / "Şimdi Değil" sorusu; varsayılan ve pencereyi kapatmak "Şimdi Değil"dir. Yükle seçildiyse True."""
    box = QMessageBox(QMessageBox.Icon.Warning, TITLE, approval_text(info, changed), parent=parent)
    load = box.addButton(LOAD, QMessageBox.ButtonRole.AcceptRole)
    later = box.addButton(NOT_NOW, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(later)
    box.setEscapeButton(later)
    box.exec()
    return box.clickedButton() is load


def offer_pending(
    report: PluginReport,
    trust: PluginTrust,
    ask: Callable[[PluginInfo, bool], bool],
    reload: Callable[[], PluginReport],
) -> list[PluginTrustError]:
    """Onay bekleyen her eklentiyi bir kez sorar; onaylananları kaydeder ve kayıt defterini hemen yeniden yükler.

    Onay, sorulan içeriğin parmak iziyle kaydedilir; yeniden yükleme izi yeniden hesapladığından arada değişen
    eklenti yüklenmez. Kaydedilemeyen onayların hataları döner (o eklenti yüklenmez)."""
    errors: list[PluginTrustError] = []
    approved = False
    for info in report.infos:
        if not info.onay_bekliyor or info.yol is None:
            continue
        if not ask(info, trust.known(info.yol)):
            continue
        try:
            trust.approve(info.yol, info.parmak_izi)
        except PluginTrustError as exc:
            errors.append(exc)
            continue
        approved = True
    if approved:
        reload()
    return errors
