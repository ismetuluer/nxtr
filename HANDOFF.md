# HANDOFF — oturum devri (2026-11-18, 0.65.1)

## Durum
- **Sürüm 0.65.1** (2026-11-18; CHANGELOG 0.65.1): açılış titremesi düzeltildi. Ebeveynsiz
  widget'a `setVisible(True)` bir anlığına üst düzey pencere açıyordu (`widgets.Card` başlık satırı,
  `MainWindow.nav_header`); görünürlük ebeveyne bağlandıktan sonra ayarlanıyor. Bekçi: `tests/test_acilis_pencere.py`.
- **Sürüm 0.65.0** (2026-11-17; CHANGELOG 0.65.0): eklenti arşiv kancası `archive_formats()` → `ArchiveFormat`
  (`core/formats/base.py`; `registry.archive_formats`, `registry.member_reader`, `GuardedArchiveFormat`; ARCHITECTURE
  228), güncelleme TitleID'li dosyaların ana ağaca yazılması (229), `path_language` (230). Kullanıcının bir oyun
  eklentisi bu kancalarla kendine yeterli hâle getirildi (eklenti depoda değil, kullanıcı klasöründe).
- **Sürüm 0.64.1** (2026-11-17; CHANGELOG 0.64.1): eklenti içe aktarma denetimi `core/plugins/imports.py`
  (`ALLOWED_MODULES`, `audit_plugin`; ARCHITECTURE 227), grafik klasörü `derived.TURKISH_DIR`/`turkish_dir`
  (226), AGENTS.md §1 ana koda yazma yasağı ve mazeretsiz teslim; `yeni-oyun.md` "Bağlayıcı kurallar".
