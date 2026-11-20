"""P0-тесты OCR (ТЗ DS-7, версия 0.3.0): ядро конвертации, выбор языка,
деградация движка, тосты и вес кнопки на обеих панелях.

Живой движок в unit-тестах не нужен: PyWinRT подменяется моками через
sys.modules (модули winrt.* подставляются целиком), распознавание — фейковым
OcrEngine. Живой прогон — dev/ocr_live.py на dev-машине и на собранной копии.
"""

import sys
import types
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication

import ocr
import panel as panel_mod
import theme
from overlay import CaptureOverlay

SELECTION = (10, 10, 400, 300)


# --- моки PyWinRT -----------------------------------------------------


class FakeBuffer(bytearray):
    """IBuffer: память доступна через memoryview, как у настоящего Buffer."""

    def __init__(self, capacity):
        super().__init__(capacity)
        self.capacity = capacity
        self.length = 0


class FakeLanguage:
    def __init__(self, tag):
        self.language_tag = tag


class FakeLine:
    def __init__(self, text):
        self.text = text


class FakeOcrResult:
    def __init__(self, text):
        self.text = text
        self.lines = [FakeLine(line) for line in text.split("\n")] if text else []


class FakeOperation:
    """IAsyncOperation: ждём через asyncio, результат — как у WinRT."""

    def __init__(self, result):
        self._result = result

    def __await__(self):
        if False:  # делает метод генератором, чтобы работал await
            yield
        return self._result


class FakeSoftwareBitmap:
    calls: ClassVar[list] = []  # (payload, format, width, height) последней конвертации

    def __init__(self, payload, width, height):
        self.payload = payload
        self.pixel_width = width
        self.pixel_height = height

    @classmethod
    def create_copy_from_buffer(cls, buffer, pixel_format, width, height):
        cls.calls.append((bytes(buffer), pixel_format, width, height))
        return cls(bytes(buffer), width, height)


class FakeOcrEngine:
    """Движок: язык, из которого создан, и строки результата."""

    available_recognizer_languages: ClassVar[list] = []  # «доступные в ОС» языки
    profile_engine: ClassVar = None  # что вернёт TryCreateFromUserProfileLanguages
    result_text: ClassVar[str] = ""
    created_with: ClassVar[list] = []

    @classmethod
    def reset(cls):
        cls.available_recognizer_languages = []
        cls.profile_engine = None
        cls.result_text = ""
        cls.created_with = []

    @classmethod
    def try_create_from_language(cls, language):
        cls.created_with.append(language.language_tag)
        if language.language_tag.startswith("ru"):
            return cls()
        return None

    @classmethod
    def try_create_from_user_profile_languages(cls):
        return cls.profile_engine

    def recognize_async(self, bitmap):
        return FakeOperation(FakeOcrResult(type(self).result_text))


