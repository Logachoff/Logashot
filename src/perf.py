"""Опциональный замер интервалов (DS-8, З4.4): включается LOGA_PERF=1.

Замер — диагностика, а не поведение: без переменной окружения `mark()`
выходит сразу и ничего не стоит. Метки копятся в памяти и пишутся в
%TEMP%\\LogaShot_perf.log при выходе: две метки подряд с числами «+N мс»
дают интервал между операциями (панель после отпускания, пин-окно после
клика). Нужен, чтобы чинить лаги по числам, а не по догадке (З4.4).
"""

import atexit
import os
import time
from pathlib import Path

_ENABLED = os.environ.get("LOGA_PERF") == "1"  # выключен по умолчанию
_START = time.perf_counter()
_LAST = _START
_LINES = []
_PATH = Path(os.environ.get("TEMP", ".")) / "LogaShot_perf.log"


def enabled():
    """Включён ли замер (для тестов и харнессов)."""
    return _ENABLED


def reset():
    """Начать новый отрезок замера: обнулить отсчёт (собранные метки не теряются)."""
    global _START, _LAST
    _START = _LAST = time.perf_counter()


def mark(name):
    """Отметить событие: время от старта замера и от предыдущей метки."""
    global _LAST
    if not _ENABLED:
        return
    now = time.perf_counter()
    _LINES.append(f"{now - _START:.3f}\t{(now - _LAST) * 1000:.1f}\t{name}")
    _LAST = now


def flush():
    """Сбросить метки в файл (вызывается при выходе и харнессом)."""
    if not _ENABLED or not _LINES:
        return
    try:
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(_LINES) + "\n")
    except OSError:
        pass  # fail-soft: диагностика не должна ронять приложение
    _LINES.clear()


atexit.register(flush)
