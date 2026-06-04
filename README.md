# Meridian

Meridian is a small local operations desk for tracking items, documents, balances, reports, and spreadsheet exports.

The project is intentionally compact:

- Django server-rendered UI;
- SQLite for local/demo usage;
- calculated balances from posted documents;
- inventory flow with automatic adjustment documents;
- spreadsheet exports;
- desktop packaging experiments around a Python sidecar.

## Status

This repository starts from the `v0.1 MVP Baseline` and is now evolving through controlled hardening slices.

The baseline is useful for local demo and pilot-style evaluation, but it is not production-complete. Current work adds activity history, built-in quick filter presets, basic `admin / operator / viewer` role UX, and a parser-only Excel import foundation for nomenclature preview/validation. Remaining gaps include import UI/commit workflows, production-grade RBAC, user-defined saved views, and installer validation.

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py test
python manage.py runserver
```

Open: http://127.0.0.1:8000

## Demo Data

```bash
source .venv/bin/activate
python manage.py seed_demo_data
```

To reset demo data intentionally:

```bash
python manage.py seed_demo_data --reset
```

## Verification

```bash
source .venv/bin/activate
python manage.py check
python manage.py test
python scripts/check_changed.py --full
```

## License

MIT
