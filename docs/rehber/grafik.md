# Grafik — resimlerin içindeki yazıları çevirmek

## Ne zaman okunur
Kullanıcı "menü başlıkları, düğme yazıları, ara sahne kartları, hikâye ve rehber sayfaları hâlâ İngilizce" diyor ve
`yeni-oyun.md` adım 2'deki `ara` komutu o yazıyı hiçbir dosyada bulamıyor. Böyle yazılar metin değil **resimdir**
(doku, DDS, PNG…). Önce `AGENTS.md` (oyun resimleri telifli: depoya konmaz, paylaşılmaz).

## Ana fikir
Resmin içindeki yazı çeviri tablosuna girmez. İş akışı iki yarıdır:
1. **Uygulama** oyundaki resimleri bulup çıkarır (`orijinal/`), değiştirilmiş resmi oyun dosyasına **aynı biçimde,
   aynı boyutta** geri yazar.
2. **Kullanıcı** (Photoshop, GIMP vb.) yazıyı silip Türkçesini çizer. Bu iş sanat işidir; ajan çizmez, kullanıcı yapar
   (ya da yazı sade ve zemin düzse ajan tek tek etiketler için araç yazabilir; DMC1'de böyle yapıldı).

## Yöntem: iki klasör

```
<oyun klasörü>/grafik_temizleme/
    orijinal/   ← uygulamanın çıkardığı özgün resimler (PNG); DEĞİŞTİRMEYİN
    temiz/      ← kullanıcının yazısını Türkçeleştirdiği resimler, AYNI ADLA
    OKUBENI.txt ← kullanıcıya kısa açıklama (Ys Origin'de uygulama yazar)
```

- Dışa aktarma yalnızca `temiz/` içinde `orijinal/` ile **gerçekten farklı** olan resimleri yerleştirir; aynı kalanlar
  yok sayılır.
- Boyut değişmişse özgün boya ölçeklenir. PNG saydamlık kaydetmediyse özgünün alfa kanalı korunur.
- Oyunun resim biçimi korunur: Ys Origin DDS'inde özgün başlık, biçim (BC3/BC1) ve mip sayısı aynen kalır, her mip
  seviyesi yeniden kodlanır, dosya boyu doğrulanır.
- Klasörü ortam değişkeni gösterir (arayüzde ayar yoktur, TECH_DEBT 75): `NXCEVIRI_YS_GRAFIK` (Ys Origin; yoksa
  oyun dosyalarının yanındaki `grafik_temizleme`), `NXCEVIRI_DMC1_GRAFIK` (Devil May Cry).

## Çözülmüş örnekler

### Ys Origin (`fontpatch/ys_graphics.py`, `docs/formats/ys-origin.md` "Grafikler")
- 150 çevrilebilir resim: `data-en.ni` içinde `EXTENSION/STORY/EN/*.DDS` (140: harita ve patron adları, hikâye ve rehber
  sayfaları) ve `EXTENSION/MENU/*/*_EN.DDS` (8: seçenek düğmeleri, onay kutuları); serbest `menu/categories_atlas.dds`
  ve `demo/demo_over.dds` (baş aşağı saklanır, PNG'de dik gösterilir).
- Biçim: DDS, BC3 (DXGI 77) veya BC1, mip zincirli, DX10 başlığı. Ana arşivdeki (`data.ni`, 946 MB) resimler kapsam
  dışıdır (TECH_DEBT 74).
- `orijinal/` klasörü şimdilik bir betikle üretilir: `ys_graphics.export_originals(read, members, folder)`
  (arayüz yok, TECH_DEBT 75). Betiği çalıştırmak gerekiyorsa kullanıcıya söyle; kendiliğinden oyun dosyası arama.

### Devil May Cry (`fontpatch/dmc1_images.py`, `dmc1_graphics.py`, `labels.py`, `dmc1_menu.py`, `dmc1_animation.py`; `docs/formats/dmc1.md`)
- Sayfalar çeşitli kapsayıcılardadır (`.itm`, `.dat`, `.tm2`, `.t32`, `.pack`, `.bnd`); hepsinde sıradan DDS başlıkları
  durur (BC7 DX10, 32 bit BGRA; birkaçı DXT3/DXT5). Uygulama kapsayıcıyı çözmez: dosyadaki DDS başlıklarını bulur,
  sayfayı çözer, **içerik özetiyle** (çözülmüş RGBA'nın SHA-1'i) tanır ve değiştirileni aynı biçimde, **yerinde**
  yazar (BC7'de yalnızca değişen 4×4 bloklar yeniden kodlanır). Aynı resim onlarca dosyada tekrar eder; özet aynı
  olduğu için hepsi değişir.
- Üç çizim yolu: (1) etiket çizimi (`labels.py`): koyu zemin üzerinde parlayan yazı silinir, Türkçesi aynı boy ve
  taban çizgisinde çizilir; (2) zemin dolgusu: zemin çevresinden yayılarak doldurulur, yazı özgünle doldurulmuş zemin
  farkından bulunur; (3) kullanıcının hazır sayfası (`temiz/` yolu) etiket çiziminin yerine geçer.
- Yazıların bulunması: `ara` bulamaz; taramada ~150 farklı yazılı resim çıktı. Dil klasörü sırası `status_e` →
  `status_u` → `status` olduğundan birçok resim dilden bağımsız `status/` içindedir.
- Görev girişi animasyonları (60 kare DXT1): kullanıcı yalnızca `*_son_kare.png` dosyasını Türkçeleştirir;
  ara kareler `dmc1_animation.py` ile türetilir.
- Yazılar video içinde de olabilir (açılış uyarısı `title.mp4`): bu uygulama dışında ffmpeg ile yapıldı (TECH_DEBT).
- Bilinen sınır: BC7 kayıplı kodlandığı için sonuç hazır resme ~29-42 dB yakındır.

### Yazısı resimde kalanlar
Unicorn Overlord'un yazılı yardım resimleri (`Help/*.ftx`) çevrilmedi (TECH_DEBT 73). Donkey Kong Country Returns HD
(`dkcr.md`) bu rehberde grafik örneği değildir: metni tek nesnededir, resim çevirisi yapılmadı.

## Yeni bir oyunda adımlar
1. **Ekranda yazıyı kanıtla:** `ara "<yazı>"` bulamadı; yazı resimdir (ya da sıkıştırılmıştır: farkı `yeni-oyun.md`
   adım 2).
2. **Resim biçimini bul:** `python -m nxceviri.arac teshis …` raporunda uzantı dağılımına bak (`.dds`, `.png`, `.tex`,
   `.t32`, `.ftx`, Unity `Texture2D`…). İlgili dosya içindeki imza: `DDS ` (4 bayt), `\x89PNG`, UnityFS içindeki
   `Texture2D`. DDS'in `fourCC` ya da DX10 başlığındaki DXGI numarası sıkıştırma biçimini söyler (71 = BC1, 77 = BC3,
   98 = BC7).
3. **Çıkar ve göster:** resimleri PNG olarak `orijinal/`e yaz (Pillow DDS'i BC1/BC3 için okur; BC7 için
   `fontpatch/bc7.py` kodlayıcısı var). Sayfa/resim sayısını kullanıcıya söyle. Hepsi çevrilmez: kullanıcıdan hangi
   ekranların önemli olduğunu sor.
4. **Geri yazma işlevini yaz** (`game_file_patches` kancası, `eklenti-yazma.md`): özgün resmi içerik özetiyle tanı,
   değişeni aynı biçim, boyut, mip ve başlıkla yaz. Test: değişikliksiz geri yazım bayt bayt aynı; bir resim
   değişince yalnızca o resim değişir; yazılan dosya yeniden okunur.
5. **Kullanıcıya `temiz/` klasörünü ve adlandırma kuralını anlat:** aynı ad, aynı boyut, (mümkünse) saydamlık
   kanalıyla PNG. Fırça/gotik gibi yazı tipi tutturmak istiyorsa uygulamayla gelen OFL yazı tipleri
   (`nxceviri/assets/fonts`: Kaushan Script, Pirata One) kullanılabilir.
6. **Dışa aktar ve kullanıcı cihazda/emülatörde bakar.** Resimler çok yer kaplar; mod boyutunu söyle.

## Karar noktaları
- **Yeni kod yazmadan önce:** yazı sayısı azsa (10-20 etiket) kullanıcının elle yaptığı `temiz/` yolu, çoksa ve düz
  zeminse etiket çizimi daha verimli olabilir.
- **Büyük arşiv:** resim 1 GB'lık bir arşivdeyse tamamını moda koymak gerekir; kullanıcıya boyutu sor (Ys Origin ana
  arşivi bu yüzden kapsam dışı).
- **Dile bağlı mı?** Bazı resimler `EN` klasöründedir (yalnızca o dil için değişir), bazıları dilden bağımsızdır;
  ikinci grubu değiştirmek oyunun tüm dillerini etkiler.

## Bitti ölçütü
`temiz/`deki her farklı resim moda yazıldı (uygulama sayıyı söyler), yazılan dosyalar yeniden okundu ve boyutları
özgünle aynı, testler yeşil. Cihazda görsel doğrulama kullanıcıdadır; yapılmadıysa "cihazda denenmedi".

## Kullanıcıya rapor
Kaç resim çıkarıldı, kaç tanesi çevrildi, hangi ekranlar hâlâ İngilizce, mod boyutu, kullanıcının cihazda bakacağı
ekranlar. Çizim kalitesi (BC7 kaybı gibi) sınırlarını açıkça yaz.
