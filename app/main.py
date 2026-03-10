from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "app.db"

app = FastAPI(title="Asset Management App")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@contextmanager
def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def market_is_open() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    return time(9, 15) <= now.time() <= time(15, 30)


SESSIONS: dict[str, int] = {}
DEFAULT_FLAGS = ["dashboard", "trade", "watchlist", "analysis", "portfolio", "alerts", "configuration"]


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = Field(pattern="^(admin|user)$")
    initial_funds: float = 100000


class FeatureFlagUpdate(BaseModel):
    enabled: bool


class TradeRequest(BaseModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell)$")
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)
    user_ids: list[int] | None = None


class WatchlistRequest(BaseModel):
    name: str


class WatchlistItemRequest(BaseModel):
    symbol: str


class AlertRequest(BaseModel):
    symbol: str
    condition: str = Field(pattern="^(reaches|closes_above|closes_below)$")
    value: float
    duration: str = Field(pattern="^(15m|30m|1h|4h|1d|1w|1mo)$")


class ConditionalOrderRequest(BaseModel):
    symbol: str
    action: str = Field(pattern="^(buy_more|sell_qty|buy_if|sell_if)$")
    condition_type: str = Field(pattern="^(closes_above|closes_below|reaches)$")
    trigger_value: float
    quantity: int = Field(gt=0)


class KiteBroker:
    """Local mock adapter; swap with real Kite Connect calls."""

    @staticmethod
    def place_order(symbol: str, side: str, quantity: int, price: float) -> dict[str, Any]:
        return {
            "broker": "kite-mock",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "broker_order_id": f"MOCK-{secrets.token_hex(4)}",
            "status": "submitted",
            "timestamp": now_iso(),
        }


def init_db() -> None:
    with db_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                max_investment_per_stock REAL DEFAULT 50000,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS funds (
                user_id INTEGER PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                avg_price REAL NOT NULL,
                UNIQUE(user_id, symbol),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                status TEXT NOT NULL,
                broker_payload TEXT,
                created_at TEXT NOT NULL,
                executed_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS watchlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS watchlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watchlist_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                UNIQUE(watchlist_id, symbol),
                FOREIGN KEY(watchlist_id) REFERENCES watchlists(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                condition TEXT NOT NULL,
                value REAL NOT NULL,
                duration TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS conditional_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                condition_type TEXT NOT NULL,
                trigger_value REAL NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS feature_flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                feature_name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, feature_name),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )

        if not conn.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
            conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
                ("admin", hash_password("admin123"), now_iso()),
            )
            admin_id = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()["id"]
            conn.execute("INSERT INTO funds(user_id, balance) VALUES (?, ?)", (admin_id, 1000000))
            for flag in DEFAULT_FLAGS:
                conn.execute(
                    "INSERT INTO feature_flags(user_id, feature_name, enabled) VALUES (?, ?, 1)", (admin_id, flag)
                )

        if not conn.execute("SELECT 1 FROM users WHERE username='demo'").fetchone():
            conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, 'user', ?)",
                ("demo", hash_password("demo123"), now_iso()),
            )
            user_id = conn.execute("SELECT id FROM users WHERE username='demo'").fetchone()["id"]
            conn.execute("INSERT INTO funds(user_id, balance) VALUES (?, ?)", (user_id, 250000))
            for flag in DEFAULT_FLAGS:
                conn.execute(
                    "INSERT INTO feature_flags(user_id, feature_name, enabled) VALUES (?, ?, 1)", (user_id, flag)
                )


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def get_current_user(request: Request) -> sqlite3.Row:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing auth token")
    token = auth.removeprefix("Bearer ").strip()
    user_id = SESSIONS.get(token)
    if not user_id:
        raise HTTPException(401, "Invalid session")
    with db_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(401, "User not found")
        return user


def require_admin(user: sqlite3.Row = Depends(get_current_user)) -> sqlite3.Row:
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return user


