# Metinleri Tara

Tarama, oyunun içindeki dosyaları açar ve tanınan metin biçimlerini bulur: MSBT, Unity Localization ve I2,
Unreal `.locres`, GFMSG mesajları ve bazı oyunlara özel biçimler.

- **Tara ve Aktar:** Boş projede tek tık yeter. Tarama bitince kaynak dildeki dosyalar kendiliğinden aktarılır ve
  Çevir açılır; seçimi değiştirmek için bildirimdeki **Dosyaları Seç**'e basın. Birden çok dil varken dili
  anlaşılamayan dosya varsa aktarma kendiliğinden başlamaz; rapor açılır, siz seçersiniz.
- Büyük oyunlarda tarama birkaç dakika sürebilir; işi istediğiniz an **İptal** edebilirsiniz.
- Rapor, bulunan metin dosyalarını, satır sayılarını ve tanınmayan dosyaları gösterir.
- **Kaynak dil:** Türkçe metin, seçtiğiniz dilin (çoğunlukla İngilizce) yerine yazılır. Oyunu da o dilde oynamanız
  gerekir. Oyun dosyalarının içinde dil listesi taşıyan biçimlerde (ör. I2 Localization) o dosyadaki diller de bu
  listede görünür.
- **Hangi dosyalar aktarılır:** Yalnızca tablodaki **Aktar** kutusu işaretli dosyalar aktarılır; işaretli dosya
  sayısı tablonun altında görünür. Başka dildeki dosyaların kutusu kapalıdır. Dili anlaşılamayan dosyalar işaretli
  gelir; istemediklerinizin işaretini kaldırın. Seçim projeye kaydedilmez, her taramada yeniden kurulur. Başlıkların
  üstüne gelince ne anlama geldikleri görünür.
- **Proje doluysa:** Tablo, projede zaten aktarılmış dosyaları işaretli getirir; yeni dosyalar işaretsiz kalır.
  İşaretini kaldırdığınız proje dosyaları aktarmada projeden çıkar; önce sorulur ve çevirileri silinir, geri alınamaz.
- Aktarınca metinler çeviri tablosuna taşınır. Daha önce çevrilmiş satırlar korunur; kaynak metni değişen satırlar
  işaretlenir.

Tanınmayan bir oyun için yeni bir eklenti gerekir (bkz. **Katkı ve eklentiler**).
