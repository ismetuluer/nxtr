"""Dosya → Son Projeler: son açılan veya kaydedilen proje dosyalarının listesi (QSettings'te)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMenu

#: Listenin uzunluğu.
RECENT_LIMIT = 8
RECENT_KEY = "ui/recent_projects"


class RecentProjects:
    def __init__(self, settings: QSettings) -> None:
        self.settings = settings

    def paths(self) -> list[Path]:
        value = self.settings.value(RECENT_KEY, [])
        items = [value] if isinstance(value, str) else value if isinstance(value, list) else []
        return [Path(str(v)) for v in items if v]

    def remember(self, path: Path) -> None:
        paths = [path, *(p for p in self.paths() if p != path)][:RECENT_LIMIT]
        self.settings.setValue(RECENT_KEY, [str(p) for p in paths])

    def clear(self) -> None:
        self.settings.setValue(RECENT_KEY, [])

    def fill_menu(self, menu: QMenu, open_project: Callable[[Path], object]) -> None:
        """Menüyü, diskte hâlâ duran projelerle yeniden doldurur."""
        menu.clear()
        paths = [p for p in self.paths() if p.is_file()]
        if not paths:
            menu.addAction("Henüz proje açılmadı").setEnabled(False)
            return
        for i, path in enumerate(paths, 1):
            action = menu.addAction(f"&{i}  {path.stem}")
            action.setToolTip(str(path))
            action.setStatusTip(str(path))
            action.triggered.connect(lambda _checked=False, p=path: open_project(p))
        menu.addSeparator()
        menu.addAction("Listeyi Temizle").triggered.connect(self.clear)