def serialize_row(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def apply_execution(conn: sqlite3.Connection, order_id: int) -> None:
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order or order["status"] != "executed":
        return
    user_id = order["user_id"]
    qty = order["quantity"]
    price = order["price"]
    side = order["side"]
    symbol = order["symbol"]
    funds = conn.execute("SELECT balance FROM funds WHERE user_id=?", (user_id,)).fetchone()
    balance = funds["balance"] if funds else 0
    hold = conn.execute("SELECT * FROM holdings WHERE user_id=? AND symbol=?", (user_id, symbol)).fetchone()

    if side == "buy":
        total_cost = qty * price
        if balance < total_cost:
            conn.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
            return
        conn.execute("UPDATE funds SET balance = balance - ? WHERE user_id=?", (total_cost, user_id))
        if hold:
            new_qty = hold["quantity"] + qty
            new_avg = ((hold["quantity"] * hold["avg_price"]) + total_cost) / new_qty
            conn.execute("UPDATE holdings SET quantity=?, avg_price=? WHERE id=?", (new_qty, new_avg, hold["id"]))
        else:
            conn.execute(
                "INSERT INTO holdings(user_id, symbol, quantity, avg_price) VALUES (?, ?, ?, ?)",
                (user_id, symbol, qty, price),
            )
    else:
        if not hold or hold["quantity"] < qty:
            conn.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
            return
        proceeds = qty * price
        conn.execute("UPDATE funds SET balance = balance + ? WHERE user_id=?", (proceeds, user_id))
        remaining = hold["quantity"] - qty
        if remaining == 0:
            conn.execute("DELETE FROM holdings WHERE id=?", (hold["id"],))
        else:
            conn.execute("UPDATE holdings SET quantity=? WHERE id=?", (remaining, hold["id"]))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    with db_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=?", (payload.username,)).fetchone()
        if not user or user["password_hash"] != hash_password(payload.password):
            raise HTTPException(401, "Invalid credentials")

        token = secrets.token_hex(16)
        SESSIONS[token] = user["id"]
        features = conn.execute(
            "SELECT feature_name, enabled FROM feature_flags WHERE user_id=?", (user["id"],)
        ).fetchall()
        return {
            "token": token,
            "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
            "features": {row["feature_name"]: bool(row["enabled"]) for row in features},
        }


@app.get("/api/me")
def me(user: sqlite3.Row = Depends(get_current_user)) -> dict[str, Any]:
    with db_conn() as conn:
        funds = conn.execute("SELECT balance FROM funds WHERE user_id=?", (user["id"],)).fetchone()
        features = conn.execute(
            "SELECT feature_name, enabled FROM feature_flags WHERE user_id=?", (user["id"],)
        ).fetchall()
        return {
            "user": serialize_row(user),
            "fund_balance": funds["balance"] if funds else 0,
            "features": {row["feature_name"]: bool(row["enabled"]) for row in features},
        }


@app.get("/api/dashboard")
def dashboard(user: sqlite3.Row = Depends(get_current_user)) -> dict[str, Any]:
    with db_conn() as conn:
        if user["role"] == "admin":
            users_count = conn.execute("SELECT COUNT(*) c FROM users WHERE role='user'").fetchone()["c"]
            todays_orders = conn.execute(
                "SELECT COUNT(*) c FROM orders WHERE date(created_at)=date('now') AND status='executed'"
            ).fetchone()["c"]
            holdings_count = conn.execute("SELECT COUNT(*) c FROM holdings").fetchone()["c"]
            return {
                "role": "admin",
                "users_count": users_count,
                "todays_executed_trades": todays_orders,
                "aggregate_holdings_positions": holdings_count,
            }
        orders = conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE user_id=? AND date(created_at)=date('now')", (user["id"],)
        ).fetchone()["c"]
        holdings = conn.execute("SELECT COUNT(*) c FROM holdings WHERE user_id=?", (user["id"],)).fetchone()["c"]
        funds = conn.execute("SELECT balance FROM funds WHERE user_id=?", (user["id"],)).fetchone()["balance"]
        return {
            "role": "user",
            "todays_orders": orders,
            "holding_positions": holdings,
            "fund_balance": funds,
        }


