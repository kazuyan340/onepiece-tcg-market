"""公式サイトのカード画像をダウンロードし、site/images/cards/ に保存するモジュール。

onepiece-cardgame.com の画像はレスポンスヘッダで
`Cross-Origin-Resource-Policy: same-site` が付いており、他ドメイン(GitHub Pages等)
からの直リンク(<img src="https://www.onepiece-cardgame.com/...">)がブラウザ側で
ブロックされる。そのため画像を一度ダウンロードして自サイトから配信する必要がある。

ダウンロード先はサイトの公開ディレクトリ(site/images/cards/)そのものにしている
(scraper/db用の中間キャッシュと公開用ファイルを分けない)。gitで管理するため、
2回目以降の実行では新しいパック分の画像だけが差分ダウンロードされる。
"""
import logging
import time
from pathlib import Path

import requests

import db

IMAGE_DIR = Path(__file__).parent / "site" / "images" / "cards"
GOODS_IMAGE_DIR = Path(__file__).parent / "site" / "images" / "goods"

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


def _goods_filename_for(detail_url: str, image_url: str) -> str:
    # 商品の詳細ページURL末尾(例: ".../products/eb05.html" -> "eb05")をキーにする。
    # goodsテーブルの一意キー(title, detail_url)のうちdetail_urlの方が安定して
    # ファイル名に使える(タイトルは日本語・記号を含みファイル名に向かない)。
    slug = Path(detail_url.rstrip("/")).stem
    suffix = Path(image_url.split("?", 1)[0]).suffix or ".webp"
    return f"{slug}{suffix}"


def download_missing_goods_images(conn, delay: float = REQUEST_DELAY_SEC) -> dict:
    """goodsテーブルの商品画像のうち、まだ保存していないものだけをダウンロードする。

    商品一覧ページの画像は、パスによって直リンク可否がまちまち(一部の画像だけ
    Cross-Origin-Resource-Policy: same-siteが付いている)ことを確認したため、
    カード画像と同様に一律で自サイトにダウンロードする。
    """
    GOODS_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        "SELECT detail_url, image_url FROM goods WHERE image_url IS NOT NULL AND detail_url IS NOT NULL"
    ).fetchall()

    downloaded = 0
    skipped = 0
    failed = 0

    for row in rows:
        filename = _goods_filename_for(row["detail_url"], row["image_url"])
        dest = GOODS_IMAGE_DIR / filename
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
            logger.warning("グッズ画像取得に失敗: %s (%s)", row["image_url"], exc)
            failed += 1

    return {"downloaded": downloaded, "skipped": skipped, "failed": failed, "total": len(rows)}


def goods_local_filename(detail_url: str | None, image_url: str | None) -> str | None:
    if not image_url or not detail_url:
        return None
    return _goods_filename_for(detail_url, image_url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    conn = db.get_connection()
    try:
        result = download_missing_images(conn)
        goods_result = download_missing_goods_images(conn)
    finally:
        conn.close()
    logger.info(
        "カード画像 完了: 新規 %d件 / スキップ %d件 / 失敗 %d件 / 合計 %d件",
        result["downloaded"], result["skipped"], result["failed"], result["total"],
    )
    logger.info(
        "グッズ画像 完了: 新規 %d件 / スキップ %d件 / 失敗 %d件 / 合計 %d件",
        goods_result["downloaded"], goods_result["skipped"], goods_result["failed"], goods_result["total"],
    )
