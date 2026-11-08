"""Single-instance через именованный мьютекс Windows.

Без внешних зависимостей — только ctypes из stdlib. Весь Qt-независимый
код вынесен сюда, чтобы его можно было покрыть P0-тестом.
"""

import ctypes
import ctypes.wintypes as wt

ERROR_ALREADY_EXISTS = 183


def acquire_mutex(name: str):
    """Создать/открыть именованный мьютекс. Вернуть хэндл или None, если
    мьютекс уже захвачен другим процессом."""
    CreateMutexW = ctypes.windll.kernel32.CreateMutexW
    CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
    CreateMutexW.restype = wt.HANDLE

    handle = CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        ctypes.windll.kernel32.CloseHandle(handle)
        return None
    return handle


def release_mutex(handle):
    """Закрыть хэндл мьютекса."""
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)


class SingleInstanceGuard:
    """Контекстный менеджер: захватывает мьютекс на время жизни объекта."""

    MUTEX_NAME = "Local\\Logachoff_LogaShot_SingleInstance_v0_1"

    def __init__(self, name: str | None = None):
        self.name = name or self.MUTEX_NAME
        self._handle = None

    def __enter__(self):
        self._handle = acquire_mutex(self.name)
        return self

    def __exit__(self, exc_type, exc, tb):
        release_mutex(self._handle)
        return False

    @property
    def is_another_running(self) -> bool:
        return self._handle is None
