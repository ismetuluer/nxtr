# Makine çevirisi (M3)

Kod: `nxceviri/core/translate/` — `providers/base.py` (sözleşme), `providers/ollama.py`,
`runner.py` (toplu çeviri), `placeholders.py`, `status.py`. Proje tarafı:
`core/project/store.py` (bellek, sözlük, ayarlar — şema v4).

## Ollama kurulumu (çeviri yapılacak bilgisayarda)

1. https://ollama.com adresinden Ollama'yı kurun ve çalıştırın (Başlat menüsü → Ollama).
2. Bir model indirin (16 GB VRAM, ör. RTX A4000 için):

   | Model | Neden |
   |---|---|
   | `ollama pull gemma4:12b` | Önerilen: Google'ın en yeni çok dilli modeli, 16 GB'a rahat sığar |
   | `ollama pull gemma3:12b` | Güçlü çok dilli yazım, yaygın olarak denenmiş |
   | `ollama pull qwen3:14b` | 16 GB için sık önerilen genel model |

   Öneriler Ekim 2026 araştırmasına dayanır; Türkçe çeviriye özel bir karşılaştırma yoktur.
   Silver Pines'tan 20–30 satırla iki modeli yan yana deneyip seçmeniz önerilir.
3. Uygulamada "Çevir" → **Otomatik Çeviri…** (`Ctrl+T`) → **Modelleri Listele** → model seçin →
   **Çeviriyi Başlat**.

## Nasıl çalışır