@app.post("/api/users", dependencies=[Depends(require_admin)])
def create_user(payload: CreateUserRequest) -> dict[str, Any]:
    with db_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (payload.username, hash_password(payload.password), payload.role, now_iso()),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(400, "Username already exists")
        user_id = cur.lastrowid
        conn.execute("INSERT INTO funds(user_id, balance) VALUES (?, ?)", (user_id, payload.initial_funds))
        for f in DEFAULT_FLAGS:
            conn.execute("INSERT INTO feature_flags(user_id, feature_name, enabled) VALUES (?, ?, 1)", (user_id, f))
        return {"user_id": user_id}


@app.get("/api/users", dependencies=[Depends(require_admin)])
def list_users() -> list[dict[str, Any]]:
    with db_conn() as conn:
        rows = conn.execute("SELECT id, username, role, max_investment_per_stock FROM users ORDER BY id").fetchall()
        return [serialize_row(r) for r in rows]


@app.delete("/api/users/{user_id}", dependencies=[Depends(require_admin)])
def delete_user(user_id: int) -> dict[str, Any]:
    with db_conn() as conn:
        conn.execute("DELETE FROM users WHERE id=? AND role='user'", (user_id,))
        return {"deleted": True}


@app.put("/api/users/{user_id}/features/{feature}", dependencies=[Depends(require_admin)])
def set_feature(user_id: int, feature: str, payload: FeatureFlagUpdate) -> dict[str, Any]:
    if feature not in DEFAULT_FLAGS:
        raise HTTPException(400, "Invalid feature")
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO feature_flags(user_id, feature_name, enabled) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, feature_name) DO UPDATE SET enabled=excluded.enabled",
            (user_id, feature, int(payload.enabled)),
        )
        return {"ok": True}


@app.put("/api/users/{user_id}/max-investment")
def set_max_investment(user_id: int, payload: dict[str, float], user: sqlite3.Row = Depends(get_current_user)) -> dict[str, Any]:
    if user["role"] != "admin" and user["id"] != user_id:
        raise HTTPException(403, "Forbidden")
    value = float(payload.get("value", 0))
    with db_conn() as conn:
        conn.execute("UPDATE users SET max_investment_per_stock=? WHERE id=?", (value, user_id))
    return {"ok": True}


@app.post("/api/trades")
def place_trade(payload: TradeRequest, user: sqlite3.Row = Depends(get_current_user)) -> dict[str, Any]:
    with db_conn() as conn:
        target_users = [user["id"]]
        if user["role"] == "admin" and payload.user_ids:
            target_users = payload.user_ids

        status = "executed" if market_is_open() else "open"
        created = []
        for uid in target_users:
            broker = KiteBroker.place_order(payload.symbol, payload.side, payload.quantity, payload.price)
            cur = conn.execute(
                "INSERT INTO orders(user_id, symbol, side, quantity, price, status, broker_payload, created_at, executed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uid,
                    payload.symbol,
                    payload.side,
                    payload.quantity,
                    payload.price,
                    status,
                    json.dumps(broker),
                    now_iso(),
                    now_iso() if status == "executed" else None,
                ),
            )
            if status == "executed":
                apply_execution(conn, cur.lastrowid)
            created.append(cur.lastrowid)
        return {"order_ids": created, "status": status}


@app.post("/api/orders/{order_id}/execute", dependencies=[Depends(require_admin)])
def execute_open_order(order_id: int) -> dict[str, Any]:
    with db_conn() as conn:
        conn.execute("UPDATE orders SET status='executed', executed_at=? WHERE id=? AND status='open'", (now_iso(), order_id))
        apply_execution(conn, order_id)
        return {"executed": True}


