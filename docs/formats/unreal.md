# Unreal Engine — .locres ve .pak

Kod: `nxceviri/core/formats/unreal/locres.py`, `nxceviri/core/archives/pak.py`,
`nxceviri/core/archives/access.py`. Test verisi: `tests/unrealbuild.py`.

> Bu biçimler **gerçek bir Unreal oyunuyla denenmedi** (geliştirme makinesinde Unreal oyunu yok).
> Uygulama, biçimlerin bilinen yapısına göre ve elle üretilmiş dosyalarla test edildi.

## .locres

| Sürüm | Ad | Fark |
|---|---|---|
| 0 | Legacy | Sihirli GUID yok; metinler anahtarın hemen arkasında |
| 1 | Compact | GUID + sürüm + metin dizisi ofseti; anahtarlar metin indeksi tutar |
| 2 | Optimized_CRC32 | + toplam girdi sayısı, ad alanı/anahtar özetleri, metin referans sayıları |
| 3 | Optimized_CityHash64_UTF16 | 2 ile aynı yapı, farklı özet algoritması |

GUID: `0E147475 674A03FC 4A15909D C3377F1B`. FString: `i32 uzunluk` (sonlandırıcı dahil),
pozitif = ANSI, negatif = UTF-16LE. Unreal, yalnızca 0x7F altı karakterlerden oluşan metni ANSI
yazar; Türkçe karakter içeren metin UTF-16 olur.

**Kaynak özeti (source string hash):** girdinin kaynak metninin özetidir; oyun çeviriyi kullanırken
bunu doğrular. Değiştirilmez. Kaynak dil (ör. `en`) dosyasının metinleri Türkçeyle değiştirildiğinde
özet hâlâ kaynak metne ait olduğu için çeviri gösterilir.

**Geri yazma:** ad alanları, anahtarlar ve özetler aynı kalır. Değişmeyen metinlerin ham baytları
korunur; yeni metin dizinin sonuna eklenir; paylaşılan bir metin yalnızca çevrilen girdi için ayrılır.
Referans sayıları yeniden hesaplanır.

**Kontrol kodları:** `{PlayerName}`, `{0}` (iç içe süslü parantez dahil), UMG zengin metin
etiketleri `<Bold>`, `</>`, `<img id="X"/>`. Adlı/numaralı argüman ve `<img …/>` serbesttir (yer değiştirebilir);
`<X>` … `</>` bir aç/kapa çiftidir (bütün olarak taşınabilir; `</>` en yakın açık etiketi kapatır).

**Argüman ekleri:** yalın çoğul ifadesi `{Count}|plural(one=cat,other=cats)` (tırnaksız, boşluksuz, boş olmayan
değerler) üç tür koda ayrılır: baş `{Count}|plural(one=` (açılış), ayraç `,other=` (çiftin içinde kalır), son `)`
(kapanış). Seçenek sözcükleri (`cat`, `cats`) çevrilir; ifade bütün olarak taşınabilir. Yazarken metin yeniden okunur:
seçeneğe boşluk, virgül, parantez, eşittir, tırnak ya da süslü parantez yazılmışsa ya da seçenek boşsa satır
yazılmaz. Başka biçimler (tırnaklı ya da boş değerli çoğul, `|gender(…)` gibi başka ekler) çözülmez: değişken ile ekin
başı (`{G}|gender(`) tek, katı kod olur, ekin geri kalanı düz metin kalır (çevirmen dokunmamalı). Bu ekler gerçek bir
oyunda görülmedi; yalnızca elle üretilmiş örneklerle denendi.

## .pak

Dosya sonundaki FPakInfo; dizin eski (v1–v9) veya yeni (v10–v11: kodlanmış girdiler + tam klasör
dizini) biçimde okunur. Sıkıştırma: Zlib, Gzip. **Desteklenmeyen:** şifreli dizin/girdiler (oyuna
özgü AES anahtarı gerekir), Oodle sıkıştırma, IoStore (.utoc/.ucas) içindeki varlıklar.
UE5 IoStore oyunlarında da `.locres` dosyaları genellikle `.pak` içinde durur.

Tarama yalnızca pak dizinini okur ve metin adayı girdileri (`.locres` vb.) listeler.

## Dışa aktarma: yama pak'ı

Orijinal pak (genellikle GB'larca) yeniden yazılmaz. Değişen `.locres` dosyaları, aynı bağlama
noktasıyla, orijinalin yanına `<ad>_NXCeviri_P.pak` olarak konur. Unreal `_P` ile biten pak'ları
daha yüksek öncelikle bağlar; aynı yoldaki dosya yamadakiyle değişir. Yama pak'ı eski dizin biçiminde
(en çok v7), sıkıştırmasız ve şifresizdir; motorlar eski sürümleri okuyabilir.

**Riskler:** oyun pak'ları imzalıysa (`.sig` dosyası) imzasız yama yok sayılabilir (uygulama uyarır);
bazı motor sürümlerinin eski pak sürümünü kabul edip etmediği gerçek oyunda doğrulanmalıdır.
