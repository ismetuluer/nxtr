# Yazılım denetimi (2026-10-25, 0.30.0)

Programın beş adımı bir kullanıcı gibi baştan sona gezildi (normal ve en küçük pencere boyutunda, açık ve
koyu temada), kod mimari açıdan okundu. Çeviri editörü için Subtitle Workshop ve Aegisub'ın iş akışı örnek
alındı: **ızgara + altında düzenleme kutusu + klavyeyle satırdan satıra ilerleme + anlık denetim.**

## Güçlü yanlar

- **Çekirdek sağlam:** biçim eklentileri (detect / extract / inject) ayrı, bayt düzeyinde geri yazım testleri
  var; kontrol kodları yer tutuculara çevriliyor ve her yazımda denetleniyor. Yeni oyun desteği eklemek çekirdeği
  değiştirmeden mümkün.
- **Veri güvenliği:** proje SQLite, her yazım işlem (transaction) içinde; çeviri geçmişi ve geri alma var;
  güncelleme yedekli ve geri alınabilir.
- **Makine çevirisi:** bağlamlı partiler, Türkçe üslup kuralları, yeniden çeviri, redaksiyon,
  değişiklik raporu.
- **Adım adım akış** (Oyunu Ekle → Tara → Çevir → Kontrol Et → Dışa Aktar) anlaşılır; boş ve hata durumları
  tasarlanmış; açık/koyu tema ve yazı boyutu ayarı var.

## Bulgular

Önem: **K** kritik (iş kaybı/bozuk görünüm), **Y** yüksek (günlük işi yavaşlatıyor), **O** orta, **D** düşük.

### Çeviri ekranı (en çok zaman geçirilen yer)

| # | Önem | Bulgu | Öneri |
|---|---|---|---|
| Ç1 | K | En küçük pencerede (820×560) alttaki düğmeler tablonun üstüne biniyor. | Tablo ve düzenleme paneli ayarlanabilir bölmede; asgari yükseklikler küçültülür. |
| Ç2 | Y | Çeviri yalnızca tablo hücresine çift tıklayarak yazılıyor; uzun metin, kontrol kodu ve satır uzunluğu hücrede görülmüyor. | Tablonun altında **satır düzenleme paneli**: özgün metin, kodların anlamı, çeviri kutusu, uzunluk sayaçları, anlık denetim, önceki/sonraki satır (sahne bağlamı). |
| Ç3 | Y | Klavyeyle çalışılamıyor: sonraki satıra geçme, kaydet-ve-ilerle, onaylanmamış sonraki satıra atlama yok. | Ctrl+Enter kaydet ve sonraki; Alt+↑/↓ önceki/sonraki; F3 sonraki bakılacak satır; Ctrl+F ara; Ctrl+H bul/değiştir. |
| Ç4 | Y | Makine çevirisini değiştirmeden **onaylamanın** yolu yok (yalnızca metni değiştirince "onaylandı" oluyor). | "Onayla" (tek satır ve seçili satırlar); kaydet-ve-ilerle aynı zamanda onaylar. |
| Ç5 | Y | **Bul ve değiştir** yok (ör. bir karakter adının çevirisini her yerde değiştirmek). | Çevirilerde bul/değiştir: büyük/küçük harf, tam sözcük, yalnızca görünen satırlar; kontrol kodunu bozan değişiklik atlanır; geri alınabilir. |
| Ç6 | O | Bilgi bandı (ör. içe aktarma sonucu) kapatılamıyor ve tablo alanını daraltıyor. | Banda kapatma düğmesi. |
| Ç7 | O | Kontrol kodları hücrede `⟦1⟧` olarak görünüyor ama ne oldukları yalnızca ipucunda. | Düzenleme panelinde kod listesi ve tıklayınca imlece ekleme. |
| Ç8 | O | Satır uzunluğu ve kutu sınırı yazarken görünmüyor; taşma ancak Kontrol Et'te çıkıyor. | Panelde satır satır karakter sayısı, özgünle karşılaştırma, sınır aşımında uyarı. |
| Ç9 | D | Çevirmen notu / işaretleme (ör. "sonra bak") yok. | Satır notu ve yer imi (sonraki aşama). |
| Ç10 | D | Yazım denetimi yok. | Türkçe yazım denetimi (hunspell; bağımlılık değerlendirilmeli). |

