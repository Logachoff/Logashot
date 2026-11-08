"""Проверка репозитория на типичные утёкшие секреты.

Сканирует текстовые файлы проекта (src/, dev/, tests/, scripts/, assets/)
и ищет паттерны: API-ключи, токены, пароли, приватные ключи, секретные
JWT. Бинарные файлы и папки сборки пропускаются.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {"build", "dist", "__pycache__", ".git", ".venv", "venv", "node_modules"}
SKIP_EXTS = {".exe", ".dll", ".pyd", ".ico", ".png", ".jpg", ".zip", ".7z"}

PATTERNS = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private key", re.compile(r"-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}")),
    ("generic API key", re.compile(r"\b(api[_-]?key|apikey)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}", re.IGNORECASE)),
    ("generic secret", re.compile(r"\b(secret|password|passwd|pwd)\s*[:=]\s*['\"]?[A-Za-z0-9_!@#$%^&*\-]{8,}", re.IGNORECASE)),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_\-]*\.eyJ[A-Za-z0-9_\-]*\.[A-Za-z0-9_\-]*")),
]


def scan():
    hits = []
    for path in ROOT.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix.lower() in SKIP_EXTS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS:
            for match in pattern.finditer(text):
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                snippet = text[start:end].replace("\n", " ")
                hits.append((path.relative_to(ROOT), label, snippet))

    if hits:
        print("Найдены совпадения (требуется ручная проверка):")
        for file, label, snippet in hits:
            print(f"  {file} [{label}]: ...{snippet}...")
        return 1
    print("Секреты не обнаружены.")
    return 0


if __name__ == "__main__":
    sys.exit(scan())
