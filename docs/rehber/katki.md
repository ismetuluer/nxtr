# Katkı — eklenti ve yamayı paylaşmak, depoya katkı vermek

## Ne zaman okunur
Kullanıcı bir oyunu çözdü (eklenti, font yaması, grafik) ve bunu paylaşmak, başkasına vermek ya da projeye
katmak istiyor; ya da bir hatayı düzeltip katkı vermek istiyor. Hiçbir şey paylaşılmak zorunda değildir: **paylaşmak
istemeyen eklentisini kendinde tutar**, yalnızca ürettiği yamayı (mod klasörü) paylaşır.

Proje lisansı MIT'tir (herkes dilediği gibi kullanabilir); paketlenen parçaların kendi lisansları yanlarındadır (Lucide
simgeleri ISC, hunspell-tr süzgeci MPL-2.0, OFL yazı tipleri, yardımcı ikililer). Depo henüz herkese açık olmayabilir; açık
değilse "çekme isteği" adımları kullanıcının depoya erişimi olduğunda geçerlidir.

## Önce yasal denetim (her paylaşımdan önce)
Paylaşılan hiçbir şey şunları içermez:
- `prod.keys`, `title.keys` ya da herhangi bir anahtar değeri.
- Oyun dosyaları (NSP/NSZ/XCI/NCA/RomFS çıkarımı), oyundan alınmış resimler, ses, uzun metin alıntıları. `docs/formats/`
  notlarında yapıyı anlatan kısa örnek yeterlidir; oyunun metnini sayfalarca kopyalama.
- Oyunun tam çevrilmiş metin tabloları (`.nxproj`, çeviri JSON/XLSX'i) telifli metin içerebilir; paylaşmadan önce
  kullanıcıyla konuş. Mod klasörü (yalnızca değişen dosyalar) paylaşılabilir, tam oyun kopyası paylaşılamaz.
- Kişisel yollar (`C:\Users\<ad>\…`), kullanıcı adı, e-posta, gizli bilgi, `teshis-raporu.md` içindeki oyun metni örnekleri.

Kontrol: `git status` ve `git diff` çıktısına bak; `.gitignore` anahtar ve oyun uzantılarını zaten dışlar, ama sen yine
de gözle doğrula. Şüpheli dosya varsa kullanıcıya sor.

## Üç paylaşım yolu

### 1. Kendinde tut
Eklenti klasörü `%LOCALAPPDATA%\NXCeviri\eklentiler\<ad>\` (ya da `eklentiler/<ad>/`) içinde kalır; hiçbir şey yapma. Kaynak
koddan çalıştırıyorsan depo içi `eklentiler/*` zaten git'e girmez (`eklentiler/README.md` hariç).

### 2. Klasörü sıkıştırıp ver
1. `eklentiler/<ad>/` (ya da `%LOCALAPPDATA%` altındaki) klasörünü zip'le: içinde `eklenti.toml`, `plugin.py`,
   `tests/`, `NOT.md`.
2. Kullanıcı kendi uygulamasında **Yardım → Eklentiler → Eklenti Ekle…** ile zip'i ya da klasörü seçer.
3. Zip'i alacak kişiye uyar: eklenti kod çalıştırır, korumalı alan yoktur; güvendiğin kişiden al, `plugin.py`'yi oku.
4. Zip'te anahtar ve oyun verisi olmadığını doğrula.

### 3. Depoya çekme isteği (pull request)
1. Çalışma dalı aç (`git switch -c eklenti/<ad>`); ana dala doğrudan yazma.
2. Eklenti klasörünü yerinde bırak ya da (yerleşik olması istenen eklenti için) bakımcıyla konuşup
   `nxceviri/core/formats/<ad>/` altına taşı:
   - `registry.py` içindeki `BUILTIN_PLUGINS` listesine ekle;
   - `core/formats/detection.py` içindeki `FileKind`, `KIND_LABELS` ve `detect` kuralını, gerekirse `scanner.py`
     motor kurallarını genişlet;
   - testleri `tests/test_<ad>.py` olarak taşı; üreticileri `tests/` içinde elle üretilmiş örneklere dayandır.
3. Belgeleri güncelle:
   - `docs/formats/<ad>.md` (yapı, kaynaklar, tuzaklar, cihazda denendi mi) ve `docs/formats/README.md` tablosuna satır;
   - `docs/uyumluluk.md`'ye oyun satırı (oyun, motor/biçim, metin/font/grafik durumu, çözen kişi, sürüm);
   - `eklentiler/<ad>/NOT.md`'deki bilgiyi biçim notuna aktar.
4. Kalite kapısı (hepsi çıktısıyla gösterilir):
   ```
   python -m pytest -q
   python -m ruff check nxceviri tests
   python -m ruff format --check nxceviri tests
   python -m mypy
   ```
   Arayüz testleri için `QT_QPA_PLATFORM=offscreen` (Windows'ta ayrıca `QT_QPA_FONTDIR=C:\Windows\Fonts`).
5. Kuralları `AGENTS.md` ile uyumlu tut: TDD, round-trip testi, teknik borç bırakma (kalan iş `TECH_DEBT.md`'ye
   gerekçesiyle), Türkçe yorum ve arayüz metni, yeni bağımlılık yok (gerekirse `ARCHITECTURE.md`'ye "neden").
6. Çekme isteği açıklaması: ne eklendi, hangi oyun/TitleID/sürüm, `dogrula` çıktısı özeti, cihazda denendi mi,
   bilinen sınırlar. Oyun metni yapıştırma.

`CHANGELOG.md`, sürüm numarası ve `ARCHITECTURE.md` kararları bakımcıya aittir; kendin artırmaya çalışma
(bakımcı yanıtında istemedikçe).

## Hata ve oyun desteği isteği
Konu açarken (ya da kullanıcıya açtırırken) şunları ver: oyun adı, TitleID ve sürüm, motor tahmini ve tanınan dosya
sayıları (`teshis-raporu.md`'nin özeti, oyun metni örnekleri **olmadan**), yapılan adımlar, hata mesajı. Oyun dosyası
gönderme ve isteme.

## Bitti ölçütü
Yasal denetim yapıldı (anahtar, oyun verisi, kişisel yol yok); seçilen yola göre zip hazır ya da dal/çekme isteği
hazır; testler ve `ruff`/`mypy` temiz çıktısı gösterildi; belgeler (biçim notu, uyumluluk satırı) güncellendi.

## Kullanıcıya rapor
Hangi yolu seçtiğin, ne paylaşıma hazır (dosya yolu ya da dal), neyin paylaşılmadığı ve nedeni (anahtar, oyun verisi),
sıradaki adım (kullanıcının çekme isteğini göndermesi ya da zip'i iletmesi). Push ve çekme isteği gönderme kullanıcı
onayı ister.