- **Sürüm 0.64.0** (2026-11-17; CHANGELOG 0.64.0): yol haritasının (docs/yol-haritasi.md) 1–2. aşaması. Ana pencere
  `gui/checks_controller.py` ve `gui/export_controller.py`'ye bölündü (ARCHITECTURE 221; pencere ince yönlendirmeler
  taşır, testler bunlara erişir). Kod çiftleri `paired_code` + `placeholders.CodeRoles` (219), Unreal çoğul (220),
  sağlayıcı kaydı şema 7 `mt_provider/mt_model` (222), pano eksikleri (223), `FormatPlugin.languages` (I2),
  `gui/scale.py` ölçek, `gui/motion.fade_in`. `tests/conftest.py` riskli düzeltme onayına kendiliğinden "Evet" der.
  Ana pencere dört denetleyiciye bölündü (221): `checks_controller`, `export_controller`, `project_controller`,
  `machine_controller`. Dışa aktarma satır bazlıdır (224): biçimin kabul etmediği ya da kaynağı oyun dosyasından
  farklı okunan satır yalnızca kendisi orijinal kalır (`ExportResult.rejected_ids`, `STALE_SOURCE_REASON`; bildirim ve
  bilgi dosyasında listelenir). Satır sonu kuralı (225): eklentinin `forbids_newline` bildirimi (Kontrol Et "Satır
  sonu" hatası, dışa aktarılmaz). I2 dil listesi kaydın `detail` ekindedir; karşılaştıran kod `scanner.base_detail`
  kullanır.
  Kalan borçlar koşula bağlı (gerçek oyun, cihaz, model); listesi yol haritasında.
- **Sürüm 0.63.0** (2026-11-17; CHANGELOG 0.63.0): Kontrol Et bekleme görünümü (`widgets.BusyState`; `qa_page` yığın,
  `mark_checking`/`stop_checking`; `checks_controller.run_full_check`, `stop_checks`, `CHECK_PROGRESS_S` (pencerede
  yalnızca yönlendirmeler);
  `checks.run_checks(progress=)`). Aday seçimi (`asciitr.fold`/`apply_choice`, `QaIssue.choices`,
  `checks_controller.apply_ascii_choice`) ve yok sayma (`core/qa/ignored.py`; süzgeç tek yerde
  `checks_controller.show_check_results` ve `_replace_board_rows`; `qa_page.active_issues`/`all_issues`, `issue_kinds.IGNORED_KIND`). Tam test seti 2748
  geçti; gerçek proje kopyasında ölçüldü. İki bilinen sorun (yok sayılan bulgunun Çevir işareti, Düzelt sonrası
  denetim durdurulunca eskimiş bulgular) 0.64.0'da giderildi.
- **Sürüm 0.62.0** (2026-11-17; CHANGELOG 0.62.0): Düzelt (`core/qa/fixrun.py` `plan_for_issues`/`plan_for_rows`;
  `checks_controller.apply_fixes`, `recheck_board_rows(keep_terms)`, `recheck_board_later` arka plan; `qa_page`
  `_scope_plan`, `mark_checking`). Yazım önerisi (`core/spell/suggest.py`; `gui/spell_window.py` Öneri sütunu, toplu
  düzeltme onay penceresi; `UnknownWordCache.row_ids`). Serbest kod sırası (`placeholders.check -> CodeCheck`,
  eklenti `movable_code`, `registry.free_codes`/`judges_codes`, `TranslationRow.free_codes`, QA türü `code_order`,
  `layeredfs.settle_rows`). Tam test seti 2714 geçti; Düzelt ve yazım süreleri gerçek proje kopyasında offscreen
  ölçüldü. Bilinen: toplu yazım düzeltmesinin örneklemde ~%25 şüpheli önerisi var (onay penceresi + Geri Al; ürün
  sahibi böyle kalsın dedi); Yazım penceresinin açılış taraması büyük projede ~3,5 sn; Unreal `{N}|plural` eki
  serbest sayılmaz.
- **Sürüm 0.61.0** (2026-11-16; CHANGELOG 0.61.0): Yinele (`core/project/store.py` `_redo`, `redo`, `redo_job`,
  ortak `_apply_step`; `main_window.redo_last`; yeni yazım `_push_undo` içinde yinele yığınını boşaltır; geçmişe işin
  kendi adıyla yazılır). Kod ekleme kısayolları (`gui/editor_pane.py` `insert_code`, `bind_code_keys`,
  `EditorPane.insert_code_for_row`; `translate_page._table_code_key`; kısayollar `WidgetShortcut` bağlamlı,
  düzenleyici kapanınca kayıttan düşer). Sayfa geçişi Alt+1…5. Tam test seti 2647 geçti. Gerçek pencerede ve
  gerçek Türkçe klavyede denenmedi. Bilinen: `QTest.keyClicks` ile ASCII dışı harf yazan test Windows'ta süreci
  çökertebiliyor; geri alma çeviri belleğine dokunmaz (geri alınan çeviri bellekte kalır).
- **Sürüm 0.60.0** (2026-11-16; CHANGELOG 0.60.0): ad temizliği (belgeler, arayüz, kod, testler, eski sürüm notları);
  biçim kimlikleri `wadlin`, `fsdmsg`, `pakyc`, `nnitext`, `psbtext`; motor anahtarları `psb`, `nni`, `cpk`, `wad`,
  `lms`, `gfmsg`; eski değerler `core/formats/legacy.py` ile okuma anında çözülür (`core/project/store.py` sınırında),
  proje dosyası dönüştürülmez. Paketteki hazır çeviri verisi çıktı (`fontpatch/fsdmsg_userdata.py`,
  `NXCEVIRI_FSD_GRAFIK` klasöründe `resim_yazilari.json` ve `aciklamalar.json`). Tablo rolleri
  `gui/table_roles.py`; `key_names` yalnızca koleksiyonlu biçimlerde bağlam sonunu ad sayar; süre testleri
  `tests/perf.py`. Tam test seti 2601 geçti. Gerçek pencerede denenmedi; paketlenmiş sürüm kurulmadı.
  Kalan adlar bilerek duruyor: `legacy.py` ve testi, oyunun kendi RomFS yolları, testlerdeki TitleID'ler.
- **Sürüm 0.59.0** (2026-11-16; CHANGELOG 0.59.0): Çevir'de simgeli durum süzgeci (`gui/status_filter.py`), "Tümü"
  bütün süzgeçleri kaldırır, arama Türkçe harf duyarsız (`core/translate/textsearch.py` `fold_search`), grup işlevi
  yalnızca Unity/Unreal'da koleksiyon kullanır (`core/project/store.py` `COLLECTION_FORMATS`, `in_collection`),
  gruplu görünüm (`gui/group_proxy.py`, `gui/group_header.py`; komut `view.grouped`, ayar `translate/grouped`).
  Tam test seti 2535 geçti. Gerçek pencerede ve gerçek projede denenmedi. Bilinen, dokunulmamış sorunlar:
  `fitconfig.py` `key_names` bağlamın son parçasını her biçimde
  anahtar adı sayıyor; `FIND_SPANS_ROLE` ile `STATUS_ROLE` aynı rol numarasını paylaşıyor (bugün zararsız).
- **Sürüm 0.58.3** (2026-11-15; CHANGELOG 0.58.3): kullanıcı eklentilerinde onay (`core/plugins/trust.py`,
  `core/plugins/loader.py` `plugin_fingerprint` ve `trusted`, `gui/plugin_approval.py`; onaylar
  `%LOCALAPPDATA%\NXCeviri\eklenti_onaylari.json`), kaydedilmemiş değişiklik sorusu Evet / Hayır / İptal
  (`main_window.py` `build_save_box`, `ask_save_changes`), boş Oyunu Ekle ekranında "Son projeler" kartı,
  `sd_kontrol.py` ve `SD Kontrol.bat` kaldırıldı, iki süre testi en iyi ölçüme bakıyor. Tam test seti 2448 geçti.
  Gerçek pencerede denenmedi (onay sorusu, kaydetme sorusu, son projeler kartı); `gui/app.py` içindeki onay
  bağlantısının testi yok. Testlerde pencere soruları `MainWindow.ask_...` yöntemleriyle sürülür;
  `QMessageBox.question` yaması `exec()` ile açılan kutuları etkilemez, test asılır. Yol haritasında açık kalan iki
  madde "istenirse" (`docs/yol-haritasi.md`).
- **Sürüm 0.58.2** (2026-11-15; CHANGELOG 0.58.2): görsel denetim 8, 11–14, 16 ve Metinleri Tara sütunları kapandı
  (`theme.py` sekme kuralları ve `row_alt`, tablolarda `setDefaultAlignment`, `statusbar.py` kısa/uzun etiket kararı
  `_refit`, `scan_page.py` `Disclosure` ile kanıtlar, `export_page.py` hedef satırı). Tam test seti 2409 geçti.
  Gerçek pencerede denenmedi. Sıradakiler ürün sahibinin kararını bekliyor: boş "Oyunu Ekle" ekranı (öneri: son
  projeler), yazım denetiminde kesme işaretli sözcükler; içerikten dil okuma ertelendi (`docs/yol-haritasi.md`).
- **Sürüm 0.58.1** (2026-11-14; CHANGELOG 0.58.1): Sorunlar'da sağ tık sıralaması (`IssueModel.set_sort`, ayar
  `qa/sort`), bulgu satırında kod çipleri (`IssueRowDelegate`, `marked_html` + sınırlı önbellek), terim denetiminde
  `turkish_lower` (`core/qa/checks.py`, `core/qa/autofix.py`), Dışa Aktar ve Kontrol Et ipuçları
  (`tests/test_page_tips.py`). Tam test seti 2383 geçti. Gerçek pencerede denenmedi. Sıradaki: Metinleri Tara'da
  eklentinin bulduğu dil ve dar pencerede kırpılan sütunlar; Kontrol Et sekme çubuğu ürün sahibinin tasarım onayını
  bekliyor (`docs/yol-haritasi.md`).
