"""P0/P1-тесты горячей клавиши захвата (фича v0.2): запись/валидация
сочетания без GUI-хука, логика пересоздания хуков, подавление PrtScr.

Логика хуков — чистая функция hotkey.hooks_for (без библиотеки keyboard);
пересоздание проверяем с моком keyboard.add_hotkey/hook/unhook_all.
NumPad-* и символ «*» — разные клавиши (scan 55 против Shift+8).
сочетание, записанное при русской раскладке, хранится по физической
клавише (кириллица → латиница), подпись — латиницей.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import keyboard
import pytest
from PySide6.QtCore import Qt

import hotkey
import settings as s
from hotkey import combo_label, hooks_for, is_prtscr_event, key_name, normalize_combo

# --- валидация и подпись сочетаний (уровень парсера, без GUI-хука) ---


def test_single_modifier_is_not_a_key():
    assert key_name(Qt.Key.Key_Control) is None
    assert key_name(Qt.Key.Key_Alt) is None
    assert key_name(Qt.Key.Key_Shift) is None
    assert key_name(Qt.Key.Key_Meta) is None


def test_letter_with_modifiers():
    combo, label = normalize_combo(
        Qt.Key.Key_X, [Qt.Key.Key_Control, Qt.Key.Key_Alt])
    assert combo == "ctrl+alt+x"
    assert label == "Ctrl+Alt+X"


def test_modifier_order_is_canonical():
    # порядок модификаторов в подписи не зависит от порядка нажатия
    combo, label = normalize_combo(
        Qt.Key.Key_Z, [Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt])
    assert combo == "ctrl+alt+shift+z"
    assert label == "Ctrl+Alt+Shift+Z"


def test_single_letter_and_function_keys():
    assert normalize_combo(Qt.Key.Key_Q, []) == ("q", "Q")
    assert normalize_combo(Qt.Key.Key_F5, [])[0] == "f5"
    assert normalize_combo(Qt.Key.Key_F12, [])[1] == "F12"


def test_print_screen():
    combo, label = normalize_combo(Qt.Key.Key_Print, [])
    assert combo == "print screen"
    assert label == "PrtScr"
    # PrtScr с модификатором — тоже допустимо
    combo, _ = normalize_combo(Qt.Key.Key_Print, [Qt.Key.Key_Alt])
    assert combo == "alt+print screen"


# --- NumPad-* и символ «*» — разные клавиши ---


def _scan_codes(combo):
    """Все scan-коды, которые keyboard повесит на сочетание."""
    return {code for step in keyboard.parse_hotkey(combo)
            for keys in step for code in keys}


def test_symbol_asterisk_is_recorded_as_shift_8():
    # «*» на основной клавиатуре — Shift+8; символ «*» именем не храним:
    # в keyboard это имя раскрывается ещё и в NumPad-* (scan 55)
    combo, label = normalize_combo(
        Qt.Key.Key_Asterisk, [Qt.Key.Key_Shift], "*")
    assert (combo, label) == ("shift+8", "Shift+8")
    assert 55 not in _scan_codes(combo)


def test_numpad_asterisk_is_recorded_as_num_key():
    combo, label = normalize_combo(Qt.Key.Key_Asterisk, [], "*", keypad=True)
    assert (combo, label) == ("num *", "Num *")
    assert _scan_codes(combo) == {55}


def test_symbol_asterisk_does_not_hit_numpad_asterisk():
    symbol = normalize_combo(Qt.Key.Key_Asterisk, [Qt.Key.Key_Shift], "*")[0]
    numpad = normalize_combo(Qt.Key.Key_Asterisk, [], "*", keypad=True)[0]
    assert not (_scan_codes(symbol) & _scan_codes(numpad))


def test_prtscr_event_skips_numpad_asterisk():
    assert is_prtscr_event(55, False) is True   # настоящий PrtScr
    assert is_prtscr_event(55, True) is False   # NumPad-*
    assert is_prtscr_event(9, False) is False   # другая клавиша


def test_modifier_only_combo_rejected():
    combo, label = normalize_combo(Qt.Key.Key_Control, [Qt.Key.Key_Control])
    assert combo is None and label is None


def test_unknown_key_rejected():
    assert normalize_combo(Qt.Key.Key_unknown, []) == (None, None)


def test_combo_label_human_readable():
    assert combo_label("print screen") == "PrtScr"
    assert combo_label("ctrl+alt+x") == "Ctrl+Alt+X"
    assert combo_label("shift+f10") == "Shift+F10"
    assert combo_label("space") == "Space"


# --- запись сочетания при русской раскладке ---


def _ru_key(letter):
    """Qt-код буквы, нажатой при русской раскладке (Unicode-значение)."""
    return Qt.Key(ord(letter))


def test_cyrillic_letter_recorded_as_physical_key():
    # Alt+Я при русской раскладке → keyboard получает alt+z: имя физической
    # клавиши, а не символ из event.text()
    for ru, latin in (("я", "z"), ("н", "y"), ("т", "n"), ("ф", "a")):
        combo, label = normalize_combo(_ru_key(ru), [Qt.Key.Key_Alt], ru)
        assert (combo, label) == (f"alt+{latin}", f"Alt+{latin.upper()}")


def test_uppercase_cyrillic_with_shift():
    # Shift+Я пишется как Shift+Z: подпись латиницей независимо от раскладки
    combo, label = normalize_combo(_ru_key("Я"), [Qt.Key.Key_Shift], "Я")
    assert (combo, label) == ("shift+z", "Shift+Z")


def test_ru_letter_combo_parses_into_latin_scan_codes():
    combo, _ = normalize_combo(_ru_key("я"), [Qt.Key.Key_Alt], "я")
    assert combo.isascii()
    assert _scan_codes(combo) == _scan_codes("alt+z")


def test_all_ru_letters_on_letter_keys_map_to_latin():
    # 26 букв на буквенных клавишах → латинские имена, которые keyboard
    # разрешает в scan-коды при любой раскладке
    letters = [ch for ch in "йцукенгшщзхъфывапролджэячсмитьбю"
               if ch not in "жхъэбюё"]
    assert len(letters) == 26
    for ru in letters:
        combo = hotkey.physical_combo(f"ctrl+{ru}")
        assert combo.isascii() and _scan_codes(combo), ru


def test_sign_key_letters_rejected():
    # ж, х, ъ, э, б, ю, ё стоят на знаковых клавишах: их имена в таблицах
    # keyboard зависят от раскладки — сочетание не принимаем (хук сломался бы)
    for ch in "жхъэбюё":
        assert normalize_combo(_ru_key(ch), [Qt.Key.Key_Control], ch) == (None, None)


def test_physical_combo_keeps_service_names():
    assert hotkey.physical_combo("print screen") == "print screen"
    assert hotkey.physical_combo("num *") == "num *"
    assert hotkey.physical_combo("ctrl+alt+x") == "ctrl+alt+x"


# --- логика хуков: какие ставить при каких настройках ---

def test_hooks_default_prtscr_suppressed():
    # дефолт: захват по PrtScr, системный снимок подавляется — один хук
    assert hooks_for("print screen", True) == [("print screen", True)]


def test_hooks_prtscr_not_suppressed():
    # тумблер выключен: PrtScr работает как обычно, LogaShot реагирует
    # только на своё сочетание — системный снимок НЕ подавляем
    assert hooks_for("print screen", False) == [("print screen", False)]


def test_hooks_custom_combo_with_suppress():
    # своё сочетание + тумблер включён: PrtScr тоже перехвачен
    assert hooks_for("ctrl+alt+x", True) == [
        ("ctrl+alt+x", True), ("print screen", True)]


def test_hooks_custom_combo_without_suppress():
    # своё сочетание + тумблер выключен: только своё сочетание
    assert hooks_for("ctrl+alt+x", False) == [("ctrl+alt+x", True)]


# --- пересоздание хуков из настроек (без реального перехвата) ---

@pytest.fixture
def portable_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "_app_dir", lambda: tmp_path)
    (tmp_path / "portable").touch()
    s.reset_store()
    yield tmp_path
    s.reset_store()


def test_reload_recreates_hooks(portable_settings, monkeypatch):
    calls = []
    monkeypatch.setattr(hotkey.keyboard, "add_hotkey",
                        lambda combo, cb, suppress=False:
                        calls.append(("hotkey", combo, suppress)))
    monkeypatch.setattr(hotkey.keyboard, "hook",
                        lambda cb, suppress=False:
                        calls.append(("hook", cb, suppress)))
    monkeypatch.setattr(hotkey.keyboard, "unhook_all", lambda: calls.clear())

    listener = hotkey.HotkeyListener()
    listener.reload()  # дефолт: PrtScr, тумблер включён — свой хук, не add_hotkey
    assert [(kind, suppress) for kind, _, suppress in calls] == [("hook", True)]

    s.set_capture_hotkey("ctrl+alt+x")
    s.set_suppress_prtscr(False)
    listener.reload()  # сменили сочетание и выключили тумблер — без перезапуска
    assert calls == [("hotkey", "ctrl+alt+x", True)]


def test_prtscr_hook_ignores_numpad_asterisk(portable_settings, monkeypatch):
    handlers = []
    monkeypatch.setattr(hotkey.keyboard, "hook",
                        lambda cb, suppress=False: handlers.append(cb))
    monkeypatch.setattr(hotkey.keyboard, "add_hotkey",
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(hotkey.keyboard, "unhook_all", lambda: handlers.clear())

    fired = []
    listener = hotkey.HotkeyListener()
    listener.triggered.connect(lambda: fired.append(True))
    listener.reload()
    handler = handlers[0]

    # NumPad-* (scan 55, цифровой блок) — символ печатается, захвата нет
    numpad = keyboard.KeyboardEvent(
        keyboard.KEY_DOWN, 55, "*", is_keypad=True)
    assert handler(numpad) is True
    assert fired == []

    # настоящий PrtScr (тот же scan 55, но не цифровой блок) — захват
    prtscr = keyboard.KeyboardEvent(
        keyboard.KEY_DOWN, 55, "print screen", is_keypad=False)
    assert handler(prtscr) is False
    assert fired == [True]


def test_legacy_asterisk_hotkey_is_migrated(portable_settings):
    # старая запись NumPad-* — «*» без модификаторов
    s.set_capture_hotkey("*")
    assert s.capture_hotkey() == "shift+8"
    # старая запись «*» с основной клавиатуры — «shift+*»
    s.set_capture_hotkey("shift+*")
    assert s.capture_hotkey() == "shift+8"
    # с другими модификаторами порядок остаётся каноническим
    s.set_capture_hotkey("alt+shift+*")
    assert s.capture_hotkey() == "alt+shift+8"
    assert hooks_for(s.capture_hotkey(), False) == [("alt+shift+8", True)]


def test_hotkey_settings_roundtrip(portable_settings):
    assert s.capture_hotkey() == "print screen"  # дефолт
    s.set_capture_hotkey("ctrl+shift+s")
    assert s.capture_hotkey() == "ctrl+shift+s"
    assert s.suppress_prtscr() is True  # дефолт тумблера — включён
    s.set_suppress_prtscr(False)
    assert s.suppress_prtscr() is False
    s.set_suppress_prtscr(True)


def test_empty_hotkey_rejected(portable_settings):
    with pytest.raises(ValueError):
        s.set_capture_hotkey("")


def test_legacy_cyrillic_hotkey_is_migrated(portable_settings):
    # в реестре запись сделана при русской раскладке
    s.set_capture_hotkey("alt+я")
    assert s.capture_hotkey() == "alt+z"
    assert hotkey.combo_label(s.capture_hotkey()) == "Alt+Z"  # подпись латиницей
    assert hooks_for(s.capture_hotkey(), False) == [("alt+z", True)]
    # миграция только при чтении: в хранилище остаётся исходная запись
    assert s._store().value("hotkey/capture", type=str) == "alt+я"
