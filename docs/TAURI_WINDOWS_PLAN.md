# TAURI_WINDOWS_PLAN.md

Последнее обновление: 2026-05-08

Этот документ больше не является primary plan-of-record.

Актуальный рабочий путь:

- `Electron + Python sidecar`
- см. `docs/ELECTRON_WINDOWS_PLAN.md`

Tauri оставлен как экспериментальный путь для будущей проверки, если размер Electron-дистрибутива станет критичным или целевая Windows-среда будет контролируемой.

Ниже сохранен прежний план как handoff для возможного Tauri-эксперимента.

Цель:

- чтобы любой следующий агент мог продолжить packaging-трек без чтения всей переписки;
- чтобы Tauri-переход не приходилось снова проектировать с нуля;
- чтобы конечная цель была user-facing Windows app, а не developer-only набор команд.

---

## 1. Принятое решение

Экспериментальный путь:

- `Tauri v2 + Python sidecar`

Fallback-path:

- `pywebview + тот же Python sidecar`

Но fallback-path больше не считается основным:

- на Windows `pywebview` тянет `pythonnet`;
- на Python `3.14` это уже вызвало реальный packaging-сбой;
- значит `pywebview` годится только как запасной prototype-path.

Итог после пересмотра 2026-05-08:

- финальный Windows desktop app сейчас должен строиться через `Electron`;
- Tauri можно проверять отдельно как experimental path;
- backend остается на Django/Python.

---

## 2. Что уже доказано и что нельзя терять

На момент этого документа уже доказано:

1. Django-контур является каноническим источником:
   - бизнес-логики;
   - HTML-экранов;
   - отчетов;
   - Excel-выгрузок;
   - доменных инвариантов.
2. Упакованный backend-sidecar уже реально собирается через `PyInstaller`.
3. Sidecar-path уже проверен:
   - на macOS;
   - на реальной Windows-машине;
   - на Windows-машине без admin-прав.
4. На Windows уже подтверждено:
   - `warehouse-sidecar.exe` собирается;
   - запускается;
   - открывает приложение на `http://127.0.0.1:<port>/`;
   - использует пользовательский data-dir;
   - не требует ручной установки Python для будущего пользователя.

Это очень важно:

- packaging backend уже не гипотеза;
- unresolved часть — это именно desktop-shell и delivery layer.

---

## 3. Что должен видеть конечный пользователь

Конечный пользователь НЕ должен:

- ставить Python;
- ставить pip-зависимости;
- открывать PowerShell / cmd;
- запускать `.bat`;
- работать с `localhost`;
- видеть внешний браузер.

Конечный пользователь должен получать одно из двух:

1. **Installer**
   - запускает `Setup.exe` / `.msi`;
   - устанавливает приложение;
   - получает ярлык;
   - открывает приложение как обычную программу.

2. **Portable build**
   - распаковывает архив;
   - запускает `Warehouse Control.exe`;
   - работает в отдельном окне.

Все текущие команды с `venv`, `pip`, `pyinstaller`, `.bat` — это только developer/release pipeline.

---

## 4. Целевая архитектура

### 4.1 Общая схема

```text
Tauri shell
  -> запускает warehouse-sidecar.exe
  -> ждет готовности localhost URL
  -> открывает главное окно приложения
  -> завершает sidecar при выходе
```

### 4.2 Разделение ответственности

#### Django / Python sidecar отвечает за:

- доменную логику;
- шаблоны и HTML;
- Excel-экспорт;
- demo/prod режимы;
- миграции;
- SQLite;
- локальный HTTP-контур.

#### Tauri shell отвечает за:

- запуск sidecar;
- readiness-check;
- управление окном;
- installer/bundle;
- будущий updater;
- desktop-only интеграции, если появятся позже.

### 4.3 Что нельзя делать

Shell не должен:

- дублировать доменную логику;
- переразмечать бизнес-сущности в отдельный frontend-контур без необходимости;
- хранить SQLite внутри bundled app;
- превращать релиз в сценарий “сначала установите Python”.

---

## 5. Runtime data и SQLite

SQLite должна жить в пользовательском data-dir, не в папке приложения.

Текущее решение уже реализовано в backend:

- `WAREHOUSE_DATA_DIR`
- `DJANGO_DB_PATH`

Это решение нужно сохранить как обязательное.

Целевой Windows data-dir:

`%LOCALAPPDATA%\Warehouse Control Desk\`

Там должны жить:

- `db.sqlite3`
- при необходимости runtime logs;
- позднее — desktop user settings.

---

## 6. Что уже лежит в репозитории

Существующие опорные части:

- `desktop/python_sidecar/serve.py`
  - launcher Django через `waitress`
- `desktop/python_sidecar/warehouse-sidecar.spec`
  - packaging backend-sidecar
- `desktop/build/build-sidecar-windows.bat`
  - текущий Windows build entrypoint для backend
- `desktop/pywebview_shell/`
  - fallback prototype-path
- `desktop/tauri_shell/README.md`
  - краткое описание будущего shell
- `docs/DESKTOP_APP.md`
  - общая стратегия desktop/gui-app

Вывод:

- Tauri-переход должен строиться поверх уже доказанного `warehouse-sidecar`;
- не нужно перепридумывать backend packaging.

---

## 7. Что должен уметь первый рабочий Tauri shell

Минимально жизнеспособный Tauri shell должен уметь:

1. запускаться как отдельное Windows-приложение;
2. не показывать консоль;
3. запускать bundled `warehouse-sidecar.exe`;
4. передавать sidecar env:
   - `WAREHOUSE_APP_PORT`
   - `WAREHOUSE_DATA_DIR`
   - `DJANGO_DB_PATH`
   - `DJANGO_DEBUG=0`
   - `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost`
   - `DJANGO_SECRET_KEY`
   - при необходимости `WAREHOUSE_DEMO_MODE`
5. ждать готовности backend;
6. открывать окно приложения;
7. завершать sidecar при закрытии app.

Что НЕ требуется в первом проходе:

- updater;
- tray;
- multi-window;
- новый продуктовый frontend;
- desktop-native rewrite.

---

## 8. Tauri shell: рекомендуемая структура

```text
desktop/
  tauri_shell/
    frontend/
      package.json
      index.html
      src/
        main.ts
        splash.ts
    src-tauri/
      Cargo.toml
      tauri.conf.json
      capabilities/
        default.json
      icons/
      binaries/
        warehouse-sidecar-x86_64-pc-windows-msvc.exe
      src/
        main.rs
        sidecar.rs
        readiness.rs
```

### Какой frontend-layer нужен

Не нужен новый полноценный SPA.

Предпочтительный вариант для первого Tauri-прохода:

- очень тонкий host frontend;
- splash/loading screen;
- после readiness — загрузка `http://127.0.0.1:<port>/`.

Это минимизирует новую фронтенд-сложность и не плодит второй UI рядом с Django.

---

## 9. Sidecar contract для Tauri

Это один из самых важных разделов.

### 9.1 Имя и формат бинарника

Логическое имя sidecar:

- `warehouse-sidecar`

Windows binary:

- `warehouse-sidecar.exe`

Для Tauri `externalBin` под Windows нужен target triple suffix, например:

- `warehouse-sidecar-x86_64-pc-windows-msvc.exe`

Это должно учитываться на этапе build pipeline.

### 9.2 Передача конфигурации

Передавать конфигурацию предпочтительно через env vars, а не через набор сложных CLI flags.

Канонический набор env:

- `WAREHOUSE_APP_PORT`
- `WAREHOUSE_DATA_DIR`
- `DJANGO_DB_PATH`
- `DJANGO_DEBUG=0`
- `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost`
- `DJANGO_SECRET_KEY=<runtime-secret>`
- `WAREHOUSE_DEMO_MODE=0|1`
- `WAREHOUSE_AUTO_MIGRATE=1`

### 9.3 Port strategy

Практичный путь:

1. Shell выбирает порт.
2. Передает его sidecar через env.
3. Сам же использует этот port для readiness-check и открытия окна.

На первом этапе достаточно узкого диапазона портов и простого выбора свободного.

### 9.4 Readiness strategy

Shell не должен открывать окно до того, как backend реально готов.

Минимальный алгоритм:

1. Запустить sidecar.
2. Poll `GET /` или отдельный `/health/`.
3. Таймаут 15–25 секунд.
4. При успехе — открыть app window.
5. При fail — показать error screen / dialog.

### 9.5 Shutdown

При выходе из Tauri app:

- child process sidecar должен завершаться;
- нельзя оставлять висящий backend в процессах.

---

## 10. Что стоит доделать в backend до или вместе с Tauri

Это не блокирует scaffold, но полезно.

### Желательно

1. Добавить `/health/` endpoint:
   - `200 OK`
   - минимальный JSON или plain text
   - без тяжёлой логики

2. Продумать runtime logging sidecar:
   - лог-файл в user data dir

3. Зафиксировать runtime secret policy для desktop shell.

### Не нужно заранее

- отдельный desktop API layer;
- новый auth flow только ради desktop;
- дублирующий frontend.

---

## 11. Реальный план реализации

### Этап A. Завести настоящий Tauri scaffold

Цель:

- превратить `desktop/tauri_shell/` из placeholder в рабочий shell-проект.

Подзадачи:

1. Инициализировать Tauri v2 scaffold.
2. Создать минимальный frontend host layer.
3. Добавить `capabilities/default.json`.
4. Настроить process/shell permissions для запуска sidecar.

Ожидаемый результат:

- Tauri shell собирается как пустая оболочка.

### Этап B. Подключить packaged sidecar

Цель:

- Tauri shell умеет запускать `warehouse-sidecar`.

Подзадачи:

1. Подготовить `src-tauri/binaries/`.
2. Настроить `externalBin`.
3. Научить build flow класть туда sidecar binary с target triple suffix.
4. Реализовать launch sidecar из Rust.

