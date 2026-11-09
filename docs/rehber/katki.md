# Katkı — eklenti ve yamayı paylaşmak, depoya katkı vermek

## Ne zaman okunur
Kullanıcı bir oyunu çözdü (eklenti, font yaması, grafik) ve bunu paylaşmak, başkasına vermek ya da projeye
katmak istiyor; ya da bir hatayı düzeltip katkı vermek istiyor. Hiçbir şey paylaşılmak zorunda değildir: **paylaşmak
istemeyen eklentisini kendinde tutar**, yalnızca ürettiği yamayı (mod klasörü) paylaşır.

Proje lisansı MIT'tir (herkes dilediği gibi kullanabilir); paketlenen parçaların kendi lisansları yanlarındadır (Lucide
simgeleri ISC, hunspell-tr süzgeci MPL-2.0, OFL yazı tipleri, yardımcı ikililer). Depo herkese açıktır:
https://github.com/ismetuluer/nxtr. Yazma izni olmayan herkes **fork** (kendi kopyası) üzerinden çekme isteği gönderir.

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
2. Kullanıcı kendi uygulamasında **Araçlar → Eklentiler → Eklenti Ekle…** ile zip'i ya da klasörü seçer.
3. Zip'i alacak kişiye uyar: eklenti kod çalıştırır, korumalı alan yoktur; güvendiğin kişiden al, `plugin.py`'yi oku.
4. Zip'te anahtar ve oyun verisi olmadığını doğrula.

### 3. Depoya çekme isteği (pull request)
0. **Fork ve kopya** (bir kez): GitHub'da depoyu fork'la, kendi kopyanı klonla ve asıl depoyu `upstream` olarak ekle:
   ```
   git clone https://github.com/<kullanıcı>/nxtr.git
   cd nxtr
   git remote add upstream https://github.com/ismetuluer/nxtr.git
   ```
   Kurulum için `baslarken.md`. Yazma iznin varsa fork gerekmez; doğrudan klonla.
1. Güncel ana daldan çalışma dalı aç; ana dala doğrudan yazma:
   ```
   git fetch upstream
   git switch -c eklenti/<ad> upstream/master
   ```
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
6. Gerçek oyunda sına (oyun dosyaları yalnızca kullanıcının bilgisayarında kalır):
   ```
   python -m nxceviri.arac dogrula <eklenti-adı> <oyun.nsp> [güncelleme.nsp]
   ```
   Her dosyada değişikliksiz geri yazımın bayt bayt aynı çıktığını ve işaret metninin yerine oturduğunu gösterir.
7. Gönder ve çekme isteği aç (kullanıcı onayıyla):
   ```
   git push -u origin eklenti/<ad>
   gh pr create --repo ismetuluer/nxtr --base master
   ```
   `gh` yoksa GitHub'ın push sonrası verdiği bağlantıdan açılır. Açıklamada: ne eklendi, hangi oyun/TitleID/sürüm,
   `dogrula` çıktısı özeti, cihazda denendi mi, bilinen sınırlar. Oyun metni yapıştırma.
8. İstek beklerken ana dal ilerlediyse: `git fetch upstream`, `git rebase upstream/master`, testleri yeniden çalıştır,
   `git push --force-with-lease`. Çakışmayı çözerken başkasının kodunu silme; emin değilsen sor.

`CHANGELOG.md`, sürüm numarası ve `ARCHITECTURE.md` kararları bakımcıya aittir; kendin artırmaya çalışma
(bakımcı yanıtında istemedikçe).

## Birden çok yerel kopya ve farklı ajanlar

Aynı anda birden çok iş (iki oyun, ya da bir oyunda eklenti ve başka yerde hata düzeltmesi) yürütülebilir. Kural: **her
iş kendi klasöründe ve kendi dalında**; iki ajan (ya da ajan ve insan) asla aynı klasörde aynı anda dosya yazmaz.

### Senaryo 1: Bir kişi, iki oyun
Ana kopyadan ikinci bir çalışma klasörü aç (aynı depo, ayrı dal; diskte az yer tutar):
```
git worktree add ../nxtr-oyunB -b eklenti/oyunB upstream/master
```
Her klasörün kendi sanal ortamı olsun (o klasörde `py -3.13 -m venv .venv` ve `pip install -e ".[dev]"`): düzenlenebilir
kurulum klasöre bağlıdır; paylaşılırsa bir klasörün kodu ötekinde çalışır. İş bitince `git worktree remove ../nxtr-oyunB`.

### Senaryo 2: Farklı ajanlar (ör. Claude Code ve Codex)
- Her ajan ayrı klasörde (yukarıdaki gibi `git worktree` ya da ayrı klon) ve ayrı dalda başlar; ikisi de önce
  `AGENTS.md`'yi okur. Ajana hangi klasörde ve hangi dalda çalışacağını açıkça söyle.
- Kullanıcı eklenti klasörü (`%LOCALAPPDATA%` altındaki `NXCeviri/eklentiler/`) **bütün kopyalar için ortaktır** ve depo
  içindeki `eklentiler/` klasöründen önceliklidir. İki ajan aynı oyun üzerinde çalışacaksa eklentiyi oraya değil, kendi
  kopyasının `eklentiler/<ad>/` klasörüne koysun.
- Küçük ve sık commit; her commit'ten önce testler. Ajanlar birbirinin dalına yazmaz; birleştirmeyi kullanıcı (ya da
  bakımcı) çekme isteğiyle yapar.
- Ortak dosyalara (`registry.py`, `detection.py`, `docs/uyumluluk.md`) iki dal da satır ekliyorsa çakışma beklenir;
  ikinci istek `rebase` ile birincinin üstüne alınır, iki satır da korunur.

### Senaryo 3: Aynı oyun için iki eklenti
İki kişi (ya da iki ajan) aynı oyuna ayrı eklenti yazdıysa uygulama şöyle davranır:
- **Aynı ad** (`eklenti.toml` içindeki `ad`) ve aynı biçim adı: öncelikli klasördeki (önce kullanıcı klasörü, sonra
  depodaki `eklentiler/`) kullanılır; öteki "gölgelendi" uyarısıyla yüklenmez.
- **Farklı ad, aynı biçim adı** (`PLUGIN.name`): ikincisi yüklenmez; **Araçlar → Eklentiler**'de "biçim adı … ile
  çakışıyor" hatası görünür.
- **Farklı ad, farklı biçim adı, aynı dosyalar:** tarama, dosyayı tanıyan **ilk** eklentiyi kullanır (klasör adına göre
  alfabetik sırayla). Proje dosyası her metin dosyasının biçim adını saklar; o eklenti kaldırılırsa proje o dosyaları
  okuyamaz.

Ne yapmalı: ikisini `dogrula` ile aynı oyunda karşılaştır (hangisi daha çok dosyayı bayt bayt geri yazıyor, kontrol
kodlarını doğru ayırıyor), iyi olanı tut, ötekinin artısını ona taşı. Depoya yalnızca biri girer; çekme isteğinde öteki
eklentinin yazarını belirt. Kullanıcı projesini hangi eklentiyle taradıysa o eklentiyle devam etmelidir.

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
