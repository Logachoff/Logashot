"""Ядро мозаичного размытия — чистая функция на пиксельном массиве (ТЗ §3а).

Мозаика, а не чёрный квадрат: область бьётся на блоки, каждый блок
заливается своим средним цветом. Чистое ядро mosaic() работает на плоском
списке пикселей 0xAARRGGBB (row-major) и мутирует его — так его можно
прогнать в тестах без Qt. Адаптер mosaic_image() применяет ядро к QImage
через memoryview (запись напрямую в биты картинки).
"""

MIN_BLOCK = 8  # блок мельче — уже не «замазано», а «приглушено»


def block_for(w, h):
    """Размер блока мозаики для области w×h: крупнее на больших областях."""
    return max(MIN_BLOCK, min(w, h) // 10)


def mosaic(pixels, width, height, rect, block):
    """Замозаичить прямоугольник rect=(x, y, w, h) в плоском массиве pixels.

    pixels[width * y + x] = 0xAARRGGBB. Крайние блоки у правого/нижнего
    края области могут быть уже block — считаются по фактическим пикселям.
    Альфа-канал не трогаем (кадр экрана непрозрачный).
    """
    if block < 1:
        raise ValueError(f"блок мозаики минимум 1 px, получено {block}")
    rx, ry, rw, rh = rect
    # кламп области в границы картинки (рамка блюра может торчать за край)
    x0, y0 = max(0, rx), max(0, ry)
    x1, y1 = min(width, rx + rw), min(height, ry + rh)
    for by in range(y0, y1, block):
        for bx in range(x0, x1, block):
            bw, bh = min(block, x1 - bx), min(block, y1 - by)
            r_sum = g_sum = b_sum = 0
            for y in range(by, by + bh):
                row = y * width
                for x in range(bx, bx + bw):
                    px = pixels[row + x]
                    r_sum += (px >> 16) & 0xFF
                    g_sum += (px >> 8) & 0xFF
                    b_sum += px & 0xFF
            count = bw * bh
            # int(x + 0.5) — округление half-up, как в storage.scale_size
            avg = (
                ((int(r_sum / count + 0.5) & 0xFF) << 16)
                | ((int(g_sum / count + 0.5) & 0xFF) << 8)
                | (int(b_sum / count + 0.5) & 0xFF)
            )
            for y in range(by, by + bh):
                row = y * width
                for x in range(bx, bx + bw):
                    pixels[row + x] = (pixels[row + x] & 0xFF000000) | avg


def mosaic_image(image, rect, block):
    """Применить мозаику к области QImage (Format_RGB32) на месте.

    Картинка копируется в плоский список построчно (bytesPerLine может
    отличаться от width×4), ядро мутирует список, строки пишутся обратно.
    Запись среза в memoryview принимает только bytes-like — пакуем struct'ом.
    """
    import struct

    from PySide6.QtGui import QImage  # локальный импорт: ядро выше — без Qt

    if image.format() != QImage.Format.Format_RGB32:
        raise ValueError("mosaic_image ждёт Format_RGB32")
    width, height = image.width(), image.height()
    stride = image.bytesPerLine() // 4  # пикселей в строке с выравниванием
    arr = image.bits().cast("I")
    pixels = [0] * (width * height)
    for y in range(height):
        src, dst = y * stride, y * width
        pixels[dst:dst + width] = arr[src:src + width]
    mosaic(pixels, width, height, rect, block)
    row_fmt = f"<{width}I"  # cast("I") — native order, на Windows little-endian
    for y in range(height):
        src, dst = y * width, y * stride
        packed = struct.pack(row_fmt, *pixels[src:src + width])
        # lvalue в формате "I" — rvalue приводим к той же структуре
        arr[dst:dst + width] = memoryview(packed).cast("I")
