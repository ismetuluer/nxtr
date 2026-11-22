# Dışa Aktar

## Hedef

- **Atmosphère** (gerçek Switch): `atmosphere/contents/<TitleID>/romfs/…` klasörü üretilir; `atmosphere` klasörünü SD
  kartın köküne kopyalayın.
- **Emülatör:** `<Mod Adı>/romfs/…`; emülatörün mod klasörüne koyun ve modu etkinleştirin.

**Mod adı** ve **Konum** seçin, **Modu Oluştur**'a basın. İlerleme düğmenin içinde görünür; o sırada düğmeye basmak
işi durdurur. Yalnızca değişen dosyalar yazılır; mod önce geçici bir klasöre yazılıp denetlenir, sonra yerine taşınır.
Bitince sayfada **Mod hazır** yazar; **Mod Klasörünü Aç** ile görün. Hatalı satır, uyarı ya da font yaması varsa
ayrıntılar bildirimde gelir.

Özet kartı kaç satırın yazılacağını, hatalı ve çevrilmemiş satırları gösterir. Hatalı satırlar yazılmaz; oyunda orijinal
metin kalır.

Biçimin kabul etmediği ya da kaynağı oyun dosyasıyla uyuşmayan satır da orijinal kalır; yalnızca o satır atlanır,
dosyanın geri kalanı yazılır. Bu satırlar bildirimde ve bilgi dosyasında sayılır. Kaynak uyuşmazlığı çoğunlukla projenin
eski bir sürümde taranmasından gelir: **Metinleri Tara** ile yeniden tarayın.

## Dolu klasör

Hedefte NXTR'nin önceki modu varsa sorulmaz: yenisi yerine geçer, eskisi “(eski)” adıyla Geri Dönüşüm Kutusu'na gider
(oradan geri alınabilir). Yeni mod yazılamazsa eskisi yerinde kalır. NXTR'nin üretmediği dolu bir klasör güvenlik için
hiç silinmez; başka klasör seçmeniz istenir.

## Görseller

Bazı oyunlarda (şimdilik NNI arşivi kullananlarda) yazılar resimlerin içindedir. **Görseller** kartı:

1. **Orijinalleri Çıkar** yazı içeren resimleri oyun dosyalarınızın yanındaki klasöre PNG olarak koyar (`orijinal/`).
2. Resmi bir resim programında Türkçeleştirip **aynı adla** `turkce/` klasörüne kaydedin (eski kurulumlardaki `temiz/` klasörü, `turkce/` yoksa hâlâ okunur).
3. Mod oluşturulurken hazır resimler kendiliğinden yerleşir. Kart "Türkçe resim: 12 / 148" gibi ilerlemeyi gösterir.
