#!/usr/bin/env python3
"""
Add a new order to food.db (used by heartbeat flow instead of editing JSON directly).
After adding, auto-exports to orders.json and triggers deploy.

Usage:
    python3 scripts/add_order.py --json '{...}'
    python3 scripts/add_order.py --file /tmp/order_data.json

Expected JSON format:
{
  "restaurant": {
    "slug": "malatang",
    "name": "Malatang 麻辣煮義",
    "address": "...",
    "cuisine": "Chinese"
  },
  "order": {
    "date": "2026-03-22",
    "time": "19:30",
    "source": "Wolt",
    "orderNumber": "abc123",
    "tip": 0,
    "serviceFee": 0.83,
    "discount": 0,
    "deliveryFee": 0,
    "rating": null,
    "notes": null,
    "items": [
      {"name": "Malatang Basis", "qty": 1, "unitPrice": 12.90}
    ]
  }
}
"""

import sqlite3
import json
import os
import sys

BASE = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE, '..', 'src', 'data', 'food.db')

def add_order(data: dict) -> int:
    """Insert order into DB. Returns order ID."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Upsert restaurant
    r = data['restaurant']
    c.execute("""
        INSERT INTO restaurants (slug, name, address, cuisine)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            name = excluded.name,
            address = COALESCE(excluded.address, address),
            cuisine = COALESCE(excluded.cuisine, cuisine)
    """, (r['slug'], r['name'], r.get('address'), r.get('cuisine')))

    # Check duplicate by orderNumber
    o = data['order']
    order_number = o.get('orderNumber')
    if order_number:
        c.execute("SELECT id FROM orders WHERE order_number = ?", (order_number,))
        existing = c.fetchone()
        if existing:
            print(f"Order {order_number} already exists (id={existing[0]}), skipping insert.")
            conn.close()
            return existing[0]

    c.execute("""
        INSERT INTO orders
            (restaurant_slug, date, time, source, order_number,
             tip, service_fee, discount, delivery_fee, rating, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        r['slug'],
        o['date'],
        o.get('time'),
        o.get('source', 'Wolt'),
        order_number,
        o.get('tip', 0),
        o.get('serviceFee', 0),
        o.get('discount', 0),
        o.get('deliveryFee', 0),
        o.get('rating'),
        o.get('notes'),
    ))
    order_id = c.lastrowid

    for item in o.get('items', []):
        c.execute("""
            INSERT INTO order_items (order_id, name, qty, unit_price)
            VALUES (?, ?, ?, ?)
        """, (order_id, item['name'], item.get('qty', 1), item.get('unitPrice', 0)))

    conn.commit()
    conn.close()
    print(f"Inserted order id={order_id} for {r['name']} on {o['date']}")
    return order_id


def update_rating(order_number: str, rating: int, notes: str = None) -> bool:
    """Update rating (and optionally notes) for an existing order by orderNumber."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if notes is not None:
        c.execute(
            "UPDATE orders SET rating = ?, notes = ? WHERE order_number = ?",
            (rating, notes, order_number)
        )
    else:
        c.execute(
            "UPDATE orders SET rating = ? WHERE order_number = ?",
            (rating, order_number)
        )
    updated = c.rowcount
    conn.commit()
    conn.close()
    if updated:
        print(f"Updated rating={rating} for order {order_number}")
        return True
    else:
        print(f"Order {order_number} not found.")
        return False


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--json', help='Order data as JSON string')
    group.add_argument('--file', help='Path to JSON file with order data')
    group.add_argument('--rate', nargs=3, metavar=('ORDER_NUMBER', 'RATING', 'NOTES'),
                       help='Update rating for an existing order')
    args = parser.parse_args()

    if args.rate:
        order_number, rating_str, notes = args.rate
        update_rating(order_number, int(rating_str), notes if notes != 'null' else None)
    else:
        if args.json:
            data = json.loads(args.json)
        else:
            with open(args.file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        add_order(data)

    # Re-export to JSON for Astro
    sys.path.insert(0, BASE)
    import db_to_json
    db_to_json.export_to_json()
