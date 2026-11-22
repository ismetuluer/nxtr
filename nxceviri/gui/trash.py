"""Geri Dönüşüm Kutusu: üzerine yazılan eski mod kalıcı silinmez, kutuya gider (geri alınabilir).

Çekirdek Qt bilmez; dışa aktarma bu işlevi `discard_old` olarak alır. Testler gerçek kutuyu doldurmasın diye
`tests/conftest.py` bu modüldeki `move_to_trash`'i değiştirir; çağıranlar onu her seferinde modül üzerinden okur.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile


def move_to_trash(path: Path) -> bool:
    """Klasörü ya da dosyayı Geri Dönüşüm Kutusu'na taşır; olmazsa (ağ sürücüsü, izin) False döner, bir şey silmez."""
    return bool(QFile.moveToTrash(str(path)))
