"""Настройки приложения на QSettings (хранение — QSettings, новых
зависимостей нет).

Две настройки v0.1 (попап шестерёнки):
- режим панели: «Сразу» (дефолт) / «по Ctrl»;
- полоска-визитка: включена (дефолт) / выключена.

Портативный режим: если рядом с exe лежит файл `portable`, настройки
хранятся в `settings.ini` в папке приложения (QSettings::IniFormat);
иначе — стандартное системное хранилище (Windows: реестр).
"""

import sys
from pathlib import Path

from PySide6.QtCore import QSettings

MODE_IMMEDIATE = "immediate"  # панель появляется после отпускания кнопки
MODE_CTRL = "ctrl"  # панель живёт, пока зажат Ctrl

# Дефолт сочетания захвата — PrtScr (возврат обязательства 16.10, фича v0.2).
# Храним в формате библиотеки keyboard («ctrl+alt+x», «print screen»);
# человекочитаемый вид («Ctrl+Alt+X», «PrtScr») делает hotkey.combo_label.
DEFAULT_CAPTURE_HOTKEY = "print screen"
DEFAULT_SUPPRESS_PRTSCR = True  # перехват PrtScr у Windows (тумблер в настройках)
# Тихий скриншот всех экранов: слот «захват всего экрана» из набора
# клавиш 15.10, сочетание переназначается как основной хоткей.
DEFAULT_QUIET_HOTKEY = "shift+print screen"

_MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")  # канонический порядок в сочетании


def _migrate_hotkey(combo):
    """Старые записи → имена физических клавиш при чтении; значение не переписываем.

    Кириллица («alt+я», записано при русской раскладке) → «alt+z» —
    keyboard строит таблицу имён по активной раскладке на старте, и имя «я»
    при английской раскладке не разрешается, хуки не встают.
    «*» → физическая клавиша Shift+8 — имя «*» в keyboard раскрывается
    ещё и в NumPad-*, поэтому хук на символ ловил цифровой блок.
    """
    import hotkey  # локально: hotkey импортирует settings на уровне модуля
    combo = hotkey.physical_combo(combo)
    parts = combo.split("+")
    if "*" not in parts:
        return combo
    mods = [p for p in parts if p in _MODIFIER_ORDER]
    if "shift" not in mods:
        mods.append("shift")  # символ «*» печатается через Shift
    mods.sort(key=_MODIFIER_ORDER.index)
    return "+".join(mods + ["8"])

_ORG, _APP = "Logachoff", "LogaShot"


def _app_dir():
    # sys.executate = LogaShot.exe в сборке, python.exe при разработке
    return Path(sys.executable).resolve().parent


# Один экземпляр QSettings на процесс: избегаем рассинхрона между чтением
# и записью (тумблер визитки не отключал подпись).
_settings_cache = None


def get_settings(app_dir=None):
    """QSettings для заданной папки приложения (None — папка текущего exe)."""
    app_dir = Path(app_dir) if app_dir else _app_dir()
    if (app_dir / "portable").exists():
        # портативная версия: настройки рядом с exe
        return QSettings(str(app_dir / "settings.ini"), QSettings.Format.IniFormat)
    return QSettings(_ORG, _APP)


def _store():
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = get_settings()
    return _settings_cache


def reset_store():
    """Сброс кэша QSettings (для тестов с monkeypatch _app_dir)."""
    global _settings_cache
    _settings_cache = None


def panel_mode():
    mode = _store().value("panel/mode", MODE_IMMEDIATE, type=str)
    return mode if mode in (MODE_IMMEDIATE, MODE_CTRL) else MODE_IMMEDIATE


def set_panel_mode(mode):
    if mode not in (MODE_IMMEDIATE, MODE_CTRL):
        raise ValueError(f"неизвестный режим панели: {mode}")
    s = _store()
    s.setValue("panel/mode", mode)
    s.sync()


def watermark_enabled():
    return _store().value("watermark/enabled", True, type=bool)


def set_watermark_enabled(enabled):
    s = _store()
    s.setValue("watermark/enabled", bool(enabled))
    s.sync()


def first_run_done():
    return _store().value("app/first_run_done", False, type=bool)


def mark_first_run_done():
    s = _store()
    s.setValue("app/first_run_done", True)
    s.sync()


def capture_hotkey():
    """Сочетание запуска захвата (формат keyboard); пустое/битое — дефолт."""
    combo = _store().value("hotkey/capture", DEFAULT_CAPTURE_HOTKEY, type=str)
    combo = combo or DEFAULT_CAPTURE_HOTKEY
    return _migrate_hotkey(combo)


def set_capture_hotkey(combo):
    if not combo:
        raise ValueError("пустое сочетание сохранить нельзя")
    s = _store()
    s.setValue("hotkey/capture", combo)
    s.sync()


def suppress_prtscr():
    """Тумблер «Перехватывать PrtScr у Windows» (дефолт — включён)."""
    return _store().value("hotkey/suppress_prtscr", DEFAULT_SUPPRESS_PRTSCR, type=bool)


def set_suppress_prtscr(enabled):
    s = _store()
    s.setValue("hotkey/suppress_prtscr", bool(enabled))
    s.sync()


def quiet_hotkey():
    """Сочетание тихого скриншота всех экранов; пустое/битое — дефолт."""
    combo = _store().value("hotkey/quiet", DEFAULT_QUIET_HOTKEY, type=str)
    combo = combo or DEFAULT_QUIET_HOTKEY
    return _migrate_hotkey(combo)


def set_quiet_hotkey(combo):
    if not combo:
        raise ValueError("пустое сочетание сохранить нельзя")
    s = _store()
    s.setValue("hotkey/quiet", combo)
    s.sync()


def autostart_enabled():
    """Автозагрузка с Windows (фича v0.2): дефолт — включена.

    Это единственный флаг автозагрузки: реестр приводится к нему при старте
    приложения и по тумблеру в настройках (autostart.sync).
    """
    return _store().value("app/autostart", True, type=bool)


def set_autostart_enabled(enabled):
    s = _store()
    s.setValue("app/autostart", bool(enabled))
    s.sync()


def pin_hint_shown():
    """Пузырь-подсказка у кнопки пина: один раз за жизнь приложения."""
    return _store().value("app/pin_hint_shown", False, type=bool)


def mark_pin_hint_shown():
    s = _store()
    s.setValue("app/pin_hint_shown", True)
    s.sync()
