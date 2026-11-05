"""API anahtarları gibi gizli değerlerin saklanması.

Gizli değerler Windows Kimlik Bilgisi Yöneticisi'nde (`keyring`) tutulur; proje dosyasına,
ayar dosyasına veya log'a asla yazılmaz (CLAUDE.md §4.2).
"""

from __future__ import annotations

import logging
from typing import Protocol

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from nxceviri.core.errors import NxError

log = logging.getLogger(__name__)

SERVICE = "NXCeviriStudyosu"
DEEPL_API_KEY = "deepl_api_key"
GITHUB_UPDATE_KEY = "github_token"  # uygulama güncellemesi için, yalnızca depoyu okuyabilen anahtar


class SecretError(NxError):
    """Gizli değer okunamadı veya kaydedilemedi."""


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class KeyringStore:
    """Windows Kimlik Bilgisi Yöneticisi (keyring) üzerinde saklama."""

    def __init__(self, service: str = SERVICE) -> None:
        self.service = service

    def get(self, name: str) -> str | None:
        try:
            return keyring.get_password(self.service, name)
        except KeyringError as exc:
            raise SecretError(
                "Kayıtlı API anahtarı okunamadı.",
                f"Windows Kimlik Bilgisi Yöneticisi'ne erişilemedi ({type(exc).__name__}).",
            ) from None

    def set(self, name: str, value: str) -> None:
        try:
            keyring.set_password(self.service, name, value)
        except KeyringError as exc:
            raise SecretError(
                "API anahtarı kaydedilemedi.",
                f"Windows Kimlik Bilgisi Yöneticisi'ne yazılamadı ({type(exc).__name__}).",
            ) from None
        log.info("Gizli değer kaydedildi: %s", name)  # değerin kendisi asla loglanmaz

    def delete(self, name: str) -> None:
        try:
            keyring.delete_password(self.service, name)
        except PasswordDeleteError:
            return  # zaten yok
        except KeyringError as exc:
            raise SecretError("API anahtarı silinemedi.", f"({type(exc).__name__})") from None
        log.info("Gizli değer silindi: %s", name)


class MemoryStore:
    """Bellekte saklama (testler ve keyring'in kullanılamadığı durumlar için)."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def __repr__(self) -> str:
        return f"<MemoryStore: {len(self._values)} değer>"

    def get(self, name: str) -> str | None:
        return self._values.get(name)

    def set(self, name: str, value: str) -> None:
        self._values[name] = value

    def delete(self, name: str) -> None:
        self._values.pop(name, None)
