# Python Sidecar

Этот каталог содержит launcher для локального backend-процесса, который desktop-shell будет запускать в фоне.

## Зачем это нужно

Текущий проект уже является полноценным Django-приложением с HTML-интерфейсом. Для desktop-упаковки не нужно переписывать домен и шаблоны; нужно только:

1. поднять локальный WSGI-сервер на `127.0.0.1`;
2. открыть его внутри desktop-окна;
3. скрыть от пользователя внешний браузер и командную строку.

Именно эту роль выполняет sidecar.

## Почему здесь выбран Waitress

- это чистый Python WSGI-сервер;
- он хорошо подходит для Windows desktop-сценария;
- он уместнее, чем `runserver`, для локально упакованного приложения.

## Что здесь лежит

- `serve.py` — минимальный launcher для Django WSGI-приложения.
- `requirements.txt` — отдельные зависимости для sidecar-контура.

## Контракт sidecar

- слушает только `127.0.0.1`;
- не открывает браузер сам;
- не использует Django development server;
- хранит рабочую SQLite-базу не внутри bundled app, а в пользовательском data-dir;
- по умолчанию выполняет `migrate` при старте, чтобы пользователь не делал это вручную;
- раздает статику через `StaticFilesHandler`, а не через `runserver`;
- получает host/port через env:
  - `WAREHOUSE_APP_HOST`
  - `WAREHOUSE_APP_PORT`
  - `WAREHOUSE_APP_THREADS`

По умолчанию data-dir выбирается так:

- Windows: `%LOCALAPPDATA%/Warehouse Control Desk`
- macOS: `~/Library/Application Support/Warehouse Control Desk`
- Linux: `$XDG_DATA_HOME/Warehouse Control Desk` или `~/.local/share/Warehouse Control Desk`

Дополнительные env-переменные:

- `WAREHOUSE_AUTO_MIGRATE=0` — если нужно отключить автоматический `migrate`.

## Запуск из исходников

```bash
pip install -r desktop/python_sidecar/requirements.txt
python desktop/python_sidecar/serve.py
```

После старта приложение будет доступно на `http://127.0.0.1:8765/`, если порт не переопределен.
