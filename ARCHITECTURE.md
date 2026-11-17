# ARCHITECTURE — NX Çeviri Stüdyosu

Güncel sürüm ve durum için `CHANGELOG.md` ve `HANDOFF.md`'ye, aşama tablosu için `docs/yol-haritasi.md`'ye bakın.
Bu belge, yığını, katmanları, bağımlılıkları ve alınan kararları gerekçeleriyle kaydeder.

## 1. Yığın

| Konu | Seçim | Gerekçe |
|---|---|---|
| Dil | **Python 3.13** (destek: 3.12–3.14) | Geliştirme makinesinde 3.12 kurulu değil; 3.13 ve 3.14 kurulu. Tüm bağımlılıkların 3.13 için Windows wheel'i var. `requires-python = ">=3.12,<3.15"` korunur; 3.12 ile ayrıca test edilmedi (bkz. TECH_DEBT). |
| Arayüz | **PySide6-Essentials 6.12** | Tam `PySide6` paketi WebEngine/Pdf gibi kullanılmayan yüzlerce MB modül getirir. Essentials (QtCore/Gui/Widgets) yeterli, paket boyutunu ciddi düşürür. LGPL-3.0. `QSortFilterProxyModel.beginFilterChange` için en az 6.9. |
| Proje dosyası | **SQLite** (`sqlite3`, standart kütüphane) | Tek dosya, işlem (transaction) güvenli, ek bağımlılık yok. |
| Paketleme | **PyInstaller** onedir (`packaging/NXTR.spec`, 0.31.0; 0.47.0'da adı değişti) | Aşağıdaki karşılaştırmaya bakın. |

### 1.1 PyInstaller ve Nuitka karşılaştırması

| | PyInstaller 6.22 | Nuitka 4.3 |
|---|---|---|
| Lisans | GPL-2.0+ ve *önyükleyici istisnası*: üretilen uygulamanın lisansını etkilemez | AGPL-3.0 (derleyicinin kendisi); çıktının lisansı konusunda ek inceleme gerekir |
| Derleme | Saniyeler/dakikalar; C derleyicisi gerekmez | C'ye derler; MSVC/MinGW gerekir, derleme dakikalar–onlarca dakika |
| PySide6 desteği | Olgun hook'lar, `--onedir` ile taşınabilir klasör | `--enable-plugin=pyside6` ile iyi, ama derleme sorunları daha zor ayıklanır |
| Çalışma hızı | Yorumlayıcı aynı; bu uygulamada darboğaz AES/zstd (C uzantıları), Python değil | Biraz daha hızlı Python kodu; bu iş yükünde fark küçük |
| Antivirüs yanlış alarmı | Tek dosya kipinde sık; **onedir** kipinde daha az | Daha az |

**Karar: PyInstaller, `--onedir` (taşınabilir klasör).** Lisans riski yok, derlemesi basit ve
tekrarlanabilir; hız avantajı Nuitka'yı haklı çıkaracak düzeyde değil (ağır işi zaten C
uzantıları yapıyor). Antivirüs riskini azaltmak için tek dosya (`--onefile`) kullanılmayacak.

## 2. Bağımlılıklar (her biri "neden" satırıyla)

### Çalışma zamanı

