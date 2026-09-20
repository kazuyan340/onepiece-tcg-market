/* ワンピースカードゲーム カード図鑑 — 一覧・検索(common.jsの上に乗る一覧ページ専用処理) */
(function () {
  "use strict";

  let allCards = [];
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
      frag.appendChild(createCardTile(card, pricesLatest));
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

  async function init() {
    const [cards, meta, prices] = await Promise.all([
      loadCardData(),
      loadSiteMeta(),
      loadPricesLatest(),
    ]);
    allCards = cards;
    pricesLatest = prices;
    renderLastUpdated();

    buildCheckboxList("filter-color-list", meta.colors, state.colors);
    buildCheckboxList("filter-type-list", meta.card_types, state.types);
    buildCheckboxList("filter-rarity-list", meta.rarities, state.rarities);
    buildCheckboxList("filter-pack-list", meta.packs, state.packs);

    renderGrid();

    keywordInput.addEventListener("input", () => {
      state.keyword = keywordInput.value.trim();
      renderGrid();
    });

    document.getElementById("reset-filters").addEventListener("click", resetFilters);
    bindModalEvents();
    bindFiltersToggle();
    bindNavMenuToggle();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
