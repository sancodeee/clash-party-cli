"""Platform-specific system proxy control."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

from cli_anything.clash_party.core.models import CliError


@dataclass(frozen=True)
class ProxySettings:
    """Describe manual system proxy settings."""

    host: str
    port: int
    bypass: tuple[str, ...]


class SystemProxy:
    """Control the current user's system proxy."""

    def enable(self, settings: ProxySettings) -> None:
        """Enable a manual proxy."""
        if sys.platform != "win32":
            raise CliError(
                "unsupported_platform",
                "System proxy control currently supports Windows.",
                4,
            )
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(
                key,
                "ProxyServer",
                0,
                winreg.REG_SZ,
                f"{settings.host}:{settings.port}",
            )
            winreg.SetValueEx(
                key,
                "ProxyOverride",
                0,
                winreg.REG_SZ,
                ";".join(settings.bypass),
            )
            try:
                winreg.DeleteValue(key, "AutoConfigURL")
            except FileNotFoundError:
                pass
        self._notify_windows()

    def disable(self) -> None:
        """Disable manual and PAC proxy settings."""
        if sys.platform != "win32":
            raise CliError(
                "unsupported_platform",
                "System proxy control currently supports Windows.",
                4,
            )
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
            try:
                winreg.DeleteValue(key, "AutoConfigURL")
            except FileNotFoundError:
                pass
        self._notify_windows()

    @staticmethod
    def _notify_windows() -> None:
        internet_set_option = ctypes.windll.Wininet.InternetSetOptionW
        internet_set_option(0, 39, 0, 0)
        internet_set_option(0, 37, 0, 0)
