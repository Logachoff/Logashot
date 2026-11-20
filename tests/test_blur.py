"""P0: мозаичное размытие — алгоритм на тестовом пиксельном массиве."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import blur


def _gray(v):
    return 0xFF000000 | (v << 16) | (v << 8) | v


def _gradient(width, height):
    """Плоский массив: яркость = номер пикселя (все блоки разные)."""
    return [_gray(i % 256) for i in range(width * height)]


def test_block_filled_with_average():
    pixels = _gradient(4, 2)  # строка 0: 0..3, строка 1: 4..7
    blur.mosaic(pixels, 4, 2, (0, 0, 4, 2), block=4)
    # среднее (0..7) = 3.5 → half-up = 4
    assert pixels == [_gray(4)] * 8


def test_outside_rect_untouched():
    pixels = _gradient(6, 1)
    blur.mosaic(pixels, 6, 1, (2, 0, 2, 1), block=2)
    assert pixels[:2] == [_gray(0), _gray(1)]
    assert pixels[4:] == [_gray(4), _gray(5)]


def test_partial_edge_block():
    # область 3×1 при блоке 2: второй блок шириной 1 — среднее по нему одному
    pixels = _gradient(3, 1)
    blur.mosaic(pixels, 3, 1, (0, 0, 3, 1), block=2)
    assert pixels[:2] == [_gray(1), _gray(1)]  # среднее (0,1) = 0.5 → 1
    assert pixels[2] == _gray(2)  # блок из одного пикселя — сам и есть


def test_uniform_area_stays_uniform():
    pixels = [_gray(77)] * 16
    blur.mosaic(pixels, 4, 4, (0, 0, 4, 4), block=2)
    assert pixels == [_gray(77)] * 16


def test_rect_clamped_to_image():
    pixels = _gradient(4, 1)
    blur.mosaic(pixels, 4, 1, (2, 0, 100, 100), block=2)  # торчит за край
    assert pixels == [_gray(0), _gray(1), _gray(3), _gray(3)]  # край цел


def test_alpha_preserved():
    pixels = [0x80102030, 0x80405060]
    blur.mosaic(pixels, 2, 1, (0, 0, 2, 1), block=2)
    assert all(px & 0xFF000000 == 0x80000000 for px in pixels)


def test_block_size_scales_with_area():
    assert blur.block_for(24, 24) == blur.MIN_BLOCK  # мелкая рамка — минимум
    assert blur.block_for(400, 200) == 20
    assert blur.block_for(1000, 900) == 90


def test_invalid_block_raises():
    try:
        blur.mosaic([0], 1, 1, (0, 0, 1, 1), block=0)
    except ValueError:
        return
    raise AssertionError("блок 0 должен дать ValueError")


def test_mosaic_image_roundtrip():
    # Qt-адаптер: ядро реально доезжает до битов картинки и обратно
    from PySide6.QtGui import QImage

    img = QImage(4, 2, QImage.Format.Format_RGB32)
    for y in range(2):
        for x in range(4):
            img.setPixel(x, y, _gray(y * 4 + x))
    blur.mosaic_image(img, (0, 0, 4, 2), block=4)
    assert img.pixel(0, 0) == img.pixel(3, 1) == _gray(4)
