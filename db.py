"""SQLite データベースアクセス層。

カードの主キーには公式サイトのカード詳細モーダルのDOM id (例: "OP17-001",
パラレルは "EB04-061_p3" のような枝番付き) をそのまま使う。同じ card_num でも
パラレル違いは別の見た目・別のレアリティを持つ独立した1件として扱うため。
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "data" / "onepiece_tcg.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    card_num TEXT NOT NULL,
    name TEXT NOT NULL,
    card_type TEXT,
    rarity TEXT,
    color TEXT,
    cost INTEGER,
    life INTEGER,
    power INTEGER,
    counter INTEGER,
    attribute TEXT,
    block_icon TEXT,
    feature TEXT,
    ability_text TEXT,
    trigger_text TEXT,
    pack TEXT,
    series_id TEXT,
    image_url TEXT,
    content_hash TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT NOT NULL,
    site TEXT NOT NULL,
    price INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    sample_count INTEGER,
    FOREIGN KEY (card_id) REFERENCES cards(id)
);

CREATE TABLE IF NOT EXISTS goods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT,
    category_label TEXT,
    tag TEXT,
    price_text TEXT,
    price_yen INTEGER,
    release_date TEXT,
    image_url TEXT,
    detail_url TEXT,
    fetched_at TEXT,
    UNIQUE(title, detail_url)
);

CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);
CREATE INDEX IF NOT EXISTS idx_cards_card_num ON cards(card_num);
CREATE INDEX IF NOT EXISTS idx_price_card ON price_history(card_id);
"""

CARD_COLUMNS = [
    "id", "card_num", "name", "card_type", "rarity", "color", "cost", "life",
    "power", "counter", "attribute", "block_icon", "feature", "ability_text",
    "trigger_text", "pack", "series_id", "image_url", "content_hash", "fetched_at",
]


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_cards(conn: sqlite3.Connection, cards: list[dict]) -> dict:
    """カードを一括 upsert する。新規/更新件数を返す。"""
    new_count = 0
    updated_count = 0
    now = datetime.now(timezone.utc).isoformat()

    placeholders = ", ".join(f":{c}" for c in CARD_COLUMNS)
    assignments = ", ".join(f"{c}=excluded.{c}" for c in CARD_COLUMNS if c not in ("id", "fetched_at"))

    sql = f"""
        INSERT INTO cards ({", ".join(CARD_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET {assignments}
        WHERE excluded.content_hash IS NOT cards.content_hash
    """

    for card in cards:
        existing = conn.execute("SELECT content_hash FROM cards WHERE id = ?", (card["id"],)).fetchone()
        row = {**card, "fetched_at": now}
        conn.execute(sql, row)
        if existing is None:
            new_count += 1
        elif existing["content_hash"] != card["content_hash"]:
            updated_count += 1

    conn.commit()
    return {"new": new_count, "updated": updated_count, "total": len(cards)}


def search_cards(conn: sqlite3.Connection, keyword: str = "", colors=None, types=None,
                  rarities=None) -> list[sqlite3.Row]:
    query = "SELECT * FROM cards WHERE 1=1"
    params: list = []

    if keyword:
        query += " AND (name LIKE ? OR ability_text LIKE ? OR feature LIKE ?)"
        like = f"%{keyword}%"
        params += [like, like, like]

    def add_in_filter(column: str, values):
        if values:
            placeholders = ", ".join("?" for _ in values)
            return f" AND {column} IN ({placeholders})", list(values)
        return "", []

    for column, values in (("color", colors), ("card_type", types), ("rarity", rarities)):
        part, vals = add_in_filter(column, values)
        query += part
        params += vals

    query += " ORDER BY card_num, id"
    return conn.execute(query, params).fetchall()


def get_card(conn: sqlite3.Connection, card_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()


def get_distinct_values(conn: sqlite3.Connection, column: str) -> list[str]:
    rows = conn.execute(f"SELECT DISTINCT {column} FROM cards WHERE {column} IS NOT NULL ORDER BY {column}").fetchall()
    return [r[0] for r in rows]


def count_cards(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]


def insert_price(
    conn: sqlite3.Connection,
    card_id: str,
    site: str,
    price: int,
    recorded_at: str | None = None,
    sample_count: int | None = None,
) -> None:
    recorded_at = recorded_at or datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO price_history (card_id, site, price, recorded_at, sample_count) VALUES (?, ?, ?, ?, ?)",
        (card_id, site, price, recorded_at, sample_count),
    )
    conn.commit()


def get_price_history(conn: sqlite3.Connection, card_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM price_history WHERE card_id = ? ORDER BY recorded_at", (card_id,)
    ).fetchall()


GOODS_COLUMNS = [
    "title", "category", "category_label", "tag", "price_text", "price_yen",
    "release_date", "image_url", "detail_url",
]


def upsert_goods(conn: sqlite3.Connection, items: list[dict]) -> dict:
    """拡張パック/デッキ/周辺グッズを一括upsertする。(title, detail_url)をキーに
    重複排除する。新規/更新件数を返す。"""
    new_count = 0
    updated_count = 0
    now = datetime.now(timezone.utc).isoformat()

    placeholders = ", ".join(f":{c}" for c in GOODS_COLUMNS)
    assignments = ", ".join(f"{c}=excluded.{c}" for c in GOODS_COLUMNS if c not in ("title", "detail_url"))

    sql = f"""
        INSERT INTO goods ({", ".join(GOODS_COLUMNS)}, fetched_at)
        VALUES ({placeholders}, :fetched_at)
        ON CONFLICT(title, detail_url) DO UPDATE SET {assignments}, fetched_at=excluded.fetched_at
        WHERE excluded.price_text IS NOT goods.price_text
    """

    for item in items:
        if not item.get("detail_url"):
            continue
        existing = conn.execute(
            "SELECT price_text FROM goods WHERE title = ? AND detail_url = ?",
            (item["title"], item["detail_url"]),
        ).fetchone()
        row = {**item, "fetched_at": now}
        conn.execute(sql, row)
        if existing is None:
            new_count += 1
        elif existing["price_text"] != item.get("price_text"):
            updated_count += 1

    conn.commit()
    return {"new": new_count, "updated": updated_count, "total": len(items)}
