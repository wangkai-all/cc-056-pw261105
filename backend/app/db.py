"""SQLite 连接与表结构。金额/数量一律以 TEXT 存 Decimal 字符串，避免浮点误差。"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "billing.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS service_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    unit       TEXT NOT NULL DEFAULT '次',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS billing_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     INTEGER NOT NULL REFERENCES customers(id),
    service_item_id INTEGER NOT NULL REFERENCES service_items(id),
    effective_from  TEXT NOT NULL,          -- YYYY-MM-DD，自然日零点生效
    fixed_fee       TEXT NOT NULL,          -- Decimal
    minimum_charge  TEXT NOT NULL,          -- Decimal
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (customer_id, service_item_id, effective_from)
);

CREATE TABLE IF NOT EXISTS rule_tiers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id    INTEGER NOT NULL REFERENCES billing_rules(id) ON DELETE CASCADE,
    tier_no    INTEGER NOT NULL,
    up_to      TEXT,                        -- Decimal，NULL = 不限量（最后一档）
    unit_price TEXT NOT NULL                -- Decimal
);

CREATE TABLE IF NOT EXISTS usage_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_no       TEXT NOT NULL UNIQUE,   -- 唯一编号：重复导入不再计费
    customer_id     INTEGER NOT NULL REFERENCES customers(id),
    service_item_id INTEGER NOT NULL REFERENCES service_items(id),
    occurred_on     TEXT NOT NULL,          -- 发生日期 YYYY-MM-DD
    quantity        TEXT NOT NULL,          -- Decimal，冲正单存正数、计费时取负
    kind            TEXT NOT NULL DEFAULT 'usage',  -- usage | reversal
    reversal_of_id  INTEGER REFERENCES usage_records(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS bills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_no         TEXT NOT NULL UNIQUE,
    customer_id     INTEGER NOT NULL REFERENCES customers(id),
    service_item_id INTEGER NOT NULL REFERENCES service_items(id),
    period          TEXT NOT NULL,          -- YYYY-MM
    kind            TEXT NOT NULL,          -- original | correction
    amount          TEXT NOT NULL,          -- Decimal，本单金额（更正单为差额，可负）
    month_total     TEXT NOT NULL,          -- Decimal，封存时重算的当月应付合计
    status          TEXT NOT NULL DEFAULT 'sealed',  -- 封存账单不覆盖
    detail          TEXT NOT NULL,          -- JSON 明细快照，可追到规则与用量
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


def db_path() -> str:
    return os.environ.get("BILLING_DB", str(DEFAULT_DB))


@contextmanager
def db():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
