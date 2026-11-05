# ruff: noqa: E501  (üretilmiş veri: paragraf metinleri tek satırda tutulur)
"""Devil May Cry oyun resimlerindeki yazıların Türkçeleri: sayfa özeti → etiketler (bkz. `dmc1_images`).

Pencereler, yazı bölgelerini otomatik bulan bir araçla (bitişik yazı piksellerinin kutuları) çıkarılıp elle
gruplandı; her etiketin İngilizcesi resimde okunan yazıdır. Eşya adlarının Türkçeleri PC Türkçe yamasının eşya
açıklamalarındaki adlarla aynıdır; silah ve düşman adları (özel adlar) PC yamasındaki gibi çevrilmez.
"""

from __future__ import annotations

from nxceviri.core.fontpatch.labels import Label

#: Resimleri değiştirilecek dosyalar (RomFS'e göre): tablodaki sayfaları içeren bütün dosyalar (aynı resim
#: birçok dosyada tekrar eder; ör. silah adları `wp_init.itm` ve `spdinit.itm` içinde onlarca kez).
FILES: tuple[str, ...] = (
    "data/dmc1/etc/t_moji_j.t32",
    "data/dmc1/etc_e/op_moji.t32",
    "data/dmc1/etc_u/op_moji.t32",
    "data/dmc1/pack_e/gdpr_opt_nx.pack",
    "data/dmc1/pack_e/title_menu_nx.pack",
    "data/dmc1/status/fle_init.dat",
    "data/dmc1/status/fontnew.tm2",
    "data/dmc1/status/item_st1.dat",
    "data/dmc1/status/item_st2.dat",
    "data/dmc1/status/item_st3.dat",
    "data/dmc1/status/item_tm2.itm",
    "data/dmc1/status/itm_tm2.itm",
    "data/dmc1/status/mssn_clr.bnd",
    "data/dmc1/status/mssn_clr.dat",
    "data/dmc1/status/mssn_f00.tm2",
    "data/dmc1/status/retry_f.t32",
    "data/dmc1/status/rlt_prts.tm2",
    "data/dmc1/status/rlt_prts00.tm2",
    "data/dmc1/status/spdinit.itm",
    "data/dmc1/status/wp_init.dat",
    "data/dmc1/status/wp_init.itm",
    "data/dmc1/etc_u/memcardl.dat",
    "data/dmc1/etc_u/memcards.dat",
    "data/dmc1/etc_u/easy_m.t32",
    "data/dmc1/etc_u/hard_m.t32",
    "data/dmc1/etc_u/v_hard_m.t32",
    "data/dmc1/etc/load.tm2",
    "data/dmc1/status/result.itm",
    "data/dmc1/status_u/act_img.itm",
    "data/dmc1/status/cockpit.t32",
    "data/dmc1/status_u/st1_map.dat",
    "data/dmc1/status_u/st2_map.dat",
    "data/dmc1/status_u/st3_map.dat",
    "data/dmc1/status_u/st4_map.dat",
    "data/dmc1/etc/dead.tm2",
    "data/dmc1/etc/tobe.tm2",
    "data/dmc1/status/mssn_ini.bnd",
)

PAGES: dict[str, tuple[Label, ...]] = {}


def _add(keys: tuple[str, ...], *labels: Label) -> None:
    PAGES.update(dict.fromkeys(keys, labels))


# status/item_st1.dat @ 0x180, 0x10214
_add(
    ("d7063e2fc54c2a18", "f3f851e7db3ccb18"),
    Label((1, 3, 209, 58), "Bangle of Time", "Zaman Bileziği", "brush", align="left"),
    Label((2, 57, 214, 111), "Staff of Hermes", "Hermes'in Asası", "brush", align="left"),
    Label((3, 115, 217, 160), "Emblem Shield", "Amblem Kalkanı", "brush", align="left"),
    Label((3, 162, 168, 206), "Untouchable", "Dokunulmaz", "brush", align="left"),
    Label((2, 208, 142, 252), "Vital Star", "Yaşam Yıldızı", "brush", align="left"),
)

# status/item_st1.dat @ 0x20408, 0x3049c
_add(
    ("c2f262f278c85f2a", "ca01a32131a27ffc"),
    Label((0, 0, 153, 54), "Holy Water", "Kutsal Su", "brush", align="left"),
    Label((1, 59, 147, 113), "Rusty Key", "Paslı Anahtar", "brush", align="left"),
    Label((2, 114, 143, 160), "Devil Star", "Şeytan Yıldızı", "brush", align="left"),
    Label((9, 165, 133, 205), "Yellow Orb", "Sarı Küre", "brush", align="left"),
    Label((143, 164, 253, 205), "Blue Orb", "Mavi Küre", "brush", align="left"),
    Label((2, 211, 129, 255), "Luminite", "Luminit", "brush", align="left"),
)

# status/item_st1.dat @ 0x40690, 0x50724
_add(
    ("711c8592c0e9f097", "9a20ac05cadeba5c"),
    Label((2, 3, 109, 48), "Amulet", "Tılsım", "brush", align="left"),
)

# status/item_st1.dat @ 0xa0a58, 0xb0aec
_add(
    ("316795c8366f28b9", "53645399aec449df"),
    Label((2, 0, 256, 55), "Staff of Judgement", "Yargı Asası", "brush", align="left"),
    Label((3, 57, 235, 111), "Melancholy Soul", "Melankolik Ruh", "brush", align="left"),
    Label((3, 112, 200, 157), "Death Sentence", "Ölüm Fermanı", "brush", align="left"),
    Label((3, 160, 200, 205), "Death Sentence", "Ölüm Fermanı", "brush", align="left"),
    Label((3, 210, 108, 254), "Trident", "Mızrak", "brush", align="left"),
)

