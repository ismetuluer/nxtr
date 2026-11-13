# AGENTS.md — NXTR

Bu dosya, bu depoda çalışan her yapay zekâ ajanının (Claude Code, Codex, Gemini CLI, Cursor…) ilk okuduğu dosyadır.
Baştan sona oku; sonra aşağıdaki yönlendirme tablosundan işine uyan rehberi aç.

**NXTR** (eski adı NX Çeviri Stüdyosu; Python paketi `nxceviri`), kullanıcının kendi sahip olduğu Nintendo Switch
oyunlarındaki (NSP / NSZ) metinleri ayıklayan, Türkçeye çeviren ve oyuna geri yüklenebilir bir **LayeredFS mod
klasörü** üreten, tek pencereli bir Windows masaüstü uygulamasıdır. Kullanıcı başka program çalıştırmaz: oyunu seçer,
metinleri görür, çevirir, kontrol eder, mod klasörünü dışa aktarır. Ana akış: **1. Oyunu Ekle → 2. Metinleri Tara →
3. Çevir → 4. Kontrol Et → 5. Dışa Aktar.**

## 1. Pazarlık konusu olmayan kurallar

Kullanıcı istese bile bu kuralları çiğneme; nedenini söyle, yasal yolu göster.

- **Şifreleme anahtarı:** Uygulama ve ajan hiçbir anahtarı içermez, indirmez, aramaz, önermez. Kullanıcı `prod.keys`
  (gerekirse `title.keys`) dosyasını kendi konsolundan çıkarır ve uygulamada kendisi gösterir (Dosya → Anahtarlar).
  Anahtar dosyasının içeriği asla loglanmaz, hata raporuna yazılmaz, proje dosyasına kopyalanmaz, sohbette
  gösterilmez, depoya girmez (yalnızca dosya yolu saklanır).
- **Oyun dosyası:** İndirilmez, paylaşılmaz, dağıtılmaz, depoya konmaz (NSP/NSZ/XCI/NCA, çıkarılmış RomFS, oyundan
  alınmış uzun metin ve resimler dahil). Ajan oyun dosyası aramaz; kullanıcının verdiği yolu kullanır.
- **Orijinal dosyalara dokunulmaz:** Kullanıcının oyun dosyaları yalnızca okunur; hiçbir zaman değiştirilmez.
- **Çıktı yalnızca mod klasörüdür:** Değişen dosyalardan oluşur. Tam oyun yeniden paketlenmez, dağıtılabilir oyun
  kopyası üretilmez.
- **Testler:** Yalnızca elle üretilmiş küçük örnekler kullanılır (`tests/nxbuild.py`, `tests/unitybuild.py` gibi
  üreticiler); gerçek oyun dosyası ya da oyundan kopyalanmış veri teste konmaz.
- **Raporlar yerelde kalır:** Teşhis raporu, `ara`/`dogrula` çıktıları oyun metni örnekleri içerebilir; kullanıcıya
  "paylaşmadan önce bakın" de. Oyun metnini izinsiz herkese açık yere (konu, çekme isteği) yapıştırma.
- **Dürüst rapor:** Çalıştırıp çıktısını görmediğin şeye "test edildi" deme. Cihazda/emülatörde denenmeyen işi öyle
  raporla ("cihazda denenmedi").

## 2. Görev yönlendirmesi

Kullanıcı ne istiyorsa ilgili rehberi baştan sona oku, adımlarını izle. Skill adları `.claude/skills/` ve
`.agents/skills/` altındadır (aynı içerik); skill yoksa rehberi doğrudan oku.

| Kullanıcı istiyor | Rehber | Skill |
|---|---|---|
| Bu bilgisayara kur / projeyi ilk kez çalıştır | `docs/rehber/baslarken.md` | (yok; rehberi oku) |
| Yeni bir oyunun metinlerine erişmek, çeviri tablosuna aktarmak | `docs/rehber/yeni-oyun.md` | `nxtr-yeni-oyun` |
| Tanınmayan bir biçim için eklenti yazmak, test etmek | `docs/rehber/eklenti-yazma.md` | `nxtr-yeni-oyun` |
| Oyunda harf kutucuğu / eksik Türkçe karakter (font) | `docs/rehber/font.md` | `nxtr-font` |
| Menü, düğme, başlık resimlerindeki yazıları çevirmek (grafik) | `docs/rehber/grafik.md` | `nxtr-grafik` |
| Yama açılmıyor, taşıyor, İngilizce kalan satır, mod görünmüyor | `docs/rehber/sorun-giderme.md` | `nxtr-sorun-giderme` |
| Eklentiyi / yamayı paylaşmak, depoya katkı vermek | `docs/rehber/katki.md` | `nxtr-katki` |
| Ajana yapıştırılacak hazır talimatlar | `docs/istemler.md` | — |
| Bir biçim daha önce çözülmüş mü? | `docs/formats/README.md` | — |
| Hangi oyun ne durumda? | `docs/uyumluluk.md` | — |

Ortak sıra: önce **teşhis** (`python -m nxceviri.arac teshis …`), sonra rehber. Oyunun motoru ve biçimi tanınıyorsa
yeni kod yazma; uygulamanın kendisini kullandır.

