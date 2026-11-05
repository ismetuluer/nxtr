"""SD karttaki Kong Survivor Instinct modunu denetler.

Neden gerekli: mod SD karta konmuş görünse de oyun İngilizce açılabiliyor. Bunun nedeni
neredeyse her zaman dosyaların Atmosphère'in aradığı yerde olmamasıdır. Bu betik SD kartı
(veya verilen klasörü) **salt okunur** olarak gezer ve somut farkı söyler:

- `atmosphere/contents/<TitleID>/romfs` doğru derinlikte mi, yoksa bir kat fazla mı?
- mod klasörü `contents` altına olduğu gibi mi kopyalanmış?
- `romfs_metadata.bin` var mı (Atmosphère bu dosyayı yalnızca modu okuduğunda oluşturur)?
- SD'deki dosyalar bilgisayardaki modla birebir aynı mı (eksik/eski kopya var mı)?
- `atmosphere/titles` (eski Atmosphère) kalıntısı var mı?

Kullanım:

    python sd_kontrol.py                # takılı SD kartları kendisi bulur
    python sd_kontrol.py --root E:/     # belirli bir sürücü/klasör
    python sd_kontrol.py --mod "..."    # karşılaştırılacak mod klasörü

Hiçbir dosya yazmaz, silmez.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import string
import sys
from dataclasses import dataclass
from pathlib import Path

#: Bu modun hedef oyunu (ABD sürümü). Bölge farklıysa son dört hane değişir.
TITLE_ID = "0100D400244D4000"
TITLE_PREFIX = "0100D400244D"
MOD_NAME = "Kong Survivor Instinct Türkçe"

OK = "[OK]"
BAD = "[!!]"
WARN = "[??]"

#: Kontrol edilen modun bilgisayardaki son hâli (yoksa karşılaştırma atlanır).
DEFAULT_MOD = Path("Kong Survivor Instinct [NSZ]") / MOD_NAME


@dataclass(frozen=True)
class Entry:
    size: int
    digest: str


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def snapshot(root: Path) -> dict[str, Entry]:
    """Klasördeki tüm dosyaları göreli yol → (boyut, sha256) olarak toplar."""
    out: dict[str, Entry] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = Entry(path.stat().st_size, sha256(path))
    return out


def mounted_roots() -> list[Path]:
    """Atmosphère/Switch izi taşıyan sürücü kökleri."""
    roots: list[Path] = []
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:/")
        if not drive.exists():
            continue
        try:
            names = {p.name.lower() for p in drive.iterdir() if p.is_dir()}
        except OSError:
            continue
        if names & {"atmosphere", "nintendo", "emummc", "switch", "hekate_ipl.ini"}:
            roots.append(drive)
    return roots


def find_mod() -> Path | None:
    here = Path(__file__).resolve().parent
    for base in (here, Path.cwd()):
        candidate = base / DEFAULT_MOD
        if (candidate / "atmosphere").is_dir():
            return candidate
    return None


def human(n: int) -> str:
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{n} B"


def _title_dirs(contents: Path) -> list[Path]:
    try:
        return sorted(p for p in contents.iterdir() if p.is_dir())
    except OSError:
        return []


def check_root(root: Path, mod_root: Path | None) -> list[str]:
    lines: list[str] = [f"=== {root} ==="]
    atmosphere = root / "atmosphere"
    if not atmosphere.is_dir():
        lines.append(f"{BAD} Bu sürücüde 'atmosphere' klasörü yok: {atmosphere}")
        return lines

    contents = atmosphere / "contents"
    lines.append(f"{OK} atmosphere klasörü var.")

    # Eski Atmosphère yerleşimi: modu okumaz.
    if (atmosphere / "titles").is_dir():
        lines.append(
            f"{WARN} 'atmosphere/titles' klasörü var (eski Atmosphère yerleşimi). "
            "Güncel Atmosphère modları 'atmosphere/contents' altından okur; "
            "'titles' içindeki eski kopya yok sayılır."
        )

    if not contents.is_dir():
        lines.append(f"{BAD} 'atmosphere/contents' klasörü yok.")
        return lines

    dirs = _title_dirs(contents)
    # En sık hata: mod klasörünün kendisi contents altına kopyalanmış.
    nested = [p for p in dirs if (p / "atmosphere").is_dir()]
    for path in nested:
        lines.append(
            f"{BAD} Yanlış katlama: '{path.name}' içinde tekrar 'atmosphere' var. "
            f"Kopyalanması gereken tek şey içindeki 'atmosphere' klasörüdür; "
            f"'{path}' SD'den silinmelidir."
        )

    channels = {p.name: p for p in dirs}
    similar = [name for name in channels if name.startswith(TITLE_PREFIX)]
    other = [name for name in channels if len(name) == 16 and name.isalnum() and name not in similar]
    if similar and TITLE_ID not in channels:
        lines.append(
            f"{BAD} 'contents' altında {TITLE_ID} yok; benzer TitleID'ler: {', '.join(sorted(similar))}. "
            "Konsoldaki oyun farklı bölge olabilir; modu o TitleID ile yeniden üretin."
        )

    tid_dir = channels.get(TITLE_ID)
    if tid_dir is None:
        lines.append(f"{BAD} 'atmosphere/contents/{TITLE_ID}' klasörü yok.")
        if similar:
            lines.append(f"{WARN} Bu sürücüdeki oyun klasörleri: {', '.join(sorted(similar))}")
        if other:
            lines.append(f"{WARN} Diğer oyun klasörleri (ilk 8): {', '.join(sorted(other)[:8])}")
        return lines

    lines.append(f"{OK} 'contents/{TITLE_ID}' var.")

    # 'romfs' atlanmış kopya: doğrudan TitleID altında 'Data'.
    romfs = tid_dir / "romfs"
    if not romfs.is_dir():
        if (tid_dir / "Data").is_dir():
            lines.append(
                f"{BAD} 'romfs' klasörü yok ama doğrudan 'Data' var. "
                f"Doğru yer: 'atmosphere/contents/{TITLE_ID}/romfs/Data/...'"
            )
        else:
            lines.append(f"{BAD} 'romfs' klasörü yok: {romfs}")
        return lines

    if (romfs / "atmosphere").is_dir():
        lines.append(f"{BAD} 'romfs' içinde tekrar 'atmosphere' var (iki kez kopyalanmış).")

    files = {p.relative_to(romfs).as_posix(): p for p in romfs.rglob("*") if p.is_file()}
    total = sum(p.stat().st_size for p in files.values())
    lines.append(f"{OK} romfs: {len(files)} dosya, {human(total)}")

    expected_name = MOD_NAME + " klasöründeki"
    if mod_root is not None:
        want = mod_root / "atmosphere" / "contents" / TITLE_ID / "romfs"
        if want.is_dir():
            expected = snapshot(want)
            lines.append(f"{OK} Karşılaştırma: bilgisayardaki mod ({len(expected)} dosya).")
            missing = sorted(set(expected) - set(files))
            extra = sorted(set(files) - set(expected))
            differ: list[str] = []
            for rel in sorted(set(files) & set(expected)):
                sd_size = files[rel].stat().st_size
                if sd_size != expected[rel].size or sha256(files[rel]) != expected[rel].digest:
                    differ.append(rel)
            for rel in missing:
                lines.append(f"{BAD} SD'de eksik: {rel} ({human(expected[rel].size)})")
            if differ:
                for rel in differ:
                    lines.append(
                        f"{BAD} SD'de farklı/eski: {rel} "
                        f"(SD {human(files[rel].stat().st_size)}, "
                        f"mod {human(expected[rel].size)})"
                    )
            if extra:
                lines.append(f"{WARN} Modda olmayan ek dosya: {', '.join(extra[:5])}")
            if not (missing or differ):
                lines.append(f"{OK} SD'deki {len(expected)} dosya bilgisayardaki modla birebir aynı.")
        else:
            lines.append(f"{WARN} Bilgisayarda {expected_name} romfs bulunamadı; karşılaştırma atlandı.")
    else:
        lines.append(f"{WARN} Bilgisayarda {expected_name} mod bulunamadı; karşılaştırma atlandı.")

    catalog = files.get("Data/StreamingAssets/aa/catalog.json")
    if catalog is None:
        lines.append(
            f"{BAD} 'Data/StreamingAssets/aa/catalog.json' yok. Bu dosya olmadan oyun değiştirilmiş "
            "paketleri CRC denetimi yüzünden yüklemez (İngilizce kalır). Modu yeniden dışa aktarıp "
            "klasörün tamamını yeniden kopyalayın."
        )

    bundle = files.get(
        "Data/StreamingAssets/aa/Switch/localization-string-tables-english(unitedstates)(en-us)_assets_all.bundle"
    )
    if bundle is None:
        lines.append(f"{BAD} İngilizce metin paketi SD'de yok.")
    else:
        blob = bundle.read_bytes()
        if b"\xc4\xb1" in blob or b"\xc4\x9f" in blob or b"\xc5\x9f" in blob:
            lines.append(f"{OK} Metin paketinde Türkçe karakterler var (ı/ğ/ş).")
        else:
            lines.append(f"{BAD} Metin paketinde Türkçe karakter bulunamadı; dosya çevrilmemiş sürüm olabilir.")

    # Atmosphère, modu okuduğunda bu dosyayı oyunun ilk açılışında oluşturur.
    metadata = tid_dir / "romfs_metadata.bin"
    if metadata.is_file():
        when = datetime.datetime.fromtimestamp(metadata.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        lines.append(
            f"{OK} 'romfs_metadata.bin' var (son yazma: {when}). "
            "Atmosphère bu klasörü okumuş; dosya oyunu her açtığınızda güncellenir."
        )
        if catalog is not None and metadata.stat().st_mtime < catalog.stat().st_mtime:
            lines.append(
                f"{WARN} 'romfs_metadata.bin' mod dosyalarından daha eski: mod kopyalandıktan sonra "
                "oyun açılmamış olabilir. Oyunu tamamen kapatıp yeniden açın."
            )
    else:
        lines.append(
            f"{WARN} 'romfs_metadata.bin' yok: Atmosphère bu oyun için modu henüz okumamış. "
            "Oyunu tamamen kapatıp (Home tuşu değil: simgeye X → Kapat) yeniden açın; "
            "dosya yine oluşmazsa SD'deki yol veya TitleID yanlıştır."
        )

    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SD karttaki modu denetler (salt okunur).")
    parser.add_argument("--root", type=Path, help="SD kartın sürücü kökü (ör. E:\\) veya klasör")
    parser.add_argument("--mod", type=Path, help="bilgisayardaki mod klasörü")
    args = parser.parse_args(argv)

    mod_root = args.mod or find_mod()
    roots = [args.root] if args.root else mounted_roots()
    print("NXTR — SD kart denetimi")
    print(f"Beklenen TitleID: {TITLE_ID}")
    if mod_root is not None:
        print(f"Karşılaştırma modu: {mod_root}")
    else:
        print("Karşılaştırma modu: bulunamadı (yalnızca SD içeriği denetlenecek)")
    print()

    if not roots:
        print(f"{BAD} SD kart bulunamadı. Kartı bilgisayara takın veya --root ile yolu verin.")
        return 2

    exit_code = 0
    for root in roots:
        try:
            lines = check_root(Path(root), mod_root)
        except OSError as exc:
            print(f"{BAD} {root} okunamadı: {exc}")
            exit_code = 1
            continue
        print("\n".join(lines))
        print()
        if any(line.startswith(BAD) for line in lines):
            exit_code = 1

    print("Not: Bu betik hiçbir dosyayı değiştirmez.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
