"""P1: контур выделения на дробном масштабе экрана.

Симптом: «толщина некоторых рёбер становится в 1 пиксель,
при переключении пина туда-обратно меняется — другие рёбра становятся тоньше».
Причина — субпиксельная растеризация: перо 1 логический px при dpr 1,05/1,25/
1,5 — это 1,05/1,25/1,5 физического, линия не помещается в один пиксель и
распыляется сглаживанием; фаза у каждого ребра своя, поэтому одно ребро
«худеет», а соседнее — нет.

Проверяем две вещи: чистая геометрия кладёт рёбра контура на центры физических
пикселей (любой масштаб, с учётом device-смещения пин-окна) и реальная
отрисовка `_paint_dashed_frame` даёт краску ровно в одной колонке на каждом
ребре — то есть все четыре ребра растеризуются одинаково.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import math

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

import canvas as canvas_mod
import geometry

SCALES = (1.0, 1.05, 1.25, 1.5, 1.75)
SEL = (40, 30, 180, 120)  # рамка в координатах холста-пробы


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# --- чистое ядро: выравнивание по физическим пикселям ---

@pytest.mark.parametrize("scale", SCALES)
def test_snap_to_physical_lands_on_pixel_center(scale):
    for value in (0.0, 39.5, 41.2, 219.7, 260.0):
        device = geometry.snap_to_physical(value, scale) * scale
        assert device - math.floor(device) == pytest.approx(0.5, abs=1e-9)


def test_snap_to_physical_on_whole_scale_keeps_half_pixel_grid():
    # при dpr 1 сетка полупиксельная: перо 1 px центрируется на 0,5
    assert geometry.snap_to_physical(39.5, 1.0) == pytest.approx(39.5)
    assert geometry.snap_to_physical(40.2, 1.0) == pytest.approx(40.5)
    assert geometry.snap_to_physical(40.9, 1.0) == pytest.approx(40.5)


def test_snap_to_physical_accounts_for_device_shift():
    # пин-окно: painter сдвинут прокруткой — пиксельная сетка та же
    shift = -37.4
    device = geometry.snap_to_physical(12.0, 1.05, shift) * 1.05 + shift
    assert device - math.floor(device) == pytest.approx(0.5, abs=1e-9)


@pytest.mark.parametrize("scale", SCALES)
def test_stroke_frame_is_one_physical_pixel_on_all_edges(scale):
    x0, y0, x1, y1, width = geometry.stroke_frame(SEL, scale)
    assert width * scale == pytest.approx(1.0)  # ровно 1 физ. px
    for edge in (x0, y0, x1, y1):
        device = edge * scale
        assert device - math.floor(device) == pytest.approx(0.5, abs=1e-9)


def test_stroke_frame_goes_around_selection_outside():
    # контур снаружи выделения: центры штриха на полпикселя за краем
    x, y, w, h = SEL
    x0, y0, x1, y1, _ = geometry.stroke_frame(SEL, 1.0)
    assert (x0, y0, x1, y1) == (x - 0.5, y - 0.5, x + w + 0.5, y + h + 0.5)


# --- реальная отрисовка: краска в одной колонке, одинаково на 4 рёбрах ---

def _render(scale, selection=SEL):
    """Контур на чёрном фоне через painter с device-масштабом scale."""
    image = QImage(round(260 * scale), round(180 * scale),
                   QImage.Format.Format_RGB32)
    image.fill(QColor(0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)  # как в холстах
    painter.scale(scale, scale)
    canvas_mod.AnnotationCanvas._paint_dashed_frame(
        None, painter, QRect(*selection))
    painter.end()
    return image


def _ink(image, x, y):
    """Доля краски в пикселе: синий канал (акцент 254, белый 248) от чёрного."""
    return min(1.0, image.pixelColor(x, y).blue() / 250.0)


def _edge_spread(image, scale, fixed, axis, span):
    """Максимум краски в колонке ребра и сумма «размазанного» по соседям."""
    inks = {}
    for step in range(-3, 4):
        total = 0.0
        for pos in span:
            x, y = (fixed + step, pos) if axis == "x" else (pos, fixed + step)
            total += _ink(image, x, y)
        inks[step] = total / len(span)
    peak = max(inks, key=inks.get)
    spread = sum(v for k, v in inks.items() if k != peak)
    return inks[peak], spread


@pytest.mark.parametrize("scale", (1.05, 1.25, 1.5))
def test_dashed_frame_paints_each_edge_in_one_physical_pixel(app, scale):
    image = _render(scale)
    x, y, w, h = SEL
    rows = range(round((y + 20) * scale), round((y + h - 20) * scale))
    cols = range(round((x + 20) * scale), round((x + w - 20) * scale))
    edges = {
        "лево": (round((x - 0.5) * scale), "x", rows),
        "верх": (round((y - 0.5) * scale), "y", cols),
        "право": (round((x + w + 0.5) * scale), "x", rows),
        "низ": (round((y + h + 0.5) * scale), "y", cols),
    }
    for name, (fixed, axis, span) in edges.items():
        peak, spread = _edge_spread(image, scale, fixed, axis, span)
        assert peak > 0.9, f"{name}: штриха нет (пик {peak:.2f} при dpr {scale})"
        assert spread < 0.1, (
            f"{name}: штрих распылён по соседним пикселям "
            f"(пик {peak:.2f}, соседи {spread:.2f}) при dpr {scale}"
        )


def test_dashed_frame_stays_uniform_after_repaint(app):
    """Пин туда-обратно = перерисовка: картина та же (не «плавает»)."""
    first = _render(1.05)
    second = _render(1.05, selection=(40, 30, 180, 120))
    assert first == second
