# Biçim notları dizini

Bir oyunun metin biçimi daha önce çözülmüş mü? Önce buraya bak; çözülmüşse yeni kod yazma, uygulamayı kullan.
Oyun durumları için `docs/uyumluluk.md`, yeni oyun için `docs/rehber/yeni-oyun.md`.

## Metin biçimleri: motor → biçim → eklenti → oyunlar → not

Eklenti sütunundaki adlar `nxceviri/core/formats/registry.py` içindeki `name` değeridir; yollar `nxceviri/core/formats/`
altındadır.

| Motor / yayıncı | Biçim | Eklenti (kod yolu) | Görülen oyunlar | Not dosyası |
|---|---|---|---|---|
| Nintendo LMS | MSBT (`MsgStdBn`), SARC/Yaz0/ZSTD kapsayıcıları | `msbt` (`msbt/`) | Rhythm Heaven Groove | `msbt.md`, `archives.md` |
| Unity | Unity Localization string tabloları (AssetBundle) | `unity` (`unity/unity.py`) | Silver Pines, Castlevania: Belmont's Curse, Kong: Survivor Instinct | `unity.md` |
| Unity | I2 Localization (ham bayt, tip ağacı yok) | `unity` (`unity/i2.py`) | Blasphemous | `unity.md` ("I2 Localization") |
| Unity | Düz `TextAsset` (SRT + TSV) ve `Locoliser` önbelleği | `unity` (`unity/loctext.py`, `locoliser.py`) | Despelote | `unity.md` ("Düz metin yerelleştirmesi") |
| Unity | `Localization` nesnesi (`[SerializeReference]` kayıt defteri) | `unity` (`unity/dklocal.py`) | Donkey Kong Country Returns HD | `dkcr.md` |
| Unity (metin Unity dışında) | AGAR/WAD arşivi, `.lin` betikleri, `.pak` tabloları | `danganronpa` (`danganronpa/`) | Danganronpa: Trigger Happy Havoc Anniversary Edition | `danganronpa.md` |
| Unreal Engine | `.locres`, `.pak` | `unreal` (`unreal/locres.py`) | SpongeBob: Titans of the Tide (yalnızca 2 satır; Oodle sıkıştırması desteklenmiyor); gerçek oyunla tam denenmedi | `unreal.md` |
| Game Freak | `.dat` + `.tbl` mesaj dosyaları | `gfmsg` (`gfmsg/`) | Pokémon Legends: Arceus, Pokémon: Let's Go, Pikachu! | `gfmsg.md` |
| Yacht Club | YCD (`.yc`) | `mina` (`mina/`) | Mina the Hollower | `mina-ycd.md` |
| Capcom (özel) | `.fsd` / `.msg` / `.atm` mesaj tabloları, oyun harf tablosu | `dmc1` (`dmc1/`) | Devil May Cry (1) | `dmc1.md` |
| Konami M2 | `.psb.m` + `.bin` arşivi, mdf, PSB | `m2text` (`m2text/`; arşiv: `core/archives/m2.py`, `psb.py`) | Metal Gear Solid Master Collection Vol. 1 (MGS1) | `m2.md` |
| Falcom | NNI arşivi (`.ni`/`.na`), XSO betikleri, arayüz XML'i | `ysorigin` (`ysorigin/`) | Ys Origin | `ys-origin.md` |
| Genel | SubRip altyazı (`.srt`) | `srt` (`srt/`) | Ys Origin giriş altyazısı | `ys-origin.md` ("Altyazı") |
| Vanillaware / CRI | CPK + CRILAYLA kapsayıcısı, FMSB MsgSheet | `fmsb` (`fmsb/`; arşiv: `core/archives/cpk.py`) | Unicorn Overlord | `unicorn-overlord.md` |

Tanınmayan oyunlarda desteklenmeyen örnekler (`docs/uyumluluk.md`): Avatar Legends (özel PACK), Devil May Cry 2/3
(`.nbz`), Scott Pilgrim EX (`.zpbn`), MIO (`.gin`), Animal Well (RomFS yok).

## Font ve grafik

| Konu | Not dosyası | Kod |
|---|---|---|
| Unity TextMeshPro fontları, TTF/OTF yaması | `tmp-font.md` | `core/fontpatch/` (`sdf.py`, `tmp.py`, `unity.py`, `ttf.py`) |
| Switch sistem fontu (`.bfttf`/`.bfotf`) | `tmp-font.md` ("Vektör fontlar") | `core/fontpatch/switchfont.py` |
| BMFont (Ys Origin) | `ys-origin.md` ("Yazı tipi yaması") | `core/fontpatch/bmfont.py`, `ys_fonts.py` |
| Oyun resimlerindeki yazılar (DMC1, Ys Origin) | `dmc1.md`, `ys-origin.md` ("Grafikler") | `core/fontpatch/dmc1_*.py`, `labels.py`, `bc7.py`, `ys_graphics.py` |

## Altyapı (kapsayıcılar ve şifreleme)

| Konu | Not dosyası | Kod |
|---|---|---|
| NSZ / NCZ (sıkıştırılmış NSP) | `nsz.md` | `core/container/ncz.py` |
| NCA (başlık, bölümler, şifreleme) | `nca.md` | `core/container/nca.py`, `crypto.py` |
| BKTR güncelleme yamaları | `bktr.md` | `core/container/patch.py`, `buckettree.py` |
| RomFS ve PFS0 | `romfs.md` | `core/container/romfs.py`, `pfs0.py` |
| CNMT, NACP, bilet | `cnmt-nacp-ticket.md` | `core/container/metadata.py` |
| İç arşivler: SARC, Yaz0, ZSTD | `archives.md` | `core/archives/` |

## Yeni not eklerken
Her not: kod yolu, test dosyası, "nerede ne var" tablosu, biçim yapısı, **kontrol kodları**, geri yazma kuralları,
bilinen tuzaklar, cihazda denendi mi. Satırı bu tabloya ve `docs/uyumluluk.md`'ye ekle. Oyundan uzun metin alıntılama.
