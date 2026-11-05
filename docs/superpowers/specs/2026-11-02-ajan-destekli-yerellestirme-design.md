# Ajan destekli yerelleştirme — tasarım (2026-11-02)

## Amaç

Projeyi indiren herkes, kendi bilgisayarında ve kendi yapay zekâ ajanıyla (Claude Code, Codex, Gemini CLI, Cursor…)
proje klasörünü açıp yeni bir oyunun metinlerine erişebilsin, font/grafik sorunlarını çözebilsin ve yamasındaki
sorunları giderebilsin; proje sahibinin desteğine gerek kalmadan. Tek bir "maymuncuk" program olmadığı için paketlenen
şey programın kendisi değil, **yeni oyunu çözme yöntemi**dir: ajanın okuyacağı rehberler, ajanın kullanacağı araçlar ve
kullanıcının eklentisini güvenle takabileceği bir yükleyici.

## Kararlar (ürün sahibiyle)

| Konu | Karar |
|---|---|
| Dağıtım | Depo herkese açık; katkı isteğe bağlı. Paylaşmak istemeyen eklentisini kendinde tutar, yamayı paylaşır. |
| Çalıştırma | İkisi birden: eklenti kaynak koddan geliştirilip test edilir; aynı klasör hazır pakete (`NXTR.exe`) takılabilir. |
| Güncelleme | GitHub'dan; açılışta otomatik denetim isteğe bağlı, her zaman elle denetlenebilir. |
| Yardım alanları | Hepsi, aşamalı: yeni oyunun metinleri, yama sonrası sorun giderme (önce); font, grafik (sonra). |
| Dil | Şimdilik Türkçe (arayüz, belgeler, ajan talimatları). Eklentiler dilden bağımsız kalır. |
| Yaklaşım | B — katmanlı bilgi tabanı + araçlar (tek büyük rehber ve skill merkezli yaklaşımlar elendi). |
| Lisans | MIT (ürün sahibi kararı: herkes dilediği gibi kullanabilir). |

## 1. Dosya yapısı ve ajanın giriş noktası

```
AGENTS.md              her ajanın ilk okuduğu dosya (kısa): kurallar + görev yönlendirmesi
CLAUDE.md              "@AGENTS.md" + Claude'a özel kısa notlar
GEMINI.md              AGENTS.md'ye yönlendirir
docs/rehber/           baslarken, yeni-oyun, eklenti-yazma, font, grafik, sorun-giderme, katki
docs/formats/README.md dizin: motor → biçim → çözülmüş oyunlar → not dosyası
docs/istemler.md       kullanıcının ajana yapıştıracağı hazır talimatlar
docs/yol-haritasi.md   ürün sahibinin yol haritası ve kararları (bugünkü CLAUDE.md §8)
eklentiler/            depo içi geliştirme klasörü (README dışında git'e girmez)
.claude/skills/, .agents/skills/   ince skill'ler
```

`AGENTS.md`: (1) pazarlık konusu olmayan kurallar — anahtar aranmaz/indirilmez/loglanmaz, oyun dosyası indirilmez ve depoya
konmaz, testlerde yalnızca elle üretilmiş örnekler, orijinal dosyalara dokunulmaz; (2) "kullanıcı X istiyorsa Y rehberi"
tablosu; (3) komutlar (pytest, ruff, mypy), kod düzeni, Türkçe arayüz ve rapor; (4) kullanıcı programcı olmayabilir:
kararı ajan verir, kısa Türkçe ile gerekçelendirir. Bugünkü `CLAUDE.md` genel kurallar (`AGENTS.md`) ve sahibin yol
haritası (`docs/yol-haritasi.md`) olarak bölünür; başka kullanıcının ajanı sahibin M1–M9 planını uygulamaya kalkmaz.

## 2. Araçlar (`python -m nxceviri.arac <komut>`)

