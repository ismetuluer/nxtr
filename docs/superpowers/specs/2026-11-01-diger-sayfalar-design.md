# Arayüz yenileme — Alt proje 3: Diğer sayfalar

Tarih: 2026-11-01 · Durum: onay bekliyor · Üst belge: `2026-10-31-arayuz-yenileme-design.md` (§2, alt proje 3)

## 1. Amaç ve kararlar

Oyunu Ekle, Metinleri Tara, Kontrol Et ve Dışa Aktar sayfaları, çeviri sayfasıyla aynı dile getirilir. Ürün sahibinin
kararları (2026-11-01):

- **Ana eylem üst araç çubuğunda.** Her sayfada başlığın sağında tek sıra eylem durur: ana eylem vurgulu (primary),
  yardımcı eylemler sade ve simgeli. Kartlar yalnızca içerik taşır.
- **Uzun metin yerine kısa durum, ayrıntısı tıklayınca.** Sayfadaki uzun uyarı şeritleri ve açıklamalar başlıkta
  kısa bir **durum çipine** dönüşür ("2 uyarı"); ayrıntı çipe tıklayınca küçük bir açılır pencerede görünür.
  Boş durumlar kısa ve eylem odaklıdır.

Kapsam dışı: çeviri sayfası, kenar çubuğu, durum çubuğu, iletişim kutuları, yeni özellik. Hiçbir iş mantığı değişmez;
yalnızca yerleşim ve metin.

## 2. Ortak parçalar (`nxceviri/gui/widgets.py`)

### 2.1 `PageHeader(QWidget)`

`PageHeader(title: str, icon: str)` — solda simge + başlık (`pageTitle`), ortada esnek boşluk ve durum çipleri,
sağda eylemler.

- `add_action(widget: QWidget) -> None`: sağa (soldan sağa) bir düğme ya da seçim kutusu ekler. Ana eylem en sağa
  eklenir; sayfalar kendi düğmelerini `button(...)` ile kurmaya devam eder.
- `chip: StatusChip`: tek bir durum çipi (bkz. 2.2); varsayılan gizli.
- `title_row` başka yerlerde (çeviri sayfası, iletişim kutuları) kullanılmaya devam eder; dört sayfa `PageHeader`'a geçer.

### 2.2 `StatusChip(QToolButton)` ve ayrıntı penceresi

- `show_status(state: str, text: str, details: list[str])`: `state` ∈ `info|success|warning|danger`; `text` kısa
  (en çok ~30 karakter, ör. "2 uyarı", "Anahtar seçilmedi"). `details` boşsa çip tıklanamaz.
  `state == ""` ya da `text == ""` çipi gizler.
- Tıklanınca `QFrame` tabanlı açılır pencere (`Qt.Popup`) çipin altında açılır: her ayrıntı ayrı satır, kelime kaydırmalı,
  en fazla 420 px genişlik; Esc ya da dışarı tıklama kapatır. Metin seçilebilir (kopyalanabilir).
- Renkler mevcut `Badge` durum renklerinden gelir (açık/koyu tema). Simge: `circle-alert` (danger),
  `triangle-alert` (warning), `check-circle` (success), yoksa simgesiz.
- Ayrıntı listesi aynı zamanda çipin ipucudur (üzerine gelince de okunur).

## 3. Sayfalar

Nesne adları (`next_button`, `export_button`, `check_button`, `import_button` vb.) **aynen kalır**; yalnızca
yerleri değişir. `main_window.py` bağlantıları değişmez, banner'lara yazan yerler çipe yazar.

### 3.1 Oyunu Ekle (`add_game_page.py`)

- Başlık eylemi: `next_button` ("Metinleri Tara →", primary). Alt satır (`status` + düğme) kalkar.
- `set_can_continue(ok, reason)`: `ok` değilse `reason` düğmenin ipucu ve çip (`info`) olur; `ok` ise çip gizlenir.
  `set_busy(busy, text)`: `text` çipte `info` olarak görünür.
- Anahtar kartı: başlık "Anahtarlar"; `prod.keys` ve `title.keys` aynı yapıda iki satır (yol + düğme). Uzun
  açıklamalar (`KEYS_HELP`, `TITLE_KEYS_HELP`) ipucunda kalır.
- Bırakma alanı metni: hazırken "NSP / NSZ dosyalarını bırakın", kilitliyken "Önce anahtar dosyası seçin".
- `keys_banner` ve `files_banner` kalır (giriş hatası anında yerinde görülmeli), ama metinleri tek cümleye iner.

### 3.2 Metinleri Tara (`scan_page.py`)

