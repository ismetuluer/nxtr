"""Kontrol kodu yer tutucuları: `⟦1⟧`, `⟦2⟧`, …

Format eklentileri metindeki her kontrol kodunu (renk, değişken, satır biçimi…) sırayla
numaralanmış bir yer tutucuya çevirir. Çevirmen (insan veya makine) yalnızca bu
yer tutucuları görür. Geri yazmadan önce yer tutucuların **sayısı, türü ve sırası**
orijinalle karşılaştırılır; uymayan satır "hatalı" sayılır ve dosyaya yazılmaz.
Aynı numara her zaman aynı kodu gösterdiğinden "tür" denetimi numara denetimiyle yapılır.

İstisnalar (ürün sahibinin kararları, 2026-11-16 ve 2026-11-17): yalnızca serbest kodların (biçim eklentisinin
`movable_code` ile bildirdiği simge ve adlı değişkenler) ya da bütün olarak taşınan aç/kapa çiftlerinin
(`paired_code`) yeri değiştiyse satır hatalı değildir, uyarıdır (`check`). Biçim eklentilerinin `inject` denetimi
(`problems`) katı kalır; dışa aktarma bu satırları `tolerate_reorder` içinde yazar.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

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


#: Yalnızca serbest kodların yeri değiştiğinde verilen uyarı (satır hatalı sayılmaz, dışa aktarılır).
FREE_REORDER_WARNING = (
    "Değişken veya simge kodlarının yeri orijinalden farklı; oyunda doğru yerde göründüğünü denetleyin."
)
#: Bir aç/kapa çifti bütün olarak yer değiştirdiğinde verilen uyarı (satır hatalı sayılmaz, dışa aktarılır).
PAIR_REORDER_WARNING = (
    "Biçim etiketi çiftlerinin (açılış/kapanış) yeri orijinalden farklı; oyunda doğru göründüğünü denetleyin."
)

#: Çift kodunun rolleri (`paired_code` yanıtının ikinci öğesi).
PAIR_OPEN = "open"
PAIR_CLOSE = "close"
#: Çiftin içinde durması gereken ayraç (ör. çoğul seçenek ayracı `,other=`): çiftle birlikte taşınır, çiftten
#: çıkamaz, aynı çiftteki öteki ayraçlarla sırası değişmez.
PAIR_SEPARATOR = "separator"
PAIR_KINDS = frozenset({PAIR_OPEN, PAIR_CLOSE, PAIR_SEPARATOR})

#: Çift kodunun rolü: (aile adı, `PAIR_OPEN` | `PAIR_CLOSE` | `PAIR_SEPARATOR`). Aynı ailenin açılışı ile kapanışı
#: eşleşir; genel bir kapanış (Unreal `</>`) için eklenti bütün açılışlara aynı aile adını verir.
PairRole = tuple[str, str]


class CodeRoles(frozenset[int]):
    """Satırın kod rolleri: küme olarak serbest kodların numaralarıdır (eski `frozenset[int]` kullanımıyla aynı);
    `pairs` aç/kapa çifti bildirilen kodları (numara → rol) taşır. Serbest kodu olmayan satırda küme boştur ve
    doğruluk değeri yanlıştır; çift olup olmadığına `pairs` ile bakılır."""

    __slots__ = ("pairs",)
    pairs: Mapping[int, PairRole]

    def __new__(cls, free: Iterable[int] = (), pairs: Mapping[int, PairRole] | None = None) -> CodeRoles:
        self = super().__new__(cls, free)
        self.pairs = dict(pairs or {})
        return self

    def __repr__(self) -> str:
        return f"CodeRoles({set(self) or '{}'}, pairs={self.pairs})"


def pairs_of(free: Collection[int]) -> Mapping[int, PairRole]:
    """`free` bir `CodeRoles` ise çift rolleri, değilse boş."""
    return free.pairs if isinstance(free, CodeRoles) else {}


def common_roles(items: Iterable[Collection[int]]) -> CodeRoles:
    """Hepsinde ortak olan roller: hepsinde serbest kodlar ve hepsinde aynı rolle bildirilmiş çift kodları."""
    roles = [(frozenset(i), pairs_of(i)) for i in items]
    if not roles:
        return CodeRoles()
    free = frozenset.intersection(*(f for f, _p in roles))
    first = roles[0][1]
    pairs = {n: r for n, r in first.items() if all(p.get(n) == r for _f, p in roles[1:])}
    return CodeRoles(free, pairs)


@dataclass(frozen=True)
class CodeCheck:
    """Çevirinin kontrol kodu denetimi: `errors` doluysa satır hatalıdır; yalnızca `warnings` doluysa yazılabilir."""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _match_pairs(order: list[int], pairs: Mapping[int, PairRole]) -> dict[int, int]:
    """Kaynakta eşleşen çiftler (açılış → kapanış). Kapanış, yığındaki aynı ailenin en yakın açılışına bağlanır;
    aradaki kapanmamış açılışlar ve eşi bulunmayan kapanışlar çift sayılmaz (katı kalır)."""
    stack: list[int] = []
    matched: dict[int, int] = {}
    for n in order:
        role = pairs.get(n)
        if role is None or role[1] == PAIR_SEPARATOR:
            continue
        family, kind = role
        if kind == PAIR_OPEN:
            stack.append(n)
            continue
        for i in range(len(stack) - 1, -1, -1):
            if pairs[stack[i]][0] == family:
                matched[stack[i]] = n
                del stack[i:]
                break
    return matched


def _parents(order: list[int], opens: Mapping[int, int]) -> dict[int, int] | None:
    """Her kodun içinde durduğu en yakın çiftin açılışı (0 = hiçbiri). Bir kapanış kendi açılışından önce gelir ya
    da çiftler çaprazlanırsa None. `opens`: kapanış → açılış."""
    stack: list[int] = []
    parent: dict[int, int] = {}
    closes = set(opens)
    for n in order:
        if n in closes:
            if not stack or stack[-1] != opens[n]:
                return None
            stack.pop()
            parent[n] = stack[-1] if stack else 0
            continue
        parent[n] = stack[-1] if stack else 0
        if n in opens.values():
            stack.append(n)
    return parent if not stack else None


def _reorder_warning(source: str, translation: str, free: Collection[int]) -> str | None:
    """Tek sorun sıra farkıysa ve bu fark kurala uyuyorsa uyarı metni, değilse None.

    Kural: serbest kodlar (çift bildirilmemiş) her yere gidebilir; kaynakta eşleşen her çift, açılışı kapanışından
    önce, çaprazlanmadan ve aynı üst çiftin içinde kalarak yer değiştirebilir; çiftin ayraçları çiftin içinde ve
    kendi aralarındaki sırada kalır; geri kalan (katı) kodların kendi aralarındaki sırası ve içinde durdukları çift
    değişmez."""
    with tolerate_reorder():
        if problems(source, translation):
            return None
    expected, got = tokens_in(source), tokens_in(translation)
    pairs = pairs_of(free)
    loose = {n for n in free if n not in pairs}
    matched = _match_pairs(expected, pairs)
    opens = {c: o for o, c in matched.items()}
    members = set(matched) | set(opens)
    before = _parents([n for n in expected if n not in loose], opens)
    after = _parents([n for n in got if n not in loose], opens)
    if before is None or after is None:
        return None
    # Ayraç yalnızca kaynakta kendi ailesinden bir çiftin içindeyse çifte bağlıdır; değilse katı bir koddur.
    bound = {
        n for n, role in pairs.items() if role[1] == PAIR_SEPARATOR and before.get(n) and pairs[before[n]][0] == role[0]
    }
    strict = [n for n in expected if n not in loose and n not in members and n not in bound]
    if strict != [n for n in got if n not in loose and n not in members and n not in bound]:
        return None
    if any(before[n] != after[n] for n in before if n not in opens):
        return None  # katı kod, ayraç ya da çift, içinde durduğu çiftten çıkmış/başkasına girmiş
    for parent in {before[n] for n in bound}:
        inside = [n for n in expected if n in bound and before[n] == parent]
        if inside != [n for n in got if n in bound and after[n] == parent]:
            return None
    fixed_before = [n for n in expected if n not in loose]
    fixed_after = [n for n in got if n not in loose]
    return FREE_REORDER_WARNING if fixed_before == fixed_after else PAIR_REORDER_WARNING


def check(source: str, translation: str, free: Collection[int] = frozenset()) -> CodeCheck:
    """Kontrol kodu kararının tek yeri: sorun yok / yalnızca izin verilen sıra farkı (uyarı) / hata.

    `free`: satırın serbest kodlarının numaraları (biçim eklentisinin `movable_code` bildirimi; tek başına durur,
    adıyla ya da kendisi anlam taşır). `CodeRoles` ise ayrıca aç/kapa çiftleri (`paired_code` bildirimi): bir çift
    iç içeliği bozulmadan bütün olarak yer değiştirebilir (ürün sahibinin kararı, 2026-11-17). Eksik, fazla,
    yinelenen kod, çaprazlanan ya da ters dönen çift ve katı kodların (satır/sayfa sonu, konumsal `%s`, eşi olmayan
    etiket) kendi aralarındaki sıra farkı her zaman hatadır. Biçim eklentilerinin `inject` denetimi katı kalır
    (`problems`); dışa aktarma uyarılı satırları `tolerate_reorder` içinde yazar.
    """
    issues = problems(source, translation)
    if not issues:
        return CodeCheck()
    if free or pairs_of(free):
        warning = _reorder_warning(source, translation, free)
        if warning is not None:
            return CodeCheck(warnings=(warning,))
    return CodeCheck(errors=tuple(issues))


def renumber(text: str) -> str:
    """Yer tutucuları göründükleri sıraya göre yeniden numaralar (⟦2⟧…⟦1⟧ → ⟦1⟧…⟦2⟧); sıra farkını yok saymak için."""
    count = 0

    def number(_m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return token(count)

    return TOKEN_RE.sub(number, text)


#: Modellerin yer tutucuyu sık bozduğu biçimler: ⟦1⟧ yerine [1], 【1】, ⟦ 1 ⟧, {1}, ⟨1⟩.
_NEAR_MISS = (
    r"\[\s*{n}\s*\]",
    r"【\s*{n}\s*】",
    r"⟦\s*{n}\s*⟧",
    r"\{{\{{\s*{n}\s*\}}\}}",  # {{1}} önce denenir: tek süslü kalıbı onu yarım bırakırdı
    r"\{{\s*{n}\s*\}}",
    r"⟨\s*{n}\s*⟩",
)


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
