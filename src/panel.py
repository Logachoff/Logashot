"""Панель инструментов (спецификация v0.2, — мок v2.13).

Одна спецификация (_PANEL_SPEC) для обеих панелей — захвата и пин-окна:
тот же порядок кнопок, тултипы, веса и размер (правка 17.10:
панель пин-окна — та же панель полного размера, одной строкой).
20 кнопок (было 16): добавлены «Выбор» (V), «Маркер» (6),
«Выделение области» (7), «Рамка» (8) — инструменты v0.2.
Три уровня визуального веса (размер и цвет = частота использования):
акцент — только «Копировать»; обычные — сохранить, инструменты разметки,
OCR и «Пин» (заметность пина, решение 24.10: из ghost-группы
выведен к обычным кнопкам); ghost (меньше, --muted) — папка, «в почту»,
масштаб, настройки, закрыть. Dimmed-заглушек нет: OCR (5) с версии 0.3.0 —
обычный работающий инструмент.
Позиционирование — в чистом модуле panel_layout.
"""

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import icons
import panel_layout
import theme

_BTN = 40  # сторона кнопки панели, px (мок: .tb)
_GHOST_DELTA = 6  # ghost меньше обычной: 34 px
_ICON = 20  # иконка обычной кнопки; ghost — на 3 px меньше
_PRESS_SCALE = 0.93  # «утопление» кнопки при нажатии
_CLICK_SLOP = 4  # сдвиг монограммы, после которого это уже не клик, px


def _rgba(hex_color, alpha):
    """Цвет токена с прозрачностью (производные альфы — из токен-файла)."""
    color = QColor(hex_color)
    color.setAlpha(alpha)
    return color


