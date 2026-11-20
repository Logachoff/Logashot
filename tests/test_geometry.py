"""P0-тесты среза «захват области»: чистая геометрия выделения.

Перечень P0 из ТЗ §3а (маска имени, ресайз, undo, блюр) к этому срезу
не применим — этих фич в объёме сессии 1 нет. Покрываем логику, которую
легко сломать и дорого заметить глазами: рамка, минимум 24×24, кламп,
ресайз за 8 ручек, попадание в ручку.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geometry

SCREEN = (0, 0, 1920, 1080)


# --- normalize_rect ---

def test_normalize_drags_all_directions():
    assert geometry.normalize_rect((100, 100), (200, 150)) == (100, 100, 100, 50)
    assert geometry.normalize_rect((200, 150), (100, 100)) == (100, 100, 100, 50)
    assert geometry.normalize_rect((200, 100), (100, 150)) == (100, 100, 100, 50)
    assert geometry.normalize_rect((100, 150), (200, 100)) == (100, 100, 100, 50)


# --- apply_min_size ---

def test_min_size_raises_too_small_rect():
    assert geometry.apply_min_size((10, 10, 3, 5)) == (10, 10, 24, 24)


def test_min_size_keeps_big_rect():
    assert geometry.apply_min_size((10, 10, 300, 200)) == (10, 10, 300, 200)


# --- clamp_to_screen ---

def test_clamp_all_sides():
    assert geometry.clamp_to_screen((-50, -50, 100, 100), SCREEN) == (0, 0, 100, 100)
    assert geometry.clamp_to_screen((1900, 1050, 100, 100), SCREEN) == (1820, 980, 100, 100)


def test_clamp_bigger_than_screen():
    assert geometry.clamp_to_screen((100, 100, 5000, 5000), SCREEN) == (0, 0, 1920, 1080)


def test_clamp_inside_unchanged():
    assert geometry.clamp_to_screen((100, 100, 200, 200), SCREEN) == (100, 100, 200, 200)


# --- handle_points / hit_handle ---

def test_handle_points_corners_and_mids():
    pts = geometry.handle_points((100, 100, 200, 100))
    assert pts[0] == (100, 100)    # TL
    assert pts[2] == (300, 100)    # TR
    assert pts[4] == (300, 200)    # BR
    assert pts[6] == (100, 200)    # BL
    assert pts[1] == (200, 100)    # T
    assert pts[3] == (300, 150)    # R
    assert pts[5] == (200, 200)    # B
    assert pts[7] == (100, 150)    # L


def test_hit_handle_hit_and_miss():
    rect = (100, 100, 200, 100)
    assert geometry.hit_handle(rect, (102, 99), 5) == 0   # TL
    assert geometry.hit_handle(rect, (300, 148), 5) == 3  # R
    assert geometry.hit_handle(rect, (200, 150), 5) is None  # центр — не ручка


# --- resize_by_handle ---

def test_resize_br_moves_only_br():
    rect = (100, 100, 200, 100)
    assert geometry.resize_by_handle(rect, 4, (400, 300), SCREEN) == (100, 100, 300, 200)


def test_resize_tl_moves_only_tl():
    rect = (100, 100, 200, 100)
    assert geometry.resize_by_handle(rect, 0, (50, 50), SCREEN) == (50, 50, 250, 150)


def test_resize_right_edge_only_width():
    rect = (100, 100, 200, 100)
    assert geometry.resize_by_handle(rect, 3, (500, 400), SCREEN) == (100, 100, 400, 100)


def test_resize_respects_min_size():
    rect = (100, 100, 200, 100)
    # тянем BR за противоположный край — сжимается до минимума, не переворачивается
    assert geometry.resize_by_handle(rect, 4, (0, 0), SCREEN) == (100, 100, 24, 24)


def test_resize_tl_respects_min_size():
    rect = (100, 100, 200, 100)
    # тянем TL за правый нижний угол — останавливается на минимуме
    assert geometry.resize_by_handle(rect, 0, (500, 500), SCREEN) == (276, 176, 24, 24)


def test_resize_clamps_to_screen():
    rect = (100, 100, 200, 100)
    assert geometry.resize_by_handle(rect, 4, (9999, 9999), SCREEN) == (100, 100, 1820, 980)
    assert geometry.resize_by_handle(rect, 0, (-500, -500), SCREEN) == (0, 0, 300, 200)


def test_resize_invalid_handle_fails_fast():
    rect = (100, 100, 200, 100)
    try:
        geometry.resize_by_handle(rect, 8, (0, 0), SCREEN)
    except ValueError:
        return
    raise AssertionError("ожидали ValueError для несуществующей ручки")


# --- move_by_delta / inside ---

def test_move_keeps_size_and_clamps():
    rect = (100, 100, 200, 100)
    assert geometry.move_by_delta(rect, 50, 30, SCREEN) == (150, 130, 200, 100)
    assert geometry.move_by_delta(rect, -500, -500, SCREEN) == (0, 0, 200, 100)
    assert geometry.move_by_delta(rect, 9999, 9999, SCREEN) == (1720, 980, 200, 100)


def test_inside():
    rect = (100, 100, 200, 100)
    assert geometry.inside(rect, (150, 150))
    assert not geometry.inside(rect, (50, 50))
    assert not geometry.inside(rect, (100, 100))  # граница — не внутри


def test_resize_by_handle_tuple_min_size():
    # минимумы по осям разные (пин-окно: 360x200, ТЗ п.3)
    rect = geometry.resize_by_handle((100, 100, 500, 400), 4, (200, 150), SCREEN,
                                     min_size=(360, 200))
    assert rect == (100, 100, 360, 200)


def test_window_border_covers_all_four_sides():
    # Д2: контур пин-окна по всему периметру — 4 стороны
    w, h, r = 200, 120, 8
    segments = geometry.window_border(w, h, r)
    lines = [s for s in segments if s[0] == "line"]
    assert len(lines) == 4
    assert any(a[1] == 0.5 and b[1] == 0.5 for _, a, b in lines)  # верх
    assert any(a[1] == h - 0.5 and b[1] == h - 0.5 for _, a, b in lines)  # низ
    assert any(a[0] == 0.5 and b[0] == 0.5 for _, a, b in lines)  # лево
    # право и низ — по крайним пикселям окна: иначе линия на 1 px внутри
    assert any(a[0] == w - 0.5 and b[0] == w - 0.5 for _, a, b in lines)  # право


def test_window_border_rounds_all_four_corners():
    w, h, r = 200, 120, 8
    arcs = [s for s in geometry.window_border(w, h, r) if s[0] == "arc"]
    assert len(arcs) == 4
    assert all(a[1][2] == 2 * r and a[1][3] == 2 * r for a in arcs)
    # центр каждой дуги — в своём углу, радиус r от края
    centers = sorted((round(a[1][0] + r, 1), round(a[1][1] + r, 1)) for a in arcs)
    assert centers == [(0.5 + r, 0.5 + r), (0.5 + r, h - 0.5 - r),
                       (w - 0.5 - r, 0.5 + r), (w - 0.5 - r, h - 0.5 - r)]
