from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import ctypes
import ctypes.util
import platform


class MacOSHotkeyError(RuntimeError):
    """Raised when native macOS hotkey registration fails."""


CARBON_CONTROL_KEY = 1 << 12
CARBON_OPTION_KEY = 1 << 11
CARBON_SHIFT_KEY = 1 << 9
CARBON_CMD_KEY = 1 << 8

K_EVENT_CLASS_KEYBOARD = 0x6B657962
K_EVENT_HOTKEY_PRESSED = 5
K_EVENT_PARAM_DIRECT_OBJECT = 0x2D2D2D2D
TYPE_EVENT_HOTKEY_ID = 0x686B6964
DKVM_SIGNATURE = 0x444B564D

NO_ERR = 0


MODIFIER_ALIASES = {
    "control": CARBON_CONTROL_KEY,
    "ctrl": CARBON_CONTROL_KEY,
    "option": CARBON_OPTION_KEY,
    "opt": CARBON_OPTION_KEY,
    "alt": CARBON_OPTION_KEY,
    "shift": CARBON_SHIFT_KEY,
    "command": CARBON_CMD_KEY,
    "cmd": CARBON_CMD_KEY,
    "meta": CARBON_CMD_KEY,
    "super": CARBON_CMD_KEY,
}

KEY_CODES = {
    "a": 0x00,
    "s": 0x01,
    "d": 0x02,
    "f": 0x03,
    "h": 0x04,
    "g": 0x05,
    "z": 0x06,
    "x": 0x07,
    "c": 0x08,
    "v": 0x09,
    "b": 0x0B,
    "q": 0x0C,
    "w": 0x0D,
    "e": 0x0E,
    "r": 0x0F,
    "y": 0x10,
    "t": 0x11,
    "1": 0x12,
    "2": 0x13,
    "3": 0x14,
    "4": 0x15,
    "6": 0x16,
    "5": 0x17,
    "=": 0x18,
    "9": 0x19,
    "7": 0x1A,
    "-": 0x1B,
    "8": 0x1C,
    "0": 0x1D,
    "]": 0x1E,
    "o": 0x1F,
    "u": 0x20,
    "[": 0x21,
    "i": 0x22,
    "p": 0x23,
    "l": 0x25,
    "j": 0x26,
    "'": 0x27,
    "k": 0x28,
    ";": 0x29,
    "\\": 0x2A,
    ",": 0x2B,
    "/": 0x2C,
    "n": 0x2D,
    "m": 0x2E,
    ".": 0x2F,
    "`": 0x32,
    "space": 0x31,
}


@dataclass(frozen=True)
class ParsedHotkey:
    keys: str
    key_code: int
    modifiers: int


@dataclass(frozen=True)
class HotkeyBinding:
    name: str
    keys: str
    key_code: int
    modifiers: int
    command: list[str]


class EventTypeSpec(ctypes.Structure):
    _fields_ = [
        ("eventClass", ctypes.c_uint32),
        ("eventKind", ctypes.c_uint32),
    ]


class EventHotKeyID(ctypes.Structure):
    _fields_ = [
        ("signature", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
    ]


HotkeyCallback = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
)


def parse_hotkey_spec(raw: str) -> ParsedHotkey:
    parts = [part.strip().lower() for part in raw.replace("-", "+").split("+")]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        raise ValueError("hotkey must include at least one modifier and one key")

    key_name = parts[-1]
    try:
        key_code = KEY_CODES[key_name]
    except KeyError as exc:
        raise ValueError(f"unsupported hotkey key '{key_name}'") from exc

    modifiers = 0
    for modifier_name in parts[:-1]:
        try:
            modifiers |= MODIFIER_ALIASES[modifier_name]
        except KeyError as exc:
            raise ValueError(f"unsupported hotkey modifier '{modifier_name}'") from exc
    if modifiers == 0:
        raise ValueError("hotkey must include at least one modifier")
    return ParsedHotkey(keys=raw, key_code=key_code, modifiers=modifiers)


