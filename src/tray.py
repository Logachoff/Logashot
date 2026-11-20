"""Иконка LogaShot в системном трее + окно настроек из меню."""

import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

import about
import autostart
import hotkey
import panel
import settings
import toast as toast_mod
import updates


class TrayIcon(QSystemTrayIcon):
    """Трей: ЛКМ = захват (как PrtScr), ПКМ = меню.

    Порядок меню: «Снять скриншот» → «Сохранить все экраны» → «Проверить
    обновления» → «Настройки» → «О программе» → «Выход». «Сохранить все
    экраны» — тихий захват без оверлея (та же механика, что хоткей
    Shift+PrtScr); «Настройки» открывает то же окно, что шестерёнка на
    панели, без захвата; «О программе» — компактный диалог; «Проверить
    обновления» — единственный пункт, который ходит в сеть, и только по
    клику.
    """

    def __init__(self, icon: QIcon, on_capture, on_settings, on_quit,
                 on_about=None, on_save_all=None, on_check_updates=None,
                 parent=None):
        super().__init__(icon, parent)
        self.setToolTip("LogaShot")
        self._on_capture = on_capture
        self.activated.connect(self._handle_activation)

        menu = QMenu()
        capture_action = menu.addAction("Снять скриншот")
        capture_action.triggered.connect(on_capture)
        save_all_action = menu.addAction("Сохранить все экраны")
        save_all_action.triggered.connect(on_save_all or on_capture)
        check_action = menu.addAction("Проверить обновления")
        check_action.triggered.connect(on_check_updates or self.check_updates)
        settings_action = menu.addAction("Настройки")
        settings_action.triggered.connect(on_settings)
        about_action = menu.addAction("О программе")
        about_action.triggered.connect(on_about or about.show_about)
        menu.addSeparator()
        quit_action = menu.addAction("Выход")
        quit_action.triggered.connect(on_quit)
        self.setContextMenu(menu)

        self._checker = updates.UpdateChecker(self)
        self._checker.finished.connect(self._show_update_result)
        self._update_toasts = []  # живые тосты проверки — ссылку держим мы

    def _handle_activation(self, reason):
        # Trigger = одиночный ЛКМ; Context (ПКМ) обрабатывает сам Qt
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._on_capture()

    def check_updates(self):
        """Пункт «Проверить обновления»: запрос по клику, повторный — no-op."""
        self._checker.start()

    def _show_update_result(self, state, found):
        """Ответ проверки — тостом у иконки трея (тот же Toast)."""
        action = None
        if state == updates.NEWER:
            # текст короче, чем в карточке: скачать можно прямо из тоста
            text, action = f"Доступна версия {found}", "Скачать"
        elif state == updates.ACTUAL:
            text = "У вас актуальная версия"
        else:
            text = "Не удалось проверить — нет связи или GitHub недоступен"
        toast = toast_mod.show_launch(text, self.geometry(),
                                      action_text=action)
        if action is not None:
            toast.action_clicked.connect(self._open_releases)
        self._update_toasts.append(toast)
        toast.destroyed.connect(
            lambda: self._update_toasts.remove(toast)
            if toast in self._update_toasts else None)

    def _open_releases(self):
        """«Скачать» в тосте: страница последнего релиза в браузере."""
        QDesktopServices.openUrl(QUrl(updates.RELEASES_URL))


def _apply_hotkey(combo):
    """Новое сочетание: сохраняем и пересоздаём хуки без перезапуска."""
    settings.set_capture_hotkey(combo)
    hotkey.get_listener().reload()


def _apply_quiet_hotkey(combo):
    """Новое сочетание тихого захвата: сохраняем и пересоздаём хуки."""
    settings.set_quiet_hotkey(combo)
    hotkey.get_listener().reload()


def _apply_suppress(enabled):
    """Тумблер перехвата PrtScr: сохраняем и пересоздаём хуки сразу."""
    settings.set_suppress_prtscr(enabled)
    hotkey.get_listener().reload()


def _apply_autostart(enabled):
    """Тумблер автозагрузки: флаг в настройки, реестр — сразу за ним.

    Ошибку реестра не маскируем: печатаем причину, флаг остаётся записанным —
    при следующем старте приложение попробует согласовать ключ снова.
    """
    settings.set_autostart_enabled(enabled)
    try:
        autostart.sync(enabled)
    except OSError as exc:
        print(f"Ошибка: не удалось изменить автозагрузку — {exc}", file=sys.stderr)


def _fill_settings_window(win):
    """Тумблеры и подписи хоткеев — из сохранённых настроек."""
    win.set_mode(settings.panel_mode())
    win.set_watermark(settings.watermark_enabled())
    win.set_hotkey_label(hotkey.combo_label(settings.capture_hotkey()))
    win.set_quiet_hotkey_label(hotkey.combo_label(settings.quiet_hotkey()))
    win.set_suppress_prtscr(settings.suppress_prtscr())
    win.set_autostart(settings.autostart_enabled())


def create_settings_window():
    """Окно настроек с текущими значениями и применением на лету (без показа)."""
    win = panel.SettingsWindow()
    _fill_settings_window(win)
    win.mode_chosen.connect(settings.set_panel_mode)
    win.watermark_toggled.connect(settings.set_watermark_enabled)
    win.hotkey_chosen.connect(_apply_hotkey)
    win.quiet_hotkey_chosen.connect(_apply_quiet_hotkey)
    win.suppress_toggled.connect(_apply_suppress)
    win.autostart_toggled.connect(_apply_autostart)
    return win


_window = None  # одно окно на процесс: закрытие = скрытие (Qt.Popup)


def open_settings_window():
    """Пункт «Настройки» в трее: показать окно настроек, захват не запускать."""
    global _window
    if _window is None:
        _window = create_settings_window()
    _fill_settings_window(_window)  # значения могли поменять с панели
    _window.show_at_cursor()
    return _window
