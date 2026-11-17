# Dışa Aktar

## Hedef

- **Atmosphère** (gerçek Switch): `atmosphere/contents/<TitleID>/romfs/…` klasörü üretilir; `atmosphere` klasörünü SD
  kartın köküne kopyalayın.
- **Emülatör:** `<Mod Adı>/romfs/…`; emülatörün mod klasörüne koyun ve modu etkinleştirin.

**Mod adı** ve **Konum** seçin, **Modu Oluştur**'a basın. Yalnızca değişen dosyalar yazılır; mod önce geçici bir
klasöre yazılıp denetlenir, sonra yerine taşınır. Bitince bildirim gelir; **Klasörü Aç** ile görün.

Özet kartı kaç satırın yazılacağını, hatalı ve çevrilmemiş satırları gösterir. Hatalı satırlar yazılmaz; oyunda orijinal
metin kalır.

Biçimin kabul etmediği ya da kaynağı oyun dosyasıyla uyuşmayan satır da orijinal kalır; yalnızca o satır atlanır,
dosyanın geri kalanı yazılır. Bu satırlar bildirimde ve bilgi dosyasında sayılır. Kaynak uyuşmazlığı çoğunlukla projenin
eski bir sürümde taranmasından gelir: **Metinleri Tara** ile yeniden tarayın.

## Dolu klasör

Hedefte daha önce NXTR'nin ürettiği bir mod varsa **Üzerine Yaz / Başka Klasör… / Vazgeç** sorulur. Üzerine yazarken
eski mod yedeğe alınır, sorun çıkarsa geri konur. NXTR'nin üretmediği dolu bir klasör güvenlik için hiç silinmez.

## Görseller

Bazı oyunlarda (şimdilik NNI arşivi kullananlarda) yazılar resimlerin içindedir. **Görseller** kartı:

1. **Orijinalleri Çıkar** yazı içeren resimleri oyun dosyalarınızın yanındaki klasöre PNG olarak koyar (`orijinal/`).
2. Resmi bir resim programında Türkçeleştirip **aynı adla** `turkce/` klasörüne kaydedin (eski kurulumlardaki `temiz/` klasörü, `turkce/` yoksa hâlâ okunur).
3. Mod oluşturulurken hazır resimler kendiliğinden yerleşir. Kart "Türkçe resim: 12 / 148" gibi ilerlemeyi gösterir.
