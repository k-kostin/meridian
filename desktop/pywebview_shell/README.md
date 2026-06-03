# PyWebView Shell

Это быстрый fallback-путь для desktop-упаковки без UI rewrite.

## Когда использовать

- нужен быстрый Windows prototype;
- хочется проверить desktop UX до полноценного Electron/Tauri-контура;
- важно не тащить сейчас Rust/Node toolchain;
- нужен почти нулевой разрыв с текущим Django UI.

## Как это работает

1. `run_desktop.py` запускает локальный Python sidecar.
2. Sidecar поднимает Django через `waitress` на `127.0.0.1`.
3. `pywebview` открывает адрес внутри desktop-окна.
4. При закрытии окна sidecar завершается.

## Почему это полезно даже при выборе Electron

- это минимальный рабочий prototype-path;
- можно быстро проверить desktop-сценарий на Windows;
- контракт `localhost + sidecar + shell` остается тем же для Electron и Tauri.

## Запуск из исходников

```bash
pip install -r desktop/python_sidecar/requirements.txt
pip install -r desktop/pywebview_shell/requirements.txt
python desktop/pywebview_shell/run_desktop.py
```
