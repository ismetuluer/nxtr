# D aşaması: Bildirimler ve Otomatik Çeviri (tasarım)

Kaynak: `docs/inceleme/2026-11-09-kullanilabilirlik.md` §2.3, §2.5, §3, §4 D; kullanıcının 2026-11-09 istekleri:
"Hata ya da bir görev ya da işlem — program beni bilgilendirsin", "uygulamaya bakmadan nasıl anlarım", "program beni
habersiz bırakmasın"; iş sonundaki uzun sarı kutu kalksın; değişiklikler penceresinde kaydırma, yerinde düzenleme,
bağlam ipucu. Hedef sürüm 0.52.0.

## Bildirim merkezi (`gui/notify.py`)
- `NotificationCenter.notify(level, title, text="", actions=(), *, loud=None) -> Notice`. Düzey: başarı, uyarı, hata,
  bilgi. Her bildirim: uygulama içi **kart** (sağ alt, üst üste; tek satır başlık + en çok iki satır metin + düğmeler)
  ve **geçmiş** (son 50; durum çubuğundaki zil düğmesinden).
- **Gürültülü** bildirim (pencere etkin değilken ya da iş ≥ 2 sn sürdüyse): Windows bildirimi (`QSystemTrayIcon`;
  tıklanınca pencere öne gelir), ses (başarı/uyarı/hata ayrı `MessageBeep`), pencere arkadaysa görev çubuğu yanıp
  söner (`QApplication.alert`). Kısa ve kullanıcının önünde biten işlemde yalnızca kart.
- Başarı/bilgi kartı 8 sn sonra kendiliğinden kapanır (fare üstündeyken beklemez); hata ve düğmeli kart kullanıcı
  kapatana dek kalır.
- Ayarlar → **Bildirimler**: ses, Windows bildirimi, görev çubuğu yanıp sönmesi (varsayılan açık).

## Bağlantılar
- Her arka plan işi (`MainWindow._run`) bitince, durunca ya da hata verince bildirim; hata kartında **Tekrar Dene**.
- Çevir sayfasındaki uyarı kutusu (`show_notice`) kalkar; aynı mesajlar karta gider. Otomatik Çeviri sonucu kısa
  özet olur: "Yeniden çeviri bitti" · "3.938 satır değişti · 6 satır denetimden geçmedi" + [Değişiklikleri Gör]
  [Ayrıntılar]; ayrıntı (reddedilen öneriler vb.) ayrı pencerede.
- Güncelleme: yeni sürüm bulununca kart + Windows bildirimi ([Şimdi Güncelle] [Sonra]); kurulum başarısızlığı açılışta
  hata bildirimi.
- Karar isteyen sorular (kaydedilsin mi, emin misiniz) soru penceresi olarak kalır.

## Değişiklikler penceresi
Orijinal/Önceki/Yeni sözcük sınırında kayar; "Yeni" hücresi çift tıkla düzenlenir (yazılınca kayıt yolu, Geri Al);
"Bağlamı göster" seçeneği (hatırlanır) açıkken satırın ipucunda önceki ve sonraki iki satırın orijinali ve çevirisi.

## Otomatik Çeviri
Sade düzen (Sağlayıcı · Model · İş · Kapsam · Başlat; uygun satır yoksa Başlat pasif ve nedeni tek satır), kapsamda
grup/anahtar deseni, **talimat kitaplığı** (AppData'da adlandırılmış talimatlar; kaydet, seç, sil), yarım yanıtta
partiyi bölerek otomatik yeniden deneme.

## Test
Bildirim merkezi birim testleri (sahte tepsi/ses/uyarı), her `_run` yolunun bildirim ürettiği, sarı kutunun kalktığı,
güncelleme bildirimi, değişiklikler penceresi, talimat kitaplığı, yarım yanıt bölme.
