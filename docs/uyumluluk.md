# Oyun uyumluluğu (gerçek oyunlarla tanılama, 0.12.0)

Geliştirme makinesindeki oyunlarla tarama → metin aktarma denendi. "Satır" aktarılan kaynak dil
metin sayısıdır. Oyun dosyaları depoya konmaz; yalnızca sonuçlar burada.

| Oyun | Motor / biçim | Durum | Not |
|---|---|---|---|
| Silver Pines | Unity Localization | ✅ 3466 satır | Font yaması: ana fontlara ı İ ş Ş ğ Ğ (0.12.0) |
| Castlevania: Belmont's Curse | Unity Localization | ✅ 2751 satır | Base seyrek: güncelleme şart (0.9.0) |
| Kong: Survivor Instinct | Unity Localization | ✅ 1383 satır | "en-us" ↔ "en" eşleşmesi düzeltildi (0.9.0) |
| Rhythm Heaven Groove | MSBT | ✅ 6908 satır (en-us) | 13 dil klasörü (USen, EUen…) artık ayrı tanınıyor (0.9.0) |
| SpongeBob: Titans of the Tide | Unreal .locres (.pak) | ⚠️ 2 satır | Oyun metinleri Oodle sıkıştırmalı (desteklenmiyor, TECH_DEBT 37); yalnızca birkaç motor metni |
| Avatar Legends: The Fighting Game | Özel "PACK" arşivi | ❌ | RomFS açılıyor (LZ4 katmanı, 0.9.0); metin biçimi oyuna özgü |
| Blasphemous | Unity, I2 Localization | ✅ 1925 satır (İngilizce sütunu) | 0.10.0; arayüz, eşya ve diyalog metinleri |
| Despelote | Unity, düz metin (`TextAsset`: SRT altyazı + TSV tablo) | ✅ 15.978 satır (İngilizce) | 0.27.0; oyun metni `Locoliser` önbelleğinden okur, Türkçe İngilizce yuvasına yazılır; gömülü fontlara ı İ ş Ş ğ Ğ eklenir; cihazda Türkçe metin doğrulandı (0.26.0), font yaması denenmedi (TECH_DEBT 65). `docs/formats/unity.md` |
| Metal Gear / MGS 1–3 Master Collection | Unity (özel) / emülasyon | ❌ | Unity Localization yok |
| MGS1 (Master Collection, Switch) | M2 arşivi (`.psb.m` + `.bin`, mdf, PSB) | ✅ 3.353 satır (menü, onay, rehber, Master Book) | 0.23.0; "dizinden çıkar + gevşek dosya" yöntemi cihazda doğrulandı (menü/onay yazıları), aracın ürettiği mod ve Master Book denenmedi. Ana menü etiketleri resim olabilir (TECH_DEBT 62); PS1 diyalogları çözülmedi. `docs/formats/m2.md` | Diyaloglar PS1 disk kalıbında (çözülmedi). `docs/formats/m2.md` |
| Pokémon Legends: Arceus | Game Freak `.dat`/`.tbl` | ✅ 32558 satır (İngilizce) | 0.11.0 |
| Pokémon: Let's Go, Pikachu! | Game Freak `.dat`/`.tbl` | ✅ 32026 satır (İngilizce) | 0.11.0 |
| Devil May Cry (1) | Özel (`.fsd`/`.msg`) | ⚠️ Yalnızca okuma: 410 satır | 0.20.0; yazma ve Türkçe harfler yok (TECH_DEBT 61) |
| Devil May Cry 2 / 3 | Özel (`.nbz` arşivi) | ❌ | `.nbz` biçimi çözülmedi |
| Mina the Hollower | Yacht Club YCD (`.yc`) | ✅ 3.974 satır, tamamı Türkçe | 0.17.0; cihazda doğrulandı (menü, diyalog, ğ ş ı İ, tam mod). 3.892 satır yamadan, 82'si `docs/mina-ek-ceviriler.json` |
| Scott Pilgrim EX | Özel (`.zpbn`) | ❌ | |
| MIO: Memories in Orbit | Özel (`.gin`) | ❌ | |
| Animal Well | Veri programın içinde | ❌ | RomFS yok |
| Ys Origin | Falcom NNI arşivi (`.ni`/`.na`), XSO betikleri + arayüz XML'i + giriş altyazısı (`.srt`) | ✅ 10.805 satır (İngilizce) | 0.39.0; betik kimlikleri Japonca kopyayla ayrılır; yazı tiplerine ğ ş ı İ eklenir (harf dönüşmez); resimler `grafik_temizleme` klasörüyle çevrilir. Cihazda denenmedi. `docs/formats/ys-origin.md` |
| Unicorn Overlord | CRI CPK + CRILAYLA, Vanillaware FMSB MsgSheet | ✅ 49.242 satır (İngilizce) | 0.36.0; mod yalnızca `Unicorn_US.CPK`; fontta ğ ş ı İ olmadığı varsayılıyor (dönüştürülür). Yardım resimleri (`Help/*.ftx`) çevrilmez. Cihazda denenmedi. `docs/formats/unicorn-overlord.md` |

0.9.0 öncesi bu oyunların çoğu daha tarama aşamasında duruyordu: NCZ bölüm sınırı (Blasphemous,
MIO, MGS, Avatar), sıkıştırılmış NCA (Avatar), seyrek NCA (Castlevania).
