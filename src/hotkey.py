"""Глобальная горячая клавиша захвата через библиотеку keyboard.

Формат сочетания — как у keyboard («ctrl+alt+x», «print screen»); дефолт —
PrtScr (возврат обязательства 16.10). Сочетание настраивается в попапе
настроек и применяется без перезапуска: HotkeyListener.reload() пересоздаёт
хуки из settings (фича v0.2). Тумблер «Перехватывать PrtScr у Windows»:
включён — PrtScr запускает захват LogaShot и системный снимок подавляется
(suppress); выключен — PrtScr живёт у системы, LogaShot реагирует только
на своё сочетание.

keyboard вызывает колбэки из своего потока — в Qt переводим сигналом,
который доставляется в главный поток (queued connection).
Win+Shift+S и Alt+PrtScr не трогаем (утверждённый проект клавиш).

PrtScr ставим не по имени «print screen»: в таблицах keyboard это имя
раскрывается в scan-коды 84 и 55, а scan 55 — ещё и NumPad-*. Поэтому PrtScr
ловим низкоуровневым хуком и отсекаем события цифрового блока.
Символ «*» с основной клавиатуры — это Shift+8; записываем его физической
клавишей, чтобы он не пересекался с NumPad-*.

Русская раскладка: имя клавиши берём по Qt-коду (физическая клавиша), а не по
символу из event.text(); сочетание храним латиницей («alt+z», не «alt+я») —
иначе при старте с английской раскладкой хук не встаёт.

Тихий скриншот всех экранов — второй, независимый хоткей: хуки для
него строит quiet_hooks_for, сигнал — quiet. Модификаторы сочетания с PrtScr
сверяются «ровно» (prtscr_hit): Shift+PrtScr уходит тихому захвату и не
открывает оверлей по одиночному PrtScr.
"""

import keyboard
from PySide6.QtCore import QObject, Qt, Signal

import settings

_MODIFIER_KEYS = {
    Qt.Key.Key_Control: "ctrl",
    Qt.Key.Key_Alt: "alt",
    Qt.Key.Key_Shift: "shift",
    Qt.Key.Key_Meta: "win",
}
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")  # порядок в подписи сочетания

# Как называют клавиши keyboard и как показываем в интерфейсе
_SPECIAL_KEYS = {
    Qt.Key.Key_Print: ("print screen", "PrtScr"),
    Qt.Key.Key_Space: ("space", "Space"),
    Qt.Key.Key_Tab: ("tab", "Tab"),
    Qt.Key.Key_Backtab: ("tab", "Shift+Tab"),
    Qt.Key.Key_Insert: ("insert", "Ins"),
    Qt.Key.Key_Delete: ("delete", "Del"),
    Qt.Key.Key_Home: ("home", "Home"),
    Qt.Key.Key_End: ("end", "End"),
    Qt.Key.Key_PageUp: ("page up", "PgUp"),
    Qt.Key.Key_PageDown: ("page down", "PgDn"),
    Qt.Key.Key_Up: ("up", "↑"),
    Qt.Key.Key_Down: ("down", "↓"),
    Qt.Key.Key_Left: ("left", "←"),
    Qt.Key.Key_Right: ("right", "→"),
    Qt.Key.Key_Backspace: ("backspace", "Backspace"),
    Qt.Key.Key_Escape: ("esc", "Esc"),
    Qt.Key.Key_Return: ("enter", "Enter"),
    Qt.Key.Key_Enter: ("enter", "Enter"),
    Qt.Key.Key_CapsLock: ("caps lock", "CapsLock"),
    Qt.Key.Key_NumLock: ("num lock", "NumLock"),
    Qt.Key.Key_ScrollLock: ("scroll lock", "ScrollLock"),
}
for _i in range(1, 13):  # F1..F12
    _SPECIAL_KEYS[Qt.Key(0x01000030 + _i - 1)] = (f"f{_i}", f"F{_i}")

# NumPad-* в keyboard — «num *» (scan 55), а символ «*» на основной клавиатуре
# печатается как Shift+8. Имя «*» в keyboard раскрывается в оба scan-кода
# (55 и 9) — иначе хук на символ ловил NumPad-*, поэтому разводим имена.
_NUMPAD_KEYS = {
    Qt.Key.Key_Asterisk: ("num *", "Num *"),
}
_SHIFTED_KEYS = {  # символы основной клавиатуры: подпись = физическая клавиша
    Qt.Key.Key_Asterisk: ("8", "8"),
}

