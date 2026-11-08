"""Тост уведомления: тёмная плашка с текстом и опциональным
inline-действием («Открыть папку»).

Тост — отдельное окно поверх всех: переживает закрытие оверлея (Enter →
тост «готово» уже после выхода из режима захвата). Позицию считает
panel_layout.toast_place — тост никогда не накрывает панель. Сам появляется
и гаснет с микроанимацией 180 мс ease-out.
Тексты — по гайду тона продукта.
`show_launch()` — тот же тост, но привязанный к иконке трея, а не к панели.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

import animations
import panel_layout
import theme

_SHOW_MS = 2600  # сколько тост висит на экране
_CORNER_ANCHOR = 32  # псевдо-иконка трея у угла экрана, если геометрии нет, px


class Toast(QFrame):
    """Плашка-уведомление: текст + опциональная ссылка-действие."""

    action_clicked = Signal()  # нажали inline-действие

    def __init__(self, text, action_text=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool  # без значка на панели задач
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # не красть фокус
        self.setWindowOpacity(0.0)  # появляемся через fade-in
        # плашку рисуем сами в paintEvent: стилевой фон на полупрозрачном
        # топ-левеле не отрисовывается (проверено пиксельной пробой)
        self.setStyleSheet(
            f"QLabel {{ color: {theme.BG}; font-size: 13px; background: transparent; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(QLabel(text, self))
        if action_text is not None:
            link = QLabel(
                f'<a href="act" style="color: {theme.ACCENT}; text-decoration: none;">'
                f"{action_text}</a>",
                self,
            )
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.linkActivated.connect(self._on_action)
            layout.addWidget(link)

        self._anim = None  # текущая анимация fade (удерживаем ссылку)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show(self):
        super().show()
        self._timer.start(_SHOW_MS)
        self._anim = animations.fade_widget(self, 0.0, 1.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        border = QColor(theme.MUTED)
        border.setAlpha(38)  # кольцо .15 из токенов
        painter.setPen(QPen(border, 1))
        painter.setBrush(QColor(theme.INK))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)
        painter.end()

    def _on_action(self):
        self.action_clicked.emit()
        self._fade_out()

    def _fade_out(self):
        self._timer.stop()
        self._anim = animations.fade_widget(self, self.windowOpacity(), 0.0)
        self._anim.finished.connect(self.close)

    def close(self):
        # тост одноразовый: окно и объект умирают вместе
        self._timer.stop()
        if self._anim is not None:
            self._anim.stop()
        super().close()
        self.deleteLater()


def _screen_rect(anchor):
    """Доступная геометрия экрана под иконкой трея — (sx, sy, sw, sh)."""
    screen = (QGuiApplication.screenAt(anchor.center())
              or QGuiApplication.primaryScreen())
    g = screen.availableGeometry()
    return (g.x(), g.y(), g.width(), g.height())


def _anchor_rect(anchor, screen):
    """Прямоугольник привязки: иконка трея, а без геометрии — угол экрана.

    Win11 прячет иконки в «другие значки», и geometry() бывает пустой;
    тост в этом случае встаёт там же, где живёт трей — у края экрана.
    """
    if anchor.isValid() and not anchor.isEmpty():
        return (anchor.x(), anchor.y(), anchor.width(), anchor.height())
    sx, sy, sw, sh = screen
    return (sx + sw - _CORNER_ANCHOR, sy + sh - _CORNER_ANCHOR,
            _CORNER_ANCHOR, _CORNER_ANCHOR)


def show_launch(text, anchor):
    """Тост о запуске у иконки трея: тот же Toast, без панели.

    Возвращает тост — ссылку держит вызывающий, иначе Qt соберёт окно
    сборщиком мусора. Позиция — по правилам panel_layout.toast_place:
    над иконкой трея, с клампом в экран.
    """
    toast = Toast(text)
    toast.adjustSize()
    screen = _screen_rect(anchor)
    toast.move(*panel_layout.toast_place(
        _anchor_rect(anchor, screen),
        (toast.width(), toast.height()), screen))
    toast.show()
    toast.raise_()
    return toast
