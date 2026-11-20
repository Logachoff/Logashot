"""P1: «В почту» не зависает без MAPI (баг 2 dogfooding)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mailer


def test_call_with_timeout_success():
    called = []
    mailer._call_with_timeout(lambda a: called.append(a), ("x",), 1.0)
    assert called == ["x"]


def test_call_with_timeout_propagates_error():
    def boom():
        raise RuntimeError("нет MAPI")
    try:
        mailer._call_with_timeout(boom, (), 1.0)
        assert False, "должно было упасть"
    except RuntimeError as exc:
        assert "нет MAPI" in str(exc)


def test_call_with_timeout_hang():
    def hang():
        time.sleep(5)
    t0 = time.perf_counter()
    try:
        mailer._call_with_timeout(hang, (), 0.1)
        assert False, "должно было сработать по таймауту"
    except mailer.MailTimeoutError:
        pass
    assert time.perf_counter() - t0 < 2.0  # не ждали 5 с


def test_send_mail_without_attachment():
    try:
        mailer.send_mail(Path("нет-такого-файла.png"))
        assert False
    except ValueError:
        pass


def test_send_mail_com_error_falls_through_to_mapi(tmp_path, monkeypatch):
    """Регрессия бага 24.10: Outlook не установлен — Dispatch бросает
    com_error (НЕ MailUnavailableError). send_mail обязана поймать его
    и дойти до Simple MAPI, а не упасть молча."""
    file = tmp_path / "shot.png"
    file.write_bytes(b"png")
    mapi_calls = []

    def fake_com(attachment):
        raise RuntimeError("(-2147221005, неверный синтаксис в имени класса)")

    def fake_mapi(attachment):
        mapi_calls.append(attachment)

    monkeypatch.setattr(mailer, "_send_outlook_com", fake_com)
    monkeypatch.setattr(mailer, "_send_simple_mapi", fake_mapi)
    mailer.send_mail(file)  # не падает
    assert mapi_calls == [file]  # до MAPI дошли


def test_send_mail_all_paths_fail_raise_unavailable(tmp_path, monkeypatch):
    file = tmp_path / "shot.png"
    file.write_bytes(b"png")

    def fake_com(attachment):
        raise RuntimeError("com_error")

    def fake_mapi(attachment):
        raise mailer.MailUnavailableError("нет MAPI-клиента")

    monkeypatch.setattr(mailer, "_send_outlook_com", fake_com)
    monkeypatch.setattr(mailer, "_send_simple_mapi", fake_mapi)
    try:
        mailer.send_mail(file)
        assert False, "должно быть MailUnavailableError"
    except mailer.MailUnavailableError as exc:
        assert "почтовый клиент недоступен" in str(exc)
