"""Окно первого запуска (идея 20.10, мок v2.12, фича v0.2).

Приложение стартует без окон и выглядит «не запустилось» (баг-репорт
18.10) — поэтому при первом старте показываем короткую инструкцию:
4 пункта «как это работает» и кнопка «Логика понятна )». Показывается
один раз (флаг в QSettings, тот же, что у тоста первого запуска 18.10, —
окно ЗАМЕНЯЕТ тост, решение 24.10). Окно не блокирует трей и хоткей:
обычный топ-левел поверх остальных окон, закрытие — кнопкой или Esc.

Тексты — дословно из мока v2.13 (кадр v212_01_first_run.png).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import theme

_CARD_W = 370  # ширина карточки (мок)
_RADIUS = 16
_HEADLINE = "LogaShot — как это работает"
_SUBTITLE = "Покажу один раз. Дальше — просто работает."
_ITEMS = (
    ("PrtScr", ("Нажми и выдели область. Скриншот сразу сохраняется в "
                "«Рисунки/LogaShot» и копируется в буфер.")),
    ("Ctrl+C", "Кадр в буфер — отправляй куда привык. В почту — Ctrl+M."),
    ("Пин", ("Закрепит скрин поверх окон — переписывай из 1С в Excel, "
             "не переключаясь.")),
    ("Маркер", ("Обведи текст, замажь лишнее, подсвети главное — как в Paint, "
                "только быстрее.")),
)
_BUTTON_TEXT = "Логика понятна )"


class FirstRunWindow(QWidget):
    """Карточка-онбординг: заголовок, 4 пункта с бейджами, кнопка."""

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(_HEADLINE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(0)

        headline = QLabel(_HEADLINE, self)
        headline.setStyleSheet(
            f"color: {theme.INK}; font-size: 17px; font-weight: 800;")
        layout.addWidget(headline)
        subtitle = QLabel(_SUBTITLE, self)
        subtitle.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 12px; padding: 4px 0 14px;")
        layout.addWidget(subtitle)

        for i, (key, text) in enumerate(_ITEMS):
            row = QHBoxLayout()
            row.setSpacing(10)
            badge = QLabel(key, self)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"background: {theme.CARD}; color: {theme.INK};"
                f" border-radius: 7px; padding: 3px 8px;"
                f" font-size: 11px; font-weight: 700;")
            badge.setFixedHeight(24)
            row.addWidget(badge)
            label = QLabel(text, self)
            label.setWordWrap(True)
            label.setStyleSheet(
                f"color: {theme.INK}; font-size: 13px; line-height: 1.45;")
            row.addWidget(label, 1)
            layout.addLayout(row)
            if i < len(_ITEMS) - 1:
                layout.addSpacing(11)

        button = QPushButton(_BUTTON_TEXT, self)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        hover = QColor(theme.ACCENT).darker(115).name()  # hover мока
        button.setStyleSheet(
            f"QPushButton {{ background: {theme.ACCENT}; color: #fff;"
            f" border: none; border-radius: 11px; padding: 11px;"
            f" font-size: 14px; font-weight: 700; margin-top: 21px; }}"
            f"QPushButton:hover {{ background: {hover}; }}"
            f"QPushButton:pressed {{ background: {hover}; }}")
        button.clicked.connect(self.close)
        layout.addWidget(button)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()  # крестика нет (мок): закрытие кнопкой или Esc
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        # карточка: белая плашка со скруглением и мягкой тенью (мок)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        shadow = QColor(theme.NAVY)
        shadow.setAlpha(102)  # rgba(11,17,32,.4) из мока
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawRoundedRect(2, 8, self.width() - 4, self.height() - 12,
                                _RADIUS, _RADIUS)
        painter.setBrush(QColor(255, 255, 255))  # белая карточка (мок)
        painter.drawRoundedRect(0, 0, self.width(), self.height() - 8,
                                _RADIUS, _RADIUS)
        painter.end()


def show_first_run() -> FirstRunWindow | None:
    """Показать окно первого запуска, если ещё не показывали; иначе None."""
    import settings

    if settings.first_run_done():
        return None
    settings.mark_first_run_done()
    win = FirstRunWindow()
    win.setFixedWidth(_CARD_W)
    win.adjustSize()
    # по центру экрана с курсором — там, куда пользователь смотрит
    from PySide6.QtGui import QCursor, QGuiApplication
    screen = (QGuiApplication.screenAt(QCursor.pos())
              or QGuiApplication.primaryScreen())
    sg = screen.availableGeometry()
    win.move(sg.x() + (sg.width() - win.width()) // 2,
             sg.y() + (sg.height() - win.height()) // 2)
    win.show()
    return win
