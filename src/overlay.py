"""Полноэкранный оверлей режима захвата.

Затемнение поверх всех окон, выделение области мышью: рамка,
плашка размеров, 8 ручек, минимум 24×24 px, кламп в пределы экрана.
Esc — отмена по уровням. Геометрия рамки — в geometry.py (чистое ядро).

Аннотации, инструменты, undo/redo, попапы и золотой путь (Enter/Ctrl+C/
Ctrl+S/Ctrl+O/Ctrl+M) — в базовом классе canvas.AnnotationCanvas, общем
с пин-окном (ТЗ п.3: редактируемость не замораживается в пине). Здесь —
специфика оверлея: затемнение, рамка выделения с ручками, панель у
выделения, режим «по Ctrl», fade-жизненный цикл, разовая подсказка
у кнопки «Пин» (заметность пина, решение владельца 24.10).

Кнопка «Пин» — переключатель (ТЗ п.3): оверлей прячется, состояние
(кадр, рамка, аннотации, история) уходит в пин-окно; возврат — через
restore_from с тем же состоянием.
"""

import ctypes

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel

import geometry
import panel_layout
import perf
import screengrab
import settings
import theme
import watermark
from canvas import (
    _DRAG_NONE,
    _FADE_MS,
    HANDLE_CURSORS,
    HANDLE_HALF,
    AnnotationCanvas,
    _virtual_geometry,
)
from history import History
from panel import ToolbarPanel

_DIM_ALPHA = 120  # прозрачность затемнения (0 — нет, 255 — сплошной)


