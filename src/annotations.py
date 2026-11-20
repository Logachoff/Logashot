"""Чистое ядро модели аннотаций — без Qt, тестируется без UI.

Объект аннотации — словарь (просто копировать и снапшотить для undo):
- arrow:  {"type", "pts": [(хвост), (сгиб), (острие)], "color", "width"}
- text:   {"type", "pos": (x, y) левый верх, "text", "color", "size",
           "rect": (x, y, w, h)} — rect кэширует UI по метрикам шрифта
- blur:   {"type", "rect": (x, y, w, h)} — цвета нет, мозаика из кадра
- num:    {"type", "pos": (x, y) центр бейджа, "value", "color", "radius"}
- marker: {"type", "pts": [(x, y), ...], "color"} — свободное рисование (v0.2),
          ресайза нет, только перетаскивание; < MARKER_MIN_POINTS точек — отмена
- hl:     {"type", "rect": (x, y, w, h)} — выделение области (v0.2): жёлтая
          полупрозрачная заливка, цвет ФИКСИРОВАННЫЙ (не за цветом аннотаций)
- frame:  {"type", "rect": (x, y, w, h), "color"} — рамка-обводка (v0.2),
          мин. размер MIN_FRAME, иначе отмена

Здесь — только то, что считается без шрифтов и картинок: автономерация,
хит-тесты (клик по объекту, ручки), ресайз за уголок.
"""

ARROW_HIT_TOL = 6  # допуск клика по линии стрелки, px
ANCHOR_HALF = 4  # половина стороны опорной точки стрелки / уголка, px
MIN_RECT = 24  # минимальная рамка блюра, px (как у выделения)
MIN_ARROW = 12  # стрелка короче — случайный клик, не ставим
NUM_RADIUS = 14  # радиус бейджа номера по умолчанию, px
TEXT_SIZE = 16  # размер шрифта аннотации по умолчанию, px

# Маркер (v0.2): цепочка кругов радиуса ~1,75 px, визуально сплошная линия
MARKER_WIDTH = 3.5  # толщина линии росчерка, px
MARKER_DOT_RADIUS = 1.75  # радиус кружка на каждой точке, px
MARKER_MIN_POINTS = 3  # росчерк короче — случайный клик, не ставим
MARKER_POINT_STEP = 2  # мин. расстояние между точками при сборе, px

# Выделение области (v0.2): фон и обводка жёлтые, фиксированные
HL_MIN = 12  # минимальный размер подсветки, px (меньше — отмена)
HL_FILL = (245, 166, 35, 82)  # rgba(245,166,35,.32)
HL_BORDER = (245, 166, 35, 217)  # rgba(245,166,35,.85)
HL_RADIUS = 3  # скругление подсветки, px

# Рамка (v0.2): обводка цвета аннотаций, без заливки
FRAME_MIN = 12  # минимальный размер рамки, px (меньше — отмена)
FRAME_BORDER_W = 3  # толщина обводки, px
FRAME_RADIUS = 3  # скругление углов, px

_COLORED = ("arrow", "text", "num", "marker", "frame")  # типы, которым
# попап цвета меняет цвет; hl фиксированно жёлтый — не перекрашивается


def next_number(objects):
    """Номер следующего шага: максимум существующих + 1, пусто — 1.

    Удаление шага из середины не переиспользует его номер (шаги в
    инструкции не «съезжают»).
    """
    values = [o["value"] for o in objects if o["type"] == "num"]
    return max(values, default=0) + 1


def has_color(obj):
    """Типу объекта попап цвета может назначить цвет (блюр — не может)."""
    return obj["type"] in _COLORED


# --- хит-тесты ---

def _dist_to_segment(p, a, b):
    """Расстояние от точки p до отрезка ab."""
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:  # отрезок выродился в точку
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = min(1.0, max(0.0, t))  # проекция клампится на отрезок
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def _bezier_point(tail, bend, tip, t):
    """Точка квадратичной кривой Безье: (1-t)²·хвост + 2(1-t)t·сгиб + t²·острие."""
    u = 1.0 - t
    return (
        u * u * tail[0] + 2 * u * t * bend[0] + t * t * tip[0],
        u * u * tail[1] + 2 * u * t * bend[1] + t * t * tip[1],
    )