## 3. Çalışma kuralları

### Yığın ve bağımlılıklar
- Python 3.12+ (geliştirmede 3.13 kullanılıyor), arayüz PySide6, proje dosyası `.nxproj` = SQLite, paketleme
  PyInstaller (onedir). Kurulum: `docs/rehber/baslarken.md`.
- Yeni bağımlılık ancak kendi yazacağımız koddan açıkça daha güvenilir ve bakımlıysa eklenir; bakımı bırakılmış ya da
  Python 3.12+ için wheel'i olmayan kütüphane kullanılmaz (gerekirse biçimi kendimiz yazarız). Gerekçesiyle
  `ARCHITECTURE.md`'ye yazılır. GPL lisanslı bağımlılık eklenmez (`oead` bu yüzden kullanılmadı).

### Mimari özet (katmanlar ayrıdır)
`nxceviri/core/` arayüzü bilmez, Qt import etmez; `nxceviri/gui/` iş mantığı içermez. Ayrıntı: `ARCHITECTURE.md` §3.
- `core/keys` anahtar okuma · `core/container` NSZ→NSP→NCA→RomFS, base+update birleştirme · `core/archives` SARC, Yaz0,
  ZSTD, pak, PSB, NNI, CPK… · `core/formats` metin biçimi eklentileri · `core/translate` sağlayıcılar, yer tutucular,
  bellek, sözlük · `core/qa` denetimler · `core/fontpatch` font/grafik yamaları · `core/export` LayeredFS çıktısı ·
  `core/project` `.nxproj`.
- Metinler çoğu zaman güncelleme (update) paketinde değişir; güncellemedeki dosya base'dekini geçersiz kılar. Proje
  TitleID + sürümü kaydeder, yanlış sürüme mod üretilirse uyarır. Anahtar/sürüm sorunlarında `core/container` notlarına
  (`docs/formats/nca.md`, `bktr.md`) bak.

### Format eklentisi sözleşmesi (`nxceviri/core/formats/base.py`)
Her metin formatı aynı arayüzü uygular:
- `detect(path, head) -> bool`
- `extract(data, context) -> list[TextEntry]`: her girdide benzersiz ve kalıcı `key`, `index`, `source` (kontrol
  kodları `⟦1⟧`, `⟦2⟧`… olarak), `codes`, varsa `max_length`, okunur `context`.
- `inject(data, translations) -> bytes`: orijinal yapıyı **bayt düzeyinde korur**, yalnızca metni değiştirir; çeviri
  verilmeyen girdiler olduğu gibi kalır.
- İsteğe bağlı: `collect_context`, `language`, `normalize_text`, `unsupported_letters`, `support_files`,
  `game_file_patches`, `exefs_patches`, `derived_files` (ayrıntı `docs/rehber/eklenti-yazma.md`).
- **Zorunlu test:** değişiklik yapmadan `extract` → `inject` sonucu orijinalle **bayt bayt aynı** olmalı (round-trip).
  Bu test geçmeyen eklenti tamamlanmış sayılmaz. Gerçek dosyada denemek için `python -m nxceviri.arac dogrula`.

### Kontrol kodları (en kritik risk)
Renk, satır sonu, değişken (oyuncu adı, sayı), duraklama gibi kodlar bozulursa oyun çöker.
- Çeviriden önce her kod `⟦1⟧`, `⟦2⟧` gibi yer tutucuya dönüşür (`core/translate/placeholders.py`); çeviriden sonra
  yer tutucuların **sayısı, türü ve sırası** doğrulanır. Uymayan satır "hatalı" işaretlenir ve dışa aktarılmaz;
  sessizce düzeltilmez.
- Tek bilinçli istisna: ürün sahibinin isteğe bağlı "Hatalı satırları da aktar" seçeneği (varsayılan kapalı;
  `ARCHITECTURE.md` karar 127). Kapalıyken davranış yukarıdaki gibidir; bu seçeneği kendiliğinden açma.

### Türkçe karakter ve font
Dışa aktarmadan önce oyunun fontunda `ç ğ ı İ ö ş ü Ç Ğ Ö Ş Ü` gliflerinin varlığı denetlenir. Glif yoksa kullanıcıya
açık uyarı ve seçenekler sunulur: harf dönüştürme (ğ→g, ş→s, ı→i…) ya da font yaması. Henüz yapılmamış özellik
arayüzde "yakında" düğmesi olarak gösterilmez. Ayrıntı: `docs/rehber/font.md`.

### Dışa aktarma
Atmosphère: `atmosphere/contents/<TitleID>/romfs/...`; emülatör: `<TitleID>/<Mod Adı>/romfs/...`. Yalnızca değişen
dosyalar yazılır; yazım atomiktir (geçici klasör → doğrulama → taşıma). Ayrıntı: `docs/export.md`.

