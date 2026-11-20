"""P1: монограмма на панели открывает «О программе».

Кнопка-монограмма в конце панели раньше была декоративной. Теперь клик по
ней открывает тот же диалог, что и пункт меню трея, — на обеих панелях
(захват и пин-окно собираются из одного `_PANEL_SPEC`). Диалог не строим:
подменяем `show_about` и смотрим, что обработчик его зовёт. Таскание панели
за монограмму — не клик: диалог при драге не открывается.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

import canvas
import panel
import pin as pin_mod
from overlay import CaptureOverlay

FRAME = (1600, 1000)
SELECTION = (100, 100, 600, 400)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def about_calls(monkeypatch):
    """Подмена диалога: считаем вызовы, окно не открываем."""
    calls = []
    monkeypatch.setattr(canvas, "show_about", lambda *a, **kw: calls.append(True))
    return calls


def _overlay(app):
    ov = CaptureOverlay()
    pm = QPixmap(*FRAME)
    pm.fill(QColor("#ffffff"))
    ov._snapshot = pm
    ov._selection = SELECTION
    ov._objects = []
    return ov


def _mouse(widget, kind, pos):
    """Событие мыши в координатах виджета (настоящий курсор не двигаем)."""
    local = QPointF(pos[0], pos[1])
    global_pos = QPointF(widget.mapToGlobal(QPoint(pos[0], pos[1])))
    buttons = (Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease
               else Qt.MouseButton.LeftButton)
    return QMouseEvent(kind, local, global_pos, Qt.MouseButton.LeftButton,
                       buttons, Qt.KeyboardModifier.NoModifier)


def test_brand_tooltip_says_about():
    # тултип из спецификации — один и тот же на обеих панелях
    assert panel._SPEC_BY_NAME["brand"][0] == "LogaShot · О программе"


def test_brand_click_opens_about_on_capture_panel(app, about_calls):
    ov = _overlay(app)
    try:
        assert about_calls == []
        ov._panel.button("brand").click()
        assert len(about_calls) == 1
    finally:
        ov.close()


def test_brand_click_opens_about_on_pin_panel(app, about_calls):
    win = pin_mod.PinWindow(_overlay(app))
    win.open()
    try:
        win._panel.button("brand").click()
        assert len(about_calls) == 1
        # другие действия панели диалог не открывают
        win._panel.triggered.emit("cancel")
        assert len(about_calls) == 1
    finally:
        win.close()


def test_brand_drag_does_not_open_about(app, about_calls):
    """Нажали монограмму и сдвинули мышь — это драг, диалог не открывается."""
    win = pin_mod.PinWindow(_overlay(app))
    win.open()
    try:
        btn = win._panel.button("brand")
        centre = (btn.width() // 2, btn.height() // 2)
        moved = (centre[0] + panel._CLICK_SLOP + 6, centre[1])  # ещё внутри кнопки
        btn.mousePressEvent(_mouse(btn, QEvent.Type.MouseButtonPress, centre))
        btn.mouseMoveEvent(_mouse(btn, QEvent.Type.MouseMove, moved))
        btn.mouseReleaseEvent(_mouse(btn, QEvent.Type.MouseButtonRelease, moved))
        assert about_calls == []
        # отпускание без смещения — обычный клик, диалог открывается
        btn.click()
        assert len(about_calls) == 1
    finally:
        win.close()


def test_panel_drag_by_background_still_moves_window(app):
    """Драг панели за фон (не за кнопку) двигает окно, как раньше."""
    win = pin_mod.PinWindow(_overlay(app))
    win.open()
    try:
        start = win.pos()
        press = (2, win._panel.height() - 3)  # поле панели, не кнопка
        win._panel.mousePressEvent(
            _mouse(win._panel, QEvent.Type.MouseButtonPress, press))
        win._panel.mouseMoveEvent(_mouse(
            win._panel, QEvent.Type.MouseMove,
            (press[0] + 18, press[1] - 12)))
        win._panel.mouseReleaseEvent(_mouse(
            win._panel, QEvent.Type.MouseButtonRelease,
            (press[0] + 18, press[1] - 12)))
        assert win.pos() != start
    finally:
        win.close()
