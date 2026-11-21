# Çevir

Tablo her satırı gösterir: **No**, orijinal, çeviri, durum ve dosya. Binlerce satırda da akıcı çalışır.

## Durumlar

- **Çevrilmedi:** henüz çeviri yok.
- **Makine:** Otomatik Çeviri yazdı.
- **Redakte:** elle düzenlendi.
- **Onaylandı:** son hâli; toplu işler dokunmaz (`Ctrl+Shift+A` onaylar).
- **Hatalı:** kontrol kodu bozuk; bu satır dışa aktarılmaz, oyunda orijinal kalır.

Durum hücresinin üzerine gelince çıkan ipucu satırı hangi hizmetin ya da modelin çevirdiğini de söyler ("Çeviren: …").

## Düzenleme

- Hücreye çift tıklayın ya da `F2`. **Çeviri paneli** (`Ctrl+J`) uzun metin, karakter sınırı ve komşu satırlar için
  rahattır; `Alt+↑` / `Alt+↓` satırlar arasında gezer.
- `Ctrl+1` … `Ctrl+9` satırın 1. … 9. kontrol kodunu ekler: hücreyi ya da panelin çeviri kutusunu düzenlerken
  imlece; tabloda tek satır seçiliyken panelin çeviri kutusuna (panel kapalıysa eklenmez).
- **Orijinali Çeviri Olarak Yaz** (`Ctrl+Shift+O`): özel adları olduğu gibi bırakmak için.
- Her değişiklik geri alınabilir (`Ctrl+Z`); geri aldığınızı **Yinele** (`Ctrl+Y`) geri getirir. Yeni bir düzenleme
  yinele listesini boşaltır. Bir satırın eski çevirileri **Çeviri Geçmişi**'nde.

## Bulma ve süzme

- **Tabloyu Süz** (`Ctrl+Shift+F`): duruma, dosyaya, gruba ya da anahtara göre. Büyük projede **Hata veya uyarılı**
  süzgeci satırları önce arka planda denetler; liste birazdan süzülür, bu sırada bekleyin.
- **Bul ve Değiştir** (`Ctrl+F` / `Ctrl+H`): küçük, taşınabilir pencere. Eşleşmeler tabloda boyanır, `F3` / `Shift+F3`
  gezinir. **Önizle** değişikliği yazmadan gösterir; **Tümünü Değiştir** tek iş olarak geri alınır. Kontrol kodunu
  bozacak değiştirme yapılmaz.

## Görünüm

Sütun başlığına sağ tıklayarak sütun gizleyebilir, sembolleri (`Ctrl+Shift+8`) ve satır kaydırmayı açabilirsiniz.
**Ayarlar → Görünüm**'de tema, yazı boyutu ve renkler.

**Gruplu görünüm** (süzgeç şeridinin sağındaki düğme ya da Görünüm menüsü) satırları dosyaya ya da gruba göre
öbekler; başlığa tıklayınca grup katlanır ya da açılır, başlıkta sağ tıkla hepsini birden katlayıp açabilirsiniz.
Katlamak süzmek değildir: sayılar, Otomatik Çeviri ve Bul/Değiştir'in "Görünenler" kapsamı katlı satırları da sayar.

## Dış redaksiyon ve dış çeviri

**Çeviri → Dış Redaksiyon** ve **Çeviri → Dış Çeviri** menüleri çeviriyi başka bir yerde (sohbet modeli, çevirmen)
yaptırıp geri almanızı sağlar.

- **Dışa aktarırken** sol tarafta biçimi (Excel ya da TXT), hangi satırların yazılacağını ve dosyaların nasıl
  bölüneceğini seçersiniz; sağda çıkacak dosyalar kartlar olarak, altında seçili dosyanın ilk satırları görünür.
  Bir karta basınca o dosyanın satırlarını görürsünüz. **Model için hazır talimat** bölümünü açıp okuyabilir,
  **Talimatı Kopyala** ile panoya alabilirsiniz.
- **İçe aktarırken** dosyaları seçince tek pencere açılır: solda dosyalar (projeyle hiç eşleşmeyen dosya sarı
  uyarıyla işaretlenir) ve sonuç sayıları, sağda yazılacak satırlar. Üstteki **Değişecek**, **Onaylıydı** ve
  **Kod uymuyor** düğmeleriyle listeyi süzersiniz. Kontrol kodu uymayan satırlar listelenir ama yazılamaz;
  mevcut çevirileri korunur. Beğenmediğiniz satırın işaretini kaldırın ya da metni çift tıklayıp düzeltin;
  **Dosya ekle** ile (ör. parçalara bölünmüş) başka dosyalar da ekleyebilirsiniz. **Nedenleri göster** yazılmayan
  satırların nedenlerini açar. Yazılanlar Geri Al ile geri alınır.

