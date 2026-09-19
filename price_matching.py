"""各ショップの価格スクレイパー共通: card_num(+わかる場合はレアリティ)からDBのカードIDを
引き当てるヘルパー。

公式サイトのデータでは、同じカード番号(card_num)でも通常版・パラレル版などが別の
DB行(id)として存在することがあり、しかも公式サイト自体が両者に同じrarity値を
付けている場合もあるため、ショップの商品情報だけでは絵柄違いまで確実に区別できない。
そのため「同じcard_num(+わかればrarity)の中では、通常版(id==card_num)を代表として
価格を紐付ける」という割り切った方針を全ショップ共通で採用する。
"""
from collections import defaultdict


def build_lookup(conn) -> dict[str, list[dict]]:
    rows = conn.execute("SELECT id, card_num, rarity FROM cards").fetchall()
    lookup: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        lookup[row["card_num"]].append({"id": row["id"], "rarity": row["rarity"]})
    return lookup


def pick_card_id(card_num: str, lookup: dict[str, list[dict]], shop_rarity: str | None = None) -> str | None:
    candidates = lookup.get(card_num)
    if not candidates:
        return None

    if shop_rarity:
        base_rarity = shop_rarity.split("/")[0].strip()
        same_rarity = [c for c in candidates if c["rarity"] == base_rarity]
        if same_rarity:
            candidates = same_rarity

    for c in candidates:
        if c["id"] == card_num:
            return c["id"]
    return candidates[0]["id"]
