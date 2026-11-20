"""P0/P1-тесты тихого скриншота всех экранов.

- имена файлов: суффикс «_мон<N>» при нескольких мониторах, обычная маска
  при одном; счётчик общий на захват и не затирает предыдущий (чистое ядро);
- capture пишет файл на каждый монитор и НЕ трогает буфер обмена;
- хоткей: дефолт Shift+PrtScr, переназначение, дубли с основным отклоняются;
- хук тихого сочетания ставится всегда (тумблер PrtScr на него не влияет),
  модификаторы PrtScr сверяются «ровно» — Shift+PrtScr не открывает оверлей;
- активный оверлей — тихий захват игнорируется; ошибка записи — тост-ошибка.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import keyboard
import pytest
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication

import hotkey
import main as main_mod
import panel
import quiet
import screengrab
import settings as s
import storage
import tray
from overlay import CaptureOverlay

MOMENT = datetime(2026, 11, 19, 15, 8, 33)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def portable(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "_app_dir", lambda: tmp_path)
    (tmp_path / "portable").touch()
    s.reset_store()
    yield tmp_path
    s.reset_store()


class _Listener:
    """Заглушка слушателя: пересоздание хуков не должно трогать keyboard."""

    def __init__(self):
        self.reloads = 0

    def reload(self):
        self.reloads += 1


# --- имена файлов: чистое ядро ---

def test_one_monitor_keeps_plain_mask():
    # при одном мониторе — обычная маска без суффикса
    assert quiet.file_names(MOMENT, 1, 1) == ["LogaShot_2026-11-19_15-08-33_001.png"]


def test_monitor_suffix_shared_counter():
    # два монитора: файлы различаются только суффиксом, счётчик общий
    assert quiet.file_names(MOMENT, 7, 2) == [
        "LogaShot_2026-11-19_15-08-33_007_мон1.png",
        "LogaShot_2026-11-19_15-08-33_007_мон2.png",
    ]
    assert quiet.file_names(MOMENT, 1, 3)[2].endswith("_001_мон3.png")


def test_file_names_reject_empty_screen_list():
    with pytest.raises(ValueError):
        quiet.file_names(MOMENT, 1, 0)


def test_next_counter_skips_monitor_files():
    # второй тихий захват в ту же секунду не должен затирать первый
    names = ["LogaShot_2026-11-19_15-08-33_001_мон1.png",
             "LogaShot_2026-11-19_15-08-33_001_мон2.png"]
    assert storage.next_counter(names, MOMENT) == 2
    # обычный файл той же секунды и чужое имя — та же логика
    assert storage.next_counter(["LogaShot_2026-11-19_15-08-33_001.png"], MOMENT) == 2
    assert storage.next_counter(["чужое.png"], MOMENT) == 1


# --- текст тоста и склонение ---

def test_toast_text_one_screen():
    assert quiet.toast_text(1) == "Сохранено"


def test_toast_text_declension():
    assert quiet.toast_text(2) == "Сохранено: 2 экрана"
    assert quiet.toast_text(5) == "Сохранено: 5 экранов"
    assert quiet.toast_text(21) == "Сохранено: 21 экран"
    assert quiet.toast_text(11) == "Сохранено: 11 экранов"


# --- захват: файл на монитор, физические пиксели, буфер не трогаем ---

def _frame(width, height):
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor("#123456"))
    return img


def test_capture_writes_file_per_screen(tmp_path, monkeypatch):
    frames = [_frame(12, 8), _frame(6, 4)]
    monkeypatch.setattr(quiet, "screens", lambda: [object(), object()])
    monkeypatch.setattr(quiet.screengrab, "grab_screen", lambda screen: frames.pop(0))

    saved = quiet.capture(shots_dir=tmp_path)

    assert saved[0].name.endswith("_001_мон1.png")
    assert saved[1].name.endswith("_001_мон2.png")
    assert all(p.exists() for p in saved)
    # кадр сохранён в физических пикселях монитора, а не в логических
    assert (QImage(str(saved[0])).width(), QImage(str(saved[0])).height()) == (12, 8)
    assert (QImage(str(saved[1])).width(), QImage(str(saved[1])).height()) == (6, 4)


def test_capture_does_not_touch_clipboard(tmp_path, monkeypatch):
    touched = []
    monkeypatch.setattr(QGuiApplication, "clipboard",
                        lambda: touched.append(True))
    monkeypatch.setattr(quiet, "screens", lambda: [object()])
    monkeypatch.setattr(quiet.screengrab, "grab_screen", lambda screen: _frame(4, 3))

    saved = quiet.capture(shots_dir=tmp_path)

    assert len(saved) == 1 and saved[0].name.endswith("_001.png")  # без суффикса
    assert touched == []  # буфер обмена не трогаем


def test_capture_passes_errors_to_caller(tmp_path, monkeypatch):
    monkeypatch.setattr(quiet, "screens", lambda: [object()])
    monkeypatch.setattr(quiet.screengrab, "grab_screen", lambda screen: QImage())
    with pytest.raises(OSError):
        quiet.capture(shots_dir=tmp_path)  # QImage.save вернул False


def test_mono_frame_detection():
    img = _frame(10, 10)
    assert screengrab.mono(img) is True  # одноцветный кадр — сбой захвата
    img.setPixelColor(5, 5, QColor("#ffffff"))  # проба по центру кадра
    assert screengrab.mono(img) is False


# --- хоткей: дефолт, переназначение, дубли ---

def test_quiet_hotkey_default_and_roundtrip(portable):
    assert s.quiet_hotkey() == "shift+print screen"  # слот «захват всего экрана»
    assert hotkey.combo_label(s.quiet_hotkey()) == "Shift+PrtScr"
    s.set_quiet_hotkey("ctrl+alt+q")
    assert s.quiet_hotkey() == "ctrl+alt+q"
    s.set_quiet_hotkey("alt+я")  # запись при русской раскладке мигрирует
    assert s.quiet_hotkey() == "alt+z"
    with pytest.raises(ValueError):
        s.set_quiet_hotkey("")


def test_taken_by_reports_both_roles(portable):
    assert hotkey.taken_by("shift+print screen", "print screen",
                           "shift+print screen") == "quiet"
    assert hotkey.taken_by("print screen", "print screen",
                           "shift+print screen") == "capture"
    assert hotkey.taken_by("ctrl+alt+q", "print screen",
                           "shift+print screen") is None


def test_settings_window_rejects_duplicates(app, portable, monkeypatch):
    listener = _Listener()
    monkeypatch.setattr(tray.hotkey, "get_listener", lambda: listener)
    messages = []
    monkeypatch.setattr(panel.toast_mod, "show_launch",
                        lambda text, anchor, **kw: messages.append(text))
    win = tray.create_settings_window()
    try:
        assert win._quiet_btn.text() == "Shift+PrtScr"  # подпись нового поля
        # тихое сочетание не может занять основное (и наоборот)
        win._on_quiet_hotkey("print screen")
        assert s.quiet_hotkey() == "shift+print screen"
        assert messages == ["Занято захватом — выбери другое сочетание"]
        assert win._quiet_btn.text() == "Shift+PrtScr"  # подпись вернулась

        win._on_capture_hotkey("shift+print screen")
        assert s.capture_hotkey() == "print screen"
        assert messages[-1] == "Занято тихим скриншотом — выбери другое"
        assert listener.reloads == 0  # отказ не пересоздаёт хуки

        # свободное сочетание применяется и пересоздаёт хуки
        win._on_quiet_hotkey("ctrl+alt+q")
        assert s.quiet_hotkey() == "ctrl+alt+q"
        assert listener.reloads == 1
    finally:
        win.close()


def test_panel_popup_shows_quiet_hotkey_label(app, portable, monkeypatch):
    """Попап с панели показывает актуальную подпись тихого хоткея."""
    listener = _Listener()
    monkeypatch.setattr(hotkey, "get_listener", lambda: listener)
    ov = CaptureOverlay()
    try:
        ov._toggle_popup("settings")
        popup = ov._popups["settings"]
        assert popup._quiet_btn.text() == "Shift+PrtScr"  # из сохранённых настроек

        # запись сочетания из попапа панели: кнопка ставит подпись, сигнал — настройку
        btn = popup._quiet_btn
        btn.set_hotkey_label("Ctrl+Shift+9")
        btn.hotkey_chosen.emit("ctrl+shift+9")
        assert s.quiet_hotkey() == "ctrl+shift+9"
        assert listener.reloads == 1  # хук пересоздан сразу, без перезапуска

        # попап закрыт/открыт заново — подпись берётся из настроек, а не из кнопки
        popup.hide()
        s.set_quiet_hotkey("ctrl+alt+q")
        ov._toggle_popup("settings")
        assert popup._quiet_btn.text() == "Ctrl+Alt+Q"
    finally:
        ov.close()


def test_apply_quiet_hotkey_saves_and_reloads(portable, monkeypatch):
    listener = _Listener()
    monkeypatch.setattr(tray.hotkey, "get_listener", lambda: listener)
    tray._apply_quiet_hotkey("ctrl+shift+9")
    assert s.quiet_hotkey() == "ctrl+shift+9"
    assert listener.reloads == 1


# --- хуки: тихий ставится всегда, PrtScr — по точным модификаторам ---

def test_quiet_hooks_ignore_prtscr_toggle():
    # тумблер «Перехватывать PrtScr у Windows» на тихий хоткей не влияет
    assert hotkey.quiet_hooks_for("shift+print screen") == [("shift+print screen", True)]
    assert hotkey.quiet_hooks_for("ctrl+alt+q") == [("ctrl+alt+q", True)]


def test_prtscr_hit_requires_exact_modifiers():
    event = keyboard.KeyboardEvent(keyboard.KEY_DOWN, 55, "print screen", is_keypad=False)

    def held(*mods):
        return lambda name: name in mods

    assert hotkey.prtscr_hit("print screen", event, held()) is True
    # Shift+PrtScr — это тихое сочетание, захват по одиночному PrtScr молчит
    assert hotkey.prtscr_hit("print screen", event, held("shift")) is False
    assert hotkey.prtscr_hit("shift+print screen", event, held("shift")) is True
    assert hotkey.prtscr_hit("shift+print screen", event, held()) is False
    assert hotkey.prtscr_hit("ctrl+shift+print screen", event,
                             held("shift")) is False  # набор модификаторов важен


def test_prtscr_hit_ignores_numpad_asterisk():
    numpad = keyboard.KeyboardEvent(keyboard.KEY_DOWN, 55, "*", is_keypad=True)
    assert hotkey.prtscr_hit("print screen", numpad, lambda name: False) is False


# --- тихий захват целиком: оверлей, тост, ошибка ---

class _FakeOverlay:
    def __init__(self, visible):
        self._visible = visible

    def isVisible(self):
        return self._visible


def test_quiet_capture_notifies_once(tmp_path):
    notified = []
    files = [tmp_path / "a.png", tmp_path / "b.png"]
    result = main_mod._run_quiet_capture(
        _FakeOverlay(False), notified.append, capture=lambda: files)
    assert result == files
    assert notified == ["Сохранено: 2 экрана"]  # один тост на весь захват


def test_active_overlay_ignores_quiet_capture():
    notified, calls = [], []
    result = main_mod._run_quiet_capture(
        _FakeOverlay(True), notified.append,
        capture=lambda: calls.append(True) or [])
    assert result is None and calls == [] and notified == []


def test_quiet_capture_failure_shows_error_toast(capsys):
    def boom():
        raise OSError("нет доступа к папке")

    notified = []
    assert main_mod._run_quiet_capture(
        _FakeOverlay(False), notified.append, capture=boom) is None
    assert notified == [quiet.FAIL_TEXT]
    assert "нет доступа к папке" in capsys.readouterr().err  # причина — в лог
