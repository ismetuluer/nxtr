"""Kontrol kodu yer tutucuları: `⟦1⟧`, `⟦2⟧`, …

Format eklentileri metindeki her kontrol kodunu (renk, değişken, satır biçimi…) sırayla
numaralanmış bir yer tutucuya çevirir. Çevirmen (insan veya makine) yalnızca bu
yer tutucuları görür. Geri yazmadan önce yer tutucuların **sayısı, türü ve sırası**
orijinalle karşılaştırılır; uymayan satır "hatalı" sayılır ve dosyaya yazılmaz.
Aynı numara her zaman aynı kodu gösterdiğinden "tür" denetimi numara denetimiyle yapılır.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

OPEN = "⟦"
CLOSE = "⟧"
TOKEN_RE = re.compile(r"⟦(\d+)⟧")


#: Açıkken `problems` yalnızca kod sırası farkını sorun saymaz (sayı ve tür farkı hâlâ sorundur).
_allow_reorder: ContextVar[bool] = ContextVar("allow_reorder", default=False)


@contextmanager
def tolerate_reorder() -> Iterator[None]:
    """Bu blokta kod sırası farkı sorun sayılmaz; biçim eklentilerinin `inject` denetimi de gevşer."""
    reset = _allow_reorder.set(True)
    try:
        yield
    finally:
        _allow_reorder.reset(reset)


def token(n: int) -> str:
    return f"{OPEN}{n}{CLOSE}"


def tokens_in(text: str) -> list[int]:
    return [int(m.group(1)) for m in TOKEN_RE.finditer(text)]


def split(text: str) -> list[str | int]:
    """Metni düz parçalara ve yer tutucu numaralarına ayırır."""
    out: list[str | int] = []
    pos = 0
    for m in TOKEN_RE.finditer(text):
        if m.start() > pos:
            out.append(text[pos : m.start()])
        out.append(int(m.group(1)))
        pos = m.end()
    if pos < len(text):
        out.append(text[pos:])
    return out


def problems(source: str, translation: str) -> list[str]:
    """Çevirideki yer tutucu sorunlarını Türkçe olarak döndürür (boş liste = sorun yok)."""
    expected = tokens_in(source)
    got = tokens_in(translation)
    issues: list[str] = []
    missing = [n for n in expected if n not in got]
    extra = [n for n in got if n not in expected]
    if missing:
        issues.append("Eksik kontrol kodu: " + " ".join(token(n) for n in missing))
    if extra:
        issues.append("Orijinalde olmayan kontrol kodu: " + " ".join(token(n) for n in extra))
    if not missing and not extra and len(got) != len(expected):
        issues.append("Kontrol kodu sayısı orijinalle aynı değil (bir kod iki kez yazılmış olabilir).")
    if not issues and got != expected and not _allow_reorder.get():
        issues.append("Kontrol kodlarının sırası değişmiş; oyun bunu desteklemeyebilir.")
    stray = translation.count(OPEN) + translation.count(CLOSE) - 2 * len(got)
    if stray:
        issues.append(f"Yarım kalmış yer tutucu işareti var ({OPEN} veya {CLOSE}).")
    return issues


def order_only_problem(source: str, translation: str, is_free: Callable[[int], bool]) -> bool:
    """Tek sorun kod sırası farkı mı ve bu fark güvenle yazılabilir mi?

    Güvenli: serbest sayılan kodlar (`is_free`: ör. değişken, simge; tek başına durur, eşi yoktur) yer değiştirmiş,
    diğer kodların (renk açma/kapama gibi çiftler) kendi aralarındaki sırası aynı kalmış.
    """
    if not problems(source, translation):
        return False
    with tolerate_reorder():
        if problems(source, translation):
            return False
    fixed = [n for n in tokens_in(source) if not is_free(n)]
    return fixed == [n for n in tokens_in(translation) if not is_free(n)]


def renumber(text: str) -> str:
    """Yer tutucuları göründükleri sıraya göre yeniden numaralar (⟦2⟧…⟦1⟧ → ⟦1⟧…⟦2⟧); sıra farkını yok saymak için."""
    count = 0

    def number(_m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return token(count)

    return TOKEN_RE.sub(number, text)


#: Modellerin yer tutucuyu sık bozduğu biçimler: ⟦1⟧ yerine [1], 【1】, ⟦ 1 ⟧, {1}, ⟨1⟩.
_NEAR_MISS = (r"\[\s*{n}\s*\]", r"【\s*{n}\s*】", r"⟦\s*{n}\s*⟧", r"\{{\s*{n}\s*\}}", r"⟨\s*{n}\s*⟩")


def repair(source: str, translation: str) -> str:
    """Eksik yer tutucunun benzer yazımını (ör. `[1]`) asıl biçimine (`⟦1⟧`) çevirir.

    Yalnızca kaynakta bulunup çeviride bulunmayan numaralar için ve kaynakta zaten geçmeyen bir
    yazımla, ilk eşleşmede yapılır; metnin geri kalanına dokunulmaz. Onarımdan sonra her zamanki
    denetim (`problems`) yine uygulanır.
    """
    got = set(tokens_in(translation))
    for n in dict.fromkeys(tokens_in(source)):
        if n in got:
            continue
        for template in _NEAR_MISS:
            pattern = re.compile(template.format(n=n))
            if pattern.search(source):
                continue
            repaired, count = pattern.subn(token(n), translation, count=1)
            if count:
                translation = repaired
                break
    return translation
