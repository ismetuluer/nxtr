# Devil May Cry (Switch) — metin biçimleri

Durum: okuma (0.20.0) ve **yazma (0.22.0, `fsd` ve `.msg`)**. Yazma 2026-10-23'te Switch'te doğrulandı: açılış sahnesi
ve sistem mesajları Türkçe göründü. Çözümleme Switch sürümü v0 (TitleID 0100E8000D5B8000)
ve topluluğun Rusça modu üzerinde yapıldı.

## Dosya yerleşimi

RomFS'te `data/dmc1/` altında 1.512 ayrı dosya vardır. Dile bağlı klasörlerin son eki dili gösterir:
(eksiz) = Japonca, `_e` İngilizce, `_f` Fransızca, `_g` Almanca, `_i` İtalyanca, `_s` İspanyolca,
`_c` ve `_z` Çince. Metin taşıyanlar:

| Yer | İçerik |
|---|---|
| `etc_e/common.msg` | 21 kısa sistem mesajı |
| `atm_e/*.atm` | başarım ve galeri metinleri |
| `status_e/st_init.dat` | 107 dizgi (eşya/durum adları) |
| `fsd/r*.fsd` | görev diyalogları ve altyazılar; her dosyada **dil başına bir tablo** |
| `pack_e/*.pack`, `etc_e/*.t32`, `*.tm2` | menü resimleri ve yazı dokuları (metin değil, resim) |

## Mesaj tablosu

`u32 adet | adet × (u32 ofset, u32 uzunluk) | dizgiler`. Ofsetler tablo başına göredir; ilk ofset
`4 + 8·adet` değerinin 16'ya yukarı yuvarlanmışıdır, dizgiler ardışıktır. `.msg` dosyalarında her
dizgi 16 bayta doldurulur; `.fsd` içinde doldurma yoktur. Tablo `.fsd` içinde 16 bayta hizalı bir
yerde, iç içe geçmiş bölümler arasında durur (`r002.fsd` içinde 0x59ea90).

Bir `.fsd` dosyasında aynı dizgi sayısına sahip **ardışık 8 tablo** bir dil kümesidir
(Japonca, İngilizce, Fransızca, Almanca, İtalyanca, İspanyolca, Çince…). Gerçek taramada 36 dosyada
8'li, 28'inde 6'lı küme bulundu; İngilizce kümedeki 2. tablodur.

## Karakter kodlaması

Tek baytlık oyun tablosu (ASCII değil):

- `0x0E`–`0x27` = A–Z, `0x28`–`0x41` = a–z (örn. "You" = `26 36 3c`)
- `0x43` = `.`, `0x4B` = `?`, `0x0D` = `'`, `0x44` = `!`; rakamlar ve diğer işaretler tam doğrulanmadı
- `0x62`, `0x72` gibi değerler aksanlı harflerdir (Fransızca/Almanca/İspanyolca tablolarda)
- Japonca tablo iki baytlıdır (`0x77`… önekli)
- `0x7E xx` kontrol kodudur: `7E 05` boşluk, `7E 0C` satır sonu, `7E 0E ..` konuşma süresi/bitiş,
  `7E 09`, `7E 0A`, `7E 10` vb. yazı stili ve renk; parametre uzunlukları kod türüne göre değişir

## Okuma eklentisi (0.20.0)

`nxceviri/core/formats/dmc1/`. Sonuçlar (Switch v0): 410 satır (`etc_e/common.msg` + 74 `fsd` dosyası). Kurallar:

- Anahtar: `fsd` için `<tablo konumu (hex)>/<dizgi no>`, `.msg` için dizgi no.
- Metin: harfler `0x0E`/`0x28`'den, rakamlar `0x00`–`0x09`, noktalama `0x43 .`, `0x44 ,`, `0x45 :`, `0x4A !`,
  `0x4B ?`, `0x0D '`, `0x4F -`. Kontrol kodu parametreleri: `08`→3, `09`/`0A`/`0B`→1, `0D`/`0E`→2 bayt.
- Dizgi `7E 0E p p` + sıfır dolgusuyla biter; bu kuyruk korunur, çevirmene gösterilmez.
- `fsd` içindeki tablolardan İngilizce olanı içeriğe bakarak seçilir (sık İngilizce sözcük oranı ≥ %50,
  tanınmayan bayt oranı ≤ %10). Yalnızca kod/rakam doldurmalı satırlar atlanır.

## `.fsd` kapsayıcısı ve yazma (0.22.0)

