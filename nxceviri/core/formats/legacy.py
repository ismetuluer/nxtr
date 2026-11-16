"""0.59.0 ve önceki sürümlerin yazdığı kalıcı değerlerin bugünkü karşılıkları.

Biçim kimlikleri, motor anahtarları ve tarama ayrıntıları eskiden oyun ve firma adlarını taşıyordu; bugün biçim
adlarıyla yazılıyor. Eski değerler `.nxproj` dosyalarında durur ve proje dönüştürülmez (eski sürüm de açabilsin):
okuma anında buradaki tek tabloyla yeniye çözülür. Eski değerlerin kaynakta kaldığı tek yer bu modüldür.
"""

from __future__ import annotations

import os

#: Biçim kimliği (eklenti `name`, `FileKind` değeri, `text_files.format`, `scan_files.kind`).
FORMAT_IDS = {
    "danganronpa": "wadlin",
    "dmc1": "fsdmsg",
    "mina": "pakyc",
    "ysorigin": "nnitext",
    "m2text": "psbtext",
}

#: Motor tahmini anahtarı (`scans.engine`).
ENGINE_IDS = {
    "m2": "psb",
    "falcom": "nni",
    "vanillaware": "cpk",
    "spike": "wad",
    "nintendo": "lms",
    "gamefreak": "gfmsg",
}

#: Tarama ayrıntısı (`scan_files.detail`).
DETAILS = {
    "M2 arşivi (mdf)": "PSB arşivi (mdf)",
    "Falcom NNI arşivi": "NNI arşivi",
    "CRI CPK arşivi": "CPK arşivi",
    "Spike Chunsoft WAD arşivi": "WAD arşivi",
    "MSBT (Nintendo LMS metni)": "MSBT (LMS metni)",
    "Game Freak mesaj dosyası": "GFMSG mesaj dosyası",
    "Game Freak etiket tablosu (AHTB)": "AHTB etiket tablosu",
    "Devil May Cry sahne dosyası (.fsd)": "FSD sahne dosyası (.fsd)",
    "Devil May Cry durum ve eşya metinleri (st_init.dat)": "Durum ve eşya metinleri (st_init.dat)",
    "Devil May Cry kayıt ekranı mesajları (memicon.dat)": "Kayıt ekranı mesajları (memicon.dat)",
    "Devil May Cry başarım/galeri metni (.atm)": "Başarım/galeri metni (.atm)",
    "Devil May Cry mesaj dosyası (.msg)": "MSG mesaj dosyası (.msg)",
    "Yacht Club YCD paketi (Mina the Hollower)": "YCD paketi (.yc)",
    "Ys Origin arayüz dizgeleri (XML)": "Arayüz dizgeleri (XML)",
    "M2 PSB metni": "PSB metni",
    "Ys Origin betik metni (XSO)": "XSO betik metni",
    "Vanillaware MsgSheet (FMSB)": "FMSB MsgSheet",
    "Danganronpa betiği / metin tablosu": "LIN betiği / PAK metin tablosu",
}

#: Motor kanıtlarının adı (`scans.engine_evidence` içinde "ad: sayı").
EVIDENCE_LABELS = {
    "M2 arşivleri (mdf)": "PSB arşivleri (mdf)",
    "M2 PSB metin dosyaları": "PSB metin dosyaları",
    "Falcom NNI arşivleri": "NNI arşivleri",
    "Ys Origin betik/arayüz metinleri": "NNI betik/arayüz metinleri",
    "CRI CPK arşivleri": "CPK arşivleri",
    "Vanillaware MsgSheet dosyaları": "FMSB MsgSheet dosyaları",
    "Spike Chunsoft WAD arşivleri": "WAD arşivleri",
    "Danganronpa betik ve metin tabloları": "LIN/PAK betik ve metin tabloları",
    "Game Freak mesaj dosyaları": "GFMSG mesaj dosyaları",
    "Game Freak paketleri (.gfpak)": "GFPAK paketleri (.gfpak)",
    "NintendoWare kaynakları (BFRES/BNTX/BFFNT)": "BFRES/BNTX/BFFNT kaynakları",
}

#: Ortam değişkeni → eski adı (yeni ad yoksa eskisi okunur).
ENV_NAMES = {
    "NXCEVIRI_FSD_GRAFIK": "NXCEVIRI_DMC1_GRAFIK",
    "NXCEVIRI_NNI_GRAFIK": "NXCEVIRI_YS_GRAFIK",
}


def format_id(value: str) -> str:
    """Biçim kimliğinin bugünkü değeri; tabloda yoksa (yeni kimlik, kullanıcı eklentisi) olduğu gibi."""
    return FORMAT_IDS.get(value, value)


def engine_id(value: str) -> str:
    return ENGINE_IDS.get(value, value)


def detail(value: str) -> str:
    return DETAILS.get(value, value)


def evidence(item: str) -> str:
    """Motor kanıtı ("ad: sayı"); adı eski sürümünkiyse bugünkü adıyla."""
    label, sep, count = item.rpartition(": ")
    return f"{EVIDENCE_LABELS.get(label, label)}{sep}{count}" if sep else item


def environ(name: str) -> str | None:
    """Ortam değişkeni; yeni adı yoksa (boşsa) eski adı okunur."""
    old = ENV_NAMES.get(name)
    return os.environ.get(name) or (os.environ.get(old) if old else None)
