"""Boşluk ve köşe ölçeği: arayüz stilindeki aralık ve köşe yarıçapları bu küçük basamaklardan seçilir.

Yeni stil yazarken ara değer (5, 9, 10 px gibi) kullanma; en yakın basamağı seç. 0-2 px'lik çizgi payları
(kenarlık, 1 px düzeltme) ölçeğin dışındadır.
"""

from __future__ import annotations

#: Aralık basamakları (px): dolgu, boşluk, kenar payı.
S4, S8, S12, S16, S24 = 4, 8, 12, 16, 24
SPACE_STEPS = (S4, S8, S12, S16, S24)

#: Köşe yarıçapı basamakları (px): küçük denetim, düğme/sekme, satır/panel, kart.
R4, R6, R8, R12 = 4, 6, 8, 12
RADIUS_STEPS = (R4, R6, R8, R12)

#: Konsol temalarının ek köşe basamakları: R0 keskin köşe (Piksel Gri, Yeşil Işık), R2 hafif yuvarlak, R16/R20/R24 çok
#: yuvarlak kart, hap düğme ve gezinme sütunu köşesi. Yalnızca `theme_style.ThemeStyle` değerleri bunları kullanır;
#: varsayılan tema yukarıdaki dört basamakta kalır.
R0, R2, R16, R20, R24 = 0, 2, 16, 20, 24
EXTRA_RADIUS_STEPS = (R0, R2, R16, R20, R24)

#: Onay kutusu ve radyo göstergesinin kenarı (px); radyonun yarıçapı bunun yarısıdır.
INDICATOR = 14
