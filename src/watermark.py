"""Полоска-визитка «Снято в LogaShot · logachoff.ru» (спецификация визитки,
решение 11.10: ненавязчивая,
свободно отключаемая, НЕ платная).

Рисуется одной функцией draw() и в оверлее, и в итоговый кадр (файл/буфер
получают кадр с визиткой). Мышь не перехватывает — это рисунок, а не
виджет. Позиция фиксированная: нижний левый угол кадра, отступ 6 px.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

import theme

TEXT = "Снято в LogaShot · logachoff.ru"
_OFFSET = 6  # отступ от границ кадра, px
_PAD_X, _PAD_Y = 8, 3  # padding плашки (спецификация)
_BAR_W, _BAR_H = 14, 2  # skew-черта акцента (спецификация)
_BAR_GAP = 6  # зазор между чертой и текстом
_SKEW = 1.732  # tg(60°): skewX(-60°) уносит низ черты влево на _BAR_H × _SKEW
_FONT_PX = 10


def fits(width, height):
    """Визитка влезает в кадр? Пороги — константы темы (спецификация)."""
    return width > theme.WM_MIN_W and height > theme.WM_MIN_H


def draw(painter, rect):
    """Нарисовать визитку в нижнем левом углу rect=(x, y, w, h)."""
    x, y, _, h = rect
    font = QFont(painter.font())
    font.setPixelSize(_FONT_PX)
    painter.setFont(font)
    metrics = painter.fontMetrics()
    text_w = metrics.horizontalAdvance(TEXT)
    # вылет скоса — часть ширины черты: без него черта наезжает на первую букву
    bar_span = _BAR_H * _SKEW + _BAR_W
    content_w = bar_span + _BAR_GAP + text_w
    pw = content_w + _PAD_X * 2
    ph = metrics.height() + _PAD_Y * 2
    px = x + _OFFSET
    py = y + h - _OFFSET - ph

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # мягкая тень 0 1px 4px rgba(22,33,62,.15) — приближаем одним смещённым
    # прямоугольником (честное размытие тут избыточно)
    shadow = QColor(theme.INK)
    shadow.setAlpha(38)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shadow)
    painter.drawRoundedRect(px, py + 1, pw, ph, 5, 5)
    # белая плашка rgba(255,255,255,.92)
    painter.setBrush(QColor(255, 255, 255, 235))
    painter.drawRoundedRect(px, py, pw, ph, 5, 5)

    # skew-черта: прямоугольник 14×2, скошенный по X на -60° (как в бренде).
    # Левый край черты = px + _PAD_X: начало рисования сдвигаем вправо на
    # вылет скоса (_BAR_H × _SKEW), который уходит влево от точки translate
    bar_cy = py + ph // 2
    painter.save()
    painter.translate(px + _PAD_X + _BAR_H * _SKEW, bar_cy - _BAR_H / 2)
    painter.shear(-_SKEW, 0)  # skewX(-60°) из спецификации
    painter.setBrush(QColor(theme.ACCENT))
    painter.drawRect(0, 0, _BAR_W, _BAR_H)
    painter.restore()

    painter.setPen(QPen(QColor(theme.MUTED)))
    tx = px + _PAD_X + bar_span + _BAR_GAP
    painter.drawText(tx, py + _PAD_Y + metrics.ascent(), TEXT)
    painter.restore()
