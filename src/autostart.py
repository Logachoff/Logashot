"""Автозагрузка с Windows: значение в HKCU\\...\\Run.

Механика — «как у других скриншотеров»: приложение самопрописывается,
галочки в установщике нет. Единственный флаг, который уважаем, — настройка
`app/autostart` (settings.py, дефолт включена).

Реестр трогаем только свой: значение `LogaShot` в ветке Run текущего
пользователя. Согласование идемпотентно (`sync`): его вызывают и при старте
приложения (миграция старых машин, переезд portable-папки), и из тумблера
настроек. Чужие значения в Run не читаем и не меняем.

Путь к exe — фактический путь запуска, без хардкода: в сборке это сам
LogaShot.exe, при запуске из исходников — pythonw с main.py.
"""

import sys
from pathlib import Path

try:  # не-Windows: автозагрузки нет, модуль всё равно импортируется
    import winreg
except ImportError:  # pragma: no cover - зависит от платформы
    winreg = None

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "LogaShot"

# Что реально сделал sync() — для лога старта и смоука (отчёт: до/после)
CREATED, UPDATED, REMOVED, UNCHANGED = "created", "updated", "removed", "unchanged"


def exe_command():
    """Командная строка автозапуска: исполняемый файл в кавычках.

    В сборке — путь к LogaShot.exe; при запуске из исходников — pythonw плюс
    точка входа рядом с этим модулем (sys.argv[0] не годится: у запуска через
    `python -c`/REPL/тест-раннер это не скрипт приложения).
    """
    exe = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return f'"{exe}"'
    interpreter = exe.with_name("pythonw.exe")
    if not interpreter.exists():  # без pythonw в комплекте хватает python
        interpreter = exe
    entry = Path(__file__).resolve().parent / "main.py"
    return f'"{interpreter}" "{entry}"'


def current_value():
    """Значение ключа LogaShot в Run или None (нет ключа/значения/реестра)."""
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value
    except OSError:
        return None  # нет ветки или значения — считаем «не прописано»


def _write(command):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                           winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)


def _delete():
    """Удалить значение; отсутствие — не ошибка (идемпотентность)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        return


def sync(enabled, command=None):
    """Согласовать реестр с настройкой; вернуть, что сделано.

    enabled=True: ключа нет → создать; путь не совпадает с текущим exe →
    обновить (переехавшая portable-папка); совпадает → не трогать.
    enabled=False: ключ есть → удалить; нет → ничего.
    Ошибки реестра не глотаем: вызывающий решает, как сообщить.
    """
    if winreg is None:
        return UNCHANGED
    command = command or exe_command()
    current = current_value()
    if enabled:
        if current == command:
            return UNCHANGED
        _write(command)
        return UPDATED if current is not None else CREATED
    if current is None:
        return UNCHANGED
    _delete()
    return REMOVED