class _PinBubble(QLabel):
    """Разовая подсказка у кнопки «Пин» (мок v2.13, решение 24.10:
    заметность пина). Акцентная плашка с хвостиком слева снизу.

    Клики проходят сквозь (WA_TransparentForMouseEvents) — не мешает
    работе; скрывается по клику в любом месте или через 8 с. Показывается
    один раз за жизнь приложения (флаг в QSettings)."""

    _TEXT = ("Пин — оставить скрин <b>поверх окон</b>: переписывай "
             "из 1С в Excel, не переключаясь")
    _AUTO_HIDE_MS = 8000

    def __init__(self, parent):
        super().__init__(self._TEXT, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWordWrap(True)
        self.setMaximumWidth(220)
        self.setStyleSheet(
            f"QLabel {{ background: {theme.ACCENT}; color: #fff;"
            f" font-size: 11.5px; font-weight: 600; padding: 8px 12px;"
            f" border-radius: 10px; border-bottom-left-radius: 2px; }}")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def popup_at(self, pos):
        """Показать у позиции (x, y) с автоматическим скрытием через 8 с."""
        self.adjustSize()
        self.move(*pos)
        self.show()
        self.raise_()
        self._timer.start(self._AUTO_HIDE_MS)


def _force_foreground(widget):
    """Windows: дать окну фокус ввода, чтобы Esc срабатывал после Alt+N.

    Qt.activateWindow() иногда не справляется, когда окно показано из
    глобального хука (баг 16 dogfooding); SetForegroundWindow надёжнее.
    """
    try:
        hwnd = int(widget.winId())
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.SetFocus(hwnd)
    except (AttributeError, OSError, ValueError):
        pass  # fail-soft: окна может не быть в момент вызова


# Режимы драга специфики оверлея (объектные 0..6 — в canvas.py)
_DRAG_DRAW = 10     # тянем новое выделение
_DRAG_MOVE = 11     # двигаем рамку выделения
_DRAG_RESIZE = 12   # тянем ручку рамки выделения


class CaptureOverlay(AnnotationCanvas):
    """Оверлей на все мониторы; один кадр захвата — одно появление."""

    cancelled = Signal()  # пользователь нажал Esc
    pinned = Signal()  # кнопка «Пин»: оверлей спрятался, пора показать пин-окно
    pin_started = Signal()  # «Пин» нажат: оверлей гаснет, окно можно собирать

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # без значка на панели задач
        )
        # тултипы Qt показывает только активному окну. Оверлей — topmost
        # tool-окно: фокус ему отдаётся через SetForegroundWindow, но после
        # любого диалога и на части систем активации нет — подсказки кнопок
        # молча пропадали (З4.1, «то есть, то нет»). ВАЖНО: атрибут ставится
        # на ОКНО, а не на кнопку с тултипом (док. Qt, свойство toolTip).
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._screen = (0, 0, 1, 1)  # экран в локальных координатах виджета
        self._drag_handle = -1

        # Микроанимация: только прозрачность, ввод доступен с первого кадра
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(_FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._closing = False  # False | "cancel" | "pin" — куда идёт fade

        # Панель инструментов у выделения (ТЗ §3г)
        self._panel = ToolbarPanel(self)
        self._panel.triggered.connect(self._on_panel_action)
        self._panel.hide()
        self._panel_fade = None
        self._wire_popups()
        self._pin_bubble = _PinBubble(self)  # разовая подсказка (фича v0.2)
        self._pin_bubble.hide()

    # --- жизненный цикл ---

    def start(self):
        """Снять кадр экрана и показать оверлей с плавным появлением."""
        vg = _virtual_geometry()
        self._snapshot = self._grab_desktop(vg)
        self._snapshot_origin = vg.topLeft()  # глобальные координаты левого верхнего угла снимка
        self._screen = (0, 0, vg.width(), vg.height())  # активная область в координатах кадра
        self.setGeometry(vg)
        self._selection = None
        self._drag_mode = _DRAG_NONE
        self._closing = False
        self._discard_text()
        self._objects = []
        self._history = History()
        self._selected = None
        self._draft = None
        self._set_tool(None)
        self._scale_percent = 100  # каждый новый захват — исходный масштаб
        self._mosaicked = None
        self._blur_dirty = True
        self._hide_panel()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        _force_foreground(self)
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def cancel(self):
        """Отмена захвата: плавное исчезновение и сигнал наружу."""
        self._discard_text()
        self._closing = "cancel"
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self):
        # fade завершился: на появление — ничего не делаем, на закрытие — прячемся
        if not self._closing:
            return
        mode, self._closing = self._closing, False
        self._hide_panel()
        self.hide()
        self.setWindowOpacity(1.0)
        if mode == "pin":
            self.pinned.emit()  # ТЗ п.3: оверлей полностью закрывается
        else:
            self.cancelled.emit()

    def _grab_desktop(self, vg):
        """Кадр всех мониторов в одном pixmap (учёт devicePixelRatio каждого экрана)."""
        result = QPixmap(vg.size())
        result.fill(QColor(theme.NAVY))  # зазоры между мониторы — фирменный тёмный
        painter = QPainter(result)
        for screen in QGuiApplication.screens():
            pm = screen.grabWindow(0)
            if screengrab.mono(pm):  # RDP: Qt-путь иногда даёт чёрный кадр
                pm = QPixmap.fromImage(screengrab.grab_gdi(screen.geometry()))
            target = QRect(screen.geometry().topLeft() - vg.topLeft(), screen.geometry().size())
            painter.drawPixmap(target, pm)
        painter.end()
        return result

    def _active_screen_for(self, rect):
        """Монитор, содержащий центр выделения (rect — в координатах кадра);
        fallback — наибольшее перекрытие. Возвращает глобальный QRect."""
        ox, oy = self._snapshot_origin.x(), self._snapshot_origin.y()
        gr = QRect(rect[0] + ox, rect[1] + oy, rect[2], rect[3])
        cx = gr.x() + gr.width() // 2
        cy = gr.y() + gr.height() // 2
        for screen in QGuiApplication.screens():
            sg = screen.geometry()
            if sg.contains(cx, cy):
                return sg
        best = QGuiApplication.primaryScreen().geometry()
        best_area = 0
        for screen in QGuiApplication.screens():
            sg = screen.geometry()
            inter = sg.intersected(gr)
            if not inter.isEmpty():
                area = inter.width() * inter.height()
                if area > best_area:
                    best_area = area
                    best = sg
        return best

    def _fit_to_active_screen(self):
        """После появления выделения оставить затемнение только на том мониторе,
        где оно создано; остальные мониторы возвращаются в работу (баг 9).

        Геометрия окна меняется, а координаты кадра остаются нетронутыми —
        маппинг локальных координат в координаты кадра учитывает смещение."""
        if self._selection is None:
            return
        sg = self._active_screen_for(self._selection)  # глобальный QRect монитора
        ox, oy = self._snapshot_origin.x(), self._snapshot_origin.y()
        new_screen = (sg.x() - ox, sg.y() - oy, sg.width(), sg.height())
        if new_screen == self._screen:
            return
        self.setGeometry(sg)
        self._screen = new_screen
        self._place_panel()
        self.update()

    # --- пин-переключатель (ТЗ п.3) ---

    def _pin_action(self):
        """Кнопка «Пин»: оверлей закрывается, состояние уйдёт в пин-окно."""
        if self._selection is None:
            return
        perf.mark("pin_click")
        self._close_popups()
        self._closing = "pin"  # fade на закрытие, но без сигнала cancelled
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        # пин-окно собирается, пока оверлей гаснет (180 мс): сборка не
        # добавляется к переходу, а идёт параллельно анимации (З4.4)
        self.pin_started.emit()
        self._fade.start()

    def restore_from(self, pin):
        """Возврат из пин-окна: тот же кадр, рамка, аннотации и история
        (решение 13.10: свободное туда-обратное переключение без потерь)."""
        self._snapshot = pin._snapshot
        self._selection = pin._selection
        self._objects = pin._objects
        self._history = pin._history
        self._scale_percent = pin._scale_percent
        self._ann_color = pin._ann_color
        self._mosaicked = pin._mosaicked
        self._blur_dirty = pin._blur_dirty
        self._selected = None
        self._draft = None
        self._closing = False
        self._set_tool(None)
        # синхронизируем кнопки с состоянием, которое могло меняться в окне
        self._panel.button("resize").set_badge(f"{self._scale_percent}%")
        self._panel.button("color").set_fill_color(self._ann_color)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        _force_foreground(self)
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        if settings.panel_mode() == settings.MODE_IMMEDIATE:
            self._show_panel()
        self.update()

    # --- хуки базового холста ---

    def _finish(self):
        self.cancel()

    def _toast_anchor(self):
        if not self._panel.isVisible():
            return None
        ox, oy = self.x(), self.y()
        return (
            self._panel.x() + ox, self._panel.y() + oy,
            self._panel.width(), self._panel.height(),
        )

    def _to_frame(self, pos_view):
        """Локальные координаты оверлея → координаты кадра (учёт обрезки
        окна до монитора: локальный (0,0) окна = глобальный geometry().topLeft(),
        кадр начинается в snapshot_origin)."""
        gx, gy = self.geometry().x(), self.geometry().y()
        ox, oy = self._snapshot_origin.x(), self._snapshot_origin.y()
        return (pos_view[0] + gx - ox, pos_view[1] + gy - oy)

    def _to_view(self, pos_frame):
        """Координаты кадра → локальные координаты оверлея."""
        gx, gy = self.geometry().x(), self.geometry().y()
        ox, oy = self._snapshot_origin.x(), self._snapshot_origin.y()
        return (pos_frame[0] - gx + ox, pos_frame[1] - gy + oy)

    def _idle_cursor(self):
        return Qt.CursorShape.CrossCursor

    def _inside_cursor(self):
        # внутри рамки без инструмента — рамку можно двигать
        return Qt.CursorShape.SizeAllCursor

    def _press_chrome(self, pos):
        """Ручки рамки выделения."""
        if self._selection is None:
            return False
        pos = self._to_frame(pos)
        handle = geometry.hit_handle(self._selection, pos, HANDLE_HALF + 2)
        if handle is None:
            return False
        self._drag_mode = _DRAG_RESIZE
        self._drag_handle = handle
        self._drag_anchor = self._selection
        self.setCursor(HANDLE_CURSORS[handle])
        return True

    def _press_inside_idle(self, pos):
        """Внутри рамки без инструмента — двигаем рамку."""
        self._drag_mode = _DRAG_MOVE
        self._drag_anchor = (self._selection, self._to_frame(pos))
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        return True

    def _press_outer(self, pos):
        """Пустое место снаружи — новое выделение; аннотации привязаны
        к рамке и вместе с ней сгорают (новый холст)."""
        self._drag_mode = _DRAG_DRAW
        self._drag_anchor = self._to_frame(pos)
        self._selection = None
        self._objects = []
        self._history = History()
        self._draft = None
        self._blur_dirty = True
        self._hide_panel()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def _chrome_drag_move(self, pos):
        pos = self._to_frame(pos)
        if self._drag_mode == _DRAG_DRAW:
            rect = geometry.normalize_rect(self._drag_anchor, pos)
            rect = geometry.clamp_to_screen(geometry.apply_min_size(rect), self._screen)
            self._selection = rect
            self.update()
        elif self._drag_mode == _DRAG_MOVE:
            rect, start = self._drag_anchor
            self._selection = geometry.move_by_delta(
                rect, pos[0] - start[0], pos[1] - start[1], self._screen
            )
            self.update()
            self._place_panel()  # панель следует за рамкой
        elif self._drag_mode == _DRAG_RESIZE:
            self._selection = geometry.resize_by_handle(
                self._drag_anchor, self._drag_handle, pos, self._screen
            )
            self.update()
            self._place_panel()

    def _chrome_drag_release(self, mode, pos):
        if mode == _DRAG_DRAW and self._selection is not None:
            perf.mark("release_chrome")
            self._fit_to_active_screen()
            perf.mark("fit_screen")
            if settings.panel_mode() == settings.MODE_IMMEDIATE:
                self._show_panel()  # режим «Сразу»: панель после отпускания
        elif self._selection is not None:
            self._fit_to_active_screen()
            self._place_panel()

    def _hover_chrome(self, pos):
        if self._selection is None:
            return False
        pos = self._to_frame(pos)
        handle = geometry.hit_handle(self._selection, pos, HANDLE_HALF + 2)
        if handle is not None:
            self.setCursor(HANDLE_CURSORS[handle])
            return True
        return False

    # --- «Открыть папку»: захват закрывается (З4.2) ---

    def _exit_before_folder(self):
        """Проводник — обычное окно, а оверлей topmost на весь экран: папку
        видно, только если захват закрыт. Поднять чужое окно над topmost
        платформа не даёт (замер протокола: SetWindowPos по окну проводника
        возвращает успех и порядок окон не меняет), поэтому «Открыть папку»
        штатно выходит из захвата — как Enter после сохранения.
        Пин-окно маленькое, папку не перекрывает — там выхода нет (база).
        """
        self._finish()

    # --- клавиатура: режим «по Ctrl» (настройки) ---

    def keyPressEvent(self, event):
        super().keyPressEvent(event)  # Esc по уровням — в базе
        if (event.key() == Qt.Key.Key_Control and not event.isAutoRepeat()
                and settings.panel_mode() == settings.MODE_CTRL
                and self._selection is not None):
            self._show_panel()  # режим «по Ctrl»: панель живёт, пока держишь

    def keyReleaseEvent(self, event):
        if (event.key() == Qt.Key.Key_Control and not event.isAutoRepeat()
                and settings.panel_mode() == settings.MODE_CTRL):
            self._hide_panel()

    # --- панель инструментов у выделения ---

    def _show_panel(self):
        """Показать панель с микроанимацией (ТЗ §3: 150–250 мс, ease-out)."""
        if self._selection is None:
            return
        perf.mark("panel_adjust")
        self._panel.adjustSize()
        self._panel.show()
        self._panel.raise_()
        perf.mark("panel_show")
        self._place_panel()
        self._maybe_show_pin_bubble()
        perf.mark("panel_bubble")
        effect = QGraphicsOpacityEffect(self._panel)
        self._panel.setGraphicsEffect(effect)
        if self._panel_fade is not None:
            self._panel_fade.stop()
        self._panel_fade = QPropertyAnimation(effect, b"opacity", self)
        self._panel_fade.setDuration(_FADE_MS)
        self._panel_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._panel_fade.setStartValue(0.0)
        self._panel_fade.setEndValue(1.0)
        self._panel_fade.start()
        perf.mark("panel_fade_start")

    def _hide_panel(self):
        self._close_popups()
        self._hide_pin_bubble()
        if self._panel_fade is not None:
            self._panel_fade.stop()
        self._panel.hide()

    # --- разовая подсказка у кнопки «Пин» (заметность пина, 24.10) ---

    def mousePressEvent(self, event):
        self._hide_pin_bubble()  # клик в любом месте гасит подсказку
        super().mousePressEvent(event)

    def _hide_pin_bubble(self):
        self._pin_bubble._timer.stop()
        self._pin_bubble.hide()

    def _maybe_show_pin_bubble(self):
        """Пузырь при первом появлении панели после выделения — один раз
        за жизнь приложения; над панелью у кнопки пина, не перекрывая её."""
        if settings.pin_hint_shown():
            return
        settings.mark_pin_hint_shown()
        btn = self._panel.button("pin")
        self._pin_bubble.adjustSize()
        x = self._panel.x() + btn.x() - 150  # сдвиг влево от кнопки (мок)
        x = min(max(6, x), max(6, self.width() - self._pin_bubble.width() - 6))
        y = self._panel.y() - self._pin_bubble.height() - 8
        if y < 6:  # панель у верхнего края — пузырь под ней
            y = self._panel.y() + self._panel.height() + 8
        self._pin_bubble.popup_at((x, y))

    def _place_panel(self):
        """Позиция панели у выделения: флип у нижнего края, кламп по горизонтали.

        Расчёт — в координатах кадра, move() — в локальных: переводим."""
        if self._selection is None or not self._panel.isVisible():
            return
        pos = panel_layout.panel_place(
            self._selection, (self._panel.width(), self._panel.height()), self._screen
        )
        self._panel.move(*self._to_view(pos))
        self._place_toast()  # тост перепривязывается к панели при её перемещении

    # --- отрисовка ---

    def paintEvent(self, event):
        perf.mark("paint_begin")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Кадр и все аннотации рисуем в координатах кадра (как до введения
        # обрезки по монитору); трансформ сдвигает их под текущую геометрию
        # окна — так оверлей можно обрезать до одного монитора (баг 9).
        gx, gy = self.geometry().x(), self.geometry().y()
        ox, oy = self._snapshot_origin.x(), self._snapshot_origin.y()
        painter.translate(ox - gx, oy - gy)
        painter.drawPixmap(0, 0, self._snapshot)
        # затемнение поверх кадра (полупрозрачный фирменный тёмный)
        dim = QColor(theme.NAVY)
        dim.setAlpha(_DIM_ALPHA)
        painter.fillRect(self.rect().translated(gx - ox, gy - oy), dim)
        if self._selection is None:
            painter.end()
            return

        x, y, w, h = self._selection
        sel = QRect(x, y, w, h)
        # просвет: чистый кроп кадра поверх затемнения
        painter.drawPixmap(sel, self._snapshot, sel)
        # области блюра — из кэша мозаики
        mosaicked = self._mosaic_source()
        if mosaicked is not None:
            for obj in self._objects:
                if obj["type"] == "blur":
                    rect = QRect(*obj["rect"])
                    painter.drawImage(rect, mosaicked, rect)
        # аннотации и предпросмотр рисуемого
        self._paint_objects(painter)
        self._paint_in_progress(painter)
        # блюр, который тащат, рисуем превью — без пересчёта мозаики
        if self._drag_blur_idx is not None:
            self._paint_blur_preview(painter, self._objects[self._drag_blur_idx]["rect"])
        # рамка выделения (штрих-пунктир акцент/белый) — в базе
        self._paint_dashed_frame(painter, sel)
        self._paint_handles(painter)
        self._paint_size_badge(painter)
        # полоска-визитка: в оверлее видна та же картинка, что уйдёт в файл
        if settings.watermark_enabled() and watermark.fits(w, h):
            watermark.draw(painter, (x, y, w, h))
        painter.end()
        perf.mark("paint_end")

    def _paint_handles(self, painter):
        painter.setPen(QPen(QColor(theme.NAVY), 1))
        painter.setBrush(QColor(theme.BG))
        for hx, hy in geometry.handle_points(self._selection):
            painter.drawRect(hx - HANDLE_HALF, hy - HANDLE_HALF,
                             HANDLE_HALF * 2, HANDLE_HALF * 2)

    def _paint_size_badge(self, painter):
        x, y, w, h = self._selection
        text = f"{w} × {h}"
        metrics = painter.fontMetrics()
        pad = 6
        bw = metrics.horizontalAdvance(text) + pad * 2
        bh = metrics.height() + pad
        sx, sy, sw, sh = self._screen
        bx = min(max(x, sx), sx + sw - bw)
        above_y = y - bh - 4
        below_y = y + h + 4
        # фикс 16.10: панель перелетела наверх — плашка у нижней грани рамки,
        # иначе она уходит под панель
        oy = self._snapshot_origin.y()
        panel_frame_y = self._panel.y() + self.geometry().y() - oy
        panel_above = self._panel.isVisible() and panel_frame_y < y
        if panel_above or above_y < sy:
            by = below_y if below_y + bh <= sy + sh else max(above_y, sy)
        else:
            by = above_y
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.NAVY))
        painter.drawRoundedRect(bx, by, bw, bh, 3, 3)
        painter.setPen(QColor(theme.BG))
        painter.drawText(bx + pad, by + pad + metrics.ascent() - 1, text)
