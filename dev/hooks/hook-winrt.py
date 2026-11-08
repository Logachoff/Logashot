"""Хук PyInstaller для PyWinRT (OCR).

Проекции WinRT грузят таблицу типов `_table.pywinrt` из папки рядом с собой
(по `__spec__.origin`). Модуль, запертый в PYZ-архив, реального пути не имеет,
и OCR в собранном exe падает с ImportError. Поэтому winrt* кладётся в сборку
файлами (pyc), а таблицы добавляются данными в dev/build.py.
"""

module_collection_mode = {"winrt": "pyc"}

hiddenimports = [
    "winrt",
    "winrt._winrt",
    "winrt.runtime",
    "winrt.system",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.globalization",
    "winrt.windows.graphics.imaging",
    "winrt.windows.media.ocr",
    "winrt.windows.storage.streams",
]
