tr.bloom — Türkçe yazım denetimi süzgeci
========================================

Bu dosya, TDD (Turkish Data Depository) grubunun hunspell-tr sözlüğünden (https://github.com/tdd-ai/hunspell-tr,
tr_TR.aff + tr_TR.dic) türetilmiştir. Sözlükteki ~6,1 milyon sözcük biçimi (kök + geçerli ekler) Türkçe küçük harfe
çevrilip bir Bloom süzgecine yazılmıştır (yanlış olumlu oranı %0,1). Sözlüğün kendisi pakete konmamıştır.

Lisans: Mozilla Public License 2.0 (MPL-2.0). Tam metin: LICENSE-MPL-2.0.txt. MPL-2.0'ın 3.2 maddesi uyarınca
türetilmiş dosyanın kaynağı yukarıdaki adresten edinilebilir; süzgeci üreten betik `packaging/build_spell_filter.py`.
Bu dosya MPL-2.0 kapsamındadır; uygulamanın kalanı bu lisansa bağlı değildir.
