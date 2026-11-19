"""Zamanlayıcı: haftalık takvimde seçilen saatlerde otomatik çeviri ya da redaksiyon (arayüzden bağımsız).

Takvim, haftanın günü (0 = pazartesi … 6 = pazar) ve saatten (0–23) oluşan hücrelerdir. Art arda seçilmiş saatler
tek bir **zaman dilimi** sayılır; dilim gece yarısını ve pazar → pazartesi geçişini aşabilir. Saatler bilgisayarın
yerel saatidir; her denetimde saat yeniden okunur (yaz saati geçişinde de o anın duvar saatine bakılır).

Ayar projede `schedule` adıyla JSON olarak saklanır. API anahtarı hiçbir zaman buraya yazılmaz (gizli depodadır);
yalnızca hizmet kimliği, model ve adres saklanır.

Satır kapsamı (`scheduled_rows`) işin sonsuza dek aynı satırlarda dönmemesi için dardır: çeviride yalnızca
çevrilmemiş satırlar (hatalılar yeniden denenmez), redaksiyonda yalnızca son işi redaksiyon olmayan makine çevirileri.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.report import job_kind
from nxceviri.core.translate.runner import ACTION_REVISE, ACTION_TRANSLATE
from nxceviri.core.translate.status import Status

#: Projede zamanlayıcı ayarının adı.
SCHEDULE_KEY = "schedule"
#: Zamanlayıcının redaksiyonda bitirdiği satırların metin özetleri (`dump_checked`).
CHECKED_KEY = "schedule/checked"
WEEKDAYS = 7
HOURS = 24
_WEEK = WEEKDAYS * HOURS
#: Zamanlayıcının yapabildiği işler.
SCHEDULE_ACTIONS = (ACTION_TRANSLATE, ACTION_REVISE)
#: Gün kısaltmaları (pazartesiden başlar).
DAY_NAMES = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")

Cell = tuple[int, int]


def _index(dt: datetime) -> int:
    return dt.weekday() * HOURS + dt.hour


def _hour_start(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _week_start(dt: datetime) -> datetime:
    return _hour_start(dt).replace(hour=0) - timedelta(days=dt.weekday())


@dataclass(frozen=True)
class Schedule:
    enabled: bool = False
    cells: frozenset[Cell] = field(default_factory=frozenset)
    action: str = ACTION_TRANSLATE
    #: Hizmet kimliği (`providers.catalog`), model ve adres; anahtar burada değil, gizli depodadır.
    provider: str = ""
    model: str = ""
    base_url: str = ""
    #: Redaksiyon talimatı.
    instruction: str = ""

    # --- saklama --------------------------------------------------------------------------

    def dump(self) -> str:
        return json.dumps(
            {
                "enabled": self.enabled,
                "cells": sorted([d, h] for d, h in self.cells),
                "action": self.action,
                "provider": self.provider,
                "model": self.model,
                "base_url": self.base_url,
                "instruction": self.instruction,
            },
            ensure_ascii=False,
        )

    @classmethod
    def load(cls, text: str) -> Schedule | None:
        """Saklanan ayar; bozuk ya da beklenmeyen içerikte None (uygulama çökmez, ayar boş sayılır)."""
        try:
            data = json.loads(text)
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        default = cls()
        enabled = data.get("enabled", default.enabled)
        raw_cells = data.get("cells", [])
        action = data.get("action", default.action)
        texts = {name: data.get(name, "") for name in ("provider", "model", "base_url", "instruction")}
        if not isinstance(enabled, bool) or not isinstance(raw_cells, list) or action not in SCHEDULE_ACTIONS:
            return None
        if not all(isinstance(v, str) for v in texts.values()):
            return None
        cells: set[Cell] = set()
        for item in raw_cells:
            if not (
                isinstance(item, list)
                and len(item) == 2
                and all(isinstance(v, int) and not isinstance(v, bool) for v in item)
                and 0 <= item[0] < WEEKDAYS
                and 0 <= item[1] < HOURS
            ):
                return None
            cells.add((item[0], item[1]))
        return cls(enabled, frozenset(cells), action, **texts)

    # --- takvim ---------------------------------------------------------------------------

    def _selected(self, index: int) -> bool:
        index %= _WEEK
        return (index // HOURS, index % HOURS) in self.cells

    @property
    def full(self) -> bool:
        return len(self.cells) >= _WEEK

    def active_at(self, dt: datetime) -> bool:
        return self._selected(_index(dt))

    def slot_start(self, dt: datetime) -> datetime:
        """`dt`'yi içeren dilimin başladığı saat (dilim kimliği). Bütün hafta seçiliyse haftanın başı."""
        if self.full:
            return _week_start(dt)
        i = _index(dt)
        back = 0
        while back < _WEEK and self._selected(i - back - 1):
            back += 1
        return _hour_start(dt) - timedelta(hours=back)

    def slot_end(self, dt: datetime) -> datetime:
        """`dt`'yi içeren dilimin bittiği an (son seçili saatin sonu). Bütün hafta seçiliyse gelecek haftanın başı."""
        if self.full:
            return _week_start(dt) + timedelta(days=WEEKDAYS)
        i = _index(dt)
        ahead = 1
        while ahead < _WEEK and self._selected(i + ahead):
            ahead += 1
        return _hour_start(dt) + timedelta(hours=ahead)

    def next_start(self, after: datetime) -> datetime | None:
        """`after`'dan sonra başlayan ilk dilimin başlangıcı; seçili saat yoksa ya da bütün hafta seçiliyse None."""
        if not self.cells or self.full:
            return None
        base = _hour_start(after)
        for step in range(1, _WEEK + 1):
            i = _index(after) + step
            if self._selected(i) and not self._selected(i - 1):
                return base + timedelta(hours=step)
        return None


