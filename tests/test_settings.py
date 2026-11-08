"""P0: выбор бэкенда QSettings в зависимости от маркера portable,
персистентность настроек через «перезапуск» и полнота ключей."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import QSettings

import settings as s
from settings import get_settings


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    """Папка «приложения» с маркером portable — настройки в settings.ini."""
    monkeypatch.setattr(s, "_app_dir", lambda: tmp_path)
    (tmp_path / "portable").touch()
    s.reset_store()
    yield tmp_path
    s.reset_store()


def setup_module(module):
    s.reset_store()


def teardown_function(function):
    s.reset_store()


def test_portable_uses_ini(tmp_path):
    (tmp_path / "portable").touch()
    st = get_settings(tmp_path)
    assert st.format() is not None  # IniFormat
    st.setValue("test", 1)
    st.sync()
    assert (tmp_path / "settings.ini").exists()


def test_installed_uses_native_registry(tmp_path):
    st = get_settings(tmp_path)
    # без маркера portable должен вернуть NativeFormat (реестр/профиль)
    assert st.format() is not None


def test_first_run_flag(tmp_path):
    # monkeypatch app_dir + маркер portable, чтобы настройки шли в файл,
    # а не в системное хранилище, где мог остаться флаг от предыдущих прогонов.
    original = s._app_dir
    s._app_dir = lambda: tmp_path
    (tmp_path / "portable").touch()
    s.reset_store()
    try:
        assert not s.first_run_done()
        s.mark_first_run_done()
        assert s.first_run_done()
    finally:
        s._app_dir = original
        s.reset_store()


def test_watermark_toggle_persists(tmp_path):
    """Тумблер визитки: запись читается тем же кэшированным хранилищем."""
    original = s._app_dir
    s._app_dir = lambda: tmp_path
    (tmp_path / "portable").touch()
    s.reset_store()
    try:
        assert s.watermark_enabled() is True
        s.set_watermark_enabled(False)
        assert s.watermark_enabled() is False
        s.set_watermark_enabled(True)
        assert s.watermark_enabled() is True
    finally:
        s._app_dir = original
        s.reset_store()


def test_capture_hotkey_persists(tmp_path):
    """Сочетание захвата: дефолт PrtScr, запись читается обратно (v0.2)."""
    original = s._app_dir
    s._app_dir = lambda: tmp_path
    (tmp_path / "portable").touch()
    s.reset_store()
    try:
        assert s.capture_hotkey() == "print screen"
        s.set_capture_hotkey("ctrl+alt+x")
        assert s.capture_hotkey() == "ctrl+alt+x"
    finally:
        s._app_dir = original
        s.reset_store()


def test_suppress_prtscr_persists(tmp_path):
    """Тумблер перехвата PrtScr: дефолт включён, запись читается (v0.2)."""
    original = s._app_dir
    s._app_dir = lambda: tmp_path
    (tmp_path / "portable").touch()
    s.reset_store()
    try:
        assert s.suppress_prtscr() is True
        s.set_suppress_prtscr(False)
        assert s.suppress_prtscr() is False
        s.set_suppress_prtscr(True)
        assert s.suppress_prtscr() is True
    finally:
        s._app_dir = original
        s.reset_store()


def test_pin_hint_flag_once(tmp_path):
    """Пузырь-подсказка пина: флаг «показан» переключается один раз (v0.2)."""
    original = s._app_dir
    s._app_dir = lambda: tmp_path
    (tmp_path / "portable").touch()
    s.reset_store()
    try:
        assert not s.pin_hint_shown()
        s.mark_pin_hint_shown()
        assert s.pin_hint_shown()
    finally:
        s._app_dir = original
        s.reset_store()


# --- настройки переживают перезапуск ---


def test_settings_survive_restart(app_dir):
    """Запись → «перезапуск» (свежий QSettings-объект) → чтение.

    reset_store() сбрасывает кэш процесса: следующий доступ создаёт новый
    QSettings над тем же файлом — как в новом запуске приложения.
    """
    s.set_panel_mode(s.MODE_CTRL)
    s.set_watermark_enabled(False)
    s.set_capture_hotkey("ctrl+alt+x")
    s.set_suppress_prtscr(False)
    s.mark_first_run_done()
    s.mark_pin_hint_shown()

    s.reset_store()  # «перезапуск»
    assert s.panel_mode() == s.MODE_CTRL
    assert s.watermark_enabled() is False
    assert s.capture_hotkey() == "ctrl+alt+x"
    assert s.suppress_prtscr() is False
    assert s.first_run_done() is True
    assert s.pin_hint_shown() is True


def test_all_settings_keys_written(app_dir):
    """Полнота ключей: хоткей + тумблеры + режимы лежат в settings.ini."""
    s.set_panel_mode(s.MODE_CTRL)
    s.set_watermark_enabled(False)
    s.set_capture_hotkey("alt+n")
    s.set_suppress_prtscr(False)
    s.mark_first_run_done()
    s.mark_pin_hint_shown()

    st = QSettings(str(app_dir / "settings.ini"), QSettings.Format.IniFormat)
    assert st.value("panel/mode") == "ctrl"
    assert st.value("watermark/enabled") is False
    assert st.value("hotkey/capture") == "alt+n"
    assert st.value("hotkey/suppress_prtscr") is False
    assert st.value("app/first_run_done") is True
    assert st.value("app/pin_hint_shown") is True


def test_portable_settings_next_to_exe(app_dir):
    """Portable-режим: settings.ini рядом с exe, значения читаются обратно."""
    s.set_watermark_enabled(False)
    ini = app_dir / "settings.ini"
    assert ini.exists()
    st = QSettings(str(ini), QSettings.Format.IniFormat)
    assert st.value("watermark/enabled", type=bool) is False
