"""Точка входа LogaShot v0.1: single-instance + трей + глобальный PrtScr +
оверлей захвата + пин-окна."""

import ctypes
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import autostart
import hotkey as hotkey_mod
import settings
import toast as toast_mod
from about import show_about
from firstrun import show_first_run
from overlay import CaptureOverlay
from pin import PinWindow
from single_instance import SingleInstanceGuard
from tray import TrayIcon, open_settings_window


def _set_dpi_awareness():
    """Per-Monitor V2: захват идёт в физических пикселях, текст не "плывёт"
    при масштабе Windows > 100% (дефект, найденный на тестировании)."""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass  # fail-soft: старая Windows или ошибка API


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: исполняемый файл на уровень выше _internal/
        return Path(sys.executable).resolve().parent / "_internal" / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def _icon_path() -> Path:
    """Иконка приложения: exe, ярлык, установщик (брендовая, без правок)."""
    return _assets_dir() / "LogaShot.ico"


def _tray_icon_path() -> Path:
    """Иконка трея: увеличенный глиф, отдельный файл."""
    return _assets_dir() / "LogaShot_tray.ico"


def _load_icon(path: Path | None = None) -> QIcon | None:
    path = path or _icon_path()
    if not path.exists():
        print(f"Ошибка: не найдена иконка {path}", file=sys.stderr)
        return None
    icon = QIcon(str(path))
    if icon.isNull():
        print(f"Ошибка: не удалось загрузить иконку {path}", file=sys.stderr)
        return None
    return icon


def _load_tray_icon() -> QIcon | None:
    """Трей — увеличенный глиф; нет файла — обычная иконка приложения."""
    return _load_icon(_tray_icon_path()) or _load_icon()


def _show_already_running_toast():
    """Второй экземпляр: короткий тост и выход (без глобального хоткея)."""
    app = QApplication(sys.argv)
    icon = _load_tray_icon()
    if icon is None or not QSystemTrayIcon.isSystemTrayAvailable():
        return

    tray = QSystemTrayIcon(icon)
    tray.setToolTip("LogaShot")
    tray.show()
    tray.showMessage(
        "LogaShot",
        "LogaShot уже работает — иконка в трее",
        QSystemTrayIcon.MessageIcon.Information,
        2600,
    )

    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 2.8:
        app.processEvents()
        time.sleep(0.02)


def _log_startup(elapsed_sec: float, tray_ok: int, reason: str = ""):
    """Для релизных метрик: логируем время старта и состояние трея.

    Пишем только в собранном exe (sys.frozen). Файл в %TEMP% — не требует
    прав и не отличает portable/installed.
    """
    if not getattr(sys, "frozen", False):
        return
    log_dir = Path(os.environ.get("TEMP", "."))
    reason = reason.replace("\t", " ").replace("\n", " ")
    try:
        with open(log_dir / "LogaShot_startup.log", "a", encoding="utf-8") as f:
            f.write(f"{elapsed_sec:.3f}\ttray={tray_ok}\t{reason}\n")
    except OSError:
        pass


def _tray_status(tray: TrayIcon) -> tuple[int, str]:
    """Проверка, что иконка реально отображается в трее (для smoke)."""
    if not tray.isVisible():
        return 0, "tray not visible"
    geom = tray.geometry()
    if not geom.isValid() or geom.width() <= 0 or geom.height() <= 0:
        return 0, "tray geometry empty"
    pm = tray.icon().pixmap(32)
    if pm.isNull():
        return 0, "tray icon pixmap null"
    return 1, "ok"


def _launch_toast_text():
    """Тост о запуске: сочетание — актуальное из настроек.

    Подпись сочетания берём тем же `hotkey.combo_label`, что и окно
    настроек, поэтому после смены сочетания тост покажет новое.
    """
    combo = hotkey_mod.combo_label(settings.capture_hotkey())
    return f"LogaShot запущен · живёт в трее · {combo} — снять скриншот"


