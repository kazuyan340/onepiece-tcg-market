"""カードショップわいTV(cardshop-waitv.net)からワンピースカードゲームの価格を
取得し price_history に保存するモジュール。

`/product-list/1` がワンピースカード専用カテゴリになっている。商品名は
「{カード名}（{パック略称} {カード番号} {レアリティ}） 状態{状態ランク}」という
形式(例: "ロックス・D・ジーベック（OP-17 OP17-118 SEC） 状態A-")で、全角括弧の
中身を空白区切りで見ると、パック略称(例: "OP-17")・カード番号(例: "OP17-118")・
レアリティ(例: "SEC")の3トークンになっている。同じカードでも状態(状態A/状態A-等)
違いで複数出品されるが、状態の違いは区別せずまとめて最安値を採用する。
"""
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

import db
import price_matching

BASE_URL = "https://www.cardshop-waitv.net/product-list/1"
PAGE_SIZE = 120

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 15
REQUEST_DELAY_SEC = 30
MAX_PAGES = 30

PAREN_CONTENT = re.compile(r"（([^（）]*)）")
CARD_NUM_PATTERN = re.compile(r"^([A-Z]{1,3}\d{1,2}-\d{3}|P-\d{3})$")
PACK_CODE_PATTERN = re.compile(r"^[A-Z]{1,3}-\d{1,2}$")

logger = logging.getLogger(__name__)


def fetch_page(page: int) -> str:
    params = {"num": PAGE_SIZE, "page": page}
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _parse_name(name_text: str) -> tuple[str | None, str | None]:
    """商品名から(card_num, rarity)を取り出す。括弧内のトークンのうち、カード番号の
    形をしたものをcard_num、パック略称(例:"OP-17")でもcard_numでもないものをrarityとする。
    """
    m = PAREN_CONTENT.search(name_text)
    if not m:
        return None, None
    card_num = None
    rarity = None
    for token in m.group(1).split():
        if CARD_NUM_PATTERN.match(token):
            card_num = token
        elif not PACK_CODE_PATTERN.match(token):
            rarity = token
    return card_num, rarity


def parse_items(html: str) -> list[tuple[str, str | None, int]]:
    """(card_num, rarity, price) のリストを返す(在庫切れ商品はページに表示されないため
    在庫切れの区別は不要)。"""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for li in soup.select("li.list_item_cell"):
        name_el = li.select_one(".goods_name")
        if not name_el:
            continue

        card_num, rarity = _parse_name(name_el.get_text())
        if not card_num:
            continue

        price_el = li.select_one(".price .figure")
        if not price_el:
            continue
        price_text = price_el.get_text().replace("¥", "").replace(",", "").strip()
        try:
            price = int(price_text)
        except ValueError:
            continue

        results.append((card_num, rarity, price))
    return results


def parse_total_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one(".count_number .number")
    if not el:
        return 0
    return int(el.get_text().replace(",", ""))


def sync_prices(conn=None, delay: float = REQUEST_DELAY_SEC, progress_callback=None) -> dict:
    """わいTVからワンピースカードの価格を取得し price_history に保存する。

    progress_callback(page, last_page, matched_count) が指定されていれば
    ページ取得のたびに呼び出す。
    """
    owns_conn = conn is None
    if owns_conn:
        conn = db.get_connection()
        db.init_db(conn)

    lookup = price_matching.build_lookup(conn)
    all_prices: dict[str, list[int]] = defaultdict(list)
    unmatched_count = 0
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
                logger.warning("わいTVの取得に失敗 (page=%d): %s", page, exc)
                break

            if page == 1:
                total = parse_total_count(html)
                last_page = max(1, -(-total // PAGE_SIZE))  # 切り上げ除算

            for card_num, rarity, price in parse_items(html):
                # わいTVは「P-SR」のようにパラレル表記にP-を前置するが、DB側の
                # rarityはこの前置詞を持たないため、マッチング時だけ取り除く。
                normalized_rarity = rarity[2:] if rarity and rarity.startswith("P-") else rarity
                card_id = price_matching.pick_card_id(card_num, lookup, normalized_rarity)
                if card_id is None:
                    unmatched_count += 1
                    continue
                all_prices[card_id].append(price)

            if progress_callback:
                progress_callback(page, last_page, len(all_prices))

            page += 1

        run_recorded_at = datetime.now(timezone.utc).isoformat()
        for card_id, prices in all_prices.items():
            db.insert_price(
                conn, card_id, "わいTV", min(prices),
                recorded_at=run_recorded_at, sample_count=len(prices),
            )

        summary = {"matched_cards": len(all_prices), "unmatched_listings": unmatched_count}
        logger.info(
            "完了: %d枚の価格を取得 (DBに無いカード番号の出品 %d件はスキップ)",
            summary["matched_cards"], summary["unmatched_listings"],
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