- **Sürüm 0.58.0** (2026-11-14; CHANGELOG 0.58.0): ürün sahibinin 0.57.2 geri bildirimi üzerine Kontrol Et → Sorunlar
  yeniden kuruldu (`gui/issue_kinds.py` tür listesi, `gui/issue_rows.py` bulgu satırları, bağlama göre düzeltme
  çubuğu) ve Metinleri Tara'ya dosya seçimi, dil sütunu, kaldırma onayı, ipuçları eklendi (`core/pipeline.py`
  `only_paths`, `Project.translated_counts_by_file`). Tam test seti 2371 geçti. Gerçek pencerede denenmedi. Bilinen
  sınırlar: Sorunlar listesinde kontrol kodları düz `⟦n⟧`; Metinleri Tara'da dil yalnızca dosya yolundan okunur ve
  seçim projede saklanmaz (varsayılan, projedeki dosyalardan türetilir). Sıradakiler: `docs/yol-haritasi.md`.
- **Sürüm 0.57.2** (2026-11-14; görsel düzeltmeler, CHANGELOG 0.57.2): ürün sahibinin ekran görüntülerinden çıkan
  görsel denetimin hata düzeyindeki yedi bulgusu kapandı (oklar, seçenek düğmesi, kırpılan başlık/sütunlar, yinelenen
  "kapalı" satırı, çift kaydırma); kenar çubuğundaki odak çerçevesi kaldırıldı. Tam test seti 2312 geçti. Kalan tasarım
  iyileştirmeleri: `docs/yol-haritasi.md` "Görsel denetim bulguları" 8–16. Ekran görüntüsü almak için uygulama ekrana
  gösterilmeden kurulup `grab()` ile çizdirilebilir (proje `Project.open_copy` ile bellekte; `QT_QPA_PLATFORM` tanımsız).
