"""Satırın makine çevirisini kimin yaptığı: sağlayıcı kimliği ve (yapay zekâ hizmetlerinde) model adı.

Proje dosyasında satırla birlikte saklanır (`text_entries.mt_provider`, `mt_model`); karar ARCHITECTURE 222.
Yalnızca kalıcı kimlik ve model adı yazılır: sunucu adresi, API anahtarı ya da kişisel veri yazılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

from nxceviri.core.translate.providers.catalog import SPECS

#: Sağlayıcı kimlikleri (ayarlardaki değerlerle aynı) ve çeviri belleği.
PROVIDER_OLLAMA = "ollama"
PROVIDER_DEEPL = "deepl"
PROVIDER_MEMORY = "memory"
#: Kimlik → arayüzde görünen ad (durum çubuğu ve satır ipucu aynı adı kullanır); hizmetler katalogdan gelir.
PROVIDER_NAMES = {**{s.id: s.name for s in SPECS}, PROVIDER_MEMORY: "Çeviri belleği"}


@dataclass(frozen=True)
class MachineOrigin:
    """Bir makine çevirisinin kaynağı; boş sağlayıcı "bilinmiyor" demektir (eski satır, dışarıdan gelen çeviri)."""

    provider: str = ""
    model: str = ""


#: Kaynağı silen değer: metni dışarıdan gelen hazır çeviriyle değişen satırlar için.
NO_ORIGIN = MachineOrigin()
#: Makine işinde sağlayıcıya gitmeden çeviri belleğinden doldurulan satırlar.
MEMORY_ORIGIN = MachineOrigin(PROVIDER_MEMORY)


def origin_label(provider: str, model: str = "") -> str:
    """Görünen ad: DeepL, Ollama (gemma4:12b), Çeviri belleği; kaynak bilinmiyorsa boş."""
    if not provider:
        return ""
    name = PROVIDER_NAMES.get(provider, provider)
    return f"{name} ({model})" if model else name
