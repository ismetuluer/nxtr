# Üçüncü taraf bildirimleri

NX Çeviri Stüdyosu kendi kodu için MIT lisansıyla ([LICENSE](LICENSE)) dağıtılır. Aşağıdaki bileşenler kendi
lisanslarıyla dağıtılır. Taşınabilir pakette (`NXTR-<sürüm>-windows.zip`) her bağımlılığın kendi lisans dosyaları
`lisanslar/<paket>/` klasöründe, bu bildirim ve `LICENSE` paketin kökünde bulunur.

Lisans bilgileri, geliştirme ortamında kurulu paketlerin üst verisinden (`importlib.metadata`) okunmuştur.

## Doğrudan bağımlılıklar

| Paket | Sürüm | Lisans |
|---|---|---|
| PySide6-Essentials (Qt for Python) | 6.12.0 | LGPL-3.0-only (ya da GPL-2.0-only / GPL-3.0-only / ticari) |
| shiboken6 (PySide6 ile gelir) | 6.12.0 | LGPL-3.0-only (ya da GPL-2.0-only / GPL-3.0-only / ticari) |
| cryptography | 50.0.2 | Apache-2.0 veya BSD-3-Clause |
| zstandard | 0.25.0 | BSD-3-Clause |
| UnityPy | 1.25.4 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| keyring | 25.7.0 | MIT |
| fonttools | 4.67.0 | MIT |
| lz4 | 4.4.5 | BSD |
| Pillow | 13.0.0 | MIT-CMU |

## Dolaylı çalışma zamanı bağımlılıkları

Doğrudan bağımlılıkların gerektirdiği paketler (üst verideki lisans alanı):

| Paket | Sürüm | Lisans |
|---|---|---|
| anyio | 4.15.1 | MIT |
| archspec | 0.2.6 | Apache-2.0 veya MIT |
| astc-encoder-py | 0.1.12 | MIT |
| attrs | 26.1.0 | MIT |
| brotli | 1.2.0 | MIT |
| certifi | 2026.10.19 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0 |
| etcpak | 0.9.15 | MIT |
| fmod-toolkit | 0.1.3 | MIT |
| fsspec | 2026.9.0 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| jaraco.classes | 3.4.0 | MIT |
| jaraco.context | 6.1.2 | MIT |
| jaraco.functools | 4.6.0 | MIT |
| more-itertools | 11.2.1 | MIT |
| pycparser | 3.11 | BSD-3-Clause |
| pyfmodex | 0.7.2 | MIT |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause |
| texture2ddecoder | 1.0.6 | MIT |
| tpk-ar | 0.2.4 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |

Bu paketlerin tam lisans metinleri paketlerin kendi dağıtımlarında (pakette `lisanslar/<paket>/`) yer alır.

## Python

Taşınabilir paket, CPython yorumlayıcısını ve standart kütüphanesini içerir. Lisansı Python Software Foundation
License (PSF-2.0)'dır: <https://docs.python.org/3/license.html>.

## Qt ve PySide6 için LGPL-3.0 notu

Qt ve PySide6 bu uygulamada **GNU LGPL sürüm 3** kapsamında kullanılır. Taşınabilir pakette Qt kütüphaneleri
(`PySide6/` altındaki `Qt6*.dll` dosyaları ve Python eklenti modülleri) uygulamadan **ayrı dinamik kütüphaneler**
olarak durur; uygulamanın kodu bunlara statik olarak bağlanmaz. Kullanıcı bu DLL'leri LGPL-3.0'ın izin verdiği
şekilde kendi değiştirilmiş sürümleriyle değiştirebilir. Uygulamanın kaynak kodu bu depodadır; Qt'nin kaynak
kodu <https://download.qt.io/> adresinden, PySide6'nın kaynak kodu <https://code.qt.io/cgit/pyside/pyside-setup.git/>
adresinden edinilebilir. Qt/PySide6'da değişiklik yapılmamıştır.

- GNU LGPL-3.0 metni: <https://www.gnu.org/licenses/lgpl-3.0.txt>
- GNU GPL-3.0 metni (LGPL-3.0 buna atıf yapar): <https://www.gnu.org/licenses/gpl-3.0.txt>

## Simgeler

`nxceviri/gui/icons/`: [Lucide](https://lucide.dev) simgeleri, ISC lisansı. Tam metin:
`nxceviri/gui/icons/LICENSE`.

## Türkçe yazım denetimi sözlüğü

`nxceviri/assets/spell/tr.bloom`: TDD (Turkish Data Depository) hunspell-tr sözlüğünden türetilmiştir,
Mozilla Public License 2.0 (MPL-2.0). Tam metin ve kaynak adresi: `nxceviri/assets/spell/LICENSE-MPL-2.0.txt`,
`nxceviri/assets/spell/README.txt`. MPL-2.0 yalnızca bu dosya için geçerlidir; uygulamanın kalanını bağlamaz.

## Yazı tipleri

`nxceviri/assets/fonts/`: değiştirilmemiş, SIL Open Font License 1.1 (OFL) altında iki yazı tipi.
Lisans metinleri yazı tiplerinin yanındadır.

| Yazı tipi | Telif | Lisans dosyası |
|---|---|---|
| Kaushan Script | Pablo Impallari, Igino Marini | `KaushanScript-OFL.txt` |
| Pirata One | Rodrigo Fuenzalida, Nicolas Massi | `PirataOne-OFL.txt` |