`u32 adet (35) | 4 bayt dolgu | 35 × u64 mutlak ofset | bölümler`. Bölümler dosyada ardışıktır; boyut sonraki ofsetten
bulunur. **İngilizce tablo, 73 dosyanın hepsinde dizindeki 23. bölümdür** (diğerleri başka diller veya model/ses verisi);
bu yüzden İngilizce tablo içeriğe bakılmadan bulunur ve çevrilince de bulunmaya devam eder.

Yazma: 23. bölüm yeni mesaj tablosuyla değiştirilir (dizgiler 4 bayta, `.msg`'de 16 bayta tamamlanır; değişmeyen
dizgiler özgün baytlarıyla kalır), sonraki bölümler kaydırılır ve dizin güncellenir. Bölümlerin içinde mutlak ofset yoktur
(Rusça mod aynı yolla çalışıyor: `r002.fsd`'de yalnızca 23. ve son bölüm farklı). Bölüm sonundaki artık bayt (Japonca
tablodan kalan parçalar, 143–858 bayt) yazarken atılır. Değişiklik yapmadan yazmak dosyayı bayt bayt aynı bırakır
(75 dosyada doğrulandı).

Harfler: oyun fontunda **ç** (`0x61`), **ü** (`0x6C`), **Ü** (`0x5E`), **Ö** (`0x78`), **ö** (`0x72 0x7A`) var; **ğ Ğ ş Ş ı İ Ç**
yok. Dışa aktarırken bu harfler otomatik dönüştürülür (ğ→g, ş→s, ı→i, İ→I, Ç→C, `fold_unsupported_letters`).

## Çözülmemiş ve gerekli olanlar

1. **Tam karakter tablosu** (rakam, noktalama, kontrol kodu parametre uzunlukları).
2. **ğ Ğ ş Ş ı İ Ç:** oyun yazıyı doku resminden çizer (`msg_tex*.t32`, `moji8.tm2`); bu harfler için dokuya glif ve kod
   eşlemesi gerekir (Rusça mod dokuları ve kodlamayı değiştiriyor). Şimdilik dönüştürülüyor.
3. **Yazma:** Türkçe metin İngilizceden uzundur; `.fsd` bölümleri bir dizinle (başta `u64` ofset dizisi)
   bağlıdır, tablo büyürse sonraki bölümlerin ofsetleri kaydırılmalıdır. Dil tablosunun nasıl seçildiği
   (dizinle mi, komut dizisiyle mi) bilinmiyor.
4. Rusça mod ayrıca `fsd`'nin 80 dosyasını yeniden düzenliyor (boyutlar değişiyor), yani yeniden boyutlandırma
   mümkün; başka bir şey (komut dizisindeki ofsetler) kaymıyor olabilir ama doğrulanmadı.

# DMC2 ve DMC3

Metinler `data/dmc2/dmc2-0.nbz` ve `data/dmc3/dmc3-0.nbz` arşivlerinde (DMC3'te güncelleme `dmc3-1.nbz`
ile değiştiriyor). `.nbz` biçimi çözülmedi. Rusça DMC3 modu ayrıca `exefs/main` (çalıştırılabilir dosya) yamalıyor;
kodlama veya yazı tipi yürütülebilir dosyada olabilir.

# PC (HD Collection) topluluk Türkçe yaması ve yazı dokusu (0.23.0)

`games/Devil May Cry/DMC_HD_Turkce_Yama` (Steam sürümü için, Salih Yılmaz): DMC1 + DMC2 + DMC3 + launcher.
Betikler yalnızca okundu, çalıştırılmadı; `dinput8.dll` (DLL enjeksiyonu) kullanılmaz.

**Önemli:** `.nbz` dosyaları düz **ZIP** arşividir (yama betiği `ZipFile` ile açıyor). Switch'in `dmc1-0.nbz`/`dmc2-0.nbz`
dosyaları da aynıdır (`dmc2-0.nbz`: 3.882 girdi).

## DMC1 uyumu (doğrulandı)
- `fsd_tr.yama` (`D1FS`): 80 `.fsd` için yerinde bayt yamaları. Yama bloklarının içindeki 80 Türkçe mesaj tablosunun
  hepsi, Switch `.fsd` dosyalarındaki İngilizce tabloyla aynı dizgi sayısına sahiptir; 65'inin konumu birebir aynı,
  15'i birkaç yüz bayt kaymıştır (PC dosyası biraz farklı). Bu yüzden eşleşme konuma göre değil **dosya adı + dizgi sırasıyla** kurulur.
