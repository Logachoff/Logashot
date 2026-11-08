"""Чистое ядро undo/redo — без Qt, под P0-тесты.

Стек 10 шагов: добавление/удаление аннотаций и все правки
объектов отменяемы. Механика — мементо: перед каждой правкой вызывающий
кладёт в стек снапшот списка объектов (deepcopy делает он же), undo/redo
возвращают снапшоты, текущее состояние при переходе отдаётся на хранение
в противоположный стек.
"""

LIMIT = 10  # глубина стека отмены


class History:
    """Пара стеков undo/redo с границей LIMIT на глубину отмены."""

    def __init__(self, limit=LIMIT):
        self._limit = limit
        self._undo = []  # снапшоты «как было», последний — ближайший
        self._redo = []  # снапшоты «как стало» после отмены

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def push(self, state):
        """Запомнить состояние перед правкой; redo при этом сгорает."""
        self._undo.append(state)
        if len(self._undo) > self._limit:
            self._undo.pop(0)  # граница стека: самый старый шаг выбывает
        self._redo.clear()

    def undo(self, current):
        """Шаг назад: отдать последний снапшот, текущее — в redo.

        Пустой стек — None (клик по ↩ бездействует, как Ctrl+Z).
        """
        if not self._undo:
            return None
        self._redo.append(current)
        return self._undo.pop()

    def redo(self, current):
        """Шаг вперёд: вернуть отменённое, текущее — обратно в undo."""
        if not self._redo:
            return None
        self._undo.append(current)
        return self._redo.pop()
