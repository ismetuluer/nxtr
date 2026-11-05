"""Çeviri tablosunun TXT veya XLSX (Excel) olarak dışa ve içe aktarılması (dış redaksiyon ve dış çeviri).

**Redaksiyon TXT (varsayılan):** UTF-8 (BOM'lu), sekme ayraçlı, dört sütun: `orijinal`, `çeviri`, `düzeltme`,
`grup`. **Redaksiyon XLSX:** Excel'de açılan, aynı dört sütunlu çalışma sayfası.
**Çeviri TXT/XLSX:** Aynı düzen, ancak üçüncü sütunun adı `yeni çeviri`; dış çevirmen/model yalnızca bu sütunu
doldurur. İki biçimde de boş bırakılan satırın mevcut çevirisi olduğu gibi kalır.
`grup` (ör. “UI”, “Dialogue”) yalnızca bağlamdır: redaksiyon modeli metnin menü mü, konuşma cümlesi mi olduğunu
bundan anlar; hiçbir zaman değiştirilmez ve içe aktarmada çeviriye yazılmaz. Dosyada satır kimliği yoktur; içe
aktarırken satırlar `(orijinal, çeviri)` çiftiyle, çift aynıysa `grup` ile, olmazsa benzersiz orijinal metinle
eşleşir. Bu biçimler, çeviri metnindeki kontrol kodlarını ve tırnakları modelin bozmasını engeller.

**CSV (eski biçim, yalnızca içe aktarma):** sütunlar `id, anahtar, orijinal, ceviri`; satırlar kimlikle eşleşir.

Tüm biçimlerde içe aktarma, sohbet modellerinin tipik sapmalarına dayanıklıdır: ``` kod bloğu, öndeki
açıklama, noktalı virgül ayraç (CSV), "çeviri"/"translation" gibi sütun adları, `[1]` gibi bozulmuş kodlar.
Her metin model çıktısıyla aynı onarım ve temizlikten geçer; kontrol kodları uymayan, orijinali projedekinden
farklı veya eşleşmeyen satırlar yazılmaz, sayılıp kullanıcıya gösterilir.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from nxceviri.core.errors import NxError
from nxceviri.core.project import TranslationRow, row_group
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.cleanup import clean_output
from nxceviri.core.translate.runner import match_edges, repair_codes
from nxceviri.core.translate.status import Status

COLUMNS = ("id", "anahtar", "orijinal", "ceviri")
TXT_COLUMNS = ("orijinal", "çeviri", "düzeltme", "grup")
TRANSLATION_COLUMNS = ("orijinal", "çeviri", "yeni çeviri", "grup")
#: Bölerek dışa aktarmada varsayılan parça boyu (ücretsiz sohbet modellerinin bir yanıtta rahat işlediği kadar).
DEFAULT_PART_ROWS = 150

_ID_NAMES = {"id", "kimlik", "no", "satir", "satır"}
_SOURCE_NAMES = {"orijinal", "özgün", "ozgun", "kaynak", "source", "original", "ingilizce", "english"}
_CORRECTION_NAMES = {
    "düzeltme",
    "duzeltme",
    "correction",
    "fix",
    "revised",
    "yeni ceviri",
    "yeni çeviri",
}
_TEXT_NAMES = {
    "ceviri",
    "çeviri",
    "ceviri (duzeltilmis)",
    "çeviri (düzeltilmiş)",
    "duzeltilmis",
    "düzeltilmiş",
    "duzeltilmis ceviri",
    "düzeltilmiş çeviri",
    "yeni",
    "yeni ceviri",
    "yeni çeviri",
    "translation",
    "revised",
    "revised translation",
    "target",
    "turkce",
    "türkçe",
    "turkish",
}
_GROUP_NAMES = {
    "grup",
    "grup adi",
    "grup adı",
    "group",
    "group name",
    "koleksiyon",
    "collection",
    "kategori",
    "category",
    "bağlam",
    "baglam",
    "context",
    "dosya",
    "file",
}
_FENCE_RE = re.compile(r"^\s*```[\w-]*\s*$")


class CsvError(NxError):
    """CSV dosyası okunamadı veya yazılamadı."""


def _label(row: TranslationRow) -> str:
    return row.context or row.key


def rows_csv(rows: Sequence[TranslationRow]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for r in rows:
        writer.writerow([r.id, _label(r), r.source, r.translation])
    return out.getvalue()


def _escape_txt(value: str) -> str:
    """TXT hücresi: satır sonu, sekme ve ters bölü kaçışlanır; her satır tek satırda kalır."""
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")


def _unescape_txt(value: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in "\\trn":
            out.append({"\\": "\\", "t": "\t", "r": "\r", "n": "\n"}[value[i + 1]])
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def _rows_table_txt(rows: Sequence[TranslationRow], columns: Sequence[str]) -> str:
    lines = ["\t".join(columns)]
    lines += [
        "\t".join((_escape_txt(r.source), _escape_txt(r.translation), "", _escape_txt(row_group(r)))) for r in rows
    ]
    return "\r\n".join(lines) + "\r\n"


def rows_txt(rows: Sequence[TranslationRow]) -> str:
    """TXT tablosu: `orijinal`, `çeviri`, `düzeltme` (boş), `grup`. Model yalnızca düzeltmeyi doldurur."""
    return _rows_table_txt(rows, TXT_COLUMNS)


def rows_translation_txt(rows: Sequence[TranslationRow]) -> str:
    """Dış çeviri TXT tablosu: `orijinal`, `çeviri`, `yeni çeviri` (boş), `grup`.

    Düzen redaksiyonla aynıdır; yalnızca üçüncü sütunun adı dış çevirmene ne beklendiğini söyler.
    """
    return _rows_table_txt(rows, TRANSLATION_COLUMNS)


# --- XLSX (Excel) --------------------------------------------------------------------------------

_XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
#: XML 1.0'ın izin vermediği denetim karakterleri (oyun metinlerinde ham hâlde gelebilir).
_ILLEGAL_XML_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _xlsx_text(value: str) -> str:
    return escape(_ILLEGAL_XML_RE.sub("", value))


def _col_letter(index: int) -> str:
    """0 → A, 25 → Z, 26 → AA."""
    out = ""
    n = index + 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def table_xlsx(header: Sequence[str], rows: Sequence[Sequence[str]], *, sheet: str = "Redaksiyon") -> bytes:
    """Dört (veya daha çok) sütunlu bir XLSX dosyası üretir; hücreler satır sonlarını korur.

    Bağımlılık yok: Office Open XML'in gereken en küçük parçaları (çalışma kitabı, stil, çalışma sayfası)
    doğrudan yazılır. Başlık satırı kalın ve dondurulmuştur; metin hücreleri kaydırılır.
    """
    header = list(header)
    width = max(len(header), 3)
    body: list[str] = []
    for r_index, cells in enumerate([header, *rows], start=1):
        style = 1 if r_index == 1 else 2
        items = []
        for c_index in range(width):
            value = cells[c_index] if c_index < len(cells) else ""
            ref = f"{_col_letter(c_index)}{r_index}"
            items.append(
                f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{_xlsx_text(value)}</t></is></c>'
            )
        body.append(f'<row r="{r_index}">{"".join(items)}</row>')
    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    sheet_xml = (
        f'{head}<worksheet xmlns="{_XLSX_NS}">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews>"
        f'<cols><col min="1" max="1" width="45" customWidth="1"/>'
        f'<col min="2" max="{width}" width="60" customWidth="1"/></cols>'
        f"<sheetData>{''.join(body)}</sheetData></worksheet>"
    )
    workbook = (
        f'{head}<workbook xmlns="{_XLSX_NS}" xmlns:r="{_REL_NS}">'
        f'<sheets><sheet name="{_xlsx_text(sheet)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    styles = (
        f'{head}<styleSheet xmlns="{_XLSX_NS}">'
        '<fonts count="2">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        "</fonts>"
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
        '<alignment vertical="top" wrapText="1"/></xf>'
        "</cellXfs>"
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )
    content_types = (
        f'{head}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    root_rels = (
        f'{head}<Relationships xmlns="{_PKG_REL_NS}">'
        '<Relationship Id="rId1" '
        f'Type="{_REL_NS}/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_rels = (
        f'{head}<Relationships xmlns="{_PKG_REL_NS}">'
        f'<Relationship Id="rId1" Type="{_REL_NS}/worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{_REL_NS}/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        z.writestr("xl/styles.xml", styles)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return out.getvalue()


def rows_xlsx(rows: Sequence[TranslationRow]) -> bytes:
    """XLSX tablosu: `orijinal`, `çeviri`, `düzeltme` (boş), `grup`; düzeltmeyi kullanıcı/model doldurur."""
    return table_xlsx(TXT_COLUMNS, [(r.source, r.translation, "", row_group(r)) for r in rows])


def rows_translation_xlsx(rows: Sequence[TranslationRow]) -> bytes:
    """Dış çeviri XLSX tablosu: `orijinal`, `çeviri`, `yeni çeviri` (boş), `grup`."""
    return table_xlsx(
        TRANSLATION_COLUMNS,
        [(r.source, r.translation, "", row_group(r)) for r in rows],
        sheet="Çeviri",
    )


def part_paths(path: Path, count: int) -> list[Path]:
    """Parça dosyalarının adları: tek parçada `path`, değilse `ad_001.csv`, `ad_002.csv` …"""
    if count <= 1:
        return [path]
    width = max(3, len(str(count)))
    return [path.with_name(f"{path.stem}_{i:0{width}d}{path.suffix}") for i in range(1, count + 1)]


_UNSAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_name(group: str) -> str:
    """Grup adının Windows dosya adında kullanılabilir hâli."""
    return _UNSAFE_NAME_RE.sub("_", group).strip(" ._") or "grup"


def group_rows(rows: Sequence[TranslationRow]) -> dict[str, list[TranslationRow]]:
    """Satırları gruplarına ayırır (gruplar ilk geçtikleri sırayla, satırlar tablodaki sırayla)."""
    groups: dict[str, list[TranslationRow]] = {}
    for r in rows:
        groups.setdefault(row_group(r), []).append(r)
    return groups


def _write_parts(
    rows: Sequence[TranslationRow],
    path: Path,
    part_rows: int,
    by_group: bool,
    *,
    kind: str,
    render: Callable[[Sequence[TranslationRow]], bytes],
) -> list[Path]:
    if by_group:
        sets = [(path.with_name(f"{path.stem}_{safe_name(g)}{path.suffix}"), rs) for g, rs in group_rows(rows).items()]
    else:
        sets = [(path, list(rows))]
    jobs: list[tuple[Path, Sequence[TranslationRow]]] = []
    for base, items in sets:
        size = part_rows if part_rows > 0 else max(len(items), 1)
        chunks = [items[i : i + size] for i in range(0, len(items), size)] or [items]
        jobs += zip(part_paths(base, len(chunks)), chunks, strict=True)
    try:
        for target, chunk in jobs:
            target.write_bytes(render(chunk))
    except OSError as exc:
        raise CsvError(
            f"{kind} dosyası yazılamadı: {exc.strerror or exc}", "Başka bir klasör seçin veya dosya açıksa kapatın."
        ) from exc
    return [t for t, _ in jobs]


def export_csv(rows: Sequence[TranslationRow], path: Path, part_rows: int = 0, *, by_group: bool = False) -> list[Path]:
    """Satırları CSV olarak yazar (eski biçim; yalnızca geriye uyum için).

    `by_group` ise her grup ayrı dosyaya (`ad_Dialogue.csv`) yazılır; `part_rows` > 0 ise her dosya en çok o kadar
    satırlık parçalara bölünür (`ad_001.csv`, gruplu `ad_Dialogue_001.csv`).
    """
    return _write_parts(
        rows, path, part_rows, by_group, kind="CSV", render=lambda items: rows_csv(items).encode("utf-8-sig")
    )


def export_txt(rows: Sequence[TranslationRow], path: Path, part_rows: int = 0, *, by_group: bool = False) -> list[Path]:
    """Satırları dört sütunlu TXT tablosu olarak yazar (bkz. `rows_txt`).

    Dosya adlandırma ve parçalama `export_csv` ile aynıdır (`ad_001.txt`, gruplu `ad_Dialogue_001.txt`).
    """
    return _write_parts(
        rows, path, part_rows, by_group, kind="TXT", render=lambda items: rows_txt(items).encode("utf-8-sig")
    )


def export_xlsx(
    rows: Sequence[TranslationRow], path: Path, part_rows: int = 0, *, by_group: bool = False
) -> list[Path]:
    """Satırları Excel'de açılan dört sütunlu XLSX tablosu olarak yazar (bkz. `rows_xlsx`).

    Dosya adlandırma ve parçalama `export_txt` ile aynıdır (`ad_001.xlsx`, gruplu `ad_Dialogue_001.xlsx`).
    """
    return _write_parts(rows, path, part_rows, by_group, kind="XLSX", render=rows_xlsx)


def export_translation_txt(
    rows: Sequence[TranslationRow], path: Path, part_rows: int = 0, *, by_group: bool = False
) -> list[Path]:
    """Satırları dış çeviri TXT tablosu olarak yazar (bkz. `rows_translation_txt`).

    Dosya adlandırma ve parçalama `export_txt` ile aynıdır (`ad_001.txt`, gruplu `ad_Dialogue_001.txt`).
    """
    return _write_parts(
        rows,
        path,
        part_rows,
        by_group,
        kind="TXT",
        render=lambda items: rows_translation_txt(items).encode("utf-8-sig"),
    )


def export_translation_xlsx(
    rows: Sequence[TranslationRow], path: Path, part_rows: int = 0, *, by_group: bool = False
) -> list[Path]:
    """Satırları dış çeviri XLSX tablosu olarak yazar (bkz. `rows_translation_xlsx`).

    Dosya adlandırma ve parçalama `export_txt` ile aynıdır (`ad_001.xlsx`, gruplu `ad_Dialogue_001.xlsx`).
    """
    return _write_parts(rows, path, part_rows, by_group, kind="XLSX", render=rows_translation_xlsx)


def revision_prompt(instruction: str = "") -> str:
    """Dışa aktarılan CSV ile birlikte dış modele verilecek hazır istem."""
    lines = [
        "Ekteki CSV dosyası bir video oyununun İngilizce metinlerini (orijinal sütunu) ve Türkçe çevirilerini "
        "(ceviri sütunu) içeriyor. Çevirileri redakte et: anlamı orijinale sadık, doğal ve akıcı Türkçe olsun; "
        "yazım, dil bilgisi ve noktalama hatalarını düzelt.",
        "",
        "Kurallar:",
        "1. Yalnızca “ceviri” sütununu değiştir; id, anahtar ve orijinal sütunlarına dokunma.",
        "2. Satır ekleme, silme, birleştirme veya sıralarını değiştirme; her id bir kez ve aynı sırada kalsın.",
        "3. ⟦1⟧, ⟦2⟧ gibi işaretler oyunun kontrol kodlarıdır (satır sonu, renk, oyuncu adı…). Her birini "
        "aynen, orijinaldekiyle aynı sayıda ve anlamca doğru yerde tut; yeni kod veya HTML etiketi ekleme.",
        "4. İyi olan çeviriyi olduğu gibi bırak; bir satırın metnini başka satıra taşıma.",
        "5. Sonucu aynı sütun başlıklarıyla (id, anahtar, orijinal, ceviri), virgülle ayrılmış ve her alanı çift "
        "tırnak içinde, eksiksiz bir CSV olarak ver; açıklama ekleme.",
    ]
    if instruction.strip():
        lines += ["", "Ek talimat:", instruction.strip()]
    return "\n".join(lines)


def revision_prompt_txt(instruction: str = "") -> str:
    """Dışa aktarılan dört sütunlu TXT ile birlikte dış modele verilecek hazır istem."""
    lines = [
        "Ekteki TXT dosyası bir video oyununun metinlerini dört sütun hâlinde içeriyor: “orijinal” (İngilizce "
        "kaynak), “çeviri” (mevcut Türkçe çeviri), “düzeltme” (boş) ve “grup” (metnin oyun içindeki yeri). "
        "Görevin yalnızca “düzeltme” sütununu doldurmak: anlamı orijinale sadık, doğal ve akıcı Türkçe olsun; "
        "yazım, dil bilgisi ve noktalama hatalarını düzelt.",
        "",
        "Kurallar:",
        "1. Yalnızca “düzeltme” sütununu doldur; “orijinal”, “çeviri” ve “grup” sütunlarını hiç değiştirme.",
        "2. “grup” sütunu bağlamdır: metnin oyunun neresinde kullanıldığını söyler (ör. “UI” menü, düğme veya "
        "etiket; “Dialogue” konuşma cümlesi; başka bir ad dosya/tablo adı). Üslubu buna göre seç: UI satırlarını "
        "cümle gibi değil kısa menü/etiket metni gibi, Dialogue satırlarını doğal konuşma cümlesi gibi düzelt.",
        "3. Düzeltme gerekmeyen satırda “düzeltme” sütununu boş bırak (üçüncü sütuna bir şey yazma); dördüncü "
        "sütundaki grup adını aynen koru. Boş düzeltme, mevcut çevirinin olduğu gibi kalacağı anlamına gelir.",
        "4. Satır ekleme, silme, birleştirme veya sıralarını değiştirme; her metin tek satırda kalsın.",
        "5. ⟦1⟧, ⟦2⟧ gibi işaretler oyunun kontrol kodlarıdır (satır sonu, renk, oyuncu adı…). Her birini "
        "aynen, orijinaldekiyle aynı sayıda ve anlamca doğru yerde tut; yeni kod veya HTML etiketi ekleme.",
        "6. Hücre içindeki \\n, \\t ve \\\\ yazıları satır sonu, sekme ve ters bölü kodlarıdır; bunları aynen "
        "koru, gerçek satır sonu veya sekmeye çevirme.",
        "7. Yanıtı yalnızca dosyanın kendisi olarak ver: önce başlık satırı (orijinal, çeviri, düzeltme ve grup "
        "adları sekmele ayrılmış), sonra satırlar. Açıklama, ``` çiti veya başka metin ekleme.",
    ]
    if instruction.strip():
        lines += ["", "Ek talimat:", instruction.strip()]
    return "\n".join(lines)


def revision_prompt_xlsx(instruction: str = "") -> str:
    """Dışa aktarılan dört sütunlu XLSX (Excel) dosyasıyla birlikte verilecek hazır istem."""
    lines = [
        "Ekteki XLSX (Excel) dosyası bir video oyununun metinlerini dört sütun hâlinde içeriyor: “orijinal” "
        "(İngilizce kaynak), “çeviri” (mevcut Türkçe çeviri), “düzeltme” (boş) ve “grup” (metnin oyun içindeki "
        "yeri). Görevin yalnızca “düzeltme” sütununu doldurmak: anlamı orijinale sadık, doğal ve akıcı Türkçe "
        "olsun; yazım, dil bilgisi ve noktalama hatalarını düzelt.",
        "",
        "Kurallar:",
        "1. Yalnızca “düzeltme” sütununu doldur; “orijinal”, “çeviri” ve “grup” sütunlarını hiç değiştirme.",
        "2. “grup” sütunu bağlamdır: metnin oyunun neresinde kullanıldığını söyler (ör. “UI” menü, düğme veya "
        "etiket; “Dialogue” konuşma cümlesi; başka bir ad dosya/tablo adı). Üslubu buna göre seç: UI satırlarını "
        "cümle gibi değil kısa menü/etiket metni gibi, Dialogue satırlarını doğal konuşma cümlesi gibi düzelt.",
        "3. Düzeltme gerekmeyen satırda “düzeltme” hücresini boş bırak; “grup” hücresini aynen koru. Boş "
        "düzeltme, mevcut çevirinin olduğu gibi kalacağı anlamına gelir.",
        "4. Satır ekleme, silme, birleştirme veya sıralarını değiştirme; her metin kendi satırında kalsın.",
        "5. ⟦1⟧, ⟦2⟧ gibi işaretler oyunun kontrol kodlarıdır (satır sonu, renk, oyuncu adı…). Her birini "
        "aynen, orijinaldekiyle aynı sayıda ve anlamca doğru yerde tut; yeni kod veya HTML etiketi ekleme.",
        "6. Hücre içindeki gerçek satır sonlarını koru; düzeltme hücresine fazladan satır ekleme.",
        "7. Yanıtı aynı dört sütunlu XLSX dosyası olarak ver (indirilebilir ek); açıklama veya başka dosya "
        "ekleme. Dosyayı veremiyorsan dört sütunlu TXT olarak da verebilirsin.",
    ]
    if instruction.strip():
        lines += ["", "Ek talimat:", instruction.strip()]
    return "\n".join(lines)


def translation_prompt_txt(instruction: str = "") -> str:
    """Dışa aktarılan dört sütunlu çeviri TXT dosyasıyla birlikte dış modele verilecek hazır istem."""
    lines = [
        "Ekteki TXT dosyası bir video oyununun metinlerini dört sütun hâlinde içeriyor: “orijinal” (İngilizce "
        "kaynak), “çeviri” (mevcut Türkçe çeviri; henüz çevrilmemişse boş), “yeni çeviri” (boş) ve “grup” "
        "(metnin oyun içindeki yeri). Görevin “yeni çeviri” sütununu doldurmak: anlamı orijinale sadık, doğal ve "
        "akıcı Türkçe çeviriler yaz.",
        "",
        "Kurallar:",
        "1. Yalnızca “yeni çeviri” sütununu doldur; “orijinal”, “çeviri” ve “grup” sütunlarını hiç değiştirme.",
        "2. “grup” sütunu bağlamdır: metnin oyunun neresinde kullanıldığını söyler (ör. “UI” menü, düğme veya "
        "etiket; “Dialogue” konuşma cümlesi; başka bir ad dosya/tablo adı). Üslubu buna göre seç: UI satırlarını "
        "cümle gibi değil kısa menü/etiket metni gibi, Dialogue satırlarını doğal konuşma cümlesi gibi çevir.",
        "3. Mevcut “çeviri” zaten doğru ve doğalsa “yeni çeviri” sütununu boş bırak; boş hücre, mevcut çevirinin "
        "olduğu gibi kalacağı anlamına gelir. “çeviri” boş olan satırları mutlaka doldur.",
        "4. Satır ekleme, silme, birleştirme veya sıralarını değiştirme; her metin tek satırda kalsın.",
        "5. ⟦1⟧, ⟦2⟧ gibi işaretler oyunun kontrol kodlarıdır (satır sonu, renk, oyuncu adı…). Her birini "
        "orijinaldekiyle aynı sayıda ve anlamca doğru yerde tut; yeni kod veya HTML etiketi ekleme.",
        "6. Hücre içindeki \\n, \\t ve \\\\ yazıları satır sonu, sekme ve ters bölü kodlarıdır; bunları aynen "
        "koru, gerçek satır sonu veya sekmeye çevirme.",
        "7. Yanıtı yalnızca dosyanın kendisi olarak ver: önce başlık satırı (orijinal, çeviri, yeni çeviri ve "
        "grup adları sekmele ayrılmış), sonra satırlar. Açıklama, ``` çiti veya başka metin ekleme.",
    ]
    if instruction.strip():
        lines += ["", "Ek talimat:", instruction.strip()]
    return "\n".join(lines)


def translation_prompt_xlsx(instruction: str = "") -> str:
    """Dışa aktarılan dört sütunlu çeviri XLSX (Excel) dosyasıyla birlikte verilecek hazır istem."""
    lines = [
        "Ekteki XLSX (Excel) dosyası bir video oyununun metinlerini dört sütun hâlinde içeriyor: “orijinal” "
        "(İngilizce kaynak), “çeviri” (mevcut Türkçe çeviri; henüz çevrilmemişse boş), “yeni çeviri” (boş) ve "
        "“grup” (metnin oyun içindeki yeri). Görevin “yeni çeviri” sütununu doldurmak: anlamı orijinale sadık, "
        "doğal ve akıcı Türkçe çeviriler yaz.",
        "",
        "Kurallar:",
        "1. Yalnızca “yeni çeviri” sütununu doldur; “orijinal”, “çeviri” ve “grup” sütunlarını hiç değiştirme.",
        "2. “grup” sütunu bağlamdır: metnin oyunun neresinde kullanıldığını söyler (ör. “UI” menü, düğme veya "
        "etiket; “Dialogue” konuşma cümlesi; başka bir ad dosya/tablo adı). Üslubu buna göre seç: UI satırlarını "
        "cümle gibi değil kısa menü/etiket metni gibi, Dialogue satırlarını doğal konuşma cümlesi gibi çevir.",
        "3. Mevcut “çeviri” zaten doğru ve doğalsa “yeni çeviri” hücresini boş bırak; boş hücre, mevcut çevirinin "
        "olduğu gibi kalacağı anlamına gelir. “çeviri” boş olan satırları mutlaka doldur.",
        "4. Satır ekleme, silme, birleştirme veya sıralarını değiştirme; her metin kendi satırında kalsın.",
        "5. ⟦1⟧, ⟦2⟧ gibi işaretler oyunun kontrol kodlarıdır (satır sonu, renk, oyuncu adı…). Her birini "
        "orijinaldekiyle aynı sayıda ve anlamca doğru yerde tut; yeni kod veya HTML etiketi ekleme.",
        "6. Hücre içindeki gerçek satır sonlarını koru; yeni çeviri hücresine fazladan satır ekleme.",
        "7. Yanıtı aynı dört sütunlu XLSX dosyası olarak ver (indirilebilir ek); açıklama veya başka dosya "
        "ekleme. Dosyayı veremiyorsan dört sütunlu TXT olarak da verebilirsin.",
    ]
    if instruction.strip():
        lines += ["", "Ek talimat:", instruction.strip()]
    return "\n".join(lines)


@dataclass(frozen=True)
class CsvRow:
    entry_id: int | None  # TXT'de kimlik yoktur; satır (orijinal, çeviri) çiftiyle eşleşir
    source: str | None  # dosyada orijinal sütunu yoksa None
    text: str
    correction: str | None = None  # TXT'de "düzeltme" sütunu (boş = değişiklik yok); CSV'de None
    group: str = ""  # TXT/XLSX'te salt okunur bağlam (ör. "UI"); eşleşmede yalnızca ipucu olarak kullanılır


def _norm(name: str) -> str:
    return " ".join(name.strip().strip("\ufeff").casefold().split())


def _strip_fences(text: str) -> str:
    return "\n".join(line for line in text.lstrip("\ufeff").splitlines() if not _FENCE_RE.match(line))


def _header(lines: list[str]) -> tuple[int, str, list[str]] | None:
    """Başlık satırı: (satır no, ayraç, normalleştirilmiş sütun adları). Modelin öndeki açıklamaları atlanır."""
    for i, line in enumerate(lines):
        for delimiter in (",", ";", "\t", "|"):
            if delimiter not in line:
                continue
            names = [_norm(c) for c in next(csv.reader([line], delimiter=delimiter))]
            if any(n in _ID_NAMES for n in names) and any(n in _TEXT_NAMES for n in names):
                return i, delimiter, names
    return None


def parse_csv(text: str) -> list[CsvRow]:
    """CSV metnini satırlara ayırır; başlık bulunamazsa `CsvError`."""
    lines = _strip_fences(text).splitlines()
    found = _header(lines)
    if found is None:
        raise CsvError(
            "CSV dosyasında “id” ve “ceviri” sütunları bulunamadı.",
            "Başlık satırı “id, anahtar, orijinal, ceviri” olmalı; sütun adlarını değiştirmeden geri yükleyin.",
        )
    start, delimiter, header = found
    reader = csv.reader(io.StringIO("\n".join(lines[start + 1 :])), delimiter=delimiter)
    id_col = next(i for i, h in enumerate(header) if h in _ID_NAMES)  # _header ikisinin de varlığını denetledi
    text_col = next(i for i, h in enumerate(header) if h in _TEXT_NAMES)
    source_col = next((i for i, h in enumerate(header) if h in _SOURCE_NAMES), None)
    out: list[CsvRow] = []
    for cells in reader:
        if not any(c.strip() for c in cells):
            continue
        if len(cells) <= max(id_col, text_col):
            raise CsvError(
                f"CSV dosyasının {start + 1 + reader.line_num}. satırında sütun eksik.",
                "Modelin çıktısı yarıda kesilmiş veya tırnaklar bozulmuş olabilir; o bölümü yeniden isteyin.",
            )
        try:
            entry_id = int(cells[id_col].strip())
        except ValueError as exc:
            raise CsvError(
                f"CSV dosyasının {start + 1 + reader.line_num}. satırındaki kimlik bir sayı değil: "
                f"“{cells[id_col][:40]}”.",
                "id sütunu değiştirilmemiş olmalı.",
            ) from exc
        source = cells[source_col] if source_col is not None and source_col < len(cells) else None
        out.append(CsvRow(entry_id, source, cells[text_col]))
    return out


@dataclass(frozen=True)
class _Layout:
    """TXT/XLSX sütun düzeni (başlık satırından çözülür)."""

    source: int
    text: int
    correction: int
    group: int | None  # eski üç sütunlu dosyalarda None

    @property
    def last(self) -> int:
        return max(self.source, self.text, self.correction, -1 if self.group is None else self.group)


_DEFAULT_LAYOUT = _Layout(0, 1, 2, None)


def _txt_layout(cells: Sequence[str]) -> _Layout | None:
    """Başlık satırıysa sütun düzeni; değilse `None`. Adlar İngilizceye çevrilse de tanınır."""
    names = [_norm(c) for c in cells]
    source = next((i for i, n in enumerate(names) if n in _SOURCE_NAMES), None)
    # “yeni çeviri” hem metin hem düzeltme adı olabilir; düzeltme sütunu sayılmasın diye önce yalın adlar aranır.
    text = next((i for i, n in enumerate(names) if n in _TEXT_NAMES and n not in _CORRECTION_NAMES), None)
    if text is None:
        text = next((i for i, n in enumerate(names) if n in _TEXT_NAMES), None)
    if source is None or text is None:
        return None
    group = next((i for i, n in enumerate(names) if n in _GROUP_NAMES), None)
    correction = next((i for i, n in enumerate(names) if i != text and n in _CORRECTION_NAMES), None)
    if correction is None:
        # Yalnızca “yeni çeviri” sütunu varsa (mevcut çeviri sütunu silinmişse) o sütun hem metin hem düzeltmedir;
        # aksi hâlde sıradaki sütun düzeltme sayılır.
        correction = text if names[text] in _CORRECTION_NAMES else text + 1
    if group is None and len(names) >= 4 and correction < len(names) - 1:
        group = len(names) - 1  # adı tanınmasa da düzeltmeden sonraki son sütun bağlamdır
    return _Layout(source, text, correction, group)


def _layout_values(cells: Sequence[str], layout: _Layout) -> tuple[str, str, str, str]:
    """Hücreleri (orijinal, çeviri, düzeltme, grup) sırasına yerleştirir.

    Eksik sütunlar boş sayılır. Beklenenden fazla sekme varsa fazlalık düzeltmeye katılır (modelin metne
    yazdığı gerçek sekme); grup fazlalıktan doldurulmaz, çünkü modelin grup sütununu silmesi yaygındır.
    """
    if len(cells) > layout.last + 1:
        if layout.group is None:  # eski üç sütunlu dosya: fazlalığın tamamı düzeltmedir
            cells = [*cells[: layout.correction], "\t".join(cells[layout.correction :])]
        elif layout.group == layout.last:
            cells = [*cells[: layout.correction], "\t".join(cells[layout.correction : -1]), cells[-1]]
        else:  # grup sütunu sonda değil: fazlalık düzeltmeye eklenir, sütunlar kaymaz
            extra = cells[layout.last + 1 :]
            cells = [*cells[: layout.last + 1]]
            cells[layout.correction] = "\t".join((cells[layout.correction], *extra))
    padded = [*cells, *([""] * (layout.last + 1 - len(cells)))]
    group = padded[layout.group] if layout.group is not None else ""
    return padded[layout.source], padded[layout.text], padded[layout.correction], group


def parse_txt(text: str) -> list[CsvRow]:
    """Dört (eski dosyalarda üç) sütunlu TXT tablosunu satırlara ayırır (`CsvRow.entry_id` None).

    Başlık satırı, ``` çiti ve modelin öndeki/sondaki açıklamaları atlanır. Başlık varsa sütun sırası oradan
    okunur; `grup` sütunu salt okunur bağlamdır. Hücrelerdeki `\\n`, `\\t`, `\\\\` kaçışları çözülür; başlıksız
    eski dosyalarda fazladan sekmeler (modelin metne yazdığı gerçek sekme) düzeltme sütununa katılır.
    """
    lines = _strip_fences(text).lstrip("\ufeff").splitlines()
    layout: _Layout | None = None
    out: list[CsvRow] = []
    for line in lines:
        if not line.strip():
            continue
        cells = line.split("\t")
        if not out and layout is None:
            found = _txt_layout(cells)
            if found is not None:
                layout = found
                continue
        if len(cells) < 2:
            continue  # modelin açıklama satırı
        source, target, correction, group = _layout_values(cells, layout or _DEFAULT_LAYOUT)
        out.append(
            CsvRow(None, _unescape_txt(source), _unescape_txt(target), _unescape_txt(correction), _unescape_txt(group))
        )
    if not out:
        raise CsvError(
            "TXT dosyasında “orijinal”, “çeviri”, “düzeltme” sütunlu bir satır bulunamadı.",
            "Dosya sekme ayraçlı ve dört sütunlu olmalı; dışa aktarılan dosyayı değiştirmeden geri yükleyin.",
        )
    return out


def _xlsx_zip(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CsvError(
            "XLSX dosyası açılamadı (bozuk veya şifreli).",
            "Dosyayı Excel'de açıp “Farklı kaydet” ile yeniden kaydedin.",
        ) from exc


def _xlsx_sheet_path(z: zipfile.ZipFile) -> str:
    """İlk çalışma sayfasının paket içi yolu (Excel farklı adlandırabilir)."""
    try:
        # Kullanıcının seçtiği yerel dosya; dış varlık çözümü yok, yalnızca paket içi metin okunur.
        workbook = ET.fromstring(z.read("xl/workbook.xml"))  # noqa: S314
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))  # noqa: S314
    except (KeyError, ET.ParseError):
        return "xl/worksheets/sheet1.xml"
    sheet = workbook.find(f".//{{{_XLSX_NS}}}sheet")
    rid = sheet.get(f"{{{_REL_NS}}}id") if sheet is not None else None
    for rel in rels.findall(f"{{{_PKG_REL_NS}}}Relationship"):
        if rel.get("Id") == rid:
            target = (rel.get("Target") or "").lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    return "xl/worksheets/sheet1.xml"


def _xlsx_shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))  # noqa: S314
    except (KeyError, ET.ParseError):
        return []
    return ["".join(t.text or "" for t in si.iter(f"{{{_XLSX_NS}}}t")) for si in root.findall(f"{{{_XLSX_NS}}}si")]


def _xlsx_cell_text(cell: ET.Element, shared: Sequence[str]) -> str:
    if cell.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{{{_XLSX_NS}}}t"))
    value = cell.find(f"{{{_XLSX_NS}}}v")
    if value is None:
        return ""
    raw = value.text or ""
    if cell.get("t") == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return ""
    return raw


def _xlsx_col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref.upper())
    if not letters:
        return -1
    n = 0
    for ch in letters.group(0):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def xlsx_table(data: bytes) -> list[list[str]]:
    """XLSX dosyasının ilk çalışma sayfası: boş olmayan satırlar, hücre metinleri sütun sırasıyla.

    Hücrelerdeki gerçek satır sonları korunur, paylaşılan metinler (Excel'in `sharedStrings`) ve satır içi metinler
    okunur. Bozuk dosyada `CsvError`.
    """
    with _xlsx_zip(data) as z:
        shared = _xlsx_shared_strings(z)
        sheet_path = _xlsx_sheet_path(z)
        try:
            root = ET.fromstring(z.read(sheet_path))  # noqa: S314
        except KeyError as exc:
            raise CsvError(
                "XLSX dosyasında çalışma sayfası bulunamadı.",
                "Dosyayı Excel'de açıp yeniden kaydedin.",
            ) from exc
        except ET.ParseError as exc:
            raise CsvError(
                "XLSX dosyasının çalışma sayfası okunamadı.",
                "Dosyayı Excel'de açıp yeniden kaydedin.",
            ) from exc
        table: list[list[str]] = []
        for row in root.iter(f"{{{_XLSX_NS}}}row"):
            by_col: dict[int, str] = {}
            for cell in row.findall(f"{{{_XLSX_NS}}}c"):
                index = _xlsx_col_index(cell.get("r", ""))
                if index >= 0:
                    by_col[index] = _xlsx_cell_text(cell, shared)
            if by_col:
                table.append([by_col.get(i, "") for i in range(max(by_col) + 1)])
    return [line for line in table if any(c.strip() for c in line)]


def parse_xlsx(data: bytes) -> list[CsvRow]:
    """XLSX çalışma sayfasını redaksiyon satırlarına çevirir.

    Başlık (`orijinal`, `çeviri`, `düzeltme`, `grup`) varsa atlanır ve sütun sırası oradan okunur; yoksa bütün
    satırlar üç sütunlu eski düzenle veri sayılır. `grup` salt okunur bağlamdır; çeviriye yazılmaz.
    """
    rows = xlsx_table(data)
    layout = _DEFAULT_LAYOUT
    start = 0
    for i, line in enumerate(rows):
        found = _txt_layout(line)
        if found is not None:
            layout = found
            start = i + 1
            break
    out: list[CsvRow] = []
    for line in rows[start:]:
        if len(line) < 2:
            continue
        source, target, correction, group = _layout_values(line, layout)
        out.append(CsvRow(None, source, target, correction, group))
    if not out:
        raise CsvError(
            "XLSX dosyasında “orijinal”, “çeviri”, “düzeltme” sütunlu bir satır bulunamadı.",
            "Dosyayı dışa aktarılan dört sütunlu tabloyu değiştirmeden geri yükleyin.",
        )
    return out


def _decode(raw: bytes, name: str) -> str:
    for encoding in ("utf-8-sig", "cp1254"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    # cp1254 her baytı çözemeyebilir (ör. 0x81)
    raise CsvError(f"Dosyanın karakter kodlaması tanınmadı: {name}", "Dosyayı UTF-8 olarak kaydedin.")


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CsvError(f"Dosya okunamadı: {path.name} ({exc.strerror or exc})") from exc
    return _decode(raw, path.name)


def read_csv(path: Path) -> list[CsvRow]:
    text = _read_text(path)
    try:
        return parse_csv(text)
    except CsvError as exc:
        raise CsvError(f"{path.name}: {exc.message}", exc.hint) from exc


def read_xlsx(path: Path) -> list[CsvRow]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CsvError(f"Dosya okunamadı: {path.name} ({exc.strerror or exc})") from exc
    try:
        return parse_xlsx(raw)
    except CsvError as exc:
        raise CsvError(f"{path.name}: {exc.message}", exc.hint) from exc


def read_revision_file(path: Path) -> list[CsvRow]:
    """Redaksiyon dosyasını biçimine göre okur: XLSX, TXT (dört sütun; eski dosyalarda üç) veya eski CSV (id'li).

    Uzantıya güvenmek yerine içeriğe bakılır: dosya bir ZIP paketiyle (PK) başlıyorsa XLSX, CSV başlığı
    (`id` + çeviri sütunu) varsa CSV, dosyada hiç sekme yoksa yine CSV (bozuk CSV'nin hatası CSV'ye göre
    verilsin), aksi hâlde TXT okunur. Böylece `.txt` kaydedilmiş eski CSV dosyaları da çalışmaya devam eder.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CsvError(f"Dosya okunamadı: {path.name} ({exc.strerror or exc})") from exc
    if raw.startswith(b"PK\x03\x04"):
        try:
            return parse_xlsx(raw)
        except CsvError as exc:
            raise CsvError(f"{path.name}: {exc.message}", exc.hint) from exc
    text = _decode(raw, path.name)
    lines = _strip_fences(text).splitlines()
    is_csv = _header(lines) is not None or not any("\t" in line for line in lines)
    try:
        return parse_csv(text) if is_csv else parse_txt(text)
    except CsvError as exc:
        raise CsvError(f"{path.name}: {exc.message}", exc.hint) from exc


@dataclass
class CsvPlan:
    """İçe aktarmada ne olacağı: yazılacaklar ve yazılmayacakların nedenleri."""

    found: int = 0
    changes: list[tuple[int, str]] = field(default_factory=list)
    unchanged: int = 0
    empty: int = 0
    approved: int = 0  # değişecek satırlardan onaylı olanlar
    cleaned: int = 0  # onarım/temizlikten geçerek değişenler
    unknown: int = 0  # kimliği projede yok (CSV)
    no_correction: int = 0  # TXT/XLSX'te “düzeltme” hücresi boş: çeviri olduğu gibi kalır
    unmatched: int = 0  # TXT/XLSX satırı projedeki bir satırla eşleşmedi (birden çok aday dahil)
    source_mismatch: list[int] = field(default_factory=list)
    code_problems: list[tuple[int, str]] = field(default_factory=list)  # (satır kimliği, sorun)


def _same_text(a: str, b: str) -> bool:
    return " ".join(a.split()) == " ".join(b.split())


def _group_key(value: str) -> str:
    return " ".join(value.split()).casefold()


class _TxtMatcher:
    """TXT/XLSX satırlarını (orijinal, çeviri) çiftiyle eşleştirir; kimlik olmadığı için sırayla tüketir.

    Aynı metin bir oyunda çok kez geçebilir (ör. “Yes” → “Evet”); çifti aynı olan satırlar dosyadaki sırayla
    eşleşir. Çift aynıysa `grup` sütunu hangi satırın kastedildiğini ayırır (ör. aynı “Yes” hem UI hem
    Dialogue'da). Çift tutmazsa benzersiz orijinal, o da belirsizse benzersiz çeviri metni denenir; `grup`
    yalnızca ipucudur, hiçbir zaman zorunlu değildir.
    """

    def __init__(self, rows: Sequence[TranslationRow]) -> None:
        self._used: set[int] = set()
        self._by_pair: dict[tuple[str, str], list[TranslationRow]] = {}
        self._by_pair_group: dict[tuple[str, str, str], list[TranslationRow]] = {}
        self._by_source: dict[str, list[TranslationRow]] = {}
        self._by_text: dict[str, list[TranslationRow]] = {}
        for r in rows:
            source = " ".join(r.source.split())
            text = " ".join(r.translation.split())
            self._by_pair.setdefault((source, text), []).append(r)
            self._by_pair_group.setdefault((source, text, _group_key(row_group(r))), []).append(r)
            self._by_source.setdefault(source, []).append(r)
            self._by_text.setdefault(text, []).append(r)

    def _free(self, candidates: Sequence[TranslationRow]) -> list[TranslationRow]:
        return [r for r in candidates if r.id not in self._used]

    def _take(self, r: TranslationRow) -> TranslationRow:
        self._used.add(r.id)
        return r

    def _unique(self, candidates: Sequence[TranslationRow], group: str) -> TranslationRow | None:
        free = self._free(candidates)
        if group:
            same = [r for r in free if _group_key(row_group(r)) == group]
            if same:
                free = same
        if len(free) == 1:  # birden çok aday varsa yanlış satıra yazmamak için eşleştirme yapılmaz
            return self._take(free[0])
        return None

    def match(self, source: str, text: str, group: str = "") -> TranslationRow | None:
        src = " ".join(source.split())
        txt = " ".join(text.split())
        grp = _group_key(group)
        if grp:
            free = self._free(self._by_pair_group.get((src, txt, grp), []))
            if free:
                return self._take(free[0])  # aynı üçlüden birden çok varsa dosya sırasıyla
        pair = self._by_pair.get((src, txt))
        free = self._free(pair) if pair else []
        if free:
            return self._take(free[0])  # aynı çiftten birden çok varsa dosya sırasıyla
        return self._unique(self._by_source.get(src, []), grp) or self._unique(self._by_text.get(txt, []), grp)


def prepare_correction(row: TranslationRow, text: str) -> tuple[str, list[str]]:
    """Bir düzeltmeyi yazılmadan önce model çıktısıyla aynı onarım/temizlikten geçirir.

    Kullanıcı “Yeni” hücresini elle düzenlediğinde de aynı kurallar geçerlidir: benzer yer tutucu yazımları
    onarılır (`[1]` → `⟦1⟧`), boşluk/satır sonu temizlenir. İkinci liste boş değilse metin yazılmamalıdır.
    """
    if not text.strip():
        return "", ["Çeviri boş."]
    repaired = repair_codes(row.source, text, row.code_labels)
    final = match_edges(row.source, clean_output(row.source, repaired, row.code_labels))
    return final, placeholders.problems(row.source, final)


def plan_import(rows: Sequence[TranslationRow], csv_rows: Sequence[CsvRow]) -> CsvPlan:
    """Dosya satırlarını projeyle eşleştirir; projeye yazmaz.

    CSV satırları kimlikle, TXT/XLSX satırları içerikle eşleşir; aynı çift birden çok kez geçiyorsa `grup`
    sütunu hangi satırın kastedildiğini ayırır. TXT/XLSX'te dolu `düzeltme` mevcut çevirinin yerine geçer;
    boş `düzeltme` satırı atlanır (mevcut çeviri korunur). `grup` hiçbir zaman yazılmaz, yalnızca bağlamdır.
    """
    by_id = {r.id: r for r in rows}
    matcher = _TxtMatcher(rows)
    entries: list[tuple[TranslationRow | None, CsvRow]] = []
    last_id: dict[int, int] = {}
    for c in csv_rows:
        if c.entry_id is None:
            entries.append((matcher.match(c.source or "", c.text, c.group), c))
        else:
            last_id[c.entry_id] = len(entries)  # aynı kimlik birden çok geçerse sonuncusu
            entries.append((by_id.get(c.entry_id), c))
    live = [(row, c) for i, (row, c) in enumerate(entries) if c.entry_id is None or last_id[c.entry_id] == i]
    plan = CsvPlan(found=len(live))
    for row, c in live:
        if row is None:
            if c.entry_id is None:
                plan.unmatched += 1
            else:
                plan.unknown += 1
            continue
        if c.correction is not None:
            if not c.correction.strip():
                plan.no_correction += 1
                continue
            candidate = c.correction
        else:
            candidate = c.text
        if c.source is not None and not _same_text(placeholders.repair(row.source, c.source), row.source):
            plan.source_mismatch.append(row.id)
            continue
        if not candidate.strip():
            plan.empty += 1
            continue
        if candidate == row.translation:
            plan.unchanged += 1  # model dokunmamış; temizlik katmanı da dokunmaz
            continue
        text, issues = prepare_correction(row, candidate)
        if issues:
            plan.code_problems.append((row.id, " ".join(issues)))
            continue
        if text == row.translation:
            plan.unchanged += 1
            continue
        if text != candidate and not _same_text(text, candidate):
            plan.cleaned += 1
        if row.status == Status.APPROVED:
            plan.approved += 1
        plan.changes.append((row.id, text))
    return plan
