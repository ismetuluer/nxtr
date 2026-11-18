# Font — Türkçe harflerin oyunda görünmesi

## Ne zaman okunur
Kullanıcı oyunda `ğ ş ı İ` gibi harflerin kutucuk, boşluk ya da başka bir harf olarak göründüğünü söylüyor; ya da
yeni bir oyunda dışa aktarmadan önce fontları denetlemek istiyor. Hedef harfler: `ç ğ ı İ ö ş ü Ç Ğ Ö Ş Ü`.
Önce `AGENTS.md` (kontrol kodları, dürüst rapor). Sorun yalnızca "kutucuk" değilse `sorun-giderme.md`.

## İlk adım: durumu gör
```
python -m nxceviri.arac font "<base.nsz>" "<update.nsp>"
```
Bu, uygulamadaki **Fontları Tara** ile aynı sonucu verir; son satır üç sonuçtan birini söyler: (a) hepsi var, (b) font
yamasıyla eklenebilir, (c) yamalanamıyor, harf dönüştürme gerek. Sonuca göre aşağıdaki adımlara geç. Komut yama
uygulamaz; yama uygulamada açılır.

## Ana fikir
Oyun metni bir **fontla** çizer. Fontta bir harfin çizimi (glif) yoksa Türkçe çeviri doğru dosyaya yazılsa bile
oyunda görünmez. Üç çözüm vardır; bu sırayla düşün:

