# Kurulum (başka bir Windows bilgisayarda)

Bu paket, çeviri yapmak (Ollama / DeepL / elle) ve proje dosyalarını düzenlemek için yeterlidir.
**Oyun dosyaları ve `prod.keys` pakette yoktur**; yalnızca oyundan metin çıkarmak ve mod üretmek için gerekir,
çeviri için gerekmez (metinler `.nxproj` proje dosyasının içindedir).

## 0. En kolayı: taşınabilir paket (Python gerekmez)
GitHub'daki **Releases** sayfasında her sürümün altında `NXTR-<sürüm>-windows.zip` bulunur. İndirip bir
klasöre açın ve `NXTR\NXTR.exe` dosyasına çift tıklayın; kurulum, Python veya internet gerekmez.
Yeni sürüm çıkınca yeni zip'i indirip eski klasörün yerine açmanız yeterlidir: projeleriniz (`.nxproj`) ve
ayarlarınız ayrı yerde durur, etkilenmez. Bu sürümde **Yardım → Güncellemeleri Denetle…** sürümler
sayfasını tarayıcıda açar; GitHub erişim anahtarı kayıtlıysa açılışta “Yeni sürüm: … — İndir” düğmesi çıkar.

Aşağıdaki adımlar paketi değil, kaynak kodunu (Python ile) çalıştırmak içindir.

## 1. Python
Python **3.13** (veya 3.12 / 3.14) kurulu olmalıdır: https://www.python.org → "Add python.exe to PATH" işaretli olsun.

## 2. Başlatma
`NX Ceviri Studyosu.bat` dosyasına çift tıklayın. İlk çalıştırmada sanal ortamı kurar (birkaç dakika, internet gerekir);
sonraki açılışlarda doğrudan uygulamayı açar. Şirket ağında `pip` engelleniyorsa bilgi işlem birimine
`PySide6-Essentials, cryptography, zstandard, UnityPy, httpx, keyring, fonttools, lz4, Pillow` (hepsi `pyproject.toml` içinde) paketlerinin
kurulmasını söyleyin.

## 3. Projeyi açma
Uygulamada **Dosya → Proje Aç…** ile `projeler\Devil May Cry.nxproj` veya `projeler\Mina the Hollower.nxproj` dosyasını seçin.
"3. Çevir" ekranında satırları görürsünüz. Oyun dosyaları bu bilgisayarda olmadığı için "Metinleri Tara" ve "Dışa Aktar"
adımları çalışmaz; çevirilen projeyi geri getirip kendi bilgisayarınızda dışa aktarırsınız.

## 4. Ollama ile çeviri
1. Ollama çalışıyor olmalı (varsayılan adres `http://localhost:11434`).
2. "3. Çevir" ekranında **Otomatik Çeviri** (`Ctrl+T`) → sağlayıcı **Ollama** → modeli listeden seçin (ör. `gemma4:26b`).
3. Önce 15–20 satır seçip (sağ tık → **Seçili satırları çevir**) deneyin; sonuçta şunlara bakın:
   `⟦n⟧` işaretleri aynı mı, satır sonları korunmuş mu, satırlar çok uzamış mı.
4. Beğenirseniz tümünü çevirin. Çeviriler "Makine" durumuyla yazılır; onayladığınız satırlara dokunulmaz.

Devil May Cry'da satır sonları ve satır uzunluğu önemlidir (metin kutusu dardır): her satır en çok ~34 karakter,
`⟦n⟧` işaretleri aynen. Bağlam notu ve terminoloji projede hazırdır (Otomatik Çeviri penceresinden görebilir/değiştirebilirsiniz).

## 5. Güncelleme
**Yardım → Güncellemeleri Denetle…** GitHub'da yayımlanan en yeni sürümü (Releases) gösterir; **Güncelle ve Yeniden Başlat** (veya **İndir ve Yeniden
Başlat**) ile kurulur, uygulama kendiliğinden yeniden açılır. Projeleriniz ve ayarlarınız değişmez.
- Uygulama klasörü bir git deposuysa (git kurulu) güncelleme git ile, Windows'ta kayıtlı GitHub oturumunuzla yapılır.
- Değilse depo özel olduğu için bir kez **salt okunur GitHub erişim anahtarı** girmeniz gerekir; pencere adımları
  gösterir (GitHub'da Anahtar Oluştur → yalnızca bu depo → Contents: Read-only).
Açılışta yeni sürüm varsa sağ alttaki durum çubuğunda “Yeni sürüm: … — Güncelle” düğmesi çıkar.

## 6. Kaydedilmemiş proje ve kurtarma
Yeni bir projeyi henüz kaydetmediyseniz program her dakika (değişiklik olduysa) bir kurtarma kopyası
tutar (`%LOCALAPPDATA%\NXCeviri\kurtarma`). Elektrik kesilir veya program çökerse bir sonraki açılışta
“Kaydedilmemiş proje bulundu” sorusu gelir; **Kurtar** deyip ardından **Kaydet** ile proje dosyasına
kaydedin. Kaydedilmiş projeler zaten her değişiklikte diske yazılır. **Dosya → Son Projeler** son açılan
projeleri listeler.

## 7. Sonucu geri getirme
Projeyi kaydedin (Ctrl+S) ve `.nxproj` dosyasını kendi bilgisayarınızdaki `projeler\` klasörüne kopyalayın.