- **Sürüm 0.57.1** (2026-11-14; denetim turu, CHANGELOG 0.57.1): veri güvenliği düzeltmeleri (kurtarma kopyası, panel metni kaybı, Farklı Kaydet,
  bağlantı sızıntısı, yarıda kalan dışa aktarma yedeği, göç yedeği), kapatma sırası, görünür klavye odağı ve AA
  kontrast, ekran okuyucu adları, bildirim kartı teması, oyun simgesi (PUA) karakterlerinin çizimi, Sığdırma ayarı
  değişince anında denetim, `arac font` komutu ve rehberlerde zorunlu font adımı, arayüz metinlerinin sadeleşmesi.
  Tam test seti 2277 geçti, ruff/mypy temiz. **Ekranda denenmeyenler:** kapatma, bildirim kartı, ekran okuyucu,
  anında sığdırma denetimi, yeni metinler. Ürün sahibi 2026-11-14'te "yayınla" dedi; master'a gönderildi. Ertelenenler:
  `docs/yol-haritasi.md` "Sonraki yapılacaklar".
- **Sürüm 0.57.0** (2026-11-13): toplu düzeltmeler — bildirim kartları kaybolur, Kontrol Et proje değişince sıfırlanır, menüde Ctrl/Shift, satıra tam kaydırma, büyük tabloda gecikmeli arama, kopyalanan sözcük işaretleme, Ollama takılan satırı atlar, kontrol kodu zarfı onarımı, "Türkçe harf eksik" denetimi. ARCHITECTURE §4.47, TECH_DEBT 92. Yayımlandı (v0.57.0, 2026-11-13).
- **Sürüm 0.55.1** (2026-11-09): modelin çeviriye anahtar adı eklemesine (`/(ursa_desc)`) karşı savunma (anahtar sözcük ipucu olarak gider, yabancı belirteç/satır sonu denetimi, dışa aktarmada yapı geri okuması), arama yalnızca Orijinal+Çeviri, Çevir sayfasında başlık yok, üç temizlik seçeneği düzeltme türü oldu (`FitOptions` kalktı), dışa aktarma uyarısında orijinal kalan satırlar No ile listelenir. ARCHITECTURE §4.43, TECH_DEBT 91. **Yayımlanmadı** (`ozellik/sorun-savunma` dalı; "yayınla" bekleniyor).
- **Sürüm 0.55.0** (2026-11-09): G aşaması — maskot (`gui/mascot.py`; dururken logodaki gibi, olayda gözler sekerek yüz kurar; durum çubuğu, kartlar, boş ekranlar; Ayarlar → Görünüm'den kapanır), Yardım penceresi (F1, `gui/help/*.md`, aranabilir, Kısayollar güncel tuşlardan), katkı rehberi (fork/dal/dogrula/PR, çoklu kopya ve ajan, çakışan eklentiler); ayrıca Bul ve Değiştir kare düzen (0.54.0'a girdi). ARCHITECTURE §4.42, TECH_DEBT 90. A–G yol haritası bitti. **Yayımlanmadı** (0.54.0 ve 0.55.0 `ozellik/kimlik-yardim` dalında; "yayınla" bekleniyor).
- **Sürüm 0.54.0** (2026-11-09): F aşaması — dolu klasörde Üzerine Yaz / Başka Klasör (yalnızca NXTR modu silinir, yedekli), font "Ne yapılabilir" sütunu, serbest TTF/OTF fontu dışa/içe aktarma (modda özgünün yerine), Dışa Aktar → Görseller (NNI arşivi). ARCHITECTURE §4.41, TECH_DEBT 89. **Yayımlanmadı:** ürün sahibi "yayınla" diyene kadar master/push/release yok. Sıradaki: G (maskot, yardım, katkı rehberi).
- **Sürüm 0.53.0** (2026-11-09): E aşaması — Terminoloji (ad, sade pencere, kısa hatalar, kitaplık, seçili satırları ekleme, örtük terimler Ollama'ya). ARCHITECTURE §4.40. Sıradaki: F (dışa aktarma, font, grafik).
- **Sürüm 0.52.1** (2026-11-09): A–D hedef/sonuç kıyasındaki eksikler kapandı (Denetle arka planda, sonuç bildirimleri, Otomatik Çeviri sadeleşti, Düzeltirken temizle tek yerde, kod türü uyarısı). ARCHITECTURE §4.39. Bilinçli bırakılan: Ayarlar'da "Genel" sayfası (içerecek ayar yok). Sıradaki: E (Terminoloji).
- **Sürüm 0.52.0** (2026-11-09): D aşaması — bildirim merkezi (kart, Windows bildirimi, ses, görev çubuğu, geçmiş; Ayarlar → Bildirimler), iş sonu sarı kutusu kalktı, güncelleme bildirimi, değişiklikler penceresinde kaydırma/yerinde düzenleme/bağlam, talimat kitaplığı, desen kapsamı, yarım yanıtta bölme. ARCHITECTURE §4.38. Kalan: TECH_DEBT 84 (Denetle arka plana), 87, 88. Sıradaki: E (Terminoloji).
- **Sürüm 0.51.0** (2026-11-10): C aşaması — anlık denetim, Sorunlar panosu, Yazım Denetimi (F7), terim tutarsızlığı, grup/anahtar sınırları; güncelleme yardımcısı düzeltildi (0.48–0.50 bir kez elle güncellenmeli); Ollama şablon denetimi ve iş başına `num_ctx`. ARCHITECTURE §4.37. Sıradaki: D (Otomatik Çeviri + bildirimler). Gerçek pencerede ve gerçek Ollama'da elle denenmedi.
- **Sürüm 0.50.0** (2026-11-09): B aşaması — menü çubuğu, Ayarlar penceresi (`Ctrl+,`), düzenlenebilir kısayollar, gruplu sağ tık menüsü, taşınabilir Bul ve Değiştir penceresi, isteğe bağlı hatalı satır vurgusu; ARCHITECTURE §4.36. Sıradaki: C (anlık denetim + Sorunlar panosu). Gerçek pencerede elle denenmedi.
- **Sürüm 0.49.0** (2026-11-09): kullanılabilirlik incelemesi A aşaması — Çevir ekranı (`docs/inceleme/2026-11-09-kullanilabilirlik.md`); ARCHITECTURE §4.35. Sıradaki: B (menüler, Ayarlar, kısayollar), C (anlık denetim + Sorunlar panosu).
- **Sürüm 0.48.0** (2026-11-06): ajan destekli yerelleştirme — AGENTS.md + docs/rehber + skill'ler + istem kartları, araçlar (nxceviri/arac: teshis/ara/dogrula/eklenti-olustur/eklentiler), kullanıcı eklentileri (core/plugins, Yardım → Eklentiler), anahtarsız + kendiliğinden güncelleme (core/selfupdate), MIT LICENSE + THIRD_PARTY_NOTICES, FSD/MSG metni özetle; ARCHITECTURE §4.34. Depo temiz geçmişle yeni depoya (ismetuluer/nxtr) taşındı. Açık: aşama 3 provası (temiz klasörde istem kartıyla ajan).
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
  0.39.0 başka oturumun NNI arşivi işidir (§4.25, TECH_DEBT 71–76).
- **Sıradaki paketler (ürün sahibinin istek listesi):** 6) NXTR adı ve Joy-Con'dan esinli kırmızı/beyaz logo (önce 2–3 taslak); menülerle ilgili
  itirazların ayrıntısı kullanıcıya soruldu, yanıt bekleniyor.
