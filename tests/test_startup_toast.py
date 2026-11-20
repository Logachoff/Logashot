"""P1: тост «LogaShot запущен» при старте (З3.3, v0.2.2).

Старты после первого раньше были молчаливыми: онбординг показывается один
раз, а тост первого запуска (18.10) им заменён. Проверяем развилку старта
на настоящих объектах приложения: чистый профиль — онбординг и НЕТ тоста;
профиль с выставленным флагом — тост с сочетанием из настроек.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QLabel

import main
import settings as s
from firstrun import show_first_run

TRAY = QRect(1800, 1030, 40, 40)  # иконка трея у правого нижнего угла экрана


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """Чистый portable-профиль: флаг первого запуска ещё не выставлен."""
    monkeypatch.setattr(s, "_app_dir", lambda: tmp_path)
    (tmp_path / "portable").touch()
    s.reset_store()
    yield tmp_path
    s.reset_store()


def _text(toast):
    return toast.findChild(QLabel).text()


def test_toast_on_repeat_start(profile, qapp):
    """Флаг первого запуска выставлен → онбординга нет, тост есть."""
    s.mark_first_run_done()
    first_run = show_first_run()
    assert first_run is None  # второй старт — окно не показывается

    toast = main._announce_startup(first_run, TRAY)
    try:
        assert toast is not None
        assert _text(toast).startswith("LogaShot запущен · живёт в трее ·")
        # тост встаёт над иконкой трея, а не в угол экрана по умолчанию
        assert toast.y() < TRAY.y()
    finally:
        toast.close()


def test_no_toast_on_first_start(profile, qapp):
    """Первый запуск: показан онбординг — тостом его не дублируем."""
    first_run = show_first_run()
    assert first_run is not None
    try:
        assert main._announce_startup(first_run, TRAY) is None
    finally:
        first_run.close()


def test_toast_text_uses_hotkey_from_settings(profile, qapp):
    """Сочетание в тосте — из настроек, а не хардкод (меняется на лету)."""
    s.set_capture_hotkey("ctrl+alt+x")
    assert "Ctrl+Alt+X" in main._launch_toast_text()

    s.set_capture_hotkey("print screen")
    text = main._launch_toast_text()
    assert "PrtScr" in text  # подпись как в окне настроек
    assert text.endswith("— снять скриншот")