# status/item_st1.dat @ 0xc0ce0, 0xd0d74
_add(
    ("e5232e38ddce0c27", "58b80d04ebb6fe60"),
    Label((3, 1, 197, 54), "Guiding Light", "Kılavuz Işık", "brush", align="left"),
    Label((2, 59, 189, 114), "Pride of Lion", "Aslanın Gururu", "brush", align="left"),
)

# status/item_st2.dat @ 0xa0a58, 0xb0aec
_add(
    ("c9ca721bc04c00ac", "ef5fa500a8dee800"),
    Label((2, 3, 253, 58), "Sign of Humbleness", "Tevazu Nişanı", "brush", align="left"),
    Label((2, 58, 256, 114), "Sign of Perseverance", "Azim Nişanı", "brush", align="left"),
    Label((2, 116, 226, 170), "Knight's Portrait", "Şövalye Portresi", "brush", align="left"),
    Label((3, 171, 230, 225), "Sign of Chastity", "İffet Nişanı", "brush", align="left"),
)

# status/item_st2.dat @ 0xc0ce0, 0xd0d74
_add(
    ("d111e923245070bc", "e01ea4b90f971a40"),
    Label((2, 4, 227, 57), "Wheel of Destiny", "Kader Çarkı", "brush", align="left"),
    Label((3, 59, 217, 104), "Emblem Shield", "Amblem Kalkanı", "brush", align="left"),
    Label((2, 106, 201, 161), "Pair of Lances", "Mızrak Çifti", "brush", align="left"),
    Label((3, 164, 110, 207), "Chalice", "Kadeh", "brush", align="left"),
)

# status/item_st3.dat @ 0xa0a58, 0xb0aec
_add(
    ("3bc22156f8bef3a7", "7575b44884a1f278"),
    Label((3, 2, 256, 58), "Token of Philosophy", "Felsefe Nişanesi", "brush", align="left"),
    Label((2, 59, 252, 112), "Philosopher's Stone", "Felsefe Taşı", "brush", align="left"),
    Label((2, 115, 225, 171), "Philosopher's Egg", "Felsefe Yumurtası", "brush", align="left"),
    Label((2, 171, 201, 226), "Perfect Amulet", "Mükemmel Tılsım", "brush", align="left"),
)

# status/item_st3.dat @ 0xc0ce0, 0xd0d74
_add(
    ("095ede3524b4a8c1", "9ac64ad0f4acf27a"),
    Label((2, 3, 159, 48), "Quicksilver", "Cıva", "brush", align="left"),
    Label((162, 4, 251, 47), "Elixir", "İksir", "brush", align="left"),
)

# status/fle_init.dat @ 0x20408, 0x3049c
_add(
    ("7f5da3033f0ebecb", "3d62a5843efb626d"),
    Label((3, 175, 149, 225), "Mission", "Görev", "brush", align="left"),
)

# status/fle_init.dat @ 0x60918, 0x709ac
_add(
    ("44fb634c8d4720bc", "831a674bac07ae57"),
    Label((2, 3, 109, 65), "Enemy", "Düşman", "brush", align="left"),
)

# status/fontnew.tm2 @ 0xc0, 0x40140
_add(
    ("fb20f322a2edcff1", "aca25d827c377c2d"),
    Label((22, 5, 216, 61), "Devil Arms", "Şeytan Silahları", "brush", align="left"),
)

# status/wp_init.dat @ 0x180, 0x10214
_add(
    ("b25ce2ab0a411e00", "fbce2a4878907fa2"),
    Label((2, 9, 206, 58), "Devil Arms", "Şeytan Silahları", "brush", align="left"),
)

# status/wp_init.dat @ 0x20408, 0x3049c
_add(
    ("207053c7ed2044e3", "d9fe6d26f3f74a71"),
    Label((154, 59, 245, 118), "Guns", "Silahlar", "brush", align="left"),
)

# status/mssn_clr.bnd @ 0x102c4
_add(
    ("b0c4da71847109d9",),
    Label((9, 1, 248, 49), "Ranking Bonus", "Derece Bonusu", "gothic", align="left"),
    Label((8, 49, 231, 97), "Special Bonus", "Özel Bonus", "gothic", align="left"),
    Label((9, 98, 203, 144), "Boss Bonus", "Boss Bonusu", "gothic", align="left"),
    Label((10, 145, 187, 189), "Clear Time", "Süre", "gothic", align="left"),
    Label((10, 193, 97, 236), "Orbs", "Küreler", "gothic", align="left"),
)

# status/mssn_clr.bnd @ 0x20358
_add(
    ("efd0ae7764afd27a",),
    Label((9, 0, 248, 49), "Ranking Bonus", "Derece Bonusu", "gothic", align="left"),
    Label((9, 49, 203, 97), "Boss Bonus", "Boss Bonusu", "gothic", align="left"),
    Label((10, 96, 187, 141), "Clear Time", "Süre", "gothic", align="left"),
    Label((9, 145, 123, 194), "Perfect", "Kusursuz", "gothic", align="left"),
    Label((162, 145, 249, 189), "Orbs", "Küreler", "gothic", align="left"),
)

# status/mssn_clr.bnd @ 0xd0
_add(
    ("071c4708170f013a",),
    Label((8, 2, 196, 40), "next mission", "sonraki görev", "gothic", align="left"),
    Label((10, 46, 112, 88), "SAVE", "KAYDET", "serif", align="left"),
)

