# Sorun giderme — yama sonrası belirtiden nedene

## Ne zaman okunur
Kullanıcı modu üretti (ya da hazır yamayı kullanıyor) ve oyunda bir şey yanlış: oyun açılmıyor/çöküyor, metin kutudan
taşıyor, harfler kutucuk, bazı satırlar İngilizce kalmış, mod hiç görünmüyor. Önce **neyin sorun olduğunu kullanıcıdan
ekranda gördüğü haliyle** al ("şu menüde, şu cümle", mümkünse fotoğraf). `AGENTS.md` kurallarını unutma:
anahtar, oyun dosyası, orijinal dosyalara dokunma yok.

## Başlamadan önce üç soru
1. **Mod hangi yapıyla üretildi ve nereye kondu?** Atmosphère (`atmosphere/contents/<TitleID>/romfs/…`) ya da emülatör
   (`<TitleID>/<Mod Adı>/romfs/…`). Yol hataları en sık sebeptir.
2. **Oyunun dili ve sürümü ne?** Uygulama Türkçeyi seçilen kaynak dilin yerine yazar (ör. İngilizce). Oyun başka dilde
   çalışıyorsa Türkçe hiç görünmez. Ayrıca metinler aktarıldığı sürümle şu anki oyun sürümü farklıysa uygulama
   Dışa Aktar'da uyarır.
3. **Küçük modla mı deniyor?** Tüm metinler tek seferde denendiyse sorunu bulmak zordur; önce yalnızca ana menü
   etiketlerini çevirip küçük bir mod üret (`docs/test-emulator.md`). Çöküyorsa hata bir dosyadadır; modu bölerek
   hangisi olduğunu bul.

## Karar ağacı

### A. Mod hiç görünmüyor / hiçbir şey değişmedi
1. **Klasör yolu:** mod `…/<TitleID>/<Mod Adı>/romfs/` biçiminde olmalı; `romfs` bir seviye fazla ya da eksik olmamalı.
   Atmosphère'de `atmosphere` klasörü SD kartın köküne kopyalanır. Ryujinx: `mods/contents/<TitleID>/`; Yuzu
   türevleri: `load/<TitleID>/` (`docs/test-emulator.md`).
