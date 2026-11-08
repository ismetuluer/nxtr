# NXTR kullanılabilirlik incelemesi (2026-11-09)

Kaynak: ürün sahibinin 5 ekran görüntüsü ve kullanım notları + kodun incelenmesi. Amaç: "yetenekli ve işlevsel ama
kullanışlı değil" tespitini somut sorunlara, nedenlere ve çözümlere dökmek.

## 1. Özet: kullanışsızlığın beş kök nedeni

1. **Ekran alanı israf ediliyor.** Sabit sol çubuk, üç kez tekrarlanan satır sayısı, orta hizalı ve yüksek satırlar,
   sığmayan sütunlar, yer kaplayan Düzeltmeler bölümü. Küçük ekranda asıl iş olan *orijinal ↔ çeviri* sıkışıyor.
2. **İş iki ekrana bölünmüş.** Kullanıcı zamanının çoğunu Çevir'de geçiriyor; ama sorunları görmek, düzeltmek, yazım
   hatasını bulmak için Kontrol Et'e gidip geri dönmek zorunda. Kontrol Et'teki bulgu da yerinde düzeltilemiyor.
3. **Durum metinle anlatılıyor.** "Makine", "Anahtarlar doğrulandı", "%100 çevrildi", "Hatalı: 4 (dışa aktarılmaz)"
   gibi metinler dar sütun ve çubuklara sığmıyor; göz taramayı zorlaştırıyor. Sembol + ipucu daha hızlı okunur.
4. **Hata ve bildirim dili zayıf.** Uzun açıklama paragrafları (Terim Öner hatası), arka planda duran bir çevirinin fark
   edilmemesi, ne yapılacağını söylemeyen mesajlar. Kullanıcı süreçten koparsa programdan haber alamıyor.
5. **Kişiselleştirme yok.** Sütun gizleme/hatırlama, kısayol düzenleme, ayarlar penceresi, kendi talimat/terminoloji
   kitaplığı yok. Her projede aynı şeyler baştan yapılıyor.

## 2. Ekran ekran bulgular

Notların hepsini korudum; ekran görüntülerinden ve koddan eklediklerim **[ek]** işaretli.

### 2.1 Genel pencere
| Sorun | Neden / not | Öneri |
|---|---|---|
| Küçük ekranda sol adım çubuğu yer kaplıyor | Çubuk sabit genişlikte | Daraltılabilir kenar çubuğu: yalnızca simgeler (Mail/Finder gibi), `Ctrl+Alt+S`, durum hatırlanır |
| Uzun durum çubuğu metinleri | Her bilgi cümleyle yazılmış | Simge + sayı; ayrıntı ipucunda (§2.5) |
| Fare tekerleği satır atlıyor **[ek: nedeni bulundu]** | Tablolar "satır satır" kaydırıyor; satır yükseklikleri farklı olduğu için uzun satırda sıçrama oluyor | Tüm tablolarda piksel bazlı (yumuşak) kaydırma — küçük bir değişiklik |
| Ayarlar dağınık | Ayar yok; seçenekler sayfalara ve menülere serpiştirilmiş | **Ayarlar penceresi** (`Ctrl+,`): Genel, Görünüm, Kısayollar, Anlık denetimler, Çeviri sağlayıcıları, Güncelleme |