| Komut | İş | Çıktı |
|---|---|---|
| `teshis <oyun dosyaları>` | Kullanıcının `prod.keys`'iyle açar (yol uygulama ayarından), base+update+DLC birleştirir, RomFS'i önbelleğe çıkarır | `teshis-raporu.md`: TitleID/sürüm, uzantı dağılımı, en büyük dosyalar, imza grupları, motor tahmini, eklentilerin tanıdığı dosyalar, aday metin dosyaları + kısaltılmış örnek satırlar |
| `ara "<metin>"` | Ekranda görülen cümleyi UTF-8/UTF-16/Shift-JIS olarak tüm dosyalarda ve iç içe arşivlerde (SARC/Yaz0/ZSTD…) arar | dosya, iç yol, ofset, kodlama |
| `dogrula <eklenti> <oyun>` | Gerçek dosyada değişikliksiz extract→inject bayt eşitliği + işaret metni yazıp yeniden okuma | dosya başına geçti/kaldı, satır sayısı |
| `eklenti-olustur <ad>` | `eklentiler/<ad>/` iskeleti | `eklenti.toml`, `plugin.py`, `tests/`, `NOT.md` |
| `eklentiler` | Yüklü eklentiler ve yükleme hataları | liste |

Rapor ve doğrulama yalnızca kullanıcının bilgisayarında kalır; rapor başında "oyun metni örnekleri içerir, paylaşmadan
önce bakın" uyarısı. Arayüzde Metinleri Tara → Daha Fazla → "Teşhis Raporu Oluştur" (ajanı olmayan kullanıcı için).

## 3. Eklenti yükleyici

