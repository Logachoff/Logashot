"""Чистое ядро сохранения скриншотов — без Qt, под P0-тесты.

- маска имени файла: LogaShot_ГГГГ-ММ-ДД_чч-мм-сс_счётчик.png;
- счётчик без коллизий: два сохранения в одну секунду не затирают друг друга
  (Ctrl+S после Enter — файл №2 рядом);
- пресеты масштаба 100/75/50 применяются к сохраняемому файлу.

Папка сохранения — %USERPROFILE%\\Pictures\\LogaShot (создаётся при первом
сохранении). Пользовательской маски имени в v0.1 нет.
"""

import os
from datetime import datetime
from pathlib import Path

SHOTS_SUBDIR = Path("Pictures") / "LogaShot"  # папка сохранения внутри домашней
SCALE_PRESETS = (100, 75, 50)  # пресеты масштаба файла
_COUNTER_W = 3  # ширина счётчика в имени файла (001, 002, …)


def open_shots_folder(folder: Path):
    """Открыть папку в проводнике Windows; надёжнее QDesktopServices.openUrl.

    Дефект, найденный на тестировании: QDesktopServices иногда молча не срабатывает
    (OneDrive-редирект, нестандартный обработчик). os.startfile —
    стандартный Windows-способ, при сбое бросает ошибку.
    """
    folder.mkdir(parents=True, exist_ok=True)
    if not folder.exists():
        raise OSError(f"папка не существует: {folder}")
    try:
        os.startfile(str(folder))
    except OSError as exc:
        raise OSError(f"не удалось открыть папку {folder}: {exc}") from exc


def shot_dir(home: Path) -> Path:
    """Папка сохранения: <домашняя>/Pictures/LogaShot."""
    return home / SHOTS_SUBDIR


def stem_for(moment: datetime) -> str:
    """Основа имени без счётчика: LogaShot_2026-10-16_15-03-07."""
    return moment.strftime("LogaShot_%Y-%m-%d_%H-%M-%S")


def file_name(moment: datetime, counter: int) -> str:
    """Имя файла по маске: основа + счётчик с ведущими нулями + .png."""
    if counter < 1:
        raise ValueError(f"счётчик начинается с 1, получено {counter}")
    return f"{stem_for(moment)}_{counter:0{_COUNTER_W}d}.png"


def next_counter(names, moment: datetime) -> int:
    """Первый свободный счётчик для этой секунды по списку имён в папке.

    Два сохранения подряд в одну секунду: первое берёт 001, второе видит
    его в папке и берёт 002 — автосохранение не затирается.
    """
    prefix = stem_for(moment) + "_"
    used = set()
    for name in names:
        if name.startswith(prefix) and name.endswith(".png"):
            suffix = name[len(prefix):-len(".png")]
            if suffix.isdigit():
                used.add(int(suffix))
    counter = 1
    while counter in used:
        counter += 1
    return counter


def scale_size(size, percent: int):
    """Размер (w, h) после пресета масштаба; минимум 1 px, округление half-up."""
    if percent not in SCALE_PRESETS:
        raise ValueError(f"неизвестный пресет масштаба: {percent}")
    w, h = size
    # int(x + 0.5) вместо round(): round в Python банковский (50.5 → 50),
    # для размеров кадра привычнее «половина — вверх»
    return max(1, int(w * percent / 100 + 0.5)), max(1, int(h * percent / 100 + 0.5))
