"""各価格スクレイパーが sync_prices() の実行中に書き出した
site/data/unresolved_raw/{site}.json (unresolved_report.write_unresolved参照)を
まとめて、管理ページ(site/admin-unresolved.html)が読み込む
site/data/unresolved-shop-items.json を作る。

各エントリを2種類に振り分ける。
- ambiguous: card_numからDBの候補カードまでは絞れたが1枚に特定できなかったもの。
  候補カードの画像(自サイトの画像パス)を出せる。
- missing: 該当するcard_numがDBに1件も無いもの。画像は出せない。

新たにサイトへアクセスすることはなく、既に書き出し済みの生データだけで完結する。
"""
import json
from pathlib import Path

import images
from unresolved_report import UNRESOLVED_DIR

OUT_PATH = Path(__file__).parent / "site" / "data" / "unresolved-shop-items.json"


def _localize_candidate(c: dict) -> dict:
    local_name = images.local_filename(c["id"], c.get("image_url"))
    return {**c, "image_url": f"images/cards/{local_name}" if local_name else None}


def dedupe_missing(rows: list[dict]) -> list[dict]:
    """候補が1件も無い(missing)ものは選択の余地が無いので、(site, raw_key, rarity)
    単位で価格リストと件数を集約してコンパクトに表示する。
    """
    grouped: dict[tuple, dict] = {}
    for r in rows:
        key = (r["site"], r["raw_key"], r["rarity"])
        if key not in grouped:
            grouped[key] = {**r, "listing_count": 1, "prices": [r["price"]] if r.get("price") is not None else []}
        else:
            grouped[key]["listing_count"] += 1
            if r.get("price") is not None:
                grouped[key]["prices"].append(r["price"])
    return list(grouped.values())


def group_ambiguous(rows: list[dict]) -> list[dict]:
    """候補があるもの(ambiguous)は、ユーザーが商品画像を見て出品ごとに候補を
    選べる必要があるため、1出品=1レコードのまま(site, raw_key, rarity)で
    見出しだけまとめる(候補リストはraw_key+rarityが同じなら全出品で共通)。
    """
    grouped: dict[tuple, dict] = {}
    for r in rows:
        key = (r["site"], r["raw_key"], r["rarity"])
        listing = {
            "product_url": r.get("product_url"),
            "image_url": r.get("image_url"),
            "price": r.get("price"),
            "product_name": r.get("product_name"),
        }
        if key not in grouped:
            grouped[key] = {
                "site": r["site"], "raw_key": r["raw_key"], "rarity": r["rarity"],
                "candidates": [_localize_candidate(c) for c in r["candidates"]],
                "listings": [listing],
            }
        else:
            grouped[key]["listings"].append(listing)
    return list(grouped.values())


def build_report() -> dict:
    ambiguous: list[dict] = []
    missing: list[dict] = []

    if not UNRESOLVED_DIR.exists():
        return {"ambiguous": [], "missing": []}

    for path in sorted(UNRESOLVED_DIR.glob("*.json")):
        site = path.stem
        entries = json.loads(path.read_text(encoding="utf-8"))
        for e in entries:
            row = {"site": site, **e}
            if row.get("candidates"):
                ambiguous.append(row)
            else:
                missing.append(row)

    return {"ambiguous": group_ambiguous(ambiguous), "missing": dedupe_missing(missing)}


def main():
    report = build_report()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"unresolved-shop-items.json: ambiguous={len(report['ambiguous'])}件 missing={len(report['missing'])}件")


if __name__ == "__main__":
    main()
