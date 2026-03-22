#!/usr/bin/env python3
"""
Export food.db → orders.json (for Astro static build).
Run this after any DB change, then run deploy.sh.

Usage: python3 scripts/db_to_json.py
"""

import sqlite3
import json
import os

BASE = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE, '..', 'src', 'data', 'food.db')
JSON_PATH = os.path.join(BASE, '..', 'src', 'data', 'orders.json')

def export_to_json():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    restaurants = c.execute("SELECT * FROM restaurants ORDER BY name").fetchall()
    result = {}

    for r in restaurants:
        slug = r['slug']
        orders = c.execute("""
            SELECT * FROM orders
            WHERE restaurant_slug = ?
            ORDER BY date ASC, time ASC
        """, (slug,)).fetchall()

        orders_list = []
        for o in orders:
            items = c.execute("""
                SELECT * FROM order_items WHERE order_id = ? ORDER BY id
            """, (o['id'],)).fetchall()

            order_dict = {
                'date': o['date'],
                'time': o['time'],
                'source': o['source'],
                'items': [
                    {
                        'name': i['name'],
                        'qty': i['qty'],
                        'unitPrice': i['unit_price'],
                    }
                    for i in items
                ],
            }
            if o['order_number']:
                order_dict['orderNumber'] = o['order_number']
            if o['tip']:
                order_dict['tip'] = o['tip']
            if o['service_fee']:
                order_dict['serviceFee'] = o['service_fee']
            if o['discount']:
                order_dict['discount'] = o['discount']
            if o['delivery_fee']:
                order_dict['deliveryFee'] = o['delivery_fee']
            if o['rating'] is not None:
                order_dict['rating'] = o['rating']
            if o['notes']:
                order_dict['notes'] = o['notes']

            orders_list.append(order_dict)

        result[slug] = {
            'name': r['name'],
            'slug': slug,
            'address': r['address'] or '',
            'orders': orders_list,
        }
        if r['cuisine']:
            result[slug]['cuisine'] = r['cuisine']

    conn.close()

    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Exported {len(result)} restaurants to {JSON_PATH}")
    for slug, rest in result.items():
        print(f"  {rest['name']}: {len(rest['orders'])} orders")

if __name__ == '__main__':
    export_to_json()
