"""Чистое позиционирование панели, попапов и тостов — без Qt, под P0-тесты.

Правила из ТЗ §3г:
- панель — под выделением по центру; у нижнего края экрана перелетает
  наверх (отступ 10 px); по горизонтали клампится с отступом 6 px;
- попап — над кнопкой; у верхнего края — под кнопкой; кламп по горизонтали;
- тост привязан к панели: сверху, если влезает; иначе под панелью —
  панель не перекрывает никогда.

Прямоугольники — кортежи (x, y, w, h), размеры — (w, h), экран — (sx, sy, sw, sh).
"""

PANEL_GAP = 10  # отступ панели от выделения, px (ТЗ §3г)
EDGE_MARGIN = 6  # кламп от краёв экрана, px (ТЗ §3г)
POPUP_GAP = 6  # отступ попапа от кнопки
TOAST_GAP = 8  # отступ тоста от панели


def _clamp_x(x, w, screen):
    """Кламп левого края блока шириной w в пределы экрана с отступом EDGE_MARGIN."""
    sx, _, sw, _ = screen
    lo = sx + EDGE_MARGIN
    hi = max(lo, sx + sw - w - EDGE_MARGIN)
    return min(max(x, lo), hi)


def panel_place(sel, size, screen):
    """Позиция (x, y) панели: под выделением по центру, флип наверх у нижнего края."""
    x, y, w, h = sel
    pw, ph = size
    _, sy, _, sh = screen
    px = _clamp_x(x + (w - pw) // 2, pw, screen)
    py = y + h + PANEL_GAP
    if py + ph + EDGE_MARGIN > sy + sh:
        py = y - ph - PANEL_GAP
    # не влезло ни снизу, ни сверху — прижать к верху
    py = max(py, sy + EDGE_MARGIN)
    return px, py


def popup_place(btn, size, screen):
    """Позиция (x, y) попапа: над кнопкой; у верхнего края — под кнопкой."""
    bx, by, bw, bh = btn
    pw, ph = size
    _, sy, _, sh = screen
    px = _clamp_x(bx + (bw - pw) // 2, pw, screen)
    py = by - ph - POPUP_GAP
    if py < sy + EDGE_MARGIN:
        py = by + bh + POPUP_GAP
    if py + ph + EDGE_MARGIN > sy + sh:  # совсем высокий попап — кламп снизу
        py = max(sy + EDGE_MARGIN, sy + sh - ph - EDGE_MARGIN)
    return px, py


def toast_place(panel, size, screen):
    """Позиция (x, y) тоста: над панелью; нет места сверху — под панелью.

    Гарантия ТЗ §3г: тост никогда не перекрывает панель.
    """
    px, py, pw, ph = panel
    tw, th = size
    _, sy, _, _ = screen
    tx = _clamp_x(px + (pw - tw) // 2, tw, screen)
    ty = py - th - TOAST_GAP
    if ty < sy + EDGE_MARGIN:
        ty = py + ph + TOAST_GAP
    return tx, ty
