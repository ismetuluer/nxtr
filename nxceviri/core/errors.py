"""Uygulama genelindeki hata türleri.

Her hata, arayüzde doğrudan gösterilebilecek Türkçe bir mesaj taşır: ne olduğu
(`message`) ve kullanıcının ne yapması gerektiği (`hint`). Mesajlara asla anahtar
değeri veya dosya içeriği konmaz.
"""

from __future__ import annotations


class NxError(Exception):
    """Kullanıcıya gösterilebilir hataların ortak tabanı."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def user_text(self) -> str:
        """Arayüzde gösterilecek tam metin."""
        if self.hint:
            return f"{self.message}\n\n{self.hint}"
        return self.message


class OperationCancelled(NxError):
    """Kullanıcı işlemi iptal etti."""

    def __init__(self) -> None:
        super().__init__("İşlem iptal edildi.")


class KeyFileError(NxError):
    """Anahtar dosyası okunamadı, bozuk veya eksik."""


class MissingKeyError(NxError):
    """Bir içeriği çözmek için gereken anahtar bulunamadı."""


class ContainerError(NxError):
    """Oyun dosyası (NSP/NSZ/NCA/RomFS) bozuk veya beklenen yapıda değil."""


class UnsupportedFormatError(ContainerError):
    """Dosya geçerli görünüyor ama bu biçim henüz desteklenmiyor."""


class ArchiveError(NxError):
    """İç arşiv (SARC, Yaz0, ZSTD) açılamadı."""


class ProjectError(NxError):
    """Proje dosyası (.nxproj) açılamadı veya kaydedilemedi."""
