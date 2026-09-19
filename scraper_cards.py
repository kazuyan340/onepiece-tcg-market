"""ワンピースカードゲーム公式サイトのカード一覧ページからカード情報を取得するモジュール。

公式サイト (https://www.onepiece-cardgame.com/cardlist/) は conanTCG公式サイトと違い
専用JSON APIを持たず、パック(シリーズ)ごとにカード情報をHTMLへサーバーサイドで
埋め込んで返す (?series=<id> のクエリでパックを切り替える)。そのため
1. トップページの <select name="series"> からパックID一覧を取得
2. 各パックIDのページを取得し、カード情報のdl(dl.modalCol)をパースする
という2段階の処理で全カードを収集する。
"""
import hashlib
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

import db

BASE_URL = "https://www.onepiece-cardgame.com/cardlist/"
IMAGE_BASE_URL = "https://www.onepiece-cardgame.com/images/cardlist/card/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

REQUEST_TIMEOUT = 15
REQUEST_DELAY_SEC = 1.0  # サーバー負荷軽減のためパック取得間隔を空ける

logger = logging.getLogger(__name__)


def _to_int(text: str | None) -> int | None:
    if text is None:
        return None
    text = text.strip()
    if not text or text == "-":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _clean_dash(text: str | None) -> str | None:
    """公式サイトは値が無い項目を文字列 "-" で表す。表示上のプレースホルダーなので
    データとしてはNoneに正規化する。"""
    if text is None:
        return None
    text = text.strip()
    return None if text == "-" else text


def _text_after_h3(div) -> str | None:
    """<div><h3>ラベル</h3>本文...</div> の「本文」部分だけをテキスト抽出する。"""
    if div is None:
        return None
    h3 = div.find("h3")
    if h3 is not None:
        h3.extract()
    text = div.get_text(separator="\n", strip=True)
    return text or None


def fetch_series_list() -> list[dict]:
    """トップページから全パック(シリーズ)のID・パック名一覧を取得する。"""
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    series = []
    select = soup.find("select", {"name": "series"})
    for option in select.find_all("option"):
        value = (option.get("value") or "").strip()
        if not value:
            continue
        # 公式サイトはパック名内の<br>をHTMLエンティティとして二重エスケープしており、
        # get_text()では実タグではなくリテラル文字列 <br class="spInline"> がそのまま
        # 出てきてしまうため、テキスト化した後に除去する。
        label = re.sub(r"<br[^>]*>", " ", option.get_text(strip=True)).strip()
        series.append({"series_id": value, "label": label})
    return series


def parse_card(dl, series_id: str, pack_label: str) -> dict | None:
    card_id = dl.get("id")
    if not card_id:
        return None

    info_spans = dl.select_one(".infoCol").find_all("span")
    if len(info_spans) < 3:
        return None
    card_num, rarity, card_type = (s.get_text(strip=True) for s in info_spans[:3])

    name = dl.select_one(".cardName").get_text(strip=True)

    img = dl.select_one(".frontCol img")
    image_url = None
    if img is not None:
        src = img.get("data-src") or img.get("src")
        if src:
            filename = src.rsplit("/", 1)[-1]
            image_url = IMAGE_BASE_URL + filename

    # コストとライフは同じ div.cost を共有し、h3のラベル文字列(「コスト」/「ライフ」)
    # でしか区別できない(公式サイトのマークアップ都合)。
    cost_div = dl.select_one(".cost")
    cost = life = None
    if cost_div is not None:
        label = cost_div.find("h3").get_text(strip=True)
        value = _to_int(_text_after_h3(cost_div))
        if label == "ライフ":
            life = value
        else:
            cost = value

    attribute_div = dl.select_one(".attribute")
    attribute = None
    if attribute_div is not None:
        img_attr = attribute_div.find("img")
        attribute = img_attr.get("alt") if img_attr is not None else _text_after_h3(attribute_div)
    attribute = _clean_dash(attribute)

    power = _to_int(_text_after_h3(dl.select_one(".power")))
    counter = _to_int(_text_after_h3(dl.select_one(".counter")))
    color = _clean_dash(_text_after_h3(dl.select_one(".color")))
    block_icon = _clean_dash(_text_after_h3(dl.select_one(".block")))
    feature = _clean_dash(_text_after_h3(dl.select_one(".feature")))
    ability_text = _text_after_h3(dl.select_one(".text"))
    trigger_text = _text_after_h3(dl.select_one(".trigger"))

    content_key = "|".join(str(v) for v in (
        name, rarity, card_type, cost, life, power, counter, color, block_icon,
        attribute, feature, ability_text, trigger_text, image_url,
    ))
    content_hash = hashlib.sha1(content_key.encode("utf-8")).hexdigest()

    return {
        "id": card_id,
        "card_num": card_num,
        "name": name,
        "card_type": card_type,
        "rarity": rarity,
        "color": color,
        "cost": cost,
        "life": life,
        "power": power,
        "counter": counter,
        "attribute": attribute,
        "block_icon": block_icon,
        "feature": feature,
        "ability_text": ability_text,
        "trigger_text": trigger_text,
        "pack": pack_label,
        "series_id": series_id,
        "image_url": image_url,
        "content_hash": content_hash,
    }


def fetch_series_cards(series_id: str, pack_label: str) -> list[dict]:
    resp = requests.get(
        BASE_URL, params={"series": series_id}, headers=HEADERS, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    cards = []
    for dl in soup.select("dl.modalCol"):
        card = parse_card(dl, series_id, pack_label)
        if card is not None:
            cards.append(card)
    return cards


def sync_all_cards(conn=None, delay: float = REQUEST_DELAY_SEC, progress_callback=None) -> dict:
    """全パックを巡回して全カードを取得しDBにupsertする。

    progress_callback(index, total, series_label, total_fetched) が指定されていれば
    パック取得のたびに呼び出す。
    """
    owns_conn = conn is None
    if owns_conn:
        conn = db.get_connection()
        db.init_db(conn)

    summary = {"new": 0, "updated": 0, "total": 0}
    try:
        series_list = fetch_series_list()
        for index, series in enumerate(series_list, start=1):
            cards = fetch_series_cards(series["series_id"], series["label"])
            result = db.upsert_cards(conn, cards)
            summary["new"] += result["new"]
            summary["updated"] += result["updated"]
            summary["total"] += result["total"]

            if progress_callback:
                progress_callback(index, len(series_list), series["label"], summary["total"])

            if index < len(series_list):
                time.sleep(delay)
    finally:
        if owns_conn:
            conn.close()

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    def _print_progress(index, total, label, fetched):
        logger.info("パック %d/%d [%s] 取得完了 (累計 %d 件)", index, total, label, fetched)

    result = sync_all_cards(progress_callback=_print_progress)
    logger.info("完了: 新規 %d件 / 更新 %d件 / 合計 %d件", result["new"], result["updated"], result["total"])