# status/mssn_clr.dat @ 0x10374
_add(
    ("8cc1457105b91b34",),
    Label((9, 1, 248, 49), "Ranking Bonus", "Derece Bonusu", "gothic", align="left"),
    Label((8, 49, 231, 97), "Special Bonus", "Özel Bonus", "gothic", align="left"),
    Label((9, 98, 203, 144), "Boss Bonus", "Boss Bonusu", "gothic", align="left"),
    Label((10, 145, 187, 189), "Clear Time", "Süre", "gothic", align="left"),
    Label((10, 193, 97, 236), "Orbs", "Küreler", "gothic", align="left"),
)

# status/mssn_clr.dat @ 0x20408, 0x3049c
_add(
    ("b10b6d3b185dd682", "44dd2db951466b0d"),
    Label((9, 0, 248, 49), "Ranking Bonus", "Derece Bonusu", "gothic", align="left"),
    Label((9, 49, 203, 97), "Boss Bonus", "Boss Bonusu", "gothic", align="left"),
    Label((10, 96, 187, 141), "Clear Time", "Süre", "gothic", align="left"),
    Label((9, 145, 123, 194), "Perfect", "Kusursuz", "gothic", align="left"),
    Label((162, 145, 249, 189), "Orbs", "Küreler", "gothic", align="left"),
)

# status/mssn_f00.tm2 @ 0xc0, 0x40140
_add(
    ("dba0faf76fffa5c1", "de5a5c9b3d1cd60a"),
    Label((7, 0, 205, 40), "mission start", "görev başla", "gothic", align="left"),
    Label((2, 48, 140, 93), "power up", "güçlen", "gothic", align="left"),
)

# status/retry_f.t32 @ 0x201f4, 0x30288
_add(
    ("b85d2d1514c9af62", "cbdd53ac3ef4c2ea"),
    Label((9, 19, 133, 59), "Yellow Orb", "Sarı Küre", "brush", align="left"),
)

# status/rlt_prts.tm2 @ 0xc0
_add(
    ("d00137d54c061ecb",),
    Label((1, 32, 148, 65), "EASY AUTO", "KOLAY OTO", "serif_italic", align="left"),
    Label((153, 33, 241, 64), "HARD", "ZOR", "serif_italic", align="left"),
)

# status/rlt_prts00.tm2 @ 0xc0
_add(
    ("780042df8aeac468",),
    Label((1, 32, 148, 65), "EASY AUTO", "KOLAY OTO", "serif_italic", align="left"),
    Label((153, 33, 241, 64), "HARD", "ZOR", "serif_italic", align="left"),
)

# etc/t_moji_j.t32 @ 0x160
_add(
    ("cdcd937efb01493a",),
    Label((43, 2, 215, 40), "NEW GAME", "YENİ OYUN", "plain"),
    Label((34, 37, 220, 75), "LOAD DATA", "YÜKLE", "plain"),
    Label((65, 68, 193, 106), "OPTION", "AYARLAR", "plain"),
    Label((10, 102, 246, 137), "EASY AUTOMATIC", "KOLAY OTOMATİK", "plain"),
    Label((84, 161, 173, 195), "HARD", "ZOR", "plain"),
)

# etc/t_moji_j.t32 @ 0x101f4
_add(
    ("dfcf79f84d9d241c",),
    Label((10, 0, 247, 43), "Character Change", "Karakter Değiştir", "plain"),
    Label((44, 36, 207, 64), "The Legendary", "Efsanevi", "plain"),
    Label((57, 64, 197, 93), "Dark Knight", "Kara Şövalye", "plain"),
    Label((12, 127, 246, 161), "Score Attack Mode", "Skor Saldırısı", "plain"),
    Label((19, 158, 238, 204), "Select Difficulty", "Zorluk Seç", "plain"),
)

# pack_e/title_menu_nx.pack @ 0x24
_add(
    ("883acafccf1fa98e",),
    Label((56, 0, 199, 39), "EXTRAS", "EKSTRALAR", "plain"),
)

# pack_e/title_menu_nx.pack @ 0x28b8
_add(
    ("1e31f4be7b211eb3",),
    Label((4, 0, 251, 39), "ACHIEVEMENTS", "BAŞARIMLAR", "plain"),
)

# pack_e/title_menu_nx.pack @ 0x514c
_add(
    ("be11582ecdb20be8",),
    Label((52, 0, 205, 39), "CREDITS", "YAPIMCILAR", "plain"),
)

# pack_e/title_menu_nx.pack @ 0x79e0
_add(
    ("b799ba8f67dc2cc6",),
    Label((46, 0, 209, 39), "GALLERY", "GALERİ", "plain"),
)

# pack_e/gdpr_opt_nx.pack @ 0xc
_add(
    ("c68e9b9ed89dac3a",),
    Label((0, 0, 217, 32), "PRIVACY POLICY", "GİZLİLİK POLİTİKASI", "plain", align="left"),
)