- Üç iş türü vardır (Otomatik Çeviri penceresi, Çeviri menüsü veya tablonun sağ tık menüsü):
  - **Çevir:** çevrilmemiş ve hatalı satırlar. Satırlar kaynak metne göre gruplanır; **aynı cümle bir kez**
    gönderilir, bellekte karşılığı olan cümle gönderilmez.
  - **Yeniden çevir:** seçili satırlar / seçili grubun tamamı / tabloda filtrelenen satırlar / tüm proje,
    çeviri silinmeden yeniden çevrilir. Bellek atlanır, her satır kendi sahnesinde ayrı çevrilir.
  - **Talimatla düzelt (redaksiyon):** mevcut çeviri, talimatla birlikte gönderilir ("zamirleri at, doğal
    konuş"); model iyi olanı aynen bırakır. Yalnızca Ollama.
  - Onaylı satırlar yalnızca “Onayladığım satırlara da uygula” işaretliyse yeniden çevrilir/düzeltilir.
- **Bağlam:** her parti sahnedeki önceki 8 ve sonraki 3 satırla (varsa çevirileriyle) birlikte gider. Parti
  yalnızca aynı dosyada art arda gelen satırlardan kurulur.
- **Çeviri belleği** (proje içinde): elle girilen ve makinenin ürettiği geçerli çeviriler
  kaydedilir. Bellekte karşılığı olan metin sağlayıcıya hiç gönderilmez. İnsan çevirisi
  makine çevirisinden önceliklidir; makine çevirisi bellekteki insan çevirisinin üzerine yazmaz.
- **Çeviri talimatı** (Ollama; Otomatik Çeviri penceresi): çevir ve yeniden çevir işlerinde isteğe bağlı bir talimat
  kutusu vardır ("Bu satırlar menü metni: kısa yaz, sona nokta koyma"). Hazır talimatlar: arayüz ve menü, diyalog ve
  altyazı, eşya/yetenek açıklamaları, eğitim ve ipucu, resmî/eski dil; seçilince kutuya yazılır, düzenlenebilir.
  Talimat oyun notlarının ardından **sistem istemine** eklenir (kontrol kodu ve JSON kuralları her zaman üstündür) ve
  projede saklanır; redaksiyon talimatından ayrıdır. Dosya, grup ya da anahtar başına farklı talimat için kapsam olarak
  "Seçili satırların grubu"nu ya da **"Grup ya da anahtar deseni"**ni (`menu_*`, `*Chapter1*`) seçip işi parça parça
  çalıştırın. **Kitaplık** düğmesiyle talimatı adlandırıp kaydedebilir, başka projelerde de seçebilirsiniz
  (`%LOCALAPPDATA%\NXCeviri\talimatlar.json`). DeepL talimat izleyemez: kutu gizlenir.
- **Yarım yanıt**: model yanıtı uzunluk sınırında keserse parti ikiye bölünüp yeniden istenir.
- **Sözlük**: her partiye yalnızca o partide geçen terimler eklenir.
  - **Bilgi notu (lore):** Türkçe karşılığı boş, notu dolu madde (ör. Elara → "Kahramanın ablası; ona 'siz'
    denir"). Ad partide geçtiğinde not modele bilgi olarak gider; çeviri zorlanmaz, QA sözlük uyarısı vermez,
    DeepL sözlüğüne girmez.
  - **XLSX içe/dışa aktarma** (Sözlük penceresi): iki sütun, `terim` ve `çeviri` (çeviri/redaksiyon tablolarıyla
    aynı yazıcı). İçe aktarırken başlık yoksa ilk satır da veridir, isteğe bağlı üçüncü sütun not olarak okunur;
    terimler büyük/küçük harf duyarsız birleşir, var olanın yazımı ve notu korunur. Bilgi notları iki sütuna
    sığmadığı için dışa aktarılmaz (pencere kaç tane olduğunu söyler).
  - **Terim Öner (Ollama):** program metinlerde en az iki kez, cümle ortasında büyük harfle geçen adları bulur
    (`terms.find_candidates`; yalnızca cümle başındaki sözcükler, tamamı büyük harf arayüz sözcükleri, sözlükte
    olanlar atlanır). Model yalnızca bu adaylara, örnek cümleleriyle, karşılık ve kısa not önerir; listede olmayan
    terimi ve gereksiz bulduğunu (`add: false`) döndüremez. Öneriler onay penceresinde işaretlenip düzeltilir,
    yalnızca onaylananlar sözlüğe katılır.
- **Oyun notları**: tür, ton, hitap (sen/siz) gibi notlar projede saklanır. Ollama'da (0.40.0'dan beri)
  **sistem isteminin** sonuna eklenir: her partide aynı oldukları için model onlara daha sıkı uyar ve Ollama
  değişmeyen istem başını yeniden işlemez. DeepL'de bağlam (`context`) olarak gider.
- Partiler (Ollama): en çok 8 satır / 1.500 karakter. Model JSON şemasıyla yanıt vermeye zorlanır
  (`format`), sıcaklık 0,2, sabit tohum (`seed` 42), bağlam 8.192 token. Model "düşünme" destekliyorsa
  kapatılır. Düşük sıcaklık ve sabit tohum aynı istemin aynı çeviriyi vermesini sağlar.
- **Kontrol kodları**: dönen her çevirinin `⟦n⟧` sayısı, türü ve sırası denetlenir; baştaki/sondaki
  boşluklar özgünle eşlenir. Bozuk dönen satır, sorunu yazılarak (`fix`) bir kez tek başına yeniden
  istenir; hâlâ bozuksa: çevirisi olmayan satıra yazılır ama durum **Hatalı** olur (dışa aktarılmaz),
  geçerli çevirisi olan satırın eski çevirisi korunur. Hiç dönmeyen satır olduğu gibi kalır.
- **Uydurma (halüsinasyon) koruması** (`guards.translation_problems`): çevirisi olmayan satırın yeni çevirisinde
  şu belirtiler aranır: satır çevrilmeden aynen dönmüş (iki sözcük ve üstü), İngilizce kalmış, orijinalde olmayan
  yabancı alfabe harfi (Türkçe çeviride Çince, Kiril…), aynı iki sözcüğün tekrar döngüsü, orijinalden çok uzun
  (2,5 katı ve 20 karakter fazlası) veya çok kısa (0,35 katı). Belirti varsa satır sorun yazılarak bir kez daha
  istenir; sürerse (kodlar yerinde olduğu için) çeviri yazılır ama Kontrol Et'te ve Çevir ekranındaki durum
  sütununda **Şüpheli çeviri** uyarısı çıkar; iş sonu iletisi kaç satır olduğunu söyler. Var olan çevirinin
  yerine yazılacak sonuçlar (yeniden çeviri, redaksiyon) daha sıkı denetlenir: belirti sürerse eski çeviri korunur.
  Yanlış yazılmış ama var olan harflerle yazılmış sözcükleri bu denetim yakalayamaz; bunun için yazım denetimi
  ayrı bir aşamadır.
- **Noktalama:** **Sondaki noktalama** uyarısı, orijinal noktalamasız bitiyorken çevirinin sonuna `. ! ? … : ;`
  eklendiğinde çıkar ("Start Game" → "Oyunu Başlat."); düzeltmesi işareti atar (sondaki boşluk ve kontrol kodları
  kalır). Metin içindeki ünlem/soru denetlenmez (Türkçede doğal). **Fazla nokta** (4+ nokta ya da kaynakta olmayan
  "..") "..."ya indirilir.
- **Kontrol Et → Düzeltmeler:** Denetle'den sonra bulguların altında düzeltilebilir türler sayılarıyla listelenir;
  işaretlediğiniz türler **Seçilenleri Düzelt** ile yerinde düzeltilir (tabloda satır seçiliyse yalnızca o satırlarda,
  onaylı satırlara dokunulmaz). “Raporu Gör” önceki/yeni hâli ve uygulanan düzeltmeyi gösterir; Ctrl+Z hepsini geri
  alır. Düzeltmeler programla yapılır, model kullanılmaz.
- **Yazım denetimi (Türkçe):** çevirideki sözcükler paketlenen Türkçe sözlükle (hunspell-tr, MPL-2.0; ~6,1 milyon
  sözcük biçimi, `nxceviri/assets/spell/tr.bloom`) karşılaştırılır. Sözlükte olmayan sözcük **Çevir sayfasında çeviri
  kutusunda kırmızı dalgalı çizgiyle** işaretlenir; çizgili sözcüğe sağ tıklayıp **“… sözcüğünü yazım sözlüğüne
  ekle”** denir. Kontrol Et → Denetle ayrıca **Yazım** uyarısı verir ve satırı durum sütununda gösterir; bulguları
  seçip **Yazım Sözlüğüne Ekle…** ile toplu kabul edebilirsiniz (işaretini kaldırdığınız sözcük yazım hatası sayılır,
  eklenmez). Eklenenler **kullanıcı sözlüğüne** (`%LOCALAPPDATA%\NXCeviri\yazim-sozlugu.txt`) yazılır ve bütün projelerde geçerlidir; **Yazım
  Sözlüğü…** düğmesiyle görülür ve silinir. Şu sözcükler denetlenmez: kontrol kodları, sayılı olanlar, kesme işaretlileri
  (özel ad + ek), tamamı büyük harfli kısaltmalar, cümle ortasında büyük harfle başlayanlar (özel ad), orijinal metinde
  de geçenler, oyun sözlüğündeki terimler ve karşılıkları. Ollama'nın bozuk veya uydurma sözcükleri (ör. "yanlışş")
  böylece yakalanır; öneri verilmez (TECH_DEBT 77).
- **Tutarlılık:** aynı cümle bir işte bir kez çevrilir ve çeviri belleğinden gelir. Yine de aynı kaynak metin
  projede farklı biçimlerde çevrilmişse (ör. sonradan elle düzeltilen veya ayrı ayrı yeniden çevrilen satırlar)
  Kontrol Et → Denetle **Tutarsız çeviri** uyarısı verir ve biçimleri satır sayılarıyla listeler. Farklı
  biçimlerin hepsi onaylıysa uyarı verilmez (bağlama göre bilerek seçilmiş kısa cevaplar).
- **Değişiklikleri görme:** her değişiklik çeviri geçmişine yazılır. Yeniden çeviri / redaksiyon / Kontrol Et düzeltmesi
  bitince “Son İşin Değişiklikleri” penceresi açılır (önceki ↔ yeni, sözcük farkı vurgulu); işaretlenenler geri
  alınır; pencereden CSV/HTML olarak dışa aktarılabilir. Tabloda “Önceki çeviri” kutusu aynı farkı ayrı sütunda
  gösterir, durum süzgecindeki “Son işte değişenler” yalnızca bu satırları listeler; durum sütunu satırı son
  değiştiren işi yazar (“Makine · redaksiyon”). Tek satırın geçmişi: sağ tık → “Çeviri geçmişi…”.
- **Otomatik düzeltme** (Kontrol Et): boşluk ve fazla satır sonu yerel düzeltilir; kontrol kodu, uzunluk
  sınırı, satır sonu ve sözlük sorunları açıklamasıyla modele gider, sonuç QA denetiminden yeniden geçer.
- **Kaldığı yerden devam**: her partinin sonucu hemen projeye yazılır. İptal, ağ hatası veya
  çökme sonrası yeniden başlatıldığında yalnızca çevrilmemiş satırlar gönderilir.
- Geçici hatalar (zaman aşımı, 5xx, bozuk JSON) 2 ve 6 saniye beklenerek iki kez yeniden
  denenir; kalıcı hatalar (Ollama kapalı, model yok, bellek yetmedi) Türkçe ve ne yapılacağını
  söyleyen bir mesajla işi durdurur.

## Çeviri tablosu ve kısayollar

Çeviri, tablodaki çeviri hücresine çift tıklanarak (veya F2) yazılır. 0.31.6'da tablonun altındaki düzenleme
paneli kaldırıldı; tablo bütün alanı kullanır. Satır sonları hücrede simgeyle değil, ipucu önizlemesindeki gibi
gerçek satır sonu olarak gösterilir; hücre yüksekliği satır sayısına göre ölçülür. Görünüm → “Metni kaydır”
kapalıyken satırlar tek satır yüksekliğinde kalır ve satır sonları boşluğa döner.

| Kısayol | İş |
|---|---|
| Ctrl+Z | Son işlemi geri al (elle düzenleme, onay, onay kaldırma, makine işi, bul/değiştir, dış redaksiyon/çeviri içe aktarma, geri alma) |
| F3 | Sonraki bakılacak (onaylanmamış) satır |
| Ctrl+C | Seçili satırları panoya kopyala |
| Ctrl+F / Ctrl+H | Ara / bul ve değiştir |

Geri alma yığını (`Project.undo`) bu oturumda yapılan son 100 işlemi tutar; aynı makine işinin parça parça
yazımları tek işlem sayılır. Yeniden tarama yığını boşaltır. Kalıcı geçmiş ayrıdır: “Son İşin Değişiklikleri” ve
sağ tık → “Çeviri geçmişi” proje kapatılıp açıldıktan sonra da çalışır. Bir hücreyi düzenlerken Ctrl+Z hücredeki
yazıyı geri alır.

Aramada bulduğunuz satırın çevresini görmek için sağ tık → **Satırı yerinde göster**: arama metni ve süzgeçler
temizlenir, satır tablodaki gerçek yerinde komşularıyla birlikte ekranın ortasına getirilir. Tek satır
seçiliyken kullanılabilir. Arama metni elle silindiğinde veya süzgeçler değiştiğinde de tablo başa dönmez;
seçili satır görünür kalıyorsa görünüm onun olduğu yerde kalır.

## Dış redaksiyon ve dış çeviri (TXT veya XLSX)

Çevir sayfasındaki **Dışa/İçe Aktar** düğmesi (veya Araçlar menüsü, sağ tık → “Seçili satırlarla dış redaksiyon
dosyası oluştur”) iki biçim sunar. Varsayılan **TXT**, UTF-8 (BOM'lu) ve sekme ayraçlı dört sütundur:
`orijinal`, `çeviri`, `düzeltme`, `grup`. Model yalnızca `düzeltme` sütununu doldurur; boş bıraktığı satırın
çevirisi olduğu gibi kalır. `grup` salt okunur bağlamdır: metnin oyun içindeki yeri (Unity'de tablo koleksiyonu,
ör. `UI`, `Dialogue`; diğer oyunlarda dosya adı) burada durur. Model “UI” satırlarını menü/düğme etiketi,
“Dialogue” satırlarını konuşma cümlesi gibi redakte eder; sütun hiçbir zaman değiştirilmez ve çeviriye yazılmaz.
Dosyada satır kimliği yoktur; içe aktarırken satırlar `(orijinal, çeviri)` çiftiyle, çift aynıysa `grup` ile,
tutmazsa benzersiz orijinal metinle eşleşir. Hücre içindeki `\n`, `\t` ve `\\` yazıları kaçışlıdır; böylece her
kayıt tek satırda kalır. Bu biçim, çeviri metnindeki tırnak ve kontrol kodlarını modelin bozma riskini azaltır.

**XLSX** seçeneği Excel'de (veya çevrimiçi tablolarda) açılan aynı dört sütunlu çalışma sayfasını verir; hücrelerdeki
gerçek satır sonları korunur, başlık satırı kalın ve dondurulmuştur. Düzeltme hücresi boş bırakılabilir. XLSX
dosyaları da içe aktarılabilir; biçim uzantıya değil dosyanın ZIP imzasına bakılarak tanınır. Eski **CSV** biçimi
(`id, anahtar, orijinal, ceviri`) artık dışa aktarılmaz, yalnızca eski dosyalar için içe aktarmada okunur. Her iki
biçimde de istenirse her grup ayrı dosyaya (`ad_Dialogue.txt`, `ad_Dialogue.xlsx` …) yazılır ve/veya 150 satırlık
parçalara bölünür (`ad_001.txt`, `ad_Dialogue_001.xlsx` …). Pencerede ve kaydettikten sonra panoda, dış model
(ör. ücretsiz bir sohbet modeli) için hazır bir istem bulunur; projede kayıtlı redaksiyon talimatı varsa isteme
eklenir. Eski üç sütunlu TXT/XLSX dosyaları (`grup` olmadan) değişmeden okunmaya devam eder.

İçe aktarırken birden çok parça birlikte seçilebilir; biçim uzantıya değil içeriğe bakılarak tanınır (`.txt`
uzantılı eski CSV de okunur). Okuma, sohbet modellerinin sapmalarına dayanıklıdır (``` çiti, öndeki açıklama,
başlık adlarının İngilizceye çevrilmesi, CSV'de `;`/sekme ayraç, “Çeviri”/“translation” sütun adı, Windows-1254
kodlaması). Her metin model çıktısıyla aynı onarım ve temizlikten geçer (`repair_codes`, `clean_output`,
`match_edges`; model dokunmadığı satırlara temizlik de dokunmaz). Kontrol kodları uymayan, orijinali
projedekinden farklı (başka projenin dosyası) veya eşleşmeyen satırlar yazılmaz; yazmadan önce özet gösterilir.
TXT'de boş `düzeltme` hata değildir; “değişmeyecek” olarak sayılır. Yazmadan önce, yazılacak düzeltmeler
“Yaz / Satır / Orijinal / Önceki / Yeni” sütunlarıyla ve sözcük farkları renkli olarak gösterilir. Her satır
varsayılan olarak işaretlidir; beğenmediğiniz satırın “Yaz” işaretini kaldırarak o satırı atlayabilir, “Yeni”
hücresine çift tıklayarak (veya F2) öneriyi düzenleyebilirsiniz. Düzenlenen metin de model çıktısıyla aynı
onarım/temizlikten geçer; boş bırakılan ya da kontrol kodları uymayan satırlar yazılmadan önce uyarıyla
durdurulur. “Çevirilere Yaz (n)” demeden hiçbir şey değişmez; düğmedeki sayı gerçekten değişecek satırları
gösterir. Değişen satırlar **Redakte** durumuyla, `csv-…` iş kimliğiyle yazılır; onaylı satırlar da
redakte edilebilir ve durumları “Redakte” olur. Aynı karşılaştırma “Son İşin Değişiklikleri”nde ve satır
geçmişinde (sağ tık → “Çeviri geçmişi”) durur; Ctrl+Z hepsini birden geri alır.

## Dış çeviri (TXT veya XLSX)

Aynı **Dışa/İçe Aktar** menüsündeki **“Dış çeviri dosyası oluştur…”** çeviri işini dışarıya vermek içindir.
Biçim redaksiyonla aynı dört sütundur, ancak üçüncü sütunun adı `yeni çeviri` olur: `orijinal`, `çeviri`,
`yeni çeviri`, `grup`. Çevirmen ya da model yalnızca `yeni çeviri` sütununu doldurur; `çeviri` mevcut Türkçe
metindir (henüz çevrilmemiş satırda boştur). Boş bırakılan `yeni çeviri`, mevcut çevirinin korunacağı anlamına
gelir. `grup` burada da salt okunur bağlamdır. TXT varsayılandır; XLSX aynı sütunları Excel'de açar. Dosya adı
varsayılan olarak `…_ceviri.txt` / `…_ceviri.xlsx` olur; gruplara ayırma ve parçalama redaksiyonla aynıdır.
Penceredeki hazır istem çevirmene/model ne beklendiğini, `yeni çeviri` dışındaki sütunlara dokunulmamasını,
kontrol kodlarının korunmasını ve doğru çevirilerin boş bırakılabileceğini anlatır; kaydedince panoya kopyalanır.

İçe aktarma (**“Dış çeviriden içe aktar…”**) redaksiyonla aynı akışı izler: TXT/XLSX/CSV dosyaları birlikte
seçilebilir, satırlar `(orijinal, çeviri)` çiftiyle (gerekirse `grup` ile) eşleşir, önce “Yaz / Satır / Orijinal /
Önceki / Yeni” önizlemesi gösterilir. Beğenilmeyen satırın işareti kaldırılır, “Yeni” hücresi düzenlenebilir;
düzenlenen metin de aynı onarım/temizlik/denetimden geçer. Yazılan satırlar **Makine** durumu ve `translation-…`
iş kimliğiyle kaydedilir; onaylı satırlara yazmak için önizlemede satırı işaretlemek yeterlidir. Değişiklikler
“Son İşin Değişiklikleri”nde görünür ve Ctrl+Z ile geri alınır.

## İptal ve takılma

Ollama'ya istekler akış (stream) olarak gönderilir. İptal edince süren istek hemen kesilir. Ollama 5 dakika
boyunca hiç parça üretmezse (`STALL_TIMEOUT_S`) iş "takılmış görünüyor" diye durur; bu hata yeniden denenmez,
çünkü takılan sunucuyu tekrar beklemek dakikalar kaybettirir. Sık oluyorsa `ollama ps` ile modelin tamamen
ekran kartında çalıştığına bakın.

## Temizlik katmanı ve sorun renkleri

Yerel modeller (ör. gemma4) redaksiyonda bazen özgünde olmayan `<div>` gibi etiketler, uydurma `⟦n⟧` kodları
ekler ya da metnin ortasındaki satır sonu kodlarını en sona yığar. Her model sonucu projeye yazılmadan önce
`core/translate/cleanup.py` bunları temizler (özgünde aynen geçen etiketlere dokunulmaz); sona yığılmış satır
sonu kodları, metin sözcük sınırlarından özgündeki satır oranlarıyla bölünerek araya yerleştirilir. Kaç satırın
temizlendiği iş bitince söylenir. Var olan çevirilerde aynı temizlik Kontrol Et → Düzeltmeler (*Fazla etiket*, *Kod yeri*) ile yapılır.

Çeviri tablosunda çeviri metninin rengi en önemli sorunu gösterir (Görünüm → Sorunları renkle göster; ipucunda
renklerin açıklaması): kırmızı kontrol kodu hatası, mor fazla etiket, turuncu uzunluk sınırı, camgöbeği satır
sonu / kod yeri, sarı-kahve olası taşma.

Durum sütununda durumun altında satırın hata ve uyarı sayısı yazar ("✖ 1 hata · ⚠ 2 uyarı"); ipucu her birini
açıklar. Etiket, kod ve uzunluk sorunları hemen görünür; sözlük, font ve sığdırma uyarıları Kontrol Et → **Denetle**
çalıştırıldıktan sonra eklenir ve çeviri değişince düşer. Onaylı satırlar da denetlenir. Durum süzgecindeki
**Hata veya uyarısı olan satırlar** bu satırları gösterir.

## Metin sığdırma (satır ve sayfa sınırı)

Oyun metin kutusuna sığmayan satırları bulup yeniden bölmek için:

1. **Kontrol Et → Sığdırma** sekmesini açın, “Sığdırmayı aç”ı işaretleyin.
2. “Satırda en çok karakter” ve “Sayfada en çok satır” değerlerini girin; bilmiyorsanız **Orijinalden öğren** orijinal
   metinlerden bir öneri yazar (kendiliğinden uygulanmaz, değiştirebilirsiniz). Bir dosyaya ayrı sınır vermek için Kapsam’dan dosyayı seçin.
3. **Kod türleri** tablosunda her kontrol kodunun ne olduğunu kontrol edin: *satır sonu* ve *sayfa sonu* metni böler,
   *değişken* birkaç karakter, *sembol* bir karakter yer kaplar, *biçim* (renk, stil) ve *diğer* yer kaplamaz ve yanındaki
   sözcükten ayrılmaz. Tür etiketten tahmin edilir; yanlışsa açılır listeden düzeltin.
4. İsterseniz “Düzeltirken temizle” seçeneklerini (gereksiz boşluk, noktalama öncesi boşluk, tekrarlı noktalama) ayarlayın.
5. **Denetle**: *Satır uzun*, *Sayfa uzun*, *Kötü bölünme* uyarıları listelenir. Düzeltmeler'de bu türleri işaretleyip **Seçilenleri Düzelt**: sorunlu sayfalar
   noktalamadan, yoksa kelime bitiminden bölünür; sonra **Değişiklikler** penceresinde önceki/sonraki hâli görüp
   satırları tek tek geri alabilirsiniz.

Bilmeye değer davranışlar:

- Sınır yokken (ya da Sığdırma kapalıyken) hiçbir şey yapılmaz; sınırlar kapalıyken de saklanır.
- Sayfa sonu kodlarına dokunulmaz. Satır sonu kodlu sayfalarda kod sayısı sabit kalır, yalnızca yerleri değişir.
- İçinde boş satır (paragraf arası, başlık altı) ya da sekme (girinti) olan sayfa yeniden bölünmez; olduğu gibi kalır,
  uyarısı listede kalır ve modele ya da elle düzeltmeye bırakılır.
- Sığmayan satır (tek sözcük sınırdan uzun ya da sayfa çok kalabalık) yerelde olduğu gibi bırakılır ve modele kısaltması istenir (sonuç sığmazsa eski çeviri korunur).
- Satıra sınır uygulanıyorsa o satır için eski “Satır sonu” denetimi çalışmaz.
- Onaylı satırlara dokunulmaz. Sınır karakter sayısıdır, piksel değildir.

## Çeviri paneli ve semboller

Çeviri sayfasında tablonun **altında** (ya da **sağında**) seçili satırın özgün ve çeviri metni için bir panel açılır;
araç çubuğundaki üç düğmeyle altta/sağda/kapalı seçilir (Ctrl+Alt+B / Ctrl+Alt+R).

- **Düzenleme:** Enter kaydeder, Shift+Enter yeni satır açar, Esc kayıtlı hâle döndürür, Alt+↑/↓ satır değiştirir. Panelde
  yazıp kaydetmeden başka satıra geçerseniz ya da pencereyi kapatırsanız metin kaydedilir.
- **Sembolleri göster/gizle** (Ctrl+Shift+8, ¶ düğmesi): boşluk `·`, satır sonu `¶`, sekme `→`; satır sonundaki fazla
  boşluklar turuncu işaretlenir. Orijinalde olmayan satır sonu boşluğu panelde ayrıca uyarılır.
- **Hiza:** sola/ortaya/sağa (Ctrl+L / Ctrl+E / Ctrl+R); yalnızca görünümdür, metne dokunmaz.
- **Kod çipleri:** tabloda `⟦1⟧` yerine koda göre renkli çip görünür (↵ satır sonu, § sayfa sonu, ◆ değişken, ★ sembol,
  ● biçim, ◇ diğer). Türleri Kontrol Et → Sığdırma tablosundan değiştirebilirsiniz. Paneldeki çipe tıklamak kodu
  imlecin olduğu yere ekler; kodlar çeviride aynı sırayla kalmalıdır.
- **Sayaç:** Sığdırma sınırı varsa "Satır 23/40 · Sayfa 3/4"; sınır aşılınca renk değişir.
- Pencere küçükse panel kendiliğinden uyum sağlar: altta sığmıyorsa sağa geçer, ikisi de sığmıyorsa gizlenir
  (seçiminiz korunur); pencereyi büyütünce geri gelir.

## İstem (prompt)

Sistem mesajı İngilizcedir (modeller talimatı en tutarlı İngilizcede izler), çıktı Türkçedir.
Kurallar: birebir değil doğal çevir, yer tutucuları aynen ve aynı sırayla koru, satır sonlarını koru,
sözlüğü kullan, `max_length` varsa aşma, yalnızca JSON döndür. Hedef Türkçeyse **Türkçe üslup
kuralları** eklenir (`ollama.TURKISH_STYLE`): özne zamirlerini düşür, "it/that/they"i her yerde
bu/şu/onlar yapma, "Ve" ile başlama, "Yes/No"yu duruma göre karşıla, deyim kullan, kısa cevabı önceki
satıra göre çevir. Redaksiyonda sistem mesajı "editör" rolündedir ve `instruction` alanını uygular.
Maddelerde `codes` alanı her kontrol kodunun anlamını verir (ör. `{"⟦1⟧": "Satır sonu"}`). Dönen
çevirideki sık bozulmalar denetimden önce onarılır (`runner.repair_codes`): `[1]` → `⟦1⟧`; satır sonu kodu
yerine yazılmış gerçek satır sonları sayısı tutuyorsa sırayla koda çevrilir. Oyun notları sistem mesajının
sonundadır. Kullanıcı mesajı:

```json
{"instruction": "(yalnızca redaksiyonda)",
 "glossary": [{"term": "Sheriff", "translation": "Şerif"}],
 "context_before": [{"text": "Have a drink with me.", "translation": "Benimle bir şey iç."}],
 "items": [{"id": "0", "text": "Not me.", "key": "Dialogue/s06", "current": "(redaksiyonda)", "fix": "(varsa)"}],
 "context_after": [{"text": "Fine."}]}
```

DeepL'e bağlam satırlarının özgün metni `context` alanıyla gider (çevrilmez, kotadan düşmez).

### Model şablonu

Ollama, `/api/chat` isteğindeki sistem mesajını (kurallar, Türkçe üslup, oyun notları, talimat) yalnızca modelin
**şablonu** onu kullanıyorsa iletir. Şablonu denetlemek için komut satırında:

```
ollama show <model> --template
```

Çıktıda `.System` ya da `.Messages` (GGUF'tan gelen Jinja şablonlarında `messages` değişkeni) geçiyorsa model sohbet biçimini bilir ve her şey olması gibi gider.
Çıktı yalnızca `{{ .Prompt }}` ise (ya da boşsa; bazı elle içe aktarılmış GGUF'larda olur) Ollama yalnızca son
kullanıcı mesajını modele verir; kurallar hiç ulaşmaz.

Uygulama bunu kendisi denetler (`/api/show` içindeki `template`, model başına bir kez okunur) ve sistem metnini
düşüren şablonda isteği yine çalıştırır: sistem metni kullanıcı mesajının başına `Instructions:` bölümü olarak,
JSON girdisi ise `Input:` bölümünün altına konur. Bağlantı sınamasında ve Otomatik Çeviri penceresinde
(**Modelleri Listele**'den sonra) model için kısa bir uyarı görünür; günlüğe de bir kez yazılır. Bu yalnızca bir
kurtarma yoludur, çünkü sohbet biçimi uygulanmaz. En iyi sonuç için sohbet şablonu olan bir model seçin
(Ollama kütüphanesindeki sürümler ve doğru şablonla gelen `hf.co/…` GGUF'ları).

### Bağlam boyutu (`num_ctx`)

`num_ctx` her iş başında **bir kez** belirlenir ve iş boyunca sabit kalır (değişirse Ollama modeli yeniden yükler
ve istem önek önbelleğini kaybeder). Hesap: en uzun partinin sistem + kullanıcı mesajının karakter sayısının
üçte biri (tahmini belirteç) + yanıt payı (`num_predict` 3072) + %15 pay, 8192'nin katına yukarı yuvarlanır.
Alt sınır 8192; üst sınır modelin `context_length`'i (`/api/show` → `model_info`) ve 32768'dir. Uzun oyun notları
ya da talimat gerekirse 16384/24576/32768 seçer. İstem üst sınıra sığmıyorsa **iş başlamadan** Türkçe hata
verilir ve kaç karakter fazla olduğu söylenir (oyun notlarını/talimatı kısaltın). Parti ortasında istem tahminden
uzun çıkarsa (bağlam satırlarındaki çeviriler uzunsa) değer o isteğe yetecek basamağa yükselir ve işin kalanında orada kalır (günlüğe yazılır);
sınırı aşarsa aynı hata verilir. Seçilen değer günlüğe yazılır. Sağlayıcıya bilgi `runner` tarafından verilir:
sağlayıcı isteğe bağlı `prepare_job(batches, kaynak_dil, hedef_dil, notlar)` yöntemini sunarsa, partiler
kurulduktan sonra ve ilk istekten önce bir kez çağrılır.

### Örnek: makine çevirisi ve hedeflenen sonuç (Despelote)

| Özgün | Birebir makine çevirisi | Hedef |
|---|---|---|
| No, I can't believe it. I just can't! And my friends. | Hayır, buna inanamıyorum. İnanamıyorum işte! Ve arkadaşlarım. | Yok, inanamıyorum. Gerçekten inanamıyorum! Bir de arkadaşlarım… |
| Yes, but they like soccer. | Evet, ama onlar futbolu seviyorlar. | Ama futbolu seviyorlar ki. |
| No, some of my friends don't like it. | Hayır, bazı arkadaşlarım bundan hoşlanmıyor. | Benim arkadaşların bazıları hiç sevmez ama. |
| That's the limit! | Bu kadar yeter! | Bu kadarı da fazla! |
| Not me. (içki teklifine) | Ben değil. | Ben içmem. |

## DeepL

- **Dosya → Ayarlar… → Çeviri** sayfasından API anahtarını kaydedin (Windows Kimlik Bilgisi
  Yöneticisi'nde saklanır). Free anahtarlar ":fx" ile biter; uç nokta otomatik seçilir.
- Otomatik Çeviri penceresinde sağlayıcı olarak DeepL'i seçin; **Bağlantıyı Test Et** kalan kotayı
  ve bu işin yaklaşık karakter kullanımını gösterir.
- Kontrol kodları `<x id="n"/>` etiketleri olarak gönderilir (`tag_handling=xml`,
  `preserve_formatting`, `split_sentences=nonewlines`); oyun notları `context` alanıyla (ücretsiz)
  iletilir. Sözlük iş boyunca DeepL'de tutulur, iş bitince silinir.
- Kota dolarsa (HTTP 456) iş durur; çevrilenler kaydedilmiştir, aynı projede Ollama ile devam
  edebilirsiniz. Geçici hatalar (429, 5xx) beklenip yeniden denenir.

## Testler

`tests/fake_ollama.py` gerçek Ollama API'sinin yanıt biçimlerini taklit eden sahte bir
sunucudur (`httpx.MockTransport`): zaman aşımı, bozuk JSON, eksik satır, bozuk yer tutucu,
sunucu hatası, kapalı sunucu ve eksik model senaryoları. Gerçek bir Ollama 0.34.4 sunucusuna
karşı da sürüm, model listesi, yetenek okuma ve "model yok" hatası doğrulandı; gerçek bir
modelle çeviri kalitesi henüz denenmedi (bkz. TECH_DEBT). DeepL için `tests/fake_deepl.py`
benzer bir sahte sunucudur; gerçek hesapla henüz istek yapılmadı.
