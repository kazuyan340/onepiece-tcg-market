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

  function priceSection(card) {
    const priceInfo = pricesLatest[card.id];
    if (!priceInfo) {
      return `<div class="info-block price-block"><h3>相場</h3><p class="price-empty">価格データがありません。</p></div>`;
    }
    const updatedAt = new Date(priceInfo.best.recorded_at).toLocaleDateString("ja-JP");
    const shopRows = priceInfo.shops
      .slice()
      .sort((a, b) => a.price - b.price)
      .map((shop) => `
        <div class="price-shop-row">
          <span>${shop.site}</span>
          <span>¥${shop.price.toLocaleString()} (${shop.sample_count}件の出品中最安値)</span>
        </div>
      `).join("");
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
