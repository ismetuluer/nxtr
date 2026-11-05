# Mina the Hollower — Yacht Club YCD (`.yc`)

Durum: okuma (0.15.0) ve **yerinde yazma (0.17.0)**. Yazma 2026-10-23'te gerçek Switch'te doğrulandı:
oyun açıldı, menü ve diyaloglar Türkçe göründü (harfler sadeleştirilmiş: ç→c, ğ→g…). Gerçek Türkçe
harfler (ğ ş ı İ) de aynı gün cihazda doğru göründü: Switch sürümünün fontunda glifler var,
font yamalama gerekmedi.

Çözümleme gerçek Switch dosyaları (`global.pak.yc`, `global_startup.pak.yc`, `tower_global.pak.yc`, sürüm
327680) ve PC topluluk Türkçe yaması üzerinde yapıldı. Repoya gerçek dosya konmaz; testler
`tests/ycdbuild.py` ile elle üretilmiş küçük dosyalar kullanır.

## Kapsayıcı

- İmza `YCD\0`. Dosya, kendi içinde işaretçilerle birbirine bağlı nesnelerden oluşur; işaretçiler
  göreli (kendi konumuna göre) olduğundan dosya yerinde taşınabilir.
- Üstte 0x20 baytlık kayıtlardan oluşan bir dizin vardır (0xC0'dan başlar). Dizin kayıtlarının
  anlamı ve boyut alanları **tam çözülmedi**; okuma için gerekmedi.

## Metin tabloları

Metin tabloları iki tür nesneden oluşur:

1. **Başlık satırı:** sütun adları. Hepsinde `ID` ilk, `English` ve `French` sonraki sütunlardır.
   11 dil sırasıyla: English, French, Italian, German, Spanish, Japanese – Kanji, Russian, Brazilian
   Portuguese, Korean, Chinese – Simplified, Chinese – Traditional.
2. **Satırlar:** başlıkla aynı genişlikte, her biri kendi dizgi havuzuyla birlikte bir nesne.

Her satır sütun başına 16 baytlık bir **betimleyici** dizisidir:

| Alan | Boyut | Anlam |
|---|---|---|
| sıfır | u32 | her zaman 0 |
| uzunluk | u32 | dizginin bayt uzunluğu (sondaki 0 hariç) |
| tür | u32 | `0x10` = dizgi. **Satırın son betimleyicisinde** negatif bir sayı (geriye işaret) |
| ofset | i32 | betimleyicinin başından +8'e göre **işaretli** konum; `-1` = boş dizgi |

Dizgi UTF-8'dir ve sonunda 0 bayt vardır. Aynı metin birden çok sütunda (ör. dile bağlı olmayan
özel adlar) veya başka satırlarda ortak havuzdan gösterilir; ofset geriye de (negatif) olabilir.
Bu yüzden dizgiler asla "sıradaki dizgi" diye değil, betimleyicinin gösterdiği yerden okunur.

### Tablo türleri (`global*.pak.yc`)

| Tür | Başlık | Satır sayısı (sürüm 327680) | Anahtar |
|---|---|---|---|
| `ui` | `ID`, 11 dil | 2.504 | `ui/<ID>` (ör. `ui/confirm`) |
| `names` | `ID`, `Speaker`, `Gender`, `Wildcard`, `Portrait`…, 11 dil | 213 | `names/<ID>` (ör. `names/ID5`) |
| `dialogue` | `ID`, `Speaker`, `Trigger`, `Branch`, `NextID`…, 11 dil | 1.260 | `dialogue/<ID>` (sayısal) |

Aynı kimlik ikinci kez geçerse anahtara `#2` eklenir. Boş İngilizce hücreli satırlar ve başka bir
`.yc` dosyasına yol olan hücreler (`palettes/…pal.yc`) çevrilecek metin sayılmaz.

### Metin işaretleri

Metinde `<f cn=mina>Mina</f>` (ad/terim), `<w>…</w>`, `<s>…</s>`, `<b action=attack></b>`,
`<au shield=true></au>` gibi etiketler ve `{…}` değişkenleri bulunur. Hepsi ⟦n⟧ yer tutucusuna
çevrilir; sayı ve sıra denetimi diğer biçimlerdeki gibidir.