def format_slot(dt: datetime) -> str:
    """Kısa gösterim: "Pzt 01:00"."""
    return f"{DAY_NAMES[dt.weekday()]} {dt:%H:%M}"


def text_fingerprint(text: str) -> str:
    """Çeviri metninin kısa özeti: satır o metinle denetlendikten sonra değişti mi, bununla anlaşılır."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def dump_checked(checked: Mapping[int, str]) -> str:
    """Zamanlayıcının redaksiyonda denetlediği satırlar (satır kimliği → metin özeti) proje ayarı olarak."""
    return json.dumps({str(k): v for k, v in sorted(checked.items())}, separators=(",", ":"))


def load_checked(text: str) -> dict[int, str]:
    """`dump_checked` çıktısını okur; boş ya da bozuk değer boş kayıt sayılır (en kötü hâlde satırlar yeniden gider)."""
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[int, str] = {}
    for key, value in data.items():
        if not (isinstance(key, str) and key.isdigit() and isinstance(value, str)):
            return {}
        out[int(key)] = value
    return out


def scheduled_rows(
    rows: Sequence[TranslationRow],
    action: str,
    last_jobs: Mapping[int, str],
    checked: Mapping[int, str] | None = None,
) -> list[TranslationRow]:
    """Zamanlayıcının işleyeceği satırlar.

    Çeviri: yalnızca çevrilmemiş satırlar (hatalılar her dilimde yeniden denenmesin). Redaksiyon: son işi
    redaksiyon olmayan makine çevirileri (redakte edilmiş, onaylı, çevrilmemiş satırlara dokunulmaz); `checked`
    içinde aynı metin özetiyle duran satırlar da atlanır (model değiştirmeden bıraktığı için geçmişe redaksiyon
    yazılmayan satırlar her dilimde yeniden gönderilmesin). Boş kaynaklı satırlar hiçbir zaman.
    """
    seen = checked or {}
    out = []
    for r in rows:
        if not r.source.strip():
            continue
        if action == ACTION_TRANSLATE:
            if r.status == Status.UNTRANSLATED:
                out.append(r)
        elif (
            r.status == Status.MACHINE
            and job_kind(last_jobs.get(r.id, "")) != ACTION_REVISE
            and seen.get(r.id) != text_fingerprint(r.translation)
        ):
            out.append(r)
    return out
