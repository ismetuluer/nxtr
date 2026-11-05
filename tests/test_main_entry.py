"""`python -m nxceviri` girişi: yalnızca bilinen komut adı araçlara gider, gerisi arayüzü açar."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

from nxceviri import arac


def _load_entry(monkeypatch: pytest.MonkeyPatch, tool_calls: list[list[str]], gui_calls: list[int]) -> ModuleType:

    def fake_tools(argv: Sequence[str]) -> int:
        tool_calls.append(list(argv))
        return 0

    def fake_window() -> int:
        gui_calls.append(1)
        return 0

    monkeypatch.setattr(arac, "main", fake_tools)
    fake_gui = ModuleType("nxceviri.gui.app")
    fake_gui.main = fake_window  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nxceviri.gui.app", fake_gui)
    sys.modules.pop("nxceviri.__main__", None)
    return importlib.import_module("nxceviri.__main__")


@pytest.mark.parametrize("args", [["eklentiler"], ["teshis", "x.nsp"], ["--help"]])
def test_known_commands_go_to_tools(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    tools: list[list[str]] = []
    gui: list[int] = []
    entry = _load_entry(monkeypatch, tools, gui)
    assert entry._run(args) == 0
    assert tools == [args]
    assert not gui


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["D:/Oyunlar/oyun.nsp"],
        ["-platform", "windows"],
        [str(Path("a") / "oyun.nsz")],
        ["proje.nxproj"],
        ["bilinmeyen"],
    ],
)
def test_other_arguments_open_the_window(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    tools: list[list[str]] = []
    gui: list[int] = []
    entry = _load_entry(monkeypatch, tools, gui)
    assert entry._run(args) == 0
    assert gui == [1]
    assert not tools
