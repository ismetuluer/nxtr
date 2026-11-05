# PyInstaller tarifi: kurulumsuz çalışan taşınabilir klasör (onedir).
#
#   pyinstaller --noconfirm packaging/NXTR.spec
#
# Çıktı dist/NXTR/ klasörüdür; NXTR.exe çift tıklanınca açılır. Klasör olduğu gibi zip'lenip
# dağıtılır. Uygulama hiçbir anahtar içermez; anahtar dosyasını kullanıcı kendisi gösterir.
# onefile yerine onedir: her açılışta geçici klasöre açma gecikmesi olmaz ve virüs tarayıcıları daha az
# yanlış alarm verir.
import importlib.metadata
import os
import re
import sys

from packaging.requirements import Requirement
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

sys.path.insert(0, SPECPATH)
from stdlib_modules import stdlib_hidden_imports  # noqa: E402 - SPECPATH eklendikten sonra

datas = collect_data_files("nxceviri", excludes=["**/__pycache__/**"])
binaries = []
hiddenimports = ["keyring.backends.Windows"]
# Kullanıcı eklentileri (%LOCALAPPDATA%\NXCeviri\eklentiler) pakette yalnızca düz kaynak dosyası olarak yüklenir
# ve içe aktaracakları modüller PyInstaller'ın çözümlemesinde görünmez. Bu yüzden (1) uygulamanın kendi modüllerinin
# tamamı (eklentiler yerleşik yardımcıları kullanabilsin) ve (2) standart kütüphanenin tamamı paketlenir;
# aksi hâlde eklentinin `import csv/zipfile/xml...` gibi bir satırı yalnızca .exe'de patlar.
EXCLUDED = ["tkinter", "pytest", "mypy", "ruff"]  # stdlib listesi packaging/stdlib_modules.py'dedir
hiddenimports += collect_submodules("nxceviri")
hiddenimports += stdlib_hidden_imports()
for package in ("UnityPy",):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

# Lisans bildirimleri paketin köküne, her bağımlılığın kendi lisans dosyaları lisanslar/<paket>/ altına girer
# (BSD/MIT/Apache/LGPL koşulu: dağıtımla birlikte lisans metni verilir). Kök dizin: bu tarifin bir üst klasörü.
root = os.path.abspath(os.path.join(SPECPATH, ".."))
datas += [(os.path.join(root, "LICENSE"), "."), (os.path.join(root, "THIRD_PARTY_NOTICES.md"), ".")]
_LICENSE_NAME = re.compile(r"(licen[sc]e|copying|notice)", re.IGNORECASE)
_seen: set[str] = set()


def _collect_licenses(name: str) -> None:
    key = re.sub(r"[-_.]+", "-", name).lower()
    if key in _seen:
        return
    _seen.add(key)
    try:
        dist = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        # Sessizce atlamak lisans metninin pakete girmemesine yol açar; derleme açık hatayla durur.
        raise SystemExit(f"Lisans toplanamadı: '{name}' dağıtımı kurulu değil. Gerçek dağıtım adını yazın ya da kurun.")
    for file in dist.files or []:
        if "dist-info" in file.parts[0] and _LICENSE_NAME.search(file.name):
            datas.append((str(dist.locate_file(file)), os.path.join("lisanslar", key)))
    for text in dist.requires or []:
        requirement = Requirement(text)
        # Ek (extra) ve bu ortama uymayan koşullu (ör. başka işletim sistemi) bağımlılıklar kurulu olmayabilir.
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            _collect_licenses(requirement.name)


for _name in ("PySide6-Essentials", "cryptography", "zstandard", "UnityPy", "httpx", "keyring", "fonttools", "lz4", "Pillow"):
    _collect_licenses(_name)

a = Analysis(
    ["../nxceviri/__main__.py"],
    pathex=[".."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=EXCLUDED,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NXTR",
    console=False,
    icon="../nxceviri/gui/appicon/nxtr.ico",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="NXTR", upx=False)