# etc_e/op_moji.t32 @ 0x160
_add(
    ("165eb10e1756852b",),
    Label((0, 0, 251, 34), "CONTROLLER SETUP", "KONTROL AYARLARI", "plain", align="left"),
    Label((0, 31, 239, 66), "DEFAULT SETTINGS", "VARSAYILANLAR", "plain", align="left"),
    Label((0, 63, 235, 97), "LANGUAGE SELECT", "DİL SEÇİMİ", "plain", align="left"),
    Label((0, 95, 229, 130), "MONITOR TUNING", "EKRAN AYARI", "plain", align="left"),
    Label((0, 127, 143, 161), "VIBRATION", "TİTREŞİM", "plain", align="left"),
    Label((155, 127, 253, 161), "AUDIO", "SES", "plain", align="left"),
    Label((0, 160, 148, 194), "MONAURAL", "MONO", "plain", align="left"),
    Label((158, 160, 230, 194), "EXIT", "ÇIKIŞ", "plain", align="left"),
    Label((0, 190, 138, 225), "SUBTITLES", "ALTYAZI", "plain", align="left"),
    Label((142, 190, 238, 225), "TYPE A", "TİP A", "plain", align="left"),
    Label((0, 222, 91, 257), "TYPE B", "TİP B", "plain", align="left"),
    Label((0, 255, 58, 288), "OFF", "YOK", "plain", align="left"),
    Label((62, 255, 114, 288), "ON", "VAR", "plain", align="left"),
)

# etc_e/op_moji.t32 @ 0x121f4
_add(
    ("77a3fb7de582a76f",),
    Label((0, 0, 256, 36), "CONTROLLER SETUP", "KONTROL AYARLARI", "serif", align="left"),
    Label((0, 36, 249, 72), "DEFAULT SETTINGS", "VARSAYILANLAR", "serif", align="left"),
    Label((0, 72, 244, 108), "LANGUAGE SELECT", "DİL SEÇİMİ", "serif", align="left"),
    Label((0, 108, 236, 144), "MONITOR TUNING", "EKRAN AYARI", "serif", align="left"),
    Label((0, 144, 149, 180), "VIBRATION", "TİTREŞİM", "serif", align="left"),
    Label((158, 145, 255, 180), "AUDIO", "SES", "serif", align="left"),
    Label((0, 181, 153, 216), "MONAURAL", "MONO", "serif", align="left"),
    Label((158, 180, 231, 215), "EXIT", "ÇIKIŞ", "serif", align="left"),
    Label((0, 216, 141, 252), "SUBTITLES", "ALTYAZI", "serif", align="left"),
    Label((142, 216, 246, 251), "TYPE A", "TİP A", "serif", align="left"),
    Label((0, 252, 100, 287), "TYPE B", "TİP B", "serif", align="left"),
)

# etc_e/op_moji.t32 @ 0x24288
_add(
    ("7be98eaa96750ff4",),
    Label((0, 0, 61, 32), "OFF", "YOK", "serif", align="left"),
    Label((62, 0, 115, 33), "ON", "VAR", "serif", align="left"),
)

# etc_u/op_moji.t32 @ 0xc0
_add(
    ("7afca9043a80c60f",),
    Label((0, 0, 251, 34), "CONTROLLER SETUP", "KONTROL AYARLARI", "plain", align="left"),
    Label((0, 31, 239, 66), "DEFAULT SETTINGS", "VARSAYILANLAR", "plain", align="left"),
    Label((0, 63, 229, 98), "MONITOR TUNING", "EKRAN AYARI", "plain", align="left"),
    Label((0, 95, 119, 129), "RUMBLE", "TİTREŞİM", "plain", align="left"),
    Label((155, 94, 253, 129), "AUDIO", "SES", "plain", align="left"),
    Label((0, 127, 148, 162), "MONAURAL", "MONO", "plain", align="left"),
    Label((159, 127, 230, 162), "EXIT", "ÇIKIŞ", "plain", align="left"),
    Label((0, 158, 138, 193), "SUBTITLES", "ALTYAZI", "plain", align="left"),
    Label((142, 158, 239, 193), "TYPE A", "TİP A", "plain", align="left"),
    Label((0, 190, 91, 225), "TYPE B", "TİP B", "plain", align="left"),
    Label((0, 222, 57, 256), "OFF", "YOK", "plain", align="left"),
    Label((62, 222, 114, 256), "ON", "VAR", "plain", align="left"),
)

# status/item_tm2.itm @ 0x590, 0x8624
_add(
    ("096fc96f19c9b598", "05b5dbd3e7beb3d4"),
    Label((0, 2, 125, 50), "Rusty Key", "Paslı Anahtar", "brush", align="left"),
)

# status/item_tm2.itm @ 0x40f80, 0x49014
_add(
    ("db7b7c61d8c3a5e6", "d26714405a0c3943"),
    Label((0, 1, 198, 50), "Melancholy Soul", "Melankolik Ruh", "brush", align="left"),
)

# status/item_tm2.itm @ 0x81970, 0x89a04
_add(
    ("d15f0b54e8bcfffc", "35d5f757fe33a3ca"),
    Label((0, 0, 98, 36), "Wiseman Soul", "Bilge Ruh", "brush", align="left"),
)

# status/item_tm2.itm @ 0xc2360, 0xca3f4
_add(
    ("c9872914523e9de5", "db46ada4053964d4"),
    Label((0, 4, 103, 45), "Halberd", "Teber", "brush", align="left"),
)

# status/item_tm2.itm @ 0x102d50, 0x10ade4
_add(
    ("f6db4251df6c8a8e", "0810bdc422532e5d"),
    Label((0, 1, 163, 51), "Sunshine Key", "Güneş Anahtarı", "brush", align="left"),
)

# status/item_tm2.itm @ 0x143740, 0x14b7d4
_add(
    ("1b81de0569f111b1", "34d00955bb20c8dd"),
    Label((0, 1, 170, 43), "Death Sentence", "Ölüm Fermanı", "brush", align="left"),
)

