#!/usr/bin/env python3
"""
Migrate orders.json → food.db (one-time migration).
Safe to run multiple times — uses INSERT OR IGNORE for restaurants,
checks order_number uniqueness for orders.

Usage: python3 scripts/migrate_json_to_db.py
"""

import sqlite3
import json
import os

BASE = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE, '..', 'src', 'data', 'food.db')
JSON_PATH = os.path.join(BASE, '..', 'src', 'data', 'orders.json')

def migrate():
    # Init DB first
    import db_init
    db_init.init_db()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    inserted_restaurants = 0
    inserted_orders = 0
    skipped_orders = 0

    for slug, restaurant in data.items():
        name = restaurant.get('name', slug)
        address = restaurant.get('address')
        cuisine = restaurant.get('cuisine')

        c.execute("""
            INSERT OR IGNORE INTO restaurants (slug, name, address, cuisine)
            VALUES (?, ?, ?, ?)
        """, (slug, name, address, cuisine))
        if c.rowcount:
            inserted_restaurants += 1

        for order in restaurant.get('orders', []):
            order_number = order.get('orderNumber')

            # Skip if order_number already in DB
            if order_number:
                c.execute("SELECT id FROM orders WHERE order_number = ?", (order_number,))
                if c.fetchone():
                    skipped_orders += 1
                    continue

            c.execute("""
                INSERT INTO orders
                    (restaurant_slug, date, time, source, order_number,
                     tip, service_fee, discount, delivery_fee, rating, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                slug,
                order.get('date'),
                order.get('time'),
                order.get('source', 'Wolt'),
                order_number,
                order.get('tip', 0),
                order.get('serviceFee', 0),
                order.get('discount', 0),
                order.get('deliveryFee', 0),
                order.get('rating'),
                order.get('notes'),
            ))
            order_id = c.lastrowid
            inserted_orders += 1

            for item in order.get('items', []):
                c.execute("""
                    INSERT INTO order_items (order_id, name, qty, unit_price)
                    VALUES (?, ?, ?, ?)
                """, (
                    order_id,
                    item.get('name', ''),
                    item.get('qty', 1),
                    item.get('unitPrice', 0),
                ))

    conn.commit()
    conn.close()

    print(f"Migration complete:")
    print(f"  Restaurants: {inserted_restaurants} inserted")
    print(f"  Orders:      {inserted_orders} inserted, {skipped_orders} skipped (already exist)")

if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    migrate()
