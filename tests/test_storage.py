"""P0-тесты ядра сохранения: маска имени, счётчик без коллизий,
пресеты масштаба 100/75/50 и их применение к сохраняемому файлу."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

import storage

NOW = datetime(2026, 10, 16, 15, 3, 7)


# --- маска имени ---

def test_file_name_mask():
    assert storage.file_name(NOW, 1) == "LogaShot_2026-10-16_15-03-07_001.png"


def test_file_name_counter_padding():
    assert storage.file_name(NOW, 7) == "LogaShot_2026-10-16_15-03-07_007.png"
    assert storage.file_name(NOW, 123) == "LogaShot_2026-10-16_15-03-07_123.png"


def test_file_name_counter_starts_at_1():
    with pytest.raises(ValueError):
        storage.file_name(NOW, 0)


def test_shot_dir_under_pictures():
    assert storage.shot_dir(Path("/home/u")) == Path("/home/u/Pictures/LogaShot")


# --- счётчик без коллизий ---

def test_next_counter_empty_dir():
    assert storage.next_counter([], NOW) == 1


def test_next_counter_same_second_no_collision():
    # два сохранения в одну секунду: второе не затирает первое (Ctrl+S)
    names = ["LogaShot_2026-10-16_15-03-07_001.png"]
    assert storage.next_counter(names, NOW) == 2


def test_next_counter_fills_gap():
    names = [
        "LogaShot_2026-10-16_15-03-07_001.png",
        "LogaShot_2026-10-16_15-03-07_003.png",
    ]
    assert storage.next_counter(names, NOW) == 2


def test_next_counter_ignores_other_files():
    names = [
        "LogaShot_2026-10-16_15-03-08_009.png",  # другая секунда
        "LogaShot_2026-10-16_15-03-07_abc.png",  # не счётчик
        "чужой_файл.png",
        "LogaShot_2026-10-16_15-03-07_005.jpg",  # не png
    ]
    assert storage.next_counter(names, NOW) == 1


def test_two_saves_same_second_on_disk(tmp_path):
    # интеграция с реальной папкой: два файла подряд — разные имена, оба на диске
    for expected in ("001", "002"):
        counter = storage.next_counter((p.name for p in tmp_path.iterdir()), NOW)
        name = storage.file_name(NOW, counter)
        assert name.endswith(f"_{expected}.png")
        (tmp_path / name).write_bytes(b"png")
    assert len(list(tmp_path.iterdir())) == 2


# --- пресеты масштаба ---

def test_scale_size_presets():
    assert storage.scale_size((200, 100), 100) == (200, 100)
    assert storage.scale_size((200, 100), 75) == (150, 75)
    assert storage.scale_size((200, 100), 50) == (100, 50)


def test_scale_size_rounding_and_minimum():
    assert storage.scale_size((101, 51), 50) == (51, 26)  # половина округляется вверх
    assert storage.scale_size((1, 1), 50) == (1, 1)  # минимум 1 px


def test_scale_size_unknown_preset_fails_fast():
    with pytest.raises(ValueError):
        storage.scale_size((200, 100), 90)


def test_preset_applied_to_saved_file(tmp_path):
    # сквозная проверка: пресет реально меняет размер сохранённого PNG
    from PySide6.QtGui import QImage

    image = QImage(200, 100, QImage.Format.Format_ARGB32)
    image.fill(0xFF3D5AFE)
    w, h = storage.scale_size((image.width(), image.height()), 50)
    path = tmp_path / storage.file_name(NOW, 1)
    assert image.scaled(w, h).save(str(path), "PNG")
    reloaded = QImage(str(path))
    assert (reloaded.width(), reloaded.height()) == (100, 50)
