"""0.4.0: проверка обновлений по GitHub Releases.

Сеть подменяется на уровне `updates._fetch_json` — ни один тест в GitHub не
ходит. Ядро (разбор тега и сравнение версий) проверяется напрямую, UI — через
тот же мок: карточка «О программе» и тост из трея.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import about
import tray
import updates
import version


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def current(monkeypatch):
    """Текущая версия для проверок — фиксированная, не из сборки."""
    monkeypatch.setattr(version, "VERSION", "0.3.2")


class _FakeDesktop:
    """Подмена QDesktopServices: запоминаем, какой URL просили открыть."""

    def __init__(self):
        self.urls = []

    def openUrl(self, url):
        self.urls.append(url.toString())


class _StubToast(QObject):
    """Заглушка тоста: нужны только сигналы, которые дёргает трей."""

    action_clicked = Signal()


def _mock_fetch(monkeypatch, answer):
    """Подмена транспорта: answer(on_done) вызывается сразу, без сети."""
    calls = []

    def fake(url, on_done):
        calls.append(url)
        answer(on_done)

    monkeypatch.setattr(updates, "_fetch_json", fake)
    return calls


# --- ядро: разбор тега -------------------------------------------------------

def test_parse_version_accepts_prefix_and_suffix():
    assert updates.parse_version("v0.4.0") == (0, 4, 0)
    assert updates.parse_version("0.4.0") == (0, 4, 0)
    assert updates.parse_version("v0.4.0-beta") == (0, 4, 0)
    assert updates.parse_version("0.4") == (0, 4)


@pytest.mark.parametrize("tag", ["", "v", "latest", "0..4", "1.2.3.4.5", None, 4])
def test_parse_version_rejects_garbage(tag):
    """Битый тег — дефект данных (None), а не исключение наружу."""
    assert updates.parse_version(tag) is None


def test_is_newer_compares_numeric_parts():
    assert updates.is_newer((9, 9, 9), (0, 3, 2)) is True
    assert updates.is_newer((0, 3, 2), (0, 3, 2)) is False
    assert updates.is_newer((0, 4), (0, 4, 0)) is False  # 0.4 == 0.4.0
    assert updates.is_newer((0, 10), (0, 9, 9)) is True  # 10 > 9, не строка


# --- ядро: разбор ответа -----------------------------------------------------

def test_interpret_newer_release(current):
    assert updates.interpret({"tag_name": "v9.9.9"}) == (updates.NEWER, "9.9.9")


@pytest.mark.parametrize("tag, found", [
    ("v0.3.2", "0.3.2"),
    ("0.3.2", "0.3.2"),
    ("v0.1.0", "0.1.0"),
    ("v0.3.2-beta", "0.3.2"),
])
def test_interpret_same_or_older_is_actual(current, tag, found):
    """Форк/сборка впереди релиза — тоже «актуально»."""
    assert updates.interpret({"tag_name": tag}) == (updates.ACTUAL, found)


@pytest.mark.parametrize("payload", [
    None, {}, [], {"tag_name": None}, {"tag_name": "latest"}, "не json",
])
def test_interpret_bad_data_is_error(current, payload):
    assert updates.interpret(payload) == (updates.ERROR, "")


# --- проверка через мок транспорта ------------------------------------------

def test_checker_reports_newer(app, current, monkeypatch):
    _mock_fetch(monkeypatch, lambda done: done({"tag_name": "v9.9.9"}, None))
    checker = updates.UpdateChecker()
    got = []
    checker.finished.connect(lambda state, found: got.append((state, found)))
    assert checker.start() is True
    assert got == [(updates.NEWER, "9.9.9")]
    assert checker.busy is False


@pytest.mark.parametrize("answer", [
    lambda done: done(None, "HTTP 404"),  # репозиторий закрыт / нет релиза
    lambda done: done(None, "сеть: timeout"),  # таймаут запроса
    lambda done: done(None, "ответ не JSON"),  # битый JSON
])
def test_checker_network_failures_are_error(app, current, monkeypatch, answer):
    _mock_fetch(monkeypatch, answer)
    checker = updates.UpdateChecker()
    got = []
    checker.finished.connect(lambda state, found: got.append((state, found)))
    checker.start()
    assert got == [(updates.ERROR, "")]
    assert checker.busy is False


def test_checker_survives_transport_crash(app, current, monkeypatch):
    """Исключение из транспорта не выходит наружу — только состояние «ошибка»."""

    def boom(url, on_done):
        raise OSError("нет сети")

    monkeypatch.setattr(updates, "_fetch_json", boom)
    checker = updates.UpdateChecker()
    got = []
    checker.finished.connect(lambda state, found: got.append((state, found)))
    assert checker.start() is True
    assert got == [(updates.ERROR, "")]
    assert checker.busy is False


def test_checker_ignores_second_start_while_busy(app, current, monkeypatch):
    """Параллельных запросов нет: второй старт во время запроса — no-op."""
    calls = []
    monkeypatch.setattr(updates, "_fetch_json",
                        lambda url, on_done: calls.append(url))
    checker = updates.UpdateChecker()
    assert checker.start() is True
    assert checker.busy is True
    assert checker.start() is False
    assert len(calls) == 1


# --- карточка «О программе» --------------------------------------------------

def test_about_button_disables_and_runs_single_request(app, current, monkeypatch):
    pending = []
    monkeypatch.setattr(updates, "_fetch_json",
                        lambda url, on_done: pending.append(on_done))
    dlg = about.AboutDialog()
    try:
        dlg.check_button.click()
        assert dlg.check_button.isEnabled() is False
        assert dlg.check_button.text() == about.BUSY_TEXT
        dlg.check_button.click()  # повторный клик не запускает второй запрос
        assert len(pending) == 1
        assert dlg.result_row.isHidden()

        pending[0]({"tag_name": "v9.9.9"}, None)
        assert dlg.check_button.isEnabled() is True
        assert dlg.check_button.text() == about.CHECK_TEXT
        assert "9.9.9" in dlg.result_label.text()
        assert dlg.result_row.isHidden() is False
        assert dlg.download_button.isHidden() is False
    finally:
        dlg.close()


def test_about_download_opens_releases_page(app, current, monkeypatch):
    _mock_fetch(monkeypatch, lambda done: done({"tag_name": "v9.9.9"}, None))
    opened = _FakeDesktop()
    monkeypatch.setattr(about, "QDesktopServices", opened)
    dlg = about.AboutDialog()
    try:
        dlg.check_button.click()
        dlg.download_button.click()
        assert opened.urls == [updates.RELEASES_URL]
    finally:
        dlg.close()


@pytest.mark.parametrize("payload, expected", [
    ({"tag_name": "v0.3.2"}, about.ACTUAL_TEXT),
    ({"tag_name": "v0.1.0"}, about.ACTUAL_TEXT),
    (None, about.FAIL_TEXT),
])
def test_about_renders_result_states(app, current, monkeypatch, payload,
                                     expected):
    _mock_fetch(monkeypatch, lambda done: done(payload, None))
    dlg = about.AboutDialog()
    try:
        dlg.check_button.click()
        assert dlg.result_label.text() == expected
        assert dlg.download_button.isHidden() is True
    finally:
        dlg.close()


# --- тост из трея ------------------------------------------------------------

def _toast_spy(monkeypatch, shown):
    def fake(text, anchor, duration_ms=None, action_text=None):
        stub = _StubToast()
        shown.append((text, action_text))
        return stub

    monkeypatch.setattr(tray.toast_mod, "show_launch", fake)


def _tray_icon(app):
    return tray.TrayIcon(QIcon(), on_capture=lambda: None,
                         on_settings=lambda: None, on_quit=lambda: None)


@pytest.mark.parametrize("payload, expected", [
    ({"tag_name": "v9.9.9"}, ("Доступна версия 9.9.9", "Скачать")),
    ({"tag_name": "v0.3.2"}, ("У вас актуальная версия", None)),
    (None, ("Не удалось проверить — нет связи или GitHub недоступен", None)),
])
def test_tray_check_shows_toast(app, current, monkeypatch, payload, expected):
    _mock_fetch(monkeypatch, lambda done: done(payload, None))
    shown = []
    _toast_spy(monkeypatch, shown)
    icon = _tray_icon(app)
    action = next(item for item in icon.contextMenu().actions()
                  if item.text() == "Проверить обновления")
    action.trigger()
    assert shown == [expected]
