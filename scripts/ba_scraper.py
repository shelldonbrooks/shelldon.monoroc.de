#!/usr/bin/env python3
"""
BA-Sitzungen Scraper
Holt Sitzungsdaten von münchen-transparent.de und parst die RIS-Tagesordnungen.
Speichert alles in SQLite.
"""

import sqlite3
import json
import re
import sys
import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "../src/data/ba.db")
JSON_PATH = os.path.join(os.path.dirname(__file__), "../src/data/ba_sessions.json")

MT_BASE = "https://www.muenchen-transparent.de"
RIS_BASE = "https://risi.muenchen.de"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BA-Tracker/1.0)"}


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mt_id TEXT UNIQUE NOT NULL,
            date TEXT NOT NULL,
            time TEXT,
            location TEXT,
            ris_url TEXT,
            ris_session_id TEXT,
            mt_url TEXT,
            status TEXT DEFAULT 'upcoming'
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_mt_id TEXT NOT NULL,
            kind TEXT NOT NULL,   -- 'to', 'nachtrag', 'protokoll', 'manual_protokoll'
            label TEXT,
            mt_doc_id TEXT,
            url TEXT,
            FOREIGN KEY (session_mt_id) REFERENCES sessions(mt_id)
        );

        CREATE TABLE IF NOT EXISTS agenda_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_mt_id TEXT NOT NULL,
            section TEXT,         -- 'A' Kultur, 'B' Mobilität, etc.
            item_type TEXT,       -- 'antrag', 'entscheidung', 'anhoerung', 'buerger', 'unterrichtung'
            item_number TEXT,
            title TEXT,
            ris_id TEXT,
            is_nachtrag INTEGER DEFAULT 0,
            FOREIGN KEY (session_mt_id) REFERENCES sessions(mt_id)
        );

        CREATE TABLE IF NOT EXISTS scrape_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_mt_id TEXT,
            scraped_at TEXT,
            source TEXT,
            success INTEGER,
            notes TEXT
        );
    """)
    db.commit()


def fetch(url, delay=0.5):
    time.sleep(delay)
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r


def scrape_session_list(ba_num=2, years_back=2):
    """Holt die Terminliste von münchen-transparent."""
    url = f"{MT_BASE}/bezirksausschuss/{ba_num}/termine"
    print(f"Lade Terminliste: {url}")
    r = fetch(url)
    soup = BeautifulSoup(r.text, "html.parser")

    sessions = []
    for item in soup.select("li"):
        h4 = item.find("h4")
        if not h4:
            continue
        a = h4.find("a")
        if not a or "/termine/" not in a.get("href", ""):
            continue

        mt_id = a["href"].split("/termine/")[1].rstrip("/")
        date_text = a.get_text(strip=True)

        # Dokument-Links sammeln
        docs = []
        for link in item.find_all("a"):
            href = link.get("href", "")
            label = link.get_text(strip=True)
            if "/dokumente/" in href:
                doc_id = href.split("/dokumente/")[1].rstrip("/")
                docs.append({"label": label, "mt_doc_id": doc_id, "href": href})

        sessions.append({
            "mt_id": mt_id,
            "date_text": date_text,
            "mt_url": f"{MT_BASE}/termine/{mt_id}",
            "docs": docs
        })

    return sessions


def parse_section_from_text(text):
    """Erkennt BA-Sektion aus Text."""
    if "Kultur" in text or "Jugend" in text or "Soziales" in text:
        return "A"
    elif "Mobilität" in text or "Straßenraum" in text:
        return "B"
    elif "Planung" in text or "Stadtentwicklung" in text or "Umwelt" in text:
        return "C"
    elif "Sicherheit" in text or "Ordnung" in text:
        return "D"
    return None


def parse_type_from_text(text):
    """Erkennt Agenda-Typ aus Text."""
    t = text.strip().rstrip(":")
    if t == "Anträge" or t.endswith(": Anträge"):
        return "antrag"
    elif "Entscheidungen" in text:
        return "entscheidung"
    elif "Anhörungen" in text:
        return "anhoerung"
    elif "Bürger" in text and "Sonstiges" in text:
        return "buerger"
    elif "Unterrichtungen" in text:
        return "unterrichtung"
    elif "Berichte" in text:
        return "bericht"
    return None


def scrape_session_detail(mt_id):
    """
    Holt Details zu einer Sitzung von münchen-transparent.
    Parst die TO-Liste sauber: nur direkte li-Kinder ohne ul.doks als Kinder.
    """
    url = f"{MT_BASE}/termine/{mt_id}"
    print(f"  Detail: {url}")
    r = fetch(url)
    soup = BeautifulSoup(r.text, "html.parser")

    data = {"items": []}

    # Datum/Zeit aus h1
    h1 = soup.find("h1")
    if h1:
        m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", h1.get_text())
        if m:
            data["date"] = m.group(1)
            data["time"] = m.group(2)

    if "date" not in data:
        # Fallback: suche nach Datum im Text
        for el in soup.find_all(string=re.compile(r"\d{2}\.\d{2}\.\d{4}")):
            m = re.search(r"(\d{2})\.(\d{2})\.(\d{4}),\s*(\d{2}:\d{2})", el)
            if m:
                data["date"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                data["time"] = m.group(4)
                break

    # Ort aus der DL/DT-Struktur oder regulärem Text
    for dl in soup.find_all("dl"):
        for dt in dl.find_all("dt"):
            if "Ort" in dt.get_text():
                dd = dt.find_next_sibling("dd")
                if dd:
                    data["location"] = dd.get_text(strip=True)

    # RIS-Link
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "risi.muenchen.de" in href and "/sitzung/detail/" in href:
            # Normalisiere auf Basis-URL ohne Tagesordnung-Suffix
            base = re.sub(r"/tagesordnung.*$", "", href)
            data["ris_url"] = base
            m = re.search(r"/sitzung/detail/(\d+)", href)
            if m:
                data["ris_session_id"] = m.group(1)
            break

    # Tagesordnung parsen
    # Struktur: h3 "Tagesordnung", dann ul > li-Items
    # Items haben Nummern wie "2.1.:" am Anfang
    # Sub-Dokumente stehen in ul.doks innerhalb des li

    to_section = soup.find("h3", string=re.compile(r"^Tagesordnung$"))
    if not to_section:
        to_section = soup.find("h3", string=re.compile(r"Tagesordnung"))

    if to_section:
        current_section = None
        current_type = None
        items = []

        # Iteriere alle li-Elemente nach dem Tagesordnung-Header
        for el in to_section.find_all_next():
            if el.name == "h3" and el != to_section:
                break  # nächste Sektion

            if el.name != "li":
                continue

            # Überspringe li-Kinder von ul.doks (Dokument-Links)
            parent_ul = el.find_parent("ul")
            if parent_ul and "doks" in parent_ul.get("class", []):
                continue

            # Nur direkten Text des li (ohne ul.doks Kinder)
            doks_ul = el.find("ul", class_="doks")
            if doks_ul:
                doks_ul.extract()  # temporär entfernen für Text
            raw_text = el.get_text(separator=" ", strip=True)
            if doks_ul:
                el.append(doks_ul)  # wiederherstellen

            text = re.sub(r"\s+", " ", raw_text).strip()

            if not text:
                continue

            # Sektion erkennen (z.B. "A: Bereich Unterausschuss Kultur...")
            sec = parse_section_from_text(text)
            if sec and (text.startswith(("A:", "B:", "C:", "D:")) or "Bereich Unterausschuss" in text):
                current_section = sec
                current_type = None
                continue

            # Typ erkennen (z.B. "1: Anträge")
            typ = parse_type_from_text(text)
            if typ and re.match(r"^\d+:", text):
                current_type = typ
                continue

            # Gliederungs-Header ohne Items überspringen
            if re.match(r"^[IVX]+:", text) or re.match(r"^[A-Z]:", text) or re.match(r"^\d+:", text):
                # Könnte ein Unter-Gliederungspunkt sein
                sub_typ = parse_type_from_text(text)
                if sub_typ:
                    current_type = sub_typ
                sub_sec = parse_section_from_text(text)
                if sub_sec:
                    current_section = sub_sec
                # Kein item hinzufügen
                continue

            # Echter Agenda-Item: beginnt mit Nummer wie "2.1.:", "1.", etc.
            num_m = re.match(r"^(\d[\d\.]*\.?):?\s*", text)
            if not num_m:
                continue

            item_num = num_m.group(1).rstrip(".")
            title = text[num_m.end():].strip()
            if not title:
                continue

            # Antrag-Link
            antrag_link = el.find("a", href=lambda h: h and "/antraege/" in h)
            ris_id = None
            if antrag_link:
                m2 = re.search(r"/antraege/(\d+)", antrag_link["href"])
                if m2:
                    ris_id = m2.group(1)

            is_nachtrag = 1 if "Nachtrag" in el.get_text() else 0

            items.append({
                "section": current_section,
                "item_type": current_type,
                "item_number": item_num,
                "title": title[:300],
                "ris_id": ris_id,
                "is_nachtrag": is_nachtrag
            })

        data["items"] = items

    return data


def parse_ris_to(ris_session_id):
    """Nicht mehr nötig — RIS blockiert direkte Anfragen. MT ist die Quelle."""
    return [], None


def classify_doc(label):
    """Ordnet ein Dokument einem Typ zu."""
    label_lower = label.lower()
    if "nachtrag" in label_lower:
        return "nachtrag"
    elif "prot" in label_lower or "protokoll" in label_lower:
        return "protokoll"
    elif "tagesordnung" in label_lower or label_lower == "tagesordnung":
        return "to"
    else:
        return "other"


def save_session(db, mt_id, date, time_str, location, ris_url, ris_session_id, mt_url):
    db.execute("""
        INSERT INTO sessions (mt_id, date, time, location, ris_url, ris_session_id, mt_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mt_id) DO UPDATE SET
            date=excluded.date, time=excluded.time, location=excluded.location,
            ris_url=excluded.ris_url, ris_session_id=excluded.ris_session_id, mt_url=excluded.mt_url
    """, (mt_id, date, time_str, location, ris_url, ris_session_id, mt_url))
    db.commit()


def save_documents(db, session_mt_id, docs):
    # Alte Docs dieser Session löschen und neu einfügen
    db.execute("DELETE FROM documents WHERE session_mt_id = ?", (session_mt_id,))
    for doc in docs:
        kind = classify_doc(doc.get("label", ""))
        url = f"{MT_BASE}{doc['href']}" if doc.get("href", "").startswith("/") else doc.get("href", "")
        db.execute("""
            INSERT INTO documents (session_mt_id, kind, label, mt_doc_id, url)
            VALUES (?, ?, ?, ?, ?)
        """, (session_mt_id, kind, doc.get("label"), doc.get("mt_doc_id"), url))
    db.commit()


def save_agenda_items(db, session_mt_id, items):
    db.execute("DELETE FROM agenda_items WHERE session_mt_id = ?", (session_mt_id,))
    for item in items:
        db.execute("""
            INSERT INTO agenda_items (session_mt_id, section, item_type, item_number, title, ris_id, is_nachtrag)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session_mt_id,
            item.get("section"),
            item.get("item_type"),
            item.get("item_number"),
            item.get("title"),
            item.get("ris_id"),
            item.get("is_nachtrag", 0)
        ))
    db.commit()


