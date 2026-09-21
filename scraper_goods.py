"""公式サイトの商品一覧ページから、拡張パック/構築済みデッキ/周辺グッズの一覧を取得するモジュール。

https://www.onepiece-cardgame.com/products/?view=normal は一覧表示に専用の
JSON APIを持たず、サーバーサイドレンダリングされたHTMLをそのまま返す。
ページ内の `li.linkListColBox` を1件ずつBeautifulSoupでパースする。ページングは
`?view=normal&page=N`で、末尾ページはページ内のページネーションリンクから
毎回動的に検出する(商品数が増えてページが増えても追従できるように)。

商品画像はカード画像(images/cardlist/card/配下)と違い
`Cross-Origin-Resource-Policy`ヘッダが付いていないことを確認済みのため、
カード画像のような自サイトホスティングは行わずホットリンクする。
"""
import logging
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import db

BASE_URL = "https://www.onepiece-cardgame.com"
LIST_URL = f"{BASE_URL}/products/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
REQUEST_TIMEOUT = 15
REQUEST_DELAY_SEC = 1.0

CATEGORY_LABELS = {
    "boosters": "ブースター",
    "decks": "デッキ",
    "others": "その他",
}

PRICE_PATTERN = re.compile(r"([\d,]+)円")
PAGE_LINK_PATTERN = re.compile(r"page=(\d+)")

logger = logging.getLogger(__name__)


def _parse_price_yen(text: str | None) -> int | None:
    m = PRICE_PATTERN.search(text or "")
    return int(m.group(1).replace(",", "")) if m else None


def parse_items(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for li in soup.select("li.linkListColBox"):
        title_el = li.select_one(".linkListColTitle")
        link_el = li.select_one("a.linkListColItem")
        if not title_el or not link_el:
            continue

        category = li.get("data-cat") or "others"
        cat_label_el = li.select_one(".linkListColCat")
        tag_el = li.select_one(".linkListColTag")
        date_el = li.select_one(".linkListColDate time")
        price_el = li.select_one(".linkListColPrice .data")
        img_el = li.select_one(".linkListColThumb img")

        href = link_el.get("href")
        detail_url = href if (href and href.startswith("http")) else (f"{BASE_URL}{href}" if href else None)

        image_url = None
        if img_el:
            src = img_el.get("data-src") or img_el.get("src")
            if src:
                image_url = src if src.startswith("http") else f"{BASE_URL}{src}"

        price_text = price_el.get_text(strip=True) if price_el else None
        items.append({
            "title": title_el.get_text(strip=True),
            "category": category,
            "category_label": cat_label_el.get_text(strip=True) if cat_label_el else CATEGORY_LABELS.get(category, "その他"),
            "tag": tag_el.get_text(strip=True) if tag_el else None,
            "release_date": date_el.get("datetime") if date_el else None,
            "price_text": price_text,
            "price_yen": _parse_price_yen(price_text),
            "image_url": image_url,
            "detail_url": detail_url,
        })
    return items


def fetch_page(page: int) -> str:
    resp = requests.get(LIST_URL, params={"view": "normal", "page": page}, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _last_page(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    last = 1
    for a in soup.select('a[href*="page="]'):
        m = PAGE_LINK_PATTERN.search(a["href"])
        if m:
            last = max(last, int(m.group(1)))
    return last


def sync_all_goods(conn=None) -> dict:
    own_conn = conn is None
    if own_conn:
        conn = db.get_connection()
        db.init_db(conn)

    try:
        html = fetch_page(1)
        last_page = _last_page(html)
        all_items = parse_items(html)
        for page in range(2, last_page + 1):
            time.sleep(REQUEST_DELAY_SEC)
            all_items.extend(parse_items(fetch_page(page)))

        result = db.upsert_goods(conn, all_items)
        logger.info("goods: 新規%d件 / 更新%d件 / 合計%d件", result["new"], result["updated"], result["total"])
        return result
    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sync_all_goods()