def _announce_startup(first_run_window, tray_anchor):
    """Тост «LogaShot запущен» на каждом старте, кроме старта с онбордингом.

    старты после первого раньше были полностью молчаливыми — по тосту
    видно, что приложение действительно запустилось. Автозапуск с Windows,
    portable и installed ведут себя одинаково: ветки по способу старта нет.
    Если в этом старте показан онбординг (он и так объясняет, что дальше) —
    тост не нужен, поэтому None.
    """
    if first_run_window is not None:
        return None
    return toast_mod.show_launch(_launch_toast_text(), tray_anchor)


def _sync_autostart():
    """Привести ключ автозагрузки Windows к настройке.

    Вызывается на каждом старте — это закрывает сразу три случая: первый
    запуск после установки (ключа ещё нет), миграцию машин, где онбординг
    пройден раньше, и переезд portable-папки (путь в ключе обновится сам).
    Ошибку реестра не маскируем, но и не роняем приложение ради автозагрузки.
    """
    enabled = settings.autostart_enabled()
    try:
        return autostart.sync(enabled)
    except OSError as exc:
        print(f"Ошибка: не удалось изменить автозагрузку — {exc}", file=sys.stderr)
        return None


def _run_app():
    t0 = time.perf_counter()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # живём в трее, окон по умолчанию нет

    _sync_autostart()  # до появления трея: ключ Run уже соответствует настройке

    icon = _load_icon()
    if icon is None:
        return 1
    app.setWindowIcon(icon)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("Ошибка: системный трей недоступен", file=sys.stderr)
        return 1

    overlay = CaptureOverlay()
    pin_windows = []  # живые пин-окна (реестр, чтобы GC не собрал)
    first_run_windows = []  # окно первого запуска — тоже держим ссылку

    def start_capture():
        # повторный PrtScr при открытом оверлее — без эффекта (POLA);
        # пин-окна при новом захвате не закрываются
        if not overlay.isVisible():
            overlay.start()

    def open_pin():
        # «Пин» на панели захвата: оверлей спрятался (сигнал pinned),
        # открываем окно с тем же состоянием
        win = PinWindow(overlay)
        pin_windows.append(win)
        win.destroyed.connect(lambda: _forget_pin(win))
        win.open()

    def _forget_pin(win):
        if win in pin_windows:
            pin_windows.remove(win)

    overlay.pinned.connect(open_pin)

    def quit_app():
        hotkey.stop()
        app.quit()

    hotkey = hotkey_mod.get_listener()
    # QueuedConnection явно: колбэк keyboard приходит из чужого потока,
    # показ окна должен идти только из GUI-потока
    hotkey.triggered.connect(start_capture, Qt.ConnectionType.QueuedConnection)
    hotkey.start()

    # трей — отдельная иконка с увеличенным глифом; окна/ярлык/exe —
    # брендовая иконка без изменений (правка 30.10)
    tray = TrayIcon(_load_tray_icon() or icon, on_capture=start_capture,
                    on_settings=open_settings_window, on_quit=quit_app,
                    on_about=show_about)
    tray.show()

    # Окно первого запуска: один раз, после появления трея; заменяет
    # тост первого запуска 18.10 (единый флаг, решение 24.10). Трей и
    # хоткей не блокирует — обычный топ-левел поверх остальных окон.
    first_run = show_first_run()
    if first_run is not None:
        first_run_windows.append(first_run)
    # На остальных стартах — тост у трея «LogaShot запущен» с актуальным
    # сочетанием; ссылку держим, иначе Qt закроет окно сборщиком мусора
    startup_toasts = []
    startup_toast = _announce_startup(first_run, tray.geometry())
    if startup_toast is not None:
        startup_toasts.append(startup_toast)

    tray_ok, reason = _tray_status(tray)
    _log_startup(time.perf_counter() - t0, tray_ok, reason)
    return app.exec()


def main():
    _set_dpi_awareness()  # до создания QApplication
    with SingleInstanceGuard() as guard:
        if guard.is_another_running:
            _show_already_running_toast()
            return 0
        return _run_app()


if __name__ == "__main__":
    sys.exit(main())