# Раскладка ЙЦУКЕН (Windows): буква кириллицей → имя физической клавиши QWERTY.
# keyboard строит таблицу имён по активной раскладке на старте, поэтому запись
# «alt+я» при английской раскладке не разрешается в хук. Имена
# латинских букв keyboard выводит из виртуального кода клавиши — они есть в
# любой раскладке, поэтому сочетание храним только ими.
_RU_LAYOUT = {
    "й": "q", "ц": "w", "у": "e", "к": "r", "е": "t", "н": "y", "г": "u",
    "ш": "i", "щ": "o", "з": "p",
    "ф": "a", "ы": "s", "в": "d", "а": "f", "п": "g", "р": "h", "о": "j",
    "л": "k", "д": "l",
    "я": "z", "ч": "x", "с": "c", "м": "v", "и": "b", "т": "n", "ь": "m",
}

# PrtScr и NumPad-* делят scan-код 55 — различаем их по признаку цифрового блока.
PRTSCR_SCAN_CODE = 55
PRTSCR_COMBO = "print screen"


def key_name(key, text="", keypad=False):
    """Имя клавиши для keyboard и подписи для UI; None — модификатор без клавиши.

    keypad (Qt.KeypadModifier) отделяет цифровой блок: NumPad-* — «num *»,
    «*» с основной клавиатуры — физическая клавиша Shift+8 (Shift добавляет
    normalize_combo).
    """
    if key in _MODIFIER_KEYS:
        return None  # одиночный модификатор — не клавиша
    if key in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[key]
    if keypad and key in _NUMPAD_KEYS:
        return _NUMPAD_KEYS[key]
    if not keypad and key in _SHIFTED_KEYS:
        return _SHIFTED_KEYS[key]
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        name = chr(key).lower()
        return name, name.upper()
    if 0x0400 <= key <= 0x04FF:
        # буква кириллицей — запись при русской раскладке; берём физическую
        # клавишу по Qt-коду, а не символ из event.text()
        name = _RU_LAYOUT.get(chr(key).lower())
        # знаковые клавиши (ж, х, ъ, э, б, ю, ё) стабильного имени в таблицах
        # keyboard не имеют — сочетание не принимаем, иначе хук сломается
        return (name, name.upper()) if name else (None, None)
    if text and text.isprintable() and len(text) == 1:
        return text.lower(), text.upper()
    return None, None  # неизвестная клавиша — не принимаем


def normalize_combo(key, modifiers, text="", keypad=False):
    """Сочетание из Qt-события в формат keyboard: «ctrl+alt+x».

    Возвращает (combo, label): combo — для хуков keyboard и настроек,
    label — человекочитаемая подпись. (None, None), если клавиша не задана
    (нажали только модификатор) или неизвестна — ждём дальше.
    keypad=True (клавиша цифрового блока) разводит NumPad-* и символ «*».
    """
    mods = sorted(
        (_MODIFIER_KEYS[m] for m in modifiers if m in _MODIFIER_KEYS),
        key=_MODIFIER_ORDER.index,
    )
    named = key_name(key, text, keypad)
    if named is None or named[0] is None:
        return None, None
    name, _ = named
    parts = mods + [name]
    return "+".join(parts), combo_label("+".join(parts))


def combo_label(combo):
    """Человекочитаемая подпись сочетания: «print screen» → «PrtScr»."""
    parts = combo.split("+")
    label = []
    for part in parts:
        if part == "print screen":
            label.append("PrtScr")
        elif len(part) == 1:
            label.append(part.upper())
        else:
            label.append(part.capitalize())
    return "+".join(label)


def physical_combo(combo):
    """Сочетание из настроек → имена физических клавиш (кириллица → латиница).

    Старые записи, сделанные при русской раскладке («alt+я»), приводим к
    «alt+z», иначе хук не встанет при старте с английской раскладкой.
    Служебные имена («print screen», «num *») и латиница не меняются.
    """
    return "+".join(
        _RU_LAYOUT.get(part.lower(), part) if len(part) == 1 else part
        for part in combo.split("+")
    )


