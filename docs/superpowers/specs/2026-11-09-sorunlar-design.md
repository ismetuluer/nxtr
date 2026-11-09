# C aşaması: Anlık denetim ve Sorunlar panosu (tasarım)

Kaynak: `docs/inceleme/2026-11-09-kullanilabilirlik.md` §2.2 (Yazım Denetimi, sınırlar tablosu), §2.6, §2.7, §2.13,
§4 C satırı. Hedef sürüm 0.51.0.

## Amaç
Sorunlar Çevir ekranından ayrılmadan görülür ve düzeltilir; Kontrol Et ise proje geneli **Sorunlar panosudur**
(sayılar, süzgeç, toplu ve yerinde düzeltme).

## Parçalar
1. **Anlık denetim** (`core/qa/live.py`, Çevir modeli, Ayarlar → Anlık Denetimler).
   - Satır başı denetimlerin hepsi (kod, etiket, uzunluk, sığdırma, satır sonu, boşluk, noktalama, eksik harf, sözlük,
     yazım, şüpheli …) satır çizilirken/kaydedilince o satır için çalışır; sonuç satır + bağlam değişene kadar önbellekte.
   - "Tutarsız çeviri" kaynak metne göre dizinle artımlı: bir satır değişince yalnızca aynı kaynaklı satırlar yenilenir.
   - Hangi türlerin anlık çalışacağı Ayarlar → **Anlık Denetimler** sayfasında seçilir (`qa/live_kinds`); varsayılan:
     hepsi açık, yazım açık.
   - Durum simgesi ve ipucu anlık sonuçtan beslenir; son Kontrol Et sonucu (font/proje geneli) üstüne eklenir.
2. **Sorunlar panosu** (`gui/qa_page.py`, "Satır denetimi" sekmesi → "Sorunlar").
   - Tür süzgeci **çip listesi** ("Satır sonu 22 · Sondaki noktalama 178 …"), boş türler gizli; çoklu seçim.
   - Düzeltmeler **daraltılabilir kenar paneli**; yalnızca bulgusu olan türler görünür; her türde 1 cümlelik ipucu +
     örnek; riskli toplu düzeltmeler varsayılan kapalı.
   - Kapsam açık seçim: "Listede seçili N bulgu" / "Tüm bulgular".
   - Çeviri hücresi bu tabloda **yerinde düzenlenir**; kayıt anında satır yeniden denetlenir, bulgu güncellenir.
   - Sağ tık bağlama göre: Bu satırı düzelt · Bu türdeki tümünü düzelt · Çevir'de göster · (yazım bulgusunda) Sözlüğe
     ekle. Sütun davranışı Çevir tablosuyla aynı (zaten `FitTableView`/`HeaderColumnMenu`).
3. **Yazım Denetimi penceresi** (Araçlar → Yazım Denetimi…, Sigil benzeri): sözlükte olmayan sözcükler + kaç satırda
   geçtiği; Yoksay (proje), Sözlüğe ekle, "Hepsini şununla değiştir" (tek iş, Geri Al), satırları göster.
4. **Terim tutarsızlığı** (`core/qa/terms.py`, tür `term`): kısa (1–4 sözcük, büyük harfle başlayan, ≥2 satırda geçen)
   kaynak ifadeleri ve sözlük terimleri kanonik çeviri sayılır; kaynağında ifade geçen satırların çevirisinde kanonik
   çeviri (Türkçe ek, büyük/küçük harf, satır sonu/kod/fazla boşluk yok sayılarak) aranır. Bulgu: "‘Silver Pines’ burada
   ‘Gümüş Çam’ olmuş; 14 satırda ‘Gümüş Çamlar’". "Terim değil" işaretlenebilir (proje ayarı).
5. **Sınırlar tablosu** (Sığdırma sekmesi): grup **ve anahtar deseni** başına satır sayısı, en uzun orijinal satır,
   öğrenilen sınır, elle sınır; "Hepsini öğren". Öncelik: anahtar deseni > grup > dosya > proje.
6. Sığdırma sekmesinde "Kod türleri" bölümü "Gelişmiş" altına iner.

## Hata ve sınırlar
- Anlık denetim 50.000 satırda kaydırmayı yavaşlatmaz (yalnızca görünen satırlar; önbellek). Süre testi.
- Yerinde düzenleme kontrol kodlarını bozamaz (mevcut kayıt kuralı: hatalı satır işaretlenir, sessizce düzeltilmez).

## Test
Her parça kendi birim/arayüz testleriyle; 50k satır süre testleri (anlık denetim, terim dizini).
