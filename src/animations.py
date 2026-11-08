"""Единый хелпер микроанимаций (150–250 мс, ease-out).

Тайминги и easing — одни и те же для оверлея, панели (QGraphicsOpacityEffect),
пин-окна и тостов. Виджеты/эффекты передаются в помощники; анимация
запускается и хранится внутри виджета, чтобы GC не собрал её в процессе.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSequentialAnimationGroup

_FADE_MS = 180  # внутри диапазона 150–250 мс (решение 13.10)
_EASING = QEasingCurve.Type.OutCubic


def fade_widget(widget, start, end, duration=_FADE_MS, parent=None):
    """Анимация windowOpacity виджета от start до end.

    Возвращает QPropertyAnimation; вызывающий должен удержать ссылку,
    пока анимация не закончится (обычно parent=widget).
    """
    anim = QPropertyAnimation(widget, b"windowOpacity", parent or widget)
    anim.setDuration(duration)
    anim.setEasingCurve(_EASING)
    widget.setWindowOpacity(start)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.start()
    return anim


def fade_effect(effect, start, end, duration=_FADE_MS, parent=None):
    """Анимация opacity у QGraphicsOpacityEffect (панель в оверлее)."""
    anim = QPropertyAnimation(effect, b"opacity", parent or effect)
    anim.setDuration(duration)
    anim.setEasingCurve(_EASING)
    effect.setOpacity(start)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.start()
    return anim


def fade_in_then_out(widget, in_end=1.0, hold_ms=None, out_duration=_FADE_MS,
                     parent=None):
    """Fade-in виджета; при необходимости — последующий fade-out.

    hold_ms=None — только fade-in (вызывающий управляет исчезновением
    самостоятельно). hold_ms задан — автоматический fade-out после паузи.
    """
    anim_in = fade_widget(widget, 0.0, in_end, _FADE_MS, parent or widget)
    if hold_ms is None:
        return anim_in
    group = QSequentialAnimationGroup(parent or widget)
    group.addAnimation(anim_in)
    # пауза в миллисекундах
    pause = QPropertyAnimation(widget, b"windowOpacity", widget)
    pause.setDuration(hold_ms)
    pause.setStartValue(in_end)
    pause.setEndValue(in_end)
    group.addAnimation(pause)
    anim_out = fade_widget(widget, in_end, 0.0, out_duration, parent or widget)
    group.addAnimation(anim_out)
    group.start()
    return group
