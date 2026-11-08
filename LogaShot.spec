# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-спека LogaShot (onedir).

Пути считаются от папки спеки — запускать из корня репозитория:

    pyinstaller LogaShot.spec

Эквивалент `python dev/build.py` (тот же результат, но без обрезки
неиспользуемых файлов и без смоук-проверки — они только в dev/build.py).
"""

import importlib.util
import os

_HERE = os.path.abspath(SPECPATH)  # noqa: F821 — SPECPATH задаёт PyInstaller


def _p(*parts):
    return os.path.join(_HERE, *parts)


# WinRT (OCR через Windows.Media.Ocr): проекции — обычные Python-модули, но
# таблицу типов `_table.pywinrt` рантайм читает из папки рядом с модулем, а у
# модуля, поднятого из PYZ, реального пути нет. Поэтому таблицы кладём данными
# в те же папки, что и проекции (те же имена, что в dev/build.py).
_WINRT_MODULES = [
    'winrt.windows.foundation',
    'winrt.windows.foundation.collections',
    'winrt.windows.globalization',
    'winrt.windows.graphics.imaging',
    'winrt.windows.media.ocr',
    'winrt.windows.storage.streams',
]

_datas = [(_p('assets'), 'assets')]
for _name in _WINRT_MODULES:
    _mod_spec = importlib.util.find_spec(_name)
    if _mod_spec is None or not _mod_spec.origin:
        print(f'warning: {_name} не найден — OCR в сборке может не работать')
        continue
    _table = os.path.join(os.path.dirname(_mod_spec.origin), '_table.pywinrt')
    if not os.path.exists(_table):
        print(f'warning: нет таблицы типов {_table}')
        continue
    _datas.append((_table, os.path.join(*_name.split('.'))))

a = Analysis(
    [_p('src', 'main.py')],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=list(_WINRT_MODULES),
    hookspath=[_p('dev', 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtNetwork', 'PySide6.QtSql', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DRender', 'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs', 'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel', 'PySide6.QtWebSockets', 'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickControls2', 'PySide6.QtQuickTemplates2', 'PySide6.QtQml', 'PySide6.QtQmlModels', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtPositioning', 'PySide6.QtPrintSupport', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtStateMachine', 'PySide6.QtTextToSpeech', 'PySide6.QtVirtualKeyboard', 'PySide6.QtWebView', 'PySide6.QtXml', 'PySide6.QtXmlPatterns', 'PySide6.QtUiTools', 'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtTest', 'numpy', 'PIL', 'cv2', 'matplotlib', 'pandas', 'scipy', 'sklearn'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LogaShot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_p('dev', 'version_file.txt'),
    icon=[_p('assets', 'LogaShot.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LogaShot',
)
