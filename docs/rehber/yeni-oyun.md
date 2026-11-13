# Yeni oyun — metinlere erişmek ve çeviri tablosuna aktarmak

## Ne zaman okunur
Kullanıcı "şu oyunu çevirmek istiyorum" diyor ya da uygulama taramada "0 metin" / "desteklenmeyen biçim" veriyor.
Önce `AGENTS.md` kurallarını (özellikle anahtar ve oyun dosyası sınırları) hatırla. Kurulum yoksa `baslarken.md`.

Kullanıcıdan gerekenler: oyun dosyalarının yolu (base NSP/NSZ, varsa güncelleme ve DLC), `prod.keys`'in uygulamada
seçili olması. Oyun dosyası aranmaz, indirilmez.

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
  bazen metni kimlikten ayırmaya yarar (Ys Origin'de böyle).
- Aynı cümle birden çok yerde (SRT + TSV + önbellek) → oyunun hangisini okuduğunu bilmeden hepsini yaz (Despelote).

### 3. Motora göre yol
Kısa tarifler; ayrıntı ilgili not dosyasında (`docs/formats/README.md` dizin).

- **Unity** (`Data/StreamingAssets/aa/…` bundle'ları, `resources.assets`, `*.assets`): önce hazır eklenti dener
  (Unity Localization string tabloları, I2 Localization, düz `TextAsset`, `Locoliser`, DKCR `Localization`).
  Metin tip ağacı olmayan dosyadaysa UnityPy alan adlarıyla okuyamaz; nesnenin **ham baytı** çözülür (`unity/i2.py`,
  `dklocal.py`). Kural: yapıyı tahmin etme, tüm nesneyi bitirebildiğin doğrulamalarla kabul et; doğrulanamayan
  nesneyi hiç okuma. "Unity oyunu, ama 0 satır" ise metin Unity dosyalarında olmayabilir (Danganronpa: WAD içinde).
  Notlar: `unity.md`, `dkcr.md`, `danganronpa.md`.
- **Unreal:** metin `.locres` dosyalarındadır, çoğu zaman `.pak` içinde. Eklenti ikisini de okur
  (`unreal.md`). Gerçek oyunla denenmedi; Oodle sıkıştırmalı pak'lar açılmaz.
- **Nintendo LMS (MSBT) / SARC / Yaz0 / ZSTD:** hazır; kapsayıcı SARC/Yaz0/ZSTD içinde iç içe açılır
  (`msbt.md`, `archives.md`).
- **Bilinmeyen ikili biçim:** şu sırayla ilerle ve her adımı bir not dosyasına yaz (`NOT.md`):
  1. **İmza:** dosya başındaki 4-8 bayt (`MsgStdBn`, `AGAR`, `YCD\0`, `mdf\0`, `NNI\0`). Yüksek ihtimalle biçim
     adını verir; yoksa uzantı ve klasör adına bak.
  2. **Tablo / ofset yapısı:** metin sayısı, ardından ofset dizisi, ardından havuz mu? `ara` çıktısındaki ofsetlerden
     metinler arasındaki mesafeyi ve çevrelerindeki u16/u32 sayıları incele (uzunluk, ofset). Ofset dizisini
     metinlerin gerçek yerleriyle eşleştirebiliyorsan yapıyı çözdün.
  3. **Kodlama:** UTF-8 / UTF-16 / Shift-JIS yetmezse özel bir harf tablosu olabilir (Devil May Cry'da oyunun kendi
     hücre kodları var; `dmc1.md` "Karakter kodlaması").
  4. **Kontrol kodları:** metin içinde çıplak bayt dizileri (`0x0E…`, `\n`, `<color:…>`, `%s`, `{0}`). Hangi kodun yer
     ve uzunluk etkisi olduğunu belirle; her biri `⟦n⟧` olacak. Aynı kodun ham baytı geri yazılırken aynen korunur.
  5. **Yazma:** metin uzunluğu değişince hangi alanlar güncellenmeli (uzunluk, ofsetler, hizalama, dosya boyutu,
     kapsayıcı dizini)? Örnekler: Danganronpa LIN'de kod bölümü dizgilere sıra numarasıyla başvurur, bu yüzden
     metin uzunluğu serbesttir (`danganronpa.md`); M2 PSB'de dizge tablosu yerinde yeniden yazılır (`m2.md`);
     Vanillaware FMSB (`unicorn-overlord.md`). Kapsayıcı bir arşivse (NNI, CPK, WAD), arşivi yeniden kuran kod
     `nxceviri/core/archives/` altında zaten var mı bak.

### 4. Eklenti iskeleti ve önce test
```
python -m nxceviri.arac eklenti-olustur <ad>
```
Kullanıcı eklentisi `eklentiler/<ad>/` (kaynak kurulum) ya da `%LOCALAPPDATA%\NXCeviri\eklentiler\` altında bir
klasördür: `eklenti.toml` + `plugin.py` + `tests/` + `NOT.md`. **Önce testi yaz** (`eklenti-yazma.md`): elle üretilmiş
küçük örnek dosya üretici + round-trip testi, başarısız olduğunu gör, sonra `extract` / `inject`'i yaz. Sözleşme ve
tuzaklar `eklenti-yazma.md`'de.

### 5. Gerçek dosyada doğrula
```
python -m nxceviri.arac dogrula <eklenti adı> "<base.nsz>" "<update.nsp>"
```
Çıktı dosya başına geçti/kaldı ve satır sayısını verir. Okuma: (a) değişikliksiz extract→inject **bayt bayt aynı**
mı, (b) işaret metni yazıp yeniden okuyunca aynı mı. Kalan dosya ya da satır sayısı beklenenden çok farklıysa
(ör. ekranda görülen 3000 satır yerine 12) eklenti metnin bir kısmını kaçırıyordur; `ara` sonuçlarıyla karşılaştır.
**`dogrula` geçmeden iş bitmiş sayılmaz.**

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
| (c) Font yamalanamıyor / okunabilen font yok | Harf dönüştürme: eklentide `unsupported_letters` = sonuç satırındaki harfler |

Eklenti yazdıysan harf kancaları `eklenti-yazma.md` "İsteğe bağlı kancalar"da: `unsupported_letters` (dönüştürülecek
harfler), `normalize_text` (oyunun özel harf tablosu), `support_files` (Türkçe harfli yazı dokusu gibi ek dosya). Sonuç
(b) ve (c) cihazda denenmeden "çalışıyor" denmez.

### 7. Uygulamada akış
Uygulamayı aç (`NX Ceviri Studyosu.bat` ya da `python -m nxceviri`):
1. **Oyunu Ekle:** base + update (+ DLC) dosyaları, `prod.keys` seçili.
2. **Metinleri Tara → Taramayı Başlat:** rapor motoru ve desteklenen dosyaları listeler; kaynak dili seç (varsayılan
   İngilizce); satırları tabloya aktar. "0 metin" hatası alırsan eklenti dosyayı tanımıyordur (`detect`) ya da
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
- **Yazılabilir mi?** `extract` kolay, `inject` zordur. Yazamadığın biçimde "yalnızca okuma" olarak dur ve kullanıcıya
  söyle (Mina the Hollower ilk sürümde böyle bitti). Yarım yazma çözümü gönderme.
- **Türkçe harf:** `arac font` sonucu (a/b/c) belirlenmeden bitmez. Yama (b) varsa `unsupported_letters = ""` ve `font.md`;
  yamalanamıyorsa (c) `unsupported_letters` doldurulur. Kararı ve gerekçesini kısaca söyle.

## Bitti ölçütü
1. `dogrula` tüm ilgili dosyalarda **geçti** (çıktıyı göster).
2. Eklenti testleri (`tests/`) elle üretilmiş örnekle yeşil; tam proje testi yeşil, `ruff` ve `mypy` temiz.
3. Uygulamada Tara → tabloda doğru sayıda ve okunaklı satır → Dışa Aktar mod klasörü yazıldı.
4. **Font durumu belirlendi:** `arac font` çıktısı (sonuç a/b/c) gösterildi, eklentideki `unsupported_letters` buna uyuyor.
5. `NOT.md` yazıldı (font sonucu dahil). Cihazda deneme yapılmadıysa raporda "cihazda denenmedi" yazar.

## Kullanıcıya rapor
Kısa Türkçe: oyun ve motor, kaç dosyadan kaç satır çıktı, `dogrula` sonucu (geçti/kaldı sayıları), neyin
çevrilemediği (resim, kod içindeki metin), Türkçe harf durumu (`arac font` sonucu a/b/c ve alınan karar), kullanıcının yapacağı sıradaki adım (modu cihazda
denemek). Test etmediğini "test edildi" yazma.
