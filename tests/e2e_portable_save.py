"""End-to-end проверка portable-сборки: exe → PrintScreen → выделение → Enter → файл.

Проверяет, что собранный dist/LogaShot/LogaShot.exe:
- стартует и реагирует на глобальный PrintScreen;
- сохраняет скриншот (Enter → золотой путь) в Рисунки/LogaShot;
- в portable-режиме создаёт settings.ini рядом с exe.

Ручной прогон, не для автотестов: нужен собранный exe и живой рабочий стол.
    python dev/build.py            # собрать
    python tests/e2e_portable_save.py
Файлы `tests/*.png` в Рисунках/LogaShot перед прогоном очищаются.
"""

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

import keyboard

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from settings import capture_hotkey

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "LogaShot" / "LogaShot.exe"
SHOTS_DIR = Path.home() / "Pictures" / "LogaShot"


MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulonglong)),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def send_mouse(flags, x=0, y=0):
    extra = ctypes.c_ulonglong(0)
    mi = MOUSEINPUT(dx=x, dy=y, mouseData=0, dwFlags=flags, time=0,
                    dwExtraInfo=ctypes.pointer(extra))
    inp = INPUT(type=0, mi=mi)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def to_absolute(px, py, w, h):
    return int(px * 65535 / (w - 1)), int(py * 65535 / (h - 1))


def drag(x1, y1, x2, y2, steps=20):
    w = ctypes.windll.user32.GetSystemMetrics(0)
    h = ctypes.windll.user32.GetSystemMetrics(1)
    ax1, ay1 = to_absolute(x1, y1, w, h)
    ax2, ay2 = to_absolute(x2, y2, w, h)
    send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, ax1, ay1)
    time.sleep(0.05)
    send_mouse(MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE, ax1, ay1)
    for i in range(1, steps + 1):
        ax = ax1 + (ax2 - ax1) * i // steps
        ay = ay1 + (ay2 - ay1) * i // steps
        send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, ax, ay)
        time.sleep(0.01)
    send_mouse(MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE, ax2, ay2)


def _kill():
    subprocess.run(
        ["powershell.exe", "-Command", "Stop-Process -Name LogaShot -Force -ErrorAction SilentlyContinue"],
        capture_output=True,
        check=False,
    )


def main():
    if not EXE.exists():
        print(f"FAIL: не найден {EXE}", file=sys.stderr)
        return 1

    _kill()
    if SHOTS_DIR.exists():
        # убираем старые файлы, чтобы новый был однозначно наш
        for f in SHOTS_DIR.glob("*.png"):
            f.unlink()

    settings_ini = EXE.parent / "settings.ini"
    if settings_ini.exists():
        settings_ini.unlink()

    proc = subprocess.Popen([str(EXE)], cwd=EXE.parent)
    try:
        time.sleep(3.0)

        # убрать сторонние перехватчики PrtScr
        subprocess.run(["taskkill", "/F", "/IM", "YandexDiskScreenshotEditor.exe"],
                       capture_output=True, check=False)

        keyboard.send(capture_hotkey())
        time.sleep(1.5)

        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        drag(int(w * 0.30), int(h * 0.30), int(w * 0.65), int(h * 0.60))
        time.sleep(0.5)

        keyboard.send("enter")
        time.sleep(2.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        _kill()

    files = sorted(SHOTS_DIR.glob("*.png")) if SHOTS_DIR.exists() else []
    ok_file = len(files) > 0
    ok_settings = settings_ini.exists()

    print(f"файл сохранён: {ok_file} ({files[-1].name if files else 'нет' })")
    print(f"settings.ini рядом с exe: {ok_settings}")

    if not ok_file:
        print("FAIL: не найден сохранённый скриншот", file=sys.stderr)
        return 2
    if not ok_settings:
        print("FAIL: portable-настройки не создались", file=sys.stderr)
        return 3
    print("OK: portable exe сохраняет файл и пишет settings.ini")
    return 0


if __name__ == "__main__":
    sys.exit(main())
