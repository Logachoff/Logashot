"""P1: тултипы на всех окнах с подсказками (DS-8, З4.1).

Репорт тестера: «подсказки по кнопкам не всегда появляются». Причина: Qt
показывает тултипы только активному окну, а оверлей захвата — topmost
tool-окно без гарантированной активации (после «О программе» фокус к нему
не возвращается — протокол в dev/tooltip_probe.py: 3/3 промаха до фикса).
Лечится атрибутом WA_AlwaysShowToolTips, и ставить его нужно НА ОКНО,
а не на кнопку (док. Qt, свойство toolTip).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from about import AboutDialog
from overlay import CaptureOverlay
from panel import ScalePopup, SettingsWindow
from pin import PinWindow

ALWAYS_TIPS = "WA_AlwaysShowToolTips"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _overlay():
    ov = CaptureOverlay()
    pm = QPixmap(800, 600)
    pm.fill(QColor("#7f8798"))
    ov._snapshot = pm
    ov._selection = (100, 100, 400, 300)
    ov._objects = []
    return ov


def _has_always_tips(widget):
    """Атрибут выставлен на окне (или на самом виджете, если он топ-левел)."""
    from PySide6.QtCore import Qt

    attribute = Qt.WidgetAttribute.WA_AlwaysShowToolTips
    return widget.window().testAttribute(attribute) or widget.testAttribute(attribute)


def test_overlay_window_shows_tooltips_for_inactive_window(app):
    """Панель захвата: подсказки не зависят от активации окна (З4.1)."""
    ov = _overlay()
    try:
        assert _has_always_tips(ov), f"на окне оверлея нет {ALWAYS_TIPS}"
        assert _has_always_tips(ov._panel.button("copy"))
    finally:
        ov.close()


def test_popups_inside_overlay_window_inherit_always_tips(app):
    """Попапы масштаба/цвета/настроек — дети окна оверлея, атрибут тот же."""
    ov = _overlay()
    try:
        assert isinstance(ov._popups["resize"], ScalePopup)
        for popup in ov._popups.values():
            assert popup.window() is ov, "попап должен жить в окне оверлея"
            assert _has_always_tips(popup)
    finally:
        ov.close()


def test_pin_window_keeps_always_tips(app):
    """Пин-окно: атрибут с фикса дельты 17.10 не теряется."""
    ov = _overlay()
    win = PinWindow(ov)
    try:
        assert _has_always_tips(win)
    finally:
        win.close()
        ov.close()


def test_settings_window_shows_tooltips(app):
    """Самостоятельное окно настроек: своя подсказка у кнопки сочетания."""
    win = SettingsWindow()
    try:
        assert _has_always_tips(win), f"на окне настроек нет {ALWAYS_TIPS}"
    finally:
        win.close()


def test_about_dialog_shows_tooltips(app):
    """«О программе»: подсказка крестика — именно это окно забирало активацию."""
    dialog = AboutDialog()
    try:
        assert _has_always_tips(dialog), f"в диалоге «О программе» нет {ALWAYS_TIPS}"
        assert dialog.close_button.toolTip()
    finally:
        dialog.close()


def test_tooltip_text_exists_for_every_panel_button(app):
    """Страховка: у каждой кнопки панели есть текст подсказки (есть что показать)."""
    ov = _overlay()
    try:
        ov._panel.adjustSize()
        for item in ov._panel._buttons.values():
            assert item.toolTip(), f"пустой тултип у кнопки {item._name}"
    finally:
        ov.close()
