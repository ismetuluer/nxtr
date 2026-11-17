# TECH_DEBT — bilinçli olarak bırakılmış işler

Her madde: ne eksik, neden bırakıldı, kullanıcıya etkisi, ne zaman ele alınmalı.
"Cihazda ya da gerçek pencerede deneme" borç sayılmaz: ürün sahibi her sürümü kendisi dener, sorun olursa bildirir.

## 1. Borçlar (düzeltilecek)

12. **Python 3.12 ile test edilmedi.** Geliştirme makinesinde yalnızca 3.13/3.14 kurulu;
    testler 3.13'te çalıştırıldı. Kod 3.12 özelliklerinin üstüne çıkmıyor (`StrEnum`,
    `datetime.UTC` 3.11+). *Ne zaman:* M9 paketlemede sabit sürüm seçilirken.

22. **AssetTable/StringTable ayrımı sezgisel** (tüm değerleri GUID olan tablo metin sayılmaz).
    Kesin ayrım için `Script_monoscripts` bundle'ındaki MonoScript sınıf adları okunabilir.

31. **Satırın hangi sağlayıcı/modelle çevrildiği kaydedilmiyor.** Karşılaştırma için ileride
    `text_entries`'e sağlayıcı/model sütunu eklenebilir.

33. **Taşma denetimi kaba.** Font ölçüsü/kutu genişliği bilinmediği için yalnızca uzunluk oranına
    bakılıyor; gerçek taşma oyunda görülür.

46. **Metin kutusu genişliği denetlenmiyor.** GFMSG biçimi satırları elle `\n` ile bölünür; Türkçe
    metin uzun olursa kutudan taşabilir. *Ne zaman:* M5 QA'ya font ölçüsüyle satır genişliği denetimi.

47. **GFMSG kod türlerinin çoğunun adı tahmini.** Etiketler grup düzeyindedir ("Değişken 0107",
    "Sayı 0202"); yalnızca seçimler, renk ve sayfa kodları kesin olarak çözüldü. Kodlar her durumda
    aynen korunur.


54. **DeepL sözlüğü çok sözcüklü terimlerde uygulanmadı (nedeni bilinmiyor).** İki sözcüklü iki terim
    (5 ve 2 satır) sözlükte olduğu hâlde çeviride kullanılmadı; tek
    sözcüklü ve ad terimleri %100 uygulandı. Terimler çeviriden sonra
    eklenmiş olabilir. Kontrol Et'teki yeni "Sözlük" denetimi bunları bulur.

55. **Çeviri tablosunda ekran dışı satırların yüksekliği ölçülmez.** Kaydırma çubuğunun boyu bu
    yüzden yaklaşıktır ve kaydırırken satırlar hafifçe kayabilir (ARCHITECTURE 51).

68. **Bağlamlı çeviri ve Türkçe üslup kuralları gerçek modelle ölçülmedi (0.28.0).** İstem ve bağlam
    partileri sahte sunucuyla test edildi; gemma4 gibi gerçek bir modelde çıktının ne kadar
    doğallaştığı, bağlamın partileri ne kadar yavaşlattığı denenmedi (`CONTEXT_BEFORE=8`,
    `CONTEXT_AFTER=3`). *Ne zaman:* kullanıcı bir Unity oyununda birkaç sahneyi yeniden çevirip
    karşılaştırınca; gerekirse sayılar ve kurallar ayarlanır.

