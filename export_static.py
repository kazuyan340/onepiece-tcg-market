"""DBの内容を静的サイト用のJSONファイル(site/data/配下)へ書き出すスクリプト。

GitHub Pages等の静的ホスティングで動かすため、サイト側はこのJSONを
fetchするだけで完結する(サーバーサイド処理は一切不要)。
"""
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import db
import images

SITE_DATA_DIR = Path(__file__).parent / "site" / "data"

CARD_FIELDS = [
    "id", "card_num", "name", "card_type", "rarity", "color", "cost", "life",
    "power", "counter", "attribute", "block_icon", "feature", "ability_text",
    "trigger_text", "pack", "image_url",
]


def build_cards_json(conn) -> list[dict]:
    rows = conn.execute(
        f"SELECT {', '.join(CARD_FIELDS)} FROM cards ORDER BY card_num, id"
    ).fetchall()
    cards = []
    for row in rows:
        card = dict(row)
        local_name = images.local_filename(card["id"], card["image_url"])
        # 公式サイトの画像は他ドメインからの直リンクをブロックしているため、
        # あらかじめ images.py でダウンロードした自サイト内の画像を参照させる。
        card["image_url"] = f"images/cards/{local_name}" if local_name else None
        cards.append(card)
    return cards


def build_prices_latest_json(conn) -> dict:
    """カードごとの直近の最安値を site/data/prices_latest.json 用に組み立てる。

    price_historyは日々の実行のたびに行を積み増していく(店舗ごとの推移を
    残すため)。ここでは各カード・各店舗の最新1件だけを抜き出し、
    店舗間の最安値をそのカードの代表価格とする。
    """
    rows = conn.execute(
        """
        SELECT ph.card_id, ph.site, ph.price, ph.recorded_at, ph.sample_count
        FROM price_history ph
        INNER JOIN (
            SELECT card_id, site, MAX(recorded_at) AS max_recorded_at
            FROM price_history
            GROUP BY card_id, site
        ) latest
        ON ph.card_id = latest.card_id
        AND ph.site = latest.site
        AND ph.recorded_at = latest.max_recorded_at
        """
    ).fetchall()

    by_card: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_card[row["card_id"]].append({
            "site": row["site"],
            "price": row["price"],
            "recorded_at": row["recorded_at"],
            "sample_count": row["sample_count"],
        })

    result = {}
    for card_id, entries in by_card.items():
        best = min(entries, key=lambda e: e["price"])
        pooled_avg = round(sum(e["price"] for e in entries) / len(entries))
        result[card_id] = {"best": best, "shops": entries, "pooled_avg": pooled_avg}
    return result


def export_prices(conn) -> dict[str, list[dict]]:
    """カードごとの価格履歴全件(全ショップ)。site/data/prices/{id}.jsonに分割保存する元データ。"""
    rows = conn.execute(
        "SELECT card_id, site, price, recorded_at, sample_count FROM price_history ORDER BY recorded_at"
    ).fetchall()
    prices: dict[str, list[dict]] = {}
    for row in rows:
        prices.setdefault(row["card_id"], []).append({
            "site": row["site"],
            "price": row["price"],
            "recorded_at": row["recorded_at"],
            "sample_count": row["sample_count"],
        })
    return prices