class IconButton(QAbstractButton):
    """Кнопка панели: своя SVG-иконка, hover/нажатие (scale .93)/фокус-кольцо.

    Веса (спецификация 17.10): accent — заливка --accent, квадрат, без
    подписи (только «Копировать»); обычная — полный размер; ghost —
    меньше на _GHOST_DELTA, иконка --muted с прозрачностью, при hover
    загорается.
    """

    def __init__(self, name, tooltip, parent=None, *,
                 accent=False, ghost=False, badge="", brand=False):
        super().__init__(parent)
        self._name = name
        self._accent = accent
        self._ghost = ghost
        self._badge = badge
        self._brand = brand
        self._active = False  # активный инструмент (подсветка --navy)
        self._fill_color = theme.ANN_RED  # для кнопки «Цвет»: точка текущего цвета
        self._press_pos = None  # где нажали монограмму (клик ≠ драг)

        self._badge_font = QFont(self.font())
        self._badge_font.setPixelSize(9)
        self._badge_font.setBold(True)

        self._icon = _ICON
        if ghost:
            self.setFixedSize(_BTN - _GHOST_DELTA, _BTN - _GHOST_DELTA)
        elif brand:
            self.setFixedSize(30, _BTN)  # монограмма чуть уже обычной (мок)
        else:
            self.setFixedSize(_BTN, _BTN)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_badge(self, text):
        """Бейдж в углу кнопки (текущий % масштаба)."""
        self._badge = text
        self.update()

    def set_fill_color(self, hex_color):
        """Цвет заливки иконки (точка текущего цвета аннотаций)."""
        self._fill_color = hex_color
        self.update()

    def set_active(self, active):
        """Подсветка активного инструмента (фон --navy)."""
        self._active = active
        self.update()

    def mousePressEvent(self, event):
        # монограмма открывает «О программе»: запоминаем точку нажатия,
        # чтобы отличить клик от таскания панели за кнопку
        if self._brand and event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._press_pos is not None:
            moved = (event.globalPosition().toPoint()
                     - self._press_pos).manhattanLength()
            self._press_pos = None
            if moved > _CLICK_SLOP:
                # утащили кнопку — это драг, а не клик: диалог не открываем
                self.setDown(False)
                self.update()
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dpr = self.devicePixelRatioF()
        hovered = self.underMouse()

        # фон кнопки
        painter.setPen(Qt.PenStyle.NoPen)
        if self._accent:
            bg = QColor(theme.ACCENT)
            if hovered:
                bg = bg.darker(115)  # производная акцента (как #2f4ae0 в макете)
            painter.setBrush(bg)
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)
        elif self._active:
            painter.setBrush(QColor(theme.NAVY))  # активный инструмент
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)
        elif hovered and not self._brand:
            painter.setBrush(QColor(255, 255, 255, 18))  # rgba(255,255,255,.07) из токенов
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)

        # содержимое: иконка scale .93 вокруг центра; обходим painter.scale,
        # иначе бейдж тоже масштабируется и обрезается границами кнопки
        # (дефект, найденный на тестировании).
        if self._brand:
            painter.setOpacity(1.0 if hovered else 0.45)
        elif self._ghost and not hovered:
            painter.setOpacity(0.85)  # ghost приглушён, но рабочий (мок v2.11)

        icon_color = self._icon_color(hovered)
        icon_size = self._icon
        if self._brand:
            icon_size = 16
        elif self._ghost:
            icon_size -= 3
        pm = icons.pixmap(self._name, icon_color, icon_size, dpr)
        icon_rect = QRect((self.width() - icon_size) // 2,
                          (self.height() - icon_size) // 2,
                          icon_size, icon_size)
        if self.isDown():
            cx, cy = self.width() / 2, self.height() / 2
            x = cx - (cx - icon_rect.x()) * _PRESS_SCALE
            y = cy - (cy - icon_rect.y()) * _PRESS_SCALE
            w = icon_rect.width() * _PRESS_SCALE
            h = icon_rect.height() * _PRESS_SCALE
            icon_rect = QRect(round(x), round(y), round(w), round(h))
        painter.drawPixmap(icon_rect, pm)

        # бейдж рисуем без scale — иначе уходит за края кнопки
        if self._badge:
            painter.setFont(self._badge_font)
            painter.setPen(QColor(theme.BG if hovered else theme.GRAY))
            painter.drawText(self.rect().adjusted(0, 0, -3, -2),
                             Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignBottom,
                             self._badge)

        # фокус-кольцо --accent
        if self.hasFocus():
            painter.setPen(QPen(QColor(theme.ACCENT), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 10, 10)
        painter.end()

    def _icon_color(self, hovered):
        if self._name == "color":
            return self._fill_color  # точка — сам цвет аннотации
        if self._accent or self._active or hovered:
            return theme.BG
        if self._ghost:
            return theme.MUTED  # ghost — редкое действие, цвет --muted
        return theme.GRAY


class _Divider(QWidget):
    """Разделитель групп кнопок: 1 px, rgba(92,107,138,.25) из токенов."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(7, 20)  # линия 1 px по центру + поля 3 px (как в макете)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(3, 0, 1, self.height(), _rgba(theme.MUTED, 64))
        painter.end()


# Состав и порядок панели (спецификация v0.2, мок v2.13); None — разделитель.
# Веса: accent — только «Копировать»; ghost — редкие действия (папка,
# «в почту» без подписи и заливки, масштаб, настройки, закрыть);
# «Пин» и OCR — обычный вес («Пин» — заметность, решение 24.10;
# OCR — рабочий инструмент с 0.3.0); brand — монограмма.
_PANEL_SPEC = (
    ("copy", "Скопировать в буфер — Ctrl+C", {"accent": True}),
    None,
    ("save", "Сохранить копию в папку — Ctrl+S", {}),
    ("select", "Выбор — двигать и править объекты · клавиша V", {}),
    ("arrow", "Стрелка — нажми и потяни · клавиша 1", {}),
    ("text", "Текст — клик и печатай · клавиша 2", {}),
    ("blur", "Замазать чувствительное — мозаика, не чёрный квадрат · клавиша 3", {}),
    ("marker", "Маркер — обведи, как в Paint · клавиша 6", {}),
    ("hl", "Выделение области — подсвети текстовый кусок · клавиша 7", {}),
    ("frame", "Рамка — обведи прямоугольником, цвет как у аннотаций · клавиша 8", {}),
    ("ocr", ("OCR — выдели текст, он попадёт в буфер (локально, без облака)"
             " · клавиша 5"), {}),
    ("num", "Номер шага — клик · клавиша 4", {}),
    ("color", "Цвет аннотаций", {}),
    ("undo", "Отменить — Ctrl+Z", {}),
    None,
    ("folder", "Открыть папку со скриншотами — Ctrl+O", {"ghost": True}),
    ("mail", "Выслать по почте — Ctrl+M", {"ghost": True}),
    ("resize", "Масштаб файла", {"ghost": True, "badge": "100%"}),
    ("pin", "Закрепить поверх окон — скриншот подождёт рядом", {}),
    None,
    ("settings", "Настройки", {"ghost": True}),
    ("cancel", "Отменить — Esc", {"ghost": True}),
    None,
    ("brand", "LogaShot · О программе", {"brand": True}),
)

_SPEC_BY_NAME = {item[0]: (item[1], item[2]) for item in _PANEL_SPEC if item}

_TOOLBAR_STYLE = (
    f"#toolbar {{ background: {theme.INK}; border-radius: 14px;"
    f" border: 1px solid rgba(92, 107, 138, 38); }}"  # кольцо .15 из токенов
)


def _make_button(name, parent, on_trigger):
    """Кнопка панели по имени из спецификации (_PANEL_SPEC)."""
    tooltip, flags = _SPEC_BY_NAME[name]
    btn = IconButton(name, tooltip, parent, **flags)
    btn.clicked.connect(lambda checked=False, n=name: on_trigger(n))
    return btn


def _fill_row(layout, names, parent, on_trigger, buttons, draggable):
    """Ряд кнопок панели; None в names — разделитель."""
    for name in names:
        if name is None:
            div = _Divider(parent)
            if draggable:
                # клики по разделителю идут панели — таскание окна за шапку
                div.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(div)
            continue
        btn = _make_button(name, parent, on_trigger)
        layout.addWidget(btn)
        buttons[name] = btn


class ToolbarPanel(QFrame):
    """Панель у выделения: тёмная (--ink), скругление 14 px, один ряд."""

    triggered = Signal(str)  # имя нажатой кнопки

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setStyleSheet(_TOOLBAR_STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)
        self._buttons = {}
        names = [item if item is None else item[0] for item in _PANEL_SPEC]
        _fill_row(layout, names, self, self.triggered.emit, self._buttons,
                  draggable=False)

    def button(self, name):
        return self._buttons[name]

    def set_active_tool(self, name):
        """Подсветить активный инструмент аннотаций; None — всё погасить."""
        for tool in ("select", "arrow", "text", "blur", "num",
                     "marker", "hl", "frame", "ocr"):
            self._buttons[tool].set_active(tool == name)


class PinPanel(QFrame):
    """Панель пин-окна: ТА ЖЕ панель, что у захвата, одним рядом и того же
    размера (спецификация 17.10 + правка 17.10: «сделай как
    нижнее по размеру»). Одновременно — часть шапки окна: таскание за фон."""

    triggered = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setStyleSheet(_TOOLBAR_STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)
        self._buttons = {}
        names = [item if item is None else item[0] for item in _PANEL_SPEC]
        _fill_row(layout, names, self, self.triggered.emit, self._buttons,
                  draggable=True)
        # «Пин» здесь — обратное действие: тултип «снять с пина» (мок v2.11)
        # и нажатое состояние (подсветка --navy), иначе неочевидно, что
        # кнопка — переключатель обратно в оверлей (правка 17.10)
        pin_btn = self._buttons["pin"]
        pin_btn.setToolTip("Снять с пина — вернуться к захвату")
        pin_btn.set_active(True)
        self._drag_origin = None  # QPoint глобальный, пока тащим окно

    def button(self, name):
        return self._buttons[name]

    def set_active_tool(self, name):
        for tool in ("select", "arrow", "text", "blur", "num",
                     "marker", "hl", "frame", "ocr"):
            self._buttons[tool].set_active(tool == name)

    # таскание окна за шапку: клики по кнопкам не доходят сюда (их едят
    # кнопки), а фон панели и разделители — тащат окно
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None:
            win = self.window()
            if getattr(win, "_maximized", False):
                return  # развёрнутое окно не таскается (как у Windows)
            gp = event.globalPosition().toPoint()
            win.move(win.pos() + (gp - self._drag_origin))
            self._drag_origin = gp

    def mouseReleaseEvent(self, event):
        self._drag_origin = None


class ScalePopup(QFrame):
    """Попап «Масштаб файла»: пресеты 100/75/50 (решение 15.10)."""

    scale_chosen = Signal(int)

    _OPTIONS = ((100, "100% — исходный"), (75, "75% — для переписки"), (50, "50% — для чатов"))

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("popup")
        self.setStyleSheet(
            f"#popup {{ background: {theme.BG}; border-radius: 12px;"
            f" border: 1px solid rgba(22, 33, 62, 20); }}"
            f"QPushButton {{ border: none; background: transparent; text-align: left;"
            f" padding: 8px 10px; border-radius: 7px; font-size: 13px; color: {theme.INK}; }}"
            f"QPushButton:hover {{ background: {theme.CARD}; }}"
            f"QPushButton:checked {{ background: {theme.CARD}; color: {theme.ACCENT};"
            f" font-weight: 700; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)
        label = QLabel("МАСШТАБ ФАЙЛА", self)
        label.setStyleSheet(
            f"color: {theme.LINE}; font-size: 11px; padding: 4px 10px 6px;")
        layout.addWidget(label)
        self._options = {}
        for value, text in self._OPTIONS:
            btn = QPushButton(text, self)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, v=value: self.scale_chosen.emit(v))
            layout.addWidget(btn)
            self._options[value] = btn
        self.set_scale(100)

    def set_scale(self, value):
        for v, btn in self._options.items():
            btn.setChecked(v == value)


class _Swatch(QAbstractButton):
    """Круглый свотч 24 px; выбранный — кольцо --ink + внутреннее кольцо --bg."""

    def __init__(self, hex_color, tooltip, parent=None):
        super().__init__(parent)
        self._color = QColor(hex_color)
        self.setFixedSize(24, 24)
        self.setCheckable(True)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        if self.isChecked():
            painter.setPen(QPen(QColor(theme.INK), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)
            painter.setPen(QPen(QColor(theme.BG), 2))
            painter.drawEllipse(rect.adjusted(3, 3, -3, -3))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(rect.adjusted(4, 4, -4, -4) if self.isChecked() else rect)
        painter.end()


class ColorPopup(QFrame):
    """Попап «Цвет аннотаций»: пресеты из токенов --ann-*."""

    color_chosen = Signal(str)

    _SWATCHES = (
        (theme.ANN_RED, "Красный — ошибка"),
        (theme.ANN_YELLOW, "Жёлтый — обрати внимание"),
        (theme.ANN_BLUE, "Синий — нейтрально"),
    )

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("popup")
        self.setStyleSheet(
            f"#popup {{ background: {theme.BG}; border-radius: 12px;"
            f" border: 1px solid rgba(22, 33, 62, 20); }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        label = QLabel("ЦВЕТ", self)
        label.setStyleSheet(f"color: {theme.LINE}; font-size: 11px;")
        layout.addWidget(label)
        self._swatches = {}
        for hex_color, tooltip in self._SWATCHES:
            sw = _Swatch(hex_color, tooltip, self)
            sw.clicked.connect(lambda checked=False, c=hex_color: self.color_chosen.emit(c))
            layout.addWidget(sw)
            self._swatches[hex_color] = sw
        self.set_color(theme.ANN_RED)

    def set_color(self, hex_color):
        for c, sw in self._swatches.items():
            sw.setChecked(c == hex_color)


class _Toggle(QAbstractButton):
    """Тумблер-«пилюля» 36×20: выкл — --line, вкл — --accent, ручка --bg."""

    def __init__(self, tooltip, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 20)
        self.setCheckable(True)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT if self.isChecked() else theme.LINE))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        knob = rect.height() - 6
        kx = rect.right() - knob - 3 if self.isChecked() else rect.left() + 3
        painter.setBrush(QColor(theme.BG))
        painter.drawEllipse(kx, rect.top() + 3, knob, knob)
        painter.end()


class HotkeyButton(QPushButton):
    """Кнопка записи горячей клавиши (мок v2.13): показывает сочетание,
    по клику — «Жду нажатия…», следующее нажатие записывается.

    Правила записи: принимаем клавишу с модификаторами или одиночную
    (включая PrtScr и F-клавиши); одиночный модификатор — не клавиша,
    ждём дальше; чистый Esc — отмена записи, прежнее значение остаётся.
    """

    hotkey_chosen = Signal(str)  # сочетание в формате keyboard («ctrl+alt+x»)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = ""
        self._listening = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Нажми, затем — новое сочетание")
        self.setStyleSheet(
            f"QPushButton {{ border: 1px solid rgba(22, 33, 62, 46);"
            f" background: {theme.CARD}; border-radius: 8px;"
            f" padding: 4px 10px; font-size: 12px; font-weight: 700;"
            f" color: {theme.INK}; }}"
            f"QPushButton:hover {{ border-color: {theme.ACCENT}; }}"
            f"QPushButton.listening {{ border: 1px solid {theme.ACCENT};"
            f" color: {theme.ACCENT}; background: #fff; }}"
        )
        self.clicked.connect(self._begin_listen)

    def set_hotkey_label(self, label):
        self._label = label
        if not self._listening:
            self.setText(label)

    def _begin_listen(self):
        self._listening = True
        self.setProperty("listening", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText("Жду нажатия…")
        self.setFocus()

    def _cancel_listen(self):
        self._listening = False
        self.setProperty("listening", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(self._label)

    def keyPressEvent(self, event):
        if not self._listening:
            super().keyPressEvent(event)
            return
        import hotkey as hk
        if event.key() == Qt.Key.Key_Escape and not event.modifiers():
            self._cancel_listen()  # отмена записи: прежнее значение остаётся
            return
        modifiers = [Qt.Key.Key_Control, Qt.Key.Key_Alt,
                     Qt.Key.Key_Shift, Qt.Key.Key_Meta]
        if event.key() in modifiers:
            return  # одиночный модификатор — не клавиша, ждём дальше
        keypad = bool(event.modifiers() & Qt.KeyboardModifier.KeypadModifier)
        combo, label = hk.normalize_combo(event.key(), modifiers_active(event),
                                          event.text(), keypad)
        if combo is None:
            return  # неизвестная клавиша — ждём
        self._listening = False
        self.setProperty("listening", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self._label = label
        self.setText(label)
        self.clearFocus()
        self.hotkey_chosen.emit(combo)


def modifiers_active(event):
    """Зажатые модификаторы из QKeyEvent как список Qt.Key."""
    keys = []
    mods = event.modifiers()
    if mods & Qt.KeyboardModifier.ControlModifier:
        keys.append(Qt.Key.Key_Control)
    if mods & Qt.KeyboardModifier.AltModifier:
        keys.append(Qt.Key.Key_Alt)
    if mods & Qt.KeyboardModifier.ShiftModifier:
        keys.append(Qt.Key.Key_Shift)
    if mods & Qt.KeyboardModifier.MetaModifier:
        keys.append(Qt.Key.Key_Meta)
    return keys


class SettingsPopup(QFrame):
    """Попап «Настройки» (шестерёнка): режим панели, визитка, горячая
    клавиша захвата + перехват PrtScr (фича v0.2).

    Значения применяются сразу и хранятся в QSettings (settings.py).
    """

    mode_chosen = Signal(str)  # settings.MODE_IMMEDIATE / MODE_CTRL
    watermark_toggled = Signal(bool)
    hotkey_chosen = Signal(str)  # сочетание в формате keyboard
    suppress_toggled = Signal(bool)
    autostart_toggled = Signal(bool)  # автозагрузка с Windows

    _MODES = (
        ("immediate", "Сразу — панель после выделения"),
        ("ctrl", "По Ctrl — пока держишь клавишу"),
    )

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("popup")
        self.setStyleSheet(
            f"#popup {{ background: {theme.BG}; border-radius: 12px;"
            f" border: 1px solid rgba(22, 33, 62, 20); }}"
            f"QPushButton {{ border: none; background: transparent; text-align: left;"
            f" padding: 8px 10px; border-radius: 7px; font-size: 13px; color: {theme.INK}; }}"
            f"QPushButton:hover {{ background: {theme.CARD}; }}"
            f"QPushButton:checked {{ background: {theme.CARD}; color: {theme.ACCENT}; }}"
            f"QLabel#hint {{ color: {theme.MUTED}; font-size: 13px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)
        title = QLabel("НАСТРОЙКИ", self)
        title.setStyleSheet(
            f"color: {theme.LINE}; font-size: 11px; padding: 4px 10px 6px;")
        layout.addWidget(title)
        self._modes = {}
        for value, text in self._MODES:
            btn = QPushButton(text, self)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, v=value: self.mode_chosen.emit(v))
            layout.addWidget(btn)
            self._modes[value] = btn

        row = QHBoxLayout()
        row.setContentsMargins(10, 8, 10, 6)
        hint = QLabel("Полоска-визитка", self)
        hint.setObjectName("hint")
        row.addWidget(hint)
        row.addStretch(1)
        self._toggle = _Toggle("«Снято в LogaShot» в углу кадра — свободно отключается", self)
        self._toggle.clicked.connect(self._on_toggle)
        row.addWidget(self._toggle)
        layout.addLayout(row)

        # фича v0.2: сочетание захвата (запись по клику) и перехват PrtScr
        row = QHBoxLayout()
        row.setContentsMargins(10, 2, 10, 0)
        hint = QLabel("Горячая клавиша", self)
        hint.setObjectName("hint")
        row.addWidget(hint)
        row.addStretch(1)
        self._hotkey_btn = HotkeyButton(self)
        self._hotkey_btn.hotkey_chosen.connect(self.hotkey_chosen)
        row.addWidget(self._hotkey_btn)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.setContentsMargins(10, 6, 10, 6)
        hint = QLabel("Перехватывать PrtScr у Windows", self)
        hint.setObjectName("hint")
        row.addWidget(hint)
        row.addStretch(1)
        self._suppress = _Toggle(
            "Когда включено, стандартный снимок Windows не откроется", self)
        self._suppress.clicked.connect(self.suppress_toggled)
        row.addWidget(self._suppress)
        layout.addLayout(row)

        # фича v0.2: самопрописывание в автозагрузку Windows
        row = QHBoxLayout()
        row.setContentsMargins(10, 0, 10, 6)
        hint = QLabel("Запускать вместе с Windows", self)
        hint.setObjectName("hint")
        row.addWidget(hint)
        row.addStretch(1)
        self._autostart = _Toggle(
            "LogaShot будет в трее сразу после входа в Windows", self)
        self._autostart.clicked.connect(self.autostart_toggled)
        row.addWidget(self._autostart)
        layout.addLayout(row)

    def _on_toggle(self, checked):
        self.watermark_toggled.emit(checked)

    def set_mode(self, mode):
        for value, btn in self._modes.items():
            btn.setChecked(value == mode)

    def set_watermark(self, enabled):
        self._toggle.setChecked(enabled)

    def set_hotkey_label(self, label):
        self._hotkey_btn.set_hotkey_label(label)

    def set_suppress_prtscr(self, enabled):
        self._suppress.setChecked(enabled)

    def set_autostart(self, enabled):
        self._autostart.setChecked(enabled)


class SettingsWindow(SettingsPopup):
    """Окно настроек из меню трея (Д1): тот же попап, но самостоятельное окно.

    Открывается без запуска захвата. Сигналы те же, что у попапа панели, —
    изменения применяются сразу. Закрывается по Esc или клику мимо (Qt.Popup);
    экземпляр переиспользуется (создаёт его tray.open_settings_window).
    """

    _RADIUS = 12  # как у попапа панели (border-radius в stylesheet #popup)

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.Popup
                            | Qt.WindowType.FramelessWindowHint)
        # скруглённые углы: вокруг контура — прозрачно (рабочий стол виден)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        """Фон и рамка окна.

        У самостоятельного окна с WA_TranslucentBackground stylesheet-фон
        #popup не рисуется (нет системного фона) — окно просвечивало.
        Рисуем те же цвета, что в QSS попапа.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(22, 33, 62, 20), 1))
        painter.setBrush(QColor(theme.BG))
        painter.drawRoundedRect(rect, self._RADIUS, self._RADIUS)
        painter.end()

    def show_at_cursor(self):
        """Показать рядом с курсором (иконка трея) с клампом в пределы экрана."""
        self.adjustSize()
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        sg = screen.availableGeometry()
        self.move(*panel_layout.popup_place(
            (pos.x(), pos.y(), 0, 0), (self.width(), self.height()),
            (sg.x(), sg.y(), sg.width(), sg.height())))
        self.show()
        self.raise_()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