69. **`gui/main_window.py` hâlâ büyük (0.57.0, ~3.700 satır; 0.63.0'da ~4.100).** Denetimdeki M1'in ilk adımı:
    makine işi iletileri `gui/jobs.py`'ye, son projeler `gui/recent.py`'ye, kurtarma kopyası
    `gui/recovery.py`'ye taşındı. İkinci adım (2026-11-17, ARCHITECTURE karar 221): Kontrol Et
    `gui/checks_controller.py`'ye, Dışa Aktar `gui/export_controller.py`'ye taşındı; pencere ~3.600 satır.
    Kalan: proje yaşam döngüsü (yeni/aç/kaydet/kurtarma), makine işleri (çeviri, redaksiyon, değişiklikler,
    terimler), yazım denetimi penceresi, dış redaksiyon içe/dışa aktarma ve görseller hâlâ pencere sınıfında.
    Testler pencerenin yöntemlerini ve modülün adlarını (`ask_machine_settings`, `provider_factory`,
    `_launch_machine`, `UpdateDialog`, `implicit_terms` …) değiştirerek çalıştığı için aynı düzenle (karar 221:
    yönlendirme + pencere üzerinden çağrı) adım adım taşınmalı.
    *Ne zaman:* bu bölümlerden birine büyük bir özellik eklenirken o bölüm ayrı bir denetleyiciye taşınır.

75. **NNI arşivli oyun: grafik klasörünü üretmek ve seçmek için arayüz yok (0.39.0).** `orijinal/`
    klasörü bir betikle (`export_originals`) üretildi; klasör oyun dosyalarının yanındaki
    `grafik_temizleme` ya da `NXCEVIRI_YS_GRAFIK` ortam değişkenidir. fsd biçimi grafikleriyle aynı
    sınır (TECH_DEBT 49 civarı). *Ne zaman:* arayüzde "Grafikler" ayarı eklendiğinde (iki oyun için ortak).

83. **Bir Unity oyununda metin aktarma yavaş (0.45.0): ≈3 dk.** 179 Unity dosyası (en büyüğü 280 MB)
    üçer kez (`collect_context`, `language`, `extract`) UnityPy ile yükleniyor; metin yalnızca
    `resources.assets`'te. Çözüm adayı: yüklenen `env`'in dosya başına önbelleğe alınması ya da
    `Localization`'ı barındırabilecek dosyaların adla sınırlanması. *Ne zaman:* kullanıcı beklemeyi
    sorun ettiğinde.

85. **Sorunlar panosu küçük eksikleri (0.51.0):** "Sorunlu satırlar" süzgeci tüm satırları anlık
    denetler (büyük projede ilk süzmede yavaş olabilir); iş sürerken yerinde düzenlenen metin
    reddedilince kaybolur; riskli toplu düzeltmelerde ayrıca onay sorusu yok; 8 harften uzun Türkçe
    ek zincirleri terim denetiminde tanınmaz. *Ne zaman:* kullanıcı geri bildirimiyle.

87. **Sayfa içi durum bantları yerinde (0.52.0; 0.52.1'de iş sonuçları bildirime taşındı).** Oyunu Ekle,
    Metinleri Tara, Kontrol Et ve Dışa Aktar sayfalarının bağlamsal uyarı bantları (ör. anahtar dosyası,
    tarama hatası) sayfada durur; iş bittiğinde ya da hata olduğunda ayrıca bildirim kartı çıkar.
    Diyalogların (Ayarlar, Otomatik Çeviri) kendi durum bantları da yerinde. *Ne zaman:* kullanıcı
    geri bildirimiyle.

89. **Görseller adımı yalnızca NNI arşivli oyunda (0.54.0).** fsd biçimi resim çevirisi hâlâ ortam
    değişkeniyle çalışır, RHG doku dönüştürücüsü (`switchtex`) arayüze bağlı değil; ikisi de
    `GraphicsSupport` uygulayınca Dışa Aktar'da kart çıkar. Paket içindeki fontlar (Unity bundle,
    SARC/BFFNT) dışa/içe aktarılamaz; yalnızca serbest TTF/OTF. Gerçek oyunda Görseller kartı ve font
    içe alma elle denenmedi. *Ne zaman:* ilgili oyun yeniden çevrilirken.

90. **Kart ve panel açılış animasyonları yok (0.55.0).** İnceleme §2.10'daki "kısa, amaçlı
    animasyonlar"dan yalnızca maskotunkiler ve kenar çubuğu daralması var; bildirim kartı ve panel
    kayarak açılmıyor. Maskot animasyonu ekransız testte ve kare dökümüyle denendi; gerçek pencerede ve
    yüksek DPI'da elle izlenmedi. *Ne zaman:* kullanıcı geri bildirimiyle.

91. **Dışa aktarma geri okuması oyunun ayrıştırıcısından yumuşak olabilir (0.55.1).** Yapı denetimi eklentinin kendi `extract`ını kullanır; oyunun yerleşik okuyucusu daha katıysa (ör. tırnaksız satır sonu bölen basit CSV okuyucu) bizim okuyucumuz sorunu görmeyebilir. Savunmanın öteki katmanları (çeviriye karışan kod/satır sonu denetimi) bu boşluğu azaltır. Kalıcı çözüm: biçim eklentilerine "satır sonu yasak" gibi bir kural bildirimi. *Ne zaman:* yeni bir oyunda benzer bozulma görülürse.

97. **Unreal argüman ekleri kısmen çözüldü (2026-11-17).** Yalnızca yalın çoğul ifadesi (`{N}|plural(one=a,other=b)`)
    parçalanır (ARCHITECTURE 220). Tırnaklı ya da boş değerli çoğul ve başka ekler (`|gender(…)`, `|ordinal(…)`)
    çözülmez: değişken ile ekin başı tek, katı kod olur, ekin geri kalanı düz metin kalır (makine çevirisi `one=`
    gibi anahtar sözcükleri çevirirse bozulur; denetim bunu görmez) ve ekin içindeki argümanlar serbest sayılır.
    Çoğul seçeneğine boşluk, virgül vb. yazılması Kontrol Et'te görünmez; dışa aktarmada eklenti reddeder ve satır
    "Hatalı" değilse bütün `.locres` dosyası, satırın anahtarını söyleyen hatayla yazılamaz. Bu sürümden önce
    taranmış projede çoğul satırları yeniden taranana dek aynı hatayı verir (yeniden tarama kaynağı değişmiş
    satırları "Hatalı" işaretler). Unreal'ın tırnaksız değer kuralları (boşluk, Türkçe harf) gerçek oyunda
    doğrulanmadı. *Ne zaman:* bu eklerle bir Unreal oyunu çevrilince; ek ayrıştırması motorun belgesine göre
    genişletilir ve seçenek denetimi Kontrol Et'e taşınır.

## 2. Bilinen sınırlar (ihtiyaç doğunca)

2. **Eski NCA0/NCA2 başlıkları desteklenmiyor.** 2017 öncesi geliştirme sürümlerine özgü;
   perakende oyunlarda görülmez. Açık hata verilir.

3. **`CTR_SKIP_LAYER_HASH` (5) ve `CTR_EX_SKIP_LAYER_HASH` (6) şifreleme türleri.**
   Tür 5 açık hatayla reddedilir; tür 6 yama yolunda tür 4 gibi işlenir ama gerçek bir
   örnekle doğrulanmadı. *Ne zaman:* İlk gerçek örnekte.

4. **Okuma sırasında IVFC hash doğrulaması yapılmıyor.** Bozuk veri, RomFS yapısı geçersizse
   yakalanır; ama yapı sağlam görünüp içeriği bozuk dosyalar fark edilmez. NSZ→NSP
   dönüşümünde SHA-256 doğrulaması vardır. *Ne zaman:* M5'te (dışa aktarmadan önce "dosya
   bütünlüğünü doğrula" seçeneği olarak).

5. **Kişiselleştirilmiş (personalized) biletler okunmuyor.** Konsola özgü RSA anahtarı
   gerektirir. Kullanıcının `title.keys` dosyasını seçmesi istenir (arayüz bunu söyler).

6. **Anahtar türetme yapılmıyor.** `prod.keys` içinde türetilmiş anahtarlar
   (`key_area_key_application_XX`, `titlekek_XX`) bulunmalıdır; Lockpick_RCM bunları her
   zaman yazar. Yalnızca `master_key_XX` içeren dosyalar reddedilir ve kullanıcı yönlendirilir.

7. **XCI/XCZ (kartuş dökümü) desteklenmiyor.** M1 kapsamı NSP/NSZ. Gerekirse HFS0 okuyucu
   eklenir.

8. **Delta güncelleme paketleri desteklenmiyor.** Tam güncelleme paketi istenir (açık hata).

9. **Unity/Unreal içerikleri bu aşamada açılmıyor.** Metin olasılığı dosya adı ve imzaya
   göre tahmin ediliyor (ör. Unity Localization `string-tables` paketleri "Yüksek").
   *Ne zaman:* M6 (UnityPy) ve M7 (.locres).

11. **Sözlük gerektiren ZSTD dosyaları açılmıyor** (ör. bazı oyunlarda `zs.dic`). Tarama
    raporunda uyarı olarak görünür. *Ne zaman:* Böyle bir oyun hedeflendiğinde; sözlük
    oyunun kendi RomFS'inden okunabilir.

15. **Yeniden sıkıştırılan Yaz0/ZSTD dosyaları orijinalle bayt bayt aynı değildir.** Oyunlar
    yalnızca geçerli bir akış ister; aynı çıktıyı üretmek Switch'in aracını birebir taklit
    etmeyi gerektirir. Değişmeyen arşivler hiç yeniden sıkıştırılmaz. Yaz0 sıkıştırıcı saf
    Python'dur; çok büyük (onlarca MB) dosyalarda yavaş olabilir. *Ne zaman:* M5'te büyük
    bir oyunla ölçülüp gerekirse hızlandırılacak.

16. **MSBT sınırları:** UTF-32 kodlamalı dosyalar ve TXT2 ofsetleri sıralı olmayan dosyalar
    açık hatayla reddedilir. Orijinal metinde `⟦`/`⟧` karakteri geçerse yer tutucu sayımı
    karışabilir (gerçek oyunlarda beklenmiyor). *Ne zaman:* İlk gerçek örnekte.

20. **Unity'de yalnızca AssetBundle içindeki Localization `StringTable`'ları destekleniyor.**
    `resources.assets`/`sharedassets*.assets` içindeki tablolar, `TextAsset` (JSON/CSV/INK),
    özel diyalog sistemleri ve Unity Localization dışındaki yapılar okunmuyor. Bir Unity oyunu
    için gerekmedi. *Ne zaman:* Bu yapıları kullanan bir oyun hedeflendiğinde.

23. **Değişen Unity dosyasının kabuğu orijinalle bayt bayt aynı değildir.** UnityPy bundle'ı
    yeniden sıkıştırır ve SerializedFile'ı yeniden düzenler (nesne verileri aynı kalır).
    Değişiklik yoksa orijinal dosya aynen korunur.

24. **Türkçe glifler (bir Unity oyunu):** 0.7.0'da denetim ve harf dönüştürme eklendi. Ana statik
    fontlarda `ğ ı İ ş Ğ Ş` yok; dinamik yedek font (LiberationSans) bunları içeriyor. Oyunun yedek
    zinciri kullanıp kullanmadığı cihazda görülecek. 0.12.0: font yaması bu harfleri ana fontlara
    ekliyor; cihazda doğrulandı (2026-10-22).

27. **Uzunluk sınırı (`max_length`) yalnızca istemde bildiriliyor;** dönen çeviri bu sınırı
    aşarsa şimdilik işaretlenmiyor. MSBT ve Unity'de biçimin kendisi sınır koymuyor; asıl kontrol
    M5'teki taşma (QA) denetimi olacak.

28. **Projeler arası ortak çeviri belleği yok;** bellek her projenin içinde.

30. **DeepL v2 sözlük uç noktası.** DeepL v3'ü öneriyor (düzenlenebilir, çok dilli sözlükler). v2
    çalıştığı sürece sorun yok. *Ne zaman:* v2 kullanımdan kaldırılırsa veya kalıcı sözlük gerekirse.

32. **BFFNT font denetimi yok.** MSBT kullanan Switch oyunlarının çoğu BFFNT kullanır; gerçek örnek
    olmadan biçimi güvenle çözmek mümkün değildi. Bu oyunlarda font denetimi "font bulunamadı" der;
    harf dönüştürme yine seçilebilir. *Ne zaman:* İlk MSBT oyununda.

34. **Mod SD karta/emülatöre otomatik kopyalanmıyor.** Bilinçli karar (ARCHITECTURE #28); istenirse
    "emülatör mod klasörüne kur" seçeneği eklenebilir (klasör tespiti emülatöre göre değişir).

36. **Yama pak'ı v7 biçiminde.** Oyunun pak'ı v10/v11 ise motorun eski sürümü okuduğu varsayılıyor.
    Okumazsa yeni dizin biçiminde (tam klasör dizini; gerekirse yol özeti dizini) yazılmalı.

37. **Şifreli pak'lar, Oodle sıkıştırma ve IoStore (.utoc/.ucas) varlıkları desteklenmiyor.** Şifre
    çözmek oyuna özgü AES anahtarı gerektirir (uygulama anahtar aramaz/içermez); Oodle lisanslıdır.

38. **İmzalı pak'lar:** `.sig` dosyası olan oyunlar imzasız yama pak'ını reddedebilir; uygulama yalnızca
    uyarır.

39. **Unreal fontları (UFont .uasset) için glif denetimi yok;** yalnızca .ttf/.otf dosyaları okunur.

40. **Bölgeye göre ayrılmış diller tek tek çevrilir.** Switch oyunlarında "USen" ve "EUen" ayrı
    dosyalardır; kaynak olarak birini seçmek diğerini çevirmez. Konsol hangi İngilizceyi (ABD /
    Birleşik Krallık) kullanıyorsa o seçilmeli. *Ne zaman:* Çeviriyi bir bölgeden diğer bölgenin
    aynı dosyalarına kopyalayan dışa aktarma seçeneği eklenebilir.

41. **Oyuna özgü metin biçimleri desteklenmiyor.** Gerçek oyun taramasında görülenler (bkz.
    `docs/uyumluluk.md`): Unity özel diyalog nesneleri, özel "PACK" arşivi,
    `.yc` (pak.yc biçimi), `.zpbn`, `.gin`. Her biri ayrı format eklentisi gerektirir.
    *Ne zaman:* Ürün sahibinin önceliklendirdiği oyuna göre, yol haritasına eklenerek.

42. **I2 düzen B gerçek oyunda denenmedi.** I2 2.8.x için yazılan TermData dizilimi yalnızca elle
    üretilmiş dosyalarla test edildi. Uymayan bir sürümde kaynak bulunmaz (yanlış veri okunmaz).
    *Ne zaman:* Yeni bir I2 oyununda "metin bulunamadı" görülürse, o oyunun ham verisiyle.

44. **Tip ağacı silinmiş dosyalardaki TextMeshPro fontları için glif denetimi yok** (bir Unity
    oyununun fontları `resources.assets` içinde). Kontrol ekranı bu fontları listeleyemez; Türkçe
    harflerin görünüp görünmediği oyunda denenmeli, gerekirse harf dönüştürme seçilmeli.

45. **GFMSG biçimi fontları için glif denetimi yok.** Oyunun fontları GFMSG biçiminde; Kontrol Et
    ekranı onları listeleyemez. Avrupa dillerinden gelen ç ö ü büyük olasılıkla var, ğ ı İ ş muhtemelen
    yok: oyunda denenmeli, gerekirse harf dönüştürme seçilmeli (font yaması yalnızca TextMeshPro
    fontlarını kapsar).

49. **Font yaması yalnızca TextMeshPro statik fontlarını kapsar.** Unity'nin eski `Font` (bitmap),
    Unreal fontları, GFMSG fontları, BFFNT ve BFTTF fontları ile tip ağacı silinmiş dosyalardaki TMP
    fontları (bir Unity oyunu) yamalanamaz; bu oyunlarda harf dönüştürme kullanılmalı.

50. **Üretilen harflerin görünümü yaklaşıktır.** "ğ"/"Ğ"deki kısa çizgi fontun kendi çizimi değildir
    (noktaların ölçüsünden çizilir); el yazısı veya süslü fontlarda biçim farkı görülebilir. Kutulu
    "etiket" fontlarında İ, ğ, Ğ üretilemez (raporlanır).

51. **Yamalanan font bundle'ları büyür** (atlas verisi bundle'a gömülür, büyütülen atlas iki kat):
    Bir Unity oyununda `fonts_assets_all.bundle` 4,2 MB → 8,1 MB.

53. **Bağlamsız kısa etiketler makine çevirisinde yanlış çıkıyor.** Bir Unity oyununda ~74 satır (%2):
    "On" → "Tarih", "Well" → "Peki", "Safe" → "Güvenli", "Display" → "Görüntüle"… DeepL'e oyun notu
    bağlam olarak gider ama tek sözcüklü satırlar için yetmez. Çözüm elle düzeltmedir; tek sözcüklü
    terimler sözlüğe eklenmemelidir (cümle içlerinde de uygulanır). *Ne zaman:* satır anahtarının
    (ör. `SystemMenu/Display`) DeepL'e bağlam olarak eklenmesi denenebilir.

56. **Hazır çeviri içe aktarma yalnızca Unity metin tablolarını okur.** Başka motorların (MSBT,
    GFMSG .dat, I2…) topluluk yamaları için aynı mantık (anahtarla eşleştirme) uygulanabilir ama
    okuyucular yazılmadı. *Ne zaman:* bir sonraki oyunda hazır bir yama varsa o biçim için eklenir.

57. **Topluluk çevirisinin izni ve emeği.** Uygulama yamayı yalnızca kullanıcının kendi dosyasından
    okur ve mod klasörüne yalnızca metinleri işler; yayımlamak için yama sahibinin iznini almak ve
    kaynağını anmak kullanıcının sorumluluğundadır.

58. **pak.yc biçimindeki yazma, çevrilen satırlarda tüm dilleri Türkçe yapar.** Yerinde yazma (0.17.0)
    cihazda doğrulandı (2026-10-23); ama satırın 11 dil sütunu aynı metni gösterir, oyun dili ne
    seçilirse seçilsin Türkçe çıkar. Dil sütunlarını ayrı tutmak için dosyaya yer açmak gerekir
    (dizin/boyut/özet alanları çözülmedi, `docs/formats/pak-yc.md`). *Ne zaman:* birden çok dil
    korunmak istenirse.

59. **pak.yc biçiminin `tower_global.pak.yc` ve diğer `.yc` paketleri taranmadı.** Yalnızca
    `global*.pak.yc` dil tabloları çözüldü ve yamada karşılıkları var. `menus/*.stb.yc` gibi başka dil
    tabloları varsa aynı ayrıştırıcıyla okunur (başlık satırında `English`/`French` aranır); gerçek
    tarama sonucu henüz doğrulanmadı.

61. **fsd biçiminde yazma yok; okuma eksikleri var (0.20.0).** Yalnızca `fsd` içindeki İngilizce
    diyaloglar ve `etc_e/*.msg` okunuyor. Okunmayanlar: `atm_e/*.atm` (başarım/galeri; ASCII + `0x80`
    kodlu ayrı kodlama), `status_e/st_init.dat` (ikili), `pack` ve doku içindeki yazılar. Yazma için
    `fsd` bölüm dizininin kaydırılması ve Türkçe harflerin (ğ ş ı İ) doku fontuna eklenmesi gerekir
    (`docs/formats/fsd-msg.md`). Çıkarma bu oyunda ~4 dakika sürer (1 GB tarama). Başka iki oyunun
    `.nbz` arşivleri çözülmedi.

62. **M2 PSB biçimi: ana menü etiketleri (ve belki başka ekranlar) metin değil resim olabilir (0.23.0).**
    Cihazda "Game Selection", "Master Book", "Screenplay Book", "Download", "Options", "Legal and
    Privacy" etiketleri değişmedi; bu yazılar arşivde ve kodda düz metin olarak yok. Büyük olasılıkla
    dile göre ayrı resim (`system/motion/txt_en.psb.m` vb.). Doğrulanmadı; doğruysa PSB içindeki
    resimlerin açılıp yeniden çizilmesi gerekir (ayrı iş). *Ne zaman:* kullanıcı bu etiketlerin de
    Türkçe olmasını isterse.

63. **M2 PSB biçimi Master Book düzeni etiketlerle sabitlenmiş (0.23.0).** Sayfa metinleri `<voffset>`,
    `<width>`, `<size=0>` boşluk etiketleriyle görsellere göre hizalı; uzun Türkçe metin taşabilir
    veya kayabilir. Çeviri satırında yüzlerce yer tutucu çıkabilir (makine çevirisinde sorun
    yaratabilir). Cihazda denenmedi. *Ne zaman:* cihaz testinde taşma görülürse.

64. **M2 PSB biçimi yalnızca İngilizce (`eng`) yuvası yazılır; diğer diller değişmez (0.23.0).** Oyun
    dili İngilizce olan oyuncu Türkçe görür; Fransızca/Almanca/İtalyanca/İspanyolca/Japonca seçili
    konsolda eski metin kalır (aynı dizgeyi paylaşan yerler hariç). Gerçek bir Türkçe dil yuvası
    eklemek oyunun dil seçimine dokunmayı gerektirir. Aynı M2 arşiv ailesindeki diğer oyunlar ve PS1
    disk kalıbındaki diyaloglar (`system/roms/*.BIN`) henüz okunmuyor.

65. **SRT ve TSV kaynaklı Unity oyunu: hangi kaynağın okunduğu bilinmiyor (0.24.0; kaynak 0.26.0'da bulundu: `Locoliser` önbelleği).** Metin hem SRT
    altyazı TextAsset'lerinde hem `despelote_loc_monsterFile` TSV'sinde var; oyunun diyalog için
    hangisini okuduğu, UI için `despelote_loc_UI` ile `_original` arasında hangisinin kullanıldığı
    doğrulanmadı (ikisi de yazılır, ~9,6 bin + 6,3 bin satır, çoğu aynı cümle). Türkçe harfler için
    oyun fontları 0.27.0'da yamalandı; `credits[es]` ve resim/sahne içi yazılar (ör. açılış ekranı
    başlığı) çevrilmez. Çeviri yalnızca İngilizce yuvasına yazılır. *Ne zaman:* kullanıcı modu
    Switch'te denedikten sonra; sonuca göre kullanılmayan kaynak aktarmadan çıkarılabilir.

66. **CID anahtarlı CFF fontları yamalanmaz (0.27.0).** `ı İ ş Ş ğ Ğ` ekleme yalnızca TrueType (glyf)
    ve CID olmayan CFF fontlarında çalışır. CID anahtarlı bir Latin fontu çıkarsa harfleri eklenemez
    (rapora "desteklenmiyor" yazılır). Bir Unity oyunundaki tek örnek Çince `HelloFont` (zaten CJK
    sayılıp atlanır). *Ne zaman:* böyle bir oyun çıkarsa.

71. **NNI arşivi ve CPK/FMSB biçimi: bilinmeyenler (0.36.0).** Arşivler aracın kendi okuyucusuyla
    yeniden açılıp doğrulanıyor; bu biçim bir topluluk yamasıyla aynı (sıkıştırılmamış CPK). Bilinmeyenler: NNI arşivli oyunun değişmiş `.ni`/`.na` çiftini kabul edip
    etmediği (dizin imzası/özeti yok gibi görünüyor), uzayan diyalogların kutulara sığması, bu biçimin
    fontunda `ğ ş ı İ` olmadığı varsayımı (doğrudan glif denetimi yapılmadı; `Font_4K/` çözülmedi).
    *Ne zaman:* kullanıcı birkaç satırı çevirip Switch'te denediğinde; sonuç `docs/formats/` belgelerine
    yazılır.

73. **Aktarılmayan metinler (0.36.0).** CPK/FMSB biçimli oyunun yazılı yardım resimleri (`Help/*.ftx`,
    14 doku) çeviri tablosunda yok. *Ne zaman:* resim çevirisi aşamasında (NNI arşivli oyundaki
    `grafik_temizleme` düzeniyle). (NNI arşivli oyunun altyazısı 0.39.0'da `.srt` eklentisiyle
    aktarılıyor.)

74. **NNI arşivli oyun: ana arşivdeki resimler çevrilemez (0.39.0).** "Character Select" başlığı
    (`MENU/CHRSELECT.DDS`), `IMAGE/DIALOG0.DDS` gibi dile bağlı olmayan resimler 946 MB'lık
    `data.ni/.na` içinde; değiştirmek bu arşivin tam kopyasını (`.na` ~946 MB) moda koymayı gerektirir.
    *Ne zaman:* kullanıcı bu resimleri isterse; serbest dosya olarak okunup okunmadığı cihazda denenebilir.
    Ayrıca ana arşivdeki dile bağlı olmayan betiklerde (`MAP/S_90/S_9010/SUBMENU*.XSO` vb.) çevrilecek
    metin var mı bakılmadı (taramada yalnızca `LOC/` aranır).

76. **NNI arşivli oyun yazı tipi yaması görünümü yaklaşıktır (0.39.0).** Breve (`ğ Ğ`) fontun kendi
    çizimi değildir (noktalardan yaylanır); Arial'da çok ince, küçük Libertine'de biraz kalın görünür.
    Yamanın oyunda doğru çizildiği (özellikle `linuxshadow` gölgesi, atlas büyütülmüş fontlar) cihazda
    görülecek. *Ne zaman:* cihaz denemesinde bozuk görünen bir font olursa o font için glif elle çizilir.

79. **WAD/LIN biçimi: resim ve Flash yazıları çevrilemez (0.44.0).** `bin/*.pak` içindeki arayüz
    Flash/doku dosyaları (başlık, menü düğmeleri) ve ilk `.tp` paketlerindeki galeri resimleri taranmaz;
    `common-dr1-all.tp` içindeki karakter adı tabloları (`.pb`) da okunmaz. Bunlar `.lin`/`.pak`
    metinleriyle birlikte oyunun görünen yazılarının küçük bir kısmıdır. *Ne zaman:* cihaz denemesinde
    eksik kalan yazılar görülünce.

80. **Aynı biçimi kullanan başka oyunlar denenmedi (0.44.0).** Aynı yapıyı kullanıyor olabilirler;
    yalnızca ilk oyunun dosyalarıyla doğrulandı. *Ne zaman:* kullanıcı bu oyunları eklediğinde.

82. **Bir Unity oyunu: `ğ ş ı İ` gliflerinin oyun yazı tipinde olup olmadığı denetlenemiyor (0.45.0).**
    TMP yazı tipleri tip ağacı olmayan dosyalarda; font taraması ve font yaması (`fontpatch/unity.py`)
    tip ağacı ister. Yazı tipi görünmüyorsa şimdilik dışa aktarmada harf dönüştürme seçilir. *Ne zaman:*
    cihazda eksik glif görülürse TMP yazı tipi nesneleri ham bayttan okunup yamalanır.

88. **Windows bildirimi yalnızca API düzeyinde denendi (0.52.0).** Gerçek Windows'ta tepsi simgesi
    kuruluyor ve bildirim isteği hatasız kabul ediliyor; Odak Yardımı/Rahatsız Etmeyin açıkken Windows
    bildirimi göstermez.

## 3. Kapananlar

1. ~~Seyrek ve sıkıştırılmış NCA bölümleri~~ — 0.9.0'da çözüldü.
   Kalan: sıkıştırma türü 2 ve 4 (gerçek oyunda görülmedi) açık hata verir.

10. ~~`oead` lisans kararı~~ — **0.3.0'da kapandı:** oead kullanılmadı, SARC/Yaz0 yazıcılar
    kendimiz yazıldı. BYML gerekirse (M2 kapsamında gerekmedi) o da kendimiz yazılacak.
    Ürün sahibi aksi yönde karar verirse yeniden değerlendirilir.

13. ~~Paketleme (PyInstaller onedir) henüz yapılmadı.~~ — **0.31.0'da kapandı:** `packaging/NXCeviri.spec`;
    release iş akışı Windows paketini derleyip release'e zip olarak ekler. Kalan riskler 70. maddede.

14. ~~Gerçek cihaz/emülatör denemesi yok.~~ — **0.59.0 sonrası kapandı (2026-11-16):** ürün sahibi denedi, sorun bildirilmedi.
    M1 dışa aktarma üretmediği için gerekmedi; M5'in bitme ölçütüdür.

17. ~~MSBT gerçek bir oyunla denenmedi.~~ — **0.59.0 sonrası kapandı (2026-11-16):** ürün sahibi denedi, sorun bildirilmedi.
    Geliştirme makinesindeki tek oyun Unity tabanlıdır. Eklenti, LMS biçimine göre elle üretilmiş dosyalarla test edildi.
    *Ne zaman:* Kullanıcı bir Switch LMS oyunu (ör. MSBT içeren bir birinci parti oyun) eklediğinde: aktarma, düzenleme ve (M5'te) oyunda görünürlük doğrulanmalı.

19. ~~Değiştirilmiş Unity bundle'ının oyunca kabul edilmesi.~~ *Doğrulandı (2026-10-22):* ürün sahibi, uygulamanın ürettiği modu (bir Unity oyunu, topluluk çevirisi) Switch cihazında çalıştırdı; metin tablosu bundle'ı kabul edildi. Font bundle'ları için TECH_DEBT 48'e bakın. Eski not: 0.7.0'da
    risk azaldı: katalogda İngilizce metin tablosu kaydının CRC alanı 0 görünüyor (CRC denetimi
    kapalı). Katalog biçimi tam çözümlenmedi. *Ne zaman:* Ürün sahibinin cihaz/emülatör testinde;
    reddedilirse katalogdaki CRC/boyut alanları güncellenmeli.

25. ~~Gerçek bir modelle makine çevirisi denenmedi.~~ — **0.59.0 sonrası kapandı (2026-11-16):** ürün sahibi denedi, sorun bildirilmedi.
    Geliştirme makinesinde 2 GB'lık ekran kartı var. Sağlayıcı ve yürütücü sahte sunucuyla, API biçimleri gerçek Ollama 0.34.4 ile doğrulandı.
    *Ne zaman:* Ürün sahibi RTX A4000 makinesinde deneyecek: kalite, hız, kaç satırın "Hatalı" düştüğü, parti boyutunun uygunluğu ölçülmeli.

29. ~~DeepL gerçek hesapla denenmedi.~~ — **0.59.0 sonrası kapandı (2026-11-16):** ürün sahibi denedi, sorun bildirilmedi.
    Sağlayıcı resmi API belgelerine göre yazıldı ve sahte sunucuyla test edildi. *Ne zaman:* Ürün sahibi bir DeepL anahtarıyla denediğinde: Türkçe sözlük oluşumu, etiket taşıma sıklığı ve kota gösterimi doğrulanmalı.

35. ~~Unreal gerçek oyunla denenmedi.~~ — **0.59.0 sonrası kapandı (2026-11-16):** ürün sahibi denedi, sorun bildirilmedi.
    .locres ve .pak biçimleri bilinen yapılarına göre yazıldı ve elle üretilmiş dosyalarla test edildi. *Ne zaman:* İlk Unreal oyununda tarama, aktarma ve yama pak'ının oyunda yüklenmesi doğrulanmalı.

48. ~~Font yaması oyunda denendi.~~ *Doğrulandı (2026-10-22):* Bir Unity oyununda yamalı fontlarla Türkçe harfler cihazda sorunsuz göründü. Eski not: Yamalı font bundle'ı uygulama içinde okunup metin
    çizilerek kontrol edildi; oyunun (Addressables CRC denetimi, TMP sürümü, büyütülmüş atlas) kabul
    edip etmediği cihazda görülecek (TECH_DEBT 19 ile aynı risk).

60. ~~Paketlemede `qtbase_tr.qm` taşınmalı.~~ — **0.31.0'da kapandı:** PyInstaller'ın PySide6 kancası
    `PySide6/Qt/translations/qtbase_tr.qm` dosyasını pakete koyuyor (Linux derlemesinde doğrulandı). Eski not: Qt standart metinleri Türkçe gösterilsin diye başlangıçta PySide6/translations/qtbase_tr.qm yüklenir; taşınabilir pakette bu dosya yoksa menü ve düğmeler İngilizce kalır (uygulama çalışır, günlüğe uyarı yazar). *Ne zaman:* M9 paketlemede.

67. ~~Sürüm yayımlanmadan önce testler CI'da çalışmıyor (0.28.0).~~ — **0.31.0'da kapandı:** `tests.yml`
    Windows runner'da ruff, mypy ve pytest çalıştırır; her PR'da ve release'ten önce (release ona bağlı). Eski not: `release.yml` yalnızca etiketi ve release'i
    oluşturur. Test takımının bir kısmı Windows'a özgü (yazı tipleri, Kimlik Bilgisi Yöneticisi), Linux runner'da
    8 test ortam yüzünden geçmiyor; bu yüzden CI testi şimdilik eklenmedi, testler PR'dan önce yerelde çalıştırılıyor.
    *Ne zaman:* Windows runner'lı test iş akışı kurulunca release ona bağlanır.

70. ~~Taşınabilir paketin uçtan uca akışı Windows'ta elle denenmedi~~ — **0.38.0'da kapandı:** paket Windows 11'de
    derlendi (PyInstaller 6.22.3, 137 MB) ve ürün sahibi 2026-11-01'de paketle oyun ekleme → tarama → çeviri →
    dışa aktarma akışını denedi, çalışıyor. Bilinen ve kabul edilen: `.exe` imzasız olduğu için SmartScreen
    "Bilinmeyen yayımcı" uyarısı verebilir; paket kendini güncelleyemez, yeni sürüm sayfası tarayıcıda açılır.

78. ~~WAD/LIN biçimi mod cihazda denenmedi (0.44.0).~~ — **0.59.0 sonrası kapandı (2026-11-16):** ürün sahibi denedi, sorun bildirilmedi.
    WAD yeniden kuruluyor ve gerçek `dr1_data.wad` ile değişiklik yokken bayt bayt aynı, ama oyunun WAD'ı bütünlük denetiminden geçirip geçirmediği (`.tp` paketlerindeki 16 baytlık
    özetler) ve `ğ ş ı İ` gliflerinin oyun yazı tipinde olup olmadığı bilinmiyor. *Ne zaman:* ilk cihaz denemesinde; glif yoksa font yaması bu oyun için yazılır, şimdilik harf dönüştürme geçerli.

81. ~~Bir Unity oyunu mod cihazda denenmedi (0.45.0).~~ — **0.59.0 sonrası kapandı (2026-11-16):** ürün sahibi denedi, sorun bildirilmedi.
    Dışa aktarılan `resources.assets` UnityPy ile yeniden yazılıyor ve nesneleri 8 bayta hizalıyor (güncellemedeki orijinal 16'ya hizalıydı; v0 ve Rusça yama 8). Nesne tablosu
    ofsetleri açık olduğundan sorun beklenmiyor ama doğrulanmadı. Oyunun hangi sistem diliyle hangi dil yuvasını okuduğu da
    doğrulanmadı (yalnızca Rusça yamanın 0'ı değiştirdiği biliniyor; ikinci İngilizce yuva 7'ye özdeş satırlar yansıtılıyor).
    *Ne zaman:* ilk cihaz denemesinde.

84. ~~Kontrol Et → Denetle ana iş parçacığında çalışıyor~~ — 0.52.1'de arka plana alındı. **(0.51.0)** 50.000 satırda birkaç saniye sürebilir. Arka plana
    almak denetim testlerinin çoğunu eşzamansız yapacağından ertelendi; diğer yeniden denetimler (Terim değil, Yoksay,
    Değiştir) arka planda. *Ne zaman:* D aşaması (bildirimler) ile.

93. ~~Sıraya bağlı test (0.59.0).~~ — **0.59.0 sonrası kapandı:** bir sayfa testi uygulama temasını değiştirip geri
    almıyordu (`tests/test_qa_layout.py`); sonraki testlerin yazı tipi ve yerleşimi değişiyordu. Fixture temayı
    geri yükler.

94. ~~Tek ölçümlü süre testleri (0.59.0).~~ — **0.59.0 sonrası kapandı:** süre testleri en iyi ölçüme bakar
    (`tests/perf.py` `best_time`); eşikler değişmedi. Durum biriktiren birkaç test bilerek tek ölçümde kaldı.

96. ~~İki tablo rolü aynı numarayı paylaşıyor (0.59.0).~~ — **0.59.0 sonrası kapandı:** çeviri tablosunun rolleri
    tek katalogda (`gui/table_roles.py`); değerlerin farklı olduğu testle korunur.
95. ~~Sığdırmada anahtar adı her biçimde bağlamdan alınıyor (0.59.0).~~ — **0.59.0 sonrası kapandı:** bağlamın son
    parçası yalnızca koleksiyonlu biçimlerde (Unity, Unreal) anahtar adı sayılır (`key_names`, `in_collection`).

18. ~~Çeviri tablosunda geri al (undo) yok.~~ — **Kapandı:** Geri Al (oturum içinde son 100 işlem; toplu işler tek
    adım) daha önce eklenmişti, kayıt eskimişti; Yinele 0.60.0 sonrasında eklendi. Yığın oturumluktur; kalıcı
    değişiklik geçmişinden satır bazlı geri dönüş ayrıca vardır.

77. ~~Yazım denetimi düzeltme önerisi vermez (0.43.0).~~ — **Kapandı:** öneriyi uygulamanın kendisi üretir
    (`core/spell/suggest.py`, çevrimdışı, yapay zekâ yok): sözcükten aday yazımlar üretilip her biri Bloom süzgecine
    (yanlış olumlu oranı %0,1; ölçümde rastgele dizilerde %0,07) sorulur. Önce Türkçe harf değişimi (ı↔i, ş↔s, ğ↔g,
    ü↔u, ö↔o, ç↔c; en çok 3 harf, en çok 12 değişebilir konum: aday sayısı ≤ 298), yalnızca o boşsa fazla ya da yer
    değiştirmiş tek harf (≈ 2·uzunluk aday; ilk harf korunur, ≥ 4 harf, en çok 2 isabet). Eksik ve değişmiş harf
    ARANMAZ: ≈ 58·uzunluk aday, gerçek projede beklenen uydurma isabet gerçek isabetten çoktu. Aday başına %0,1 risk:
    toplu düzeltmeye yalnızca harf değişimiyle tek isabet girer ve ya aday sayısı ≤ 7 (risk ≤ %0,7) ya da kök
    doğrulanmıştır; tek düzenleme toplu düzeltmeye hiç girmez; toplu düzeltme onay ister. Sınırlar: sözlükte olmayan
    ama doğru sözcüğün (özel ad, sözlükte olmayan ek zinciri) sözlükteki yakın bir akrabaya çevrilmesi önerilebilir
    ("öğeyi" → "ögeyi", "güldene" → "guldene"); bu Bloom gürültüsü değil sözlük kapsamıdır, bu yüzden toplu
    düzeltme önce Öneri sütunundan gözden geçirilir ve Geri Al ile döner. Önerilerin sırası olasılığa değil değişen
    harf sayısına dayanır (sözcük sıklığı bilinmiyor). *Olası iyileştirme:* Türkçe harf silen önerileri toplu
    düzeltmeden çıkarmak (gerçek projede güvenli sınıfın 109/257'si).

86. ~~Ollama belirteç tahmini kaba~~ — **Kapandı:** tahmin CJK (kana, Kanji/Çince, Hangul) karakterini ~1 belirteç, Latin metni karakter/3 sayar (estimate_tokens, prompt_weight; ollama.py). Gerçek sayı modele göre değişir; parti tahminden uzun çıkarsa num_ctx yine bir basamak yükselir.

92. ~~Türkçe harf onarımı sözlüğe bağlı~~ — **Kapandı:** ASCII biçimi sözlükte geçerli olsa da yaygın yazım hatası olan sözcükler (simdi, sey, aksam, buyuk, tum, basla, yasam) küçük bir listeyle (asciitr._ASCII_MISTAKES) onarılır. surat (sürat) gerçek bir sözcük olduğu için listede yoktur; eşyazımlılar (cok → çok/çök) seçime kalır. Kalan: hatalı satırlarda kod onarımı ile harf onarımı ayrı geçişlerde çalışır; düzeltme onay kutusu için arayüz testi yok.

72. ~~CRILAYLA açma yavaş~~ — **Kapandı:** açma döngüsü hızlandırıldı: akış bir kez 0/1 dizgesine açılıp dilim + int(…, 2) ile okunuyor, geri başvurular dilimle kopyalanıyor. Elle üretilmiş 2 MB'lık rastgele geçerli akışta en iyi süre 0,649 sn -> 0,199 sn (~3,3 kat), çıktı bayt bayt aynı (testte bit bit başvuru açıcıyla karşılaştırılır). İlk geçişte dili yoldan belli dosyaları atlamak (pipeline değişikliği) yapılmadı.

21. ~~Smart String ifadeleri tek bir kontrol kodu sayılıyor~~ — **Kapandı:** çoğul ifadesi (iki ya da daha çok dallı {0:plural:a|b}) artık ayrılıyor: iskeleti ({0:plural:, her |, kapanış }) sıralı ve katı kod, dalların sözcükleri çevrilebilir (markup.tokenize plural=True; yalnızca Unity kullanır). Yer tutucu sözleşmesi (sayı/sıra/tür) değişmedi; round-trip bayt bayt aynı. Tek dallı çoğul ve choose/cond/list gibi öteki ifadeler tek kod olarak kalır. Gerçek bir oyunda denenmedi; Türkçe çoğul dalı sayısı kaynak dilden azsa çeviride yine tüm ayraçlar bulunmalıdır.

26. ~~Yer tutucu sırası katı denetleniyor.~~ — **Kapandı (ürün sahibinin kararı, 2026-11-17):** biçim eklentisi
    `paired_code` ile bildirdiğinde aç/kapa çifti iç içeliği bozulmadan bütün olarak taşınabilir; satır uyarıdır,
    dışa aktarılır (ARCHITECTURE 219). Bildirmeyen eklentide (GFMSG, fsd, kullanıcı eklentileri) çiftler katı kalır.

52. ~~Kontrol kodu sırası katıdır; Türkçe cümle yapısı bunu sık bozar.~~ — **Kapandı:** serbest kodlar (0.62.0) ve
    bütün olarak taşınan aç/kapa çiftleri (2026-11-17, ARCHITECTURE 219) uyarıdır. Kalan: satır/sayfa sonu ve
    konumsal kodların (`%s`) sırası bilerek katıdır; MSBT'de rengi yeni bir renk etiketiyle sıfırlayan oyunlarda
    (0x0F kapanışı yok) renk kodları çift sayılmaz, katı kalır.

43. ~~I2 kaynak dili dil listesinde görünmüyor.~~ — **Kapandı (2026-11-17):** `FormatPlugin`'e isteğe bağlı
    `languages(data)` kancası eklendi (I2 için Unity eklentisi uygular); `pipeline.scan_sources` tarama sonunda
    kancayı uygulayan eklentilerin dosyalarını okur, dil kodlarını kaydın `detail` ekine yazar (proje yeniden açılınca
    kalır) ve `available_languages` bunları toplar. Kalan: tarama, kancalı eklentinin dosyalarını (Unity
    `.assets`/bundle) bir kez daha okuduğu için büyük oyunlarda tarama uzar.
