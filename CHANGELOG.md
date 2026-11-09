# Değişiklik Günlüğü

Biçim [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/), sürümleme [SemVer](https://semver.org/lang/tr/).

## [0.49.0] — 2026-11-09 — Çevir ekranı: küçük ekran, sütunlar, Bul ve Değiştir

### Eklendi
- **Bul ve Değiştir çubuğu** (tablonun üstünde; `Ctrl+F` bul, `Ctrl+H` değiştir, `F3` / `Shift+F3`): eşleşmeler hücrede
  boyanır, sayaç "3 / 41", **Önizle** açıkken değişiklik tabloda görünür ama yazılmaz, Değiştir / Tümünü Değiştir (tek
  adımda geri alınır). Büyük/küçük harf, tam sözcük, düzenli ifade (kilitleyecek desenler engellenir), kapsam ve alan
  seçimi. Kontrol kodunu bozacak değişiklik uygulanmaz. Süzgeç etkinken yalnızca görünen satırlarda arar; süzgeci
  kendiliğinden temizlemez. Tablo arama kutusu `Ctrl+Shift+F`.
- **No sütunu** (aktarım sırası; aramada `#120` o satıra gider) ve **doğal sıralama** (1, 2, 10, 100).
- **Çoklu süzgeç:** Dosya (grup) ve Anahtar başlığındaki huniden aramalı, onay kutulu seçim; proje başına hatırlanır.
  Süzgeç etkinken "Süzgeç etkin · Temizle" çipi görünür.
- Panelde **canlı karakter sınırı**: "En uzun satır 23 / 28"; sınır sığdırma kuralından, biçim sınırından ya da
  orijinalin en uzun satırından gelir; projeye özel **Elle sınır** girilebilir (oyunun gerçek sınırı aşılırsa yine uyarır).
- Tabloda yazım hataları kırmızı dalgalı çizgiyle; Orijinal hücresine çift tıklayınca seçilip kopyalanabilir.

### Değişti
- **Kenar çubuğu daraltılabilir** (`Ctrl+Alt+S`, Görünüm → Kenar Çubuğu); dar pencerede daralmış başlar.
- **Durum çubuğu simgelerle:** anahtar, satır, ilerleme, sorunlar, sağlayıcı, kayıt; ayrıntı ipucunda. Ollama ipucunda
  model, GPU/CPU payı ve bellekte kalma süresi; DeepL ipucunda kalan kota. Tekrarlanan satır sayıları kalktı.
- **Durum sütunu simge:** çevrilmedi, makine, redakte, onaylı; sorunlu satırda sarı/kırmızı üçgen.
- **Sütunlar:** Orijinal ve Çeviri pencereye sığar, diğerleri daralır; başlığa sağ tıkla gizle/göster (hatırlanır);
  tıklayınca tablo yana kaymaz; kaydırma piksel piksel (satır atlamaz). Kontrol Et tablosunda da.
- **Semboller tabloda da** (· boşluk, ¶ satır sonu, → sekme, kod çipleri); sözcükler ortadan bölünmez.
- **Çeviri paneli** `Ctrl+J` ile açılıp kapanır ve yer yetmeyince sağa kaçmaz; başlıkta "No 120 · grup"; Orijinal alanı
  kopyalanabilir.

### Kaldırıldı
- Ayrı Bul ve Değiştir penceresi (yerine çubuk).

## [0.48.1] — 2026-11-06 — Yeni depo

### Değişti
- Proje temiz bir geçmişle yeni depoya (`ismetuluer/nxtr`) taşındı; güncelleme denetimi artık o depoya bakar. Eski depodaki
  (`nx-ceviri-studyosu`) 0.48.0 ve öncesi kurulu kopyalar yeni sürümü bir kez elle indirmelidir: sürümler sayfasından
  `NXTR-<sürüm>-windows.zip` dosyasını indirip eskisinin yerine açın (projeleriniz ve ayarlarınız etkilenmez).

## [0.48.0] — 2026-11-06 — Ajan destekli yerelleştirme

### Eklendi
- **Yapay zekâ ajanıyla yeni oyun desteği:** `AGENTS.md` (her ajanın okuduğu kurallar ve görev yönlendirmesi; `CLAUDE.md`
  ve `GEMINI.md` onu içe aktarır), `docs/rehber/` (başlarken, yeni oyun, eklenti yazma, font, grafik, sorun giderme,
  katkı), `docs/istemler.md` (ajana yapıştırılacak hazır talimatlar), `docs/formats/README.md` (motor → biçim → oyun
  dizini) ve skill'ler (`.claude/skills/`, `.agents/skills/`: `nxtr-yeni-oyun`, `nxtr-sorun-giderme`, `nxtr-font`,
  `nxtr-grafik`, `nxtr-katki`). Proje sahibinin yol haritası `docs/yol-haritasi.md`'ye taşındı.
- **Araçlar** (`python -m nxceviri.arac <komut>`): `teshis` (oyunu açıp `teshis-raporu.md`: TitleID/sürüm, dosya türleri,
  imzalar, motor tahmini, tanınan dosyalar, metin adayları), `ara` (ekranda görülen cümleyi UTF-8/UTF-16/Shift-JIS olarak
  arşivlerin içinde de arar), `dogrula` (eklentiyi gerçek oyun dosyasında bayt bayt geri yazım ve işaret metniyle
  sınar), `eklenti-olustur` (çalışan iskelet + testler), `eklentiler`. Metinleri Tara → Daha Fazla → Teşhis Raporu
  Oluştur… (çıkarma eylemleri de bu menüde).
