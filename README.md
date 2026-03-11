# Asset Management App (Zerodha-style Local Platform)

A local-first enterprise-style asset management platform for Admin/User workflows with persistent storage.

## Highlights
- Multi-user profiles with role-based access (`admin`, `user`)
- Feature-flag driven UX per user
- Trade placement with market-hours aware execution (open vs executed orders)
- Portfolio, funds, watchlists, alerts, conditional orders
- Admin dashboard + user management
- Analysis workspace with TradingView chart backed by a FastAPI datafeed server
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
- `KiteBroker` calls the live Kite order endpoint (`POST https://api.kite.trade/orders/regular`) when Kite is connected from the **Configuration** page.
- Configure only Kite API key + API secret, then use **Login with Kite**; the app exchanges the returned `request_token` for an access token automatically.
- Set your Kite app redirect URL to `/kite/callback` on this app host so popup login can complete.
- FastAPI exposes TradingView-compatible datafeed endpoints (`/api/tradingview/config`, `/api/tradingview/symbols`, `/api/tradingview/history`) that pull NSE candles from Kite historical APIs.
- Use optional `KITE_BASE_URL` environment variable to override the endpoint host for testing/sandbox.
- If Kite is not connected, it safely falls back to local mock orders so local development still works end-to-end.
- This is a local development build focused on complete E2E workflow.
