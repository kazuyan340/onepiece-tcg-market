"""カード1枚ごとに固有のURL(site/card/{id}.html)を持つ静的ページを生成する。

これまで全カードがindex.html上のJavaScriptモーダルとしてしか閲覧できず、
検索エンジンから見て「このカード名の情報を載せている固有ページ」が存在
しなかった。カードごとに専用のtitle/meta description/OGP/構造化データを持つ
静的HTMLを生成することで、個別カード名+「相場」等の検索に直接ヒットできる
ようにする(conan-tcg-marketと同じ狙い)。

価格情報はビルド時点の値(export_static.build_prices_latest_jsonと同じ計算)を
HTMLに直接埋め込み、JavaScript実行に依存せず検索エンジンが読み取れるように
する。ページ読み込み後はcard-detail.jsがこのカード1枚分の価格履歴
(data/prices/{id}.json、遅延取得)を使って、期間切り替えタブ付きの簡易グラフに
差し替える(値そのものは一致する)。
"""
import html
import json
from pathlib import Path

import db
import images
from export_static import CARD_FIELDS, build_prices_latest_json

SITE_BASE_URL = "https://kazuyan340.github.io/onepiece-tcg-market"
SITE_DIR = Path(__file__).parent / "site"
CARD_PAGE_DIR = SITE_DIR / "card"

ASSET_VERSION = "1"

NAV_LINKS = [
    ("index.html", "📋 一覧"),
    ("trends.html", "📊 価格の動きを見る"),
    ("movers-up.html", "🔺 値上がりを見る"),
    ("movers-down.html", "🔻 値下がりを見る"),
    ("ranking.html", "💰 相場ランキング"),
    ("compare.html", "★ お気に入り"),
]

STATIC_PAGES = [
    "index.html", "trends.html", "movers-up.html", "movers-down.html",
    "ranking.html", "compare.html", "about.html", "privacy.html",
]


def _e(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _json_script(data) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _nav_links_html() -> str:
    items = [f'<a href="{href}" class="nav-btn">{label}</a>' for href, label in NAV_LINKS]
    items.append('<button type="button" class="nav-btn nav-btn-disabled" disabled title="準備中です">🃏 デッキ作成(準備中)</button>')
    return "\n      ".join(items)


def _static_price_html(price_info: dict | None) -> tuple[str, str]:
    """(相場サマリーHTML, ショップ別テーブルHTML) を返す。"""
    if not price_info:
        return "", ""
    stats = f'<div class="price-best">¥{price_info["best"]["price"]:,}〜 ({_e(price_info["best"]["site"])}) / 全ショップ平均 ¥{price_info["pooled_avg"]:,}</div>'
    rows = []
    for shop in sorted(price_info["shops"], key=lambda s: s["price"]):
        rows.append(
            f'<div class="price-shop-row"><span>{_e(shop["site"])}</span>'
            f'<span>¥{shop["price"]:,} ({shop["sample_count"]}件の出品中最安値)</span></div>'
        )
    return stats, "".join(rows)


def _meta_description(card: dict, price_info: dict | None) -> str:
    parts = [card["name"]]
    if card.get("rarity"):
        parts.append(f"({card['rarity']})")
    parts.append("の相場・価格情報。")
    if price_info:
        parts.append(f"現在の相場は¥{price_info['pooled_avg']:,}です。")
    parts.append("駿河屋・カードラボ・まんぞく屋・わいTV・カードラッシュ等、複数の販売サイトの価格をまとめて比較できます。")
    return "".join(parts)


def _field_rows_html(card: dict) -> str:
    cost_label = "ライフ" if card.get("card_type") == "LEADER" else "コスト"
    cost_value = card.get("life") if card.get("card_type") == "LEADER" else card.get("cost")
    fields = [
        ("カード番号", card.get("card_num")),
        ("種類", card.get("card_type")),
        ("レアリティ", card.get("rarity")),
        (cost_label, cost_value),
        ("パワー", card.get("power")),
        ("カウンター", card.get("counter")),
        ("属性", card.get("attribute")),
        ("色", card.get("color")),
        ("ブロックアイコン", card.get("block_icon")),
        ("特徴", card.get("feature")),
        ("収録パック", card.get("pack")),
    ]
    return "\n".join(
        f'<div class="info-row"><span class="info-label">{_e(label)}</span><span class="info-value">{_e(value)}</span></div>'
        for label, value in fields
        if value not in (None, "", 0) or label in ("コスト", "ライフ", "パワー", "カウンター")
    )


def _card_page_html(card: dict, price_info: dict | None) -> str:
    title = f"{card['name']}({card['rarity'] or '?'}) 相場・価格情報 | ワンピースカードゲーム カード図鑑"
    description = _meta_description(card, price_info)
    page_url = f"{SITE_BASE_URL}/card/{card['id']}.html"
    image_url = card.get("image_url") or ""

    price_stats_html, price_table_html = _static_price_html(price_info)
    price_empty_hidden = "hidden" if price_info else ""

    ability_html = ""
    if card.get("ability_text"):
        ability_html = f'<div class="info-block"><h3>テキスト</h3><p>{_e(card["ability_text"])}</p></div>'
    trigger_html = ""
    if card.get("trigger_text"):
        trigger_html = f'<div class="info-block"><h3>トリガー</h3><p>{_e(card["trigger_text"])}</p></div>'

    card_detail_json = _json_script({"id": card["id"], "card_num": card.get("card_num"), "name": card["name"]})

    ld_json = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": card["name"],
        "image": image_url,
        "description": description,
        "url": page_url,
    }
    if price_info:
        prices = [s["price"] for s in price_info["shops"]]
        ld_json["offers"] = {
            "@type": "AggregateOffer",
            "priceCurrency": "JPY",
            "lowPrice": min(prices),
            "highPrice": max(prices),
            "offerCount": len(prices),
        }

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<!-- card/配下のページはサイトルート基準の相対パス(data/cards.json等)をそのまま
     使えるよう<base>でルートを指定する。 -->
