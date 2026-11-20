"""«В почту»: письмо с вложением кадра в системном почтовом
клиенте. pywin32 из белого списка зависимостей заявлен ровно на это.

Два пути, оба локальные:
1. Outlook COM через pywin32 (классический Outlook) — Dispatch +
   CreateItem + Display, письмо открывается черновиком.
2. Simple MAPI (MAPISendMail из mapi32) — системный клиент по умолчанию;
   ctypes — стандартная библиотека, новых зависимостей нет.

Оба не сработали (клиента нет / новый Outlook наружу письма не отдаёт) —
MailUnavailableError, вызывающий показывает тост по гайду тона.
"""

import ctypes
import os
import threading
from ctypes import wintypes
from pathlib import Path

SUBJECT = "Скриншот LogaShot"
_TIMEOUT_COM = 2.0   # c Outlook COM
_TIMEOUT_MAPI = 5.0  # на открытие диалога Simple MAPI


class MailUnavailableError(RuntimeError):
    """Ни один почтовый путь не доступен на этой машине."""


class MailTimeoutError(MailUnavailableError):
    """MAPI/COM не ответил за таймаут (зависающий клиент)."""


def _call_with_timeout(func, args, timeout):
    """Вызвать func в потоке с таймаутом; timeout — MailTimeoutError.

    COM/MAPI вызываем из фонового потока, чтобы зависание клиента (у тестера
    «Ворис 1» приложение падало) не блокировало UI-поток.
    """
    box = {}

    def target():
        try:
            func(*args)
            box["ok"] = True
        except Exception as exc:  # noqa: BLE001 — COM/MAPI бросают что угодно
            box["err"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise MailTimeoutError(f"{func.__name__} не ответил за {timeout} с")
    if "err" in box:
        raise box["err"]


def send_mail(attachment: Path):
    """Открыть черновик письма с вложением; не вышло — MailUnavailableError.

    Каждый путь (COM, MAPI) бросает что угодно: com_error при отсутствии
    Outlook, OSError при отсутствии mapi32, результат вызова... Ловим всё —
    иначе необработанное исключение уходило в слот и кнопка «молчала»
    (Outlook не установлен, до Simple MAPI дело не доходило).
    """
    if not attachment.exists():
        raise ValueError(f"вложение не найдено: {attachment}")
    errors = []
    for sender, timeout in (
        (_send_outlook_com, _TIMEOUT_COM),
        (_send_simple_mapi, _TIMEOUT_MAPI),
    ):
        try:
            _call_with_timeout(sender, (attachment,), timeout)
            return
        except Exception as exc:  # noqa: BLE001 — сендеры бросают что угодно
            errors.append(exc)
    raise MailUnavailableError("почтовый клиент недоступен") from errors[-1]


def _send_outlook_com(attachment: Path):
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()  # вызываем из GUI-потока — COM должен знать
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)  # 0 = olMailItem
    mail.Subject = SUBJECT
    mail.Attachments.Add(str(attachment))
    mail.Display()  # модальный черновик; отправка — руками пользователя


# --- Simple MAPI через ctypes (клиент по умолчанию) ---

_MAPI_LOGON_UI = 0x00000001
_MAPI_DIALOG = 0x00000008


class _MapiFileDesc(ctypes.Structure):
    _fields_ = [
        ("ulReserved", wintypes.ULONG),
        ("flFlags", wintypes.ULONG),
        ("nPosition", wintypes.ULONG),
        ("lpszPathName", ctypes.c_char_p),
        ("lpszFileName", ctypes.c_char_p),
        ("lpFileType", ctypes.c_void_p),
    ]


class _MapiMessage(ctypes.Structure):
    _fields_ = [
        ("ulReserved", wintypes.ULONG),
        ("lpszSubject", ctypes.c_char_p),
        ("lpszNoteText", ctypes.c_char_p),
        ("lpszMessageType", ctypes.c_char_p),
        ("lpszDateReceived", ctypes.c_char_p),
        ("lpszConversationID", ctypes.c_char_p),
        ("flFlags", wintypes.ULONG),
        ("lpOriginator", ctypes.c_void_p),
        ("nRecipCount", wintypes.ULONG),
        ("lpRecips", ctypes.c_void_p),
        ("nFileCount", wintypes.ULONG),
        ("lpFiles", ctypes.POINTER(_MapiFileDesc)),
    ]


def _send_simple_mapi(attachment: Path):
    desc = _MapiFileDesc(
        ulReserved=0,
        flFlags=0,
        nPosition=0xFFFFFFFF,  # -1: позиция в теле не задана
        lpszPathName=os.fsencode(str(attachment)),
        lpszFileName=os.fsencode(attachment.name),
        lpFileType=None,
    )
    message = _MapiMessage(
        ulReserved=0,
        lpszSubject=SUBJECT.encode("mbcs", errors="replace"),
        lpszNoteText=None,
        lpszMessageType=None,
        lpszDateReceived=None,
        lpszConversationID=None,
        flFlags=0,
        lpOriginator=None,
        nRecipCount=0,
        lpRecips=None,
        nFileCount=1,
        lpFiles=ctypes.pointer(desc),
    )
    mapi32 = ctypes.windll.mapi32  # нет DLL — здесь и упадёт в fallback
    # parent=0 (окна-родителя нет), UI разрешён: клиент покажет черновик
    result = mapi32.MAPISendMail(
        0, 0, ctypes.byref(message), _MAPI_DIALOG | _MAPI_LOGON_UI, 0
    )
    if result != 0:  # SUCCESS_SUCCESS; 1 = пользователь отменил — тоже ок
        if result == 1:  # MAPI_USER_ABORT: черновик закрыли — не ошибка
            return
        raise MailUnavailableError(f"MAPISendMail вернул {result}")
