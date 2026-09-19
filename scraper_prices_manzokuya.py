"""カードショップ「まんぞく屋」(shopmanzokuya.com)からワンピースカードゲームの
価格を取得し price_history に保存するモジュール。

EC-CUBE系のECカートシステムを使っており、商品名に「OP17-079」のような形式で
DBの`card_num`と完全一致するカード番号がそのまま含まれている。ただし収録パック名
(「【OP-17】」のようにハイフンの後が2桁)と実カード番号(「OP17-079」のように
文字の直後に数字が付き、ハイフンの後は3桁)は桁数のパターンで区別できる。

対象カテゴリ(category_id=2636)がワンピースカードゲームの単品カードをまとめている。
まんぞく屋のrobots.txtは`/*.csv$`のみDisallowで一般クローラーへの制限が無いが、
他サイトと同様に安全側でリクエスト間隔30秒を採用する。
"""
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import db
import price_matching
from unresolved_report import write_unresolved

BASE_URL = "https://shopmanzokuya.com"
LIST_URL = BASE_URL + "/products/list"
CATEGORY_ID = 2636
PAGE_SIZE = 100

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 15
REQUEST_DELAY_SEC = 30
MAX_PAGES = 30

# 実カード番号: 文字1〜3+数字1〜2+ハイフン+数字3桁 (例: OP17-079, EB04-061, ST31-004)、
# もしくはプロモの P-107 のような形式。「【OP-17】」のようなパック名(ハイフン後2桁)は
# 文字の直後に数字が無いため、このパターンにはマッチしない。
CARD_NUM_PATTERN = re.compile(r"\b([A-Z]{1,3}\d{1,2}-\d{3}|P-\d{3})\b")

TOTAL_COUNT_PATTERN = re.compile(r"(\d+)件")

logger = logging.getLogger(__name__)


def fetch_page(page: int) -> str:
    params = {"category_id": CATEGORY_ID, "pageno": page}
    resp = requests.get(LIST_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_items(html: str) -> list[tuple[str, int, str, str | None, str | None]]:
    """(card_num, price, 商品名, 商品画像URL, 商品ページURL) のリストを返す。
    在庫0件(品切れ)や、単品カードとして特定できない商品(セット販売等)は除外する。
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for li in soup.select("li.ec-shelfGrid__item"):
        name_el = li.select_one(".ec-shelfGrid__item-text")
        if not name_el:
            continue

        stock_el = li.select_one(".productStock")
        if stock_el and re.search(r"在庫:0\b", stock_el.get_text(strip=True)):
            continue

        product_name = name_el.get_text(strip=True)
        m = CARD_NUM_PATTERN.search(product_name)
        if not m:
            continue
        card_num = m.group(0)

        price_el = li.select_one(".price02-default")
        if not price_el:
            continue
        price_text = price_el.get_text().replace("￥", "").replace(",", "")
        price_text = re.sub(r"\(税込\)", "", price_text).strip()
        try:
            price = int(price_text)
        except ValueError:
            continue

        link_el = li.find("a", href=True)
        product_url = urljoin(BASE_URL, link_el["href"]) if link_el else None
        img_el = li.select_one(".ec-shelfGrid__item-image img")
        image_url = urljoin(BASE_URL, img_el["src"]) if img_el and img_el.get("src") else None

        results.append((card_num, price, product_name, image_url, product_url))
    return results


def parse_total_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one(".ec-searchnavRole__counter .ec-font-bold")
    if not el:
        return 0
    m = TOTAL_COUNT_PATTERN.search(el.get_text())
    return int(m.group(1)) if m else 0


def sync_prices(conn=None, delay: float = REQUEST_DELAY_SEC, progress_callback=None) -> dict:
    """まんぞく屋からワンピースカードの価格を取得し price_history に保存する。

    progress_callback(page, last_page, matched_count) が指定されていれば
    ページ取得のたびに呼び出す。
    """
    owns_conn = conn is None
    if owns_conn:
        conn = db.get_connection()
        db.init_db(conn)

    lookup = price_matching.build_lookup(conn)
    manual_resolutions = price_matching.load_manual_resolutions()
    all_prices: dict[str, list[int]] = defaultdict(list)
    unresolved_entries: list[dict] = []
    first_request = True

    try:
        page = 1
        last_page = 1
        while page <= min(last_page, MAX_PAGES):
            if not first_request:
                time.sleep(delay)
            first_request = False

            try:
                html = fetch_page(page)
            except requests.RequestException as exc:
                logger.warning("まんぞく屋の取得に失敗 (page=%d): %s", page, exc)
                break

            if page == 1:
                total = parse_total_count(html)
                last_page = max(1, -(-total // PAGE_SIZE))  # 切り上げ除算

            for card_num, price, product_name, image_url, product_url in parse_items(html):
                price_matching.apply_resolution(
                    all_prices, unresolved_entries, card_num, None, price,
                    lookup, manual_resolutions, product_name, image_url, product_url,
                )

            if progress_callback:
                progress_callback(page, last_page, len(all_prices))

            page += 1

        run_recorded_at = datetime.now(timezone.utc).isoformat()
        for card_id, prices in all_prices.items():
            db.insert_price(
                conn, card_id, "まんぞく屋", min(prices),
                recorded_at=run_recorded_at, sample_count=len(prices),
            )

        write_unresolved("まんぞく屋", unresolved_entries)

        summary = {"matched_cards": len(all_prices), "unresolved_listings": len(unresolved_entries)}
        logger.info(
            "完了: %d枚の価格を取得 (特定できなかった出品 %d件は管理ページへ)",
            summary["matched_cards"], summary["unresolved_listings"],
        )
        return summary
    finally:
        if owns_conn:
            conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    def _print_progress(page, last_page, matched_count):
        logger.info("ページ%d/%d取得完了 (累計マッチ %d件)", page, last_page, matched_count)

    sync_prices(progress_callback=_print_progress)
