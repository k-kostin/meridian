# DESKTOP_APP.md

Последнее обновление: 2026-05-08

## Зачем появился desktop/gui-app трек

Проект начинался как локальное web-приложение на Django. Следующий практический шаг — подготовить Windows-доставку так, чтобы пользователь:

- не ставил Python отдельно;
- не работал через терминал;
- не видел обычный браузер с адресной строкой и вкладками;
- запускал систему как обычное desktop-приложение.

## Финальное решение на текущем этапе

Выбраны три траектории:

### Primary path: Electron + Python sidecar

Это основной путь для "настоящего" Windows desktop-продукта.

Причины:

- сохраняет текущий Django UI и доменную логику;
- дает нативное окно без внешнего браузера;
- несет Chromium с собой и не зависит от установленного WebView2;
- лучше подходит для предсказуемого первого запуска без admin-прав;
- имеет зрелый NSIS/electron-builder delivery path.

Цена решения — больший размер дистрибутива. Для текущего складского приложения надежность запуска важнее размера.

### Experimental path: Tauri + Python sidecar

Tauri остается технически возможным путем, но теперь не является primary.

Причины оставить как эксперимент:

- меньше shell-дистрибутив, если WebView2 уже есть;
- хороший long-term вариант для контролируемых Windows-машин;
- тот же sidecar-контракт можно переиспользовать.

Почему не primary сейчас:

- WebView2 может отсутствовать или быть заблокирован политиками;
- offline/no-admin сценарий усложняется;
- при включении WebView2 offline/fixed runtime преимущество размера уменьшается.

### Fast fallback: pywebview + тот же Python sidecar

Это быстрый и практичный backup-путь.

Причины:

- почти нулевой входной порог;
- весь prototype можно собрать на Python-стеке;
- удобно для ранней проверки desktop UX и packaging-гипотез.

Техническая оговорка:

- на Windows `pywebview` может тянуть `pythonnet`;
- на Python `3.14` это уже дало реальный сбой сборки;
- поэтому текущий packaging-порядок такой:
  1. сначала отдельно собирается и проверяется `python_sidecar`;
  2. затем отдельным шагом пробуется `pywebview_shell`;
  3. если `pywebview` снова упрется в интерпретатор, fallback-путь временно переводится на Python `3.13`, а основной вектор остается `Electron`.

Подробный handoff-план по основному пути лежит в:

- `docs/ELECTRON_WINDOWS_PLAN.md`

Tauri-план оставлен как экспериментальный:

- `docs/TAURI_WINDOWS_PLAN.md`

## Что сознательно не выбрано

- `PySide6 / Qt` — хороший вариант, но означает отдельный UI rewrite.
- `Flet` — проще, чем Qt, но все равно создает новый UI-контур.
- `Electron` — выбран как рабочий путь, несмотря на размер.

## Версионность

- Каноническая версия приложения задается в `warehouse_app/version.py`.
- Эта версия выводится в интерфейсе через общий context processor.
- `desktop/electron_shell/package.json` должен оставаться синхронизирован с `warehouse_app/version.py` перед desktop-сборкой.

Текущая версия: `0.4.0`.

## Desktop-архитектура

### 1. Backend остается Django

Текущий Django-контур остается единственным источником:

- бизнес-логики;
- HTML-экранов;
- отчетов;
- Excel-выгрузок;
- доменных инвариантов.

Desktop shell не должен переносить эту логику в отдельный код.

### 2. Sidecar-процесс

Для desktop-сборки backend поднимается как локальный sidecar:

- WSGI-приложение из `config.wsgi`;
- сервер `waitress`;
- bind только на `127.0.0.1`;
- отдельный порт, по умолчанию `8765`.

### 3. Desktop shell

Shell делает только orchestration:

1. запускает sidecar;
2. ждет готовности локального URL;
3. открывает окно приложения;
4. завершает sidecar при выходе.

## Структура репозитория

- `desktop/python_sidecar/`
  - `serve.py`
  - `requirements.txt`
- `desktop/pywebview_shell/`
  - `run_desktop.py`
  - `requirements.txt`
- `desktop/electron_shell/`
  - `package.json`
  - `src/main.js`
- `desktop/tauri_shell/`
  - `README.md`
  - `frontend/`
  - `src-tauri/`

## Что уже подготовлено

- зафиксирована desktop-стратегия;
- добавлена `desktop/`-структура в репозиторий;
- создан sidecar launcher на `waitress`;
- создан быстрый `pywebview` shell launcher;
- вынесен путь к рабочей SQLite-базе в desktop-friendly env-конфигурацию (`WAREHOUSE_DATA_DIR` / `DJANGO_DB_PATH`);
- для Local Single User deployments user data directory содержит SQLite-базу и `backups/`;
- перед автоматической миграцией sidecar создает `pre_migration` backup, если база уже существует;
- добавлены стартовые `PyInstaller` spec-файлы и Windows build-скрипты для prototype-path;
- добавлен primary path (`Electron`) и отделен от экспериментального path (`Tauri`) и fallback-path (`pywebview`).
- на macOS уже проверен sidecar-path:
  - launcher из исходников поднимает приложение через `waitress`;
  - выполняет auto-migrate на пустом data-dir;
  - отдает HTML и статику;
  - `PyInstaller`-сборка `warehouse-sidecar` успешно создается и проходит тот же smoke-test.
- Windows build flow разведен на два шага:
  - отдельная сборка backend-sidecar;
  - отдельная сборка `pywebview` shell.

## Что еще не сделано

- нет собранного Windows `.exe` / `.msi`;
- Electron scaffold добавлен, но еще не прошел Windows installer validation;
- нет Tauri scaffold с toolchain и bundle config; Tauri теперь экспериментальный path;
- не проверены packaging-size и signing-сценарии;
- не выбрана финальная схема auto-update;
- не добавлены desktop-specific icons и installer assets.

## Практический план

### Этап 1. Sidecar validation

- проверить `desktop/python_sidecar/serve.py` c `waitress`;
- убедиться, что demo/prod режимы корректно работают через локальный host/port;
- убедиться, что Excel-выгрузки и статические файлы работают из sidecar-контура.
- это должен быть независимый шаг, не зависящий от `pywebview`.

### Этап 2. Primary Electron shell

- собрать sidecar в PyInstaller `onedir`;
- скопировать sidecar в `desktop/electron_shell/resources/backend`;
- проверить запуск Electron shell из исходников;
- собрать NSIS per-user installer;
- проверить установку без admin-прав.

### Этап 3. Fast prototype

- собрать рабочий `pywebview` prototype;
- проверить, что пользователь не видит браузер и CLI;
- оценить startup time и UX.

### Этап 4. Experimental Tauri shell

- завести полноценный `Tauri` shell только как эксперимент;
- подключить packaged Python sidecar;
- настроить Windows bundle / installer.

### Этап 5. Distribution hardening

- иконки;
- versioning;
- installer polish;
- release checklist;
- smoke-check Windows build на чистой машине.

## Правила для будущих изменений

- desktop-shell не должен дублировать доменную логику;
- если меняется desktop-стратегия, обновлять этот файл;
- если появляется отдельный desktop frontend layer, это должно быть явно отражено в `docs/ARCHITECTURE.md`.