1. **Fontta zaten var** (bazı oyunlarda; çoğu Latin font `ç ö ü` için): yapacak bir şey yok.
2. **Font yaması:** uygulama eksik harfleri **fontun kendi glifleriyle** türetip fonta ekler (ı = i'nin noktasız
   gövdesi, İ = I + nokta, ş = s + ç'nin çengeli, ğ = g + üstte yay). Yazı tipi değişmez, dış çizgi ve gölge korunur.
   Uygulamanın yerleşik yaması fontu tanımıyorsa yama oyunun eklentisinde yazılır ("Yeni font biçimi").
3. **Harf dönüştürme:** eksik harf yakın karşılığa çevrilir (ğ→g, ş→s, ı→i, İ→I). Yalnızca üretilen moda uygulanır,
   projedeki çeviriler değişmez. Font yamasının kanıtla imkânsız olduğu durumda son çare.

## Harfler nasıl türetilir

Üç yamacı (vektör TTF/OTF ve Switch sistem fontu, TextMeshPro atlası, BMFont) işareti aynı sırayla arar
(`nxceviri/core/fontpatch/sources.py`, `ARCHITECTURE.md` karar 234):

| Harf | Kaynak sırası (ilk uygun olan kullanılır) |
|---|---|
| ı | `i`'nin noktası silinir → (yalnızca vektör fontta) `I` x-yüksekliğine küçültülür |
| İ | `I` + nokta: `i`'nin noktası → `ż Ż ċ Ċ ė Ė` noktası → `ö`/`Ö`'nün bir noktası → nokta işareti (`.`) → çizilir |
| ş | `s` + çengel: `ç`'nin taban çizgisi altı → `Ç`'ninki → virgül (`,`) → çizilir |
| Ş | `S` + çengel: `Ç`'nin → `ç`'nin → virgül → çizilir |
| ğ | `g` + kavis: `ă` → `˘` (U+02D8) → `ŭ` / `ŏ` → `Ă` / `Ŭ` / `Ŏ` → çizilir |
| Ğ | `G` + kavis: `Ă` → `˘` → `Ŭ` / `Ŏ` → `ă` / `ŭ` / `ŏ` → çizilir |

İşaret kaynaktan olduğu gibi alınır, ölçeklenmez (küçük harften alınıp büyük harfe konduğunda da); yalnızca taban harfe
ortalanır ve kaynaktaki yüksekliği korunur. Bilgi dosyasında her font satırı hangi kaynağın kullanıldığını yazar
(`bigtext (resources.assets): ı İ ş Ş ğ Ğ — ı: i'den nokta silindi, …, ğ: çizildi`). "çizildi" gören harf fontun
kendi çizimi değildir; cihazda ona özellikle bak. Vektör fontta yeni harfler taban harfin kerning'ini devralır; işaret
fontun üst sınırını aşıyorsa satırda "oyunda kesilebilir" notu çıkar (metrikler değiştirilmez).

## Adımlar (uygulamadaki yol)
1. **4. Kontrol Et → "Font ve harfler" sekmesi → Fontları Tara.** Tablo: Font, Tür, Eksik Türkçe harfler, Yamayla
   eklenir, Dosya. Okuma:
   - "Eksik harf" = Latin fontların çoğunluğunda (yarıdan fazlasında) olmayan harf. Dile özgü fontlar (japanese,
     chinese, russian… adlı) sayılmaz.
   - "Yamayla eklenir" sütununda olmayan harf o fontta eklenemiyor demektir.
   - Switch sistem fontları (`.bfttf`/`.bfotf`) artık listelenir; eski sürümde "okunabilen font bulunamadı" diyen
     projede **Fontları Tara**'yı yeniden çalıştır, yoksa font yaması bu fontları bilmez.
2. Eksik harf varsa **"Eksik Türkçe harfleri fontlara ekle (font yaması)"** kutusunu işaretle. Kapalıysa harf dönüştürme
   seçeneğini ("yok / yalnızca eksik harfler / tüm Türkçe harfler") belirle; yama açıkken dönüştürme yalnızca
   yamanın ekleyemediği harflere uygulanır.
3. **5. Dışa Aktar.** Yamalanan font dosyaları moda yazılır; `NXTR - Bilgi.txt` hangi fontlara hangi harflerin
   eklendiğini, hangilerinin eklenemediğini listeler. Dışa aktarma yazdığı fontu yeniden açıp harflerin gerçekten
   var olduğunu doğrular.
4. **Cihazda / emülatörde göz kontrolü kullanıcıdan istenir** (`docs/test-emulator.md`): ana menü ve ayarlar
   ekranında `ç ğ ı İ ö ş ü` yazan bir satır. Kutucuk varsa tabloya geri dön.

## Font türleri ve ne yapar

| Tür | Nerede | Ne yapılır | Not |
|---|---|---|---|
| Unity **TextMeshPro, statik** atlas | `TMP_FontAsset` (bundle veya `.assets`) | Glifler SDF olarak atlasa çizilir; atlas dolarsa iki katına büyür | `docs/formats/tmp-font.md` |
| Unity **TMP dinamik** / eski `Font` | Gömülü TTF/OTF `Font` nesneleri | TTF/OTF'e glif eklenir (sona eklenir, numaralar kaymaz) | Dinamik font harfi çalışma anında gömülü TTF'den üretir; orada yoksa yedek fonta düşüp farklı görünür |
| **TTF / OTF** (RomFS'te serbest) | `*.ttf`, `*.otf` | Aynı glif ekleme | CID anahtarlı CFF ve CJK (≥200 CJK karakteri) fontlar atlanır |
| **Switch sistem fontu** `.bfttf`/`.bfotf` (`.zs`) | `mesg/Font/…` gibi RomFS'te serbest ya da SARC içinde | Taranır (Tür: "Switch sistem fontu"); yama açıksa zstd + XOR katmanı çözülür, `ı İ ş Ş ğ Ğ` eklenir, aynı başlık ve anahtarla yeniden paketlenip aynı yola yazılır | Yalnızca ASCII taşıyan CJK fontlar (Çince/Korece) dile özgü sayılır, yamalanmaz; Japonca glifli Latin fontlar yamalanır. Dışarıda düzenleme (Fontu Dışa Aktar) bu türde yok. `docs/formats/switch-font.md` |
| **BMFont** (`*.fnt` ikili v3 + `*.png`) | NNI arşivli oyun | Eksik glifler atlasa çizilir, `.fnt`'e eklenir; atlas dolarsa yüksekliği ikiye katlanır | `docs/formats/nni.md` |
| **Oyunun kendi harf dokusu** | `.fsd`/`.msg` biçimli oyun, `msg_tex.t32` | Eklenti `support_files` ile Türkçe harfli yeni doku üretir | Harf kodları da özel (`0x72` + hücre); `fsd-msg.md` |
| Font tip ağacı olmayan dosyada | Ör. `Localization` nesneli Unity oyunu | Okunamaz; `ğ ş ı İ` denetlenemez | Cihazda deneyip gerekirse harf dönüştürme |

Atlanan durumlar raporlanır: dinamik fontlar (atlas yok), gerçekten çok atlaslı fontlar, atlası başka dosyada ya da
başka fontla ortak olanlar, kaynak harfi olmayan fontlar (yalnızca rakam içeren saat fontu), tip ağacı silinmiş
dosyalar. Raporda "atlandı" gördüğünde o fontun gerçekten oyunda kullanılıp kullanılmadığını sor.

## Karar noktaları
- **Yamayı açmalı mıyım?** Eksik harf ve "Yamayla eklenir" sütunu doluysa evet. Yama çıktısı kullanıcının cihazında
  denenmeden "çalışıyor" deme.
- **Yama bir fonta uygulanamadı ya da font biçimi yeni:** uyarı verilir, sessizce dönüştürmeye geçilmez. Türkçe harfi
  eksik her font ailesi Türkçe destekli hale getirilir: font biçimini çöz ve yamayı **oyunun eklentisinin içinde**
  yaz (aşağıda). Ana koda (`nxceviri/`) yama yazılmaz; çekirdekteki yamacılar eklentilere açık değildir
  (`eklenti-yazma.md` "İzinli çekirdek modülleri"), gerekirse benzer kodu eklentiye kendi modülü olarak yaz.
- **Yeni font biçimi (eklentide):** fontun glif tablosunu çözmeden başlama. Sırayla: (1) fontun hangi harfleri
  taşıdığını `fontTools` ile / biçimin kendi tablosundan oku; (2) eksik harfi hangi parçalardan türeteceğini seç (i, I,
  s, ç, g…); (3) yeni glifi biçimin kendi atlasına/tablosuna yazan kodu eklenti klasöründe ayrı bir modüle yaz
  (`eklentiler/<ad>/font.py`, `plugin.py`'de `from . import font`); (4) yamalanan dosyayı moda koy:
  `derived_files(read, files, game_dir)` → `Derived(files=…)` (serbest dosya) ya da `Derived(members=…)` (arşiv
  üyesi), oyunun özel harf dokusu için `support_files()`, yerinde dönüştürme için `game_file_patches()`;
  `Derived.font_notes`'a eklenen harfleri yaz; (5) yazılan dosyayı yeniden oku ve harfin gerçekten orada olduğunu
  doğrula; (6) elle üretilmiş örnek fontla eklentinin `tests/` klasöründe test yaz; (7) eklentide
  `unsupported_letters = ""`.
- **Harf dönüştürme ne zaman?** Yalnızca font yamasının **kanıtla** imkânsız olduğu harflerde (font şifreli ya da
  okunamıyor, glif tablosu sabit ve büyütülemiyor; denemenin komut çıktısı raporda). O zaman yalnızca o harfler
  `unsupported_letters`'a yazılır.
- **Harf dönüştürme mi font yaması mı?** Yama görünümü korur ama gerçek cihaz testi ister; dönüştürme her zaman
  çalışır ama metin yazım kuralını bozar. Kullanıcıya önerini kısa gerekçeyle söyle.

## Bilinen tuzaklar
- Atlas büyütülünce `m_AtlasHeight`, `m_CreationSettings.atlasHeight` ve atlası kullanan malzemelerin
  `_TextureHeight` değeri güncellenir; elle yazıyorsan unutma.
- Fontta `ă`, `˘`, `ŭ`, `ŏ` yoksa breve (ğ'nin üstü) çizilir, fontun kendi çizimi değildir (TECH_DEBT 50/76); el
  yazısı fontlarda biraz farklı görünür. Bilgi dosyasında "ğ: çizildi" yazar.
- Bazı Unity oyunlarında fontlar yalnızca "font" adlı paketlerde değil, ana sahne paketinde ve
  `resources.assets` içindedir; tarama bunları bulur ve projeye `font_files` olarak kaydeder.
- Unity Addressables kataloğu değiştirilmiş bir bundle'ı CRC nedeniyle reddedebilir (`docs/formats/unity.md`
  "Addressables katalog CRC'si"); font bundle'ı yamalandıktan sonra oyun açılmıyorsa buna bak.

## Bitti ölçütü
1. Fontları Tara tablosunda tüm Latin fontlar için eksik harf yok ya da "Yamayla eklenir" sütunu eksiği kapatıyor;
   yerleşik yamanın tanımadığı fontlar eklentideki yamayla kapatıldı (bilgi dosyasında listeleniyor). Yeni yama kodu
   eklenti klasöründe; `git status --porcelain nxceviri/` boş, `arac dogrula` içe aktarma bulgusu vermiyor.
2. Dışa aktarma hatasız bitti; `NXTR - Bilgi.txt` eklenen harfleri listeliyor.
3. Kullanıcı cihazda/emülatörde Türkçe harfleri gördü. (Görmediyse rapor "cihazda denenmedi" der.)

## Kullanıcıya rapor
Kaç fontta hangi harf eksikti, hangilerine eklendi/hangileri atlandı ve neden, dönüştürme açık mı, kullanıcının
cihazda bakacağı yer ("Seçenekler ekranı"). Tahmin değil, tablodaki sayıları yaz.