_BEZIER_STEPS = 16  # сэмплов кривой для хит-теста


def hit_arrow(obj, pos, tol=ARROW_HIT_TOL):
    """Клик попал в стрелку? Стрелка — квадратичная кривая (хвост, сгиб —
    управляющая точка, острие), проверяем расстояние до сэмплов кривой."""
    tail, bend, tip = obj["pts"]
    lim = tol + obj["width"] / 2
    prev = tail
    for step in range(1, _BEZIER_STEPS + 1):
        cur = _bezier_point(tail, bend, tip, step / _BEZIER_STEPS)
        if _dist_to_segment(pos, prev, cur) <= lim:
            return True
        prev = cur
    return False


def object_rect(obj):
    """Охватывающий прямоугольник объекта (text/blur/num/marker/hl/frame)."""
    if obj["type"] in ("text", "blur", "hl", "frame"):
        return obj["rect"]
    if obj["type"] == "num":
        cx, cy = obj["pos"]
        r = obj["radius"]
        return cx - r, cy - r, r * 2, r * 2
    if obj["type"] == "marker":
        pts = obj["pts"]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    raise ValueError(f"у объекта нет рамки: {obj['type']}")


def hit_marker(obj, pos, tol=ARROW_HIT_TOL):
    """Клик попал в росчерк маркера? Проверяем расстояние до сегментов
    ломаной через все точки (рисуем круги радиуса MARKER_DOT_RADIUS)."""
    pts = obj["pts"]
    lim = tol + MARKER_DOT_RADIUS
    for i in range(len(pts) - 1):
        if _dist_to_segment(pos, pts[i], pts[i + 1]) <= lim:
            return True
    return False


def hit_object(obj, pos, tol=ARROW_HIT_TOL):
    """Клик по объекту любого типа (рамки — с допуском наружу).

    Рамка-инструмент ловит клик ТОЛЬКО по обводке: пустота внутри —
    «пустое место холста», туда ставятся новые объекты (был баг:
    клик номером внутри красной рамки таскал рамку вместо постановки).
    """
    if obj["type"] == "arrow":
        return hit_arrow(obj, pos, tol)
    if obj["type"] == "marker":
        return hit_marker(obj, pos, tol)
    x, y, w, h = object_rect(obj)
    px, py = pos
    outer = x - tol <= px <= x + w + tol and y - tol <= py <= y + h + tol
    if obj["type"] == "frame":
        inner = FRAME_BORDER_W + tol
        inside = (x + inner <= px <= x + w - inner
                  and y + inner <= py <= y + h - inner)
        return outer and not inside
    return outer


def topmost_at(objects, pos, tol=ARROW_HIT_TOL):
    """Индекс верхнего объекта под точкой или None (рисуем снизу вверх —
    поздний в списке = выше)."""
    for i in range(len(objects) - 1, -1, -1):
        if hit_object(objects[i], pos, tol):
            return i
    return None


# --- ручки редактирования ---

def hit_arrow_anchor(obj, pos, tol=ANCHOR_HALF + 2):
    """Индекс опорной точки стрелки под кликом (0=хвост, 1=сгиб, 2=острие)."""
    px, py = pos
    for i, (ax, ay) in enumerate(obj["pts"]):
        if abs(px - ax) <= tol and abs(py - ay) <= tol:
            return i
    return None


def corner_point(obj):
    """Правый нижний уголок рамки объекта — ручка ресайза (блюр/текст/номер)."""
    x, y, w, h = object_rect(obj)
    return x + w, y + h


def hit_corner(obj, pos, tol=ANCHOR_HALF + 2):
    """Клик попал в уголок ресайза объекта? (у маркера ресайза нет)"""
    if obj["type"] == "marker":
        return False
    cx, cy = corner_point(obj)
    px, py = pos
    return abs(px - cx) <= tol and abs(py - cy) <= tol


def resize_corner(rect, pos, min_size=MIN_RECT):
    """Новая рамка при тяге за правый нижний уголок; левый верх неподвижен.

    Кламп в экран не нужен: рамки объектов и так живут внутри выделения.
    """
    x, y, _, _ = rect
    px, py = pos
    return x, y, max(min_size, px - x), max(min_size, py - y)