### 2.2 Çevir ekranı (en çok kullanılan)
| Sorun | Neden / not | Öneri |
|---|---|---|
| Satır bilgisi üç yerde (başlık altı, tablo altı, durum çubuğu) | Sadeleştirmede kaldı | Yalnızca durum çubuğunda kalsın; tablo altı ve başlık altı satırı kalkar |
| Çeviri paneli küçük ekranda sağa kaçıyor, tablo sıkışıyor | Panel "alt" seçili olsa da yükseklik yetmeyince sağa geçiyor (otomatik kural) | Panel gizle/göster düğmesi (kenar simgesi, `Ctrl+J`), alt/sağ kararı kullanıcıda; yer yoksa paneli kapat, tabloyu küçültme |
| Yatay kaydırma kendiliğinden kayıyor; tıklayınca hücre ortalanıyor | Sütunlar pencereye sığmıyor; Qt seçilen hücreyi görünür yapmak için kaydırıyor | **Akıllı sığdırma:** Orijinal ve Çeviri her zaman pencereye sığar, diğer sütunlar kalan yere; yatay kaydırma yalnızca kullanıcı isterse |
| Sütun gizleme yok | — | Başlığa sağ tık → sütun aç/kapat, hatırlanır (Çevir ve Kontrol Et tablolarında) |
| Satır numarası yok | — | **No** sütunu (aktarım sırası, sabit); arama "#120" ile satıra gider |
| Sıralama "1, 10, 11, 2" | Metin sıralaması | Doğal sıralama (1, 2, 3 … 10, 11 … 100) |
| Durum sütunu uzun yazılar | Metin rozet | Simgeler: makine (mavi bilgisayar), redaksiyon (yeşil bilgisayar), onaylı (yeşil kişi), uyarı (sarı üçgen), hata (kırmızı üçgen), çevrilmedi (gri boş daire); ipucunda açıklama ve sorunlar |
| Grup ve anahtar süzgeci tek seçimli | Açılır liste | Excel tarzı çoklu seçimli süzgeç: başlıktaki huni simgesi → arama + onay kutuları; Anahtar sütununda da |
| Sembol göster açık ama tabloda yalnızca boşluk noktası var; satır sonu/sekme görünmüyor **[ek: ekran 2]** | Tablo çizicisi semboller için ayrı | Word gibi: ¶ satır sonu, ↵ elle satır sonu, → sekme, · boşluk, kontrol kodu çipleri; panelde ve tabloda aynı |
| Sözcükler ortadan bölünüyor ("yiyorsun / ." gibi) | Hücre kaydırması karakter bazlı düşüyor | Sözcük sınırında kaydırma; çok uzun tek sözcük için yalnızca son çare bölme |
| Yazım hataları tabloda görünmüyor | Dalgalı çizgi yalnızca panelde | Tabloda da kırmızı dalgalı çizgi + **Araçlar → Yazım Denetimi** penceresi (Sigil benzeri: sözcük, sayı, Yoksay / Sözlüğe ekle / Hepsini şununla değiştir) |
| Görünüm menüsü ekranda yer kaplıyor; "Önceki çeviri sütunu" hep pasif | Pasifliğin nedeni: yalnızca son işte değişiklik varsa açılır | Görünüm seçenekleri menü çubuğuna; pasif öğe yerine "Son işte değişiklik yok" ipucu |
| Orijinalden kopyalanamıyor | Orijinal hücre/panel salt okunur ve seçilemiyor | Salt okunur ama seçilebilir/kopyalanabilir metin |
| Satırdaki karakter sınırını görmek zor | Panel yalnızca toplam karakteri gösteriyor | Panelde canlı sayaç: "en uzun satır 23/28" (sınır: orijinalin en uzun satırı **ya da** elle girilen sınır; elle girilen açıksa o esas alınır), aşınca kırmızı |
| Grup/anahtar başına sınırlar elle yönetiliyor | Grup kuralı var ama anahtar yok; görünürlüğü düşük | Sınırlar tablosu: grup **ve** anahtar desenleri için satır sayısı, en uzun satır, öğrenilen sınır, elle sınır; "Hepsini öğren" otomatik |
| Panel başlığında anlamsız "/(...g)" **[ek: ekran 1]** | Anahtar adı kesiliyor | Başlıkta "No 1 · grup" gibi kısa kimlik, tam anahtar ipucunda |
| Satırları yeniden böl gibi sık işler kısayolsuz | — | Kısayollar (aşağıda), adlar "Ctrl+Shift+…" biçiminde |
| Bağlam menüsü karışık; "Daha fazla" belirsiz | Gruplama yok, uzun adlar, simge yok | Gruplu kısa menü (simgeli): **Çevir ▸** (Çevir, Yeniden çevir, Redaksiyon) · Onayla / Onayı kaldır · **Düzenle ▸** (Satırları yeniden böl, Orijinali yaz, Temizle) · **Kopyala ▸** · **Dışa aktar ▸** · Geçmiş · Yerinde göster |
| "Daha Fazla" ve "Makine Çevirisi…" düğmeleri | Menüye taşınabilir | Menü çubuğu: **Dosya** (proje, içe/dışa aktar), **Düzen** (geri al, bul/değiştir, yeniden böl), **Görünüm**, **Çeviri** (Otomatik Çeviri `Ctrl+T`, Redaksiyon `Ctrl+R`, Terminoloji), **Araçlar** (Yazım Denetimi, Eklentiler, Teşhis), **Yardım**. Sayfadaki tek birincil düğme: Otomatik Çeviri |

