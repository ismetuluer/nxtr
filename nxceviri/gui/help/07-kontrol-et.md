# Kontrol Et

## Sorunlar

**Denetle** bütün satırları arka planda tarar; bitince bildirim gelir. Soldaki listeden türe göre süzün: en üstte
oyunu bozabilecek sorunlar durur. Bir türe tıklayın; birkaç tür için Ctrl'ye basılı tutun; grup başlığına tıklayınca
grubun hepsi seçilir; **Tüm bulgular** süzgeci kaldırır (bilgi düzeyindeki öneriler, örneğin yazım, bu sayıya girmez; görmek için türünü soldan seçin).

Her bulgu üç satırlık bir kart olarak listelenir: üstte açıklama (sağda çeviri tablosundaki **No**), altında soluk
orijinal metin, en altta çeviri. Sıra önemden başlar (hata, uyarı, bilgi), sonra türe ve satır numarasına göre gider.
Bir satıra çift tıklayın ya da Enter'a basın: satır çeviri ekranında düzenlemeye açılır. Çeviri satırına çift
tıklayarak (ya da `F2` ile) çeviriyi burada da düzeltebilirsiniz.

**Bulguları dışa aktarma:** listede sağ tık → **Bulguları dışa aktar…** (ya da Çeviri → Dış Redaksiyon →
Kontrol Bulgularını Dosyaya Yaz…) görünen bulguları, seçili bulgu varsa yalnızca onların satırlarını yazar. Dosya dış
redaksiyon dosyasıyla aynıdır (`orijinal`, `çeviri`, `düzeltme`, `grup`) ve en sonda `bulgu` sütunu bulunur: satırın
bütün bulguları tek hücrede, `|` ile ayrılmış. `bulgu` yalnızca bilgi içindir; düzeltmeyi **düzeltme** sütununa
yazın (bulgusu olmayan satırlar dosyaya girmez; hazır model talimatı panoya kopyalanır). Düzeltilen dosyayı
**Çeviri → Dış Redaksiyon → İçe Aktar** ile geri yükleyin; açılan pencerede değişiklikleri satır satır görür,
beğenmediğinizi işaretten çıkarır, yazdıktan sonra geri alabilirsiniz.

Denetimler: kontrol kodu (sayı, tür, sıra), boş çeviri, taşma, terim tutarsızlığı, aynı metnin farklı çevirisi,
noktalama, çift boşluk, yazım ve uydurma şüphesi. Satırlar düzenlenirken de anlık denetlenir.

**Kod sırası** uyarısı: biçim izin veriyorsa tek başına duran simge ve adlı değişkenler (`{0}`, `{name}`) cümlede
yer değiştirebilir; satır hatalı sayılmaz, dışa aktarılır. Biçim etiketi çiftleri (`<b>…</b>` gibi) de içindekilerle
birlikte, bütün olarak taşınabilir. Eksik, fazla, çaprazlanan ya da sırası değişen öteki kodlar hatadır.

**Satır sonu** hatası: bazı biçimler (ör. tırnaksız tablo hücreleri) çeviride satır sonunu taşıyamaz. Böyle bir satıra satır
sonu girerseniz satır hatalı sayılır, dışa aktarılmaz ve oyunda orijinal kalır; satır sonunu kaldırın.

Listenin üstündeki **düzeltme çubuğu** güvenli düzeltmeleri toplu uygular (fazla boşluk, kod sırası, satır
sığdırma…). Çubuk, listede görünen bulgulardan kendiliğinden düzeltilebilenleri sayar; satır seçerseniz yalnızca
seçilileri sayar. Soldan bir tür seçmek ya da listede satır seçmek, o bulguların düzeltilmesini istediğinizi gösterir
(yanılabilen düzeltmeler için çubuk uyarır ve birden çok satırda uygulamadan önce onay sorar); **Tüm bulgular**dayken yalnızca güvenli türler düzeltilir. Tüm
düzeltmeler tek iş olarak kaydedilir ve `Ctrl+Z` ile geri alınır (`Ctrl+Y` geri getirir). Onaylı satırlar da
düzeltilir ve onaylı kalır; çubuktaki sayı, düğmenin gerçekten değiştireceği satır sayısıdır. Denetim yapıldıktan sonra üstteki düğme **Yeniden Denetle** olur.

**Türkçe harf eksik** bulgusunda program birden çok sözcük olasılığı görürse (hasarın / haşarın) sözcüğe dokunmaz:
bulguya sağ tıklayıp **Şununla düzelt** altından doğru yazımı seçin, seçim o sözcüğün geçtiği bütün satırlara uygulanır.
Hata olmayan bir bulgu için sağ tık → **Bulguyu yok say** der; bulgu listeden çıkar, çeviri değişirse geri gelir, soldaki
**Yok sayılanlar**dan **Yok saymayı kaldır** ile geri alınır.

