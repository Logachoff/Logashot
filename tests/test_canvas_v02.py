"""P1: сценарии инструментов v0.2 на холсте — маркер/выделение/рамка
рисуются и фиксируются, «Выбор» выбирает и не ставит объекты,
undo работает, Ctrl+S открывает папку а Enter (автосохранение) — нет.

Холст поднимаем без показа оверлея: снапшот — сгенерированный pixmap,
финал «_finish» подменён (без fade и закрытия окна).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

import annotations as ann
import canvas as canvas_mod
import settings as s
import theme
from overlay import CaptureOverlay

SELECTION = (10, 10, 400, 300)


@pytest.fixture(scope="module")
def overlay():
    QApplication.instance() or QApplication([])
    ov = CaptureOverlay()
    pm = QPixmap(800, 600)
    pm.fill(QColor(theme.BG))
    ov._snapshot = pm
    ov._screen = (0, 0, 800, 600)
    ov._snapshot_origin = QPoint(0, 0)
    ov._selection = SELECTION
    ov._finish_calls = []
    ov._finish = lambda: ov._finish_calls.append(True)  # без fade/закрытия
    yield ov


def _click(ov, pos):
    """Честный клик левой кнопкой по холсту: press + release в одной точке."""
    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(*pos),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(*pos),
                          Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.NoModifier)
    ov.mousePressEvent(press)
    ov.mouseReleaseEvent(release)


def _stroke(ov, tool, points):
    """Росчерк/прямоугольник инструментом по цепочке точек (как мышь)."""
    ov._set_tool(None)  # сброс: повторный выбор того же инструмента его снимает
    ov._set_tool(tool)
    assert ov._press_inside(points[0])
    for pos in points[1:]:
        ov._obj_drag_move(pos)
    ov._obj_drag_release(ov._drag_mode, points[-1])


def test_marker_draws_and_undoable(overlay):
    _stroke(overlay, "marker", [(50, 50), (90, 70), (130, 60), (170, 90)])
    assert len(overlay._objects) == 1
    obj = overlay._objects[0]
    assert obj["type"] == "marker"
    assert len(obj["pts"]) >= ann.MARKER_MIN_POINTS
    assert obj["color"] == theme.ANN_RED  # цвет аннотаций
    overlay._undo()
    assert overlay._objects == []
    overlay._redo()
    assert len(overlay._objects) == 1
    overlay._undo()
    overlay._objects.clear()


def test_marker_short_stroke_cancelled(overlay):
    # росчерк короче 3 точек — случайный клик, объект не ставится
    _stroke(overlay, "marker", [(50, 50), (60, 52)])
    assert overlay._objects == []


def test_hl_draws_fixed_yellow(overlay):
    _stroke(overlay, "hl", [(60, 60), (220, 110)])
    obj = overlay._objects[-1]
    assert obj["type"] == "hl"
    assert "color" not in obj  # жёлтый фиксированный, не за цветом аннотаций
    overlay._move_object(obj, 5, 5)
    assert obj["rect"] == (65, 65, 160, 50)
    overlay._objects.clear()


def test_frame_draws_with_ann_color(overlay):
    overlay._on_color_chosen(theme.ANN_BLUE)
    _stroke(overlay, "frame", [(60, 60), (220, 150)])
    obj = overlay._objects[-1]
    assert obj["type"] == "frame"
    assert obj["color"] == theme.ANN_BLUE  # следит за цветом аннотаций
    overlay._objects.clear()


def test_tiny_rect_tools_cancelled(overlay):
    # меньше 12×12 px — отмена (спека v0.2), объект не ставится
    _stroke(overlay, "hl", [(60, 60), (66, 65)])
    _stroke(overlay, "frame", [(60, 60), (65, 66)])
    assert overlay._objects == []


def test_select_tool_picks_object_and_places_nothing(overlay):
    overlay._objects.clear()
    _stroke(overlay, "frame", [(80, 80), (200, 160)])
    count = len(overlay._objects)
    # «Выбор»: клик по обводке рамки выбирает её (рамка ловит клик только
    # по границе — пустота внутри пустое место, дефект 25.10), клик в пустоту —
    # снимает
    ov = overlay
    ov._set_tool(None)
    ov._set_tool("select")
    obj_pos = (ov._objects[0]["rect"][0] + 2, ov._objects[0]["rect"][1] + 2)
    _click(ov, obj_pos)
    assert ov._selected == 0
    _click(ov, (390, 290))  # внутри рамки выделения, мимо объекта
    assert len(ov._objects) == count  # объектов не прибавилось
    assert ov._selected is None  # клик по пустому снял выделение
    ov._objects.clear()


def test_ctrl_s_opens_folder_after_save(overlay, tmp_path, monkeypatch):
    """Ctrl+S: диалог → запись → выход → проводник по фактическому пути.
    Enter — автосохранение: тихий, папку не открывает (решение 24.10)."""
    opened = []
    monkeypatch.setattr(canvas_mod.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(tmp_path / "s.png"), "")))
    monkeypatch.setattr(canvas_mod.storage, "open_shots_folder",
                        lambda folder: opened.append(Path(folder)))
    # автосохранение Enter пишет во временную папку, не в папку снимков
    monkeypatch.setattr(canvas_mod.storage, "shot_dir", lambda home: tmp_path)

    overlay._save_as()
    assert (tmp_path / "s.png").exists()  # файл реально записан
    assert opened == [tmp_path]  # папка открыта по пути сохранения
    assert overlay._finish_calls  # вышли из захвата
    overlay._finish_calls.clear()
    opened.clear()

    overlay._confirm()  # Enter — автосохранение по маске
    assert not opened  # папку не открывали
    assert overlay._finish_calls


def test_hotkey_change_applies_without_restart(overlay, tmp_path, monkeypatch):
    """Запись нового сочетания: хук пересоздан сразу (reload вызван)."""
    reloaded = []
    monkeypatch.setattr(s, "_app_dir", lambda: tmp_path)
    (tmp_path / "portable").touch()
    s.reset_store()
    monkeypatch.setattr(canvas_mod.hotkey, "get_listener",
                        lambda: type("L", (), {"reload": lambda self: reloaded.append(True)})())
    try:
        overlay._on_hotkey_chosen("ctrl+alt+x")
        assert s.capture_hotkey() == "ctrl+alt+x"
        assert reloaded == [True]
    finally:
        s.reset_store()


def test_frame_draft_has_color_while_dragging():
    """Регрессия бага из dev-прогона: draft рамки во время drag обязан
    нести color — иначе paintEvent падает с KeyError на каждый кадр,
    превью рамки не рисуется. Подсветка color не читает."""
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    ov = CaptureOverlay()
    pm = QPixmap(800, 600)
    pm.fill(QColor(theme.BG))
    ov._snapshot = pm
    ov._snapshot_origin = QPoint(0, 0)
    ov._selection = (10, 10, 400, 300)
    ov._set_tool("frame")
    assert ov._press_inside((60, 60))
    ov._obj_drag_move((220, 150))
    assert ov._draft["type"] == "frame"
    assert ov._draft["color"] == theme.ANN_RED  # paintEvent его читает
    ov._obj_drag_release(ov._drag_mode, (220, 150))
    assert ov._objects[-1]["color"] == theme.ANN_RED

    ov._set_tool(None)
    ov._set_tool("hl")
    assert ov._press_inside((60, 60))
    ov._obj_drag_move((220, 110))
    ov._obj_drag_release(ov._drag_mode, (220, 110))
    assert "color" not in ov._objects[-1]  # подсветка — фиксированно жёлтая


def test_marker_preview_follows_cursor(overlay):
    """Росчерк маркера виден ДО отпускания кнопки (как карандаш в Paint):
    _paint_in_progress рисует текущую цепочку точек без падений."""
    from PySide6.QtGui import QPainter, QPixmap
    overlay._set_tool(None)
    overlay._set_tool("marker")
    assert overlay._press_inside((50, 50))
    overlay._obj_drag_move((90, 70))
    overlay._obj_drag_move((130, 60))
    assert overlay._drag_mode != 0  # драг идёт
    pm = QPixmap(400, 300)
    pm.fill(QColor(theme.BG))
    painter = QPainter(pm)
    overlay._paint_in_progress(painter)  # не падает, рисует цепочку
    painter.end()
    overlay._obj_drag_release(overlay._drag_mode, (130, 60))
    assert overlay._objects[-1]["type"] == "marker"
    overlay._objects.clear()


def test_num_tool_activates_from_panel(overlay):
    """Регрессия: клик по кнопке «Номер шага» активирует инструмент
    (num выпал из ветки инструментов _on_panel_action — дефект 24.10)."""
    overlay._on_panel_action("num")
    assert overlay._tool == "num"
    assert overlay._panel.button("num")._active
    overlay._set_tool(None)


def test_num_clicks_inside_frame_object(overlay):
    """Регрессия бага 25.10: клик «Номером» ВНУТРИ рамки-инструмента
    ставит номерок (пустота внутри frame — пустое место холста),
    а не таскает рамку."""
    overlay._objects.clear()
    _stroke(overlay, "frame", [(60, 60), (300, 200)])  # красная рамка
    assert overlay._objects[-1]["type"] == "frame"
    overlay._set_tool(None)
    overlay._set_tool("num")
    _click(overlay, (180, 130))  # центр рамки — пустое место внутри неё
    nums = [o for o in overlay._objects if o["type"] == "num"]
    assert len(nums) == 1, overlay._objects  # номерок поставлен
    assert nums[0]["value"] == 1
    frame = next(o for o in overlay._objects if o["type"] == "frame")
    assert frame["rect"] == (60, 60, 240, 140)  # рамка не сдвинулась
    overlay._objects.clear()


def test_pin_hint_shown_once(overlay, tmp_path, monkeypatch):
    """Пузырь у кнопки пина: один раз за жизнь приложения, флаг в QSettings."""
    monkeypatch.setattr(s, "_app_dir", lambda: tmp_path)
    (tmp_path / "portable").touch()
    s.reset_store()
    monkeypatch.setattr(overlay, "_place_panel", lambda: None)
    try:
        assert not s.pin_hint_shown()
        overlay._panel.adjustSize()
        overlay._panel.show()
        overlay._maybe_show_pin_bubble()
        assert not overlay._pin_bubble.isHidden()  # показан (родитель скрыт —
        # isVisible() здесь не работает, проверяем локальное скрытие)
        assert s.pin_hint_shown()  # показан — флаг выставлен
        overlay._hide_pin_bubble()
        assert overlay._pin_bubble.isHidden()
        overlay._maybe_show_pin_bubble()  # второй раз — не показываем
        assert overlay._pin_bubble.isHidden()
    finally:
        s.reset_store()
        overlay._panel.hide()
