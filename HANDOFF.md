# HANDOFF — oturum devri (2026-11-02, 0.47.0)

## Durum
- **Sürüm 0.48.0** (2026-11-06): ajan destekli yerelleştirme — AGENTS.md + docs/rehber + skill'ler + istem kartları, araçlar (nxceviri/arac: teshis/ara/dogrula/eklenti-olustur/eklentiler), kullanıcı eklentileri (core/plugins, Yardım → Eklentiler), anahtarsız + kendiliğinden güncelleme (core/selfupdate), MIT LICENSE + THIRD_PARTY_NOTICES, DMC1 metni özetle; ARCHITECTURE §4.34. Depo temiz geçmişle yeni depoya (ismetuluer/nxtr) taşındı. Açık: aşama 3 provası (temiz klasörde istem kartıyla ajan).
- **Sürüm 0.47.0** (2026-11-02): ad NXTR + logo (`docs/tasarim/logo/uret.py` üretir), Kontrol Et seçmeli düzeltme + rapor (Ollama düzeltmesi kaldırıldı), yeni denetimler, kod sırası, grup sınırları, satırları yeniden böl, hatalı satırları da aktar; ARCHITECTURE §4.33. Opus şef + Sonnet işçiler (`isci/*` dalları, `.claude/worktrees/w-*`). Menü itirazları sadeleştirme istekleriyle karşılandı; sadeleştirme sürecek.
- **Sürüm 0.46.0** (2026-11-02): sadeleştirme turu — Çevir/Kontrol Et düğmeleri menülere, sağ tık menüsü 6 öğe, gürültü azaltıldı; ARCHITECTURE §4.32. Sıradaki: Makine Çevirisi penceresini sadeleştir, NXTR adı + logo, kalan menü itirazları.
- **Sürüm 0.43.0** (2026-11-02): 5. paket — Türkçe yazım denetimi (`core/spell`, QA `spelling`, editörde dalgalı çizgi, `spell_dialogs`), kullanıcı sözlüğü; ARCHITECTURE §4.29, TECH_DEBT 77. Süzgeç `tr.bloom` (11 MB, MPL-2.0).
- **Sürüm 0.42.0** (2026-11-02): 4. paket — çeviri talimatı kutusu ve hazır talimatlar (`TRANSLATE_PRESETS`),
  ARCHITECTURE §4.28.
- **Sürüm 0.41.0** (2026-11-02): 3. paket bitti — sözlük XLSX içe/dışa aktarma (`glossary_io`), bilgi notları
  (çevirisiz sözlük maddesi), Ollama ile terim önerisi (`terms`, `TermSuggestionsDialog`); ayrıca kullanıcı isteğiyle
  noktalama denetimi (QA `end_punctuation` yerel düzeltilir, `punctuation` uyarı). ARCHITECTURE §4.27.
- **Sürüm 0.40.0** (2026-11-01): arayüz düzeltmeleri (anahtarlar Dosya → Anahtarlar menüsünde ve durum çubuğunda,
  "Metinleri Tara →" taramayı başlatır, çeviri tablosunda hata/uyarılar durum sütununda, alt panel taşması), yeni
  çevirilerde uydurma koruması (`guards.translation_problems`, QA `suspicious`), tutarsız çeviri denetimi (QA
  `inconsistent`), Ollama sıcaklık 0,2 + sabit `seed`, oyun notları sistem isteminde (ARCHITECTURE §4.26).
  0.39.0 başka oturumun Ys Origin işidir (§4.25, TECH_DEBT 71–76).
- **Sıradaki paketler (ürün sahibinin istek listesi):** 6) NXTR adı ve Joy-Con'dan esinli kırmızı/beyaz logo (önce 2–3 taslak); menülerle ilgili
  itirazların ayrıntısı kullanıcıya soruldu, yanıt bekleniyor.
- **Sürüm 0.38.0 yayımlandı** (2026-11-01): `master` GitHub'a gönderildi, CI yeşil, release `v0.38.0` ve
  `NXCeviri-0.38.0-windows.zip` hazır. Depo ürün sahibinin kararıyla **gizli** kalıyor (geçmişte DMC1'in İngilizce
  düşman açıklamaları var); paylaşım depoya davetle. Depoda lisans dosyası yok.
- **0.38.0:** uygulama simgesi (`nxceviri/gui/appicon/`, `packaging/make_icon.py`); CI düzeltmeleri — testlerde mypy
  hataları, offscreen testlerin Windows yazı tiplerini görmesi (`QT_QPA_FONTDIR`). Yerelde CI'ın yaptığı gibi
  denetlemek için: `ruff check .`, `ruff format --check .` (Markdown kod blokları dahil), `mypy` (testler dahil).
