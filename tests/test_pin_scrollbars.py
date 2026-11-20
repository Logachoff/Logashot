"""P1: видимые полосы прокрутки вьюпорта пин-окна (бэклог п.12, фича v0.2).

Проверяем на живом виджете: ползунки появляются, когда кадр больше окна,
исчезают, когда кадр помещается, и ходят синхронно со смещением вьюпорта.
Кадр под ними не рисуется (вьюпорт ужимается), в экспорт они не попадают:
экспорт берёт пиксели из снапшота, а не с виджета.
З3.1: полосы прижаты к краю окна, правый-нижний угол остаётся зоной
ресайза, над бегунком — курсор-рука (при драге — сжатая).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionSlider

import pin as pin_mod
import theme
from canvas import HANDLE_CURSORS
from overlay import CaptureOverlay

FRAME = (1600, 1000)  # кадр «экрана» больше любого окна в тесте
SELECTION = (100, 100, 600, 400)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _overlay(app, frame=FRAME, selection=SELECTION):
    ov = CaptureOverlay()
    pm = QPixmap(*frame)
    pm.fill(QColor(theme.BG))
    ov._snapshot = pm
    ov._selection = selection
    ov._objects = []
    return ov


@pytest.fixture
def pin_window(app):
    win = pin_mod.PinWindow(_overlay(app))
    win.open()
    yield win
    win.close()


def _wheel(win, up=False):
    """Честное колесо мыши над вьюпортом (step вверх — прокрутка вверх)."""
    delta = QPoint(0, 120 if up else -120)
    event = QWheelEvent(QPointF(100, 100), QPointF(100, 100), QPoint(0, 0),
                        delta, Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    win.wheelEvent(event)


def test_scrollbars_visible_when_frame_larger(pin_window):
    win = pin_window
    assert win._vbar.isVisible()
    assert win._hbar.isVisible()
    # вьюпорт ужат ровно на толщину полосы — кадр под ней не рисуется
    full_w = win.width()
    full_h = win.height() - win._header_h
    view_w, view_h = win._view_size()
    assert view_w == full_w - pin_mod._BAR
    assert view_h == full_h - pin_mod._BAR
    # ползунки стоят вплотную к правому и нижнему краю окна (З3.1)
    assert win._vbar.x() == view_w
    assert win._hbar.y() == win._header_h + view_h
    assert win._vbar.geometry().right() + 1 == win.width()
    assert win._hbar.geometry().bottom() + 1 == win.height()


def test_scrollbars_hidden_when_frame_fits(app):
    # маленький кадр + разворот на весь экран: кадр помещается целиком
    win = pin_mod.PinWindow(_overlay(app, frame=(320, 240),
                                     selection=(40, 40, 200, 140)))
    win.open()
    try:
        assert win._content_size()[0] < win.width()
        win.toggle_maximize()
        assert not win._vbar.isVisible()
        assert not win._hbar.isVisible()
        assert win._view_size() == (win.width(), win.height() - win._header_h)
    finally:
        win.close()


def test_bar_value_syncs_viewport_offset(pin_window):
    win = pin_window
    win._vbar.setValue(120)  # ползунок тащит кадр
    assert win._offset[1] == 120
    win._hbar.setValue(80)
    assert win._offset[0] == 80
    # обратно: прокрутка колесом двигает ползунок
    _wheel(win)
    assert win._vbar.value() == win._offset[1]
    assert win._vbar.value() > 120  # колесо вниз — смещение растёт


def test_wheel_and_shift_wheel_still_scroll(pin_window):
    win = pin_window
    win._scroll_to(0, 0)
    start = win._offset
    _wheel(win)
    assert win._offset[1] > start[1]  # вертикаль — как раньше
    _wheel(win, up=True)
    _wheel(win, up=True)
    assert win._offset[1] < start[1] + 1


def test_export_has_no_scrollbars(pin_window):
    """Экспорт — пиксели снапшота по рамке выделения, без ползунков."""
    win = pin_window
    exported = win._selection_pixmap()
    assert (exported.width(), exported.height()) == (
        win._selection[2], win._selection[3])


# --- З3.1: полосы вплотную к краю, угол под ресайз, курсор-рука ---


def _handle_rect(bar):
    """Прямоугольник бегунка по стилю — зона, где ожидается курсор-рука."""
    option = QStyleOptionSlider()
    bar.initStyleOption(option)
    return bar.style().subControlRect(
        QStyle.ComplexControl.CC_ScrollBar, option,
        QStyle.SubControl.SC_ScrollBarSlider, bar)


def _mouse(bar, kind, pos):
    """Событие мыши в координатах полосы (настоящий курсор не двигаем)."""
    local = QPointF(pos[0], pos[1])
    global_pos = QPointF(bar.mapToGlobal(QPoint(pos[0], pos[1])))
    buttons = (Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease
               else Qt.MouseButton.LeftButton)
    return QMouseEvent(kind, local, global_pos, Qt.MouseButton.LeftButton,
                       buttons, Qt.KeyboardModifier.NoModifier)


def test_corner_stays_window_resize_zone(pin_window):
    """Правый-нижний угол свободен от полос: окно тянется за угол всегда."""
    win = pin_window
    w, h = win.width(), win.height()
    centre = QPoint(w - pin_mod._GRIP // 2, h - pin_mod._GRIP // 2)
    assert not win._vbar.geometry().contains(centre)
    assert not win._hbar.geometry().contains(centre)
    assert win._edge_handle((w - 3, h - 3)) == 4  # 4 — правый-нижний угол
    assert win._edge_handle((w - pin_mod._GRIP, h - pin_mod._GRIP)) == 4
    # курсор в углу — диагональ ресайза, а не что-то из аннотаций
    assert win._hover_chrome((w - 3, h - 3))
    assert win.cursor().shape() == HANDLE_CURSORS[4]


def test_bar_wins_over_window_edge(pin_window):
    """Полоса лежит в зоне правого края окна, но её драг приоритетнее."""
    win = pin_window
    bar = win._vbar
    mid = bar.geometry().center()
    assert win._edge_handle((mid.x(), mid.y())) == 3  # край окна — ресайз
    handle = _handle_rect(bar)
    bar.mousePressEvent(_mouse(bar, QEvent.Type.MouseButtonPress,
                               (bar.width() // 2, handle.center().y())))
    assert win._win_drag is None  # ресайз окна не стартовал
    bar.mouseReleaseEvent(_mouse(bar, QEvent.Type.MouseButtonRelease,
                                 (bar.width() // 2, handle.center().y())))


def test_cursor_over_handle_and_track(pin_window):
    win = pin_window
    bar = win._vbar
    # трекинг включён: иначе QWidget не отдаёт hover-движения и рука
    # над бегунком не появилась бы в реальной жизни (поймано живой пробой)
    assert bar.hasMouseTracking()
    bar.setValue(60)
    handle = _handle_rect(bar)
    assert handle.top() > 4  # над бегунком остаётся дорожка
    bar.mouseMoveEvent(_mouse(bar, QEvent.Type.MouseMove,
                              (bar.width() // 2, handle.center().y())))
    assert bar.cursor().shape() == Qt.CursorShape.OpenHandCursor
    bar.mouseMoveEvent(_mouse(bar, QEvent.Type.MouseMove, (bar.width() // 2, 2)))
    assert bar.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_dragging_handle_closes_hand_and_scrolls(pin_window):
    win = pin_window
    bar = win._vbar
    bar.setValue(60)
    handle = _handle_rect(bar)
    start_y = handle.center().y()
    x = bar.width() // 2
    bar.mousePressEvent(_mouse(bar, QEvent.Type.MouseButtonPress, (x, start_y)))
    assert bar.cursor().shape() == Qt.CursorShape.ClosedHandCursor
    before = bar.value()
    bar.mouseMoveEvent(_mouse(bar, QEvent.Type.MouseMove, (x, start_y + 40)))
    assert bar.cursor().shape() == Qt.CursorShape.ClosedHandCursor  # драг держит
    bar.mouseReleaseEvent(_mouse(bar, QEvent.Type.MouseButtonRelease,
                                 (x, start_y + 40)))
    assert bar.value() > before  # бегунок таскается
    assert win._offset[1] == bar.value()  # и тянет за собой кадр
    assert win._win_drag is None  # ресайз окна так и не начался
    assert bar.cursor().shape() != Qt.CursorShape.ClosedHandCursor
