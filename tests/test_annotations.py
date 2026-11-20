"""P0: модель аннотаций — автономерация, хит-тесты, уголки."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import annotations as ann


def _num(value, pos=(10, 10)):
    return {"type": "num", "pos": pos, "value": value, "color": "#E5484D", "radius": 14}


def _arrow(tail=(0, 0), bend=(50, 0), tip=(100, 0), width=3):
    return {"type": "arrow", "pts": [tail, bend, tip], "color": "#E5484D", "width": width}


# --- автономерация ---

def test_first_number_is_one():
    assert ann.next_number([]) == 1


def test_numbers_increment():
    objects = [_num(1), _num(2)]
    assert ann.next_number(objects) == 3


def test_deleted_middle_number_not_reused():
    objects = [_num(1), _num(3)]  # двойку удалили — шаги не «съезжают»
    assert ann.next_number(objects) == 4


def test_other_types_ignored_in_numbering():
    assert ann.next_number([_arrow()]) == 1


# --- хит-тесты ---

def test_hit_arrow_polyline():
    obj = _arrow()  # коллинеарные точки — кривая вырождается в прямую
    assert ann.hit_arrow(obj, (50, 3))  # рядом со сгибом
    assert ann.hit_arrow(obj, (100, -2))  # рядом с острием
    assert not ann.hit_arrow(obj, (50, 30))


def test_hit_arrow_curved():
    # точки не коллинеарны: середина кривой (50, 25) далеко от ломаной
    # (расстояние до звеньев ~18 px), клик ловится по самой кривой
    obj = _arrow(tail=(0, 0), bend=(50, 50), tip=(100, 0))
    assert ann.hit_arrow(obj, (50, 25))
    assert not ann.hit_arrow(obj, (50, 45))


def test_hit_arrow_respects_width():
    obj = _arrow(width=10)
    assert ann.hit_arrow(obj, (0, 9))  # толстая линия ловит дальше


def test_hit_rect_types_with_tolerance():
    blur_obj = {"type": "blur", "rect": (10, 10, 40, 30)}
    assert ann.hit_object(blur_obj, (30, 25))
    assert ann.hit_object(blur_obj, (6, 30))  # допуск наружу
    assert not ann.hit_object(blur_obj, (0, 0))


def test_hit_num_uses_badge_square():
    obj = _num(1, pos=(100, 100))
    assert ann.hit_object(obj, (100, 100))
    assert ann.hit_object(obj, (112, 100))
    assert not ann.hit_object(obj, (140, 100))


def test_topmost_is_last_drawn():
    a = _num(1, pos=(10, 10))
    b = _num(2, pos=(12, 12))  # перекрывает первый
    assert ann.topmost_at([a, b], (12, 12)) == 1
    assert ann.topmost_at([a, b], (500, 500)) is None


# --- ручки ---

def test_arrow_anchor_hit():
    obj = _arrow()
    assert ann.hit_arrow_anchor(obj, (1, 1)) == 0
    assert ann.hit_arrow_anchor(obj, (51, -1)) == 1
    assert ann.hit_arrow_anchor(obj, (99, 2)) == 2
    assert ann.hit_arrow_anchor(obj, (50, 40)) is None


def test_corner_handle_of_num():
    obj = _num(1, pos=(100, 100))
    assert ann.corner_point(obj) == (114, 114)
    assert ann.hit_corner(obj, (112, 116))
    assert not ann.hit_corner(obj, (100, 100))


def test_resize_corner_keeps_top_left_and_min():
    assert ann.resize_corner((10, 10, 40, 30), (80, 90)) == (10, 10, 70, 80)
    x, y, w, h = ann.resize_corner((10, 10, 40, 30), (0, 0))
    assert (x, y) == (10, 10)
    assert w == ann.MIN_RECT and h == ann.MIN_RECT


def test_color_discipline():
    # попап цвета работает только с типами, у которых цвет есть
    assert ann.has_color(_arrow())
    assert ann.has_color({"type": "text", "color": "#000"})
    assert ann.has_color(_num(1))
    assert not ann.has_color({"type": "blur", "rect": (0, 0, 1, 1)})


# --- v0.2: маркер, выделение области, рамка ---

def _marker(*pts):
    return {"type": "marker", "pts": list(pts), "color": "#E5484D"}


def _hl(rect=(10, 10, 60, 20)):
    return {"type": "hl", "rect": rect}


def _frame(rect=(10, 10, 60, 20)):
    return {"type": "frame", "rect": rect, "color": "#0B7FFF"}


def test_marker_hit_follows_stroke():
    obj = _marker((0, 0), (50, 0), (50, 50))
    assert ann.hit_object(obj, (25, 2))  # рядом с первым сегментом
    assert ann.hit_object(obj, (50, 25))  # рядом со вторым сегментом
    assert not ann.hit_object(obj, (25, 25))


def test_marker_min_points_and_rect():
    # росчерк короче 3 точек — случайный клик, не объект
    assert ann.MARKER_MIN_POINTS == 3
    obj = _marker((0, 0), (10, 5), (20, 0))
    assert ann.object_rect(obj) == (0, 0, 20, 5)


def test_marker_has_no_resize_handle():
    # маркер ресайзится не за что — только перетаскивание (спека v0.2)
    obj = _marker((0, 0), (10, 0), (20, 0))
    assert not ann.hit_corner(obj, (20, 0))
    assert ann.corner_point(_frame()) == (70, 30)  # у рамки уголок есть


def test_hl_style_fixed_yellow():
    # выделение области: цвет фиксированный, попап цвета не перекрашивает
    assert not ann.has_color(_hl())
    assert ann.HL_FILL == (245, 166, 35, 82)  # rgba(245,166,35,.32)
    assert ann.HL_BORDER == (245, 166, 35, 217)  # rgba(245,166,35,.85)
    assert ann.HL_RADIUS == 3


def test_frame_style_from_annotations():
    # рамка перекрашивается с цветом аннотаций
    assert ann.has_color(_frame())
    assert ann.FRAME_BORDER_W == 3
    assert ann.FRAME_MIN == 12
    assert ann.HL_MIN == 12


def test_frame_hit_only_border():
    """Рамка ловит клик по обводке, пустота внутри — «пустое место»
    (номер внутри красной рамки не ставился)."""
    obj = _frame(rect=(10, 10, 200, 100))
    assert ann.hit_object(obj, (12, 50))  # обводка слева
    assert ann.hit_object(obj, (105, 108))  # обводка снизу
    assert not ann.hit_object(obj, (110, 60))  # центр — пустое место
    assert not ann.hit_object(obj, (500, 500))


def test_rect_types_hit_and_resize_min():
    # подсветка ловит клик по всей площади (это заливка)
    assert ann.hit_object(_hl(), (30, 20))
    assert not ann.hit_object(_hl(), (200, 200))
    # рамка — только по обводке (см. test_frame_hit_only_border)
    assert ann.hit_object(_frame(), (12, 12))
    # ресайз за уголок не опускается ниже минимума 12 px (спека v0.2)
    x, y, w, h = ann.resize_corner((10, 10, 60, 20), (11, 11), min_size=12)
    assert (x, y) == (10, 10) and w == 12 and h == 12
