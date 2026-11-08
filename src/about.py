"""Диалог «О программе» (план 27.10): минимум по традиции.

Монограмма L из брендовой графики (icons.py — единственный источник графики),
название, версия из version.py, автор и кликабельная ссылка на сайт.
Фон — тёмный NAVY, как у пин-окна; только токены темы, новых цветов нет.
Закрытие — крестик или Esc. Открывается пунктом меню трея «О программе»;
ЛКМ по иконке трея остаётся захватом (решение 16.10).
"""

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import icons
import theme
import version

SITE_URL = "https://logachoff.ru/"  # проверено 27.10
AUTHOR = "Сергей Логачев"
TITLE = "LogaShot"


class AboutDialog(QWidget):
    """Компактная карточка: монограмма, название, версия, автор, сайт."""

    _WIDTH = 300
    _RADIUS = 12

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("О программе")
        self.setFixedWidth(self._WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 22)
        layout.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addStretch(1)
        self.close_button = QPushButton(self)
        # крестик — своя SVG-иконка (без хардкода цвета), 14 px как у шапки
        self.close_button.setIcon(
            QIcon(icons.pixmap("cancel", theme.GRAY, 14,
                               self.devicePixelRatioF())))
        self.close_button.setFixedSize(24, 24)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip("Закрыть")
        self.close_button.setStyleSheet(
            "QPushButton { border: none; background: transparent;"
            " border-radius: 6px; }"
            "QPushButton:hover { background: rgba(255, 255, 255, 18); }")
        self.close_button.clicked.connect(self.close)
        top.addWidget(self.close_button)
        layout.addLayout(top)

        logo = QLabel(self)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(icons.pixmap("brand", theme.BG, 56,
                                    self.devicePixelRatioF()))
        layout.addWidget(logo)

        name = QLabel(TITLE, self)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(
            f"color: {theme.BG}; font-size: 17px; font-weight: 800;"
            f" padding-top: 10px;")
        layout.addWidget(name)

        release = QLabel(f"версия {version.VERSION}", self)
        release.setAlignment(Qt.AlignmentFlag.AlignCenter)
        release.setStyleSheet(
            f"color: {theme.GRAY}; font-size: 12px; padding-top: 3px;")
        self.release_label = release
        layout.addWidget(release)

        author = QLabel(f"Автор: {AUTHOR}", self)
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 12px; padding-top: 14px;")
        layout.addWidget(author)

        self.link = QLabel(
            f'<a href="{SITE_URL}" style="color: {theme.ACCENT};'
            f' text-decoration: none;">logachoff.ru</a>', self)
        self.link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.link.setTextFormat(Qt.TextFormat.RichText)
        self.link.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link.setStyleSheet("font-size: 13px; padding-top: 6px;")
        self.link.linkActivated.connect(self._open_site)
        layout.addWidget(self.link)

    def _open_site(self, _link=None):
        """Ссылка в диалоге: открываем сайт в системном браузере."""
        QDesktopServices.openUrl(QUrl(SITE_URL))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        """Фон карточки: тёмный NAVY со скруглением и светлой окантовкой.

        У окна с WA_TranslucentBackground stylesheet-фон не рисуется (нет
        системного фона) — карточку рисуем сами, как в окне настроек.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        border = QColor(theme.LINE)
        border.setAlpha(165)  # как окантовка пин-окна (Д2)
        painter.setPen(QPen(border, 1))
        painter.setBrush(QColor(theme.NAVY))
        painter.drawRoundedRect(rect, self._RADIUS, self._RADIUS)
        painter.end()


def QIcon_from_theme(dpr):
    """Крестик шапки: своя SVG-иконка на тёмном фоне (без хардкода цвета)."""
    from PySide6.QtGui import QIcon

    return QIcon(icons.pixmap("cancel", theme.GRAY, 14, dpr))


_dialog = None  # один диалог на процесс (как окно настроек)


def show_about():
    """Показать «О программе» по центру экрана с курсором."""
    global _dialog
    if _dialog is None:
        _dialog = AboutDialog()
    _dialog.adjustSize()

    screen = (QGuiApplication.screenAt(QCursor.pos())
              or QGuiApplication.primaryScreen())
    sg = screen.availableGeometry()
    _dialog.move(sg.x() + (sg.width() - _dialog.width()) // 2,
                 sg.y() + (sg.height() - _dialog.height()) // 2)
    _dialog.show()
    _dialog.raise_()
    return _dialog