## Topluluk yaması nasıl çalışıyor

Yama her dil tablosunun **yeni bir kopyasını dosyanın sonuna ekler** ve Türkçe metni
**İngilizce sütununa** koyar; diğer 10 dil aynı kalır. Özgün tablolar yerinde durur (dosya
bu yüzden ~%6 büyür). `global_startup.pak.yc` içinde 2 tablo, `global.pak.yc` içinde türüne göre
birden çok kopya vardır; **aynı başlığa sahip tabloların sonuncusu Türkçedir.**

Kimlikler sürümler arasında kayabilir: `dialogue` kimlikleri sayısaldır ve yama eski bir oyun
sürümüne dayanır; aynı kimlik güncellemeden sonra başka bir cümleyi gösterebilir. Bu yüzden
içe aktarırken yamanın *özgün (ilk) tablolarındaki İngilizce metin* oyunun şimdiki İngilizce
metniyle karşılaştırılır ve yalnızca eşit olanlara çeviri yazılır (`ReadyTranslations.sources`).
Gerçek veride (sürüm 327680 ↔ yama): 3.521 satır yazıldı, 366 satırın özgün metni güncellemede
değişmişti (atlandı), 86 satır yamada yoktu.

## Yazma (0.17.0)

Dosya yeniden düzenlenmez; yapının geri kalanına dokunulmaz. Çevrilen satırın dil sütunlarının
**betimleyicileri** (uzunluk ve ofset) ve gösterdikleri dizgi baytları güncellenir:

1. Satırın dizgilerinden, dosyadaki **başka hiçbir betimleyicinin göstermediği** (yalnızca bu
   satıra ait) olanlar bulunur; bitişik olanlar birleşik bir boş bölge oluşturur. Satırın tüm dil
   sütunları artık aynı Türkçe metni göstereceğinden bu bölge serbesttir.
2. Türkçe metin (UTF-8 + 0 bayt) bu bölgenin başına yazılır; 11 dil sütununun betimleyicisi oraya yönlendirilir.
3. Bölgeye sığmayan satırlar (ör. "Yes" gibi başka satırlarla paylaşılan kısa dizgiler) için, çevrilen
   diğer satırların bölgelerinde artakalan boş parçalar kullanılır.
4. Dosya boyutu, başlıktaki boyut alanları, dizin kayıtları, nesne sonlarındaki özet baytları ve hiçbir
   işaretçi değişmez. Gerçek veride (sürüm 327680, 3.521 satırlık yama çevirisi) 2.418 + 213 + 891
   satır yazıldı, hepsi sığdı; yeniden okumada tüm metinler beklenen değerde, çevirisiz satırlar özgün.

Bilinen sonuçlar: çevrilen satırlarda **bütün diller** Türkçe görünür (oyun dili ne seçilirse seçilsin);
Türkçe harfler (ğ ş ı İ) Switch fontunda mevcuttur (cihazda doğrulandı); harf dönüştürme gerekmez.

Tam mod (yama + 82 ek satır, 3.974 satır) 2026-10-23'te Switch'te sorunsuz açıldı.

## Çözülmemiş alanlar (yazma için gerekmedi)

Mod üretmek için dosyanın yeniden yazılması gerekir; bunun için çözülmesi gerekenler:

- Dizin kayıtlarının (0xC0'dan sonra) boyut/ofset alanları ve her nesnenin boyutunu tutan alanlar.
- Satır nesnesinin son betimleyicisindeki "geriye işaret" değerinin anlamı (satır başı mı, nesne başı mı).
- Her nesnenin sonundaki ~20 baytlık özet (hash gibi) alanın nasıl hesaplandığı ve oyunun onu denetleyip
  denetlemediği.
- Yamanın yaptığı gibi tabloyu sona eklemek mi, yoksa satırları yerinde yeniden düzenlemek mi daha güvenli.

Bunlar çözülene kadar `MinaPlugin.inject` çeviri verilirse hata verir; bozuk bir dosya oyunu çökertir.
