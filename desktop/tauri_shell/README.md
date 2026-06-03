# Tauri Shell

Это экспериментальная desktop-оболочка проекта.

## Почему Tauri оставлен как эксперимент

- позволяет сохранить текущий web-UI без отдельного UI rewrite;
- дает нативное окно и установщик для Windows;
- опирается на системный webview вместо тяжелого bundled browser runtime;
- хорошо сочетается с Python sidecar-процессом.

С 2026-05-08 primary path изменен на `Electron + Python sidecar`, потому что для текущего Windows/no-admin/offline сценария надежность первого запуска важнее размера.

## Что ожидается от этого каталога

- `frontend/` — desktop-специфичный host-layer, если понадобится отдельная оболочка поверх текущего UI;
- `src-tauri/` — Rust/Tauri config, bundle settings, icons, installer config, sidecar wiring.

## Контракт с backend

Tauri не должен дублировать бизнес-логику.

Он должен:

1. запустить упакованный Python sidecar;
2. дождаться локального `http://127.0.0.1:<port>/`;
3. открыть окно приложения;
4. корректно завершить sidecar при закрытии приложения.

## Текущий статус

Пока здесь зафиксирована структура и правила. Полноценный Tauri scaffold не является ближайшим релизным шагом.

Актуальный primary plan-of-record:

- `docs/ELECTRON_WINDOWS_PLAN.md`

Экспериментальный Tauri handoff:

- `docs/TAURI_WINDOWS_PLAN.md`
