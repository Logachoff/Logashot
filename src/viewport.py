"""Чистое ядро вьюпорта пин-окна — без Qt, тестируется без UI.

Окно пина — вьюпорт поверх полного кадра:
- изображение масштабируется только ВНИЗ или до 100% — растяжения
  пикселей никогда (zoom <= 1.0);
- дефолтный зум: рамка выделения крупно (~70–80% окна) + контекст кадра;
- ресайз окна = изменение области просмотра, зум при нём не меняется;
- контент меньше вьюпорта — центрируется; больше — прокрутка, вьюпорт
  не выходит за пределы кадра;
- кадр больше вьюпорта — видимые полосы прокрутки,
  их геометрия считается здесь же (`scroll_bars`); полосы прижаты
  к краю окна без зазора, зона ресайза — правый-нижний угол.

Система координат: offset — позиция левого верхнего угла вьюпорта в
МАСШТАБИРОВАННЫХ пикселях кадра (px кадра × zoom); отрицательный offset
означает центровку (контент меньше вьюпорта). Прямоугольники — кортежи
(x, y, w, h), размеры — (w, h).
"""

from typing import NamedTuple

TARGET_FILL = 0.75  # рамка занимает ~75% вьюпорта (допуск 70–80%)
MAX_FILL = 0.8  # дефолтное окно — не крупнее 80% экрана
BAR_THICKNESS = 10  # толщина полосы прокрутки, px


def _clamp_axis(o, v, c):
    """Кламп offset по одной оси: вьюпорт v, контент c (оба в масштаб. px)."""
    if c <= v:
        return (c - v) / 2  # контент меньше вьюпорта — центруем (offset < 0)
    return min(max(o, 0.0), c - v)


def clamp_offset(offset, view, content):
    """Кламп прокрутки: вьюпорт не выходит за пределы контента,
    маленький контент центрируется."""
    return (
        _clamp_axis(offset[0], view[0], content[0]),
        _clamp_axis(offset[1], view[1], content[1]),
    )


def center_on(point, view, content):
    """offset, при котором точка контента (масштаб. px) окажется в центре
    вьюпорта; результат клампится в пределы контента."""
    return clamp_offset(
        (point[0] - view[0] / 2, point[1] - view[1] / 2), view, content
    )


def initial_view(sel, frame, avail, target=TARGET_FILL):
    """Дефолтный вид пин-окна: рамка крупно + контекст кадра.

    sel — рамка выделения (x, y, w, h) в пикселях кадра,
    frame — размер полного кадра (w, h),
    avail — максимальный вьюпорт (w, h), который может дать окно.
    Возвращает (view_w, view_h, zoom, offset):
    - рамка помещается при зуме 1:1 в avail с запасом — вьюпорт такой,
      чтобы рамка заняла ~target окна, зум 1.0;
    - не помещается — вьюпорт максимальный, зум < 1 (только вниз);
    - рамка центрируется во вьюпорте, offset клампится по полному кадру.
    """
    sx, sy, sw, sh = sel
    aw, ah = avail
    if sw <= 0 or sh <= 0 or aw <= 0 or ah <= 0:
        raise ValueError(f"размеры должны быть положительными: {sel}, {avail}")
    if sw / target <= aw and sh / target <= ah:
        # рамка влезает без зума — окно под рамку с контекстом
        view = (round(sw / target), round(sh / target))
        zoom = 1.0
    else:
        view = (aw, ah)
        zoom = min(1.0, target * aw / sw, target * ah / sh)
    # центр рамки в масштабированных пикселях кадра
    center = ((sx + sw / 2) * zoom, (sy + sh / 2) * zoom)
    offset = center_on(center, view, (frame[0] * zoom, frame[1] * zoom))
    return view[0], view[1], zoom, offset


class ScrollBars(NamedTuple):
    """Геометрия полос прокрутки вьюпорта пин-окна.

    view_w/view_h — размер вьюпорта ПОСЛЕ вычета видимых полос: кадр
    рисуется только в этих пределах, ползунки его не перекрывают.
    max_v/max_h — предел прокрутки (0 у оси, где кадр помещается),
    value_v/value_h — положение ползунка = смещению вьюпорта.
    """

    view_w: int
    view_h: int
    vertical: bool
    horizontal: bool
    max_v: int
    max_h: int
    value_v: int
    value_h: int


def scroll_bars(view, content, offset, thickness=BAR_THICKNESS):
    """Полосы прокрутки по размерам кадра и вьюпорта.

    Полоса видна, только если кадр больше вьюпорта по своей оси; появившись,
    она забирает `thickness` у второй оси, поэтому проверка второй оси идёт
    уже с вычетом. Полоса встаёт вплотную к краю окна — зазора нет.
    """
    vw, vh = int(view[0]), int(view[1])
    cw, ch = content
    vertical = ch > vh
    horizontal = cw > vw
    if vertical and cw > vw - thickness:
        horizontal = True
    if horizontal and ch > vh - thickness:
        vertical = True
    view_w = vw - (thickness if vertical else 0)
    view_h = vh - (thickness if horizontal else 0)
    max_v = max(0, round(ch - view_h))
    max_h = max(0, round(cw - view_w))
    return ScrollBars(
        view_w=view_w,
        view_h=view_h,
        vertical=vertical,
        horizontal=horizontal,
        max_v=max_v if vertical else 0,
        max_h=max_h if horizontal else 0,
        value_v=min(max(round(offset[1]), 0), max_v),
        value_h=min(max(round(offset[0]), 0), max_h),
    )