- Boş/başlamadı: başlık eylemi "Taramayı Başlat" (primary); ortada yalnızca simge + "Henüz tarama yapılmadı" +
  tek satır. İkinci (orta) düğme kalkar.
- Hata: başlık eylemi "Tekrar Dene" (primary); "Oyunu Ekle adımına dön" yardımcı eylem olur.
- Sonuç: başlık eylemleri soldan sağa: "Yeniden Tara" (yardımcı), "Kaynak dil" seçimi (yalnızca birden çok dil
  varken), `import_button` "Çeviri Tablosuna Aktar →" (primary). Özet kartının başlık sağı boşalır.
- `support` ve `warnings` banner'ları çipe dönüşür: tek çip, en ağır durum rengi, metin "N uyarı"/"Desteklenmiyor";
  satırları ayrıntıda.
- Tarama sürerken eylemler pasif.

### 3.3 Kontrol Et (`qa_page.py`)

- Başlıkta sayfa eylemi yok; sekmeler kalır.
- Her sekmenin üstünde, kart dışında, sekmenin eylem satırı (araç çubuğu): solda kısa durum metni, sağda eylemler.
  - Satır denetimi: Programla Düzelt, Otomatik Düzelt…, **Denetle** (primary). "Satır denetimi" kart başlığı kalkar.
  - Sığdırma: "Etkin" anahtarı ve "Orijinalden öğren". Kart başlığı kalkar.
  - Font ve harfler: **Fontları Tara** (primary). Kart başlığı kalkar.
- Sekme içindeki "Çift tıklayın veya Enter'a basın…" gibi açıklamalar tablonun ipucuna taşınır.
- `fix_banner` (düzeltme sonucu) yerinde kalır; tek cümle.

### 3.4 Dışa Aktar (`export_page.py`)

- Başlık eylemi: `export_button` "Modu Oluştur" (primary). Başlıktaki uzun açıklama ipucuna iner.
- `version_banner` → başlık çipi: `danger`/`warning`, metin "N sorun"/"N uyarı", cümleler ayrıntıda.
- Özet kartı tek satır sayılara iner: "21 yazılacak · 0 hatalı · 10 çevrilmemiş · Harf dönüştürme: yok".
- `result` banner'ı ve "Mod Klasörünü Aç" kalır (işlem sonucu yerinde görülmeli).
- Çalışırken (`show_running`) başlık eylemi pasif.

## 4. Kenar durumları

- Pencere en küçükken (mevcut asgari boyut) başlık eylemleri sığmazsa düğme metinleri kısalmaz, başlık metni
  kısaltılır (`…`); düğmeler her zaman görünür kalır.
- Çip ayrıntısı çok uzunsa açılır pencere kaydırılabilir (en fazla 320 px yükseklik).
- Klavye: başlık eylemleri sekme sırasında başlıktan hemen sonra gelir; çip Enter/Boşluk ile açılır.
- Koyu tema ve yüksek DPI: renkler tema belirteçlerinden; simgeler mevcut `bind_icon` ile.

## 5. Test planı

- `PageHeader`: eylem sırası, ana eylemin en sağda olması, uzun başlıkta düğmelerin görünür kalması.
- `StatusChip`: durumlar, gizlenme, ayrıntı yokken tıklanamaması, açılır pencerenin ayrıntıyı göstermesi ve Esc ile kapanması.
- Her sayfa: ana eylemin `PageHeader` içinde olması; mevcut etkin/pasif kurallarının korunması (`set_can_continue`,
  `set_summary(can_export=…)`, tarama durumları); banner yerine çipe yazılan uyarıların ayrıntıda görünmesi.
- Mevcut GUI testlerinin tamamı (nesne adları korunduğu için değişmeden geçmeli; geçmeyen testler yalnızca yerleşim
  varsayımı içeriyorsa güncellenir).
- Ekran görüntüleri: açık/koyu, 1180×780 ve en küçük pencere, dört sayfa.

## 6. Dosyalar

- `nxceviri/gui/widgets.py`: `PageHeader`, `StatusChip`.
- `nxceviri/gui/theme.py`: çip ve eylem satırı biçemleri.
- `nxceviri/gui/add_game_page.py`, `scan_page.py`, `qa_page.py`, `export_page.py`: yerleşim ve metinler.
- `nxceviri/gui/main_window.py`: `version_banner` ve tarama uyarılarının çipe yazılması.
- Testler: `tests/test_page_header.py` (yeni) ve mevcut sayfa testleri.
- Sürüm 0.37.0, CHANGELOG (0.36.0'ın üstüne), ARCHITECTURE §4.24.
