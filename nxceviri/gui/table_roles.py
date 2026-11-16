"""Çeviri tablosu modelinin özel veri rolleri tek yerde; sayılar çakışmasın."""

from __future__ import annotations

from PySide6.QtCore import Qt

#: Modelin bu rolde döndürdüğü `TranslationRow`.
ROW_ROLE = Qt.ItemDataRole.UserRole + 10
STATUS_ROLE = Qt.ItemDataRole.UserRole + 20
#: Modelin hücre için verdiği bul-vurgusu: `FindCell`. Hücre çizimi eşleşen aralıkları bununla boyar.
FIND_SPANS_ROLE = Qt.ItemDataRole.UserRole + 21
#: Başlık satırında grubun adı; gerçek satırda `None`.
HEADER_ROLE = Qt.ItemDataRole.UserRole + 40
