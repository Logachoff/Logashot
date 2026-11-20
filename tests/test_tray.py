"""P1: меню трея и окно настроек без захвата.

Пункт «Настройки» стоит между «Снять скриншот» и «Выход» и открывает то же
окно, что шестерёнка панели; изменения применяются на лету.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import settings as s
import tray


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def portable(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "_app_dir", lambda: tmp_path)
    (tmp_path / "portable").touch()
    s.reset_store()
    yield tmp_path
    s.reset_store()


def test_tray_menu_has_settings_between(app):
    calls = []
    icon = tray.TrayIcon(QIcon(), on_capture=lambda: calls.append("capture"),
                         on_settings=lambda: calls.append("settings"),
                         on_quit=lambda: calls.append("quit"),
                         on_about=lambda: calls.append("about"),
                         on_save_all=lambda: calls.append("save_all"))
    actions = icon.contextMenu().actions()
    # порядок меню: «О программе» — после «Настроек», перед «Выходом»;
    # «Сохранить все экраны» — сразу за «Снять скриншот», «Проверить
    # обновления» — между ними и настройками
    assert [a.text() for a in actions if not a.isSeparator()] == [
        "Снять скриншот", "Сохранить все экраны", "Проверить обновления",
        "Настройки", "О программе", "Выход"]
    next(a for a in actions if a.text() == "Настройки").trigger()
    next(a for a in actions if a.text() == "О программе").trigger()
    next(a for a in actions if a.text() == "Сохранить все экраны").trigger()
    assert calls == ["settings", "about", "save_all"]  # окна без запуска захвата
    assert "capture" not in calls  # тихий пункт не открывает оверлей


def test_settings_window_applies_values_live(app, portable, monkeypatch):
    reloads = []

    class _Listener:
        def reload(self):
            reloads.append(True)

    monkeypatch.setattr(tray.hotkey, "get_listener", lambda: _Listener())
    win = tray.create_settings_window()
    try:
        win.mode_chosen.emit(s.MODE_CTRL)
        assert s.panel_mode() == s.MODE_CTRL
        win.watermark_toggled.emit(False)
        assert s.watermark_enabled() is False
        win.hotkey_chosen.emit("ctrl+alt+x")
        assert s.capture_hotkey() == "ctrl+alt+x"
        win.suppress_toggled.emit(False)
        assert s.suppress_prtscr() is False
        assert reloads == [True, True]  # хоткей и перехват — без перезапуска
    finally:
        win.close()


def test_autostart_toggle_writes_and_removes_key(app, portable, monkeypatch):
    """Тумблер «Запускать вместе с Windows»: флаг + ключ Run на лету."""
    synced = []
    monkeypatch.setattr(tray.autostart, "sync", synced.append)
    win = tray.create_settings_window()
    try:
        assert s.autostart_enabled() is True  # дефолт — включена
        win.autostart_toggled.emit(False)
        assert s.autostart_enabled() is False
        win.autostart_toggled.emit(True)
        assert s.autostart_enabled() is True
        assert synced == [False, True]  # реестр получил оба переключения
    finally:
        win.close()


def test_open_settings_window_shows(app, portable):
    win = tray.open_settings_window()
    try:
        assert win.isVisible()
    finally:
        win.close()
        tray._window = None
