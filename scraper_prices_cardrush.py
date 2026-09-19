"""カードラッシュ ワンピース(cardrush-op.jp)からワンピースカードゲームの価格を
取得し price_history に保存するモジュール。

カードラボ・わいTVと同じ系列のECカートシステムを使っており、HTML構造もほぼ同一。
商品名は「{カード名}(状態・イラスト等の説明)【{レアリティ}】{{カード番号}}」という
形式(例: "ジュラキュール・ミホーク(未開封/CS26-27/illust:Akanegumo)【SEC】{OP14-119}")
になっている。パラレルは「SEC/P」のようにレアリティ側に"/P"が付く。

オリパ(福袋的なランダムパック商品)やドン!!カード等、単品カードとして特定できない
商品も同じ一覧に混在するため、末尾の{カード番号}がDBのcard_num形式と一致する
ものだけを対象にする。全商品検索(約14,500件)だと関係ない商品が大半を占めるため、
"OP"キーワードで絞り込む(それでも約9,400件・95ページ程度)。

カードラッシュのrobots.txtの内容は未確認だが、他の同系列サイトに合わせて
安全側でリクエスト間隔30秒を採用する。
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

SEARCH_URL = "https://www.cardrush-op.jp/product-list"
KEYWORD = "OP"
PAGE_SIZE = 100

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 15
REQUEST_DELAY_SEC = 30
MAX_PAGES = 150  # 安全のための上限(実際の最終ページはparse_total_countから算出)

# 例: "ジュラキュール・ミホーク(未開封/CS26-27/illust:Akanegumo)【SEC】{OP14-119}"
NAME_PATTERN = re.compile(r"【([^】]+)】\{([^{}]+)\}\s*$")
CARD_NUM_PATTERN = re.compile(r"^([A-Z]{1,3}\d{1,2}-\d{3}|P-\d{3})$")

logger = logging.getLogger(__name__)


def fetch_page(page: int) -> str:
    params = {"keyword": KEYWORD, "num": PAGE_SIZE, "page": page}
    resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_items(html: str) -> list[tuple[str, str, int]]:
    """(card_num, rarity, price) のリストを返す。オリパ・ドン!!カード等、単品の
    カード番号として特定できない商品は除外する。
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for li in soup.select("li.list_item_cell"):
        name_el = li.select_one(".goods_name")
        if not name_el:
            continue

        m = NAME_PATTERN.search(name_el.get_text())
        if not m:
            continue
        rarity, card_num = m.group(1), m.group(2)
        if not CARD_NUM_PATTERN.match(card_num):
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


def sync_prices(conn=None, delay: float = REQUEST_DELAY_SEC, progress_callback=None) -> dict:
    """カードラッシュからワンピースカードの価格を取得し price_history に保存する。

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
                logger.warning("カードラッシュの取得に失敗 (page=%d): %s", page, exc)
                break

            if page == 1:
                total = parse_total_count(html)
                last_page = max(1, -(-total // PAGE_SIZE))  # 切り上げ除算

            for card_num, rarity, price in parse_items(html):
                card_id = price_matching.pick_card_id(card_num, lookup, rarity)
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
                conn, card_id, "カードラッシュ", min(prices),
                recorded_at=run_recorded_at, sample_count=len(prices),
            )

        summary = {"matched_cards": len(all_prices), "unmatched_listings": unmatched_count}
        logger.info(
            "完了: %d枚の価格を取得 (単品カードとして特定できない出品 %d件はスキップ)",
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
