"""Yeni eklenti iskeleti: çalışan küçük bir örnek biçim, onun bayt bayt round-trip testi ve not şablonu.

İskelet bilerek çalışır durumdadır (satır başına `anahtar=metin` tutan uydurma bir biçim); yazar
`detect/extract/inject` gövdelerini kendi biçimiyle değiştirirken testler yol gösterici kalır.
"""

from __future__ import annotations

import re
from pathlib import Path

from nxceviri.core.formats.detection import FileKind
from nxceviri.core.formats.registry import BUILTIN_PLUGINS
from nxceviri.core.plugins.install import PluginInstallError
from nxceviri.core.plugins.loader import EKLENTI_API

_NAME = re.compile(r"^[a-z][a-z0-9_]{2,31}$")

_MANIFEST = f"""ad = "__AD__"
surum = "0.1.0"
yazar = "Adınızı yazın"
# Yalnızca bu oyunlarda denenir (16 haneli TitleID'ler). Boş liste: her oyunda denenir.
oyunlar = []
api = {EKLENTI_API}
aciklama = "Bu eklentinin hangi oyunun hangi dosyalarını çevirdiğini bir cümleyle yazın."
"""

_PLUGIN = '''"""__AD__ biçim eklentisi.

İskelet, satır başına `anahtar=metin` tutan uydurma bir biçimi çözer. Kendi biçiminiz için `detect`,
`extract` ve `inject` gövdelerini değiştirin; `tests/` içindeki round-trip testi (hiçbir şeyi
değiştirmeden çıkar → geri yaz = bayt bayt aynı dosya) eklenti bitene kadar geçmelidir.
"""

from __future__ import annotations

from collections.abc import Mapping

from nxceviri.core.formats.base import Context, FormatError, TextEntry
from nxceviri.core.plugins import FormatPluginBase

BASLIK = b"NXORNEK\\n"


class Eklenti(FormatPluginBase):
    name = "__AD__"  # tarama raporundaki tür; benzersiz olmalı
    label = "__AD__ (örnek biçim)"
    candidates_only = False  # True: yalnızca tarama raporunda metin adayı olan dosyalar denenir
    path_suffixes = (".nxornek",)  # boş değilse yalnızca bu uzantılı dosyalar açılır

    def detect(self, path: str, head: bytes) -> bool:
        """Dosya bu eklentinin biçiminde mi? `head`, dosyanın ilk 64 baytıdır."""
        return head.startswith(BASLIK)

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        """Çevrilecek metinleri çıkarır. `key` dosya içinde benzersiz ve kalıcı olmalıdır."""
        if not data.startswith(BASLIK):
            raise FormatError("Bu dosya __AD__ biçiminde değil.", "Başlık bulunamadı.")
        entries = []
        for index, line in enumerate(data[len(BASLIK) :].decode("utf-8").split("\\n")):
            key, sep, text = line.partition("=")
            if sep and text:
                entries.append(TextEntry(key=key, index=index, source=text, codes=()))
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        """Yalnızca çevirisi verilen girdilerin metnini değiştirir; dosyanın geri kalanı bayt bayt aynı kalır."""
        lines = data[len(BASLIK) :].decode("utf-8").split("\\n")
        for index, line in enumerate(lines):
            key, sep, _text = line.partition("=")
            if sep and key in translations:
                if "\\n" in translations[key]:
                    raise FormatError(f"“{key}” çevirisi satır sonu içeriyor; bu biçim tek satırlık metin tutar.")
                lines[index] = f"{key}={translations[key]}"
        return BASLIK + "\\n".join(lines).encode("utf-8")


PLUGIN = Eklenti()
'''

_TEST = '''"""__AD__ eklentisi testleri. Gerçek oyun dosyası kullanılmaz; örnek elle üretilir.

Çalıştırma (uygulama klasöründen): python -m pytest eklentiler/__AD__/tests
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("eklenti_plugin", Path(__file__).resolve().parents[1] / "plugin.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PLUGIN = MODULE.PLUGIN

ORNEK = b"NXORNEK\\nbaslik=Hello World\\nsecim_1=Yes\\n\\nsecim_2=T\\xc3\\xbcrk\\xc3\\xa7e \\xc4\\xb1\\xc5\\x9f\\n"


def test_round_trip_is_byte_identical() -> None:
    entries = PLUGIN.extract(ORNEK)
    assert PLUGIN.inject(ORNEK, {e.key: e.source for e in entries}) == ORNEK
    assert PLUGIN.inject(ORNEK, {}) == ORNEK


def test_detect_and_extract() -> None:
    assert PLUGIN.detect("a.nxornek", ORNEK[:64])
    assert not PLUGIN.detect("a.nxornek", b"BASKA")
    assert [e.key for e in PLUGIN.extract(ORNEK)] == ["baslik", "secim_1", "secim_2"]


def test_inject_changes_only_the_translated_text() -> None:
    out = PLUGIN.inject(ORNEK, {"secim_1": "Evet"})
    assert out == ORNEK.replace(b"secim_1=Yes", b"secim_1=Evet")


def test_inject_rejects_newline_in_translation() -> None:
    with pytest.raises(Exception, match="satır sonu"):
        PLUGIN.inject(ORNEK, {"secim_1": "iki\\nsatır"})
'''

_NOTE = """# __AD__ eklentisi

Bu eklentinin neyi çevirdiğini, biçimin yapısını ve bilinen tuzakları buraya yazın.

## Oyun ve dosyalar

- Oyun / TitleID:
- Dosya adları ve konumları:

## Biçim

- Başlık ve alanlar:
- Metin kodlaması, sonlandırıcılar, uzunluk sınırları:
- Kontrol kodları (renk, değişken, satır sonu) ve `⟦n⟧` yer tutucularına nasıl çevrildiği:

## Bilinen tuzaklar

-
"""


def validate_name(ad: str) -> None:
    if not _NAME.match(ad):
        raise PluginInstallError(
            f"“{ad}” geçerli bir eklenti adı değil.",
            "Ad küçük harfle başlamalı; yalnızca a-z, 0-9 ve _ içermeli; 3-32 karakter olmalı (ör. oyunadi_msg).",
        )
    reserved = {k.value for k in FileKind} | {p.name for p in BUILTIN_PLUGINS}
    if ad in reserved:
        raise PluginInstallError(f"“{ad}” yerleşik bir biçim adı.", "Farklı bir ad seçin (ör. oyunadi_msg).")


def create_plugin(ad: str, target_root: Path) -> Path:
    """`target_root/<ad>/` altına eklenti iskeletini yazar ve klasörü döndürür."""
    validate_name(ad)
    folder = target_root / ad
    if folder.exists():
        raise PluginInstallError(f"“{folder}” zaten var.", "Başka bir ad seçin ya da klasörü silin.")
    files = {
        "eklenti.toml": _MANIFEST,
        "plugin.py": _PLUGIN,
        "NOT.md": _NOTE,
        f"tests/test_{ad}.py": _TEST,
    }
    try:
        for rel, template in files.items():
            path = folder / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template.replace("__AD__", ad), encoding="utf-8", newline="\n")
    except OSError as exc:
        raise PluginInstallError(f"Eklenti iskeleti yazılamadı ({exc}).", f"Konum: {folder}") from exc
    return folder