def compute_status(session_row, docs, items):
    """Berechnet den Vollständigkeitsstatus einer Sitzung."""
    now = datetime.now().strftime("%Y-%m-%d")
    session_date = session_row["date"] if isinstance(session_row, dict) else session_row[1]

    has_to = any(d["kind"] in ("to", "nachtrag") for d in docs)
    has_protokoll = any(d["kind"] in ("protokoll", "manual_protokoll") for d in docs)
    has_items = len(items) > 0
    is_past = session_date < now

    if not is_past:
        if has_to and has_items:
            return "to_complete"
        elif has_to:
            return "to_partial"
        else:
            return "upcoming"
    else:
        if has_protokoll and has_items:
            return "complete"
        elif has_protokoll:
            return "protokoll_only"
        elif has_to and has_items:
            return "to_complete"
        elif has_to:
            return "to_only"
        else:
            return "empty"


def export_json(db):
    """Exportiert alle Sitzungsdaten als JSON für Astro."""
    sessions = []

    for row in db.execute("SELECT * FROM sessions ORDER BY date DESC").fetchall():
        mt_id = row["mt_id"]

        docs = [dict(d) for d in db.execute(
            "SELECT * FROM documents WHERE session_mt_id = ?", (mt_id,)
        ).fetchall()]

        items = [dict(i) for i in db.execute(
            "SELECT * FROM agenda_items WHERE session_mt_id = ?", (mt_id,)
        ).fetchall()]

        # Antrag-Zählung
        antraege = [i for i in items if i["item_type"] == "antrag"]
        entscheidungen = [i for i in items if i["item_type"] == "entscheidung"]
        anhoerungen = [i for i in items if i["item_type"] == "anhoerung"]

        status = compute_status(row, docs, items)

        sessions.append({
            "mt_id": row["mt_id"],
            "date": row["date"],
            "time": row["time"],
            "location": row["location"],
            "ris_url": row["ris_url"],
            "ris_session_id": row["ris_session_id"],
            "mt_url": row["mt_url"],
            "status": status,
            "documents": docs,
            "items": items,
            "counts": {
                "total": len(items),
                "antraege": len(antraege),
                "entscheidungen": len(entscheidungen),
                "anhoerungen": len(anhoerungen),
            }
        })

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)

    print(f"Exportiert: {len(sessions)} Sitzungen → {JSON_PATH}")
    return sessions


