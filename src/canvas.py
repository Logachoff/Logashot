"""Базовый холст аннотаций: общая логика оверлея захвата и пин-окна (ТЗ п.3:
«Редактируемость действует и в закреплённом окне: пин = приложение, ничего
не замораживается»).

Координаты объектов и выделения — в пикселях КАДРА. В оверлее они совпадают
с координатами виджета (зум 1:1); в пин-окне есть зум и прокрутка —
пересчёт через хуки _to_frame/_to_view/_tol.

Подкласс обязан:
- заполнить self._snapshot (QPixmap полного кадра) и self._selection;
- создать self._panel и вызвать self._wire_popups();
- переопределить хуки: _finish, _pin_action, _toast_anchor, _to_frame,
  _to_view, _tol, _view_font_size, _press_chrome, _press_inside_idle,
  _press_outer, _chrome_drag_move, _chrome_drag_release, _hover_chrome,
  _inside_cursor, _idle_cursor.

Мышь разбирается шаблоном: ручки выбранного объекта → объект под курсором
(drag двигает ВСЕГДА, решение 15.10) → «хром» подкласса (рамка/края окна)
→ инструмент внутри рамки → пустое место снаружи.
"""

import math
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import QFileDialog, QLineEdit, QWidget

import animations
import annotations as ann
import blur
import geometry
import hotkey
import mailer
import ocr
import panel_layout
import perf
import settings
import storage
import theme
import watermark
from about import show_about
from history import History
from panel import ColorPopup, ScalePopup, SettingsPopup
from toast import Toast

_CLICK_TOL = 12  # сдвиг мыши, до которого драг считается кликом, px.
# Было 4 px: у части мышей клик превращается в микродраг на 5–10 px,
# и клик инструментом «текст/номер» молча гас (баг 25.10: «кружок
# не ставится внутри рамки» — курсор-перекрестье есть, объекта нет).
DASH = 4  # длина штриха рамки, px (чередование акцент/белый)
HANDLE_HALF = 4  # половина стороны ручки рамки выделения, px
OCR_MIN = 8  # регион меньше — мусорный drag, OCR не запускаем (ТЗ DS-7, п.1)

_FADE_MS = animations._FADE_MS  # единый тайминг (animations.py)
# Режимы драга объектов аннотаций (общие). Подклассы добавляют свои
# режимы с 10: у оверлея — рамка выделения, у пин-окна — окно.
(
    _DRAG_NONE,
    _DRAG_OBJ,       # двигаем объект аннотации
    _DRAG_CORNER,    # ресайз объекта за уголок
    _DRAG_ANCHOR,    # тянем опорную точку стрелки
    _DRAG_ARROW,     # рисуем новую стрелку (от хвоста к острию)
    _DRAG_BLUR,      # выделяем область блюра
    _DRAG_CLICK,     # клик инструментом (текст/номер) — ждём отпускания
    _DRAG_MARKER,    # рисуем росчерк маркера (цепочка точек)
    _DRAG_RECT,      # рисуем прямоугольник инструментом (выделение/рамка)
    _DRAG_OCR,       # выделяем регион для распознавания (объект не создаётся)
) = range(10)

# Инструменты разметки панели (подсветка активного на панели, клавиши)
TOOLS = ("select", "arrow", "text", "blur", "marker", "hl", "frame", "ocr")

# Курсор-стрелка над каждой ручкой (нумерация geometry: 0=TL .. 7=L);
# используется и рамкой выделения, и краями пин-окна
HANDLE_CURSORS = (
    Qt.CursorShape.SizeFDiagCursor,  # 0 TL  ↘
    Qt.CursorShape.SizeVerCursor,    # 1 T   ↕
    Qt.CursorShape.SizeBDiagCursor,  # 2 TR  ↗
    Qt.CursorShape.SizeHorCursor,    # 3 R   ↔
    Qt.CursorShape.SizeFDiagCursor,  # 4 BR  ↘
    Qt.CursorShape.SizeVerCursor,    # 5 B   ↕
    Qt.CursorShape.SizeBDiagCursor,  # 6 BL  ↗
    Qt.CursorShape.SizeHorCursor,    # 7 L   ↔
)


def _virtual_geometry():
    """Общий прямоугольник всех мониторов (в Qt6 нет QDesktopWidget.virtualGeometry)."""
    screens = QGuiApplication.screens()
    rect = screens[0].geometry()
    for screen in screens[1:]:
        rect = rect.united(screen.geometry())
    return rect


def _virtual_geometry_tuple():
    vg = _virtual_geometry()
    return vg.x(), vg.y(), vg.width(), vg.height()


