"""P0-тесты спецификации панели.

Порядок и состав кнопок (20 кнопок: добавлены select/marker/hl/frame),
флаги весов (accent только «Копировать», ghost — редкие действия без
пина: заметность пина, решение 24.10, dimmed-заглушек нет — OCR с 0.3.0
обычный инструмент), один ряд
в пин-окне полного размера (правка 17.10). Легко сломать
правкой _PANEL_SPEC, дорого заметить глазами.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

import panel
from panel import _BTN, _GHOST_DELTA, _PANEL_SPEC, _SPEC_BY_NAME

# порядок кнопок по спецификации v0.2 (None — разделители групп)
EXPECTED_ORDER = [
    "copy", None,
    "save", "select", "arrow", "text", "blur", "marker", "hl", "frame",
    "ocr", "num", "color", "undo", None,
    "folder", "mail", "resize", "pin", None,
    "settings", "cancel", None,
    "brand",
]

# ghost — редкие действия; «Пин» из ghost исключён (заметность, 24.10)
GHOST_BUTTONS = {"folder", "mail", "resize", "settings", "cancel"}
NORMAL_BUTTONS = {"save", "select", "arrow", "text", "blur", "marker",
                  "hl", "frame", "ocr", "num", "color", "undo", "pin"}


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _flags(name):
    return panel._SPEC_BY_NAME[name][1]


def test_order_matches_spec():
    names = [item if item is None else item[0] for item in _PANEL_SPEC]
    assert names == EXPECTED_ORDER


def test_panel_has_20_buttons():
    count = sum(1 for item in _PANEL_SPEC if item is not None)
    assert count == 20


def test_weights_accent_only_copy():
    for item in _PANEL_SPEC:
        if item is None:
            continue
        assert ("accent" in item[2]) == (item[0] == "copy"), item[0]


def test_weights_ghost_set():
    ghosts = {item[0] for item in _PANEL_SPEC if item and item[2].get("ghost")}
    assert ghosts == GHOST_BUTTONS
    # «Пин» — обычного веса, как инструменты (решение 24.10)
    assert not _flags("pin").get("ghost")
    assert not _flags("pin").get("accent")
    # остальные обычные кнопки — без флагов веса
    for name in NORMAL_BUTTONS - {"pin"}:
        assert not _flags(name).get("ghost") and not _flags(name).get("accent")


def test_no_dimmed_buttons():
    """Dimmed-заглушек нет: OCR (5) с 0.3.0 — обычный инструмент."""
    dimmed = {item[0] for item in _PANEL_SPEC if item and item[2].get("dimmed")}
    assert dimmed == set()


def test_badge_only_resize():
    badged = {item[0] for item in _PANEL_SPEC if item and item[2].get("badge")}
    assert badged == {"resize"}


def test_capture_panel_sizes(qapp):
    tb = panel.ToolbarPanel(None)
    assert tb.button("copy").width() == _BTN  # акцент — квадрат, без подписи
    assert tb.button("save").width() == _BTN
    assert tb.button("pin").width() == _BTN  # пин — полного размера (24.10)
    for name in GHOST_BUTTONS:
        btn = tb.button(name)
        assert btn.width() == _BTN - _GHOST_DELTA, name
        assert btn.height() == _BTN - _GHOST_DELTA, name


def test_pin_panel_single_row_same_size(qapp):
    pp = panel.PinPanel(None)
    from PySide6.QtWidgets import QHBoxLayout
    lay = pp.layout()
    assert isinstance(lay, QHBoxLayout)  # один ряд, без вложенных рядов
    for i in range(lay.count()):
        assert lay.itemAt(i).layout() is None  # нет подрядов — одна строка
    # полный набор кнопок, тот же, что у захвата
    for name in EXPECTED_ORDER:
        if name is not None:
            assert pp.button(name) is not None, name
    # размеры — как у панели захвата (правка 17.10)
    assert pp.button("copy").width() == _BTN
    assert pp.button("save").width() == _BTN
    assert pp.button("pin").width() == _BTN
    for name in GHOST_BUTTONS:
        assert pp.button(name).width() == _BTN - _GHOST_DELTA, name
    # ширина однострочной панели пина равна ширине панели захвата
    tb = panel.ToolbarPanel(None)
    tb.adjustSize()
    pp.adjustSize()
    assert pp.width() == tb.width(), (pp.width(), tb.width())


def test_panel_actual_width(qapp):
    """Фактическая ширина новой 20-кнопочной панели — для мин. ширины
    пин-окна (сообщается)."""
    tb = panel.ToolbarPanel(None)
    tb.adjustSize()
    assert tb.width() > 700  # заметно шире старой 16-кнопочной


def test_pin_button_toggled_in_pin_panel(qapp):
    # в пин-окне «Пин» — переключатель обратно: свой тултип и нажатый вид
    # (правка 17.10); на панели захвата — обычная кнопка
    pp = panel.PinPanel(None)
    pin_btn = pp.button("pin")
    assert pin_btn.toolTip() == "Снять с пина — вернуться к захвату"
    assert pin_btn._active
    tb = panel.ToolbarPanel(None)
    assert tb.button("pin").toolTip() == _SPEC_BY_NAME["pin"][0]
    assert not tb.button("pin")._active