- **Sürüm 0.38.0 yayımlandı** (2026-11-01): `master` GitHub'a gönderildi, CI yeşil, release `v0.38.0` ve
  `NXCeviri-0.38.0-windows.zip` hazır. Depo ürün sahibinin kararıyla **gizli** kalıyor (geçmişte oyunun İngilizce
  düşman açıklamaları var); paylaşım depoya davetle. Depoda lisans dosyası yok.
- **0.38.0:** uygulama simgesi (`nxceviri/gui/appicon/`, `packaging/make_icon.py`); CI düzeltmeleri — testlerde mypy
  hataları, offscreen testlerin Windows yazı tiplerini görmesi (`QT_QPA_FONTDIR`). Yerelde CI'ın yaptığı gibi
  denetlemek için: `ruff check .`, `ruff format --check .` (Markdown kod blokları dahil), `mypy` (testler dahil).
- **Arayüz yenileme (0.32–0.37) bitti:** metin sığdırma (satır/sayfa sınırı, otomatik bölme, kod türleri),
  simge sistemi + kenar çubuğu + durum çubuğu, çeviri sayfası (altta/sağda düzenleme paneli, sembolleri göster/gizle,
  hiza, kod çipleri), diğer dört sayfada başlık eylemleri ve durum çipi. Ayrıntı: CHANGELOG, ARCHITECTURE §4.20–4.24,
  tasarım belgeleri `docs/superpowers/specs/2026-10-3*`, `2026-11-01-*`.