# status/itm_tm2.itm @ 0x1c4b30, 0x1ccbc4
_add(
    ("ce7fbd1c69b8f417", "eb80e0f4ba5bdee0"),
    Label((0, 1, 170, 43), "Death Sentence", "Ölüm Fermanı", "brush", align="left"),
)

# etc_u/memcardl.dat @ 0xe0, 0xe0220, 0x1c0360
_add(
    ("102288a6afcfc482", "4bfc8d48dd2d871a", "17dcc127a87c9821"),
    Label((28, 90, 132, 130), "LOAD", "YÜKLE", "serif", glow=(230, 200, 40)),
    Label((22, 140, 80, 178), "File", "Dosya", "serif", align="left"),
    Label(
        (24, 196, 104, 224),
        "MODE",
        "MOD",
        "serif",
        align="left",
        ink=(20, 4, 8),
        glow=(225, 25, 55),
        box=(31, 201, 97, 218),
    ),
    Label(
        (24, 226, 96, 254),
        "TIME",
        "SÜRE",
        "serif",
        align="left",
        ink=(20, 4, 8),
        glow=(225, 25, 55),
        box=(31, 231, 88, 249),
    ),
    Label(
        (24, 258, 104, 286),
        "SAVES",
        "KAYIT",
        "serif",
        align="left",
        ink=(20, 4, 8),
        glow=(225, 25, 55),
        threshold=25,
        box=(31, 263, 97, 281),
    ),
)

# etc_u/memcards.dat @ 0xe0, 0xe0220, 0x1c0360
_add(
    ("e0febdc61a7fecec", "0cce1ba0c869223e", "791443688a5b1d9d"),
    Label((26, 88, 160, 132), "SAVE", "KAYDET", "serif", glow=(230, 200, 40)),
    Label((22, 140, 80, 178), "File", "Dosya", "serif", align="left"),
    Label(
        (24, 196, 104, 224),
        "MODE",
        "MOD",
        "serif",
        align="left",
        ink=(20, 4, 8),
        glow=(225, 25, 55),
        box=(31, 201, 97, 218),
    ),
    Label(
        (24, 226, 96, 254),
        "TIME",
        "SÜRE",
        "serif",
        align="left",
        ink=(20, 4, 8),
        glow=(225, 25, 55),
        box=(31, 231, 88, 249),
    ),
    Label(
        (24, 258, 104, 286),
        "SAVES",
        "KAYIT",
        "serif",
        align="left",
        ink=(20, 4, 8),
        glow=(225, 25, 55),
        threshold=25,
        box=(31, 263, 97, 281),
    ),
)

# etc_u/memcardl.dat @ 0x2a0540, 0x2b05d4
_add(
    ("5ed255078164ada4", "e8ec4fc34361766a"),
    Label((4, 8, 238, 42), "MEMORY CARD SLOT 1", "KAYIT YUVASI 1", "serif", align="left"),
    Label((4, 56, 238, 90), "MEMORY CARD SLOT 2", "KAYIT YUVASI 2", "serif", align="left"),
    Label((0, 130, 150, 160), "EASY AUTO", "KOLAY OTO", "plain", align="left"),
    Label((152, 130, 236, 160), "HARD", "ZOR", "plain", align="left"),
)

# etc_u/memcardl.dat @ 0x300908, 0x340988
_add(
    ("de53ebb0eecdbf72", "b5a51d8e66dd0fb0"),
    Label(
        (4, 8, 238, 42),
        "MEMORY CARD SLOT 1",
        "KAYIT YUVASI 1",
        "serif",
        align="left",
        ink=(255, 248, 190),
        glow=(215, 190, 30),
    ),
    Label(
        (4, 56, 238, 90),
        "MEMORY CARD SLOT 2",
        "KAYIT YUVASI 2",
        "serif",
        align="left",
        ink=(255, 248, 190),
        glow=(215, 190, 30),
    ),
)

# etc_u/memcardl.dat @ 0x300868
_add(
    ("ba3ce414aa30d131",),
    Label(
        (42, 8, 256, 42),
        "MEMORY CARD SLOT",
        "KAYIT YUVASI",
        "serif",
        align="left",
        ink=(255, 248, 190),
        glow=(215, 190, 30),
        box=(48, 15, 240, 37),
    ),
    Label(
        (42, 56, 256, 90),
        "MEMORY CARD SLOT",
        "KAYIT YUVASI",
        "serif",
        align="left",
        ink=(255, 248, 190),
        glow=(215, 190, 30),
        box=(48, 63, 240, 85),
    ),
)

# etc_u/memcardl.dat @ 0x380ac8
_add(
    ("016ab6642a3d4f60",),
    Label(
        (0, 0, 264, 48),
        "SECRET MISSION",
        "GİZLİ GÖREV",
        "serif",
        ink=(12, 3, 5),
        glow=(170, 15, 35),
        box=(12, 15, 249, 34),
    ),
)