- **Kullanıcı eklentileri:** `%LOCALAPPDATA%\NXCeviri\eklentiler\` (ve kaynak kurulumda depodaki `eklentiler/`) altındaki
  eklentiler açılışta yüklenir, yerleşiklerden önce denenir; hatalı eklenti uygulamayı durdurmaz. Yardım → Eklentiler…
  (liste, hata ayrıntısı, Eklenti Ekle… zip/klasör, güvenli açma). Proje, metinlerin hangi eklenti ve sürümle
  çıkarıldığını kaydeder ve eksikse uyarır.
- `LICENSE` (MIT) ve `THIRD_PARTY_NOTICES.md`; paket bunları ve bağımlılık lisanslarını (`lisanslar/`) içerir.

### Değişti
- **Güncelleme:** GitHub'a önce anahtarsız sorulur (anahtar yalnızca gizli depoda gerekir). Hazır pakette yeni sürüm
  indirilir, SHA-256 ile doğrulanır ve uygulama kapanınca kendiliğinden kurulur; başarısızsa eski sürüm geri konur.
  "Açılışta güncellemeleri denetle" güncelleme penceresinde. Git ile kurulan kopya `git pull` ile güncellenir.
- DMC1 düşman açıklamaları özgün İngilizce metin yerine metnin SHA-256 özetiyle eşleştirilir (depoda telifli metin
  kalmadı; gerçek oyunda üretilen yama öncekiyle bayt bayt aynı).

## [0.47.0] — 2026-11-02 — NXTR: yeni ad ve logo, seçmeli düzeltme, grup sınırları

### Değişti
- **Uygulamanın adı NXTR** (NX + TR) ve yeni logo: iki Joy-Con'dan esinlenen kare simge (ortada NX/TR) ve yatay logo
  (`docs/tasarim/logo/`). Paket `NXTR-<sürüm>-windows.zip`, program `NXTR.exe`. Ayarlar, projeler (`.nxproj`), kayıtlı
  anahtarlar ve `%LOCALAPPDATA%\NXCeviri` klasörü aynı kalır; güncellemede hiçbir şey kaybolmaz.
- **Kontrol Et → Satır denetimi, Subtitle Workshop gibi:** bulguların altında düzeltilebilir türler onay kutularıyla ve
  sayılarıyla listelenir; **Seçilenleri Düzelt** yalnızca işaretli türleri (tabloda satır seçiliyse yalnızca o satırlarda)
  yerinde düzeltir. Ardından “N satır düzeltildi — Raporu Gör” (önceki/yeni ve uygulanan düzeltme), denetim kendiliğinden
  yenilenir; Ctrl+Z hepsini geri alır. Yazım sözlüğü eylemleri bulgu tablosunun sağ tık menüsünde.
- **Makine Çevirisi penceresi sade:** sağlayıcı/model, iş türü ve kapsam önde; adres, kaynak dil, oyun notları, talimat
  ve “onaylılara da uygula” kapalı başlayan **Gelişmiş** bölümünde (doluysa başlıkta görünür). Sözlük penceresinde İçe/Dışa
  Aktar ve Terim Öner **Daha Fazla** menüsünde. Çevir sayfasının alt düğme satırı kalktı (sağ tık menüsü ve Ctrl+H).
- Çeviri paneli başlığı dar panelde sıkışmıyor; uzun açıklamalar kısaltıldı.

### Eklendi
- **Yeni denetimler:** Eksik etiket (ham `<i>`, `[color=…]`, `{ad}`), Korunan ifade (cümle içindeki alt çizgili kod adları,
  ör. DKCR HD), Çift boşluk, Tekrarlı sözcük (“ve ve”; “güle güle” gibi ikilemelere dokunmaz), Fazla nokta. Kaynakta aynı
  desen varsa uyarı yok.
- **Kod sırası düzeltmesi:** biçim kodları (renk aç/kapa, satır/sayfa sonu) kaynaktaki sıraya dizilir; değer taşıyan kodlara
  (oyuncu adı, sayı) dokunulmaz.
- **Grup başına satır sınırı:** sığdırma kuralı grup (tablo) için de verilebilir (grup > dosya > proje); “Her grup ayrı”
  her grubun sınırını orijinal metinlerden ayrı öğrenir.
- **Satırları yeniden böl** (Çevir → sağ tık → Daha fazla): çevirideki satır sonlarını silip satırı kurala, kural yoksa
  orijinalin satır sayısına göre yeniden böler; kodlar korunur, geri alınabilir.
- **Hatalı satırları da aktar** (Dışa Aktar, varsayılan kapalı, proje başına): oyunun kabul ettiği hatalı satırlar
  çevirisiyle yazılır; Unicorn Overlord'da (FMSB) yalnızca değişken kodlarının yeri değişmiş satırlar da yazılır. Kontrol
  kodu bozuk satırlar orijinal bırakılır ve sonuçta sayılır.

### Kaldırıldı
- Kontrol Et'teki Ollama ile **Otomatik Düzelt** (yerine seçmeli program düzeltmesi).

## [0.46.0] — 2026-11-02 — Sadeleştirme turu

### Değişti
- **Çevir sayfası:** üstte tek birincil düğme (**Makine Çevirisi…**) ve **Daha Fazla** menüsü (Sözlük, Son İşin
  Değişiklikleri, dış redaksiyon/çeviri dosyaları). Tablo araç çubuğundaki hizalama, panel yeri ve simge düğmeleri
  kalktı (Görünüm menüsünde ve durum çubuğunda zaten var). Sağ tık menüsü 12 öğeden 6'ya indi; gerisi **Daha fazla**
  alt menüsünde.
- **Kontrol Et sayfası:** üst çubukta yalnızca **Düzelt** menüsü (Programla/Otomatik Düzelt, yazım sözlüğü) ve
  **Denetle**. Özet tek cümle: “N satır denetlendi — X hata, Y uyarı.” Türlere süzgeçle ulaşılır.
- Uzun ipuçları ve pencere açıklamaları kısaltıldı.

### Kaldırıldı
- “Fazla noktalama” uyarısı: metin içindeki ünlem/soru Türkçede doğaldır, yüzlerce yanlış uyarı üretiyordu. Sona
  eklenen noktalama uyarısı ve yerel düzeltmesi durur.

### Düzeltildi
- **Yazım** bulguları artık bilgi düzeyinde: varsayılan listeyi ve kenar çubuğu sayacını şişirmez, “Yazım” süzgeciyle
  görülür. Ses efektleri (hihihi, ehehehe, ahhh) yazım hatası sayılmaz.

## [0.45.0] — 2026-11-02 — Donkey Kong Country Returns HD metinleri

### Eklendi
- **DKCR HD `Localization` desteği** (`formats/unity/dklocal.py`, Unity eklentisine bağlı): oyunun tüm metni `resources.assets`
  içindeki tek bir `[SerializeReference]` kayıt defterindedir (14 dil, dil başına 1.321 metin). Ayrıştırıcı hem v0 hem güncelleme
  düzenini okur ve her ikisinde ile Rusça topluluk yamasında değişiklik yokken bayt bayt aynı yazar. İngilizce yuvadan
  1.199 metin aktarılır (ses kimlikleri, boş ve harfsiz satırlar atlanır); `<scale=…>`/`<space=…>` etiketleri kontrol kodudur.
  Türkçe aynı yuvaya yazılır, özdeş satırlar ikinci İngilizce yuvaya yansıtılır. Gerçek oyunda aktarma ve dışa aktarma
  (tek dosya: `Data/resources.assets`) doğrulandı. Belge: `docs/formats/dkcr.md`.

### Bilinen sınırlar
- Mod cihazda denenmedi; `ğ ş ı İ` gliflerinin oyun yazı tipinde olup olmadığı denetlenemiyor (TECH_DEBT 81–82). Metin aktarma
  ≈3 dk sürer (TECH_DEBT 83).
## [0.44.0] — 2026-11-02 — Danganronpa: Trigger Happy Havoc metinleri

### Eklendi
- **Spike Chunsoft WAD arşivi** (`archives/wad.py`, `AGAR`): `dr1_data.wad` dizini okunur, üyeler büyük dosya tamamen
  okunmadan açılır, değişenlerle arşiv yeniden kurulur (değişiklik yoksa bayt bayt aynı; gerçek dosyayla doğrulandı).
- **Danganronpa eklentisi** (`formats/danganronpa`): `.lin` betik metinleri (UTF-16LE, `<CLT n>` renk etiketleri kontrol
  kodu), `.pak` metin tabloları (eşya, harita, menü, ipucu…) ve `.lin` içeren betik paketleri. Dil klasöründen
  okunur (`us` → en, `jp` → ja, `ch` → zh-hant). Gerçek oyunda İngilizce kaynakta 6.048 dosya, 176.393 satır; hepsinde
  değişiklik yapılmadan geri yazım bayt bayt aynı.
- Dışa aktarma WAD arşivini yeniden kurar ve doğrular. Belge: `docs/formats/danganronpa.md`.

### Düzeltildi
- **Hiç metin çıkmayan oyunda "0 satır aktarıldı" başarısı gösteriliyordu** (Danganronpa ve Donkey Kong Country Returns HD
  bu yüzden "metin çıkmadı" diye boş geçiyordu). Artık açık bir hata verilir: kaç dosyanın açıldığı, tahmin edilen motor ve
  kaynak dilde metin yoksa oyundaki diller söylenir.

### Bilinen sınırlar
- Mod cihazda denenmedi; `ğ ş ı İ` gliflerinin oyun yazı tipinde olup olmadığı denetlenmedi (`docs/formats/danganronpa.md`).

## [0.43.0] — 2026-11-02 — Türkçe yazım denetimi

### Eklendi
- **Türkçe yazım denetimi:** çevirideki sözlükte olmayan sözcükler Çevir sayfasında çeviri kutusunda kırmızı dalgalı
  çizgiyle işaretlenir; sağ tık menüsünden **yazım sözlüğüne eklenir**. Kontrol Et → Denetle bunları **Yazım** uyarısı
  olarak da listeler; seçilen bulgulardaki sözcükler **Yazım Sözlüğüne Ekle…** ile toplu eklenir. Eklenenler kalıcı
  **kullanıcı sözlüğüne** (`%LOCALAPPDATA%\NXCeviri\yazim-sozlugu.txt`) yazılır, bütün projelerde geçerlidir ve
  **Yazım Sözlüğü…** penceresinden silinebilir. Özel adlar (kaynakta geçenler, cümle ortasında büyük harfli olanlar,
  kesme işaretlilerin kökü), kısaltmalar, kontrol kodları ve oyun sözlüğündeki terimler denetlenmez.
- Sözlük: hunspell-tr (TDD, MPL-2.0). 6,1 milyon sözcük biçimi 11 MB'lık bir Bloom süzgecine indirildi (`assets/spell`,
  lisans metni yanında); süzgeç anında yüklenir ve ek bellek istemez. hunspell-tr'nin ölçütünde (trspell-10) hata
  yakalama kesinliği %99,9, duyarlılığı %97,3. Yeni bağımlılık eklenmedi.

## [0.42.0] — 2026-11-02 — Çeviri talimatı ve hazır talimatlar

### Eklendi
- **Çeviri talimatı:** Makine Çevirisi penceresinde çevir ve yeniden çevir için isteğe bağlı talimat kutusu (yalnızca
  Ollama). Beş hazır talimat: arayüz ve menü metinleri, diyalog ve altyazı, eşya/yetenek açıklamaları, eğitim ve
  ipucu, resmî/eski dil. Talimat oyun notlarının ardından sistem istemine eklenir, projede saklanır ve redaksiyon
  talimatından ayrıdır. Bir grubu (ör. menüler) kendi talimatıyla çevirmek için kapsam olarak "Seçili satırların
  grubu" seçilir. Oyun notları zaten vardı; talimat o işe özel yönlendirmedir.

## [0.41.0] — 2026-11-02 — Sözlük: XLSX, bilgi notları, terim önerisi; noktalama denetimi

### Eklendi
- **Sözlük XLSX olarak içe ve dışa aktarılır** (Sözlük penceresi): iki sütun, `terim` ve `çeviri`. İçe aktarılan
  terimler sözlüğe katılır (büyük/küçük harf duyarsız); var olan terimin yazımı ve notu korunur. Başlıksız dosya
  ve not için üçüncü sütun da okunur.
- **Bilgi notları (lore):** Türkçe karşılığı boş, notu dolu sözlük maddesi. Ad metinde geçtiğinde not modele bilgi
  olarak gider (kim olduğu, nasıl konuştuğu); çeviri zorlanmaz.
- **Terim Öner (Ollama):** metinlerde sık geçen özel adlar programla bulunur, Ollama yalnızca bunlara örnek
  cümlelerle karşılık ve not önerir. Öneriler bir onay penceresinde işaretlenip düzeltilir; onaylanmadan sözlüğe
  bir şey yazılmaz. İş arka planda çalışır, ilerleme gösterir ve iptal edilebilir.
- **Noktalama denetimi:** Kontrol Et, orijinal noktalamasız biterken çevirinin sonuna eklenen işareti ("Start Game"
  → "Oyunu Başlat.") **Sondaki noktalama** olarak bildirir; otomatik düzeltme bunu modele gitmeden atar. Çeviride
  orijinalde hiç olmayan `! ? ; : …` **Fazla noktalama** uyarısı verir. İkisi de Çevir ekranında durum sütununda
  hemen görünür.

## [0.40.0] — 2026-11-01 — Arayüz düzeltmeleri, uydurma koruması ve tutarlılık

### Eklendi
- **Uydurma (halüsinasyon) koruması yeni çevirilerde de:** daha önce yalnızca var olan çevirinin yerine yazılan
  sonuçlar denetleniyordu. Artık ilk çeviride de şu belirtiler aranır: satır çevrilmeden aynen dönmüş, İngilizce
  kalmış, orijinalde olmayan yabancı alfabe harfi (Çince, Kiril…), tekrar döngüsü, orijinalden çok uzun veya çok
  kısa. Belirti varsa satır sorun yazılarak bir kez yeniden istenir; sürerse çeviri yazılır ama **Şüpheli çeviri**
  uyarısı alır (Kontrol Et'te ve Çevir ekranındaki durum sütununda). İş sonu iletisi kaç satır olduğunu söyler.
- **Tutarsız çeviri denetimi:** aynı kaynak metin projede farklı biçimlerde çevrilmişse Kontrol Et → Denetle uyarı
  verir ve biçimleri satır sayılarıyla listeler. Farklı biçimlerin hepsi onaylıysa uyarı verilmez.

### Değişti
- **Ollama daha tutarlı çevirir:** sıcaklık 0,3'ten 0,2'ye indi ve sabit tohum (`seed`) eklendi; aynı istem aynı
  çeviriyi verir. **Oyun notları sistem istemine taşındı:** her partide aynı oldukları için model onlara daha sıkı
  uyar ve Ollama istemin bu bölümünü her partide yeniden işlemez.
- **Anahtarlar ana ekrandan kalktı:** prod.keys ve title.keys artık **Dosya → Anahtarlar** menüsünden seçilir veya
  kaldırılır. Anahtar durumu durum çubuğunun solunda her zaman görünür ("Anahtarlar doğrulandı", "Anahtar
  geçersiz", "Anahtar seçilmedi"); ipucunda dosya yolları ve title.keys bilgisi var, tıklayınca prod.keys seçme
  penceresi açılır. Oyunu Ekle sayfasında anahtar kartı yalnızca geçerli anahtar yokken görünür.
- **"Metinleri Tara →" taramayı hemen başlatır:** tarama sayfasında ikinci kez "Taramayı Başlat"a basmak gerekmez.
  Güncel bir tarama raporu varsa yeniden taranmaz, rapor gösterilir.
- **Çeviri tablosunda sorunlar durumun altında:** Durum sütunu satırın hata ve uyarı sayısını gösterir
  ("✖ 1 hata · ⚠ 2 uyarı"), ipucu her birini açıklar. Etiket, kod ve uzunluk sorunları hemen; sözlük, font ve
  sığdırma uyarıları Kontrol Et → Denetle'den sonra görünür ve çeviri değişince düşer. Onaylı satırların sorunları
  da gösterilir. Durum süzgecindeki seçenek "Hata veya uyarısı olan satırlar" oldu ve aynı listeyi kullanır.

### Düzeltildi
- Alt çeviri panelinde orijinal ve çeviri kutuları çok basıktı; üç satırlık metin kaydırma çubuğu olmadan
  okunamıyordu. Kutular artık yazı boyutuna göre en az üç satırı gösterir.
- Tekrar döngüsü denetimi iç içe geçen tekrarı ("çok çok çok") iki kez sayıyordu; doğal vurgu artık döngü sayılmaz.
- Alt panelin yüksekliği ilk açılışta sabitleniyordu; satır seçince kod çipleri veya uyarı satırı belirdiğinde
  panel büyümüyor, "Çeviri" etiketi ve çipler kutuların üstüne biniyordu. Panel artık içeriğine göre büyür.

## [0.39.0] — 2026-11-01 — Ys Origin: altyazı, yazı tipi yaması, grafik klasörü

### Eklendi
- **SubRip (`.srt`) altyazı eklentisi** (`formats/srt`): Ys Origin'in giriş videosu (`yso_pro.mp4`) yazısızdır; altyazıyı
  oyun `extension/movies/yso_pro_<dil>.srt` dosyasından çizer. Altyazı blokları çeviri tablosuna girer (anahtar sıra
  numarası, bağlam zaman aralığı), zaman damgalarına dokunulmaz, LF/CRLF ve BOM korunur. Dil dosya adından okunur
  (`yso_pro_sp.srt` → es). Gerçek oyunda 8 dosya tanındı, İngilizce kaynakla 18 satır aktarılıyor.
- **Ys Origin yazı tipi yaması** (`fontpatch/bmfont.py`, `ys_fonts.py`): oyunun beş Latin BMFont yazı tipine
  (`arial`, `ysfont`, `linuxwhite`, `linuxshadow`, `linuxwhitesmall`) eksik `ğ Ğ ş Ş ı İ` harfleri yazı tipinin kendi
  glifleriyle türetilip eklenir; dış çizgi ve gölge korunur. Dışa aktarma bu dosyaları moda koyar ve harfleri artık
  g/s/i'ye çevirmez. Atlas doluysa yüksekliği ikiye katlanır.
- **Ys Origin grafik klasörü** (`fontpatch/ys_graphics.py`): menü düğmeleri, onay kutuları, harita/patron adları, hikâye
  ve rehber sayfaları gibi İngilizce yazı içeren 150 resim `<oyun klasörü>/grafik_temizleme/orijinal` içine PNG olarak
  çıkarılır; kullanıcı yazıyı Türkçe yapıp `temiz` klasörüne aynı adla kaydeder, dışa aktarma değişenleri DDS
  başlığını, biçimini ve mip zincirini koruyarak yerleştirir (`data-en` arşivi yeniden kurulur, serbest dosyalar moda
  eklenir). Klasör `NXCEVIRI_YS_GRAFIK` ortam değişkeniyle değiştirilebilir.
- Dışa aktarmada eklentiler için yeni kanca: `derived_files(read, files, game_dir)` (`formats/derived.py`,
  `export/extras.py`): metinden bağımsız dosya ve arşiv üyeleri üretir; `ExportResult.extra_notes` bilgi dosyasına yazılır.

### Düzeltildi
- **Ys Origin arayüz XML'inde satır sonu `\n` olarak yazılıyordu** ve oyunda "¥n" görünüyordu. XML'deki satır sonu
  gerçek satır sonudur (gerçek dosyada hiç `\n` yok); artık gerçek satır sonu yazılır. XSO dizgeleri etkilenmedi.

### Bilinen sınırlar
- Mod cihazda denenmedi (TECH_DEBT 71). Ana arşivdeki resimler (`MENU/CHRSELECT.DDS` "Character Select") henüz
  çevrilemez (TECH_DEBT 74). Grafik klasörünü üretmek ve seçmek için arayüz yok (TECH_DEBT 75).

## [0.38.0] — 2026-11-01 — Uygulama simgesi

### Eklendi
- **Uygulama simgesi:** mavi zemin üzerinde iki konuşma balonu ("A" → "Ç"). `NXCeviri.exe`'nin kendisinde,
  pencere başlığında ve görev çubuğunda görünür. Kaynak `nxceviri/gui/appicon/nxceviri.svg`; .ico (16–256 piksel)
  ve .png `packaging/make_icon.py` ile üretilir.

### Doğrulandı
- Taşınabilir paket Windows 11'de derlendi; ürün sahibi oyun ekleme → tarama → çeviri → dışa aktarma akışını
  paketle denedi, çalışıyor.

### Düzeltildi
- CI denetimleri yeniden yeşil: testlerdeki tip hataları (yeni PySide6 tip tanımları, `TranslationRow`'a yanlış
  sütuna verilen grup) giderildi; pytest-qt'nin tipsiz `QtBot` yöntemleri mypy'de muaf tutuldu.
- CI'daki ekransız (offscreen) testler Windows yazı tiplerini görmüyordu; metinler yedek yazı tipiyle iki kat geniş
  ölçüldüğü için düzen testleri yanlış başarısız oluyordu (`QT_QPA_FONTDIR`).

## [0.37.0] — 2026-11-01 — Diğer sayfalar: başlık eylemleri ve durum çipi

### Değişti
- **Oyunu Ekle, Metinleri Tara, Kontrol Et, Dışa Aktar** çeviri sayfasıyla aynı dile geçti: ana eylem başlığın sağında
  (vurgulu), yardımcı eylemler yanında. "Metinleri Tara →", "Taramayı Başlat", "Çeviri Tablosuna Aktar →" ve
  "Modu Oluştur" artık sayfanın üstünde.
- **Durum çipi:** uzun uyarı şeritleri başlıkta kısa bir çipe dönüştü ("2 sorun · 1 uyarı", "3 uyarı",
  "Desteklenmeyen biçim"); ayrıntılar çipe tıklayınca açılan küçük pencerede okunur (seçilip kopyalanabilir).
  Tarama uyarıları artık kırpılmaz (önceden en çok 6 tanesi gösteriliyordu).
- **Metinleri Tara:** başlıkta her an yalnızca o duruma ait eylemler görünür (başlat / tekrar dene / yeniden tara,
  kaynak dil, aktar); boş durumda ikinci düğme kalktı.
- **Kontrol Et:** her sekmenin kendi eylem satırı var (Denetle, Programla Düzelt, Otomatik Düzelt…; Sığdırmayı aç,
  Orijinalden öğren; Fontları Tara); sekme adını tekrarlayan kart başlıkları kalktı. "Çift tıklayın…" açıklaması
  tablonun ipucuna taşındı.
- **Dışa Aktar:** özet tek satır ("21 yazılacak · 0 hatalı · 10 çevrilmemiş · Harf dönüştürme: yok"); mod oluşturulurken
  "Modu Oluştur" pasif.
- **Oyunu Ekle:** devam edilemiyorsa nedeni başlıktaki çipte ve düğmenin ipucunda; anahtar kartı "Anahtarlar",
  bırakma alanı metni kısaldı.

### Eklendi
- Ortak parçalar: `PageHeader`, `ActionBar`, `StatusChip` (`nxceviri/gui/widgets.py`).

## [0.36.0] — 2026-11-01 — Ys Origin ve Unicorn Overlord

### Eklendi
- **Ys Origin:** Falcom NNI arşivleri (`ys_data/archives/data-<dil>.ni` + `.na`) okunup yazılıyor
  (`core/archives/nni.py`). Harita betiklerindeki (`LOC/<DİL>/…/*.XSO`) diyalog ve eşya/menü yazıları ile arayüz
  dizgeleri (`loc/strings/english.xml`) çeviri tablosuna aktarılıyor (`formats/ysorigin`). Betik kimlikleri
  (`V_180`, `OPEN`, `@Flag_Inv`) aynı betiğin Japonca kopyasıyla karşılaştırılarak ayıklanır. Gerçek oyunda
  İngilizce kaynakla 10.787 satır. Mod: `data-en.ni`, `data-en.na` (değişen betikler sona eklenir) ve `english.xml`.
- **Unicorn Overlord:** CRI CPK arşivleri okunuyor ve değişen dosyalarla yeniden kuruluyor; CRILAYLA sıkıştırması
  açılıyor (`core/archives/cpk.py`). Vanillaware MsgSheet (`MsgSheet/*.fms`) eklentisi (`formats/fmsb`): renk,
  eğik yazı, ad değişkeni, vurgu gibi kodlar `⟦n⟧` olur. Gerçek oyunda İngilizce kaynakla 49.242 satır. Mod yalnızca
  `Unicorn_US.CPK`; ana arşivdeki Japonca sayfalar otomatik atlanır.
- İki oyunun fontunda olmayan `ğ Ğ ş Ş ı İ` dışa aktarmada g, s, i, I'ya dönüştürülür (`ç ö ü` korunur).
- Motor tahmini: "Falcom (Ys Origin)" ve "Vanillaware / CRI (Unicorn Overlord)".

### Bilinen sınırlar
- İki oyunda da mod henüz cihazda denenmedi (TECH_DEBT 71). Unicorn Overlord'da metin aktarma ~27 sn sürer
  (saf Python CRILAYLA, TECH_DEBT 72). Ys açılış videosu altyazısı (`.srt`) ve Unicorn Overlord yardım resimleri
  aktarılmıyor (TECH_DEBT 73).

## [0.35.0] — 2026-11-01 — Çeviri sayfası: düzenleme paneli ve semboller

### Eklendi
- **Düzenleme paneli:** seçili satırın özgün ve çeviri metni ayrı bir panelde düzenlenir. Panel **altta**, **sağda** ya
  da **kapalı** olabilir (üç durumlu düğmeler, Ctrl+Alt+B / Ctrl+Alt+R); seçim ve bölme oranları hatırlanır. Pencere
  küçükse panel kendiliğinden uyum sağlar (dar pencerede "sağda" yerine altta, altta sığmıyorsa sağda, ikisi de
  yetmiyorsa gizli); seçiminiz değişmez.
  Enter kaydeder, Shift+Enter yeni satır açar, Esc kayıtlı hâle döndürür; Alt+↑/↓ önceki/sonraki satır. Panel kaydı
  tablo düzenlemesiyle aynı yoldan geçer (geçmiş ve geri alma aynen çalışır); bekleyen metin satır değişince, panel
  kapanınca, makine çevirisi başlayınca, proje değişince ve pencere kapanırken kaydedilir.
- **Sembolleri göster/gizle** (Ctrl+Shift+8; araç çubuğu, Görünüm menüsü ve durum çubuğu): boşluk `·`, satır sonu `¶`,
  sekme `→`, bölünmez boşluk `°`; satır sonundaki boşluklar uyarı zeminiyle işaretlenir. Tabloda ve panelde çalışır.
- **Metin hizası** (sola/ortaya/sağa; Ctrl+L / Ctrl+E / Ctrl+R): tablo ve panelde, yalnızca görünüm; metne boşluk eklenmez.
- **Kontrol kodu çipleri:** tabloda `⟦1⟧` yerine koda göre renkli ve simgeli çip (satır sonu ↵, sayfa sonu §, değişken ◆,
  sembol ★, biçim ●, diğer ◇); türler Kontrol Et → Sığdırma tablosundan gelir. Paneldeki çipe tıklamak kodu imlece ekler.
- **Panel sayacı:** Sığdırma sınırı varsa "Satır 23/40 · Sayfa 3/4" (aşılınca renkli), yalnızca `max_length` varsa "N/sınır",
  yoksa karakter sayısı; orijinalde olmayan satır sonu boşluğu için uyarı.
- **Durum çubuğu:** panelin imleç konumu ("Satır 3 · Sütun 14", yalnızca panel odaktayken) ve ¶ düğmesi.
- 7 yeni simge (Lucide 1.66.0): `pilcrow`, `align-left/center/right`, `panel-bottom`, `panel-right`, `chevron-up`.

### Değişti
- Çeviri tablosunun Özgün ve Çeviri hücreleri çipli/sembollü çizilir (hücre düzenleyicisi aynı); çizilen HTML sınırlı bir
  ön bellekte tutulur, 5.000 satırda ölçüm akıcıdır.
- `fit.split_lines` herkese açık yapıldı (önceden `_split_lines` başka modülden içe aktarılıyordu).

## [0.34.0] — 2026-10-31 — Arayüz altyapısı

### Eklendi
- **Simge sistemi** (`gui/icons.py`): Lucide simgeleri (ISC lisansı, `gui/icons/` altında SVG dosyaları, sürüm
  `icons/README.md`'de) temaya uyan renkte ve yüksek DPI'da keskin çizilir; açık/koyu tema değişince yenilenir. Yeni
  bağımlılık yok, çalışma sırasında hiçbir şey indirilmez. Eksik ya da bozuk SVG uygulamayı durdurmaz.
- **Kenar çubuğu:** her adımın simgesi ve sağında rozeti var (eklenen dosya sayısı, bulunan metin dosyası sayısı, çevrilen
  yüzde, denetimdeki hata+uyarı sayısı); tamamlanan adımın simgesi onay işaretine döner. Üstte proje adı ve
  oyun · TitleID · sürüm bilgisi görünür (uzunsa kısaltılır, tamamı ipucunda).
- **Durum çubuğu bölmeleri:** satır sayısı, ilerleme çubuğu, hatalı satır sayısı (tıklayınca Kontrol Et açılır),
  çeviri sağlayıcısı (Ollama · model / DeepL) ve kayıt durumu. Bölmeler yalnızca anlamlıyken görünür; geçici
  iletiler ve “Yeni sürüm” rozeti eskisi gibi çalışır.
- **Windows vurgu rengi:** “Sistem” temasında Windows'un vurgu rengi kullanılır (kontrast yetersizse sabit renge
  dönülür); Açık/Koyu elle seçilince sabit renkler kullanılır.
- Düğmelere simge eklendi (metinler aynı); sayfa başlıklarının yanında adım simgesi var.

### Değişti
- “i” bilgi düğmeleri kalktı; bilgi metni kaybolmadan başlığın üstüne gelince ipucu olarak görünür.
- Sayfa başlıkları numarasız (“Çevir”, “Kontrol Et” …); başlığı tekrarlayan kısa açıklama satırları silindi.
- Çeviri tablosundan yapılan her düzenlemeden sonra kenar çubuğu rozeti ve durum çubuğu anında güncellenir.
- Tema: alan çerçevesi `QSpinBox`'a da uygulandı; devre dışı alanlar soluk gösterilir.

## [0.33.0] — 2026-10-31 — Rhythm Heaven Groove: derece resimleri Türkçe

### Eklendi
- **Resimdeki yazıların çevirisi (Rhythm Heaven Groove):** Sonuç ekranındaki derece yazıları ("Good", "Superb",
  "Try Again" …) metin değil, `graph/result/rank_USen.tex` / `rank_EUen.tex` dokusuna çizilmiş resimdir. Dışa aktarma
  bu yazıları, projedeki `common.msbt` → `rank_00_*` / `rank_01_*` satırlarının çevirisinden, oyunun kendi fontuyla ve
  özgün renklerle yeniden çizer; redakte edilen derece adı resme de yansır. Çevrilmemiş derecenin resmine dokunulmaz.
- `core/fontpatch/switchtex.py`: Switch GPU dokularının block-linear düzenini çözen/geri yazan kodlayıcı (Tegra X1 GOB
  düzeni; dolgu ve dosya sonu baytları korunur) ve oyunun zstd çerçeve ayarlarıyla (2 MB pencere, sağlama toplamı)
  yeniden paketleme. Biçim notları: `docs/formats/rhg-tex.md`.
- Atlas SHA-1 özetiyle tanınır; oyunun başka sürümünde resim farklıysa dosyaya dokunulmaz ve uyarı verilir.

## [0.32.0] — 2026-10-31 — Metin sığdırma

### Eklendi
- **Satır ve sayfa sınırı denetimi** (Kontrol Et → yeni **Sığdırma** sekmesi): "Satırda en çok karakter" ve "Sayfada en çok satır"
  girilince Denetle üç yeni uyarı bulur: `Satır uzun`, `Sayfa uzun`, `Kötü bölünme` (gereksiz kısa kesilmiş satır). Sınır
  karakterle ölçülür (piksel değil, font gerekmez). Proje sınırı ve dosya başına ayrı sınır vardır; **Orijinalden öğren**
  orijinal metinlerden öneri üretir. Sınır yokken (veya Sığdırmayı aç kapalıyken) hiçbir şey yapılmaz.
- **Otomatik bölme:** Programla Düzelt, sorunlu sayfayı noktalamadan, yoksa kelime bitiminden dengeli böler; kelime ortasından
  bölmez, sorunsuz sayfaya dokunmaz, sayfa sonu kodlarının sayısını ve yerini değiştirmez, satır sonu kodlu sayfalarda kod
  sayısını ve sırasını sabit tutar. Orijinalde de olan kısa bölünme (menü, liste) sorun sayılmaz; içinde boş satır ya da
  sekme olan sayfa birleştirilmez, olduğu gibi kalır.
- **Kontrol kodu türleri** (satır sonu, sayfa sonu, değişken, sembol, biçim, diğer): kodun etiketinden tahmin edilir, sekmedeki
  tablodan düzeltilir; uzunluk hesabı türe göre yapılır (değişken birkaç, sembol bir karakter, biçim sıfır).
- **Temizlik seçenekleri** (yalnızca orijinalde olmayan kalıba dokunur): gereksiz boşluk, noktalama öncesi boşluk, tekrarlı noktalama.
- **Sığmayanlar:** Sınıra sığdırılamayan satırlar (tek kelime sınırdan uzun, sayfa çok kalabalık) yerelde değişmeden bırakılır ve
  Otomatik Düzelt ile kısaltılmak üzere modele gider; dönen sonuç sınıra sığmazsa eski çeviri korunur. Başka bir sorun için
  düzeltilen satır, sınır yüzünden reddedilmez.

### Değişti
- Bir satıra satır/sayfa sınırı uygulanıyorsa eski **Satır sonu** denetimi (satır sayısı özgünle aynı olmalı) o satır için
  kapanır; satır sayısını sınırlar belirler. Sınır yoksa eski davranış aynen sürer.
- Tema: sayı kutuları (QSpinBox) koyu/açık temada diğer alanlarla uyumlu çizilir.

## [0.31.18] — 2026-10-31 — Devil May Cry: terminoloji ve Hareket listesi

### Eklendi
- `docs/terminoloji-dmc1.md`: grafik ve metin çevirilerinin ortak terim listesi (onaylandı).
- Devil May Cry Hareket ekranının sol listesi (`status_u/act_init.dat`, `status/act_init.dat`) Türkçeleştirildi;
  hareket adları açıklama sayfalarının başlıklarıyla aynıdır (Girdap, Tekme 13, Cehennem …).

- Kullanıcı grafikleri (`temiz`) dosya özellikleri değişse de yüklenir: boyutu farklıysa özgün boya ölçeklenir,
  saydamlık kaydedilmemişse özgünün alfa kanalı korunur (önceden boyutu farklı sayfa sessizce atlanıyordu).
- `docs/grafik-cevirileri-dmc1.md`: görev, gizli görev ve dükkân sayfalarının metinleri ve Türkçeleri.
  Proje metinleri ve terminolojiyle karşılaştırılarak gözden geçirildi: tırnaksız özel adlar, Nightmare çevrilmez,
  Court → Avlu, Ruh Taşı / İksir / Kadeh / Kılavuz Işık terimleri, "yaşam gücü" tutarlılığı.

### Düzeltildi
- "görev başla" → "göreve başla"; grafiklerde Devil Trigger → Şeytan Tetiği, UnderWorld → Yeraltı Dünyası.
- Çeviri tablosunda ekrandan uzun bir satırın (uzun paragraf) sonuna inilemiyordu; dikey kaydırma artık piksel
  piksel.

## [0.31.17] — 2026-10-31 — Switch oyun fontlarına Türkçe harf ekleme

### Eklendi
- **Kontrol Et → Fontları Tara** artık Switch oyunlarının gömülü fontlarını (`mesg/Font/*.bfttf.zs`,
  `*.bfotf.zs`) da bulur ve eksik Türkçe harfleri raporlar. Font yaması açıksa dışa aktarma bu fontlara
  `ı İ ş Ş ğ Ğ` harflerini kendi çizimlerinden türeterek ekler (`core/fontpatch/switchfont.py` artık
  dışa aktarmaya bağlı). Yalnızca ASCII taşıyan Çince/Korece fontlar Latin metin fontu sayılmaz, yamalanmaz.
  Rhythm Heaven Groove'da menüdeki `ş` kutu olarak çiziliyordu ve `İ` başka bir fonttan geliyordu; oyunun 12 Latin
  fontu yamalandı.

### Değişti
- **5. Dışa Aktar** ekranı, fontlarda eksik Türkçe harf olduğu ve font yaması kapalı olduğu hâlde harfler
  dönüştürülmüyorsa uyarır. Daha önce yama kutusu varsayılan olarak kapalıydı ve dışa aktarma sessizce
  yamasız mod üretiyordu (Rhythm Heaven Groove'da kullanıcı fontlu modu yeniden üretince harfler yine kutu çıktı).

## [0.31.16] — 2026-10-30 — Mod, aynı dilin diğer bölge klasörlerine de yazılır

### Düzeltildi
- Nintendo düzenindeki oyunlarda (`mesg/US/USen/…`) mod yalnızca kaynak dilin klasörünü değiştiriyordu. Switch
  oyunu dil klasörünü konsolun dilinden seçtiği için "English (UK)" seçili konsolda oyun `EU/EUen` klasörünü okuyor
  ve mod hiç görünmüyordu (Rhythm Heaven Groove). Dışa aktarma artık çeviriyi aynı dilin diğer bölge kopyalarına
  (`EU/EUen`, `US/USfr` → `EU/EUfr` …) da yazar. İkiz dosyanın kendi orijinali temel alınır; çevrilmeyen satırlar
  o bölgenin metninde kalır. Etiketleri kaynak dosyayla uyuşmayan ikiz dosya yazılmaz ve uyarı verilir.

## [0.31.15] — 2026-10-30 — Kopya (0.31.7–0.31.14) ile GitHub (0.31.7) birleştirildi

0.31.6'dan sonra iki yapay zekâ ayrı yönlerde ilerlemişti: GitHub'daki sürüm CSV'yi iki sütuna indirmiş, ayrı bir kopya
ise TXT/XLSX dış redaksiyonunu geliştirmişti. Bu sürüm ikisini tek yerde toplar.

### Eklendi (kopyadan)
- Dış redaksiyon/çeviri: TXT (varsayılan, üç sütun: orijinal, çeviri, düzeltme + grup), XLSX; "Redakte" durumu
  (şema 6); yazmadan önce önizleme; dış çeviri istemleri. Bul ve Değiştir: tek tek, kapsam, düzenli ifade.
- Addressables katalog CRC düzeltmesi (`core/export/addressables.py`); Switch yazı tipi yaması
  (`core/fontpatch/switchfont.py`); `sd_kontrol.py` / `SD Kontrol.bat` (SD kart denetimi).
- Daha ayrıntılısı aşağıdaki 0.31.14 … 0.31.7 girişlerinde.

### Değişti
- GitHub 0.31.7'nin iki sütunlu CSV'si (orijinal | ceviri) kopyanın TXT/XLSX tasarımıyla aynı amacı karşıladığı için kodu
  kopyanınkine bırakıldı; CSV hâlâ okunur. Bunun sonucu: içe aktarınca değişiklikler penceresinin otomatik açılması
  yerini yazmadan önce önizlemeye bıraktı.

## [0.31.14] — 2026-10-28 — Toplu bul ve değiştirmede kapsam, düzenli ifade ve önizleme

### Eklendi
- **Bul ve Değiştir** penceresinde **tek tek değiştirme**: “Sonrakini Bul” (F3) eşleşmeler arasında gezer,
  “Sonrakini Değiştir” yalnızca gösterilen satırı yazar ve sonraki eşleşmeye geçer. “Tümünü Değiştir”
  kalanların hepsini yazar. Tek tek yazımlar aynı iş kimliğini kullanır: **Ctrl+Z hepsini tek işlem** olarak
  geri alır.
- Pencerede geçerli eşleşmenin **dosya · anahtar**, **orijinal**, **şu anki** ve **yeni** metni gösterilir;
  altta “Eşleşme 3 / 12” sayacı ve ilk üç satırın önizlemesi bulunur.
- Pencere içinde **Ctrl+F** “Aranan” alanına gelir; “Aranan” alanında **Enter**, “Yerine” alanında **Enter**
  sırasıyla sonraki eşleşmeye geçer / sonrakini değiştirir.
- **Kapsam** seçimi eklendi: tüm satırlar, tabloda görünenler (süzgeç uygulanmış liste) veya seçili satırlar.
  Kullanılamayan kapsam (süzgeç yokken “görünenler”, seçim yokken “seçili satırlar”) listede pasif görünür.
- **Düzenli ifade (regex)** seçeneği: grup kullanılabilir, yerine yazılan metinde `\1`, `\2` … grup
  başvuruları çalışır. Geçersiz ifade pencere içinde anlaşılır bir hata olarak gösterilir ve değiştirme
  düğmeleri kapalı kalır.
- Çeviri tablosundaki toplu işlem düğmelerinin yanına **"Bul ve Değiştir…"** düğmesi eklendi.
- Çeviri tablosunun sağ tık menüsüne **"Satırı yerinde göster"** eklendi: aramada tek başına görünen satırın
  çevresini görebilmek için arama metni ve süzgeçler temizlenir, satır gerçek yerinde komşularıyla birlikte
  ekranın ortasına getirilir.

### Değişti
- Düz metin aramasında “Yerine” metni olduğu gibi yazılır (`\1` grup başvurusu sayılmaz); düzenli ifade
  kapalıyken `.` ve `[` gibi karakterler özel anlam taşımaz.
- Kontrol kodu (⟦1⟧ …) koruması düzenli ifadede de geçerlidir: kontrol kodunu bozacak satır değiştirilmez,
  atlanan satır sayısı özet satırında bildirilir.
- Arama metni silindiğinde veya süzgeçler değiştiğinde tablo artık başa dönmüyor: seçili satır görünür
  kalıyorsa görünüm o satırın olduğu yerde kalır.

### Düzeltildi
- **Kong’da bazı fontlara Türkçe harfler eklenmiyordu.** TMP fontları `m_AtlasTextures` dizisini 4/8
  yuvalı yazar; kullanılmayan yuvaların `m_PathID` değeri `0`’dır. Yama bu boş yuvaları “birden çok
  atlas” sayıp fontu atlıyordu (`BAIJAMJUREE-LIGHT`, `BAIJAMJUREE-MEDIUM`, `KumbhSans-Medium`). Artık
  yalnızca gerçek doku başvuruları sayılır; boş yuvalar yok sayılır (`core/fontpatch/unity.py`).
- Fontta büyük harfli donor yoksa (`Ç`, `Ü`) `Ş`/`Ğ` artık üretilemiyordu. Aynı büyüklükteki donor
  bulunamazsa diğer büyüklükteki donor (`ç`, `ü`) kullanılır; çengel/breve büyük harfte büyütülmez,
  yalnızca taban harfin boyuna göre konumlandırılır (`core/fontpatch/tmp.py`).

## [0.31.13] — 2026-10-27 — Addressables katalog CRC düzeltmesi (Kong modu oyunda açılmıyordu)

### Düzeltildi
- Değiştirilen bir Unity Addressables paketi oyunda **hiç yüklenmiyordu**: katalogdaki
  `AssetBundleRequestOptions.m_Crc` sıfırdan farklıysa Addressables paketi
  `AssetBundle.LoadFromFileAsync(yol, crc)` ile açar ve yeniden yazılan paketin CRC'si
  tutmadığı için yükleme başarısız olur. Artık dışa aktarma, değiştirilen paketlerin
  katalog kayıtlarının CRC'sini sıfırlar ve düzeltilmiş `catalog.json`'ı moda ekler
  (`core/export/addressables.py`). Kayıt uzunlukları korunur (giriş verisi kayıtlara bayt
  ofsetiyle bağlıdır); yalnızca boyutu değişen dosyaların özgün boyutuyla eşleşen, CRC'si
  sıfırdan farklı kayıtlar düzeltilir.
- Bilgi dosyasına “Addressables katalog CRC düzeltmesi” satırı eklendi; katalog bulunamazsa
  veya düzeltilemezse dışa aktarma uyarı verir. Katalog yoksa/CRC gerekmiyorsa davranış eskisi gibidir.

## [0.31.12] — 2026-10-27 — Dış çeviri dosyaları (TXT/XLSX)

### Eklendi
- **Dış çeviri dosyası:** çeviriler TXT veya XLSX olarak dört sütunla dışa aktarılabilir: `orijinal`, `çeviri`,
  `yeni çeviri`, `grup`. Çevirmen ya da model yalnızca `yeni çeviri` sütununu doldurur; boş bıraktığı satırın
  mevcut çevirisi olduğu gibi kalır. `grup` salt okunur bağlamdır. Dosya adı varsayılan olarak `…_ceviri.txt` /
  `…_ceviri.xlsx` olur; parçalama ve gruba göre ayırma redaksiyonla aynıdır.
- Araçlar menüsüne **“Dış Çeviri Dosyası Oluştur (TXT/XLSX)…”** ve **“Dış Çeviriden İçe Aktar…”** eklendi.
  Çevir sayfasındaki düğme artık **“Dışa/İçe Aktar”**; menüsünde redaksiyon ve çeviri eylemleri birlikte durur.
  Sağ tık menüsünden de seçili satırlarla dış çeviri dosyası oluşturulabilir.
- Dış çeviriden içe aktarma, redaksiyonla aynı önizleme akışını kullanır: “Yaz” işareti, satır satır ret,
  “Yeni” hücresini düzenleme, “Tümünü Yaz / Hiçbirini Yazma”. Yazılan satırlar **Makine** durumu ve
  `translation-…` iş kimliğiyle kaydedilir; “Son İşin Değişiklikleri” veya Ctrl+Z ile geri alınabilir.

### Değişti
- `yeni çeviri` / `yeni ceviri` başlığı düzeltme sütunu olarak tanınır; başlık varsa sütun sırası oradan çözülür.
  Eski üç sütunlu TXT/XLSX dosyaları ve mevcut dış redaksiyon biçimi değişmeden okunmaya devam eder.
- İş etiketlerine “Dış çeviriden içe aktarma”, durum işaretlerine “dış çeviri” eklendi.

## [0.31.11] — 2026-10-27 — Redaksiyon önizlemesinde satır satır kabul, ret ve düzenleme

### Eklendi
- Dış redaksiyondan içe aktarma önizlemesine **“Yaz”** sütunu geldi: her satır varsayılan olarak işaretlidir;
  işareti kaldırılan satırın mevcut çevirisi ve durumu değişmez.
- **“Yeni”** hücresi artık düzenlenebilir (çift tıklama veya F2). Öneri beğenilmezse satır atlanmadan metin
  düzeltilebilir; hücredeki renkli sözcük farkı düzenlemeden sonra tazelenir.
- “Tümünü Yaz” ve “Hiçbirini Yazma” düğmeleriyle çok satırlı dosyalarda işaretler topluca değiştirilebilir.
- “Çevirilere Yaz (n)” düğmesindeki sayı gerçekten değişecek satırları gösterir; boş ya da önceki çeviriyle aynı
  kalan satırlar sayılmaz.

### Değişti
- Düzenlenen düzeltme, içe aktarmadaki model çıktısıyla aynı onarım/temizlikten geçer (`csvio.prepare_correction`:
  `repair_codes`, `clean_output`, `match_edges`). Boş bırakılan veya kontrol kodları uymayan satırlar yazılmadan
  önce uyarıyla durdurulur; kullanıcı satırı düzeltir ya da işaretini kaldırır.
- Yalnızca kabul edilen ve gerçekten değişen satırlar `Redakte` durumuyla yazılır.

## [0.31.10] — 2026-10-27 — Satır sonları tabloda gerçek satır olarak görünür

### Değişti
- Çeviri tablosunda ve “Kontrol Et” bulgu listesinde satır sonları artık “⏎” simgesiyle değil, ipucu
  önizlemesindeki gibi gerçek satır sonu olarak gösterilir. Hücre yüksekliği metnin satır sayısına göre ölçülür.
- “Metni kaydır” kapatıldığında satırlar tek satır yüksekliğinde kalır ve satır sonları boşluğa döner; böylece
  metnin ilk satırdan sonrası kaybolmaz.

## [0.31.9] — 2026-10-27 — Dış redaksiyonda grup bağlamı

### Eklendi
- **`grup` sütunu:** Dışa aktarılan TXT/XLSX dosyaları artık dördüncü sütun olarak satırın grubunu taşır
  (`UI`, `Dialogue`, dosya adı…). Redaksiyon modeli metnin menü/düğme mi, konuşma cümlesi mi olduğunu görüp
  üslubu buna göre seçer; “UI” satırları kısa etiket gibi, “Dialogue” satırları cümle gibi redakte edilir.
  Sütun salt okunurdur; içe aktarmada hiçbir zaman çeviriye yazılmaz.
- Aynı `(orijinal, çeviri)` çifti birden çok kez geçtiğinde `grup` sütunu doğru satırı seçer.

### Değişti
- TXT/XLSX başlığı `orijinal, çeviri, düzeltme, grup` oldu; hazır istemler grup bağlamını ve salt okunur sütun
  kuralını açıklar. Eski üç sütunlu dosyalar ve eski CSV dosyaları değişmeden okunur; grup adı tanınmasa bile
  düzeltmeden sonraki son sütun bağlam sayılır.

## [0.31.8] — 2026-10-27 — Redakte durumu ve XLSX ile dış redaksiyon

### Eklendi
- **“Redakte” durumu:** dış redaksiyondan içe aktarılan düzeltmeler artık makine çevirisi sayılmaz; yeni
  `Status.REDACTED` durumuyla yazılır. Redakte satırlar ilerlemede çevrilmiş sayılır, oyuna aktarılır ve
  onaylanabilir. Durum süzgecinde yalnızca o durumda satır varsa görünür.
- Onaylı satırlar da redakte edilebilir; içe aktarmayı onayladığınızda durumları “Redakte” olur. Redakte metin
  çeviri belleğine `human` kaynağıyla yazılır, böylece makine çevirisi onu ezmez.
- **XLSX dışa aktarma:** Dışa aktarma penceresinde CSV'nin yerini Excel'de açılan XLSX aldı. TXT'deki gibi üç
  sütun (`orijinal`, `çeviri`, `düzeltme`); hücrelerdeki gerçek satır sonları korunur, başlık kalın ve
  dondurulmuştur. TXT varsayılan biçim olarak kaldı.
- XLSX dosyaları yeniden içe aktarılabilir (Excel'de elle doldurup geri yükleme). Biçim uzantıya değil ZIP
  imzasına bakılarak tanınır.
- Proje şeması 6. sürüme yükseltildi (`text_entries` CHECK kısıtına `redacted` eklendi); göç eski projeleri ve
  çeviri geçmişini korur.

### Değişti
- Eski CSV biçimi artık dışa aktarma seçeneği değil; yalnızca eski dosyalar için içe aktarmada okunur.

## [0.31.7] — 2026-10-27 — TXT ile üç sütunlu dış redaksiyon

### Eklendi
- **TXT dış redaksiyon (varsayılan):** Dışa aktarma penceresi artık TXT/CSV seçtirir; TXT, sekme ayraçlı üç
  sütundur: `orijinal`, `çeviri`, `düzeltme`. Model yalnızca `düzeltme` sütununu doldurur; boş bıraktığı satırın
  mevcut çevirisi korunur. Böylece modelin `id`/`anahtar` sütunlarını ve çeviri metnindeki tırnakları yeniden
  yazması gerekmez; içerikteki yoğun kontrol kodları daha az bozulur.
- TXT içe aktarmada satırlar `(orijinal, çeviri)` çiftiyle, çift tutmazsa benzersiz orijinal veya çeviri metniyle
  eşleşir. Aynı metin birden çok kez geçiyorsa dosya sırasıyla eşleştirilir; belirsiz eşleşme yazılmaz ve
  özetlenir. Hücrelerdeki `\n`, `\t`, `\\` kaçışları korunur; ``` çiti, öndeki açıklama ve İngilizceye çevrilmiş
  sütun adları tanınır.
- Dolu `düzeltme` mevcut çevirinin yerine geçer; boş düzeltme “değişmeyecek” olarak sayılır (hata değildir).
  Kontrol kodu uymayan satır yazılmaz, eski çeviri korunur.
- **Yazmadan önce önizleme:** İçe aktarma, değişiklikleri “Satır / Orijinal / Önceki / Yeni” sütunlarıyla, sözcük
  farkları renkli olarak gösteren bir pencerede onaya sunar (özet: eşleşmeyen, kodu uymayan, onaylı satırlar).
  “Çevirilere Yaz” demeden hiçbir şey değişmez; yazıldıktan sonra aynı karşılaştırma “Son İşin Değişiklikleri”
  ve satır geçmişinde durur.
- Biçim, dosya uzantısına değil içeriğe bakılarak tanınır: `.txt` uzantılı eski CSV dosyaları da okunur.

### Değişti
- Çevir sayfasındaki **CSV** düğmesi **Redaksiyon** oldu; menü ve Araçlar menüsü “dış redaksiyon” olarak
  adlandırıldı. CSV biçimi (`id, anahtar, orijinal, ceviri`) seçenek olarak korunur.

## [0.31.7 · GitHub kolu] — 2026-10-30 — Sade iki sütunlu CSV (kopyadaki TXT/XLSX tasarımıyla birleştirilirken kodu kopyanınkine bırakıldı)

### Değişti
- **CSV artık iki sütunlu:** `orijinal` | `ceviri`. Satır kimliği, anahtar ve dosya adı yazılmaz; sohbet modelleri
  bunları sık sık bozuyordu. İçe aktarırken satırlar orijinal metne göre eşleşir (boşluk, noktalama, büyük/küçük
  harf ve `[1]` gibi kod yazımı farkları tolere edilir). Aynı orijinal birden çok satırda geçiyorsa dosyadaki
  sırayla ve çevirisi en çok benzeyen satıra bağlanır. 0.31.6'dan kalma `id` sütunlu dosyalar yine okunur.
- Hazır istem yeni biçime göre güncellendi.

### Eklendi
- CSV içe aktarılır aktarılmaz **değişiklikler penceresi kendiliğinden açılır**: redaksiyonda hangi satırların
  ne olarak değiştiği (sözcük sözcük) görünür, istenenler orada geri alınır (Ctrl+Z hepsini birden alır).
- Eşleşmeyen satırlar (orijinali projede bulunmayan) özetlenir.

## [0.31.6] — 2026-10-26 — CSV ile dış redaksiyon, Ctrl+Z

### Eklendi
- **CSV dışa/içe aktarma:** Çevir sayfasındaki **CSV** düğmesi, Araçlar menüsü ve sağ tık → “Seçili satırları
  CSV olarak dışa aktar”. Seçili, tabloda görünen veya tüm satırlar `id, anahtar, orijinal, ceviri` sütunlarıyla
  yazılır; istenirse her grup ayrı dosyaya (`ad_Dialogue.csv`, `ad_UI.csv` …) yazılır ve/veya 150 satırlık
  parçalara bölünür. Dosyayla birlikte bir sohbet modeline verilecek hazır istem
  pencerede gösterilir ve kaydedince panoya kopyalanır (projedeki redaksiyon talimatı da eklenir).
- İçe aktarmada birden çok parça birlikte seçilebilir. Satırlar kimlikle eşleşir; modelin eklediği ```csv çiti,
  açıklama, noktalı virgül ayraç, “Çeviri”/“translation” sütun adı ve Excel'in Türkçe kodlaması tanınır. Fazla
  etiket ve `[1]` gibi bozuk kod yazımları programca düzeltilir; kontrol kodu uymayan, orijinali farklı veya boş
  satırlar yazılmaz ve yazmadan önce özetlenir. Değişiklikler “Son İşin Değişiklikleri”nden görülüp geri alınabilir.
- **Ctrl+Z (Düzen → Geri Al):** son işlemi geri alır: elle düzenleme, onaylama, onay kaldırma, makine çevirisi /
  redaksiyon (parçaları tek işlem), bul ve değiştir, otomatik düzeltme, CSV içe aktarma, geri alma. Menüde neyin
  geri alınacağı yazar. Oturumdaki son 100 işlem tutulur.

### Kaldırıldı
- Çeviri tablosunun altındaki düzenleme paneli; tablo artık bütün alanı kullanır. Çeviri hücreye çift tıklayarak
  (veya F2) yazılır.

## [0.31.5] — 2026-10-26 — Gemma 4'ün düşünme işaretleri

### Düzeltildi
- Hugging Face'ten içe aktarılan Gemma 4 sürümlerinde Ollama "thinking" yeteneğini tanımadığı için düşünme modu
  kapatılamıyor ve model düşüncesini yanıtın içine yazabiliyordu. Gemma 4'ün kanal işaretleri
  (`<|channel>thought … <channel|>`) de atlanır; yanıttaki her JSON nesnesi denenir, düşünürken yazılmış taslak
  varsa son geçerli nesne alınır (taslaktaki süslü parantezler artık okumayı bozmaz).

## [0.31.4] — 2026-10-26 — Hugging Face'ten indirilen modellerle çalışma

### Düzeltildi
- Hugging Face'ten indirilen modeller (ör. `hf.co/unsloth/gemma-4-26B-A4B-it-GGUF:UD-Q3_K_M`) Ollama sohbetinde
  çalıştığı hâlde uygulamada "Model istenen biçimde (JSON) yanıt vermedi" hatası veriyordu. Yanıt artık daha
  hoşgörülü okunur: JSON'un önündeki düşünme bölümü (`<think>…</think>`), kod çiti (```json) ve kısa açıklamalar
  atlanır.
- Yanıt yine okunamazsa modelin ne yazdığının başı günlüğe yazılır (Yardım → Log Klasörünü Aç); yanıt uzunluk
  sınırında kesildiyse (uzun düşünme bölümü) bu ayrıca söylenir.

## [0.31.3] — 2026-10-25 — Değişiklikler penceresi, Kontrol Et listesi, onayı kaldırma

### Düzeltildi
- **Değişiklikler penceresi** ("Son İşin Değişiklikleri"): uzun satır adı (ör. bağlam ya da yol biçimli anahtar)
  "Satır" sütununu binlerce piksele genişletiyor, Orijinal/Önceki/Yeni sütunları birkaç piksele sıkışıp harf harf
  alt alta yazılıyordu. "Satır" sütunu artık en çok 240 px, tek satır, baştan kısaltılır (tamamı ipucunda);
  satır yükseklikleri sütunlar son genişliğini aldıktan sonra ölçülür.
- **Kontrol Et listesi**: açıklama, orijinal ve çeviri hücreye sığmayınca kesiliyordu; artık alt satıra kayar,
  satır yüksekliği metne göre ayarlanır (pencere boyutu değişince de). "Kod yeri" ve "Fazla etiket" açıklamaları
  kısaldı.
- **Onaylı satırlara redaksiyon**: sağ tık menüsü onaylı satırları saymadığı için "Seçili satırları talimatla
  düzelt…" (0) ve pasif kalıyordu. Artık sayılır; pencere açılınca seçilenlerin hepsi onaylıysa "Onayladığım
  satırlara da uygula" kendiliğinden işaretlenir.

### Eklendi
- Sağ tık → **Onayı kaldır**: yanlışlıkla düzenlenip onaylanmış satırları metnine dokunmadan "Makine" durumuna
  döndürür.

### Değişti
- Düzenleme panelindeki "Önceki / Sonraki" satırları kaldırıldı (bağlam tabloda zaten görünüyor; panel sadeleşti).

### Doğrulandı
- Yeni testler: değişiklikler penceresinde uzun satır adıyla metin sütunları ≥ 150 px (eski kodda "Satır" 3.629 px,
  diğerleri 100 px çıkıyordu), Kontrol Et listesinde uzun metin alt satıra kayar, onaylı satıra redaksiyon ve onayı
  kaldırma.

## [0.31.2] — 2026-10-25 — Çeviri ekranında hizalama, boşluk ve sadelik

Kullanıcının 1920×990 ekran görüntüsünde görülen düzen hataları. Testler işlevi doğruluyordu ama düzeni
ölçmüyordu; ekran görüntüleri de kısa anahtarlı küçük örnekle alınmıştı.

### Düzeltildi
- **Düzenleme paneli:** "Orijinal" ve "Çeviri" kutuları farklı yükseklikte duruyor, aralarında ve üstlerinde
  büyük boş alanlar açılıyordu. Artık tek ızgarada, aynı hizada; panel büyüyünce yalnızca kutular uzar.
- Bölme, panelin içeriği sığacak kadar yer ayırır (tabloya en az 120 px kalır); kullanıcı bölme çubuğunu
  sürüklerse onun ayarı korunur.
- **Uzun anahtarlar** (ör. `despelote_loc_monsterFile/01_Kids\Conversations\…`) "Metni kaydır" açıkken satırı dört
  satır yüksekliğe çıkarıyordu. Anahtar ve Dosya sütunları artık hep tek satır, baştan kısaltılır; tamamı ipucunda.
- Paneldeki satır bilgisi anahtarın yalnızca sonunu gösterir ("…/Nina1_01/conversation/2"); tamamı ipucunda.
- Üstteki ilerleme çubuğu "Çevrilen" yazısının yanına taşındı (sağda düğme gibi duruyordu); yüzde yazılır.
- "Görünüm" düğmesinde açılır ok yazının üstüne biniyordu.
- Uzunluk açıklaması kısaldı: "71 karakter · orijinal 51 · belirgin uzun, kutuya sığmayabilir".

### Doğrulandı
- Yeni düzen testleri (`tests/test_layout.py`, 1920×990 ve 1180×780, uzun anahtarlarla): kutular aynı hizada, panelde
  boş alan yok, panel kaydırmasız sığıyor, uzun anahtar satırı uzatmıyor, ilerleme çubuğu yazısının yanında. Eski
  kodda bu testlerin çoğu başarısız oluyordu. Testler iki yazı boyutunda (10 ve 12 punto) çalışır: Windows CI'da
  daha iri yazı tipiyle panelin yine kaydırma çubuğu çıkardığı yakalandı; panelin gereken yüksekliği her düzen
  değişikliğinde yeniden hesaplanarak düzeltildi.

## [0.31.1] — 2026-10-25 — İptal anında çalışır, takılan Ollama anlaşılır, yanlış yerdeki satır sonu kodu

Uzun bir redaksiyonda Ollama 52 dakika yanıt vermedi ve "İptal" 10 dakikadan uzun sürdü; gemma4:26b'nin
redaksiyon çıktısında (60 satır) 11 satırda satır sonu kodu sona taşınmış, 5 satıra `</div>` eklenmişti. Bu sürüm
bunları ele alır.

### Düzeltildi
- **İptal anında çalışır:** Ollama'ya istek akış (stream) olarak gönderilir; iptal istenince süren istek
  beklenmeden kesilir (eskiden yanıtın bitmesi, takılmada 10 dakika × 3 deneme beklenebiliyordu). Düğme
  "Durduruluyor…" der.
- **Takılan Ollama anlaşılır:** Ollama 5 dakika boyunca hiç parça üretmezse iş durur ve ne yapılacağı söylenir
  (Ollama'yı yeniden başlatın, `ollama ps` ile modelin ekran kartına sığdığına bakın). Uzun ama ilerleyen
  yanıtlar kesilmez. Biten partiler kayıtlı kalır, iş kaldığı yerden sürer.
- **Satır sonu kodlarından biri ortada, biri sonda kalmışsa** artık "Kod yeri" uyarısı verilir (tabloda
  camgöbeği). Program bunu oranla bölerek düzeltmez (cümleyi bozardı); "Otomatik Düzelt…" modele açık talimatla
  düzelttirir.
- **Halüsinasyon önlemi (redaksiyon ve yeniden çeviri):** satırın zaten çevirisi varken modelin sonucu şu
  belirtilerden biri varsa yazılmaz: Türkçe yerine İngilizce yazılmış ("You're crazy! Don't you think it's a bit
  risky?"), orijinalden ve eski çeviriden çok uzun (uydurma ekleme, komşu satırın metni), çok kısa (cümlenin yarısı
  başka satıra kaçmış), aynı sözcük çifti tekrar tekrar ("türlü türlü … türlü türlü"). Model bir kez sorunu
  söylenerek yeniden istenir; yine olmazsa eski çeviri korunur ("denetimden geçmedi" örneklerinde nedeni görünür).
  Örnekler gemma4:12b'nin gerçek redaksiyon çıktılarından; eşikler doğal kısaltma ve uzatmaları reddetmeyecek
  kadar gevşek (`core/translate/guards.py`).
- **Redaksiyon ve yeniden çeviride**, iyi bir çevirinin yerine satır sonu kodu sona taşınmış bir sonuç
  yazılmaz: model bir kez açık talimatla yeniden istenir, yine olmazsa eski çeviri korunur ("denetimden geçmedi"
  sayısında görünür).

## [0.31.0] — 2026-10-25 — Çeviri editörü, programla düzeltme, kurtarma kopyası, CI ve taşınabilir paket

Programın baştan sona denetimi yapıldı; bulgular ve yol haritası `docs/DENETIM.md`'de. Bu sürüm yol haritasının
A–E aşamalarının tamamıdır. Çeviri ekranında Subtitle Workshop ve Aegisub'daki "ızgara + düzenleme kutusu +
klavyeyle ilerleme" akışı örnek alındı.

### Eklendi — Kontrol Et (B)
- **Programla Düzelt:** model kullanmadan, programın kesin yapabildiği düzeltmeler: baştaki/sondaki boşluk;
  satır sonu sayısı özgünle tutmuyorsa çeviri sözcük sınırlarından dengeli satırlara yeniden bölünür; aynı türden
  kontrol kodlarının (ör. iki "Satır sonu") karışmış sırası düzeltilir; çeviride İngilizce kalmış sözlük terimi
  karşılığıyla değiştirilir ("Sheriff'e" → "Şerif'e", ek korunur). Anlam gerektiren sorunlar olduğu gibi kalır ve
  kaç satır olduğu söylenir.
- **Otomatik Düzelt** önce aynı program düzeltmelerini yapar, satırı yeniden denetler; modele yalnızca hâlâ kalan
  sorunlar gider (daha az satır, daha hızlı).
- Bulgu listesinde **Orijinal** ve **Çeviri** sütunları; çift tıklama (veya Enter) **tam o satırı** çeviri
  ekranında açar ve düzenleme kutusuna odaklanır (filtre gizliyorsa temizlenir; eskiden anahtarla arama yapılıyordu
  ve aynı anahtar başka dosyada da olabiliyordu).
- Kontrol Et iki sekmede: **Satır denetimi** ve **Font ve harfler**.

### Eklendi — Model çıktısı temizliği ve sorun renkleri
- **Temizlik katmanı:** her model sonucu yazılmadan önce özgünde olmayan HTML/XML etiketleri (`<div>`, `<p>`,
  `<br>` …) ve `&nbsp;` gibi varlıklar, özgünde olmayan veya fazladan tekrarlanan `⟦n⟧` kodları atılır; özgünde
  cümlenin ortasında duran satır sonu kodları çeviride en sona yığılmışsa metin sözcük sınırlarından özgündeki
  oranlarla bölünüp kodlar araya yerleştirilir. İş bitince kaç satırın temizlendiği söylenir.
- Ollama istemine "etiket ekleme, satır sonu kodunu sona taşıma" kuralı eklendi.
- Kontrol Et'e iki yeni bulgu: **Fazla etiket** (hata) ve **Kod yeri** (uyarı); ikisi de "Programla Düzelt" ile
  düzelir. Düzenleme panelinde aynı sorunlar yazarken gösterilir ve **Temizle** düğmesi çıkar.
- **Sorunları renkle göster:** çeviri tablosunda çeviri metni sorun türüne göre renklenir (kod hatası kırmızı,
  fazla etiket mor, uzunluk sınırı turuncu, satır sonu/kod yeri camgöbeği, olası taşma sarı-kahve); ayrıntı
  satırın ipucunda. Durum süzgecine **Sorunlu (renkli) satırlar** eklendi. Görünüm menüsünden kapatılabilir.

### Eklendi — Proje güvenliği (C)
- **Kurtarma kopyası:** henüz kaydedilmemiş yeni projede değişiklik varsa her dakika bir kopya
  `%LOCALAPPDATA%\NXCeviri\kurtarma`'ya yazılır. Program çöker veya elektrik kesilirse sonraki açılışta
  "Kaydedilmemiş proje bulundu" sorusu gelir: Kurtar / Sil / Sonra. Proje kaydedilince veya bilerek kapatılınca
  kopya silinir. Aynı anda açık iki pencere birbirinin kopyasını önermez.
- **Dosya → Son Projeler** (son 8 proje; diskte olmayanlar gösterilmez; listeyi temizleme).

### Eklendi — Mimari ve paket (D, E)
- **Testler GitHub Actions'ta Windows'ta** çalışır (ruff, mypy, pytest) — her pull request'te ve sürüm
  yayımlanmadan önce; testler geçmezse release oluşmaz.
- **Taşınabilir Windows paketi** (PyInstaller, `packaging/NXCeviri.spec`): her release'e
  `NXCeviri-<sürüm>-windows.zip` eklenir; açıp `NXCeviri.exe`'yi çalıştırmak yeterli, Python gerekmez. Paket
  sürümünde "Güncellemeleri Denetle" sürüm sayfasını açar; açılışta yeni sürüm varsa "— İndir" düğmesi çıkar.
- `ARCHITECTURE.md`: ayarların nerede durduğu tablosu (QSettings / proje / keyring) ve 0.31.0 kararları.

### Değişti — mimari
- `main_window.py` bölünmeye başladı: makine işi iletileri `gui/jobs.py`'ye, son projeler `gui/recent.py`'ye
  taşındı; kurtarma `gui/recovery.py`'de. Davranış değişmedi; kalan bölme TECH_DEBT 69'da.

### Eklendi — Çeviri editörü (A)
- **Satır düzenleme paneli** (çeviri tablosunun altında, bölme çubuğuyla boyutlanır; Görünüm menüsünden açılıp
  kapanır): özgün metin, sahnede önceki ve sonraki satır (çevirileriyle), çeviri kutusu, kontrol kodu düğmeleri
  (tıklayınca imlecin yerine eklenir, anlamı ipucunda), yazarken anlık denetim (eksik/fazla/sırası bozuk kod,
  toplam ve satır satır uzunluk, sınır ve özgüne göre uzunluk uyarısı).
- **Klavyeyle çalışma:** Ctrl+Enter kaydet, onayla ve sonraki satır · Alt+↑/↓ önceki/sonraki satır (değişiklik
  satırdan çıkarken kaydedilir) · F3 sonraki bakılacak (onaylanmamış) satır · Esc kaydedilmemiş değişikliği geri al
  · Ctrl+F ara · Ctrl+H bul ve değiştir. Komutlar yeni **Düzen** menüsünde de var.
- **Onayla:** makine çevirisini değiştirmeden onaylama; sağ tık menüsünden seçili satırlar topluca onaylanır.
- **Bul ve değiştir** (Ctrl+H): yalnızca çevirilerde; büyük/küçük harf, tam sözcük, yalnızca görünen satırlar;
  yazdıkça kaç satırın değişeceği görünür; kontrol kodunu bozacak değişiklik atlanır; onaylı satırlar onaylı kalır;
  değişiklik geçmişe yazılır, "Son İşin Değişiklikleri"nden geri alınır.
- `docs/DENETIM.md`: bulgular (önem dereceli) ve yol haritası.

### Değişti
- Bilgi bandı kapatılabilir; gereksiz açıklama satırı kaldırıldı; tablo/panel alanı büyüdü.
- Görünüm seçenekleri (düzenleme paneli, önceki çeviri sütunu, metni kaydır) tek "Görünüm" menü düğmesinde.
- Tarama özetinde yalnızca bulunan dosya türleri gösterilir (onlarca "0" kutusu kalktı).

### Düzeltildi
- En küçük pencere boyutunda (820×560) çeviri ekranındaki düğmeler tablonun üstüne biniyordu.
- Dar pencerede düzenleme panelinin kaydet düğmeleri kesiliyordu; artık ikinci satıra iner. Tablonun altındaki
  toplu işlem düğmelerinin adları kısaldı ("Seçilenlere Orijinal", "Seçilenleri Temizle").
- Çevirideki `<div>` gibi metinler ipuçlarında ve bilgi bantlarında biçim olarak yorumlanıp görünmez oluyordu;
  artık yazı olarak görünür.
- Güncelleyici, `pyproject.toml` baytları değişti diye (yalnızca sürüm numarası veya Windows satır sonları farklı
  olsa bile) her güncellemede paketleri yeniden kuruyordu; artık yalnızca bağımlılık listesi değişince kurar
  (Windows CI'da yakalandı).
- Sayfa kapandıktan sonra canlı izleme vurgusunun zamanlayıcısı silinmiş tabloya erişmeye çalışabiliyordu.

### Doğrulandı
- 646 testin tamamı Windows'ta (GitHub Actions) geçiyor (32 yeni); ruff ve mypy temiz. Çeviri ve Kontrol Et ekranları normal ve en küçük boyutta,
  açık ve koyu temada ekran görüntüsüyle denetlendi. Taşınabilir paket Linux'ta derlenip açıldı; Windows paketi
  release iş akışında derlenir (gerçek Windows'ta deneme TECH_DEBT 70).

## [0.30.0] — 2026-10-25 — Tabloda önceki çeviri ve redaksiyon işareti, canlı izleme, değişiklikleri dışa aktarma

### Eklendi
- **Önceki çeviri** sütunu (çeviri tablosunda “Önceki çeviri” kutusuyla açılır/kapanır): son yeniden çeviri, düzeltme
  veya otomatik düzeltmede değişen satırların önceki hâli, Çeviri sütununun yanında; çıkarılan sözcükler kırmızı ve
  üstü çizili. Durum süzgecinde **“Son işte değişenler”** seçeneği yalnızca bu satırları gösterir.
- **Durum sütununda işaret:** satırın son değişikliği bir işle yapıldıysa “Makine · redaksiyon”, “· otomatik
  düzeltme”, “· yeniden çeviri” yazar. Elle düzenleyince işaret kalkar.
- **Canlı izleme:** makine işi sürerken her parti tabloya yazıldığı anda o satırlar kısa süre sarı vurgulanır;
  ilerleme şeridindeki “Canlı izle” açıksa tablo yazılan satırlara kayar (tercih hatırlanır).
- Değişiklikler penceresinde **Dışa Aktar…**: Excel'de doğrudan açılan CSV (noktalı virgül ayraçlı, UTF-8) veya
  tarayıcıda açılan renkli karşılaştırma sayfası (HTML).

### Değişti
- Durum sütunu varsayılan genişliği arttı (işaretler kesilmeden okunsun); kayıtlı sütun genişlikleri korunur.

### Doğrulandı
- 614 test geçiyor (3 yeni); ruff ve mypy temiz. Tablo açık ve koyu temada ekran görüntüsüyle denetlendi.

## [0.29.0] — 2026-10-25 — Değişiklikleri görme ve geri alma, çeviri geçmişi, hazır talimatlar

### Eklendi
- **Çeviri geçmişi:** bir satırın çevirisi her değiştiğinde önceki metni, durumu ve açıklaması projeye kaydedilir
  (makine işleri, otomatik düzeltme, elle düzenleme, hazır çeviri aktarma; proje şeması 5). Eski projeler açılırken
  kendiliğinden güncellenir (öncesinde `.nxproj.bak` yedeği alınır).
- **Son İşin Değişiklikleri** penceresi: yeniden çeviri, talimatla düzeltme veya otomatik düzeltme bitince
  kendiliğinden açılır (çeviri işinde 3. Çevir sayfasındaki düğmeyle). Orijinal / Önceki / Yeni yan yana; çıkarılan
  sözcükler kırmızı ve üstü çizili, eklenenler yeşil. İşaretlenen satırlar önceki çevirisine ve durumuna döner.
- **Çeviri geçmişi…** (satıra sağ tık): satırın bütün değişiklikleri, hangi işle ve ne zaman yapıldığı; seçilen
  değişiklikten önceki hâle dönülür. Geri alma da geçmişe yazılır, yani geri alma da geri alınabilir.
- Talimatla düzeltmede **hazır talimatlar**: “Doğal konuşma dili (makine çevirisi izlerini temizle)”, “Kısalt”,
  “Hitap tutarlılığı (sen / siz)”. Seçilen talimat kutuya yazılır, sonra düzenlenebilir.

### Doğrulandı
- 611 test geçiyor (8 yeni: geçmiş, işe göre değişiklikler, geri alma, şema göçü, sözcük farkı, pencere akışı);
  ruff ve mypy temiz. Pencere açık/koyu temada ekran görüntüsüyle denetlendi.

## [0.28.1] — 2026-10-25 — Kontrol kodları: modele anlamı söylenir, sık bozulmalar onarılır, reddedilen öneri gösterilir

Despelote'de altyazı satırı ("We could make⟦1⟧the goal out of sticks, or...⟦2⟧out of...") yeniden çevrilirken
model satır sonu kodlarını koruyamadı; yazılım öneriyi doğru biçimde reddetti, ama ne olduğunu göstermedi.

### Eklendi
- Modele her kontrol kodunun anlamı gider (`"codes": {"⟦1⟧": "Satır sonu"}`); istem satır sonunun Türkçe cümlede
  doğal bir kırılma yerine konmasını söyler.
- Sık bozulmalar denetimden önce onarılır: `[1]`, `【1】`, `{1}`, `⟦ 1 ⟧` → `⟦1⟧`; satır sonu kodu yerine yazılmış
  gerçek satır sonu veya `\n` yazısı (sayısı eksik kod sayısıyla tutuyorsa, sırayla) koda çevrilir. Onarılan
  sonuç yine aynı denetimden geçer.
- Yeniden istekte modele beklenen kod dizisi açıkça yazılır ("⟦1⟧ ⟦2⟧ bu sırayla ve birer kez").
- Öneri reddedilince mesajda satırın adı, nedeni ve modelin önerisi görünür (en çok 3 örnek); öneri elle
  düzeltilip kullanılabilir.

### Doğrulandı
- 4 yeni test; ruff ve mypy temiz. Gerçek modelde denenmedi.

## [0.28.0] — 2026-10-25 — Bağlamlı çeviri, yeniden çeviri, talimatla düzeltme, otomatik düzeltme, GitHub'dan güncelleme

Makine çevirileri "it, that, they, and" gibi her sözcüğü birebir çevirdiği için makine çevirisi gibi duruyordu; kısa
cevaplar ("Not me.") neye cevap olduğu bilinmeden çevriliyordu. Bir satırı yeniden çevirmek için çeviriyi silmek bile
yetmiyordu: çeviri belleği aynı çeviriyi geri getiriyordu.

### Eklendi
- **Bağlamlı çeviri:** her parti, sahnede hemen önceki 8 ve sonraki 3 satırla (varsa çevirileriyle) birlikte
  gönderilir. Partiler yalnızca aynı dosyada art arda gelen satırlardan kurulur. Önceki partide çevrilen satırlar
  sonraki partinin bağlamında yeni çevirileriyle görünür.
- **Türkçe üslup kuralları** (hedef Türkçe olduğunda istemde): özne zamirlerini düşür; "it/this/that/they"i her
  yerde bu/şu/o/onlar diye çevirme; cümleye "Ve" ile başlama; "Yes/No/Well"i duruma göre karşıla; deyimleri ve
  konuşma dilini kullan; kısa cevabı önceki satıra göre çevir ("Have a drink." → "Not me." → "Ben içmem.").
- **Yeniden çevir:** seçili satırlar, seçili satırların grubu, tabloda filtrelenen satırlar veya tüm proje,
  çeviriler silinmeden yeniden çevrilir. Çeviri belleği atlanır, her satır kendi sahnesinde ayrı çevrilir. Sonucu
  bozuk gelen satırın eski çevirisi korunur.
- **Talimatla düzelt (redaksiyon):** mevcut çeviriler, yazdığınız talimata göre (ör. "zamirleri at, doğal konuş")
  düzeltilir. Model özgün metni, mevcut çeviriyi ve sahnenin bağlamını birlikte görür; zaten iyi olanı aynen bırakır.
  Son talimat projede hatırlanır. Yalnızca Ollama ile (DeepL talimat izleyemez; pencere bunu önler).
- Makine Çevirisi penceresinde iş türü (Çevir / Yeniden çevir / Talimatla düzelt), kapsam ve “Onayladığım satırlara
  da uygula” seçeneği; her kapsamın satır sayısı. Çeviri tablosunun sağ tık menüsünde üç iş için ayrı komut.
- **Otomatik düzelt** (4. Kontrol Et → Satır denetimi): baştaki/sondaki boşluk ve özgünde olmayan satır sonları
  hemen düzeltilir; kontrol kodu, uzunluk sınırı, satır sonu ve sözlük sorunları sorunun açıklamasıyla Ollama'ya
  düzelttirilir. Dönen sonuç aynı denetimlerden yeniden geçer; sorun sürüyorsa eski çeviri korunur. Olası taşma,
  eksik harf ve kod adı uyarıları otomatik düzeltilmez; onaylı satırlara dokunulmaz.
- **GitHub'dan güncelleme** (Yardım → Güncellemeleri Denetle…): yalnızca yayımlanmış **sürümlere (GitHub Releases,
  `v0.28.0` gibi etiketler)** bakılır, master'daki ara değişiklikler kullanıcıya gelmez. Sürüm notları, tek tıkla
  güncelleme ve yeniden başlatma. Uygulama klasörü bir git deposuysa git ile (kayıtlı GitHub oturumu, ayrı anahtar
  gerekmez, yerel değişiklik varsa durur), değilse zip arşiviyle (salt okunur erişim anahtarı, yedekli ve geri
  alınabilir yazım). Güncelleme yeniden başlarken, dosyalar henüz açılmadan uygulanır; paketler değiştiyse başlatıcı
  yenilerini kurar. Açılışta arka planda denetlenir; yeni sürüm varsa durum çubuğunda düğme çıkar.

- **Otomatik sürüm yayımlama** (`.github/workflows/release.yml`): master'a sürüm numarası değişmiş bir commit
  gelince GitHub Actions `v<sürüm>` etiketini ve release'i CHANGELOG'daki bölümle oluşturur.

### Değişti
- Makine çevirisi yer tutucusu bozuk dönen satırı yeniden isterken sorunu açıkça yazar (`fix`).
- Dönen çevirilerin baştaki/sondaki boşlukları özgünle eşlenir.
- "Çevir" işi artık hatalı satırları da kapsar; Ollama istemindeki sıcaklık 0,2 → 0,3.
- Çeviri belleğinden dolan ama yeni çeviri gelmeyen işte mesaj, “Seçili satırları yeniden çevir”i önerir.

### Düzeltildi
- Testlerdeki üç eski mypy hatası (tip açıklamaları).

### Doğrulandı
- 601 test geçiyor (54 yeni: bağlamlı partiler, yeniden çeviri, redaksiyon, otomatik düzeltme, release, zip ve git
  güncellemesi, arayüz akışları); ruff ve mypy temiz. Linux test ortamında 8 eski test, ortama özgü nedenlerle
  (Windows yazı tipleri, keyring, Windows yol hatası) geçmiyor; bu sürümle ilgisi yok.
- Pencereler açık ve koyu temada ekran görüntüsüyle denetlendi.
- **Denenmedi:** gerçek bir Ollama modeliyle çeviri kalitesi (gemma4 ile denemeniz gerekiyor) ve Windows'ta
  güncelleme sonrası yeniden başlatma.

## [0.27.0] — 2026-10-24 — Despelote: ı İ ş Ş ğ Ğ harfleri oyunun kendi fontuyla; Türkçe yalnızca kaynak dil yuvasına

0.26.0 modu cihazda Türkçe gösterdi. İki sorun çıktı: bazı yazılarda `ı ş ğ` harfleri başka bir yazı tipiyle
görünüyordu ve oyundaki tüm dil seçenekleri Türkçe olmuştu.

### Düzeltildi
- **Harfler farklı yazı tipiyle görünüyordu:** Despelote'nin fontları (Despelote-Regular, DespeloteFill3,
  DespeloteOutline3 …) `ı İ ş Ş ğ Ğ` harflerini içermiyor; oyun eksik harfi yedek fonta (LiberationSans) düşürüyordu.
  Fontlar dinamik TextMeshPro olduğu için çalışma anında gömülü TTF/OTF dosyasından harf üretir: bu dosyalara harfler
  eklendi (aşağıda). Font taraması ise yalnızca adında "font" geçen paketlere baktığı için "okunabilen font bulunamadı"
  diyordu; artık boyutu makul tüm Unity dosyalarını açar (Despelote: ~20 sn).
- **Tüm diller Türkçe olmuştu:** 0.25.0'daki "çeviriyi 6 dil yuvasının hepsine yaz" davranışı yanlış bir varsayıma
  dayanıyordu (asıl neden `Locoliser` önbelleğiydi). Kaldırıldı: Türkçe yalnızca kaynak dil yuvasına (İngilizce)
  yazılır, diğer diller özgün kalır.
- Birden çok serileştirilmiş dosyası olan Addressables paketlerinde (ör. Despelote ana sahne paketi) path_id'ler
  dosyalar arasında çakışıyordu; font yaması ve taraması nesneleri yanlış dosyadan okuyabiliyordu
  (`LiberationSans SDF` atlası "okunamadı" hatası buradandı). Artık (dosya, path_id) ile eşleniyor.

### Eklendi
- `core/fontpatch/ttf.py`: TrueType (glyf) ve CFF fontlarına `ı İ ş Ş ğ Ğ` ekler. Harfler fontun kendi şekillerinden
  türetilir: `ı` = `i`'nin noktasız hâli (nokta gövdeye kaynamışsa `I` x-yüksekliğine ölçeklenir), `İ` = `I` + fontun
  nokta şekli, `ş Ş` = `s S` + fontun virgül şekli, `ğ Ğ` = `g G` + fontun nokta ölçüsüne göre çizilmiş kuşak.
  Yeni glifler sona eklenir (mevcut glif numaraları değişmez). Çince/Japonca/Korece fontlar atlanır.
- `fontpatch/unity.py`: `Font` nesnelerinin içindeki fontlar yamalanır; yazılan paket yeniden okunup doğrulanır.
- Dışa aktarma `font_files`: yamalanacak dosyalar font taramasından gelir (proje ayarı `font_files`); adında "font"
  geçmeyen paketler de yamalanır.
- 23 yeni test (elle üretilmiş glyf ve CFF fontlarla); Locoliser/altyazı testleri yeni davranışa güncellendi.

### Doğrulandı
- Gerçek Despelote'de üretilen modda: 3 Font nesnesi (ana sahne paketi) + 2 (`resources.assets`) + Mario-Kart-DS
  yamalandı, ana sahne paketindeki diğer 42.894 nesne bayt bayt aynı; Locoliser'da yalnızca İngilizce sütunu değişti
  (6.004 diyalog, 154 menü satırı), es/fr/de/br/chs özgün. Pillow ile çizilen örneklerde harfler fontun üslubuna uyuyor.
  555 test, ruff ve mypy temiz. Cihazda denenmedi.

### Bilinen sınırlar
- CID anahtarlı CFF fontları (Çince olmayanlar) yamalanmaz (TECH_DEBT 66).
- Yalnızca anahatlı (Outline) fontta `ğ Ğ` işareti dolu çizilir; okunaklı ama özgün üsluptan biraz farklı.

## [0.26.0] — 2026-10-24 — Despelote: Türkçe, oyunun gerçekten okuduğu `Locoliser` önbelleğine yazılır

0.25.0 modu cihazda yine her dilde özgün metni gösterdi. Nedeni bulundu: oyun metinleri TSV TextAsset'lerinden değil,
`resources.assets` içindeki **`Locoliser` MonoBehaviour'undan** okuyor. Bu nesne, TSV'lerin editörde ayrıştırılıp oyuna
gömülmüş kopyası (1,8 MB, tip ağacı silinmiş). Tüm oyun dosyaları, sıkıştırılmış Unity paketlerinin içi dahil tarandı;
diyalog ve menü metinlerinin TSV'ler dışındaki tek kopyası bu nesne.

### Eklendi
- `core/formats/unity/locoliser.py`: `Locoliser` yapısının ham bayt okuyucu/yazıcısı (1.013 anahtar, 6.042 altyazı ×
  6 dil, 164 menü satırı × 6 dil; zaman bilgileri ve bilinmeyen alanlar aynen korunur). Yapı kesin doğrulanır;
  gerçek dosyadaki 103 MonoBehaviour'dan yalnızca doğru nesne tanınıyor, değişiklik yokken bayt bayt aynı yazılıyor.
- Dışa aktarmada TSV satırlarına yazılan Türkçe, önbellekteki karşılığının **6 dil yuvasının hepsine** taşınır:
  diyalog satırları anahtar + altyazı sırasıyla eşlenir (önbellekte metin satırlara bölünmüş olabilir, 6.042/6.042
  eşleşiyor); menü satırları sırayla ve yalnızca özgün metin TSV'dekiyle aynıysa yazılır. Projeye yeni satır eklenmez,
  var olan çeviriler aynen kullanılır.
- 7 yeni test (elle üretilmiş `Locoliser` ve tip ağacı olmayan dosyada TextAsset).

### Düzeltildi
- 0.24.0'daki "oyunun altyazıyı SRT'den mi TSV'den mi okuduğu bilinmiyor" belirsizliği giderildi: ikisi de değil.

### Doğrulandı
- Kullanıcının projesinden üretilen modda `Locoliser`: 6.042 altyazının 6.004'ü, 164 menü satırının 154'ü Türkçe
  (değişmeyenler çevirisi özgünüyle aynı satırlar). 532 test, ruff ve mypy temiz. Cihazda denenmedi.

## [0.25.0] — 2026-10-24 — Despelote: Türkçe tüm dil yuvalarına yazılır; çeviri tablosunda panoya kopyalama

Cihazda Despelote'de çeviriler görünmüyordu. Çıktı dosyası doğruydu (İngilizce sütunundaki ve altyazılardaki
15.826 satır Türkçe), ama oyunun Türkçe dil yuvası yok: konsolun sistem dili Türkçe olunca oyun desteklemediği
bu dil yerine başka bir dile (büyük olasılıkla İspanyolca) düşüyor ve Türkçe yazılan İngilizce sütununa hiç bakmıyor.

### Değişti
- **TSV tablolarında çeviri satırın tüm dil sütunlarına yazılır** (es, en, fr, de, br, chs): oyun hangi dili seçerse
  seçsin Türkçe görünür. Aynı ada ve birebir aynı zaman satırlarına sahip altyazının diğer dildeki kopyası
  (ör. `Nina1[en]` → `Nina1[es]`) da aynı çeviriyi alır; eşleşme belirsizse (aynı dilde birden çok aday) dokunulmaz.
  Gerçek oyunda 1.411 İngilizce altyazının 1.369'u eşleşiyor. Açıkça çeviri verilen hücre aynalamayı ezer.
- Çeviri tablosunda **panoya kopyalama**: satırlara sağ tık → Panoya kopyala → "Orijinal ve çeviri" / "Yalnızca
  orijinal" / "Yalnızca çeviri"; tablo odaktayken **Ctrl+C** orijinal ve çeviriyi birlikte kopyalar (tablodaki sırayla).

### Doğrulandı
- Kullanıcının projesinden yeniden üretilen çıktıda altı TSV dil sütununun hepsinde 6.285 satır Türkçe;
  İspanyolca altyazıların 8.810 bloğu Türkçe. 522 test, ruff ve mypy temiz.
- Cihazda denenmedi (TECH_DEBT 65).

## [0.24.0] — 2026-10-24 — Unity: TextAsset altyazı (SRT) ve TSV dil tabloları (Despelote)

**Despelote'de "metinler ayıklanmıyor" sorunu giderildi.** Oyun metinlerini Unity Localization ya da I2 ile
değil, `Data/resources.assets` içindeki düz metin varlıklarında (TextAsset) tutuyor; eklenti bunları tanımıyordu,
tarama "Unity" diyor ama hiçbir satır çıkmıyordu. Gerçek oyunda artık 15.978 İngilizce satır çıkıyor.

### Eklendi
- **SRT altyazı desteği:** `Nina1[en]`, `[es]shop convo_x` gibi adlı TextAsset'ler; dil, adındaki `[xx]` etiketinden
  anlaşılır. Her altyazı bloğu ayrı satırdır; zaman damgaları, numaralar, BOM ve satır sonları değişmeden kalır
  (1-3 haneli milisaniye ve blok içindeki boş satır dahil).
- **Dil sütunlu TSV desteği:** `despelote_loc_monsterFile` (6.042 diyalog satırı) ve `despelote_loc_UI` (menü).
  Başlıkta `es`, `en`, `fr`… ya da `[es]`, `[en]` sütunları aranır; seçilen kaynak dilin (yoksa İngilizce)
  sütunu aktarılır, Türkçe aynı sütuna yazılır. Hücre içindeki düz `\n` yazısı ve `{}` değişkenleri
  ⟦n⟧ yer tutucusu olur.
- Yazılan dosya yeniden okunup tüm metinler doğrulanır; çeviri TSV'de sekme/satır sonu, altyazıda yeni boş satır
  eklerse (biçimi bozacağı için) yazılmaz ve açık bir hata verilir.
- `core/formats/unity/loctext.py` (ayrıştırıcı), `markup.tokenize(literals=…)`, 13 yeni test.

### Düzeltildi
- Oyun verisindeki bozuk UTF-8 baytları (6 altyazıda kesilmiş `’`) metinleri projeye yazarken tüm aktarmayı
  çökertiyordu (`surrogates not allowed`). Bu satırlar artık `�` ile gösterilir; çevrilmedikçe dosyadaki
  orijinal baytlara dokunulmaz. Gerçek oyunda projeye 15.978 satır eklendiği doğrulandı.

### Doğrulandı (gerçek Despelote `resources.assets`, 47,5 MB)
- Çıkarma 1,2 sn; değişiklik yokken geri yazım bayt bayt aynı; seçili satırlar Türkçe harflerle (ğüşıöçİ)
  yazılıp yeniden okununca birebir geliyor; diğer diller ve diğer TextAsset'ler değişmiyor.

### Bilinen sınırlar
- Mod cihazda denenmedi; oyunun altyazıyı SRT'den mi TSV'den mi okuduğu bilinmiyor, ikisi de yazılır (TECH_DEBT 65).
- `credits[es]`, resim/sahne içindeki yazılar ve ses (FMOD) çevrilmez.

## [0.23.0] — 2026-10-24 — Metal Gear Solid Master Collection: metin çevirisi (M2)

**MGS1 (Switch) menü, onay penceresi ve Master Book metinleri artık tarama → çeviri tablosu → dışa aktarma
akışında.** Dışa aktarma, cihazda doğrulanan "dizinden çıkar + gevşek dosya" yöntemini kullanır (8 GB'lık
`alldata.bin` değişmez). Aracın ürettiği modun cihaz testi bekleniyor.

### Eklendi
- **M2 PSB metin eklentisi** (`core/formats/m2text`): dil tablolarındaki (`eng` yuvası: menü, onay, rehber,
  kayıt metinleri) ve Master Book sayfalarındaki (`087/config/*_EN`) metinleri çıkarır. Satırlar dizge
  başına tekilleştirilir (aynı yazı tek satır, bağlamda kullanıldığı anahtarlar yazılır); çeviri dizgeyi yerinde
  değiştirir, dosyanın geri kalanı bayt bayt aynı kalır. Kimlik olarak da kullanılan dizgeler çıkarılmaz.
  Kontrol kodları (`<br>`, `<size=…>`, `#{color,…}`, `%s`, `{…}`) ⟦n⟧ yer tutucusu olur.
- **Tarama:** M2 arşivi (mdf kodlu `.psb.m` dizini) tanınır; anahtar oyunun kendi kodundan bulunur,
  yalnızca çevrilebilir metin içeren üyeler listelenir (gerçek dökümde 22 dosya, 3.353 satır, tarama ~6 sn).
- **Dışa aktarma:** değişen üyeler dizinden çıkarılmış `alldata.psb.m` ile birlikte, kendileri gevşek dosya olarak
  yazılır; her dosya yazmadan önce yeniden okunup doğrulanır.
- `PSB` okuyucuda dizge başvuruları (`Psb.string_refs`); oyun kodu erişimi `ContentTree.code`.
- 17 yeni test.

### Doğrulandı
- Menü yazı tiplerinin (21 PSB bitmap fontu) hepsinde `ç ğ ı İ ö ş ü Ç Ğ Ö Ş Ü` glifleri var: harf dönüştürmeye
  gerek yok.
- Gerçek dökümle uçtan uca: çıkarma → çeviri → `export_mod` → yeni dizin özgün `.bin` ile açılıyor, 4.943 girdi aynı konumda.

### Bilinen sınırlar
- Ana menü etiketleri ("Game Selection", "Master Book"…) metin değil, büyük olasılıkla resim; çevrilmez (TECH_DEBT).
- Master Book'ta sayfa düzeni etiketlerle sabitlenmiş (`<voffset>`, `<width>`): uzun Türkçe metin taşabilir.

## [0.22.0] — 2026-10-23 — Devil May Cry: yazma

**Cihazda doğrulandı:** açılış sahnesi ve sistem mesajları Türkçe göründü (46 satırlık deneme modu).

### Eklendi
- **Devil May Cry'ye çeviri yazma** (`.fsd` ve `etc_e/*.msg`): İngilizce tablo dizindeki 23. bölümde sabit olduğundan
  bulunuyor; tablo büyüyebilir, sonraki fsd bölümleri kaydırılıp dizin güncelleniyor. Değişiklik yapmadan yazmak
  75 gerçek dosyada birebir aynı sonucu veriyor. Ayrıntı: `docs/formats/dmc1.md`.
- **Oyun fontunda olmayan harflerin otomatik dönüştürülmesi:** dışa aktarırken eklenti `unsupported_letters` bildirirse
  o dosyalarda yalnızca bu harfler dönüşür (DMC1: ğ ş ı İ Ç; ç ö ü Ö Ü korunur) ve rapora uyarı düşer.
- 13 yeni test.

## [0.21.0] — 2026-10-23 — M2 arşivleri: dizin düzenleme (mod yazımı araştırması)

**Cihazda henüz denenmedi; arayüzde yok.**

### Eklendi
- `psb.replace_root`: kök değer ağacını yeniden kodlar; ad ve dizge tabloları aynen kalır, sonraki bölümler
  hizalamayı koruyarak kayar. Gerçek `alldata`/`dlc_usa` dizinlerinde değişmeden yeniden kodlama orijinal
  baytları birebir veriyor.
- `M2Archive.index_without`: verilen üyelerin girdisi çıkarılmış yeni `.psb.m` dizini.
- MGS1 için iki deneme modu (`games/MGS Master Collection [NSZ]/deneme_modlari/`): 8 GB'lık `alldata.bin`'e
  dokunmadan, değişen menü dosyasını gevşek dosya olarak vermeyi dener. Ayrıntı ve sonuç yorumu:
  `docs/formats/m2.md` "Mod yazımı".
- 9 yeni test.

### Değişti
- PSB okuyucu tamsayı dizilerini `IntArray` olarak döndürür (tamsayı listesinden ayrı); `[ofset, boy]`
  girdileri liste olarak kalır.
- Test PSB üreticisi kök ağacı uygulamanın kodlayıcısıyla üretir (tek kural seti).

## [0.20.0] — 2026-10-23 — Devil May Cry: güvenli okuma

**Yalnızca okuma.** Oyun dosyalarına yazılmaz; DMC için "Dışa Aktar" açık bir hata verir (TECH_DEBT 61).

### Eklendi
- **Devil May Cry (Switch) okuma eklentisi:** `fsd` sahne dosyalarındaki İngilizce diyalog tabloları ve
  `etc_e/*.msg` sistem mesajları çeviri tablosuna aktarılır (gerçek oyunda 410 satır). Oyunun kendi
  tek baytlık harf tablosu çözüldü; kontrol kodları (boşluk/satır sonu hariç) ⟦n⟧ yer tutucusu olur,
  tanınmayan her bayt kayıpsız korunur. Kodlama gidiş-dönüş testi gerçek verinin tüm dizgilerinde
  bozulmadan geçti. Ayrıntı: `docs/formats/dmc1.md`.
- Dil kümesinden İngilizce tablo, içeriğe bakılarak seçilir; rastgele ikili veriler gürültü oranıyla elenir.
- 11 yeni test.

## [0.19.0] — 2026-10-23 — M2 arşivleri (Metal Gear Solid Master Collection): okuma

Çekirdek katman; arayüzde henüz görünmez (tarama ve çeviri tablosu bağlantısı sonraki adım).

### Eklendi
- **mdf açma/kodlama** (`core/archives/m2.py`): zlib + 64 baytlık XOR akışı (MD5 → MT19937). Değişmeyen
  dosya orijinal baytlarıyla kalır.
- **Oyun anahtarı kullanıcının kendi dökümünden bulunur:** uygulama anahtar içermez; oyunun ExeFS `main`
  kodundaki dizgeler denenir, gerçek bir `.psb.m`'yi açan seçilir. Anahtar yalnızca bellekte tutulur.
- **NSO açma** (`core/container/nso.py`): ExeFS kodunu yalnızca dizge aramak için okur.
- **PSB okuyucu (sürüm 2–4)** ve dizge tablosunu yerinde yeniden yazma (`core/archives/psb.py`): kök ağaç
  bayt bayt korunur, sonraki bölümler hizalamayı koruyarak kayar, sağlama toplamı yeniden hesaplanır.
- **M2 arşivi** (`.psb.m` dizini + `.bin` verisi): üyeleri listeleme, büyük üyeleri (disk kalıpları) dilim
  olarak açma, `.m` üyeleri çözerek okuma.
- Gerçek MGS1 Switch dökümüyle doğrulandı: anahtar bulundu; 4.945 + 3 üye; 4.903 mdf üyesinin tamamı
  açıldı ve değişmeden geri yazımda aynı baytlar çıktı; 620 PSB okundu, 578'inde metin değiştirilip yeniden
  okundu. Ayrıntı: `docs/formats/m2.md`.
- 19 yeni test (elle üretilmiş PSB/mdf/NSO; gerçek oyun verisi yok).

## [0.18.0] — 2026-10-23 — Büyük harfle gösterilen metinler (i → İ)

Oyun menü ve başlıklarda küçük büyük harf (smallcaps) / hepsi büyük harf stilini kullanıyorsa Unity
Türkçe `i`'yi `I` yapıyordu (`İ` olmalı). Bu stilde çizilen satırlar artık işaretlenebilir.

### Eklendi
- **Çeviri tablosu sağ tık menüsü:** “Büyük harfle gösterilir (i → İ)” (seçili satırlar) ve
  “<tablo> tablosunun tamamı büyük harfle gösterilir” (ör. `World_Sign`, `UI_Settings`). İşaretli
  satırların anahtar sütununda `⇧` görünür. İşaretler projeye kaydedilir.
- **Dışa aktarma:** yalnızca işaretli satırlarda çevirideki `i` harfleri `İ` yazılır (büyük harf
  olduğu için oyun onu olduğu gibi çizer). Çeviri tablosundaki metin değişmez. Bilgi dosyasına
  dönüştürülen satır sayısı yazılır. Harf dönüştürme (İ → I) açıksa önce `İ` yazılır, sonra dönüştürülür.
- **Satır istisnası:** tablo işaretliyken tek bir satırın işaretini kaldırmak o satırı istisna yapar
  (tablonun geri kalanı işaretli kalır); işareti yeniden koymak istisnayı siler. İstisnalar projeye kaydedilir.
- 10 yeni test.

## [0.17.0] — 2026-10-23 — Mina the Hollower: yazma (deneysel)

**Cihazda henüz denenmedi.** Dosya yeniden düzenlenmez: boyut, dizin ve işaretçiler aynı kalır.

### Eklendi
- **Mina çevirisini mod olarak yazma:** çevrilen satırların 11 dil sütunu Türkçe metni gösterir; metin,
  satırın kendi dizgilerinin boşalttığı yere (sığmazsa diğer satırların artığına) yazılır. Gerçek
  dosyalarla: 3.521 satırlık yama çevirisi yazıldı, hepsi sığdı, yeniden okumada doğrulandı; çevirisiz
  satırlar özgün kaldı. Ayrıntı: `docs/formats/mina-ycd.md`.
- Dışa aktarırken "Tüm Türkçe harfleri dönüştür" seçin: oyunun fontunda ğ ş ı İ glifleri henüz doğrulanmadı.
- 4 yeni test.

## [0.16.0] — 2026-10-23 — Satır bağlam menüsü ve Türkçe Qt metinleri

### Eklendi
- **Çeviri tablosunda sağ tık menüsü:** istediğiniz satıra (ya da seçtiğiniz birden çok satıra) sağ
  tıklayıp **“Seçili satırları çevir”** diyebilirsiniz. Makine çevirisi penceresi “yalnızca seçili
  satırlar” seçili olarak açılır; onaylanmış satırlara dokunulmaz. Menüde ayrıca “Orijinali çeviri
  olarak kopyala” ve “Çevirisini temizle” vardır. Sağ tıklanan satır seçili değilse yalnızca o satır seçilir.

### Düzeltildi
- **İngilizce kalan metinler:** Qt'nin kendi metinleri (çeviri hücresindeki düzenleme menüsü: Undo/Copy/Paste,
  Evet/Hayır/Tamam/İptal düğmeleri, dosya seçme penceresi) İngilizce görünüyordu. Başlangıçta PySide6'nın
  Türkçe çeviri dosyası (`qtbase_tr.qm`) yükleniyor. Dosya bulunamazsa uygulama çalışır, günlüğe yazılır.
- 2 yeni test.

## [0.15.1] — 2026-10-22 — Font yaması uyarısı düzeltildi

### Düzeltildi
- **Yanlış font uyarısı:** Castlevania: Belmont's Curse'te "BaseFont (ı İ ş Ş ğ Ğ) eklenemedi" uyarısı
  çıkıyordu. Bu font yalnızca "¤" karakterini içeren bir yer tutucudur; harflerin türetileceği temel
  harfler (i, s, g …) yoktur ve hiçbir metin onunla çizilmez. Böyle fontlar artık uyarı üretmez,
  bilgi dosyasına "metin fontu değil; atlandı" notu düşülür.
- **Bilgi dosyası:** uyarı "ayrıntı bilgi dosyasında" diyordu ama hiç harf eklenemeyen fontların nedeni
  dosyaya yazılmıyordu. Gerçek bir metin fontuna harf eklenemezse neden (ör. "atlasta yer yok") artık
  "Font yaması (eklenemeyen / atlanan fontlar)" bölümünde listelenir.
- 2 yeni test.

## [0.15.0] — 2026-10-22 — Mina the Hollower: güvenli okuma

**Yalnızca okuma.** Oyun dosyalarına hiçbir şey yazılmaz; mod üretme (yazma) henüz yok ve Mina için
"Dışa Aktar" bu yüzden açık bir hata verir (TECH_DEBT 58). Switch dosyası bozulursa oyun çöker; yazma
aşaması ayrıca, adım adım ve cihazda denenerek yapılacak.

### Eklendi
- **Mina the Hollower (Yacht Club YCD `.yc`) okuma eklentisi:** `global.pak.yc` ve
  `global_startup.pak.yc` içindeki arayüz, konuşmacı adı ve diyalog tabloları çeviri tablosuna
  aktarılır (Switch sürümü 327680'de 3.974 İngilizce satır). Tablo yapısı `docs/formats/mina-ycd.md`.
- **Hazır Çeviriyi İçe Aktar** artık Mina yamasını da tanır (klasörde `.yc` varsa): PC yamasının
  Türkçe tablolarını okur ve **yalnızca yamanın dayandığı İngilizce metin oyunun şimdiki metniyle
  aynıysa** yazar. Kimlikler sürümler arasında kaydığı için bu denetim yanlış satıra çeviri
  yazılmasını önler. Gerçek veride 3.521 satır yazıldı; 366 satırın metni güncellemede değişmiş
  (atlandı, çevrilmeleri gerekir), 86 satır yamada yoktu, 1 satır kontrol kodu uyuşmadığı için atlandı.
- Özet penceresinde "özgün metni oyunun bu sürümünde değişmiş" satır sayısı gösterilir.
- 12 yeni test (elle üretilmiş YCD dosyalarıyla).

## [0.14.0] — 2026-10-22 — Hazır çeviriyi içe aktarma

**Cihazda doğrulandı:** Silver Pines'ın aktarılmış çevirisiyle üretilen mod, ürün sahibinin Switch cihazında başarıyla çalıştı (M5'in bitme ölçütü). Font yaması (M8) da cihazda doğrulandı: Türkçe harfler sorunsuz görünüyor.

### Eklendi
- **Araçlar → Hazır Çeviriyi İçe Aktar…:** oyunun topluluk Türkçe yamasındaki (Unity metin tabloları
  paketleri) çeviriler projeye aktarılır. Satırlar anahtarla eşleşir (tablo adındaki dil soneki
  `_en`/`_tr` yok sayılır); önce özet gösterilir ve onay istenir.
- Güvenlik: onayladığınız satırlara dokunulmaz; çeviriler "Makine" durumuyla yazılır; yamadaki kontrol
  kodları özgün kodlarla uyuşmayan satırlar yazılmaz ve mevcut çeviri korunur (oyunun özgün kodları
  dışa aktarırken yine geri konur). Font ve metin dışı paketler atlanır.
- **Silver Pines:** yamadaki 3.468 metnin 3.466'sı projeyle eşleşti; 3.459 satırın 3.455'i yazıldı
  (4 satır kontrol kodu uyuşmadığı için atlandı). DeepL çevirisine göre bağlam gerektiren etiketler
  (Well → Kuyu, Safe → Kasa, Resolution → Çözünürlük…) düzeldi.
- 4 yeni test.

## [0.13.0] — 2026-10-21 — Arayüz iyileştirmeleri ve çeviri denetimi

Silver Pines'ın DeepL ile çevrilmiş projesi gerçek veriyle incelendi (3.466 satır).

### Eklendi
- **Yazı boyutu:** Görünüm → Yazı boyutu (9–18 punto), Ctrl+= / Ctrl+- / Ctrl+0; tercih hatırlanır.
- **Çeviri tablosu:** sütun başlığına tıklayınca sıralama (artan → azalan → özgün sıra; Türkçe alfabe
  sırası: ç c'den sonra, ş s'den sonra), "Metni kaydır" (varsayılan açık: metnin tamamı görünür),
  her sütunun genişliği sürüklenerek ayarlanır ve hatırlanır. Kontrol Et'teki font ve satır tabloları
  da sıralanır.
- **Satır denetimleri:** "Sözlük" (sözlükteki terim kaynakta var, karşılığı çeviride yok) ve "Kod adı"
  (`Misc_Church_Medallion` gibi kaynaklar çevrilmiş; oyun bu adı arıyor olabilir).
- Oyun notları kutusu DeepL için bağlam olduğunu açıklıyor (talimat değil, İngilizce kısa tarif).
- `docs/test-emulator.md`: modu Switch olmadan emülatörde deneme.

### Değişti
- Uzun açıklamalar ipucuna taşındı: başlıkların yanındaki "i" simgesi (üzerine gelince veya tıklayınca
  açılır). Sayfalarda yalnızca kısa bir cümle görünür; metinler sadeleştirildi.
- Sıralama proxy'de değil modelde yapılır: 34.000 satırda 0,3 sn (önce 5 sn). Satır yükseklikleri yalnızca
  ekrandaki satırlar için ölçülür (3.466 satırda 2,3 sn yerine 0,01 sn).

### Düzeltildi
- Tablo sütunları (Orijinal/Çeviri) elle genişletilemiyordu.

## [0.12.0] — 2026-10-21 — M8: font yaması (TextMeshPro)

### Eklendi
- **Font yaması:** Unity TextMeshPro statik fontlarına eksik Türkçe harfler ekleniyor. Harfler
  aynı fontun kendi harflerinden üretiliyor: ı (i'nin noktası kaldırılarak), İ (I + nokta),
  ş/Ş (s/S + ç'nin çengeli), ğ/Ğ (g/G + kısa çizgi). Atlasta yer yoksa atlas büyütülüyor; var olan
  harfler yerinde kalıyor.
- **Kontrol Et ekranı:** font tablosunda "Yamayla eklenir" sütunu ve "Eksik Türkçe harfleri fontlara
  ekle" seçeneği. Seçenek açıkken harf dönüştürme yalnızca yamanın ekleyemediği harflere uygulanıyor.
- **Dışa aktarma:** değişen font bundle'ları moda yazılıyor; eklenen ve eklenemeyen harfler bilgi
  dosyasında, özet uyarı sonuç ekranında.
- **Silver Pines:** Noticia Text (3 stil), Impact, PapaMan ve tuş fontlarına altı harfin hepsi eklendi;
  yazılan dosya yeniden okunup metin çizilerek kontrol edildi.
- 12 yeni test (uzaklık dönüşümü, glif tarifleri, atlas büyütme, büyük harf fontu, ortak atlas,
  bundle yazımı, sahte oyunla tarama → dışa aktarma).

### Düzeltildi
- Kontrol Et ekranındaki öneri metinleri font yamasını hesaba katıyor.

### Doğrulanmadı
- Yamalı fontların oyunda (cihaz/emülatör) görünmesi (TECH_DEBT 48).

## [0.11.0] — 2026-10-21 — Game Freak mesajları (Pokémon)

### Eklendi
- **Game Freak mesaj eklentisi** (`.dat` + `.tbl`): şifreli UTF-16 satırlar çözülüp yeniden
  şifreleniyor; değişkenler, renk/sayfa kodları ve özel simgeler `⟦n⟧` olarak korunuyor; satır
  adları yan `.tbl` dosyasından bağlam olarak gösteriliyor.
- **Cinsiyet ve tekil/çoğul seçimleri** (`my ⟦1⟧boy⟦2⟧girl⟦3⟧`) çevrilebiliyor; seçenek
  uzunlukları yazarken yeniden hesaplanıyor (Türkçede seçenekler boş bırakılabilir).
- **Pokémon: Let's Go** (32.026 satır) ve **Legends: Arceus** (32.558 satır): tüm mesaj dosyaları
  değişiklik yapılmadan bayt bayt aynı geri yazılıyor; gerçek dışa aktarma denendi.
- Dil klasörleri: `English`, `French`, `JPN`, `JPN_KANJI` (ayrı dil), `Simp_Chinese`…
- Motor tahmini: "Game Freak (Pokémon)".
- Format eklentisi sözleşmesi: `collect_context(data, path)`; aktarma bağlamında `SOURCE_PATH`.
- 12 yeni test (bağımsız yazıcıyla üretilmiş dosyalar, seçimler, vekil çiftler, 5000 satır, sahte
  Pokémon oyunuyla tarama → aktarma → dışa aktarma).

### Doğrulanmadı
- Modun oyunda açılması; Türkçe harflerin (ğ ı İ ş) oyunun fontunda olup olmadığı (TECH_DEBT 45).

## [0.10.0] — 2026-10-21 — Unity I2 Localization

### Eklendi
- **I2 Localization desteği** (Unity oyunlarında yaygın yerelleştirme eklentisi): tüm dilleri tek
  nesnede tutan `LanguageSource` kaynakları okunur ve geri yazılır. Oyun derlemelerinde tip bilgisi
  silindiği için nesne ham bayttan çözülür; yapı sıkı denetlenir, değişiklik yoksa dosya bayt bayt
  aynı kalır, yalnızca değişen terimler yeniden yazılır.
- **Blasphemous:** 1.925 İngilizce satır (arayüz, eşyalar, diyaloglar) aktarılıyor; Türkçe İngilizce
  sütununa yazılıyor. Gerçek `resources.assets` ile dışa aktarma denendi: 10.942 nesneden yalnızca
  metin nesnesi değişti.
- Kaynak dil seçimi format eklentilerine iletiliyor (`SOURCE_LANGUAGE`); seçim yoksa İngilizce.
- 22 yeni test (iki I2 düzeni, dil sütunu seçimi, kontrol kodları, 3000 terimlik kaynak, sahte
  I2 oyunuyla tarama → aktarma → dışa aktarma).

### Değişti
- Unity eklentisi artık `.assets` serileştirilmiş dosyalarını da açıyor (önceden yalnızca bundle).
- Dil karşılaştırması `core/languages.py`'ye taşındı.

### Doğrulanmadı
- Değiştirilmiş `resources.assets` ile oyunun gerçek cihazda/emülatörde açılması.
- Blasphemous fontlarında Türkçe harfler (TECH_DEBT 44).

## [0.9.0] — 2026-10-21 — Gerçek oyun uyumluluğu

`games/` klasöründeki 14 oyunla tanılama yapıldı; tarama aşamasında duran oyunlar düzeltildi.
Sonuçlar: `docs/uyumluluk.md`.

### Düzeltildi
- **Binlerce bölümlü NCZ dosyaları** reddediliyordu ("bölüm sayısı mantıksız"): Blasphemous, MIO,
  MGS Master Collection, Avatar Legends güncellemesi. Sabit 64 sınırı kaldırıldı.
- **Dil kodu eşleşmesi:** dosya adında "en-us", tabloda "en" yazan oyunlarda (Kong) hiçbir metin
  aktarılmıyordu. Bölgesiz kod artık o dilin bölgeleriyle eşleşir.
- Disk dolduğunda Türkçe olmayan bir hata çıkıyordu; artık önbelleğe açmadan önce boş alan
  denetleniyor ve "Önbelleği Temizle" öneriliyor.

### Eklendi
- **Sıkıştırılmış NCA (LZ4) desteği:** yeni SDK'lı oyunlar (Avatar Legends); base ve güncellemeli.
- **Seyrek (sparse) NCA desteği:** verisinin bir kısmını güncellemeye bırakan ana oyunlar
  (Castlevania: Belmont's Curse). Seyrek base tek başına eklenirse güncellemeyi ister.
- **Dil klasörlerinin tanınması:** Nintendo "USen/EUfr…" ve Unreal "Localization/<hedef>/<dil>/"
  klasörleri; dil listesinde "İngilizce (ABD)", "İngilizce (Avrupa)" gibi adlar. Önceden bu
  oyunlarda tüm dillerin metinleri birlikte aktarılıyordu (Rhythm Heaven: 13 dil).
- "RomFS yok" uyarısı açıklandı (verinin program içinde olduğu, metinlerin çıkarılamayacağı).
- `lz4` doğrudan bağımlılık olarak listelendi.
- 29 yeni test (sıkıştırılmış ve seyrek NCA, binlerce bölümlü NCZ, dil kodları, disk dolu).

## [0.8.0] — 2026-10-21 — M7: Unreal Engine (.locres)

### Eklendi
- **.locres eklentisi:** sürüm 0–3; ad alanı/anahtar/özetler korunur, yalnızca metinler değişir;
  paylaşılan metinler doğru ayrılır; değişiklik yoksa dosya bayt bayt aynı kalır.
  `{Değişken}` ve UMG zengin metin etiketleri (`<Bold>`, `</>`, `<img …/>`) `⟦n⟧` olarak korunur.
- **.pak okuyucu:** sürüm 1–11 (eski ve yeni/kodlanmış dizin), Zlib/Gzip. Tarama yalnızca dizini
  okuyup metin adaylarını listeler; aktarma pak'ın tamamını değil yalnızca ilgili girdiyi okur.
  Şifreli pak ve Oodle için Türkçe ve açık hata.
- **Yama pak'ı ile dışa aktarma:** değişen .locres dosyaları orijinalin yanına `<ad>_NXCeviri_P.pak`
  olarak yazılır (orijinal pak'a dokunulmaz); yazılan pak yeniden okunarak doğrulanır; pak imzalıysa uyarı.
- Ortak etiket ayrıştırıcısı (`translate/markup.py`): Unity ve Unreal aynı kodu kullanır.
- Format eklentisi sözleşmesine `path_suffixes` (büyük dosyaları boşuna okumamak için) eklendi.
- 24 yeni test (tüm .locres sürümleri, pak v3/v7/v8/v9/v11, sıkıştırmalı/sıkıştırmasız, sahte Unreal
  oyunuyla tarama → aktarma → yama pak'ı).

### Doğrulanmadı
- Gerçek bir Unreal oyunu (geliştirme makinesinde yok). Yama pak'ının motorca kabulü oyunda denenmeli.

## [0.7.0] — 2026-10-21 — M5: kontrol ve dışa aktarma

### Eklendi
- **Font glif denetimi:** TextMeshPro font varlıkları (statik atlas karakter tabloları; dinamik
  fontlarda kaynak TTF), Unity `Font` nesneleri ve RomFS'teki TTF/OTF dosyaları (fontTools). Harf
  başına "kaç Latin fontta var" raporu; dile özgü fontlar ayrı tutulur; dinamik yedek fontta bulunan
  harfler ayrıca bildirilir.
- **Harf dönüştürme:** yok / yalnızca eksik harfler / tümü. Yalnızca üretilen moda uygulanır.
- **Satır denetimleri:** kontrol kodu, uzunluk sınırı, eksik harf, olası taşma, satır sonu, boşluk,
  çevrilmedi. Bulgudan çeviri tablosundaki satıra çift tıklayarak gidilir.
- **LayeredFS dışa aktarma:** Atmosphère (`atmosphere/contents/<TitleID>/romfs`) ve emülatör
  (`<TitleID>/<Mod Adı>/romfs`) yapıları. Yalnızca değişen dosyalar; iç içe arşivler yeniden
  kapatılır; her dosya yazılmadan önce yeniden okunup doğrulanır; geçici klasörden atomik taşıma;
  dolu klasörün üzerine yazmaz; iptalde iz bırakmaz; `NX Ceviri - Bilgi.txt` kurulum ve sürüm bilgisi.
- Metinlerin aktarıldığı oyun sürümü ile şu anki dosyalar farklıysa uyarı.
- **Arayüz:** "4. Kontrol Et" ve "5. Dışa Aktar" adımları.
- 22 yeni test (font raporu, dönüştürme, denetimler, MSBT/iç içe arşiv ve Unity dışa aktarma, arayüz akışı).

### Doğrulandı (gerçek oyun: Silver Pines)
- Font taraması: 27 font, 13 Latin statik; `ğ ı İ ş Ğ Ş` eksik, dinamik yedek fontta (LiberationSans) var.
- Mod üretildi (`atmosphere/contents/0100D5B026844000/romfs/.../localization-string-tables-english(en)_assets_all.bundle`),
  yeniden okunarak doğrulandı. Katalogda bu bundle'ın CRC alanı 0 görünüyor.

### Doğrulanmadı
- Modun gerçek cihazda/emülatörde açılması (M5'in bitme ölçütü) — ürün sahibi deneyecek.

### Bağımlılık
- `fonttools` (MIT) eklendi.

## [0.6.0] — 2026-10-21 — M4: DeepL ve sağlayıcı seçimi

### Eklendi
- **DeepL sağlayıcısı:** Free/Pro uç noktası anahtardan otomatik seçilir (":fx"); kontrol kodları
  XML etiketi (`<x id="n"/>`, `tag_handling=xml`) olarak gönderilip geri çevrilir; oyun notları
  `context` alanıyla iletilir; terimler DeepL sözlüğüne (v2 glossaries) yüklenir, yeni terim gelince
  birleşimle yeniden kurulur, iş bitince silinir (dil çifti desteklenmezse sözlüksüz devam ve uyarı);
  kota `/v2/usage` ile okunur ve gösterilir. Hata kodları (403, 456, 429, 413, 5xx) Türkçe ve
  ne yapılacağını söyleyen mesajlara çevrilir; geçici olanlar yeniden denenir.
- **API anahtarı saklama:** Windows Kimlik Bilgisi Yöneticisi (`keyring`); proje dosyasına, ayarlara
  veya log'a yazılmaz (testle kanıtlı).
- **Arayüz:** Makine Çevirisi penceresinde sağlayıcı seçimi (Ollama / DeepL), DeepL için kota ve
  tahmini karakter kullanımı; **Araçlar → Çeviri Ayarları…** penceresi (anahtarı kaydet / sil / test et).
- Aynı projede sağlayıcılar arasında geçiş: ör. DeepL kotası dolunca Ollama ile kalanlar çevrilir.
- Sahte DeepL sunucusu (`tests/fake_deepl.py`) ve 25 yeni test.

### Doğrulanmadı
- Gerçek bir DeepL hesabıyla istek (geliştirmede API anahtarı yok); API biçimleri resmi belgelerden.

### Bağımlılık
- `keyring` (MIT) eklendi.

## [0.5.0] — 2026-10-21 — M3 altyapısı (makine çevirisi)

### Eklendi
- **Çeviri sağlayıcısı sözleşmesi** (`translate/providers/base.py`, CLAUDE.md §4.2) ve
  **Ollama sağlayıcısı**: model listeleme (gömme modelleri elenir), bağlantı testi, JSON şemalı
  toplu çeviri, Türkçe hata mesajları (Ollama kapalı, model yok, bellek yetmedi, zaman aşımı).
- **Toplu çeviri yürütücüsü:** aynı cümle bir kez çevrilir; çeviri belleği; partiye özel sözlük
  terimleri; bozuk yer tutuculu satır tek başına yeniden istenir, düzelmezse "Hatalı" işaretlenir;
  geçici hatalarda yeniden deneme; her parti hemen kaydedilir → iptal/çökme sonrası kaldığı yerden
  devam.
- **Proje şeması v4:** çeviri belleği, terim sözlüğü ve proje ayarları (oyun notları, kaynak dil).
- **Arayüz:** "Makine Çevirisi…" penceresi (Ollama adresi, model listesi, bağlantı testi, oyun
  notları, kapsam: çevrilmemişler / seçililer), çalışırken ilerleme şeridi ve iptal, "Sözlük…"
  penceresi, "Makine" durum filtresi.
- Makine çevirisi **onaylanmış satırların üzerine asla yazmaz**; bellekteki insan çevirisini ezmez.
- Sahte Ollama sunucusu (`tests/fake_ollama.py`) ve 22 yeni test.

### Doğrulanmadı
- Gerçek bir modelle çeviri kalitesi ve hızı (geliştirme makinesinde uygun ekran kartı yok).
  Gerçek Ollama 0.34.4 sunucusuna karşı API biçimleri doğrulandı.

### Bağımlılık
- `httpx` (BSD-3) eklendi: Ollama (ve M4'te DeepL) HTTP istekleri, zaman aşımı yönetimi ve
  testlerde ağsız sahte sunucu (`MockTransport`).

## [0.4.0] — 2026-10-21 — M6 tamamlandı (Unity)

Yol haritası ürün sahibinin kararıyla değişti: M2 → **M6** → M3 (bkz. CLAUDE.md §8).

### Eklendi
- **Unity format eklentisi:** Unity Localization paketinin AssetBundle'lardaki `StringTable`'ları
  tip ağacı üzerinden okunup yazılıyor (UnityPy). TextMeshPro etiketleri ve Smart String
  değişkenleri `⟦n⟧` olarak korunuyor. Değişmeyen tablolara dokunulmuyor; değişen bundle orijinal
  sıkıştırma ayarlarıyla kaydedilip yeniden okunarak doğrulanıyor. AssetTable'lar (font/görsel
  başvuruları) metin sayılmıyor.
- **Okunur anahtar adları:** başka bundle'daki `SharedTableData`'dan anahtar adları
  (ör. `Dialogue/Jade_Intro_01`) toplanıyor; projede saklanıyor (şema v3, otomatik göç).
- **Kaynak dil seçimi:** oyunda birden çok dil varsa tarama raporunda "Kaynak dil" seçilir
  (varsayılan İngilizce); yalnızca o dildeki tablolar aktarılır, atlananlar bildirilir.
- **Çeviri tablosu:** "Grup" filtresi (Unity'de tablo koleksiyonu: Dialogue, Items…, diğerlerinde
  dosya), Anahtar sütununda okunur ad, yol ve anahtarlar baştan kısaltılıyor.
- Format eklentisi sözleşmesine `collect_context`, `language` ve `candidates_only` eklendi.
- Testler için sahte Unity bundle üreticisi (`tests/unitybuild.py`); 33 yeni test.

### Doğrulandı (gerçek oyun: Silver Pines, base v0 + update v65536)
- 3.466 metin, 24 tablo, 1 bundle aktarıldı; 9 diğer dil atlandı; tüm satırların anahtar adı var.
- Değişikliksiz geri yazım orijinal bundle'la bayt bayt aynı; Türkçe çeviri yazılıp geri okundu.

### Bağımlılık
- `UnityPy` (MIT) eklendi; gerekçesi ve paket boyutuna etkisi ARCHITECTURE.md'de.

## [0.3.0] — 2026-10-21 — M2 tamamlandı

### Eklendi
- **Arşivleri açma-kapama:** SARC yeniden kurma (dosya sırası, hizalama, hash anahtarı ve
  adlar korunur; değişiklik yoksa bayt bayt aynı), Yaz0 sıkıştırıcı (başlıktaki hizalama
  alanı korunur), ZSTD sıkıştırıcı, iç içe yolları (`dış.sarc.zs>…>Msg/a.msbt`) açan ve
  değiştirip tüm üst arşivleri yeniden kapatan `archives/nested.py`. Değişmeyen arşivler
  yeniden sıkıştırılmaz.
- **Format eklentisi sözleşmesi** (`formats/base.py`: `detect` / `extract` / `inject`) ve
  eklenti kaydı (`formats/registry.py`).
- **MSBT eklentisi:** UTF-16 (LE/BE) ve UTF-8; LBL1 etiketleri girdi kimliği olur; kontrol
  etiketleri ham baytlarıyla `⟦1⟧`, `⟦2⟧`… yer tutucularına çevrilir; geri yazarken yalnızca
  TXT2 yeniden kurulur. Zorunlu round-trip testi 6 varyantta ve 5.000 satırlık dosyada geçiyor.
- **Yer tutucu denetimi:** eksik, fazla, tekrarlanan, yer değiştiren veya yarım kalmış
  yer tutucular Türkçe açıklamayla "Hatalı" işaretlenir; hatalı satır dosyaya yazılmaz.
- **Proje şeması v2:** `text_files` ve `text_entries` tabloları (orijinal, çeviri, durum,
  açıklama, kontrol kodları). v1 projeler açılırken otomatik göç edilir (`.bak` yedeğiyle).
- **Metin aktarma:** tarama raporundaki MSBT dosyaları (iç içe arşivlerin içindekiler dahil)
  çıkarılıp projeye aktarılır; bozuk dosya işlemi durdurmaz, uyarı olarak raporlanır.
  Yeniden aktarmada çeviriler korunur; orijinali değişen çevrilmiş satır "Hatalı" (gözden
  geçir) işaretlenir; oyundan kalkan satırlar silinir.
- **Arayüz — "3. Çevir":** sanal model üzerinde çeviri tablosu (Orijinal / Çeviri / Durum /
  Dosya / Anahtar), çift tıklayarak çok satırlı düzenleme (Enter kaydeder, Shift+Enter yeni
  satır), arama, durum ve dosya filtresi, çoklu seçim ve toplu işlemler (orijinali kopyala,
  çeviriyi temizle), ilerleme göstergesi, kontrol kodlarını açıklayan ipuçları. Her
  düzenleme projeye hemen (işlem içinde) yazılır.
- Tarama raporunda "Metinleri Çeviri Tablosuna Aktar" düğmesi ve hangi metin türlerinin
  desteklendiğini/desteklenmediğini söyleyen bilgi bandı.
- Başlatıcı: `NX Ceviri Studyosu.bat`.

### Değişti
- Lisans kararı: `oead` (GPL) kullanılmadı; SARC/Yaz0 yazıcılar kendimiz yazıldı. Uygulamanın
  lisansı serbest kalır.

## [0.2.0] — 2026-10-21 — M1 tamamlandı

### Eklendi
- **Anahtarlar:** `prod.keys` ve isteğe bağlı `title.keys` okuma; `header_key`,
  `key_area_key_application_XX` ve `titlekek_XX` varlığı ve uzunlukları doğrulanır. Eksik,
  boş, bozuk, çok büyük veya metin olmayan dosyalarda Türkçe, satır numaralı hata. Anahtar
  değerleri hiçbir yere yazılmaz (testle kanıtlı).
- **Konteyner:** NSP/NSZ (PFS0) okuma; NCZ blok kipinde rastgele erişim, akış kipinde
  önbelleğe açma; NSZ → NSP dönüştürme (SHA-256 doğrulamalı, atomik yazım); NCA3 başlığı ve
  bölümleri (AES-XTS/CTR), içerik anahtarı (anahtar alanı veya bilet/title.keys); CNMT'den
  TitleID/sürüm, NACP'den oyun adı ve görünen sürüm; RomFS okuma.
- **Base + update birleştirme:** BKTR yamaları (Indirect + AesCtrEx bucket tree'leri) ile
  güncel RomFS; tam RomFS taşıyan güncellemeler için dosya düzeyinde katmanlama; DLC ayrı
  ağaç. Yanlış oyunun güncellemesi, base'siz güncelleme ve çift base açıkça reddedilir.
- **Çıkarma:** RomFS'i (tamamı veya yalnızca metin adayları) klasöre çıkarma; geçici klasöre
  yazıp yerine taşır, iptal edilince iz bırakmaz, dolu klasörün üzerine yazmaz, klasör dışına
  çıkan dosya adlarını reddeder.
- **Format tarama:** SARC/Yaz0/ZSTD iç içe arşivlerin içine bakan tarayıcı; MSBT, Unity,
  Unreal, düz metin/JSON/CSV ve diğer türlerin tespiti; metin olasılığı (Yüksek/Olası);
  kanıtlarıyla motor tahmini (Unity, Unreal, Nintendo LMS, Godot, GameMaker, Ren'Py).
- **Proje dosyası (.nxproj):** SQLite şeması v1 (oyun, kaynak dosyalar, tarama sonucu),
  göç altyapısı (`user_version`, göç öncesi `.bak` yedeği, başarısız göçte geri alma),
  atomik "Farklı kaydet", bozuk/yabancı/yeni sürüm dosya kontrolü.
- **Arayüz:** "1. Oyunu Ekle" ve "2. Metinleri Tara" adımları; anahtar seçimi ve doğrulama
  rozeti; sürükle-bırak ve dosya seçici ile NSP/NSZ ekleme; arka planda ilerleme ve iptal;
  özet kartları, motor tahmini, filtrelenebilir/aranabilir sanal tablo; boş, yükleniyor ve
  hata durumları; açık/koyu/sistem teması; proje yeni/aç/kaydet/farklı kaydet; önbellek
  boyutu ve temizleme; kaydedilmemiş değişiklik uyarısı; log klasörü.
- **Testler:** 113 test (anahtar doğrulama ve sızdırmama, bozuk/eksik dosyalar, NCA/NCZ/BKTR,
  birleştirme, çıkarma, arşivler, format tespiti, proje kaydet/aç/göç, Türkçe karakterli
  yollar, 50.000 satırlık tablo, arayüz akışı). Testler sahte anahtarlarla sıfırdan üretilen
  içerikler kullanır; depoda gerçek oyun dosyası yoktur.

## [0.1.0] — 2026-10-21 — Proje iskeleti

### Eklendi
- Klasör yapısı, `pyproject.toml`, ruff/mypy/pytest yapılandırması, `.gitignore`
  (anahtarlar, oyun dosyaları, önbellek ve `.nxproj` dışarıda), `ARCHITECTURE.md`,
  `TECH_DEBT.md`, `CHANGELOG.md`.
