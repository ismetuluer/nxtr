"""Çökme günlüğü: uygulama sert çökerse (abort, erişim ihlali) Python yığını günlük klasörüne yazılır."""

from __future__ import annotations

import faulthandler
import subprocess
import sys
from pathlib import Path

import pytest

from nxceviri.gui import app as app_module


def test_enable_crash_log_writes_to_the_log_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "log_dir", lambda: tmp_path)
    handle = app_module.enable_crash_log()
    try:
        assert handle is not None
        assert faulthandler.is_enabled()
        assert (tmp_path / "cokme.log").is_file()
    finally:
        faulthandler.disable()
        if handle is not None:
            handle.close()


def test_crash_log_survives_unwritable_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocked = tmp_path / "dosya"
    blocked.write_text("klasör değil", encoding="utf-8")
    monkeypatch.setattr(app_module, "log_dir", lambda: blocked / "alt")
    assert app_module.enable_crash_log() is None  # uygulama açılışı bozulmaz


def test_a_real_abort_leaves_a_python_traceback(tmp_path: Path) -> None:
    """Ayrı süreçte abort() çağrılınca dosyada Python yığını (hangi işlevde olduğu) bulunur."""
    code = (
        "import sys, os\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})\n"
        "from pathlib import Path\n"
        "from nxceviri.gui import app\n"
        f"app.log_dir = lambda: Path({str(tmp_path)!r})\n"
        "app.enable_crash_log()\n"
        "def yapilan_is():\n"
        "    os.abort()\n"
        "yapilan_is()\n"
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=False, capture_output=True, timeout=60)
    text = (tmp_path / "cokme.log").read_text(encoding="utf-8", errors="replace")
    assert "yapilan_is" in text
