# Asset Management App (Zerodha-style Local Platform)

A local-first enterprise-style asset management platform for Admin/User workflows with persistent storage.

## Highlights
- Multi-user profiles with role-based access (`admin`, `user`)
- Feature-flag driven UX per user
- Trade placement with market-hours aware execution (open vs executed orders)
- Portfolio, funds, watchlists, alerts, conditional orders
- Admin dashboard + user management
- Analysis workspace with chart widget + trendline-capable embedded chart
- SQLite persistence (`data/app.db`) for permanent local memory

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000

## Default credentials
- Admin: `admin / admin123`
- User: `demo / demo123`

## Notes
- `KiteBroker` adapter is included with a local mock implementation. Replace internals in `KiteBroker.place_order` with real Zerodha Kite Connect API calls.
- This is a local development build focused on complete E2E workflow.
