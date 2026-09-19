"""公式サイトのカード画像をダウンロードし、data/card_images/ に保存するモジュール。

onepiece-cardgame.com の画像はレスポンスヘッダで
`Cross-Origin-Resource-Policy: same-site` が付いており、他ドメイン(GitHub Pages等)
からの直リンク(<img src="https://www.onepiece-cardgame.com/...">)がブラウザ側で
ブロックされる。そのため画像を一度ダウンロードして自サイトから配信する必要がある。
"""
import logging
import time
from pathlib import Path

import requests

import db

IMAGE_DIR = Path(__file__).parent / "data" / "card_images"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://www.onepiece-cardgame.com/cardlist/",
}
REQUEST_TIMEOUT = 15
REQUEST_DELAY_SEC = 0.15

logger = logging.getLogger(__name__)


def _filename_for(card_id: str, image_url: str) -> str:
    suffix = Path(image_url.split("?", 1)[0]).suffix or ".png"
    return f"{card_id}{suffix}"


def download_missing_images(conn, delay: float = REQUEST_DELAY_SEC) -> dict:
    """DB内の全カードについて、まだ保存していない画像だけをダウンロードする。"""
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    rows = conn.execute("SELECT id, image_url FROM cards WHERE image_url IS NOT NULL").fetchall()

    downloaded = 0
    skipped = 0
    failed = 0

    for row in rows:
        filename = _filename_for(row["id"], row["image_url"])
        dest = IMAGE_DIR / filename
        if dest.exists():
            skipped += 1
            continue
        try:
            resp = requests.get(row["image_url"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            downloaded += 1
            time.sleep(delay)
        except requests.RequestException as exc:
            logger.warning("画像取得に失敗: %s (%s)", row["image_url"], exc)
            failed += 1

    return {"downloaded": downloaded, "skipped": skipped, "failed": failed, "total": len(rows)}


def local_filename(card_id: str, image_url: str | None) -> str | None:
    """cards.json用に、DBのimage_url(公式サイトURL)から保存済みローカルファイル名を導出する。"""
    if not image_url:
        return None
    return _filename_for(card_id, image_url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    conn = db.get_connection()
    try:
        result = download_missing_images(conn)
    finally:
        conn.close()
    logger.info(
        "完了: 新規 %d件 / スキップ %d件 / 失敗 %d件 / 合計 %d件",
        result["downloaded"], result["skipped"], result["failed"], result["total"],
    )
