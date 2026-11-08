"""P0-тесты среза «панель у выделения»: чистое позиционирование.

Покрываем правила, которые легко сломать и дорого заметить глазами:
флип панели у нижнего края (отступ 10 px), кламп по горизонтали (6 px),
попап над кнопкой / под кнопкой у верхнего края, тост не перекрывает панель.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import panel_layout
from panel_layout import EDGE_MARGIN, PANEL_GAP, POPUP_GAP, TOAST_GAP

SCREEN = (0, 0, 1920, 1080)
PANEL = (700, 52)
POPUP = (180, 150)
TOAST = (300, 60)


# --- панель ---

def test_panel_below_centered():
    # обычный случай: под выделением, по центру, отступ 10 px
    x, y = panel_layout.panel_place((400, 300, 800, 400), PANEL, SCREEN)
    assert x == 400 + (800 - PANEL[0]) // 2
    assert y == 300 + 400 + PANEL_GAP


def test_panel_flips_above_at_bottom_edge():
    # у нижнего края панель перелетает над выделение с тем же отступом
    _x, y = panel_layout.panel_place((400, 1000, 800, 60), PANEL, SCREEN)
    assert y == 1000 - PANEL[1] - PANEL_GAP


def test_panel_clamps_left():
    x, _ = panel_layout.panel_place((0, 300, 100, 400), PANEL, SCREEN)
    assert x == SCREEN[0] + EDGE_MARGIN


def test_panel_clamps_right():
    x, _ = panel_layout.panel_place((1820, 300, 100, 400), PANEL, SCREEN)
    assert x == SCREEN[0] + SCREEN[2] - PANEL[0] - EDGE_MARGIN


def test_panel_squeezed_top_when_no_space():
    # выделение во весь экран: ни снизу, ни сверху места нет — прижать к верху
    _, y = panel_layout.panel_place((100, 0, 800, 1080), PANEL, SCREEN)
    assert y == SCREEN[1] + EDGE_MARGIN


def test_panel_offset_screen():
    # экран с ненулевым началом (второй монитор): кламп от его краёв
    screen = (1920, 0, 1920, 1080)
    x, _ = panel_layout.panel_place((1920, 300, 100, 400), PANEL, screen)
    assert x == 1920 + EDGE_MARGIN


# --- попап ---

def test_popup_above_button():
    x, y = panel_layout.popup_place((500, 500, 40, 40), POPUP, SCREEN)
    assert x == 500 + (40 - POPUP[0]) // 2
    assert y == 500 - POPUP[1] - POPUP_GAP


def test_popup_below_button_at_top_edge():
    _, y = panel_layout.popup_place((500, 20, 40, 40), POPUP, SCREEN)
    assert y == 20 + 40 + POPUP_GAP


def test_popup_clamps_right():
    x, _ = panel_layout.popup_place((1880, 500, 40, 40), POPUP, SCREEN)
    assert x == SCREEN[0] + SCREEN[2] - POPUP[0] - EDGE_MARGIN


def test_popup_clamps_left():
    x, _ = panel_layout.popup_place((0, 500, 40, 40), POPUP, SCREEN)
    assert x == SCREEN[0] + EDGE_MARGIN


# --- тост ---

def test_toast_above_panel():
    x, y = panel_layout.toast_place((400, 700, 700, 52), TOAST, SCREEN)
    assert x == 400 + (700 - TOAST[0]) // 2
    assert y == 700 - TOAST[1] - TOAST_GAP


def test_toast_below_when_no_space_above():
    _, y = panel_layout.toast_place((400, 20, 700, 52), TOAST, SCREEN)
    assert y == 20 + 52 + TOAST_GAP


def test_toast_never_overlaps_panel():
    # инвариант: ни один расклад не накрывает панель
    for py in (0, 20, 100, 500, 1020):
        panel = (400, py, 700, 52)
        tx, ty = panel_layout.toast_place(panel, TOAST, SCREEN)
        overlap_v = ty < py + 52 and ty + TOAST[1] > py
        overlap_h = tx < 400 + 700 and tx + TOAST[0] > 400
        assert not (overlap_v and overlap_h), f"тост накрыл панель при py={py}"
