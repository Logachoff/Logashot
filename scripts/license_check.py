"""license_check.py — проверка зависимостей по лицензиям.

Белый список: PySide6 (LGPL), keyboard (MIT), pywin32 (PSF),
PyWinRT — winrt-runtime и проекции winrt-Windows.* (MIT, OCR с 0.3.0).
Другие пакеты в requirements — FORBIDDEN (стоп-сигнал, спрашивать автора).
Правила: только permissive; LGPL — как библиотека без модификации.
"""

import sys
from pathlib import Path

_KNOWN = {
    "PySide6": ("LGPL-3.0", "REVIEW"),
    "keyboard": ("MIT", "OK"),
    "pywin32": ("PSF", "OK"),
    # Windows.Media.Ocr из Python: проекции WinRT, лицензия MIT.
    # winsdk — предыдущее имя той же библиотеки (нет колёс для Python 3.14).
    "winrt-runtime": ("MIT", "OK"),
    "winrt-Windows.Foundation": ("MIT", "OK"),
    "winrt-Windows.Foundation.Collections": ("MIT", "OK"),
    "winrt-Windows.Globalization": ("MIT", "OK"),
    "winrt-Windows.Graphics.Imaging": ("MIT", "OK"),
    "winrt-Windows.Media.Ocr": ("MIT", "OK"),
    "winrt-Windows.Storage.Streams": ("MIT", "OK"),
    # зависимость winrt-runtime (не наша прямая, но попадает в сборку)
    "typing_extensions": ("PSF-2.0", "OK"),
}


def main(req_path="requirements.txt"):
    path = Path(req_path)
    if not path.exists():
        print(f"FORBIDDEN: не найден {path.resolve()}", file=sys.stderr)
        return 2

    names = [line.strip().split("#")[0].strip() for line in path.read_text(encoding="utf-8").splitlines()]
    names = [n for n in names if n]

    counts = {"OK": 0, "REVIEW": 0, "FORBIDDEN": 0}
    for name in names:
        if name in _KNOWN:
            license_, status = _KNOWN[name]
            counts[status] += 1
            print(f"{status}: {name} ({license_})")
        else:
            counts["FORBIDDEN"] += 1
            print(f"FORBIDDEN: {name} (лицензия неизвестна)")

    print(f"\nИтого: OK={counts['OK']}, REVIEW={counts['REVIEW']}, FORBIDDEN={counts['FORBIDDEN']}")
    return 0 if counts["FORBIDDEN"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "requirements.txt"))
