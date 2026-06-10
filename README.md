# Meridian

Meridian is a small local operations desk for tracking items, documents, balances, reports, and spreadsheet exports.

The project is intentionally compact:

- Django server-rendered UI;
- SQLite for local/demo usage;
- calculated balances from posted documents;
- inventory flow with automatic adjustment documents;
- spreadsheet exports;
- desktop packaging experiments around a Python sidecar.

Meridian is not intended to be a full ERP, accounting system, POS, marketplace connector, or enterprise WMS. The near-term target is a small local warehouse desk for spreadsheet-first operations that need document-based stock accounting without adopting a large system.

The intended delivery model is one shared domain core with two deployment profiles:

- Local Single User profile: SQLite, one Windows computer, one active operator, local backup/restore;
- Team / Multi-User profile: the same Django domain logic on a server/PostgreSQL deployment for multiple workstations and users.

The project should not fork into separate accounting kernels for these profiles.

## Status

This repository starts from the `v0.1 MVP Baseline` and is now evolving through controlled hardening slices.

The project has closed `v0.4.0` Stage B operational contour work: activity history, built-in quick filter presets, basic `admin / operator / viewer` role UX, Excel nomenclature import with preview/validation, opening stock import through draft full inventory documents, item categories, category-aware filters, and saved views for key lists.

The project is useful for local demo and pilot-style evaluation, but it is not production-complete. Remaining commercial-readiness gaps include backup/restore, user attribution in operational history, Windows installer validation, explicit SQLite deployment limits, and broader desktop update/migration safety.

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