- **Arayüz yenileme (0.32–0.37) bitti:** metin sığdırma (satır/sayfa sınırı, otomatik bölme, kod türleri),
  simge sistemi + kenar çubuğu + durum çubuğu, çeviri sayfası (altta/sağda düzenleme paneli, sembolleri göster/gizle,
  hiza, kod çipleri), diğer dört sayfada başlık eylemleri ve durum çipi. Ayrıntı: CHANGELOG, ARCHITECTURE §4.20–4.24,
  tasarım belgeleri `docs/superpowers/specs/2026-10-3*`, `2026-11-01-*`.
- **0.36.0 (başka oturum):** Ys Origin ve Unicorn Overlord metin eklentileri (TECH_DEBT 71–73).
- **Taşınabilir paket Windows'ta denendi (2026-11-01; ürün sahibi akışı onayladı):** master'ın temiz kopyası geçici bir klasörde, CI ile aynı
  adımlarla (Python 3.13, `pip install .`, PyInstaller 6.22.3, `packaging/NXCeviri.spec`) derlendi: 137 MB onedir
  klasör. `NXCeviri.exe` açıldı, 0.37.0 başlatıldı, `prod.keys`/`title.keys` okundu (günlükte hata yok). Pakette Qt
  Windows/SVG eklentileri, `qtbase_tr.qm`, simgeler, `nxceviri` modüllerinin tamamı, fontTools tabloları,
  `keyring.backends.Windows` + `win32ctypes`, httpx, zstandard, UnityPy var. Derleme uyarıları zararsız
  (`pycparser.lextab/yacctab`, UnityPy ses için `fmod.dll`). Ekran üstünden tıklayarak deneme **yapılmadı**
  (kullanıcı ekran denetimi iznini vermedi) — bkz. TECH_DEBT 70.
- Yığın: Python 3.13, PySide6-Essentials, cryptography, zstandard, UnityPy, httpx, keyring, fonttools, lz4, Pillow
  (gerekçeler ARCHITECTURE.md).

## Çalışma ağacındaki başka işler (commit edilmedi, bu oturuma ait değil)
`TECH_DEBT.md` (madde 49), `nxceviri/core/export/layeredfs.py`, `nxceviri/core/fontpatch/dmc1_*.py`,
`nxceviri/core/qa/fonts.py`, `nxceviri/gui/jobs.py`, `nxceviri/gui/translate_page.py` (2 satır), testler
(`test_dmc1_images`, `test_export`, `test_fontpatch_switchfont`, `test_gui` — `version_banner` bloğu çipi okuyacak
biçimde güncellendi) ve izlenmeyen `rhg_ranks.py`, `switchtex.py`, `docs/formats/rhg-tex.md`, `docs/*-dmc1.md`.
Bu yüzden `git checkout master` engelleniyor; master `git branch -f` ile ileri sarıldı.

## Kullanıcının yapacağı testler
- **Paket (M9):** paketlenmiş `NXTR.exe` → oyun ekle → tara → aktar → (Ollama ya da DeepL ile)
  birkaç satır çevir → Kontrol Et → Dışa Aktar. DeepL anahtarını kaydetmek Kimlik Bilgisi Yöneticisi'ni dener.
- **Cihaz/emülatör:** denenmemiş modlar — MGS1 (TECH_DEBT 62–64), Despelote (65), Ys Origin / Unicorn Overlord (71),
  Silver Pines font yaması (M5/M8 bitme ölçütü).

## Bilinen hatalar ve ertelenenler
- Veritabanı yazımı başarısız olursa pencere kapanırken panelde kaydedilmemiş metin kaybolur (nadir).
- Arayüz incelemelerinden ertelenen küçükler: Font/Sığdırma sekme açıklaması boş etiketin ipucunda; çip metin sınırı
  40 (tasarım ~30); koyu temada çip penceresi gövde rengi; `_set_wrap` görünümü iki kez yeniler; HTML ön belleği bayt
  değil sayı sınırlı; `update_rows`/`_update_progress` büyük tablolarda karesel.

## Önerilen sıradaki iş
1. Kullanıcı paketi ve modları dener; çıkan sorunlar önceliklidir.
2. Kayıt hatasında metin kaybı düzeltmesi (küçük).
3. `gui/main_window.py` bölünmesi (TECH_DEBT 69, ~2.250 satır).
4. Ürün sahibi yeni bir oyun isterse ilgili format eklentisi (kalanlar: `docs/uyumluluk.md`).
