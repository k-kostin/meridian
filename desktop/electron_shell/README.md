# Electron Shell

Основной Windows desktop path после пересмотра Tauri/Electron решения.

## Роль

Electron shell не содержит бизнес-логики. Он только:

1. выбирает свободный localhost-порт;
2. запускает Python sidecar;
3. передает sidecar desktop data-dir;
4. ждет `/healthz/`;
5. открывает Django UI в нативном окне;
6. завершает sidecar при выходе.

## Почему Electron выбран primary path

- встроенный Chromium убирает зависимость от WebView2;
- первый запуск предсказуемее на Windows-машинах без admin-прав;
- NSIS per-user installer является зрелым и стандартным каналом поставки;
- обновления shell + sidecar можно выпускать единым приложением;
- текущий Django UI не нужно переписывать.

Цена решения — больший размер дистрибутива. Для этого проекта надежность запуска важнее размера.

## Development run

Из этой папки:

```bash
npm install
npm start
```

В dev-режиме shell запускает:

```bash
python desktop/python_sidecar/serve.py
```

Если нужен конкретный Python:

```bash
WAREHOUSE_PYTHON=/path/to/python npm start
```

Проверено на macOS:

- shell запускает Python sidecar;
- sidecar отвечает на `/healthz/`;
- главная страница и Excel export работают через локальный `waitress`;
- SQLite создается в Electron `userData/data`.

## Production packaging

Production build ожидает packaged sidecar в:

```text
desktop/electron_shell/resources/backend/
```

Windows sidecar должен лежать как:

```text
resources/backend/warehouse-sidecar.exe
```

Затем:

```bash
npm run dist:win
```

## Data layout

SQLite и логи не хранятся рядом с `.exe`.

Electron передает sidecar:

```text
WAREHOUSE_DATA_DIR=<Electron userData>/data
DJANGO_DB_PATH=<Electron userData>/data/db.sqlite3
```

Логи shell:

```text
<Electron userData>/logs/desktop.log
```

## Не делать

- Не использовать фиксированный порт `8000` / `8765` в shell.
- Не хранить SQLite в install directory.
- Не переносить Excel-логику в Electron.
- Не делать portable основным каналом поставки.
