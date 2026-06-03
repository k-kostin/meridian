# Launch Scripts

Скрипты для быстрого запуска проекта в двух режимах:

- `prod` — обычный рабочий режим без demo-данных;
- `demo` — demo-режим с перезагрузкой демонстрационного набора.

Файлы:

- `run-prod-macos.command`
- `run-demo-macos.command`
- `run-prod-linux.sh`
- `run-demo-linux.sh`
- `run-prod-windows.bat`
- `run-demo-windows.bat`

Что делают скрипты:

1. переходят в корень проекта;
2. проверяют наличие `.venv`;
3. выставляют env-переменные запуска;
4. выполняют `migrate`;
5. в demo-режиме выполняют `seed_demo_data --reset`;
6. запускают сервер на `0.0.0.0:8000`.

Поддерживаемые env-переменные:

- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_SECRET_KEY`

Важно:

- это удобные launch-скрипты для текущего проекта;
- для публичного интернет-деплоя все равно нужен отдельный production-контур с нормальным WSGI/ASGI-сервером и прокси.

## Changed-file guardrail

`check_changed.py` is an opt-in guardrail for targeted source edits.

The project is not currently a git repository, so the script does not infer changed files from `git diff`. Pass touched files explicitly:

```bash
source .venv/bin/activate
python scripts/check_changed.py warehouse_app/services.py
```

Behavior:

- docs-only changes: no command is needed;
- changed Python files: run `py_compile`;
- Django-impacting files under `warehouse_app/`, `config/`, `templates/`, or `manage.py`: run `manage.py check`;
- Django-impacting non-doc changes: run `manage.py test`;
- `--full`: run `manage.py check` and `manage.py test` regardless of paths;
- `--dry-run`: print selected commands without running them.

Use this before broader verification after changing a small set of files. It is not a replacement for the full test suite before significant releases or packaging work.
