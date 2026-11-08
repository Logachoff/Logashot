"""Перегенерация иконки ТРЕЯ из монограммы брендовой графики.

Иконка приложения (exe, ярлык, установщик) — брендовая, НЕ меняется:
правка 30.10 («на ярлыке было всё хорошо, увеличить только в трее»).
Для трея глиф занимает ~86% холста (было ~56–59%): плитка NAVY со
скруглением 0.225 стороны и белая монограмма по центру. Источник — SVG
монограммы из `assets/`, файл не правим: рендерим QSvgRenderer и
перекрашиваем по альфа-маске. ICO собирается вручную (PNG-слои
16/32/48/256) — как брендовая графика; новых зависимостей нет (только PySide6).

Запуск из корня песочницы: python dev/gen_icon.py
"""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "assets" / "LogaShot_монограмма_L.svg"
ASSET = ROOT / "assets" / "LogaShot_tray.ico"  # только трей, не exe/ярлык
PREVIEW = ROOT / "dev" / "icon_preview.png"

NAVY = "#16213E"  # токен --navy из брендовой графики
WHITE = "#FFFFFF"
RADIUS_RATIO = 0.225  # скругление плитки, как в брендовой графике
GLYPH_RATIO = 0.90  # высота глифа к стороне плитки (видимый глиф ~86%)
SIZES = (16, 32, 48, 256)


def glyph_image(svg, size):
    """Белая монограмма по центру прозрачного холста size×size."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    gh = size * GLYPH_RATIO
    gw = gh * svg.defaultSize().width() / svg.defaultSize().height()
    rect = QRectF((size - gw) / 2, (size - gh) / 2, gw, gh)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    svg.render(painter, rect)
    # SVG хранит NAVY — перекрашиваем в белый, сохраняя альфа-маску
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(img.rect(), QColor(WHITE))
    painter.end()
    return img


def icon_image(svg, size):
    """Плитка: скруглённый NAVY-квадрат + белая монограмма по центру."""
    tile = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    tile.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tile)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(NAVY))
    radius = size * RADIUS_RATIO
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.drawImage(0, 0, glyph_image(svg, size))
    painter.end()
    return tile


def _png(image):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def write_ico(path, images):
    """ICO с PNG-слоями: каталог 6 + 16·N байт, затем данные слоёв."""
    payloads = [_png(img) for img in images]
    entries, blobs = b"", b""
    offset = 6 + 16 * len(images)
    for img, data in zip(images, payloads):
        w = 0 if img.width() >= 256 else img.width()  # 0 = 256 в формате ICO
        h = 0 if img.height() >= 256 else img.height()
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + entries + blobs)


def preview(icons):
    """Превью: 4 слоя подряд + 16px с увеличением без сглаживания."""
    cell, gap = 240, 16
    width = gap + len(icons) * (cell + gap)
    height = 2 * cell + 3 * gap
    sheet = QImage(width, height, QImage.Format.Format_ARGB32)
    sheet.fill(QColor("#F4F6FA"))  # --panel
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    x = gap
    for img in icons:
        painter.drawImage(x, gap, img.scaled(
            cell, cell, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        x += cell + gap
    # 16px без сглаживания: видно пиксели глифа (проверка «не мыло»)
    painter.drawImage(gap, cell + 2 * gap, icons[0].scaled(
        cell, cell, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.FastTransformation))
    painter.end()
    sheet.save(str(PREVIEW))


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    svg = QSvgRenderer(str(BRAND))
    if not svg.isValid():
        print(f"Ошибка: не открылась монограмма {BRAND}", file=sys.stderr)
        return 1
    icons = [icon_image(svg, size) for size in SIZES]
    write_ico(ASSET, icons)
    preview(icons)
    print(f"готово: {ASSET} ({ASSET.stat().st_size} байт), превью {PREVIEW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
