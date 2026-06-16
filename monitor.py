#!/usr/bin/env python3
"""
monitor.py — Telegram ping when a product appears on the SpaceX store.

Default behaviour: watches for KEYWORDS (e.g. a "doge plushie" called "Asteroid")
and pings the moment a matching product is published. Set NOTIFY_ALL_NEW=true to
ALSO get a quieter heads-up for any brand-new product, as a backup.

Pings once per product (won't re-spam). State is kept in alerted_products.json.
"""

import json
import os
import time
import pathlib
import requests

# ---- Config (set via env / GitHub secrets) --------------------------------
STORE = os.environ.get("STORE_URL", "https://shop.spacex.com")
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KEYWORDS = [k.strip().lower() for k in
            os.environ.get("KEYWORDS", "asteroid,doge,plush,plushie").split(",") if k.strip()]

NOTIFY_ALL_NEW = os.environ.get("NOTIFY_ALL_NEW", "false").lower() == "true"

STATE_FILE = pathlib.Path(os.environ.get("STATE_FILE", "alerted_products.json"))
USER_AGENT = "spacex-product-monitor/1.0 (personal use)"
# ---------------------------------------------------------------------------


def fetch_all_products(store: str) -> list[dict]:
    products, page = [], 1
    while True:
        url = f"{store}/products.json?limit=250&page={page}"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        page += 1
        time.sleep(1)
    return products


def matched_keyword(product: dict) -> str | None:
    tags = product.get("tags", [])
    tags = tags if isinstance(tags, list) else [str(tags)]
    haystack = " ".join([
        product.get("title", ""),
        product.get("body_html", ""),
        product.get("product_type", ""),
        " ".join(tags),
    ]).lower()
    for kw in KEYWORDS:
        if kw in haystack:
            return kw
    return None


def load_alerted() -> set[int]:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save_alerted(ids: set[int]) -> None:
    STATE_FILE.write_text(json.dumps(sorted(ids)))


def notify(product: dict, keyword: str | None) -> None:
    title = product.get("title", "Untitled")
    handle = product.get("handle", "")
    link = f"{STORE}/products/{handle}"
    variants = product.get("variants") or [{}]
    price = variants[0].get("price", "?")

    header = (f'🎯 *Keyword match: "{keyword}"*' if keyword
              else "🆕 *New item dropped*")
    text = f"{header}\n\n*{title}*\nPrice: ${price}\n{link}"

    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
              "parse_mode": "Markdown", "disable_web_page_preview": False},
        timeout=30,
    )
    r.raise_for_status()


def main() -> None:
    first_run = not STATE_FILE.exists()
    products = fetch_all_products(STORE)
    alerted = load_alerted()
    to_save = set(alerted)
    hits = 0

    for p in products:
        pid = p["id"]
        if pid in alerted:
            continue
        kw = matched_keyword(p)
        if kw:
            notify(p, kw)                 # keyword match: always alert
            to_save.add(pid)
