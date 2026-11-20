"""Свои SVG-иконки панели: единый линейный стиль, штрих 1.8 px.

Источник путей — прототип v2 (`03_Прототип/Прототип_v2/index.html`),
наша собственная графика (Правила: чужую графику не копируем).
Рендер в QPixmap через QSvgRenderer с подменой цвета (роль currentColor).
"""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Контурные иконки: viewBox 0 0 24 24, stroke 1.8, скруглённые концы линий
_STROKE = {
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/>'
            '<path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    "save": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 19h16"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5'
              'a2 2 0 0 1-2-2z"/>',
    "resize": '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/>'
              '<path d="M8 21H5a2 2 0 0 1-2-2v-3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "pin": '<path d="M9.5 3.5h5l-.9 5.6 2.9 2.9v2H7.5v-2l2.9-2.9-.9-5.6z"/>'
           '<path d="M12 14v6.5"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "arrow": '<path d="M5 19L19 5"/><path d="M11 5h8v8"/>',
    "text": '<path d="M5 6V4h14v2"/><path d="M12 4v16"/><path d="M9 20h6"/>',
    "ocr": '<path d="M7 20L12 5l5 15"/><path d="M9 14.5h6"/>',
    "num": '<circle cx="12" cy="12" r="8.5"/>'
           '<path d="M12 7v10"/><path d="M9.8 9.2 12 7l2.2 2.2"/>'
           '<path d="M9.5 17h5"/>',  # единица с базисом — читается сразу
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "settings": '<circle cx="12" cy="12" r="3"/>'
                '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83'
                'l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0'
                'v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83'
                'l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09'
                'A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83'
                'l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09'
                'a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83'
                'l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4'
                'h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    "cancel": '<path d="M6 6l12 12M18 6L6 18"/>',
    # v0.2: курсор-выбор (V) — стрелка, как у обычного курсора мыши
    "select": '<path d="M5 3l14 9.5-7.2 1L8.5 21z"/>',
    # маркер (6) — карандаш, как в Paint
    "marker": '<path d="M4 20l1.2-4.2L16.6 4.4a2.05 2.05 0 0 1 2.9 2.9L8.2 19.8 4 20z"/>'
              '<path d="M14.5 6.5l3 3"/>',
    # выделение области (7) — заливка поверх строки текста
    "hl": '<path d="M5 20h14"/><path d="M7.5 15.5l7-7 3 3-7 7z"/>'
          '<path d="M14 6.5l1.5-1.5 3 3L17 9.5"/>',
    # рамка (8) — пунктирный прямоугольник
    "frame": '<rect x="4" y="4" width="16" height="16" rx="2" stroke-dasharray="4 3"/>'
             '<path d="M4 9V4a0 0 0 0 1 0 0h5"/>',
    # кнопки шапки пин-окна (правка владельца 17.10: − ▢ ✕ как у Windows)
    "min": '<path d="M5 12h14"/>',
    "max": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "restore": '<rect x="8" y="8" width="12" height="12" rx="2"/>'
               '<path d="M4 16V6a2 2 0 0 1 2-2h10"/>',
}

# Заливные иконки (роль currentColor играет параметр color)
_FILL = {
    # блюр — пиксельная сетка 2×2 (решение 15.10)
    "blur": '<rect x="3.5" y="3.5" width="5" height="5" rx="1"/>'
            '<rect x="15.5" y="3.5" width="5" height="5" rx="1"/>'
            '<rect x="9.5" y="9.5" width="5" height="5" rx="1"/>'
            '<rect x="3.5" y="15.5" width="5" height="5" rx="1"/>'
            '<rect x="15.5" y="15.5" width="5" height="5" rx="1"/>',
    # цвет аннотаций — точка текущего цвета (заливка = сам цвет)
    "color": '<circle cx="12" cy="12" r="7"/>',
}

# Монограмма L (бренд-пакет 15.10, viewBox синхронизирован с бренд-файлом)
_BRAND_VIEWBOX = "60 40 380 425"
_BRAND_PATHS = (
    '<path d="M 101.93,46.03 L 78.91,45.28 Q 63.00,44.77 63.00,60.69 L 63.00,338.46'
    ' Q 63.00,354.38 76.49,362.85 L 215.82,450.30 Q 229.31,458.77 229.31,442.85'
    ' L 229.31,407.46 Q 229.31,391.54 215.77,383.16 L 131.38,330.92 Q 117.85,322.54'
    ' 117.85,306.62 L 117.85,62.46 Q 117.85,46.54 101.93,46.03 Z"/>'
    '<path d="M 432.44,113.77 L 431.33,60.69 Q 431.00,44.77 415.08,44.77 L 170.92,44.77'
    ' Q 155.00,44.77 155.00,60.69 L 155.00,288.92 Q 155.00,304.85 168.61,313.12'
    ' L 231.62,351.42 Q 245.23,359.69 259.02,351.74 L 323.44,314.57 Q 337.23,306.62'
    ' 338.41,290.74 L 339.59,274.73 Q 340.77,258.85 326.00,264.81 L 263.53,290.04'
    ' Q 248.77,296.00 235.06,287.90 L 223.55,281.10 Q 209.85,273.00 209.85,257.08'
    ' L 209.85,119.08 Q 209.85,103.15 225.77,102.98 L 363.39,101.52 Q 376.15,101.38'
    ' 376.95,114.12 L 377.13,116.95 Q 377.92,129.69 390.69,129.69 L 416.85,129.69'
    ' Q 432.77,129.69 432.44,113.77 Z"/>'
    '<path d="M 432.77,336.69 L 432.77,182.77 Q 432.77,166.85 416.85,166.85'
    ' L 282.38,166.85 Q 266.46,166.85 266.46,182.77 L 266.46,207.54 Q 266.46,223.46'
    ' 282.38,223.71 L 362.00,224.98 Q 377.92,225.23 377.92,241.15 L 377.92,306.62'
    ' Q 377.92,322.54 364.42,330.98 L 278.20,384.87 Q 264.69,393.31 264.69,409.23'
    ' L 264.69,442.85 Q 264.69,458.77 278.16,450.27 L 419.31,361.12 Q 432.77,352.62'
    ' 432.77,336.69 Z"/>'
)

_SVG_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="{}">{}</svg>'

_cache = {}


def _svg_source(name, color):
    if name == "brand":
        return _SVG_HEAD.format(_BRAND_VIEWBOX, f'<g fill="{color}">{_BRAND_PATHS}</g>')
    if name in _FILL:
        return _SVG_HEAD.format("0 0 24 24", f'<g fill="{color}" stroke="none">{_FILL[name]}</g>')
    if name in _STROKE:
        return _SVG_HEAD.format(
            "0 0 24 24",
            f'<g fill="none" stroke="{color}" stroke-width="1.8"'
            f' stroke-linecap="round" stroke-linejoin="round">{_STROKE[name]}</g>',
        )
    raise KeyError(f"неизвестная иконка: {name}")


def pixmap(name, color, size_px, dpr=1.0):
    """QPixmap иконки name цветом color, квадрат size_px (логических), учёт HiDPI."""
    key = (name, color, size_px, dpr)
    if key in _cache:
        return _cache[key]
    renderer = QSvgRenderer(_svg_source(name, color).encode("utf-8"))
    side = max(1, round(size_px * dpr))
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)  # прозрачный фон
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, side, side))
    painter.end()
    pm = QPixmap.fromImage(image)
    pm.setDevicePixelRatio(dpr)
    _cache[key] = pm
    return pm
