"""Захват кадра монитора: Qt-путь + GDI-фолбэк.

Под RDP (и на части удалённых сессий) `QScreen.grabWindow` отдаёт чёрный
кадр — тогда снимаем через GDI BitBlt по DC экрана. Оба хелпера раньше
жили в overlay.py; их использует и тихий захват всех экранов (quiet.py),
поэтому код вынесен в общий модуль — реализация одна на два пути.

Кадр монитора отдаётся QImage в физических пикселях: он же уходит и в файл
тихого захвата (Per-Monitor V2).
"""

import ctypes
import struct

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPixmap


def as_image(frame):
    """QPixmap|QImage → QImage: пиксели как есть, без масштабирования."""
    return frame.toImage() if isinstance(frame, QPixmap) else frame


def mono(frame):
    """Кадр целиком одного цвета (обычно чёрного) — признак сбоя захвата
    под RDP."""
    img = as_image(frame)
    if img.isNull():
        return True
    if img.width() < 2 or img.height() < 2:
        return True
    first = img.pixelColor(0, 0)
    # пробы по углам и центру: монохромный кадр = сбой
    for x, y in ((img.width() - 1, 0), (0, img.height() - 1),
                 (img.width() - 1, img.height() - 1),
                 (img.width() // 2, img.height() // 2)):
        if img.pixelColor(x, y) != first:
            return False
    return True


def _image_data(img):
    """Адрес пиксельных данных QImage для Win32: PySide6 отдаёт memoryview.

    Раньше здесь стоял int(img.bits()) — на memoryview (PySide6 6.12) это
    ValueError, то есть GDI-фолбэк падал вместо кадра.
    """
    view = img.bits()
    if isinstance(view, memoryview):
        return ctypes.addressof(ctypes.c_char.from_buffer(view))
    return int(view)


def grab_gdi(rect):
    """Запасной захват через GDI BitBlt — под RDP Qt-путь даёт чёрный кадр,
    а BitBlt через DC экрана обычно работает. rect — физические пиксели."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    w, h = rect.width(), rect.height()
    screen_dc = user32.GetDC(0)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bmp = gdi32.CreateCompatibleBitmap(screen_dc, w, h)
    gdi32.SelectObject(mem_dc, bmp)
    SRCCOPY = 0x00CC0020
    gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, rect.x(), rect.y(), SRCCOPY)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    bi_size = 40
    bi = struct.pack("<IiiHHIIiiII", bi_size, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    gdi32.GetDIBits(mem_dc, bmp, 0, h, ctypes.c_void_p(_image_data(img)), bi, 0)
    user32.ReleaseDC(0, screen_dc)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem_dc)
    return img


def physical_geometry(screen):
    """Прямоугольник монитора в физических пикселях (для GDI-фолбэка).

    QScreen.geometry — логические (DIP) координаты; BitBlt работает в
    физических, поэтому умножаем на devicePixelRatio этого монитора.
    """
    g = screen.geometry()
    dpr = screen.devicePixelRatio()
    return QRect(round(g.x() * dpr), round(g.y() * dpr),
                 round(g.width() * dpr), round(g.height() * dpr))


def grab_screen(screen):
    """Полный кадр монитора в физических пикселях; чёрный кадр → GDI."""
    pm = screen.grabWindow(0)
    if mono(pm):  # RDP: Qt-путь иногда даёт чёрный кадр
        return grab_gdi(physical_geometry(screen))
    return pm.toImage()
