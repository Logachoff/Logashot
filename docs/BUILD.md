# Сборка LogaShot

Два артефакта: portable-папка (`dist\LogaShot\`) и установщик (`dist\LogaShot_<версия>_setup.exe`).
Установщик собирается из готовой portable-папки.

## Что нужно

- Windows 10 1809 или новее (на Windows 7/8 не запустится рантайм Python и WinRT).
- Python 3.11+ (разработка — на 3.14).
- Зависимости проекта и PyInstaller:

  ```cmd
  pip install -r requirements.txt pyinstaller
  ```

- [Inno Setup](https://jrsoftware.org/isinfo.php) 6.x или 7.x — только для установщика.
- UPX — по желанию: если найден в `PATH`, PyInstaller сожмёт бинарники, иначе сборка пройдёт без него.

## 1. Portable-сборка

```cmd
python dev\build.py
```

Скрипт:

1. проверяет иконку (`assets\LogaShot.ico`) и файл версии (`dev\version_file.txt`);
2. запускает PyInstaller в режиме `--onedir --windowed`, кладёт `assets\` внутрь сборки,
   подключает хук `dev\hooks\hook-winrt.py`, добавляет таблицы типов WinRT как данные
   (без них не работает OCR) и исключает неиспользуемые модули Qt;
3. удаляет из `_internal` файлы, которые PyInstaller тащит зря: QML, сеть, PDF,
   OpenGL-software, лишние imageformats, переводы Qt;
4. кладёт маркер `portable` — с ним настройки пишутся в `settings.ini` рядом с exe;
5. делает смоук-проверку: запускает exe на 4 секунды и читает `%TEMP%\LogaShot_startup.log`
   (строка вида `0.132	tray=1	ok`). Иконка трея не подтвердилась — сборка считается неудачной.

Результат: `dist\LogaShot\LogaShot.exe` (portable-версия, ~57 МБ на диске).

Смоук можно пропустить: `set LOGA_SKIP_SMOKE=1` перед запуском. Нужно, когда у вас
установлена рабочая версия — запуск exe синхронизирует ключ автозагрузки в `HKCU\...\Run`.

Эквивалент без обрезки и смоука — сборка по спеке:

```cmd
pyinstaller LogaShot.spec
```

## 2. Установщик

```cmd
"C:\Program Files\Inno Setup 7\ISCC.exe" "%CD%\scripts\setup.iss"
```

Путь к скрипту лучше давать абсолютным: относительный путь в папке с кириллицей иногда
не находит исходные файлы. Результат — `dist\LogaShot_<версия>_setup.exe`.

Установщик:

- копирует `dist\LogaShot\*` в `{Program Files}\LogaShot`, **исключая** маркер `portable`
  и `settings.ini` — установленная копия хранит настройки в реестре, а не в папке программы
  (иначе без прав администратора настройки терялись бы);
- создаёт ярлыки в меню «Пуск» и (по выбору) на рабочем столе;
- поддерживает обычную деинсталляцию.

Бесшумная установка:

```cmd
LogaShot_0.3.2_setup.exe /VERYSILENT /NORESTART
```

## 3. Обновление версии

Версия живёт в трёх местах и меняется синхронно:

| Файл | Что |
|---|---|
| `src/version.py` | `VERSION` — единственный источник для интерфейса |
| `dev/version_file.txt` | версия в свойствах exe |
| `scripts/setup.iss` | `AppVersion` установщика |

Согласованность проверяет `tests/test_packaging.py`, так что рассинхрон всплывёт на тестах.

## 4. Проверка сборки

```cmd
python -m pytest
python tests\e2e_portable_save.py
```

`e2e_portable_save.py` — ручной прогон собранной portable-версии: открывает exe, шлёт PrtScr,
рисует выделение мышью, жмёт Enter и проверяет, что файл появился в `Рисунки\LogaShot`,
а `settings.ini` — рядом с exe. Очищает старые `*.png` в папке снимков и закрывает
`YandexDiskScreenshotEditor.exe`, если тот перехватывает PrtScr.

## Если что-то пошло не так

- **В сборке не работает OCR.** Не нашлись проекции WinRT или таблицы `_table.pywinrt`.
  Проверьте, что установлены все `winrt-*` из `requirements.txt`, и пересоберите:
  `dev\build.py` предупреждает о каждой ненайденной таблице.
- **Иконки нет в собранной версии.** В `_internal` должен остаться
  `PySide6\plugins\imageformats\qico.dll`: без него Qt не читает `.ico`.
- **Установленная версия не сохраняет настройки.** Проверьте, что в папке установки нет
  файлов `portable` и `settings.ini` — их не должно быть, установщик их исключает.
- **Антивирус ругается на exe.** Ожидаемо для неподписанных сборок PyInstaller;
  подпись кода в проекте пока не настроена.
