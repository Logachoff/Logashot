"""Проверка обновлений по GitHub Releases (0.4.0).

Запрос уходит только по действию пользователя — кнопкой в «О программе» или
пунктом меню трея. Ни на старте, ни по таймеру, ни при открытии карточки сеть
не трогается: единственный путь — `UpdateChecker.start()` из обработчика клика.

HTTP — QtNetwork (`QNetworkAccessManager`): запрос асинхронный, GUI-поток не
блокируется; таймаут (~10 с) — `QTimer`, который обрывает запрос. Ответ живёт
только в этом запросе: ни кеша, ни состояния между запусками, ни записи в
настройки.

Пользователю показываем одно из трёх состояний; код и текст ошибки — только
в stderr, не в интерфейс.
"""

import json
import sys

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)

import version

API_URL = "https://api.github.com/repos/Logachoff/Logashot/releases/latest"
RELEASES_URL = "https://github.com/Logachoff/Logashot/releases/latest"
TIMEOUT_MS = 10_000

NEWER = "newer"  # на GitHub свежее: предлагаем скачать
ACTUAL = "actual"  # та же или старше — форк/сборка впереди релиза
ERROR = "error"  # нет связи, таймаут, приватный репозиторий, битый JSON

_MAX_PARTS = 4  # 0.4, 0.4.0, 0.4.0.1 — больше похоже на мусор


def parse_version(tag):
    """Тег релиза → кортеж чисел: 'v0.4.0' → (0, 4, 0).

    Префикс `v` и суффикс сборки (`-beta`, `+meta`) отбрасываются. Не строка,
    пустой или нечисловой тег → None: это дефект данных, а не исключение.
    """
    if not isinstance(tag, str):
        return None
    text = tag.strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    for separator in ("-", "+"):
        text = text.split(separator, 1)[0]
    parts = text.split(".")
    if not 1 <= len(parts) <= _MAX_PARTS:
        return None
    if not all(part.isascii() and part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_newer(remote, current):
    """remote строго свежее current? 0.4 и 0.4.0 — одна версия."""
    size = max(len(remote), len(current))
    remote_full = tuple(remote) + (0,) * (size - len(remote))
    current_full = tuple(current) + (0,) * (size - len(current))
    return remote_full > current_full


def current_version():
    """Версия приложения из version.py — кортежем (None, если строка битая)."""
    return parse_version(version.VERSION)


def interpret(payload):
    """JSON релиза → (состояние, «X.Y.Z»). Любой дефект данных — ERROR.

    Из ответа нужен только `tag_name`; ссылку на страницу релизов знаем сами,
    поэтому остальные поля не разбираем.
    """
    if not isinstance(payload, dict):
        return ERROR, ""
    remote = parse_version(payload.get("tag_name"))
    local = current_version()
    if remote is None or local is None:
        return ERROR, ""
    text = ".".join(str(part) for part in remote)
    return (NEWER if is_newer(remote, local) else ACTUAL), text


_MANAGER = None  # один менеджер на процесс, создаётся при первом клике


def _manager():
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = QNetworkAccessManager()
    return _MANAGER


def _request(url):
    request = QNetworkRequest(QUrl(url))
    request.setRawHeader(b"Accept", b"application/vnd.github+json")
    # без User-Agent GitHub отвечает 403 даже на публичный репозиторий
    request.setRawHeader(b"User-Agent", f"LogaShot-{version.VERSION}".encode())
    return request


def _fetch_json(url, on_done):
    """GET JSON асинхронно: `on_done(payload | None, причина | None)`.

    Единственное место в приложении, где дёргается сеть. Тесты подменяют эту
    функцию целиком и по-настоящему в сеть не ходят. Сбой сети, таймаут и
    битый JSON сходятся в `None`: пользователю достаточно факта «не удалось»,
    причина уходит в stderr.
    """
    reply = _manager().get(_request(url))
    timer = QTimer(reply)  # живёт вместе с ответом
    timer.setSingleShot(True)
    timer.timeout.connect(reply.abort)
    timer.start(TIMEOUT_MS)

    def _finish():
        timer.stop()
        payload, reason = None, None
        status = reply.attribute(
            QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reason = f"сеть: {reply.errorString()}"
        elif status != 200:
            reason = f"HTTP {status}"
        else:
            try:
                payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                reason = "ответ не JSON"
        reply.deleteLater()
        on_done(payload, reason)

    reply.finished.connect(_finish)


class UpdateChecker(QObject):
    """Одна проверка за раз: повторный старт во время запроса игнорируется."""

    finished = Signal(str, str)  # состояние, версия ("0.4.0" или "")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False

    @property
    def busy(self):
        return self._busy

    def start(self):
        """Запустить проверку. True — запрос ушёл, False — уже идёт."""
        if self._busy:
            return False
        self._busy = True
        try:
            _fetch_json(API_URL, self._on_done)
        except Exception as exc:  # noqa: BLE001 — сбой сети = «не удалось»
            self._report(ERROR, "", f"запрос не ушёл: {exc}")
        return True

    def _on_done(self, payload, reason):
        if not self._busy:
            return
        try:
            state, found = interpret(payload)
        except Exception as exc:  # noqa: BLE001 — данные приходят любые
            self._report(ERROR, "", f"разбор ответа: {exc}")
            return
        self._report(state, found, reason)

    def _report(self, state, found, reason=None):
        self._busy = False
        if reason:
            print(f"Проверка обновлений: {reason}", file=sys.stderr)
        self.finished.emit(state, found)
