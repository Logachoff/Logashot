"""Тихий скриншот всех экранов — без оверлея и панели.

Один вызов = один захват: каждый подключённый монитор — отдельным файлом по
обычной маске `storage` с суффиксом «_мон<N>» (при одном мониторе суффикса
нет; счётчик маски общий на весь захват). Нумерация мониторов — порядок
QScreen, 1..N. Кадр — полный экран в физических пикселях, без аннотаций и
визитки; буфер обмена не трогаем.

Приложение Per-Monitor V2: у каждого монитора свой devicePixelRatio, и в
файл идут именно физические пиксели — QScreen.grabWindow отдаёт их с
devicePixelRatio, QImageWriter пишет пиксели как есть.

Тост один на весь захват, без действий: «Сохранено» на одном экране,
«Сохранено: N экрана» на нескольких (склонение — screen_word).
"""

from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QGuiApplication

import screengrab
import storage

TOAST_MS = 2000  # тихий тост живёт ~2 с, действий в нём нет
FAIL_TEXT = "Файл не сохранился — проверьте доступ к папке"


def file_names(moment, counter, monitors):
    """Имена файлов захвата: по одному на монитор, счётчик у них общий.

    monitors — число подключённых мониторов (1..N). Один монитор — обычная
    маска без суффикса, несколько — «<маска>_мон<N>.png».
    """
    if monitors < 1:
        raise ValueError(f"мониторов должно быть не меньше одного: {monitors}")
    if monitors == 1:
        return [storage.file_name(moment, counter)]
    return [storage.file_name(moment, counter, monitor=i + 1)
            for i in range(monitors)]


def screen_word(count):
    """Счётное слово для числа экранов: 1 экран, 2 экрана, 5 экранов."""
    if count % 10 == 1 and count % 100 != 11:
        return "экран"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "экрана"
    return "экранов"


def toast_text(count):
    """Тост на весь захват: «Сохранено» или «Сохранено: N экрана»."""
    if count == 1:
        return "Сохранено"
    return f"Сохранено: {count} {screen_word(count)}"


def screens():
    """Подключённые мониторы в порядке QScreen — он же порядок нумерации."""
    return QGuiApplication.screens()


def capture(shots_dir=None):
    """Снять все мониторы в папку сохранения; вернуть записанные файлы.

    Ошибку записи не маскируем (Fail Fast): папка недоступна или save вернул
    False — OSError, вызывающий показывает тост-ошибку. Файлы, которые успели
    записаться, остаются на диске — затирать их нечем и незачем.
    """
    folder = storage.shot_dir(Path.home()) if shots_dir is None else Path(shots_dir)
    folder.mkdir(parents=True, exist_ok=True)
    monitors = screens()
    if not monitors:
        raise OSError("не найдено ни одного монитора")
    moment = datetime.now()
    counter = storage.next_counter((p.name for p in folder.iterdir()), moment)
    saved = []
    for screen, name in zip(monitors, file_names(moment, counter, len(monitors))):
        path = folder / name
        if not screengrab.grab_screen(screen).save(str(path), "PNG"):
            raise OSError(f"QImage.save вернул False: {path}")
        saved.append(path)
    return saved
