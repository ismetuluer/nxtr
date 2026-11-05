"""Çeviri sağlayıcısı sözleşmesi (CLAUDE.md §4.2).

Yeni bir sağlayıcı (DeepL, OpenAI uyumlu uç nokta…) yalnızca `TranslationProvider`'ı
uygulayarak eklenir; çekirdeğin geri kalanı değişmez. Sağlayıcıya giden metinlerde kontrol
kodları zaten `⟦n⟧` yer tutucularına çevrilmiştir; dönen çevirinin yer tutucuları
çağıran tarafından (`runner`) denetlenir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nxceviri.core.errors import NxError


class ProviderError(NxError):
    """Sağlayıcıya ulaşılamadı veya istek reddedildi (ağ, zaman aşımı, kota, eksik model…)."""

    def __init__(self, message: str, hint: str = "", *, retryable: bool = False) -> None:
        super().__init__(message, hint)
        self.retryable = retryable


@dataclass(frozen=True)
class ProviderStatus:
    ok: bool
    message: str  # kullanıcıya gösterilecek Türkçe özet


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    translation: str
    note: str = ""


@dataclass(frozen=True)
class BatchItem:
    id: str
    text: str  # ⟦n⟧ yer tutuculu kaynak metin
    context: str = ""  # anahtar adı gibi ipucu
    max_length: int | None = None
    current: str = ""  # redaksiyonda: düzeltilecek mevcut çeviri
    fix: str = ""  # giderilmesi gereken sorun (önceki denemede bulunan)
    codes: tuple[str, ...] = ()  # yer tutucuların anlamı: ⟦n⟧ → codes[n-1] (ör. "Satır sonu")


@dataclass(frozen=True)
class ContextLine:
    """Partinin önünde/arkasında oyunda geçen satır: yalnızca anlamak için, çevrilmez."""

    source: str
    translation: str = ""


@dataclass(frozen=True)
class Scene:
    """Partinin sahnesi: çevrilecek satırların hemen öncesi ve sonrası, varsa kullanıcının talimatı.

    `revise=True` ise maddelerin `current` alanındaki mevcut çeviriler talimata göre düzeltilir;
    talimatı izleyemeyen sağlayıcılar (`supports_instructions=False`) bu işi reddeder. Çeviride talimat
    ("bu satırlar menü metni") isteğe bağlıdır; talimat izleyemeyen sağlayıcı onu yok sayar.
    """

    before: tuple[ContextLine, ...] = ()
    after: tuple[ContextLine, ...] = ()
    revise: bool = False
    instruction: str = ""


@dataclass(frozen=True)
class BatchResult:
    id: str
    text: str | None  # None: sağlayıcı bu satırı döndürmedi
    error: str = ""


class TranslationProvider(Protocol):
    name: str
    label: str
    requires_api_key: bool
    supports_glossary: bool
    max_batch_chars: int
    max_batch_items: int
    #: Serbest talimatı (redaksiyon) izleyebilir mi? DeepL izleyemez.
    supports_instructions: bool

    def test_connection(self) -> ProviderStatus: ...

    def translate_batch(
        self,
        items: list[BatchItem],
        source_lang: str,
        target_lang: str,
        context: str,
        glossary: list[GlossaryTerm],
        *,
        scene: Scene | None = None,
    ) -> list[BatchResult]:
        """`context`: kullanıcının oyun notları. `scene`: komşu satırlar ve redaksiyon talimatı."""
        ...

    def estimate_cost(self, items: list[BatchItem]) -> str | None:
        """Ücretli sağlayıcılarda tahmini maliyet/kota kullanımı; ücretsizse None."""
        ...

    def close(self) -> None:
        """Bağlantıyı ve sağlayıcıda oluşturulan geçici kaynakları (ör. DeepL sözlüğü) kapatır."""
        ...