def hotkey_binding_from_config(name: str, raw: object) -> HotkeyBinding:
    if isinstance(raw, str):
        keys = raw
        command = default_command_for_hotkey(name)
    elif isinstance(raw, dict):
        keys = raw.get("keys")
        command = raw.get("command")
        if command is None:
            command = default_command_for_hotkey(name)
        if not isinstance(keys, str):
            raise ValueError(f"hotkey '{name}' must include string keys")
        if not isinstance(command, list) or not command:
            raise ValueError(f"hotkey '{name}' command must be a non-empty array")
        command = [str(part) for part in command]
    else:
        raise ValueError(f"hotkey '{name}' must be a string or table")

    parsed = parse_hotkey_spec(keys)
    return HotkeyBinding(
        name=name,
        keys=keys,
        key_code=parsed.key_code,
        modifiers=parsed.modifiers,
        command=command,
    )


def default_command_for_hotkey(name: str) -> list[str]:
    if name == "kvm":
        return ["kvm-toggle"]
    if name == "layouts":
        return ["cycle", "layouts"]
    raise ValueError(f"hotkey '{name}' must include a command")


class MacOSHotkeyRunner:
    def __init__(self, bindings: list[HotkeyBinding], handler: Callable[[HotkeyBinding], None]):
        if platform.system() != "Darwin":
            raise MacOSHotkeyError("native hotkeys are only supported on macOS")
        self.bindings = bindings
        self._handler = handler
        self._carbon = self._load_carbon()
        self._callback = HotkeyCallback(self._handle_event)
        self._bindings_by_id = {index + 1: binding for index, binding in enumerate(bindings)}
        self._registered_refs: list[ctypes.c_void_p] = []
        self._configure_functions()

    @staticmethod
    def _load_carbon() -> ctypes.CDLL:
        path = ctypes.util.find_library("Carbon")
        if path is None:
            raise MacOSHotkeyError("could not find Carbon framework")
        return ctypes.CDLL(path)

    def _configure_functions(self) -> None:
        self._carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        self._carbon.GetApplicationEventTarget.argtypes = []
        self._carbon.InstallEventHandler.restype = ctypes.c_int
        self._carbon.InstallEventHandler.argtypes = [
            ctypes.c_void_p,
            HotkeyCallback,
            ctypes.c_uint32,
            ctypes.POINTER(EventTypeSpec),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._carbon.RegisterEventHotKey.restype = ctypes.c_int
        self._carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            EventHotKeyID,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._carbon.GetEventParameter.restype = ctypes.c_int
        self._carbon.GetEventParameter.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        ]
        self._carbon.RunApplicationEventLoop.restype = None
        self._carbon.RunApplicationEventLoop.argtypes = []

    def run(self) -> None:
        event_target = self._carbon.GetApplicationEventTarget()
        if not event_target:
            raise MacOSHotkeyError("could not get macOS application event target")

        event_type = EventTypeSpec(K_EVENT_CLASS_KEYBOARD, K_EVENT_HOTKEY_PRESSED)
        handler_ref = ctypes.c_void_p()
        result = self._carbon.InstallEventHandler(
            event_target,
            self._callback,
            1,
            ctypes.byref(event_type),
            None,
            ctypes.byref(handler_ref),
        )
        self._raise_for_status(result, "InstallEventHandler")

        for index, binding in self._bindings_by_id.items():
            hotkey_ref = ctypes.c_void_p()
            hotkey_id = EventHotKeyID(DKVM_SIGNATURE, index)
            result = self._carbon.RegisterEventHotKey(
                binding.key_code,
                binding.modifiers,
                hotkey_id,
                event_target,
                0,
                ctypes.byref(hotkey_ref),
            )
            self._raise_for_status(result, f"RegisterEventHotKey {binding.keys}")
            self._registered_refs.append(hotkey_ref)

        self._carbon.RunApplicationEventLoop()

    def _handle_event(
        self,
        _next_handler: ctypes.c_void_p,
        event: ctypes.c_void_p,
        _user_data: ctypes.c_void_p,
    ) -> int:
        hotkey_id = EventHotKeyID()
        actual_size = ctypes.c_uint32()
        result = self._carbon.GetEventParameter(
            event,
            K_EVENT_PARAM_DIRECT_OBJECT,
            TYPE_EVENT_HOTKEY_ID,
            None,
            ctypes.sizeof(hotkey_id),
            ctypes.byref(actual_size),
            ctypes.byref(hotkey_id),
        )
        if result != NO_ERR:
            return result
        binding = self._bindings_by_id.get(hotkey_id.id)
        if binding is None:
            return NO_ERR
        self._handler(binding)
        return NO_ERR

    @staticmethod
    def _raise_for_status(result: int, operation: str) -> None:
        if result != NO_ERR:
            raise MacOSHotkeyError(f"{operation} failed with OSStatus {result}")