### Kontrol Et

| # | Önem | Bulgu | Öneri |
|---|---|---|---|
| K1 | O | Bulgu listesinde metin görünmüyor; satıra gitmek anahtarla aramaya dayanıyor (aynı anahtar başka dosyada da olabilir). | Listede özgün/çeviri sütunu; çift tıklayınca tam o satıra gidilip düzenleme panelinde açılsın. |
| K2 | O | Otomatik düzeltme, programın kendisinin yapabileceği işleri de modele gönderiyor (satır sonu sayısını dengeleme, aynı türden kodların sırası, çevrilmeden kalmış sözlük terimi). | Bu düzeltmeler yerel yapılsın; "yalnızca program düzeltsin" seçeneği. |
| K3 | D | Font denetimi ve satır denetimi aynı uzun sayfada. | İki sekme. |

### Diğer adımlar

| # | Önem | Bulgu | Öneri |
|---|---|---|---|
| T1 | O | Tarama özetinde 10 kutunun çoğu "0"; önemli bilgi kayboluyor. | Yalnızca bulunan türler gösterilsin. |
| E1 | D | Dar pencerede Oyunu Ekle tablosundaki "Kaldır" bağlantısı ilk sütunun üstüne kayıyor. | Sütun genişlikleri düzeltilmeli. |
| D1 | O | Dışa aktarmadan önce "hangi dosyalar yazılacak" listesi yok. | Özet altında dosya listesi. |

### Proje ve veri güvenliği

| # | Önem | Bulgu | Öneri |
|---|---|---|---|
| P1 | Y | Kaydedilmemiş yeni proje bellekte; çökme veya elektrik kesintisinde tarama ve çeviriler kaybolur. | Metinler içe aktarılınca proje dosyası istenir ya da otomatik kurtarma dosyası tutulur. |
| P2 | O | "Son projeler" listesi yok. | Dosya → Son Projeler; açılışta son proje önerisi. |

### Mimari

| # | Önem | Bulgu | Öneri |
|---|---|---|---|
| M1 | O | `gui/main_window.py` 1.650 satır, 109 metot: proje, anahtar, tarama, makine işleri, QA, güncelleme, geçmiş tek sınıfta. Değişiklik riski ve test maliyeti yüksek. | Denetleyicilere bölünmeli: `ProjectController`, `MachineController`, `UpdateController`… Davranış değişmeden, testlerle adım adım. |
| M2 | O | Testler CI'da çalışmıyor; release testlerden bağımsız (TECH_DEBT 67). | Windows runner'lı test iş akışı; release ona bağlanır. |
| M3 | O | Kurulum internet + Python + pip gerektiriyor (M9 bekliyor). | Taşınabilir paket (PyInstaller/Nuitka), güncelleme paket üzerinden. |
| M4 | D | Ayarlar iki yerde (QSettings ve proje ayarları); hangisinin nerede olduğu belgelenmeli. | ARCHITECTURE.md'ye tablo. |

## Yol haritası

Durum (0.31.0): A–E aşamalarının hepsi yapıldı. M1'in kalanı TECH_DEBT 69'da.

1. ✅ **A — Çeviri editörü ve ergonomi:** Ç1–Ç8, T1.
2. ✅ **B — Kontrol Et iyileştirmeleri:** K1, K2 (yerel düzeltmeler + model çıktısı temizliği), K3; ek olarak
   tabloda sorun renkleri.
3. ✅ **C — Proje güvenliği:** P1 (kurtarma kopyası), P2 (son projeler).
4. ✅ **D — Mimari:** M1 ilk adım, M2 (Windows CI), M4 (ayarlar tablosu ARCHITECTURE.md'de).
5. ✅ **E — Paketleme (M9):** M3 (PyInstaller onedir, release'e zip).
6. **Sürekli:** yeni oyun biçimleri (uyumsuz oyun çıktıkça), Ç9–Ç10, D1, E1.
