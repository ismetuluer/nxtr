# Biçim notları dizini

Bir oyunun metin biçimi daha önce çözülmüş mü? Önce buraya bak; çözülmüşse yeni kod yazma, uygulamayı kullan.
Oyun durumları için `docs/uyumluluk.md`, yeni oyun için `docs/rehber/yeni-oyun.md`.

## Metin biçimleri: motor → biçim → eklenti → not

Eklenti sütunundaki adlar `nxceviri/core/formats/registry.py` içindeki `name` değeridir; yollar `nxceviri/core/formats/`
altındadır.

| Motor / aile | Biçim | Eklenti (kod yolu) | Not dosyası |
|---|---|---|---|
| LMS | MSBT (`MsgStdBn`), SARC/Yaz0/ZSTD kapsayıcıları | `msbt` (`msbt/`) | `msbt.md`, `archives.md` |
| Unity | Unity Localization string tabloları (AssetBundle) | `unity` (`unity/unity.py`) | `unity.md` |
| Unity | I2 Localization (ham bayt, tip ağacı yok) | `unity` (`unity/i2.py`) | `unity.md` ("I2 Localization") |
| Unity | Düz `TextAsset` (SRT + TSV) ve `Locoliser` önbelleği | `unity` (`unity/loctext.py`, `locoliser.py`) | `unity.md` ("Düz metin yerelleştirmesi") |
| Unity | `Localization` nesnesi (`[SerializeReference]` kayıt defteri) | `unity` (`unity/serializeref.py`) | `unity-serializereference.md` |
| Unity (metin Unity dışında) | AGAR/WAD arşivi, `.lin` betikleri, `.pak` tabloları | `wadlin` (`wadlin/`) | `wad-lin.md` |
| Unreal Engine | `.locres`, `.pak` | `unreal` (`unreal/locres.py`) | `unreal.md` |
| Switch mesaj biçimi | `.dat` + `.tbl` mesaj dosyaları (GFMSG) | `gfmsg` (`gfmsg/`) | `gfmsg.md` |
| Özel | YCD (`.yc`), `pak.yc` | `pakyc` (`pakyc/`) | `pak-yc.md` |
| Özel | `.fsd` / `.msg` / `.atm` mesaj tabloları, oyun harf tablosu | `fsdmsg` (`fsdmsg/`) | `fsd-msg.md` |
| M2 | `.psb.m` + `.bin` arşivi, mdf, PSB | `psbtext` (`psbtext/`; arşiv: `core/archives/psb_archive.py`, `psb.py`) | `psb.md` |
| Özel | NNI arşivi (`.ni`/`.na`), XSO betikleri, arayüz XML'i | `nnitext` (`nnitext/`) | `nni.md` |
| Genel | SubRip altyazı (`.srt`) | `srt` (`srt/`) | `nni.md` ("Altyazı") |
| CRI | CPK + CRILAYLA kapsayıcısı, FMSB MsgSheet | `fmsb` (`fmsb/`; arşiv: `core/archives/cpk.py`) | `cpk-fmsb.md` |

Bu biçimlerin hangi durumda olduğu (okuma, yazma, font) için `docs/uyumluluk.md`. Henüz çözülmemiş biçimler orada
"çözülmedi" olarak listelenir.

## Font ve grafik

| Konu | Not dosyası | Kod |
|---|---|---|
| Unity TextMeshPro fontları, TTF/OTF yaması | `tmp-font.md` | `core/fontpatch/` (`sdf.py`, `tmp.py`, `unity.py`, `ttf.py`) |
| Switch sistem fontu (`.bfttf`/`.bfotf`, `.zs`) | `switch-font.md` | `core/fontpatch/switchfont.py`, `core/qa/fonts.py` |
| BMFont | `nni.md` ("Yazı tipi yaması") | `core/fontpatch/bmfont.py`, `nni_fonts.py` |
| Oyun resimlerindeki yazılar (`.fsd`/`.msg` ve NNI biçimleri) | `fsd-msg.md`, `nni.md` ("Grafikler") | `core/fontpatch/fsdmsg*.py`, `labels.py`, `bc7.py`, `nni_graphics.py` |

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
