# ELECTRON_WINDOWS_PLAN.md

Последнее обновление: 2026-05-08

Этот документ фиксирует актуальный рабочий путь для Windows desktop-доставки:

- **Primary path**: `Electron + Python sidecar`
- **Experimental path**: `Tauri v2 + Python sidecar`
- **Prototype/fallback path**: `pywebview + Python sidecar`

## 1. Почему primary path сменен на Electron

Главный критерий для текущего продукта — не минимальный размер, а предсказуемый первый запуск у обычного Windows-пользователя:

- без установки Python;
- без командной строки;
- без admin-прав;
- без зависимости от внешнего браузера;
- желательно без зависимости от интернета на первом запуске.

Electron несет Chromium внутри приложения. Это делает дистрибутив тяжелее, но убирает класс проблем с отсутствующим или заблокированным WebView2.

Для складского приложения надежность запуска важнее экономии десятков или сотен мегабайт.

## 2. Архитектура

```text
Electron shell
  -> выбирает свободный localhost-порт
  -> запускает Python sidecar
      -> Django + SQLite + openpyxl + Waitress
      -> /healthz/
      -> server-rendered UI
      -> Excel exports
  -> ждет /healthz/
  -> открывает http://127.0.0.1:<port>/ в окне приложения
  -> завершает sidecar при закрытии
```

Electron не должен дублировать бизнес-логику. Вся доменная логика остается в Django.

## 3. Почему не Tauri как основной путь сейчас

Tauri технически подходит, но на Windows использует WebView2.

Это нормально, если:

- целевые машины почти гарантированно имеют WebView2;
- есть интернет или контролируемый installer-flow;
- команда готова тестировать WebView2 edge cases;
- размер дистрибутива критичен.

Для текущего кейса эти условия не гарантированы. Возможные проблемы:

- WebView2 отсутствует;
- установка WebView2 заблокирована политиками;
- нет интернета на первом запуске;
- нет admin-прав;
- корпоративные политики отключают обновление runtime.

Если включать WebView2 offline/fixed runtime в поставку, Tauri теряет значительную часть преимущества по размеру, но сохраняет дополнительную runtime-зависимость.

## 4. Почему не portable как основной канал

Основной канал поставки должен быть:

- **NSIS per-user installer**, без admin-прав.

Portable ZIP можно держать как тестовый или аварийный вариант, но не как основной продуктовый сценарий.

Причины:

- SQLite нельзя надежно хранить рядом с `.exe`;
- запуск с флешки или read-only папки ломает ожидания по данным;
- auto-update для portable хуже;
- пользователи могут случайно удалить или переместить часть файлов.

## 5. Sidecar rules

Python sidecar:

- собирается через PyInstaller `onedir`, не `onefile`;
- слушает только `127.0.0.1`;
- получает порт через `WAREHOUSE_APP_PORT`;
- получает data-dir через `WAREHOUSE_DATA_DIR`;
- хранит SQLite в пользовательском data-dir;
- сам выполняет `migrate` на старте;
- отдает `/healthz/` после готовности Django.

`onefile` не выбран, потому что он медленнее стартует, распаковывается во временную директорию и сложнее диагностируется.

## 6. Electron shell rules

Electron shell:

- выбирает свободный порт, не использует фиксированный `8000` или `8765`;
- запускает sidecar из bundled `resources/backend`;
- ждет `/healthz/`;
- показывает окно только после readiness;
- пишет логи в userData/logs;
- при закрытии приложения завершает sidecar;
- использует single-instance lock;
- не хранит SQLite в install directory.

## 7. Data layout

Рекомендуемый layout:

```text
%LOCALAPPDATA%/<AppName>/data/db.sqlite3
%LOCALAPPDATA%/<AppName>/logs/desktop.log
```

В Electron текущая реализация использует:

```text
app.getPath("userData")/data/db.sqlite3
app.getPath("userData")/logs/desktop.log
```

## 8. Build flow

Windows flow:

1. Собрать Python sidecar:
   - `desktop/build/build-sidecar-windows.bat`
2. Скопировать sidecar onedir в:
   - `desktop/electron_shell/resources/backend/`
3. Собрать Electron installer:
   - `npm run dist:win`

Общий скрипт:

```bat
desktop\build\build-electron-windows.bat
```

## 9. Первый milestone

Минимальный production prototype должен доказать:

- sidecar стартует из Electron;
- порт выбирается автоматически;
- `/healthz/` проходит;
- окно открывает текущий Django UI;
- SQLite создается в пользовательском data-dir;
- Excel-выгрузки работают;
- закрытие Electron завершает sidecar;
- NSIS installer ставится без admin-прав.

## 10. Что остается экспериментом

Tauri оставлен как экспериментальный путь в:

- `desktop/tauri_shell/`
- `docs/TAURI_WINDOWS_PLAN.md`

К нему имеет смысл возвращаться, если:

- размер Electron-дистрибутива станет реальной проблемой;
- целевые Windows-машины будут контролируемыми;
- WebView2 availability будет подтверждена;
- появится ресурс на отдельную Tauri validation matrix.
