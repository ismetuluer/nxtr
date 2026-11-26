# İstem kartları

Yapay zekâ ajanınızı (Claude Code, Codex, Gemini CLI, Cursor…) bu proje klasöründe açın ve istediğiniz işe uyan
kartı kopyalayıp ajana yapıştırın. `<…>` ile işaretli yerleri kendi bilgilerinizle değiştirin. Ajan önce `AGENTS.md`'yi
ve ilgili rehberi okur.

Bilmeniz gerekenler:
- Ajan **hiçbir şifreleme anahtarı aramaz, indirmez, önermez.** `prod.keys` dosyasını kendi konsolunuzdan siz çıkarır
  ve uygulamada (Dosya → Anahtarlar) siz gösterirsiniz.
- Oyun dosyalarınızı siz verirsiniz (yol olarak); ajan oyun dosyası indirmez, paylaşmaz.
- Ajanın "cihazda çalıştı" demesine güvenmeyin: modu Switch'te ya da emülatörde sizin denemeniz gerekir.

## 1. Yeni oyun

```
Bu klasördeki NXTR projesiyle yeni bir oyunun metinlerini çeviri tablosuna aktarmak istiyorum.
Önce AGENTS.md'yi, sonra docs/rehber/yeni-oyun.md rehberini baştan sona oku ve adımları izle.

Oyun: <oyunun adı>
Oyun dosyaları (base, güncelleme, varsa DLC): <C:\...\oyun.nsz>, <C:\...\guncelleme.nsp>
prod.keys uygulamada seçili: <evet / hayır, dosya yolu C:\...\prod.keys>
Oyunda ekranda gördüğüm ayırt edici bir cümle: "<oyundaki bir cümle>"

Önce `python -m nxceviri.arac teshis` ile teşhis yap, sonuçları Türkçe ve kısaca anlat. Yeni kod gerekiyorsa bütün
kodu (metin, font, resim) tek bir eklenti klasörüne yaz; ana koda (`nxceviri/` klasörü) hiçbir dosya ekleme ya da
değiştirme. "Eklenti oluşturamıyorum" deme: yapabildiğin her parçayı eklentide teslim et, imkânsız olanı komut
çıktısıyla kanıtla. Önce test yaz; `python -m nxceviri.arac dogrula` geçmeden ve içe aktarma bulgusu kalmışken
"bitti" deme. Teşhis raporundaki her metin dosyasını ya kapsa ya da neden kapsamadığını yaz; başka dil istemedikçe
yalnızca İngilizce metni aktar. `python -m nxceviri.arac font` ile Türkçe harf durumunu (a/b/c) belirle; eksik harfleri
önce font yamasıyla (gerekirse eklentinin içinde) kapat, harf dönüştürmeyi yalnızca son çare olarak kullan. Yazı
içeren resimleri say ve bana örnek adlarla bildir. Anahtar içeriğini gösterme, oyun dosyası indirme. Her adımda ne
yaptığını ve ne test ettiğini çıktısıyla göster.

Kotan ya da oturumun her an bitebilir; işi başka bir ajan sürdürecek. Teşhisten hemen sonra eklenti iskeletini kur.
Bir şey bulduğun anda (işin sonunda değil) eklenti klasöründeki NOT.md'ye (oyunun haritası: metinler, fontlar,
resimler, video ve program kodu nerede, belirti → neden → çözüm) ve CALISMA_GUNLUGU.md'ye (durum, sıradaki adım,
denenip olmayanlar, eklenti dışındaki betiklerin yolu) yaz.
```

## 1b. Yarım kalan işi başka ajanla sürdür

Önceki ajanın kotası bittiyse ya da başka bir yapay zekâyla devam etmek istiyorsanız bunu yapıştırın:

```
Bu klasördeki NXTR projesinde başka bir ajanın yarım bıraktığı oyun çevirisini sürdüreceksin.
Önce AGENTS.md'yi, sonra docs/rehber/yeni-oyun.md'yi oku. Ardından eklenti klasöründeki şu iki dosyayı baştan sona
oku: <eklentiler\eklenti_adi>\NOT.md (oyunun haritası) ve CALISMA_GUNLUGU.md (durum ve sıradaki adım).

Bu dosyalarda yazan işleri ve dosya incelemelerini baştan yapma; "Sıradaki adım"dan devam et. "Eklenti dışındaki
betikler ve dosyalar" bölümündeki betikler yerindeyse onları kullan. Bir sonucundan şüphelenirsen yalnızca o komutu
tekrar çalıştır. Önce bana 5 satırda neyin bittiğini, neyin kaldığını ve ilk adımını söyle, sonra işe başla.
Çalışırken her bulguyu ve her adımı bu iki dosyaya yazmaya devam et; senden sonra da başka bir ajan devam edebilir.

Oyun dosyaları: <C:\...\oyun.nsz>, <C:\...\guncelleme.nsp>
Cihazda denediklerim (varsa): <ne çalıştı, ne İngilizce kaldı, ekran görüntüsü klasörü>
```

## 2. Modda sorun var

