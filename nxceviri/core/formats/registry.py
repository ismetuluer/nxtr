"""Kayıtlı format eklentileri: yerleşikler (buraya eklenerek etkinleşir) ve kullanıcı eklentileri.

Kullanıcı eklentileri açılışta `load_user_plugins()` ile yüklenir (arayüz onay denetimiyle; kullanıcı yeni bir
eklentiyi onaylayınca yeniden yüklenir) ve yerleşiklerden ÖNCE denenir."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from nxceviri.core.archives.access import MemberReader
from nxceviri.core.container.view import ContentTree
from nxceviri.core.errors import NxError
from nxceviri.core.formats import legacy
from nxceviri.core.formats.base import ArchiveFormat, ControlCode, FormatPlugin
from nxceviri.core.formats.detection import KIND_LABELS, FileKind
from nxceviri.core.formats.fmsb import FmsbPlugin
from nxceviri.core.formats.fsdmsg import FsdMsgPlugin
from nxceviri.core.formats.gfmsg import GfMsgPlugin
from nxceviri.core.formats.msbt import MsbtPlugin
from nxceviri.core.formats.nnitext import NniTextPlugin
from nxceviri.core.formats.pakyc import PakYcPlugin
from nxceviri.core.formats.psbtext import PsbTextPlugin
from nxceviri.core.formats.srt import SrtPlugin
from nxceviri.core.formats.unity import UnityPlugin
from nxceviri.core.formats.unreal import LocresPlugin
from nxceviri.core.formats.wadlin import WadLinPlugin
from nxceviri.core.plugins.loader import PluginInfo, PluginReport, TrustCheck, load_plugins
from nxceviri.core.translate.placeholders import PAIR_KINDS, CodeRoles, PairRole

log = logging.getLogger(__name__)

BUILTIN_PLUGINS: tuple[FormatPlugin, ...] = (
    MsbtPlugin(),
    UnityPlugin(),
    LocresPlugin(),
    GfMsgPlugin(),
    PakYcPlugin(),
    FsdMsgPlugin(),
    PsbTextPlugin(),
    NniTextPlugin(),
    FmsbPlugin(),
    SrtPlugin(),
    WadLinPlugin(),
)


#: Açılışta yüklenen kullanıcı eklentileri (yüklenmediyse boş rapor).
_user_report = PluginReport()
#: Tarama sırasında `detect` hatası verip günlüğe yazılmış eklentiler (her biri bir kez bildirilir).
_failed_detect: set[str] = set()
#: (biçim, oyun, ham kod, etiket) → eklentinin `movable_code` yanıtı; kullanıcı eklentileri yeniden yüklenince silinir.
_movable: dict[tuple[str, str | None, bytes, str], bool] = {}
#: (biçim, oyun, ham kod, etiket) → eklentinin `paired_code` yanıtı (geçersiz yanıt None); aynı anda silinir.
_paired: dict[tuple[str, str | None, bytes, str], PairRole | None] = {}
#: (biçim, oyun) → eklenti `movable_code` ya da `paired_code` bildiriyor mu; aynı anda silinir.
_judges: dict[tuple[str, str | None], bool] = {}
#: (biçim, oyun) → eklentinin `forbids_newline` bildirimi (yoksa None); aynı anda silinir.
_newline_rules: dict[tuple[str, str | None], Callable[[str], object] | None] = {}


def load_user_plugins(dirs: Sequence[Path] | None = None, trusted: TrustCheck | None = None) -> PluginReport:
    """Kullanıcı eklentilerini (yeniden) yükler ve kayıt defterine koyar.

    `trusted` (onay denetimi) yalnızca arayüz verir: onaylanmamış kullanıcı eklentisi içe aktarılmaz. Verilmezse
    (komut satırı araçları, kullanıcı bilerek çalıştırır) hepsi yüklenir."""
    global _user_report  # noqa: PLW0603 - uygulama genelinde tek kayıt defteri
    _failed_detect.clear()
    _movable.clear()
    _paired.clear()
    _judges.clear()
    _newline_rules.clear()
    _user_report = load_plugins(dirs, {p.name for p in BUILTIN_PLUGINS}, trusted)
    for info in _user_report.errors:
        log.warning("Eklenti yüklenemedi: %s: %s", info.ad, info.hata)
    for info in _user_report.infos:
        if info.onay_bekliyor:
            log.info("Eklenti onay bekliyor, yüklenmedi: %s (%s)", info.ad, info.yol)
    return _user_report


def reset_user_plugins() -> None:
    """Yüklü kullanıcı eklentilerini bırakır (testler için)."""
    global _user_report  # noqa: PLW0603 - uygulama genelinde tek kayıt defteri
    _user_report = PluginReport()
    _failed_detect.clear()
    _movable.clear()
    _paired.clear()
    _judges.clear()
    _newline_rules.clear()


def user_plugin_report() -> PluginReport:
    return _user_report


def all_plugins() -> tuple[FormatPlugin, ...]:
    """Tüm eklentiler; kullanıcı eklentileri yerleşiklerden önce gelir."""
    return (*_user_report.plugins, *BUILTIN_PLUGINS)


def plugin_for_kind(kind: str, title_id: str | None = None) -> FormatPlugin | None:
    """Tarama raporundaki tür (`ScanEntry.kind`) için eklenti; desteklenmiyorsa None.

    `title_id` verilirse, `oyunlar` sınırı bu oyunu içermeyen kullanıcı eklentileri atlanır ve yerleşik
    biçim kullanılır. Oyun bilinen her yerde (çıkarma, dışa aktarma) verilmelidir. Eski sürümlerin kimlikleri
    (`legacy.FORMAT_IDS`) bugünkü eklentiye çözülür."""
    kind = legacy.format_id(kind)
    for info in _user_report.infos:
        plugin = info.plugin
        if plugin is None or plugin.name != kind:
            continue
        if title_id is None or not info.oyunlar or title_id.upper() in info.oyunlar:
            return plugin
    return next((p for p in BUILTIN_PLUGINS if p.name == kind), None)


def supported_kinds() -> set[str]:
    return {p.name for p in all_plugins()}


def user_plugin_info(kind: str) -> PluginInfo | None:
    """`kind` biçimini sağlayan yüklü kullanıcı eklentisi; yerleşik ya da yoksa None."""
    return next((i for i in _user_report.infos if i.plugin is not None and i.tur == kind), None)


def user_plugins_for(title_id: str) -> tuple[FormatPlugin, ...]:
    """Bu oyunda geçerli (yüklü, `oyunlar` sınırı uyan) kullanıcı eklentileri."""
    return tuple(
        info.plugin
        for info in _user_report.infos
        if info.plugin is not None and (not info.oyunlar or title_id.upper() in info.oyunlar)
    )


def user_plugin_for_file(title_id: str, path: str, head: bytes) -> FormatPlugin | None:
    """Bu dosyayı tanıyan ilk kullanıcı eklentisi (yalnızca eklentinin oyunlarında); yoksa None."""
    for info in _user_report.infos:
        plugin = info.plugin
        if plugin is None or (info.oyunlar and title_id.upper() not in info.oyunlar):
            continue
        try:
            if plugin.detect(path, head):
                return plugin
        except NxError as exc:
            if info.ad not in _failed_detect:
                _failed_detect.add(info.ad)
                log.warning("Eklenti tarama sırasında hata verdi: %s: %s", info.ad, exc.message)
    return None


def archive_formats(title_id: str | None) -> tuple[ArchiveFormat, ...]:
    """Bu oyunda geçerli eklenti arşiv biçimleri (`archive_formats()` kancası), eklenti sırasıyla.

    `oyunlar` sınırı uygulanır; oyun bilinmiyorsa (None) yalnızca her oyunda geçerli eklentilerinkiler."""
    return tuple(
        fmt
        for info in _user_report.infos
        if info.plugin is not None and (not info.oyunlar or (title_id is not None and title_id.upper() in info.oyunlar))
        for fmt in info.arsivler
    )


def all_archive_formats() -> tuple[ArchiveFormat, ...]:
    """Yüklü bütün eklenti arşiv biçimleri, `oyunlar` sınırına bakılmadan (oyunu bilinmeyen klasörü sınayan araç)."""
    return tuple(fmt for info in _user_report.infos if info.plugin is not None for fmt in info.arsivler)


def member_reader(tree: ContentTree) -> MemberReader:
    """Oyun ağacı için arşiv üyesi okuyucusu: yerleşik arşivler ve bu oyunda geçerli eklenti arşivleri."""
    return MemberReader(tree.view, tree.code, archive_formats(tree.title_id))


def kind_label(kind: str) -> str:
    """Tarama türünün Türkçe adı: yerleşik tür, eklenti biçimi ya da (bilinmiyorsa) türün kendi adı."""
    kind = legacy.format_id(kind)
    try:
        return KIND_LABELS[FileKind(kind)]
    except ValueError:
        plugin = plugin_for_kind(kind)
        return plugin.label if plugin is not None else kind


def free_codes(kind: str, codes: Sequence[ControlCode], title_id: str | None = None) -> CodeRoles:
    """Satırın kod rolleri (`⟦n⟧`, 1'den): küme olarak serbest kodların numaraları (çeviride yeri değişebilen, tek
    başına duran kodlar), `pairs` olarak aç/kapa çifti kodlarının rolleri (bütün olarak taşınabilir).

    Biçim eklentisi isteğe bağlı `movable_code(code) -> bool` ve
    `paired_code(code) -> (aile, "open"|"close"|"separator") | None` bildirimleriyle söyler; bildirmeyen eklentide
    (ve tanınmayan biçimde) hiçbir kod serbest ya da çift değildir.
    Projede kodların ham baytı ve etiketi saklandığından eski projelerde de eklentiye sorulur; şema değişmez.
    `title_id`: dosyayı yazan eklentinin seçimi için (`plugin_for_kind`)."""
    kind = legacy.format_id(kind)
    found: set[int] = set()
    pairs: dict[int, PairRole] = {}
    for n, code in enumerate(codes, 1):
        key = (kind, title_id, code.raw, code.label)
        movable = _movable.get(key)
        if movable is None:
            movable = _movable[key] = _ask_movable(kind, title_id, code)
        if key not in _paired:
            _paired[key] = _ask_paired(kind, title_id, code)
        role = _paired[key]
        if role is not None:
            pairs[n] = role
        elif movable:
            found.add(n)
    return CodeRoles(found, pairs)


def judges_codes(kind: str, title_id: str | None = None) -> bool:
    """Biçimin eklentisi `movable_code` ya da `paired_code` bildiriyor mu (bildirmiyorsa satır başına kod sorgusu
    gereksiz)."""
    key = (kind, title_id)
    known = _judges.get(key)
    if known is None:
        plugin = plugin_for_kind(legacy.format_id(kind), title_id)
        known = _judges[key] = any(getattr(plugin, hook, None) is not None for hook in ("movable_code", "paired_code"))
    return known


def forbids_newline(kind: str, key: str, title_id: str | None = None) -> bool:
    """Biçim eklentisi bu satırın çevirisinde gerçek satır sonunu yasaklıyor mu (`forbids_newline(key)` bildirimi)?

    Bildirmeyen eklentide ve tanınmayan biçimde False. Eklentinin kendi hatası kuralı yok sayar (günlüğe yazılır)."""
    rule_key = (kind, title_id)
    if rule_key not in _newline_rules:
        _newline_rules[rule_key] = getattr(plugin_for_kind(legacy.format_id(kind), title_id), "forbids_newline", None)
    rule = _newline_rules[rule_key]
    if rule is None:
        return False
    try:
        return rule(key) is True
    except Exception as exc:  # kullanıcı eklentisinin hatası projenin açılmasını engellememeli; kural yok sayılır
        log.warning("Eklentinin satır sonu bildirimi hata verdi (%s, %s): %s", kind, key, exc)
        return False


def _ask_movable(kind: str, title_id: str | None, code: ControlCode) -> bool:
    judge = getattr(plugin_for_kind(kind, title_id), "movable_code", None)
    if judge is None:
        return False
    try:
        return judge(code) is True
    except Exception as exc:  # kullanıcı eklentisinin hatası projenin açılmasını engellememeli; kod katı sayılır
        log.warning("Eklentinin kod bildirimi hata verdi (%s, %s): %s", kind, code.label, exc)
        return False


def _ask_paired(kind: str, title_id: str | None, code: ControlCode) -> PairRole | None:
    judge = getattr(plugin_for_kind(kind, title_id), "paired_code", None)
    if judge is None:
        return None
    try:
        role = judge(code)
    except Exception as exc:  # kullanıcı eklentisinin hatası projenin açılmasını engellememeli; kod katı sayılır
        log.warning("Eklentinin çift bildirimi hata verdi (%s, %s): %s", kind, code.label, exc)
        return None
    if role is None:
        return None
    if isinstance(role, tuple) and len(role) == 2 and isinstance(role[0], str) and role[1] in PAIR_KINDS:
        return (role[0], role[1])
    log.warning("Eklentinin çift bildirimi geçersiz (%s, %s): %r", kind, code.label, role)
    return None