def write_prices_per_card(prices: dict[str, list[dict]], out_dir: Path) -> int:
    """カードごとの価格履歴全件を site/data/prices/{id}.json に1枚1ファイルで書き出す。

    個別カードのモーダルは自分のカード1枚分の履歴しか使わないため、全カード分を
    1本のJSONにまとめるとモーダルを開くたびに無関係な分まで読み込むことになる。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.stem for p in out_dir.glob("*.json")}
    written = set()
    for card_id, points in prices.items():
        (out_dir / f"{card_id}.json").write_text(
            json.dumps(points, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        written.add(card_id)
    # 価格が無くなった(=対象外になった)カードの古いファイルは残さず消す。
    for stale in existing - written:
        (out_dir / f"{stale}.json").unlink(missing_ok=True)
    return len(prices)


POOLED_SITE_LABEL = "全体"
TREND_LIMIT = 50
MOVERS_LIMIT = 100


def _price_points_by_card_site(conn) -> dict[tuple[str, str], list[tuple[str, int]]]:
    """(card_id, site) -> [(recorded_at, price), ...] (日時順)。

    サイトごとに独立した時系列として扱う。仕入れ元が違えば価格帯そのものが
    異なるため、サイトをまたいで1本の時系列にすると「サイトが入れ替わっただけ」を
    値上がり/値下がりと誤検出してしまう。同じ日に複数回記録されていた場合は
    その日の最後の値だけを残す(重複ポイントの誤検出防止)。
    """
    rows = conn.execute(
        "SELECT card_id, site, price, recorded_at FROM price_history ORDER BY card_id, site, recorded_at"
    ).fetchall()

    latest_by_day: dict[tuple[str, str], dict[str, tuple[str, int]]] = defaultdict(dict)
    for row in rows:
        key = (row["card_id"], row["site"])
        day = row["recorded_at"][:10]
        latest_by_day[key][day] = (row["recorded_at"], row["price"])

    return {
        key: [days[day] for day in sorted(days)] for key, days in latest_by_day.items()
    }


def _pooled_points_by_card(
    by_card_site: dict[tuple[str, str], list[tuple[str, int]]],
) -> dict[str, list[tuple[str, int]]]:
    """(card_id) -> [(日付, 全ショップ単純平均価格), ...]。

    新規ショップの参入(または撤退)でその日の集計対象の顔ぶれが変わると、
    どのショップの実売価格も動いていないのに平均値だけ動いて見えてしまうため、
    最新日のショップ構成と一致する連続区間(末尾から遡って同じ顔ぶれが続く範囲)
    だけを対象にする。
    """
    by_card_day: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    site_set_by_card_day: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for (card_id, site), points in by_card_site.items():
        for recorded_at, price in points:
            day = recorded_at[:10]
            by_card_day[card_id][day].append(price)
            site_set_by_card_day[card_id][day].add(site)

    result: dict[str, list[tuple[str, int]]] = {}
    for card_id, days in by_card_day.items():
        sorted_days = sorted(days)
        latest_set = frozenset(site_set_by_card_day[card_id][sorted_days[-1]])
        cutoff = len(sorted_days) - 1
        for i in range(len(sorted_days) - 2, -1, -1):
            if frozenset(site_set_by_card_day[card_id][sorted_days[i]]) != latest_set:
                break
            cutoff = i
        stable_days = sorted_days[cutoff:]
        result[card_id] = [(day, round(sum(days[day]) / len(days[day]))) for day in stable_days]
    return result


def _all_price_series(conn) -> dict[tuple[str, str], list[tuple[str, int]]]:
    by_card_site = _price_points_by_card_site(conn)
    pooled = _pooled_points_by_card(by_card_site)
    combined = dict(by_card_site)
    for card_id, points in pooled.items():
        combined[(card_id, POOLED_SITE_LABEL)] = points
    return combined


def _previous_day_moves(
    by_card_site: dict[tuple[str, str], list[tuple[str, int]]],
) -> tuple[list[dict], list[dict]]:
    """(card_id, site)ごとに、前回の記録と比べて値上がり/値下がりしたものを返す(閾値なし)。"""
    up, down = [], []
    for (card_id, site), points in by_card_site.items():
        if len(points) < 2:
            continue
        prev_date, prev_price = points[-2]
        last_date, last_price = points[-1]
        if prev_price <= 0 or prev_price == last_price:
            continue

        pct = (last_price - prev_price) / prev_price * 100
        item = {
            "card_id": card_id, "site": site, "change_pct": round(pct, 1),
            "previous_price": prev_price, "previous_date": prev_date,
            "latest_price": last_price, "latest_date": last_date,
        }
        (up if pct > 0 else down).append(item)
    return up, down


def _sort_limit_per_site(items: list[dict], limit: int, reverse: bool) -> list[dict]:
    """ショップ(「全体」含む)ごとに変化率順でソートし、上位limit件だけ残す。"""
    by_site: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_site[item["site"]].append(item)

    result = []
    for site_items in by_site.values():
        site_items.sort(key=lambda x: x["change_pct"], reverse=reverse)
        result.extend(site_items[:limit])
    return result


def compute_trends(by_card_site: dict[tuple[str, str], list[tuple[str, int]]]) -> dict[str, list[dict]]:
    """価格が直近上昇/上昇傾向/直近下降/下降傾向にあるカードを判定する。"""
    recent_up, recent_down = _previous_day_moves(by_card_site)

    trend_up, trend_down = [], []
    for (card_id, site), points in by_card_site.items():
        if len(points) < 3:
            continue
        mid_date, mid_price = points[-2]
        last_date, last_price = points[-1]
        prev_price = points[-3][1]
        if prev_price <= 0 or mid_price <= 0:
            continue
        item = {
            "card_id": card_id, "site": site,
            "change_pct": round((last_price - mid_price) / mid_price * 100, 1),
            "previous_price": mid_price, "previous_date": mid_date,
            "latest_price": last_price, "latest_date": last_date,
        }
        if mid_price > prev_price and last_price > mid_price:
            trend_up.append(item)
        elif mid_price < prev_price and last_price < mid_price:
            trend_down.append(item)

    return {
        "recent_up": _sort_limit_per_site(recent_up, TREND_LIMIT, reverse=True),
        "trend_up": _sort_limit_per_site(trend_up, TREND_LIMIT, reverse=True),
        "recent_down": _sort_limit_per_site(recent_down, TREND_LIMIT, reverse=False),
        "trend_down": _sort_limit_per_site(trend_down, TREND_LIMIT, reverse=False),
    }


def compute_movers(by_card_site: dict[tuple[str, str], list[tuple[str, int]]]) -> dict[str, list[dict]]:
    """前回と比べて値上がりしたカード/値下がりしたカードを(閾値なしで)全て挙げる。"""
    up, down = _previous_day_moves(by_card_site)
    return {
        "up": _sort_limit_per_site(up, MOVERS_LIMIT, reverse=True),
        "down": _sort_limit_per_site(down, MOVERS_LIMIT, reverse=False),
    }


def build_meta_json(conn) -> dict:
    return {
        "total_cards": db.count_cards(conn),
        "colors": db.get_distinct_values(conn, "color"),
        "card_types": db.get_distinct_values(conn, "card_type"),
        "rarities": db.get_distinct_values(conn, "rarity"),
        "packs": db.get_distinct_values(conn, "pack"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def export_static() -> None:
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = db.get_connection()
    try:
        cards = build_cards_json(conn)
        meta = build_meta_json(conn)
        prices_latest = build_prices_latest_json(conn)
        prices = export_prices(conn)
        all_series = _all_price_series(conn)
        trends = compute_trends(all_series)
        movers = compute_movers(all_series)
    finally:
        conn.close()

    (SITE_DATA_DIR / "cards.json").write_text(
        json.dumps(cards, ensure_ascii=False), encoding="utf-8"
    )
    (SITE_DATA_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (SITE_DATA_DIR / "prices_latest.json").write_text(
        json.dumps(prices_latest, ensure_ascii=False), encoding="utf-8"
    )
    per_card_count = write_prices_per_card(prices, SITE_DATA_DIR / "prices")
    (SITE_DATA_DIR / "trends.json").write_text(
        json.dumps(trends, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (SITE_DATA_DIR / "movers.json").write_text(
        json.dumps(movers, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(
        f"site/data/cards.json, meta.json, prices_latest.json({len(prices_latest)}件), "
        f"prices/({per_card_count}件), trends.json, movers.json を書き出しました。"
    )


if __name__ == "__main__":
    export_static()