**Küfür / argo (çocuklara yönelik oyunlar):** **Araçlar → Küfür / Argo Denetimi** projeye özgüdür ve varsayılan
olarak **Kapalı**dır. **Yalnızca ağır küfür** ağır küfür ve sövgüleri, **Ağır küfür ve argo** buna ek olarak "lan",
"bok", "defol" gibi kaba argoyu işaretler. Bulgu uyarıdır ve dışa aktarmayı engellemez; satırda bulunan sözcükler
listelenir. Sözlük elle yazılmıştır ve her masum sözcüğü ayıramaz: yanlış işaretlenen sözcük için sağ tık → **Bu
kelime argo değil** der, sözcük bu projede bir daha işaretlenmez. Orijinal metinde aynen geçen sözcük (özel ad) ve üç
harfe kadar BÜYÜK HARFLİ kısaltma (LAN) argo olarak sayılmaz. Orijinalde de kaba bir İngilizce ifade varsa ileti bunu
söyler; çeviri o zaman sadıktır.

## Sığdırma

Oyunun metin kutusuna sığmayan satırlar için satırda en çok karakter ve sayfada en çok satır sınırı verin; bilmiyorsanız
**Orijinalden öğren**. Gelişmiş bölümünde grup ya da anahtar başına sınır ve kontrol kodu türleri (satır sonu, sayfa
sonu, değişken) ayarlanır. Ayarı değiştirince denetim kendiliğinden yenilenir (önce bir kez **Denetle**'ye
basmış olmanız gerekir); kaç satırın taştığı bu sekmede görünür, **Göster** onları Sorunlar'da açar.

**Genişliği fontla denetle** (kapsam başına, varsayılan kapalı): menü ve düğme gibi kısa metinlerde çevirinin
ekrandaki genişliği oyunun fontuyla ölçülür. Kutu, kapsamdaki en geniş orijinaldir (ya da seçerseniz satırın kendi
orijinali); **Genişlik payı**'nı (%15) aşan satır "Geniş satır" uyarısı alır, dışa aktarma engellenmez. "Ölçüm:" satırı
hangi fontun kullanıldığını söyler; fontlar taranmadıysa yaklaşık tablo kullanılır. Bu denetim karakter sınırı
gerektirmez. Açıkken çeviri panelinde sayacın yanında "Genişlik %112" gibi oran görünür.

## Yazım Denetimi

**Araçlar → Yazım Denetimi** (`F7`): Türkçe yazım hatalarını tek tek gezer; program doğru yazımı kendisi önerir (önce
ı/i, ş/s, ğ/g, ü/u, ö/o, ç/c harf hatası, yoksa çift basılmış ya da ters yazılmış harf), öneriye tıklayıp hepsinde birden değiştirir, yok
sayar ya da sözlüğe eklersiniz. **Tek önerisi olanları düzelt** harf hatasıyla tek önerisi olan sözcüklerin hepsini tek
işte düzeltir (Geri Al hepsini geri alır); önce Öneri sütununa bakın, doğru ama sözlükte olmayan sözcükleri Yoksay ya da
Sözlüğe Ekle ile ayırın.

## Grafik

Menü, düğme ve başlık gibi resimlerdeki yazıları çeviriyorsanız Türkçe resimlerinizi burada denetleyin. Program
`orijinal/` klasöründeki özgün resimleri `turkce/` klasöründeki aynı adlı Türkçeleriyle karşılaştırır: eksik olanları,
özgünle aynı kalanları, boyutu farklı olanları, arka plan saydamlığı kaybolanları ve kenara değen yazıları gösterir.

Oyun resim çevirisini destekliyorsa klasör kendiliğinden bulunur; özgünler henüz yoksa **Görselleri Çıkar**'a basın.
Desteklemiyorsa **Klasör Seç…** ile içinde `orijinal/` ve `turkce/` bulunan klasörü seçin; bu durumda resimler yalnızca
karşılaştırılır, moda kendiliğinden yerleşmez.

Sağda resmi **Yan yana**, **Üst üste** (sürgüyle özgünden Türkçeye geçin) ya da **Gidip gel** (resme tıklayın ya da
Boşluk) kipinde inceleyin. **Kılavuz** özgün yazının alanını gösterir. Baktığınız resmi **Onayla** (`Ctrl+Enter`)
ile işaretleyin; resmi yeniden kaydederseniz onay kalkar. Klasöre kaydettiğiniz resimler listeye kendiliğinden gelir.
Sekme başlığındaki sayı, onaylanmamış sorunlu resimlerdir.

Font ve Türkçe harfler için **Font ve harfler** konusuna bakın.