| Paket | Sürüm | Lisans | Neden |
|---|---|---|---|
| `PySide6-Essentials` | ≥6.9 | LGPL-3.0 | Arayüz. |
| `cryptography` | ≥44 (50.0.2 test edildi) | Apache-2.0 / BSD | NCA başlığı (AES-XTS), bölümler (AES-CTR), anahtar alanı/başlık anahtarları (AES-ECB). abi3 wheel'leri var; PyInstaller hook'u standart. Kendi AES'imizi yazmak güvenli/hızlı olmazdı. |
| `zstandard` | ≥0.23 (0.25.0 test edildi) | BSD-3 | NCZ blokları/akışı ve oyun içi `.zs` dosyaları. Python 3.9–3.14 için Windows wheel'leri var, etkin bakımda. |
| `fonttools` | ≥4.50,<5 (4.67.0 test edildi) | MIT | TTF/OTF ve Unity `Font` nesnelerindeki gömülü TTF'lerin cmap tablosunu okuyarak Türkçe glif denetimi. Font biçimini kendimiz çözmek gereksiz risk olurdu. |
| `lz4` | ≥4.3,<5 (4.4.5 test edildi) | BSD-3 | Yeni SDK'lı oyunlarda NCA veri bölgesinin LZ4 blok sıkıştırması. UnityPy'nin de bağımlılığıdır (zaten kuruluydu); doğrudan kullandığımız için açıkça listelendi. C hızında açma gerekir; LZ4'ü Python'da yazmak GB'larca veride çok yavaş olurdu. |
| `keyring` | ≥25,<26 (25.7.0 test edildi) | MIT | DeepL API anahtarını Windows Kimlik Bilgisi Yöneticisi'nde saklamak (CLAUDE.md §4.2). Windows'ta `WinVaultKeyring` arka ucu doğrulandı. |
| `httpx` | ≥0.27,<1 (0.28.1 test edildi) | BSD-3 | Ollama (M4'te DeepL) HTTP istekleri; ayrıntılı zaman aşımı ve bağlantı hatası türleri; `MockTransport` ile testlerde ağsız sahte sunucu. Standart `urllib` ile aynı güvenilirlikte hata ayrımı ve test kolaylığı elde etmek daha çok kod gerektirirdi. |
| `UnityPy` | ≥1.25,<2 (1.25.4 test edildi) | MIT | Unity AssetBundle (UnityFS, LZ4/LZMA) ve SerializedFile okuma/yazma; tip ağacıyla MonoBehaviour okuma/yazma. Etkin bakımda, cp38–cp314 wheel'leri var. Kendimiz yazmak (bundle sıkıştırma blokları, SerializedFile v22+ meta verisi, typetree okuyucu/yazıcı) çok daha büyük ve riskli olurdu. **Bedeli:** zorunlu bağımlılıkları (Pillow, texture2ddecoder, etcpak, astc-encoder-py, fmod_toolkit/pyfmodex, brotli, lz4, fsspec, attrs, tpk_ar) paket boyutunu büyütür; M9'da PyInstaller ile kullanılmayan modüllerin dışlanması denenecek. |
| `Pillow` | ≥10 (13.0.0 test edildi) | HPND | FSD/MSG yazı dokusunun (`fontpatch/fsdmsg.py`) çizimi ve BC7 dokuların okunması. UnityPy'nin de bağımlılığı olduğundan ek yük getirmez. |

### Geliştirme

`pytest`, `pytest-qt` (arayüz testleri), `ruff` (lint + format), `mypy` (strict).

### Değerlendirilip *kullanılmayan* adaylar

| Aday | Durum (Ekim 2026) | Karar |
|---|---|---|
| `nsz` 5.0.0 | MIT, etkin bakımda, saf Python | **Kütüphane olarak kullanılmadı.** CLI odaklı: anahtarları sabit yollardan (`~/.switch`) kendisi arar, global durum tutar, konsola yazar; ilerleme/iptal arayüzü yok. NCZ biçimi küçük ve belgeli olduğundan okuyucuyu `zstandard` ile kendimiz yazdık (`core/container/ncz.py`); nsz yalnızca biçim başvurusu olarak kullanıldı. |
| `hactool` 1.4.0 | ISC, son sürüm 2020, depo 2023'ten beri durgun | **Kullanılmadı.** NCZ'yi açamaz (önce diske tam NSP açmak gerekir: oyun başına GB'larca ek yer), ayrı süreç olduğu için ince ilerleme/iptal ve Türkçe hata vermek zor. |
| `hactoolnet` / LibHac | GitHub deposu artık erişilemiyor (404) | **Kullanılmadı.** Bakımı ve lisansı doğrulanamadı. |
| `oead` 1.3.0 | GPL-2.0+, etkin bakımda, cp310–cp315 wheel'leri var | **Kullanılmadı (0.3.0 kararı).** Teknik olarak uygun, ancak GPL olduğu için paketlenirse **uygulamanın tamamı GPL ile dağıtılmak zorunda kalır.** SARC okuma/yazma, Yaz0 açma/sıkıştırma küçük ve iyi belgelenmiş biçimler; kendimiz yazdık (`core/archives/`), bayt düzeyinde round-trip testleriyle. MSBT için oead zaten gerekmiyordu. |

## 3. Katmanlar

```
nxceviri/
  core/                    # arayüzü bilmez; Qt import etmez
    errors.py              # Türkçe mesaj + "ne yapmalı" ipucu taşıyan hata türleri
    progress.py            # TaskContext: ilerleme geri çağrısı + iptal bayrağı
    languages.py           # dil kodu karşılaştırma ("en" ↔ "en-us") ve Türkçe sıralama anahtarı
    keys/keyset.py         # prod.keys / title.keys okuma, doğrulama (değerler asla yazılmaz)
    container/
      storage.py           # Storage soyutlaması (dosya, dilim, bellek) — salt okunur
      crypto.py            # AES-XTS/CTR/ECB, AesCtrStorage
      pfs0.py              # NSP/NSZ ve PFS0 bölümleri
      ncz.py               # NCZ blok/akış okuma, NSZ→NSP (SHA-256 doğrulamalı)
      nca.py               # NCA3 başlığı, bölümler, içerik anahtarı
      buckettree.py        # BKTR ağaç okuyucu, IndirectStorage, ZeroStorage
      compression.py       # NCA sıkıştırma katmanı (LZ4 bloklar)
      patch.py             # BKTR: Indirect + AesCtrEx bucket tree'leri
      romfs.py             # RomFS ağacı
      metadata.py          # CNMT, NACP, bilet (.tik)
      package.py           # Paket açma (TitleID, sürüm, ad, NCA'lar)
      view.py              # Birleşik görünüm (base+update+DLC), güvenli çıkarma
      nso.py               # ExeFS `main` kodunu açma (yalnızca dizge aramak için okunur)
    archives/              # SARC (oku/kur), Yaz0, ZSTD (aç/sıkıştır), nested.py (iç içe yollar)
      pak.py               # Unreal .pak okuma (v1–11) ve yama pak'ı yazma
      psb.py               # PSB (v2–4) okuma, dizge tablosunu yerinde yeniden yazma
      psb_archive.py       # mdf aç/kodla, oyun anahtarını kullanıcının kodundan bulma, .psb.m + .bin
      nni.py               # NNI (.ni dizini + .na veri): oku, değişen üyeleri sona ekleyerek yaz
      cpk.py               # CRI CPK (@UTF tabloları, CRILAYLA açma): oku, değişen dosyalarla yeniden kur
      access.py            # iç içe yoldan okuma; pak/PSB/NNI/CPK'da yalnızca dizin + girdi
    formats/
      detection.py         # imza/uzantı ile tür tahmini + metin olasılığı
      scanner.py           # iç içe arşiv taraması, motor tahmini, ScanReport
      base.py              # format eklentisi sözleşmesi: detect / extract / inject
      registry.py          # kayıtlı eklentiler
      msbt/                # MSBT eklentisi (M2)
      unity/               # Unity Localization string tabloları (M6, UnityPy); i2.py: I2 Localization (ham bayt); serializeref.py: Unity SerializeReference kayıt defteri
      unreal/              # .locres (M7)
      gfmsg/               # GFMSG mesajları (.dat + .tbl)
      nnitext/             # NNI arşivi: XSO betik dizgeleri (Japonca kopyayla metin/kimlik ayrımı) + arayüz XML'i
      fmsb/                # FMSB MsgSheet (CPK)
      wadlin/              # WAD/LIN biçimi: .lin betik metinleri + .pak metin tabloları (WAD içinde)
    project/store.py       # .nxproj şeması, göçler, atomik "farklı kaydet"
    pipeline.py            # arayüzün çağırdığı iş akışı adımları
    translate/
      placeholders.py      # ⟦n⟧ yer tutucuları ve sayı/tür/sıra denetimi
      status.py            # satır durumları (çevrilmedi/makine/onaylandı/hatalı)
      codekinds.py         # kontrol kodu türleri (satır sonu, sayfa sonu, değişken, sembol, biçim, diğer): kodun yer/uzunluk etkisi
      fit.py               # saf sığdırma: sayfa/satır ayrıştırma, sorun bulma, noktalama→kelime bitimi bölme (Qt'siz, projesiz)
      fitconfig.py         # sınırlar + seçenekler + kod türlerinin `settings` tablosundan okunması/yazılması, orijinalden öğrenme
      providers/base.py    # TranslationProvider sözleşmesi, ProviderError
      providers/ollama.py  # Ollama (yerel) sağlayıcısı
      providers/deepl.py   # DeepL (Free/Pro, XML etiket, sözlük, kota)
    secrets.py             # API anahtarları: keyring (Windows Kimlik Bilgisi Yöneticisi)
      runner.py            # toplu çeviri: tekilleştirme, bellek, sözlük, yeniden deneme, devam
      csvio.py             # TXT/XLSX/CSV dışa/içe aktarma (dış redaksiyon ve dış çeviri), hazır istem
    qa/fonts.py            # font glif denetimi (TMP, TTF/OTF) + yamayla eklenebilecek harfler
    fontpatch/             # M8: sdf.py (mesafe alanı), tmp.py (glif üretimi/atlas), unity.py (bundle)
    qa/transliterate.py    # harf dönüştürme (yalnızca dışa aktarırken)
    qa/checks.py           # satır denetimleri
    export/layeredfs.py    # Atmosphère / emülatör mod klasörü, atomik ve doğrulamalı
  gui/                     # PySide6; iş mantığı içermez
    main_window.py         # adımlar arası akış, menüler, arka plan işleri
    checks_controller.py   # Kontrol Et iş akışı: denetim, pano yenileme, yok sayma, Düzelt (karar 221)
    export_controller.py   # Dışa Aktar iş akışı: özet, hedef klasör, mod oluşturma (karar 221)
    project_controller.py  # proje yaşam döngüsü: yeni, aç, kaydet, son projeler, kurtarma (karar 221)
    machine_controller.py  # makine işleri: çevir, yeniden çevir, talimatla düzelt penceresi ve iş (karar 221)
    icons.py + icons/*.svg # Lucide simgeleri; temaya uyan QIcon, bind_icon/refresh_icons
    appicon/               # uygulama simgesi: nxtr.svg + nxtr-kucuk.svg (kaynak) → .ico/.png (packaging/make_icon.py)
    step_nav.py            # simgeli kenar çubuğu (StepNav) ve proje başlığı
    statusbar.py           # durum çubuğu bölmeleri (satır, ilerleme, sorun, sağlayıcı, imleç, ¶, kayıt)
    textmarks.py           # işaretli metin (semboller, çipler): saf işlevler, yalnızca çizim
    marked_delegate.py     # tablo hücreleri: textmarks + hiza, HTML ön belleği
    editor_pane.py         # düzenleme paneli: özgün/çeviri, çipler, sayaç, kayıt isteği
    view_actions.py        # semboller/hiza/panel konumu: paylaşılan QAction'lar ve ayarları
    widgets.py             # ortak parçalar: Card, Banner, PageHeader, ActionBar, StatusChip, DropZone…
    *_page.py              # beş adım ekranı
    jobs.py                # makine işi başlıkları, iş kimliği, sonuç iletileri
    csv_dialog.py          # dış redaksiyon/çeviri penceresi (TXT/XLSX, kapsam, parçalar, hazır istem)
    recovery.py            # kaydedilmemiş proje kurtarma kopyası
    recent.py              # Dosya → Son Projeler
packaging/NXTR.spec        # PyInstaller (taşınabilir Windows klasörü)
packaging/make_icon.py     # simge SVG'sinden .ico/.png üretir (simge değişince elle çalıştırılır)
tests/                     # pytest; tests/nxbuild.py sahte anahtarla test içeriği üretir
tools/                     # paketlenecek yardımcı ikililer (M1'de gerek kalmadı, boş)
docs/formats/              # çözümlenen biçimlerin notları
```

> Not: CLAUDE.md'deki ağaçta `tests/` ve `tools/` `nxceviri/` altında gösteriliyor. Bunları
> depo köküne koyduk: testlerin paketle birlikte dağıtılmaması ve pytest/PyInstaller
> alışkanlıklarıyla uyum için. İçerik ve amaç aynıdır.

### 3.1 Veri akışı (M1)

```
NSP/NSZ ──FileStorage(rb)──► Pfs0 ──► [.ncz → NczBlockStorage | önbellekteki .nca]
                                          │
                                          ▼
                                 Nca (header_key: XTS) ── content key (key area | bilet/title.keys)
                                          │
              base RomFS bölümü (CTR) ◄───┼───► update yama bölümü (BKTR: Indirect + AesCtrEx)
                                          ▼
                              IndirectStorage → RomFs → LayeredRomFs (GameView)
                                          ▼
                              scan_view → ScanReport → Project (.nxproj)
```

Hiçbir aşamada oyunun tamamı diske açılmaz: blok kipindeki NCZ'ler rastgele erişimle
(1 MB'lık bloklar, LRU önbellek) doğrudan okunur. Yalnızca akış kipindeki NCZ'ler
proje önbelleğine bir kez açılır (SHA-256 ile doğrulanarak).

## 4. Önemli kararlar

1. **Kendi NCA/NCZ/BKTR okuyucumuz.** Harici araç çağırmadan, diske ek GB'lar yazmadan,
   ince ilerleme/iptal ve Türkçe hata mesajlarıyla çalışmak için. Doğruluk iki yoldan
   kanıtlandı: (a) testlerde sıfırdan şifrelenmiş sahte içerikler, (b) gerçek bir oyunda
   (bir Unity oyunu, base v0 + update v65536) birleşik RomFS'in rastgele 200 bloğunun oyunun
   kendi IVFC SHA-256 hash ağacıyla eşleşmesi ve NSZ→NSP çıktısının NCA adlarındaki
   SHA-256 ile eşleşmesi.
2. **Güncelleme birleştirme.** Gerçek güncellemeler BKTR yamasıdır; base ile birleşince
   tam ve güncel RomFS oluşur (bu, dosya düzeyinde "update base'i geçersiz kılar" kuralını
   kendiliğinden sağlar). Güncelleme tam RomFS taşıyorsa `LayeredRomFs` dosya düzeyinde
   katmanlar. Her dosya için kaynak ("base"/"update"/"dlc") raporlanır: BKTR'de dosyanın
   herhangi bir baytı yamadan geliyorsa "update".
3. **DLC ayrı başlıktır.** Kendi TitleID'si ve kendi LayeredFS klasörü olacağı için ayrı
   ağaç olarak taranır.
4. **Anahtar güvenliği.** `KeySet.__repr__` değer göstermez; hata mesajları yalnızca anahtar
   adını/satır numarasını içerir; NCZ bölüm anahtarları ve bilet `repr`'leri gizlidir.
   Bir test, log çıktısında, hata metinlerinde ve kaydedilmiş `.nxproj` baytlarında hiçbir
   anahtar değerinin (hex veya ham) geçmediğini doğrular. Anahtar dosyası yolu proje
   dosyasında değil, kullanıcı ayarlarında (`QSettings`) tutulur.
5. **Proje dosyası.** Kaydedilmemiş proje bellekte; "Farklı kaydet" SQLite yedekleme
   API'siyle geçici dosyaya yazar ve `os.replace` ile atomik olarak yerine taşır. Kayıtlı
   projede her değişiklik `BEGIN IMMEDIATE … COMMIT` işlemiyle anında yazılır
   (`synchronous=FULL`). Şema sürümü `PRAGMA user_version`, sahiplik `PRAGMA application_id`
   ("NXPR") ile izlenir; göçten önce `.nxproj.bak` yedeği alınır.
6. **Önbellek.** Kayıtlı projede `<proje>_onbellek/`, kaydedilmemişte
   `%LOCALAPPDATA%\NXCeviri\onbellek`. Arayüzde boyutu gösterilip temizlenebilir.
7. **Metin olasılığı** bu aşamada ad/uzantı ve imzaya dayalı bir tahmindir; Unity bundle
   içerikleri M6'da UnityPy ile gerçekten açılınca kesinleşecektir.

### 4.1 M2 kararları

8. **Kontrol kodlarının temsili.** Format eklentisi her kodu ham baytlarıyla saklar ve metinde
   `⟦n⟧` ile gösterir. Proje dosyası kodların ham baytlarını (hex) ve açıklamalarını tutar;
   çevirmen yalnızca yer tutucuları görür. Geri yazmadan önce sayı, tür (numara) ve sıra
   denetlenir; uymayan satır "Hatalı" olur ve dosyaya yazılmaz, sessizce düzeltilmez.
9. **Girdi kimliği.** `(dosya yolu, MSBT etiketi)`; etiket yoksa metin indeksi. İç arşivdeki
   dosyalar tarama yoluyla (`dış.sarc.zs>…>a.msbt`) tanımlanır. Böylece güncellemeyle
   değişen metinler yeniden aktarıldığında çeviriler doğru satırda kalır.
10. **Elle girilen geçerli çeviri "Onaylandı"** sayılır (insan girdisidir). "Makine" durumu M3'te
    makine çevirisiyle kullanılmaya başlanacak; o zamana kadar filtrede gösterilmez.
11. **Veritabanı yazımları ana iş parçacığında.** SQLite bağlantısı iş parçacıkları arasında
    paylaşılmaz; ağır iş (oyundan metin çıkarma) arka planda yapılır, sonuç tek işlemle yazılır.
12. **Arşivler değişmediyse yeniden kurulmaz/sıkıştırılmaz**; SARC yeniden kurulurken her dosyanın
    orijinal hizalaması korunur.

### 4.2 M6 kararları

13. **Hedef: Unity Localization paketinin `StringTable`'ları.** Bir Unity oyununda tüm oyun metni
    (3.466 satır, 24 tablo) bu yapıda. Tablo tip ağacı bundle'ın içinde olduğu için oyunun
    IL2CPP kodunu çözmeye gerek kalmadan güvenle okunup yazılır.
14. **Girdi kimliği `TabloAdı/m_Id`** (ör. `Dialogue_en/4123…`): m_Id kalıcıdır. Okunur anahtar
    adları (`Dialogue/Jade_Intro_01`) başka bir bundle'daki `SharedTableData`'dan, aktarmanın ilk
    geçişinde toplanır ve projede `context` sütununda (şema v3) saklanır; çeviri tablosunda
    "Anahtar" ve "Grup" (tablo koleksiyonu) olarak gösterilir.
15. **Kaynak dil.** Oyunda aynı tablonun her dil için kopyası vardır. Kullanıcı kaynak dili seçer
    (varsayılan İngilizce); yalnızca o dildeki tablolar aktarılır. Türkçe metin bu dilin yerine
    yazılacaktır (oyun o dilde oynandığında Türkçe görünür).
16. **Kontrol kodları:** TextMeshPro zengin metin etiketleri (`<b>`, `<color=…>`, `<sprite …>`) ve
    Smart String ifadeleri (`{0}`, `{input_0}`, iç içe `{…}` dahil bütün olarak) `⟦n⟧` olur.
17. **AssetTable ayrımı.** AssetTable (font/görsel başvuruları) StringTable ile aynı yapıdadır;
    tüm dolu değerleri 32 haneli GUID olan tablo metin sayılmaz.
18. **Geri yazma:** yalnızca değişen tablolar yeniden serileştirilir (değişmeyen nesneler bayt
    bayt aynı kalır; gerçek oyunda 24/24 tabloda doğrulandı), bundle orijinal sıkıştırma
    bayraklarıyla kaydedilir ve döndürülmeden önce yeniden okunup her metin karşılaştırılır.
    Hiçbir metin değişmediyse orijinal baytlar döner.

### 4.3 M3 kararları

19. **Sonuçlar parti parti kaydedilir.** Çeviri arka plan iş parçacığında yapılır; her partinin
    sonucu Qt sinyaliyle ana iş parçacığına gelir ve tek işlemde projeye yazılır (SQLite
    bağlantısı iş parçacıkları arasında paylaşılmaz). Ayrı bir "iş durumu" tablosu yoktur:
    satır durumları zaten nerede kalındığını gösterir, yeniden başlatma yalnızca çevrilmemiş
    satırları alır.
20. **Çeviri belleği proje içindedir** (kaynak metin → çeviri, köken insan/makine). Projeler arası
    ortak bellek şimdilik yok.
21. **İstem İngilizce, JSON şemalı.** Yanıt `format` ile şemaya zorlanır; serbest metin
    ayrıştırılmaz.
22. **Model sabit kodlanmaz.** Uygulama yüklü modelleri listeler; öneri listesi yalnızca yol gösterir.
23. **Onaylanmış satırlar korunur.** Makine çevirisi `approved` durumundaki satıra yazmaz.

### 4.4 M4 kararları

24. **DeepL'e kontrol kodları kendi kapanan XML etiketi olarak gider** (`<x id="3"/>`); DeepL bunları
    çeviride uygun yere taşıyabilir. Taşıma sırayı değiştirirse satır "Hatalı" olur (TECH_DEBT #26).
25. **DeepL sözlüğü iş başına geçicidir.** Kalıcı sözlük eşitlemesi (hesapta tek sözlük, değişince
    güncelleme) yapılmadı; her iş bittiğinde oluşturulan sözlük silinir, hesapta birikmez.
26. **v2 sözlük uç noktası kullanıldı;** DeepL yeni entegrasyonlar için v3'ü öneriyor. v2 tek dil
    çifti için yeterli ve belgeleri net; v3'e geçiş TECH_DEBT'te.
27. **Sağlayıcı seçimi uygulama ayarıdır** (son kullanılan hatırlanır); her satırın hangi sağlayıcıyla
    çevrildiği ayrıca kaydedilmez (durum "makine").

### 4.5 M5 kararları

28. **Mod her zaman yeni/boş klasöre üretilir.** SD kart veya emülatör klasörüne doğrudan yazmak
    kullanıcının diğer modlarını bozabilirdi; kopyalama adımı kullanıcıdadır (bilgi dosyası anlatır).
29. **Harf dönüştürme projeyi değiştirmez;** yalnızca üretilen modda uygulanır.
30. **"Eksik harf" çoğunluk kuralıyla belirlenir** (Latin statik fontların yarısından fazlasında yoksa),
    çünkü hangi metnin hangi fontla çizildiği dosyalardan güvenilir biçimde anlaşılamaz.
31. **Doğrulama:** üretilen her dosya, yazılmadan önce aynı eklentiyle yeniden açılır ve her metnin
    beklenen değerde olduğu karşılaştırılır; uyuşmazlıkta mod üretilmez.

### 4.6 M7 kararları

32. **Orijinal pak yeniden yazılmaz;** değişen dosyalar `_P` yama pak'ına konur. Hem GB'larca veriyi
    kopyalamaktan hem de pak'ın şifreleme/sıkıştırma/imza ayrıntılarına dokunmaktan kaçınılır.
33. **Yama pak'ı v7 eski dizin biçimindedir** (oyunun pak'ı daha yeni olsa bile); yeni dizinin yol
    özeti algoritması platforma göre değiştiği için yazılmadı. Motorların eski pak sürümlerini okuduğu
    varsayılır; gerçek oyunda doğrulanmalı (TECH_DEBT).
34. **Kaynak özetleri değiştirilmez;** Türkçe metin kaynak dil dosyasının yerine yazılır.
35. **Pak'ın tamamı belleğe alınmaz;** tarama dizini, aktarma ve dışa aktarma yalnızca ilgili girdiyi okur.

### 4.7 0.9.0 kararları (gerçek oyun uyumluluğu)

36. **Sıkıştırma katmanı veri bölgesinin üzerinde açılır,** bölümün değil; yamalı oyunda yamadan
    sonra, yamanın tablosuyla. Gerçek oyunda (base + update) doğrulandı.
37. **Seyrek base tek başına okunmaz;** eksik aralıklar sıfır döner ve RomFS anlamsız olur. Uygulama
    güncellemenin eklenmesini ister. Gerçek bir oyunla doğrulandı.
38. **Dil kodu yoldan da çıkarılır** (Unity "(en)", LMS "USen" klasörü, Unreal
    "Localization/<hedef>/<dil>/"). Bölgesiz kod o dilin her bölgesiyle eşleşir ("en" ↔ "en-us");
    iki kodun da bölgesi varsa tam eşleşme gerekir ("en-us" ≠ "en-eu"), çünkü LMS oyunları
    bölge başına ayrı dosya tutar.
39. **Önbelleğe açmadan önce disk alanı denetlenir;** geliştirme sırasında 38 GB'lık tanılama
    önbelleği diski doldurdu ve hata Türkçe değildi.

### 4.8 0.10.0 kararları (I2 Localization)

40. **I2, ayrı bir eklenti değil Unity eklentisinin parçasıdır;** tarama türü (`unity`) aynıdır ve
    bir dosyada hem string tablosu hem I2 kaynağı olabilir.
41. **Ham bayt çözümlemesi:** oyunlarda tip ağacı silindiği için UnityPy alanları okuyamaz. IL2CPP
    meta verisinden tip ağacı üretmek (Il2CppDumper benzeri) büyük ve kırılgan bir iş olurdu; I2'nin
    yapısı küçük olduğundan doğrudan çözülür ve sıkı doğrulamayla yanlış eşleşme engellenir.
42. **Tüm diller tek dosyada:** `extract` hangi sütunu okuyacağını aktarma bağlamındaki
    `SOURCE_LANGUAGE`'dan öğrenir; bağlam verilmezse (dışa aktarma doğrulaması) tüm sütunlar okunur.
    Anahtar dil kodunu içerdiği için geri yazma sütunu bilir.

### 4.9 0.11.0 kararları (GFMSG biçimi)

43. **Anahtar satır numarasıdır,** `.tbl`'deki ad değil: geri yazma yalnızca `.dat`'ı görür; adlar
    bağlam olarak `collect_context(data, path)` ile yan dosyadan toplanır (sözleşmeye `path` eklendi).
44. **Seçimler üç yer tutucuya açılır** (başı, ayraç, son); seçenek uzunlukları yazarken yeniden
    hesaplanır. Tek kod yapmak çevirmenin İngilizce "s" ekini Türkçe metne taşımasına yol açardı.
45. **Satırlar yeniden yazılırken sırayla ve 4 bayta hizalı dizilir;** gerçek dosyaların tümünde
    özgün düzen de böyledir (bayt bayt aynı çıktı ile doğrulandı).

### 4.10 0.12.0 kararları (font yaması, M8)

46. **Eksik harfler aynı fontun gliflerinden üretilir** (ı = i − nokta, ş = s + ç'nin çengeli…). Başka
    bir fonttan glif almak veya kaynak TTF'ten SDF üretmek yazı tipini değiştirirdi; statik fontların
    çoğunun kaynak TTF'i oyunda yoktur.
47. **Yalnızca ayırma gereken parçalar için SDF yeniden hesaplanır** (tam Öklid uzaklık dönüşümü, saf
    Python); birleştirme SDF'lerin en büyüğüyle yapılır. numpy eklenmedi: glif başına küçük alanlarda
    hız yeterli (Bir Unity oyununda 9 font, 50 harf: ~4 sn).
48. **Atlas dolarsa yukarı doğru büyütülür;** çoklu atlas (ikinci doku) TMP'nin çalışma anı
    malzeme yönetimine bağlı olduğu için seçilmedi.
49. **Font yaması isteğe bağlıdır** (Kontrol Et ekranında seçenek); açıkken harf dönüştürme yalnızca
    yamanın ekleyemediği harflere uygulanır (çoğunluk kuralı aynı).

### 4.11 0.13.0 kararları (arayüz)

50. **Sıralama modelde yapılır** (`TranslationModel.sort_by`, tek `list.sort`); `QSortFilterProxyModel.lessThan`
    her karşılaştırmada Python'a döndüğü için 34.000 satırda 5 sn sürüyordu. Proxy yalnızca süzgeç içindir.
51. **Satır yüksekliği tembel ölçülür:** `resizeRowsToContents` binlerce satırda arayüzü dondurur; ekrandaki
    satırlar ve çevresi (±8) ölçülür, kaydırınca sıradakiler. Kaydırma çubuğunun boyu bu yüzden yaklaşıktır.
52. **Sıralama anahtarı Türkçe alfabeye göredir** (`languages.sort_key`); `casefold` "çilek"i "dünya"dan
    sonraya atar. Büyük "I" ve "İ" noktalı "i" gibi sıralanır (oyun metinleri çoğunlukla İngilizcedir).
53. **Uzun açıklamalar `InfoButton` ile ipucuna taşınır;** sayfa başına görünen açıklama tek kısa cümledir
    (test: `test_pages_have_no_long_visible_descriptions`).
54. **Yazı boyutu uygulama düzeyindedir** (`apply_theme(..., font_size)`); QSS punto değerleri bu boyuttan
    çarpanla türetilir, böylece başlıklar ve gövde birlikte ölçeklenir.

### 4.12 0.14.0 kararları (hazır çeviri)

55. **Hazır çeviri yalnızca metin tablosundan alınır** (`translate/port.py`). Yamadaki font ve diğer
    paketler (Windows derlemesi) Switch dosyalarıyla uyumlu olmadığı için kullanılmaz; Switch fontları
    M8 font yamasıyla yamalanır.
56. **İçe aktarılan çeviriler "Makine" durumundadır.** Yeni bir "içe aktarıldı" durumu eklemek tabloyu ve
    dışa aktarmayı karmaşıklaştırırdı; "Makine" onaylananlara dokunmama ve gözden geçirme ihtiyacını zaten
    doğru anlatır. Kullanıcı satırları onayladıkça korunur.
57. **Kod uyuşmazlığı çeviri korumasını gevşetmez:** uyuşmayan satır yazılmaz (CLAUDE.md §4.3).

### 4.13 0.15.0 kararları (YCD paketi)

58. **YCD paketine yazma yerinde ve işaretçisizdir.** Dizin/boyut/özet alanları çözülmediği için dosya yeniden
    düzenlenmez; yalnızca çevrilen satırın dil sütunu betimleyicileri ve satırın kendi dizgi baytları güncellenir
    (dosya boyutu aynı). Çeviri verilmezse dosya bayt bayt aynıdır (round-trip, CLAUDE.md §4.1). Cihazda
    doğrulanana kadar deneyseldir; adım adım denenir (`docs/formats/pak-yc.md`).
59. **Dizgiler betimleyicilerden okunur.** Dosyadaki dizgi havuzu tekilleştirilmiştir; "sıradaki dizgi"
    varsayımı yanlış sütuna metin koyar. Her satır 16 baytlık betimleyici dizisi olarak ayrıştırılır (`pakyc/ycd.py`).
60. **Hazır çeviri kaynak metne bakar.** `ReadyTranslations.sources` verilmişse satır yalnızca yamanın
    dayandığı özgün metin projedekiyle eşitse eşleşir. Kimlikleri sürümler arasında kayabilen biçimlerde
    (YCD diyalog kimlikleri) yanlış satıra çeviri yazılmasını önler; Unity için kullanılmaz (kimlikler kalıcı).

### 4.14 0.19.0 kararları (PSB arşivleri)

61. **mdf anahtarı uygulamada yoktur, kullanıcının dökümünden bulunur.** CLAUDE.md §2 gereği uygulama
    şifreleme anahtarı içermez. PSB arşivi oyunlarının arşiv anahtarı oyunun kendi kodunda geçen bir dizgedir;
    `psb_archive.find_key`, kullanıcının ExeFS `main` kodundaki dizgeleri dener ve gerçek bir `.psb.m` dosyasını açanı
    seçer. Anahtar yalnızca bellekte tutulur; loglanmaz, hata mesajına ve proje dosyasına yazılmaz.
62. **Yeni bağımlılık yok.** MT19937 (init_by_array) ve MD5 standart kütüphaneyle/kendi kodumuzla;
    NSO açma için zaten var olan `lz4` kullanıldı. MT19937 uygulaması testte Python'un `random`
    modülüyle (aynı algoritma) karşılaştırılır.
63. **Değişmeyen mdf orijinal baytlarıyla kalır.** Oyunun zlib ayarları yeniden üretilemiyor; nested.py'deki
    Yaz0/ZSTD ile aynı ilke: içerik değişmediyse orijinal baytlar döner (round-trip, CLAUDE.md §4.1).
64. **PSB'ye metin yalnızca dizge tablosu üzerinden yazılır.** Kök ağaç yeniden serileştirilmez (bayt
    düzeyinde korunur); sonraki bölümler hizalamayı koruyarak kayar, sağlama toplamı yeniden hesaplanır.
    Gerçek dökümdeki 620 PSB'nin tamamında doğrulandı (`docs/formats/psb.md`).

### 4.15 0.21.0 kararları (PSB arşivi mod yazımı araştırması)

65. **8 GB'lık `.bin` yeniden yazılmaz; hedef "dizinden çıkar + gevşek dosya".** Oyunun betiği
    (`game_content.nut`) önce bağlı arşive, bulamazsa dosya sistemine bakıyor. Mod, yalnızca küçük
    `alldata.psb.m` (değişen üyelerin girdisi çıkarılmış) ve değişen üyeleri RomFS'te gevşek dosya olarak
    taşır. Yerel kodun aynı yolu izlediği **cihazda doğrulanana kadar** bu bir hipotezdir; arayüzde yoktur.
66. **Kök ağaç yalnızca dizin düzenlemek için yeniden kodlanır** (`psb.replace_root`). Ad ve dizge
    tabloları aynen kalır; yeni ad/dizge eklenemez. Tamsayı dizisi (`IntArray`, 0x0D–0x14) ile tamsayı
    listesi (0x20) ayrı tutulur. Gerçek `alldata`/`dlc_usa` dizinleri değişmeden yeniden kodlanınca
    orijinal baytlar birebir çıkıyor.

### 4.16 0.23.0 kararları (PSB metin çevirisi)

67. **Satırlar dizge başına tekilleştirilir.** PSB dizge tablosu aynı yazıyı bir kez tutar ve birden çok yerden
    başvurur; eklenti (`formats/psbtext`) bu yüzden ağaçtaki her konum yerine her *dizge* için bir satır çıkarır
    (anahtar: ilk geçtiği yol, bağlam: kullanıldığı anahtarlar). Çeviri dizgeyi yerinde değiştirir; kök ağacı yeniden
    serileştirmek gerekmez. Bir dizge metin dışı bir yerden de (kimlik) başvuruluyorsa çıkarılmaz.
68. **PSB üyeleri `ContentTree.code` ile açılır.** Arşiv anahtarı oyunun kodundan bulunduğundan görünüm, kodu tembel
    okuyan bir işlev taşır (önce güncelleme, sonra ana oyun). `MemberReader`, tarama, çıkarma ve dışa aktarma aynı
    yolu kullanır; yol biçimi `alldata.psb.m>system/config/menu_item.psb.m`.
69. **Dışa aktarma cihazda doğrulanan yöntemi kullanır** (docs/formats/psb.md): değişen üyelerin girdisi
    `alldata.psb.m`'den çıkarılır, üyeler (mdf kodlu) aynı yolda gevşek dosya olarak yazılır; `.bin` yazılmaz.
    Yazmadan önce her üye yeniden okunup doğrulanır ve yeni dizin özgün `.bin` ile açılarak sınanır.
70. **Harf dönüştürme gerekmedi.** Bu oyunun 21 menü fontunun hepsinde Türkçe harfler var (`psbtext`, ayrı bir
    `unsupported_letters` tanımlanmadı); kullanıcı yine de dışa aktarmada dönüştürmeyi seçebilir.

### 4.17 0.28.0 kararları (bağlamlı çeviri, redaksiyon, güncelleme)

71. **Bağlam, partiyi çevreleyen satırlarla verilir.** Model her partide sahnedeki önceki 8 ve sonraki 3 satırı
    (varsa çevirileriyle) "çevirme, yalnızca anla" diye görür. Parti yalnızca aynı dosyada art arda gelen
    satırlardan kurulur; arada atlanan satır varsa yeni parti başlar (atlanan satır bir sonraki partinin bağlamına
    girer). İstek sayısı biraz artar, karşılığında kısa cevaplar ve zamirler doğru çevrilir.
72. **Üç iş türü tek yürütücüde** (`runner`): çevir (bellek + tekilleştirme), yeniden çevir (bellek yok, her satır
    ayrı), redaksiyon (`Scene.revise`, maddelerde `current`). Yeni sağlayıcı sözleşmesi geriye uyumludur:
    `translate_batch(..., *, scene=None)`, `supports_instructions`.
73. **Bozuk sonuç geçerli çevirinin yerine yazılmaz.** Yeniden çeviride/düzeltmede sonucu denetimden geçmeyen satırın
    eski çevirisi korunur (`rejected`); çevirisi olmayan satırda eskisi gibi "Hatalı" yazılır.
74. **Otomatik düzeltme, redaksiyon işinin bir kullanımıdır:** satıra sorunun açıklaması (`fix`) ve ek kabul
    denetimi (`check`, QA denetimleri) verilir. Taşma bilerek kapsam dışı: kutuya sığıp sığmadığı oyunda görülmeden
    bilinemez.
75. **Güncelleme iki yoldan:** git deposu olan kurulumda `git fetch` + `git merge --ff-only` (git geçmişi bozulmaz,
    kimlik bilgisi git'in kendi yöneticisinden), diğerlerinde zip arşivi. Her iki yolda da uygulama, yeniden
    başlarken dosyalar açılmadan yapılır (Windows dosya kilitleri) ve başlatıcı paket değişikliklerini kurar.
    Yeni bağımlılık eklenmedi (`httpx`, `keyring`, `tomllib`, `zipfile`, `subprocess`).
76. **Güncelleme kaynağı master değil, sürümlerdir** (GitHub Releases / `vX.Y.Z` etiketleri). Master'daki ara
    commit'ler kullanıcıya gitmez. Release'i elle açmak gerekmez: `.github/workflows/release.yml`, master'a
    `pyproject.toml` sürümü değişmiş bir commit gelince etiketi ve release'i CHANGELOG bölümüyle oluşturur.
    Git yolunda etiketteki `pyproject.toml` sürümünün etiketle aynı olduğu doğrulanır.
77. **Çeviri geçmişi proje içinde, değişiklik başına bir satır** (`history`: önceki metin/durum/açıklama, yeni
    metin, iş kimliği). Yalnızca metni gerçekten değişen satırlar yazılır. İşin değişiklikleri "işten önceki ilk hâl
    → işin sonundaki son hâl" olarak gösterilir; geri alma eski durumu ve açıklamayı aynen geri koyar (ör. "orijinal
    değişti" uyarısı kaybolmaz) ve kendisi de geçmişe yazılır. Çeviri belleğine geri almada dokunulmaz.

### 4.18 0.31.0 kararları (çeviri editörü, Kontrol Et, proje güvenliği, CI, paket)

78. **Program düzeltmesi modelden önce gelir.** Kontrol Et'in otomatik düzeltmesi kesin sonucu olan işleri
    (boşluk, satır sonu sayısı → sözcük sınırından dengeli bölme, aynı türden kodların sırası, İngilizce kalmış
    sözlük terimi) kendisi yapar; satır yeniden denetlenir, yalnızca anlam gerektiren sorunlar modele gider.
    "Programla Düzelt" hiç model kullanmaz. Hatalı (ERROR) satırlar yerelde değiştirilmez; "gözden geçirin"
    işareti kaybolmasın diye olduğu gibi modele gider.
79. **Kaydedilmemiş proje için kurtarma kopyası** (`gui/recovery.py`): değişiklik varsa dakikada bir SQLite
    `backup` ile `%LOCALAPPDATA%/NXCeviri/kurtarma`'ya yazılır (bellekteki veritabanında milisaniyeler sürer;
    arka plan işleri projeye dokunmadığı için arayüz iş parçacığında güvenlidir). Her pencere kendi dosyasını
    `QLockFile` ile tutar; başka bir açık pencerenin kopyası "kalmış" sayılmaz, sahibi çökmüş kilit bayat
    sayılır. Kurtarılan kopya belleğe yüklenir (`Project.open_copy`), kurtarma dosyasına doğrudan yazılmaz.
    Kaydedilmiş projelerde gerekmez: her yazım zaten işlem içinde diske gider.
80. **CI Windows'ta** (`tests.yml`): testlerin bir kısmı Windows'a özgü (yazı tipleri, Kimlik Bilgisi
    Yöneticisi). ruff ve mypy sürümleri iş akışında sabitlenir; yeni sürümlerin yeni kuralları PR'ı
    beklenmedik biçimde kırmasın. Release testlere bağlıdır.
81. **Taşınabilir paket kendini güncellemez.** Çalışan `.exe` ve `_internal` dosyaları Windows'ta kilitli olduğu
    için paket yalnızca yeni sürüm olup olmadığına bakar ve sürüm sayfasını açar; kaynak kurulumundaki zip/git
    güncelleyicisi aynen kalır. Proje ve ayarlar paket klasöründe değil (`.nxproj` kullanıcının seçtiği yerde,
    ayarlar QSettings'te), bu yüzden klasörü yenisiyle değiştirmek güvenlidir.
82. **`main_window` bölünmesi adım adım** (TECH_DEBT 69): önce pencereye bağlı olmayan parçalar (iş iletileri,
    son projeler, kurtarma) ayrı modüllere alındı; pencere yöntemleri testlerde değiştirildiği için genel API
    korunur.
83. **Düzenleme paneli kaldırıldı, dış redaksiyon CSV ile** (0.31.6, ürün sahibi kararı): tablonun altındaki
    panel kullanılmıyordu ve ekranı kalabalıklaştırıyordu; çeviri hücrede düzenlenir. Uzun metinlerin redaksiyonu
    için CSV dışa/içe aktarma (`translate/csvio.py`) eklendi. Eşleşme yalnızca satır kimliğiyle; orijinal sütunu
    projedekiyle karşılaştırılır (başka projenin dosyası yazılmasın). Model çıktısıyla aynı onarım/temizlik
    uygulanır, kodu uymayan satır yazılmaz (CLAUDE.md 4.3: sessizce düzeltilmez, sayılıp gösterilir).
84. **Ctrl+Z bellekte bir geri alma yığınıyla** (`Project.undo`): her yazım işlemi değiştirdiği satırların önceki
    (metin, durum, açıklama) hâlini tutar; onay gibi yalnızca durum değiştiren işlemler de geri alınır. Kalıcı
    `history` tablosu yalnızca metin değişikliklerini tuttuğu için onay geri alınamazdı; şemayı değiştirmek
    yerine oturumluk yığın seçildi (son 100 işlem, yeniden taramada boşalır). Geri alma da geçmişe "geri alma"
    olarak yazılır. **Yinele** (`Project.redo`): geri alınan adım, geri alınmadan önceki hâliyle ayrı bir yığına (yine 100)
    konur; yeni yazım ve yeniden tarama yığını boşaltır. Yinele geçmişe işin kendi adıyla yazılır (durum sütunundaki iş
    işareti ve “Son işte değişenler” eski hâline döner); çeviri belleğine dokunmaz (`undo` gibi).
85. **Dış redaksiyonun varsayılanı üç sütunlu TXT** (0.31.7, ürün sahibi kararı): CSV'de modelin `id` ve
    `anahtar` sütunlarını yeniden yazması gerekiyordu; içerikte yoğun kontrol kodu ve tırnak olduğunda model
    çıktısı bozuluyordu. TXT'de `orijinal`, `çeviri`, `düzeltme` sütunları vardır; model yalnızca sonuncuyu
    doldurur, boş bıraktığı satır değişmez. Kimlik olmadığı için eşleşme `(orijinal, çeviri)` çiftiyle, çift
    tutmazsa benzersiz orijinal/çeviri metniyle yapılır; belirsiz satır yazılmaz. CSV biçimi o sürümde geriye uyum
    için seçenek olarak korundu. Hücre içi sekme/satır sonu `\t`, `\n`, `\\` olarak kaçışlanır; her kayıt tek satırdır.
    İçe aktarma yazmadan önce `ChangesDialog(preview=True)` ile satır satır fark önizlemesi gösterir; onaylanınca
    değişiklikler normal iş geçmişine (`csv-…`) yazılır, böylece aynı karşılaştırma sonradan da görülebilir ve
    geri alınabilir.
86. **Redaksiyon sonucu “Redakte” durumuna geçer; dışa aktarmada TXT/XLSX** (0.31.8, ürün sahibi kararı):
    dışarıdan gelen düzeltmeler makine çevirisi değildir; `Status.REDACTED` (“Redakte”) ile yazılır, ilerlemede
    çevrilmiş sayılır, oyuna aktarılır ve onaylanabilir. Onaylı satırlar da redakte edilebilir; içe aktarmayı
    kullanıcı açıkça onayladığı için `overwrite_approved=True` verilir. Redakte metin çeviri belleğine `human`
    kaynağıyla yazılır (makine çevirisi onu ezmez). Proje şeması 6’da `text_entries` CHECK kısıtı `redacted` ile
    yeniden kurulur; göç yabancı anahtarları geçici kapatıp `foreign_key_check` ile doğrular. Dışa aktarma
    penceresinde CSV’nin yerini XLSX alır; TXT varsayılan kalır. XLSX aynı sütunları kullanır ve hücrelerde gerçek
    satır sonu korur; dosya stdlib `zipfile`/`ElementTree` ile yazılır (yeni bağımlılık yok). Eski CSV dosyaları
    yalnızca içe aktarmada okunur.
87. **Dış redaksiyon dosyalarına salt okunur `grup` sütunu** (0.31.9, ürün sahibi kararı): dış redaksiyon
    modelinin metnin bağlamını bilmesi için TXT/XLSX’e dördüncü sütun olarak `grup` eklenir (`row_group`: Unity
    koleksiyonu ya da dosya adı). Ör. “UI” satırı menü/düğme, “Dialogue” satırı konuşma cümlesidir; model üslubu
    buna göre seçer (menü etiketi kısa olur, diyalog cümle gibi redakte edilir). Sütun en sona konur: model onu
    düşürse bile `düzeltme` kaymaz, eski üç sütunlu dosyalar da aynı düzenle okunur. Başlık varsa sütun sırası
    başlıktan çözülür; `grup` hiçbir zaman çeviriye yazılmaz, yalnızca aynı `(orijinal, çeviri)` çifti birden çok
    kez geçtiğinde doğru satırı seçmek için ipucu olur.
88. **Satır sonları tabloda simge değil gerçek satır sonu** (0.31.10, ürün sahibi kararı): çeviri tablosu ve
    “Kontrol Et” bulgu listesi `\n` karakterini “⏎” ile gösteriyordu; yoğun satır sonu olan metinler okunaksız
    görünüyordu. Artık hücre metni gerçek satır sonu içerir; yükseklik `wordWrap`/`resizeRowsToContents` ile
    ölçülür. Çeviri tablosunda kaydırma kapalıyken satırlar tek satır yüksekliğinde kaldığı için satır sonları
    boşluğa döner, böylece metnin devamı kaybolmaz. Kontrol kodları (⟦n⟧) görünür kalır.
89. **Dış redaksiyon önizlemesinde satır satır kabul, ret ve düzenleme** (0.31.11, ürün sahibi kararı):
    içe aktarma artık ya hep ya hiç değildir. Önizleme tablosunda ilk sütun “Yaz” işaretidir (varsayılan açık);
    işareti kaldırılan satırın mevcut çevirisi ve durumu değişmez. “Yeni” sütunu çift tıklama/F2 ile düzenlenir:
    hücrede HTML farkı çizilir ama düzenleyiciye `NEW_TEXT_ROLE` içindeki düz metin gider, böylece kullanıcı HTML
    etiketiyle uğraşmaz ve satır sonları korunur. Düzenlenen metin model çıktısıyla aynı `prepare_correction`
    (`repair_codes` → `clean_output` → `match_edges` → `placeholders.problems`) denetiminden geçer; boş veya
    kontrol kodu uymayan satır varken `ChangesDialog.accept()` kapanmaz, sorun satır adıyla gösterilir. Yalnızca
    işaretli ve gerçekten değişen satırlar `Redakte` durumuyla yazılır; `overwrite_approved=True` korunur.
90. **Dış çeviri, dış redaksiyonla aynı boru hattını kullanır** (0.31.12, ürün sahibi kararı): çeviri işini
    dışarıya vermek için ayrı bir biçim uydurmak yerine redaksiyon tablosunun aynısı kullanılır; yalnızca üçüncü
    sütunun adı `yeni çeviri` olur (`TRANSLATION_COLUMNS`). Böylece `plan_import`, `_TxtMatcher`, hazır istem
    onarımı ve `ChangesDialog(preview=True)` olduğu gibi çalışır; `yeni çeviri`/`yeni ceviri` düzeltme sütunu
    olarak tanınır. Dışa aktarmada dosya adı `…_ceviri.*` olur, içe aktarmada satırlar **Makine** durumu ve
    `translation-…` iş kimliğiyle yazılır (redaksiyondaki `Redakte`/`csv-…` karşılığı). Eski üç sütunlu ve
    redaksiyon dosyaları geriye uyumlu kalır.
91. **Değiştirilen Addressables paketlerinin katalog CRC'si sıfırlanır** (0.31.13, gerçek arıza: bir Unity oyunu):
    Addressables `m_Crc != 0` ise yerel paketi `AssetBundle.LoadFromFileAsync(path, crc)` ile açar; CRC
    tutmazsa paket yüklenmez. Metin bundle'ı yeniden yazıldığı için CRC eşleşmez. Dışa aktarma,
    `catalog.json` → `m_ExtraDataString` (base64 → `SerializationUtilities` kayıtları) içinde **özgün
    boyutu değişen bir dosyayla eşleşen** ve CRC'si sıfırdan farklı kayıtların değerini `0` yapar. Kayıt
    uzunluğu korunur (`"m_Crc":N` → `0` + boşluk) çünkü `m_EntryDataString` konumları kayıtlara bayt
    ofsetiyle bağlıdır; katalogdaki diğer baytlara dokunulmaz. CRC 0 denetimi kapatır, cihazda/emülatörde
    paket normal yüklenir. Düzeltilmiş katalog moda eklenir; `catalog.hash` varsa ayrıca güncellenmez
    (bu oyunda yok). Katalog yoksa veya ayrıştırılamazsa uyarı verilir, dışa aktarma durmaz.
92. **Bul ve değiştirme ayrı bir iş değil, mevcut pencerenin genişletilmesidir** (0.31.14, ürün sahibi
    isteği: “toplu değiştirme” ve “tek tek değiştirmek istiyorum”): Ctrl+H / Düzen → Bul ve Değiştir… zaten
    vardı; ikinci bir akış eklemek yerine `FindReplaceDialog` kapsam seçimi (tüm satırlar / tabloda görünenler
    / seçili satırlar), düzenli ifade, tek tek gezinme ve önizleme kazandı. `plan_replace` saf kalır (projeye
    yazmaz); kapsam yalnızca hangi satır listesinin verildiğini belirler. Düzenli ifade yalnızca `regex=True`
    iken derlenir; düz metin `re.escape` ile aranır ve “yerine” metni `\1` gibi dizileri grup başvurusu
    saymaz (kullanıcı düz metin bekler). Geçersiz ifade `ReplacePlan.error` ile pencere içinde gösterilir,
    istisna dışarı sızmaz. Kontrol kodu (⟦1⟧) koruması iki modda da aynıdır: değişiklik kodu bozacaksa satır
    atlanır ve sayılır. Onaylı satırlar onaylı kalır, değişiklik geçmişe yazılır.
    **Tek tek yazım** için pencere projeye doğrudan erişmez: `main_window.find_replace` bir `apply` geri
    çağrısı verir; “Sonrakini Değiştir” yalnızca o satırı `set_translations` ile yazar, dönen güncel satırları
    pencere kendi kopyalarına işler ve kalan eşleşmeleri yeniden hesaplar (imleç aynı konumda kalır → sıradaki
    eşleşme). Tüm parçalar aynı `replace-…` iş kimliğini kullanır; `Project._push_undo` aynı iş kimliğindeki
    ardışık yazımları birleştirdiği için **Ctrl+Z hepsini tek işlem** olarak geri alır. “Tümünü Değiştir”
    kalan eşleşmeleri tek çağrıda yazar. Pencere içi Ctrl+F “Aranan” alanına, F3 sonraki eşleşmeye gider.

### 4.19 Ayarlar nerede durur

| Ayar | Yer | Anahtar |
|---|---|---|
| Tema, yazı boyutu | QSettings (kullanıcı) | `ui/theme`, `ui/font_size` |
| Son klasörler | QSettings | `ui/last_dir`, `ui/project_dir`, `import/dir`, `export/dir`, `csv/dir` |
| Son projeler | QSettings | `ui/recent_projects` |
| Anahtar dosyalarının **yolu** (içerik asla) | QSettings | `keys/prod`, `keys/title` |
| Çeviri sağlayıcısı, Ollama adresi/modeli | QSettings | `translate/provider`, `ollama/url`, `ollama/model` |
| Tablo görünümü (sütunlar, satır kaydırma, takip, sorun renkleri) | QSettings | `translate/*` |
| API anahtarları (DeepL, GitHub güncelleme) | Windows Kimlik Bilgisi Yöneticisi (keyring) | — |
| Kaynak dili, oyun notları, son redaksiyon talimatı | Proje (`.nxproj`, `settings` tablosu) | `source_language`, `translation_notes`, `revise_instruction` |
| Harf dönüştürme, font yaması, font tarama sonucu | Proje | `transliterate_mode`, `font_patch`, `font_*` |
| Metin sığdırma (sınırlar, dosya sınırları, temizlik seçenekleri, açık/kapalı), kod türleri | Proje (`settings`, JSON) | `fit_config`, `code_kinds` |
| Sözlük, büyük harf kuralları, çeviri geçmişi | Proje (kendi tabloları) | — |

Kural: oyuna/projeye özgü olan proje dosyasında (başka bilgisayara taşınınca birlikte gider), kişiye/bilgisayara
özgü olan QSettings'te, gizli olan keyring'de.

### 4.20 0.32.0 kararları (metin sığdırma)

Ayrıntılı tasarım: `docs/superpowers/specs/2026-10-31-metin-sigdirma-design.md`.

- **Üç yeni çekirdek modül, her birinin nedeni:** `codekinds.py` kontrol kodunun metne etkisini (böler mi, yer kaplar mı)
  etiketten bağımsız bir türe indirger, böylece formatlar değişse de bölme mantığı aynı kalır; `fit.py` bölme ve
  sorun bulmayı proje/arayüz bilmeden, saf işlevler olarak tutar (kolay test, idempotent); `fitconfig.py` ayarın
  saklanmasını ve “orijinalden öğren” ölçümünü tek yerde toplar, `qa/checks` ve `qa/autofix` yalnızca `FitConfig` alır.
- **Sınır piksel değil karakterdir.** Piksel ölçmek oyun fontunu ve onun ölçülerini gerektirir; çoğu formatta font
  erişilemez ya da dinamiktir. Karakter sınırı fontsuz çalışır, kullanıcı oyundaki gerçek taşmadan ayarlar.
  Kodun görünen genişliği türden gelir (değişken `variable_width`, sembol 1, biçim 0).
- **Sığdırma sayfa sonu kodlarına asla dokunmaz.** Sayfalar sayfa sonu kodlarında ayrılır; yalnızca sayfanın içi
  yeniden bölünür. Satır sonu kodlu sayfada kod sayısı ve sırası sabit kalır (yalnızca yerleri değişir); düz satır sonu karakteri (`\n`) ve satır
  sonu kodunu karıştıran sayfa atlanır. İçinde boş satır (paragraf arası) ya da sekme (girinti) olan sayfa da
  bilinçli biçimlendirilmiş sayılır ve değiştirilmeden bırakılır (bulgusu raporlanır). Yeniden bölme kod sırasını
  (yanındaki diğer kodlara göre bile) değiştirecekse sayfa onarılmaz; yerel düzeltme `placeholders.problems`'u
  kötüleştirirse çeviri olduğu gibi kalır.
- **Sınır yoksa sığdırma yoktur:** `fit_config` içindeki `enabled` kapalıyken ya da kural tanımsızken yeni denetimler ve
  onarımlar çalışmaz; kural varken eski “Satır sonu” denetimi o satır için kapanır (satır sayısını sınır belirler).
- **Sığmayanlar** yerelde değişmeden kalır ve sınır bilgisiyle kısaltılmak üzere model akışına (`plan.model_rows`) gider;
  sonuç aynı denetimden geçmezse eski çeviri korunur. (`FixPlan.skipped` yalnızca otomatik düzeltilmeyen eski türleri sayar.)
- **Yeni bağımlılık eklenmedi.**

### 4.21 0.34.0 kararları (arayüz altyapısı)

Ayrıntılı tasarım: `docs/superpowers/specs/2026-10-31-arayuz-yenileme-design.md`.

- **Simgeler Lucide, SF Symbols değil.** Apple'ın SF Symbols lisansı Apple dışı platformlarda kullanımı açıkça
  kapsamıyor; Lucide ISC lisanslıdır ve ticari kullanıma açıktır. SVG dosyaları sürüm sabitlenerek geliştirme
  sırasında bir kez alınır (`gui/icons/README.md`), çalışma sırasında indirme yoktur ve yeni bağımlılık eklenmedi
  (`QtSvg` PySide6 ile gelir). Dosyalar `pyproject.toml` `package-data` ile paketlenir (taşınabilir paket, M9).
- **Simge rengi çizim anında üretilir.** `icon(ad)` geçerli tema belirtecinden renklenir ve önbelleğe alınır;
  düğme/eylem/etiketler `bind_icon` ile kaydedilir, `apply_theme` sonunda `refresh_icons()` hepsini yeniler
  (silinmiş Qt nesneleri sessizce atılır). Kenar çubuğu öğeleri bağlanamadığı için simgesini temsilci her çizimde üretir.
- **`MainWindow.nav` hâlâ bir `QListWidget`** (`StepNav` alt sınıfı): mevcut kod ve testler (`setCurrentRow`,
  `currentRowChanged`, öğe bayrakları) değişmeden çalışır. Adımlar numarasızdır; sıra zaten görünür.
- **“i” düğmeleri kalktı, metin kalmadı:** `title_row(info=…)` ve `Card(hint=…)` metni başlık etiketinin ipucudur.
- **Rozetler ve durum çubuğu tablo modelinden okunur,** bu yüzden `_commit_translations` model satırlarını rozetler
  hesaplanmadan önce günceller (aksi hâlde bir düzenleme geride kalırdı).
- **Windows vurgu rengi** `QStyleHints.accentColor` PySide6'da açık olmadığından sistem paletinin `Accent` rolünden,
  uygulama kendi paletini kurmadan önce okunur ve saklanır; kontrast yetersizse sabit renk kullanılır.

### 4.22 0.35.0 kararları (çeviri sayfası)

Ayrıntılı tasarım: `docs/superpowers/specs/2026-10-31-ceviri-sayfasi-design.md`.

- **Çizim ≠ veri.** Semboller, çipler ve hiza yalnızca görüntüdür (`textmarks`); kopyalama, kayıt ve düzenleme ham metin
  (`⟦n⟧` dahil) üzerindedir. Çip, ham kodun üstünde bir boyamadır; panelde kodlar ham kalır ve `ExtraSelection` ile renklenir.
- **Üç yerde tek eylem.** Semboller, hiza ve panel konumu `ViewActions` içindeki `QAction`lardır; araç çubuğu düğmeleri
  (`setDefaultAction`), Görünüm menüsü ve durum çubuğundaki ¶ düğmesi aynı nesneleri paylaşır, böylece biri değişince
  hepsi değişir ve kısayollar bir kez tanımlanır. Değerler `QSettings`te (`translate/symbols|align|pane|pane_sizes_*`).
- **Panel kaydı `TranslationModel.apply` yolundan geçer** (geçmiş, geri alma, durum hesabı aynen); panel veri tutmaz,
  `commit_requested(satır_kimliği, metin)` yayar. Bekleyen metin satır kimliğiyle kaydedilir: süzgeç/sıralama satırı
  listeden çıkarsa bile başka satıra yazılmaz. `MainWindow` proje değiştirirken önce `flush_pending()` çağırır
  (satır kimlikleri başka projeye karışmasın).
- **Yerleşim:** tablo kartı ve panel bir `QSplitter`te. Kullanıcının seçimi (`view_actions.pane`) tercihtir; o an
  uygulanan yer `_wanted_pane_layout` ile bulunur: "sağda" 1000 px altında altta; altta sığmıyorsa (tablo kartının ve panelin
  en küçük ölçüleri toplamı yetmiyorsa) genişlik yeterliyse sağda; ikisi de yetmiyorsa gizli. Yükseklik ölçümü yerleşim
  oturduktan sonra (zamanlayıcıyla) yapılır; ilk yerleşimin bayat ölçüsü kullanılmaz.
- **Hız:** üretilen HTML (satır kimliği, alan, metin, bayraklar, tema) sınırlı bir ön bellekte tutulur (en az kullanılan
  atılır); boyut ölçümü yalnızca görünen satırlar ve çevresinde yapılır.
- **Bilinen ortam sınırı:** `pytest-qt`/`QTest` Windows'ta ASCII dışı tuşlarda süreci çökertir; panel testleri ASCII yazar.
- **Yeni bağımlılık eklenmedi.**

### 4.23 0.36.0 kararları (NNI arşivi, CPK/FMSB biçimi)

93. **Büyük arşivlerin üyeleri "dizin + üye" okunur** (PSB arşivi ve pak ile aynı yol): `data-en.ni>LOC/EN/…/X.XSO`,
    `<oyun>_US.CPK>MsgSheet/X.fms`. Tarama yalnızca dizini okur ve üyeleri adından seçer (XSO yalnızca `LOC/`
    altında; CPK'da `.fms`), böylece 2,9 GB'lık `<oyun>.CPK` taranırken içeriği okunmaz.
94. **NNI yazımı orijinal `.na`'ya ekleme yapar**, yeniden paketlemez: kayıtların yeri değişmez, yalnızca değişen
    üyelerin ofset/boyutu yeni yeri gösterir. Oyunun arşiv yerine gevşek dosya okuyup okumadığı bilinmediği için
    (`docs/formats/nni.md`) mod `.ni` + `.na` çiftini taşır.
95. **CPK yazımı değişen dosyaları sıkıştırmadan koyar** (CRILAYLA kodlayıcı yazılmadı): Rusça topluluk yamasında
    da tüm dosyalar sıkıştırılmamış ve oyun kabul ediyor. Tablolar yeniden serileştirilmez; yalnızca sayısal hücreler
    yerinde değişir, böylece değişiklik yoksa çıktı bayt bayt aynıdır. 512 MB üstü arşiv yeniden yazılmaz.
96. **XSO'da metin/kimlik ayrımı Japonca kopyayla yapılır** (`collect_context`): sezgisel kural tek sözcüklü
    metinleri (`Yes`, `Cancel`) kimliklerden (`Battle`, `Back`) ayıramıyordu. Japonca kopya yoksa sezgisel kurala
    düşülür. Dışa aktarma doğrulamasında bağlam olmadığından tüm metin dizgeleri okunur (anahtar = sıra numarası).
97. **Fontta olmayan harfler eklenti bildirimiyle dönüştürülür** (`unsupported_letters = "ğĞşŞıİ"`, her iki oyun):
    NNI oyununda BMFont glif tablosundan doğrulandı; CPK/FMSB oyununda kanıt dolaylı (Rusça yamanın Latin-1 hilesi).

### 4.24 0.37.0 kararları (diğer sayfalar)

Ayrıntılı tasarım: `docs/superpowers/specs/2026-11-01-diger-sayfalar-design.md`.

- **Ana eylem başlıkta.** Dört sayfa `PageHeader` kullanır: simge + başlık, durum çipi, sağda eylemler (ana eylem en
  sağda). Kontrol Et'te eylemler sekmeye bağlı olduğundan her sekmenin üstünde bir `ActionBar` vardır.
- **Kalıcı durum çipte, anlık sonuç yerinde.** Sayfanın genel durumu (dışa aktarma sorunları, tarama uyarıları,
  devam edilememe nedeni) başlıktaki `StatusChip`te kısa metin + açılır ayrıntıdır. Kullanıcının az önce yaptığı işin
  sonucu (anahtar/dosya hatası, düzeltme sonucu, mod oluşturuldu) yerindeki `Banner`da kalır.
- **Nesne adları korundu** (`next_button`, `import_button`, `export_button`, `check_button`, `summary` …); yalnızca
  yerleri değişti, böylece `main_window.py` bağlantıları ve testler aynı kaldı. Değişen tek bağlantı:
  `ExportPage.version_banner` → `ExportPage.set_notes(sorunlar, uyarılar)`.
- **Tarama başlığı duruma göre:** `ScanPage._sync_header` her durumda (boş, yükleniyor, hata, rapor) yalnızca o duruma
  ait eylemleri gösterir; rapor görünümü durumu `status_changed` sinyaliyle sayfaya bildirir.
- **Yeni bağımlılık ve yeni simge eklenmedi.**

### 4.25 0.39.0 kararları (NNI arşivi: altyazı, yazı tipi, grafik)

98. **Eklentiler metinden bağımsız dosya üretebilir** (`derived_files(read, files, game_dir) -> Derived`): dışa
    aktarma bunları oyun başına bir kez çağırır (aynı işlevi paylaşan NNI metni ve altyazı eklentileri tek çağrı olur).
    Serbest dosyalar moda eklenir, arşiv üyeleri `_export_member_archive(extra=…)` ile metin değişiklikleriyle aynı
    yeniden kurulumda birleşir; böylece `data-en.ni/.na` çifti tek kez üretilir.
99. **Eksik harfler yazı tipinin kendi glifleriyle türetilir** (BMFont): `ı` = `i`nin gövdesi, `İ` = `I` + `i`nin
    noktası, `ş` = `s` + `ç`nin sedili, `ğ` = `g` + küçültülmüş noktalardan yaylanan breve. Parçalar "açık olan kazanır"
    ile birleştirilir; böylece dolgu rengi, dış çizgi ve gölge (glif kutusu gölge payı içerdiğinden `yoffset` farkları
    değil, opak çekirdek satırları ölçüt) aynı kalır. TTF'den çizim denendi, dış çizgi/gölge efektini yeniden üretmek
    gerektiği için bırakıldı. Yeni bağımlılık yok (yalnızca Pillow).
100. **NNI metin eklentileri harf dönüştürmez** (`unsupported_letters = ""`): yazı tipi yaması dışa aktarmada her zaman
    çalışır. Yama bir yazı tipine uygulanamazsa uyarı verilir (sessizce dönüştürmeye geçilmez).
101. **Grafik çevirisi dosya klasörüyle yapılır** (FSD/MSG ile aynı düzen): `orijinal/` (uygulama üretir) ve `temiz/`
    (kullanıcı); yalnızca özgünden farklı olanlar yerleştirilir. DDS yazımı özgün başlığı, biçimi (BC3/BC1) ve mip
    sayısını korur ve boyutu doğrular. Ana arşivdeki resimler 946 MB'lık `data.na` kopyasını gerektirdiğinden
    kapsam dışı (TECH_DEBT 74).
102. **XML'de satır sonu gerçek satır sonudur**; `\n` dönüşümü yalnızca XSO dizgelerindedir (`tokenize(…,
    escaped_newlines=False)`).

### 4.26 0.40.0 kararları (uydurma koruması, tutarlılık, anahtar menüsü)

103. **Yeni çevirideki uydurma belirtisi satırı engellemez, işaretler** (`guards.translation_problems`): kodlar
    yerindeyse çeviri bir yeniden denemeden sonra yazılır ve QA'da `suspicious` uyarısı olur. Gerekçe: boş kalan satır
    oyunda İngilizce görünür; şüpheli ama okunur bir çeviri kullanıcı tarafından tek bakışta düzeltilir. "Hatalı"
    durumu yalnızca kontrol kodu bozukluğuna ayrılır (dışa aktarmayı durdurur). Var olan çevirinin yerine yazılacak
    sonuçta eski kural sürer: belirti varsa eski çeviri korunur.
104. **Tutarlılık denetimi tam eşleşmeye bakar** (`checks.consistency_issues`): aynı kaynak, farklı çeviri. Benzer
    cümleler (bulanık eşleşme) yanlış alarm üretir ve gömme modeli gerektirir; kapsam dışı. Farklı biçimlerin hepsi
    onaylıysa kullanıcının bilinçli seçimi sayılır.
105. **Ollama: sıcaklık 0,2 ve sabit `seed`; oyun notları sistem isteminde.** Sabit tohum aynı istemi aynı yanıta
    bağlar; yeniden denemede istem (`fix`) değiştiği için sonuç yine değişebilir. Notların sistem isteminde durması
    hem talimata uyumu artırır hem Ollama'nın değişmeyen istem başını önbellekten okumasını sağlar.
106. **Anahtarlar menüde, durumu durum çubuğunda.** Oyunu Ekle sayfasındaki anahtar kartı yalnızca geçerli anahtar
    yokken görünür (ilk açılışta oradan seçilmesi gerekir).

### 4.27 0.41.0 kararları (sözlük XLSX, lore, terim önerisi, noktalama)

107. **Lore ayrı tablo değil, çevirisiz sözlük maddesidir.** Sözlük zaten "partide geçen ada notu ekle" mantığıyla
    çalışıyordu (`relevant_terms`); ayrı bir yapı aynı eşleşmeyi tekrar ederdi. Çeviri boşsa madde Ollama'ya
    `{"term", "note"}` olarak gider, istem bunu bilgi olarak kullanmasını söyler; DeepL sözlüğüne ve QA sözlük
    denetimine girmez.
108. **Sözlük XLSX'i iki sütundur** (ürün sahibinin isteği); notlar dışa aktarılmaz, içe aktarmada üçüncü sütun
    varsa okunur. Yazıcı/okuyucu çeviri tablolarınınkidir (`csvio.table_xlsx`, `csvio.xlsx_table`); yeni bağımlılık yok.
109. **Terim önerisinde adayları program, karşılıkları model bulur.** Modelden serbestçe terim listesi istemek
    uydurma ad ve gereksiz sözcük üretir; program en az iki kez, cümle ortasında büyük harfle geçen dizileri seçer,
    model listede olmayanı döndüremez. Öneriler onay penceresinden geçmeden yazılmaz. Yalnızca Ollama
    (`OllamaProvider.chat_json`); DeepL serbest istem desteklemez.
110. **Sondaki fazla noktalama yerel düzeltilir, metin içindeki yalnızca uyarıdır.** Orijinal noktalamasız biterken
    eklenen işaret (menü ve düğme metinlerinde sık) güvenle atılabilir; cümle içindeki ünlem/soru Türkçede bazen
    doğrudur, otomatik silinmez ve kabul denetimini (`GUARDED_KINDS`) etkilemez.

### 4.28 0.42.0 kararları (çeviri talimatı)

111. **Çeviri talimatı redaksiyon talimatıyla aynı alanı kullanmaz** (`translate_instruction` / `revise_instruction`):
    biri "bu satırlar menü metni" gibi yönlendirme, öteki mevcut çeviriyi düzelten emirdir; aynı kutuda karışırsa
    redaksiyon metni yeni çeviriye sızar. Kutu iş türüne göre iki metin arasında geçiş yapar.
112. **Çeviri talimatı sistem istemindedir, redaksiyonunki kullanıcı mesajındadır.** Çeviri talimatı iş boyunca
    sabit olduğu için oyun notları gibi sistem istemine girer; "kurallar her zaman üstündür" cümlesi kod ve JSON
    kurallarının talimatla ezilmesini önler. Dosya başına otomatik talimat yapılmadı: kapsam olarak grup seçimi aynı
    işi görünür biçimde yapar.

### 4.29 0.43.0 kararları (yazım denetimi)

113. **Yazım sözlüğü Bloom süzgeci olarak paketlenir, Hunspell kütüphanesi kullanılmaz.** hunspell-tr (TDD, MPL-2.0)
    her kökün yanında geçerli ekleri tek tek sayar: 75.909 kök, 59.266 ek, ~6,1 milyon biçim. `spylls` (saf Python
    Hunspell, MIT) denendi: doğru çalıştı (aynı kesinlik/duyarlılık) ama yükleme 8,6 sn ve ~750 MB bellek, ayrıca
    2021'den beri bakımsız (CLAUDE.md §3). Kök + serbest ek kümesi (bayraksız) duyarlılığı %67,8'e düşürdü. Her
    biçim `packaging/build_spell_filter.py` ile %0,1 yanlış olumlu oranlı 11 MB'lık süzgece yazıldı; yükleme 36 ms,
    ölçüt sonucu birebir korundu. Süzgeç MPL-2.0 kapsamındadır (README ve lisans metni `assets/spell`'de); uygulamanın
    geri kalanı etkilenmez.
114. **Yanlış alarmı azaltan sayılmayan sözcükler:** kaynakta geçenler (korunan adlar), cümle ortasında büyük harfliler
    (özel ad), kesme işaretliler, kısaltmalar, oyun sözlüğü terimleri. Gerekçe: oyun metinleri özel ad doludur;
    her biri için kullanıcıyı "Sözlüğe ekle"ye zorlamak denetimi kullanılmaz kılar.
115. **Kullanıcı sözlüğü uygulama düzeyindedir, projede değil:** bir kez kabul edilen sözcük her projede geçerlidir
    (`%LOCALAPPDATA%\NXCeviri\yazim-sozlugu.txt`, atomik yazım). Oyun terimleri için proje sözlüğü
    (`Sözlük…`) ayrıdır.

### 4.30 0.44.0 kararları (WAD/LIN biçimi)

116. **WAD yazımı arşivin tamamını bellekte kurar** (50 MB): üyeler aynı sırayla yeniden dizilir, başlık ve klasör
    tablosu aynen kalır, yalnızca dosya tablosundaki boyut/ofset alanları yerinde güncellenir. Değişiklik yoksa çıktı
    bayt bayt aynıdır. 1 GB üstü arşiv yeniden yazılmaz (açık hata). Mod tek dosyadır (WAD arşivi).
117. **LIN/PAK metni dizge sırasıyla anahtarlanır**; betik paketlerinde `<öğe>.<dizge>`. Betik bölümü (komutlar) hiç
    yeniden yazılmaz: komutlar dizgelere sıra numarasıyla başvurur, bu yüzden metin uzunluğu serbesttir.
118. **"0 metin" artık hatadır** (`pipeline.extract_texts`): hiçbir dosyadan satır çıkmadıysa kullanıcıya açıklayıcı hata
     gösterilir; "0 dosyadan metinler aktarıldı" başarısı yanıltıcıydı.

### 4.31 0.45.0 kararları (Unity SerializeReference biçimi)

119. **Unity SerializeReference `Localization`'ı Unity eklentisinin içinde, ham bayttan okunur** (`serializeref.py`; `i2`/`locoliser` ile aynı yol):
     tip ağacı yok, nesne `[SerializeReference]` kayıt defteri. Yapı kesin doğrulanır (kayıt defteri nesnenin son baytında
     bitmeli, kimlikler tutarlı olmalı); doğrulanamayan nesne hiç okunmaz. Değişiklik yokken bayt bayt aynı yazılır.
120. **İki düzen tek ayrıştırıcıda** (v0 adlı, güncelleme adsız): ikisi sırayla denenir, tüm kayıt defterini bitiren kazanır.
121. **Türkçe aktarılan dil yuvasına yazılır** (varsayılan İngilizce, Rusça yamayla aynı); aynı dili taşıyan ikinci yuvaya yalnızca
     özgün metni özdeş olan satırlar yansıtılır. Yuva anahtarı sıradır, böylece oyun güncellenince eşleşme korunur.

### 4.32 0.46.0 kararları (sadeleştirme)

122. **Sık yol önde, gerisi bir seviye altta** (SKILL.md “Simplicity”): sayfa başına tek birincil düğme, ikincil
    eylemler tek menüde; aynı işi yapan ikinci yol (araç çubuğu simgeleri ↔ Görünüm menüsü) kaldırıldı.
123. **Uyarı yalnızca işe yarıyorsa uyarıdır:** “Fazla noktalama” silindi; “Yazım” bilgi düzeyine indi (kenar çubuğu
    sayacına girmez, süzgeçle görülür). Gerekçe: 608 uyarının çoğu gürültüydü, gerçek hatalar kayboluyordu.

### 4.33 0.47.0 kararları (NXTR, seçmeli düzeltme, grup sınırları)

124. **Ad yalnızca kullanıcıya görünen yerde değişti (NXTR).** Python paketi `nxceviri`, QSettings adı `NXCeviri`,
    `%LOCALAPPDATA%\NXCeviri`, keyring hizmet adı, `.nxproj` ve kaynak kurulum başlatıcısı (`NX Ceviri Studyosu.bat`,
    `update.py` buna bağlı) aynı kaldı: güncelleyen kullanıcının ayarı, anahtarı ve projesi kaybolmaz.
125. **Kontrol Et'te model ile düzeltme kaldırıldı (ürün sahibi kararı, 2026-11-02).** Düzeltme yalnızca deterministik,
    tür tür seçilir (`plan_fixes(kinds=…)`), tek iş olarak geçmişe yazılır ve rapor "Son İşin Değişiklikleri" penceresidir
    (Düzeltme sütunu). Biçim düzeltmeleri çeviri belleğine yazılmaz (`set_translations(remember=False)`).
126. **Kod sırası düzeltmesi yalnızca değer taşımayan kodlarda** (biçim/renk, satır/sayfa sonu) ve aynı tür + aynı etiket
    içinde yapılır; değişkenler başka koda çevrilmez (anlam bozulur: eşya adı kişi adının yerine geçer).
127. **"Hatalı satırları da aktar" — CLAUDE.md §4.3 için ürün sahibinin bilinçli istisnası (2026-11-02).** Varsayılan kapalı;
    kapalıyken dışa aktarma bayt bayt eskisi gibi. Açıkken: kontrol kodu bozuk satırlar (`placeholders.problems`) hiç
    denenmez, orijinal kalır; sorunsuz hatalı satırlar (ör. kaynağı değişmiş) denenir, eklenti reddederse ikili bölmeyle
    ayıklanır (iptal edilebilir). Tek gevşetme: yalnızca SIRASI farklı ve yer değiştiren kodların hepsi tek başına duran
    değişken/simge olan satırlarda sıra denetimi o dosyanın inject'i için kapatılır (`placeholders.tolerate_reorder`);
    aç/kapa çiftleri ve satır sonları gevşetilmez. Satır tabloda "Hatalı" görünmeye devam eder.
128. **Grup kuralları (`fit_config.groups`) gerçek gruplar içindir:** tek dosyanın taban adından ibaret gruplar öğrenilmez
    ve dosya kuralı olan satırda taban-ad grup kuralı yok sayılır (kullanıcının dosya kuralı sessizce ezilmesin).

### 4.34 0.48.0 kararları (ajan destekli yerelleştirme)

129. **Bilgi md dosyalarında, giriş `AGENTS.md`.** Ajanların çoğu `AGENTS.md`'yi kendiliğinden okur; `CLAUDE.md` ve
    `GEMINI.md` onu içe aktarır. Skill'ler yalnızca rehbere yönlendiren ince kapılardır (bilgi tek yerde, eskimez).
    Ayrıntı: `docs/superpowers/specs/2026-11-02-ajan-destekli-yerellestirme-design.md`.
130. **Araçlar uygulamanın çekirdeğini kullanır** (`nxceviri/arac/`): ajan her oyunda kendi betiğini yazmaz; anahtar
    içeriği hiçbir çıktıda görünmez (testle sabit).
131. **Kullanıcı eklentisi = klasör** (`eklenti.toml` + `plugin.py`'de `PLUGIN` + `tests/` + `NOT.md`, `EKLENTI_API = 1`);
    yerleşikten önce denenir, istisnaları `FormatError`'a sarılır, korumalı alan yoktur (uyarı gösterilir). PyInstaller
    paketi standart kütüphaneyi tümüyle içerir ki eklentinin içe aktarmaları exe'de de çalışsın.
132. **Kendiliğinden güncelleme klasörü bütünüyle değiştirir;** kullanıcı verisi (`%LOCALAPPDATA%\NXCeviri`: eklentiler,
    kurtarma, loglar; projeler; ayarlar) klasör dışında olduğu için etkilenmez. Git kopyasında yalnızca denetim yapılır.
133. **Depoda oyun metni yok:** FSD/MSG metni özetle eşleşir (`exe.digest`: satır sonu ve sondaki boşluk normalize).

### 4.35 0.49.0 kararları (Çevir ekranı)

134. **No = aktarım sırası**, tek kaynak `TranslationModel.number(row_id)`; sıralama ve süzgeçle değişmez.
135. **Önizleme yalnızca çizimdedir:** önizleme metni `DisplayRole`/`ROW_ROLE`'dan döner; `EditRole`, `model.rows`,
    kayıt, dışa aktarma ve denetim gerçek metni kullanır. Bul vurgusu `FIND_SPANS_ROLE` ile, aralıklar tembel hesaplanır.
136. **Süzgeci yalnızca kullanıcı temizler;** bul çubuğu süzgeç etkinken görünen satırlarda arar. Sütunu gizli süzgeç
    yüklenmez (görünmez süzgeç satır gizlemesin).
137. **Düzenli ifade koruması:** Python `re` kesilemediği için önce riskli desen denetimi (`regexguard.is_risky`),
    sonra satırlar arası süre bütçesi (500 ms; Tümünü Değiştir 2 sn). Yeni bağımlılık yok.
138. **Elle sınır proje ayarıdır** (`translate_manual_limit`); oyunun gerçek sınırının (kural/`max_length`) aşımını gizlemez.

### 4.36 0.50.0 kararları (menüler, Ayarlar, kısayollar)

139. **Kısayolların tek kaynağı `gui/shortcuts.py`:** `COMMANDS` kataloğu + `ShortcutRegistry.bind(id, QAction|QShortcut,
    tip)`. Tuş koda yazılmaz (test denetler); kullanıcı tuşları `shortcuts/<kimlik>` altında, varsayılana dönen kayıt
    silinir. Ayrılmış tuşlar (`reserved_reason`) atanamaz; kayıt dışındaki sabit tuşlarla belirsizlik böyle önlenir.
140. **Menüler `gui/menus.py`'de, eylemler ana pencerede (WindowShortcut).** Ebeveynli `Qt.Tool` pencere (Bul) etkinken
    de Qt ebeveynin pencere kısayollarını çalıştırır; sayfaya ayrıca `QShortcut` bağlanmaz (aynı tuş iki kez → belirsiz).
141. **Seçime bağlı menü durumu yalnızca menü açılırken hesaplanır;** kısayolla gelen yuvalar boş seçimi kendileri
    denetler. Seçili satırlar seçim aralıklarından okunur (`selectedRows()` 50k satırda saniyeler sürüyordu).
142. **Bul ve Değiştir `FindWindow` (Qt.Tool) içindedir;** arama mantığı `FindBar`da kaldı. Konum `translate/find_geometry`;
    sayfa gizlenince pencere gizlenir, yeni satırlar gelince arama kapanır.
143. **Ayarlar penceresi ayar yazmaz, sinyal yayar** (tema/boyut ana pencerede uygulanır ve yazılır); görünüm seçenekleri
    aynı `QAction`larla iki yönlü eşlenir. DeepL anahtarı yalnızca kimlik bilgisi deposunda.

### 4.37 0.51.0 kararları (anlık denetim, Sorunlar, yazım, terimler, sınırlar, Ollama)

144. **Anlık denetim `core/qa/live.py` `LiveChecker`:** satır nesnesi (dondurulmuş) + bağlam anahtarıyla önbellekli;
    tutarlılık kaynak metne göre dizinle artımlı (`update_row` etkilenen kimlikleri döndürür). Çevir tablosunda anlık
    türler yalnızca anlık sonuçtan gelir; Kontrol Et'ten yalnızca proje geneli türler (`term`, `untranslated`) eklenir
    (çift sayım ve kapatılan türün geri gelmesi olmasın).
145. **Terim tutarsızlığı proje genelidir, anlık değildir** (`core/qa/terms.py`); sözlük terimleri "glossary"
    denetiminde kaldığından `term` bulgusu yalnızca satırlardan çıkan kanonik terimler için üretilir.
146. **Anahtar deseni kuralları** `FitConfig.per_key` (fnmatch, büyük/küçük harf duyarsız, en uzun desen kazanır);
    yalnızca `rules_for_row` uygular. Sınırlar tablosu kartla tek kaynaktan beslenir, düzenleme yalnızca kendi
    girdisini birleştirir (`rule_edited`).
147. **Ağır yeniden denetimler arka plan işindedir** (Terim değil / Yoksay / Değiştir / Sözlüğe ekle sonrası); yazım
    penceresi yalnızca görünürken ve değişen satırlar için artımlı tazelenir.
148. **Güncelleme yardımcısı `DETACHED_PROCESS` olmadan** (`CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`) başlatılır;
    konsolsuz PowerShell betiği çalıştırmıyordu. Uçtan uca test gerçek PowerShell'le (Windows).
149. **Ollama şablonu `/api/show`'dan okunur:** `.System`/`.Messages` (Go) ya da `messages` (Jinja) yoksa sistem
    düşer → sistem metni kullanıcı mesajına eklenir ve uyarı verilir. `num_ctx` iş başında `prepare_job` ile en uzun
    partiden hesaplanır (karakter/3 + yanıt + %15, 8192'nin katı, ≤ modelin sınırı ve 32768).

### 4.38 0.52.0 kararları (bildirimler, değişiklikler, Otomatik Çeviri)

150. **Tek bildirim yolu `gui/notify.py` `NotificationCenter`:** kart + geçmiş her zaman; "gürültülü" kanallar
    (Windows bildirimi `QSystemTrayIcon`, `winsound.MessageBeep`, `QApplication.alert`) pencere etkin değilken ya da iş
    ≥ 2 sn sürdüyse ve yalnızca Ayarlar'da açıksa (`notify/sound|system|flash`).
151. **`MainWindow._run` her işin sonucunu bildirir:** işleyici kendi bildirimini verdiyse genel bildirim verilmez;
    hata kartında "Tekrar Dene" aynı işi yeniden kurar. Sayfa mesajları (`TranslatePage.show_notice`) sinyalle karta
    gider; sayfada kalıcı kutu yoktur. Uzun ya da çok satırlı metin kartta kısalır, tamamı "Ayrıntılar"da.
152. **Değişiklikler penceresi satırları tembel ölçer** (görünen aralık, kaydırma/sütun değişiminde); yerinde düzenleme
    `edit_fn` ile ana pencerenin kayıt yolundan, bağlam `context_fn` ile aktarım sırasındaki komşulardan gelir.
153. **Talimat kitaplığı kullanıcıya aittir** (`core/translate/instructions.py`, AppData JSON, atomik yazım).
154. **Yarım yanıt bölünür:** `ProviderError(splittable=True)` (Ollama `done_reason == "length"`) partiyi ikiye
    böler; tek maddede yine anlaşılır hata.

### 4.39 0.52.1 kararları

155. **Kullanıcının başlattığı denetim arka plandadır** (`start_checks`); `run_checks` eşzamanlı kalır (düzeltmenin
    ardından ve testler). Sayfaların iş *sonucu* bildirimdir; *durum* bantları (anahtar yok, tarama hatası) yerinde kalır.
156. **Kod türü şüphesi** (`codekinds.suspected_line_breaks`): tahmini "diğer" olan, en az 3 kez görülen ve
    görülmelerinin %70'inde sözcük arasına boşluksuz giren kod; kullanıcı türünü elle verdiyse sorulmaz.

### 4.40 0.53.0 kararları (Terminoloji)

157. **Arayüzde "Terminoloji", kodda `glossary`:** veri modeli ve proje şeması değişmedi; yalnızca kullanıcıya görünen
    adlar. "Yazım sözlüğü" ayrı kavramdır.
158. **Kitaplık kullanıcıya aittir** (`core/translate/termlib.py`, AppData, liste başına JSON; görünen ad dosyada,
    dosya adı güvenli karakter + özet). Kitaplıktan eklerken projedeki karşılık korunur (`add_missing`).
159. **Satırdan terim** `glossary_io.plan_terms_from_rows`: kod/satır sonu/sayı/sembol ayıklanır; çakışma kullanıcıya
    sorulur (onay listesinde işaretsiz).
160. **Örtük terimler** (`qa/terms.implicit_terms`) iş başında bir kez hesaplanır ve iş sözlüğüne eklenir; partiye
    yalnızca geçenler gider (`relevant_terms`), "Terim değil" listesi uygulanır.

### 4.41 0.54.0 kararları (dışa aktarma, font, görseller)

161. **Üzerine yazma yalnızca NXTR modunda** (`ExportOptions.overwrite`): hedefte `NXTR - Bilgi.txt` yoksa reddedilir,
    kullanıcının başka dosyaları asla silinmez. Sıra: geçici klasöre yaz → eskiyi `.eski` yedeğe taşı → `os.replace` →
    başarıda yedeği sil, hatada geri koy. Karar arayüzde `ask_full_folder` (empty/overwrite/other/cancel).
162. **Düzenlenmiş font = ek dosya** (`ExportOptions.extra_files`, TitleID → RomFS yolu → bayt): proje ayarı
    `font_overrides` (RomFS yolu → kullanıcının dosya yolu, JSON) yalnızca yolu saklar; bayt dışa aktarırken okunur.
    Yalnızca RomFS'te serbest duran TTF/OTF (`is_editable_font`); paket içi fontlar (Unity bundle, SARC) kapsam dışı.
    İçe alınan dosya başlık imzasıyla denetlenir (`looks_like_font`).
163. **Font önerisi satırın kendisinde** (`_ADVICE_ROLE`): aynı paketteki fontlar aynı kaynak yolunu paylaşır, yola
    göre sözlük yanlış öneri gösterirdi.
164. **Görseller eklenti özelliği** (`derived.GraphicsSupport(folder_name, export)`, eklentide `graphics = ...`):
    klasör oyun dosyalarının yanında `<folder_name>/orijinal|temiz`; hazır resimler mevcut `derived_files` yoluyla
    moda girer. İlk destek NNI arşivi; FSD/MSG ve MSBT doku dönüştürücüleri henüz bu arayüze bağlanmadı (TECH_DEBT 89).

### 4.42 0.55.0 kararları (maskot, Yardım, katkı)

165. **Maskot QPainter ile çizilir** (`gui/mascot.py`; dosya ya da SVG yok): 256 birimlik kutuda logodaki küçük
    simgenin ölçüleri; her boyutta net. Hâl geçişi yüz kurulan/bozulan hâller arasındaysa gözler `bounce_point` ile
    duvardan seker (sol yer, sağ tavan; ilk %45 düşüş, kalan geri sekme). Kareler yalnızca hareket varken ve maskot
    görünürken çizilir (33 ms); `animations_enabled()` kapalıysa anında geçer.
166. **Tek açma/kapama** (`appearance/mascot`, `set_mascot_enabled`): canlı maskotlar zayıf kümede; kapalıyken yeni
    oluşanlar da gizli doğar. Bildirim kartı maskotu yalnızca başarı/uyarı/hatada; bilgi kartında simge kalır.
167. **Maskotun hâlini ana pencere yönetir:** `_run` başında çalışıyor; `notify` düzeyiyle bitti/hata (süreli), iş
    bitince çalışıyorsa boşa; uygulama düzeyinde olay süzgeci (`_ActivityWatcher`, tuş/fare) uyku sayacını sıfırlar
    ve uyandırır. Süzgeç pencere kapanınca kaldırılır.
168. **Yardım konuları paket verisi** (`gui/help/NN-ad.md`, PyInstaller `collect_data_files` ile gelir); "Kısayollar"
    dosya değildir, `ShortcutRegistry`den üretilir ve tuş değişince yenilenir (`help.contents`, F1, yeni kategori
    "Yardım"). Arama `turkish_lower` ile; vurgu `ExtraSelection`.

### 4.43 0.55.1 kararları (çeviriye karışan kod, temizlik türleri)

169. **Anahtar kod olarak gitmez** (`ollama._key_hint`): kalem alanı `where`, değeri anahtarın sözcükleri. Kopyalanacak
    kod kalmaz; ipucu işlevi sürer. Sağlayıcıdan bağımsız savunma `guards.foreign_key_tokens` (kaynakta/eski çeviride
    olmayan `/(x)` ve alt çizgili tanımlayıcılar) ve eklenen satır sonudur; ikisi `translation_problems` ve
    `revision_problems` içindedir, bu yüzden hem toplu çeviride yeniden istek hem Kontrol Et'te "Şüpheli çeviri" olur.
170. **Dışa aktarmada yapı geri okuması** (`_verify_group(..., original=)`): metin eşitliğine ek olarak yazılan
    dosyanın anahtar kümesi orijinalinkiyle aynı olmalı. Aynı eklentinin `extract`ı iki yanda kullanıldığı için
    eklenti tuhaflıkları birbirini götürür; fark `ExportError` olur ve hedefe hiçbir şey yazılmaz. Oyunun kendi
    ayrıştırıcısı bizimkinden katıysa (ör. tırnaksız satır sonu) bu yine de yakalamayabilir; savunmanın birinci ve
    ikinci katmanı bunun için vardır.
171. **`FitOptions` kalktı:** üç temizlik (çift boşluk, noktalama öncesi boşluk, tekrarlı noktalama) ayrı seçenek
    değil düzeltme türüdür (`double_space`, `space_before_punct`, `extra_dots`); satır sığdırma da seçili türlere
    bakar (`autofix.Tidy`). `fit_config` JSON'undaki eski `options` anahtarı okunurken yok sayılır, yazılmaz.
172. **Arama yalnızca görünen metin** (`TranslationFilter.filterAcceptsRow`): anahtar ve dosya adı eşleşmeye girmez.

### 4.44 0.55.4 kararları (çökme)

173. **Uygulama çapında Python olay süzgeci yasak:** `QApplication.installEventFilter` ile Python `eventFilter` her Qt
    olayında (zamanlayıcı, boyama, iş parçacığı sinyali) Python'a girer; PySide6'da yarış ve çökme kaynağıdır. Maskotun
    uyku/uyanması `motion.idle_seconds()` (Windows `GetLastInputInfo`) ile 5 sn'de bir yoklanır; testle süzgeç
    kurulmadığı denetlenir.
174. **Çökme günlüğü** (`app.enable_crash_log`, `cokme.log`): `faulthandler` dosyaya yazar; dosya `main()` boyunca açık
    tutulur, normal çıkışta kapatılır. Klasör yazılamazsa açılış bozulmaz.

### 4.45 0.55.5 kararları (çöp toplayıcı)

175. **Döngü toplayıcı ana döngüden** (`gui/gcguard.GarbageCollector`): `gc.disable()`; 500 ms'de bir kuşak sayaçlarına
    bakılır, eşik aşıldıysa yalnızca o kuşak toplanır (pyqtgraph yaklaşımı). Böylece Qt sarmalayıcılarının yok
    edilmesi Qt çağrılarının ortasında ya da iş parçacığında olmaz. `cokme.log`'daki iki çökme de "Garbage-collecting"
    sırasındaydı. Testlerde (uygulama `main()` çalışmadığı için) otomatik toplayıcı açıktır.
176. **İş parçacığı bırakma** (`tasks.release_thread`): `wait()` sonra `deleteLater()`; `Task`, sağlayıcı yoklaması ve
    yazım taraması bu yolu kullanır. Pencereler `exec()` sonrası `deleteLater()` ile silinir.

### 4.46 0.56.0 kararları (yay animasyonu)

177. **Yay çözücü** (`gui/spring.py`): `shared/motion.js`teki çözücü birebir (yarı örtük Euler, kütle 1, 4 alt adım,
    dt ≤ 1/30 s). Süre yok; denge eşiği 0,4 birim ve 8 birim/s. `SpringAnimator` Qt zamanlayıcısıyla sürer; `retarget`
    hızı korur (yön değişimi sıçramaz). Yeni bağımlılık yok. Kenar çubuğu `--spring-soft` (260, 24) kullanır.
178. **Düğme daralmış sütuna sığmalı** (`NAV_TOGGLE_SIZE`/`MARGIN`): daralmış genişlik simge sütunudur; yay taşsa da genişlik
    `COLLAPSED_WIDTH`in altına inmez.

### 4.47 0.57.0 kararları (kod zarfı, Türkçe harf onarımı, Ollama atlama)

179. **Kod onarımı yalnızca kesin durumda** (`core/qa/codefix.py`): tam satır tek biçim çifti sarılır, eksik kapanış
    sona eklenir; sonuçta `placeholders.problems` boş olmalı ve görünen metin değişmemeli. Kısmi kapsamlı kodlar elle
    kalır (§4.3: sessizce düzeltilmez). Yeni tür eklenmedi, `placeholder` türünün parçası.
180. **Türkçe harf onarımı sözlükle** (`core/qa/asciitr.py`, tür `ascii_turkish`, `RISKY_FIX_KINDS`): yalnızca sözlükte
    olmayan sözcüklere bakılır, değiştirilebilir harflerin (en çok 10) tüm kombinasyonları denenir, tek bilinen aday
    varsa uygulanır. Var olan Türkçe harf geri alınmaz; işlem iki kez çalışınca sonuç değişmez. Cümle ortasında büyük
    harfle başlayan sözcük özel ad sayılıp atlanır.
181. **Ollama'da satır atlama:** takılan satır işi durdurmaz; atlananlar raporlanır ve satır çevrilmemiş kalır.

### 4.48 0.57.1 kararları (denetim turu)

182. **Özel kullanım alanı (U+E000–U+F8FF) karakterleri yalnızca çizimde değişir:** tabloda nötr `★`
    (`gui/textmarks.py`), düzenleme panelinde yedek fonta düşme kapatılır (`NoFontMerging`, `gui/editor_pane.py`); metin,
    arama, kayıt, dışa aktarma ham karakterle çalışır. Düzenlenebilir alanda karakter başka karakterle çizdirilemediği
    için panel kutu gösterir.
183. **Sığdırma ayarı değişince denetim** yalnızca proje daha önce denetlendiyse, 500 ms gecikmeyle ve mevcut yeniden
    denetim yoluyla (`_recheck_if_done`) yenilenir; ikinci bir denetim yolu yoktur. Taşma sayımı `line_too_long` ve
    `page_too_tall` türleridir.
184. **`arac font` arayüzle aynı çekirdeği kullanır** (`core/qa/fonts.py`: `scan_game_fonts`, `font_verdict`); yama
    uygulamaz. Rehberlerde font durumu yeni oyun akışının bitti ölçütüdür.
185. **Dışa aktarmada üzerine yazma yedeği** (`.{ad}.{8 hex}.eski`) bir sonraki dışa aktarmada onarılır; yalnızca adı
    kalıba uyan ve içinde bilgi dosyası bulunan klasörlere dokunulur.
186. **Proje deposu:** `save_as` yeni bağlantıyı eskisini kapatmadan önce açar; `open` hata yollarında bağlantıyı
    kapatır; göç yedeği var olan `.bak`ın üzerine yazmaz (`.v<sürüm>.bak`), yedek alınamazsa göç yapılmaz.
187. **`closeEvent`:** önce onaylar, sonra iptal, pencere gizlenir, iş parçacıkları beklenir (beklemeler kaldırılmadı).
188. **Kullanıcıya görünen metinlerde iç biçim adları kullanılmaz** (hata kaydı, geçici dosyalar, talimat, oyun kimliği).

### 4.49 0.57.2 kararları (görsel düzeltmeler)

189. **QSS `image:` görselleri** (tik, ok, seçenek noktası) tek yardımcıyla (`gui/theme.py`: `_svg_file` ve onu kullanan
    `_check_mark`, `_chevron`, `_radio_dot`) geçici klasöre yazılır; bozuksa yeniden yazılır.
190. **Tablolarda yalnızca simge gösteren sütun:** görünen metin boş, ad ipucu ve erişilebilir metinde, sıralama ayrı
    rolden (`gui/qa_page.py` `_SORT_ROLE`); hücre ipucu satır açma yönergesini (`OPEN_HINT`) taşımayı sürdürür.
191. **Sayfa içinde tablo:** tablo dikey `Ignored` boyut ilkesiyle kalan yüksekliği doldurur; sayfa kaydırması yalnızca
    tablo en küçük yüksekliğine indiğinde devreye girer (`gui/scan_page.py`; `gui/qa_page.py` sınır tablosu).
192. **Adım listesinde liste düzeyinde odak çerçevesi yok** (ürün sahibi kararı); seçim vurgusu odağı gösterir.

### 4.50 0.58.0 kararları (Sorunlar ekranı, tarama seçimi)

193. **Sorunlar tür süzgeci:** soldaki gruplu listedir (`gui/issue_kinds.py` `KIND_GROUPS`; sunum bilgisi, core'da
    değil); yalnızca bulgusu olan türler listelenir.
194. **Bulgu görünümü:** tek sütunlu, sabit satır yükseklikli liste (`gui/issue_rows.py`); HTML belgesi kurulmaz; sıra
    önem → tür → satır numarası, kullanıcı sıralaması yok.
195. **Düzeltme kapsamı** ayrı bir işaretleme sistemiyle değil seçimle belirlenir: satır seçimi > tür seçimi > "Tüm
    bulgular" (yalnızca riskli olmayan türler; `RISKY_FIX_KINDS`). `fix_requested` her zaman açık satır kimlikleri
    gönderir.
196. **Aktarma seçimi:** `extract_texts(only_paths=…)`; None eski davranıştır. Seçim projede saklanmaz; varsayılan,
    projede zaten bulunan dosyalardan türetilir (proje boşsa aktarılabilir tüm dosyalar).
197. **Kaldırma onayı:** `Project.import_texts` aktarımda olmayan dosyaları çevirileriyle siler; bu yüzden arayüz
    kaldırılacak dosyaları ve çevrilmiş satır sayısını (`translated_counts_by_file`) aktarmadan önce sorar, aktarma
    sırasında fazladan dosya düşerse yazmadan önce yeniden sorar.
198. **Dosya dili** arayüzde yalnızca `path_language` ile gösterilir; dosya adından tahmin yapılmaz.

### 4.51 0.58.3 kararları (eklenti onayı, kaydetme sorusu)

199. **Eklenti onayı:** kullanıcı eklentisi rastgele Python kodudur; bu yüzden `load_plugins(..., trusted=…)` yalnızca
    onaylı klasörü içe aktarır. Onay, klasörün içerik parmak izine (`plugin_fingerprint`, SHA-256; `__pycache__`
    hariç) bağlıdır; içerik değişince onay düşer. Onaylar proje dosyasında değil kullanıcı profilinde durur
    (`core/plugins/trust.py`, `eklenti_onaylari.json`, atomik yazım). `trusted=None` eski davranıştır: komut satırı
    araçları sormaz; depo eklenti klasörü de muaftır (uygulamanın kendi kodu).
200. **Derlenmiş önbellek:** parmak izi `__pycache__` içermediği için hazır bir `.pyc` onaylı kaynağın yerine
    çalışabilirdi; yükleyici içe aktarmadan önce eklentinin `__pycache__` klasörlerini siler.
201. **Kaydetme sorusu:** olumlu soru ve üç yanıt (Evet kaydeder ve varsayılandır, Hayır kaydetmez, İptal ve Esc
    projeye döner); okumadan "Evet" diyen kullanıcı veri kaybetmez. Kutu `build_save_box` ile kurulur, testler
    `MainWindow.ask_save_changes` üzerinden sürer.

### 4.52 0.59.0 kararları (gruplu görünüm, grup işlevi)

202. **Grup işlevi:** bağlamın ilk parçası yalnızca `COLLECTION_FORMATS` (Unity, Unreal) satırlarında grup adıdır;
    diğer biçimlerde bağlamdaki "/" koleksiyon anlamına gelmez, grup dosya adıdır (`in_collection`, `row_group`).
    Gerçek projelerde ölçüldü: kural yalnızca iki biçimin grup listesini değiştirdi. Eski grup adlı büyük harf
    işaretleri okunurken satır işaretine çevrilir (`_with_legacy_groups`; veritabanına yazım yok).
203. **Gruplu görünüm vekili:** `GroupProxy` yalnızca gruplama açıkken tabloya takılır; her zaman takılıyken büyük
    tabloda boyama yaklaşık %25 yavaşlıyordu. Kapalı kipte tablo doğrudan `TranslationFilter`'a bağlıdır.
    Sayfanın geri kalanı satıra `_model_row` / `_view_index` yardımcılarıyla ulaşır, vekili bilmez.
204. **Katlama ve düzenleme:** grup katlanmadan önce açık hücre düzenlemesi kaydedilir; kayıt başarısızsa grup
    katlanmaz (yazılan metin kaybolmaz).
205. **Başlıktaki uyarı simgesi** denetim çalıştırmaz; yalnızca bilinen sonuçları gösterir (`LiveChecks.cached`).
    Simgenin yokluğu "sorun yok" anlamına gelmez.
206. **Gruplama düğmesinin yeri:** süzgeç değil görünüm seçeneği olduğu için süzgeç şeridinde durmaz; esnek boşluğun
    sağında, birincil düğmenin solundadır ve panel düğmesiyle aynı görünümdedir.

### 4.53 0.60.0 kararları (adlar, eski kimlikler, ek çeviri verisi)

207. **Adlandırma:** depoda oyun ve firma adı geçmez; paket, modül, sınıf, biçim kimliği, motor anahtarı ve görünen
    etiketler dosya biçimi ya da motor adını taşır. Oyunun kendi RomFS yolları ve dosya adları biçim gerçeğidir,
    tespit ve yazma bunlara bağlı olduğu için kalır.
208. **Eski kalıcı değerler:** proje dosyası dönüştürülmez (eski sürüm de açabilsin). Eski biçim kimliği, motor
    anahtarı, tarama ayrıntısı ve kanıt adı projeden okuma sınırında (`core/project/store.py`) tek tablodan
    (`core/formats/legacy.py`) bugünkü değere çözülür; üst katmanlar yalnızca yeni değeri görür. Yeniden içe
    aktarmada aynı biçimin dosyada saklı eski kimliği korunur, projeye yeni giren dosya yeni kimlikle yazılır.
    Eski adların kaynakta kalabileceği tek yer bu tablo ve onun testidir.
209. **Oyuna ait çeviri verisi uygulamayla gelmez:** resim üzeri yazılar, program içi açıklamalar ve menü sözcükleri
    kullanıcının grafik klasöründeki isteğe bağlı JSON dosyalarından okunur (`fontpatch/fsdmsg_userdata.py`; şema
    denetimli). Veri yoksa yama atlanır ve bilgi dosyasına not düşülür; bozuksa dışa aktarma yazmaya başlamadan
    durur. Yapı (doku işleme, IPS üretimi) kodda, veri (koordinat, sözcük, özet) dışarıdadır.
210. **Tablo rolleri kataloğu:** çeviri tablosu modelinin özel veri rolleri `gui/table_roles.py` içindedir;
    değerlerin farklı olduğu testle korunur.
211. **Anahtar adı:** bağlamın son parçası yalnızca koleksiyonlu biçimlerde anahtar adıdır (`key_names`,
    `in_collection`); sığdırma kuralları ve makine çevirisi kapsamı aynı işlevi kullanır.

### 4.54 0.61.0 kararları (yinele, kod kısayolları)

212. **Yinele:** geri alma bir adımı yazarken satırların o andaki tam hâlini (metin, durum, açıklama) yinele
    yığınına koyar; yinele bunu tek işlemde geri yazar ve adımı birleştirmeden geri al yığınına döndürür (toplu iş
    iki yönde de tek adımdır). Kullanıcıdan gelen her yeni yazım ve yeniden tarama yinele yığınını boşaltır; hiçbir
    satırı değiştirmeyen yazım boşaltmaz. Yinele geçmişe işin kendi adıyla yazılır: "Son işte değişenler" ve
    "Önceki Çeviri" işin ilk yapıldığı hâle döner. Yığınlar oturumluktur; şema değişmedi.
213. **Kod kısayolları:** dokuz katalog komutu (`edit.code1`…`edit.code9`) menüde yer almaz; her düzenleyiciye ve
    tabloya `WidgetShortcut` bağlamlı kısayol olarak bağlanır, bu yüzden odak başka yerdeyken tuş yutulmaz ve aynı
    tuş iki kez işlenmez. Ctrl+Alt (AltGr) tam değiştirici eşleşmesi gerektiği için kısayolla eşleşmez. Tablodan
    ekleme, paneli önce geçerli satıra eşler ve yalnızca panelin gösterdiği satıra yazar.
214. **Sayfa geçişi Alt+1…5:** Ctrl+rakam kod eklemeye ayrıldı (ürün sahibinin kararı). Varsayılana eşit tuş
    ayarlarda saklanmadığı için göç gerekmedi; kullanıcının kendi atamaları korunur.
215. **Düzelt onaylı satırlarda da çalışır, satır onaylı kalır (ürün sahibi kararı):** `qa/fixrun` planı
    `include_approved=True` ile çıkarır; yazım `_write_row_changes`: onaylılar ayrı çağrıyla (insan durumu, `machine`
    değil) yazılır, aynı `job_id` ile tek iş (Geri Al/Yinele tek adım). "Onaylı satıra dokunulmaz" kuralı yalnızca
    makine çevirisi ve redaksiyon için sürer (`set_translations` onaylıyı `overwrite_approved` olmadan atlar).
    Bulgu çubuğundaki sayı Düzelt'in değiştireceği satır sayısıdır: ikisi de `plan_for_issues` kuralından gelir;
    plan düzeltemeyecekse çubuk bunu söyler ve düğmeyi göstermez. Düzelt yalnızca bulgusu olan satırları denetler
    (tüm projeyi değil; 200 satırdan fazlasında arka plan işi); sonrasında değişen satırlar panoda yerinde
    yenilenir (2000'den fazlasında arka planda tam denetim; bitene dek bulgu çubuğu gizlenir). Yerinde yenilemede satırın terim bulguları korunur
    (biçim düzeltmesi terim bulgusunu değiştirmez; tazesi sonraki tam denetimde gelir).

216. **Serbest kod sırası (ürün sahibinin kararı, 2026-11-16):** kodun serbest olduğunu yalnızca biçim eklentisi
    `movable_code` ile bildirir; karar tek yerde (`placeholders.check`) verilir, eklentilerin `inject` denetimi katı
    kalır. Proje şeması değişmedi: kodların ham baytı ve etiketi zaten saklı, eklentiye okuma anında sorulur
    (`registry.free_codes`, önbellekli; `movable_code` bildirmeyen biçimde hiç sorulmaz).
217. **Yazım önerisi çevrimdışı ve dar:** Türkçe harf değişimi (iki yön, en çok 3 harf) ya da yalnızca bu boşsa fazla
    harf / yer değiştirmiş iki harf. Eksik ve değişmiş harf, Bloom süzgecinin uydurma isabeti doğru isabeti geçtiği
    için denenmez (ölçüm). Toplu düzeltme yalnızca tek harf-değişimi önerisi olan "güvenli" sınıfa ve onayla uygulanır.
218. **Belirsiz Türkçe harf sözcüğünü kullanıcı çözer; hata olmayan bulgu yok sayılabilir (ürün sahibinin onayı):**
    `repair_ascii_turkish` tireli sözcüğün parçalarını ayrı değerlendirir ve belirsiz sözcüklerin adaylarını
    (`AsciiRepair.choices` → `QaIssue.choices`) bulguya taşır; sağ tıktaki seçim `apply_choice` ile projedeki bütün
    satırlara tek iş olarak (`_replace_translations`) uygulanır. Yok sayma `core/qa/ignored.py`: proje ayarında
    (satır, tür, çeviri özeti); özet tutmazsa bulgu geri gelir, hata bulguları yok sayılamaz. Süzgeç tek yerde
    (`ChecksController.show_check_results` ve `_replace_board_rows`, `gui/checks_controller.py`) uygulanır; panoda yalnızca gerçek bulgular sayılır,
    yok sayılanlar "Yok sayılanlar" girişiyle ayrı görünür. Menü eylemleri planı 0 satır düzeltiyorsa hiç çıkmaz.
219. **Aç/kapa çiftleri bütün olarak taşınabilir (ürün sahibinin kararı, 2026-11-17):** biçim eklentisi isteğe bağlı
    `paired_code(code) -> (aile, "open"|"close"|"separator") | None` ile bildirir; bildirmeyen eklentide çiftler katı
    kalır. Karar yine tek yerde (`placeholders.check`): kaynakta aynı ailenin açılışı ile kapanışı yığınla eşlenir
    (eşi olmayan kod katı); çift açılışı kapanışından önce, çaprazlanmadan ve aynı üst çiftin içinde kalarak yer
    değiştirdiyse uyarıdır. Katı kodların kendi aralarındaki sırası ve içinde durdukları çift değişmez (`%s` içeren
    bir çift başka bir `%s`'nin öbür yanına geçemez); ayraç kendi çiftinin içinde, sırasıyla kalır. Rolleri taşımak
    için `TranslationRow.free_codes` artık `placeholders.CodeRoles` (`frozenset[int]` alt sınıfı, `pairs` özniteliği)
    taşır; böylece arayüz dahil bütün çağıranlar değişmeden aynı kararı verir. Boş kümenin doğruluk değeri yanlış
    olduğundan çift varlığına `pairs_of` ile bakılır; makine çevirisinde aynı kaynaklı satırların ortak rolü
    `common_roles`. Dışa aktarma uyarılı satırı `tolerate_reorder` içinde yazar; Düzelt uyarılı sıra farkını özgün
    sıraya dizmez. Bildiren yerleşikler: Unity (TextMeshPro), Unreal (UMG `<X>…</>`), PSB metni, YCD paketi, SRT,
    FMSB, MSBT (yalnızca 0x0F kapanışlı etiketler), NNI metni (`<color:…>…<color:>`), WAD/LIN (`<CLT n>…<CLT>`).
    GFMSG seçimleri ve fsd kodları bildirilmez (seçim üçlüdür, fsd kodlarının anlamı çözülmedi).
220. **Unreal çoğul ifadesi parçalanır:** yalnızca yalın biçim (`{Count}|plural(one=cat,other=cats)`: tırnaksız,
    boşluksuz, boş olmayan değerler) baş (`{Count}|plural(one=`, açılış), ayraç (`,other=`, ayraç) ve son (`)`,
    kapanış) kodlarına ayrılır; seçenek sözcükleri çevrilir, ifade bütün olarak taşınır. Başka biçimde ya da başka
    bir ek (`|gender(`, tırnaklı değer) geldiğinde değişken ile ekin başı tek, katı kod olur (önceden `{N}` serbestti
    ve ek düz metindi; değişken ekinden ayrılabiliyordu). `inject` çoğul içeren satırı yazdıktan sonra yeniden okur;
    seçeneğe ayraç, boşluk ya da boş değer yazılmışsa reddeder. Eski projelerde bu satırların kaynak metni değişir
    (yeniden taramada "orijinal değişti"); eski çeviri yeni kodlarla yazılamaz, sessizce bozulmaz.
221. **Ana pencere denetleyicilere bölünür (ürün sahibinin onayı, 2026-11-17; TECH_DEBT 69):** Kontrol Et iş akışı
    `gui/checks_controller.py` `ChecksController`'da (denetim, pano yenileme, yok sayma, Düzelt, aday seçimi,
    yazım/terim yok sayma; durumu `qa_count`, `board_task`… da orada), Dışa Aktar iş akışı
    `gui/export_controller.py` `ExportController`'da (özet, hedef klasör, hatalı satır seçeneği, mod oluşturma;
    durum tutmaz). Denetleyici Qt nesnesi değildir, pencereyi tutar ve her çağrıda pencereden okur; pencerede
    yönlendirmesi olan yöntemi pencere üzerinden çağırır (`self._win._recheck_if_done()`), bağlı yöntemi
    saklamaz: testler pencerenin yöntemlerini değiştirerek çalışır. Sinyal bağlantıları, kısayollar ve iş akışı
    (`MainWindow._run`, `Task`) pencerede kalır; pencere taşınan bütün eski adları (iç yardımcılar dahil) ince
    yönlendirme ve okuma/yazma property'si (`_qa_count`, `_board_task`…) olarak korur. Taşınan modül adları
    (`run_qa_checks`, `FIX_SYNC_ROWS`, `FIX_RECHECK_ROWS`, `KEPT_ROWS_SHOWN`) artık denetleyici modülündedir; onları
    değiştiren testler denetleyici modülünü içe aktarır. Testlerin pencere modülünde değiştirdiği `choose_button`,
    `opened_view`, `MemberReader` orada kalır: dolu klasör sorusu `MainWindow._ask_full_folder` üzerinden,
    görsel çıkarma pencerede. Dışa aktarma `check_sources`'u kendi modülünden çağırır; pencere modülündeki adı
    değiştirmek artık yalnızca pencerede kalan yolları (ekleme, görseller, font) etkiler. Adım sabitleri
    `gui/step_nav.py`'dedir, `main_window` `__all__` ile yeniden verir.
    Üçüncü adım (aynı düzen): proje yaşam döngüsü (yeni, aç, kaydet, farklı kaydet, son projeler, kurtarma kopyası)
    `gui/project_controller.py` `ProjectController`'da (`self.projects`), makine işleri (çevir / yeniden çevir /
    talimatla düzelt penceresi, kapsamlar, ayarların hatırlanması, işin yürütülmesi ve partilerin yazılması)
    `gui/machine_controller.py` `MachineController`'da (`self.machine`). İkisi de durum tutmaz: proje, `dirty`,
    `recent`, `recovery`, `_recovery_due`, `_last_job`, `secrets`, `provider_factory` pencerede kalır (testler bunları
    pencerede atar). Kaydetme sorusu (`ask_save_changes`, `build_save_box` pencere modülünde) ve `closeEvent`
    pencerede kalır. Testlerin pencere modülünde değiştirdiği `implicit_terms`'i makine denetleyicisi gecikmeli
    içe aktarılan pencere modülünden okur (`_mw.implicit_terms`). Talimat anahtarları (`REVISE_INSTRUCTION_KEY`,
    `TRANSLATE_INSTRUCTION_KEY`) denetleyici modülündedir, `main_window` yeniden verir.

### 4.55 2026-11-17 kararları (çeviri kaynağı, Sorunlar panosu)

222. **Satırın makine çevirisi kaynağı saklanır (TECH_DEBT 31):** şema 7, `text_entries`'e `mt_provider` (kalıcı
    kimlik: `ollama`, `deepl`, `memory`) ve `mt_model` (yalnızca Ollama'da model adı; DeepL'de boş) ekler; `history`'ye
    aynı değerlerin önceki hâli (`old_mt_provider`, `old_mt_model`). Göç yalnızca `ALTER TABLE ... ADD COLUMN`
    (varsayılan boş = "bilinmiyor"); diğer göçler gibi tek işlemde, öncesinde `.bak` yedeği alınır. Adres, API
    anahtarı ya da kişisel veri yazılmaz (`core/translate/origin.py`). Değer `Project.set_translations(origin=...)`
    ile yalnızca açıkça verilince değişir; `machine=True`'dan türetilmez, çünkü bu bayrağı makine dışı yollar da
    kullanır. Yazım yolları: makine işi (Çevir, Yeniden çevir, Talimatla düzelt) sağlayıcıyı ve modeli yazar; aynı
    işte çeviri belleğinden dolan satırlar (`runner.memory_filled_ids`) `memory` olur. Elle düzenleme, onaylama/onay
    kaldırma, Bul ve Değiştir, Kontrol Et'in Düzelt'i ve aday seçimi, satır sonu yeniden bölme ile dış redaksiyon
    kaynağı **değiştirmez**: bunlar makine taslağını düzeltir, insanın dokunduğunu durum sütunu zaten gösterir;
    sağlayıcıları karşılaştırmak için onaylanmış satırın taslağının nereden geldiği de gerekir. Metni dışarıdan
    baştan değiştiren yollar (hazır çeviri aktarma `port.py`, dış çeviri içe aktarma) kaynağı **siler**. Yeniden
    tarama satırın kaynağına dokunmaz. Geri Al/Yinele satırın tam hâlini (metin, durum, açıklama, sağlayıcı, model)
    taşır; yalnızca kaynağı değişen yazım da geri alınabilir bir adımdır. Geçmişten geri alma (`revert`) önceki
    kaynağı da geri koyar; şema 7'den önceki geçmiş kaydında önceki kaynak bilinmez, boş olur. Arayüzde yeni sütun
    yok: Çevir tablosunda Durum hücresinin ipucuna "Çeviren: Ollama (model)" satırı eklenir (çeviri boşsa ya da kaynak
    bilinmiyorsa eklenmez). Görünen adlar tek yerde (`origin.PROVIDER_NAMES`); durum çubuğu da onu kullanır.
223. **Sorunlar panosu ve "Hata veya uyarılı" süzgecinin pürüzleri (TECH_DEBT 85):** (a) Çevir'deki süzgeç her satırı
    anlık denetimden geçirir; ölçüm (35.000 sentetik satır, yazım + terminoloji + sığdırma açık, tüm anlık türler):
    ilk süzme 32 sn, önbellek dolunca 0,3 sn. Denetlenmemiş satır `ISSUES_PRECHECK_ROWS` (1.000, ≈1 sn) üstündeyse
    `LiveChecker.precheck_job` arka planda (`Task`) çalışır, süzgeç sonuç gelince uygulanır; tıklama 0,01 sn'de döner.
    İş bağlamın anlık görüntüsüyle çalışır; `store` bağlam değiştiyse sonucu atar, iş sürerken önbellek kaydı değişen
    satıra dokunmaz. Pencere kapanırken iş durdurulup beklenir. (b) İş sürerken Sorunlar'da yerinde düzenleme
    reddedilmez, saklanır (`ChecksController.pending_edits`) ve `_task_finished`'te yazılır; satırın proje dosyasındaki
    çevirisi düzenleme anındakiyle aynı değilse (biten iş değiştirmiş) ezilmez: metin bildirimde gösterilir, "Yine de
    Kaydet" ile yazılır. (c) Riskli türleri (`RISKY_FIX_KINDS`) birden çok satırda ya da türün bütün bulgularında
    düzeltmeden önce `qa_page.ask_risky_fix` kısa onay sorar; tek satır sorulmaz (seçim onaydır). (d) Terim
    denetiminde köke doğrudan eklenebilen harf sınırı son sözcüğü 4+ harfli terimde 14'tür ("Şövalye" +
    "lerimizdekiler"); 3 harfe kadar kısa terimde 8 kalır, yoksa "Ev" → "Evcilleştirilmiş" gibi başka sözcükler terim
    sayılırdı. Bedeli: kısa terimde uzun gerçek ek zinciri ("Evlerimizdekiler") ve uzun terimde 15+ harflik zincir
    uyarı verir; uzun terimle başlayan ilgisiz bir sözcük de (14 harfe kadar devamıyla) terim sayılabilir, o satır
    uyarı vermez. (e) Büyük tabloda süzgeç açıkken satırlar yeniden yüklenince (`set_rows`, ör. makine işinden sonra)
    süzgeç denetlenmemiş satırı denetlemez, gösterir (`TranslationFilter.lazy_issues`); arka plan denetimi bitince
    süzgeç yeniden uygulanır. Arka plan işi iptal edilirse yeniden başlamaz, hata verirse bildirir ve yeniden denemez.
    Saklanan düzenleme varken pencere kapatılırsa "İşlem sürüyor" sorusu bunu söyler; vazgeçilirse saklananlar atılır.
224. **Eklentinin reddettiği satır yalnızca kendisi orijinal kalır (TECH_DEBT 97'nin dışa aktarma kısmı):** önceden
    yalnızca "yumuşak" satırlar (serbest kod sırası farklı, ya da "Hatalı satırları da aktar" açıkken hatalı satırlar)
    ayıklanabiliyordu; "Hatalı" olmayan bir satırı eklenti reddedince (eski kod düzeniyle saklanmış çoğul satırı,
    geçersiz çoğul seçeneği) bütün dosya yazılamıyordu. Şimdi `_inject_tolerant` tam yazım ve (varsa) yumuşaklar
    dışındaki yazım başarılıysa eskisi gibi davranır (127'nin yolu değişmedi); o da başarısızsa önce çevirisiz yazımı
    dener (o da düşüyorsa sorun satırlarda değildir, hata olduğu gibi çıkar), sonra reddedilen satırları
    `_find_rejected` ile bulur: alt kümeler birbirinden bağımsız sınanır, ret satırı adlandırıyorsa
    (`FormatError(key=…)`, yerleşik eklentilerin satır reddi) o satır doğrudan çıkarılır, adlandırmıyorsa küme ikiye
    bölünür; kalan yine ikiye bölünerek çağrılar küçülür. Kalanlar birlikte yazılamıyorsa (ör. toplam boyut sınırı)
    birikimli ikili bölmeye (`_accept_soft`) düşülür. Her `inject` dosyayı baştan ayrıştırdığından süre çağrı
    sayısıyla gider; ölçüm (3.000 satırlık locres, eski düzenli çoğul satırları): 20 ret 45 çağrı / 4,7 sn, 200 ret
    405 çağrı / 14,8 sn (adlandırmadan saf ikili bölme: 323 / 12,8 sn ve 1.955 / 52 sn). İptal edilebilir. Hatalı
    olmayan reddedilen satır `ExportResult.rejected_ids`/`rejected_rows`'a yazılır, "yazılan" sayısından düşülür;
    uyarı verilir ve bilgi dosyası "dosya : anahtar — eklentinin iletisi" olarak listeler (en çok 200 satır; satırın
    metni yazılmaz, yerleşik eklentilerin iletisi kod numaralarını ve kuralı söyler). Kod sırası reddi (`reordered_keys`) eskisi gibi
    kendi uyarısıyla sayılır. Bilinçli değişiklik: "Hatalı satırları da aktar" açıkken hatalı olmayan bir satırın
    reddi önceden dosyayı düşürürdü, şimdi o satır orijinal kalır (`test_export_include_errors_rejected_good_row_*`).
    Yazılacak satırların hepsi reddedildiği için hiçbir dosya değişmediyse hata "çeviriler orijinalle aynı" demez;
    reddedilen satır sayısını ve ilk anahtarları söyler.
    **Kaynak denetimi (bütün biçimler):** yazımdan önce `_stale_keys` dosyayı eklentinin `extract`iyle bir kez okur
    ve yazılacak (çevirisi olan) her satırın projede saklı kaynağını (`ExportResult.expected_sources`, kodlar `⟦n⟧`
    olarak) bugünkü okumayla karşılaştırır; ölçüt yeniden taramadaki "kaynak değişti" ölçütüyle aynıdır (kaynak metin
    aynen eşit). Uyuşmayan satır denenmez, orijinal kalır, aynı ret düzeniyle bildirilir (`STALE_SOURCE_REASON`:
    "kaynak değişmiş — Metinleri Tara ile yeniden tarayın"). Gerekçe: eklentinin okuma düzeni değişince (ör. Unreal ek
    ayrıştırması, Unity Smart String çoğulu) eski çeviri kod sayısı aynı kaldığı için yazım denetimine takılmadan
    yanlış yazılabiliyordu (`{G}|gender(|gender(o,o) …`). Çevrilmemiş satırlara ve bugünkü okumada bulunmayan anahtara
    bakılmaz (onu eklenti zaten reddeder). Değişen dosyada ek ayrıştırma yoktur: okunan anahtar
    kümesi (`ExportResult.original_keys`) geri okuma denetimindeki (`_verify_group`) orijinal satır kümesinin yerine
    kullanılır; o okuma kaldırıldı. Sonunda değişmeyen dosya (ör. bütün satırları reddedilen arşiv üyesi) önceden hiç
    okunmazdı, şimdi bir kez okunur. Eklentilerin `extract`'i bağlamı (kaynak dil, dosya yolu, toplanan bağlam)
    yalnızca hangi anahtarların alınacağını ve okunur bağlamı seçmek için kullanır, kaynak metni değiştirmez
    (yerleşiklerde koddan denetlendi); bağlamsız okuma bu yüzden aynı kaynağı verir. Kod ham baytı karşılaştırılmaz (etiketler sürümler arasında yalnızca yazı olarak
    değişebilir; görünen kaynak aynıyken kod sınırları da aynıdır). Arayüz: Dışa Aktar bildirimi bu satırları
    (`rejected_ids`) hatalı tutulanlarla aynı düzende listeler (`KEPT_ROWS_SHOWN`).
225. **"Satır sonu yasak" biçim kuralı (TECH_DEBT 91):** biçim eklentisi isteğe bağlı `forbids_newline(key) -> bool`
    ile bildirir (satır başına, çünkü aynı eklenti hem satır sonu taşıyan hem taşıyamayan metin tutabilir). Karar
    `registry.forbids_newline`'da (eklenti bildirimi biçim+oyun başına önbellekli; eklenti hatası kuralı yok sayar,
    günlüğe yazılır) verilir ve `TranslationRow.newline_forbidden` olarak satıra taşınır (şema değişmez). Yalnızca
    gerçek `\n`/`\r` sayılır; satır sonu kodu (`⟦n⟧`) sayılmaz. Kontrol Et: yeni tür açılmadı, var olan "Satır sonu"
    (`newlines`) türü hata önemiyle verilir (arayüzdeki tür grupları ve Düzelt değişmeden çalışır; Düzelt kaynağında
    satır sonu olmayan satırı tek satıra indirir, sığdırma kuralı olan dosyada indirmez); aynı satıra satır sonu
    sayısı uyarısı ayrıca verilmez. Dışa aktarma: `drop_forbidden_newlines` harf dönüştürme ve `normalize_text`'ten
    sonra bu satırları yazılacaklardan çıkarır, 224'teki gibi bildirir (neden: `NEWLINE_FORBIDDEN_REASON`);
    "Hatalı satırları da aktar" açık da olsa yazılmaz. Eklentinin `inject`i satırı kabul etse bile yazılmaz: oyunun
    okuyucusu bizimkinden katı olabilir. Bildiren yerleşik: yalnızca Unity'nin dil sütunlu TSV hücreleri (`TSV|`
    anahtarları; yazıcı zaten reddediyordu). Satır sonu içeren çevirinin yazılıp aynen geri okunduğu elle üretilmiş
    örnekte denendi: Unreal, Unity String Table, MSBT, GFMSG. Koddan ve biçim notlarından satır sonunun metnin parçası
    olduğu ya da koda çevrildiği görülen: FMSB, WAD/LIN, NNI (XSO'da `\n` koduna), FSD/MSG (0x0C koduna), SRT (yalnızca
    boş satırı reddeder). Denenmedi, bildirilmedi: PSB metni, Unity I2 ve SerializeReference, YCD (`.yc`; biçim
    notlarında kural belirsiz).
226. **Türkçe resim klasörü `turkce/` (ürün sahibi, 2026-11-17):** grafik çevirisinde kullanıcının Türkçe resimleri
    koyduğu klasör `temiz/` yerine `turkce/` olur (`orijinal/` aynı). Ad tek yerde, `core/formats/derived.py`'de
    (`TURKISH_DIR`, `LEGACY_TURKISH_DIR`, `turkish_dir`). Geriye uyum: `turkce/` yoksa ve `temiz/` varsa eski klasör
    okunur (yeniden adlandırılmaz, dosyalara dokunulmaz); ikisi de varsa `turkce/` kullanılır ve `temiz/` yok
    sayıldığı uyarılır (NNI: dışa aktarma uyarısı; FSD/MSG: günlük). Yeni kurulumda `export_originals` `turkce/`
    oluşturur; uyarı metinleri etkin klasörün gerçek adını söyler.
227. **Yeni oyun yalnızca eklentiyle; eklentinin çekirdek içe aktarmaları denetlenir (ürün sahibi, 2026-11-17):**
    yeni bir oyun için yazılan bütün kod (metin, font, resim) tek kullanıcı eklentisinde durur, ajan `nxceviri/`
    altına yazmaz; "eklenti oluşturamıyorum" kabul edilmez (`AGENTS.md` §1, `yeni-oyun.md`). Neden: başka bir kopyada
    çekirdeğe eklenmiş bir modülü içe aktaran eklenti bu kopyada yüklenemiyordu. Eklentiye açık çekirdek modülleri
    tek yerde, `core/plugins/imports.py` `ALLOWED_MODULES` (tam adlar: `core.plugins`, `formats.base`,
    `formats.derived`, `formats.msbt[.msbt]`, `translate.placeholders`, `translate.markup`, eklenti-yazma.md'deki
    arşiv modülleri); `eklenti-yazma.md` "İzinli çekirdek modülleri" aynı listeyi verir, test ikisini karşılaştırır.
    `msbt` listede: kurulu eklentiler yerleşik MSBT okuyucusundan türetiyor. `fontpatch.*` listede değil (iç
    yapı; BC7 kodlayıcı gibi yardımcı gereken eklenti kendi kopyasını yazar). `audit_plugin(klasör)` `.py`
    dosyalarını (`tests/`, `__pycache__` hariç) `ast` ile tarar, kod çalıştırmaz; `import`, `from … import` (paketten
    alınan ad alt modül olarak değerlendirilir) ve sabit adlı `importlib.import_module`/`__import__` çağrılarını
    `find_spec` ile çözer (paketlenmiş exe'de de çalışır). Göreli içe aktarma eklentinin kendi modülüdür, geçer.
    Bağlantılar: `arac eklentiler` bulguları `İçe aktarma:` satırıyla gösterir (çıkış kodu değişmez; yükleme
    engellenmez), `arac dogrula` bulguyu KALDI sayar, yükleyici `nxceviri` altından bir şey bulamayıp içe
    aktaramazsa hata metnine bulguları ekler. Ayrıca `dogrula` artık kullanıcı eklentilerini kendisi yükler (önceden
    yalnızca yerleşikleri görüyordu) ve adı verilen eklenti yüklenemediyse "yok" yerine yükleme hatasını söyler.
    İskeletin testi `plugin.py`'yi paket olarak yükler; çok dosyalı eklentinin göreli içe aktarmaları testte de çalışır.
228. **Eklenti arşiv kancası `archive_formats()` (ürün sahibi, 2026-11-17):** oyuna özgü arşiv biçimi çekirdeğe değil
    eklentiye yazılır; eklenti `ArchiveFormat` nesneleri (`core/formats/base.py`: `name`, `label`, `suffixes`,
    `detect`, `open(game, yol) -> MemberArchive`, `rebuild(changes, game) -> {RomFS yolu: bayt}`) bildirir. Yerleşik
    üye arşivlerinin (NNI/CPK/WAD) bağlandığı noktalara bağlanır, paralel yol yoktur: `MemberReader` eklenti biçimini
    (uzantı + `detect`, ilk 4 KB) yerleşiklerden önce dener ve `arşiv>üye` yolunu çözer; `is_member_path` biçimleri
    parametre alır; `scanner` arşivi `ARCHIVE` türüyle yazar ve üyelerden kullanıcı eklentilerinin tanıdıklarını
    listeler (üye adı bir eklentinin `path_suffixes`'ine uymuyorsa okunmaz: üye okumak açma maliyetlidir); `pipeline`
    üyeyi okuyucudan okur; `layeredfs` değişen üyeleri ve `derived_files` üyelerini toplayıp eklentinin `rebuild`'ine
    verir. `rebuild` bir oyundaki o biçimin bütün değişikliklerini tek seferde alır (`{arşiv: {üye: bayt}}`) ve
    dönen dosyaları yazar; çünkü bazı oyunlar değişikliği güncellemenin arşivine koyar (temel arşiv GB'larca olabilir,
    yeniden yazılmaz) ve arşiv başına `rebuild(changed) -> bytes` bunu anlatamaz. Kardeş dosyalar (`game.open`) bu
    yüzden verilir; oyun dosyası `ByteSource` olarak açılır, tamamı okunmaz. Doğrulama çekirdekte: dönen dosyalar oyunun
    üstüne bindirilir (`OverlayFiles`) ve eklentinin okuyucusuyla açılır; her değişiklik dönen arşivlerden birinde
    aynen okunmalı, oyunda var olan arşivden üye düşmemeli, yoksa mod üretilmez (atomik yazım ve "yalnızca değişen
    dosyalar" kuralı aynen). `oyunlar` sınırı uygulanır: biçimler `registry.archive_formats(title_id)`'den gelir,
    okuyucu `registry.member_reader(tree)` ile kurulur (bütün `MemberReader` kurulumları buna geçti; oyun bilinmezse
    yalnızca her oyunda geçerli eklentilerin biçimleri). Kancanın kodu korumalı çağrılır (`GuardedArchiveFormat`,
    `GuardedMemberArchive`: beklenmeyen istisna eklentinin adıyla `ArchiveError` olur, dönüş türleri denetlenir);
    geçersiz biçim yüklemede eklenti hatasıdır. Protokoller `formats.base`'te durduğu için izinli modül listesi
    değişmedi. `arac dogrula` eklenti arşivlerinin üyelerini de gezer (klasör kaynağında oyun bilinmediği için yüklü
    bütün biçimler denenir), `arac eklentiler` biçimleri listeler. Kancayı bildirmeyen eklentide ve yerleşik
    arşivlerde davranış değişmez. Test: `tests/test_plugin_archives.py` (uydurma "KUTU" arşivi ve "SATIR" metni:
    tarama → aktarma → dışa aktarma, `oyunlar` sınırı, `derived_files` üyesi, değişikliği yazmayan `rebuild`'in
    reddi, geçersiz biçim, korumalı hata, `dogrula`).
229. **Güncellemenin TitleID'siyle kayıtlı dosya ana oyuna yazılır:** birleşik görünümde güncelleme ana oyunun ağacına
    bindirilir, ayrı ağacı yoktur; eski sürümlerin projelerinde güncellemeden aktarılmış dosya `…800` TitleID'siyle
    kayıtlı olabiliyor ve dışa aktarma "Oyunda bulunamadı" diyordu. `export_mod` bu grupları (ağacı olmayan `…800`,
    ana oyunun `…000` ağacı varsa) ana oyunun ağacına taşır (`_merge_update_groups`); mod ana oyunun klasörüne yazılır.
    Proje kaydı değiştirilmez.

## 5. Bilinen sınırlar

`TECH_DEBT.md` dosyasına bakın.

> **Not (0.31.15):** GitHub'daki 0.31.7 CSV'yi iki sütuna (orijinal | çeviri) indirmişti; aynı amaç (kimlik/anahtar sütunlarını
> modele göstermemek) kopyadaki TXT/XLSX tasarımıyla karşılandığı için CSV akışı kopyanınkine birleştirildi. Karar ve
> gerekçe CHANGELOG 0.31.15'te.
