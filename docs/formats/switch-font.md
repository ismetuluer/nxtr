# Switch sistem fontu (`.bfttf` / `.bfotf`)

Kod: `core/fontpatch/switchfont.py` (kapsayıcı, yama), `core/qa/fonts.py` (tarama), `core/export/layeredfs.py`
(`_patch_switch_font`). Karar: `ARCHITECTURE.md` 233.

## Yerleşim

Oyunlar bu fontları çoğunlukla `mesg/Font/<ad>.bfttf.zs` (TrueType) ya da `.bfotf.zs` (CFF/OpenType) olarak taşır;
bir arşivin (SARC) üyesi de olabilirler. Katmanlar dıştan içe:

1. **zstd** çerçevesi (`.zs`). Tarayıcı açılmış hâli ayrıca `X.bfttf.zs>X.bfttf` iç dosyası olarak gösterir.
2. **8 baytlık başlık:** `d9 9b 87 1a` + 4 bayt. Son dört baytın anlamı çözülmedi; **aynen korunur**.
3. **sfnt** (TTF/OTF) verisi, 4 baytlık anahtarla tekrarlı **XOR** uygulanmış.

Anahtar dosyadan dosyaya değişir ve tahmin edilmez: verinin ilk 4 baytı bilinen sfnt sihirleriyle (`00 01 00 00`,
`OTTO`, `true`, `ttcf`) XOR'lanarak aday anahtar bulunur; aday sfnt olarak açılıp Unicode cmap'i okunabiliyorsa doğru
kabul edilir.

## Tarama

Her font bir kez listelenir: kanonik yol, adı font olan en dıştaki parçadır (`mesg/Font/X.bfttf.zs`; arşivde
`paket.sarc>Font/X.bfttf.zs`), çünkü mod o dosyanın yerine konur. Tür "Switch sistem fontu"; karakterler, yamayla
eklenebilecek harfler ve genişlikler açılmış sfnt'den okunur.

Switch oyunlarının Latin metin fontları Japonca glif de taşır. Bu yüzden font, CJK karakter sayısına bakılarak değil şu
kuralla dile özgü sayılır: adı bir dili gösteriyorsa (`japanese`, `zh`, `ko`…) ya da CJK yoğun olup Avrupa dillerinin
aksanlı harflerinin (é, ö, ç…) çoğunu (%75'ten azını) taşıyorsa. Çince fontlar pinyin için ü, é, à gibi birkaç
aksanlı harf taşır; bu yüzden ölçüt "hiç yok" değil "çoğu yok"tur. Dile özgü font
yamalanmaz ve genişlik ölçümünde kullanılmaz.

## Yama ve yazım

`ttf.patch_font(..., allow_cjk=True)` eksik `ı İ ş Ş ğ Ğ` harflerini fontun kendi `i I s S g G` harflerinden ve ortak
kaynak sırasıyla bulunan nokta, çengel ve kavisten türetir (`tmp-font.md` "Vektör fontlar", karar 234); `ç ö ü Ç Ö Ü` türetilmez. Yamalı sfnt aynı anahtarla
XOR'lanır, aynı başlığın arkasına konur ve özgün dosya sıkıştırılmışsa zstd ile (düzey 19) sıkıştırılır. Sonuç yeniden
açılır; eklenen her harf cmap'te değilse yama hata verir ve dosya moda yazılmaz. Hiçbir harf eklenemezse özgün baytlar
kalır, dosya moda yazılmaz.

Korunan: başlığın 8 baytı, XOR anahtarı, sıkıştırılmış/sıkıştırılmamış hâl, var olan glifler ve numaraları (yeni
glifler sona eklenir). Değişen: zstd çerçevesinin baytları (yeniden sıkıştırma), `hdmx`/`LTSH`/`VDMX`/`DSIG` tabloları
silinir.

## Sınırlar

- SARC, Yaz0 ve zstd dışındaki arşivlerin (pak, NNI, eklenti arşivi) içindeki Switch fontları yamalanmaz; dışa
  aktarma uyarı verir.
- Fontu dışarıda düzenleyip içe alma (Kontrol Et → Fontu Dışa Aktar / İçe Al) bu türde yok.
- BFFNT (bitmap Nintendo fontu) ayrı bir biçimdir ve desteklenmez (`TECH_DEBT.md` 32).
