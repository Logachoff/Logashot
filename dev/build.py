"""Сборка релизного onedir-исполняемого файла LogaShot (PyInstaller).

Запуск из корня репозитория:
    python dev/build.py
Артефакты:
    build/      — рабочие файлы PyInstaller
    dist/LogaShot/   — portable-версия (LogaShot.exe + _internal/)
    dist/LogaShot/portable — маркер портативного режима

Требования: PyInstaller установлен для текущего Python, иконка в assets/.
UPX: используется, если найден в PATH; иначе сборка идёт без UPX.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
ASSETS = ROOT / "assets"
DIST = ROOT / "dist" / "LogaShot"
INTERNAL = DIST / "_internal"
ICON = ASSETS / "LogaShot.ico"
VERSION_FILE = ROOT / "dev" / "version_file.txt"

# Модули Qt, которые приложение не использует — исключаем для уменьшения веса.
_QT_EXCLUDES = [
    "PySide6.QtSql",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickTemplates2",
    "PySide6.QtQml",
    "PySide6.QtQmlModels",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtWebView",
    "PySide6.QtXml",
    "PySide6.QtXmlPatterns",
    "PySide6.QtUiTools",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtTest",
]

# Неиспользуемые сторонние модули, которые PyInstaller иногда тащит
_OTHER_EXCLUDES = [
    "numpy",
    "PIL",
    "cv2",
    "matplotlib",
    "pandas",
    "scipy",
    "sklearn",
]

# PyWinRT (OCR через Windows.Media.Ocr): проекции — Python-модули, но таблицу
# типов `_table.pywinrt` рантайм читает из папки рядом с модулем (__spec__.origin),
# а модули из PYZ реального пути не имеют. Поэтому хук dev/hooks/hook-winrt.py
# кладёт winrt в сборку файлами, а таблицы идут данными (_winrt_args).
_WINRT_MODULES = [
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.globalization",
    "winrt.windows.graphics.imaging",
    "winrt.windows.media.ocr",
    "winrt.windows.storage.streams",
]
HOOKS = ROOT / "dev" / "hooks"


def _winrt_args():
    """hidden-imports и таблицы типов WinRT для PyInstaller."""
    import importlib.util
    import os

    args = []
    for name in _WINRT_MODULES:
        args += ["--hidden-import", name]
        spec = importlib.util.find_spec(name)
        if spec is None or not spec.origin:
            print(f"  внимание: проекция {name} не найдена", file=sys.stderr)
            continue
        table = Path(spec.origin).parent / "_table.pywinrt"
        if not table.exists():
            print(f"  внимание: нет таблицы типов {table}", file=sys.stderr)
            continue
        args += ["--add-data", f"{os.fspath(table)};{Path(*name.split('.'))}"]
    return args

# Файлы и папки внутри _internal, которые PyInstaller всё равно тащит,
# но приложению не нужны (проверяем смоуком после удаления).
_TRIM = [
    # QML/Quick — не используем
    "PySide6/Qt6Quick.dll",
    "PySide6/Qt6Qml.dll",
    "PySide6/Qt6QmlModels.dll",
    "PySide6/Qt6QmlMeta.dll",
    "PySide6/qml",
    # Сеть нужна проверке обновлений (QtNetwork): Qt6Network.dll и Qt-плагины
    # tls остаются. OpenSSL Qt ждёт парой *-x64 — её не трогаем; пара без
    # суффикса нужна только _hashlib.pyd, а он в сборке не работает.
    "libcrypto-3.dll",
    "libssl-3.dll",
    # PDF, VirtualKeyboard, OpenGL-software, ненужные платформы
    "PySide6/Qt6Pdf.dll",
    "PySide6/Qt6VirtualKeyboard.dll",
    "PySide6/Qt6OpenGL.dll",
    "PySide6/opengl32sw.dll",
    "PySide6/plugins/platforms/qdirect2d.dll",
    # Лишние imageformats. ICO оставляем — QIcon загружает .ico через qico.dll,
    # без него иконка трея в сборке не отображается.
    "PySide6/plugins/imageformats/qtiff.dll",
    "PySide6/plugins/imageformats/qwebp.dll",
    "PySide6/plugins/imageformats/qjpeg.dll",
    # Переводы Qt
    "PySide6/translations",
    # pywin32: GUI-фреймворк не нужен, только COM/MAPI
    "pythonwin",
    # Стандартные модули Python, не используемые в золотом пути
    "_zstd.pyd",
    "_ssl.pyd",
    "_lzma.pyd",
]


def _size_mb(path):
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def _trim():
    for rel in _TRIM:
        target = INTERNAL / rel
        if not target.exists():
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        print(f"  удалено: {rel}")


def _smoke(exe):
    """Запуск собранного exe на 4 с — проверяем старт и состояние трея."""
    import os
    log = Path(os.environ.get("TEMP", ".")) / "LogaShot_startup.log"
    if log.exists():
        log.unlink()
    proc = subprocess.Popen([str(exe)], cwd=DIST)
    time.sleep(4.0)
    proc.terminate()
    try:
        proc.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    if not log.exists() or not log.read_text().strip():
        print("  смоук: стартап-лог не найден — возможен сбой", file=sys.stderr)
        return False

    # startup.log: "0.132\ttray=1\tok" (или tray=0 + причина)
    last_line = log.read_text(encoding="utf-8").strip().splitlines()[-1]
    print(f"  смоук: {last_line}")
    if "tray=1" in last_line:
        return True
    print("  смоук: иконка трея не подтверждена — см. лог", file=sys.stderr)
    return False


def main():
    if not ICON.exists():
        print(f"Ошибка: не найдена иконка {ICON}", file=sys.stderr)
        return 1

    if not VERSION_FILE.exists():
        print(f"Ошибка: не найден version-file {VERSION_FILE}", file=sys.stderr)
        return 1

    excludes = []
    for name in _QT_EXCLUDES + _OTHER_EXCLUDES:
        excludes.extend(["--exclude-module", name])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "LogaShot",
        "--icon", str(ICON),
        "--version-file", str(VERSION_FILE),
        "--add-data", f"{ASSETS};assets",
        "--additional-hooks-dir", str(HOOKS),
        *_winrt_args(),
        *excludes,
        str(SRC / "main.py"),
    ]
    print("сборка:", " ".join(cmd))
    result = subprocess.run(cmd, check=False, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    print("\nобрезка неиспользуемых файлов...")
    _trim()

    # маркер портативного режима: настройки рядом с exe
    (DIST / "portable").touch()

    exe = DIST / "LogaShot.exe"
    print(f"\nсобрано: {exe}")
    print(f"размер exe: {_size_mb(exe):.1f} МБ")
    print(f"размер папки dist/LogaShot: {_size_mb(DIST):.1f} МБ")

    print("\nсмоук-сборки: запуск exe на 4 с...")
    if os.environ.get("LOGA_SKIP_SMOKE") == "1":
        # Запуск exe на старте синхронизирует ключ автозагрузки в
        # HKCU\...\Run. Там может стоять рабочий ключ пользователя от
        # установленной версии — перезаписывать его смоуком нельзя.
        print("  смоук пропущен (LOGA_SKIP_SMOKE=1): exe пишет ключ Run")
        return 0
    if not _smoke(exe):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
