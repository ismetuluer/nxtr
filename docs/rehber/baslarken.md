# Başlarken — bu bilgisayara kurulum

## Ne zaman okunur
Kullanıcı projeyi ilk kez bilgisayarına kurduruyor ya da "çalışmıyor / paket bulunamadı" diyor. Önce `AGENTS.md`'yi
oku. Bu rehber kaynak koddan çalışma içindir; hazır `NXTR.exe` paketi için Python gerekmez (bkz. `KURULUM.md` §0).

## Adımlar

Kullanıcı Windows'ta ve çoğu zaman programcı değildir: her komutun ne yaptığını bir cümleyle söyle.

1. **Python ve git var mı?**
   ```
   py --list
   git --version
   ```
   `py --list` çıktısında 3.12, 3.13 veya 3.14 görünmeli (geliştirmede 3.13 kullanılıyor; `pyproject.toml`:
   `requires-python = ">=3.12,<3.15"`). Yoksa kullanıcıdan https://www.python.org adresinden kurmasını iste
   ("Add python.exe to PATH" ve "py launcher" işaretli olsun); git için https://git-scm.com. Kurulumları ajan
   kendiliğinden yapmaz, kullanıcı onaylar.
2. **Depoyu al** (kullanıcı zaten klasörü indirdiyse atla): `git clone <depo adresi>`; adresi kullanıcı verir.
   Sonra proje klasörüne geç.
3. **Sanal ortam ve paketler** (birkaç dakika, internet gerekir):
   ```
   py -3.13 -m venv .venv
   .venv\Scripts\python -m pip install --upgrade pip
   .venv\Scripts\python -m pip install -e ".[dev]"
   ```
   3.13 yoksa `-3.12` ya da `-3.14` kullan. `[dev]` test araçlarını (pytest, pytest-qt, ruff, mypy) getirir; yalnızca
   uygulamayı çalıştıracaksa `-e .` yeter. Şirket ağında `pip` engelleniyorsa kullanıcıdan bilgi işlemden
   `pyproject.toml` içindeki paketleri istemesini iste.
4. **Ortamı doğrula** (testler pencere açmasın diye `QT_QPA_PLATFORM=offscreen`):
   - PowerShell: `$env:QT_QPA_PLATFORM = "offscreen"; .venv\Scripts\python -m pytest -q`
   - bash: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python -m pytest -q`

   Tam set ~2,5 dakika sürer. Sonu `N passed` olmalı. `failed` varsa çıktıyı kullanıcıya olduğu gibi yapıştırma;
   hangi testin neden düştüğünü özetle. İlk bakılacaklar: eksik paket (`ModuleNotFoundError` → adım 3'ü tekrarla),
   yazı tipi kaynaklı yerleşim testleri (`QT_QPA_FONTDIR=C:\Windows\Fonts` ekle), Python sürümü.
   Hızlı bir ön kontrol: `.venv\Scripts\python -m pytest -q tests/test_msbt.py`.
5. **Uygulamayı aç:** `NX Ceviri Studyosu.bat` dosyasına çift tıklamak (ilk kurulumu kendi yapar) ya da
   `.venv\Scripts\python -m nxceviri`. Pencere açılıyorsa kurulum tamamdır.
6. **Anahtarlar (kullanıcının işi):** Uygulama anahtar vermez, aramaz, indirmez. Kullanıcı `prod.keys` dosyasını
   kendi konsolundan (Lockpick_RCM ile) çıkarmış olmalı ve **Dosya → Anahtarlar → prod.keys Seç…** ile kendisi
   göstermeli. Ajan bu dosyayı açıp okumaz, içeriğini göstermez, kopyalamaz; yalnızca yolu bilir. Anahtarı olmayan
   kullanıcıya nereden bulacağını söyleme; "kendi konsolunuzdan çıkarmanız gerekir" de.
7. **Araçların çalıştığını gör:** `.venv\Scripts\python -m nxceviri.arac --help` komut listesini göstermeli
   (`teshis`, `ara`, `dogrula`, `eklenti-olustur`, `eklentiler`).

## Karar noktaları
- Python 3.12–3.14 arası hangisi: kurulu olan; birden çoksa 3.13.
- Kullanıcı yalnızca çevirmek istiyorsa (oyundan metin çıkarmayacaksa) `[dev]` ve anahtar gerekmez; projeyi
  (`.nxproj`) açıp çevirir. Anahtar ve oyun dosyaları yalnızca metin çıkarmak ve mod üretmek için gerekir.
- Makine çevirisi istiyorsa Ollama kurulumu için `docs/translation.md`.

## Bitti ölçütü
Testler `passed` ile bitti (sayıyı yaz), uygulama penceresi açıldı, `prod.keys` seçildi ve uygulama anahtarı geçerli
buldu (Oyunu Ekle sayfasındaki anahtar kartı, yalnızca geçerli anahtar yokken görünür; kayboldu).

## Kullanıcıya rapor
Kısa Türkçe: hangi Python sürümüyle kuruldu, kaç test geçti, uygulama açılıyor mu, anahtarı kendisinin göstermesi
gerektiği ve sıradaki adım ("hangi oyunu çevirmek istiyorsunuz?" → `yeni-oyun.md`). Çalıştırmadığın bir adımı
"yapıldı" diye yazma.