class AnnotationCanvas(QWidget):
    """Холст с кадром, рамкой выделения и редактируемыми аннотациями."""

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)  # курсоры над ручками без зажатой кнопки

        self._snapshot = QPixmap()  # полный кадр экрана
        self._snapshot_origin = QPoint(0, 0)  # глоб. координаты верхнего левого угла снимка
        self._screen = (0, 0, 1, 1)  # глобальный прямоугольник активной области (монитор/виртуальный стол)
        self._selection = None  # (x, y, w, h) в пикселях кадра или None
        self._drag_mode = _DRAG_NONE
        self._drag_anchor = None  # точка нажатия / снапшоты для режима

        # Аннотации (ТЗ §3г)
        self._objects = []  # размещённые аннотации (модель — annotations.py)
        self._history = History()  # undo/redo, стек 10
        self._tool = None  # активный инструмент: arrow/text/blur/num или None
        self._selected = None  # индекс выбранного объекта
        self._ann_color = theme.ANN_RED  # цвет новых аннотаций (попап цвета)
        self._draft = None  # предпросмотр рисуемого объекта (стрелка/блюр)
        self._text_editor = None  # (QLineEdit, позиция в кадре, индекс | None)
        self._mosaicked = None  # кэш QImage с применёнными блюрами
        self._blur_dirty = True  # кэш мозаики надо пересчитать
        self._drag_blur_idx = None  # индекс блюра, который сейчас тащат (превью, не пересчёт)

        # Панель и попапы создаёт подкласс, затем вызывает _wire_popups()
        self._panel = None
        self._popups = {}
        self._scale_percent = 100  # пресет масштаба сохраняемого файла
        self._toast = None  # живой тост (окно отдельное, переживает холст)
        self._toast_gen = 0  # поколение тоста: destroyed старого не гасит новый
        # OCR — действие, а не разметка: распознаёт регион в фоне, объект
        # аннотации не создаётся (в файл, буфер-кадр и undo не попадает)
        self._ocr = ocr.OcrWorker()
        self._ocr.finished.connect(self._on_ocr_finished)
        self._ocr.failed.connect(self._on_ocr_failed)

        # Клавиши (ТЗ §3г): QShortcut — работают и при фокусе на кнопках
        # панели/попапов (тот же топ-левел). Пока редактируется текстовая
        # аннотация, все они отключены — буквы и Enter уходят в поле ввода
        # (принцип из Горячие_клавиши_проект.md).
        self._shortcuts = []

        def sc(key, handler):
            self._shortcuts.append(QShortcut(QKeySequence(key), self, activated=handler))

        sc(Qt.Key.Key_Return, self._confirm)
        sc(Qt.Key.Key_Enter, self._confirm)
        sc(QKeySequence.StandardKey.Copy, self._copy_to_clipboard)
        sc("Ctrl+S", self._save_as)
        sc("Ctrl+O", self._open_folder)
        sc("Ctrl+M", self._send_mail)
        sc("Ctrl+Z", self._undo)
        sc("Ctrl+Shift+Z", self._redo)
        sc("Ctrl+Y", self._redo)
        sc(Qt.Key.Key_Delete, self._delete_selected)
        sc(Qt.Key.Key_V, lambda: self._set_tool("select"))
        sc("1", lambda: self._set_tool("arrow"))
        sc("2", lambda: self._set_tool("text"))
        sc("3", lambda: self._set_tool("blur"))
        sc("4", lambda: self._set_tool("num"))
        sc("6", lambda: self._set_tool("marker"))
        sc("7", lambda: self._set_tool("hl"))
        sc("8", lambda: self._set_tool("frame"))
        sc("5", lambda: self._set_tool("ocr"))

    def _wire_popups(self):
        """Попапы масштаба/цвета/настроек — общие у обеих панелей."""
        self._popups = {
            "resize": ScalePopup(self),
            "color": ColorPopup(self),
            "settings": SettingsPopup(self),
        }
        self._popups["resize"].scale_chosen.connect(self._on_scale_chosen)
        self._popups["color"].color_chosen.connect(self._on_color_chosen)
        self._popups["settings"].mode_chosen.connect(self._on_mode_chosen)
        self._popups["settings"].watermark_toggled.connect(self._on_watermark_toggled)
        self._popups["settings"].hotkey_chosen.connect(self._on_hotkey_chosen)
        self._popups["settings"].quiet_hotkey_chosen.connect(self._on_quiet_hotkey_chosen)
        self._popups["settings"].suppress_toggled.connect(self._on_suppress_toggled)
        for popup in self._popups.values():
            popup.hide()
        for widget in (self._panel, *self._popups.values()):
            widget.installEventFilter(self)  # Esc по уровням при фокусе на кнопке

    # --- хуки подкласса (заполняются в оверлее и пин-окне по-разному) ---

    def _to_frame(self, pos_view):
        """Координаты виджета → координаты кадра (в оверлее тождественны)."""
        return pos_view

    def _to_view(self, pos_frame):
        """Координаты кадра → координаты виджета."""
        return pos_frame

    def _tol(self, tol):
        """Допуск хит-теста (px кадра) с учётом зума подкласса."""
        return tol

    def _view_font_size(self, size):
        """Кегль поля ввода в координатах виджета (в пин-окне — с зумом)."""
        return size

    def _inside_cursor(self):
        """Курсор внутри рамки без активного инструмента."""
        return Qt.CursorShape.SizeAllCursor

    def _idle_cursor(self):
        """Курсор в покое (прицел в оверлее, обычная стрелка в окне)."""
        return Qt.CursorShape.CrossCursor

    def _frame_size(self):
        return self._snapshot.width(), self._snapshot.height()

    # Хуки, которые подкласс обязан наполнить поведением
    def _press_chrome(self, pos_view):
        return False

    def _press_inside_idle(self, pos_view):
        return False

    def _press_outer(self, pos_view):
        pass

    def _chrome_drag_move(self, pos_view):
        pass

    def _chrome_drag_release(self, mode, pos_view):
        pass

    def _hover_chrome(self, pos_view):
        return False

    def _exit_before_folder(self):
        """Хук: закрыть своё окно, если оно перекрывает проводник (З4.2)."""

    def _finish(self):
        """Выход из холста: оверлей — cancel(), пин-окно — close."""
        raise NotImplementedError

    def _pin_action(self):
        """Кнопка «Пин» — переключатель (ТЗ п.3)."""
        raise NotImplementedError

    def _toast_anchor(self):
        """Глобальный rect панели для привязки тоста; None — панели нет."""
        raise NotImplementedError

    # --- мышь: шаблон разбора ---

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._commit_text()  # клик по полотну фиксирует вводимый текст
        self._close_popups()  # клик по полотну — попапы закрываются
        pos = (int(event.position().x()), int(event.position().y()))

        # 1. ручки выбранного объекта — точнее всего, проверяем первыми
        if self._press_selected_handles(pos):
            return
        # 2. объект под курсором: drag двигает его ВСЕГДА, даже при активном
        #    инструменте (решение 15.10); новый объект — по пустому месту
        if self._press_object(pos):
            return
        # клик мимо объектов снимает выбор
        if self._selected is not None:
            self._selected = None
            self.update()
        # 3. «хром» подкласса: ручки рамки выделения / края и шапка окна
        if self._press_chrome(pos):
            return
        # 4. внутри рамки: инструмент ставит объект (без инструмента — подкласс)
        if self._press_inside(pos):
            return
        # 5. пустое место снаружи (оверлей: новое выделение)
        self._press_outer(pos)

    def _press_selected_handles(self, pos_view):
        """Ручки выбранного объекта: опорные точки стрелки или уголок."""
        pos = self._to_frame(pos_view)
        if self._selected is None or self._selected >= len(self._objects):
            return False
        obj = self._objects[self._selected]
        tol = self._tol(ann.ANCHOR_HALF + 2)
        if obj["type"] == "arrow":
            anchor = ann.hit_arrow_anchor(obj, pos, tol)
            if anchor is not None:
                self._push_history()
                self._drag_mode = _DRAG_ANCHOR
                self._drag_anchor = (self._selected, anchor)
                return True
        elif ann.hit_corner(obj, pos, tol):
            self._push_history()
            self._drag_mode = _DRAG_CORNER
            self._drag_anchor = (self._selected, deepcopy(obj))
            if obj["type"] == "blur":
                self._drag_blur_idx = self._selected
                self._blur_dirty = True  # пересчитаем без этого блюра
            return True
        return False

    def _press_object(self, pos_view):
        """Объект под курсором — начать его drag (выбор + перемещение)."""
        if self._selection is None:
            return False
        pos = self._to_frame(pos_view)
        idx = ann.topmost_at(self._objects, pos, self._tol(ann.ARROW_HIT_TOL))
        if idx is None:
            return False
        self._selected = idx
        self._drag_mode = _DRAG_OBJ
        # снапшот в историю — на первом реальном сдвиге, не на клике
        self._drag_anchor = (idx, pos, False)
        if self._objects[idx]["type"] == "blur":
            self._drag_blur_idx = idx
            self._blur_dirty = True  # пересчитаем без этого блюра
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.update()
        return True

    def _press_inside(self, pos_view):
        """Клик внутри рамки: активный инструмент ставит объект."""
        if self._selection is None:
            return False
        pos = self._to_frame(pos_view)
        if not geometry.inside(self._selection, pos):
            return False
        if self._tool == "select":
            return True  # «Выбор» ничего не ставит: клик по объекту — выше
        if self._tool == "arrow":
            self._drag_mode = _DRAG_ARROW
            self._drag_anchor = pos
        elif self._tool == "blur":
            self._drag_mode = _DRAG_BLUR
            self._drag_anchor = pos
        elif self._tool == "marker":
            self._drag_mode = _DRAG_MARKER
            self._drag_anchor = [pos]  # цепочка точек росчерка
        elif self._tool in ("hl", "frame"):
            self._drag_mode = _DRAG_RECT
            self._drag_anchor = pos
        elif self._tool == "ocr":
            self._drag_mode = _DRAG_OCR
            self._drag_anchor = pos
        elif self._tool in ("text", "num"):
            self._drag_mode = _DRAG_CLICK
            self._drag_anchor = pos
        else:
            return self._press_inside_idle(pos_view)
        self.update()
        return True

    def mouseMoveEvent(self, event):
        pos = (int(event.position().x()), int(event.position().y()))
        if self._drag_mode == _DRAG_NONE:
            self._update_hover_cursor(pos)
            return
        if self._obj_drag_move(pos):
            return
        self._chrome_drag_move(pos)

    def _obj_drag_move(self, pos_view):
        """Драги объектов аннотаций (общие); True — режим был объектный."""
        pos = self._to_frame(pos_view)
        if self._drag_mode == _DRAG_OBJ:
            idx, start, pushed = self._drag_anchor
            if not pushed:  # первый реальный сдвиг — снапшот для undo
                self._push_history()
                pushed = True
            obj = self._objects[idx]
            dx, dy = pos[0] - start[0], pos[1] - start[1]
            self._move_object(obj, dx, dy)
            self._drag_anchor = (idx, pos, pushed)
            self.update()
        elif self._drag_mode == _DRAG_CORNER:
            idx, original = self._drag_anchor
            self._resize_object(self._objects[idx], original, pos)
            self.update()
        elif self._drag_mode == _DRAG_ANCHOR:
            idx, anchor = self._drag_anchor
            # точки стрелки клампим в кадр — не уводить за край
            fw, fh = self._frame_size()
            cx = min(max(pos[0], 0), fw)
            cy = min(max(pos[1], 0), fh)
            self._objects[idx]["pts"][anchor] = (cx, cy)
            self.update()
        elif self._drag_mode == _DRAG_ARROW:
            self._draft = {
                "type": "arrow",
                "pts": [self._drag_anchor, self._mid(self._drag_anchor, pos), pos],
                "color": self._ann_color,
                "width": 3,
            }
            self.update()
        elif self._drag_mode == _DRAG_BLUR:
            rect = geometry.normalize_rect(self._drag_anchor, pos)
            fw, fh = self._frame_size()
            self._draft = {
                "type": "blur",
                "rect": geometry.clamp_to_screen(rect, (0, 0, fw, fh)),
            }
            self.update()
        elif self._drag_mode == _DRAG_MARKER:
            pts = self._drag_anchor
            lx, ly = pts[-1]
            # точки чаще шага не собираем — иначе список раздувается,
            # а визуально линия от этого не плотнее (круги накладываются)
            if math.hypot(pos[0] - lx, pos[1] - ly) >= ann.MARKER_POINT_STEP:
                pts.append(pos)
                self.update()
        elif self._drag_mode == _DRAG_RECT:
            rect = geometry.normalize_rect(self._drag_anchor, pos)
            fw, fh = self._frame_size()
            self._draft = {
                "type": self._tool,
                "rect": geometry.clamp_to_screen(rect, (0, 0, fw, fh)),
                "color": self._ann_color,  # читает рамка; подсветка игнорит
            }
            self.update()
        elif self._drag_mode == _DRAG_OCR:
            rect = geometry.normalize_rect(self._drag_anchor, pos)
            fw, fh = self._frame_size()
            self._draft = {
                "type": "ocr",
                "rect": geometry.clamp_to_screen(rect, (0, 0, fw, fh)),
            }
            self.update()
        else:
            return False
        return True

    def mouseReleaseEvent(self, event):
        perf.mark("release")  # З4.4: начало интервала «отпустил → панель»
        if event.button() != Qt.MouseButton.LeftButton:
            return
        mode = self._drag_mode
        self._drag_mode = _DRAG_NONE
        pos = (int(event.position().x()), int(event.position().y()))
        self._update_hover_cursor(pos)
        if self._obj_drag_release(mode, pos):
            self._end_blur_drag()
            return
        self._chrome_drag_release(mode, pos)
        self._end_blur_drag()

    def _end_blur_drag(self):
        """Пересчитать мозаику после окончания drag блюра."""
        if self._drag_blur_idx is not None:
            self._drag_blur_idx = None
            self._blur_dirty = True
            self.update()

    def _obj_drag_release(self, mode, pos_view):
        """Отпускание при объектных драгах: фиксация стрелки/блюра/клика."""
        pos = self._to_frame(pos_view)
        if mode == _DRAG_ARROW:
            draft, self._draft = self._draft, None
            if draft is not None:
                tail, _, tip = draft["pts"]
                if math.hypot(tip[0] - tail[0], tip[1] - tail[1]) >= ann.MIN_ARROW:
                    self._push_history()
                    self._objects.append(draft)
            self.update()
        elif mode == _DRAG_BLUR:
            draft, self._draft = self._draft, None
            if draft is not None:
                rect = geometry.apply_min_size(draft["rect"], ann.MIN_RECT)
                if rect[2] >= ann.MIN_RECT and rect[3] >= ann.MIN_RECT:
                    self._push_history()
                    self._objects.append({"type": "blur", "rect": rect})
                    self._blur_dirty = True
            self.update()
        elif mode == _DRAG_MARKER:
            pts, self._drag_anchor = self._drag_anchor, None
            if len(pts) >= ann.MARKER_MIN_POINTS:
                self._push_history()
                self._objects.append({"type": "marker", "pts": pts,
                                      "color": self._ann_color})
            self.update()
        elif mode == _DRAG_RECT:
            draft, self._draft = self._draft, None
            if draft is not None:
                # минимум — фильтр «меньше — отмена», а не подъём размера:
                # клик с лёгким сдвигом объект не ставит (спека v0.2)
                min_size = ann.HL_MIN if self._tool == "hl" else ann.FRAME_MIN
                rect = draft["rect"]
                if rect[2] >= min_size and rect[3] >= min_size:
                    self._push_history()
                    obj = {"type": self._tool, "rect": rect}
                    if self._tool == "frame":  # подсветка — фиксированно жёлтая
                        obj["color"] = self._ann_color
                    self._objects.append(obj)
            self.update()
        elif mode == _DRAG_OCR:
            draft, self._draft = self._draft, None
            self.update()
            # меньше OCR_MIN — мусорный drag: тихая отмена, без тоста (ТЗ)
            if draft is not None:
                rect = draft["rect"]
                if rect[2] >= OCR_MIN and rect[3] >= OCR_MIN:
                    self._recognize_region(rect)
        elif mode == _DRAG_CLICK:
            dist = math.hypot(pos[0] - self._drag_anchor[0],
                              pos[1] - self._drag_anchor[1])
            if dist <= self._tol(_CLICK_TOL):
                if self._tool == "text":
                    self._open_text_editor(self._drag_anchor)
                elif self._tool == "num":
                    self._push_history()
                    self._objects.append({
                        "type": "num",
                        "pos": self._drag_anchor,
                        "value": ann.next_number(self._objects),
                        "color": self._ann_color,
                        "radius": ann.NUM_RADIUS,
                    })
                    self.update()
        else:
            return False
        return True

    def _mid(self, a, b):
        return ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)

    def mouseDoubleClickEvent(self, event):
        """Двойной клик по текстовой аннотации — правка её текста
        (решение владельца 16.10: опечатка не должна начинаться сначала)."""
        if event.button() != Qt.MouseButton.LeftButton or self._selection is None:
            return
        pos = self._to_frame((int(event.position().x()), int(event.position().y())))
        idx = ann.topmost_at(self._objects, pos, self._tol(ann.ARROW_HIT_TOL))
        if idx is None or self._objects[idx]["type"] != "text":
            return
        # даблклик пришёл после двух mousePress — гасим возможный драг
        self._drag_mode = _DRAG_NONE
        self._draft = None
        self._selected = idx
        self._open_text_editor(self._objects[idx]["pos"], edit_index=idx)
        self.update()

    def _update_hover_cursor(self, pos_view):
        """Курсор под позицией мыши: ручки объектов, объекты, хром, инструмент."""
        pos = self._to_frame(pos_view)
        tol = self._tol(ann.ANCHOR_HALF + 2)
        if self._selected is not None and self._selected < len(self._objects):
            obj = self._objects[self._selected]
            if obj["type"] == "arrow" and ann.hit_arrow_anchor(obj, pos, tol) is not None:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return
            if obj["type"] != "arrow" and ann.hit_corner(obj, pos, tol):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                return
        if self._selection is not None:
            if self._tool == "select":
                # «Выбор» — обычный курсор-стрелка, не прицел (фича v0.2)
                self.setCursor(Qt.CursorShape.ArrowCursor)
                return
            if ann.topmost_at(self._objects, pos, self._tol(ann.ARROW_HIT_TOL)) is not None:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return
            if self._hover_chrome(pos_view):
                return
            if geometry.inside(self._selection, pos):
                if self._tool == "text":
                    self.setCursor(Qt.CursorShape.IBeamCursor)
                elif self._tool is not None:
                    self.setCursor(Qt.CursorShape.CrossCursor)
                else:
                    self.setCursor(self._inside_cursor())
                return
        elif self._hover_chrome(pos_view):
            return
        self.setCursor(self._idle_cursor())

    # --- объекты аннотаций ---

    def _push_history(self):
        """Снапшот списка объектов перед правкой (мементо для undo)."""
        self._history.push(deepcopy(self._objects))

    def _move_object(self, obj, dx, dy):
        """Сдвиг объекта любого типа на дельту."""
        if obj["type"] in ("arrow", "marker"):
            obj["pts"] = [(px + dx, py + dy) for px, py in obj["pts"]]
        elif obj["type"] == "num":
            obj["pos"] = (obj["pos"][0] + dx, obj["pos"][1] + dy)
        else:  # text/blur/hl/frame — у них есть rect; у текста ещё и pos
            x, y, w, h = obj["rect"]
            obj["rect"] = (x + dx, y + dy, w, h)
            if obj["type"] == "text":
                obj["pos"] = (obj["pos"][0] + dx, obj["pos"][1] + dy)
        if obj["type"] == "blur" and self._drag_blur_idx is None:
            self._blur_dirty = True

    def _resize_object(self, obj, original, pos):
        """Ресайз за правый нижний уголок (ТЗ §3г): блюр/выделение/рамка —
        рамка, текст — размер шрифта, номер — размер бейджа. Маркер не
        ресайзится — только перетаскивание (спека v0.2)."""
        if obj["type"] == "blur":
            obj["rect"] = ann.resize_corner(original["rect"], pos)
            if self._drag_blur_idx is None:
                self._blur_dirty = True
        elif obj["type"] in ("hl", "frame"):
            min_size = ann.HL_MIN if obj["type"] == "hl" else ann.FRAME_MIN
            obj["rect"] = ann.resize_corner(original["rect"], pos,
                                            min_size=min_size)
        elif obj["type"] == "text":
            _, oy, _, oh = original["rect"]
            # высота рамки пропорциональна кеглю — от неё и считаем
            scale = max(8, pos[1] - oy) / max(1, oh)
            obj["size"] = max(8, min(160, round(original["size"] * scale)))
            self._measure_text(obj)
        elif obj["type"] == "num":
            cx, cy = original["pos"]
            obj["radius"] = max(10, min(60, round(math.hypot(pos[0] - cx, pos[1] - cy))))

    def _measure_text(self, obj):
        """Обновить кэш рамки текста по метрикам шрифта (для хит-теста)."""
        font = QFont(self.font())
        font.setPixelSize(obj["size"])
        metrics = QFontMetrics(font)
        obj["rect"] = (
            obj["pos"][0], obj["pos"][1],
            metrics.horizontalAdvance(obj["text"]), metrics.height(),
        )

    def _set_tool(self, name):
        """Активировать инструмент; повторный выбор снимает активность.

        Снимаем выделение объекта при смене инструмента — иначе ручки
        выделенного объекта и рамка начинают конфликтовать (баг 8 dogfooding).
        """
        if name is not None and self._tool == name:
            name = None
        self._tool = name
        self._selected = None
        if self._panel is not None:
            self._panel.set_active_tool(name)
        self.setCursor(self._idle_cursor())
        self.update()

    def _undo(self):
        state = self._history.undo(deepcopy(self._objects))
        if state is None:
            return  # пустой стек — клик по ↩ бездействует, как Ctrl+Z (ТЗ §3г)
        self._objects = state
        self._selected = None
        self._blur_dirty = True
        self.update()

    def _redo(self):
        state = self._history.redo(deepcopy(self._objects))
        if state is None:
            return
        self._objects = state
        self._selected = None
        self._blur_dirty = True
        self.update()

    def _delete_selected(self):
        """Del — удалить выбранную аннотацию (ТЗ §3г)."""
        if self._selected is None or self._selected >= len(self._objects):
            return
        self._push_history()
        self._objects.pop(self._selected)
        self._selected = None
        self._blur_dirty = True
        self.update()

    # --- ввод текста ---

    def _open_text_editor(self, pos, edit_index=None):
        """Поле ввода текста: новая аннотация в точке клика (инструмент
        «Текст») или правка существующей (двойной клик по ней, edit_index).

        pos — позиция в координатах кадра; поле позиционируется через
        _to_view (в пин-окне — с зумом и прокруткой).
        """
        self._commit_text()
        if edit_index is not None:
            obj = self._objects[edit_index]
            size, color, text = obj["size"], obj["color"], obj["text"]
        else:
            size, color, text = ann.TEXT_SIZE, self._ann_color, ""
        editor = QLineEdit(self)
        editor.setPlaceholderText("Текст аннотации")
        font = QFont(self.font())
        font.setPixelSize(self._view_font_size(size))
        editor.setFont(font)
        editor.setStyleSheet(
            f"QLineEdit {{ background: {theme.BG}; color: {color};"
            f" border: 1px solid {theme.ACCENT}; border-radius: 4px; padding: 2px 6px; }}"
        )
        editor.setText(text)
        editor.selectAll()  # правка: весь текст выделен — легко перепечатать
        # высота поля — по кеглю объекта (после ресайза поле не «уменьшается»),
        # ширина — по содержимому; кламп в пределы виджета
        view_size = self._view_font_size(size)
        height = max(30, view_size + 14)
        width = min(max(120, editor.fontMetrics().horizontalAdvance(text) + 40),
                    self.width() - 8)
        vx, vy = self._to_view(pos)
        ex = min(max(0, vx), max(0, self.width() - width - 4))
        ey = min(max(0, vy), max(0, self.height() - height - 4))
        editor.setGeometry(ex, ey, width, height)
        editor.returnPressed.connect(self._commit_text)
        editor.textChanged.connect(lambda: self._fit_editor(editor))
        editor.installEventFilter(self)
        editor.show()
        editor.setFocus()
        # позиция объекта — в координатах кадра (от клампнутого поля)
        self._text_editor = (editor, self._to_frame((ex, ey)), edit_index)
        self._set_shortcuts_enabled(False)

    def _fit_editor(self, editor):
        """Автораздвижка поля по мере ввода (правка владельца 16.10):
        ширина следует за текстом, у правого края поле сдвигается влево."""
        width = min(max(120, editor.fontMetrics().horizontalAdvance(editor.text()) + 40),
                    self.width() - 8)
        if width == editor.width():
            return
        ex = min(editor.x(), max(0, self.width() - width - 4))
        editor.setGeometry(max(0, ex), editor.y(), width, editor.height())

    def _commit_text(self):
        """Enter в поле / клик по полотну — текст становится аннотацией
        (или правка существующей сохраняется; всё undoable)."""
        if self._text_editor is None:
            return
        editor, pos, edit_index = self._text_editor
        text = editor.text().strip()
        self._close_editor()
        if edit_index is not None:
            if edit_index >= len(self._objects):
                return  # объект уже удалён (теоретический случай) — не падаем
            obj = self._objects[edit_index]
            self._push_history()
            if not text:
                # очистил текст = удалил аннотацию (отменяемо через Ctrl+Z)
                self._objects.pop(edit_index)
                if self._selected is not None and self._selected >= edit_index:
                    self._selected = None if self._selected == edit_index else self._selected - 1
            elif text != obj["text"]:
                obj["text"] = text
                self._measure_text(obj)
            self.update()
            return
        if not text:
            return  # пустая подпись не ставится
        self._push_history()
        obj = {
            "type": "text", "pos": pos, "text": text,
            "color": self._ann_color, "size": ann.TEXT_SIZE,
            "rect": (pos[0], pos[1], 1, 1),
        }
        self._measure_text(obj)
        self._objects.append(obj)
        self.update()

    def _discard_text(self):
        """Esc в поле / новый захват — ввод отменяется без объекта."""
        if self._text_editor is None:
            return
        self._close_editor()

    def _close_editor(self):
        editor, _, _ = self._text_editor
        self._text_editor = None
        editor.removeEventFilter(self)
        editor.hide()
        editor.deleteLater()
        self._set_shortcuts_enabled(True)

    def _set_shortcuts_enabled(self, enabled):
        for shortcut in self._shortcuts:
            shortcut.setEnabled(enabled)

    # --- клавиатура ---

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._escape()

    def eventFilter(self, obj, event):
        # Esc по уровням, даже когда фокус на кнопке панели/попапа/поле ввода
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._escape()
            return True
        return super().eventFilter(obj, event)

    def _escape(self):
        """Esc по уровням (ТЗ §3г): попап → ввод текста → выбор/инструмент →
        выход из холста."""
        if self._close_popups():
            return
        if self._text_editor is not None:
            self._discard_text()
            return
        if self._selected is not None or self._tool is not None:
            self._selected = None
            self._set_tool(None)
            self.update()
            return
        self._finish()

    # --- панель инструментов и попапы ---

    def _toggle_popup(self, name):
        """Открыть/закрыть попап у кнопки; другие попапы закрываются."""
        target = self._popups[name]
        for key, popup in self._popups.items():
            if key != name:
                popup.hide()
        if target.isVisible():
            target.hide()
            return
        if name == "settings":
            # синхронизируем тумблеры с сохранёнными значениями
            target.set_mode(settings.panel_mode())
            target.set_watermark(settings.watermark_enabled())
            target.set_hotkey_label(hotkey.combo_label(settings.capture_hotkey()))
            target.set_quiet_hotkey_label(hotkey.combo_label(settings.quiet_hotkey()))
            target.set_suppress_prtscr(settings.suppress_prtscr())
        btn = self._panel.button(name)
        top_left = btn.mapTo(self, QPoint(0, 0))
        target.adjustSize()
        bounds = (0, 0, self.width(), self.height())
        pos = panel_layout.popup_place(
            (top_left.x(), top_left.y(), btn.width(), btn.height()),
            (target.width(), target.height()),
            bounds,
        )
        target.move(*pos)
        target.show()
        target.raise_()

    def _close_popups(self):
        """Закрыть открытые попапы; True — если что-то закрыли (для Esc по уровням)."""
        closed = False
        for popup in self._popups.values():
            if popup.isVisible():
                popup.hide()
                closed = True
        return closed

    def _on_panel_action(self, name):
        """Кнопки панели: попапы, инструменты, действия золотого пути."""
        if self._text_editor is not None:
            self._commit_text()  # действие по кнопке фиксирует вводимый текст
        if name in ("resize", "color", "settings"):
            # кнопки-меню: своё меню переключают, чужие закрывают
            self._toggle_popup(name)
            return
        # любое другое действие панели скрывает открытые меню (баг-репорт
        # владельца 16.10: попап масштаба оставался поверх диалога сохранения)
        self._close_popups()
        if name in ("select", "arrow", "text", "blur", "num",
                    "marker", "hl", "frame", "ocr"):
            self._set_tool(name)
        elif name == "undo":
            self._undo()
        elif name == "copy":
            self._copy_to_clipboard()
        elif name == "save":
            self._save_as()
        elif name == "folder":
            self._open_folder()
        elif name == "mail":
            self._send_mail()
        elif name == "pin":
            self._pin_action()
        elif name == "brand":
            # монограмма в конце панели — «О программе», как в меню трея
            # (З3.2: обе панели, панель захвата и панель пин-окна)
            show_about()
        elif name == "cancel":
            self._finish()

    # --- OCR: действие, а не разметка (ТЗ DS-7, часть 1) ---

    def _recognize_region(self, rect):
        """Распознать регион кадра: текст → в буфер, тост с числом символов.

        Берётся чистый снапшот (аннотации не мешают), распознавание — в фоне
        (ocr.OcrWorker). Объект-аннотация не создаётся: в файл, буфер-кадр
        и undo-стек OCR не попадает, инструмент остаётся активным.
        """
        self._ocr.start(self._snapshot.toImage().copy(QRect(*rect)))

    def _on_ocr_finished(self, text):
        """Результат распознавания (GUI-поток): буфер + тост по гайду тона."""
        if text:
            QGuiApplication.clipboard().setText(text)
        self._show_toast(ocr.toast_text(text))

    def _on_ocr_failed(self, reason):
        """Движок недоступен: понятный тост, приложение продолжает работу."""
        self._show_toast(f"OCR недоступен: {reason}")

    def _on_scale_chosen(self, value):
        self._scale_percent = value
        self._popups["resize"].set_scale(value)
        self._panel.button("resize").set_badge(f"{value}%")
        self._popups["resize"].hide()

    def _on_color_chosen(self, hex_color):
        self._ann_color = hex_color  # новые объекты — этим цветом
        self._popups["color"].set_color(hex_color)
        self._panel.button("color").set_fill_color(hex_color)
        self._popups["color"].hide()
        # выбранному объекту цвет меняем тоже (правка undoable, ТЗ §3г)
        if self._selected is not None and self._selected < len(self._objects):
            obj = self._objects[self._selected]
            if ann.has_color(obj) and obj["color"] != hex_color:
                self._push_history()
                obj["color"] = hex_color
                self.update()

    def _on_mode_chosen(self, mode):
        settings.set_panel_mode(mode)
        self._popups["settings"].set_mode(mode)

    def _on_watermark_toggled(self, enabled):
        settings.set_watermark_enabled(enabled)
        self._show_toast("Водяной знак включён" if enabled else "Водяной знак выключен")
        self.update()

    def _on_hotkey_chosen(self, combo):
        """Новое сочетание захвата: сохраняем и пересоздаём хук сразу,
        без перезапуска (фича v0.2). Конфликт с чужим перехватчиком
        надёжно не проверяется — предупреждаем в тосте (решение 24.10)."""
        settings.set_capture_hotkey(combo)
        hotkey.get_listener().reload()
        label = hotkey.combo_label(combo)
        self._show_toast(
            f"Горячая клавиша: {label}. Если не срабатывает — проверь "
            "конфликт с другими программами")

    def _on_quiet_hotkey_chosen(self, combo):
        """Новое сочетание тихого захвата: сохраняем и пересоздаём хуки
        сразу (DS-9). Тост не показываем — как в окне из трея."""
        settings.set_quiet_hotkey(combo)
        hotkey.get_listener().reload()

    def _on_suppress_toggled(self, enabled):
        """Тумблер перехвата PrtScr: применяется сразу, без перезапуска."""
        settings.set_suppress_prtscr(enabled)
        hotkey.get_listener().reload()
        if enabled:
            self._show_toast("PrtScr перехвачен — стандартный снимок Windows "
                             "открываться не будет")
        else:
            self._show_toast("PrtScr у Windows — стандартный снимок остаётся "
                             "за системой")

    # --- золотой путь: кадр, файл, буфер, папка, почта ---

    def _selection_pixmap(self):
        """Чистый кадр выделения из снимка рабочего стола."""
        return self._snapshot.copy(QRect(*self._selection))

    def _render_final(self):
        """Итоговый кадр: выделение + блюр + аннотации + полоска-визитка.

        Именно он уходит в файл и буфер (ТЗ §3г, спецификация визитки);
        в пин-окне правило то же: пин — просмотр, в файл уходит рамка (ТЗ п.3).
        """
        pm = self._selection_pixmap()
        sx, sy, sw, sh = self._selection
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        mosaicked = self._mosaic_source()
        if mosaicked is not None:
            sel = QRect(sx, sy, sw, sh)
            for obj in self._objects:
                if obj["type"] == "blur":
                    source = QRect(*obj["rect"]).intersected(sel)
                    painter.drawImage(source.translated(-sx, -sy), mosaicked, source)
        self._paint_objects(painter, offset=(-sx, -sy), export=True)
        if settings.watermark_enabled() and watermark.fits(sw, sh):
            watermark.draw(painter, (0, 0, sw, sh))
        painter.end()
        return pm

    def _scaled_for_file(self, pm):
        """Кадр с применённым пресетом масштаба (100/75/50) — для файла."""
        w, h = storage.scale_size((pm.width(), pm.height()), self._scale_percent)
        if (w, h) == (pm.width(), pm.height()):
            return pm
        return pm.scaled(
            w, h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _save_file(self, pm):
        """Записать кадр по маске в Рисунки/LogaShot; папку создать при надобности."""
        folder = storage.shot_dir(Path.home())
        folder.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        counter = storage.next_counter((p.name for p in folder.iterdir()), now)
        path = folder / storage.file_name(now, counter)
        if not pm.save(str(path), "PNG"):
            raise OSError(f"QPixmap.save вернул False: {path}")
        return path

    def _confirm(self):
        """Enter: файл по маске + кадр в буфер + тост «готово» → выход (ТЗ §3г)."""
        if self._selection is None or self._text_editor is not None:
            return
        self._close_popups()  # действие с клавиатуры тоже скрывает меню
        pm = self._render_final()
        QGuiApplication.clipboard().setPixmap(pm)
        try:
            self._save_file(self._scaled_for_file(pm))
            text = "Сохранено в Рисунки · Скопировано"
        except OSError:
            # ошибка = факт + выход (гайд тона); кадр уже в буфере, не теряется
            text = "Файл не сохранился, но кадр в буфере"
        self._show_toast(text)
        self._finish()

    def _copy_to_clipboard(self):
        """Ctrl+C / кнопка «копировать»: кадр в буфер → выход из режима захвата.

        Решение владельца 16.10: после копирования оверлей закрывается,
        как и при Enter (сценарий «снял → отправил» без лишних шагов).
        """
        if self._selection is None or self._text_editor is not None:
            return
        self._close_popups()  # действие с клавиатуры тоже скрывает меню
        QGuiApplication.clipboard().setPixmap(self._render_final())
        self._show_toast("Скопировано в буфер")
        self._finish()

    def _save_as(self):
        """Ctrl+S / кнопка «сохранить»: диалог сохранения, после записи —
        выход из захвата и открытие папки со скрином (решение владельца
        23.10/24.10; Enter — автосохранение — остаётся «тихим», без папки)."""
        if self._selection is None or self._text_editor is not None:
            return
        self._close_popups()  # меню не висит поверх диалога сохранения
        folder = storage.shot_dir(Path.home())
        folder.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        counter = storage.next_counter((p.name for p in folder.iterdir()), now)
        default = folder / storage.file_name(now, counter)
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить скриншот", str(default), "PNG (*.png)"
        )
        if not path:
            return  # отменили — остаёмся в режиме захвата
        saved = Path(path)
        if not self._scaled_for_file(self._render_final()).save(path, "PNG"):
            self._show_toast("Файл не сохранился — проверьте доступ к папке")
            return
        try:
            storage.open_shots_folder(saved.parent)
            self._show_toast("Скриншот сохранён — открываю папку")
        except OSError:
            self._show_toast(f"Сохранён в {saved.parent}, но папку не открыл")
        self._finish()

    def _open_folder(self):
        """Ctrl+O / кнопка «папка»: открыть папку сохранения в проводнике."""
        self._close_popups()  # действие с клавиатуры тоже скрывает меню
        folder = storage.shot_dir(Path.home())
        try:
            storage.open_shots_folder(folder)
        except OSError as exc:
            # ошибка = факт + выход; захват не трогаем — он ещё нужен
            self._show_toast(f"Не удалось открыть папку — {exc}")
            return
        self._show_toast("Открываю папку со скриншотами")
        # перекрывающее окно закрывается: иначе папка окажется под ним (З4.2)
        self._exit_before_folder()

    def _send_mail(self):
        """Ctrl+M / кнопка «В почту»: письмо с вложением кадра (ТЗ §3г).

        Кадр пишется во временную папку по той же маске имён. Почтового
        клиента нет — кадр уходит в буфер, тост объясняет (гайд тона).
        """
        if self._selection is None or self._text_editor is not None:
            return
        self._close_popups()  # действие с клавиатуры тоже скрывает меню
        pm = self._scaled_for_file(self._render_final())
        temp_dir = Path(tempfile.gettempdir()) / "LogaShot"
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            now = datetime.now()
            counter = storage.next_counter((p.name for p in temp_dir.iterdir()), now)
            path = temp_dir / storage.file_name(now, counter)
            if not pm.save(str(path), "PNG"):
                raise OSError(f"QPixmap.save вернул False: {path}")
        except OSError:
            self._show_toast("Файл не сохранился — проверьте доступ к диску")
            return
        try:
            mailer.send_mail(path)
        except mailer.MailUnavailableError:
            # выход из ситуации — кадр в буфере (гайд тона, строка про Outlook)
            QGuiApplication.clipboard().setPixmap(self._render_final())
            self._show_toast("Не нашли почтовый клиент — кадр уже в буфере")
            return
        self._show_toast("Письмо открыто в почте")
        self._finish()

    def _show_toast(self, text, action_text=None, on_action=None):
        """Показать тост у панели; прежний (если висит) заменяется новым."""
        if self._toast is not None:
            self._toast.close()  # destroyed старого придёт позже — ген ниже его отсечёт
            self._toast = None
        toast = Toast(text, action_text)
        if on_action is not None:
            toast.action_clicked.connect(on_action)
        toast.adjustSize()
        self._toast_gen += 1
        gen = self._toast_gen
        toast.destroyed.connect(lambda: self._forget_toast(gen))
        self._toast = toast
        self._place_toast()
        toast.show()
        toast.raise_()

    def _forget_toast(self, gen):
        # тост удалился: забываем его, только если он ещё текущий
        if self._toast_gen == gen:
            self._toast = None

    def _place_toast(self):
        """Тост следует за панелью и не перекрывает её (ТЗ §3г).

        Тост — отдельное окно, поэтому позиция считается в глобальных
        координатах (холст может начинаться не в (0,0) при двух мониторах).
        """
        if self._toast is None:
            return
        anchor = self._toast_anchor()
        if anchor is None:
            return
        pos = panel_layout.toast_place(
            anchor, (self._toast.width(), self._toast.height()),
            _virtual_geometry_tuple(),
        )
        self._toast.move(*pos)

    # --- мозаика блюра ---

    def _mosaic_source(self):
        """QImage снимка с применёнными блюрами; None, если блюров нет.

        Кэш пересчитывается только когда блюры менялись (_blur_dirty) —
        перетаскивание стрелок и текста мозаику не пересчитывает.
        Блюр, который сейчас тащат, исключается из кэша и рисуется
        отдельным превью — так drag не фризит UI (баг 5 dogfooding).
        """
        rects = [
            o["rect"] for i, o in enumerate(self._objects)
            if o["type"] == "blur" and i != self._drag_blur_idx
        ]
        if not rects:
            return None
        if self._blur_dirty or self._mosaicked is None:
            img = self._snapshot.toImage().convertToFormat(QImage.Format.Format_RGB32)
            for rect in rects:
                blur.mosaic_image(img, rect, blur.block_for(rect[2], rect[3]))
            self._mosaicked = img
            self._blur_dirty = False
        return self._mosaicked

    # --- отрисовка аннотаций (вызывается из paintEvent подкласса) ---

    def _paint_objects(self, painter, offset=(0, 0), export=False):
        """Аннотации поверх кадра; блюр рисуется отдельно (кэш мозаики).

        Рисует в КООРДИНАТАХ КАДРА — зум/сдвиг задаёт подкласс трансформом
        painter'а до вызова. offset — сдвиг для экспорта в кропнутый кадр.
        export=True — без подсветки выбранного (в файл не уходит).
        """
        ox, oy = offset
        for i, obj in enumerate(self._objects):
            kind = obj["type"]
            if kind == "arrow":
                self._paint_arrow(painter, obj, ox, oy)
            elif kind == "text":
                self._paint_text(painter, obj, ox, oy)
            elif kind == "num":
                self._paint_num(painter, obj, ox, oy)
            elif kind == "marker":
                self._paint_marker(painter, obj, ox, oy)
            elif kind == "hl":
                self._paint_hl(painter, obj, ox, oy)
            elif kind == "frame":
                self._paint_frame(painter, obj, ox, oy)
            if not export and i == self._selected:
                self._paint_selection_chrome(painter, obj, ox, oy)

    def _paint_selection_chrome(self, painter, obj, ox=0, oy=0):
        """Ручки выбранного объекта: 3 опорные точки стрелки или уголок."""
        painter.setPen(QPen(QColor(theme.NAVY), 1))
        painter.setBrush(QColor(theme.BG))
        if obj["type"] == "arrow":
            points = obj["pts"]
        else:
            points = [ann.corner_point(obj)]
        half = ann.ANCHOR_HALF
        for px, py in points:
            painter.drawRect(px + ox - half, py + oy - half, half * 2, half * 2)

    def _paint_arrow(self, painter, obj, ox=0, oy=0):
        pts = [(px + ox, py + oy) for px, py in obj["pts"]]
        pen = QPen(QColor(obj["color"]), obj["width"])
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        tail, bend, tip = pts
        dx, dy = tip[0] - bend[0], tip[1] - bend[1]
        len2 = math.hypot(dx, dy)
        len1 = math.hypot(bend[0] - tail[0], bend[1] - tail[1])
        if len1 < 0.5 or len2 < 0.5:  # вырожденная точка — рисуем как есть
            painter.drawPolyline([QPointF(*p) for p in pts])
            return
        # стрелка — квадратичная кривая Безье (правка владельца 16.10, вид —
        # как в прототипе): точка сгиба — управляющая, изгиб плавный целиком
        path = QPainterPath(QPointF(*tail))
        path.quadTo(QPointF(*bend), QPointF(*tip))
        painter.drawPath(path)
        # наконечник: две линии под 150° от касательной в острие — для
        # квадратичной кривой это направление «сгиб → острие»
        head = max(10.0, obj["width"] * 4)
        base = math.atan2(dy, dx)
        for sign in (1, -1):
            angle = base + sign * math.radians(150)
            painter.drawLine(
                QPointF(*tip),
                QPointF(tip[0] + head * math.cos(angle), tip[1] + head * math.sin(angle)),
            )

    def _paint_text(self, painter, obj, ox=0, oy=0):
        painter.save()  # шрифт объекта не должен течь наружу (баг: росла
        font = QFont(self.font())  # плашка размеров после смены кегля)
        font.setPixelSize(obj["size"])
        painter.setFont(font)
        painter.setPen(QPen(QColor(obj["color"])))
        x, y = obj["pos"]
        painter.drawText(x + ox, y + oy + painter.fontMetrics().ascent(), obj["text"])
        painter.restore()

    def _paint_marker(self, painter, obj, ox=0, oy=0):
        """Маркер (спека v0.2, мок v2.13): линия 3,5 px цвета аннотаций
        сквозь все точки + кружок радиуса 1,75 px на каждой — визуально
        сплошной росчерк, как карандаш в Paint."""
        pts = [(px + ox, py + oy) for px, py in obj["pts"]]
        if len(pts) < 2:
            return
        pen = QPen(QColor(obj["color"]), ann.MARKER_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline([QPointF(*p) for p in pts])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(obj["color"]))
        r = ann.MARKER_DOT_RADIUS
        for px, py in pts:
            painter.drawEllipse(QPointF(px, py), r, r)

    def _paint_hl(self, painter, obj, ox=0, oy=0):
        """Выделение области (спека v0.2): жёлтая полупрозрачная заливка
        + внутренняя обводка 1,5 px; цвет фиксированный, не аннотаций."""
        fill = QColor(*ann.HL_FILL)
        border = QColor(*ann.HL_BORDER)
        rect = QRect(*obj["rect"]).translated(ox, oy)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, ann.HL_RADIUS, ann.HL_RADIUS)
        pen = QPen(border, 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1),
                                ann.HL_RADIUS, ann.HL_RADIUS)

    def _paint_frame(self, painter, obj, ox=0, oy=0):
        """Рамка (спека v0.2): обводка 3 px цвета аннотаций, без заливки."""
        pen = QPen(QColor(obj["color"]), ann.FRAME_BORDER_W)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRect(*obj["rect"]).translated(ox, oy)
        painter.drawRoundedRect(rect, ann.FRAME_RADIUS, ann.FRAME_RADIUS)

    def _paint_num(self, painter, obj, ox=0, oy=0):
        painter.save()
        cx, cy = obj["pos"][0] + ox, obj["pos"][1] + oy
        r = obj["radius"]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(obj["color"]))
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        font = QFont(self.font())
        font.setPixelSize(max(9, round(r * 1.1)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(theme.BG)))
        painter.drawText(cx - r, cy - r, r * 2, r * 2,
                         Qt.AlignmentFlag.AlignCenter, str(obj["value"]))
        painter.restore()

    def _paint_draft(self, painter):
        """Предпросмотр рисуемого объекта: стрелка/маркер — как готовые,
        блюр — рамка-превью, выделение/рамка — своим стилем, OCR — пунктиром
        выделения (объекта не будет: регион уходит в распознавание)."""
        kind = self._draft["type"]
        if kind == "arrow":
            self._paint_arrow(painter, self._draft)
        elif kind == "marker":
            self._paint_marker(painter, self._draft)
        elif kind == "hl":
            self._paint_hl(painter, self._draft)
        elif kind == "frame":
            self._paint_frame(painter, self._draft)
        elif kind == "ocr":
            self._paint_dashed_frame(painter, QRect(*self._draft["rect"]))
        else:
            self._paint_blur_preview(painter, self._draft["rect"])

    def _paint_in_progress(self, painter):
        """Всё незавершённое рисование: росчерк маркера следует за курсором
        (как карандаш в Paint), draft-объект — своим превью."""
        if self._drag_mode == _DRAG_MARKER and self._drag_anchor:
            self._paint_marker(painter, {
                "type": "marker", "pts": self._drag_anchor,
                "color": self._ann_color,
            })
        if self._draft is not None:
            self._paint_draft(painter)

    def _paint_blur_preview(self, painter, rect):
        """Превью блюра: полупрозрачная рамка со штриховой границей."""
        fill = QColor(theme.NAVY)
        fill.setAlpha(60)
        painter.setPen(QPen(QColor(theme.ACCENT), 1, Qt.PenStyle.DashLine))
        painter.setBrush(fill)
        painter.drawRect(QRect(*rect))

    def _paint_dashed_frame(self, painter, rect):
        """Рамка выделения: штрих-пунктир акцент/белый (два пера со сдвигом).

        Штрих выровнен по целым физическим пикселям (З4.3): толщина — ровно
        1 физ. px, координаты — по центрам пикселей. Иначе на дробном dpr
        (105/125/150%) линия в 1 логический px распыляется сглаживанием, и
        картина зависит от субпиксельной фазы ребра: левое «худеет», верх
        чёткий, после пина туда-обратно — наоборот. Стиль (пунктир, шаг 4 px,
        акцент/белый) не меняется: шаг задаётся в единицах толщины пера,
        поэтому остаётся 4 логических px на любом масштабе.
        """
        transform = painter.deviceTransform()
        scale = transform.m11()  # device-пикселей на логический (dpr × зум пин-окна)
        x0, y0, x1, y1, width = geometry.stroke_frame(
            (rect.x(), rect.y(), rect.width(), rect.height()),
            scale, (transform.dx(), transform.dy()),
        )
        # drawRect заливает текущей кистью — после аннотаций она цветная,
        # сбрасываем, иначе всё выделение заливается цветом последнего объекта
        painter.setBrush(Qt.BrushStyle.NoBrush)
        dash = DASH * scale  # dashPattern и offset — в единицах толщины пера
        edges = ((x0, y0, x1, y0), (x1, y0, x1, y1),
                 (x1, y1, x0, y1), (x0, y1, x0, y0))
        for color, offset in ((theme.ACCENT, 0.0), (theme.BG, dash)):
            pen = QPen(QColor(color), width)
            pen.setDashPattern([dash, dash])
            pen.setDashOffset(offset)
            painter.setPen(pen)
            for x_start, y_start, x_end, y_end in edges:
                painter.drawLine(QPointF(x_start, y_start), QPointF(x_end, y_end))
