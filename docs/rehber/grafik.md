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
   (ya da yazı sade ve zemin düzse ajan tek tek etiketler için araç yazabilir; `.fsd`/`.msg` biçimli oyunda böyle yapıldı).

## Yöntem: iki klasör

```
<oyun klasörü>/grafik_temizleme/
    orijinal/   ← uygulamanın çıkardığı özgün resimler (PNG); DEĞİŞTİRMEYİN
    turkce/     ← kullanıcının yazısını Türkçeleştirdiği resimler, AYNI ADLA
    OKUBENI.txt ← kullanıcıya kısa açıklama (NNI arşivli oyunda uygulama yazar)
```

- Klasörün adı `turkce/`dir. Eski sürümlerin `temiz/` klasörü, `turkce/` yokken okunmaya devam eder; ikisi birden
  varsa `temiz/` yok sayılır ve uyarılır. Yeni kurulumda her zaman `turkce/` oluştur.

- Dışa aktarma yalnızca `turkce/` içinde `orijinal/` ile **gerçekten farklı** olan resimleri yerleştirir; aynı kalanlar
  yok sayılır.
- Boyut değişmişse özgün boya ölçeklenir. PNG saydamlık kaydetmediyse özgünün alfa kanalı korunur.
- Oyunun resim biçimi korunur: NNI arşivli oyunun DDS'inde özgün başlık, biçim (BC3/BC1) ve mip sayısı aynen kalır, her mip
  seviyesi yeniden kodlanır, dosya boyu doğrulanır.
- Yerleştirme klasörünü ortam değişkeni gösterir (Kontrol Et → Grafik'teki Klasör Seç… yalnızca karşılaştırma
  içindir, yerleştirmeyi değiştirmez; TECH_DEBT 75): `NXCEVIRI_NNI_GRAFIK` (NNI arşivli oyun; yoksa
  oyun dosyalarının yanındaki `grafik_temizleme`), `NXCEVIRI_FSD_GRAFIK` (`.fsd`/`.msg` biçimli oyun). 0.59.0 ve
  öncesinin adları (`NXCEVIRI_YS_GRAFIK`, `NXCEVIRI_DMC1_GRAFIK`) yeni ad tanımlı değilse okunmaya devam eder.

## Kontrol Et → Grafik sekmesi (denetim ve onay)
Kullanıcı Türkçe resimleri hazırladıkça uygulamada **Kontrol Et → Grafik** sekmesine bakar:
- **Klasör:** resim çevirisini bilen oyunda (eklenti `GraphicsSupport` sunuyor) klasör kendiliğinden bulunur; özgünler
  yoksa sekmedeki **Görselleri Çıkar** düğmesi (Dışa Aktar → Görseller ile aynı iş). Bilmeyen oyunda **Klasör Seç…**
  ile içinde `orijinal/` ve `turkce/` (ya da eski `temiz/`) bulunan klasör seçilir; seçim projeye kaydedilir. Bu
  durumda sekme yalnızca karşılaştırır, resimleri moda yerleştirmez (yerleştirme eklentinin işidir). Alt klasörler
  okunur: Türkçe resim `turkce/` içinde özgünüyle aynı alt klasörde ve aynı adla durur (`orijinal/ui/menu/a.png` ↔
  `turkce/ui/menu/a.png`); listede adı bu göreli yoldur.
- **Liste:** her resim için durum: Onaylandı, Hazır, Uyarı, Hata, Eksik, Değişmemiş. Hatalar: boyut özgünden farklı,
  arka plan saydamlığı kaybolmuş, `orijinal/`de aynı adlı resim yok, dosya açılamıyor. Uyarılar: özgünle aynı
  (düzenlenmemiş), yazı resmin kenarına değiyor (oyunda kesilebilir). Süzgeç: Sorunlu / Eksik / Hepsi.
- **Karşılaştırma:** Yan yana, Üst üste (sürgü özgünden Türkçeye geçer), Gidip gel (resme tıklayın ya da Boşluk).
  **Kılavuz** özgün yazının alanını kesikli çerçeveyle, Türkçe yazınınkini düz çerçeveyle gösterir (özgünü aşıyorsa
  kırmızı; bu otomatik sorun sayılmaz, Türkçe yazı doğal olarak daha geniş olabilir). Sığdır / %100.