# etc_u/easy_m.t32 @ 0xc0
_add(
    ("98d5966335d2195f",),
    Label(
        (55, 22, 458, 64),
        "EASY AUTOMATIC MODE",
        "KOLAY OTOMATİK MOD",
        "bold",
        fill="filter",
        ink=(225, 240, 240),
        glow=(40, 170, 180),
    ),
    Label(
        (204, 70, 502, 170),
        "In this mode you'll be able to\nperform and enjoy many different\nmoves with simplified controls.",
        "Bu modda basitleştirilmiş\nkontrollerle birçok farklı hareketi\nyapabilir ve keyfini sürebilirsin.",
        "bold",
        align="left",
        ink=(235, 235, 230),
        glow=(70, 70, 70),
    ),
    Label(
        (72, 170, 406, 244),
        "With just one button, you'll be able to perform\nmany different sword actions depending on the\nsituation.",
        "Tek bir düğmeyle duruma göre birçok\nfarklı kılıç hareketi yapabilirsin.\n ",
        "bold",
        align="left",
        fill="filter",
        ink=(215, 250, 250),
        glow=(30, 150, 160),
    ),
    Label(
        (200, 276, 500, 352),
        "You'll also be able to fire without pressing\nR to aim. Plus, you can fire rapidly by\nholding down the fire button.",
        "Ayrıca nişan için R'ye basmadan ateş\nedebilirsin. Ateş düğmesini basılı\ntutarak seri ateş de edebilirsin.",
        "bold",
        align="left",
        fill="filter",
        ink=(215, 250, 250),
        glow=(30, 150, 160),
    ),
)

# etc_u/hard_m.t32 @ 0xc0
_add(
    ("40d832f606a8684a",),
    Label((108, 214, 310, 252), "Go challenge the", "Sırada", "bold", align="right", fill="filter", size=26),
    Label((306, 204, 428, 252), "HARD", "ZOR", "bold", fill="filter", ink=(14, 2, 4), glow=(200, 15, 35)),
    Label((424, 214, 510, 252), "mode.", "mod.", "bold", align="left", fill="filter", size=26),
)

# etc_u/v_hard_m.t32 @ 0xc0
_add(
    ("ab90aea4f8de7241",),
    Label((34, 156, 244, 190), "Go challenge the", "Şimdi meydan oku:", "bold", align="left", fill="filter"),
)

# status/retry_f.t32 @ 0x160
_add(
    ("b1efbc0509704064",),
    Label((20, 30, 500, 236), "Try Again", "Tekrar Dene", "brush", ink=(8, 8, 0), glow=(225, 220, 20)),
)

# etc/load.tm2 @ 0xc0
_add(
    ("d8d8e10a2bc9e27f",),
    Label((148, 34, 480, 98), "Now Loading", "Yükleniyor", "serif", align="left"),
)

# status/result.itm @ 0xf0
_add(
    ("45fb3c81657c9819",),
    Label(
        (112, 14, 378, 56),
        "TOTAL RESULTS",
        "GENEL SONUÇ",
        "serif_italic",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(121, 20, 369, 50),
    ),
    Label(
        (236, 62, 396, 90),
        "SECRET MISSION",
        "GİZLİ GÖREVLER",
        "serif_italic",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(243, 68, 389, 85),
    ),
    Label(
        (232, 128, 510, 158),
        "DEVIL HUNTER RANKINGS",
        "ŞEYTAN AVCISI DERECELERİ",
        "serif_italic",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(239, 133, 503, 152),
    ),
)

# status/result.itm @ 0xe0230, 0x1c0370, 0x2a04b0
_add(
    ("7b93192024c7e5d7", "01ea89e97c1e4843", "208ece1cded45357"),
    Label(
        (112, 14, 378, 56),
        "TOTAL RESULTS",
        "GENEL SONUÇ",
        "serif_italic",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(121, 20, 369, 50),
    ),
    Label(
        (236, 62, 396, 90),
        "SECRET MISSION",
        "GİZLİ GÖREVLER",
        "serif_italic",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(243, 68, 389, 85),
    ),
    Label(
        (232, 128, 510, 158),
        "DEVIL HUNTER RANKINGS",
        "ŞEYTAN AVCISI DERECELERİ",
        "serif_italic",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(239, 133, 503, 152),
    ),
    Label(
        (4, 64, 120, 92),
        "DIFFICULTY",
        "ZORLUK",
        "serif_italic",
        align="left",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(10, 71, 112, 86),
    ),
    Label(
        (4, 107, 166, 135),
        "TOTAL RED ORBS",
        "TOPLAM KIRMIZI KÜRE",
        "serif_italic",
        align="left",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(10, 114, 158, 129),
    ),
    Label(
        (4, 152, 136, 180),
        "TOTAL RETRY",
        "TOPLAM DENEME",
        "serif_italic",
        align="left",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(10, 159, 128, 174),
    ),
    Label(
        (4, 197, 120, 225),
        "TOTAL TIME",
        "TOPLAM SÜRE",
        "serif_italic",
        align="left",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(10, 204, 112, 219),
    ),
    Label(
        (4, 241, 166, 269),
        "STYLISH COMBOS",
        "STİL KOMBOLARI",
        "serif_italic",
        align="left",
        fill="filter",
        ink=(12, 2, 4),
        glow=(190, 10, 30),
        box=(10, 248, 158, 263),
    ),
)

