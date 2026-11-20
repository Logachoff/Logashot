"""P1: порядок операций на отпускании мыши и на клике «Пин» (DS-8, З4.4).

Репорт владельца: «выделил и панель появляется с запозданием, пин с
запозданием включает переход в другое окно». Замеры (dev/perf_probe.py)
показали: на пути показа панели нет ни записи файла, ни истории, ни OCR —
панель показывается сразу. Тест фиксирует этот инвариант: отпускание мыши
не трогает диск и undo-стек, иначе регресс вернёт лаг.

Второй тест — сборка пин-окна: окно собирается, пока оверлей гаснет
(pin_started), и показывается после (pinned). Так сборка не добавляется
к переходу.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

import canvas as canvas_mod
import settings
import storage
from overlay import CaptureOverlay
from pin import PinWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _overlay():
    ov = CaptureOverlay()
    pm = QPixmap(900, 700)
    pm.fill(QColor("#7f8798"))
    ov._snapshot = pm
    ov._screen = (0, 0, 900, 700)
    ov._snapshot_origin = QPoint(0, 0)
    ov._selection = None
    return ov


def _send(widget, kind, pos, buttons=Qt.MouseButton.LeftButton):
    event = QMouseEvent(kind, QPointF(*pos), QPointF(*pos),
                        Qt.MouseButton.LeftButton, buttons,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def _drag(ov, start=(100, 100), end=(600, 500)):
    """Выделение мышью: press → move → release."""
    _send(ov, QEvent.Type.MouseButtonPress, start)
    _send(ov, QEvent.Type.MouseMove, ((start[0] + end[0]) / 2,
                                      (start[1] + end[1]) / 2))
    _send(ov, QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton)


def _wait(ms):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        QApplication.processEvents()
        time.sleep(0.002)


def test_panel_shown_without_disk_or_history_on_release(app, monkeypatch):
    """Показ панели не ждёт автосохранения и записи в историю."""
    def boom(*args, **kwargs):
        raise AssertionError("на отпускании мыши не должно быть записи на диск")

    monkeypatch.setattr(canvas_mod.AnnotationCanvas, "_save_file", boom)
    monkeypatch.setattr(storage, "next_counter", boom)
    monkeypatch.setattr(storage, "open_shots_folder", boom)
    pushes = []
    monkeypatch.setattr(canvas_mod.AnnotationCanvas, "_push_history",
                        lambda self: pushes.append(True))
    # режим панели и флаг подсказки — из настроек машины, в тесте фиксируем
    monkeypatch.setattr(settings, "panel_mode", lambda: settings.MODE_IMMEDIATE)
    monkeypatch.setattr(settings, "pin_hint_shown", lambda: True)

    ov = _overlay()
    try:
        ov._hide_panel()
        _drag(ov)
        assert ov._selection is not None
        # окно в тесте не показано: «показана» = не спрятана явно (как show у ребёнка)
        assert not ov._panel.isHidden(), "панель не показалась после отпускания"
        assert pushes == [], "история не пишется на выделении — нечему ждать"
    finally:
        ov.close()


def test_pin_window_prepared_during_fade_and_shown_after(app):
    """Сборка пин-окна — параллельно анимации закрытия, показ — после неё."""
    ov = _overlay()
    ov._selection = (100, 100, 400, 300)
    prepared, shown, created = [], [], []

    def create():
        win = PinWindow(ov)  # как main.prepare_pin: собрать, но не показывать
        created.append(win)
        prepared.append(win)

    def show():
        win = prepared.pop()  # как main.open_pin: показать готовое окно
        win.open()
        shown.append(win)

    ov.pin_started.connect(create)
    ov.pinned.connect(show)
    try:
        ov._pin_action()
        assert len(prepared) == 1, "окно не собрано к началу анимации"
        assert not prepared[0].isVisible(), "окно показалось до конца анимации"
        assert shown == [], "показ должен ждать конца анимации оверлея"
        _wait(400)
        assert shown == [created[0]], "показали не то окно, что собрали"
        assert shown[0].isVisible()
    finally:
        for win in created:
            win.hide()
            win.close()
        ov.close()
        _wait(50)