- **Onayla** (`Ctrl+Enter`): resme gözle bakıldığını işaretler; dosya değişirse onay kalkar. Hatalı resim onaylanmaz.
- Liste, klasöre dosya kaydedilince kendiliğinden yenilenir; **Yenile** elle yeniden denetler.

Ajan bu sekmeyi kullanıcıya önerir; denetim sonucunu (ör. "3 resmin boyutu farklı") kullanıcıya iletir, resimleri
kendisi düzenlemez.

## Çözülmüş örnekler

### NNI arşivli oyun (`fontpatch/nni_graphics.py`, `docs/formats/nni.md` "Grafikler")
- 150 çevrilebilir resim: `data-en.ni` içinde `EXTENSION/STORY/EN/*.DDS` (140: harita ve patron adları, hikâye ve rehber
  sayfaları) ve `EXTENSION/MENU/*/*_EN.DDS` (8: seçenek düğmeleri, onay kutuları); serbest `menu/categories_atlas.dds`
  ve `demo/demo_over.dds` (baş aşağı saklanır, PNG'de dik gösterilir).
- Biçim: DDS, BC3 (DXGI 77) veya BC1, mip zincirli, DX10 başlığı. Ana arşivdeki (`data.ni`, 946 MB) resimler kapsam
  dışıdır (TECH_DEBT 74).
- `orijinal/` klasörü şimdilik bir betikle üretilir: `nni_graphics.export_originals(read, members, folder)`
  (arayüz yok, TECH_DEBT 75). Betiği çalıştırmak gerekiyorsa kullanıcıya söyle; kendiliğinden oyun dosyası arama.

### `.fsd`/`.msg` biçimli oyun (`fontpatch/fsdmsg_images.py`, `fsdmsg_graphics.py`, `labels.py`, `fsdmsg_menu.py`, `fsdmsg_animation.py`; `docs/formats/fsd-msg.md`)
- Sayfalar çeşitli kapsayıcılardadır (`.itm`, `.dat`, `.tm2`, `.t32`, `.pack`, `.bnd`); hepsinde sıradan DDS başlıkları
  durur (BC7 DX10, 32 bit BGRA; birkaçı DXT3/DXT5). Uygulama kapsayıcıyı çözmez: dosyadaki DDS başlıklarını bulur,
  sayfayı çözer, **içerik özetiyle** (çözülmüş RGBA'nın SHA-1'i) tanır ve değiştirileni aynı biçimde, **yerinde**
  yazar (BC7'de yalnızca değişen 4×4 bloklar yeniden kodlanır). Aynı resim onlarca dosyada tekrar eder; özet aynı
  olduğu için hepsi değişir.
- Üç çizim yolu: (1) etiket çizimi (`labels.py`): koyu zemin üzerinde parlayan yazı silinir, Türkçesi aynı boy ve
  taban çizgisinde çizilir; (2) zemin dolgusu: zemin çevresinden yayılarak doldurulur, yazı özgünle doldurulmuş zemin
  farkından bulunur; (3) kullanıcının hazır sayfası (`turkce/` yolu) etiket çiziminin yerine geçer.
- Yazıların bulunması: `ara` bulamaz; taramada ~150 farklı yazılı resim çıktı. Dil klasörü sırası `status_e` →
  `status_u` → `status` olduğundan birçok resim dilden bağımsız `status/` içindedir.
- Görev girişi animasyonları (60 kare DXT1): kullanıcı yalnızca `*_son_kare.png` dosyasını Türkçeleştirir;
  ara kareler `fsdmsg_animation.py` ile türetilir.
- Yazılar video içinde de olabilir (açılış uyarısı `title.mp4`): bu uygulama dışında ffmpeg ile yapıldı (TECH_DEBT).
- Bilinen sınır: BC7 kayıplı kodlandığı için sonuç hazır resme ~29-42 dB yakındır.
- Etiket çizimi için gereken tablo (hangi sayfada hangi İngilizce yazı nerede, Türkçesi ne; menü başlıkları için
  `menuler` bölümü) ve düşman açıklamaları uygulamayla gelmez. Kullanıcı `resim_yazilari.json` ve `aciklamalar.json`
  dosyalarını `NXCEVIRI_FSD_GRAFIK` klasörüne koyar (biçim ve uydurma örnek: `docs/formats/fsd-msg.md` "Ek çeviri
  verisi"). Dosya yoksa o yazılar İngilizce kalır ve bilgi dosyasında söylenir; bozuksa dışa aktarma hatanın yerini
  söyleyerek durur.

### Yazısı resimde kalanlar
CPK/FMSB biçimli oyunun yazılı yardım resimleri (`Help/*.ftx`) çevrilmedi (TECH_DEBT 73). `Localization` nesneli Unity oyunu
(`unity-serializereference.md`) bu rehberde grafik örneği değildir: metni tek nesnededir, resim çevirisi yapılmadı.

## Yeni bir oyunda adımlar
Bütün resim kodu (çıkarma, çözme, kodlama, geri yazma) **oyunun eklentisinin içinde** yazılır; metin ve font koduyla
aynı eklentide (`eklentiler/<ad>/resim.py`, `plugin.py`'de `from . import resim`). Ana koda (`nxceviri/`) yazılmaz.
Yukarıdaki çözülmüş örneklerin kodu (`fontpatch/…`) yerleşik biçimlere aittir ve eklentilere açık değildir
(`eklenti-yazma.md` "İzinli çekirdek modülleri"); gerekirse benzerini eklentiye yaz.

0. **Her oyunda tespit et ve bildir:** kullanıcı sormasa da teşhis raporundaki resim dosyalarına bak, yazı içerebilecek
   olanları (menü, başlık, düğme, harita, hikâye kartı) say ve kullanıcıya **sayı ve birkaç örnek adla** bildir; ilgili
   ekranları çevirmek isteyip istemediğini sor. İsterse aşağıdaki adımlar.
1. **Ekranda yazıyı kanıtla:** `ara "<yazı>"` bulamadı; yazı resimdir (ya da sıkıştırılmıştır: farkı `yeni-oyun.md`
   adım 2).
2. **Resim biçimini bul:** `python -m nxceviri.arac teshis …` raporunda uzantı dağılımına bak (`.dds`, `.png`, `.tex`,
   `.t32`, `.ftx`, Unity `Texture2D`…). İlgili dosya içindeki imza: `DDS ` (4 bayt), `\x89PNG`, UnityFS içindeki
   `Texture2D`. DDS'in `fourCC` ya da DX10 başlığındaki DXGI numarası sıkıştırma biçimini söyler (71 = BC1, 77 = BC3,
   98 = BC7).
3. **Çıkar ve göster:** eklentide `graphics = GraphicsSupport(folder_name, export)` sun (`nxceviri.core.formats.derived`);
   `export` resimleri PNG olarak `orijinal/`e yazar, uygulama bunu Dışa Aktar → Görseller'den çağırır ve `turkce/`
   klasörünü kurar. Çözme: Pillow DDS'i BC1/BC3 için okur; BC7 ya da oyuna özgü doku biçimi için çözücü/kodlayıcıyı
   eklentinin kendi modülü olarak yaz. Sayfa/resim sayısını kullanıcıya söyle. Hepsi çevrilmez: kullanıcıdan hangi
   ekranların önemli olduğunu sor.
4. **Geri yazma işlevini yaz** (`derived_files` ya da yerinde dönüştürme için `game_file_patches` kancası,
   `eklenti-yazma.md`): okunacak klasörü `derived.turkish_dir(klasör)` verir; özgün resmi içerik özetiyle tanı,
   değişeni aynı biçim, boyut, mip ve başlıkla yaz. Test: değişikliksiz geri yazım bayt bayt aynı; bir resim
   değişince yalnızca o resim değişir; yazılan dosya yeniden okunur.
5. **Kullanıcıya `turkce/` klasörünü ve adlandırma kuralını anlat:** aynı ad, aynı boyut, (mümkünse) saydamlık
   kanalıyla PNG. Fırça/gotik gibi yazı tipi tutturmak istiyorsa uygulamayla gelen OFL yazı tipleri
   (`nxceviri/assets/fonts`: Kaushan Script, Pirata One) kullanılabilir.
6. **Dışa aktar ve kullanıcı cihazda/emülatörde bakar.** Resimler çok yer kaplar; mod boyutunu söyle.

## Önceki oyunlardan tuzaklar
Her bulguyu oyunun `NOT.md` "Resimdeki yazılar" bölümüne yaz (hangi arşivde ne var, kopyalar, oyunda kullanılan
kopya); kullanıcının resim koyduğu klasörleri `CALISMA_GUNLUGU.md`'ye. Sonraki ajan resimleri yeniden aramaz.
- **Oyunda görünen kopyayı doğrula.** Aynı ekranın resmi birden çok pakette olabilir (eski çözünürlük + yüksek
  çözünürlüklü yeniden yapım paketi, dil başına paket). Kullanıcının ekran görüntüsünü adaylarla karşılaştırmadan
  çevirtme; şüphede ikisini de çıkar ve hangisinin kullanıldığını cihaz denemesiyle doğrula.
- **Aynı resim birden çok konumda.** Arşivde aynı doku farklı ofsetlerde tekrar edebilir; yalnızca biri değişirse
  oyun ötekini gösterir. Resmi içerik özetiyle (hash) tanı, bütün konumlarını bir dizine çıkar (`hash → [konumlar]`)
  ve Türkçesini hepsine yaz. Aynı resmin iki çevirisi varsa en yenisini kullan ve kullanıcıya söyle.
- **Metin ve resim aynı dosyadaysa** resim adımı metin yazılmış baytlardan başlar; orijinalden başlarsa metin
  yamasını ezer.
- **Değişti mi denetimi bayt kıyasıyla.** Pillow'da RGBA fark resminin `getbbox()`'ı yalnızca alfa kanalına bakar,
  renk değişikliğini kaçırır; `a.tobytes() != b.tobytes()` ile karşılaştır.
- **Animasyonlu başlıklar** (kare kare dokular): kullanıcı yalnızca son kareyi Türkçeleştirir; son karedeki farkı
  bütün karelere aktar, yazı bölgesini kısmen sabitle (titreşmesin), son kareyi Türkçenin aynısı yap.
- **Kullanıcıya bir kerede ver.** Bir ekranın bütün adaylarını (bütün paketlerden) tek seferde `orijinal/`e çıkar ve
  listesini (`OKU.md`: dosya → ekran) yaz; parça parça vermek tur kaybettirir. Kullanıcı Türkçeleri farklı bir
  klasöre koyabilir: klasörü sorup günlüğe yaz.
- **Başka platformun (PC) Türkçe yaması varsa** resimleri doğrudan konmaz: sanat aynı olsa da Switch sürümü farklı
  doku biçimi (BC3 yerine BC7) ve kimi sayfada iki kat çözünürlük kullanabilir. Türkçe resmi Switch dosyasının
  biçimine yeniden kodla; her sayfayı Switch dosyasıyla karşılaştır.
- **Video:** yazı videodaysa resim taraması bulmaz; `yeni-oyun.md` "video ve program kodu".

## Karar noktaları
- **Yeni kod yazmadan önce:** yazı sayısı azsa (10-20 etiket) kullanıcının elle yaptığı `turkce/` yolu, çoksa ve düz
  zeminse etiket çizimi daha verimli olabilir.
- **Büyük arşiv:** resim 1 GB'lık bir arşivdeyse tamamını moda koymak gerekir; kullanıcıya boyutu sor (NNI arşivli oyunun ana
  arşivi bu yüzden kapsam dışı).
- **Dile bağlı mı?** Bazı resimler `EN` klasöründedir (yalnızca o dil için değişir), bazıları dilden bağımsızdır;
  ikinci grubu değiştirmek oyunun tüm dillerini etkiler.

## Bitti ölçütü
Yazılı resimlerin sayısı ve örnek adları kullanıcıya bildirildi. Kullanıcı istediyse `turkce/`deki her farklı resim
moda yazıldı (uygulama sayıyı söyler), yazılan dosyalar yeniden okundu ve boyutları özgünle aynı, testler yeşil; resim
kodu eklentide, `git status --porcelain nxceviri/` boş. Cihazda görsel doğrulama kullanıcıdadır; yapılmadıysa "cihazda denenmedi".

## Kullanıcıya rapor
Kaç resim çıkarıldı, kaç tanesi çevrildi, hangi ekranlar hâlâ İngilizce, mod boyutu, kullanıcının cihazda bakacağı
ekranlar. Çizim kalitesi (BC7 kaybı gibi) sınırlarını açıkça yaz.