- **0.36.0 (başka oturum):** NNI arşivi ve CPK/FMSB biçimi metin eklentileri (TECH_DEBT 71–73).
- **Taşınabilir paket Windows'ta denendi (2026-11-01; ürün sahibi akışı onayladı):** master'ın temiz kopyası geçici bir klasörde, CI ile aynı
  adımlarla (Python 3.13, `pip install .`, PyInstaller 6.22.3, `packaging/NXCeviri.spec`) derlendi: 137 MB onedir
  klasör. `NXCeviri.exe` açıldı, 0.37.0 başlatıldı, `prod.keys`/`title.keys` okundu (günlükte hata yok). Pakette Qt
  Windows/SVG eklentileri, `qtbase_tr.qm`, simgeler, `nxceviri` modüllerinin tamamı, fontTools tabloları,
  `keyring.backends.Windows` + `win32ctypes`, httpx, zstandard, UnityPy var. Derleme uyarıları zararsız
  (`pycparser.lextab/yacctab`, UnityPy ses için `fmod.dll`). Ekran üstünden tıklayarak deneme **yapılmadı**
  (kullanıcı ekran denetimi iznini vermedi) — bkz. TECH_DEBT 70.
- Yığın: Python 3.13, PySide6-Essentials, cryptography, zstandard, UnityPy, httpx, keyring, fonttools, lz4, Pillow
  (gerekçeler ARCHITECTURE.md).

## Kullanıcının yapacağı testler
- **Paket (M9):** paketlenmiş `NXTR.exe` → oyun ekle → tara → aktar → (Ollama ya da DeepL ile)
  birkaç satır çevir → Kontrol Et → Dışa Aktar. DeepL anahtarını kaydetmek Kimlik Bilgisi Yöneticisi'ni dener.
- **Cihaz/emülatör:** denenmemiş modlar — PSB (TECH_DEBT 62–64), bir Unity oyunu (65), NNI / CPK/FMSB (71),
  bir Unity oyununun font yaması (M5/M8 bitme ölçütü).

## Bilinen hatalar ve ertelenenler
- Veritabanı yazımı başarısız olursa pencere kapanırken panelde kaydedilmemiş metin kaybolur (nadir).
- Arayüz incelemelerinden ertelenen küçükler: Font/Sığdırma sekme açıklaması boş etiketin ipucunda; çip metin sınırı
  40 (tasarım ~30); koyu temada çip penceresi gövde rengi; `_set_wrap` görünümü iki kez yeniler; HTML ön belleği bayt
  değil sayı sınırlı; `update_rows`/`_update_progress` büyük tablolarda karesel.

## Önerilen sıradaki iş
1. Kullanıcı paketi ve modları dener; çıkan sorunlar önceliklidir.
2. Kayıt hatasında metin kaybı düzeltmesi (küçük).
3. `gui/main_window.py` bölünmesinin kalanı (TECH_DEBT 69, ~3.370 satır; dört denetleyici ayrıldı).
4. Ürün sahibi yeni bir oyun isterse ilgili format eklentisi (kalanlar: `docs/uyumluluk.md`).