```
NXTR ile ürettiğim modda bir sorun var. AGENTS.md'yi ve docs/rehber/sorun-giderme.md rehberini baştan sona oku, sonra
karar ağacını izleyerek nedeni bul.

Oyun: <oyunun adı>   TitleID/sürüm (biliyorsam): <TitleID>, <sürüm>
Modu nereye koydum: <Atmosphère SD kart / Ryujinx / Yuzu türevi / diğer: ...>
Ne görüyorum: <oyun açılmıyor / metin kutudan taşıyor / harfler kutucuk / şu satırlar İngilizce / mod görünmüyor>
Hangi ekranda ve hangi cümle: <menü adı, cümle>
Mod klasörünün yolu: <C:\...\mod klasörü>

Önce soruları kendi cevaplayabileceğin kadar dosyalardan doğrula, sonra gerekirse bana sor. Nedeni kanıtla (komut
çıktısıyla), tahminleri tahmin olarak belirt. Cihazı ben deneyeceğim; benden ne deneyeceğimi açıkça iste.
```

## 3. Font (Türkçe harfler görünmüyor)

```
Oyunda Türkçe harfler (<örneğin ğ ş ı İ>) kutucuk ya da yanlış harf olarak görünüyor. AGENTS.md'yi ve
docs/rehber/font.md rehberini baştan sona oku.

Oyun: <oyunun adı>
Proje dosyası (.nxproj): <C:\...\proje.nxproj>
Kutucuğu nerede görüyorum: <menü / diyalog / ayarlar ekranı>

Önce `python -m nxceviri.arac font <oyun dosyaları>` çalıştır (uygulamadaki Fontları Tara ile aynı sonucu verir), sonra uygulamada Kontrol Et → Fontları Tara ile hangi fontlarda hangi harflerin eksik olduğunu bul ve tablodaki
sayıları bana anlat. Font yaması uygulanabiliyorsa onu kullan; uygulamanın yaması fontu tanımıyorsa yamayı oyunun
eklentisinin içinde yaz (ana koda yazma). Yeni bir font biçimiyse biçimi önce çöz, test yaz, yazılan dosyayı yeniden
okuyup doğrula. Harf dönüştürmeyi yalnızca yamanın imkânsız olduğunu komut çıktısıyla gösterirsen öner. Sonucu cihazda
ben deneyeceğim.
```

## 4. Grafik (resimlerdeki yazılar)

```
Oyundaki bazı yazılar metin değil resim olduğu için çeviri tablosunda yok. AGENTS.md'yi ve docs/rehber/grafik.md
rehberini baştan sona oku.

Oyun: <oyunun adı>
Hangi ekranlar İngilizce kalıyor: <ana menü başlıkları / seçenekler ekranı / hikâye kartları / ...>
Oyun dosyaları: <C:\...\oyun.nsz>, <C:\...\guncelleme.nsp>
Resimleri düzenleyeceğim klasör (yoksa oluştur): <C:\...\oyun klasörü\grafik_temizleme>

Önce `python -m nxceviri.arac ara "<ekrandaki yazı>"` ile yazının gerçekten resimde olduğunu kanıtla; resim
biçimini, kaç resim olduğunu ve örnek adları bana söyle. Resim kodunu oyunun eklentisinin içine yaz, ana koda yazma. Resimleri `orijinal` klasörüne PNG olarak çıkar; ben yazıyı Türkçe
yapıp aynı adla `turkce` klasörüne koyacağım. Sonra değişenleri moda yerleştir ve resimlerin biçim/boyut
doğrulamasını göster.
```

## 5. Paylaşım

```
Çözdüğüm oyunu başkalarıyla paylaşmak istiyorum. AGENTS.md'yi ve docs/rehber/katki.md rehberini baştan sona oku.

Oyun: <oyunun adı>
Eklenti klasörüm: <C:\...\eklentiler\eklenti_adi>
Ne paylaşmak istiyorum: <yalnızca üretilen mod klasörü / eklentiyi zip olarak / depoya çekme isteği>

Önce paylaşımda anahtar, oyun dosyası, oyundan alınmış metin/resim ve kişisel yol olmadığını kanıtla (neye baktığını
göster). Testlerin, ruff ve mypy'nin çıktısını göster. Hazırladığın şeyin yolunu ve neyin paylaşılmadığını söyle.
Push yapma, çekme isteği gönderme: onayım olmadan hiçbir şeyi yayımlama.
```

## 6. Bu bilgisayara kur

```
Bu klasördeki NXTR projesini bu Windows bilgisayara kur ve çalıştığını doğrula. AGENTS.md'yi ve
docs/rehber/baslarken.md rehberini baştan sona oku, adımları izle.

Python kurulu mu bilmiyorum: <evet, sürüm... / hayır / bilmiyorum>
Yalnızca çeviri yapacağım mı, oyundan metin de çıkaracak mıyım: <yalnızca çeviri / metin çıkarma ve mod üretme>
Makine çevirisi için Ollama kullanacağım mı: <evet / hayır / bilmiyorum>

Her komutun ne yaptığını bir cümleyle anlat. Python ya da git kurulumu gerekiyorsa benden onay iste. Testleri çalıştır
ve geçen test sayısını göster. Anahtarımı (prod.keys) ben göstereceğim; sen bu dosyayı açma, içeriğini okuma.
```
