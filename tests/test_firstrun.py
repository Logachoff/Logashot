"""P1: окно первого запуска (фича v0.2) — содержимое по моку v2.12
и флаг одноразового показа (тот же, что у тоста 18.10 — тост заменён).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtWidgets import QLabel, QPushButton

import settings as s
from firstrun import _BUTTON_TEXT, _HEADLINE, _ITEMS, _SUBTITLE, FirstRunWindow, show_first_run


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_window_contains_all_items(qapp):
    win = FirstRunWindow()
    texts = [label.text() for label in win.findChildren(QLabel)]
    assert _HEADLINE in texts
    assert _SUBTITLE in texts
    for _, text in _ITEMS:
        assert text in texts  # все 4 пункта — дословно из мока
    buttons = [b.text() for b in win.findChildren(QPushButton)]
    assert _BUTTON_TEXT in buttons
    assert len(_ITEMS) == 4


def test_first_run_shown_once(tmp_path, monkeypatch):
    """Чистый профиль → окно есть; после закрытия флаг стоит → не показываем."""
    monkeypatch.setattr(s, "_app_dir", lambda: tmp_path)
    (tmp_path / "portable").touch()
    s.reset_store()
    try:
        assert not s.first_run_done()
        win = show_first_run()
        assert win is not None
        assert s.first_run_done()  # флаг выставлен сразу при показе
        win.close()
        assert show_first_run() is None  # второй раз — не показываем
    finally:
        s.reset_store()