Ожидаемый результат:

- Tauri shell реально стартует backend.

### Этап C. Readiness flow

Цель:

- окно приложения не открывается в “битое” состояние.

Подзадачи:

1. Реализовать polling readiness.
2. Сделать timeout.
3. Показать loading screen / splash.
4. Показать error state при fail.

### Этап D. Main app window

Цель:

- рендерить текущий Django UI внутри Tauri.

Подзадачи:

1. Подключить окно к `http://127.0.0.1:<port>/`.
2. Проверить:
   - dashboard;
   - balances;
   - analytics;
   - Excel exports;
   - demo mode.

### Этап E. Graceful shutdown

Цель:

- sidecar lifecycle привязан к lifecycle shell.

Подзадачи:

1. Закрытие child process при exit.
2. Проверка repeated relaunch.
3. Проверка отсутствия висящих процессов.

### Этап F. Windows packaging

Цель:

- получить пользовательский Windows deliverable.

Подзадачи:

1. Собрать portable build.
2. Собрать installer.
3. Проверить user-level install без admin.

Предпочтительный install mode:

- **per-user installer**

Почему:

- у целевой машины может не быть admin-прав;
- это лучше соответствует реальному пользовательскому сценарию.

### Этап G. Release hardening

Цель:

- довести сборку до пригодного к передаче состояния.

Подзадачи:

1. App icon.
2. Product name/version.
3. Installer branding.
4. Smoke-check на чистой Windows-машине.
5. Release notes / release checklist.

### Этап H. Optional updater

Это уже не first release.

Если понадобится:

1. Подключить Tauri updater plugin.
2. Настроить подпись артефактов.
3. Поднять update endpoint / static manifest.

---

## 12. Что делать на macOS, а что на Windows

### На macOS можно делать

- backend-изменения;
- docs;
- структуру shell-проекта;
- Tauri source code;
- build scripts;
- icons/assets;
- план release workflow.

### На Windows лучше делать

- сборку final Windows artifacts;
- проверку `warehouse-sidecar.exe`;
- проверку Tauri installers;
- smoke-test на реальной Windows-машине;
- проверку сценария без admin-прав.

Практический принцип:

- разработка может оставаться в основном на macOS;
- Windows нужен как build/release machine.

---

## 13. Release workflow после внедрения Tauri

### Для разработчика

1. Доработать backend / UI в основном проекте.
2. Синхронизировать репозиторий на Windows build machine.
3. Собрать новый sidecar.
4. Собрать новый Tauri bundle.
5. Прогнать smoke-test.
6. Выпустить installer / portable build.

### Для тестировщика

Он не должен ставить Python или пользоваться терминалом.

Он получает:

- либо portable build;
- либо installer.

### Для конечного пользователя

Идеальный сценарий:

1. Скачать installer или zip.
2. Установить или распаковать.
3. Дважды кликнуть по приложению.
4. Работать в обычном desktop-окне.

---

## 14. Обновления после релиза

Да, Windows-версию потом можно обновлять без изменения общей архитектуры.

Нормальный цикл:

1. Меняем backend в основном репозитории.
2. На Windows собираем:
   - новый `warehouse-sidecar.exe`;
   - новый Tauri bundle / installer.
3. Отдаем новую версию пользователю.

То есть:

- основная работа продолжается в текущем Django-проекте;
- desktop-shell — это delivery layer;
- Windows-релизы становятся повторяемым packaging-процессом.

Auto-update можно добавить позже через Tauri updater, но это не должно блокировать первый user-facing релиз.

---

## 15. Критерии готовности задачи

Задачу “Windows desktop app готов” можно считать закрытой только если:

1. На Windows собирается `warehouse-sidecar.exe`.
2. На Windows собирается Tauri shell.
3. Shell запускает backend автоматически.
4. Пользователь не видит внешний браузер.
5. Пользователь не видит консоль.
6. SQLite создается в user data dir.
7. Demo mode работает.
8. Excel-выгрузки работают из desktop app.
9. Закрытие app завершает sidecar.
10. Есть user-facing deliverable:
    - installer
    - или portable build.

---

## 16. Что не забыть следующему агенту

1. Не переписывать UI на новый стек без отдельного решения владельца.
2. Не возвращать `pywebview` в статус primary path.
3. Не смешивать backend-рефакторинг и delivery-layer работу.
4. Не строить конечный пользовательский сценарий вокруг Python/pip/bat.
5. Не хранить SQLite внутри bundled app.
6. Учитывать отсутствие admin-прав как обычный сценарий.

---

## 17. Следующий практический шаг

Когда packaging-трек возобновится, следующий шаг должен быть таким:

**если Tauri снова станет актуален, завести первый настоящий Tauri scaffold в `desktop/tauri_shell/` и подключить к нему уже доказанный `warehouse-sidecar`.**

Для ближайшего рабочего Windows-релиза использовать `docs/ELECTRON_WINDOWS_PLAN.md`.
