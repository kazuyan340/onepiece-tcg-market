"""カードラボからワンピースカードゲームの価格を取得し price_history に保存するモジュール。

カードラボの検索結果には goods_name というクラスの要素に
"【OP】{カード名}【{レアリティ}】{カード番号}" という形式でカード番号が
そのまま残っている(名探偵コナンTCGの"【CTCG】...[card_num]"とは末尾の
括弧の有無が違う)。キーワード「OP」1つで全カードを横断検索できる。

パラレル("R/SP"のようにレアリティにスラッシュ区切りで付与される)は、公式サイトの
カードデータ側でも同じカード番号・同じレアリティの複数印刷が存在し、絵違いまでは
区別できないため、同じ(card_num, レアリティ)を持つDB行が複数あった場合は
通常版(id が card_num と一致する行)を代表として価格を紐付ける。
"""
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

import db

SEARCH_URL = "https://www.c-labo-online.jp/product-list/"
KEYWORD = "OP"
PAGE_SIZE = 120

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 15
REQUEST_DELAY_SEC = 30
MAX_PAGES = 80  # 安全のための上限(実際の最終ページはparse_total_countから算出)

# 例: "【OP】BB【C】OP08-035" / "【OP】お菊【R/SP】(OP07収録)OP01-105"
#     "【OP】ロロノア・ゾロ[25周年エディション]【L】(PRカード)OP01-001(1)"
NAME_PATTERN = re.compile(
    r"^【OP】.*?【([^】]+)】(?:\([^)]*\))?([A-Za-z]{1,4}\d{1,3}-\d{1,3})"
)

logger = logging.getLogger(__name__)


def fetch_search_page(page: int) -> str:
    params = {"keyword": KEYWORD, "num": PAGE_SIZE, "page": page}
    resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_items(html: str) -> list[tuple[str, str, int | None]]:
    """(card_num, rarity, price) のリストを返す。在庫切れの場合はpriceがNoneになる。"""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for li in soup.select("li.list_item_cell"):
        name_el = li.select_one(".goods_name")
        if not name_el:
            continue

        m = NAME_PATTERN.match(name_el.get_text())
        if not m:
            continue
        rarity, card_num = m.group(1), m.group(2)

        if "list_item_soldout" in (li.get("class") or []):
            results.append((card_num, rarity, None))
            continue

        price_el = li.select_one(".price .figure")
        if not price_el:
            continue

        price_text = price_el.get_text().split("円")[0].replace(",", "").strip()
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


def _build_lookup(conn) -> dict[str, list[dict]]:
    rows = conn.execute("SELECT id, card_num, rarity FROM cards").fetchall()
    lookup: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        lookup[row["card_num"]].append({"id": row["id"], "rarity": row["rarity"]})
    return lookup


def _pick_card_id(card_num: str, shop_rarity: str, lookup: dict[str, list[dict]]) -> str | None:
    candidates = lookup.get(card_num)
    if not candidates:
        return None

    base_rarity = shop_rarity.split("/")[0].strip()
    same_rarity = [c for c in candidates if c["rarity"] == base_rarity] or candidates

    for c in same_rarity:
        if c["id"] == card_num:
            return c["id"]
    return same_rarity[0]["id"]


def sync_prices(conn=None, delay: float = REQUEST_DELAY_SEC, progress_callback=None) -> dict:
    """ワンピースカードゲームの価格をカードラボから取得し price_history に保存する。

    progress_callback(page, last_page, matched_count) が指定されていれば
    ページ取得のたびに呼び出す。
    """
    owns_conn = conn is None
    if owns_conn:
        conn = db.get_connection()
        db.init_db(conn)

    lookup = _build_lookup(conn)
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
                html = fetch_search_page(page)
            except requests.RequestException as exc:
                logger.warning("カードラボの取得に失敗 (page=%d): %s", page, exc)
                break

            if page == 1:
                total = parse_total_count(html)
                last_page = max(1, -(-total // PAGE_SIZE))  # 切り上げ除算

            for card_num, rarity, price in parse_items(html):
                if price is None:
                    continue
                card_id = _pick_card_id(card_num, rarity, lookup)
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
                conn, card_id, "カードラボ", min(prices),
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