@app.get("/api/orders")
def list_orders(user: sqlite3.Row = Depends(get_current_user)) -> list[dict[str, Any]]:
    with db_conn() as conn:
        if user["role"] == "admin":
            rows = conn.execute(
                "SELECT o.*, u.username FROM orders o JOIN users u ON o.user_id=u.id ORDER BY o.id DESC LIMIT 200"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 200", (user["id"],)).fetchall()
        return [serialize_row(r) for r in rows]


@app.get("/api/portfolio")
def portfolio(user: sqlite3.Row = Depends(get_current_user)) -> dict[str, Any]:
    with db_conn() as conn:
        if user["role"] == "admin":
            rows = conn.execute(
                "SELECT h.*, u.username FROM holdings h JOIN users u ON h.user_id=u.id ORDER BY h.user_id"
            ).fetchall()
            return {"holdings": [serialize_row(r) for r in rows]}
        rows = conn.execute("SELECT * FROM holdings WHERE user_id=?", (user["id"],)).fetchall()
        return {"holdings": [serialize_row(r) for r in rows]}


@app.get("/api/funds")
def funds(user: sqlite3.Row = Depends(get_current_user)) -> dict[str, Any]:
    with db_conn() as conn:
        rows = conn.execute("SELECT balance FROM funds WHERE user_id=?", (user["id"],)).fetchone()
        return {"balance": rows["balance"] if rows else 0}


@app.post("/api/watchlists")
def create_watchlist(payload: WatchlistRequest, user: sqlite3.Row = Depends(get_current_user)) -> dict[str, Any]:
    with db_conn() as conn:
        cur = conn.execute("INSERT INTO watchlists(user_id, name) VALUES (?, ?)", (user["id"], payload.name))
        return {"watchlist_id": cur.lastrowid}


@app.get("/api/watchlists")
def list_watchlists(user: sqlite3.Row = Depends(get_current_user)) -> list[dict[str, Any]]:
    with db_conn() as conn:
        lists = conn.execute("SELECT * FROM watchlists WHERE user_id=?", (user["id"],)).fetchall()
        output = []
        for w in lists:
            items = conn.execute("SELECT symbol FROM watchlist_items WHERE watchlist_id=?", (w["id"],)).fetchall()
            d = serialize_row(w)
            d["symbols"] = [i["symbol"] for i in items]
            output.append(d)
        return output


@app.post("/api/watchlists/{watchlist_id}/items")
def add_watchlist_item(watchlist_id: int, payload: WatchlistItemRequest, user: sqlite3.Row = Depends(get_current_user)) -> dict[str, Any]:
    with db_conn() as conn:
        watchlist = conn.execute("SELECT * FROM watchlists WHERE id=?", (watchlist_id,)).fetchone()
        if not watchlist or watchlist["user_id"] != user["id"]:
            raise HTTPException(404, "Watchlist not found")
        conn.execute("INSERT OR IGNORE INTO watchlist_items(watchlist_id, symbol) VALUES (?, ?)", (watchlist_id, payload.symbol))
        return {"ok": True}


@app.post("/api/alerts")
def create_alert(payload: AlertRequest, user: sqlite3.Row = Depends(get_current_user)) -> dict[str, Any]:
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO alerts(user_id, symbol, condition, value, duration, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], payload.symbol, payload.condition, payload.value, payload.duration, now_iso()),
        )
        return {"alert_id": cur.lastrowid}


@app.get("/api/alerts")
def list_alerts(user: sqlite3.Row = Depends(get_current_user)) -> list[dict[str, Any]]:
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM alerts WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
        return [serialize_row(r) for r in rows]


@app.post("/api/conditional-orders")
def create_conditional_order(payload: ConditionalOrderRequest, user: sqlite3.Row = Depends(get_current_user)) -> dict[str, Any]:
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO conditional_orders(user_id, symbol, action, condition_type, trigger_value, quantity, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user["id"],
                payload.symbol,
                payload.action,
                payload.condition_type,
                payload.trigger_value,
                payload.quantity,
                now_iso(),
            ),
        )
        return {"conditional_order_id": cur.lastrowid}


@app.get("/api/conditional-orders")
def list_conditional_orders(user: sqlite3.Row = Depends(get_current_user)) -> list[dict[str, Any]]:
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM conditional_orders WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
        return [serialize_row(r) for r in rows]
