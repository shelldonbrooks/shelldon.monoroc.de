#!/usr/bin/env python3
"""
Initialize or migrate the food SQLite database.
Run this once to create the schema.

Usage: python3 scripts/db_init.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'src', 'data', 'food.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS restaurants (
            slug        TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            address     TEXT,
            cuisine     TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS orders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_slug TEXT NOT NULL REFERENCES restaurants(slug),
            date          TEXT NOT NULL,   -- YYYY-MM-DD
            time          TEXT,            -- HH:MM
            source        TEXT DEFAULT 'Wolt',
            order_number  TEXT,
            tip           REAL DEFAULT 0,
            service_fee   REAL DEFAULT 0,
            discount      REAL DEFAULT 0,
            delivery_fee  REAL DEFAULT 0,
            rating        INTEGER,         -- NULL = ausstehend
            notes         TEXT,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            qty         INTEGER DEFAULT 1,
            unit_price  REAL DEFAULT 0
        );
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized: {os.path.abspath(DB_PATH)}")

if __name__ == '__main__':
    init_db()
