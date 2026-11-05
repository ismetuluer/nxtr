"""Projeye "metinler hangi eklenti ve sürümle çıkarıldı" kaydı ve açılışta uyarı.

Kayıt, proje ayarlarında tek bir JSON olarak durur (şema değişmez). Yerleşik biçimlerin sürümü
uygulama sürümüdür ve uyarı üretmez; yalnızca kullanıcı eklentileri denetlenir.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import Protocol

from nxceviri import __version__
from nxceviri.core.formats.registry import user_plugin_info

log = logging.getLogger(__name__)

#: Proje ayarlarında kaydın anahtarı.
SETTING_KEY = "cikaran_eklentiler"


class SettingsStore(Protocol):
    def setting(self, key: str, default: str = "") -> str: ...

    def set_setting(self, key: str, value: str) -> None: ...


def record_extraction(store: SettingsStore, formats: Iterable[str]) -> None:
    """Metinleri çıkaran biçimleri (tür → eklenti adı, sürüm, yerleşik mi) projeye yazar."""
    record: dict[str, dict[str, object]] = {}
    for kind in sorted(set(formats)):
        info = user_plugin_info(kind)
        if info is None:
            record[kind] = {"ad": kind, "surum": __version__, "yerlesik": True}
        else:
            record[kind] = {"ad": info.ad, "surum": info.surum, "yerlesik": False}
    store.set_setting(SETTING_KEY, json.dumps(record, ensure_ascii=False, sort_keys=True))


def plugin_warnings(store: SettingsStore) -> list[str]:
    """Projenin kullandığı kullanıcı eklentisi yüklü değilse ya da sürümü farklıysa kısa uyarılar."""
    raw = store.setting(SETTING_KEY)
    if not raw:
        return []
    try:
        record = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Projedeki eklenti kaydı okunamadı; yok sayıldı.")
        return []
    notes = []
    for kind, item in sorted(record.items()):
        if item.get("yerlesik"):
            continue
        ad, surum = str(item.get("ad", kind)), str(item.get("surum", "?"))
        info = user_plugin_info(kind)
        if info is None:
            notes.append(
                f"Bu projenin metinleri “{ad}” eklentisiyle (sürüm {surum}) çıkarılmış, ama eklenti yüklü değil. "
                "Yardım → Eklentiler'den ekleyip uygulamayı yeniden başlatın; yoksa bu dosyalar dışa aktarılamaz."
            )
        elif info.surum != surum:
            notes.append(
                f"Bu projenin metinleri “{ad}” eklentisinin {surum} sürümüyle çıkarılmış, yüklü sürüm {info.surum}. "
                "Metinleri yeniden aktarmanız önerilir."
            )
    return notes
