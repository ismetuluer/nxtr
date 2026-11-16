# Biçim ve motor uyumluluğu

Geliştirme makinesindeki gerçek oyunlarla tarama → metin aktarma denendi; sonuçlar oyun adı verilmeden motor ve
biçim başına özetlenir. Aynı biçimi kullanan birden çok oyun tek satırdadır; satırda **en zayıf durum** yazılır, farklar
notta belirtilir. Oyun dosyaları depoya konmaz. Biçim ayrıntıları: `docs/formats/README.md`.

Simgeler: ✅ çalışıyor, ⚠️ kısmi, ❌ çözülmedi / desteklenmiyor. "Cihazda denenmedi" ifadesi mod çıktısının gerçek bir
Switch'te ya da emülatörde açılmadığı anlamına gelir.

| Motor / biçim | Okuma | Yazma | Font denetimi / yaması | Notlar |
|---|---|---|---|---|
| Unity Localization (AssetBundle StringTable) | ✅ (1.383–3.466 satır) | ✅ yeniden okunup doğrulanır | ✅ ana fontlara ı İ ş Ş ğ Ğ eklenir | Bazı oyunlarda base seyrek: güncelleme şart (0.9.0); "en-us" ↔ "en" eşleşmesi düzeltildi (0.9.0); Addressables katalog CRC'si dışa aktarmada güncellenir. `docs/formats/unity.md` |
| Unity I2 Localization | ✅ (1.925 satır, İngilizce sütunu) | ✅ (düzen A gerçek oyunla doğrulandı; düzen B gerçek oyunda denenmedi) | ⚠️ tip ağacı silinmiş dosyadaki fontlar okunamaz | Arayüz, eşya ve diyalog metinleri (0.10.0). `docs/formats/unity.md`, `docs/formats/tmp-font.md` |
| Unity düz metin (`TextAsset`: SRT + TSV) ve `Locoliser` önbelleği | ✅ (15.978 satır, İngilizce) | ✅ Türkçe, İngilizce yuvasına yazılır; cihazda Türkçe metin doğrulandı (0.26.0; ürün sahibi, 2026-11) | ✅ gömülü fontlara ı İ ş Ş ğ Ğ eklenir; cihazda denenmedi (TECH_DEBT 65) | Oyun metni `Locoliser` önbelleğinden okur (0.27.0). `docs/formats/unity.md` |
| Unity `Localization` nesnesi (`[SerializeReference]` kayıt defteri) | ✅ | ✅ cihazda doğrulandı (ürün sahibi, 2026-11) | ⚠️ tip ağacı olmayan dosyadaki font okunamaz; ğ ş ı İ denetlenemez | Tek nesnede tüm metin; çıkarma yaklaşık 3 dakika sürer. `docs/formats/unity-serializereference.md` |
| Unity dışı metin: AGAR/WAD arşivi, `.lin` betikleri, `.pak` tabloları | ✅ | ✅ arşiv yeniden kurulur ve doğrulanır; cihazda doğrulandı (ürün sahibi, 2026-11) | ⚠️ glif denetlenmedi, font yaması yok (harf dönüştürme) | Resim olarak gelen yazılar çevrilemez; aynı biçimin diğer oyunlarda geçerliliği denenmedi. `docs/formats/wad-lin.md` |
| Unreal `.locres` (`.pak`) | ⚠️ yalnızca birkaç motor metni (2 satır) | ✅ cihazda doğrulandı (ürün sahibi, 2026-11) | belgelenmedi | Oyun metinleri Oodle sıkıştırmalı (desteklenmiyor, TECH_DEBT 37). `docs/formats/unreal.md` |
| MSBT (LMS) | ✅ (6.908 satır, en-us) | ✅ bayt düzeyinde round-trip; cihazda doğrulandı (ürün sahibi, 2026-11) | belgelenmedi | 13 dil klasörü (USen, EUen…) ayrı tanınır (0.9.0). `docs/formats/msbt.md` |
| GFMSG (`.dat` + `.tbl`) | ✅ (32.026–32.558 satır, İngilizce) | ✅ değişiklik yapılmadan bayt bayt aynı | belgelenmedi | 0.11.0. `docs/formats/gfmsg.md` |
| M2 arşivi (`.psb.m` + `.bin`, mdf, PSB) | ✅ (3.353 satır: menü, onay, rehber) | ⚠️ "dizinden çıkar + gevşek dosya" yöntemi cihazda doğrulandı; aracın ürettiği mod denenmedi | ⚠️ ana menü etiketleri resim olabilir (TECH_DEBT 62) | Diyaloglar bir disk kalıbında, çözülmedi. `docs/formats/psb.md` |
| `pak.yc` (YCD, `.yc`) | ✅ (3.974 satır) | ✅ cihazda doğrulandı (menü, diyalog, tam mod) | ✅ fontta ğ ş ı İ var, yama gerekmedi | Bir kısmı elle hazırlanmış ek çeviri dosyasından gelir. `docs/formats/pak-yc.md` |
| `.fsd` / `.msg` mesaj tabloları (özel harf tablosu) | ✅ | ✅ cihazda doğrulandı; Türkçe harfler yeni harf dokusuyla | ✅ eklentinin ürettiği harf dokusu | Resim üzerindeki menü yazıları için grafik araçları var. `docs/formats/fsd-msg.md`, `docs/rehber/grafik.md` |
| `.nbz` arşivi (düz ZIP) | ⚠️ ZIP olduğu ve içindeki dosyalar belgeli; metin eklentisi belgelenmedi | belgelenmedi | belgelenmedi | `.nbz` düz ZIP arşividir; içindeki `msg_*.nb` metin dosyaları ve görüntü bindirmeleri ön değerlendirmedir, doğrulanmadı. `docs/formats/fsd-msg.md` |
| NNI arşivi (`.ni`/`.na`), XSO betikleri, arayüz XML'i, `.srt` altyazı | ✅ (10.805 satır, İngilizce) | ✅ cihazda doğrulandı (ürün sahibi, 2026-11) | ✅ BMFont'a ğ ş ı İ eklenir (harf dönüşmez) | Betik kimlikleri Japonca kopyayla ayrılır; resimler `grafik_temizleme` klasörüyle çevrilir (0.39.0). `docs/formats/nni.md` |
| CPK + CRILAYLA, FMSB MsgSheet | ✅ (49.242 satır, İngilizce) | ✅ mod yalnızca dil CPK'sını içerir; cihazda doğrulandı (ürün sahibi, 2026-11) | ⚠️ fontta ğ ş ı İ olmadığı varsayılır (dönüştürülür) | Yazılı yardım resimleri (`Help/*.ftx`) çevrilmez (0.36.0). `docs/formats/cpk-fmsb.md` |
| Unity (özel) / emülasyon tabanlı paketler | ❌ | ❌ | ❌ | Unity Localization yok; metin biçimi çözülmedi |
| Özel "PACK" arşivi | ❌ | ❌ | ❌ | RomFS açılıyor (LZ4 katmanı, 0.9.0); metin biçimi çözülmedi |
| Özel `.zpbn` | ❌ | ❌ | ❌ | Çözülmedi |
| Özel `.gin` | ❌ | ❌ | ❌ | Çözülmedi |
| Veri programın içinde | ❌ | ❌ | ❌ | RomFS yok |

0.9.0 öncesi bu biçimlerin çoğu daha tarama aşamasında duruyordu: NCZ bölüm sınırı, sıkıştırılmış NCA, seyrek NCA.
