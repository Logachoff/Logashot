"""P0: логика single-instance через именованный мьютекс."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from single_instance import SingleInstanceGuard, acquire_mutex, release_mutex


def test_acquire_returns_handle_for_unique_name():
    name = f"LogaShot_Test_{uuid.uuid4()}"
    handle = acquire_mutex(name)
    assert handle is not None
    release_mutex(handle)


def test_second_instance_detects_first():
    name = f"LogaShot_Test_{uuid.uuid4()}"
    first = acquire_mutex(name)
    assert first is not None
    try:
        second = acquire_mutex(name)
        assert second is None
    finally:
        release_mutex(first)


def test_guard_context_manager_detects_another():
    name = f"LogaShot_Test_{uuid.uuid4()}"
    with SingleInstanceGuard(name) as g1:
        assert not g1.is_another_running
        with SingleInstanceGuard(name) as g2:
            assert g2.is_another_running
