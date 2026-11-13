# B aşaması: Menüler, Ayarlar, kısayollar (tasarım)

Kaynak: `docs/inceleme/2026-11-09-kullanilabilirlik.md` §2.1 (Ayarlar), §2.2 (görünüm menüsü, bağlam menüsü, düğmeler,
kısayollar), §4 B satırı. Hedef sürüm 0.50.0.

## Amaç
- Sayfalardaki "Daha Fazla" ve "Makine Çevirisi…" düğme satırı kalkar; işler menü çubuğuna taşınır. Çevir sayfasında
  tek birincil düğme kalır: **Otomatik Çeviri** (eski adı Makine Çevirisi).
- Dağınık ayarlar tek **Ayarlar** penceresinde toplanır (`Ctrl+,`).
- Kısayollar tek kayıt defterinden gelir ve kullanıcı tarafından değiştirilebilir.
- Tablo sağ tık menüsü gruplu, kısa ve simgeli olur.

## Bileşenler
1. **`nxceviri/gui/shortcuts.py`** (yapıldı): `COMMANDS` kataloğu (kimlik, ad, kategori, varsayılan tuş),
   `ShortcutRegistry` (`bind_settings`, `bind(id, QAction|QShortcut, tip=None)`, `sequence`, `text`, `set_sequence`,
   `reset`, `reset_all`, `conflicts`, `is_custom`, `changed(str)`). Ayar anahtarı `shortcuts/<kimlik>`.
   Varsayılanlar çakışmaz (test). Hizalama `Ctrl+Shift+L/E/R`'ye taşındı; `Ctrl+R` artık Redaksiyon.
2. **Ayarlar penceresi** (`nxceviri/gui/settings_dialog.py`): solda sayfa listesi (simgeli), sağda sayfa.
   - **Görünüm:** tema, yazı boyutu, sembolleri göster, hiza, panel konumu, metni kaydır, sorunları renkle göster.
     Değişiklik anında uygulanır (Tamam/İptal yok; "Kapat").
   - **Kısayollar:** aranabilir liste (Komut · Kısayol · kategori grupları), çift tıkla/“Değiştir” ile tuş kaydı
     (`QKeySequenceEdit`), çakışmada uyarı ve "Yine de ata" (öteki komut kısayolsuz kalır) ya da vazgeç;
     "Varsayılana dön" (seçili) ve "Tümünü varsayılana döndür". Özelleştirilmiş satır kalın.
   - **Çeviri sağlayıcıları:** DeepL API anahtarı (eski "Çeviri Ayarları" penceresinin içeriği; Windows Kimlik
     Bilgisi Yöneticisi) ve Ollama adresi + bağlantı testi.
   - **Güncelleme:** "Açılışta güncellemeleri denetle" ve "Şimdi denetle".
   - "Anlık denetimler" sayfası C aşamasıyla gelir; şimdi gösterilmez (işlevsiz arayüz yok).
3. **Menü çubuğu** (simgeli, kısayollar kayıt defterinden):
   - **Dosya:** Yeni Proje, Proje Aç, Son Projeler ▸, Kaydet, Farklı Kaydet · Anahtarlar ▸ · Önbelleği Temizle ·
     Ayarlar… · Çıkış
   - **Düzen:** Geri Al · Bul, Değiştir, Tabloyu Süz, Sonrakini/Öncekini Bul · Satırları Yeniden Böl, Orijinali Çeviri
     Olarak Yaz, Çeviriyi Temizle
   - **Görünüm:** Kenar Çubuğu, Çeviri Paneli, Panel Konumu ▸ · Semboller, Hizala ▸, Metni Kaydır, Sorunları Renkle
     Göster, Önceki Çeviri Sütunu (pasifken ipucu: "Son işte değişiklik yok") · Tema ▸, Yazı Boyutu ▸
   - **Çeviri:** Otomatik Çeviri…, Seçili Satırları Çevir/Yeniden Çevir, Redaksiyon… · Onayla, Onayı Kaldır · Sözlük…,
     Son İşin Değişiklikleri…, Çeviri Geçmişi… · Hazır Çeviriyi İçe Aktar…, Dış Redaksiyon ▸, Dış Çeviri ▸
   - **Git:** beş adım (`Ctrl+1…5`)
   - **Araçlar:** Metin Adaylarını Çıkar…, Oyunun Tüm Dosyalarını Çıkar…, Teşhis Raporu… · Yazım Sözlüğü…, Eklentiler…
   - **Yardım:** Güncellemeleri Denetle…, Log Klasörünü Aç, Hakkında
   Menü öğeleri, ilgili sayfa/proje yokken pasiftir (gizlenmez); seçime bağlı öğeler Çevir sayfasında seçim varken
   etkindir.
4. **Sayfalar:** Çevir'deki `more_button` ve `action_row` kalkar; "Otomatik Çeviri" birincil düğmesi süzgeç satırının
   sağına gelir; "Görünüm" araç düğmesi kalkar (menü çubuğunda). Metinleri Tara'daki "Daha Fazla" kalkar (Araçlar).
5. **Bağlam menüsü (Çevir tablosu):** Çevir ▸ (Çevir, Yeniden çevir, Redaksiyon) · Onayla / Onayı kaldır ·
   Düzenle ▸ (Satırları yeniden böl, Orijinali yaz, Temizle) · Kopyala ▸ · Dışa aktar ▸ · Büyük harf ▸ · Geçmiş ·
   Yerinde göster. Simgeli, kısayollar menüde görünür, sayılar parantez içinde.

## Hata ve sınırlar
- Bozuk kısayol ayarı varsayılana döner (günlüğe uyarı). Çakışan atamayı kullanıcı onaylamadan yapmayız.
- DeepL anahtarı hiçbir zaman günlüğe ya da ayar dosyasına yazılmaz (yalnızca kimlik bilgisi deposu).

## Test
- Kayıt defteri birim testleri (`tests/test_shortcuts.py`, yapıldı).
- Ayarlar penceresi: sayfa geçişi, tema/boyut sinyali, kısayol kaydı + çakışma + sıfırlama, DeepL sayfası sahte
  depo ile, güncelleme onay kutusu ayara yazar.
- Menüler: her menü öğesi tetiklenebilir ve işlevlidir (boş slot yok), kısayol değişince menü metni değişir,
  Çevir sayfasında "Daha Fazla" yok, bağlam menüsü grupları, Ctrl+R Redaksiyon'u açar.