def run_scrape(ba_num=2, limit=None, force=False):
    db = get_db()
    init_db(db)

    print(f"\n=== BA {ba_num} Sitzungen Scraper ===\n")
    session_list = scrape_session_list(ba_num)
    print(f"Gefunden: {len(session_list)} Sitzungen\n")

    processed = 0
    for s in session_list:
        if limit and processed >= limit:
            break

        mt_id = s["mt_id"]
        existing = db.execute("SELECT * FROM sessions WHERE mt_id = ?", (mt_id,)).fetchone()

        # Nur scrapen wenn nötig (oder force)
        if existing and not force:
            # Prüfen ob wir schon Items haben
            item_count = db.execute(
                "SELECT COUNT(*) FROM agenda_items WHERE session_mt_id = ?", (mt_id,)
            ).fetchone()[0]
            if item_count > 0:
                print(f"  Skip {mt_id} (bereits {item_count} Items)")
                continue

        print(f"\nVerarbeite Sitzung {mt_id}...")
        try:
            detail = scrape_session_detail(mt_id)

            date = detail.get("date", "")
            if not date:
                # Fallback aus date_text
                dt = s.get("date_text", "")
                m = re.search(r"(\d+)\.\s*(\w+)\s*(?:(\d{4}),)?", dt)
                if m:
                    date = f"2026-01-01"  # Fallback

            save_session(
                db, mt_id,
                date=detail.get("date", ""),
                time_str=detail.get("time", "19:00"),
                location=detail.get("location", ""),
                ris_url=detail.get("ris_url", ""),
                ris_session_id=detail.get("ris_session_id", ""),
                mt_url=s["mt_url"]
            )

            save_documents(db, mt_id, s["docs"])

            items = detail.get("items", [])

            if items:
                save_agenda_items(db, mt_id, items)
                print(f"  ✓ {len(items)} Agenda-Items gespeichert")
            else:
                print(f"  ⚠ Keine Agenda-Items gefunden")

            db.execute("""
                INSERT INTO scrape_log (session_mt_id, scraped_at, source, success, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (mt_id, datetime.now().isoformat(), "mt+ris", 1, f"{len(items)} items"))
            db.commit()

            processed += 1

        except Exception as e:
            print(f"  FEHLER bei {mt_id}: {e}")
            db.execute("""
                INSERT INTO scrape_log (session_mt_id, scraped_at, source, success, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (mt_id, datetime.now().isoformat(), "mt+ris", 0, str(e)))
            db.commit()

    export_json(db)
    db.close()
    print("\nFertig!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BA-Sitzungen Scraper")
    parser.add_argument("--ba", type=int, default=2, help="Bezirksausschuss Nummer")
    parser.add_argument("--limit", type=int, default=None, help="Max Sitzungen")
    parser.add_argument("--force", action="store_true", help="Alle neu scrapen")
    parser.add_argument("--export-only", action="store_true", help="Nur JSON exportieren")
    args = parser.parse_args()

    if args.export_only:
        db = get_db()
        init_db(db)
        export_json(db)
        db.close()
    else:
        run_scrape(ba_num=args.ba, limit=args.limit, force=args.force)