def hooks_for(capture_combo, suppress_prtscr):
    """Какие глобальные хуки ставить: [(сочетание, подавлять_системное)].

    Чистая функция — логика пересоздания хуков под тестом.
    - своё сочетание с suppress=True (модификаторы не уходят в приложение);
    - сочетание == PrtScr: подавляем системный снимок, только если тумблер
      включён (выключен — PrtScr живёт у системы целиком);
    - тумблер включён и сочетание ≠ PrtScr — PrtScr тоже хук с подавлением:
      запускает захват LogaShot, системный снимок Windows не откроется.
    """
    if capture_combo == PRTSCR_COMBO:
        return [(PRTSCR_COMBO, suppress_prtscr)]
    hooks = [(capture_combo, True)]
    if suppress_prtscr:
        hooks.append((PRTSCR_COMBO, True))
    return hooks


def quiet_hooks_for(quiet_combo):
    """Хуки тихого скриншота всех экранов: [(сочетание, подавлять)].

    Перехватывается ровно записанное сочетание — тумблер «Перехватывать
    PrtScr у Windows» на тихий хоткей не влияет; системный снимок Windows
    по этому сочетанию не открывается (Shift+PrtScr у Windows — свой снимок).
    """
    return [(quiet_combo, True)]


def combo_modifiers(combo):
    """Модификаторы сочетания в каноническом порядке: «shift+print screen» → («shift»,)."""
    return tuple(part for part in combo.split("+") if part in _MODIFIER_ORDER)


def prtscr_hit(combo, event, pressed):
    """Сработало ли сочетание с PrtScr у этого события.

    pressed — предикат «клавиша зажата» (keyboard.is_pressed). Модификаторы
    сверяем по набору «ровно» — как у keyboard.add_hotkey: Shift+PrtScr не
    запускает захват по одиночному PrtScr, а уходит тихому сочетанию.
    """
    if not is_prtscr_event(event.scan_code, event.is_keypad):
        return False
    required = set(combo_modifiers(combo))
    held = {name for name in _MODIFIER_ORDER if pressed(name)}
    return required == held


def taken_by(combo, capture_combo, quiet_combo):
    """Кем занято сочетание: «capture» | «quiet» | None (дубли запрещены)."""
    if combo == capture_combo:
        return "capture"
    if combo == quiet_combo:
        return "quiet"
    return None


def is_prtscr_event(scan_code, is_keypad):
    """Настоящий PrtScr: scan 55 без признака цифрового блока.

    NumPad-* тоже даёт scan 55, но keyboard помечает его is_keypad=True;
    нажатие NumPad-* не должно запускать захват.
    """
    return scan_code == PRTSCR_SCAN_CODE and not is_keypad


class HotkeyListener(QObject):
    """Слушает хоткеи глобально и испускает Qt-сигналы triggered / quiet."""

    triggered = Signal()  # захват с выделением области
    quiet = Signal()  # тихий скриншот всех экранов

    def start(self):
        self.reload()

    def reload(self):
        """Пересоздать хуки из настроек — применение без перезапуска (v0.2)."""
        keyboard.unhook_all()
        for combo, suppress in hooks_for(settings.capture_hotkey(),
                                         settings.suppress_prtscr()):
            self._install(combo, suppress, self.triggered.emit)
        for combo, suppress in quiet_hooks_for(settings.quiet_hotkey()):
            self._install(combo, suppress, self.quiet.emit)

    def _install(self, combo, suppress, action):
        """Своё сочетание — add_hotkey, любое с PrtScr — низкоуровневый хук.

        Имя «print screen» в таблицах keyboard раскрывается ещё и в scan 55
        (NumPad-*), поэтому сочетания с PrtScr ловим своим хуком и сверяем
        scan-код с модификаторами.
        """
        if PRTSCR_COMBO in combo.split("+"):
            keyboard.hook(
                lambda event: self._on_prtscr_event(event, combo, action),
                suppress=suppress)
        else:
            keyboard.add_hotkey(combo, action, suppress=suppress)

    def _on_prtscr_event(self, event, combo, action):
        """Всё пропускаем; PrtScr с модификаторами своего сочетания — запуск."""
        if event.event_type != keyboard.KEY_DOWN or not prtscr_hit(
                combo, event, keyboard.is_pressed):
            return True
        action()
        return False  # при suppress=True системный снимок не открывается

    def stop(self):
        keyboard.unhook_all()


_listener = None


def get_listener():
    """Единый слушатель процесса: настройки из попапов пересоздают его хуки."""
    global _listener
    if _listener is None:
        _listener = HotkeyListener()
    return _listener