2. **TitleID:** mod klasörünün adı oyunun (güncelleme ya da DLC'nin değil) TitleID'siyle eşleşmeli. `NXTR - Bilgi.txt`
   doğru TitleID'yi yazar.
3. **Emülatörde mod etkin mi?** Bazılarında oyun özellikleri → mod listesinde işaretlenir.
4. **Dil:** oyunun/sistem dili uygulamanın aktardığı kaynak dil olmalı (adım 2 yukarıda). Hâlâ yoksa:
5. **Metin farklı yerden okunuyor:** oyun, değiştirdiğimiz dosyayı değil bir önbelleği ya da başka kopyayı okuyor
   olabilir. Örnekler: Despelote metni `Locoliser` nesnesinden okur (TSV/SRT değiştirmek yetmedi); DKCR HD'de aynı dil
   iki yuvadadır (0 ve 7) ve eklenti ikisine de yazar. `ara "<ekrandaki cümle>"` ile cümlenin hâlâ nerede olduğuna bak:
   değiştirdiğimiz dosyada **Türkçesi** ve başka bir yerde **İngilizcesi** varsa oyun diğer yeri okuyor.

### B. Oyun açılmıyor veya çöküyor (özellikle modla)
1. **Önce bölme:** modu küçült (yalnızca birkaç dosya) ve çökmenin hangi dosyayla başladığını bul. İkili bölme:
   dosyaların yarısını çıkar, çöküyor mu bak.
2. **Kontrol kodu bozulmuş olabilir** (en yaygın sebep): Kontrol Et'te kırmızı kontrol kodu hatası kalan satır var mı?
   "Hatalı" satırlar varsayılan olarak yazılmaz; ama "Hatalı satırları da aktar" seçeneği açıksa yazılmış olabilir.
   Kapat ve yeniden üret.
3. **Dosya boyutu ya da hizalama:** metin uzayınca kapsayıcının dizini/ofsetleri güncellenmemiş olabilir. Eklenti
   `inject`'inin değişiklikli round-trip testi ve `dogrula` bunu yakalar; yoksa `ARCHITECTURE.md` ve ilgili
   `docs/formats/*.md` notundaki "yazma" bölümüne bak.
4. **Unity Addressables CRC:** katalog o bundle için CRC denetimi istiyorsa değiştirilmiş bundle yüklenmez ve
   çeviri görünmez (ya da oyun hata verir). Uygulama `catalog.json`'daki CRC'yi sıfırlar (`docs/formats/unity.md`
   "Addressables katalog CRC'si"). `catalog.bin` (ikili) kullanan oyunlarda bu doğrulanamadı: kesin sonuç cihaz testidir.
5. **Font yaması:** yamalanmış font bundle'ından sonra çöküyorsa yamasız dene (`font.md`).
6. **Özel yamalar:** DMC1'de ana doku ve yazı dokusu hatalıysa oyun açılışta çöker ("Hata oluştu, kapatılıyor");
   `dmc1.md`'ye bak. Her oyunun notu böyle tuzakları listeler.
7. Çökme günlüğü (emülatör logu) varsa özetle; ham logu paylaşmaya özenme (yol ve kullanıcı adı içerebilir).

### C. Metin kutudan taşıyor / satır kaydı bozuk
1. **Kontrol Et → Sığdırma:** "Sığdırmayı aç", satırda en çok karakter ve sayfada en çok satır değerleri (bilmiyorsa
   "Orijinalden öğren"). Kod türlerini kontrol et: *satır sonu*, *sayfa sonu*, *değişken* (birkaç karakter),
   *sembol* (bir karakter). Yanlış tahmin edilen tür taşmanın sebebidir. Denetle → Düzeltmeler'de ilgili türleri
   işaretle → Seçilenleri Düzelt → Değişiklikler penceresinde bak (`docs/translation.md` "Metin sığdırma").
2. Türkçe çeviri İngilizceden %20-40 uzundur; sınırı aşan satırlar için modele kısaltma yaptır.
3. Sınır karakter sayısıdır, piksel değildir. Geniş harfli fontta (`W`, `M`) taşma olursa sınırı biraz düşür.
4. Taşma yalnızca bir yerde oluyorsa o dosyaya ayrı sınır ver ("Kapsam").

### D. Harfler kutucuk / boşluk / yanlış harf
`font.md`'ye geç. Hızlı kontrol: Kontrol Et → Fontları Tara. Eksik harf var ve font yaması kapalıysa aç ya da harf
dönüştürmeyi seç; açıksa ve hâlâ kutucuk varsa tabloda o fontun "Yamayla eklenir" sütununa bak.

### E. Bazı satırlar İngilizce kalmış
1. **Çevrilmemiş / hatalı / onaysız satırlar mı?** Çeviri tablosunda durum süzgeci: *Çevrilmedi*, *Hatalı*. "Hatalı"
   satırlar dışa aktarılmaz (orijinal kalır): nedeni durum sütununda (kontrol kodu sayı/tür/sıra).
2. **Metin resimde mi?** Satır tabloda hiç yoksa ve yazı bir düğme/başlıksa resimdir: `grafik.md`.
3. **Başka dosyada mı?** Tabloda yok ama metin başka bir dosyada ya da kod içinde: `python -m nxceviri.arac ara
   "<cümle>" <oyun dosyaları>` (DMC1'de düşman açıklamaları program kodunda, `.atm` dosyalarında, kayıt mesajları
   `memicon.dat`'ta idi).
4. **Başka bir dil yuvası mı?** Oyun kaynak dilden başka bir yuvayı okuyor olabilir (ör. DKCR'da ikinci İngilizce yuva).
5. **Güncelleme paketi:** metin update'te değiştiyse ve yalnızca base eklendiyse eski/eksik metin görünür.
   `docs/formats/` notları ve tarama raporundaki sürüm uyarıları. Base + update birlikte eklenmeli.
6. **Kasıtlı bırakılanlar:** özel adlar bazı oyunlarda İngilizce bırakılır (DMC1: silah ve düşman adları).

### F. Bazı satırlar bozuk görünüyor (`⟦3⟧`, `{0}`, fazla `<b>`)
1. `⟦n⟧` ekranda görünüyorsa dışa aktarma kodu geri çevirmemiş demektir; bu olmamalı. Satırın durumuna bak ve
   tabloda ham çeviriyi gör. Bozuk satırı Kontrol Et'te düzelt, yeniden üret.
2. `{input_0}` gibi değişkenler yerinde değilse çeviri kodu yanlış yere taşımıştır (kod sırası). Yalnızca değer
   taşımayan kodlarda (renk/biçim, satır/sayfa sonu) sıra otomatik düzeltilir; değişkenler elle düzeltilir.
3. Fazla `<div>` gibi etiketler yerel modelden gelir: Kontrol Et → Düzeltmeler → *Fazla etiket*.

### G. Tüm bunlardan sonra hâlâ belirsiz
Sorunu **küçült**: tek dosya, tek satır, tek harf. Elle üretilmiş küçük örnekle (yani gerçek oyun dosyası olmadan)
tekrarlanabiliyorsa test yaz; tekrarlanmıyorsa gerçek dosyada `dogrula`'yı çalıştır. Çözemezsen kullanıcıya hangi
bilgiyi toplayıp (TitleID, sürüm, `teshis-raporu.md` özeti, yapılan adımlar, hata ekranı) bir konu açabileceğini söyle;
oyun dosyası ya da oyun metni gönderme.

## Karar noktaları
- Hatayı yeniden üretemiyorsan çözüm önerme; önce "ne gördüm / ne bekliyorum" yaz.
- Düzeltme sonrası aynı yoldan tekrar dene (yeni, boş bir mod klasörüne üretilir: hedef klasör boş olmalı).
- Cihazda deneme kullanıcıdadır.

## Bitti ölçütü
Kullanıcı aynı ekranda sorunun gittiğini söyledi **ya da** neden bulundu, kalıcı çözümü yazıldı (test + belge) ve
kullanıcının yapacağı deneme açıkça belirtildi.

## Kullanıcıya rapor
Belirti → bulunan neden → yapılan düzeltme → kullanıcının deneyeceği şey. Tahmini neden ile kanıtlanan nedeni ayır.
