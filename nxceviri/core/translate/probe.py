"""Sağlayıcı durumunu ucuzca sorgular: Ollama'nın bellekteki modeli ve DeepL'in kalan karakter kotası.

Durum çubuğu ipucu için kullanılır; yalnızca kısa okuma istekleri yapar (Ollama `/api/ps`, DeepL `/v2/usage`),
çeviri yapmaz ve hata fırlatmaz: ulaşılamazsa tek satırlık açıklama döner. Zaman aşımını çağıranın verdiği
`httpx.Client` belirler.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from nxceviri.core.translate.providers.base import ProviderError
from nxceviri.core.translate.providers.deepl import DeepLProvider

#: Bundan uzun kalan süre "süresiz" sayılır (Ollama `keep_alive: -1` çok uzak bir tarih verir).
_FOREVER = 24 * 3600
_FRACTION = re.compile(r"\.(\d+)")


def _grouped(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def parse_expiry(text: str) -> datetime | None:
    """Ollama'nın `expires_at` değeri (örn. `2026-11-09T12:00:00.123456789+03:00`); okunamazsa None."""
    # Nanosaniye basamakları `fromisoformat` için en çok 6 basamağa kısaltılır.
    value = _FRACTION.sub(lambda m: "." + m.group(1)[:6], text.strip().replace("Z", "+00:00"))
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _remaining(seconds: float) -> str:
    if seconds > _FOREVER:
        return "süresiz"
    if seconds <= 0:
        return "bitmek üzere"
    if seconds < 90:
        return f"{round(seconds)} sn"
    return f"{round(seconds / 60)} dk"


def _placement(entry: dict[str, Any]) -> str:
    size = int(entry.get("size") or 0)
    vram = int(entry.get("size_vram") or 0)
    if size <= 0 or vram <= 0:
        return "CPU"
    gpu = min(100, round(100 * vram / size))
    return "GPU %100" if gpu >= 100 else f"GPU %{gpu} · CPU %{100 - gpu}"


def ollama_summary(
    base_url: str,
    model: str,
    client: httpx.Client,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[str]:
    """Seçili modelin bellekte olup olmadığı, GPU/CPU payı ve kalan süre (ipucu satırları)."""
    lines = [f"Model: {model}" if model else "Model seçilmedi"]
    try:
        response = client.get(f"{base_url.rstrip('/')}/api/ps")
        response.raise_for_status()
        data = response.json()
        loaded = data.get("models") or []
    except (httpx.HTTPError, ValueError, AttributeError):
        return ["Ollama'ya bağlanılamadı."]
    entry = next((m for m in loaded if model and model in (m.get("name"), m.get("model"))), None)
    if entry is None:
        lines.append("Bellekte değil (ilk istekte yüklenir).")
        return lines
    lines.append(f"Bellekte: {_placement(entry)}")
    expiry = parse_expiry(str(entry.get("expires_at") or ""))
    if expiry is not None:
        lines.append(f"Kalan süre: {_remaining((expiry - now()).total_seconds())}")
    return lines


def deepl_summary(provider: DeepLProvider) -> list[str]:
    """Kalan karakter kotası (ipucu satırları)."""
    try:
        used, limit = provider.usage()
    except ProviderError as exc:
        return [exc.message]
    if not limit:
        return [f"Kullanılan: {_grouped(used)} karakter"]
    left = max(limit - used, 0)
    return [f"Kalan kota: {_grouped(left)} karakter", f"Kullanılan: {_grouped(used)} / {_grouped(limit)}"]