<base href="../">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="{_e(description)}">
<link rel="canonical" href="{page_url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="ワンピースカードゲーム カード図鑑">
<meta property="og:locale" content="ja_JP">
<meta property="og:url" content="{page_url}">
<meta property="og:title" content="{_e(title)}">
<meta property="og:description" content="{_e(description)}">
<meta property="og:image" content="{_e(image_url)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{_e(title)}">
<meta name="twitter:description" content="{_e(description)}">
<meta name="twitter:image" content="{_e(image_url)}">
<title>{_e(title)}</title>
<link rel="stylesheet" href="style.css?v={ASSET_VERSION}">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9080305842487680" crossorigin="anonymous"></script>
<script type="application/ld+json">{_json_script(ld_json)}</script>
</head>
<body>
<header class="toolbar">
  <div class="title-row">
    <div class="title-block">
      <h1>{_e(card['name'])}</h1>
      <p id="last-updated" class="last-updated"></p>
    </div>
    <div class="nav-links">
      {_nav_links_html()}
    </div>
    <button type="button" class="nav-menu-toggle" aria-label="メニュー" aria-expanded="false">☰</button>
  </div>
</header>

<main class="card-detail-page">
  <div class="modal-card card-detail-card">
    <div class="modal-body">
      <div class="modal-image">
        <img src="{_e(image_url)}" alt="{_e(card['name'])}">
      </div>
      <div class="modal-info">
        <div class="modal-card-id">{_e(card['id'])}</div>
        {_field_rows_html(card)}
        {ability_html}
        {trigger_html}
      </div>
    </div>

    <div class="info-block price-block">
      <h3>相場</h3>
      {price_stats_html}
      {price_table_html}
      <div class="price-chart-col">
        <div class="period-tabs hidden" id="period-tabs">
          <button type="button" class="period-tab" data-days="0">全期間</button>
          <button type="button" class="period-tab active" data-days="30">30日</button>
          <button type="button" class="period-tab" data-days="7">7日</button>
        </div>
        <canvas id="price-chart" width="420" height="200" class="hidden"></canvas>
        <p id="chart-empty" class="price-empty {price_empty_hidden}">{"" if price_info else "価格データがありません。"}</p>
      </div>
    </div>
  </div>

  <p class="card-detail-back"><a href="index.html">← カード一覧へ戻る</a></p>
</main>

<footer class="site-disclaimer">
  <p>価格情報は当サイト調べです。実際の価格・在庫状況と差異が生じる場合があります。掲載しているカード画像はワンピースカードゲーム公式サイトの情報を参照しています。</p>
  <p><a href="about.html">運営者情報</a>　<a href="privacy.html">プライバシーポリシー・お問い合わせ</a></p>
</footer>

<script>window.CARD_DETAIL = {card_detail_json};</script>
<script src="common.js?v={ASSET_VERSION}"></script>
<script src="card-detail.js?v={ASSET_VERSION}"></script>
</body>
</html>
"""


def generate_card_pages(conn) -> int:
    CARD_PAGE_DIR.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(f"SELECT {', '.join(CARD_FIELDS)} FROM cards").fetchall()
    cards = []
    for row in rows:
        card = dict(row)
        local_name = images.local_filename(card["id"], card["image_url"])
        card["image_url"] = f"images/cards/{local_name}" if local_name else None
        cards.append(card)

    prices_latest = build_prices_latest_json(conn)

    existing = {p.stem for p in CARD_PAGE_DIR.glob("*.html")}
    written = set()
    for card in cards:
        html_text = _card_page_html(card, prices_latest.get(card["id"]))
        (CARD_PAGE_DIR / f"{card['id']}.html").write_text(html_text, encoding="utf-8")
        written.add(card["id"])
    for stale in existing - written:
        (CARD_PAGE_DIR / f"{stale}.html").unlink(missing_ok=True)

    generate_sitemap([c["id"] for c in cards])
    return len(cards)


def generate_sitemap(card_ids: list[str]) -> None:
    urls = [f"{SITE_BASE_URL}/{page}" for page in STATIC_PAGES]
    urls += [f"{SITE_BASE_URL}/card/{card_id}.html" for card_id in card_ids]
    body = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )
    (SITE_DIR / "sitemap.xml").write_text(xml, encoding="utf-8")


def main():
    conn = db.get_connection()
    db.init_db(conn)
    try:
        count = generate_card_pages(conn)
    finally:
        conn.close()
    print(f"card pages: {count}件 -> {CARD_PAGE_DIR}")
    print(f"sitemap.xml: {len(STATIC_PAGES) + count}件のURL")


if __name__ == "__main__":
    main()
