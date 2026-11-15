"""Kullanıcı eklentisi onay kaydı: onaylanan eklenti klasörlerinin parmak izleri.

Kayıt, kullanıcı veri klasöründe küçük bir JSON dosyasıdır:
`{"surum": 1, "eklentiler": {"<klasörün mutlak yolu>": "<SHA-256 parmak izi>"}}`.
Parmak izi `loader.plugin_fingerprint` ile hesaplanır; içerik değişirse onay geçersizleşir. İz `__pycache__`'i
saymadığından, onaylı eklenti içe aktarılmadan hemen önce klasördeki tüm `__pycache__` dizinleri silinir (önceden
konmuş bir `.pyc` onaylanan kaynağın yerine çalışmasın; bayt kodu kaynaktan yeniden derlenir).

Dosya bozuk ya da okunamazsa hiçbir eklenti onaylı sayılmaz ve bu günlüğe yazılır. Yazım atomiktir (geçici
dosya + `os.replace`). Tehdit modeli: amaç, kullanıcının bilmeden kopyaladığı eklentinin sessizce çalışmasını
önlemektir; eklenti klasörüne ve bu dosyaya yazabilen biri kaydı da değiştirebilir (kapsam dışı).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from nxceviri.core.errors import NxError
from nxceviri.core.plugins.loader import user_data_dir

log = logging.getLogger(__name__)

TRUST_FILE_NAME = "eklenti_onaylari.json"
_FORMAT_VERSION = 1


class PluginTrustError(NxError):
    """Onay kaydı yazılamadı."""


def trust_key(folder: Path) -> str:
    """Kayıttaki anahtar: eklenti klasörünün çözümlenmiş mutlak yolu (yükleyici ve kurulum aynı anahtarı üretir)."""
    return str(folder.resolve())


class PluginTrust:
    """Onay kaydı. Her sorguda dosya yeniden okunur; böylece başka bir pencerenin yazdığı onay da görülür."""

    def __init__(self, path: Path | None = None) -> None:
        # Yol çağrı anında hesaplanır (modül düzeyinde değil): testlerdeki veri klasörü yalıtımı geçerli olsun.
        self.path = path if path is not None else user_data_dir() / TRUST_FILE_NAME

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            log.warning("Eklenti onay dosyası okunamadı (%s): %s; hiçbir eklenti onaylı sayılmadı.", self.path, exc)
            return {}
        entries = data.get("eklentiler") if isinstance(data, dict) else None
        if not isinstance(entries, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in entries.items()
        ):
            log.warning("Eklenti onay dosyası bozuk (%s); hiçbir eklenti onaylı sayılmadı.", self.path)
            return {}
        return entries

    def is_trusted(self, folder: Path, fingerprint: str) -> bool:
        """Klasör bu içerikle (parmak iziyle) onaylanmış mı?"""
        return self._read().get(trust_key(folder)) == fingerprint

    def known(self, folder: Path) -> bool:
        """Klasör daha önce (belki başka bir içerikle) onaylanmış mı? Onay bekliyorsa "içerik değişti" demektir."""
        return trust_key(folder) in self._read()

    def approve(self, folder: Path, fingerprint: str) -> None:
        """Klasörü bu parmak iziyle onaylı kaydeder; diğer kayıtlar korunur."""
        entries = self._read()
        entries[trust_key(folder)] = fingerprint
        text = json.dumps({"surum": _FORMAT_VERSION, "eklentiler": entries}, ensure_ascii=False, indent=2)
        tmp: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=".onay_", suffix=".tmp", dir=self.path.parent)
            tmp = Path(name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, self.path)
        except OSError as exc:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
            raise PluginTrustError(
                f"Eklenti onayı kaydedilemedi ({exc}).",
                f"Konum: {self.path}. Klasörün yazılabilir olduğundan emin olun; "
                "eklenti bir sonraki açılışta yine sorulur.",
            ) from exc
