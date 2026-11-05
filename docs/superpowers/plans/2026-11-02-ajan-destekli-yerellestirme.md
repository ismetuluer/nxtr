# Ajan destekli yerelleştirme — uygulama planı

> Yürütme: Opus şef + Sonnet işçiler (ürün sahibinin seçtiği düzen); her işçi kendi worktree'sinde
> (`.claude/worktrees/w-<ad>`, dal `isci/<ad>`), ortak kurallar `.claude/worktrees/isci-ortak-kurallar.md`.

**Spec:** `docs/superpowers/specs/2026-11-02-ajan-destekli-yerellestirme-design.md`

**Hedef:** Başka kullanıcıların kendi ajanlarıyla yeni oyunları çözebileceği yapı: AGENTS.md + rehberler + araçlar +
kullanıcı eklentisi yükleyici + anahtarsız güncelleme + açık depo hazırlığı.

## Genel kısıtlar

- CLAUDE.md §2 yasal sınırlar tüm görevlerde geçerli; araçlar anahtar içeriğini asla yazmaz/loglamaz.
- Sürüm/CHANGELOG/ARCHITECTURE/HANDOFF/README şefte. Lisans: MIT.
- Arayüz Türkçe ve sade (yeni kalıcı düğme yok; menüler).
- Spec'teki aşamalar (1–5) tek sürümde (0.48.0) birleşir; aşama 6 (depoyu açma) ürün sahibinin ayrıca onayıyla.
  Gerekçe: işler paralel yürüyor; ayrı sürümler yalnızca bekleme ekler.

## Görevler

### Görev A — Belgeler (aşama 1 + 5): `isci/belge`
AGENTS.md (kurallar, görev yönlendirme tablosu, komutlar, kullanıcı profili), CLAUDE.md = `@AGENTS.md` + sahip notları,
GEMINI.md, `docs/yol-haritasi.md` (CLAUDE.md §8 ve sahibin kararları), `docs/rehber/` (baslarken, yeni-oyun,
eklenti-yazma, font, grafik, sorun-giderme, katki), `docs/formats/README.md` dizini, `docs/istemler.md`, skill'ler
(`.claude/skills/nxtr-*/SKILL.md` ve `.agents/skills/` kopyası), `eklentiler/README.md` + `.gitignore`.
Tüketir: B ve C'nin komut adları ve yolları (aşağıdaki arayüzler).

### Görev B — Araçlar (aşama 2): `isci/arac`
`nxceviri/arac/` paketi, `python -m nxceviri.arac <komut>`; komutlar `teshis`, `ara`, `dogrula`. GUI: Metinleri Tara →
Daha Fazla → "Teşhis Raporu Oluştur".
Üretir: `nxceviri/arac/__main__.py` argparse; her komut modülü `def ekle(sub) -> None` ile kaydolur, liste
`nxceviri/arac/__init__.py` içinde `KOMUT_MODULLERI: tuple[str, ...]`.

### Görev C — Eklenti yükleyici (aşama 3): `isci/eklenti`
`nxceviri/core/plugins/` (keşif, `eklenti.toml` doğrulama, `EKLENTI_API = 1`, yükleme raporu), kayıt defterine
entegrasyon (kullanıcı eklentisi önce), Yardım → Eklentiler penceresi ("Eklenti Ekle…" zip/klasör), projeye eklenti adı +
sürüm kaydı ve uyarı, `eklenti-olustur` ve `eklentiler` komutları (`nxceviri/arac/` içine B'nin düzeniyle).
Üretir: `user_plugin_dirs() -> list[Path]` (`%LOCALAPPDATA%\NXCeviri\eklentiler` + kaynak kurulumda depo `eklentiler/`),
`load_plugins() -> PluginReport`, kayıt defterinde tüm eklentileri veren tek işlev.

### Görev D — Güncelleyici (aşama 4): `isci/guncelle`
Anahtarsız GitHub denetimi (depo açılana kadar anahtar varsa onu kullanır), Ayarlar → "Açılışta güncellemeleri denetle",
exe için indir + SHA-256 doğrula + yardımcıyla değiştir + yeniden aç + başarısızsa geri al; release iş akışı SHA-256
dosyası yayımlar; değişiklik notu.

### Görev E — Açılış denetimi (aşama 6, yalnızca rapor): `isci/acilis`
Depo ve git geçmişinde oyun içeriği, gizli bilgi, kişisel yol taraması; bulgu raporu + önerilen temizlik. Depo
görünürlüğü DEĞİŞMEZ, geçmiş yeniden yazılmaz.

### Şef
Birleştirme, gözden geçirme (Opus), LICENSE (MIT), README "Yapay zekâ ajanıyla kullanım", belgeler, 0.48.0 yayımı;
aşama 3 provası (temiz klasörde yalnızca istem kartıyla bir ajan).
