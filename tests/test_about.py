"""P1: диалог «О программе» (план 27.10, фича v0.2).

Проверяем контракт: версия берётся из src/version.py (а не из строки в
виджете), ссылка ведёт на подтверждённый сайт и открывается системным
браузером, крестик и Esc закрывают.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

import about
import version


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(app):
    dlg = about.AboutDialog()
    yield dlg
    dlg.close()


class _FakeDesktop:
    """Подмена QDesktopServices: запоминаем, какой URL просили открыть."""

    def __init__(self):
        self.urls = []

    def openUrl(self, url):
        self.urls.append(url.toString())


def test_version_comes_from_version_module(app, monkeypatch):
    """Не хардкод: версия в подписи — value из version.VERSION."""
    monkeypatch.setattr(version, "VERSION", "9.9.9")
    fresh = about.AboutDialog()
    try:
        assert fresh.release_label.text() == "версия 9.9.9"
    finally:
        fresh.close()


def test_link_points_to_site_and_opens_browser(app, monkeypatch):
    opened = _FakeDesktop()
    monkeypatch.setattr(about, "QDesktopServices", opened)
    dlg = about.AboutDialog()
    try:
        assert about.SITE_URL == "https://logachoff.ru/"
        assert about.SITE_URL in dlg.link.text()
        dlg.link.linkActivated.emit(about.SITE_URL)  # клик по ссылке
        assert opened.urls == ["https://logachoff.ru/"]
    finally:
        dlg.close()


def test_dialog_title_and_author(app):
    dlg = about.AboutDialog()
    try:
        assert dlg.windowTitle() == "О программе"
        assert about.AUTHOR == "Сергей Логачев"
    finally:
        dlg.close()


def test_escape_closes_dialog(dialog):
    dialog.show()
    assert dialog.isVisible()
    dialog.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                   Qt.KeyboardModifier.NoModifier))
    assert not dialog.isVisible()


def test_close_button_closes_dialog(dialog):
    dialog.show()
    assert dialog.isVisible()
    dialog.close_button.click()
    assert not dialog.isVisible()
