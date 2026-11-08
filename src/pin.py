"""Пин-окно: скриншот «приложение, а не висящий слой».

Кнопка «Пин» на панели захвата закрывает оверлей и открывает это окно:
- поверх всех окон (WindowStaysOnTopHint), своя рамка по всему периметру —
  она живёт в отдельном слое ВЫШЕ полос прокрутки, иначе полосы её
  перекрывают, и все 4 угла скруглены, без системной рамки;
- содержимое — ПОЛНЫЙ кадр экрана с аннотациями; рамка выделения нарисована
  поверх как пометка (решение 15.10: LogaShot не «режет» по рамке), её можно
  двигать и тянуть за ручки, как в оверлее (правка 17.10);
- окно видно на панели задач: клик по значку сворачивает/восстанавливает
  (правка 17.10: «свернул → поработал → вернулся к скрину»);
- дефолтный зум: рамка крупно (~75% окна) + контекст кадра; растяжения
  пикселей никогда (зум ≤ 100%); при зуме 100% и маленьком окне — прокрутка
  колесом (с Shift — горизонтальная) и видимые полосы прокрутки вьюпорта,
  когда кадр больше окна по оси; полосы прижаты к краю окна,
  над бегунком курсор-рука, свои углы срезаны по контуру окна;
- ресайз окна = изменение области просмотра (вьюпорт), за угол и края,
  правый-нижний угол свободен от полос и тянется всегда,
  минимальная ширина = полная однострочная панель, минимальная
  высота ~200; Aero Snap не делаем;
- сверху — шапка окна с кнопками свернуть/развернуть/закрыть (правка
  17.10, как у обычных окон Windows) и ВСЯ панель одним рядом
  полного размера (PinPanel = панель захвата, правка 17.10);
  таскание — за шапку и фон панели; крестик снимает окно;
- «Пин» — переключатель: возвращает в оверлей с тем же кадром, рамкой,
  аннотациями и историей (решение 13.10);
- в файл и буфер по-прежнему уходит рамка выделения (золотой путь общий
  с оверлеем — canvas.AnnotationCanvas).

Геометрия вьюпорта (зум/клампы/центровка) — чистый модуль viewport.py.
Состояние захвата окно получает копией ссылок из оверлея: новый захват
пересоздаёт объекты оверлея, окна от прошлых кадров не ломаются
(допускается несколько пин-окон).
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QScrollBar,
    QStyle,
    QStyleOptionSlider,
    QWidget,
)

import geometry
import icons
import settings
import theme
import viewport
import watermark
from canvas import (
    _FADE_MS,
    HANDLE_CURSORS,
    HANDLE_HALF,
    AnnotationCanvas,
    _virtual_geometry,
)
from panel import PinPanel

_HEADER_MARGIN = 6  # поля вокруг панели-шапки
_TITLE_H = 28  # высота шапки окна (кнопки − ▢ ✕)
_EDGE = 6  # зона ресайза у краёв окна, px
_CORNER = 14  # верхние углы: ресайз над шапкой, px
_RADIUS = 8  # скругление внешних углов окна (как у окна на скрине)
_MIN_W, _MIN_H = 480, 200  # минимум окна: однострочная панель + высота
_WHEEL_STEP = 60  # прокрутка за один шаг колеса, px вьюпорта

# Полосы прокрутки вьюпорта: тёмный стиль из токенов,
# вплотную к правому и нижнему краю окна — без зазора. Правый-нижний
# угол _GRIP×_GRIP под полосы не отдаётся: там зона ресайза, поэтому угол
# тянется всегда, а драг бегунка приоритетнее по всей своей площади.
_BAR = viewport.BAR_THICKNESS
_GRIP = _BAR  # свободный правый-нижний угол под ресайз окна, px
_SCROLLBAR_QSS = f"""
QScrollBar:vertical {{
    background: {theme.NAVY}; width: {_BAR}px; margin: 0; border: none;
}}
QScrollBar::handle:vertical {{
    background: {theme.MUTED}; min-height: 24px; border-radius: {_BAR // 2}px;
}}
QScrollBar::handle:vertical:hover {{ background: {theme.GRAY}; }}
QScrollBar:horizontal {{
    background: {theme.NAVY}; height: {_BAR}px; margin: 0; border: none;
}}
QScrollBar::handle:horizontal {{
    background: {theme.MUTED}; min-width: 24px; border-radius: {_BAR // 2}px;
}}
QScrollBar::handle:horizontal:hover {{ background: {theme.GRAY}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""

# Режимы драга специфики окна (объектные 0..6 — в canvas.py)
_DRAG_WIN_MOVE = 10      # таскание окна за шапку
_DRAG_WIN_RESIZE = 11    # ресайз окна за край/угол
_DRAG_FRAME_MOVE = 12    # двигаем рамку выделения (правка 17.10)
_DRAG_FRAME_RESIZE = 13  # тянем ручку рамки выделения


class _ScrollBar(QScrollBar):
    """Полоса прокрутки вьюпорта: над бегунком — «рука-захват», при драге —
    сжатая рука, над дорожкой — обычная стрелка.

    Попадание в бегунок спрашиваем у стиля (subControlRect), а не считаем
    пропорцией: зона руки тогда совпадает с нарисованным бегунком, включая
    минимальную длину 24 px из QSS.
    """

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._grab = False  # бегунок тащат (кнопка мыши ещё нажата)
        # без трекинга QWidget отдаёт движения мыши только при зажатой
        # кнопке — курсор-рука над бегунком не появлялся бы
        self.setMouseTracking(True)

    def _over_handle(self, pos):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_ScrollBar, option,
            QStyle.SubControl.SC_ScrollBarSlider, self)
        return handle.contains(pos)

    def _apply_cursor(self, pos):
        if self._grab:
            cursor = Qt.CursorShape.ClosedHandCursor
        elif self._over_handle(pos):
            cursor = Qt.CursorShape.OpenHandCursor
        else:
            cursor = Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._grab = self._over_handle(event.position().toPoint())
        self._apply_cursor(event.position().toPoint())
        super().mousePressEvent(event)

    def enterEvent(self, event):
        # зашли на полосу сразу над бегунком — рука нужна без движения
        self._apply_cursor(event.position().toPoint())
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        self._apply_cursor(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._grab = False
        self._apply_cursor(event.position().toPoint())

    def leaveEvent(self, event):
        self._grab = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)


class _TitleButton(QAbstractButton):
    """Кнопка шапки окна (− ▢ ✕): своя SVG-иконка, hover как у панели;
    у «закрыть» hover — --ann-red (разрушающее действие)."""

    def __init__(self, icon, tooltip, parent, danger=False):
        super().__init__(parent)
        self._icon = icon
        self._danger = danger
        self.setFixedSize(30, _TITLE_H - 4)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = self.underMouse()
        if hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            if self._danger:
                painter.setBrush(QColor(theme.ANN_RED))
            else:
                painter.setBrush(QColor(255, 255, 255, 18))  # rgba(.07) из токенов
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
        color = theme.BG if hovered else theme.GRAY
        pm = icons.pixmap(self._icon, color, 14, self.devicePixelRatioF())
        painter.drawPixmap((self.width() - 14) // 2, (self.height() - 14) // 2, pm)
        painter.end()


class TitleBar(QWidget):
    """Шапка пин-окна: монограмма + «LogaShot» слева, кнопки − ▢ ✕ справа.

    Таскание за шапку двигает окно (в развёрнутом состоянии — не двигает,
    как у Windows), двойной клик — развернуть/восстановить.
    """

    def __init__(self, window):
        super().__init__(window)
        self._win = window
        self._drag_origin = None
        self.setFixedHeight(_TITLE_H)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 2, 2)
        layout.setSpacing(6)
        logo = QLabel(self)
        logo.setPixmap(icons.pixmap("brand", theme.GRAY, 14,
                                    self.devicePixelRatioF()))
        layout.addWidget(logo)
        title = QLabel("LogaShot", self)
        title.setStyleSheet(f"color: {theme.MUTED}; font-size: 12px;")
        layout.addWidget(title)
        layout.addStretch(1)
        self.btn_min = _TitleButton("min", "Свернуть", self)
        self.btn_max = _TitleButton("max", "Развернуть во весь экран", self)
        self.btn_close = _TitleButton("cancel", "Закрыть", self, danger=True)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_max.clicked.connect(window.toggle_maximize)
        self.btn_close.clicked.connect(window._finish)

    def set_maximized(self, maximized):
        self.btn_max._icon = "restore" if maximized else "max"
        self.btn_max.setToolTip("Восстановить" if maximized
                                else "Развернуть во весь экран")
        self.btn_max.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._win.is_maximized():
            self._drag_origin = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None:
            gp = event.globalPosition().toPoint()
            self._win.move(self._win.pos() + (gp - self._drag_origin))
            self._drag_origin = gp

    def mouseReleaseEvent(self, event):
        self._drag_origin = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._win.toggle_maximize()


class _FrameLayer(QWidget):
    """Окантовка окна поверх содержимого: прозрачный слой над полосами.

    Полосы прокрутки — дочерние виджеты, они рисуются ПОСЛЕ paintEvent окна
    и закрывали правый/нижний сегменты рамки, а нижняя полоса (идёт от x=0)
    закрывала ещё и нижнюю левую дугу — угол выглядел квадратным.
    Слой лежит выше полос, рисует только контур и мышь не перехватывает:
    ползунки, края окна и панель работают как раньше.
    """

    def __init__(self, window):
        super().__init__(window)
        # нажатия/наведение проходят сквозь слой к полосам и окну
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        # Окантовка frameless-окна — КОЛЬЦОМ толщиной 1 px: внешний контур
        # совпадает с формой окна (то же скругление, те же координаты), внутренний
        # — на 1 px внутрь. Штрих по середине края ложился на сглаженную кромку
        # окна и на углах распадался на полупрозрачные точки — угол выглядел
        # «погрызенным» (правка по физпроверке 07.11). Цвет — светлый токен
        # LINE, а не полупрозрачный MUTED из мока: иначе окно NAVY сливалось
        # с фоном рабочего стола.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        border = QColor(theme.LINE)
        border.setAlpha(165)
        outer = self._outline(inset=0, radius=_RADIUS)
        inner = self._outline(inset=1, radius=_RADIUS - 1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(border)
        painter.drawPath(outer.subtracted(inner))
        painter.end()

    def _outline(self, inset, radius):
        """Контур окна по сегментам geometry.window_border (смещение/радиус)."""
        path = QPainterPath()
        segments = geometry.window_border(self.width(), self.height(), radius,
                                          inset=inset)
        path.moveTo(*segments[0][1])  # старт верхней грани
        for segment in segments:
            if segment[0] == "line":
                path.lineTo(*segment[2])
            else:
                _, arc_rect, start, sweep = segment
                path.arcTo(*arc_rect, start, sweep)
        path.closeSubpath()
        return path


class PinWindow(AnnotationCanvas):
    """Закреплённое окно с полным кадром и панелью в два ряда."""

    def __init__(self, overlay):
        super().__init__()
        self._overlay = overlay  # куда возвращает кнопка «Пин»
        # состояние захвата — копия ссылок (живёт независимо от оверлея)
        self._snapshot = overlay._snapshot
        self._selection = overlay._selection
        self._objects = overlay._objects
        self._history = overlay._history
        self._scale_percent = overlay._scale_percent
        self._ann_color = overlay._ann_color

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            # БЕЗ Qt.Tool: окно видно на панели задач — клик по значку
            # сворачивает/восстанавливает (правка 17.10:
            # «свернул → поработал → вернулся к скрину»)
        )
        # фокус у рабочего приложения при появлении не отнимаем;
        # по клику окно активируется обычно — клавиши работают
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # из-за WA_ShowWithoutActivating окно никогда не активно, а тултипы
        # Qt показывает только детям активного окна — разрешаем явно.
        # ВАЖНО: атрибут ставится на ОКНО, не на виджет с тултипом
        # (док. Qt, свойство toolTip; баг-репорт 17.10)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # скруглённые углы окна: фон рисуем сами (rounded), за пределами —
        # прозрачно (правка 24.10: «скругление на 4 внешних углах»)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._titlebar = TitleBar(self)
        self._panel = PinPanel(self)
        self._panel.triggered.connect(self._on_panel_action)
        self._wire_popups()

        # полосы прокрутки вьюпорта: видны только когда кадр
        # больше окна по оси, кадр под ними не рисуется (вьюпорт ужимается)
        self._syncing_bars = False  # защита от рекурсии valueChanged ↔ offset
        self._vbar = _ScrollBar(Qt.Orientation.Vertical, self)
        self._hbar = _ScrollBar(Qt.Orientation.Horizontal, self)
        for bar in (self._vbar, self._hbar):
            bar.setStyleSheet(_SCROLLBAR_QSS)
            bar.hide()
        self._vbar.valueChanged.connect(self._on_vscroll)
        self._hbar.valueChanged.connect(self._on_hscroll)
        # окантовка окна — отдельным слоем выше полос
        self._border = _FrameLayer(self)
        # синхронизируем кнопки с состоянием из оверлея
        self._panel.button("resize").set_badge(f"{self._scale_percent}%")
        self._panel.button("color").set_fill_color(self._ann_color)

        self._header_h = 0  # высота шапки (титул + панель + поля), в open()
        self._maximized = False  # развёрнуто на весь экран (кнопка ▢ шапки)
        self._normal_geom = None  # геометрия до разворачивания
        self._zoom = 1.0
        self._offset = (0.0, 0.0)  # левый верх вьюпорта в масштаб. px кадра
        self._win_drag = None  # (режим, ручка, стартовый rect, стартовый глобал)
        self._drag_handle = -1  # ручка рамки выделения при _DRAG_FRAME_RESIZE

        # микроанимация появления/исчезновения
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(_FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._closing = None  # None | "exit" | "unpin"

    # --- открытие и геометрия ---

    def open(self):
        """Разместить окно на экране под курсором и показать с fade."""
        self._panel.adjustSize()
        # шапка = титул (− ▢ ✕) + панель в один ряд + поля
        self._header_h = _TITLE_H + 2 + self._panel.height() + _HEADER_MARGIN
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        sg = screen.availableGeometry()
        fw, fh = self._frame_size()
        avail = (int(sg.width() * viewport.MAX_FILL),
                 int(sg.height() * viewport.MAX_FILL) - self._header_h)
        vw, vh, self._zoom, self._offset = viewport.initial_view(
            self._selection, (fw, fh), avail)
        # минимум окна: вся панель должна помещаться (не обрезать)
        min_w = max(_MIN_W, self._panel.width() + _HEADER_MARGIN * 2)
        min_h = max(_MIN_H, self._header_h + 40)
        self.setMinimumSize(min_w, min_h)
        w = max(vw, min_w)
        h = max(vh + self._header_h, min_h)
        x = sg.x() + (sg.width() - w) // 2
        y = sg.y() + (sg.height() - h) // 2
        self.setGeometry(x, y, w, h)
        # финальный кламп прокрутки под фактический вьюпорт
        self._offset = viewport.clamp_offset(
            self._offset, self._view_size(), self._content_size())
        self._place_header()
        self._update_scrollbars()
        self.setWindowOpacity(0.0)
        self.show()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _view_size(self):
        """Размер вьюпорта (окно минус шапка и видимые полосы прокрутки)."""
        bars = self._bars()
        return bars.view_w, bars.view_h

    def _bars(self):
        """Геометрия полос прокрутки под текущие размеры окна и кадра."""
        return viewport.scroll_bars(
            (self.width(), self.height() - self._header_h),
            self._content_size(), self._offset, thickness=_BAR)

    def _update_scrollbars(self):
        """Показать/спрятать ползунки и синхронизировать их с прокруткой.

        Полосы стоят вплотную к правому и нижнему краю окна, но
        правый-нижний угол _GRIP×_GRIP оставляют окну — там зона ресайза.
        Кадр рисуется только до view_w/view_h, ползунки его не перекрывают
        и в экспорт не попадают (экспорт берёт из снапшота, не с виджета).
        """
        bars = self._bars()
        view_h = min(bars.view_h, self.height() - self._header_h - _GRIP)
        view_w = min(bars.view_w, self.width() - _GRIP)
        self._vbar.setGeometry(bars.view_w, self._header_h, _BAR, view_h)
        # левый конец нижней полосы тоже не доходит до угла на _GRIP: иначе
        # прямоугольная полоса закрашивает скруглённый нижний левый угол
        #, а маска по контуру резала её ступеньками — угол выглядел
        # «погрызенным». Стык не виден: дорожка того же цвета, что фон окна
        self._hbar.setGeometry(_GRIP, self._header_h + bars.view_h,
                               max(0, view_w - _GRIP), _BAR)
        self._vbar.setVisible(bars.vertical)
        self._hbar.setVisible(bars.horizontal)
        self._syncing_bars = True
        for bar, span, page, value in (
            (self._vbar, bars.max_v, bars.view_h, bars.value_v),
            (self._hbar, bars.max_h, bars.view_w, bars.value_h),
        ):
            bar.setRange(0, span)
            bar.setPageStep(page)
            bar.setSingleStep(_WHEEL_STEP // 2)
            bar.setValue(value)
        self._syncing_bars = False
        # слой окантовки — во всю площадь окна и поверх полос: иначе правый,
        # нижний сегменты рамки и нижний левый угол пропадают под ними
        self._border.setGeometry(self.rect())
        self._vbar.raise_()
        self._hbar.raise_()
        self._border.raise_()

    def _scroll_to(self, dx, dy):
        """Прокрутить вьюпорт на смещение (px вьюпорта) и обновить ползунки."""
        self._offset = viewport.clamp_offset(
            (self._offset[0] + dx, self._offset[1] + dy),
            self._view_size(), self._content_size())
        self._update_scrollbars()
        self.update()

    def _on_vscroll(self, value):
        if self._syncing_bars:
            return  # эхо собственной синхронизации, не команда пользователя
        self._commit_text()
        self._scroll_to(0.0, value - self._offset[1])

    def _on_hscroll(self, value):
        if self._syncing_bars:
            return
        self._commit_text()
        self._scroll_to(value - self._offset[0], 0.0)

    def _content_size(self):
        """Размер кадра в масштабированных пикселях."""
        fw, fh = self._frame_size()
        return fw * self._zoom, fh * self._zoom

    def _place_header(self):
        """Шапка: титул во всю ширину сверху, панель под ним по центру."""
        self._titlebar.setGeometry(0, 0, self.width(), _TITLE_H)
        x = max(0, (self.width() - self._panel.width()) // 2)
        self._panel.move(x, _TITLE_H + 2)
        self._titlebar.raise_()
        self._panel.raise_()

    # --- свернуть / развернуть / закрыть (шапка, правка 17.10) ---

    def is_maximized(self):
        return self._maximized

    def toggle_maximize(self):
        """Развернуть на весь экран / восстановить (своя кнопка ▢, без
        Aero Snap — non-goal). В развёрнутом виде края и таскание
        отключены, как у обычных окон."""
        if self._maximized:
            if self._normal_geom is not None:
                self.setGeometry(self._normal_geom)
            self._maximized = False
        else:
            screen = QGuiApplication.screenAt(
                self.geometry().center()) or QGuiApplication.primaryScreen()
            self._normal_geom = self.geometry()
            self.setGeometry(screen.availableGeometry())
            self._maximized = True
        self._titlebar.set_maximized(self._maximized)

    def resizeEvent(self, event):
        # ресайз = вьюпорт (решение 15.10): зум не меняем, клампим прокрутку
        self._commit_text()  # поле ввода не должно «отставать» от кадра
        self._offset = viewport.clamp_offset(
            self._offset, self._view_size(), self._content_size())
        self._place_header()
        self._update_scrollbars()
        super().resizeEvent(event)

    def moveEvent(self, event):
        self._place_toast()  # тост привязан к панели и при таскании окна
        super().moveEvent(event)

    def wheelEvent(self, event):
        """Прокрутка вьюпорта колесом (при зуме 100% и маленьком окне);
        Shift — горизонтальная."""
        self._commit_text()
        steps = -event.angleDelta().y() / 120
        dx, dy = 0.0, steps * _WHEEL_STEP
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            dx, dy = dy, 0.0
        self._scroll_to(dx, dy)

    # --- хуки базового холста: координаты кадра ↔ виджета ---

    def _to_frame(self, pos_view):
        vx, vy = pos_view[0], pos_view[1] - self._header_h
        return (int((vx + self._offset[0]) / self._zoom),
                int((vy + self._offset[1]) / self._zoom))

    def _to_view(self, pos_frame):
        return (round(pos_frame[0] * self._zoom - self._offset[0]),
                round(pos_frame[1] * self._zoom - self._offset[1]) + self._header_h)

    def _tol(self, tol):
        return tol / self._zoom

    def _view_font_size(self, size):
        return max(8, round(size * self._zoom))

    def _idle_cursor(self):
        return Qt.CursorShape.ArrowCursor

    def _inside_cursor(self):
        # рамку в пин-окне можно двигать, как в оверлее (правка 17.10)
        return Qt.CursorShape.SizeAllCursor

    # --- рамка выделения в окне: двигается и тянется (правка 17.10 —
    # в оверлей возвращаться ради правки рамки не нужно) ---

    def _frame_bounds(self):
        return 0, 0, *self._frame_size()

    def _press_chrome(self, pos_view):
        """Ручки рамки выделения (края окна перехвачены раньше — в
        mousePressEvent, поэтому здесь только рамка)."""
        if self._selection is None:
            return False
        pos = self._to_frame(pos_view)
        handle = geometry.hit_handle(self._selection, pos, self._tol(HANDLE_HALF + 2))
        if handle is None:
            return False
        self._drag_mode = _DRAG_FRAME_RESIZE
        self._drag_handle = handle
        self._drag_anchor = self._selection
        self.setCursor(HANDLE_CURSORS[handle])
        return True

    def _press_inside_idle(self, pos_view):
        """Внутри рамки без инструмента — двигаем рамку (как в оверлее)."""
        self._drag_mode = _DRAG_FRAME_MOVE
        self._drag_anchor = (self._selection, self._to_frame(pos_view))
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        return True

    def _chrome_drag_move(self, pos_view):
        pos = self._to_frame(pos_view)
        if self._drag_mode == _DRAG_FRAME_MOVE:
            rect, start = self._drag_anchor
            self._selection = geometry.move_by_delta(
                rect, pos[0] - start[0], pos[1] - start[1], self._frame_bounds())
            self.update()
        elif self._drag_mode == _DRAG_FRAME_RESIZE:
            self._selection = geometry.resize_by_handle(
                self._drag_anchor, self._drag_handle, pos, self._frame_bounds())
            self.update()

    def _toast_anchor(self):
        top_left = self._panel.mapToGlobal(self._panel.rect().topLeft())
        return (top_left.x(), top_left.y(), self._panel.width(), self._panel.height())

    # --- края окна и шапка (своя рамка frameless) ---

    def _edge_handle(self, pos):
        """Индекс ручки (0=TL..7=L, как у geometry) по зоне края или None.

        Правый-нижний угол _GRIP×_GRIP свободен от полос прокрутки и тянется
        всегда, когда окно не развёрнуто. Верхний край занят шапкой —
        ресайз сверху только за углы. В развёрнутом состоянии края не тянутся
        (как у обычных окон).
        """
        if self._maximized:
            return None
        x, y = pos
        w, h = self.width(), self.height()
        if x >= w - _GRIP and y >= h - _GRIP:
            return 4  # правый-нижний угол: полосы до него не доходят
        top = y < _EDGE and (x < _CORNER or x >= w - _CORNER)
        left = x < _EDGE or (y < _EDGE and x < _CORNER)
        right = x >= w - _EDGE or (y < _EDGE and x >= w - _CORNER)
        bottom = y >= h - _EDGE
        if top and left:
            return 0
        if top and right:
            return 2
        if bottom and left:
            return 6
        if bottom and right:
            return 4
        if bottom:
            return 5
        if left:
            return 7
        if right:
            return 3
        return None

    def mousePressEvent(self, event):
        # края окна и шапка перехватывают нажатие раньше аннотаций
        if event.button() == Qt.MouseButton.LeftButton:
            pos = (int(event.position().x()), int(event.position().y()))
            handle = self._edge_handle(pos)
            if handle is not None:
                rect = (self.x(), self.y(), self.width(), self.height())
                self._win_drag = (_DRAG_WIN_RESIZE, handle, rect,
                                  event.globalPosition().toPoint())
                return
            if pos[1] < self._header_h and not self._maximized:
                # шапка вне титула и панели (поля) — таскание окна
                self._win_drag = (_DRAG_WIN_MOVE, None, (self.x(), self.y()),
                                  event.globalPosition().toPoint())
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._win_drag is not None:
            mode, handle, start, start_gp = self._win_drag
            gp = event.globalPosition().toPoint()
            if mode == _DRAG_WIN_MOVE:
                self.move(start[0] + gp.x() - start_gp.x(),
                          start[1] + gp.y() - start_gp.y())
            else:
                rect = geometry.resize_by_handle(
                    start, handle, (gp.x(), gp.y()),
                    _virtual_geometry().getRect(),
                    min_size=(self.minimumWidth(), self.minimumHeight()))
                self.setGeometry(*rect)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._win_drag is not None:
            self._win_drag = None
            return
        super().mouseReleaseEvent(event)

    def _hover_chrome(self, pos):
        if pos[1] < self._header_h:
            self.setCursor(Qt.CursorShape.ArrowCursor)  # шапка
            return True
        handle = self._edge_handle(pos)
        if handle is not None:
            self.setCursor(HANDLE_CURSORS[handle])
            return True
        if self._selection is not None:
            # ручки рамки выделения — те же курсоры-стрелки, что в оверлее
            fh = geometry.hit_handle(self._selection, self._to_frame(pos),
                                     self._tol(HANDLE_HALF + 2))
            if fh is not None:
                self.setCursor(HANDLE_CURSORS[fh])
                return True
        return False

    # --- закрытие и переключатель «Пин» ---

    def _finish(self):
        """Крестик / Esc / действия золотого пути — снять окно."""
        self._begin_close("exit")

    def _pin_action(self):
        """Кнопка «Пин» в окне — вернуться в оверлей к тому же кадру
        и аннотациям (переключатель, решение 13.10)."""
        self._begin_close("unpin")

    def _begin_close(self, action):
        if self._closing is not None:
            return
        self._closing = action
        self._commit_text()
        self._close_popups()
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self):
        if self._closing is None:
            return  # fade на появление — ничего не делаем
        action, self._closing = self._closing, None
        self.hide()
        self.setWindowOpacity(1.0)
        if action == "unpin":
            self._overlay.restore_from(self)
        self.close()

    # --- отрисовка ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # фон окна — скруглённый на ВСЕХ 4 углах; всё содержимое клампится
        # этим контуром, иначе кадр закроет скругления
        r = _RADIUS
        # заливка — во все пиксели окна: окантовка идёт по крайним пикселям
        # (window_border, inset 0.5), и у них должен быть фон окна
        w, h = self.width(), self.height()
        shape = QPainterPath()
        shape.addRoundedRect(0, 0, w, h, r, r)
        painter.save()
        painter.setClipPath(shape)
        painter.fillPath(shape, QColor(theme.NAVY))

        vw, vh = self._view_size()
        painter.save()
        # IntersectClip: иначе заменит клип-контур скругления, и кадр
        # перекроет углы (верх круглый, низ квадратный — дефект 24.10)
        painter.setClipRect(0, self._header_h, vw, vh,
                            Qt.ClipOperation.IntersectClip)
        painter.translate(-self._offset[0], -self._offset[1] + self._header_h)
        painter.scale(self._zoom, self._zoom)
        if self._zoom < 1.0:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, self._snapshot)  # ПОЛНЫЙ кадр
        mosaicked = self._mosaic_source()
        if mosaicked is not None:
            for obj in self._objects:
                if obj["type"] == "blur":
                    rect = QRect(*obj["rect"])
                    painter.drawImage(rect, mosaicked, rect)
        self._paint_objects(painter)
        self._paint_in_progress(painter)
        # блюр, который тащат, рисуем превью — без пересчёта мозаики
        if self._drag_blur_idx is not None:
            self._paint_blur_preview(painter, self._objects[self._drag_blur_idx]["rect"])
        if self._selection is not None:
            # рамка поверх кадра — пометка, а не ножницы (решение 15.10)
            self._paint_dashed_frame(painter, QRect(*self._selection))
            x, y, w, h = self._selection
            if settings.watermark_enabled() and watermark.fits(w, h):
                watermark.draw(painter, (x, y, w, h))
        painter.restore()

        if self._selection is not None:
            # ручки рамки — видимые, как в оверлее (правка 17.10:
            # без отрисовки нащупывался только уголок); рисуются в координатах
            # окна, чтобы не сжиматься зумом
            painter.setPen(QPen(QColor(theme.NAVY), 1))
            painter.setBrush(QColor(theme.BG))
            for hx, hy in geometry.handle_points(self._selection):
                vx, vy = self._to_view((hx, hy))
                painter.drawRect(vx - HANDLE_HALF, vy - HANDLE_HALF,
                                 HANDLE_HALF * 2, HANDLE_HALF * 2)
            self._paint_size_badge(painter)
        # клип-контур скругления снимаем здесь: ручки рамки и плашка размеров
        # у края не должны обрезаться (правка 24.10). Сама окантовка окна
        # живёт в слое _FrameLayer — он выше полос прокрутки
        painter.restore()
        painter.end()

    def _paint_size_badge(self, painter):
        """Плашка размеров у рамки (правила оверлея): шапка окна
        всегда «панель сверху» — плашка рисуется у нижней грани рамки;
        не влезает — над рамкой; кламп в пределы окна."""
        x, y, w, h = self._selection
        text = f"{w} × {h}"
        metrics = painter.fontMetrics()
        pad = 6
        bw = metrics.horizontalAdvance(text) + pad * 2
        bh = metrics.height() + pad
        fx, fb = self._to_view((x, y + h))  # нижний левый угол рамки во вьюпорте
        bx = min(max(fx, 4), self.width() - bw - 4)
        by = fb + 4
        if by + bh > self.height() - 4:
            by = self._to_view((x, y))[1] - bh - 4  # над рамкой
        # кламп в окно (шапка сверху недоступна)
        by = min(max(by, self._header_h + 4), max(self._header_h + 4,
                                                  self.height() - bh - 4))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.NAVY))
        painter.drawRoundedRect(bx, by, bw, bh, 3, 3)
        painter.setPen(QColor(theme.BG))
        painter.drawText(bx + pad, by + pad + metrics.ascent() - 1, text)
