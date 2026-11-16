# Kontrol Et

## Sorunlar

**Denetle** bütün satırları arka planda tarar; bitince bildirim gelir. Soldaki listeden türe göre süzün: en üstte
oyunu bozabilecek sorunlar durur. Bir türe tıklayın; birkaç tür için Ctrl'ye basılı tutun; grup başlığına tıklayınca
grubun hepsi seçilir; **Tüm bulgular** süzgeci kaldırır.

Her bulgu üç satırlık bir kart olarak listelenir: üstte açıklama (sağda çeviri tablosundaki **No**), altında soluk
orijinal metin, en altta çeviri. Sıra önemden başlar (hata, uyarı, bilgi), sonra türe ve satır numarasına göre gider.
Bir satıra çift tıklayın ya da Enter'a basın: satır çeviri ekranında düzenlemeye açılır. Çeviri satırına çift
tıklayarak (ya da `F2` ile) çeviriyi burada da düzeltebilirsiniz.

Denetimler: kontrol kodu (sayı, tür, sıra), boş çeviri, taşma, terim tutarsızlığı, aynı metnin farklı çevirisi,
noktalama, çift boşluk, yazım ve uydurma şüphesi. Satırlar düzenlenirken de anlık denetlenir.

Listenin üstündeki **düzeltme çubuğu** güvenli düzeltmeleri toplu uygular (fazla boşluk, kod sırası, satır
sığdırma…). Çubuk, listede görünen bulgulardan kendiliğinden düzeltilebilenleri sayar; satır seçerseniz yalnızca
seçilileri sayar. Soldan bir tür seçmek ya da listede satır seçmek, o bulguların düzeltilmesini istediğinizi gösterir
(yanılabilen düzeltmeler için çubuk uyarır); **Tüm bulgular**dayken yalnızca güvenli türler düzeltilir. Tüm
düzeltmeler tek iş olarak kaydedilir ve `Ctrl+Z` ile geri alınır. Denetim yapıldıktan sonra üstteki düğme **Yeniden Denetle** olur.

## Sığdırma

Oyunun metin kutusuna sığmayan satırlar için satırda en çok karakter ve sayfada en çok satır sınırı verin; bilmiyorsanız
**Orijinalden öğren**. Gelişmiş bölümünde grup ya da anahtar başına sınır ve kontrol kodu türleri (satır sonu, sayfa
sonu, değişken) ayarlanır. Ayarı değiştirince denetim kendiliğinden yenilenir (önce bir kez **Denetle**'ye
basmış olmanız gerekir); kaç satırın taştığı bu sekmede görünür, **Göster** onları Sorunlar'da açar.

## Yazım Denetimi

**Araçlar → Yazım Denetimi** (`F7`): Türkçe yazım hatalarını tek tek gezer; program doğru yazımı kendisi önerir (önce
ı/i, ş/s, ğ/g, ü/u, ö/o, ç/c harf hatası, yoksa tek harflik hata), öneriye tıklayıp hepsinde birden değiştirir, yok
sayar ya da sözlüğe eklersiniz. **Tek önerisi olanları düzelt** harf hatasıyla tek önerisi olan sözcüklerin hepsini tek
işte düzeltir (Geri Al hepsini geri alır); önce Öneri sütununa bakın, doğru ama sözlükte olmayan sözcükleri Yoksay ya da
Sözlüğe Ekle ile ayırın.

Font ve Türkçe harfler için **Font ve harfler** konusuna bakın.