### 2.3 Otomatik Çeviri (eski adı Makine Çevirisi) — ekran 4
| Sorun | Öneri |
|---|---|
| "Kaynak dil / en" düzeni bozuk, Model boş, kapsam "0 satır" ama Başlat açık görünüyor **[ek]** | Sade düzen: Sağlayıcı · Model · İş (segmentli: Çevir / Yeniden çevir / Redaksiyon) · Kapsam (çoklu: tümü, seçili, grup, **anahtar**) · Başlat. Uygun satır yoksa Başlat pasif ve nedeni tek satır |
| Oyun notları ve talimat iki ayrı kutu | İkisi de **gerçekten modele gidiyor** (sistem isteminde). Kavramları netleştir: **Oyun hakkında** (projede kalıcı: tür, dönem, ton) ve **Bu iş için talimat** (tek seferlik). İkisi de "Talimat kitaplığı"ndan seçilebilir |
| Hazır talimatlara ekleme yapılamıyor | **Talimat kitaplığı** (AppData'da): kendi talimatlarını kaydet, başka projede/oyunda kullan |
| Anahtara göre ton (Despelote "Bölüm 1 çocuklar") | Kapsamda anahtar/grup desenine göre seçim + talimat |

### 2.4 Terminoloji (eski adı Sözlük)
| Sorun | Öneri |
|---|---|
| "Sözlük" iki anlamda (oyun terimleri / yazım sözlüğü) | **Terminoloji** (oyun terimleri) ve **Yazım sözlüğü** ayrı adlar |
| Terminoloji projeye hapsolmuş | AppData'da **terminoloji kitaplığı**: "DMC serisi" listesi DMC2'de doğrudan açılır, birden çok liste birleştirilebilir |
| Boş satır ekleniyor, uzun sütun adları, "Daha Fazla" gereksiz | Boş satır kaydedilmez; sütunlar: Terim · Karşılık · Not; İçe/Dışa Aktar ve Terim Öner ayrı küçük düğmeler |
| Ollama yokken dev bir açıklama paragrafı | Kısa hata: "Ollama'ya bağlanılamadı." + **Ayarları Aç** / **Kapat** |

### 2.5 Durum çubuğu ve bildirimler
- Simgeler: anahtar (yeşil/kırmızı), sağlayıcı (DeepL: ipucunda kalan kota; Ollama: ipucunda model, GPU/CPU payı,
  bellekte kalan süre — Ollama'nın `/api/ps` uç noktasından ucuzca alınır), ilerleme, sorun sayısı (tıklayınca Sorunlar),
  kayıt durumu.
- **Bildirim merkezi:** uzun iş durunca ya da hata olunca ses + Windows bildirimi + pencere içi kart:
  "Çeviri durdu: Ollama 3 dk yanıt vermedi." **[Tekrar Dene] [Kapat]**. Başarıyla bitince kısa bildirim.

### 2.6 Kontrol Et → **Sorunlar** — ekran 5
| Sorun | Öneri |
|---|---|
| Düzeltmeler bölümü çok yer kaplıyor | Daraltılabilir kenar paneli |
| "Seçili satırlarda düzelt" muğlak | "Listede seçtiğim N bulgu" / "Tüm bulgular" açık seçim |
| Sağ tıkta her zaman pasif "Yazım sözlüğüne ekle" | Bağlama göre: Bu satırı düzelt · Bu türdeki tümünü düzelt · Yerinde göster · (yalnızca yazım bulgusunda) Sözlüğe ekle |
| Bulgu yerinde düzeltilemiyor | Çeviri hücresi bu tabloda düzenlenebilir; kayıt anında, bulgu kendiliğinden yeniden denetlenir |
| Düzeltme türleri ne yapıyor belli değil | Her türde 1 cümlelik ipucu + örnek ("Sondaki noktalama: orijinalde olmayan son noktayı siler") |
| Hangi türde bulgu var görünmüyor | Tür süzgeci çip listesi: "Satır sonu 22 · Sondaki noktalama 178 …"; boş türler gizli |
| İşaretli ama soluk (0 bulgulu) kutular kafa karıştırıyor; "Sondaki noktalama" varsayılan açık **[ek]** | 0 bulgulu türler gizlenir; riskli toplu düzeltmeler varsayılan kapalı |
| Sütun boyutu ayarlanamıyor, gizlenemiyor | Çevir tablosuyla aynı sütun davranışı |

**Anlık denetim (sorunuz):** maliyeti düşük. Satır başına denetimler (kod, etiket, uzunluk, satır sonu, boşluk,
noktalama, yazım) bir satırda milisaniyelerin altında çalışır; satır kaydedilince yalnızca o satır denetlenir. Proje
geneli olan tek denetim "tutarsız çeviri"dir; o da kaynak metne göre dizinle artımlı yapılabilir. Yani **anlık denetim
verimi düşürmeden kurulabilir**. Öneri: Kontrol Et sayfası **Sorunlar panosuna** dönüşür (sayılar, süzgeç, toplu
düzeltme); asıl düzeltme Çevir ekranında, durum simgesi ve ipucuyla anlık görünür. Hangi denetimlerin anlık çalışacağı
Ayarlar → Anlık denetimler'de seçilir.

### 2.7 Sığdırma sekmesi
- **Kod türleri ne işe yarar:** oyundaki kontrol kodlarının (⟦1⟧ gibi) ne olduğunu söyler: satır sonu, sayfa sonu,
  değişken (oyuncu adı), sembol, biçim. Program sınır hesabında satır sonunu yeni satır sayar, değişkene tahmini
  genişlik verir, panelde kodları renkli çip olarak gösterir. Uygulama çoğunu tahmin eder; kullanıcının yalnızca
  tahmin yanlışsa (ör. satır sonu kodu "diğer" görünüyorsa) değiştirmesi gerekir. Öneri: bölüm "Gelişmiş"e iner,
  yanlış tahmin şüphesi varsa uyarı çıkar.
- **"Düzeltirken temizle"** (gereksiz boşluk, noktalama öncesi boşluk, tekrarlı noktalama): sığdırma düzeltmesinin
  yan temizliği. Sorunlar'daki "Çift boşluk/Fazla nokta" ile çakışıyor → kaldırılır, tek yer Ayarlar → Düzeltmeler.

### 2.8 Dışa Aktar
- Dolu klasöre yazmayı reddediyor (bilerek: eski dosya kalıntısı karışmasın diye). Öneri: "Klasör dolu" uyarısında
  **Üzerine Yaz** (eski modu siler, yenisini yazar) / **Başka Klasör** seçenekleri.

### 2.9 Font ve grafik (bağımsızlık)
- **Font:** Font ve harfler sekmesine her fontun *neden* yamanabildiği/yamanamadığı (TMP statik / dinamik, BFFNT,
  bitmap doku…) ve hangi aracın gerektiği. Yamanamayan fontu dışarıda düzenlemek için "Fontu Dışa Aktar" / "Düzenlenmiş
  Fontu İçe Al" (biçim destekliyorsa).
- **Grafik:** bugün "orijinal/temiz" klasörünü ben üretiyorum (Ys Origin'de bir betik). Uygulamaya **Görseller** adımı:
  resim metni olan dokuları PNG olarak dışa aktar → kullanıcı düzenler → klasörü göster → dışa aktarmada otomatik yamaya
  girer. Desteklenen doku biçimleriyle sınırlı (DMC1, Ys Origin, RHG); diğerleri için ajan rehberi.

### 2.10 Görsel kimlik ve canlılık
- Kart tasarımı sürer; animasyonlar amaçlı ve kısa (panel açılışı, bildirim kartı, ilerleme), Windows "animasyonları
  azalt" ayarına uyar.
- **Maskot:** logodaki Joy-Con'lar; düğmeler göz olur. Durum çubuğunda küçük; hâlleri: boşta, çalışıyor (bakınır),
  bitti (sevinir), hata (endişeli), uyku (uzun boşta). Bildirim kartlarında da görünür. Kapatılabilir.

### 2.11 Katkı ve yardım
- `docs/rehber/katki.md` birden çok yerel kopya + farklı ajan senaryosunu adım adım anlatmalı: fork, dal, eklenti
  klasörü, `dogrula`, çekme isteği; aynı oyun için çakışan iki eklenti.
- Uygulama içi **Yardım** (F1): rehberlerin kullanıcı sürümü, aranabilir, ekran adlarıyla.

### 2.12 Bul ve Değiştir
Bugün ayrı bir pencerede toplu iş gibi çalışıyor; tabloda gezinmeye izin vermiyor. Öneri: **tablonun üstünde açılan
satır içi çubuk** (`Ctrl+F` bul, `Ctrl+H` değiştir), pencere değil:
- Bul kutusu yazdıkça eşleşmeler tabloda **boyanır**, sayaç "3 / 41"; **Sonraki / Önceki** (`F3` / `Shift+F3`) satırı
  yerinde gösterir. Kullanıcı istediği satırı elle de düzenleyebilir; çubuk açık kalır.
- Değiştir kutusu + **Önizle** onay kutusu: açıkken değişiklik satırlarda yeşil/kırmızı boyalı olarak görünür ama
  yazılmaz; kapatınca önizleme kaybolur.
- **Değiştir** (o anki), **Tümünü Değiştir** (tek iş olarak geçmişe, `Ctrl+Z` hepsini geri alır).
- Seçenekler simgelerle: Aa (büyük/küçük harf), tam sözcük, düzenli ifade, kapsam (tümü / görünenler / seçili),
  alan (çeviri / orijinal). Kontrol kodları korunur; kodu bozacak değişiklik uygulanmaz ve sayılır.

### 2.13 Cümle içindeki tutarsız terimler (örtük terminoloji)
Bugünkü "Tutarsız çeviri" yalnızca **satırın tamamı** aynıysa yakalar. Oysa mekân/karakter adları çevirdikçe kendi
terminolojisini oluşturur; uzun cümlede farklı çevrilmesi kaçar.
- **Yöntem:** oyunda kendi başına bir satır olarak geçen kısa ifadeler (menüdeki mekân adı, eşya adı, bölüm adı) ve
  terminolojideki terimler "kanonik çeviri" sayılır. Kaynağında bu ifade geçen her satırın çevirisinde kanonik çevirinin
  geçip geçmediğine bakılır. Türkçe ek (`Gümüş Çamlar'a`, `Gümüş Çamlar'daki`) ve büyük/küçük harf farkı yok sayılır;
  satır sonu, elle satır sonu, sayfa sonu kodu ve fazla boşluk tek boşluk sayılır, yani bölünmüş ifade de bulunur.
- **Maliyet:** dizin bir kez kurulur, satır başına yalnızca sözlük araması yapılır. Bu yüzden — sizin tahmininizin aksine —
  anlık denetim olarak da çalışabilir; proje geneli listesi Sorunlar panosunda "Terim tutarsızlığı" olarak durur.
- **Kapsam daraltma:** yalnızca 1–4 sözcüklü, en az iki satırda geçen ve büyük harfle başlayan (özel ad) ifadeler; kullanıcı
  bir ifadeyi "terim değil" diye işaretleyebilir. Bulguda: "‘Silver Pines’ burada ‘Gümüş Çam’ olmuş; 14 satırda ‘Gümüş
  Çamlar’" + **Kanonik çeviriyle değiştir**.
- Ollama tarafı: çeviriden önce kanonik terimler (terminoloji + kısa satırlar) partiye eklenirse tutarsızlık baştan azalır.

### 2.14 Satırları terminolojiye ekle
Önce mekân/karakter adlarını çevirtip sonra onları terminolojiye eklemek tutarlılığı sağlar. Öneri: tabloda satırları
seç → sağ tık **Terminolojiye ekle** (`Ctrl+Shift+G`). Eklenen: kaynak ve çeviri, kontrol kodları, satır sonları,
baştaki/sondaki noktalama, sayılar ve semboller ayıklanmış hâliyle; zaten varsa atlanır, çakışan karşılık varsa sorulur.
Önce küçük bir onay listesi görünür (işaretini kaldırdığın eklenmez).

## 3. Sorularınızın cevapları (Ollama)

- **Oyun notları ve talimat modele gidiyor mu?** Evet, ikisi de her partide sistem isteminin içinde gider (notlar:
  oyun bağlamı; talimat: yalnızca o işte). Redaksiyon talimatı kullanıcı mesajında gider.
- **Neden sıralı gitmiyor, satır atlıyor?** İş projenin aktarım sırasına göre gider, ama: (1) aynı kaynak metin tek
  kez çevrilip hepsine yazılır (çeviri belleği), (2) zaten çevrilmiş ya da onaylı satırlar atlanır, (3) tablo başka bir
  sütuna göre sıralıysa ekranda sıçrıyor görünür. "No" sütunu gelince sıra açıkça görünür.
- **Bağlamı yakalıyor mu?** Her parti sahnedeki önceki ve sonraki satırlarla gider; aynı işte yazılan çeviriler de
  sonraki partilere bağlam olarak eklenir.
- **Düşünüyor mu? Neden bazen iptal oluyor?** Düşünme yeteneği olan modellerde düşünme kapatılarak (`think: false`)
  istek gönderilir. Gemma 4 buna rağmen bazen "düşünme kanalı" metni üretiyor; program onu siler ama düşünme uzarsa
  yanıt için ayrılan 3.072 belirteçlik sınır dolup yanıt yarım kalıyor → parti hatası. Ayrıca model 3 dakika hiç çıktı
  vermezse "takıldı" sayılıyor. Öneri: yarım yanıtta partiyi bölerek otomatik yeniden deneme, sınırı modele göre
  ayarlama ve bu durumda net bildirim (§2.5).
- **"Eski Türkçe karşılıklar kullan" gibi talimata uyuyor mu?** Talimat sistem istemine girer; uyma derecesi modele
  bağlıdır. Ölçmek için: 20 satırlık örnek üzerinde talimatlı/talimatsız çeviriyi yan yana gösteren bir **Talimat
  önizleme** düğmesi öneririm.

## 4. Önerilen yol haritası

Her aşama ayrı sürüm; sıra, en çok vakit geçirilen ekrandan başlar.

| Aşama | İçerik | Büyüklük |
|---|---|---|
| **A. Çevir ekranı** | Daraltılabilir kenar çubuğu, tekrar eden sayıların kaldırılması, panel göster/gizle, akıllı sütun sığdırma, sütun gizle/hatırla, No sütunu, doğal sıralama, durum simgeleri, çoklu süzgeç (grup + anahtar), sözcük sınırında kaydırma, tabloda semboller ve yazım çizgisi, orijinalden kopyalama, yumuşak kaydırma, panelde canlı karakter sınırı, satır içi Bul ve Değiştir çubuğu (önizlemeli) | Büyük |
| **B. Menüler, Ayarlar, kısayollar** | Menü çubuğu yeniden düzeni (simgeli), Ayarlar penceresi, kısayol düzenleyici, gruplu bağlam menüsü | Orta |
| **C. Anlık denetim + Sorunlar panosu** | Satır kaydında anlık denetim, Kontrol Et → Sorunlar (yerinde düzenleme, çip süzgeç, daraltılabilir düzeltmeler, ipuçları), Yazım Denetimi penceresi, grup/anahtar sınır tablosu, cümle içi terim tutarsızlığı | Büyük |
| **D. Otomatik Çeviri + bildirimler** | Pencerenin yenilenmesi, talimat kitaplığı, anahtar kapsamı, bildirim merkezi (ses, Windows bildirimi, Tekrar Dene), Ollama/DeepL ipucu panosu, yarım yanıtta otomatik bölme | Orta |
| **E. Terminoloji** | Ad değişikliği, AppData kitaplığı, sade pencere, kısa hatalar, seçili satırları terminolojiye ekleme, kanonik terimlerin Ollama'ya verilmesi | Küçük |
| **F. Dışa aktarma, font, grafik** | Üzerine yaz, font raporu + dışa/içe aktar, Görseller adımı | Orta |
| **G. Kimlik, maskot, yardım, katkı rehberi** | Maskot hâlleri ve animasyonlar, uygulama içi Yardım, katkı rehberinin genişletilmesi | Orta |

A ile C birbirine bağlı (durum simgeleri anlık denetimden beslenir): A'nın görünüm kısmı önce, simgelerin "sorun"
hâli C ile birlikte gelir.
