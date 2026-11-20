"""OCR локально (бэклог п.2, версия 0.3.0): выделил область → текст в буфере.

Движок — Windows.Media.Ocr: встроен в Win10/11, работает офлайн, русский
язык в комплекте ОС (на нём же Text Extractor в PowerToys). Из Python —
PyWinRT (MIT). Приложение никуда не ходит: кадр не покидает машину — это
жёсткая граница продукта (решение 11.10).

Механика: QImage региона → поля и увеличение (prepare) → SoftwareBitmap
(BGRA8, Premultiplied) → OcrEngine (ru → языки профиля → первый доступный) →
текст построчно. WinRT-асинхронность ждём в фоновом потоке (OcrWorker,
механика mailer.py): UI не блокируется, результат приходит сигналом
в GUI-поток.

Движок недоступен (нет языковых пакетов, ОС без WinRT) — OcrUnavailableError,
вызывающий показывает тост-ошибку; приложение не падает.
"""

import asyncio
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter

LANGUAGE_TAG = "ru"  # предпочитаемый язык: русский текст в комплекте ОС
MAX_SIDE = 10000  # предел стороны кадра у движка (OcrEngine.max_image_dimension)
PAD = 12  # белые поля вокруг региона, px: движок отбрасывает текст у края
UPSCALE = 2  # увеличение мелкого шрифта (14 px и меньше читается точнее)
UPSCALE_MAX_AREA = 1_000_000  # регион крупнее мегапикселя уже читается без увеличения


class OcrUnavailableError(RuntimeError):
    """Движок распознавания недоступен на этой машине."""


def pick_language(languages, tag=LANGUAGE_TAG):
    """Язык движка из доступных: сначала точный тег, затем его варианты.

    Доступные языки отдаёт сама ОС (например, "en-US" и "ru"); нужен
    объект Language — OcrEngine принимает только его, не строку.
    """
    wanted = tag.lower()
    for language in languages:
        if language.language_tag.lower() == wanted:
            return language
    for language in languages:
        if language.language_tag.lower().startswith(wanted + "-"):
            return language
    return None


def text_of(result):
    """Текст результата распознавания построчно: абзац переносится как есть.

    result.text — сплошная строка через пробел; переносы строк в ней теряются,
    а скопированный абзац должен читаться так же, как в оригинале.
    """
    lines = [line.text for line in result.lines if line.text]
    return "\n".join(lines) if lines else (result.text or "")


def toast_text(text):
    """Тост по результату (гайд тона): успех — с числом символов."""
    if not text:
        return "Текст не распознан"
    return f"Текст скопирован · {len(text)} символов"


def create_engine():
    """Движок распознавания: ru → языки профиля → первый доступный."""
    from winrt.windows.media.ocr import OcrEngine

    try:
        languages = list(OcrEngine.available_recognizer_languages)
    except OSError as exc:  # WinRT без пакетов распознавания — тоже сюда
        raise OcrUnavailableError(f"Windows.Media.Ocr недоступен: {exc}") from exc
    language = pick_language(languages)
    if language is not None:
        engine = OcrEngine.try_create_from_language(language)
        if engine is not None:
            return engine
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is not None:
        return engine
    for language in languages:
        engine = OcrEngine.try_create_from_language(language)
        if engine is not None:
            return engine
    raise OcrUnavailableError("нет языковых пакетов распознавания")


def fit_to_engine(image):
    """Уменьшить кадр до предела движка (огромное выделение — не ошибка)."""
    side = max(image.width(), image.height())
    if side <= MAX_SIDE:
        return image
    ratio = MAX_SIDE / side
    return image.scaled(round(image.width() * ratio), round(image.height() * ratio))


def prepare(image):
    """Кадр региона для движка: белые поля и увеличение мелкого шрифта.

    Windows OCR отбрасывает строки, прижатые к краю кадра: одиночная строка
    с шапкой таблицы (14 px, поля 3–6 px) не распознавалась вовсе — тост
    «Текст не распознан» (репорт владельца 07.11). Поля 12 px это лечат,
    а увеличение вдвое помогает мелкому шрифту: на том же кадре «и» и
    заглавные читаются верно. Поля белые — движок бинаризует сам, тема
    (светлая/тёмная/цветная плашка) на результат не влияет.
    """
    padded = QImage(image.width() + PAD * 2, image.height() + PAD * 2,
                    QImage.Format.Format_ARGB32_Premultiplied)
    padded.fill(QColor("#ffffff"))
    painter = QPainter(padded)
    painter.drawImage(PAD, PAD, image)
    painter.end()
    if image.width() * image.height() > UPSCALE_MAX_AREA:
        return padded  # крупный регион читается и так, увеличение — только время
    return padded.scaled(
        padded.width() * UPSCALE, padded.height() * UPSCALE,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def to_software_bitmap(image):
    """QImage → SoftwareBitmap BGRA8/Premultiplied; пиксели кадра не меняются.

    BGRA8888 — родной формат OCR-движка (и памяти QImage ARGB32 на little-endian),
    поэтому конвертация без пересчёта каналов. Данные копируем в IBuffer:
    SoftwareBitmap не должен делить память с QImage, который живёт в GUI-потоке.
    """
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import Buffer

    bgra = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    data = bgra.constBits().tobytes()
    buffer = Buffer(len(data))
    buffer.length = len(data)  # memoryview видит длину, заданную ДО его создания
    memoryview(buffer)[:] = data
    return SoftwareBitmap.create_copy_from_buffer(
        buffer, BitmapPixelFormat.BGRA8, bgra.width(), bgra.height()
    )


def recognize(image):
    """Распознать текст на кадре (вызывать из фонового потока).

    OcrUnavailableError — движка нет; прочие ошибки WinRT пробрасываются
    как есть (вызывающий показывает тост, ничего не глотаем молча).
    """
    engine = create_engine()
    bitmap = to_software_bitmap(fit_to_engine(prepare(image)))

    # get_results() первого же вызова падает в PyWinRT с REGDB_E_CLASSNOTREG,
    # поэтому WinRT-операцию именно ждём — через asyncio (проверено вживую).
    async def _wait():
        return await engine.recognize_async(bitmap)

    return text_of(asyncio.run(_wait()))


class OcrWorker(QObject):
    """Распознавание в фоновом потоке: результат — сигналом в GUI-поток.

    Живёт в GUI-потоке, поэтому сигналы из рабочего потока приходят
    в очередь событий — как с тостом запуска: UI не блокируется.
    """

    finished = Signal(str)  # распознанный текст (может быть пустым)
    failed = Signal(str)  # причина: тост «OCR недоступен: …»

    def start(self, image):
        """Запустить распознавание кадра (кадр — копия региона из снапшота)."""
        threading.Thread(target=self._run, args=(image,), daemon=True).start()

    def _run(self, image):
        try:
            text = recognize(image)
        except Exception as exc:  # noqa: BLE001 — WinRT бросает что угодно
            self.failed.emit(str(exc))
            return
        self.finished.emit(text)
