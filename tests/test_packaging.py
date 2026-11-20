"""Статическая проверка установщика: маркер portable не должен ставиться.

Тест держит корневую причину бага: dev/build.py оставляет `portable` в
dist\\LogaShot, [Files] копирует папку целиком — установленная копия
попадала в portable-режим и теряла настройки в Program Files.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUP_ISS = ROOT / "scripts" / "setup.iss"
VERSION_FILE = ROOT / "dev" / "version_file.txt"

sys.path.insert(0, str(ROOT / "src"))

import version as version_mod


def _section(text, name):
    """Тело секции [name] Inno-скрипта без строк-комментариев."""
    body, inside = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            inside = stripped == f"[{name}]"
            continue
        if inside and stripped and not stripped.startswith(";"):
            body.append(stripped)
    return "\n".join(body)


def test_installer_excludes_portable_marker():
    text = SETUP_ISS.read_text(encoding="utf-8")
    assert 'Excludes: "portable,settings.ini"' in _section(text, "Files")


def test_installer_removes_leftover_portable_marker():
    delete = _section(SETUP_ISS.read_text(encoding="utf-8"), "InstallDelete")
    assert "{app}\\portable" in delete
    assert "{app}\\settings.ini" in delete


def test_installer_version_matches_version_file():
    text = SETUP_ISS.read_text(encoding="utf-8")
    setup_version = re.search(r'#define AppVersion\s+"([\d.]+)"', text).group(1)
    assert f"OutputBaseFilename=LogaShot_{setup_version}_setup" in text
    version = VERSION_FILE.read_text(encoding="utf-8")
    nums = re.search(r"filevers=\(([^)]+)\)", version).group(1).split(",")
    assert ".".join(n.strip() for n in nums[:3]) == setup_version


def test_version_single_source_matches_artifacts():
    """VERSION из src/version.py — тот же, что в артефактах сборки (v0.2)."""
    text = SETUP_ISS.read_text(encoding="utf-8")
    setup_version = re.search(r'#define AppVersion\s+"([\d.]+)"', text).group(1)
    assert setup_version == version_mod.VERSION
    assert f"LogaShot_{version_mod.VERSION}_setup" in text

    version = VERSION_FILE.read_text(encoding="utf-8")
    nums = re.search(r"filevers=\(([^)]+)\)", version).group(1).split(",")
    assert ".".join(n.strip() for n in nums[:3]) == version_mod.VERSION
    assert f"FileVersion', u'{version_mod.VERSION}.0'" in version