- Aktarma: `nxceviri/core/formats/dmc1/yama.py` + `translate/port.py` (Hazır Çeviriyi İçe Aktar, klasörde `fsd_tr.yama` varsa).
  Gerçek veride 491/491 satır eşleşti, kod uyuşmazlığı yok.
- `Etc_e/common.msg` (21 mesaj) aynı yolla alınır. `status_e/st_init.dat` (eşya/durum adları) bu sürümde okunmuyor.

## Türkçe harf kodlaması (PC yamasından)
Tüm Türkçe harfler iki baytlıdır: `0x72` + yazı dokusundaki hücre kodu — `ç 61`, `Ç 53`, `ü 6C`, `Ü 5E`, `ö 7A`, `Ö 78`,
`ğ 73`, `Ğ 60`, `ı 74`, `İ 6F`, `ş 75`, `Ş 70`; `;` da çifttir (`72 46`). Özgün Switch fontunda ç Ç ü Ü ö Ö glifi hazırdır;
ğ Ğ ı İ ş Ş hücreleri başka harflere (á í ú Ñ Ú …) aittir, glif eklenmeden kullanılamaz. Proje bu çifti yazar
(`codec.PAIR_CHARS`). Önceki sürümün tek baytlık deneme kodları (0x62–0x69) kaldırıldı.

