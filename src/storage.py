"""Чистое ядро сохранения скриншотов — без Qt, тестируется без UI.

- маска имени файла: LogaShot_ГГГГ-ММ-ДД_чч-мм-сс_счётчик.png;
- счётчик без коллизий: два сохранения в одну секунду не затирают друг друга
  (Ctrl+S после Enter — файл №2 рядом);
- суффикс монитора «_мон<N>» для тихого захвата всех экранов: файлы
  одного захвата различаются только им, счётчик у них общий;
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
MONITOR_SUFFIX = "_мон"  # суффикс монитора в тихом захвате всех экранов


def open_shots_folder(folder: Path):
    """Открыть папку в проводнике Windows; надёжнее QDesktopServices.openUrl.

    QDesktopServices иногда молча не срабатывает
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


def file_name(moment: datetime, counter: int, monitor: int | None = None) -> str:
    """Имя файла по маске: основа + счётчик с ведущими нулями + .png.

    monitor (1..N) добавляет перед расширением суффикс «_мон<N>» — так
    тихий захват всех экранов даёт по файлу на монитор.
    """
    if counter < 1:
        raise ValueError(f"счётчик начинается с 1, получено {counter}")
    name = f"{stem_for(moment)}_{counter:0{_COUNTER_W}d}"
    if monitor is not None:
        name += f"{MONITOR_SUFFIX}{monitor}"
    return name + ".png"


def _counter_in(name, prefix):
    """Счётчик из имени по маске (с суффиксом монитора или без); None — чужое."""
    if not name.startswith(prefix) or not name.endswith(".png"):
        return None
    number = name[len(prefix):-len(".png")].split(MONITOR_SUFFIX)[0]
    return int(number) if number.isdigit() else None


def next_counter(names, moment: datetime) -> int:
    """Первый свободный счётчик для этой секунды по списку имён в папке.

    Два сохранения подряд в одну секунду: первое берёт 001, второе видит
    его в папке и берёт 002 — автосохранение не затирается.
    Имена с суффиксом монитора считаются теми же файлами этой секунды:
    второй тихий захват не должен затирать первый.
    """
    prefix = stem_for(moment) + "_"
    used = set()
    for name in names:
        counter = _counter_in(name, prefix)
        if counter is not None:
            used.add(counter)
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
