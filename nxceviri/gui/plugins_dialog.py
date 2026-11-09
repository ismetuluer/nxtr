"""Araçlar → Eklentiler: yüklü eklentilerin listesi, hataları ve "Eklenti Ekle…"."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nxceviri import __version__
from nxceviri.core.formats.base import FormatPlugin
from nxceviri.core.plugins.install import PluginExistsError, PluginInstallError, install_plugin
from nxceviri.core.plugins.loader import PluginInfo, PluginReport, user_plugin_dirs
from nxceviri.gui.widgets import Banner, button, label, title_row

COLUMNS = ("Ad", "Sürüm", "Yazar", "Kaynak", "Durum")
SOURCE_BUILTIN = "Yerleşik"
SOURCE_USER = "Kullanıcı"
STATUS_OK = "Yüklü"
#: Satırın tam ayrıntısı (hata, uyarı, konum) için kullanılan veri rolü.
_DETAIL_ROLE = Qt.ItemDataRole.UserRole
_FOLDER_ROLE = Qt.ItemDataRole.UserRole + 1


def _open_folder(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class PluginsDialog(QDialog):
    """Eklenti listesi. Eklenti ekleme, uygulama yeniden başlayınca etkinleşir (çalışırken yeniden yükleme yoktur)."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        report: PluginReport,
        builtin: Sequence[FormatPlugin],
        install_dir: Path | None = None,
        opener: Callable[[Path], None] = _open_folder,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Eklentiler")
        self.setMinimumWidth(660)
        self._install_dir = install_dir if install_dir is not None else user_plugin_dirs()[0]
        self._opener = opener

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(
            title_row(
                "Biçim eklentileri",
                "Eklentiler, yerleşik desteği olmayan oyunların metin biçimlerini ekler. "
                "Eklenti bilgisayarınızda kod çalıştırır; yalnızca güvendiğiniz kişiden eklenti kurun.",
                "cardTitle",
            )
        )
        self.banner = Banner()
        lay.addWidget(self.banner)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(220)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        lay.addWidget(self.table)
        self.detail = label("", "muted", wrap=True)
        lay.addWidget(self.detail)

        buttons = QHBoxLayout()
        self.add_button = button("Eklenti Ekle…", "primary")
        menu = QMenu(self.add_button)
        menu.addAction("Zip dosyasından…", self.add_from_zip)
        menu.addAction("Klasörden…", self.add_from_folder)
        self.add_button.setMenu(menu)
        self.open_button = button("Klasörü Aç")
        self.open_button.clicked.connect(self.open_selected_folder)
        close = button("Kapat")
        close.clicked.connect(self.accept)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        lay.addLayout(buttons)

        for info in report.infos:
            self._add_user_row(info)
        for plugin in builtin:
            self._add_row((plugin.label, __version__, "NXTR", SOURCE_BUILTIN, STATUS_OK), "", None)
        if not report.infos:
            self.detail.setText(
                "Henüz kullanıcı eklentisi yok. “Eklenti Ekle…” ile bir zip ya da klasör ekleyebilirsiniz."
            )

    def _add_user_row(self, info: PluginInfo) -> None:
        status = info.hata or STATUS_OK
        notes = [info.aciklama, info.uyari, info.hata, f"Konum: {info.yol}" if info.yol else ""]
        if info.oyunlar:
            notes.insert(1, "Oyunlar: " + ", ".join(info.oyunlar))
        if info.golge:
            status = "Gölgelendi (öncelikli klasördeki kopya kullanılıyor)"
        elif info.uyari and not info.hata:
            status = f"{STATUS_OK} (yerleşiğin yerini aldı)"
        detail = "\n".join(n for n in notes if n)
        self._add_row((info.ad, info.surum, info.yazar, SOURCE_USER, status), detail, info.yol)

    def _add_row(self, columns: tuple[str, ...], detail: str, folder: Path | None) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, text in enumerate(columns):
            item = QTableWidgetItem(text)
            item.setData(_DETAIL_ROLE, detail)
            item.setData(_FOLDER_ROLE, str(folder) if folder else "")
            if col == len(COLUMNS) - 1:
                item.setToolTip(text)
            self.table.setItem(row, col, item)

    def selected_folder(self) -> Path | None:
        items = self.table.selectedItems()
        if not items:
            return None
        text = str(items[0].data(_FOLDER_ROLE))
        return Path(text) if text else None

    def _selection_changed(self) -> None:
        items = self.table.selectedItems()
        self.detail.setText(str(items[0].data(_DETAIL_ROLE)) if items else "")

    def open_selected_folder(self) -> None:
        """Seçili kullanıcı eklentisinin klasörünü; seçim yoksa eklentilerin kurulduğu klasörü açar."""
        folder = self.selected_folder()
        if folder is None:
            self._install_dir.mkdir(parents=True, exist_ok=True)
            folder = self._install_dir
        self._opener(folder)

    def add_from_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Eklenti zip dosyasını seç", "", "Eklenti (*.zip)")
        if path:
            self.install(Path(path))

    def add_from_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Eklenti klasörünü seç")
        if path:
            self.install(Path(path))

    def install(self, source: Path) -> bool:
        """Zip ya da klasörü kurar; sonucu bantta söyler. Başarılıysa True."""
        try:
            try:
                target = install_plugin(source, self._install_dir)
            except PluginExistsError as exc:
                answer = QMessageBox.question(
                    self, "Eklentiyi değiştir", f"{exc.message}\n\nEskisinin yerine bu sürüm kurulsun mu?"
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return False
                target = install_plugin(source, self._install_dir, replace=True)
        except PluginInstallError as exc:
            self.banner.show_message("danger", exc.user_text())
            return False
        self.banner.show_message(
            "success", f"Eklenti kuruldu: {target.name}. Etkinleşmesi için uygulamayı yeniden başlatın."
        )
        return True
