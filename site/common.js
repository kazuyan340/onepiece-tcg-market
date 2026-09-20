/* ワンピースカードゲーム カード図鑑 — 各ページ共通のヘルパー
   (データ読み込み、カードタイル、モーダル、お気に入り、ナビ開閉)。 */

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function fetchFresh(url) {
  return fetch(url, { cache: "no-store" });
}

async function loadCardData() {
  const res = await fetchFresh("data/cards.json");
  return res.json();
}

async function loadPricesLatest() {
  const res = await fetchFresh("data/prices_latest.json");
  return res.ok ? res.json() : {};
}

let siteMeta = null;

async function loadSiteMeta() {
  const res = await fetchFresh("data/meta.json");
  siteMeta = await res.json();
  return siteMeta;
}

function renderLastUpdated() {
  const el = document.getElementById("last-updated");
  if (el && siteMeta) {
    el.textContent = "最終更新: " + new Date(siteMeta.generated_at).toLocaleString("ja-JP");
  }
}

// ---- お気に入り(ブラウザのlocalStorageのみに保存。サーバーには送らない) ----
const FAVORITES_KEY = "onepieceTcgFavorites";

function loadFavorites() {
  try {
    return new Set(JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveFavorites(set) {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify([...set]));
}

function isFavorite(cardId) {
  return loadFavorites().has(cardId);
}

function toggleFavorite(cardId) {
  const set = loadFavorites();
  const now = !set.has(cardId);
  if (now) set.add(cardId);
  else set.delete(cardId);
  saveFavorites(set);
  return now;
}

// ---- ショップへのリンク(駿河屋のみアフィリエイト、他は素の検索リンク) ----
const SURUGAYA_AFFILIATE_USER_ID = "5367";

function surugaSearchUrl(cardNum) {
  const query = `ワンピースカードゲーム ${cardNum}`;
  return `https://www.suruga-ya.jp/search?category=&search_word=${encodeURIComponent(query)}`;
}

function surugaAffiliateUrl(cardNum) {
  const target = surugaSearchUrl(cardNum);
  return `https://affiliate.suruga-ya.jp/modules/af/af_jump.php?user_id=${SURUGAYA_AFFILIATE_USER_ID}&goods_url=${encodeURIComponent(target)}`;
}

const SHOP_LINK_BUILDERS = {
  "駿河屋": (cardNum) => surugaAffiliateUrl(cardNum),
  "カードラボ": (cardNum) => `https://www.c-labo-online.jp/product-list/?keyword=${encodeURIComponent(cardNum)}`,
  "まんぞく屋": (cardNum) => `https://shopmanzokuya.com/products/list?category_id=2636&name=${encodeURIComponent(cardNum)}`,
  "わいTV": (cardNum) => `https://www.cardshop-waitv.net/product-list/1?keyword=${encodeURIComponent(cardNum)}`,
  "カードラッシュ": (cardNum) => `https://www.cardrush-op.jp/product-list?keyword=${encodeURIComponent(cardNum)}`,
};

function shopLinkUrl(site, cardNum) {
  const builder = SHOP_LINK_BUILDERS[site];
  return builder ? builder(cardNum) : null;
}

// ---- メルカリ・Amazon・楽天市場の「価格を確認する」ボタン(スクレイピング対象外の
// 一般マーケットプレイス向け。アフィリエイトIDはconan-tcg-marketと共用) ----
const MERCARI_AFFILIATE_ID = "8969530097";

function mercariAffiliateUrl(query) {
  return `https://jp.mercari.com/search?afid=${MERCARI_AFFILIATE_ID}&keyword=${encodeURIComponent(query)}`;
}

function mercariButtonHtml(cardName, cardId, cardRarity) {
  if (!cardName) return "";
  const query = `${cardName} ${cardId || ""} ${cardRarity || ""}`.replace(/\s+/g, " ").trim();
  return `<a class="marketplace-check-btn" href="${mercariAffiliateUrl(query)}" target="_blank" rel="nofollow noopener sponsored">🔍 メルカリで価格を確認する <span class="pr-label">PR</span></a>`;
}

const AMAZON_ASSOCIATE_TAG = "conantcgmarke-22";

function amazonCardSearchUrl(query) {
  const url = `https://www.amazon.co.jp/s?k=${encodeURIComponent(query)}`;
  return AMAZON_ASSOCIATE_TAG ? `${url}&tag=${AMAZON_ASSOCIATE_TAG}` : url;
}

function amazonButtonHtml(cardName, cardId, cardRarity) {
  if (!cardName) return "";
  const query = `${cardName} ${cardId || ""} ${cardRarity || ""}`.replace(/\s+/g, " ").trim();
  return `<a class="marketplace-check-btn" href="${amazonCardSearchUrl(query)}" target="_blank" rel="nofollow noopener sponsored">🔍 Amazonで価格を確認する <span class="pr-label">PR</span></a>`;
}

const RAKUTEN_AFFILIATE_ID = "567cd45a.2625f6eb.567cd45b.7e49c506";

function rakutenCardSearchUrl(query) {
  const url = `https://search.rakuten.co.jp/search/mall/${encodeURIComponent(query)}/`;
  if (!RAKUTEN_AFFILIATE_ID) return url;
  return `https://hb.afl.rakuten.co.jp/hgc/${RAKUTEN_AFFILIATE_ID}/?pc=${encodeURIComponent(url)}`;
}

function rakutenButtonHtml(cardName, cardId, cardRarity) {
  if (!cardName) return "";
  const query = `${cardName} ${cardId || ""} ${cardRarity || ""}`.replace(/\s+/g, " ").trim();
  return `<a class="marketplace-check-btn" href="${rakutenCardSearchUrl(query)}" target="_blank" rel="nofollow noopener sponsored">🔍 楽天市場で価格を確認する <span class="pr-label">PR</span></a>`;
}

function purchaseButtonsHtml(cardName, cardId, cardRarity) {
  return `<div class="purchase-buttons">${mercariButtonHtml(cardName, cardId, cardRarity)}${amazonButtonHtml(cardName, cardId, cardRarity)}${rakutenButtonHtml(cardName, cardId, cardRarity)}</div>`;
}

// ---- カードタイル(一覧・ランキング・値動き等で共用) ----
function statRow(label, value) {
  if (value === null || value === undefined || value === "") return "";
  return `<div class="info-row"><span class="info-label">${label}</span><span class="info-value">${value}</span></div>`;
}

function createCardTile(card, pricesLatest, badgeHtml) {
  const priceInfo = pricesLatest[card.id];
  const priceBadge = priceInfo
    ? `<div class="card-tile-price">¥${priceInfo.best.price.toLocaleString()}〜</div>`
    : "";
  const tile = document.createElement("button");
  tile.type = "button";
  tile.className = "card-tile";
  tile.innerHTML = `
    ${badgeHtml || ""}
    <img class="card-thumb" src="${card.image_url || ""}" alt="${escapeHtml(card.name)}" loading="lazy">
    <div class="card-tile-name">${escapeHtml(card.name)}</div>
    <div class="card-tile-sub">${card.id} ・ ${escapeHtml(card.rarity || "")}</div>
    ${priceBadge}
  `;

  const star = document.createElement("button");
  star.type = "button";
  star.className = "favorite-star" + (isFavorite(card.id) ? " active" : "");
  star.textContent = isFavorite(card.id) ? "★" : "☆";
  star.title = "お気に入りに登録/解除";
  star.addEventListener("click", (e) => {
    e.stopPropagation();
    const nowFav = toggleFavorite(card.id);
    star.textContent = nowFav ? "★" : "☆";
    star.classList.toggle("active", nowFav);
  });
  tile.prepend(star);

  tile.addEventListener("click", () => openModal(card, pricesLatest));
  return tile;
}

// ---- 詳細モーダル(相場・簡易グラフ付き) ----
const priceHistoryCache = new Map();

function fetchPriceHistory(cardId) {
  if (priceHistoryCache.has(cardId)) return priceHistoryCache.get(cardId);
  const promise = fetchFresh(`data/prices/${cardId}.json`)
    .then((r) => (r.ok ? r.json() : []))
    .catch(() => []);
  priceHistoryCache.set(cardId, promise);
  return promise;
}

function priceSection(card, pricesLatest) {
  const priceInfo = pricesLatest[card.id];
  const purchaseButtons = purchaseButtonsHtml(card.name, card.id, card.rarity);
  if (!priceInfo) {
    return `<div class="info-block price-block"><h3>相場</h3><p class="price-empty">価格データがありません。</p>${purchaseButtons}</div>`;
  }
  const updatedAt = new Date(priceInfo.best.recorded_at).toLocaleDateString("ja-JP");
  const shopRows = priceInfo.shops
    .slice()
    .sort((a, b) => a.price - b.price)
    .map((shop) => {
      const url = shopLinkUrl(shop.site, card.card_num);
      const shopLabel = url
        ? `<a href="${url}" target="_blank" rel="noopener">${shop.site}</a>`
        : shop.site;
      return `
        <div class="price-shop-row">
          <span>${shopLabel}</span>
          <span>¥${shop.price.toLocaleString()} (${shop.sample_count}件の出品中最安値)</span>
        </div>
      `;
    }).join("");
  return `
    <div class="info-block price-block">
      <h3>相場(最終取得: ${updatedAt})</h3>
      <div class="price-best">¥${priceInfo.best.price.toLocaleString()}〜 (${priceInfo.best.site}) / 全ショップ平均 ¥${priceInfo.pooled_avg.toLocaleString()}</div>
      ${shopRows}
      ${purchaseButtons}
      <div class="price-chart-col">
        <div class="period-tabs" id="period-tabs">
          <button type="button" class="period-tab" data-days="0">全期間</button>
          <button type="button" class="period-tab active" data-days="30">30日</button>
          <button type="button" class="period-tab" data-days="7">7日</button>
        </div>
        <canvas id="price-chart" width="420" height="200"></canvas>
        <p id="chart-empty" class="price-empty hidden">推移データがまだありません。</p>
      </div>
    </div>
  `;
}

function pooledSeriesFromHistory(history) {
  // カードごとの価格履歴(全ショップ混在)から、日付ごとの全ショップ単純平均を作る。
  const byDay = new Map();
  for (const p of history) {
    const day = p.recorded_at.slice(0, 10);
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push(p.price);
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([day, prices]) => ({
      day,
      price: Math.round(prices.reduce((a, b) => a + b, 0) / prices.length),
    }));
}

function drawSimpleChart(canvas, points) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (points.length < 2) return;

  const padding = { top: 12, right: 12, bottom: 22, left: 50 };
  const plotW = w - padding.left - padding.right;
  const plotH = h - padding.top - padding.bottom;
  const prices = points.map((p) => p.price);
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const range = maxP - minP || 1;

  const x = (i) => padding.left + (i / (points.length - 1)) * plotW;
  const y = (v) => padding.top + plotH - ((v - minP) / range) * plotH;

  ctx.strokeStyle = "#3a4a5c";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, padding.top + plotH);
  ctx.lineTo(padding.left + plotW, padding.top + plotH);
  ctx.stroke();

  ctx.fillStyle = "#a9b4bf";
  ctx.font = "10px sans-serif";
  ctx.textAlign = "right";
  ctx.fillText(`¥${maxP.toLocaleString()}`, padding.left - 4, padding.top + 8);
  ctx.fillText(`¥${minP.toLocaleString()}`, padding.left - 4, padding.top + plotH);

  ctx.strokeStyle = "#ffd166";
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const px = x(i);
    const py = y(p.price);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();

  ctx.fillStyle = "#ffd166";
  points.forEach((p, i) => {
    ctx.beginPath();
    ctx.arc(x(i), y(p.price), 2.5, 0, Math.PI * 2);
    ctx.fill();
  });

  ctx.fillStyle = "#a9b4bf";
  ctx.textAlign = "center";
  ctx.fillText(points[0].day.slice(5), x(0), h - 6);
  ctx.fillText(points[points.length - 1].day.slice(5), x(points.length - 1), h - 6);
}

