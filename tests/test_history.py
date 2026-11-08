"""P0: стек undo/redo — размещение/правка/удаление, граница 10."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from history import History


def test_empty_stack_undo_returns_none():
    h = History()
    assert not h.can_undo
    assert h.undo([]) is None  # клик по ↩ при пустом стеке бездействует


def test_add_object_undoable():
    h = History()
    h.push([])  # состояние до размещения
    state = h.undo([{"type": "num"}])
    assert state == []
    assert h.can_redo


def test_redo_restores_after_undo():
    h = History()
    h.push([])
    current = h.undo([{"type": "num"}])
    restored = h.redo(current)
    assert restored == [{"type": "num"}]
    assert not h.can_redo


def test_edit_and_delete_steps():
    h = History()
    h.push([])  # до добавления
    h.push([{"type": "num", "value": 1}])  # до правки
    after_edit = h.undo([{"type": "num", "value": 2}])
    assert after_edit == [{"type": "num", "value": 1}]
    empty = h.undo(after_edit)
    assert empty == []
    assert h.undo(empty) is None  # глубина исчерпана


def test_new_push_burns_redo():
    h = History()
    h.push([])
    h.undo([1])
    assert h.can_redo
    h.push([2])  # новая правка — redo-ветка сгорает
    assert not h.can_redo


def test_limit_drops_oldest():
    h = History(limit=10)
    for i in range(11):  # 11 правок при границе 10
        h.push([i])
    undone = 0
    state = ["current"]
    while True:
        state = h.undo(state)
        if state is None:
            break
        undone += 1
    assert undone == 10  # ровно 10 шагов назад, одиннадцатый выбыл


def test_limit_keeps_newest():
    h = History(limit=3)
    for i in range(5):
        h.push([i])
    assert h.undo(["now"]) == [4]  # свежайший снапшот наверху
