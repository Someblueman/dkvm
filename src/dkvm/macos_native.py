from __future__ import annotations

import ctypes
import ctypes.util
import platform
import time
from typing import Any


class MacOSNativeDdcError(RuntimeError):
    """Raised when native macOS DDC access fails."""


DDC_CHIP_ADDRESS = 0x37
DDC_DATA_ADDRESS = 0x51
DDC_WAIT_SECONDS = 0.01
DDC_WRITE_ITERATIONS = 2


class MacOSNativeDdc:
    def __init__(self) -> None:
        self._core_display = self._load_library("CoreDisplay")
        self._core_foundation = self._load_library("CoreFoundation")
        self._io_av_service_create = self._function(
            "IOAVServiceCreate",
            restype=ctypes.c_void_p,
            argtypes=[ctypes.c_void_p],
        )
        self._io_av_service_write_i2c = self._function(
            "IOAVServiceWriteI2C",
            restype=ctypes.c_int,
            argtypes=[
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_uint32,
            ],
        )
        self._cf_release = self._core_foundation.CFRelease
        self._cf_release.restype = None
        self._cf_release.argtypes = [ctypes.c_void_p]

    @staticmethod
    def supported_platform() -> bool:
        return platform.system() == "Darwin" and platform.machine() == "arm64"

    @classmethod
    def available(cls) -> bool:
        if not cls.supported_platform():
            return False
        try:
            cls()
        except Exception:
            return False
        return True

    def probe(self) -> None:
        if not self.supported_platform():
            raise MacOSNativeDdcError("native macOS DDC requires Apple Silicon")
        service = self._create_default_service()
        self._cf_release(service)

    def write_vcp(self, display: str | None, feature: int, value: int) -> None:
        # TODO(agent): add IORegistry display matching so native DDC can target
        # more than the default service.
        if display not in (None, "", "1"):
            raise MacOSNativeDdcError(
                "native macOS DDC currently supports the default display only; "
                "omit --display or use --display 1"
            )
        if not 0 <= feature <= 0xFF:
            raise MacOSNativeDdcError("VCP feature must fit in one byte")
        if not 0 <= value <= 0xFFFF:
            raise MacOSNativeDdcError("VCP value must fit in two bytes")

        service = self._create_default_service()
        try:
            packet = self._write_packet(feature, value)
            for _ in range(DDC_WRITE_ITERATIONS):
                time.sleep(DDC_WAIT_SECONDS)
                result = self._io_av_service_write_i2c(
                    service,
                    DDC_CHIP_ADDRESS,
                    DDC_DATA_ADDRESS,
                    packet,
                    len(packet),
                )
                if result != 0:
                    raise MacOSNativeDdcError(
                        f"DDC write failed with IOReturn {result}"
                    )
        finally:
            self._cf_release(service)

    def _create_default_service(self) -> ctypes.c_void_p:
        service = self._io_av_service_create(None)
        if not service:
            raise MacOSNativeDdcError("could not create a macOS IOAVService")
        return service

    @staticmethod
    def _write_packet(feature: int, value: int) -> ctypes.Array[ctypes.c_uint8]:
        value_hi = value >> 8
        value_lo = value & 0xFF
        checksum = (
            0x6E
            ^ DDC_DATA_ADDRESS
            ^ 0x84
            ^ 0x03
            ^ feature
            ^ value_hi
            ^ value_lo
        )
        return (ctypes.c_uint8 * 6)(0x84, 0x03, feature, value_hi, value_lo, checksum)

    @staticmethod
    def _load_library(name: str) -> ctypes.CDLL:
        path = ctypes.util.find_library(name)
        if path is None:
            raise MacOSNativeDdcError(f"could not find {name} framework")
        return ctypes.CDLL(path)

    def _function(
        self,
        name: str,
        *,
        restype: Any,
        argtypes: list[Any],
    ) -> Any:
        try:
            function = getattr(self._core_display, name)
        except AttributeError as exc:
            raise MacOSNativeDdcError(f"missing macOS symbol {name}") from exc
        function.restype = restype
        function.argtypes = argtypes
        return function
