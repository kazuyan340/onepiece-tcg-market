"""DBの内容を静的サイト用のJSONファイル(site/data/配下)へ書き出すスクリプト。

GitHub Pages等の静的ホスティングで動かすため、サイト側はこのJSONを
fetchするだけで完結する(サーバーサイド処理は一切不要)。
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import db
import images

SITE_DATA_DIR = Path(__file__).parent / "site" / "data"
SITE_IMAGE_DIR = Path(__file__).parent / "site" / "images" / "cards"

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


def sync_site_images() -> int:
    """data/card_images/ に保存済みの画像を site/images/cards/ へコピーする。"""
    SITE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in images.IMAGE_DIR.glob("*"):
        dest = SITE_IMAGE_DIR / src.name
        if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
            shutil.copyfile(src, dest)
            copied += 1
    return copied


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
    finally:
        conn.close()

    (SITE_DATA_DIR / "cards.json").write_text(
        json.dumps(cards, ensure_ascii=False), encoding="utf-8"
    )
    (SITE_DATA_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    copied = sync_site_images()
    print(f"site/data/cards.json, site/data/meta.json を書き出しました(画像 {copied} 件をコピー)。")


if __name__ == "__main__":
    export_static()
