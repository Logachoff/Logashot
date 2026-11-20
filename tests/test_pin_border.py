"""P1: окантовка пин-окна поверх полос прокрутки и 4 скруглённых угла.

Полосы — дочерние виджеты, они рисуются ПОСЛЕ paintEvent окна, поэтому
правый и нижний сегменты рамки пропадали под ними, окно выглядело «открытым»
справа и снизу. Нижняя полоса идёт от x=0 и закрашивала нижний левый
угол квадратом — дуга не читалась. Проверяем пиксельной пробой настоящего
кадра окна (grab с детьми): линия рамки светлее полосы под ней, все четыре
угла скруглены — при видимых полосах, без них и после ресайза.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

import geometry
import pin as pin_mod
import theme
from overlay import CaptureOverlay

FRAME = (1600, 1000)  # кадр больше любого окна в тесте — полосы видны
SELECTION = (100, 100, 600, 400)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _overlay(frame=FRAME, selection=SELECTION):
    ov = CaptureOverlay()
    pm = QPixmap(*frame)
    pm.fill(QColor(theme.BG))
    ov._snapshot = pm
    ov._selection = selection
    ov._objects = []
    return ov


@pytest.fixture
def pin_window(app):
    win = pin_mod.PinWindow(_overlay())
    win.open()
    yield win
    win.close()


def _pixels(win):
    """Кадр окна вместе с детьми → цвет по координатам окна."""
    image = win.grab().toImage()
    ratio = image.width() / win.width()  # HiDPI: проба идёт по device-пикселям

    def at(x, y):
        return image.pixelColor(round(x * ratio), round(y * ratio))

    return at


def _is_border(color):
    """Светлая окантовка: LINE с альфой 165 поверх NAVY или бегунка.

    Порог по красному каналу отсекает и фон NAVY (11, 17, 32), и бегунок
    MUTED (92, 107, 138): окантовка над ними даёт 116…199 по красному.
    На дугах пиксель бывает частично прозрачным — внешняя кромка окна
    сглажена, — поэтому альфа проверяется снизу (совсем прозрачные точки
    вроде a=5 линией не считаем).
    """
    return color.alpha() > 60 and color.red() > 100 and color.blue() > 128


def _arc_midpoints(width, height, radius=pin_mod._RADIUS):
    """Середины четырёх дуг рамки — точки пробы углов (из той же геометрии)."""
    points = []
    for segment in geometry.window_border(width, height, radius):
        if segment[0] != "arc":
            continue
        _, (ax, ay, aw, ah), start, sweep = segment
        angle = math.radians(start + sweep / 2)
        # Qt: угол против часовой от 3 часов при оси Y вниз
        points.append((ax + aw / 2 + aw / 2 * math.cos(angle),
                       ay + ah / 2 - ah / 2 * math.sin(angle)))
    return points


def _assert_corners_rounded(win, at):
    """Все 4 угла: за дугой прозрачно, сама дуга читается."""
    w, h = win.width(), win.height()
    corners = {
        "верх-лево": (0, 0), "верх-право": (w - 1, 0),
        "низ-лево": (0, h - 1), "низ-право": (w - 1, h - 1),
    }
    for name, (x, y) in corners.items():
        color = at(x, y)
        # полоса или кадр, залившие угол квадратом, дали бы непрозрачный пиксель
        assert color.alpha() == 0, f"угол {name} не скруглён: {color.name()}"

    assert len(_arc_midpoints(w, h)) == 4
    for mx, my in _arc_midpoints(w, h):
        probe = [at(mx + dx, my + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        assert any(_is_border(c) for c in probe), f"дуги нет у точки ({mx:.1f}, {my:.1f})"


def test_border_reads_above_scrollbars(pin_window):
    """Правый и нижний сегменты рамки видны поверх полос."""
    win = pin_window
    assert win._vbar.isVisible() and win._hbar.isVisible()
    at = _pixels(win)
    # линия идёт по полупиксельной сетке и ложится на КРАЙНИЙ пиксель:
    # правый сегмент — колонка w-1, нижний — строка h-1 (x1 = w-0.5)
    x_line, y_line = win.width() - 1, win.height() - 1

    for y in (win._header_h + 20, win.height() // 2, win.height() - 40):
        assert win._vbar.geometry().contains(x_line, y)  # проба именно над полосой
        line, bar = at(x_line, y), at(x_line - 1, y)
        assert _is_border(line), f"правый сегмент перекрыт полосой на y={y}"
        assert line.red() > bar.red() + 20, f"под рамкой не полоса, y={y}"

    for x in (20, win.width() // 2, win.width() - 40):
        assert win._hbar.geometry().contains(x, y_line)
        line, bar = at(x, y_line), at(x, y_line - 1)
        assert _is_border(line), f"нижний сегмент перекрыт полосой на x={x}"
        assert line.red() > bar.red() + 20, f"под рамкой не полоса, x={x}"


def test_border_layer_does_not_steal_mouse(pin_window):
    """Слой окантовки прозрачен для мыши: ползунки и ресайз за угол живы."""
    win = pin_window

    def widget_at(x, y):
        return QApplication.widgetAt(win.mapToGlobal(QPoint(x, y)))

    # под слоем рамки — те же виджеты, что и без него
    assert widget_at(win.width() - 3, win.height() // 2) is win._vbar
    assert widget_at(win.width() // 2, win.height() - 3) is win._hbar
    assert widget_at(win.width() - 3, win.height() - 3) is win  # угол — ресайз окна


def test_all_corners_rounded_with_scrollbars(pin_window):
    """При видимых полосах скруглены все 4 угла, дуги на месте."""
    _assert_corners_rounded(pin_window, _pixels(pin_window))


def test_corners_after_window_resize(pin_window):
    """Ресайз меняет геометрию полос — маска и окантовка должны успевать."""
    win = pin_window
    win.resize(win.width() - 140, win.height() - 100)
    _assert_corners_rounded(win, _pixels(win))


def test_border_and_corners_without_scrollbars(app):
    """Полос нет (кадр помещается): периметр тоже замкнут, углы скруглены."""
    win = pin_mod.PinWindow(_overlay(frame=(320, 240), selection=(40, 40, 200, 140)))
    win.open()
    try:
        win.toggle_maximize()  # разворот: кадр помещается, полосы прячутся
        assert not win._vbar.isVisible() and not win._hbar.isVisible()
        at = _pixels(win)
        _assert_corners_rounded(win, at)
        # правый и нижний сегменты на месте (тут под ними фон окна, не полосы)
        assert _is_border(at(win.width() - 1, win.height() // 2))
        assert _is_border(at(win.width() // 2, win.height() - 1))
    finally:
        win.close()