@pytest.fixture
def fake_winrt(monkeypatch):
    """Подменить модули winrt.* целиком — живой движок не нужен."""
    imaging = types.ModuleType("winrt.windows.graphics.imaging")
    imaging.BitmapPixelFormat = types.SimpleNamespace(BGRA8="BGRA8")
    imaging.SoftwareBitmap = FakeSoftwareBitmap
    streams = types.ModuleType("winrt.windows.storage.streams")
    streams.Buffer = FakeBuffer
    media = types.ModuleType("winrt.windows.media.ocr")
    media.OcrEngine = FakeOcrEngine
    for name, module in (
        ("winrt.windows.graphics.imaging", imaging),
        ("winrt.windows.storage.streams", streams),
        ("winrt.windows.media.ocr", media),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    FakeSoftwareBitmap.calls = []
    FakeOcrEngine.reset()
    return types.SimpleNamespace(
        imaging=imaging, streams=streams, ocr=media, bitmap=FakeSoftwareBitmap,
        engine=FakeOcrEngine,
    )


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def overlay(qapp):
    """Оверлей без показа: снапшот, рамка выделения, финал без fade."""
    ov = CaptureOverlay()
    pm = QPixmap(800, 600)
    pm.fill(QColor(theme.BG))
    ov._snapshot = pm
    ov._screen = (0, 0, 800, 600)
    ov._snapshot_origin = QPoint(0, 0)
    ov._selection = SELECTION
    ov._finish = lambda: None
    yield ov
    ov.deleteLater()


# --- ядро конвертации QImage → SoftwareBitmap -------------------------


def test_software_bitmap_format_and_size(fake_winrt):
    image = QImage(120, 40, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#ffffff"))
    bitmap = ocr.to_software_bitmap(image)
    payload, pixel_format, width, height = fake_winrt.bitmap.calls[-1]
    assert pixel_format == "BGRA8"  # родной формат движка
    assert (width, height) == (120, 40)
    assert (bitmap.pixel_width, bitmap.pixel_height) == (120, 40)
    assert len(payload) == 120 * 40 * 4  # 4 байта на пиксель


def test_software_bitmap_keeps_pixels_and_source(fake_winrt):
    """Байты совпадают с пикселями кадра, исходный QImage не модифицирован."""
    image = QImage(4, 2, QImage.Format.Format_ARGB32_Premultiplied)
    image.setPixelColor(0, 0, QColor(255, 0, 0))
    image.setPixelColor(3, 1, QColor(0, 0, 255))
    before = image.constBits().tobytes()
    ocr.to_software_bitmap(image)
    payload = fake_winrt.bitmap.calls[-1][0]
    assert payload == before  # те же байты BGRA, без пересчёта
    assert image.constBits().tobytes() == before  # кадр не тронут
    assert image.pixelColor(0, 0) == QColor(255, 0, 0)


def test_software_bitmap_scales_over_engine_limit(fake_winrt):
    """Кадр больше предела движка ужимается, а не роняет распознавание."""
    image = QImage(ocr.MAX_SIDE + 100, 20, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#ffffff"))
    ocr.to_software_bitmap(ocr.fit_to_engine(image))
    assert fake_winrt.bitmap.calls[-1][2] == ocr.MAX_SIDE


# --- подготовка региона: поля и увеличение (репорт владельца 07.11) ----


def test_prepare_adds_white_margins_and_upscales():
    """Плотный кроп одной строки без полей движок не читает вовсе."""
    image = QImage(100, 20, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#101010"))
    prepared = ocr.prepare(image)
    assert (prepared.width(), prepared.height()) == (
        (100 + ocr.PAD * 2) * ocr.UPSCALE, (20 + ocr.PAD * 2) * ocr.UPSCALE)
    assert prepared.pixelColor(0, 0) == QColor("#ffffff")  # поля белые
    assert prepared.pixelColor(ocr.PAD * ocr.UPSCALE, ocr.PAD * ocr.UPSCALE) != QColor("#ffffff")


def test_prepare_keeps_big_region_unscaled():
    """Крупный регион читается и так — увеличение только тратит время."""
    image = QImage(1400, 900, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#ffffff"))
    assert image.width() * image.height() > ocr.UPSCALE_MAX_AREA
    prepared = ocr.prepare(image)
    assert (prepared.width(), prepared.height()) == (
        1400 + ocr.PAD * 2, 900 + ocr.PAD * 2)


# --- выбор языка движка ----------------------------------------------


def test_pick_language_prefers_russian():
    languages = [FakeLanguage("en-US"), FakeLanguage("ru")]
    assert ocr.pick_language(languages).language_tag == "ru"


def test_pick_language_accepts_regional_tag():
    languages = [FakeLanguage("en-US"), FakeLanguage("ru-RU")]
    assert ocr.pick_language(languages).language_tag == "ru-RU"


def test_pick_language_without_russian():
    assert ocr.pick_language([FakeLanguage("en-US")]) is None
    assert ocr.pick_language([]) is None


def test_create_engine_uses_russian(fake_winrt):
    fake_winrt.engine.available_recognizer_languages = [FakeLanguage("en-US"), FakeLanguage("ru")]
    ocr.create_engine()
    assert fake_winrt.engine.created_with == ["ru"]


def test_create_engine_falls_back_to_profile_languages(fake_winrt):
    fake_winrt.engine.available_recognizer_languages = [FakeLanguage("en-US")]
    fake_winrt.engine.profile_engine = fake_winrt.engine()
    assert ocr.create_engine() is fake_winrt.engine.profile_engine


def test_create_engine_unavailable_raises(fake_winrt):
    fake_winrt.engine.available_recognizer_languages = [FakeLanguage("en-US")]  # нет ни ru, ни профиля
    with pytest.raises(ocr.OcrUnavailableError):
        ocr.create_engine()


def test_create_engine_without_language_packs(fake_winrt, monkeypatch):
    """ОС без пакетов распознавания: чтение доступных языков бросает OSError."""

    class BrokenEngine:
        def __getattr__(self, name):
            if name == "available_recognizer_languages":
                raise OSError("нет WinRT")
            raise AttributeError(name)

    monkeypatch.setattr(fake_winrt.ocr, "OcrEngine", BrokenEngine())
    with pytest.raises(ocr.OcrUnavailableError):
        ocr.create_engine()


# --- распознавание и тексты тостов ------------------------------------


def test_recognize_returns_lines(fake_winrt):
    fake_winrt.engine.available_recognizer_languages = [FakeLanguage("ru")]
    fake_winrt.engine.result_text = "Первая строка\nВторая строка"
    image = QImage(80, 40, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#ffffff"))
    assert ocr.recognize(image) == "Первая строка\nВторая строка"


def test_recognize_empty_result(fake_winrt):
    fake_winrt.engine.available_recognizer_languages = [FakeLanguage("ru")]
    fake_winrt.engine.result_text = ""
    image = QImage(80, 40, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#ffffff"))
    assert ocr.recognize(image) == ""
    assert ocr.toast_text("") == "Текст не распознан"
    # движку уходит подготовленный кадр (поля + увеличение), а не сырой регион
    _, _, width, height = fake_winrt.bitmap.calls[-1]
    assert (width, height) == ((80 + ocr.PAD * 2) * ocr.UPSCALE,
                               (40 + ocr.PAD * 2) * ocr.UPSCALE)


def test_toast_text_counts_actual_characters():
    text = "Привет"
    assert ocr.toast_text(text) == f"Текст скопирован · {len(text)} символов"
    assert ocr.toast_text(text) == "Текст скопирован · 6 символов"


def test_ocr_failure_shows_toast_without_exception(overlay):
    """Деградация: движка нет — тост-ошибка, приложение живёт."""
    toasts = []
    overlay._show_toast = toasts.append
    overlay._on_ocr_failed("нет языковых пакетов")  # не бросает
    assert toasts == ["OCR недоступен: нет языковых пакетов"]


def test_ocr_success_copies_text_to_clipboard(overlay, qapp):
    overlay._show_toast = lambda text, *a: overlay.__dict__.setdefault(
        "_toasts", []).append(text)
    overlay._on_ocr_finished("Привет")
    assert QApplication.clipboard().text() == "Привет"
    assert overlay._toasts == ["Текст скопирован · 6 символов"]


# --- инструмент на холсте: регион, а не аннотация ---------------------


def _drag(overlay, tool, start, end):
    overlay._set_tool(None)
    overlay._set_tool(tool)
    assert overlay._press_inside(start)
    overlay._obj_drag_move(end)
    overlay._obj_drag_release(overlay._drag_mode, end)


def test_ocr_region_goes_to_worker_without_annotation(overlay):
    started = []
    overlay._ocr.start = lambda image: started.append(image)
    _drag(overlay, "ocr", (50, 50), (250, 140))
    assert overlay._objects == []  # разметка не создаётся
    assert overlay._history.undo([]) is None  # undo-стек пуст
    assert len(started) == 1
    assert (started[0].width(), started[0].height()) == (200, 90)


def test_ocr_tiny_region_cancelled_silently(overlay):
    started = []
    toasts = []
    overlay._ocr.start = lambda image: started.append(image)
    overlay._show_toast = toasts.append
    _drag(overlay, "ocr", (50, 50), (55, 55))  # 5×5 — мусорный drag
    assert started == []  # распознавание не запускалось
    assert toasts == []  # и тоста нет


def test_ocr_region_in_pin_window_uses_frame_coords(overlay):
    """Пин-окно: регион считается в координатах кадра сквозь зум (ТЗ: «то же»)."""
    from pin import PinWindow

    window = PinWindow(overlay)
    window._zoom = 0.5  # кадр показан вдвое мельче вьюпорта
    window._offset = (0.0, 0.0)
    window._header_h = 0
    started = []
    window._ocr.start = lambda image: started.append(image)
    window._set_tool("ocr")
    assert window._press_inside((60, 60))  # вьюпорт → кадр (120, 120)
    window._obj_drag_move((160, 110))  # вьюпорт → кадр (320, 220)
    window._obj_drag_release(window._drag_mode, (160, 110))
    assert len(started) == 1
    assert (started[0].width(), started[0].height()) == (200, 100)  # 200×100 кадра
    window.deleteLater()


# --- кнопка OCR на обеих панелях --------------------------------------


def test_ocr_button_normal_weight_both_panels(qapp):
    for panel in (panel_mod.ToolbarPanel(None), panel_mod.PinPanel(None)):
        button = panel.button("ocr")
        assert button.width() == panel_mod._BTN, type(panel).__name__
        assert button.height() == panel_mod._BTN
        assert not getattr(button, "_dimmed", False)  # заглушки больше нет
        assert not button._ghost and not button._accent
        assert "локально, без облака" in button.toolTip()
        panel.set_active_tool("ocr")
        assert button._active  # инструмент подсвечивается, как прочие
