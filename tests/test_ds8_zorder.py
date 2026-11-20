"""P1: окна поверх захвата (DS-8, З4.2).

Репорт тестера: «предупреждалки и открытие папки со скриншотами во время
активного скриншотера открываются под ним». Протокол (dev/zorder_probe.py,
WindowFromPoint по центру окна):

- «О программе» и тосты — topmost, видны поверх оверлея (проверено);
- проводник — обычное окно, под topmost-оверлеем его не видно; поднять
  чужое окно над topmost платформа не даёт (SetWindowPos по окну проводника
  возвращает успех и порядок окон не меняет — протокол в отчёте), поэтому
  «Открыть папку» штатно закрывает захват.

Тесты фиксируют: папка → выход из захвата; ошибка открытия → захват цел;
свои окна (диалог, тост) — topmost.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

import storage
from about import AboutDialog
from overlay import CaptureOverlay
from pin import PinWindow
from toast import Toast


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _toast_text(canvas):
    """Текст живого тоста холста (первая метка тоста)."""
    label = canvas._toast.findChild(QLabel) if canvas._toast is not None else None
    return label.text() if label is not None else ""


def _overlay():
    ov = CaptureOverlay()
    pm = QPixmap(800, 600)
    pm.fill(QColor("#7f8798"))
    ov._snapshot = pm
    ov._screen = (0, 0, 800, 600)
    ov._selection = (100, 100, 400, 300)
    ov._objects = []
    ov.finished = []
    ov._finish = lambda: ov.finished.append(True)  # без fade и закрытия окна
    return ov


def test_open_folder_closes_capture(app, monkeypatch):
    """Ctrl+O / кнопка «папка»: папка открыта, захват закрыт (иначе папка под ним)."""
    opened = []
    monkeypatch.setattr(storage, "open_shots_folder",
                        lambda folder: opened.append(folder))
    ov = _overlay()
    try:
        ov._open_folder()
        assert opened == [storage.shot_dir(Path.home())]
        assert ov.finished == [True], "захват не закрылся — папка будет под ним"
        assert "папку" in _toast_text(ov)
    finally:
        ov.close()


def test_open_folder_failure_keeps_capture(app, monkeypatch):
    """Папка не открылась — захват не теряем, тост объясняет причину."""
    def boom(folder):
        raise OSError("нет доступа")

    monkeypatch.setattr(storage, "open_shots_folder", boom)
    ov = _overlay()
    try:
        ov._open_folder()
        assert ov.finished == [], "при ошибке захват должен остаться"
        assert "нет доступа" in _toast_text(ov)
    finally:
        ov.close()


def test_pin_window_is_not_closed_by_folder(app, monkeypatch):
    """Пин-окно маленькое: папку не перекрывает — выходить из него не нужно."""
    monkeypatch.setattr(storage, "open_shots_folder", lambda folder: None)
    ov = _overlay()
    win = PinWindow(ov)
    try:
        win.finished = []
        win._finish = lambda: win.finished.append(True)
        win._open_folder()
        assert win.finished == [], "пин-окно закрывать не требовалось"
        assert "папку" in _toast_text(win)
    finally:
        win.close()
        ov.close()


def test_own_dialogs_are_topmost():
    """Свои диалоги обязаны быть выше оверлея: topmost + без parent-конфликта."""
    dialog = AboutDialog()
    try:
        flags = dialog.windowFlags()
        assert flags & Qt.WindowType.WindowStaysOnTopHint
    finally:
        dialog.close()


def test_toast_is_topmost():
    """Тост — это и есть «предупреждалка» приложения: он выше оверлея."""
    toast = Toast("Файл не сохранился, но кадр в буфере")
    try:
        flags = toast.windowFlags()
        assert flags & Qt.WindowType.WindowStaysOnTopHint
        assert flags & Qt.WindowType.Tool  # не появляется на панели задач
    finally:
        toast.close()