### Veri güvenliği
Proje veritabanına yazımlar işlem içinde yapılır (çökmeden sonra proje açılabilir olmalı). Çıkarılan büyük dosyalar
proje önbelleğinde tutulur (kullanıcı arayüzden temizler). Uzun işler arka plan iş parçacığında, ilerleme ve iptal
destekli çalışır; arayüz donmaz. API anahtarları Windows Kimlik Bilgisi Yöneticisi'nde (keyring) durur, proje
dosyasında değil. Sağlayıcı ayrıntıları (Ollama, DeepL): `docs/yol-haritasi.md` ve `docs/translation.md`.

### Arayüz ilkeleri
- Tüm arayüz Türkçedir. Hata mesajı ne olduğunu ve kullanıcının ne yapması gerektiğini söyler.
- Sık yol önde, gelişmiş seçenekler bir seviye altta (menüde); yeni kalıcı düğme eklemeden önce mevcut menülere
  bak (menü çubuğu ve tablonun sağ tık menüsü; Kontrol Et'te "Düzelt" menüsü). Kısayol eklemek için
  `nxceviri/gui/shortcuts.py` kataloğuna komut ekleyip eylemi `ShortcutRegistry.bind` ile bağla; tuşu koda yazma.
  İpucu en çok 1-2 kısa cümle.
- Çeviri tablosu: orijinal / çeviri / durum (çevrilmedi, makine, redakte, onaylandı, hatalı) / dosya; arama, filtre,
  toplu seçim, satır içi düzenleme; binlerce satırda akıcı (sanal model).
- Açık/koyu tema, yüksek DPI, küçük pencere, boş / yükleniyor / hata durumları tasarlanır. Hiçbir düğme işlevsiz
  bırakılmaz; yapılmamış özellik arayüzde görünmez.
- Bir özellik ancak şu zincirin tamamı çalışınca bitmiştir: arayüz → etkileşim → iş mantığı → veri → hata yönetimi →
  kullanıcı geri bildirimi → test.

### Kalite
- **TDD:** önce başarısız testi yaz ve başarısız olduğunu gör, sonra kodu yaz. pytest ile birim ve entegrasyon testi;
  round-trip, yer tutucu, Türkçe karakter, bozuk/eksik dosya, yanlış anahtar, boş proje, çok büyük tablo, yarıda
  kesilen işlem test edilir. Mevcut testi yalnızca davranış bilerek değiştiyse güncelle.
- **Teknik borç bırakma:** geçici çözüm, sahte veri, ölü kod, kullanılmayan import, açıklamasız TODO/FIXME, sessiz
  `except: pass` yok. Gerçekten bitirilemeyen iş gerekçesiyle `TECH_DEBT.md`'ye yazılır.
- **Test edilmeyen bir şey "test edildi" diye raporlanmaz.**
- `ruff` (lint + format) ve `mypy` (strict) temiz geçer. Yorumlar ve arayüz metinleri Türkçe; çevredeki kodun adlandırma
  ve yorum yoğunluğuna uy.

### Komutlar (depo kökünden)
```
python -m pytest -q                      # tam test seti (~5 dk)
python -m pytest -q tests/test_msbt.py   # tek dosya
python -m ruff check nxceviri tests && python -m ruff format nxceviri tests
python -m mypy                           # strict; pyproject'teki files = nxceviri, tests
```
Windows'ta arayüz testleri için pencere açılmasın diye `QT_QPA_PLATFORM=offscreen` ortam değişkenini ver
(PowerShell: `$env:QT_QPA_PLATFORM = "offscreen"`; bash: `export QT_QPA_PLATFORM=offscreen`). Testlerde
kullanılan yazı tipi için gerekirse `QT_QPA_FONTDIR=C:\Windows\Fonts` ekle. Sanal ortam `.venv` içindedir;
`.venv\Scripts\python.exe` ile çalıştır.
Araçlar: `python -m nxceviri.arac teshis | ara | dogrula | eklenti-olustur | eklentiler` (ayrıntı için `--help`).

### Belgeler
`AGENTS.md` (bu dosya: kurallar) · `docs/rehber/` (nasıl yapılır) · `docs/formats/` (çözülmüş biçim notları, dizin
`docs/formats/README.md`) · `docs/uyumluluk.md` (oyun durumları) · `ARCHITECTURE.md` (mimari, kararlar) ·
`TECH_DEBT.md` (bilinçli bırakılan işler) · `CHANGELOG.md` · `HANDOFF.md` (oturum devri) · `docs/yol-haritasi.md`
(ürün sahibinin planı; başka kullanıcının ajanı bunu uygulamaya kalkmaz).

## 4. Kullanıcı

Kullanıcı programcı olmayabilir ve Türkçe konuşur. Teknik kararları sen verirsin; kararı ve gerekçesini kısa, anlaşılır
Türkçe ile söylersin (jargon gerekirse bir cümleyle açıkla). Seçenek sunacaksan en fazla iki tane ve önerini belirt.
Kullanıcıdan yalnızca senin yapamayacağın şeyleri iste: `prod.keys`'i göstermek, oyun dosyalarının yolu, oyunu
cihazda/emülatörde denemek, kendi resimlerini hazırlamak. Her iş sonunda kısa rapor ver: ne değişti, ne test edildi
(komut çıktısıyla), ne edilmedi, sıradaki adım.