function bindPeriodTabs(canvas, series) {
  const tabs = document.querySelectorAll("#period-tabs .period-tab");
  const emptyEl = document.getElementById("chart-empty");

  function render(days) {
    const filtered = days > 0
      ? series.filter((p) => {
          const diffDays = (Date.now() - new Date(p.day).getTime()) / 86400000;
          return diffDays <= days;
        })
      : series;
    canvas.hidden = filtered.length < 2;
    emptyEl.hidden = filtered.length >= 2;
    if (filtered.length >= 2) drawSimpleChart(canvas, filtered);
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      render(Number(tab.dataset.days));
    });
  });

  render(30);
}

function openModal(card, pricesLatest) {
  const overlay = document.getElementById("modal-overlay");
  const img = document.getElementById("modal-image");
  const info = document.getElementById("modal-info");
  const favBtn = document.getElementById("modal-favorite");

  img.src = card.image_url || "";
  img.alt = card.name;

  const costOrLife = card.card_type === "LEADER"
    ? statRow("ライフ", card.life)
    : statRow("コスト", card.cost);

  info.innerHTML = `
    <h2 class="modal-card-name">${escapeHtml(card.name)}</h2>
    <div class="modal-card-id">${card.id} ・ ${escapeHtml(card.rarity || "")} ・ ${escapeHtml(card.card_type || "")}</div>
    <a class="modal-detail-link" href="card/${card.id}.html">🔗 このカードの詳細ページを見る</a>
    ${costOrLife}
    ${statRow("パワー", card.power)}
    ${statRow("カウンター", card.counter)}
    ${statRow("属性", card.attribute)}
    ${statRow("色", card.color)}
    ${statRow("ブロックアイコン", card.block_icon)}
    ${statRow("特徴", card.feature)}
    ${card.ability_text ? `<div class="info-block"><h3>テキスト</h3><p>${escapeHtml(card.ability_text)}</p></div>` : ""}
    ${card.trigger_text ? `<div class="info-block"><h3>トリガー</h3><p>${escapeHtml(card.trigger_text)}</p></div>` : ""}
    ${statRow("収録パック", card.pack)}
    ${priceSection(card, pricesLatest)}
  `;

  if (favBtn) {
    favBtn.textContent = isFavorite(card.id) ? "★" : "☆";
    favBtn.classList.toggle("active", isFavorite(card.id));
    favBtn.onclick = () => {
      const nowFav = toggleFavorite(card.id);
      favBtn.textContent = nowFav ? "★" : "☆";
      favBtn.classList.toggle("active", nowFav);
    };
  }

  overlay.classList.remove("hidden");

  const canvas = document.getElementById("price-chart");
  if (canvas && pricesLatest[card.id]) {
    fetchPriceHistory(card.id).then((history) => {
      const series = pooledSeriesFromHistory(history);
      bindPeriodTabs(canvas, series);
    });
  }
}

