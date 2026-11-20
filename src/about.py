"""Диалог «О программе»: минимум по традиции.

Монограмма L из бренд-пакета (icons.py — единственный источник графики),
название, версия из version.py, автор и кликабельная ссылка на сайт.
Фон — тёмный NAVY, как у пин-окна; только токены темы, новых цветов нет.
Закрытие — крестик или Esc. Открывается пунктом меню трея «О программе»;
ЛКМ по иконке трея остаётся захватом (решение 16.10).

«Проверить обновления» (0.4.0) — сеть только по этому клику: кнопка
дизейблится на время запроса, результат появляется строкой в карточке,
отдельных диалогов нет.
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
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import icons
import theme
import updates
import version

SITE_URL = "https://logachoff.ru/"  # сайт автора
AUTHOR = "Сергей Логачев"
TITLE = "LogaShot"

CHECK_TEXT = "Проверить обновления"
BUSY_TEXT = "Проверяю…"
NEWER_TEXT = "Доступна версия"
ACTUAL_TEXT = "У вас актуальная версия"
FAIL_TEXT = "Не удалось проверить — нет связи или GitHub недоступен"
DOWNLOAD_TEXT = "Скачать"

_FLAT_BUTTON = (
    "QPushButton {{ border: none; background: transparent; color: {color};"
    " font-size: {size}px; padding: 6px 8px; }}"
    "QPushButton:hover {{ background: rgba(255, 255, 255, 18);"
    " border-radius: 6px; }}"
    "QPushButton:disabled {{ color: {muted}; }}"
)


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
        # тултип крестика: Qt показывает подсказки только активному окну, а
        # диалог открывается поверх оверлея и активацию забирает сам
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
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

        self.check_button = QPushButton(CHECK_TEXT, self)
        self.check_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_button.setStyleSheet(_FLAT_BUTTON.format(
            color=theme.ACCENT, size=13, muted=theme.MUTED))
        self.check_button.clicked.connect(self._check_updates)
        layout.addWidget(self.check_button)

        # результат — строкой в карточке: версия и «Скачать» или одна фраза
        self.result_row = QWidget(self)
        column = QVBoxLayout(self.result_row)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        self.result_label = QLabel("", self.result_row)
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.setWordWrap(True)
        self.result_label.setTextFormat(Qt.TextFormat.RichText)
        self.result_label.setStyleSheet(
            f"color: {theme.GRAY}; font-size: 12px; padding-top: 4px;")
        column.addWidget(self.result_label)
        self.download_button = QPushButton(DOWNLOAD_TEXT, self.result_row)
        self.download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_button.setStyleSheet(_FLAT_BUTTON.format(
            color=theme.ACCENT, size=12, muted=theme.MUTED))
        self.download_button.clicked.connect(self._open_download)
        self.download_button.hide()
        column.addWidget(self.download_button,
                         0, Qt.AlignmentFlag.AlignHCenter)
        self.result_row.hide()
        layout.addWidget(self.result_row)

        self.checker = updates.UpdateChecker(self)
        self.checker.finished.connect(self._show_result)

    def _open_site(self, _link=None):
        """Ссылка в диалоге: открываем сайт в системном браузере."""
        QDesktopServices.openUrl(QUrl(SITE_URL))

    def _check_updates(self):
        """Кнопка: один запрос за раз, повторный клик во время него — no-op."""
        if self.checker.busy:
            return
        self.result_label.clear()
        self.result_row.hide()
        self.check_button.setEnabled(False)
        self.check_button.setText(BUSY_TEXT)
        self.checker.start()

    def _show_result(self, state, found):
        """Ответ проверки: три состояния, всё в карточке, без диалогов."""
        self.check_button.setEnabled(True)
        self.check_button.setText(CHECK_TEXT)
        if state == updates.NEWER:
            self.result_label.setText(f"{NEWER_TEXT} <b>{found}</b>")
            self.result_label.setStyleSheet(
                f"color: {theme.BG}; font-size: 12px; padding-top: 4px;")
            self.download_button.show()
        else:
            self.result_label.setText(
                ACTUAL_TEXT if state == updates.ACTUAL else FAIL_TEXT)
            self.result_label.setStyleSheet(
                f"color: {theme.GRAY}; font-size: 12px; padding-top: 4px;")
            self.download_button.hide()
        self.result_row.show()
        self.adjustSize()  # карточка выросла на строку результата

    def _open_download(self):
        """«Скачать»: страница последнего релиза в системном браузере."""
        QDesktopServices.openUrl(QUrl(updates.RELEASES_URL))

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
