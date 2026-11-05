"""Ajan araçları (`python -m nxceviri.arac`): teşhis, ara, doğrula. Elle üretilmiş küçük verilerle."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import pytest
import zstandard

from nxceviri.arac import KOMUT_MODULLERI, main, ortak
from nxceviri.arac.ara import Aranan
from nxceviri.arac.metin_sezgisi import sezgi
from nxceviri.arac.teshis import RAPOR_ADI, UYARI, imza_adi
from nxceviri.core.formats import registry
from nxceviri.core.formats.base import Context, FormatError, TextEntry
from nxceviri.core.plugins.loader import PluginInfo, PluginReport
from tests import nxbuild
from tests.conftest import BASE_TID, GameFiles

CUMLELER = (
    "The quick brown fox jumps over the lazy dog.",
    "Welcome back to the village, traveler.",
    "Press the button to open the heavy door.",
    "Your journey begins in the old forest today.",
)


def _utf16(metin: str) -> bytes:
    return metin.encode("utf-16-le")


# --- komut düzeni -------------------------------------------------------------------------


def test_komut_modulleri_ve_kullanim_hatasi(capsys: pytest.CaptureFixture[str]) -> None:
    assert {"nxceviri.arac.teshis", "nxceviri.arac.ara", "nxceviri.arac.dogrula"} <= set(KOMUT_MODULLERI)
    with pytest.raises(SystemExit) as cikis:
        main([])
    assert cikis.value.code == 2
    with pytest.raises(SystemExit) as cikis:
        main(["ara"])  # eksik argümanlar
    assert cikis.value.code == 2
    capsys.readouterr()


def test_anahtar_yoksa_acik_mesaj(
    game: GameFiles, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ortak, "ayardaki_yol", lambda _anahtar: None)
    assert main(["ara", "Merhaba", str(game.base_nsp)]) == 1
    err = capsys.readouterr().err
    assert "prod.keys dosyası belirtilmedi" in err
    assert "--anahtar" in err


def test_anahtar_ayardan_okunur(game: GameFiles, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ortak, "ayardaki_yol", lambda anahtar: game.keys_path if anahtar == ortak.AYAR_PROD_KEYS else None
    )
    assert main(["ara", "Start Game", str(game.base_nsp)]) == 0


# --- ara ----------------------------------------------------------------------------------


def test_aranan_parca_sinirinda_eslesme_kacmaz() -> None:
    aranan = Aranan("merhaba", harf_duyarsiz=False)
    veri = b"x" * 10 + b"merhaba" + b"y" * 10
    for kes in range(11, 17):
        bulgular = list(aranan.tara([veri[:kes], veri[kes:]]))
        assert [b[0] for b in bulgular] == [10], kes


def test_aranan_kodlamalar_ve_harf_duyarsiz() -> None:
    aranan = Aranan("Start", harf_duyarsiz=True)
    veri = b"..start.." + b"\0" * 4 + _utf16("START") + b"\0" * 4 + "Start".encode("utf-16-be")
    kodlamalar = {k for _o, k, _s in aranan.tara([veri])}
    assert kodlamalar == {"UTF-8 / Shift-JIS", "UTF-16LE", "UTF-16BE"}
    assert list(Aranan("Start", harf_duyarsiz=False).tara([b"start"])) == []
    japonca = "こんにちは".encode("shift_jis")
    assert [k for _o, k, _s in Aranan("こんにちは", False).tara([b"ab" + japonca])] == ["Shift-JIS"]


def test_ara_klasorde_ic_ice_arsivde_bulur(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kok = tmp_path / "romfs"
    (kok / "Msg").mkdir(parents=True)
    cumle = "Merhaba dünya, hoş geldin yolcu"
    (kok / "Msg" / "a.sarc").write_bytes(nxbuild.build_sarc({"Metin/x.txt": b"\x00\x00" + _utf16(cumle)}))
    ic = nxbuild.build_sarc({"Metin/y.txt": cumle.encode()})
    (kok / "Msg" / "b.sarc.zs").write_bytes(zstandard.ZstdCompressor().compress(ic))
    (kok / "ham.bin").write_bytes(b"\x01" * 50 + "MERHABA DÜNYA, HOŞ GELDİN YOLCU".encode("shift_jis", "ignore"))

    kod = main(["ara", cumle, str(kok)])
    cikti = capsys.readouterr().out
    assert kod == 0
    assert "Msg/a.sarc>Metin/x.txt  ofset 0x2" in cikti.replace("  ", "  ")
    assert "UTF-16LE" in cikti
    assert "Msg/b.sarc.zs>b.sarc>Metin/y.txt" in cikti
    assert f"[{cumle}]" in cikti  # kesit, eşleşmeyi köşeli parantezle gösterir

    assert main(["ara", cumle.upper(), str(kok), "--harf-duyarsiz"]) == 0
    assert main(["ara", cumle.upper(), str(kok)]) == 1
    assert "bulunamadı" in capsys.readouterr().out


def test_ara_nsp_icinde_ve_anahtar_sizmaz(game: GameFiles, capsys: pytest.CaptureFixture[str]) -> None:
    kod = main(["ara", "Start Game", str(game.base_nsp), "--anahtar", str(game.keys_path)])
    out, err = capsys.readouterr()
    assert kod == 0
    assert "Message/Ana_Menü.msbt" in out
    for gizli in game.keys.all_secret_hex():
        assert gizli not in out + err


def test_ara_en_fazla_siniri(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.txt").write_bytes(b"abc " * 100)
    assert main(["ara", "abc", str(tmp_path), "--en-fazla", "5"]) == 0
    out = capsys.readouterr().out
    assert "5 bulgu" in out
    assert "sınıra" in out


def test_ara_buyuk_arsivler_icin_not(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "veri.pak").write_bytes(b"xx hedef metin xx")
    assert main(["ara", "hedef metin", str(tmp_path)]) == 0
    assert "içine bakılmadı" in capsys.readouterr().out


def test_ara_bos_metin(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ara", "", str(tmp_path)]) == 1
    assert "boş" in capsys.readouterr().err


# --- metin sezgisi ------------------------------------------------------------------------


def test_metin_sezgisi() -> None:
    utf8 = b"\x00\x01\x02" * 20 + "\n".join(CUMLELER).encode() + bytes(range(256))
    sonuc = sezgi(utf8)
    assert sonuc is not None
    assert sonuc.kodlama == "UTF-8"
    assert sonuc.ornekler[0] == CUMLELER[0]

    utf16 = b"\xff\xfe\x01\x00" * 10 + _utf16("\n".join(CUMLELER))
    sonuc16 = sezgi(utf16)
    assert sonuc16 is not None
    assert sonuc16.kodlama == "UTF-16LE"
    assert len(sonuc16.ornekler) == 3
    assert all(len(o) <= 80 for o in sonuc16.ornekler)

    assert sezgi(os.urandom(4096)) is None
    assert sezgi(bytes(range(256)) * 16) is None
    assert sezgi(b"") is None


def test_imza_adlandirma() -> None:
    assert imza_adi(b"SARC", "a.sarc") == "SARC arşivi"
    assert imza_adi(b"Yaz0", "a.szs") == "Yaz0 sıkıştırma"
    assert imza_adi(b"\x28\xb5\x2f\xfd", "a.zs") == "ZSTD sıkıştırma"
    assert imza_adi(b"MsgS", "a.msbt") == "MsgStdBn (MSBT)"
    assert imza_adi(b"Unit", "a.bundle") == "UnityFS paketi"
    assert imza_adi(b"\x00\x01\x02\x03", "Paks/oyun.pak") == "PAK (uzantıdan)"
    assert imza_adi(b"\x00\x01\x02\x03", "x.bin") == ""


# --- teşhis -------------------------------------------------------------------------------


def test_teshis_raporu(game: GameFiles, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cikti = tmp_path / "çıktı klasörü"
    kod = main(
        [
            "teshis",
            str(game.base_nsp),
            str(game.update_nsp),
            str(game.dlc_nsp),
            "--anahtar",
            str(game.keys_path),
            "--cikti",
            str(cikti),
        ]
    )
    out, err = capsys.readouterr()
    assert kod == 0
    rapor = (cikti / RAPOR_ADI).read_text(encoding="utf-8")
    assert UYARI in rapor.splitlines()[2]
    assert f"{BASE_TID:016X}" in rapor
    assert "Güncelleme: v65536" in rapor
    assert "AddOnContent" not in rapor  # iç adlar değil, içerik başlıkları
    assert "`.msbt`" in rapor
    assert "MsgStdBn (MSBT)" in rapor
    assert "SARC" in rapor or "ZSTD sıkıştırma" in rapor
    assert "## Motor tahmini" in rapor
    assert "MSBT" in rapor.split("## Uygulamanın tanıdığı dosyalar")[1]
    assert "docs/rehber/yeni-oyun.md" in rapor
    assert not list(cikti.glob("*.gecici"))
    for gizli in game.keys.all_secret_hex():
        assert gizli not in rapor + out + err


def test_teshis_aday_metin_dosyasi(tmp_path: Path) -> None:
    keys = nxbuild.TestKeys.random()
    anahtar = keys.write(tmp_path / "prod.keys")
    diyalog = b"\x01\x00\x00\x00" * 40 + _utf16("\n".join(CUMLELER) + "\n") + b"\x00" * 64
    paket = nxbuild.build_package(
        keys,
        kind="base",
        title_id=BASE_TID,
        application_id=BASE_TID,
        version=0,
        romfs_files={"Data/diyalog.dat": diyalog, "Data/ikili.dat": os.urandom(2048)},
    )
    nsp = tmp_path / "oyun.nsp"
    nsp.write_bytes(paket.nsp)
    assert main(["teshis", str(nsp), "--anahtar", str(anahtar), "--cikti", str(tmp_path)]) == 0
    rapor = (tmp_path / RAPOR_ADI).read_text(encoding="utf-8")
    bolum = rapor.split("## Aday metin dosyaları")[1].split("##")[0]
    assert "Data/diyalog.dat" in bolum
    assert "UTF-16LE" in bolum
    assert CUMLELER[0] in bolum
    assert "Data/ikili.dat" not in bolum


def test_teshis_olmayan_dosya(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["teshis", str(tmp_path / "yok.nsp"), "--anahtar", str(tmp_path / "prod.keys")]) == 1
    assert "bulunamadı" in capsys.readouterr().err


# --- doğrula ------------------------------------------------------------------------------


class _SahteEklenti:
    """`FAKE` imzalı, satır başına `anahtar=değer` tutan sahte biçim."""

    name = "sahte"
    label = "Sahte"
    candidates_only = False
    path_suffixes: tuple[str, ...] = (".fake",)

    def detect(self, path: str, head: bytes) -> bool:
        return head.startswith(b"FAKE")

    def collect_context(self, data: bytes, path: str) -> dict[object, object]:
        return {}

    def language(self, data: bytes) -> str | None:
        return None

    def _satirlar(self, data: bytes) -> list[tuple[str, str]]:
        govde = data[4:].decode("utf-8")
        return [tuple(s.split("=", 1)) for s in govde.splitlines()]  # type: ignore[misc]

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        return [TextEntry(k, i, v, ()) for i, (k, v) in enumerate(self._satirlar(data))]

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        govde = "".join(f"{k}={translations.get(k, v)}\n" for k, v in self._satirlar(data))
        return b"FAKE" + govde.encode("utf-8")


class _KayipEklenti(_SahteEklenti):
    """Değişikliksiz bile son satır sonunu atan, bayt eşitliğini bozan eklenti."""

    name = "kayip"

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        return super().inject(data, translations).rstrip(b"\n")


class _YokSayanEklenti(_SahteEklenti):
    """Çevirileri hiç yazmayan eklenti: işaret metni geri okunamaz."""

    name = "yoksayan"

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        return data


class _PatlayanEklenti(_SahteEklenti):
    name = "patlayan"

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        raise FormatError("başlık bozuk", "Dosya kesilmiş olabilir.")


@pytest.fixture
def sahte_klasor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        registry,
        "BUILTIN_PLUGINS",
        (_SahteEklenti(), _KayipEklenti(), _YokSayanEklenti()),
    )
    # Kullanıcı eklentisi olarak yüklenmiş bir eklenti de bulunmalı.
    monkeypatch.setattr(
        registry,
        "_user_report",
        PluginReport((PluginInfo("patlayan", "1", "t", None, 1, (), tur="patlayan", plugin=_PatlayanEklenti()),)),
    )
    kok = tmp_path / "romfs"
    (kok / "Veri").mkdir(parents=True)
    govde = b"FAKE" + "a=Merhaba\nb=Nasılsın\nc=İyiyim çok\nd=Görüşürüz\ne=Hoşça kal\n".encode()
    (kok / "Veri" / "bir.fake").write_bytes(govde)
    (kok / "Veri" / "iki.fake").write_bytes(b"FAKE" + b"x=Tek\n")
    (kok / "Veri" / "baska.bin").write_bytes(b"NOPE")
    return kok


def test_dogrula_gecen_eklenti(sahte_klasor: Path, capsys: pytest.CaptureFixture[str]) -> None:
    once = {p: p.read_bytes() for p in sahte_klasor.rglob("*") if p.is_file()}
    kod = main(["dogrula", "sahte", str(sahte_klasor)])
    out = capsys.readouterr().out
    assert kod == 0
    assert "GEÇTİ  Veri/bir.fake  (5 girdi)" in out
    assert "GEÇTİ  Veri/iki.fake  (1 girdi)" in out
    assert "baska.bin" not in out
    assert "2 dosya sınandı, 2 geçti, 0 kaldı" in out
    assert {p: p.read_bytes() for p in sahte_klasor.rglob("*") if p.is_file()} == once


def test_dogrula_bozuk_eklenti_kalir(sahte_klasor: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["dogrula", "kayip", str(sahte_klasor)]) == 1
    out = capsys.readouterr().out
    assert "KALDI  Veri/bir.fake" in out
    assert "ilk fark ofseti 0x" in out
    assert "0 geçti, 2 kaldı" in out


def test_dogrula_isaret_geri_okunamazsa_kalir(sahte_klasor: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["dogrula", "yoksayan", str(sahte_klasor)]) == 1
    assert "işaret metni geri okunamadı" in capsys.readouterr().out
    assert main(["dogrula", "patlayan", str(sahte_klasor)]) == 1
    assert "başlık bozuk" in capsys.readouterr().out


def test_dogrula_bilinmeyen_eklenti_adlari_listeler(sahte_klasor: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["dogrula", "olmayan", str(sahte_klasor)]) == 1
    err = capsys.readouterr().err
    assert "'olmayan' adlı bir eklenti yok" in err
    assert "sahte" in err
    assert "msbt" not in err  # sahte kayıt defteri


def test_dogrula_hicbir_dosya_taninmazsa_kalir(
    sahte_klasor: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bos = tmp_path / "bos"
    bos.mkdir()
    (bos / "x.bin").write_bytes(b"NOPE")
    assert main(["dogrula", "sahte", str(bos)]) == 1
    assert "hiçbir dosyayı tanımadı" in capsys.readouterr().out


def test_dogrula_msbt_gercek_kayit_defterinde(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kok = tmp_path / "romfs"
    kok.mkdir()
    msbt = nxbuild.build_msbt(
        [("Menu_Start", ["Start Game"]), ("Menu_Hello", ["Hello ", ("tag", 0, 3, b"\x01\x00"), "!"])]
    )
    (kok / "Ana.msbt").write_bytes(msbt)
    (kok / "Msg.sarc").write_bytes(nxbuild.build_sarc({"Ortak.msbt": msbt}))
    assert main(["dogrula", "msbt", str(kok)]) == 0
    out = capsys.readouterr().out
    assert "GEÇTİ  Ana.msbt" in out
    assert "GEÇTİ  Msg.sarc>Ortak.msbt" in out


def test_dogrula_nsp_icinde(game: GameFiles, capsys: pytest.CaptureFixture[str]) -> None:
    kod = main(["dogrula", "msbt", str(game.base_nsp), "--anahtar", str(game.keys_path)])
    out, err = capsys.readouterr()
    assert "GEÇTİ  Message/Ana_Menü.msbt" in out
    assert "Mals/TRtr.Product.sarc.zs>TRtr.Product.sarc>Msg/Ortak.msbt" in out
    # BASE_FILES içindeki Bozuk.msbt geçerli bir MSBT değil; doğrulama bunu yakalamalı.
    assert kod == 1
    assert "KALDI  Mals/TRtr.Product.sarc.zs>TRtr.Product.sarc>Msg/Bozuk.msbt" in out
    assert "2 geçti, 1 kaldı" in out
    for gizli in game.keys.all_secret_hex():
        assert gizli not in out + err
