/* ワンピースカードゲーム カード図鑑 — 一覧・検索・詳細モーダル */
(function () {
  "use strict";

  let allCards = [];
  let meta = null;
  let pricesLatest = {};

  const state = {
    keyword: "",
    colors: new Set(),
    types: new Set(),
    rarities: new Set(),
    packs: new Set(),
  };

  const grid = document.getElementById("card-grid");
  const resultCount = document.getElementById("result-count");
  const keywordInput = document.getElementById("keyword");

  function cardMatches(card) {
    if (state.keyword) {
      const kw = state.keyword;
      const haystack = [card.name, card.feature, card.ability_text, card.trigger_text]
        .filter(Boolean).join(" ");
      if (!haystack.includes(kw)) return false;
    }
    if (state.colors.size && !state.colors.has(card.color)) return false;
    if (state.types.size && !state.types.has(card.card_type)) return false;
    if (state.rarities.size && !state.rarities.has(card.rarity)) return false;
    if (state.packs.size && !state.packs.has(card.pack)) return false;
    return true;
  }

  function renderGrid() {
    const filtered = allCards.filter(cardMatches);
    resultCount.textContent = `${filtered.length}件 / 全${allCards.length}件`;

    const frag = document.createDocumentFragment();
    for (const card of filtered) {
      const priceInfo = pricesLatest[card.id];
      const priceBadge = priceInfo
        ? `<div class="card-tile-price">¥${priceInfo.best.price.toLocaleString()}〜</div>`
        : "";
      const tile = document.createElement("button");
      tile.type = "button";
      tile.className = "card-tile";
      tile.innerHTML = `
        <img class="card-thumb" src="${card.image_url || ""}" alt="${card.name}" loading="lazy">
        <div class="card-tile-name">${card.name}</div>
        <div class="card-tile-sub">${card.id} ・ ${card.rarity || ""}</div>
        ${priceBadge}
      `;
      tile.addEventListener("click", () => openModal(card));
      frag.appendChild(tile);
    }
    grid.replaceChildren(frag);
  }

  function buildCheckboxList(containerId, values, targetSet) {
    const container = document.getElementById(containerId);
    const frag = document.createDocumentFragment();
    for (const value of values) {
      if (!value) continue;
      const label = document.createElement("label");
      label.className = "checkbox-item";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = value;
      input.addEventListener("change", () => {
        if (input.checked) targetSet.add(value);
        else targetSet.delete(value);
        renderGrid();
      });
      label.appendChild(input);
      label.appendChild(document.createTextNode(" " + value));
      frag.appendChild(label);
    }
    container.replaceChildren(frag);
  }

  function resetFilters() {
    state.keyword = "";
    state.colors.clear();
    state.types.clear();
    state.rarities.clear();
    state.packs.clear();
    keywordInput.value = "";
    document.querySelectorAll(".checkbox-list input[type=checkbox]").forEach((el) => {
      el.checked = false;
    });
    renderGrid();
  }

  function statRow(label, value) {
    if (value === null || value === undefined || value === "") return "";
    return `<div class="info-row"><span class="info-label">${label}</span><span class="info-value">${value}</span></div>`;
  }

  // 駿河屋アフィリエイト(Smart Biz Affiliate)のリンク生成。
  // user_id=固定のアフィリエイターID、goods_url=転送先URLをエンコードしたもの、という
  // 仕組みなので、カードごとの検索結果URLを組み立てて渡せば全カード分を自動生成できる。
  const SURUGAYA_AFFILIATE_USER_ID = "5367";

  function surugaSearchUrl(cardNum) {
    const query = `ワンピースカードゲーム ${cardNum}`;
    return `https://www.suruga-ya.jp/search?category=&search_word=${encodeURIComponent(query)}`;
  }

  function surugaAffiliateUrl(cardNum) {
    const target = surugaSearchUrl(cardNum);
    return `https://affiliate.suruga-ya.jp/modules/af/af_jump.php?user_id=${SURUGAYA_AFFILIATE_USER_ID}&goods_url=${encodeURIComponent(target)}`;
  }

  // 駿河屋以外はアフィリエイト提携が無いため、素の検索ページへのリンクのみ設置する
  // (金銭的な結びつきが無いことを景表法上も正しく反映するため「PR」表記は付けない)。
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

  function priceSection(card) {
    const priceInfo = pricesLatest[card.id];
    if (!priceInfo) {
      return `<div class="info-block price-block"><h3>相場</h3><p class="price-empty">価格データがありません。</p></div>`;
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
        <div class="price-best">¥${priceInfo.best.price.toLocaleString()}〜 (${priceInfo.best.site})</div>
        ${shopRows}
      </div>
    `;
  }

  function openModal(card) {
    const overlay = document.getElementById("modal-overlay");
    const img = document.getElementById("modal-image");
    const info = document.getElementById("modal-info");

    img.src = card.image_url || "";
    img.alt = card.name;

    const costOrLife = card.card_type === "LEADER"
      ? statRow("ライフ", card.life)
      : statRow("コスト", card.cost);

    info.innerHTML = `
      <h2 class="modal-card-name">${card.name}</h2>
      <div class="modal-card-id">${card.id} ・ ${card.rarity || ""} ・ ${card.card_type || ""}</div>
      ${costOrLife}
      ${statRow("パワー", card.power)}
      ${statRow("カウンター", card.counter)}
      ${statRow("属性", card.attribute)}
      ${statRow("色", card.color)}
      ${statRow("ブロックアイコン", card.block_icon)}
      ${statRow("特徴", card.feature)}
      ${card.ability_text ? `<div class="info-block"><h3>テキスト</h3><p>${card.ability_text}</p></div>` : ""}
      ${card.trigger_text ? `<div class="info-block"><h3>トリガー</h3><p>${card.trigger_text}</p></div>` : ""}
      ${statRow("収録パック", card.pack)}
      ${priceSection(card)}
    `;

    overlay.classList.remove("hidden");
  }

  function closeModal() {
    document.getElementById("modal-overlay").classList.add("hidden");
  }

  function init() {
    Promise.all([
      fetch("data/cards.json").then((r) => r.json()),
      fetch("data/meta.json").then((r) => r.json()),
      fetch("data/prices_latest.json").then((r) => (r.ok ? r.json() : {})),
    ]).then(([cards, metaJson, prices]) => {
      allCards = cards;
      meta = metaJson;
      pricesLatest = prices;

      document.getElementById("last-updated").textContent =
        "最終更新: " + new Date(meta.generated_at).toLocaleString("ja-JP");

      buildCheckboxList("filter-color-list", meta.colors, state.colors);
      buildCheckboxList("filter-type-list", meta.card_types, state.types);
      buildCheckboxList("filter-rarity-list", meta.rarities, state.rarities);
      buildCheckboxList("filter-pack-list", meta.packs, state.packs);

      renderGrid();
    });

    keywordInput.addEventListener("input", () => {
      state.keyword = keywordInput.value.trim();
      renderGrid();
    });

    document.getElementById("reset-filters").addEventListener("click", resetFilters);
    document.getElementById("modal-close").addEventListener("click", closeModal);
    document.getElementById("modal-overlay").addEventListener("click", (e) => {
      if (e.target.id === "modal-overlay") closeModal();
    });
    document.getElementById("toggle-filters").addEventListener("click", () => {
      document.getElementById("filters-panel").classList.toggle("open");
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
