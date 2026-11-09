# eklentiler/

Bu klasör, **kaynak koddan çalıştırırken** kendi yazdığınız metin biçimi eklentilerinin geliştirme yeridir. Her eklenti
bir alt klasördür:

```
eklentiler/<ad>/
    eklenti.toml   ad, surum, yazar, oyunlar (TitleID listesi), aciklama (isteğe bağlı), api = 1
    plugin.py      detect / extract / inject (docs/rehber/eklenti-yazma.md)
    tests/         elle üretilmiş örnekle bayt bayt round-trip testi
    NOT.md         biçim notu
```

## Nasıl kullanılır
- İskelet üretmek: `python -m nxceviri.arac eklenti-olustur <ad>`
- Yüklü eklentileri ve yükleme hatalarını görmek: `python -m nxceviri.arac eklentiler`
- Gerçek oyun dosyasında doğrulamak: `python -m nxceviri.arac dogrula <ad> <oyun dosyaları>`
- Uygulamada: **Araçlar → Eklentiler**. Hazır `NXTR.exe` paketinde eklentiler
  `%LOCALAPPDATA%\NXCeviri\eklentiler\` klasöründen yüklenir; buradaki klasörü oraya kopyalayarak aynı eklentiyi
  pakette de kullanabilirsiniz (yalnızca paketle gelen kütüphaneler kullanılabilir).

Adım adım rehber: `docs/rehber/yeni-oyun.md` ve `docs/rehber/eklenti-yazma.md`.

## Git'e girmez
Bu klasördeki her şey (bu README hariç) `.gitignore` ile dışlanır: eklentiniz size aittir ve paylaşmak zorunda değilsiniz.
Paylaşmak isterseniz `docs/rehber/katki.md`. Eklenti kod çalıştırır ve korumalı alanı yoktur: başkasından aldığınız
eklentinin `plugin.py` dosyasını çalıştırmadan önce okuyun. Eklentiye anahtar (`prod.keys`) ya da oyun dosyası koymayın.
