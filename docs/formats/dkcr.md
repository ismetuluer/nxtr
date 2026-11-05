# Donkey Kong Country Returns HD (Switch)

Kod: `core/formats/unity/dklocal.py` (kayıt defteri ayrıştırıcı/yazıcı), `core/formats/unity/unity.py` (eklenti bağlantısı).
Test: `tests/test_dkcr.py`.

## Nerede ne var

Oyun Unity 6000.0.28f1 (IL2CPP) ile çalışır. **Tüm oyun metni tek bir nesnededir:** `Data/resources.assets` içindeki
`Localization` adlı `MonoBehaviour` (2,7 MB). Tip ağacı silinmiştir; nesne ham bayttan çözülür. Başka dosyada çevrilebilir
metin yoktur (179 `level*`/`sharedassets*` dosyası taranır ama boş çıkar; bu taramanın kendisi yaklaşık 3 dakika sürer).

Base (v0) ve güncelleme (v65536) `resources.assets`'i farklı üretilmiştir: nesne düzeni biraz değişmiştir (aşağıda).
Rusça topluluk yaması yalnızca `resources.assets`'i değiştirir ve yalnızca **0 numaralı dil yuvasını** (İngilizce)
Rusçayla doldurur; Türkçe de aynı yuvaya yazılır.

## `Localization` nesnesi

Unity'nin `[SerializeReference]` kayıt defteri. Nesne içinde ofset yoktur (sıralı); bir dizgenin boyu değişince yalnızca
uzunluk alanı ve 4 bayt hizalaması değişir, geri kalan her şey aynen yazılır.

```
MonoBehaviour başlığı: m_GameObject (12) | m_Enabled (4) | m_Script (12) | m_Name = "Localization"
int n; n × int64            dil listesi: her dilin LanguageData kimliği (rid); -2 = boş yuva (5. dil)
int 2; int sayı             kayıt defteri sürümü ve kayıt sayısı
sayı × kayıt:
    int64 rid; dizge sınıf; dizge "dk3ds"; dizge "Assembly-CSharp"
    (boş)                       rid -2, üç boş dizge
    LanguageData                int dil sırası; int m; m × int64 yuva rid'i
    SingleLanguageDataItem      [dizge ad]; dizge metin; uint32 numara; dizge etiket; uint32; uint32
    MultipleLanguageDataItem    uint32 numara; [dizge ad]; int m; m × int64 (SingleLanguageDataItem rid'leri)
```

- **Ad dizgeleri** (`NewText_60`, `blow`) yalnızca v0'dadır; güncellemede kaldırılmıştır. `parse` önce adsız, sonra adlı düzeni dener;
  kayıt defterini nesnenin son baytında bitiren geçerli olur. v0 ve güncelleme nesneleri ile Rusça yamanın nesnesi
  değişiklik yapılmadan **bayt bayt aynı** yazılıyor (gerçek dosyalarla doğrulandı).
- **Etiket:** `*` (genel), `*_1/_2/_3` (seviye adları, üç kez), `OPT`, `DIS`, `CON`, `INT` (balon satışıyla ilgili konuşma metinleri),
  `Core`/`Standard`/`Grab`/`Up`/`Blow` (ses ve animasyon kimlikleri, çevrilmez). Alfabetik etiketler çeviri tablosunda bağlam olur.
- **Yuvalar:** bir dilin yuvası tekli öğeye ya da çoklu öğeye (`["Hit", "Hits"]`, `["Jungle", "Beach", …]`) bağlıdır. Çoklu öğenin
  çocukları aynı dilin başka bir yuvasındaki metne de işaret edebilir; bu yüzden her metin bir kez, ilk yerinde sayılır.
  Anahtar: doğrudan yuva `DK|<nesne>|<dil sırası>|<yuva>`; yalnızca çocuk olan metin `…|<yuva>.<k>`.
- **Sayılar (güncelleme):** 14 dil × 1.321 benzersiz metin = 18.494 tekli öğe (+ 2.282 çoklu öğe + 14 dil + 1 boş = 20.791 kayıt).
  İngilizce yuvada 1.199 çevrilebilir metin çıkar (boş, harfsiz ve ses kimliği olanlar atlanır).

## Diller

| Sıra | Dil | Sıra | Dil |
|---|---|---|---|
| 0 | İngilizce | 8 | Fransızca (ikinci) |
| 1 | Fransızca | 9 | İspanyolca (ikinci) |
| 2 | İspanyolca | 10 | Felemenkçe |
| 3 | Almanca | 11 | Portekizce |
| 4 | İtalyanca | 12 | Çince (basit) |
| 5 | (boş) | 13 | Çince (geleneksel) |
| 6 | Japonca | 14 | Korece |
| 7 | İngilizce (ikinci) | | |

Sıra, her dilin metinlerinden çıkarıldı; oyunun hangi yuvayı hangi sistem diliyle seçtiği **doğrulanmadı** (yalnızca Rusça yamanın
0'ı değiştirdiği kesin). Aynı dili taşıyan ikinci yuvada (0 ve 7) birkaç satır farklı yazılmıştır
(`1 Player Mode` / `1-Player Mode`, `A save file could not be created…` / `Could not create save file…`).

## Dışa aktarma

Türkçe, aktarılan yuvaya yazılır (varsayılan İngilizce). Aynı dilin ikinci yuvasında (İngilizce 7) aynı sıradaki satırın **özgün
metni de özdeşse** aynı çeviri oraya da yazılır; böylece oyun hangi İngilizce yuvayı okursa okusun Türkçe görünür. Özdeş olmayan
satırlar (≈9) ikinci yuvada İngilizce kalır. Mod tek dosyadır: `…/romfs/Data/resources.assets` (≈28 MB). Yazım sonrası dosya
yeniden okunup her metin doğrulanır; `MonoBehaviour` dışındaki tüm nesneler aynen korunur.

## Bilinen sınırlar

- **Cihazda denenmedi.** UnityPy dosyayı yeniden yazarken nesneleri 8 bayta hizalar; güncellemedeki orijinal 16 bayta hizalıydı
  (v0 ve Rusça yama zaten 8). Nesne tablosu ofsetleri açıkça yazıldığından sorun beklenmiyor ama doğrulanmadı.
- **Yazı tipi:** oyunun TMP yazı tipleri de tip ağacı olmayan dosyalardadır; `ğ ş ı İ` gliflerinin varlığı denetlenemiyor.
  Rusça yamanın `resources.assets`'i orijinalden yaklaşık 5 MB büyüktür; Kiril harflerin yazı tipine eklenmiş olması muhtemeldir
  (incelenmedi). Oyunda `ğ ş ı İ` görünmüyorsa dışa aktarmada harf dönüştürme (ğ→g…) seçilmelidir.
- `The following columns/windows apply only to NEW TEXTS :` her dilin ilk satırıdır; yerelleştirme tablosunun başlık notudur,
  oyunda görünmez ama çeviri tablosuna girer.
