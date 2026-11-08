"""Чистая геометрия выделения области — без Qt, под P0-тесты.

Прямоугольник — кортеж (x, y, w, h), координаты целые, левый верхний угол.
Ручки нумеруются по часовой от левого верхнего угла:
0=TL, 1=T, 2=TR, 3=R, 4=BR, 5=B, 6=BL, 7=L.
"""

MIN_SIZE = 24  # минимальный размер выделения, px

# Какие края двигает каждая ручка: (левый, верхний, правый, нижний)
_HANDLE_EDGES = (
    (True, True, False, False),   # 0 TL
    (False, True, False, False),  # 1 T
    (False, True, True, False),   # 2 TR
    (False, False, True, False),  # 3 R
    (False, False, True, True),   # 4 BR
    (False, False, False, True),  # 5 B
    (True, False, False, True),   # 6 BL
    (True, False, False, False),  # 7 L
)


def normalize_rect(p1, p2):
    """Прямоугольник по двум углам драга, в любую сторону."""
    x1, y1 = p1
    x2, y2 = p2
    x, y = min(x1, x2), min(y1, y2)
    return x, y, abs(x2 - x1), abs(y2 - y1)


def clamp_to_screen(rect, screen):
    """Вписать прямоугольник в пределы экрана (sx, sy, sw, sh).

    Размер сохраняется, если помещается; иначе обрезается до экрана.
    """
    x, y, w, h = rect
    sx, sy, sw, sh = screen
    w = min(w, sw)
    h = min(h, sh)
    x = min(max(x, sx), sx + sw - w)
    y = min(max(y, sy), sy + sh - h)
    return x, y, w, h


def apply_min_size(rect, min_size=MIN_SIZE):
    """Поднять ширину и высоту до минимума, не двигая левый верхний угол."""
    x, y, w, h = rect
    return x, y, max(w, min_size), max(h, min_size)


def handle_points(rect):
    """Центры 8 ручек для прямоугольника (x, y, w, h)."""
    x, y, w, h = rect
    xs = (x, x + w // 2, x + w)
    ys = (y, y + h // 2, y + h)
    return [
        (xs[0], ys[0]), (xs[1], ys[0]), (xs[2], ys[0]),
        (xs[2], ys[1]),
        (xs[2], ys[2]), (xs[1], ys[2]), (xs[0], ys[2]),
        (xs[0], ys[1]),
    ]


def hit_handle(rect, pos, tol):
    """Индекс ручки под точкой pos (с допуском tol) или None."""
    px, py = pos
    for i, (hx, hy) in enumerate(handle_points(rect)):
        if abs(px - hx) <= tol and abs(py - hy) <= tol:
            return i
    return None


def resize_by_handle(rect, handle_id, pos, screen, min_size=MIN_SIZE):
    """Новый прямоугольник при тяге ручки handle_id в точку pos.

    Противоположный край неподвижен; размер не ниже минимума,
    результат клампится в экран. min_size — число или пара (w, h)
    (пара нужна пин-окну: минимум окна 360×200).
    """
    if not 0 <= handle_id < 8:
        raise ValueError(f"нет ручки с индексом {handle_id}")
    min_w, min_h = min_size if isinstance(min_size, tuple) else (min_size, min_size)
    x, y, w, h = rect
    left, top, right, bottom = x, y, x + w, y + h
    px, py = pos
    move_l, move_t, move_r, move_b = _HANDLE_EDGES[handle_id]
    sx, sy, sw, sh = screen

    if move_l:
        left = min(max(px, sx), right - min_w)
    if move_t:
        top = min(max(py, sy), bottom - min_h)
    if move_r:
        right = max(min(px, sx + sw), left + min_w)
    if move_b:
        bottom = max(min(py, sy + sh), top + min_h)

    return clamp_to_screen((left, top, right - left, bottom - top), screen)


def move_by_delta(rect, dx, dy, screen):
    """Сдвиг прямоугольника с сохранением размера, кламп в экран."""
    x, y, w, h = rect
    return clamp_to_screen((x + dx, y + dy, w, h), screen)


def inside(rect, pos):
    """Точка строго внутри прямоугольника (для драга-перемещения)."""
    x, y, w, h = rect
    px, py = pos
    return x < px < x + w and y < py < y + h


def window_border(width, height, radius, inset=0.5):
    """Контур рамки frameless-окна по периметру: 4 стороны + 4 скругления.

    Возвращает сегменты по часовой стрелке: ("line", (x0, y0), (x1, y1))
    или ("arc", (x, y, w, h), start_angle, sweep). Координаты идут по
    полупиксельной сетке (inset): pen 1 px центрируется на координате и
    покрывает КРАЙНИЙ пиксель полотна — левый/верхний при x0/y0, правый/
    нижний при x1/y1 (иначе линия уезжает на 1 px внутрь и у правого края
    остаётся полоска фона — дефект на сборке 0.2.2).
    """
    x0 = y0 = inset
    x1 = width - inset
    y1 = height - inset
    d = 2 * radius
    return [
        ("line", (x0 + radius, y0), (x1 - radius, y0)),          # верх
        ("arc", (x1 - d, y0, d, d), 90, -90),                    # верхний правый
        ("line", (x1, y0 + radius), (x1, y1 - radius)),          # право
        ("arc", (x1 - d, y1 - d, d, d), 0, -90),                 # нижний правый
        ("line", (x1 - radius, y1), (x0 + radius, y1)),          # низ
        ("arc", (x0, y1 - d, d, d), 270, -90),                   # нижний левый
        ("line", (x0, y1 - radius), (x0, y0 + radius)),          # лево
        ("arc", (x0, y0, d, d), 180, -90),                       # верхний левый
    ]
