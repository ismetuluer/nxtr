# Yeni oyun — metinlere erişmek ve çeviri tablosuna aktarmak

## Ne zaman okunur
Kullanıcı "şu oyunu çevirmek istiyorum" diyor ya da uygulama taramada "0 metin" / "desteklenmeyen biçim" veriyor.
Önce `AGENTS.md` kurallarını (özellikle anahtar ve oyun dosyası sınırları) hatırla. Kurulum yoksa `baslarken.md`.

Kullanıcıdan gerekenler: oyun dosyalarının yolu (base NSP/NSZ, varsa güncelleme ve DLC), `prod.keys`'in uygulamada
seçili olması. Oyun dosyası aranmaz, indirilmez.

## Bağlayıcı kurallar (her ajan için)
1. **Ana koda yazma yok.** Yeni oyun için bütün kod tek bir eklenti klasöründe durur (`eklentiler/<ad>/` ya da
   `%LOCALAPPDATA%\NXCeviri\eklentiler\<ad>\`). `nxceviri/` altında dosya oluşturma, değiştirme. Eklenti yalnızca
   standart kütüphane, paketlenmiş bağımlılıklar, kendi modülleri ve izinli çekirdek modüllerini içe aktarır
   (`eklenti-yazma.md` "İzinli çekirdek modülleri"). Gereken yardımcı (font yamacı, doku kodlayıcı, arşiv okuyucu)
   çekirdekte yoksa ya da izinli değilse eklentinin içine ayrı modül olarak yazılır.
2. **Mazeretsiz teslim.** "Eklenti oluşturamıyorum" kabul edilmez. Yapabildiğin her parçayı (metin okuma ve yazma,
   font, resim) eklentide teslim et. Gerçekten imkânsız olanı (şifreli ya da açılamayan arşiv, bilinmeyen sıkıştırma)
   **komut çıktısıyla** kanıtla, raporda yaz ve o parça dışındaki işi bitir. "Yalnızca okuma" ancak yazma yolu
   denenip kanıtla olmadığı görüldüğünde ve raporda gerekçesiyle kabul edilir.
3. **Bütün metin dosyaları.** Teşhis raporundaki her metin adayı dosya ya eklentiyle kapsanır ya da raporda neden
   kapsanmadığı (kod, ad tablosu, başka dil, bozuk) dosya dosya yazılır. Bir cümleyi bulup yetinme.
4. **Varsayılan yalnızca İngilizce.** Kullanıcı başka dil demedikçe yalnızca İngilizce metin aktarılır. Dil dosya
   yolundaysa `language(data)` `None` döner (yol belirler); çok dilli dosyada `languages(data)` dilleri bildirir ve
   `extract` yalnızca `SOURCE_LANGUAGE` ile gelen dili (uygulamada varsayılan İngilizce) döndürür.
5. **Font önce yama.** Türkçe harfi eksik her font ailesi Türkçe destekli hale getirilir: önce uygulamanın yerleşik
   yaması; biçim yeniyse yama eklentinin içinde yazılır. Harf dönüştürme (`unsupported_letters`) son çaredir.
6. **Resimdeki yazılar.** Yazı içeren resimler tespit edilip sayısı ve örnek adlarıyla kullanıcıya bildirilir;
   kullanıcı isterse `grafik_temizleme/orijinal/` ve `grafik_temizleme/turkce/` klasörleri kurulur ve eklenti
   `turkce/`deki resimleri moda yerleştirir.
7. **Hepsi tek eklentide:** metin, font ve resim kodu aynı eklenti klasöründe.

## Adımlar

### 1. Teşhis
```
python -m nxceviri.arac teshis "<base.nsz>" "<update.nsp>" "<dlc.nsp>"
```
Üretilen `teshis-raporu.md` dosyasını oku (içinde oyun metni örnekleri olabilir; kullanıcıya "paylaşmadan önce
bakın" de). Rapor şunları söyler: TitleID ve sürüm, uzantı dağılımı, en büyük dosyalar, imza grupları, **motor tahmini**,
mevcut eklentilerin tanıdığı dosyalar ve aday metin dosyaları + örnek satırlar. Güncelleme dosyasını da ver:
metinler çoğu zaman update'te değişir ve update dosyası base'dekini geçersiz kılar.

Karar:
- Eklentilerin tanıdığı dosyalar var ve satırlar okunaklı → **yeni kod yazma**, adım 6'ya geç (font durumu, sonra uygulamayı kullan).
  `docs/uyumluluk.md` ve `docs/formats/README.md`'de oyun/biçim zaten çözülmüş olabilir; önce orayı oku.
- Hiçbir şey tanınmıyor ya da yalnızca bir kısmı tanınıyor → adım 2.

Raporun "aday metin dosyaları" listesini bir kapsam tablosuna çevir (dosya → kapsayan eklenti ya da kapsanmama
nedeni); iş bitene kadar bu tabloyu güncel tut, raporda göster (bağlayıcı kural 3).

### 2. Ekranda görülen metni dosyalarda bul
Kullanıcıdan oyunda gördüğü **kısa, ayırt edici bir cümleyi** iste (menü sözcüğü değil; bir diyalog cümlesi ya da eşya
açıklaması iyi olur). Sonra:
```
python -m nxceviri.arac ara "<cümle>" "<oyun dosyaları ya da çıkarılmış klasör>"
```
Çıktı: dosya, iç yol (iç içe arşiv için `arşiv>üye`), ofset, kodlama (UTF-8 / UTF-16 / Shift-JIS). Nasıl okunur:
- Hiç sonuç yok → metin sıkıştırılmış, şifreli ya da resimdir. Cümlenin bir parçasını (4-5 sözcük) dene; sonra
  sıkıştırılmış kapsayıcıları düşün (Unreal `.pak` Oodle sıkıştırmalıysa açılamaz: `docs/formats/unreal.md`,
  TECH_DEBT 37). Oyun metni resimdeyse `grafik.md`.
- Çok sayıda sonuç, hepsi aynı dosyada → o dosya metin tablosudur; adım 3'e.
- Sonuç dil klasörlerinde (`en`, `fr`, `ja`…) → yapı dil başına dosyadır; yalnızca kaynak dil aktarılır, `ja` kopyası
  bazen metni kimlikten ayırmaya yarar (NNI arşivli oyunda böyle).
- Aynı cümle birden çok yerde (SRT + TSV + önbellek) → oyunun hangisini okuduğunu bilmeden hepsini yaz (düz metin + `Locoliser` oyunu).

### 3. Motora göre yol
Kısa tarifler; ayrıntı ilgili not dosyasında (`docs/formats/README.md` dizin).

- **Unity** (`Data/StreamingAssets/aa/…` bundle'ları, `resources.assets`, `*.assets`): önce hazır eklenti dener
  (Unity Localization string tabloları, I2 Localization, düz `TextAsset`, `Locoliser`, `Localization` nesnesi).
  Metin tip ağacı olmayan dosyadaysa UnityPy alan adlarıyla okuyamaz; nesnenin **ham baytı** çözülür (`unity/i2.py`,
  `serializeref.py`). Kural: yapıyı tahmin etme, tüm nesneyi bitirebildiğin doğrulamalarla kabul et; doğrulanamayan
  nesneyi hiç okuma. "Unity oyunu, ama 0 satır" ise metin Unity dosyalarında olmayabilir (WAD/LIN biçimi: WAD içinde).
  Notlar: `unity.md`, `unity-serializereference.md`, `wad-lin.md`.
- **Unreal:** metin `.locres` dosyalarındadır, çoğu zaman `.pak` içinde. Eklenti ikisini de okur
  (`unreal.md`). Gerçek oyunla denenmedi; Oodle sıkıştırmalı pak'lar açılmaz.
- **LMS (MSBT) / SARC / Yaz0 / ZSTD:** hazır; kapsayıcı SARC/Yaz0/ZSTD içinde iç içe açılır
  (`msbt.md`, `archives.md`).
- **Bilinmeyen ikili biçim:** şu sırayla ilerle ve her adımı bir not dosyasına yaz (`NOT.md`):
  1. **İmza:** dosya başındaki 4-8 bayt (`MsgStdBn`, `AGAR`, `YCD\0`, `mdf\0`, `NNI\0`). Yüksek ihtimalle biçim
     adını verir; yoksa uzantı ve klasör adına bak.
  2. **Tablo / ofset yapısı:** metin sayısı, ardından ofset dizisi, ardından havuz mu? `ara` çıktısındaki ofsetlerden
     metinler arasındaki mesafeyi ve çevrelerindeki u16/u32 sayıları incele (uzunluk, ofset). Ofset dizisini
     metinlerin gerçek yerleriyle eşleştirebiliyorsan yapıyı çözdün.
  3. **Kodlama:** UTF-8 / UTF-16 / Shift-JIS yetmezse özel bir harf tablosu olabilir (`.fsd`/`.msg` biçiminde oyunun kendi
     hücre kodları var; `fsd-msg.md` "Karakter kodlaması").
  4. **Kontrol kodları:** metin içinde çıplak bayt dizileri (`0x0E…`, `\n`, `<color:…>`, `%s`, `{0}`). Hangi kodun yer
     ve uzunluk etkisi olduğunu belirle; her biri `⟦n⟧` olacak. Aynı kodun ham baytı geri yazılırken aynen korunur.
  5. **Yazma:** metin uzunluğu değişince hangi alanlar güncellenmeli (uzunluk, ofsetler, hizalama, dosya boyutu,
     kapsayıcı dizini)? Örnekler: WAD/LIN biçiminde kod bölümü dizgilere sıra numarasıyla başvurur, bu yüzden
     metin uzunluğu serbesttir (`wad-lin.md`); M2 PSB'de dizge tablosu yerinde yeniden yazılır (`psb.md`);
     CRI CPK ve FMSB (`cpk-fmsb.md`). Kapsayıcı bir arşivse (NNI, CPK, WAD), arşivi yeniden kuran kod
     izinli çekirdek modüllerinde (`nxceviri.core.archives.*`, `eklenti-yazma.md`) var mı bak; yoksa okuyucuyu ve
     yazıcıyı eklentinin içine ayrı modül olarak yaz. Yazma yolunu mutlaka dene; "yalnızca okuma" kararı ancak
     denemenin çıktısıyla verilir.

### 4. Eklenti iskeleti ve önce test
```
python -m nxceviri.arac eklenti-olustur <ad>
```
Kullanıcı eklentisi `eklentiler/<ad>/` (kaynak kurulum) ya da `%LOCALAPPDATA%\NXCeviri\eklentiler\` altında bir
klasördür: `eklenti.toml` + `plugin.py` + `tests/` + `NOT.md`; yardımcı kod `plugin.py`'nin yanında ayrı modüller
olarak durur (`from . import arsiv`; `eklenti-yazma.md` "Ana koda yazma yasağı ve çok dosyalı eklenti"). `nxceviri/`
altına hiçbir şey yazma. **Önce testi yaz** (`eklenti-yazma.md`): elle üretilmiş
küçük örnek dosya üretici + round-trip testi, başarısız olduğunu gör, sonra `extract` / `inject`'i yaz. Sözleşme ve
tuzaklar `eklenti-yazma.md`'de.

### 5. Gerçek dosyada doğrula
```
python -m nxceviri.arac dogrula <eklenti adı> "<base.nsz>" "<update.nsp>"
```
Çıktı dosya başına geçti/kaldı ve satır sayısını verir. Okuma: (a) değişikliksiz extract→inject **bayt bayt aynı**
mı, (b) işaret metni yazıp yeniden okuyunca aynı mı. Kalan dosya ya da satır sayısı beklenenden çok farklıysa
(ör. ekranda görülen 3000 satır yerine 12) eklenti metnin bir kısmını kaçırıyordur; `ara` sonuçlarıyla karşılaştır.
`dogrula` eklentinin ana koddan izinsiz ya da bu kopyada olmayan bir modül içe aktardığını görürse
`KALDI  İçe aktarma: …` yazar ve başarısız olur: gereken kodu eklenti klasörüne taşı. Her metin adayı dosyayı
kapsam tablosunda işaretle. **`dogrula` geçmeden iş bitmiş sayılmaz.**

### 6. Font durumu (zorunlu)
```
python -m nxceviri.arac font "<base.nsz>" "<update.nsp>" "<dlc.nsp>"
```
Aynı dosyaları ver (`--json` makinece okunur). Uygulamadaki **Fontları Tara** ile aynı sonucu verir; son satır
`Sonuç: …` üç durumdan birini söyler. Çıktıyı raporuna **aynen** yaz.

| Sonuç | Ne yapılır |
|---|---|
| (a) Türkçe harflerin tümü var | Ek iş yok. Eklentide `unsupported_letters = ""` bırak |
| (b) Eksik harfler font yamasıyla eklenebilir | `font.md`'yi izle (uygulamada Kontrol Et'te yama kutusu); eklentide `unsupported_letters = ""` |
| (c) Font yamalanamıyor / okunabilen font yok | Yerleşik yama bu fontu tanımıyor demektir: font biçimini çöz ve yamayı **eklentinin içinde** yaz (`font.md` "Yeni font biçimi"); moda `derived_files` / `support_files` / `game_file_patches` ile koy, `unsupported_letters = ""`. Harf dönüştürme yalnızca yamanın imkânsız olduğu komut çıktısıyla kanıtlanan harflerde (şifreli/okunamayan font, glif eklenemeyen sabit tablo) |

Harf kancaları `eklenti-yazma.md` "İsteğe bağlı kancalar" ve "Font ve resim kancaları"nda: `unsupported_letters`
(son çare), `normalize_text` (oyunun özel harf tablosu), `support_files` (Türkçe harfli yazı dokusu gibi ek dosya),
`derived_files` (yamalanmış font). Sonuç (b) ve (c) cihazda denenmeden "çalışıyor" denmez.

### 6b. Resimdeki yazılar (her oyunda)
Teşhis raporundaki resim dosyalarına (`.dds`, `.png`, `.bntx`, `.tex`, Unity `Texture2D`…) bak; yazı içerebilecek
olanları (menü, başlık, düğme, harita, hikâye kartı) say ve kullanıcıya **sayı ve birkaç örnek adla** bildir. Kullanıcı
isterse `grafik.md`'yi izle: eklenti özgünleri `grafik_temizleme/orijinal/`e PNG çıkarır, kullanıcı Türkçe resmi
aynı adla `grafik_temizleme/turkce/`e koyar, eklenti onları aynı biçim ve boyutta moda yerleştirir (aynı eklentide).

### 7. Uygulamada akış
Uygulamayı aç (`NX Ceviri Studyosu.bat` ya da `python -m nxceviri`):
1. **Oyunu Ekle:** base + update (+ DLC) dosyaları, `prod.keys` seçili.
2. **Metinleri Tara → Taramayı Başlat:** rapor motoru ve desteklenen dosyaları listeler; kaynak dili seç (varsayılan
   İngilizce); tablodaki "Aktar" kutularıyla hangi dosyaların alınacağını seç (varsayılan: kaynak dildeki ve dili
   anlaşılamayan dosyalar); satırları tabloya aktar. "0 metin" hatası alırsan eklenti dosyayı tanımıyordur (`detect`) ya da
   yanlış dil seçilidir.
3. **Çevir** (Ollama, DeepL ya da elle). Önce 15-20 satır dene; `⟦n⟧` işaretleri ve satır sonları korundu mu bak
   (`docs/translation.md`).
4. **Kontrol Et:** kontrol kodu, uzunluk, taşma denetimleri; **Fontları Tara** (adım 6'daki sonucu doğrular; yama → `font.md`).
5. **Dışa Aktar:** Atmosphère ya da emülatör yapısı (`docs/export.md`). Yeni, boş bir klasöre yazar.

**Cihazda / emülatörde deneme kullanıcıdan istenir** (`docs/test-emulator.md`): önce yalnızca ana menü etiketlerini
çevirip küçük bir mod üret; açılıyorsa sonra tamamını. Ajan bunu yapamaz ve "çalıştı" diyemez.

### 8. Kayıt ve paylaşım
- `eklentiler/<ad>/NOT.md`: oyun, TitleID/sürüm, dosya yerleşimi, biçim çözümü, bilinen sınırlar, cihazda denenip
  denenmediği.
- Çözülen biçim için `docs/formats/<ad>.md` ve `docs/formats/README.md` satırı; `docs/uyumluluk.md` satırı öner
  (kullanıcı yalnızca kendine saklamak istiyorsa yapma).
- Kullanıcı paylaşmak isterse `katki.md`.

## Karar noktaları
- **Yeni kod gerekli mi?** Gerekmiyorsa gerekmez; öncelik uygulamanın kendisi.
- **Metin resimde mi?** `ara` sonuç vermiyorsa ve ekranda yazı varsa `grafik.md`.
- **Kod nereye?** Her zaman eklenti klasörüne. Çekirdekte benzeri olan ama izinli listede olmayan kodu
  (`nxceviri.core.fontpatch.*` gibi) içe aktarma; eklentiye kendi modülü olarak yaz. Çekirdeğe taşımayı bakımcı yapar.
- **Yazılabilir mi?** `extract` kolay, `inject` zordur; yine de yazma yolunu dene. "Yalnızca okuma" ancak deneme
  kanıtla başarısız olduysa (komut çıktısı, hangi alanın çözülemediği) kabul edilir ve raporda gerekçesiyle yazılır.
  Yarım yazma çözümü gönderme; okunan metin ve font/resim işi yine teslim edilir.
- **Bir parça imkânsızsa** (şifreli/açılamayan arşiv, bilinmeyen sıkıştırma): kanıtı (komut çıktısı) raporla, o
  parçayı kapsam tablosunda "kapsanmadı: neden" diye işaretle, kalan işi bitir. İşin tamamından vazgeçme.
- **Türkçe harf:** `arac font` sonucu (a/b/c) belirlenmeden bitmez. Önce yama (yerleşik, yoksa eklentide);
  `unsupported_letters` yalnızca yamanın kanıtla imkânsız olduğu harfleri içerir. Kararı ve gerekçesini kısaca söyle.
- **Dil:** kullanıcı başka dil demedikçe yalnızca İngilizce.

## Bitti ölçütü
1. `dogrula` tüm ilgili dosyalarda **geçti** ve `İçe aktarma:` bulgusu yok (çıktıyı göster);
   `python -m nxceviri.arac eklentiler` eklentiyi `[TAMAM]` gösteriyor, altında `İçe aktarma:` satırı yok.
2. `git status --porcelain nxceviri/` **boş**: ana koda tek dosya yazılmadı; bütün kod tek eklenti klasöründe.
3. Kapsam tablosu: teşhis raporundaki her metin adayı dosya kapsandı ya da kapsanmama nedeni yazıldı. Yalnızca
   İngilizce aktarıldı (kullanıcı başka dil istemediyse).
4. Eklenti testleri (`tests/`) elle üretilmiş örnekle yeşil; tam proje testi yeşil, `ruff` ve `mypy` temiz.
5. Uygulamada Tara → tabloda doğru sayıda ve okunaklı satır → Dışa Aktar mod klasörü yazıldı.
6. **Font:** `arac font` çıktısı (sonuç a/b/c) gösterildi; Türkçe harfi eksik her font ailesi yamalandı (yerleşik ya
   da eklentideki yama, yazılan font yeniden okunup doğrulandı) ya da yamanın imkânsızlığı kanıtla yazıldı ve yalnızca
   o harfler `unsupported_letters`'ta.
7. **Resim:** yazılı resimlerin sayısı ve örnek adları kullanıcıya bildirildi; kullanıcı istediyse `orijinal/` ve
   `turkce/` düzeni kuruldu, `turkce/`deki resimler moda yerleşti.
8. `NOT.md` yazıldı (font sonucu, kapsam tablosu dahil). Cihazda deneme yapılmadıysa raporda "cihazda denenmedi" yazar.

## Kullanıcıya rapor
Kısa Türkçe: oyun ve motor, eklenti klasörünün yolu (ve `nxceviri/` altında değişiklik olmadığı), kaç dosyadan kaç
satır çıktı, kapsam tablosu (kapsanmayan dosyalar ve nedenleri), `dogrula` sonucu (geçti/kaldı sayıları, içe aktarma
bulgusu yok), imkânsız kalan parça varsa kanıtı (komut çıktısı), Türkçe harf durumu (`arac font` sonucu a/b/c, hangi
fontlar yamalandı, dönüştürmeye kalan harfler ve gerekçesi), yazılı resim sayısı ve örnek adlar (`turkce/` klasörü
kuruldu mu), kullanıcının yapacağı sıradaki adım (modu cihazda denemek). Test etmediğini "test edildi" yazma.
