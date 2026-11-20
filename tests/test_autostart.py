"""P0: автозагрузка с Windows (фича v0.2).

Реестр подменён мини-реализацией winreg: проверяем именно то, что уходит в
HKCU\\...\\Run — одна ветка, одно значение LogaShot. Настоящий реестр трогает
только живой смоук.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

import autostart

COMMAND = '"C:\\Apps\\LogaShot\\LogaShot.exe"'


class _FakeKey:
    """Хэндл ветки Run: хранит ссылку на сам поддельный реестр."""

    def __init__(self, registry):
        self.registry = registry

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeRegistry:
    """winreg-совместимый минимум для одной ветки Run."""

    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 0x0002
    REG_SZ = 1

    def __init__(self, present=True):
        self.present = present  # ветка Run существует
        self.values = {}

    def OpenKey(self, root, path, reserved=0, access=0):
        if not self.present:
            raise FileNotFoundError(2, "нет ветки", path)
        assert path == autostart.RUN_KEY
        return _FakeKey(self)

    def CreateKeyEx(self, root, path, reserved=0, access=0):
        self.present = True
        return _FakeKey(self)

    def QueryValueEx(self, key, name):
        if name not in key.registry.values:
            raise FileNotFoundError(2, "нет значения", name)
        return key.registry.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):
        assert kind == self.REG_SZ
        key.registry.values[name] = value

    def DeleteValue(self, key, name):
        if name not in key.registry.values:
            raise FileNotFoundError(2, "нет значения", name)
        del key.registry.values[name]


@pytest.fixture
def registry(monkeypatch):
    fake = FakeRegistry()
    monkeypatch.setattr(autostart, "winreg", fake)
    return fake


@pytest.fixture
def command(monkeypatch):
    """Путь к exe под контролем: не зависит от машины прогона."""
    monkeypatch.setattr(autostart, "exe_command", lambda: COMMAND)
    return COMMAND


def test_sync_creates_key_when_enabled(registry, command):
    assert autostart.current_value() is None
    assert autostart.sync(True) == autostart.CREATED
    assert registry.values[autostart.VALUE_NAME] == COMMAND


def test_sync_removes_key_when_disabled(registry, command):
    registry.values[autostart.VALUE_NAME] = COMMAND
    assert autostart.sync(False) == autostart.REMOVED
    assert autostart.VALUE_NAME not in registry.values
    assert autostart.current_value() is None


def test_sync_updates_stale_path(registry, command):
    """Переехавшая portable-папка: путь в ключе не совпадает — обновляем."""
    registry.values[autostart.VALUE_NAME] = '"D:\\Old\\LogaShot.exe"'
    assert autostart.sync(True) == autostart.UPDATED
    assert registry.values[autostart.VALUE_NAME] == COMMAND


def test_sync_keeps_matching_path(registry, command):
    registry.values[autostart.VALUE_NAME] = COMMAND
    assert autostart.sync(True) == autostart.UNCHANGED
    assert registry.values[autostart.VALUE_NAME] == COMMAND


def test_sync_disabled_creates_nothing(registry, command):
    """autostart=false: ключа нет — и он не появляется."""
    assert autostart.sync(False) == autostart.UNCHANGED
    assert registry.values == {}


def test_sync_tolerates_missing_branch(registry, command):
    """Ветки Run нет вовсе — выключение не падает (идемпотентность)."""
    registry.present = False
    assert autostart.sync(False) == autostart.UNCHANGED


def test_exe_command_points_to_running_exe(monkeypatch):
    """Путь — фактический, без хардкода: сборка = сам exe, исходники = python."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    exe = Path(sys.executable).resolve()
    assert autostart.exe_command() == f'"{exe}"'


def test_exe_command_in_sources_quotes_entry_point(monkeypatch):
    """Из исходников: pythonw + main.py рядом с модулем, а не sys.argv[0]."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    command_str = autostart.exe_command()
    entry = Path(autostart.__file__).resolve().parent / "main.py"
    assert command_str.endswith(f'"{entry}"')
    assert command_str.startswith('"')