function closeModal() {
  document.getElementById("modal-overlay").classList.add("hidden");
}

function bindModalEvents() {
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-overlay").addEventListener("click", (e) => {
    if (e.target.id === "modal-overlay") closeModal();
  });
}

// ---- ナビ用の三本線メニュー ----
function bindNavMenuToggle() {
  const btn = document.querySelector(".nav-menu-toggle");
  const nav = document.querySelector(".nav-links");
  if (!btn || !nav) return;

  const backdrop = document.createElement("div");
  backdrop.className = "nav-backdrop";
  nav.parentNode.insertBefore(backdrop, nav);

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "nav-drawer-close";
  closeBtn.setAttribute("aria-label", "閉じる");
  closeBtn.textContent = "✕";
  nav.insertBefore(closeBtn, nav.firstChild);

  function setOpen(isOpen) {
    nav.classList.toggle("open", isOpen);
    backdrop.classList.toggle("open", isOpen);
    btn.setAttribute("aria-expanded", String(isOpen));
    document.body.style.overflow = isOpen ? "hidden" : "";
  }

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    setOpen(!nav.classList.contains("open"));
  });

  closeBtn.addEventListener("click", () => setOpen(false));
  backdrop.addEventListener("click", () => setOpen(false));

  document.addEventListener("click", (e) => {
    if (nav.classList.contains("open") && !nav.contains(e.target) && e.target !== btn) {
      setOpen(false);
    }
  });
}

// ---- 絞り込みパネルの開閉(一覧・ランキングで共用) ----
function bindFiltersToggle() {
  const btn = document.getElementById("toggle-filters");
  const panel = document.getElementById("filters-panel");
  if (!btn || !panel) return;
  btn.addEventListener("click", () => panel.classList.toggle("open"));
}