## Yazı dokusu (düzeltildi)
`msg_tex.t32` = 0xC0 baytlık T32 başlığı + **iki sıkıştırılmamış DDS sayfası** (her biri `DDS ` + 124 bayt başlık + 256×256
piksel, B G R A). 1. sayfa yazı tipidir: **16×32 hücre**, kod → (sütun `c%16`, satır `c//16`), kayma yok; taban çizgisi y=27.
2. sayfada birkaç simge vardır (µ ¡ · ¿ ° ` § ´ ® → hücre 0–8). Switch'in kendi `etc_u/msg_tex.t32` dosyası aynı geometrinin
BC7 hâlidir. Rusça modun ve PC yamasının dosyaları, dil klasörüne (`etc_e`) konduğunda Switch'te açılıyor (cihazda doğrulandı).
Başlıktaki 0x14 alanı (`F0 96 E3 4F`) içerik özeti değil, dokunun sabit kimliğidir.

Hatalı önceki varsayımlar (bu bölümün eski sürümü): dosyayı ham 512×256 RGBA sanmak ("+2 hücre kayması" aslında 0x80 baytlık
DDS başlığının görüntüyü 32 piksel kaydırmasıydı). DDS başlığı olmayan veya boş hücreli bir doku oyunu açılışta çökertti
("Hata oluştu, kapatılıyor"; cihazda iki kez). Oyun 0x47 dışındaki tüm hücreleri ölçüyor olabilir; üretilen doku hepsini doldurur.

## DMC2 / DMC3 (ön değerlendirme, doğrulanmadı)
- DMC2: PC yamasındaki 87 dosyanın hepsi Switch `dmc2-0.nbz` içinde aynı adla var; 73'ü (`edm_*_e.bin`, altyazı görüntüleri) aynı
  boyutta, 14'ü (`msg_*.nb`, metin) farklı boyutta (Türkçe metin). Switch'te `dmc2-1.nbz` bindirmesi yok; uygulamak için ya 768 MB'lık
  `dmc2-0.nbz` yeniden yazılmalı ya da oyunun başka bir yüklemesi aranmalı.
- DMC3: yama 347 dosyalık bir bindirme (`GData.afs/id*.pac` görüntüleri, menü görselleri); metin görüntü içinde olduğundan çeviri değil
  görüntü yamasıdır. İncelenmedi.

## Cihaz doğrulaması (2026-10-24)
Mod #8 (PC Türkçe yamasının 566 satırı + üretilen yazı dokusu) Switch'te açıldı: ara sahne altyazıları, diyaloglar,
pause menüsü açıklamaları ve eşya metinleri Türkçe; ğ ş ı İ ç ö ü doğru, harf aralığı uygun (`_SQUEEZE = 0.72`).
Hâlâ İngilizce: menü başlıkları ve Option ekranı (resim/doku), gizlilik ve başarım ekranları (`atm_e/*.atm`).

## Menü başlığı dokuları (`status_e/st_init.dat`, bölüm 2–4)
Durum menüsünün başlıkları resimdir. Bölüm 1–4 T32 dokularıdır; Switch'te başlık 0x160 bayt, sayfalar DX10 DDS
(BC7_UNORM, 1 bayt/piksel; bölüm 4'ün 2. sayfası sıkıştırılmamış BGRA). Sayfa 1 normal, sayfa 2 seçili (altın) hâldir.
Doku kimliği (0x14): `AECBB6FE` Weapon/New/Total Exp/Action/Map/Item, `3729D0FF` File/Exit, `F6A70F3F` harita ekranı
(Floor Select mode / Move MAP mode / Roll MAP). PC Türkçe yamasında bu dokular İngilizcedir (yalnızca sıkıştırılmamış
biçime çevrilmiş). `fontpatch/dmc1_menu.py` sözcüğü siler, Türkçesini aynı boy ve taban çizgisinde özgün renk ve
parıltıyla çizer, dokuyu PC biçiminde yazar (başlık 0xC0, 0x3C = bir sayfanın boyu, sayfa başına BGRA DDS). Oyun
toplamsal karıştırma kullanır (alfa her yerde 255, siyah görünmez). Aynı resimler `status_u/st_init.dat` içinde de var (kimlikler `7C3C275B`, `E5DE415A`, `24509E9A`; o dosyanın metni
Japoncadır ve çevrilmez). Yalnızca `status_e` değiştirildiğinde (Mod #11) başlıklar cihazda İngilizce kaldı; dışa aktarma
artık iki dosyayı da değiştirir (eklentinin `game_file_patches` kancası). Mod #12 ile cihazda doğrulandı (2026-10-24): pause menüsü sekmeleri Türkçe.
Hâlâ resim olarak İngilizce: eşya adları (Vital Star, Yellow Orb …), görev başlık ekranı, "Mission", uyarı ekranı,
Option ekranı, Galeri başlığı.

## `.atm` dosyaları (`atm_e/`)
`achievement_nx.atm` (102 dizgi: 34 başarım adı + 34 açıklama + adların tekrarı), `gallery_nx.atm` (188), `gdpr_nx.atm` (3),
`new_common_nx.atm` (8). Tablo yapısı ve harf tablosu `.msg` ile aynıdır; tek fark kontrol kodlarının kaçış baytının **0x80**
olmasıdır (boşluk `80 05`, satır sonu `80 0C`, bitiş `80 0E p p`). Eklenti kaçış baytını dizgilerdeki boşluk/bitiş kodlarını
sayarak seçer; dizgi uzunlukları 4'ün katıdır ve yeniden yazımda bu korunur. Değiştirmeden yazınca dört dosya da bayt bayt aynı.
Türkçe çeviriler `docs/dmc1-ek-ceviriler.json` dosyasındadır (anahtar `dosya|sıra`). Bu ekranlar 0x72 çiftini tanımaz (0x72'yi
"ñ" çizer, Mod #9); Türkçe harfler yalnızca hücre koduyla tek bayt yazılır. Mod #10 ile cihazda doğrulandı.

## Oyun resimlerindeki yazılar (eşya, silah, menü, ayarlar, görev sonu)
Taramada (`status/`, `status_u/`, `etc/`, `etc_e/`, `etc_u/`, `pack_e/`, `pack_cmn/`) ~150 farklı yazılı resim bulundu.
İngilizce dil `status_e` → `status_u` → `status` sırasıyla dosya arar: eşya ve silah adları gibi birçok resim dilden
bağımsız `status/` klasöründedir. Kapsayıcılar çeşitlidir (`.itm`, `.dat`, `.tm2`, `.t32`, `.pack`, `.bnd`); hepsinde
sayfalar sıradan DDS başlıklarıyla durur (BC7 DX10, 32 bit BGRA; birkaçı DXT3/DXT5).

`fontpatch/dmc1_images.py` kapsayıcıları çözmez: dosyadaki DDS başlıklarını bulur, sayfayı çözer, içerik özetiyle
(`page_key`, çözülmüş RGBA'nın SHA-1'i) tanır ve değiştirilen sayfayı **aynı biçimde, yerinde** yazar (BC7'de yalnız
değişen 4×4 bloklar yeniden kodlanır: `fontpatch/bc7.py`, kip 6). Dosya boyu ve diğer baytlar değişmez. Aynı resim
dosyalarda onlarca kez tekrar eder (ör. silah adları `wp_init.itm`, `spdinit.itm`); özet aynı olduğu için hepsi değişir.
Bazı DDS başlıkları sahtedir (başlık alanına düşen artıklar, sayfa verisinin üstüne denk gelen "sayfalar"); özetleri
eşleşmediği için atlanırlar.

İki çizim türü vardır (`fontpatch/labels.py`): toplamsal (alfa ~255, siyah zemin; parıltı renkli) ve saydam (zemin alfa
0; yazı opak, çevresinde yarı saydam gölge). Yazı tipleri: Monotype Corsiva / Times (Windows) ve uygulamayla gelen OFL
lisanslı Kaushan Script (fırça yazısı eşya adları) ile Pirata One (gotik: görev sonu, "mission start").

Mod #13 cihazda çalıştı (2026-10-24). Mod #14'te hizalama düzeltildi: taban çizgisi artık harflerin dip noktalarının
ortancasından bulunur (kuyruklu harfler hizayı bozmaz), listeler sola dayalıdır. Resim üzerindeki yazılar için üçüncü çizim
türü eklendi: zemin çevresinden yayılarak doldurulur, yazı haritası özgün ile doldurulmuş zemin arasındaki farktır;
zor durumlar için etikete renk, eşik ve elle ölçülmüş kutu verilebilir. Bu türle yükleme/kayıt ekranı (LOAD/SAVE, File,
MODE, TIME, SAVES), kayıt yuvaları ve SECRET MISSION çevrildi (Mod #14, cihazda **henüz doğrulanmadı**).

Mod #14 cihazda doğrulandı. Mod #15: paragraflar (resim üzerindeki çok satırlı yazı) için satırlar yatay izdüşümün en
derin vadilerinden ayrılır, paragraf alanı yazısı süzülmüş ve koyulaştırılmış bir panelle kapatılır, satırlar aynı boyda
çizilir. Bu yolla kolay mod tanıtımı, zorluk ekranları ("Sırada ZOR mod."), Tekrar Dene, Yükleniyor ve sonuç ekranı
(GENEL SONUÇ …) çevrildi (cihazda **henüz doğrulanmadı**).

Çevrilenler: eşya adları ve eşya kartları, "Devil Arms"/"Guns", dosya
ekranındaki "Mission"/"Enemy", görev sonu (Ranking Bonus, Clear Time, Orbs, Perfect, next mission, SAVE), "mission
start / power up", sonuç ekranı zorluk adları, başlık menüsü (NEW GAME …, Character Change …), EXTRAS/ACHIEVEMENTS/
CREDITS/GALLERY, PRIVACY POLICY, Ayarlar ekranı. Özel adlar (silah, düşman adları, "Dante Must Die", "Super Dante",
"Stylish" dereceleri) PC Türkçe yamasındaki gibi İngilizce kalır.

Henüz yapılmayanlar: resim üzerindeki yazılar (kontrol şemaları `ctrl_*_nx.pack`/`*type*.t32`, hareket açıklamaları
`status_u/act_img.itm`, düşman adları `status_u/file_img.itm`, görev ekranları `status_u/mssn_img.itm`, haritalar,
"You are Dead", "To Be Continued", "Try Again", sonuç ekranı `result.itm`, Galeri/Başarım başlıkları), DXT3/DXT5
sayfalar (`etc/select.t32` "SELECT DIFFICULTY", `etc/finish00.t32` "You Are The King of Hell.") ve görev girişi
animasyonları (`mssn_ips_*.ip2`, kare başına bir resim).

## Program kodundaki metinler: düşman dosyası açıklamaları
Dosya → Düşman ekranındaki açıklamalar RomFS'te yoktur; oyun kodunda (ExeFS `main`, `ro` bölümü) oyunun harf
kodlamasıyla, dil dil art arda durur (Japonca, İngilizce 147 metin, Fransızca, Almanca, İtalyanca, İspanyolca), her biri
`7E 0E 00 00` ile biter. v0 (yapı kimliği 883F54C67475ABAE9611355F210059F8): `ro` dosyada 0x57F700, bellekte 0x580000;
İngilizce bölge 0x70D9E3–0x714786 (28.067 bayt). Oyun bunlara bir işaretçi dizisiyle (bellekte 0x8AD238'den, 1346 giriş)
ulaşır; dizinin değerleri `.rela.dyn` R_AARCH64_RELATIVE kayıtlarının addend alanlarından gelir.

`formats/dmc1/exe.py` Türkçe metinleri İngilizce bölgeye art arda yazar ve kayıtların addend'lerini yeni adreslere
çevirir (tek tek değil, toplamda sığması yeterli). Çıktı bir IPS32 yamasıdır: Atmosphère'de
`atmosphere/exefs_patches/<mod>/<build id>.ips`, emülatörde `<TitleID>/<mod>/exefs/<build id>.ips`. Türkçe metinler
`nxceviri/assets/dmc1/dusman_aciklamalari.json` dosyasındadır; özgün İngilizce metin depoda tutulmaz, yalnızca SHA-256 özeti (satır sonu ve satır sonu boşlukları atılarak) saklanır ve koddakiyle özetler eşleşmezse yama
üretilmez (başka sürüm). PC Türkçe yaması bu metinleri çevirmemişti. Cihazda **henüz doğrulanmadı** (Mod #17).

Not: sahne dosyalarında (`fsd`) 23. bölüm dışında da İngilizce metin bulunabiliyor (ör. r11b 26. bölüm); oyunun bunları
kullanıp kullanmadığı doğrulanmadı.

## Kayıt mesajları, kombo dereceleri, harita adları, açılış uyarısı (Mod #18)
- `etc_u/memicon.dat`: u32 dizinli; 3. bölüm 32 dizgilik mesaj tablosu (PS2 hafıza kartı metinleri, "Will you save
  here?" …). Eklenti u32 dizinli dosyada mesaj tablosu olan ilk bölümü kullanır. Türkçeleri `docs/dmc1-ek-ceviriler.json`.
- Kombo dereceleri (`status/cockpit.t32`): büyük baş harf derecedir (S/A/B/C/D) ve korunur, yalnızca kuyruğu değişir:
  Durgun, Cesur!, Amansız!; "Bravo!" ve "Stylish!" aynı kalır.
- Harita adları (`status_u/st1_map.dat` ve st2–st4 aynı sayfayı paylaşır): Yeraltı, Bilinmeyen, Bahçe, Şato, Gemi.
- "You are Dead" / "To Be Continued" (`etc/dead.tm2`, `etc/tobe.tm2`): Öldün / Devam Edecek.
- Açılış uyarısı `video/title.mp4` ve `titlep.mp4`'ün ilk ~3,6 saniyesindedir (yazı siyah zemine eklenmiş, ateş girerken
  söner). Yazı maskesi en parlak karelerden çıkarılır, her karede maske normalize bulanıklıkla çevreden doldurulur, Türkçe
  uyarı özgünün o karedeki görünürlüğüyle çizilir; video yeniden kodlanır (ffmpeg, x264 crf 16), ses kopyalanır. Bu adım
  şimdilik uygulamanın dışında yapıldı (bkz. TECH_DEBT). Duraklatma menüsü (PAUSE/SAVE/RESET), "NO DATA" ve YES/NO
  dokuları RomFS'te bulunamadı.

## Kullanıcının hazırladığı grafikler ve animasyonlar (Mod #19)
Zor sayfalar (kontrol şemaları, hareket açıklamaları, görev kartları, zorluk ve sonuç ekranları) resim olarak
`games/Devil May Cry/grafik_temizleme/orijinal` klasörüne çıkarılır; kullanıcı yazıyı silip Türkçeyi çizerek aynı adla
`temiz` klasörüne koyar. `fontpatch/dmc1_graphics.py` değişmiş çiftleri okur (`NXCEVIRI_DMC1_GRAFIK` ortam değişkeni
klasörü gösterir), özgün sayfanın içerik özetiyle oyundaki her kopyasını bulur (`dizin.json`: 22 dosya) ve hazır sayfayı
yerinde yazar; hazır sayfa varsa etiket çizimi yerine geçer. Yazılan sayfalar BC7 kayıplı kodlandığı için sonuç hazır
resme ~29–42 dB yakındır (özgüne 15–28 dB).

Görev girişi animasyonları (`status_u/mssn_ips_NN.ip2`, 60 kare DXT1): kullanıcı yalnızca `*_son_kare.png` dosyasını
Türkçeleştirir; `fontpatch/dmc1_animation.py` ara kareleri türetir: son karede özgün ile Türkçe arasında farklı
bölgeler parçalara ayrılır, her parçanın belirme eğrisi özgün karelerin parlaklığından ölçülür, kare başına özgün
yazı çevreden doldurulur ve Türkçe son karenin bu oranda karışımı konur. Dalgalanma efekti yoktur. 38 animasyon, 21 sn/adet.
"Mission Clear" animasyonları (`mssn_ips_00–15, 42`) ve çözülemeyen sayfalar bu sürümde yapılmadı.
Cihazda **henüz doğrulanmadı** (Mod #19).