# status_u/act_img.itm @ 0x170
_add(
    ("7d9a78a3b5a13eed",),
    Label(
        (55, 75, 445, 132),
        "While holding  , press Left Stick in the\ndirection of Dante's back and  .",
        "R'yi basılı tutarken Sol Çubuğu\nDante'nin arkasına doğru it ve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
    Label(
        (140, 165, 472, 196),
        "Then continue holding down  to jump.",
        "Ardından zıplamak için X'i basılı tut.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
    Label(
        (55, 225, 388, 280),
        "Finally, while jumping press  again to\nslash down.",
        "Son olarak zıplarken aşağı kesmek\niçin X'e yeniden bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
    Label(
        (55, 312, 398, 366),
        "Swing the sword in a upward rising motion,\nbashing up enemies into the air.",
        "Kılıcı yukarı doğru savurarak\ndüşmanları havaya fırlat.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
)

# status_u/act_img.itm @ 0x402c4
_add(
    ("c06564fb1d43d527",),
    Label(
        (55, 78, 472, 140),
        "Press  while jumping against walls and on\nenemies.",
        "Duvarlara ve düşmanlara doğru zıplarken\nB'ye bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x80418
_add(
    ("3d60b64c6dcf8c79",),
    Label(
        (55, 298, 472, 362),
        "While holding  , press Left Stick toward\nDante's left or right and  .",
        "R'yi basılı tutarken Sol Çubuğu Dante'nin\nsoluna veya sağına it ve B'ye bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0xc056c
_add(
    ("454d6a47d3a12fb5",),
    Label(
        (55, 78, 275, 103),
        "Unleash the devil inside.",
        "İçindeki şeytanı serbest bırak.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 300, 472, 362),
        "Press  when three or more Devil Trigger\ngauges are charged.",
        "Üç veya daha fazla Devil Trigger göstergesi\ndolunca L'ye bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x1006c0
_add(
    ("58a5c97370a77032",),
    Label(
        (55, 25, 462, 70),
        "EASY AUTOMATIC MODE",
        "KOLAY OTOMATİK MOD",
        "bold",
        fill="filter",
        ink=(225, 240, 240),
        glow=(40, 170, 180),
    ),
    Label(
        (165, 70, 478, 150),
        "In this mode you'll be able to\nperform and enjoy many different\nmoves with simplified controls.",
        "Bu modda basitleştirilmiş\nkontrollerle birçok farklı hareketi\nyapabilir ve keyfini sürebilirsin.",
        "bold",
        align="left",
        ink=(235, 235, 230),
        glow=(70, 70, 70),
        size=21,
    ),
    Label(
        (70, 185, 448, 256),
        "With just one button, you'll be able to perform\nmany different sword actions depending on the\nsituation.",
        "Tek bir düğmeyle duruma göre birçok\nfarklı kılıç hareketi yapabilirsin.\n ",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=19,
    ),
    Label(
        (135, 290, 472, 362),
        "You'll also be able to fire without pressing\nR to aim. Plus, you can fire rapidly by\nholding down the fire button.",
        "Ayrıca nişan için R'ye basmadan ateş\nedebilirsin. Ateş düğmesini basılı\ntutarak seri ateş de edebilirsin.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=19,
    ),
)

# status_u/act_img.itm @ 0x180968
_add(
    ("948c0ae1ec7fb970",),
    Label(
        (55, 78, 275, 103),
        "Double jump in the air.",
        "Havada ikinci kez zıpla.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 326, 312, 360),
        "Press  while jumping.",
        "Zıplarken B'ye bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x1c0abc
_add(
    ("bf8eb4846d029bcf",),
    Label(
        (55, 78, 375, 103),
        "Throw the sword like a boomerang.",
        "Kılıcı bumerang gibi fırlat.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 298, 472, 362),
        "Hold down  .\nThe longer the hold, the further the sword travels.",
        "X'i basılı tut.\nNe kadar uzun tutarsan kılıç o kadar uzağa gider.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x200c10
_add(
    ("154eb826db2b93ed",),
    Label(
        (55, 78, 445, 128),
        "With lightening speed, plunge the sword into\nenemies.",
        "Yıldırım hızıyla kılıcı düşmanlara\nsapla.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 298, 472, 362),
        "While holding  , press Left Stick in the\ndirection that Dante is facing and  .",
        "R'yi basılı tutarken Sol Çubuğu Dante'nin\nbaktığı yöne it ve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x240d64
_add(
    ("3607fa7bfa14be07",),
    Label(
        (55, 78, 345, 128),
        "Plunge the sword from an even\nfurther distance.",
        "Kılıcı daha da uzak bir\nmesafeden sapla.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 298, 472, 362),
        "While holding  , press Left Stick in the\ndirection that Dante is facing and  .",
        "R'yi basılı tutarken Sol Çubuğu Dante'nin\nbaktığı yöne it ve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x280eb8
_add(
    ("5c43bdefbee89e29",),
    Label(
        (55, 78, 455, 128),
        "Damage enemies with an intense spinning body\nattack.",
        "Güçlü bir dönme saldırısıyla\ndüşmanlara hasar ver.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 298, 472, 362),
        "While airborne in Devil Trigger, use Left Stick\nand press  .",
        "Devil Trigger'dayken havada Sol Çubuğu\nkullan ve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x2c100c
_add(
    ("bb5f61fbf52dcd6a",),
    Label(
        (55, 78, 335, 128),
        "Keeps attacking as long as the\nmagic gauges last.",
        "Büyü göstergeleri bitene kadar\nsaldırmaya devam eder.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 298, 472, 362),
        "While airborne in Devil Trigger, use Left Stick\nand press  .",
        "Devil Trigger'dayken havada Sol Çubuğu\nkullan ve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x301160
_add(
    ("0a71173db2ea8807",),
    Label(
        (55, 78, 455, 128),
        "Become airborne and be capable of performing\naerial electrocution attacks.",
        "Havalan ve havadan elektrik\nsaldırıları yap.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 298, 455, 362),
        "Press  while jumping in Devil Trigger.\nPress  or  to shoot electric bolts.",
        "Devil Trigger'dayken zıplarken R'ye bas.\nElektrik atmak için A veya Y'ye bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x3412b4
_add(
    ("2211e49edde0515e",),
    Label(
        (55, 78, 345, 128),
        "Surround the body in flame and\ndamage enemies upon contact.",
        "Bedenini alevle sar ve temas\neden düşmanlara hasar ver.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 326, 312, 360),
        "Press Left Stick and  .",
        "Sol Çubuğu it ve B'ye bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x381408
_add(
    ("016b721af568e818",),
    Label(
        (55, 78, 345, 128),
        "Charge power and release it in the\nform of a magma uppercut.",
        "Güç topla ve onu magma dolu\nbir aparkat olarak sal.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 298, 472, 362),
        "While holding  , press Left Stick in the\ndirection of Dante's back and  .",
        "R'yi basılı tutarken Sol Çubuğu\nDante'nin arkasına doğru it ve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x3c155c
_add(
    ("ae48e6913a49489f",),
    Label(
        (55, 78, 365, 152),
        "A quick but powerful flaming back\nroundhouse kick.  Its impact will\ndrive the enemy back.",
        "Hızlı ama güçlü, alevli bir\ngeri dönüş tekmesi. Darbesi\ndüşmanı geri savurur.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 298, 472, 362),
        "While holding  , press Left Stick in the\ndirection that Dante is facing and  .",
        "R'yi basılı tutarken Sol Çubuğu Dante'nin\nbaktığı yöne it ve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x4016b0
_add(
    ("eaebaf614055ab36",),
    Label(
        (55, 78, 365, 128),
        "A flaming back roundhouse kick with\na longer reach.",
        "Daha uzun menzilli, alevli bir\ngeri dönüş tekmesi.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 298, 472, 362),
        "While holding  , press Left Stick in the\ndirection that Dante is facing and  .",
        "R'yi basılı tutarken Sol Çubuğu Dante'nin\nbaktığı yöne it ve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x441804
_add(
    ("d8922ccde0a8d835",),
    Label(
        (55, 78, 325, 103),
        "Shoot fireballs from the fists.",
        "Yumruklarından ateş topu fırlat.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 268, 472, 362),
        "While in Devil Trigger, hold  then press\nLeft Stick in the direction of Dante's back\nand  .",
        "Devil Trigger'dayken R'yi basılı tut, sonra\nSol Çubuğu Dante'nin arkasına doğru it\nve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x481958
_add(
    ("3136df7fe15eca6c",),
    Label(
        (55, 78, 325, 128),
        "Shoot even more destructive\nfireballs from the fists.",
        "Yumruklarından daha da yıkıcı\nateş topları fırlat.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 268, 472, 362),
        "While in Devil Trigger, hold  then press\nLeft Stick in the direction of Dante's back\nand  .",
        "Devil Trigger'dayken R'yi basılı tut, sonra\nSol Çubuğu Dante'nin arkasına doğru it\nve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status_u/act_img.itm @ 0x4c1aac
_add(
    ("f1b35762a5179082",),
    Label(
        (55, 78, 325, 128),
        "Create a wall of fire and burn\neverything within range.",
        "Bir ateş duvarı yarat ve\nmenzildeki her şeyi yak.",
        "sans",
        align="left",
        ink=(238, 238, 238),
        glow=(40, 40, 40),
        size=17,
    ),
    Label(
        (55, 298, 472, 362),
        "While jumping in Devil Trigger, press Left Stick\nand  .",
        "Devil Trigger'dayken zıplarken Sol Çubuğu\nit ve X'e bas.",
        "bold",
        align="left",
        ink=(225, 250, 250),
        glow=(30, 150, 160),
        size=21,
    ),
)

# status/cockpit.t32 @ 0xc03cc
_add(
    ("efeb1be113058afe",),
    Label((233, 452, 310, 500), "ull", "urgun", "serif_italic", align="left", size=30),
    Label((212, 318, 338, 404), "ool !", "esur!", "serif_italic", align="left", box=(214, 352, 330, 395), size=34),
    Label(
        (182, 112, 366, 200), "bsolute !", "mansız!", "serif_italic", align="left", box=(184, 160, 355, 190), size=30
    ),
)

# status_u/st1_map.dat @ 0x250, 0x102e4
_add(
    ("8afb22dd32beebf9", "a825d1d7ce3a16ad"),
    Label((9, 1, 221, 48), "UnderWorld", "Yeraltı", "script", align="left", size=36),
    Label((10, 65, 168, 112), "Unknown", "Bilinmeyen", "script", align="left", size=36),
    Label((5, 130, 123, 189), "Garden", "Bahçe", "script", align="left", size=36),
    Label((145, 128, 244, 175), "Castle", "Şato", "script", align="left", size=36),
    Label((17, 193, 102, 252), "Ship", "Gemi", "script", align="left", size=36),
)

# etc/dead.tm2 @ 0xc0
_add(
    ("5310b58223235881",),
    Label((0, 0, 512, 256), "You are Dead", "Öldün", "brush", ink=(8, 0, 2), glow=(200, 10, 40)),
)

# etc/tobe.tm2 @ 0xc0
_add(
    ("f6ebb7791bb86289",),
    Label((0, 0, 512, 180), "To Be Continued", "Devam Edecek", "brush", ink=(8, 0, 2), glow=(200, 10, 40)),
)

# status/mssn_ini.bnd @ 0x160, 0x101f4
_add(
    ("d3360de475cd6bfc", "6ed79b7f377b54eb"),
    Label((7, 0, 205, 40), "mission start", "görev başla", "gothic", align="left"),
    Label((2, 48, 140, 93), "power up", "güçlen", "gothic", align="left"),
)