- Konum: `%LOCALAPPDATA%\NXCeviri\eklentiler\` (her iki çalıştırma biçimi; güncelleme dokunmaz) + kaynak kodda depodaki
  `eklentiler/`.
- Paket: klasör = `eklenti.toml` (ad, sürüm, yazar, TitleID'ler, `api = 1`) + `plugin.py` (mevcut `detect/extract/inject`
  sözleşmesi) + `tests/` (elle üretilmiş örnekle bayt bayt round-trip) + `NOT.md`.
- Yükleme: açılışta; hatalı eklenti uygulamayı durdurmaz, Yardım → Eklentiler penceresinde nedeniyle listelenir. `api`
  uyumsuzsa atlanır, gereken sürüm söylenir. Kullanıcı eklentisi yerleşikten önce denenir. Exe'de saf Python eklentileri
  yüklenir; yalnızca pakette gelen kütüphaneler kullanılabilir (liste `eklenti-yazma.md`'de).
- Proje, metinlerin hangi eklenti ve sürümle çıkarıldığını kaydeder; eksik/farklı sürümde açılışta uyarır.
- Güvenlik: eklenti kod çalıştırır, korumalı alan yoktur; rehberde ve pencerede uyarı + klasör yolu.
- Paylaşım: kendinde tut / klasörü zip'leyip ver (Eklentiler → "Eklenti Ekle…") / `katki.md` ile çekme isteği; kabul
  edilen eklenti `nxceviri/core/formats/`'a taşınır.

## 4. Rehberler

Ortak yapı: ne zaman okunur → adımlar (komut + sonucu okuma) → karar noktaları → "bitti" ölçütü → kullanıcıya rapor.

- `yeni-oyun.md`: teşhis (tanınıyorsa doğrudan uygulamaya) → `ara` ile metni bul → motora göre yol (Unity/Unreal/MSBT
  tarifleri; bilinmeyen ikili: imza → tablo/ofset → kodlama → kontrol kodları; Danganronpa LIN, M2 PSB, FMSB örnekleri)
  → `eklenti-olustur` + önce test → `dogrula` geçmeden bitmez → uygulamada Tara → çevir → Dışa Aktar, cihaz/emülatör
  denemesi kullanıcıdan → `NOT.md`, `docs/uyumluluk.md` önerisi, istenirse `katki.md`.
- `sorun-giderme.md`: belirti → neden karar ağacı (açılmıyor, taşıyor, kutucuk harf, İngilizce kalan satır, mod
  görünmüyor).
- `font.md`, `grafik.md`: uygulamanın araçları, sonra çözülmüş örnekler (DMC1, DKCR, Ys Origin) ve yeni biçimde yöntem.
- Kalite: "test edildi" demeden önce komut çıktısı gösterilir; cihazda denenmeyen iş öyle raporlanır.

## 5. Skill'ler, istem kartları, güncelleme

- Skill'ler (Agent Skills biçimi, `.claude/skills/` ve `.agents/skills/`): `nxtr-yeni-oyun`, `nxtr-sorun-giderme`,
  `nxtr-font`, `nxtr-grafik`, `nxtr-katki`. Her biri birkaç satır: ilgili rehberi okut, adımları başlat. Bilgi rehberde.
- `docs/istemler.md`: tek işlik kartlar, doldurulacak boşluklar belirgin (yeni oyun, mod sorunu, font, grafik, paylaşım,
  "bu bilgisayara kur"). README başına "Yapay zekâ ajanıyla kullanım" bölümü.
- Güncelleme: Ayarlar → "Açılışta güncellemeleri denetle"; Yardım → Güncellemeleri Denetle her zaman. Anahtar gerekmez
  (depo açık). Exe: zip indirilir, release iş akışının yayımladığı SHA-256 ile doğrulanır, uygulama kapanınca küçük
  yardımcı klasörü değiştirir ve yeniden açar, başarısızsa eskisini geri koyar. Kaynak kurulum: mevcut zipball yolu, git
  ile kurulduysa `git pull` önerisi. Eklentiler, projeler, ayarlar uygulama klasörü dışında. Değişiklik notu sürüm
  açıklamasından.

## 6. Depoyu açma ve katkı düzeni

- Açılış denetimi: depoda ve git geçmişinde oyundan alınmış metin/resim/dosya (şüpheliler: `docs/dmc1-*.json`,
  `docs/mina-ek-ceviriler.json`, biçim notlarındaki uzun alıntılar), gizli bilgi ve kişisel yollar. Geçmişte oyun
  içeriği varsa temiz geçmişle yeni depo ya da geçmiş temizliği — ürün sahibi karar verir.
- Lisans: MIT + paketlenen parçaların lisansları (Lucide ISC, hunspell-tr MPL-2.0, yardımcı ikililer).
- `katki.md`, çekme isteği şablonu; CI'ye eklenti denetimi (`eklenti.toml` geçerli, örnek testler var ve geçiyor, büyük
  ikili dosya yok); konu şablonları (oyun desteği isteği — teşhis özeti, oyun dosyası değil; hata; eklenti paylaşımı);
  `docs/uyumluluk.md` herkese açık oyun listesi (oyun, biçim, metin/font/grafik durumu, çözen).

## Aşamalar (her biri ayrı sürüm)

1. `AGENTS.md` bölünmesi, `docs/rehber/` iskeleti, `yeni-oyun` ve `sorun-giderme` rehberleri, istem kartları.
2. Araçlar: `teshis`, `ara`, `dogrula`, `eklenti-olustur`, `eklentiler`.
3. Eklenti yükleyici, Eklentiler penceresi, proje kaydı. **Prova:** başka bir ajan temiz klasörde yalnızca istem kartıyla
   bir oyunu baştan çözmeye çalışır; takıldığı yerler rehbere geri yazılır.
4. Güncelleyici (anahtarsız, kendiliğinden kurulum, isteğe bağlı otomatik denetim).
5. Font ve grafik rehberleri, skill'ler.
6. Açılış denetimi, lisans, katkı düzeni, depoyu herkese açma.

## Kapsam dışı

Çok dilli hedef (şimdilik), eklenti korumalı alanı, eklenti mağazası/uzak depo, ajanın oyun dosyası indirmesi.

## Başarı ölçütü

Projeyi ilk kez gören biri, yalnızca README ve bir istem kartıyla kendi ajanına yeni bir oyunun metinlerini tabloya
aktarttırabiliyor ve `dogrula` geçen bir eklentiyle mod üretebiliyor; aşama 3 provası bunu ölçer.
